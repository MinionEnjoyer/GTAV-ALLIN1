"""All-or-restored package toggles across loose, archive and registry layers."""
import hashlib
import json
from pathlib import Path

import pytest

from allin1.extensions import ExtensionRegistry
from allin1.mods import ModIntegrationService, ModManifest
from tests.test_mods import _game, _rpf_entry_package, _fake_rpf_service


def snapshot(game):
    result = {}
    registry = Path("scripts/.allin1/extensions/registry.json")
    for file in game.rglob("*"):
        if not file.is_file(): continue
        relative = file.relative_to(game)
        if relative in {registry, registry.with_suffix(".json.bak")}:
            # Rebuilding the derived registry legitimately updates its time and
            # retains a previous generation. Compare its authorization, not time.
            data = json.loads(file.read_bytes())
            data.pop("generated_at")
            assert data == {"api_version": 1, "schema_version": 1, "extensions": []}
            if relative == registry: result[relative] = data
        else: result[relative] = file.read_bytes()
    return result


def mixed_tree(tmp_path, monkeypatch, original):
    game = _game(tmp_path)
    (game / "x64h.rpf").write_bytes(b"synthetic base RPF")
    package = _rpf_entry_package(tmp_path, "recovery", mod_type="mixed")
    manifest = package / "mod.toml"
    text = manifest.read_text(encoding="utf-8").replace('type = "mixed"', 'type = "mixed"\ndlc_packs = ["recovery_pack"]')
    for name, relative in [("config", "scripts/recovery.ini"), ("archive", "mods/update/x64/dlcpacks/recovery_pack/dlc.rpf")]:
        (package / name).write_bytes(f"new {name}".encode())
        text += f'\n[[files]]\nsource = "{name}"\ndestination = "{relative}"\n'
        if original:
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f"original {name}".encode())
    manifest.write_text(text, encoding="utf-8")
    service = ModIntegrationService(game)
    archive = game / "mods/x64h.rpf"
    entries = {(str(archive.resolve()).casefold(), "levels/gta5/test.bin"): b"original entry"} if original else {}
    _fake_rpf_service(service, monkeypatch, entries)
    registrations = set()
    def register(pack, enabled):
        changed = (pack in registrations) != enabled
        if enabled: registrations.add(pack)
        else: registrations.discard(pack)
        return changed
    monkeypatch.setattr(service, "_set_dlc_registration", register)
    service.install(ModManifest.load(package))
    return game, service, entries, registrations


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("original", [False, True])
@pytest.mark.parametrize("failure", ["receipt", "registry", "loose-move", "registration"])
def test_toggle_fault_restores_every_completed_layer(tmp_path, monkeypatch, enabled, original, failure):
    game, service, entries, registrations = mixed_tree(tmp_path, monkeypatch, original)
    if enabled: service.set_enabled("recovery", False)
    before_files = snapshot(game)
    before_entries, before_registration = dict(entries), set(registrations)
    triggered = False

    if failure == "registry":
        real = ExtensionRegistry.rebuild
        def rebuild(registry):
            nonlocal triggered
            if not triggered:
                triggered = True
                raise OSError("injected registry failure")
            return real(registry)
        monkeypatch.setattr(ExtensionRegistry, "rebuild", rebuild)
    elif failure == "receipt":
        real = service._write_receipt
        def write(receipt):
            nonlocal triggered
            real(receipt)
            if not triggered:
                triggered = True
                raise OSError("injected receipt failure")
        monkeypatch.setattr(service, "_write_receipt", write)
    elif failure == "registration":
        real = service._set_dlc_registration
        def register(pack, active):
            nonlocal triggered
            if not triggered:
                triggered = True
                raise OSError("injected registration failure")
            return real(pack, active)
        monkeypatch.setattr(service, "_set_dlc_registration", register)
    else:
        real = Path.replace
        moves = 0
        def replace(source, target):
            nonlocal moves, triggered
            if str(source).endswith(("recovery.ini", "recovery.ini.disabled", "dlc.rpf", "dlc.rpf.disabled")):
                moves += 1
                if moves == 2:
                    triggered = True
                    raise OSError("injected loose move failure")
            return real(source, target)
        monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError, match="injected"): service.set_enabled("recovery", enabled)
    assert triggered
    assert entries == before_entries
    assert registrations == before_registration
    assert before_files == snapshot(game)
    assert service._read_receipt("recovery")["enabled"] is not enabled


@pytest.mark.parametrize("damage", ["missing-managed", "changed-managed", "missing-backup", "changed-backup", "changed-disabled-underlay", "directory-underlay"])
def test_toggle_preflight_preserves_unowned_files_and_receipt(tmp_path, monkeypatch, damage):
    game, service, entries, registrations = mixed_tree(tmp_path, monkeypatch, True)
    enabling = damage in {"changed-disabled-underlay", "directory-underlay"}
    if enabling: service.set_enabled("recovery", False)
    receipt = service._read_receipt("recovery")
    item = receipt["files"][0]
    target = game / item["destination"]
    backup = game / item["backup"]
    if damage == "missing-managed": target.unlink()
    elif damage == "changed-managed": target.write_bytes(b"external change")
    elif damage == "missing-backup": backup.unlink()
    elif damage == "changed-backup": backup.write_bytes(b"external change")
    elif damage == "changed-disabled-underlay": target.write_bytes(b"external change")
    else:
        target.unlink()
        target.mkdir()
    before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)): service.set_enabled("recovery", enabling)
    assert before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
    assert service._read_receipt("recovery") == receipt
