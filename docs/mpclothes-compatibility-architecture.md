# MPClothes Compatibility Runtime — final architecture draft

Draft revision: 1.0 | Date: 2026-09-04 | Target: GTA V Story Mode

Status: implementation-planning baseline, not an implemented or accepted patch. No game-memory modification, game launch, or live acceptance test was performed for this document. All engine interfaces below are proposed contracts requiring discovery and verification.

This document narrows the earlier [YMT research and architecture](ymt-limit-expansion-research-and-architecture.md) to the MPClothes crash. It supersedes that document's product scope and delivery sequence, while retaining its research evidence and correctness requirements.

## 1. Product decision

Build a **standalone native compatibility layer delivered as an ASI**, focused on the clothing-metadata dependency-limit failure encountered when loading MP male/female freemode peds with MPClothes installed.

Working technical name: **MPClothes Compatibility Runtime**. `MPClothesCompat.asi` is a placeholder artifact name, not a released product. “Hotloader” may remain an informal label, but live asset replacement/reloading is not a version-one requirement and is not assumed to solve dependency overflow.

The preferred research strategy is **complete dependency accounting, independently owned metadata residency, and verified parent-model admission**. This potentially avoids widening every fixed-size engine array. It is a strategy to prove, not a guaranteed implementation.

The SDK team is building the supporting ped infrastructure. The native runtime must not depend on the SDK running, a generated inventory being present, or the user launching through ALLIN1.

### Intended outcome

On an explicitly supported game build, a reproducible MPClothes metadata-overflow setup can load freemode peds, select clothing, switch models repeatedly, and reload safely:

- Without deleting or disabling Rockstar DLC to create room.
- Without rewriting clothing identifiers, changing collection order, or migrating saved outfits.
- Without sacrificing stock clothes, expressions, or other affected ped behavior.
- Without requiring end users to install a compiler.

MPClothes is the reproduction and acceptance target, not an engine-level filename whitelist. The runtime must account for the relevant stock and third-party metadata attached to its supported peds, including shared dependencies and multiple simultaneously live freemode peds.

### Explicit non-goals

No universal GTA crash fixer; unlimited clothing; general mod hot-reloader; live archive mounting; automated YMT merging; executable-on-disk patches; automatic gameconfig tuning; DLC deletion; GTA Online operation; anticheat bypass; kernel component; or arbitrary external memory-write interface. Prop-index, expression-index, alternate-variation, apparel-shop, and texture-memory limits remain separate issues unless independently diagnosed and qualified.

## 2. Evidence and limits of the conclusion

The MPClothes author attributes current failures to YMT exhaustion, while also acknowledging that crashes have multiple possible causes. This is a strong reproduction lead, not a diagnosis of every user's crash. [MPClothes author page](https://www.gta5-mods.com/misc/mpclothes-addon-clothing-slots.)

The original Cfx investigation connects excess freemode metadata to dependency handling and documents regressions and rollback. A later array-widening attempt, PR #3444, reported a repeated male/female-switching failure. These establish why initial spawn success is insufficient. [Original investigation](https://forum.cfx.re/t/setplayermodel-crash-when-you-have-too-much-ymts-assigned-to-a-freemode-ped-model/1934063), [PR #3444](https://github.com/citizenfx/fivem/pull/3444)

FiveM PR #4165 proposes retaining metadata separately and removing already-loaded, retained entries from a constrained dependency result. It was open and unmerged when checked on 2026-09-04; the reviewed revision is `d65a864014e218407c3a47e14fb91019775f7230`. Its author reports tests on build 3258. Neither that report nor its 256-entry buffer establishes a safe Story Mode or Enhanced capacity. [PR #4165](https://github.com/citizenfx/fivem/pull/4165), [reviewed source](https://github.com/citizenfx/fivem/blob/d65a864014e218407c3a47e14fb91019775f7230/code/components/gta-streaming-five/src/PedMetaDataLimits.cpp)

Design inference: investigating separately owned residency is justified. Production compatibility, exact capacities, readiness ordering, reference ownership, and standalone lifecycle hooks remain unproven.

## 3. Ownership and reuse boundaries

