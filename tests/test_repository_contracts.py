"""Whole-repository contracts connecting data, generated code, and releases."""

import json
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
from pathlib import Path
from PIL import Image

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
    assert set(prices) == models
    assert all(price > 0 for price in prices.values())
    catalog = json.loads((ROOT / "catalog/vehicles.json").read_text())
    assert {item["model"] for item in catalog} == models
    assert all(item["price"] > 0 for item in catalog)


def test_latest_dlc_purchase_catalog_is_complete():
    models = {
        vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")
    }
    assert {
        "velenogt", "caracara3", "merula", "laufer", "lrcgt",
        "cartuccia", "estride", "polignus", "horus", "warden",
    } <= models


def test_generated_seat_catalog_covers_base_game_and_all_supported_dlc_models():
    seat_catalog = json.loads((ROOT / "catalog/vehicle_seats.json").read_text())
    records = seat_catalog["Vehicles"]
    by_model = {record["Model"]: record for record in records}
    supported = {
        vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")
    }

    assert seat_catalog["ResolvedCount"] == seat_catalog["ModelCount"]
    assert seat_catalog["ModelCount"] >= 900
    assert seat_catalog["ArchiveCount"] >= 100
    assert "GamePath" not in seat_catalog
    assert len(by_model) == len(records)
    assert supported <= set(by_model)
    assert all(record["Status"] == "resolved" for record in records)
    assert all(record["SeatCount"] >= 1 for record in records)

    assert by_model["technical"]["Seats"][2]["Label"] == "Bed Turret"
    assert by_model["barrage"]["Seats"][2]["Label"] == "Top Turret"
    assert by_model["barrage"]["Seats"][3]["Label"] == "Rear Turret"
    assert by_model["boxville5"]["Seats"][4]["Label"] == "Roof Turret"
    assert by_model["insurgent2"]["Seats"][8]["Label"] == "Roof Turret"
    assert by_model["insurgent2"]["Seats"][6]["Label"] == "Left Bed Seat"
    assert [seat["Index"] for seat in by_model["limo2"]["Seats"] if seat["Turret"]] == [3]
    assert not any(seat["Turret"] for seat in by_model["savage"]["Seats"])


def test_promoted_grounding_catalog_contains_every_validated_outcome():
    catalog = json.loads((ROOT / "data/vehicle_grounding.json").read_text())
    entries = catalog["Entries"]
    assert catalog["SchemaVersion"] == 1
    assert catalog["TotalModels"] == 827
    assert len(entries) == 827
    assert catalog["StableModels"] == catalog["MeasuredModels"] == 821
    assert catalog["UnsupportedModels"] == 6
    assert catalog["OutlierModels"] == 0
    measured = [entry for entry in entries.values() if entry["Status"] == "measured"]
    unsupported = [entry for entry in entries.values() if entry["Status"] == "unsupported"]
    assert len(measured) == 821
    assert all(entry["Stable"] is True for entry in measured)
    assert all(0 <= float(entry["RootOffset"]) <= 5 for entry in measured)
    assert {entry["Model"] for entry in unsupported} == {
        "boattrailer", "boattrailer2", "boattrailer3", "kosatka",
        "trailerlarge", "trailersmall",
    }
    assert all(entry["Stable"] is False for entry in unsupported)


