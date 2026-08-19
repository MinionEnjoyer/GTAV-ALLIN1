"""Tests for the UI-facing management service."""

from pathlib import Path
import json
import struct
from unittest.mock import Mock

import pytest

from allin1.config import Config
from allin1.manager import ModManager


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _manager(tmp_path: Path, **kwargs) -> ModManager:
    data = tmp_path / "data"
    data.mkdir()
    (data / "vehicles.toml").write_text(
        '[[vehicles]]\nmodel="testcar"\nname="Test Car"\n'
        'class="compacts"\nmanufacturer="Test"\ntraffic=[]\n',
        encoding="utf-8",
    )
    return ModManager(tmp_path, **kwargs)


def test_status_reports_complete_legacy_install(tmp_path):
    (tmp_path / "GTA5.exe").touch()
    _write_pe(tmp_path / "ScriptHookV.dll")
    _write_pe(tmp_path / "ScriptHookVDotNet.asi")
    _write_pe(tmp_path / "OpenIV.asi")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    _write_pe(scripts / "ALLIN1.dll")
    (scripts / "ALLIN1.version").write_text("0.2.0\n")
    config = Config.default()
    config.general.gta_path = str(tmp_path)

    status = _manager(tmp_path).status(config)

    assert status.valid_game is True
    assert status.edition == "Legacy"
    assert status.mod_installed is True
    assert status.scripthookv_installed is True
    assert status.shvdn_installed is True
    assert status.openrpf_installed is True
    assert status.rpf_loader_status == "Installed (file validated)"
    assert status.installed_version == "0.2.0"
    assert status.manager_version == "0.5.0"


def test_status_reports_invalid_manual_path(tmp_path):
    missing = tmp_path / "missing-game"
    config = Config.default()
    config.general.gta_path = str(missing)

    status = _manager(tmp_path).status(config)

    assert status.gta_path == missing
    assert status.valid_game is False
    assert status.edition == "Unknown"
    assert status.mod_installed is False


def test_status_distinguishes_disabled_openrpf_from_missing_loader(tmp_path):
    (tmp_path / "GTA5_Enhanced.exe").touch()
    (tmp_path / "dinput8.dll").write_bytes(b"loader")
    disabled = tmp_path / "allin1_backups" / "DisabledPlugins"
    disabled.mkdir(parents=True)
    (disabled / "OpenRPF.asi.disabled").write_bytes(b"plugin")
    config = Config.default()
    config.general.gta_path = str(tmp_path)

    status = _manager(tmp_path).status(config)

    assert status.openrpf_installed is False
    assert status.rpf_loader_status == "Disabled"


def test_install_saves_config_and_delegates(tmp_path):
    install_fn = Mock(return_value=object())
    manager = _manager(tmp_path, install_fn=install_fn)
    config = Config.default()
    config.general.gta_path = r"C:\Games\Grand Theft Auto V"

    result = manager.install(config)

    assert result is install_fn.return_value
    assert Config.load(tmp_path / "config.toml").general.gta_path == config.general.gta_path
    install_fn.assert_called_once()


def test_install_forwards_progress_callback(tmp_path):
    install_fn = Mock(return_value=object())
    manager = _manager(tmp_path, install_fn=install_fn)
    config = Config.default()
    progress = Mock()

    manager.install(config, progress=progress)

    assert install_fn.call_args.kwargs == {"progress": progress}


def test_save_config_cleans_retired_owned_offline_launch_policy(
    tmp_path, monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    manager = _manager(project)
    game = tmp_path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").touch()
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr("allin1.manager.detect_gta_path", lambda: None)
    (game / "commandline.txt").write_text("-scofflineonly\n")
    state = game / "scripts/.allin1/launch-policy.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({
        "schema_version": 1, "argument": "-scofflineonly",
        "inserted": True, "created_file": True,
    }))

    manager.save_config(config)
    assert not (game / "commandline.txt").exists()
    assert not state.exists()
    runtime_config = game / "scripts/ALLIN1.toml"
    assert runtime_config.is_file()
    assert "story_mode_only" not in runtime_config.read_text()


def test_save_config_cleans_retired_policy_from_both_configured_editions(
    tmp_path, monkeypatch,
):
    project = tmp_path / "project"
    project.mkdir()
    manager = _manager(project)
    legacy = tmp_path / "legacy"
    enhanced = tmp_path / "enhanced"
    legacy.mkdir()
    enhanced.mkdir()
    (legacy / "GTA5.exe").touch()
    (enhanced / "GTA5_Enhanced.exe").touch()
    config = Config.default()
    config.general.gta_legacy_path = str(legacy)
    config.general.gta_enhanced_path = str(enhanced)
    monkeypatch.setattr("allin1.manager.detect_gta_path", lambda: None)
    for game in (legacy, enhanced):
        (game / "commandline.txt").write_text("-scofflineonly\n")
        state = game / "scripts/.allin1/launch-policy.json"
        state.parent.mkdir(parents=True)
        state.write_text(json.dumps({
            "schema_version": 1, "argument": "-scofflineonly",
            "inserted": True, "created_file": True,
        }))
    manager.save_config(config)

    assert not (legacy / "commandline.txt").exists()
    assert not (enhanced / "commandline.txt").exists()


def test_uninstall_delegates_without_loading_database(tmp_path):
    uninstall_fn = Mock(return_value=[tmp_path / "scripts" / "ALLIN1.dll"])
    manager = _manager(tmp_path, uninstall_fn=uninstall_fn)
    config = Config.default()

    removed = manager.uninstall(config)

    assert removed == uninstall_fn.return_value
    uninstall_fn.assert_called_once_with(config)


def test_load_config_precedence_and_auto_detection_none(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    assert manager.load_config() == Config.default()
    (tmp_path / "config.example.toml").write_text("[general]\nfree_mode=true\n")
    assert manager.load_config().general.free_mode is True
    config = Config.default()
    config.general.free_mode = False
    config.save(tmp_path / "config.toml")
    assert manager.load_config().general.free_mode is False
    monkeypatch.setattr("allin1.manager.detect_gta_path", lambda: None)
    assert manager.resolve_path(Config.default()) is None
    assert manager.status(Config.default()).gta_path is None


def test_resolve_paths_keeps_legacy_and_enhanced_installations_independent(
    tmp_path, monkeypatch,
):
    legacy = tmp_path / "legacy"
    enhanced = tmp_path / "enhanced"
    legacy.mkdir()
    enhanced.mkdir()
    (legacy / "GTA5.exe").touch()
    (enhanced / "GTA5_Enhanced.exe").touch()
    config = Config.default()
    config.general.gta_legacy_path = str(legacy)
    config.general.gta_enhanced_path = str(enhanced)
    config.general.target_edition = "legacy"
    manager = _manager(tmp_path)
    monkeypatch.setattr("allin1.manager.detect_gta_path", lambda: None)

    assert manager.resolve_paths(config) == {
        "legacy": legacy,
        "enhanced": enhanced,
    }
    assert manager.resolve_path(config) == legacy
    assert manager.resolve_mod_path(config, ("enhanced",)) == enhanced


def test_resolve_mod_path_reports_missing_compatible_edition(tmp_path, monkeypatch):
    enhanced = tmp_path / "enhanced"
    enhanced.mkdir()
    (enhanced / "GTA5_Enhanced.exe").touch()
    config = Config.default()
    config.general.gta_enhanced_path = str(enhanced)
    manager = _manager(tmp_path)
    monkeypatch.setattr("allin1.manager.detect_gta_path", lambda: None)

    with pytest.raises(ValueError, match="No configured Legacy"):
        manager.resolve_mod_path(config, ("legacy",))
