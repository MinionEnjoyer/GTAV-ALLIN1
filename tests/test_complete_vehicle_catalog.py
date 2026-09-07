"""The complete model roster is browseable, not automatically traffic/purchase safe."""
import json
from pathlib import Path

from allin1.generators.catalog_only_vehicles import generate
from allin1.vehicles.database import VehicleDatabase

ROOT = Path(__file__).resolve().parents[1]


def test_full_roster_matches_every_extracted_rockstar_model():
    reference = {v["Model"].lower() for v in json.loads((ROOT / "catalog/vehicle_seats.json").read_text())["Vehicles"]}
    static = {v.model for v in VehicleDatabase.load(ROOT / "data/vehicles.toml")}
    story = {v["model"] for v in json.loads((ROOT / "data/story_vehicles.json").read_text())["vehicles"]}
    extra = json.loads((ROOT / "data/catalog_only_vehicles.json").read_text())["vehicles"]
    models = {v["model"] for v in extra}
    assert len(models) == len(extra) == 218
    assert not models & (static | story)
    assert static | story | models == reference
    assert len(reference) == 935
    assert not any("price" in v or "traffic" in v for v in extra)


def test_generated_catalog_is_current_and_separate_from_purchase_and_traffic():
    source = generate(ROOT / "data/catalog_only_vehicles.json")
    assert source == (ROOT / "script/src/CatalogOnlyVehicles.cs").read_text(encoding="utf-8")
    assert source.count("new GbayVehicleRecord(") == 218
    assert source.count(", 0, Storage, ") == 218
    assert source.count(", 0, null, null, false, 1.0)") == 218


def test_story_mission_reward_models_are_not_lost():
    story = {v["model"]: v for v in json.loads((ROOT / "data/story_vehicles.json").read_text())["vehicles"]}
    assert {"tractor", "dune2", "cheetah", "entityxf", "ztype", "jb700", "monroe"} <= story.keys()
    assert story["dune2"]["name"] == "Space Docker"
    assert story["jb700"]["name"] == "JB 700"


def test_catalog_only_models_are_in_launcher_preview_inventory():
    from allin1.catalog_model_previews import catalog_names
    models = catalog_names(ROOT, "vehicles")
    assert len(models) == 935
    assert {"zentorno", "tractor", "dune2", "cargoplane", "trflat2"} <= set(models)
