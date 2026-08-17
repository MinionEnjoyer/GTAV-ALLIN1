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
