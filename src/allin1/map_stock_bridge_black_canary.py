"""Phase-B black-transition promotion for the Enhanced Davis bridge.

Phase B does not rebuild or re-register the Phase-A metadata archive.  It
promotes the exact, observed Phase-A installation by replacing only its
marker and runtime receipt.  The in-game runtime may then execute one fixed
Rockstar changeset group for an explicit Davis garage entry while a black
transition is held.  Proximity activation and arbitrary groups/IPLs remain
outside this contract.
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

from allin1 import map_stock_bridge_canary as phase_a


CANARY_ID = "davis-enhanced-stock-reference-black-transition-v1"
PROMOTE_CONFIRMATION = (
    "PROMOTE_DAVIS_ENHANCED_STOCK_REFERENCE_BLACK_TRANSITION_V1"
)
ROLLBACK_CONFIRMATION = (
    "ROLLBACK_DAVIS_ENHANCED_STOCK_REFERENCE_BLACK_TRANSITION_V1"
)
STATE_SCHEMA = 5
STATE_DIRECTORY = "DavisStockReferenceBlackTransitionV1"

PHASE = "phase-b-black-transition"
MARKER_STATUS = "installed_black_transition_pending_test"
RUNTIME_STATUS = "verified"
LAYOUT = phase_a.LAYOUT
RUNTIME_CONTRACT = "allin1-stock-mptuner-davis-black-transition-v1"
ACTIVATION = "explicit-davis-entry-black-transition"
ACTIVATION_SCOPE = "garage-entry-only"
PROPERTY_SCOPE = "davis"
DAVIS_IPL = "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"
MARKER_PREAMBLE = (
    "ALLIN1 stock mptuner Phase-B black-transition bridge; "
    "Davis garage-entry activation only."
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
    "pack_name", "device_name", "edition", "layout",
    "runtime_contract", "archive_registration", "activation",
    "activation_scope", "property_scope", "asset_count",
    "data_file_count", "startup_changeset", "dormant_group_count",
    "declared_groups", "stock_changesets", "ipls", "groups",
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
    "session_event_count", "blocked_event_count",
    "survival_after_last_block_ms", "error_count", "fatal_count",
    "game_closed", "session_lock_absent", "operator_confirmed",
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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"JSON evidence is unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON evidence is not an object: {path.name}")
    return payload


def _exact_block_event(event: dict[str, Any]) -> bool:
    return (
        event.get("component") == "DeferredMap"
        and event.get("message") ==
        "davis_phase_a_runtime_activation_blocked"
        and event.get("property") == "davis"
        and event.get("request_source") == "proximity_zone"
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
    """Validate and summarize one completed Phase-A Story Mode session."""
    if (
        len(session) != 12
        or session.casefold() != session
        or any(character not in "0123456789abcdef" for character in session)
    ):
        raise ValueError("The Phase-A session must be exactly 12 lowercase hex digits.")
    log = game / CLIENT_LOG_RELATIVE
    if not log.is_file():
        raise FileNotFoundError("The Phase-A ALLIN1 client log is missing.")
    if (game / SESSION_LOCK_RELATIVE).exists():
        raise RuntimeError(
            "The ALLIN1 session lock still exists; a clean Phase-A shutdown "
            "has not been observed."
        )
    raw = log.read_bytes()
    if len(raw) > 16 * 1024 * 1024:
        raise RuntimeError("The Phase-A client log exceeds the bounded evidence limit.")

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
        raise RuntimeError(
            "Phase-A evidence must contain exactly one matching session start."
        )
    timed: list[tuple[dict[str, Any], datetime]] = []
    for event in events:
        timestamp = _parse_utc(event.get("ts"))
        if timestamp is None:
            raise RuntimeError("Phase-A session evidence has an invalid timestamp.")
        timed.append((event, timestamp))
    started = _parse_utc(starts[0].get("ts"))
    if started is None:
        raise RuntimeError("The Phase-A session start timestamp is invalid.")
    installed = datetime.fromtimestamp(
        phase_a_receipt_path.stat().st_mtime, tz=timezone.utc,
    )
    if started <= installed:
        raise RuntimeError(
            "The selected session predates the active Phase-A installation."
        )

    blocks = [(event, stamp) for event, stamp in timed if _exact_block_event(event)]
    if not blocks:
        raise RuntimeError(
            "The selected session never exercised the exact Phase-A Davis guard."
        )
    ended = max(stamp for _event, stamp in timed)
    last_block = max(stamp for _event, stamp in blocks)
    survived_ms = int((ended - last_block).total_seconds() * 1000)
    if survived_ms < MINIMUM_POST_BLOCK_SURVIVAL_MS:
        raise RuntimeError(
            "The selected session did not survive the Davis guard long enough."
        )
    errors = sum(event.get("level") == "ERROR" for event, _stamp in timed)
    fatals = sum(event.get("level") == "FATAL" for event, _stamp in timed)
    if errors or fatals:
        raise RuntimeError(
            "The selected Phase-A session contains ERROR or FATAL events."
        )

    transaction_id = phase_a_receipt.get("transaction_id")
    if not isinstance(transaction_id, str) or len(transaction_id) != 32:
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
        "ipls": [DAVIS_IPL],
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
    return {
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
        "ipls": [DAVIS_IPL],
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
        "ipls": DAVIS_IPL,
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
        "phase_a_observation_sha256": receipt[
            "phase_a_observation_sha256"
        ],
        "receipt": RUNTIME_RECEIPT_NAME,
        "archive_bytes": str(receipt["archive_bytes"]),
        "archive_sha256": receipt["archive_sha256"],
    }


def _marker_text(receipt: dict[str, Any]) -> str:
    fields = _marker_fields(receipt)
    return MARKER_PREAMBLE + "\n" + "".join(
        f"{key}={value}\n" for key, value in fields.items()
    )


def _parse_strict_marker(path: Path) -> tuple[dict[str, str] | None, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"marker unreadable: {exc}"
    lines = raw.replace("\r", "").split("\n")
    if not lines or lines[0] != MARKER_PREAMBLE:
        return None, "marker preamble mismatch"
    result: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        separator = line.find("=")
        if separator <= 0:
            return None, "marker line is malformed"
        key = line[:separator].strip()
        value = line[separator + 1:].strip()
        if key in result:
            return None, f"duplicate marker field: {key}"
        result[key] = value
    if set(result) != MARKER_FIELDS:
        return None, "marker field allowlist mismatch"
    return result, "verified"


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
        return False, "Davis group contract mismatch"
    archive_sha256 = phase_a.shared._sha256(archive)
    expected = {
        **_runtime_receipt(
            archive,
            {
                "transaction_id": parent["transaction_id"],
                "archive_sha256": parent["archive_sha256"],
                "marker_sha256": parent["marker_sha256"],
                "runtime_receipt_sha256": parent["runtime_receipt_sha256"],
                "source_attestation": payload.get("source_attestation"),
            },
            str(payload.get("phase_a_observation_sha256")),
        ),
    }
    if payload != expected:
        return False, "receipt values mismatch"
    if (
        payload.get("archive_sha256") != archive_sha256
        or parent.get("archive_sha256") != archive_sha256
        or not _is_sha256(payload.get("phase_a_observation_sha256"))
        or not phase_a._source_attestation_current(
            game, payload.get("source_attestation"),
        )
    ):
        return False, "archive, observation, or source attestation mismatch"
    return True, "verified"


def validate_phase_b_launch_contract(
    gta_path: Path,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Bounded launch-time verification independent from local state."""
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
        hosts = phase_a._native_map_hosts(game)
        if hosts:
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
    mods_archive = game / "mods/update/update.rpf"
    with tempfile.TemporaryDirectory(prefix="allin1-phase-b-dlclist-") as tmp:
        output = Path(tmp) / "dlclist.xml"
        payload = phase_a.shared._extract_dlclist(
            patcher, game, mods_archive, output,
        )
        if phase_a._count_entry(payload, PACK_ENTRY) != 1:
            raise RuntimeError("The stock bridge registration is not exact.")
        if phase_a._count_entry(payload, phase_a.OLD_PACK_ENTRY) != 0:
            raise RuntimeError("The retired map pack remains registered.")
        return phase_a.shared._sha256(output)


