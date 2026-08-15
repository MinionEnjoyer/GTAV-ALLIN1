"""Artifact-backed reliability checks for the in-game smoke workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class SmokeAnalysis:
    source_log: Path
    log_sha256: str
    session: str | None
    session_started_utc: str | None
    checks: tuple[SmokeCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def write_smoke_report(path: Path, edition: str, analysis: SmokeAnalysis) -> bool:
    """Write the machine-readable result consumed by release qualification."""
    payload = {
        "schema": 2,
        "edition": edition,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": analysis.passed,
        "source_log": str(analysis.source_log.resolve()),
        "source_log_sha256": analysis.log_sha256,
        "session": analysis.session,
        "session_started_utc": analysis.session_started_utc,
        "checks": [asdict(check) for check in analysis.checks],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return analysis.passed


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


def analyze_client_log(
    path: Path, *, now: datetime | None = None, max_age: timedelta = timedelta(hours=24),
) -> SmokeAnalysis:
    """Derive smoke checks from one fresh, internally consistent game session."""
    raw_bytes = path.read_bytes()
    events: list[dict[str, object]] = []
    for raw in raw_bytes.decode("utf-8-sig").splitlines():
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)

    start_index = -1
    session: str | None = None
    started: datetime | None = None
    for index, event in enumerate(events):
        component = event.get("component", "")
        message = event.get("message", "")
        candidate = event.get("session")
        timestamp = _parse_utc(event.get("ts"))
        if (component == "Client" and message == "session_started" and
                isinstance(candidate, str) and candidate and timestamp is not None):
            start_index = index
            session = candidate
            started = timestamp

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fresh = started is not None and timedelta(0) <= current - started <= max_age
    session_events = [
        event for event in events[start_index:]
        if start_index >= 0 and event.get("session") == session
    ]
    timestamps_valid = bool(session_events) and all(
        _parse_utc(event.get("ts")) is not None for event in session_events
    )
    session_integrity = start_index >= 0 and fresh and timestamps_valid

    observed: set[str] = set()
    standard_enter = standard_leave = False
    floor_enter = floor_leave = False
    has_errors = False
    for event in session_events:
        component = event.get("component", "")
        message = event.get("message", "")
        level = event.get("level", "")
        if level == "ERROR":
            has_errors = True
        if component == "VehicleHelper" and message == "vehicle_created":
            observed.add("vehicle_spawn")
        if (component == "GBAY" and isinstance(message, str) and
                message.startswith("GiveWeapon:") and "price=$" in message):
            observed.add("weapon_grant")
        if component == "Garage" and isinstance(message, str):
            standard_enter |= message.startswith("EnterGarage: COMPLETE")
            standard_leave |= message.startswith("LeaveGarage: COMPLETE")
            floor_enter |= message.startswith("EnterFloorGarage: COMPLETE")
            floor_leave |= message.startswith("LeaveFloorGarage: COMPLETE")
        if component == "SeatSelector" and message == "seat_switch_completed":
            observed.add("seat_switch")
        if (component == "Preview" and message == "texture_loaded" and
                str(event.get("dictionary", "")).startswith("allin1_")):
            observed.add("preview_stream")
    if standard_enter and standard_leave:
        observed.add("garage_transition")
    if floor_enter and floor_leave:
        observed.add("floor_garage_transition")

    checks = [
        SmokeCheck("session_integrity", session_integrity,
                   "fresh single session" if session_integrity else "missing, stale, or invalid session"),
        SmokeCheck("client_errors", not has_errors,
                   "none observed" if not has_errors else "ERROR event observed"),
    ]
    required_events = (
        "vehicle_spawn", "weapon_grant", "preview_stream", "garage_transition",
        "floor_garage_transition", "seat_switch",
    )
    checks.extend(SmokeCheck(name, name in observed,
                             "observed" if name in observed else "not observed")
                  for name in required_events)
    return SmokeAnalysis(
        source_log=path,
        log_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        session=session,
        session_started_utc=started.isoformat() if started else None,
        checks=tuple(checks),
    )
