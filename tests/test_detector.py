"""Cross-platform tests for GTA installation discovery."""

import os
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
import sys

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


@pytest.mark.parametrize("cached", [True, False])
def test_read_only_discovery_never_publishes_cache(tmp_path, monkeypatch, cached):
    game = _game(tmp_path / "owned game")
    monkeypatch.setattr(detector, "load_cached_path", lambda: game if cached else None)
    monkeypatch.setattr(detector.platform, "system", lambda: "Windows")
    monkeypatch.setattr(detector, "_detect_windows", lambda: game)
    monkeypatch.setattr(detector, "save_cached_path", lambda *_: pytest.fail("Read-only discovery wrote a cache"))
    assert detector.inspect_detected_gta_path() == game
    assert detector.inspect_gta_path(game) == game
    with pytest.raises(ValueError): detector.inspect_gta_path(tmp_path / "missing")


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
    assert detector._find_via_steam_appmanifest().samefile(game)


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


@pytest.mark.parametrize("winner", [
    "_find_via_steam_appmanifest", "_check_registry",
    "_check_steam_uninstall_registry", "_find_epic_install_windows",
    "_find_rockstar_launcher_windows", "_check_hardcoded_paths",
    "_deep_scan_windows",
])
def test_windows_detection_pipeline_reaches_each_fallback(tmp_path, monkeypatch, winner):
    game = _game(tmp_path / "game")
    ordered = [
        "_find_via_steam_appmanifest", "_check_registry",
        "_check_steam_uninstall_registry", "_find_epic_install_windows",
        "_find_rockstar_launcher_windows", "_check_hardcoded_paths",
        "_deep_scan_windows",
    ]
    monkeypatch.setattr(detector, "_get_windows_drives", lambda: [tmp_path])
    for name in ordered:
        monkeypatch.setattr(detector, name, Mock(return_value=game if name == winner else None))
    assert detector._detect_windows() == game
    for name in ordered[ordered.index(winner) + 1:]:
        getattr(detector, name).assert_not_called()


def test_find_all_steam_libraries_combines_and_deduplicates_sources(tmp_path, monkeypatch):
    steam = tmp_path / "Steam"
    (steam / "steamapps").mkdir(parents=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        f'"path" "{tmp_path / "Library"}"'
    )
    (steam / "config").mkdir()
    (steam / "config" / "config.vdf").write_text(
        f'"BaseInstallFolder_1" "{tmp_path / "Library"}"'
    )
    monkeypatch.setattr(detector, "_get_steam_path_from_registry", lambda: [steam, steam])
    monkeypatch.setattr(detector, "_get_windows_drives", lambda: [])
    assert detector._find_all_steam_libraries() == [steam, tmp_path / "Library"]


def test_epic_manifest_and_fallback_detection(tmp_path, monkeypatch):
    manifests = tmp_path / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    manifests.mkdir(parents=True)
    game = _game(tmp_path / "EpicGame")
    (manifests / "gta.item").write_text(
        '{"DisplayName":"GTA V","InstallLocation":"' + str(game) + '"}'
    )
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    assert detector._find_epic_install_windows() == game

    (manifests / "gta.item").unlink()
    drive = tmp_path / "drive"
    fallback = _game(drive / "Epic Games" / "GTAV")
    monkeypatch.setattr(detector, "_get_windows_drives", lambda: [drive])
    assert detector._find_epic_install_windows() == fallback


def test_rockstar_settings_and_deep_scan_detection(tmp_path, monkeypatch):
    settings = tmp_path / "Rockstar Games" / "Launcher" / "settings_user.dat"
    settings.parent.mkdir(parents=True)
    settings.write_bytes(b'C:\\Games\\Grand Theft Auto V\x00')
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(detector, "_validate_gta_path", lambda p: "Grand Theft Auto V" in str(p))
    assert detector._find_rockstar_launcher_windows() is not None

    drive = tmp_path / "scan"
    game = _game(drive / "one" / "two" / "GTAV")
    monkeypatch.setattr(detector, "_validate_gta_path",
                        lambda p: (p / "GTA5.exe").exists())
    assert detector._deep_scan_windows([drive]) == game


def test_linux_detection_uses_manifest_and_direct_fallback(tmp_path, monkeypatch):
    home = tmp_path / "home"
    root = home / ".local" / "share" / "Steam"
    steamapps = root / "steamapps"
    game = _game(steamapps / "common" / "CustomGTAV")
    steamapps.mkdir(parents=True, exist_ok=True)
    (steamapps / "appmanifest_271590.acf").write_text('"installdir" "CustomGTAV"')
    monkeypatch.setattr(detector.Path, "home", lambda: home)
    assert detector._detect_linux() == game

    (steamapps / "appmanifest_271590.acf").unlink()
    game.rename(steamapps / "common" / "Grand Theft Auto V")
    assert detector._detect_linux() == steamapps / "common" / "Grand Theft Auto V"


def test_detector_io_error_branches(tmp_path, monkeypatch):
    path = tmp_path / "file"
    path.touch()
    monkeypatch.setattr(detector.Path, "read_text", Mock(side_effect=OSError("denied")))
    assert detector._parse_steam_vdf(path) == []
    assert detector._parse_config_vdf(path) == []
    assert detector._parse_appmanifest_installdir(path) is None


