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


class ManagerWindow:
    def __init__(self, root: tk.Tk, manager: ModManager) -> None:
        self.root = root
        self.manager = manager
        self.config = manager.load_config()
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.profiles = ProfileStore(manager.project_root / "profiles")

        root.title("GTA V ALLIN1 Manager")
        root.geometry("820x720")
        root.minsize(680, 540)

        self.path = tk.StringVar(value=self.config.general.gta_path)
        self.free_mode = tk.BooleanVar(value=self.config.general.free_mode)
        self.rpf_previews = tk.BooleanVar(value=self.config.general.enable_rpf_previews)
        self.traffic = tk.BooleanVar(value=self.config.traffic.enabled)
        self.police = tk.BooleanVar(value=self.config.script.enable_dlc_police)
        self.logging_enabled = tk.BooleanVar(value=self.config.script.enable_logging)
        self.gbay_key = tk.StringVar(value=self.config.script.gbay_key)
        self.night_vision_key = tk.StringVar(value=self.config.script.night_vision_key)
        self.preview_capture_key = tk.StringVar(value=self.config.script.preview_capture_key)
        self.seat_selector_enabled = tk.BooleanVar(value=self.config.script.seat_selector_enabled)
        self.safe_mode = tk.BooleanVar(value=self.config.script.safe_mode)
        self.reduced_motion = tk.BooleanVar(value=self.config.script.reduced_motion)
        self.colorblind_mode = tk.BooleanVar(value=self.config.script.colorblind_mode)
        self.ui_scale = tk.DoubleVar(value=self.config.script.ui_scale)
        self.hold_duration_ms = tk.IntVar(value=self.config.script.hold_duration_ms)
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
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="GTA V ALLIN1", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Install, configure, and remove the single-player mod.").pack(anchor="w", pady=(0, 14))

        profiles = ttk.LabelFrame(outer, text="Profile", padding=8)
        profiles.pack(fill="x", pady=(0, 10))
        self.profile_box = ttk.Combobox(profiles, textvariable=self.profile_name,
                                        values=self.profiles.list(), width=28)
        self.profile_box.pack(side="left")
        ttk.Button(profiles, text="Load", command=self.load_profile).pack(side="left", padx=6)
        ttk.Button(profiles, text="Save as…", command=self.save_profile).pack(side="left")

        location = ttk.LabelFrame(outer, text="Game location", padding=10)
        location.pack(fill="x")
        ttk.Entry(location, textvariable=self.path).pack(side="left", fill="x", expand=True)
        ttk.Button(location, text="Browse…", command=self._browse).pack(side="left", padx=(8, 0))

        options = ttk.LabelFrame(outer, text="Options", padding=10)
        options.pack(fill="x", pady=12)
        ttk.Checkbutton(options, text="Free purchases", variable=self.free_mode).grid(row=0, column=0, sticky="w", padx=(0, 30))
        ttk.Checkbutton(options, text="DLC traffic", variable=self.traffic).grid(row=0, column=1, sticky="w", padx=(0, 30))
        ttk.Checkbutton(options, text="DLC police", variable=self.police).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Detailed script logging", variable=self.logging_enabled).grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Force safe mode", variable=self.safe_mode).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Reduced motion", variable=self.reduced_motion).grid(row=2, column=1, sticky="w", pady=(8, 0))
        ttk.Checkbutton(options, text="Colorblind-safe palette", variable=self.colorblind_mode).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Label(options, text="UI text scale").grid(row=3, column=1, sticky="w", pady=(8, 0))
        ttk.Spinbox(options, from_=0.75, to=1.5, increment=0.05, textvariable=self.ui_scale,
                    width=6).grid(row=3, column=1, sticky="e", pady=(8, 0))
        ttk.Checkbutton(options, text="Experimental RPF artwork (may affect startup)",
                        variable=self.rpf_previews).grid(row=4, column=0, columnspan=2,
                                                         sticky="w", pady=(8, 0))

        controls = ttk.LabelFrame(outer, text="Mod controls", padding=10)
        controls.pack(fill="x", pady=(0, 12))
        key_choices = tuple([f"F{i}" for i in range(1, 13)] +
                            [chr(i) for i in range(ord("A"), ord("Z") + 1)] +
                            [f"NumPad{i}" for i in range(10)])
        for row, (label, variable) in enumerate((
            ("Open GBAY", self.gbay_key),
            ("Night vision", self.night_vision_key),
            ("Preview capture", self.preview_capture_key),
        )):
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(controls, textvariable=variable, values=key_choices,
                         state="readonly", width=14).grid(row=row, column=1, sticky="w", padx=(12, 30), pady=3)
        ttk.Checkbutton(controls, text="Enable hold-to-select vehicle seats",
                        variable=self.seat_selector_enabled).grid(row=0, column=2, rowspan=2, sticky="w")
        ttk.Label(controls, text="Seat hold (ms)").grid(row=2, column=2, sticky="w")
        ttk.Spinbox(controls, from_=100, to=2000, increment=50,
                    textvariable=self.hold_duration_ms, width=7).grid(row=2, column=3, sticky="w")

        state = ttk.LabelFrame(outer, text="Installation status", padding=10)
        state.pack(fill="x")
        ttk.Label(state, textvariable=self.status_text, justify="left").pack(anchor="w")
        ttk.Label(state, textvariable=self.version_text, justify="left").pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=12)
        self.install_button = ttk.Button(actions, text="Install / Repair", command=self.install)
        self.install_button.pack(side="left")
        self.uninstall_button = ttk.Button(actions, text="Uninstall", command=self.uninstall)
        self.uninstall_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(actions, text="Save settings", command=self.save)
        self.save_button.pack(side="left")
        ttk.Button(actions, text="Character customization…",
                   command=self.customize_characters).pack(side="left", padx=8)
        ttk.Button(actions, text="Diagnostics…", command=self.create_diagnostics).pack(side="left")
        ttk.Button(actions, text="Health check", command=self.run_health_check).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="About…", command=self.show_about).pack(side="left", padx=(8, 0))
        self.refresh_button = ttk.Button(actions, text="Refresh", command=self.refresh)
        self.refresh_button.pack(side="right")

        log_frame = ttk.LabelFrame(outer, text="Activity", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(outer, text="Use only in Story Mode. The installer disables BattlEye for mod loading.", foreground="#9a3412").pack(anchor="w", pady=(10, 0))

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="Select the GTA V installation folder")
        if selected:
            self.path.set(selected)
            self.refresh()

    def _current_config(self) -> Config:
        self.config.general.gta_path = self.path.get().strip() or "auto"
        self.config.general.free_mode = self.free_mode.get()
        self.config.general.enable_rpf_previews = self.rpf_previews.get()
        self.config.traffic.enabled = self.traffic.get()
        self.config.script.enable_dlc_police = self.police.get()
        self.config.script.enable_logging = self.logging_enabled.get()
        self.config.script.gbay_key = self.gbay_key.get()
        self.config.script.night_vision_key = self.night_vision_key.get()
        self.config.script.preview_capture_key = self.preview_capture_key.get()
        self.config.script.seat_selector_enabled = self.seat_selector_enabled.get()
        self.config.script.safe_mode = self.safe_mode.get()
        self.config.script.reduced_motion = self.reduced_motion.get()
        self.config.script.colorblind_mode = self.colorblind_mode.get()
        self.config.script.ui_scale = self.ui_scale.get()
        self.config.script.hold_duration_ms = self.hold_duration_ms.get()
        return self.config

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
            self.free_mode.set(self.config.general.free_mode)
            self.rpf_previews.set(self.config.general.enable_rpf_previews)
            self.traffic.set(self.config.traffic.enabled)
            self.police.set(self.config.script.enable_dlc_police)
            self.logging_enabled.set(self.config.script.enable_logging)
            self.gbay_key.set(self.config.script.gbay_key)
            self.night_vision_key.set(self.config.script.night_vision_key)
            self.preview_capture_key.set(self.config.script.preview_capture_key)
            self.seat_selector_enabled.set(self.config.script.seat_selector_enabled)
            self.safe_mode.set(self.config.script.safe_mode)
            self.reduced_motion.set(self.config.script.reduced_motion)
            self.colorblind_mode.set(self.config.script.colorblind_mode)
            self.ui_scale.set(self.config.script.ui_scale)
            self.hold_duration_ms.set(self.config.script.hold_duration_ms)
            self.refresh()
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not load profile", str(exc))

    def refresh(self) -> None:
        status = self.manager.status(self._current_config())
        self._show_status(status)

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
