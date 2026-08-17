import hashlib
import json
from datetime import datetime, timezone

import pytest

from allin1.compatibility import load_weapon_compatibility, weapon_available
from allin1.preview_artifacts import expected_dictionary, verify_ytd_set
from allin1.reliability import (
    SmokeAnalysis, SmokeCheck, analyze_client_log, write_smoke_report,
)


def test_smoke_report_records_pass_and_failure(tmp_path):
    path = tmp_path / "report.json"
    log = tmp_path / "client.log"
    log.write_text("session log")
    digest = hashlib.sha256(log.read_bytes()).hexdigest()
    passed = SmokeAnalysis(log, digest, "session-a", "2026-08-12T12:00:00+00:00",
                           (SmokeCheck("spawn", True),))
    failed = SmokeAnalysis(log, digest, "session-b", "2026-08-12T12:00:00+00:00",
                           (SmokeCheck("preview", False, "missing"),))
    assert write_smoke_report(path, "enhanced", passed) is True
    assert json.loads(path.read_text())["passed"] is True
    assert write_smoke_report(path, "legacy", failed) is False
    payload = json.loads(path.read_text())
    assert payload["checks"][0]["detail"] == "missing"
    assert payload["schema"] == 2 and payload["source_log_sha256"] == digest


def test_weapon_compatibility_manifest(tmp_path):
    path = tmp_path / "compat.toml"
    path.write_text('[weapons.WEAPON_NEW]\neditions=["enhanced"]\n')
    manifest = load_weapon_compatibility(path)
    assert weapon_available("WEAPON_NEW", "enhanced", manifest) is True
    assert weapon_available("WEAPON_NEW", "legacy", manifest) is False
    assert weapon_available("WEAPON_NORMAL", "legacy", manifest) is True


def test_preview_artifact_plan_and_validation(tmp_path):
    assert expected_dictionary(0, 2) == "allin1_prev_01"
    assert expected_dictionary(2, 2) == "allin1_prev_02"
    with pytest.raises(ValueError):
        expected_dictionary(-1)
    (tmp_path / "allin1_prev_01.ytd").write_bytes(b"one")
    (tmp_path / "allin1_prev_03.ytd").write_bytes(b"extra")
    report = verify_ytd_set(tmp_path, 3, 2)
    assert report.valid is False
    assert report.missing_dicts == ("allin1_prev_02",)
    assert report.unexpected_dicts == ("allin1_prev_03",)
    (tmp_path / "allin1_prev_02.ytd").write_bytes(b"two")
    (tmp_path / "allin1_prev_03.ytd").unlink()
    assert verify_ytd_set(tmp_path, 3, 2).valid is True


def test_client_log_analysis_handles_events_and_malformed_lines(tmp_path):
    path = tmp_path / "client.log"
    now = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)
    session = "fresh-session"
    def event(component, message, **fields):
        return {"ts": "2026-08-12T12:00:00+00:00", "level": "INFO",
                "session": session, "component": component, "message": message, **fields}
    events = [
        event("Client", "session_started"),
        event("VehicleHelper", "vehicle_created"),
        event("GBAY", "GiveWeapon: WEAPON_TEST, price=$0"),
        event("Preview", "texture_loaded", dictionary="allin1_prev_01"),
        event("Garage", "EnterGarage: COMPLETE, character=michael"),
        event("Garage", "LeaveGarage: COMPLETE"),
        event("Garage", "EnterFloorGarage: COMPLETE, character=michael_floor"),
        event("Garage", "LeaveFloorGarage: COMPLETE"),
        event("SeatSelector", "seat_switch_completed"),
    ]
    path.write_text("broken\n" + "\n".join(json.dumps(event) for event in events))
    analysis = analyze_client_log(path, now=now)
    assert analysis.passed is True
    assert analysis.session == session


def test_client_log_analysis_rejects_stale_mixed_or_failed_events(tmp_path):
    path = tmp_path / "client.log"
    events = [
        {"ts": "2026-08-10T12:00:00+00:00", "level": "INFO", "session": "old",
         "component": "Client", "message": "session_started"},
        {"ts": "2026-08-10T12:00:01+00:00", "level": "INFO", "session": "old",
         "component": "GBAY", "message": "GiveWeapon: WEAPON_TEST, price=$0"},
        {"ts": "2026-08-12T12:00:00+00:00", "level": "INFO", "session": "new",
         "component": "Client", "message": "session_started"},
        {"ts": "2026-08-12T12:00:01+00:00", "level": "INFO", "session": "new",
         "component": "GBAY", "message": "GiveWeapon: native grant failed for WEAPON_TEST"},
        {"ts": "2026-08-12T12:00:02+00:00", "level": "ERROR", "session": "new",
         "component": "Garage", "message": "transition_failed"},
    ]
    path.write_text("\n".join(json.dumps(event) for event in events))
    analysis = analyze_client_log(
        path, now=datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc))
    checks = {check.name: check.passed for check in analysis.checks}
    assert analysis.session == "new"
    assert checks["weapon_grant"] is False
    assert checks["client_errors"] is False
