# GTA V ALLIN1 — Comprehensive Documentation

GTA V ALLIN1 is a mod installer that ports 444 GTA Online DLC vehicles, 100+ weapons, and gear into GTA V single-player Story Mode. It includes a traffic spawner, an in-game shop (GBAY), a personal garage system, and a vehicle seat selector.

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
5. Builds and deploys the preview texture DLC pack to `mods/update/x64/dlcpacks/allin1_previews/`
6. Patches `dlclist.xml` inside `mods/update/update.rpf` to register the DLC
7. Adds `-nobattleye` to `commandline.txt`
8. Auto-downloads OpenRPF if missing (Enhanced edition only)

### Uninstall

Run `uninstall.bat` to remove all ALLIN1 files, unpatch `dlclist.xml`, and clean up legacy files.

### Update

Run `update.bat` to pull the latest version and redeploy.

---

## Configuration

Configuration is stored in `config.toml` (copied to `scripts/ALLIN1.toml` during install). See `config.example.toml` for all options with comments.

### [general]

| Key | Default | Description |
|-----|---------|-------------|
| `gta_path` | `"auto"` | GTA V installation path. Set to `"auto"` for auto-detection. |
| `free_mode` | `false` | When true, all vehicles are free in-game. |
| `backup` | `true` | Create backups of original game files before modifying. |

### [traffic]

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Add GTA Online vehicles to ambient traffic. |
| `rich_areas_only_supers` | `true` | Super/sports cars spawn only in wealthy neighborhoods. |

### [vehicles]

| Key | Default | Description |
|-----|---------|-------------|
| `enable_all` | `true` | Enable all 444 DLC vehicles. When false, use catalog to pick specific ones. |
| `disabled_classes` | `[]` | Vehicle classes to exclude (e.g., `["helicopters", "planes", "boats"]`). |
| `disabled_vehicles` | `[]` | Specific model names to exclude (e.g., `["adder", "t20"]`). |

Available classes: `compacts`, `coupes`, `sedans`, `suvs`, `muscle`, `sports`, `sportsclassics`, `super`, `offroad`, `motorcycles`, `military`, `industrial`, `vans`, `boats`, `helicopters`, `planes`, `openwheel`, `emergency`, `service`, `cycles`.

### [script]

| Key | Default | Description |
|-----|---------|-------------|
| `gbay_key` | `"F9"` | Key to open the GBAY shop menu. Uses .NET `Keys` enum names. |
| `gbay_free_mode` | `false` | All GBAY purchases are free regardless of prices. |
| `enable_logging` | `false` | Write debug info to `scripts/ALLIN1.log`. |
| `enable_dlc_police` | `false` | Replace vanilla police cars with DLC police vehicles. |
| `spawner_debug` | `false` | Show vehicle spawn debug notifications. |
| `garage_debug` | `false` | Show debug markers at garage parking slots. |

### Price Customization

Vehicle and weapon prices are defined in two separate files at the project root:

- `prices_vehicles.toml` — grouped by vehicle class
- `prices_weapons.toml` — grouped by weapon category

Edit these files and re-run the installer (or regenerate the lists via CLI) to change in-game prices.

---

## In-Game Features

### GBAY Shop (F9)

Press **F9** (configurable) to open the GBAY shop menu.

**Top Menu** — choose between:
- **Vehicles** — browse and purchase 444 DLC vehicles
- **Weapons** — browse and purchase 100+ weapons
- **Gear** — purchase body armor, parachute, and utility items
- **My Garage** — manage stored vehicles

**Vehicle Browser:**
- 20 category tabs (Compacts, Coupes, Sedans, etc.) with scroll arrows
- 3x3 card grid per page with vehicle preview images, name, manufacturer, and price
- Full keyboard and mouse navigation
- Click a vehicle to open a 3D preview with orbiting camera
- Purchase and deliver to your current location

**Weapon Browser:**
- 10 category tabs (Pistols, SMGs, Shotguns, Rifles, etc.)
- Shows owned status and ammo refill option
- Purchase gives weapon with starter ammo

**Gear Browser:**
- Categories: All, Protection, Equipment
- Items: Body Armor ($500), Parachute ($300), Tear Gas ($150), Fire Extinguisher ($100), Jerry Can ($100), Hazardous Jerry Can ($250), Night Vision ($5,000)
- Armor can be re-purchased to top up; gadgets show "OWNED" once acquired

