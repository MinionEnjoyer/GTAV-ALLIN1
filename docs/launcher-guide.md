# ALLIN1 Launcher guide — 0.6.5

0.6.5 is an unsigned portable release. The desktop is React/Tauri v2; bundled Python provides its services
and command-line tools, with no Tkinter fallback. Do not assume an
older downloaded build has every action described here.

## Before starting

Use GTA V Story Mode only. Select Legacy or Enhanced explicitly and verify its
directory. Close the game before installing, repairing, updating, disabling or
removing packages. Keep save files, authored content and recovery receipts.
Do not use the modded launch configuration in GTA Online.

### Cancelling a launch

While the reviewed launch is preparing, **Cancel launch** stops the remaining
preparation before GTA is started. During preview generation it stops the owned
renderer and retains completed cached previews. The panel stays locked until
cleanup finishes; cancellation does not undo already-completed settings saves.
Once launch is handed to Steam/Rockstar, cancellation is disabled. It never
terminates a running game. Starting again requires a fresh review.

In the same CLI `agent-api` session, `cancel_launch` accepts the active
`review_id` while its launch `apply` is running. Wait for that apply's terminal
`result.status: cancelled`; the cancellation acknowledgement alone only means
the signal was accepted. Stale review IDs cannot cancel another launch.

### Acknowledging warnings

When startup monitoring stops with a warning (for example, a Reactor disconnect
or timeout), choose **Acknowledge warning** in the Reactor startup panel. The
Launcher returns to its normal status unless another error, warning, operation,
or unsaved draft needs attention. Previous startup details remain in a collapsed
panel and the acknowledgement appears in this session's Activity view. Completed
operations with warnings have their own acknowledgement button.

Acknowledgement does not reconnect services, retry an operation, mark the game
ready, change files, or delete logs. It lasts for the current Launcher session;
a new launch can report the same warning again. Warnings from a still-active
startup monitor cannot be acknowledged until monitoring finishes. Use Reconnect
service when the Launcher service itself needs reconnection.

### Cached GBAY catalog previews

Before launching Story Mode, the launcher validates enabled managed packages
and checks the mounted DLC list. It then prepares missing stock/add-on weapon,
vehicle, and equipment images using isolated Blender/Cycles rendering. Unchanged artwork is reused; changed
archives, catalogs, editions or renderer builds invalidate the relevant cache.
Rendering completes the selected queue without a whole-catalog time cap (up to
180 seconds per item); discovery is separately bounded. Rendering starts with one
isolated Blender worker; the live Render performance control allows up to eight
within the CPU limit, with RAM/performance warnings and a critical-memory guard.
It prefers supported GPU acceleration with a bounded CPU fallback. Worker
numerical libraries use one thread each to avoid nested oversubscription.
Discovery and cache/index publication remain
serialized. Cancel Launch propagates to every worker; none survives into launch.
Failures keep
the existing artwork and do not block launch. No thumbnail rendering runs in GTA.

These are textured base-model catalog previews, not exact GTA shader renders or
live previews of the player's selected attachments. Unsupported, ambiguous or
unowned assets fall back to existing artwork. Vehicle fragments include wheels,
one LOD per component, inherited/shared textures, and a showroom camera.
Vehicles use an asphalt-floor/concrete-wall studio background. Weapons and gear
retain their pegboard backdrop. All categories use soft warm key light, cool fill
and subtle rim highlights. Vehicles receive a floor contact shadow.
The background asset participates in cache identity: Update Previews
regenerates the old style, while Quick Launch keeps existing published pictures.
Juggernaut armor has no supported standalone
prop; unsupported equipment uses downloaded defaults when installed, otherwise a placeholder. Both game editions
have separate, reusable caches. This does not reproduce GTA's paint/glass shaders
or the player's current vehicle customization.

The launch review has two modes: **Quick Launch** and **Update Previews**.

