"""Standalone package and launcher lifecycle coverage for Realistic Suppressors."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from unittest.mock import Mock

import pytest

from allin1.extensions import ExtensionRegistry
from allin1.gui import ManagerWindow
from allin1.mods import ModIntegrationService, ModManifest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "mods" / "realistic-suppressors"
PACKAGE_ID = "realistic-suppressors"
MANAGED_DESTINATIONS = {
    "scripts/RealisticSuppressors/RealisticSuppressors.dll",
    "scripts/RealisticSuppressors/allin1.content.json",
}


def _write_pe(path: Path) -> None:
    payload = bytearray(4096)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _game(tmp_path: Path, edition: str) -> Path:
    game = tmp_path / edition
    game.mkdir()
    executable = "GTA5.exe" if edition == "legacy" else "GTA5_Enhanced.exe"
    (game / executable).write_bytes(b"synthetic GTA V executable")
    _write_pe(game / "ScriptHookVDotNet.asi")
    return game


def _installed_paths(game: Path) -> dict[str, Path]:
    return {
        destination: game / Path(destination)
        for destination in MANAGED_DESTINATIONS
    }


def test_realistic_suppressors_is_a_standalone_schema_v2_package() -> None:
    manifest = ModManifest.load(PACKAGE)

    assert manifest.mod_id == PACKAGE_ID
    assert manifest.name == "Realistic Suppressors"
    assert manifest.version == "1.0.0"
    assert manifest.mod_type == "script"
    assert manifest.editions == ("legacy", "enhanced")
    assert manifest.dependencies == ("shvdn",)
    assert manifest.conflicts == ()
    assert manifest.package_requirements == ()
    assert {
        item.destination.as_posix() for item in manifest.files
    } == MANAGED_DESTINATIONS
    assert all(
        item.destination.as_posix().startswith("scripts/RealisticSuppressors/")
        for item in manifest.files
    )
    assert all(
        item.destination.as_posix().casefold() != "scripts/allin1.dll"
        for item in manifest.files
    )

    extension = manifest.extension
    assert extension is not None
    assert extension.extension_id == PACKAGE_ID
    assert set(extension.capabilities) == {
        "launcher.settings",
        "story-save.transactions",
        "weapon.components.lifecycle",
    }
    assert [assembly.path.as_posix() for assembly in extension.runtime_assemblies] == [
        "scripts/RealisticSuppressors/RealisticSuppressors.dll"
    ]
    assert extension.runtime_assemblies[0].entry_point == (
        "RealisticSuppressors.RealisticSuppressorController"
    )

    stealth = extension.setting("realistic_suppressors")
    assert stealth.setting_type == "boolean"
    assert stealth.default is True
    assert stealth.config_key is None

    breakage = extension.setting("suppressor_breakage")
    assert breakage.setting_type == "boolean"
    assert breakage.default is True
    assert breakage.config_key is None

    durability = extension.setting("suppressor_durability_scale")
    assert durability.setting_type == "number"
    assert durability.default == 1.0
    assert durability.minimum == 0.5
    assert durability.maximum == 3.0
    assert durability.step == 0.25
    assert durability.config_key is None

    builtin_descriptor = (
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    ).read_text(encoding="utf-8")
    assert "realistic_suppressors" not in builtin_descriptor
    assert "suppressor_breakage" not in builtin_descriptor
    assert not (ROOT / "script" / "src" / "RealisticSuppressorController.cs").exists()


@pytest.mark.parametrize("edition", ["legacy", "enhanced"])
def test_launcher_round_trip_preserves_core_and_unowned_files(
    tmp_path: Path, edition: str,
) -> None:
    game = _game(tmp_path, edition)
    scripts = game / "scripts"
    package_runtime = scripts / "RealisticSuppressors"
    package_runtime.mkdir(parents=True)

    sentinels = {
        scripts / "ALLIN1.dll": b"ALLIN1 core sentinel",
        scripts / "OtherMod.dll": b"unrelated mod sentinel",
        package_runtime / "runtime-state.json": b'{"condition":"retained"}',
    }
    for path, payload in sentinels.items():
        path.write_bytes(payload)

    manifest = ModManifest.load(PACKAGE)
    service = ModIntegrationService(game)
    installed = service.install(manifest)
    targets = _installed_paths(game)

    assert installed.installed is True
    assert installed.enabled is True
    assert service.edition == edition
    assert service.list_installed() == [installed]
    source_by_destination = {
        item.destination.as_posix(): PACKAGE / Path(*item.source.parts)
        for item in manifest.files
    }
    for destination, target in targets.items():
        assert target.read_bytes() == source_by_destination[destination].read_bytes()

    receipt_path = service.state_root / f"{PACKAGE_ID}.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 2
    assert receipt["id"] == PACKAGE_ID
    assert receipt["type"] == "script"
    assert receipt["enabled"] is True
    assert receipt["dependencies"] == ["shvdn"]
    assert receipt["requires"] == []
    assert receipt["extension"]["id"] == PACKAGE_ID
    assert {item["destination"] for item in receipt["files"]} == (
        MANAGED_DESTINATIONS
    )
    for item in receipt["files"]:
        source = source_by_destination[item["destination"]]
        assert item["backup"] is None
        assert item["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()

    registry_entry = ExtensionRegistry(game).installed()[0]
    assert registry_entry["id"] == PACKAGE_ID
    assert registry_entry["source"] == "package"
    assert registry_entry["enabled"] is True
    assert registry_entry["settings"] == {
        "realistic_suppressors": True,
        "suppressor_breakage": True,
        "suppressor_durability_scale": 1.0,
    }
    assert registry_entry["runtime_files"] == [{
        "path": "scripts/RealisticSuppressors/RealisticSuppressors.dll",
        "sha256": hashlib.sha256(
            targets[
                "scripts/RealisticSuppressors/RealisticSuppressors.dll"
            ].read_bytes()
        ).hexdigest(),
    }]
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())

    disabled = service.set_enabled(PACKAGE_ID, False)
    assert disabled.enabled is False
    for target in targets.values():
        assert not target.exists()
        assert target.with_name(target.name + ".disabled").is_file()
    disabled_entry = ExtensionRegistry(game).installed()[0]
    assert disabled_entry["id"] == PACKAGE_ID
    assert disabled_entry["enabled"] is False
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())

    enabled = service.set_enabled(PACKAGE_ID, True)
    assert enabled.enabled is True
    for destination, target in targets.items():
        assert target.read_bytes() == source_by_destination[destination].read_bytes()
        assert not target.with_name(target.name + ".disabled").exists()
    assert ExtensionRegistry(game).installed()[0]["enabled"] is True

    service.uninstall(PACKAGE_ID)

    assert service.list_installed() == []
    assert not receipt_path.exists()
    assert ExtensionRegistry(game).installed() == []
    for target in targets.values():
        assert not target.exists()
        assert not target.with_name(target.name + ".disabled").exists()
    assert all(path.read_bytes() == payload for path, payload in sentinels.items())
    assert package_runtime.is_dir()
    assert set(package_runtime.iterdir()) == {package_runtime / "runtime-state.json"}


def test_launcher_gui_routes_standalone_package_lifecycle(monkeypatch) -> None:
    manifest = ModManifest.load(PACKAGE, validate_payload=False)
    service = Mock()
    window = ManagerWindow.__new__(ManagerWindow)
    window._selected_mod_id = Mock(return_value=PACKAGE_ID)
    window.builtin_package_manifests = {}
    window.builtin_package_entries = {}
    window.sdk_manifests = {}
    window.mod_manifests = {PACKAGE_ID: manifest}
    window.installed_mod_ids = {PACKAGE_ID}
    window._mod_service = Mock(return_value=service)
    window._run = Mock(side_effect=lambda _label, action: action())
    monkeypatch.setattr("allin1.gui.messagebox.askyesno", lambda *_args: True)

    window.install_selected_mod()
    window.toggle_selected_mod(False)
    window.toggle_selected_mod(True)
    window.uninstall_selected_mod()

    service.install.assert_called_once_with(manifest)
    assert service.set_enabled.call_args_list == [
        ((PACKAGE_ID, False),),
        ((PACKAGE_ID, True),),
    ]
    service.uninstall.assert_called_once_with(PACKAGE_ID)
