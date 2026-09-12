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


def _assert_removal_preserves_save(name, tmp_path, monkeypatch):
    """Check persistence behavior, not membership in an old deletion list."""
    from allin1 import installer
    from allin1.config import Config
    game = tmp_path / "synthetic game"
    scripts = game / "scripts"
    scripts.mkdir(parents=True)
    saved = scripts / name
    backup = scripts / (name + ".bak")
    saved.write_bytes(b'{"vehicle":"saved"}')
    backup.write_bytes(b'{"vehicle":"previous save"}')
    client = scripts / "ALLIN1.dll"
    client.write_bytes(b"inert fixture; never executed")
    monkeypatch.setattr(installer, "resolve_gta_path", lambda _: game)
    # No real RPF fixtures or game installation are used by this contract.
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", lambda *a, **kw: None)
    monkeypatch.setattr(installer, "_remove_preview_ytds", lambda *a, **kw: None)
    installer.uninstall(Config.default())
    assert not client.exists()
    assert saved.read_bytes() == b'{"vehicle":"saved"}'
    assert backup.read_bytes() == b'{"vehicle":"previous save"}'


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


def test_legacy_world_asset_source_is_preserved_but_not_repackaged():
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
    assert "def _deploy_preview_dlc(" not in installer
    assert '"world_asset_previews"' in installer


def test_generated_csharp_contains_every_data_model():
    source = (ROOT / "script/src/VehicleList.cs").read_text()
    for vehicle in VehicleDatabase.load(ROOT / "data/vehicles.toml"):
        assert f'"{vehicle.model}"' in source


def test_production_project_includes_only_supported_developer_tools():
    project = (ROOT / "script/ALLIN1.csproj").read_text()
    assert '<Compile Remove="tools\\**" />' in project
    assert '<Compile Include="tools\\VehicleGroundingTool.cs" />' not in project
    assert '<Compile Include="tools\\SeatTestTool.cs" />' not in project
    assert project.count('<Compile Include="tools\\') == 0
    assert not (ROOT / "script/tools/WorldVectorTool.cs").exists()
    assert not (ROOT / "script/src/GarageTraversalLab.cs").exists()
    assert not (ROOT / "script/tests/GarageTraversalLabPolicyTests.cs").exists()


def test_prebuilt_runtime_artifacts_are_present_and_nonempty():
    for relative in (
        "script/dist/ALLIN1.dll",
        "script/dist/ALLIN1.ReactorBridge.plugin",
    ):
        artifact = ROOT / relative
        assert artifact.stat().st_size > 1024


def test_runtime_distribution_contains_only_the_core_dll():
    assert sorted(
        path.name for path in (ROOT / "script/dist").glob("*.dll")
    ) == ["ALLIN1.dll"]


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
        arguments = "transition" if operation == "EnterFloorGarage" else ""
        assert f"{operation}Core({arguments});" in garage
        assert f'EndTransition("{operation}")' in garage
    assert "RecoverTransition(" in garage
    assert "TryRecoverTransitionCleanup(" in garage
    recover = garage[
        garage.index("private static void RecoverTransition"):
        garage.index("private static void EndTransition")
    ]
    assert recover.count("TryRecoverTransitionCleanup(") == 6
    for operation in (
        "UnloadFloorGarageInterior", "UnloadDavisAutoShopInterior",
        "UnloadGarmentInterior", "UnloadRuralInterior",
        "UnloadPaletoInterior",
    ):
        assert operation in recover
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
    aborted = garage[
        garage.index("internal static void OnScriptAborted()"):
        garage.index("private static void PersistVehiclesForStorySave")
    ]
    assert "finally" in aborted
    assert "DeferredMapContentRuntime.OnScriptAborted();" in aborted
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


def test_installer_and_seat_selector_contracts():
    installer = (ROOT / "src/allin1/installer.py").read_text()
    seat = (ROOT / "script/src/SeatSelector.cs").read_text()
    assert "def _deploy_preview_dlc(" not in installer
    assert "def _deploy_reactor_catalog_artwork(" not in installer
    assert '"weapon_previews"' in installer
    assert '"equipment_previews"' in installer
    assert "RETIRED_DEVELOPER_ARTIFACTS" in installer
    assert "ALLIN1_height_check.toml" in installer
    assert "RETIRED_DEVELOPER_DIRECTORIES" in installer
    assert "ALLIN1_seat_tests" in installer
    assert "ALLIN1.dll.pre-seat-nav-fix.bak" in installer
    assert "Removed retired developer artifact" in installer
    assert "IsSelectorHeld" in seat
    assert "That seat is no longer available" in seat
    assert "seat_selector_enabled" in seat
    assert "seat_selector_key" in seat
    assert "FindNavigationTarget" in seat
    assert "GetSeatEnumerationPassengerLimit" in seat
    assert "Sparse authored layouts" in seat


