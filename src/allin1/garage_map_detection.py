"""Verified discovery cache for official GTA map placement names.

The launcher performs archive inspection before GTA starts.  The managed
Story Mode client consumes only the small, checksummed cache written here; it
never walks Rockstar RPFs on the game thread.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from allin1.processes import run_hidden
from allin1.runtime_resources import resource_root


CACHE_SCHEMA_VERSION = 1
CACHE_PRODUCER = "allin1-launcher"
# Bump whenever the generator's accepted/emitted shape changes. This value is
# folded into the source identity instead of widening the strict game-side
# payload schema.
DETECTION_CONTRACT_REVISION = 3
CACHE_RELATIVE_PATH = PurePosixPath(
    "scripts/ALLIN1/Maps/runtime-detected.json"
)
REGISTRY_RELATIVE_PATH = PurePosixPath(
    "scripts/.allin1/extensions/registry.json"
)
OFFICIAL_CONTENT_ID = "allin1.online-content"
MAX_REGISTRY_BYTES = 4 * 1024 * 1024
MAX_DESCRIPTOR_BYTES = 1024 * 1024
MAX_INDEX_BYTES = 64 * 1024 * 1024
MAX_PROJECTS = 32
MAX_IPLS_PER_PROJECT = 64
MAX_MAPPINGS_TOTAL = 1024
MAX_INDEX_ENTRIES = 250_000
PATCHER_TIMEOUT_SECONDS = 240

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
_PACK_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_IPL_RE = re.compile(r"^[A-Za-z0-9_]{1,96}$")
_PORTABLE_PATH_RE = re.compile(r"^[A-Za-z0-9_@+./ -]{1,512}$")
_PACK_ARCHIVE_RE = re.compile(r"^dlc(?:[1-9][0-9]*)?\.rpf$", re.IGNORECASE)
_GENERIC_IPL_TOKENS = frozenset({
    "ba", "dlc", "hei", "int", "interior", "level", "map", "milo",
    "mp", "placement", "prop", "v", "ymap",
})


@dataclass(frozen=True)
class GarageMapDetectionResult:
    """Summary suitable for launcher progress and diagnostics."""

    cache_path: Path
    cache_hit: bool
    edition: str
    verified_projects: int
    unresolved_projects: int

    @property
    def summary(self) -> str:
        source = "cached" if self.cache_hit else "refreshed"
        return (
            f"Garage map names {source}: {self.verified_projects} verified, "
            f"{self.unresolved_projects} unresolved ({self.edition.title()})."
        )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    if normalized != normalized.strip():
        raise ValueError(f"{label} contains surrounding whitespace")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} contains an unsafe path segment")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ":" in parts[0]:
        raise ValueError(f"{label} must be GTA-root-relative")
    if not _PORTABLE_PATH_RE.fullmatch(path.as_posix()):
        raise ValueError(f"{label} contains unsupported characters")
    return path


def _safe_virtual_archive_path(value: object, label: str) -> str:
    """Validate RpfPatcher's bounded ``parent.rpf!child.rpf`` syntax."""
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ValueError(f"{label} must be a bounded virtual archive path")
    components = value.split("!")
    if any(not component for component in components):
        raise ValueError(f"{label} contains an empty virtual archive segment")
    normalized = [
        _safe_relative(component, label).as_posix()
        for component in components
    ]
    result = "!".join(normalized)
    if len(result) > 512:
        raise ValueError(f"{label} exceeds the path limit")
    return result


def _read_json(path: Path, maximum: int, label: str) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise ValueError(f"{label} has an invalid size ({size} bytes)")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc


def _edition(game: Path) -> tuple[str, Path]:
    enhanced = game / "GTA5_Enhanced.exe"
    legacy = game / "GTA5.exe"
    if enhanced.is_file():
        return "enhanced", enhanced
    if legacy.is_file():
        return "legacy", legacy
    raise ValueError(
        "The selected folder does not contain GTA5.exe or GTA5_Enhanced.exe"
    )


