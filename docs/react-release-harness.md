# React release and Tkinter-retirement harness

The release targets are Launcher/SDK **0.6.5**. Other products are outside this
harness. It neither installs into a real game directory nor launches GTA.

Run from the Launcher checkout after installing locked desktop dependencies:

```powershell
.venv/Scripts/python.exe tools/react_release_harness.py --product both --sdk-source ../ALLIN1-SDK
```

Use `--pnpm <absolute-path>`, `--python <absolute-path>`, or
`--cargo <absolute-path>` when needed; Node must be on PATH. SDK tests use real
native RPF/runtime workflows and the pinned Blender path (or
`ALLIN1_BLENDER_EXECUTABLE`). Missing prerequisites, disabled native tests, and
skips fail qualification. Only this developer invocation uses the sibling
checkout; shipped applications do not.

Each run writes fresh Vitest JSON, pytest XML, logs, source-before/after
inventories, tool/dependency identities, and a versioned report under
`build/react-harness/<unique-run-id>/`. Exact test **file and title** must match
`desktop/module-happy-paths.json`; reconciled assertions reject missing,
duplicate, unrelated, stale, pending, todo, or skipped checks. Source drift
fails. Results are local evidence, not release approval, signed artifacts, or
live acceptance.

Rust is a separate required result: Cargo artifact events bind exact test
executables and the stable-libtest adapter rejects ignored, filtered, or missing
named outcomes. `TAURI_CONFIG` disables bundle resources for native unit tests,
is recorded with the command, and cannot qualify a package. TypeScript checking
and the production frontend build are also required. None prove packaged GUI or
clean-machine acceptance.

The default Python selection covers service/framing, containment/rollback,
managed SDK lifecycle, release evidence, SDK protocol/packaging, and extension
contract parity; documentation is checked per product. `--full-python` runs the
full suites at their existing thresholds (Launcher 91%, SDK 80%). The targeted
run is not a full-suite-coverage or full-release PASS.

## Tkinter removal sequence

Full release requires verified source/entrypoint removal and packaged
replacement; a targeted pass does not meet the [full-release
milestone](release-0.6.5.md#mandatory-065-full-release-milestone). Shared
nonvisual behavior must be UI-independent; source process/React fixtures forbid
Tk imports, network access, and non-isolated user state. Every replacement
workflow needs behavioral preservation/error tests, not merely page navigation.
Frozen artifacts must exclude Tcl/Tk and source-checkout dependencies, then be
qualified for dialogs, close/cancel/restart/handoff/preference migration and
clean Windows install, upgrade, repair, uninstall, and rollback with path and
user-data canaries. Keep package integrity and live acceptance separate.

`tools/tk_retirement.py` (SDK: `scripts/tk_retirement.py`) checks retired
adapters, imports, and GUI/build entrypoints. `--require-retirement-ready`
requires this source-only result with the automated gates; it neither deletes
files nor qualifies packaged/live behavior. Frozen payload inspection is
separate, and required skips/coverage failures still fail. Module inventories
are regression sentinels, not a complete human feature inventory; row/title
changes require review.

## Same-machine testing

Use disposable application folders and isolated user state with before/after
hashes and outside-root canaries. Report them as same-machine tests; clean-machine
and unavailable-dependency checks remain NOT TESTED. Never remove shared
WebView2/.NET/Python installations to simulate a dependency. Portable copies are
not NSIS install/upgrade/uninstall acceptance because installers can replace
registration or shortcuts. Preservation regressions use synthetic game folders:
saves, configuration, preferences, unknown legacy files, and unrelated content
remain intact; redirected installation subtrees fail preflight. They do not
modify an installed game.
