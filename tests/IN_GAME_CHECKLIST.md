# GTA runtime smoke checklist

Run this checklist on both Legacy and Enhanced after automated tests pass.

- With GTA V closed, open the launcher's **Packages** workspace, import the
  standalone `realistic-suppressors/mod.toml`, and install it for the selected
  edition. Confirm the launcher reports **Suppressors Enhanced** as installed
  and enabled, and that it creates
  `scripts/RealisticSuppressors/RealisticSuppressors.dll` plus
  `scripts/RealisticSuppressors/allin1.content.json` without replacing
  `scripts/ALLIN1.dll` or another mod's files.
- Start Story Mode with BattlEye disabled; confirm no ScriptHook or SHVDN load
  errors and confirm the standalone log contains a fresh `configured` entry.
- Import the standalone GTA-V-FPV release's `mod.toml`, install it for the selected edition, and confirm its independent DLL and descriptor appear under `scripts/GTA-V-FPV` without changing `scripts/ALLIN1.dll`. Confirm its package-owned Flight, Controls, OSD, and Payload settings render in Content; then disable, re-enable, and uninstall it and verify only its receipt-owned files change.
- Open GBAY with F9 and navigate every vehicle, weapons, gear, and garage screen.
- Purchase, spawn, customize, store, retrieve, sell, and remove a vehicle.
- Try each story-owned personal vehicle at every ALLIN1 vehicle entrance:
  Franklin's Buffalo S and Bagger, Trevor's Bodhi, Michael's Tailgater and
  temporary Premier, plus Amanda's Sentinel, Tracey's Issi, and Jimmy's BeeJay
  XL. Confirm none can enter garage persistence or be sold through GBAY.
- During an active Story Mode mission, approach Eclipse Garage, Harmony Garage,
  Davis, the Garment Factory, Grapeseed, and Paleto Bay both on foot and in a mission vehicle
  with passengers. Confirm
  no entrance marker or interaction prompt appears and no fade, teleport, vehicle
  storage, passenger separation, or mission failure occurs. Garage exits must
  remain usable if a mission flag becomes active while already inside.
- With **Allow garage entry while wanted** disabled, gain one through five stars
  and approach every pedestrian and vehicle entrance. Confirm each shows the
  wanted-level denial and cannot start a transition. Lose the wanted level and
  confirm entry immediately returns. Enable the launcher override and confirm
  wanted entry works, while mission, protected-story-vehicle, and size rules are
  still enforced. Garage exits must remain usable in either setting.
- Enter and leave the DLC-backed garages (Harmony, Davis, and the Garment Factory),
  then visit Michael's house and Floyd's apartment. Confirm Story Mode bedroom
  beds, sofas, and other furniture still render, and confirm the log records
  `multiplayer_map_acquired` followed by `story_map_restored` for each visit.
- Restart the game and confirm garage, balance, ownership, and configuration persistence.
- Drive through poor, middle, rich, highway, emergency, air, and water spawn regions.
- Watch off-screen DLC traffic replacements enter view. Cars whose source had a
  driver must retain a driver and resume ambient driving even when replaced at a
  red light or in stopped traffic. Bump several managed vehicles and confirm
  collision and physics are active; no road vehicle may remain frozen or lose
  its occupants during replacement. Parked source vehicles may remain parked.
- Park a vehicle in each Story Mode safehouse garage and leave another ordinary
  parked vehicle on a nearby public road. Confirm the safehouse vehicle, current
  vehicle, last-used vehicle, and recently exited vehicle are never selected for
  replacement while the unrelated public-road vehicle remains eligible.
- Hold the selector key in 2-, 4-, and 6-seat vehicles; verify selection, cancellation, and occupied seats. In Franklin's Buffalo S, verify front -1/0 and rear 1/2 switches shuffle internally, while front/rear row changes exit and re-enter normally.
- For every switch that requires an exit, park first in open space and then with
  the intended walk-around side against a wall or another vehicle. In open space,
  the selector must trace the route before opening the door and complete it. When
  all candidate routes are obstructed, the player must remain in the original
  seat and see the blocked-route message; no exit or teleport may occur.
