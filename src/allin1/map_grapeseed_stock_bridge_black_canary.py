"""Phase-B black-transition promotion for the Enhanced Grapeseed bridge.

Promotion never rebuilds the Phase-A archive and never edits ``dlclist.xml``.
It atomically replaces only the exact marker and runtime receipt after one
clean Phase-A Story session has exercised the fail-closed Grapeseed guard.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from allin1 import map_grapeseed_stock_bridge_canary as phase_a


CANARY_ID = "grapeseed-enhanced-stock-reference-black-transition-v1"
PROMOTE_CONFIRMATION = (
    "PROMOTE_GRAPESEED_ENHANCED_STOCK_REFERENCE_BLACK_TRANSITION_V1"
)
ROLLBACK_CONFIRMATION = (
    "ROLLBACK_GRAPESEED_ENHANCED_STOCK_REFERENCE_BLACK_TRANSITION_V1"
)
STATE_SCHEMA = 5
STATE_DIRECTORY = "GrapeseedStockReferenceBlackTransitionV1"

PHASE = "phase-b-black-transition"
MARKER_STATUS = "installed_black_transition_pending_test"
RUNTIME_STATUS = "verified"
LAYOUT = phase_a.LAYOUT
RUNTIME_CONTRACT = "allin1-stock-mpheist-grapeseed-black-transition-v1"
ACTIVATION = "explicit-grapeseed-entry-black-transition"
ACTIVATION_SCOPE = "garage-entry-only"
PROPERTY_SCOPE = "grapeseed"
GRAPESEED_IPL = phase_a.GRAPESEED_IPL
MARKER_PREAMBLE = (
    "ALLIN1 stock mpheist Grapeseed Phase-B black-transition bridge; "
    "Grapeseed garage-entry activation only."
)

PACK_NAME = phase_a.PACK_NAME
DEVICE_NAME = phase_a.DEVICE_NAME
PACK_ENTRY = phase_a.PACK_ENTRY
MARKER_NAME = phase_a.MARKER_NAME
RUNTIME_RECEIPT_NAME = phase_a.RUNTIME_RECEIPT_NAME
STARTUP_CHANGESET = phase_a.STARTUP_CHANGESET
DORMANT_GROUP = phase_a.DORMANT_GROUP
STOCK_CHANGESET = phase_a.STOCK_CHANGESET
PACKAGE_ID = phase_a.PACKAGE_ID

CLIENT_LOG_RELATIVE = Path("scripts/ALLIN1_client.log")
SESSION_LOCK_RELATIVE = Path("scripts/ALLIN1_session.lock")
MINIMUM_POST_BLOCK_SURVIVAL_MS = 30_000
ALLOWED_REQUEST_SOURCES = frozenset({"startup_guard", "garage_entry"})

MARKER_FIELDS = frozenset({
    "canary_id", "schema", "status", "phase", "layout",
    "runtime_contract", "archive_registration", "activation",
    "activation_scope", "property_scope", "asset_count",
    "data_file_count", "startup_changeset", "dormant_group_count",
    "declared_groups", "stock_changesets", "ipls",
    "native_group_execution_enabled", "runtime_ipl_requests_enabled",
    "proximity_activation_enabled", "black_transition_required",
    "keep_resident", "release_on_exit", "gameconfig_changed",
    "native_host_installed", "phase_a_canary_id",
    "phase_a_transaction_id", "phase_a_observation_sha256", "receipt",
    "archive_bytes", "archive_sha256",
})
RECEIPT_FIELDS = frozenset({
    "schema", "canary_id", "status", "phase", "package_id",
    "pack_name", "device_name", "edition", "layout", "runtime_contract",
    "archive_registration", "activation", "activation_scope",
    "property_scope", "asset_count", "data_file_count",
    "startup_changeset", "dormant_group_count", "declared_groups",
    "stock_changesets", "ipls", "groups",
    "native_group_execution_enabled", "runtime_ipl_requests_enabled",
    "proximity_activation_enabled", "black_transition_required",
    "keep_resident", "release_on_exit", "gameconfig_changed",
    "native_host_installed", "archive_bytes", "archive_sha256",
    "source_attestation", "phase_a_parent", "phase_a_observation_sha256",
})
GROUP_FIELDS = frozenset({
    "property", "group", "changesets", "ipls", "activation_enabled",
    "activation_sources", "requires_black_screen", "keep_resident",
    "release_on_exit",
})
PARENT_FIELDS = frozenset({
    "canary_id", "transaction_id", "archive_sha256", "marker_sha256",
    "runtime_receipt_sha256",
})
OBSERVATION_FIELDS = frozenset({
    "schema", "status", "phase", "phase_a_canary_id",
    "phase_a_transaction_id", "phase_a_install_receipt_sha256", "session",
    "session_started_utc", "session_ended_utc", "client_log_sha256",
    "session_event_count", "blocked_event_count", "request_sources",
    "survival_after_last_block_ms", "error_count", "fatal_count",
    "game_closed", "session_lock_absent", "operator_confirmed",
})

PHASE_A_MARKER_BACKUP = "phase-a-marker"
PHASE_A_RUNTIME_BACKUP = "phase-a-runtime.json"
PHASE_B_MARKER_BACKUP = "phase-b-marker"
PHASE_B_RUNTIME_BACKUP = "phase-b-runtime.json"
JOURNAL_REQUIRED_FIELDS = frozenset({
    "schema", "canary_id", "transaction_id", "status", "phase",
    "phase_a_transaction_id", "phase_a_marker_sha256",
    "phase_a_runtime_receipt_sha256", "phase_b_marker_sha256",
    "phase_b_runtime_receipt_sha256", "archive_sha256",
    "registered_dlclist_sha256", "phase_a_observation_sha256",
})
JOURNAL_OPTIONAL_FIELDS = frozenset({"promotion_error", "recovery_error"})
JOURNAL_STATUSES = frozenset({
    "prepared",
    "promotion_runtime_replace_pending",
    "promotion_marker_replace_pending",
    "promotion_pair_replaced",
    "promotion_complete",
    "promotion_recovery_runtime_replace_pending",
    "promotion_recovery_marker_replace_pending",
    "promotion_recovery_pair_replaced",
    "rollback_started",
    "rollback_runtime_replace_pending",
    "rollback_marker_replace_pending",
    "rollback_pair_replaced",
    "rollback_complete",
    "recovery_required",
})
ROLLBACK_IN_PROGRESS_STATUSES = frozenset({
    "rollback_started",
    "rollback_runtime_replace_pending",
    "rollback_marker_replace_pending",
    "rollback_pair_replaced",
})
PREJOURNAL_ARTIFACTS = frozenset({
    PHASE_A_MARKER_BACKUP,
    PHASE_A_RUNTIME_BACKUP,
    "phase-a-install-receipt.json",
    "phase-a-observation.json",
    "phase-a-observation.json.tmp",
    PHASE_B_MARKER_BACKUP,
    PHASE_B_MARKER_BACKUP + ".tmp",
    PHASE_B_RUNTIME_BACKUP,
    PHASE_B_RUNTIME_BACKUP + ".tmp",
    "journal.json.tmp",
})


def _state_root(gta_path: Path, override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).resolve()
    base = os.environ.get("LOCALAPPDATA")
    local = Path(base) if base else Path.home() / "AppData" / "Local"
    identity = hashlib.sha256(
        str(gta_path.resolve()).casefold().encode("utf-8")
    ).hexdigest()[:16]
    return local / "ALLIN1" / "DeveloperCanaries" / STATE_DIRECTORY / identity


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _owned_prejournal_entries(state: Path) -> list[Path]:
    if _is_reparse_point(state) or not state.is_dir():
        raise RuntimeError(
            "The journal-less Grapeseed Phase-B checkpoint is not a regular "
            "owned directory."
        )
    entries = list(state.iterdir())
    unexpected = sorted(
        path.name for path in entries if path.name not in PREJOURNAL_ARTIFACTS
    )
    unsafe = sorted(
        path.name for path in entries
        if _is_reparse_point(path) or not path.is_file()
    )
    if unexpected or unsafe:
        details = ", ".join(unexpected + unsafe)
        raise RuntimeError(
            "The journal-less Grapeseed Phase-B checkpoint contains "
            f"unrecognized or non-regular artifacts: {details}."
        )
    return entries


def _discard_owned_prejournal_state(state: Path) -> None:
    """Discard only Phase-B preparation debris created before live mutation.

    The journal is durably published before either live marker/receipt rename.
    A journal-less state can therefore be retried, but only when its shallow
    contents are the exact regular-file names the preparation path can create.
    Deliberately avoid recursive deletion so a raced or unrecognized child is
    preserved and blocks the retry instead of being followed or removed.
    """
    entries = _owned_prejournal_entries(state)
    for path in entries:
        path.unlink()
    state.rmdir()


def _destination(game: Path) -> Path:
    return phase_a._destination(game)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical_json_sha256(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _parse_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _read_json_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"JSON evidence is not a regular file: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > 256 * 1024:
        raise RuntimeError(f"JSON evidence is outside its size bound: {path.name}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8-sig"),
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"JSON evidence is unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON evidence is not an object: {path.name}")
    return payload


def _exact_block_event(event: dict[str, Any]) -> bool:
    return (
        event.get("component") == "DeferredMap"
        and event.get("message") ==
        "grapeseed_phase_a_runtime_activation_blocked"
        and event.get("property") == "grapeseed"
        and event.get("request_source") in ALLOWED_REQUEST_SOURCES
        and event.get("required_phase") == PHASE
        and event.get("native_group_executed") is False
        and event.get("ipl_requested") is False
    )


def inspect_phase_a_session_evidence(
    game: Path,
    *,
    session: str,
    phase_a_receipt: dict[str, Any],
    phase_a_receipt_path: Path,
) -> dict[str, Any]:
    """Validate one completed Grapeseed Phase-A Story session."""
    if (
        len(session) != 12
        or session.casefold() != session
        or any(character not in "0123456789abcdef" for character in session)
    ):
        raise ValueError("The Phase-A session must be 12 lowercase hex digits.")
    log = game / CLIENT_LOG_RELATIVE
    if not log.is_file():
        raise FileNotFoundError("The Phase-A ALLIN1 client log is missing.")
    if (game / SESSION_LOCK_RELATIVE).exists():
        raise RuntimeError(
            "The ALLIN1 session lock still exists; clean shutdown is unproven."
        )
    raw = log.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise RuntimeError("The Phase-A client log exceeds the evidence bound.")
    events: list[dict[str, Any]] = []
    for line in raw.decode("utf-8-sig").splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict) and event.get("session") == session:
            events.append(event)
    starts = [
        event for event in events
        if event.get("component") == "Client"
        and event.get("message") == "session_started"
    ]
    if len(starts) != 1:
        raise RuntimeError("Phase-A evidence must contain one session start.")
    timed: list[tuple[dict[str, Any], datetime]] = []
    for event in events:
        timestamp = _parse_utc(event.get("ts"))
        if timestamp is None:
            raise RuntimeError("Phase-A session evidence has an invalid timestamp.")
        timed.append((event, timestamp))
    started = _parse_utc(starts[0].get("ts"))
    assert started is not None
    installed = datetime.fromtimestamp(
        phase_a_receipt_path.stat().st_mtime, tz=timezone.utc,
    )
    if started <= installed:
        raise RuntimeError("The selected session predates Phase-A installation.")
    blocks = [(event, stamp) for event, stamp in timed if _exact_block_event(event)]
    if not blocks:
        raise RuntimeError(
            "The selected session never exercised the exact Grapeseed guard."
        )
    ended = max(stamp for _event, stamp in timed)
    last_block = max(stamp for _event, stamp in blocks)
    survived_ms = int((ended - last_block).total_seconds() * 1000)
    if survived_ms < MINIMUM_POST_BLOCK_SURVIVAL_MS:
        raise RuntimeError(
            "The selected session did not survive the Grapeseed guard long enough."
        )
    errors = sum(event.get("level") == "ERROR" for event, _ in timed)
    fatals = sum(event.get("level") == "FATAL" for event, _ in timed)
    if errors or fatals:
        raise RuntimeError("The Phase-A session contains ERROR or FATAL events.")
    transaction_id = phase_a_receipt.get("transaction_id")
    if (
        not isinstance(transaction_id, str)
        or len(transaction_id) != 32
        or any(character not in "0123456789abcdef" for character in transaction_id)
    ):
        raise RuntimeError("The active Phase-A transaction identity is invalid.")
    return {
        "schema": 1,
        "status": "passed",
        "phase": phase_a.PHASE,
        "phase_a_canary_id": phase_a.CANARY_ID,
        "phase_a_transaction_id": transaction_id,
        "phase_a_install_receipt_sha256": phase_a.shared._sha256(
            phase_a_receipt_path,
        ),
        "session": session,
        "session_started_utc": started.isoformat(),
        "session_ended_utc": ended.isoformat(),
        "client_log_sha256": _sha256_bytes(raw),
        "session_event_count": len(events),
        "blocked_event_count": len(blocks),
        "request_sources": sorted({
            str(event["request_source"]) for event, _stamp in blocks
        }),
        "survival_after_last_block_ms": survived_ms,
        "error_count": 0,
        "fatal_count": 0,
        "game_closed": True,
        "session_lock_absent": True,
        "operator_confirmed": True,
    }


def _phase_a_parent(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "canary_id": phase_a.CANARY_ID,
        "transaction_id": receipt.get("transaction_id"),
        "archive_sha256": receipt.get("archive_sha256"),
        "marker_sha256": receipt.get("marker_sha256"),
        "runtime_receipt_sha256": receipt.get("runtime_receipt_sha256"),
    }


def _group_contract() -> dict[str, Any]:
    return {
        "property": PROPERTY_SCOPE,
        "group": DORMANT_GROUP,
        "changesets": [STOCK_CHANGESET],
        "ipls": [GRAPESEED_IPL],
        "activation_enabled": True,
        "activation_sources": ["garage_entry"],
        "requires_black_screen": True,
        "keep_resident": True,
        "release_on_exit": False,
    }


def _runtime_receipt(
    archive: Path,
    phase_a_receipt: dict[str, Any],
    observation_sha256: str,
) -> dict[str, Any]:
    payload = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": RUNTIME_STATUS,
        "phase": PHASE,
        "package_id": PACKAGE_ID,
        "pack_name": PACK_NAME,
        "device_name": DEVICE_NAME,
        "edition": "enhanced",
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": "metadata-only",
        "activation": ACTIVATION,
        "activation_scope": ACTIVATION_SCOPE,
        "property_scope": PROPERTY_SCOPE,
        "asset_count": 0,
        "data_file_count": 0,
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": 1,
        "declared_groups": ["GROUP_STARTUP", DORMANT_GROUP],
        "stock_changesets": [STOCK_CHANGESET],
        "ipls": [GRAPESEED_IPL],
        "groups": [_group_contract()],
        "native_group_execution_enabled": True,
        "runtime_ipl_requests_enabled": True,
        "proximity_activation_enabled": False,
        "black_transition_required": True,
        "keep_resident": True,
        "release_on_exit": False,
        "gameconfig_changed": False,
        "native_host_installed": False,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": phase_a.shared._sha256(archive),
        "source_attestation": phase_a_receipt.get("source_attestation"),
        "phase_a_parent": _phase_a_parent(phase_a_receipt),
        "phase_a_observation_sha256": observation_sha256,
    }
    phase_a._assert_portable_receipt(payload)
    return payload


def _marker_fields(receipt: dict[str, Any]) -> dict[str, str]:
    parent = receipt["phase_a_parent"]
    return {
        "canary_id": CANARY_ID,
        "schema": str(STATE_SCHEMA),
        "status": MARKER_STATUS,
        "phase": PHASE,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": "metadata-only",
        "activation": ACTIVATION,
        "activation_scope": ACTIVATION_SCOPE,
        "property_scope": PROPERTY_SCOPE,
        "asset_count": "0",
        "data_file_count": "0",
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": "1",
        "declared_groups": f"GROUP_STARTUP,{DORMANT_GROUP}",
        "stock_changesets": STOCK_CHANGESET,
        "ipls": GRAPESEED_IPL,
        "native_group_execution_enabled": "true",
        "runtime_ipl_requests_enabled": "true",
        "proximity_activation_enabled": "false",
        "black_transition_required": "true",
        "keep_resident": "true",
        "release_on_exit": "false",
        "gameconfig_changed": "false",
        "native_host_installed": "false",
        "phase_a_canary_id": phase_a.CANARY_ID,
        "phase_a_transaction_id": str(parent["transaction_id"]),
        "phase_a_observation_sha256": str(
            receipt["phase_a_observation_sha256"]
        ),
        "receipt": RUNTIME_RECEIPT_NAME,
        "archive_bytes": str(receipt["archive_bytes"]),
        "archive_sha256": str(receipt["archive_sha256"]),
    }


def _marker_text(receipt: dict[str, Any]) -> str:
    return MARKER_PREAMBLE + "\n" + "".join(
        f"{key}={value}\n" for key, value in _marker_fields(receipt).items()
    )


def _parse_strict_marker(path: Path) -> tuple[dict[str, str] | None, str]:
    try:
        lines = path.read_text(encoding="utf-8").replace("\r", "").split("\n")
    except (OSError, UnicodeError) as exc:
        return None, f"marker unreadable: {exc}"
    if not lines or lines[0] != MARKER_PREAMBLE:
        return None, "marker preamble mismatch"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if "=" not in line:
            return None, "marker line is malformed"
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in fields:
            return None, "marker has an invalid or duplicate field"
        fields[key] = value.strip()
    if set(fields) != MARKER_FIELDS:
        return None, "marker field allowlist mismatch"
    return fields, "verified"


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _receipt_matches_contract(
    payload: object,
    *,
    game: Path,
    archive: Path,
) -> tuple[bool, str]:
    if not isinstance(payload, dict) or set(payload) != RECEIPT_FIELDS:
        return False, "receipt field allowlist mismatch"
    parent = payload.get("phase_a_parent")
    groups = payload.get("groups")
    if (
        not isinstance(parent, dict)
        or set(parent) != PARENT_FIELDS
        or parent.get("canary_id") != phase_a.CANARY_ID
        or not isinstance(parent.get("transaction_id"), str)
        or len(parent["transaction_id"]) != 32
        or not all(_is_sha256(parent.get(key)) for key in (
            "archive_sha256", "marker_sha256", "runtime_receipt_sha256",
        ))
    ):
        return False, "Phase-A parent binding mismatch"
    if (
        not isinstance(groups, list)
        or len(groups) != 1
        or not isinstance(groups[0], dict)
        or set(groups[0]) != GROUP_FIELDS
        or groups[0] != _group_contract()
    ):
        return False, "Grapeseed group contract mismatch"
    expected = _runtime_receipt(
        archive,
        {
            "transaction_id": parent["transaction_id"],
            "archive_sha256": parent["archive_sha256"],
            "marker_sha256": parent["marker_sha256"],
            "runtime_receipt_sha256": parent["runtime_receipt_sha256"],
            "source_attestation": payload.get("source_attestation"),
        },
        str(payload.get("phase_a_observation_sha256")),
    )
    if payload != expected:
        return False, "receipt values mismatch"
    archive_sha256 = phase_a.shared._sha256(archive)
    if (
        payload.get("archive_sha256") != archive_sha256
        or parent.get("archive_sha256") != archive_sha256
        or not _is_sha256(payload.get("phase_a_observation_sha256"))
        or not phase_a._source_attestation_identity_current(
            game, payload.get("source_attestation"),
        )
    ):
        return False, "archive, observation, or source attestation mismatch"
    return True, "verified"


def validate_phase_b_launch_contract(
    gta_path: Path,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Validate bounded live files; registration is a separate tool-backed gate."""
    game = Path(gta_path)
    root = _destination(game)
    archive = root / "dlc.rpf"
    marker = root / MARKER_NAME
    runtime = root / RUNTIME_RECEIPT_NAME
    try:
        if not (game / "GTA5_Enhanced.exe").is_file():
            return False, "Phase B is Enhanced-only", None
        if root.is_symlink() or not root.is_dir():
            return False, "pack root is not a regular directory", None
        entries = {path.name: path for path in root.iterdir()}
        if set(entries) != {"dlc.rpf", MARKER_NAME, RUNTIME_RECEIPT_NAME}:
            return False, "pack files differ from exact three-file layout", None
        if any(path.is_symlink() or not path.is_file() for path in entries.values()):
            return False, "pack contains a non-regular file", None
        if archive.stat().st_size <= 0 or archive.stat().st_size > 4 * 1024 * 1024:
            return False, "metadata archive size is outside the bound", None
        if marker.stat().st_size > 32 * 1024:
            return False, "marker exceeds its size bound", None
        if phase_a._native_map_hosts(game):
            return False, "a native map host is installed", None
        if phase_a._old_pack_paths(game):
            return False, "the retired allin1_maps pack is present", None
        marker_payload, detail = _parse_strict_marker(marker)
        if marker_payload is None:
            return False, detail, None
        runtime_payload = _read_json_object(runtime)
        valid, detail = _receipt_matches_contract(
            runtime_payload, game=game, archive=archive,
        )
        if not valid:
            return False, detail, runtime_payload
        if marker_payload != _marker_fields(runtime_payload):
            return False, "marker values mismatch", runtime_payload
        return True, "verified", runtime_payload
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, str(exc), None


