# Shared Python runtime packaging (developer-only)

The successful prototype is now the standard packaging path for Launcher 0.6.6.
The builder creates candidates only; publishing remains an explicit owner action.

Build on Windows with `.venv/Scripts/python.exe tools/launcher_desktop_candidate.py`.
Outputs are immutable, uniquely named directories under `build/launcher-candidates`.
Do not overlay the package on a PyInstaller installation; use a fresh folder.

The native Tauri shell starts the official, unmodified CPython 3.13.15 embeddable
interpreter. Service and preview jobs use separate processes with one shared
runtime. Weapons, custom weapons, vehicles, gear, and throwable Blender pipelines
are retained. Blender remains an external dependency; users do not install Python.

`tools/shared-runtime-lock.json` pins the official CPython archive and PyPI wheels
by SHA256. Python provenance: https://www.python.org/ftp/python/3.13.15/windows-3.13.15.json
The SDK renderer's transitive module closure is bundled, not the SDK application.
Upstream licenses are retained. No pip or Tk runtime is installed or bundled.
Neither `WeaponPreview.exe` nor `ALLIN1-Launcher-Sidecar.exe` is in the package.

The `_pth` configuration and `-I -B` flags exclude user/site/environment imports
and bytecode writes. The bootstrap checks the exact runtime tree before application
imports. Existing resource identity, confirmation, and process-isolation contracts
remain enforced. Checksums detect damage/mixed builds, not publisher authenticity.
The native frontend probe records which service runtime was compiled into the shell.

Service tests include relocated paths with spaces, extended Windows paths,
confirmation and persistence, wrong build IDs, corrupted/missing/extra resources
and runtime modules, and hostile PYTHONPATH/PYTHONHOME/current-directory imports.
`tools/shared_runtime_preview_smoke.py APP JOB...` replays selected jobs into a
new diagnostic folder without installing content, changing cached previews, or
starting GTA. Test jobs must reference models currently present on the machine.

This packaging change does not itself establish an antivirus verdict. Scan the
exact final ZIP; do not infer that it is clean from a component-only result.
Runtime modules are readable in this layout; obtain approval before submitting
unpublished packages to external scanning services.
