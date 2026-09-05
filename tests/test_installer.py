"""Unit tests for game-file installation orchestration."""

from pathlib import Path
import hashlib
import json
import struct
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from allin1.config import Config
from allin1 import asi_loader, installer


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


def _write_reactor_pair(
    dist: Path, *, core: bytes = b"mod", bridge: bytes = b"bridge",
) -> None:
    (dist / "ALLIN1.dll").write_bytes(core)
    (dist / "ALLIN1.ReactorBridge.plugin").write_bytes(bridge)
    (dist / "ALLIN1.ReactorBridge.contract.json").write_text(json.dumps({
        "schema_version": 1,
        "version": installer.__version__,
        "core_file": "ALLIN1.dll",
        "core_sha256": hashlib.sha256(core).hexdigest(),
        "bridge_file": "ALLIN1.ReactorBridge.plugin",
        "bridge_sha256": hashlib.sha256(bridge).hexdigest(),
    }))


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


def test_content_registry_deploys_and_authorizes_all_trusted_map_descriptors(
    tmp_path, monkeypatch,
):
    project = tmp_path / "project"
    content_root = project / "content" / "allin1-online-content"
    content_root.mkdir(parents=True)
    source_root = project / "data" / "maps" / "allin1-online-content"
    source_root.mkdir(parents=True)
    descriptors = {
        "city.maps.json": b'{"schema_version":1,"id":"city"}\n',
        "country.maps.json": b'{"schema_version":1,"id":"country"}\n',
    }
    for name, content in descriptors.items():
        (source_root / name).write_bytes(content)
    (content_root / "allin1.content.json").write_text(json.dumps({
        "schema_version": 1,
        "api_version": 1,
        "id": "allin1.online-content",
        "name": "ALLIN1 Online Content",
        "version": "1.0.0",
        "description": "Map deployment fixture",
        "capabilities": ["world.maps"],
        "systems": [{"id": "garages", "name": "Garages"}],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    }), encoding="utf-8")
    game = _game(tmp_path)
    (game / "scripts").mkdir()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_BUILTIN_CATALOG_PAYLOADS", {})
    monkeypatch.setattr(installer, "_BUILTIN_MAP_PAYLOADS", {
        "allin1.online-content": source_root,
    })

    installer._deploy_content_registry(game, Config.default())

    destination_root = (
        game / "scripts" / "ALLIN1" / "Maps" / "allin1.online-content"
    )
    assert {
        path.name: path.read_bytes()
        for path in destination_root.glob("*.maps.json")
    } == descriptors
    registry = json.loads(
        (game / "scripts" / ".allin1" / "extensions" / "registry.json")
        .read_text(encoding="utf-8")
    )
    online = registry["extensions"][0]
    assert online["enabled"] is True
    assert online["map_files"] == [
        {
            "path": (
                "scripts/ALLIN1/Maps/allin1.online-content/"
                f"{name}"
            ),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for name, content in descriptors.items()
    ]


def test_content_registry_refuses_world_maps_without_trusted_payloads(
    tmp_path, monkeypatch,
):
    project = tmp_path / "project"
    content_root = project / "content" / "allin1-online-content"
    content_root.mkdir(parents=True)
    (content_root / "allin1.content.json").write_text(json.dumps({
        "schema_version": 1,
        "api_version": 1,
        "id": "allin1.online-content",
        "name": "ALLIN1 Online Content",
        "version": "1.0.0",
        "description": "Missing map deployment fixture",
        "capabilities": ["world.maps"],
        "systems": [{"id": "garages", "name": "Garages"}],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    }), encoding="utf-8")
    game = _game(tmp_path)
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_BUILTIN_CATALOG_PAYLOADS", {})
    monkeypatch.setattr(installer, "_BUILTIN_MAP_PAYLOADS", {})

    with pytest.raises(FileNotFoundError, match="mapping is missing"):
        installer._deploy_content_registry(game, Config.default())


def test_deploy_script_copies_binaries_and_config(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    _write_reactor_pair(dist)
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
    foreign_lemonui = scripts / installer.RETIRED_LEMONUI_FILENAME
    foreign_lemonui.write_bytes(b"owned by another mod")
    (scripts / "ALLIN1.ini").touch()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game) is True
    assert (scripts / "ALLIN1.dll").read_bytes() == b"mod"
    assert foreign_lemonui.read_bytes() == b"owned by another mod"
    assert (
        scripts / "ReactorV" / "ALLIN1.ReactorBridge.plugin"
    ).read_bytes() == b"bridge"
    assert (
        scripts / "ReactorV" / "ALLIN1.ReactorBridge.contract.json"
    ).is_file()
    assert (scripts / "ALLIN1.toml").exists()
    assert (scripts / "ALLIN1_vehicle_grounding.json").exists()
    assert (scripts / ".reactorv" / "preload" / "allin1.json").exists()
    assert (scripts / "ALLIN1.version").read_text().strip() == installer.__version__
    assert not (scripts / "ALLIN1.ini").exists()


def test_deploy_script_blocks_reactor_only_backend_when_bridge_is_missing(
    tmp_path, monkeypatch,
):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    (dist / "ALLIN1.dll").write_bytes(b"mod")
    game = _game(tmp_path)
    config = Config.default()
    config.script.gbay_ui_backend = "reactor"
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game, config) is False
    assert not (game / "scripts" / "ALLIN1.dll").exists()


