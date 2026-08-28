import inspect
import logging
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from allin1.config import Config
from allin1.extensions import ExtensionManifest
from allin1.gui import (
    ManagerWindow, QueueLogHandler, _operation_progress_text, _status_presentation,
)
from allin1.manager import InstallationStatus
from allin1.ui_theme import UiSettings


ROOT = Path(__file__).resolve().parents[1]


def test_manager_window_uses_shared_project_and_quick_import_catalog() -> None:
    initialization = inspect.getsource(ManagerWindow.__init__)
    assert "self.mod_catalog = default_mod_catalog(manager.project_root)" in (
        initialization
    )


def test_launcher_navigation_matches_the_embedded_workspace_shell() -> None:
    assert ManagerWindow.NAVIGATION == (
        ("setup", "Setup", "Ctrl+1"),
        ("gameplay", "Gameplay", "Ctrl+2"),
        ("content", "Content", "Ctrl+3"),
        ("input", "Input", "Ctrl+4"),
        ("mods", "Packages", "Ctrl+5"),
        ("characters", "Characters", "Ctrl+6"),
        ("sdk", "SDK Manager", "Ctrl+7"),
        ("activity", "Activity", "Ctrl+8"),
        ("help", "Help Center", "Ctrl+9"),
    )
    source = inspect.getsource(ManagerWindow._build)
    assert 'text="PLAYER WORKSPACES"' in source
    assert 'logo.thumbnail((180, 88)' in source
    assert 'text="ALLIN1 · GTA V Launcher"' in source
    assert 'text="Support ALLIN1 ↗"' in source
    assert 'text="<"' in source
    assert 'self.root.bind("<Control-b>"' in source
    assert 'self.root.bind("<Control-Tab>"' in source
    assert 'style="WarningPanel.TFrame"' in source
    assert 'text="Add package…"' in source
    assert 'text="Selected package"' in source
    assert "typed settings" not in source
    assert "versioned API" not in source


def test_launcher_builds_offscreen_before_first_themed_paint() -> None:
    from allin1.gui import main

    source = inspect.getsource(main)
    assert source.index("root.withdraw()") < source.index("ManagerWindow(root")
    assert source.index("ManagerWindow(root") < source.index("root.deiconify()")


def test_sidebar_toggle_preserves_the_active_workspace() -> None:
    window = ManagerWindow.__new__(ManagerWindow)
    window.sidebar_visible = Mock()
    window.workspace_sidebar = Mock()
    window.sidebar_toggle_rail = Mock()
    window.sidebar_toggle_button = Mock()
    window.current_workspace = "mods"

    assert window._set_sidebar_visible(False) == "break"
    window.sidebar_visible.set.assert_called_with(False)
    window.workspace_sidebar.pack_forget.assert_called_once_with()
    assert window.current_workspace == "mods"

    window.workspace_sidebar.winfo_manager.return_value = ""
    assert window._set_sidebar_visible(True) == "break"
    window.workspace_sidebar.pack.assert_called_once_with(
        side="left", fill="y", before=window.sidebar_toggle_rail,
    )
    assert window.current_workspace == "mods"


def test_theme_selection_persists_without_dirtying_gameplay_settings(
    tmp_path, monkeypatch,
) -> None:
    window = ManagerWindow.__new__(ManagerWindow)
    window.theme_mode = Mock()
    window.ui_settings_path = tmp_path / "ui-settings.json"
    window._apply_theme = Mock()
    window.notice_text = Mock()
    saved = []
    monkeypatch.setattr(
        "allin1.gui.save_ui_settings",
        lambda settings, path: saved.append((settings, path)),
    )

    window._set_theme("DARK")

    window.theme_mode.set.assert_called_once_with("dark")
    assert saved == [(UiSettings(theme="dark"), window.ui_settings_path)]
    window._apply_theme.assert_called_once_with()
    window.notice_text.set.assert_called_once_with("Dark theme active")


