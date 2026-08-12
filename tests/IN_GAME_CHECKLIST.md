# GTA runtime smoke checklist

Run this checklist on both Legacy and Enhanced after automated tests pass.

- Start Story Mode with BattlEye disabled; confirm no ScriptHook or SHVDN load errors.
- Open GBAY with F9 and navigate every vehicle, weapons, gear, and garage screen.
- Purchase, spawn, customize, store, retrieve, sell, and remove a vehicle.
- Try each story-owned personal vehicle at every ALLIN1 vehicle entrance:
  Franklin's Buffalo S and Bagger, Trevor's Bodhi, Michael's Tailgater and
  temporary Premier, plus Amanda's Sentinel, Tracey's Issi, and Jimmy's BeeJay
  XL. Confirm none can enter garage persistence or be sold through GBAY.
- Restart the game and confirm garage, balance, ownership, and configuration persistence.
- Drive through poor, middle, rich, highway, emergency, air, and water spawn regions.
- Hold the selector key in 2-, 4-, and 6-seat vehicles; verify selection, cancellation, and occupied seats. In Franklin's Buffalo S, verify front -1/0 and rear 1/2 switches shuffle internally, while front/rear row changes exit and re-enter normally.
- Equip and remove armor, Juggernaut, night vision, weapons, ammo, and throwables.
- Open Gear from the GBAY top menu, visit All/Protection/Equipment, verify all
  12 cards and previews are reachable, and purchase at least one item from each tab.
  Reopen the purchased item, confirm its card says **OWNED**, and verify selecting
  it again does not deduct money. Rapidly double-select one new item and confirm
  it is still charged only once. Repeat the duplicate check with a weapon.
- At Davis, verify the green vehicle marker at `204.0661, -1466.4750, 29.1437`
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
