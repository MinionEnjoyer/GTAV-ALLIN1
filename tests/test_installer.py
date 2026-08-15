"""Unit tests for game-file installation orchestration."""

from pathlib import Path
import json
import struct
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
    assert (scripts / "ALLIN1.version").read_text().strip() == "0.4.6"
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
    assert (game / "commandline.txt").read_text() == "-windowed\n"
    assert scripts / "ALLIN1.dll" in removed
    unpatch.assert_called_once_with(game)
    remove_ytds.assert_called_once_with(game)


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