def _extract_current_dlclist_hash(game: Path, patcher: Path) -> str:
    with tempfile.TemporaryDirectory(
        prefix="allin1-grapeseed-phase-b-dlclist-"
    ) as tmp:
        output = Path(tmp) / "dlclist.xml"
        payload = phase_a._current_dlclist(game, patcher, output)
        if phase_a._count_entry(payload, PACK_ENTRY) != 1:
            raise RuntimeError("The Grapeseed bridge registration is not exact.")
        if phase_a._count_entry(payload, phase_a.OLD_PACK_ENTRY) != 0:
            raise RuntimeError("The retired map pack remains registered.")
        return phase_a.shared._sha256(output)


def _registration_checks(
    game: Path, state: Path, patcher: Path,
) -> tuple[dict[str, bool], str | None]:
    del state
    checks = {
        "grapeseed_registration_exact": False,
        "retired_allin1_maps_entry_absent": False,
        "retired_allin1_maps_paths_absent": False,
        "davis_registration_cardinality": False,
        "davis_pack_registration_coherent": False,
        "davis_quarantined_layout": False,
        "native_map_host_absent": False,
        "davis_coexistence_safe": False,
    }
    try:
        with tempfile.TemporaryDirectory(
            prefix="allin1-grapeseed-phase-b-registration-"
        ) as tmp:
            output = Path(tmp) / "dlclist.xml"
            payload = phase_a._current_dlclist(game, patcher, output)
            davis_root = (
                game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
            )
            davis_count = phase_a._count_entry(payload, phase_a.DAVIS_PACK_ENTRY)
            davis_present = (
                davis_root.is_dir() and not davis_root.is_symlink()
            )
            davis_entries = (
                {path.name: path for path in davis_root.iterdir()}
                if davis_present else {}
            )
            expected_davis_files = {
                "dlc.rpf",
                f"{phase_a.DAVIS_PACK_NAME}.active",
                f"{phase_a.DAVIS_PACK_NAME}.runtime.json",
            }
            davis_layout = (
                not davis_present and davis_count == 0
            ) or (
                davis_present
                and davis_count == 1
                and set(davis_entries) == expected_davis_files
                and all(
                    path.is_file() and not path.is_symlink()
                    for path in davis_entries.values()
                )
                and 0 < davis_entries["dlc.rpf"].stat().st_size
                <= 4 * 1024 * 1024
            )
            native_host_absent = not phase_a._native_map_hosts(game)
            davis_stable = (
                davis_count in {0, 1}
                and davis_present == (davis_count == 1)
                and davis_layout
                and native_host_absent
            )
            checks.update({
                "grapeseed_registration_exact": phase_a._count_entry(
                    payload, PACK_ENTRY,
                ) == 1,
                "retired_allin1_maps_entry_absent": phase_a._count_entry(
                    payload, phase_a.OLD_PACK_ENTRY,
                ) == 0,
                "retired_allin1_maps_paths_absent": not phase_a._old_pack_paths(
                    game
                ),
                "davis_registration_cardinality": davis_count in {0, 1},
                "davis_pack_registration_coherent": (
                    davis_present == (davis_count == 1)
                ),
                "davis_quarantined_layout": davis_layout,
                "native_map_host_absent": native_host_absent,
                "davis_coexistence_safe": davis_stable,
            })
            return checks, phase_a.shared._sha256(output)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        return checks, None


