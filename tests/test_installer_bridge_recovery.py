"""Disposable bridge packaging transactions, with native-tool boundaries faked."""
import json
from pathlib import Path
import shutil

import pytest

from allin1 import installer
from tests.test_garment_stock_bridge import _write_stock_metadata


@pytest.fixture
def bridge_tree(tmp_path, monkeypatch):
    game = tmp_path / "game with spaces"
    bridge = installer.GARMENT
    source = game / "update/x64/dlcpacks" / bridge.source_pack / "dlc.rpf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"synthetic source archive")
    stock = tmp_path / "stock"
    stock.mkdir()
    _write_stock_metadata(stock)
    tools = tmp_path / "tools"
    tool = tools / "RpfPatcher/RpfPatcher.exe"
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"never executed")
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    destination = game / "mods/update/x64/dlcpacks" / bridge.pack
    state = {"registered": False, "fault": None, "staging": None, "calls": []}

    def command(_tool, args, **kwargs):
        state["calls"].append(args[0])
        if args[0] == "build-dlc":
            state["staging"] = Path(args[1])
            if state["fault"] != "missing-output":
                Path(args[2]).write_bytes(b"verified synthetic bridge")
            return
        assert args[0] == "extract-entry"
        archive, entry, output = Path(args[2]), args[3], Path(args[4])
        output.parent.mkdir(parents=True, exist_ok=True)
        if entry == installer._MAP_DLCLIST_ENTRY:
            enabled = state["registered"] and not (
                state["fault"] == "missing-registration" and output.name == "verified-dlclist.xml"
            )
            item = f"<Item>dlcpacks:/{bridge.pack}/</Item>" if enabled else ""
            output.write_text(f"<SMandatoryPacksData><Paths>{item}</Paths></SMandatoryPacksData>", encoding="utf-8")
        elif archive == source:
            shutil.copy2(stock / entry, output)
        else:
            shutil.copy2(state["staging"] / entry, output)
            if state["fault"] == "packaged-drift":
                output.write_bytes(b"wrong packaged bytes")

    def register(*args):
        if state["fault"] == "register":
            # Fail once, allowing restoration of the old registration.
            state["fault"] = None
            return False
        state["registered"] = True
        return True

    def unregister(*args):
        if state["fault"] == "unregister":
            state["fault"] = None
            return False
        state["registered"] = False
        return True

    monkeypatch.setattr(installer, "_map_patcher_command", command)
    monkeypatch.setattr(installer, "_patch_dlclist_rpf", register)
    monkeypatch.setattr(installer, "_unpatch_dlclist_rpf", unregister)
    return game, destination, source, state


@pytest.mark.parametrize("enhanced", [False, True])
@pytest.mark.parametrize("prior", [False, True])
def test_bridge_deployment_attests_sources_and_registers_only_verified_payload(bridge_tree, enhanced, prior):
    game, destination, source, state = bridge_tree
    if prior:
        destination.mkdir(parents=True)
        (destination / "old-receipt.txt").write_bytes(b"prior owned pack")
        (game / "mods/update/update.rpf").write_bytes(b"synthetic dlclist archive")
        state["registered"] = True
    result = installer.InstallResult(game, is_enhanced=enhanced)
    assert installer._deploy_garment_stock_bridge(game, result)
    receipt = json.loads((destination / installer.GARMENT.receipt).read_text(encoding="utf-8"))
    assert receipt["archive_sha256"] == installer._map_file_sha256(destination / "dlc.rpf")
    assert receipt["source_attestation"]["archive_sha256"] == installer._map_file_sha256(source)
    assert receipt["edition"] == ("enhanced" if enhanced else "legacy")
    assert state["registered"] is True
    assert not (destination / "old-receipt.txt").exists()
    assert state["calls"].count("build-dlc") == 1
    assert source.read_bytes() == b"synthetic source archive"


@pytest.mark.parametrize("failure", ["missing-output", "packaged-drift", "register", "unregister", "missing-registration"])
@pytest.mark.parametrize("prior", [False, True])
def test_bridge_failure_preserves_prior_pack_and_never_claims_success(bridge_tree, failure, prior):
    game, destination, source, state = bridge_tree
    # Unregister has a meaningful failure boundary only for an existing registration.
    if prior or failure == "unregister":
        destination.mkdir(parents=True)
        (destination / "user-owned-sentinel.txt").write_bytes(b"retain exactly")
        (game / "mods/update/update.rpf").write_bytes(b"synthetic dlclist archive")
        state["registered"] = True
        prior = True
    state["fault"] = failure
    with pytest.raises(RuntimeError):
        installer._deploy_garment_stock_bridge(game, installer.InstallResult(game))
    if prior:
        assert (destination / "user-owned-sentinel.txt").read_bytes() == b"retain exactly"
        assert list(destination.iterdir()) == [destination / "user-owned-sentinel.txt"]
        assert state["registered"] is True
    else:
        assert not destination.exists()
        assert state["registered"] is False
    assert source.read_bytes() == b"synthetic source archive"


def test_bridge_missing_tool_fails_without_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "_TOOLS_DIR", tmp_path / "absent tools")
    with pytest.raises(FileNotFoundError, match="required"):
        installer._deploy_garment_stock_bridge(tmp_path, installer.InstallResult(tmp_path))
    assert list(tmp_path.iterdir()) == []