def test_vehicle_previews_cover_database():
    models = {vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")}
    previews = {path.stem for path in (ROOT / "script/dist/previews").glob("*.png")}
    pending = set(tomllib.loads((ROOT / "data/preview_pending.toml").read_text())["models"])
    assert models - previews == pending
    assert pending <= models
    source = (ROOT / "script/src/VehicleList.cs").read_text()
    preview_source = source[source.index("PreviewDict"):]
    for model in pending:
        assert f'{{ "{model}", "allin1_prev_' not in preview_source


def test_world_asset_preview_is_packaged_and_streamed_separately():
    preview = ROOT / "script/dist/world_asset_previews/allin1_super_yacht.png"
    assert preview.is_file()
    with Image.open(preview) as image:
        assert image.size == (512, 288)
        assert image.format == "PNG"
    asset_list = (ROOT / "script/src/WorldAssetList.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    installer = (ROOT / "src/allin1/installer.py").read_text()
    assert '"allin1_asset_01"' in asset_list
    assert "WorldAssetList.PreviewDict.TryGetValue" in renderer
    assert "GbayRenderer.TryGetPreviewDict" in browser
    assert '"allin1_asset"' in installer
    assert '"world_asset_previews"' in installer


def test_generated_csharp_contains_every_data_model():
    source = (ROOT / "script/src/VehicleList.cs").read_text()
    for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml"):
        assert f'"{vehicle.model}"' in source


def test_production_project_includes_only_supported_developer_tools():
    project = (ROOT / "script/ALLIN1.csproj").read_text()
    assert '<Compile Remove="tools\\**" />' in project
    assert '<Compile Include="tools\\WorldVectorTool.cs" />' in project
    assert '<Compile Include="tools\\VehicleGroundingTool.cs" />' not in project
    assert '<Compile Include="tools\\SeatTestTool.cs" />' not in project
    assert project.count('<Compile Include="tools\\') == 1
    assert not (ROOT / "script/src/GarageTraversalLab.cs").exists()
    assert not (ROOT / "script/tests/GarageTraversalLabPolicyTests.cs").exists()


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


def test_windows_installer_bootstraps_a_real_python_runtime():
    installer = (ROOT / "install.bat").read_text(encoding="utf-8")
    assert "call :find_python" in installer
    assert "sys.version_info.minor in range(10, 100)" in installer
    assert "Python.Python.3.12" in installer
    assert "winget install --exact" in installer
    assert '"--check-python"' in installer
    assert "where python >nul" not in installer


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


def test_garage_vehicle_progress_only_commits_on_story_saves():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()

    assert "GarageStorySavePolicy.HasSaveEvent(" in garage
    assert "Hash.IS_AUTO_SAVE_IN_PROGRESS" in garage
    assert "CharacterInventory.LatestStorySaveWriteUtc()" in garage
    assert "PersistVehiclesForStorySave(" in garage
    assert '"vehicle_state_backed_up"' in garage
    assert "if (!_vehicleSaveCommitInProgress)" in garage
    assert "Aborted += OnAborted" in shop
    assert "GarageManager.OnScriptAborted();" in shop
    assert "internal static DateTime LatestStorySaveWriteUtc()" in inventory
    assert "latestStorySaveWriteUtc > lastObservedStorySaveWriteUtc" in definitions

    assert "StageOrWriteVehicleSave(SAVE_PATH, BuildJson" in garage
    assert "FLOOR_GARAGE_SAVE_PATH, FloorGarageBuildJson" in garage
    assert "DAVIS_SAVE_PATH, DavisBuildJson" in davis
    assert "GARMENT_SAVE_PATH, GarmentBuildJson" in garment
    assert "RURAL_SAVE_PATH, RuralBuildJson" in rural

    commit = garage[garage.index("private static void PersistVehiclesForStorySave"):
                    garage.index("private static bool IsPersonalVehicle")]
    for save_call in (
        "Save();", "FloorGarageSave();", "DavisSave();",
        "GarmentSave();", "RuralSave();",
    ):
        assert save_call in commit


def test_content_audit_models_are_in_catalog():
    models = {vehicle.model for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml")}
    audited = {
        "cargobob5", "duster2", "maverick2", "poldominator10", "poldorado",
        "polgreenwood", "polimpaler5", "polimpaler6", "titan2", "vivanite2", "youga5",
        "caracara3", "cartuccia", "estride", "laufer", "lrcgt", "merula",
        "polignus", "velenogt",
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
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    assert "IS_WEAPON_VALID" in shop
    assert "HAS_PED_GOT_WEAPON" in shop
    assert "GetWeaponPurchaseQuote" in shop
    assert "PriceActualQuantity" in shop
    assert "GetAmmoUnitPrice" in shop
    assert "PurchaseQuantities" in generated
    assert '{ "WEAPON_STICKYBOMB", 25 }' in generated
    assert '{ "WEAPON_PROXMINE", 5 }' in generated
    assert '$"{card.PurchaseQuantity} x ${card.UnitPrice:N0} = ${card.Price:N0}"' in browser


def test_world_vector_and_seat_selector_contracts():
    installer = (ROOT / "src/allin1/installer.py").read_text()
    vector = (ROOT / "script/tools/WorldVectorTool.cs").read_text()
    seat = (ROOT / "script/src/SeatSelector.cs").read_text()
    assert "Package" in installer and "reviewed repository assets" in installer
    assert "models = sorted(v.model" in installer
    assert '"weapon_previews"' in installer
    assert '"equipment_previews"' in installer
    assert "RETIRED_DEVELOPER_ARTIFACTS" in installer
    assert "ALLIN1_height_check.toml" in installer
    assert "RETIRED_DEVELOPER_DIRECTORIES" in installer
    assert "ALLIN1_seat_tests" in installer
    assert "ALLIN1.dll.pre-seat-nav-fix.bak" in installer
    assert "Removed retired developer artifact" in installer
    assert "WORLD VECTOR" in vector
    assert "world_vector_key" in vector
    assert "preview_capture_key" not in vector
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
    assert "FindNavigationTarget" in seat
    assert "GetSeatEnumerationPassengerLimit" in seat
    assert "Sparse authored layouts" in seat


def test_vehicle_grounding_catalog_is_complete_and_read_only_at_runtime():
    assert not (ROOT / "script/tools/VehicleGroundingTool.cs").exists()
    assert not (ROOT / "script/src/VehicleGroundingPolicy.cs").exists()
    catalog = (ROOT / "script/src/VehicleGroundingCatalog.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    assert "ALLIN1_vehicle_grounding.json" in catalog
    assert "ALLIN1_vehicle_grounding_outliers.json" not in catalog
    assert "WriteAtomic" not in catalog
    assert "static void Save" not in catalog
    assert "TryGetStableRootOffset" in manager
    assert "SET_ENTITY_ROTATION" in manager
    assert "heightSource=\u007bheightSource\u007d" in manager
    assert "VehicleGroundingTool" not in traffic

    document = json.loads((ROOT / "data/vehicle_grounding.json").read_text())
    entries = document["Entries"]
    resolved = [
        entry for entry in entries.values()
        if ((entry.get("Status") == "measured" and entry.get("Stable") is True)
            or entry.get("Status") == "unsupported")
    ]
    assert len(entries) == 827
    assert len(resolved) == 827
    assert document["StableModels"] == 821
    assert document["UnsupportedModels"] == 6
    assert document["OutlierModels"] == 0


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
    assert "new List<ManagedTraffic>()" in traffic
    assert "RequiresDriver = true" in traffic
    assert "keepPersistent: true" in traffic
    assert "ShouldPurgeManagedTraffic(suppression)" in traffic
    assert "managed_occupancy_released" in traffic
    assert "DecideManagedTrafficAction" in traffic
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
    workbench = (ROOT / "script/src/GbayWeaponCustomization.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    generated = (ROOT / "script/src/WeaponList.cs").read_text()
    assert 'new Category("Favorites",' in browser
    assert 'new WeaponCategory("Favorites",' in browser
    assert browser.count("FavoritesOnly") >= 6
    assert "(_vehicleOwnershipFilter + 1) % 3" in browser
    assert "(_weaponOwnershipFilter + 1) % 3" in browser
    purchase_route = browser.split("activateIdx == 1", 1)[1].split(
        "activateIdx == 2", 1
    )[0]
    assert '_weaponOwnershipFilter = 0;' in purchase_route
    assert '_weaponSearch = "";' in purchase_route
    assert "if (_state != BrowserState.WeaponCustomize)" in browser
    assert "Keep one camera alive for the entire workbench session" in workbench
    assert "SET_CAM_ACTIVE_WITH_INTERP" not in workbench
    assert "_weaponCamera.Position = _workbenchCameraPosition" in workbench
    assert "IS_CAM_RENDERING" in workbench
    assert '"weapon_camera_render_repaired"' in workbench
    assert "TASK_AIM_GUN_AT_COORD" not in workbench
    assert "ped.Task.AimAt(_workbenchAimTarget, -1)" in workbench
    assert "TASK_PLAY_ANIM" not in workbench
    assert "CanUseWeaponWorkbenchHere" in workbench
    assert "GET_INTERIOR_FROM_ENTITY" in workbench
    assert "GET_NUM_DLC_WEAPONS" in workbench
    assert "GET_DLC_WEAPON_COMPONENT_DATA" in workbench
    assert "Marshal.AllocHGlobal" in workbench
    assert "Marshal.PtrToStructure<RuntimeDlcWeaponData>" in workbench
    assert "new OutputArgument(\n                    new RuntimeDlcWeaponData())" not in workbench
    assert "WeaponComponent.GetAllHashes()" in workbench
    assert "DOES_WEAPON_TAKE_WEAPON_COMPONENT" in workbench
    assert "SET_PED_CAN_PLAY_AMBIENT_ANIMS" in workbench
    assert "WORKBENCH_WEAPON_RECOVERY_DELAY_MS" in workbench
    assert "SET_PED_WEAPON_COMPONENT_TINT_INDEX" in workbench
    assert "_workbenchAnchorForward" in workbench
    assert "MaintainWeaponWorkbenchPose" in workbench
    assert "if (_workbenchCameraAngle > 52f)" in workbench
    assert "PointWeaponCameraAtFocus" in workbench
    assert "SetWeaponCameraFocusTarget" in workbench
    assert "SET_LOCAL_PLAYER_VISIBLE_LOCALLY" in workbench
    assert 'equipped ? "EQUIPPED" : fullAmmo ? "FULL"' in workbench
    assert "row.Kind != WorkbenchRowKind.Ammo" in workbench
    assert "0.005f, rowH - 0.014f, GbayRenderer.Success" in workbench
    assert "input.MouseMoved" in workbench
    assert workbench.count("ApplyWeaponCustomizationNow") >= 2
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    assert "hasSavedCustomizations" in inventory
    assert "internal static bool ApplyWeaponCustomizationNow" in inventory
    assert "owned_component_tints" in inventory
    assert "active_component_tints" in inventory
    assert "GET_PED_WEAPON_COMPONENT_TINT_INDEX" in inventory
    assert "HAS_PED_GOT_WEAPON_COMPONENT" in inventory.split(
        "internal static bool ApplyWeaponCustomizationNow", 1
    )[1]
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
    assert "NORMAL_ENTER_FLAG = 0" in seat
    assert "NORMAL_EXIT_FLAG = 0" in seat
    assert "ExecutionPhase.Exiting" in seat
    assert "ExecutionPhase.WaitingAfterExit" in seat
    assert "ExecutionPhase.Reentering" in seat
    assert "ExecutionPhase.ApproachingExternalSeat" in seat
    assert "EXIT_SETTLE_MS = 1200" in seat
    assert "CARACARA_HASH = 1254014755" in seat
    assert "CARACARA_TURRET_APPROACH_OFFSETS" in seat
    assert "CARACARA_REAR_LEFT_APPROACH_OFFSETS" in seat
    assert "CARACARA_REAR_RIGHT_APPROACH_OFFSETS" in seat
    assert "SeatSwitchTelemetry" not in seat
    assert "HarnessSwitchFinished" not in seat
    assert "TryBeginHarnessSwitch" not in seat
    assert "seat_lab" not in seat
    assert "TASK_FOLLOW_NAV_MESH_TO_COORD" in seat
    assert "GET_NAVMESH_ROUTE_RESULT" in seat
    assert "EXTERNAL_ROUTE_STALL_TIMEOUT_MS" in seat
    assert "BeginSimulatedExternalRoutePlan(player)" in seat
    assert "ShapeTest.StartTestCapsule" in seat
    assert "ExecutionPhase.PlanningExternalRoute" in seat
    assert "BuildLocalExternalRoute" in seat
    assert '"preexit_route_blocked"' in seat
    assert '"preexit_route_planned"' in seat
    assert "ExecutionPhase.RecoveringWrongSeat" in seat
    assert "ExecutionPhase.ReturningToSourceSeat" in seat
    assert '"restore_source_seat"' in seat
    assert '"seat_switch_rolled_back"' in seat
    assert "NATIVE_ENTER_TIMEOUT = -1" in seat
    assert "GetNativeEntryRequestSeat" in seat
    assert "SET_CONTROL_VALUE_NEXT_FRAME" in seat
    assert "native_context_turret_reentry" in seat
    assert "ShouldUseNativeContextEntry" in seat
    assert "IsSeatSelectable" in seat
    assert "VehicleSeatLayoutCatalog.GetLabel" in seat
    assert '"exit_animation_settle"' in seat
    assert 'BeginExit(player, "different_row_or_external_seat")' in seat
    assert "Stop the vehicle before changing rows or using an external seat" in seat
    assert "IsSeatPair(currentSeat, targetSeat, -1, 0)" in seat
    assert "IsSeatPair(currentSeat, targetSeat, 1, 2)" in seat
    assert 'CancelExecution(player, "same_row_shuffle_timeout", true)' in seat
    assert 'BeginExit(player, "shuffle_fallback")' not in seat
    assert "LIMO2_HASH = -114627507" in seat
    generated_seats = (ROOT / "script/src/VehicleSeatLayoutCatalog.cs").read_text()
    assert 'Model = "limo2"' in generated_seats
    assert '{ 3, "Roof Turret" }' in generated_seats
    assert '{ 3, "Bed Turret" }' in generated_seats
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
    assert "gbay_state_backed_up" in inventory
    assert "GET_AMMO_IN_PED_WEAPON" in inventory
    assert "Hash.SET_PED_AMMO" in inventory
    assert "inventory.weapon_ammo.TryGetValue" in inventory
    assert "RecordWeaponAmmo(weaponName, refillTarget)" in (
        ROOT / "script/src/GbayShop.cs").read_text()
    customization = (ROOT / "src/allin1/customization.py").read_text()
    assert "LOADOUT_SCHEMA_VERSION = 8" in customization
    assert '"weapon_ammo"' in customization


def test_all_gbay_mutations_commit_only_at_story_save_boundary():
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    preferences = (ROOT / "script/src/GbayPreferences.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()

    purchase_section = inventory[
        inventory.index("internal static void RecordOwned"):
        inventory.index("private void OnAborted")
    ]
    assert "StageStateLocked(" in purchase_section
    assert "SaveStateLocked();" in purchase_section
    assert purchase_section.count("SaveStateLocked();") == 1
    assert "GbayPreferences.CommitForStorySave(reason);" in purchase_section
    assert "GbayPreferences.DiscardStaged();" in inventory
    assert "GbayShop.DiscardStagedRuntimeGear" in inventory

    mutation_section = preferences[
        preferences.index("internal static void ToggleVehicle"):
        preferences.index("private static GbayPreferenceData Load()")
    ]
    assert "Save();" not in mutation_section
    assert "Stage();" in mutation_section
    assert "internal static void CommitForStorySave" in preferences
    assert "internal static void DiscardStaged" in preferences

    assert "_garageCustomizationSavesDirty = true;" in garage
    assert "FloorGarageThemesWrite();" in garage
    assert "DavisCustomizationWrite();" in garage
    assert "private static bool DavisCustomizationWrite()" in davis
    assert "ReloadCommittedGarageState();" in garage


def test_runtime_hot_paths_are_throttled_and_cached():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    assert "Interval = 100" in traffic
    assert "now - _lastCleanupTime >= 1000" in traffic
    assert "UpdateLocationBlipColors();" in garage
    assert "_hasBlipColor && charColor == _lastBlipColor" in garage
    assert "_lastFloorBlipColor" not in garage


def test_traffic_replacements_clone_occupants_before_atomic_commit():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    replace = traffic[traffic.index("private bool ReplaceVehicle"):]
    clone = replace.index("TryCloneOccupants")
    delete = replace.index("old.Delete()")
    assert clone < delete
    assert "occupant.SourcePed.Clone" in traffic
    assert "clone.SetIntoVehicle" in traffic
    assert "SourceOccupantsUnchanged(occupants, old)" in replace
    assert "CleanupStagedReplacement" in replace
    assert "CanCommitReplacement(hadDriver, clonedDriver != null)" in traffic
    assert "SET_PED_INTO_VEHICLE" not in traffic
    assert "SET_ENTITY_DYNAMIC" in traffic
    assert "ACTIVATE_PHYSICS" in traffic
    assert "SET_VEHICLE_HANDBRAKE" in traffic
    assert "GetTrafficCruiseSpeed(capturedSpeed)" in traffic


def test_traffic_replacement_scan_has_bounded_work_and_expiring_seen_cache():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    scan = traffic[traffic.index("private void ScanAndReplace"):
                   traffic.index("private bool IsEligibleForReplacement")]
    assert "MAX_SCAN_CANDIDATES = 24" in traffic
    assert "THROTTLED_SCAN_CANDIDATES = 12" in traffic
    assert "MAX_REPLACEMENTS_PER_SCAN = 1" in traffic
    assert "replacementAttempts >= MAX_REPLACEMENTS_PER_SCAN" in scan
    assert "_seenVehicleOrder" in traffic
    assert "SEEN_HANDLE_TTL_MS" in traffic
    assert "DOES_ENTITY_EXIST" not in scan
    assert "_replacedHandles" not in traffic


def test_all_garage_entrances_fail_closed_during_story_missions():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    assert "Hash.GET_MISSION_FLAG" in garage
    assert definitions.count("disableDuringMissions: true") == 6
    assert definitions.count("blockWantedLevel: true") == 6
    assert "rules.DisableDuringMissions && missionActive" in definitions
    assert "rules.BlockWantedLevel && wantedLevel > 0" in definitions
    assert "!garagesAlwaysAccessible" in definitions
    assert "Game.Player.WantedLevel" in garage
    assert "garages_always_accessible" in (
        ROOT / "src/allin1/config.py").read_text()
    assert "Allow garage entry while wanted" in (
        ROOT / "src/allin1/gui.py").read_text()
    assert "GarageEntryPolicy.Evaluate(" in garage
    assert "RejectGarageEntry(ECLIPSE_GARAGE)" in garage
    assert "RejectGarageEntry(THREE_FLOOR_GARAGE)" in garage
    assert "RejectGarageEntry(DAVIS_GARAGE)" in davis
    assert "RejectGarageEntry(GARMENT_GARAGE)" in garment
    assert "RejectGarageEntry(RURAL_GARAGE)" in rural
    assert "RejectGarageEntry(PALETO_GARAGE)" in paleto
    assert "EvaluateGarageEntry(ECLIPSE_GARAGE)" in garage
    assert "EvaluateGarageEntry(THREE_FLOOR_GARAGE)" in garage
    assert "EvaluateGarageEntry(DAVIS_GARAGE)" in davis
    assert "EvaluateGarageEntry(GARMENT_GARAGE)" in garment
    assert "EvaluateGarageEntry(RURAL_GARAGE)" in rural
    assert "EvaluateGarageEntry(PALETO_GARAGE)" in paleto
    assert '"entry_blocked"' in garage


def test_all_garages_block_unsafe_game_transitions_before_local_map_load():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    assert "GameTransitionActive" in definitions
    assert "gameTransitionActive" in definitions
    assert "IsUnsafeGarageTransitionActive()" in garage
    assert "Hash.IS_CUTSCENE_ACTIVE" in garage
    assert "Hash.IS_PLAYER_SWITCH_IN_PROGRESS" in garage
    assert "Hash.IS_SCREEN_FADING_IN" in garage
    assert "Hash.IS_SCREEN_FADING_OUT" in garage

    loader = garage[garage.index("private static bool LoadFloorGarageInterior"):
                    garage.index("private static void UnloadFloorGarageInterior")]
    assert loader.index("IsUnsafeGarageTransitionActive()") < loader.index(
        "StandaloneMapPack.TryActivate(FLOOR_GARAGE_REQUIRED_IPLS, 1500)")
    assert "DlcMapState" not in loader
    assert "UnloadFloorGarageInterior();" in loader
    assert "Hash.SET_FOCUS_POS_AND_VEL" in loader
    assert 'FLOOR_GARAGE_INTERIOR_TYPE = "ba_dlc_int_02_ba"' in garage
    assert "Hash.GET_INTERIOR_AT_COORDS_WITH_TYPE" in garage
    assert "Hash.IS_VALID_INTERIOR" in garage
    assert "Hash.DISABLE_INTERIOR, interior, true" in garage
    assert "Hash.PIN_INTERIOR_IN_MEMORY" in garage
    assert "Hash.DISABLE_INTERIOR, interior, false" in garage
    assert "Hash.SET_INTERIOR_ACTIVE, interior, true" in garage
    assert "Hash.CAP_INTERIOR, interior, false" in garage
    assert "Hash.SET_INSTANCE_PRIORITY_MODE, true" in loader
    assert "Hash.SET_INSTANCE_PRIORITY_MODE, false" in loader
    assert "Hash.REQUEST_COLLISION_AT_COORD" in loader
    assert "Hash.IS_INTERIOR_READY" in loader
    assert "TryProbeInteriorFloor" in loader
    assert "interiorReady && floorCollisionReady" in loader
    assert "GarageInteriorReadinessPolicy.IsUsable" not in loader
    assert "Hash.REMOVE_IPL" not in loader

    entry = garage[garage.index("private static void EnterFloorGarageCore"):
                   garage.index("private static void LeaveFloorGarage()")]
    assert "if (!LoadFloorGarageInterior())" in entry
    assert "storedListDuringEntry.Remove(storedDuringEntry)" in entry
    assert "rolled back drive-in storage after interior load failure" in entry


def test_grapeseed_garage_is_fully_integrated_and_persistent():
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    installer = (ROOT / "src/allin1/installer.py").read_text()
    assert "private const int RURAL_SLOT_COUNT = 6" in rural
    assert "new Vector3(2551.4610f, 4674.3250f, 33.9819f)" in rural
    assert "RURAL_VEHICLE_ENTRANCE_HEADING = 0f" in rural
    assert "new Vector3(2553.4590f, 4650.6360f, 34.0768f)" in rural
    assert "RURAL_PED_ENTRANCE_HEADING = 90f" in rural
    assert '"ALLIN1_rural_garage.json"' in rural
    assert "RuralUpdateStoredFromLive();" in manager
    assert "GetRuralGarageStoredVehicles()" in manager
    assert "Grapeseed" in browser
    assert "ExecuteDeliverToRuralGarage" in shop
    assert "OnRuralGarageTick" in shop
    assert "ALLIN1_rural_garage.json" in installer
    rural_definition = definitions[
        definitions.index("GarageDefinition Rural"):
        definitions.index("GarageDefinition Paleto")
    ]
    assert "requiresMultiplayerMap: true" not in rural_definition


def test_grapeseed_entry_streams_the_explicit_six_car_milo():
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    loader = rural[rural.index("private static bool LoadRuralInterior"):
                   rural.index("private static void UnloadRuralInterior")]
    entry = rural[rural.index("private static void EnterRuralGarageCore"):
                  rural.index("private static void LeaveRuralGarage")]

    assert '"hw1_blimp_interior_v_garagem_milo_"' in rural
    assert '"v_garagem",' not in rural
    assert "new Vector3(206.3603f, -999.0687f, -99.0000f)" in rural
    assert "RURAL_INTERIOR_PED_HEADING = 90f" in rural
    assert "Hash.REQUEST_IPL" in loader
    assert "Hash.SET_FOCUS_POS_AND_VEL" in loader
    assert "Hash.REQUEST_COLLISION_AT_COORD" in loader
    assert "IS_INTERIOR_READY" in loader
    assert "IS_IPL_ACTIVE" in loader
    assert "GarageInteriorReadinessPolicy.IsUsable" in loader
    assert "interior, true, iplActive" in loader
    assert "RURAL_INTERIOR_FALLBACK_SETTLE_MS" in loader
    assert "PIN_INTERIOR_IN_MEMORY" in loader
    assert "DISABLE_INTERIOR" in loader
    assert "DlcMapState.Acquire(RURAL_GARAGE)" not in loader
    assert "ON_ENTER_MP" not in loader
    assert "RURAL_INTERIOR_LOAD_TIMEOUT_MS" in loader
    assert "if (!interiorLoaded && !LoadRuralInterior())" in entry
    assert "DlcMapState.Release(RURAL_GARAGE)" not in rural
    assert "Hash.REMOVE_IPL" in rural


def test_paleto_bay_garage_uses_native_casino_layout_and_full_integration():
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    installer = (ROOT / "src/allin1/installer.py").read_text()
    diagnostics = (ROOT / "src/allin1/diagnostics.py").read_text()

    assert "private const int PALETO_SLOT_COUNT = 10" in paleto
    assert "new Vector3(-221.9008f, 6252.8020f, 31.4894f)" in paleto
    assert "PALETO_VEHICLE_ENTRANCE_HEADING = 45f" in paleto
    assert "new Vector3(-224.5180f, 6244.2620f, 31.4926f)" in paleto
    assert "PALETO_PED_ENTRANCE_HEADING = 45f" in paleto
    assert "new Vector3(1295.3110f, 221.1703f, -49.0574f)" in paleto
    assert "new Vector3(1295.3350f, 260.7359f, -49.0574f)" in paleto
    assert "PALETO_INTERIOR_PED_EXITS.Length" in paleto
    exit_headings = paleto[
        paleto.index("PALETO_INTERIOR_PED_EXIT_HEADINGS"):
        paleto.index("private const float PALETO_FLOOR_Z")
    ]
    assert "0f," in exit_headings
    assert "180f," in exit_headings
    assert '"vw_casino_garage"' in paleto
    assert "new Vector3(1295.0000f, 230.0000f, -50.0000f)" in paleto
    assert paleto.count("new ParkingSlot(") == 10
    assert "1281.4710f, 241.6617f, -49.3467f, 270f" in paleto
    assert "1309.3640f, 232.0345f, -49.3470f, 90f" in paleto
    assert "1295.5920f, 249.7942f, -49.3470f, 211.32f" in paleto
    assert "PlaceVehicleInParkingSpace(" in paleto
    assert "ReleaseGarageVehicleForDriving(playerVehicle" in paleto
    assert '"ALLIN1_paleto_garage.json"' in paleto
    assert "PaletoUpdateStoredFromLive();" in manager
    assert "GetPaletoGarageStoredVehicles()" in manager
    assert '"Paleto Bay Garage"' in browser
    assert "ExecuteDeliverToPaletoGarage" in shop
    assert "RemovePaletoGarageVehicle(listIndex)" in shop
    assert "OnPaletoGarageTick" in shop
    assert "ALLIN1_paleto_garage.json" in installer
    assert "ALLIN1_paleto_garage.json" in diagnostics

    assert "RequiresMultiplayerMap" not in definitions
    assert "DlcMapState" not in paleto
    assert "GarageInteriorReadinessPolicy.IsUsable" in paleto
    assert "PALETO_INTERIOR_FALLBACK_SETTLE_MS" in paleto
    assert "ON_ENTER_MP" not in paleto


def test_traffic_protects_safehouse_storage_without_excluding_all_parked_cars():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    assert "SAFEHOUSE_GARAGE_ZONES" in traffic
    assert "IsInsideSafehouseGarageZone(vehicle.Position)" in traffic
    assert 'HasDecorator(vehicle, "Player_Vehicle")' in traffic
    assert "PLAYER_INTERACTION_PROTECTION_MS" in traffic
    assert "hadDriver" not in traffic[traffic.index("IsEligibleForReplacement"):
                                      traffic.index("ReplaceVehicle")]
def test_dlc_garages_use_only_local_story_map_assets():
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    standalone = (ROOT / "script/src/StandaloneMapPack.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "RequiresMultiplayerMap" not in definitions
    assert not (ROOT / "script/src/DlcMapState.cs").exists()
    for source in (garage, davis, garment, paleto, rural, shop):
        assert "DlcMapState" not in source
        assert "0x0888C3502DBBEEF5" not in source  # ON_ENTER_MP
        assert "0xD7C10C4A637992C9" not in source  # ON_ENTER_SP
    assert "allin1_maps" in standalone
    assert "allin1_maps.active" in standalone
    assert "Hash.IS_IPL_ACTIVE" in standalone
    assert "Hash.REQUEST_IPL" in standalone
    assert "StandaloneMapPack.TryActivate(FLOOR_GARAGE_REQUIRED_IPLS, 1500)" in garage
    assert "StandaloneMapPack.TryActivate(DAVIS_AUTO_SHOP_IPLS, 1500)" in davis
    assert "StandaloneMapPack.TryActivate(GARMENT_IPLS)" in garment
    assert "StandaloneMapPack.TryActivate(PALETO_IPLS)" in paleto
    assert "StandaloneMapPack.TryActivate(RURAL_IPLS)" in rural
    assert "UnloadFloorGarageInterior();" in garage
    assert "UnloadDavisAutoShopInterior();" in davis
    assert "standalone map unavailable" in garage
    assert "standalone map unavailable" in davis
    assert "standalone map unavailable" in garment
    assert "standalone map unavailable" in paleto


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
    assert "if (!davisGarage)" in customize
    assert "int floorCount = 1" in customize
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
    # The retired 3D showroom was one former full-screen page.
    assert browser.count("DrawCenteredBackButton(") >= 6
    assert browser.count("DrawFocusedRect(") >= 7
    assert "hasKeyboardFocus" in customize
    assert "HandleGarageCustomizeInput(input, backClicked, davisGarage" in customize


def test_gbay_catalog_is_readable_and_every_listing_is_reachable():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "DrawGbayHeader(BROWSER_CX, 0.145f, 0.22f, 0.075f)" in browser
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
    assert "private const int   MAX_VISIBLE_TABS = 6" in browser
    assert "private const int   GRID_ROWS      = 2" in browser
    assert "private const int   PAGE_SIZE      = 6" in browser
    assert "private const float CARD_H         = 0.30f" in browser
    assert "private const float CARD_GAP_Y     = 0.018f" in browser


def test_physics_live_hits_balance_without_standing_ground_writhe():
    physics = (ROOT / "script/src/NpcPhysicsExperiment.cs").read_text()
    assert "uprightValue <= 0.55f" in physics
    assert "relax.Relaxation = relaxation" in physics
    assert "private const int ScanIntervalMs = 50" in physics
    assert "private const float LiveBodyRelaxation = 25f" in physics
    assert "LiveBalanceReinforcementDelayMs = 90" in physics
    assert '"delayed_live_balance"' in physics
    assert "balance.LegStiffness = 12f" in physics
    assert "balance.MaxSteps = 32" in physics
    assert "balance.MaxBalanceTime = 6.2f" in physics


def test_experimental_systems_are_independent_opt_in_launcher_options():
    config = (ROOT / "src/allin1/config.py").read_text()
    gui = (ROOT / "src/allin1/gui.py").read_text()
    example = (ROOT / "config.example.toml").read_text()
    coordinator = (ROOT / "script/src/PoliceTacticsCoordinator.cs").read_text()
    physics = (ROOT / "script/src/NpcPhysicsExperiment.cs").read_text()
    smoke = (ROOT / "script/src/EnhancedSmokeController.cs").read_text()

    assert "enhanced_police_ai: bool = False" in config
    assert "gta_iv_npc_physics: bool = False" in config
    assert "gta_iv_npc_physics_debug: bool = False" in config
    assert "enhanced_smoke_effects: bool = False" in config
    assert 'f"{boolean(self.script.enhanced_police_ai)}\\n"' in config
    assert 'text="Enhanced Police AI"' in gui
    assert "self.config.script.enhanced_police_ai" in gui
    assert "enhanced_police_ai = false" in example
    assert "gta_iv_npc_physics = false" in example
    assert "gta_iv_npc_physics_debug = false" in example
    assert "enhanced_smoke_effects = false" in example
    assert '"enhanced_police_ai", false' in coordinator
    assert '"gta_iv_npc_physics_debug", false' in physics
    assert '"enhanced_smoke_effects", false' in smoke
    constructor = coordinator[coordinator.index("public PoliceTacticsCoordinator()"):
                              coordinator.index("private void OnTick")]
    assert '"gta_iv_npc_physics", false' not in constructor


def test_offline_launch_experiment_is_culled_from_release_surfaces():
    config = (ROOT / "src/allin1/config.py").read_text()
    gui = (ROOT / "src/allin1/gui.py").read_text()
    manager = (ROOT / "src/allin1/manager.py").read_text()
    policy = (ROOT / "src/allin1/launch_policy.py").read_text()
    example = (ROOT / "config.example.toml").read_text()

    assert "story_mode_only" not in config
    assert "story_mode_only" not in gui
    assert "story_mode_only" not in example
    assert "configure_story_mode_only" not in manager
    assert "_append_argument" not in policy
    assert "_write_state" not in policy
    assert "remove_retired_offline_policy" in manager


def test_gbay_main_menu_uses_clean_rounded_green_header():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "DrawGbayHeader(BROWSER_CX, 0.145f, 0.22f, 0.075f)" in browser
    assert "internal static void DrawRoundedRect(" in renderer
    assert "internal static void DrawGbayHeader(" in renderer
    assert "const int slices = 32" in renderer
    assert "Color highlight" not in renderer
    assert 'DrawText("GBAY"' in renderer
    assert "TextWhite" in renderer


def test_gbay_visual_system_is_shared_across_catalogs_and_workbench():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    gear = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    workbench = (ROOT / "script/src/GbayWeaponCustomization.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()

    for primitive in (
        "DrawElevatedPanel", "DrawCatalogCardSurface", "DrawHeaderAccent",
        "DrawMoneyBadge", "DrawStatusPill", "DrawMenuTile", "DrawEmptyState",
    ):
        assert f"internal static void {primitive}(" in renderer
    assert "CARD_VISUAL_ASPECT = 1.45f" in browser
    assert browser.count("DrawCatalogCardSurface(") >= 2
    assert "GbayPreferences.IsVehicleFavorite(card.Model)" in browser
    assert "GbayPreferences.IsWeaponFavorite(card.WeaponName)" in browser
    assert '"STORY MODE MARKETPLACE"' in browser
    assert "GbayRenderer.DrawMenuTile(" in browser
    assert "GbayRenderer.DrawCatalogCardSurface(" in gear
    assert "GbayRenderer.DrawCatalogCardSurface(" in workbench
    assert "_workbenchRows.Count > WORKBENCH_VISIBLE_ROWS" in workbench
    assert "GbayRenderer.DrawElevatedPanel(" in customize


def test_gbay_vehicle_purchase_chooses_a_destination_without_a_3d_showroom():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()

    assert "VehiclePreview" not in browser
    assert "OpenPreview" not in browser
    assert "World.RenderingCamera" not in browser
    assert "OpenDeliveryConfirm(card.Model, card.Price)" in browser
    assert "CHOOSE DELIVERY LOCATION" in browser
    assert "GARAGE_LOCATION_NAMES" in browser
    assert "GarageAcceptsVehicle" in browser
    assert "GetGarageUsedSlots" in browser
    assert "GetGarageCapacity" in browser
    assert "ExecuteVehicleDelivery(_deliveryGarageIndex)" in browser
    eclipse_delivery = shop[
        shop.index("internal void ExecuteDeliverToGarage"):
        shop.index("internal void ExecuteDeliverToFloorGarage")
    ]
    assert "ExecuteDeliverToFloorGarage(model, price)" not in eclipse_delivery
    assert "too large for the Eclipse Garage" in eclipse_delivery


def test_gbay_world_property_purchase_bypasses_vehicle_delivery():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assets = (ROOT / "script/src/WorldAssetList.cs").read_text()
    yacht = (ROOT / "script/src/YachtManager.cs").read_text()

    assert "WorldAssetList.Special" not in browser
    assert "WorldAssetList.All" in browser
    assert "WorldAssetList.IsWorldAsset(model)" in browser
    assert "DrawWorldAssetModal(input)" in browser
    world_modal = browser[
        browser.index("private void DrawWorldAssetModal"):
        browser.index("//  Garage View")
    ]
    assert "CHOOSE DESTINATION GARAGE" not in world_modal
    assert "ExecutePurchaseWorldAsset" in world_modal
    assert "ExecutePurchaseWorldAsset" in shop
    assert 'SuperYacht = "allin1_super_yacht"' in assets
    assert "CharacterInventory.IsPropertyOwned" in yacht
    assert '"hei_yacht_heist"' in yacht
    assert "Hash.REQUEST_IPL" in yacht
    assert "YachtManager.Initialize();" in shop
    assert "YachtManager.OnTick();" in shop
    assert "RequestWorld();" in yacht
    assert "_nextStreamCheck = Game.GameTime + 1000" in yacht
    assert "YachtStreamingPolicy.ShouldAcquire" in yacht
    assert "StandaloneMapPack.TryActivate(RequiredIpls, 1500)" in yacht
    assert 'private static readonly string[] RequiredIpls' in yacht
    assert "DlcMapState" not in yacht
    assert "_activationBlockedUntilExit" in yacht
    assert '"standalone_map_unavailable"' in yacht
    assert "Hash.SET_INSTANCE_PRIORITY_MODE" not in yacht
    assert "IS_IPL_ACTIVE" in yacht


def test_yacht_helipad_is_a_persistent_specialized_garage():
    helipad = (ROOT / "script/src/GarageManager.Yacht.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    installer = (ROOT / "src/allin1/installer.py").read_text()
    diagnostics = (ROOT / "src/allin1/diagnostics.py").read_text()

    assert "-2043.9200f" in helipad
    assert "-1031.4230f" in helipad
    assert "11.9807f" in helipad
    assert "YACHT_HELIPAD_HEADING = 255.76f" in helipad
    assert 'string.Equals(model, "swift2"' in helipad
    assert 'string.Equals(model, "supervolito2"' in helipad
    assert "YACHT_HELIPAD_SLOT_COUNT = 1" in helipad
    assert '"ALLIN1_yacht_helipad.json"' in helipad
    assert '"Yacht Helipad"' in browser
    assert "ExecuteDeliverToYachtHelipad" in shop
    assert "RemoveYachtHelipadVehicle(listIndex)" in shop
    assert "YachtHelipadUpdateStoredFromLive();" in manager
    assert "YachtHelipadSave();" in manager
    assert "ALLIN1_yacht_helipad.json" in installer
    assert "ALLIN1_yacht_helipad.json" in diagnostics


def test_gbay_delivery_modal_does_not_redraw_browser_behind_text():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    delivery_case = browser[
        browser.index("case BrowserState.DeliveryConfirm"):
        browser.index("case BrowserState.GarageView")
    ]
    renderer = (ROOT / "script/src/GbayRenderer.cs").read_text()
    assert "DrawBrowser" not in delivery_case
    assert "DrawDeliveryModal(input)" in delivery_case
    assert "ModalBg        = Color.FromArgb(255, 255, 255, 255)" in renderer


def test_gbay_sale_modal_does_not_bleed_selected_vehicle_text():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    sale_modal = browser[
        browser.index("private void DrawGarageSellConfirm"):
        browser.index("//  Weapon Browser")
    ]
    assert "DrawGarageView" not in sale_modal
    assert "DrawBorderedRect(BROWSER_CX, 0.5f, MODAL_W, modalH" in sale_modal
    assert "DrawTextFit(name" in sale_modal
    assert '"CONFIRM VEHICLE SALE"' in sale_modal


def test_gbay_my_garage_is_a_scalable_two_pane_browser():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    garage_view = browser[
        browser.index("private void DrawGarageView"):
        browser.index("private void BeginSell")
    ]

    assert 'DrawText("STORAGE"' in garage_view
    assert "_garageLocationScrollOffset" in garage_view
    assert "visibleGarageRows" in garage_view
    assert "visibleVehicleRows" in garage_view
    assert "GetGarageVehicles(_garageLocationIndex)" in garage_view
    assert "_garagePane = 1" in garage_view
    assert "_garagePane = 0" in garage_view


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
        '"LOADING GBAY"', '"VEHICLES"',
        '"CONFIRM VEHICLE SALE"',
    ):
        assert f"DrawTitleBadge(\n                {title}" in browser
    assert '_weaponWorkbenchMode ? "CUSTOMIZE WEAPONS" : "PURCHASE WEAPONS"' in browser
    assert '_harbourListAccessMode ? "BOAT LIST" : "MY GARAGE"' in browser
    assert "DrawTitleBadge(displayName" in browser
    assert "DrawTitleBadge(displayName" in browser
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
    assert "user32.GetSystemMetricsForDpi(11, dpi)" in gui
    assert "user32.SendMessageW(target, 0x0080, 1, icon_big)" in gui
    assert "user32.SendMessageW(target, 0x0080, 2, icon_small)" in gui
    assert gui.index("_register_windows_app()") < gui.rindex("root = tk.Tk()")
    assert 'allin1 = ["assets/*.png", "assets/*.ico"]' in project


def test_floor_garage_drive_in_is_visible_and_markers_match_character():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "System.Drawing.Color.FromArgb(128, 200, 100, 0)" not in garage
    assert garage.count("var markerColor = CharacterMarkerColor();") >= 3
    assert '"Eclipse Garage"' in browser
    assert '"Harmony Garage"' in browser
    assert "GetFloorGarageStoredVehicles()" in browser
    assert "visibleVehicleRows = 11" in browser
    assert "_garageLocationScrollOffset" in browser
    assert "_garagePane" in browser
    assert "input.ScrollDelta" in browser
    assert "_pendingSellGarageLocation" in browser
    assert "RemoveFloorGarageVehicle(listIndex)" in shop
    assert "private static bool FloorGarageSave()" in garage
    entry = garage[garage.index("private static void EnterFloorGarageCore"):
                   garage.index("private static void LeaveFloorGarage()")]
    ready = entry.index("CompleteGarageBlackTransition(")
    confirmation = entry.index("ShowSubtitle(storedConfirmation", ready)
    assert confirmation > ready


def test_gbay_gear_store_is_reachable_and_uses_captured_previews():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    gear_browser = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert '"Vehicles", "Purchase Weapons", "Customize Weapons"' in browser
    assert '"Gear", "My Garage", "Diagnostics", "About"' in browser
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
    assert "CharacterInventory.RemoveOwnedGear" in shop
    assert "Repurchase it to equip it again" in shop


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


def test_harmony_blips_are_not_suppressed_by_recovery_mode():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    helper = garage[
        garage.index("internal static void EnsureFloorGarageBlips()"):
        garage.index("internal static int GetFloorThemeChoice")
    ]
    assert "_floorGarageEntranceBlip == null" in helper
    assert "_floorGaragePedBlip == null" in helper
    assert '"ALLIN1 Harmony Garage (Vehicle)"' in helper
    assert '"ALLIN1 Harmony Garage (Pedestrian)"' in helper
    initialize = shop[
        shop.index("GarageManager.InitializeYachtHelipad();"):
        shop.index("Log(\"GarageManager base initialization completed\")")
    ]
    assert initialize.index("GarageManager.EnsureFloorGarageBlips();") < \
        initialize.index("if (!ClientWatchdog.SafeMode)")
    floor_init = garage[
        garage.index("internal static void InitializeFloorGarage()"):
        garage.index("internal static int GetFloorGarageUsedSlots()")
    ]
    assert "EnsureFloorGarageBlips();" in floor_init


def test_gbay_control_legends_are_high_contrast_and_shared_across_pages():
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    gear_browser = (ROOT / "script/src/GbayBrowser.Gear.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    assert "private static void DrawControlHint(" in browser
    assert "GbayRenderer.BtnGreen" in browser
    assert "GbayRenderer.TextWhite" in browser
    assert "0.31f, 0.235f" in browser
    # The retired 3D showroom supplied one former control legend.
    workbench = (ROOT / "script/src/GbayWeaponCustomization.cs").read_text()
    assert browser.count("DrawControlHint(") + workbench.count("DrawControlHint(") >= 5
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
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
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
    assert definitions.count("blockStoryOwnedVehicles: true") == 6
    assert "rules.BlockStoryOwnedVehicles && storyOwnedVehicle" in definitions
    assert "IsPersonalVehicle(vehicle);" in manager
    assert "RejectGarageEntry(\n                        ECLIPSE_GARAGE, rideIn" in manager
    assert "RejectGarageEntry(\n                        THREE_FLOOR_GARAGE, rideIn" in manager
    assert "RejectGarageEntry(\n                        DAVIS_GARAGE, rideIn" in davis
    assert "RejectGarageEntry(\n                        PALETO_GARAGE, rideIn" in paleto
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
    assert '"tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"' in garage
    assert "DAVIS_INTERIOR_LOAD_TIMEOUT_MS" in garage
    assert "Hash.SET_FOCUS_POS_AND_VEL" in garage
    assert "Hash.IS_INTERIOR_READY" in garage
    assert "GarageInteriorReadinessPolicy.IsUsable" in garage
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
    assert '"Eclipse Garage"' in browser
    assert '"Harmony Garage"' in browser
    assert '"Davis Auto Shop"' in browser
    assert '"Garment Factory"' in browser
    assert '"Grapeseed Garage"' in browser
    assert '"Paleto Bay Garage"' in browser
    assert "GetDavisGarageStoredVehicles()" in browser
    assert "ExecuteDeliverToDavisGarage" in shop
    assert "RemoveDavisGarageVehicle(listIndex)" in shop
    assert "PlaceVehicleInParkingSpace" in manager
    assert "GET_MODEL_DIMENSIONS" in manager
    assert "maxCorrection = 1.25f" in manager


def test_legacy_garages_use_finished_harmony_sets_and_model_aware_placement():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    customize = (ROOT / "script/src/GbayBrowserCustomize.cs").read_text()
    assert manager.count("PlaceVehicleInParkingSpace(") >= 5
    assert '"Eclipse"' in manager and '"ThreeFloor", 2.0f' in manager
    assert "GetGarageSizeTier" in manager
    assert "width > 3.4f || length > 8.5f" in manager
    assert "GET_MODEL_DIMENSIONS" in manager
    assert 'new[] { "int02_ba_floor01", "int02_ba_floor02", "int02_ba_floor03",' in manager
    assert '"int02_ba_floor04", "int02_ba_floor05"' in manager
    assert '"int02_ba_sec_upgrade_grg"' in manager
    assert '"int02_ba_equipment_upgrade"' in manager
    assert '"int02_ba_sec_desks_l1", "int02_ba_sec_desks_l2345"' in manager
    assert '"int02_ba_clutterstuff"' in manager
    for invalid_set in (
        "Int02_ba_Style01", "Int02_ba_walls_01",
        "Int02_ba_decor_01", "Int02_ba_trad_lights",
    ):
        assert invalid_set not in manager
    apply_sets = manager[manager.index("private static bool ApplyFloorEntitySets"):]
    assert apply_sets.index("DEACTIVATE_INTERIOR_ENTITY_SET") < apply_sets.index(
        "ACTIVATE_INTERIOR_ENTITY_SET")
    assert "FLOOR_GARAGE_FIXED_ENTITY_SETS" in apply_sets
    assert '"int02_ba_sec_upgrade_grg"' in manager
    assert '"int02_ba_equipment_upgrade"' in manager
    assert '"int02_ba_clutterstuff"' in manager
    assert '? "int02_ba_sec_desks_l1"' in apply_sets
    assert '"int02_ba_deskpc"' in manager
    assert '"int02_ba_sec_upgrade_strg"' in manager
    assert '"int02_ba_sec_upgrade_desk"' in manager
    assert '"int02_ba_sec_upgrade_desk02"' in manager
    assert "0x35F7DD45E8C0A16D" in apply_sets
    assert "FLOOR_GARAGE_ENTITY_SET_SETTLE_MS" in apply_sets
    assert "ValidateFloorEntitySets" in apply_sets
    assert "WaitForFloorGaragePlayerInterior" in manager
    assert "Hash.GET_ROOM_KEY_FROM_ENTITY" in manager
    assert "Hash.GET_ROOM_KEY_FOR_GAME_VIEWPORT" in manager
    assert "Hash.IS_COLLISION_MARKED_OUTSIDE" in manager
    assert "GarageRoomAttachmentPolicy.IsAttached" in manager
    assert "new Vector3(-1507.721f, -3011.700f, -80.2419f)" in manager
    assert "post-teleport interior=" in manager
    assert 'BeginGarageBlackTransition("SwitchFloorGarageFloor")' in manager[
        manager.index("private static void SwitchFloorGarageFloor"):]
    assert "private const int FLOOR_GARAGE_FLOOR_COUNT = 5" in manager
    assert "FLOOR_GARAGE_FLOOR_COUNT * FLOOR_GARAGE_SLOTS_PER_FLOOR" in manager
    assert "BuildFloorGarageSlots()" in manager
    assert '"Floor 4", "Floor 5", "Exit Garage"' in manager
    assert 'F{sv.Slot / 5 + 1}-{sv.Slot % 5 + 1}' in browser
    assert '"Fixed Interior"' in browser
    assert "bool customizationAvailable = !SpecializedListAccessMode &&" in browser
    assert "_garageLocationIndex == 2" in browser
    assert "if (!davisGarage)" in customize
    assert manager.count("new ParkingSlot(-1517.0f") == 5
    assert manager.count("-80.2422f)") == 5


def test_all_garage_transitions_hold_black_until_destination_is_ready():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()

    assert "private static void BeginGarageBlackTransition" in manager
    assert "private static void CompleteGarageBlackTransition" in manager
    assert "Hash.IS_SCREEN_FADED_OUT" in manager
    assert "GARAGE_DESTINATION_STABLE_MS" in manager
    assert "Hash.HAS_COLLISION_LOADED_AROUND_ENTITY" in manager
    assert "AreGarageVehiclesReady" in manager

    expected = {
        manager: ("EnterGarage", "LeaveGarage",
                  "EnterFloorGarage", "LeaveFloorGarage",
                  "SwitchFloorGarageFloor"),
        davis: ("EnterDavisGarage", "LeaveDavisGarage"),
        garment: ("EnterGarmentGarage", "LeaveGarmentGarage"),
        rural: ("EnterRuralGarage", "LeaveRuralGarage"),
        paleto: ("EnterPaletoGarage", "LeavePaletoGarage"),
    }
    for source, transitions in expected.items():
        for transition in transitions:
            assert f'BeginGarageBlackTransition("{transition}")' in source
            assert f'"{transition}", player' in source


def test_garment_factory_uses_native_ten_car_layout_and_shared_grounding():
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    placement = (ROOT / "script/src/VehiclePlacementMath.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    assert "new Vector3(762.1525f, -899.2333f, 25.1761f)" in garment
    assert "new Vector3(760.7663f, -909.4583f, 25.2538f)" in garment
    assert "new Vector3(751.0350f, -975.4493f, -67.5536f)" in garment
    assert "GARMENT_INTERIOR_PED_HEADING = 180f" in garment
    assert "GARMENT_VEHICLE_ENTRANCE_HEADING = 270f" in garment
    assert "GARMENT_PED_ENTRANCE_HEADING = 270f" in garment
    assert "m24_2_int_placement_interior_int_hacker_garage_milo_" in garment
    assert garment.count("new ParkingSlot(") == 10
    assert "slot.Position.Y += stored.Slot <= 4 ? 0.8f : -0.8f" in garment
    assert '"ALLIN1_garment_factory_garage.json"' in garment
    assert "ExecuteDeliverToGarmentGarage" in shop
    assert "RemoveGarmentGarageVehicle(listIndex)" in shop
    assert '"Garment Factory"' in browser
    assert "TryProbeParkingFloor" in manager
    assert "World.Raycast" in manager
    assert "CalculateRootZ" in placement


def test_garage_settle_correction_sets_the_exact_entity_root():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    start = manager.index("if (corrected)")
    placement = manager[start:manager.index("Log($\"PlaceVehicleInParkingSpace", start)]

    assert "SET_ENTITY_COORDS_NO_OFFSET" in placement
    assert "SET_ENTITY_COORDS, vehicle" not in placement
    assert "GetSpawnDeltaZ" not in manager
    parking = manager[
        manager.index("private static void PlaceVehicleInParkingSpace"):
        manager.index("private static void ReleaseGarageVehicleForDriving")
    ]
    assert "SET_VEHICLE_ON_GROUND_PROPERLY" not in parking
    assert "NeedsSettledRootCorrection" in parking
    assert "vehicle.IsPositionFrozen = true" in parking


def test_every_garage_vehicle_exit_restores_full_drivability():
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    start = manager.index("private static void ReleaseGarageVehicleForDriving")
    helper = manager[start:manager.index("private static bool TryProbeParkingFloor", start)]

    for operation in (
        "SET_FOCUS_POS_AND_VEL",
        "REQUEST_COLLISION_AT_COORD",
        "HAS_COLLISION_LOADED_AROUND_ENTITY",
        "SET_VEHICLE_HANDBRAKE",
        "SET_VEHICLE_UNDRIVEABLE",
        "FREEZE_ENTITY_POSITION",
        "SET_ENTITY_DYNAMIC",
        "ACTIVATE_PHYSICS",
        "SET_VEHICLE_ON_GROUND_PROPERLY",
        "SET_VEHICLE_ENGINE_ON",
        "CLEAR_FOCUS",
    ):
        assert operation in helper
    assert helper.index("SET_VEHICLE_HANDBRAKE") < helper.index("ACTIVATE_PHYSICS")
    assert helper.index("HAS_COLLISION_LOADED_AROUND_ENTITY") < helper.index(
        "FREEZE_ENTITY_POSITION"
    )
    assert manager.count("ReleaseGarageVehicleForDriving(") == 3  # helper + Eclipse + Harmony
    assert "ReleaseGarageVehicleForDriving(playerVehicle" in davis
    assert "ReleaseGarageVehicleForDriving(playerVehicle" in garment
    assert "ReleaseGarageVehicleForDriving(playerVehicle" in rural
    assert "ReleaseGarageVehicleForDriving(playerVehicle" in paleto

    davis_leave = davis[
        davis.index("private static void LeaveDavisGarageCore"):
        davis.index("private static bool LoadDavisAutoShopInterior")
    ]
    garment_leave = garment[
        garment.index("private static void LeaveGarmentGarageCore"):
        garment.index("private static bool LoadGarmentInterior")
    ]
    paleto_leave = paleto[
        paleto.index("private static void LeavePaletoGarageCore"):
        paleto.index("private static bool LoadPaletoInterior")
    ]
    harmony_leave = manager[
        manager.index("private static void LeaveFloorGarageCore"):
        manager.index("//  Floor Garage Helpers")
    ]
    for leave, unload in (
        (davis_leave, "UnloadDavisAutoShopInterior"),
        (garment_leave, "UnloadGarmentInterior"),
        (paleto_leave, "UnloadPaletoInterior"),
        (harmony_leave, "UnloadFloorGarageInterior"),
    ):
        assert leave.index(unload) < leave.index(
            "ReleaseGarageVehicleForDriving(playerVehicle"
        )


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
    controller_source = (ROOT / "script/src/ControllerBindings.cs").read_text()
    assert "FrontendY" in controller_source and "FrontendX" in controller_source


def test_physics_experiment_has_observable_runtime_and_safe_archive_tooling():
    physics = (ROOT / "script/src/NpcPhysicsExperiment.cs").read_text()
    workbench = (ROOT / "script/src/GbayWeaponCustomization.cs").read_text()
    diagnostics = (ROOT / "script/src/PhysicsExperimentLog.cs").read_text()
    patcher = (ROOT / "tools/RpfPatcher/Program.cs").read_text()
    assert "PhysicsExperimentLog.Step" in physics
    assert '"reaction_observation"' in physics
    assert '"heartbeat"' in physics
    assert "IS_ENTITY_TOUCHING_ENTITY" in physics
    assert "ShouldForceVehicleImpactRagdoll" in physics
    assert '"vehicle_push_vanilla_preserved"' in physics
    assert '"vehicle_native_reaction_observed"' in physics
    assert 'fields["natural_motion_dispatched"] = false' in physics
    assert "private Ped _workbenchDummy" in workbench
    assert "player.Clone(_workbenchPreviousHeading)" in workbench
    assert "SET_LOCAL_PLAYER_INVISIBLE_LOCALLY" in workbench
    assert "DeleteWeaponWorkbenchDummy" in workbench
    assert "state.WasAlive = true;" in physics
    assert "Enum.GetValues(typeof(ExplosionType))" in physics
    assert "ScriptDirectory =\n            AppDomain.CurrentDomain.BaseDirectory" in physics
    assert "PhysicsExperimentLog.Configure(_debug)" in physics
    assert "Assembly.Location" not in diagnostics
    assert "MaxBytes" in diagnostics and "RotateIfNeeded" in diagnostics
    assert 'command == "validate-euphoria"' in patcher
    assert "createModsCopy" in patcher
    assert "IsGtaProcessRunning()" in patcher
    assert "RPF post-conversion scan returned no entries" in patcher
    assert "RPF reopened:" in patcher
    assert "Archive-relative entry is ambiguous" in patcher
    install = patcher[patcher.index("static int InstallEuphoria"):
                      patcher.index("static int VerifyEuphoria")]
    assert install.index("EnsureEuphoriaBackup") < install.index(
        "tuningWritesStarted = true"
    )
    assert "TryRollbackEuphoriaInstall" in install
    assert "VerifyEuphoriaMarker" in patcher
    assert 'command == "install-smoke-tuning"' in patcher
    assert 'command == "verify-smoke-tuning"' in patcher
    assert 'command == "remove-smoke-tuning"' in patcher
    assert 'command == "install-colored-smoke-weapons"' in patcher
    assert 'command == "build-colored-smoke-weapons"' in patcher
    assert 'command == "verify-colored-smoke-weapons"' in patcher
    assert 'command == "remove-colored-smoke-weapons"' in patcher
    assert 'command == "build-merged-smoke-canary"' in patcher
    assert 'command == "install-merged-smoke-canary"' in patcher
    assert 'command == "verify-merged-smoke-canary"' in patcher
    assert 'command == "remove-merged-smoke-canary"' in patcher
    assert 'command == "build-merged-smoke-weapons"' in patcher
    assert 'command == "install-merged-smoke-weapons"' in patcher
    assert 'command == "verify-merged-smoke-weapons"' in patcher
    assert 'command == "remove-merged-smoke-weapons"' in patcher
    assert "base_weapons_meta_merge" in patcher
    assert 'ValidateMergedSmokeWeaponMeta(current, installed, 1)' in patcher
    assert "BuildMergedSmokeWeaponAnimationsMeta" in patcher
    assert "ValidateMergedSmokeWeaponAnimationsMeta" in patcher
    assert "BaseWeaponAnimationsMetaPath" in patcher
    assert '"WEAPON_SMOKEGRENADE"' in patcher
    assert 'clone.SetAttributeValue(\n                        "key", ColoredSmokeWeapons[index].WeaponName)' in patcher
    assert "ValidateMergedSmokeArchiveSnapshot(\n                    gtaPath, original, originalAnimations, originalLanguage," in patcher
    assert "BaseAmericanLanguageArchivePath" in patcher
    assert "BuildMergedSmokeLanguageArchive" in patcher
    assert "BaseScaleformGenericArchivePath" in patcher
    assert "BuildMergedSmokeHudArchive" in patcher
    assert "PatchSmokeHudGfx" in patcher
    assert 'const string bzGasLabel = "INT-1600701090"' in patcher
    assert 'SetElementValue(item, "StatName",' in patcher
    assert '"A1SM" + spec.Color.ToUpperInvariant())' in patcher
    assert 'SetAttributeValue("value", "5")' in patcher
    assert "installed_animations_sha256" in patcher
    assert '"full_pending"' in patcher
    assert 'CreateMergedSmokeArchiveSnapshot(modsRpf, gtaPath)' in patcher
    assert 'RestoreMergedSmokeArchiveSnapshot(gtaPath)' in patcher
    assert '{ "allin1_smoke", "dlcpacks:/allin1_smoke/" }' in patcher
    assert 'WeaponName = "WEAPON_ALLIN1_SMOKE_" + suffix' in patcher
    assert 'AmmoName = "AMMO_ALLIN1_SMOKE_" + suffix' in patcher
    assert 'Gxt2File.FromText' in patcher
    assert 'new XAttribute("value", 451 + index)' in patcher
    assert 'new XAttribute("value", 401 + index)' in patcher
    assert 'new XAttribute("value", "58")' in patcher
    assert 'new XAttribute("value", "0")' in patcher
    assert '"dlc_allin1_smokeCRC:/common/data/ai/weaponAllin1Smoke.meta"' in patcher
    assert '"dlc_allin1_smokeCRC:/common/data/shop_weapon.meta"' in patcher
    assert '"WEAPON_SHOP_INFO_METADATA_FILE"' in patcher
    assert 'BuildColoredSmokeShopMeta()' in patcher
    assert 'new XElement("nameHash", spec.WeaponName)' in patcher
    assert 'shopItems.Length != ColoredSmokeWeapons.Length' in patcher
    assert '"Invalid shop registration for {spec.Color} smoke."' in patcher
    assert '"contentChangeSets", "contentChangeSetGroups"' in patcher
    assert '"startupScript", "scriptCallstackSize", "type", "order"' in patcher
    assert '"minorOrder", "isLevelPack", "dependencyPackHash"' in patcher
    assert '"Colored smoke setup2.xml does not match the required positional SSetupData schema."' in patcher
    assert 'SmokeExplosionTag = "EXP_TAG_SMOKEGRENADE"' in patcher
    assert 'SmokeVfxTag = "EXP_VFXTAG_SMOKE_GRENADE"' in patcher
    assert '"bAppliesContinuousDamage", false' in patcher
    assert '"bNoOcclusion", true' in patcher
    assert "Do not call PsoFile.Save here" in patcher
    assert 'SmokeExplosionFxPath' in patcher
    smoke = patcher[patcher.index("static int InstallSmokeTuning"):
                    patcher.index("static int VerifySmokeTuning")]
    assert smoke.index("EnsureSmokeBackup") < smoke.index(
        "writesStarted = true"
    )
    assert "RestoreSmokeBackup" in smoke
    remove = patcher[patcher.index("static int RemoveEuphoria"):
                     patcher.index("static bool TryLoadEuphoriaPayload")]
    assert remove.index("restore.Add") < remove.index(
        "File.Copy(backup, target, true)"
    )


def test_enhanced_smoke_uses_independent_weapons_and_grounded_deployment():
    controller = (ROOT / "script/src/EnhancedSmokeController.cs").read_text()
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    catalog = (ROOT / "script/src/SmokeGrenadeCatalog.cs").read_text()

    assert "Control.Reload" not in controller
    assert "ALLIN1_colored_smoke_merged_canary.json" in controller
    assert "0x32CA01C3UL" not in controller
    assert "RegisterWeaponWheelLabels" not in controller
    assert "colored_smoke_weapon_sync_failed" in inventory
    assert "colored_smoke_purchase_grant_failed" in inventory
    assert "colored_smoke_equip_attempt" in inventory
    assert "SET_CURRENT_PED_WEAPON" in inventory
    assert "TryGetByWeaponHash" in controller
    assert "TryConsumeSmokeColor" in controller
    assert "!isInAir && hasCollided" in controller
    assert '"enhanced_smoke_projectile_motion"' in controller
    assert '"enhanced_smoke_projectile_settled"' in controller
    assert '"enhanced_smoke_projectile_expired_unsettled"' in controller
    assert "SET_PARTICLE_FX_NON_LOOPED_COLOUR" in controller
    assert controller.index("SET_PARTICLE_FX_NON_LOOPED_COLOUR") < controller.index(
        "START_PARTICLE_FX_NON_LOOPED_AT_COORD"
    )
    assert "ShouldUsePrimaryLoop" in controller
    assert "CanUseNativeFallback" in controller
    assert "WEAPON_ALLIN1_SMOKE_" in catalog
    assert "AMMO_ALLIN1_SMOKE_" in catalog
    assert "GET_NUM_DLC_WEAPONS" in catalog
    assert "GET_DLC_WEAPON_DATA" in catalog
    assert "DlcWeaponHashOffset = 8" in catalog
    assert "1, false, true" in inventory
    assert '"registered_custom_weapon_types"' in controller
    assert "RemoveInvalidWeaponsInMemory" in inventory
    assert '"invalid_managed_weapons_cleaned"' in inventory
    assert '"staged_smoke_stock_preserved"' in inventory
    assert '"registration_mode", registeredWeapons ==' in inventory
    assert '"registration_required", false' in inventory
    assert "availableWeapons == SmokeGrenadeCatalog.Products.Length" in inventory
    assert "TryConsumeSmokeColorInMemory" in inventory
    assert "Hash.REMOVE_WEAPON_FROM_PED" in inventory
    assert "SmokeGrenadeCatalog.NativeWeaponName" in inventory


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


def test_rpf_toolchain_pins_enhanced_aware_codewalker_authoring_core():
    tools_script = (ROOT / "runtools.ps1").read_text(encoding="utf-8")
    modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "https://github.com/crxhvrd/CodeWalkerProjects.git" in tools_script
    assert "0bf552913d96da9ad1f266eb5c7d6d75b96c89f2" in tools_script
    assert "checkout --detach --force $CwCommit" in tools_script
    assert "-or -not (Test-Path $CwCorePath)" in tools_script
    assert "https://github.com/crxhvrd/CodeWalkerProjects.git" in modules


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
