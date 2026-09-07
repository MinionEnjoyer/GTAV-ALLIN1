# ALLIN1 Launcher React/Tauri development shell

Target **0.6.5**, Tauri **v2**. Standalone development candidates are available;
native installer/lifecycle acceptance is not complete.
`manager.bat` / `allin1-gui` now forward to the native desktop. For source use,
set `ALLIN1_LAUNCHER_EXECUTABLE` to a complete candidate's shell, or place
`allin1-launcher-desktop.exe` on PATH. Missing native desktop produces an error,
not a fallback interface. Reinstall the editable Python package after upgrading.

From the repository root, install the editable Python project into `.venv`,
install the locked frontend dependencies and run `pnpm --dir desktop tauri dev`.
See [development setup](../docs/development.md) for prerequisites and commands.

The native broker owns the persistent Python service, explicit native dialogs,
single-instance handoff and close guards. The WebView cannot choose arbitrary
processes or acquire raw shell/file-system authority. The current debug host
uses `.venv/Scripts/python.exe`. The candidate builder freezes the service
without Tkinter/Tcl/Tk, stages hash-bound resources, and builds the native shell:

```powershell
.venv/Scripts/python.exe tools/launcher_desktop_candidate.py
```

Use `--pnpm <path>` / `--cargo <path>` if those tools are not on PATH. Node must
be on PATH and frontend dependencies must already be installed. `--service-only`
builds/tests only the frozen service. PyInstaller is a build-time dependency;
end users do not need Python. Outputs go into a new
`build/launcher-candidates/<build-id>/app/` directory on each run. Never distribute
the shell alone: it requires the sibling `sidecar/` and `resources/` directories.
Full builds also produce a complete, checksum-verified candidate portable ZIP.
The shell must compile with `tauri/custom-protocol`; its read-only
`--verify-embedded-frontend` probe checks embedded HTML/JavaScript/CSS and the
compiled build ID without creating a WebView. The report compares its asset
inventory to the production frontend. This is not native-window acceptance.

The executable smoke relocates the application into a disposable path with
spaces, with fresh preferences, an unrelated working directory, a system-only
PATH and no game-write/launch authority. It tests every
workspace, imports previous preferences without overwriting conflicts, saves
preinstall content and independent assistant preferences, inspects package/example
catalogs, reads structured action history, verifies restart preservation and rejects
invalid requests. It does **not** launch the GUI or GTA. The embedded resource
inventory rejects missing/extra/changed payloads before service startup (also
tested against the real frozen service); the shell
also supplies its build ID so a service from another build is rejected.

These unsigned local candidates are **not release-qualified**. Reports keep
service smoke/resource integrity separate from untested native dialogs,
installer lifecycle and live acceptance. They may be built from a dirty checkout
for development; final release still requires reviewed, clean source and the
full [milestone gates](../docs/release-0.6.5.md#mandatory-065-full-release-milestone).

Use the [migration harness](../docs/react-release-harness.md) for disposable
real-service tests. An interactive development session is not a sandbox and can
apply reviewed operations to selected real paths. Do not use real GTA files in
automated write tests.

See [release scope](../docs/release-0.6.5.md) and
[Launcher manual](../docs/launcher-guide.md) for current workspace limits.
