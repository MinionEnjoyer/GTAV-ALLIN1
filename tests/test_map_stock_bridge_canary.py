from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from lxml import etree

import allin1.cli as cli
import allin1.map_canary as shared
import allin1.map_stock_bridge_canary as bridge


def _dlclist(items: list[str]) -> bytes:
    root = etree.Element("SMandatoryPacksData")
    paths = etree.SubElement(root, "Paths")
    for value in items:
        etree.SubElement(paths, "Item").text = value
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


def _stock_metadata() -> tuple[bytes, bytes]:
    content_root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
    etree.SubElement(content_root, "disabledFiles")
    etree.SubElement(content_root, "includedXmlFiles")
    etree.SubElement(content_root, "includedDataFiles")
    data_files = etree.SubElement(content_root, "dataFiles")

    proxy = etree.SubElement(data_files, "Item")
    etree.SubElement(proxy, "filename").text = bridge.STOCK_PROXY
    etree.SubElement(proxy, "fileType").text = "INTERIOR_PROXY_ORDER_FILE"
    etree.SubElement(proxy, "disabled").set("value", "true")
    for filename in bridge._EXPECTED_MAP_FILES:
        item = etree.SubElement(data_files, "Item")
        etree.SubElement(item, "filename").text = filename
        etree.SubElement(item, "fileType").text = "RPF_FILE"
        etree.SubElement(item, "disabled").set("value", "true")

    sets = etree.SubElement(content_root, "contentChangeSets")
    startup = etree.SubElement(sets, "Item")
    etree.SubElement(startup, "changeSetName").text = (
        bridge.STOCK_STARTUP_CHANGESET
    )
    etree.SubElement(startup, "mapChangeSetData")
    etree.SubElement(startup, "filesToInvalidate")
    etree.SubElement(startup, "filesToDisable")
    startup_enabled = etree.SubElement(startup, "filesToEnable")
    etree.SubElement(startup_enabled, "Item").text = bridge.STOCK_PROXY
    etree.SubElement(startup, "requiresLoadingScreen").set("value", "false")

    change = etree.SubElement(sets, "Item")
    etree.SubElement(change, "changeSetName").text = bridge.STOCK_CHANGESET
    map_data = etree.SubElement(change, "mapChangeSetData")
    route = etree.SubElement(map_data, "Item")
    etree.SubElement(route, "associatedMap").text = "MO_JIM_L11"
    etree.SubElement(route, "filesToInvalidate")
    etree.SubElement(route, "filesToDisable")
    enabled = etree.SubElement(route, "filesToEnable")
    for filename in bridge._EXPECTED_MAP_FILES:
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

    navmesh = etree.SubElement(sets, "Item")
    etree.SubElement(navmesh, "changeSetName").text = (
        "MPTUNER_MAP_UPDATE_NAVMESH_ONLY"
    )

    setup_root = etree.Element("SSetupData")
    etree.SubElement(setup_root, "deviceName").text = bridge.STOCK_DEVICE
    etree.SubElement(setup_root, "datFile").text = "content.xml"
    etree.SubElement(setup_root, "nameHash").text = "mpTuner"
    etree.SubElement(setup_root, "contentChangeSets")
    groups = etree.SubElement(setup_root, "contentChangeSetGroups")
    startup_group = etree.SubElement(groups, "Item")
    etree.SubElement(startup_group, "NameHash").text = "GROUP_STARTUP"
    startup_changes = etree.SubElement(startup_group, "ContentChangeSets")
    etree.SubElement(startup_changes, "Item").text = (
        bridge.STOCK_STARTUP_CHANGESET
    )
    map_group = etree.SubElement(groups, "Item")
    etree.SubElement(map_group, "NameHash").text = "GROUP_MAP"
    map_changes = etree.SubElement(map_group, "ContentChangeSets")
    for name in bridge._EXPECTED_STOCK_GROUP_MAP:
        etree.SubElement(map_changes, "Item").text = name
    etree.SubElement(setup_root, "type").text = "EXTRACONTENT_COMPAT_PACK"
    etree.SubElement(setup_root, "order").set("value", "37")

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


def _game(tmp_path: Path) -> Path:
    game = tmp_path / "game"
    game.mkdir(parents=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"enhanced")
    mods_update = game / "mods/update/update.rpf"
    mods_update.parent.mkdir(parents=True)
    mods_update.write_bytes(b"mods update")
    mptuner = game / bridge.STOCK_ARCHIVE_RELATIVE
    mptuner.parent.mkdir(parents=True)
    mptuner.write_bytes(b"effective mptuner archive fixture")
    return game


