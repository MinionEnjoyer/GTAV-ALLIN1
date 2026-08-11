"""Small Tkinter desktop manager for GTA V ALLIN1."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from allin1.config import Config
from allin1.logging import setup_logging
from allin1.manager import InstallationStatus, ModManager
from allin1.mods import ModCatalog, ModIntegrationService, ModManifest
from allin1.customization_ui import CharacterCustomizationDialog
from allin1 import __version__
from allin1.versioning import fetch_latest_release
from allin1.profiles import ProfileStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class QueueLogHandler(logging.Handler):
    def __init__(self, messages: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.messages = messages

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.put(("log", self.format(record)))


class ScrollableFrame(ttk.Frame):
    """Vertically scrollable surface for settings-heavy launcher pages."""

    def __init__(self, parent, background: str = "#f8fafc") -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=background, highlightthickness=0)
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

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class ManagerWindow:
    def __init__(self, root: tk.Tk, manager: ModManager) -> None:
        self.root = root
        self.manager = manager
        self.config = manager.load_config()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.profiles = ProfileStore(manager.project_root / "profiles")
        self.mod_catalog = ModCatalog(manager.project_root / "mods" / "catalog")
        self.mod_manifests: dict[str, ModManifest] = {}
        self.installed_mod_ids: set[str] = set()
        self.mod_action_buttons: list[ttk.Button] = []

        root.title("GTA V ALLIN1 Launcher")
        root.geometry("940x820")
        root.minsize(780, 620)

        self.path = tk.StringVar(value=self.config.general.gta_path)
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
        self.preview_capture_key = tk.StringVar(value=self.config.script.preview_capture_key)
        self.seat_selector_enabled = tk.BooleanVar(value=self.config.script.seat_selector_enabled)
        self.seat_selector_key = tk.StringVar(value=self.config.script.seat_selector_key)
        self.safe_mode = tk.BooleanVar(value=self.config.script.safe_mode)
        self.reduced_motion = tk.BooleanVar(value=self.config.script.reduced_motion)
        self.colorblind_mode = tk.BooleanVar(value=self.config.script.colorblind_mode)
        self.ui_scale = tk.DoubleVar(value=self.config.script.ui_scale)
        self.hold_duration_ms = tk.IntVar(value=self.config.script.hold_duration_ms)
        self.gbay_free_mode = tk.BooleanVar(value=self.config.script.gbay_free_mode)
        self.spawner_debug = tk.BooleanVar(value=self.config.script.spawner_debug)
        self.garage_debug = tk.BooleanVar(value=self.config.script.garage_debug)
        self.status_text = tk.StringVar(value="Checking installation…")
        self.version_text = tk.StringVar(value=f"Manager {__version__} · latest not checked")
        self.profile_name = tk.StringVar(value="Full ALLIN1")

        self._build()
        handler = QueueLogHandler(self.messages)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger("allin1").addHandler(handler)
        self.root.after(100, self._drain_messages)
        self.refresh()

    def _build(self) -> None:
        green, dark_green, body_bg = "#2d9c50", "#238746", "#f8fafc"
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
        style.map("Accent.TButton", background=[("active", dark_green)])
        style.configure("TNotebook", background=body_bg, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(18, 9),
                        foreground="#646e69")
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")],
                  foreground=[("selected", green)])
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        banner = tk.Frame(outer, background=dark_green, padx=18, pady=13)
        banner.pack(fill="x", pady=(0, 14))
        tk.Label(banner, text="GTA V ALLIN1 LAUNCHER", background=dark_green,
                 foreground="white", font=("Impact", 24)).pack(anchor="w")
        support = tk.Label(banner, text="A mod by MinionEnjoyer (Support Link!)", background=dark_green,
                           foreground="#d2ead9", cursor="hand2",
                           font=("Segoe UI Semibold", 9, "underline"))
        support.pack(anchor="w", pady=(3, 0))
        support.bind("<Button-1>", lambda _event: webbrowser.open(
            "https://buymeacoffee.com/minionenjoyer"))

        tabs = ttk.Notebook(outer)
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
        ttk.Checkbutton(options, text="Safe mode (disable traffic and floor garages)", variable=self.safe_mode).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Disable GBAY page-transition fades", variable=self.reduced_motion).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Colorblind-safe palette", variable=self.colorblind_mode).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(options, text="UI text scale").grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Spinbox(options, from_=0.75, to=1.5, increment=0.05, textvariable=self.ui_scale,
                    width=6).grid(row=3, column=1, sticky="e", pady=(8, 0))
        ttk.Checkbutton(options, text="Back up game changes", variable=self.backup_enabled).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Supercars only in wealthy areas", variable=self.rich_areas_only).grid(row=4, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Adaptive traffic performance", variable=self.adaptive_performance).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Enable every DLC vehicle", variable=self.enable_all_vehicles).grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Spawner debug messages (developer)", variable=self.spawner_debug).grid(row=6, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Garage debug markers (developer)", variable=self.garage_debug).grid(row=7, column=0, sticky="w", pady=(8, 0))

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
            ("Preview capture (developer)", self.preview_capture_key),
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

        state = ttk.LabelFrame(home, text="INSTALLATION STATUS", padding=12)
        state.pack(fill="x")
        ttk.Label(state, textvariable=self.status_text, justify="left").pack(anchor="w")
        ttk.Label(state, textvariable=self.version_text, justify="left").pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(home)
        actions.pack(fill="x", pady=12)
        self.install_button = ttk.Button(actions, text="Install / Repair", command=self.install,
                                         style="Accent.TButton")
        self.install_button.pack(side="left")
        self.uninstall_button = ttk.Button(actions, text="Uninstall", command=self.uninstall)
        self.uninstall_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(actions, text="Save settings", command=self.save)
        self.save_button.pack(side="left")
        self.refresh_button = ttk.Button(actions, text="Refresh", command=self.refresh)
        self.refresh_button.pack(side="right")

        utilities = ttk.LabelFrame(home, text="TOOLS", padding=12)
        utilities.pack(fill="x", pady=(0, 10))
        for label, command in (
            ("Characters & garages", self.customize_characters),
            ("Diagnostics", self.create_diagnostics),
            ("Health check", self.run_health_check),
            ("About", self.show_about),
        ):
            ttk.Button(utilities, text=label, command=command).pack(side="left", padx=(0, 8))

        log_frame = ttk.LabelFrame(activity, text="ACTIVITY LOG", padding=10)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(home, text="Use only in Story Mode. The installer disables BattlEye for mod loading.",
                  foreground="#9a3412").pack(anchor="w", pady=(10, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="Select the GTA V installation folder")
        if selected:
            self.path.set(selected)
            self.refresh()

    def _current_config(self) -> Config:
        self.config.general.gta_path = self.path.get().strip() or "auto"
        self.config.general.free_mode = self.gbay_free_mode.get()
        self.config.general.backup = self.backup_enabled.get()
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
        self.config.script.preview_capture_key = self.preview_capture_key.get()
        self.config.script.seat_selector_enabled = self.seat_selector_enabled.get()
        self.config.script.seat_selector_key = self.seat_selector_key.get()
        self.config.script.safe_mode = self.safe_mode.get()
        self.config.script.reduced_motion = self.reduced_motion.get()
        self.config.script.colorblind_mode = self.colorblind_mode.get()
        self.config.script.ui_scale = self.ui_scale.get()
        self.config.script.hold_duration_ms = self.hold_duration_ms.get()
        self.config.script.gbay_free_mode = self.gbay_free_mode.get()
        self.config.script.spawner_debug = self.spawner_debug.get()
        self.config.script.garage_debug = self.garage_debug.get()
        return self.config

    @staticmethod
    def _comma_values(value: str) -> list[str]:
        return list(dict.fromkeys(item.strip().lower() for item in value.split(",") if item.strip()))

    def save(self) -> None:
        try:
            self.manager.save_config(self._current_config())
            self._append_log("Settings saved.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not save settings", str(exc))

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
            self.preview_capture_key.set(self.config.script.preview_capture_key)
            self.seat_selector_enabled.set(self.config.script.seat_selector_enabled)
            self.seat_selector_key.set(self.config.script.seat_selector_key)
            self.safe_mode.set(self.config.script.safe_mode)
            self.reduced_motion.set(self.config.script.reduced_motion)
            self.colorblind_mode.set(self.config.script.colorblind_mode)
            self.ui_scale.set(self.config.script.ui_scale)
            self.hold_duration_ms.set(self.config.script.hold_duration_ms)
            self.gbay_free_mode.set(self.config.script.gbay_free_mode)
            self.spawner_debug.set(self.config.script.spawner_debug)
            self.garage_debug.set(self.config.script.garage_debug)
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
        path = str(status.gta_path) if status.gta_path else "Not detected"
        mark = lambda value: "Installed" if value else "Missing"
        self.status_text.set(
            f"Game: {path}\nEdition: {status.edition}\n"
            f"ALLIN1: {mark(status.mod_installed)}    "
            f"ScriptHookV: {mark(status.scripthookv_installed)}    "
            f"ScriptHookVDotNet: {mark(status.shvdn_installed)}    "
            f"OpenRPF/OpenIV: {mark(status.openrpf_installed)}"
        )
        installed = status.installed_version or ("unknown" if status.mod_installed else "not installed")
        self.version_text.set(
            f"Manager {status.manager_version} · Installed client {installed} · latest not checked"
        )

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
        self._run("Installing", lambda: self.manager.install(config))

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
        messagebox.showinfo("Health check", f"{title}\n\n{details}")

    def _run(self, label: str, operation) -> None:
        if self.busy:
            return
        self.busy = True
        self._set_actions(False)
        self._append_log(f"{label}…")

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
            elif kind == "done":
                label, _ = payload
                self._finish()
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
        self._set_actions(True)
        self.refresh()

    def _set_actions(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (self.install_button, self.uninstall_button, self.save_button, self.refresh_button):
            button.configure(state=state)
        for button in self.mod_action_buttons:
            button.configure(state=state)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    setup_logging(PROJECT_ROOT)
    root = tk.Tk()
    ManagerWindow(root, ModManager(PROJECT_ROOT))
    root.mainloop()


if __name__ == "__main__":
    main()
