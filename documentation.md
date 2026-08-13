# GTA V ALLIN1 — Comprehensive Documentation

GTA V ALLIN1 is a mod installer that ports 461 GTA Online DLC vehicles, 100+ weapons, and gear into GTA V single-player Story Mode. It includes a traffic spawner, an in-game shop (GBAY), a personal garage system, and a vehicle seat selector.

Supports both GTA V Legacy and GTA V Enhanced editions.

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [In-Game Features](#in-game-features)
5. [CLI Commands](#cli-commands)
6. [Project Structure](#project-structure)
7. [Build System](#build-system)
8. [Code Generators](#code-generators)
9. [DLC Texture Pack](#dlc-texture-pack)
10. [Tools](#tools)
11. [Data Files](#data-files)
12. [Troubleshooting](#troubleshooting)

---

## Requirements

- **GTA V** (Legacy or Enhanced edition, Steam/Epic/Rockstar Launcher)
- **ScriptHookV** — [dev-c.com/gtav/scripthookv](http://www.dev-c.com/gtav/scripthookv/)
- **ScriptHookVDotNet Enhanced** — [github.com/Chiheb-Bacha/scripthookvdotnetenhanced](https://github.com/Chiheb-Bacha/scripthookvdotnetenhanced)
- **OpenRPF** (Enhanced edition) or **OpenIV.asi** (Legacy edition)
- **Python 3.10+** (for the installer)
- **Windows** (GTA V is Windows-only)

ScriptHookV and ScriptHookVDotNet must be installed into the GTA V root directory before running the ALLIN1 installer.

---

## Installation

### Quick Start

1. Place `ScriptHookV.dll` and `ScriptHookVDotNet.asi` in your GTA V root directory
2. Run `install.bat`
3. The installer auto-detects your GTA V path (Steam, Epic, Rockstar Launcher, registry)
4. If auto-detection fails, enter the path manually when prompted
5. Launch GTA V — press **F9** to open GBAY

### What the Installer Does

1. Creates a Python virtual environment and installs dependencies
2. Copies `config.example.toml` to `config.toml`
3. Detects GTA V installation path and edition
4. Deploys to `<GTA V>/scripts/`:
   - `ALLIN1.dll` — main script
   - `LemonUI.SHVDN3.dll` — UI framework dependency
   - `ALLIN1.toml` — configuration (copy of `config.toml`)
   - `prices_gear.toml` — gear price overrides
5. Builds and deploys the preview texture DLC pack to `mods/update/x64/dlcpacks/allin1_previews/`
6. Patches `dlclist.xml` inside `mods/update/update.rpf` to register the DLC
7. Adds `-nobattleye` to `commandline.txt`
8. Auto-downloads OpenRPF if missing (Enhanced edition only)

### Uninstall

Run `uninstall.bat` to remove all ALLIN1 files, unpatch `dlclist.xml`, and clean up legacy files.

### Update

Run `update.bat` to open the latest verified GitHub Release. Extract the new ZIP into a fresh
folder and run `install.bat`; repair preserves the installed configuration and garage saves.

The desktop manager also has an **About** page with the project goal, creator
credit, support link, and an explicit **Check for updates** action backed by
GitHub Releases. Update checks are never performed silently. Each successful
install writes `scripts/ALLIN1.version`, allowing the manager to distinguish
its own version from the deployed mod client. The in-game GBAY About and
Diagnostics pages display the C# assembly version as well.

Updates can be packaged with a `checksums.json` manifest and applied through
`allin1 apply-update`. Every declared file is SHA-256 verified in a staging
directory before deployment; replaced files are retained for
`allin1 rollback-update`.

### Reliability and profiles

The manager's **Health check** verifies the game executable, ScriptHook
dependencies, RPF loader, duplicate/legacy ALLIN1 files, installed version,
and optional file checksums. Named profiles preserve complete traffic,
keybind, performance, and accessibility configurations.

An unclean game shutdown leaves `ALLIN1_session.lock`. On the next session the
client enters safe mode, suppressing traffic spawning and the floor-garage
initializer while leaving GBAY diagnostics available. A clean SHVDN shutdown
removes the marker. Set `script.safe_mode = true` to force this behavior.

Garage saves can be repaired with `allin1 repair-garage`. Valid vehicles are
retained, duplicate or invalid slots are reassigned, and rejected records are
written to a quarantine JSON file instead of being discarded.

---

## Configuration

Configuration is stored in `config.toml` (copied to `scripts/ALLIN1.toml` during install). See `config.example.toml` for all options with comments.

### [general]

| Key | Default | Description |
|-----|---------|-------------|
| `gta_path` | `"auto"` | GTA V installation path. Set to `"auto"` for auto-detection. |
| `free_mode` | `false` | Deprecated compatibility alias for `script.gbay_free_mode`. |
| `backup` | `true` | Create backups of original game files before modifying. |

### [traffic]

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Add GTA Online vehicles to ambient traffic. |
| `max_driven` | `20` | Maximum client-spawned, AI-driven DLC vehicles. |
| `spawn_distance_min` / `spawn_distance_max` | `80` / `200` | Spawn annulus around the player, in metres. |
| `cleanup_distance` | `350` | Distance at which managed traffic is released. |
| `driven_cooldown_ms` | `5000` | Delay between driven vehicle spawns. |
| `scan_cooldown_ms` | `3000` | Delay between ambient replacement scans. |
| `scan_radius` | `200` | Ambient vehicle scan radius. |
| `minimum_replace_distance` | `50` | Prevent replacements too near the player. |
| `replacement_chance` | `0.30` | Per-candidate replacement probability from 0 to 1. |
| `rich_areas_only_supers` | `true` | Super/sports cars spawn only in wealthy neighborhoods. |

### [vehicles]

| Key | Default | Description |
|-----|---------|-------------|
| `enable_all` | `true` | Enable all 461 DLC vehicles. When false, use catalog to pick specific ones. |
| `disabled_classes` | `[]` | Vehicle classes to exclude (e.g., `["helicopters", "planes", "boats"]`). |
| `disabled_vehicles` | `[]` | Specific model names to exclude (e.g., `["adder", "t20"]`). |

Available classes: `compacts`, `coupes`, `sedans`, `suvs`, `muscle`, `sports`, `sportsclassics`, `super`, `offroad`, `motorcycles`, `military`, `industrial`, `vans`, `boats`, `helicopters`, `planes`, `openwheel`, `emergency`, `service`, `cycles`, `special`, `weaponized`.

### [script]

| Key | Default | Description |
|-----|---------|-------------|
| `gbay_key` | `"F9"` | Key to open the GBAY shop menu. Uses .NET `Keys` enum names. |
| `night_vision_key` | `"N"` | Toggle purchased night vision. |
| `world_vector_key` | `"F10"` | Toggle the developer world-vector overlay. |
| `seat_selector_enabled` | `true` | Enable hold-to-select vehicle seats. |
| `gbay_free_mode` | `false` | All GBAY purchases are free; vehicle sales have no payout. |
| `enable_logging` | `false` | Write debug info to `scripts/ALLIN1.log`. |
| `enable_dlc_police` | `false` | Replace vanilla police cars with DLC police vehicles. |

### Price Customization

Prices are defined in three separate files at the project root:

- `prices_vehicles.toml` — grouped by vehicle class
- `prices_weapons.toml` — grouped by weapon category
- `prices_gear.toml` — gear item prices

Edit these files and re-run the installer (or regenerate the lists via CLI) to change in-game prices. Gear prices are loaded at runtime from `scripts/prices_gear.toml` without needing regeneration.

---

## In-Game Features

### GBAY Shop (F9)

Press **F9** (configurable) to open the GBAY shop menu.

Opening GBAY now presents an animated PHAT avatar loading screen, followed by
short cross-fades when moving between shop, garage, weapon, and customization
screens.

Vehicle and weapon catalogs support **Y** ownership filters (all, owned, or
available), a dedicated **Favorites** category, **R3** favorite toggling, and
**X** text search using GTA's on-screen keyboard. The garage view
also exposes **Y — Recover**, which saves live vehicle state, clears spawned
garage entities and transition locks, and safely returns the player outside.

### Character Customization

The desktop manager's **Character customization** window provides three tabs:

- advanced traffic-spawner settings;
- import, export, add, remove, and validate per-character garage vehicles;
- exact per-character weapon and gear loadouts.
- an outfit unlocker/customizer for all 12 component slots and 8 prop slots.

Managed loadouts are stored in `scripts/ALLIN1_characters.json`. They are opt-in
per character: an untouched character retains the inventory from the native
Story Mode save. Once managed, launcher additions and removals are applied by
the client, while purchases made in GBAY are written back to the same file.
Outfits are also opt-in. Drawable and texture IDs are validated against the
active Michael, Franklin, or Trevor model before native calls are made. A prop
drawable of `-1` removes that prop. The unlock option exposes native component
variants without modifying the player's underlying GTA save file.
Named outfit presets can be saved, loaded, and deleted independently for each
character. Legacy character and garage JSON files remain readable; subsequent
saves add schema-version markers and normalized fields while retaining `.bak`
recovery copies.

### Diagnostic bundles

Use **Diagnostics** in the desktop manager or run:

```text
allin1 diagnostics --scripts-dir "C:\Games\GTAV\scripts" -o diagnostics.zip
```

The bundle contains available ALLIN1 configuration, structured logs, managed
save files, smoke reports, and a checksum manifest. GTA installation paths and
home-directory usernames are redacted before files enter the archive.

Preview captures can be checked before packaging with:

```text
allin1 audit-previews "C:\Games\GTAV\scripts\previews"
```

The audit rejects corrupt, undersized, nearly transparent, blank/low-contrast,
or badly framed transparent previews. Raw captures remain review material;
installation packages only curated assets from `script/dist`. Import approved
captures explicitly with `allin1 import-previews SOURCE --kind vehicle` (or
`weapon` / `equipment`) before rebuilding the preview DLC.

### Runtime optimization

The client keeps render-frequency work limited to controls, markers, and active
UI drawing. Traffic simulation runs at 10 Hz, traffic cleanup runs once per
second, character loadout file checks run once per second, repeated character
and weapon hashes are cached, garage blip colors update only after a character
change, and the former per-frame GBAY texture-debug overlay has been removed.

**Top Menu** — choose between:
- **Vehicles** — browse and purchase 461 DLC vehicles
- **Weapons** — browse and purchase 100+ weapons
- **Gear** — purchase body armor, parachute, and utility items
- **My Garage** — manage and sell stored vehicles

**Vehicle Browser:**
- 22 category tabs (All, Compacts, Coupes, Sedans, SUVs, Muscle, Sports Classics, Super, Off-Road, Motorcycles, Vans, Boats, Helicopters, Planes, Military, Industrial, Open Wheel, Emergency, Cycles, Service, Special, Weaponized) with scroll arrows
- 3x3 card grid per page with vehicle preview images, manufacturer, name, and price
- Vehicle names wrap to a second line when too long for the card width
- Full keyboard and mouse navigation
- Click a vehicle to open a 3D preview with orbiting camera and zoom
- Purchase and deliver to your garage

**Weapon Browser:**
- 11 category tabs (All, Pistols, SMGs, Shotguns, Assault Rifles, Machine Guns, Sniper Rifles, Heavy Weapons, Melee, Throwables, Miscellaneous)
- Shows owned status and ammo refill option for owned weapons
- Ammo refill confirmation prompt with cost breakdown (rounds x per-round cost)
- Purchase gives weapon with starter ammo

**Gear Browser:**
- 3 category tabs: All, Protection, Equipment
- **Protection** (6 items): Super Light Armor ($500), Light Armor ($1,000), Standard Armor ($1,500), Heavy Armor ($2,000), Super Heavy Armor ($2,500), Juggernaut Armor ($50,000)
- **Equipment** (6 items): Parachute ($300), Tear Gas ($150), Fire Extinguisher ($100), Jerry Can ($100), Hazardous Jerry Can ($250), Night Vision ($5,000)
- Juggernaut Armor applies a full ballistic suit outfit, 1000 HP, 80% damage reduction, and heavy movement animation
- Night Vision adds a toggleable mode (press **N** while it is equipped)
- Purchased gear remains owned when unequipped. Press **Y** on the selected
  card or click its **UNEQUIP** badge to remove it, then select the owned card
  again to re-equip it without another charge.
- Protection uses one active equipment slot, so equipping another armor tier
  replaces normal or Juggernaut armor without removing ownership.
- Grid-based card layout matching the vehicle and weapon browsers

**Navigation:**
| Key | Action |
|-----|--------|
| Arrow keys | Navigate grid / menu |
| Enter | Select / Purchase |
| Escape | Back |
| Q / E | Previous / Next page |
| Z / X | Previous / Next category |
| Y | Unequip selected gear |
| Mouse | Full click and hover support |

### Traffic Spawner

Automatically integrates DLC vehicles into Story Mode traffic. Two systems work together:

**Driven Spawner** — creates new DLC vehicles with AI drivers:
- Up to 20 active DLC vehicles at a time
- Spawns 80-200m from the player on road nodes
- Cleans up vehicles beyond 350m
- 5-second cooldown between spawns
- Only spawns road-appropriate classes (no planes, boats, military in traffic)

**Replacement Scanner** — swaps vanilla ambient vehicles:
- Scans 200m radius every 3 seconds
- 30% replacement chance for a natural vanilla/DLC mix
- Class-matched replacements (a vanilla sedan becomes a DLC sedan)
- Minimum 50m distance before replacing

When `rich_areas_only_supers` is enabled, super and sports cars only appear in wealthy neighborhoods like Vinewood.

### Personal Garages

Garage storage is separate per character (Michael, Franklin, Trevor) and per
location. Eclipse Towers provides the original 10-car underground garage, the
three-floor garage provides oversized storage, and Davis adds a second 10-car
garage in the Los Santos Tuners Auto Shop interior.

Rockstar-managed story vehicles are excluded from every ALLIN1 garage and its
sale flow, even when a mission temporarily removes the vehicle's decorator or
map blip. A model-plus-unique-plate fallback protects Franklin's Buffalo S and Bagger, Trevor's Bodhi,
Michael's Tailgater and temporary Premier, Amanda's Sentinel, Tracey's Issi,
and Jimmy's BeeJay XL without blocking ordinary civilian copies of those models.

**Eclipse access:** Use the markers near Eclipse Towers on Eclipse Boulevard.

### Davis Auto Shop Garage

The Davis garage uses these surveyed exterior anchors:

- Vehicle entrance: `X 204.0661, Y -1466.4750, Z 29.1437`, heading `43.97`.
- Pedestrian entrance/exit: `X 215.0502, Y -1461.0250, Z 29.1847`, heading `49.38`.
- Interior pedestrian exit: `X -1357.6240, Y 153.2929, Z -99.1942`, heading `0`.

The vehicle door stores a driven-in car before loading the Auto Shop. The
pedestrian door enters on foot. Inside, GBAY uses Rockstar's native Auto Shop
10-car arrangement; leaving in a stored car removes it from storage and places
it outside the Davis vehicle door.

**Davis features:**

- Independent per-character persistence in `ALLIN1_davis_garage.json`.
- Ten fixed Auto Shop parking spaces with complete color, plate, wheel, mod,
  livery, neon, smoke, extra, and custom-color restoration.
- GBAY delivery targeting, garage browsing, selling, ownership filtering, and
  emergency recovery integration.
- Auto Shop customization for all nine styles and tints, the optional second
  lift, personal quarters, work-area fixtures, and storage decor. Choices are
  saved per protagonist in `ALLIN1_davis_customization.json` and apply live
  while the player is inside Davis.
- World markers and map blips follow the active protagonist: blue for Michael,
  green for Franklin, and orange for Trevor. Eclipse Towers and the three-floor
  garage use the same shared color behavior.

**Eclipse features:**
- 10 parking slots (two rows of 5, heading -105° and 134°)
- Vehicles persist across game sessions via `ALLIN1_garage.json`
- Vehicle colors are saved and restored
- Vehicles spawn at fixed Z=-99.0 coordinates when entering the garage interior
- Uses joaat hash-based reverse lookup for reliable model name resolution

**Sell Vehicles:**
- Each garage vehicle shows its sell price (60% of purchase price)
- Click the "Sell" button or press Enter to sell and receive the money
- Sell price is displayed inline next to each vehicle

**Detail Cars:**
- Click the "Detail All" button in the footer or press Q to clean all garage vehicles
- Costs $500 (configurable via free mode)
- Removes dirt and repairs visual damage on all stored vehicles

### Seat Selector

Hold **F** for 300ms near a vehicle to open the seat selection UI.

- Arrow keys to navigate available seats in a 2-column grid
- Release F or press Enter to enter the selected seat
- Quick tap F still works normally for default enter/exit
- Color indicators: blue (your seat), green (selected), gray (free), red (occupied)
- Works with multi-seat vehicles (buses, planes, etc.)

### Night Vision (N)

After purchasing and equipping Night Vision from the Gear shop, press **N** to
toggle night vision on/off. Unequipping it disables the effect but keeps the
item unlocked for later use. Active visual state resets on death or game reload.

### Juggernaut Armor

Purchased from the Gear shop ($50,000). When equipped:

- Applies the Paleto Score ballistic suit (character-specific drawables)
- Sets max health to 1000 and heals back 80% of damage each tick
- Disables headshot critical hit bonus
- Applies heavy movement animation clipset (`ANIM_GROUP_MOVE_BALLISTIC`)
- Saves and restores the previous outfit when removed
- Automatically removed on character switch or death
- Can be replaced by purchasing a lower armor tier

### World Vector Display (F10)

Press F10 to toggle a persistent overlay containing player position (X, Y, Z)
and heading. It is intended for scouting garage entrances, exits, parking slots,
and spawn positions.

---

## CLI Commands

The Python CLI is invoked via `allin1` after installation (`pip install -e .`).

```
allin1 [--config PATH] [--verbose] COMMAND
```

| Command | Description |
|---------|-------------|
| `install` | Install ALLIN1 into GTA V (deploy DLL, DLC pack, patch dlclist). |
| `uninstall` | Remove all ALLIN1 files and unpatch dlclist.xml. |
| `list [--class CLASS]` | List available vehicles, optionally filtered by class. |
| `status` | Show current installation status and configuration. |
| `export-catalog [--output PATH]` | Export vehicle database as JSON (default: `catalog/vehicles.json`). |
| `generate-vehiclelist [--output PATH]` | Regenerate `VehicleList.cs` from data files. |
| `generate-weaponlist [--output PATH]` | Regenerate `WeaponList.cs` from data files. |
| `import-previews SOURCE [--kind vehicle\|weapon\|equipment]` | Validate and import screenshots captured in-game. |
| `verify-preview-artifacts DIRECTORY` | Verify built YTD dictionary coverage. |
| `analyze-client-log LOG --edition EDITION` | Produce a machine-readable smoke report from an in-game session. |

### Advanced client diagnostics

The mod writes structured JSON-lines events to `scripts/ALLIN1_client.log` when
logging is enabled. Each event includes UTC time, severity, session ID,
component, message, optional operation fields, elapsed time, and exception
details. Logs rotate at 5 MiB with three retained archives. Run
`allin1 analyze-client-log` after an in-game qualification session to verify
vehicle creation, weapon granting, preview streaming, garage transitions, and
seat switching.

---

## Project Structure

```
GTA_V_ALLIN1/
├── .github/workflows/
│   └── build-asi.yml              # GitHub Actions CI build
├── data/
│   ├── vehicles.toml              # Vehicle database (461 entries)
│   ├── weapons.toml               # Weapon database (100+ entries)
│   └── templates/
│       └── popgroups_base.xml     # Population group template
├── script/
│   ├── ALLIN1.csproj              # C# project file (.NET 4.8, x64)
│   ├── src/                       # C# source files
│   │   ├── GbayShop.cs            # Script entrypoint, config, key handler
│   │   ├── GbayBrowser.cs         # Main browser state and vehicle/garage UI
│   │   ├── GbayBrowser.Gear.cs    # Gear storefront UI
│   │   ├── GbayRenderer.cs        # Drawing primitives and theme colors
│   │   ├── GbayInput.cs           # Input polling (keyboard + mouse)
│   │   ├── GarageManager.cs       # Eclipse and three-floor garage systems
│   │   ├── GarageManager.Davis.cs # Davis Auto Shop 10-car garage
│   │   ├── TrafficSpawner.cs      # DLC traffic integration
│   │   ├── SeatSelector.cs        # Hold-F seat picker
│   │   ├── VehicleHelper.cs       # Vehicle spawn utilities
│   │   ├── VehicleList.cs         # Auto-generated vehicle data (461 vehicles)
│   │   ├── WeaponList.cs          # Auto-generated weapon data
│   │   └── GearList.cs            # Static gear item data (12 items)
│   ├── tools/
│   │   ├── WorldVectorTool.cs     # F10 coordinate overlay (included)
│   │   └── SeatTestTool.cs        # F11 automated seat laboratory (included)
│   ├── dist/                      # Pre-built binaries
│   │   ├── ALLIN1.dll
│   │   ├── LemonUI.SHVDN3.dll
│   │   ├── PHAT.png               # GBAY logo
│   │   └── previews/              # Captured previews plus generated placeholders
│   └── out/                       # Alternative build output
├── src/allin1/                    # Python installer package
│   ├── cli.py                     # CLI commands (click)
│   ├── config.py                  # TOML config parsing
│   ├── installer.py               # Install/uninstall logic
│   ├── detector.py                # GTA V path auto-detection
│   ├── backup.py                  # File backup/restore
│   ├── asi_loader.py              # BattlEye bypass helper
│   ├── logging.py                 # Logging setup
│   ├── vehicles/database.py       # Vehicle database class
│   └── generators/
│       ├── vehiclelist.py         # VehicleList.cs generator
│       ├── weaponlist.py          # WeaponList.cs generator
│       ├── dlc_previews.py        # DLC pack structure generator
│       ├── dlclist.py             # dlclist.xml patcher
│       ├── ytd_builder.py         # PNG to YTD texture builder
│       ├── popgroups.py           # Population group generator
│       └── gameconfig.py          # Gameconfig helper
├── tools/
│   ├── RpfPatcher/                # C# tool for RPF archive manipulation
│   └── CodeWalker/                # RPF library dependency
├── tests/                         # Python unit tests
├── config.example.toml            # Configuration template
├── prices_vehicles.toml           # Vehicle price overrides
├── prices_weapons.toml            # Weapon price overrides
├── prices_gear.toml               # Gear price overrides
├── install.bat                    # Windows installer
├── uninstall.bat                  # Windows uninstaller
├── update.bat                     # Open the latest verified release
├── runtools.ps1                   # Build external tools (YTDToolio, RpfPatcher)
├── pyproject.toml                 # Python package metadata
└── README.md                      # Project overview
```

---

## Build System

### GitHub Actions (CI)

Defined in `.github/workflows/build-asi.yml`. Triggers on pushes to `script/` or manual dispatch.

**Steps:**
1. Restore NuGet packages (`dotnet restore`)
2. Build Release (`dotnet build -c Release`)
3. Copy `ALLIN1.dll` and `LemonUI.SHVDN3.dll` to `script/dist/`
4. Upload build artifacts
5. Auto-commit pre-built binaries to the repo

The auto-commit uses `github-actions[bot]` and does `git pull --rebase` before pushing to avoid conflicts.

### C# Project

- **Target:** .NET Framework 4.8, x64
- **Dependencies:** ScriptHookVDotNet3 (3.6.0), LemonUI.SHVDN3 (2.2.0), System.Windows.Forms
- **Exclusions:** `tools/**` is excluded from compilation by default
- **Inclusions:** `WorldVectorTool.cs` and `SeatTestTool.cs` are explicitly re-included for the F10 coordinate overlay and F11 seat laboratory
- **Output:** `script/dist/ALLIN1.dll`

### Building External Tools

Run `runtools.ps1` on Windows to build:
- **RpfPatcher.exe** — builds texture dictionaries, converts Enhanced resources, and safely updates RPF archives
- **YTDToolio.exe** — retained only as a legacy diagnostic utility; the installer no longer uses its corrupt PNG encoder

Requires Visual Studio 2022 with C++ desktop workload and .NET 6.0+ SDK.

---

## Code Generators

The C# data files `VehicleList.cs` and `WeaponList.cs` are auto-generated from TOML data files. Do not edit them manually.

### Vehicle List Generator

```bash
allin1 generate-vehiclelist
```

**Input:** `data/vehicles.toml` + `prices_vehicles.toml`

**Output:** `script/src/VehicleList.cs` containing:
- `string[] All` — all 461 model names
- Per-class arrays (`Compacts[]`, `Super[]`, `Weaponized[]`, etc.)
- `Dictionary<string, string> DisplayNames` — model to display name
- `Dictionary<string, int> Prices` — model to price
- `Dictionary<string, string> ClassNames` — model to class
- `Dictionary<string, string> PreviewDict` — model to YTD texture dict name

Preview textures are packed 89 per YTD file, named `allin1_prev_01` through `allin1_prev_05`.

### Weapon List Generator

```bash
allin1 generate-weaponlist
```

**Input:** `data/weapons.toml` + `prices_weapons.toml`

**Output:** `script/src/WeaponList.cs` containing:
- `string[] All` — all weapon names
- Per-category arrays (`Pistols[]`, `Smgs[]`, `Shotguns[]`, etc.)
- `Dictionary<string, string> DisplayNames`
- `Dictionary<string, int> Prices`
- `Dictionary<string, string> CategoryNames`
- `Dictionary<string, int> AmmoCostPerRound` — per-round ammo refill costs

---

## GBAY RPF Preview Textures

Catalog preview images are served to the in-game UI from the registered
`allin1_previews` DLC pack. Enhanced does not add arbitrary files placed in
`update2.rpf/textures` to the streamed-texture index; registering the nested RPF
through `content.xml` and `dlclist.xml` makes the dictionaries discoverable.

### Structure

```
mods/update/x64/dlcpacks/allin1_previews/dlc.rpf
├── content.xml
├── setup2.xml
└── x64/textures/textures.rpf
    ├── phat_logo.ytd
    ├── allin1_logo.ytd
    ├── allin1_prev_01.ytd
    ├── allin1_prev_02.ytd
    ├── allin1_weapon_01.ytd
    ├── allin1_weapon_02.ytd
    ├── allin1_gear_01.ytd
    └── ...
```

### Build Pipeline

1. **PNG source:** curated vehicle, weapon, and equipment art in `script/dist/previews/`, `script/dist/weapon_previews/`, and `script/dist/equipment_previews/`; models listed in `data/preview_pending.toml` use the runtime fallback until compatible art is available
2. **Texture encoding:** Pillow converts PNGs to standards-compliant BC3 DDS payloads
3. **YTD packing:** `RpfPatcher.exe build-ytd` writes Legacy texture dictionaries through CodeWalker (89 textures per YTD)
4. **Enhanced conversion:** `RpfPatcher.exe convert-gen9` converts the YTD resources for Gen9
5. **DLC packaging:** `RpfPatcher.exe build-dlc` embeds the YTDs in `x64/textures/textures.rpf`
6. **Verification:** `RpfPatcher.exe verify-dlc` extracts the nested archive and verifies every expected dictionary before deployment
7. **Registration:** the installer deploys `dlc.rpf` and patches current `mods/update/update.rpf/common/data/dlclist.xml`

### Runtime Loading

The C# script uses GTA native functions to load textures:
- `REQUEST_STREAMED_TEXTURE_DICT(dictName)` — request a YTD
- `HAS_STREAMED_TEXTURE_DICT_LOADED(dictName)` — check if ready
- `DRAW_SPRITE(dictName, textureName, ...)` — render on screen

Textures are loaded on demand per page and pre-fetched one page ahead. Unused dicts are released when scrolling away.

### RpfPatcher Commands

| Command | Description |
|---------|-------------|
| `build-ytd <dds_folder> <output_ytd> [legacy\|gen9]` | Build a YTD from validated DDS payloads |
| `unpack-ytd <ytd_path> <output_folder> [legacy\|gen9]` | Extract DDS payloads for visual verification |
| `build-dlc <folder> <output> [--embed-rpf <src> <dest>]` | Pack loose folder into dlc.rpf with optional nested RPF |
| `verify-dlc <dlc_rpf> <ytd_folder>` | Read back metadata, nested RPF, and every expected YTD |
| `patch <gta_path>` | Add `allin1_previews` to dlclist.xml |
| `unpatch <gta_path>` | Remove `allin1_previews` from dlclist.xml |
| `inject-ytd <gta_path> <ytd_folder>` | Inject YTDs into `script_txds.rpf` |
| `verify-ytd <gta_path> <ytd_folder>` | Verify all expected YTDs after injection |
| `remove-ytd <gta_path> <prefix>` | Remove injected YTDs |
| `inspect <gta_path> <rpf_path>` | Dump RPF structure for debugging |
| `audit-seats <gta_path> <output_json> [output_cs]` | Extract every base-game and DLC vehicle layout, seat role, occupant-access door, and hatch; also emit Markdown and an optional C# lookup |

---

## Tools

Development tools live in `script/tools/`. The csproj excludes all `tools/**` from compilation by default; individual tools are re-included via `<Compile Include>` entries.

### World Vector Overlay (F10) — Included in Build

Press F10 to show or hide player position and heading on screen. The retired
preview-capture menu and screenshot actions are no longer part of the
production script.

Format: `X 123.4567  Y -456.7890  Z 89.0123` plus `Heading 180.50`.

Implemented in `script/tools/WorldVectorTool.cs`.

### Seat Laboratory (F11 / Shift+F11) — Included in Build

Enter or stand near the vehicle model to test, then press F11. The laboratory
clones that model at the flat Sandy Shores airfield test site, clears ambient
peds and vehicles, pauses ALLIN1 traffic, and runs a directed matrix covering
outside access plus every source-seat to target-seat transition. Setup and
session restoration may place the player directly; every measured transition
uses the production selector's animation-only path.

Rolling trial records survive an interrupted run in
`scripts/ALLIN1_seat_tests/*.jsonl`. Completed runs also update a per-model JSON
report, `ALLIN1_seat_catalog.jsonl`, and the append-only
`ALLIN1_seat_outliers.jsonl` refinement queue. F11 aborts a run and restores the
player's previous location or vehicle seat.

Press Shift+F11 while on foot to run the curated fleet suite. It covers real
physical turret, gunner, and unconventional passenger stations while excluding
driver-controlled remote weapons and interior weapon consoles that are not
vehicle seats. Ground vehicles and aircraft use Sandy Shores; the Weaponized
Dinghy uses an open-water Del Perro arena. The suite checkpoints after every
model, treats unavailable models as skipped rather than failed, and writes
`latest-unconventional-seat-fleet.json` with aggregate results and links to its
per-model reports. F11 aborts either mode safely.

Implemented in `script/tools/SeatTestTool.cs`.

### Vehicle Seat Metadata Catalog

`catalog/vehicle_seats.json` is generated from Rockstar's active `vehicles.meta`
and `vehiclelayouts*.meta` definitions. The audit scans `common.rpf`,
`update.rpf`, modern loose DLC packs, and the early DLC packs consolidated in
root `x64*.rpf` archives. It resolves patch priority and records, per model:

- the ordered native seat indices (driver is `-1`), semantic labels, and turret roles;
- the source layout and DLC pack;
- unique occupant-access door bones and separate access hatches; and
- the raw Rockstar seat identifier for later forensic review.

The generated `script/src/VehicleSeatLayoutCatalog.cs` supplies these labels to
the production selector. Seat Lab reports both the metadata seat count and GTA's
runtime count, so disagreement is logged rather than concealed. The curated
Shift+F11 fleet remains the focused regression suite for physical turrets,
rappel, bench, bed, and other layouts where a declared seat can still be
unreachable in practice.

Regenerate the current catalog and runtime lookup with:

```powershell
tools\RpfPatcher\RpfPatcher.exe audit-seats `
  "D:\Path\To\Grand Theft Auto V" `
  catalog\vehicle_seats.json `
  script\src\VehicleSeatLayoutCatalog.cs
```

The completed preview-capture, height-check, interior-scout, and outfit tools
are archived outside the production repository. They can be recovered for a
future DLC pass without shipping dormant developer scripts to players.

Curated capture imports remain available through `allin1 import-previews
SOURCE --kind vehicle`, `--kind weapon`, or `--kind equipment`.

---

## Data Files

### data/vehicles.toml

461 vehicle entries with the following fields per vehicle:

```toml
[[vehicles]]
model = "adder"
name = "Truffade Adder"
class = "super"
manufacturer = "Truffade"
traffic = ["veh_rich"]
```

Traffic pool assignments: `veh_poor` (low-income areas), `veh_mid` (middle-class), `veh_rich` (wealthy areas like Vinewood).

### data/weapons.toml

100+ weapon entries:

```toml
[[weapons]]
name = "WEAPON_PISTOL"
label = "Pistol"
category = "pistols"
price = 500
```

Categories: pistols, smgs, shotguns, rifles, machineguns, snipers, heavy, melee, throwables, misc.

### Price Files

`prices_vehicles.toml`, `prices_weapons.toml`, and `prices_gear.toml` at the project root allow customizing prices without editing the core data files.

Vehicle and weapon prices are grouped by class/category:

```toml
[super]
adder = 1000000
t20 = 2200000
```

Gear prices are flat key-value pairs:

```toml
ARMOR_SUPER_LIGHT = 500
ARMOR_LIGHT = 1000
GADGET_PARACHUTE = 300
WEAPON_NIGHTVISION = 5000
```

Vehicle and weapon price changes require regenerating the C# list files and rebuilding. Gear price changes take effect at runtime (loaded from `scripts/prices_gear.toml` on script init).

### GearList.cs (Hand-Written)

Unlike VehicleList.cs and WeaponList.cs, `GearList.cs` is hand-written since the gear catalog is small (12 items) and stable. It contains:
- `string[] All`, `Protection[]`, `Equipment[]` — item ID arrays
- `Dictionary<string, string> DisplayNames`
- `Dictionary<string, int> Prices` — default prices (overridden by prices_gear.toml)
- `Dictionary<string, string> CategoryNames`
- `Dictionary<string, int> ArmorValues` — armor tier to armor value (0-100)
- `bool IsArmor(string gearId)` — helper to check if an item is armor

### Garage Persistence

Garage state is split into independent files in the scripts directory:

- `ALLIN1_garage.json` — Eclipse Towers.
- `ALLIN1_floor_garage.json` — three-floor garage.
- `ALLIN1_davis_garage.json` — Davis Auto Shop.
- `ALLIN1_davis_customization.json` — per-character Davis Auto Shop themes and upgrades.

Each file stores per-character vehicle data, including complete customization
state. Atomic writes retain a `.bak` recovery copy. A representative entry is:

```json
{
  "michael": [
    { "model": "zentorno", "slot": 0, "color1": 12, "color2": 0 },
    ...
  ],
  "franklin": [],
  "trevor": []
}
```

Model names are stored as spawn names (e.g., `"zentorno"` not GXT labels). A migration step runs on load to fix any legacy entries that stored GXT labels by performing a joaat hash reverse lookup against the full vehicle list.

---

## Troubleshooting

### Menu doesn't open (F9)

- Verify `ScriptHookV.dll` is in the GTA V root directory
- Verify `ScriptHookVDotNet.asi` is in the GTA V root directory
- Check that `ALLIN1.dll` exists in the `scripts/` folder
- Check `scripts/ALLIN1_gbay.log` for error messages
- Try setting `enable_logging = true` in config for more detail

### Game crashes when opening menu

- The DLC texture pack may be malformed or incompatible with your GTA V edition
- Try removing `mods/update/x64/dlcpacks/allin1_previews/` and testing without textures
- Rebuild the DLC pack with the correct encryption for your edition (Enhanced vs Legacy)

### No DLC vehicles in traffic

- Check `[traffic] enabled = true` in config
- Enable detailed logging in the launcher and check `scripts/ALLIN1.log` for suppression reasons

### Vehicles are free / wrong prices

- Check the `gbay_free_mode` setting in config (`free_mode` is its legacy alias)
- Edit `prices_vehicles.toml`, `prices_weapons.toml`, or `prices_gear.toml` to adjust prices
- Re-run `allin1 generate-vehiclelist` and `allin1 install` after changing vehicle/weapon prices
- Gear prices reload automatically on script init

### Garage not saving vehicles

- Check that the applicable `scripts/ALLIN1_garage.json`,
  `scripts/ALLIN1_floor_garage.json`, or `scripts/ALLIN1_davis_garage.json` is writable
- Each character (Michael, Franklin, Trevor) has a separate 10-slot garage
- Vehicles must be purchased through GBAY and delivered to the garage

### Vehicles floating in garage

- The garage interior is underground at Z=-99.0. Vehicle placement uses `SET_ENTITY_COORDS` to force exact slot positions rather than `SET_VEHICLE_ON_GROUND_PROPERLY` (which is unreliable in interiors).
- If vehicles still appear offset, record the affected model and garage slot for a targeted placement adjustment.

### Preview images not showing

- The DLC pack must be properly installed and registered in dlclist.xml
- Check that `mods/update/x64/dlcpacks/allin1_previews/dlc.rpf` exists
- For Enhanced edition, ensure OpenRPF.asi is installed
- For Legacy edition, ensure OpenIV.asi is installed
- Check the debug subtitle when browsing vehicles — it shows texture dict loading status

---

## File Deployment Map

After `allin1 install`, the following files exist in the GTA V directory:

```
<GTA V root>/
├── scripts/
│   ├── ALLIN1.dll                 # Main script
│   ├── LemonUI.SHVDN3.dll        # UI dependency
│   ├── ALLIN1.toml                # Configuration
│   ├── prices_gear.toml           # Gear price overrides
│   ├── ALLIN1.log                 # Runtime log (if logging enabled)
│   ├── ALLIN1_gbay.log            # GBAY shop log
│   ├── ALLIN1_garage.json         # Eclipse Towers persistence
│   ├── ALLIN1_floor_garage.json   # Three-floor garage persistence
│   ├── ALLIN1_davis_garage.json   # Davis Auto Shop persistence
├── mods/update/x64/dlcpacks/
│   └── allin1_previews/
│       └── dlc.rpf                # Preview texture DLC pack
├── mods/update/
│   └── update.rpf                 # Patched dlclist.xml
└── commandline.txt                # -nobattleye flag
```

---

## Architecture Notes

### GbayBrowser State Machine

The browser UI (`GbayBrowser.cs`) uses a simple state enum to manage navigation:

```
Closed → TopMenu → VehicleBrowser → VehiclePreview → DeliveryConfirm
                 → WeaponBrowser
                 → GearBrowser
                 → GarageView
```

Each state has its own Draw and Input handler methods. The top menu routes to sub-browsers, and Escape always returns one level up.

### Vehicle Model Resolution

GTA V's `GET_DISPLAY_NAME_FROM_VEHICLE_MODEL` returns GXT label hashes, not spawn names. ALLIN1 builds a reverse lookup dictionary at init time:

```csharp
foreach (string name in VehicleList.All)
    _hashToSpawnName[Game.GenerateHash(name)] = name;
```

This is used when a vehicle drives into the garage (hash from `GET_ENTITY_MODEL` → spawn name) and during save file migration.

### SHVDN3 Script Auto-Discovery

ScriptHookVDotNet uses reflection to find and instantiate all classes that inherit from `Script` in the loaded DLL. This means every `public class Foo : Script` in the compiled assembly will run automatically — there's no explicit registration. The `<Compile Remove="tools\**" />` csproj rule keeps development tools out of production builds.
