"""Unit tests for game-file installation orchestration."""

from pathlib import Path
import json
import struct
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from allin1.config import Config
from allin1 import installer


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _game(tmp_path: Path, enhanced: bool = False) -> Path:
    game = tmp_path / "Grand Theft Auto V"
    game.mkdir()
    (game / ("GTA5_Enhanced.exe" if enhanced else "GTA5.exe")).touch()
    return game


def test_resolve_gta_path_uses_configured_path(tmp_path):
    game = _game(tmp_path)
    config = Config.default()
    config.general.gta_path = str(game)

    assert installer.resolve_gta_path(config) == game


def test_resolve_gta_path_reports_failed_detection(monkeypatch):
    monkeypatch.setattr(installer, "detect_gta_path", lambda: None)
    config = Config.default()

    try:
        installer.resolve_gta_path(config)
    except FileNotFoundError as exc:
        assert "auto-detect" in str(exc)
    else:
        raise AssertionError("Expected failed auto-detection to raise")


def test_content_registry_deploys_trusted_story_vehicle_catalog(tmp_path):
    game = _game(tmp_path)
    (game / "scripts").mkdir()

    installer._deploy_content_registry(game, Config.default())

    catalog_path = (
        game / "scripts" / "ALLIN1" / "Catalogs" / "story-vehicles.json"
    )
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert catalog["id"] == "story-vehicles"
    assert len(catalog["vehicles"]) == 256
    registry = json.loads(
        (game / "scripts" / ".allin1" / "extensions" / "registry.json")
        .read_text(encoding="utf-8")
    )
    online = next(
        item for item in registry["extensions"]
        if item["id"] == "allin1.online-content"
    )
    assert online["gbay"]["catalogs"] == [{
        "id": "story-vehicles",
        "kind": "vehicle",
        "source": "scripts/ALLIN1/Catalogs/story-vehicles.json",
    }]


def test_deploy_script_copies_binaries_and_config(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    (dist / "ALLIN1.dll").write_bytes(b"mod")
    (dist / "LemonUI.SHVDN3.dll").write_bytes(b"ui")
    data = project / "data"
    data.mkdir()
    (data / "vehicle_grounding.json").write_text(
        '{"SchemaVersion":1,"TotalModels":1,"Entries":'
        '{"jester":{"Model":"jester","Status":"measured",'
        '"Stable":true,"RootOffset":0.31}}}'
    )
    (project / "config.toml").write_text("[general]\ngta_path='auto'\n")
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    (scripts / "ALLIN1.ini").touch()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game) is True
    assert (scripts / "ALLIN1.dll").read_bytes() == b"mod"
    assert (scripts / "LemonUI.SHVDN3.dll").read_bytes() == b"ui"
    assert (scripts / "ALLIN1.toml").exists()
    assert (scripts / "ALLIN1_vehicle_grounding.json").exists()
    assert (scripts / "ALLIN1.version").read_text().strip() == "0.6.1"
    assert not (scripts / "ALLIN1.ini").exists()


def test_deploy_script_removes_retired_developer_artifacts(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    (dist / "ALLIN1.dll").write_bytes(b"mod")
    (dist / "LemonUI.SHVDN3.dll").write_bytes(b"ui")
    data = project / "data"
    data.mkdir()
    (data / "vehicle_grounding.json").write_text(
        '{"SchemaVersion":1,"Entries":{}}'
    )
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    for name in installer.RETIRED_DEVELOPER_ARTIFACTS:
        (scripts / name).write_text("retired")
    for name in installer.RETIRED_DEVELOPER_DIRECTORIES:
        retired_dir = scripts / name
        retired_dir.mkdir()
        (retired_dir / "result.json").write_text("retired")
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game) is True
    assert all(not (scripts / name).exists()
               for name in installer.RETIRED_DEVELOPER_ARTIFACTS)
    assert all(not (scripts / name).exists()
               for name in installer.RETIRED_DEVELOPER_DIRECTORIES)


