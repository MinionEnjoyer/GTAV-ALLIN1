# GBAY trailer hitches

Open GBAY > Vehicles > Trailer hitches while in the driver's seat in Story Mode
free roam. The list updates automatically and offers compatible nearby trailers
for the current vehicle's configured front/rear slots. Only one live connection
per towing vehicle is supported; trailer chains are not supported.

Both vehicles must be stopped (at most 0.15 m/s), the trailer must be unoccupied,
and the selected hitch/coupler must be within the profile's coupling distance.
Already-connected vehicles, missing bones, expired selections and mission/
online/loading states are rejected. Connections and disconnections require
confirmation and repeat the live checks when applied, not just when listed.
No vehicle is spawned and no scripted position/teleport correction is used.

SDK Vehicle Workbench hitch profiles arrive through the receipt-authorized
vehicle catalog. There is no second in-game profile format or offset editor.
Without a profile, an existing `attach_female` bone enables native detection
with a bounded list of stock trailer models. An explicit empty profile disables
this fallback. Detection does not guarantee the engine supports every pair.

Native mode uses GTA's authored towing system. Custom/front physical joints are
experimental and explicitly labeled. They preserve collisions and use a joint
instead of a per-frame attachment retry loop. SDK previews are offset schematics,
not collision or physics validation. Script shutdown releases only physical
joints created by this system; existing native towing connections are left alone.

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
