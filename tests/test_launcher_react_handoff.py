"""Cross-product navigation must not resurrect Tk or launch a headless sidecar."""
import pytest

from allin1 import launcher_handoff as bridge


def test_frozen_service_opens_only_its_companion_gui(tmp_path, monkeypatch):
    sidecar = tmp_path / "sidecar/ALLIN1-Launcher-Sidecar.exe"
    sidecar.parent.mkdir()
    sidecar.write_bytes(b"fixture, never launched")
    companion = tmp_path / "allin1-launcher-desktop.exe"
    companion.write_bytes(b"fixture, never launched")
    monkeypatch.setattr(bridge.sys, "executable", str(sidecar))
    monkeypatch.setattr(bridge.sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge.shutil, "which", lambda _: None)
    handoff = bridge.LauncherHandoff.create("test.package", traffic=False)
    assert bridge.launcher_process_command(handoff, environment={}) == [str(companion),
        "--workspace", "packages", "--package-id", "test.package", "--traffic", "off"]
    companion.unlink()
    with pytest.raises(ValueError, match="executable was not found"):
        bridge.launcher_process_command(handoff, environment={})


def test_source_bridge_never_falls_back_to_tk(monkeypatch):
    searched = []
    def which(name):
        searched.append(name)
    monkeypatch.setattr(bridge.shutil, "which", which)
    monkeypatch.setattr(bridge.sys, "frozen", False, raising=False)
    with pytest.raises(ValueError, match="executable was not found"):
        bridge.launcher_process_command(bridge.LauncherHandoff.create(), environment={})
    assert searched == ["allin1-launcher-desktop"]


def test_react_handoff_never_uses_a_shell_or_creates_a_console(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda command, **kw: calls.append((command, kw)))
    bridge.open_launcher_packages("test.package", executable=tmp_path / "Launcher with spaces.exe")
    command, options = calls.pop()
    assert command[0] == str(tmp_path / "Launcher with spaces.exe")
    assert options == {"close_fds": True, "creationflags": getattr(bridge.subprocess, "CREATE_NO_WINDOW", 0)}
