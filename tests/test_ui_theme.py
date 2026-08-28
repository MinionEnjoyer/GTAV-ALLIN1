"""Headless tests for the Launcher/SDK shared theme contract."""

from __future__ import annotations

import json
from pathlib import Path

from allin1.ui_theme import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    UiSettings,
    default_ui_settings_path,
    detect_system_theme,
    load_ui_settings,
    normalize_theme,
    palette_for,
    resolve_theme,
    save_ui_settings,
    _mapped_color,
)


def test_shared_ui_settings_path_uses_local_appdata(tmp_path):
    assert default_ui_settings_path({"LOCALAPPDATA": str(tmp_path)}) == (
        tmp_path / "ALLIN1" / "ui-settings.json"
    )


def test_theme_normalization_is_case_insensitive_and_fail_closed():
    assert normalize_theme(" DARK ") == "dark"
    assert normalize_theme("Light") == "light"
    assert normalize_theme("SYSTEM") == "system"
    assert normalize_theme("neon") == "system"
    assert normalize_theme(None) == "system"


def test_missing_or_corrupt_settings_fall_back_to_system(tmp_path):
    path = tmp_path / "ui-settings.json"
    assert load_ui_settings(path) == UiSettings()
    path.write_text("{broken", encoding="utf-8")
    assert load_ui_settings(path) == UiSettings()
    path.write_text('"not-an-object"', encoding="utf-8")
    assert load_ui_settings(path) == UiSettings()


def test_shared_settings_round_trip_preserves_future_fields(tmp_path):
    path = tmp_path / "ALLIN1" / "ui-settings.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"schema_version": 7, "theme": "light", "sdk_layout": "wide"}),
        encoding="utf-8",
    )

    save_ui_settings(UiSettings(theme="dark"), path)

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document == {
        "schema_version": 1,
        "sdk_layout": "wide",
        "theme": "dark",
    }
    assert load_ui_settings(path).theme == "dark"


def test_windows_system_theme_resolver_and_portable_fallback():
    assert detect_system_theme(
        platform_name="win32", windows_value_reader=lambda: 0,
    ) == "dark"
    assert detect_system_theme(
        platform_name="win32", windows_value_reader=lambda: 1,
    ) == "light"
    assert detect_system_theme(platform_name="linux") == "light"

    def unavailable() -> int:
        raise OSError("registry unavailable")

    assert detect_system_theme(
        platform_name="win32", windows_value_reader=unavailable,
    ) == "light"


def test_system_mode_is_resolved_lazily_and_palettes_are_semantic():
    assert resolve_theme("system", detector=lambda: "dark") == "dark"
    assert resolve_theme("LIGHT", detector=lambda: "dark") == "light"
    assert palette_for("dark") is DARK_PALETTE
    assert palette_for("light") is LIGHT_PALETTE
    assert DARK_PALETTE.body != LIGHT_PALETTE.body
    assert DARK_PALETTE.text != LIGHT_PALETTE.text
    assert DARK_PALETTE.accent != DARK_PALETTE.body


def test_explicit_light_surface_role_wins_over_duplicate_input_color():
    assert _mapped_color(
        "#ffffff", DARK_PALETTE, foreground=False,
    ) == DARK_PALETTE.surface
    assert _mapped_color(
        "white", DARK_PALETTE, foreground=False,
    ) == DARK_PALETTE.surface


def test_tk_typed_color_values_are_normalized_before_mapping():
    class TclColor:
        def __str__(self) -> str:
            return "#173d32"

    assert _mapped_color(
        TclColor(), DARK_PALETTE, foreground=True,
    ) == DARK_PALETTE.text_strong


def test_lazy_launcher_panels_apply_the_owning_application_theme():
    root = Path(__file__).resolve().parents[1] / "src" / "allin1"
    modules = (
        "help_center.py",
        "customization_ui.py",
        "sdk_installer_ui.py",
        "asset_viewer.py",
        "rpf_explorer.py",
        "addon_sdk_ui.py",
    )
    for name in modules:
        source = (root / name).read_text(encoding="utf-8")
        assert "apply_current_theme(" in source, name


def test_reactor_composited_surface_is_exempt_from_desktop_theme_passes():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "allin1" / "reactor_bootstrap_ui.py"
    ).read_text(encoding="utf-8")
    assert "self.window._allin1_theme_exempt = True" in source
