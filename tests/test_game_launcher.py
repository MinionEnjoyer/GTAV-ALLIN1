import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from allin1 import game_launcher
from allin1.game_launcher import (
    GtaRuntimeState,
    LaunchTarget,
    launch_gta,
    observe_gta_launch,
    probe_gta_runtime,
    resolve_launch_target,
)


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
    assert target.location == f"steam://run/{app_id}"
    assert target.edition == edition
    assert target.arguments == ()
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

    opener.assert_called_once_with("steam://run/3240220")
    starter.assert_not_called()
    assert target.method == "steam"
    assert target.arguments == ()


def test_launch_gta_starts_local_executable(tmp_path):
    game = _game(tmp_path)
    (game / "PlayGTAV.exe").touch()
    opener = Mock()
    starter = Mock()

    target = launch_gta(game, uri_opener=opener, process_starter=starter)

    starter.assert_called_once_with(
        game / "PlayGTAV.exe", game, ("-nobattleye",),
    )
    opener.assert_not_called()
    assert target.method == "executable"


def test_default_steam_launcher_uses_windows_shell(tmp_path, monkeypatch):
    game = _game(tmp_path, steam=True)
    (game.parent.parent / "appmanifest_3240220.acf").touch()
    startfile = Mock()
    monkeypatch.setattr("allin1.game_launcher.os.startfile", startfile, raising=False)

    launch_gta(game)

    startfile.assert_called_once_with("steam://run/3240220")


def test_default_executable_launcher_suppresses_console(tmp_path, monkeypatch):
    game = _game(tmp_path)
    (game / "PlayGTAV.exe").touch()
    popen = Mock()
    monkeypatch.setattr("allin1.game_launcher.subprocess.Popen", popen)

    launch_gta(game)

    popen.assert_called_once_with(
        [str(game / "PlayGTAV.exe"), "-nobattleye"],
        cwd=str(game),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_observe_launch_confirms_visible_game_window():
    target = LaunchTarget("steam", "steam://run/3240220", "Enhanced")

    result = observe_gta_launch(
        target,
        runtime_probe=lambda _target: GtaRuntimeState((321,), 321),
    )

    assert result.status == "success"
    assert result.process_id == 321
    assert result.window_visible is True
    assert result.message == "GTA V Enhanced window is running (PID 321)."


def test_observe_launch_requires_process_to_remain_stable_without_window():
    target = LaunchTarget("steam", "steam://run/271590", "Legacy")
    clock = _FakeClock()
    pending = []

    result = observe_gta_launch(
        target,
        timeout_seconds=5,
        stability_seconds=1,
        poll_interval_seconds=0.5,
        runtime_probe=lambda _target: GtaRuntimeState((456,), None),
        monotonic=clock,
        sleeper=clock.sleep,
        on_pending=pending.append,
    )

    assert result.status == "success"
    assert result.process_id == 456
    assert result.window_visible is False
    assert "window is still initializing" in result.message
    assert [item.status for item in pending] == ["pending"]
    assert clock.value == 1.0


def test_default_process_fallback_does_not_accept_a_two_second_startup_crash():
    target = LaunchTarget("steam", "steam://run/3240220", "Enhanced")
    clock = _FakeClock()
    states = iter([
        GtaRuntimeState((901,), None),
        GtaRuntimeState((901,), None),
        GtaRuntimeState((901,), None),
        GtaRuntimeState(),
    ])

    result = observe_gta_launch(
        target,
        timeout_seconds=3,
        poll_interval_seconds=1,
        runtime_probe=lambda _target: next(states),
        monotonic=clock,
        sleeper=clock.sleep,
    )

    assert result.status == "failure"
    assert "appeared briefly" in result.message


def test_observe_launch_reports_transient_process_and_actionable_timeout():
    target = LaunchTarget("steam", "steam://run/3240220", "Enhanced")
    clock = _FakeClock()
    states = iter([
        GtaRuntimeState((777,), None),
        GtaRuntimeState(),
        GtaRuntimeState(),
    ])
    pending = []

    result = observe_gta_launch(
        target,
        timeout_seconds=1,
        stability_seconds=2,
        poll_interval_seconds=0.5,
        runtime_probe=lambda _target: next(states),
        monotonic=clock,
        sleeper=clock.sleep,
        on_pending=pending.append,
    )

    assert result.status == "failure"
    assert "within 1 seconds" in result.message
    assert "appeared briefly" in result.message
    assert "sign-in, update, or error prompt" in result.message
    assert any("exited before its window appeared" in item.message for item in pending)


def test_probe_runtime_filters_processes_for_target_edition(monkeypatch):
    target = LaunchTarget("executable", "PlayGTAV.exe", "Enhanced")
    monkeypatch.setattr(
        "allin1.game_launcher._windows_processes",
        lambda: {11: "gta5.exe", 22: "gta5_enhanced.exe", 33: "steam.exe"},
    )
    window_probe = Mock(return_value=22)
    monkeypatch.setattr(
        "allin1.game_launcher._largest_visible_window_pid", window_probe,
    )

    result = probe_gta_runtime(target)

    assert result == GtaRuntimeState((22,), 22)
    window_probe.assert_called_once_with({22})


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"timeout_seconds": 0}, "timeout"),
        ({"stability_seconds": -1}, "stability"),
        ({"poll_interval_seconds": 0}, "poll interval"),
    ],
)
def test_observe_launch_rejects_invalid_timing(kwargs, match):
    target = LaunchTarget("steam", "steam://run/3240220", "Enhanced")

    with pytest.raises(ValueError, match=match):
        observe_gta_launch(target, **kwargs)