def test_deploy_grounding_catalog_preserves_stable_user_data_and_fills_seed(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    (data / "vehicle_grounding.json").write_text(
        '{"SchemaVersion":1,"TotalModels":2,"Entries":{'
        '"alpha":{"Model":"alpha","Status":"measured","Stable":true,"RootOffset":0.3},'
        '"beta":{"Model":"beta","Status":"measured","Stable":true,"RootOffset":0.4}}}'
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    destination = scripts / "ALLIN1_vehicle_grounding.json"
    destination.write_text(
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"alpha":{"Model":"alpha","Status":"measured","Stable":true,"RootOffset":0.35}}}'
    )
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    merged = json.loads(destination.read_text())
    assert merged["Entries"]["alpha"]["RootOffset"] == 0.35
    assert merged["Entries"]["beta"]["RootOffset"] == 0.4
    assert merged["StableModels"] == 2


def test_deploy_grounding_catalog_replaces_corrupt_checkpoint(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    seed = '{"SchemaVersion":1,"TotalModels":1,"Entries":{"alpha":{}}}'
    (data / "vehicle_grounding.json").write_text(seed)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    destination = scripts / "ALLIN1_vehicle_grounding.json"
    destination.write_text("not json")
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    assert destination.read_text() == seed


def test_deploy_grounding_catalog_is_noop_when_stable_seed_already_exists(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    seed = (
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"alpha":{"Model":"alpha","Status":"measured","Stable":true,"RootOffset":0.3}}}'
    )
    (data / "vehicle_grounding.json").write_text(seed)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    destination = scripts / "ALLIN1_vehicle_grounding.json"
    destination.write_text(seed)
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    assert destination.read_text() == seed


def test_deploy_grounding_catalog_preserves_unsupported_classification(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    seed = (
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"kosatka":{"Model":"kosatka","Status":"unsupported",'
        '"Stable":false,"Note":"validated seed"}}}'
    )
    (data / "vehicle_grounding.json").write_text(seed)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    destination = scripts / "ALLIN1_vehicle_grounding.json"
    destination.write_text(
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"kosatka":{"Model":"kosatka","Status":"unsupported",'
        '"Stable":false,"Note":"local classification"}}}'
    )
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    assert json.loads(destination.read_text())["Entries"]["kosatka"]["Note"] \
        == "local classification"


def test_deploy_grounding_catalog_replaces_unresolved_with_seed_outcome(tmp_path, monkeypatch):
    project = tmp_path / "project"
    data = project / "data"
    data.mkdir(parents=True)
    (data / "vehicle_grounding.json").write_text(
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"bati":{"Model":"bati","Status":"measured",'
        '"Stable":true,"RootOffset":0.35}}}'
    )
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    destination = scripts / "ALLIN1_vehicle_grounding.json"
    destination.write_text(
        '{"SchemaVersion":1,"TotalModels":1,"Entries":{'
        '"bati":{"Model":"bati","Status":"unstable",'
        '"Stable":false,"RootOffset":0.0}}}'
    )
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    merged = json.loads(destination.read_text())
    assert merged["Entries"]["bati"]["RootOffset"] == 0.35
    assert merged["StableModels"] == 1
    assert merged["UnsupportedModels"] == 0
    assert merged["OutlierModels"] == 0


def test_deploy_grounding_catalog_tolerates_missing_seed(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)

    installer._deploy_grounding_catalog(scripts)

    assert not (scripts / "ALLIN1_vehicle_grounding.json").exists()


def test_deploy_script_returns_false_when_binary_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", tmp_path / "missing")
    assert installer._deploy_script(_game(tmp_path)) is False


def test_prerequisite_checks(tmp_path):
    game = _game(tmp_path)
    assert installer._check_scripthookv(game) is False
    assert installer._check_shvdn(game) is False
    _write_pe(game / "ScriptHookV.dll")
    _write_pe(game / "ScriptHookVDotNet.asi")
    assert installer._check_scripthookv(game) is True
    assert installer._check_shvdn(game) is True


def test_legacy_openiv_check_does_not_download(tmp_path):
    game = _game(tmp_path)
    assert installer._check_openrpf(game, enhanced=False) is False
    _write_pe(game / "OpenIV.asi")
    assert installer._check_openrpf(game, enhanced=False) is False
    _write_pe(game / "dinput8.dll")
    assert installer._check_openrpf(game, enhanced=False) is True


def test_uninstall_removes_owned_files_and_preserves_other_flags(tmp_path, monkeypatch):
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    for name in ("ALLIN1.dll", "ALLIN1.toml", "ALLIN1_garage.json"):
        (scripts / name).touch()
    story_catalog = scripts / "ALLIN1" / "Catalogs" / "story-vehicles.json"
    story_catalog.parent.mkdir(parents=True)
    story_catalog.write_text("{}", encoding="utf-8")
    story_catalog.with_name(story_catalog.name + ".bak").write_text(
        "{}", encoding="utf-8",
    )
    (game / "commandline.txt").write_text("-windowed\n-nobattleye\n")
    config = Config.default()
    config.general.gta_path = str(game)
    unpatch = Mock()
    remove_ytds = Mock()
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    monkeypatch.setattr(installer, "_remove_preview_ytds", remove_ytds)

    removed = installer.uninstall(config)

    assert not (scripts / "ALLIN1.dll").exists()
    assert not (scripts / "ALLIN1.toml").exists()
    assert not story_catalog.exists()
    assert not story_catalog.with_name(story_catalog.name + ".bak").exists()
    assert (game / "commandline.txt").read_text() == "-windowed\n"
    assert scripts / "ALLIN1.dll" in removed
    unpatch.assert_called_once_with(game)
    remove_ytds.assert_called_once_with(game)


def test_uninstall_removes_owned_story_policy_but_preserves_other_flags(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path)
    (game / "commandline.txt").write_text(
        "-windowed\n-nobattleye\n-scofflineonly\n"
    )
    state = game / "scripts/.allin1/launch-policy.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({
        "schema_version": 1, "argument": "-scofflineonly",
        "inserted": True, "created_file": False,
    }))
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())

    installer.uninstall(config)

    assert (game / "commandline.txt").read_text() == "-windowed\n"
    assert not (game / "scripts/.allin1/launch-policy.json").exists()


