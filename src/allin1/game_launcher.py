"""Resolve and start a GTA V installation without opening a console window."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


STEAM_APP_IDS = {
    "Legacy": "271590",
    "Enhanced": "3240220",
}

# ALLIN1 is a Story Mode launcher. Local executable launches carry the managed
# BattlEye opt-out explicitly. Steam launches deliberately use a bare
# ``steam://run/<appid>`` URI: putting custom arguments in that URI makes Steam
# show a confirmation dialog before every launch. The installer-managed
# commandline.txt remains the authoritative Steam-side Story configuration.
STORY_MODE_ARGUMENTS = ("-nobattleye",)
DEFAULT_LAUNCH_TIMEOUT_SECONDS = 90.0
# A process-only fallback is needed while GTA creates or replaces its first
# top-level window, but two seconds is short enough for a startup crash to look
# successful.  Ten seconds still keeps the launcher responsive while requiring
# a materially stable game process when no visible window can be observed.
DEFAULT_PROCESS_STABILITY_SECONDS = 10.0
DEFAULT_LAUNCH_POLL_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class LaunchTarget:
    """A storefront URI or local executable used to start GTA V."""

    method: Literal["steam", "executable"]
    location: str
    edition: str
    arguments: tuple[str, ...] = STORY_MODE_ARGUMENTS

    @property
    def description(self) -> str:
        if self.method == "steam":
            return f"GTA V {self.edition} through Steam"
        return f"GTA V {self.edition} through {Path(self.location).name}"


@dataclass(frozen=True)
class GtaRuntimeState:
    """Processes and a top-level window observed for one GTA edition."""

    process_ids: tuple[int, ...] = ()
    window_process_id: int | None = None

    @property
    def window_visible(self) -> bool:
        return self.window_process_id is not None


@dataclass(frozen=True)
class LaunchObservation:
    """A user-facing launch state based on GTA itself, not dispatch alone."""

    status: Literal["pending", "success", "failure"]
    message: str
    process_id: int | None = None
    window_visible: bool = False


RuntimeProbe = Callable[[LaunchTarget], GtaRuntimeState]


class _ProcessEntry32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    )


def resolve_launch_target(gta_path: Path | str) -> LaunchTarget:
    """Choose the safest available launch target for a GTA V directory."""
    game = Path(gta_path).expanduser()
    if not game.is_dir():
        raise FileNotFoundError(f"GTA V folder does not exist: {game}")

    enhanced = game / "GTA5_Enhanced.exe"
    legacy = game / "GTA5.exe"
    if enhanced.is_file():
        edition = "Enhanced"
    elif legacy.is_file():
        edition = "Legacy"
    else:
        raise ValueError(
            f"'{game}' is not launchable. Expected GTA5_Enhanced.exe or GTA5.exe."
        )

    steamapps = _steamapps_directory(game)
    app_id = STEAM_APP_IDS[edition]
    if steamapps is not None and (steamapps / f"appmanifest_{app_id}.acf").is_file():
        # `steam://run/<appid>` is Valve's documented launch URI. Keep custom
        # arguments out of the URI because Steam presents an extra confirmation
        # dialog for them. The managed commandline.txt already carries
        # `-nobattleye` for this Story Mode installation.
        return LaunchTarget(
            "steam",
            f"steam://run/{app_id}",
            edition,
            arguments=(),
        )

    play_launcher = game / "PlayGTAV.exe"
    executable = play_launcher if play_launcher.is_file() else enhanced if enhanced.is_file() else legacy
    return LaunchTarget("executable", str(executable), edition)


def launch_gta(
    gta_path: Path | str,
    *,
    uri_opener: Callable[[str], object] | None = None,
    process_starter: Callable[[Path, Path, tuple[str, ...]], object] | None = None,
) -> LaunchTarget:
    """Launch GTA V and return the target that was started."""
    target = resolve_launch_target(gta_path)
    game = Path(gta_path).expanduser()
    if target.method == "steam":
        (uri_opener or _open_uri)(target.location)
    else:
        (process_starter or _start_executable)(
            Path(target.location), game, target.arguments,
        )
    return target


def probe_gta_runtime(target: LaunchTarget) -> GtaRuntimeState:
    """Return the matching GTA process IDs and largest visible game window."""
    expected_name = (
        "gta5_enhanced.exe" if target.edition.casefold() == "enhanced"
        else "gta5.exe"
    )
    processes = _windows_processes()
    process_ids = tuple(sorted(
        pid for pid, name in processes.items() if name == expected_name
    ))
    return GtaRuntimeState(
        process_ids=process_ids,
        window_process_id=_largest_visible_window_pid(set(process_ids)),
    )


def observe_gta_launch(
    target: LaunchTarget,
    *,
    timeout_seconds: float = DEFAULT_LAUNCH_TIMEOUT_SECONDS,
    stability_seconds: float = DEFAULT_PROCESS_STABILITY_SECONDS,
    poll_interval_seconds: float = DEFAULT_LAUNCH_POLL_INTERVAL_SECONDS,
    runtime_probe: RuntimeProbe = probe_gta_runtime,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], object] = time.sleep,
    on_pending: Callable[[LaunchObservation], object] | None = None,
) -> LaunchObservation:
    """Wait for GTA itself after a storefront or executable handoff.

    A dispatch call returning only proves that Windows accepted the request. A
    visible game window is definitive success; a process that remains present
    for a short stability interval is also accepted because GTA can spend a
    noticeable period creating its first window. The bounded wait is intended
    to run on a worker thread.
    """
    if timeout_seconds <= 0:
        raise ValueError("Launch observation timeout must be greater than zero.")
    if stability_seconds < 0:
        raise ValueError("Process stability interval cannot be negative.")
    if poll_interval_seconds <= 0:
        raise ValueError("Launch observation poll interval must be greater than zero.")

    started_at = monotonic()
    deadline = started_at + timeout_seconds
    stable_pid: int | None = None
    stable_since: float | None = None
    saw_process = False
    last_pending_message: str | None = None

    def publish_pending(message: str, process_id: int | None = None) -> None:
        nonlocal last_pending_message
        if on_pending is None or message == last_pending_message:
            return
        last_pending_message = message
        on_pending(LaunchObservation("pending", message, process_id))

    while True:
        state = runtime_probe(target)
        now = monotonic()
        active_ids = set(state.process_ids)

        if state.window_process_id is not None:
            pid = state.window_process_id
            return LaunchObservation(
                "success",
                f"GTA V {target.edition} window is running (PID {pid}).",
                process_id=pid,
                window_visible=True,
            )

        if active_ids:
            saw_process = True
            if stable_pid not in active_ids:
                stable_pid = min(active_ids)
                stable_since = now
            publish_pending(
                f"GTA V {target.edition} process detected (PID {stable_pid}); "
                "waiting for it to stabilize.",
                stable_pid,
            )
            if stable_since is not None and now - stable_since >= stability_seconds:
                return LaunchObservation(
                    "success",
                    f"GTA V {target.edition} process is running (PID {stable_pid}); "
                    "its game window is still initializing.",
                    process_id=stable_pid,
                )
        else:
            if stable_pid is not None:
                publish_pending(
                    f"GTA V {target.edition} exited before its window appeared; "
                    "waiting for the storefront to retry."
                )
                stable_pid = None
                stable_since = None
            else:
                publish_pending(
                    f"Waiting for the GTA V {target.edition} process after the "
                    f"{_handoff_name(target)} handoff."
                )

        if now >= deadline:
            transient = (
                " A GTA process appeared briefly, but exited before becoming stable."
                if saw_process else ""
            )
            return LaunchObservation(
                "failure",
                f"The {_handoff_name(target)} launch request was sent, but no stable "
                f"GTA V {target.edition} process or game window appeared within "
                f"{timeout_seconds:g} seconds.{transient} Check Steam or Rockstar "
                "Games Launcher for a sign-in, update, or error prompt, then try again.",
            )

        sleeper(min(poll_interval_seconds, max(0.0, deadline - now)))


def _handoff_name(target: LaunchTarget) -> str:
    if target.method == "steam":
        return "Steam"
    return Path(target.location).name


def _windows_processes() -> dict[int, str]:
    if os.name != "nt":
        return {}
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W),
    )
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W),
    )
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid = ctypes.c_void_p(-1).value
    if snapshot in (0, invalid):
        return {}
    entry = _ProcessEntry32W()
    entry.dwSize = ctypes.sizeof(entry)
    processes: dict[int, str] = {}
    try:
        if kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                processes[int(entry.th32ProcessID)] = entry.szExeFile.casefold()
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return processes


def _largest_visible_window_pid(process_ids: set[int]) -> int | None:
    if os.name != "nt" or not process_ids:
        return None
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    matches: list[tuple[int, int]] = []

    @callback_type
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = int(pid.value)
        if process_id not in process_ids:
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            width = max(0, int(rect.right - rect.left))
            height = max(0, int(rect.bottom - rect.top))
            if width > 320 and height > 240:
                matches.append((width * height, process_id))
        return True

    user32.EnumWindows(visit, 0)
    return max(matches)[1] if matches else None


def _steamapps_directory(game: Path) -> Path | None:
    common = game.parent
    steamapps = common.parent
    if common.name.casefold() == "common" and steamapps.name.casefold() == "steamapps":
        return steamapps
    return None


def _open_uri(uri: str) -> None:
    """Open a registered storefront URI using Windows ShellExecute."""
    if not hasattr(os, "startfile"):  # pragma: no cover - launcher targets Windows
        raise OSError("Storefront URI launching is only supported on Windows.")
    os.startfile(uri)  # type: ignore[attr-defined]


def _start_executable(
    executable: Path,
    working_directory: Path,
    arguments: tuple[str, ...] = STORY_MODE_ARGUMENTS,
) -> None:
    """Start the Rockstar game launcher without creating a console window."""
    subprocess.Popen(
        [str(executable), *arguments],
        cwd=str(working_directory),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
