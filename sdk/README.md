# ALLIN1 Add-on Content SDK

The SDK describes a GTA V add-on as a linked graph instead of a loose pile of
metadata files. Its `addon.json` manifest records every content node, the field
references between nodes, and the ordered installation stages. The desktop
launcher can then explain the graph field by field and detect incomplete or
incorrect integrations before the game archives are touched.

Open **Mods → Add-on Content SDK** in the ALLIN1 launcher to browse one live
package index. It combines built-in examples, external manifests remembered by
the viewer, local `mods/catalog` manifests, and installation receipts from every
configured Legacy and Enhanced game root. Installed receipts take precedence so
the displayed edition and state match the deployed package. The first built-in
example is the complete seven-color smoke-grenade feature; it also appears in
the main Mods package list as a read-only SDK package.

Opening or importing an external `addon.json` remembers its absolute manifest
and optional package-source path in the local, git-ignored
`sdk/imported_packages.json` registry. Payloads are never copied into the SDK.
When an installed package's original `mod.toml` remains available, the viewer
synthesizes a linked package graph from it. When only its receipt survives, the
viewer builds a smaller fallback graph from the receipt's managed files and DLC
registrations so the installation is still visible and auditable.

Use **Mods & SDK → Browse assets** for a read-only inventory of a loose package
or OIV/ZIP/RAR/7z. Common image and text formats receive an inline preview; GTA
binary assets receive format guidance and a bounded header view. RAR and 7z
members are streamed through the operating system's libarchive reader with file,
size, path, and preview limits; package code is never executed.
It demonstrates the details that are easy to miss when creating add-on weapons:

- independent weapon, slot, and ammo identifiers;
- a current-build metadata template rather than a stale copied record;
- animation mappings for every relevant first- and third-person set;
- real GXT weapon-wheel labels;
- Scaleform `INT<signed weapon hash>` aliases for native wheel artwork;
- runtime behavior where metadata alone is insufficient;
- GBAY catalog and save-bound persistence links;
- nested-RPF filename/encryption requirements; and
- exact-entry backups, post-write verification, and snapshot rollback.

The linker is deliberately read-only. A passing report means that the declared
fields, source files, relationships, HUD hashes, and install stages are
internally complete; it does not silently authorize arbitrary RPF writes.

## Commands

```powershell
allin1 sdk list
allin1 sdk import-package C:\path\to\loose-dlc-folder
allin1 sdk import-package C:\path\to\package.oiv -o C:\path\to\package.addon.json
allin1 sdk import-package C:\path\to\vehicle.rar -o C:\path\to\vehicle.addon.json
allin1 sdk audit-folder C:\path\to\test-mods -o C:\path\to\package-audit.md
allin1 sdk oiv-plan C:\path\to\package.oiv -o C:\path\to\oiv-plan.md
allin1 sdk oiv-plan C:\path\to\package.oiv -o C:\path\to\oiv-plan.md --managed-package C:\path\to\reviewed-package
allin1 sdk dlc-inventory "C:\path\to\Grand Theft Auto V" -o C:\path\to\dlc-inventory.md
allin1 sdk compile-vehicle-data C:\path\to\vehicle-package -o C:\path\to\compiled-data
allin1 sdk inspect-rpf C:\path\to\dlc.rpf -o C:\path\to\rpf-inventory.txt
allin1 sdk index-rpf C:\path\to\dlc.rpf --gta-path "C:\path\to\GTA V" -o C:\path\to\dlc-index.json
allin1 sdk extract-rpf-entry C:\path\to\dlc.rpf vehicle.ytd --archive-path x64/vehicles.rpf -o C:\review\vehicle.ytd
allin1 sdk plan-rpf-replacement C:\path\to\dlc.rpf vehicle.ytd C:\payload\vehicle.ytd --archive-path x64/vehicles.rpf -o C:\review\replacement-plan.json
allin1 sdk inspect-package-rpfs C:\path\to\package.rar -o C:\path\to\rpf-reports
allin1 sdk validate sdk/examples/colored_smokes/addon.json
allin1 sdk link sdk/examples/colored_smokes/addon.json -o smoke-link-report.md
```

## Package intelligence

**OIV recipe preview** implements the operation names used by the pinned
CodeWalker OIV parser. It inventories archive containers, file additions,
deletes, text edits, XML/PSO XPath edits, defragmentation, and unknown commands
without invoking the installer. Managed export extracts only declared sources
and writes checksummed `[[files]]`/`[[rpf_entries]]` records when the entire
recipe fits ALLIN1's ownership and rollback model. Partial conversion is never
silently presented as safe.

**DLC inventory** extracts the active edition's `dlclist.xml` read-only and
compares registration counts against stock and `mods` package folders and local
install receipts. The Markdown/JSON result distinguishes Rockstar stock,
external, ALLIN1-managed, receipt-only, and registration-only packages.

