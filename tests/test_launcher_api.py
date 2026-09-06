import copy
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest
from click.testing import CliRunner

from allin1.desktop_host import serve
from allin1.desktop_service import GAME_ACTIONS, LOCAL_ACTIONS, LauncherService, digest
from allin1.launcher_api import ACTION_FIELDS, LauncherAPI, contract
from allin1.launcher_cli import launcher
from tests.test_desktop_service import service, PROJECT
from tests.test_extensions import _content_package


def test_catalog_covers_every_desktop_action_and_fails_closed(monkeypatch):
    catalog = contract()
    assert {item["name"] for item in catalog["actions"]} == GAME_ACTIONS | LOCAL_ACTIONS
    assert all(item["requires_review"] for item in catalog["actions"])
    monkeypatch.delitem(ACTION_FIELDS, "launch")
    with pytest.raises(ValueError, match="incomplete"): contract()


@pytest.mark.parametrize("module", ["setup", "gameplay", "input", "content", "mods", "characters", "sdk", "activity", "help"])
def test_api_all_workspaces_share_read_only_service(service, module):
    before = service.tree_identity(service.project.parent)
    result = LauncherAPI(service).read("inspect", {"module": module})
    assert result["read_only"] is True
    assert service.tree_identity(service.project.parent) == before


@pytest.mark.parametrize("operation,payload", [("shell", {}), ("inspect", {"module": "setup", "command": "run"}), ("inspect", {"module": 2}), ("open_activity_folder", {})])
def test_unknown_or_ungranted_operations_blocked(service, operation, payload):
    with pytest.raises(ValueError): LauncherAPI(service).read(operation, payload)


def test_agent_stdio_defaults_read_only_but_can_review(service):
    api = LauncherAPI(service)
    rows = [{"schema_version": 1, "request_id": op, "operation": op, "payload": payload} for op, payload in [
        ("catalog", {}), ("review", {"action": "save_profile", "name": "Agent profile"}),
        ("apply", {"review_id": "none", "review_sha256": "none", "confirmed": True})]]
    output = io.StringIO()
    serve(api, io.StringIO("".join(json.dumps(row) + "\n" for row in rows)), output)
    responses = [json.loads(row) for row in output.getvalue().splitlines()]
    assert responses[0]["payload"]["agent_authority"]["writes"] is False
    assert responses[1]["payload"]["executed"] is False
    assert responses[2]["kind"] == "error"
    assert not service.state.exists()


def test_sdk_zip_to_launcher_install_enable_disable_uninstall(service, tmp_path):
    package = _content_package(tmp_path, "acme.sdk-export", runtime=False)
    manifest = package / "mod.toml"
    manifest.write_text(manifest.read_text().replace("schema_version = 1", "schema_version = 2"))
    archive = tmp_path / "SDK build with spaces.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for file in package.iterdir(): zipped.write(file, "package/" + file.name)
    api = LauncherAPI(service, allow_writes=True)
    inspected = api.read("inspect", {"module": "package", "source": str(archive)})
    review = api.review({"action": "package_install", "source": str(archive), "settings": {"strength": 3},
                        "expected_state_sha256": inspected["state_sha256"]})
    assert review["executed"] is False
    with pytest.raises(ValueError, match="confirmation"):
        api.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": False})
    applied = api.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert applied["executed"] is True
    for action in ("package_disable", "package_enable", "package_uninstall"):
        review = api.review({"action": action, "id": "acme.sdk-export"})
        api.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert not api.read("inspect", {"module": "mods"})["installed"]


def test_cli_approval_survives_process_boundary_but_cannot_replay(service):
    api = LauncherAPI(service, allow_writes=True)
    plan = api.plan({"action": "save_profile", "name": "CLI profile"})
    next_api = LauncherAPI(LauncherService(service.project, service.state), allow_writes=True)
    assert next_api.apply_plan(plan, plan["approval_sha256"], confirmed=True)["executed"] is True
    with pytest.raises((ValueError, FileExistsError)):
        next_api.apply_plan(plan, plan["approval_sha256"], confirmed=True)


@pytest.mark.parametrize("change", ["hash", "context", "expiry", "files", "authority", "confirmation"])
def test_plan_guards(service, change):
    api = LauncherAPI(service, allow_writes=True)
    plan = api.plan({"action": "save_profile", "name": "Safe profile"})
    if change == "hash": plan["request"]["name"] = "Changed"
    elif change == "context": plan["state"] += "/other"
    elif change == "expiry": plan["expires_at"] = 0
    elif change == "files":
        game = service.game(service.config())
        (game / "scripts").mkdir()
        (game / "scripts/ALLIN1.toml").write_text("# externally changed")
    elif change == "authority": api.allow_writes = False
    if change in {"context", "expiry"}: plan["approval_sha256"] = digest({k: v for k, v in plan.items() if k != "approval_sha256"})
    with pytest.raises(ValueError): api.apply_plan(plan, plan["approval_sha256"], confirmed=change != "confirmation")
    assert not service.state.exists()


def test_real_cli_plan_apply_and_agent_catalog(service, tmp_path):
    env = {**os.environ, "PYTHONPATH": str(PROJECT / "src"), "PYTHONIOENCODING": "utf-8"}
    base = [sys.executable, "-m", "allin1.launcher_cli", "--project-root", str(service.project), "--state-root", str(service.state)]
    def run(args, input=None):
        result = subprocess.run([*base, *args], input=input, capture_output=True, text=True, encoding="utf-8", env=env,
                                timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert result.returncode == 0, result.stderr + result.stdout
        return json.loads(result.stdout)
    assert run(["catalog"])["api"]["default_authority"] == "read_only"
    assert run(["inspect", "--module", "setup"])["module"] == "setup"
    request = tmp_path / "request.json"; request.write_text('{"action":"save_profile","name":"CLI proof"}')
    output = tmp_path / "plan.json"
    plan = run(["review", "--request", str(request), "--output", str(output)])
    assert plan["executed"] is False and not service.state.exists()
    receipt = run(["--allow-writes", "apply", "--plan", str(output), "--approval-sha256", plan["approval_sha256"], "--confirm"])
    assert receipt["executed"] is True
    response = run(["agent-api"], json.dumps({"schema_version": 1, "request_id": "sdk", "operation": "catalog", "payload": {}}) + "\n")
    assert response["payload"]["api"]["transport"] == "stdio-json-lines"


def test_source_cli_registers_launcher_group():
    from allin1.cli import main
    assert main.commands["launcher"] is launcher
