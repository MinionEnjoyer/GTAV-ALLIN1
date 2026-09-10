# Driving HUD, shifting and hitch telemetry

The built-in speedometer is a small non-interactive **React HUD rendered by Reactor V**, not a resized GBAY window and not LemonUI/native text. It uses Reactor's new passive-HUD contract, separate from menu/input ownership. The HUD shows speed, KMH/MPH, AUTO or MANUAL (sequential hold), and the current native gear. GTA gear zero is labelled `R`, never invented neutral. Unsupported readings display `?`.

This candidate requires the coordinated Reactor V build with `PassiveHudContract` v1 (Core, Script, Runtime/Preloader and browser assets). An older installed Reactor still supports GBAY but cannot show this HUD: ALLIN1 logs `passive_hud_unavailable_update_reactor_v`, without falling back to native drawing or forcing a menu open. Telemetry/shifting remain independent. Candidate components are built locally; installation and in-game validation are separate steps.

HUD updates are bounded to 10 Hz. Both native host and React readout revoke stale data, and the React readout clears after one second without updates. Menu presentation supersedes the HUD; it never acquires pointer/keyboard ownership. The dependency contains only a generic speedometer prefab/protocol, no ALLIN1-specific content.

The built-in HUD hides while the player uses the phone, during a phone call, or while the in-vehicle phone camera is active. It returns automatically when phone use ends and the normal driving visibility checks permit it. Phone use does not change the saved provider/units, reset gear hold, or interrupt telemetry. Visibility transitions are logged as `hud_visibility` with reason `phone`; external speedometer mods control their own displays.

Holding the character-wheel control (Alt by default, or its remapped/controller binding) also hides the built-in HUD. It stays hidden during an actual character switch and returns after cancelling or completing selection, once normal driving visibility checks permit it. This uses GTA's input state, including disabled controls while the selector owns input, and logs reason `character_switch`; it does not change saved display preferences.

## Configuration and controls

Launcher **Gameplay** exposes these settings. They also round-trip through the launcher config/CLI/API and deploy to `scripts/ALLIN1.toml`:

```toml
[script]
speedometer_provider = "auto" # auto | builtin | rex | lefix | off
speedometer_units = "kmh"     # kmh | mph
driving_telemetry = "towing"  # off | towing | all
shift_controls_enabled = true
```

- Numpad decimal: switch **ALLIN1** units for the current session. Save the preferred default in the launcher. It does not change an external mod's units.
- Numpad `*`: opt into experimental sequential **forward-gear hold**; press again to return to automatic. Every session/vehicle starts automatic. Enter while GTA reports a valid forward gear and the engine is running.
- Numpad `+` / `−`: shift up/down while holding gears. Each press is one shift, with a 250 ms minimum interval. High-RPM downshifts are conservatively rejected; this is not a calculated gear-ratio/redline model.

This is **not** a full manual-transmission simulation: no clutch, neutral, reverse selector, torque model, or handling/gear-ratio edits. Return to automatic for reverse. It uses SHVDN CurrentGear/NextGear properties and verifies readback; road behaviour still requires in-game testing on each edition.

Gear writes stop on safe/recovery mode, menus, pause, loss of game focus, missions, cutscenes/loading, garage transitions, death, leaving the driver's seat, vehicle identity changes, invalid gear/RPM readings, or a detected competing transmission module. Gear control is restricted to cars/bikes. It must be explicitly re-enabled after suspension; held keys are not replayed. No Online operation.

## External speedometers

`auto` chooses a loaded Rex FSS assembly first, then a loaded LeFixSpeedo ASI, otherwise the ALLIN1 HUD. `rex`/`lefix` select that provider, falling back to ALLIN1 if it is not detected. `off` hides the built-in HUD without disabling telemetry or configured shift controls. To ensure ALLIN1 never draws alongside an external display with an unrecognised filename/assembly name, select `off`.

