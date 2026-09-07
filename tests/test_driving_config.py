import pytest

from allin1.config import Config


def test_driving_settings_roundtrip(tmp_path):
    config = Config.default()
    config.script.speedometer_provider = "lefix"
    config.script.speedometer_units = "mph"
    config.script.driving_telemetry = "all"
    config.script.shift_controls_enabled = False
    path = tmp_path / "config.toml"
    config.save(path)
    assert Config.load(path).script == config.script


@pytest.mark.parametrize("key,value", [
    ("speedometer_provider", "unknown"), ("speedometer_provider", None),
    ("speedometer_units", "knots"), ("driving_telemetry", True),
    ("shift_controls_enabled", "true"), ("shift_controls_enabled", 1),
])
def test_driving_settings_reject_invalid_values(key, value):
    config = Config.default()
    setattr(config.script, key, value)
    with pytest.raises(ValueError, match=key):
        config.validate()


def test_old_configs_get_automatic_display_and_towing_only_telemetry(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[script]\n")
    config = Config.load(path)
    assert config.script.speedometer_provider == "auto"
    assert config.script.speedometer_units == "kmh"
    assert config.script.driving_telemetry == "towing"
