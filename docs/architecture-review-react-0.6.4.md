# Launcher and SDK architecture review — 0.6.4

> Historical checkpoint: results, commands and artifact identities below apply
> only to the described source/session. They do not qualify current 0.6.5.
> See the [current release guide](release-0.6.5.md) before using this as guidance.

## Decision: FAIL / not release-qualified

Both applications are migrating to **React inside Tauri v2**. The SDK is much
further along. The Launcher now has a working development shell and real
shared-service workflows, but is not yet a packaged replacement for Tkinter.
Existing unrelated changes were preserved. No GTA process was launched, no real
game installation was changed, and no release was published.

The native Launcher visual check used temporary preferences and a service
without game-write or launch authority. Synthetic tests are not live acceptance.

## Architecture

`React drafts/review → Tauri capability broker → versioned Python protocol → domain services → files/native tools`

Keep this dependency direction: React owns presentation, Rust owns process and
native-dialog authority, and Python owns package semantics, validation,
transactions and receipts. Neither packaged application should import a sibling
checkout or require the other application for its own core work.

The new Launcher in `desktop/` delegates through `desktop_host.py` and
`desktop_service.py` to existing manager, package, extension, customization,
health and SDK services. Help content is separated from Tkinter rendering.
Game paths are explicitly selected; the service does not silently detect and
write another installed edition.

## Prioritized findings and fixes

Follow-up reproduction/fix coverage, still not release qualification:

- Atomic installer staging could restore a stale backup or overwrite a concurrent
  edit after a failed copy. Unique owned stages, complete preflight, original-byte
  checks and committed-only rollback now refuse that damage and retain recovery
  backups on incomplete rollback (`test_installer_transactions.py`).
- Client removal deleted user configuration and garage-related saves. Reviewed
  removal now preserves them and unknown legacy-folder files; installation roots
  reject redirected subtrees before writes (`test_installer_preservation.py`).
- Status inspection rewrote the source checkout's game-path cache. Discovery now
  has a read-only route, with isolated fixture paths (`test_detector.py`).
- Launcher stdio could hang indefinitely or mis-handle an uncertain writer after
  disconnect. Bounded framing/timeouts and explicit reconnect preserve drafts,
  do not replay writes, and allow EOF completion without killing an active writer
  (native protocol/process tests and React recovery tests).
- SDK's older frozen sidecar retained Tcl/Tk; source-only no-Tk tests missed its
  payload. Explicit exclusions and frozen CArchive/PYZ/ZIP inventory checks now
  guard both freeze output and extracted installer bytes (`test_frozen_desktop.py`
  in the SDK). Both product handoffs no longer implicitly choose Tk or a headless
  sidecar (`test_launcher_react_handoff.py`, SDK `test_launcher_bridge.py`).
- SDK gate labels and successful exit codes were insufficient proof of complete
  tests. Gate schema 2 binds canonical commands, prepared tool hashes and actual
  framework reports; skips fail (`test_candidate_test_evidence.py` in the SDK).

No VM is available. Same-machine disposable tests are supported, but cannot be
reported as clean-machine or NSIS registration/dependency qualification.

