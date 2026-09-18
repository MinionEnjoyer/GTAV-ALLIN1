"""Content parity uses real registry state, without a Tk presentation layer."""
import json

import pytest

from allin1.desktop_service import serializable
from allin1.extensions import ExtensionRegistry
from allin1.mods import ModIntegrationService, ModManifest
from tests.test_desktop_service import service, apply, PROJECT
from tests.test_extensions import _content_package


def builtin(service):
    target = service.project / "content/test-fixture/allin1.content.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "schema_version": 1,
        "api_version": 1,
        "id": "test.fixture-content",
        "name": "Synthetic Content Fixture",
        "version": "1.0.0",
        "description": "Non-shipping desktop content-settings fixture.",
        "capabilities": ["launcher.settings"],
        "systems": [{
            "id": "fixture-settings",
            "name": "Fixture Settings",
            "category": "Testing",
            "experimental": False,
            "enabled_by_default": False,
            "settings": [{
                "key": "enabled",
                "label": "Fixture enabled",
                "type": "boolean",
                "default": True,
                "config_key": "script.enable_logging",
            }],
        }],
        "gbay": {"sections": [], "catalogs": []},
        "runtime": {"assemblies": []},
    }, indent=2) + "\n", encoding="utf-8")
    return target


def test_preinstall_preferences_are_available_without_game_write_authority(service):
    builtin(service)
    service.allow_game_writes = False
    config = serializable(service.config())
    config["general"]["gta_enhanced_path"] = "auto"
    config["general"]["gta_path"] = "auto"
    before = service.tree_identity(service.project)
    content = service.inspect({"module": "content", "config": config})["content"]
    assert content[0]["installed"] is False
    assert content[0]["schema_settings"][0]["label"]
    result = apply(service, "save_content_preferences", id=content[0]["id"], settings={"enabled": False}, config=config)
    assert not result["result"]["game_write"]
    assert result["saved_config"]["script"]["enable_logging"] is False
    assert service.tree_identity(service.project) == before
    assert not (service.project.parent / "Disposable Enhanced game/scripts").exists()


@pytest.mark.parametrize("values", [None, [], {}, {"enabled": 1}, {"unknown": True}])
def test_preinstall_invalid_values_cannot_create_preferences(service, values):
    builtin(service)
    before = service.tree_identity(service.project.parent)
    with pytest.raises((ValueError, KeyError)):
        service.review({"action": "save_content_preferences", "id": "test.fixture-content", "settings": values})
    assert service.tree_identity(service.project.parent) == before


def test_preinstall_review_detects_manifest_drift(service):
    source = builtin(service)
    review = service.review({"action": "save_content_preferences", "id": "test.fixture-content", "settings": {"enabled": False}})
    source.write_text(source.read_text().replace("Fixture enabled", "Changed after review"))
    with pytest.raises(ValueError, match="changed"):
        service.apply({"confirmed": True, "review_id": review["review_id"], "review_sha256": review["review_sha256"]})
    assert not service.state.exists()


def test_third_party_content_discovery_settings_and_enable_disable(service, tmp_path):
    package = _content_package(tmp_path / "third-party", "acme.weather", runtime=False)
    domain = ModIntegrationService(service.game(service.config()))
    domain.install(ModManifest.load(package / "mod.toml"))
    before = service.tree_identity(service.game(service.config()))
    rows = service.inspect({"module": "content"})["content"]
    assert len(rows) == 1 and rows[0]["id"] == "acme.weather"
    assert rows[0]["source"] != "built-in" and rows[0]["installed"]
    assert rows[0]["schema_settings"][0]["minimum"] == 0
    assert service.tree_identity(service.game(service.config())) == before
    apply(service, "content_settings", id="acme.weather", settings={"strength": 4})
    assert service.inspect({"module": "content"})["content"][0]["settings"]["strength"] == 4
    apply(service, "content_disable", id="acme.weather")
    assert not domain.list_installed()[0].enabled
    apply(service, "content_enable", id="acme.weather")
    assert domain.list_installed()[0].enabled


def test_managed_package_without_extension_has_real_content_lifecycle_controls(service, tmp_path):
    package = tmp_path / "corefx-base"
    package.mkdir()
    (package / "corefx.ini").write_text("preset=corefx\n", encoding="utf-8")
    (package / "mod.toml").write_text(
        """schema_version = 1
id = "corefx-legacy-base"
name = "CoreFX Legacy Base"
version = "1.2"
type = "config"
description = "Managed visual package."
editions = ["legacy", "enhanced"]
dependencies = []
conflicts = []

[[files]]
source = "corefx.ini"
destination = "scripts/CoreFX/corefx.ini"
""",
        encoding="utf-8",
    )
    domain = ModIntegrationService(service.game(service.config()))
    domain.install(ModManifest.load(package / "mod.toml"))

    rows = service.inspect({"module": "content"})["content"]
    row = next(item for item in rows if item["id"] == "corefx-legacy-base")
    assert row["managed_package"] is True
    assert row["enabled"] is True
    assert row["systems"][0]["settings"][0]["key"] == "enabled"
    assert row["settings"] == {"enabled": True}
    assert row["schema_settings"][0]["type"] == "boolean"

    with pytest.raises(ValueError, match="no package-owned settings"):
        service.review({
            "action": "content_settings",
            "id": "corefx-legacy-base",
            "settings": {"preset": "other"},
        })
    apply(service, "content_disable", id="corefx-legacy-base")
    assert domain.list_installed()[0].enabled is False
    apply(service, "content_enable", id="corefx-legacy-base")
    assert domain.list_installed()[0].enabled is True


def test_unsaved_bound_config_wins_over_installed_registry_value(service):
    from allin1.extensions import ExtensionManifest
    source = builtin(service)
    registry = ExtensionRegistry(service.game(service.config()))
    registry.register_builtin(ExtensionManifest.load(source))
    config = serializable(service.config())
    config["script"]["enable_logging"] = False
    before = service.tree_identity(service.project.parent)
    assert service.inspect({"module": "content", "config": config})["content"][0]["settings"]["enabled"] is False
    assert service.tree_identity(service.project.parent) == before