- In the Benefactor Turreted Limo, confirm seat index 3 is labeled **Turret**
  rather than **Extra 1**. Switch from the driver and both rear seats to the
  turret, and back again. Every route must finish its exit animation before
  walking to and mounting the target position; no transition may teleport.
- In the weaponized Vapid Caracara, confirm **Extra 1** is labeled **Turret**.
  Switch from the cab to the turret and verify the character exits fully, walks
  to the nearest rear climb point, and uses the truck's native mounting
  animation. Repeat from outside on both sides and behind the truck; no route
  may teleport or stall at the front door. Block a rear approach point with the
  truck against a wall or solid prop and repeat: the selector must report no
  valid path and return the player to the seat occupied before the attempt. If
  GTA redirects an entry toward the cab, the selector must cancel it before
  entry or exit the wrong seat normally, then restore the previous seat without
  teleporting.
- Equip and remove armor, Juggernaut, night vision, weapons, ammo, and throwables.
- Buy Sticky Bombs from GBAY and confirm the card shows `25 x $600 = $15,000`,
  the player receives 25, and exactly $15,000 is deducted. Spend five, refill
  them, and confirm the refill costs `5 x $600 = $3,000`. Repeat with the
  five-item Proximity Mine bundle and verify its quantity and total.
- Purchase an Online-only weapon from GBAY without opening the desktop character
  editor. Fire a measurable number of rounds, make a normal GTA save, quit, and
  reload as the same protagonist; confirm the weapon and its remaining ammunition
  return while unrelated story weapons remain.
  Repeat after death/save reload, then switch protagonists twice and confirm the
  weapon is restored only for its purchasing character.
- Open Customize Weapons and verify the active attachment or finish has a green
  **EQUIPPED** badge and green row accent, purchased alternatives show **OWNED**,
  and a fully stocked ammunition row shows **FULL** rather than **EQUIPPED**.
- In **Content**, select the separately installed **Suppressors Enhanced**
  package and enable **Realistic suppressor stealth**. Do not enable it through
  ALLIN1 Online Content; the mod owns its own settings namespace.
  With no wanted level and outside a mission, fire one suppressed pistol shot in
  an isolated outdoor location with no NPC looking toward the player; confirm no
  wanted level or distant crowd panic appears. Repeat with the suppressor removed
  and confirm the ordinary report remains. Equip a Mk II muzzle brake and confirm
  it behaves as unsuppressed. Then repeat suppressed fire beside an NPC, in the
  NPC's clear view, indoors, and with the bullet striking near an NPC; each must
  remain detectable. Fire a sustained suppressed burst and confirm its effective
  hearing radius expands rather than granting silent automatic fire. Start a
  mission and separately gain a wanted level; confirm the mod does not suppress or
  unwind either authored response. Review sampled `shot_evaluated` records in
  `%LOCALAPPDATA%\RealisticSuppressors\RealisticSuppressors.log`, including
  `witness_reason` and `crime_suppressed`.
