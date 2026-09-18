# ALLIN1 Launcher React/Tauri development shell

Target **0.6.6**, Tauri **v2**. `manager.bat` / `allin1-gui` forward to the
native desktop. For source use, set `ALLIN1_LAUNCHER_EXECUTABLE` to a complete
candidate shell or put `allin1-launcher-desktop.exe` on PATH; missing native
desktop errors rather than falling back. Reinstall the editable Python package
after upgrading. Setup, checks, and native prerequisites are canonical in the
[development guide](../docs/development.md).

The native broker owns the persistent Python service, explicit native dialogs,
single-instance handoff, and close guards. The WebView cannot choose arbitrary
processes or gain raw shell/file-system authority. The debug host uses
`.venv/Scripts/python.exe`. Build a development candidate with:

```powershell
.venv/Scripts/python.exe tools/launcher_desktop_candidate.py
```

Use `--pnpm <path>` / `--cargo <path>` if needed; Node must be on PATH and
frontend dependencies installed. `--service-only` builds/tests only the shared
runtime; `--sdk <path>` selects the renderer checkout (default: sibling
`ALLIN1-SDK`). The builder uses pinned
official CPython (not PyInstaller), shared service/preview modules without
Tkinter/Tcl/Tk, and hash-bound resources. Each build writes a complete,
checksum-verified portable candidate to
`build/launcher-candidates/<build-id>/app/`; never distribute its shell without
the sibling `runtime/` and `resources/` directories. The shell compiles with
`tauri/custom-protocol`; its read-only `--verify-embedded-frontend` probe checks
embedded assets/build ID against the production frontend without a WebView. It
is not native-window acceptance.

The executable smoke uses a disposable spaced path, fresh preferences, an
unrelated working directory, system-only PATH, and no game-write/launch
authority. It exercises workspaces, conflict-preserving preference import,
saved preferences, catalog/history reads, restart preservation, and invalid
requests. It does **not** launch the GUI or GTA. Resource inventory rejects
missing/extra/changed payloads before startup, and the shell build ID rejects a
service from another build.

Unsigned local candidates are **not release-qualified**: service/resource
evidence is separate from native dialogs, installer lifecycle, and live
acceptance. They may use dirty development source; release requires reviewed,
clean source and the [milestone gates](../docs/release-0.6.6.md#mandatory-066-full-release-milestone).

Use the [React harness](../docs/react-release-harness.md) for disposable
real-service tests. An interactive development session is not a sandbox; it can
apply reviewed operations to selected real paths. Never use real GTA files in
automated write tests.

See [release scope](../docs/release-0.6.6.md) and
[Launcher manual](../docs/launcher-guide.md) for current workspace limits.
