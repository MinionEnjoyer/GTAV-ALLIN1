"""Launch orchestration contracts: every external process boundary is replaced."""
from types import SimpleNamespace

import pytest

from allin1 import desktop_service, game_launcher, health, garage_map_detection, reactor_bootstrap, versioning, prelaunch_previews, runtime_diagnostic_session
from tests.test_desktop_service import apply, service


@pytest.fixture
def launch_boundary(service, monkeypatch):
    events = []
    session_type = runtime_diagnostic_session.RuntimeSession
    monkeypatch.setattr(session_type,"watch",lambda *args:None)
    def diagnostic(game,state):
        return session_type(game,state,process_probe=lambda pid:{"status":"observed","pid":pid,"started_at":"2026-01-01T00:00:00+00:00",
            "executable_path":str(next(game.glob("GTA5*.exe"))),"modules":[],"modules_status":"observed","modules_truncated":False})
    monkeypatch.setattr(runtime_diagnostic_session,"RuntimeSession",diagnostic)
    service.allow_launch = True
    monkeypatch.setattr(prelaunch_previews, "prepare", lambda *a, **kw: events.append("previews") or {"status":"complete", "skip":kw['skip']})
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
    assert receipt["result"]["diagnostic_session_id"] == service.diagnostic_session.value["session_id"]
    assert service.diagnostic_session.value["status"] == "process_observed"
    assert launch_boundary == ["previews", "map", "dispatch", "requested", "canary"]
    status = service.read("startup_status", {})
    assert status["schema_version"] == 1 and status["event"] == "launcher.reactor.startup"
    assert status["ready"] == ["story"] and status["active"] is False
    assert service.read("startup_status", {}) == {"active": False}


def test_startup_process_identity_is_captured_before_stable_launch(service,launch_boundary,monkeypatch):
    def early_failure(target,on_pending):
        on_pending(game_launcher.LaunchObservation("pending","process appeared",123))
        assert service.diagnostic_session.process["pid"]==123
        return game_launcher.LaunchObservation("failure","process exited during startup")
    monkeypatch.setattr(game_launcher,"observe_gta_launch",early_failure)
    with pytest.raises(RuntimeError,match="during startup"): apply(service,"launch")
    assert service.diagnostic_session.value["status"]=="launch_failed"
    assert service.diagnostic_session.stop.is_set()
    assert any(event["type"]=="process_identity" for event in service.diagnostic_session.value["events"])


def test_launch_reports_measured_preview_progress_but_no_game_percentage(service, launch_boundary, monkeypatch):
    updates = []
    service.progress = lambda percentage, message: updates.append((percentage, message))
    def previews(*args, **kwargs):
        kwargs['progress'](None, 'Validated mod list')
        kwargs['progress'](0, 'Weapon previews: 0/2 processed')
        kwargs['progress'](50, 'Weapon previews: 1/2 processed')
        kwargs['progress'](100, 'Weapon previews: 2/2 processed')
        return {'status': 'complete'}
    monkeypatch.setattr(prelaunch_previews, 'prepare', previews)
    apply(service, 'launch')
    assert [p for p, _ in updates if p is not None] == [0, 50, 100]
    assert updates[0][0] is None and updates[-1][0] is None
    assert all(p is None for p, m in updates if not m.startswith('Weapon previews:'))
    assert any('Requesting GTA launch' in m for _, m in updates)


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


def test_optional_preview_failure_does_not_block_launch(service, launch_boundary, monkeypatch):
    def fail(*args, **kw): raise OSError("cache unavailable")
    monkeypatch.setattr(prelaunch_previews,"prepare",fail)
    result=apply(service,"launch")["result"]
    assert result["status"]=="success" and result["weapon_previews"]["status"]=="unavailable"


def test_prepare_action_does_not_require_launch_authority_or_dispatch(service,launch_boundary):
    service.allow_launch=False
    assert apply(service,"prepare_previews")["result"]["status"]=="complete"
    assert launch_boundary==["previews"]


