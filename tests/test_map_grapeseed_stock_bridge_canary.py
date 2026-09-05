from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from lxml import etree

import allin1.cli as cli
import allin1.map_canary as shared
import allin1.map_grapeseed_stock_bridge_black_canary as phase_b
import allin1.map_grapeseed_stock_bridge_canary as phase_a


class SimulatedProcessCrash(BaseException):
    """Model process termination after an os.replace has committed."""


def _dlclist(items: list[str]) -> bytes:
    root = etree.Element("SMandatoryPacksData")
    paths = etree.SubElement(root, "Paths")
    for value in items:
        etree.SubElement(paths, "Item").text = value
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


def _append_dlclist_entry(tool: "FakeTool", entry: str) -> None:
    root = etree.fromstring(tool.dlclist)
    paths = root.find("Paths")
    assert paths is not None
    etree.SubElement(paths, "Item").text = entry
    tool.dlclist = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


def _remove_dlclist_entry(tool: "FakeTool", entry: str) -> None:
    root = etree.fromstring(tool.dlclist)
    paths = root.find("Paths")
    assert paths is not None
    wanted = entry.rstrip("/").casefold()
    for item in list(paths):
        if (item.text or "").rstrip("/").casefold() == wanted:
            paths.remove(item)
    tool.dlclist = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


def _stock_metadata() -> tuple[bytes, bytes]:
    content_root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
    etree.SubElement(content_root, "disabledFiles")
    etree.SubElement(content_root, "includedXmlFiles")
    etree.SubElement(content_root, "includedDataFiles")
    data_files = etree.SubElement(content_root, "dataFiles")
    proxy = etree.SubElement(data_files, "Item")
    etree.SubElement(proxy, "filename").text = phase_a.STOCK_PROXY
    etree.SubElement(proxy, "fileType").text = "INTERIOR_PROXY_ORDER_FILE"
    etree.SubElement(proxy, "disabled").set("value", "true")
    for filename in phase_a._EXPECTED_MAP_FILES:
        item = etree.SubElement(data_files, "Item")
        etree.SubElement(item, "filename").text = filename
        etree.SubElement(item, "fileType").text = "RPF_FILE"
        etree.SubElement(item, "disabled").set("value", "true")

    sets = etree.SubElement(content_root, "contentChangeSets")
    startup = etree.SubElement(sets, "Item")
    etree.SubElement(startup, "changeSetName").text = (
        phase_a.STOCK_STARTUP_CHANGESET
    )
    etree.SubElement(startup, "mapChangeSetData")
    etree.SubElement(startup, "filesToInvalidate")
    etree.SubElement(startup, "filesToDisable")
    startup_enabled = etree.SubElement(startup, "filesToEnable")
    etree.SubElement(startup_enabled, "Item").text = phase_a.STOCK_PROXY
    etree.SubElement(startup, "requiresLoadingScreen").set("value", "false")

    change = etree.SubElement(sets, "Item")
    etree.SubElement(change, "changeSetName").text = phase_a.STOCK_CHANGESET
    map_data = etree.SubElement(change, "mapChangeSetData")
    route = etree.SubElement(map_data, "Item")
    etree.SubElement(route, "associatedMap").text = "MO_JIM_L11"
    invalidated = etree.SubElement(route, "filesToInvalidate")
    for filename in phase_a._EXPECTED_MAP_INVALIDATIONS:
        etree.SubElement(invalidated, "Item").text = filename
    etree.SubElement(route, "filesToDisable")
    enabled = etree.SubElement(route, "filesToEnable")
    for filename in phase_a._EXPECTED_MAP_FILES:
        etree.SubElement(enabled, "Item").text = filename
    etree.SubElement(change, "txdToLoad")
    etree.SubElement(change, "txdToUnload")
    etree.SubElement(change, "residentResources")
    etree.SubElement(change, "unregisterResources")
    etree.SubElement(change, "requiresLoadingScreen").set("value", "true")
    etree.SubElement(change, "loadingScreenContext").text = (
        "LOADINGSCREEN_CONTEXT_LAST_FRAME"
    )
    etree.SubElement(change, "useCacheLoader").set("value", "true")

    setup_root = etree.Element("SSetupData")
    etree.SubElement(setup_root, "deviceName").text = phase_a.STOCK_DEVICE
    etree.SubElement(setup_root, "datFile").text = "content.xml"
    etree.SubElement(setup_root, "nameHash").text = "mpHeist"
    etree.SubElement(setup_root, "contentChangeSets")
    groups = etree.SubElement(setup_root, "contentChangeSetGroups")
    startup_group = etree.SubElement(groups, "Item")
    etree.SubElement(startup_group, "NameHash").text = "GROUP_STARTUP"
    startup_changes = etree.SubElement(startup_group, "ContentChangeSets")
    for name in phase_a._EXPECTED_STOCK_GROUP_STARTUP:
        etree.SubElement(startup_changes, "Item").text = name
    map_group = etree.SubElement(groups, "Item")
    etree.SubElement(map_group, "NameHash").text = "GROUP_MAP"
    map_changes = etree.SubElement(map_group, "ContentChangeSets")
    for name in phase_a._EXPECTED_STOCK_GROUP_MAP:
        etree.SubElement(map_changes, "Item").text = name
    etree.SubElement(setup_root, "type").text = "EXTRACONTENT_COMPAT_PACK"
    etree.SubElement(setup_root, "order").set("value", "10")
    return (
        etree.tostring(
            content_root, xml_declaration=True, encoding="UTF-8",
            pretty_print=True,
        ),
        etree.tostring(
            setup_root, xml_declaration=True, encoding="UTF-8",
            pretty_print=True,
        ),
    )