| Priority | Confirmed issue / impact | Disposition and regression evidence |
| --- | --- | --- |
| P0 | Launcher update/rollback trusted manifest paths separately from payload validation. | Normalized relative paths, exact ZIP/checksum agreement, link/alias rejection, disjoint roots, preflight, unique retained backups and target/hash-bound rollback receipts. `tests/test_updater_containment.py` uses outside-root canaries. Legacy rollback receipts fail closed. |
| P1 | SDK management assumed legacy executable names and did not consume Tauri portable packages. PE headers alone did not prove installed integrity. | Tauri release/build/resource contracts and full owned-file hashes; guarded swap, restoration, recoverable uninstall and preservation of unowned files. `tests/test_sdk_tauri_installation.py`. SDK portable producer emits matching metadata and rejects contradictory identity/companion inputs before output creation. |
| P1 | Diagnostic smoke/log evidence could be mistaken for live release acceptance. | Complete versioned checks, independently supplied session anchor, actual artifact/dependency bytes, edition and freshness required. Legacy logs fail closed. The artifact dashboard always marks itself not release-ready. `test_release_acceptance.py`, `test_qualification.py`. |
| P1 | SDK close/restart could terminate a sidecar with unresolved work. | Frontend draft guards and native pending-job checks; timed-out work remains pending until terminal evidence. Uncertain live processes cannot be automatically replaced. Packaged timeout/crash/close stress testing remains. |
| P1 | Launcher React cleared unrelated drafts after saving one workspace and reused stale configuration after content-bound changes. | Receipts return authoritative saved configuration; React adopts it and only clears the saved draft. Real-boundary tests preserve garage edits through character save and verify content → gameplay binding persistence. |
| P1, separate product | Actual suppressor ALLIN1 1.1.0 ZIP contains a different DLL from the staged payload. | Historical aggregate finding, owned by the separate **Suppressors Enhanced 1.2.1** release. Not an unconditional SDK/Launcher blocker; a candidate that actually bundles it must still prove payload integrity. `test_public_release_archives_are_clean_credited_and_self_describing` reproduces it. Do not overwrite a published version to hide this. |
| P1 | Launcher source/version and staged client pair differed. | Source targets 0.6.4; core/bridge rebuilt together with their hash contract. Previous three artifacts retained in `build/architecture-prebuild-1e97f9a2f87048d9aa6f22d8d1cda244`. This is local build evidence, not a reviewed release. |
| P1 | Launcher release-mode Rust expects a frozen service that is not packaged yet. | **Open.** `bundle.active` is deliberately false. Need pinned resources, frozen resource lookup, embedded-manifest verification, reproducible installer/portable staging and clean-machine lifecycle before switching default entrypoints. |
| P1 | Launcher Python coverage is below its unchanged 91% requirement. | **Open.** Latest measured 85.43%. Cover desktop-service errors, transaction failures, map/package contracts and process boundaries; do not lower thresholds or exclude new code. |
| P2 | Purchase telemetry parser expected historical price logging rather than unit/quantity/total. | Schema-1 structured successful-purchase event, strict parsing and producer contract tests. Historical display forms remain diagnostic compatibility, never release evidence. `test_purchase_telemetry.py`. |
| P2 | Four Tkinter SDK menu utilities were missing from the claimed parity inventory. | Metadata diff, round-trip, DLC inventory and vehicle-data compilation now have React Data Tools paths and real Python integration coverage. Declared module inventory increased to 27. |
| P2 | Pure suppressor policy tests invoked a game-runtime hash API during type initialization. | Three fixed player-model lookups use equivalent `PedHash` constants. The 14 previously failing cases now pass without GTA; 228 Debug companion tests pass. Existing suppressor release artifacts were not regenerated. |
| P2 | Native Launcher handoff could be delivered before its frontend listener existed. | Separate synchronized handoff readiness/pending request. Handoff only offers navigation and never applies installation/traffic changes. Packaged multi-process stress test remains. |
| P2 | Garage import allowed invalid shapes into the React draft. | Strict JSON and domain validation before returning a draft; invalid shape, boolean slot and unknown-model tests preserve files. |
| P2 | CLI/test defaults could inherit real preferences or detected game paths. | Click default resolves at invocation; common fixtures isolate user paths and discovery. Detector unit tests retain their own controlled fixtures. |
| P2 | Content inspection relied on private registry readers because `installed()` publishes files. | Added public pure `inspect()` and exact `installed_manifest()` APIs; publishing uses the same authorization computation. Tests verify zero writes and matching published evidence. Desktop service uses these public APIs. |

## Structural weaknesses still open

- SDK `App.tsx` / `desktop_protocol.py` and Launcher root components concentrate
  too many domains. Split workspace components and protocol adapters while
  retaining Python as the only writer. SDK's approximately 719 kB production
  JavaScript chunk still produces a size warning; do not suppress the threshold.
- Launcher `Record<string, any>` wire types are scaffolding, not a stable final
  contract. Replace them with per-operation discriminated request/result types
  and negative producer/consumer tests.
- Launcher synchronous response handling is size-bounded but lacks complete
  hung-child deadline/recovery behavior. Add it without killing an unresolved
  writer. Preserve bounded diagnostics instead of discarding drained stderr.
- The content read/write computation is now separated. Still review configuration
  + extension writes as a recoverable multi-file transaction, not merely
  sequential writes; keep legacy `installed()` callers explicit about publishing.
- Shared security/schema code is duplicated across repositories. Use shared
  contract fixtures and cross-version consumer tests, without creating a runtime
  dependency from one app to the sibling source checkout.
- A validator cannot create its own independent release authority. The final
  build/session anchor must come from the release workflow, never from the
  evidence under test. The full aggregate release gate is still unfinished.

## Migration inventory

