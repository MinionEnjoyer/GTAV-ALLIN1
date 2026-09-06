"""SDK session tracing on the published Launcher baseline, without other drafts."""
import pytest

from allin1 import game_launcher, runtime_diagnostic_session
from tests.test_desktop_launch import launch_boundary
from tests.test_desktop_service import apply, service


# launch_boundary supplies the isolated diagnostic process probe as well as
# the launch stubs. Do not wrap RuntimeSession a second time here: that makes
# fixture ordering replace the class with a factory before watch is patched.
def test_launch_retains_the_exact_session_identity(service, launch_boundary):
    result = apply(service, "launch")["result"]
    assert result["status"] == "success"
    assert result["diagnostic_session_id"] == service.diagnostic_session.value["session_id"]
    assert result["diagnostic_session_path"] == str(service.diagnostic_session.path)
    assert service.diagnostic_session.value["status"] == "process_observed"


def test_process_is_anchored_before_stable_startup(service, launch_boundary, monkeypatch):
    def early_failure(target, on_pending):
        on_pending(game_launcher.LaunchObservation("pending", "process appeared", 123))
        assert service.diagnostic_session.process["pid"] == 123
        return game_launcher.LaunchObservation("failure", "process exited during startup")
    monkeypatch.setattr(game_launcher, "observe_gta_launch", early_failure)
    with pytest.raises(RuntimeError, match="during startup"):
        apply(service, "launch")
    assert service.diagnostic_session.value["status"] == "launch_failed"
    assert service.diagnostic_session.stop.is_set()
    assert any(event["type"] == "process_identity" for event in service.diagnostic_session.value["events"])


def test_optional_diagnostics_failure_does_not_block_launch(service, launch_boundary, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("diagnostics unavailable")
    monkeypatch.setattr(runtime_diagnostic_session, "RuntimeSession", unavailable)
    result = apply(service, "launch")["result"]
    assert result["status"] == "success"
    assert result["diagnostic_session_id"] is None
