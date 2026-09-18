"""Run reproducible off-game hardening checks and retain strict evidence.

This is deliberately not a release builder, installer, packager, or game
launcher.  It uses already-installed toolchains only and records the checks it
could not run instead of inferring success from a process exit code.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

# Direct ``python tools/hardening_harness.py`` puts tools/ rather than the
# checkout on sys.path. Keep the reusable validator import working for both
# that normal invocation and importlib-based harness tests.
ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.react_release_harness import sha, validate_native, validate_python, validate_react
from allin1.release_paths import no_links, strict_json
from allin1.reactor_bridge_contract import validate_reactor_bridge_pair_payloads

SOURCE_EXCLUDES = ("build/", ".work/", "output/", ".artifacts/", ".tmp", ".pytest_cache/", "htmlcov/")
GENERATED_ARTIFACTS = (
    "script/dist/ALLIN1.dll",
    "script/dist/ALLIN1.ReactorBridge.plugin",
    "script/dist/ALLIN1.ReactorBridge.contract.json",
)


def write_new(path: Path, value: object) -> None:
    with no_links(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def source_snapshot(root: Path) -> dict:
    """Hash tracked/source inputs while intentionally excluding generated DLLs."""
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=60).strip()
    names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split("\0")
    files: dict[str, object] = {}
    for name in sorted(set(names)):
        if not name or name.startswith(SOURCE_EXCLUDES) or name in GENERATED_ARTIFACTS:
            continue
        path = no_links(root / name)
        if path.is_file():
            files[name] = sha(path)
        elif path.is_dir():
            # A gitlink is source input too.  Preserve its exact HEAD and
            # dirtiness rather than treating an entire nested checkout as a
            # disposable generated directory.
            try:
                top = Path(subprocess.check_output(["git", "-C", str(path), "rev-parse", "--show-toplevel"], text=True, timeout=30).strip())
                if top.resolve() != path.resolve():
                    stage = git("ls-files", "--stage", "--", name)
                    fields = stage.split()
                    files[name] = {"gitlink": fields[1] if len(fields) >= 2 and fields[0] == "160000" else None,
                                   "head": None, "dirty": None}
                    continue
                head = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True, timeout=30).strip()
                dirty = bool(subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True, timeout=30).strip())
                if dirty:
                    raise ValueError(f"Build dependency has uncommitted changes: {name}")
                files[name] = {"head": head, "dirty": False}
            except (OSError, subprocess.CalledProcessError):
                files[name] = {"head": None, "dirty": None}
        else:
            files[name] = None
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")),
            "files": files, "sha256": hashlib.sha256(encoded).hexdigest()}


def generated_artifacts(root: Path) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for name in GENERATED_ARTIFACTS:
        path = no_links(root / name)
        values[name] = sha(path) if path.is_file() else None
    return values


def resolve_tool(value: str | None) -> str | None:
    if not value:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute() or candidate.parent != Path(".") or candidate.exists():
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        candidate = no_links(candidate)
        return str(candidate) if candidate.is_file() else None
    return shutil.which(value)


def run_command(argv: list[str], cwd: Path, output: Path, name: str, env: dict[str, str]) -> dict:
    started = time.time_ns() // 1_000_000
    log = no_links(output / f"{name}.log")
    with log.open("xb") as stream:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            code = result.returncode
        except (OSError, subprocess.TimeoutExpired) as error:
            stream.write((str(error) + "\n").encode("utf-8", "replace")); code = -1
    return {"argv": argv, "cwd": str(cwd), "started_ms": started, "ended_ms": time.time_ns() // 1_000_000,
            "returncode": code, "log": str(log), "log_sha256": sha(log)}


def failed(reason: str, *, skipped: bool = False) -> dict:
    return {"status": "SKIPPED" if skipped else "FAIL", "reason": reason}


def validate_coverage(path: Path) -> dict:
    value = strict_json(path.read_bytes()).get("totals", {}).get("percent_covered")
    if type(value) not in (int, float) or not 91 <= value <= 100:
        raise ValueError("Python coverage is missing or below the existing 91% threshold")
    # Keep the JUnit evidence hash when these fields are merged into the
    # Python layer; coverage.json is a separate report, not its replacement.
    return {"coverage": value, "coverage_report_sha256": sha(path)}


def validate_python_hardening(path: Path) -> dict:
    """Reject green-looking JUnit output that omitted required tests."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag.endswith("testsuite") else root.findall(".//testsuite")
    cases = root.findall(".//testcase")
    if not cases:
        raise ValueError("Python evidence has no test cases")
    identities = [(case.get("classname", ""), case.get("name", "")) for case in cases]
    if any(not name for _klass, name in identities) or len(set(identities)) != len(identities):
        raise ValueError("Python evidence has missing or duplicate test identities")
    if suites:
        declared = sum(int(suite.get("tests", "-1")) for suite in suites)
        if declared != len(cases):
            raise ValueError("Python JUnit suite counts do not reconcile with test cases")
        for attribute, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped")):
            for suite in suites:
                if attribute in suite.attrib and int(suite.attrib[attribute]) != sum(case.find(tag) is not None for case in suite.findall("testcase")):
                    raise ValueError(f"Python JUnit {attribute} summary does not reconcile with test cases")
    failed = [case for case in cases if any(case.find(tag) is not None for tag in ("failure", "error"))]
    if failed:
        raise ValueError("Python evidence includes failed tests")
    skipped = []
    for case in cases:
        node = case.find("skipped")
        if node is not None:
            skipped.append({"name": case.get("name", ""), "classname": case.get("classname", ""),
                            "reason": node.get("message") or (node.text or "").strip() or "no reason recorded"})
    result = {"tests": len(cases), "passed": len(cases) - len(skipped), "report_sha256": sha(path)}
    if skipped:
        return {"status": "INCOMPLETE", "skipped": skipped, **result}
    return {"status": "PASS", **result}


