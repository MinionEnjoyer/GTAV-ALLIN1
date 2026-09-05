# GTA V YMT limit expansion: research and proposed architecture

Research date: 2026-09-04. Status: architecture proposal, not an implemented or validated patch.

Implementation-planning update: the [MPClothes Compatibility Runtime architecture draft](../docs/mpclothes-compatibility-architecture.md) now defines the focused product scope, SDK/native responsibilities, shared contracts, and delivery gates. This document remains the supporting research record.

## Executive recommendation

Build a standalone, build-gated Story Mode native ASI with an optional read-only inspector. Investigate **externally managed metadata residency with verified loading prerequisites** as the first prototype. Do not start by replacing every occurrence of 80/100, increasing gameconfig pools indiscriminately, or deleting Rockstar DLC.

The product should preserve clothing collections, identifiers, files, and load order. Its initial purpose is to expand the effective metadata dependency capacity of supported freemode ped loading paths, not to make every clothing limit unlimited.

The strongest current lead is experimental, not production proof. The research supports funding a bounded feasibility phase. It does not yet justify promising a reliable 256-YMT single-player release.

Scope of this investigation: public primary-source code, developer discussions, current PR status, and local metadata schema inspection. No GTA executable was disassembled, no crash dump was analyzed, no game was launched, and no patch was built or installed. All interfaces and lifecycle mechanisms proposed below are design requirements, not claims that corresponding standalone engine APIs have already been located.

## 1. Findings that change the design

### 1.1 This is not a global count of files with a .ymt extension

