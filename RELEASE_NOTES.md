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