| Workstream | Owns | Does not own |
| --- | --- | --- |
| SDK ped infrastructure | Ped/collection inventory, archive provenance, static dependency resolution, validation findings, report UI/CLI/Agent API, synthetic content fixtures | Game pointers, engine hooks, runtime readiness decisions |
| Native runtime | Engine discovery, adapters, early initialization, dependency observation, admission, residency, lifecycle, bounded telemetry | Archive editing, automatic repacking, broad authoring UI |
| Shared contract work | Versioned inventory/report/profile/receipt schemas and cross-language fixtures; SDK maintains canonical schema definitions with native-team review | A generic plugin ABI or unrestricted command channel |
| ALLIN1 integration, later | Optional edition selection, package ownership, installation/repair/rollback, diagnostics collection | Making an unsupported native profile safe |
| Reactor V, optional later | Read-only presentation of copied runtime diagnostics | Loading prerequisites, ownership, hook scheduling, mandatory bootstrap |
| Release qualification | Exact artifact/build acceptance evidence and an approved release catalog | Treating compilation or a runtime self-report as certification |

Concrete reuse points:

- Extend the SDK Ped Workbench (`ALLIN1-SDK/src/allin1_sdk/ped_workbench.py:689`; matching local checkout) and guarded ped authoring foundation (`ALLIN1-SDK/src/allin1_sdk/ped_authoring.py:277`; matching local checkout). Existing filename association/readiness checks are not a full engine dependency resolver.
- Reuse exact archive-member handling and synthetic RPF regression patterns (`ALLIN1-SDK/tools/RpfPatcher.Tests/README.md`; matching local checkout), not third-party assets as mandatory test fixtures.
- Generalize the axle native build preflight (`ALLIN1-SDK/src/allin1_sdk/story_axle_runtime_builder.py:1050`; matching local checkout) and its profile/receipt discipline. Do not reuse wheel offsets or infer ped compatibility from axle tests.
- Use [Launcher DLC inventory](../src/allin1/dlc_inventory.py) as evidence for registered/present packs, then add explicit mounting/override uncertainty handling in the SDK.
- Reuse the [binary-pair identity contract pattern](../src/allin1/reactor_bridge_contract.py) and [session-aware incremental log reader](../src/allin1/reactor_bootstrap.py).
- Extend [diagnostic bundle redaction and manifests](../src/allin1/diagnostics.py) with bounded input/output. The current bundle function reads complete candidate files; it is not already a bounded collector.
- The source-only native map-host scaffold (`native/map-host/README.md` in a local source checkout) offers policy/test patterns only. Its logical leases and disabled backend do not prove engine metadata ownership. It is not distributed with the public Launcher package.

Keep implementation in the appropriate project. This architecture does not direct the SDK team to modify the Launcher or ship placeholder native functionality. No Reactor integration or generalized compatibility framework is a prerequisite for the first native experiment.

## 4. Deployable components

| Component | Location | Contract |
| --- | --- | --- |
| Minimal ASI bootstrap | GTA process | Capture identity, arrange verified deferred initialization, report startup status |
| Profile registry | Compiled into edition-specific release | Approved identities, signatures, layouts, hook obligations, capacities, capability gates |
| Legacy/Enhanced adapters | Native ASI | Translate verified engine operations into narrow internal interfaces |
| Expansion core | Shared native library compiled into ASI and tests | Plans, bounded queues, residency ledger, state transitions, invariant checks |
| Diagnostic recorder | ASI, with off-callback writer | Copy bounded events; serialize outside engine hooks |
| Ped/YMT inspector | SDK desktop/CLI/Agent API | Read-only static analysis and import of runtime observations |
| Package/build utilities | SDK/release tooling | Preflight, artifact checks, manifests, candidate/release separation |

Runtime interfaces use internal typed identities and opaque hold tokens; no external tool receives raw addresses. The public interoperability surface is versioned data, not a remotely callable patching API.

Build separate Legacy and Enhanced binaries from shared core source. Each edition package may install the same ASI basename, but exactly one matching runtime belongs in a game directory. No implicit binary renaming or cross-edition fallback.

## 5. Bootstrap and compatibility activation

### Activation ordering

1. Identify the executable and runtime artifact, load bounded settings, and reject unsupported configuration.
2. Confirm a permitted Story Mode environment and matching compiled profile before expansion becomes usable. The profile must explain how this is established at its early activation boundary.
3. Resolve all required hook locations, expected bytes, code ranges, calling conventions, and layout canaries without modifying them.
4. Verify that initialization has not missed the relevant registration/request boundary. Do not assume metadata can be retroactively adopted safely.
5. Prepare bounded storage and all detours; commit them transactionally at a proven safe point.
6. Enter observation or expansion mode only after the mode's complete validation succeeds.