def _game(tmp_path: Path, *, davis: bool = True) -> Path:
    game = tmp_path / "game"
    game.mkdir(parents=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"enhanced")
    mods_update = game / "mods/update/update.rpf"
    mods_update.parent.mkdir(parents=True)
    mods_update.write_bytes(b"mods update")
    mpheist = game / phase_a.STOCK_ARCHIVE_RELATIVE
    mpheist.parent.mkdir(parents=True)
    mpheist.write_bytes(b"effective stock mpheist archive fixture")
    if davis:
        davis_root = (
            game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
        )
        davis_root.mkdir(parents=True)
        (davis_root / "dlc.rpf").write_bytes(b"davis bridge")
        (davis_root / f"{phase_a.DAVIS_PACK_NAME}.active").write_text(
            "davis phase a", encoding="utf-8",
        )
        (davis_root / f"{phase_a.DAVIS_PACK_NAME}.runtime.json").write_text(
            '{"phase":"phase-a"}\n', encoding="utf-8",
        )
    return game


class FakeTool:
    def __init__(self, dlclist: bytes) -> None:
        self.dlclist = dlclist
        self.content, self.setup = _stock_metadata()
        self.packaged: dict[str, bytes] = {}
        self.commands: list[list[str]] = []
        self.fail: str | None = None
        self.crash_after: str | None = None

    def __call__(
        self,
        _patcher: Path,
        arguments: list[str | Path],
        *,
        operation: str,
        timeout: int = 600,
    ) -> None:
        del operation, timeout
        args = [str(value) for value in arguments]
        self.commands.append(args)
        command = args[0]
        if command == self.fail:
            raise RuntimeError(f"injected {command} failure")
        if command == "extract-entry":
            archive = Path(args[2])
            entry = args[3]
            output = Path(args[4])
            output.parent.mkdir(parents=True, exist_ok=True)
            if archive.name == "update.rpf":
                output.write_bytes(self.dlclist)
            elif "mpheist" in str(archive).casefold() and archive.name == "dlc.rpf":
                output.write_bytes(self.content if entry == "content.xml" else self.setup)
            else:
                output.write_bytes(self.packaged[entry])
        elif command == "build-dlc":
            root = Path(args[1])
            self.packaged = {
                name: (root / name).read_bytes()
                for name in ("content.xml", "setup2.xml")
            }
            Path(args[2]).write_bytes(b"grapeseed metadata-only bridge")
        elif command == "index-json":
            Path(args[3]).write_text(json.dumps({
                "schema_version": 1,
                "entries": [
                    {"path": "content.xml"}, {"path": "setup2.xml"},
                ],
                "warnings": [],
            }), encoding="utf-8")
        elif command == "register-dlc":
            root = etree.fromstring(self.dlclist)
            paths = root.find("Paths")
            assert paths is not None
            etree.SubElement(paths, "Item").text = phase_a.PACK_ENTRY
            self.dlclist = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif command == "unregister-dlc":
            root = etree.fromstring(self.dlclist)
            paths = root.find("Paths")
            assert paths is not None
            wanted = phase_a.PACK_ENTRY.rstrip("/").casefold()
            matches = [
                item for item in list(paths)
                if (item.text or "").rstrip("/").casefold() == wanted
            ]
            if len(matches) != 1:
                raise RuntimeError("injected unregister-dlc ownership failure")
            paths.remove(matches[0])
            self.dlclist = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif command == "replace-entry":
            self.dlclist = Path(args[4]).read_bytes()
        else:  # pragma: no cover
            raise AssertionError(f"Unexpected RPF command: {command}")
        if command == self.crash_after:
            raise SimulatedProcessCrash(f"process terminated after {command}")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    game = _game(tmp_path)
    patcher = tmp_path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    baseline = _dlclist([
        "dlcpacks:/mpheist/", phase_a.DAVIS_PACK_ENTRY,
    ])
    tool = FakeTool(baseline)
    monkeypatch.setattr(shared, "_run_tool", tool)
    return game, patcher, tool, baseline


