"""The retained compatibility builder must never register unsafe startup maps."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1 import installer
from allin1.generators import dlc_maps


@pytest.fixture
def copied_map_tree(tmp_path, monkeypatch):
    game = tmp_path / "disposable game"
    game.mkdir()
    tools = tmp_path / "tools"
    helper = tools / "RpfPatcher/RpfPatcher.exe"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"synthetic helper; not executable")
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    for asset in dlc_maps.MAP_ASSETS:
        archive = asset.source_archive(game)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"stock canary")
    state = {"fault": None, "stderr": True, "calls": [], "unregistered": False, "restored": False}

    def run(args, **kwargs):
        command = args[1]
        state["calls"].append(command)
        if state["fault"] == command:
            return SimpleNamespace(returncode=7, stdout="", stderr="injected failure" if state["stderr"] else "")
        if command == "extract-entries":
            staging = Path(args[5])
            for line in Path(args[4]).read_text(encoding="utf-8").splitlines():
                _, relative = line.split("\t")
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"" if state["fault"] == "empty-stage" else b"synthetic extracted archive")
        elif command == "build-dlc":
            if state["fault"] != "missing-output":
                Path(args[3]).write_bytes(b"" if state["fault"] == "empty-output" else b"verified synthetic DLC")
        elif command not in {"open-rpfs", "verify-map-dlc"}: pytest.fail(f"Unexpected native command: {command}")
        return SimpleNamespace(returncode=0, stdout="synthetic native progress", stderr="")

    def unregister(*args):
        state["unregistered"] = True
        return state["fault"] != "unregister"

    monkeypatch.setattr(installer, "run_hidden", run)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unregister)
    monkeypatch.setattr(installer, "_restore_verified_startup_map_pool_profile", lambda *args: state.update(restored=True))
    monkeypatch.setattr(installer, "_patch_dlclist_rpf", lambda *a: pytest.fail("Retired maps cannot be registered"))
    return game, helper, state


@pytest.mark.parametrize("enhanced", [False, True])
def test_retired_copied_pack_remains_inert_for_both_editions(copied_map_tree, enhanced):
    game, _, state = copied_map_tree
    result = installer.InstallResult(game, is_enhanced=enhanced)
    progress = []
    assert installer._deploy_retired_copied_map_dlc(game, result, lambda *args: progress.append(args))
    pack = game / "mods/update/x64/dlcpacks/allin1_maps"
    marker = (pack / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert "archive_registration=disabled" in marker
    assert (pack / "dlc.rpf").read_bytes() == b"verified synthetic DLC"
    assert not (pack / dlc_maps.RUNTIME_RECEIPT).exists()
    assert state["unregistered"] and state["restored"] is enhanced
    assert progress and result.warnings
    assert all(asset.source_archive(game).read_bytes() == b"stock canary" for asset in dlc_maps.MAP_ASSETS)


@pytest.mark.parametrize("fault", ["extract-entries", "open-rpfs", "build-dlc", "verify-map-dlc"])
@pytest.mark.parametrize("stderr", [False, True])
def test_retired_native_failure_cannot_publish_an_archive(copied_map_tree, fault, stderr):
    game, _, state = copied_map_tree
    state.update(fault=fault, stderr=stderr)
    with pytest.raises(RuntimeError, match="injected failure" if stderr else "exit code 7"):
        installer._deploy_retired_copied_map_dlc(game, installer.InstallResult(game))
    assert not (game / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf").exists()
    assert not state["unregistered"]


@pytest.mark.parametrize("fault", ["missing-source", "empty-stage", "missing-output", "empty-output", "unregister", "missing-helper"])
def test_retired_incomplete_artifacts_fail_closed(copied_map_tree, fault):
    game, helper, state = copied_map_tree
    state["fault"] = fault
    if fault == "missing-source": dlc_maps.MAP_ASSETS[0].source_archive(game).unlink()
    if fault == "missing-helper":
        helper.unlink()
        result = installer.InstallResult(game)
        assert not installer._deploy_retired_copied_map_dlc(game, result)
        assert "missing" in result.warnings[0]
    else:
        with pytest.raises(RuntimeError): installer._deploy_retired_copied_map_dlc(game, installer.InstallResult(game))
    assert not (game / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf").exists()
