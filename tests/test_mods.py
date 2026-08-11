"""Synthetic coverage for optional, user-supplied mod integrations."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from allin1.mods import ModCatalog, ModIntegrationService, ModManifest


def _game(tmp_path: Path, *, enhanced: bool = True) -> Path:
    game = tmp_path / "game"
    game.mkdir()
    (game / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).write_bytes(b"exe")
    return game


def _package(
    tmp_path: Path,
    mod_id: str,
    mod_type: str,
    destination: str,
    *,
    payload: bytes = b"synthetic mod payload",
    dependencies: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    editions: tuple[str, ...] = ("legacy", "enhanced"),
    checksum: bool = True,
    version: str = "1.2.3",
) -> Path:
    package = tmp_path / mod_id
    package.mkdir(parents=True)
    source = package / "payload.bin"
    source.write_bytes(payload)
    dependency_text = ", ".join(f'"{value}"' for value in dependencies)
    conflict_text = ", ".join(f'"{value}"' for value in conflicts)
    edition_text = ", ".join(f'"{value}"' for value in editions)
    checksum_line = (
        f'sha256 = "{hashlib.sha256(payload).hexdigest()}"\n' if checksum else ""
    )
    (package / "mod.toml").write_text(
        "schema_version = 1\n"
        f'id = "{mod_id}"\n'
        f'name = "Synthetic {mod_type.upper()}"\n'
        f'version = "{version}"\n'
        f'type = "{mod_type}"\n'
        'description = "Generated only for tests"\n'
        f"editions = [{edition_text}]\n"
        f"dependencies = [{dependency_text}]\n"
        f"conflicts = [{conflict_text}]\n"
        "[[files]]\n"
        'source = "payload.bin"\n'
        f'destination = "{destination}"\n'
        + checksum_line,
        encoding="utf-8",
    )
    return package


@pytest.mark.parametrize(
    ("mod_type", "destination", "dependencies"),
    [
        ("asi", "Synthetic.asi", ("scripthookv",)),
        ("script", "scripts/Synthetic.dll", ("shvdn",)),
        ("rpf", "mods/update/x64/dlcpacks/synthetic/dlc.rpf", ("openrpf",)),
        ("config", "scripts/Synthetic/settings.toml", ()),
    ],
)
def test_install_toggle_and_uninstall_each_supported_mod_shape(
    tmp_path: Path, mod_type: str, destination: str, dependencies: tuple[str, ...]
):
    game = _game(tmp_path)
    for loader in ("ScriptHookV.dll", "ScriptHookVDotNet.asi", "OpenRPF.asi",
                   "xinput1_4.dll"):
        (game / loader).write_bytes(b"loader")
    package = _package(tmp_path, f"test-{mod_type}", mod_type, destination,
                       dependencies=dependencies)
    manifest = ModManifest.load(package)
    service = ModIntegrationService(game)

    status = service.install(manifest)
    target = game / Path(destination)
    assert status.installed and status.enabled
    assert target.read_bytes() == b"synthetic mod payload"
    assert service.list_installed()[0].mod_type == mod_type

    disabled = service.set_enabled(manifest.mod_id, False)
    assert not disabled.enabled
    assert not target.exists()
    assert target.with_name(target.name + ".disabled").is_file()
    assert not service.set_enabled(manifest.mod_id, False).enabled

    enabled = service.set_enabled(manifest.mod_id, True)
    assert enabled.enabled and target.is_file()
    service.uninstall(manifest.mod_id)
    assert not target.exists()
    assert service.list_installed() == []


def test_install_backups_and_uninstall_restores_preexisting_file(tmp_path: Path):
    game = _game(tmp_path)
    target = game / "scripts" / "settings.ini"
    target.parent.mkdir()
    target.write_bytes(b"original")
    manifest = ModManifest.load(_package(
        tmp_path, "config-backup", "config", "scripts/settings.ini", payload=b"replacement"
    ))
    service = ModIntegrationService(game)

    service.install(manifest)
    receipt = json.loads((service.state_root / "config-backup.json").read_text())
    assert receipt["files"][0]["backup"]
    assert target.read_bytes() == b"replacement"
    service.uninstall("config-backup")
    assert target.read_bytes() == b"original"


def test_reinstall_same_mod_updates_payload(tmp_path: Path):
    game = _game(tmp_path)
    package = _package(tmp_path, "updated-script", "script", "scripts/Updated.dll",
                       payload=b"v1")
    service = ModIntegrationService(game)
    service.install(ModManifest.load(package))
    (package / "payload.bin").write_bytes(b"v2")
    manifest_text = (package / "mod.toml").read_text()
    (package / "mod.toml").write_text(
        manifest_text.replace(hashlib.sha256(b"v1").hexdigest(), hashlib.sha256(b"v2").hexdigest())
    )
    service.install(ModManifest.load(package))
    assert (game / "scripts" / "Updated.dll").read_bytes() == b"v2"


def test_failed_update_restores_previous_installed_version(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "rollback-script", "script", "scripts/Rollback.dll",
        payload=b"v1", version="1.0.0"
    )
    new_package = _package(
        tmp_path / "new", "rollback-script", "script", "scripts/Rollback.dll",
        payload=b"v2", version="2.0.0"
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    real_copy = shutil.copy2
    new_payload = (new_package / "payload.bin").resolve()

    def fail_new_payload(source, destination, *args, **kwargs):
        if Path(source).resolve() == new_payload:
            raise OSError("synthetic update failure")
        return real_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr("allin1.mods.shutil.copy2", fail_new_payload)
    with pytest.raises(OSError, match="synthetic update failure"):
        service.install(ModManifest.load(new_package))

    target = game / "scripts" / "Rollback.dll"
    assert target.read_bytes() == b"v1"
    assert service.list_installed()[0].version == "1.0.0"


def test_catalog_discovers_sorted_packages(tmp_path: Path):
    catalog = tmp_path / "catalog"
    _package(catalog, "z-script", "script", "scripts/Z.dll")
    _package(catalog, "a-script", "script", "scripts/A.dll")
    assert [manifest.mod_id for manifest in ModCatalog(catalog).discover()] == [
        "a-script", "z-script"
    ]
    assert ModCatalog(tmp_path / "missing").discover() == []


@pytest.mark.parametrize("dependency", ["scripthookv", "shvdn", "openrpf"])
def test_missing_loader_dependency_is_rejected(tmp_path: Path, dependency: str):
    game = _game(tmp_path)
    manifest = ModManifest.load(_package(
        tmp_path, f"needs-{dependency}", "config", "scripts/needs.ini",
        dependencies=(dependency,),
    ))
    with pytest.raises(ValueError, match="Missing required loader"):
        ModIntegrationService(game).install(manifest)


def test_declared_and_destination_conflicts_are_rejected(tmp_path: Path):
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    first = ModManifest.load(_package(
        tmp_path, "first-mod", "script", "scripts/Shared.dll", conflicts=("second-mod",)
    ))
    second = ModManifest.load(_package(
        tmp_path, "second-mod", "script", "scripts/Other.dll"
    ))
    collision = ModManifest.load(_package(
        tmp_path, "collision", "script", "scripts/Shared.dll"
    ))
    service.install(first)
    with pytest.raises(ValueError, match="Conflicts with"):
        service.install(second)
    with pytest.raises(ValueError, match="destination is owned"):
        service.install(collision)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ('schema_version = 1', "schema_version"),
        ('id = "safe-mod"', "Mod id"),
        ('type = "script"', "Unsupported mod type"),
        ('editions = ["legacy", "enhanced"]', "editions"),
        ('dependencies = []', "Unsupported dependencies"),
    ],
)
def test_manifest_metadata_validation(tmp_path: Path, replacement: str, message: str):
    package = _package(tmp_path, "safe-mod", "script", "scripts/Safe.dll")
    manifest_path = package / "mod.toml"
    text = manifest_path.read_text()
    if replacement.startswith("schema"):
        text = text.replace(replacement, "schema_version = 2")
    elif replacement.startswith("id"):
        text = text.replace(replacement, 'id = "BAD ID"')
    elif replacement.startswith("type"):
        text = text.replace(replacement, 'type = "unknown"')
    elif replacement.startswith("editions"):
        text = text.replace(replacement, 'editions = ["future"]')
    else:
        text = text.replace(replacement, 'dependencies = ["mystery"]')
    manifest_path.write_text(text)
    with pytest.raises(ValueError, match=message):
        ModManifest.load(manifest_path)


@pytest.mark.parametrize(
    ("mod_type", "destination", "message"),
    [
        ("asi", "scripts/Test.asi", "GTA V root"),
        ("asi", "Test.exe", "ASI packages"),
        ("script", "Test.dll", "below scripts"),
        ("rpf", "update/Test.rpf", "below mods"),
        ("rpf", "mods/Test.txt", "only .rpf"),
        ("config", "Test.ini", "below scripts/ or mods"),
    ],
)
def test_type_specific_destination_rules(
    tmp_path: Path, mod_type: str, destination: str, message: str
):
    package = _package(tmp_path, "destination-test", mod_type, destination)
    with pytest.raises(ValueError, match=message):
        ModManifest.load(package)


def test_traversal_checksum_and_missing_payload_are_rejected(tmp_path: Path):
    package = _package(tmp_path, "unsafe-mod", "script", "scripts/Safe.dll")
    manifest_path = package / "mod.toml"
    manifest_path.write_text(manifest_path.read_text().replace(
        'destination = "scripts/Safe.dll"', 'destination = "../outside.dll"'
    ))
    with pytest.raises(ValueError, match="traversal"):
        ModManifest.load(package)

    package = _package(tmp_path, "bad-hash", "script", "scripts/Hash.dll")
    (package / "payload.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ModManifest.load(package)

    package = _package(tmp_path, "missing-file", "script", "scripts/Missing.dll")
    (package / "payload.bin").unlink()
    with pytest.raises(FileNotFoundError, match="payload is missing"):
        ModManifest.load(package)


@pytest.mark.parametrize("destination", ["ScriptHookV.dll", "scripts/ALLIN1.dll",
                                           "scripts/.allin1/mods/forged.json"])
def test_launcher_managed_destinations_are_reserved(tmp_path: Path, destination: str):
    mod_type = "asi" if "/" not in destination else "script"
    package = _package(tmp_path, "reserved-target", mod_type, destination)
    with pytest.raises(ValueError, match="reserved by the ALLIN1 launcher"):
        ModManifest.load(package)


def test_edition_missing_receipt_and_corrupt_receipt_errors(tmp_path: Path):
    game = _game(tmp_path, enhanced=False)
    service = ModIntegrationService(game)
    manifest = ModManifest.load(_package(
        tmp_path, "enhanced-only", "script", "scripts/Enhanced.dll", editions=("enhanced",)
    ))
    with pytest.raises(ValueError, match="does not support"):
        service.install(manifest)
    with pytest.raises(FileNotFoundError, match="not installed"):
        service.set_enabled("no-mod", False)
    service.state_root.mkdir(parents=True)
    (service.state_root / "broken.json").write_text("not json")
    assert service.list_installed() == []


def test_enable_refuses_missing_or_colliding_managed_file(tmp_path: Path):
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    manifest = ModManifest.load(_package(
        tmp_path, "toggle-test", "script", "scripts/Toggle.dll"
    ))
    service.install(manifest)
    target = game / "scripts" / "Toggle.dll"
    target.unlink()
    with pytest.raises(FileNotFoundError, match="Managed mod file is missing"):
        service.set_enabled("toggle-test", False)

    target.write_bytes(b"managed")
    service.set_enabled("toggle-test", False)
    target.write_bytes(b"collision")
    with pytest.raises(FileExistsError, match="destination exists"):
        service.set_enabled("toggle-test", True)