**Vehicle data compilation** joins visible `vehicles.meta`, `handling.meta`,
`carvariations.meta`, `carcols.meta`, stream assets, text dictionaries, and
setup/content registration. It emits `vehicles.json`, `vehicles.csv`,
`vehicles.xlsx`, `unresolved.csv`, and `vehicle-data-report.md`. Opaque binary
archives and dictionaries remain explicit unresolved evidence.

## Importing an existing package

Use **Import DLC folder…** or **Import archive…** in the SDK viewer, or run
`sdk import-package`, to create a review-only `addon.json` draft. The importer:

- inventories loose folders and ZIP/OIV/RAR/7z members without installing them;
- rejects traversal paths, encrypted members, oversized packages, and XML
  entity/DTD declarations;
- discovers visible weapon, ammo, animation, weapon-shop, vehicle, handling,
  variation, tuning-kit, streamed-asset, and package-registration records;
- classifies ScriptHookVDotNet DLLs, native ASIs, ReShade add-ons/shaders,
  standalone DLC archives, replacement assets, mixed layouts, edition folders,
  documented dependencies, and exact RPF target hints;
- creates linked nodes for the relationships it can prove; and
- reports missing ammo, animation, storefront, vehicle model/texture/tuning,
  DLC registration, UI, runtime, and rollback work.

A loose-folder draft is written at that package's root so relative source paths
remain valid. Nested RPF files are intentionally opaque to this first importer:
they are inventoried and flagged for inspection with the Enhanced-aware
RpfPatcher/CodeWalker toolchain. Import does not make a package installable. The
author must review the inferred fields, resolve every linker error, identify
exact current-build archive targets, and define verification and rollback.
Every generated draft is marked review-only and deliberately fails linking with
`imported_draft_requires_review`; a lack of recognized weapon or vehicle records
can never be mistaken for installation approval. Use **Audit package folder…**
or `sdk audit-folder` to produce one Markdown assessment across a mixed test-mod
directory, while partial `.crdownload` files are excluded.
For loose RPFs, **Open RPF explorer** or `sdk index-rpf` builds a searchable
root/nested hierarchy with storage metadata, resource versions, flags and
hashes. Entries can be extracted read-only and passed directly to native XML or
texture preview. Replacement planning is inert: it writes the target and
payload hash plus mandatory backup, verification and rollback requirements.

For packaged RPFs, **Inspect package RPFs** or `sdk inspect-package-rpfs`
streams only the declared RPF member into temporary storage, inspects its file
tree and XML with the detected edition keys, follows first-level nested RPFs,
summarizes resource versions, writes text reports, and deletes the temporary
copies. It never writes to the game directory.

## From inspection to a managed package

An archive scan is deliberately not an installation authorization. After the
link report passes, create a normal local `mod.toml` package and declare every
add-on pack that must appear in `dlclist.xml`:

```toml
type = "rpf"
dependencies = ["openrpf"]
dlc_packs = ["my_vehicle_pack"]

[[files]]
source = "payload/dlc.rpf"
destination = "mods/update/x64/dlcpacks/my_vehicle_pack/dlc.rpf"
sha256 = "<64 lowercase hex characters>"
```

The pack name must exactly match its payload directory. ALLIN1 copies and
hash-validates the payload first, then registers the pack through the
edition-aware RPF helper. Disable, uninstall, failed install, and failed update
paths unregister or restore that entry together with the managed files. If the
entry already existed, ALLIN1 records it as externally owned and never removes
it during package lifecycle operations.

## Manifest shape

An integration contains three lists:

- `nodes` describe authored records and the fields consumed by GTA, a loader,
  the native UI, or an ALLIN1 runtime system;
- `references` link a field on one node to a field on another and require the
  values to agree; and
- `install_steps` explain the ordered target, source, and merge strategy.

Supported node kinds include `weapon`, `ammo`, `animation`, `text_label`,
`hud_alias`, `runtime`, `storefront`, `vehicle`, `handling`,
`vehicle_variation`, `tuning`, `streaming`, `dlc_registration`, `archive`, and
`package`, plus `script_plugin`, `asi_plugin`, `reshade_addon`, and
`replacement` for non-DLC and mixed packages. Each kind has a small required-field contract in
`allin1.addon_sdk.REQUIRED_FIELDS`. The desktop field inspector supplies
plain-language help for the common fields.

The machine-readable schema is [addon.schema.json](addon.schema.json). Start by
copying [the colored-smoke example](examples/colored_smokes/addon.json), keep all
paths relative to your integration root, and run `allin1 sdk validate` after
each new link.

## Safety boundary

Do not distribute a whole replacement `update.rpf` or a nested archive copied
from another game build. An installer should read the user's current archive,
merge only the declared records, save exact originals first, reopen and verify
the result, and retain a rollback path. The example smoke installer follows
that model and is intended to be studied, not treated as permission to patch
unknown archives without validation.