- Enable **Suppressor wear and breakage** and **Suppressor heat smoke**, set
  **Suppressor durability multiplier** to 0.5× and **Heat smoke intensity** to
  1.0×, enable **Temperature debug**, and purchase fresh
  suppressors for a Pistol and Heavy
  Sniper Mk II. Confirm detailed logs identify different thermal profiles and
  per-shot heat rates. Sustain fire with the Heavy Sniper Mk II; from a cold
  start, physical glow begins on the 34th uninterrupted round. Confirm the first
  visible heat is a faint red-orange band at the can's center, not a uniformly
  orange tube. The band should casually diffuse toward the ends as temperature
  rises: low opacity below 38% of the glow-to-critical range, broader shoulders
  above 60%, most of the sleeve visible above 80%, and full opacity only in the
  final 4% before critical. In particular, short rifle cans around 613–631 °C
  must still retain dark ends and a clear center-to-end gradient. Test fast
  pans, strafing, sprinting, jumping, recoil, hip fire, ADS transitions, and
  reloads in first and third person; the sleeve must remain attached and the
  receiver, optic, sight picture, and hands must never inherit the heat color.
  Above the profile's damage-onset temperature, confirm a faint gray plume
  follows the suppressor instead of remaining at an old world position. Near
  critical heat, especially the final 18% of the damage-onset-to-critical range,
  it should escalate into a dramatically denser and longer two-emitter trail
  without covering the receiver or hands. Holster, swap weapons, switch
  protagonists, pause, and let the can cool below onset; each must stop the
  emitter cleanly. Set **Heat smoke intensity** to 0.5× and 2.0× across script
  reloads and confirm plume strength changes without altering the temperature
  readout, condition loss, or failure point. Disable **Suppressor heat smoke**
  and confirm glow and thermal simulation remain active without smoke.
  Confirm `glow_started` names the `bone_attached_emissive_overlay` renderer;
  pause and confirm logged temperature falls
  before firing again. Confirm a small lower-right `SUPPRESSOR <n> °C` HUD
  readout rises during fire and falls while cooling, and that no suppressor
  heat, critical, failure, activation, or recovery notification appears in
  GTA's feed. Continue the abusive firing cycle
  until failure. Confirm exactly one small spark burst and metallic pop occur
  at the suppressor front cap, with no explosion, damage, prop movement,
  wanted-level change, scorch decal, fire, or camera shake. Leave the failed
  weapon equipped through several removal retries and confirm the effect does
  not repeat. Confirm the component is physically removed, subsequent fire
  is unsuppressed, `break_effect_emitted` and `component_broken` are logged,
  and the suppressor no
  longer has an **OWNED** price bypass in GBAY. Replace one failed suppressor
  through vanilla Ammu-Nation and another through GBAY. In each storefront,
  preview the failed suppressor and back out once before buying it; confirm a
  preview alone does not restore condition. Then complete each purchase and
  confirm both attach at full condition and produce a
  `replacement_registered` log. Reload the same
  character and switch protagonists to confirm remaining condition stays with
  the correct character and weapon.
- Disable **Suppressor wear and breakage**, reload scripts, and repeat sustained
  fire with a fresh suppressor. Confirm heating, cooling, and glow still occur
  but `durability` does not fall and the component never breaks.
  Restore the durability multiplier to 1.0× and disable **Temperature debug**
  after testing.
- With GTA V closed, disable the **Suppressors Enhanced** package in the
  launcher, start Story Mode, and confirm its stealth/thermal behavior is absent
  while ALLIN1 and unrelated mods still load. Re-enable it and confirm the
  behavior returns. Then uninstall it from **Packages** and verify its DLL,
  descriptor, receipt, and registry entry are removed while `scripts/ALLIN1.dll`
  and unrelated mod files remain byte-for-byte unchanged. Confirm
  `%LOCALAPPDATA%\RealisticSuppressors\condition.json` remains, reinstall the
  package through the launcher, and verify the correct protagonist/weapon
  condition resumes on GTA V Enhanced.
- Open Gear from the GBAY top menu, visit All/Protection/Equipment, verify all
  12 cards and previews are reachable, and purchase at least one item from each tab.
  Confirm equipped cards say **EQUIPPED**. Press Y and separately click the
  **UNEQUIP** badge; confirm armor, Juggernaut, parachute, and night vision are
  physically removed and their cards return to a purchase price. Confirm each
  item must be repurchased before it can be equipped again. Confirm equipping one
  armor consumes the previously active armor, which must likewise be repurchased.
  Rapidly double-select one new item and confirm it is still charged only once.
  Repeat the duplicate check with a weapon.
- At Eclipse Garage, Harmony Garage, Davis, the Garment Factory, Grapeseed, and Paleto Bay, switch among Michael,
  Franklin, and Trevor. Verify every vehicle/pedestrian map blip and every visible
  world marker changes to blue, green, and orange respectively without a reload.
- At Davis, verify the vehicle marker at `204.0661, -1466.4750, 29.1437`
  and pedestrian marker at `215.0502, -1461.0250, 29.1847` appear on the map/world.
