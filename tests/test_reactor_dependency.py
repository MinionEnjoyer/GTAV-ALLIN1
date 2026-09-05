"""Offline installer regression fixtures; never write to a real GTA install."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import zipfile

import pytest

from allin1 import reactor_dependency as dep


def put(root, name, payload):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload if isinstance(payload, bytes) else payload.encode())
    return path


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def archive_fixture(tmp_path, enhanced=False, *, extra=None):
    files = {name: b"MZ-native-fixture" for name in dep.ROOT_ASIS}
    files.update({
        "scripts/ReactorV/RageWebUI.Script.dll": b"script",
        "scripts/ReactorV/RageWebUI.Core.dll": b"core",
        "plugins/ReactorV/RageWebUI.Core.dll": b"core",
        "plugins/ReactorV/legal/LICENSE": b"MIT",
        "scripts/ReactorV/ReactorV.contract.json": json.dumps({"product": "reactor-v", "runtime_version": "0.2.0", "extension_api_version": 1}).encode(),
        dep.UI_ROOT + "index.html": b"neutral-ui",
        dep.UI_ROOT + "reactor-ui.json": b'{"profile":"reactor-runtime"}',
        dep.UI_ROOT + "assets/neutral.js": b"generic-menus",
        "scripts/ReactorV/ReactorV.json": b'{"renderer":"auto"}',
        "plugins/ReactorV/ReactorV.Preloader.json": b'{"enabled":true}',
    })
    if not enhanced:
        files["plugins/ReactorV/ReactorV.LegacyCpuFrames.enabled"] = b"enabled"
    files.update(extra or {})
    archive = tmp_path / ("enhanced.zip" if enhanced else "legacy.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as package:
        for name, payload in files.items():
            package.writestr(name, payload)
    release = replace(dep.RELEASES[enhanced], size=archive.stat().st_size, sha256=dep._sha(archive),
                      game_sha256=hashlib.sha256(b"game-fixture").hexdigest())
    return archive, release, files


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "GTA with spaces"
    root.mkdir()
    put(root, "GTA5.exe", b"game-fixture")
    archive, release, files = archive_fixture(tmp_path)
    monkeypatch.setitem(dep.RELEASES, False, release)
    monkeypatch.setattr(dep, "_assert_game_closed", lambda: None)
    monkeypatch.setattr(dep, "_download", lambda *_a, **_kw: archive)
    ui = {dep.UI_ROOT + "index.html": put(tmp_path / "consumer", "index.html", "gbay-and-generic-menus"),
          dep.UI_ROOT + "assets/allin1.js": put(tmp_path / "consumer", "assets/allin1.js", "consumer-script")}
    monkeypatch.setattr(dep, "consumer_files", lambda: ui)
    return SimpleNamespace(root=root, archive=archive, release=release, runtime=files, ui=ui)


def test_install_repair_remove_preserves_shared_runtime_and_other_mods(setup):
    root = setup.root
    put(root, "scripts/ReactorV/Other.plugin", "other mod")
    put(root, dep.UI_ROOT + "assets/another-mod/icon.png", "other art")
    put(root, "scripts/AnotherMod/settings.json", '{"custom":true}')
    dep.install_dependency(root, False)
    first = snapshot(root)
    assert dep.dependency_recorded(root, False)
    assert not dep.dependency_recorded(root, True)
    assert first[dep.UI_ROOT + "index.html"] == b"gbay-and-generic-menus"
    assert json.loads(first[dep.RECEIPT])["shared"] is True
    put(root, "scripts/ReactorV/ReactorV.json", '{"renderer":"directx","toggleKey":"F10"}')
    before = snapshot(root)
    dep.install_dependency(root, False)
    assert snapshot(root) == before
    dep.remove_consumer(root)
    assert (root / dep.UI_ROOT / "index.html").read_bytes() == b"neutral-ui"
    assert not (root / dep.CONSUMER_RECEIPT).exists()
    assert not (root / dep.UI_ROOT / "assets/allin1.js").exists()
    assert (root / "ReactorV.RenderHook.asi").is_file()
    assert (root / dep.RECEIPT).is_file()
    assert (root / "scripts/ReactorV/Other.plugin").read_text() == "other mod"
    assert (root / dep.UI_ROOT / "assets/another-mod/icon.png").read_text() == "other art"
    assert (root / "scripts/ReactorV/ReactorV.json").read_bytes() == before["scripts/ReactorV/ReactorV.json"]
    assert dep.remove_consumer(root) == []
    dep.install_dependency(root, False)
    assert (root / dep.UI_ROOT / "index.html").read_bytes() == b"gbay-and-generic-menus"


def test_enhanced_uses_its_pinned_archive(setup, tmp_path, monkeypatch):
    archive, release, _ = archive_fixture(tmp_path, True)
    put(setup.root, "GTA5_Enhanced.exe", b"game-fixture")
    monkeypatch.setitem(dep.RELEASES, True, release)
    monkeypatch.setattr(dep, "_download", lambda *_a, **_kw: archive)
    assert "Enhanced" in dep.install_dependency(setup.root, True)
    assert not (setup.root / "plugins/ReactorV/ReactorV.LegacyCpuFrames.enabled").exists()


@pytest.mark.parametrize("name", ["ReactorV.RenderHook.asi", dep.UI_ROOT + "index.html"])
def test_unknown_or_edited_runtime_and_ui_are_never_overwritten(setup, name):
    put(setup.root, name, "somebody else's work")
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="Unmanaged or modified"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


def test_identical_manual_runtime_is_adopted_without_deleting_extensions(setup):
    for name, payload in setup.runtime.items():
        put(setup.root, name, payload)
    dep.install_dependency(setup.root, False)
    assert dep.dependency_recorded(setup.root, False)


def test_deleted_managed_files_repair_but_modified_files_block(setup):
    dep.install_dependency(setup.root, False)
    (setup.root / "ReactorV.ScriptProbe.asi").unlink()
    dep.install_dependency(setup.root, False)
    assert (setup.root / "ReactorV.ScriptProbe.asi").is_file()
    put(setup.root, "ReactorV.ScriptProbe.asi", "modified")
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="modified"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


@pytest.mark.parametrize("invalid", ["invalid-json", "[]", "null"])
def test_invalid_existing_settings_block_before_writes(setup, invalid):
    put(setup.root, "scripts/ReactorV/ReactorV.json", invalid)
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="Cannot read"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


def test_uninstall_refuses_changed_ui_and_corrupt_neutral_backup(setup):
    dep.install_dependency(setup.root, False)
    put(setup.root, dep.UI_ROOT + "index.html", "edited")
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="edited"):
        dep.remove_consumer(setup.root)
    assert snapshot(setup.root) == before
    put(setup.root, dep.UI_ROOT + "index.html", b"gbay-and-generic-menus")
    put(setup.root, dep.BACKUP_ROOT + "index.html", "corrupt")
    with pytest.raises(dep.ReactorInstallError, match="neutral UI backup"):
        dep.remove_consumer(setup.root)


def test_install_rolls_back_every_changed_file_on_copy_failure(setup, monkeypatch):
    dep.install_dependency(setup.root, False)
    # Reinstallation must restore the previous receipt after a late failure too.
    (setup.root / "ReactorV.ScriptProbe.asi").unlink()
    before = snapshot(setup.root)
    original = dep._atomic_copy
    def fail_last(source, target):
        if str(target).endswith("allin1-ui.json"):
            raise OSError("simulated sharing violation")
        original(source, target)
    monkeypatch.setattr(dep, "_atomic_copy", fail_last)
    with pytest.raises(OSError, match="sharing violation"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


def test_invalid_game_version_fails_before_download(setup, monkeypatch):
    put(setup.root, "GTA5.exe", "wrong game version")
    download = Mock()
    monkeypatch.setattr(dep, "_download", download)
    with pytest.raises(dep.ReactorInstallError, match="supported build"):
        dep.install_dependency(setup.root, False)
    download.assert_not_called()
    assert not (setup.root / "scripts").exists()


def test_running_game_fails_before_any_writes(setup, monkeypatch):
    guard = Mock(side_effect=dep.ReactorInstallError("Close GTA V"))
    monkeypatch.setattr(dep, "_assert_game_closed", guard)
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="Close GTA"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


def test_other_edition_marker_blocks_before_download(setup):
    put(setup.root, "plugins/ReactorV/ReactorV.EnhancedLiveTest.json", "{}")
    with pytest.raises(dep.ReactorInstallError, match="other edition"):
        dep.install_dependency(setup.root, False)


@pytest.mark.parametrize("name", ["../outside.dll", "scripts/ReactorV/../../outside.dll", "C:/escape", "/absolute", "scripts/ReactorV/a:stream", "scripts/ReactorV/CON.txt", "scripts/ReactorV/a. ", "scripts/ReactorV//empty"])
def test_rejects_unsafe_archive_paths(tmp_path, name):
    archive, release, _ = archive_fixture(tmp_path, extra={name: b"bad"})
    with pytest.raises(dep.ReactorInstallError, match="Unsafe"):
        dep._extract(archive, tmp_path / "staging", release)


def test_backslash_zip_paths_are_portable_and_case_duplicates_block(tmp_path):
    archive, release, _ = archive_fixture(tmp_path, extra={"scripts\\ReactorV\\extra.dll": b"x"})
    assert "scripts/ReactorV/extra.dll" in dep._extract(archive, tmp_path / "stage1", release)
    archive, release, _ = archive_fixture(tmp_path, extra={"scripts/ReactorV/ragewebui.core.DLL": b"x"})
    with pytest.raises(dep.ReactorInstallError, match="Duplicate"):
        dep._extract(archive, tmp_path / "stage2", release)


def test_archive_hash_size_and_expansion_bound_are_enforced(tmp_path, monkeypatch):
    archive, release, _ = archive_fixture(tmp_path)
    with pytest.raises(dep.ReactorInstallError, match="size/SHA"):
        dep._extract(archive, tmp_path / "stage", replace(release, sha256="0" * 64))
    monkeypatch.setattr(dep, "MAX_UNPACKED", 1)
    with pytest.raises(dep.ReactorInstallError, match="limits"):
        dep._extract(archive, tmp_path / "stage", release)


def test_download_is_bounded_pinned_cached_and_respects_skip(tmp_path, monkeypatch):
    archive, release, _ = archive_fixture(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    class Response(io.BytesIO):
        def geturl(self): return "https://release-assets.githubusercontent.com/fixture"
    download = Mock(side_effect=lambda *_a, **_k: Response(archive.read_bytes()))
    monkeypatch.setattr(dep.urllib.request, "urlopen", download)
    with pytest.raises(dep.ReactorInstallError, match="cache is missing"):
        dep._download(release, lambda _: None, allow_download=False)
    download.assert_not_called()
    result = dep._download(release, lambda _: None)
    assert dep._sha(result) == release.sha256
    assert dep._download(release, lambda _: None, allow_download=False) == result
    download.assert_called_once()
    result.unlink()
    download.side_effect = lambda *_a, **_k: Response(b"x" * (release.size + 1))
    with pytest.raises(dep.ReactorInstallError, match="exceeds"):
        dep._download(release, lambda _: None)
    assert not list(result.parent.glob("*.part"))


def test_receipt_cannot_claim_game_or_another_mod_paths(setup):
    put(setup.root, dep.CONSUMER_RECEIPT, json.dumps({"schema_version": 1, "product": "allin1-ui", "files": {"GTA5.exe": "a" * 64}}))
    with pytest.raises(dep.ReactorInstallError, match="non-owned"):
        dep.remove_consumer(setup.root)
    assert (setup.root / "GTA5.exe").read_bytes() == b"game-fixture"


def test_preflight_source_and_destination_races_abort_without_writes(tmp_path):
    root = tmp_path / "game"
    root.mkdir()
    source = put(tmp_path, "source", "new")
    put(root, "dest", "changed")
    with pytest.raises(dep.ReactorInstallError, match="since preflight"):
        dep._transaction(root, {"dest": source}, expected_targets={"dest": "a" * 64})
    with pytest.raises(dep.ReactorInstallError, match="Source changed"):
        dep._transaction(root, {"dest": source}, expected_sources={"dest": "a" * 64})
    assert (root / "dest").read_text() == "changed"


def test_consumer_payload_and_real_pins_are_valid():
    files = dep.consumer_files(artwork=False)
    assert dep.UI_ROOT + "index.html" in files
    assert not any(p.suffix in {".dll", ".exe", ".asi"} for p in files.values())
    assert any(b"GBAY" in p.read_bytes() for p in files.values() if p.suffix == ".js")
    assert {r.edition for r in dep.RELEASES.values()} == {"legacy", "enhanced"}
    assert all(r.url.startswith("https://github.com/MinionEnjoyer/GTAV-REACTOR-V/") for r in dep.RELEASES.values())


def test_old_framework_package_cannot_have_dual_ownership(setup):
    put(setup.root, "scripts/.allin1/mods/ragewebui.framework.json", json.dumps({
        "id": "ragewebui.framework", "files": [{"destination": "ReactorV.RenderHook.asi"}],
    }))
    before = snapshot(setup.root)
    with pytest.raises(dep.ReactorInstallError, match="still owned.*ragewebui.framework"):
        dep.install_dependency(setup.root, False)
    assert snapshot(setup.root) == before


def test_packages_cannot_replace_or_disable_shared_files(setup, monkeypatch):
    from allin1.mods import ModIntegrationService
    dep.install_dependency(setup.root, False)
    dep.assert_package_paths_available(setup.root, ["scripts/ReactorV/Another.plugin", dep.UI_ROOT + "assets/another/icon.png"])
    with pytest.raises(dep.ReactorInstallError, match="shared Reactor ownership"):
        dep.assert_package_paths_available(setup.root, ["reactorv.renderhook.ASI"])
    service = ModIntegrationService(setup.root)
    monkeypatch.setattr(service, "_read_receipt", lambda _: {"files": [{"destination": "ReactorV.RenderHook.asi"}]})
    for operation in (lambda: service.set_enabled("old.framework", False), lambda: service.uninstall("old.framework")):
        with pytest.raises(dep.ReactorInstallError, match="shared Reactor ownership"):
            operation()
    manifest = SimpleNamespace(mod_id="new.framework", files=[SimpleNamespace(destination=Path("ReactorV.RenderHook.asi"))])
    with pytest.raises(dep.ReactorInstallError, match="shared Reactor ownership"):
        service._check_conflicts(manifest)


def test_symlink_is_rejected_without_touching_target(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "plugins").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Host does not permit symlink creation")
    with pytest.raises(dep.ReactorInstallError, match="Reparse"):
        dep._path(root, "plugins/ReactorV/file.dll")
    assert not list(outside.iterdir())