This is **coexistence support**, not a private telemetry injection API. Both external mods read the game's vehicle state independently. Detection proves a module/assembly was loaded, not that its HUD is enabled or drawing. Nothing is downloaded, bundled, launched, or written to third-party configuration.

- [Rex Forza Styled Speedometer documentation](https://rexmods-dev.github.io/rexmods/FSSDocs.html): install the correct edition separately; use its native GTA gear source with ALLIN1. Its Numpad 1–3 controls remain untouched. Units and assist settings stay in FSS. Disable overlapping car/manual-reverse controls before testing ALLIN1 gear hold.
- [LeFix Speedometer](https://www.gta5-mods.com/scripts/lefix-speedometer): install a version compatible with your game edition; configure its units/display in its own menu. [Maintainer's source](https://github.com/ikt32/gta5-speedometer) is separate; none of its GPL code is incorporated here.
- Loaded `Gears.asi`, `ManualTransmission.asi`, or `CustomGearRatios.asi` disable ALLIN1 gear writes. There is no call to undocumented shift functions. Other/renamed transmission controllers cannot be reliably identified: set `shift_controls_enabled = false` when using them. The display/telemetry remain usable.

External-mod coexistence and native gear-hold behaviour are **not yet game-verified** by automated tests.

## Test data

`scripts/ALLIN1_driving.jsonl` receives local JSONL events and samples at up to **5 Hz** while driving in free roam. Default `towing` records samples only with a currently observed native or ALLIN1 physical connection. `all` also records solo driving. `off` disables this log entirely. No upload or location tracking.

Each row has schema version, session ID, UTC timestamp, kind and dropped-sample count. Samples contain game time, vehicle/model identity, speed in m/s, signed longitudinal speed, speed-magnitude acceleration in m/s², sample interval, current/next/high gear, requested held gear, normalized RPM (not engine RPM), steering angle, throttle/brake inputs, roll/pitch and collision flag. Frame timing includes the **worst observed frame since the previous sample**, to help spot hitches in rendering/frame delivery.

The `joints` array records both front/rear connections: trailer identity/speed/roll/pitch/collision, attachment mode, known hitch ID, coupler gap in metres and wrapped relative yaw in degrees. Configured physical break force is metadata, **not measured joint force**. Missing bone/profile data is `null`, not zero. Native towing outside an authored profile may have unknown hitch/gap values.

Events include connect attempts/results, disconnects, failed actions, observed/lost couplings, observation suspension, shifts, display provider and runtime failures. `coupling_no_longer_observed` does **not** establish a break-force failure: despawning or another script can also remove a connection. Leaving the seat or suspending sampling emits `observation_ended` instead.

All native reads occur on the game thread. Detached data enters a bounded 512-row queue; a single background writer handles disk I/O. Overflow drops samples rather than blocking gameplay. Logs rotate at 8 MiB to `.1`, `.2`, `.3` (about 32 MiB total). Disk failure stops logging with a warning. Shutdown drains for at most 500 ms; a crash/slow disk can lose the last buffered rows. Acceleration is invalidated across observation/vehicle changes and long sample gaps.

## Next in-game validation

1. Native rear trailer: accelerate, brake, turn, reverse in automatic, disconnect. Confirm correct units, gears, gap/yaw data and disconnect events.
2. Experimental front joint: begin at walking pace in an open area, turn gently, then compare yaw/gap/roll with rear towing. Watch for jackknifing and collision instability; telemetry does not change joint physics.
3. Gear hold: test each shift, high-RPM downshift refusal, return to auto; then open GBAY, pause, change vehicles and verify it remains automatic until re-enabled.
4. Repeat with Rex and LeFix **individually**. Confirm only the selected display draws, and its native gear readout agrees. Test a known external transmission controller and confirm ALLIN1 refuses gear hold.
5. Repeat on Legacy and Enhanced; inspect `ALLIN1_client.log` for provider/failure status and `ALLIN1_driving.jsonl` for measurements.
