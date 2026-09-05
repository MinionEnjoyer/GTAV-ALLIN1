"""Malformed acceptance claims must fail even with matching evidence digests."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

from allin1 import release_acceptance as acceptance
from tests.test_release_acceptance import fixture


@pytest.mark.parametrize("field,value", [
    ("launcher_commit", None), ("launcher_commit", "main"),
    ("build_id", ""), ("build_id", 64), ("launcher_version", ""),
    ("source_tree_sha256", "not a digest"), ("artifacts", {}),
    ("dependencies", []), ("artifacts", {"app.exe": 12}),
    ("schema_versions", {}), ("schema_versions", []),
    ("schema_versions", {"protocol": ""}), ("schema_versions", {"protocol": 1}),
])
def test_incomplete_exact_build_identity_is_rejected(tmp_path, field, value):
    report, kwargs = fixture(tmp_path)
    identity = deepcopy(report["identity"])
    identity[field] = value
    report["identity"] = kwargs["expected_identity"] = kwargs["trusted_session"]["identity"] = identity
    with pytest.raises(ValueError): acceptance.validate_live_acceptance(report, **kwargs)


@pytest.mark.parametrize("value", [None, "yesterday", "2026-01-01T10:00:00"])
def test_non_absolute_timestamps_do_not_qualify(tmp_path, value):
    report, kwargs = fixture(tmp_path)
    report["started_at"] = kwargs["trusted_session"]["started_at"] = value
    with pytest.raises(ValueError, match="timestamp"):
        acceptance.validate_live_acceptance(report, **kwargs)


@pytest.mark.parametrize("mutation", ["anchor-version", "anchor-authority", "short-session", "suite",
    "edition", "different-expected-build", "different-expected-edition", "digest", "oversize", "naive-clock"])
def test_independent_session_and_evidence_envelope(tmp_path, monkeypatch, mutation):
    report, kwargs = fixture(tmp_path)
    if mutation == "anchor-version": kwargs["trusted_session"]["schema_version"] = True
    elif mutation == "anchor-authority": kwargs["trusted_session"]["authority"] = " "
    elif mutation == "short-session": report["session_id"] = "short"
    elif mutation == "suite": kwargs["suite"] = "unrecognized"
    elif mutation == "edition": kwargs["target_edition"] = "Online"
    elif mutation == "different-expected-build": kwargs["expected_identity"]["build_id"] = "other"
    elif mutation == "different-expected-edition": kwargs["target_edition"] = "Legacy"
    elif mutation == "digest": (tmp_path / "events.jsonl").write_bytes(b"changed")
    elif mutation == "oversize": monkeypatch.setattr(acceptance, "MAX_EVIDENCE_BYTES", 1)
    else: kwargs["now"] = kwargs["now"].replace(tzinfo=None)
    with pytest.raises(ValueError): acceptance.validate_live_acceptance(report, **kwargs)


@pytest.mark.parametrize("mutation", ["timestamp", "boundary-type", "boundary-check", "boundary-proof",
    "boundary-time", "event-type", "event-status", "empty-proof", "changed-proof", "directory-proof", "bad-shape"])
def test_rehashed_semantically_invalid_events_are_not_acceptance(tmp_path, mutation):
    report, kwargs = fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "timestamp": events[1]["timestamp"] = (kwargs["now"] + timedelta(hours=1)).isoformat()
    elif mutation == "boundary-type": events[0]["type"] = "acceptance_check"
    elif mutation == "boundary-check": events[0]["check"] = "upgrade"
    elif mutation == "boundary-proof": events[0]["evidence"] = {"proof.json": "0" * 64}
    elif mutation == "boundary-time": events[0]["timestamp"] = report["ended_at"]
    elif mutation == "event-type": events[1]["type"] = "display_message"
    elif mutation == "event-status": events[1]["status"] = "SKIP"
    elif mutation == "empty-proof": events[1]["evidence"] = {}
    elif mutation == "changed-proof": (tmp_path / "proof.json").write_bytes(b"changed")
    elif mutation == "directory-proof":
        (tmp_path / "proof.json").unlink()
        (tmp_path / "proof.json").mkdir()
    else: events[1]["unexpected"] = True
    path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report["events_sha256"] = kwargs["trusted_session"]["events_sha256"] = digest
    with pytest.raises(ValueError): acceptance.validate_live_acceptance(report, **kwargs)