- Enter the Davis garage on foot and in a non-personal vehicle. Confirm the Auto
  Shop loads, all ten parking spaces are usable, the driven-in vehicle is stored,
  and the pedestrian exit appears at `-1357.6240, 153.2929, -99.1942` before
  pedestrian/vehicle exits return to their respective Davis exterior doors.
- At the Garment Factory, verify the vehicle marker at
  `762.1525, -899.2333, 25.1761` and pedestrian marker at
  `760.7663, -909.4583, 25.2538`, both heading 270. Enter on foot and in a
  vehicle, confirm all ten native bays are used and standard cars sit 0.8 m
  deeper than large vehicles. Confirm the pedestrian exit is centered at
  `751.0350, -975.4493, -67.5536` at heading 180, then verify both exit paths
  return to La Mesa.
- At Grapeseed, verify the vehicle marker at
  `2551.4610, 4674.3250, 33.9819`, heading 0, and pedestrian marker at
  `2553.4590, 4650.6360, 34.0768`, heading 90. Enter on foot and in a standard
  vehicle, confirm all six spaces are usable, and verify GBAY delivery, sale,
  recovery, character-colored blips, and independent persistence.
- At Paleto Bay, verify the vehicle marker at
  `-221.9008, 6252.8020, 31.4894`, heading 45, and pedestrian marker at
  `-224.5180, 6244.2620, 31.4926`, heading 45. Enter on foot and in a standard
  vehicle, confirm the `vw_casino_garage` shell loads, all ten native bays are
  usable, the pedestrian exits are centered at
  `1295.3110, 221.1703, -49.0574` heading `0` and
  `1295.3350, 260.7359, -49.0574` heading `180`, and pedestrian/vehicle exits
  return to their separate exterior anchors.
- Purchase the Galaxy Super Yacht, then buy a Swift Deluxe and choose **Yacht
  Helipad** as its destination. Verify it appears centered on the surveyed pad
  at `-2043.9200, -1031.4230, 11.9807`, heading `255.76`, can be flown away,
  and does not duplicate when crossing the yacht streaming boundary. Repeat
  with the SuperVolito Carbon. Confirm every other aircraft shows **YACHT HELIS
  ONLY**, and that an unowned yacht shows **YACHT REQUIRED**.
- Fly toward and away from the yacht across the 900/1200 m streaming radii.
  Confirm there is no loading screen and Story Mode bedroom/furniture assets
  remain intact; the yacht IPL must stream without ON_ENTER_MP/ON_ENTER_SP.
- On a clean install, confirm `scripts/ALLIN1_vehicle_grounding.json` contains
  the completed 827-model catalog and garages place a low sports car, an SUV,
  and a motorcycle on their tires without hovering or clipping. Confirm F10
  remains the World Vector toggle and F11 has no ALLIN1 runtime binding.
- In My Garage, switch among Eclipse Garage, Harmony Garage, Davis Auto Shop,
  Garment Factory, Grapeseed Garage, and Paleto Bay Garage. Deliver a standard vehicle to the Garment Factory,
  sell it, restart, and confirm its save remains independent. Then switch among
  all six locations and confirm each list and capacity is correct.
  Deliver a standard vehicle to Davis Auto
  Shop. Deliver a standard vehicle to Davis, sell it, restart, and confirm Davis
  storage remains independent. Confirm the purchase dialog lists every garage
  with live capacity, rejects incompatible destinations, and permits oversized
  vehicles only when Harmony is explicitly selected.
- Store and sell a valid base-game vehicle that is not in the GBAY catalog (the
  Huntley in the current Davis save is suitable). Confirm it shows a dollar sale
  value instead of **Remove** or **This vehicle cannot be sold**.
- Store a base-game Furore GT in Eclipse Garage. Confirm it is not incorrectly
  rejected as oversized, the outside car is deleted only after the save succeeds,
  it respawns as **Furore GT**, and its garage action is **Sell** rather than
  **Protected**. Restart once and confirm the same entry still respawns.
