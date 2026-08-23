"""Contract and lifecycle coverage for ALLIN1 content extensions."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from allin1.cli import main
from allin1.config import Config
from allin1.extensions import (
    ExtensionCatalog,
    ExtensionManifest,
    ExtensionRegistry,
    ExtensionSetting,
    ExtensionSettingsStore,
    ExtensionSystem,
    GbayCatalog,
    GbaySection,
    RuntimeAssembly,
    _ContentRequirement,
    _content_requirements,
    apply_settings_to_config,
    settings_from_config,
)
from allin1.mods import ModIntegrationService, ModManifest


ROOT = Path(__file__).resolve().parents[1]


def _descriptor() -> dict:
    return {
        "schema_version": 1,
        "api_version": 1,
        "id": "acme.extension",
        "name": "ACME Extension",
        "version": "1.0.0",
        "description": "Synthetic descriptor",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "weather-system",
            "name": "Weather System",
            "settings": [{
                "key": "strength",
                "label": "Strength",
                "type": "integer",
                "default": 2,
                "minimum": 0,
                "maximum": 5,
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    }


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    game.mkdir(parents=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"exe")
    return game


def _content_package(
    tmp_path: Path,
    package_id: str,
    *,
    version: str = "1.0.0",
    requires: tuple[str, ...] = (),
    runtime: bool = True,
) -> Path:
    package = tmp_path / package_id
    package.mkdir(parents=True)
    destination = (
        f"scripts/{package_id}.dll" if runtime
        else f"scripts/{package_id}/content.json"
    )
    payload = b"managed extension payload"
    (package / "payload.bin").write_bytes(payload)
    descriptor = {
        "schema_version": 1,
        "api_version": 1,
        "id": package_id,
        "name": f"Test {package_id}",
        "version": version,
        "description": "Synthetic content package",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "weather-system",
            "name": "Weather System",
            "category": "World",
            "settings": [{
                "key": "strength",
                "label": "Strength",
                "type": "integer",
                "default": 2,
                "minimum": 0,
                "maximum": 5,
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {
            "assemblies": [{"path": destination}] if runtime else [],
        },
    }
    (package / "allin1.content.json").write_text(
        json.dumps(descriptor), encoding="utf-8",
    )
    requirement_text = ", ".join(json.dumps(value) for value in requires)
    (package / "mod.toml").write_text(
        "schema_version = 2\n"
        f"id = {json.dumps(package_id)}\n"
        f"name = {json.dumps('Test ' + package_id)}\n"
        f"version = {json.dumps(version)}\n"
        f"type = {json.dumps('script' if runtime else 'config')}\n"
        'editions = ["legacy", "enhanced"]\n'
        "dependencies = []\n"
        "conflicts = []\n"
        "dlc_packs = []\n"
        "[allin1]\n"
        "api_version = 1\n"
        'content = "allin1.content.json"\n'
        f"requires = [{requirement_text}]\n"
        "[[files]]\n"
        'source = "payload.bin"\n'
        f"destination = {json.dumps(destination)}\n"
        f"sha256 = {json.dumps(hashlib.sha256(payload).hexdigest())}\n",
        encoding="utf-8",
    )
    return package


def test_bundled_content_catalog_is_valid_and_experiments_default_off() -> None:
    manifests = ExtensionCatalog(ROOT / "content").discover()
    assert [manifest.extension_id for manifest in manifests] == [
        "allin1.experimental-gameplay",
        "allin1.online-content",
    ]
    experiments = manifests[0]
    assert all(system.experimental for system in experiments.systems)
    assert all(not system.enabled_by_default for system in experiments.systems)
    assert all(setting.default is False for setting in experiments.settings)


def test_bound_settings_round_trip_through_core_config() -> None:
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    config = Config.default()
    values = settings_from_config(online, config)
    assert values["traffic_enabled"] is True
    apply_settings_to_config(online, config, {
        "traffic_enabled": False,
        "free_purchases": True,
    })
    assert config.traffic.enabled is False
    assert config.script.gbay_free_mode is True


def test_builtin_registry_preserves_state_and_namespaced_settings(tmp_path: Path) -> None:
    game = _game(tmp_path)
    manifest = ExtensionManifest.load(
        ROOT / "content" / "allin1-experimental-gameplay" / "allin1.content.json"
    )
    registry = ExtensionRegistry(game)
    registry.register_builtin(manifest, settings={"npc_physics": False})
    registry.set_builtin_enabled(manifest.extension_id, False)
    registry.set_setting(manifest.extension_id, "npc_physics", True)
    registry.register_builtin(manifest, enabled=None)

    entry = registry.installed()[0]
    assert entry["id"] == manifest.extension_id
    assert entry["source"] == "built-in"
    assert entry["enabled"] is False
    assert entry["settings"]["npc_physics"] is True


def test_extension_package_lifecycle_authorizes_only_receipt_hashed_runtime(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    package = _content_package(tmp_path, "acme.weather")
    manifest = ModManifest.load(package)
    service = ModIntegrationService(game)

    service.install(manifest)
    entry = ExtensionRegistry(game).installed()[0]
    assert entry["id"] == "acme.weather"
    assert entry["enabled"] is True
    assert entry["source"] == "package"
    assert entry["runtime_files"] == [{
        "path": "scripts/acme.weather.dll",
        "sha256": hashlib.sha256(b"managed extension payload").hexdigest(),
    }]

    service.set_enabled("acme.weather", False)
    assert ExtensionRegistry(game).installed()[0]["enabled"] is False
    service.set_enabled("acme.weather", True)
    service.uninstall("acme.weather")
    assert ExtensionRegistry(game).installed() == []


def test_runtime_hash_drift_blocks_loading_toggle_and_uninstall(tmp_path: Path) -> None:
    game = _game(tmp_path)
    package = _content_package(tmp_path, "acme.secure")
    service = ModIntegrationService(game)
    service.install(ModManifest.load(package))
    target = game / "scripts" / "acme.secure.dll"
    target.write_bytes(b"externally changed")

    entry = ExtensionRegistry(game).rebuild()["extensions"][0]
    assert entry["enabled"] is False
    assert "receipt hash" in entry["blocked_reason"]
    with pytest.raises(RuntimeError, match="externally changed"):
        service.set_enabled("acme.secure", False)
    with pytest.raises(RuntimeError, match="externally changed"):
        service.uninstall("acme.secure")


def test_package_requirements_protect_enabled_dependencies(tmp_path: Path) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    base = _content_package(
        tmp_path / "base", "acme.foundation", runtime=False, version="1.2.0",
    )
    child = _content_package(
        tmp_path / "child", "acme.feature", runtime=False,
        requires=("acme.foundation>=1.1",),
    )
    service.install(ModManifest.load(base))
    service.install(ModManifest.load(child))

    with pytest.raises(ValueError, match="required by: acme.feature"):
        service.set_enabled("acme.foundation", False)
    with pytest.raises(ValueError, match="required by: acme.feature"):
        service.uninstall("acme.foundation")
    service.set_enabled("acme.feature", False)
    service.set_enabled("acme.foundation", False)


def test_dependency_update_cannot_downgrade_below_enabled_requirement(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    foundation_v2 = ModManifest.load(_content_package(
        tmp_path / "v2", "acme.foundation", version="2.0.0",
    ))
    dependent = ModManifest.load(_content_package(
        tmp_path / "child", "acme.dependent",
        requires=("acme.foundation>=2.0.0",),
    ))
    foundation_v1 = ModManifest.load(_content_package(
        tmp_path / "v1", "acme.foundation", version="1.0.0",
    ))
    service.install(foundation_v2)
    service.install(dependent)

    with pytest.raises(ValueError, match="cannot be updated to 1.0.0"):
        service.install(foundation_v1)

    statuses = {status.mod_id: status for status in service.list_installed()}
    assert statuses["acme.foundation"].version == "2.0.0"
    assert statuses["acme.dependent"].enabled is True


def test_registry_blocks_missing_dependency_chains(tmp_path: Path) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    foundation = _content_package(
        tmp_path / "foundation", "acme.foundation", runtime=False,
        version="2.0.0",
    )
    middle = _content_package(
        tmp_path / "middle", "acme.middle", runtime=False,
        requires=("ACME.Foundation >= 2.0",),
    )
    leaf = _content_package(
        tmp_path / "leaf", "acme.leaf", runtime=False,
        requires=("acme.middle",),
    )
    service.install(ModManifest.load(foundation))
    service.install(ModManifest.load(middle))
    service.install(ModManifest.load(leaf))

    before = {
        entry["id"]: entry for entry in ExtensionRegistry(game).installed()
    }
    assert before["acme.middle"]["requires"] == ["acme.foundation>=2.0"]
    assert before["acme.leaf"]["requires"] == ["acme.middle"]

    (game / "scripts" / ".allin1" / "mods" / "acme.foundation.json").unlink()
    after = {
        entry["id"]: entry
        for entry in ExtensionRegistry(game).rebuild()["extensions"]
    }
    assert after["acme.middle"]["enabled"] is False
    assert "missing: acme.foundation>=2.0" in after["acme.middle"]["blocked_reason"]
    assert after["acme.leaf"]["enabled"] is False
    assert "unavailable: acme.middle" in after["acme.leaf"]["blocked_reason"]


@pytest.mark.parametrize(
    ("failure_mode", "reason_fragment"),
    (("disabled", "disabled: acme.foundation"),
     ("incompatible", "incompatible: acme.foundation>=2.0")),
)
def test_registry_blocks_disabled_or_incompatible_dependencies(
    tmp_path: Path, failure_mode: str, reason_fragment: str,
) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    foundation = _content_package(
        tmp_path / "foundation", "acme.foundation", runtime=False,
        version="2.0.0",
    )
    child = _content_package(
        tmp_path / "child", "acme.child", runtime=False,
        requires=("acme.foundation>=2.0",),
    )
    service.install(ModManifest.load(foundation))
    service.install(ModManifest.load(child))

    receipt_path = (
        game / "scripts" / ".allin1" / "mods" / "acme.foundation.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if failure_mode == "disabled":
        receipt["enabled"] = False
    else:
        receipt["version"] = "1.0.0"
        receipt["extension"]["version"] = "1.0.0"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    entries = {
        entry["id"]: entry
        for entry in ExtensionRegistry(game).rebuild()["extensions"]
    }
    assert entries["acme.child"]["enabled"] is False
    assert reason_fragment in entries["acme.child"]["blocked_reason"]


def test_registry_mutations_roll_back_when_rebuild_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    game = _game(tmp_path)
    manifest = ExtensionManifest.load(
        ROOT / "content" / "allin1-experimental-gameplay" / "allin1.content.json"
    )
    registry = ExtensionRegistry(game)
    registry.register_builtin(manifest, settings={"npc_physics": False})
    target = registry.builtin_root / f"{manifest.extension_id}.json"
    target_before = target.read_bytes()
    settings_before = registry.settings.path.read_bytes()

    def fail_rebuild():
        raise RuntimeError("forced registry rebuild failure")

    monkeypatch.setattr(registry, "rebuild", fail_rebuild)

    with pytest.raises(RuntimeError, match="forced registry rebuild failure"):
        registry.register_builtin(
            manifest, enabled=False, settings={"npc_physics": True},
        )
    assert target.read_bytes() == target_before
    assert registry.settings.path.read_bytes() == settings_before

    with pytest.raises(RuntimeError, match="forced registry rebuild failure"):
        registry.set_builtin_enabled(manifest.extension_id, False)
    assert target.read_bytes() == target_before

    with pytest.raises(RuntimeError, match="forced registry rebuild failure"):
        registry.unregister_builtin(manifest.extension_id)
    assert target.read_bytes() == target_before

    with pytest.raises(RuntimeError, match="forced registry rebuild failure"):
        registry.set_setting(manifest.extension_id, "npc_physics", True)
    assert registry.settings.path.read_bytes() == settings_before


@pytest.mark.parametrize("drift", ("missing", "tampered"))
def test_declared_catalog_files_are_receipt_hashed_and_verified(
    tmp_path: Path, drift: str,
) -> None:
    game = _game(tmp_path)
    package = _content_package(tmp_path, "acme.catalog", runtime=False)
    descriptor_path = package / "allin1.content.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["capabilities"].append("gbay.catalogs")
    descriptor["gbay"]["catalogs"] = [{
        "id": "weapons",
        "kind": "weapon",
        "source": "scripts/acme.catalog/content.json",
    }]
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    ModIntegrationService(game).install(ModManifest.load(package))
    registry = ExtensionRegistry(game)
    entry = registry.installed()[0]
    assert entry["catalog_files"] == [{
        "path": "scripts/acme.catalog/content.json",
        "sha256": hashlib.sha256(b"managed extension payload").hexdigest(),
    }]

    target = game / "scripts" / "acme.catalog" / "content.json"
    if drift == "missing":
        target.unlink()
    else:
        target.write_bytes(b"tampered catalog")
    blocked = registry.rebuild()["extensions"][0]
    assert blocked["enabled"] is False
    assert "GBAY catalog failed its receipt hash" in blocked["blocked_reason"]


@pytest.mark.parametrize(
    "path",
    (
        "scripts/addon:stream.dll",
        "scripts/CON.dll",
        "scripts/com1.data.dll",
        "scripts/bad?.dll",
        "scripts/folder./addon.dll",
        "scripts/folder /addon.dll",
        "scripts/addon.dll ",
        "scripts/control\x01.dll",
    ),
)
def test_runtime_paths_reject_windows_invalid_components(path: str) -> None:
    with pytest.raises(ValueError):
        RuntimeAssembly.from_dict({"path": path}, 1)


def test_builtin_dependency_cannot_be_disabled_under_enabled_package(tmp_path: Path) -> None:
    game = _game(tmp_path)
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    registry = ExtensionRegistry(game)
    registry.register_builtin(online)
    package = _content_package(
        tmp_path, "acme.gbay-addon", runtime=False,
        requires=("allin1.online-content>=0.5.0",),
    )
    ModIntegrationService(game).install(ModManifest.load(package))
    with pytest.raises(ValueError, match="required by: acme.gbay-addon"):
        registry.set_builtin_enabled("allin1.online-content", False)


def test_v2_manifest_is_fail_closed_and_owns_declared_runtime(tmp_path: Path) -> None:
    package = _content_package(tmp_path, "acme.validation")
    manifest_path = package / "mod.toml"
    original = manifest_path.read_text(encoding="utf-8")

    manifest_path.write_text(original.replace("schema_version = 2", "schema_version = 1"))
    with pytest.raises(ValueError, match="schema_version = 2"):
        ModManifest.load(manifest_path)

    manifest_path.write_text(original.replace("[allin1]\n", ""))
    with pytest.raises(ValueError, match=r"requires an \[allin1\]"):
        ModManifest.load(manifest_path)

    manifest_path.write_text(original, encoding="utf-8")
    descriptor_path = package / "allin1.content.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["runtime"]["assemblies"][0]["path"] = "scripts/SomeoneElse.dll"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(ValueError, match="not owned"):
        ModManifest.load(manifest_path)

    descriptor["runtime"]["assemblies"][0]["path"] = "scripts/acme.validation.dll"
    descriptor["systems"][0]["settings"][0]["config_key"] = "traffic.enabled"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(ValueError, match="may not bind launcher core config"):
        ModManifest.load(manifest_path)


def test_setting_type_and_range_validation_is_strict(tmp_path: Path) -> None:
    package = _content_package(tmp_path, "acme.settings", runtime=False)
    manifest = ModManifest.load(package).extension
    assert manifest is not None
    setting = manifest.setting("strength")
    assert setting.validate(5) == 5
    with pytest.raises(ValueError, match="integer"):
        setting.validate(True)
    with pytest.raises(ValueError, match="at most"):
        setting.validate(6)

    descriptor_path = package / "allin1.content.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["surprise_hook"] = "ignored-by-old-parser"
    with pytest.raises(ValueError, match="Unsupported content manifest field"):
        ExtensionManifest.from_dict(descriptor)


def test_content_cli_exposes_registry_and_requires_explicit_write_approval(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr("allin1.cli.setup_logging", lambda **_kwargs: None)
    game = _game(tmp_path)
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    ExtensionRegistry(game).register_builtin(online)
    config = Config.default()
    config.general.gta_path = str(game)
    config_path = tmp_path / "config.toml"
    config.save(config_path)
    runner = CliRunner()

    listed = runner.invoke(main, [
        "--config", str(config_path), "content", "list",
        "--gta-path", str(game), "--json-output",
    ])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["installed"][0]["id"] == "allin1.online-content"

    refused = runner.invoke(main, [
        "--config", str(config_path), "content", "disable",
        "allin1.online-content", "--gta-path", str(game),
    ], input="n\n")
    assert refused.exit_code == 1
    assert ExtensionRegistry(game).installed()[0]["enabled"] is True

    changed = runner.invoke(main, [
        "--config", str(config_path), "content", "set",
        "allin1.online-content", "traffic_enabled", "false",
        "--gta-path", str(game), "--yes",
    ])
    assert changed.exit_code == 0, changed.output
    assert Config.load(config_path).traffic.enabled is False
    assert ExtensionRegistry(game).installed()[0]["settings"]["traffic_enabled"] is False


def test_content_cli_explicit_game_path_controls_runtime_config_target(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr("allin1.cli.setup_logging", lambda **_kwargs: None)
    configured_game = _game(tmp_path / "configured")
    explicit_game = _game(tmp_path / "explicit")
    online = ExtensionManifest.load(
        ROOT / "content" / "allin1-online-content" / "allin1.content.json"
    )
    ExtensionRegistry(explicit_game).register_builtin(online)
    config = Config.default()
    config.general.gta_path = str(configured_game)
    config_path = tmp_path / "config.toml"
    config.save(config_path)
    for game in (configured_game, explicit_game):
        scripts = game / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "ALLIN1.dll").write_bytes(b"runtime")
        config.save(scripts / "ALLIN1.toml")

    result = CliRunner().invoke(main, [
        "--config", str(config_path), "content", "set",
        "allin1.online-content", "traffic_enabled", "false",
        "--gta-path", str(explicit_game), "--yes",
    ])

    assert result.exit_code == 0, result.output
    assert Config.load(explicit_game / "scripts" / "ALLIN1.toml").traffic.enabled is False
    assert Config.load(configured_game / "scripts" / "ALLIN1.toml").traffic.enabled is True
    assert ExtensionRegistry(explicit_game).installed()[0]["settings"][
        "traffic_enabled"
    ] is False


def test_requirement_parser_and_version_matching_are_fail_closed() -> None:
    requirement = _ContentRequirement.parse(" ACME.Foundation >= 1.2 ")
    assert requirement.normalized() == "acme.foundation>=1.2"
    assert requirement.accepts("1.2.0") is True
    assert requirement.accepts("2") is True
    assert requirement.accepts("1.1.9") is False
    assert requirement.accepts("broken") is False
    assert _ContentRequirement.parse("acme.foundation").accepts("anything") is True
    assert _ContentRequirement.parse("acme.foundation==1.2").accepts("1.2.0") is True
    assert _ContentRequirement.parse("acme.foundation==1.2").accepts("1.2.1") is False
    assert _content_requirements(None) == ()
    with pytest.raises(ValueError, match="must be strings"):
        _ContentRequirement.parse(12)
    with pytest.raises(ValueError, match="Invalid ALLIN1 content requirement"):
        _ContentRequirement.parse("not a valid requirement!")
    with pytest.raises(ValueError, match="must be an array"):
        _content_requirements("acme.foundation")
    with pytest.raises(ValueError, match="duplicate requirements"):
        _content_requirements(["acme.foundation", "ACME.Foundation>=1"])


def test_setting_descriptor_validation_covers_every_type_and_bound() -> None:
    valid = {
        "key": "mode",
        "label": "Mode",
        "type": "choice",
        "default": "safe",
        "choices": ["safe", "fast", "safe", ""],
        "description": "Choose a mode",
        "group": "Advanced",
    }
    setting = ExtensionSetting.from_dict(valid, "setting")
    assert setting.validate("fast") == "fast"
    assert setting.to_dict()["choices"] == ["safe", "fast"]
    with pytest.raises(ValueError, match="one of"):
        setting.validate("unknown")
    with pytest.raises(ValueError, match="must be text"):
        setting.validate(1)

    number = ExtensionSetting.from_dict({
        "key": "scale", "label": "Scale", "type": "number",
        "default": 1.5, "minimum": 1, "maximum": 2, "step": 0.25,
        "config_key": "traffic.cleanup_distance",
    }, "setting")
    serialized = number.to_dict()
    assert serialized["minimum"] == 1.0
    assert serialized["maximum"] == 2.0
    assert serialized["step"] == 0.25
    assert serialized["config_key"] == "traffic.cleanup_distance"
    with pytest.raises(ValueError, match="must be a number"):
        number.validate(True)
    with pytest.raises(ValueError, match="must be finite"):
        number.validate(float("inf"))
    with pytest.raises(ValueError, match="at least"):
        number.validate(0.5)

    boolean = ExtensionSetting.from_dict({
        "key": "enabled", "label": "Enabled", "type": "boolean",
        "default": True,
    }, "setting")
    with pytest.raises(ValueError, match="true or false"):
        boolean.validate(1)

    invalid_cases = [
        (None, "must be an object"),
        ({"key": "Bad Key", "label": "Bad", "type": "string", "default": ""},
         "safe lowercase"),
        ({"key": "bad", "label": "Bad", "type": "opaque", "default": None},
         "type must be one of"),
        ({"key": "bad", "label": "Bad", "type": "choice", "default": "x"},
         "choices is required"),
        ({"key": "bad", "label": "Bad", "type": "string", "default": "x",
          "choices": ["x"]}, "valid only"),
        ({"key": "bad", "label": "Bad", "type": "number", "default": 1,
          "minimum": True}, "finite number"),
        ({"key": "bad", "label": "Bad", "type": "number", "default": 1,
          "maximum": float("nan")}, "finite number"),
        ({"key": "bad", "label": "Bad", "type": "number", "default": 1,
          "minimum": 2, "maximum": 1}, "must not exceed"),
        ({"key": "bad", "label": "Bad", "type": "number", "default": 1,
          "step": 0}, "must be positive"),
        ({"key": "bad", "label": "Bad", "type": "string", "default": "x",
          "minimum": 0}, "numeric bounds"),
        ({"key": "bad", "label": "Bad", "type": "string", "default": "x",
          "config_key": "unknown.field"}, "not a supported"),
        ({"key": "bad", "label": "Bad", "type": "string", "default": object()},
         "must be JSON values"),
        ({"key": "bad", "label": "Bad", "type": "integer", "default": True},
         "must be an integer"),
        ({"key": "bad", "label": "Bad", "type": "string", "default": "x",
          "choices": "x"}, "array of strings"),
        ({"key": "bad", "type": "string", "default": "x"},
         "must be a non-empty string"),
    ]
    for payload, message in invalid_cases:
        with pytest.raises(ValueError, match=message):
            ExtensionSetting.from_dict(payload, "setting")


def test_system_gbay_and_runtime_descriptors_validate_shape() -> None:
    setting = {
        "key": "enabled", "label": "Enabled", "type": "boolean",
        "default": True,
    }
    system = ExtensionSystem.from_dict({
        "id": "acme-system", "name": "ACME", "category": "",
        "experimental": True, "enabled_by_default": False,
        "settings": [setting],
    }, 1)
    assert system.to_dict()["category"] == "Other"
    with pytest.raises(ValueError, match="must be an object"):
        ExtensionSystem.from_dict([], 1)
    with pytest.raises(ValueError, match="settings must be an array"):
        ExtensionSystem.from_dict({"id": "acme", "name": "ACME", "settings": {}}, 1)
    with pytest.raises(ValueError, match="duplicate setting keys"):
        ExtensionSystem.from_dict({
            "id": "acme", "name": "ACME", "settings": [setting, setting],
        }, 1)
    with pytest.raises(ValueError, match="boolean flags"):
        ExtensionSystem.from_dict({
            "id": "acme", "name": "ACME", "experimental": "yes",
        }, 1)

    section = GbaySection.from_dict({
        "id": "tools", "label": "Tools", "route": "acme:tools", "order": 5,
    }, 1)
    assert section.to_dict()["order"] == 5
    with pytest.raises(ValueError, match="must be an object"):
        GbaySection.from_dict([], 1)
    with pytest.raises(ValueError, match="order must be an integer"):
        GbaySection.from_dict({
            "id": "tools", "label": "Tools", "route": "tools", "order": True,
        }, 1)
    with pytest.raises(ValueError, match="route is invalid"):
        GbaySection.from_dict({
            "id": "tools", "label": "Tools", "route": "Not Valid",
        }, 1)

    catalog = GbayCatalog.from_dict({
        "id": "tools", "kind": "gear", "source": "scripts/acme/tools.json",
    }, 1)
    assert catalog.to_dict()["source"] == "scripts/acme/tools.json"
    with pytest.raises(ValueError, match="must be an object"):
        GbayCatalog.from_dict([], 1)
    with pytest.raises(ValueError, match="kind must be one of"):
        GbayCatalog.from_dict({"id": "tools", "kind": "unknown", "source": "x.json"}, 1)
    with pytest.raises(ValueError, match="must be a JSON file"):
        GbayCatalog.from_dict({"id": "tools", "kind": "gear", "source": "x.txt"}, 1)

    assembly = RuntimeAssembly.from_dict({
        "path": "scripts/acme.dll", "entry_point": "Acme.Entry",
    }, 1)
    assert assembly.to_dict()["entry_point"] == "Acme.Entry"
    with pytest.raises(ValueError, match="must be an object"):
        RuntimeAssembly.from_dict([], 1)
    with pytest.raises(ValueError, match="DLL below scripts"):
        RuntimeAssembly.from_dict({"path": "plugins/acme.dll"}, 1)
    with pytest.raises(ValueError, match="must not be empty"):
        RuntimeAssembly.from_dict({"path": "scripts/acme.dll", "entry_point": " "}, 1)


def test_manifest_validation_rejects_ambiguous_or_undeclared_content() -> None:
    cases: list[tuple[object, str]] = [
        ([], "must be a JSON object"),
    ]
    bad = _descriptor()
    bad["schema_version"] = 2
    cases.append((bad, "schema_version"))
    bad = _descriptor()
    bad["api_version"] = 2
    cases.append((bad, "api_version"))
    bad = _descriptor()
    bad["systems"] = {}
    cases.append((bad, "systems must be an array"))
    bad = _descriptor()
    bad["systems"].append(deepcopy(bad["systems"][0]))
    cases.append((bad, "duplicate system ids"))
    bad = _descriptor()
    other = deepcopy(bad["systems"][0])
    other["id"] = "other-system"
    bad["systems"].append(other)
    cases.append((bad, "setting keys must be unique"))
    bad = _descriptor()
    bad["gbay"] = []
    cases.append((bad, "gbay must be an object"))
    bad = _descriptor()
    bad["gbay"] = {"sections": {}, "catalogs": []}
    cases.append((bad, "sections and catalogs must be arrays"))
    section = {"id": "tools", "label": "Tools", "route": "tools"}
    bad = _descriptor()
    bad["capabilities"].append("gbay.sections")
    bad["gbay"]["sections"] = [section, section]
    cases.append((bad, "duplicate GBAY section ids"))
    catalog = {"id": "gear", "kind": "gear", "source": "gear.json"}
    bad = _descriptor()
    bad["capabilities"].append("gbay.catalogs")
    bad["gbay"]["catalogs"] = [catalog, catalog]
    cases.append((bad, "duplicate GBAY catalog ids"))
    bad = _descriptor()
    bad["runtime"] = []
    cases.append((bad, "runtime must be an object"))
    bad = _descriptor()
    bad["runtime"] = {"assemblies": {}}
    cases.append((bad, "runtime assemblies must be an array"))
    bad = _descriptor()
    bad["runtime"]["assemblies"] = [
        {"path": "scripts/acme.dll"}, {"path": "SCRIPTS/ACME.dll"},
    ]
    cases.append((bad, "duplicate runtime assemblies"))
    bad = _descriptor()
    bad["capabilities"] = ["bad capability"]
    cases.append((bad, "Invalid extension capability"))
    bad = _descriptor()
    bad["capabilities"] = ["launcher.settings"]
    bad["gbay"]["sections"] = [section]
    cases.append((bad, "require the gbay.sections"))
    bad = _descriptor()
    bad["capabilities"] = ["launcher.settings"]
    bad["gbay"]["catalogs"] = [catalog]
    cases.append((bad, "require the gbay.catalogs"))
    bad = _descriptor()
    bad["capabilities"] = []
    cases.append((bad, "Typed system settings require"))
    bad = _descriptor()
    bad["capabilities"] = []
    bad["systems"] = []
    cases.append((bad, "must contribute at least one"))
    bad = _descriptor()
    bad["id"] = "x"
    cases.append((bad, "must be 2-96"))

    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            ExtensionManifest.from_dict(payload)
    with pytest.raises(ValueError, match="registry entry must be an object"):
        ExtensionManifest.from_registry_entry([])


def test_manifest_loading_catalog_discovery_and_ownership_fail_closed(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        ExtensionManifest.load(missing)
    invalid = tmp_path / "invalid.content.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid ALLIN1 content manifest"):
        ExtensionManifest.load(invalid)
    directory = tmp_path / "directory"
    directory.mkdir()
    (directory / "allin1.content.json").write_text(
        json.dumps(_descriptor()), encoding="utf-8",
    )
    manifest = ExtensionManifest.load(directory)
    assert ExtensionManifest.from_registry_entry(manifest.to_dict()).to_dict() == manifest.to_dict()
    with pytest.raises(KeyError, match="Unknown setting"):
        manifest.setting("missing")

    owned = _descriptor()
    owned["runtime"]["assemblies"] = [{"path": "scripts/acme.dll"}]
    owned["capabilities"].append("gbay.catalogs")
    owned["gbay"]["catalogs"] = [{
        "id": "gear", "kind": "gear", "source": "scripts/acme/gear.json",
    }]
    owned_manifest = ExtensionManifest.from_dict(owned)
    with pytest.raises(ValueError, match="Runtime assembly is not owned"):
        owned_manifest.validate_package_destinations(["scripts/acme/gear.json"])
    with pytest.raises(ValueError, match="GBAY catalog is not owned"):
        owned_manifest.validate_package_destinations(["scripts/acme.dll"])
    owned_manifest.validate_package_destinations([
        "SCRIPTS\\ACME.DLL", "scripts/acme/gear.json",
    ])

    assert ExtensionCatalog(tmp_path / "absent").discover() == []
    catalog_root = tmp_path / "catalog"
    (catalog_root / "one").mkdir(parents=True)
    (catalog_root / "two").mkdir(parents=True)
    for child in ("one", "two"):
        (catalog_root / child / "allin1.content.json").write_text(
            json.dumps(_descriptor()), encoding="utf-8",
        )
    with pytest.raises(ValueError, match="duplicate package ids"):
        ExtensionCatalog(catalog_root).discover()


def test_namespaced_settings_recover_from_bad_values_and_reject_bad_files(
    tmp_path: Path,
) -> None:
    manifest = ExtensionManifest.from_dict(_descriptor())
    path = tmp_path / "settings.json"
    store = ExtensionSettingsStore(path)
    assert store.effective(manifest) == {"strength": 2}
    assert store.update(manifest, {"strength": 4}) == {"strength": 4}
    assert path.with_suffix(".json.bak").is_file() is False
    assert store.update(manifest, {"strength": 3}) == {"strength": 3}
    assert path.with_suffix(".json.bak").is_file()

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["extensions"][manifest.extension_id]["strength"] = 100
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.effective(manifest) == {"strength": 2}
    store.remove("not-installed")
    store.remove(manifest.extension_id)
    assert store.effective(manifest) == {"strength": 2}

    invalid_payloads = [
        ("{", "Invalid extension settings file"),
        (json.dumps({"schema_version": 999, "extensions": {}}), "Unsupported"),
        (json.dumps({"schema_version": 1, "extensions": []}), "extensions object"),
        (json.dumps({"schema_version": 1, "extensions": {"x": {}}}),
         "invalid package namespace"),
        (json.dumps({"schema_version": 1, "extensions": {"valid.id": []}}),
         "invalid package namespace"),
    ]
    for content, message in invalid_payloads:
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            store.effective(manifest)


def test_core_config_bindings_ignore_unbound_settings_and_reject_drift() -> None:
    unbound = ExtensionManifest.from_dict(_descriptor())
    empty = SimpleNamespace()
    assert settings_from_config(unbound, empty) == {}
    apply_settings_to_config(unbound, empty, {"strength": 3})

    bound_data = _descriptor()
    bound_data["systems"][0]["settings"][0]["config_key"] = "traffic.enabled"
    bound_data["systems"][0]["settings"][0]["type"] = "boolean"
    bound_data["systems"][0]["settings"][0]["default"] = True
    bound_data["systems"][0]["settings"][0].pop("minimum")
    bound_data["systems"][0]["settings"][0].pop("maximum")
    bound = ExtensionManifest.from_dict(bound_data)
    with pytest.raises(ValueError, match="missing config field"):
        settings_from_config(bound, empty)
    with pytest.raises(ValueError, match="Unknown core config binding"):
        apply_settings_to_config(bound, empty, {"strength": False})


def test_registry_read_and_builtin_edge_cases_fail_closed(tmp_path: Path) -> None:
    game = _game(tmp_path)
    registry = ExtensionRegistry(game)
    assert registry.read()["extensions"] == []
    with pytest.raises(FileNotFoundError, match="not installed"):
        registry.set_builtin_enabled("acme.missing", True)
    with pytest.raises(KeyError, match="not installed"):
        registry.set_setting("acme.missing", "value", True)

    registry.registry_path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid ALLIN1 extension registry"):
        registry.read()
    registry.registry_path.write_text(json.dumps({
        "schema_version": 1, "api_version": 1, "extensions": {},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported ALLIN1 extension registry"):
        registry.read()

    manifest = ExtensionManifest.from_dict(_descriptor())
    registry.builtin_root.mkdir(parents=True, exist_ok=True)
    target = registry.builtin_root / f"{manifest.extension_id}.json"
    target.write_text("{", encoding="utf-8")
    registry.register_builtin(manifest, enabled=None)
    assert registry.installed()[0]["enabled"] is True
    registry.unregister_builtin(manifest.extension_id, force=True)
    assert registry.installed() == []


def test_corrupt_or_ambiguous_receipts_never_authorize_content(tmp_path: Path) -> None:
    game = _game(tmp_path)
    registry = ExtensionRegistry(game)
    registry.receipt_root.mkdir(parents=True)
    manifest = ExtensionManifest.from_dict(_descriptor()).to_dict()
    receipts = {
        "bad-json.json": "{",
        "no-extension.json": json.dumps({"id": "acme.none"}),
        "mismatch.json": json.dumps({
            "id": "acme.other", "extension": manifest, "files": [],
        }),
        "self-dependency.json": json.dumps({
            "id": "acme.extension", "extension": manifest,
            "requires": ["acme.extension"], "files": [],
        }),
        "invalid-requirements.json": json.dumps({
            "id": "acme.extension", "extension": manifest,
            "requires": "acme.other", "files": [],
        }),
    }
    for name, content in receipts.items():
        (registry.receipt_root / name).write_text(content, encoding="utf-8")
    assert registry.installed() == []


def test_missing_receipt_hashes_block_runtime_and_catalog_authorization(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    service = ModIntegrationService(game)
    runtime_package = _content_package(tmp_path / "runtime", "acme.runtime")
    service.install(ModManifest.load(runtime_package))
    receipt_path = game / "scripts" / ".allin1" / "mods" / "acme.runtime.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"][0].pop("sha256")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    runtime_entry = ExtensionRegistry(game).installed()[0]
    assert runtime_entry["enabled"] is False
    assert "Runtime assembly lacks a receipt hash" in runtime_entry["blocked_reason"]

    game = _game(tmp_path / "catalog-game")
    service = ModIntegrationService(game)
    catalog_package = _content_package(
        tmp_path / "catalog", "acme.catalog-only", runtime=False,
    )
    descriptor_path = catalog_package / "allin1.content.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["capabilities"].append("gbay.catalogs")
    descriptor["gbay"]["catalogs"] = [{
        "id": "gear", "kind": "gear",
        "source": "scripts/acme.catalog-only/content.json",
    }]
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    service.install(ModManifest.load(catalog_package))
    receipt_path = (
        game / "scripts" / ".allin1" / "mods" / "acme.catalog-only.json"
    )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"][0]["sha256"] = "not-a-hash"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    catalog_entry = ExtensionRegistry(game).installed()[0]
    assert catalog_entry["enabled"] is False
    assert "GBAY catalog lacks a receipt hash" in catalog_entry["blocked_reason"]


def test_duplicate_builtin_and_package_ids_are_rejected_and_rolled_back(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    package = _content_package(tmp_path, "acme.duplicate")
    ModIntegrationService(game).install(ModManifest.load(package))
    descriptor = _descriptor()
    descriptor["id"] = "acme.duplicate"
    descriptor["name"] = "Built-in Duplicate"
    registry = ExtensionRegistry(game)
    with pytest.raises(ValueError, match="Duplicate installed ALLIN1 content id"):
        registry.register_builtin(ExtensionManifest.from_dict(descriptor))
    assert not (registry.builtin_root / "acme.duplicate.json").exists()
    assert registry.installed()[0]["source"] == "package"


def test_extension_paths_and_string_settings_reject_ambiguous_input() -> None:
    with pytest.raises(ValueError, match="non-empty relative path"):
        RuntimeAssembly.from_dict({"path": None}, 1)
    with pytest.raises(ValueError, match="whitespace"):
        RuntimeAssembly.from_dict({"path": " scripts/acme.dll"}, 1)
    text = ExtensionSetting.from_dict({
        "key": "label", "label": "Label", "type": "string", "default": "ACME",
    }, "setting")
    assert text.validate("updated") == "updated"


def test_dependency_guard_skips_malformed_disabled_and_unrelated_receipts(
    tmp_path: Path,
) -> None:
    game = _game(tmp_path)
    registry = ExtensionRegistry(game)
    manifest = ExtensionManifest.from_dict(_descriptor())
    registry.register_builtin(manifest)
    registry.receipt_root.mkdir(parents=True, exist_ok=True)
    receipts = {
        "corrupt.json": "{",
        "disabled.json": json.dumps({
            "id": "acme.disabled", "enabled": False,
            "requires": [manifest.extension_id],
        }),
        "bad-requires.json": json.dumps({
            "id": "acme.bad", "enabled": True, "requires": "not-a-list",
        }),
        "unrelated.json": json.dumps({
            "id": "acme.unrelated", "enabled": True,
            "requires": ["somewhere.else>=1"],
        }),
    }
    for name, content in receipts.items():
        (registry.receipt_root / name).write_text(content, encoding="utf-8")
    registry.set_builtin_enabled(manifest.extension_id, False)
    assert registry.read()["extensions"][0]["enabled"] is False
