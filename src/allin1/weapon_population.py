"""Receipt-authorized ambient NPC weapon replacement policy.

This launcher-side module only writes a bounded policy consumed by the game
runtime.  It never grants a player weapon, changes a save, or launches GTA.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from allin1.extensions import ExtensionRegistry
from allin1.ped_population import (
    MAX_CATALOG_BYTES, _DIGEST, _read_bounded_bytes, _safe_identifier, _sha256,
)
from allin1.release_paths import filesystem_path, no_links, strict_json
from allin1.weapon_catalog import WeaponCatalog


SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_ENTRIES = 512
POLICY_RELATIVE_PATH = PurePosixPath("scripts/.allin1/weapon-population.json")
# Keep the launcher inventory exactly aligned with the conservative runtime
# tier map.  A visible toggle must never produce a document the injector will
# quietly reject.
SUPPORTED_CATEGORIES = frozenset({"pistols", "smgs", "shotguns", "rifles"})


def _default_document() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "enabled": False,
            "active_during_missions": False, "replacement_chance": 0.0,
            "entries": []}


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _policy_path(game: str | Path) -> Path:
    root = no_links(Path(game).expanduser())
    return no_links(root / Path(*POLICY_RELATIVE_PATH.parts))


def _catalog_hashes(extension: dict[str, Any]) -> dict[str, str]:
    rows = extension.get("catalog_files", [])
    if not isinstance(rows, list):
        return {}
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path", "")).replace("\\", "/")
        digest = str(row.get("sha256", "")).lower()
        if path and _DIGEST.fullmatch(digest):
            result[path.casefold()] = digest
    return result


def _discover_models(game: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Return only currently enabled, receipt-hashed add-on weapon records."""
    try:
        registry = ExtensionRegistry(game).inspect()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"extension registry inspection failed: {exc}"]
    records: list[dict[str, str]] = []
    weapons: set[str] = set()
    warnings: list[str] = []
    for extension in registry.get("extensions", []):
        if not isinstance(extension, dict) or not extension.get("enabled"):
            continue
        try:
            package_id = _safe_identifier(extension.get("id"), "weapon package id")
            capabilities = extension.get("capabilities", [])
            if not isinstance(capabilities, list) or "gbay.catalogs" not in {
                str(value).lower() for value in capabilities
            }:
                continue
            gbay = extension.get("gbay", {})
            if not isinstance(gbay, dict) or not isinstance(gbay.get("catalogs", []), list):
                raise ValueError("malformed catalog authorization")
            # A GBAY-capable extension can legitimately publish only another
            # catalog kind (the built-in Online Content extension does this).
            # It is irrelevant to weapon population and therefore has no
            # reason to prove DLC ownership here.  Once an extension declares
            # a weapon catalog, however, retain the receipt/DLC check before
            # touching that catalog or admitting any weapon from it.
            weapon_catalogs = [
                declaration for declaration in gbay["catalogs"]
                if isinstance(declaration, dict)
                and str(declaration.get("kind", "")).lower() == "weapon"
            ]
            if not weapon_catalogs:
                continue
            declared_packs = extension.get("dlc_packs")
            if (not isinstance(declared_packs, list) or not declared_packs or
                    any(not isinstance(pack, str) for pack in declared_packs) or
                    len(set(declared_packs)) != len(declared_packs)):
                raise ValueError("no valid registry receipt-declared DLC packs")
            for pack in declared_packs:
                if _safe_identifier(pack, "declared DLC pack") != pack:
                    raise ValueError("no valid registry receipt-declared DLC packs")
            hashes = _catalog_hashes(extension)
            pending: list[dict[str, str]] = []
            package_weapons: set[str] = set()
            for declaration in weapon_catalogs:
                catalog_id = _safe_identifier(declaration.get("id"), "weapon catalog id")
                source = str(declaration.get("source", "")).replace("\\", "/")
                relative = PurePosixPath(source)
                if (not relative.parts or relative.is_absolute() or ".." in relative.parts
                        or any(not part for part in relative.parts)
                        or relative.as_posix() != source):
                    raise ValueError("weapon catalog source is not contained")
                expected = hashes.get(relative.as_posix().casefold())
                if not expected:
                    raise ValueError("weapon catalog lacks a receipt hash")
                path = no_links(game / Path(*relative.parts))
                raw = _read_bounded_bytes(path, MAX_CATALOG_BYTES, "weapon catalog")
                if _sha256(raw) != expected:
                    raise ValueError("weapon catalog failed its receipt hash")
                catalog = WeaponCatalog.from_dict(strict_json(raw))
                if catalog.catalog_id != catalog_id:
                    raise ValueError("weapon catalog id does not match its declaration")
                catalog.validate_package_ownership(declared_packs)
                for item in catalog.weapons:
                    if item.category not in SUPPORTED_CATEGORIES:
                        continue
                    if item.weapon in package_weapons:
                        raise ValueError(f"duplicate authorized add-on weapon: {item.weapon}")
                    package_weapons.add(item.weapon)
                    pending.append({"package_id": package_id, "weapon": item.weapon,
                                    "name": item.name, "category": item.category})
            if any(row["weapon"] in weapons for row in pending):
                raise ValueError("duplicate authorized add-on weapon across packages")
            weapons.update(row["weapon"] for row in pending)
            records.extend(pending)
        except (FileNotFoundError, OSError, ValueError) as exc:
            warnings.append(f"{extension.get('id', 'unknown')}: {exc}")
    records.sort(key=lambda row: (row["package_id"], row["weapon"]))
    return records, warnings