def validate_trx(path: Path) -> dict:
    root = ET.parse(path).getroot()
    rows = root.findall(".//{*}UnitTestResult")
    if not rows:
        raise ValueError("C# TRX has no tests")
    identifiers = [row.get("testId") for row in rows]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("C# TRX has missing or duplicate test identities")
    counters = root.find(".//{*}ResultSummary/{*}Counters")
    if counters is None:
        raise ValueError("C# TRX is missing ResultSummary counters")
    def count(name: str) -> int:
        value = counters.get(name)
        if value is None or not value.isdigit():
            raise ValueError(f"C# TRX counter is missing or invalid: {name}")
        return int(value)
    total, executed, passed = count("total"), count("executed"), count("passed")
    if count("failed") or count("error"):
        raise ValueError("C# TRX summary reports failures")
    if total != len(rows) or executed != len(rows):
        raise ValueError("C# TRX counters do not reconcile with test results")
    outcomes = {"Passed": sum(row.get("outcome") == "Passed" for row in rows),
                "NotExecuted": sum(row.get("outcome") in ("NotExecuted", "Skipped") for row in rows)}
    if passed != outcomes["Passed"]:
        raise ValueError("C# TRX passed counter does not reconcile with test results")
    failed = [row for row in rows if row.get("outcome") not in ("Passed", "NotExecuted", "Skipped")]
    if failed:
        raise ValueError("C# TRX includes failed tests")
    skipped = [{"name": row.get("testName", ""), "reason": row.get("outcome", "unknown")}
               for row in rows if row.get("outcome") != "Passed"]
    result = {"tests": len(rows), "passed": outcomes["Passed"], "report_sha256": sha(path)}
    return ({"status": "INCOMPLETE", "skipped": skipped, **result} if skipped
            else {"status": "PASS", **result})


def validate_ctest(path: Path) -> dict:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError("CTest JUnit is malformed") from error
    suites = [root] if root.tag.endswith("testsuite") else root.findall(".//testsuite")
    cases = root.findall(".//testcase")
    if not suites or not cases:
        raise ValueError("CTest JUnit has no tests")
    identities = [(case.get("classname", ""), case.get("name", "")) for case in cases]
    if any(not name for _klass, name in identities) or len(set(identities)) != len(identities):
        raise ValueError("CTest JUnit has missing or duplicate test identities")
    skipped, failed = [], []
    declared = 0
    for suite in suites:
        value = suite.get("tests")
        if value is None or not value.isdigit():
            raise ValueError("CTest JUnit suite is missing a test count")
        declared += int(value)
    if declared != len(cases):
        raise ValueError("CTest JUnit counts do not reconcile with test cases")
    for attribute, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"), ("disabled", "skipped")):
        for suite in suites:
            if attribute in suite.attrib and int(suite.attrib[attribute]) != sum(case.find(tag) is not None for case in suite.findall("testcase")):
                raise ValueError(f"CTest JUnit {attribute} summary does not reconcile with test cases")
    for case in cases:
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(case)
        node = case.find("skipped")
        if node is not None:
            skipped.append({"name": case.get("name", ""), "classname": case.get("classname", ""),
                            "reason": node.get("message") or (node.text or "").strip() or "no reason recorded"})
    if failed:
        raise ValueError("CTest JUnit includes failed tests")
    result = {"tests": len(cases), "passed": len(cases) - len(skipped), "report_sha256": sha(path)}
    return {"status": "INCOMPLETE", "skipped": skipped, **result} if skipped else {"status": "PASS", **result}