def _descriptor_ipls(descriptor: Mapping[str, Any]) -> tuple[str, ...]:
    raw: list[object] = []
    streaming = descriptor.get("streaming")
    if isinstance(streaming, Mapping):
        values = streaming.get("ipls", [])
        if isinstance(values, list):
            raw.extend(values)
    levels = descriptor.get("levels", [])
    if isinstance(levels, list):
        for level in levels:
            if not isinstance(level, Mapping):
                continue
            values = level.get("ipls", [])
            if isinstance(values, list):
                raw.extend(values)
    normalized: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, str) or not _IPL_RE.fullmatch(item):
            raise ValueError("Map descriptor contains an invalid IPL name")
        normalized.setdefault(item.casefold(), item)
    if len(normalized) > MAX_IPLS_PER_PROJECT:
        raise ValueError("Map descriptor exceeds the IPL discovery limit")
    return tuple(normalized[key] for key in sorted(normalized))


def _authorized_projects(game: Path, edition: str) -> list[dict[str, Any]]:
    registry_path = game / Path(*REGISTRY_RELATIVE_PATH.parts)
    registry = _read_json(registry_path, MAX_REGISTRY_BYTES, "extension registry")
    if not isinstance(registry, Mapping) or registry.get("schema_version") != 1:
        raise ValueError("The extension registry has an unsupported schema")
    extensions = registry.get("extensions")
    if not isinstance(extensions, list):
        raise ValueError("The extension registry has no extension list")
    extension = next((
        item for item in extensions
        if isinstance(item, Mapping)
        and item.get("id") == OFFICIAL_CONTENT_ID
    ), None)
    if extension is None or not extension.get("enabled"):
        raise ValueError("ALLIN1 Online Content maps are not enabled")
    records = extension.get("map_files")
    if not isinstance(records, list) or not records:
        raise ValueError("The Online Content registry has no authorized maps")
    if len(records) > MAX_PROJECTS:
        raise ValueError("The Online Content registry exceeds the map limit")

    projects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("The map registry contains an invalid record")
        relative = _safe_relative(record.get("path"), "map descriptor path")
        if tuple(part.casefold() for part in relative.parts[:2]) != (
            "scripts", "allin1",
        ):
            raise ValueError("Map descriptors must remain under scripts/ALLIN1")
        expected_hash = str(record.get("sha256", "")).casefold()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("A map descriptor lacks a valid registry hash")
        descriptor_path = game / Path(*relative.parts)
        raw = descriptor_path.read_bytes() if descriptor_path.is_file() else b""
        if not raw or len(raw) > MAX_DESCRIPTOR_BYTES:
            raise ValueError(f"Map descriptor is missing or oversized: {relative}")
        actual_hash = _sha256_bytes(raw)
        if actual_hash != expected_hash:
            raise ValueError(f"Map descriptor failed its registry hash: {relative}")
        try:
            descriptor = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Map descriptor is invalid JSON: {relative}") from exc
        if not isinstance(descriptor, Mapping) or descriptor.get("schema_version") != 1:
            raise ValueError(f"Map descriptor has an unsupported schema: {relative}")
        project_id = str(descriptor.get("id", "")).strip().lower()
        if not _ID_RE.fullmatch(project_id) or project_id in seen_ids:
            raise ValueError(f"Map descriptor has an invalid or duplicate id: {relative}")
        supported = descriptor.get("editions", [])
        if not isinstance(supported, list) or edition not in {
            str(item).strip().casefold() for item in supported
        }:
            continue
        streaming = descriptor.get("streaming")
        if not isinstance(streaming, Mapping):
            raise ValueError(f"Map descriptor has no streaming contract: {relative}")
        pack_name = str(streaming.get("pack_name", "")).strip().casefold()
        if not _PACK_RE.fullmatch(pack_name):
            raise ValueError(f"Map descriptor has an invalid pack name: {relative}")
        seen_ids.add(project_id)
        projects.append({
            "id": project_id,
            "descriptor_path": relative.as_posix(),
            "descriptor_sha256": actual_hash,
            "pack_name": pack_name,
            "ipls": _descriptor_ipls(descriptor),
        })
    return sorted(projects, key=lambda item: item["id"])


