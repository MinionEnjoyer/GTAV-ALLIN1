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
from allin1.launcher_api import ACTION_FIELDS, LauncherAPI, contract, schema
from allin1.preview_render_pool import MAX_PREVIEW_WORKERS
from allin1.launcher_cli import launcher
from tests.test_component_bundles import write_bundle, zip_bundle
from tests.test_desktop_service import service, PROJECT
from tests.test_extensions import _content_package


@pytest.mark.parametrize('value', [None, 'weapons', True, {}, ['cars'], ['weapons', 'weapons'], [1], [{}]])
def test_preview_category_contract_rejects_invalid_choices(value):
    with pytest.raises(ValueError):
        LauncherAPI.validate({'skip_preview_categories': value}, ['skip_preview_categories'])


def test_preview_choices_available_to_cli_and_agents():
    from allin1.launcher_api import schema
    for action in ('launch', 'prepare_previews'):
        fields = ACTION_FIELDS[action]
        LauncherAPI.validate({'missing_previews_only': True}, fields)
        assert schema(fields)['properties']['missing_previews_only']['type'] == 'boolean'
        with pytest.raises(ValueError):
            LauncherAPI.validate({'missing_previews_only': 'true'}, fields)
        LauncherAPI.validate({'skip_preview_categories': ['weapons', 'gear'], 'skip_previews': False}, fields)
        field = schema(fields)['properties']['skip_preview_categories']
        assert field['items']['enum'] == ['weapons', 'vehicles', 'gear']
        assert field['uniqueItems'] is True
    LauncherAPI.validate({'quick_launch': True}, ACTION_FIELDS['launch'])
    with pytest.raises(ValueError):
        LauncherAPI.validate({'quick_launch': 'yes'}, ACTION_FIELDS['launch'])
    with pytest.raises(ValueError):
        LauncherAPI.validate({'quick_launch': True}, ACTION_FIELDS['prepare_previews'])


@pytest.mark.parametrize("payload", [
    {"categories": []}, {"categories": ["weapons", "weapons"]}, {"categories": ["unknown"]},
    {"workers": 0}, {"workers": MAX_PREVIEW_WORKERS + 1}, {"workers": True},
])
def test_api_enforces_published_preview_selection_and_worker_bounds(payload):
    with pytest.raises(ValueError):
        LauncherAPI.validate(payload, list(payload))

    # The documented ceiling and a non-empty explicit download selection are
    # valid transport values, not merely schema declarations.
    LauncherAPI.validate({"categories": ["weapons"], "workers": MAX_PREVIEW_WORKERS}, ["categories", "workers"])
    workers = schema(["workers"])["properties"]["workers"]
    assert workers["minimum"] == 1
    assert workers["maximum"] == MAX_PREVIEW_WORKERS
    assert schema(["categories"])["properties"]["categories"]["minItems"] == 1


def test_api_rejects_unknown_review_actions_before_service_dispatch(service, monkeypatch):
    api = LauncherAPI(service)
    monkeypatch.setattr(service, "review", lambda _payload: pytest.fail("unknown action reached service"))
    with pytest.raises(ValueError, match="Unknown Launcher API action"):
        api.review({"action": "erase_game"})


def test_sdk_release_plans_refresh_at_review_and_apply_boundaries(service, monkeypatch):
    """A stale SDK-release cache must be refreshed before either reviewed boundary."""
    api = LauncherAPI(service, allow_writes=True)
    refreshed = []
    monkeypatch.setattr(api, "read", lambda operation, payload: refreshed.append((operation, payload)) or {})
    monkeypatch.setattr(api, "review", lambda payload: {"review_id": "review", "review_sha256": "digest"})
    monkeypatch.setattr(api, "apply", lambda payload: {"executed": True, "payload": payload})

    from allin1.desktop_service import serializable
    request = {"action": "sdk_install_release", "config": serializable(service.config())}
    plan = api.plan(request)
    assert refreshed == [("check_sdk_update", {})]
    assert plan["request"] == request

    refreshed.clear()
    approval = plan["approval_sha256"]
    result = api.apply_plan(plan, approval, confirmed=True)
    assert refreshed == [("check_sdk_update", {})]
    assert result["executed"] is True


def test_agent_api_can_review_the_explicit_component_selected_by_desktop(service, tmp_path):
    source = zip_bundle(write_bundle(tmp_path / "components"), tmp_path / "components.zip")
    review = LauncherAPI(service).review({
        "action": "package_install", "source": str(source), "component_id": "enhanced.part0",
    })
    assert "component_id" in ACTION_FIELDS["package_install"]
    assert review["package"]["id"] == "enhanced.part0"


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


def test_cli_in_process_review_apply_inspect_and_stdio(service, tmp_path):
    runner = CliRunner()
    base = ["--project-root", str(service.project), "--state-root", str(service.state)]

    def invoke(args, input=None):
        result = runner.invoke(launcher, [*base, *args], input=input)
        assert result.exit_code == 0, result.output
        return json.loads(result.output)

    catalog = invoke(["catalog"])
    assert catalog["agent_authority"] == {"writes": False, "game_writes": False, "launch": False}
    config = tmp_path / "config.json"
    from allin1.desktop_service import serializable
    config.write_text(json.dumps(serializable(service.config())))
    assert invoke(["inspect", "--module", "setup", "--config-json", str(config)])["module"] == "setup"
    assert invoke(["request", "catalog"])["api"]["default_authority"] == "read_only"
    payload = tmp_path / "payload.json"
    payload.write_text('{"module":"input"}')
    assert invoke(["request", "inspect", "--payload", str(payload)])["module"] == "input"
    request = tmp_path / "request.json"
    request.write_text('{"action":"save_profile","name":"In process"}')
    plan_path = tmp_path / "reviewed.json"
    plan = invoke(["review", "--request", str(request), "--output", str(plan_path)])
    assert plan == json.loads(plan_path.read_text())
    assert not service.state.exists()
    assert invoke(["review", "--request", str(request)])["executed"] is False
    assert invoke(["--allow-writes", "apply", "--plan", str(plan_path),
                   "--approval-sha256", plan["approval_sha256"], "--confirm"])["executed"] is True
    assert "In process" in service.read("inspect", {"module": "setup"})["profiles"]
    response = invoke(["agent-api"], input=json.dumps({"schema_version": 1, "request_id": "agent",
                      "operation": "catalog", "payload": {}}) + "\n")
    assert response["kind"] == "result"
    assert response["payload"]["agent_authority"]["writes"] is False


@pytest.mark.parametrize("content", ["[]", '{"x":1,"x":2}', "x" * (1024 * 1024 + 1)],
                         ids=["non-object", "duplicate-key", "oversized"])
def test_cli_document_rejects_non_objects_duplicates_and_oversized_requests(tmp_path, content):
    from allin1.launcher_cli import document
    path = tmp_path / "untrusted.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        document(path)


def test_cli_main_emits_structured_errors_and_success(service, tmp_path, capsys):
    from allin1.launcher_cli import main
    base = ["--project-root", str(service.project), "--state-root", str(service.state)]
    assert main([*base, "catalog"]) == 0
    assert json.loads(capsys.readouterr().out)["api"]["default_authority"] == "read_only"
    assert main([*base, "not-a-command"]) == 1
    assert json.loads(capsys.readouterr().out)["kind"] == "error"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]")
    assert main([*base, "review", "--request", str(invalid)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["kind"] == "error" and "object" in result["message"]
    assert not service.state.exists()
