import subprocess
from unittest.mock import Mock

from allin1 import processes


def test_run_hidden_applies_no_console_creation_flags(monkeypatch):
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(processes.subprocess, "run", run)

    processes.run_hidden(["helper.exe", "repair"], capture_output=True, text=True)

    kwargs = run.call_args.kwargs
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert run.call_args.args[0] == ["helper.exe", "repair"]


def test_caller_can_override_hidden_process_options(monkeypatch):
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(processes.subprocess, "run", run)

    processes.run_hidden(["helper"], creationflags=123)

    assert run.call_args.kwargs["creationflags"] == 123


def test_run_hidden_falls_back_to_managed_rpf_helper_when_apphost_is_blocked(
    monkeypatch, tmp_path,
):
    patcher = tmp_path / "RpfPatcher.exe"
    managed = patcher.with_suffix(".dll")
    patcher.touch()
    managed.touch()

    blocked = OSError("Application Control policy blocked this file")
    blocked.winerror = 4551
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise blocked
        return "managed-result"

    monkeypatch.setattr(processes.subprocess, "run", run)
    monkeypatch.setattr(processes.shutil, "which", lambda name: "dotnet.exe")

    result = processes.run_hidden(
        [patcher, "verify-dlc", "preview.rpf"],
        capture_output=True,
        text=True,
    )

    assert result == "managed-result"
    assert calls[0][0] == [str(patcher), "verify-dlc", "preview.rpf"]
    assert calls[1][0] == [
        "dotnet.exe", str(managed), "verify-dlc", "preview.rpf",
    ]
    assert calls[1][1]["capture_output"] is True


def test_run_hidden_does_not_fallback_for_unrelated_blocked_executable(
    monkeypatch, tmp_path,
):
    helper = tmp_path / "third-party.exe"
    helper.touch()
    helper.with_suffix(".dll").touch()
    blocked = OSError("blocked")
    blocked.winerror = 4551

    def run(*_args, **_kwargs):
        raise blocked

    monkeypatch.setattr(processes.subprocess, "run", run)
    monkeypatch.setattr(processes.shutil, "which", lambda name: "dotnet.exe")

    try:
        processes.run_hidden([helper, "inspect"])
    except OSError as exc:
        assert exc is blocked
    else:
        raise AssertionError("unrelated executable unexpectedly used managed fallback")
