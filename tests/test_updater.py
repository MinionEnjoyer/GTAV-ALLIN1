import hashlib
import json
import zipfile
import pytest
from allin1.updater import deploy_release, package_release, rollback_update


def _release(path, files, checksums=None):
    checksums = checksums or {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items(): archive.writestr(name, data)
        archive.writestr("checksums.json", json.dumps(checksums))


def test_deploy_and_rollback_release(tmp_path):
    destination = tmp_path / "game"; (destination / "scripts").mkdir(parents=True)
    (destination / "scripts/mod.dll").write_bytes(b"old")
    archive = tmp_path / "release.zip"; _release(archive, {"scripts/mod.dll": b"new", "scripts/version": b"2"})
    result = deploy_release(archive, destination, tmp_path / "backups")
    assert (destination / "scripts/mod.dll").read_bytes() == b"new"
    assert set(rollback_update(destination, result.backup)) == set(result.deployed)
    assert (destination / "scripts/mod.dll").read_bytes() == b"old"
    assert not (destination / "scripts/version").exists()


def test_updater_rejects_invalid_archives(tmp_path):
    bad = tmp_path / "bad.zip"; _release(bad, {"mod.dll": b"x"}, {"mod.dll": "0" * 64})
    with pytest.raises(ValueError, match="checksum"): deploy_release(bad, tmp_path / "dest", tmp_path / "backup")
    missing = tmp_path / "missing.zip"
    with zipfile.ZipFile(missing, "w") as archive: archive.writestr("x", b"x")
    with pytest.raises(ValueError, match="checksums"): deploy_release(missing, tmp_path / "dest", tmp_path / "backup")
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive: archive.writestr("../x", b"x")
    with pytest.raises(ValueError, match="unsafe"): deploy_release(unsafe, tmp_path / "dest", tmp_path / "backup")


def test_rollback_requires_marker(tmp_path):
    with pytest.raises(FileNotFoundError): rollback_update(tmp_path, tmp_path / "missing")


def test_package_release_is_deployable(tmp_path):
    root = tmp_path / "root"; (root / "scripts").mkdir(parents=True)
    source = root / "scripts/mod.dll"; source.write_bytes(b"release")
    archive = package_release(tmp_path / "release.zip", root, [source])
    result = deploy_release(archive, tmp_path / "game", tmp_path / "backups")
    assert result.deployed == ("scripts/mod.dll",)
    assert (tmp_path / "game/scripts/mod.dll").read_bytes() == b"release"
    with pytest.raises(FileNotFoundError): package_release(tmp_path / "x.zip", root, [root / "missing"])
