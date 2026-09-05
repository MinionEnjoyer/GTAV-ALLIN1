"""Mixed-package uninstall restores all completed layers when a later write fails."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1.extensions import ExtensionRegistry
from allin1.mods import ModIntegrationService
from tests.test_mod_toggle_recovery import mixed_tree, snapshot


@pytest.mark.parametrize("original", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", ["registry", "loose-move", "receipt"])
def test_failed_uninstall_restores_payloads_registrations_and_receipt(tmp_path, monkeypatch, original, enabled, failure):
    game, service, entries, registrations = mixed_tree(tmp_path, monkeypatch, original)
    if not enabled: service.set_enabled("recovery", False)
    before = snapshot(game)
    expected_entries, expected_registrations = dict(entries), set(registrations)
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
        real = Path.unlink
        def unlink(path, *args, **kwargs):
            nonlocal triggered
            if path == service._receipt_path("recovery") and not triggered:
                triggered = True
                raise OSError("injected receipt failure")
            return real(path, *args, **kwargs)
        monkeypatch.setattr(Path, "unlink", unlink)
    else:
        real = Path.replace
        moves = 0
        def replace(path, target):
            nonlocal triggered, moves
            if ".uninstall-rollback" in Path(target).parts:
                moves += 1
                if moves == 2:
                    triggered = True
                    raise OSError("injected move failure")
            return real(path, target)
        monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(OSError, match="injected"): service.uninstall("recovery")
    assert triggered and before == snapshot(game)
    assert entries == expected_entries and registrations == expected_registrations
    assert service._read_receipt("recovery")["enabled"] is enabled


@pytest.mark.parametrize("damage", ["missing", "changed", "missing-backup", "underlay-changed", "underlay-directory", "unowned-underlay", "rpf-changed"])
def test_uninstall_preflight_rejects_external_drift_before_any_mutation(tmp_path, monkeypatch, damage):
    game, service, entries, registrations = mixed_tree(tmp_path, monkeypatch, damage != "unowned-underlay")
    if damage.startswith("underlay") or damage == "unowned-underlay": service.set_enabled("recovery", False)
    receipt = service._read_receipt("recovery")
    item = receipt["files"][0]
    target = game / item["destination"]
    if damage == "missing": target.unlink()
    elif damage == "missing-backup": (game / item["backup"]).unlink()
    elif damage == "underlay-directory":
        target.unlink()
        target.mkdir()
    elif damage == "rpf-changed":
        entries[next(iter(entries))] = b"external RPF edit"
    else: target.write_bytes(b"external user data")
    before = snapshot(game)
    expected_entries, expected_registrations = dict(entries), set(registrations)
    with pytest.raises((ValueError, FileNotFoundError, RuntimeError)): service.uninstall("recovery")
    assert before == snapshot(game)
    assert entries == expected_entries and registrations == expected_registrations


@pytest.mark.parametrize("operation", ["extract", "replace", "delete"])
@pytest.mark.parametrize("message", ["stderr", "stdout", "empty"])
def test_archive_tool_failures_cannot_be_reported_as_success(tmp_path, monkeypatch, operation, message):
    (tmp_path / "GTA5.exe").write_bytes(b"synthetic nonexecutable")
    service = ModIntegrationService(tmp_path)
    def failed(*args):
        return SimpleNamespace(returncode=9, stderr="denied" if message == "stderr" else "", stdout="denied" if message == "stdout" else "")
    monkeypatch.setattr(service, "_run_rpf_command", failed)
    archive, payload = tmp_path / "fixture.rpf", tmp_path / "payload"
    with pytest.raises(RuntimeError, match="Could not"):
        if operation == "extract": service._extract_rpf_entry(archive, "dir/file", payload, allow_missing=True)
        elif operation == "replace": service._replace_rpf_entry(archive, "dir/file", payload)
        else: service._delete_rpf_entry(archive, "dir/file")
    assert not archive.exists() and not payload.exists()


def test_archive_tool_success_requires_actual_output(tmp_path, monkeypatch):
    (tmp_path / "GTA5.exe").write_bytes(b"synthetic nonexecutable")
    service = ModIntegrationService(tmp_path)
    monkeypatch.setattr(service, "_run_rpf_command", lambda *args: SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError, match="without extracting"):
        service._extract_rpf_entry(tmp_path / "fixture.rpf", "dir/file", tmp_path / "payload")