def test_registry_detectors_and_steam_paths(tmp_path, monkeypatch):
    game = _game(tmp_path / "game")

    class Key:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    fake = SimpleNamespace(
        HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2,
        OpenKey=lambda *_args: Key(),
        QueryValueEx=lambda _key, value: (
            str(game) if value in ("InstallFolder", "InstallLocation")
            else str(tmp_path / "Steam").replace("\\", "/"), None
        ),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert detector._check_registry() == game
    assert detector._check_steam_uninstall_registry() == game
    paths = detector._get_steam_path_from_registry()
    assert paths


def test_cache_and_detection_write_error_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(detector, "_project_root", lambda: tmp_path)
    assert detector.load_cached_path() is None
    cache = tmp_path / ".gta_path"
    cache.write_text("not-a-game")
    assert detector.load_cached_path() is None
    monkeypatch.setattr(detector.Path, "write_text", Mock(side_effect=OSError("readonly")))
    detector.save_cached_path(tmp_path)


def test_find_via_steam_handles_uppercase_and_bad_manifests(tmp_path, monkeypatch):
    library = tmp_path / "Library"
    steamapps = library / "SteamApps"
    steamapps.mkdir(parents=True)
    manifest = steamapps / "appmanifest_271590.acf"
    manifest.write_text("bad")
    monkeypatch.setattr(detector, "_find_all_steam_libraries", lambda: [tmp_path / "none", library])
    assert detector._find_via_steam_appmanifest() is None
    game = _game(steamapps / "common" / "GTAV")
    manifest.write_text('"installdir" "GTAV"')
    assert detector._find_via_steam_appmanifest().samefile(game)


@pytest.mark.parametrize("mode", ["absent-module", "missing-key", "empty", "invalid"])
def test_registry_fallbacks_never_guess_an_installation(tmp_path, monkeypatch, mode):
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    def open_key(*args):
        if mode == "missing-key": raise FileNotFoundError("synthetic missing key")
        return Key()
    fake = SimpleNamespace(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2, OpenKey=open_key,
        QueryValueEx=lambda *args: ("" if mode == "empty" else str(tmp_path / "not installed"), None))
    monkeypatch.setitem(sys.modules, "winreg", None if mode == "absent-module" else fake)
    assert detector._check_registry() is None
    assert detector._check_steam_uninstall_registry() is None
    paths = detector._get_steam_path_from_registry()
    assert len(paths) == (3 if mode == "invalid" else 0)


@pytest.mark.parametrize("relative", ["GTAV", "Library/Grand Theft Auto V", "Library/Games/GTA V",
    "steamapps/common/CustomGame", "Library/steamapps/common/CustomGame", "Library/Steam/steamapps/common/CustomGame"])
def test_deep_scan_is_bounded_to_supplied_disposable_drive(tmp_path, relative):
    drive = tmp_path / "drive"
    game = _game(drive / relative)
    for directory in [drive, game.parent]: (directory / "ignore-file.txt").write_bytes(b"not a directory")
    if "steamapps" in relative:
        steamapps = game.parent.parent
        (steamapps / "appmanifest_3240220.acf").write_text('"installdir" "CustomGame"', encoding="utf-8")
    assert detector._deep_scan_windows([drive]) == game


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_deep_scan_permission_denied_skips_only_unreadable_directory(tmp_path, monkeypatch, depth):
    drive = tmp_path / "drive"
    blocked = drive.joinpath(*(["nested"] * depth))
    (blocked / "child").mkdir(parents=True)
    real = Path.iterdir
    def iterdir(path):
        if path == blocked: raise PermissionError("synthetic denied directory")
        return real(path)
    monkeypatch.setattr(Path, "iterdir", iterdir)
    assert detector._deep_scan_windows([drive]) is None


@pytest.mark.parametrize("damage", ["none", "invalid-path", "unreadable"])
@pytest.mark.skipif(os.name != "nt", reason="Windows absolute path in Rockstar settings")
def test_rockstar_settings_detection_is_read_only(tmp_path, monkeypatch, damage):
    game = _game(tmp_path / "Grand Theft Auto V Enhanced")
    settings = tmp_path / "Rockstar Games/Launcher/settings_user.dat"
    settings.parent.mkdir(parents=True)
    selected = game if damage != "invalid-path" else tmp_path / "missing Grand Theft Auto V"
    raw = b"header\x00" + str(selected).encode() + b"\x00footer"
    settings.write_bytes(raw)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    if damage == "unreadable":
        real = Path.read_bytes
        def read(path):
            if path == settings: raise PermissionError("synthetic settings permission")
            return real(path)
        monkeypatch.setattr(Path, "read_bytes", read)
    assert detector._find_rockstar_launcher_windows() == (game if damage == "none" else None)


def test_epic_manifest_noise_unreadable_and_fallback_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setattr(detector, "_get_windows_drives", lambda: [tmp_path / "drive"])
    manifests = tmp_path / "Epic/EpicGamesLauncher/Data/Manifests"
    manifests.mkdir(parents=True)
    (manifests / "other.item").write_text('{"Name":"Other Game"}', encoding="utf-8")
    (manifests / "bad.item").write_text('{"Name":"GTA"}', encoding="utf-8")
    unreadable = manifests / "denied.item"
    unreadable.write_text("GTA", encoding="utf-8")
    real = Path.read_text
    def read(path, *args, **kwargs):
        if path == unreadable: raise PermissionError("synthetic denied manifest")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    assert detector._find_epic_install_windows() is None
    game = _game(tmp_path / "drive/Epic Games/Grand Theft Auto V Enhanced")
    assert detector._find_epic_install_windows() == game


def test_cached_path_read_error_is_nonfatal(tmp_path, monkeypatch):
    (tmp_path / ".gta_path").write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=PermissionError("synthetic denied cache")))
    assert detector.load_cached_path() is None