| Workspace | Present in React | Still needed before full replacement |
| --- | --- | --- |
| Launcher shell | Tauri v2, logo/theme, sidebar/keyboard controls, dialogs, guarded close, persistent service, SDK handoff; frozen candidate and conflict-preserving state import | Native installer packaging; minimum-size/high-DPI audit; process-tree stress |
| Setup | Explicit paths/edition, readiness, profiles, reviewed save/sync/install/repair/uninstall/launch, dependency consent | Native lifecycle E2E, clearer field descriptions and install-plan presentation |
| Gameplay / Input | Existing config fields and persisted bindings | Purpose-built grouping, units/ranges, exhaustive secondary-control comparison |
| Content | Pure builtin/third-party inspection, schema settings, preinstall bound preferences, enable/disable | Native interaction acceptance; configuration/registry transaction review |
| Packages | Import inspector, initial settings, shared SDK library, builtin/example catalogs, install/disable/enable/uninstall | Native dialogs and package lifecycle acceptance |
| Characters | Progress/skills/money, inventory/ammo, outfit/presets, garage edit/import/export/repair | Remaining secondary controls, native dialogs and live runtime behavior |
| SDK Manager | Tauri/legacy archive verification, managed lifecycle, release lookup/tool handoff; independent assistant configuration/hardware/pinned download/import/remove | Fresh packaged SDK E2E, actual upstream/network failures and assistant native acceptance |
| Activity / Help | Session progress, retained structured journal, copy/open-folder, diagnostics export, readable manual-release lookup and fixed official-page navigation, independently scrolling help | Native interaction acceptance; automatic update installation is not part of the former Tk manual-release workflow |
| SDK authoring | Named happy paths for 27 declared modules; Data Tools and direct-open route gaps filled | Secondary-route and native-dialog coverage; outstanding partial items in SDK's `docs/tauri-feature-parity.md` |
| SDK updates | Read-only release check | Signed install intentionally blocked pending production signing identity/metadata |

Opening a workspace is not proof of completing every workflow. Launcher React
tests additionally execute real settings/profile/content/character/garage,
package/SDK lifecycle and diagnostic operations in temporary directories. SDK
tests mix fixture-backed UI tests and real Python/native integration; they are
not 221 packaged end-to-end tests.

## Release validation matrix

| Gate | Result | Evidence / limits |
| --- | --- | --- |
| Launcher React | PASS | 18 tests, no skips, real Python fixture boundary. |
| Launcher TypeScript/assets | PASS | Local production build, not a standalone installer. |
| Launcher Rust | PASS | 2 unit tests and development build. Actual 1200×820 window inspected; no separate console observed. Resize attempt did not resize, so minimum-size native validation remains NOT TESTED. |
| SDK React | PASS | 221 tests / 23 files; native runtime, RPF and Blender enabled; no skips. |
| SDK TypeScript/assets | PASS | Main-chunk size warning remains. |
| SDK Rust | PASS | 15 tests. Current source not sealed into a new installer. |
| Launcher Python | FAIL | 1 failed, 1,643 passed, 7 skipped; coverage 85.43% versus 91%. Artifact mismatch above. Final reports have `-final` suffixes. |
| SDK Python executed tests | PASS with qualification caveats | Final run: 2,356 passed, 8 skipped, 1 warning; 80.03% against 80%. Final XML/coverage reports have `-final` suffixes. Earlier visibility/teardown failures are not erased; shutdown test now retains a 250 ms worker-close limit plus a no-join assertion. |
| SDK omitted Python cases / Tcl cleanup | NOT TESTED / unresolved | 8 skips include four symbolic-link privilege cases, two native opt-in cases, a private game fixture, and one unexpected Tcl initialization failure. A Tk variable finalizer also warned about the wrong thread. The zero exit code does not certify stable native GUI lifecycle. |
| Main C# client | PASS | 1,053 Release tests, no skips; paired 0.6.4 core/bridge. `build/reports/architecture-client.trx`. |
| Suppressor policy | PASS, Debug only | 228 tests after initializer fix. Original 14 failures in `architecture-suppressors.trx`; fixed run in `architecture-suppressors-fixed.trx`. Packaged consistency still FAIL. |
| Containment and rollback canaries | PASS | Disposable update, manifest, rollback and SDK-consumer tests; no real installations used. |
| Managed SDK archive lifecycle | PASS, synthetic | Clean install, upgrade, repair, retained uninstall, user-file preservation, failed-swap restoration. Not proof of an NSIS lifecycle. |
| Actual SDK producer → Launcher consumer | PASS, synthetic | `tools/verify_sdk_portable_contract.py` exercises SDK ZIP generation, Launcher install/repair/removal and preserved user data. No synthetic executable is launched. |
| Fresh Launcher packaged lifecycle | NOT TESTED | Frozen candidate does not exist yet. |
| Fresh SDK packaged lifecycle | NOT TESTED | Historical candidates predate these edits. Clean Windows lifecycle still required. |
| Real Reactor dependency archives | NOT TESTED this pass | Optional tests skipped. Earlier audit results do not automatically qualify this source. |
| Signed updates / reviewed source | NOT TESTED / not eligible | Both trees dirty. No release approved or published. |
| Live Legacy / Enhanced | NOT TESTED | Requires explicit approval and acceptance bound to final artifacts. |