class FakeTool:
    def __init__(self, dlclist: bytes) -> None:
        self.dlclist = dlclist
        self.content, self.setup = _stock_metadata()
        self.packaged: dict[str, bytes] = {}
        self.commands: list[list[str]] = []
        self.fail: str | None = None
        self.fail_commands: set[str] = set()
        self.fail_after_commands: set[str] = set()
        self.extra_index_entry = False

    def __call__(
        self, _patcher: Path, arguments: list[str | Path], *,
        operation: str, timeout: int = 600,
    ) -> None:
        del operation, timeout
        args = [str(value) for value in arguments]
        self.commands.append(args)
        command = args[0]
        if command == self.fail or command in self.fail_commands:
            raise RuntimeError(f"injected {command} failure")
        if command == "extract-entry":
            archive = Path(args[2])
            entry = args[3]
            output = Path(args[4])
            output.parent.mkdir(parents=True, exist_ok=True)
            if archive.name == "update.rpf":
                output.write_bytes(self.dlclist)
            elif archive.name == "dlc.rpf" and "mptuner" in str(archive).casefold():
                output.write_bytes(self.content if entry == "content.xml" else self.setup)
            else:
                output.write_bytes(self.packaged[entry])
        elif command == "build-dlc":
            root = Path(args[1])
            self.packaged = {
                name: (root / name).read_bytes()
                for name in ("content.xml", "setup2.xml")
            }
            Path(args[2]).write_bytes(b"metadata-only bridge archive")
        elif command == "index-json":
            entries = [
                {"path": "content.xml"},
                {"path": "setup2.xml"},
            ]
            if self.extra_index_entry:
                entries.append({"path": "payload.rpf"})
            Path(args[3]).write_text(json.dumps({
                "schema_version": 1,
                "entries": entries,
                "warnings": [],
            }), encoding="utf-8")
        elif command == "register-dlc":
            root = etree.fromstring(self.dlclist)
            paths = root.find("Paths")
            assert paths is not None
            etree.SubElement(paths, "Item").text = bridge.PACK_ENTRY
            self.dlclist = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif command == "unregister-dlc":
            root = etree.fromstring(self.dlclist)
            paths = root.find("Paths")
            assert paths is not None
            wanted = bridge._normalized(bridge.PACK_ENTRY)
            for item in list(paths):
                if bridge._normalized(item.text or "") == wanted:
                    paths.remove(item)
            self.dlclist = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif command == "replace-entry":
            self.dlclist = Path(args[4]).read_bytes()
        else:  # pragma: no cover - catches accidental scope expansion
            raise AssertionError(f"Unexpected RPF operation: {command}")
        if command in self.fail_after_commands:
            raise RuntimeError(f"injected post-mutation {command} failure")


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    game = _game(tmp_path)
    patcher = tmp_path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    baseline = _dlclist(["dlcpacks:/mptuner/"])
    tool = FakeTool(baseline)
    monkeypatch.setattr(shared, "_run_tool", tool)
    return game, patcher, tool, baseline


def test_bridge_xml_is_metadata_only_inert_and_ordered_after_mptuner(tmp_path):
    root = bridge.create_stock_bridge_staging(tmp_path)
    topology = bridge.inspect_stock_bridge_topology(root)

    assert topology["asset_count"] == 0
    assert topology["data_file_count"] == 0
    assert topology["groups"] == ["GROUP_STARTUP", bridge.DORMANT_GROUP]
    assert topology["stock_changesets"] == [bridge.STOCK_CHANGESET]
    assert all(topology["checks"].values())
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))
    assert content.xpath("//dataFiles/Item") == []
    assert setup.xpath("string(/SSetupData/order/@value)") == "72"
    assert set(path.name for path in root.iterdir()) == {"content.xml", "setup2.xml"}

    with pytest.raises(FileExistsError):
        bridge.create_stock_bridge_staging(tmp_path)