def _install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, FakeTool, dict[str, object]]:
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "phase-a-state"
    receipt = phase_a.install_grapeseed_stock_reference_boot_canary(
        game,
        confirmation=phase_a.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    return game, patcher, state, tool, receipt


def _phase_a_log(game: Path, state: Path, *, source: str = "startup_guard") -> str:
    session = "abcdef123456"
    receipt_path = state / "install-receipt.json"
    start = datetime.now(timezone.utc) + timedelta(seconds=2)
    blocked = start + timedelta(seconds=2)
    ended = blocked + timedelta(seconds=35)
    events = [
        {
            "ts": start.isoformat(), "level": "INFO", "session": session,
            "component": "Client", "message": "session_started",
        },
        {
            "ts": blocked.isoformat(), "level": "WARN", "session": session,
            "component": "DeferredMap",
            "message": "grapeseed_phase_a_runtime_activation_blocked",
            "property": "grapeseed", "request_source": source,
            "required_phase": phase_b.PHASE,
            "native_group_executed": False, "ipl_requested": False,
        },
        {
            "ts": ended.isoformat(), "level": "INFO", "session": session,
            "component": "Client", "message": "session_survived",
        },
    ]
    log = game / phase_b.CLIENT_LOG_RELATIVE
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    assert receipt_path.is_file()
    return session


def test_phase_a_attests_exact_official_closure_and_inert_bridge(tmp_path):
    game = _game(tmp_path, davis=False)
    archive = game / phase_a.STOCK_ARCHIVE_RELATIVE
    content, setup = _stock_metadata()
    content_path = tmp_path / "content.xml"
    setup_path = tmp_path / "setup2.xml"
    content_path.write_bytes(content)
    setup_path.write_bytes(setup)
    attestation = phase_a.inspect_effective_mpheist_metadata(
        content_path, setup_path, archive_path=archive,
        archive_source="stock", game=game,
    )
    assert attestation["stock_map_group_changesets"] == list(
        phase_a._EXPECTED_STOCK_GROUP_MAP
    )
    assert attestation["stock_startup_changesets"] == list(
        phase_a._EXPECTED_STOCK_GROUP_STARTUP
    )
    assert attestation["official_semantics"]["files_to_enable"] == list(
        phase_a._EXPECTED_MAP_FILES
    )
    root = phase_a.create_stock_bridge_staging(tmp_path / "stage")
    topology = phase_a.inspect_stock_bridge_topology(root)
    assert all(topology["checks"].values())
    assert topology["stock_changesets"] == [phase_a.STOCK_CHANGESET]
    assert set(path.name for path in root.iterdir()) == {"content.xml", "setup2.xml"}
    assert etree.parse(str(root / "content.xml")).xpath("//dataFiles/Item") == []


def test_phase_a_install_status_and_rollback_preserve_davis(
    tmp_path, monkeypatch,
):
    game, patcher, state, tool, receipt = _install(tmp_path, monkeypatch)
    destination = phase_a._destination(game)
    assert not phase_a._transaction_paths(
        game, receipt["transaction_id"],
    )["root"].exists()
    assert set(path.name for path in destination.iterdir()) == {
        "dlc.rpf", phase_a.MARKER_NAME, phase_a.RUNTIME_RECEIPT_NAME,
    }
    assert receipt["schema"] == 4
    assert receipt["davis_bridge_snapshot"]["registration_count"] == 1
    runtime_text = (destination / phase_a.RUNTIME_RECEIPT_NAME).read_text(
        encoding="utf-8"
    )
    assert str(tmp_path) not in runtime_text
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 1
    assert phase_a._count_entry(tool.dlclist, phase_a.DAVIS_PACK_ENTRY) == 1
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["checks"]["retired_allin1_maps_absent"] is True
    assert status["checks"]["davis_bridge_unaffected"] is True
    rolled_back = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert rolled_back["status"] == "rolled_back"
    assert not destination.exists()
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0
    assert phase_a._count_entry(tool.dlclist, phase_a.DAVIS_PACK_ENTRY) == 1


def test_phase_a_register_failure_restores_exact_baseline(tmp_path, monkeypatch):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    tool.fail = "register-dlc"
    state = tmp_path / "phase-a-state"
    with pytest.raises(RuntimeError, match="injected register-dlc"):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
        )
    assert tool.dlclist == baseline
    assert not phase_a._destination(game).exists()
    assert not state.exists()


def _crash_at(expected: str):
    def inject(boundary: str) -> None:
        if boundary == expected:
            raise SimulatedProcessCrash(f"process terminated at {boundary}")

    return inject


