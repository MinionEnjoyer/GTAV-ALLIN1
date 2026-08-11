# GTA runtime smoke checklist

Run this checklist on both Legacy and Enhanced after automated tests pass.

- Start Story Mode with BattlEye disabled; confirm no ScriptHook or SHVDN load errors.
- Open GBAY with F9 and navigate every vehicle, weapons, gear, and garage screen.
- Purchase, spawn, customize, store, retrieve, sell, and remove a vehicle.
- Restart the game and confirm garage, balance, ownership, and configuration persistence.
- Drive through poor, middle, rich, highway, emergency, air, and water spawn regions.
- Hold F in 2-, 4-, and 6-seat vehicles; verify selection, cancellation, and occupied seats.
- Equip and remove armor, Juggernaut, night vision, weapons, ammo, and throwables.
- Confirm preview textures load and no placeholder remains for catalogued vehicles.
- Switch protagonists, die, reload a save, enter interiors, and reload scripts.
- Uninstall and confirm Story Mode starts cleanly with original command-line flags retained.
- Inspect `scripts/ALLIN1*.log` and ScriptHookVDotNet logs for errors or runaway loops.