def _current_davis_transaction_snapshot(
    game: Path, patcher: Path,
) -> dict[str, Any]:
    """Capture Davis only for immediate before/after noninterference proof."""
    with tempfile.TemporaryDirectory(
        prefix="allin1-grapeseed-phase-b-davis-snapshot-"
    ) as tmp:
        output = Path(tmp) / "dlclist.xml"
        payload = phase_a._current_dlclist(game, patcher, output)
        return phase_a._davis_bridge_snapshot(game, payload)


def validate_phase_b_registration_contract(
    gta_path: Path,
    *,
    patcher: Path | None = None,
    state_root: Path | None = None,
) -> tuple[bool, str, dict[str, bool]]:
    """Validate registration separately from the bounded launch-file contract."""
    try:
        game = phase_a.shared._assert_enhanced_root(Path(gta_path))
        tool = phase_a._tool_path(patcher)
        if not tool.is_file():
            return False, "RpfPatcher is unavailable", {
                "grapeseed_registration_exact": False,
            }
        state = _state_root(game, state_root)
        checks, _dlclist_sha256 = _registration_checks(game, state, tool)
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            return False, "registration checks failed: " + ", ".join(failed), checks
        return True, "verified", checks
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, str(exc), {"grapeseed_registration_exact": False}


def validate_phase_b_launch_registration_contract(
    gta_path: Path,
    *,
    patcher: Path | None = None,
) -> tuple[bool, str, dict[str, bool]]:
    """Validate only launch-critical registration and quarantine state.

    Unlike the developer transaction status, this check is deliberately
    independent from ``state_root`` and from the Davis bridge's lifecycle.
    A legitimate Davis promotion or an unrelated DLC-list edit must not grant
    or revoke Grapeseed authority.  Launch authorization only needs to prove
    that Grapeseed is registered exactly once and that the retired broad map
    route is absent from both the active list and the filesystem.
    """
    checks = {
        "grapeseed_registration_exact": False,
        "retired_allin1_maps_entry_absent": False,
        "retired_allin1_maps_paths_absent": False,
    }
    try:
        game = phase_a.shared._assert_enhanced_root(Path(gta_path))
        tool = phase_a._tool_path(patcher)
        if not tool.is_file():
            return False, "RpfPatcher is unavailable", checks
        with tempfile.TemporaryDirectory(
            prefix="allin1-grapeseed-launch-registration-"
        ) as tmp:
            output = Path(tmp) / "dlclist.xml"
            payload = phase_a._current_dlclist(game, tool, output)
        retired_paths = [
            game / base / "x64/dlcpacks" / phase_a.OLD_PACK_NAME
            for base in ("mods/update", "update")
        ]
        checks.update({
            "grapeseed_registration_exact": phase_a._count_entry(
                payload, PACK_ENTRY,
            ) == 1,
            "retired_allin1_maps_entry_absent": phase_a._count_entry(
                payload, phase_a.OLD_PACK_ENTRY,
            ) == 0,
            "retired_allin1_maps_paths_absent": not any(
                path.exists() or path.is_symlink() for path in retired_paths
            ),
        })
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            return False, "launch registration checks failed: " + ", ".join(
                failed
            ), checks
        return True, "verified", checks
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, str(exc), checks


