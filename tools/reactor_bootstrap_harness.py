r"""Developer-only visual harness for the Reactor V launch bootstrap.

Run from the repository root with::

    .\.venv\Scripts\python.exe tools\reactor_bootstrap_harness.py

This tool never starts GTA, edits a game install, or registers a hotkey.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tkinter as tk
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk


REPOSITORY = Path(__file__).resolve().parents[1]
SOURCE = REPOSITORY / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from allin1.reactor_bootstrap import BootstrapState  # noqa: E402
from allin1.reactor_bootstrap_ui import (  # noqa: E402
    ACRONYM_DISPLAY_SEQUENCE,
    ACRONYM_EFFECT_FRAMES,
    REACTOR_ACRONYM,
    OverlayEnvironment,
    ReactorBootstrapWindow,
    overlay_geometry,
)


@dataclass(frozen=True, slots=True)
class HarnessScenario:
    label: str
    ready: frozenset[str]
    failure: str | None = None
    terminal: bool = False

    def state(self) -> BootstrapState:
        return BootstrapState(
            self.ready,
            failure=self.failure,
            terminal=self.terminal,
            process_seen="launch" in self.ready,
        )


SCENARIOS: tuple[HarnessScenario, ...] = (
    HarnessScenario("Preparing", frozenset()),
    HarnessScenario("Launch requested", frozenset({"launch"})),
    HarnessScenario("Interface preloaded", frozenset({"launch", "warmup"})),
    HarnessScenario("Native extensions", frozenset({"launch", "warmup", "native"})),
    HarnessScenario(
        "Story assets",
        frozenset({"launch", "warmup", "native", "assets"}),
    ),
    HarnessScenario(
        "ScriptHookVDotNet",
        frozenset({"launch", "warmup", "native", "assets", "dotnet"}),
    ),
    HarnessScenario(
        "Reactor ready",
        frozenset(
            {"launch", "warmup", "native", "assets", "dotnet", "reactor"},
        ),
    ),
    HarnessScenario(
        "Story ready",
        frozenset(
            {
                "launch", "warmup", "native", "assets", "dotnet",
                "reactor", "story",
            },
        ),
        terminal=True,
    ),
    HarnessScenario(
        "Failure",
        frozenset({"launch", "warmup"}),
        failure="Reactor V could not open its interface.",
        terminal=True,
    ),
)


class ScriptedMonitor:
    def __init__(self) -> None:
        self.current = SCENARIOS[0]

    def mark_launch_requested(self) -> None:
        self.current = SCENARIOS[1]

    def sample(self, *, process_running: bool) -> BootstrapState:
        _ = process_running
        return self.current.state()


class ScriptedEnvironment:
    def __init__(self) -> None:
        self.bounds: tuple[int, int, int, int] | None = None
        self.visible = True

    def __call__(self) -> OverlayEnvironment:
        return OverlayEnvironment(
            process_running=True,
            bounds=self.bounds,
            safe_foreground=self.visible,
        )


def _monitor_bounds(root: tk.Misc) -> list[tuple[str, tuple[int, int, int, int]]]:
    fallback = (
        "Primary desktop",
        (0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight())),
    )
    if os.name != "nt":
        return [fallback]

    records: list[tuple[int, int, int, int]] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    @callback_type
    def visit(_monitor, _hdc, rect, _data):
        value = rect.contents
        records.append(
            (
                int(value.left),
                int(value.top),
                int(value.right - value.left),
                int(value.bottom - value.top),
            ),
        )
        return True

    try:
        ctypes.windll.user32.EnumDisplayMonitors(0, 0, visit, 0)
    except (AttributeError, OSError):
        return [fallback]
    if not records:
        return [fallback]
    return [
        (f"Monitor {index}: {width}×{height} at {left},{top}", bounds)
        for index, bounds in enumerate(records, start=1)
        for left, top, width, height in (bounds,)
    ]


def self_check() -> dict[str, object]:
    all_ready = SCENARIOS[-2].ready
    progress = [frame.scan_progress for frame in ACRONYM_EFFECT_FRAMES]
    checks = {
        "acronym": "".join(letter for letter, _ in REACTOR_ACRONYM) == "REACTOR",
        "states_monotonic": all(
            left.ready <= right.ready
            for left, right in zip(SCENARIOS[:-3], SCENARIOS[1:-2])
        ),
        "story_complete": "story" in all_ready and "reactor" in all_ready,
        "effect_bounded": 4 <= len(ACRONYM_EFFECT_FRAMES) <= 12,
        "scan_monotonic": progress == sorted(progress),
        "defocus_resolves": (
            ACRONYM_EFFECT_FRAMES[0].blur_offset > 0
            and ACRONYM_EFFECT_FRAMES[-1].blur_offset == 0
        ),
        "final_title": ACRONYM_DISPLAY_SEQUENCE[-1] == "REACTOR",
        "upper_right": overlay_geometry((100, 40, 1280, 720), (1920, 1080))[2]
        > 100,
    }
    return {"ok": all(checks.values()), "checks": checks}


class HarnessApp:
    def __init__(self, root: tk.Tk, *, autoplay: bool) -> None:
        self.root = root
        self.monitor = ScriptedMonitor()
        self.environment = ScriptedEnvironment()
        self.monitor_targets = _monitor_bounds(root)
        self.state_by_label = {item.label: item for item in SCENARIOS}
        self.target_by_label = dict(self.monitor_targets)
        self.auto_index = 0

        root.title("Reactor V bootstrap visual harness")
        root.geometry("560x300+40+60")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.close)

        panel = ttk.Frame(root, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(
            panel,
            text="Reactor V bootstrap harness",
            font=("Segoe UI Semibold", 15),
        ).pack(anchor="w")
        ttk.Label(
            panel,
            text="Exercises the production overlay without launching or modifying GTA.",
        ).pack(anchor="w", pady=(2, 16))

        ttk.Label(panel, text="Startup state").pack(anchor="w")
        self.state_value = tk.StringVar(value=SCENARIOS[0].label)
        state_box = ttk.Combobox(
            panel,
            state="readonly",
            textvariable=self.state_value,
            values=[item.label for item in SCENARIOS],
        )
        state_box.pack(fill="x", pady=(3, 10))
        state_box.bind("<<ComboboxSelected>>", self._state_changed)

        ttk.Label(panel, text="Placement target").pack(anchor="w")
        target_label = self.monitor_targets[0][0]
        self.target_value = tk.StringVar(value=target_label)
        target_box = ttk.Combobox(
            panel,
            state="readonly",
            textvariable=self.target_value,
            values=[label for label, _bounds in self.monitor_targets],
        )
        target_box.pack(fill="x", pady=(3, 12))
        target_box.bind("<<ComboboxSelected>>", self._target_changed)

        buttons = ttk.Frame(panel)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Play sequence", command=self.play).pack(side="left")
        self.visibility_button = ttk.Button(
            buttons,
            text="Hide overlay",
            command=self.toggle_visibility,
        )
        self.visibility_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Close", command=self.close).pack(side="right")

        self.environment.bounds = self.target_by_label[target_label]
        self.overlay = ReactorBootstrapWindow(
            root,
            REPOSITORY,
            None,
            monitor=self.monitor,  # type: ignore[arg-type]
            environment_probe=self.environment,
            close_on_terminal=False,
            on_log=lambda message: print(f"[Reactor harness] {message}"),
        )
        if autoplay:
            root.after(500, self.play)

    def _state_changed(self, _event=None) -> None:
        self.monitor.current = self.state_by_label[self.state_value.get()]

    def _target_changed(self, _event=None) -> None:
        self.environment.bounds = self.target_by_label[self.target_value.get()]

    def toggle_visibility(self) -> None:
        self.environment.visible = not self.environment.visible
        self.visibility_button.configure(
            text="Hide overlay" if self.environment.visible else "Show overlay",
        )

    def play(self) -> None:
        self.auto_index = 0
        self.environment.visible = True
        self.visibility_button.configure(text="Hide overlay")
        self._play_step()

    def _play_step(self) -> None:
        if self.auto_index >= len(SCENARIOS) - 1:
            return
        scenario = SCENARIOS[self.auto_index]
        self.monitor.current = scenario
        self.state_value.set(scenario.label)
        self.auto_index += 1
        self.root.after(850, self._play_step)

    def close(self) -> None:
        if getattr(self, "overlay", None) is not None:
            self.overlay.stop()
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="validate the harness scenarios and exit without opening a window",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="play the startup sequence after the visual harness opens",
    )
    parser.add_argument(
        "--exit-after-ms",
        type=int,
        default=0,
        help="close an opened harness automatically after this many milliseconds",
    )
    args = parser.parse_args()
    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    root = tk.Tk()
    app = HarnessApp(root, autoplay=args.auto)
    if args.exit_after_ms > 0:
        root.after(args.exit_after_ms, app.close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