def test_path_and_effective_archive_helpers_fail_closed(tmp_path, monkeypatch):
    game = _game(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert "DavisStockReferenceBootV4" in str(bridge._state_root(game))
    assert bridge._tool_path(None).name == "RpfPatcher.exe"

    override = game / "mods" / bridge.STOCK_ARCHIVE_RELATIVE
    override.parent.mkdir(parents=True)
    override.write_bytes(b"override")
    assert bridge._effective_mptuner_archive(game) == (override, "mods")
    override.unlink()
    stock = game / bridge.STOCK_ARCHIVE_RELATIVE
    stock.unlink()
    with pytest.raises(FileNotFoundError, match="effective Enhanced mptuner"):
        bridge._effective_mptuner_archive(game)

    host = game / "scripts/ThirdPartyMapHost.asi"
    host.parent.mkdir()
    host.write_bytes(b"host")
    assert "scripts/ThirdPartyMapHost.asi" in bridge._native_map_hosts(game)


def test_effective_stock_attestation_preserves_official_semantics(tmp_path):
    game = _game(tmp_path)
    content_bytes, setup_bytes = _stock_metadata()
    content = tmp_path / "content.xml"
    setup = tmp_path / "setup2.xml"
    content.write_bytes(content_bytes)
    setup.write_bytes(setup_bytes)
    archive = game / bridge.STOCK_ARCHIVE_RELATIVE

    result = bridge.inspect_effective_mptuner_metadata(
        content, setup,
        archive_path=archive, archive_source="stock", game=game,
    )

    assert result["device_name"] == "dlc_mpTuner"
    assert result["setup_order"] == 37
    assert result["stock_startup_changeset"] == "MPTUNER_AUTOGEN"
    assert result["stock_proxy"] == bridge.STOCK_PROXY
    assert result["changeset_name"] == "MPTUNER_MAP_UPDATE"
    assert result["official_semantics"]["requires_loading_screen"] is True
    assert result["official_semantics"]["use_cache_loader"] is True
    assert len(result["official_semantics"]["files_to_enable"]) == 10
    assert len(result["changeset_sha256"]) == 64


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("device", "setup identity changed"),
        ("order", "setup identity changed"),
        ("startup-group", "no longer registers MPTUNER_AUTOGEN"),
        ("map-group", "GROUP_MAP membership changed"),
        ("startup-proxy", "no longer enables the stock interior proxy"),
        ("proxy-type", "interior proxy contract changed"),
        ("route-count", "semantics changed"),
    ],
)
def test_stock_metadata_contract_drift_is_rejected(
    tmp_path, mutation, message,
):
    game = _game(tmp_path)
    raw_content, raw_setup = _stock_metadata()
    content = etree.fromstring(raw_content)
    setup = etree.fromstring(raw_setup)
    if mutation == "device":
        setup.find("deviceName").text = "dlc_wrong"
    elif mutation == "order":
        setup.find("order").set("value", "72")
    elif mutation == "startup-group":
        setup.xpath(
            "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
            "ContentChangeSets/Item"
        )[0].text = "WRONG"
    elif mutation == "map-group":
        setup.xpath(
            "//contentChangeSetGroups/Item[NameHash='GROUP_MAP']/"
            "ContentChangeSets/Item"
        )[0].text = "WRONG"
    elif mutation == "startup-proxy":
        content.xpath(
            "//contentChangeSets/Item[changeSetName='MPTUNER_AUTOGEN']/"
            "filesToEnable/Item"
        )[0].text = "wrong:/proxy.meta"
    elif mutation == "proxy-type":
        content.xpath(
            "//dataFiles/Item[filename='"
            + bridge.STOCK_PROXY
            + "']/fileType"
        )[0].text = "RPF_FILE"
    else:
        route = content.xpath(
            "//contentChangeSets/Item[changeSetName='MPTUNER_MAP_UPDATE']/"
            "mapChangeSetData/Item"
        )[0]
        route.addnext(etree.fromstring(etree.tostring(route)))
    content_path = tmp_path / "content.xml"
    setup_path = tmp_path / "setup2.xml"
    content_path.write_bytes(etree.tostring(content))
    setup_path.write_bytes(etree.tostring(setup))

    with pytest.raises(RuntimeError, match=message):
        bridge.inspect_effective_mptuner_metadata(
            content_path,
            setup_path,
            archive_path=game / bridge.STOCK_ARCHIVE_RELATIVE,
            archive_source="stock",
            game=game,
        )


