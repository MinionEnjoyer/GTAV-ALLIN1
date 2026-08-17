"""Tests for the vehicle database."""

import tempfile
from pathlib import Path

from allin1.vehicles.database import Vehicle, VehicleDatabase


SAMPLE_TOML = """
[[vehicles]]
model = "brioso"
name = "Grotti Brioso R/A"
class = "compacts"
manufacturer = "Grotti"
traffic = ["veh_mid", "veh_poor"]

[[vehicles]]
model = "entity3"
name = "Overflod Entity MT"
class = "super"
manufacturer = "Overflod"
traffic = ["veh_rich"]

[[vehicles]]
model = "oppressor2"
name = "Pegassi Oppressor Mk II"
class = "military"
manufacturer = "Pegassi"
traffic = []

[[vehicles]]
model = "vigero2"
name = "Declasse Vigero ZX"
class = "muscle"
manufacturer = "Declasse"
traffic = ["veh_mid", "veh_poor"]
"""


def _load_db(tmp_path: Path) -> VehicleDatabase:
    p = tmp_path / "vehicles.toml"
    p.write_text(SAMPLE_TOML)
    return VehicleDatabase.load(p)


def test_load_count(tmp_path):
    db = _load_db(tmp_path)
    assert len(db) == 4


def test_get_by_model(tmp_path):
    db = _load_db(tmp_path)
    v = db.get("entity3")
    assert v is not None
    assert v.name == "Overflod Entity MT"
    assert v.vehicle_class == "super"


def test_get_missing(tmp_path):
    db = _load_db(tmp_path)
    assert db.get("nonexistent") is None


def test_by_class(tmp_path):
    db = _load_db(tmp_path)
    compacts = db.by_class("compacts")
    assert len(compacts) == 1
    assert compacts[0].model == "brioso"


def test_classes(tmp_path):
    db = _load_db(tmp_path)
    classes = db.classes
    assert "compacts" in classes
    assert "super" in classes
    assert "military" in classes
    assert "muscle" in classes


def test_filter_disabled_classes(tmp_path):
    db = _load_db(tmp_path)
    filtered = db.filter(disabled_classes=["military"])
    models = [v.model for v in filtered]
    assert "oppressor2" not in models
    assert "brioso" in models
    assert len(filtered) == 3


def test_filter_disabled_vehicles(tmp_path):
    db = _load_db(tmp_path)
    filtered = db.filter(disabled_vehicles=["entity3", "brioso"])
    models = [v.model for v in filtered]
    assert "entity3" not in models
    assert "brioso" not in models
    assert len(filtered) == 2


def test_filter_combined(tmp_path):
    db = _load_db(tmp_path)
    filtered = db.filter(disabled_classes=["military"], disabled_vehicles=["brioso"])
    models = [v.model for v in filtered]
    assert "oppressor2" not in models
    assert "brioso" not in models
    assert len(filtered) == 2


def test_iteration(tmp_path):
    db = _load_db(tmp_path)
    models = [v.model for v in db]
    assert len(models) == 4
    assert "brioso" in models
