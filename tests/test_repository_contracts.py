"""Whole-repository contracts connecting data, generated code, and releases."""

import json
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
    assert models <= previews


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