def test_install_status_and_rollback_are_exact_and_never_authorize_execution(
    tmp_path, monkeypatch,
):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    prior = game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
    prior.mkdir(parents=True)
    (prior / "prior.bin").write_bytes(b"recover me")

    receipt = bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    destination = game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
    runtime = json.loads(
        (destination / bridge.RUNTIME_RECEIPT_NAME).read_text(encoding="utf-8")
    )
    assert receipt["status"] == "installed_boot_only_pending"
    assert runtime["schema"] == 4
    assert runtime["status"] == "verified"
    assert runtime["asset_count"] == 0
    assert runtime["data_file_count"] == 0
    assert runtime["activation"] == "disabled-phase-a-boot-only"
    assert runtime["native_group_execution_enabled"] is False
    assert runtime["runtime_ipl_requests_enabled"] is False
    assert runtime["gameconfig_changed"] is False
    assert runtime["groups"] == [{
        "property": "davis",
        "group": bridge.DORMANT_GROUP,
        "changesets": [bridge.STOCK_CHANGESET],
        "activation_enabled": False,
    }]
    assert set(path.name for path in destination.iterdir()) == {
        "dlc.rpf", bridge.MARKER_NAME, bridge.RUNTIME_RECEIPT_NAME,
    }
    assert str(tmp_path) not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(runtime)
    assert not any("gameconfig" in " ".join(command).casefold()
                   for command in tool.commands)
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    assert "EXECUTE_CONTENT_CHANGESET" not in source
    assert "REVERT_CONTENT_CHANGESET" not in source
    assert "REQUEST_IPL" not in source
    assert "launch_gta" not in source

    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["registration_count"] == 1
    assert status["old_registration_count"] == 0
    assert all(status["checks"].values())

    rolled_back = bridge.rollback_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert rolled_back["status"] == "rolled_back"
    assert tool.dlclist == baseline
    assert (destination / "prior.bin").read_bytes() == b"recover me"
    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert all(status["checks"].values())
    assert bridge.rollback_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    ) == rolled_back

    archived = state.with_name(
        state.name + ".rolled-back-" + rolled_back["transaction_id"][:12]
    )
    reinstalled = bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert reinstalled["status"] == bridge.INSTALL_STATUS
    assert reinstalled["transaction_id"] != rolled_back["transaction_id"]
    assert archived.is_dir()
    assert (archived / "rollback-receipt.json").is_file()
    assert (state / "install-receipt.json").is_file()
    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert all(status["checks"].values())


def test_registration_failure_restores_exact_baseline(tmp_path, monkeypatch):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    destination = game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
    destination.mkdir(parents=True)
    (destination / "prior.bin").write_bytes(b"original")
    tool.fail = "register-dlc"

    with pytest.raises(RuntimeError, match="injected register-dlc failure"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )

    assert tool.dlclist == baseline
    assert (destination / "prior.bin").read_bytes() == b"original"
    assert not state.exists()

    tool.fail = None
    retried = bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert retried["status"] == bridge.INSTALL_STATUS


def test_packaged_archive_index_rejects_hidden_payload(tmp_path, monkeypatch):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    tool.extra_index_entry = True
    with pytest.raises(RuntimeError, match="two-metadata-entry RPF"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )
    assert tool.dlclist == baseline
    assert not state.exists()


def test_failed_automatic_recovery_is_reported_and_checkpointed(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    tool.fail_after_commands = {"register-dlc"}
    tool.fail_commands = {"unregister-dlc"}
    with pytest.raises(RuntimeError, match="automatic rollback also failed"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )
    journal = json.loads((state / "journal.json").read_text(encoding="utf-8"))
    assert journal["status"] == "recovery_required"
    assert journal["install_error"] == "RuntimeError"
    assert "injected unregister-dlc failure" in journal["recovery_error"]


@pytest.mark.parametrize(
    "hazard",
    [
        "old-directory", "old-registration", "host",
        "missing-mptuner", "duplicate-mptuner",
    ],
)
def test_install_refuses_unsafe_map_baselines(tmp_path, monkeypatch, hazard):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    if hazard == "old-directory":
        (game / "mods/update/x64/dlcpacks/allin1_maps").mkdir(parents=True)
    elif hazard == "old-registration":
        tool.dlclist = _dlclist(["dlcpacks:/mptuner/", bridge.OLD_PACK_ENTRY])
    else:
        if hazard == "host":
            (game / "ALLIN1MapHost-Enhanced.asi").write_bytes(b"host")
        elif hazard == "missing-mptuner":
            tool.dlclist = _dlclist([])
        else:
            tool.dlclist = _dlclist([
                "dlcpacks:/mptuner/", "dlcpacks:/mptuner/",
            ])

    with pytest.raises(RuntimeError):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=tmp_path / f"state-{hazard}",
            patcher=patcher,
            process_probe=lambda: set(),
        )
    assert bridge._count_entry(tool.dlclist, bridge.PACK_ENTRY) == 0
    assert not (tmp_path / f"state-{hazard}").exists()


