# Creator-defined suppressor profiles

The JSON-config release is **Suppressors Enhanced 1.2.1**, as designated by the
maintainer. It builds on the archived 1.2.0 source in
`.work/suppressors-vector-1.2.0/`; the original archive is untouched. Source
assembly, package, OIV and release-builder version metadata now targets 1.2.1.
The earlier development build was labelled 1.3.0 and installed for testing;
those binaries, archives, checksums and installation records retain that label
as historical evidence. The rebuilt 1.2.1 sleeve-tracking package replaced the
Enhanced installation on 2026-09-04; see the sleeve-tracking installation record.
The older in-repository mod source also carries the discovery backport, but
its 1.1.0 binaries are not the update to install.

A rebuilt **1.2.1 sleeve-tracking candidate** is now available under
`.work/suppressor-sleeve-tracking-20260904/`, now installed in Enhanced. It retains
JSON discovery and fixes the edition-gated sleeve refresh and streaming early
return. See [sleeve animation tracking](suppressor-sleeve-tracking.md) for the
test evidence and required in-game verification.

Creators can supply declarative JSON with their weapon package, without writing
C# or rebuilding the suppressor mod. There is no code execution, remote fetch,
include directive, or modification of GTA's `weapons.meta` schema.

## Minimal Vector profile

Save this as `suppressor-profile.json`:

```json
{
  "schema_version": 1,
  "profiles": [
    {
      "weapon": "WEAPON_A1_KRISS_VECTOR",
      "component": "COMPONENT_AT_PI_SUPP",
      "preset": "smg_45",
      "profile_code": "A1V45",
      "thermal_basis": ".45-class Vector gameplay approximation"
    }
  ]
}
```

The runtime computes the GTA hashes from the identifiers. The Vector is no
longer hardcoded in the candidate's built-in table. Its existing weapon/component
durability key is retained, so switching to JSON does not reset its saved wear.

## ALLIN1 packages

Add the JSON as a normal file owned by the **weapon's** `mod.toml`, for example:

```toml
[[files]]
source = "suppressor-profile.json"
destination = "scripts/ALLIN1/Catalogs/a1.krissvector/suppressor-profile.json"
# Include the actual SHA-256 when building your package.
```

Any contained directory under `scripts/` is supported. The basename must be
`suppressor-profile.json`; a document can contain multiple weapon profiles.
There is no new content-manifest capability or workbench field to add.

At successful runtime activation, the hosted mod checks the existing ALLIN1
enabled-package registry and the package's enabled installation receipt. It
reads only profile files explicitly listed in that receipt and verifies their
SHA-256 over the exact bytes before parsing. Uninstalled/disabled packages and
unowned loose files are not profile sources. Profiles in RPF archives are not
scanned. Rebuild and reinstall the weapon package after editing a managed file;
an in-place edit that disagrees with its receipt is rejected.

The Vector 0.5.0 candidate includes this owned file. Its existing DLC and GBAY
catalog bytes are unchanged. Thermal integration is optional: the weapon does
not gain a mandatory dependency on Suppressors Enhanced. Use the 1.2.1-or-newer
consumer to discover its JSON; earlier consumers do not support discovery.

## Standalone mod

Place one or more `*.json` files in `profiles/` beside the installed
`RealisticSuppressors.dll`, normally:

```text
GTA V/scripts/RealisticSuppressors/profiles/vector.json
```

Create the directory if needed. This mode needs no ALLIN1 installation or
receipt. Only that directory's immediate JSON files are read, not subfolders.
The hosted build intentionally does not scan this unowned standalone directory.

Changes take effect after a script/game restart. There is no filesystem watcher
or profile reload during a shot, and no automatic resetting of saved condition.

## Presets and overrides

Available presets: `pistol_9mm`, `smg_9mm`, `smg_45`, `rifle_556`, `rifle_762`,
`shotgun_12g`, and `sniper_magnum`. These reuse existing gameplay tuning, not
measurements of the creator's real-world weapon or suppressor.

Each profile may override these fields:

| Field | Accepted values |
| --- | --- |
| `weapon_class` | `sidearm`, `smg`, `rifle`, `shotgun`, `sniper`, `other` |
| `heat_per_shot_c` | Number from 0.01 to 100 |
| `cooling_half_life_s` | Number from 1 to 3,600 |
| `damage_onset_c` | Number from 21 to 1,500 |
| `critical_c` | Number from 526 to 1,600, strictly above damage onset |
| `rated_life_rounds` | Integer from 1 to 1,000,000 |
| `profile_code` | 1–16 uppercase letters, digits, underscores or hyphens |
| `thermal_basis` | 1–160 characters without control characters |

Without a preset, `weapon_class` and all five numeric fields are required.
Numbers must be finite JSON numbers, not strings or booleans. Unknown fields
and duplicate JSON keys are errors, so misspelled controls do not silently do
nothing. The existing global glow onset, smoke curve, model families, user
settings and attachment behavior remain unchanged; this schema does not add
arbitrary glow thresholds or custom visual geometry.

Version 1 supports **custom weapons using one of the eight existing stock
suppressor component types**. It does not yet support an arbitrary custom-can
mesh/heat-overlay family or multiple thermal identities for the same weapon.
Unsupported components are reported, not treated as a visually compatible can.

## Conflicts, limits and diagnostics

The 39 built-in profiles cannot be overridden. If multiple valid definitions
resolve to the same custom weapon hash, **all definitions for that weapon are
rejected**, regardless of file order or package name. Other unique profiles
remain available. An invalid document is rejected as a whole.

Documents must be UTF-8 (an optional UTF-8 BOM is supported), at most 64 KiB,
and contain 1–64 profiles. Discovery permits at most 128 profile files, 256
custom profile entries, 256 receipt files, 1 MiB per receipt and 8 MiB of total
file reads. Aggregate limit failures discard the custom catalog while retaining
built-ins. Paths cannot traverse out of the game directory or use reparse points,
UNC/absolute destinations, alternate data streams or ambiguous path segments.

The normal Suppressors Enhanced log reports `custom_profile_loaded` with the
weapon, component and source; `profile_discovery_warning` explains rejected
inputs; `profile_discovery_completed` records the totals. Verbose logging is not
required. Invalid optional profiles do not crash or disable built-in behavior.

## Validation and current scope

The automated suite exercises presets and explicit values; malformed JSON,
unknown keys and versions; receipt enablement, identity and hash checks; path
traversal and a real Windows junction; duplicate/built-in conflicts; size/count
budgets; Vector heat, cooling, wear and lifecycle lookup; and saved durability
continuity. The controller uses the discovered catalog for firing, hydration
and attachment lifecycle operations.

This is the discovery/packaging implementation. A dedicated React profile editor
and assembled custom-suppressor visual authoring are not part of this slice.
In-game testing remains required after installing the candidate.

Validation completed: **270 tests passed in each of the hosted and standalone
1.3.0 builds**, plus 228 tests for the older source backport. Enhanced and
Legacy hosted candidate ZIPs and the Vector 0.5.0 ZIP pass the real ALLIN1
manifest, archive and payload checksum validators. The Vector profile bytes
match the fixture used by the discovery tests. Candidate outputs and the
archive-relative source patch are under `.work/suppressor-json-config-20260904/`;
the weapon candidate is in the SDK's
`output/kriss-vector-allin1-0.5.0-json-profile-candidate/` directory.

### Enhanced installation — September 4, 2026

Installed hosted Suppressors Enhanced 1.3.0 and Vector 0.5.0 into
`D:/Programs/Steam/steamapps/common/Grand Theft Auto V Enhanced` with GTA closed.
The narrow update replaced the suppressor DLL/content manifest and Vector
content manifest/profile, refreshed their receipts while preserving uninstall
backups, and rebuilt the derived registry. Existing Vector DLC, GBAY catalog,
heat assets, settings and saves were not rewritten.

Backup, complete repair packages and verification evidence:
`D:/ALLIN1-SDK-Backups/suppressor-json-discovery/20260904_100121_078680`.
Local installation record: `.work/suppressor-json-config-20260904/installed.json`.
The actual installed DLL's discovery loader was invoked read-only against the
installed receipts and enabled registry: **one custom profile, zero diagnostics**,
resolving weapon hash `3449971877` to the Vector's owned JSON profile. This proves
installed discovery, not in-game rendering or heat/wear behavior. Gameplay testing
remains required. Legacy and standalone runtime candidates were not installed.