def test_temporary_f11_axle_harness_is_retired():
    assert not (ROOT / "script/src/AxleTestHarness.cs").exists()
    assert not (ROOT / "script/tests/AxleTestHarnessPolicyTests.cs").exists()

    current_surfaces = "\n".join(
        (ROOT / path).read_text()
        for path in (
            "config.example.toml",
            "src/allin1/config.py",
            "desktop/src/App.tsx",
            "content/allin1-experimental-gameplay/allin1.content.json",
        )
    )
    assert "axle_test_harness" not in current_surfaces
    assert "vehicle-axle-test" not in current_surfaces
    assert "vehicles.axle-testing" not in current_surfaces


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
    assert 'ClientLog.Info("Traffic", "replacement_source_changed_before_commit"' in traffic
    assert '"validation_outcome"' in traffic
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


def test_gbay_requires_reactor_and_garage_services_stay_independent():
    shop = (ROOT / "script/src/GbayShop.cs").read_text(encoding="utf-8")
    assert "GbayUiBackend" not in shop
    assert "_menuEnabled" not in shop
    assert "TryInitializeReactorBridge" in shop
    assert '"reactor_fallback_to_legacy"' not in shop
    assert "ShowReactorUnavailable();" in shop
    assert "EnsureBrowser().Toggle()" not in shop
    assert "_browser.Draw()" not in shop
    assert "_browser.TickReactorWeaponPreview()" in shop
    assert "if (_initialized && _onlineContentEnabled)" in shop
    assert "GarageManager.OnTick();" in shop
    assert "if (e.KeyCode == _openKey)" in shop
    # World markers now route through the same typed Reactor handoff as the
    # rest of the garage UI. No native menu fallback is allowed.
    assert "GarageManager.ConsumeHelipadListRequest()" in shop
    assert "Allin1GarageWorldEntryLocation.VespucciHelipad" in shop
    assert "EnsureBrowser().OpenHelipadList()" not in shop
    assert "GarageManager.ConsumeHarbourListRequest()" in shop
    assert "Allin1GarageWorldEntryLocation.Harbour" in shop
    assert "EnsureBrowser().OpenHarbourList()" not in shop


