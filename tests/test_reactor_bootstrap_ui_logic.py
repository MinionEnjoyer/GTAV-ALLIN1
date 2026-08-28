from pathlib import Path

import pytest

import allin1.reactor_bootstrap_ui as bootstrap_ui
from allin1.reactor_bootstrap import BootstrapState
from allin1.reactor_bootstrap_ui import (
    ACCENT,
    ACRONYM_DISPLAY_SEQUENCE,
    ACRONYM_EFFECT_FRAMES,
    COMPACT_HEIGHT,
    COMPACT_WIDTH,
    CORNER_MARGIN,
    REACTOR_ACRONYM,
    REACTOR_TITLE_HOLD_MS,
    TRANSPARENT_KEY,
    OverlayEnvironment,
    native_position_request,
    overlay_geometry,
    startup_status,
    window_geometry_spec,
)


def _state(*ready: str, failure: str | None = None) -> BootstrapState:
    return BootstrapState(frozenset(ready), failure=failure)


def test_compact_geometry_uses_game_upper_right_corner():
    geometry = overlay_geometry(
        (-1920, 40, 1920, 1080),
        (2560, 1440),
    )

    assert geometry == (
        COMPACT_WIDTH,
        COMPACT_HEIGHT,
        -1920 + 1920 - COMPACT_WIDTH - CORNER_MARGIN,
        40 + CORNER_MARGIN,
    )


def test_compact_geometry_stays_inside_small_game_window():
    width, height, x, y = overlay_geometry(
        (120, 80, 400, 100),
        (1920, 1080),
    )

    assert (width, height) == (COMPACT_WIDTH, COMPACT_HEIGHT)
    assert (x, y) == (120, 80)


@pytest.mark.parametrize(
    ("bounds", "screen_size", "expected", "spec"),
    (
        (
            None,
            (2560, 1440),
            (COMPACT_WIDTH, COMPACT_HEIGHT, 2072, 28),
            "460x72+2072+28",
        ),
        (
            (0, 0, 1920, 1080),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, 1432, 28),
            "460x72+1432+28",
        ),
        (
            (-1920, 0, 1920, 1080),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, -488, 28),
            "460x72-488+28",
        ),
        (
            (1920, 120, 1920, 1080),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, 3352, 148),
            "460x72+3352+148",
        ),
        (
            (0, -1440, 2560, 1440),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, 2072, -1412),
            "460x72+2072-1412",
        ),
        (
            (-1280, -1024, 1280, 1024),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, -488, -996),
            "460x72-488-996",
        ),
        (
            (120, 80, 400, 100),
            (1920, 1080),
            (COMPACT_WIDTH, COMPACT_HEIGHT, 120, 80),
            "460x72+120+80",
        ),
    ),
)
def test_geometry_matrix_handles_desktop_and_monitor_quadrants(
    bounds,
    screen_size,
    expected,
    spec,
):
    geometry = overlay_geometry(bounds, screen_size)

    assert geometry == expected
    assert window_geometry_spec(geometry) == spec


def test_negative_monitor_geometry_is_valid_for_tk_and_native_placement():
    geometry = (COMPACT_WIDTH, COMPACT_HEIGHT, -488, 68)

    assert window_geometry_spec(geometry) == "460x72-488+68"
    x, y, width, height, flags = native_position_request(
        geometry,
        show=True,
    )
    assert (x, y, width, height) == (-488, 68, COMPACT_WIDTH, COMPACT_HEIGHT)
    assert flags & 0x0010  # SWP_NOACTIVATE
    assert flags & 0x0040  # SWP_SHOWWINDOW
    assert not flags & 0x0001  # SWP_NOSIZE must stay off
    assert not flags & 0x0002  # SWP_NOMOVE must stay off


def test_hidden_native_placement_does_not_request_a_show():
    *_, flags = native_position_request((460, 72, 100, 28), show=False)

    assert flags & 0x0010
    assert not flags & 0x0040


