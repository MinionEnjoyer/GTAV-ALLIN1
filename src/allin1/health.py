"""Pre-launch installation health and conflict checks."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from allin1.config import Config
from allin1.versioning import read_installed_version


QUARANTINED_RPF_PACKS = {
    "allin1_smoke": (
        "This experimental pack caused repeatable Story Mode startup hangs. "
        "Run Install / Repair to remove it before launching."
    ),
}
COLORED_SMOKE_PACK_ID = "allin1_smoke"
COLORED_SMOKE_CANARY_MARKER = "ALLIN1_colored_smoke_weapons.json"
PERFORMANCE_ISOLATION_ROOT = (
    Path("allin1_backups") / "PerformanceIsolation"
)
PERFORMANCE_ISOLATION_POINTER = "active-session.json"
PERFORMANCE_ISOLATION_INACTIVE_STATUSES = frozenset({
    "completed", "inactive", "restored",
})
SHVDN_REQUIRED_BINARIES = (
    "ScriptHookVDotNet.asi",
    "ScriptHookVDotNet3.dll",
    "MinHook.x64.dll",
)

# This is deliberately a closed allowlist rather than a projection of the
# general map generator. A future map asset or property must not silently
# inherit permission to register files at startup.
_DAVIS_STARTUP_IPL_CANARY_ID = "davis-enhanced-isolated-startup-ipl-v3"
_DAVIS_STARTUP_IPL_RUNTIME_CONTRACT = "allin1-isolated-startup-ipl-v1"
_DAVIS_STARTUP_IPL_NAME = (
    "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"
)
_DAVIS_STARTUP_IPL_CHANGESET = "ALLIN1_MAPS_AUTOGEN"
_DAVIS_STARTUP_IPL_REFERENCES = (
    "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/"
    "dlc_int_01_tr.rpf",
    "dlc_allin1_maps:/%PLATFORM%/levels/gta5/interiors/"
    "int_placement_tr.rpf",
    "dlc_allin1_maps:/common/data/allin1/"
    "mptuner_davis_interiorProxies.meta",
)
_DAVIS_STARTUP_IPL_PROXY_PATH = (
    "common/data/allin1/mptuner_davis_interiorProxies.meta"
)
_DAVIS_STARTUP_IPL_RECEIPT_FIELDS = frozenset({
    "schema", "status", "canary_id", "package_id", "pack_name", "edition",
    "layout", "runtime_contract", "archive_registration", "activation",
    "archive_bytes", "archive_sha256", "asset_count",
    "startup_rpf_enable_count", "startup_file_enable_count",
    "property_scope", "properties", "ipls", "declared_changesets",
    "declared_groups", "groups", "custom_property_groups",
    "group_map_binding", "source_archives", "sources", "proxy_filters",
})

# Phase A deliberately proves only that GTA can boot with a tiny metadata-only
# pack which names Rockstar's already-registered MPTUNER_MAP_UPDATE changeset.
# Nothing in this contract authorizes executing that changeset, requesting an
# IPL, installing a native host, or changing gameconfig.  Keep this allowlist
# independent from the general map generator so a later generator feature
# cannot silently broaden launch permission.
_STOCK_MPTUNER_BRIDGE_PACK = "allin1_mptuner_bridge"
_STOCK_MPTUNER_BRIDGE_DEVICE = "dlc_allin1_mptuner_bridge"
_STOCK_MPTUNER_BRIDGE_MARKER = "allin1_mptuner_bridge.active"
_STOCK_MPTUNER_BRIDGE_RECEIPT = "allin1_mptuner_bridge.runtime.json"
_STOCK_MPTUNER_BRIDGE_CANARY_ID = (
    "davis-enhanced-stock-reference-boot-v4"
)
_STOCK_MPTUNER_BRIDGE_LAYOUT = "stock-reference-v1-metadata-only"
_STOCK_MPTUNER_BRIDGE_CONTRACT = "allin1-stock-mptuner-davis-boot-v1"
_STOCK_MPTUNER_BRIDGE_PHASE = "phase-a-boot-only"
_STOCK_MPTUNER_BRIDGE_BASE_CHANGESET = (
    "ALLIN1_MPTUNER_BRIDGE_AUTOGEN"
)
_STOCK_MPTUNER_BRIDGE_GROUP = "ALLIN1_STOCK_MPTUNER_DAVIS_V1"
_STOCK_MPTUNER_CHANGESET = "MPTUNER_MAP_UPDATE"
_STOCK_MPTUNER_BRIDGE_MARKER_PREAMBLE = (
    "ALLIN1 stock mptuner Phase-A metadata bridge; activation disabled."
)
_STOCK_MPHEIST_GRAPESEED_BRIDGE_PACK = (
    "allin1_mpheist_grapeseed_bridge"
)
_STOCK_MPTUNER_BRIDGE_MARKER_FIELDS = frozenset({
    "canary_id", "schema", "status", "phase", "layout",
    "runtime_contract", "archive_registration", "activation",
    "asset_count", "data_file_count", "startup_changeset",
    "dormant_group_count", "declared_groups", "stock_changesets",
    "native_group_execution_enabled", "runtime_ipl_requests_enabled",
    "gameconfig_changed", "native_host_installed", "receipt",
    "archive_bytes", "archive_sha256",
})
_STOCK_MPTUNER_BRIDGE_RECEIPT_FIELDS = frozenset({
    "schema", "canary_id", "status", "phase", "package_id",
    "pack_name", "device_name", "edition", "layout",
    "runtime_contract", "archive_registration", "activation",
    "asset_count", "data_file_count", "startup_changeset",
    "dormant_group_count", "declared_groups", "stock_changesets",
    "groups", "native_group_execution_enabled",
    "runtime_ipl_requests_enabled", "gameconfig_changed",
    "native_host_installed", "archive_bytes", "archive_sha256",
    "source_attestation",
})
_STOCK_MPTUNER_SOURCE_FIELDS = frozenset({
    "pack", "archive", "source", "path", "size", "mtime_ns",
    "archive_sha256", "content_xml_bytes", "content_xml_sha256",
    "setup2_xml_bytes", "setup2_xml_sha256", "device_name",
    "device_name_sha256", "setup_order", "stock_startup_group",
    "stock_startup_changeset", "stock_startup_changeset_sha256",
    "stock_proxy", "stock_map_group", "stock_map_group_changesets",
    "changeset_name", "changeset_sha256", "official_semantics",
})
_STOCK_MPTUNER_MAP_FILES = (
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/interiors/dlc_int_01_tr.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/interiors/dlc_int_02_tr.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/interiors/dlc_int_04_tr.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/interiors/int_placement_tr.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "dt1_17_tuner_additions.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "id2_18_tuner_additions.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "sc1_02_tuner_additions.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "sc1_28_tuner_additions.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "ss1_05_tuner_additions.rpf",
    "dlc_mpTuner:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "tuner_additions_metadata.rpf",
)


def _is_sha256_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _is_exact_int(value: object, expected: int) -> bool:
    return type(value) is int and value == expected


def _is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _valid_davis_startup_ipl_provenance(payload: dict) -> bool:
    archives = payload.get("source_archives")
    if not isinstance(archives, list) or len(archives) != 1:
        return False
    source_archive = archives[0]
    if not isinstance(source_archive, dict) or set(source_archive) != {
        "pack", "archive", "source", "path", "size", "mtime_ns", "sha256",
    }:
        return False
    if not (
        source_archive.get("pack") == "mptuner"
        and source_archive.get("archive") == "dlc.rpf"
        and source_archive.get("source") == "stock"
        and source_archive.get("path") ==
            "update/x64/dlcpacks/mptuner/dlc.rpf"
        and _is_positive_int(source_archive.get("size"))
        and _is_positive_int(source_archive.get("mtime_ns"))
        and _is_sha256_text(source_archive.get("sha256"))
    ):
        return False

    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 3:
        return False
    source_paths = (
        "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
        "x64/levels/gta5/interiors/int_placement_tr.rpf",
        "common/data/interiorProxies.meta",
    )
    destination_paths = (
        "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
        "x64/levels/gta5/interiors/int_placement_tr.rpf",
        _DAVIS_STARTUP_IPL_PROXY_PATH,
    )
    base_fields = {
        "source_pack", "source_archive", "source_path", "destination_path",
        "source_asset_bytes", "source_asset_sha256",
    }
    for index, source in enumerate(sources):
        expected_fields = (
            base_fields
            if index < 2
            else base_fields | {"proxy_names", "proxy_start_from"}
        )
        if not isinstance(source, dict) or set(source) != expected_fields:
            return False
        if not (
            source.get("source_pack") == "mptuner"
            and source.get("source_archive") == "dlc.rpf"
            and source.get("source_path") == source_paths[index]
            and source.get("destination_path") == destination_paths[index]
            and _is_positive_int(source.get("source_asset_bytes"))
            and _is_sha256_text(source.get("source_asset_sha256"))
        ):
            return False
    return (
        sources[2].get("proxy_names") == [_DAVIS_STARTUP_IPL_NAME]
        and _is_exact_int(sources[2].get("proxy_start_from"), 1117)
    )


def _valid_davis_startup_ipl_receipt(
    payload: object,
    *,
    edition: str,
    archive_bytes: int,
    archive_sha256: str,
) -> bool:
    """Recognize only the audited three-file Davis startup/IPL receipt."""
    if (
        not isinstance(payload, dict)
        or set(payload) != _DAVIS_STARTUP_IPL_RECEIPT_FIELDS
        or not _valid_davis_startup_ipl_provenance(payload)
    ):
        return False
    references = list(_DAVIS_STARTUP_IPL_REFERENCES)
    proxy_filters = payload.get("proxy_filters")
    if (
        not isinstance(proxy_filters, list)
        or len(proxy_filters) != 1
        or not isinstance(proxy_filters[0], dict)
        or set(proxy_filters[0]) != {
            "destination_path", "proxy_names", "start_from", "entry_count",
        }
        or proxy_filters[0].get("destination_path") !=
            _DAVIS_STARTUP_IPL_PROXY_PATH
        or proxy_filters[0].get("proxy_names") != [_DAVIS_STARTUP_IPL_NAME]
        or not _is_exact_int(proxy_filters[0].get("start_from"), 1117)
        or not _is_exact_int(proxy_filters[0].get("entry_count"), 1)
    ):
        return False
    return (
        _is_exact_int(payload.get("schema"), 3)
        and payload.get("status") == "verified"
        and payload.get("canary_id") == _DAVIS_STARTUP_IPL_CANARY_ID
        and payload.get("package_id") == "allin1.online-content"
        and payload.get("pack_name") == "allin1_maps"
        and payload.get("edition") == edition == "enhanced"
        and payload.get("layout") ==
            "pruned-local-v3-startup-registered-ipl"
        and payload.get("runtime_contract") ==
            _DAVIS_STARTUP_IPL_RUNTIME_CONTRACT
        and payload.get("archive_registration") == "startup"
        and payload.get("activation") ==
            "startup-file-registration-plus-request-ipl"
        and _is_exact_int(payload.get("archive_bytes"), archive_bytes)
        and payload.get("archive_sha256") == archive_sha256
        and _is_exact_int(payload.get("asset_count"), 3)
        and _is_exact_int(payload.get("startup_rpf_enable_count"), 2)
        and _is_exact_int(payload.get("startup_file_enable_count"), 3)
        and payload.get("property_scope") == "davis"
        and payload.get("properties") == ["davis"]
        and payload.get("ipls") == [_DAVIS_STARTUP_IPL_NAME]
        and payload.get("declared_changesets") == [
            _DAVIS_STARTUP_IPL_CHANGESET
        ]
        and payload.get("declared_groups") == ["GROUP_STARTUP"]
        and payload.get("groups") == [{
            "group": "GROUP_STARTUP",
            "changesets": [_DAVIS_STARTUP_IPL_CHANGESET],
            "references": references,
        }]
        and payload.get("custom_property_groups") == []
        and payload.get("group_map_binding") is False
    )


@dataclass(frozen=True)
class HealthIssue:
    code: str
    severity: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class HealthReport:
    edition: str
    installed_version: str | None
    issues: tuple[HealthIssue, ...]

    @property
    def launch_safe(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict:
        return {"edition": self.edition, "installed_version": self.installed_version,
                "launch_safe": self.launch_safe,
                "issues": [asdict(issue) for issue in self.issues]}


@dataclass(frozen=True)
class BinaryInspection:
    valid: bool
    reason: str


def inspect_windows_binary(
    path: Path, *, minimum_size: int = 4096,
    allowed_machines: tuple[int, ...] = (0x8664,),
) -> BinaryInspection:
    """Perform a cheap structural PE check without loading third-party code."""
    if not path.is_file():
        return BinaryInspection(False, "missing")
    try:
        size = path.stat().st_size
        if size < minimum_size:
            return BinaryInspection(False, f"too small ({size} bytes)")
        with path.open("rb") as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b"MZ":
                return BinaryInspection(False, "missing DOS/PE signature")
            pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
            if pe_offset < 64 or pe_offset + 6 > size:
                return BinaryInspection(False, "invalid PE header offset")
            stream.seek(pe_offset)
            pe_header = stream.read(6)
            if len(pe_header) != 6 or pe_header[:4] != b"PE\0\0":
                return BinaryInspection(False, "missing PE signature")
            machine = struct.unpack_from("<H", pe_header, 4)[0]
            if machine not in allowed_machines:
                return BinaryInspection(False, f"wrong architecture (0x{machine:04X})")
    except OSError as exc:
        return BinaryInspection(False, f"unreadable ({exc})")
    architecture = "x64" if allowed_machines == (0x8664,) else "compatible"
    return BinaryInspection(True, f"validated {architecture} PE file")


def is_shvdn_runtime_ready(gta_path: Path) -> bool:
    """Return whether the complete SHVDN runtime required by ALLIN1 is valid."""
    return all(
        inspect_windows_binary(gta_path / name).valid
        for name in SHVDN_REQUIRED_BINARIES
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_strict_key_value_marker(
    path: Path, *, fields: frozenset[str], maximum_bytes: int = 16 * 1024,
    preamble: str | None = None,
) -> tuple[dict[str, str] | None, str]:
    """Read a small marker without accepting duplicate or surprise keys."""
    try:
        if path.is_symlink() or not path.is_file():
            return None, "marker is not a regular file"
        stat = path.stat()
        if stat.st_size <= 0 or stat.st_size > maximum_bytes:
            return None, "marker size is outside the bounded contract"
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"marker is unreadable ({exc})"

    values: dict[str, str] = {}
    lines = text.splitlines()
    if preamble is not None:
        if not lines or lines[0].strip() != preamble:
            return None, "marker preamble does not match the fixed contract"
        lines = lines[1:]
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            return None, "marker contains a malformed line"
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in fields:
            return None, f"marker contains unknown field {key!r}"
        if key in values:
            return None, f"marker repeats field {key!r}"
        if not value:
            return None, f"marker field {key!r} is empty"
        values[key] = value
    if set(values) != fields:
        missing = sorted(fields - set(values))
        return None, "marker is missing fields: " + ", ".join(missing)
    return values, "verified"


def _read_bounded_json_object(
    path: Path, *, maximum_bytes: int = 64 * 1024,
) -> tuple[dict | None, str]:
    """Read a small JSON receipt while rejecting duplicate object keys."""
    try:
        if path.is_symlink() or not path.is_file():
            return None, "receipt is not a regular file"
        size = path.stat().st_size
        if size <= 0 or size > maximum_bytes:
            return None, "receipt size is outside the bounded contract"
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"receipt is unreadable ({exc})"

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    try:
        payload = json.loads(text, object_pairs_hook=reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"receipt is malformed ({exc})"
    if not isinstance(payload, dict):
        return None, "receipt is not a JSON object"
    return payload, "verified"


def _stock_mptuner_source_attestation_is_valid(
    payload: object, gta_path: Path,
) -> bool:
    if (
        not isinstance(payload, dict)
        or set(payload) != _STOCK_MPTUNER_SOURCE_FIELDS
    ):
        return False
    semantics = payload.get("official_semantics")
    if not isinstance(semantics, dict) or semantics != {
        "associated_maps": ["MO_JIM_L11"],
        "files_to_invalidate": [],
        "files_to_disable": [],
        "files_to_enable": list(_STOCK_MPTUNER_MAP_FILES),
        "requires_loading_screen": True,
        "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
        "use_cache_loader": True,
    }:
        return False
    expected_device_hash = hashlib.sha256(
        b"dlc_mpTuner"
    ).hexdigest()
    if not (
        payload.get("pack") == "mptuner"
        and payload.get("archive") == "dlc.rpf"
        and payload.get("source") in {"stock", "mods"}
        and _is_positive_int(payload.get("size"))
        and _is_positive_int(payload.get("mtime_ns"))
        and _is_sha256_text(payload.get("archive_sha256"))
        and _is_positive_int(payload.get("content_xml_bytes"))
        and _is_sha256_text(payload.get("content_xml_sha256"))
        and _is_positive_int(payload.get("setup2_xml_bytes"))
        and _is_sha256_text(payload.get("setup2_xml_sha256"))
        and payload.get("device_name") == "dlc_mpTuner"
        and _is_sha256_text(payload.get("device_name_sha256"))
        and hmac.compare_digest(
            str(payload.get("device_name_sha256")).casefold(),
            expected_device_hash.casefold(),
        )
        and type(payload.get("setup_order")) is int
        and 0 <= payload["setup_order"] < 72
        and payload.get("stock_startup_group") == "GROUP_STARTUP"
        and payload.get("stock_startup_changeset") == "MPTUNER_AUTOGEN"
        and _is_sha256_text(
            payload.get("stock_startup_changeset_sha256")
        )
        and payload.get("stock_proxy") ==
            "dlc_mpTuner:/common/data/interiorProxies.meta"
        and payload.get("stock_map_group") == "GROUP_MAP"
        and payload.get("stock_map_group_changesets") == [
            "MPTUNER_MAP_UPDATE", "MPTUNER_MAP_UPDATE_NAVMESH_ONLY",
        ]
        and payload.get("changeset_name") == _STOCK_MPTUNER_CHANGESET
        and _is_sha256_text(payload.get("changeset_sha256"))
    ):
        return False

    stock = gta_path / "update/x64/dlcpacks/mptuner/dlc.rpf"
    override = gta_path / "mods/update/x64/dlcpacks/mptuner/dlc.rpf"
    effective = override if override.is_file() else stock
    source = "mods" if override.is_file() else "stock"
    if not effective.is_file():
        return False
    try:
        relative = effective.relative_to(gta_path).as_posix()
        stat = effective.stat()
    except (OSError, ValueError):
        return False
    # Deliberately do not hash the large stock archive during the bounded
    # launch scan. Its effective source, path, size and nanosecond timestamp
    # must still match the attested build input; full canary status can perform
    # the expensive content hash when explicitly requested.
    return (
        payload.get("source") == source
        and payload.get("path") == relative
        and payload.get("size") == stat.st_size
        and payload.get("mtime_ns") == stat.st_mtime_ns
    )


def _stock_mptuner_bridge_receipt_is_valid(
    payload: object,
    *,
    gta_path: Path,
    archive_bytes: int,
    archive_sha256: str,
) -> bool:
    if (
        not isinstance(payload, dict)
        or set(payload) != _STOCK_MPTUNER_BRIDGE_RECEIPT_FIELDS
    ):
        return False
    return (
        _is_exact_int(payload.get("schema"), 4)
        and payload.get("canary_id") == _STOCK_MPTUNER_BRIDGE_CANARY_ID
        and payload.get("status") == "verified"
        and payload.get("phase") == _STOCK_MPTUNER_BRIDGE_PHASE
        and payload.get("package_id") == "allin1.online-content"
        and payload.get("pack_name") == _STOCK_MPTUNER_BRIDGE_PACK
        and payload.get("device_name") == _STOCK_MPTUNER_BRIDGE_DEVICE
        and payload.get("edition") == "enhanced"
        and payload.get("layout") == _STOCK_MPTUNER_BRIDGE_LAYOUT
        and payload.get("runtime_contract") ==
            _STOCK_MPTUNER_BRIDGE_CONTRACT
        and payload.get("archive_registration") == "metadata-only"
        and payload.get("activation") == "disabled-phase-a-boot-only"
        and _is_exact_int(payload.get("asset_count"), 0)
        and _is_exact_int(payload.get("data_file_count"), 0)
        and payload.get("startup_changeset") ==
            _STOCK_MPTUNER_BRIDGE_BASE_CHANGESET
        and _is_exact_int(payload.get("dormant_group_count"), 1)
        and payload.get("declared_groups") == [
            "GROUP_STARTUP", _STOCK_MPTUNER_BRIDGE_GROUP,
        ]
        and payload.get("stock_changesets") == [
            _STOCK_MPTUNER_CHANGESET,
        ]
        and payload.get("groups") == [{
            "property": "davis",
            "group": _STOCK_MPTUNER_BRIDGE_GROUP,
            "changesets": [_STOCK_MPTUNER_CHANGESET],
            "activation_enabled": False,
        }]
        and payload.get("native_group_execution_enabled") is False
        and payload.get("runtime_ipl_requests_enabled") is False
        and payload.get("gameconfig_changed") is False
        and payload.get("native_host_installed") is False
        and _is_exact_int(payload.get("archive_bytes"), archive_bytes)
        and isinstance(payload.get("archive_sha256"), str)
        and hmac.compare_digest(
            payload["archive_sha256"].casefold(), archive_sha256.casefold(),
        )
        and _stock_mptuner_source_attestation_is_valid(
            payload.get("source_attestation"), gta_path,
        )
    )


def _scan_stock_mptuner_bridge(gta_path: Path) -> HealthIssue | None:
    root = (
        gta_path / "mods/update/x64/dlcpacks" /
        _STOCK_MPTUNER_BRIDGE_PACK
    )

    def invalid(detail: str, path: Path = root) -> HealthIssue:
        return HealthIssue(
            "stock_mptuner_bridge_phase_a_invalid", "error",
            "The Phase-A stock mptuner bridge failed its closed launch "
            f"contract ({detail}). Roll it back before launching GTA V.",
            str(path),
        )

    if not root.exists() and not root.is_symlink():
        return None
    if root.is_symlink() or not root.is_dir():
        return invalid("pack root is not a regular directory")
    if not (gta_path / "GTA5_Enhanced.exe").is_file():
        return invalid("the bridge is authorized only for Enhanced")

    # Phase B deliberately reuses the exact Phase-A pack root and filenames.
    # Detect it before applying the Phase-A-only field allowlists. A damaged
    # Phase-B marker is still recognized from its bounded receipt so changing
    # the preamble cannot downgrade the scan into a different contract.
    from allin1 import map_stock_bridge_black_canary as phase_b

    marker_candidate = root / _STOCK_MPTUNER_BRIDGE_MARKER
    receipt_candidate = root / _STOCK_MPTUNER_BRIDGE_RECEIPT
    phase_b_claimed = False
    try:
        first_line = marker_candidate.read_text(
            encoding="utf-8",
        ).replace("\r", "").split("\n", 1)[0]
        phase_b_claimed = first_line == phase_b.MARKER_PREAMBLE
    except (OSError, UnicodeError):
        pass
    if not phase_b_claimed and receipt_candidate.is_file():
        try:
            if receipt_candidate.stat().st_size <= 256 * 1024:
                phase_b_claimed = json.loads(receipt_candidate.read_text(
                    encoding="utf-8",
                )).get("canary_id") == phase_b.CANARY_ID
        except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
            pass
    if phase_b_claimed:
        ready, detail, _receipt = phase_b.validate_phase_b_launch_contract(
            gta_path,
        )
        if not ready:
            return HealthIssue(
                "stock_mptuner_bridge_phase_b_invalid", "error",
                "The Phase-B Davis black-transition bridge failed its "
                f"closed launch contract ({detail}). Restore Phase A before "
                "launching GTA V.",
                str(marker_candidate),
            )
        return HealthIssue(
            "stock_mptuner_bridge_phase_b_ready", "info",
            "The exact Davis Phase-B bridge is verified for explicit garage "
            "entry under a required black transition. Proximity activation "
            "remains disabled and the map stays resident for this session.",
            str(marker_candidate),
        )

    old_roots = (
        gta_path / "mods/update/x64/dlcpacks/allin1_maps",
        gta_path / "update/x64/dlcpacks/allin1_maps",
    )
    if any(path.exists() for path in old_roots):
        return invalid("a retired allin1_maps pack is still present")
    native_hosts: set[Path] = set()
    for parent in (gta_path, gta_path / "scripts"):
        if not parent.is_dir():
            continue
        for path in parent.glob("*.asi"):
            if path.is_file() and "maphost" in path.stem.casefold():
                native_hosts.add(path)
    if native_hosts:
        return invalid(
            "a native map host is installed",
            sorted(native_hosts, key=lambda item: str(item).casefold())[0],
        )

    archive = root / "dlc.rpf"
    marker = root / _STOCK_MPTUNER_BRIDGE_MARKER
    receipt = root / _STOCK_MPTUNER_BRIDGE_RECEIPT
    try:
        entries = {path.name: path for path in root.iterdir()}
    except OSError as exc:
        return invalid(f"pack directory is unreadable: {exc}")
    if set(entries) != {
        "dlc.rpf", _STOCK_MPTUNER_BRIDGE_MARKER,
        _STOCK_MPTUNER_BRIDGE_RECEIPT,
    }:
        return invalid("pack files differ from the exact three-file layout")
    if any(path.is_symlink() or not path.is_file() for path in entries.values()):
        return invalid("pack contains a non-regular file")
    try:
        archive_bytes = archive.stat().st_size
        if archive_bytes <= 0 or archive_bytes > 4 * 1024 * 1024:
            return invalid("metadata archive size is outside the bounded contract")
        archive_sha256 = sha256_file(archive)
    except OSError as exc:
        return invalid(f"metadata archive is unreadable: {exc}", archive)

    marker_payload, marker_detail = _read_strict_key_value_marker(
        marker,
        fields=_STOCK_MPTUNER_BRIDGE_MARKER_FIELDS,
        preamble=_STOCK_MPTUNER_BRIDGE_MARKER_PREAMBLE,
    )
    if marker_payload is None:
        return invalid(marker_detail, marker)
    expected_marker = {
        "canary_id": _STOCK_MPTUNER_BRIDGE_CANARY_ID,
        "schema": "4",
        "status": "installed_boot_only_pending",
        "phase": _STOCK_MPTUNER_BRIDGE_PHASE,
        "layout": _STOCK_MPTUNER_BRIDGE_LAYOUT,
        "runtime_contract": _STOCK_MPTUNER_BRIDGE_CONTRACT,
        "archive_registration": "metadata-only",
        "activation": "disabled-phase-a-boot-only",
        "asset_count": "0",
        "data_file_count": "0",
        "startup_changeset": _STOCK_MPTUNER_BRIDGE_BASE_CHANGESET,
        "dormant_group_count": "1",
        "declared_groups": (
            "GROUP_STARTUP," + _STOCK_MPTUNER_BRIDGE_GROUP
        ),
        "stock_changesets": _STOCK_MPTUNER_CHANGESET,
        "native_group_execution_enabled": "false",
        "runtime_ipl_requests_enabled": "false",
        "gameconfig_changed": "false",
        "native_host_installed": "false",
        "receipt": _STOCK_MPTUNER_BRIDGE_RECEIPT,
        "archive_bytes": str(archive_bytes),
        "archive_sha256": archive_sha256.upper(),
    }
    if {
        key: value.casefold() if key == "archive_sha256" else value
        for key, value in marker_payload.items()
    } != {
        key: value.casefold() if key == "archive_sha256" else value
        for key, value in expected_marker.items()
    }:
        return invalid("marker values do not match the Phase-A contract", marker)

    receipt_payload, receipt_detail = _read_bounded_json_object(receipt)
    if receipt_payload is None:
        return invalid(receipt_detail, receipt)
    if not _stock_mptuner_bridge_receipt_is_valid(
        receipt_payload,
        gta_path=gta_path,
        archive_bytes=archive_bytes,
        archive_sha256=archive_sha256,
    ):
        return invalid("receipt or source attestation drifted", receipt)
    return HealthIssue(
        "stock_mptuner_bridge_phase_a_ready", "info",
        "The exact metadata-only Phase-A mptuner bridge is verified and "
        "pending its boot test. Its Davis group is dormant: native group "
        "execution and runtime IPL requests are disabled.",
        str(marker),
    )


def _scan_stock_mpheist_grapeseed_bridge(
    gta_path: Path,
) -> HealthIssue | None:
    """Validate Grapeseed's exact stock-reference bridge at launch time.

    This scan intentionally delegates the contract details to the canary
    modules so health cannot drift from the installer. Those validators hash
    only the tiny metadata bridge and compare the effective multi-gigabyte
    ``mpheist`` source by its attested path, size, and timestamp.
    """
    root = (
        gta_path / "mods/update/x64/dlcpacks" /
        _STOCK_MPHEIST_GRAPESEED_BRIDGE_PACK
    )
    if not root.exists() and not root.is_symlink():
        return None

    from allin1 import map_grapeseed_stock_bridge_canary as phase_a
    from allin1 import map_grapeseed_stock_bridge_black_canary as phase_b

    marker = root / phase_a.MARKER_NAME
    receipt = root / phase_a.RUNTIME_RECEIPT_NAME

    # Phase B reuses the Phase-A filenames. Classify it before running the
    # Phase-A allowlists, and retain that classification even when JSON or the
    # marker has been damaged. This prevents a corrupt promoted bridge from
    # being reported as (or restored through) the less-authoritative phase.
    phase_b_tokens = tuple(
        value.encode("utf-8") for value in (
            phase_b.CANARY_ID,
            phase_b.MARKER_PREAMBLE,
            phase_b.RUNTIME_CONTRACT,
        )
    )

    def bounded_phase_b_claim(path: Path) -> bool:
        try:
            if path.is_symlink() or not path.is_file():
                return False
            size = path.stat().st_size
            if size <= 0:
                return False
            # Classification is not validation. Read only the bounded prefix
            # so an oversized, damaged Phase-B file is still reported as a
            # Phase-B contract failure rather than falling back to Phase A.
            with path.open("rb") as stream:
                payload = stream.read(64 * 1024)
        except OSError:
            return False
        return any(token in payload for token in phase_b_tokens)

    phase_b_claimed = (
        bounded_phase_b_claim(marker) or bounded_phase_b_claim(receipt)
    )
    if phase_b_claimed:
        ready, detail, _payload = phase_b.validate_phase_b_launch_contract(
            gta_path,
        )
        if ready:
            ready, registration_detail, _registration = (
                phase_b.validate_phase_b_launch_registration_contract(
                    gta_path,
                )
            )
            if not ready:
                detail = registration_detail
        if not ready:
            return HealthIssue(
                "stock_mpheist_grapeseed_bridge_phase_b_invalid", "error",
                "The Phase-B Grapeseed black-transition bridge failed its "
                f"closed launch contract ({detail}). Restore Phase A before "
                "launching GTA V.",
                str(marker),
            )
        return HealthIssue(
            "stock_mpheist_grapeseed_bridge_phase_b_ready", "info",
            "The exact Grapeseed Phase-B bridge is verified for explicit "
            "garage entry under a required black transition. Proximity "
            "activation remains disabled and the map stays resident for this "
            "session.",
            str(marker),
        )

    ready, detail, _payload = phase_a.validate_phase_a_launch_contract(
        gta_path,
    )
    if not ready:
        return HealthIssue(
            "stock_mpheist_grapeseed_bridge_phase_a_invalid", "error",
            "The Phase-A Grapeseed stock mpheist bridge failed its closed "
            f"launch contract ({detail}). Roll it back before launching GTA V.",
            str(marker),
        )
    return HealthIssue(
        "stock_mpheist_grapeseed_bridge_phase_a_ready", "info",
        "The exact metadata-only Grapeseed Phase-A bridge is verified and "
        "pending its boot observation. Its Rockstar group is dormant: native "
        "group execution and runtime IPL requests are disabled.",
        str(marker),
    )


def _canary_marker_path(gta_path: Path) -> Path:
    return gta_path / "scripts" / COLORED_SMOKE_CANARY_MARKER


def _read_canary_marker(gta_path: Path) -> dict | None:
    marker = _canary_marker_path(gta_path)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def is_rpf_canary_authorized(
    gta_path: Path, pack_id: str, archive: Path,
) -> bool:
    """Allow only the exact, unattempted smoke canary built by RpfPatcher."""
    if pack_id != COLORED_SMOKE_PACK_ID or not archive.is_file():
        return False
    marker = _read_canary_marker(gta_path)
    if marker is None:
        return False
    expected = marker.get("archive_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    try:
        actual = sha256_file(archive)
    except OSError:
        return False
    return (
        marker.get("schema") == 2
        and marker.get("pack_id") == pack_id
        and marker.get("canary_state") == "pending"
        and hmac.compare_digest(actual.lower(), expected.lower())
    )


def consume_rpf_canary(gta_path: Path, pack_id: str) -> bool:
    """Atomically consume a pending canary after the launcher hands off GTA."""
    archive = (
        gta_path / "mods" / "update" / "x64" / "dlcpacks" /
        pack_id / "dlc.rpf"
    )
    if not is_rpf_canary_authorized(gta_path, pack_id, archive):
        return False
    marker_path = _canary_marker_path(gta_path)
    marker = _read_canary_marker(gta_path)
    if marker is None:
        return False
    marker["canary_state"] = "attempted"
    marker["attempted_at_utc"] = datetime.now(timezone.utc).isoformat()
    temporary = marker_path.with_name(marker_path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, marker_path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def _performance_isolation_invalid(
    pointer: Path, detail: str,
) -> HealthIssue:
    return HealthIssue(
        "performance_isolation_invalid", "error",
        "Performance isolation state could not be safely verified "
        f"({detail}). Do not launch GTA V. Run "
        ".work\\performance-isolation\\mod-matrix.ps1 -Action restore for "
        "this GTA installation, then rerun Health Check.",
        str(pointer),
    )


def _display_isolation_value(value: object) -> str:
    """Keep untrusted manifest labels short and single-line for the GUI."""
    if not isinstance(value, str):
        return "unknown"
    normalized = " ".join(value.split())
    return normalized[:128] if normalized else "unknown"


def _scan_performance_isolation(gta_path: Path) -> HealthIssue | None:
    """Fail closed when a PerformanceIsolation session may still be active."""
    root = Path(gta_path) / PERFORMANCE_ISOLATION_ROOT
    pointer = root / PERFORMANCE_ISOLATION_POINTER

    # lstat distinguishes an absent marker (ordinary operation) from a broken
    # symlink or unreadable marker, both of which leave the launch state
    # unverifiable and must block.
    try:
        pointer.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        return _performance_isolation_invalid(pointer, "marker is unreadable")

    try:
        root_resolved = root.resolve(strict=True)
        pointer_resolved = pointer.resolve(strict=True)
        pointer_resolved.relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        return _performance_isolation_invalid(
            pointer, "marker does not resolve inside the isolation backup root",
        )

    try:
        marker = json.loads(pointer_resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _performance_isolation_invalid(pointer, "marker is malformed")
    if not isinstance(marker, dict):
        return _performance_isolation_invalid(
            pointer, "marker is not a JSON object",
        )

    manifest_reference = marker.get("manifest")
    if not isinstance(manifest_reference, str) or not manifest_reference.strip():
        return _performance_isolation_invalid(
            pointer, "marker has no valid manifest reference",
        )

    try:
        manifest_candidate = Path(manifest_reference)
        if not manifest_candidate.is_absolute():
            manifest_candidate = root_resolved / manifest_candidate
        manifest = manifest_candidate.resolve(strict=True)
        manifest.relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        return _performance_isolation_invalid(
            pointer, "manifest does not resolve inside the isolation backup root",
        )

    try:
        state = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _performance_isolation_invalid(pointer, "manifest is malformed")
    if not isinstance(state, dict):
        return _performance_isolation_invalid(
            pointer, "manifest is not a JSON object",
        )

    status_value = state.get("status")
    if not isinstance(status_value, str) or not status_value.strip():
        return _performance_isolation_invalid(
            pointer, "manifest has no valid status",
        )
    status = status_value.strip().casefold()
    if status in PERFORMANCE_ISOLATION_INACTIVE_STATUSES:
        return None
    if status != "active":
        return _performance_isolation_invalid(
            pointer, f"manifest has unknown status {_display_isolation_value(status)!r}",
        )

    session = _display_isolation_value(
        state.get("session_id", marker.get("session_id")),
    )
    stage = _display_isolation_value(state.get("current_stage"))
    return HealthIssue(
        "performance_isolation_active", "error",
        f"Performance isolation session {session!r} is active at stage "
        f"{stage!r}. Run "
        ".work\\performance-isolation\\mod-matrix.ps1 -Action restore for "
        "this GTA installation, then rerun Health Check.",
        str(manifest),
    )


def scan_launch_hazards(gta_path: Path) -> tuple[HealthIssue, ...]:
    """Check conditions that must block an immediate game launch.

    The full health report validates binaries, hashes, versions, duplicates,
    and compatibility.  That belongs in Setup/Health and can traverse a large
    installation. Launch needs a much smaller fail-closed check for active
    performance isolation and known bad or incomplete ALLIN1 pack roots.
    """
    issues: list[HealthIssue] = []
    isolation_issue = _scan_performance_isolation(Path(gta_path))
    if isolation_issue is not None:
        issues.append(isolation_issue)
    stock_bridge_issue = _scan_stock_mptuner_bridge(Path(gta_path))
    if stock_bridge_issue is not None:
        issues.append(stock_bridge_issue)
    grapeseed_bridge_issue = _scan_stock_mpheist_grapeseed_bridge(
        Path(gta_path),
    )
    if grapeseed_bridge_issue is not None:
        issues.append(grapeseed_bridge_issue)
    dlcpacks = Path(gta_path) / "mods/update/x64/dlcpacks"
    for pack_id, reason in QUARANTINED_RPF_PACKS.items():
        archive = dlcpacks / pack_id / "dlc.rpf"
        if not archive.is_file():
            continue
        if is_rpf_canary_authorized(Path(gta_path), pack_id, archive):
            issues.append(HealthIssue(
                "rpf_pack_canary", "info",
                "A hash-verified colored-smoke canary is authorized for "
                "one Story Mode launch.", str(archive),
            ))
        else:
            issues.append(HealthIssue(
                "rpf_pack_quarantined", "error",
                f"Quarantined RPF pack is still installed: {pack_id}. {reason}",
                str(archive),
            ))
    if dlcpacks.is_dir():
        for pack in sorted(dlcpacks.glob("allin1_*")):
            if (
                not pack.is_dir()
                or pack.name in QUARANTINED_RPF_PACKS
                or pack.name == _STOCK_MPTUNER_BRIDGE_PACK
                or pack.name == _STOCK_MPHEIST_GRAPESEED_BRIDGE_PACK
            ):
                continue
            archive = pack / "dlc.rpf"
            if not archive.is_file() or archive.stat().st_size == 0:
                issues.append(HealthIssue(
                    "rpf_pack_incomplete", "error",
                    f"ALLIN1 RPF pack is incomplete: {pack.name}.", str(pack),
                ))
    return tuple(issues)


def scan_installation(gta_path: Path, *, expected_hashes: dict[str, str] | None = None) -> HealthReport:
    issues: list[HealthIssue] = []
    rpf_plugin_active = False
    legacy = gta_path / "GTA5.exe"
    enhanced = gta_path / "GTA5_Enhanced.exe"
    edition = "enhanced" if enhanced.is_file() else "legacy" if legacy.is_file() else "unknown"
    if edition == "unknown":
        issues.append(HealthIssue("game_missing", "error", "GTA V executable was not found.", str(gta_path)))
    for name in ("ScriptHookV.dll", *SHVDN_REQUIRED_BINARIES):
        path = gta_path / name
        if not path.is_file():
            issues.append(HealthIssue("dependency_missing", "error", f"Required dependency is missing: {name}", str(path)))
        else:
            inspection = inspect_windows_binary(path)
            if not inspection.valid:
                issues.append(HealthIssue(
                    "dependency_corrupt", "error",
                    f"Required dependency is invalid: {name} ({inspection.reason}).", str(path),
                ))
    if edition != "unknown":
        # Imported here to keep PE validation in this module while avoiding a
        # module-import cycle: rpf_loader uses inspect_windows_binary above.
        from allin1.rpf_loader import PLUGIN_NAMES, inspect_rpf_loader
        rpf_status = inspect_rpf_loader(gta_path, edition == "enhanced")
        rpf_plugin_active = rpf_status.plugin is not None
        present_plugins = [
            gta_path / name for name in PLUGIN_NAMES
            if (gta_path / name).exists()
        ]
        if rpf_status.conflicts:
            issues.append(HealthIssue(
                "rpf_loader_conflict", "error", rpf_status.reason,
                str(rpf_status.conflicts[0]),
            ))
        elif rpf_status.plugin is not None and rpf_status.asi_loader is None:
            code = "asi_loader_corrupt" if "invalid" in rpf_status.reason.lower() else "asi_loader_missing"
            issues.append(HealthIssue(
                code, "error", rpf_status.reason, str(gta_path),
            ))
        elif not rpf_status.ready and present_plugins:
            issues.append(HealthIssue(
                "rpf_loader_corrupt", "error", rpf_status.reason,
                str(present_plugins[0]),
            ))
            asi_names = (
                ("xinput1_4.dll", "dsound.dll", "dinput8.dll")
                if edition == "enhanced" else ("dinput8.dll",)
            )
            present_asi = [
                gta_path / name for name in asi_names
                if (gta_path / name).exists()
            ]
            if not any(inspect_windows_binary(path).valid for path in present_asi):
                issues.append(HealthIssue(
                    "asi_loader_corrupt" if present_asi else "asi_loader_missing",
                    "error",
                    "ASI loader files are invalid." if present_asi
                    else "RPF plug-in is present but no ASI loader was detected.",
                    str(gta_path),
                ))
        elif not rpf_status.ready:
            expected = "RageOpenV.asi"
            issues.append(HealthIssue(
                "rpf_loader_missing", "warning",
                f"{expected} is missing; previews may not load.",
                str(gta_path / expected),
            ))
    preview_dir = gta_path / "mods/update/x64/dlcpacks/allin1_previews"
    if preview_dir.exists():
        preview_rpf = preview_dir / "dlc.rpf"
        if not preview_rpf.is_file() or preview_rpf.stat().st_size == 0:
            issues.append(HealthIssue(
                "preview_dlc_invalid", "error",
                "The ALLIN1 preview DLC is incomplete; run Install / Repair.",
                str(preview_dir),
            ))
    maps_dir = gta_path / "mods/update/x64/dlcpacks/allin1_maps"
    if maps_dir.exists():
        maps_rpf = maps_dir / "dlc.rpf"
        if not maps_rpf.is_file() or maps_rpf.stat().st_size == 0:
            issues.append(HealthIssue(
                "standalone_map_dlc_invalid", "error",
                "The ALLIN1 standalone map DLC is incomplete; run Install / Repair.",
                str(maps_dir),
            ))
        else:
            # Keep this import local so the ordinary dependency scan remains
            # lightweight when no generated map pack is installed.
            from allin1.generators import dlc_maps

            marker = maps_dir / dlc_maps.ACTIVE_MARKER
            try:
                marker_text = marker.read_text(
                    encoding="utf-8", errors="replace",
                )
            except OSError:
                marker_text = ""
            layout = ""
            archive_registration = ""
            activation = ""
            asset_count = ""
            receipt_name = ""
            runtime_contract = ""
            property_scope = ""
            group_map_binding = ""
            startup_rpf_enable_count = ""
            startup_file_enable_count = ""
            reference_count = ""
            custom_property_groups = ""
            marker_archive_bytes = ""
            marker_archive_sha256 = ""
            for raw_line in marker_text.splitlines():
                line = raw_line.strip()
                if line.lower().startswith("layout="):
                    layout = line.split("=", 1)[1].strip()
                elif line.lower().startswith("archive_registration="):
                    archive_registration = line.split("=", 1)[1].strip()
                elif line.lower().startswith("activation="):
                    activation = line.split("=", 1)[1].strip()
                elif line.lower().startswith("asset_count="):
                    asset_count = line.split("=", 1)[1].strip()
                elif line.lower().startswith("receipt="):
                    receipt_name = line.split("=", 1)[1].strip()
                elif line.lower().startswith("runtime_contract="):
                    runtime_contract = line.split("=", 1)[1].strip()
                elif line.lower().startswith("property_scope="):
                    property_scope = line.split("=", 1)[1].strip()
                elif line.lower().startswith("group_map_binding="):
                    group_map_binding = line.split("=", 1)[1].strip()
                elif line.lower().startswith("startup_rpf_enable_count="):
                    startup_rpf_enable_count = line.split("=", 1)[1].strip()
                elif line.lower().startswith("startup_file_enable_count="):
                    startup_file_enable_count = line.split("=", 1)[1].strip()
                elif line.lower().startswith("reference_count="):
                    reference_count = line.split("=", 1)[1].strip()
                elif line.lower().startswith("custom_property_groups="):
                    custom_property_groups = line.split("=", 1)[1].strip()
                elif line.lower().startswith("archive_bytes="):
                    marker_archive_bytes = line.split("=", 1)[1].strip()
                elif line.lower().startswith("archive_sha256="):
                    marker_archive_sha256 = line.split("=", 1)[1].strip()
            if (
                layout == dlc_maps.REFERENCE_PACK_LAYOUT
                and archive_registration == "metadata-bridge"
                and activation == "property-group-runtime"
            ):
                valid, detail, _ = (
                    dlc_maps.validate_reference_bridge_receipt(
                        maps_dir, edition=edition, gta_path=gta_path,
                    )
                )
                if valid:
                    issues.append(HealthIssue(
                        "garage_map_bridge_ready", "info",
                        "The lightweight garage map bridge is verified. "
                        "Rockstar map resources will load per garage and "
                        "unload after its transition.",
                        str(marker),
                    ))
                else:
                    issues.append(HealthIssue(
                        "garage_map_bridge_invalid", "error",
                        "The garage map bridge failed verification; run "
                        f"Install / Repair before launching ({detail}).",
                        str(marker),
                    ))
            elif archive_registration == "disabled":
                issues.append(HealthIssue(
                    "standalone_map_dlc_unregistered", "info",
                    "The local ALLIN1 map archive is safely excluded from "
                    "startup registration. Map-backed garages and the yacht "
                    "remain unavailable until a safe on-demand mount path is "
                    "validated.",
                    str(marker),
                ))
            elif (
                layout == dlc_maps.DEFERRED_PACK_LAYOUT
                and archive_registration == "property-groups"
                and activation == "property-group-native-host-required"
                and asset_count == "2"
            ):
                runtime_receipt = maps_dir / receipt_name
                runtime_ready = False
                if (
                    receipt_name == dlc_maps.RUNTIME_RECEIPT
                    and runtime_contract == "allin1-isolated-property-v1"
                    and property_scope == "davis"
                    and runtime_receipt.is_file()
                ):
                    try:
                        payload = json.loads(runtime_receipt.read_text(
                            encoding="utf-8",
                        ))
                        runtime_ready = (
                            payload.get("schema") == 2
                            and payload.get("status") == "verified"
                            and payload.get("package_id") ==
                                "allin1.online-content"
                            and payload.get("pack_name") == "allin1_maps"
                            and payload.get("edition") == edition
                            and payload.get("layout") ==
                                dlc_maps.DEFERRED_PACK_LAYOUT
                            and payload.get("runtime_contract") ==
                                runtime_contract
                            and payload.get("properties") == ["davis"]
                            and payload.get("asset_count") == 2
                            and payload.get("startup_rpf_enable_count") == 0
                            and payload.get("archive_bytes") ==
                                maps_rpf.stat().st_size
                            and payload.get("archive_sha256") ==
                                marker_archive_sha256
                        )
                    except (OSError, TypeError, ValueError,
                            json.JSONDecodeError):
                        runtime_ready = False
                if runtime_ready:
                    issues.append(HealthIssue(
                        "davis_isolated_map_runtime_ready", "info",
                        "The isolated Davis map package is installed with "
                        "zero startup RPF enables. ALLIN1 will verify its full "
                        "receipt and stream only Davis on demand.",
                        str(marker),
                    ))
                else:
                    issues.append(HealthIssue(
                        "standalone_map_dlc_registration_canary", "info",
                        "The guarded Davis map canary is registered with zero "
                        "startup RPF enables, but no valid runtime receipt was "
                        "found. Its content group remains dormant.",
                        str(marker),
                    ))
            elif (
                layout == dlc_maps.STARTUP_IPL_PACK_LAYOUT
                and archive_registration == "startup"
                and activation ==
                    "startup-file-registration-plus-request-ipl"
                and runtime_contract ==
                    _DAVIS_STARTUP_IPL_RUNTIME_CONTRACT
                and property_scope == "davis"
                and group_map_binding == "false"
                and asset_count == "3"
                and startup_rpf_enable_count == "2"
                and startup_file_enable_count == "3"
                and reference_count == "3"
                and custom_property_groups == "0"
                and receipt_name == dlc_maps.RUNTIME_RECEIPT
                and marker_archive_bytes == str(maps_rpf.stat().st_size)
                and len(marker_archive_sha256) == 64
                and all(
                    character in "0123456789abcdefABCDEF"
                    for character in marker_archive_sha256
                )
            ):
                runtime_receipt = maps_dir / receipt_name
                runtime_ready = False
                if runtime_receipt.is_file():
                    try:
                        payload = json.loads(runtime_receipt.read_text(
                            encoding="utf-8",
                        ))
                        runtime_ready = (
                            sha256_file(maps_rpf).casefold() ==
                                marker_archive_sha256.casefold()
                            and _valid_davis_startup_ipl_receipt(
                                payload,
                                edition=edition,
                                archive_bytes=maps_rpf.stat().st_size,
                                archive_sha256=marker_archive_sha256,
                            )
                        )
                    except (OSError, TypeError, ValueError,
                            json.JSONDecodeError):
                        runtime_ready = False
                if runtime_ready:
                    message = (
                        "The exact, receipt-verified Davis startup/IPL v3 "
                        "package is quarantined after repeatable live GTA V "
                        "Enhanced crashes. Startup registration reached the "
                        "same native write-to-null before SHVDNE or ALLIN1 "
                        "initialized. Run Install / Repair or startup-rollback "
                        "to remove it before launching."
                    )
                else:
                    message = (
                        "The Davis startup/IPL marker has no matching verified "
                        "three-file receipt and the entire v3 layout is "
                        "quarantined after live startup crashes. Run Install / "
                        "Repair or startup-rollback to remove the unsafe "
                        "registration before launching."
                    )
                issues.append(HealthIssue(
                    "standalone_map_dlc_unsafe_registration", "error",
                    message,
                    str(marker),
                ))
            elif (
                layout == dlc_maps.STARTUP_IPL_PACK_LAYOUT
                or archive_registration == "startup"
            ):
                # A receipt proves only the static install transaction.  The
                # startup-registered layout subsequently crashed Story Mode,
                # so health must reject it even when every hash still matches.
                issues.append(HealthIssue(
                    "standalone_map_dlc_unsafe_registration", "error",
                    "The ALLIN1 map archive is startup-registered. This layout "
                    "is quarantined after Story Mode loading crashes; run "
                    "Install / Repair to remove its dlclist entry and receipt "
                    "before launching.",
                    str(marker),
                ))
            else:
                issues.append(HealthIssue(
                    "standalone_map_dlc_outdated", "warning",
                    "The ALLIN1 map archive does not have the current disabled "
                    "startup-safety marker. Run Install / Repair to quarantine "
                    "it before launching.",
                    str(marker),
                ))
    issues.extend(scan_launch_hazards(gta_path))
    archive_names = ("update.rpf", "update2.rpf") if edition == "enhanced" else ("update.rpf",)
    for archive_name in archive_names:
        mods_update = gta_path / "mods/update" / archive_name
        base_update = gta_path / "update" / archive_name
        if (rpf_plugin_active and mods_update.is_file() and base_update.is_file()
                and mods_update.stat().st_mtime_ns + 1_000_000_000 < base_update.stat().st_mtime_ns):
            issues.append(HealthIssue(
                "rpf_mod_archive_stale", "error",
                f"mods/update/{archive_name} predates the installed game update and may crash "
                "the RPF loader; run Install / Repair before launching.",
                str(mods_update),
            ))

    scripts = gta_path / "scripts"
    dll = scripts / "ALLIN1.dll"
    if not dll.is_file():
        issues.append(HealthIssue("mod_missing", "error", "ALLIN1.dll is not installed.", str(dll)))
    else:
        inspection = inspect_windows_binary(dll)
        if not inspection.valid:
            issues.append(HealthIssue(
                "mod_corrupt", "error", f"ALLIN1.dll is invalid ({inspection.reason}).", str(dll),
            ))
    non_loading_backup_roots = {"allin1_backups", ".reactorv-backups"}
    duplicates = sorted(
        path for path in gta_path.rglob("ALLIN1.dll")
        if path != dll and not non_loading_backup_roots.intersection({
            part.lower() for part in path.relative_to(gta_path).parts
        })
    )
    for duplicate in duplicates:
        issues.append(HealthIssue("duplicate_mod", "error", "Duplicate ALLIN1.dll may load twice.", str(duplicate)))

    # Missing/malformed/retired configuration must not bypass the dependency.
    if dll.is_file():
        reactor_files = (
            scripts / "ReactorV" / "ALLIN1.ReactorBridge.plugin",
            scripts / "ReactorV" / "RageWebUI.Core.dll",
            scripts / "ReactorV" / "RageWebUI.Script.dll",
        )
        reactor_contract = scripts / "ReactorV" / "ReactorV.contract.json"
        unavailable = [
            path for path in (*reactor_files, reactor_contract)
            if not path.is_file()
        ]
        invalid = []
        for path in reactor_files:
            if not path.is_file():
                continue
            # Reactor's netstandard Core contract is intentionally AnyCPU and
            # therefore carries the managed PE32 machine value (0x014c). The
            # Script and ALLIN1 bridge remain x64-only game assemblies.
            allowed = (0x8664, 0x014C) if path.name == "RageWebUI.Core.dll" \
                else (0x8664,)
            if not inspect_windows_binary(
                    path, allowed_machines=allowed).valid:
                invalid.append(path)
        if reactor_contract.is_file():
            try:
                contract = json.loads(reactor_contract.read_text(
                    encoding="utf-8"))
                capabilities = set(contract.get("capabilities", ()))
                contract_valid = (
                    contract.get("schema_version") == 1
                    and contract.get("product") == "reactor-v"
                    and contract.get("extension_api_version") == 1
                    and {
                        "story.menu-presentation",
                        "story.menu-bound-parameters",
                    } <= capabilities
                )
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
                contract_valid = False
            if not contract_valid:
                invalid.append(reactor_contract)
        if unavailable or invalid:
            detail = unavailable[0] if unavailable else invalid[0]
            issues.append(HealthIssue(
                "gbay_reactor_unavailable", "error",
                "GBAY requires Reactor V. The dependency is incomplete or invalid; "
                "use Install / Repair and allow the verified Reactor V download before launching.",
                str(detail),
            ))
    for old_name in ("ALLIN1.asi", "ALLIN1-Launcher.exe"):
        old = gta_path / old_name
        if old.exists():
            issues.append(HealthIssue("legacy_file", "warning", f"Legacy file should be removed: {old_name}", str(old)))
    for conflict in ("PackfileLimitAdjuster.asi", "HeapAdjuster.asi"):
        path = gta_path / conflict
        if path.exists():
            issues.append(HealthIssue("review_conflict", "info", f"Detected {conflict}; verify its settings match your game build.", str(path)))
    for relative, expected in (expected_hashes or {}).items():
        path = gta_path / relative
        if not path.is_file() or sha256_file(path).lower() != expected.lower():
            issues.append(HealthIssue("checksum_mismatch", "error", f"Installed file failed verification: {relative}", str(path)))
    try:
        installed = read_installed_version(scripts)
    except (OSError, ValueError):
        installed = None
        issues.append(HealthIssue("version_invalid", "warning", "Installed version marker is missing or invalid.", str(scripts)))
    return HealthReport(edition, installed, tuple(issues))
