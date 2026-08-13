# GTA V ALLIN1 0.4.1

Version 0.4.1 expands the animation-only seat selector into a metadata-backed system covering the
complete base game and installed DLC catalog, with a focused runtime laboratory for unconventional
and mounted-weapon layouts.

## Vehicle seat catalog and selector

- Added a read-only RPF audit that resolves active `vehicles.meta` and `vehiclelayouts*.meta`
  definitions across `common.rpf`, `update.rpf`, modern DLC packs, and early DLC consolidated in
  root `x64*.rpf` archives.
- Generated seat, occupant-access door, hatch, Rockstar layout, and source-pack records for all
  935 installed Enhanced vehicle models with no unresolved layouts or extraction warnings.
- Replaced generic high-index seat names with model-specific labels. Physical stations such as bed,
  roof, top, rear, missile, cannon, grenade, and aircraft turrets are identified independently from
  ordinary rear, bench, bed, rappel, deck, and interior passenger seats.
- Corrected the Caracara, Technical, Turreted Limo, Barrage, Insurgent, APC, Khanjali, Valkyrie,
  and other high-risk layouts. Armored Boxville and Savage passenger seats are no longer described
  as turrets.
- Seat Lab now records Rockstar metadata count, GTA runtime count, ALLIN1 selectable count, access
  geometry, and mismatch status separately. Shift+F11 retains the directed high-risk fleet suite.

## Catalog and qualification repairs

- Corrected the Grotti Veleno GT model identifier from the invalid `veleno` to Rockstar's
  `velenogt` across the storefront, price data, preview queue, web catalog, and generated client.
- Expanded repository contracts and runtime policy tests. The qualified release passes 349 Python
  tests, 66 production C# tests, the 91% coverage gate, and public archive verification.

---

# GTA V ALLIN1 0.4.0

Version 0.4.0 is a reliability release that replaces several permissive or synthetic safeguards
with transactional runtime behavior and production-backed tests.

## Data integrity and runtime repairs

- Garage files are decoded with a strict, side-effect-free JSON codec. Incomplete, malformed,
  duplicate-slot, and out-of-range data is rejected before live state changes, allowing the
  recovery copy to load without silently emptying a garage.
- GTA Online map data is reference-counted across the multi-floor and Davis interiors, and Story
  Mode map state is restored after the final garage closes or emergency recovery runs. This
  prevents missing beds, furniture, and other interior variants.
- Every garage shares the same mission, protected-story-vehicle, and vehicle-size admission
  policy. Unknown protagonist models fail closed instead of inheriting Michael's data.
- DLC traffic replacements are created and validated off-screen before the original vehicle is
  removed, preventing failed model loads from deleting ambient cars and occupants.
- Online weapon and gear state is backed up with character saves, native ammunition failures are
  reported accurately, and unsupported characters cannot mutate protagonist inventories.
- Seat selection improves mounted-turret labeling and animation routing without adding teleport
  fallbacks.

## Diagnostics and qualification

- ScriptHookV, ScriptHookVDotNet, ASI loaders, OpenRPF/OpenIV, and the ALLIN1 client are validated
  as x64 PE binaries rather than accepted solely because a file exists.
- GBAY distinguishes an installed preview plug-in from texture streaming that has actually been
  observed in the current game session.
- Release qualification now consumes hashed coverage, client assembly, and fresh single-session
  smoke artifacts. Replayed, edited, stale, or mixed-session evidence is rejected.
- Added a .NET Framework test assembly for production garage parsing, admission rules, map leases,
  protagonist identity, ammunition handling, and preview diagnostics. These tests now run in local
  release scripts and both Windows CI paths.
- Install / Repair now reports determinate percentage progress, helper tools run without flashing
  console windows, and repeated game-launch requests are suppressed during the Steam/Rockstar
  handoff.

## Verification

- 36 production C# tests and 340 Python/repository tests pass for this source release. The optional
  real Windows preview-tool integration remains isolated to its toolchain-qualified CI job.

---

# GTA V ALLIN1 0.3.1

Version 0.3.1 is a stabilization release focused on garage data integrity, gear management,
map-marker consistency, and a clearer desktop launcher.

## Fixes and safeguards

- Garage saves now preserve the vehicle's native model hash instead of relying on its display
  label. Existing Furore GT entries saved as `furore` migrate to `furoregt`, keeping their plate
  and customization data, and uncatalogued vehicles no longer become permanently protected.
- Drive-in storage verifies that the garage save succeeded before removing the outside vehicle.
- Character gear can be unequipped and re-equipped without another purchase, with owned-state
  handling for armor, parachutes, night vision, and juggernaut armor.
- ALLIN1 location markers use the active protagonist's color consistently.
- Added regression coverage for native vehicle identities, legacy garage migration, gear ownership,
  marker colors, and duplicate-purchase behavior.

## Launcher improvements

- The current installation state is summarized as ready, update available, missing dependencies,
  or game folder required, with the next action stated plainly.
- Launch, repair, save, and refresh controls remain accessible from every page, including at the
  supported minimum window size.
- Added unsaved-settings protection, operation progress, keyboard shortcuts, activity-log copy and
  clear controls, and a shortcut to the diagnostics/log folder.
- Improved status readability, destructive-action separation, tab navigation, scrolling, and
  version visibility.

## Qualification

- The Python and repository-contract suite, C# Release build, real Enhanced installation health
  check, structured in-game smoke report, and public archive verification must all pass before the
  0.3.1 package is published.

---

# GTA V ALLIN1 0.3.0

Version 0.3.0 is the first public release built around the complete GBAY preview pipeline and the
expanded Story Mode garage, weapon, gear, and character systems.

## Highlights

- GBAY now includes vehicle, weapon, and gear storefronts with streamed preview artwork,
  categories, search, favorites, ownership filtering, duplicate-purchase protection, and sales.
- Persistent storage now covers Eclipse Towers, the three-floor garage, and the 10-car Davis Auto
  Shop, including interior customization and improved placement for varied vehicle dimensions.
- The vehicle preview set has been rebuilt and packaged into verified YTD dictionaries, including
  water-based captures for boats and native-resolution PHAT and ALLIN1 artwork.
- Character tools now support money, skills, loadouts, gear, outfits, and per-protagonist saves.
- DLC traffic, police replacements, animation-first seat selection, safe mode, accessibility
  controls, health checks, diagnostics, and local third-party mod packages are integrated into one
  launcher.

## Release hardening

- Removed screenshot capture, marker-debug, spawn-notification, log-upload, and other retired
  development surfaces. The F10 world-vector overlay remains as the single location-authoring tool.
- Replaced the private-token updater with a link to the latest checksum-verified GitHub Release.
- Added a strict public-file manifest, deterministic SHA-256 package generation, archive
  verification, version-consistency checks, and release-contract tests.
- GBAY preview artwork is now a supported, default-on option; it can still be disabled when
  troubleshooting an OpenRPF/OpenIV loader conflict.

## Installation

Extract the release to a new folder, run `install.bat`, then open `manager.bat`. ScriptHookV and
ScriptHookVDotNet Enhanced remain required. Enhanced preview artwork requires OpenRPF; Legacy uses
OpenIV.asi.

ALLIN1 is for GTA V Story Mode only. Do not use it in GTA Online.