- Open **Customize Auto Shop** for Davis. Cycle every style, tint, lift,
  quarters, work-area, and storage option; confirm changes apply live when
  inside, remain isolated per protagonist, and persist after a script/game restart.
- In My Garage, confirm Eclipse Garage reports **Fixed Interior** and does not
  open the unrelated Nightclub Warehouse customization screen.
- Enter Harmony and use the elevator to visit all five virtual floors. Confirm
  exactly one garage-level shell is visible, security/equipment/workstations/
  stocked detail are present without an upgrade menu, and no entity sets flicker
  or overlap. Confirm slot labels run F1-1 through F5-5.
- Place short, long, wide, and offset-origin vehicles in Eclipse, Harmony,
  Davis, the Garment Factory, Grapeseed, and Paleto Bay. Confirm each body—not
  merely its model origin—is centered over its native bay and the lowest model
  bound meets the raycast/configured floor. Wheels must remain on the floor,
  adjacent vehicles must not overlap, and the log must identify the Z source as
  `raycast`, `configured`, or the safe `native-root` fallback.
- Confirm preview textures load and no placeholder remains for catalogued vehicles.
- Press F10 and confirm the world-vector overlay toggles directly, with no
  retired capture menu or screenshot actions. Confirm X/Y/Z and heading update
  while walking or driving.
- Allow ALLIN1 traffic to populate, then begin a Story Mode mission. Confirm no
  newly spawned or replacement traffic appears during the mission and no
  previously managed vehicle continues driving without a visible driver.
- With **Enhanced Police AI** enabled, confirm a firing line is never logged as
  established without its required majority. Move more than 28 metres and wait
  through a full line cycle; the element should re-form instead of rushing one
  at a time. Compare visible cover use with
  `police_firing_line_cover_acquired`, `cover_failed`, and
  `police_firing_line_reforming` events.
- At two or more wanted stars, let a healthy police car with at least three
  officers approach from beyond 30 metres. Confirm it stages ahead, stops
  broadside, dismounts together, and produces
  `police_vehicle_containment_staged`, `dismount_ordered`, and
  `containment_line_forming` before the officers establish a firing line.
- Shoot an ambient officer in either hand. Confirm the held weapon drops, the
  injured arm reaches instead of continuing to point the gun, and any recovery
  waits until the officer is outside the player's line of fire. Place a better
  pistol, shotgun, SMG, PDW, or carbine pickup nearby and confirm it can be
  selected; explosives and heavy weapons must be ignored.
- Down a living officer near an established firing line. Confirm stabilization
  routes the casualty and rescuer behind the line. Once the casualty reaches the
  collection zone, confirm a new script-owned Police Maverick logs
  `dedicated_casevac_spawned`, approaches the rear landing point, lands, and
  boards the casualty. Its pilot must not attack the player and ambient recon
  helicopters must remain on their existing assignments.
- Stage two or more stabilized officers at the same collection zone. Confirm
  one dedicated CASEVAC helicopter loads every casualty for which it has a free
  passenger seat, logging `dedicated_casevac_batch_assigned` between boardings.
  It must then log `dedicated_casevac_departing`, fly away from the engagement,
  and log `dedicated_casevac_despawned` only after reaching the fly-out distance
  (or the bounded cleanup timeout). It must not depart after only the first
  passenger when another eligible casualty is waiting at that zone.
- While a casualty waits at the collection zone, record their health and leave
  them untouched long enough for any native bleed/recovery behavior to run.
  Confirm the value remains pinned. Then shoot the casualty once and confirm
  the lower value becomes the new pinned baseline; additional damage must still
  be able to kill them. Correlate this with
  `casualty_stabilized_health_held` and the three stabilization heartbeat
  counters.
