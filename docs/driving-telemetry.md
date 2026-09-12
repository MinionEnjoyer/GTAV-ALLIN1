# Driving HUD, shifting and hitch telemetry

The built-in speedometer is a small non-interactive **React HUD rendered by
Reactor V**, not GBAY, LemonUI, or native text. It uses the passive-HUD contract,
separate from menu/input ownership, and shows speed, KMH/MPH, AUTO or MANUAL
(sequential hold), and native gear. Gear zero is `R`, never invented neutral;
unsupported readings are `?`.

It needs the coordinated Reactor V `PassiveHudContract` v1 build (Core, Script,
Runtime/Preloader, browser assets). Older Reactor still supports GBAY but cannot
draw this HUD: ALLIN1 logs `passive_hud_unavailable_update_reactor_v`, with no
native fallback or forced menu. Telemetry/shifting continue independently.
Candidates are built locally; installation and in-game validation remain separate.
Updates are capped at 10 Hz and stale data clears after one second. Menus supersede
the HUD; it never owns pointer/keyboard input. The dependency is a generic
speedometer prefab/protocol, not ALLIN1 content.

The built-in HUD hides for phone use/calls/in-vehicle camera and while the
character wheel is held (Alt by default or remapped/controller binding), including
an actual character switch. It returns when that state ends and normal driving
visibility permits it. These transitions log `hud_visibility` with `phone` or
`character_switch`; they do not alter saved provider/units, gear hold, or
telemetry. External mods manage their own displays.

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

This is **not** a manual-transmission simulation: no clutch, neutral, reverse
selector, torque model, or handling/gear-ratio edits. Return to automatic for
reverse. It only uses SHVDN CurrentGear/NextGear and verifies readback; each
edition still needs road testing.

Gear writes stop in safe/recovery mode; menus, pause, lost focus, missions,
cutscenes/loading, garage transitions, death, leaving the driver's seat, vehicle
changes, invalid gear/RPM, or a competing transmission module. They are limited
to cars/bikes and require explicit re-enable after suspension; held keys never
replay. No Online operation.

## External speedometers

`auto` chooses a loaded Rex FSS assembly, then LeFixSpeedo ASI, otherwise ALLIN1.
`rex`/`lefix` choose that provider but fall back to ALLIN1 if absent. `off` hides
the built-in HUD without disabling telemetry or shift controls; use it to ensure
ALLIN1 never draws beside an unrecognised external display.

This is **coexistence support**, not a private telemetry API. Both mods read game
state independently; detection means only that a module/assembly loaded, not that
its HUD draws. Nothing is downloaded, bundled, launched, or written to third-party
configuration.

- [Rex Forza Styled Speedometer documentation](https://rexmods-dev.github.io/rexmods/FSSDocs.html): install the correct edition separately; use its native GTA gear source with ALLIN1. Its Numpad 1–3 controls remain untouched. Units and assist settings stay in FSS. Disable overlapping car/manual-reverse controls before testing ALLIN1 gear hold.
- [LeFix Speedometer](https://www.gta5-mods.com/scripts/lefix-speedometer): install a version compatible with your game edition; configure its units/display in its own menu. [Maintainer's source](https://github.com/ikt32/gta5-speedometer) is separate; none of its GPL code is incorporated here.
- Loaded `Gears.asi`, `ManualTransmission.asi`, or `CustomGearRatios.asi` disable ALLIN1 gear writes. There is no call to undocumented shift functions. Other/renamed transmission controllers cannot be reliably identified: set `shift_controls_enabled = false` when using them. The display/telemetry remain usable.

External-mod coexistence and native gear-hold behaviour are **not yet game-verified** by automated tests.

## Test data

`scripts/ALLIN1_driving.jsonl` receives local JSONL events and samples at up to **5 Hz** while driving in free roam. Default `towing` records samples only with a currently observed native or ALLIN1 physical connection. `all` also records solo driving. `off` disables this log entirely. No upload or location tracking.

Each row has schema version, session ID, UTC timestamp, kind, and dropped-sample
count. Samples include game time; vehicle/model identity; speed and signed
longitudinal speed in m/s, speed-magnitude acceleration in m/s², and sample
interval; current/next/high/requested held gear; normalized
RPM (not engine RPM); steering, throttle/brake, roll/pitch, and collision. Frame
timing includes the **worst observed frame since the previous sample** to reveal
render/frame-delivery hitches.

The `joints` array records both front/rear connections: trailer identity/speed/roll/pitch/collision, attachment mode, known hitch ID, coupler gap in metres and wrapped relative yaw in degrees. Configured physical break force is metadata, **not measured joint force**. Missing bone/profile data is `null`, not zero. Native towing outside an authored profile may have unknown hitch/gap values.

Events include connection attempts/results, disconnects, failed actions,
observed/lost couplings, observation suspension, shifts, provider, and runtime
failures. `coupling_no_longer_observed` does **not** prove break-force failure:
despawning or another script can remove a connection. Leaving the seat or
suspending sampling emits `observation_ended` instead.

Native reads stay on the game thread. Detached rows enter a bounded 512-row queue
for one background writer; overflow drops samples rather than blocking gameplay.
Logs rotate at 8 MiB to `.1`, `.2`, `.3` (about 32 MiB total). Disk failure warns
and stops logging; shutdown drains at most 500 ms, so a crash/slow disk can lose
the last buffered rows. Acceleration is invalid across observation/vehicle changes
and long sample gaps.

## Next in-game validation

1. Native rear trailer: accelerate, brake, turn, reverse in automatic, disconnect. Confirm correct units, gears, gap/yaw data and disconnect events.
2. Experimental front joint: begin at walking pace in an open area, turn gently, then compare yaw/gap/roll with rear towing. Watch for jackknifing and collision instability; telemetry does not change joint physics.
3. Gear hold: test each shift, high-RPM downshift refusal, return to auto; then open GBAY, pause, change vehicles and verify it remains automatic until re-enabled.
4. Repeat with Rex and LeFix **individually**. Confirm only the selected display draws, and its native gear readout agrees. Test a known external transmission controller and confirm ALLIN1 refuses gear hold.
5. Repeat on Legacy and Enhanced; inspect `ALLIN1_client.log` for provider/failure status and `ALLIN1_driving.jsonl` for measurements.
