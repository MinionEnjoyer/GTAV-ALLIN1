"""Structured activity persistence must never obscure mutation outcomes."""
import json
import os
from types import SimpleNamespace

import pytest

from allin1 import desktop_activity, desktop_service
from allin1.desktop_service import LauncherService
from tests.test_desktop_service import apply, service


def test_activity_survives_service_restart_without_progress_text_parsing(service):
    receipt = apply(service, "save_profile", name="Journal test")
    restarted = LauncherService(service.project, service.state)
    rows = restarted.inspect({"module": "activity"})["activity"]
    assert len(rows) == 1
    assert rows[0]["event"] == "launcher.action.completed" and rows[0]["schema_version"] == 1
    assert rows[0]["action"] == "save_profile" and rows[0]["review_id"] == receipt["review_id"]


def test_open_log_folder_uses_only_host_owned_path(service, monkeypatch):
    seen = []
    monkeypatch.setattr(desktop_service, "os", SimpleNamespace(name="nt", startfile=seen.append))
    with pytest.raises(ValueError, match="No activity folder"):
        service.read("open_activity_folder", {})
    apply(service, "save_profile", name="Journal")
    result = service.read("open_activity_folder", {"path": "C:/untrusted"})
    assert seen == [service.state / "logs"]
    assert result == {"opened": str(service.state / "logs")}


@pytest.mark.parametrize("failure", ["invalid", "oversized", "hardlink"])
def test_journal_failure_keeps_successful_action_and_preserves_evidence(service, tmp_path, failure):
    path = service.state / "logs/activity.json"; path.parent.mkdir(parents=True)
    if failure == "invalid": path.write_bytes(b'{"schema_version":99}')
    elif failure == "oversized": path.write_bytes(b"x" * (desktop_activity.MAX_BYTES + 1))
    else:
        outside = tmp_path / "canary"; outside.write_bytes(b"outside")
        os.link(outside, path)
    before = path.read_bytes()
    receipt = apply(service, "save_profile", name="Completed")
    assert receipt["kind"] == "launcher_applied"
    assert "Action completed" in receipt["warning"]
    assert service.profiles.load("Completed") == service.config()
    assert path.read_bytes() == before


def test_bounded_structured_event_history(tmp_path):
    root = tmp_path / "state"
    for index in range(205):
        desktop_activity.append(root, {"schema_version": 1, "event": "launcher.action.completed", "action": "save_profile", "review_id": str(index), "time": index})
    rows = desktop_activity.read(root)
    assert len(rows) == 200 and rows[0]["review_id"] == "5" and rows[-1]["review_id"] == "204"
    path = root / "logs/activity.json"
    for invalid in ({"schema_version": True, "events": []}, {"schema_version": 1, "events": [{}]}, {"schema_version": 1, "events": "invalid"}):
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError): desktop_activity.read(root)