def test_deploy_script_rejects_mixed_core_and_bridge_before_copy(
    tmp_path, monkeypatch,
):
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_reactor_pair(dist)
    (dist / "ALLIN1.ReactorBridge.plugin").write_bytes(b"new-bridge")
    game = _game(tmp_path)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_script(game) is False
    assert not (game / "scripts" / "ALLIN1.dll").exists()
    assert not (
        game / "scripts/ReactorV/ALLIN1.ReactorBridge.plugin"
    ).exists()


def test_deploy_script_rolls_back_both_binaries_on_partial_pair_failure(
    tmp_path, monkeypatch,
):
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_reactor_pair(dist, core=b"new-core", bridge=b"new-bridge")
    game = _game(tmp_path)
    scripts = game / "scripts"
    reactor = scripts / "ReactorV"
    reactor.mkdir(parents=True)
    (scripts / "ALLIN1.dll").write_bytes(b"old-core")
    (reactor / "ALLIN1.ReactorBridge.plugin").write_bytes(b"old-bridge")
    (reactor / "ALLIN1.ReactorBridge.contract.json").write_bytes(b"old-contract")
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)
    original_replace = installer.os.replace
    replacements = 0

    def fail_second_replace(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("fixture pair deployment failure")
        return original_replace(source, destination)

    monkeypatch.setattr(installer.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="fixture pair deployment failure"):
        installer._deploy_script(game)

    assert (scripts / "ALLIN1.dll").read_bytes() == b"old-core"
    assert (
        reactor / "ALLIN1.ReactorBridge.plugin"
    ).read_bytes() == b"old-bridge"
    assert (
        reactor / "ALLIN1.ReactorBridge.contract.json"
    ).read_bytes() == b"old-contract"


def test_deploy_reactor_catalog_artwork_uses_only_allowlisted_ui_root(
    tmp_path, monkeypatch,
):
    dist = tmp_path / "dist"
    vehicle_source = dist / "previews"
    weapon_source = dist / "weapon_previews"
    gear_source = dist / "equipment_previews"
    vehicle_source.mkdir(parents=True)
    weapon_source.mkdir()
    gear_source.mkdir()
    (vehicle_source / "barrage.png").write_bytes(b"vehicle-art")
    (vehicle_source / "notes.txt").write_text("not artwork")
    (weapon_source / "weapon_pistol.png").write_bytes(b"weapon-art")
    (gear_source / "armor_heavy.png").write_bytes(b"gear-art")
    game = _game(tmp_path)
    ui = game / "plugins" / "ReactorV" / "ui"
    ui.mkdir(parents=True)
    (ui / "index.html").write_text("<html></html>")
    owned = ui / "assets" / "allin1"
    (owned / "vehicles").mkdir(parents=True)
    (owned / "vehicles" / "retired.png").write_bytes(b"stale")
    (owned / "vehicles" / "keep.txt").write_text("foreign")
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_reactor_catalog_artwork(game) == 3
    assert (owned / "vehicles" / "barrage.png").read_bytes() == b"vehicle-art"
    assert (
        owned / "weapons" / "weapon_pistol.png"
    ).read_bytes() == b"weapon-art"
    assert (owned / "gear" / "armor_heavy.png").read_bytes() == b"gear-art"
    assert not (owned / "vehicles" / "retired.png").exists()
    assert (owned / "vehicles" / "keep.txt").read_text() == "foreign"
    assert not (owned / "vehicles" / "notes.txt").exists()

    # Repair is content-aware: unchanged assets are not rewritten.
    assert installer._deploy_reactor_catalog_artwork(game) == 0


def test_deploy_reactor_catalog_artwork_skips_uninstalled_reactor(
    tmp_path, monkeypatch,
):
    dist = tmp_path / "dist"
    (dist / "previews").mkdir(parents=True)
    (dist / "previews" / "barrage.png").write_bytes(b"vehicle-art")
    game = _game(tmp_path)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)

    assert installer._deploy_reactor_catalog_artwork(game) == 0
    assert not (game / installer._REACTOR_ARTWORK_RELATIVE).exists()