def test_reactor_bridge_keeps_allin1_authoritative_and_server_pages_catalog():
    contracts = (ROOT / "script/src/GbayReactorContracts.cs").read_text(
        encoding="utf-8"
    )
    bridge = (
        ROOT / "script/reactor-bridge/Allin1ReactorBridge.cs"
    ).read_text(encoding="utf-8")
    project = (
        ROOT / "script/reactor-bridge/ALLIN1.ReactorBridge.csproj"
    ).read_text(encoding="utf-8")
    assert "IAllin1VehicleStorefront" in contracts
    assert "MaximumPageSize = 12" in contracts
    assert "ValidateVehiclePurchase(model, request.QuotedPrice)" in contracts
    assert "ConfirmVehicleDelivery" in contracts
    assert "BuildDeliveryOptions(model)" in contracts
    assert "DestinationCompatible" in contracts
    assert "ExecuteDeliverToFloorGarage(model, request.QuotedPrice)" in contracts
    assert "using ReactorV" not in contracts
    assert "ReactorV.Integration" not in contracts
    assert 'ExtensionId = "allin1.gbay"' in bridge
    assert 'HomeMenuId = "home"' in bridge
    assert '"Purchase Weapons"' in bridge
    assert '"Customize Weapons"' in bridge
    assert '"My Garage"' in bridge
    assert '"vehicle.checkout"' in bridge
    assert '"vehicle.delivery.confirm"' in bridge
    assert '"weapon.purchase"' in bridge
    assert '"gear.apply"' in bridge
    assert '"garage.sell"' in bridge
    assert '"garage.retrieve"' in bridge
    assert '"quotedprice"' in bridge
    assert '["presentation"] = "refresh"' in bridge
    assert '["menuRevision"] = RevisionText()' in bridge
    assert "TryPresentMenu(HomeMenuId, context)" in bridge
    assert "IsMenuPresented(HomeMenuId)" in bridge
    assert "TryDismissMenu(HomeMenuId)" in bridge
    assert "_request.RefreshCatalog = true" not in bridge
    assert "IAllin1GameStateBridge" in bridge
    assert "TrySynchronizeGameStateCore" in bridge
    assert "No catalog scan, menu rebuild, or native UI handoff" in bridge
    assert '"legacyDeliveryModal"' not in bridge
    garage_builder = bridge[
        bridge.index("private ReactorMenuDescriptor BuildGarageMenu"):
        bridge.index("private void AddGarageInteriorNodes")
    ]
    assert "GaragePageSize" not in garage_builder
    assert "ReactorPaginationNode" not in garage_builder
    assert "foreach (Allin1GarageVehicleListing value in filtered)" in garage_builder
    assert '"CUSTOMIZE WEAPONS"' in bridge
    assert '"weapon.customize.apply"' in bridge
    assert "BrowseCustomizableWeapons" in contracts
    assert "BrowseWeaponCustomization" in contracts
    assert "ApplyWeaponCustomization" in contracts
    assert "ReactorActionRisk.Persistent" in bridge
    assert "AvailabilityStatus" in contracts
    assert "Hash.IS_WEAPON_VALID" in contracts
    assert "SmokeGrenadeCatalog.AvailableCustomWeaponCount()" in contracts
    assert "countBeforeSale" in contracts
    assert "GTA did not confirm the gear change" in contracts
    assert 'Private="false"' in project


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
    extension_runtime = (ROOT / "script/src/ExtensionRuntime.cs").read_text()
    assert "bool hasSavedWeapons = inventory.weapons.Count > 0" in inventory
    assert "inventory.equipped_gear.Count == 0 && !hasSavedWeapons" in inventory
    apply_start = inventory.index("private void Apply(string character)")
    grant = inventory.index("RestoreWeapons(ped, inventory, inventory.weapons)", apply_start)
    # Persistence can now load off-game without eagerly invoking ScriptHookV.
    # Keep the same restore-before-removal assertion on the lazy hash table.
    assert "Lazy<Dictionary<string, int>> WeaponHashes" in inventory
    weapon_loop = inventory.index("foreach (var entry in WeaponHashes.Value)", apply_start)
    managed_remove = inventory.index("if (!owned.Contains(entry.Key) && inventory.managed)", weapon_loop)
    remove = inventory.index("REMOVE_WEAPON_FROM_PED", managed_remove)
    assert grant < weapon_loop < managed_remove < remove
    assert "RuntimeWeaponCatalog.Refresh();" in inventory[apply_start:grant]
    assert "WeaponLoadoutRestore.Restore(inventory, candidates, RuntimeWeaponCatalog.All" in inventory
    assert "CleanupInvalidSavedWeapons(character, ped, inventory)" not in inventory
    assert "RetryDeferredWeapons(character)" in inventory
    assert "_weaponRestoreRetries >= 5" in inventory
    assert '"weapons", restored.Restored.Count' in inventory
    restore = inventory[inventory.index("private static WeaponRestoreResult RestoreWeapons"):]
    assert restore.index("Hash.GIVE_WEAPON_TO_PED") < restore.index("Hash.HAS_PED_GOT_WEAPON") < restore.index("Hash.SET_PED_AMMO")
    assert "Game.IsLoading" in inventory
    assert "_restorePending" in inventory
    assert "player.IsDead" in inventory
    assert "player.Handle == _lastPedHandle" in inventory
    assert '"managed", inventory.managed' in inventory
    assert "IS_AUTO_SAVE_IN_PROGRESS" in inventory
    assert "CaptureWeaponAmmo(character, player, \"story_save_started\")" in inventory
    assert "CreateActiveScope(documents, scripts)" in extension_runtime
    assert "SaveGameFolderForScripts" in extension_runtime
    assert 'profileDirectory, "SGTA5*", SearchOption.TopDirectoryOnly' in extension_runtime
    assert 'new[] { "GTA V", "GTAV Enhanced" }' not in extension_runtime
    assert '"SGTA5*", SearchOption.AllDirectories' not in extension_runtime
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