def test_uninstall_removes_commandline_when_only_battleye_flag(tmp_path, monkeypatch):
    game = _game(tmp_path)
    (game / "commandline.txt").write_text("-nobattleye\n")
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())

    installer.uninstall(config)

    assert not (game / "commandline.txt").exists()


def test_clean_legacy_files_removes_old_runtime_and_data(tmp_path):
    game = _game(tmp_path)
    (game / "ALLIN1.asi").touch()
    (game / "ALLIN1.dll").touch()
    data = game / "ALLIN1"
    data.mkdir()
    (data / "old.json").write_text("{}")
    result = installer.InstallResult(game)

    installer._clean_legacy_files(game, result)

    assert not (game / "ALLIN1.asi").exists()
    assert not (game / "ALLIN1.dll").exists()
    assert not data.exists()
    assert len(result.warnings) == 3


def test_uninstall_removes_legacy_preview_locations(tmp_path, monkeypatch):
    game = _game(tmp_path)
    previews = game / "scripts" / "previews"
    previews.mkdir(parents=True)
    (previews / "car.png").touch()
    (game / "scripts" / "PHAT.png").touch()
    dlc = game / "mods" / "update" / "x64" / "dlcpacks" / "allin1_previews"
    dlc.mkdir(parents=True)
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())

    installer.uninstall(config)

    assert not previews.exists()
    assert not (game / "scripts" / "PHAT.png").exists()
    assert not dlc.exists()


