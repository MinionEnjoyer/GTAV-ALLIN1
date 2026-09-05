"""Run fresh React migration checks; never certify a release or delete Tkinter.

This developer harness can explicitly test a sibling SDK checkout. Neither
application acquires a runtime dependency on this script or the other checkout.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allin1.release_paths import contained, no_links, strict_json


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def write_new(path, value):
    with no_links(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def source_identity(root):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8", timeout=60).strip()
    inputs = {}
    for name in sorted(set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0"))):
        if not name or name.startswith(("build/", ".work/")):
            continue
        path = contained(root, name)
        if path.is_file(): inputs[name] = sha(path)
        elif path.is_dir():
            dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True, timeout=30).strip()
            if dirty:
                raise ValueError(f"Build dependency has uncommitted changes: {name}")
            inputs[name] = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True, timeout=30).strip()
        else: inputs[name] = None
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "inputs": inputs, "sha256": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()}


def validate_react(report, inventory, desktop, started_ms, ended_ms):
    """Validate actual assertions, not a success flag or human log message."""
    if type(inventory.get("schema_version")) is not int or inventory["schema_version"] != 1:
        raise ValueError("Unknown module inventory schema")
    modules = inventory.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("Empty module inventory")
    counts = ("numTotalTests", "numPassedTests", "numFailedTests", "numPendingTests", "numTodoTests")
    if any(type(report.get(key)) is not int or report[key] < 0 for key in counts):
        raise ValueError("Missing or invalid structured test counts")
    if report.get("success") is not True or not report["numTotalTests"]:
        raise ValueError("React run did not succeed")
    if report["numTotalTests"] != report["numPassedTests"] or any(report[key] for key in counts[2:]):
        raise ValueError("Failed, skipped, pending or todo React checks")
    if type(report.get("startTime")) not in (int, float) or not started_ms <= report["startTime"] <= ended_ms:
        raise ValueError("Report is not from this invocation")
    rows = []
    suites = report.get("testResults")
    if not isinstance(suites, list) or not suites:
        raise ValueError("Missing actual test evidence")
    suite_paths = set()
    for suite in suites:
        path = no_links(Path(suite["name"]).absolute())
        if not path.is_relative_to(desktop) or not path.is_file() or path in suite_paths:
            raise ValueError("Unrelated or duplicate test file")
        suite_paths.add(path)
        if suite.get("status") != "passed" or suite.get("message"):
            raise ValueError("Unsuccessful test suite")
        if not started_ms <= suite["startTime"] <= suite["endTime"] <= ended_ms:
            raise ValueError("Stale or inconsistent test session")
        seen = set()
        for assertion in suite["assertionResults"]:
            if assertion.get("status") != "passed" or assertion.get("failureMessages"):
                raise ValueError("Non-passing assertion")
            full_name = assertion["fullName"]
            if not isinstance(full_name, str) or not full_name or full_name in seen:
                raise ValueError("Ambiguous assertion identity")
            seen.add(full_name)
            rows.append((path, assertion))
    if len(rows) != report["numTotalTests"]:
        raise ValueError("Summary counts disagree with actual assertions")
    mapped, names = [], set()
    for module in modules:
        if set(module) - {"module", "test_file", "test_title", "native"}:
            raise ValueError("Unknown inventory fields")
        name = module["module"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Duplicate or empty module identity")
        names.add(name)
        expected = contained(desktop, module["test_file"])
        matches = [row for path, row in rows if path == expected and row["title"] == module["test_title"]]
        if len(matches) != 1:
            raise ValueError(f"Missing or ambiguous happy path: {name}")
        mapped.append({**module, "status": "PASS", "full_name": matches[0]["fullName"], "test_sha256": sha(expected)})
    return {"status": "PASS", "tests": len(rows), "files": len(suites), "modules": mapped}


def validate_python(path):
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases or any(case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")):
        raise ValueError("Python evidence is empty, failed or skipped")
    return {"status": "PASS", "tests": len(cases)}


def validate_native(log_path, desktop):
    """Bind Cargo's test executables and reconcile every libtest result.

    Stable Rust does not expose libtest JSON. Cargo's compiler-artifact events
    are structured; the bounded adapter below rejects ignored/filtered tests or
    unknown/missing summaries instead of treating Cargo exit zero as acceptance.
    """
    text = log_path.read_text(encoding="utf-8")
    binaries = {}
    for line in text.splitlines():
        if not line.startswith('{'): continue
        event = strict_json(line)
        if event.get("reason") == "compiler-artifact" and event.get("profile", {}).get("test") and event.get("executable"):
            path = no_links(Path(event["executable"]))
            if not path.is_relative_to(desktop / "src-tauri/target") or not path.is_file():
                raise ValueError("Unrelated or missing native test executable")
            binaries[str(path)] = sha(path)
    summaries = re.findall(r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;", text, re.MULTILINE)
    rows = re.findall(r"^test (\S+) \.\.\. (ok|FAILED|ignored)\s*$", text, re.MULTILINE)
    if not binaries or not summaries or not rows:
        raise ValueError("Missing native binary or test evidence")
    if any(status != "ok" or any(int(n) for n in rest) for status, _passed, *rest in summaries):
        raise ValueError("Native tests failed, skipped, ignored or filtered")
    if any(status != "ok" for _name, status in rows) or sum(int(row[1]) for row in summaries) != len(rows):
        raise ValueError("Native summaries disagree with actual test outcomes")
    if len({name for name, _ in rows}) != len(rows):
        raise ValueError("Ambiguous native test identity")
    return {"status": "PASS", "tests": len(rows), "test_names": [name for name, _ in rows],
            "executables": binaries, "log_sha256": sha(log_path), "scope": "native unit/process tests; not packaged GUI acceptance"}


def run_command(command, cwd, folder, name, env):
    start = time.time_ns() // 1_000_000
    log = folder / (name + ".log")
    print(f"[{folder.name}] {name}", flush=True)
    with log.open("xb") as stream:
        try:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            stream.write(str(error).encode("utf-8")); code = -1
    return {"argv": command, "cwd": str(cwd), "started_ms": start,
            "ended_ms": time.time_ns() // 1_000_000, "returncode": code,
            "log": str(log), "log_sha256": sha(log)}


def run_product(name, root, output, pnpm, python, full_python, cargo):
    desktop = no_links(root / "desktop")
    folder = output / name; folder.mkdir()
    before = source_identity(root)
    write_new(folder / "source-before.json", before)
    env = dict(os.environ, ALLIN1_TEST_PYTHON=python, ALLIN1_SDK_TEST_PYTHON=python)
    if name == "sdk":
        env.update(ALLIN1_NATIVE_RPF_TEST="1", ALLIN1_NATIVE_RUNTIME_TEST="1")
        env.setdefault("ALLIN1_BLENDER_EXECUTABLE", str(root / "build/dependencies/blender-4.5.13-windows-x64/blender.exe"))
    report_path = folder / "vitest.json"
    frontend_build = run_command([pnpm, "build"], desktop, folder, "frontend-build", env)
    react_command = run_command([pnpm, "test", "--reporter=json", f"--outputFile={report_path}"], desktop, folder, "react", env)
    result = {"source": {"commit": before["commit"], "dirty": before["dirty"], "sha256": before["sha256"]}, "commands": {"react": react_command}}
    result["commands"]["frontend_build"] = frontend_build
    result["frontend_build"] = {"status": "PASS" if frontend_build["returncode"] == 0 else "FAIL", "scope": "TypeScript and production frontend build"}
    try:
        if react_command["returncode"] != 0: raise ValueError("React command failed; inspect react.log")
        result["react"] = validate_react(strict_json(report_path.read_bytes()), strict_json((desktop / "module-happy-paths.json").read_bytes()), desktop, react_command["started_ms"], react_command["ended_ms"])
        result["react"]["report_sha256"] = sha(report_path)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result["react"] = {"status": "FAIL", "reason": str(error)}
    tests = (["tests/test_documentation.py", "tests/test_react_release_harness.py", "tests/test_desktop_host.py", "tests/test_desktop_service.py",
              "tests/test_preference_migration.py", "tests/test_desktop_content.py", "tests/test_desktop_packages.py", "tests/test_desktop_assistant.py",
              "tests/test_desktop_activity.py", "tests/test_desktop_character_drafts.py", "tests/test_desktop_launch.py", "tests/test_launcher_react_handoff.py",
              "tests/test_installer_transactions.py", "tests/test_installer_preservation.py", "tests/test_detector.py", "tests/test_manager.py", "tests/test_assistant_containment.py", "tests/test_assistant_manager.py",
              "tests/test_launcher_desktop_candidate.py", "tests/test_updater_containment.py", "tests/test_sdk_tauri_installation.py", "tests/test_release_acceptance.py"]
             if name == "launcher" else ["tests/test_desktop_documentation.py", "tests/test_release_notes.py", "tests/test_extension_contract_parity.py", "tests/test_desktop_no_tk.py", "tests/test_desktop_protocol.py", "tests/test_release_package.py", "tests/test_standalone_sdk.py", "tests/test_desktop_candidate.py", "tests/test_candidate_test_evidence.py", "tests/test_frozen_desktop.py", "tests/test_launcher_bridge.py"])
    xml = folder / "python.xml"
    tests.append("tests/test_tk_retirement.py")
    command = [python, "-m", "pytest", *( ["tests", f"--cov={'allin1' if name == 'launcher' else 'allin1_sdk'}", f"--cov-report=json:{folder / 'coverage.json'}"] if full_python else tests), "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"]
    executed = run_command(command, root, folder, "python", env)
    result["commands"]["python"] = executed
    try:
        if executed["returncode"] != 0: raise ValueError("Python command/coverage gate failed; inspect python.log")
        result["python"] = validate_python(xml)
        result["python"]["report_sha256"] = sha(xml)
    except (ValueError, OSError, ET.ParseError) as error:
        result["python"] = {"status": "FAIL", "reason": str(error)}
    result["python"]["scope"] = "full suite with unchanged coverage threshold" if full_python else "targeted migration/security checks; not the full coverage gate"
    # Native unit compilation must not silently consume a stale frozen sidecar
    # or release resource staging directory. Packaging has its own full gates.
    native_env = dict(env, TAURI_CONFIG=json.dumps({"bundle": {"active": False, "resources": []}}))
    native = run_command([cargo, "test", "--locked", "--manifest-path", str(desktop / "src-tauri/Cargo.toml"), "--message-format=json", "--", "--format=pretty"], root, folder, "native", native_env)
    native["configuration_override"] = json.loads(native_env["TAURI_CONFIG"])
    result["commands"]["native"] = native
    try:
        if native["returncode"] != 0: raise ValueError("Native command failed; inspect native.log")
        result["native"] = validate_native(folder / "native.log", desktop)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result["native"] = {"status": "FAIL", "reason": str(error)}
    documentation = run_command([python, str(ROOT / "tools/documentation_audit.py"), "--product", name, *(["--sdk-source", str(root)] if name == "sdk" else [])], root, folder, "documentation", env)
    result["commands"]["documentation"] = documentation
    result["documentation"] = {"status": "PASS" if documentation["returncode"] == 0 else "FAIL"}
    after = source_identity(root)
    write_new(folder / "source-after.json", after)
    result["source_unchanged"] = before == after
    result["dependency_identities"] = {name: {"version": strict_json((desktop / "node_modules" / name / "package.json").read_bytes())["version"], "package_json_sha256": sha(desktop / "node_modules" / name / "package.json")} for name in ("vitest", "vite", "react", "react-dom", "typescript")}
    result["automated_checks"] = "PASS" if result["source_unchanged"] and all(result[key]["status"] == "PASS" for key in ("frontend_build", "react", "python", "native", "documentation")) else "FAIL"
    result.update(package_integrity="NOT TESTED", native_installer_lifecycle="NOT TESTED", live_acceptance="NOT TESTED", release_ready=False)
    # Source retirement is measurable independently of packaged/live acceptance.
    retirement = run_command([python, str(root / ("tools" if name == "launcher" else "scripts") / "tk_retirement.py")], root, folder, "tk-retirement", env)
    result["commands"]["tkinter_retirement"] = retirement
    result["tkinter_retirement"] = {"status": "PASS" if retirement["returncode"] == 0 else "FAIL", "scope": "source and GUI/build entrypoints; not packaged/live qualification"}
    if retirement["returncode"] != 0:
        result["automated_checks"] = "FAIL"
    write_new(folder / "result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", choices=("launcher", "sdk", "both"), default="launcher")
    parser.add_argument("--sdk-source", type=Path)
    parser.add_argument("--pnpm", default="pnpm")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--full-python", action="store_true", help="Run full Python suites with existing coverage thresholds; skips still fail this harness.")
    parser.add_argument("--require-retirement-ready", action="store_true", help="Require source-retirement checks as well as automated gates. Does not qualify packaged/live acceptance or delete files.")
    options = parser.parse_args()
    if options.product != "launcher" and options.sdk_source is None:
        parser.error("SDK checks require an explicit --sdk-source checkout")
    pnpm, python, cargo = shutil.which(options.pnpm), shutil.which(options.python), shutil.which(options.cargo)
    if not pnpm or not python or not cargo: parser.error("Python, pnpm and Cargo must be installed and resolvable")
    run_id = uuid.uuid4().hex
    output = no_links(ROOT / "build/react-harness" / run_id)
    output.mkdir(parents=True, exist_ok=False)
    node = shutil.which("node")
    if not node: parser.error("Node must be on PATH")
    report = {"schema_version": 1, "kind": "react_migration_test_run", "run_id": run_id,
              "created_at": datetime.now(timezone.utc).isoformat(), "release_ready": False,
              "tools": {name: {"path": path, "sha256": sha(Path(path))} for name, path in (("python", python), ("pnpm", pnpm), ("node", node), ("cargo", cargo))},
              "scope": "SDK/Launcher only, including generic package and weapon integration. Suppressors Enhanced, weapon pack bundle, GTA VR and FPV are independent projects with separate release gates.", "products": {}}
    for name in (("launcher", "sdk") if options.product == "both" else (options.product,)):
        root = ROOT if name == "launcher" else no_links(options.sdk_source.absolute())
        report["products"][name] = run_product(name, root, output, pnpm, python, options.full_python, cargo)
    write_new(output / "report.json", report)
    retired = all(value["tkinter_retirement"]["status"] == "PASS" for value in report["products"].values())
    print(json.dumps({"report": str(output / "report.json"), "sha256": sha(output / "report.json"), "results": {name: value["automated_checks"] for name, value in report["products"].items()}, "tkinter_retirement": "PASS" if retired else "FAIL", "release_ready": False}), flush=True)
    return 0 if all(value["automated_checks"] == "PASS" for value in report["products"].values()) and (not options.require_retirement_ready or retired) else 1


if __name__ == "__main__":
    raise SystemExit(main())
