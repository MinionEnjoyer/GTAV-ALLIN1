# GTA V ALLIN1 0.5.0

Version 0.5.0 unifies the launcher, in-game client, and standalone SDK around a
guarded package lifecycle and a more consistent professional desktop identity.

## Launcher, client, and SDK integration

- Retired the pre-release offline-launch toggle after it proved capable of
  blocking Rockstar authentication. ALLIN1 now uses the normal signed-in game
  launch flow and removes only offline arguments it can prove it previously added.
- Added structured SDK agent commands to list, install, and uninstall validated
  packages through approved console/API actions with two-stage write consent,
  closed-game checks, audit logging, checksums, receipts, backups, and rollback.
- Restored distinct high-DPI launcher and SDK branding across window headers,
  title bars, taskbar icons, packaged executables, and release documentation.
- Kept the launcher as the interactive package and game-launch workspace while
  exposing the same guarded package lifecycle to developer and AI tooling.
- Bumped the launcher, in-game client assembly, and SDK release surfaces
  together to 0.5.0.
- Made Enhanced Police AI, experimental NPC physics, physics diagnostics, and
  enhanced smoke effects explicit opt-ins. New installations and missing
  settings now fail closed, while existing saved user choices remain intact.
- Disabled verbose launcher/client logging in the public example profile so a
  clean installation starts with production-oriented settings.

# GTA V ALLIN1 0.4.9

Version 0.4.9 promotes the standalone SDK from a read-only inspection surface
to a guarded authoring workbench while keeping every archive mutation outside
stock GTA V files.

## SDK and launcher integration

- Added transactional root and first-level nested RPF replacement, addition,
  and deletion with checksummed plans, whole-archive backups, staged
  verification, collision checks, rollback, and per-archive process locks.
- Added persistent transaction history, interrupted-operation recovery, stale
  lock inspection, and progress reporting in both the SDK desktop UI and CLI.
- Added a real-archive canary that operates only on a disposable copy and proves
  replace/add/delete rollback by comparing the final SHA-256 with its untouched
  source. The Enhanced canary passed against a real installed archive.
- Added semantic META/XML comparison and parse/serialize/reparse validation so
  formatting-only changes can be distinguished from meaningful game-data
  changes; binary PSO/RBF files remain routed to native inspection.
- Fixed filename-sensitive Enhanced NG archive staging in the SDK and RPF
  helper while preserving the exact outer archive name throughout a mutation.
- Integrated the dedicated ALLIN1 SDK logo and favicon into the desktop app,
  release package, documentation, and Windows build.
- Added an in-app SDK Console backed by the real CLI, with Source-style
  progressive command, option, path, and history suggestions, Tab completion,
  keyboard history, persistent recall, and non-blocking command execution.
- Bumped the launcher and in-game assembly version surfaces together to 0.4.9;
  the launcher continues to discover and checksum-install the latest public SDK
  release through its existing Install / Manage SDK panel.

# GTA V ALLIN1 0.4.8

Version 0.4.8 expands GBAY into a save-safe weapon workbench and develops the
optional physics experiment into a coordinated police-response layer. It also
hardens DLC vehicle compatibility, input handling, diagnostics, and the
launcher controls used to configure the new systems.

## GBAY weapon workbench and interface

- Split **Purchase Weapons** and **Customize Weapons** into adjacent main-menu
  destinations so buying and modifying a weapon cannot be confused.
- Added a dedicated, controller-aware customization presentation with weapon
  attachment and finish catalogs, equipped-state feedback, ammo refills,
  shouldered preview poses, focused camera transitions, and clean restoration
  of the player and world when the workbench closes.
- Kept every GBAY purchase transactional until a real Story Mode save commits
  the character state, including weapons, attachments, ammunition, and gear.
- Added seven separately stocked GBAY smoke colours as independent, labeled
  weapon-wheel throwables with separate ammo pools and per-throw consumption.
  Capped each colour at five, reused the BZ Gas wheel icon, removed Reload
  cycling, and left native Tear Gas unchanged.
- Layered a bounded, colour-tinted bloom over the persistent smoke field,
  enlarged its scale and footprint without adding emitters, retired settled
  canisters to stop persistent rolling audio, added retry-safe particle loading
  and sampled emission diagnostics, and verified that Enhanced already supplies
  the M18-shaped smoke canister.
- Required collided, grounded stability before deployment; removed native
  trail/primed/explosion smoke from the generated color ammo; isolated colored
  fields from multicomponent/native fallbacks; and added sampled projectile
  motion, settlement, backend, overlap, and expiration diagnostics.
- Improved GBAY readability, scrolling, navigation repeat behavior, catalog
  recovery, preview cleanup, and structured client logging.

## Experimental physics and Enhanced Police AI

- Expanded impact, fall, blast, push, weapon-hit, disarm, and recovery behavior
  with optional NaturalMotion and archive-level physics tuning.