def _file_identity(path: Path, relative: str) -> dict[str, Any]:
    if not path.is_file():
        return {"path": relative, "exists": False, "size": 0, "mtime_ns": 0}
    stat = path.stat()
    return {
        "path": relative,
        "exists": True,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _pack_root_archives(pack_root: Path) -> dict[str, Path]:
    """Return one bounded root archive per case-insensitive sibling name."""
    if not pack_root.is_dir():
        return {}
    archives: dict[str, Path] = {}
    for item in pack_root.iterdir():
        if not item.is_file() or not _PACK_ARCHIVE_RE.fullmatch(item.name):
            continue
        key = item.name.casefold()
        if key in archives:
            raise ValueError(
                "DLC pack contains duplicate case-insensitive root archives: "
                f"{pack_root / archives[key].name} and {item}"
            )
        archives[key] = item
    return archives


def _effective_pack_archives(game: Path, pack: str) -> list[Path]:
    """Resolve OpenRPF's overlay independently for each root RPF sibling.

    A partial ``mods/update`` pack commonly replaces only ``dlc.rpf`` while
    leaving Enhanced split siblings such as ``dlc1.rpf`` in the stock tree.
    Treating the whole mod pack directory as a replacement would silently omit
    those stock siblings.  Build the effective union by archive name instead:
    a mod archive shadows only the stock archive with that same name.
    """
    stock = _pack_root_archives(
        game / "update" / "x64" / "dlcpacks" / pack,
    )
    overlay = _pack_root_archives(
        game / "mods" / "update" / "x64" / "dlcpacks" / pack,
    )
    effective = {
        name: overlay.get(name, stock.get(name))
        for name in stock.keys() | overlay.keys()
    }
    return sorted(
        (path for path in effective.values() if path is not None),
        key=lambda item: (
            item.name.casefold() != "dlc.rpf", item.name.casefold(),
        ),
    )[:8]


def _source_identity(
    game: Path, edition: str, executable: Path, projects: list[dict[str, Any]],
    patcher: Path,
) -> tuple[str, dict[str, dict[str, Any]]]:
    packs: dict[str, dict[str, Any]] = {}
    for pack in sorted({item["pack_name"] for item in projects}):
        archives = _effective_pack_archives(game, pack)
        identities = [
            _file_identity(
                archive,
                archive.relative_to(game).as_posix(),
            )
            for archive in archives
        ]
        primary = (
            identities[0]["path"] if identities else
            f"update/x64/dlcpacks/{pack}/dlc.rpf"
        )
        packs[pack] = {
            "path": primary,
            "exists": bool(identities),
            "size": sum(item["size"] for item in identities),
            "mtime_ns": max(
                (item["mtime_ns"] for item in identities), default=0,
            ),
            "archives": identities,
        }
    identity = {
        "schema_version": 1,
        "detector_contract_revision": DETECTION_CONTRACT_REVISION,
        "edition": edition,
        "game_executable": _file_identity(executable, executable.name),
        "patcher": _file_identity(patcher, "tools/RpfPatcher/RpfPatcher.exe"),
        "descriptors": [{
            "id": item["id"],
            "sha256": item["descriptor_sha256"],
            "pack_name": item["pack_name"],
        } for item in projects],
        "packs": [packs[key] for key in sorted(packs)],
    }
    encoded = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded), packs


