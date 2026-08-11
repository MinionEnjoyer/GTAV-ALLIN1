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
    window.free_mode = Variable(True)
    window.traffic = Variable(False)
    window.police = Variable(True)
    window.logging_enabled = Variable(True)
    window.gbay_key = Variable("F8")
    window.night_vision_key = Variable("V")
    window.preview_capture_key = Variable("F11")
    window.seat_selector_enabled = Variable(False)
    window.safe_mode = Variable(True)
    window.reduced_motion = Variable(True)
    window.colorblind_mode = Variable(True)
    window.ui_scale = Variable(1.2)
    window.hold_duration_ms = Variable(600)
    return window


def test_current_config_collects_all_launcher_fields():
    config = _window()._current_config()
    assert config.general.gta_path == "/game"
    assert config.general.free_mode is True
    assert config.traffic.enabled is False
    assert config.script.gbay_key == "F8"
    assert config.script.night_vision_key == "V"
    assert config.script.preview_capture_key == "F11"
    assert config.script.seat_selector_enabled is False
    assert config.script.safe_mode is True
    assert config.script.reduced_motion is True
    assert config.script.colorblind_mode is True
    assert config.script.ui_scale == 1.2
    assert config.script.hold_duration_ms == 600


def test_queue_log_handler_sends_formatted_record():
    messages = queue.Queue()
    handler = QueueLogHandler(messages)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    handler.emit(logging.LogRecord("test", logging.WARNING, "", 0, "hello", (), None))
    assert messages.get_nowait() == ("log", "WARNING:hello")


def test_save_displays_validation_errors(monkeypatch):
    window = _window()
    window.gbay_key = Variable("F8")
    window.preview_capture_key = Variable("F8")
    window.manager = Mock()
    window._append_log = Mock()
    shown = Mock()
    monkeypatch.setattr("allin1.gui.messagebox.showerror", shown)
    window.manager.save_config.side_effect = ValueError("conflict")
    window.save()
    shown.assert_called_once()