- Added coordinated police containment, defensive lines, bounded stack-and-rush
  tactics, vehicle barriers, withdrawals, smoke cover, casualty collection,
  stabilization, weapon recovery, and CASEVAC support.
- Added recon, CAS, and safe hot-rope helicopter roles. Insertions prefer clear
  rooftops or screened positions behind established firing lines, and stalled
  scripted flight legs now return control to GTA's ambient aircraft AI.
- Added comprehensive structured telemetry for physics reactions, tactical
  decisions, cover failures, rappel interception, insertion planning, aerial
  mission progress, and CASEVAC deferrals.

## DLC vehicles and launcher

- Split the developer experience into a separate `ALLIN1-SDK` repository and
  desktop application. The launcher now hands off to that external process,
  while the SDK owns its linker, importer, native asset viewer, RPF explorer,
  help center, CLI, examples, pinned CodeWalker source, and release lifecycle.
- Added an optional **Install / Manage SDK** panel backed by public SDK releases.
  Downloads require a matching win-x64 asset and published SHA-256, then every
  internal file is verified before an atomic per-user install. Update, repair,
  offline package install, open, and uninstall remain isolated from GTA V.
- Reworked the launcher around persistent Setup, Gameplay, Input, Packages,
  and Activity work zones. Application menus and contextual dropdowns replace
  dense button rows; the footer now keeps only game actions, save, and launch.
- Added a searchable, contextual Help Center and a dedicated SDK help corpus.
  The SDK, asset viewer, and RPF explorer expose their own Content, Review,
  Archive/Entry, Package Intelligence, and Help menus.
- Applied Story Mode getaway-vehicle suitability rules to DLC vehicles and
  prevented aircraft and watercraft from entering ordinary car garages.
- Improved traffic and special-vehicle compatibility for seats, weaponized
  vehicles, and nonstandard vehicle classes.
- Added launcher configuration for controller bindings, experimental physics,
  archive tuning, and **Enhanced Police AI**.
- Added a read-only **Add-on Content SDK** linker/viewer to the standalone SDK.
  It explains and validates cross-file metadata, animation, native text,
  Scaleform HUD, runtime, storefront, packaging, and rollback fields. The
  complete colored-smoke integration ships as its first example.
- Listed the colored-smoke integration in the launcher Packages catalog and
  the SDK as a self-contained built-in example, and added safe loose-folder/OIV/ZIP inspection
  that generates a reviewable SDK draft without extracting or installing the
  source package. The importer rejects unsafe archive paths and XML entities,
  discovers visible weapon/ammo/animation/shop links, and flags opaque RPF and
  unresolved integration work for author review.
- Refocused the player-facing desktop application as **ALLIN1 Launcher** and
  moved authoring into **ALLIN1 SDK**. Both share a restrained visual system,
  clear work zones, contextual actions, readable typography, and help surfaces.
- Added a read-only SDK package asset viewer for loose DLC folders and OIV/ZIP
  packages, with filtering, image/text previews, binary-format guidance,
  bounded header inspection, hashing, and JSON inventory export.
- Expanded the asset viewer with native RAGE header parsing, structured
  CodeWalker XML for YTD/YDR/YDD/YFT/YBN/YMAP/YTYP/YMT/GXT2, automatic
  Legacy/Enhanced decoder fallback, and visual YTD texture contact sheets.
- Added an interactive RPF explorer backed by a versioned JSON helper contract.
  It follows root and nested archives, searches and filters exact entries,
  exposes storage/resource/page metadata, extracts nested assets for preview,
  exports JSON/CSV, and creates inert checksummed replacement safety plans.
- Extended package inspection to RAR/7z and linked vehicle, handling,
  variation, tuning, streaming, and DLC-registration metadata. Missing model,
  texture, tuning, and resource-manifest assets now fail visibly in SDK reports.
- Expanded the importer beyond vehicle and weapon packages: mixed test folders
  now distinguish managed scripts, native ASIs, ReShade add-ons and shaders,
  replacements, standalone DLC archives, edition layouts, dependencies, and
  inferred RPF targets. PE headers are inspected without executing plug-ins,
  and every generated draft remains explicitly blocked for author review.
- Added batch folder audits plus temporary, read-only inspection of packaged and
  first-level nested RPFs. Reports retain resource-version evidence while all
  extracted inspection copies are removed after the audit.
- Added edition-aware loose-RPF inventory and transactional, manifest-owned DLC
  registration. RPF packages declare `dlc_packs`; install/enable registers them,
  while rollback/disable/uninstall removes or restores their entries.
- Added independent Legacy and Enhanced installation paths plus an active-target
  selector. Package rows now show Legacy, Enhanced, dual-edition, or unresolved
  tags and route installs only to a compatible configured game root.