`DllMain` remains minimal. Heavy initialization, scanning, UI, COM/.NET/browser startup, and engine calls cannot be placed under loader lock. A worker thread by itself does not establish a safe engine context or correct initialization order. [Microsoft DLL guidance](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices)

### ASI versus separate preloader

First prove whether the supported ASI loading environment offers a safe, sufficiently early entry point. ScriptHook's first gameplay tick must not be assumed early enough. ScriptHook may provide later services without owning the critical early path.

Only if measurements show the ASI route cannot satisfy the ordering contract should the native team propose a minimal separate preloader. That requires a new compatibility/deployment decision; it is not a hidden Launcher or Reactor dependency. Do not replace the user's loader or proxy DLL opportunistically.

Unknown build, conflicting hook, or missed initialization boundary means no activation. An inert patch does not make an already-over-limit loadout safe; diagnostics must state that distinction.

## 6. Native adapter contract and release blockers

The following are logical operations, not discovered GTA APIs. Every adapter must document execution context, reentrancy, side effects, failure behavior, and identity lifetime for each operation.

| Logical operation | Required proof |
| --- | --- |
| Observe registration and generation | Metadata/model identities can be distinguished from recycled numeric indices |
| Snapshot complete dependencies | Enumeration is complete, bounded, correctly ordered, and safe inside the callee as well as the caller |
| Defer/admit a parent model request | Every relevant request path can be held before metadata consumption without lying about readiness |
| Acquire an independent metadata hold | The engine recognizes ownership distinct from other mods and stock users |
| Request/observe readiness | A request is distinguishable from completed, usable metadata |
| Present the streaming wait set | Only the intended constrained streaming consumer receives the reduced list |
| Preserve full semantic queries | Expression/creature/other consumers retain complete supported metadata |
| Drain/release at lifecycle boundary | Releases occur after dependent users drain and before identities/managers become invalid |
| Reject or abort unsafe work | Unsupported requests cannot proceed with silently missing prerequisites |

Three initial go/no-go blockers are early activation, safe parent admission, and independent engine ownership. Complete enumeration and downstream consumer coverage are additional release blockers, not cleanup work.