def test_system_theme_poll_repaints_only_when_effective_theme_changes(
    tmp_path, monkeypatch,
) -> None:
    window = ManagerWindow.__new__(ManagerWindow)
    window.ui_settings_path = tmp_path / "ui-settings.json"
    window.theme_mode = Mock()
    window.theme_mode.get.return_value = "system"
    window._resolved_theme = "light"
    window._apply_theme = Mock()
    window.root = Mock()
    window.root.after.return_value = "theme-poll"
    monkeypatch.setattr(
        "allin1.gui.load_ui_settings", lambda _path: UiSettings(theme="system"),
    )
    monkeypatch.setattr("allin1.gui.detect_system_theme", lambda: "dark")

    window._poll_theme()

    window._apply_theme.assert_called_once_with()
    window.root.after.assert_called_once_with(1500, window._poll_theme)
    assert window._theme_poll_after_id == "theme-poll"

def test_workspace_cycle_wraps_in_both_directions() -> None:
    window = ManagerWindow.__new__(ManagerWindow)
    window._select_workspace = Mock()
    window.current_workspace = "help"

    assert window._cycle_workspace() == "break"
    window._select_workspace.assert_called_once_with("setup")

    window._select_workspace.reset_mock()
    window.current_workspace = "setup"
    assert window._cycle_workspace(direction=-1) == "break"
    window._select_workspace.assert_called_once_with("help")


@pytest.mark.parametrize(
    ("selected", "expected_label", "expected_states"),
    [
        (None, "Install / update", ("disabled", "disabled", "disabled", "disabled")),
        ("available", "Install / update", ("normal", "disabled", "disabled", "disabled")),
        ("installed", "Install / update", ("normal", "normal", "normal", "normal")),
        ("builtin:item", "Install / Repair", ("normal", "normal", "normal", "disabled")),
        ("sdk:item", "Open in ALLIN1 SDK", ("normal", "disabled", "disabled", "disabled")),
    ],
)
def test_package_action_menu_exposes_only_valid_actions(
    selected, expected_label, expected_states,
) -> None:
    window = ManagerWindow.__new__(ManagerWindow)
    window._selected_mod_id = Mock(return_value=selected)
    window.mod_manifests = {
        "available": Mock(), "installed": Mock(),
    }
    window.installed_mod_ids = {"installed"}
    window.builtin_package_manifests = {"builtin:item": Mock()}
    window.builtin_package_entries = {"builtin:item": {"enabled": True}}
    window.sdk_manifests = {"sdk:item": Mock()}
    window.package_action_menu = Mock()

    window._prepare_package_action_menu()

    calls = window.package_action_menu.entryconfigure.call_args_list
    assert calls[0].kwargs["label"] == expected_label
    states = tuple(calls[index].kwargs["state"] for index in range(1, 5))
    assert states == expected_states


class Variable:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value


def _window():
    window = ManagerWindow.__new__(ManagerWindow)
    window.reactor_bootstrap = None
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
    content_catalog = Mock()
    content_catalog.discover.return_value = []
    window.manager = SimpleNamespace(extension_catalog=content_catalog)
    window._content_registry = Mock(side_effect=ValueError("game not selected"))

    window.refresh_mods()

    assert window.sdk_manifests == {"sdk:allin1.colored_smokes": smoke}
    window.mod_tree.insert.assert_called_once_with(
        "", "end", iid="sdk:allin1.colored_smokes",
        text="ALLIN1 Colored Smoke Grenades",
        values=("SDK", "Enhanced", "1.0.0", "Built-in example"),
    )


def test_mod_package_list_includes_all_builtin_content_packages():
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    experiments = ExtensionManifest.load(
        ROOT / "content" / "allin1-experimental-gameplay" / "allin1.content.json"
    )
    window = ManagerWindow.__new__(ManagerWindow)
    window.mod_tree = Mock()
    window.mod_tree.selection.return_value = ()
    window.mod_tree.get_children.return_value = ()
    window.mod_catalog = Mock()
    window.mod_catalog.discover.return_value = []
    window.sdk_catalog = Mock()
    window.sdk_catalog.discover.return_value = []
    window.mod_details = Mock()
    content_catalog = Mock()
    content_catalog.discover.return_value = [online, experiments]
    window.manager = SimpleNamespace(extension_catalog=content_catalog)
    registry = Mock()
    registry.installed.return_value = [
        {"id": online.extension_id, "source": "built-in", "enabled": True},
        {"id": experiments.extension_id, "source": "built-in", "enabled": False},
        {"id": "third.party", "source": "package", "enabled": True},
    ]
    window._content_registry = Mock(return_value=registry)
    service = Mock()
    service.list_installed.return_value = []
    window._mod_service = Mock(return_value=service)

    window.refresh_mods()

    assert set(window.builtin_package_manifests) == {
        f"builtin:{online.extension_id}",
        f"builtin:{experiments.extension_id}",
    }
    window.mod_tree.insert.assert_any_call(
        "", "end", iid=f"builtin:{online.extension_id}", text=online.name,
        values=("CONTENT", "Legacy + Enhanced", online.version, "Enabled"),
    )
    window.mod_tree.insert.assert_any_call(
        "", "end", iid=f"builtin:{experiments.extension_id}",
        text=experiments.name,
        values=("CONTENT", "Legacy + Enhanced", experiments.version, "Disabled"),
    )
    assert window.mod_tree.insert.call_count == 2


