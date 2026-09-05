"""Dependency copy and rollback failures retain original bytes for recovery."""
import hashlib
from pathlib import Path

import pytest

from allin1 import reactor_dependency as reactor


@pytest.mark.parametrize("boundary", ["target-preflight", "source-preflight", "copied-bytes", "restore-locked"])
def test_dependency_transaction_failure_preserves_or_retains_original(tmp_path, monkeypatch, boundary):
    root = tmp_path / "Disposable installation with spaces"
    root.mkdir()
    target = root / "plugins/fixture.dll"
    target.parent.mkdir()
    target.write_bytes(b"original")
    source = tmp_path / "replacement"
    source.write_bytes(b"replacement")
    digest = lambda data: hashlib.sha256(data).hexdigest()
    kwargs = {}
    if boundary == "target-preflight": kwargs["expected_targets"] = {"plugins/fixture.dll": "0" * 64}
    elif boundary == "source-preflight": kwargs["expected_sources"] = {"plugins/fixture.dll": "0" * 64}
    elif boundary == "copied-bytes":
        monkeypatch.setattr(reactor, "_atomic_copy", lambda source, dest: dest.write_bytes(b"corrupt copy"))
    else:
        def copy_failure(source, dest): raise OSError("synthetic deployment failure")
        monkeypatch.setattr(reactor, "_atomic_copy", copy_failure)
        original_copy = reactor.shutil.copyfile
        def locked_restore(source_path, destination, *args, **kwargs):
            if Path(destination) == target: raise PermissionError("synthetic destination locked")
            return original_copy(source_path, destination, *args, **kwargs)
        monkeypatch.setattr(reactor.shutil, "copyfile", locked_restore)
    with pytest.raises(reactor.ReactorInstallError):
        reactor._transaction(root, {"plugins/fixture.dll": source}, **kwargs)
    assert target.read_bytes() == b"original"
    assert source.read_bytes() == b"replacement"
    if boundary == "restore-locked":
        assert (root / "allin1_backups/ReactorRecovery/plugins/fixture.dll").read_bytes() == b"original"


def test_dependency_rollback_removes_only_newly_owned_file(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"fixture")
    root = tmp_path / "target"
    root.mkdir()
    canary = root / "user.txt"
    canary.write_bytes(b"preserve")
    real_copy = reactor._atomic_copy
    def copy(source, target):
        if target.name == "second": raise OSError("synthetic second copy failed")
        return real_copy(source, target)
    monkeypatch.setattr(reactor, "_atomic_copy", copy)
    with pytest.raises(OSError, match="synthetic"):
        reactor._transaction(root, {"first": source, "second": source})
    assert list(root.iterdir()) == [canary] and canary.read_bytes() == b"preserve"
