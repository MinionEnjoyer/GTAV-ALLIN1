"""Tests for the UI-facing management service."""

from pathlib import Path
from unittest.mock import Mock

from allin1.config import Config
from allin1.manager import ModManager


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
    (tmp_path / "ScriptHookV.dll").touch()
    (tmp_path / "ScriptHookVDotNet.asi").touch()
    (tmp_path / "OpenIV.asi").touch()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "ALLIN1.dll").touch()
    config = Config.default()
    config.general.gta_path = str(tmp_path)

    status = _manager(tmp_path).status(config)

    assert status.valid_game is True
    assert status.edition == "Legacy"
    assert status.mod_installed is True
    assert status.scripthookv_installed is True
    assert status.shvdn_installed is True
    assert status.openrpf_installed is True


def test_status_reports_invalid_manual_path(tmp_path):
    missing = tmp_path / "missing-game"
    config = Config.default()
    config.general.gta_path = str(missing)

    status = _manager(tmp_path).status(config)

    assert status.gta_path == missing
    assert status.valid_game is False
    assert status.edition == "Unknown"
    assert status.mod_installed is False


def test_install_saves_config_and_delegates(tmp_path):
    install_fn = Mock(return_value=object())
    manager = _manager(tmp_path, install_fn=install_fn)
    config = Config.default()
    config.general.gta_path = r"C:\Games\Grand Theft Auto V"

    result = manager.install(config)

    assert result is install_fn.return_value
    assert Config.load(tmp_path / "config.toml").general.gta_path == config.general.gta_path
    install_fn.assert_called_once()


def test_uninstall_delegates_without_loading_database(tmp_path):
    uninstall_fn = Mock(return_value=[tmp_path / "scripts" / "ALLIN1.dll"])
    manager = _manager(tmp_path, uninstall_fn=uninstall_fn)
    config = Config.default()

    removed = manager.uninstall(config)

    assert removed == uninstall_fn.return_value
    uninstall_fn.assert_called_once_with(config)