def _valid_cached_payload(
    destination: Path, edition: str, fingerprint: str,
    expected_projects: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        if (
            not destination.is_file()
            or destination.stat().st_size > MAX_DESCRIPTOR_BYTES
        ):
            return None
        envelope = json.loads(destination.read_text(encoding="utf-8"))
        payload_json = envelope["payload_json"]
        if (
            set(envelope) != {
                "schema_version", "producer", "payload_sha256", "payload_json",
            }
            or
            envelope.get("schema_version") != CACHE_SCHEMA_VERSION
            or envelope.get("producer") != CACHE_PRODUCER
            or not isinstance(payload_json, str)
            or _sha256_bytes(payload_json.encode("utf-8"))
                != str(envelope.get("payload_sha256", "")).casefold()
        ):
            return None
        payload = json.loads(payload_json)
        if (
            not isinstance(payload, Mapping)
            or set(payload) != {
                "schema_version", "edition", "source_identity_fingerprint",
                "projects",
            }
            or
            payload.get("schema_version") != CACHE_SCHEMA_VERSION
            or payload.get("edition") != edition
            or payload.get("source_identity_fingerprint") != fingerprint
            or not isinstance(payload.get("projects"), list)
        ):
            return None
        if not _cached_projects_match(payload["projects"], expected_projects):
            return None
        return payload
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _cached_projects_match(
    values: list[Any], expected_projects: list[dict[str, Any]],
) -> bool:
    """Mirror the strict game-side project/mapping shape before a cache hit."""
    if len(values) != len(expected_projects) or len(values) > MAX_PROJECTS:
        return False
    expected = {item["id"]: item for item in expected_projects}
    seen: set[str] = set()
    total_mappings = 0
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {
            "id", "descriptor_sha256", "pack_name", "status", "source",
            "ipl_mappings",
        }:
            return False
        project_id = value.get("id")
        if not isinstance(project_id, str) or project_id in seen:
            return False
        current = expected.get(project_id)
        if current is None:
            return False
        seen.add(project_id)
        if (
            value.get("descriptor_sha256") != current["descriptor_sha256"]
            or value.get("pack_name") != current["pack_name"]
            or value.get("status") not in {
                "verified", "unresolved", "not_applicable",
            }
        ):
            return False
        source = value.get("source")
        if not isinstance(source, Mapping) or set(source) != {
            "archive_path", "size", "mtime_ns",
        }:
            return False
        try:
            _safe_relative(source.get("archive_path"), "cached source path")
        except ValueError:
            return False
        if (
            type(source.get("size")) is not int
            or type(source.get("mtime_ns")) is not int
            or source["size"] < 0
            or source["size"] > 64 * 1024 * 1024 * 1024
            or source["mtime_ns"] < 0
        ):
            return False
        mappings = value.get("ipl_mappings")
        if not isinstance(mappings, list) or len(mappings) > MAX_IPLS_PER_PROJECT:
            return False
        total_mappings += len(mappings)
        if total_mappings > MAX_MAPPINGS_TOTAL:
            return False
        requested_names = {name.casefold() for name in current["ipls"]}
        mapped_requested: set[str] = set()
        resolved_names: set[str] = set()
        for mapping in mappings:
            if not isinstance(mapping, Mapping) or set(mapping) not in ({
                "requested", "resolved", "match", "archive_path", "entry_path",
            }, {
                "requested", "resolved", "match", "archive_path", "entry_path",
                "source_rpf",
            }):
                return False
            requested = mapping.get("requested")
            resolved = mapping.get("resolved")
            match = mapping.get("match")
            if (
                not isinstance(requested, str) or not _IPL_RE.fullmatch(requested)
                or not isinstance(resolved, str) or not _IPL_RE.fullmatch(resolved)
                or match not in {"exact", "semantic_unique"}
                or requested.casefold() not in requested_names
                or requested.casefold() in mapped_requested
                or resolved.casefold() in resolved_names
                or (match == "exact" and requested.casefold() != resolved.casefold())
            ):
                return False
            mapped_requested.add(requested.casefold())
            resolved_names.add(resolved.casefold())
            try:
                _safe_virtual_archive_path(
                    mapping["archive_path"], "cached mapping archive_path",
                )
                _safe_relative(
                    mapping["entry_path"], "cached mapping entry_path",
                )
                if "source_rpf" in mapping:
                    _safe_relative(
                        mapping["source_rpf"], "cached mapping source_rpf",
                    )
            except ValueError:
                return False
        status = value["status"]
        if status == "verified" and (
            not requested_names or mapped_requested != requested_names
        ):
            return False
        if status == "not_applicable" and (requested_names or mappings):
            return False
    return seen == set(expected)


def _safe_index_path(value: object, label: str) -> str:
    path = _safe_relative(value, label)
    if len(path.as_posix()) > 512:
        raise ValueError(f"{label} exceeds the path limit")
    return path.as_posix()


def _index_pack(
    game: Path, source: Path, patcher: Path,
    runner: Callable[..., Any], temporary_root: Path, source_relative: str,
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    output = temporary_root / f"{source.parent.name}-{source.stem}.index.json"
    completed = runner(
        [patcher, "index-json", game, source, output],
        capture_output=True,
        text=True,
        timeout=PATCHER_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"RPF index failed for {source.parent.name}: {detail[:500]}")
    index = _read_json(output, MAX_INDEX_BYTES, "RPF index")
    if not isinstance(index, Mapping) or index.get("schema_version") != 1:
        raise ValueError("RPF index has an unsupported schema")
    raw_entries = index.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) > MAX_INDEX_ENTRIES:
        raise ValueError("RPF index has an invalid entry count")
    by_stem: dict[str, list[dict[str, str]]] = defaultdict(list)
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            continue
        name = str(entry.get("name", ""))
        if not name.casefold().endswith(".ymap"):
            continue
        stem = name[:-5]
        if not _IPL_RE.fullmatch(stem):
            continue
        raw_archive_path = entry.get("archive_path", "")
        archive_path = (
            source_relative
            if raw_archive_path == ""
            else _safe_virtual_archive_path(
                raw_archive_path, "RPF archive path",
            )
        )
        entry_path = _safe_index_path(entry.get("path"), "RPF entry path")
        by_stem[stem.casefold()].append({
            "resolved": stem,
            "archive_path": archive_path,
            "entry_path": entry_path,
            "source_rpf": source_relative,
        })
    for values in by_stem.values():
        values.sort(key=lambda item: (
            len(item["archive_path"]), item["archive_path"].casefold(),
            item["entry_path"].casefold(), item["source_rpf"].casefold(),
        ))
    return by_stem, sorted(
        (values[0]["resolved"] for values in by_stem.values()),
        key=str.casefold,
    )


def _semantic_anchors(name: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z]+\d*|\d+", name.casefold())
    anchors = {
        token for token in tokens
        if len(token) >= 3 and token not in _GENERIC_IPL_TOKENS
    }
    return tuple(sorted(anchors))


def _match_ipl(
    requested: str, by_stem: Mapping[str, list[dict[str, str]]],
    stems: list[str],
) -> dict[str, str] | None:
    exact = by_stem.get(requested.casefold())
    if exact and len(exact) == 1:
        return {"requested": requested, "match": "exact", **exact[0]}
    if exact:
        # Multiple exact entries are not interchangeable evidence.  Choosing
        # the first one would make the result depend on archive ordering and
        # could bind a garage to the wrong placement after an overlay change.
        return None
    anchors = _semantic_anchors(requested)
    if len(anchors) < 3:
        return None
    candidates = []
    for stem in stems:
        lowered = stem.casefold()
        candidate_tokens = set(re.findall(r"[a-z]+\d*|\d+", lowered))
        if not all(anchor in candidate_tokens for anchor in anchors):
            continue
        score = difflib.SequenceMatcher(None, requested.casefold(), lowered).ratio()
        if score >= 0.72:
            candidates.append(stem)
    unique = {item.casefold(): item for item in candidates}
    if len(unique) != 1:
        return None
    stem = next(iter(unique.values()))
    record = by_stem[stem.casefold()][0]
    return {"requested": requested, "match": "semantic_unique", **record}


def _write_envelope(payload: dict[str, Any], destination: Path) -> None:
    payload_json = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    envelope = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "producer": CACHE_PRODUCER,
        "payload_sha256": _sha256_bytes(payload_json.encode("utf-8")),
        "payload_json": payload_json,
    }
    encoded = (
        json.dumps(envelope, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_DESCRIPTOR_BYTES:
        raise ValueError("Garage map detection cache exceeds the 1 MiB limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, destination)


def refresh_garage_map_detection(
    gta_path: str | Path, *, patcher: str | Path | None = None,
    runner: Callable[..., Any] = run_hidden, force: bool = False,
) -> GarageMapDetectionResult:
    """Verify official descriptor IPLs and publish a game-thread-safe cache."""
    game = Path(gta_path).expanduser().resolve()
    edition, executable = _edition(game)
    projects = _authorized_projects(game, edition)
    selected_patcher = Path(patcher).resolve() if patcher is not None else (
        resource_root() / "tools" / "RpfPatcher" /
        "RpfPatcher.exe"
    )
    fingerprint, pack_identities = _source_identity(
        game, edition, executable, projects, selected_patcher,
    )
    destination = game / Path(*CACHE_RELATIVE_PATH.parts)
    cached = None if force else _valid_cached_payload(
        destination, edition, fingerprint, projects,
    )
    if cached is not None:
        verified = sum(
            item.get("status") in {"verified", "not_applicable"}
            for item in cached["projects"] if isinstance(item, Mapping)
        )
        return GarageMapDetectionResult(
            destination, True, edition, verified,
            len(cached["projects"]) - verified,
        )

    needs_index = any(item["ipls"] for item in projects)
    if needs_index and not selected_patcher.is_file():
        raise FileNotFoundError(
            f"Garage map detection requires RpfPatcher.exe: {selected_patcher}"
        )

    indexes: dict[str, tuple[dict[str, list[dict[str, str]]], list[str]]] = {}
    with tempfile.TemporaryDirectory(prefix="allin1-map-detection-") as temporary:
        temporary_root = Path(temporary)
        for pack in sorted({
            item["pack_name"] for item in projects if item["ipls"]
        }):
            pack_identity = pack_identities[pack]
            archives = pack_identity.get("archives", [])
            if not archives:
                continue
            combined: dict[str, list[dict[str, str]]] = defaultdict(list)
            for archive in archives:
                relative = archive["path"]
                source = game / Path(*PurePosixPath(relative).parts)
                indexed, _stems = _index_pack(
                    game, source, selected_patcher, runner, temporary_root,
                    relative,
                )
                for stem, records in indexed.items():
                    combined[stem].extend(records)
            for records in combined.values():
                records.sort(key=lambda item: (
                    item["source_rpf"].casefold(),
                    len(item["archive_path"]), item["archive_path"].casefold(),
                    item["entry_path"].casefold(),
                ))
            indexes[pack] = (
                dict(combined),
                sorted(
                    (records[0]["resolved"] for records in combined.values()),
                    key=str.casefold,
                ),
            )

    detected: list[dict[str, Any]] = []
    verified = 0
    for project in projects:
        pack = project["pack_name"]
        identity = pack_identities[pack]
        source = {
            "archive_path": identity["path"],
            "size": identity["size"],
            "mtime_ns": identity["mtime_ns"],
        }
        mappings: list[dict[str, str]] = []
        missing: list[str] = []
        if not project["ipls"]:
            status = "not_applicable"
        elif pack not in indexes:
            status = "unresolved"
            missing.extend(project["ipls"])
        else:
            by_stem, stems = indexes[pack]
            for requested in project["ipls"]:
                match = _match_ipl(requested, by_stem, stems)
                if match is None:
                    missing.append(requested)
                else:
                    mappings.append(match)
            resolved = [item["resolved"].casefold() for item in mappings]
            if len(resolved) != len(set(resolved)):
                # Two requested names resolving to one native placement is not
                # a one-to-one contract. Retain the bundled descriptor instead
                # of publishing an apparently verified but unusable project.
                mappings = []
                missing = list(project["ipls"])
            status = "verified" if not missing else "unresolved"
        if status in {"verified", "not_applicable"}:
            verified += 1
        detected.append({
            "id": project["id"],
            "descriptor_sha256": project["descriptor_sha256"],
            "pack_name": pack,
            "status": status,
            "source": source,
            "ipl_mappings": mappings,
        })

    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "edition": edition,
        "source_identity_fingerprint": fingerprint,
        "projects": detected,
    }
    if not _cached_projects_match(detected, projects):
        raise RuntimeError(
            "Garage map detector produced a cache outside the runtime contract"
        )
    _write_envelope(payload, destination)
    return GarageMapDetectionResult(
        destination, False, edition, verified, len(detected) - verified,
    )


__all__ = [
    "CACHE_RELATIVE_PATH",
    "GarageMapDetectionResult",
    "refresh_garage_map_detection",
]
