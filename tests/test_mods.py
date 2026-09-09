"""Synthetic coverage for optional, user-supplied mod integrations."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1.mods import (
    ModCatalog,
    ModIntegrationService,
    ModManifest,
    default_mod_catalog,
    default_package_library_root,
)


def _write_pe(path: Path) -> None:
    payload = bytearray(4096)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


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
    dlc_packs: tuple[str, ...] = (),
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
    dlc_pack_text = ", ".join(f'"{value}"' for value in dlc_packs)
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
        f"dlc_packs = [{dlc_pack_text}]\n"
        "[[files]]\n"
        'source = "payload.bin"\n'
        f'destination = "{destination}"\n'
        + checksum_line,
        encoding="utf-8",
    )
    return package


def _rpf_entry_package(
    tmp_path: Path,
    mod_id: str,
    *,
    payload: bytes = b"replacement entry",
    archive: str = "mods/x64h.rpf",
    entry: str = "levels/gta5/test.bin",
    mod_type: str = "rpf",
) -> Path:
    package = tmp_path / mod_id
    package.mkdir(parents=True)
    (package / "entry.bin").write_bytes(payload)
    (package / "mod.toml").write_text(
        "schema_version = 1\n"
        f'id = "{mod_id}"\n'
        f'name = "Synthetic {mod_id}"\n'
        'version = "1.0.0"\n'
        f'type = "{mod_type}"\n'
        'editions = ["legacy", "enhanced"]\n'
        'dependencies = ["openrpf"]\n'
        "[[rpf_entries]]\n"
        'source = "entry.bin"\n'
        f'archive = "{archive}"\n'
        f'entry = "{entry}"\n'
        f'sha256 = "{hashlib.sha256(payload).hexdigest()}"\n',
        encoding="utf-8",
    )
    return package


def _fake_rpf_service(
    service: ModIntegrationService,
    monkeypatch,
    entries: dict[tuple[str, str], bytes],
) -> None:
    monkeypatch.setattr(service, "_check_dependencies", lambda _manifest: None)

    def key(archive: Path, entry: str) -> tuple[str, str]:
        return (str(Path(archive).resolve()).casefold(), entry.casefold())

    def extract(archive, entry, output, *, allow_missing=False):
        payload = entries.get(key(Path(archive), str(entry)))
        if payload is None:
            if allow_missing:
                return False
            raise RuntimeError("synthetic entry missing")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(payload)
        return True

    def replace(archive, entry, payload, *, expected_sha256=None):
        entries[key(Path(archive), str(entry))] = Path(payload).read_bytes()

    def delete(archive, entry):
        entries.pop(key(Path(archive), str(entry)), None)

    monkeypatch.setattr(service, "_extract_rpf_entry", extract)
    monkeypatch.setattr(service, "_replace_rpf_entry", replace)
    monkeypatch.setattr(service, "_delete_rpf_entry", delete)


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
        _write_pe(game / loader)
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


@pytest.mark.parametrize(
    "destination",
    [
        "VehicleWorkbenchAxles/runtime.json",
        "VehicleWorkbenchAxles/profiles/compatibility.json",
    ],
)
def test_mixed_package_can_own_vehicle_workbench_json_runtime_tree(
    tmp_path: Path, destination: str,
):
    manifest = ModManifest.load(_package(
        tmp_path, "vehicle-workbench-runtime", "mixed", destination,
        payload=b'{"manifestVersion": 1}',
    ))
    game = _game(tmp_path)
    service = ModIntegrationService(game)

    service.install(manifest)

    target = game / Path(destination)
    assert target.read_bytes() == b'{"manifestVersion": 1}'
    receipt = json.loads(
        (service.state_root / "vehicle-workbench-runtime.json").read_text(
            encoding="utf-8",
        )
    )
    assert receipt["files"][0]["destination"] == destination

    service.uninstall(manifest.mod_id)
    assert not target.exists()


@pytest.mark.parametrize(
    "destination",
    ["addonhelper.addon", "license.md", "CustomShaders/settings.json"],
)
def test_mixed_package_can_own_reshade_addon_payloads(
    tmp_path: Path, destination: str,
):
    manifest = ModManifest.load(_package(
        tmp_path, "reshade-addon-payload", "mixed", destination,
    ))
    assert manifest.files[0].destination.as_posix() == destination


@pytest.mark.parametrize(
    ("destination", "message"),
    [
        ("OtherRuntime/runtime.json", "Mixed package files"),
        ("VehicleWorkbenchAxles.json", "Mixed package files"),
        ("VehicleWorkbenchAxles/runtime.dll", "Mixed package files"),
        ("VehicleWorkbenchAxles/tools/settings.exe", "Mixed package files"),
        ("VehicleWorkbenchAxles/../escape.json", "traversal"),
        ("VehicleWorkbenchAxles/runtime.json:alternate", "Windows-invalid"),
    ],
)
def test_mixed_package_runtime_tree_exception_stays_narrow(
    tmp_path: Path, destination: str, message: str,
):
    package = _package(
        tmp_path, "vehicle-workbench-runtime-invalid", "mixed", destination,
    )

    with pytest.raises(ValueError, match=message):
        ModManifest.load(package)


def test_mixed_runtime_tree_cannot_target_launcher_reserved_root(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path, "mixed-reserved-target", "mixed", "ScriptHookV.dll",
    )

    with pytest.raises(ValueError, match="reserved by the ALLIN1 launcher"):
        ModManifest.load(package)


def test_mixed_runtime_tree_rejects_case_insensitive_duplicate_destination(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path, "mixed-duplicate-runtime", "mixed",
        "VehicleWorkbenchAxles/runtime.json", payload=b"{}",
    )
    (package / "other.json").write_bytes(b"{}")
    manifest_path = package / "mod.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8")
        + "[[files]]\n"
        + 'source = "other.json"\n'
        + 'destination = "vehicleworkbenchaxles/RUNTIME.JSON"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate destination"):
        ModManifest.load(package)


def test_mixed_runtime_tree_receipt_ownership_collision_is_rejected(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    first = ModManifest.load(_package(
        tmp_path, "mixed-runtime-owner", "mixed",
        "VehicleWorkbenchAxles/runtime.json", payload=b'{"owner": 1}',
    ))
    collision = ModManifest.load(_package(
        tmp_path, "mixed-runtime-collision", "mixed",
        "vehicleworkbenchaxles/RUNTIME.JSON", payload=b'{"owner": 2}',
    ))
    service.install(first)

    with pytest.raises(ValueError, match="destination is owned"):
        service.install(collision)


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


def test_toggle_restores_and_reapplies_preexisting_loose_file(tmp_path: Path):
    game = _game(tmp_path)
    target = game / "scripts" / "settings.ini"
    target.parent.mkdir()
    target.write_bytes(b"original")
    manifest = ModManifest.load(_package(
        tmp_path, "layered-config", "config", "scripts/settings.ini",
        payload=b"replacement",
    ))
    service = ModIntegrationService(game)

    service.install(manifest)
    service.set_enabled("layered-config", False)
    assert target.read_bytes() == b"original"
    assert target.with_name("settings.ini.disabled").read_bytes() == b"replacement"

    service.set_enabled("layered-config", True)
    assert target.read_bytes() == b"replacement"
    assert not target.with_name("settings.ini.disabled").exists()
    service.uninstall("layered-config")
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


def test_reinstall_repairs_missing_managed_payload(tmp_path: Path):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "repair-update", "script",
        "scripts/RepairUpdate.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "repair-update", "script",
        "scripts/RepairUpdate.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    target = game / "scripts" / "RepairUpdate.dll"
    target.unlink()

    status = service.install(ModManifest.load(new_package))

    assert status.version == "2.0.0"
    assert target.read_bytes() == b"v2"
    receipt = json.loads(
        (service.state_root / "repair-update.json").read_text(encoding="utf-8")
    )
    assert receipt["version"] == "2.0.0"


def test_reinstall_accepts_payload_already_matching_validated_replacement(
    tmp_path: Path,
):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "partial-repair", "script",
        "scripts/PartialRepair.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "partial-repair", "script",
        "scripts/PartialRepair.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    target = game / "scripts" / "PartialRepair.dll"
    target.write_bytes(b"v2")

    status = service.install(ModManifest.load(new_package))

    assert status.version == "2.0.0"
    assert target.read_bytes() == b"v2"


def test_reinstall_still_refuses_unrecognized_managed_payload_change(
    tmp_path: Path,
):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "tampered-repair", "script",
        "scripts/TamperedRepair.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "tampered-repair", "script",
        "scripts/TamperedRepair.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    target = game / "scripts" / "TamperedRepair.dll"
    target.write_bytes(b"unexpected")

    with pytest.raises(RuntimeError, match="externally changed managed file"):
        service.install(ModManifest.load(new_package))

    assert target.read_bytes() == b"unexpected"

    status = service.install(
        ModManifest.load(new_package), repair_managed=True,
    )

    assert status.version == "2.0.0"
    assert target.read_bytes() == b"v2"


def test_failed_repair_update_restores_prior_missing_state(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "repair-update-rollback", "script",
        "scripts/RepairRollback.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "repair-update-rollback", "script",
        "scripts/RepairRollback.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    target = game / "scripts" / "RepairRollback.dll"
    target.unlink()

    monkeypatch.setattr(
        service,
        "_copy_atomic",
        lambda _source, _target: (_ for _ in ()).throw(
            OSError("synthetic repair failure")
        ),
    )
    with pytest.raises(OSError, match="synthetic repair failure"):
        service.install(ModManifest.load(new_package))

    assert not target.exists()
    receipt = json.loads(
        (service.state_root / "repair-update-rollback.json").read_text(
            encoding="utf-8",
        )
    )
    assert receipt["version"] == "1.0.0"


def test_update_preserves_disabled_package_state(tmp_path: Path):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "disabled-update", "script",
        "scripts/DisabledUpdate.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "disabled-update", "script",
        "scripts/DisabledUpdate.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    service.set_enabled("disabled-update", False)

    status = service.install(ModManifest.load(new_package))

    target = game / "scripts" / "DisabledUpdate.dll"
    assert status.enabled is False
    assert not target.exists()
    assert target.with_name("DisabledUpdate.dll.disabled").read_bytes() == b"v2"
    receipt = json.loads(
        (service.state_root / "disabled-update.json").read_text(encoding="utf-8")
    )
    assert receipt["enabled"] is False
    assert receipt["version"] == "2.0.0"


def test_failed_disabled_update_never_leaves_new_payload_active(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    old_package = _package(
        tmp_path / "old", "disabled-update-rollback", "script",
        "scripts/DisabledRollback.dll", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "disabled-update-rollback", "script",
        "scripts/DisabledRollback.dll", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    service.set_enabled("disabled-update-rollback", False)
    monkeypatch.setattr(
        service, "_deactivate_new_loose_payload",
        lambda _records: (_ for _ in ()).throw(OSError("synthetic deactivate failure")),
    )

    with pytest.raises(OSError, match="synthetic deactivate failure"):
        service.install(ModManifest.load(new_package))

    target = game / "scripts" / "DisabledRollback.dll"
    assert not target.exists()
    assert target.with_name("DisabledRollback.dll.disabled").read_bytes() == b"v1"
    receipt = json.loads(
        (service.state_root / "disabled-update-rollback.json").read_text(
            encoding="utf-8",
        )
    )
    assert receipt["enabled"] is False
    assert receipt["version"] == "1.0.0"


def test_failed_disabled_update_restores_underlying_file(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    target = game / "scripts" / "LayeredRollback.ini"
    target.parent.mkdir()
    target.write_bytes(b"original")
    old_package = _package(
        tmp_path / "old", "disabled-layered-rollback", "config",
        "scripts/LayeredRollback.ini", payload=b"v1", version="1.0.0",
    )
    new_package = _package(
        tmp_path / "new", "disabled-layered-rollback", "config",
        "scripts/LayeredRollback.ini", payload=b"v2", version="2.0.0",
    )
    service = ModIntegrationService(game)
    service.install(ModManifest.load(old_package))
    service.set_enabled("disabled-layered-rollback", False)

    def fail_deactivation(_records):
        raise OSError("synthetic deactivate failure")

    monkeypatch.setattr(
        service, "_deactivate_new_loose_payload", fail_deactivation,
    )
    with pytest.raises(OSError, match="synthetic deactivate failure"):
        service.install(ModManifest.load(new_package))

    assert target.read_bytes() == b"original"
    assert target.with_name("LayeredRollback.ini.disabled").read_bytes() == b"v1"
    receipt = json.loads(
        (service.state_root / "disabled-layered-rollback.json").read_text(
            encoding="utf-8",
        )
    )
    assert receipt["enabled"] is False
    assert receipt["version"] == "1.0.0"


def test_uninstall_rolls_back_loose_files_and_receipt_when_registry_fails(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    target = game / "scripts" / "rollback.ini"
    target.parent.mkdir()
    target.write_bytes(b"original")
    manifest = ModManifest.load(_package(
        tmp_path, "uninstall-rollback", "config", "scripts/rollback.ini",
        payload=b"managed",
    ))
    service = ModIntegrationService(game)
    service.install(manifest)

    from allin1.extensions import ExtensionRegistry

    real_rebuild = ExtensionRegistry.rebuild
    calls = 0

    def fail_once(registry):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("synthetic registry failure")
        return real_rebuild(registry)

    monkeypatch.setattr(ExtensionRegistry, "rebuild", fail_once)
    with pytest.raises(OSError, match="synthetic registry failure"):
        service.uninstall("uninstall-rollback")

    assert target.read_bytes() == b"managed"
    assert (service.state_root / "uninstall-rollback.json").is_file()
    assert service.list_installed()[0].enabled is True


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


def test_default_package_library_root_uses_stable_per_user_location(
    tmp_path: Path,
) -> None:
    assert default_package_library_root({"LOCALAPPDATA": str(tmp_path)}) == (
        tmp_path.resolve() / "ALLIN1" / "Packages"
    )
    assert default_package_library_root({}) == (
        Path.home().resolve() / ".allin1" / "packages"
    )


def test_default_catalog_discovers_project_and_quick_import_packages(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    local_appdata = tmp_path / "local-appdata"
    project_catalog = project / "mods" / "catalog"
    package_library = local_appdata / "ALLIN1" / "Packages"
    _package(
        project_catalog, "bundled-script", "script", "scripts/Bundled.dll",
    )
    _package(
        package_library, "quick-import-vehicle", "rpf",
        "mods/update/x64/dlcpacks/quickcar/dlc.rpf",
        dependencies=("openrpf",), dlc_packs=("quickcar",),
    )

    catalog = default_mod_catalog(
        project, {"LOCALAPPDATA": str(local_appdata)},
    )

    assert catalog.root == project_catalog.resolve()
    assert catalog.roots == (
        project_catalog.resolve(), package_library.resolve(),
    )
    assert [manifest.mod_id for manifest in catalog.discover()] == [
        "bundled-script", "quick-import-vehicle",
    ]


def test_catalog_rejects_duplicate_ids_across_package_roots(
    tmp_path: Path,
) -> None:
    project_catalog = tmp_path / "project-catalog"
    package_library = tmp_path / "package-library"
    _package(
        project_catalog, "duplicate-package", "script", "scripts/One.dll",
    )
    _package(
        package_library, "duplicate-package", "script", "scripts/Two.dll",
    )

    with pytest.raises(ValueError, match="Duplicate mod package id") as error:
        ModCatalog(project_catalog, package_library).discover()

    assert str(project_catalog / "duplicate-package" / "mod.toml") in str(
        error.value
    )
    assert str(package_library / "duplicate-package" / "mod.toml") in str(
        error.value
    )


def test_catalog_does_not_double_scan_the_same_root(tmp_path: Path) -> None:
    catalog_root = tmp_path / "catalog"
    _package(catalog_root, "one-package", "script", "scripts/One.dll")

    catalog = ModCatalog(catalog_root, catalog_root)

    assert catalog.roots == (catalog_root.resolve(),)
    assert [manifest.mod_id for manifest in catalog.discover()] == [
        "one-package",
    ]


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
        text = text.replace(replacement, "schema_version = 99")
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


def test_mixed_package_accepts_isolated_plugin_runtime_tree(tmp_path: Path):
    package = _package(
        tmp_path,
        "isolated-runtime",
        "mixed",
        "plugins/ReactorV/Renderer.dll",
    )

    manifest = ModManifest.load(package)

    assert manifest.files[0].destination.as_posix() == "plugins/ReactorV/Renderer.dll"


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


@pytest.mark.parametrize(
    "destination",
    [
        "scripts/payload.dll:stream",
        "scripts/CON.txt",
        "scripts/trailing-dot.",
        "scripts/bad?.dll",
    ],
)
def test_windows_invalid_destination_components_are_rejected(
    tmp_path: Path, destination: str,
):
    package = _package(
        tmp_path, "invalid-windows-path", "script", destination,
    )
    with pytest.raises(ValueError, match="Windows-invalid or reserved"):
        ModManifest.load(package)


def test_package_namespace_reserved_for_launcher_builtins(tmp_path: Path):
    package = _package(
        tmp_path, "allin1.forged", "script", "scripts/Forged.dll",
    )
    with pytest.raises(ValueError, match="namespace is reserved"):
        ModManifest.load(package)


def test_install_rejects_in_root_symlink_destination_alias(tmp_path: Path):
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    protected = scripts / "ALLIN1.toml"
    protected.write_bytes(b"protected")
    alias = scripts / "Harmless.toml"
    try:
        alias.symlink_to(protected)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    manifest = ModManifest.load(_package(
        tmp_path, "alias-package", "config", "scripts/Harmless.toml",
        payload=b"replacement",
    ))

    with pytest.raises(ValueError, match="symlink or junction"):
        ModIntegrationService(game).install(manifest)
    assert protected.read_bytes() == b"protected"


def test_runtime_tree_install_rejects_symlinked_parent_directory(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    outside = tmp_path / "outside-runtime"
    outside.mkdir()
    sentinel = outside / "sentinel.json"
    sentinel.write_bytes(b"protected")
    runtime_root = game / "VehicleWorkbenchAxles"
    try:
        runtime_root.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    manifest = ModManifest.load(_package(
        tmp_path, "runtime-parent-alias", "mixed",
        "VehicleWorkbenchAxles/runtime.json", payload=b"replacement",
    ))
    service = ModIntegrationService(game)

    with pytest.raises(ValueError, match="symlink or junction|escapes the allowed root"):
        service.install(manifest)
    assert sentinel.read_bytes() == b"protected"
    assert not (outside / "runtime.json").exists()
    assert not (service.state_root / "runtime-parent-alias.json").exists()


def test_runtime_tree_install_rejects_predictable_temporary_symlink(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    runtime_root = game / "VehicleWorkbenchAxles"
    runtime_root.mkdir()
    sentinel = tmp_path / "outside-sentinel.json"
    sentinel.write_bytes(b"protected")
    legacy_temporary = runtime_root / ".runtime.json.allin1-install"
    try:
        legacy_temporary.symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    manifest = ModManifest.load(_package(
        tmp_path, "runtime-temp-alias", "mixed",
        "VehicleWorkbenchAxles/runtime.json", payload=b"replacement",
    ))
    service = ModIntegrationService(game)

    with pytest.raises(ValueError, match="legacy install-temporary"):
        service.install(manifest)
    assert sentinel.read_bytes() == b"protected"
    assert not (runtime_root / "runtime.json").exists()
    assert not (service.state_root / "runtime-temp-alias.json").exists()


def test_runtime_tree_install_rejects_occupied_legacy_temporary_file(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    runtime_root = game / "VehicleWorkbenchAxles"
    runtime_root.mkdir()
    legacy_temporary = runtime_root / ".runtime.json.allin1-install"
    legacy_temporary.write_bytes(b"protected")
    manifest = ModManifest.load(_package(
        tmp_path, "runtime-temp-file", "mixed",
        "VehicleWorkbenchAxles/runtime.json", payload=b"replacement",
    ))
    service = ModIntegrationService(game)

    with pytest.raises(ValueError, match="legacy install-temporary"):
        service.install(manifest)
    assert legacy_temporary.read_bytes() == b"protected"
    assert not (runtime_root / "runtime.json").exists()
    assert not (service.state_root / "runtime-temp-file.json").exists()


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

    target.write_bytes(b"synthetic mod payload")
    service.set_enabled("toggle-test", False)
    target.write_bytes(b"collision")
    with pytest.raises(FileExistsError, match="destination exists"):
        service.set_enabled("toggle-test", True)


def test_raw_archive_is_rejected_with_sdk_guidance(tmp_path: Path):
    archive = tmp_path / "vehicle.rar"
    archive.write_bytes(b"Rar!\x1a\x07\x01\x00")
    with pytest.raises(ValueError, match="Add-on Content SDK"):
        ModManifest.load(archive)


@pytest.mark.parametrize(
    ("mod_type", "dependencies", "dlc_packs", "destination", "message"),
    [
        ("script", (), ("vehicle_pack",), "scripts/Test.dll", "RPF or mixed"),
        ("rpf", (), ("vehicle_pack",),
         "mods/update/x64/dlcpacks/vehicle_pack/dlc.rpf", "depend on openrpf"),
        ("rpf", ("openrpf",), ("BAD PACK",),
         "mods/update/x64/dlcpacks/BAD PACK/dlc.rpf", "pack names"),
        ("rpf", ("openrpf",), ("vehicle_pack",),
         "mods/update/x64/dlcpacks/other/dlc.rpf", "must own exactly"),
    ],
)
def test_dlc_pack_manifest_contract(
    tmp_path: Path, mod_type: str, dependencies: tuple[str, ...],
    dlc_packs: tuple[str, ...], destination: str, message: str,
):
    package = _package(
        tmp_path, "managed-dlc", mod_type, destination,
        dependencies=dependencies, dlc_packs=dlc_packs,
    )
    with pytest.raises(ValueError, match=message):
        ModManifest.load(package)


def test_managed_dlc_registration_follows_install_toggle_and_uninstall(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    for loader in ("OpenRPF.asi", "xinput1_4.dll"):
        _write_pe(game / loader)
    package = _package(
        tmp_path, "managed-vehicle", "rpf",
        "mods/update/x64/dlcpacks/vehicle_pack/dlc.rpf",
        dependencies=("openrpf",), dlc_packs=("vehicle_pack",),
    )
    service = ModIntegrationService(game)
    registrations: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        service, "_set_dlc_registration",
        lambda pack, enabled: registrations.append((pack, enabled)) or True,
    )

    service.install(ModManifest.load(package))
    receipt = json.loads(
        (service.state_root / "managed-vehicle.json").read_text(encoding="utf-8")
    )
    assert receipt["dlc_packs"] == ["vehicle_pack"]
    assert receipt["owned_dlc_packs"] == ["vehicle_pack"]
    service.set_enabled("managed-vehicle", False)
    service.set_enabled("managed-vehicle", True)
    service.uninstall("managed-vehicle")
    assert registrations == [
        ("vehicle_pack", True),
        ("vehicle_pack", False),
        ("vehicle_pack", True),
        ("vehicle_pack", False),
    ]


def test_failed_dlc_registration_rolls_back_payload(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    for loader in ("OpenRPF.asi", "xinput1_4.dll"):
        _write_pe(game / loader)
    destination = "mods/update/x64/dlcpacks/failing_pack/dlc.rpf"
    manifest = ModManifest.load(_package(
        tmp_path, "failing-dlc", "rpf", destination,
        dependencies=("openrpf",), dlc_packs=("failing_pack",),
    ))
    service = ModIntegrationService(game)

    def fail_registration(_pack: str, enabled: bool) -> None:
        if enabled:
            raise RuntimeError("synthetic registration failure")

    monkeypatch.setattr(service, "_set_dlc_registration", fail_registration)
    with pytest.raises(RuntimeError, match="synthetic registration failure"):
        service.install(manifest)
    assert not (game / Path(destination)).exists()
    assert service.list_installed() == []


def test_preexisting_dlc_registration_is_not_claimed_or_removed(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    for loader in ("OpenRPF.asi", "xinput1_4.dll"):
        _write_pe(game / loader)
    package = _package(
        tmp_path, "shared-registration", "rpf",
        "mods/update/x64/dlcpacks/shared_pack/dlc.rpf",
        dependencies=("openrpf",), dlc_packs=("shared_pack",),
    )
    service = ModIntegrationService(game)
    calls: list[tuple[str, bool]] = []

    def preexisting(pack: str, enabled: bool) -> bool:
        calls.append((pack, enabled))
        return False

    monkeypatch.setattr(service, "_set_dlc_registration", preexisting)
    service.install(ModManifest.load(package))
    receipt = json.loads(
        (service.state_root / "shared-registration.json").read_text(encoding="utf-8")
    )
    assert receipt["owned_dlc_packs"] == []
    service.set_enabled("shared-registration", False)
    service.set_enabled("shared-registration", True)
    service.uninstall("shared-registration")
    assert calls == [("shared_pack", True)]


def test_disabled_update_preserves_owned_dlc_for_reenable(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    for loader in ("OpenRPF.asi", "xinput1_4.dll"):
        _write_pe(game / loader)
    package = _package(
        tmp_path, "disabled-update", "rpf",
        "mods/update/x64/dlcpacks/owned_pack/dlc.rpf",
        dependencies=("openrpf",), dlc_packs=("owned_pack",),
    )
    service = ModIntegrationService(game)
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        service, "_set_dlc_registration",
        lambda pack, enabled: calls.append((pack, enabled)) or True,
    )
    manifest = ModManifest.load(package)

    service.install(manifest)
    service.set_enabled("disabled-update", False)
    service.install(manifest)
    disabled_receipt = json.loads(
        (service.state_root / "disabled-update.json").read_text(
            encoding="utf-8"
        )
    )
    assert disabled_receipt["enabled"] is False
    assert disabled_receipt["owned_dlc_packs"] == ["owned_pack"]

    service.set_enabled("disabled-update", True)
    enabled_receipt = json.loads(
        (service.state_root / "disabled-update.json").read_text(
            encoding="utf-8"
        )
    )
    assert enabled_receipt["owned_dlc_packs"] == ["owned_pack"]
    assert calls == [
        ("owned_pack", True),
        ("owned_pack", False),
        ("owned_pack", True),
    ]


def test_rpf_entry_install_toggle_and_uninstall_restore_exact_entry(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic base archive")
    service = ModIntegrationService(game)
    archive = game / "mods" / "x64h.rpf"
    entry = "levels/gta5/test.bin"
    entries = {(str(archive.resolve()).casefold(), entry.casefold()): b"stock"}
    _fake_rpf_service(service, monkeypatch, entries)
    manifest = ModManifest.load(_rpf_entry_package(tmp_path, "entry-lifecycle"))

    service.install(manifest)
    assert archive.read_bytes() == b"synthetic base archive"
    assert entries[(str(archive.resolve()).casefold(), entry.casefold())] == (
        b"replacement entry"
    )
    receipt = json.loads(
        (service.state_root / "entry-lifecycle.json").read_text(encoding="utf-8")
    )
    assert receipt["rpf_entries"][0]["backup"]
    assert receipt["rpf_entries"][0]["sha256"] == hashlib.sha256(
        b"replacement entry"
    ).hexdigest()

    service.set_enabled("entry-lifecycle", False)
    assert entries[(str(archive.resolve()).casefold(), entry.casefold())] == b"stock"
    service.set_enabled("entry-lifecycle", True)
    assert entries[(str(archive.resolve()).casefold(), entry.casefold())] == (
        b"replacement entry"
    )
    service.uninstall("entry-lifecycle")
    assert entries[(str(archive.resolve()).casefold(), entry.casefold())] == b"stock"
    assert not (service.state_root / ".payloads" / "entry-lifecycle").exists()


def test_schema_one_rpf_entry_records_stable_canonical_roundtrip(
    tmp_path: Path, monkeypatch,
):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic base archive")
    service = ModIntegrationService(game)
    archive = game / "mods" / "x64h.rpf"
    entry = "levels/gta5/test.bin"
    key = (str(archive.resolve()).casefold(), entry.casefold())
    entries = {key: b"stock"}
    _fake_rpf_service(service, monkeypatch, entries)

    def canonical_replace(archive_path, entry_path, payload, *, expected_sha256=None):
        data = Path(payload).read_bytes()
        entries[(str(Path(archive_path).resolve()).casefold(), str(entry_path).casefold())] = (
            b"canonical replacement" if data == b"replacement entry" else data
        )

    monkeypatch.setattr(service, "_replace_rpf_entry", canonical_replace)
    manifest = ModManifest.load(_rpf_entry_package(tmp_path, "entry-canonical"))

    service.install(manifest)

    assert entries[key] == b"canonical replacement"
    receipt = json.loads(
        (service.state_root / "entry-canonical.json").read_text(encoding="utf-8")
    )
    assert receipt["rpf_entries"][0]["sha256"] == hashlib.sha256(
        b"canonical replacement"
    ).hexdigest()
    service.set_enabled("entry-canonical", False)
    assert entries[key] == b"stock"
    service.set_enabled("entry-canonical", True)
    assert entries[key] == b"canonical replacement"


def test_rpf_entry_uninstall_refuses_external_change(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic base archive")
    service = ModIntegrationService(game)
    archive = game / "mods" / "x64h.rpf"
    entry = "levels/gta5/test.bin"
    key = (str(archive.resolve()).casefold(), entry.casefold())
    entries = {key: b"stock"}
    _fake_rpf_service(service, monkeypatch, entries)
    service.install(ModManifest.load(_rpf_entry_package(tmp_path, "entry-protect")))
    entries[key] = b"external edit"

    with pytest.raises(RuntimeError, match="externally changed RPF entry"):
        service.uninstall("entry-protect")
    assert entries[key] == b"external edit"
    assert (service.state_root / "entry-protect.json").is_file()


def test_rpf_entry_collision_and_update_are_fail_closed(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic base archive")
    service = ModIntegrationService(game)
    archive = game / "mods" / "x64h.rpf"
    entry = "levels/gta5/test.bin"
    entries = {(str(archive.resolve()).casefold(), entry.casefold()): b"stock"}
    _fake_rpf_service(service, monkeypatch, entries)
    first = ModManifest.load(_rpf_entry_package(tmp_path, "entry-first"))
    second = ModManifest.load(_rpf_entry_package(tmp_path, "entry-second"))
    service.install(first)

    with pytest.raises(ValueError, match="RPF entry destination is owned"):
        service.install(second)
    with pytest.raises(ValueError, match="requires uninstalling"):
        service.install(first)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ('archive = "mods/x64h.rpf"', "below the GTA V mods directory"),
        ('entry = "levels/gta5/test.bin"', "traversal"),
        ('dependencies = ["openrpf"]', "require the openrpf"),
        ('type = "rpf"', "require an RPF or mixed"),
    ],
)
def test_rpf_entry_manifest_contract(
    tmp_path: Path, replacement: str, message: str,
):
    package = _rpf_entry_package(tmp_path, "entry-contract")
    manifest_path = package / "mod.toml"
    text = manifest_path.read_text(encoding="utf-8")
    if replacement.startswith("archive"):
        text = text.replace(replacement, 'archive = "x64h.rpf"')
    elif replacement.startswith("entry"):
        text = text.replace(replacement, 'entry = "../test.bin"')
    elif replacement.startswith("dependencies"):
        text = text.replace(replacement, "dependencies = []")
    else:
        text = text.replace(replacement, 'type = "script"')
    manifest_path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        ModManifest.load(package)


def test_mixed_manifest_accepts_loose_and_rpf_entry_payloads(tmp_path: Path):
    package = _rpf_entry_package(tmp_path, "mixed-entry", mod_type="mixed")
    dll = package / "script.dll"
    dll.write_bytes(b"script")
    with (package / "mod.toml").open("a", encoding="utf-8") as manifest:
        manifest.write(
            "[[files]]\n"
            'source = "script.dll"\n'
            'destination = "scripts/Mixed/script.dll"\n'
        )
    loaded = ModManifest.load(package)
    assert loaded.mod_type == "mixed"
    assert len(loaded.files) == len(loaded.rpf_entries) == 1


def test_rpf_archive_copy_and_helper_wrappers(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"stock archive")
    service = ModIntegrationService(game)

    archive = service._ensure_mods_archive("mods/x64h.rpf")
    assert archive.read_bytes() == b"stock archive"
    assert service._ensure_mods_archive("mods/x64h.rpf") == archive
    with pytest.raises(FileNotFoundError, match="Base archive"):
        service._ensure_mods_archive("mods/missing.rpf")
    invalid = game / "mods" / "directory.rpf"
    invalid.mkdir(parents=True)
    with pytest.raises(ValueError, match="not a file"):
        service._ensure_mods_archive("mods/directory.rpf")
    with pytest.raises(ValueError, match="below mods"):
        service._ensure_mods_archive("x64h.rpf")

    calls = []
    helper = tmp_path / "helper.exe"
    helper.write_bytes(b"MZ")
    monkeypatch.setattr(service, "_rpf_patcher_path", lambda *_args: helper)
    assert service._rpf_patcher_path().name == "helper.exe"
    monkeypatch.setattr(
        "allin1.mods.run_hidden",
        lambda command, **kwargs: calls.append((command, kwargs))
        or SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    result = service._run_rpf_command("inspect", archive)
    assert result.returncode == 0
    assert calls[0][0][:3] == [helper, "inspect", game]


@pytest.mark.parametrize("canonical,fail_verification", [(False, False), (True, False), (False, True)])
def test_rpf_helper_progress_counts_lifecycle_canonicalization_and_rollback(tmp_path, monkeypatch, canonical, fail_verification):
    from allin1.rpf_progress import RpfProgress
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic archive")
    frames, content = [], {"levels/gta5/test.bin": b"original"}
    work = RpfProgress(lambda percent, message: frames.append((percent, message)))
    service = ModIntegrationService(game, rpf_progress=work)
    monkeypatch.setattr(service, "_check_dependencies", lambda _: None)
    monkeypatch.setattr(service, "_rpf_patcher_path", lambda *_: tmp_path / "synthetic-helper.exe")

    def helper(args, **kwargs):
        command, entry = args[1], str(args[4])
        if command == "extract-exact-entry":
            if fail_verification and ".probes" in str(args[5]):
                return SimpleNamespace(returncode=1, stdout="", stderr="verification failed")
            if entry not in content:
                return SimpleNamespace(returncode=5, stdout="", stderr="not found")
            Path(args[5]).write_bytes(content[entry])
        elif command == "replace-entry":
            value = Path(args[5]).read_bytes()
            content[entry] = b"canonical entry" if canonical and value == b"replacement entry" else value
        elif command == "delete-entry":
            content.pop(entry, None)
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("allin1.mods.run_hidden", helper)
    manifest = ModManifest.load(_rpf_entry_package(tmp_path, "progress-package"))
    if fail_verification:
        with pytest.raises(RuntimeError, match="verification failed"):
            service.install(manifest)
        assert content["levels/gta5/test.bin"] == b"original"
        assert not service.list_installed()
        assert work.snapshot()["completed_actions"] == work.snapshot()["estimated_actions"] == 4
        assert any("Rolling back" in message for _, message in frames)
    else:
        service.install(manifest)
        assert work.snapshot()["completed_actions"] == work.snapshot()["estimated_actions"] == (6 if canonical else 3)
        for action in (lambda: service.set_enabled(manifest.mod_id, False),
                       lambda: service.set_enabled(manifest.mod_id, True),
                       lambda: service.uninstall(manifest.mod_id)):
            service.rpf_progress = RpfProgress(lambda percent, message: frames.append((percent, message)))
            action()
            assert service.rpf_progress.snapshot()["completed_actions"] == 2
            assert service.rpf_progress.snapshot()["estimated_actions"] == 2
        assert content["levels/gta5/test.bin"] == b"original"
    assert all(percent < 100 for percent, _ in frames)
    for phase in ("Backing up", "Replacing", "Verifying"):
        assert any(phase in message for _, message in frames)


def test_rpf_extract_replace_delete_error_contracts(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    archive = game / "mods" / "x64h.rpf"
    archive.parent.mkdir()
    archive.write_bytes(b"archive")
    output = tmp_path / "entry.bin"

    def success_extract(command, *arguments):
        assert command == "extract-exact-entry"
        Path(arguments[-1]).write_bytes(b"entry")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(service, "_run_rpf_command", success_extract)
    assert service._extract_rpf_entry(archive, "path/entry.bin", output)
    assert output.read_bytes() == b"entry"

    monkeypatch.setattr(
        service, "_run_rpf_command",
        lambda *_args: SimpleNamespace(
            returncode=5, stdout="", stderr="ERROR: Entry not found",
        ),
    )
    assert not service._extract_rpf_entry(
        archive, "missing.bin", output, allow_missing=True,
    )
    with pytest.raises(RuntimeError, match="Could not extract"):
        service._extract_rpf_entry(archive, "missing.bin", output)

    monkeypatch.setattr(
        service, "_run_rpf_command",
        lambda *_args: SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    )
    with pytest.raises(RuntimeError, match="without extracting"):
        service._extract_rpf_entry(archive, "missing.bin", output)
    service._replace_rpf_entry(archive, "path/entry.bin", tmp_path / "payload")
    service._delete_rpf_entry(archive, "path/entry.bin")

    monkeypatch.setattr(
        service, "_run_rpf_command",
        lambda *_args: SimpleNamespace(returncode=99, stdout="", stderr="failure"),
    )
    with pytest.raises(RuntimeError, match="Could not replace"):
        service._replace_rpf_entry(archive, "path/entry.bin", tmp_path / "payload")
    with pytest.raises(RuntimeError, match="Could not delete"):
        service._delete_rpf_entry(archive, "path/entry.bin")


def test_dlc_registration_helper_contract(tmp_path: Path, monkeypatch):
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    helper = tmp_path / "helper.exe"
    helper.write_bytes(b"MZ")
    monkeypatch.setattr(service, "_rpf_patcher_path", lambda *_args: helper)
    results = iter((
        SimpleNamespace(returncode=0, stdout="registered", stderr=""),
        SimpleNamespace(returncode=0, stdout="No changes needed", stderr=""),
        SimpleNamespace(returncode=9, stdout="", stderr="registration failed"),
    ))
    monkeypatch.setattr("allin1.mods.run_hidden", lambda *_args, **_kwargs: next(results))

    assert service._set_dlc_registration("valid_pack", True)
    assert not service._set_dlc_registration("valid_pack", False)
    with pytest.raises(RuntimeError, match="registration failed"):
        service._set_dlc_registration("valid_pack", True)
    with pytest.raises(ValueError, match="Invalid DLC pack"):
        service._set_dlc_registration("bad pack", True)