def validate_key_context(path: Path) -> dict:
    matches = re.findall(r"(?m)^([1-9][0-9]*) game-key context, bounded-I/O and stored-fingerprint checks passed\.\s*$", path.read_text(encoding="utf-8", errors="replace"))
    if len(matches) != 1:
        raise ValueError("RpfPatcher key-context run has no unique positive check count")
    return {"tests": int(matches[0]), "passed": int(matches[0]), "report_sha256": sha(path)}


def layer(name: str, argv: list[str], cwd: Path, output: Path, env: dict[str, str], execute=run_command, validate=None) -> tuple[dict, dict]:
    try:
        command = execute(argv, cwd, output, name, env)
    except Exception as error:
        return {"argv": argv, "cwd": str(cwd), "exception": str(error)}, failed(f"Could not run layer: {error}")
    result = {"status": "PASS" if command["returncode"] == 0 else "FAIL"}
    if command["returncode"] == 0 and validate:
        try:
            evidence = validate(command)
            result.update(evidence)
        except (OSError, ValueError, ET.ParseError, KeyError, TypeError, json.JSONDecodeError) as error:
            result = failed(str(error))
    elif command["returncode"]:
        result["reason"] = f"command exited {command['returncode']}"
    return command, result


def profile(options, tools: dict[str, str | None], output: Path, execute=run_command, scratch: Path | None = None) -> tuple[dict, dict]:
    """Execute independent layers; a failed layer never suppresses another."""
    commands, layers = {}, {}
    scratch = scratch or no_links(output / "pytest")
    scratch.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, ALLIN1_TEST_PYTHON=tools.get("python") or "",
               COVERAGE_FILE=str(output / ".coverage"))
    if options.real_tools:
        env["ALLIN1_RUN_TOOL_INTEGRATION"] = "1"
    def require(key: str, name: str) -> bool:
        if tools.get(key): return True
        layers[name] = failed(f"Required tool is unavailable: {key}")
        return False
    python, pnpm, cargo = tools.get("python"), tools.get("pnpm"), tools.get("cargo")
    desktop = ROOT / "desktop"
    if require("python", "python"):
        junit, coverage = output / "python.xml", output / "coverage.json"
        commands["python"], layers["python"] = layer("python", [python, "-m", "pytest", "tests", "-m", "not (windows_integration or packaged_integration)", "-q", "-p", "no:cacheprovider", "--basetemp", str(scratch / "python"), "--cov=allin1", f"--cov-report=json:{coverage}", "--cov-fail-under=91", f"--junitxml={junit}"], ROOT, output, env, execute,
            lambda _c: {**validate_python_hardening(junit), **validate_coverage(coverage)})
        layers["python"]["selection"] = {"expression": "not (windows_integration or packaged_integration)",
                                              "excluded": ["windows_integration", "packaged_integration"]}
    if require("pnpm", "react"):
        commands["react-build"], build = layer("react-build", [pnpm, "build"], desktop, output, env, execute)
        report = output / "vitest.json"
        def react_evidence(command):
            result = validate_react(strict_json(report.read_bytes()), strict_json((desktop / "module-happy-paths.json").read_bytes()), desktop, command["started_ms"], command["ended_ms"])
            return {**result, "passed": result["tests"], "report_sha256": sha(report), "inventory_sha256": sha(desktop / "module-happy-paths.json")}
        commands["react"], react = layer("react", [pnpm, "test", "--reporter=json", f"--outputFile={report}"], desktop, output, env, execute, react_evidence)
        layers["react"] = {"status": "PASS" if build["status"] == react["status"] == "PASS" else "FAIL", "build": build, "tests": react}
    if require("cargo", "rust-native"):
        def native_evidence(_command):
            result = validate_native(output / "rust-native.log", desktop)
            return {**result, "passed": result["tests"]}
        native_env = dict(env, TAURI_CONFIG=json.dumps({"bundle": {"active": False, "resources": []}}))
        commands["rust-native"], layers["rust-native"] = layer("rust-native", [cargo, "test", "--locked", "--manifest-path", str(desktop / "src-tauri" / "Cargo.toml"), "--message-format=json", "--", "--format=pretty"], ROOT, output, native_env, execute, native_evidence)
        commands["rust-native"]["configuration_override"] = json.loads(native_env["TAURI_CONFIG"])
    if python:
        for name, script in (("documentation", "tools/documentation_audit.py"), ("retirement", "tools/tk_retirement.py")):
            commands[name], layers[name] = layer(name, [python, str(ROOT / script), *( ["--product", "launcher"] if name == "documentation" else [])], ROOT, output, env, execute)
    else:
        layers["documentation"] = failed("Required tool is unavailable: python")
        layers["retirement"] = failed("Required tool is unavailable: python")
    if IS_WINDOWS:
        if require("dotnet", "csharp"):
            trx = output / "csharp.trx"
            commands["csharp"], layers["csharp"] = layer("csharp", [tools["dotnet"], "test", str(ROOT / "script/tests/ALLIN1.Tests.csproj"), "-c", "Release", "--no-restore", "--results-directory", str(output), "--logger", "trx;LogFileName=csharp.trx"], ROOT, output, env, execute, lambda _c: validate_trx(trx))
        cmake_ready = require("cmake", "map-policy")
        ctest_ready = require("ctest", "map-policy")
        if cmake_ready and ctest_ready:
            build = output / "map-build"
            pieces = []
            junit = output / "map-policy.junit.xml"
            for suffix, argv in (("configure", [tools["cmake"], "-S", str(ROOT / "native/map-host"), "-B", str(build), "-DBUILD_TESTING=ON"]), ("build", [tools["cmake"], "--build", str(build), "--config", "Release"]), ("ctest", [tools["ctest"], "--test-dir", str(build), "-C", "Release", "--output-on-failure", "--output-junit", str(junit)])):
                command, result = layer("map-" + suffix, argv, ROOT, output, env, execute,
                                        validate=(lambda _c: validate_ctest(junit)) if suffix == "ctest" else None)
                commands["map-" + suffix] = command; pieces.append(result)
            layers["map-policy"] = {"status": "PASS" if all(row["status"] == "PASS" for row in pieces) else "FAIL", "steps": pieces}
        if options.real_tools:
            if not python:
                layers["windows-integration"] = failed("Required tool is unavailable: python")
            else:
                xml = output / "windows-integration.xml"
                commands["windows-integration"], layers["windows-integration"] = layer("windows-integration", [python, "-m", "pytest", "tests", "-m", "windows_integration", "-q", "-p", "no:cacheprovider", "--basetemp", str(scratch / "windows-integration"), f"--junitxml={xml}"], ROOT, output, env, execute, lambda _c: validate_python_hardening(xml))
            if require("dotnet", "rpf-key-context"):
                commands["rpf-key-context"], layers["rpf-key-context"] = layer("rpf-key-context", [tools["dotnet"], "run", "--project", str(ROOT / "tools/RpfPatcher.KeyContext.Tests/RpfPatcher.KeyContext.Tests.csproj"), "-c", "Release", "--no-restore"], ROOT, output, env, execute, lambda _c: validate_key_context(output / "rpf-key-context.log"))
    elif options.real_tools:
        # This was explicitly requested, so an unsupported platform is a
        # failed prerequisite, never a harmless skip.
        layers["windows-integration"] = failed("--real-tools requires Windows")
        layers["rpf-key-context"] = failed("--real-tools requires Windows")
    return commands, layers