Under Update Previews, enable **Missing previews only** to keep intact generated
images even if model or renderer revisions have changed. Only catalog entries
without an intact indexed generated image need a preview; available valid cache
entries can restore missing files without rendering. The category checkboxes
still apply. Active package/source validation and stale-image cleanup still run;
this does not authorize disabled or modified packages. Uncheck it to refresh
outdated previews normally. CLI/API/agent `launch` and `prepare_previews` requests
accept the boolean `missing_previews_only` with the same behavior.
Both show per-category **existing / total** generated preview counts for the
selected game and enabled installed catalogs. Throwables and unsupported gear
are excluded; downloaded default artwork does not inflate the count. Counts are a
lightweight check of published image files, not source/cache validation. No RPF
discovery or rendering runs to obtain them, including in Quick Launch. Unreadable
catalogs or indexes display **Unavailable**, never a misleading complete count.
The same coverage is exposed as `preview_counts` in CLI/API/agent launch and
`prepare_previews` reviews. Reopening the review refreshes the counts.
Update Previews shows **Weapons**, **Vehicles**, and **Gear** checkboxes; checked
categories generate missing images. Unchecked categories still validate and reuse
cached images, but do not render new ones. Keep at least one category selected,
or choose Quick Launch to skip the preview phase entirely. Category choices are
preserved when switching modes. There are no nested skip-all controls.

**Quick Launch** opens a normal launch review with the entire optional preview
phase disabled, including model discovery. It leaves existing artwork unchanged
(no fresh artwork validation or regeneration). Missing images use an installed
default preview pack or the UI placeholder. Mod safety checks, confirmation, garage preparation and
Reactor initialization still run. Quick Launch is a per-launch choice, not the
default for subsequent normal launches.

CLI/API/agents can use `skip_preview_categories: ["vehicles", "gear"]` on either
`launch` or `prepare_previews`, and `quick_launch: true` on `launch` to bypass the
entire preview phase. Unknown or duplicate categories are rejected. Quick Launch
takes precedence over render-skip choices; changing choices requires a new review.

CLI/API/agents can use the reviewed `prepare_previews` action without launching
GTA, or pass `skip_previews: true` with `launch`. Both use the same approval and
game-closed checks as the desktop. Results include rendered/cached/pending counts,
selected weapon IDs, cache keys and failures. The latest receipt is stored in the
launcher's per-game `weapon-previews` cache (including vehicle/gear subdirectories).
Generated PNGs and portable indexes are published under
`plugins/ReactorV/ui/assets/allin1/generated-weapons`, `generated-vehicles`, and
`generated-gear`. `prepare_previews` reports separate category results; launch
returns them in `catalog_previews` and retains the `weapon_previews` compatibility field.

### Separate default preview pack

Rendered fallback images are no longer bundled with the launcher or copied with
the Reactor UI. GBAY prefers locally generated images, then a separately installed
default pack, then its lightweight placeholder. The GitHub download pack is not
published yet; this build does not automatically download one. Existing generated
caches are preserved. Legacy bundled artwork is retired through the existing
installer receipt on repair, without claiming generated/default preview folders.

The pack layout reserves `plugins/ReactorV/ui/assets/allin1/default-weapons`,
`default-vehicles`, and `default-gear`. Each contains a bounded `index.json` with
`schema_version: 1`, `owner: "allin1.default-previews"`, and an `images` mapping
from lowercase catalog model/weapon IDs to `<id>.<64-lowercase-hex-id>.png`.
Use the same portable IDs as the generated indexes; paths and arbitrary filenames
are not accepted. Only files with a valid PNG header, bounded dimensions (up to
4096 pixels per side) and size (up to 4 MiB) are selected. This is a lightweight
header check, not a full image decode. Restart the game
after installing a pack. Publishing/downloading a pack remains a separate step.

RpfPatcher and the isolated preview worker remain required for optional local
model discovery/extraction and rendering; RpfPatcher also supports mod/map
installation. Blender scene textures remain render inputs, not fallback images.
Quick Launch skips preview extraction and rendering entirely.

Install trusted, compatible ScriptHookV and the complete ScriptHookVDotNet
Enhanced runtime for the selected edition. The readiness check identifies
missing components; “prerequisites present” does not mean the ALLIN1 client is
installed. Review the Install / Repair plan to add it.