def test_skip_flag_reaches_launch_preview_phase(service,launch_boundary):
    assert apply(service,"launch",skip_previews=True)["result"]["weapon_previews"]["skip"] is True


@pytest.mark.parametrize("stage", ["review", "validation", "previews", "maps", "preloader"])
def test_cancel_at_each_safe_stage_prevents_dispatch(service, launch_boundary, monkeypatch, stage):
    from allin1.launch_cancellation import checkpoint
    def cancel():
        review_id = service.launch_cancellation.status()["launch_review_id"]
        assert service.cancel_launch({"review_id": review_id})["accepted"]
    if stage == "review":
        def progress(_, message):
            if message == "Checking reviewed launch": cancel()
        service.progress = progress
    elif stage == "validation":
        monkeypatch.setattr(health, "scan_launch_hazards", lambda *a: cancel() or [])
    elif stage == "previews":
        def previews(*a, **kw):
            cancel()
            checkpoint()  # Must not become an optional-preview failure.
        monkeypatch.setattr(prelaunch_previews, "prepare", previews)
    elif stage == "maps":
        monkeypatch.setattr(garage_map_detection, "refresh_garage_map_detection", lambda *a: cancel())
    else:
        monkeypatch.setattr(reactor_bootstrap, "start_reactor_preloader",
                            lambda *a, **kw: cancel() or SimpleNamespace(stop=lambda: launch_boundary.append("stop")))
    receipt = apply(service, "launch")
    assert receipt["kind"] == "launcher_cancelled"
    assert receipt["result"] == {"status": "cancelled", "game_started": False}
    assert "dispatch" not in launch_boundary and "canary" not in launch_boundary
    assert ("stop" in launch_boundary) is (stage == "preloader")
    assert not service.reviews and not service.launch_cancellation.status()["cancellable"]
    assert service.activity[-1]["event"] == "launcher.action.cancelled"
    assert not any(e["event"] == "launcher.action.completed" for e in service.activity)


def test_cancel_after_os_handoff_cannot_report_cancelled_or_stop_game(service, launch_boundary):
    replies = []
    def progress(_, message):
        if message.startswith("Requesting GTA launch"):
            replies.append(service.cancel_launch({"review_id": service.launch_cancellation.status()["launch_review_id"]}))
    service.progress = progress
    assert apply(service, "launch")["result"]["status"] == "success"
    assert replies == [{"status": "already_dispatched", "accepted": False}]
    assert "dispatch" in launch_boundary and "stop" not in launch_boundary


def test_cancelled_review_is_consumed_and_retry_requires_new_review(service, launch_boundary):
    def cancel(_, message):
        if message == "Checking reviewed launch":
            service.cancel_launch({"review_id": service.launch_cancellation.status()["launch_review_id"]})
    service.progress = cancel
    review = service.review({"action": "launch"})
    payload = {"confirmed": True, "review_id": review["review_id"], "review_sha256": review["review_sha256"]}
    assert service.apply(payload)["result"]["status"] == "cancelled"
    with pytest.raises(ValueError, match="already used"): service.apply(payload)
    service.progress = lambda *a: None
    assert apply(service, "launch")["result"]["status"] == "success"


def test_manual_release_page_is_fixed_and_cannot_execute_remote_metadata(service, monkeypatch):
    opened = []
    monkeypatch.setattr(desktop_service, "os", SimpleNamespace(name="nt", startfile=opened.append))
    monkeypatch.setattr(versioning, "fetch_latest_release", lambda: versioning.ReleaseInfo("0.6.5", "file:///C:/untrusted.exe", True, "Next release"))
    with pytest.raises(ValueError, match="Check Launcher releases first"):
        service.read("open_launcher_release", {})
    assert service.read("check_update", {})["update_available"] is True
    service.read("open_launcher_release", {"url": "ms-settings:bad"})
    assert opened == ["https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/latest"]
    assert not service.state.exists()
