"""Small Tkinter desktop manager for GTA V ALLIN1."""

from __future__ import annotations

import argparse
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from allin1.config import Config
from allin1.extensions import (
    ExtensionManifest,
    ExtensionRegistry,
    apply_settings_to_config,
)
from allin1.game_launcher import launch_gta
from allin1.logging import setup_logging
from allin1.manager import InstallationStatus, ModManager
from allin1.mods import (
    ModIntegrationService, ModManifest, default_mod_catalog, open_mod_package,
)
from allin1.launcher_handoff import (
    LauncherHandoff,
    consume_launcher_handoffs,
    publish_launcher_handoff,
)
from allin1.customization_ui import CharacterCustomizationDialog
from allin1.addon_sdk import AddonManifest, AddonSdkCatalog
from allin1.asset_viewer import AssetViewerDialog
from allin1.rpf_explorer import RpfExplorerDialog
from allin1.help_center import HelpCenterDialog
from allin1.sdk_installer_ui import SdkManagerDialog
from allin1.sdk_manager import default_sdk_root, read_sdk_status
from allin1 import __version__
from allin1.versioning import fetch_latest_release
from allin1.profiles import ProfileStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSET_DIR = Path(__file__).resolve().parent / "assets"
WINDOWS_APP_ID = "MinionEnjoyer.GTAVALLIN1.Launcher"
_INSTANCE_MUTEX: int | None = None
PACKAGE_LIBRARY_WATCH_INTERVAL_MS = 2000
LAUNCHER_HANDOFF_POLL_INTERVAL_MS = 500


@dataclass(frozen=True)
class StatusPresentation:
    """Plain-language launcher status derived from installation facts."""

    headline: str
    detail: str
    tone: str
    can_launch: bool
    can_install: bool
    can_uninstall: bool


def _status_presentation(status: InstallationStatus) -> StatusPresentation:
    """Convert low-level installation checks into an actionable summary."""
    if not status.valid_game:
        return StatusPresentation(
            "Select your GTA V folder",
            "Choose the folder containing GTA5.exe or GTA5_Enhanced.exe.",
            "warning",
            False,
            False,
            False,
        )

    missing = []
    if not status.scripthookv_installed:
        missing.append("ScriptHookV")
    if not status.shvdn_installed:
        missing.append("ScriptHookVDotNet Enhanced")

    if not status.mod_installed:
        headline = "ALLIN1 is ready to install"
        detail = "Install the Story Mode client, then run the health check before playing."
        tone = "warning"
    elif missing:
        headline = "Required components are missing"
        detail = "Install " + " and ".join(missing) + " before launching with ALLIN1."
        tone = "error"
    elif status.installed_version != status.manager_version:
        installed = status.installed_version or "unknown"
        headline = "Client update available"
        detail = (
            f"Installed client {installed}; launcher {status.manager_version}. "
            "Use Install / Repair to synchronize them."
        )
        tone = "warning"
    else:
        headline = "Ready to play"
        detail = "The ALLIN1 client and required script components are installed."
        tone = "success"

    return StatusPresentation(
        headline,
        detail,
        tone,
        True,
        True,
        status.mod_installed,
    )


