"""Exercise real deployment/rollback only in disposable trees."""
import hashlib
import json
import os
import subprocess
import zipfile

import pytest

from allin1.updater import deploy_release, rollback_update


def archive(path, files, manifest=None):
    with zipfile.ZipFile(path, "w") as bundle:
        for name, content in files:
            bundle.writestr(name, content)
        bundle.writestr("checksums.json", manifest if manifest is not None else json.dumps(
            {name: hashlib.sha256(content).hexdigest() for name, content in files}))
    return path


UNSAFE = ["../canary", "/canary", "C:/canary", "C:canary", "//host/share",
          "a\\..\\canary", "a\\b", "a//b", "a/./b", "a/../b", "a/CON.txt",
          "a/NUL", "a/com¹.txt", "a/b.", "a/b ", "a/ b", "a:x", "a/*"]


@pytest.mark.parametrize("name", UNSAFE)
@pytest.mark.parametrize("location", ["manifest", "archive", "rollback"])
def test_rejects_unsafe_names_before_any_destination_write(tmp_path, name, location):
    canary = tmp_path / "canary"; canary.write_bytes(b"outside")
    destination = tmp_path / "installation"; destination.mkdir()
    owned = destination / "first"; owned.write_bytes(b"original")
    files = [("first", b"new")]
    checksums = {"first": hashlib.sha256(b"new").hexdigest(), name: hashlib.sha256(b"outside").hexdigest()}
    if location == "rollback":
        backup = tmp_path / "backup"; backup.mkdir()
        (backup / "deployed.json").write_text(json.dumps({"schema_version": 2,
            "destination": str(destination), "files": {
                "first": {"before": None, "after": hashlib.sha256(b"original").hexdigest()},
                name: {"before": None, "after": hashlib.sha256(b"outside").hexdigest()},
            }}))
        run = lambda: rollback_update(destination, backup)
    else:
        if location == "archive": files.append((name, b"outside"))
        package = archive(tmp_path / "bad.zip", files, json.dumps(checksums))
        run = lambda: deploy_release(package, destination, tmp_path / "backup")
    with pytest.raises(ValueError): run()
    assert canary.read_bytes() == b"outside"
    assert owned.read_bytes() == b"original"


@pytest.mark.parametrize("files,manifest", [
    ([("A", b"1"), ("a", b"2")], None),
    ([("a", b"1"), ("a/b", b"2")], None),
    ([("a", b"1"), ("extra", b"2")], json.dumps({"a": hashlib.sha256(b"1").hexdigest()})),
    ([("a", b"1")], '{"a":"' + '0' * 64 + '","a":"' + hashlib.sha256(b"1").hexdigest() + '"}'),
])
def test_duplicates_collisions_and_undeclared_payloads(tmp_path, files, manifest):
    package = archive(tmp_path / "bad.zip", files, manifest)
    with pytest.raises(ValueError): deploy_release(package, tmp_path / "destination", tmp_path / "backup")
    assert not (tmp_path / "destination").exists()
    assert not (tmp_path / "backup").exists()


def test_retains_previous_backups_and_refuses_stale_or_wrong_target_rollback(tmp_path):
    destination = tmp_path / "installation with spaces"; destination.mkdir()
    (destination / "payload").write_bytes(b"old")
    (destination / "user-data").write_bytes(b"keep")
    package = archive(tmp_path / "good.zip", [("payload", b"new")])
    first = deploy_release(package, destination, tmp_path / "backup")
    second = deploy_release(package, destination, tmp_path / "backup")
    assert first.backup != second.backup and first.backup.is_dir()
    with pytest.raises(ValueError, match="another installation"):
        rollback_update(tmp_path / "other", first.backup)
    (destination / "payload").write_bytes(b"user edit")
    with pytest.raises(ValueError, match="changed"):
        rollback_update(destination, first.backup)
    assert (destination / "payload").read_bytes() == b"user edit"
    assert (destination / "user-data").read_bytes() == b"keep"


def test_failure_restores_already_deployed_files(tmp_path, monkeypatch):
    from allin1 import updater
    destination = tmp_path / "installation"; destination.mkdir()
    (destination / "first").write_bytes(b"old")
    package = archive(tmp_path / "good.zip", [("first", b"new"), ("second", b"new")])
    original = updater._replace
    def fail_second(source, target):
        if target.name == "second": raise OSError("injected write failure")
        original(source, target)
    monkeypatch.setattr(updater, "_replace", fail_second)
    with pytest.raises(OSError, match="injected"):
        deploy_release(package, destination, tmp_path / "backup")
    assert (destination / "first").read_bytes() == b"old"
    assert not (destination / "second").exists()


def test_junction_destination_and_backup_refused(tmp_path):
    outside = tmp_path / "outside"; outside.mkdir()
    canary = outside / "payload"; canary.write_bytes(b"keep")
    redirect = tmp_path / "redirect"
    if os.name == "nt":
        quote = lambda p: "'" + str(p).replace("'", "''") + "'"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            f"New-Item -ItemType Junction -Path {quote(redirect)} -Target {quote(outside)} | Out-Null"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
    else:
        redirect.symlink_to(outside, target_is_directory=True)
    package = archive(tmp_path / "good.zip", [("payload", b"new")])
    for destination, backup in [(redirect, tmp_path / "backup"), (tmp_path / "installation", redirect)]:
        with pytest.raises(ValueError, match="[Jj]unction|[Ss]ymlink|reparse"):
            deploy_release(package, destination, backup)
    assert canary.read_bytes() == b"keep"
