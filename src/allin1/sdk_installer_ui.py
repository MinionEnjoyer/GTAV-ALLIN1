"""Focused launcher panel for the standalone ALLIN1 SDK lifecycle."""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from allin1.sdk_manager import (
    SDK_REPOSITORY_URL,
    SdkRelease,
    default_sdk_root,
    fetch_latest_sdk_release,
    install_sdk_archive,
    install_sdk_release,
    read_sdk_status,
    sdk_launch_error_message,
    sdk_update_available,
    uninstall_sdk,
)


class SdkManagerDialog(ttk.Frame):
    """Install and maintain the SDK inside the launcher workspace shell."""

    def __init__(
        self, parent, *, install_root: Path | None = None,
        embedded: bool = False,
    ) -> None:
        self._window: tk.Toplevel | None = None
        host = parent
        if not embedded:
            self._window = tk.Toplevel(parent)
            self._window.title("ALLIN1 SDK — Developer Tools")
            self._window.geometry("760x520")
            self._window.minsize(640, 440)
            self._window.transient(parent.winfo_toplevel())
            host = self._window
        super().__init__(host)
        self.pack(fill="both", expand=True)
        self.install_root = (install_root or default_sdk_root()).resolve()
        self.release: SdkRelease | None = None
        self.busy = False
        self.installed_text = tk.StringVar()
        self.latest_text = tk.StringVar(value="Checking the public SDK release…")
        self.detail_text = tk.StringVar(
            value="The SDK is optional and never changes either GTA V installation."
        )
        self.progress_text = tk.StringVar(value="")
        self._build()
        self._refresh_local()
        self._run_background("Checking SDK releases", self._check_release, quiet=True)

    def _build(self) -> None:
        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="ALLIN1 SDK", font=("Segoe UI Semibold", 19),
            foreground="#1f7f42",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=("Developer workspace for add-on linking, package auditing, native assets, "
                  "RPF inspection, and vehicle metadata."),
            wraplength=650, justify="left",
        ).pack(anchor="w", fill="x", pady=(4, 18))

        status = ttk.LabelFrame(body, text="Installation", padding=14)
        status.pack(fill="x")
        ttk.Label(
            status, textvariable=self.installed_text,
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")
        ttk.Label(status, textvariable=self.latest_text).pack(anchor="w", pady=(5, 0))
        ttk.Label(
            status, text=str(self.install_root), foreground="#52635c",
            wraplength=630, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(18, 4))
        ttk.Label(body, textvariable=self.progress_text, foreground="#52635c").pack(anchor="w")
        ttk.Label(
            body, textvariable=self.detail_text, wraplength=650, justify="left",
        ).pack(anchor="w", fill="x", pady=(12, 18))

        primary = ttk.Frame(body)
        primary.pack(fill="x")
        self.install_button = ttk.Button(
            primary, text="Install SDK", style="Accent.TButton", command=self.install_latest,
        )
        self.install_button.pack(side="left")
        self.open_button = ttk.Button(primary, text="Open SDK", command=self.open_sdk)
        self.open_button.pack(side="left", padx=(8, 0))
        self.repair_button = ttk.Button(primary, text="Repair", command=self.repair)
        self.repair_button.pack(side="left", padx=(8, 0))
        self.remove_button = ttk.Button(primary, text="Uninstall…", command=self.remove)
        self.remove_button.pack(side="right")

        secondary = ttk.Frame(body)
        secondary.pack(fill="x", pady=(12, 0))
        self.package_button = ttk.Button(
            secondary, text="Install from package…", command=self.install_package,
        )
        self.package_button.pack(side="left")
        self.update_button = ttk.Button(
            secondary, text="Check for updates", command=self.check_for_updates,
        )
        self.update_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            secondary, text="View public repository",
            command=lambda: webbrowser.open(SDK_REPOSITORY_URL),
        ).pack(side="left", padx=(8, 0))
        if self._window is not None:
            ttk.Button(
                secondary, text="Close", command=self._window.destroy,
            ).pack(side="right")

    def _refresh_local(self) -> None:
        status = read_sdk_status(self.install_root)
        if status.healthy:
            self.installed_text.set(f"Installed: ALLIN1 SDK {status.version}")
            self.detail_text.set("The managed SDK installation passed its local integrity checks.")
        elif status.installed:
            self.installed_text.set("Installed SDK needs repair")
            self.detail_text.set(status.detail)
        else:
            self.installed_text.set("SDK is not installed")
        self.open_button.configure(state="normal" if status.healthy else "disabled")
        self.repair_button.configure(state="normal" if status.installed else "disabled")
        self.remove_button.configure(state="normal" if status.installed else "disabled")
        if self.release:
            available = sdk_update_available(status, self.release)
            self.install_button.configure(
                text=("Update SDK" if status.installed and available else
                      "Reinstall SDK" if status.installed else "Install SDK"),
            )

    def _set_busy(self, busy: bool, label: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.install_button.configure(state=state)
        self.package_button.configure(state=state)
        self.update_button.configure(state=state)
        self.open_button.configure(state=state)
        self.repair_button.configure(state=state)
        self.remove_button.configure(state=state)
        self.progress_text.set(label)
        if not busy:
            self.progress.configure(value=0)
            self._refresh_local()

    def _run_background(self, label: str, operation, *, quiet: bool = False) -> None:
        if self.busy:
            return
        self._set_busy(True, label + "…")

        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:  # UI boundary: keep network/filesystem failures actionable.
                self.after(0, lambda error=exc: self._finish_error(label, error, quiet))
            else:
                self.after(0, lambda value=result: self._finish_success(label, value, quiet))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_success(self, label: str, _result, quiet: bool) -> None:
        self._set_busy(False)
        if not quiet:
            messagebox.showinfo("ALLIN1 SDK", f"{label} completed successfully.", parent=self)

    def _finish_error(self, label: str, error: Exception, quiet: bool) -> None:
        self._set_busy(False)
        self.detail_text.set(str(error))
        if quiet:
            self.latest_text.set(f"Release check unavailable: {error}")
        else:
            messagebox.showerror(f"{label} failed", str(error), parent=self)

    def _check_release(self) -> SdkRelease:
        release = fetch_latest_sdk_release()
        self.release = release
        self.after(0, lambda: self.latest_text.set(
            f"Latest public release: {release.version} — {release.name}"
        ))
        return release

    def check_for_updates(self) -> None:
        self.latest_text.set("Checking the public SDK release…")
        self._run_background(
            "Checking SDK releases", self._check_release, quiet=True,
        )

    def _progress(self, label: str, current: int, total: int) -> None:
        percentage = int(current * 100 / total) if total > 0 else 0
        self.after(0, lambda: (
            self.progress.configure(value=max(0, min(100, percentage))),
            self.progress_text.set(f"{label} — {percentage}%"),
        ))

    def install_latest(self) -> None:
        def operation():
            release = self.release or fetch_latest_sdk_release()
            self.release = release
            return install_sdk_release(release, self.install_root, progress=self._progress)

        self._run_background("Installing ALLIN1 SDK", operation)

    def repair(self) -> None:
        self.install_latest()

    def install_package(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self, title="Install ALLIN1 SDK package",
            filetypes=(("ALLIN1 SDK release", "*.zip"),),
        )
        if selected:
            self._run_background(
                "Installing SDK package",
                lambda: install_sdk_archive(Path(selected), self.install_root),
            )

    def open_sdk(self) -> None:
        status = read_sdk_status(self.install_root)
        if not status.healthy or status.executable is None:
            messagebox.showerror("ALLIN1 SDK", status.detail, parent=self)
            return
        options: dict[str, object] = {}
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen([str(status.executable)], cwd=status.root, **options)
        except OSError as exc:
            detail = sdk_launch_error_message(exc)
            self.detail_text.set(detail)
            messagebox.showerror("Could not open ALLIN1 SDK", detail, parent=self)

    def remove(self) -> None:
        if not messagebox.askyesno(
            "Uninstall ALLIN1 SDK",
            "Remove the managed SDK application? User-created projects are not stored here.",
            parent=self,
        ):
            return
        self._run_background(
            "Uninstalling ALLIN1 SDK", lambda: uninstall_sdk(self.install_root),
        )
