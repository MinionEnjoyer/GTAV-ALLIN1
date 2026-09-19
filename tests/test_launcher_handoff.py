import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from allin1 import cli
from allin1.launcher_handoff import (
    LauncherHandoff,
    consume_launcher_handoffs,
    launcher_process_command,
    launcher_request_root,
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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ({"extra": True}, "unsupported fields"),
        ({"version": 1, "action": "install"}, "action"),
        ({"version": 1, "action": "show_packages", "request_id": "bad"}, "request id"),
        ({"version": 1, "action": "show_packages", "request_id": "a" * 32,
          "package_id": "studio.pagani", "traffic": "yes", "created_at": 1.0}, "traffic"),
        ({"version": 1, "action": "show_packages", "request_id": "a" * 32,
          "package_id": None, "traffic": True, "created_at": 1.0}, "requires a package id"),
    ],
)
def test_handoff_rejects_untrusted_request_shapes(payload, message):
    with pytest.raises(ValueError, match=message):
        LauncherHandoff.from_dict(payload)


def test_consumer_is_empty_without_request_inbox(tmp_path):
    assert consume_launcher_handoffs(environment=_environment(tmp_path), now=100.0) == ()


def test_handoff_inbox_fallback_and_size_limits_keep_invalid_requests_unconsumed(tmp_path):
    fallback = launcher_request_root({})
    assert fallback.name == "Requests"
    assert fallback.parent.name == "Launcher"

    huge = SimpleNamespace(request_id="a" * 32, to_dict=lambda: {"payload": "x" * 5000})
    with pytest.raises(ValueError, match="size limit"):
        publish_launcher_handoff(huge, environment=_environment(tmp_path))

    root = launcher_request_root(_environment(tmp_path))
    root.mkdir(parents=True, exist_ok=True)
    (root / ("b" * 32 + ".json")).write_text("x" * 5000, encoding="utf-8")
    assert consume_launcher_handoffs(environment=_environment(tmp_path), now=100.0) == ()
    assert not list(root.glob("*.json"))


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


def test_launcher_command_discovers_gui_entry_or_requires_explicit_path(monkeypatch):
    handoff = LauncherHandoff.create("studio.pagani", now=100.0)
    monkeypatch.setattr("allin1.launcher_handoff.shutil.which", lambda name: "/tools/" + name)
    assert launcher_process_command(handoff, environment={})[:1] == ["/tools/allin1-launcher-desktop"]

    monkeypatch.setattr("allin1.launcher_handoff.shutil.which", lambda name: None)
    monkeypatch.setattr("allin1.launcher_handoff.sys.frozen", False, raising=False)
    with pytest.raises(ValueError, match="executable was not found"):
        launcher_process_command(handoff, environment={})


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
    ], close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


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