- Connected the Add-on Content SDK to remembered external manifests, the local
  package catalog, and installation receipts from every configured Legacy and
  Enhanced root. Installed packages now appear in the SDK without duplicating
  their payloads, with a receipt-only fallback when their source was removed.
- Added reviewed `mixed` packages and transactionally managed `[[rpf_entries]]`.
  Exact archive entries are backed up, verified, collision-checked, toggled, and
  restored without replacing unrelated RPF content.
- Corrected custom smoke artwork by linking all seven signed weapon hashes to
  both native BZ Gas HUD frames; unknown hashes no longer fall back to C4.
- Added a read-only OIV operation workbench based on the OIV 2.x grammar. It
  previews ordered archive/file/delete/text/XML/PSO operations and exports a
  managed package only when every action reduces to an owned file copy or exact
  existing-RPF entry transaction.
- Added an edition-aware DLC inventory that compares Rockstar and modded
  `dlcpacks` folders, live `dlclist.xml` registrations, duplicates, missing or
  incomplete payloads, and ALLIN1 receipt ownership without rewriting anything.
- Added a cross-file vehicle data compiler joining `vehicles.meta`,
  `handling.meta`, `carvariations.meta`, `carcols.meta`, streamed models and
  textures, labels, and package registrations. It exports JSON, CSV, XLSX,
  Markdown, and a separate unresolved-reference table.

## Release

- Bumped the desktop launcher and in-game assembly together to 0.4.8.
- Rebuilt and verified the client and automated test suites for the release.

---

# GTA V ALLIN1 0.4.6

Version 0.4.6 is a focused GBAY and garage-packaging hotfix. It corrects the
five Ammu-Nation armor previews, prevents repeat gear purchases, and ensures
every install or repair restores the standalone map data required by the DLC
garage interiors.

## GBAY inventory and artwork

- Realigned Super Light, Light, Standard, Heavy, and Super Heavy Armor with
  their correct in-game Ammu-Nation vest artwork.
- Fixed gear ownership normalization so a newly purchased item is recorded
  before it is equipped. Already-owned gear can no longer deduct money again.
- Added regression coverage for case-insensitive duplicate gear purchases.

## Standalone garage maps

- Restored verified `allin1_maps` generation and registration during every
  install and repair. This fixes the Garment Factory and other DLC-backed
  garages becoming unavailable after the previous pack was cleaned up.
- Made a missing map pack a visible repair failure instead of silently
  completing with unusable garage interiors.
- Kept repair progress monotonic while locally extracting, converting,
  packaging, and verifying the required assets from the player's GTA install.

## Release

- Bumped the desktop launcher and in-game client together to 0.4.6.
- Rebuilt and verified the public release archive with the corrected client,
  artwork, installer, and automated coverage.

---

# GTA V ALLIN1 0.4.5

Version 0.4.5 is a garage-transition reliability release. It converts the
remaining multiplayer-dependent garage map data into standalone ALLIN1 packs,
stabilizes Harmony's five-floor interior, and keeps transitions hidden until
the destination is genuinely ready.

## Garage transition reliability

- Added standalone map-pack generation, installation, health checks, and
  repair support for DLC-backed Story Mode garages without enabling the global
  multiplayer map state.
- Standardized every garage entry, exit, and Harmony floor switch on a shared
  black-screen transition that waits for the destination interior, room,
  collision, and stored vehicles to remain ready before fading in.
- Moved Harmony's player arrival away from the elevator room boundary, restored
  all five floor shells and fixed detail sets, and made failed floor switches
  recover safely outside instead of exposing unloaded geometry.
- Hardened vehicle grounding and exterior release so stored vehicles regain
  collision, physics, controls, and a valid floor before the transition ends.
- Corrected the Davis, Garment Factory, Grapeseed, Paleto Bay, and yacht map
  leases and transition anchors uncovered by the full garage traversal pass.

## Release cleanup

- Bumped the desktop launcher and in-game client together to 0.4.5.
- Removed the temporary F11 garage traversal laboratory and its test-only
  runtime surface. F10 World Vector remains the sole production developer tool.
- Kept logs, caches, test files, source-only tools, debug symbols, local
  configuration, and build workspaces out of the checksum-verified public ZIP.

---

# GTA V ALLIN1 0.4.4

Version 0.4.4 expands the persistent garage network, adds the purchasable Galaxy
Super Yacht and its specialized helipad, and hardens GBAY, vehicle grounding,
traffic replacement, and Story Mode map streaming for general release.

## Garage and yacht expansion

- Added the 10-car Paleto Bay Garage using the Casino Penthouse Garage shell,
  with two internal elevator exits and separate exterior pedestrian and vehicle
  anchors at the Paleto Bay repair shop.
- Promoted Harmony Garage to five fully detailed floors and standardized
  collision-aware vehicle grounding across every garage.
