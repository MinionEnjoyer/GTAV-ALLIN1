import logging
import queue
from unittest.mock import Mock

import pytest

from allin1.config import Config
from allin1.gui import ManagerWindow, QueueLogHandler


class Variable:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def _window():
    window = ManagerWindow.__new__(ManagerWindow)
    window.config = Config.default()
    window.path = Variable(" /game ")
    window.rpf_previews = Variable(True)
    window.backup_enabled = Variable(False)
    window.traffic = Variable(False)
    window.rich_areas_only = Variable(False)
    window.adaptive_performance = Variable(False)
    window.enable_all_vehicles = Variable(False)
    window.disabled_classes = Variable("military, emergency")
    window.disabled_vehicles = Variable("oppressor2, deluxo")
    window.police = Variable(True)
    window.logging_enabled = Variable(True)
    window.gbay_key = Variable("F8")
    window.night_vision_key = Variable("V")
    window.world_vector_key = Variable("F11")
    window.seat_selector_enabled = Variable(False)
    window.seat_selector_key = Variable("G")
    window.safe_mode = Variable(True)
    window.reduced_motion = Variable(True)
    window.colorblind_mode = Variable(True)
    window.ui_scale = Variable(1.2)
    window.hold_duration_ms = Variable(600)
    window.gbay_free_mode = Variable(True)
    return window


def test_current_config_collects_all_launcher_fields():
    config = _window()._current_config()
    assert config.general.gta_path == "/game"
    assert config.general.free_mode is True
    assert config.general.enable_rpf_previews is True
    assert config.general.backup is False
    assert config.traffic.enabled is False
    assert config.traffic.rich_areas_only_supers is False
    assert config.traffic.adaptive_performance is False
    assert config.vehicles.disabled_classes == ["military", "emergency"]
    assert config.vehicles.disabled_vehicles == ["oppressor2", "deluxo"]
    assert config.script.gbay_key == "F8"
    assert config.script.night_vision_key == "V"
    assert config.script.world_vector_key == "F11"
    assert config.script.seat_selector_enabled is False
    assert config.script.seat_selector_key == "G"
    assert config.script.safe_mode is True
    assert config.script.reduced_motion is True
    assert config.script.colorblind_mode is True
    assert config.script.ui_scale == 1.2
    assert config.script.hold_duration_ms == 600
    assert config.script.gbay_free_mode is True


def test_queue_log_handler_sends_formatted_record():
    messages = queue.Queue()
    handler = QueueLogHandler(messages)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    handler.emit(logging.LogRecord("test", logging.WARNING, "", 0, "hello", (), None))
    assert messages.get_nowait() == ("log", "WARNING:hello")


def test_save_displays_validation_errors(monkeypatch):
    window = _window()
    window.gbay_key = Variable("F8")
    window.world_vector_key = Variable("F8")
    window.manager = Mock()
    window._append_log = Mock()
    shown = Mock()
    monkeypatch.setattr("allin1.gui.messagebox.showerror", shown)
    window.manager.save_config.side_effect = ValueError("conflict")
    window.save()
    shown.assert_called_once()
