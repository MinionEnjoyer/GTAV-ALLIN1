"""Small Tkinter desktop manager for GTA V ALLIN1."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from allin1.config import Config
from allin1.logging import setup_logging
from allin1.manager import InstallationStatus, ModManager

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

        root.title("GTA V ALLIN1 Manager")
        root.geometry("760x610")
        root.minsize(680, 540)

        self.path = tk.StringVar(value=self.config.general.gta_path)
        self.free_mode = tk.BooleanVar(value=self.config.general.free_mode)
        self.traffic = tk.BooleanVar(value=self.config.traffic.enabled)
        self.police = tk.BooleanVar(value=self.config.script.enable_dlc_police)
        self.logging_enabled = tk.BooleanVar(value=self.config.script.enable_logging)
        self.status_text = tk.StringVar(value="Checking installation…")

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

        state = ttk.LabelFrame(outer, text="Installation status", padding=10)
        state.pack(fill="x")
        ttk.Label(state, textvariable=self.status_text, justify="left").pack(anchor="w")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=12)
        self.install_button = ttk.Button(actions, text="Install / Repair", command=self.install)
        self.install_button.pack(side="left")
        self.uninstall_button = ttk.Button(actions, text="Uninstall", command=self.uninstall)
        self.uninstall_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(actions, text="Save settings", command=self.save)
        self.save_button.pack(side="left")
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
        self.config.traffic.enabled = self.traffic.get()
        self.config.script.enable_dlc_police = self.police.get()
        self.config.script.enable_logging = self.logging_enabled.get()
        return self.config

    def save(self) -> None:
        try:
            self.manager.save_config(self._current_config())
            self._append_log("Settings saved.")
        except OSError as exc:
            messagebox.showerror("Could not save settings", str(exc))

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

    def install(self) -> None:
        config = self._current_config()
        self._run("Installing", lambda: self.manager.install(config))

    def uninstall(self) -> None:
        if not messagebox.askyesno("Uninstall ALLIN1", "Remove ALLIN1 files and restore its game changes?"):
            return
        config = self._current_config()
        self._run("Uninstalling", lambda: self.manager.uninstall(config))

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
