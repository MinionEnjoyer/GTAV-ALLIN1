"""Deployment fault injection uses only disposable roots and outside canaries."""
import json
import os
from pathlib import Path

import pytest

from allin1 import installer


@pytest.fixture
def deployment(tmp_path):
    sources, targets = tmp_path / "sources", tmp_path / "install with spaces"
    sources.mkdir()
    targets.mkdir()
    entries = []
    for name in ("core.dll", "bridge.plugin"):
        source, target = sources / name, targets / name
        source.write_bytes(b"new " + name.encode())
        target.write_bytes(b"old " + name.encode())
        entries.append((source, target))
    return tuple(entries)


@pytest.mark.parametrize(("operation", "linked"), [
    ("single", "source"), ("single", "destination"), ("single", "backup"),
    ("pair", "source"), ("pair", "destination"),
    ("json", "destination"), ("json", "backup"),
])
def test_preflight_rejects_hardlinks_without_changing_canary(tmp_path, deployment, operation, linked):
    source, target = deployment[0]
    canary = tmp_path / "outside-canary"
    canary.write_bytes(b"outside")
    path = {"source": source, "destination": target, "backup": target.with_name(target.name + ".bak")}[linked]
    path.unlink(missing_ok=True)
    os.link(canary, path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="linked"):
        if operation == "single": installer._copy_atomic(source, target)
        elif operation == "pair": installer._copy_files_transactionally(deployment)
        else: installer._write_json_atomic({"safe": True}, target)
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_pair_preflights_all_targets_before_staging(tmp_path, deployment):
    canary = tmp_path / "outside"
    canary.write_bytes(b"keep")
    deployment[1][1].unlink()
    os.link(canary, deployment[1][1])
    with pytest.raises(ValueError):
        installer._copy_files_transactionally(deployment)
    assert deployment[0][1].read_bytes() == b"old core.dll"
    assert sorted(p.name for p in deployment[0][1].parent.iterdir()) == ["bridge.plugin", "core.dll"]
    assert canary.read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["duplicate", "case-alias", "parent-child", "missing-source", "directory"])
def test_invalid_pair_plan_has_no_writes(deployment, kind):
    first, second = deployment
    if kind == "duplicate": second = (second[0], first[1])
    elif kind == "case-alias": second = (second[0], first[1].with_name("CORE.DLL"))
    elif kind == "parent-child": second = (second[0], first[1] / "child")
    elif kind == "missing-source": second = (second[0].with_name("missing"), second[1])
    else: second = (second[0], second[1].parent)
    with pytest.raises((OSError, ValueError)):
        installer._copy_files_transactionally((first, second))
    assert first[1].read_bytes() == b"old core.dll"
    assert deployment[1][1].read_bytes() == b"old bridge.plugin"


@pytest.mark.parametrize("operation", ["single", "pair"])
def test_partial_copy_failure_does_not_restore_stale_backup(deployment, monkeypatch, operation):
    source, target = deployment[0]
    backup = target.with_name(target.name + ".bak")
    backup.write_bytes(b"ancient")
    original = installer.shutil.copy2
    def fail_copy(src, dst, *args, **kwargs):
        if Path(src) == source:
            Path(dst).write_bytes(b"partial")
            raise OSError("injected copy failure")
        return original(src, dst, *args, **kwargs)
    monkeypatch.setattr(installer.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="injected"):
        if operation == "single": installer._copy_atomic(source, target)
        else: installer._copy_files_transactionally(deployment)
    assert target.read_bytes() == b"old core.dll"
    assert backup.read_bytes() == b"ancient"
    assert not list(target.parent.glob("*.tmp*"))
    assert not list(target.parent.glob("*.pair.bak"))


@pytest.mark.parametrize("existing", [True, False])
def test_pair_commit_failure_rolls_back_only_committed_destinations(deployment, monkeypatch, existing):
    first, second = deployment
    if not existing:
        first[1].unlink()
    replace = os.replace
    def fail_second(src, dst):
        if Path(dst) == second[1] and str(src).endswith(".pair.tmp"):
            second[1].write_bytes(b"concurrent edit")
            raise PermissionError("injected locked second target")
        return replace(src, dst)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(PermissionError, match="injected"):
        installer._copy_files_transactionally(deployment)
    assert first[1].exists() == existing
    if existing: assert first[1].read_bytes() == b"old core.dll"
    assert second[1].read_bytes() == b"concurrent edit"
    assert not list(first[1].parent.glob("*.pair.*"))


@pytest.mark.parametrize("changed", ["destination", "backup"])
def test_failed_rollback_preserves_concurrent_edits_and_recovery_backup(deployment, monkeypatch, changed):
    first, second = deployment
    replace = os.replace
    def fail_second(src, dst):
        if Path(dst) == second[1] and str(src).endswith(".pair.tmp"):
            victim = first[1] if changed == "destination" else next(first[1].parent.glob("core.dll.*.pair.bak"))
            victim.write_bytes(b"concurrent edit")
            raise PermissionError("injected failure")
        return replace(src, dst)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(RuntimeError, match="rollback incomplete.*backups retained"):
        installer._copy_files_transactionally(deployment)
    assert first[1].read_bytes() == (b"concurrent edit" if changed == "destination" else b"new core.dll")
    backups = list(first[1].parent.glob("*.pair.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == (b"old core.dll" if changed == "destination" else b"concurrent edit")
    assert second[1].read_bytes() == b"old bridge.plugin"


@pytest.mark.parametrize("operation", ["single", "pair"])
def test_staging_detects_destination_change_and_preserves_it(deployment, monkeypatch, operation):
    source, target = deployment[0]
    copy = installer.shutil.copy2
    def edit_during_copy(src, dst, *args, **kwargs):
        result = copy(src, dst, *args, **kwargs)
        if Path(src) == source: target.write_bytes(b"concurrent edit")
        return result
    monkeypatch.setattr(installer.shutil, "copy2", edit_during_copy)
    with pytest.raises(ValueError, match="changed during staging"):
        if operation == "single": installer._copy_atomic(source, target)
        else: installer._copy_files_transactionally(deployment)
    assert target.read_bytes() == b"concurrent edit"
    assert not list(target.parent.glob("*.tmp*"))


@pytest.mark.parametrize("operation", ["single", "pair"])
def test_legacy_shared_staging_names_are_not_used(deployment, operation):
    source, target = deployment[0]
    legacy = [target.with_name(target.name + suffix) for suffix in (".tmp", ".pair.tmp", ".pair.bak")]
    for path in legacy: path.write_bytes(b"unrelated user file")
    if operation == "single": installer._copy_atomic(source, target)
    else: installer._copy_files_transactionally(deployment)
    assert all(path.read_bytes() == b"unrelated user file" for path in legacy)
    assert target.read_bytes() == source.read_bytes()


def test_json_serialization_failure_is_read_only_and_success_retains_previous(deployment):
    _, target = deployment[0]
    with pytest.raises(ValueError):
        installer._write_json_atomic({"invalid": float("nan")}, target)
    assert target.read_bytes() == b"old core.dll"
    assert not target.with_name(target.name + ".bak").exists()
    installer._write_json_atomic({"schema_version": 1}, target)
    assert json.loads(target.read_text()) == {"schema_version": 1}
    assert target.with_name(target.name + ".bak").read_bytes() == b"old core.dll"