def _write_promoted_pair(
    state: Path,
    marker: Path,
    runtime: Path,
    journal: dict[str, Any],
    journal_path: Path,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    staged_runtime = runtime.with_name(runtime.name + ".phase-b-new")
    staged_marker = marker.with_name(marker.name + ".phase-b-new")
    try:
        shutil.copy2(state / PHASE_B_RUNTIME_BACKUP, staged_runtime)
        shutil.copy2(state / PHASE_B_MARKER_BACKUP, staged_marker)
        journal["status"] = "promotion_runtime_replace_pending"
        phase_a.shared._write_json_atomic(journal, journal_path)
        replace(staged_runtime, runtime)
        journal["status"] = "promotion_marker_replace_pending"
        phase_a.shared._write_json_atomic(journal, journal_path)
        replace(staged_marker, marker)
        journal["status"] = "promotion_pair_replaced"
        phase_a.shared._write_json_atomic(journal, journal_path)
    finally:
        staged_runtime.unlink(missing_ok=True)
        staged_marker.unlink(missing_ok=True)


def _restore_phase_a_pair(
    state: Path,
    marker: Path,
    runtime: Path,
    journal: dict[str, Any],
    journal_path: Path,
    *,
    operation: str,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    source_marker = state / PHASE_A_MARKER_BACKUP
    source_runtime = state / PHASE_A_RUNTIME_BACKUP
    if not source_marker.is_file() or not source_runtime.is_file():
        raise RuntimeError("The exact Phase-A marker/receipt backup is incomplete.")
    staged_marker = marker.with_name(marker.name + ".phase-a-restore")
    staged_runtime = runtime.with_name(runtime.name + ".phase-a-restore")
    try:
        if phase_a.shared._sha256(runtime) != journal[
            "phase_a_runtime_receipt_sha256"
        ]:
            shutil.copy2(source_runtime, staged_runtime)
            journal["status"] = f"{operation}_runtime_replace_pending"
            phase_a.shared._write_json_atomic(journal, journal_path)
            replace(staged_runtime, runtime)
        if phase_a.shared._sha256(marker) != journal["phase_a_marker_sha256"]:
            shutil.copy2(source_marker, staged_marker)
            journal["status"] = f"{operation}_marker_replace_pending"
            phase_a.shared._write_json_atomic(journal, journal_path)
            replace(staged_marker, marker)
        journal["status"] = f"{operation}_pair_replaced"
        phase_a.shared._write_json_atomic(journal, journal_path)
    finally:
        staged_marker.unlink(missing_ok=True)
        staged_runtime.unlink(missing_ok=True)


def _load_state_receipt(state: Path, name: str) -> dict[str, Any]:
    path = state / name
    if not path.is_file():
        raise FileNotFoundError(f"The Grapeseed Phase-B {name} is missing.")
    return _read_json_object(path)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value.upper() == value
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _load_transaction_journal(state: Path) -> dict[str, Any]:
    journal = _read_json_object(state / "journal.json")
    keys = set(journal)
    if (
        not JOURNAL_REQUIRED_FIELDS.issubset(keys)
        or not keys.issubset(JOURNAL_REQUIRED_FIELDS | JOURNAL_OPTIONAL_FIELDS)
    ):
        raise RuntimeError("The Grapeseed Phase-B journal fields are invalid.")
    transaction_id = journal.get("transaction_id")
    phase_a_transaction_id = journal.get("phase_a_transaction_id")
    if (
        journal.get("schema") != STATE_SCHEMA
        or journal.get("canary_id") != CANARY_ID
        or journal.get("phase") != PHASE
        or journal.get("status") not in JOURNAL_STATUSES
        or not isinstance(transaction_id, str)
        or len(transaction_id) != 32
        or any(character not in "0123456789abcdef" for character in transaction_id)
        or not isinstance(phase_a_transaction_id, str)
        or len(phase_a_transaction_id) != 32
        or any(
            character not in "0123456789abcdef"
            for character in phase_a_transaction_id
        )
    ):
        raise RuntimeError("The Grapeseed Phase-B journal identity is invalid.")
    for field in (
        "phase_a_marker_sha256", "phase_a_runtime_receipt_sha256",
        "phase_b_marker_sha256", "phase_b_runtime_receipt_sha256",
        "archive_sha256", "registered_dlclist_sha256",
        "phase_a_observation_sha256",
    ):
        if not _is_sha256(journal.get(field)):
            raise RuntimeError(
                f"The Grapeseed Phase-B journal {field} is invalid."
            )
    return journal


def _regular_hash(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    return phase_a.shared._sha256(path)


def _transaction_artifact_checks(
    state: Path, journal: dict[str, Any],
) -> dict[str, bool]:
    return {
        "phase_a_marker_backup": _regular_hash(
            state / PHASE_A_MARKER_BACKUP
        ) == journal["phase_a_marker_sha256"],
        "phase_a_runtime_backup": _regular_hash(
            state / PHASE_A_RUNTIME_BACKUP
        ) == journal["phase_a_runtime_receipt_sha256"],
        "phase_b_marker_backup": _regular_hash(
            state / PHASE_B_MARKER_BACKUP
        ) == journal["phase_b_marker_sha256"],
        "phase_b_runtime_backup": _regular_hash(
            state / PHASE_B_RUNTIME_BACKUP
        ) == journal["phase_b_runtime_receipt_sha256"],
    }


def _live_pair_state(
    marker: Path, runtime: Path, journal: dict[str, Any],
) -> tuple[str, dict[str, str | None]]:
    hashes = {
        "marker": _regular_hash(marker),
        "runtime_receipt": _regular_hash(runtime),
    }
    marker_generation = (
        "phase_a" if hashes["marker"] == journal["phase_a_marker_sha256"]
        else "phase_b" if hashes["marker"] == journal["phase_b_marker_sha256"]
        else "drift"
    )
    runtime_generation = (
        "phase_a"
        if hashes["runtime_receipt"]
        == journal["phase_a_runtime_receipt_sha256"]
        else "phase_b"
        if hashes["runtime_receipt"]
        == journal["phase_b_runtime_receipt_sha256"]
        else "drift"
    )
    if "drift" in {marker_generation, runtime_generation}:
        state = "drifted"
    elif marker_generation == runtime_generation:
        state = marker_generation
    else:
        state = "mixed_known"
    return state, hashes


def _immutable_checks(
    game: Path, state: Path, patcher: Path, journal: dict[str, Any],
) -> dict[str, bool]:
    archive = _destination(game) / "dlc.rpf"
    try:
        archive_ok = _regular_hash(archive) == journal["archive_sha256"]
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        archive_ok = False
    registration_checks, _dlclist_sha256 = _registration_checks(
        game, state, patcher,
    )
    return {
        "archive_unchanged": archive_ok,
        **registration_checks,
    }


def _assert_recovery_safe(
    game: Path,
    state: Path,
    patcher: Path,
    journal: dict[str, Any],
) -> str:
    artifact_checks = _transaction_artifact_checks(state, journal)
    if not all(artifact_checks.values()):
        failed = ", ".join(
            name for name, ok in artifact_checks.items() if not ok
        )
        raise RuntimeError(
            "The Grapeseed Phase-B recovery artifacts drifted: " + failed
        )
    marker = _destination(game) / MARKER_NAME
    runtime = _destination(game) / RUNTIME_RECEIPT_NAME
    pair_state, _hashes = _live_pair_state(marker, runtime, journal)
    if pair_state == "drifted":
        raise RuntimeError(
            "The live Grapeseed marker/receipt contains unknown drift; "
            "recovery refuses to overwrite it."
        )
    immutable_checks = _immutable_checks(game, state, patcher, journal)
    if not all(immutable_checks.values()):
        failed = ", ".join(
            name for name, ok in immutable_checks.items() if not ok
        )
        raise RuntimeError(
            "The Grapeseed Phase-B immutable inputs drifted: " + failed
        )
    return pair_state


def _rollback_result(expectations: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": expectations.get("transaction_id"),
        "status": "rolled_back_to_phase_a",
        "restored_phase_a_transaction_id": expectations.get(
            "phase_a_transaction_id"
        ),
        "restored_marker_sha256": expectations.get("phase_a_marker_sha256"),
        "restored_runtime_receipt_sha256": expectations.get(
            "phase_a_runtime_receipt_sha256"
        ),
    }


def _transaction_status_checks(
    game: Path,
    state: Path,
    patcher: Path,
    journal: dict[str, Any],
) -> tuple[str, dict[str, bool]]:
    destination = _destination(game)
    pair_state, _hashes = _live_pair_state(
        destination / MARKER_NAME,
        destination / RUNTIME_RECEIPT_NAME,
        journal,
    )
    checks = {
        "journal": True,
        **_transaction_artifact_checks(state, journal),
        "live_pair_known": pair_state != "drifted",
        **_immutable_checks(game, state, patcher, journal),
    }
    return pair_state, checks


def promote_grapeseed_stock_reference_black_transition_canary(
    gta_path: Path,
    *,
    confirmation: str,
    session: str,
    state_root: Path | None = None,
    phase_a_state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = phase_a.shared._default_process_names,
    replace: Callable[[Path, Path], None] = os.replace,
) -> dict[str, Any]:
    if confirmation != PROMOTE_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {PROMOTE_CONFIRMATION!r} is required."
        )
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    phase_a.shared._assert_game_closed(process_probe)
    tool = phase_a._tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    state = _state_root(game, state_root)
    if (state / "promotion-receipt.json").is_file():
        existing = _load_state_receipt(state, "promotion-receipt.json")
        status = read_grapeseed_stock_reference_black_transition_canary_status(
            game, state_root=state, phase_a_state_root=phase_a_state_root,
            patcher=tool, process_probe=process_probe,
        )
        if status.get("healthy") is True:
            return existing
        raise RuntimeError("The existing Grapeseed Phase-B promotion drifted.")
    prejournal_state = state.exists() and not (state / "journal.json").is_file()
    if state.exists() and not prejournal_state:
        raise RuntimeError(
            f"A Grapeseed Phase-B checkpoint already exists at {state}."
        )

    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    phase_a_receipt_path = phase_a_state / "install-receipt.json"
    phase_a_status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=phase_a_state, patcher=tool,
        process_probe=process_probe,
    )
    if (
        phase_a_status.get("status") != phase_a.INSTALL_STATUS
        or phase_a_status.get("healthy") is not True
        or not all(phase_a_status.get("checks", {}).values())
    ):
        raise RuntimeError("An exact healthy active Grapeseed Phase A is required.")
    if prejournal_state:
        _discard_owned_prejournal_state(state)
    phase_a_receipt = _read_json_object(phase_a_receipt_path)
    observation = inspect_phase_a_session_evidence(
        game, session=session, phase_a_receipt=phase_a_receipt,
        phase_a_receipt_path=phase_a_receipt_path,
    )
    observation_sha256 = _canonical_json_sha256(observation)

    destination = _destination(game)
    archive = destination / "dlc.rpf"
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    registration_checks, registered_hash = _registration_checks(
        game, state, tool,
    )
    failed_registration = [
        name for name, passed in registration_checks.items() if not passed
    ]
    if registered_hash is None or failed_registration:
        raise RuntimeError(
            "The current Grapeseed promotion registration baseline is unsafe: "
            + ", ".join(failed_registration or ["dlclist_unreadable"])
        )
    davis_transaction_snapshot = _current_davis_transaction_snapshot(
        game, tool,
    )
    archive_hash = phase_a.shared._sha256(archive)
    if archive_hash != phase_a_receipt.get("archive_sha256"):
        raise RuntimeError("The Grapeseed Phase-A metadata archive drifted.")

    state.mkdir(parents=True)
    journal_path = state / "journal.json"
    transaction_id = uuid.uuid4().hex
    shutil.copy2(marker, state / PHASE_A_MARKER_BACKUP)
    shutil.copy2(runtime, state / PHASE_A_RUNTIME_BACKUP)
    shutil.copy2(phase_a_receipt_path, state / "phase-a-install-receipt.json")
    phase_a.shared._write_json_atomic(
        observation, state / "phase-a-observation.json",
    )
    promoted = _runtime_receipt(archive, phase_a_receipt, observation_sha256)
    phase_a.shared._write_json_atomic(
        promoted, state / PHASE_B_RUNTIME_BACKUP,
    )
    phase_a.shared._write_text_atomic(
        _marker_text(promoted), state / PHASE_B_MARKER_BACKUP,
    )
    journal: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": transaction_id,
        "status": "prepared",
        "phase": PHASE,
        "phase_a_transaction_id": phase_a_receipt.get("transaction_id"),
        "phase_a_marker_sha256": phase_a.shared._sha256(
            state / PHASE_A_MARKER_BACKUP
        ),
        "phase_a_runtime_receipt_sha256": phase_a.shared._sha256(
            state / PHASE_A_RUNTIME_BACKUP
        ),
        "phase_b_marker_sha256": phase_a.shared._sha256(
            state / PHASE_B_MARKER_BACKUP
        ),
        "phase_b_runtime_receipt_sha256": phase_a.shared._sha256(
            state / PHASE_B_RUNTIME_BACKUP
        ),
        "archive_sha256": archive_hash,
        "registered_dlclist_sha256": registered_hash,
        "phase_a_observation_sha256": observation_sha256,
    }
    phase_a.shared._write_json_atomic(journal, journal_path)
    if not all(_transaction_artifact_checks(state, journal).values()):
        raise RuntimeError(
            "The Grapeseed Phase-B transaction checkpoint failed verification."
        )
    mutated = False
    try:
        mutated = True
        _write_promoted_pair(
            state, marker, runtime, journal, journal_path, replace=replace,
        )
        pair_state, _hashes = _live_pair_state(marker, runtime, journal)
        if pair_state != "phase_b":
            raise RuntimeError(
                "The promoted Grapeseed Phase-B pair is not internally exact."
            )
        valid, detail, live_receipt = validate_phase_b_launch_contract(game)
        if not valid or live_receipt != promoted:
            raise RuntimeError(
                f"The promoted Grapeseed Phase-B contract failed: {detail}"
            )
        post_registration_checks, post_registered_hash = _registration_checks(
            game, state, tool,
        )
        if (
            not all(post_registration_checks.values())
            or post_registered_hash != registered_hash
        ):
            raise RuntimeError("Grapeseed Phase-B promotion changed dlclist.xml.")
        if phase_a.shared._sha256(archive) != archive_hash:
            raise RuntimeError("Grapeseed Phase-B promotion changed the archive.")
        if (
            _current_davis_transaction_snapshot(game, tool)
            != davis_transaction_snapshot
        ):
            raise RuntimeError(
                "Davis changed during the Grapeseed Phase-B promotion."
            )
        receipt = {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": transaction_id,
            "status": MARKER_STATUS,
            "phase": PHASE,
            "phase_a_transaction_id": phase_a_receipt.get("transaction_id"),
            "phase_a_install_receipt_sha256": phase_a.shared._sha256(
                phase_a_receipt_path,
            ),
            "phase_a_marker_sha256": journal["phase_a_marker_sha256"],
            "phase_a_runtime_receipt_sha256": journal[
                "phase_a_runtime_receipt_sha256"
            ],
            "phase_a_observation_sha256": observation_sha256,
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": archive_hash,
            "registered_dlclist_sha256": registered_hash,
            "phase_b_marker_sha256": journal["phase_b_marker_sha256"],
            "phase_b_runtime_receipt_sha256": journal[
                "phase_b_runtime_receipt_sha256"
            ],
        }
        phase_a.shared._write_json_atomic(
            receipt, state / "promotion-receipt.json",
        )
        journal["status"] = "promotion_complete"
        phase_a.shared._write_json_atomic(journal, journal_path)
        return receipt
    except Exception as promotion_error:
        if mutated:
            try:
                _assert_recovery_safe(game, state, tool, journal)
                recovery_dlclist_sha256 = _extract_current_dlclist_hash(
                    game, tool,
                )
                _restore_phase_a_pair(
                    state, marker, runtime, journal, journal_path,
                    operation="promotion_recovery", replace=replace,
                )
                restored, _detail, _runtime = (
                    phase_a.validate_phase_a_launch_contract(game)
                )
                registration_checks, _registration_sha256 = (
                    _registration_checks(game, state, tool)
                )
                if not restored or not all(registration_checks.values()):
                    raise RuntimeError("restored Grapeseed Phase A did not verify")
                if (
                    _extract_current_dlclist_hash(game, tool)
                    != recovery_dlclist_sha256
                    or phase_a.shared._sha256(archive) != archive_hash
                ):
                    raise RuntimeError(
                        "automatic recovery changed the archive or dlclist"
                    )
            except Exception as recovery_error:
                journal.update({
                    "status": "recovery_required",
                    "promotion_error": type(promotion_error).__name__,
                    "recovery_error": str(recovery_error),
                })
                phase_a.shared._write_json_atomic(journal, journal_path)
                raise RuntimeError(
                    "Grapeseed Phase-B promotion and automatic Phase-A "
                    f"restoration failed: {recovery_error}"
                ) from promotion_error
        shutil.rmtree(state, ignore_errors=True)
        raise


