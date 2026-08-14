# GTA runtime smoke checklist

Run this checklist on both Legacy and Enhanced after automated tests pass.

- Start Story Mode with BattlEye disabled; confirm no ScriptHook or SHVDN load errors.
- Open GBAY with F9 and navigate every vehicle, weapons, gear, and garage screen.
- Purchase, spawn, customize, store, retrieve, sell, and remove a vehicle.
- Try each story-owned personal vehicle at every ALLIN1 vehicle entrance:
  Franklin's Buffalo S and Bagger, Trevor's Bodhi, Michael's Tailgater and
  temporary Premier, plus Amanda's Sentinel, Tracey's Issi, and Jimmy's BeeJay
  XL. Confirm none can enter garage persistence or be sold through GBAY.
- During an active Story Mode mission, approach Eclipse Garage, Harmony Garage,
  Davis, the Garment Factory, and Grapeseed both on foot and in a mission vehicle
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
- Open Gear from the GBAY top menu, visit All/Protection/Equipment, verify all
  12 cards and previews are reachable, and purchase at least one item from each tab.
  Confirm equipped cards say **EQUIPPED**. Press Y and separately click the
  **UNEQUIP** badge; confirm armor, Juggernaut, parachute, and night vision are
  physically removed and their cards return to a purchase price. Confirm each
  item must be repurchased before it can be equipped again. Confirm equipping one
  armor consumes the previously active armor, which must likewise be repurchased.
  Rapidly double-select one new item and confirm it is still charged only once.
  Repeat the duplicate check with a weapon.
- At Eclipse Garage, Harmony Garage, Davis, the Garment Factory, and Grapeseed, switch among Michael,
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
- On a clean install, confirm `scripts/ALLIN1_vehicle_grounding.json` contains
  the completed 827-model catalog and garages place a low sports car, an SUV,
  and a motorcycle on their tires without hovering or clipping. Confirm F11 no
  longer opens a developer tool and F10 remains the World Vector toggle.
- In My Garage, switch among Eclipse Garage, Harmony Garage, Davis Auto Shop,
  Garment Factory, and Grapeseed Garage. Deliver a standard vehicle to the Garment Factory,
  sell it, restart, and confirm its save remains independent. Then switch among
  all five locations and confirm each list and capacity is correct.
  Deliver a standard vehicle to Davis Auto
  Shop. Deliver a standard vehicle to Davis, sell it, restart, and confirm Davis
  storage remains independent. Confirm oversized vehicles still route to the
  Harmony Garage and cannot be delivered to Davis or Grapeseed.
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
- Open **Customize Harmony Garage** and test every option on all three virtual
  floors. Confirm only one garage-level shell and one choice per category is
  visible, changes do not flicker or overlap, and each floor/character retains
  its choices after exiting and restarting. Confirm slot labels run F1-1 through
  F1-5, F2-1 through F2-5, and F3-1 through F3-5.
- Place short, long, wide, and offset-origin vehicles in Eclipse, Harmony,
  Davis, the Garment Factory, and Grapeseed. Confirm each body—not
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