A local counter or aggregate engine “required” flag is not proof of an independent hold. A loaded flag is not proof that metadata will remain alive. Audit the semantics of the engine request/release/reference operations separately. [Upstream streaming interface](https://github.com/citizenfx/fivem/blob/03dcc562ca175e24eb018569ecb919b4b7a56824/code/components/gta-streaming-five/include/Streaming.h)

If these contracts cannot be demonstrated, do not ship the residency strategy. Produce the evidence and evaluate a narrowly identified routine replacement in a separate decision. No blind array widening or fake success fallback.

## 7. Core data and correctness model

### Three separate views

1. **Metadata catalog:** complete supported attachments and provenance for a model generation.
2. **Dependency closure:** every prerequisite required by the relevant loading path, including indirect dependencies where applicable.
3. **Streaming wait set:** the prerequisites the original constrained streaming consumer still needs to track.

Only the third view may omit a prerequisite that is already ready and protected by the patch's independent hold. The first two remain complete. Do not globally filter a dependency virtual function unless every affected caller's semantics have been established and preserved.

Every snapshot carries completeness status, generation, source evidence, and a bound. `count == capacity` does not prove completeness. Never call a potentially overflowing enumerator and rely on truncating its result afterward. A larger caller buffer cannot fix a smaller hidden callee buffer.

Preserve the ordering and duplicate semantics required by the engine. Unique physical holds may be deduplicated without rewriting a caller-visible semantic list.

### Residency ledger

Track a stable-in-context asset key containing streamer/session generation, module identity, streaming index, and verified registration identity. Keep model ownership edges separately from unique held assets. Record:

- Metadata role and provenance when known.
- Request state and observed readiness.
- Verified independent hold token and ownership count.
- Parent-model consumers and their generations.
- Acquisition/release progress, timeout/failure reason, and lifecycle generation.
- Measured memory use where available; otherwise explicitly unknown.

SDK file hashes and source paths are not runtime streaming identities. Join them through observed registration/provenance evidence when possible. An ambiguous join remains ambiguous.

### Mandatory invariants

- No parent admission before every separately handled prerequisite is ready and held.
- No truncated enumeration labeled complete and no unchecked buffer write.
- No release without proven patch ownership; no clearing another owner's flags.
- No stale-generation pointer/index access.
- No full semantic query receives a residency-filtered substitute.
- No unsafe partial hook activation or dropping active holds to return to stock mode.
- No unsafe request accepted because an inspector report or assistant says it is valid.

## 8. Loading, threading, and teardown

For each supported request, validate identity and a complete dependency plan. Preserve stock behavior for under-limit requests where that path is proven equivalent. An incomplete plan is not an under-limit plan.

For overflow, defer the parent through the verified admission mechanism, reserve bounded resources, acquire independent holds, and issue supported loading requests. Let the engine progress asynchronously. Once readiness and all required holds are confirmed, expose only the correctly reduced wait set to the intended streaming consumer and admit the parent.

Cover requests from trainers, saves, scripts, and other engine paths—not only a wrapper around `SET_PLAYER_MODEL`. A delay, zero-dependency return, or synchronous “load everything now” call inside a streaming callback is not a readiness barrier.

Logical asset states are `discovered`, `hold_acquired`, `loading`, `ready_held`, `draining`, `released`, and `failed`. Logical request states are `planned`, `deferred`, `waiting`, `admitted`, `cancelled`, and `failed`. State transitions must carry generation checks and explicit ownership side effects; failure is not automatic permission to release.

Engine operations run only in adapter-verified contexts. Hooks use preallocated bounded storage and explicit reentrancy handling. No archive parsing, disk/network I/O, UI calls, unbounded heap growth, or long waits in hooks. Do not invoke potentially reentrant engine operations while holding a ledger lock. Background writers only consume copied records.

Version one should retain a bounded union of required metadata for the verified streaming session, avoiding speculative eviction on each player switch. This deliberately trades memory for a simpler lifetime proof; the union has an explicit budget and cannot grow indefinitely.

Release only after dependent users drain and while engine release operations remain valid. Determine whether a Story reload preserves or rebuilds streaming identities; do not invent a generation from a menu event. On process exit, do not call destroyed engine managers. No hot ASI unload or live mode switching in version one.

## 9. Capacity and failure policy

Do not promise “256 extra YMTs,” unlimited clothing, or a universal slot count. Certified capacity is the lowest verified bound across complete enumeration, internal consumers, representation widths, dependency handling, ledger resources, and admission behavior. The upstream 256 value is a research parameter only.

Keep metadata pools, dependency capacities, clothing schema/index widths, and texture/model streaming memory separate. Disk size does not establish resident size. User settings cannot override compiled safety ceilings or supply arbitrary offsets.

| Condition | Required behavior |
| --- | --- |
| Unsupported build, hook conflict, or late startup | Remain inactive; emit a precise reason and warn that stock loading may still fail |
| Incomplete plan, failed load, timeout, or budget exhaustion before admission | Use verified defer/cancel behavior; do not proceed with missing dependencies |
| Invariant failure after expansion has active consumers | Stop new expansion, preserve required existing holds, and follow the profile's verified safe-abort behavior |
| Shutdown with pending work | Prevent new admission and drain according to verified engine lifecycle ordering |
| Corrupt settings or unsupported required schema | Refuse activation; never silently replace settings with permissive defaults |

No generic promise of a safe stock fallback after activation. If no safe abort mechanism exists for a possible failure, release remains blocked until the path is addressed. A research build's explicit termination policy must be documented; forced termination is not silently presented as recovery.

Profiles match edition, exact executable identity, signatures/layout assertions, and capability evidence—not a storefront label. Steam/Epic/Rockstar variants require matching evidence; mismatches must not be called piracy. Enhanced gets independent qualification even when the pure core is shared.

## 10. SDK ped infrastructure handoff

The SDK workstream can proceed without waiting for engine offsets.

### Required first deliverables

1. Content-based classification of supported ped variation/creature metadata, plus explicit unsupported/opaque findings.
2. Exact nested archive provenance, file fingerprints, and ped/collection/reference records.
3. Candidate dependency graphs with per-edge evidence, unresolved references, cycles, and conflicting definitions.
4. Effective-content analysis that distinguishes present, registered, expected mounted, and runtime-observed content; unknown mounting behavior remains visible.
5. Side-by-side stock and stock-plus-MPClothes reports, separately showing male, female, and shared relationships.
6. Versioned runtime-report import with synthetic fixtures and matching desktop/CLI/Agent API output.
7. Reusable native preflight/build/package contracts and fixture tests, not a fake functioning YMT ASI.

Inspectors may read user-selected files, supported archives, or a selected installation. Proposed combinations are plans, not installations. No game writes or implicit repacking.

The native team returns observed model/metadata identities, request counts, readiness/ownership events, generation behavior, and provenance links where established. SDK and native observations may disagree; preserve both sources and surface the discrepancy instead of treating either as authoritative outside its scope.

SDK reports never authorize raw engine operations. Version one does not require a runtime sidecar generated by the inspector. Any future sidecar used as a cache must be revalidated against the actual registration state and cannot become the source of truth for safety.

### Contract set

Names below are proposals for coordination, not files implemented by this draft.

| Contract | Producer → consumer | Minimum content |
| --- | --- | --- |
| `ped-inventory.schema.json` | SDK → SDK/tests/native analysts | Source catalog, exact members/hashes, typed records/edges, selection fingerprint, completeness and unresolved findings |
| `ped-runtime-report.schema.json` | Native → SDK/Launcher | Session/artifact/game/profile identity; observation scope; counts/states; readiness/ownership evidence; failures, unknowns, dropped-event counts |
| `ped-runtime-profile.schema.json` | Native qualification → release tooling | Exact build fingerprints, adapter/capability revision, verified capacity and boundaries, required evidence and exclusions |
| `ped-runtime-build-receipt.schema.json` | Build tooling → release tooling | Source/toolchain/configuration identity, tests, edition artifacts and hashes, experimental status |
| `ped-runtime-acceptance.schema.json` | Qualification → approved catalog | Exact artifact/profile/game identity, fixture/loadout fingerprint, required test results, evidence hashes and approval provenance |
| `ped-runtime-package.schema.json` | Release tooling → installer | Owned paths, edition/dependencies, runtime/config/schema versions, file hashes, support catalog binding |

Use versioned schemas with bounded sizes, arrays, strings, and nesting. Reject unsupported major versions and unknown required capabilities; permit documented optional extensions. Prefer `null` plus a reason for unavailable numeric measurements, not zero. Engine integer IDs must have lossless encodings across native code, Python, and JSON consumers.

All measurements identify their unit and basis: total dependencies, metadata-only dependencies, unique assets, model ownership edges, pending loads, and memory bytes are not interchangeable. Keep evidence classes `static_estimate`, `runtime_observation`, and `unknown` explicit.

## 11. Build, packaging, configuration, and trust

Reuse the SDK's configurable CMake/CTest, Visual Studio/MSVC, Windows SDK, x64, and real compile/link/run preflight. Discover supported installations beyond inherited PATH, refresh on Recheck, and report invalid explicit overrides instead of silently selecting another compiler. The actual build must use the exact toolchain that passed preflight.

Derive versions/features from this runtime's build contract, not axle-specific assumptions. Test the native core and validate AMD64 PE32+ outputs, required exports, edition markers, hashes, and configuration parsing before producing a candidate. Do not execute arbitrary downloaded binaries merely to inspect their exports.

Separate three states: `built_candidate`, `accepted_profile`, and `published_release`. A profile-presence export, successful compile, or runtime self-report cannot grant release approval. Pin approved receipts through a trusted release catalog; checksums establish consistency, not who is authorized to approve a result. Prefer compiled profiles initially. External executable patch recipes are not supported.

Proposed installed layout:

```text
<GTA root>/
  MPClothesCompat.asi
  MPClothesCompat/
    settings.json
    package-manifest.json
    logs/
    reports/
```

Runtime defaults are package-local and portable. Configurable runtime output paths must remain within validated writable locations, with explicit policy for absolute paths, traversal, and reparse points; initial packages use GTA-root-relative paths. Do not serialize author source/output paths into runtime settings. The SDK exposes Browse/edit controls and documents manual settings; players do not need the SDK to use defaults.

Configuration exposes enabled state, certified operating mode, and bounded diagnostics settings—not user-supplied hooks or unlimited capacity sliders. A configured change applies on restart. Development observation mode is visibly not a crash fix and still requires an audited instrumentation profile.

Ship prebuilt ASIs and required notices. Declare loader/ScriptHook prerequisites according to the actual host design; do not redistribute them without permission. Do not require Visual Studio, CMake, Python, .NET, Qwen, Reactor, or ALLIN1 merely to run the native patch.

Optional Launcher integration stages and verifies only owned files with GTA closed, backs up owned replacements, detects existing conflicts, and supports rollback. Never overwrite a foreign same-name file without explicit resolution. Uninstall leaves MPClothes and stock DLC intact and warns that a loadout relying on the patch may again exceed stock capacity.

Build, installed, and loaded identities are separate records. Runtime logs identify the current session and embedded build ID; tooling records on-disk binary hashes. Do not equate an old log, current file hash, or filename with proof of the loaded module. Any exact loaded-artifact attestation must document its measurement and timing.

## 12. Diagnostics and user experience

Show separate results for archive validity, decoded metadata, dependency resolution, executable compatibility, and in-game acceptance. Unknown is never green. A session that only visited one model does not certify every installed outfit.

Normal diagnostics contain state changes and summaries. Initial operational limits, distinct from engine capacity, should be configurable downward and enforced by implementation:

- Native event ring: maximum 1 MiB with dropped-event accounting.
- Normal logs: maximum 4 MiB per file, current plus two rotations.
- Normal session summaries: retain at most ten bounded summaries, each at most 256 KiB.
- Detailed captures: explicit opt-in, at most 60 seconds and 8 MiB; no rolling accumulation across sessions.
- Exported support bundle: at most 16 MiB of selected uncompressed content, with omissions disclosed and bounded processing before compression.

SDK full inventories may use a separate bounded/streamed export workflow; do not silently embed huge inventories or assets in support bundles. A diagnostic I/O failure must not break engine correctness.

Redact personal roots using structured fields and opaque source IDs before export. Exclude clothes, RPFs, executables, memory dumps, credentials, and unrelated logs by default. No automatic upload. Synthetic examples and user-approved asset links are preferred for support reproduction.

Qwen may explain structured results and prepare a concise handoff for another assistant. Treat metadata names and imported reports as untrusted data. AI must not choose offsets, infer acceptance, change installed content, or control memory writes. Reactor may later display copied counters through a bounded read-only interface, never drive the loading state machine.

## 13. Test strategy and release acceptance

### Establish the failure before implementing the fix

Capture the exact edition/executable, MPClothes version/package fingerprint, loader/trainer versions, effective DLC selection, and reproduction steps. Collect opt-in crash evidence locally. Show the same installation under stock, under-limit, and minimal-overflow conditions; separate bad assets and unrelated pool/VRAM failures from dependency overflow.

Use original, legally redistributable synthetic metadata fixtures to cross the relevant boundary without large textures. Verify the target failure mechanism, not merely a common crash label. Do not distribute Rockstar content or downloaded third-party packs as test fixtures.

### Automated coverage

- SDK: nested/same-name archive members, malformed/oversized files, unsupported types, duplicates, unresolved refs, cycles, override uncertainty, report/schema parity, paths/redaction/bounds.
- Core: limit minus one, exact limit, limit plus one, certified ceiling and ceiling plus one; shared/mixed dependencies, incomplete enumeration, repeated requests, slow/failed loads, queue/memory exhaustion, cancellation, index reuse, generation changes, ownership balance, reentrancy, and teardown.
- Adapter: unique signature/layout assertions, all relevant caller/callee buffers, thread/context assumptions, startup timing, conflicting detours, transaction rollback, and x64 unwind correctness. A hooking library alone does not prove ABI safety. [Microsoft x64 unwind guidance](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)
- Package: exact preflight selection, mismatched tool versions, failed probes, wrong-edition/invalid PE artifacts, altered hashes, unapproved receipts, interrupted owned-file transactions, and clean uninstall on temporary fixtures.

### Live matrix per advertised profile

Test cold and warm loads, delayed I/O, both genders, repeated male/female/male changes, multiple simultaneous freemode peds, stock NPC regressions, death/respawn, model replacement, save/reload, return to menu, and exit. Verify MPClothes plus stock clothing, props, expression-sensitive items, alternates, first-person variants, and outfit restoration within their declared supported scope.

Test with and without the patch on the same under-limit configuration, then with the verified overflow fixture. Exercise supported loader/trainer combinations and overlapping limit-adjuster conflicts. Track bounded-memory/queue behavior, generation validity, clothing identity preservation, and lifecycle leaks rather than only crash counts.

Proposed minimum qualification run: 100 alternating model switches, 20 Story reload cycles, and a two-hour representative session for each release profile, in addition to the boundary/fault tests. These are acceptance targets, not statistical proof of universal stability. Record loading-time, memory, and frame-time deltas against a matched baseline; approve tolerances before the qualification run.

Every required result is bound to the exact ASI, adapter/profile, executable, fixture/loadout, and test-harness revisions. Compilation and fixture tests cannot substitute for this matrix. Optional capabilities require their own evidence. A storefront/build variant not represented by approved evidence remains unsupported.

## 14. Delivery sequence and gates

| Stage | Parallel work and deliverable | Exit gate |
| --- | --- | --- |
| A — contracts and reproduction | SDK builds ped infrastructure/synthetic report fixtures; native team isolates MPClothes failure and maps candidate engine paths | Agreed schema v1, attributable repro, legal fixture/dependency plan |
| B — observe-only native research | One exact Legacy target; bounded instrumentation and annotated registration/dependency/lifecycle observations | Proven early-entry opportunity, complete-enumeration method, ownership and admission feasibility; no safety claim from observation alone |
| C — experimental expansion | Pure core, one adapter, bounded telemetry, fault tests, preserved full semantic queries | Correctness invariants and minimal overflow fixture pass, including cold loading and teardown |
| D — Legacy qualification/package | SDK imports real observations; release tooling builds candidates; full live matrix | Approved artifact/profile acceptance receipt and standalone package |
| E — optional Launcher integration | Owned install/repair/rollback and compact support reporting | Installation tests plus same standalone behavior; no new mandatory dependency |
| F — Enhanced | Reuse contracts/core; rediscover and qualify edition-specific internals | Independent Enhanced acceptance, not inherited Legacy support |

Reactor presentation, repacking, hot reloading, and adjacent engine-limit patches are explicitly deferred. No delivery date or numerical expanded capacity is promised before Stage B.

If feasibility fails, the SDK ped inspector remains useful, but must be described as diagnostics—not a completed MPClothes fix.

## 15. Open decisions and change control

Before the native prototype can activate, resolve and record:

1. Exact first executable and MPClothes reproduction set.
2. Actual failing consumer(s), their complete-enumeration contract, and all relevant semantic callers.
3. Earliest safe ASI initialization point; whether a separate preloader is necessary.
4. A real request-admission/cancellation boundary covering all supported model-loading paths.
5. Independent engine hold semantics and how ownership can be proved and released.
6. Story reload/teardown identity behavior, including pending and simultaneous model requests.
7. Build-specific capacities, bounded-memory budgets, and safe failure policy.
8. Source/library reuse rights and the release-approval trust root.

The SDK team can finalize inventory/report infrastructure while these remain open. Profile capabilities and capacities stay unset until evidence exists. Changes to identifiers, archive content, external bootstrap requirements, or target platform scope require an explicit architecture revision.

The reviewed FiveM source has directory-dependent license terms; do not assume blanket permissive/LGPL reuse. CodeWalker's source notice also requires review before extending redistribution. Existing inclusion in another project is not new permission. Record provenance and obtain permission where needed; rewriting inspected code is not automatically a clean-room implementation. [FiveM license at reviewed revision](https://github.com/citizenfx/fivem/blob/d65a864014e218407c3a47e14fb91019775f7230/LICENSE), [CodeWalker source notice](https://github.com/dexyfex/CodeWalker/blob/master/Readme_Src.txt)

## Definition of done

The SDK can explain the selected ped/metadata configuration without hiding unknowns. The independently usable native ASI fixes a reproduced MPClothes dependency-limit failure on explicitly qualified builds, preserves stock and addon behavior, and passes repeated loading and teardown tests. Packages, runtime observations, and acceptance evidence identify the same artifacts. No DLC removal or clothing-ID rewrite is required.

An inspector, a compiled ASI, a resolved signature, or one successful spawn is a milestone—not this definition of done.