- Added the Galaxy Super Yacht as a GBAY world asset. Its per-character,
  save-backed helipad accepts the two GTA Online yacht aircraft: the Swift
  Deluxe and SuperVolito Carbon.
- Streamed the yacht IPL directly in Story Mode without crossing the global
  multiplayer-map boundary, eliminating approach/departure loading screens and
  avoiding missing Story interior furniture.

## GBAY and catalog refinement

- Replaced temporary 3D purchasing with an explicit destination picker covering
  every compatible garage and the Yacht Helipad.
- Reworked My Garage into a scrollable garage list and stored-vehicle panel,
  repaired confirmation layering, and completed vehicle sale-price fallbacks.
- Audited DLC vehicle listings and prices, added Special-world-asset purchasing,
  and preserved independent native-resolution preview assets.

## Runtime hardening

- Tightened traffic replacement ownership, driver, physics, mission, recent-use,
  and safehouse protections while retaining moving and parked ambient variety.
- Vehicles and yacht aircraft are staged immediately but committed only with a
  genuine Story Mode save, matching normal game persistence behavior.
- Expanded release coverage to 149 C# tests and 380 passing Python tests, with
  one intentional environment-specific skip.

---

# GTA V ALLIN1 0.4.3

Version 0.4.3 adds a fifth persistent garage, standardizes garage identity across the client, and
protects player and safehouse vehicles from DLC traffic replacement without reducing ambient
parked-car variety.

## Garage expansion and consistency

- Added the six-car Grapeseed Garage with independent per-character persistence, exterior vehicle
  and pedestrian access, GBAY delivery targeting, selling, recovery, map blips, and shared garage
  entry rules.
- Standardized the original locations as **Eclipse Garage** and **Harmony Garage** across GBAY,
  diagnostics, map labels, prompts, and release documentation.
- Applied the same mission, wanted-level, story-vehicle, capacity, size, and save-before-delete
  policies to Grapeseed that protect every existing ALLIN1 garage.
- Extended install, repair, diagnostics, backup recovery, and repository contracts to include the
  Grapeseed save independently from Eclipse, Harmony, Davis, and the Garment Factory.

## Traffic ownership protection

- Added narrowly scoped Story Mode safehouse parking zones for Michael, Franklin, Trevor, Floyd,
  and the Vanilla Unicorn so vehicles stored at those homes are never replaced by ALLIN1 traffic.
- Protected the current, last-used, and recently interacted player vehicles, including Rockstar's
  player-vehicle decorators, with a short identity cache that survives brief handle churn.
- Revalidate replacement candidates immediately before and during replacement. Ordinary parked
  vehicles outside protected safehouse storage remain eligible for ambient DLC replacement.

## Release qualification

- Bumped the desktop launcher and in-game client together to 0.4.3 and expanded automated
  contracts for the fifth garage, save deployment, naming, and safehouse traffic policy.
- Kept F10 World Vector as the sole production developer tool; retired labs and capture tools
  remain excluded from the checksum-verified public archive.

---

# GTA V ALLIN1 0.4.2

Version 0.4.2 completes the garage-grounding survey, retires the last temporary runtime
laboratory, and tightens GBAY quantity purchasing for stackable weapons.

## Production tool cleanup

- Promoted the completed 827-model grounding run into the packaged catalog: 821 stable measured
  offsets, six intentionally unsupported standalone models, and no unresolved outliers.
- Retired the F11 grounding laboratory, its mutable runtime writer, and its outlier checkpoint.
  F10 World Vector is now the only developer tool compiled into the public client.
- Removed the dormant Seat Lab programmatic harness and the retired preview-capture key alias;
  production seat switching retains its recovery logic and structured support logging without
  exposing developer-only entry points.
- Install and repair preserve valid measured offsets, merge the completed catalog, and remove old
  grounding-lab checkpoint files.

## Storefront and qualification

- GBAY throwable listings now show unit price × quantity and charge the actual stack granted;
  for example, 25 Sticky Bombs at $600 each cost $15,000.
- Moving DLC traffic remains paired with its driver while managed. Mission, cutscene, interior,
  wanted-level, and character-switch transitions purge off-screen managed traffic, and any moving
  vehicle that loses its driver is removed instead of coasting through the world empty.
- Bumped the desktop launcher and in-game client together to 0.4.2 and expanded release contracts
  to prevent retired tools from returning to public builds.

---

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
- Retired the completed runtime Seat Lab after promoting its findings into the generated metadata
  catalog and selector regression tests. F11 now runs only unresolved vehicle-grounding outliers;
  the old F12 fleet and focused grounding modes are retired.

## Catalog and qualification repairs

- GBAY now prices throwable purchases and refills by the actual quantity granted. Listing cards
  show the unit-price multiplication before purchase instead of charging one unit for a full stack.
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