def _normalize_document(document: object, records: list[dict[str, str]]) -> dict[str, Any]:
    required = {"schema_version", "enabled", "replacement_chance", "entries"}
    allowed = required | {"active_during_missions"}
    if not isinstance(document, dict) or not required <= set(document) or set(document) - allowed:
        raise ValueError("weapon population document must contain only schema_version, enabled, active_during_missions, replacement_chance and entries")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise ValueError("weapon population schema_version must be 1")
    if type(document["enabled"]) is not bool:
        raise ValueError("weapon population enabled must be a boolean")
    # Schema v1 documents written before this setting existed remain valid.
    # Normalize them to the explicit false value used by all new writes.
    active_during_missions = document.get("active_during_missions", False)
    if type(active_during_missions) is not bool:
        raise ValueError("weapon population active_during_missions must be a boolean")
    chance = document["replacement_chance"]
    if type(chance) not in (int, float) or not math.isfinite(float(chance)) or not 0 <= float(chance) <= 1:
        raise ValueError("weapon population replacement_chance must be finite and between 0 and 1")
    entries = document["entries"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError(f"weapon population entries must contain at most {MAX_ENTRIES} entries")
    authorized = {(row["package_id"], row["weapon"]): row for row in records}
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(entries, 1):
        if not isinstance(row, dict) or set(row) != {"package_id", "weapon", "enabled", "weight"}:
            raise ValueError(f"entries[{index}] must contain only package_id, weapon, enabled and weight")
        package_id = _safe_identifier(row["package_id"], f"entries[{index}].package_id")
        weapon = row["weapon"]
        if not isinstance(weapon, str) or weapon not in {key[1] for key in authorized}:
            raise ValueError(f"entries[{index}] is not an enabled receipt-authorized add-on weapon")
        key = (package_id, weapon)
        if key not in authorized:
            raise ValueError(f"entries[{index}] is not owned by its declared package")
        if key in seen:
            raise ValueError(f"entries contains duplicate weapon selection: {package_id}/{weapon}")
        seen.add(key)
        if type(row["enabled"]) is not bool:
            raise ValueError(f"entries[{index}].enabled must be a boolean")
        if type(row["weight"]) is not int or not 1 <= row["weight"] <= 100:
            raise ValueError(f"entries[{index}].weight must be an integer from 1 to 100")
        normalized.append({"package_id": package_id, "weapon": weapon,
                           "enabled": row["enabled"], "weight": row["weight"]})
    normalized.sort(key=lambda row: (row["package_id"], row["weapon"]))
    return {"schema_version": SCHEMA_VERSION, "enabled": document["enabled"],
            "active_during_missions": active_during_missions,
            "replacement_chance": float(chance), "entries": normalized}


def validate_document(game: str | Path, document: object) -> dict[str, Any]:
    root = no_links(Path(game).expanduser())
    records, warnings = _discover_models(root)
    if warnings:
        raise ValueError("Weapon catalog authorization is incomplete: " + "; ".join(warnings))
    return _normalize_document(document, records)


def inspect_population(game: str | Path) -> dict[str, Any]:
    root = no_links(Path(game).expanduser())
    path = _policy_path(root)
    warnings: list[str] = []
    try:
        raw = _read_bounded_bytes(path, MAX_DOCUMENT_BYTES, "weapon population document")
    except FileNotFoundError:
        document = _default_document(); raw = _canonical_bytes(document)
    except ValueError as exc:
        document = _default_document(); warnings.append(str(exc))
        raw = _canonical_bytes(document)
    else:
        try:
            document = strict_json(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            document = _default_document()
            warnings.append(f"Invalid weapon population document: {exc}")
    models, discovery_warnings = _discover_models(root)
    warnings.extend(discovery_warnings)
    try: normalized = _normalize_document(document, models)
    except ValueError as exc:
        normalized = _default_document(); warnings.append(str(exc))
    return {"document": normalized, "document_sha256": _sha256(raw),
            "models": models, "warnings": warnings}


def save_population(game: str | Path, document: object, expected_document_sha256: str) -> dict[str, Any]:
    if not isinstance(expected_document_sha256, str) or not _DIGEST.fullmatch(expected_document_sha256.lower()):
        raise ValueError("expected_document_sha256 must be a SHA-256 digest")
    root = no_links(Path(game).expanduser())
    normalized = validate_document(root, document)
    path = _policy_path(root)
    try: current = _read_bounded_bytes(path, MAX_DOCUMENT_BYTES, "weapon population document")
    except FileNotFoundError: current = _canonical_bytes(_default_document())
    if _sha256(current) != expected_document_sha256.lower():
        raise ValueError("Weapon population document changed; reload before saving")
    parent = no_links(path.parent)
    filesystem_path(parent).mkdir(parents=True, exist_ok=True); no_links(parent)
    payload = _canonical_bytes(normalized)
    temporary = no_links(parent / f".{path.name}.{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with filesystem_path(temporary).open("x", encoding="utf-8", newline="\n") as stream:
            created = True; stream.write(payload.decode("utf-8"))
        try:
            latest = _read_bounded_bytes(path, MAX_DOCUMENT_BYTES, "weapon population document")
        except FileNotFoundError:
            latest = _canonical_bytes(_default_document())
        if _sha256(latest) != expected_document_sha256.lower():
            raise ValueError("Weapon population document changed; reload before saving")
        no_links(parent)
        no_links(path); os.replace(filesystem_path(temporary), filesystem_path(path))
    finally:
        if created: filesystem_path(temporary).unlink(missing_ok=True)
    return {"document": normalized, "document_sha256": _sha256(payload), "path": str(path)}
