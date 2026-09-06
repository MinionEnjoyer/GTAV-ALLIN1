import json

import pytest

from allin1 import runtime_diagnostic_session as runtime
from allin1.mods import ModIntegrationService, ModManifest
from allin1.artifact_contract import digest
from tests.test_sdk_provenance import traced
from tests.test_mods import _game


def setup(tmp_path):
    package, artifact=traced(tmp_path)
    game=_game(tmp_path)
    ModIntegrationService(game).install(ModManifest.load(package/"mod.toml"))
    return game, artifact


def observation(game, **changes):
    return {"status":"observed","pid":42,"started_at":"2026-01-01T00:00:00+00:00","executable_path":str(game/"GTA5_Enhanced.exe"),"modules":[str(game/"scripts/owned.ini")],"modules_status":"observed","modules_truncated":False,**changes}


def test_snapshot_reports_current_bytes_not_just_install_receipt(tmp_path):
    game, artifact=setup(tmp_path)
    snapshot=runtime.installed_snapshot(game)
    assert snapshot[0]["artifact_id"]==artifact["artifact_id"]
    assert snapshot[0]["files"][0]["status"]=="match"
    (game/"scripts/owned.ini").write_bytes(b"stale or changed")
    assert runtime.installed_snapshot(game)[0]["files"][0]["status"]=="mismatch"
    (game/"scripts/owned.ini").unlink()
    assert runtime.installed_snapshot(game)[0]["files"][0]["status"]=="missing"


def test_session_binds_process_creation_and_modules_without_crash_claim(tmp_path):
    game,_=setup(tmp_path)
    responses=iter([observation(game),{"status":"absent"}])
    session=runtime.RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:next(responses))
    assert session.observe(42)
    assert not session.observe(42)
    report=json.loads(session.path.read_text())
    assert report["status"]=="process_disappeared"
    process=next(e for e in report["events"] if e["type"]=="process_identity")
    assert process["data"]["pid"]==42 and process["data"]["started_at"]
    modules=next(e for e in report["events"] if e["type"]=="module_paths")
    assert modules["data"]["modules"][0]["hash_status"]=="on_disk_at_observation"
    assert report["record_sha256"]==digest({k:v for k,v in report.items() if k!="record_sha256"})
    previous=None
    for index,event in enumerate(report["events"]):
        assert event["sequence"]==index and event["previous_sha256"]==previous
        assert event["event_sha256"]==digest({k:v for k,v in event.items() if k!="event_sha256"})
        previous=event["event_sha256"]
    assert "cause not established" in report["events"][-1]["data"]["reason"]


def test_wrong_installation_and_pid_reuse_are_not_same_session(tmp_path):
    game,_=setup(tmp_path)
    responses=iter([observation(game,executable_path=str(tmp_path/"other/GTA5_Enhanced.exe")),observation(game),observation(game,started_at="2026-09-06T11:00:00+00:00")])
    session=runtime.RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:next(responses))
    assert not session.observe(42) and session.process is None
    assert session.observe(42)
    assert not session.observe(42)
    assert session.value["status"]=="process_identity_changed"
    assert session.stop.is_set()


def test_unavailable_observation_does_not_become_exit_or_runtime_proof(tmp_path):
    game,_=setup(tmp_path)
    session=runtime.RuntimeSession(game,tmp_path/"state",process_probe=lambda pid:{"status":"unavailable","reason":"access boundary"})
    assert not session.observe(42)
    assert session.value["status"]=="launch_requested"
    assert session.process is None and not session.stop.is_set()


def test_competing_temporary_file_is_not_deleted(tmp_path):
    game,_=setup(tmp_path)
    session=runtime.RuntimeSession(game,tmp_path/"state")
    competing=session.path.with_name(session.path.name+".tmp")
    competing.write_text("do not remove")
    with pytest.raises(FileExistsError):session.event("test",{})
    assert competing.read_text()=="do not remove"


def test_frozen_observer_uses_verified_sidecar_identity_not_missing_py_siblings(tmp_path,monkeypatch):
    from allin1 import runtime_resources
    game,_=setup(tmp_path)
    executable=tmp_path/"ALLIN1-Launcher-Sidecar.exe";executable.write_bytes(b"test-owned-frozen-image")
    monkeypatch.setattr(runtime.sys,"frozen",True,raising=False)
    monkeypatch.setattr(runtime.sys,"executable",str(executable))
    monkeypatch.setattr(runtime,"__file__",str(tmp_path/"no-python-siblings/runtime_diagnostic_session.pyc"))
    monkeypatch.setattr(runtime_resources,"resource_root",lambda:tmp_path)
    monkeypatch.setattr(runtime_resources,"frozen_identity",lambda root:{"build_id":"verified-test-build","source_sha256":"a"*64})
    session=runtime.RuntimeSession(game,tmp_path/"state")
    assert session.value["observer_components"]=={"sidecar_executable":runtime.file_hash(executable)}
    assert session.value["observer_build"]["mode"]=="frozen_verified_resources"