def test_character_death_consumes_gear_without_bypassing_story_save():
    inventory = (ROOT / "script/src/CharacterInventory.cs").read_text()
    handler = inventory[
        inventory.index("private void HandlePlayerDeath"):
        inventory.index("private void CompleteDeathCleanup")
    ]
    helper = inventory[
        inventory.index(
            "internal static List<string> ConsumeAllGearAfterDeathInMemory"):
        inventory.index("private static bool ContainsIgnoreCase")
    ]

    assert "ConsumeAllGearAfterDeathInMemory(inventory)" in handler
    assert 'StageStateLocked(_deathCharacter,' in handler
    assert '"gear_lost_on_death"' in handler
    assert "SaveStateLocked" not in handler
    assert "inventory.gear = new List<string>();" in helper
    assert "inventory.equipped_gear = new List<string>();" in helper
    loading_guard = inventory[
        inventory.index("private void OnTick"):
        inventory.index("if (Game.IsLoading)")
    ]
    assert "Game.Player.IsDead" in loading_guard
    post_load = inventory[
        inventory.index("if (_discardStagedAfterLoad)"):
        inventory.index("DateTime write =")
    ]
    assert "HandlePlayerDeath(player);" in loading_guard
    assert "GET_TIME_SINCE_LAST_DEATH" in post_load
    assert "ShouldPreserveDeathAcrossLoading(" in post_load
    assert '"death_state_preserved_across_respawn_load"' in post_load
    # A real Story load deliberately discards staged purchases, unlike an
    # ordinary watcher reload whose missing/corrupt primary must retain them.
    assert "Reload(discardStaged: true);" in post_load
    assert "ResetDeathTracking();" in post_load


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
    stage = replace.index("LoadAndCreateVehicle")
    capture = replace.index("CaptureAmbientOccupants")
    clone = replace.index("TryCloneOccupants")
    delete = replace.index("old.Delete()")
    # Potentially slow model streaming finishes before the source snapshot so
    # normal ambient churn during Request() cannot poison every validation.
    assert stage < capture < clone
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
    garage_compact = "".join(garage.split())
    davis_compact = "".join(davis.split())
    garment_compact = "".join(garment.split())
    rural_compact = "".join(rural.split())
    paleto_compact = "".join(paleto.split())
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
        ROOT / "content/allin1-online-content/allin1.content.json").read_text()
    assert "GarageEntryPolicy.Evaluate(" in garage
    assert "RejectGarageEntry(ECLIPSE_GARAGE)" in garage
    assert "RejectGarageEntry(THREE_FLOOR_GARAGE)" in garage
    assert "RejectGarageEntry(DAVIS_GARAGE)" in davis
    assert "RejectGarageEntry(GARMENT_GARAGE)" in garment
    assert "RejectGarageEntry(RURAL_GARAGE)" in rural
    assert "RejectGarageEntry(PALETO_GARAGE)" in paleto
    assert "EvaluateGarageEntry(ECLIPSE_GARAGE,veh)" in garage_compact
    assert "EvaluateGarageEntry(ECLIPSE_GARAGE)" in garage_compact
    assert "EvaluateGarageEntry(THREE_FLOOR_GARAGE,vehicle)" in garage_compact
    assert "EvaluateGarageEntry(THREE_FLOOR_GARAGE)" in garage_compact
    assert "EvaluateGarageEntry(DAVIS_GARAGE,vehicle)" in davis_compact
    assert "EvaluateGarageEntry(DAVIS_GARAGE)" in davis_compact
    assert "EvaluateGarageEntry(GARMENT_GARAGE,vehicle)" in garment_compact
    assert "EvaluateGarageEntry(GARMENT_GARAGE)" in garment_compact
    assert "EvaluateGarageEntry(RURAL_GARAGE,vehicle)" in rural_compact
    assert "EvaluateGarageEntry(RURAL_GARAGE)" in rural_compact
    assert "EvaluateGarageEntry(PALETO_GARAGE,vehicle)" in paleto_compact
    assert "EvaluateGarageEntry(PALETO_GARAGE)" in paleto_compact
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
        "DeferredMapContentRuntime.TryAcquireInteriorUnderBlackTransition(")
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
    assert "if (!LoadFloorGarageInterior(transition))" in entry
    # The new owned fade loads before any drive-in save, eliminating the
    # old speculative persistence/rollback path on map failure.
    assert entry.index("transition.HoldFade") < entry.index("LoadFloorGarageInterior(transition)")
    assert entry.index("LoadFloorGarageInterior(transition)") < entry.index("storedList.Add(sv)")
    assert 'transition.Fail("map_activation_failed")' in entry


def test_grapeseed_garage_is_fully_integrated_and_persistent(tmp_path, monkeypatch):
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
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
    _assert_removal_preserves_save("ALLIN1_rural_garage.json", tmp_path, monkeypatch)
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

    assert '"hei_hw1_blimp_interior_v_garagem_milo_"' in rural
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
    assert "transition.HoldFade(" in entry
    assert "LoadRuralInterior(transition)" in entry
    assert entry.index("transition.HoldFade(") < entry.index(
        "LoadRuralInterior(transition)"
    )
    assert "TryAcquireGrapeseedPhaseB(" in loader
    assert "DlcMapState.Release(RURAL_GARAGE)" not in rural
    assert "DeferredMapContentRuntime.Release" in rural


def test_paleto_bay_garage_uses_native_casino_layout_and_full_integration(tmp_path, monkeypatch):
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
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
    _assert_removal_preserves_save("ALLIN1_paleto_garage.json", tmp_path, monkeypatch)
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


def test_traffic_disabled_baseline_is_handler_free_and_catalog_validation_is_reused():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    constructor = traffic[traffic.index("public TrafficSpawner()"):
                          traffic.index("private void LoadSettings")]
    initializer = traffic[traffic.index("private void Initialize()"):
                          traffic.index("SelectedModelValidationAction")]
    assert constructor.index("if (!ShouldAttachRuntimeHandlers") < \
        constructor.index("Tick += OnTick")
    assert "Aborted +=" not in constructor
    assert "RuntimeVehicleCatalog.Refresh()" not in initializer
    assert "RuntimeVehicleCatalog.TrafficEntries" in initializer
    assert "entry.ValidatedRuntimeVehicleClass" in initializer
    assert "model.IsInCdImage" not in initializer
    assert "model.IsVehicle" not in initializer
    loader = traffic[traffic.index("private Vehicle LoadAndCreateVehicle"):
                     traffic.index("private void QuarantineModel")]
    assert "model.Request();" in loader
    assert "model.Request(MODEL_LOAD_TIMEOUT)" not in loader
    assert "HasModelLoadTimedOut" in loader


