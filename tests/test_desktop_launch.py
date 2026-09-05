"""Launch orchestration contracts: every external process boundary is replaced."""
from types import SimpleNamespace

import pytest

from allin1 import game_launcher, health, garage_map_detection, reactor_bootstrap, versioning
from tests.test_desktop_service import apply, service


@pytest.fixture
def launch_boundary(service, monkeypatch):
    events = []
    service.allow_launch = True
    preloader = SimpleNamespace(stop=lambda: events.append("stop"))
    monitor = SimpleNamespace(mark_launch_requested=lambda: events.append("requested"),
                              sample=lambda **kwargs: reactor_bootstrap.BootstrapState(frozenset({"story"})))
    monkeypatch.setattr(health, "scan_launch_hazards", lambda path: [])
    monkeypatch.setattr(health, "consume_rpf_canary", lambda *args: events.append("canary"))
    monkeypatch.setattr(garage_map_detection, "refresh_garage_map_detection", lambda *args: events.append("map"))
    monkeypatch.setattr(reactor_bootstrap, "inspect_reactor_installation", lambda *args: SimpleNamespace(available=True))
    monkeypatch.setattr(reactor_bootstrap, "ReactorStartupMonitor", lambda *args: monitor)
    monkeypatch.setattr(reactor_bootstrap, "start_reactor_preloader", lambda *args, **kwargs: preloader)
    def dispatch(path):
        assert path == service.game(service.config())
        events.append("dispatch")
        return SimpleNamespace(description="synthetic process")
    monkeypatch.setattr(game_launcher, "launch_gta", dispatch)
    def observe(target, on_pending):
        on_pending(game_launcher.LaunchObservation("pending", "waiting"))
        return game_launcher.LaunchObservation("success", "observed", 123, True)
    monkeypatch.setattr(game_launcher, "observe_gta_launch", observe)
    monkeypatch.setattr(game_launcher, "probe_gta_runtime", lambda *args: SimpleNamespace(process_ids=(123,)))
    return events


def test_reviewed_launch_and_structured_reactor_completion(service, launch_boundary):
    receipt = apply(service, "launch")
    assert receipt["result"]["status"] == "success" and receipt["result"]["startup_monitoring"]
    assert launch_boundary == ["map", "dispatch", "requested", "canary"]
    status = service.read("startup_status", {})
    assert status["schema_version"] == 1 and status["event"] == "launcher.reactor.startup"
    assert status["ready"] == ["story"] and status["active"] is False
    assert service.read("startup_status", {}) == {"active": False}


@pytest.mark.parametrize("failure", ["preloader", "dispatch", "observation", "negative-observation"])
def test_failed_launch_clears_monitor_and_stops_only_started_preloader(service, launch_boundary, monkeypatch, failure):
    def fail(*args, **kwargs): raise RuntimeError("synthetic launch failure")
    if failure == "preloader": monkeypatch.setattr(reactor_bootstrap, "start_reactor_preloader", fail)
    elif failure == "dispatch": monkeypatch.setattr(game_launcher, "launch_gta", fail)
    elif failure == "observation": monkeypatch.setattr(game_launcher, "observe_gta_launch", fail)
    else: monkeypatch.setattr(game_launcher, "observe_gta_launch", lambda *args, **kwargs: game_launcher.LaunchObservation("failure", "synthetic launch failure"))
    with pytest.raises(RuntimeError, match="synthetic launch failure"):
        apply(service, "launch")
    assert service.startup_monitor is None
    assert ("stop" in launch_boundary) is (failure != "preloader")


def test_launch_hazards_block_before_save_or_dispatch(service, launch_boundary, monkeypatch):
    monkeypatch.setattr(health, "scan_launch_hazards", lambda *args: [SimpleNamespace(severity="error", message="unsafe runtime")])
    with pytest.raises(ValueError, match="unsafe runtime"):
        apply(service, "launch")
    assert not launch_boundary and not service.state.exists()


def test_optional_map_refresh_failure_does_not_turn_launch_into_failure(service, launch_boundary, monkeypatch):
    def fail(*args): raise OSError("optional map cache unavailable")
    monkeypatch.setattr(garage_map_detection, "refresh_garage_map_detection", fail)
    assert apply(service, "launch")["result"]["status"] == "success"


def test_manual_release_page_is_fixed_and_cannot_execute_remote_metadata(service, monkeypatch):
    import os
    opened = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(versioning, "fetch_latest_release", lambda: versioning.ReleaseInfo("0.6.5", "file:///C:/untrusted.exe", True, "Next release"))
    with pytest.raises(ValueError, match="Check Launcher releases first"):
        service.read("open_launcher_release", {})
    assert service.read("check_update", {})["update_available"] is True
    service.read("open_launcher_release", {"url": "ms-settings:bad"})
    assert opened == ["https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/latest"]
    assert not service.state.exists()
