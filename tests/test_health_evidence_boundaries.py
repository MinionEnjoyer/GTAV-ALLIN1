"""Health checks fail closed on corrupt local evidence, without launching anything."""
import json
from pathlib import Path

import pytest

from allin1 import health


@pytest.mark.parametrize("raw", [None, b"", b"x" * 16385, b"\xff", b"wrong\nkey=value",
    b"HEADER\nmalformed", b"HEADER\nunknown=value", b"HEADER\nkey=one\nkey=two",
    b"HEADER\nkey=", b"HEADER\n", b"HEADER\n\nkey=value\n"], ids=["absent", "empty", "oversize", "utf8", "preamble", "malformed", "unknown", "duplicate", "blank-value", "missing-field", "valid"])
def test_marker_reader_rejects_ambiguous_or_unbounded_evidence(tmp_path, raw):
    path = tmp_path / "marker"
    if raw is not None: path.write_bytes(raw)
    result, detail = health._read_strict_key_value_marker(path, fields=frozenset({"key"}), preamble="HEADER")
    if raw == b"HEADER\n\nkey=value\n": assert result == {"key": "value"} and detail == "verified"
    else: assert result is None and detail != "verified"


@pytest.mark.parametrize("raw", [None, b"", b"x" * 65537, b"\xff", b"{", b"[]", b'{"same":1,"same":2}', b'{"ok":1}'], ids=["absent", "empty", "oversize", "utf8", "malformed", "array", "duplicate", "valid"])
def test_receipt_reader_requires_bounded_unique_object(tmp_path, raw):
    path = tmp_path / "receipt"
    if raw is not None: path.write_bytes(raw)
    result, detail = health._read_bounded_json_object(path)
    if raw == b'{"ok":1}': assert result == {"ok": 1}
    else: assert result is None and detail != "verified"


@pytest.mark.parametrize("mutation", ["marker-array", "marker-json", "marker-utf8", "missing-reference",
    "reference-type", "missing-manifest", "outside-manifest", "manifest-array", "manifest-json",
    "missing-status", "status-type", "unknown-status", "active-labels", "inactive"])
def test_performance_isolation_evidence_cannot_silently_allow_launch(tmp_path, mutation):
    root = tmp_path / health.PERFORMANCE_ISOLATION_ROOT
    root.mkdir(parents=True)
    pointer = root / health.PERFORMANCE_ISOLATION_POINTER
    manifest = root / "session.json"
    manifest.write_text(json.dumps({"status": "active"}), encoding="utf-8")
    marker = {"manifest": "session.json"}
    if mutation == "marker-array": marker = []
    elif mutation == "missing-reference": marker = {}
    elif mutation == "reference-type": marker["manifest"] = 17
    elif mutation == "missing-manifest": marker["manifest"] = "missing.json"
    elif mutation == "outside-manifest":
        outside = tmp_path / "outside.json"
        outside.write_text('{"status":"restored"}', encoding="utf-8")
        marker["manifest"] = str(outside)
    elif mutation == "manifest-array": manifest.write_text("[]", encoding="utf-8")
    elif mutation == "manifest-json": manifest.write_text("{", encoding="utf-8")
    elif mutation == "missing-status": manifest.write_text("{}", encoding="utf-8")
    elif mutation == "status-type": manifest.write_text('{"status":1}', encoding="utf-8")
    elif mutation == "unknown-status": manifest.write_text('{"status":"unrecognized"}', encoding="utf-8")
    elif mutation == "active-labels": manifest.write_text(json.dumps({"status": "active", "session_id": [], "current_stage": " \n "}), encoding="utf-8")
    elif mutation == "inactive": manifest.write_text(json.dumps({"status": next(iter(health.PERFORMANCE_ISOLATION_INACTIVE_STATUSES))}), encoding="utf-8")
    pointer.write_text(json.dumps(marker), encoding="utf-8")
    if mutation == "marker-json": pointer.write_bytes(b"{")
    elif mutation == "marker-utf8": pointer.write_bytes(b"\xff")
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    issue = health._scan_performance_isolation(tmp_path)
    if mutation == "inactive": assert issue is None
    else:
        assert issue.severity == "error"
        assert issue.code == ("performance_isolation_active" if mutation == "active-labels" else "performance_isolation_invalid")
    assert before == {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("boundary", ["lstat", "resolve", "read"])
def test_unreadable_isolation_state_blocks_launch(tmp_path, monkeypatch, boundary):
    root = tmp_path / health.PERFORMANCE_ISOLATION_ROOT
    root.mkdir(parents=True)
    pointer = root / health.PERFORMANCE_ISOLATION_POINTER
    pointer.write_text('{"manifest":"session.json"}', encoding="utf-8")
    method = {"lstat": "lstat", "resolve": "resolve", "read": "read_text"}[boundary]
    original = getattr(Path, method)
    def fail(path, *args, **kwargs):
        if path == pointer: raise PermissionError("synthetic evidence access denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, method, fail)
    issue = health._scan_performance_isolation(tmp_path)
    assert issue.code == "performance_isolation_invalid" and issue.severity == "error"
