"""Reviewed traffic-list overrides; never edits models or grants package capabilities."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

from allin1.extensions import ExtensionRegistry
from allin1.release_paths import contained, filesystem_path, no_links, strict_json
from allin1.vehicle_catalog import VehicleCatalog, ROAD_TRAFFIC_CATEGORIES, vehicle_model_hash

MAX_BYTES = 1024 * 1024
MAX_ENTRIES = 512
POLICY_PATH = "scripts/.allin1/traffic-population.json"
_SHA = re.compile(r"[0-9a-f]{64}")


def _bytes(document):
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, limit=MAX_BYTES):
    path = filesystem_path(no_links(path))
    if path.stat().st_size > limit:
        raise ValueError("Population file exceeds its safety limit")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Population file exceeds its safety limit")
    return raw, strict_json(raw)


def _discover_models(game):
    models, warnings, hashes = [], [], set()
    for extension in ExtensionRegistry(game).inspect().get("extensions", []):
        if not extension.get("enabled") or "traffic.catalog" not in extension.get("capabilities", []):
            continue
        # Preserve both the author's per-item opt-in and the package setting.
        if extension.get("settings", {}).get("traffic_enabled") is not True:
            continue
        package_id = extension["id"]
        try:
            # Use the same verified receipt snapshot as the declaration/hash,
            # never reread a mutable receipt to broaden package ownership.
            packs = extension.get("dlc_packs")
            if (not isinstance(packs, list) or not packs or
                    any(not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value)
                        for value in packs) or len(set(packs)) != len(packs)):
                raise ValueError("Traffic package receipt has no valid declared DLC ownership")
            evidence = {row["path"].replace("\\", "/").casefold(): row["sha256"]
                        for row in extension.get("catalog_files", [])}
            pending = []
            for declaration in extension.get("gbay", {}).get("catalogs", []):
                if declaration.get("kind") != "vehicle":
                    continue
                relative = declaration["source"].replace("\\", "/")
                expected = evidence.get(relative.casefold())
                raw, document = _read(contained(game, relative), 4 * MAX_BYTES)
                if not isinstance(expected, str) or not _SHA.fullmatch(expected) or _hash(raw) != expected:
                    raise ValueError("Traffic catalog failed its receipt hash")
                catalog = VehicleCatalog.from_dict(document)
                if catalog.catalog_id != declaration["id"]:
                    raise ValueError("Traffic catalog ID differs from its declaration")
                catalog.validate_package_ownership(packs, allow_traffic=True)
                for row in catalog.vehicles:
                    if row.traffic.enabled and row.category in ROAD_TRAFFIC_CATEGORIES:
                        pending.append({"package_id": package_id, "model": row.model,
                                        "name": row.display_name, "category": row.category,
                                        "default_weight": row.traffic.weight})
            # Do not leave a half-admitted catalog/package after validation fails.
            candidate_hashes = [vehicle_model_hash(row["model"]) for row in pending]
            if len(set(candidate_hashes)) != len(candidate_hashes) or any(value in hashes for value in candidate_hashes):
                raise ValueError("Ambiguous duplicate traffic model ownership")
            if len(models) + len(pending) > MAX_ENTRIES:
                raise ValueError("Traffic catalog exceeds the selectable model limit")
            hashes.update(candidate_hashes)
            models.extend(pending)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f"{package_id}: {exc}")
    models.sort(key=lambda row: (row["package_id"], row["model"]))
    return models, warnings


def _default(models):
    return {"schema_version": 1, "enabled": True, "replacement_chance": 0.3,
            "entries": [{"package_id": row["package_id"], "model": row["model"],
                         "enabled": True, "weight": row["default_weight"]} for row in models]}


def _legacy_defaults(game, models):
    from allin1.config import tomllib
    document = _default(models)
    path = contained(game, "scripts/ALLIN1.toml")
    if path.is_file():
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("Runtime traffic configuration exceeds its safety limit")
        with filesystem_path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Runtime traffic configuration exceeds its safety limit")
        traffic = tomllib.loads(raw.decode("utf-8")).get("traffic", {})
        document["enabled"] = traffic.get("enabled", True)
        document["replacement_chance"] = traffic.get("replacement_chance", 0.3)
    return _normalize(document, models)


def _normalize(document, models):
    if not isinstance(document, dict) or set(document) != {"schema_version", "enabled", "replacement_chance", "entries"}:
        raise ValueError("Traffic policy contains missing or unsupported fields")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("Traffic policy schema_version must be 1")
    if type(document["enabled"]) is not bool:
        raise ValueError("Traffic policy enabled must be a boolean")
    chance = document["replacement_chance"]
    if type(chance) not in (int, float) or not math.isfinite(chance) or not 0 <= chance <= 1:
        raise ValueError("Traffic replacement_chance must be finite and between 0 and 1")
    rows = document["entries"]
    if not isinstance(rows, list) or len(rows) > MAX_ENTRIES:
        raise ValueError("Traffic entries exceeds its limit")
    allowed = {(row["package_id"], row["model"]) for row in models}
    seen, result = set(), []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"package_id", "model", "enabled", "weight"}:
            raise ValueError("Traffic selection contains missing or unsupported fields")
        if not isinstance(row["package_id"], str) or not isinstance(row["model"], str):
            raise ValueError("Traffic selection identifiers must be strings")
        key = (row["package_id"], row["model"])
        if key not in allowed or key in seen:
            raise ValueError("Traffic selection is duplicate or not an authorized opted-in road vehicle")
        if type(row["enabled"]) is not bool:
            raise ValueError("Traffic selection enabled must be a boolean")
        weight = row["weight"]
        if type(weight) not in (int, float) or not math.isfinite(weight) or not 0.1 <= weight <= 20:
            raise ValueError("Traffic selection weight must be finite and between 0.1 and 20")
        seen.add(key)
        result.append({**row, "weight": float(weight)})
    return {"schema_version": 1, "enabled": document["enabled"], "replacement_chance": float(chance),
            "entries": sorted(result, key=lambda row: (row["package_id"], row["model"]))}


def validate_document(game, document):
    models, warnings = _discover_models(no_links(Path(game)))
    if warnings:
        raise ValueError("Traffic catalog authorization failed: " + "; ".join(warnings))
    return _normalize(document, models)


def inspect_population(game):
    game = no_links(Path(game))
    models, warnings = _discover_models(game)
    path = contained(game, POLICY_PATH)
    document = _default(models)
    # Missing-file token is distinct from any on-disk document and independent
    # of the discovered list, so first-save review is deterministic.
    identity = _hash(b"ALLIN1 traffic policy absent")
    try:
        raw, loaded = _read(path)
        identity = _hash(raw)
        document = _normalize(loaded, models)
    except FileNotFoundError:
        try:
            document = _legacy_defaults(game, models)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            document = {**_default([]), "enabled": False}
            warnings.append("Could not import current traffic defaults: " + str(exc))
    except (OSError, ValueError) as exc:
        # Fail closed, without reading unbounded bytes from an oversized file.
        document = {**_default([]), "enabled": False}
        warnings.append(str(exc))
        identity = ""
        try:
            # Even malformed-file diagnostics must use a bounded read: a file
            # can grow or disappear between validation and this second read.
            with filesystem_path(no_links(path)).open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) <= MAX_BYTES:
                identity = _hash(raw)
        except (OSError, ValueError):
            pass
    return {"document": document, "document_sha256": identity, "models": models, "warnings": warnings}


def save_population(game, document, expected_document_sha256):
    game = no_links(Path(game))
    if not isinstance(expected_document_sha256, str) or not _SHA.fullmatch(expected_document_sha256):
        raise ValueError("A valid traffic document SHA-256 is required")
    normalized = validate_document(game, document)
    if inspect_population(game)["document_sha256"] != expected_document_sha256:
        raise ValueError("Traffic policy changed; reload before saving")
    path = contained(game, POLICY_PATH)
    filesystem_path(no_links(path.parent)).mkdir(parents=True, exist_ok=True)
    temporary = contained(path.parent, ".traffic-population." + uuid.uuid4().hex + ".tmp")
    payload = _bytes(normalized)
    created = False
    try:
        with filesystem_path(temporary).open("xb") as stream:
            created = True
            stream.write(payload)
        # Revalidate authorization and state immediately before committing.
        validate_document(game, normalized)
        if inspect_population(game)["document_sha256"] != expected_document_sha256:
            raise ValueError("Traffic policy changed while saving; reload")
        os.replace(filesystem_path(temporary), filesystem_path(no_links(path)))
    finally:
        if created:
            filesystem_path(no_links(temporary)).unlink(missing_ok=True)
    return {"document": normalized, "document_sha256": _hash(payload), "path": str(path)}