def test_builtin_package_actions_use_registry_and_protect_uninstall(monkeypatch):
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    item_id = f"builtin:{online.extension_id}"
    window = ManagerWindow.__new__(ManagerWindow)
    window._selected_mod_id = Mock(return_value=item_id)
    window.builtin_package_manifests = {item_id: online}
    window.builtin_package_entries = {
        item_id: {"id": online.extension_id, "source": "built-in", "enabled": True},
    }
    window.notice_text = Mock()
    window.refresh_mods = Mock()
    window.refresh_content = Mock()
    window.install = Mock()
    registry = Mock()
    window._content_registry = Mock(return_value=registry)
    showinfo = Mock()
    monkeypatch.setattr("allin1.gui.messagebox.showinfo", showinfo)

    window.install_selected_mod()
    window.toggle_selected_mod(False)
    window.uninstall_selected_mod()

    window.install.assert_called_once_with()
    registry.set_builtin_enabled.assert_called_once_with(
        online.extension_id, False,
    )
    window.refresh_mods.assert_called_once_with()
    window.refresh_content.assert_called_once_with()
    assert "cannot be uninstalled" in showinfo.call_args.args[1]


def test_builtin_package_details_point_to_content_workspace():
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    item_id = f"builtin:{online.extension_id}"
    window = ManagerWindow.__new__(ManagerWindow)
    window._selected_mod_id = Mock(return_value=item_id)
    window.mod_manifests = {}
    window.sdk_manifests = {}
    window.builtin_package_manifests = {item_id: online}
    window.builtin_package_entries = {
        item_id: {"enabled": True, "source": "built-in"},
    }
    window.mod_details = Mock()

    window._show_mod_details()

    detail = window.mod_details.set.call_args.args[0]
    assert "Built into ALLIN1" in detail
    assert "Open Content to configure" in detail


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
    executable = window.sdk_install_root / "ALLIN1-SDK-Desktop.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZsdk")
    (window.sdk_install_root / "allin1-sdk.exe").write_bytes(b"MZcli")
    (window.sdk_install_root / "release.json").write_text(
        '{"product":"ALLIN1-SDK","version":"0.4.8"}'
    )
    launched = Mock()
    monkeypatch.setattr("allin1.gui.subprocess.Popen", launched)
    monkeypatch.setattr("allin1.gui.shutil.which", lambda _name: None)

    window.open_addon_sdk()

    launched.assert_called_once()
    assert launched.call_args.args[0] == [str(executable)]


def test_frozen_launcher_gives_sdk_explicit_navigation_route(tmp_path, monkeypatch):
    window = ManagerWindow.__new__(ManagerWindow)
    window.manager = SimpleNamespace(project_root=tmp_path / "ALLIN1")
    window.sdk_install_root = tmp_path / "local" / "ALLIN1" / "SDK"
    window._append_log = Mock()
    executable = window.sdk_install_root / "ALLIN1-SDK-Desktop.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"MZsdk")
    (window.sdk_install_root / "allin1-sdk.exe").write_bytes(b"MZcli")
    (window.sdk_install_root / "release.json").write_text(
        '{"product":"ALLIN1-SDK","version":"0.5.4"}'
    )
    launched = Mock()
    monkeypatch.setattr("allin1.gui.subprocess.Popen", launched)
    monkeypatch.setattr("allin1.gui.shutil.which", lambda _name: None)
    monkeypatch.setattr("allin1.gui.sys.frozen", True, raising=False)

    window.open_addon_sdk()

    environment = launched.call_args.kwargs["env"]
    assert environment["ALLIN1_LAUNCHER_EXECUTABLE"] == sys.executable


