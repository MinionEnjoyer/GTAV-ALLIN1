"""Receipt-authorized configuration for ambient custom-ped population.

This module is intentionally launcher-side only.  It neither installs a DLC
pack nor starts GTA; it validates the small policy document consumed by the
managed Story Mode runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from allin1.extensions import ExtensionRegistry
from allin1.release_paths import filesystem_path, no_links, strict_json


SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_CATALOG_PEDS = 2048
MAX_ENTRIES = 512
MAX_ADDED = 20
POLICY_RELATIVE_PATH = PurePosixPath("scripts/.allin1/ped-population.json")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9._-]{1,95}$")
_MODEL = re.compile(r"^[a-z0-9_]{1,64}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")

# There is no existing authoritative pedestrian catalogue in this checkout.
# Replacement therefore starts with a deliberately small, civilian-only set;
# every runtime target is still checked as a loaded ped model before use.
SUPPORTED_VANILLA_TARGETS = (
    "a_f_m_beach_01", "a_f_m_bevhills_01", "a_f_m_business_02",
    "a_f_m_downtown_01", "a_f_m_eastsa_01", "a_f_m_fatbla_01",
    "a_f_m_fatcult_01", "a_f_m_ktown_01", "a_f_m_tourist_01",
    "a_f_y_beach_01", "a_f_y_bevhills_01", "a_f_y_business_01",
    "a_f_y_eastsa_01", "a_f_y_hipster_01", "a_f_y_tourist_01",
    "a_m_m_beach_01", "a_m_m_business_01", "a_m_m_eastsa_01",
    "a_m_m_genfat_01", "a_m_m_ktown_01", "a_m_m_malibu_01",
    "a_m_m_paparazzi_01", "a_m_m_salton_01", "a_m_m_skidrow_01",
    "a_m_m_socenlat_01", "a_m_m_soucent_01", "a_m_m_tourist_01",
    "a_m_y_beach_01", "a_m_y_bevhills_01", "a_m_y_business_01",
    "a_m_y_business_02", "a_m_y_downtown_01", "a_m_y_eastsa_01",
    "a_m_y_hipster_01", "a_m_y_ktown_01", "a_m_y_tourist_01",
)
_TARGET_SET = frozenset(SUPPORTED_VANILLA_TARGETS)


def _default_document() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "replacement_chance": 0.0,
        "max_added": 0,
        "entries": [],
    }


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _policy_path(game: str | Path) -> Path:
    root = no_links(Path(game).expanduser())
    return no_links(root / Path(*POLICY_RELATIVE_PATH.parts))


def _safe_identifier(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = value.strip().lower()
    if not _IDENTIFIER.fullmatch(normalized):
        raise ValueError(f"Invalid {label}: {value!r}")
    return normalized


def _safe_model(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = value.strip().lower()
    if not _MODEL.fullmatch(normalized):
        raise ValueError(f"Invalid {label}: {value!r}")
    return normalized


def _read_bounded_bytes(path: Path, limit: int, label: str) -> bytes:
    disk_path = filesystem_path(no_links(path))
    if not disk_path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    if disk_path.stat().st_size > limit:
        raise ValueError(f"{label} exceeds its {limit} byte limit")
    with disk_path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{label} exceeds its {limit} byte limit")
    return data


def _read_json_bytes(path: Path, limit: int, label: str) -> tuple[bytes, Any]:
    data = _read_bounded_bytes(path, limit, label)
    try:
        return data, strict_json(data)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid {label}: {exc}") from exc


def _parse_catalog(
    payload: Any, *, package_id: str, catalog_id: str, declared_packs: set[str],
) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "id", "name", "peds",
    }:
        raise ValueError("ped catalog must contain only schema_version, id, name and peds")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ValueError("ped catalog schema_version must be 1")
    if _safe_identifier(payload.get("id"), "ped catalog id") != catalog_id:
        raise ValueError("ped catalog id does not match its declared catalog")
    name = payload.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 128:
        raise ValueError("ped catalog name must be 1-128 characters")
    rows = payload.get("peds")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CATALOG_PEDS:
        raise ValueError(f"ped catalog peds must contain 1-{MAX_CATALOG_PEDS} entries")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or set(row) != {"model", "name", "source_pack"}:
            raise ValueError(f"ped catalog peds[{index}] has unsupported fields")
        model = _safe_model(row.get("model"), f"peds[{index}].model")
        if model in seen:
            raise ValueError(f"ped catalog contains duplicate model: {model}")
        seen.add(model)
        display_name = row.get("name")
        if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 128:
            raise ValueError(f"peds[{index}].name must be 1-128 characters")
        source_pack = _safe_identifier(row.get("source_pack"), f"peds[{index}].source_pack")
        if source_pack not in declared_packs:
            raise ValueError(
                f"peds[{index}].source_pack is not a receipt-declared DLC pack: {source_pack}"
            )
        result.append({
            "package_id": package_id,
            "catalog_id": catalog_id,
            "model": model,
            "name": display_name.strip(),
            "source_pack": source_pack,
        })
    return result


def _discover_models(game: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Return enabled, receipt-hashed ped records without publishing registry state."""
    warnings: list[str] = []
    try:
        registry = ExtensionRegistry(game).inspect()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"extension registry inspection failed: {exc}"]
    records: list[dict[str, str]] = []
    owners: set[tuple[str, str]] = set()
    for extension in registry.get("extensions", []):
        if not isinstance(extension, dict) or not extension.get("enabled"):
            continue
        package_id = str(extension.get("id", "")).strip().lower()
        try:
            capabilities = extension.get("capabilities", [])
            if not _IDENTIFIER.fullmatch(package_id) or not isinstance(capabilities, list):
                continue
            if "ped.population" not in {str(value).lower() for value in capabilities}:
                continue
            packs = extension.get("dlc_packs")
            if (not isinstance(packs, list) or not packs or
                    any(not isinstance(value, str) for value in packs) or
                    len(set(packs)) != len(packs)):
                raise ValueError("no valid registry receipt-declared DLC packs")
            declared_packs: set[str] = set()
            for value in packs:
                normalized = _safe_identifier(value, "declared DLC pack")
                if normalized != value:
                    raise ValueError("no valid registry receipt-declared DLC packs")
                declared_packs.add(normalized)
            gbay = extension.get("gbay", {})
            catalog_files = extension.get("catalog_files", [])
            if not isinstance(gbay, dict) or not isinstance(catalog_files, list):
                raise ValueError("malformed catalog authorization")
            hashes = {
                str(row.get("path", "")).replace("\\", "/").casefold(): str(row.get("sha256", "")).lower()
                for row in catalog_files if isinstance(row, dict)
            }
            catalogs = gbay.get("catalogs", [])
            if not isinstance(catalogs, list):
                raise ValueError("malformed catalog authorization")
            pending: list[dict[str, str]] = []
            package_models: set[str] = set()
            for catalog in catalogs:
                if not isinstance(catalog, dict) or str(catalog.get("kind", "")).lower() != "ped":
                    continue
                catalog_id = _safe_identifier(catalog.get("id"), "ped catalog id")
                source = str(catalog.get("source", "")).replace("\\", "/")
                relative = PurePosixPath(source)
                if (not relative.parts or relative.is_absolute() or ".." in relative.parts
                        or any(not part for part in relative.parts)
                        or relative.as_posix() != source):
                    raise ValueError("ped catalog source is not contained")
                expected = hashes.get(relative.as_posix().casefold(), "")
                if not _DIGEST.fullmatch(expected):
                    raise ValueError("ped catalog lacks a receipt hash")
                catalog_path = no_links(game / Path(*relative.parts))
                data, payload = _read_json_bytes(catalog_path, MAX_CATALOG_BYTES, "ped catalog")
                if _sha256(data) != expected:
                    raise ValueError("ped catalog failed its receipt hash")
                for record in _parse_catalog(
                    payload, package_id=package_id, catalog_id=catalog_id,
                    declared_packs=declared_packs,
                ):
                    if record["model"] in package_models:
                        raise ValueError(f"duplicate authorized ped model: {record['model']}")
                    package_models.add(record["model"])
                    pending.append(record)
            if any((record["package_id"], record["model"]) in owners for record in pending):
                raise ValueError("duplicate authorized ped model across packages")
            owners.update((record["package_id"], record["model"]) for record in pending)
            records.extend(pending)
        except (FileNotFoundError, ValueError, OSError, TypeError) as exc:
            warnings.append(f"{package_id or 'unknown'}: {exc}")
    records.sort(key=lambda row: (row["package_id"], row["catalog_id"], row["model"]))
    return records, warnings


