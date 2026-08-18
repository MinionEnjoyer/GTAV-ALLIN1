<p align="center">
  <img src="src/allin1/assets/ALLIN1.png" alt="GTA V ALLIN1" width="120" height="120" />
</p>

# ALLIN1 Launcher — GTA V Story Mode

A Windows mod tool and Story Mode expansion for bringing GTA Online vehicles, weapons, and
supporting systems into Grand Theft Auto V single-player. ALLIN1 combines a desktop control center,
an in-game storefront called **GBAY**, persistent garages, DLC-aware traffic, character editing,
and a general-purpose local mod-package manager in one project.

ALLIN1 supports both GTA V Legacy and GTA V Enhanced. It is designed exclusively for **Story
Mode**; the installer configures the game to launch without BattlEye and should never be used in
GTA Online.

> **Current public release:** **0.4.9**. See [RELEASE_NOTES.md](RELEASE_NOTES.md) for the release
> highlights and hardening work included in this build.

## Support

If the ALLIN1 Launcher and SDK are useful to you, project support is available through
[Buy Me a Coffee](https://buymeacoffee.com/minionenjoyer).

## Features

- **Galaxy Super Yacht** — purchase the persistent yacht from GBAY's Special
  catalog and assign its GTA Online helipad aircraft (Swift Deluxe or
  SuperVolito Carbon) to a per-character, save-backed helipad slot.

- **GBAY vehicle marketplace** — browse all 461 supported DLC vehicles by category, search and
  filter the catalog, collect listings in a dedicated Favorites tab, inspect streamed preview
  artwork, purchase a vehicle, and choose its destination from every compatible garage.
- **Weapons and gear** — purchase more than 100 weapons, refill owned ammunition, browse captured
  previews for armor and equipment in GBAY, and manage exact per-character loadouts from the
  desktop manager. Quantity-based items show and charge their full bundle total (for example,
  25 Sticky Bombs at $600 each cost $15,000). Unequipping gear discards it; equipping it again
  requires another purchase.
- **Persistent garages** — maintain independent collections at the 10-car Eclipse Garage, the
  oversized 25-car Harmony Garage, the 10-car Davis Auto Shop, the 10-car Garment Factory,
  the six-car Grapeseed Garage, and the 10-car Paleto Bay Garage; drive vehicles in,
  choose purchase destinations, browse garages and
  stored vehicles in a two-pane manager, sell stored vehicles,
  recover interrupted transitions, use Harmony's five fully detailed floors, and configure every Davis Auto Shop
  style, tint, lift, quarters, work-area, and storage option. Every ALLIN1
  garage blip and world marker follows the active protagonist's blue, green, or orange color.
  Wanted players are denied entry by default, with an optional launcher override.
- **DLC traffic integration** — adds Online vehicles to ambient traffic with class-aware
  replacements, road and visibility checks, mission/interior/wanted-level guards, distance-based
  cleanup, and adaptive performance throttling. Player-owned and recently used vehicles, plus
  vehicles parked in Story Mode safehouse garages, are protected without excluding ordinary
  ambient parked traffic.
- **Vehicle seat selector** — choose a seat with the configurable selector key (default
  **L**). Accessible seats use native entry and shuffle animations.
- **Character control** — manage Michael, Franklin, and Trevor independently, including money,
  skill levels, weapons, gear, garage saves, outfit components, props, and named outfit presets.
- **Desktop control center** — detect the game edition, configure gameplay and accessibility
  options, install or repair the mod, run health checks, export redacted diagnostics, manage
  profiles, block accidental GTA Online entry with a reversible Story Mode-only gameplay toggle,
  and launch GTA V from one persistent launcher window.
- **Local mod packages** — install, update, enable, disable, and uninstall user-supplied ASI,
  ScriptHookVDotNet, RPF, and config/data packages through validated `mod.toml` manifests,
  including transactional `dlclist.xml` registration for explicitly owned add-on packs.
- **Add-on Content SDK** — inspect linked weapon, ammo, animation, native-text, HUD, runtime,
  storefront, vehicle, handling, variation, tuning, streamed-asset, archive, and rollback fields
  in the desktop viewer; validate an `addon.json` integration and export its ordered install plan
  before any archive is written. The seven colored smoke grenades are included as the first
  complete example. Its live package index also combines remembered external SDK drafts, local
  catalog manifests, and receipt-backed packages from every configured Legacy and Enhanced
  installation without copying third-party payloads.
- **Package and native asset viewer** — safely browse loose DLC folders and OIV/ZIP/RAR/7z
  packages, preview images and authored text, parse GTA binary headers, convert supported RAGE
  resources to structured CodeWalker XML, and render YTD texture contact sheets without installing
  or executing content.
- **Interactive RPF explorer** — search root and nested RPFs as one hierarchy, inspect logical and
  stored sizes, offsets, compression/encryption state, resource versions, page flags, and hashes;
  extract exact root or nested entries, export JSON/CSV indexes, and create checksummed replacement
  plans without changing an archive. Mixed test-mod folders can be batch-audited into a report that
  distinguishes DLL scripts, ASIs, ReShade companions, replacements, DLC archives, and incomplete
  downloads.
- **Package intelligence workbench** — preview actual OIV operation recipes and convert only fully
  translatable packages into validated, rollback-owned `mod.toml` packages; reconcile stock,
  external, and ALLIN1-owned DLC folders against `dlclist.xml`; and compile vehicle, handling,
  variation, tuning, streaming, label, and registration metadata into JSON, CSV, XLSX, and
  unresolved-reference reports.
- **Recovery-minded operation** — backs up replaced files, preserves garage recovery copies,
  detects unclean sessions, offers a safe mode, and writes structured client diagnostics.

## How it fits together

```text
ALLIN1 desktop manager
  Settings, profiles, health checks, character editor, mod packages
  Install / repair and Launch GTA V
                     |
                     v
GTA V Story Mode
  ScriptHookV + ScriptHookVDotNet Enhanced
    ALLIN1 client
      GBAY marketplace and streamed preview artwork
      Traffic spawner and vehicle helpers
      Persistent garages and floor customization
      Character loadouts, progress, outfits, and seat selector
```

The Python manager owns configuration, installation, backups, RPF packaging, diagnostics, and
external mod integration. The C# ScriptHookVDotNet client owns the live Story Mode systems and
persists character and garage state under the game's `scripts` directory.

## Requirements

- Windows 10 or Windows 11.
- GTA V Legacy or GTA V Enhanced from Steam, Epic Games, or Rockstar Games Launcher.
- [ScriptHookV](http://www.dev-c.com/gtav/scripthookv/).
- [ScriptHookVDotNet Enhanced](https://github.com/Chiheb-Bacha/scripthookvdotnetenhanced).
- Python 3.10 or newer when installing from source.
- OpenRPF for Enhanced or OpenIV.asi for Legacy when GBAY preview artwork is enabled.

ScriptHookV and ScriptHookVDotNet Enhanced must be installed in the directory containing
`GTA5.exe` or `GTA5_Enhanced.exe` before ALLIN1 is installed.

## Windows installation

1. Clone or download this repository.
2. Install ScriptHookV and ScriptHookVDotNet Enhanced into the GTA V root directory.
3. Run `install.bat` once. It creates the local Python environment and prepares the manager.
4. Open `manager.bat`.
5. Confirm the Legacy and/or Enhanced GTA V directories, choose the active target, and select
   **Install / Repair**.
6. Keep **Gameplay → Story Mode only** enabled, select **Launch GTA V**, and press **F9** in
   Story Mode to open GBAY.

The installer deploys the ALLIN1 client and configuration under `<GTA V>/scripts`, registers the
GBAY preview DLC when artwork is enabled, creates recoverable backups before replacement, and adds the no-BattlEye
launch argument required for Story Mode scripting.

## Desktop manager

The launcher is the main player-facing configuration surface. Setup, Gameplay,
Input, Packages, Characters, SDK Manager, Activity, and Help Center are persistent
workspaces inside one launcher window. The standalone SDK uses one separate
developer window for Integration, Native Assets, RPF Explorer, SDK Console, and
Help Center. Routine navigation no longer opens a collection of independent tool
windows; only file selection, confirmation, and blocking progress remain modal.

The launcher workspaces cover:

- core gameplay, traffic, keybind, performance, and accessibility settings;
- installation status, dependency and RPF-loader health, updates, and rollback-aware repair;
- per-character skills, money, garages, inventories, outfits, and presets;
- local third-party mod packages with dependency, conflict, edition, and checksum validation;
- managed SDK installation, update, repair, removal, and launch;
- redacted support bundles and runtime log inspection.

Named profiles can preserve different combinations of traffic, GBAY, input, and accessibility
settings. The installed `scripts/ALLIN1.toml` remains the runtime source of truth.

## In-game controls

| Input | Action |
|---|---|
| `F9` | Open or close GBAY |
| Arrow keys / D-pad | Navigate menus and listing grids |
| `Enter` / controller Accept | Select or purchase |
| `Escape`, right-click / controller Back | Return to the previous page |
| `LB` / `RB` or mouse wheel | Previous or next listing page |
| `LT` / `RT` | Previous or next category |
| `Y` | Cycle ownership filters: all, owned, or available |
| `X` | Search the active catalog |
| `R3` | Favorite or unfavorite the selected listing |
| `L` | Open the seat selector by default |
| `N` | Toggle acquired night vision |
| `F10` | Toggle the developer world-vector overlay |

GBAY supports keyboard, mouse, and controller navigation. Page arrows and category-strip arrows
are also clickable, and directional navigation crosses listing-page boundaries automatically.

Seat names are backed by a generated Rockstar metadata audit rather than guessed from passenger
indices. The checked-in `catalog/vehicle_seats.json` and `.md` cover base-game and installed DLC
models, including authored access geometry and verified exceptions for inaccessible stations.

## Configuration

`config.example.toml` documents every supported option. The manager writes the active settings to
`config.toml` and copies them to `scripts/ALLIN1.toml` during installation.

Important groups include:

- `[general]` — independent Legacy and Enhanced game paths, active target, backups, and RPF
  preview artwork;
- `[traffic]` — spawn distances, population limits, replacement behavior, and adaptive FPS guard;
- `[vehicles]` — global enablement plus class and model exclusions;
- `[script]` — GBAY, night vision and seat-selector keys, UI scale, reduced motion, colorblind mode,
  safe mode, free purchases, support logging, and the F10 world-vector overlay.
  The experimental branch also offers an opt-in GTA IV-style ambient NPC physics preset.
  See [the experiment notes](docs/gtaiv-npc-physics-experiment.md) for its safety boundary and prior art.

Vehicle, weapon, and gear pricing is maintained in `prices_vehicles.toml`,
`prices_weapons.toml`, and `prices_gear.toml`.

## Optional mod packages

The launcher's **Packages** workspace accepts local packages containing a `mod.toml` manifest.
Supported package types include ASI plugins, ScriptHookVDotNet scripts, whole RPF content,
entry-level RPF patches, mixed packages, and config/data files. Every package is tagged as
Legacy, Enhanced, both, or unresolved; installs are routed only to a compatible configured game
directory. Legacy and Enhanced can be configured and managed side by side.
The manager validates edition support, loader requirements, conflicts, destination paths, and
optional SHA-256 hashes before installation. Replaced files are backed up and restored when the
package is removed. Entry-level RPF ownership and rollback preserve unrelated archive content.

The format and inert examples are documented in [mods/README.md](mods/README.md). ALLIN1 does not
ship or download arbitrary third-party mods through this interface.

## Standalone ALLIN1 SDK

Developer tooling now lives in the independent sibling
[ALLIN1-SDK](https://github.com/MinionEnjoyer/ALLIN1-SDK) repository. Open **SDK → Install /
Manage SDK** to download its public, self-contained Windows release. The launcher verifies the
published SHA-256 and every file in the archive before atomically installing it under
`%LOCALAPPDATA%\ALLIN1\SDK`; Python is not required. The same panel opens, updates, repairs, or
uninstalls the managed application without touching either GTA V directory.

The launcher opens or focuses the SDK as a single separate process; both apps
prevent duplicate main windows. The SDK has its own `allin1_sdk` namespace, version, tests, CLI/GUI entry
points, user state, CodeWalker submodule, and RPF helper build. Package importing and lifecycle
management remain in the launcher, while integration linking, native asset inspection, RPF
exploration, OIV auditing, DLC inventory, vehicle-data compilation, and the structured local
AI-agent command API belong to the SDK.

## Tech stack

- **Desktop manager:** Python 3.10+, Tk/ttk, Click, Pillow, and TOML configuration.
- **Game client:** C# on .NET Framework 4.8 with ScriptHookVDotNet Enhanced and LemonUI.
- **RPF and YTD tooling:** .NET, a pinned Enhanced-aware CodeWalker authoring core, Pillow BC3 encoding, and the
  repository's `RpfPatcher` utility.
- **Testing:** pytest for manager, installer, generator, and repository contracts; dotnet builds
  for the in-game client and native tool integration checks on Windows.

## Repository layout

```text
src/allin1                 Python launcher, installer, diagnostics, and package management
script/src                 C# Story Mode client, GBAY, garages, traffic, and character systems
script/dist                Prebuilt client binaries and runtime artwork
data                       Vehicle and weapon source catalogs
catalog                    Generated and curated DLC content metadata
mods                       Local mod-package format and examples
sdk                        Compatibility mirror for the extracted standalone SDK contract
tools/RpfPatcher           RPF, YTD, Gen9 conversion, and verification utility
tests                      Python, build, packaging, and repository contract tests
documentation.md           Complete configuration, architecture, and troubleshooting reference
config.example.toml        Commented configuration template
install.bat / manager.bat  Windows setup and launcher entry points
```

## Local development and testing

Create the environment and run the complete Windows harness:

```powershell
.\install.bat
powershell -ExecutionPolicy Bypass -File .\test-all.ps1
```

The Python suite can be run directly with:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest -q
```

The harness covers configuration, detection, installation and rollback behavior, mod manifests,
garage and character persistence, preview generation, RPF contracts, C# compilation, and release
artifacts. Native gameplay still requires the manual checklist in
[tests/IN_GAME_CHECKLIST.md](tests/IN_GAME_CHECKLIST.md) because ScriptHook APIs require a running
game process.

## Documentation

Detailed setup, configuration, GBAY behavior, garages, traffic, the preview DLC pipeline, build
tools, diagnostics, and troubleshooting are maintained in
[documentation.md](documentation.md).

GTA V ALLIN1 is licensed under the GNU General Public License v3.0 or later.