def test_deploy_script_removes_retired_developer_artifacts(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    dist.mkdir(parents=True)
    (dist / "ALLIN1.dll").write_bytes(b"mod")
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


def test_retired_lemonui_cleanup_requires_historical_payload_hash(
    tmp_path, monkeypatch,
):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    candidate = scripts / installer.RETIRED_LEMONUI_FILENAME
    managed_payload = b"historical ALLIN1 LemonUI payload fixture"
    monkeypatch.setattr(
        installer,
        "RETIRED_LEMONUI_SHA256",
        hashlib.sha256(managed_payload).hexdigest().upper(),
    )

    candidate.write_bytes(b"foreign or locally changed dependency")
    assert installer._remove_retired_lemonui_dependency(scripts) is None
    assert candidate.read_bytes() == b"foreign or locally changed dependency"

    candidate.write_bytes(managed_payload)
    assert installer._remove_retired_lemonui_dependency(scripts) == candidate
    assert not candidate.exists()


def test_retired_lemonui_cleanup_uses_the_released_allin1_hash():
    assert installer.RETIRED_LEMONUI_SHA256 == (
        "B52EF80136152ED7AFDF335BD4FF16183977C8E27223AAF5C94A8C16E62E1AEB"
    )


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
    _write_pe(game / "ScriptHookVDotNet3.dll")
    assert installer._check_scripthookv(game) is True
    assert installer._check_shvdn(game) is False
    _write_pe(game / "MinHook.x64.dll")
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
    foreign_lemonui = scripts / installer.RETIRED_LEMONUI_FILENAME
    foreign_lemonui.write_bytes(b"owned by another mod")
    story_catalog = scripts / "ALLIN1" / "Catalogs" / "story-vehicles.json"
    story_catalog.parent.mkdir(parents=True)
    story_catalog.write_text("{}", encoding="utf-8")
    story_catalog.with_name(story_catalog.name + ".bak").write_text(
        "{}", encoding="utf-8",
    )
    (game / "commandline.txt").write_text("-windowed\n-nobattleye\n")
    asi_loader.ensure_nobattleye(game, is_enhanced=False)
    preload_manifest = scripts / ".reactorv" / "preload" / "allin1.json"
    preload_manifest.parent.mkdir(parents=True)
    preload_manifest.write_text("{}", encoding="utf-8")
    reactor_bridge = scripts / "ReactorV" / "ALLIN1.ReactorBridge.plugin"
    reactor_bridge.parent.mkdir(parents=True)
    reactor_bridge.write_bytes(b"bridge")
    reactor_contract = (
        scripts / "ReactorV" / "ALLIN1.ReactorBridge.contract.json"
    )
    reactor_contract.write_text("{}")
    reactor_artwork = game / installer._REACTOR_ARTWORK_RELATIVE
    reactor_artwork.mkdir(parents=True)
    (reactor_artwork / "fixture.png").write_bytes(b"art")
    config = Config.default()
    config.general.gta_path = str(game)
    unpatch = Mock()
    remove_ytds = Mock()
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    monkeypatch.setattr(installer, "_remove_preview_ytds", remove_ytds)

    removed = installer.uninstall(config)

    assert not (scripts / "ALLIN1.dll").exists()
    assert (scripts / "ALLIN1.toml").exists()
    assert (scripts / "ALLIN1_garage.json").exists()
    assert not story_catalog.exists()
    assert not story_catalog.with_name(story_catalog.name + ".bak").exists()
    assert not preload_manifest.exists()
    assert not reactor_bridge.exists()
    assert not reactor_contract.exists()
    assert not reactor_artwork.exists()
    assert foreign_lemonui.read_bytes() == b"owned by another mod"
    assert (game / "commandline.txt").read_text() == "-windowed\n"
    assert not (game / "args.txt").exists()
    assert scripts / "ALLIN1.dll" in removed
    assert game / "args.txt" in removed
    assert preload_manifest in removed
    assert reactor_bridge in removed
    assert reactor_contract in removed
    assert reactor_artwork in removed
    unpatch.assert_called_once_with(game)
    remove_ytds.assert_called_once_with(game)


def test_uninstall_removes_only_the_historical_allin1_lemonui_payload(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path)
    scripts = game / "scripts"
    scripts.mkdir()
    candidate = scripts / installer.RETIRED_LEMONUI_FILENAME
    managed_payload = b"historical ALLIN1 LemonUI payload fixture"
    candidate.write_bytes(managed_payload)
    monkeypatch.setattr(
        installer,
        "RETIRED_LEMONUI_SHA256",
        hashlib.sha256(managed_payload).hexdigest().upper(),
    )
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", Mock())
    monkeypatch.setattr(installer, "_remove_preview_ytds", Mock())
    config = Config.default()
    config.general.gta_path = str(game)

    removed = installer.uninstall(config)

    assert not candidate.exists()
    assert candidate in removed


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


def test_clean_legacy_files_removes_old_runtime_but_preserves_unknown_data(tmp_path):
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
    assert (data / "old.json").read_text() == "{}"
    assert any("Preserved" in warning for warning in result.warnings)
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
    config.script.gbay_ui_backend = "legacy"
    monkeypatch.setattr(installer, "_clean_legacy_files", Mock())
    monkeypatch.setattr(installer, "_deploy_script", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_scripthookv", Mock(return_value=True))
    monkeypatch.setattr(installer, "_check_shvdn", Mock(return_value=False))
    monkeypatch.setattr(installer, "_check_openrpf", Mock(return_value=True))
    monkeypatch.setattr(installer, "_remove_preview_pack", Mock(return_value=[]))
    remove_map = Mock(return_value=[])
    monkeypatch.setattr(installer, "_remove_map_pack", remove_map)
    unpatch = Mock()
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    map_deploy = Mock(return_value=True)
    monkeypatch.setattr(installer, "_deploy_standalone_map_dlc", map_deploy)
    monkeypatch.setattr(
        installer, "_deploy_garment_stock_bridge", Mock(return_value=True),
    )
    monkeypatch.setattr(
        installer, "refresh_garage_map_detection",
        Mock(return_value=SimpleNamespace(summary="map names verified")),
    )
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
    remove_map.assert_not_called()
    unpatch.assert_not_called()
    patch.assert_not_called()


def test_install_uses_approved_optional_rpf_dependency(tmp_path, monkeypatch):
    game = _game(tmp_path, enhanced=True)
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_remove_preview_pack", []), ("_remove_map_pack", []),
        ("_unpatch_dlclist_rpf", None), ("_deploy_preview_dlc", True),
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


@pytest.mark.parametrize("loader_present", [False, True])
def test_reactor_install_uses_png_artwork_and_retires_preview_dlc(
    tmp_path, monkeypatch, loader_present,
):
    game = _game(tmp_path)
    config = Config.default()
    config.general.gta_path = str(game)
    config.general.enable_rpf_previews = True
    config.script.gbay_ui_backend = "reactor"
    monkeypatch.setattr("allin1.reactor_dependency.dependency_recorded", lambda *_: True)
    monkeypatch.setattr("allin1.reactor_dependency.install_dependency", Mock(return_value="Reactor V"))
    monkeypatch.setattr(installer, "validate_reactor_bridge_pair", Mock())
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
            ("_check_scripthookv", True), ("_check_shvdn", True),
            ("_remove_map_pack", []),
            ("_deploy_garment_stock_bridge", True),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    monkeypatch.setattr(
        installer, "refresh_garage_map_detection",
        Mock(return_value=SimpleNamespace(summary="map names verified")),
    )
    monkeypatch.setattr(
        installer, "_check_openrpf", Mock(return_value=loader_present),
    )
    consent = Mock(return_value=True)
    dependency = Mock()
    deploy = Mock(return_value=True)
    remove_preview = Mock(return_value=[])
    unpatch = Mock(return_value=True)
    monkeypatch.setattr(
        installer, "install_recommended_rpf_loader", dependency,
    )
    monkeypatch.setattr(installer, "_deploy_preview_dlc", deploy)
    monkeypatch.setattr(installer, "_remove_preview_pack", remove_preview)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    monkeypatch.setattr(
        installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"),
    )

    result = installer.install(
        config, Mock(), rpf_loader_consent=consent,
    )

    consent.assert_not_called()
    dependency.assert_not_called()
    deploy.assert_not_called()
    remove_preview.assert_called_once_with(game)
    assert unpatch.call_args_list == [
        call(game, "allin1_maps"),
        call(game, "allin1_previews"),
    ]
    assert result.rpf_previews_deployed is False
    assert not any("RPF previews requested" in item for item in result.warnings)


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
        ("_unpatch_dlclist_rpf", None), ("_deploy_preview_dlc", True),
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


def test_install_replaces_legacy_map_pack_with_metadata_bridge(
    tmp_path, monkeypatch,
):
    game = _game(tmp_path, enhanced=True)
    legacy_pack = game / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf"
    legacy_pack.parent.mkdir(parents=True)
    legacy_pack.write_bytes(b"retired compatibility pack")
    config = Config.default()
    config.general.gta_path = str(game)
    for name, value in (
        ("_clean_legacy_files", None), ("_deploy_script", True),
        ("_check_scripthookv", True), ("_check_shvdn", True),
        ("_check_openrpf", True), ("_remove_preview_pack", []),
        ("_deploy_preview_dlc", True),
    ):
        monkeypatch.setattr(installer, name, Mock(return_value=value))
    def replace_with_bridge(_game, _result, progress=None):
        assert progress is None
        legacy_pack.unlink()
        return True

    build = Mock(side_effect=replace_with_bridge)
    monkeypatch.setattr(installer, "_deploy_standalone_map_dlc", build)
    monkeypatch.setattr(
        installer, "_deploy_garment_stock_bridge", Mock(return_value=True),
    )
    unpatch = Mock(return_value=True)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unpatch)
    monkeypatch.setattr(
        installer, "refresh_garage_map_detection",
        Mock(return_value=SimpleNamespace(summary="map names verified")),
    )
    monkeypatch.setattr(
        installer.asi_loader, "ensure_nobattleye", Mock(return_value="set"),
    )

    result = installer.install(config, Mock())

    build.assert_called_once_with(game, result, progress=None)
    unpatch.assert_not_called()
    assert not legacy_pack.exists()
    assert result.standalone_maps_deployed is True
    assert not any("temporarily unavailable" in item for item in result.warnings)


def test_install_deploys_default_enabled_rpf_previews(tmp_path, monkeypatch):
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