def run(options, *, execute=run_command) -> tuple[int, Path, dict]:
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = options.run_id or uuid.uuid4().hex[:8]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{7,31}", run_id):
        raise ValueError("run id must be 8-32 lowercase letters, digits, or dashes")
    parent = no_links(ROOT / "build" / "hh"); parent.mkdir(parents=True, exist_ok=True); no_links(parent)
    output = no_links(parent / run_id)
    output.mkdir(exist_ok=False)
    # Keep the pytest base path genuinely short on Windows. Deep checkout names
    # plus receipt-owned backup paths can otherwise exceed the legacy Win32
    # path limit and turn a valid filesystem test into a harness-only failure.
    checkout_id = hashlib.sha256(str(ROOT.resolve()).encode("utf-8")).hexdigest()[:8]
    scratch = no_links(Path(tempfile.gettempdir()) / "a1hp" / f"{checkout_id}-{run_id}")
    try:
        scratch.mkdir(parents=True, exist_ok=False)
        scratch_error = None
    except OSError as error:
        # The evidence directory already exists and remains usable even if a
        # short pytest root cannot be created; retain a failure summary there.
        scratch_error = str(error)
    before_error = None
    try: before = source_snapshot(ROOT)
    except Exception as error: before, before_error = None, str(error)
    try: artifacts_before, artifact_before_error = generated_artifacts(ROOT), None
    except Exception as error: artifacts_before, artifact_before_error = None, str(error)
    tools, tool_errors = {}, {}
    for key in ("python", "pnpm", "cargo", "dotnet", "cmake", "ctest"):
        try:
            tools[key] = resolve_tool(getattr(options, key))
        except Exception as error:
            tools[key] = None
            tool_errors[key] = str(error)
    if scratch_error:
        commands, layers = {}, {"scratch": failed(f"Could not create short pytest root: {scratch_error}")}
    else:
        try:
            commands, layers = profile(options, tools, output, scratch=scratch, execute=execute)
        except Exception as error:
            commands, layers = {}, {"harness": failed(f"Unexpected harness I/O failure: {error}")}
    if tool_errors:
        layers["tool-resolution"] = failed("; ".join(f"{name}: {error}" for name, error in sorted(tool_errors.items())))
    try: after = source_snapshot(ROOT); source_unchanged = before is not None and before == after
    except Exception as error: after, source_unchanged = None, False; before_error = before_error or str(error)
    try: artifacts_after, artifact_after_error = generated_artifacts(ROOT), None
    except Exception as error: artifacts_after, artifact_after_error = None, str(error)
    if before_error: layers["source-integrity"] = failed(before_error)
    elif not source_unchanged: layers["source-integrity"] = failed("Source inputs changed during hardening run")
    else: layers["source-integrity"] = {"status": "PASS"}
    if artifact_before_error or artifact_after_error:
        layers["generated-artifacts"] = failed(artifact_before_error or artifact_after_error)
    elif IS_WINDOWS:
        try:
            dist = ROOT / "script" / "dist"
            validate_reactor_bridge_pair_payloads(
                (dist / "ALLIN1.dll").read_bytes(),
                (dist / "ALLIN1.ReactorBridge.plugin").read_bytes(),
                (dist / "ALLIN1.ReactorBridge.contract.json").read_bytes(),
            )
            layers["generated-artifacts"] = {"status": "PASS"}
        except (OSError, ValueError) as error:
            layers["generated-artifacts"] = failed(str(error))
    else:
        layers["generated-artifacts"] = {"status": "PASS", "scope": "not rebuilt or contract-validated off Windows"}
    tool_report = {}
    for name, path in tools.items():
        if not path:
            tool_report[name] = None
            continue
        try:
            tool_report[name] = {"path": path, "sha256": sha(Path(path))}
        except OSError as error:
            tool_report[name] = {"path": path, "sha256": None, "error": str(error)}
            layers["tool-integrity"] = failed(f"{name}: {error}")
    statuses = {row["status"] for row in layers.values()}
    overall = ("PASS" if layers and statuses == {"PASS"}
               else "INCOMPLETE" if "FAIL" not in statuses and "INCOMPLETE" in statuses
               else "FAIL")
    unrun = {"packaged_release": "NOT RUN", "packaged_integration": "NOT TESTED", "native_installer_lifecycle": "NOT RUN", "live_game": "NOT RUN", "installer": "NOT RUN"}
    if not options.real_tools:
        unrun.update(windows_integration="NOT TESTED", rpf_key_context="NOT TESTED")
    if not IS_WINDOWS:
        unrun.update(csharp="NOT TESTED (Windows only)", map_policy="NOT TESTED (Windows only)")
    summary = {"schema_version": 1, "kind": "allin1_off_game_hardening", "run_id": run_id,
        "started_at": started_at, "ended_at": datetime.now(timezone.utc).isoformat(), "output": str(output), "scratch": str(scratch), "tools": tool_report,
        "source_before": before, "source_after": after, "source_unchanged": source_unchanged,
        "generated_artifacts_before": artifacts_before, "generated_artifacts_after": artifacts_after,
        "commands": commands, "layers": layers,
        "unrun": unrun, "status": overall, "release_ready": False}
    write_new(output / "summary.json", summary)
    return (0 if overall == "PASS" else 1), output, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--real-tools", action="store_true", help="Opt in to Windows integration and RpfPatcher key-context tests.")
    parser.add_argument("--python", default=sys.executable); parser.add_argument("--pnpm", default="pnpm"); parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--dotnet", default="dotnet"); parser.add_argument("--cmake", default="cmake"); parser.add_argument("--ctest", default="ctest")
    options = parser.parse_args()
    try: code, output, summary = run(options)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"summary": str(output / "summary.json"), "sha256": sha(output / "summary.json"), "status": summary["status"], "release_ready": False}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