def _normalize_document(document: object, records: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {
        "schema_version", "enabled", "replacement_chance", "max_added", "entries",
    }:
        raise ValueError(
            "ped population document must contain only schema_version, enabled, "
            "replacement_chance, max_added and entries"
        )
    if type(document.get("schema_version")) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"ped population schema_version must be {SCHEMA_VERSION}")
    enabled = document.get("enabled")
    if type(enabled) is not bool:
        raise ValueError("ped population enabled must be a boolean")
    chance = document.get("replacement_chance")
    if type(chance) not in (int, float) or not math.isfinite(float(chance)) or not 0 <= float(chance) <= 1:
        raise ValueError("ped population replacement_chance must be finite and between 0 and 1")
    max_added = document.get("max_added")
    if type(max_added) is not int or not 0 <= max_added <= MAX_ADDED:
        raise ValueError(f"ped population max_added must be an integer between 0 and {MAX_ADDED}")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        raise ValueError(f"ped population entries must contain at most {MAX_ENTRIES} entries")
    authorized = {(row["package_id"], row["model"]) for row in records}
    normalized_entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(entries, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"entries[{index}] must be an object")
        allowed = {"package_id", "model", "mode", "target_model"}
        if set(row) - allowed or not {"package_id", "model", "mode"} <= set(row):
            raise ValueError(f"entries[{index}] has unsupported or missing fields")
        package_id = _safe_identifier(row.get("package_id"), f"entries[{index}].package_id")
        model = _safe_model(row.get("model"), f"entries[{index}].model")
        key = (package_id, model)
        if key not in authorized:
            raise ValueError(f"entries[{index}] is not an enabled receipt-authorized ped model")
        if key in seen:
            raise ValueError(f"entries contains duplicate model selection: {package_id}/{model}")
        seen.add(key)
        mode = row.get("mode")
        if mode not in {"disabled", "add", "replace"}:
            raise ValueError(f"entries[{index}].mode must be disabled, add or replace")
        result: dict[str, str] = {"package_id": package_id, "model": model, "mode": mode}
        target = row.get("target_model")
        if mode == "replace":
            target_model = _safe_model(target, f"entries[{index}].target_model")
            if target_model not in _TARGET_SET:
                raise ValueError(f"entries[{index}].target_model is not a supported vanilla ambient target")
            result["target_model"] = target_model
        elif target is not None:
            raise ValueError(f"entries[{index}].target_model is valid only for replace mode")
        normalized_entries.append(result)
    normalized_entries.sort(key=lambda row: (row["package_id"], row["model"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": enabled,
        "replacement_chance": float(chance),
        "max_added": max_added,
        "entries": normalized_entries,
    }


def validate_document(game: str | Path, document: object) -> dict[str, Any]:
    """Validate a policy against the currently enabled receipt-authorized catalogs."""
    root = no_links(Path(game).expanduser())
    records, warnings = _discover_models(root)
    if warnings:
        raise ValueError("Ped catalog authorization is incomplete: " + "; ".join(warnings))
    return _normalize_document(document, records)


def inspect_population(game: str | Path) -> dict[str, Any]:
    """Read the policy plus available ped records without changing game state."""
    root = no_links(Path(game).expanduser())
    policy_path = _policy_path(root)
    warnings: list[str] = []
    raw: bytes
    try:
        raw = _read_bounded_bytes(policy_path, MAX_DOCUMENT_BYTES,
                                  "ped population document")
    except FileNotFoundError:
        document = _default_document()
        raw = _canonical_bytes(document)
    except ValueError as exc:
        document = _default_document()
        warnings.append(str(exc))
        # Do not read an over-limit document merely to make a diagnostic hash.
        raw = _canonical_bytes(document)
    else:
        try:
            document = strict_json(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            document = _default_document()
            warnings.append(f"Invalid ped population document: {exc}")
    records, discovery_warnings = _discover_models(root)
    warnings.extend(discovery_warnings)
    try:
        normalized = _normalize_document(document, records)
    except ValueError as exc:
        normalized = _default_document()
        warnings.append(str(exc))
    return {
        "document": normalized,
        "document_sha256": _sha256(raw),
        "models": records,
        "targets": list(SUPPORTED_VANILLA_TARGETS),
        "warnings": warnings,
    }


def save_population(
    game: str | Path, document: object, expected_document_sha256: str,
) -> dict[str, Any]:
    """Atomically persist a reviewed policy, refusing stale editor state."""
    if not isinstance(expected_document_sha256, str) or not _DIGEST.fullmatch(
        expected_document_sha256.lower()
    ):
        raise ValueError("expected_document_sha256 must be a SHA-256 digest")
    root = no_links(Path(game).expanduser())
    normalized = validate_document(root, document)
    policy_path = _policy_path(root)
    try:
        current = _read_bounded_bytes(policy_path, MAX_DOCUMENT_BYTES,
                                      "ped population document")
    except FileNotFoundError:
        current = _canonical_bytes(_default_document())
    if _sha256(current) != expected_document_sha256.lower():
        raise ValueError("Ped population document changed; reload before saving")
    parent = no_links(policy_path.parent)
    filesystem_path(parent).mkdir(parents=True, exist_ok=True)
    no_links(parent)
    payload = _canonical_bytes(normalized)
    temporary = no_links(parent / f".{policy_path.name}.{uuid.uuid4().hex}.tmp")
    created = False
    try:
        with filesystem_path(temporary).open("x", encoding="utf-8", newline="\n") as stream:
            created = True
            stream.write(payload.decode("utf-8"))
        # A normal concurrent editor must not be overwritten after its first
        # stale-state check.  os.replace still has the usual local-process
        # check/use window, but this closes the ordinary stage/write race.
        try:
            latest = _read_bounded_bytes(policy_path, MAX_DOCUMENT_BYTES,
                                         "ped population document")
        except FileNotFoundError:
            latest = _canonical_bytes(_default_document())
        if _sha256(latest) != expected_document_sha256.lower():
            raise ValueError("Ped population document changed; reload before saving")
        no_links(parent)
        no_links(policy_path)
        os.replace(filesystem_path(temporary), filesystem_path(policy_path))
    finally:
        if created:
            filesystem_path(temporary).unlink(missing_ok=True)
    return {
        "document": normalized,
        "document_sha256": _sha256(payload),
        "path": str(policy_path),
    }