@pytest.mark.parametrize("boundary", [
    "preparing",
    "prepared",
    "old_pack_rename_pending",
    "old_pack_saved",
    "new_pack_rename_pending",
    "pack_deployed_live",
    "pack_deployed",
    "registration_pending",
    "registration_added_live",
    "registered",
    "receipt_pending",
    "install_receipt_written_live",
    "complete",
])
def test_phase_a_process_death_at_every_install_boundary_is_recoverable(
    tmp_path, monkeypatch, boundary,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "phase-a-state"
    with pytest.raises(SimulatedProcessCrash):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
            fault_injector=_crash_at(boundary),
        )

    unrelated = f"dlcpacks:/unrelated_after_{boundary}/"
    _append_dlclist_entry(tool, unrelated)
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is (boundary == "complete")
    if boundary != "complete":
        assert status["recoverable"] is True
        assert status["status"] in {"pre_mutation", "interrupted_recoverable"}

    result = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back"
    assert not phase_a._destination(game).exists()
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1
    assert phase_a._count_entry(tool.dlclist, phase_a.DAVIS_PACK_ENTRY) == 1


def test_phase_a_recovers_process_death_inside_registration_tool(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "phase-a-state"
    tool.crash_after = "register-dlc"
    with pytest.raises(SimulatedProcessCrash, match="after register-dlc"):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
        )
    tool.crash_after = None
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "interrupted_recoverable"
    assert status["live"]["registration_count"] == 1
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0


def test_phase_a_preexisting_unregistered_pack_is_restored_after_process_death(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    destination = phase_a._destination(game)
    destination.mkdir(parents=True)
    (destination / "preexisting.bin").write_bytes(b"friend-owned preimage")
    original_manifest = shared._file_manifest(destination)
    state = tmp_path / "phase-a-state"
    with pytest.raises(SimulatedProcessCrash):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
            fault_injector=_crash_at("old_pack_saved_live"),
        )
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "interrupted_recoverable"
    assert status["live"]["destination"] == "absent"
    assert status["live"]["saved_original"] == "original"
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert shared._file_manifest(destination) == original_manifest
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0


@pytest.mark.parametrize("boundary", [
    "original_pack_restore_pending",
    "original_pack_restored_live",
])
def test_phase_a_preexisting_pack_restore_resumes_across_atomic_boundaries(
    tmp_path, monkeypatch, boundary,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    destination = phase_a._destination(game)
    destination.mkdir(parents=True)
    (destination / "preexisting.bin").write_bytes(b"friend-owned preimage")
    original_manifest = shared._file_manifest(destination)
    state = tmp_path / "phase-a-state"
    phase_a.install_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.INSTALL_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    with pytest.raises(SimulatedProcessCrash):
        phase_a.rollback_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
            fault_injector=_crash_at(boundary),
        )
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["recoverable"] is True
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert shared._file_manifest(destination) == original_manifest


def test_phase_a_recovers_process_death_inside_unregister_tool(
    tmp_path, monkeypatch,
):
    game, patcher, state, tool, _receipt = _install(tmp_path, monkeypatch)
    unrelated = "dlcpacks:/unrelated_before_unregister_crash/"
    _append_dlclist_entry(tool, unrelated)
    tool.crash_after = "unregister-dlc"
    with pytest.raises(SimulatedProcessCrash, match="after unregister-dlc"):
        phase_a.rollback_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
        )
    tool.crash_after = None
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "interrupted_recoverable"
    assert status["live"]["registration_count"] == 0
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1


def test_phase_a_journal_less_preparation_debris_is_discarded_without_live_write(
    tmp_path, monkeypatch,
):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    destination = phase_a._destination(game)
    destination.mkdir(parents=True)
    (destination / "unmanaged.bin").write_bytes(b"unmanaged preexisting pack")
    original_manifest = shared._file_manifest(destination)
    state = tmp_path / "phase-a-state"
    state.mkdir()
    (state / "work").mkdir()
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "pre_mutation"
    result = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "discarded_pre_mutation_checkpoint"
    assert not state.exists()
    assert tool.dlclist == baseline
    assert shared._file_manifest(destination) == original_manifest


def test_phase_a_power_loss_during_same_volume_stage_copy_never_exposes_partial_pack(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "phase-a-state"
    copytree = phase_a.shutil.copytree

    def crash_copy(source, destination, *args, **kwargs):
        destination = Path(destination)
        if destination.name == "stage-building":
            destination.mkdir(parents=True)
            source = Path(source)
            phase_a.shutil.copy2(source / "dlc.rpf", destination / "dlc.rpf")
            raise SimulatedProcessCrash("power loss during stage copy")
        return copytree(source, destination, *args, **kwargs)

    monkeypatch.setattr(phase_a.shutil, "copytree", crash_copy)
    with pytest.raises(SimulatedProcessCrash, match="during stage copy"):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
        )
    destination = phase_a._destination(game)
    assert not destination.exists()
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "pre_mutation"
    assert status["recoverable"] is True
    monkeypatch.setattr(phase_a.shutil, "copytree", copytree)
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert not destination.exists()