def test_install_orchestrates_steps_and_collects_preview_warning(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    monkeypatch.setattr(installer, "_clean_legacy_files", Mock())
    monkeypatch.setattr(installer, "_deploy_script", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_scripthookv", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_shvdn", Mock(return_value=False))
    monkeypatch.setattr(installer, "_check_openrpf", Mock(return_value=True))
    monkeypatch.setattr(installer, "_remove_preview_pack", Mock(return_value=[]))
    monkeypatch.setattr(installer, "_remove_map_pack", Mock(return_value=[]))
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    map_deploy = Mock(return_value=True)
    monkeypatch.setattr(installer, "_deploy_standalone_map_dlc", map_deploy)
    monkeypatch.setattr(installer, "_deploy_preview_dlc", Mock(side_effect=RuntimeError("preview failed")))
    patch = Mock()
    monkeypatch.setattr(installer, "_patch_dlclist_rpf", patch)
    monkeypatch.setattr(installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"))

    result = installer.install(config, Mock())

    assert result.is_enhanced is True
    assert result.dll_deployed is True
    assert result.shvdn_found is False
    assert result.standalone_maps_deployed is True
    assert result.battleye_status == "set"
    assert result.warnings == ["Preview texture injection failed: preview failed"]
    map_deploy.assert_called_once_with(game, result, progress=None)
    patch.assert_not_called()


def test_install_uses_approved_optional_rpf_dependency(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_remove_preview_pack", []), ("_remove_map_pack", []),
        ("_unpatch_dlclist_rpf", None),
        ("_deploy_standalone_map_dlc", True), ("_deploy_preview_dlc", True),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    check = Mock(side_effect=[False, True])
    monkeypatch.setattr(installer, "_check_openrpf", check)
    installed = SimpleNamespace(
        installed=(game / "RageOpenV.asi",),
        provider="RageOpenV", version="v1.0",
    )
    dependency = Mock(return_value=installed)
    monkeypatch.setattr(installer, "install_recommended_rpf_loader", dependency)
    monkeypatch.setattr(
        installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"),
    )
    consent = Mock(return_value=True)

    result = installer.install(
        config, Mock(), rpf_loader_consent=consent,
    )

    consent.assert_called_once_with(game, True)
    dependency.assert_called_once_with(game, True)
    assert result.openrpf_found is True
    assert result.rpf_loader_installed is True
    assert result.rpf_loader_provider == "RageOpenV v1.0"


def test_optional_rpf_dependency_io_failure_does_not_block_repair(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path, enhanced=False)
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_remove_preview_pack", []), ("_remove_map_pack", []),
        ("_unpatch_dlclist_rpf", None),
        ("_deploy_standalone_map_dlc", True), ("_deploy_preview_dlc", True),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    monkeypatch.setattr(installer, "_check_openrpf", Mock(return_value=False))
    monkeypatch.setattr(
        installer, "install_recommended_rpf_loader",
        Mock(side_effect=PermissionError("access denied")),
    )
    monkeypatch.setattr(
        installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"),
    )

    result = installer.install(
        config, Mock(), rpf_loader_consent=lambda _path, _enhanced: True,
    )

    assert result.openrpf_found is False
    assert result.rpf_previews_deployed is False
    assert any("access denied" in warning for warning in result.warnings)


def test_install_rejects_missing_required_standalone_map_pack(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_check_openrpf", True), ("_remove_preview_pack", []),
        ("_remove_map_pack", []), ("_unpatch_dlclist_rpf", None),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    monkeypatch.setattr(
        installer, "_deploy_standalone_map_dlc", Mock(return_value=False),
    )

    with pytest.raises(RuntimeError, match="garage interiors would be unavailable"):
        installer.install(config, Mock())


def test_repair_preserves_existing_dlc_packs_when_rebuild_fails(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path, enhanced=True)
    preview = game / "mods/update/x64/dlcpacks/allin1_previews/dlc.rpf"
    maps = game / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf"
    preview.parent.mkdir(parents=True)
    maps.parent.mkdir(parents=True)
    preview.write_bytes(b"working-preview")
    maps.write_bytes(b"working-maps")

    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_check_openrpf", True),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    monkeypatch.setattr(
        installer, "_deploy_standalone_map_dlc",
        Mock(side_effect=RuntimeError("helper blocked")),
    )
    remove_preview = Mock()
    remove_maps = Mock()
    unpatch = Mock()
    monkeypatch.setattr(installer, "_remove_preview_pack", remove_preview)
    monkeypatch.setattr(installer, "_remove_map_pack", remove_maps)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)

    with pytest.raises(RuntimeError, match="helper blocked"):
        installer.install(config, Mock())

    assert preview.read_bytes() == b"working-preview"
    assert maps.read_bytes() == b"working-maps"
    remove_preview.assert_not_called()
    remove_maps.assert_not_called()
    unpatch.assert_not_called()


def test_install_deploys_default_enabled_rpf_previews(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_check_openrpf", True), ("_remove_preview_pack", []),
        ("_remove_map_pack", []), ("_deploy_standalone_map_dlc", True),
        ("_unpatch_dlclist_rpf", None),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    deploy = Mock(return_value=True)
    monkeypatch.setattr(installer, "_deploy_preview_dlc", deploy)
    monkeypatch.setattr(installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"))
    progress = Mock()
    result = installer.install(config, Mock(), progress=progress)
    assert result.rpf_previews_deployed is True
    deploy.assert_called_once_with(game, result, progress=progress)
    percentages = [call.args[0] for call in progress.call_args_list]
    assert percentages == sorted(percentages)
    assert percentages[0] == 0 and percentages[-1] == 100


def test_atomic_copy_replaces_complete_file_and_keeps_backup(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"new")
    destination.write_bytes(b"old")
    installer._copy_atomic(source, destination)
    assert destination.read_bytes() == b"new"
    assert (tmp_path / "destination.bak").read_bytes() == b"old"


def test_atomic_copy_restores_previous_file_on_replace_failure(tmp_path, monkeypatch):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"new")
    destination.write_bytes(b"old")
    original_replace = installer.Path.replace
    monkeypatch.setattr(installer.Path, "replace", lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    with pytest.raises(OSError, match="locked"):
        installer._copy_atomic(source, destination)
    assert destination.read_bytes() == b"old"
    monkeypatch.setattr(installer.Path, "replace", original_replace)


def test_install_colored_smoke_weapons_invokes_owned_dlc_command(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    game = _game(tmp_path)
    result = installer.InstallResult(game)
    run = Mock(return_value=Mock(returncode=0, stdout="verified", stderr=""))
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    monkeypatch.setattr(installer, "run_hidden", run)

    assert installer._install_colored_smoke_weapons(game, result) is True
    run.assert_called_once_with(
        [str(patcher), "install-colored-smoke-weapons", str(game)],
        capture_output=True, text=True, timeout=600,
    )
    assert result.warnings == []


def test_install_colored_smoke_weapons_reports_patcher_failure(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    game = _game(tmp_path)
    result = installer.InstallResult(game)
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    monkeypatch.setattr(installer, "run_hidden", Mock(return_value=Mock(
        returncode=3, stdout="", stderr="metadata mismatch",
    )))

    assert installer._install_colored_smoke_weapons(game, result) is False
    assert result.warnings == [
        "Colored smoke weapon installation failed: metadata mismatch"
    ]


def test_colored_smoke_removal_does_not_depend_on_marker(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    game = _game(tmp_path)
    archive = game / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"unsafe")
    run = Mock(return_value=Mock(returncode=0, stdout="removed", stderr=""))
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    monkeypatch.setattr(installer, "run_hidden", run)

    installer._remove_colored_smoke_weapons(game)

    run.assert_called_once_with(
        [str(patcher), "remove-colored-smoke-weapons", str(game)],
        capture_output=True, text=True, timeout=600,
    )


def test_merged_smoke_canary_removal_is_marker_gated(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    game = _game(tmp_path)
    run = Mock(return_value=Mock(returncode=0, stdout="restored", stderr=""))
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    monkeypatch.setattr(installer, "run_hidden", run)

    installer._remove_merged_smoke_canary(game)
    run.assert_not_called()

    marker = game / "scripts/ALLIN1_colored_smoke_merged_canary.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    installer._remove_merged_smoke_canary(game)

    run.assert_called_once_with(
        [str(patcher), "remove-merged-smoke-canary", str(game)],
        capture_output=True, text=True, timeout=600,
    )


def test_rpf_quarantine_marker_is_atomic_and_diagnostic(tmp_path):
    game = _game(tmp_path)

    installer._write_rpf_quarantine(game)

    marker = json.loads(
        (game / "scripts/ALLIN1_rpf_quarantine.json").read_text()
    )
    smoke = marker["packs"]["allin1_smoke"]
    assert marker["schema"] == 1
    assert smoke["state"] == "quarantined"
    assert "Story Mode startup hangs" in smoke["reason"]


def test_smoke_tuning_installer_reports_missing_failure_exception_and_success(
    tmp_path, monkeypatch,
):
    tools = tmp_path / "tools"
    game = _game(tmp_path)
    result = installer.InstallResult(game)
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)

    assert installer._install_smoke_tuning(game, result) is False
    assert "RpfPatcher.exe missing" in result.warnings[-1]

    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    monkeypatch.setattr(installer, "run_hidden", Mock(return_value=Mock(
        returncode=0, stdout="merged\nverified", stderr="",
    )))
    assert installer._install_smoke_tuning(game, result) is True

    monkeypatch.setattr(installer, "run_hidden", Mock(return_value=Mock(
        returncode=4, stdout="", stderr="",
    )))
    assert installer._install_smoke_tuning(game, result) is False
    assert result.warnings[-1].endswith("exit code 4")

    monkeypatch.setattr(installer, "run_hidden", Mock(side_effect=OSError("locked")))
    assert installer._install_smoke_tuning(game, result) is False
    assert result.warnings[-1].endswith("locked")


def test_smoke_tuning_removal_is_gated_and_handles_all_tool_results(
    tmp_path, monkeypatch,
):
    tools = tmp_path / "tools"
    game = _game(tmp_path)
    run = Mock()
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    monkeypatch.setattr(installer, "run_hidden", run)

    installer._remove_smoke_tuning(game)
    run.assert_not_called()

    marker = game / "scripts" / "ALLIN1_smoke_tuning.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    installer._remove_smoke_tuning(game)
    run.assert_not_called()

    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    run.return_value = Mock(returncode=0, stdout="", stderr="")
    installer._remove_smoke_tuning(game)
    assert run.call_count == 1

    run.return_value = Mock(returncode=5, stdout="", stderr="restore failed")
    installer._remove_smoke_tuning(game)
    assert run.call_count == 2

    run.side_effect = OSError("busy")
    installer._remove_smoke_tuning(game)
    assert run.call_count == 3


def test_colored_smoke_helpers_cover_missing_tool_and_exception_paths(
    tmp_path, monkeypatch,
):
    tools = tmp_path / "tools"
    game = _game(tmp_path)
    result = installer.InstallResult(game)
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)

    assert installer._install_colored_smoke_weapons(game, result) is False
    assert "independent colored smoke weapons were skipped" in result.warnings[-1]

    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    monkeypatch.setattr(installer, "run_hidden", Mock(side_effect=OSError("denied")))
    assert installer._install_colored_smoke_weapons(game, result) is False
    assert result.warnings[-1].endswith("denied")

    archive = game / "mods/update/x64/dlcpacks/allin1_smoke/dlc.rpf"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"unsafe")
    patcher.unlink()
    installer._remove_colored_smoke_weapons(game)

    patcher.touch()
    installer._remove_colored_smoke_weapons(game)


def test_merged_smoke_removal_handles_missing_tool_failure_and_exception(
    tmp_path, monkeypatch,
):
    tools = tmp_path / "tools"
    game = _game(tmp_path)
    marker = game / "scripts" / "ALLIN1_colored_smoke_merged_canary.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}")
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    missing_run = Mock()
    monkeypatch.setattr(installer, "run_hidden", missing_run)

    installer._remove_merged_smoke_canary(game)
    missing_run.assert_not_called()

    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    patcher.parent.mkdir(parents=True)
    patcher.touch()
    run = Mock(return_value=Mock(returncode=7, stdout="", stderr="bad restore"))
    monkeypatch.setattr(installer, "run_hidden", run)
    installer._remove_merged_smoke_canary(game)
    run.assert_called_once_with(
        [str(patcher), "remove-merged-smoke-canary", str(game)],
        capture_output=True, text=True, timeout=600,
    )

    run.side_effect = OSError("busy")
    installer._remove_merged_smoke_canary(game)
    assert run.call_count == 2
