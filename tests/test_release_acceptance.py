"""Synthetic contract tests are not live acceptance evidence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from allin1.release_acceptance import CHECKS, validate_live_acceptance


def fixture(tmp_path, suite="launcher-desktop"):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=2)).isoformat()
    end = (now - timedelta(minutes=1)).isoformat()
    (tmp_path / "sdk.exe").write_bytes(b"fixture SDK, not executable")
    (tmp_path / "renderer.dll").write_bytes(b"fixture renderer, not executable")
    (tmp_path / "proof.json").write_text('{"synthetic_test_only":true}')
    digest = lambda name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    identity = {"launcher_commit": "a" * 40, "build_id": "reviewed-build-fixture", "launcher_version": "1.2.3",
        "source_tree_sha256": "b" * 64, "artifacts": {"sdk.exe": digest("sdk.exe")},
        "dependencies": {"renderer.dll": digest("renderer.dll")}, "schema_versions": {"desktop": "1.0.0", "acceptance": "1"}}
    # Deliberately model a trusted authority only inside this unit fixture.
    report = {"schema_version": 1, "kind": "live_acceptance", "synthetic": False, "suite": suite,
        "session_id": "unit-fixture-session-1234", "target_edition": "Enhanced", "identity": identity,
        "started_at": start, "ended_at": end, "checks": {name: "PASS" for name in CHECKS[suite]},
        "events_path": "events.jsonl", "events_sha256": ""}
    events = []
    for sequence, check in enumerate([None, *sorted(CHECKS[suite]), None]):
        events.append({"schema_version": 1, "sequence": sequence, "session_id": report["session_id"],
            "timestamp": start if sequence == 0 else end, "type": "acceptance_check" if check else "session_start" if sequence == 0 else "session_end",
            "identity": identity, "target_edition": "Enhanced", "check": check, "status": "PASS",
            "evidence": {"proof.json": digest("proof.json")} if check else {}})
    (tmp_path / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    report["events_sha256"] = digest("events.jsonl")
    anchor = {key: deepcopy(report[key]) for key in ("schema_version", "session_id", "suite", "target_edition", "identity", "started_at", "ended_at", "events_sha256")}
    anchor["authority"] = "unit-test authority only"
    kwargs = dict(expected_identity=deepcopy(identity), trusted_session=anchor, evidence_root=tmp_path,
        artifact_root=tmp_path, dependency_root=tmp_path, target_edition="Enhanced", suite=suite, now=now)
    return report, kwargs


@pytest.mark.parametrize("suite", CHECKS)
def test_complete_versioned_event_contract_keeps_results_separate(tmp_path, suite):
    report, kwargs = fixture(tmp_path, suite)
    result = validate_live_acceptance(report, **kwargs)
    assert result["live_acceptance"] == "PASS"
    assert result["automated_tests"] == result["package_integrity"] == "NOT TESTED"


@pytest.mark.parametrize("field", ["schema_version", "kind", "suite", "session_id", "target_edition", "identity",
    "started_at", "ended_at", "checks", "events_path", "events_sha256", "synthetic"])
def test_every_acceptance_field_required(tmp_path, field):
    report, kwargs = fixture(tmp_path); del report[field]
    with pytest.raises(ValueError):
        validate_live_acceptance(report, **kwargs)


@pytest.mark.parametrize("mutation", ["missing-check", "skip", "failed", "old", "future", "synthetic", "schema", "session", "edition", "commit", "build", "schema-identity", "binary", "dependency", "no-proof", "log-only"])
def test_untrusted_incomplete_stale_or_unrelated_claims_fail(tmp_path, mutation):
    report, kwargs = fixture(tmp_path)
    if mutation == "missing-check": report["checks"].pop("upgrade")
    elif mutation == "skip": report["checks"]["upgrade"] = "SKIP"
    elif mutation == "failed": report["checks"]["upgrade"] = "FAIL"
    elif mutation == "old": kwargs["now"] += timedelta(days=8)
    elif mutation == "future": kwargs["now"] -= timedelta(days=1)
    elif mutation == "synthetic": report["synthetic"] = True
    elif mutation == "schema": report["schema_version"] = True
    elif mutation == "session": report["session_id"] = "different-session-123456"
    elif mutation == "edition": report["target_edition"] = "Legacy"
    elif mutation == "commit": report["identity"]["launcher_commit"] = "c" * 40
    elif mutation == "build": report["identity"]["build_id"] = "another build"
    elif mutation == "schema-identity": report["identity"]["schema_versions"]["desktop"] = "2.0.0"
    elif mutation == "binary": (tmp_path / "sdk.exe").write_bytes(b"MZ unrelated")
    elif mutation == "dependency": (tmp_path / "renderer.dll").write_bytes(b"MZ unrelated")
    elif mutation == "no-proof": (tmp_path / "proof.json").unlink()
    else:
        report = {"schema_version": 1, "source_log_sha256": report["events_sha256"], "status": "PASS"}
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_live_acceptance(report, **kwargs)


@pytest.mark.parametrize("mutation", ["old-event-version", "missing-boundary", "duplicate-check", "wrong-session", "wrong-edition", "wrong-artifact", "reordered", "outside-proof"])
def test_semantic_events_checked_even_when_log_hash_matches(tmp_path, mutation):
    report, kwargs = fixture(tmp_path)
    path = tmp_path / "events.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    if mutation == "old-event-version": events[1]["schema_version"] = 0
    elif mutation == "missing-boundary": events.pop()
    elif mutation == "duplicate-check": events[2]["check"] = events[1]["check"]
    elif mutation == "wrong-session": events[1]["session_id"] = "different-session-1234"
    elif mutation == "wrong-edition": events[1]["target_edition"] = "Legacy"
    elif mutation == "wrong-artifact": events[1]["identity"]["artifacts"]["sdk.exe"] = "0" * 64
    elif mutation == "reordered": events[1], events[2] = events[2], events[1]
    else: events[1]["evidence"] = {"../canary": "0" * 64}
    path.write_text("\n".join(json.dumps(event) for event in events))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report["events_sha256"] = kwargs["trusted_session"]["events_sha256"] = digest
    with pytest.raises(ValueError):
        validate_live_acceptance(report, **kwargs)