Reactor V is the preferred in-game UI path. It is a separately versioned
dependency with edition-specific validation, not the desktop React renderer.
Dependency downloads require consent. The compatibility renderer and older RPF
artwork path are not proof that Reactor acceptance passed.

## Legacy Python distribution

The batch names remain compatible, but no longer start a Python GUI:

1. Obtain and verify the exact package version you intend to use.
2. Run `install.bat` to prepare its Python environment and review prerequisite
   installation prompts. This is an installation action, not a read-only check.
3. Install a complete Tauri desktop, or set `ALLIN1_LAUNCHER_EXECUTABLE` to a
   complete local candidate's `allin1-launcher-desktop.exe`. Then open
   `manager.bat`; `allin1-gui` forwards to it without a console window.
4. Select the correct game path/edition, review Install / Repair and confirm.
5. Launch only when readiness permits, then use the configured GBAY key in Story
   Mode. Its source default is F9.

The standalone SDK is optional. Not having the ALLIN1 game client installed
does not prevent SDK package authoring.

## React development application

Follow [development setup](development.md). Debug builds use the repository's
Python service; the [candidate builder](../desktop/README.md) produces a bundled
shared Python runtime, native shell and hash-bound resources. End users need no
Python installation. Broader installer/live-game qualification remains incomplete.
Do not distribute the development executable by itself.

The React service uses `%LOCALAPPDATA%\ALLIN1\Launcher` for its state by default.
Existing repository configuration may be read as a compatibility starting point;
it is not silently migrated by merely opening a page. Save through a reviewed
action. Setup's **Import previous Launcher preferences** previews a previous
folder's `config.toml` and named profiles, copies only missing files, and preserves
existing preferences and the old folder. A changed source invalidates the review.
Profiles and package/SDK state are not interchangeable with GTA save data.

The UI holds editable drafts; Python validates and writes. A review is bound to
the selected inputs/state, expires, and is consumed once. If source files or
configuration change, reload and review again rather than reusing a token.

## Workspaces

| Workspace | Use | Current limits |
| --- | --- | --- |
| Setup | Choose paths/edition; inspect readiness; save profiles; review save, sync, install/repair, uninstall and launch | Native installer/launch lifecycle not yet qualified |
| Gameplay | Edit existing gameplay configuration and content-bound behavior | Secondary-control descriptions/grouping still need parity review |
| Content | Inspect builtin and installed third-party content; edit schema-labelled settings; save bound preinstall preferences; enable/disable installed entries | Package-owned unbound settings require installation; native interaction acceptance remains |
| Input | Configure keyboard/controller mappings and accessibility values | Verify conflicts and game behavior; desktop tests are not live input acceptance |
| Packages | Inspect a local package and its destinations; edit initial settings; review install, enable, disable or uninstall; browse included content and SDK examples | Reinstall preserves existing settings; native dialog/lifecycle acceptance remains |
| Characters | Edit per-character money/skills, loadouts/ammo, outfit components/props/presets and garage data | Native dialogs and secondary controls still need full parity verification |
| SDK Manager | Inspect/install/remove SDK; open SDK tools; independently configure, import, download or remove an optional assistant pack | Actual upstream downloads, inference and native packaged lifecycle remain separate acceptance work |
| Activity | Read/copy session progress and saved action history; open log folder; export diagnostics; check updates | Clearing the view preserves the journal; complete update-install/rollback UI remains incomplete |
| Help Center | Search task-oriented help in independently scrolling topic/article panels | Guidance must distinguish legacy and React actions |

F1 opens help; Ctrl+1 through Ctrl+9 navigate Launcher workspaces. Theme/sidebar
state is local presentation state. Collapsing a panel does not approve an action.
Do not force-close an unresolved writer; close/restart guards exist to preserve
in-flight operations and drafts. Saving one workspace must not discard another
workspace's draft.

## Package lifecycle and trust

Inspect the package identity, author, edition, file destinations, dependencies
and ownership before confirming. A checksum proves byte consistency, not that
untrusted code is safe. The Launcher does not execute package-provided Python
widgets or shell commands to construct its UI.