def test_install_refuses_running_game_and_changed_stock_semantics(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="must be closed"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=tmp_path / "running",
            patcher=patcher,
            process_probe=lambda: {"GTA5_Enhanced.exe"},
        )

    content = etree.fromstring(tool.content)
    target = content.xpath(
        "//contentChangeSets/Item[changeSetName='MPTUNER_MAP_UPDATE']/"
        "requiresLoadingScreen"
    )[0]
    target.set("value", "false")
    tool.content = etree.tostring(content, encoding="UTF-8", xml_declaration=True)
    with pytest.raises(RuntimeError, match="semantics changed"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=tmp_path / "changed-semantics",
            patcher=patcher,
            process_probe=lambda: set(),
        )
    assert bridge._count_entry(tool.dlclist, bridge.PACK_ENTRY) == 0
    assert not (tmp_path / "changed-semantics").exists()


def test_install_preflight_authorization_and_prerequisites(tmp_path):
    game = _game(tmp_path)
    patcher = tmp_path / "RpfPatcher.exe"
    with pytest.raises(PermissionError, match="Exact confirmation"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation="wrong",
            state_root=tmp_path / "unauthorized",
            patcher=patcher,
            process_probe=lambda: set(),
        )
    with pytest.raises(FileNotFoundError, match="RpfPatcher"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=tmp_path / "missing-tool",
            patcher=patcher,
            process_probe=lambda: set(),
        )
    patcher.write_bytes(b"tool")
    (game / "mods/update/update.rpf").unlink()
    with pytest.raises(RuntimeError, match="mods/update/update.rpf"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=tmp_path / "missing-update",
            patcher=patcher,
            process_probe=lambda: set(),
        )


def test_status_absent_and_corrupt_completed_rollback_fails_closed(tmp_path):
    game = _game(tmp_path)
    state = tmp_path / "state"
    absent = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=tmp_path / "missing.exe",
        process_probe=lambda: set(),
    )
    assert absent["status"] == "absent"
    assert absent["healthy"] is True
    state.mkdir()
    rolled_back = {
        "schema": 4,
        "canary_id": bridge.CANARY_ID,
        "status": "rolled_back",
    }
    (state / "rollback-receipt.json").write_text(
        json.dumps(rolled_back), encoding="utf-8",
    )
    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=tmp_path / "missing.exe",
        process_probe=lambda: {"GTA5_Enhanced.exe"},
    )
    assert status["status"] == "rolled_back"
    assert status["game_running"] is True
    assert status["healthy"] is False
    assert status["checks"] == {"rollback_receipt": False}


def test_install_does_not_supersede_unverified_completed_rollback(
    tmp_path, monkeypatch,
):
    game, patcher, tool, baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    state.mkdir()
    corrupt = {
        "schema": 4,
        "canary_id": bridge.CANARY_ID,
        "transaction_id": "a" * 32,
        "status": "rolled_back",
    }
    receipt = state / "rollback-receipt.json"
    receipt.write_text(json.dumps(corrupt), encoding="utf-8")

    with pytest.raises(RuntimeError, match="cannot be verified"):
        bridge.install_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.INSTALL_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )

    assert state.is_dir()
    assert json.loads(receipt.read_text(encoding="utf-8")) == corrupt
    assert not list(tmp_path.glob("state.rolled-back-*"))
    assert tool.dlclist == baseline
    assert tool.commands == []


def test_status_detects_tamper_and_strict_rollback_refuses(tmp_path, monkeypatch):
    game, patcher, _tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    runtime = (
        game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
        / bridge.RUNTIME_RECEIPT_NAME
    )
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["groups"][0]["activation_enabled"] = True
    runtime.write_text(json.dumps(payload), encoding="utf-8")

    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is False
    assert status["checks"]["runtime_receipt"] is False
    with pytest.raises(RuntimeError, match="changed after installation"):
        bridge.rollback_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.ROLLBACK_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )


def test_rollback_validates_original_pack_backup_before_any_mutation(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    destination = game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
    destination.mkdir(parents=True)
    (destination / "prior.bin").write_bytes(b"original")
    bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    active_archive = (destination / "dlc.rpf").read_bytes()
    registered = tool.dlclist
    (state / "original-pack/prior.bin").write_bytes(b"corrupt")

    with pytest.raises(RuntimeError, match="backup is missing or corrupt"):
        bridge.rollback_davis_stock_reference_boot_canary(
            game,
            confirmation=bridge.ROLLBACK_CONFIRMATION,
            state_root=state,
            patcher=patcher,
            process_probe=lambda: set(),
        )
    assert (destination / "dlc.rpf").read_bytes() == active_archive
    assert tool.dlclist == registered


def test_interrupted_journal_recovery_preserves_unrelated_dlclist_changes(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    (state / "install-receipt.json").unlink()
    tool.dlclist = _dlclist([
        "dlcpacks:/mptuner/", bridge.PACK_ENTRY, "dlcpacks:/unrelated/",
    ])
    result = bridge.rollback_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert result["status"] == "rolled_back"
    assert shared._dlclist_items(tool.dlclist) == [
        "dlcpacks:/mptuner/", "dlcpacks:/unrelated/",
    ]


def test_status_and_rollback_coexist_with_grapeseed_and_later_dlc_entries(
    tmp_path, monkeypatch,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    grapeseed = "dlcpacks:/allin1_grapeseed_stock_bridge/"
    unrelated = "dlcpacks:/unrelated_after_davis/"
    tool.dlclist = _dlclist([
        "dlcpacks:/mptuner/", bridge.PACK_ENTRY, grapeseed, unrelated,
    ])

    active = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert active["healthy"] is True
    assert active["registration_count"] == 1
    assert all(active["checks"].values())

    bridge.rollback_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.ROLLBACK_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert shared._dlclist_items(tool.dlclist) == [
        "dlcpacks:/mptuner/", grapeseed, unrelated,
    ]

    later = "dlcpacks:/installed_after_davis_rollback/"
    tool.dlclist = _dlclist([
        "dlcpacks:/mptuner/", grapeseed, unrelated, later,
    ])
    rolled_back = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert rolled_back["healthy"] is True
    assert all(rolled_back["checks"].values())


@pytest.mark.parametrize("target", ["archive", "marker", "receipt", "dlclist"])
def test_status_verifies_every_installed_evidence(
    tmp_path, monkeypatch, target,
):
    game, patcher, tool, _baseline = _fixture(tmp_path, monkeypatch)
    state = tmp_path / "state"
    bridge.install_davis_stock_reference_boot_canary(
        game,
        confirmation=bridge.INSTALL_CONFIRMATION,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    destination = game / "mods/update/x64/dlcpacks" / bridge.PACK_NAME
    if target == "archive":
        (destination / "dlc.rpf").write_bytes(b"changed")
        check = "archive"
    elif target == "marker":
        (destination / bridge.MARKER_NAME).write_text(
            "activation=enabled\n", encoding="utf-8",
        )
        check = "marker"
    elif target == "receipt":
        (destination / bridge.RUNTIME_RECEIPT_NAME).write_text(
            "{}", encoding="utf-8",
        )
        check = "runtime_receipt"
    else:
        tool.dlclist = _dlclist([
            "dlcpacks:/mptuner/", bridge.PACK_ENTRY, bridge.PACK_ENTRY,
        ])
        check = "dlclist_registration"

    status = bridge.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is False
    assert status["checks"][check] is False


def test_cli_requires_exact_stock_boot_authorization(tmp_path, monkeypatch):
    game = _game(tmp_path)
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run")

    monkeypatch.setattr(
        bridge, "install_davis_stock_reference_boot_canary", unexpected,
    )
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(
        cli.main,
        [
            "--config", str(tmp_path / "missing.toml"),
            "map-canary", "stock-boot-install",
            "--gta-path", str(game), "--yes",
            "--confirm-canary", "wrong",
        ],
    )
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert called is False

    result = CliRunner().invoke(
        cli.main,
        [
            "--config", str(tmp_path / "missing.toml"),
            "map-canary", "stock-boot-rollback",
            "--gta-path", str(game), "--yes",
            "--confirm-canary", "wrong",
        ],
    )
    assert result.exit_code != 0
    assert "requires --yes" in result.output
