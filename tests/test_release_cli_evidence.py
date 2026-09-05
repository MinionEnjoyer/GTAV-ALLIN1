"""CLI qualification must retain strict evidence and coverage requirements."""
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from allin1 import cli, qualification
from tests.test_cli import _project, _write_pe
from tests.test_release_acceptance import fixture


@pytest.mark.parametrize("mutation", ["none", "missing", "relative", "wrong-suite", "invalid-json", "low-floor"])
def test_qualification_cli_does_not_turn_incomplete_evidence_into_ready(tmp_path, monkeypatch, mutation):
    _project(tmp_path, monkeypatch)
    report, context = fixture(tmp_path)
    context.pop("now")
    context = {key: str(value) if isinstance(value, Path) else value for key, value in context.items()}
    if mutation == "missing": context.pop("trusted_session")
    elif mutation == "relative": context["artifact_root"] = "relative"
    elif mutation == "wrong-suite": context["suite"] = "reactor-story"
    context_file = tmp_path / "context.json"
    context_file.write_text("{" if mutation == "invalid-json" else json.dumps(context), encoding="utf-8")
    smoke = tmp_path / "acceptance.json"
    smoke.write_text(json.dumps(report), encoding="utf-8")
    coverage = tmp_path / "coverage.json"
    coverage.write_text('{"totals":{"percent_covered":95}}', encoding="utf-8")
    assembly = tmp_path / "unrelated.dll"
    _write_pe(assembly)
    output = tmp_path / "qualification.json"
    args = ["qualification-report", str(output), "--coverage-report", str(coverage),
        "--script-assembly", str(assembly), "--smoke-report", str(smoke), "--acceptance-context", str(context_file)]
    if mutation == "low-floor": args.extend(["--minimum-coverage", "90"])
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code != 0
    if mutation == "none":
        stored = json.loads(output.read_bytes())
        assert stored["release_ready"] is False and stored["passed"] is False
        check = next(c for c in stored["checks"] if c["name"] == "in_game_smoke")
        assert not check["passed"] and "selected script assembly" in check["detail"]
    else: assert not output.exists()


def test_smoke_verification_reads_proof_not_just_valid_report(tmp_path):
    report, context = fixture(tmp_path)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert qualification.verify_smoke_artifact(path, context=context)[0]
    (tmp_path / "proof.json").write_bytes(b"changed after acceptance")
    assert not qualification.verify_smoke_artifact(path, context=context)[0]
    path.write_bytes(b"{")
    assert not qualification.verify_smoke_artifact(path, context=context)[0]


@pytest.mark.parametrize("kind", ["weapon", "equipment"])
def test_preview_import_cli_reports_rejected_unknown_content(tmp_path, monkeypatch, kind):
    _project(tmp_path, monkeypatch)
    source = tmp_path / "previews"
    source.mkdir()
    (source / "unknown.png").write_bytes(b"not a valid preview")
    result = CliRunner().invoke(cli.main, ["import-previews", str(source), "--kind", kind])
    assert result.exit_code == 0, result.output
    assert "Rejected 1" in result.output and "Imported 0" in result.output
