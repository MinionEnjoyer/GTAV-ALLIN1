import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from allin1 import cli
from allin1.gui import (
    ManagerWindow,
    _parse_launcher_arguments,
    _supports_package_traffic_intent,
)
from allin1.launcher_handoff import (
    LauncherHandoff,
    consume_launcher_handoffs,
    launcher_process_command,
    open_launcher_packages,
    publish_launcher_handoff,
)
from allin1.mods import ModCatalog


def _environment(tmp_path: Path) -> dict[str, str]:
    return {"LOCALAPPDATA": str(tmp_path)}


def test_handoff_round_trip_is_typed_atomic_and_one_shot(tmp_path):
    handoff = LauncherHandoff.create(
        "studio.pagani", traffic=True, now=100.0,
    )
    path = publish_launcher_handoff(
        handoff, environment=_environment(tmp_path),
    )

    assert path.suffix == ".json"
    assert not list(path.parent.glob("*.tmp"))
    assert consume_launcher_handoffs(
        environment=_environment(tmp_path), now=101.0,
    ) == (handoff,)
    assert consume_launcher_handoffs(
        environment=_environment(tmp_path), now=101.0,
    ) == ()


@pytest.mark.parametrize(
    ("package_id", "traffic"),
    [
        ("../escape", None),
        ("C:/payload", None),
        ("A", None),
        (None, True),
    ],
)
def test_handoff_rejects_paths_and_unbound_intent(package_id, traffic):
    with pytest.raises(ValueError):
        LauncherHandoff.create(package_id, traffic=traffic)


@pytest.mark.parametrize("package_id", [True, 1, [], {}])
def test_handoff_rejects_non_string_package_ids(package_id):
    with pytest.raises(ValueError, match="must be a string"):
        LauncherHandoff.from_dict({
            "version": 1,
            "action": "show_packages",
            "request_id": "a" * 32,
            "package_id": package_id,
            "traffic": None,
            "created_at": 1.0,
        })


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("version", True, "version"),
        ("created_at", True, "timestamp"),
    ],
)
def test_handoff_rejects_boolean_numeric_fields(field, value, message):
    payload = {
        "version": 1,
        "action": "show_packages",
        "request_id": "a" * 32,
        "package_id": "studio.pagani",
        "traffic": None,
        "created_at": 1.0,
    }
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        LauncherHandoff.from_dict(payload)


def test_consumer_discards_stale_and_unstructured_requests(tmp_path):
    environment = _environment(tmp_path)
    stale = LauncherHandoff.create("studio.pagani", now=10.0)
    publish_launcher_handoff(stale, environment=environment)
    root = path = publish_launcher_handoff(
        LauncherHandoff.create("studio.audi", now=100.0), environment=environment,
    ).parent
    (root / "bad.json").write_text(json.dumps({"action": "install"}))

    accepted = consume_launcher_handoffs(environment=environment, now=100.0)

    assert tuple(item.package_id for item in accepted) == ("studio.audi",)
    assert not list(path.glob("*.json"))


def test_launcher_command_is_argv_only_and_carries_non_mutating_intent(tmp_path):
    executable = tmp_path / "ALLIN1 Launcher.exe"
    handoff = LauncherHandoff.create("studio.pagani", traffic=False)

    assert launcher_process_command(handoff, executable=executable) == [
        str(executable),
        "--workspace", "packages",
        "--package-id", "studio.pagani",
        "--traffic", "off",
    ]


def test_open_launcher_packages_uses_validated_process_arguments(monkeypatch, tmp_path):
    popen = Mock(return_value=Mock())
    monkeypatch.setattr("allin1.launcher_handoff.subprocess.Popen", popen)
    executable = tmp_path / "launcher.exe"

    result = open_launcher_packages(
        "studio.pagani", traffic=True, executable=executable,
    )

    assert result is popen.return_value
    popen.assert_called_once_with([
        str(executable), "--workspace", "packages",
        "--package-id", "studio.pagani", "--traffic", "on",
    ], close_fds=True)


def test_gui_argument_contract_is_narrow_and_validated():
    request = _parse_launcher_arguments([
        "--workspace", "packages", "--package-id", "studio.pagani",
        "--traffic", "on",
    ])
    assert request is not None
    assert request.package_id == "studio.pagani"
    assert request.traffic is True
    assert _parse_launcher_arguments([]) is None
    with pytest.raises(SystemExit):
        _parse_launcher_arguments(["--package-id", "studio.pagani"])


def test_cli_route_forwards_selection_without_install_authority(monkeypatch, tmp_path):
    launched = Mock()
    monkeypatch.setattr(cli, "open_launcher_packages", launched)
    monkeypatch.setattr(cli, "setup_logging", Mock())
    monkeypatch.setattr(cli, "DEFAULT_CONFIG", tmp_path / "missing.toml")
    executable = tmp_path / "launcher.exe"

    result = CliRunner().invoke(cli.main, [
        "open-launcher", "--package-id", "studio.pagani", "--traffic",
        "--launcher-path", str(executable),
    ])

    assert result.exit_code == 0, result.output
    launched.assert_called_once_with(
        "studio.pagani", traffic=True, executable=executable,
    )
    assert "Opened Launcher Packages" in result.output


