"""A green summary must never substitute for actual mapped assertions."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("react_harness", Path(__file__).resolve().parents[1] / "tools/react_release_harness.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)


@pytest.fixture
def evidence(tmp_path):
    desktop = tmp_path / "desktop"; (desktop / "src").mkdir(parents=True)
    test = desktop / "src/module.test.tsx"; test.write_text("test source")
    inventory = {"schema_version": 1, "modules": [{"module": "workflow", "test_file": "src/module.test.tsx", "test_title": "saves and reopens"}]}
    report = {"success": True, "startTime": 110, "numTotalTests": 1, "numPassedTests": 1,
              "numFailedTests": 0, "numPendingTests": 0, "numTodoTests": 0,
              "testResults": [{"name": str(test), "status": "passed", "message": "", "startTime": 120, "endTime": 190,
                "assertionResults": [{"title": "saves and reopens", "fullName": "workspace saves and reopens", "status": "passed", "failureMessages": []}]}]}
    return report, inventory, desktop


def test_actual_named_assertion_passes(evidence):
    result = harness.validate_react(*evidence, 100, 200)
    assert result["status"] == "PASS" and result["tests"] == 1
    assert len(result["modules"][0]["test_sha256"]) == 64


@pytest.mark.parametrize("case", ["empty", "counts", "skipped", "todo", "missing-count", "boolean-count", "stale", "future", "duplicate-file", "duplicate-assertion", "wrong-title", "failed-assertion", "suite-error", "unrelated-file", "outside-file"])
def test_rejects_incomplete_stale_or_unrelated_results(evidence, case):
    report, inventory, desktop = evidence
    suite = report["testResults"][0]
    row = suite["assertionResults"][0]
    if case == "empty": report["testResults"] = []
    elif case == "counts": report.update(numTotalTests=2, numPassedTests=2)
    elif case == "skipped": report["numPendingTests"] = 1
    elif case == "todo": report["numTodoTests"] = 1
    elif case == "missing-count": del report["numFailedTests"]
    elif case == "boolean-count": report["numTotalTests"] = True
    elif case == "stale": report["startTime"] = 99
    elif case == "future": suite["endTime"] = 201
    elif case == "duplicate-file": report["testResults"].append(copy.deepcopy(suite))
    elif case == "duplicate-assertion": suite["assertionResults"].append(copy.deepcopy(row))
    elif case == "wrong-title": row["title"] = "opens a page"
    elif case == "failed-assertion": row["status"] = "failed"
    elif case == "suite-error": suite["message"] = "Unhandled rejection"
    elif case == "unrelated-file": suite["name"] = str(desktop / "missing.test.tsx")
    elif case == "outside-file":
        outside = desktop.parent / "other.test.tsx"; outside.write_text("unrelated")
        suite["name"] = str(outside)
    with pytest.raises(ValueError):
        harness.validate_react(report, inventory, desktop, 100, 200)


@pytest.mark.parametrize("case", ["empty", "duplicate", "schema", "traversal", "unknown", "missing-workflow"])
def test_inventory_fails_closed(evidence, case):
    report, inventory, desktop = evidence
    if case == "empty": inventory["modules"] = []
    elif case == "duplicate": inventory["modules"].append(copy.deepcopy(inventory["modules"][0]))
    elif case == "schema": inventory["schema_version"] = True
    elif case == "traversal": inventory["modules"][0]["test_file"] = "../outside.test.tsx"
    elif case == "unknown": inventory["modules"][0]["skip_allowed"] = True
    elif case == "missing-workflow": inventory["modules"].append({"module": "secondary-action", "test_file": "src/module.test.tsx", "test_title": "not implemented"})
    with pytest.raises(ValueError): harness.validate_react(report, inventory, desktop, 100, 200)


@pytest.mark.parametrize("body", ["", '<testcase><skipped/></testcase>', '<testcase><failure/></testcase>', '<testcase><error/></testcase>'])
def test_python_skips_are_not_passes(tmp_path, body):
    path = tmp_path / "report.xml"; path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>")
    with pytest.raises(ValueError): harness.validate_python(path)


def test_python_assertions_pass(tmp_path):
    path = tmp_path / "report.xml"; path.write_text('<testsuites><testsuite><testcase name="real check"/></testsuite></testsuites>')
    assert harness.validate_python(path) == {"status": "PASS", "tests": 1}


@pytest.fixture
def native_evidence(tmp_path):
    desktop = tmp_path / "desktop"
    binary = desktop / "src-tauri/target/debug/deps/test.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"synthetic, not executable")
    event = json.dumps({"reason": "compiler-artifact", "profile": {"test": True}, "executable": str(binary)})
    lines = [event, "test protocol::recovery ... ok", "test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;"]
    return desktop, binary, lines, tmp_path / "native.log"


def test_native_test_evidence_binds_binary(native_evidence):
    desktop, binary, lines, log = native_evidence
    log.write_text("\n".join(lines))
    result = harness.validate_native(log, desktop)
    assert result["tests"] == 1
    assert result["executables"] == {str(binary): harness.sha(binary)}


@pytest.mark.parametrize("case", ["no-binary", "missing-binary", "outside-binary", "no-summary", "counts", "ignored", "filtered", "failed", "no-rows", "duplicate"])
def test_native_empty_skipped_filtered_or_unbound_evidence_fails(native_evidence, case):
    desktop, binary, lines, log = native_evidence
    if case == "no-binary": lines[0] = ""
    elif case == "missing-binary": binary.unlink()
    elif case == "outside-binary":
        outside = desktop.parent / "outside.exe"; outside.write_bytes(b"unrelated")
        lines[0] = json.dumps({"reason": "compiler-artifact", "profile": {"test": True}, "executable": str(outside)})
    elif case == "no-summary": lines[2] = ""
    elif case == "counts": lines[2] = lines[2].replace("1 passed", "2 passed")
    elif case == "ignored": lines[2] = lines[2].replace("0 ignored", "1 ignored")
    elif case == "filtered": lines[2] = lines[2].replace("0 filtered", "1 filtered")
    elif case == "failed": lines[1] = lines[1].replace("ok", "FAILED")
    elif case == "no-rows": lines[1] = ""
    else:
        lines[1] += "\n" + lines[1]; lines[2] = lines[2].replace("1 passed", "2 passed")
    log.write_text("\n".join(lines))
    with pytest.raises(ValueError): harness.validate_native(log, desktop)


def test_source_inventory_rejects_dirty_git_dependencies(tmp_path, monkeypatch):
    dependency = tmp_path / "native-dependency"; dependency.mkdir()
    def git(command, **kwargs):
        if "ls-files" in command: return "native-dependency\0"
        if command[2] == str(dependency) and "status" in command: return " M source.cpp"
        if "rev-parse" in command: return "a" * 40
        return ""
    monkeypatch.setattr(harness.subprocess, "check_output", git)
    with pytest.raises(ValueError, match="uncommitted changes"):
        harness.source_identity(tmp_path)
