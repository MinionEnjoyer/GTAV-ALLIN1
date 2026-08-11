import json
from allin1.qualification import QualificationCheck, build_report


def test_qualification_required_and_optional_checks(tmp_path):
    output = tmp_path / "report.json"
    report = build_report(output, [QualificationCheck("tests", True, "passed"),
        QualificationCheck("smoke", False, "not run", required=False)], metrics={"coverage": 92.0})
    assert report["passed"] and report["summary"]["required_failed"] == 0
    assert json.loads(output.read_text())["metrics"]["coverage"] == 92.0