def test_position_commits_computed_bounds_through_tk_and_native_api(monkeypatch):
    class Parent:
        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

    class Window:
        def __init__(self):
            self.specs = []
            self.update_count = 0

        def geometry(self, spec):
            self.specs.append(spec)

        def update_idletasks(self):
            self.update_count += 1

    native_calls = []
    monkeypatch.setattr(
        bootstrap_ui,
        "_set_native_position",
        lambda hwnd, geometry, *, show: native_calls.append(
            (hwnd, geometry, show),
        ),
    )
    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay.parent = Parent()
    overlay.window = Window()
    overlay.hwnd = 77
    overlay._visible = True
    overlay._last_geometry = None

    overlay._position((-1920, 40, 1920, 1080))

    expected = (
        COMPACT_WIDTH,
        COMPACT_HEIGHT,
        -1920 + 1920 - COMPACT_WIDTH - CORNER_MARGIN,
        40 + CORNER_MARGIN,
    )
    assert overlay.window.specs == [window_geometry_spec(expected)]
    assert overlay.window.update_count == 1
    assert native_calls == [(77, expected, True)]


def test_first_frame_is_withdrawn_positioned_then_shown_without_activation(
    monkeypatch,
):
    events = []

    class Parent:
        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

        def after(self, delay, callback):
            events.append(("after", delay))
            return f"job-{delay}-{len(events)}"

    class Window:
        def __init__(self, _parent):
            events.append("create")

        def withdraw(self):
            events.append("withdraw")

        def overrideredirect(self, value):
            events.append(("override", value))

        def configure(self, **kwargs):
            events.append(("configure", kwargs))

        def geometry(self, spec):
            events.append(("geometry", spec))

        def wm_attributes(self, *args):
            events.append(("attribute", args))

        def update_idletasks(self):
            events.append("idle")

    class Canvas:
        def __init__(self, *_args, **_kwargs):
            pass

        def pack(self, **_kwargs):
            pass

        def create_text(self, *_args, **_kwargs):
            return 1

        def create_line(self, *_args, **_kwargs):
            return 2

    monkeypatch.setattr(bootstrap_ui.tk, "Toplevel", Window)
    monkeypatch.setattr(bootstrap_ui.tk, "Canvas", Canvas)
    monkeypatch.setattr(
        bootstrap_ui,
        "_apply_nonactivating_styles",
        lambda _window: events.append("styles") or 77,
    )
    monkeypatch.setattr(
        bootstrap_ui,
        "_set_native_position",
        lambda _hwnd, geometry, *, show: events.append(
            ("native", geometry, show),
        ),
    )
    monkeypatch.setattr(
        bootstrap_ui,
        "_show_without_activation",
        lambda _hwnd, geometry: events.append(("show", geometry)),
    )

    overlay = bootstrap_ui.ReactorBootstrapWindow(
        Parent(),
        Path("C:/nonexistent-gta"),
        None,
    )

    expected = (COMPACT_WIDTH, COMPACT_HEIGHT, 1432, 28)
    withdraw_index = events.index("withdraw")
    positioned_index = events.index(("native", expected, False))
    shown_index = events.index(("show", expected))
    assert withdraw_index < positioned_index < shown_index
    assert overlay._visible is True


def test_startup_status_distinguishes_renderer_from_story_readiness():
    assert startup_status(_state("launch", "warmup"))[0] == (
        "Reactor V interface ready · GTA V is still loading…"
    )
    assert "entering Story Mode" in startup_status(
        _state("launch", "native", "assets", "dotnet", "reactor"),
    )[0]
    assert startup_status(
        _state("launch", "native", "assets", "dotnet", "reactor", "story"),
    )[0] == "Story Mode ready"
    assert startup_status(_state(failure="startup failed"))[0] == "startup failed"


def test_reactor_acronym_spells_the_framework_name():
    assert "".join(letter for letter, _word in REACTOR_ACRONYM) == "REACTOR"
    assert " ".join(word for _letter, word in REACTOR_ACRONYM) == (
        "Real-time Embedded Application Component Toolkit Overlay Runtime"
    )


