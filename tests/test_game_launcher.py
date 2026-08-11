import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from allin1.game_launcher import launch_gta, resolve_launch_target


def _game(tmp_path: Path, *, enhanced: bool = True, steam: bool = False) -> Path:
    if steam:
        game = tmp_path / "Steam" / "steamapps" / "common" / "Grand Theft Auto V"
    else:
        game = tmp_path / "Grand Theft Auto V"
    game.mkdir(parents=True)
    (game / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    return game


@pytest.mark.parametrize(
    ("enhanced", "app_id", "edition"),
    [(True, "3240220", "Enhanced"), (False, "271590", "Legacy")],
)
def test_resolve_steam_launch_target(tmp_path, enhanced, app_id, edition):
    game = _game(tmp_path, enhanced=enhanced, steam=True)
    (game.parent.parent / f"appmanifest_{app_id}.acf").touch()

    target = resolve_launch_target(game)

    assert target.method == "steam"
    assert target.location == f"steam://rungameid/{app_id}"
    assert target.edition == edition
    assert target.description == f"GTA V {edition} through Steam"


def test_non_steam_prefers_rockstar_launcher(tmp_path):
    game = _game(tmp_path)
    (game / "PlayGTAV.exe").touch()

    target = resolve_launch_target(game)

    assert target.method == "executable"
    assert Path(target.location) == game / "PlayGTAV.exe"
    assert target.description.endswith("through PlayGTAV.exe")


def test_non_steam_falls_back_to_edition_executable(tmp_path):
    game = _game(tmp_path, enhanced=False)

    target = resolve_launch_target(game)

    assert Path(target.location) == game / "GTA5.exe"
    assert target.edition == "Legacy"


def test_resolve_rejects_missing_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        resolve_launch_target(tmp_path / "missing")


def test_resolve_rejects_directory_without_game_executable(tmp_path):
    with pytest.raises(ValueError, match="not launchable"):
        resolve_launch_target(tmp_path)


def test_launch_gta_opens_steam_uri(tmp_path):
    game = _game(tmp_path, steam=True)
    (game.parent.parent / "appmanifest_3240220.acf").touch()
    opener = Mock()
    starter = Mock()

    target = launch_gta(game, uri_opener=opener, process_starter=starter)

    opener.assert_called_once_with("steam://rungameid/3240220")
    starter.assert_not_called()
    assert target.method == "steam"


def test_launch_gta_starts_local_executable(tmp_path):
    game = _game(tmp_path)
    (game / "PlayGTAV.exe").touch()
    opener = Mock()
    starter = Mock()

    target = launch_gta(game, uri_opener=opener, process_starter=starter)

    starter.assert_called_once_with(game / "PlayGTAV.exe", game)
    opener.assert_not_called()
    assert target.method == "executable"


def test_default_steam_launcher_uses_windows_shell(tmp_path, monkeypatch):
    game = _game(tmp_path, steam=True)
    (game.parent.parent / "appmanifest_3240220.acf").touch()
    startfile = Mock()
    monkeypatch.setattr("allin1.game_launcher.os.startfile", startfile)

    launch_gta(game)

    startfile.assert_called_once_with("steam://rungameid/3240220")


def test_default_executable_launcher_suppresses_console(tmp_path, monkeypatch):
    game = _game(tmp_path)
    (game / "PlayGTAV.exe").touch()
    popen = Mock()
    monkeypatch.setattr("allin1.game_launcher.subprocess.Popen", popen)

    launch_gta(game)

    popen.assert_called_once_with(
        [str(game / "PlayGTAV.exe")],
        cwd=str(game),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
