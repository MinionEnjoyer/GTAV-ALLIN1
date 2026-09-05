"""Machine-readable release qualification dashboard."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from allin1.health import inspect_windows_binary, sha256_file
from allin1.release_paths import no_links, strict_json
from allin1.release_acceptance import validate_live_acceptance


@dataclass(frozen=True)
class QualificationCheck:
    name: str
    passed: bool
    detail: str
    required: bool = True


def build_report(output: Path, checks: list[QualificationCheck], *,
                 metrics: dict[str, object] | None = None) -> dict:
    if len({check.name for check in checks}) != len(checks): raise ValueError("Duplicate qualification check")
    passed = bool(checks) and all(check.passed for check in checks if check.required)
    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "release_ready": False,
        "scope": "artifact dashboard; automated test and complete release qualification evidence is separate",
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
    if not math.isfinite(value) or value < 0.0 or value > 100.0:
        raise ValueError(f"coverage percentage is outside 0-100: {value}")
    return value


def verify_smoke_artifact(path: Path, *, context: dict | None = None) -> tuple[bool, str]:
    """Require a complete acceptance session pinned by an independent authority."""
    try:
        payload = strict_json(no_links(path).read_bytes())
    except (OSError, ValueError) as exc:
        return False, f"unreadable smoke artifact: {exc}"
    if not isinstance(payload, dict) or payload.get("kind") != "live_acceptance":
        return False, "unsupported or legacy smoke schema; log analysis cannot qualify a release"
    if context is None: return False, "independent acceptance identity and session anchor required"
    try:
        result = validate_live_acceptance(payload, **context)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return False, f"acceptance verification failed: {exc}"
    return True, f"verified session {result['session_id']}"


def checks_from_artifacts(
    coverage_report: Path, script_assembly: Path, smoke_report: Path, *,
    minimum_coverage: float = 91.0,
    acceptance_context: dict | None = None,
) -> tuple[list[QualificationCheck], dict[str, object]]:
    """Build qualification checks from files produced by the real workflows."""
    if not math.isfinite(minimum_coverage) or minimum_coverage < 91: raise ValueError("Minimum release coverage cannot be below 91%")
    coverage = coverage_from_report(coverage_report)
    binary = inspect_windows_binary(script_assembly)
    smoke_ok, smoke_detail = verify_smoke_artifact(smoke_report, context=acceptance_context)
    if smoke_ok and acceptance_context["expected_identity"]["artifacts"].get("script/dist/ALLIN1.dll") != sha256_file(script_assembly):
        smoke_ok, smoke_detail = False, "Acceptance evidence does not bind the selected script assembly"
    checks = [
        QualificationCheck("python_coverage", coverage >= minimum_coverage,
                           f"{coverage:.2f}% / {minimum_coverage:.2f}%"),
        QualificationCheck("script_header", binary.valid,
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
