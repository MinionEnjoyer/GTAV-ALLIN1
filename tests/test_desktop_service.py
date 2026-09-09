"""Headless React boundary happy paths; real persistence in synthetic roots only."""
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import pytest
from allin1.config import Config
from allin1.desktop_service import LauncherService, NAVIGATION, serializable
from allin1.desktop_host import serve

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service(tmp_path):
    project = tmp_path / "Launcher source"; (project / "data").mkdir(parents=True)
    for name in ("vehicles.toml", "weapons.toml"):
        shutil.copy2(PROJECT / "data" / name, project / "data" / name)
    game = tmp_path / "Disposable Enhanced game"; game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"SYNTHETIC NONEXECUTABLE")
    config = Config.default(); config.general.gta_enhanced_path = str(game); config.general.target_edition = "enhanced"
    config.save(project / "config.toml")
    result = LauncherService(project, tmp_path / "User preferences", allow_game_writes=True)
    # Only this fixture's synthetic game can reach write tests; no process launch.
    result.require_closed = lambda: None
    return result


def apply(service, action, **fields):
    review = service.review({"action": action, **fields})
    return service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})


def test_reviewed_package_actions_share_workload_progress_and_clear_it_afterward(service, tmp_path, monkeypatch):
    from allin1.mods import ModIntegrationService, ModStatus
    from tests.test_mods import _rpf_entry_package
    package = _rpf_entry_package(tmp_path, "progress-wiring")
    observed = []
    service.progress = lambda percent, message: observed.append(
        (percent, service.rpf_progress.snapshot() if service.rpf_progress is not None else None))

    def execute(domain, *_args, **_kwargs):
        assert domain.rpf_progress is service.rpf_progress and domain.rpf_progress is not None
        domain.rpf_progress.plan(3, 1)
        for command in ("extract-exact-entry", "replace-entry", "extract-exact-entry"):
            domain.rpf_progress.start(command, "test.bin")
            domain.rpf_progress.finish()
        return ModStatus("progress-wiring", "Test", "1", "rpf", True, True)

    monkeypatch.setattr(ModIntegrationService, "install", execute)
    monkeypatch.setattr(ModIntegrationService, "set_enabled", execute)
    monkeypatch.setattr(ModIntegrationService, "uninstall", execute)
    for action, fields in (("package_install", {"source": str(package)}),
                           ("package_disable", {"id": "progress-wiring"}),
                           ("package_uninstall", {"id": "progress-wiring"})):
        observed.clear()
        assert apply(service, action, **fields)["kind"] == "launcher_applied"
        assert observed[-1] == (100, None)
        assert observed[-2][1]["completed_actions"] == 3
        assert observed[-2][1]["budget_seconds"] == 135
        assert service.rpf_progress is None

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic operation failure")
    monkeypatch.setattr(ModIntegrationService, "uninstall", fail)
    with pytest.raises(RuntimeError, match="synthetic operation failure"):
        apply(service, "package_uninstall", id="progress-wiring")
    assert service.rpf_progress is None


@pytest.mark.parametrize("module", [key for key, _ in NAVIGATION])
def test_every_workspace_has_read_only_happy_path(service, module):
    before = service.tree_identity(service.project.parent)
    result = service.read("inspect", {"module": module})
    assert result["module"] == module and result["state_sha256"]
    assert before == service.tree_identity(service.project.parent)
    json.dumps(result)


def test_setup_exposes_required_reactor_without_retired_backend_fields(service):
    result = service.read('inspect', {'module': 'setup'})
    assert result['reactor']['available'] is False
    assert 'not installed' in result['reactor']['reason']
    assert 'gbay_ui_backend' not in result['config']['script']
    assert 'gbay_menu_enabled' not in result['config']['script']


def test_local_settings_profiles_and_export_do_not_touch_game(service, tmp_path):
    config = serializable(service.config()); config["script"]["ui_scale"] = 1.25
    game = service.game(service.config()); before = service.tree_identity(game)
    receipt = apply(service, "save_config", config=config)
    assert receipt["saved_config"] == config
    assert service.config().script.ui_scale == 1.25
    apply(service, "save_profile", name="Testing profile", config=config)
    assert service.read("load_profile", {"name": "Testing profile"})["config"] == config
    output = tmp_path / "export with spaces.toml"
    apply(service, "export_profile", name="Testing profile", destination=str(output))
    assert Config.load(output).script.ui_scale == 1.25
    apply(service, "delete_profile", name="Testing profile")
    assert not service.profiles.list()
    assert service.tree_identity(game) == before


def test_characters_progress_inventory_outfit_and_unknown_data_survive(service):
    game = service.game(service.config()); (game / "scripts").mkdir()
    target = game / "scripts/ALLIN1_characters.json"
    target.write_text(json.dumps({"future_root": {"keep": True}, "michael": {"future_field": "preserved"}}))
    current = service.inspect({"module": "characters"})
    document = copy.deepcopy(current["loadouts"])
    michael = document["michael"]; michael["progress"].update(managed=True, money=25000)
    michael["managed"] = True; michael["weapons"] = ["WEAPON_PISTOL"]; michael["weapon_ammo"] = {"WEAPON_PISTOL": 120}
    michael["outfit"]["managed"] = True; michael["outfit"]["components"][0]["drawable"] = 1
    apply(service, "characters_save", document=document, expected_state_sha256=current["state_sha256"])
    stored = json.loads(target.read_text())
    assert stored["michael"]["progress"]["money"] == 25000
    assert stored["michael"]["weapon_ammo"]["WEAPON_PISTOL"] == 120
    assert stored["michael"]["outfit"]["components"][0]["drawable"] == 1
    assert stored["future_root"] == {"keep": True} and stored["michael"]["future_field"] == "preserved"