def _handoff_window(manifest) -> ManagerWindow:
    window = ManagerWindow.__new__(ManagerWindow)
    window._select_workspace = Mock()
    window._refresh_mods_if_changed = Mock()
    window.mod_manifests = {"studio.pagani": manifest}
    window.package_handoff_intents = {}
    window.mod_tree = Mock()
    window.mod_tree.exists.return_value = True
    window._show_mod_details = Mock()
    window.notice_text = Mock()
    window.mod_details = Mock()
    window.root = Mock()
    return window


def test_running_launcher_handoff_only_selects_discovered_package():
    manifest = Mock()
    manifest.extension = None
    window = _handoff_window(manifest)

    window._show_launcher_handoff(
        LauncherHandoff.create("studio.pagani", traffic=True),
    )

    window._select_workspace.assert_called_once_with("mods")
    window._refresh_mods_if_changed.assert_called_once_with()
    window.mod_tree.selection_set.assert_called_once_with("studio.pagani")
    window.mod_tree.focus.assert_called_once_with("studio.pagani")
    window.mod_tree.see.assert_called_once_with("studio.pagani")
    assert window.package_handoff_intents == {"studio.pagani": True}


def test_running_launcher_refuses_to_select_undiscovered_package():
    window = _handoff_window(Mock())
    window.mod_manifests = {}
    window.mod_tree.exists.return_value = False

    window._show_launcher_handoff(LauncherHandoff.create("studio.unknown"))

    window.mod_tree.selection_set.assert_not_called()
    assert "not in the shared package library" in window.mod_details.set.call_args.args[0]


def test_package_watcher_is_lazy_and_refreshes_only_on_change():
    window = ManagerWindow.__new__(ManagerWindow)
    window.root = Mock()
    window.current_workspace = "setup"
    window.mod_catalog = Mock()
    window._mod_catalog_fingerprint = (("old", 1, 1),)
    window.refresh_mods = Mock()

    window._watch_package_library()
    window.mod_catalog.fingerprint.assert_not_called()
    window.refresh_mods.assert_not_called()

    window.current_workspace = "mods"
    window.mod_catalog.fingerprint.return_value = (("new", 2, 2),)
    window._watch_package_library()
    window.refresh_mods.assert_called_once_with()


def test_catalog_fingerprint_tracks_manifests_without_walking_payloads(tmp_path):
    catalog_root = tmp_path / "catalog"
    package = catalog_root / "studio.pagani"
    package.mkdir(parents=True)
    catalog = ModCatalog(catalog_root)
    before = catalog.fingerprint()
    payload = package / "very-large.rpf"
    payload.write_bytes(b"payload")

    # Payload churn alone does not trigger UI reconstruction.
    assert catalog.fingerprint() == before
    (package / "mod.toml").write_text("schema_version = 1\n")
    assert catalog.fingerprint() != before


def _traffic_manifest() -> SimpleNamespace:
    setting = SimpleNamespace(setting_type="boolean", default=False)
    extension = SimpleNamespace(
        capabilities=("launcher.settings", "traffic.catalog"),
        setting=Mock(return_value=setting),
    )
    return SimpleNamespace(
        mod_id="studio.pagani", name="Pagani", version="1.0.0",
        extension=extension,
    )


def test_traffic_intent_requires_typed_default_off_package_setting():
    manifest = _traffic_manifest()
    assert _supports_package_traffic_intent(manifest) is True
    manifest.extension.capabilities = ("launcher.settings",)
    assert _supports_package_traffic_intent(manifest) is False


def test_traffic_intent_is_confirmed_and_applied_only_after_install(
    monkeypatch, tmp_path,
):
    manifest = _traffic_manifest()
    service = SimpleNamespace(gta_path=tmp_path, install=Mock(return_value=Mock()))
    window = ManagerWindow.__new__(ManagerWindow)
    window.package_handoff_intents = {manifest.mod_id: True}
    window._mod_service = Mock(return_value=service)
    window._run = Mock(side_effect=lambda _label, operation: operation())
    confirm = Mock(return_value=True)
    monkeypatch.setattr("allin1.gui.messagebox.askyesno", confirm)

    window._install_mod_manifest(manifest)

    assert "allowed in ambient traffic" in confirm.call_args.args[1]
    service.install.assert_called_once_with(
        manifest, initial_settings={"traffic_enabled": True},
    )
    assert manifest.mod_id not in window.package_handoff_intents


def test_declined_install_never_applies_traffic_intent(monkeypatch):
    manifest = _traffic_manifest()
    window = ManagerWindow.__new__(ManagerWindow)
    window.package_handoff_intents = {manifest.mod_id: True}
    window._mod_service = Mock()
    window._run = Mock()
    monkeypatch.setattr("allin1.gui.messagebox.askyesno", Mock(return_value=False))

    window._install_mod_manifest(manifest)

    window._mod_service.assert_not_called()
    window._run.assert_not_called()