@pytest.mark.parametrize("boundary", [
    "rollback_registration_pending",
    "registration_removed_live",
    "registration_restored",
    "installed_pack_remove_pending",
    "installed_pack_removed_live",
    "installed_pack_removed",
    "original_pack_restored",
    "rollback_receipt_pending",
    "rollback_receipt_written_live",
    "rolled_back",
])
def test_phase_a_interrupted_rollback_resumes_at_every_live_boundary(
    tmp_path, monkeypatch, boundary,
):
    game, patcher, state, tool, _receipt = _install(tmp_path, monkeypatch)
    unrelated = f"dlcpacks:/unrelated_rollback_{boundary}/"
    _append_dlclist_entry(tool, unrelated)
    with pytest.raises(SimulatedProcessCrash):
        phase_a.rollback_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
            fault_injector=_crash_at(boundary),
        )
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["recoverable"] is True
    result = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back"
    assert not phase_a._destination(game).exists()
    assert phase_a._count_entry(tool.dlclist, phase_a.PACK_ENTRY) == 0
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1


def test_phase_a_rollback_preserves_independent_davis_lifecycle_change(
    tmp_path, monkeypatch,
):
    game, patcher, state, tool, _receipt = _install(tmp_path, monkeypatch)
    _remove_dlclist_entry(tool, phase_a.DAVIS_PACK_ENTRY)
    davis_root = (
        game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
    )
    for path in sorted(davis_root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    davis_root.rmdir()
    phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert phase_a._count_entry(tool.dlclist, phase_a.DAVIS_PACK_ENTRY) == 0
    assert not davis_root.exists()


def test_phase_a_install_and_rollback_are_idempotent_and_ignore_unrelated_dlc(
    tmp_path, monkeypatch,
):
    game, patcher, state, tool, receipt = _install(tmp_path, monkeypatch)
    unrelated = "dlcpacks:/legitimate_added_after_phase_a/"
    _append_dlclist_entry(tool, unrelated)
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert phase_a.install_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.INSTALL_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    ) == receipt
    first = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    second = phase_a.rollback_grapeseed_stock_reference_boot_canary(
        game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert second == first
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1


def test_phase_a_interrupted_install_refuses_unknown_destination_drift(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "phase-a-state"
    with pytest.raises(SimulatedProcessCrash):
        phase_a.install_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.INSTALL_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
            fault_injector=_crash_at("pack_deployed"),
        )
    destination = phase_a._destination(game)
    (destination / "unknown.bin").write_bytes(b"external drift")
    status = phase_a.read_grapeseed_stock_reference_boot_canary_status(
        game, state_root=state, patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "interrupted_drifted"
    assert status["recoverable"] is False
    with pytest.raises(RuntimeError, match="refuses to overwrite unknown live drift"):
        phase_a.rollback_grapeseed_stock_reference_boot_canary(
            game, confirmation=phase_a.ROLLBACK_CONFIRMATION,
            state_root=state, patcher=patcher, process_probe=lambda: set(),
        )
    assert (destination / "unknown.bin").read_bytes() == b"external drift"


def test_bounded_phase_a_launch_contract_rejects_duplicate_json(
    tmp_path, monkeypatch,
):
    game, _patcher, _state, _tool, _receipt = _install(tmp_path, monkeypatch)
    valid, detail, _runtime = phase_a.validate_phase_a_launch_contract(game)
    assert (valid, detail) == (True, "verified")
    runtime = phase_a._destination(game) / phase_a.RUNTIME_RECEIPT_NAME
    raw = runtime.read_text(encoding="utf-8")
    runtime.write_text(raw[:-2] + ',"schema":4}\n', encoding="utf-8")
    valid, detail, _runtime = phase_a.validate_phase_a_launch_contract(game)
    assert valid is False
    assert "unreadable" in detail


@pytest.mark.parametrize("source", ["startup_guard", "garage_entry"])
def test_phase_b_promotes_only_pair_and_rolls_back_to_exact_phase_a(
    tmp_path, monkeypatch, source,
):
    game, patcher, phase_a_state, tool, phase_a_receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state, source=source)
    destination = phase_a._destination(game)
    archive = destination / "dlc.rpf"
    archive_before = archive.read_bytes()
    dlclist_before = tool.dlclist
    marker_before = (destination / phase_a.MARKER_NAME).read_bytes()
    runtime_before = (destination / phase_a.RUNTIME_RECEIPT_NAME).read_bytes()
    phase_b_state = tmp_path / "phase-b-state"
    receipt = phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert receipt["schema"] == 5
    assert archive.read_bytes() == archive_before
    assert tool.dlclist == dlclist_before
    runtime_text = (destination / phase_a.RUNTIME_RECEIPT_NAME).read_text(
        encoding="utf-8"
    )
    assert str(tmp_path) not in runtime_text
    valid, detail, runtime = phase_b.validate_phase_b_launch_contract(game)
    assert (valid, detail) == (True, "verified")
    assert runtime["groups"] == [phase_b._group_contract()]
    assert runtime["source_attestation"] == phase_a_receipt["source_attestation"]
    result = phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back_to_phase_a"
    assert (destination / phase_a.MARKER_NAME).read_bytes() == marker_before
    assert (destination / phase_a.RUNTIME_RECEIPT_NAME).read_bytes() == runtime_before
    assert archive.read_bytes() == archive_before
    assert tool.dlclist == dlclist_before


def test_phase_b_promotion_preserves_unrelated_dlc_added_after_phase_a(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    unrelated = "dlcpacks:/legitimate_added_between_grapeseed_phases/"
    _append_dlclist_entry(tool, unrelated)
    dlclist_before = tool.dlclist
    phase_b_state = tmp_path / "phase-b-state"

    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )

    assert tool.dlclist == dlclist_before
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1
    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True


def test_phase_b_promotion_preserves_davis_removal_after_phase_a(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    _remove_dlclist_entry(tool, phase_a.DAVIS_PACK_ENTRY)
    davis_root = (
        game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
    )
    for path in sorted(davis_root.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    davis_root.rmdir()
    dlclist_before = tool.dlclist
    phase_b_state = tmp_path / "phase-b-state"

    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )

    assert tool.dlclist == dlclist_before
    assert phase_a._count_entry(tool.dlclist, phase_a.DAVIS_PACK_ENTRY) == 0
    assert not davis_root.exists()
    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["checks"]["davis_coexistence_safe"] is True


def test_phase_b_retry_discards_only_owned_prejournal_preparation(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, _tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    original_copy2 = phase_b.shutil.copy2

    def crash_after_first_preparation_copy(source: Path, target: Path):
        result = original_copy2(source, target)
        if target.name == phase_b.PHASE_A_MARKER_BACKUP:
            raise SimulatedProcessCrash("promotion died before its journal")
        return result

    monkeypatch.setattr(
        phase_b.shutil, "copy2", crash_after_first_preparation_copy,
    )
    with pytest.raises(SimulatedProcessCrash):
        phase_b.promote_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    monkeypatch.setattr(phase_b.shutil, "copy2", original_copy2)
    assert not (phase_b_state / "journal.json").exists()
    assert set(path.name for path in phase_b_state.iterdir()) == {
        phase_b.PHASE_A_MARKER_BACKUP,
    }
    interrupted = (
        phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
            game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    )
    assert interrupted["status"] == "pre_mutation"
    assert interrupted["recoverable"] is True

    receipt = phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert receipt["status"] == phase_b.MARKER_STATUS


def test_phase_b_retry_preserves_unrecognized_prejournal_state(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, _tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    phase_b_state.mkdir()
    unrelated = phase_b_state / "not-owned.txt"
    unrelated.write_text("preserve me", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unrecognized or non-regular"):
        phase_b.promote_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    assert unrelated.read_text(encoding="utf-8") == "preserve me"


def test_phase_b_interrupted_promotion_is_detected_and_guardedly_rolled_back(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    destination = phase_a._destination(game)
    marker = destination / phase_a.MARKER_NAME
    runtime = destination / phase_a.RUNTIME_RECEIPT_NAME
    marker_before = marker.read_bytes()
    runtime_before = runtime.read_bytes()
    archive_before = (destination / "dlc.rpf").read_bytes()
    dlclist_before = tool.dlclist
    phase_b_state = tmp_path / "phase-b-state"
    replacements = 0

    def crash_after_first_replace(source: Path, target: Path) -> None:
        nonlocal replacements
        os.replace(source, target)
        replacements += 1
        if replacements == 1:
            raise SimulatedProcessCrash("promotion process terminated")

    with pytest.raises(SimulatedProcessCrash):
        phase_b.promote_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
            replace=crash_after_first_replace,
        )

    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "promotion_interrupted_recoverable"
    assert status["live_pair_state"] == "mixed_known"
    assert status["recoverable"] is True
    assert status["healthy"] is False
    assert (destination / "dlc.rpf").read_bytes() == archive_before
    assert tool.dlclist == dlclist_before

    result = phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back_to_phase_a"
    assert marker.read_bytes() == marker_before
    assert runtime.read_bytes() == runtime_before
    assert (destination / "dlc.rpf").read_bytes() == archive_before
    assert tool.dlclist == dlclist_before


def test_phase_b_interrupted_rollback_resumes_without_overwriting_drift(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    destination = phase_a._destination(game)
    marker = destination / phase_a.MARKER_NAME
    runtime = destination / phase_a.RUNTIME_RECEIPT_NAME
    marker_before = marker.read_bytes()
    runtime_before = runtime.read_bytes()
    archive_before = (destination / "dlc.rpf").read_bytes()
    dlclist_before = tool.dlclist
    phase_b_state = tmp_path / "phase-b-state"
    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    replacements = 0

    def crash_after_first_replace(source: Path, target: Path) -> None:
        nonlocal replacements
        os.replace(source, target)
        replacements += 1
        if replacements == 1:
            raise SimulatedProcessCrash("rollback process terminated")

    with pytest.raises(SimulatedProcessCrash):
        phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
            replace=crash_after_first_replace,
        )

    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["status"] == "rollback_interrupted_recoverable"
    assert status["live_pair_state"] == "mixed_known"
    assert status["recoverable"] is True

    tampered = marker.read_bytes() + b"unknown drift"
    marker.write_bytes(tampered)
    with pytest.raises(RuntimeError, match="refuses to overwrite"):
        phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    assert marker.read_bytes() == tampered
    marker.write_bytes(
        (phase_b_state / phase_b.PHASE_B_MARKER_BACKUP).read_bytes()
    )

    result = phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back_to_phase_a"
    assert marker.read_bytes() == marker_before
    assert runtime.read_bytes() == runtime_before
    assert (destination / "dlc.rpf").read_bytes() == archive_before
    assert tool.dlclist == dlclist_before


def test_phase_b_allows_unrelated_dlc_addition_and_preserves_it_on_rollback(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    unrelated = "dlcpacks:/unrelated_legitimate_mod/"
    _append_dlclist_entry(tool, unrelated)

    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["checks"]["grapeseed_registration_exact"] is True
    assert status["checks"]["davis_coexistence_safe"] is True

    phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert phase_a._count_entry(tool.dlclist, unrelated) == 1
    rolled_back = (
        phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
            game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    )
    assert rolled_back["healthy"] is True


def test_phase_b_allows_independent_davis_phase_lifecycle_change(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    davis_root = (
        game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
    )
    davis_marker = davis_root / f"{phase_a.DAVIS_PACK_NAME}.active"
    davis_runtime = davis_root / f"{phase_a.DAVIS_PACK_NAME}.runtime.json"
    davis_marker.write_text("davis phase b", encoding="utf-8")
    davis_runtime.write_text(
        '{"phase":"phase-b-black-transition"}\n', encoding="utf-8",
    )
    davis_after_promotion = shared._file_manifest(davis_root)

    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["checks"]["davis_registration_cardinality"] is True
    assert status["checks"]["davis_pack_registration_coherent"] is True
    assert status["checks"]["davis_quarantined_layout"] is True
    assert status["checks"]["davis_coexistence_safe"] is True

    phase_b.rollback_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert shared._file_manifest(davis_root) == davis_after_promotion
    rolled_back = (
        phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
            game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
        )
    )
    assert rolled_back["healthy"] is True


def test_phase_b_transaction_detects_davis_change_but_recovers_grapeseed(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    destination = phase_a._destination(game)
    phase_a_marker = (destination / phase_a.MARKER_NAME).read_bytes()
    phase_a_runtime = (destination / phase_a.RUNTIME_RECEIPT_NAME).read_bytes()
    davis_root = (
        game / "mods/update/x64/dlcpacks" / phase_a.DAVIS_PACK_NAME
    )
    davis_marker = davis_root / f"{phase_a.DAVIS_PACK_NAME}.active"
    replacements = 0

    def replace_and_advance_davis(source: Path, target: Path) -> None:
        nonlocal replacements
        os.replace(source, target)
        replacements += 1
        if replacements == 1:
            davis_marker.write_text("davis phase b", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Davis changed during"):
        phase_b.promote_grapeseed_stock_reference_black_transition_canary(
            game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
            state_root=phase_b_state, phase_a_state_root=phase_a_state,
            patcher=patcher, process_probe=lambda: set(),
            replace=replace_and_advance_davis,
        )
    assert (destination / phase_a.MARKER_NAME).read_bytes() == phase_a_marker
    assert (destination / phase_a.RUNTIME_RECEIPT_NAME).read_bytes() == phase_a_runtime
    assert davis_marker.read_text(encoding="utf-8") == "davis phase b"
    assert not phase_b_state.exists()
    assert phase_a.validate_phase_a_launch_contract(game)[:2] == (
        True, "verified",
    )


@pytest.mark.parametrize("registration_drift", ["missing", "duplicate", "retired"])
def test_phase_b_status_fails_closed_on_its_own_registration_drift(
    tmp_path, monkeypatch, registration_drift,
):
    game, patcher, phase_a_state, tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    if registration_drift == "missing":
        _remove_dlclist_entry(tool, phase_a.PACK_ENTRY)
    elif registration_drift == "duplicate":
        _append_dlclist_entry(tool, phase_a.PACK_ENTRY)
    else:
        _append_dlclist_entry(tool, phase_a.OLD_PACK_ENTRY)

    valid, _detail, checks = phase_b.validate_phase_b_registration_contract(
        game, patcher=patcher, state_root=phase_b_state,
    )
    assert valid is False
    assert checks["grapeseed_registration_exact"] is (
        registration_drift == "retired"
    )
    status = phase_b.read_grapeseed_stock_reference_black_transition_canary_status(
        game, state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is False


def test_launch_validators_never_hash_the_large_source_archive(
    tmp_path, monkeypatch,
):
    game, patcher, phase_a_state, _tool, _receipt = _install(
        tmp_path, monkeypatch,
    )
    source_archive = (game / phase_a.STOCK_ARCHIVE_RELATIVE).resolve()
    original = shared._sha256

    def bounded(path: Path) -> str:
        if Path(path).resolve() == source_archive:
            raise AssertionError("launch validator hashed the stock archive")
        return original(Path(path))

    monkeypatch.setattr(shared, "_sha256", bounded)
    assert phase_a.validate_phase_a_launch_contract(game)[:2] == (
        True, "verified",
    )
    monkeypatch.setattr(shared, "_sha256", original)
    session = _phase_a_log(game, phase_a_state)
    phase_b_state = tmp_path / "phase-b-state"
    phase_b.promote_grapeseed_stock_reference_black_transition_canary(
        game, confirmation=phase_b.PROMOTE_CONFIRMATION, session=session,
        state_root=phase_b_state, phase_a_state_root=phase_a_state,
        patcher=patcher, process_probe=lambda: set(),
    )
    monkeypatch.setattr(shared, "_sha256", bounded)
    assert phase_b.validate_phase_b_launch_contract(game)[:2] == (
        True, "verified",
    )


def _quoted_keys(block: str) -> set[str]:
    return set(re.findall(r'"([a-z][a-z0-9_]*)"', block))


def test_generated_python_contract_matches_csharp_exact_key_allowlists(
    tmp_path,
):
    game = _game(tmp_path, davis=False)
    content, setup = _stock_metadata()
    content_path = tmp_path / "content.xml"
    setup_path = tmp_path / "setup2.xml"
    content_path.write_bytes(content)
    setup_path.write_bytes(setup)
    attestation = phase_a.inspect_effective_mpheist_metadata(
        content_path, setup_path,
        archive_path=game / phase_a.STOCK_ARCHIVE_RELATIVE,
        archive_source="stock", game=game,
    )
    archive = tmp_path / "bridge.rpf"
    archive.write_bytes(b"metadata bridge")
    runtime = phase_a._runtime_receipt(archive, attestation)
    marker = tmp_path / phase_a.MARKER_NAME
    phase_a._write_marker(marker, runtime)
    generated_marker_keys = set(shared._marker_fields(marker))
    generated_receipt_keys = set(runtime)
    generated_group_keys = set(runtime["groups"][0])
    generated_source_keys = set(runtime["source_attestation"])

    source = (
        Path(__file__).resolve().parents[1]
        / "script/src/GrapeseedStockReferenceBridgePolicy.cs"
    ).read_text(encoding="utf-8")
    phase_a_method = source.split(
        "internal static bool IsExactPhaseABootOnlyContract", 1,
    )[1].split(
        "internal static bool IsExactPhaseBBlackTransitionContract", 1,
    )[0]
    marker_block = phase_a_method.split("string[] exactMarkerKeys", 1)[1].split(
        "};", 1,
    )[0]
    receipt_block = phase_a_method.split("string[] exactReceiptKeys", 1)[1].split(
        "};", 1,
    )[0]
    group_method = source.split("private static bool HasExactPhaseAGroup", 1)[1]
    group_block = group_method.split("string[] keys", 1)[1].split("};", 1)[0]
    source_method = source.split("private static bool HasExactSourceAttestation", 1)[1]
    source_block = source_method.split("string[] sourceKeys", 1)[1].split(
        "};", 1,
    )[0]
    assert generated_marker_keys == _quoted_keys(marker_block)
    assert generated_receipt_keys == _quoted_keys(receipt_block)
    assert generated_group_keys == _quoted_keys(group_block)
    assert generated_source_keys == _quoted_keys(source_block)
    assert 'MarkerEquals(markerFields, "schema", "4")' in phase_a_method
    assert phase_b.STATE_SCHEMA == 5


def test_hidden_cli_commands_are_registered_and_confirmation_gated(tmp_path):
    commands = cli.map_canary_group.commands
    expected = {
        "grapeseed-stock-boot-install",
        "grapeseed-stock-boot-status",
        "grapeseed-stock-boot-rollback",
        "grapeseed-stock-black-promote",
        "grapeseed-stock-black-status",
        "grapeseed-stock-black-rollback",
    }
    assert expected.issubset(commands)
    game = _game(tmp_path, davis=False)
    result = CliRunner().invoke(cli.main, [
        "map-canary", "grapeseed-stock-boot-install",
        "--gta-path", str(game), "--yes",
    ])
    assert result.exit_code != 0
    assert phase_a.INSTALL_CONFIRMATION in result.output
