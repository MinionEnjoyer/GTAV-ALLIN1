import logging
import queue
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from allin1.config import Config
from allin1.gui import (
    ManagerWindow, QueueLogHandler, _operation_progress_text, _status_presentation,
)
from allin1.manager import InstallationStatus


ROOT = Path(__file__).resolve().parents[1]


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
    window.garages_always_accessible = Variable(True)
    window.enhanced_police_ai = Variable(True)
    window.gta_iv_npc_physics = Variable(True)
    window.gta_iv_npc_physics_debug = Variable(False)
    window.enhanced_smoke_effects = Variable(True)
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
    assert config.script.garages_always_accessible is True
    assert config.script.enhanced_police_ai is True
    assert config.script.gta_iv_npc_physics is True
    assert config.script.gta_iv_npc_physics_debug is False
    assert config.script.enhanced_smoke_effects is True


def test_current_config_collects_both_game_roots_and_active_target():
    window = _window()
    window.legacy_path = Variable(r"C:\Games\GTAV Legacy")
    window.enhanced_path = Variable(r"D:\Games\GTAV Enhanced")
    window.target_edition = Variable("Enhanced")

    config = window._current_config()

    assert config.general.gta_legacy_path == r"C:\Games\GTAV Legacy"
    assert config.general.gta_enhanced_path == r"D:\Games\GTAV Enhanced"
    assert config.general.target_edition == "enhanced"
    assert config.general.gta_path == r"D:\Games\GTAV Enhanced"


def test_queue_log_handler_sends_formatted_record():
    messages = queue.Queue()
    handler = QueueLogHandler(messages)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    handler.emit(logging.LogRecord("test", logging.WARNING, "", 0, "hello", (), None))
    assert messages.get_nowait() == ("log", "WARNING:hello")


def test_mod_package_list_includes_builtin_smoke_sdk_example():
    window = ManagerWindow.__new__(ManagerWindow)
    window.mod_tree = Mock()
    window.mod_tree.selection.return_value = ()
    window.mod_tree.get_children.return_value = ()
    window.mod_catalog = Mock()
    window.mod_catalog.discover.return_value = []
    window.sdk_catalog = Mock()
    from allin1.addon_sdk import AddonSdkCatalog
    smoke = AddonSdkCatalog(ROOT).discover()[0]
    window.sdk_catalog.discover.return_value = [smoke]
    window.mod_details = Mock()
    window._mod_service = Mock(side_effect=ValueError("game not selected"))

    window.refresh_mods()

    assert window.sdk_manifests == {"sdk:allin1.colored_smokes": smoke}
    window.mod_tree.insert.assert_called_once_with(
        "", "end", iid="sdk:allin1.colored_smokes",
        text="ALLIN1 Colored Smoke Grenades",
        values=("SDK", "Enhanced", "1.0.0", "Built-in example"),
    )


def test_asset_viewer_opens_selected_package_root(tmp_path, monkeypatch):
    window = ManagerWindow.__new__(ManagerWindow)
    window.root = Mock()
    window._selected_mod_id = Mock(return_value="package.test")
    window.mod_manifests = {
        "package.test": SimpleNamespace(package_root=tmp_path),
    }
    window.sdk_manifests = {}
    viewer = Mock()
    monkeypatch.setattr("allin1.gui.AssetViewerDialog", viewer)

    window.open_asset_viewer()

    viewer.assert_called_once_with(window.root, tmp_path)


def test_launcher_opens_sdk_as_an_external_application(tmp_path, monkeypatch):
    window = ManagerWindow.__new__(ManagerWindow)
    window.manager = SimpleNamespace(project_root=tmp_path / "ALLIN1")
    window._append_log = Mock()
    window.sdk_install_root = tmp_path / "managed" / "SDK"
    executable = tmp_path / "bin" / "allin1-sdk-gui.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"sdk")
    launched = Mock()
    monkeypatch.setattr("allin1.gui.shutil.which", lambda _name: str(executable))
    monkeypatch.setattr("allin1.gui.subprocess.Popen", launched)

    window.open_addon_sdk()

    launched.assert_called_once()
    assert launched.call_args.args[0] == [str(executable)]
    window._append_log.assert_called_once()


def test_launcher_explains_when_standalone_sdk_is_missing(tmp_path, monkeypatch):
    window = ManagerWindow.__new__(ManagerWindow)
    window.manager = SimpleNamespace(project_root=tmp_path / "ALLIN1")
    window.sdk_install_root = tmp_path / "managed" / "SDK"
    window.manage_addon_sdk = Mock()
    monkeypatch.setattr("allin1.gui.shutil.which", lambda _name: None)

    window.open_addon_sdk()

    window.manage_addon_sdk.assert_called_once_with()


