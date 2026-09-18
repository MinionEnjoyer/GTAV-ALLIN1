# ALLIN1 Launcher guide — 0.6.5

0.6.5 is an unsigned portable release. The desktop is React/Tauri v2; bundled Python provides its services
and command-line tools, with no Tkinter fallback. Do not assume an
older downloaded build has every action described here.

## Before starting

Use GTA V Story Mode only. Select Legacy or Enhanced explicitly and verify its
directory. Close the game before installing, repairing, updating, disabling or
removing packages. Keep save files, authored content and recovery receipts.
Do not use the modded launch configuration in GTA Online.

For the Content page’s pedestrian, traffic and weapon population editors, see
[Content injectors](content-injectors.md). They configure authorized installed
content through reviewed policies without overwriting original game assets.

For the portable release, verify and extract the complete download into a fresh
folder. Keep `runtime/` and `resources/` beside `allin1-launcher-desktop.exe`;
run that executable, select your edition/path, then review **Install / Repair**.
Launch once readiness permits. Python need not be installed separately.

Setup groups Reactor V with the ALLIN1 client, ScriptHookV, ScriptHookVDotNet,
and OpenRPF under **Installation dependencies**. Each card uses **Installed**,
**Missing**, or **Not checked**. These are installation checks, not confirmation
that the component has loaded in-game. For Reactor V, follow any reported
validation reason and use **Review Install / Repair** when needed.
After changing the edition or game paths, use **Refresh** to check that selection.

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

Before Story Mode, the Launcher validates enabled managed packages and mounted
DLC, then can prepare stock/add-on weapon, vehicle and gear images with isolated
Blender/Cycles workers. Unchanged artwork is reused; archive, catalog, edition,
renderer, or backdrop changes invalidate the relevant cache. Each item has a
180-second worker limit, but no catalog-wide render limit; discovery and
cache/index publication stay serialized. Workers start at one and **Render
performance** can raise the live limit to 8 within CPU/RAM safeguards. GPU is
preferred with a bounded CPU fallback; numerical libraries use one thread each.
Cancel Launch stops every owned worker, never GTA; failures retain existing art
and do not block launch. Nothing renders inside GTA.

These are offline textured base-model cards, not exact GTA shader renders or
live selected-attachment/customization previews. Vehicles use an asphalt/concrete
showroom; weapons and gear use a pegboard. Unsupported, ambiguous, or unowned
assets retain existing art, use an installed default, or show a placeholder.
Separate reusable caches are kept per edition.

Choose **Update Previews** or **Quick Launch** in the reviewed launch flow.
Update Previews offers **Weapons**, **Vehicles**, and **Gear**: checked categories
render missing entries; unchecked ones still validate/reuse cache. Keep one
selected. **Missing previews only** retains intact indexed generated images even
after source/renderer changes and restores valid cache copies without rendering;
it still validates active packages/sources and cleans stale images. Uncheck it
for a normal refresh. The review's **existing / total** counts cover published
generated files only—not defaults, source/cache validation, discovery, or
rendering—and show **Unavailable** for unreadable catalogs/indexes. Unsupported
gear is excluded. Reopen the review to refresh counts.

**Quick Launch** disables the complete optional preview phase, including model
discovery, and leaves published artwork unchanged. It remains a per-launch
choice: safety checks, confirmation, garage preparation, and Reactor startup
still apply. Missing art uses a default pack or placeholder.

For CLI/API/agents, `launch` and `prepare_previews` accept
`missing_previews_only`, `skip_preview_categories: ["vehicles", "gear"]`, and
`skip_previews: true`; `launch` also accepts `quick_launch: true`. Unknown or
duplicate categories are rejected; Quick Launch wins over category skips and a
changed choice needs a new review. These operations require the same approval and
closed-game checks as the desktop. `preview_counts` is included in reviews;
`prepare_previews` reports per-category results, while launch returns
`catalog_previews` plus the compatibility `weapon_previews` field. Receipts live
in the per-game `weapon-previews` cache; generated images/indexes publish under
`plugins/ReactorV/ui/assets/allin1/generated-weapons`, `generated-vehicles`, and
`generated-gear`.