The original reproducible investigation attached additional variation and creature metadata to freemode peds. A Cfx developer traced the failure to model streaming dependency enumeration: required metadata could be absent when ped model processing assumed it was available. Several fixed-capacity consumers were implicated. Both early workarounds were subsequently backed out after widespread new crashes. [Original investigation and rollback](https://forum.cfx.re/t/setplayermodel-crash-when-you-have-too-much-ymts-assigned-to-a-freemode-ped-model/1934063)

**Design consequence:** count resolved dependencies by model and metadata role. Disk file totals, pack counts, and an approximate male/female slot table are useful hints, not authoritative capacity measurements. Shared metadata needs one physical-residency record but potentially several model ownership edges.

### 1.2 Broad array widening has a documented regression history

FiveM PR #3444 attempted widening numerous fixed arrays and related stack accesses. Its author reported a rare male-to-female-to-male crash and closed the attempt. Its source also identifies creature metadata queries, prop expression updates, externally driven DOFs, dependency graphs, and streaming requests as relevant consumers. [PR #3444](https://github.com/citizenfx/fivem/pull/3444), [pinned implementation](https://github.com/citizenfx/fivem/blob/0fec9789c99fac73d9e3362536363c2f1bec3aaf/code/components/gta-streaming-five/src/CrashFixes_Clothing.cpp)

**Design consequence:** fixing initial model selection is insufficient. Expression evaluation and teardown are first-class acceptance cases. A bigger caller buffer also does not establish that the original callee has no smaller internal buffer.

### 1.3 A newer approach reduces the patch surface

PR #4165, opened September 1, 2026, targets a 256-entry dependency buffer with separately maintained residency for overflow. Its author reports two formerly crashing packs working on FiveM build 3258. At inspection it was open and unmerged; the reviewed head was `d65a864014e218407c3a47e14fb91019775f7230`. That evidence does not establish Story Mode or Enhanced compatibility. [PR #4165](https://github.com/citizenfx/fivem/pull/4165)

The pinned code intercepts metadata assignment and model dependency enumeration, uses streaming requests and loaded flags, and releases recorded entries during a FiveM session shutdown event. [Pinned source](https://github.com/citizenfx/fivem/blob/d65a864014e218407c3a47e14fb91019775f7230/code/components/gta-streaming-five/src/PedMetaDataLimits.cpp)

### 1.4 Review questions for that prototype

These are risks identified by source inspection, not reproduced defects:

| Observation in the pinned prototype | Proof required before using the idea in Story Mode |
| --- | --- |
| Overflow entries can be requested without an explicit readiness barrier in this file. | Every omitted prerequisite is ready before its parent is processed. |
| Residency uses a set of indices and aggregate engine flags. | The patch has an independent hold and releases only its own ownership. |
| Dependency enumeration is intercepted through a vtable. | No caller needs the complete list for a different purpose. |
| Results above the scratch limit are clamped. | Completeness and bounded writes are established independently. |
| Cleanup uses FiveM lifecycle facilities. | Standalone teardown occurs before streaming identities become invalid. |

Source: [the exact reviewed implementation](https://github.com/citizenfx/fivem/blob/d65a864014e218407c3a47e14fb91019775f7230/code/components/gta-streaming-five/src/PedMetaDataLimits.cpp). The proposed architecture below is an independent design intended to address these proof obligations.

### 1.5 Several unrelated limits are commonly conflated

| Mechanism | Evidence | Product treatment |
| --- | --- | --- |
| Per-model metadata dependency capacity | The YMT investigations above | Core expansion candidate |
| Metadata-store pool allocation | Separate from a caller's dependency buffer | Diagnose; no blanket automatic increases |
| Global prop-index truncation | FiveM patches functions narrowing 32-bit indices to 8 bits | Separate capability; do not call it unlimited props. [Source](https://github.com/citizenfx/fivem/blob/03dcc562ca175e24eb018569ecb919b4b7a56824/code/components/gta-core-five/src/PatchPedPropsLimit.cpp) |
| Component expression index truncation | A separate merged FiveM fix addresses indices above 255 | Separate compatibility finding. [PR #2579](https://github.com/citizenfx/fivem/pull/2579) |
| Alternate-variation working capacity | Current FiveM source uses 512 and guards output bounds | Diagnose independently; not covered by YMT residency. [Source](https://github.com/citizenfx/fivem/blob/03dcc562ca175e24eb018569ecb919b4b7a56824/code/components/gta-core-five/src/PedAlternateVariationCache.cpp) |
| Apparel shop lookup capacity | PR #4061 describes an approximately 65,520-entry global lookup overflow; it was still unmerged when checked | Count separately; no automatic inclusion of that patch. [PR #4061](https://github.com/citizenfx/fivem/pull/4061) |
| Collection file-format fields | CodeWalker declares byte-sized prop counts and component/drawable fields | Validate content schema; runtime expansion does not widen disk fields. [Schema source](https://github.com/dexyfex/CodeWalker/blob/master/CodeWalker.Core/GameFiles/MetaTypes/MetaTypes.cs) |
| Texture/model streaming pressure | More metadata is not more available rendering memory | Report measured pressure; no unlimited-content promise |

Do not import FiveM networking limits or FiveM-only natives into the Story Mode specification. Do not assign every crash with the same error name to clothing.

### 1.6 Enhanced requires its own investigation

A July 2026 Cfx discussion reported no spare clothing YMT slots in its then-current Enhanced configuration. It distinguished an unrelated native crash fix from addon-clothing support. This is historical evidence of an Enhanced problem, not a measurement of the user's current Story Mode installation. [Cfx Enhanced discussion](https://github.com/citizenfx/rfc/discussions/204)

The official Script Hook V page currently lists Legacy `1.0.3889.0` and Enhanced `1.0.1158.13`. These are useful candidate research targets, not proof our hooks support them. Its public native API is intended for Story Mode ASIs and excludes GTA Online. [Script Hook V](https://www.dev-c.com/gtav/scripthookv/)

## 2. Product boundary and architecture

Proposed names below are placeholders.

| Component | Placement | Responsibility |
| --- | --- | --- |
| `YmtExpand.asi` | GTA process | Bootstrap, validated native interception, lifecycle coordination |
| `ExpansionCore` | Native library compiled into ASI and tests | Dependency plans, residency ledger, bounded state machine; no hardcoded GTA addresses |
| `LegacyAdapter` / `EnhancedAdapter` | ASI, separate profile implementations | Exact layouts, enumeration semantics, loading/hold operations, request admission, teardown |
| `ProfileRegistry` | Compiled/signed release data | Supported executable identities, expected code and layout assertions, certified capacities |
| `YmtInspector` | Optional external CLI/UI | Effective content inventory, preflight, report comparison, support bundle |
| `Diagnostics` | Bounded native events and external report writer | Version identity, dependency counts, readiness, ownership, refusals, performance |
| ALLIN1/SDK integration | Optional consumer | Install/check/report using the same package and inspector contracts |

The ASI should not require Reactor, Chromium, Python, .NET, or ALLIN1 to function. A .NET inspector could fit existing tooling, but parser licensing and portable packaging must be resolved first. Keep archive parsing and rich reports out of hot game callbacks.

No general-purpose external memory-write API. No remote patch downloads or arbitrary user-supplied offsets. No executable-on-disk modifications, archive changes, DLC removal, slot renaming, or saved-outfit migration in the core product.

### 2.1 Strategy decision

| Candidate | Benefit | Main risk | Recommendation |
| --- | --- | --- | --- |
| Raise gameconfig pools | Simple for genuine allocation exhaustion | Does not enlarge fixed dependency consumers | Not the YMT fix |
| Repack collections | Can reduce metadata demand without hooks | Changes identifiers/references; bounded by file formats | Optional, separate tool later |
| Widen all fixed arrays in place | Direct capacity expansion | Many callers, stack/unwind assumptions, teardown paths | Do not lead with this |
| Manage verified metadata prerequisites outside the narrow dependency list | Smaller initial intervention | Load ordering, ownership, and complete enumeration | Preferred research prototype |
| Replace selected engine routines with bounded native implementations | Full control over proven unsafe consumers | Larger reverse-engineering and maintenance burden | Fallback only for explicitly identified consumers |

Collection consolidation is already implemented by other tooling, including reversible workflows. That supports its feasibility, not equivalence to runtime limit expansion. [Red40 repacker](https://github.com/Red40-Development/red40_clothing_packer)

## 3. Core correctness model

### 3.1 Three distinct sets

For each model generation, maintain:

1. **Complete metadata catalog:** every resolved variation/creature metadata attachment and its provenance. This remains the complete view used for auditing and non-streaming consumers.
2. **Dependency closure:** all prerequisites the relevant loading path requires, including indirect dependencies where applicable. Bound traversal, detect cycles, and distinguish incomplete enumeration from an empty set.
3. **Streaming wait set:** the subset the original streaming caller still needs to track. An item may leave this set only after the patch has independently established readiness and protected its lifetime.

Preserve original ordering and semantics in caller-visible lists. Deduplicate physical holds in the ledger without automatically deduplicating an engine list whose duplicate semantics have not been established.

This separation is essential: preventing eviction does not justify concealing metadata from expression queries or dependency-graph analysis. Audit every relevant consumer, including indirect dispatch and direct calls bypassing a vtable. If a consumer needs full enumeration, preserve it through a separately verified adapter. If an internal creature query remains capped, that becomes the effective product ceiling until addressed.

### 3.2 Proposed invariants

- A required metadata object is never treated as satisfied merely because a load was requested.
- Every removed streaming prerequisite has a current, verifiable patch-owned lifetime hold.
- Full metadata consumers receive their full supported data, not a residency-filtered substitute.
- Every write fits both the destination capacity and any callee/internal representation constraints.
- A complete snapshot cannot be inferred solely from `returned_count == buffer_capacity`.
- Non-metadata prerequisites retain original engine handling unless separately proven safe.
- A model is not admitted to use an incomplete prerequisite set.
- A numeric streaming index is not a permanent identity.
- No hook installation is partially committed; no live model loses required holds during a mode change.

These are acceptance requirements, not descriptions of current engine behavior.

### 3.3 Proposed residency ledger

An internal asset identity should include the session/streamer generation, module identity, local/global index, and a registration generation or other verified identity token. Track model ownership edges separately from unique resident assets.

Suggested logical fields:

- asset identity and owning model generations;
- metadata role and source provenance when available;
- request/readiness state, timestamps, and retry/failure reason;
- whether an independent engine hold was actually acquired;
- adapter-specific release token and teardown ordering;
- estimated/measured resident bytes, with unknown reported explicitly.

An internal reference counter does not create an engine reference. Reverse-engineer whether the available operations use reference counts, shared request bits, or both. Aggregate loaded/required flags do not prove our ownership. If the adapter cannot establish an independent hold without clearing another owner's state later, this strategy fails its release gate. Do not invent unused engine flag bits.

The FiveM wrapper exposes distinct request, release, module-reference, and deletion-readiness operations, but their presence is not proof of interchangeable semantics. [Streaming interface](https://github.com/citizenfx/fivem/blob/03dcc562ca175e24eb018569ecb919b4b7a56824/code/components/gta-streaming-five/include/Streaming.h), [wrappers](https://github.com/citizenfx/fivem/blob/03dcc562ca175e24eb018569ecb919b4b7a56824/code/components/gta-streaming-five/src/Streaming.cpp)

### 3.4 Loading and readiness sequence

The proposed logical sequence is:

1. Resolve an effective metadata catalog at a verified registration boundary.
2. Before the parent model can consume metadata, obtain and validate its complete prerequisite plan.
3. If it fits the original path, retain stock behavior wherever possible.
4. Otherwise reserve bounded ledger/queue capacity and acquire the required metadata holds.
5. Let the engine progress loading on its verified thread/context. Observe completion without blocking a streaming callback.
6. Admit the parent only when every separately handled prerequisite is loaded and held.
7. Maintain the complete catalog and holds throughout the model's applicable lifetime.
8. Drain ownership at a verified safe lifecycle boundary before registration identities are destroyed or reused.

The difficult step is parent admission. The research phase must locate a real engine mechanism for deferring/cancelling/retrying the request without lying about readiness. Returning zero dependencies, changing `SET_PLAYER_MODEL` alone, or issuing a synchronous global load from an arbitrary callback is not an acceptable substitute.

Prefer metadata preloading at registration/startup boundaries when the ordering is proven. Still cover model requests from trainers, ambient peds, saves, and other scripts. Never use a timing delay as proof that preloading finished.

If no safe standalone admission boundary can be demonstrated, do not ship this design. Reassess targeted routine replacement or leave the result as a diagnostic tool.

### 3.5 Capacity policy

Use 256 as a research ceiling to evaluate, not a promised user entitlement. It would denote a verified dependency capacity for a particular adapter/path, not 256 additional packs, 256 clothes, or automatically 256 extra YMTs per gender.

Certified capacity is the minimum of all relevant verified limits: enumeration, internal metadata queries, dependency consumers, representation widths, ledger resources, and admission machinery. Publish only the capacity demonstrated by tests.

A fixed 256-entry scratch buffer must not silently turn an unknown larger result into success. Determine enumeration completeness from a verified source/contract; refuse uncertain plans before they affect model admission. Account for indirect dependencies and unrelated prerequisites.

Preallocate bounded structures, cap concurrent plans and global resident assets, and expose overflow distinctly from parser errors or missing resources. Set memory budgets using measured metadata allocations on supported builds; do not equate file size with resident size or expand texture budgets automatically.

### 3.6 Threading and lifecycle

Engine operations run only on an adapter-verified engine context. Do not assume all streaming hooks execute on the ScriptHook script fiber. A background writer may consume copied diagnostic records but must never dereference GTA objects.

Use bounded, preallocated scratch storage with explicit reentrancy handling. No disk I/O, HTTP, UI calls, general heap growth, or long waits inside hooks. Never call potentially reentrant engine loading/releasing operations while holding a ledger mutex.

For the first release, retain a bounded metadata set for the verified streaming session instead of aggressively releasing on every player swap. That trades memory for a simpler lifetime proof. Release it only after dependent users are gone and while the engine still accepts releases. If identities persist across a story reload, retain the same generation; if they are rebuilt, drain before destruction and start a new generation. FiveM shutdown events cannot be assumed to exist in Story Mode.

No hot ASI unload in version one. At process teardown, avoid calling into already destroyed streaming managers. `DllMain` remains minimal; substantive initialization must occur outside loader lock, early enough to meet the validated registration boundary. These requirements must be reconciled in the prototype, not hidden behind a startup sleep. [Microsoft DLL guidance](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-best-practices)

## 4. Build compatibility and failure policy

### 4.1 Profiles are evidence, not just version strings

Each profile records:

- edition, executable identity/fingerprint, tested distribution variants, and profile revision;
- expected module/code ranges, unique signatures, surrounding instructions, and vtable layout;
- structure offsets, sentinel values, count semantics, and residency ownership contract;
- registration/admission/readiness/teardown boundaries;
- covered model and metadata types, certified limits, and unsupported cases;
- overlapping hook exclusions and the test receipt authorizing release.

A storefront is not the patch-selection key. Accept different Steam/Epic/Rockstar installations only when executable identity and semantics satisfy a certified profile. Unknown variants remain unsupported pending verification; do not infer piracy from a mismatch.

Legacy and Enhanced share pure planning/ledger code, not assumed layouts, signatures, resource formats, or loading semantics. Initially target one current Legacy build; use build 3258 as an upstream comparison only if legitimately available. Enhanced is an independent qualification phase.

### 4.2 Hook transaction

Resolve and validate every required location before modifying anything. Inspect existing bytes/targets for other patches. Prepare detours first; commit at a verified safe point; record originals and ownership. Roll back startup failure before gameplay depends on the patch. Never overwrite an unknown detour or blindly chain multiple limit adjusters.

Prefer function-entry or audited dispatch hooks over rewriting stack layouts. Generated trampolines need correct x64 calling conventions and unwind behavior; the presence of a hooking library is not a complete proof. [Microsoft x64 unwind documentation](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170)

### 4.3 Refusal before activation differs from failure after activation

- **Unsupported or conflicting at startup:** do not patch; report why. The user's original oversized loadout may still crash. Being inert does not make that loadout safe.
- **Unsafe new request with a verified cancellation path:** reject/defer it while preserving existing safe state and explain the offending model/asset.
- **Invariant failure after expansion is active:** do not unhook, drop references, or claim a stock fallback is safe. Stop new expansion and use a verified safe abort path. If none exists, diagnostic termination is more honest than continuing with invalid prerequisites. A production profile must specify this behavior.

Story Mode only. Never bypass anticheat or enable Online use. Installation/removal occurs with GTA closed; uninstallation removes only owned patch files and leaves clothing content intact. Users need a compatible loadout before launching without a previously required patch.

## 5. Inspector and support experience

### 5.1 Static inventory

Read the selected game/mod paths, effective DLC registrations, override precedence, and relevant shop/ped/creature metadata. Resolve archives rather than counting filenames. Detect missing/duplicate identities, unsupported resource formats, malformed references, and expression/alternate dependencies.

Export three distinct evidence classes:

- **Static estimate:** resolved from the recognized load configuration.
- **Runtime observation:** measured in an identified session and profile.
- **Unknown:** inaccessible archives, unsupported loader behavior, or incomplete graph.

An unknown is never green. A clean static schema check does not prove in-game loading. A runtime observation below the limit does not certify unvisited model paths.

### 5.2 Reporting contract

Suggested state codes: `unsupported_build`, `hook_conflict`, `observe_only`, `active`, `metadata_not_ready`, `enumeration_incomplete`, `capacity_exceeded`, `ownership_unproven`, and `restart_required`.

Report patch version, executable/profile identity, session ID, observed model, capacity, complete dependency count, uniquely held assets, pending loads, refused requests, and related limits checked/not checked. Separate requested, loaded, and held counts.

The optional ALLIN1/SDK interface consumes the same versioned JSON report as the CLI. No special launcher is necessary. Users set their own game root, scan roots, and report location; sensible defaults never contain the developer's paths. Keep paths private in exported support bundles by default. No automatic uploads of clothing, archives, executables, or dumps.

Bound and rotate logs. A normal session records state transitions and summaries, not every hook call. Short diagnostic captures are opt-in and capped; report dropped events explicitly. Do not generate enormous traces as routine telemetry.

## 6. Validation and release gates

### 6.1 Pure native core tests

Use a deterministic fake streaming adapter to test:

- exact original limit minus one, at limit, plus one, certified ceiling, and ceiling plus one;
- incomplete/truncated enumeration, invalid indices, duplicates, cycles, shared metadata, and mixed prerequisite types;
- out-of-order completions, slow/failed loads, cancellation, repeated requests, queue exhaustion, and timeouts;
- independent owners, repeated acquisition/release, generation changes, and numeric index reuse;
- reentrant callbacks, concurrent readers, teardown while requests are pending, and allocation failures;
- under-limit equivalence and complete non-streaming enumeration.

Guard buffers and use sanitizers where supported. Property tests should enforce: no destination overflow, no premature admission, no release without ownership, and no unreported incomplete dependency set.

### 6.2 Native adapter qualification

For each executable profile, document all relevant callers/callees and verify signatures, internal buffers, request semantics, and lifecycle ordering. Test hook conflicts and startup rollback on a harness before GTA. Validate stack unwinding through patched paths and ensure no exceptions escape the ABI boundary.

An observation build may use audited hooks that preserve behavior, but that is still runtime instrumentation requiring profile validation. A debugger breakpoint or snapshot is not automatically safe on a live streaming hot path. Unknown builds get external-only inspection.

### 6.3 Live Story Mode acceptance

Build a minimal synthetic, legally distributable fixture that crosses dependency capacity without large textures. Use it to isolate metadata from VRAM and unrelated pools. Then test realistic user-authorized content locally.

Required matrix:

| Axis | Required cases |
| --- | --- |
| Build/edition | Every advertised profile; unsupported adjacent build refuses |
| Content | Stock, minimal overflow, mixed variation/creature metadata, near-ceiling, over-ceiling |
| Models | Male, female, shared metadata, multiple simultaneous freemode peds, stock NPC regression |
| Timing | Cold load, warm load, delayed I/O, deliberate request failure, memory pressure |
| Lifecycle | Repeated male/female/male swaps, death/respawn, model replacement, save/reload, return to menu, process exit |
| Clothing features | Props, heels/expression changes, hats/hair alternates, first-person variants, outfit restoration |
| Coexistence | Relevant trainers, loaders, existing limit adjusters, and multiple ASI load orders |

Proposed release minimum: 100 successful alternating model swaps, 20 story reload cycles, and a two-hour representative session per release profile, in addition to boundary tests. These counts are engineering acceptance targets, not statistical proof of universal stability.

Verify that original and addon items remain present and correctly indexed, no bounded-queue/refcount growth persists across the corresponding lifecycle, no references target reused generations, and no additional crash appears in teardown. Compare under-limit performance and memory against a no-patch baseline on the same machine; publish the measured delta instead of promising zero overhead.

### 6.4 Dependency and packaging checks

Pin the native build toolchain and libraries in CI. Validate compiler/SDK/CMake/CTest requirements for developers, not end users. Ship prebuilt user-mode ASI binaries with hashes, versioned profiles, license notices, and reproducible build receipts; no kernel driver is needed. Test install/uninstall ownership behavior on temporary fixtures. Do not require players to compile the patch themselves.

## 7. Implementation sequence and decision gates

### Phase A: feasibility and licensing

1. Reproduce the precise failure on one selected Legacy build with a minimal fixture.
2. Map full metadata registration, dependency enumeration, expression consumers, parent admission, and teardown.
3. Prove independent residency ownership and readiness ordering under cold loads.
4. Resolve source/library reuse rights before importing code.

Deliverable: annotated call graph, exact failing capacity, crash evidence, and a yes/no decision on the preferred strategy. Stop at an inspector if the required ownership/admission contracts cannot be established.

### Phase B: standalone experimental Legacy ASI

Implement the pure core, narrow adapter, bounded diagnostics, and one profile. No UI framework or automatic gameconfig edits. Preserve identifiers and all DLC. Run fault injection and the full model/lifecycle matrix before inviting broader tests.

### Phase C: usable diagnostic package

Add the inspector, portable configuration, owned installation/removal, and a compact support report. Integrate with ALLIN1/SDK only through that stable contract. Expand supported Legacy fingerprints individually.

### Phase D: Enhanced and optional adjacent fixes

Repeat adapter discovery and acceptance for Enhanced. Add prop, expression, alternate-cache, or apparel-store fixes only as separately gated capabilities with their own evidence. A missing adjacent capability must be visible, not hidden behind an overall green status.

Repacking and content migration remain a separate, explicitly approved workflow with backups and ID-remapping reports.

## 8. Licensing and provenance constraints

The inspected FiveM license places the repository under the Rockstar Creator Platform terms with an LGPL exception for listed directories. `code/components/gta-streaming-five/`, which contains the candidate patch, is not one of those listed exceptions. Do not assume blanket LGPL/MIT reuse. Resolve applicable permissions before copying or distributing a port. [License at the reviewed commit](https://github.com/citizenfx/fivem/blob/d65a864014e218407c3a47e14fb91019775f7230/LICENSE)

CodeWalker's source readme states an educational-purpose release; no general license file was found in the inspected repository root. Existing inclusion in another tool does not itself establish distribution rights for a new inspector. [Source readme](https://github.com/dexyfex/CodeWalker/blob/master/Readme_Src.txt)

These are dependency-selection constraints, not a legal conclusion about every possible implementation. Keep primary-source links and commit identities in the research record, write independently where appropriate, and obtain permission when needed. Do not label an implementation clean-room merely because it was rewritten after reading source. Do not redistribute Rockstar executables, keys, or clothing assets in the release or test suite.

## Final decision

Proceed with a bounded research prototype, not a universal limit-adjuster announcement. The preferred architecture is **complete dependency accounting + independently owned residency + verified parent admission**, enclosed by per-build native adapters and explicit failure handling.

Success means a supported over-limit clothing setup loads, renders, switches models, and tears down correctly without deleting DLC or changing clothing IDs. Merely avoiding the first crash, producing a green preflight, or compiling the ASI is not success.