def test_launcher_prefers_managed_sdk_installation(tmp_path, monkeypatch):
    window = ManagerWindow.__new__(ManagerWindow)
    window.manager = SimpleNamespace(project_root=tmp_path / "ALLIN1")
    window.sdk_install_root = tmp_path / "local" / "ALLIN1" / "SDK"
    window._append_log = Mock()
    executable = window.sdk_install_root / "ALLIN1-SDK.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZsdk")
    (window.sdk_install_root / "release.json").write_text(
        '{"product":"ALLIN1-SDK","version":"0.4.8"}'
    )
    launched = Mock()
    monkeypatch.setattr("allin1.gui.subprocess.Popen", launched)
    monkeypatch.setattr("allin1.gui.shutil.which", lambda _name: None)

    window.open_addon_sdk()

    launched.assert_called_once()
    assert launched.call_args.args[0] == [str(executable)]


def test_repair_progress_text_clamps_percentages():
    assert _operation_progress_text("Repairing", -5) == "Repairing - 0%"
    assert _operation_progress_text("Repairing", 47) == "Repairing - 47%"
    assert _operation_progress_text("Repairing", 150) == "Repairing - 100%"


def test_launch_guard_submits_only_one_storefront_request(tmp_path, monkeypatch):
    window = _window()
    window.busy = False
    window.launch_pending = False
    window.manager = Mock()
    window.manager.resolve_path.return_value = tmp_path
    window.launch_button = Mock()
    window.root = Mock()
    window._clear_dirty = Mock()
    window._append_log = Mock()
    target = Mock(description="GTA V Enhanced through Steam")
    launcher = Mock(return_value=target)
    monkeypatch.setattr("allin1.gui.launch_gta", launcher)

    window.launch_game()
    window.launch_game()

    launcher.assert_called_once_with(tmp_path)
    window.root.after.assert_called_once_with(15000, window._reset_launch_guard)


def test_launch_guard_blocks_quarantined_rpf_pack(tmp_path, monkeypatch):
    window = _window()
    window.busy = False
    window.launch_pending = False
    window.manager = Mock()
    window.manager.resolve_path.return_value = tmp_path
    window.launch_button = Mock()
    window.root = Mock()
    window._clear_dirty = Mock()
    window._append_log = Mock()
    pack = tmp_path / "mods/update/x64/dlcpacks/allin1_smoke"
    pack.mkdir(parents=True)
    (pack / "dlc.rpf").write_bytes(b"unsafe")
    launcher = Mock()
    shown = Mock()
    monkeypatch.setattr("allin1.gui.launch_gta", launcher)
    monkeypatch.setattr("allin1.gui.messagebox.showerror", shown)

    window.launch_game()

    launcher.assert_not_called()
    shown.assert_called_once()
    assert "RPF safety check blocked launch" in shown.call_args.args[1]


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


def _status(**overrides):
    values = {
        "gta_path": None,
        "valid_game": False,
        "edition": "Unknown",
        "mod_installed": False,
        "scripthookv_installed": False,
        "shvdn_installed": False,
        "openrpf_installed": False,
    }
    values.update(overrides)
    return InstallationStatus(**values)


def test_status_presentation_guides_invalid_and_uninstalled_states(tmp_path):
    invalid = _status_presentation(_status())
    assert invalid.headline == "Select your GTA V folder"
    assert invalid.can_launch is False
    assert invalid.can_install is False

    uninstalled = _status_presentation(_status(
        gta_path=tmp_path,
        valid_game=True,
        edition="Enhanced",
        scripthookv_installed=True,
        shvdn_installed=True,
    ))
    assert uninstalled.headline == "ALLIN1 is ready to install"
    assert uninstalled.can_install is True
    assert uninstalled.can_uninstall is False


def test_status_presentation_prioritizes_missing_dependencies_and_version_drift(tmp_path):
    missing = _status_presentation(_status(
        gta_path=tmp_path,
        valid_game=True,
        edition="Enhanced",
        mod_installed=True,
        installed_version="0.4.1",
        manager_version="0.4.1",
    ))
    assert missing.headline == "Required components are missing"
    assert "ScriptHookV" in missing.detail

    update = _status_presentation(_status(
        gta_path=tmp_path,
        valid_game=True,
        edition="Enhanced",
        mod_installed=True,
        scripthookv_installed=True,
        shvdn_installed=True,
        installed_version="0.4.0",
        manager_version="0.4.1",
    ))
    assert update.headline == "Client update available"
    assert "0.4.0" in update.detail and "0.4.1" in update.detail


def test_status_presentation_reports_ready_when_versions_match(tmp_path):
    ready = _status_presentation(_status(
        gta_path=tmp_path,
        valid_game=True,
        edition="Enhanced",
        mod_installed=True,
        scripthookv_installed=True,
        shvdn_installed=True,
        installed_version="0.4.1",
        manager_version="0.4.1",
    ))
    assert ready.headline == "Ready to play"
    assert ready.can_launch is True
    assert ready.tone == "success"
