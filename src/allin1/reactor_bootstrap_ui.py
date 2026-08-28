"""Non-activating Reactor V startup status owned by the desktop launcher."""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from allin1.reactor_bootstrap import (
    MILESTONE_LABELS,
    BootstrapState,
    ReactorStartupMonitor,
    inspect_reactor_installation,
)


TRANSPARENT_KEY = "#010203"
ACCENT = "#1ba8ff"
READY = "#51e78b"
PENDING = "#8da1ad"
FAILED = "#ff6577"
COMPACT_WIDTH = 460
COMPACT_HEIGHT = 72
CORNER_MARGIN = 28
POLL_INTERVAL_MS = 400
ACRONYM_INTERVAL_MS = 580
ACRONYM_EFFECT_INTERVAL_MS = 45
REACTOR_TITLE_HOLD_MS = 1400
REACTOR_ACRONYM: tuple[tuple[str, str], ...] = (
    ("R", "Real-time"),
    ("E", "Embedded"),
    ("A", "Application"),
    ("C", "Component"),
    ("T", "Toolkit"),
    ("O", "Overlay"),
    ("R", "Runtime"),
)
ACRONYM_DISPLAY_SEQUENCE: tuple[str, ...] = (
    *(f"{letter} · {word.upper()}" for letter, word in REACTOR_ACRONYM),
    "REACTOR",
)


@dataclass(frozen=True, slots=True)
class AcronymEffectFrame:
    """One small, precomputed canvas-only acronym transition frame."""

    title_color: str
    trail_color: str
    ghost_color: str
    scan_color: str
    scan_progress: float
    blur_offset: int
    streak_width: int


@dataclass(frozen=True, slots=True)
class OverlayEnvironment:
    """Small OS snapshot consumed by one bootstrap poll.

    Keeping the window/process probing behind this value lets the developer
    harness exercise real rendering, visibility and placement without starting
    GTA or fabricating log files.
    """

    process_running: bool
    bounds: tuple[int, int, int, int] | None
    safe_foreground: bool


# The bootstrap runs while GTA is doing its heaviest work, so the effect is a
# deliberately tiny set of Canvas updates rather than decoded images or a
# continuously running animation loop. Offset cyan/white ghost layers emulate
# a short defocus streak, then collapse onto the sharp Reactor accent. This is
# intentionally deterministic and bounded while GTA is doing its heaviest work.
ACRONYM_EFFECT_FRAMES: tuple[AcronymEffectFrame, ...] = (
    AcronymEffectFrame(
        "#5e9fbb", "#1777a5", "#0f5779", "#167eaa", 0.08, 14, 3,
    ),
    AcronymEffectFrame(
        "#8fd5ef", "#12658e", "#197fab", "#20b8f4", 0.22, 11, 3,
    ),
    AcronymEffectFrame(
        "#d8f8ff", "#0d526f", "#3bbde8", "#75e7ff", 0.38, 8, 2,
    ),
    AcronymEffectFrame(
        "#effcff", "#083d55", "#82e8ff", "#32caff", 0.54, 6, 2,
    ),
    AcronymEffectFrame(
        "#9be6ff", "#062e40", "#2ea8d2", ACCENT, 0.68, 4, 2,
    ),
    AcronymEffectFrame(
        "#51c8fa", "#041f2d", "#14769d", "#126b97", 0.80, 2, 1,
    ),
    AcronymEffectFrame(
        ACCENT, "#02121b", "#07384e", "#083e5a", 0.90, 1, 1,
    ),
    AcronymEffectFrame(
        ACCENT, TRANSPARENT_KEY, TRANSPARENT_KEY, TRANSPARENT_KEY,
        1.00, 0, 1,
    ),
)

_GTA_PROCESS_NAMES = {"gta5.exe", "gta5_enhanced.exe"}
_LAUNCH_PROCESS_NAMES = {
    "launcher.exe",
    "playgtav.exe",
    "rockstargameslauncher.exe",
    "socialclubhelper.exe",
    "steam.exe",
}