### Separate default preview pack

Fallback art is not bundled or copied with the Reactor UI. GBAY prefers generated
images, then a separately installed default pack, then a placeholder; see the
[default-preview pack guide](gbay-default-previews.md). Existing generated caches
are preserved. Repair retires legacy bundled art through its receipt without
claiming generated/default-preview folders.

The pack layout reserves `plugins/ReactorV/ui/assets/allin1/default-weapons`,
`default-vehicles`, and `default-gear`. Each contains a bounded `index.json` with
`schema_version: 1`, `owner: "allin1.default-previews"`, and an `images` mapping
from lowercase catalog model/weapon IDs to `<id>.<64-lowercase-hex-id>.png`.
Use the same portable IDs as generated indexes; paths and arbitrary filenames are
rejected. Selected files need a valid PNG header, dimensions up to 4096 pixels per
side, and size up to 4 MiB. This is a header check, not a full decode. Restart the
game after installing a pack; publishing/downloading remains separate.

RpfPatcher and the isolated worker remain required for optional local model
discovery/extraction/rendering; RpfPatcher also supports mod/map installation.
Blender textures are render inputs, not fallbacks. Quick Launch skips extraction
and rendering.

Install trusted, compatible ScriptHookV and the complete ScriptHookVDotNet
Enhanced runtime for the selected edition. The readiness check identifies
missing components; “prerequisites present” does not mean the ALLIN1 client is
installed. Review the Install / Repair plan to add it.

Reactor V is required for GBAY. It is a separately versioned
dependency with edition-specific validation, not the desktop React renderer.
Dependency downloads require consent; installation alone does not establish
in-game acceptance.

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

The React service stores state in `%LOCALAPPDATA%\ALLIN1\Launcher` by default.
Repository configuration is only a compatibility starting point; it is never
migrated by opening a page. **Import previous Launcher preferences** reviews a
folder's `config.toml` and named profiles, copies only missing files, and keeps
both the source and existing preferences. A changed source invalidates the review.
Profiles and package/SDK state are not GTA save data.

The UI keeps drafts while Python validates/writes. Reviews bind selected state,
expire, and are single-use; reload and review again after source/config changes.

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

F1 opens Help and Ctrl+1 through Ctrl+9 switch workspaces. Theme/sidebar state is
presentation-only; collapsing a panel does not approve an action. Do not
force-close an unresolved writer: close/restart guards protect in-flight work and
drafts, including drafts in other workspaces.

## Package lifecycle and trust

Before confirming, inspect identity, author, edition, destinations, dependencies,
and ownership. A checksum proves byte consistency, not that untrusted code is
safe; the Launcher never executes package-provided Python widgets or shell
commands to construct its UI.

The normal Launcher package library includes `%LOCALAPPDATA%\ALLIN1\Packages`,
the same location used by SDK exports. Explicit isolated preview/test hosts use
their own state instead. Inspecting an example does not install it into GTA.

Manifest/archive members must agree and use safe relative paths. Traversal,
Windows aliases, duplicate destinations, and link escapes are rejected before
writes. Do not rename `allin1-sdk.exe` or another member to bypass an older
Launcher check; use a compatible validated build.

Enable/disable/uninstall act only on receipt-owned files. Preserve externally
changed managed files and inspect ownership rather than forcing removal. SDK
removal retains a recoverable installation directory and user files; it does not
delete every SDK-related project or cache.

The optional [Suppressors Enhanced](realistic-suppressors.md) mod is independently
installed and released. Its 1.2.1 work is not bundled into Launcher/SDK 0.6.5.
Other independent mods keep their own contracts.

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