def _verify_rolled_back(
    game: Path,
    state: Path,
    phase_a_state: Path,
    patcher: Path,
    process_probe: Callable[[], set[str]],
) -> tuple[dict[str, Any], dict[str, bool]]:
    journal = _load_transaction_journal(state)
    promotion_path = state / "promotion-receipt.json"
    promotion = (
        _load_state_receipt(state, "promotion-receipt.json")
        if promotion_path.is_file()
        else journal
    )
    rollback = _load_state_receipt(state, "rollback-receipt.json")
    del phase_a_state, process_probe
    phase_a_valid, _phase_a_detail, _phase_a_runtime = (
        phase_a.validate_phase_a_launch_contract(game)
    )
    expected = _rollback_result(promotion)
    destination = _destination(game)
    immutable_checks = _immutable_checks(game, state, patcher, journal)
    checks = {
        "rollback_receipt": rollback == expected,
        "phase_a_launch_contract": phase_a_valid,
        "phase_a_marker_restored": phase_a.shared._sha256(
            destination / MARKER_NAME,
        ) == promotion.get("phase_a_marker_sha256"),
        "phase_a_runtime_receipt_restored": phase_a.shared._sha256(
            destination / RUNTIME_RECEIPT_NAME,
        ) == promotion.get("phase_a_runtime_receipt_sha256"),
        **immutable_checks,
    }
    return rollback, checks