def test_repair_progress_text_clamps_percentages():
    assert _operation_progress_text("Repairing", -5) == "Repairing - 0%"
    assert _operation_progress_text("Repairing", 47) == "Repairing - 47%"
    assert _operation_progress_text("Repairing", 150) == "Repairing - 100%"


def test_install_offers_verified_optional_rpf_loader(tmp_path, monkeypatch):
    window = _window()
    window.root = Mock()
    window.messages = queue.Queue()
    window.manager = Mock()
    window.manager.status.return_value = _status(
        gta_path=tmp_path,
        valid_game=True,
        edition="Enhanced",
        openrpf_installed=False,
    )
    window._run = Mock(side_effect=lambda _label, worker, **_kwargs: worker())
    approved = Mock(return_value=True)
    monkeypatch.setattr("allin1.gui.messagebox.askyesno", approved)

    window.install()

    approved.assert_called_once()
    kwargs = window.manager.install.call_args.kwargs
    assert kwargs["rpf_loader_consent"](tmp_path, True) is True
    assert callable(kwargs["progress"])


def test_content_workspace_renders_every_declared_system():
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    window = ManagerWindow.__new__(ManagerWindow)
    window.content_tree = Mock()
    window.content_tree.selection.return_value = ()
    window.content_tree.get_children.return_value = ()
    window.content_detail_title = Mock()
    window.content_detail_text = Mock()
    catalog = Mock()
    catalog.discover.return_value = [online]
    window.manager = SimpleNamespace(extension_catalog=catalog)
    registry = Mock()
    registry.installed.return_value = []
    window._content_registry = Mock(return_value=registry)

    window.refresh_content()

    assert window.content_manifests == {online.extension_id: online}
    assert window.content_registry_entries == {}
    assert window.content_registry_error == ""
    assert set(window.content_tree_items.values()) == {
        (online.extension_id, None),
        *((online.extension_id, system.system_id) for system in online.systems),
    }
    assert window.content_tree.insert.call_count == 1 + len(online.systems)
    package_call = window.content_tree.insert.call_args_list[0]
    assert package_call.kwargs["text"] == "ALLIN1 Online Content"
    assert package_call.kwargs["values"] == (
        "Package", "0.6.1", "Install / Repair",
    )


def test_content_workspace_surfaces_registry_failure():
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    window = ManagerWindow.__new__(ManagerWindow)
    window.content_tree = Mock()
    window.content_tree.selection.return_value = ()
    window.content_tree.get_children.return_value = ()
    window.content_detail_title = Mock()
    window.content_detail_text = Mock()
    catalog = Mock()
    catalog.discover.return_value = [online]
    window.manager = SimpleNamespace(extension_catalog=catalog)
    registry = Mock()
    registry.installed.side_effect = ValueError("registry is corrupt")
    window._content_registry = Mock(return_value=registry)

    window.refresh_content()

    assert window.content_registry_error == "registry is corrupt"
    package_call = window.content_tree.insert.call_args_list[0]
    assert package_call.kwargs["values"] == (
        "Package", "0.6.1", "Registry error",
    )