Skipped checks are never passes. Individual test runs are not aggregate release
qualification. The new Windows React CI job is defined but has not run on GitHub.

## Identities and reproduction

Launcher HEAD: `fb3a9b1a3e6941fc837b15a51d14076695da1d94`, **plus dirty edits**.
SDK HEAD: `bfc4e010126efe3a549adb96cbe9a4c855c80db3`, **plus dirty edits**.
Neither HEAD alone describes tested source. Both target 0.6.4. There is no newly
qualified release build ID; historical SDK candidates cannot qualify these edits.

Local artifact SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| Development Launcher shell | `29d3324657aa0d58eb18c43a19b1811b446cdceff1bec5f1da75f4e03eaf2374` |
| Paired `script/dist/ALLIN1.dll` | `63839be242127a6ef451fb14f9cca37309c4d2eb58aad06c58967bd2724f5c96` |
| Paired Reactor bridge plugin | `8d8991c9511d7ca9b6fd6acbcb4421c9bc018f5beb0f505fd5ff5db600367eaa` |
| Paired Reactor bridge contract | `9853e552f51a790252d6f915151c636ec67351c14d819314a9596b2bd6611437` |
| Existing suppressor ALLIN1 1.1.0 ZIP | `cb8c62270bcf1610ed55de7fd659d3738544f8facbc89ca8b6b8537287a11f8f` |
| Existing staged suppressor DLL | `5a37c4c2295a7d92b4ad2e28a0766e505200dc285f11d15ff5c58ee1aeb2199b` |

The development shell loads current frontend/Python sources; its hash alone
does not bind those inputs. Previous binary identities remain in the retained
prebuild directory rather than being silently discarded.
The final `build/reports/architecture-identity.json` snapshot records per-file
source inputs, dirty-tree digests, Python identity and observed artifact/report
hashes for both checkouts. It explicitly does not assert release qualification.

From the Launcher checkout:

```powershell
.venv/Scripts/python.exe -m pytest tests --cov=allin1 --cov-report=json:build/reports/architecture-coverage.json --junitxml=build/reports/architecture-python.xml -q -p no:cacheprovider
.venv/Scripts/python.exe -m pytest tests/test_updater_containment.py tests/test_sdk_tauri_installation.py tests/test_release_acceptance.py tests/test_desktop_service.py -q
.venv/Scripts/python.exe tools/verify_sdk_portable_contract.py --sdk-source ../ALLIN1-SDK
dotnet test script/tests/ALLIN1.Tests.csproj -c Release
dotnet test mods/realistic-suppressors/tests/RealisticSuppressors.Tests.csproj -c Debug
pnpm --dir desktop test
pnpm --dir desktop build
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
```

For SDK React tests, set `ALLIN1_NATIVE_RUNTIME_TEST=1`,
`ALLIN1_NATIVE_RPF_TEST=1` and `ALLIN1_BLENDER_EXECUTABLE` to the pinned Blender
executable before `pnpm test`. Run SDK Python with `--cov=allin1_sdk` and its
unchanged 80% threshold. Locally, Launcher `.venv` also contains the editable SDK.

## Next work in order

1. Freeze/package the Launcher service and resources with exact build identity;
   validate isolated installed operation before switching default entrypoints.
2. Qualify secondary Launcher actions and replace remaining broad wire types.
   Bounded native protocol frames and explicit no-replay reconnect now have
   process tests, including refusal to terminate an uncertain writer; packaged
   cancellation/process-tree acceptance remains. Retain Tkinter as the behavior oracle.
3. Verify companions actually included in these products, reach real Launcher coverage of 91%,
   and resolve SDK Tcl initialization/finalizer instability. Repeat the complete
   native lifecycle gate with prerequisites available rather than counting skips.
4. Seal new candidates from reviewed source and verify matching producer/consumer
   versions, native components, dependencies and installer contents.
5. Run clean Windows install/upgrade/repair/uninstall/rollback, missing-dependency,
   spaces/long-path/user-preservation tests; then approved live Legacy/Enhanced
   acceptance and signing. Publishing requires separate approval.