def overlay_geometry(
    bounds: tuple[int, int, int, int] | None,
    screen_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """Return ``width, height, x, y`` for the corner bootstrap."""
    if bounds is None:
        left, top = 0, 0
        area_width, area_height = screen_size
    else:
        left, top, area_width, area_height = bounds

    width, height = COMPACT_WIDTH, COMPACT_HEIGHT
    x_margin = CORNER_MARGIN if area_width >= width + CORNER_MARGIN * 2 else 0
    y_margin = CORNER_MARGIN if area_height >= height + CORNER_MARGIN * 2 else 0
    x = left + max(0, area_width - width - x_margin)
    y = top + y_margin
    return width, height, x, y


def window_geometry_spec(geometry: tuple[int, int, int, int]) -> str:
    """Return a Tk geometry string that remains valid on negative monitors."""
    width, height, x, y = geometry
    x_offset = f"+{x}" if x >= 0 else str(x)
    y_offset = f"+{y}" if y >= 0 else str(y)
    return f"{width}x{height}{x_offset}{y_offset}"


def native_position_request(
    geometry: tuple[int, int, int, int],
    *,
    show: bool,
) -> tuple[int, int, int, int, int]:
    """Return x, y, width, height and flags for native window placement."""
    width, height, x, y = geometry
    # SWP_NOACTIVATE | SWP_NOOWNERZORDER, optionally SWP_SHOWWINDOW. Do not use
    # SWP_NOMOVE/SWP_NOSIZE: Tk can defer geometry until after the first show.
    flags = 0x0010 | 0x0200
    if show:
        flags |= 0x0040
    return x, y, width, height, flags


def startup_status(state: BootstrapState) -> tuple[str, str]:
    """Return concise, honest copy for the corner-only startup phase."""
    if state.failure:
        return state.failure, FAILED
    if state.story_ready:
        return "Story Mode ready", READY
    if state.reactor_ready:
        return "Reactor V ready · entering Story Mode…", "#eff8fc"
    if "dotnet" in state.ready:
        return "ScriptHookVDotNet ready · starting Reactor V…", "#eff8fc"
    if "assets" in state.ready:
        return "GTA V runtime ready · loading scripts…", "#eff8fc"
    if "native" in state.ready:
        return "Native extensions loaded · starting Story Mode…", "#eff8fc"
    if "warmup" in state.ready:
        return "Reactor V interface ready · GTA V is still loading…", "#eff8fc"
    if "launch" in state.ready:
        return "Starting GTA V Story Mode…", "#eff8fc"
    return "Preparing Story Mode…", PENDING


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


def _foreground_pid() -> int | None:
    if os.name != "nt":
        return os.getpid()
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


def _gta_window_bounds(gta_pids: set[int]) -> tuple[int, int, int, int] | None:
    if os.name != "nt" or not gta_pids:
        return None
    user32 = ctypes.windll.user32
    matches: list[tuple[int, int, int, int]] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in gta_pids:
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            width = int(rect.right - rect.left)
            height = int(rect.bottom - rect.top)
            if width > 320 and height > 240:
                matches.append((int(rect.left), int(rect.top), width, height))
        return True

    user32.EnumWindows(visit, 0)
    return max(matches, key=lambda item: item[2] * item[3]) if matches else None


def probe_overlay_environment() -> OverlayEnvironment:
    """Inspect GTA placement and focus without changing process or window state."""
    processes = _windows_processes()
    gta_pids = {
        pid for pid, name in processes.items() if name in _GTA_PROCESS_NAMES
    }
    bounds = _gta_window_bounds(gta_pids)
    foreground = _foreground_pid()
    foreground_name = processes.get(foreground or -1, "")
    safe_foreground = (
        foreground in (None, os.getpid())
        or foreground in gta_pids
        or foreground_name in _LAUNCH_PROCESS_NAMES
    )
    return OverlayEnvironment(
        process_running=bool(gta_pids),
        bounds=bounds,
        safe_foreground=safe_foreground,
    )


def _root_hwnd(window: tk.Toplevel) -> int:
    client = int(window.winfo_id())
    if os.name != "nt":
        return client
    user32 = ctypes.windll.user32
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    return int(user32.GetAncestor(client, 2) or client)  # GA_ROOT


def _apply_nonactivating_styles(window: tk.Toplevel) -> int:
    """Make the transparent overlay click-through and absent from Alt+Tab."""
    hwnd = _root_hwnd(window)
    if os.name != "nt":
        return hwnd
    user32 = ctypes.windll.user32
    get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    get_long.argtypes = (wintypes.HWND, ctypes.c_int)
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
    set_long.restype = ctypes.c_ssize_t
    style = int(get_long(hwnd, -20))  # GWL_EXSTYLE
    style |= 0x08000000 | 0x00000080 | 0x00000020
    set_long(hwnd, -20, style)  # NOACTIVATE | TOOLWINDOW | TRANSPARENT
    try:
        window.wm_attributes("-disabled", True)
    except tk.TclError:
        pass
    return hwnd


def _set_native_position(
    hwnd: int,
    geometry: tuple[int, int, int, int],
    *,
    show: bool,
) -> None:
    """Place the overlay exactly without taking focus or entering Alt+Tab."""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    user32.SetWindowPos.argtypes = (
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    )
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    x, y, width, height, flags = native_position_request(
        geometry,
        show=show,
    )
    user32.SetWindowPos(hwnd, -1, x, y, width, height, flags)
    if show:
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE


def _show_without_activation(
    hwnd: int,
    geometry: tuple[int, int, int, int],
) -> None:
    _set_native_position(hwnd, geometry, show=True)


class ReactorBootstrapWindow:
    """Small transparent launch overlay that never owns game input."""

    def __init__(
        self,
        parent: tk.Misc,
        gta_path: Path,
        logo_path: Path | None,
        *,
        on_log: Callable[[str], None] | None = None,
        on_closed: Callable[[], None] | None = None,
        monitor: ReactorStartupMonitor | None = None,
        environment_probe: Callable[[], OverlayEnvironment] | None = None,
        close_on_terminal: bool = True,
    ) -> None:
        self.parent = parent
        self.gta_path = Path(gta_path)
        self.on_log = on_log
        self.on_closed = on_closed
        self.monitor = monitor or ReactorStartupMonitor(self.gta_path)
        self._environment_probe = environment_probe or probe_overlay_environment
        self._close_on_terminal = close_on_terminal
        self.closed = False
        self._visible = False
        self._last_ready: frozenset[str] = frozenset()
        self._after_ids: set[str] = set()
        self._last_geometry: tuple[int, int, int, int] | None = None
        self._handoff_complete = False
        self._acronym_index = 0
        # The centered logo belongs to the in-game React layer. The launcher
        # keeps this bootstrap text-only and therefore deliberately does not
        # decode the package artwork during GTA startup.
        _ = logo_path

        self.window = tk.Toplevel(parent)
        # The bootstrap is a deliberately transparent, composited game overlay.
        # Desktop theme passes must never repaint its keyed surface or canvas.
        self.window._allin1_theme_exempt = True
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(background=TRANSPARENT_KEY)
        self.window.geometry(
            window_geometry_spec((COMPACT_WIDTH, COMPACT_HEIGHT, 0, 0)),
        )
        if os.name == "nt":
            try:
                self.window.wm_attributes("-transparentcolor", TRANSPARENT_KEY)
            except tk.TclError:
                pass
        else:  # pragma: no cover - the GTA launcher targets Windows
            self.window.wm_attributes("-topmost", True)

        self.canvas = tk.Canvas(
            self.window,
            width=COMPACT_WIDTH,
            height=COMPACT_HEIGHT,
            background=TRANSPARENT_KEY,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.pack(fill="both", expand=True)
        title_x = COMPACT_WIDTH - 18
        title_y = 15
        self.compact_trail_item = self.canvas.create_text(
            title_x,
            title_y,
            text="",
            anchor="ne",
            fill=TRANSPARENT_KEY,
            font=("Segoe UI Semibold", 10),
        )
        self.compact_blur_left_item = self.canvas.create_text(
            title_x,
            title_y,
            text=ACRONYM_DISPLAY_SEQUENCE[0],
            anchor="ne",
            fill=TRANSPARENT_KEY,
            font=("Segoe UI Semibold", 10),
        )
        self.compact_blur_right_item = self.canvas.create_text(
            title_x,
            title_y,
            text=ACRONYM_DISPLAY_SEQUENCE[0],
            anchor="ne",
            fill=TRANSPARENT_KEY,
            font=("Segoe UI Semibold", 10),
        )
        self.compact_title_item = self.canvas.create_text(
            title_x,
            title_y,
            text=ACRONYM_DISPLAY_SEQUENCE[0],
            anchor="ne",
            fill=ACCENT,
            font=("Segoe UI Semibold", 10),
        )
        self.compact_scan_item = self.canvas.create_line(
            title_x - 30,
            27,
            title_x,
            27,
            fill=TRANSPARENT_KEY,
            width=1,
        )
        self.compact_status_item = self.canvas.create_text(
            COMPACT_WIDTH - 18,
            38,
            text="Preparing Story Mode…",
            anchor="ne",
            justify="right",
            width=COMPACT_WIDTH - 36,
            fill=PENDING,
            font=("Segoe UI", 10),
        )
        self.window.update_idletasks()
        self.hwnd = _apply_nonactivating_styles(self.window)
        self._position(None)
        self._set_visible(True)
        self._schedule(ACRONYM_INTERVAL_MS, self._cycle_acronym)
        self._schedule(POLL_INTERVAL_MS, self._poll)
        self._emit("Reactor V bootstrap is monitoring Story Mode startup.")

    def mark_launch_requested(self) -> None:
        self.monitor.mark_launch_requested()
        self._render_state(self.monitor.sample(process_running=False))

    def _schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if self.closed:
            return
        identifier: str | None = None

        def run() -> None:
            if identifier is not None:
                self._after_ids.discard(identifier)
            if not self.closed:
                callback()

        identifier = self.parent.after(delay_ms, run)
        self._after_ids.add(identifier)

    def _cycle_acronym(self) -> None:
        if self._handoff_complete:
            return
        old_title = ACRONYM_DISPLAY_SEQUENCE[self._acronym_index]
        self._acronym_index = (
            self._acronym_index + 1
        ) % len(ACRONYM_DISPLAY_SEQUENCE)
        title = ACRONYM_DISPLAY_SEQUENCE[self._acronym_index]
        self.canvas.itemconfigure(
            self.compact_trail_item,
            text=old_title,
        )
        for item in (
            self.compact_blur_left_item,
            self.compact_blur_right_item,
            self.compact_title_item,
        ):
            self.canvas.itemconfigure(item, text=title)
        self._animate_acronym(0)

    def _animate_acronym(self, frame_index: int) -> None:
        if self._handoff_complete:
            return
        if frame_index >= len(ACRONYM_EFFECT_FRAMES):
            delay = (
                REACTOR_TITLE_HOLD_MS
                if ACRONYM_DISPLAY_SEQUENCE[self._acronym_index] == "REACTOR"
                else ACRONYM_INTERVAL_MS
            )
            self._schedule(delay, self._cycle_acronym)
            return
        frame = ACRONYM_EFFECT_FRAMES[frame_index]
        title_x = COMPACT_WIDTH - 18
        title_y = 15
        scan_left = COMPACT_WIDTH - 210
        scan_right = COMPACT_WIDTH - 18
        scan_x = scan_left + (scan_right - scan_left) * frame.scan_progress
        self.canvas.itemconfigure(
            self.compact_title_item,
            fill=frame.title_color,
        )
        self.canvas.itemconfigure(
            self.compact_trail_item,
            fill=frame.trail_color,
        )
        self.canvas.itemconfigure(
            self.compact_blur_left_item,
            fill=frame.ghost_color,
        )
        self.canvas.itemconfigure(
            self.compact_blur_right_item,
            fill=frame.ghost_color,
        )
        self.canvas.itemconfigure(
            self.compact_scan_item,
            fill=frame.scan_color,
            width=frame.streak_width,
        )
        self.canvas.coords(
            self.compact_blur_left_item,
            title_x - frame.blur_offset,
            title_y,
        )
        self.canvas.coords(
            self.compact_blur_right_item,
            title_x + frame.blur_offset,
            title_y,
        )
        self.canvas.coords(
            self.compact_scan_item,
            scan_x - 28,
            27,
            scan_x,
            27,
        )
        self._schedule(
            ACRONYM_EFFECT_INTERVAL_MS,
            lambda: self._animate_acronym(frame_index + 1),
        )

    def _settle_acronym_title(self) -> None:
        """Resolve every transition layer to the clean framework title."""
        self._acronym_index = len(ACRONYM_DISPLAY_SEQUENCE) - 1
        self.canvas.itemconfigure(
            self.compact_title_item,
            text="REACTOR",
            fill=ACCENT,
        )
        for item in (
            self.compact_trail_item,
            self.compact_blur_left_item,
            self.compact_blur_right_item,
        ):
            self.canvas.itemconfigure(item, fill=TRANSPARENT_KEY)
        self.canvas.itemconfigure(
            self.compact_scan_item,
            fill=TRANSPARENT_KEY,
            width=1,
        )

    def _poll(self) -> None:
        environment = self._environment_probe()
        if environment.bounds is not None:
            self._position(environment.bounds)
        self._set_visible(environment.safe_foreground)

        state = self.monitor.sample(
            process_running=environment.process_running,
        )
        self._render_state(state)
        if state.story_ready:
            if self._close_on_terminal:
                self._settle_acronym_title()
                self._handoff_complete = True
                self._emit("Story Mode is ready; Reactor V startup handoff complete.")
                self._schedule(700, self._fade_out)
                return
        if state.terminal:
            if self._close_on_terminal:
                if state.failure:
                    self._emit(state.failure)
                self._schedule(3500, self._fade_out)
                return
        self._schedule(POLL_INTERVAL_MS, self._poll)

    def _render_state(self, state: BootstrapState) -> None:
        compact_text, compact_color = startup_status(state)
        self.canvas.itemconfigure(
            self.compact_status_item,
            text=compact_text,
            fill=compact_color,
        )
        new_items = state.ready - self._last_ready
        labels = dict(MILESTONE_LABELS)
        for key in MILESTONE_LABELS:
            if key[0] in new_items:
                self._emit(f"Reactor V bootstrap: {labels[key[0]]}.")
        self._last_ready = state.ready

    def _position(self, bounds: tuple[int, int, int, int] | None) -> None:
        screen_size = (
            int(self.parent.winfo_screenwidth()),
            int(self.parent.winfo_screenheight()),
        )
        width, height, x, y = overlay_geometry(bounds, screen_size)
        geometry = (width, height, x, y)
        if self._last_geometry == geometry:
            return
        self._last_geometry = geometry
        self.window.geometry(window_geometry_spec(geometry))
        self.window.update_idletasks()
        if hasattr(self, "hwnd"):
            _set_native_position(self.hwnd, geometry, show=self._visible)

    def _set_visible(self, visible: bool) -> None:
        if self.closed or visible == self._visible:
            return
        if visible:
            if os.name == "nt":
                geometry = self._last_geometry
                if geometry is None:
                    self._position(None)
                    geometry = self._last_geometry
                if geometry is not None:
                    _show_without_activation(self.hwnd, geometry)
            else:  # pragma: no cover - the GTA launcher targets Windows
                self.window.deiconify()
            self._visible = True
        else:
            self.window.withdraw()
            self._visible = False

    def _fade_out(self, step: int = 0) -> None:
        if self.closed:
            return
        if step >= 7:
            self.stop()
            return
        try:
            self.window.wm_attributes("-alpha", max(0.0, 1.0 - (step + 1) / 7))
        except tk.TclError:
            self.stop()
            return
        self._schedule(65, lambda: self._fade_out(step + 1))

    def stop(self) -> None:
        if self.closed:
            return
        self.closed = True
        for identifier in tuple(self._after_ids):
            try:
                self.parent.after_cancel(identifier)
            except tk.TclError:
                pass
        self._after_ids.clear()
        try:
            self.window.destroy()
        except tk.TclError:
            pass
        if self.on_closed is not None:
            self.on_closed()

    def _emit(self, message: str) -> None:
        if self.on_log is not None:
            self.on_log(message)


def start_reactor_bootstrap(
    parent: tk.Misc,
    gta_path: Path | str,
    *,
    on_log: Callable[[str], None] | None = None,
    on_closed: Callable[[], None] | None = None,
) -> ReactorBootstrapWindow | None:
    """Start the optional splash only for a healthy, enabled Reactor package."""
    installation = inspect_reactor_installation(gta_path)
    if not installation.available:
        return None
    try:
        return ReactorBootstrapWindow(
            parent,
            Path(gta_path),
            installation.logo_path,
            on_log=on_log,
            on_closed=on_closed,
        )
    except (OSError, RuntimeError, tk.TclError, ValueError):
        return None
