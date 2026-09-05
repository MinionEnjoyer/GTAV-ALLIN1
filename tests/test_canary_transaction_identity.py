"""Recovery journals and artifacts cannot substitute another transaction's bytes."""
import json

import pytest

from allin1 import map_grapeseed_stock_bridge_canary as phase
from tests.test_map_grapeseed_stock_bridge_canary import _install


@pytest.mark.parametrize("field,value", [
    ("schema", 0), ("canary_id", "other"), ("phase", "other"), ("edition", "legacy"),
    ("status", "unknown"), ("transaction_id", "../escape"), ("pack_existed", 1),
    ("original_pack_manifest", []), ("deployed_pack_manifest", []), ("source_attestation", []),
    ("davis_bridge_snapshot", []), ("topology", []), ("archive_bytes", "10"), ("archive_bytes", 0),
    *[(name, "invalid") for name in ("original_dlclist_sha256", "archive_sha256", "marker_sha256",
        "runtime_receipt_sha256", "content_xml_sha256", "setup2_xml_sha256")]])
def test_corrupt_journal_is_rejected_without_changing_deployed_files(tmp_path, monkeypatch, field, value):
    game, patcher, state, tool, receipt = _install(tmp_path, monkeypatch)
    path = state / phase.JOURNAL
    journal = json.loads(path.read_bytes())
    journal[field] = value
    path.write_text(json.dumps(journal), encoding="utf-8")
    before = phase.shared._file_manifest(game)
    with pytest.raises(RuntimeError): phase._load_transaction_journal(state)
    assert phase.shared._file_manifest(game) == before


def test_original_pack_identity_requires_its_actual_backup(tmp_path, monkeypatch):
    game, patcher, state, tool, receipt = _install(tmp_path, monkeypatch)
    path = state / phase.JOURNAL
    journal = json.loads(path.read_bytes())
    journal["pack_existed"] = True
    journal["original_pack_manifest"] = {}
    path.write_text(json.dumps(journal), encoding="utf-8")
    with pytest.raises(RuntimeError, match="inconsistent"):
        phase._load_transaction_journal(state)
    (state / phase.ORIGINAL_PACK_BACKUP).mkdir()
    assert phase._load_transaction_journal(state)["pack_existed"] is True


def test_artifact_read_failure_cannot_partially_verify_transaction(tmp_path, monkeypatch):
    game, patcher, state, tool, receipt = _install(tmp_path, monkeypatch)
    journal = phase._load_transaction_journal(state)
    assert all(phase._transaction_artifact_checks(state, journal).values())
    def denied(path): raise PermissionError("synthetic artifact access denied")
    monkeypatch.setattr(phase.shared, "_sha256", denied)
    assert not any(phase._transaction_artifact_checks(state, journal).values())


@pytest.mark.parametrize("kind", ["absent", "file", "deployed", "original", "changed", "unreadable"])
def test_recovery_classification_requires_exact_tree_identity(tmp_path, monkeypatch, kind):
    path = tmp_path / "candidate"
    if kind == "file": path.write_bytes(b"not a directory")
    elif kind != "absent":
        path.mkdir()
        (path / "payload").write_bytes(b"fixture")
    manifest = phase.shared._file_manifest(path) if path.is_dir() else {}
    expected = {"original_manifest": manifest if kind == "original" else {},
        "deployed_manifest": manifest if kind == "deployed" else {}}
    if kind == "unreadable":
        def denied(path): raise PermissionError("synthetic manifest access denied")
        monkeypatch.setattr(phase.shared, "_file_manifest", denied)
    assert phase._manifest_kind(path, **expected) == (kind if kind in {"absent", "deployed", "original"} else "unknown")
    with pytest.raises(RuntimeError, match="transaction id"):
        phase._transaction_paths(tmp_path, "../outside")
