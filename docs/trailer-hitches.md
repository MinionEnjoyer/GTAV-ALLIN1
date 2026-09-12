# GBAY trailer hitches

Open GBAY > Vehicles > Trailer hitches from the driver's seat in Story Mode free
roam. The live list offers compatible nearby trailers for configured front/rear
slots. One connection per towing vehicle is supported; trailer chains are not.

Both vehicles must be stopped (at most 0.15 m/s), the trailer unoccupied, and the
selected hitch/coupler inside the profile distance. Already-connected vehicles,
missing bones, expired selections, and mission/online/loading states are rejected.
Connect/disconnect require confirmation and recheck live state at apply time. No
vehicle is spawned or position/teleport correction scripted.

SDK Vehicle Workbench profiles arrive through the receipt-authorized vehicle
catalog; there is no second in-game format or offset editor. Without a profile,
`attach_female` enables native detection for a bounded stock-trailer list; an
explicit empty profile disables that fallback. Detection does not guarantee an
engine-supported pair.

Native mode uses GTA towing. Custom/front physical joints are experimental,
preserve collisions, and use a joint rather than a per-frame attachment retry.
SDK previews are offset schematics, not physics/collision validation. Shutdown
releases only this system's physical joints; existing native towing remains.

## Acceptance checks before release

- Verify the SDK profile survives export, install, and runtime catalog loading.
- Native rear hitch: connect, turn, brake, reverse, and disconnect on both editions.
- Custom/front hitch: verify bone-local placement, orientation, collision,
  articulation and break behavior before describing it as supported.
- Confirm moving/occupied/connected trailers and stale confirmations are rejected.
- Switch vehicles and reload the script; verify no leftover experimental joints
  or unintended changes to native trailer connections.

The editor, export path, bridge UI and policy validation have automated tests.
Live GTA physics has not yet been validated for this implementation.