- In GBAY's Throwables category, buy each five-pack of **White/Red/Orange/
  Yellow/Green/Blue/Purple Smoke Grenades**. Confirm each card shows independent
  stock and its color badge, with no **LOADED** state. Confirm each stocked
  color appears as its own normally selectable
  throwable with a `(Color) Smoke` weapon-wheel label, the BZ Gas canister
  icon, its own ammo count, and a maximum stock of five.
  Reload must retain its normal GTA function and ALLIN1 must not draw any
  replacement panel over the native weapon wheel. Throw one and confirm exactly
  one unit is removed from only that colour. After deployment, listen for and
  confirm the settled canister's rolling sound does not persist. Reload
  the game without saving and confirm the purchase/consumption is discarded;
  repeat and make a Story Mode save to confirm it persists.
- Trigger player, casualty-extraction, and withdrawal smoke. First run
  `verify-smoke-tuning` and confirm both audited RPF entries and the marker pass.
  Confirm the physical canister remains on the ground until its native fuse
  finishes rather than being deleted by the fallback. No trail, primed cloud,
  native plume, or scripted field may appear while the canister is airborne or
  bouncing. After at least 300 ms of grounded stability, the custom canister
  must produce one consistently coloured field at its final position for
  roughly 40 seconds. It must not display residual white/green smoke, inherit
  the color of another active grenade, shake the camera, knock entities down,
  or add damage. Casualty extraction must
  always use orange, while ordinary police withdrawal smoke remains white.
  Confirm the log sequence
  contains `enhanced_smoke_projectile_tracked`,
  sampled `enhanced_smoke_projectile_motion`,
  `enhanced_smoke_projectile_settled` with `is_in_air=false`,
  `has_collided=true`, `stationary_ms>=300`, and low speed/displacement,
  `enhanced_smoke_projectile_consumed`,
  `enhanced_smoke_field_started`, `enhanced_smoke_loop_started` with
  `single_color_backend=true` for non-white colors, and
  `enhanced_smoke_supplemental_pulse` with a
  positive `effects_emitted` count. The heartbeat must report both
  `particle_asset_ready` and `supplemental_particle_asset_ready`; neither pulse
  counter should grow after its field completes,
  and `enhanced_smoke_field_completed`. Then throw native **Tear Gas** and
  confirm it retains its original gas behavior without the ALLIN1 smoke field;
  its `EXP_TAG_BZGAS` record and `EXP_VFXTAG_BZGAS` row must remain stock.
- Trigger an ambient police hot-rope deployment near an established firing
  line. Confirm the aircraft does not hover over the player or continuously
  reset its flight task. It must approach a logged
  `aerial_safe_rappel_planned` rooftop when one is navigable, otherwise use the
  screened ground point behind the line; release only from a stable hover; and
  log `aerial_safe_rappel_completed`. Confirm it is not borrowed for CASEVAC;
  the casualty should wait for the dedicated evacuation aircraft instead.
- Repeat without an established firing line. Confirm an intercepted airborne
  exit logs `aerial_rappel_request_inferred_from_exit`, the officer is reseated,
  and throttled `aerial_safe_rappel_deferred` events report
  `no_established_firing_line`. If a recon leg cannot close on its waypoint for
  18 seconds, confirm one `aerial_recon_leg_stalled` event appears and orbit
  commands stop until unsafe-perimeter egress is needed.
- In the SMG Mk II customizer, equip each special-ammo magazine, refill it, move
  to another option, and reopen the workbench. The purchased ammo must remain
  at the component's capacity and a second refill must report fully stocked
  rather than charging for the same rounds again.
- In the Vapid Caracara selector, confirm only Driver, Passenger, and Bed Turret
  are shown. From Driver, press Down once and confirm selection skips the hidden
  rear-seat row and lands on Bed Turret; release the selector key and confirm the
  native external climb mounts the gun. From Bed Turret, press Up once and
  confirm Driver is reachable again.
- Open GBAY and confirm PHAT loads on the loading screen from its own texture
  dictionary. Open About and confirm the independent ALLIN1 logo is contain-fit,
  crisp, and undistorted above the page content.
- Switch protagonists, die, reload a save, enter interiors, and reload scripts.
- Uninstall and confirm Story Mode starts cleanly with original command-line flags retained.
- Inspect `scripts/ALLIN1*.log` and ScriptHookVDotNet logs for errors or runaway loops.
