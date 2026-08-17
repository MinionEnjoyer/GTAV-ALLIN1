"""Machine-readable release qualification dashboard."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from allin1.health import inspect_windows_binary, sha256_file


@dataclass(frozen=True)
class QualificationCheck:
    name: str
    passed: bool
    detail: str
    required: bool = True


def build_report(output: Path, checks: list[QualificationCheck], *,
                 metrics: dict[str, object] | None = None) -> dict:
    passed = all(check.passed for check in checks if check.required)
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "summary": {
            "passed": sum(check.passed for check in checks),
            "failed": sum(not check.passed for check in checks),
            "required_failed": sum(not check.passed and check.required for check in checks),
        },
        "metrics": metrics or {},
        "checks": [asdict(check) for check in checks],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def coverage_from_report(path: Path) -> float:
    """Read the measured total from a pytest-cov JSON artifact."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = float(payload["totals"]["percent_covered"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid coverage artifact: {path}") from exc
    if value < 0.0 or value > 100.0:
        raise ValueError(f"coverage percentage is outside 0-100: {value}")
    return value


def verify_smoke_artifact(path: Path) -> tuple[bool, str]:
    """Verify that a smoke report still matches its exact source game log."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"unreadable smoke artifact: {exc}"
    if payload.get("schema") != 2:
        return False, "unsupported or legacy smoke schema"
    if payload.get("passed") is not True or not payload.get("session"):
        return False, "smoke artifact did not pass a named game session"
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict) or check.get("passed") is not True for check in checks):
        return False, "one or more smoke checks did not pass"
    source_value = payload.get("source_log")
    expected_hash = payload.get("source_log_sha256")
    if not isinstance(source_value, str) or not isinstance(expected_hash, str):
        return False, "smoke artifact is missing source-log provenance"
    source = Path(source_value)
    if not source.is_file():
        return False, "source game log is no longer available"
    if sha256_file(source) != expected_hash.lower():
        return False, "source game log changed after smoke analysis"
    return True, f"verified session {payload['session']}"


def checks_from_artifacts(
    coverage_report: Path, script_assembly: Path, smoke_report: Path, *,
    minimum_coverage: float = 91.0,
) -> tuple[list[QualificationCheck], dict[str, object]]:
    """Build qualification checks from files produced by the real workflows."""
    coverage = coverage_from_report(coverage_report)
    binary = inspect_windows_binary(script_assembly)
    smoke_ok, smoke_detail = verify_smoke_artifact(smoke_report)
    checks = [
        QualificationCheck("python_coverage", coverage >= minimum_coverage,
                           f"{coverage:.2f}% / {minimum_coverage:.2f}%"),
        QualificationCheck("script_build", binary.valid,
                           f"{script_assembly}: {binary.reason}"),
        QualificationCheck("in_game_smoke", smoke_ok, smoke_detail),
    ]
    metrics = {
        "coverage": coverage,
        "coverage_report": str(coverage_report.resolve()),
        "script_assembly": str(script_assembly.resolve()),
        "script_sha256": sha256_file(script_assembly) if binary.valid else None,
        "smoke_report": str(smoke_report.resolve()),
        "smoke_report_sha256": sha256_file(smoke_report) if smoke_report.is_file() else None,
    }
    return checks, metrics