The normal Launcher package library includes `%LOCALAPPDATA%\ALLIN1\Packages`,
the same location used by SDK exports. Explicit isolated preview/test hosts use
their own state instead. Inspecting an example does not install it into GTA.

Manifests and archive members must agree exactly and use safe relative paths.
Traversal, Windows aliases, duplicate destinations and link escapes are rejected
before destination writes. Do not rename `allin1-sdk.exe` or another member to
work around an older Launcher's filename check; use a compatible validated build.

Enable/disable/uninstall act on receipt-owned files. If a managed file changed
externally, preserve it and inspect ownership instead of forcing a removal.
SDK removal retains a recoverable installation directory and user files; this is
not equivalent to deleting every SDK-related project or cache on the machine.

The optional [Suppressors Enhanced](realistic-suppressors.md) mod is independently
installed and released. Its 1.2.1 work is not bundled into Launcher/SDK 0.6.5.
Other independent mods, including GTA-V-FPV, keep their own contracts.

## SDK and assistant

The SDK can be installed and used independently of the Launcher and gameplay
client. The Launcher understands the new SDK portable metadata and retained
recovery layout; it does not turn a bare executable into a complete SDK package.
Opening an SDK workspace is navigation, not an implicit package install.

The React Launcher now exposes its own optional assistant configuration,
hardware assessment, reviewed pinned-source download, pack import and removal.
It does not start inference when a pack is installed or a mode is saved. In the SDK, Standalone setup can
save a compatible API or existing local runtime/model configuration without
downloading or starting it. See [assistant boundaries](optional-assistant.md).

## Updates, repair and recovery

Activity shows the current/latest Launcher versions and opens the fixed official
release page. This matches the previous Tk manual-download workflow. The 0.6.5
channel is explicitly unsigned manual download; lookup never installs an update.
Automatic-update signature requirements remain enforced.

The update services validate archive and checksum names together, stage under
contained roots and retain uniquely named backups. Rollback receipts bind the
target and before/after bytes. A stale, wrong-target or tampered receipt is
rejected; this prevents restoring arbitrary files over a different installation.
Keep the original receipt and backup when investigating a failed update.

Repair revalidates package identity and owned payloads; user content is not
discardable just because it lives near a managed installation. A failed or
uncertain write requires evidence inspection, not automatic process termination.
Client removal preserves character/garage saves and their backups, customization,
GBAY preferences, configuration and the legacy `ALLIN1` user-data folder. The
review states that this is not a data purge. Repair also retains the old data
folder; unknown files are not disposable merely because they use an old path.
Read-only status checks do not update the remembered game-path cache.

If the service connection stalls or fails, **Reconnect service** keeps drafts,
invalidates prior reviews and never replays a save. The native broker rejects
malformed/oversized responses and waits at most two minutes without a response
frame. Reconnect cannot terminate a still-running writer with an unknown outcome.
After an interrupted write, verify the files and receipts before reviewing again.
Saving one character document does not refresh the original identity of an
unsaved draft for another document; external changes must be reviewed explicitly.

## Configuration and game behavior

The [generated configuration reference](configuration-reference.md) lists every
source default; saved preferences and content-bound values may differ. Common
controls include `script.gbay_key`,
`script.seat_selector_key`, `traffic.enabled`, safe mode and accessibility values.
The seat selector default is L, not the old hold-F prototype.

Official content supplies GBAY categories, purchases, weapons/gear, garage and
character persistence. Reactor presents the in-game UI. The retired F10 world
vector overlay is **not** part of this release. Native runtime behavior still
requires edition-specific acceptance against the final paired binaries.

## Troubleshooting

### Offline catalog rendering

All catalog preview updates use an existing Blender 4+ installation and validated
model/material data. Cars render in Cycles on a textured asphalt
floor against a concrete wall, with glass, normal/specular maps, area lights and
cast shadows. This is an offline approximation of GTA materials, not the game's
own renderer. Weapons and gear use a separate Cycles pegboard studio with soft
area lights and ray-traced contact shadows. Weapon palettes, assembled default
attachments and broad-side knuckle-duster framing are preserved.

