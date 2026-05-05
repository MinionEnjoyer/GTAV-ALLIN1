"""Tests for config loading and validation."""

import tempfile
from pathlib import Path

import pytest

from allin1.config import Config, load_prices


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content)
    return p


def test_load_default_config(tmp_path):
    path = _write_toml(tmp_path, """
[general]
gta_path = "auto"
free_mode = false
backup = true

[traffic]
enabled = true
density = "medium"
rich_areas_only_supers = true

[vehicles]
enable_all = true
disabled_classes = []
disabled_vehicles = []
""")
    config = Config.load(path)
    assert config.general.gta_path == "auto"
    assert config.general.free_mode is False
    assert config.traffic.density == "medium"
    assert config.vehicles.enable_all is True


def test_load_minimal_config(tmp_path):
    """Config with missing sections should use defaults."""
    path = _write_toml(tmp_path, "")
    config = Config.load(path)
    assert config.general.gta_path == "auto"
    assert config.traffic.enabled is True
    assert config.vehicles.enable_all is True


def test_invalid_density(tmp_path):
    path = _write_toml(tmp_path, """
[traffic]
density = "ultra"
""")
    with pytest.raises(ValueError, match="Invalid traffic density"):
        Config.load(path)


def test_none_density(tmp_path):
    path = _write_toml(tmp_path, """
[traffic]
density = "none"
""")
    config = Config.load(path)
    assert config.traffic.density == "none"


def test_disabled_classes(tmp_path):
    path = _write_toml(tmp_path, """
[vehicles]
disabled_classes = ["military", "emergency"]
disabled_vehicles = ["oppressor2"]
""")
    config = Config.load(path)
    assert "military" in config.vehicles.disabled_classes
    assert "oppressor2" in config.vehicles.disabled_vehicles


def test_load_prices(tmp_path):
    prices_file = tmp_path / "prices.toml"
    prices_file.write_text("""
[super]
entity3 = 2000000
krieger = 1800000

[compacts]
brioso = 150000
""")
    prices = load_prices(prices_file)
    assert prices["entity3"] == 2000000
    assert prices["krieger"] == 1800000
    assert prices["brioso"] == 150000


def test_load_prices_missing_file(tmp_path):
    prices = load_prices(tmp_path / "nonexistent.toml")
    assert prices == {}


def test_default_config():
    config = Config.default()
    assert config.general.gta_path == "auto"
    assert config.traffic.density == "medium"
    assert config.vehicles.enable_all is True
