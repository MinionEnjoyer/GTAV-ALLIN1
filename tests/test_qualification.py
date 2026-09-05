import hashlib
import json
import struct

import pytest

from allin1.qualification import (
    QualificationCheck, build_report, checks_from_artifacts, verify_smoke_artifact,
)


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def test_qualification_required_and_optional_checks(tmp_path):
    output = tmp_path / "report.json"
    report = build_report(output, [QualificationCheck("tests", True, "passed"),
        QualificationCheck("smoke", False, "not run", required=False)], metrics={"coverage": 92.0})
    assert report["passed"] and report["summary"]["required_failed"] == 0
    assert json.loads(output.read_text())["metrics"]["coverage"] == 92.0


def test_qualification_is_derived_from_verifiable_artifacts(tmp_path):
    coverage = tmp_path / "coverage.json"
    coverage.write_text(json.dumps({"totals": {"percent_covered": 92.5}}))
    assembly = tmp_path / "ALLIN1.dll"
    _write_pe(assembly)
    source_log = tmp_path / "client.log"
    source_log.write_text("exact session bytes")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({
        "schema": 2, "passed": True, "session": "session-1",
        "source_log": str(source_log.resolve()),
        "source_log_sha256": hashlib.sha256(source_log.read_bytes()).hexdigest(),
        "checks": [{"name": "session_integrity", "passed": True, "detail": "fresh"}],
    }))

    checks, metrics = checks_from_artifacts(coverage, assembly, smoke)

    assert checks[0].passed and checks[1].passed
    assert not checks[2].passed  # A matching log hash is not release acceptance.
    assert metrics["coverage"] == 92.5
    assert metrics["script_sha256"] == hashlib.sha256(assembly.read_bytes()).hexdigest()


def test_smoke_artifact_fails_when_source_log_changes(tmp_path):
    source_log = tmp_path / "client.log"
    source_log.write_text("original")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({
        "schema": 2, "passed": True, "session": "session-1",
        "source_log": str(source_log.resolve()),
        "source_log_sha256": hashlib.sha256(source_log.read_bytes()).hexdigest(),
        "checks": [{"name": "session_integrity", "passed": True}],
    }))
    source_log.write_text("changed")

    valid, detail = verify_smoke_artifact(smoke)

    assert valid is False
    assert "legacy smoke schema" in detail


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"schema": 1}, "unsupported"),
        ({"schema": 2, "passed": False, "session": "run"}, "legacy"),
        ({"schema": 2, "passed": True, "session": "run", "checks": []},
         "legacy"),
        ({"schema": 2, "passed": True, "session": "run",
          "checks": [{"passed": True}]}, "legacy"),
    ],
)
def test_smoke_artifact_rejects_incomplete_evidence(tmp_path, payload, expected):
    artifact = tmp_path / "smoke.json"
    artifact.write_text(json.dumps(payload))

    valid, detail = verify_smoke_artifact(artifact)

    assert valid is False
    assert expected in detail


def test_smoke_artifact_rejects_missing_source_log(tmp_path):
    artifact = tmp_path / "smoke.json"
    artifact.write_text(json.dumps({
        "schema": 2,
        "passed": True,
        "session": "run",
        "checks": [{"passed": True}],
        "source_log": str(tmp_path / "missing.log"),
        "source_log_sha256": "0" * 64,
    }))

    valid, detail = verify_smoke_artifact(artifact)

    assert valid is False
    assert "legacy smoke schema" in detail


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -1, 101])
def test_coverage_requires_finite_bounded_percentage(tmp_path, number):
    from allin1.qualification import coverage_from_report
    report = tmp_path / "coverage.json"; report.write_text(json.dumps({"totals": {"percent_covered": number}}))
    with pytest.raises(ValueError): coverage_from_report(report)


def test_an_empty_or_partial_dashboard_never_implies_release_readiness(tmp_path):
    assert not build_report(tmp_path / "empty.json", [])["passed"]
    result = build_report(tmp_path / "header.json", [QualificationCheck("script_header", True, "PE signature")])
    assert result["passed"] and not result["release_ready"]


def test_smoke_artifact_rejects_unreadable_json(tmp_path):
    artifact = tmp_path / "smoke.json"
    artifact.write_text("not-json")

    valid, detail = verify_smoke_artifact(artifact)

    assert valid is False
    assert "unreadable" in detail
