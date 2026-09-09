"""Real package inspector/install workflows in disposable game and library roots."""
import json
import shutil
import zipfile

import pytest

from allin1.desktop_service import LauncherService
from allin1.extensions import ExtensionRegistry
from tests.test_desktop_service import PROJECT, apply, service
from tests.test_extensions import _content_package
from tests.test_edition_bundles import make_bundle, archive_bundle
from tests.test_component_bundles import write_bundle, zip_bundle


def test_collection_inspection_and_review_bind_one_component(service, tmp_path):
    game = service.game(service.config())
    (game / "GTA5_Enhanced.exe").rename(game / "GTA5.exe")
    source = zip_bundle(write_bundle(tmp_path / "components"), tmp_path / "components.zip")
    before = service.tree_identity(tmp_path)
    inspection = service.inspect({"module": "package", "source": str(source)})
    assert service.tree_identity(tmp_path) == before
    item = inspection["package"]
    assert item["schema_version"] == 6 and item["selected_edition"] == "legacy"
    assert [c["id"] for c in item["components"]] == ["legacy.part0", "legacy.part1"]
    for component in (None, "enhanced.part0", "unknown"):
        with pytest.raises(ValueError, match="Select one component"):
            service.review({"action": "package_install", "source": str(source), "component_id": component})
    review = service.review({"action": "package_install", "source": str(source),
                              "component_id": "legacy.part1", "expected_state_sha256": inspection["state_sha256"]})
    assert review["package"]["id"] == "legacy.part1"
    assert review["package"]["bundle"]["selected_edition"] == "legacy"
    service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    game = service.game(service.config())
    assert (game / "scripts/part1.ini").read_bytes() == b"legacy-1"
    assert not (game / "scripts/part0.ini").exists()
    refreshed = service.inspect({"module": "package", "source": str(source)})["package"]["components"]
    assert not refreshed[0]["installed"] and refreshed[1]["installed"]


