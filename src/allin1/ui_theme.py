"""Shared, persistent desktop theming for ALLIN1 applications.

The Launcher and SDK deliberately share the small ``ui-settings.json`` contract.
This module owns the Launcher implementation while keeping preference parsing and
system-theme resolution independent from Tk so they can be tested headlessly.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tkinter as tk
from ctypes import wintypes
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import ttk
from typing import Callable, Literal, Mapping


ThemeMode = Literal["light", "dark", "system"]
ResolvedTheme = Literal["light", "dark"]
THEME_MODES: tuple[ThemeMode, ...] = ("light", "dark", "system")
UI_SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class UiSettings:
    """Cross-application UI preferences shared by Launcher and SDK."""

    schema_version: int = UI_SETTINGS_SCHEMA_VERSION
    theme: ThemeMode = "system"


@dataclass(frozen=True)
class ThemePalette:
    """Semantic colors used by the Launcher shell and its child tools."""

    name: ResolvedTheme
    body: str
    surface: str
    surface_alt: str
    surface_hover: str
    surface_selected: str
    border: str
    border_strong: str
    text: str
    text_strong: str
    muted: str
    disabled_text: str
    disabled_bg: str
    accent: str
    accent_hover: str
    accent_selected: str
    accent_surface: str
    inverse_text: str
    success: str
    warning: str
    warning_surface: str
    warning_text: str
    danger: str
    danger_surface: str
    danger_hover: str
    input: str
    selection: str


LIGHT_PALETTE = ThemePalette(
    name="light",
    body="#f4f7f5",
    surface="#ffffff",
    surface_alt="#eef3f0",
    surface_hover="#e2ebe6",
    surface_selected="#dcefe3",
    border="#d4ddd9",
    border_strong="#aebdb5",
    text="#24332d",
    text_strong="#173d32",
    muted="#52635c",
    disabled_text="#84928c",
    disabled_bg="#e5ebe7",
    accent="#2d9c50",
    accent_hover="#1f7f42",
    accent_selected="#176b36",
    accent_surface="#dcefe3",
    inverse_text="#ffffff",
    success="#18753a",
    warning="#d09a22",
    warning_surface="#fff8e8",
    warning_text="#714b00",
    danger="#b42318",
    danger_surface="#fff0ed",
    danger_hover="#ffe2dc",
    input="#ffffff",
    selection="#176b36",
)

DARK_PALETTE = ThemePalette(
    name="dark",
    body="#111815",
    surface="#18211d",
    surface_alt="#202c27",
    surface_hover="#293832",
    surface_selected="#1f4a32",
    border="#34453e",
    border_strong="#4b6259",
    text="#dce8e2",
    text_strong="#f2f8f5",
    muted="#9eb1a8",
    disabled_text="#71827a",
    disabled_bg="#26322d",
    accent="#43bb68",
    accent_hover="#35a859",
    accent_selected="#27934c",
    accent_surface="#1c3d2b",
    inverse_text="#ffffff",
    success="#62cf82",
    warning="#e0ab41",
    warning_surface="#3a301c",
    warning_text="#f1ce79",
    danger="#ef786c",
    danger_surface="#3b2321",
    danger_hover="#50302c",
    input="#101713",
    selection="#287d48",
)


def normalize_theme(value: object, default: ThemeMode = "system") -> ThemeMode:
    """Return a canonical preference without trusting external JSON values."""

    normalized = str(value).strip().lower() if isinstance(value, str) else ""
    if normalized in THEME_MODES:
        return normalized  # type: ignore[return-value]
    return default


def default_ui_settings_path(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> Path:
    """Resolve the shared per-user preference file without touching disk."""

    values = os.environ if environ is None else environ
    base = values.get("LOCALAPPDATA") or values.get("XDG_CONFIG_HOME")
    if base:
        root = Path(base).expanduser()
    else:
        user_home = Path.home() if home is None else Path(home)
        root = (
            user_home / "AppData" / "Local"
            if os.name == "nt"
            else user_home / ".config"
        )
    return root / "ALLIN1" / "ui-settings.json"


def load_ui_settings(path: Path | None = None) -> UiSettings:
    """Load preferences fail-closed, retaining a usable system default."""

    settings_path = path or default_ui_settings_path()
    try:
        raw = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return UiSettings()
    if not isinstance(raw, dict):
        return UiSettings()
    return UiSettings(theme=normalize_theme(raw.get("theme")))


def save_ui_settings(settings: UiSettings, path: Path | None = None) -> Path:
    """Atomically save the tiny shared preference contract."""

    settings_path = path or default_ui_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = UiSettings(theme=normalize_theme(settings.theme))
    # The SDK shares this document and future releases may add independent UI
    # keys. Preserve fields we do not own instead of downgrading their state.
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        existing = {}
    document = dict(existing) if isinstance(existing, dict) else {}
    document.update(asdict(normalized))
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    temporary = settings_path.with_name(
        f".{settings_path.name}.{os.getpid()}.tmp"
    )
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(settings_path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return settings_path


def _read_windows_apps_use_light_theme() -> int:
    import winreg

    path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
        value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    return int(value)


def detect_system_theme(
    *,
    platform_name: str | None = None,
    windows_value_reader: Callable[[], int] | None = None,
) -> ResolvedTheme:
    """Resolve the OS application theme, with light as the portable fallback."""

    platform_value = sys.platform if platform_name is None else platform_name
    if platform_value != "win32":
        return "light"
    reader = windows_value_reader or _read_windows_apps_use_light_theme
    try:
        return "dark" if reader() == 0 else "light"
    except (OSError, ValueError, TypeError):
        return "light"


def resolve_theme(
    mode: str,
    *,
    detector: Callable[[], ResolvedTheme] = detect_system_theme,
) -> ResolvedTheme:
    normalized = normalize_theme(mode)
    return detector() if normalized == "system" else normalized


def palette_for(theme: str) -> ThemePalette:
    return DARK_PALETTE if theme == "dark" else LIGHT_PALETTE


def configure_ttk_theme(root: tk.Misc, palette: ThemePalette) -> ttk.Style:
    """Apply all named and base ttk styles used throughout the Launcher."""

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(
        ".", font=("Segoe UI", 10), background=palette.body,
        foreground=palette.text,
    )
    style.configure("TFrame", background=palette.body)
    style.configure("TLabel", background=palette.body, foreground=palette.text)
    style.configure(
        "TButton", padding=(11, 7), background=palette.surface_alt,
        foreground=palette.text, bordercolor=palette.border,
        lightcolor=palette.border, darkcolor=palette.border,
    )
    style.map(
        "TButton",
        background=[
            ("disabled", palette.disabled_bg),
            ("pressed", palette.surface_selected),
            ("active", palette.surface_hover),
        ],
        foreground=[("disabled", palette.disabled_text)],
    )
    for name in ("TEntry", "TSpinbox"):
        style.configure(
            name, padding=(7, 6), fieldbackground=palette.input,
            background=palette.input, foreground=palette.text,
            insertcolor=palette.text, bordercolor=palette.border,
            lightcolor=palette.border, darkcolor=palette.border,
            arrowcolor=palette.text,
        )
        style.map(
            name,
            fieldbackground=[("disabled", palette.disabled_bg)],
            foreground=[("disabled", palette.disabled_text)],
        )
    style.configure(
        "TCombobox", padding=(6, 5), fieldbackground=palette.input,
        background=palette.surface_alt, foreground=palette.text,
        arrowcolor=palette.text, bordercolor=palette.border,
        lightcolor=palette.border, darkcolor=palette.border,
        selectbackground=palette.selection, selectforeground=palette.inverse_text,
    )
    style.map(
        "TCombobox",
        fieldbackground=[
            ("readonly", palette.input), ("disabled", palette.disabled_bg),
        ],
        foreground=[
            ("readonly", palette.text), ("disabled", palette.disabled_text),
        ],
        background=[("active", palette.surface_hover)],
    )
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(
            name, padding=(0, 2), background=palette.body,
            foreground=palette.text, indicatorcolor=palette.input,
            indicatorbackground=palette.input,
        )
        style.map(
            name,
            background=[("active", palette.body)],
            foreground=[("disabled", palette.disabled_text)],
            indicatorcolor=[("selected", palette.accent)],
        )
    style.configure("Surface.TFrame", background=palette.surface)
    style.configure(
        "Surface.TLabel", background=palette.surface, foreground=palette.text,
    )
    style.configure(
        "SurfaceMuted.TLabel", background=palette.surface,
        foreground=palette.muted,
    )
    style.configure(
        "Card.TFrame", background=palette.surface, borderwidth=1,
        bordercolor=palette.border, relief="solid",
    )
    style.configure(
        "TLabelframe", background=palette.surface, bordercolor=palette.border,
        lightcolor=palette.border, darkcolor=palette.border,
    )
    style.configure(
        "TLabelframe.Label", background=palette.body,
        foreground=palette.accent_hover, font=("Segoe UI Semibold", 10),
    )
    style.configure(
        "PageTitle.TLabel", font=("Segoe UI Semibold", 17),
        foreground=palette.text_strong,
    )
    style.configure("PageIntro.TLabel", foreground=palette.muted)
    style.configure(
        "Section.TLabel", font=("Segoe UI Semibold", 11),
        foreground=palette.text_strong,
    )
    style.configure(
        "FieldLabel.TLabel", font=("Segoe UI Semibold", 9),
        foreground=palette.muted,
    )
    style.configure(
        "Accent.TButton", background=palette.accent,
        foreground=palette.inverse_text, font=("Segoe UI Semibold", 10),
        padding=(13, 8), bordercolor=palette.accent_hover,
    )
    style.map(
        "Accent.TButton",
        background=[
            ("active", palette.accent_hover),
            ("pressed", palette.accent_selected),
            ("disabled", palette.disabled_bg),
        ],
        foreground=[("disabled", palette.disabled_text)],
    )
    style.configure("Quiet.TButton", padding=(10, 7))
    style.configure(
        "Danger.TButton", background=palette.danger_surface,
        foreground=palette.danger, padding=(10, 7),
        font=("Segoe UI Semibold", 10), bordercolor=palette.danger,
    )
    style.map(
        "Danger.TButton",
        background=[
            ("active", palette.danger_hover),
            ("disabled", palette.disabled_bg),
        ],
        foreground=[("disabled", palette.disabled_text)],
    )
    style.configure(
        "Nav.TButton", anchor="w", padding=(16, 11), relief="flat",
        background=palette.surface_alt, foreground=palette.muted,
        bordercolor=palette.surface_alt,
    )
    style.map(
        "Nav.TButton",
        background=[("active", palette.surface_hover), ("focus", palette.surface_hover)],
        foreground=[("disabled", palette.disabled_text)],
    )
    style.configure(
        "NavSelected.TButton", anchor="w", padding=(16, 11), relief="flat",
        background=palette.accent_surface, foreground=palette.accent,
        font=("Segoe UI Semibold", 10), bordercolor=palette.accent_surface,
    )
    style.map(
        "NavSelected.TButton",
        background=[
            ("active", palette.surface_selected),
            ("focus", palette.surface_selected),
        ],
    )
    style.configure(
        "Success.Status.TLabel", font=("Segoe UI Semibold", 15),
        foreground=palette.success,
    )
    style.configure(
        "Warning.Status.TLabel", font=("Segoe UI Semibold", 15),
        foreground=palette.warning,
    )
    style.configure(
        "Error.Status.TLabel", font=("Segoe UI Semibold", 15),
        foreground=palette.danger,
    )
    style.configure("Muted.TLabel", foreground=palette.muted)
    style.configure(
        "Link.TButton", relief="flat", borderwidth=0, padding=(4, 3),
        background=palette.body, foreground=palette.accent,
        font=("Segoe UI Semibold", 9, "underline"),
    )
    style.map(
        "Link.TButton",
        foreground=[("active", palette.accent_hover), ("focus", palette.accent_hover)],
        background=[("active", palette.surface_hover), ("focus", palette.surface_hover)],
    )
    style.configure(
        "WarningPanel.TFrame", background=palette.warning_surface,
        borderwidth=1, bordercolor=palette.warning, relief="solid",
    )
    style.configure(
        "WarningPanel.TLabel", background=palette.warning_surface,
        foreground=palette.warning_text,
    )
    style.configure("TNotebook", background=palette.body, borderwidth=0)
    style.configure(
        "TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(10, 6),
        background=palette.surface_alt, foreground=palette.muted,
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", palette.surface), ("active", palette.surface_hover),
        ],
        foreground=[("selected", palette.accent)],
    )
    style.configure(
        "Treeview", rowheight=28, font=("Segoe UI", 10),
        background=palette.input, fieldbackground=palette.input,
        foreground=palette.text, bordercolor=palette.border,
    )
    style.configure(
        "Treeview.Heading", font=("Segoe UI Semibold", 10), padding=(6, 6),
        background=palette.surface_alt, foreground=palette.text,
        bordercolor=palette.border,
    )
    style.map(
        "Treeview",
        background=[("selected", palette.selection)],
        foreground=[("selected", palette.inverse_text)],
    )
    style.configure(
        "TScrollbar", background=palette.surface_alt,
        troughcolor=palette.body, arrowcolor=palette.text,
        bordercolor=palette.border,
    )
    style.map("TScrollbar", background=[("active", palette.surface_hover)])
    style.configure(
        "TProgressbar", background=palette.accent,
        troughcolor=palette.surface_alt, bordercolor=palette.border,
    )
    style.configure("TSeparator", background=palette.border)
    return style


_LIGHT_BACKGROUND_ROLES = {
    "#f4f7f5": "body",
    "#f8fafc": "body",
    "#ffffff": "surface",
    "#eef3f0": "surface_alt",
    "#e2ebe6": "surface_hover",
    "#dcefe3": "surface_selected",
    "#d2e8da": "surface_selected",
    "#c9e4d3": "surface_selected",
    "#d4ddd9": "border",
    "#d5ded9": "border",
    "#aebdb5": "border_strong",
    "#fff8e8": "warning_surface",
    "#d09a22": "warning",
    "#fff0ed": "danger_surface",
    "#ffe2dc": "danger_hover",
    "#c94b3b": "danger",
    "#f1f1f1": "disabled_bg",
    "#c8d4cc": "disabled_bg",
    "#2d9c50": "accent",
    "#1f7f42": "accent_hover",
    "#176b36": "accent_selected",
    # Tk frequently reports an explicitly white widget background using the
    # named color rather than ``#ffffff``.  In a background slot it is a
    # surface, not inverse text.
    "white": "surface",
}
_LIGHT_FOREGROUND_ROLES = {
    "#24332d": "text",
    "#1e2925": "text",
    "#26332e": "text",
    "#173d32": "text_strong",
    "#52635c": "muted",
    "#3f6659": "muted",
    "#646e69": "muted",
    "#84928c": "disabled_text",
    "#8b9691": "disabled_text",
    "#66756e": "disabled_text",
    "#1f7f42": "accent_hover",
    "#176b36": "accent_selected",
    "#0e5228": "accent_selected",
    "#18753a": "success",
    "#9a6700": "warning",
    "#714b00": "warning_text",
    "#9a3412": "warning_text",
    "#a43a2b": "danger",
    "#b42318": "danger",
    "#c94b3b": "danger",
    "#ffffff": "inverse_text",
    "white": "inverse_text",
}


def _theme_role_lookup() -> tuple[dict[str, str], dict[str, str]]:
    backgrounds = dict(_LIGHT_BACKGROUND_ROLES)
    foregrounds = dict(_LIGHT_FOREGROUND_ROLES)
    for palette in (LIGHT_PALETTE, DARK_PALETTE):
        for role in ThemePalette.__dataclass_fields__:
            value = getattr(palette, role)
            if not isinstance(value, str) or not value.startswith("#"):
                continue
            if role in {
                "body", "surface", "surface_alt", "surface_hover",
                "surface_selected", "border", "border_strong", "disabled_bg",
                "accent", "accent_hover", "accent_selected", "accent_surface",
                "success", "warning", "warning_surface", "danger",
                "danger_surface", "danger_hover", "input", "selection",
            }:
                backgrounds.setdefault(value.lower(), role)
            if role in {
                "text", "text_strong", "muted", "disabled_text", "accent",
                "accent_hover", "accent_selected", "inverse_text", "success",
                "warning", "warning_text", "danger",
            }:
                foregrounds.setdefault(value.lower(), role)
    return backgrounds, foregrounds


_BACKGROUND_ROLES, _FOREGROUND_ROLES = _theme_role_lookup()


def _mapped_color(value: object, palette: ThemePalette, *, foreground: bool) -> str | None:
    if value is None:
        return None
    roles = _FOREGROUND_ROLES if foreground else _BACKGROUND_ROLES
    # Real Tk/ttk widgets return typed Tcl color/border objects from ``cget``;
    # mocks and pure tests usually return plain strings.  Normalize both.
    normalized = str(value).strip().lower()
    role = roles.get(normalized)
    if role is None:
        return None
    return str(getattr(palette, role))


def _configure_if_supported(widget: tk.Misc, **options: str) -> None:
    available = set(widget.keys())
    selected = {key: value for key, value in options.items() if key in available}
    if not selected:
        return
    try:
        widget.configure(**selected)
    except tk.TclError:
        pass


def _theme_native_widget(widget: tk.Misc, palette: ThemePalette) -> None:
    if isinstance(widget, tk.Menu):
        _configure_if_supported(
            widget,
            background=palette.surface,
            foreground=palette.text,
            activebackground=palette.selection,
            activeforeground=palette.inverse_text,
            disabledforeground=palette.disabled_text,
            selectcolor=palette.accent,
            borderwidth=1,
        )
        return
    if isinstance(widget, (tk.Text, tk.Listbox)):
        _configure_if_supported(
            widget,
            background=palette.input,
            foreground=palette.text,
            insertbackground=palette.text,
            selectbackground=palette.selection,
            selectforeground=palette.inverse_text,
            highlightbackground=palette.border,
            highlightcolor=palette.accent,
            disabledforeground=palette.disabled_text,
        )
        return

    background = None
    foreground = None
    active_background = None
    active_foreground = None
    try:
        if "background" in widget.keys():
            background = _mapped_color(widget.cget("background"), palette, foreground=False)
        if "foreground" in widget.keys():
            foreground = _mapped_color(widget.cget("foreground"), palette, foreground=True)
        if "activebackground" in widget.keys():
            active_background = _mapped_color(
                widget.cget("activebackground"), palette, foreground=False,
            )
        if "activeforeground" in widget.keys():
            active_foreground = _mapped_color(
                widget.cget("activeforeground"), palette, foreground=True,
            )
    except tk.TclError:
        return
    options = {}
    if background:
        options["background"] = background
    if foreground:
        options["foreground"] = foreground
    if active_background:
        options["activebackground"] = active_background
    if active_foreground:
        options["activeforeground"] = active_foreground
    _configure_if_supported(widget, **options)


def apply_windows_titlebar(window: tk.Misc, dark: bool) -> None:
    """Best-effort immersive title bars for Windows 10/11 Tk windows."""

    if os.name != "nt" or not isinstance(window, (tk.Tk, tk.Toplevel)):
        return
    try:
        window.update_idletasks()
        hwnd = int(window.winfo_id())
        parent = ctypes.windll.user32.GetParent(wintypes.HWND(hwnd))
        if parent:
            hwnd = int(parent)
        enabled = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), ctypes.c_uint(attribute),
                ctypes.byref(enabled), ctypes.sizeof(enabled),
            )
            if result == 0:
                break
    except (AttributeError, OSError, tk.TclError, ValueError):
        pass


def apply_widget_tree(widget: tk.Misc, palette: ThemePalette) -> None:
    """Restyle raw Tk widgets while honoring explicitly exempt visual surfaces."""

    if bool(getattr(widget, "_allin1_theme_exempt", False)):
        return
    _theme_native_widget(widget, palette)
    if isinstance(widget, (tk.Tk, tk.Toplevel)):
        _configure_if_supported(widget, background=palette.body)
        apply_windows_titlebar(widget, palette.name == "dark")
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return
    for child in children:
        apply_widget_tree(child, palette)


def _configure_option_database(root: tk.Misc, palette: ThemePalette) -> None:
    options = {
        "*Menu.background": palette.surface,
        "*Menu.foreground": palette.text,
        "*Menu.activeBackground": palette.selection,
        "*Menu.activeForeground": palette.inverse_text,
        "*Menu.disabledForeground": palette.disabled_text,
        "*Menu.selectColor": palette.accent,
        "*TCombobox*Listbox.background": palette.input,
        "*TCombobox*Listbox.foreground": palette.text,
        "*TCombobox*Listbox.selectBackground": palette.selection,
        "*TCombobox*Listbox.selectForeground": palette.inverse_text,
    }
    for pattern, value in options.items():
        try:
            root.option_add(pattern, value, 80)
        except tk.TclError:
            pass


def apply_application_theme(
    root: tk.Misc,
    mode: str,
    *,
    detector: Callable[[], ResolvedTheme] = detect_system_theme,
) -> ThemePalette:
    """Apply and publish the effective palette for a complete Tk application."""

    normalized = normalize_theme(mode)
    resolved = resolve_theme(normalized, detector=detector)
    palette = palette_for(resolved)
    setattr(root, "_allin1_theme_mode", normalized)
    setattr(root, "_allin1_resolved_theme", resolved)
    setattr(root, "_allin1_palette", palette)
    _configure_option_database(root, palette)
    configure_ttk_theme(root, palette)
    apply_widget_tree(root, palette)
    return palette


def current_palette(widget: tk.Misc) -> ThemePalette:
    """Return the owning application's palette, defaulting safely to light."""

    try:
        root = widget.winfo_toplevel()
    except tk.TclError:
        return LIGHT_PALETTE
    palette = getattr(root, "_allin1_palette", None)
    if isinstance(palette, ThemePalette):
        return palette
    try:
        application_root = root._root()
    except (AttributeError, tk.TclError):
        application_root = None
    palette = getattr(application_root, "_allin1_palette", None)
    return palette if isinstance(palette, ThemePalette) else LIGHT_PALETTE


def apply_current_theme(widget: tk.Misc) -> ThemePalette:
    """Theme a lazily created embedded panel or Toplevel from its owner."""

    palette = current_palette(widget)
    apply_widget_tree(widget, palette)
    return palette
