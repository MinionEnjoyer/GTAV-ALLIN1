"""Machine-readable release qualification dashboard."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


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