def _write_promoted_pair(
    marker: Path,
    runtime: Path,
    receipt_payload: dict[str, Any],
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    staged_runtime = runtime.with_name(runtime.name + ".phase-b-new")
    staged_marker = marker.with_name(marker.name + ".phase-b-new")
    try:
        phase_a.shared._write_json_atomic(receipt_payload, staged_runtime)
        phase_a.shared._write_text_atomic(
            _marker_text(receipt_payload), staged_marker,
        )
        replace(staged_runtime, runtime)
        replace(staged_marker, marker)
    finally:
        staged_runtime.unlink(missing_ok=True)
        staged_marker.unlink(missing_ok=True)


def _restore_phase_a_pair(
    state: Path,
    marker: Path,
    runtime: Path,
    *,
    replace: Callable[[Path, Path], None] = os.replace,
) -> None:
    backup_marker = state / "phase-a-marker"
    backup_runtime = state / "phase-a-runtime.json"
    if not backup_marker.is_file() or not backup_runtime.is_file():
        raise RuntimeError("The Phase-A marker/receipt backup is incomplete.")
    staged_runtime = runtime.with_name(runtime.name + ".phase-a-restore")
    staged_marker = marker.with_name(marker.name + ".phase-a-restore")
    try:
        shutil.copy2(backup_runtime, staged_runtime)
        shutil.copy2(backup_marker, staged_marker)
        replace(staged_runtime, runtime)
        replace(staged_marker, marker)
    finally:
        staged_runtime.unlink(missing_ok=True)
        staged_marker.unlink(missing_ok=True)


def _load_state_receipt(state: Path, name: str) -> dict[str, Any]:
    payload = _read_json_object(state / name)
    if payload.get("schema") != STATE_SCHEMA or payload.get("canary_id") != CANARY_ID:
        raise RuntimeError("The Phase-B state receipt identity is invalid.")
    return payload


def promote_davis_stock_reference_black_transition_canary(
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
    """Promote an observed, exact Phase-A install without rebuilding it."""
    if confirmation != PROMOTE_CONFIRMATION:
        raise PermissionError(f"Exact confirmation {PROMOTE_CONFIRMATION!r} is required.")
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    phase_a.shared._assert_game_closed(process_probe)
    tool = phase_a._tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")

    state = _state_root(game, state_root)
    if (state / "promotion-receipt.json").is_file():
        existing = _load_state_receipt(state, "promotion-receipt.json")
        status = read_davis_stock_reference_black_transition_canary_status(
            game, state_root=state, phase_a_state_root=phase_a_state_root,
            patcher=tool, process_probe=process_probe,
        )
        if status.get("healthy"):
            return existing
        raise RuntimeError("The existing Phase-B promotion no longer verifies.")
    if state.exists():
        raise RuntimeError(
            f"A Phase-B checkpoint already exists at {state}; inspect or roll it back first."
        )

    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    phase_a_receipt_path = phase_a_state / "install-receipt.json"
    phase_a_status = phase_a.read_davis_stock_reference_boot_canary_status(
        game, state_root=phase_a_state, patcher=tool,
        process_probe=process_probe,
    )
    if (
        phase_a_status.get("status") != phase_a.INSTALL_STATUS
        or phase_a_status.get("healthy") is not True
        or not all(phase_a_status.get("checks", {}).values())
    ):
        raise RuntimeError("An exact healthy active Phase-A checkpoint is required.")
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
    registered_hash = _extract_current_dlclist_hash(game, tool)
    archive_hash = phase_a.shared._sha256(archive)
    if archive_hash != phase_a_receipt.get("archive_sha256"):
        raise RuntimeError("The Phase-A metadata archive drifted.")

    state.mkdir(parents=True)
    journal_path = state / "journal.json"
    transaction_id = uuid.uuid4().hex
    journal: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": transaction_id,
        "status": "ready_to_mutate",
        "phase": PHASE,
        "phase_a_transaction_id": phase_a_receipt.get("transaction_id"),
        "phase_a_marker_sha256": phase_a.shared._sha256(marker),
        "phase_a_runtime_receipt_sha256": phase_a.shared._sha256(runtime),
        "archive_sha256": archive_hash,
        "registered_dlclist_sha256": registered_hash,
        "phase_a_observation_sha256": observation_sha256,
    }
    phase_a.shared._write_json_atomic(journal, journal_path)
    shutil.copy2(marker, state / "phase-a-marker")
    shutil.copy2(runtime, state / "phase-a-runtime.json")
    shutil.copy2(phase_a_receipt_path, state / "phase-a-install-receipt.json")
    phase_a.shared._write_json_atomic(observation, state / "phase-a-observation.json")
    promoted = _runtime_receipt(archive, phase_a_receipt, observation_sha256)

    mutated = False
    try:
        journal["status"] = "mutation_started"
        phase_a.shared._write_json_atomic(journal, journal_path)
        mutated = True
        _write_promoted_pair(
            marker, runtime, promoted, replace=replace,
        )
        journal.update({
            "status": "promoted",
            "phase_b_marker_sha256": phase_a.shared._sha256(marker),
            "phase_b_runtime_receipt_sha256": phase_a.shared._sha256(runtime),
        })
        phase_a.shared._write_json_atomic(journal, journal_path)

        valid, detail, live_receipt = validate_phase_b_launch_contract(game)
        if not valid or live_receipt != promoted:
            raise RuntimeError(f"The promoted Phase-B contract failed verification: {detail}")
        if _extract_current_dlclist_hash(game, tool) != registered_hash:
            raise RuntimeError("Phase-B promotion changed dlclist.xml.")
        if phase_a.shared._sha256(archive) != archive_hash:
            raise RuntimeError("Phase-B promotion changed the DLC archive.")

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
        phase_a.shared._write_json_atomic(receipt, state / "promotion-receipt.json")
        return receipt
    except Exception as promotion_error:
        if mutated:
            try:
                _restore_phase_a_pair(
                    state, marker, runtime, replace=replace,
                )
                restored = phase_a.read_davis_stock_reference_boot_canary_status(
                    game, state_root=phase_a_state, patcher=tool,
                    process_probe=process_probe,
                )
                if restored.get("healthy") is not True:
                    raise RuntimeError("restored Phase-A state failed verification")
            except Exception as recovery_error:
                journal.update({
                    "status": "recovery_required",
                    "promotion_error": type(promotion_error).__name__,
                    "recovery_error": str(recovery_error),
                })
                phase_a.shared._write_json_atomic(journal, journal_path)
                raise RuntimeError(
                    "Phase-B promotion failed and automatic Phase-A restoration "
                    f"also failed: {recovery_error}"
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
    promotion = _load_state_receipt(state, "promotion-receipt.json")
    rollback = _load_state_receipt(state, "rollback-receipt.json")
    phase_a_status = phase_a.read_davis_stock_reference_boot_canary_status(
        game, state_root=phase_a_state, patcher=patcher,
        process_probe=process_probe,
    )
    expected = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": promotion.get("transaction_id"),
        "status": "rolled_back_to_phase_a",
        "restored_phase_a_transaction_id": promotion.get(
            "phase_a_transaction_id"
        ),
        "restored_marker_sha256": promotion.get("phase_a_marker_sha256"),
        "restored_runtime_receipt_sha256": promotion.get(
            "phase_a_runtime_receipt_sha256"
        ),
    }
    destination = _destination(game)
    checks = {
        "rollback_receipt": rollback == expected,
        "phase_a_status": phase_a_status.get("healthy") is True,
        "phase_a_marker_restored": phase_a.shared._sha256(
            destination / MARKER_NAME,
        ) == promotion.get("phase_a_marker_sha256"),
        "phase_a_runtime_receipt_restored": phase_a.shared._sha256(
            destination / RUNTIME_RECEIPT_NAME,
        ) == promotion.get("phase_a_runtime_receipt_sha256"),
    }
    return rollback, checks


def rollback_davis_stock_reference_black_transition_canary(
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
        raise PermissionError(f"Exact confirmation {ROLLBACK_CONFIRMATION!r} is required.")
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    phase_a.shared._assert_game_closed(process_probe)
    state = _state_root(game, state_root)
    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    tool = phase_a._tool_path(patcher)
    if (state / "rollback-receipt.json").is_file():
        payload, checks = _verify_rolled_back(
            game, state, phase_a_state, tool, process_probe,
        )
        if not all(checks.values()):
            failed = ", ".join(name for name, ok in checks.items() if not ok)
            raise RuntimeError(f"The completed Phase-B rollback drifted: {failed}")
        return payload

    promotion = _load_state_receipt(state, "promotion-receipt.json")
    valid, detail, _payload = validate_phase_b_launch_contract(game)
    if not valid:
        raise RuntimeError(
            f"The active Phase-B contract changed; rollback refuses: {detail}"
        )
    destination = _destination(game)
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    if (
        phase_a.shared._sha256(marker) != promotion.get("phase_b_marker_sha256")
        or phase_a.shared._sha256(runtime) !=
        promotion.get("phase_b_runtime_receipt_sha256")
    ):
        raise RuntimeError("The active Phase-B marker or receipt changed.")
    rollback_dlclist_sha256 = _extract_current_dlclist_hash(game, tool)

    journal = _read_json_object(state / "journal.json")
    journal["status"] = "rollback_started"
    phase_a.shared._write_json_atomic(journal, state / "journal.json")
    try:
        _restore_phase_a_pair(state, marker, runtime, replace=replace)
        restored = phase_a.read_davis_stock_reference_boot_canary_status(
            game, state_root=phase_a_state, patcher=tool,
            process_probe=process_probe,
        )
        if restored.get("healthy") is not True:
            raise RuntimeError("The restored Phase-A contract failed verification.")
        if _extract_current_dlclist_hash(game, tool) != rollback_dlclist_sha256:
            raise RuntimeError("Phase-B rollback changed dlclist.xml.")
    except Exception as exc:
        journal["status"] = "recovery_required"
        journal["recovery_error"] = str(exc)
        phase_a.shared._write_json_atomic(journal, state / "journal.json")
        raise

    result = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": promotion.get("transaction_id"),
        "status": "rolled_back_to_phase_a",
        "restored_phase_a_transaction_id": promotion.get(
            "phase_a_transaction_id"
        ),
        "restored_marker_sha256": promotion.get("phase_a_marker_sha256"),
        "restored_runtime_receipt_sha256": promotion.get(
            "phase_a_runtime_receipt_sha256"
        ),
    }
    phase_a.shared._write_json_atomic(result, state / "rollback-receipt.json")
    return result


def read_davis_stock_reference_black_transition_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    phase_a_state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = phase_a.shared._default_process_names,
) -> dict[str, Any]:
    game = phase_a.shared._assert_enhanced_root(Path(gta_path))
    names = {name.casefold() for name in process_probe()}
    running = bool(names.intersection({"gta5.exe", "gta5_enhanced.exe"}))
    state = _state_root(game, state_root)
    phase_a_state = phase_a._state_root(game, phase_a_state_root)
    tool = phase_a._tool_path(patcher)
    if not state.exists():
        valid, _detail, _payload = validate_phase_b_launch_contract(game)
        if valid:
            status = "unmanaged"
            healthy = False
        else:
            try:
                prior = phase_a.read_davis_stock_reference_boot_canary_status(
                    game, state_root=phase_a_state, patcher=tool,
                    process_probe=process_probe,
                )
                promotion_ready = (
                    prior.get("status") == phase_a.INSTALL_STATUS
                    and prior.get("healthy") is True
                    and all(prior.get("checks", {}).values())
                )
            except (FileNotFoundError, OSError, RuntimeError, TypeError,
                    ValueError):
                promotion_ready = False
            pack_present = _destination(game).exists()
            status = "promotion_ready" if promotion_ready else (
                "unmanaged" if pack_present else "absent"
            )
            healthy = promotion_ready or not pack_present
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
        try:
            journal = _read_json_object(state / "journal.json")
            status = str(journal.get("status", "interrupted"))
        except (OSError, RuntimeError):
            status = "interrupted"
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": status,
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
        }

    try:
        promotion = _load_state_receipt(state, "promotion-receipt.json")
        observation = _read_json_object(state / "phase-a-observation.json")
        observation_ok = (
            set(observation) == OBSERVATION_FIELDS
            and _canonical_json_sha256(observation) ==
            promotion.get("phase_a_observation_sha256")
        )
        valid, detail, runtime = validate_phase_b_launch_contract(game)
        destination = _destination(game)
        marker = destination / MARKER_NAME
        receipt = destination / RUNTIME_RECEIPT_NAME
        archive = destination / "dlc.rpf"
        dlclist_ok = False
        if tool.is_file():
            _extract_current_dlclist_hash(game, tool)
            dlclist_ok = True
        checks = {
            "launch_contract": valid,
            "phase_a_observation": observation_ok,
            "archive_unchanged": archive.is_file() and
            phase_a.shared._sha256(archive) == promotion.get("archive_sha256"),
            "marker": marker.is_file() and phase_a.shared._sha256(marker) ==
            promotion.get("phase_b_marker_sha256"),
            "runtime_receipt": receipt.is_file() and
            phase_a.shared._sha256(receipt) ==
            promotion.get("phase_b_runtime_receipt_sha256"),
            "davis_registration_exact": dlclist_ok,
        }
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