class _FakeWinFunction:
    """Callable Windows API stand-in that also accepts ctypes metadata."""

    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


def test_windows_process_snapshot_enumerates_and_closes_handle(monkeypatch):
    entries = iter(((41, "GTA5.exe"), (42, "GTA5_Enhanced.exe")))

    def write_next(_snapshot, pointer):
        try:
            pid, name = next(entries)
        except StopIteration:
            return False
        pointer._obj.th32ProcessID = pid
        pointer._obj.szExeFile = name
        return True

    close = Mock(return_value=True)
    kernel32 = SimpleNamespace(
        CreateToolhelp32Snapshot=_FakeWinFunction(lambda *_args: 123),
        Process32FirstW=_FakeWinFunction(write_next),
        Process32NextW=_FakeWinFunction(write_next),
        CloseHandle=_FakeWinFunction(close),
    )
    monkeypatch.setattr(
        game_launcher.ctypes, "windll", SimpleNamespace(kernel32=kernel32),
    )

    assert game_launcher._windows_processes() == {
        41: "gta5.exe",
        42: "gta5_enhanced.exe",
    }
    close.assert_called_once_with(123)


def test_windows_process_snapshot_rejects_invalid_handle(monkeypatch):
    kernel32 = SimpleNamespace(
        CreateToolhelp32Snapshot=_FakeWinFunction(lambda *_args: 0),
        Process32FirstW=_FakeWinFunction(lambda *_args: False),
        Process32NextW=_FakeWinFunction(lambda *_args: False),
        CloseHandle=_FakeWinFunction(lambda *_args: True),
    )
    monkeypatch.setattr(
        game_launcher.ctypes, "windll", SimpleNamespace(kernel32=kernel32),
    )

    assert game_launcher._windows_processes() == {}


def test_largest_visible_window_uses_largest_matching_client(monkeypatch):
    visible = {1: False, 2: True, 3: True, 4: True, 5: True}
    iconic = {2: True}
    process_ids = {3: 999, 4: 51, 5: 52}
    rectangles = {
        4: (0, 0, 300, 200),
        5: (10, 20, 1290, 740),
    }

    def get_process_id(hwnd, pointer):
        pointer._obj.value = process_ids[hwnd]
        return 1

    def get_rect(hwnd, pointer):
        left, top, right, bottom = rectangles[hwnd]
        pointer._obj.left = left
        pointer._obj.top = top
        pointer._obj.right = right
        pointer._obj.bottom = bottom
        return True

    def enum_windows(callback, lparam):
        for hwnd in range(1, 6):
            assert callback(hwnd, lparam)
        return True

    user32 = SimpleNamespace(
        IsWindowVisible=lambda hwnd: visible[hwnd],
        IsIconic=lambda hwnd: iconic.get(hwnd, False),
        GetWindowThreadProcessId=get_process_id,
        GetWindowRect=get_rect,
        EnumWindows=enum_windows,
    )
    monkeypatch.setattr(
        game_launcher.ctypes, "windll", SimpleNamespace(user32=user32),
    )
    monkeypatch.setattr(
        game_launcher.ctypes,
        "WINFUNCTYPE",
        lambda *_args: lambda callback: callback,
    )

    assert game_launcher._largest_visible_window_pid({51, 52}) == 52
    assert game_launcher._largest_visible_window_pid(set()) is None
