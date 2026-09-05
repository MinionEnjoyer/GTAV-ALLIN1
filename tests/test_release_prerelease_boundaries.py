"""Portable release refusals and process guards; every root/API is disposable."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from allin1 import desktop_service, processes, updater
from tests.test_updater_containment import archive


@pytest.mark.parametrize("returncode,stdout,message", [
    (1, '"explorer.exe","100"', "Could not verify"),
    (0, "", "Could not verify"),
    (0, "not-csv", "Invalid process inventory"),
    (0, '"GTA5.exe","101"', "Close GTA"),
    (0, '"GTA5_Enhanced.exe","102"', "Close GTA"),
    (0, '"PlayGTAV.exe","103"', "Close GTA"),
    (0, '"explorer.exe","100"', None),
])
def test_write_authorization_requires_valid_closed_game_inventory(monkeypatch, returncode, stdout, message):
    seen = []
    monkeypatch.setattr(desktop_service, "os", SimpleNamespace(name="nt", environ={"SystemRoot": "C:/Windows"}))
    def inventory(command, **kwargs):
        seen.append(command)
        assert kwargs == {"capture_output": True, "text": True, "timeout": 15}
        assert Path(command[0]).name == "tasklist.exe" and command[1:] == ["/FO", "CSV", "/NH"]
        return SimpleNamespace(returncode=returncode, stdout=stdout)
    monkeypatch.setattr(processes, "run_hidden", inventory)
    if message:
        with pytest.raises(ValueError, match=message): desktop_service.LauncherService.require_closed()
    else:
        assert desktop_service.LauncherService.require_closed() is None
    assert len(seen) == 1


def test_non_windows_host_cannot_authorize_game_writes(monkeypatch):
    monkeypatch.setattr(desktop_service, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(processes, "run_hidden", lambda *a, **k: pytest.fail("Must not inspect real processes"))
    with pytest.raises(ValueError, match="Windows process checks"):
        desktop_service.LauncherService.require_closed()


@pytest.mark.parametrize("mutation", ["no-manifest", "empty", "array", "bad-hash", "hash-type", "content", "too-many", "too-big"])
def test_release_manifest_refusal_precedes_all_destination_writes(tmp_path, monkeypatch, mutation):
    path = tmp_path / "payload.zip"
    manifest = {"payload": hashlib.sha256(b"payload").hexdigest()}
    if mutation == "empty": manifest = {}
    elif mutation == "array": manifest = []
    elif mutation == "bad-hash": manifest["payload"] = "invalid"
    elif mutation == "hash-type": manifest["payload"] = False
    elif mutation == "content": manifest["payload"] = "0" * 64
    elif mutation == "too-many": monkeypatch.setattr(updater, "MAX_RELEASE_FILES", 1)
    elif mutation == "too-big": monkeypatch.setattr(updater, "MAX_RELEASE_BYTES", 1)
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("payload", b"payload")
        if mutation != "no-manifest": package.writestr("checksums.json", json.dumps(manifest))
    before = path.read_bytes()
    with pytest.raises(ValueError): updater.deploy_release(path, tmp_path / "app", tmp_path / "backup")
    assert not (tmp_path / "app").exists() and not (tmp_path / "backup").exists()
    assert path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["shape", "schema", "evidence", "fields", "before", "after", "backup", "selection"])
def test_bad_rollback_evidence_preserves_current_installation(tmp_path, mutation):
    root = tmp_path / "app"; root.mkdir()
    owned = root / "payload"; owned.write_bytes(b"old")
    package = archive(tmp_path / "payload.zip", [("payload", b"new")])
    result = updater.deploy_release(package, root, tmp_path / "backups")
    receipt = result.backup / "deployed.json"
    data = json.loads(receipt.read_text())
    selected = None
    if mutation == "shape": data = []
    elif mutation == "schema": data["schema_version"] = 1
    elif mutation == "evidence": data["files"]["payload"] = []
    elif mutation == "fields": data["files"]["payload"]["extra"] = "ambiguous"
    elif mutation == "before": data["files"]["payload"]["before"] = 10
    elif mutation == "after": data["files"]["payload"]["after"] = "bad"
    elif mutation == "backup": (result.backup / "files/payload").write_bytes(b"tampered")
    else: selected = ["unowned"]
    receipt.write_text(json.dumps(data))
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError): updater.rollback_update(root, result.backup, selected)
    assert owned.read_bytes() == b"new"
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mutation", ["missing-source", "reserved-manifest", "input-as-output", "directory-destination", "nested-backups"])
def test_package_and_deployment_boundaries_refuse_invalid_roots(tmp_path, mutation):
    source = tmp_path / "payload"; source.write_bytes(b"original")
    if mutation == "missing-source":
        run = lambda: updater.package_release(tmp_path / "package.zip", tmp_path, [Path("absent")])
    elif mutation == "reserved-manifest":
        run = lambda: updater.package_release(tmp_path / "package.zip", tmp_path, [source], extra_files={"CHECKSUMS.JSON": b"bad"})
    elif mutation == "input-as-output":
        run = lambda: updater.package_release(source, tmp_path, [source])
    else:
        package = archive(tmp_path / "package.zip", [("payload", b"new")])
        root = tmp_path / "app"; root.mkdir()
        if mutation == "directory-destination": (root / "payload").mkdir()
        run = lambda: updater.deploy_release(package, root, root / "backup" if mutation == "nested-backups" else tmp_path / "backup")
    with pytest.raises((ValueError, FileNotFoundError)): run()
    assert source.read_bytes() == b"original"


@pytest.mark.parametrize("phase", ["stage", "backup", "pre-deploy"])
def test_changed_content_during_deployment_never_overwrites_user_file(tmp_path, monkeypatch, phase):
    root = tmp_path / "app"; root.mkdir()
    owned = root / "payload"; owned.write_bytes(b"old")
    package = archive(tmp_path / "payload.zip", [("payload", b"new")])
    original = updater._sha
    observed = 0
    def changed(path):
        nonlocal observed
        if path == owned:
            observed += 1
            if phase == "pre-deploy" and observed == 2: return "f" * 64
        elif phase == "stage" and "allin1-update-" in str(path): return "f" * 64
        elif phase == "backup" and "backups" in path.parts: return "f" * 64
        return original(path)
    monkeypatch.setattr(updater, "_sha", changed)
    with pytest.raises(ValueError, match="checksum mismatch|changed"):
        updater.deploy_release(package, root, tmp_path / "backups")
    assert owned.read_bytes() == b"old"