def test_yacht_frame_consumers_use_cached_stream_state_and_offsite_gating():
    yacht = (ROOT / "script/src/YachtManager.cs").read_text()
    helipad = (ROOT / "script/src/GarageManager.Yacht.cs").read_text()
    streamed_property = yacht[yacht.index("internal static bool IsWorldStreamed"):
                               yacht.index("internal static bool FeaturesUnlocked")]
    assert "Function.Call" not in streamed_property
    assert "_worldStreamed" in streamed_property
    assert "GetStreamingPollInterval(_worldStreamed)" in yacht
    assert "ShouldServiceYachtHelipad" in helipad
    assert "YACHT_HELIPAD_OFFSITE_INTERVAL_MS" in helipad
    assert "ShouldServiceExteriorMarker" in helipad
def test_dlc_garages_use_verified_property_groups_without_global_map_switches():
    definitions = (ROOT / "script/src/GarageDefinition.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    paleto = (ROOT / "script/src/GarageManager.Paleto.cs").read_text()
    garment = (ROOT / "script/src/GarageManager.GarmentFactory.cs").read_text()
    rural = (ROOT / "script/src/GarageManager.Rural.cs").read_text()
    standalone = (ROOT / "script/src/StandaloneMapPack.cs").read_text()
    deferred = (ROOT / "script/src/DeferredMapContentRuntime.cs").read_text()
    yacht = (ROOT / "script/src/YachtManager.cs").read_text()
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
    official_acquire = deferred[
        deferred.index("internal static DeferredMapContentResult TryAcquire("):
        deferred.index("private static DeferredMapContentResult ObserveOfficialGarageAttempt")
    ]
    assert '"verified_isolated_startup_ipl_pack"' in official_acquire
    assert '"verified_metadata_bridge"' in official_acquire
    assert "StandaloneMapPack.IsReferenceBridgeVerified" in official_acquire
    assert "OfficialMapActivationPolicy.Resolve" in official_acquire
    assert "OfficialMapActivationPolicy.Acquire" in official_acquire
    assert "GROUP_MAP" not in official_acquire
    assert "GROUP_MAP_SP" not in official_acquire
    assert "0x6BEDF5769AC2DC07UL" in deferred
    assert "0x3C1978285B036B25UL" in deferred
    assert "DeferredMapProperty.Harmony" in garage
    assert "DeferredMapProperty.Davis" in davis
    assert "DeferredMapProperty.GarmentFactory" in garment
    assert "DeferredMapProperty.Paleto" in paleto
    assert "DeferredMapProperty.Grapeseed" in rural
    assert "DeferredMapProperty.Yacht" in yacht
    for source in (garage, davis, garment, paleto, rural):
        assert "DeferredMapContentRuntime.TryAcquire" in source
        assert "DeferredMapContentRuntime.Release" in source
    assert "DeferredMapContentRuntime.TryAcquire" in yacht
    assert "DeferredMapContentRuntime.Release" in yacht
    assert '"verified_metadata_bridge"' in yacht
    yacht_update = yacht[
        yacht.index("private static void UpdateStreaming()"):
        yacht.index("internal static int GetStreamingPollInterval")
    ]
    assert yacht_update.count("DeferredMapContentRuntime.TryAcquire(") == 1
    acquire_guard = yacht_update.index("if (!_worldRequested)")
    assert acquire_guard < yacht_update.index(
        "DeferredMapContentRuntime.TryAcquire(")
    assert "_worldRequested = true;" in yacht_update[acquire_guard:]
    assert "UnloadFloorGarageInterior();" in garage
    assert "UnloadDavisAutoShopInterior();" in davis
    assert "deferred map unavailable" in garage
    assert "deferred map unavailable" in davis
    assert "deferred map unavailable" in garment
    assert "deferred map unavailable" in paleto


def test_deferred_map_readiness_warms_before_transitions_and_retries_safely():
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    deferred = (
        ROOT / "script/src/DeferredMapContentRuntime.cs"
    ).read_text()

    initialize = garage[
        garage.index("internal static void Initialize()"):
        garage.index("internal static bool IsPlayerInGarage")
    ]
    tick = garage[
        garage.index("internal static void OnTick()"):
        garage.index("internal static int GetUsedSlots()")
    ]
    readiness_call = (
        "DeferredMapContentRuntime.ObserveStoryRuntimeReadiness();"
    )
    assert readiness_call in initialize
    assert readiness_call in tick
    assert tick.index(readiness_call) < tick.index(
        "PollStorySaveAndPersistVehicles(now);")
    assert tick.index(readiness_call) < tick.index(
        "if (_transitionInProgress)")

    assert "StoryRuntimeReadinessGate" in deferred
    assert "GarageManager.IsUnsafeGarageTransitionActive()" in deferred
    assert 'reason = "game_transition_active"' in deferred
    assert "RuntimeSafetyRetryTimeoutMs = 15000" in deferred
    assert "WaitForRuntimeSafe(" in deferred
    assert '"activation_queued_unsafe_runtime"' in deferred
    assert '"activation_runtime_ready_after_queue"' in deferred
    assert "int activationStartedAt = _bridge.MonotonicMilliseconds" in deferred
    assert (
        "descriptor.Ipls, true, timeoutMs, activationStartedAt"
        in deferred
    )


def test_davis_entry_holds_black_before_phase_b_activation_and_recovers():
    davis = (ROOT / "script/src/GarageManager.Davis.cs").read_text()
    coordinator = (
        ROOT / "script/src/OfficialGarageStreamingTransition.cs"
    ).read_text()
    entry = davis[
        davis.index("private static void EnterDavisGarageCore"):
        davis.index("private static void LeaveDavisGarage()")
    ]
    loader = davis[
        davis.index("private static bool LoadDavisAutoShopInterior"):
        davis.index("private static void UnloadDavisAutoShopInterior")
    ]

    assert "enum OfficialGarageTransitionPhase" in coordinator
    for phase in (
        "FadeHeld", "LeaseRequested", "IplReady", "InteriorReady",
        "Occupied", "FailedRecovery",
    ):
        assert phase in coordinator
    assert "scope_disposed_before_completion" in coordinator
    assert "official_garage_transition_phase" in davis
    assert entry.index("transition.HoldFade(") < entry.index(
        "OfficialGarageTransitionPhase.LeaseRequested")
    assert entry.index(
        "OfficialGarageTransitionPhase.LeaseRequested") < entry.index(
        "LoadDavisAutoShopInterior(transition)")
    assert "transition.Fail(\"map_activation_failed\")" in entry
    assert "transition.Complete(" in entry
    assert loader.index("OfficialGarageTransitionPhase.IplReady") < loader.index(
        "OfficialGarageTransitionPhase.InteriorReady")


def test_yacht_streaming_is_proximity_scoped_and_waits_for_stable_story():
    yacht = (ROOT / "script/src/YachtManager.cs").read_text()
    deferred = (
        ROOT / "script/src/DeferredMapContentRuntime.cs"
    ).read_text()
    update = yacht[
        yacht.index("private static void UpdateStreaming()"):
        yacht.index("internal static int GetStreamingPollInterval")
    ]

    assert "internal static bool IsStoryRuntimeReady" in deferred
    assert "YachtStreamingPolicy.ShouldAcquire" in update
    assert update.index("YachtStreamingPolicy.ShouldAcquire(") < update.index(
        "DeferredMapContentRuntime.TryAcquire"
    )
    assert "DeferredMapContentRuntime.TryAcquire" in update
    assert '"verified_metadata_bridge"' in update
    assert "private const float AcquireDistance = 900f" in yacht
    assert "private const float ReleaseDistance = 1200f" in yacht
    assert "player.Position.DistanceTo(WorldPosition)" in update
    assert "RemoveWorld();" in update
    assert "DeferredMapContentRuntime.Release" in update
    assert "internal static bool KeepResident" in deferred
    assert "false;" in deferred[
        deferred.index("internal static bool KeepResident"):
        deferred.index("internal sealed class DeferredMapContentDescriptor")
    ]
    assert '"session_streaming_deferred"' in yacht


def test_deferred_garages_move_the_player_outside_before_releasing_maps():
    cases = (
        ("script/src/GarageManager.cs", "LeaveFloorGarageCore",
         "UnloadFloorGarageInterior"),
        ("script/src/GarageManager.Davis.cs", "LeaveDavisGarageCore",
         "UnloadDavisAutoShopInterior"),
        ("script/src/GarageManager.GarmentFactory.cs",
         "LeaveGarmentGarageCore", "UnloadGarmentInterior"),
        ("script/src/GarageManager.Paleto.cs", "LeavePaletoGarageCore",
         "UnloadPaletoInterior"),
        ("script/src/GarageManager.Rural.cs", "LeaveRuralGarageCore",
         "UnloadRuralInterior"),
    )
    for relative, leave_name, unload_name in cases:
        source = (ROOT / relative).read_text(encoding="utf-8")
        start = source.index(f"private static void {leave_name}")
        end = source.index("private static bool Load", start)
        leave = source[start:end]
        release_at = leave.index(f"{unload_name}();")
        assert leave.index("ReleaseGarageVehicleForDriving(") < release_at
        assert leave.index("Hash.SET_ENTITY_COORDS") < release_at


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
    gui = (ROOT / "src/allin1/desktop_content.py").read_text()
    example = (ROOT / "config.example.toml").read_text()
    coordinator = (ROOT / "script/src/PoliceTacticsCoordinator.cs").read_text()
    physics = (ROOT / "script/src/NpcPhysicsExperiment.cs").read_text()
    smoke = (ROOT / "script/src/EnhancedSmokeController.cs").read_text()
    experiment_content = (
        ROOT / "content/allin1-experimental-gameplay/allin1.content.json"
    ).read_text()

    assert "enhanced_police_ai: bool = False" in config
    assert "gta_iv_npc_physics: bool = False" in config
    assert "gta_iv_npc_physics_debug: bool = False" in config
    assert "enhanced_smoke_effects: bool = False" in config
    assert 'f"{boolean(self.script.enhanced_police_ai)}\\n"' in config
    assert '"label": "Enhanced Police AI"' in experiment_content
    assert '"default": false' in experiment_content
    assert "config_key" in gui
    assert "settings" in gui
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
    gui = (ROOT / "desktop/src/App.tsx").read_text()
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
    assert "DeferredMapContentRuntime.TryAcquire" in yacht
    assert "DeferredMapContentRuntime.Release" in yacht
    assert "DeferredMapProperty.Yacht" in yacht
    assert 'private static readonly string[] RequiredIpls' in yacht
    assert "DlcMapState" not in yacht
    assert "_activationBlockedUntilExit" in yacht
    assert '"session_streaming_ready"' in yacht
    assert "DistanceTo(WorldPosition)" in yacht
    assert "Hash.SET_INSTANCE_PRIORITY_MODE" not in yacht
    assert "IS_IPL_ACTIVE" in yacht


def test_yacht_helipad_is_a_persistent_specialized_garage(tmp_path, monkeypatch):
    helipad = (ROOT / "script/src/GarageManager.Yacht.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    manager = (ROOT / "script/src/GarageManager.cs").read_text()
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
    _assert_removal_preserves_save("ALLIN1_yacht_helipad.json", tmp_path, monkeypatch)
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
    native = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text())
    project = (ROOT / "pyproject.toml").read_text()
    assert (ROOT / "src/allin1/assets/ALLIN1.png").stat().st_size > 0
    assert (ROOT / "src/allin1/assets/ALLIN1-icon.png").stat().st_size > 0
    assert (ROOT / "src/allin1/assets/ALLIN1.ico").stat().st_size > 0
    assert native["identifier"] == "com.minionenjoyer.allin1launcher"
    assert native["bundle"]["icon"] == ["../../src/allin1/assets/ALLIN1.ico"]
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
    assert '"Gear", "My Garage", "Add-ons", "Diagnostics", "About"' in browser
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
    assert "markerColor = CharacterMarkerColor();" in davis
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
    assert "if (RuntimeVehicleCatalog.IsListed(model) && !RuntimeVehicleCatalog.IsCatalogOnly(model))" in shop
    assert "buyPrice = RuntimeVehicleCatalog.GetPrice(model);" in shop


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
        # The player/vehicle must reach the exterior before reverting the
        # deferred content group; otherwise its RPF is unmounted underneath
        # the entity during the black transition.
        assert leave.index(unload) > leave.index(
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


def test_reactor_weapon_workbench_keeps_react_controls_with_world_preview():
    workbench = (ROOT / "script/src/GbayWeaponCustomization.cs").read_text()
    browser = (ROOT / "script/src/GbayBrowser.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    contracts = (ROOT / "script/src/GbayReactorContracts.cs").read_text()
    bridge = (ROOT / "script/reactor-bridge/Allin1ReactorBridge.cs").read_text()

    provider = workbench[
        workbench.index("DescribeDetachedWeaponCustomization"):
        workbench.index("private Vector3 GetWeaponCameraPosition")
    ]
    assert "catalog.BuildWorkbenchRows(allowStorefrontCache);" in provider
    assert "IsWorkbenchRowOwned(row)" in provider
    assert "IsWorkbenchRowActive(row)" in provider
    for forbidden in (
        "BeginWeaponCustomization",
        "CreateWeaponCamera",
        "_weaponCamera",
        "_workbenchDummy",
        "GbayRenderer",
    ):
        assert forbidden not in provider

    apply = contracts[
        contracts.index("ApplyWeaponCustomization("):
        contracts.index("public Allin1GearCatalogPage BrowseGear")
    ]
    assert apply.index("GetWeaponCustomizationCatalog(weapon)") < apply.index(
        "ExecuteWeaponComponentPurchase"
    )
    cache = contracts[
        contracts.index("GetWeaponCustomizationCatalog(string weapon)"):
        contracts.index("internal bool TryGetCachedWeaponCustomizationCatalog")
    ]
    assert "GbayBrowser.DescribeDetachedWeaponCustomization(" in cache
    assert "allowStorefrontCache: false" in cache
    assert "ExecuteRefillAmmo" in apply
    assert "ExecuteWeaponTintPurchase" in apply
    assert "ExecuteWeaponComponentTintPurchase" in apply
    assert "CustomizationPostconditionSatisfied" in apply
    assert "request.QuotedPrice != currentPrice" in apply

    assert '"owned-weapons"' in bridge
    assert '"workbench-options"' in bridge
    assert '"weapon.customize.apply"' in bridge
    assert '"component_tint"' in bridge
    assert '"Load owned weapons"' not in bridge
    assert '"refresh-owned-weapons"' not in bridge
    assert "TryOpenWeaponCustomization" in browser
    assert "TryOpenReactorWeaponPreview" in shop
    assert "IAllin1WeaponPreviewStorefront" in contracts
    assert '"world-preview"' in bridge
    assert "private Ped _workbenchPlayer;" in workbench
    assert "player.Handle != _workbenchPlayer.Handle" in workbench
    cleanup = workbench[
        workbench.index("private void EndWeaponCustomization"):
        workbench.index("private void DeleteWeaponWorkbenchDummy")
    ]
    assert "Ped ped = _workbenchPlayer;" in cleanup
    assert "_workbenchPlayer = null;" in cleanup
    handoff = browser[
        browser.index("internal bool TryOpenWeaponCustomization"):
        browser.index("//  Main Draw")
    ]
    assert "catch" in handoff
    assert "EndWeaponCustomization();" in handoff
    assert "_state = BrowserState.Closed;" in handoff
    select = bridge[
        bridge.index("private ReactorActionResult SelectCustomWeapon"):
        bridge.index("private ReactorActionResult UpdateCustomizationView")
    ]
    assert "BeginWeaponPreview" in select
    assert "BrowseWeaponCustomization" in select
    assert "catch" in select
    assert '"workbench_failed"' in select
    assert "_customizationPage = page;" in select
    lifecycle = bridge[
        bridge.index("public void OnLifecycle"):
        bridge.index("public void Dispose()")
    ]
    assert "ReactorLifecycleStage.OverlayClosed" in lifecycle
    assert "StopWeaponPreviewCore" in lifecycle


def test_reactor_gbay_automatically_synchronizes_game_state_without_refresh_controls():
    contracts = (ROOT / "script/src/GbayReactorContracts.cs").read_text()
    shop = (ROOT / "script/src/GbayShop.cs").read_text()
    bridge = (
        ROOT / "script/reactor-bridge/Allin1ReactorBridge.cs"
    ).read_text()

    assert "interface IAllin1GameStateBridge" in contracts
    assert "GbayGameStateSynchronizationGate" in shop
    assert "ObserveReactorGameState(activeCharacter)" in shop
    assert "TrySynchronizeGameStateCore" in bridge
    assert "PublishSynchronizedMenus" in bridge
    assert "JsonConvert.SerializeObject" in bridge
    assert 'builder.AddEvent(new ReactorEventDescriptor(' in bridge
    assert '"state.changed"' in bridge
    assert '_handle!.TryPublishEvent(' in bridge
    for player_refresh_action in (
        '"gbay.refresh"',
        '"weapon.customize.refresh"',
        '"garage.refresh"',
        '"diagnostics.refresh"',
    ):
        assert player_refresh_action not in bridge


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
    assert "RemoveInvalidWeaponsInMemory" not in inventory
    assert '"ownership_preserved", true' in inventory
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
    assert "contents: read" in build_workflow
    assert "ALLIN1-runtime-${{ github.sha }}" in build_workflow
    assert "if-no-files-found: error" in build_workflow
    assert "git push" not in build_workflow and "git commit" not in build_workflow
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
    assert 'allin1-gui = "allin1.desktop_entry:main"' in gui_section


def test_repair_progress_and_helper_consoles_are_managed_in_process():
    gui = (ROOT / "desktop/src/App.tsx").read_text(encoding="utf-8")
    service = (ROOT / "src/allin1/desktop_service.py").read_text(encoding="utf-8")
    installer = (ROOT / "src/allin1/installer.py").read_text(encoding="utf-8")
    processes = (ROOT / "src/allin1/processes.py").read_text(encoding="utf-8")
    ytd_builder = (ROOT / "src/allin1/generators/ytd_builder.py").read_text(
        encoding="utf-8"
    )
    assert "onProgress" in gui and "progress.percentage" in gui
    assert "progress=self.progress" in service
    assert "observe_gta_launch" in service
    assert "CREATE_NO_WINDOW" in processes and "STARTF_USESHOWWINDOW" in processes
    assert "subprocess.run(" not in installer
    assert "subprocess.run(" not in ytd_builder
