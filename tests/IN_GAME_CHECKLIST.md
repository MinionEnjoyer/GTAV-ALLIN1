# GTA runtime smoke checklist

Run this checklist on both Legacy and Enhanced after automated tests pass.

- Start Story Mode with BattlEye disabled; confirm no ScriptHook or SHVDN load errors.
- Open GBAY with F9 and navigate every vehicle, weapons, gear, and garage screen.
- Purchase, spawn, customize, store, retrieve, sell, and remove a vehicle.
- Try each story-owned personal vehicle at every ALLIN1 vehicle entrance:
  Franklin's Buffalo S and Bagger, Trevor's Bodhi, Michael's Tailgater and
  temporary Premier, plus Amanda's Sentinel, Tracey's Issi, and Jimmy's BeeJay
  XL. Confirm none can enter garage persistence or be sold through GBAY.
- During an active Story Mode mission, approach Eclipse Towers, the three-floor
  garage, and Davis both on foot and in a mission vehicle with passengers. Confirm
  no entrance marker or interaction prompt appears and no fade, teleport, vehicle
  storage, passenger separation, or mission failure occurs. Garage exits must
  remain usable if a mission flag becomes active while already inside.
- Enter and leave both DLC-backed garages (Davis and the three-floor garage),
  then visit Michael's house and Floyd's apartment. Confirm Story Mode bedroom
  beds, sofas, and other furniture still render, and confirm the log records
  `multiplayer_map_acquired` followed by `story_map_restored` for each visit.
- Restart the game and confirm garage, balance, ownership, and configuration persistence.
- Drive through poor, middle, rich, highway, emergency, air, and water spawn regions.
- Hold the selector key in 2-, 4-, and 6-seat vehicles; verify selection, cancellation, and occupied seats. In Franklin's Buffalo S, verify front -1/0 and rear 1/2 switches shuffle internally, while front/rear row changes exit and re-enter normally.
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
  valid path and leave the player on foot. If GTA redirects an entry toward the
  cab, the selector must cancel it before entry or exit the wrong seat normally.
- Equip and remove armor, Juggernaut, night vision, weapons, ammo, and throwables.
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
  physically removed while their cards remain **OWNED**. Select each owned card
  again, confirm it re-equips without deducting money, and confirm equipping one
  armor removes the previously active armor. Rapidly double-select one new item
  and confirm it is still charged only once. Repeat the duplicate check with a weapon.
- At Eclipse Towers, the three-floor garage, and Davis, switch among Michael,
  Franklin, and Trevor. Verify every vehicle/pedestrian map blip and every visible
  world marker changes to blue, green, and orange respectively without a reload.
- At Davis, verify the vehicle marker at `204.0661, -1466.4750, 29.1437`
  and pedestrian marker at `215.0502, -1461.0250, 29.1847` appear on the map/world.
- Enter the Davis garage on foot and in a non-personal vehicle. Confirm the Auto
  Shop loads, all ten parking spaces are usable, the driven-in vehicle is stored,
  and the pedestrian exit appears at `-1357.6240, 153.2929, -99.1942` before
  pedestrian/vehicle exits return to their respective Davis exterior doors.
- In My Garage, switch among Eclipse Towers, Three-Floor Garage, and Davis Auto
  Shop. Deliver a standard vehicle to Davis, sell it, restart, and confirm Davis
  storage remains independent. Confirm oversized vehicles still route to the
  three-floor garage and cannot be delivered to Davis.
- Store and sell a valid base-game vehicle that is not in the GBAY catalog (the
  Huntley in the current Davis save is suitable). Confirm it shows a dollar sale
  value instead of **Remove** or **This vehicle cannot be sold**.
- Store a base-game Furore GT in Eclipse Towers. Confirm it is not incorrectly
  rejected as oversized, the outside car is deleted only after the save succeeds,
  it respawns as **Furore GT**, and its garage action is **Sell** rather than
  **Protected**. Restart once and confirm the same entry still respawns.
- Open **Customize Auto Shop** for Davis. Cycle every style, tint, lift,
  quarters, work-area, and storage option; confirm changes apply live when
  inside, remain isolated per protagonist, and persist after a script/game restart.
- In My Garage, confirm Eclipse Towers reports **Fixed Interior** and does not
  open the unrelated Nightclub Warehouse customization screen.
- Open **Customize Three Floors** and test every option on all three virtual
  floors. Confirm only one garage-level shell and one choice per category is
  visible, changes do not flicker or overlap, and each floor/character retains
  its choices after exiting and restarting. Confirm slot labels run F1-1 through
  F1-5, F2-1 through F2-5, and F3-1 through F3-5.
- Place short, long, wide, and offset-origin vehicles in Eclipse and the
  three-floor garage. Confirm each body—not merely its model origin—is centered
  over its bay, wheels remain on the floor, and adjacent vehicles do not overlap.
- Confirm preview textures load and no placeholder remains for catalogued vehicles.
- Press F10 and confirm the world-vector overlay toggles directly, with no
  retired capture menu or screenshot actions. Confirm X/Y/Z and heading update
  while walking or driving.
- Open GBAY and confirm PHAT loads on the loading screen from its own texture
  dictionary. Open About and confirm the independent ALLIN1 logo is contain-fit,
  crisp, and undistorted above the page content.
- Switch protagonists, die, reload a save, enter interiors, and reload scripts.
- Uninstall and confirm Story Mode starts cleanly with original command-line flags retained.
- Inspect `scripts/ALLIN1*.log` and ScriptHookVDotNet logs for errors or runaway loops.
