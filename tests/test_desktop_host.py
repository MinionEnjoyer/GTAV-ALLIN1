"""Real stdio process tests: no GUI, network, game discovery or user state."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from allin1.desktop_host import MAX_REQUEST, serve


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''
import importlib.abc, runpy, socket, sys
attempts = []
class NoTk(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'tkinter', '_tkinter'}:
            attempts.append(fullname)
            raise ImportError('Tkinter deliberately unavailable: ' + fullname)
sys.meta_path.insert(0, NoTk())
def no_network(*args, **kwargs):
    raise AssertionError('Offline process test attempted network access')
socket.socket.connect = no_network
socket.create_connection = no_network
runpy.run_module('allin1.desktop_host', run_name='__main__')
assert not attempts, attempts
'''


def envelope(operation, payload=None, **changes):
    return {"schema_version": 1, "request_id": operation, "operation": operation,
            "payload": payload or {}, **changes}


def run_host(tmp_path, requests):
    project = tmp_path / "Empty project with spaces"
    project.mkdir()
    state = tmp_path / "User data with spaces"
    outside = tmp_path / "outside.canary"
    outside.write_bytes(b"preserved")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONIOENCODING="utf-8")
    for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        env[key] = str(tmp_path / "isolated-user" / key)
    env.pop("ALLIN1_GTA_PATH", None)
    result = subprocess.run(
        [sys.executable, "-u", "-c", BOOTSTRAP, "--project-root", str(project), "--state-root", str(state)],
        input="".join(json.dumps(item) + "\n" for item in requests), text=True,
        encoding="utf-8", capture_output=True, timeout=30, cwd=project, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    assert outside.read_bytes() == b"preserved"
    assert not state.exists(), "Read-only startup must not publish preferences"
    assert not list(project.iterdir()), "Read-only startup must not write the project"
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_real_host_all_workspaces_without_tkinter_or_write_authority(tmp_path):
    modules = ("setup", "gameplay", "content", "input", "mods", "characters", "sdk", "activity", "help")
    responses = run_host(tmp_path, [envelope("catalog"), *[
        envelope("inspect", {"module": name}, request_id=name) for name in modules
    ], envelope("shutdown"), envelope("catalog", request_id="after-shutdown")])
    assert len(responses) == 11
    assert all(item["kind"] == "result" for item in responses), responses
    catalog = responses[0]["payload"]
    assert catalog["capabilities"] == {"game_writes": False, "launch": False}
    assert len(catalog["navigation"]) == 9
    assert any(item["key"] == "getting-started" for item in catalog["help_topics"])
    assert [item["payload"]["module"] for item in responses[1:-1]] == list(modules)
    assert responses[-1]["payload"] == {"closed": True}


def test_real_host_recovers_after_rejected_envelope_and_exits_on_eof(tmp_path):
    responses = run_host(tmp_path, [envelope("catalog", schema_version=True), envelope("catalog")])
    assert [item["kind"] for item in responses] == ["error", "result"]


def test_mixed_shell_service_identity_rejected_before_service_creation(tmp_path, monkeypatch):
    from allin1 import desktop_host
    monkeypatch.setattr(sys, "argv", ["desktop_host", "--project-root", str(tmp_path), "--expected-build-id", "current-shell"])
    monkeypatch.setattr(desktop_host, "frozen_identity", lambda _: {"build_id": "stale-sidecar"})
    monkeypatch.setattr(desktop_host, "LauncherService", lambda *a, **k: pytest.fail("Mixed build started the service"))
    with pytest.raises(ValueError, match="identities disagree"):
        desktop_host.main()
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("changes", [
    {"schema_version": True}, {"schema_version": 1.0}, {"schema_version": "1"},
    {"schema_version": 2}, {"operation": []}, {"operation": "shell"},
    {"request_id": ""}, {"request_id": "x" * 97}, {"payload": []}, {"extra": True},
])
def test_invalid_envelopes_never_dispatch(changes):
    class NoDispatch:
        def read(self, *_):
            pytest.fail("Rejected request reached the service")
    output = io.StringIO()
    request = envelope("catalog")
    request.update(changes)
    serve(NoDispatch(), io.StringIO(json.dumps(request) + "\n"), output)
    assert json.loads(output.getvalue())["kind"] == "error"


@pytest.mark.parametrize("text", ['{"schema_version":1,"schema_version":1}\n', '{"payload":NaN}\n'])
def test_ambiguous_json_is_rejected(text):
    output = io.StringIO()
    serve(object(), io.StringIO(text), output)
    assert json.loads(output.getvalue())["kind"] == "error"


@pytest.mark.parametrize("text", ["x" * (MAX_REQUEST + 1) + "\n", "{}", "é" * (MAX_REQUEST // 2 + 1) + "\n"], ids=["oversize", "unterminated", "utf8-byte-limit"])
def test_oversize_or_unterminated_frame_closes_without_dispatch(text):
    output = io.StringIO()
    serve(object(), io.StringIO(text), output)
    assert output.getvalue() == ""


def test_dispatch_progress_and_incidental_stdout_remain_separate(capsys):
    class Service:
        def review(self, payload):
            print("human diagnostic, not JSON")
            self.progress(50, "reviewed")
            return {"review_id": "fixture", **payload}
        def apply(self, payload):
            return {"applied": payload["review_id"]}
    incoming = io.StringIO("".join(json.dumps(item) + "\n" for item in [
        envelope("review", {"action": "save_config"}), envelope("apply", {"review_id": "fixture"}), envelope("shutdown")]))
    output = io.StringIO()
    serve(Service(), incoming, output)
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [row["kind"] for row in rows] == ["progress", "result", "result", "result"]
    assert rows[0]["payload"]["event"] == "launcher.progress"
    assert rows[2]["payload"] == {"applied": "fixture"}
    assert "human diagnostic" in capsys.readouterr().err


@pytest.mark.parametrize("payload", [{"huge": "x" * (4 * 1024**2)}, {"invalid": float("nan")}], ids=["response-bound", "nonfinite-response"])
def test_invalid_service_output_returns_a_protocol_error(payload):
    class Service:
        def read(self, *_): return payload
    output = io.StringIO()
    serve(Service(), io.StringIO(json.dumps(envelope("catalog")) + "\n"), output)
    response = json.loads(output.getvalue())
    assert response["kind"] == "error" and response["request_id"] == "catalog"


@pytest.mark.parametrize("explicit", [True, False])
def test_entrypoint_routes_state_and_authority_without_writing_user_paths(tmp_path, monkeypatch, explicit):
    from allin1 import desktop_host, sdk_manager
    observed = {}
    def service(project, state, **kwargs):
        observed.update(project=project, state=state, **kwargs)
        from types import SimpleNamespace
        return SimpleNamespace()
    def no_serve(*args): observed["served"] = True
    monkeypatch.setattr(desktop_host, "LauncherService", service)
    monkeypatch.setattr(desktop_host, "serve", no_serve)
    monkeypatch.setattr(sdk_manager, "default_sdk_root", lambda: tmp_path / "managed-sdk")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    args = ["desktop_host", "--project-root", str(tmp_path / "project")]
    if explicit: args += ["--state-root", str(tmp_path / "preview"), "--allow-game-writes", "--allow-launch"]
    monkeypatch.setattr(sys, "argv", args)
    for name in ("stdin", "stdout", "stderr"): monkeypatch.setattr(sys, name, io.StringIO())
    desktop_host.main()
    assert observed["state"] == (tmp_path / "preview" if explicit else tmp_path / "appdata/ALLIN1/Launcher")
    assert observed["sdk_root"] == (None if explicit else tmp_path / "managed-sdk")
    assert observed["package_library_root"] == (None if explicit else tmp_path / "appdata/ALLIN1/Packages")
    assert observed["assistant_root"] == (None if explicit else tmp_path / "appdata/ALLIN1/Assistant")
    assert observed["allow_game_writes"] is explicit and observed["allow_launch"] is explicit
    assert observed["served"] is True
    assert not list(tmp_path.iterdir())
