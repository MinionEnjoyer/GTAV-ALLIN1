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
rich_areas_only_supers = true

[vehicles]
enable_all = true
disabled_classes = []
disabled_vehicles = []
""")
    config = Config.load(path)
    assert config.general.gta_path == "auto"
    assert config.general.free_mode is False
    assert config.traffic.enabled is True
    assert config.traffic.rich_areas_only_supers is True
    assert config.vehicles.enable_all is True


def test_load_minimal_config(tmp_path):
    """Config with missing sections should use defaults."""
    path = _write_toml(tmp_path, "")
    config = Config.load(path)
    assert config.general.gta_path == "auto"
    assert config.traffic.enabled is True
    assert config.vehicles.enable_all is True


def test_legacy_free_mode_migrates_to_gbay_setting(tmp_path):
    path = _write_toml(tmp_path, """
[general]
free_mode = true
""")
    config = Config.load(path)
    assert config.script.gbay_free_mode is True


def test_explicit_gbay_free_mode_overrides_legacy_alias(tmp_path):
    path = _write_toml(tmp_path, """
[general]
free_mode = true
[script]
gbay_free_mode = false
""")
    config = Config.load(path)
    assert config.script.gbay_free_mode is False


def test_backwards_compat_density_ignored(tmp_path):
    """Old configs with density should load without error."""
    path = _write_toml(tmp_path, """
[traffic]
density = "ultra"
enabled = true
""")
    config = Config.load(path)
    assert config.traffic.enabled is True


def test_retired_offline_launch_setting_is_ignored(tmp_path):
    path = _write_toml(tmp_path, """
[general]
story_mode_only = true
""")
    config = Config.load(path)
    assert not hasattr(config.general, "story_mode_only")


def test_retired_axle_test_harness_setting_is_ignored(tmp_path):
    path = _write_toml(tmp_path, """
[script]
axle_test_harness = true
""")
    config = Config.load(path)
    assert not hasattr(config.script, "axle_test_harness")


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
    prices_file = tmp_path / "prices_vehicles.toml"
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
    assert config.general.gta_legacy_path == "auto"
    assert config.general.gta_enhanced_path == "auto"
    assert config.general.target_edition == "auto"
    assert config.traffic.enabled is True
    assert config.traffic.max_driven == 20
    assert config.traffic.replacement_chance == 0.30
    assert config.vehicles.enable_all is True
    assert config.traffic.adaptive_performance is True
    assert config.general.enable_rpf_previews is True
    assert config.script.ui_scale == 1.0
    assert config.script.seat_selector_key == "L"
    assert config.script.garages_always_accessible is False
    assert config.script.enhanced_police_ai is False
    assert config.script.gta_iv_npc_physics is False
    assert config.script.gta_iv_npc_physics_debug is False
    assert config.script.enhanced_smoke_effects is False
    assert config.script.controller_enabled is True
    assert config.script.controller_open_gbay == "FrontendRdown"


def test_save_round_trip_preserves_all_fields(tmp_path):
    config = Config.default()
    config.general.gta_path = r'C:\Games\Grand "Theft" Auto V'
    config.general.gta_legacy_path = r"C:\Games\GTAV Legacy"
    config.general.gta_enhanced_path = r"D:\Games\GTAV Enhanced"
    config.general.target_edition = "enhanced"
    config.general.free_mode = True
    config.general.backup = False
    config.traffic.enabled = False
    config.traffic.rich_areas_only_supers = False
    config.vehicles.enable_all = False
    config.vehicles.disabled_classes = ["military", "emergency"]
    config.vehicles.disabled_vehicles = ["oppressor2"]
    config.script.enable_logging = True
    config.script.enable_dlc_police = True
    config.script.gbay_key = "F8"
    config.script.night_vision_key = "V"
    config.script.world_vector_key = "F10"
    config.script.seat_selector_enabled = False
    config.script.seat_selector_key = "G"
    config.script.gbay_free_mode = True
    config.script.garages_always_accessible = True
    config.script.enhanced_police_ai = True
    config.script.gta_iv_npc_physics = True
    config.script.gta_iv_npc_physics_debug = False
    config.script.enhanced_smoke_effects = True
    path = tmp_path / "nested" / "config.toml"

    config.save(path)
    loaded = Config.load(path)

    assert loaded == config


def test_target_edition_validation_rejects_unknown_value():
    config = Config.default()
    config.general.target_edition = "online"
    with pytest.raises(ValueError, match="target_edition"):
        config.validate()


@pytest.mark.parametrize("field,value,match", [
    ("gbay_key", "", "Unsupported"),
    ("night_vision_key", "Space", "Unsupported"),
    ("world_vector_key", "F13", "Unsupported"),
    ("seat_selector_key", "Space", "Unsupported"),
])
def test_keybind_validation_rejects_unsupported_values(field, value, match):
    config = Config.default()
    setattr(config.script, field, value)
    with pytest.raises(ValueError, match=match):
        config.validate()


def test_keybind_validation_rejects_conflicts_and_normalizes_case():
    config = Config.default()
    config.script.gbay_key = "f9"
    config.script.world_vector_key = "F9"
    with pytest.raises(ValueError, match="both"):
        config.validate()
    config.script.world_vector_key = "NumPad9"
    config.validate()


def test_controller_bindings_round_trip_and_validate(tmp_path):
    config = Config.default()
    config.script.controller_open_gbay = "FrontendX"
    config.script.controller_open_gbay_modifier = "FrontendRt"
    path = tmp_path / "controller.toml"
    config.save(path)
    loaded = Config.load(path)
    assert loaded.script.controller_open_gbay == "FrontendX"
    assert loaded.script.controller_open_gbay_modifier == "FrontendRt"

    loaded.script.controller_accept = "Attack"
    with pytest.raises(ValueError, match="controller_accept"):
        loaded.validate()


@pytest.mark.parametrize("field,value", [
    ("max_driven", -1), ("max_driven", 101),
    ("spawn_distance_min", 10), ("spawn_distance_max", 50),
    ("cleanup_distance", 100),
    ("replacement_chance", -0.1), ("replacement_chance", 1.1),
    ("driven_cooldown_ms", 249), ("scan_cooldown_ms", 100),
    ("scan_radius", 10),
])
def test_traffic_validation_rejects_unsafe_values(field, value):
    config = Config.default()
    setattr(config.traffic, field, value)
    with pytest.raises(ValueError):
        config.validate()


@pytest.mark.parametrize("section,field,value", [
    ("traffic", "minimum_fps", 19), ("traffic", "minimum_fps", 121),
    ("script", "ui_scale", 0.5), ("script", "ui_scale", 2.0),
    ("script", "hold_duration_ms", 99), ("script", "hold_duration_ms", 2001),
])
def test_performance_and_accessibility_validation(section, field, value):
    config = Config.default(); setattr(getattr(config, section), field, value)
    with pytest.raises(ValueError): config.validate()
