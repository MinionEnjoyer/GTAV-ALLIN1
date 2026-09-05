"""Adversarial assistant archives and rollback roots; no real installations."""
import hashlib
import io
import json
import os
import subprocess
import zipfile

import pytest

from allin1 import assistant_manager as manager
from allin1.desktop_service import LauncherService
from tests.test_assistant_manager import _package_bytes, _write_package


def rewrite(path, additions=(), metadata=None):
    with zipfile.ZipFile(io.BytesIO(_package_bytes())) as original:
        rows = {item.filename: original.read(item) for item in original.infolist()}
    if metadata:
        name, transform = metadata
        rows[name] = transform(rows[name])
        if name != "checksums.json":
            hashes = json.loads(rows["checksums.json"])
            hashes[name] = hashlib.sha256(rows[name]).hexdigest()
            rows["checksums.json"] = json.dumps(hashes).encode()
    with zipfile.ZipFile(path, "w") as output:
        for name, content in rows.items(): output.writestr(name, content)
        for name, content in additions:
            entry = zipfile.ZipInfo("placeholder")
            entry.filename = entry.orig_filename = name
            output.writestr(entry, content)
    return path


@pytest.mark.parametrize("name", ["../escape/", "/absolute/", "C:/drive/", "//server/share/", "bad\\folder/",
                                       "dir/../escape/", "dir//child/", "dir/./child/", "NUL/", "dir. /",
                                       "runtime/llama-server.exe/", "runtime/LLAMA-SERVER.EXE"])
def test_all_members_preflight_before_any_destination_write(tmp_path, name):
    archive = rewrite(tmp_path / "bad.zip", [(name, b"")])
    root = tmp_path / "assistant"
    canary = tmp_path / "escape"; canary.write_bytes(b"outside")
    with pytest.raises(ValueError):
        manager.install_assistant_archive(archive, root, enforce_hardware=False)
    assert not root.exists()
    assert canary.read_bytes() == b"outside"


@pytest.mark.parametrize("key", ["../escape", "C:/escape", "bad\\escape", "runtime/llama-server.exe ", "extra.bin"])
def test_checksum_names_cannot_supply_an_independent_destination(tmp_path, key):
    archive = rewrite(tmp_path / "bad.zip", metadata=("checksums.json",
        lambda data: json.dumps({**json.loads(data), key: "0" * 64}).encode()))
    before = LauncherService.tree_identity(tmp_path)
    with pytest.raises(ValueError):
        manager.install_assistant_archive(archive, tmp_path / "assistant", enforce_hardware=False)
    assert LauncherService.tree_identity(tmp_path) == before


@pytest.mark.parametrize("name", ["assistant-package.json", "checksums.json"])
def test_duplicate_json_keys_rejected(tmp_path, name):
    archive = rewrite(tmp_path / "duplicate.zip", metadata=(name, lambda data: b'{"extra":1,"extra":2,' + data[1:]))
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        manager.inspect_assistant_archive(archive)


@pytest.mark.parametrize("operation", ["install", "uninstall", "restore"])
@pytest.mark.parametrize("relative", ["component", ".component.installing", ".component.previous"])
def test_hardlink_escape_in_any_owned_tree_prevents_all_mutations(tmp_path, operation, relative):
    archive = _write_package(tmp_path / "valid.zip")
    root = tmp_path / "assistant"; (root / relative).mkdir(parents=True)
    outside = tmp_path / "outside.canary"; outside.write_bytes(b"keep")
    os.link(outside, root / relative / "linked.txt")
    (root / "config.json").write_text("keep config")
    with pytest.raises(ValueError, match="Hard-linked"):
        if operation == "install": manager.install_assistant_archive(archive, root, enforce_hardware=False)
        elif operation == "uninstall": manager.uninstall_assistant(root)
        else: manager._prepare_assistant_transaction(root)
    assert outside.read_bytes() == b"keep"
    assert (root / relative / "linked.txt").read_bytes() == b"keep"
    assert (root / "config.json").read_text() == "keep config"


def test_invalid_backup_not_restored_and_pending_preserved(tmp_path):
    root = tmp_path / "assistant"
    backup = root / ".component.previous"; backup.mkdir(parents=True)
    (backup / "old.txt").write_text("unverified")
    pending = root / ".component.installing"; pending.mkdir()
    (pending / "download.txt").write_text("retained")
    before = LauncherService.tree_identity(tmp_path)
    with pytest.raises(ValueError, match="metadata is missing"):
        manager._prepare_assistant_transaction(root)
    assert LauncherService.tree_identity(tmp_path) == before


def test_runtime_archive_preflight_leaves_no_partial_extraction(tmp_path):
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("llama-server.exe", b"MZsynthetic")
        output.writestr("../outside/", b"")
    root = tmp_path / "runtime"
    with pytest.raises(ValueError): manager._extract_runtime_archive(archive, root)
    assert not root.exists()


def test_corrupted_backup_digest_rejected_before_recovery(tmp_path):
    archive = _write_package(tmp_path / "valid.zip")
    root = tmp_path / "assistant"
    manager.install_assistant_archive(archive, root, enforce_hardware=False)
    (root / "component").rename(root / ".component.previous")
    (root / ".component.previous/models/test.gguf").write_bytes(b"GGUFtampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        manager._prepare_assistant_transaction(root)
    assert not (root / "component").exists()
    assert (root / ".component.previous/models/test.gguf").read_bytes() == b"GGUFtampered"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction boundary")
@pytest.mark.parametrize("location", ["root", "component", ".component.installing", ".component.previous"])
def test_windows_junctions_cannot_redirect_install_or_cleanup(tmp_path, location):
    outside = tmp_path / "outside"; outside.mkdir()
    (outside / "canary.txt").write_bytes(b"outside user data")
    root = tmp_path / "assistant"
    if location != "root": root.mkdir()
    link = root if location == "root" else root / location
    result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
    try:
        archive = _write_package(tmp_path / "valid.zip")
        for action in (lambda: manager.install_assistant_archive(archive, root, enforce_hardware=False),
                       lambda: manager.uninstall_assistant(root)):
            with pytest.raises(ValueError, match="junction"):
                action()
            assert (outside / "canary.txt").read_bytes() == b"outside user data"
            assert list(outside.iterdir()) == [outside / "canary.txt"]
    finally:
        # Remove only the junction created above, never its target or contents.
        assert link.parent == tmp_path or link.parent == root
        assert link.lstat().st_file_attributes & 0x400
        os.rmdir(link)
