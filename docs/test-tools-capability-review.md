# Test tools capability review

> Historical checkpoint: results, commands and artifact identities below apply
> only to the described source/session. They do not qualify current 0.6.4.
> See the [current release guide](release-0.6.4.md) before using this as guidance.

Reviewed from `C:\Users\nivea\OneDrive\Desktop\test tools` on 2026-08-18.
The review was read-only: archive inventories, authored documentation, PE headers,
and bounded static strings were inspected; no third-party executable or plug-in
was loaded.

## Implemented from this review

The first three recommendations now ship as clean ALLIN1 implementations:

1. OIV operation-plan preview with all-or-nothing managed package export.
2. Edition-aware DLC folder/registration/receipt reconciliation reports.
3. Cross-file vehicle metadata compilation with JSON, CSV, XLSX, Markdown, and
   unresolved-reference outputs.

They do not bundle or invoke the reviewed third-party binaries.

## Recommended ALLIN1 additions

### 1. OIV recipe preview and managed translation — highest priority

`CodeWalker.OIVInstaller.exe` and `CodeWalker.OivsPacker.exe` represent the most
important remaining package-management gap. ALLIN1 can inspect OIV archives and
perform exact managed RPF writes, but it does not yet interpret an OIV recipe as
a visible ordered operation plan.

Add an OIV workbench that:

- parses and validates `assembly.xml`/package instructions without executing them;
- shows every copy, delete, archive edit, and DLC registration before approval;
- maps supported actions to manifest-owned files and `[[rpf_entries]]`;
- refuses unknown commands, live-game writes, ambiguous archive paths, and
  edition-incompatible resources;
- exports a reviewed `mod.toml` plus SDK graph rather than invoking a third-party
  installer.

### 2. DLC inventory and `dlclist.xml` reconciler — high priority

`DLCForge` statically identifies itself as an intelligent DLC-list compiler. It
scans stock and modded `dlcpacks`, preserves original packs first, removes
duplicates, and writes `dlclist.xml`.

ALLIN1 already registers owned DLC packs, so the useful extension is a read-only
inventory/reconciliation screen: show stock, externally owned, ALLIN1-owned,
missing, duplicated, disabled, and edition-specific packs; preview the merged
load order; then repair only after explicit approval.

### 3. Cross-file RAGE data compiler — high priority

`RAGE Data Compiler` scans `vehicles.meta`, `handling.meta`,
`carvariations.meta`, `carcols.meta`, GXT/OXT labels, and related data. It joins
models to display names, makes, classes, handling IDs, audio profiles, mod-kit
IDs, siren IDs, and DLC ownership, then exports a spreadsheet and unresolved
records.

This aligns closely with ALLIN1's vehicle catalog and SDK linker. Add a native
**Compile vehicle data** action that emits JSON/CSV/XLSX plus unresolved and
collision reports. Feed the resolved graph into GBAY, traffic, seat auditing,
getaway suitability, and add-on validation instead of maintaining parallel
manual lookup tables.

### 4. Particle dictionary browser and in-game preview — high priority

`Particle Effects Tester` is a ScriptHookVDotNet menu backed by a large authored
dictionary/effect list. It lets a developer browse particle dictionaries and
effects and adjust values in game.

Add an opt-in developer-only particle lab to ALLIN1 with search, favorites,
position/rotation/scale/color controls, bounded cleanup, and an exportable SDK
snippet. This would directly improve smoke, CASEVAC signals, weapon effects, and
future visual-effect integrations. Never enable it in normal gameplay profiles.

### 5. Per-instance handling sandbox — medium/high priority

`HandlingReplacement` exposes three native functions that clone, enable, inspect,
and restore handling data for one vehicle rather than changing every vehicle of
the same model. Its documentation declares both current Legacy and Enhanced
support.

The concept would make a strong vehicle-tuning workbench: compare stock and
experimental values on a disposable preview vehicle, restore on exit, and export
the resulting handling record. Treat the supplied ASI as an optional,
version-gated dependency; do not bundle or call it until source, license, game
build offsets, allocator behavior, and cleanup have been independently audited.

### 6. Model, texture, skeleton, and collision validation — medium priority

`TRIUM Skeleton Studio Free` documents offline, read-only YFT/YDD/YTD inspection,
skeleton comparison, structural validation, technical reports, a 3D model and
skeleton viewer, and texture browsing/PNG export.

These are valuable SDK capabilities, especially before installing peds, weapons,
or vehicle models. Extend ALLIN1's asset viewer with structural summaries,
skeleton/bone diffs, texture previews, resource-version checks, and validation
reports using the existing pinned format library. Treat TRIUM as a UX/capability
reference only; it is a self-contained third-party binary with no reusable source
in this test package.

### 7. YDR/YBN/YFT/YNV/YMAP XML validation and round trips — medium priority

`Escobar XML Tool 3` includes readable Python/MaxScript implementing CodeWalker
XML import/export for drawable geometry, LODs, skeletons, weights, materials,
textures, collisions, lights, fragments, navmeshes, and YMAPs. It also includes
round-trip tests and fixtures.

ALLIN1 should adopt the validation ideas—schema-aware XML inspection,
float/weight/tangent checks, round-trip diagnostics, and fixture-driven tests—but
not copy source until its license and provenance are explicitly compatible. A
full 3ds Max scene importer is outside the launcher; clean XML validation and
conversion belong in the SDK.

### 8. YTYP/MLO authoring checks — medium priority

`Esco GTA V YTYP Tools` provides 3ds Max workflows for archetypes, MLO rooms,
limbo, portals, entities, bounds, YMAP placement, and XML import/export.

Useful ALLIN1 additions are a YTYP/MLO validator and visual relationship graph:
missing limbo rooms, invalid room indices, exterior portals not connected to
room zero, reversed portal winding, unattached entities, bounds/extents errors,
duplicate GUIDs, and unresolved texture/physics dictionaries. DCC viewport
authoring should remain in Blender/3ds Max rather than being recreated in the
launcher.

### 9. Rockstar Editor camera export — lower priority

Static strings in `MudstarCamExport.exe` identify a drag-and-drop Rockstar Editor
project camera exporter with project-folder discovery, selectable output formats,
composition size, and output-folder management.

Camera-path import/export could help GBAY preview cameras, cinematic validation,
and future authored demos. Add it only after the Rockstar project format and the
tool's outputs are documented with fixtures; camera smoothing and transform
preview are more valuable than another opaque executable integration.

### 10. Community ScriptHookVDotNet Core host — research only

The `15.08.2026` package contains a native CoreCLR host, reload/input libraries,
standard native bindings, and a `.NET 10` runtime configuration. This could
eventually enable modern .NET plug-ins and reloadable development scripts.

It is also a process-wide runtime/loader replacement with no included user
documentation in the test archive. Keep it out of automatic installation. A
future compatibility checker may inventory runtime version, native database,
loader conflicts, and edition support, but ALLIN1 should continue using its
known-good ScriptHookVDotNet path until this host is separately researched and
qualified.

## Suggested delivery order

1. OIV recipe parser and operation preview.
2. DLC inventory/reconciler.
3. RAGE vehicle-data compiler and unresolved-report export.
4. Particle lab.
5. Asset/skeleton and YTYP/MLO validators.
6. Optional per-instance handling sandbox.
7. Camera project tooling and alternate .NET host research.

No reviewed package should be bundled merely because it is useful. Concepts can
guide clean ALLIN1 implementations; third-party code or binaries require an
explicit license, provenance, edition, dependency, and security review first.
