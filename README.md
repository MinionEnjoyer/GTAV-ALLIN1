# GTA V ALLIN1
ALLIN1 is a mod installer that ports Online content into SP mode for GTA V.

 - Requires ScriptHookV and ScriptHookDotNetEnhanced.
 - Drop the ScriptHook files into the directory with your GTA.exe and then run the ALLIN1 installer.  It will automatically detect your game directory and install.

## Desktop manager

Run `install.bat` once to create the virtual environment, then double-click
`manager.bat`. You can also launch it from a terminal with:

```bat
.venv\Scripts\allin1-gui.exe
```

The manager detects the game edition and prerequisites, edits the common options,
and provides Install/Repair and Uninstall actions with an activity log. Use ALLIN1
only in Story Mode; the installer configures GTA V to launch without BattlEye.

## Testing

The automated harness covers Python units and commands, mocked game-file operations,
Steam/platform detection, generator pipelines, data/catalog consistency, release
artifact contracts, the C# script build, and the native ASI build.

On Windows, run `powershell -ExecutionPolicy Bypass -File test-all.ps1`. On Linux or
macOS, run `sh test-all.sh`. Native GTA behavior still requires the manual in-game
smoke checklist in `tests/IN_GAME_CHECKLIST.md` because ScriptHook APIs need a running
game process.

## Features

- A traffic spawn sytstem to integrate DLC content around Los Santos.
- GBAY web portal to purchase/deliver DLC content.  (Can be made free in config.  Prices can be adjusted in prices_vehicles.toml and prices_weapons.toml).
- Custom garage system.
- Juggernaut armour from the Paleto heist, nightvision, and equipment equip/unequip options.
- Vehicle seat system (hold down F and switch using arrow keys).
- DLC spawner for emergency vehicles. (Enable in config file).

## If you found this project useful, consider supporting me here: https://buymeacoffee.com/minionenjoyer Thank you!

## Optional mod packages

The desktop launcher's **Mods** tab can install, update, enable, disable, and
uninstall local ASI, ScriptHookVDotNet script, RPF, and config/data packages.
Packages use a small `mod.toml` manifest so the launcher can validate editions,
loader dependencies, conflicts, destination paths, and optional SHA-256 hashes.
Replaced files are backed up and restored on uninstall. See
[`mods/README.md`](mods/README.md) for the package format and inert examples.