def test_collection_change_after_review_cannot_apply(service, tmp_path):
    game = service.game(service.config())
    (game / "GTA5_Enhanced.exe").rename(game / "GTA5.exe")
    root = write_bundle(tmp_path / "components")
    source = zip_bundle(root, tmp_path / "components.zip")
    review = service.review({"action": "package_install", "source": str(source), "component_id": "legacy.part0"})
    (root / "enhanced/0/payload.bin").write_bytes(b"changed")
    zip_bundle(root, source)
    with pytest.raises(ValueError, match="changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert not (service.game(service.config()) / "scripts/part0.ini").exists()


@pytest.mark.parametrize("kind", ["folder", "manifest", "archive"])
def test_inspect_initial_settings_and_reinstall_preserve_preferences(service, tmp_path, kind):
    package = _content_package(tmp_path, "acme.react", runtime=False)
    source = package if kind == "folder" else package / "mod.toml"
    if kind == "archive":
        source = tmp_path / "package with spaces.zip"
        with zipfile.ZipFile(source, "w") as archive:
            for path in package.iterdir(): archive.write(path, path.name)
    before = service.tree_identity(tmp_path)
    inspection = service.inspect({"module": "package", "source": str(source)})
    assert service.tree_identity(tmp_path) == before
    assert inspection["source"] == str(source)
    assert inspection["package"]["settings"] == {"strength": 2}
    assert inspection["package"]["extension"]["systems"][0]["settings"][0]["label"] == "Strength"
    assert "manifest_path" not in json.dumps(inspection["package"])
    apply(service, "package_install", source=str(source), settings={"strength": 4},
          expected_state_sha256=inspection["state_sha256"])
    registry = ExtensionRegistry(service.game(service.config()))
    assert registry.inspect()["extensions"][0]["settings"] == {"strength": 4}
    again = service.inspect({"module": "package", "source": str(source)})
    assert again["package"]["settings"] == {"strength": 4}
    apply(service, "package_install", source=str(source), settings=again["package"]["settings"],
          expected_state_sha256=again["state_sha256"])
    assert registry.inspect()["extensions"][0]["settings"] == {"strength": 4}


@pytest.mark.parametrize("values", [{"strength": 6}, {"strength": True}, {"unknown": 1}, [], "invalid"])
def test_invalid_initial_settings_rejected_before_issuing_review(service, tmp_path, values):
    package = _content_package(tmp_path, "acme.invalid", runtime=False)
    before = service.tree_identity(tmp_path)
    with pytest.raises((ValueError, KeyError)):
        service.review({"action": "package_install", "source": str(package), "settings": values})
    assert service.reviews == {}
    assert service.tree_identity(tmp_path) == before


@pytest.mark.parametrize("changed", ["payload", "descriptor", "installation"])
def test_changed_inspection_cannot_be_reviewed(service, tmp_path, changed):
    package = _content_package(tmp_path, "acme.stale", runtime=False)
    source = str(package / "mod.toml")
    inspection = service.inspect({"module": "package", "source": source})
    if changed == "payload": (package / "payload.bin").write_bytes(b"changed")
    elif changed == "descriptor":
        path = package / "allin1.content.json"
        path.write_text(path.read_text() + "\n")
    else:
        target = service.game(service.config()) / "scripts/ALLIN1.toml"
        target.parent.mkdir(); target.write_text("# external edit")
    before = service.tree_identity(tmp_path)
    with pytest.raises(ValueError, match="changed"):
        service.review({"action": "package_install", "source": source,
                        "expected_state_sha256": inspection["state_sha256"], "settings": {"strength": 4}})
    assert service.reviews == {}
    assert service.tree_identity(tmp_path) == before


def test_package_library_uses_explicit_shared_sdk_export_location(service, tmp_path):
    shared = tmp_path / "Shared SDK packages"
    _content_package(shared, "acme.shared", runtime=False)
    service.package_library_root = shared
    inspection = service.inspect({"module": "mods"})
    assert [item["mod_id"] for item in inspection["packages"]] == ["acme.shared"]
    assert not service.state.exists()
    # An explicitly isolated host must not inherit a machine-wide package library.
    isolated = LauncherService(service.project, tmp_path / "isolated state")
    assert isolated.inspect({"module": "mods"})["packages"] == []


def test_included_content_and_sdk_examples_are_discoverable_without_writes(service, tmp_path):
    shutil.copytree(PROJECT / "content", service.project / "content")
    shutil.copytree(PROJECT / "sdk/examples", service.project / "sdk/examples")
    before = service.tree_identity(tmp_path)
    inspection = service.inspect({"module": "mods"})
    assert len(inspection["builtin_packages"]) == 2
    assert all(not item["installed"] for item in inspection["builtin_packages"])
    assert any(item["name"] == "ALLIN1 Colored Smoke Grenades" for item in inspection["sdk_examples"])
    assert service.tree_identity(tmp_path) == before


def test_retired_installed_preview_setting_is_not_presented_or_resaved(service, monkeypatch):
    shutil.copytree(PROJECT / "content", service.project / "content")
    monkeypatch.setattr(ExtensionRegistry, "inspect", lambda self: {"extensions": [{
        "id": "allin1.online-content", "enabled": True, "source": "built-in",
        "settings": {"preview_artwork": False, "free_purchases": True},
    }]})
    rows = service.inspect({"module": "mods"})["builtin_packages"]
    online = next(row for row in rows if row["id"] == "allin1.online-content")
    assert "preview_artwork" not in online["settings"]
    assert not any(setting["key"] == "preview_artwork" for setting in online["schema_settings"])
    assert "free_purchases" in online["settings"]


def test_edition_bundle_review_and_install(service, tmp_path):
    package = make_bundle(tmp_path / "bundle")
    source = archive_bundle(package, tmp_path / "bundle.zip")
    game = service.game(service.config())
    expected = b"enhanced" if (game / "GTA5_Enhanced.exe").exists() else b"legacy"
    inspection = service.inspect({"module": "package", "source": str(source)})
    assert inspection["package"]["selected_edition"] == expected.decode()
    assert inspection["package"]["bundle_editions"] == ["legacy", "enhanced"]
    apply(service, "package_install", source=str(source), settings={},
          expected_state_sha256=inspection["state_sha256"])
    assert (game / "scripts/test.ini").read_bytes() == expected


def test_edition_bundle_payload_change_invalidates_review(service, tmp_path):
    package = make_bundle(tmp_path / "bundle")
    source = archive_bundle(package, tmp_path / "bundle.zip")
    review = service.review({"action": "package_install", "source": str(source)})
    (package / "enhanced/payload.bin").write_bytes(b"changed")
    archive_bundle(package, source)
    with pytest.raises(ValueError, match="changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"],
                       "confirmed": True})
    assert not (service.game(service.config()) / "scripts/test.ini").exists()
