# React release and Tkinter-retirement harness

The release targets are Launcher/SDK **0.6.4**. Suppressors Enhanced **1.2.1**,
the weapon pack bundle, GTA VR and FPV are separate products. This harness
neither installs anything into a real game directory nor launches GTA.

Run from the Launcher checkout after installing locked desktop dependencies:

```powershell
.venv/Scripts/python.exe tools/react_release_harness.py --product both --sdk-source ../ALLIN1-SDK
```

Use `--pnpm <absolute-path>`, `--python <absolute-path>` or `--cargo <absolute-path>` when needed. Node must
be on PATH. SDK tests enable real native RPF/runtime workflows and use the pinned
Blender path, or `ALLIN1_BLENDER_EXECUTABLE`. Missing prerequisites fail; disabled
native tests and skips do not qualify. Only this explicit developer invocation
depends on the sibling checkout, never the shipped applications.

Each invocation creates `build/react-harness/<unique-run-id>/` with fresh Vitest
JSON, pytest XML, full command logs, source-before/source-after inventories,
tool/dependency identities and a versioned report. Exact test **file and title**
must match `desktop/module-happy-paths.json`. Counts are reconciled against actual
assertions; missing, duplicate, unrelated, stale, pending, todo and skipped checks
fail. Changed source fails the run. These are local test results, not independent
release approval, signed artifacts or live acceptance.

Native Rust tests are a separate required result. Cargo compiler-artifact events
bind the exact test executables; the stable-libtest adapter reconciles named
outcomes and summaries and rejects ignored, filtered or missing tests. Native
unit/process tests do not establish packaged GUI or clean-machine acceptance.
The native unit invocation sets `TAURI_CONFIG` to disable bundle resources, so
unit tests do not depend on stale installer staging. That override is recorded
with the command and is never used to qualify a packaged application.
TypeScript checking and the production frontend build are also required; a
passing Vitest transformation alone does not prove that the application builds.

The default Python selection exercises the Launcher service, stdio framing,
containment, rollback, managed SDK lifecycle, release evidence validation, SDK
protocol/packaging and the shared extension-contract parity sentinel. Documentation
inventory, links and generated references are checked separately for each product.
`--full-python` runs each full Python suite with its existing coverage
threshold (Launcher 91%, SDK 80%). Independent mod release checks run separately;
generic package and weapon integration tests stay in the product suites. The default targeted run does
**not** establish full-suite coverage or a full release PASS.

## Tkinter removal sequence

This is mandatory for the full 0.6.4 release of **both** products, not a later
cleanup phase. Until source/entrypoint removal and packaged replacement are
verified, the [full-release milestone](release-0.6.4.md#mandatory-064-full-release-milestone)
is unmet even if the targeted harness passes.

1. Extract shared nonvisual behavior from Tk adapters. SDK Help topics/search
   and map recognition now live in UI-independent modules. Retired GUI imports
   are no longer supported. Source process tests forbid importing Tkinter, deny network access
   and use isolated user state. React real-Python fixtures also forbid Tk imports.
2. Complete the secondary actions below and in both parity documents; give each
   action an exact behavioral test, including preservation/error paths. Opening
   a page is not workflow parity.
3. Freeze both applications without Tcl/Tk and certify native-dialog, close,
   cancellation, crash/restart, handoff and preference migration behavior against
   those exact artifacts. Verify no Tk implementation or accidental runtime
   source-checkout dependency remains in the bundle.
4. Qualify clean Windows install, upgrade, repair, uninstall and rollback with
   missing dependencies, spaces/long paths and user-data canaries. Keep package
   integrity and live Legacy/Enhanced acceptance separate.
5. Only then switch default GUI entrypoints and remove legacy Tk modules,
   Tk-only tests and Tcl/Tk packaging inputs in one reviewed change. Keep shared
   services, CLI/API compatibility and the resulting React regression tests.

Tk source removal was explicitly approved and completed. The harness now runs
`tools/tk_retirement.py` (SDK: `scripts/tk_retirement.py`) to check retired adapter
absence, imports and GUI/build entrypoints. `--require-retirement-ready` checks
this **source-only** result along with the automated gates. It never deletes
files or claims packaged/live qualification. Frozen payload inspection remains
a separate gate; required skips and coverage failures still fail the run.

## Remaining replacement gates

| Product | Required work | Current state |
| --- | --- | --- |
| Launcher | Frozen service/resources/build identity and preference migration | Candidate builder, conflict-preserving preference import and frozen smoke implemented; native lifecycle remains unqualified |
| Launcher | Preinstall content settings; third-party catalog/details | Real React/service tests; native interaction acceptance remains |
| Launcher | Builtin/SDK-example package catalog and initial package settings | Inspector, shared SDK library, schema controls and stale/reinstall tests implemented |
| Launcher | Local Qwen provisioning, not merely an SDK handoff | Configuration, hardware check and reviewed install/remove implemented; synthetic lifecycle and adversarial containment tests; actual upstream/native acceptance remains |
| Launcher | Activity controls and manual release lookup | Copy/open-folder, retained versioned journal, readable release results and fixed official release-page navigation implemented; the old Tk interface also used manual download, not an automatic installer |
| Launcher | Process recovery and independent drafts | Bounded versioned frames, explicit reconnect without replay, uncertain-writer termination refusal and per-document stale-draft checks implemented; packaged process-tree acceptance remains |
| Both | Secondary controls, native dialogs, minimum size/high-DPI, keyboard/dirty-state recovery | Partial |
| SDK | Remaining authoring/native-route gaps in `docs/tauri-feature-parity.md` | Partial |
| Both | Clean-machine packaged lifecycle, reviewed source, unsigned-manual trust disclosure, exact artifact identity | NOT TESTED for current sources |

Module inventories are regression sentinels, not exhaustive Tkinter action
inventories. Removing a row or changing a test title requires review; this runner
cannot prove that a human supplied a complete feature inventory.

## Same-machine testing

A test VM is not currently available. Use disposable application folders and
isolated user state with before/after hashes and outside-root canaries. Report
these as same-machine tests; keep clean-machine and unavailable-dependency checks
NOT TESTED. Never remove shared WebView2/.NET/Python installations to simulate a
missing dependency. Actual installer runs can replace an existing product's
registration or shortcuts regardless of the destination folder, so portable
copy tests are not equivalent to NSIS install/upgrade/uninstall acceptance.

Current preservation regressions exercise real reviewed client removal only in
synthetic game folders. Character/garage saves, configuration, GBAY preferences,
unknown legacy `ALLIN1/` files and unrelated content remain intact; redirected
installation subtrees fail preflight. Read-only status no longer rewrites the
project's cached game path. These tests do not modify the installed game.