def _register_windows_app() -> None:
    """Set taskbar identity before Tk creates the native window."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)


def _focus_existing_window(title_prefix: str) -> bool:
    """Restore and focus an existing ALLIN1 shell on Windows."""
    if os.name != "nt":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def visit(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value.startswith(title_prefix):
                matches.append(int(hwnd))
                return False
        return True

    user32.EnumWindows(visit, 0)
    if not matches:
        return False
    user32.ShowWindow(matches[0], 9)  # SW_RESTORE
    user32.SetForegroundWindow(matches[0])
    return True


def _claim_single_instance(handoff: LauncherHandoff | None = None) -> bool:
    """Keep launcher operations in one persistent main window."""
    global _INSTANCE_MUTEX
    if os.name != "nt":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(
        None, False, "Local\\MinionEnjoyer.GTAVALLIN1.Launcher",
    )
    if not handle:
        return True
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        if handoff is not None:
            try:
                publish_launcher_handoff(handoff)
            except (OSError, ValueError) as exc:
                logging.getLogger("allin1.gui").warning(
                    "Could not forward Launcher package request: %s", exc,
                )
        _focus_existing_window("ALLIN1 Launcher")
        return False
    _INSTANCE_MUTEX = int(handle)
    return True


class QueueLogHandler(logging.Handler):
    def __init__(self, messages: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.put(("log", self.format(record)))


def _operation_progress_text(label: str, percentage: int) -> str:
    return f"{label} - {max(0, min(100, int(percentage)))}%"


def _supports_package_traffic_intent(manifest: ModManifest) -> bool:
    """Return whether the package owns the typed, default-off traffic gate."""
    extension = manifest.extension
    if extension is None or "traffic.catalog" not in extension.capabilities:
        return False
    try:
        setting = extension.setting("traffic_enabled")
    except KeyError:
        return False
    return setting.setting_type == "boolean" and setting.default is False


class ScrollableFrame(ttk.Frame):
    """Vertically scrollable surface for settings-heavy launcher pages."""

    def __init__(self, parent, background: str = "#f8fafc") -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0)
        self.canvas.configure(takefocus=True)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, padding=(14, 12, 20, 18))
        self._window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", lambda _event: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(
            self._window, width=event.width))
        self.canvas.bind("<Enter>", lambda _event: self.canvas.bind_all(
            "<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda _event: self.canvas.unbind_all("<MouseWheel>"))
        self.canvas.bind("<Prior>", lambda _event: self.canvas.yview_scroll(-1, "pages"))
        self.canvas.bind("<Next>", lambda _event: self.canvas.yview_scroll(1, "pages"))
        self.canvas.bind("<Home>", lambda _event: self.canvas.yview_moveto(0))
        self.canvas.bind("<End>", lambda _event: self.canvas.yview_moveto(1))

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class ManagerWindow:
    NAVIGATION = (
        ("setup", "Setup", "Ctrl+1"),
        ("gameplay", "Gameplay", "Ctrl+2"),
        ("content", "Content", "Ctrl+3"),
        ("input", "Input", "Ctrl+4"),
        ("mods", "Packages", "Ctrl+5"),
        ("characters", "Characters", "Ctrl+6"),
        ("sdk", "SDK Manager", "Ctrl+7"),
        ("activity", "Activity", "Ctrl+8"),
        ("help", "Help Center", "Ctrl+9"),
    )

    def __init__(self, root: tk.Tk, manager: ModManager) -> None:
        self.root = root
        self.manager = manager
        self.config = manager.load_config()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.launch_pending = False
        self.profiles = ProfileStore(manager.project_root / "profiles")
        self.mod_catalog = default_mod_catalog(manager.project_root)
        self._mod_catalog_fingerprint = self.mod_catalog.fingerprint()
        self.mod_manifests: dict[str, ModManifest] = {}
        self.package_handoff_intents: dict[str, bool] = {}
        self.builtin_package_manifests: dict[str, ExtensionManifest] = {}
        self.builtin_package_entries: dict[str, dict[str, object]] = {}
        self.content_manifests: dict[str, ExtensionManifest] = {}
        self.content_registry_entries: dict[str, dict[str, object]] = {}
        self.content_setting_vars: dict[tuple[str, str], tk.Variable] = {}
        self.content_selected_system: tuple[str, str | None] | None = None
        self.sdk_catalog = AddonSdkCatalog(manager.project_root)
        self.sdk_manifests: dict[str, AddonManifest] = {}
        self.sdk_install_root = default_sdk_root()
        self.sdk_manager_dialog: SdkManagerDialog | None = None
        self.character_workspace: CharacterCustomizationDialog | None = None
        self.character_workspace_path: Path | None = None
        self.help_workspace: HelpCenterDialog | None = None
        self.installed_mod_ids: set[str] = set()
        self.mod_action_buttons: list[tk.Widget] = []
        self.current_status: InstallationStatus | None = None
        self.settings_dirty = False
        self.sidebar_visible = tk.BooleanVar(self.root, value=True)

        root.title("ALLIN1 Launcher")
        root.geometry("1240x840")
        root.minsize(980, 700)
        self._window_icon: tk.PhotoImage | None = None
        self._banner_logo: ImageTk.PhotoImage | None = None
        self._native_icon_handles: tuple[int, int] | None = None
        self._apply_window_branding()

        self.path = tk.StringVar(value=self.config.general.gta_path)
        self.legacy_path = tk.StringVar(value=self.config.general.gta_legacy_path)
        self.enhanced_path = tk.StringVar(value=self.config.general.gta_enhanced_path)
        self.target_edition = tk.StringVar(value=self.config.general.target_edition.title())
        self.rpf_previews = tk.BooleanVar(value=self.config.general.enable_rpf_previews)
        self.backup_enabled = tk.BooleanVar(value=self.config.general.backup)
        self.traffic = tk.BooleanVar(value=self.config.traffic.enabled)
        self.rich_areas_only = tk.BooleanVar(value=self.config.traffic.rich_areas_only_supers)
        self.adaptive_performance = tk.BooleanVar(value=self.config.traffic.adaptive_performance)
        self.enable_all_vehicles = tk.BooleanVar(value=self.config.vehicles.enable_all)
        self.disabled_classes = tk.StringVar(value=", ".join(self.config.vehicles.disabled_classes))
        self.disabled_vehicles = tk.StringVar(value=", ".join(self.config.vehicles.disabled_vehicles))
        self.police = tk.BooleanVar(value=self.config.script.enable_dlc_police)
        self.logging_enabled = tk.BooleanVar(value=self.config.script.enable_logging)
        self.gbay_key = tk.StringVar(value=self.config.script.gbay_key)
        self.night_vision_key = tk.StringVar(value=self.config.script.night_vision_key)
        self.world_vector_key = tk.StringVar(value=self.config.script.world_vector_key)
        self.seat_selector_enabled = tk.BooleanVar(value=self.config.script.seat_selector_enabled)
        self.seat_selector_key = tk.StringVar(value=self.config.script.seat_selector_key)
        self.safe_mode = tk.BooleanVar(value=self.config.script.safe_mode)
        self.reduced_motion = tk.BooleanVar(value=self.config.script.reduced_motion)
        self.colorblind_mode = tk.BooleanVar(value=self.config.script.colorblind_mode)
        self.ui_scale = tk.DoubleVar(value=self.config.script.ui_scale)
        self.hold_duration_ms = tk.IntVar(value=self.config.script.hold_duration_ms)
        self.gbay_free_mode = tk.BooleanVar(value=self.config.script.gbay_free_mode)
        self.garages_always_accessible = tk.BooleanVar(
            value=self.config.script.garages_always_accessible)
        self.enhanced_police_ai = tk.BooleanVar(
            value=self.config.script.enhanced_police_ai)
        self.gta_iv_npc_physics = tk.BooleanVar(
            value=self.config.script.gta_iv_npc_physics)
        self.gta_iv_npc_physics_debug = tk.BooleanVar(
            value=self.config.script.gta_iv_npc_physics_debug)
        self.axle_test_harness = tk.BooleanVar(
            value=self.config.script.axle_test_harness)
        self.enhanced_smoke_effects = tk.BooleanVar(
            value=self.config.script.enhanced_smoke_effects)
        self.controller_enabled = tk.BooleanVar(value=self.config.script.controller_enabled)
        for name in (
            "controller_open_gbay", "controller_open_gbay_modifier",
            "controller_night_vision", "controller_night_vision_modifier",
            "controller_seat_selector", "controller_seat_selector_modifier",
            "controller_accept", "controller_back", "controller_up", "controller_down",
            "controller_left", "controller_right", "controller_page_left",
            "controller_page_right", "controller_category_prev",
            "controller_category_next", "controller_filter", "controller_search",
            "controller_favorite",
        ):
            setattr(self, name, tk.StringVar(value=getattr(self.config.script, name)))
        self.status_text = tk.StringVar(value="Checking installation…")
        self.status_headline = tk.StringVar(value="Checking installation…")
        self.status_detail = tk.StringVar(value="Inspecting the selected GTA V folder.")
        self.version_text = tk.StringVar(
            value=f"Launcher {__version__} · updates not checked",
        )
        self.notice_text = tk.StringVar(value="Ready")
        self.operation_text = tk.StringVar(value="")
        self.profile_name = tk.StringVar(value="Full ALLIN1")

        self._build()
        self._setting_variables = (
            self.path, self.legacy_path, self.enhanced_path, self.target_edition,
            self.rpf_previews, self.backup_enabled, self.traffic,
            self.rich_areas_only, self.adaptive_performance, self.enable_all_vehicles,
            self.disabled_classes, self.disabled_vehicles, self.police,
            self.logging_enabled, self.gbay_key, self.night_vision_key,
            self.world_vector_key, self.seat_selector_enabled, self.seat_selector_key,
            self.safe_mode, self.reduced_motion, self.colorblind_mode, self.ui_scale,
            self.hold_duration_ms, self.gbay_free_mode,
            self.garages_always_accessible,
            self.enhanced_police_ai,
            self.gta_iv_npc_physics,
            self.gta_iv_npc_physics_debug,
            self.axle_test_harness,
            self.enhanced_smoke_effects,
            self.controller_enabled,
            self.controller_open_gbay, self.controller_open_gbay_modifier,
            self.controller_night_vision, self.controller_night_vision_modifier,
            self.controller_seat_selector, self.controller_seat_selector_modifier,
            self.controller_accept, self.controller_back, self.controller_up,
            self.controller_down, self.controller_left, self.controller_right,
            self.controller_page_left, self.controller_page_right,
            self.controller_category_prev, self.controller_category_next,
            self.controller_filter, self.controller_search, self.controller_favorite,
        )
        for variable in self._setting_variables:
            variable.trace_add("write", self._mark_dirty)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-s>", lambda _event: self.save())
        self.root.bind("<F5>", lambda _event: self.refresh())
        self.root.bind("<Control-l>", lambda _event: self.launch_game())
        self.root.bind("<F1>", lambda _event: self.open_help_center())
        handler = QueueLogHandler(self.messages)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger("allin1").addHandler(handler)
        self.root.after(100, self._drain_messages)
        self.root.after(
            LAUNCHER_HANDOFF_POLL_INTERVAL_MS, self._poll_launcher_handoffs,
        )
        self.root.after(
            PACKAGE_LIBRARY_WATCH_INTERVAL_MS, self._watch_package_library,
        )
        self.refresh()

    def _apply_window_branding(self) -> None:
        """Apply the ALLIN1 logo to the title bar and Windows taskbar."""
        try:
            icon_path = ASSET_DIR / "ALLIN1.ico"
            self._window_icon = tk.PhotoImage(file=str(ASSET_DIR / "ALLIN1-icon.png"))
            self.root.iconphoto(True, self._window_icon)
            if os.name == "nt":
                import ctypes
                self.root.iconbitmap(str(icon_path))
                self.root.iconbitmap(default=str(icon_path))
                self.root.update_idletasks()

                # Tk's iconbitmap can be ignored by Windows taskbar grouping.
                # Load native-size frames for the current monitor DPI and set
                # every Windows icon slot on both Tk's client and wrapper HWND.
                user32 = ctypes.windll.user32
                from ctypes import wintypes

                user32.GetParent.argtypes = (wintypes.HWND,)
                user32.GetParent.restype = wintypes.HWND
                user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
                user32.GetDpiForWindow.restype = wintypes.UINT
                user32.GetSystemMetricsForDpi.argtypes = (ctypes.c_int, wintypes.UINT)
                user32.GetSystemMetricsForDpi.restype = ctypes.c_int
                user32.LoadImageW.argtypes = (
                    wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                    ctypes.c_int, ctypes.c_int, wintypes.UINT,
                )
                user32.LoadImageW.restype = wintypes.HANDLE
                user32.SendMessageW.argtypes = (
                    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                )
                user32.SendMessageW.restype = wintypes.LPARAM

                client = int(self.root.winfo_id())
                wrapper = int(user32.GetParent(client) or 0)
                targets = tuple(dict.fromkeys(
                    handle for handle in (wrapper, client) if handle
                ))
                if targets:
                    dpi = int(user32.GetDpiForWindow(targets[0]) or 96)
                    small_width = max(16, int(user32.GetSystemMetricsForDpi(49, dpi)))
                    small_height = max(16, int(user32.GetSystemMetricsForDpi(50, dpi)))
                    large_width = max(32, int(user32.GetSystemMetricsForDpi(11, dpi)))
                    large_height = max(32, int(user32.GetSystemMetricsForDpi(12, dpi)))
                    load_from_file = 0x0010
                    small = int(user32.LoadImageW(
                        None, str(icon_path), 1,
                        small_width, small_height, load_from_file,
                    ) or 0)
                    large = int(user32.LoadImageW(
                        None, str(icon_path), 1,
                        large_width, large_height, load_from_file,
                    ) or 0)
                    if small or large:
                        self._native_icon_handles = (small or large, large or small)
                        icon_small, icon_big = self._native_icon_handles
                        for target in targets:
                            user32.SendMessageW(target, 0x0080, 0, icon_small)
                            user32.SendMessageW(target, 0x0080, 1, icon_big)
                            user32.SendMessageW(target, 0x0080, 2, icon_small)
        except (AttributeError, OSError, TypeError, ValueError, tk.TclError):
            # Branding is optional; never prevent the repair tool from opening.
            self._window_icon = None

    def _build_application_menu(self) -> None:
        """Build the stable application command hierarchy."""
        menu = tk.Menu(self.root, tearoff=False)

        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Save changes", accelerator="Ctrl+S", command=self.save)
        file_menu.add_command(label="Refresh status", accelerator="F5", command=self.refresh)
        file_menu.add_separator()
        file_menu.add_command(label="Apply selected profile", command=self.load_profile)
        file_menu.add_command(label="Save profile as…", command=self.save_profile)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        self.file_menu = file_menu
        menu.add_cascade(label="File", menu=file_menu)

        self.game_menu = tk.Menu(menu, tearoff=False)
        self.game_menu.add_command(
            label="Launch GTA V", accelerator="Ctrl+L", command=self.launch_game,
        )
        self.game_menu.add_command(label="Install / Repair…", command=self.install)
        self.game_menu.add_command(label="Health Check…", command=self.run_health_check)
        self.game_menu.add_separator()
        self.game_menu.add_command(
            label="Characters & garages", command=self.customize_characters,
        )
        self.game_menu.add_command(label="Create diagnostics…", command=self.create_diagnostics)
        self.game_menu.add_separator()
        self.game_menu.add_command(label="Uninstall ALLIN1…", command=self.uninstall)
        menu.add_cascade(label="Game", menu=self.game_menu)

        sdk_menu = tk.Menu(menu, tearoff=False)
        sdk_menu.add_command(label="Open ALLIN1 SDK…", command=self.open_addon_sdk)
        sdk_menu.add_command(label="Install / Manage SDK", command=self.manage_addon_sdk)
        sdk_menu.add_separator()
        sdk_menu.add_command(
            label="SDK Help", command=lambda: self.open_help_center("sdk"),
        )
        self.sdk_menu = sdk_menu
        menu.add_cascade(label="SDK", menu=sdk_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        for key, label, shortcut in self.NAVIGATION:
            view_menu.add_command(
                label=label, accelerator=shortcut,
                command=lambda selected=key: self._select_workspace(selected),
            )
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="Show workspace sidebar", accelerator="Ctrl+B",
            variable=self.sidebar_visible, onvalue=True, offvalue=False,
            command=lambda: self._set_sidebar_visible(
                self.sidebar_visible.get(),
            ),
        )
        self.sidebar_visible.set(True)
        menu.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(
            label="Help Center", accelerator="F1", command=self.open_help_center,
        )
        help_menu.add_separator()
        help_menu.add_command(label="About ALLIN1", command=self.show_about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menu)

    def _select_workspace(self, key: str) -> None:
        """Show one task-oriented workspace and keep navigation state obvious."""
        pages = getattr(self, "workspace_pages", {})
        if key not in pages:
            return
        if key == "characters":
            self._ensure_character_workspace()
        elif key == "sdk":
            self._ensure_sdk_workspace()
        elif key == "mods" and hasattr(self, "mod_tree"):
            self._refresh_mods_if_changed()
        pages[key].tkraise()
        self.current_workspace = key
        for name, button in self.workspace_buttons.items():
            button.configure(
                style="NavSelected.TButton" if name == key else "Nav.TButton",
            )

    def _refresh_mods_if_changed(self) -> bool:
        """Refresh package rows only when the bounded catalog snapshot changed."""
        fingerprint = self.mod_catalog.fingerprint()
        if fingerprint == self._mod_catalog_fingerprint:
            return False
        self.refresh_mods()
        return True

    def _watch_package_library(self) -> None:
        """Watch lazily while Packages is visible; never hash package payloads."""
        if getattr(self, "current_workspace", None) == "mods":
            self._refresh_mods_if_changed()
        self.root.after(
            PACKAGE_LIBRARY_WATCH_INTERVAL_MS, self._watch_package_library,
        )

    def _show_launcher_handoff(self, handoff: LauncherHandoff) -> None:
        """Reveal a discovered package without granting any mutation authority."""
        self._select_workspace("mods")
        # A request may arrive just after an atomic Quick Import publish. Refresh
        # once before resolving the ID; payload hashing remains deferred.
        self._refresh_mods_if_changed()
        package_id = handoff.package_id
        if package_id is not None:
            if package_id in self.mod_manifests and self.mod_tree.exists(package_id):
                if handoff.traffic is not None:
                    self.package_handoff_intents[package_id] = handoff.traffic
                self.mod_tree.selection_set(package_id)
                self.mod_tree.focus(package_id)
                self.mod_tree.see(package_id)
                self._show_mod_details()
                traffic_note = ""
                if handoff.traffic is True:
                    traffic_note = (
                        " · traffic requested"
                        if _supports_package_traffic_intent(
                            self.mod_manifests[package_id]
                        )
                        else " · traffic is not supported by this package"
                    )
                elif handoff.traffic is False:
                    traffic_note = " · traffic will remain off"
                self.notice_text.set(
                    "Package ready to review · choose Install / update to continue"
                    + traffic_note,
                )
            else:
                self.mod_details.set(
                    f"Package '{package_id}' is not in the shared package library. "
                    "Prepare it in Quick Import, then try again.",
                )
                self.notice_text.set("Requested package was not found")
        self.root.deiconify()
        self.root.lift()
        self.root.after_idle(self.root.focus_force)

    def _poll_launcher_handoffs(self) -> None:
        for handoff in consume_launcher_handoffs():
            self._show_launcher_handoff(handoff)
        self.root.after(
            LAUNCHER_HANDOFF_POLL_INTERVAL_MS, self._poll_launcher_handoffs,
        )

    def _set_sidebar_visible(self, visible: bool) -> str:
        """Fold the workspace list away without changing the current page."""
        self.sidebar_visible.set(bool(visible))
        if visible:
            if not self.workspace_sidebar.winfo_manager():
                self.workspace_sidebar.pack(
                    side="left", fill="y", before=self.sidebar_toggle_rail,
                )
            self.sidebar_toggle_button.configure(
                text="<", command=lambda: self._set_sidebar_visible(False),
            )
        else:
            self.workspace_sidebar.pack_forget()
            self.sidebar_toggle_button.configure(
                text=">", command=lambda: self._set_sidebar_visible(True),
            )
        return "break"

    def _toggle_sidebar(self, _event: object | None = None) -> str:
        return self._set_sidebar_visible(not self.sidebar_visible.get())

    def _cycle_workspace(
        self, _event: object | None = None, direction: int = 1,
    ) -> str:
        keys = [key for key, _label, _shortcut in self.NAVIGATION]
        current = getattr(self, "current_workspace", keys[0])
        index = keys.index(current) if current in keys else 0
        self._select_workspace(keys[(index + direction) % len(keys)])
        return "break"

    def _build(self) -> None:
        green, dark_green, body_bg = "#2d9c50", "#1f7f42", "#f4f7f5"
        self.root.configure(background=body_bg)
        self.root.option_add("*tearOff", False)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), foreground="#173d32")
        style.configure("TFrame", background=body_bg)
        style.configure("TLabel", background=body_bg, foreground="#24332d")
        style.configure("TButton", padding=(11, 7))
        style.configure("TEntry", padding=(7, 6))
        style.configure("TCombobox", padding=(6, 5))
        style.configure("TCheckbutton", padding=(0, 2))
        style.configure("Surface.TFrame", background="#ffffff")
        style.configure(
            "Card.TFrame", background="#ffffff", borderwidth=1,
            relief="solid",
        )
        style.configure("TLabelframe", background="#ffffff", bordercolor="#d4ddd9")
        style.configure("TLabelframe.Label", background=body_bg, foreground=dark_green,
                        font=("Segoe UI Semibold", 10))
        style.configure("PageTitle.TLabel", font=("Segoe UI Semibold", 17),
                        foreground="#173d32")
        style.configure("PageIntro.TLabel", foreground="#52635c")
        style.configure("Section.TLabel", font=("Segoe UI Semibold", 11),
                        foreground="#173d32")
        style.configure("FieldLabel.TLabel", font=("Segoe UI Semibold", 9),
                        foreground="#52635c")
        style.configure("Accent.TButton", background=green, foreground="white",
                        font=("Segoe UI Semibold", 10), padding=(13, 8))
        style.map("Accent.TButton", background=[("active", dark_green),
                                                ("disabled", "#c8d4cc")],
                  foreground=[("disabled", "#66756e")])
        style.configure("Quiet.TButton", padding=(10, 7))
        style.configure(
            "Danger.TButton", background="#fff0ed", foreground="#a43a2b",
            padding=(10, 7), font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Danger.TButton",
            background=[("active", "#ffe2dc"), ("disabled", "#f1f1f1")],
            foreground=[("disabled", "#8b9691")],
        )
        style.configure("Nav.TButton", anchor="w", padding=(16, 11), relief="flat",
                        background="#eef3f0", foreground="#3c5048")
        style.map(
            "Nav.TButton",
            background=[("active", "#e2ebe6"), ("focus", "#e2ebe6")],
            foreground=[("disabled", "#84928c")],
        )
        style.configure("NavSelected.TButton", anchor="w", padding=(16, 11),
                        relief="flat", background="#dcefe3", foreground="#176b36",
                        font=("Segoe UI Semibold", 10))
        style.map(
            "NavSelected.TButton",
            background=[("active", "#d2e8da"), ("focus", "#c9e4d3")],
        )
        style.configure("Success.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#18753a")
        style.configure("Warning.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#9a6700")
        style.configure("Error.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#b42318")
        style.configure("Muted.TLabel", foreground="#52635c")
        style.configure(
            "Link.TButton", relief="flat", borderwidth=0, padding=(4, 3),
            background=body_bg, foreground="#176b36",
            font=("Segoe UI Semibold", 9, "underline"),
        )
        style.map(
            "Link.TButton",
            foreground=[("active", "#0e5228"), ("focus", "#0e5228")],
            background=[("active", "#e2ebe6"), ("focus", "#e2ebe6")],
        )
        style.configure(
            "WarningPanel.TFrame", background="#fff8e8",
            borderwidth=1, relief="solid",
        )
        style.configure(
            "WarningPanel.TLabel", background="#fff8e8", foreground="#714b00",
        )
        style.configure("TNotebook", background=body_bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(10, 6),
                        foreground="#646e69")
        style.map("TNotebook.Tab", background=[("selected", "#ffffff"),
                                                ("active", "#e6efe9")],
                  foreground=[("selected", green)])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10),
                        background="#ffffff", fieldbackground="#ffffff")
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10),
                        padding=(6, 6), foreground="#26332e")
        style.map(
            "Treeview", background=[("selected", "#176b36")],
            foreground=[("selected", "#ffffff")],
        )
        self._build_application_menu()

        outer = ttk.Frame(self.root, padding=(12, 9, 12, 10))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        try:
            with Image.open(ASSET_DIR / "ALLIN1.png") as source:
                logo = source.convert("RGBA")
                logo.thumbnail((180, 88), Image.Resampling.LANCZOS)
            self._banner_logo = ImageTk.PhotoImage(logo)
            ttk.Label(header, image=self._banner_logo).pack(
                side="left", padx=(0, 14), anchor="center",
            )
        except (OSError, tk.TclError):
            self._banner_logo = None

        header_actions = ttk.Frame(header)
        header_actions.pack(side="right", padx=(18, 4), fill="y")
        self.version_badge = tk.Label(
            header_actions, text=f"v{__version__}",
            background="#176b36", foreground="white",
            font=("Segoe UI Semibold", 10), padx=12, pady=5,
        )
        self.version_badge.pack(anchor="e")
        self.support_button = ttk.Button(
            header_actions, text="Support ALLIN1 ↗", style="Link.TButton",
            cursor="hand2", command=lambda: webbrowser.open(
                "https://buymeacoffee.com/minionenjoyer"
            ),
        )
        self.support_button.pack(anchor="e", pady=(10, 0))

        header_text = ttk.Frame(header)
        header_text.pack(side="left", fill="x", expand=True, anchor="center")
        ttk.Label(
            header_text, text="ALLIN1 · GTA V Launcher",
            font=("Segoe UI Semibold", 18), foreground="#173d32",
        ).pack(anchor="w")
        ttk.Label(
            header_text,
            text=(
                "Set up Story Mode, manage content, configure controls, and "
                "launch the game from one place."
            ),
            wraplength=760, justify="left",
        ).pack(anchor="w", pady=(3, 0))

        shell = ttk.Frame(outer)
        shell.grid(row=1, column=0, sticky="nsew")
        self.navigation_shell = ttk.Frame(shell)
        self.navigation_shell.pack(side="left", fill="y")
        sidebar = ttk.Frame(
            self.navigation_shell, style="Surface.TFrame", padding=(8, 12),
        )
        self.workspace_sidebar = sidebar
        sidebar.pack(side="left", fill="y")
        self.sidebar_toggle_rail = tk.Frame(
            self.navigation_shell, width=16, background="#d5ded9",
            highlightthickness=0, borderwidth=0,
        )
        self.sidebar_toggle_rail.pack(side="left", fill="y", padx=(0, 12))
        self.sidebar_toggle_rail.pack_propagate(False)
        tk.Frame(
            self.sidebar_toggle_rail, width=1, background="#aebdb5",
            highlightthickness=0, borderwidth=0,
        ).place(relx=0.5, y=0, relheight=1, anchor="n")
        self.sidebar_toggle_button = tk.Button(
            self.sidebar_toggle_rail, text="<",
            background=dark_green, foreground="#ffffff",
            activebackground="#176b36", activeforeground="#ffffff",
            relief="flat", borderwidth=0, highlightthickness=0,
            padx=0, pady=0, font=("Segoe UI Semibold", 9), cursor="hand2",
            command=lambda: self._set_sidebar_visible(False),
        )
        self.sidebar_toggle_button.place(
            relx=0.5, rely=0.5, anchor="center", width=16, height=30,
        )
        ttk.Label(
            sidebar, text="PLAYER WORKSPACES", style="FieldLabel.TLabel",
            background="#ffffff",
        ).pack(anchor="w", padx=10, pady=(0, 7))
        workspace = ttk.Frame(shell)
        workspace.pack(side="left", fill="both", expand=True)
        workspace.rowconfigure(0, weight=1)
        workspace.columnconfigure(0, weight=1)
        workspace.grid_propagate(False)

        home_view = ScrollableFrame(workspace, body_bg)
        gameplay_view = ScrollableFrame(workspace, body_bg)
        content_view = ScrollableFrame(workspace, body_bg)
        controls_view = ScrollableFrame(workspace, body_bg)
        mods_view = ScrollableFrame(workspace, body_bg)
        characters = ttk.Frame(workspace)
        sdk = ttk.Frame(workspace)
        activity = ttk.Frame(workspace, padding=14)
        help_page = ttk.Frame(workspace)
        self.workspace_pages = {
            "setup": home_view,
            "gameplay": gameplay_view,
            "content": content_view,
            "input": controls_view,
            "mods": mods_view,
            "characters": characters,
            "sdk": sdk,
            "activity": activity,
            "help": help_page,
        }
        self.characters_page = characters
        self.sdk_page = sdk
        self.help_page = help_page
        self.workspace_buttons: dict[str, ttk.Button] = {}
        for key, label, shortcut in self.NAVIGATION:
            page = self.workspace_pages[key]
            page.grid(row=0, column=0, sticky="nsew")
            button = ttk.Button(
                sidebar, text=label, style="Nav.TButton",
                command=lambda selected=key: self._select_workspace(selected),
                width=18,
            )
            button.pack(fill="x", pady=1)
            self.workspace_buttons[key] = button
            key_name = shortcut.removeprefix("Ctrl+").casefold()
            self.root.bind(
                f"<Control-Key-{key_name}>",
                lambda _event, selected=key: (
                    self._select_workspace(selected), "break"
                )[1],
            )
        self.root.bind("<Control-b>", self._toggle_sidebar)
        self.root.bind("<Control-Tab>", self._cycle_workspace)
        self.root.bind(
            "<Control-Shift-Tab>",
            lambda event: self._cycle_workspace(event, -1),
        )
        self.current_workspace = "setup"
        self.help_workspace = HelpCenterDialog(
            help_page, initial_topic="getting-started", embedded=True,
        )
        self._select_workspace("setup")
        home = home_view.content
        gameplay = gameplay_view.content
        content_page = content_view.content
        controls_page = controls_view.content
        mods_page = mods_view.content

        self._page_intro(
            home, "Game setup",
            "Choose your game folder, check the installation, and get ready to play.",
        )
        self._page_intro(
            gameplay, "Gameplay systems",
            "Choose launcher-wide recovery, preview, and logging options.",
        )
        self._page_intro(
            content_page, "Content",
            "See what each installed content pack adds and change its settings.",
        )
        self._page_intro(
            controls_page, "Controls",
            "Set keyboard shortcuts, controller buttons, and vehicle filters.",
        )
        self._page_intro(
            mods_page, "Packages",
            "Add, update, enable, or remove optional Story Mode packages.",
        )
        self._page_intro(
            activity, "Activity",
            "Review launcher work and copy useful details when something goes wrong.",
        )

        profiles = ttk.LabelFrame(home, text="Configuration profile", padding=12)
        profiles.pack(fill="x", pady=(0, 10))
        self.profile_box = ttk.Combobox(profiles, textvariable=self.profile_name,
                                        values=self.profiles.list(), width=34,
                                        state="readonly")
        self.profile_box.pack(side="left", fill="x", expand=True)
        ttk.Button(profiles, text="Apply profile", command=self.load_profile).pack(
            side="left", padx=(8, 0),
        )

        location = ttk.LabelFrame(home, text="GTA V installations", padding=12)
        location.pack(fill="x")
        location.columnconfigure(1, weight=1)
        for row, (label, variable, edition) in enumerate((
            ("Legacy folder", self.legacy_path, "legacy"),
            ("Enhanced folder", self.enhanced_path, "enhanced"),
        )):
            ttk.Label(location, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(location, textvariable=variable).grid(
                row=row, column=1, sticky="ew", padx=(10, 8), pady=3,
            )
            ttk.Button(
                location, text="Browse…",
                command=lambda value=edition: self._browse(value),
            ).grid(row=row, column=2, sticky="e", pady=3)
        ttk.Label(location, text="Active target").grid(
            row=2, column=0, sticky="w", pady=(8, 3),
        )
        ttk.Combobox(
            location, textvariable=self.target_edition,
            values=("Auto", "Legacy", "Enhanced"), state="readonly", width=16,
        ).grid(row=2, column=1, sticky="w", padx=(10, 8), pady=(8, 3))
        ttk.Label(
            location,
            text="Install, launch, health, and package actions use this edition.",
            foreground="#3f6659",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 0))

        world = ttk.LabelFrame(gameplay, text="Launcher host & recovery", padding=14)
        world.pack(fill="x", pady=(0, 12))
        world.columnconfigure(0, weight=1)
        world.columnconfigure(1, weight=1)
        for row, (left_text, left_var, right_text, right_var) in enumerate((
            ("Back up managed game changes", self.backup_enabled,
             "Safe mode for recovery", self.safe_mode),
            ("Enable archive-backed content previews", self.rpf_previews,
             "Detailed host and runtime logging", self.logging_enabled),
        )):
            ttk.Checkbutton(world, text=left_text, variable=left_var).grid(
                row=row, column=0, sticky="w", padx=(0, 28), pady=4,
            )
            ttk.Checkbutton(world, text=right_text, variable=right_var).grid(
                row=row, column=1, sticky="w", pady=4,
            )

        ttk.Label(
            gameplay,
            text=("Gameplay supplied by content packs is configured in Content. "
                  "This page contains only shared launcher behavior."),
            foreground="#52635c", wraplength=900, justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 12))

        content_library = ttk.LabelFrame(
            content_page, text="Content packages & systems", padding=14,
        )
        content_library.pack(fill="both", expand=True, pady=(0, 12))
        ttk.Label(
            content_library,
            text=(
                "ALLIN1 Online Content is the main gameplay pack. Other installed "
                "packages can add settings and features here."
            ),
            wraplength=900, justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 10))
        content_split = ttk.Frame(content_library)
        content_split.pack(fill="both", expand=True)
        content_split.columnconfigure(0, weight=2)
        content_split.columnconfigure(1, weight=3)
        content_split.rowconfigure(0, weight=1)
        content_tree_frame = ttk.Frame(content_split)
        content_tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.content_tree = ttk.Treeview(
            content_tree_frame,
            columns=("category", "version", "status"),
            show="tree headings", height=15, selectmode="browse",
        )
        self.content_tree.heading("#0", text="Package / system")
        self.content_tree.heading("category", text="Category")
        self.content_tree.heading("version", text="Version")
        self.content_tree.heading("status", text="Status")
        self.content_tree.column("#0", width=280, minwidth=190)
        self.content_tree.column("category", width=105, anchor="center")
        self.content_tree.column("version", width=75, anchor="center")
        self.content_tree.column("status", width=95, anchor="center")
        content_scroll = ttk.Scrollbar(
            content_tree_frame, orient="vertical", command=self.content_tree.yview,
        )
        self.content_tree.configure(yscrollcommand=content_scroll.set)
        self.content_tree.pack(side="left", fill="both", expand=True)
        content_scroll.pack(side="right", fill="y")
        self.content_tree.bind("<<TreeviewSelect>>", self._show_content_details)

        content_detail = ttk.Frame(content_split, style="Surface.TFrame", padding=12)
        content_detail.grid(row=0, column=1, sticky="nsew")
        self.content_detail_title = tk.StringVar(value="Select a content system")
        self.content_detail_text = tk.StringVar(
            value="Installed systems and their package ownership appear here."
        )
        ttk.Label(
            content_detail, textvariable=self.content_detail_title,
            style="Section.TLabel", background="#ffffff",
        ).pack(fill="x", anchor="w")
        ttk.Label(
            content_detail, textvariable=self.content_detail_text,
            wraplength=520, justify="left", background="#ffffff",
        ).pack(fill="x", anchor="w", pady=(4, 10))
        self.content_settings_frame = ttk.Frame(
            content_detail, style="Surface.TFrame",
        )
        self.content_settings_frame.pack(fill="both", expand=True)
        content_actions = ttk.Frame(content_detail, style="Surface.TFrame")
        content_actions.pack(fill="x", pady=(12, 0))
        ttk.Button(
            content_actions, text="Apply settings",
            command=self.apply_content_settings, style="Accent.TButton",
        ).pack(side="left")
        content_state_menu = tk.Menu(content_actions, tearoff=False)
        content_state_menu.add_command(
            label="Enable selected package",
            command=lambda: self.toggle_selected_content(True),
        )
        content_state_menu.add_command(
            label="Disable selected package",
            command=lambda: self.toggle_selected_content(False),
        )
        ttk.Menubutton(
            content_actions, text="Package state", menu=content_state_menu,
        ).pack(side="left", padx=(8, 0))

        controls = ttk.LabelFrame(controls_page, text="Keyboard shortcuts & vehicle filters", padding=14)
        controls.pack(fill="x", pady=(0, 12))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)
        key_choices = tuple([f"F{i}" for i in range(1, 13)] +
                            [chr(i) for i in range(ord("A"), ord("Z") + 1)] +
                            [f"NumPad{i}" for i in range(10)])
        for row, (label, variable) in enumerate((
            ("Open GBAY", self.gbay_key),
            ("Night vision", self.night_vision_key),
            ("World-vector overlay", self.world_vector_key),
            ("Seat selector", self.seat_selector_key),
        )):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(controls, textvariable=variable, values=key_choices,
                         state="readonly", width=14).grid(row=row, column=1, sticky="w", padx=(12, 30), pady=3)
        ttk.Checkbutton(controls, text="Enable hold-to-select vehicle seats",
                        variable=self.seat_selector_enabled).grid(row=0, column=2, rowspan=2, sticky="w")
        ttk.Label(controls, text="Seat hold (ms)").grid(row=2, column=2, sticky="w")
        ttk.Spinbox(controls, from_=100, to=2000, increment=50,
                    textvariable=self.hold_duration_ms, width=7).grid(row=2, column=3, sticky="w")
        ttk.Label(controls, text="Disabled classes").grid(row=4, column=0, sticky="w", pady=(8, 3))
        ttk.Entry(controls, textvariable=self.disabled_classes, width=34).grid(
            row=4, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=(8, 3))
        ttk.Label(controls, text="Disabled vehicle models").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Entry(controls, textvariable=self.disabled_vehicles, width=34).grid(
            row=5, column=1, columnspan=3, sticky="ew", padx=(12, 0), pady=3)
        ttk.Label(controls, text="Comma-separated. Advanced traffic, garages, inventories, stats, money, and outfits are under Character customization.",
                  wraplength=760, foreground="#3f6659").grid(
                      row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))

        controller = ttk.LabelFrame(
            controls_page, text="Controller configuration", padding=14)
        controller.pack(fill="x", pady=(0, 12))
        controller.columnconfigure(1, weight=1)
        controller.columnconfigure(3, weight=1)
        ttk.Checkbutton(controller, text="Enable controller support",
                        variable=self.controller_enabled).grid(
                            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        controller_choices = (
            "FrontendAccept", "FrontendCancel", "FrontendUp", "FrontendDown",
            "FrontendLeft", "FrontendRight", "FrontendLb", "FrontendRb",
            "FrontendLt", "FrontendRt", "FrontendY", "FrontendX", "FrontendRdown",
        )
        controller_rows = (
            ("Open GBAY", self.controller_open_gbay,
             "Open modifier", self.controller_open_gbay_modifier),
            ("Night vision", self.controller_night_vision,
             "Night vision modifier", self.controller_night_vision_modifier),
            ("Seat selector", self.controller_seat_selector,
             "Seat modifier", self.controller_seat_selector_modifier),
            ("Accept", self.controller_accept, "Back", self.controller_back),
            ("Navigate up", self.controller_up, "Navigate down", self.controller_down),
            ("Navigate left", self.controller_left, "Navigate right", self.controller_right),
            ("Previous page", self.controller_page_left,
             "Next page", self.controller_page_right),
            ("Previous category", self.controller_category_prev,
             "Next category", self.controller_category_next),
            ("Filter", self.controller_filter, "Search", self.controller_search),
            ("Favorite", self.controller_favorite, "", None),
        )
        for row, (left_label, left_var, right_label, right_var) in enumerate(
                controller_rows, start=1):
            ttk.Label(controller, text=left_label).grid(
                row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(controller, textvariable=left_var,
                         values=controller_choices, state="readonly", width=18).grid(
                             row=row, column=1, sticky="w", padx=(10, 24), pady=3)
            if right_var is not None:
                ttk.Label(controller, text=right_label).grid(
                    row=row, column=2, sticky="w", pady=3)
                ttk.Combobox(controller, textvariable=right_var,
                             values=controller_choices, state="readonly", width=18).grid(
                                 row=row, column=3, sticky="w", padx=(10, 0), pady=3)
        ttk.Label(controller,
                  text="Shortcut actions use the configured modifier plus action. GBAY navigation bindings apply while its menus are open.",
                  wraplength=760, foreground="#3f6659").grid(
                      row=len(controller_rows) + 1, column=0, columnspan=4,
                      sticky="w", pady=(8, 0))

        mod_library = ttk.LabelFrame(mods_page, text="Package library", padding=14)
        mod_library.pack(fill="x", pady=(0, 12))
        ttk.Label(
            mod_library,
            text=(
                "Install validated Story Mode packages. ALLIN1 records what each "
                "package changes and backs up files it replaces."
            ),
            wraplength=790,
            justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 10))
        trust_panel = ttk.Frame(
            mod_library, style="WarningPanel.TFrame", padding=(10, 8),
        )
        trust_panel.pack(fill="x", pady=(0, 10))
        ttk.Label(
            trust_panel, text="Before you install", style="WarningPanel.TLabel",
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        ttk.Label(
            trust_panel,
            text=(
                "Only use packages you trust. Some packages also need ScriptHookV, "
                "ScriptHookVDotNet, or OpenRPF."
            ),
            style="WarningPanel.TLabel", wraplength=790, justify="left",
        ).pack(fill="x", anchor="w", pady=(2, 0))

        tree_frame = ttk.Frame(mod_library)
        tree_frame.pack(fill="both", expand=True)
        self.mod_tree = ttk.Treeview(
            tree_frame,
            columns=("type", "edition", "version", "status"),
            show="tree headings",
            height=7,
            selectmode="browse",
        )
        self.mod_tree.heading("#0", text="Mod")
        self.mod_tree.heading("type", text="Type")
        self.mod_tree.heading("edition", text="Edition")
        self.mod_tree.heading("version", text="Version")
        self.mod_tree.heading("status", text="Status")
        self.mod_tree.column("#0", width=440, minwidth=260, stretch=False)
        self.mod_tree.column("type", width=80, anchor="center", stretch=False)
        self.mod_tree.column("edition", width=125, anchor="center", stretch=False)
        self.mod_tree.column("version", width=80, anchor="center", stretch=False)
        self.mod_tree.column("status", width=120, anchor="center", stretch=False)
        mod_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=mod_scroll.set)
        self.mod_tree.pack(side="left", fill="both", expand=True)
        mod_scroll.pack(side="right", fill="y")
        self.mod_tree.bind("<<TreeviewSelect>>", self._show_mod_details)

        self.mod_details = tk.StringVar(value="Select a package to view its details.")
        ttk.Label(mod_library, textvariable=self.mod_details, wraplength=790,
                  justify="left").pack(fill="x", anchor="w", pady=(10, 0))

        package_toolbar = ttk.Frame(mods_page)
        package_toolbar.pack(fill="x", pady=(0, 10), before=mod_library)
        add_package_button = ttk.Button(
            package_toolbar, text="Add package…", command=self.import_mod_package,
            style="Accent.TButton",
        )
        add_package_button.pack(side="left")
        self.mod_action_buttons.append(add_package_button)
        library_menu = tk.Menu(package_toolbar, tearoff=False)
        library_menu.add_command(label="Refresh package library", command=self.refresh_mods)
        library_menu.add_separator()
        library_menu.add_command(label="Open ALLIN1 SDK…", command=self.open_addon_sdk)
        library_menu.add_command(label="Install / Manage SDK…", command=self.manage_addon_sdk)
        library_button = ttk.Menubutton(
            package_toolbar, text="Library options", menu=library_menu,
        )
        library_button.pack(side="left", padx=(8, 0))
        self.mod_action_buttons.append(library_button)

        package_menu = tk.Menu(
            package_toolbar, tearoff=False,
            postcommand=self._prepare_package_action_menu,
        )
        self.package_action_menu = package_menu
        package_menu.add_command(label="Install / update", command=self.install_selected_mod)
        package_menu.add_separator()
        package_menu.add_command(label="Enable", command=lambda: self.toggle_selected_mod(True))
        package_menu.add_command(label="Disable", command=lambda: self.toggle_selected_mod(False))
        package_menu.add_separator()
        package_menu.add_command(label="Uninstall…", command=self.uninstall_selected_mod)
        package_button = ttk.Menubutton(
            package_toolbar, text="Selected package", menu=package_menu,
        )
        package_button.pack(side="right")
        self.mod_action_buttons.append(package_button)
        ttk.Label(
            package_toolbar, text="Choose a package below to manage it.",
            style="Muted.TLabel",
        ).pack(side="right", padx=(12, 8))

        ttk.Label(
            mods_page,
            text=(
                "Want to build or inspect a package? Open the ALLIN1 SDK from "
                "Library options."
            ),
            style="Muted.TLabel",
            wraplength=790,
            justify="left",
        ).pack(fill="x", anchor="w")

        state_shell = ttk.Frame(home, style="Card.TFrame")
        state_shell.pack(fill="x", before=profiles, pady=(0, 10))
        self.status_accent = tk.Frame(
            state_shell, width=5, background="#d09a22",
            highlightthickness=0, borderwidth=0,
        )
        self.status_accent.pack(side="left", fill="y")
        self.status_accent.pack_propagate(False)
        state = ttk.Frame(state_shell, style="Surface.TFrame", padding=14)
        state.pack(side="left", fill="both", expand=True)
        ttk.Label(
            state, text="INSTALLATION STATUS", style="FieldLabel.TLabel",
            background="#ffffff",
        ).pack(anchor="w", pady=(0, 4))
        self.status_headline_label = ttk.Label(
            state,
            textvariable=self.status_headline,
            style="Warning.Status.TLabel",
            background="#ffffff",
        )
        self.status_headline_label.pack(anchor="w")
        ttk.Label(
            state,
            textvariable=self.status_detail,
            justify="left",
            wraplength=830,
            background="#ffffff",
        ).pack(anchor="w", pady=(3, 10))
        ttk.Separator(state).pack(fill="x", pady=(0, 9))
        ttk.Label(
            state, textvariable=self.status_text, justify="left",
            wraplength=830, background="#ffffff",
        ).pack(anchor="w")
        ttk.Label(state, textvariable=self.version_text, justify="left",
                  background="#ffffff", style="Muted.TLabel").pack(
                      anchor="w", pady=(5, 0),
                  )
        status_actions = ttk.Frame(state, style="Surface.TFrame")
        status_actions.pack(fill="x", pady=(10, 0))
        self.install_repair_button = ttk.Button(
            status_actions, text="Install / Repair", command=self.install,
            style="Accent.TButton",
        )
        self.install_repair_button.pack(side="left")
        self.update_button = ttk.Button(
            status_actions, text="Check for updates", command=self.check_for_updates,
        )
        self.update_button.pack(side="left", padx=(8, 0))

        activity_toolbar = ttk.Frame(activity)
        activity_toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(
            activity_toolbar,
            text="Launcher operations and diagnostics appear here.",
            foreground="#3f6659",
        ).pack(side="left")
        activity_menu = tk.Menu(activity_toolbar, tearoff=False)
        activity_menu.add_command(label="Copy activity", command=self.copy_activity)
        activity_menu.add_command(label="Clear activity", command=self.clear_activity)
        activity_menu.add_separator()
        activity_menu.add_command(label="Open log folder", command=self.open_log_folder)
        ttk.Menubutton(
            activity_toolbar, text="Activity actions", menu=activity_menu,
        ).pack(side="right")
        log_frame = ttk.LabelFrame(activity, text="Launcher log", padding=10)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_frame, height=12, wrap="word", state="disabled",
            background="#ffffff", foreground="#1e2925", relief="flat",
            font=("Cascadia Mono", 9), padx=9, pady=9,
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(
            outer, style="Surface.TFrame", padding=(10, 8),
        )
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        footer_actions = ttk.Frame(footer, style="Surface.TFrame")
        footer_actions.pack(side="right")
        footer_left = ttk.Frame(footer, style="Surface.TFrame")
        footer_left.pack(side="left", fill="x", expand=True)
        ttk.Label(
            footer_left,
            text="STORY MODE ONLY",
            background="#ffffff",
            foreground="#9a3412",
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")
        ttk.Label(
            footer_left, text="  ·  ", background="#ffffff",
        ).pack(side="left")
        ttk.Label(footer_left, textvariable=self.notice_text,
                  background="#ffffff", foreground="#3f6659").pack(side="left")
        self.busy_progress = ttk.Progressbar(
            footer_left, mode="determinate", maximum=100, length=170,
        )
        ttk.Label(footer_left, textvariable=self.operation_text,
                  background="#ffffff", foreground="#3f6659").pack(side="left")

        game_action_menu = tk.Menu(footer_actions, tearoff=False)
        game_action_menu.add_command(label="Install / Repair…", command=self.install)
        game_action_menu.add_command(label="Health Check…", command=self.run_health_check)
        game_action_menu.add_command(label="Create diagnostics…", command=self.create_diagnostics)
        game_action_menu.add_separator()
        game_action_menu.add_command(label="Refresh status", command=self.refresh)
        self.game_action_button = ttk.Menubutton(
            footer_actions, text="Game actions", menu=game_action_menu,
        )
        self.game_action_button.pack(side="left")
        self.save_button = ttk.Button(footer_actions, text="Save changes", command=self.save,
                                      style="Quiet.TButton")
        self.save_button.pack(side="left", padx=7)
        self.launch_button = ttk.Button(footer_actions, text="Launch GTA V",
                                        command=self.launch_game, style="Accent.TButton")
        self.launch_button.pack(side="left")

    @staticmethod
    def _page_intro(parent: tk.Misc, title: str, description: str) -> None:
        heading = ttk.Frame(parent)
        heading.pack(fill="x", pady=(0, 14))
        ttk.Label(heading, text=title, style="PageTitle.TLabel").pack(anchor="w")
        ttk.Label(
            heading, text=description, style="PageIntro.TLabel",
            wraplength=900, justify="left",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Separator(heading).pack(fill="x", pady=(11, 0))

    def _browse(self, edition: str | None = None) -> None:
        label = f"GTA V {edition.title()}" if edition else "GTA V"
        selected = filedialog.askdirectory(title=f"Select the {label} installation folder")
        if selected:
            if edition == "legacy":
                self.legacy_path.set(selected)
            elif edition == "enhanced":
                self.enhanced_path.set(selected)
            else:
                self.path.set(selected)
            self.refresh()

    def _current_config(self) -> Config:
        if hasattr(self, "legacy_path"):
            self.config.general.gta_legacy_path = self.legacy_path.get().strip() or "auto"
            self.config.general.gta_enhanced_path = self.enhanced_path.get().strip() or "auto"
            target = self.target_edition.get().strip().lower() or "auto"
            self.config.general.target_edition = target
            selected_path = (
                self.config.general.gta_legacy_path if target == "legacy"
                else self.config.general.gta_enhanced_path if target == "enhanced"
                else self.path.get().strip() or "auto"
            )
            self.config.general.gta_path = selected_path
        else:
            self.config.general.gta_path = self.path.get().strip() or "auto"
        self.config.general.free_mode = self.gbay_free_mode.get()
        self.config.general.backup = self.backup_enabled.get()
        self.config.general.enable_rpf_previews = self.rpf_previews.get()
        self.config.traffic.enabled = self.traffic.get()
        self.config.traffic.rich_areas_only_supers = self.rich_areas_only.get()
        self.config.traffic.adaptive_performance = self.adaptive_performance.get()
        self.config.vehicles.enable_all = self.enable_all_vehicles.get()
        self.config.vehicles.disabled_classes = self._comma_values(self.disabled_classes.get())
        self.config.vehicles.disabled_vehicles = self._comma_values(self.disabled_vehicles.get())
        self.config.script.enable_dlc_police = self.police.get()
        self.config.script.enable_logging = self.logging_enabled.get()
        self.config.script.gbay_key = self.gbay_key.get()
        self.config.script.night_vision_key = self.night_vision_key.get()
        self.config.script.world_vector_key = self.world_vector_key.get()
        self.config.script.seat_selector_enabled = self.seat_selector_enabled.get()
        self.config.script.seat_selector_key = self.seat_selector_key.get()
        self.config.script.safe_mode = self.safe_mode.get()
        self.config.script.reduced_motion = self.reduced_motion.get()
        self.config.script.colorblind_mode = self.colorblind_mode.get()
        self.config.script.ui_scale = self.ui_scale.get()
        self.config.script.hold_duration_ms = self.hold_duration_ms.get()
        self.config.script.gbay_free_mode = self.gbay_free_mode.get()
        self.config.script.garages_always_accessible = \
            self.garages_always_accessible.get()
        self.config.script.enhanced_police_ai = \
            self.enhanced_police_ai.get()
        self.config.script.gta_iv_npc_physics = \
            self.gta_iv_npc_physics.get()
        self.config.script.gta_iv_npc_physics_debug = \
            self.gta_iv_npc_physics_debug.get()
        self.config.script.axle_test_harness = \
            self.axle_test_harness.get()
        enhanced_smoke = getattr(self, "enhanced_smoke_effects", None)
        if enhanced_smoke is not None:
            self.config.script.enhanced_smoke_effects = enhanced_smoke.get()
        if hasattr(self, "controller_enabled"):
            self.config.script.controller_enabled = self.controller_enabled.get()
        for name in (
            "controller_open_gbay", "controller_open_gbay_modifier",
            "controller_night_vision", "controller_night_vision_modifier",
            "controller_seat_selector", "controller_seat_selector_modifier",
            "controller_accept", "controller_back", "controller_up", "controller_down",
            "controller_left", "controller_right", "controller_page_left",
            "controller_page_right", "controller_category_prev",
            "controller_category_next", "controller_filter", "controller_search",
            "controller_favorite",
        ):
            variable = getattr(self, name, None)
            if variable is not None:
                setattr(self.config.script, name, variable.get())
        return self.config

    @staticmethod
    def _comma_values(value: str) -> list[str]:
        return list(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))

    def _mark_dirty(self, *_args) -> None:
        self.settings_dirty = True
        self.notice_text.set("Unsaved changes")

    def _clear_dirty(self, notice: str = "Settings saved") -> None:
        self.settings_dirty = False
        self.notice_text.set(notice)

    def save(self) -> bool:
        try:
            self.manager.save_config(self._current_config())
            self._append_log("Settings saved.")
            self._clear_dirty()
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save settings", str(exc))
            return False

    def save_profile(self) -> None:
        try:
            self.profiles.save(self.profile_name.get(), self._current_config())
            self.profile_box.configure(values=self.profiles.list())
            self._append_log(f"Saved profile {self.profile_name.get().strip()}.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save profile", str(exc))

    def load_profile(self) -> None:
        try:
            self.config = self.profiles.load(self.profile_name.get())
            self.path.set(self.config.general.gta_path)
            if hasattr(self, "legacy_path"):
                self.legacy_path.set(self.config.general.gta_legacy_path)
                self.enhanced_path.set(self.config.general.gta_enhanced_path)
                self.target_edition.set(self.config.general.target_edition.title())
            self.backup_enabled.set(self.config.general.backup)
            self.rpf_previews.set(self.config.general.enable_rpf_previews)
            self.traffic.set(self.config.traffic.enabled)
            self.rich_areas_only.set(self.config.traffic.rich_areas_only_supers)
            self.adaptive_performance.set(self.config.traffic.adaptive_performance)
            self.enable_all_vehicles.set(self.config.vehicles.enable_all)
            self.disabled_classes.set(", ".join(self.config.vehicles.disabled_classes))
            self.disabled_vehicles.set(", ".join(self.config.vehicles.disabled_vehicles))
            self.police.set(self.config.script.enable_dlc_police)
            self.logging_enabled.set(self.config.script.enable_logging)
            self.gbay_key.set(self.config.script.gbay_key)
            self.night_vision_key.set(self.config.script.night_vision_key)
            self.world_vector_key.set(self.config.script.world_vector_key)
            self.seat_selector_enabled.set(self.config.script.seat_selector_enabled)
            self.seat_selector_key.set(self.config.script.seat_selector_key)
            self.safe_mode.set(self.config.script.safe_mode)
            self.reduced_motion.set(self.config.script.reduced_motion)
            self.colorblind_mode.set(self.config.script.colorblind_mode)
            self.ui_scale.set(self.config.script.ui_scale)
            self.hold_duration_ms.set(self.config.script.hold_duration_ms)
            self.gbay_free_mode.set(self.config.script.gbay_free_mode)
            self.garages_always_accessible.set(
                self.config.script.garages_always_accessible)
            self.enhanced_police_ai.set(
                self.config.script.enhanced_police_ai)
            self.gta_iv_npc_physics.set(
                self.config.script.gta_iv_npc_physics)
            self.gta_iv_npc_physics_debug.set(
                self.config.script.gta_iv_npc_physics_debug)
            self.axle_test_harness.set(
                self.config.script.axle_test_harness)
            self.enhanced_smoke_effects.set(
                self.config.script.enhanced_smoke_effects)
            self.controller_enabled.set(self.config.script.controller_enabled)
            for name in (
                "controller_open_gbay", "controller_open_gbay_modifier",
                "controller_night_vision", "controller_night_vision_modifier",
                "controller_seat_selector", "controller_seat_selector_modifier",
                "controller_accept", "controller_back", "controller_up", "controller_down",
                "controller_left", "controller_right", "controller_page_left",
                "controller_page_right", "controller_category_prev",
                "controller_category_next", "controller_filter", "controller_search",
                "controller_favorite",
            ):
                getattr(self, name).set(getattr(self.config.script, name))
            self.notice_text.set(
                f"Profile '{self.profile_name.get()}' loaded · save to apply"
            )
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not load profile", str(exc))

    def refresh(self) -> None:
        status = self.manager.status(self._current_config())
        self._show_status(status)
        self.refresh_mods()
        self.refresh_content()

    def _content_registry(self) -> ExtensionRegistry:
        gta_path = self.manager.resolve_path(self._current_config())
        if gta_path is None:
            raise ValueError("Select a valid GTA V installation first.")
        return ExtensionRegistry(gta_path)

    def refresh_content(self) -> None:
        if not hasattr(self, "content_tree"):
            return
        selected = self.content_tree.selection()
        selected_id = selected[0] if selected else None
        self.content_tree.delete(*self.content_tree.get_children())
        self.content_tree_items: dict[str, tuple[str, str | None]] = {}
        manifests: dict[str, ExtensionManifest] = {}
        registry_entries: dict[str, dict[str, object]] = {}
        registry_error = ""
        try:
            manifests.update({
                manifest.extension_id: manifest
                for manifest in self.manager.extension_catalog.discover()
            })
        except (OSError, ValueError) as exc:
            self.content_detail_title.set("Content catalog error")
            self.content_detail_text.set(str(exc))
        try:
            for entry in self._content_registry().installed():
                manifest = ExtensionManifest.from_registry_entry(entry)
                manifests[manifest.extension_id] = manifest
                registry_entries[manifest.extension_id] = entry
        except (OSError, ValueError, KeyError) as exc:
            registry_error = str(exc)
        self.content_registry_error = registry_error
        self.content_manifests = manifests
        self.content_registry_entries = registry_entries

        for extension_id, manifest in sorted(
            manifests.items(), key=lambda item: item[1].name.casefold(),
        ):
            entry = registry_entries.get(extension_id)
            if entry is None:
                if registry_error:
                    status = "Registry error"
                else:
                    status = (
                        "Install / Repair"
                        if extension_id.startswith("allin1.") else "Available"
                    )
            elif entry.get("blocked_reason"):
                status = "Blocked"
            else:
                status = "Enabled" if entry.get("enabled") else "Disabled"
            parent_id = f"content:{extension_id}"
            self.content_tree.insert(
                "", "end", iid=parent_id, text=manifest.name, open=True,
                values=("Package", manifest.version, status),
            )
            self.content_tree_items[parent_id] = (extension_id, None)
            for system in manifest.systems:
                child_id = f"system:{extension_id}:{system.system_id}"
                system_status = "Experimental" if system.experimental else "Included"
                if entry is not None and not entry.get("enabled"):
                    system_status = "Off"
                self.content_tree.insert(
                    parent_id, "end", iid=child_id, text=system.name,
                    values=(system.category, "", system_status),
                )
                self.content_tree_items[child_id] = (
                    extension_id, system.system_id,
                )
        if selected_id and self.content_tree.exists(selected_id):
            self.content_tree.selection_set(selected_id)
            self.content_tree.focus(selected_id)
        elif self.content_tree.get_children():
            first = self.content_tree.get_children()[0]
            self.content_tree.selection_set(first)
            self.content_tree.focus(first)
            self._show_content_details()

    def _core_content_variable(self, config_key: str | None) -> tk.Variable | None:
        if not config_key:
            return None
        names = {
            "script.gbay_free_mode": "gbay_free_mode",
            "general.enable_rpf_previews": "rpf_previews",
            "vehicles.enable_all": "enable_all_vehicles",
            "traffic.enabled": "traffic",
            "traffic.rich_areas_only_supers": "rich_areas_only",
            "traffic.adaptive_performance": "adaptive_performance",
            "script.enable_dlc_police": "police",
            "script.garages_always_accessible": "garages_always_accessible",
            "script.seat_selector_enabled": "seat_selector_enabled",
            "script.enhanced_police_ai": "enhanced_police_ai",
            "script.gta_iv_npc_physics": "gta_iv_npc_physics",
            "script.gta_iv_npc_physics_debug": "gta_iv_npc_physics_debug",
            "script.axle_test_harness": "axle_test_harness",
            "script.enhanced_smoke_effects": "enhanced_smoke_effects",
            "script.reduced_motion": "reduced_motion",
            "script.colorblind_mode": "colorblind_mode",
            "script.ui_scale": "ui_scale",
        }
        name = names.get(config_key)
        return getattr(self, name, None) if name else None

    @staticmethod
    def _new_content_variable(
        setting_type: str, value: object,
    ) -> tk.Variable:
        if setting_type == "boolean":
            return tk.BooleanVar(value=bool(value))
        if setting_type == "integer":
            return tk.IntVar(value=int(value))
        if setting_type == "number":
            return tk.DoubleVar(value=float(value))
        return tk.StringVar(value=str(value))

    def _show_content_details(self, _event=None) -> None:
        selection = self.content_tree.selection() if hasattr(self, "content_tree") else ()
        if not selection:
            return
        selected = self.content_tree_items.get(selection[0])
        if selected is None:
            return
        extension_id, system_id = selected
        manifest = self.content_manifests[extension_id]
        entry = self.content_registry_entries.get(extension_id, {})
        self.content_selected_system = selected
        for child in self.content_settings_frame.winfo_children():
            child.destroy()
        self.content_setting_vars.clear()
        if system_id is None:
            self.content_detail_title.set(manifest.name)
            status = "not installed"
            if getattr(self, "content_registry_error", ""):
                status = f"registry error: {self.content_registry_error}"
            if entry:
                status = "enabled" if entry.get("enabled") else "disabled"
                if entry.get("blocked_reason"):
                    status = f"blocked: {entry['blocked_reason']}"
            capability_text = ", ".join(manifest.capabilities) or "none declared"
            self.content_detail_text.set(
                f"{manifest.description or 'No package description.'}\n\n"
                f"API {manifest.api_version} · {len(manifest.systems)} system(s) · "
                f"{status}\nCapabilities: {capability_text}"
            )
            ttk.Label(
                self.content_settings_frame,
                text="Choose a system below this package to review its settings.",
                background="#ffffff", foreground="#52635c", wraplength=500,
            ).pack(anchor="w")
            return
        system = next(
            item for item in manifest.systems if item.system_id == system_id
        )
        marker = " · Experimental" if system.experimental else ""
        self.content_detail_title.set(system.name + marker)
        self.content_detail_text.set(
            system.description or "This system does not provide a description."
        )
        effective = entry.get("settings", {}) if isinstance(entry, dict) else {}
        if not isinstance(effective, dict):
            effective = {}
        if not system.settings:
            ttk.Label(
                self.content_settings_frame,
                text="This system has no configurable settings.",
                background="#ffffff", foreground="#52635c",
            ).pack(anchor="w")
            return
        for setting in system.settings:
            row = ttk.Frame(self.content_settings_frame, style="Surface.TFrame")
            row.pack(fill="x", pady=(0, 10))
            value = self._content_setting_initial_value(setting, effective)
            variable = self._core_content_variable(setting.config_key)
            if variable is None:
                variable = self._new_content_variable(setting.setting_type, value)
            self.content_setting_vars[(extension_id, setting.key)] = variable
            if setting.setting_type == "boolean":
                ttk.Checkbutton(
                    row, text=setting.label, variable=variable,
                ).pack(anchor="w")
            else:
                ttk.Label(
                    row, text=setting.label, background="#ffffff",
                ).pack(anchor="w")
                if setting.setting_type == "choice":
                    ttk.Combobox(
                        row, textvariable=variable, values=setting.choices,
                        state="readonly",
                    ).pack(fill="x", pady=(3, 0))
                elif setting.setting_type in {"integer", "number"}:
                    ttk.Spinbox(
                        row,
                        from_=setting.minimum if setting.minimum is not None else -1000000,
                        to=setting.maximum if setting.maximum is not None else 1000000,
                        increment=setting.step or 1,
                        textvariable=variable,
                    ).pack(fill="x", pady=(3, 0))
                else:
                    ttk.Entry(row, textvariable=variable).pack(fill="x", pady=(3, 0))
            if setting.description:
                ttk.Label(
                    row, text=setting.description, wraplength=500,
                    foreground="#52635c", background="#ffffff",
                ).pack(anchor="w", pady=(3, 0))

    def _content_setting_initial_value(
        self, setting, effective: dict[str, object],
    ) -> object:
        """Use the active profile for bound settings, registry state otherwise."""
        if setting.config_key:
            section_name, field_name = setting.config_key.split(".", 1)
            section = getattr(self.config, section_name, None)
            if section is not None and hasattr(section, field_name):
                return getattr(section, field_name)
        if setting.key in effective:
            return effective[setting.key]
        return setting.default

    def apply_content_settings(self) -> None:
        selected = self.content_selected_system
        if selected is None:
            messagebox.showinfo("Content settings", "Select a content system first.")
            return
        extension_id, system_id = selected
        if system_id is None:
            messagebox.showinfo("Content settings", "Select a system below the package.")
            return
        manifest = self.content_manifests[extension_id]
        system = next(item for item in manifest.systems if item.system_id == system_id)
        values: dict[str, object] = {}
        try:
            for setting in system.settings:
                variable = self.content_setting_vars[(extension_id, setting.key)]
                values[setting.key] = setting.validate(variable.get())
            unbound = [
                setting for setting in system.settings if not setting.config_key
            ]
            installed = extension_id in self.content_registry_entries
            if unbound and not installed:
                raise ValueError(
                    "Install this content package before saving its package-owned settings."
                )
            apply_settings_to_config(manifest, self.config, values)
            config = self._current_config()
            self.manager.save_config(config)
            if installed and unbound:
                registry = self._content_registry()
                registry.set_settings(
                    extension_id,
                    {setting.key: values[setting.key] for setting in unbound},
                )
            self.settings_dirty = False
            self.notice_text.set(f"Saved settings for {system.name}")
            self.refresh_content()
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror("Could not save content settings", str(exc))

    def toggle_selected_content(self, enabled: bool) -> None:
        selected = self.content_selected_system
        if selected is None:
            messagebox.showinfo("Content package", "Select a content package first.")
            return
        extension_id, _system_id = selected
        entry = self.content_registry_entries.get(extension_id)
        if entry is None:
            messagebox.showinfo(
                "Content package",
                "Run Install / Repair to install the official content packages first.",
            )
            return
        try:
            if entry.get("source") == "built-in":
                self._content_registry().set_builtin_enabled(extension_id, enabled)
            else:
                self._mod_service().set_enabled(extension_id, enabled)
            self.notice_text.set(
                f"{self.content_manifests[extension_id].name} "
                f"{'enabled' if enabled else 'disabled'} · restart Story Mode"
            )
            self.refresh_mods()
            self.refresh_content()
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Could not change package state", str(exc))

    def _mod_service(self, manifest: ModManifest | None = None) -> ModIntegrationService:
        config = self._current_config()
        gta_path = (
            self.manager.resolve_mod_path(config, manifest.editions)
            if manifest else self.manager.resolve_path(config)
        )
        if gta_path is None:
            raise ValueError("Select a valid GTA V installation first.")
        return ModIntegrationService(gta_path)

    def refresh_mods(self) -> None:
        if not hasattr(self, "mod_tree"):
            return
        selected = self._selected_mod_id()
        self.mod_tree.delete(*self.mod_tree.get_children())
        catalog_error: str | None = None
        try:
            manifests = self.mod_catalog.discover()
            self.mod_manifests = {manifest.mod_id: manifest for manifest in manifests}
        except (OSError, ValueError) as exc:
            self.mod_manifests = {}
            catalog_error = str(exc)
        try:
            sdk_examples = self.sdk_catalog.discover()
            self.sdk_manifests = {
                f"sdk:{manifest.addon_id}": manifest
                for manifest in sdk_examples
            }
        except (OSError, ValueError) as exc:
            self.sdk_manifests = {}
            catalog_error = catalog_error or f"SDK catalog: {exc}"

        try:
            builtin_content = self.manager.extension_catalog.discover()
            self.builtin_package_manifests = {
                f"builtin:{manifest.extension_id}": manifest
                for manifest in builtin_content
            }
        except (OSError, ValueError) as exc:
            self.builtin_package_manifests = {}
            catalog_error = catalog_error or f"Built-in content: {exc}"
        self.builtin_package_entries = {}
        try:
            registry_entries = {
                str(entry["id"]): entry
                for entry in self._content_registry().installed()
                if entry.get("source") == "built-in"
            }
            self.builtin_package_entries = {
                item_id: registry_entries[manifest.extension_id]
                for item_id, manifest in self.builtin_package_manifests.items()
                if manifest.extension_id in registry_entries
            }
        except (OSError, ValueError, KeyError):
            pass

        installed = {}
        try:
            installed = {status.mod_id: status for status in self._mod_service().list_installed()}
        except (OSError, ValueError):
            pass
        self.installed_mod_ids = set(installed)
        mod_ids = sorted(set(self.mod_manifests) | set(installed))
        for mod_id in mod_ids:
            manifest = self.mod_manifests.get(mod_id)
            status = installed.get(mod_id)
            name = manifest.name if manifest else status.name
            mod_type = (
                "content" if manifest and manifest.extension
                else manifest.mod_type if manifest else status.mod_type
            )
            version = manifest.version if manifest else status.version
            editions = (
                " + ".join(value.title() for value in manifest.editions)
                if manifest else self.config.general.target_edition.title()
            )
            state = "Enabled" if status and status.enabled else "Disabled" if status else "Available"
            self.mod_tree.insert("", "end", iid=mod_id, text=name,
                                 values=(mod_type.upper(), editions, version, state))
        for item_id, manifest in sorted(
            self.builtin_package_manifests.items(),
            key=lambda item: item[1].name.casefold(),
        ):
            entry = self.builtin_package_entries.get(item_id)
            if entry is None:
                state = "Install / Repair"
            elif entry.get("blocked_reason"):
                state = "Blocked"
            else:
                state = "Enabled" if entry.get("enabled") else "Disabled"
            self.mod_tree.insert(
                "", "end", iid=item_id, text=manifest.name,
                values=(
                    "CONTENT", "Legacy + Enhanced", manifest.version, state,
                ),
            )
        for sdk_id, manifest in sorted(
            self.sdk_manifests.items(), key=lambda item: item[1].name.lower()
        ):
            self.mod_tree.insert(
                "", "end", iid=sdk_id, text=manifest.name,
                values=(
                    "SDK", " + ".join(value.title() for value in manifest.editions),
                    manifest.version, "Built-in example",
                ),
            )
        self._mod_catalog_fingerprint = self.mod_catalog.fingerprint()
        if selected and self.mod_tree.exists(selected):
            self.mod_tree.selection_set(selected)
            self.mod_tree.focus(selected)
        elif catalog_error:
            self.mod_details.set(f"Catalog error: {catalog_error}")
        elif not mod_ids and not self.builtin_package_manifests and not self.sdk_manifests:
            self.mod_details.set(
                "No optional mods installed or present in the local catalog. Import a package to begin."
            )

    def _selected_mod_id(self) -> str | None:
        if not hasattr(self, "mod_tree"):
            return None
        selection = self.mod_tree.selection()
        return selection[0] if selection else None

    def _prepare_package_action_menu(self) -> None:
        """Disable package commands that cannot apply to the selection."""
        mod_id = self._selected_mod_id()
        builtin = mod_id in self.builtin_package_manifests
        sdk_example = mod_id in self.sdk_manifests
        available = mod_id in self.mod_manifests
        installed = mod_id in self.installed_mod_ids
        builtin_ready = builtin and mod_id in self.builtin_package_entries

        if sdk_example:
            install_label = "Open in ALLIN1 SDK"
        elif builtin:
            install_label = "Install / Repair"
        else:
            install_label = "Install / update"
        self.package_action_menu.entryconfigure(0, label=install_label)
        self.package_action_menu.entryconfigure(
            0, state="normal" if available or builtin or sdk_example else "disabled",
        )
        state_change = installed or builtin_ready
        self.package_action_menu.entryconfigure(
            2, state="normal" if state_change else "disabled",
        )
        self.package_action_menu.entryconfigure(
            3, state="normal" if state_change else "disabled",
        )
        self.package_action_menu.entryconfigure(
            5,
            state=(
                "normal"
                if installed and not builtin and not sdk_example
                else "disabled"
            ),
        )

    def _show_mod_details(self, _event=None) -> None:
        mod_id = self._selected_mod_id()
        if not mod_id:
            return
        manifest = self.mod_manifests.get(mod_id)
        builtin_manifest = self.builtin_package_manifests.get(mod_id)
        sdk_manifest = self.sdk_manifests.get(mod_id)
        if builtin_manifest:
            entry = self.builtin_package_entries.get(mod_id)
            if entry is None:
                status = "not installed; run Install / Repair"
            elif entry.get("blocked_reason"):
                status = f"blocked: {entry['blocked_reason']}"
            else:
                status = "enabled" if entry.get("enabled") else "disabled"
            self.mod_details.set(
                f"{builtin_manifest.description or 'Included ALLIN1 content package.'}\n"
                f"Package ID: {builtin_manifest.extension_id} · Built into ALLIN1 · "
                f"API {builtin_manifest.api_version} · "
                f"{len(builtin_manifest.systems)} system(s) · {status}. "
                "Open Content to configure its individual systems."
            )
            return
        if sdk_manifest:
            self.mod_details.set(
                f"{sdk_manifest.summary or 'Built-in SDK integration example.'}\n"
                f"Package ID: {sdk_manifest.addon_id} · Read-only SDK example · "
                f"Supports: {', '.join(value.title() for value in sdk_manifest.editions)}"
            )
            return
        if manifest:
            requirements = ", ".join(manifest.dependencies) or "none"
            description = manifest.description or "No description provided."
            extension_text = ""
            if manifest.extension:
                extension_text = (
                    f" · ALLIN1 API {manifest.extension.api_version} · "
                    f"{len(manifest.extension.systems)} contributed system(s)"
                )
            self.mod_details.set(
                f"{description}\nPackage ID: {mod_id} · Requires: {requirements} · "
                f"Supports: {', '.join(value.title() for value in manifest.editions)}"
                f"{extension_text}"
            )
        else:
            self.mod_details.set(
                f"{mod_id} is installed. Its original local package is not in the launcher catalog."
            )

    def import_mod_package(self) -> None:
        manifest_path = filedialog.askopenfilename(
            title="Select a local mod.toml or ZIP package",
            filetypes=(
                ("ALLIN1 package", "mod.toml *.zip"),
                ("ALLIN1 mod manifest", "mod.toml"),
                ("ZIP package", "*.zip"),
            ),
        )
        if not manifest_path:
            return
        source = Path(manifest_path)
        try:
            # Payload checks and hashing run in the install worker so a large RPF
            # cannot block the Tk event loop.
            with open_mod_package(source, validate_payload=False) as manifest:
                package_name = manifest.name
                package_version = manifest.version
                package_id = manifest.mod_id
                service = self._mod_service(manifest)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Invalid mod package", str(exc))
            return
        if not messagebox.askyesno(
            "Install optional mod",
            f"Install {package_name} {package_version}?\n\n"
            "Only continue if you trust this package and its source.",
        ):
            return

        def install_imported_package():
            with open_mod_package(source) as verified:
                if (verified.mod_id, verified.version) != (package_id, package_version):
                    raise ValueError(
                        "The selected package changed after confirmation; review it again"
                    )
                return service.install(verified)

        self._run(f"Installing {package_name}", install_imported_package)

    def install_selected_mod(self) -> None:
        mod_id = self._selected_mod_id()
        if mod_id in self.builtin_package_manifests:
            self.install()
            return
        if mod_id in self.sdk_manifests:
            self.open_addon_sdk()
            return
        manifest = self.mod_manifests.get(mod_id or "")
        if manifest is None:
            messagebox.showinfo(
                "Package unavailable",
                "Select an available catalog package, or use Import & install package…",
            )
            return
        self._install_mod_manifest(manifest)

    def _install_mod_manifest(self, manifest: ModManifest) -> None:
        handoff_intents = getattr(self, "package_handoff_intents", {})
        traffic_intent = handoff_intents.get(manifest.mod_id)
        supports_traffic = _supports_package_traffic_intent(manifest)
        traffic_message = ""
        if traffic_intent is True and supports_traffic:
            traffic_message = (
                "\n\nAfter installation, this package's eligible road vehicles "
                "will be allowed in ambient traffic."
            )
        elif traffic_intent is False and supports_traffic:
            traffic_message = (
                "\n\nThis package's vehicles will remain disabled in ambient traffic."
            )
        elif traffic_intent is True:
            traffic_message = (
                "\n\nThe package does not expose a compatible traffic setting, so "
                "ambient traffic will remain unchanged."
            )
        if not messagebox.askyesno(
            "Install optional mod",
            f"Install {manifest.name} {manifest.version}?\n\n"
            "Only continue if you trust this package and its source."
            f"{traffic_message}",
        ):
            return
        try:
            service = self._mod_service(manifest)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Game not found", str(exc))
            return
        def install_with_preferences():
            initial_settings = (
                {"traffic_enabled": traffic_intent}
                if traffic_intent is not None and supports_traffic
                else None
            )
            if initial_settings is None:
                result = service.install(manifest)
            else:
                result = service.install(manifest, initial_settings=initial_settings)
            handoff_intents.pop(manifest.mod_id, None)
            return result

        self._run(f"Installing {manifest.name}", install_with_preferences)

    def toggle_selected_mod(self, enabled: bool) -> None:
        mod_id = self._selected_mod_id()
        if not mod_id:
            messagebox.showinfo("Optional mods", "Select an installed mod first.")
            return
        builtin_manifest = self.builtin_package_manifests.get(mod_id)
        if builtin_manifest is not None:
            entry = self.builtin_package_entries.get(mod_id)
            if entry is None:
                messagebox.showinfo(
                    "Built-in content",
                    "Run Install / Repair before changing this package.",
                )
                return
            try:
                self._content_registry().set_builtin_enabled(
                    builtin_manifest.extension_id, enabled,
                )
                self.notice_text.set(
                    f"{builtin_manifest.name} "
                    f"{'enabled' if enabled else 'disabled'} · restart Story Mode"
                )
                self.refresh_mods()
                self.refresh_content()
            except (OSError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Could not change package state", str(exc))
            return
        if mod_id in self.sdk_manifests:
            messagebox.showinfo(
                "Built-in SDK example",
                "This package documents an ALLIN1 built-in feature and is not "
                "enabled or disabled as a separate mod.",
            )
            return
        if mod_id not in self.installed_mod_ids:
            messagebox.showinfo("Optional mods", "Install the selected package first.")
            return
        try:
            service = self._mod_service()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Game not found", str(exc))
            return
        verb = "Enabling" if enabled else "Disabling"
        self._run(f"{verb} {mod_id}", lambda: service.set_enabled(mod_id, enabled))

    def uninstall_selected_mod(self) -> None:
        mod_id = self._selected_mod_id()
        if not mod_id:
            messagebox.showinfo("Optional mods", "Select an installed mod first.")
            return
        if mod_id in self.builtin_package_manifests:
            messagebox.showinfo(
                "Built-in content",
                "This package is included with ALLIN1 and cannot be uninstalled "
                "separately. Use Install / Repair to restore it.",
            )
            return
        if mod_id in self.sdk_manifests:
            messagebox.showinfo(
                "Built-in SDK example",
                "This package is part of ALLIN1 and cannot be uninstalled from "
                "the optional package manager.",
            )
            return
        if mod_id not in self.installed_mod_ids:
            messagebox.showinfo("Optional mods", "The selected package is not installed.")
            return
        if not messagebox.askyesno(
            "Uninstall optional mod",
            f"Remove {mod_id} and restore any files it replaced?",
        ):
            return
        try:
            service = self._mod_service()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Game not found", str(exc))
            return
        self._run(f"Uninstalling {mod_id}", lambda: service.uninstall(mod_id))

    def _show_status(self, status: InstallationStatus) -> None:
        self.current_status = status
        presentation = _status_presentation(status)
        self.status_headline.set(presentation.headline)
        self.status_detail.set(presentation.detail)
        style = {
            "success": "Success.Status.TLabel",
            "warning": "Warning.Status.TLabel",
            "error": "Error.Status.TLabel",
        }[presentation.tone]
        self.status_headline_label.configure(style=style)
        self.status_accent.configure(background={
            "success": "#2d9c50",
            "warning": "#d09a22",
            "error": "#c94b3b",
        }[presentation.tone])
        path = str(status.gta_path) if status.gta_path else "Not detected"
        mark = lambda value: "Installed" if value else "Missing"
        self.status_text.set(
            f"Game folder: {path}\n"
            f"Edition: {status.edition}  ·  ALLIN1: {mark(status.mod_installed)}\n"
            f"ScriptHookV: {mark(status.scripthookv_installed)}  ·  "
            f"ScriptHookVDotNet: {mark(status.shvdn_installed)}\n"
            f"Preview loader: {status.rpf_loader_status}"
        )
        installed = status.installed_version or ("unknown" if status.mod_installed else "not installed")
        self.version_text.set(
            f"Launcher {status.manager_version} · Installed client {installed} · "
            "updates not checked"
        )
        if not self.busy:
            self._set_actions(True)

    def show_about(self) -> None:
        self.open_help_center("about")

    def check_for_updates(self) -> None:
        """Check releases from the persistent Setup workspace."""
        self.version_text.set(f"Launcher {__version__} · checking for updates…")
        self.update_button.configure(state="disabled")

        def worker() -> None:
            try:
                release = fetch_latest_release(__version__)
                self.messages.put((
                    "release", (release, self.version_text, self.update_button),
                ))
            except Exception as exc:
                self.messages.put((
                    "release_error", (exc, self.version_text, self.update_button),
                ))

        threading.Thread(target=worker, daemon=True).start()

    def open_help_center(self, topic: str | None = None) -> None:
        """Navigate to embedded task help without creating another window."""
        if topic is None:
            topic = {
                "setup": "getting-started",
                "gameplay": "gameplay",
                "content": "content",
                "input": "input",
                "mods": "packages",
                "characters": "characters",
                "sdk": "sdk",
                "activity": "troubleshooting",
            }.get(getattr(self, "current_workspace", "setup"), "getting-started")
        self._select_workspace("help")
        if self.help_workspace is not None:
            self.help_workspace.show_topic(topic)

    def install(self) -> None:
        config = self._current_config()
        install_rpf_loader = False
        status = self.manager.status(config)
        if (
            config.general.enable_rpf_previews
            and status.valid_game
            and not status.openrpf_installed
        ):
            install_rpf_loader = messagebox.askyesno(
                "Install optional preview loader?",
                "GBAY preview artwork needs an RPF loader.\n\n"
                "ALLIN1 can download the pinned RageOpenV release directly "
                "from its author and verify its SHA-256 before installing it. "
                "If needed, the official x64 Ultimate ASI Loader will also "
                "be downloaded and verified.\n\n"
                "These are optional third-party components. Choose No to "
                "continue with placeholder artwork.",
                parent=self.root,
            )

        def report(percentage: int, detail: str) -> None:
            self.messages.put(("progress", ("Repairing", percentage, detail)))
        self._run(
            "Repairing",
            lambda: self.manager.install(
                config,
                progress=report,
                rpf_loader_consent=(
                    (lambda _path, _enhanced: install_rpf_loader)
                    if config.general.enable_rpf_previews else None
                ),
            ),
            determinate=True,
        )

    def launch_game(self) -> None:
        """Save the current settings and start the selected Story Mode installation."""
        if self.busy or self.launch_pending:
            return
        self.launch_pending = True
        self.launch_button.configure(state="disabled")
        config = self._current_config()
        gta_path = self.manager.resolve_path(config)
        if gta_path is None:
            self._reset_launch_guard()
            messagebox.showerror("Game not found", "Select a GTA V installation first.")
            return
        try:
            # A structurally readable RPF can still fail GTA's startup data
            # manager. Block packs that failed a real Story Mode canary instead
            # of asking the player to discover the same hang again.
            from allin1.health import consume_rpf_canary, scan_installation
            rpf_hazards = [
                issue for issue in scan_installation(gta_path).issues
                if issue.code in {"rpf_pack_quarantined", "rpf_pack_incomplete"}
            ]
            if rpf_hazards:
                details = "\n".join(f"• {issue.message}" for issue in rpf_hazards)
                raise ValueError(
                    "RPF safety check blocked launch:\n\n" + details +
                    "\n\nRun Install / Repair, then launch again."
                )
            self.manager.save_config(config)
            target = launch_gta(gta_path)
            smoke_canary_consumed = consume_rpf_canary(
                gta_path, "allin1_smoke"
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._reset_launch_guard()
            self._append_log(f"Launch failed: {exc}")
            messagebox.showerror("Could not launch GTA V", str(exc))
            return
        self._clear_dirty("Launching GTA V")
        self._append_log(f"Launching {target.description}.")
        if smoke_canary_consumed:
            self._append_log(
                "Consumed the one-run colored-smoke RPF canary authorization."
            )
        # Ignore repeated clicks or key-repeat while Steam and Rockstar hand
        # off the request. Reopening the URI can restart the game's intro.
        self.root.after(15000, self._reset_launch_guard)

    def _reset_launch_guard(self) -> None:
        self.launch_pending = False
        if not self.busy:
            self.launch_button.configure(state="normal")

    def uninstall(self) -> None:
        if not messagebox.askyesno("Uninstall ALLIN1", "Remove ALLIN1 files and restore its game changes?"):
            return
        config = self._current_config()
        self._run("Uninstalling", lambda: self.manager.uninstall(config))

    def customize_characters(self) -> None:
        self._select_workspace("characters")

    def _ensure_character_workspace(self) -> None:
        gta_path = self.manager.resolve_path(self._current_config())
        if gta_path is not None and (
            self.character_workspace is not None
            and self.character_workspace_path == gta_path.resolve()
            and self.character_workspace.winfo_exists()
        ):
            return
        for child in self.characters_page.winfo_children():
            child.destroy()
        self.character_workspace = None
        self.character_workspace_path = None
        if gta_path is None:
            empty = ttk.Frame(self.characters_page, padding=24)
            empty.pack(fill="both", expand=True)
            ttk.Label(
                empty, text="Characters & saved content", style="PageTitle.TLabel",
            ).pack(anchor="w")
            ttk.Label(
                empty,
                text=("Select a valid GTA V installation in Setup before editing "
                      "character progress, garages, weapons, or outfits."),
                wraplength=760, justify="left", foreground="#52635c",
            ).pack(anchor="w", pady=(5, 16))
            ttk.Button(
                empty, text="Go to Setup", style="Accent.TButton",
                command=lambda: self._select_workspace("setup"),
            ).pack(anchor="w")
            return
        self.character_workspace = CharacterCustomizationDialog(
            self.characters_page, self.manager.project_root,
            gta_path / "scripts", self.config, embedded=True,
        )
        self.character_workspace_path = gta_path.resolve()

    def open_addon_sdk(self) -> None:
        # A real launcher shell focuses the existing SDK. Keeping this tied to
        # the initialized Tk owner also makes the launch resolver deterministic
        # for headless callers and contract tests.
        if hasattr(self, "root") and _focus_existing_window("ALLIN1 SDK"):
            self._append_log("Focused the existing ALLIN1 SDK workspace.")
            return
        managed = read_sdk_status(
            getattr(self, "sdk_install_root", default_sdk_root())
        )
        installed = shutil.which("allin1-sdk-gui")
        sdk_root = self.manager.project_root.parent / "ALLIN1-SDK"
        environment = os.environ.copy()
        if getattr(sys, "frozen", False):
            # Give the separately installed SDK a narrow, explicit route back
            # to this exact Launcher build. The SDK may only use it to reveal a
            # prepared package; normal user confirmation still owns install.
            environment["ALLIN1_LAUNCHER_EXECUTABLE"] = sys.executable
        if managed.healthy and managed.executable is not None:
            command = [str(managed.executable)]
            working_directory = managed.root
        elif installed:
            command = [installed]
            working_directory = Path(installed).parent
        elif (sdk_root / "src" / "allin1_sdk" / "app.py").is_file():
            command = [sys.executable, "-m", "allin1_sdk.app"]
            working_directory = sdk_root
            source = str(sdk_root / "src")
            existing = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = source + (os.pathsep + existing if existing else "")
        else:
            self.manage_addon_sdk()
            return
        options: dict[str, object] = {}
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                command, cwd=working_directory, env=environment, **options,
            )
        except OSError as exc:
            messagebox.showerror("Could not open ALLIN1 SDK", str(exc))
            return
        self._append_log(f"Opened standalone ALLIN1 SDK from {working_directory}.")

    def manage_addon_sdk(self) -> None:
        self._select_workspace("sdk")

    def _ensure_sdk_workspace(self) -> None:
        existing = self.sdk_manager_dialog
        if existing is not None and existing.winfo_exists():
            return
        for child in self.sdk_page.winfo_children():
            child.destroy()
        self.sdk_manager_dialog = SdkManagerDialog(
            self.sdk_page,
            install_root=getattr(self, "sdk_install_root", default_sdk_root()),
            embedded=True,
        )

    def open_asset_viewer(self) -> None:
        mod_id = self._selected_mod_id()
        source: Path | None = None
        manifest = self.mod_manifests.get(mod_id or "")
        sdk_manifest = self.sdk_manifests.get(mod_id or "")
        if manifest is not None:
            source = manifest.package_root
        elif sdk_manifest is not None:
            source = sdk_manifest.manifest_path.parent
        AssetViewerDialog(self.root, source)

    def open_rpf_explorer(self) -> None:
        roots = tuple(self.manager.resolve_paths(self._current_config()).values())
        RpfExplorerDialog(
            self.root, self.manager.project_root, installation_roots=roots,
        )

    def create_diagnostics(self) -> None:
        from allin1.diagnostics import create_diagnostic_bundle
        destination = filedialog.asksaveasfilename(
            title="Save diagnostic bundle", defaultextension=".zip",
            filetypes=(("ZIP archive", "*.zip"),))
        if not destination:
            return
        gta_path = self.manager.resolve_path(self._current_config())
        scripts = gta_path / "scripts" if gta_path else None
        try:
            create_diagnostic_bundle(Path(destination), self.manager.project_root, scripts)
            messagebox.showinfo("Diagnostics", "Redacted diagnostic bundle created.")
        except OSError as exc:
            messagebox.showerror("Diagnostics failed", str(exc))

    def run_health_check(self) -> None:
        from allin1.health import scan_installation
        gta_path = self.manager.resolve_path(self._current_config())
        if gta_path is None:
            messagebox.showerror("Health check", "Select a GTA V installation first.")
            return
        report = scan_installation(gta_path)
        details = "\n".join(f"[{issue.severity.upper()}] {issue.message}"
                            for issue in report.issues) or "No issues found."
        title = "Ready to launch" if report.launch_safe else "Action required"
        self._append_log(f"Health check: {title}.")
        for issue in report.issues:
            self._append_log(f"{issue.severity.upper()}: {issue.message}")
        messagebox.showinfo("Health check", f"{title}\n\n{details}")

    def copy_activity(self) -> None:
        text = self.log.get("1.0", "end-1c")
        if not text:
            self.notice_text.set("Activity log is empty")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.notice_text.set("Activity copied")

    def clear_activity(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.notice_text.set("Activity cleared")

    def open_log_folder(self) -> None:
        try:
            if os.name == "nt":
                os.startfile(self.manager.project_root)  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.manager.project_root.as_uri())
        except OSError as exc:
            messagebox.showerror("Could not open log folder", str(exc))

    def _on_close(self) -> None:
        if self.busy:
            messagebox.showwarning(
                "Operation in progress",
                "Wait for the current operation to finish before closing the launcher.",
            )
            return
        if self.settings_dirty:
            choice = messagebox.askyesnocancel(
                "Save settings?",
                "You have unsaved launcher settings. Save them before closing?",
            )
            if choice is None:
                return
            if choice and not self.save():
                return
        self.root.destroy()

    def _run(self, label: str, operation, *, determinate: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_actions(False)
        self._append_log(f"{label}…")
        self.notice_text.set("Working")
        self.operation_text.set(
            _operation_progress_text(label, 0) if determinate else label + "…"
        )
        self.busy_progress.configure(
            mode="determinate" if determinate else "indeterminate", value=0,
        )
        self.busy_progress.pack(side="left", padx=12)
        if not determinate:
            self.busy_progress.start(12)

        def worker() -> None:
            try:
                result = operation()
                self.messages.put(("done", (label, result)))
            except Exception as exc:  # UI boundary: display any operation failure.
                self.messages.put(("error", (label, exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_messages(self) -> None:
        while True:
            try:
                kind, payload = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "progress":
                label, percentage, detail = payload
                percentage = max(0, min(100, int(percentage)))
                self.busy_progress.configure(value=percentage)
                self.operation_text.set(_operation_progress_text(label, percentage))
                self.notice_text.set(str(detail))
            elif kind == "done":
                label, _ = payload
                self._finish()
                if label == "Repairing":
                    self._clear_dirty("Install / Repair complete")
                self._append_log(f"{label} completed.")
                messagebox.showinfo("ALLIN1 Launcher", f"{label} completed successfully.")
            elif kind == "error":
                label, exc = payload
                self._finish()
                self._append_log(f"{label} failed: {exc}")
                messagebox.showerror(f"{label} failed", str(exc))
            elif kind == "release":
                release, variable, button = payload
                state = "Update available" if release.update_available else "Up to date"
                variable.set(f"{state}: latest release is {release.version}.")
                self.version_text.set(
                    f"Launcher {__version__} · latest {release.version} · "
                    f"{state.lower()}"
                )
                button.configure(state="normal", text="Open latest release",
                                 command=lambda url=release.url: webbrowser.open(url))
            elif kind == "release_error":
                exc, variable, button = payload
                variable.set(f"Could not check releases: {exc}")
                button.configure(state="normal")
        self.root.after(100, self._drain_messages)

    def _finish(self) -> None:
        self.busy = False
        self.busy_progress.stop()
        self.busy_progress.configure(value=0)
        self.busy_progress.pack_forget()
        self.operation_text.set("")
        if not self.settings_dirty:
            self.notice_text.set("Ready")
        self._set_actions(True)
        self.refresh()

    def _set_actions(self, enabled: bool) -> None:
        if not enabled:
            for button in (
                self.launch_button, self.save_button, self.game_action_button,
                self.install_repair_button, self.update_button,
            ):
                button.configure(state="disabled")
            for menu in (self.file_menu, self.game_menu, self.sdk_menu):
                for index in range(menu.index("end") + 1):
                    if menu.type(index) == "command":
                        menu.entryconfigure(index, state="disabled")
        else:
            presentation = (
                _status_presentation(self.current_status)
                if self.current_status is not None
                else None
            )
            self.launch_button.configure(
                state=(
                    "normal"
                    if presentation and presentation.can_launch and not self.launch_pending
                    else "disabled"
                )
            )
            self.save_button.configure(state="normal")
            self.game_action_button.configure(state="normal")
            self.update_button.configure(state="normal")
            self.install_repair_button.configure(
                state=(
                    "normal"
                    if presentation and presentation.can_install
                    else "disabled"
                ),
            )
            for menu in (self.file_menu, self.sdk_menu):
                for index in range(menu.index("end") + 1):
                    if menu.type(index) == "command":
                        menu.entryconfigure(index, state="normal")
            for index in range(self.game_menu.index("end") + 1):
                if self.game_menu.type(index) == "command":
                    self.game_menu.entryconfigure(index, state="normal")
            self.game_menu.entryconfigure(
                "Launch GTA V",
                state=(
                    "normal"
                    if presentation and presentation.can_launch and not self.launch_pending
                    else "disabled"
                ),
            )
            self.game_menu.entryconfigure(
                "Install / Repair…",
                state="normal" if presentation and presentation.can_install else "disabled",
            )
            self.game_menu.entryconfigure(
                "Uninstall ALLIN1…",
                state="normal" if presentation and presentation.can_uninstall else "disabled",
            )
        state = "normal" if enabled else "disabled"
        for button in self.mod_action_buttons:
            button.configure(state=state)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def _parse_launcher_arguments(
    arguments: list[str] | None = None,
) -> LauncherHandoff | None:
    """Parse the deliberately narrow external Launcher navigation contract."""
    parser = argparse.ArgumentParser(prog="allin1-gui")
    parser.add_argument("--workspace", choices=("packages",))
    parser.add_argument("--package-id")
    parser.add_argument("--traffic", choices=("on", "off"))
    options = parser.parse_args(arguments)
    if options.package_id and options.workspace != "packages":
        parser.error("--package-id requires --workspace packages")
    if options.traffic and not options.package_id:
        parser.error("--traffic requires --package-id")
    if options.workspace == "packages":
        try:
            traffic = None if options.traffic is None else options.traffic == "on"
            return LauncherHandoff.create(options.package_id, traffic=traffic)
        except ValueError as exc:
            parser.error(str(exc))
    return None


def main(arguments: list[str] | None = None) -> None:
    setup_logging(PROJECT_ROOT)
    _register_windows_app()
    handoff = _parse_launcher_arguments(arguments)
    if not _claim_single_instance(handoff):
        return
    root = tk.Tk()
    window = ManagerWindow(root, ModManager(PROJECT_ROOT))
    if handoff is not None:
        root.after_idle(lambda: window._show_launcher_handoff(handoff))
    root.mainloop()


if __name__ == "__main__":
    main()