def rollback_grapeseed_stock_reference_black_transition_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    phase_a_state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = phase_a.shared._default_process_names,
    replace: Callable[[Path, Path], None] = os.replace,
) -> dict[str, Any]:
    if confirmation != ROLLBACK_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {ROLLBACK_CONFIRMATION!r} is required."
        )
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    phase_a.shared._assert_game_closed(process_probe)
    state = _state_root(game, state_root)
    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    tool = phase_a._tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    if state.exists() and not (state / "journal.json").is_file():
        prior = phase_a.read_grapeseed_stock_reference_boot_canary_status(
            game, state_root=phase_a_state, patcher=tool,
            process_probe=process_probe,
        )
        if (
            prior.get("status") != phase_a.INSTALL_STATUS
            or prior.get("healthy") is not True
            or not all(prior.get("checks", {}).values())
        ):
            raise RuntimeError(
                "The journal-less Grapeseed Phase-B checkpoint does not have "
                "an exact healthy Phase-A baseline."
            )
        _discard_owned_prejournal_state(state)
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": None,
            "status": "discarded_pre_mutation_checkpoint",
            "restored_phase_a_transaction_id": prior.get("transaction_id"),
        }
    if (state / "rollback-receipt.json").is_file():
        payload, checks = _verify_rolled_back(
            game, state, phase_a_state, tool, process_probe,
        )
        if not all(checks.values()):
            failed = ", ".join(name for name, ok in checks.items() if not ok)
            raise RuntimeError(f"The Grapeseed Phase-B rollback drifted: {failed}")
        return payload
    journal_path = state / "journal.json"
    journal = _load_transaction_journal(state)
    promotion_path = state / "promotion-receipt.json"
    promotion = (
        _load_state_receipt(state, "promotion-receipt.json")
        if promotion_path.is_file()
        else journal
    )
    destination = _destination(game)
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    _assert_recovery_safe(game, state, tool, journal)
    rollback_dlclist_sha256 = _extract_current_dlclist_hash(game, tool)
    davis_transaction_snapshot = _current_davis_transaction_snapshot(
        game, tool,
    )
    journal["status"] = "rollback_started"
    journal.pop("promotion_error", None)
    journal.pop("recovery_error", None)
    phase_a.shared._write_json_atomic(journal, journal_path)
    try:
        _restore_phase_a_pair(
            state, marker, runtime, journal, journal_path,
            operation="rollback", replace=replace,
        )
        restored, _detail, _runtime = phase_a.validate_phase_a_launch_contract(
            game
        )
        if not restored:
            raise RuntimeError("The restored Grapeseed Phase A failed validation.")
        immutable_checks = _immutable_checks(game, state, tool, journal)
        if not all(immutable_checks.values()):
            raise RuntimeError(
                "The archive or dlclist changed during Grapeseed rollback."
            )
        if _extract_current_dlclist_hash(game, tool) != rollback_dlclist_sha256:
            raise RuntimeError("Grapeseed rollback changed dlclist.xml.")
        if (
            _current_davis_transaction_snapshot(game, tool)
            != davis_transaction_snapshot
        ):
            raise RuntimeError("Davis changed during Grapeseed rollback.")
    except Exception as exc:
        journal["status"] = "recovery_required"
        journal["recovery_error"] = str(exc)
        phase_a.shared._write_json_atomic(journal, journal_path)
        raise
    result = _rollback_result(promotion)
    phase_a.shared._write_json_atomic(result, state / "rollback-receipt.json")
    journal["status"] = "rollback_complete"
    journal.pop("recovery_error", None)
    phase_a.shared._write_json_atomic(journal, journal_path)
    return result