def test_content_workspace_saves_namespaced_package_settings():
    manifest = ExtensionManifest.from_dict({
        "schema_version": 1,
        "api_version": 1,
        "id": "example.content",
        "name": "Example Content",
        "version": "1.0.0",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "display",
            "name": "Display",
            "settings": [{
                "key": "show_hints",
                "label": "Show hints",
                "type": "boolean",
                "default": True,
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    })
    window = _window()
    window.content_selected_system = (manifest.extension_id, "display")
    window.content_manifests = {manifest.extension_id: manifest}
    window.content_registry_entries = {
        manifest.extension_id: {"source": "package", "enabled": True},
    }
    window.content_setting_vars = {
        (manifest.extension_id, "show_hints"): Variable(False),
    }
    window.manager = Mock()
    registry = Mock()
    window._content_registry = Mock(return_value=registry)
    window.notice_text = Mock()
    window.refresh_content = Mock()

    window.apply_content_settings()

    window.manager.save_config.assert_called_once()
    registry.set_settings.assert_called_once_with(
        manifest.extension_id, {"show_hints": False},
    )
    window.notice_text.set.assert_called_once_with("Saved settings for Display")
    window.refresh_content.assert_called_once_with()


def test_content_workspace_toggles_builtins_through_registry():
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    window = ManagerWindow.__new__(ManagerWindow)
    window.content_selected_system = (online.extension_id, None)
    window.content_manifests = {online.extension_id: online}
    window.content_registry_entries = {
        online.extension_id: {"source": "built-in", "enabled": True},
    }
    registry = Mock()
    window._content_registry = Mock(return_value=registry)
    window._mod_service = Mock()
    window.notice_text = Mock()
    window.refresh_mods = Mock()
    window.refresh_content = Mock()

    window.toggle_selected_content(False)

    registry.set_builtin_enabled.assert_called_once_with(
        online.extension_id, False,
    )
    window._mod_service.assert_not_called()
    window.refresh_mods.assert_called_once_with()
    window.refresh_content.assert_called_once_with()


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
    events = []
    bootstrap = Mock()
    bootstrap.mark_launch_requested.side_effect = lambda: events.append("handoff")
    factory = Mock(side_effect=lambda *_args, **_kwargs: (
        events.append("bootstrap") or bootstrap
    ))
    preloader = Mock(reason="Reactor V browser warm-up started.")
    preloader_factory = Mock(side_effect=lambda *_args, **_kwargs: (
        events.append("preloader") or preloader
    ))
    target = Mock(description="GTA V Enhanced through Steam")
    launcher = Mock(side_effect=lambda _path: events.append("launch") or target)
    monkeypatch.setattr("allin1.gui.start_reactor_bootstrap", factory)
    monkeypatch.setattr("allin1.gui.start_reactor_preloader", preloader_factory)
    monkeypatch.setattr("allin1.gui.launch_gta", launcher)

    window.launch_game()
    window.launch_game()

    launcher.assert_called_once_with(tmp_path)
    factory.assert_called_once_with(
        window.root,
        tmp_path,
        on_log=window._append_log,
        on_closed=window._reactor_bootstrap_closed,
    )
    preloader_factory.assert_called_once_with(tmp_path)
    assert events == ["bootstrap", "preloader", "launch", "handoff"]
    window.root.after.assert_called_once_with(15000, window._reset_launch_guard)


def test_launch_failure_stops_reactor_bootstrap(tmp_path, monkeypatch):
    window = _window()
    window.busy = False
    window.launch_pending = False
    window.manager = Mock()
    window.manager.resolve_path.return_value = tmp_path
    window.launch_button = Mock()
    window.root = Mock()
    window._append_log = Mock()
    bootstrap = Mock()
    preloader = Mock(reason="Reactor V browser warm-up started.")
    monkeypatch.setattr(
        "allin1.gui.start_reactor_bootstrap", Mock(return_value=bootstrap),
    )
    monkeypatch.setattr(
        "allin1.gui.start_reactor_preloader", Mock(return_value=preloader),
    )
    monkeypatch.setattr(
        "allin1.gui.launch_gta", Mock(side_effect=OSError("storefront failed")),
    )
    shown = Mock()
    monkeypatch.setattr("allin1.gui.messagebox.showerror", shown)

    window.launch_game()

    bootstrap.stop.assert_called_once_with()
    preloader.stop.assert_called_once_with()
    assert window.reactor_bootstrap is None
    assert window.launch_pending is False
    shown.assert_called_once()


def test_close_stops_active_reactor_bootstrap():
    window = ManagerWindow.__new__(ManagerWindow)
    window.busy = False
    window.settings_dirty = False
    window.root = Mock()
    reactor = Mock()
    window.reactor_bootstrap = reactor

    window._on_close()

    reactor.stop.assert_called_once_with()
    assert window.reactor_bootstrap is None
    window.root.destroy.assert_called_once_with()


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
    window.night_vision_key = Variable("F8")
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
