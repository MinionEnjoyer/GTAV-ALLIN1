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


def test_production_project_excludes_developer_scripts():
    project = (ROOT / "script/ALLIN1.csproj").read_text()
    assert '<Compile Remove="tools\\**" />' in project
    assert '<Compile Include="tools\\' not in project


def test_prebuilt_runtime_artifacts_are_present_and_nonempty():
    for relative in ("script/dist/ALLIN1.dll", "script/dist/LemonUI.SHVDN3.dll", "asi/dist/ALLIN1.asi"):
        artifact = ROOT / relative
        assert artifact.stat().st_size > 1024


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


def test_preview_capture_and_seat_selector_contracts():
    installer = (ROOT / "src/allin1/installer.py").read_text()
    seat = (ROOT / "script/src/SeatSelector.cs").read_text()
    assert 'gta_path / SCRIPTS_DIR / "previews"' in installer
    assert "models = sorted(v.model" in installer
    assert "IsSelectorHeld" in seat
    assert "That seat is no longer available" in seat
    assert "seat_selector_enabled" in seat
    assert "seat_selector_key" in seat


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


def test_runtime_hot_paths_are_throttled_and_cached():
    traffic = (ROOT / "script/src/TrafficSpawner.cs").read_text()
    garage = (ROOT / "script/src/GarageManager.cs").read_text()
    assert "Interval = 100" in traffic
    assert "now - _lastCleanupTime >= 1000" in traffic
    assert "charColor != _lastBlipColor" in garage
    assert "charColor != _lastFloorBlipColor" in garage


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
    assert "floorCount = GarageManager.IsPlayerInFloorGarage ? 3 : 1" in customize
    assert "GarageSellConfirm" in browser and "CONFIRM VEHICLE SALE" in browser
    assert "progress_applied" in inventory and "STAT_SET_INT" in inventory


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
