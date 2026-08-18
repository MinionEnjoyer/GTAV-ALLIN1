"""Small Tkinter desktop manager for GTA V ALLIN1."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from allin1.config import Config
from allin1.game_launcher import launch_gta
from allin1.logging import setup_logging
from allin1.manager import InstallationStatus, ModManager
from allin1.mods import ModCatalog, ModIntegrationService, ModManifest
from allin1.customization_ui import CharacterCustomizationDialog
from allin1 import __version__
from allin1.versioning import fetch_latest_release
from allin1.profiles import ProfileStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSET_DIR = Path(__file__).resolve().parent / "assets"
WINDOWS_APP_ID = "MinionEnjoyer.GTAVALLIN1.Launcher"


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


class QueueLogHandler(logging.Handler):
    def __init__(self, messages: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.put(("log", self.format(record)))


def _operation_progress_text(label: str, percentage: int) -> str:
    return f"{label} - {max(0, min(100, int(percentage)))}%"


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
    def __init__(self, root: tk.Tk, manager: ModManager) -> None:
        self.root = root
        self.manager = manager
        self.config = manager.load_config()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.launch_pending = False
        self.profiles = ProfileStore(manager.project_root / "profiles")
        self.mod_catalog = ModCatalog(manager.project_root / "mods" / "catalog")
        self.mod_manifests: dict[str, ModManifest] = {}
        self.installed_mod_ids: set[str] = set()
        self.mod_action_buttons: list[ttk.Button] = []
        self.current_status: InstallationStatus | None = None
        self.settings_dirty = False

        root.title("GTA V ALLIN1 Launcher")
        root.geometry("1000x760")
        root.minsize(760, 600)
        self._window_icon: tk.PhotoImage | None = None
        self._banner_logo: ImageTk.PhotoImage | None = None
        self._native_icon_handle: int | None = None
        self._apply_window_branding()

        self.path = tk.StringVar(value=self.config.general.gta_path)
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
        self.version_text = tk.StringVar(value=f"Manager {__version__} · latest not checked")
        self.notice_text = tk.StringVar(value="Ready")
        self.operation_text = tk.StringVar(value="")
        self.profile_name = tk.StringVar(value="Full ALLIN1")

        self._build()
        self._setting_variables = (
            self.path, self.rpf_previews, self.backup_enabled, self.traffic,
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
        handler = QueueLogHandler(self.messages)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger("allin1").addHandler(handler)
        self.root.after(100, self._drain_messages)
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
                # Set both native icon slots on the actual HWND as well.
                user32 = ctypes.windll.user32
                user32.LoadImageW.restype = ctypes.c_void_p
                handle = user32.LoadImageW(
                    None, str(icon_path), 1, 0, 0, 0x10 | 0x40
                )
                if handle:
                    hwnd = self.root.winfo_id()
                    user32.SendMessageW(hwnd, 0x0080, 0, handle)  # ICON_SMALL
                    user32.SendMessageW(hwnd, 0x0080, 1, handle)  # ICON_BIG
                    self._native_icon_handle = handle
        except (OSError, tk.TclError):
            # Branding is optional; never prevent the repair tool from opening.
            self._window_icon = None

    def _build(self) -> None:
        green, dark_green, body_bg = "#2d9c50", "#1f7f42", "#f4f7f5"
        self.root.configure(background=body_bg)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), foreground="#173d32")
        style.configure("TFrame", background=body_bg)
        style.configure("TLabel", background=body_bg, foreground="#1e1e23")
        style.configure("TLabelframe", background="#ffffff", bordercolor="#d2dcd7")
        style.configure("TLabelframe.Label", background=body_bg, foreground=green,
                        font=("Segoe UI Semibold", 10))
        style.configure("Accent.TButton", background=green, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(12, 7))
        style.map("Accent.TButton", background=[("active", dark_green),
                                                ("disabled", "#9bc8aa")],
                  foreground=[("disabled", "#edf7f0")])
        style.configure("Quiet.TButton", padding=(10, 7))
        style.configure("Danger.TButton", foreground="#9a3412", padding=(10, 7))
        style.configure("Success.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#18753a")
        style.configure("Warning.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#9a6700")
        style.configure("Error.Status.TLabel", font=("Segoe UI Semibold", 15),
                        foreground="#b42318")
        style.configure("TNotebook", background=body_bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(18, 9),
                        foreground="#646e69")
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")],
                  foreground=[("selected", green)])
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        banner = tk.Frame(outer, background=dark_green, padx=18, pady=13)
        banner.pack(fill="x", pady=(0, 14))
        try:
            with Image.open(ASSET_DIR / "ALLIN1.png") as source:
                logo = source.convert("RGBA")
                logo.thumbnail((112, 72), Image.Resampling.LANCZOS)
            self._banner_logo = ImageTk.PhotoImage(logo)
            tk.Label(banner, image=self._banner_logo, background=dark_green,
                     borderwidth=0).pack(side="left", padx=(0, 16))
        except (OSError, tk.TclError):
            self._banner_logo = None

        banner_text = tk.Frame(banner, background=dark_green)
        banner_text.pack(side="left", fill="y")
        tk.Label(banner_text, text="GTA V ALLIN1 LAUNCHER", background=dark_green,
                 foreground="white", font=("Impact", 24)).pack(anchor="w")
        support = tk.Label(banner_text, text="A mod by MinionEnjoyer (Support Link!)", background=dark_green,
                           foreground="#d2ead9", cursor="hand2",
                           font=("Segoe UI Semibold", 9, "underline"))
        support.pack(anchor="w", pady=(3, 0))
        support.bind("<Button-1>", lambda _event: webbrowser.open(
            "https://buymeacoffee.com/minionenjoyer"))
        tk.Label(
            banner,
            text=f"v{__version__}",
            background="#176b36",
            foreground="white",
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=5,
        ).pack(side="right", anchor="n")

        tabs = ttk.Notebook(outer)
        self.tabs = tabs
        tabs.pack(fill="both", expand=True)
        home_view = ScrollableFrame(tabs, body_bg)
        gameplay_view = ScrollableFrame(tabs, body_bg)
        controls_view = ScrollableFrame(tabs, body_bg)
        mods_view = ScrollableFrame(tabs, body_bg)
        activity = ttk.Frame(tabs, padding=14)
        tabs.add(home_view, text="HOME")
        tabs.add(gameplay_view, text="GAMEPLAY")
        tabs.add(controls_view, text="CONTROLS")
        tabs.add(mods_view, text="MODS")
        tabs.add(activity, text="ACTIVITY")
        for index in range(5):
            self.root.bind(
                f"<Control-Key-{index + 1}>",
                lambda _event, selected=index: tabs.select(selected),
            )
        home = home_view.content
        gameplay = gameplay_view.content
        controls_page = controls_view.content
        mods_page = mods_view.content

        profiles = ttk.LabelFrame(home, text="PROFILE", padding=12)
        profiles.pack(fill="x", pady=(0, 10))
        self.profile_box = ttk.Combobox(profiles, textvariable=self.profile_name,
                                        values=self.profiles.list(), width=28)
        self.profile_box.pack(side="left")
        ttk.Button(profiles, text="Load", command=self.load_profile).pack(side="left", padx=6)
        ttk.Button(profiles, text="Save as…", command=self.save_profile).pack(side="left")

        location = ttk.LabelFrame(home, text="GAME LOCATION", padding=12)
        location.pack(fill="x")
        ttk.Entry(location, textvariable=self.path).pack(side="left", fill="x", expand=True)
        ttk.Button(location, text="Browse…", command=self._browse).pack(side="left", padx=(8, 0))

        options = ttk.LabelFrame(gameplay, text="MOD FEATURES", padding=14)
        options.pack(fill="x", pady=12)
        options.columnconfigure(0, weight=1)
        options.columnconfigure(1, weight=1)
        ttk.Checkbutton(options, text="Free GBAY purchases (no sale payouts)", variable=self.gbay_free_mode).grid(row=0, column=0, sticky="w", padx=(0, 30))
        ttk.Checkbutton(options, text="DLC traffic", variable=self.traffic).grid(row=0, column=1, sticky="w", padx=(0, 30))
        ttk.Checkbutton(options, text="DLC police", variable=self.police).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Detailed script logging", variable=self.logging_enabled).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Safe mode (disables traffic and Harmony Garage)", variable=self.safe_mode).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Disable GBAY page-transition fades", variable=self.reduced_motion).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Colorblind-safe palette", variable=self.colorblind_mode).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(options, text="UI text scale").grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Spinbox(options, from_=0.75, to=1.5, increment=0.05, textvariable=self.ui_scale,
                    width=6).grid(row=3, column=1, sticky="e", pady=(8, 0))
        ttk.Checkbutton(options, text="Back up game changes", variable=self.backup_enabled).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Supercars only in wealthy areas", variable=self.rich_areas_only).grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Adaptive traffic performance", variable=self.adaptive_performance).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Enable every DLC vehicle", variable=self.enable_all_vehicles).grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="GBAY preview artwork (requires OpenRPF/OpenIV)",
                        variable=self.rpf_previews).grid(row=6, column=0,
                                                         sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Allow garage entry while wanted",
                        variable=self.garages_always_accessible).grid(
                            row=6, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Enhanced Police AI",
                        variable=self.enhanced_police_ai).grid(
                            row=7, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Experimental GTA IV-style NPC physics",
                        variable=self.gta_iv_npc_physics).grid(
                            row=7, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Physics experiment diagnostics",
                        variable=self.gta_iv_npc_physics_debug).grid(
                            row=8, column=0, sticky="w", pady=(8, 0))

        controls = ttk.LabelFrame(controls_page, text="KEYBINDS & VEHICLE FILTERS", padding=14)
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
            controls_page, text="CONTROLLER CONFIGURATION", padding=14)
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

        mod_library = ttk.LabelFrame(mods_page, text="OPTIONAL MOD LIBRARY", padding=14)
        mod_library.pack(fill="both", expand=True, pady=(0, 12))
        ttk.Label(
            mod_library,
            text=("Install user-supplied ASI, script, RPF, and config/data packages from a "
                  "validated mod.toml manifest. ALLIN1 keeps a receipt and backs up files it replaces."),
            wraplength=790,
            justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 10))
        ttk.Label(
            mod_library,
            text="Only install mods you trust. Optional mods are intended for Story Mode and may require ScriptHookV, ScriptHookVDotNet, or OpenRPF.",
            foreground="#9a3412",
            wraplength=790,
            justify="left",
        ).pack(fill="x", anchor="w", pady=(0, 10))

        tree_frame = ttk.Frame(mod_library)
        tree_frame.pack(fill="both", expand=True)
        self.mod_tree = ttk.Treeview(
            tree_frame,
            columns=("type", "version", "status"),
            show="tree headings",
            height=10,
            selectmode="browse",
        )
        self.mod_tree.heading("#0", text="Mod")
        self.mod_tree.heading("type", text="Type")
        self.mod_tree.heading("version", text="Version")
        self.mod_tree.heading("status", text="Status")
        self.mod_tree.column("#0", width=310, minwidth=180)
        self.mod_tree.column("type", width=90, anchor="center")
        self.mod_tree.column("version", width=100, anchor="center")
        self.mod_tree.column("status", width=120, anchor="center")
        mod_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.mod_tree.yview)
        self.mod_tree.configure(yscrollcommand=mod_scroll.set)
        self.mod_tree.pack(side="left", fill="both", expand=True)
        mod_scroll.pack(side="right", fill="y")
        self.mod_tree.bind("<<TreeviewSelect>>", self._show_mod_details)

        self.mod_details = tk.StringVar(value="Select a package to view its details.")
        ttk.Label(mod_library, textvariable=self.mod_details, wraplength=790,
                  justify="left").pack(fill="x", anchor="w", pady=(10, 0))

        mod_actions = ttk.Frame(mods_page)
        mod_actions.pack(fill="x", pady=(0, 12))
        for label, command, style_name in (
            ("Import & install package…", self.import_mod_package, "Accent.TButton"),
            ("Install / Update", self.install_selected_mod, "TButton"),
            ("Enable", lambda: self.toggle_selected_mod(True), "TButton"),
            ("Disable", lambda: self.toggle_selected_mod(False), "TButton"),
            ("Uninstall", self.uninstall_selected_mod, "TButton"),
        ):
            button = ttk.Button(mod_actions, text=label, command=command, style=style_name)
            button.pack(side="left", padx=(0, 8))
            self.mod_action_buttons.append(button)
        ttk.Button(mod_actions, text="Refresh", command=self.refresh_mods).pack(side="right")

        ttk.Label(
            mods_page,
            text=("Package authors: place catalog packages under mods/catalog/<mod-id>/ with "
                  "a mod.toml and payload files. See mods/examples for safe starter manifests."),
            foreground="#3f6659",
            wraplength=790,
            justify="left",
        ).pack(fill="x", anchor="w")

        state = ttk.LabelFrame(home, text="INSTALLATION STATUS", padding=14)
        state.pack(fill="x")
        self.status_headline_label = ttk.Label(
            state,
            textvariable=self.status_headline,
            style="Warning.Status.TLabel",
        )
        self.status_headline_label.pack(anchor="w")
        ttk.Label(
            state,
            textvariable=self.status_detail,
            justify="left",
            wraplength=830,
        ).pack(anchor="w", pady=(3, 10))
        ttk.Separator(state).pack(fill="x", pady=(0, 9))
        ttk.Label(state, textvariable=self.status_text, justify="left",
                  wraplength=830).pack(anchor="w")
        ttk.Label(state, textvariable=self.version_text, justify="left",
                  foreground="#3f6659").pack(anchor="w", pady=(5, 0))

        utilities = ttk.LabelFrame(home, text="MAINTENANCE", padding=12)
        utilities.pack(fill="x", pady=(0, 10))
        for column, (label, command) in enumerate((
            ("Characters & garages", self.customize_characters),
            ("Diagnostics", self.create_diagnostics),
            ("Health check", self.run_health_check),
            ("About", self.show_about),
        )):
            ttk.Button(utilities, text=label, command=command,
                       style="Quiet.TButton").grid(row=0, column=column, padx=(0, 8), sticky="w")
        self.uninstall_button = ttk.Button(
            utilities, text="Uninstall ALLIN1", command=self.uninstall, style="Danger.TButton"
        )
        self.uninstall_button.grid(row=0, column=4, sticky="e")
        utilities.columnconfigure(4, weight=1)

        activity_toolbar = ttk.Frame(activity)
        activity_toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(
            activity_toolbar,
            text="Launcher operations and diagnostics appear here.",
            foreground="#3f6659",
        ).pack(side="left")
        ttk.Button(activity_toolbar, text="Open log folder", command=self.open_log_folder,
                   style="Quiet.TButton").pack(side="right")
        ttk.Button(activity_toolbar, text="Clear", command=self.clear_activity,
                   style="Quiet.TButton").pack(side="right", padx=6)
        ttk.Button(activity_toolbar, text="Copy", command=self.copy_activity,
                   style="Quiet.TButton").pack(side="right")
        log_frame = ttk.LabelFrame(activity, text="ACTIVITY LOG", padding=10)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = ttk.Frame(outer, padding=(0, 11, 0, 0))
        footer.pack(side="bottom", fill="x")
        footer_actions = ttk.Frame(footer)
        footer_actions.pack(side="right")
        footer_left = ttk.Frame(footer)
        footer_left.pack(side="left", fill="x", expand=True)
        ttk.Label(
            footer_left,
            text="STORY MODE ONLY",
            foreground="#9a3412",
            font=("Segoe UI Semibold", 9),
        ).pack(side="left")
        ttk.Label(footer_left, text="  ·  ").pack(side="left")
        ttk.Label(footer_left, textvariable=self.notice_text,
                  foreground="#3f6659").pack(side="left")
        self.busy_progress = ttk.Progressbar(
            footer_left, mode="determinate", maximum=100, length=170,
        )
        ttk.Label(footer_left, textvariable=self.operation_text,
                  foreground="#3f6659").pack(side="left")

        self.refresh_button = ttk.Button(footer_actions, text="Refresh", command=self.refresh,
                                         style="Quiet.TButton")
        self.refresh_button.pack(side="left")
        self.save_button = ttk.Button(footer_actions, text="Save settings", command=self.save,
                                      style="Quiet.TButton")
        self.save_button.pack(side="left", padx=7)
        self.install_button = ttk.Button(footer_actions, text="Install / Repair",
                                         command=self.install, style="Quiet.TButton")
        self.install_button.pack(side="left")
        self.launch_button = ttk.Button(footer_actions, text="Launch GTA V",
                                        command=self.launch_game, style="Accent.TButton")
        self.launch_button.pack(side="left", padx=(7, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="Select the GTA V installation folder")
        if selected:
            self.path.set(selected)
            self.refresh()

    def _current_config(self) -> Config:
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

    def _mod_service(self) -> ModIntegrationService:
        gta_path = self.manager.resolve_path(self._current_config())
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
            mod_type = manifest.mod_type if manifest else status.mod_type
            version = manifest.version if manifest else status.version
            state = "Enabled" if status and status.enabled else "Disabled" if status else "Available"
            self.mod_tree.insert("", "end", iid=mod_id, text=name,
                                 values=(mod_type.upper(), version, state))
        if selected and self.mod_tree.exists(selected):
            self.mod_tree.selection_set(selected)
            self.mod_tree.focus(selected)
        elif catalog_error:
            self.mod_details.set(f"Catalog error: {catalog_error}")
        elif not mod_ids:
            self.mod_details.set(
                "No optional mods installed or present in the local catalog. Import a package to begin."
            )

    def _selected_mod_id(self) -> str | None:
        if not hasattr(self, "mod_tree"):
            return None
        selection = self.mod_tree.selection()
        return selection[0] if selection else None

    def _show_mod_details(self, _event=None) -> None:
        mod_id = self._selected_mod_id()
        if not mod_id:
            return
        manifest = self.mod_manifests.get(mod_id)
        if manifest:
            requirements = ", ".join(manifest.dependencies) or "none"
            description = manifest.description or "No description provided."
            self.mod_details.set(
                f"{description}\nPackage ID: {mod_id} · Requires: {requirements} · "
                f"Supports: {', '.join(value.title() for value in manifest.editions)}"
            )
        else:
            self.mod_details.set(
                f"{mod_id} is installed. Its original local package is not in the launcher catalog."
            )

    def import_mod_package(self) -> None:
        manifest_path = filedialog.askopenfilename(
            title="Select a local mod.toml package manifest",
            filetypes=(("ALLIN1 mod manifest", "mod.toml"), ("TOML files", "*.toml")),
        )
        if not manifest_path:
            return
        try:
            # Payload checks and hashing run in the install worker so a large RPF
            # cannot block the Tk event loop.
            manifest = ModManifest.load(manifest_path, validate_payload=False)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Invalid mod package", str(exc))
            return
        self._install_mod_manifest(manifest)

    def install_selected_mod(self) -> None:
        mod_id = self._selected_mod_id()
        manifest = self.mod_manifests.get(mod_id or "")
        if manifest is None:
            messagebox.showinfo(
                "Package unavailable",
                "Select an available catalog package, or use Import & install package…",
            )
            return
        self._install_mod_manifest(manifest)

    def _install_mod_manifest(self, manifest: ModManifest) -> None:
        if not messagebox.askyesno(
            "Install optional mod",
            f"Install {manifest.name} {manifest.version}?\n\n"
            "Only continue if you trust this package and its source.",
        ):
            return
        try:
            service = self._mod_service()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Game not found", str(exc))
            return
        self._run(f"Installing {manifest.name}", lambda: service.install(manifest))

    def toggle_selected_mod(self, enabled: bool) -> None:
        mod_id = self._selected_mod_id()
        if not mod_id:
            messagebox.showinfo("Optional mods", "Select an installed mod first.")
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
        path = str(status.gta_path) if status.gta_path else "Not detected"
        mark = lambda value: "Installed" if value else "Missing"
        self.status_text.set(
            f"Game folder: {path}\n"
            f"Edition: {status.edition}  ·  ALLIN1: {mark(status.mod_installed)}  ·  "
            f"ScriptHookV: {mark(status.scripthookv_installed)}  ·  "
            f"ScriptHookVDotNet: {mark(status.shvdn_installed)}  ·  "
            f"Preview loader: {status.rpf_loader_status}"
        )
        installed = status.installed_version or ("unknown" if status.mod_installed else "not installed")
        self.version_text.set(
            f"Manager {status.manager_version} · Installed client {installed} · Update status not checked"
        )
        if not self.busy:
            self._set_actions(True)

    def show_about(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("About GTA V ALLIN1")
        dialog.geometry("560x390")
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="GTA V ALLIN1", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"Manager and mod client version {__version__}").pack(anchor="w", pady=(2, 16))
        ttk.Label(
            body,
            text=("Project goal\n\nBring GTA Online DLC vehicles, weapons, garages, "
                  "and related content into GTA V Story Mode through a safe, manageable "
                  "one-click install."),
            wraplength=510, justify="left",
        ).pack(anchor="w")
        ttk.Label(body, text="Created and maintained by MinionEnjoyer.").pack(anchor="w", pady=(18, 4))
        link = ttk.Label(body, text="buymeacoffee.com/minionenjoyer",
                         foreground="#087f5b", cursor="hand2")
        link.pack(anchor="w")
        link.bind("<Button-1>", lambda _event: webbrowser.open(
            "https://buymeacoffee.com/minionenjoyer"))
        update_status = tk.StringVar(value="Release status has not been checked.")
        ttk.Label(body, textvariable=update_status, wraplength=510).pack(anchor="w", pady=(22, 8))

        def check() -> None:
            update_status.set("Checking GitHub Releases…")
            button.configure(state="disabled")

            def worker() -> None:
                try:
                    release = fetch_latest_release(__version__)
                    self.messages.put(("release", (release, update_status, button)))
                except Exception as exc:
                    self.messages.put(("release_error", (exc, update_status, button)))

            threading.Thread(target=worker, daemon=True).start()

        button = ttk.Button(body, text="Check for updates", command=check)
        button.pack(anchor="w")

    def install(self) -> None:
        config = self._current_config()
        def report(percentage: int, detail: str) -> None:
            self.messages.put(("progress", ("Repairing", percentage, detail)))
        self._run(
            "Repairing",
            lambda: self.manager.install(config, progress=report),
            determinate=True,
        )

    def launch_game(self) -> None:
        """Save the current settings and start the selected GTA V installation."""
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
            self.manager.save_config(config)
            target = launch_gta(gta_path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            self._reset_launch_guard()
            self._append_log(f"Launch failed: {exc}")
            messagebox.showerror("Could not launch GTA V", str(exc))
            return
        self._clear_dirty("Launching GTA V")
        self._append_log(f"Launching {target.description}.")
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
        gta_path = self.manager.resolve_path(self._current_config())
        if gta_path is None:
            messagebox.showerror("Game not found", "Select a GTA V installation first.")
            return
        CharacterCustomizationDialog(self.root, self.manager.project_root,
                                     gta_path / "scripts", self.config)

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
                messagebox.showinfo("GTA V ALLIN1", f"{label} completed successfully.")
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
                    f"Manager {__version__} · latest {release.version} · {state.lower()}"
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
                self.launch_button,
                self.install_button,
                self.uninstall_button,
                self.save_button,
                self.refresh_button,
            ):
                button.configure(state="disabled")
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
            self.install_button.configure(
                state="normal" if presentation and presentation.can_install else "disabled"
            )
            self.uninstall_button.configure(
                state="normal" if presentation and presentation.can_uninstall else "disabled"
            )
            self.save_button.configure(state="normal")
            self.refresh_button.configure(state="normal")
        state = "normal" if enabled else "disabled"
        for button in self.mod_action_buttons:
            button.configure(state=state)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    setup_logging(PROJECT_ROOT)
    _register_windows_app()
    root = tk.Tk()
    ManagerWindow(root, ModManager(PROJECT_ROOT))
    root.mainloop()


if __name__ == "__main__":
    main()