def test_acronym_effect_is_a_bounded_defocus_scan_resolving_to_sharp_text():
    assert 4 <= len(ACRONYM_EFFECT_FRAMES) <= 12
    assert len({frame.title_color for frame in ACRONYM_EFFECT_FRAMES}) >= 4
    assert [frame.scan_progress for frame in ACRONYM_EFFECT_FRAMES] == sorted(
        frame.scan_progress for frame in ACRONYM_EFFECT_FRAMES
    )
    assert ACRONYM_EFFECT_FRAMES[-1].title_color == ACCENT
    assert ACRONYM_EFFECT_FRAMES[0].trail_color != TRANSPARENT_KEY
    assert ACRONYM_EFFECT_FRAMES[-1].trail_color == TRANSPARENT_KEY
    assert ACRONYM_EFFECT_FRAMES[-1].ghost_color == TRANSPARENT_KEY
    assert ACRONYM_EFFECT_FRAMES[-1].scan_color == TRANSPARENT_KEY
    assert [frame.blur_offset for frame in ACRONYM_EFFECT_FRAMES] == sorted(
        (frame.blur_offset for frame in ACRONYM_EFFECT_FRAMES),
        reverse=True,
    )
    assert ACRONYM_EFFECT_FRAMES[0].blur_offset > 0
    assert ACRONYM_EFFECT_FRAMES[-1].blur_offset == 0


def test_acronym_animation_keeps_only_one_callback_in_flight():
    class Canvas:
        def itemconfigure(self, *_args, **_kwargs):
            pass

        def coords(self, *_args, **_kwargs):
            pass

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay._handoff_complete = False
    overlay._acronym_index = 0
    overlay.canvas = Canvas()
    overlay.compact_trail_item = 1
    overlay.compact_title_item = 2
    overlay.compact_scan_item = 3
    overlay.compact_blur_left_item = 4
    overlay.compact_blur_right_item = 5
    pending = []
    scheduled_delays = []

    def schedule(delay, callback):
        scheduled_delays.append(delay)
        pending.append(callback)

    overlay._schedule = schedule
    overlay._cycle_acronym()

    for _ in range(len(ACRONYM_EFFECT_FRAMES)):
        assert len(pending) == 1
        pending.pop(0)()

    assert len(pending) == 1
    assert scheduled_delays == [
        *(
            [bootstrap_ui.ACRONYM_EFFECT_INTERVAL_MS]
            * len(ACRONYM_EFFECT_FRAMES)
        ),
        bootstrap_ui.ACRONYM_INTERVAL_MS,
    ]


def test_full_acronym_resolves_to_clean_reactor_title_and_holds():
    configured = []

    class Canvas:
        def itemconfigure(self, item, **kwargs):
            configured.append((item, kwargs))

        def coords(self, *_args, **_kwargs):
            pass

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay._handoff_complete = False
    overlay._acronym_index = len(REACTOR_ACRONYM) - 1
    overlay.canvas = Canvas()
    overlay.compact_trail_item = 1
    overlay.compact_title_item = 2
    overlay.compact_scan_item = 3
    overlay.compact_blur_left_item = 4
    overlay.compact_blur_right_item = 5
    pending = []
    delays = []

    def schedule(delay, callback):
        delays.append(delay)
        pending.append(callback)

    overlay._schedule = schedule
    overlay._cycle_acronym()

    assert ACRONYM_DISPLAY_SEQUENCE[overlay._acronym_index] == "REACTOR"
    assert (2, {"text": "REACTOR"}) in configured
    for _ in range(len(ACRONYM_EFFECT_FRAMES)):
        pending.pop(0)()

    assert delays[-1] == REACTOR_TITLE_HOLD_MS
    pending.pop(0)()
    assert ACRONYM_DISPLAY_SEQUENCE[overlay._acronym_index] == "R · REAL-TIME"


def test_acronym_animation_does_not_schedule_after_handoff():
    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay._handoff_complete = True
    overlay._schedule = lambda *_args: pytest.fail("scheduled after handoff")

    overlay._cycle_acronym()
    overlay._animate_acronym(0)