Blender is optional for launching the game and is never installed automatically.
Select it with `BLENDER_EXECUTABLE`, or a `blender_executable` string in
`%LOCALAPPDATA%/ALLIN1/preview-tools.json`. The path stays in per-user settings;
Blender itself is not distributed. An invalid explicit choice reports an error.
PATH, the development SDK's portable dependency and standard Blender Foundation
installations are also detected.

All categories use up to two concurrent renders, prefer an available Cycles GPU,
and use a bounded CPU fallback. CPU threads are divided across the workers.
Each image has a 180-second total worker deadline, but there is no catalog-wide
deadline; cancellation terminates every owned worker/Blender tree.
Weapons and gear use 64 samples; vehicles use 96. Quick Launch skips generation.
After a completed publication pass, obsolete generated image copies (including
orphaned copies from interrupted passes) are removed when their recorded digest
still matches. Current images, user-edited images and unrelated files are kept.
This cleanup is confined to the category's generated image directory; reusable
cache copies are retained. Parked aircraft omit animated rotor blur cards, use
their solid blades and render on an outdoor asphalt runway with daylight,
markings and edge lights. A lower aircraft camera includes the sky; distant
terrain and runway are blurred without softening the aircraft. Multiscale
grass and asphalt variation breaks up repeated textures. Distant industrial
hangars face a shared paved apron beside a parallel taxiway, with a grass
separation from the runway and a paved connector. Shallow metal roofs,
segmented sliding doors and clerestory windows remain softly blurred in the
background. A modest apron-side control tower, striped windsock on the grass,
and hazy distant city skyline add separate depth layers. This general-aviation arrangement draws on the airport project
references from [Passero](https://www.passero.com/projects/master-plan-and-airport-layout-plan-at-lake-city-gateway-airport)
and [Garver](https://garverusa.com/markets/aviation/general-aviation); it is a
procedural catalog backdrop, not a reproduction of either airport. Camera fitting
preserves authored vehicle dimensions. Boat/watercraft categories use an open
ocean scene instead, with gentle modeled swells, surface ripples, reflected
daylight and a soft horizon. Boat categories take priority over propeller-bone
aircraft detection. Water height uses the authored Z=0 origin when plausible,
otherwise a bounded draft estimate (not a physical buoyancy simulation).
No wake is added to stationary vessels. Camera fitting
preserves authored vehicle dimensions and decal UV proportions; meshes and
symbols are not independently scaled. Weapons and gear
retain the pegboard, except throwables: these are now included in weapon preview
discovery and counts. A closed lower crate supports an open, compartmented upper
crate beside the warehouse wall, with the removed lid leaning behind it.
Upright throwables sit inside the organizer; flat packages and mines rest on a
closed upper lid instead. Scanned wood and concrete textures, chipped edges,
battens, nail heads and rope handles give the stack visible surface detail.
Open organizers contain four matching throwables; closed lids display two,
using linked instances that share the original meshes, materials and textures.
The storage corner includes palletized, banded weapon crates, stocked steel
shelving, ribbed hard cases with latches/handles, aged inventory labels, cartons
and grouped olive ammo cans on wooden dunnage. M2A1-inspired cans have squat
rectangular bodies, lid seams, end latches/hinges, folded handles and stencils.
Upward-facing dust, handling wear and stained concrete age the scene; shallow
depth of field keeps the throwables in focus. Inert prop caps and disconnected
coiled cord sit in a divided supply bin on a background crate, leaving the floor
clear. These decorative props do not change the actual catalog item.
Storage arrangement references: [Army warehouse photographs](https://www.army.mil/article/289732/ammunition_supply_points_where_the_fight_begins)
and [Pelican transit cases](https://business.pelican.com/us/en/discover/mobile-military/mobile-armory).
Ammo-can silhouette reference: [M2A1 surplus photographs](https://commandoaustralia.com/products/bxg001n).
These are original procedural props, not copied product meshes or branding.
Stock catalog categories (including the misc Acid Package) and verified add-on
GROUP_THROWN metadata select this scene. Opaque weapon material alpha is
not treated as transparency (including the Gusenberg magazine), and
layered vehicle paint keeps its solid base beneath authored decals.

Renderer/Blender changes invalidate cached renders in every category; catalog
cards remain 512×320, downsampled from 1280×800 renders.

Each preview run starts with **one worker**. During rendering, expand **Render
performance** in the review dialog to choose a live limit of 1–4 (bounded by the
run's CPU budget). RAM-based recommendations warn before selecting a higher
count; increases are blocked if free RAM is unknown or below 2 GiB. Increases schedule additional work without waiting for
the current render; decreases let active renders finish before filling more
slots. Cancellation still waits for owned workers; tuning never launches or
terminates GTA and cannot target a different or completed review.

The panel separates the requested limit from active renders, shows free RAM and
the median of up to 12 successful render times at the selected count, and warns
about low RAM, failures, or per-item slowdown versus at least three one-worker
samples. Cache hits and jobs spanning a count change do not enter timing samples;
comparisons reset between categories. Model complexity varies, so these are
advisories, not proof of contention or a throughput benchmark. GPU memory is not
measured; workers share the GPU and increasing the count can slow things down.
Worker settings reset to one for the next run rather than persisting a risky
choice. The UI's scheduling request bypasses the busy action queue but retains
the active review ID and backend validation; it does not broaden write authority.

Civilian vehicle preview paint is selected deterministically by model from white,
black, gray, red, blue, orange and yellow. The same model keeps the same color
across editions and regenerations. Military listings use olive green (preserving
camouflage patterns); police use black/white paint and authored markings. Other
emergency vehicles retain their liveries. These are disposable render-scene
changes only: vehicle files, in-game paint and weapon/gear pegboards are untouched.
Authored `matDiffuseColor` values now survive decoding, wheel placement and
material interchange. Fixed RGB tints are preserved; paint-layer references
resolve independently of shader names. The catalog uses its selected primary
colour, a dark secondary (white for police), graphite wheels and dark interiors;
the unpainted default channel is white. These are showroom swatches, not a claim
to reproduce a particular in-game carcols configuration. Texture colour is
multiplied by its resolved tint without changing rubber into metallic paint or
tinting normal/specular maps. This fixes untinted white tyres/rims on Bruiser3
and Deathbike3 while retaining intentionally white textures and body paint.
Source changes require rebuilding a bundled preview worker before that worker
uses the fix. Previously saved artwork must be regenerated; missing-only runs
deliberately retain existing images.
The concrete backdrop has exposed metallic I-beams, horizontal crossbeams and
diagonal bracing. A masked background blur softens the wall and structural steel
without blurring the vehicle or nearby asphalt; normalized filtering prevents
the vehicle's colors bleeding into the background at its silhouette.

| Symptom | Safe next check |
| --- | --- |
| Access denied at a game path | Verify the actual path/edition, that GTA is closed, file ownership/permissions and security-software history. Do not grant broad permissions or disable protection as a blanket fix. |
| ALLIN1 missing despite prerequisites | Prerequisites are dependencies, not the client. Review Install / Repair for the selected edition. |
| SDK archive member/checksum mismatch | Re-download the exact matching distribution and use a compatible Launcher. Preserve the rejected archive for diagnosis; do not rename members. |
| GBAY fails to open | Check key/backend settings, readiness, Reactor dependency/receipt and matching core/bridge identity. Collect current-session diagnostics. |
| A custom weapon is missing | Confirm the package is installed/enabled for this edition and supplies valid catalog metadata; authoring alone does not register it in GBAY. |
| Review no longer applies | Reload current state, preserve drafts and review again. The source may have changed or the review expired. |
| Uninstall/rollback refuses | Inspect receipt ownership and backup identity; retain modified user files and recovery evidence. |

Export diagnostics to a new location outside GTA. Review the redacted bundle
before sharing it; do not share API keys or full private projects. Include the
exact app version/build identity, edition, operation and failure time. “The same
version number” is insufficient when development binaries differ.

See [CLI reference](cli-reference.md), [release gates](release-0.6.5.md) and
[documentation index](README.md).