**Navigation:**
| Key | Action |
|-----|--------|
| Arrow keys | Navigate grid / menu |
| Enter | Select / Purchase |
| Escape | Back |
| Q / E | Previous / Next page |
| Z / X | Previous / Next category |
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

### Personal Garage

10-vehicle garage at Eclipse Towers underground interior, per character (Michael, Franklin, Trevor).

**Access:** Walk to the marker near Eclipse Towers on Eclipse Boulevard.

**Features:**
- 10 parking slots (two rows of 5)
- Vehicles persist across game sessions via `ALLIN1_garages.json`
- Vehicle colors are saved and restored
- Vehicles spawn when entering and despawn when leaving

### Seat Selector

Hold **F** for 300ms near a vehicle to open the seat selection UI.

- Arrow keys to navigate available seats in a 2-column grid
- Release F or press Enter to enter the selected seat
- Quick tap F still works normally for default enter/exit
- Color indicators: blue (your seat), green (selected), gray (free), red (occupied)
- Works with multi-seat vehicles (buses, planes, etc.)

### Coordinate Display (F11)

Development tool. Press **F11** to toggle an on-screen overlay showing player position (X, Y, Z) and heading. Useful for finding coordinates for garage slots and spawn positions.

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

---

## Project Structure

```
GTA_V_ALLIN1/
├── .github/workflows/
│   └── build-asi.yml              # GitHub Actions CI build
├── data/
│   ├── vehicles.toml              # Vehicle database (444 entries)
│   ├── weapons.toml               # Weapon database (100+ entries)
│   └── templates/
│       └── popgroups_base.xml     # Population group template
├── script/
│   ├── ALLIN1.csproj              # C# project file (.NET 4.8, x64)
│   ├── src/                       # C# source files
│   │   ├── GbayShop.cs            # Script entrypoint, config, key handler
│   │   ├── GbayBrowser.cs         # Full browser UI (vehicles, weapons, gear, garage)
│   │   ├── GbayRenderer.cs        # Drawing primitives and theme colors
│   │   ├── GbayInput.cs           # Input polling (keyboard + mouse)
│   │   ├── GarageManager.cs       # 10-car garage with persistence
│   │   ├── TrafficSpawner.cs      # DLC traffic integration
│   │   ├── SeatSelector.cs        # Hold-F seat picker
│   │   ├── VehicleHelper.cs       # Vehicle spawn utilities
│   │   ├── VehicleList.cs         # Auto-generated vehicle data
│   │   ├── WeaponList.cs          # Auto-generated weapon data
│   │   └── GearList.cs            # Static gear item data
│   ├── tools/
│   │   ├── CoordinateDisplay.cs   # F11 position overlay (included in build)
│   │   └── GbayPreviewCapture.cs  # F10 automated screenshot tool (excluded)
│   └── dist/                      # Pre-built binaries
│       ├── ALLIN1.dll
│       ├── LemonUI.SHVDN3.dll
│       ├── PHAT.png               # GBAY logo
│       └── previews/              # 444 vehicle preview PNGs
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
├── install.bat                    # Windows installer
├── uninstall.bat                  # Windows uninstaller
├── update.bat                     # Update script
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
- **Exclusions:** `tools/**` is excluded from compilation except `CoordinateDisplay.cs`
- **Output:** `script/dist/ALLIN1.dll` (~142 KB)

### Building External Tools

Run `runtools.ps1` on Windows to build:
- **YTDToolio.exe** — converts PNG images to GTA V `.ytd` texture dictionaries
- **RpfPatcher.exe** — manipulates RPF archives (build DLC packs, patch dlclist.xml)

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
- `string[] All` — all 444 model names
- Per-class arrays (`Compacts[]`, `Super[]`, etc.)
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

---

## DLC Texture Pack

Vehicle preview images are served to the in-game UI via a custom GTA V DLC pack.

### Structure

```
mods/update/x64/dlcpacks/allin1_previews/dlc.rpf
├── content.xml          # Registers textures.rpf as RPF_FILE
├── setup2.xml           # DLC metadata (EXTRACONTENT_COMPAT_PACK)
└── x64/textures/
    └── textures.rpf     # Contains all .ytd texture dictionaries
        ├── allin1_logo.ytd
        ├── allin1_prev_01.ytd
        ├── allin1_prev_02.ytd
        └── ...
```

### Build Pipeline

1. **PNG source:** 444 preview images in `script/dist/previews/`
2. **YTD packing:** `YTDToolio.exe` converts PNGs to `.ytd` files (DXT1 compression, 89 textures per YTD)
3. **DLC structure:** Python generates `content.xml` and `setup2.xml`
4. **RPF packing:** `RpfPatcher.exe build-dlc` creates outer `dlc.rpf` with nested `textures.rpf`
5. **Deployment:** `dlc.rpf` copied to `mods/update/x64/dlcpacks/allin1_previews/`
6. **Registration:** `RpfPatcher.exe patch` adds entry to `dlclist.xml` in `mods/update/update.rpf`

### Runtime Loading

The C# script uses GTA native functions to load textures:
- `REQUEST_STREAMED_TEXTURE_DICT(dictName)` — request a YTD
- `HAS_STREAMED_TEXTURE_DICT_LOADED(dictName)` — check if ready
- `DRAW_SPRITE(dictName, textureName, ...)` — render on screen

### RpfPatcher Commands

| Command | Description |
|---------|-------------|
| `build-dlc <folder> <output> [--embed-rpf <src> <dest>]` | Pack loose folder into dlc.rpf with optional nested RPF |
| `patch <gta_path>` | Add `allin1_previews` to dlclist.xml |
| `unpatch <gta_path>` | Remove `allin1_previews` from dlclist.xml |
| `inject-ytd <gta_path> <ytd_folder>` | Inject YTDs into script_txds.rpf (legacy method) |
| `remove-ytd <gta_path> <prefix>` | Remove injected YTDs |
| `inspect <gta_path> <rpf_path>` | Dump RPF structure for debugging |

---

## Tools

### CoordinateDisplay (F11) — Included in Build

Toggle with **F11** to show player position and heading on screen.

Format: `X:123.4  Y:-456.7  Z:89.0  H:180.5`

Located at `script/tools/CoordinateDisplay.cs`. Included in the build via `ALLIN1.csproj`.

### GbayPreviewCapture (F10) — Excluded from Build

Automated vehicle screenshot tool. Press **F10** to cycle through all 444 vehicles, spawning each at a fixed showroom location and capturing a side-profile screenshot.

- Showroom position: (-736, -1455.7, 4.5) near LSIA
- Camera: dynamic radius based on vehicle dimensions, 50° FOV
- Output: `scripts/previews/{model}.png`
- Progress bar shown on screen during capture

Located at `script/tools/GbayPreviewCapture.cs`. Excluded from build by default. To enable, add a `<Compile Include>` entry in `ALLIN1.csproj`.

---

## Data Files

### data/vehicles.toml

444 vehicle entries with the following fields per vehicle:

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

`prices_vehicles.toml` and `prices_weapons.toml` at the project root allow customizing prices without editing the TOML databases. Grouped by class/category:

```toml
[super]
adder = 1000000
t20 = 2200000
```

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
- Set `spawner_debug = true` to see spawn notifications
- Check `scripts/ALLIN1.log` for spawner errors

### Vehicles are free / wrong prices

- Check `free_mode` and `gbay_free_mode` settings in config
- Edit `prices_vehicles.toml` or `prices_weapons.toml` to adjust prices
- Re-run `allin1 generate-vehiclelist` and `allin1 install` after changing prices

### Garage not saving vehicles

- Check that `scripts/ALLIN1_garages.json` is writable
- Each character (Michael, Franklin, Trevor) has a separate 10-slot garage
- Vehicles must be parked inside the garage interior to save

### Preview images not showing

- The DLC pack must be properly installed and registered in dlclist.xml
- Check that `mods/update/x64/dlcpacks/allin1_previews/dlc.rpf` exists
- For Enhanced edition, ensure OpenRPF.asi is installed
- For Legacy edition, ensure OpenIV.asi is installed

---

## File Deployment Map

After `allin1 install`, the following files exist in the GTA V directory:

```
<GTA V root>/
├── scripts/
│   ├── ALLIN1.dll                 # Main script
│   ├── LemonUI.SHVDN3.dll        # UI dependency
│   ├── ALLIN1.toml                # Configuration
│   ├── ALLIN1.log                 # Runtime log
│   ├── ALLIN1_gbay.log            # GBAY shop log
│   ├── ALLIN1_spawner.log         # Traffic spawner log
│   └── ALLIN1_garages.json        # Garage persistence
├── mods/update/x64/dlcpacks/
│   └── allin1_previews/
│       └── dlc.rpf                # Preview texture DLC pack
├── mods/update/
│   └── update.rpf                 # Patched dlclist.xml
└── commandline.txt                # -nobattleye flag
```
