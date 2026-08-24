"""Focused launcher panel for the standalone ALLIN1 SDK lifecycle."""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from allin1.assistant_manager import (
    ASSISTANT_PROFILES,
    ASSISTANT_SOURCES,
    CAPABILITY_JSON_SCHEMA,
    CAPABILITY_THINKING_QWEN,
    CAPABILITY_THINKING_REASONING,
    CAPABILITY_THINKING_TEMPLATE,
    LOCAL_LLAMA_CAPABILITIES,
    AssistantConfig,
    AssistantSource,
    assess_assistant_hardware,
    default_assistant_root,
    install_assistant_archive,
    install_qwen_source,
    read_assistant_status,
    save_assistant_config,
    uninstall_assistant,
)
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


_ASSISTANT_MODE_LABELS = {
    "disabled": "Disabled",
    "managed_local": "Managed local model pack",
    "custom_local": "Existing local GGUF model",
    "compatible_api": "Compatible model API",
}
_ASSISTANT_MODE_KEYS = {label: key for key, label in _ASSISTANT_MODE_LABELS.items()}
_PROVIDER_STYLE_CAPABILITIES = {
    "Qwen chat-template control": CAPABILITY_THINKING_TEMPLATE,
    "Alibaba Qwen API control": CAPABILITY_THINKING_QWEN,
    "Reasoning-effort control": CAPABILITY_THINKING_REASONING,
}
_PROVIDER_STYLE_LABELS = {
    capability: label for label, capability in _PROVIDER_STYLE_CAPABILITIES.items()
}


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
        self.assistant_root = default_assistant_root()
        self.release: SdkRelease | None = None
        self.assistant_sources: dict[str, AssistantSource] = {
            item.profile: item for item in ASSISTANT_SOURCES
        }
        self.busy = False
        self.installed_text = tk.StringVar()
        self.latest_text = tk.StringVar(value="Checking the public SDK release…")
        self.detail_text = tk.StringVar(
            value="The SDK is optional and never changes either GTA V installation."
        )
        self.progress_text = tk.StringVar(value="")
        self.assistant_installed_text = tk.StringVar()
        self.assistant_release_text = tk.StringVar(
            value="Qwen is downloaded separately from its official upstream source."
        )
        self.assistant_detail_text = tk.StringVar(
            value="The assistant is optional and disabled by default."
        )
        self.assistant_progress_text = tk.StringVar(value="")
        self.assistant_hardware_text = tk.StringVar(
            value="Run the hardware check before installing a managed model pack."
        )
        self.assistant_mode = tk.StringVar(value=_ASSISTANT_MODE_LABELS["disabled"])
        self.assistant_workflow = tk.StringVar(value="installer")
        self.assistant_profile = tk.StringVar(value="recommended")
        self.assistant_endpoint = tk.StringVar(value="http://127.0.0.1:8080/v1")
        self.assistant_model_name = tk.StringVar()
        self.assistant_api_key_env = tk.StringVar()
        self.assistant_runtime_path = tk.StringVar()
        self.assistant_model_path = tk.StringVar()
        self.assistant_context = tk.StringVar(value="8192")
        self.assistant_temperature = tk.StringVar(value="0.1")
        self.assistant_provider_style = tk.StringVar(value="Qwen chat-template control")
        self.assistant_thinking = tk.StringVar(value="Disabled")
        self.assistant_llama_revision = tk.StringVar()
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

        tabs = ttk.Notebook(body)
        tabs.pack(fill="both", expand=True)
        sdk_body = ttk.Frame(tabs, padding=(12, 14))
        assistant_body = ttk.Frame(tabs, padding=(12, 14))
        tabs.add(sdk_body, text="SDK application")
        tabs.add(assistant_body, text="Optional assistant")

        status = ttk.LabelFrame(sdk_body, text="Installation", padding=14)
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

        self.progress = ttk.Progressbar(sdk_body, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(18, 4))
        ttk.Label(
            sdk_body, textvariable=self.progress_text, foreground="#52635c",
        ).pack(anchor="w")
        ttk.Label(
            sdk_body, textvariable=self.detail_text, wraplength=650, justify="left",
        ).pack(anchor="w", fill="x", pady=(12, 18))

        primary = ttk.Frame(sdk_body)
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

        secondary = ttk.Frame(sdk_body)
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

        self._build_assistant(assistant_body)

    def _build_assistant(self, body: ttk.Frame) -> None:
        intro = (
            "Optional, local-first help for package installation and diagnostics. "
            "It is disabled by default, never runs in GTA V, and can be removed "
            "without removing the SDK. A dedicated GPU is not required."
        )
        ttk.Label(body, text=intro, wraplength=680, justify="left").pack(
            anchor="w", fill="x", pady=(0, 10),
        )

        status = ttk.LabelFrame(body, text="Managed model pack", padding=12)
        status.pack(fill="x")
        ttk.Label(
            status, textvariable=self.assistant_installed_text,
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")
        ttk.Label(status, textvariable=self.assistant_release_text).pack(
            anchor="w", pady=(4, 0),
        )
        ttk.Label(
            status, text=str(self.assistant_root), foreground="#52635c",
            wraplength=650, justify="left",
        ).pack(anchor="w", pady=(5, 0))

        hardware = ttk.Frame(status)
        hardware.pack(fill="x", pady=(10, 0))
        ttk.Label(hardware, text="Model size").pack(side="left")
        self.assistant_profile_box = ttk.Combobox(
            hardware, textvariable=self.assistant_profile,
            values=ASSISTANT_PROFILES, state="readonly", width=15,
        )
        self.assistant_profile_box.pack(side="left", padx=(8, 8))
        self.assistant_profile_box.bind(
            "<<ComboboxSelected>>", lambda _event: self.check_assistant_hardware(),
        )
        self.assistant_hardware_button = ttk.Button(
            hardware, text="Check this PC", command=self.check_assistant_hardware,
        )
        self.assistant_hardware_button.pack(side="left")
        ttk.Label(
            status, textvariable=self.assistant_hardware_text,
            foreground="#52635c", wraplength=650, justify="left",
        ).pack(anchor="w", fill="x", pady=(6, 0))

        self.assistant_progress = ttk.Progressbar(
            body, mode="determinate", maximum=100,
        )
        self.assistant_progress.pack(fill="x", pady=(12, 3))
        ttk.Label(
            body, textvariable=self.assistant_progress_text, foreground="#52635c",
        ).pack(anchor="w")
        ttk.Label(
            body, textvariable=self.assistant_detail_text, foreground="#52635c",
            wraplength=680, justify="left",
        ).pack(anchor="w", fill="x", pady=(4, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(10, 12))
        self.assistant_install_button = ttk.Button(
            actions, text="Install selected Qwen model", style="Accent.TButton",
            command=self.install_assistant_latest,
        )
        self.assistant_install_button.pack(side="left")
        self.assistant_package_button = ttk.Button(
            actions, text="Install from package…",
            command=self.install_assistant_package,
        )
        self.assistant_package_button.pack(side="left", padx=(8, 0))
        self.assistant_remove_button = ttk.Button(
            actions, text="Uninstall pack…", command=self.remove_assistant,
        )
        self.assistant_remove_button.pack(side="right")

        configuration = ttk.LabelFrame(body, text="Assistant configuration", padding=12)
        configuration.pack(fill="x")
        configuration.columnconfigure(1, weight=1)
        ttk.Label(configuration, text="Mode").grid(row=0, column=0, sticky="w")
        self.assistant_mode_box = ttk.Combobox(
            configuration, textvariable=self.assistant_mode,
            values=tuple(_ASSISTANT_MODE_LABELS.values()), state="readonly", width=26,
        )
        self.assistant_mode_box.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.assistant_mode_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._assistant_mode_changed(),
        )
        ttk.Label(configuration, text="Workflow").grid(
            row=1, column=0, sticky="w", pady=(6, 0),
        )
        self.assistant_workflow_box = ttk.Combobox(
            configuration, textvariable=self.assistant_workflow,
            values=("installer", "diagnostic"), state="readonly", width=22,
        )
        self.assistant_workflow_box.grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(6, 0),
        )
        self.assistant_endpoint_entry = self._assistant_entry(
            configuration, 2, "Compatible API URL", self.assistant_endpoint,
        )
        self.assistant_model_name_entry = self._assistant_entry(
            configuration, 3, "API model name", self.assistant_model_name,
        )
        self.assistant_api_key_entry = self._assistant_entry(
            configuration, 4, "API key environment variable", self.assistant_api_key_env,
        )
        (
            self.assistant_runtime_entry,
            self.assistant_runtime_browse_button,
        ) = self._assistant_path_row(
            configuration, 5, "Custom runtime", self.assistant_runtime_path,
            self.browse_assistant_runtime,
        )
        (
            self.assistant_model_entry,
            self.assistant_model_browse_button,
        ) = self._assistant_path_row(
            configuration, 6, "Custom GGUF model", self.assistant_model_path,
            self.browse_assistant_model,
        )
        provider = ttk.Frame(configuration)
        provider.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(provider, text="Provider protocol").pack(side="left")
        self.assistant_provider_style_box = ttk.Combobox(
            provider, textvariable=self.assistant_provider_style,
            values=tuple(_PROVIDER_STYLE_CAPABILITIES), state="readonly", width=27,
        )
        self.assistant_provider_style_box.pack(side="left", padx=(8, 14))
        ttk.Label(provider, text="Thinking").pack(side="left")
        self.assistant_thinking_box = ttk.Combobox(
            provider, textvariable=self.assistant_thinking,
            values=("Disabled", "Enabled"), state="readonly", width=10,
        )
        self.assistant_thinking_box.pack(side="left", padx=(8, 0))
        ttk.Label(provider, text="llama.cpp rev").pack(side="left", padx=(14, 0))
        self.assistant_llama_revision_entry = ttk.Entry(
            provider, textvariable=self.assistant_llama_revision, width=12,
        )
        self.assistant_llama_revision_entry.pack(side="left", padx=(8, 0))
        tuning = ttk.Frame(configuration)
        tuning.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(tuning, text="Context tokens").pack(side="left")
        ttk.Entry(tuning, textvariable=self.assistant_context, width=9).pack(
            side="left", padx=(8, 18),
        )
        ttk.Label(tuning, text="Temperature").pack(side="left")
        ttk.Entry(tuning, textvariable=self.assistant_temperature, width=7).pack(
            side="left", padx=(8, 0),
        )
        self.assistant_save_button = ttk.Button(
            tuning, text="Save settings", command=self.save_assistant_settings,
        )
        self.assistant_save_button.pack(side="right")
        ttk.Label(
            configuration,
            text=("Secrets are never stored here. For an authenticated API, enter only "
                  "the name of an environment variable containing the key."),
            foreground="#52635c", wraplength=650, justify="left",
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(8, 0))

    @staticmethod
    def _assistant_entry(
        parent: ttk.Frame, row: int, label: str, variable: tk.StringVar,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(6, 0))
        return entry

    @staticmethod
    def _assistant_path_row(
        parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command,
    ) -> tuple[ttk.Entry, ttk.Button]:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(6, 0))
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=(6, 0))
        holder.columnconfigure(0, weight=1)
        entry = ttk.Entry(holder, textvariable=variable)
        entry.grid(row=0, column=0, sticky="ew")
        button = ttk.Button(holder, text="Browse…", command=command)
        button.grid(row=0, column=1, padx=(6, 0))
        return entry, button

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
        self._refresh_assistant()

    def _refresh_assistant(self) -> None:
        status = read_assistant_status(self.assistant_root)
        config = status.config
        self.assistant_mode.set(_ASSISTANT_MODE_LABELS[config.mode])
        self.assistant_workflow.set(config.workflow)
        if config.profile in ASSISTANT_PROFILES:
            self.assistant_profile.set(config.profile)
        self.assistant_endpoint.set(config.endpoint)
        self.assistant_model_name.set(config.model_name)
        self.assistant_api_key_env.set(config.api_key_env)
        self.assistant_runtime_path.set(config.runtime_path)
        self.assistant_model_path.set(config.model_path)
        self.assistant_context.set(str(config.context_tokens))
        self.assistant_temperature.set(str(config.temperature))
        thinking_control = next(
            (item for item in config.capabilities
             if item in _PROVIDER_STYLE_LABELS),
            CAPABILITY_THINKING_TEMPLATE,
        )
        self.assistant_provider_style.set(
            _PROVIDER_STYLE_LABELS[thinking_control]
        )
        self.assistant_thinking.set(
            "Enabled" if config.thinking == "enabled" else "Disabled"
        )
        self.assistant_llama_revision.set(config.llama_cpp_revision)
        if status.package is not None and status.healthy:
            self.assistant_installed_text.set(
                f"Installed: {status.package.display_name} {status.package.version} "
                f"({status.package.profile})"
            )
        elif status.installed:
            self.assistant_installed_text.set("Managed assistant pack needs repair")
        else:
            self.assistant_installed_text.set("No managed model pack is installed")
        mode = config.mode.replace("_", " ")
        self.assistant_detail_text.set(
            f"Mode: {mode}. {status.detail}"
        )
        self.assistant_remove_button.configure(
            state="normal" if status.installed and not self.busy else "disabled",
        )
        self._assistant_mode_changed()

    def _set_busy(self, busy: bool, label: str = "") -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.install_button.configure(state=state)
        self.package_button.configure(state=state)
        self.update_button.configure(state=state)
        self.open_button.configure(state=state)
        self.repair_button.configure(state=state)
        self.remove_button.configure(state=state)
        self.assistant_install_button.configure(state=state)
        self.assistant_package_button.configure(state=state)
        self.assistant_hardware_button.configure(state=state)
        self.assistant_save_button.configure(state=state)
        self.assistant_profile_box.configure(state="disabled" if busy else "readonly")
        self.assistant_mode_box.configure(state="disabled" if busy else "readonly")
        self.assistant_workflow_box.configure(state="disabled" if busy else "readonly")
        self.assistant_provider_style_box.configure(
            state="disabled" if busy else "readonly"
        )
        self.assistant_thinking_box.configure(
            state="disabled" if busy else "readonly"
        )
        if busy:
            self.assistant_remove_button.configure(state="disabled")
        self._assistant_mode_changed()
        self.progress_text.set(label)
        if not busy:
            self.progress.configure(value=0)
            self.assistant_progress.configure(value=0)
            self.assistant_progress_text.set("")
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
        self.assistant_detail_text.set(str(error))
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
        labels = ", ".join(
            f"{profile}: {source.display_name} ({source.model.size / (1024 ** 3):.1f} GB)"
            for profile, source in sorted(self.assistant_sources.items())
        )
        self.after(0, lambda value=labels: self.assistant_release_text.set(
            "Verified upstream choices — " + value
        ))
        return release

    def check_for_updates(self) -> None:
        self.latest_text.set("Checking the public SDK release…")
        self.assistant_release_text.set("Refreshing assistant source information…")
        self._run_background(
            "Checking SDK releases", self._check_release, quiet=True,
        )

    def _progress(self, label: str, current: int, total: int) -> None:
        percentage = int(current * 100 / total) if total > 0 else 0
        self.after(0, lambda: (
            self.progress.configure(value=max(0, min(100, percentage))),
            self.progress_text.set(f"{label} — {percentage}%"),
        ))

    def _assistant_progress(self, label: str, current: int, total: int) -> None:
        percentage = int(current * 100 / total) if total > 0 else 0
        self.after(0, lambda: (
            self.assistant_progress.configure(value=max(0, min(100, percentage))),
            self.assistant_progress_text.set(f"{label} — {percentage}%"),
        ))

    def check_assistant_hardware(self):
        profile = self.assistant_profile.get().casefold()
        source = self.assistant_sources.get(profile)
        report = assess_assistant_hardware(
            profile, self.assistant_root,
            archive_size=source.total_download_bytes if source else 0,
            unpacked_size=(source.model.size + source.runtime.size) if source else 0,
        )
        snapshot = report.snapshot
        detected = (
            f" Detected: {snapshot.total_ram_bytes / (1024 ** 3):.1f} GB RAM, "
            f"{snapshot.logical_cpus or 'unknown'} CPU threads, "
            f"{snapshot.free_disk_bytes / (1024 ** 3):.1f} GB free."
        )
        self.assistant_hardware_text.set(report.summary + detected)
        return report

    def _approve_assistant_hardware(self) -> bool:
        report = self.check_assistant_hardware()
        if not report.compatible:
            messagebox.showerror(
                "Assistant hardware check failed", report.summary, parent=self,
            )
            return False
        if report.warnings:
            return messagebox.askyesno(
                "Assistant hardware caution",
                report.summary + "\n\nContinue with this model pack?",
                parent=self,
            )
        return True

    def install_assistant_latest(self) -> None:
        profile = self.assistant_profile.get().casefold()
        source = self.assistant_sources.get(profile)
        if source is None:
            messagebox.showerror(
                "Assistant source unavailable",
                f"No verified upstream source is configured for the {profile} profile.",
                parent=self,
            )
            return
        if not self._approve_assistant_hardware():
            return
        self._run_background(
            "Installing optional assistant",
            lambda: install_qwen_source(
                profile, self.assistant_root, source=source,
                progress=self._assistant_progress,
            ),
        )

    def install_assistant_package(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self, title="Install ALLIN1 assistant model pack",
            filetypes=(("ALLIN1 assistant package", "*.zip"),),
        )
        if not selected:
            return
        archive = Path(selected)
        # The exact package requirements are validated again after its manifest
        # and payload checksums have been inspected in the worker.
        if not self._approve_assistant_hardware():
            return
        self._run_background(
            "Installing assistant package",
            lambda: install_assistant_archive(archive, self.assistant_root),
        )

    def remove_assistant(self) -> None:
        if not messagebox.askyesno(
            "Uninstall managed assistant",
            "Remove the managed runtime and model pack? Assistant settings and any "
            "user-supplied model files remain untouched.",
            parent=self,
        ):
            return
        self._run_background(
            "Uninstalling optional assistant",
            lambda: uninstall_assistant(self.assistant_root),
        )

    def browse_assistant_runtime(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self, title="Select a local assistant runtime",
            filetypes=(("Windows executable", "*.exe"),),
        )
        if selected:
            self.assistant_runtime_path.set(selected)

    def browse_assistant_model(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self, title="Select a GGUF model",
            filetypes=(("GGUF model", "*.gguf"),),
        )
        if selected:
            self.assistant_model_path.set(selected)

    def _assistant_mode_changed(self) -> None:
        if not hasattr(self, "assistant_endpoint_entry"):
            return
        mode = _ASSISTANT_MODE_KEYS.get(self.assistant_mode.get(), "disabled")
        api_state = "normal" if mode == "compatible_api" and not self.busy else "disabled"
        local_state = "normal" if mode == "custom_local" and not self.busy else "disabled"
        for widget in (
            self.assistant_endpoint_entry,
            self.assistant_model_name_entry,
            self.assistant_api_key_entry,
        ):
            widget.configure(state=api_state)
        for widget in (
            self.assistant_runtime_entry, self.assistant_model_entry,
            self.assistant_runtime_browse_button, self.assistant_model_browse_button,
        ):
            widget.configure(state=local_state)
        provider_state = (
            "readonly" if mode == "compatible_api" and not self.busy else "disabled"
        )
        thinking_state = (
            "readonly" if mode != "disabled" and not self.busy else "disabled"
        )
        revision_state = (
            "normal" if mode in {"custom_local", "compatible_api"} and not self.busy
            else "disabled"
        )
        self.assistant_provider_style_box.configure(state=provider_state)
        self.assistant_thinking_box.configure(state=thinking_state)
        self.assistant_llama_revision_entry.configure(state=revision_state)

    def save_assistant_settings(self) -> None:
        mode = _ASSISTANT_MODE_KEYS.get(self.assistant_mode.get(), "disabled")
        try:
            if mode in {"managed_local", "custom_local"}:
                capabilities = LOCAL_LLAMA_CAPABILITIES
                thinking = self.assistant_thinking.get().casefold()
            elif mode == "compatible_api":
                thinking_control = _PROVIDER_STYLE_CAPABILITIES.get(
                    self.assistant_provider_style.get(), "",
                )
                if not thinking_control:
                    raise ValueError("Select a supported compatible-API provider protocol")
                capabilities = (CAPABILITY_JSON_SCHEMA, thinking_control)
                thinking = self.assistant_thinking.get().casefold()
            else:
                capabilities = ()
                thinking = "provider_default"
            config = AssistantConfig(
                mode=mode,
                workflow=self.assistant_workflow.get().casefold(),
                profile=(
                    self.assistant_profile.get().casefold()
                    if mode in {"disabled", "managed_local"} else "custom"
                ),
                endpoint=self.assistant_endpoint.get().strip(),
                model_name=self.assistant_model_name.get().strip(),
                api_key_env=self.assistant_api_key_env.get().strip(),
                runtime_path=self.assistant_runtime_path.get().strip(),
                model_path=self.assistant_model_path.get().strip(),
                context_tokens=int(self.assistant_context.get()),
                temperature=float(self.assistant_temperature.get()),
                capabilities=capabilities, thinking=thinking,
                llama_cpp_revision=self.assistant_llama_revision.get().strip(),
            )
            save_assistant_config(config, self.assistant_root)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror(
                "Could not save assistant settings", str(exc), parent=self,
            )
            return
        self._refresh_assistant()
        messagebox.showinfo(
            "Assistant settings",
            "Assistant settings were saved. The component remains separate from GTA V "
            "and only starts when an SDK workflow requests it.",
            parent=self,
        )

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
