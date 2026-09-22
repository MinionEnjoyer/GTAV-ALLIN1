"""Off-game harness orchestration is tested with fake commands, never recursively."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_spec = importlib.util.spec_from_file_location(
    "hardening_harness", Path(__file__).resolve().parents[1] / "tools" / "hardening_harness.py",
)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


def test_scratch_name_is_bounded_and_isolated(tmp_path):
    short = harness.scratch_name(tmp_path, "12345678")
    long = harness.scratch_name(tmp_path, "x" * 32)
    assert len(short) == len(long) == 16
    assert short != long
    assert long == harness.scratch_name(tmp_path, "x" * 32)
    assert long != harness.scratch_name(tmp_path / "other", "x" * 32)


def fake_command(argv, cwd, output, name, env, *, code=0):
    log = output / f"{name}.log"
    log.write_text("synthetic\n", encoding="utf-8")
    return {"argv": argv, "cwd": str(cwd), "started_ms": 10, "ended_ms": 20,
            "returncode": code, "log": str(log), "log_sha256": harness.sha(log)}


def test_fresh_short_evidence_directory_and_no_overwrite(tmp_path, monkeypatch):
    dist = tmp_path / "script" / "dist"; dist.mkdir(parents=True)
    for name in ("ALLIN1.dll", "ALLIN1.ReactorBridge.plugin", "ALLIN1.ReactorBridge.contract.json"):
        (dist / name).write_bytes(b"fixture")
    monkeypatch.setattr(harness, "validate_reactor_bridge_pair_payloads", lambda *_args: None)
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "source_snapshot", lambda _root: {"sha256": "a", "files": {}})
    monkeypatch.setattr(harness, "generated_artifacts", lambda _root: {})
    monkeypatch.setattr(harness, "resolve_tool", lambda _value: None)
    monkeypatch.setattr(harness, "profile", lambda *_args, **_kwargs: ({}, {"synthetic": {"status": "PASS"}}))
    options = SimpleNamespace(run_id="fresh-run", real_tools=False, python="python", pnpm="pnpm", cargo="cargo", dotnet="dotnet", cmake="cmake", ctest="ctest")

    code, output, summary = harness.run(options)
    assert code == 0 and output == tmp_path / "build" / "hh" / "fresh-run"
    assert (output / "summary.json").is_file()
    assert summary["unrun"]["live_game"] == "NOT RUN"
    assert "--game-fixtures" in summary["unrun"]["game_fixtures"]
    with pytest.raises(FileExistsError):
        harness.run(options)


def test_source_drift_fails_even_when_every_fake_layer_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    snapshots = iter(({"sha256": "before", "files": {"src/x.py": "a"}}, {"sha256": "after", "files": {"src/x.py": "b"}}))
    monkeypatch.setattr(harness, "source_snapshot", lambda _root: next(snapshots))
    monkeypatch.setattr(harness, "generated_artifacts", lambda _root: {"script/dist/ALLIN1.dll": "artifact"})
    monkeypatch.setattr(harness, "resolve_tool", lambda _value: None)
    monkeypatch.setattr(harness, "profile", lambda *_args, **_kwargs: ({}, {"synthetic": {"status": "PASS"}}))
    options = SimpleNamespace(run_id="drift-run", real_tools=False, python="python", pnpm="pnpm", cargo="cargo", dotnet="dotnet", cmake="cmake", ctest="ctest")

    code, output, summary = harness.run(options)
    assert code == 1 and summary["layers"]["source-integrity"]["status"] == "FAIL"
    assert summary["generated_artifacts_before"] == summary["generated_artifacts_after"]
    assert (output / "summary.json").is_file()


def test_missing_tools_are_failures_and_do_not_prevent_other_layers(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    options = SimpleNamespace(real_tools=False)
    commands, layers = harness.profile(options, {name: None for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")}, tmp_path)
    assert commands == {}
    assert {"python", "react", "rust-native"}.issubset(layers)
    assert all(layers[name]["status"] == "FAIL" for name in ("python", "react", "rust-native"))


def test_command_failure_is_recorded_while_independent_layers_continue(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / "desktop").mkdir()
    tools = {name: f"{name}.exe" for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")}
    options = SimpleNamespace(real_tools=False)
    def runner(argv, cwd, output, name, env):
        return fake_command(argv, cwd, output, name, env, code=7 if name == "python" else 0)

    commands, layers = harness.profile(options, tools, tmp_path, runner)
    assert layers["python"]["status"] == "FAIL"
    assert "documentation" in commands and "retirement" in commands
    assert "rust-native" in commands


@pytest.mark.parametrize("include", [False, True])
def test_game_capture_scope_is_explicit_and_missing_opt_in_fixtures_remain_incomplete(tmp_path, include):
    def runner(argv, cwd, output, name, env):
        if name == "python":
            (output / "python.xml").write_text('<testsuite tests="1"><testcase name="capture"><skipped message="capture absent"/></testcase></testsuite>')
            (output / "coverage.json").write_text('{"totals":{"percent_covered":92}}')
        return fake_command(argv, cwd, output, name, env)
    tools = {name: None for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")}
    tools["python"] = "python"
    commands, layers = harness.profile(SimpleNamespace(real_tools=False, game_fixtures=include), tools, tmp_path, runner)
    selection = layers["python"]["selection"]
    assert ("game_fixtures" in selection["excluded"]) is not include
    assert commands["python"]["argv"][5] == selection["expression"]
    assert layers["python"]["status"] == "INCOMPLETE"


@pytest.mark.parametrize("payload", [b"{}", b'{"totals":{"percent_covered":90}}', b'{"totals":{"percent_covered":true}}'])
def test_missing_or_low_coverage_evidence_fails(tmp_path, payload):
    path = tmp_path / "coverage.json"; path.write_bytes(payload)
    with pytest.raises(ValueError):
        harness.validate_coverage(path)


def test_python_layer_retains_separate_junit_and_coverage_hashes(tmp_path):
    junit = tmp_path / "python.xml"
    junit.write_text('<testsuite tests="1"><testcase name="proof"/></testsuite>')
    coverage = tmp_path / "coverage.json"
    coverage.write_text('{"totals":{"percent_covered":91.5}}')
    evidence = {**harness.validate_python_hardening(junit),
                **harness.validate_coverage(coverage)}
    assert evidence["report_sha256"] == harness.sha(junit)
    assert evidence["coverage_report_sha256"] == harness.sha(coverage)
    assert evidence["report_sha256"] != evidence["coverage_report_sha256"]


@pytest.mark.parametrize("body", ["", "<testcase><skipped/></testcase>"])
def test_empty_or_skipped_python_evidence_is_not_a_pass(tmp_path, body):
    report = tmp_path / "python.xml"
    report.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    with pytest.raises(ValueError):
        harness.validate_python(report)


def test_skipped_python_evidence_is_recorded_as_incomplete(tmp_path):
    report = tmp_path / "python.xml"
    report.write_text('<testsuites><testsuite tests="1"><testcase name="optional" classname="tests.live"><skipped message="fixture unavailable"/></testcase></testsuite></testsuites>')
    result = harness.validate_python_hardening(report)
    assert result["status"] == "INCOMPLETE"
    assert result["skipped"] == [{"name": "optional", "classname": "tests.live", "reason": "fixture unavailable"}]


def test_incomplete_layer_returns_nonzero_without_calling_it_a_failure(tmp_path, monkeypatch):
    dist = tmp_path / "script" / "dist"; dist.mkdir(parents=True)
    for name in ("ALLIN1.dll", "ALLIN1.ReactorBridge.plugin", "ALLIN1.ReactorBridge.contract.json"):
        (dist / name).write_bytes(b"fixture")
    monkeypatch.setattr(harness, "validate_reactor_bridge_pair_payloads", lambda *_args: None)
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "source_snapshot", lambda _root: {"sha256": "a", "files": {}})
    monkeypatch.setattr(harness, "generated_artifacts", lambda _root: {})
    monkeypatch.setattr(harness, "resolve_tool", lambda _value: None)
    monkeypatch.setattr(harness, "profile", lambda *_args, **_kwargs: ({}, {"python": {"status": "INCOMPLETE", "skipped": [{"name": "optional"}]}}))
    options = SimpleNamespace(run_id="incomplete", real_tools=False, python="python", pnpm="pnpm", cargo="cargo", dotnet="dotnet", cmake="cmake", ctest="ctest")
    code, _output, summary = harness.run(options)
    assert code == 1 and summary["status"] == "INCOMPLETE"


@pytest.mark.parametrize("text", [
    "No tests were found!!!",
    '<testsuites><testsuite tests="0"/></testsuites>',
    '<testsuites><testsuite tests="1"><testcase name="policy"><failure/></testcase></testsuite></testsuites>',
])
def test_ctest_requires_a_nonempty_unskipped_passing_result(tmp_path, text):
    report = tmp_path / "ctest.xml"; report.write_text(text)
    with pytest.raises(ValueError):
        harness.validate_ctest(report)


def test_ctest_skip_is_incomplete_with_reason(tmp_path):
    report = tmp_path / "ctest.xml"
    report.write_text('<testsuites><testsuite tests="1"><testcase name="policy"><skipped message="disabled"/></testcase></testsuite></testsuites>')
    result = harness.validate_ctest(report)
    assert result["status"] == "INCOMPLETE" and result["skipped"][0]["reason"] == "disabled"


def test_ctest_passing_evidence_is_counted(tmp_path):
    report = tmp_path / "ctest.xml"; report.write_text('<testsuites><testsuite tests="1"><testcase name="policy"/></testsuite></testsuites>')
    assert harness.validate_ctest(report)["tests"] == 1


def test_source_snapshot_excludes_only_exact_generated_artifacts_and_records_submodule(tmp_path, monkeypatch):
    for name in ("config.toml", "script/dist/ALLIN1.dll", "script/dist/other.json"):
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(name)
    nested = tmp_path / "nested"; nested.mkdir()
    def git(argv, **kwargs):
        if "ls-files" in argv:
            return "config.toml\0script/dist/ALLIN1.dll\0script/dist/other.json\0nested\0"
        if "--show-toplevel" in argv:
            return str(nested)
        if "rev-parse" in argv:
            return "a" * 40
        if "status" in argv:
            return ""
        raise AssertionError(argv)
    monkeypatch.setattr(harness.subprocess, "check_output", git)
    result = harness.source_snapshot(tmp_path)
    assert "config.toml" in result["files"]
    assert "script/dist/ALLIN1.dll" not in result["files"]
    assert "script/dist/other.json" in result["files"]
    assert result["files"]["nested"] == {"head": "a" * 40, "dirty": False}


def test_source_snapshot_ignores_generated_artifact_status_but_not_source_status(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"; path.write_text("source")
    def git(argv, **kwargs):
        if "ls-files" in argv:
            return "config.toml\0"
        if "status" in argv:
            return " M script/dist/ALLIN1.dll\0"
        if "rev-parse" in argv:
            return "a" * 40
        raise AssertionError(argv)
    monkeypatch.setattr(harness.subprocess, "check_output", git)
    assert harness.source_snapshot(tmp_path)["dirty"] is False

    def source_git(argv, **kwargs):
        if "status" in argv:
            return " M config.toml\0"
        return git(argv, **kwargs)
    monkeypatch.setattr(harness.subprocess, "check_output", source_git)
    assert harness.source_snapshot(tmp_path)["dirty"] is True


def test_trx_reconciles_summary_and_duplicate_test_identity(tmp_path):
    path = tmp_path / "results.trx"
    def document(rows, **counts):
        counters = " ".join(f'{name}="{value}"' for name, value in counts.items())
        path.write_text(f'<TestRun><Results>{rows}</Results><ResultSummary><Counters {counters}/></ResultSummary></TestRun>')
    document('<UnitTestResult testId="one" outcome="Passed"/>', total=1, executed=1, passed=1, failed=1, error=0)
    with pytest.raises(ValueError, match="summary"):
        harness.validate_trx(path)
    document('<UnitTestResult testId="one" outcome="Passed"/><UnitTestResult testId="one" outcome="Passed"/>', total=2, executed=2, passed=2, failed=0, error=0)
    with pytest.raises(ValueError, match="duplicate"):
        harness.validate_trx(path)


def test_key_context_requires_one_positive_runner_count(tmp_path):
    report = tmp_path / "key.log"; report.write_text("17 game-key context, bounded-I/O and stored-fingerprint checks passed.\n")
    assert harness.validate_key_context(report)["tests"] == 17
    report.write_text("0 game-key context, bounded-I/O and stored-fingerprint checks passed.\n")
    with pytest.raises(ValueError):
        harness.validate_key_context(report)


def test_python_profile_uses_short_unique_basetemp_and_coverage_file(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / "desktop").mkdir()
    (tmp_path / "evidence").mkdir()
    commands, _layers = harness.profile(SimpleNamespace(real_tools=False),
        {name: f"{name}.exe" for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")},
        tmp_path / "evidence", lambda argv, cwd, output, name, env: fake_command(argv, cwd, output, name, env), tmp_path / "scratch")
    python = commands["python"]
    assert "--basetemp" in python["argv"]
    assert str(tmp_path / "scratch" / "python") in python["argv"]


def test_tool_hash_error_makes_an_otherwise_passing_run_fail(tmp_path, monkeypatch):
    dist = tmp_path / "script" / "dist"; dist.mkdir(parents=True)
    for name in ("ALLIN1.dll", "ALLIN1.ReactorBridge.plugin", "ALLIN1.ReactorBridge.contract.json"):
        (dist / name).write_bytes(b"fixture")
    tool = tmp_path / "prepared-tool.exe"; tool.write_bytes(b"tool")
    real_sha = harness.sha
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "source_snapshot", lambda _root: {"sha256": "same", "files": {}})
    monkeypatch.setattr(harness, "generated_artifacts", lambda _root: {})
    monkeypatch.setattr(harness, "validate_reactor_bridge_pair_payloads", lambda *_args: None)
    monkeypatch.setattr(harness, "resolve_tool", lambda _value: str(tool))
    monkeypatch.setattr(harness, "profile", lambda *_args, **_kwargs: ({}, {"checks": {"status": "PASS"}}))
    monkeypatch.setattr(harness, "sha", lambda path: (_ for _ in ()).throw(OSError("unreadable tool"))
                        if Path(path) == tool else real_sha(path))
    options = SimpleNamespace(run_id="tool-hash", real_tools=False, python="python", pnpm="pnpm", cargo="cargo", dotnet="dotnet", cmake="cmake", ctest="ctest")
    code, _output, summary = harness.run(options)
    assert code == 1 and summary["status"] == "FAIL"
    assert summary["layers"]["tool-integrity"]["status"] == "FAIL"


@pytest.mark.parametrize("state", ["absent", "corrupt"])
def test_generated_pair_absence_or_corruption_is_not_a_passing_run(tmp_path, monkeypatch, state):
    monkeypatch.setattr(harness, "IS_WINDOWS", True)
    if state == "corrupt":
        dist = tmp_path / "script" / "dist"; dist.mkdir(parents=True)
        for name in ("ALLIN1.dll", "ALLIN1.ReactorBridge.plugin", "ALLIN1.ReactorBridge.contract.json"):
            (dist / name).write_bytes(b"corrupt")
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "source_snapshot", lambda _root: {"sha256": "same", "files": {}})
    monkeypatch.setattr(harness, "resolve_tool", lambda _value: None)
    monkeypatch.setattr(harness, "profile", lambda *_args, **_kwargs: ({}, {"checks": {"status": "PASS"}}))
    options = SimpleNamespace(run_id=f"pair-{state}", real_tools=False, python="python", pnpm="pnpm", cargo="cargo", dotnet="dotnet", cmake="cmake", ctest="ctest")
    code, _output, summary = harness.run(options)
    assert code == 1 and summary["layers"]["generated-artifacts"]["status"] == "FAIL"


def test_executor_exception_keeps_independent_harness_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / "desktop").mkdir()
    tools = {name: f"{name}.exe" for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")}
    def runner(argv, cwd, output, name, env):
        if name == "python":
            raise OSError("broken child process")
        return fake_command(argv, cwd, output, name, env, code=1)
    commands, layers = harness.profile(SimpleNamespace(real_tools=False), tools, tmp_path, runner)
    assert layers["python"]["status"] == "FAIL" and "broken child process" in layers["python"]["reason"]
    assert {"documentation", "retirement", "rust-native"}.issubset(commands)


def test_profile_records_real_tool_and_rust_source_only_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "IS_WINDOWS", True)
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    (tmp_path / "desktop").mkdir()
    tools = {name: f"{name}.exe" for name in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest")}
    seen = {}
    def runner(argv, cwd, output, name, env):
        seen[name] = dict(env)
        return fake_command(argv, cwd, output, name, env, code=1)
    commands, _layers = harness.profile(SimpleNamespace(real_tools=True), tools, tmp_path, runner)
    assert seen["windows-integration"]["ALLIN1_RUN_TOOL_INTEGRATION"] == "1"
    assert seen["rust-native"]["TAURI_CONFIG"] == '{"bundle": {"active": false, "resources": []}}'
    assert commands["rust-native"]["configuration_override"] == {"bundle": {"active": False, "resources": []}}


@pytest.mark.parametrize(("document", "match"), [
    ('<testsuite tests="2"><testcase name="same"/><testcase name="same"/></testsuite>', "duplicate"),
    ('<testsuite tests="2"><testcase name="one"/></testsuite>', "counts"),
])
def test_ctest_rejects_duplicate_or_mismatched_root_testsuite(tmp_path, document, match):
    report = tmp_path / "ctest.xml"; report.write_text(document)
    with pytest.raises(ValueError, match=match):
        harness.validate_ctest(report)
    report.write_text('<testsuite tests="1"><testcase name="root-policy"/></testsuite>')
    assert harness.validate_ctest(report)["status"] == "PASS"


@pytest.mark.parametrize(("validator", "name"), [(harness.validate_python_hardening, "python"), (harness.validate_ctest, "ctest")])
def test_junit_rejects_claimed_failure_without_failure_case(tmp_path, validator, name):
    report = tmp_path / f"{name}.xml"
    report.write_text('<testsuite tests="1" failures="1"><testcase name="only" classname="suite"/></testsuite>')
    with pytest.raises(ValueError, match="summary"):
        validator(report)
