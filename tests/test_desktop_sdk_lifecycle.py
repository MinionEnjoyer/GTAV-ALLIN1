"""Reviewed Launcher-to-SDK actions; inert portable fixtures and no process launch."""
import os
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

from allin1 import desktop_service, sdk_manager
from allin1.sdk_installation import SHELL, SIDECAR
from tests.test_desktop_service import service, apply
from tests.test_sdk_tauri_installation import archive, tauri_payload


def test_reviewed_sdk_install_repair_upgrade_open_and_uninstall(service, tmp_path, monkeypatch):
    source = archive(tmp_path / "SDK package.zip", tauri_payload())
    game = service.game(service.config())
    original = service.tree_identity(game)
    receipt = apply(service, "sdk_install", source=str(source))
    assert receipt["result"]["healthy"]
    root = service.sdk_root
    (root / "personal.xml").write_bytes(b"user project")
    (root / SIDECAR).write_bytes(b"broken")
    apply(service, "sdk_install", source=str(source))
    assert sdk_manager.read_sdk_status(root).healthy
    archive(source, tauri_payload("0.6.5", "upgrade-fixture"))
    apply(service, "sdk_install", source=str(source))
    assert sdk_manager.read_sdk_status(root).version == "0.6.5"
    popen = Mock(return_value=SimpleNamespace(pid=12345))
    monkeypatch.setattr(desktop_service.subprocess, "Popen", popen)
    opened = apply(service, "sdk_open", workspace="assets")
    assert opened["result"] == {"pid": 12345}
    assert popen.call_args.args == ([str(root / SHELL), "--workspace", "assets"],)
    assert popen.call_args.kwargs["cwd"] == root
    if os.name == "nt": assert popen.call_args.kwargs["creationflags"] & 0x08000000
    apply(service, "sdk_uninstall")
    retired = next(root.parent.glob(root.name + ".uninstalled-*"))
    assert (retired / "personal.xml").read_bytes() == b"user project"
    assert not root.exists() and original == service.tree_identity(game)


def test_sdk_open_missing_payload_or_unknown_workspace_never_spawns(service, monkeypatch):
    popen = Mock(side_effect=AssertionError("process launch forbidden"))
    monkeypatch.setattr(desktop_service.subprocess, "Popen", popen)
    with pytest.raises(ValueError, match="Unknown SDK workspace"):
        apply(service, "sdk_open", workspace="untrusted")
    with pytest.raises(ValueError): apply(service, "sdk_open")
    popen.assert_not_called()


def test_sdk_release_install_requires_checked_identity_and_routes_progress(service, monkeypatch):
    with pytest.raises(ValueError, match="Check the latest"):
        service.review({"action": "sdk_install_release"})
    release = {"version": "0.6.4", "synthetic_test_only": True}
    monkeypatch.setattr(sdk_manager, "fetch_latest_sdk_release", lambda: release)
    assert service.read("check_sdk_update", {}) == release
    calls = []
    def install(selected, root, *, progress):
        calls.append((selected, root))
        progress("Synthetic bounded download", 1, 2)
        return {"synthetic_test_only": True}
    monkeypatch.setattr(sdk_manager, "install_sdk_release", install)
    progress = Mock()
    service.progress = progress
    apply(service, "sdk_install_release")
    assert calls == [(release, service.sdk_root)]
    assert any(call.args == (50, "Synthetic bounded download") for call in progress.call_args_list)


def test_diagnostic_export_and_config_sync_preserve_saves(service, tmp_path):
    config = service.config()
    config.script.ui_scale = 1.25
    result = apply(service, "sync_config", config=desktop_service.serializable(config))
    assert result["saved_config"]["script"]["ui_scale"] == 1.25
    destination = tmp_path / "Diagnostics with spaces.zip"
    apply(service, "diagnostics", destination=str(destination))
    with zipfile.ZipFile(destination) as bundle:
        assert bundle.namelist()
        assert bundle.testzip() is None


@pytest.mark.skipif(os.name != "nt", reason="Windows shell dispatch contract")
def test_launcher_release_and_activity_shell_actions_use_fixed_targets(service, monkeypatch):
    from allin1 import versioning
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(str(path)))
    with pytest.raises(ValueError, match="Check Launcher"):
        service.read("open_launcher_release", {})
    with pytest.raises(ValueError, match="No activity"):
        service.read("open_activity_folder", {})
    release = {"version": "0.6.4", "url": "file:///untrusted.exe"}
    monkeypatch.setattr(versioning, "fetch_latest_release", lambda: release)
    service.read("check_update", {})
    result = service.read("open_launcher_release", {"url": "file:///untrusted.exe"})
    assert result["opened"] == "https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/latest"
    apply(service, "save_config")
    service.read("open_activity_folder", {})
    assert opened == [result["opened"], str(service.state / "logs")]
