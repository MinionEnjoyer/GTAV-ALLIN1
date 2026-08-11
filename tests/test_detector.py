"""Cross-platform tests for GTA installation discovery."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from allin1 import detector


def _game(path: Path, enhanced: bool = False) -> Path:
    path.mkdir(parents=True)
    (path / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    return path


def test_validate_accepts_both_editions_and_rejects_invalid(tmp_path):
    assert detector.validate_gta_path(_game(tmp_path / "legacy")) == tmp_path / "legacy"
    assert detector.validate_gta_path(_game(tmp_path / "enhanced", True)) == tmp_path / "enhanced"
    with pytest.raises(ValueError):
        detector.validate_gta_path(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="GTA5.exe"):
        detector.validate_gta_path(empty)


def test_cache_round_trip_and_invalid_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "_project_root", lambda: tmp_path)
    game = _game(tmp_path / "game")
    detector.save_cached_path(game)
    assert detector.load_cached_path() == game
    (tmp_path / ".gta_path").write_text(str(tmp_path / "gone"))
    assert detector.load_cached_path() is None
    (tmp_path / ".gta_path").write_text("")
    assert detector.load_cached_path() is None


@pytest.mark.parametrize("system,target", [("Windows", "win"), ("Linux", "linux"), ("Darwin", None)])
def test_platform_dispatch_and_cache(system, target, tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "load_cached_path", lambda: None)
    monkeypatch.setattr(detector.platform, "system", lambda: system)
    found = _game(tmp_path / target) if target else None
    monkeypatch.setattr(detector, "_detect_windows", lambda: found)
    monkeypatch.setattr(detector, "_detect_linux", lambda: found)
    save = Mock()
    monkeypatch.setattr(detector, "save_cached_path", save)
    assert detector.detect_gta_path() == found
    assert save.call_count == (1 if found else 0)


def test_cached_path_short_circuits_detection(tmp_path, monkeypatch):
    game = _game(tmp_path / "game")
    monkeypatch.setattr(detector, "load_cached_path", lambda: game)
    monkeypatch.setattr(detector, "_detect_windows", Mock())
    assert detector.detect_gta_path() == game
    detector._detect_windows.assert_not_called()


def test_parse_appmanifest(tmp_path):
    manifest = tmp_path / "app.acf"
    manifest.write_text('"installdir"  "Grand Theft Auto V"')
    assert detector._parse_appmanifest_installdir(manifest) == "Grand Theft Auto V"
    assert detector._parse_appmanifest_installdir(tmp_path / "missing") is None


def test_parse_steam_vdf_new_and_old_formats(tmp_path):
    vdf = tmp_path / "libraryfolders.vdf"
    vdf.write_text('"path" "D:\\\\SteamLibrary"\n"path" "E:\\\\Games"')
    assert detector._parse_steam_vdf(vdf) == [Path("D:\\SteamLibrary"), Path("E:\\Games")]
    vdf.write_text('"1" "F:\\\\Steam"')
    assert detector._parse_steam_vdf(vdf) == [Path("F:\\Steam")]
    assert detector._parse_steam_vdf(tmp_path / "absent") == []


def test_parse_config_vdf(tmp_path):
    config = tmp_path / "config.vdf"
    config.write_text('"BaseInstallFolder_1" "D:\\\\Games"')
    assert detector._parse_config_vdf(config) == [Path("D:\\Games")]
    assert detector._parse_config_vdf(tmp_path / "missing") == []


def test_find_via_steam_manifest(tmp_path, monkeypatch):
    library = tmp_path / "Steam"
    game = _game(library / "steamapps" / "common" / "GTAV")
    manifest = library / "steamapps" / "appmanifest_271590.acf"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('"installdir" "GTAV"')
    monkeypatch.setattr(detector, "_find_all_steam_libraries", lambda: [library])
    assert detector._find_via_steam_appmanifest() == game


def test_steamapps_directory_finds_known_manifest(tmp_path):
    steamapps = tmp_path / "steamapps"
    game = _game(steamapps / "common" / "GTAV")
    steamapps.mkdir(exist_ok=True)
    (steamapps / "appmanifest_271590.acf").write_text('"installdir" "GTAV"')
    assert detector._check_steamapps_dir(steamapps) == game


def test_windows_pipeline_stops_at_first_result(tmp_path, monkeypatch):
    game = _game(tmp_path / "game")
    steam = Mock(return_value=game)
    registry = Mock()
    monkeypatch.setattr(detector, "_find_via_steam_appmanifest", steam)
    monkeypatch.setattr(detector, "_check_registry", registry)
    assert detector._detect_windows() == game
    registry.assert_not_called()


def test_hardcoded_paths_and_deep_scan(tmp_path):
    drive = tmp_path / "C"
    expected = _game(drive / "Games" / "Grand Theft Auto V")
    assert detector._check_hardcoded_paths([drive]) == expected
    assert detector._deep_scan_windows([]) is None


def test_get_windows_drives_uses_existing_letters(monkeypatch):
    monkeypatch.setattr(detector.string, "ascii_uppercase", "AB")
    monkeypatch.setattr(detector.Path, "exists", lambda self: str(self).startswith("A"))
    assert detector._get_windows_drives() == [Path("A:\\")]