def read_grapeseed_stock_reference_black_transition_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    phase_a_state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = phase_a.shared._default_process_names,
) -> dict[str, Any]:
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    running = bool(
        {name.casefold() for name in process_probe()}.intersection(
            {"gta5.exe", "gta5_enhanced.exe"}
        )
    )
    state = _state_root(game, state_root)
    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    tool = phase_a._tool_path(patcher)
    if not state.exists():
        valid, _detail, _payload = validate_phase_b_launch_contract(game)
        if valid:
            status, healthy = "unmanaged", False
        else:
            try:
                prior = phase_a.read_grapeseed_stock_reference_boot_canary_status(
                    game, state_root=phase_a_state, patcher=tool,
                    process_probe=process_probe,
                )
                ready = (
                    prior.get("status") == phase_a.INSTALL_STATUS
                    and prior.get("healthy") is True
                    and all(prior.get("checks", {}).values())
                )
            except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
                ready = False
            present = _destination(game).exists()
            status = "promotion_ready" if ready else (
                "unmanaged" if present else "absent"
            )
            healthy = ready or not present
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": status,
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": healthy,
        }
    if (state / "rollback-receipt.json").is_file():
        try:
            payload, checks = _verify_rolled_back(
                game, state, phase_a_state, tool, process_probe,
            )
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            payload, checks = {}, {"rollback_receipt": False}
        return {
            **payload,
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "rolled_back_to_phase_a",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": all(checks.values()),
            "checks": checks,
        }
    if not (state / "promotion-receipt.json").is_file():
        if not (state / "journal.json").is_file():
            try:
                _owned_prejournal_entries(state)
                prior = (
                    phase_a.read_grapeseed_stock_reference_boot_canary_status(
                        game, state_root=phase_a_state, patcher=tool,
                        process_probe=process_probe,
                    )
                )
                phase_a_ready = (
                    prior.get("status") == phase_a.INSTALL_STATUS
                    and prior.get("healthy") is True
                    and all(prior.get("checks", {}).values())
                )
            except (
                FileNotFoundError, OSError, RuntimeError, TypeError, ValueError,
            ):
                phase_a_ready = False
            return {
                "schema": STATE_SCHEMA,
                "canary_id": CANARY_ID,
                "status": (
                    "pre_mutation" if phase_a_ready
                    else "promotion_interrupted_unrecoverable"
                ),
                "journal_status": None,
                "live_pair_state": "phase_a" if phase_a_ready else "unknown",
                "phase": PHASE,
                "edition": "enhanced",
                "game_running": running,
                "healthy": False,
                "recoverable": phase_a_ready,
                "checks": {
                    "prejournal_artifacts_owned": phase_a_ready,
                    "phase_a_baseline_ready": phase_a_ready,
                },
                "recovery_action": (
                    "Retry promotion or run the guarded Grapeseed Phase-B "
                    "rollback while GTA is closed."
                    if phase_a_ready else None
                ),
            }
        try:
            journal = _load_transaction_journal(state)
            pair_state, checks = _transaction_status_checks(
                game, state, tool, journal,
            )
            recoverable = all(checks.values())
            status = (
                "promotion_interrupted_recoverable"
                if recoverable
                else "promotion_interrupted_drifted"
            )
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            journal = {}
            pair_state = "unknown"
            checks = {"journal": False}
            status = "promotion_interrupted_unrecoverable"
            recoverable = False
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": status,
            "journal_status": journal.get("status"),
            "live_pair_state": pair_state,
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
            "recoverable": recoverable,
            "checks": checks,
            "recovery_action": (
                "Run the guarded Grapeseed Phase-B rollback while GTA is closed."
                if recoverable else None
            ),
        }
    try:
        journal = _load_transaction_journal(state)
        pair_state, transaction_checks = _transaction_status_checks(
            game, state, tool, journal,
        )
        if journal.get("status") != "promotion_complete" or pair_state != "phase_b":
            recoverable = all(transaction_checks.values())
            status = (
                "rollback_interrupted_recoverable"
                if journal.get("status") in ROLLBACK_IN_PROGRESS_STATUSES
                and recoverable
                else "transaction_interrupted_recoverable"
                if recoverable
                else "transaction_interrupted_drifted"
            )
            return {
                "schema": STATE_SCHEMA,
                "canary_id": CANARY_ID,
                "status": status,
                "journal_status": journal.get("status"),
                "live_pair_state": pair_state,
                "phase": PHASE,
                "edition": "enhanced",
                "game_running": running,
                "healthy": False,
                "recoverable": recoverable,
                "checks": transaction_checks,
                "recovery_action": (
                    "Run the guarded Grapeseed Phase-B rollback while GTA is closed."
                    if recoverable else None
                ),
            }
        promotion = _load_state_receipt(state, "promotion-receipt.json")
        observation = _read_json_object(state / "phase-a-observation.json")
        observation_ok = (
            set(observation) == OBSERVATION_FIELDS
            and _canonical_json_sha256(observation)
            == promotion.get("phase_a_observation_sha256")
        )
        valid, detail, runtime = validate_phase_b_launch_contract(game)
        destination = _destination(game)
        archive = destination / "dlc.rpf"
        marker = destination / MARKER_NAME
        receipt = destination / RUNTIME_RECEIPT_NAME
        registration_ok, registration_detail, registration_checks = (
            validate_phase_b_registration_contract(
                game, patcher=tool, state_root=state,
            )
        )
        checks = {
            "transaction_journal": all(transaction_checks.values()),
            "launch_contract": valid,
            "registration_contract": registration_ok,
            **registration_checks,
            "phase_a_observation": observation_ok,
            "archive_unchanged": archive.is_file()
            and phase_a.shared._sha256(archive) == promotion.get("archive_sha256"),
            "marker": marker.is_file()
            and phase_a.shared._sha256(marker)
            == promotion.get("phase_b_marker_sha256"),
            "runtime_receipt": receipt.is_file()
            and phase_a.shared._sha256(receipt)
            == promotion.get("phase_b_runtime_receipt_sha256"),
        }
        if valid and not registration_ok:
            detail = registration_detail
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        promotion, runtime, detail = {}, None, "status verification failed"
        checks = {"promotion_receipt": False}
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": promotion.get("status", MARKER_STATUS),
        "phase": PHASE,
        "edition": "enhanced",
        "game_running": running,
        "healthy": all(checks.values()),
        "checks": checks,
        "detail": detail,
        "pack_name": PACK_NAME,
        "device_name": DEVICE_NAME,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "activation": ACTIVATION,
        "runtime_receipt": runtime,
    }