Do not overlay a Launcher ZIP onto an older application folder: retired hashed
UI assets can fail the exact resource check. Use a fresh folder, or, from a
matching source checkout with the Launcher closed, run
`python tools/install_launcher_candidate.py --archive <portable.zip> --destination <launcher-folder>`.
This Launcher-only installer retains the previous application as a sibling
backup, replaces its complete owned tree, and verifies the result before
returning. It preserves nonconflicting user files outside the runtime/resource
trees and refuses ambiguous ownership. The generic `apply-update` overlay is
for payload updates, not complete Launcher installations.

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
Long-running service requests send liveness heartbeats every 15 seconds. These
keep the connection alive but do not count as completed work. Package RPF actions
also report backup, replacement and verification progress, with helper-call
counts and elapsed time. Install normally uses three helper calls per entry;
uninstall and enable/disable normally use two. Original-checksum preflight, DLC
registration, resource canonicalization and recovery can add calls.

The RPF workload budget is advisory: two minutes of setup allowance plus five
seconds per estimated helper call. Additional calls extend the budget. A helper
running for two minutes or an operation exceeding that budget displays a warning,
not cancellation or an automatic retry. Keep the launcher open until it reports
a definitive result. The progress bar stays below 100% until the reviewed action
finishes; a live service alone does not prove that its archive helper is advancing.
Successful reconnect refreshes the installed state while retaining drafts, so a
retained package draft no longer prevents recovery-state inspection.
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

Updates need an existing Blender 4+ installation and validated model/material
data. Blender is optional for launching, never installed automatically, and is
selected with `BLENDER_EXECUTABLE` or `blender_executable` in
`%LOCALAPPDATA%/ALLIN1/preview-tools.json`; PATH, the development SDK portable
dependency, and standard Blender Foundation installations are also detected. An
invalid explicit path errors. The renderer is an offline Cycles approximation,
not GTA's renderer: vehicles use the showroom, weapons/gear the pegboard, and
throwables a procedural warehouse crate scene. Its references—[Army warehouse photographs](https://www.army.mil/article/289732/ammunition_supply_points_where_the_fight_begins),
[Pelican transit cases](https://business.pelican.com/us/en/discover/mobile-military/mobile-armory),
and [M2A1 surplus photographs](https://commandoaustralia.com/products/bxg001n)—inform
original props, not copied meshes or branding.

Aircraft use a daylight runway scene based on [Passero](https://www.passero.com/projects/master-plan-and-airport-layout-plan-at-lake-city-gateway-airport)
and [Garver](https://garverusa.com/markets/aviation/general-aviation); boats use
an open ocean. Both are procedural backdrops, not physical simulation or
reproductions. Camera fitting preserves authored dimensions and decal UVs;
meshes/symbols are not independently scaled. Renderer changes invalidate every
category. Cards remain 512×320, downsampled from 1280×800. Throwables are in
weapon discovery/counts; opaque weapon alpha stays opaque and layered vehicle
paint retains its solid base beneath decals.

Runs start at one worker. While rendering, **Render performance** can set 1–8
workers within the active review's hardware limit; increases schedule new slots,
while decreases drain active work. A higher setting is blocked when free RAM is
unknown or below 2 GiB; warnings cover RAM, failures, or slower per-item times.
The panel distinguishes requested/active workers and shows free RAM plus a median
from up to 12 successful renders. Cache hits and jobs spanning a change are
excluded; comparisons reset per category and GPU memory is not measured. These
are advisories, not a benchmark: workers share GPU/CPU/RAM and more can be slower.
The setting resets to one next run. Its request keeps the active `review_id` and
backend validation, so it cannot target another review or expand write authority.
Cancellation waits for owned workers and never launches or terminates GTA.

Each item has a 180-second deadline, without a catalog-wide limit; GPU is
preferred with bounded CPU fallback. Weapons/gear use 64 samples and vehicles
96. Quick Launch skips generation. After successful publication, cleanup removes
only obsolete generated copies whose recorded digest still matches; current,
user-edited, unrelated, and reusable-cache files remain. Civilian model colours
are deterministic; military, police, and other emergency liveries retain their
specified showroom treatments. These are render-scene changes, not vehicle files,
in-game paint, or GTA carcols behavior. Rebuild the bundled worker after source
changes, then regenerate art; missing-only deliberately retains existing art.

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