def test_story_handoff_settles_every_effect_layer_to_clean_reactor_title():
    configured = []

    class Canvas:
        def itemconfigure(self, item, **kwargs):
            configured.append((item, kwargs))

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay._acronym_index = 2
    overlay.canvas = Canvas()
    overlay.compact_trail_item = 1
    overlay.compact_title_item = 2
    overlay.compact_scan_item = 3
    overlay.compact_blur_left_item = 4
    overlay.compact_blur_right_item = 5

    overlay._settle_acronym_title()

    assert ACRONYM_DISPLAY_SEQUENCE[overlay._acronym_index] == "REACTOR"
    assert (2, {"text": "REACTOR", "fill": ACCENT}) in configured
    for item in (1, 4, 5):
        assert (item, {"fill": TRANSPARENT_KEY}) in configured
    assert (3, {"fill": TRANSPARENT_KEY, "width": 1}) in configured


def test_scheduler_removes_completed_jobs_and_refuses_work_after_close():
    callbacks = {}

    class Parent:
        def after(self, delay, callback):
            identifier = f"job-{delay}-{len(callbacks)}"
            callbacks[identifier] = callback
            return identifier

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay.parent = Parent()
    overlay.closed = False
    overlay._after_ids = set()
    completed = []

    overlay._schedule(45, lambda: completed.append(True))

    assert overlay._after_ids == {"job-45-0"}
    callbacks["job-45-0"]()
    assert completed == [True]
    assert overlay._after_ids == set()

    overlay.closed = True
    overlay._schedule(45, lambda: pytest.fail("ran after close"))
    assert len(callbacks) == 1


def test_stop_cancels_every_pending_animation_callback_once():
    cancelled = []
    closed = []

    class Parent:
        def after_cancel(self, identifier):
            cancelled.append(identifier)

    class Window:
        def destroy(self):
            closed.append("window")

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay.parent = Parent()
    overlay.window = Window()
    overlay.closed = False
    overlay._after_ids = {"frame-1", "frame-2", "poll-1"}
    overlay.on_closed = lambda: closed.append("callback")

    overlay.stop()
    overlay.stop()

    assert set(cancelled) == {"frame-1", "frame-2", "poll-1"}
    assert len(cancelled) == 3
    assert overlay._after_ids == set()
    assert closed == ["window", "callback"]


def test_overlay_environment_is_a_small_injectable_os_snapshot():
    environment = OverlayEnvironment(
        process_running=True,
        bounds=(-1920, 0, 1920, 1080),
        safe_foreground=False,
    )

    assert environment.process_running is True
    assert environment.bounds == (-1920, 0, 1920, 1080)
    assert environment.safe_foreground is False


def test_poll_uses_injected_environment_and_keeps_harness_terminal_state_open():
    environment = OverlayEnvironment(
        process_running=True,
        bounds=(100, 40, 1280, 720),
        safe_foreground=False,
    )
    state = BootstrapState(
        frozenset({"launch", "reactor", "story"}),
        terminal=True,
        process_seen=True,
    )

    class Monitor:
        def __init__(self):
            self.samples = []

        def sample(self, *, process_running):
            self.samples.append(process_running)
            return state

    overlay = bootstrap_ui.ReactorBootstrapWindow.__new__(
        bootstrap_ui.ReactorBootstrapWindow,
    )
    overlay.monitor = Monitor()
    overlay._environment_probe = lambda: environment
    overlay._close_on_terminal = False
    overlay._handoff_complete = False
    overlay._position = lambda bounds: events.append(("position", bounds))
    overlay._set_visible = lambda visible: events.append(("visible", visible))
    overlay._render_state = lambda value: events.append(("render", value))
    overlay._schedule = lambda delay, callback: events.append(("schedule", delay))
    overlay._emit = lambda message: events.append(("log", message))
    events = []

    overlay._poll()

    assert overlay.monitor.samples == [True]
    assert events == [
        ("position", environment.bounds),
        ("visible", False),
        ("render", state),
        ("schedule", bootstrap_ui.POLL_INTERVAL_MS),
    ]
