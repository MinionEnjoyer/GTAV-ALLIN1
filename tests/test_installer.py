"""Unit tests for game-file installation orchestration."""

from pathlib import Path
from unittest.mock import Mock

from allin1.config import Config
from allin1 import installer


def _game(tmp_path: Path, enhanced: bool = False) -> Path:
    game = tmp_path / "Grand Theft Auto V"
    game.mkdir()
    (game / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    return game


def test_resolve_gta_path_uses_configured_path(tmp_path):
    game = _game(tmp_path)
    config = Config.default()
    config.general.gta_path = str(game)

    assert installer.resolve_gta_path(config) == game


def test_resolve_gta_path_reports_failed_detection(monkeypatch):
    monkeypatch.setattr(installer, "detect_gta_path", lambda: None)
    config = Config.default()

    try:
        installer.resolve_gta_path(config)
    except FileNotFoundError as exc:
        assert "auto-detect" in str(exc)
    else:
        raise AssertionError("Expected failed auto-detection to raise")


def test_deploy_script_copies_binaries_and_config(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    (dist / "ALLIN1.dll").write_bytes(b"mod")
    (dist / "LemonUI.SHVDN3.dll").write_bytes(b"ui")
    (project / "config.toml").write_text("[general]\ngta_path='auto'\n")
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    (scripts / "ALLIN1.ini").touch()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game) is True
    assert (scripts / "ALLIN1.dll").read_bytes() == b"mod"
    assert (scripts / "LemonUI.SHVDN3.dll").read_bytes() == b"ui"
    assert (scripts / "ALLIN1.toml").exists()
    assert not (scripts / "ALLIN1.ini").exists()


def test_deploy_script_returns_false_when_binary_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", tmp_path / "missing")
    assert installer._deploy_script(_game(tmp_path)) is False


def test_prerequisite_checks(tmp_path):
    game = _game(tmp_path)
    assert installer._check_scripthookv(game) is False
    assert installer._check_shvdn(game) is False
    (game / "ScriptHookV.dll").touch()
    (game / "ScriptHookVDotNet.asi").touch()
    assert installer._check_scripthookv(game) is True
    assert installer._check_shvdn(game) is True


def test_legacy_openiv_check_does_not_download(tmp_path):
    game = _game(tmp_path)
    assert installer._check_openrpf(game, enhanced=False) is False
    (game / "OpenIV.asi").touch()
    assert installer._check_openrpf(game, enhanced=False) is True


def test_uninstall_removes_owned_files_and_preserves_other_flags(tmp_path, monkeypatch):
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    for name in ("ALLIN1.dll", "ALLIN1.toml", "ALLIN1_garage.json"):
        (scripts / name).touch()
    (game / "commandline.txt").write_text("-windowed\n-nobattleye\n")
    config = Config.default()
    config.general.gta_path = str(game)
    unpatch = Mock()
    remove_ytds = Mock()
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    monkeypatch.setattr(installer, "_remove_preview_ytds", remove_ytds)

    removed = installer.uninstall(config)

    assert not (scripts / "ALLIN1.dll").exists()
    assert not (scripts / "ALLIN1.toml").exists()
    assert (game / "commandline.txt").read_text() == "-windowed\n"
    assert scripts / "ALLIN1.dll" in removed
    unpatch.assert_called_once_with(game)
    remove_ytds.assert_called_once_with(game)


def test_uninstall_removes_commandline_when_only_battleye_flag(tmp_path, monkeypatch):
    game = _game(tmp_path)
    (game / "commandline.txt").write_text("-nobattleye\n")
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())

    installer.uninstall(config)

    assert not (game / "commandline.txt").exists()


def test_clean_legacy_files_removes_old_runtime_and_data(tmp_path):
    game = _game(tmp_path)
    (game / "ALLIN1.asi").touch()
    (game / "ALLIN1.dll").touch()
    data = game / "ALLIN1"
    data.mkdir()
    (data / "old.json").write_text("{}")
    result = installer.InstallResult(game)

    installer._clean_legacy_files(game, result)

    assert not (game / "ALLIN1.asi").exists()
    assert not (game / "ALLIN1.dll").exists()
    assert not data.exists()
    assert len(result.warnings) == 3


def test_uninstall_removes_legacy_preview_locations(tmp_path, monkeypatch):
    game = _game(tmp_path)
    previews = game / "scripts" / "previews"
    previews.mkdir(parents=True)
    (previews / "car.png").touch()
    (game / "scripts" / "PHAT.png").touch()
    dlc = game / "mods" / "update" / "x64" / "dlcpacks" / "allin1_previews"
    dlc.mkdir(parents=True)
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())

    installer.uninstall(config)

    assert not previews.exists()
    assert not (game / "scripts" / "PHAT.png").exists()
    assert not dlc.exists()


def test_install_orchestrates_steps_and_collects_preview_warning(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_clean_legacy_files", Mock())
    monkeypatch.setattr(installer, "_deploy_script", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_scripthookv", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_shvdn", Mock(return_value=False))
    monkeypatch.setattr(installer, "_check_openrpf", Mock(return_value=True))
    monkeypatch.setattr(installer, "_deploy_preview_dlc", Mock(side_effect=RuntimeError("preview failed")))
    patch = Mock()
    monkeypatch.setattr(installer, "_patch_dlclist_rpf", patch)
    monkeypatch.setattr(installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"))

    result = installer.install(config, Mock())

    assert result.is_enhanced is True
    assert result.dll_deployed is True
    assert result.shvdn_found is False
    assert result.battleye_status == "set"
    assert result.warnings == ["Preview DLC pack failed: preview failed"]
    patch.assert_not_called()
