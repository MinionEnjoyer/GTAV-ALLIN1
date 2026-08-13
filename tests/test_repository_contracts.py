"""Whole-repository contracts connecting data, generated code, and releases."""

import json
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path

from allin1.config import load_prices
from allin1.vehicles.database import VehicleDatabase

ROOT = Path(__file__).resolve().parents[1]


def test_vehicle_models_are_unique_and_well_formed():
    db = VehicleDatabase.load(ROOT / "data/vehicles.toml")
    models = [vehicle.model for vehicle in db]
    assert len(models) == len(set(models))
    assert all(model == model.lower() and model.strip() == model for model in models)
    assert all(vehicle.name and vehicle.manufacturer and vehicle.vehicle_class for vehicle in db)


def test_every_vehicle_price_and_catalog_entry_refers_to_a_model():
    db = VehicleDatabase.load(ROOT / "data/vehicles.toml")
    models = {vehicle.model for vehicle in db}
    prices = load_prices(ROOT / "prices_vehicles.toml")
    assert set(prices) <= models
    catalog = json.loads((ROOT / "catalog/vehicles.json").read_text())
    assert {item["model"] for item in catalog} == models


def test_vehicle_previews_cover_database():
    models = {vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")}
    previews = {path.stem for path in (ROOT / "script/dist/previews").glob("*.png")}
    pending = set(tomllib.loads((ROOT / "data/preview_pending.toml").read_text())["models"])
    assert models - previews == pending
    assert pending <= models


def test_generated_csharp_contains_every_data_model():
    source = (ROOT / "script/src/VehicleList.cs").read_text()
    for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml"):
        assert f'"{vehicle.model}"' in source


def test_production_project_includes_only_supported_capture_tool():
    project = (ROOT / "script/ALLIN1.csproj").read_text()
    assert '<Compile Remove="tools\\**" />' in project
    assert '<Compile Include="tools\\WorldVectorTool.cs" />' in project
    assert project.count('<Compile Include="tools\\') == 1


def test_prebuilt_runtime_artifacts_are_present_and_nonempty():
    for relative in ("script/dist/ALLIN1.dll", "script/dist/LemonUI.SHVDN3.dll"):
        artifact = ROOT / relative
        assert artifact.stat().st_size > 1024


def test_retired_native_asi_is_not_shipped_or_built():
    assert not (ROOT / "asi").exists()
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "asi-build" not in workflow
    assert "cmake -S asi" not in workflow


def test_production_csharp_tests_run_in_ci():
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    command = "dotnet test script/tests/ALLIN1.Tests.csproj -c Release --no-restore"
    assert workflow.count(command) >= 2
    assert (ROOT / "script/tests/GarageSaveCodecTests.cs").is_file()
    assert (ROOT / "script/tests/AmmoRefillPolicyTests.cs").is_file()
    reliability = (ROOT / "src/allin1/reliability.py").read_text(encoding="utf-8")
    assert "class GarageState" not in reliability
    assert "class SeatState" not in reliability


def test_required_user_entrypoints_exist():
    for relative in ("install.bat", "uninstall.bat", "manager.bat", "install.sh", "uninstall.sh"):
        assert (ROOT / relative).is_file()


def test_garage_transitions_are_guarded_and_recoverable():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    for operation in ("EnterGarage", "LeaveGarage", "EnterFloorGarage", "LeaveFloorGarage"):
        assert f'BeginTransition("{operation}")' in garage
        assert f"{operation}Core();" in garage
        assert f'EndTransition("{operation}")' in garage
    assert "RecoverTransition(" in garage
    assert "if (_transitionInProgress)" in garage
    assert "GarageManager.IsTransitionInProgress" in shop


def test_drive_in_vehicle_is_deleted_after_player_extraction():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    for core_name in ("EnterGarageCore", "EnterFloorGarageCore"):
        start = garage.index(f"private static void {core_name}")
        section = garage[start: garage.index("private static void", start + 30)]
        save_guard = "if (!Save())" if core_name == "EnterGarageCore" else "if (!FloorGarageSave())"
        assert section.index(save_guard) < section.index("rideInToDelete = rideIn")
        assert section.index("CLEAR_PED_TASKS_IMMEDIATELY") < section.index("rideInToDelete.Delete()")


def test_garage_persistence_uses_atomic_backup_replacement():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    assert "private static void AtomicWriteText" in garage
    assert "File.Replace(tmp, path, backup, true)" in garage
    assert 'SAVE_PATH + ".bak"' in garage


def test_content_audit_models_are_in_catalog():
    models = {vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")}
    audited = {
        "cargobob5", "duster2", "maverick2", "poldominator10", "poldorado",
        "polgreenwood", "polimpaler5", "polimpaler6", "titan2", "vivanite2", "youga5",
        "caracara3", "cartuccia", "estride", "laufer", "lrcgt", "merula",
        "polignus", "veleno",
    }
    assert audited <= models


def test_current_online_weapons_are_generated_and_safely_granted():
    weapons = tomllib.loads((ROOT / "data/weapons.toml").read_text())["weapons"]
    names = {weapon["name"] for weapon in weapons}
    expected = {
        "WEAPON_PISTOLXM3", "WEAPON_STUNGUN_MP", "WEAPON_TECPISTOL",
        "WEAPON_BATTLERIFLE", "WEAPON_STRICKLER", "WEAPON_RAILGUNXM3",
        "WEAPON_SNOWLAUNCHER", "WEAPON_CANDYCANE", "WEAPON_STUNROD",
        "WEAPON_NEWSPAPER",
    }
    assert expected <= names
    generated = (ROOT / "script/src/WeaponList.cs").read_text()
    assert all(name in generated for name in expected)
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "IS_WEAPON_VALID" in shop
    assert "HAS_PED_GOT_WEAPON" in shop


def test_world_vector_and_seat_selector_contracts():
    installer = (ROOT / "src/allin1/installer.py").read_text()
    vector = (ROOT / "script/tools/WorldVectorTool.cs").read_text()
    seat = (ROOT / "script/src/SeatSelector.cs").read_text()
    assert "Package" in installer and "reviewed repository assets" in installer
    assert "models = sorted(v.model" in installer
    assert '"weapon_previews"' in installer
    assert '"equipment_previews"' in installer
    assert 'scripts_dir / "ALLIN1_preview_pending.toml"' in installer
    assert "Removed retired preview capture manifest" in installer
    assert "WORLD VECTOR" in vector
    assert "world_vector_key" in vector
    assert "preview_capture_key" in vector  # legacy config compatibility
    assert "position.X:F4" in vector
    assert "position.Y:F4" in vector
    assert "position.Z:F4" in vector
    assert "Heading {heading:F2}" in vector
    assert "CaptureMode" not in vector
    assert "CaptureScreenshot" not in vector
    assert "Vehicle previews" not in vector
    assert "IsSelectorHeld" in seat
    assert "That seat is no longer available" in seat
    assert "seat_selector_enabled" in seat
    assert "seat_selector_key" in seat


def test_preview_streaming_uses_per_dictionary_timeout_and_retry():
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text(encoding="utf-8")
    assert "Dictionary<string, DateTime> _requestStarted" in renderer
    assert "TimeSpan.FromSeconds(30)" in renderer
    assert "texture_requested" in renderer
    assert "texture_unavailable" in renderer
    assert "pending = Math.Max" in renderer
    assert "_failedDicts.Remove(dict)" in renderer
    assert "_failCheckCounter" not in renderer


def test_watchdog_recovery_and_traffic_diagnostics_are_bounded():
    watchdog = (ROOT / "script/src/ClientWatchdog.cs").read_text(encoding="utf-8")
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text(encoding="utf-8")
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text(encoding="utf-8")
    assert "DateTime.UtcNow.AddSeconds(30)" in watchdog
    assert "recovery_window_completed_features_resumed" in watchdog
    assert "PreviousSessionCrashed || ForcedSafeMode" not in watchdog
    assert "PreviewCaptureActive" not in watchdog
    assert "preview capture safe mode" not in watchdog
    assert "SmoothedFps { get; private set; } = 60f" in traffic
    assert traffic.index("UpdatePerformanceSample();") < traffic.index("if (!_enabled)")
    assert "PauseReason = ClientWatchdog.SafeModeReason" in traffic
    assert "RemoveManagedTrafficForCapture()" not in traffic
    assert "paused: " in browser


def test_floor_garage_initializes_after_temporary_safe_mode_expires():
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    assert "IsFloorGarageInitialized => _floorGarageInitialized" in garage
    assert "Floor garage initialization deferred:" in shop
    assert "!GarageManager.IsFloorGarageInitialized" in shop
    assert 'Log("Floor garage initialized after safe-mode recovery")' in shop
    recovery = shop.index("!GarageManager.IsFloorGarageInitialized")
    floor_tick = shop.index("GarageManager.OnFloorGarageTick();", recovery)
    assert recovery < floor_tick


def test_gbay_favorites_tabs_and_weapon_previews_are_integrated():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    generated = (ROOT / "script/src/WeaponList.cs").read_text()
    assert 'new Category("Favorites",' in browser
    assert 'new WeaponCategory("Favorites",' in browser
    assert browser.count("FavoritesOnly") >= 6
    assert "(_vehicleOwnershipFilter + 1) % 3" in browser
    assert "(_weaponOwnershipFilter + 1) % 3" in browser
    assert "DrawWeaponPreviewTexture(" in browser
    assert "DrawWeaponPreviewTexture(" in renderer
    assert "DrawEquipmentPreviewTexture(" in renderer
    assert '"allin1_weapon_' in generated


def test_seat_selector_is_animation_only_and_has_external_route_recovery():
    seat = (ROOT / "script/src/SeatSelector.cs").read_text()
    assert "SET_PED_INTO_VEHICLE" not in seat
    assert "TASK_WARP_PED_INTO_VEHICLE" not in seat
    assert "WarpIntoVehicle" not in seat
    assert "CLEAR_PED_TASKS_IMMEDIATELY" not in seat
    assert "TASK_SHUFFLE_TO_NEXT_VEHICLE_SEAT" in seat
    assert "TASK_LEAVE_VEHICLE" in seat
    assert "TASK_ENTER_VEHICLE" in seat
    assert "NORMAL_ENTER_FLAG = 1" in seat
    assert "NORMAL_EXIT_FLAG = 0" in seat
    assert "ExecutionPhase.Exiting" in seat
    assert "ExecutionPhase.WaitingAfterExit" in seat
    assert "ExecutionPhase.Reentering" in seat
    assert "ExecutionPhase.ApproachingExternalSeat" in seat
    assert "EXIT_SETTLE_MS = 1200" in seat
    assert "CARACARA_HASH = 1254014755" in seat
    assert "CARACARA_TURRET_APPROACH_OFFSETS" in seat
    assert "TASK_GO_STRAIGHT_TO_COORD" in seat
    assert 'new Dictionary<int, string> { { 3, "Turret" } }' in seat
    assert '"exit_animation_settle"' in seat
    assert 'BeginExit(player, "different_row_or_external_seat")' in seat
    assert "Stop the vehicle before changing rows or using an external seat" in seat
    assert "IsSeatPair(currentSeat, targetSeat, -1, 0)" in seat
    assert "IsSeatPair(currentSeat, targetSeat, 1, 2)" in seat
    assert 'CancelExecution(player, "same_row_shuffle_timeout", true)' in seat
    assert 'BeginExit(player, "shuffle_fallback")' not in seat
    assert "LIMO2_HASH = -114627507" in seat
    assert 'new Dictionary<int, string> { { 3, "Turret" } }' in seat
    assert "GetSeatLabel(_targetVeh.Model.Hash, idx)" in seat
    settle_case = seat.index("case ExecutionPhase.WaitingAfterExit:")
    settle_guard = seat.index("phaseElapsed >= EXIT_SETTLE_MS", settle_case)
    staged_reentry = seat.index("BeginExternalApproach(player, true)", settle_guard)
    reentry = seat.index("BeginEnter(player, true);", staged_reentry)
    assert settle_case < settle_guard < staged_reentry < reentry
    checklist = (ROOT / "tests/IN_GAME_CHECKLIST.md").read_text()
    assert "Benefactor Turreted Limo" in checklist
    assert "Vapid Caracara" in checklist
    assert "labeled **Turret**" in checklist


def test_client_logging_is_structured_rotating_and_shared():
    client = (ROOT / "script/src/ClientLog.cs").read_text()
    assert "ALLIN1_client.log" in client
    assert "RotateIfNeeded" in client
    assert 'Add(line, "session", Session)' in client
    assert 'Add(line, "elapsed_ms"' in client or '["elapsed_ms"]' in client
    for relative in (
        "script/src/GbayShop.cs", "script/src/GarageManager.cs",
        "script/src/SeatSelector.cs", "script/src/TrafficSpawner.cs",
        "script/src/VehicleHelper.cs",
    ):
        assert "ClientLog." in (ROOT / relative).read_text()


def test_character_customization_is_shared_with_gbay_and_has_animated_loading():
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    assert "ALLIN1_characters.json" in inventory
    assert "RecordOwned(weaponName, false)" in shop
    assert "RecordOwned(gearId, true)" in shop
    assert 'key == "replacement_chance"' in traffic
    assert "BrowserState.Loading" in browser
    assert "DrawLogo(0.5f, 0.43f" in browser
    assert "GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS" in inventory
    assert "GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS" in inventory
    assert "outfit_applied" in inventory
    assert "DEBUG: show texture dict loading status" not in browser
    assert "WeaponHashes" in inventory
    assert "internal static bool IsOwned(string item, bool gear)" in inventory
    record_owned = inventory[inventory.index("internal static void RecordOwned"):]
    assert "if (!File.Exists(PathName)) return;" not in record_owned
    assert "StringComparison.OrdinalIgnoreCase" in inventory
    assert "duplicate purchase blocked" in shop
    assert "CharacterInventory.IsOwned(weaponName, false)" in shop


def test_gbay_weapons_restore_without_clobbering_story_loadouts():
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    assert "bool hasSavedWeapons = inventory.weapons.Count > 0" in inventory
    assert "inventory.equipped_gear.Count == 0 && !hasSavedWeapons" in inventory
    apply_start = inventory.index("private static void Apply(string character)")
    weapon_loop = inventory.index("foreach (var entry in WeaponHashes)", apply_start)
    grant = inventory.index("ped.Weapons.Give", weapon_loop)
    managed_remove = inventory.index("else if (inventory.managed)", grant)
    remove = inventory.index("REMOVE_WEAPON_FROM_PED", managed_remove)
    assert weapon_loop < grant < managed_remove < remove
    assert "Game.IsLoading" in inventory
    assert "_restorePending" in inventory
    assert "player.IsDead" in inventory
    assert "player.Handle == _lastPedHandle" in inventory
    assert '"managed", inventory.managed' in inventory
    assert "IS_AUTO_SAVE_IN_PROGRESS" in inventory
    assert "CaptureWeaponAmmo(character, player, \"story_save_started\")" in inventory
    assert 'new[] { "GTA V", "GTAV Enhanced" }' in inventory
    assert 'Directory.EnumerateFiles(' in inventory
    assert 'profiles, "SGTA5*", SearchOption.AllDirectories' in inventory
    assert 'CaptureWeaponAmmo(character, player, "story_save_written")' in inventory
    assert "weapon_state_backed_up" in inventory
    assert "GET_AMMO_IN_PED_WEAPON" in inventory
    assert "Hash.SET_PED_AMMO" in inventory
    assert "inventory.weapon_ammo.TryGetValue" in inventory
    assert "RecordWeaponAmmo(weaponName, maxAmmo)" in (
        ROOT / "script/src/GbayShop.cs").read_text()
    customization = (ROOT / "src/allin1/customization.py").read_text()
    assert "LOADOUT_SCHEMA_VERSION = 5" in customization
    assert '"weapon_ammo"' in customization


def test_runtime_hot_paths_are_throttled_and_cached():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    assert "Interval = 100" in traffic
    assert "now - _lastCleanupTime >= 1000" in traffic
    assert "UpdateLocationBlipColors();" in garage
    assert "_hasBlipColor && charColor == _lastBlipColor" in garage
    assert "_lastFloorBlipColor" not in garage


def test_all_garage_entrances_fail_closed_during_story_missions():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    assert "Hash.GET_MISSION_FLAG" in garage
    assert definitions.count("disableDuringMissions: true") == 3
    assert "rules.DisableDuringMissions && missionActive" in definitions
    assert "GarageEntryPolicy.Evaluate(" in garage
    assert "RejectGarageEntry(ECLIPSE_GARAGE)" in garage
    assert "RejectGarageEntry(THREE_FLOOR_GARAGE)" in garage
    assert "RejectGarageEntry(DAVIS_GARAGE)" in davis
    # All outside tick paths consult their assigned policy before markers draw.
    assert "EvaluateGarageEntry(ECLIPSE_GARAGE)" in garage
    assert "EvaluateGarageEntry(THREE_FLOOR_GARAGE)" in garage
    assert "EvaluateGarageEntry(DAVIS_GARAGE)" in davis
    assert '"entry_blocked"' in garage


def test_dlc_garages_restore_story_map_and_interior_furniture_on_exit():
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    state = (ROOT / "script/src/DlcMapState.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    assert definitions.count("requiresMultiplayerMap: true") == 2
    assert "0x0888C3502DBBEEF5" in state  # ON_ENTER_MP
    assert "0xD7C10C4A637992C9" in state  # ON_ENTER_SP
    assert '"multiplayer_map_acquired"' in state
    assert '"story_map_restored"' in state
    assert "DlcMapState.Acquire(THREE_FLOOR_GARAGE)" in garage
    assert "DlcMapState.Release(THREE_FLOOR_GARAGE)" in garage
    assert "DlcMapState.Acquire(DAVIS_GARAGE)" in davis
    assert "DlcMapState.Release(DAVIS_GARAGE)" in davis
    assert "UnloadFloorGarageInterior();" in garage
    assert "UnloadDavisAutoShopInterior();" in davis
    assert "0x0888C3502DBBEEF5" not in garage
    assert "0x0888C3502DBBEEF5" not in davis


def test_issue_five_playtest_regressions_are_guarded():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    assert "GbayRenderer.TextDark" in browser and "GBAY artwork:" in browser
    assert "vector placeholders enabled" in renderer and "OpenRpfStatus" in renderer
    for guard in ("GET_MISSION_FLAG", "WantedLevel", "GET_INTERIOR_FROM_ENTITY",
                  "IS_POINT_ON_ROAD", "IS_ANY_VEHICLE_NEAR_POINT", "IS_SPHERE_VISIBLE"):
        assert guard in traffic
    assert "int floorCount = floorGarage ? 3 : 1" in customize
    assert "GarageSellConfirm" in browser and "CONFIRM VEHICLE SALE" in browser
    assert "progress_applied" in inventory and "STAT_SET_INT" in inventory


def test_gbay_information_pages_have_a_clickable_back_action():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    assert "INFO_BACK_W" in browser and "INFO_BACK_H" in browser
    assert "private bool DrawCenteredBackButton(" in browser
    assert "return input.MouseClick && hover" in browser
    assert "input.Back || input.MouseRightClick || backClicked" in browser
    assert 'DrawInfoPanel("DIAGNOSTICS"' in browser
    assert 'DrawInfoPanel("ABOUT ALLIN1"' in browser
    assert "}, input, false);" in browser
    assert "}, input, true);" in browser
    assert "if (showLogo)" in browser
    assert "GbayRenderer.DrawBrandLogo(" in browser
    assert "BROWSER_CX, 0.165f, 0.24f, 0.115f" in browser
    assert "input, INFO_BACK_CY, INFO_BACK_W, \"Back\", false" in browser
    assert "bodyBottom = 0.775f" in browser
    assert "DrawTextFit(lines[i]" in browser
    assert '"BACK  Return to GBAY"' not in browser


def test_gbay_pages_share_back_navigation_and_visible_focus():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    assert "FocusBorderWidth" in browser and "FocusBorderColor" in browser
    assert "return 0.003f" in browser
    assert "return GbayRenderer.CardBorderSel" in browser
    assert "Math.Sin(Game.GameTime / 170.0)" not in browser
    assert browser.count("DrawCenteredBackButton(") >= 7
    assert browser.count("DrawFocusedRect(") >= 7
    assert "hasKeyboardFocus" in customize
    assert "HandleGarageCustomizeInput(input, backClicked, davisGarage" in customize


def test_gbay_catalog_is_readable_and_every_listing_is_reachable():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "DrawGbayHeader(BROWSER_CX, 0.18f, 0.22f, 0.075f)" in browser
    assert browser.count("GbayRenderer.DrawLogo(") == 1  # loading-screen PHAT only
    assert "internal static void DrawTextFit(" in renderer
    assert "private void DrawPager(" in browser
    assert "previousPageClicked" in browser and "nextPageClicked" in browser
    assert "input.ScrollDelta < 0" in browser
    assert "input.ScrollDelta > 0" in browser
    assert "LB/RB PAGES" in browser
    assert "_tabScrollOffset - (MAX_VISIBLE_TABS - 1)" in browser
    assert "_weaponTabScrollOffset - (MAX_VISIBLE_TABS - 1)" in browser
    assert "_selectedCard == maxIdx" in browser
    assert "_weaponSelectedCard == maxIdx" in browser
    assert "private const float CARD_H         = 0.21f" in browser
    assert "private const float CARD_GAP_Y     = 0.014f" in browser


def test_gbay_main_menu_uses_clean_rounded_green_header():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "DrawGbayHeader(BROWSER_CX, 0.18f, 0.22f, 0.075f)" in browser
    assert "internal static void DrawRoundedRect(" in renderer
    assert "internal static void DrawGbayHeader(" in renderer
    assert "const int slices = 32" in renderer
    assert "Color highlight" not in renderer
    assert 'DrawText("GBAY"' in renderer
    assert "TextWhite" in renderer


def test_every_gbay_screen_uses_the_shared_green_title_badge():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    gear = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "internal static void DrawTitleBadge(" in renderer
    title_badge = renderer[renderer.index("internal static void DrawTitleBadge("):]
    assert "BtnGreen" in title_badge
    assert "TextWhite" in title_badge
    for title in (
        '"LOADING GBAY"', '"VEHICLES"', '"MY GARAGE"',
        '"CONFIRM VEHICLE SALE"', '"WEAPONS"',
    ):
        assert f"DrawTitleBadge(\n                {title}" in browser
    assert "DrawTitleBadge(displayName" in browser
    assert "DrawTitleBadge(_previewDisplayName" in browser
    assert 'DrawTitleBadge(\n                "GEAR"' in gear
    assert 'davisGarage ? "CUSTOMIZE AUTO SHOP" : "CUSTOMIZE THREE FLOORS"' in customize


def test_launcher_packages_and_applies_allin1_branding():
    gui = (ROOT / "src/allin1/gui.py").read_text()
    project = (ROOT / "pyproject.toml").read_text()
    assert (ROOT / "src/allin1/assets/ALLIN1.png").stat().st_size > 0
    assert (ROOT / "src/allin1/assets/ALLIN1-icon.png").stat().st_size > 0
    assert (ROOT / "src/allin1/assets/ALLIN1.ico").stat().st_size > 0
    assert "SetCurrentProcessExplicitAppUserModelID" in gui
    assert "self.root.iconphoto(True, self._window_icon)" in gui
    assert "user32.SendMessageW(hwnd, 0x0080, 1, handle)" in gui
    assert gui.index("_register_windows_app()") < gui.rindex("root = tk.Tk()")
    assert 'allin1 = ["assets/*.png", "assets/*.ico"]' in project


def test_floor_garage_drive_in_is_visible_and_markers_match_character():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "System.Drawing.Color.FromArgb(128, 200, 100, 0)" not in garage
    assert garage.count("var markerColor = CharacterMarkerColor();") >= 3
    assert '"Eclipse Towers", "Three-Floor Garage"' in browser
    assert "GetFloorGarageStoredVehicles()" in browser
    assert "visibleGarageRows = 12" in browser
    assert "input.ScrollDelta" in browser
    assert "_pendingSellGarageLocation" in browser
    assert "RemoveFloorGarageVehicle(listIndex)" in shop
    assert "private static bool FloorGarageSave()" in garage
    fade = garage.index('Log("EnterFloorGarage: fading in")')
    confirmation = garage.index("ShowSubtitle(storedConfirmation", fade)
    assert confirmation > fade


def test_gbay_gear_store_is_reachable_and_uses_captured_previews():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    gear_browser = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert '"Vehicles", "Weapons", "Gear", "My Garage"' in browser
    assert "case BrowserState.GearBrowser:" in browser
    assert "new GearCategory(\"Protection\", GearList.Protection)" in gear_browser
    assert "new GearCategory(\"Equipment\", GearList.Equipment)" in gear_browser
    assert "DrawEquipmentPreviewTexture(" in gear_browser
    assert "_shop.ExecuteGiveGear(card.GearId, card.Price)" in gear_browser
    assert "internal void ExecuteGiveGear(string gearId, int price)" in shop
    assert "Owned = _shop.IsGearOwned(gearId)" in gear_browser
    assert "Equipped = _shop.IsGearEquipped(gearId)" in gear_browser
    assert 'card.Owned ? "OWNED"' in gear_browser
    assert "if (card.Owned)" in gear_browser
    assert "if (IsGearOwned(gearId))" in shop
    assert "ExecuteEquipGear" in gear_browser
    assert "ExecuteUnequipGear" in gear_browser
    assert 'GbayRenderer.DrawText("UNEQUIP"' in gear_browser
    assert "CharacterInventory.SetGearEquipped" in shop


def test_all_garage_locations_share_protagonist_colors():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    for blip in (
        "_entranceBlip", "_pedEntranceBlip", "_floorGarageEntranceBlip",
        "_floorGaragePedBlip", "_davisVehicleBlip", "_davisPedBlip",
    ):
        assert f"SetBlipColor({blip}, charColor);" in garage
    assert davis.count("CharacterBlipColor()") >= 2
    assert "Color markerColor = CharacterMarkerColor();" in davis
    assert "BlipColor.Green" not in davis


def test_gbay_control_legends_are_high_contrast_and_shared_across_pages():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    gear_browser = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    assert "private static void DrawControlHint(" in browser
    assert "GbayRenderer.BtnGreen" in browser
    assert "GbayRenderer.TextWhite" in browser
    assert "0.31f, 0.235f" in browser
    assert browser.count("DrawControlHint(") >= 6
    assert "DrawControlHint(" in gear_browser
    assert "DrawControlHint(" in customize
    assert "BROWSER_LEFT + 0.10f" in browser


def test_garage_sales_fall_back_to_native_values_for_uncatalogued_vehicles():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "GarageManager.IsProtectedStoryVehicle(" in browser
    assert "model, plateText, modelHash" in browser
    assert 'protectedStory ? "Protected"' in browser
    assert 'sellPrice > 0 ? $"Sell ${sellPrice:N0}" : "Remove"' in browser
    assert "GET_VEHICLE_MODEL_VALUE" in shop
    assert "GET_VEHICLE_CLASS_FROM_NAME" in shop
    assert "GetFallbackVehicleValue" in shop
    assert "IS_MODEL_A_VEHICLE" in shop
    assert "if (!VehicleList.Prices.TryGetValue(model, out buyPrice))" in shop


def test_uncatalogued_garage_vehicles_preserve_native_model_identity():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    assert "internal int ModelHash;" in manager
    assert 'sb.Append($"\\\"modelHash\\\": {GetStoredModelHash(sv)}, ");' in manager
    assert 'case "modelHash": sv.ModelHash = val;' in manager
    assert "ModelHash = veh != null && veh.Exists()" in manager
    assert manager.count("GetStoredModel(sv)") >= 4
    assert "GetGarageSizeTier(modelName, modelHash)" in manager
    assert '{ "furore", "furoregt" }' in manager
    assert "modelHash" in davis
    assert "sv.ModelHash" in browser


def test_story_owned_vehicles_cannot_enter_garage_persistence_or_sale_flow():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    for model in (
        "buffalo2", "bagger", "bodhi2", "tailgater", "premier",
        "sentinel2", "issi2", "bjxl",
    ):
        assert f'Game.GenerateHash("{model}")' in manager
    for plate in (
        "FC1988", "FC88", "BETTY32", "5MDS003", "880HS955", "KRYST4L",
        "P3RSEUS", "57EIG117",
    ):
        assert f'"{plate}"' in manager
    assert "IsProtectedStoryVehicle(veh.Model.Hash, plate)" in manager
    assert definitions.count("blockStoryOwnedVehicles: true") == 3
    assert "rules.BlockStoryOwnedVehicles && storyOwnedVehicle" in definitions
    assert "IsPersonalVehicle(vehicle);" in manager
    assert "RejectGarageEntry(\n                        ECLIPSE_GARAGE, rideIn" in manager
    assert "RejectGarageEntry(\n                        THREE_FLOOR_GARAGE, rideIn" in manager
    assert "RejectGarageEntry(\n                        DAVIS_GARAGE, rideIn" in davis
    assert "model, plateText, modelHash" in shop
    assert '"protected_story_vehicle"' in shop


def test_davis_auto_shop_is_a_separate_persistent_ten_car_garage():
    garage = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "new Vector3(204.0661f, -1466.4750f, 29.1437f)" in garage
    assert "new Vector3(215.0502f, -1461.0250f, 29.1847f)" in garage
    assert "new Vector3(-1357.6240f, 153.2929f, -99.1942f)" in garage
    assert "DAVIS_INTERIOR_PED_HEADING = 0f" in garage
    assert '"tr_tuner_shop_rancho"' in garage
    assert '"entity_set_style_9"' in garage
    assert garage.count('"entity_set_style_9"') >= 2
    assert "private const int DAVIS_SLOT_COUNT = 10" in garage
    assert garage.count("new ParkingSlot(") == 10
    assert '"ALLIN1_davis_garage.json"' in garage
    assert '"ALLIN1_davis_customization.json"' in garage
    assert "DAVIS_CUSTOM_CATEGORY_NAMES" in garage
    assert "GetDavisCustomizationChoice" in garage
    assert "SetDavisCustomizationChoice" in garage
    assert "ApplyDavisAutoShopCustomization" in garage
    assert "0xC1F1920BAF281317" in garage
    assert "Customize Auto Shop" in browser
    assert "Fixed Auto Shop Interior" not in browser
    assert "DavisUpdateStoredFromLive();" in manager
    assert '"Eclipse Towers", "Three-Floor Garage", "Davis Auto Shop"' in browser
    assert "GetDavisGarageStoredVehicles()" in browser
    assert "ExecuteDeliverToDavisGarage" in shop
    assert "RemoveDavisGarageVehicle(listIndex)" in shop
    assert "CenterVehicleInParkingSpace" in manager
    assert "GET_MODEL_DIMENSIONS" in manager
    assert "maxCorrection = 1.25f" in manager


def test_legacy_garages_use_real_customization_sets_and_model_aware_placement():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    assert manager.count("CenterVehicleInParkingSpace(") >= 5
    assert '"Eclipse"' in manager and '"ThreeFloor", 2.0f' in manager
    assert "GetGarageSizeTier" in manager
    assert "width > 3.4f || length > 8.5f" in manager
    assert "GET_MODEL_DIMENSIONS" in manager
    assert 'new[] { "Int02_ba_floor01", "Int02_ba_floor02", "Int02_ba_floor03",' in manager
    assert '"Int02_ba_floor04", "Int02_ba_floor05"' in manager
    assert '"Int02_ba_sec_upgrade_grg"' in manager
    assert '"Int02_ba_equipment_upgrade"' in manager
    assert '"Int02_ba_sec_desks_L1", "Int02_ba_sec_desks_L2345"' in manager
    assert '"Int02_ba_clutterstuff"' in manager
    assert manager.count('ACTIVATE_INTERIOR_ENTITY_SET, interior, "Int02_ba_sec_upgrade_grg"') == 0
    for invalid_set in (
        "Int02_ba_Style01", "Int02_ba_walls_01",
        "Int02_ba_decor_01", "Int02_ba_trad_lights",
    ):
        assert invalid_set not in manager
    apply_sets = manager[manager.index("private static void ApplyFloorEntitySets"):]
    assert apply_sets.index("DEACTIVATE_INTERIOR_ENTITY_SET") < apply_sets.index(
        "ACTIVATE_INTERIOR_ENTITY_SET")
    assert "GetFloorCustomizationOptionCount" in manager
    assert "DrawFloorCustomizationCarousel" in customize
    assert 'F{sv.Slot / 5 + 1}-{sv.Slot % 5 + 1}' in browser
    assert '"Fixed Interior"' in browser
    assert "bool customizationAvailable = floorGarage || davisGarage" in browser
    assert manager.count("new ParkingSlot(-1517.0f") == 20
    assert manager.count("-80.0f, 90f)") == 20


def test_rpf_diagnostics_distinguish_plugin_from_asi_host_and_disabled_state():
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    policy = (ROOT / "script/src/PreviewRuntimeStatus.cs").read_text()
    assert '"OpenRPF.asi.disabled"' in renderer
    assert '"ASI loader detected; OpenRPF plug-in missing"' in policy
    assert '"OpenRPF plug-in disabled (fallback active)"' in policy
    assert '"preview streaming verified"' in policy


def test_watchdog_cleans_session_marker_on_all_graceful_shutdown_paths():
    watchdog = (ROOT / "script/src/ClientWatchdog.cs").read_text()
    assert "AppDomain.CurrentDomain.ProcessExit += OnProcessExit" in watchdog
    assert "AppDomain.CurrentDomain.DomainUnload += OnDomainUnload" in watchdog
    assert "private static void CleanupMarker()" in watchdog
    assert watchdog.count("CleanupMarker();") >= 3


def test_runtime_save_files_emit_backward_compatible_schema_markers():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    assert garage.count('\\"_schema_v2\\": []') >= 2
    assert "presets" in inventory


def test_gbay_search_ownership_and_emergency_recovery_contracts():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    input_source = (ROOT / "script/src/GbayInput.cs").read_text()
    assert "_vehicleOwnershipFilter" in browser and "_weaponOwnershipFilter" in browser
    assert "DISPLAY_ONSCREEN_KEYBOARD" in browser
    assert "IsVehicleOwned(model)" in browser
    assert "EmergencyRecover" in garage
    assert "emergency_recovery_completed" in garage
    assert "FrontendY" in input_source and "FrontendX" in input_source


def test_windows_toolchain_ci_is_cached_bounded_and_non_mutating():
    tests_workflow = (ROOT / ".github/workflows/test.yml").read_text()
    build_workflow = (ROOT / ".github/workflows/build-asi.yml").read_text()
    tools_script = (ROOT / "runtools.ps1").read_text()
    assert "cancel-in-progress: true" in tests_workflow
    assert "branches: [main]" in tests_workflow
    assert "github.event.pull_request.number || github.ref" in tests_workflow
    assert "actions/cache@v4" in tests_workflow
    assert "windows-real-tools-v2-" in tests_workflow
    assert "timeout-minutes: 20" in tests_workflow
    assert "timeout-minutes: 8" in tests_workflow
    assert "if: github.ref == 'refs/heads/main'" in build_workflow
    assert '$env:CI -eq "true"' in tools_script
    assert "refusing to modify the hosted runner" in tools_script
    assert "-requires Microsoft.VisualStudio.Workload.NativeDesktop" in tools_script
    assert '$RpfPublishDir = Join-Path $TempDir "rpfpatcher_publish"' in tools_script
    assert '-o $RpfPublishDir' in tools_script
    assert '-o $RpfPatcherDir' not in tools_script


def test_launcher_uses_gui_entry_point_without_console_window():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[project.gui-scripts]" in pyproject
    gui_section = pyproject.split("[project.gui-scripts]", 1)[1]
    assert 'allin1-gui = "allin1.gui:main"' in gui_section


def test_repair_progress_and_helper_consoles_are_managed_in_process():
    gui = (ROOT / "src/allin1/gui.py").read_text(encoding="utf-8")
    installer = (ROOT / "src/allin1/installer.py").read_text(encoding="utf-8")
    processes = (ROOT / "src/allin1/processes.py").read_text(encoding="utf-8")
    ytd_builder = (ROOT / "src/allin1/generators/ytd_builder.py").read_text(
        encoding="utf-8"
    )
    assert '"Repairing"' in gui and 'kind == "progress"' in gui
    assert 'mode="determinate"' in gui and "maximum=100" in gui
    assert "launch_pending" in gui and "root.after(15000" in gui
    assert "CREATE_NO_WINDOW" in processes and "STARTF_USESHOWWINDOW" in processes
    assert "subprocess.run(" not in installer
    assert "subprocess.run(" not in ytd_builder
