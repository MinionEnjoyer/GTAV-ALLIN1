import json

import pytest

from allin1.compatibility import load_weapon_compatibility, weapon_available
from allin1.preview_artifacts import expected_dictionary, verify_ytd_set
from allin1.reliability import (
    GarageState, SeatState, SmokeCheck, analyze_client_log, write_smoke_report,
)


def test_garage_state_machine_success_overlap_and_recovery():
    state = GarageState()
    assert state.begin("enter") is True
    assert state.begin("leave") is False
    state.step("fade_out")
    state.step("freeze")
    state.step("enter_complete")
    state.finish()
    assert state == GarageState(location="garage")
    assert state.begin("leave") is True
    state.step("fade_out")
    state.recover()
    assert state == GarageState()
    with pytest.raises(ValueError, match="no transition"):
        state.step("freeze")
    state.begin("enter")
    with pytest.raises(ValueError, match="unknown"):
        state.step("explode")


def test_seat_state_revalidates_occupancy_and_times_out():
    state = SeatState({-1: "player", 0: "free", 1: "npc"})
    assert state.available() == [-1, 0]
    assert state.select(1) is False
    assert state.select(0) is True
    state.seats[0] = "npc"
    assert state.confirm() is False
    state.seats[0] = "free"
    assert state.confirm() is True
    state.timeout()
    assert state.executing is False


def test_smoke_report_records_pass_and_failure(tmp_path):
    path = tmp_path / "report.json"
    assert write_smoke_report(path, "enhanced", [SmokeCheck("spawn", True)]) is True
    assert json.loads(path.read_text())["passed"] is True
    assert write_smoke_report(path, "legacy", [SmokeCheck("preview", False, "missing")]) is False
    payload = json.loads(path.read_text())
    assert payload["checks"][0]["detail"] == "missing"


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
    events = [
        {"component": "VehicleHelper", "message": "vehicle_created"},
        {"component": "GBAY", "message": "GiveWeapon: WEAPON_TEST, price=$0"},
        {"component": "Preview", "message": "texture_loaded"},
        {"component": "Garage", "message": "EnterGarage: COMPLETE, character=michael"},
        {"component": "Garage", "message": "LeaveFloorGarage: COMPLETE"},
        {"component": "SeatSelector", "message": "seat_switch_completed"},
    ]
    path.write_text("broken\n" + "\n".join(json.dumps(event) for event in events))
    assert all(check.passed for check in analyze_client_log(path))
