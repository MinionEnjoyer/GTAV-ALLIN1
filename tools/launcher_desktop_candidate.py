"""Build and exercise an unsigned, non-qualifying standalone Launcher candidate.

Never installs software, starts the GUI/GTA, changes real user data, or publishes.
Every run gets a new output directory; no staged application is overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from allin1 import __version__
from allin1.config import tomllib
from allin1.release_paths import contained, no_links, strict_json, tree_files, unique_paths
from allin1.runtime_resources import SIDECAR_NAME, sha256, verify_resources
from tools.react_release_harness import source_identity, write_new

LEGACY_MODULES = (
    "allin1.gui", "allin1.customization_ui", "allin1.addon_sdk_ui",
    "allin1.asset_viewer", "allin1.rpf_explorer", "allin1.reactor_bootstrap_ui",
    "allin1.help_center", "allin1.sdk_installer_ui", "allin1.ui_theme",
)
EXCLUDED_MODULES = ("tkinter", "_tkinter", "PIL.ImageTk", "PIL._imagingtk", *LEGACY_MODULES)


def resource_inputs(root: Path) -> dict[str, Path]:
    from allin1.release import PUBLIC_DOCUMENTATION_FILES, collect_public_files
    allowed = {"LICENSE", "README.md", "RELEASE_NOTES.md", "config.example.toml",
               "prices_gear.toml", "prices_vehicles.toml", "prices_weapons.toml",
               *PUBLIC_DOCUMENTATION_FILES}
    result = {}
    for path in collect_public_files(root):
        name = path.relative_to(root).as_posix()
        if name in allowed or name.startswith(("data/", "content/", "sdk/examples/", "script/dist/", "tools/RpfPatcher/")):
            if path.suffix.lower() not in {".cs", ".csproj", ".pdb"}:
                result[name] = contained(root, name)
    unique_paths(list(result))
    return result


def stage_resources(inputs: dict[str, Path], destination: Path) -> dict[str, str]:
    """Preflight every source and destination before creating any output."""
    no_links(destination)
    if destination.exists():
        raise FileExistsError("Candidate resources must be a new directory")
    unique_paths(list(inputs))
    checked = [(name, no_links(path), contained(destination, name)) for name, path in inputs.items()]
    hashes = {name: sha256(path) for name, path, _ in checked}
    for name, source, target in checked:
        target.parent.mkdir(parents=True, exist_ok=True)
        with no_links(target).open("xb") as stream, no_links(source).open("rb") as incoming:
            shutil.copyfileobj(incoming, stream)
        if sha256(target) != hashes[name]:
            raise ValueError("Resource changed during staging: " + name)
    return hashes


def assert_no_tk(names) -> None:
    for name in names:
        parts = str(name).replace("\\", "/").casefold().split("/")
        module = str(name).replace("/", ".").replace("\\", ".").casefold()
        if (any(part in {"tkinter", "_tkinter", "_tcl_data", "_tk_data"}
                or part.startswith(("_tkinter.", "tcl8", "tcl9", "tk8", "tk9", "pyi_rth__tkinter")) for part in parts)
                or any(module == excluded.casefold() or module.startswith(excluded.casefold() + ".") for excluded in EXCLUDED_MODULES)):
            raise ValueError("Tk/legacy GUI leaked into the candidate: " + str(name))


def inspect_frozen(sidecar: Path) -> dict:
    from PyInstaller.archive.readers import CArchiveReader
    files = tree_files(sidecar.parent)
    names = list(files)
    archive = CArchiveReader(str(sidecar))
    names.extend(archive.toc)
    for name, entry in archive.toc.items():
        if entry[-1] == "z":
            names.extend(archive.open_embedded_archive(name).toc)
    for path in files.values():
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as compressed:
                names.extend(compressed.namelist())
    assert_no_tk(names)
    return {"status": "PASS", "files_and_modules_inspected": len(names)}


def run_logged(command: list[str], cwd: Path, log: Path, *, env=None) -> None:
    print("Running " + str(command[0]) + " (" + log.name + ")", flush=True)
    with log.open("xb") as stream:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
            timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}")


def validate_frontend_probe(report: dict, identity: dict, frontend: Path) -> None:
    if (type(report.get("schema_version")) is not int or report["schema_version"] != 1
            or report.get("kind") != "embedded_frontend_probe" or report.get("status") != "PASS"
            or report.get("production") is not True or report.get("build_id") != identity["build_id"]
            or report.get("version") != identity["version"] or report.get("release_ready") is not False
            or report.get("native_ui") != "NOT TESTED"):
        raise ValueError("Unrelated or non-production embedded frontend evidence")
    assets = report.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("Embedded frontend inventory is missing")
    names = []
    for asset in assets:
        if not isinstance(asset, dict) or set(asset) != {"path", "bytes"} or type(asset["bytes"]) is not int or asset["bytes"] <= 0:
            raise ValueError("Invalid embedded frontend asset")
        names.append(asset["path"])
    unique_paths(names)
    if set(names) != set(tree_files(frontend)):
        raise ValueError("Compiled frontend inventory differs from the production build")


def write_portable(app: Path, destination: Path, identity: dict) -> dict:
    """Package a complete candidate, then verify its actual ZIP bytes.

    This is an unsigned diagnostic distribution, not release qualification or
    installer acceptance. Existing artifacts are never overwritten.
    """
    from allin1.updater import _archive_payloads
    destination = no_links(destination)
    if destination.exists():
        raise FileExistsError(destination)
    if destination.is_relative_to(no_links(app)):
        raise ValueError("Portable output must be outside its input application")
    files = tree_files(app)
    required = {"allin1-launcher-desktop.exe", "sidecar/" + SIDECAR_NAME}
    if not required.issubset(files) or not any(name.startswith("resources/") for name in files):
        raise ValueError("Portable Launcher requires the shell, service and resources")
    generated = {
        "build-identity.json": json.dumps(identity, sort_keys=True).encode(),
        "release.json": json.dumps({"schema_version": 1, "product": "ALLIN1-Launcher", "format": "tauri-v2",
            "version": identity["version"], "build_id": identity["build_id"],
            "entrypoint": "allin1-launcher-desktop.exe", "unsigned_manual_download": True,
            "release_qualified": False}, sort_keys=True).encode(),
    }
    unique_paths([*files, *generated, "checksums.json"])
    hashes = {name: sha256(path) for name, path in files.items()}
    hashes.update({name: hashlib.sha256(value).hexdigest() for name, value in generated.items()})
    generated["checksums.json"] = json.dumps(hashes, sort_keys=True).encode()
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*files, *generated]):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            if name in generated:
                archive.writestr(info, generated[name])
            else:
                with no_links(files[name]).open("rb") as incoming, archive.open(info, "w") as output:
                    shutil.copyfileobj(incoming, output)
    with zipfile.ZipFile(destination) as archive:
        if _archive_payloads(archive) != hashes:
            raise ValueError("Portable Launcher differs from the tested payload")
    return {"file": destination.name, "sha256": sha256(destination), "bytes": destination.stat().st_size,
        "members": len(hashes) + 1, "package_integrity": "PASS", "release_ready": False}


class Host:
    def __init__(self, executable: Path, resources: Path, state: Path, work: Path, env: dict, build_id: str):
        self.process = subprocess.Popen([str(executable), "--project-root", str(resources),
            "--state-root", str(state), "--expected-build-id", build_id], cwd=work, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.events = queue.Queue()
        self.errors = []
        self.sequence = 0
        def read():
            for line in self.process.stdout:
                self.events.put(line)
            self.events.put(None)
        def drain():
            for line in self.process.stderr:
                self.errors.append(line)
        self.reader = threading.Thread(target=read, daemon=True)
        self.stderr_reader = threading.Thread(target=drain, daemon=True)
        self.reader.start()
        self.stderr_reader.start()

    def request(self, operation: str, payload=None, *, fails=False):
        self.sequence += 1
        request_id = f"frozen-smoke-{self.sequence}"
        self.process.stdin.write(json.dumps({"schema_version": 1, "request_id": request_id,
            "operation": operation, "payload": payload or {}}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + 45
        while True:
            line = self.events.get(timeout=max(.01, deadline - time.monotonic()))
            if line is None:
                raise RuntimeError("Frozen service ended: " + "".join(self.errors))
            response = json.loads(line)
            if response.get("schema_version") != 1 or response.get("request_id") != request_id:
                raise ValueError("Frozen service returned another request's response")
            if response["kind"] == "progress":
                continue
            if response["kind"] != ("error" if fails else "result"):
                raise ValueError(f"Unexpected frozen response: {response}")
            return response["payload"]

    def apply(self, review):
        return self.request("apply", {"confirmed": True, "review_id": review["review_id"],
            "review_sha256": review["review_sha256"]})

    def close(self):
        try:
            self.request("shutdown")
            self.process.stdin.close()
            if self.process.wait(timeout=15) != 0:
                raise RuntimeError("Frozen service exited unsuccessfully")
        finally:
            self.abort()

    def abort(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=15)
        self.reader.join(timeout=5)
        self.stderr_reader.join(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


def smoke(sidecar: Path, resources: Path, expected: dict) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    executable_hash = sha256(sidecar)
    verify_resources(resources, expected)
    checks = []
    with tempfile.TemporaryDirectory(prefix="ALLIN1 frozen test with spaces ") as temporary:
        base = Path(temporary)
        # Prove relocatability, not just execution from the source checkout's
        # staging area. Only this disposable copy is changed by failure tests.
        copied = base / "relocated application with spaces"
        shutil.copytree(sidecar.parent.parent, copied)
        original_sidecar, original_resources = sidecar, resources
        sidecar, resources = copied / "sidecar" / sidecar.name, copied / "resources"
        verify_resources(resources, expected)
        # All state/cache/detection paths belong to this disposable directory.
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("ALLIN1", "PYTHON", "VIRTUAL_ENV"))}
        for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TEMP", "TMP"):
            directory = base / key
            directory.mkdir()
            env[key] = str(directory)
        env["PATH"] = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
        state = base / "preferences with spaces"
        canary = base / "outside.canary"
        canary.write_bytes(b"user data preserved")
        host = Host(sidecar, resources, state, base, env, expected["build_id"])
        try:
            catalog = host.request("catalog")
            if catalog["build_identity"]["build_id"] != expected["build_id"]:
                raise ValueError("Frozen binary belongs to another build")
            if catalog["capabilities"] != {"game_writes": False, "launch": False}:
                raise ValueError("Isolated smoke acquired game authority")
            for item in catalog["navigation"]:
                host.request("inspect", {"module": item["id"]})
                checks.append("workspace:" + item["id"])
            if state.exists():
                raise ValueError("Read-only frozen startup created preferences")
            checks.append("read_only_startup")
            host.request("unsupported_operation", fails=True)
            host.request("catalog")
            checks.append("protocol_error_recovery")
            config = catalog["defaults"]
            config["general"]["target_edition"] = "enhanced"
            review = host.request("review", {"action": "save_config", "config": config})
            host.request("apply", {"review_id": review["review_id"]}, fails=True)
            host.apply(review)
            host.request("apply", {"confirmed": True, "review_id": review["review_id"],
                "review_sha256": review["review_sha256"]}, fails=True)
            checks.extend(("explicit_confirmation", "review_single_use", "save_preferences"))
            previous = base / "previous Launcher preferences"
            (previous / "profiles").mkdir(parents=True)
            legacy_bytes = b"[script]\nui_scale = 1.25\n"
            (previous / "config.toml").write_bytes(legacy_bytes)
            (previous / "profiles/Imported profile.toml").write_bytes(legacy_bytes)
            migration = host.request("review", {"action": "import_preferences", "source": str(previous)})
            if migration["migration"]["copy_count"] != 1 or migration["migration"]["preserve_count"] != 1:
                raise ValueError("Frozen preference migration lost its conflict policy")
            host.apply(migration)
            if host.request("load_profile", {"name": "Imported profile"})["config"]["script"]["ui_scale"] != 1.25:
                raise ValueError("Frozen profile import did not preserve values")
            if (previous / "config.toml").read_bytes() != legacy_bytes:
                raise ValueError("Migration changed legacy preferences")
            checks.append("legacy_preferences_import_and_conflict_preservation")
            content = host.apply(host.request("review", {"action": "save_content_preferences",
                "id": "allin1.online-content", "settings": {"traffic_enabled": False}, "config": config}))
            config = content["saved_config"]
            if config["traffic"]["enabled"] is not False:
                raise ValueError("Frozen preinstall preferences did not persist their binding")
            checks.append("preinstall_content_without_game_authority")
            assistant = host.request("inspect", {"module": "sdk"})["assistant"]["status"]["config"]
            assistant["context_tokens"] = 4096
            host.apply(host.request("review", {"action": "assistant_save", "assistant_config": assistant}))
            if host.request("inspect", {"module": "sdk"})["assistant"]["status"]["config"]["context_tokens"] != 4096:
                raise ValueError("Frozen independent assistant preferences did not persist")
            checks.append("assistant_preferences_without_sdk_or_runtime_launch")
            package = base / "inspected package"
            package.mkdir()
            (package / "payload.ini").write_bytes(b"synthetic config")
            (package / "mod.toml").write_text('schema_version = 1\nid = "frozen-fixture"\nname = "Frozen fixture"\nversion = "1.0.0"\ntype = "config"\neditions = ["enhanced"]\n[[files]]\nsource = "payload.ini"\ndestination = "scripts/frozen-fixture.ini"\n')
            inspected = host.request("inspect", {"module": "package", "source": str(package / "mod.toml")})
            if inspected["package"]["id"] != "frozen-fixture":
                raise ValueError("Frozen package inspection returned the wrong package")
            checks.append("package_inspection_without_installation")
            library = host.request("inspect", {"module": "mods"})
            if not library["sdk_examples"] or len(library["builtin_packages"]) != 2:
                raise ValueError("Frozen package examples or included content are missing")
            checks.append("included_content_and_sdk_example_catalog")
            journal = host.request("inspect", {"module": "activity"})["activity"]
            if not journal or any(row["schema_version"] != 1 for row in journal):
                raise ValueError("Frozen structured activity evidence is missing")
            checks.append("structured_activity_journal")
            host.apply(host.request("review", {"action": "save_profile", "name": "Frozen smoke", "config": config}))
            checks.append("save_profile")
            host.request("review", {"action": "install", "config": config}, fails=True)
            checks.append("install_without_game_rejected")
            host.close()
        finally:
            host.abort()
        before = {name: sha256(path) for name, path in tree_files(state).items()}
        host = Host(sidecar, resources, state, base, env, expected["build_id"])
        try:
            session = host.request("inspect", {"module": "setup"})
            if session["config"] != config or host.request("load_profile", {"name": "Frozen smoke"})["config"] != config:
                raise ValueError("Frozen preferences/profile did not survive restart")
            checks.append("restart_preferences_and_profile")
            host.close()
        finally:
            host.abort()
        if before != {name: sha256(path) for name, path in tree_files(state).items()} or canary.read_bytes() != b"user data preserved":
            raise ValueError("Restart changed saved data or an outside canary")
        checks.append("user_data_preservation")
        checks.append("relocated_application_path_with_spaces")
        failed_state = base / "failed-startup-state"
        def rejected(build_id, message):
            result = subprocess.run([str(sidecar), "--project-root", str(resources),
                "--state-root", str(failed_state), "--expected-build-id", build_id],
                input="", capture_output=True, text=True, encoding="utf-8", env=env, cwd=base,
                timeout=45, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode == 0 or result.stdout or message not in result.stderr or failed_state.exists():
                raise ValueError("Corrupt/mixed frozen candidate was not rejected before startup")
        rejected("another-build", "build identities disagree")
        checks.append("mixed_shell_service_rejected")
        target = resources / "config.example.toml"
        original = target.read_bytes()
        try:
            target.write_bytes(b"tampered resource")
            rejected(expected["build_id"], "checksum mismatch")
            target.unlink()
            rejected(expected["build_id"], "exactly match")
        finally:
            target.write_bytes(original)
        checks.extend(("tampered_resource_rejected", "missing_resource_rejected"))
        extra = resources / "stale-payload.txt"
        try:
            extra.write_bytes(b"stale generated resource")
            rejected(expected["build_id"], "exactly match")
        finally:
            extra.unlink()
        checks.append("extra_resource_rejected")
        verify_resources(resources, expected)
        sidecar, resources = original_sidecar, original_resources
    verify_resources(resources, expected)
    if sha256(sidecar) != executable_hash:
        raise ValueError("Frozen binary changed during smoke")
    return {"schema_version": 1, "kind": "launcher_frozen_smoke", "status": "PASS",
        "build_id": expected["build_id"], "sidecar_sha256": executable_hash,
        "resources_sha256": expected["resources_sha256"], "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "gui_and_native_dialogs": "NOT TESTED", "installer_lifecycle": "NOT TESTED",
        "live_acceptance": "NOT TESTED", "release_ready": False}


def build(root: Path, *, service_only: bool = False, pnpm: str = "pnpm", cargo: str = "cargo") -> Path:
    from allin1.release import validate_version_consistency
    from allin1.reactor_bridge_contract import validate_reactor_bridge_pair
    validate_version_consistency(root)
    validate_reactor_bridge_pair(root / "script/dist", expected_version=__version__)
    if importlib.metadata.version("gta-v-allin1") != __version__:
        raise ValueError("Stale Python distribution; reinstall this checkout before freezing")
    for name, version in (
        ("desktop/package.json", json.loads((root / "desktop/package.json").read_text())["version"]),
        ("desktop/src-tauri/tauri.conf.json", json.loads((root / "desktop/src-tauri/tauri.conf.json").read_text())["version"]),
        ("desktop/src-tauri/Cargo.toml", tomllib.loads((root / "desktop/src-tauri/Cargo.toml").read_text())["package"]["version"]),
    ):
        if version != __version__:
            raise ValueError("Stale desktop version: " + name)
    before = source_identity(root)
    folder = contained(root, "build/launcher-candidates/" + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    app = folder / "app"
    resources = app / "resources"
    hashes = stage_resources(resource_inputs(root), resources)
    identity = {"schema_version": 1, "kind": "launcher_desktop_build", "version": __version__,
        "build_id": folder.name, "commit": before["commit"], "source_sha256": before["sha256"],
        "source_dirty": before["dirty"], "created_at": datetime.now(timezone.utc).isoformat(),
        "resources": hashes, "resources_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "runtime": {"python": sys.version, "executable_sha256": sha256(Path(sys.executable)),
            "packages": {name: importlib.metadata.version(name) for name in ("pyinstaller", "pyinstaller-hooks-contrib", "gta-v-allin1", "lxml", "Pillow", "click")}},
        "release_ready": False}
    write_new(folder / "source.json", before)
    identity_path = folder / "_desktop_build.json"
    write_new(identity_path, identity)
    version_file = folder / "sidecar-version.txt"
    numbers = tuple(map(int, __version__.split("."))) + (0,)
    with version_file.open("x", encoding="utf-8") as stream:
        stream.write(f"VSVersionInfo(ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0',[StringStruct('ProductName','ALLIN1 Launcher'),StringStruct('FileVersion',{__version__!r}),StringStruct('ProductVersion',{__version__!r}),StringStruct('BuildId',{folder.name!r})])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])")
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--console", "--onedir",
        "--name", SIDECAR_NAME.removesuffix(".exe"), "--paths", str(root / "src"),
        "--icon", str(root / "src/allin1/assets/ALLIN1.ico"), "--version-file", str(version_file),
        "--add-data", str(identity_path) + os.pathsep + "allin1",
        "--distpath", str(folder / "frozen"), "--workpath", str(folder / "work"), "--specpath", str(folder)]
    for module in EXCLUDED_MODULES:
        command.extend(["--exclude-module", module])
    command.append(str(root / "tools/launcher_sidecar_entry.py"))
    run_logged(command, root, folder / "freeze.log")
    shutil.copytree(folder / "frozen" / SIDECAR_NAME.removesuffix(".exe"), app / "sidecar")
    sidecar = app / "sidecar" / SIDECAR_NAME
    no_tk = inspect_frozen(sidecar)
    write_new(folder / "smoke.json", smoke(sidecar, resources, identity))
    if not service_only:
        manager = shutil.which(pnpm)
        compiler = shutil.which(cargo)
        if not manager or not compiler:
            raise FileNotFoundError("Native candidate requires pnpm and cargo on PATH (or explicit tool paths)")
        package_command = [manager]
        if os.name == "nt" and Path(manager).suffix.lower() in {".cmd", ".bat"}:
            package_command = [os.environ["COMSPEC"], "/d", "/c", manager]
        run_logged([*package_command, "build"], root / "desktop", folder / "frontend.log")
        build_env = dict(os.environ, ALLIN1_LAUNCHER_BUILD_ID=identity["build_id"])
        run_logged([compiler, "build", "--release", "--locked", "--features", "tauri/custom-protocol", "--manifest-path", str(root / "desktop/src-tauri/Cargo.toml")],
                   root, folder / "native.log", env=build_env)
        shell = root / "desktop/src-tauri/target/release/allin1-launcher-desktop.exe"
        shutil.copy2(shell, app / shell.name)
        run_logged([str(app / shell.name), "--verify-embedded-frontend"], app, folder / "frontend-probe.json")
        validate_frontend_probe(strict_json((folder / "frontend-probe.json").read_bytes()), identity, root / "desktop/dist")
    if source_identity(root) != before:
        raise ValueError("Source changed during build; candidate cannot be used as evidence")
    files = {name: sha256(path) for name, path in tree_files(app).items()}
    portable = None
    if not service_only:
        portable = write_portable(app, folder / f"ALLIN1-Launcher-{__version__}-candidate-{folder.name[:12]}-portable.zip", identity)
        with (folder / (portable["file"] + ".sha256")).open("x", encoding="utf-8") as stream:
            stream.write(f"{portable['sha256']}  {portable['file']}\n")
    if source_identity(root) != before:
        raise ValueError("Source changed during packaging; candidate cannot be used as evidence")
    write_new(folder / "report.json", {"schema_version": 1, "build_id": folder.name,
        "kind": "launcher_service_candidate" if service_only else "launcher_desktop_candidate", "version": __version__, "files": files,
        "source_sha256": before["sha256"], "source_dirty": before["dirty"],
        "frozen_service": "PASS", "no_tk_runtime": no_tk, "resource_integrity": "PASS",
        "smoke_sha256": sha256(folder / "smoke.json"), "native_shell_build": "NOT TESTED" if service_only else "PASS",
        "embedded_frontend": "NOT TESTED" if service_only else "PASS", "portable": portable,
        "native_shell_acceptance": "NOT TESTED",
        "installer_lifecycle": "NOT TESTED", "live_acceptance": "NOT TESTED", "release_ready": False})
    return folder / "report.json"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-only", action="store_true",
                        help="Build a non-distributable frozen service; not a full Launcher or release gate")
    parser.add_argument("--pnpm", default="pnpm")
    parser.add_argument("--cargo", default="cargo")
    args = parser.parse_args()
    print(build(ROOT, service_only=args.service_only, pnpm=args.pnpm, cargo=args.cargo))