def test_garage_save_export_and_import(service, tmp_path):
    current = service.inspect({"module": "characters"})
    garages = copy.deepcopy(current["garages"])
    model = current["models"][0]
    garages["michael"] = [{"slot": 0, "model": model}]
    apply(service, "garages_save", document=garages, expected_state_sha256=current["state_sha256"])
    assert service.inspect({"module": "characters"})["garages"]["michael"][0]["model"] == model
    output = tmp_path / "garages.json"
    apply(service, "garages_export", destination=str(output))
    assert service.read("read_garages", {"source": str(output)})["garages"]["michael"][0]["model"] == model


def test_stale_draft_review_and_single_use_guard(service):
    current = service.inspect({"module": "characters"})
    request = {"action": "characters_save", "document": current["loadouts"], "expected_state_sha256": current["state_sha256"]}
    review = service.review(request)
    target = service.game(service.config()) / "scripts/ALLIN1_characters.json"; target.parent.mkdir(); target.write_text("{}")
    with pytest.raises(ValueError, match="changed"): service.apply({"confirmed": True, "review_id": review["review_id"], "review_sha256": review["review_sha256"]})
    with pytest.raises(ValueError, match="changed"): service.review(request)
    with pytest.raises(ValueError, match="already used"): service.apply({"confirmed": True, "review_id": review["review_id"]})
    assert target.read_text() == "{}"


def test_authority_cannot_be_granted_by_payload(service):
    service.allow_game_writes = False
    with pytest.raises(ValueError, match="authority"): service.review({"action": "uninstall", "allow_game_writes": True})
    with pytest.raises(ValueError, match="Unknown"): service.review({"action": "shell", "command": "whatever"})
    service.allow_game_writes = True
    with pytest.raises(ValueError, match="launch authority"): service.review({"action": "launch"})


def test_host_protocol_identity_progress_and_errors(service):
    inputs = [
        {"schema_version": 1, "request_id": "a", "operation": "catalog", "payload": {}},
        {"schema_version": 2, "request_id": "b", "operation": "catalog", "payload": {}},
        {"schema_version": 1, "request_id": "c", "operation": "inspect", "payload": {"module": "help"}},
    ]
    output = io.StringIO(); serve(service, io.StringIO("".join(json.dumps(v) + "\n" for v in inputs)), output)
    result = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r["kind"] for r in result] == ["result", "error", "result"]
    assert result[0]["request_id"] == "a" and result[2]["request_id"] == "c"


def test_package_install_disable_enable_uninstall_real_domain(service, tmp_path):
    source = tmp_path / "package"; source.mkdir()
    (source / "payload.ini").write_bytes(b"synthetic mod payload")
    (source / "mod.toml").write_text('schema_version = 1\nid = "react-fixture"\nname = "React fixture"\nversion = "1.0.0"\ntype = "script"\neditions = ["enhanced"]\n[[files]]\nsource = "payload.ini"\ndestination = "scripts/react-fixture.ini"\n')
    apply(service, "package_install", source=str(source / "mod.toml"))
    target = service.game(service.config()) / "scripts/react-fixture.ini"
    assert target.read_bytes() == b"synthetic mod payload"
    apply(service, "package_disable", id="react-fixture")
    assert not target.exists()
    apply(service, "package_enable", id="react-fixture")
    assert target.exists()
    apply(service, "package_uninstall", id="react-fixture")
    assert not target.exists()


@pytest.mark.parametrize("document", [[], None, {"michael": {}}, {"michael": [None]}, {"michael": [{"slot": True, "model": "adder"}]}, {"michael": [{"slot": 0, "model": "not-a-vehicle"}]}])
def test_garage_import_rejects_bad_shapes_without_writes(service, tmp_path, document):
    source = tmp_path / "bad-garage.json"; source.write_text(json.dumps(document))
    before = service.tree_identity(tmp_path)
    with pytest.raises(ValueError): service.read("read_garages", {"source": str(source)})
    assert service.tree_identity(tmp_path) == before


def test_package_payload_changed_after_review_is_rejected(service, tmp_path):
    source = tmp_path / "package"; source.mkdir()
    payload = source / "payload.ini"; payload.write_text("reviewed content")
    manifest = source / "mod.toml"
    manifest.write_text('schema_version = 1\nid = "review-fixture"\nname = "Review fixture"\nversion = "1.0.0"\ntype = "script"\neditions = ["enhanced"]\n[[files]]\nsource = "payload.ini"\ndestination = "scripts/review-fixture.ini"\n')
    review = service.review({"action": "package_install", "source": str(manifest)})
    payload.write_text("changed after review")
    before = service.tree_identity(service.game(service.config()))
    with pytest.raises(ValueError, match="Files changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert service.tree_identity(service.game(service.config())) == before
