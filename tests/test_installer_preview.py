"""End-to-end orchestration tests for preview packaging and helper tools."""

from pathlib import Path
import json
import struct
from unittest.mock import Mock

import pytest

from allin1 import installer
from allin1.generators import dlc_maps
from allin1.preview_assets import PreviewMergeResult


def _write_pe(path, *, size=4096):
    payload = bytearray(size)
    payload[:2] = b"MZ"
    struct.pack_into("<I", payload, 0x3C, 0x80)
    payload[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", payload, 0x84, 0x8664)
    path.write_bytes(payload)


def _layout(tmp_path, monkeypatch):
    project = tmp_path / "project"
    dist = project / "script" / "dist"
    previews = dist / "previews"
    previews.mkdir(parents=True)
    (previews / "alpha.png").touch()
    data = project / "data"
    data.mkdir()
    (data / "vehicles.toml").write_text(
        '[[vehicles]]\nmodel="alpha"\nname="Alpha"\nclass="super"\nmanufacturer="A"\n'
    )
    (data / "weapons.toml").write_text(
        '[[weapons]]\nname="WEAPON_TEST"\nlabel="Test"\ncategory="pistols"\nprice=10\n'
    )
    tools = project / "tools"
    (tools / "RpfPatcher").mkdir(parents=True)
    (tools / "YTDToolio.exe").touch()
    (tools / "RpfPatcher" / "RpfPatcher.exe").touch()
    monkeypatch.setattr(installer, "_PROJECT_ROOT", project)
    monkeypatch.setattr(installer, "_SCRIPT_DIST_DIR", dist)
    monkeypatch.setattr(installer, "_TOOLS_DIR", tools)
    return project, dist, tools


def _enhanced_gameconfig_xml() -> bytes:
    pools = {
        "DrawableStore": 81000,
        "DwdStore": 20500,
        "FragmentStore": 42000,
        "InteriorProxy": 1200,
        "IplStore": 3000,
        "MaxLoadedInfo": 32000,
        "MapDataStore": 10020,
        "MetaDataStore": 3200,
        "StaticBounds": 15000,
        "TxdStore": 80200,
        "ScaleformStore": 820,
    }
    entries = "".join(
        f"<Item><PoolName>{name}</PoolName><PoolSize value=\"{value}\" /></Item>"
        for name, value in pools.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<fwAllConfigs><ConfigArray><Item><Config type="CGameConfig">'
        f'<PoolSizes><Entries>{entries}</Entries></PoolSizes>'
        '</Config></Item>'
        '<Item><Build>any</Build><Platforms>x64</Platforms>'
        '<Config type="CGameConfig"><PoolSizes><Entries>'
        '<Item><PoolName>ScaleformStore</PoolName>'
        '<PoolSize value="1000" /></Item>'
        '</Entries></PoolSizes></Config></Item>'
        '</ConfigArray></fwAllConfigs>'
    ).encode("utf-8")


def test_enhanced_gameconfig_allows_cross_scope_platform_override():
    pools = installer._enhanced_gameconfig_pools(
        _enhanced_gameconfig_xml().decode("utf-8")
    )

    assert pools["ScaleformStore"] == 1000
    assert pools["FragmentStore"] == 42000


def test_enhanced_gameconfig_rejects_duplicate_within_one_scope():
    source = _enhanced_gameconfig_xml().decode("utf-8").replace(
        '<Item><PoolName>ScaleformStore</PoolName>'
        '<PoolSize value="1000" /></Item>',
        '<Item><PoolName>ScaleformStore</PoolName>'
        '<PoolSize value="1000" /></Item>'
        '<Item><PoolName>ScaleformStore</PoolName>'
        '<PoolSize value="1100" /></Item>',
    )

    with pytest.raises(ValueError, match="duplicate within one Entries scope"):
        installer._enhanced_gameconfig_pools(source)


def test_enhanced_gameconfig_still_rejects_negative_pool_size():
    source = _enhanced_gameconfig_xml().decode("utf-8").replace(
        '<PoolSize value="1000" />', '<PoolSize value="-1" />', 1,
    )

    with pytest.raises(ValueError, match="negative value"):
        installer._enhanced_gameconfig_pools(source)


def test_enhanced_gameconfig_rejects_pool_shape_outside_schema_scope():
    source = (
        '<fwAllConfigs><ConfigArray><Item>'
        '<PoolName>ScaleformStore</PoolName><PoolSize value="1000" />'
        '</Item></ConfigArray></fwAllConfigs>'
    )

    with pytest.raises(ValueError, match="outside Config/PoolSizes/Entries"):
        installer._enhanced_gameconfig_pools(source)


def _dlclist_xml(*, registered: bool = False) -> bytes:
    entry = (
        "<Item>dlcpacks:/allin1_maps/</Item>" if registered else ""
    )
    return (
        '<?xml version="1.0"?><SMandatoryPacksData><Paths>'
        f'<Item>dlcpacks:/base/</Item>{entry}</Paths></SMandatoryPacksData>'
    ).encode("utf-8")


def _known_sparse_onigiri_gameconfig() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<CGameConfig><pools>
<Item><Name>CVehicle</Name><Size value="512" /></Item>
<Item><Name>CVehicleModelInfo</Name><Size value="900" /></Item>
<Item><Name>CHandlingDataMgr</Name><Size value="900" /></Item>
</pools></CGameConfig>"""


@pytest.mark.parametrize("missing,warning", [
    ("previews", "Preview images not found"),
    ("rpf", "RpfPatcher.exe missing"),
])
def test_preview_deploy_reports_missing_inputs(tmp_path, monkeypatch, missing, warning):
    _project, dist, tools = _layout(tmp_path, monkeypatch)
    if missing == "previews":
        (dist / "previews").rename(dist / "gone")
    else:
        (tools / "RpfPatcher" / "RpfPatcher.exe").unlink()
    result = installer.InstallResult(tmp_path)
    installer._deploy_preview_dlc(tmp_path, result)
    assert any(warning in item for item in result.warnings)


def test_preview_deploy_builds_and_deploys_curated_assets(tmp_path, monkeypatch):
    _project, dist, _tools = _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import ytd_builder

    merge = Mock(return_value=PreviewMergeResult(1, ("bad.png",), ()))
    monkeypatch.setattr(preview_assets, "merge_previews", merge)

    def build(_source, _logo, output, _tools, models, **_kwargs):
        output.mkdir(parents=True)
        ytd = output / "allin1_prev_01.ytd"
        ytd.write_bytes(b"ytd")
        assert models == ["alpha"]
        return [ytd]
    monkeypatch.setattr(ytd_builder, "build_ytd_files", build)

    calls = []
    def run(args, **_kwargs):
        calls.append(args)
        if "build-dlc" in args:
            Path(args[3]).write_bytes(b"valid-dlc-rpf")
        return Mock(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=True)

    assert installer._deploy_preview_dlc(tmp_path, result) is True

    assert "Ignored 1 invalid preview capture(s)." in result.warnings
    assert merge.call_args_list[0].args[0] == [dist / "previews"]
    assert merge.call_args_list[1].args[0] == [dist / "weapon_previews"]
    assert merge.call_args_list[2].args[0] == [dist / "equipment_previews"]
    assert merge.call_args_list[3].args[0] == [dist / "world_asset_previews"]
    assert any("build-dlc" in args for args in calls)
    assert any("verify-dlc" in args for args in calls)
    assert any("patch" in args for args in calls)
    assert (tmp_path / "mods/update/x64/dlcpacks/allin1_previews/dlc.rpf").exists()


@pytest.mark.parametrize("stage", ["convert-gen9", "build-dlc", "verify-dlc", "patch"])
def test_preview_deploy_surfaces_tool_failures(tmp_path, monkeypatch, stage):
    _layout(tmp_path, monkeypatch)
    from allin1 import preview_assets
    from allin1.generators import ytd_builder
    monkeypatch.setattr(preview_assets, "merge_previews",
                        Mock(return_value=PreviewMergeResult(1, (), ())))
    def build(_a, _b, output, _d, _e, **_kwargs):
        output.mkdir(parents=True, exist_ok=True)
        ytd = output / "one.ytd"
        ytd.write_bytes(b"ytd")
        return [ytd]
    monkeypatch.setattr(ytd_builder, "build_ytd_files", build)
    def run(args, **_kwargs):
        if "build-dlc" in args and stage != "build-dlc":
            Path(args[3]).write_bytes(b"valid-dlc-rpf")
        return Mock(returncode=1 if stage in args else 0, stdout="", stderr="boom")
    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=(stage == "convert-gen9"))
    with pytest.raises(RuntimeError, match=stage):
        installer._deploy_preview_dlc(tmp_path, result)


def test_openrpf_detection_requires_nonempty_plugin_and_loader(tmp_path):
    _write_pe(tmp_path / "OpenRPF.asi")
    assert installer._check_openrpf(tmp_path, enhanced=True) is False
    _write_pe(tmp_path / "xinput1_4.dll")
    assert installer._check_openrpf(tmp_path, enhanced=True) is True
    _write_pe(tmp_path / "OpenIV.asi")
    assert installer._check_openrpf(tmp_path, enhanced=True) is False


def test_remove_preview_pack_only_removes_owned_directories(tmp_path):
    owned = tmp_path / "mods/update/x64/dlcpacks/allin1_previews"
    unrelated = tmp_path / "mods/update/x64/dlcpacks/user_pack"
    owned.mkdir(parents=True); unrelated.mkdir(parents=True)
    removed = installer._remove_preview_pack(tmp_path)
    assert removed == [owned]
    assert not owned.exists() and unrelated.exists()


@pytest.mark.parametrize(
    "enhanced", [True, False],
)
def test_map_deploy_builds_registered_zero_payload_reference_bridge(
    tmp_path, monkeypatch, enhanced,
):
    _project, _dist, _tools = _layout(tmp_path, monkeypatch)
    calls = []
    stock_update = tmp_path / "update/update.rpf"
    stock_update.parent.mkdir(parents=True)
    stock_update.write_bytes(b"complete-stock-update-rpf")
    sparse_override = (
        tmp_path / "onigiri/common/data/gameconfig.xml"
    )
    if enhanced:
        sparse_override.parent.mkdir(parents=True)
        sparse_override.write_bytes(_known_sparse_onigiri_gameconfig())
    state = {
        "gameconfig": _enhanced_gameconfig_xml(),
        "dlclist": _dlclist_xml(),
        "registered": False,
    }
    source_identities = {
        (asset.source_pack, asset.source_archive_name)
        for asset in dlc_maps.MAP_ASSETS
    } | {
        (pack, "dlc.rpf") for pack in dlc_maps.ROCKSTAR_DEVICE_BY_PACK
    }
    for pack, archive_name in source_identities:
        source = (
            tmp_path / "update/x64/dlcpacks" / pack / archive_name
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"installed-rockstar-archive")
    stale_receipt = (
        tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
        / installer._MAP_RUNTIME_RECEIPT
    )
    stale_receipt.parent.mkdir(parents=True, exist_ok=True)
    stale_receipt.write_text(
        '{"status":"verified","layout":"unsafe-old-startup"}',
        encoding="utf-8",
    )

    staged = {}

    def run(args, **_kwargs):
        calls.append(args)
        action = args[1]
        if action == "extract-entry":
            entry = args[4]
            output = Path(args[5])
            output.parent.mkdir(parents=True, exist_ok=True)
            if entry == installer._MAP_GAMECONFIG_ENTRY:
                output.write_bytes(state["gameconfig"])
            elif entry == installer._MAP_DLCLIST_ENTRY:
                output.write_bytes(_dlclist_xml(
                    registered=state["registered"],
                ))
            elif entry in {"content.xml", "setup2.xml"}:
                source = Path(args[3])
                if source.name == "allin1_maps.bridge.rpf":
                    output.write_bytes(staged[entry])
                else:
                    output.write_bytes(b"verified-rockstar-metadata")
        elif action == "replace-entry":
            entry = args[4]
            if entry == installer._MAP_GAMECONFIG_ENTRY:
                state["gameconfig"] = Path(args[5]).read_bytes()
            elif entry == installer._MAP_DLCLIST_ENTRY:
                state["dlclist"] = Path(args[5]).read_bytes()
                state["registered"] = b"allin1_maps" in state["dlclist"]
        elif action == "patch":
            state["registered"] = True
            mods_update = tmp_path / "mods/update/update.rpf"
            mods_update.parent.mkdir(parents=True, exist_ok=True)
            mods_update.write_bytes(b"patched-update-rpf")
        elif action == "unpatch":
            state["registered"] = False
        if action == "build-dlc":
            root = Path(args[2])
            staged["content.xml"] = (root / "content.xml").read_bytes()
            staged["setup2.xml"] = (root / "setup2.xml").read_bytes()
            Path(args[3]).write_bytes(b"valid-map-dlc")
        return Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(
        dlc_maps, "validate_reference_source_metadata",
        Mock(return_value=(True, "verified")),
    )
    monkeypatch.setattr(
        dlc_maps, "validate_reference_pack_against_source_metadata",
        Mock(return_value=(True, "verified")),
    )

    def create_reference(work, _metadata):
        root = work / dlc_maps.DLC_NAME
        root.mkdir(parents=True)
        (root / "content.xml").write_bytes(b"<content />")
        (root / "setup2.xml").write_bytes(b"<setup />")
        return root

    monkeypatch.setattr(
        dlc_maps, "create_reference_dlc_pack", create_reference,
    )
    # This installer transaction test stubs Rockstar metadata extraction and
    # validation, so it must also stub the metadata-derived receipt.  Detailed
    # closure parsing and receipt validation are covered in test_dlc_maps.py.
    receipt_groups = []
    for definition in dlc_maps.MAP_CHANGESETS:
        references = [
            asset.source_filename for asset in dlc_maps.MAP_ASSETS
            if asset.file_type == "RPF_FILE"
            and asset.change_set_key == definition.key
        ]
        routes = []
        for route_index, (pack, changeset) in enumerate(
            dlc_maps.OFFICIAL_CHANGESET_ROUTES[definition.key]
        ):
            routes.append({
                "pack": pack,
                "changeset": changeset,
                "associated_maps": [],
                "files_to_invalidate": [],
                "files_to_disable": [],
                "files_to_enable": references if route_index == 0 else [],
                "requires_loading_screen": False,
                "loading_screen_context": "",
                "use_cache_loader": False,
            })
        receipt_groups.append({
            "property": definition.key,
            "group": definition.group_name,
            "references": references,
            "routes": routes,
        })
    assert dlc_maps.validate_reference_group_receipt(receipt_groups) == (
        True, "verified",
    )
    monkeypatch.setattr(
        dlc_maps, "reference_group_receipt",
        Mock(return_value=receipt_groups),
    )
    monkeypatch.setattr(
        installer, "_dlclist_registered_pack_names",
        Mock(return_value={
            *dlc_maps.ROCKSTAR_DEVICE_BY_PACK,
            dlc_maps.DLC_NAME,
        }),
    )
    activate = Mock(side_effect=AssertionError(
        "production map deploy must not call startup activation",
    ))
    monkeypatch.setattr(
        installer, "_activate_enhanced_standalone_map_dlc", activate,
    )
    result = installer.InstallResult(tmp_path, is_enhanced=enhanced)
    assert installer._deploy_standalone_map_dlc(tmp_path, result) is True
    activate.assert_not_called()
    assert any("build-dlc" in args for args in calls)
    deployed = tmp_path / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf"
    assert deployed.read_bytes() == b"valid-map-dlc"
    marker = (deployed.parent / dlc_maps.ACTIVE_MARKER).read_text(
        encoding="utf-8",
    )
    assert f"layout={dlc_maps.REFERENCE_PACK_LAYOUT}" in marker
    assert "group_map_binding=false" in marker
    assert "asset_count=0" in marker
    assert f"reference_count={len(dlc_maps.MAP_ASSETS)}" in marker
    unpatch_call = next(args for args in calls if args[1] == "unpatch")
    assert unpatch_call[-1] == "allin1_maps"
    assert any(args[1] == "patch" for args in calls)
    assert not any(args[1] == "replace-entry" for args in calls)
    assert "archive_registration=metadata-bridge" in marker
    assert "activation=property-group-runtime" in marker
    receipt = json.loads(stale_receipt.read_text(encoding="utf-8"))
    assert receipt["asset_count"] == 0
    assert receipt["reference_count"] == len(dlc_maps.MAP_ASSETS)
    assert len(receipt["source_archives"]) == 6
    assert not result.warnings
    if enhanced:
        # Quarantine does not alter or retire an unrelated loose gameconfig.
        assert sparse_override.read_bytes() == _known_sparse_onigiri_gameconfig()
        assert not sparse_override.with_name(
            "gameconfig.xml.allin1-retired.bak"
        ).exists()


def test_enhanced_map_activation_rolls_back_both_archive_payloads(
    tmp_path, monkeypatch,
):
    _project, _dist, _tools = _layout(tmp_path, monkeypatch)
    stock = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    stock.parent.mkdir(parents=True)
    mods.parent.mkdir(parents=True)
    stock.write_bytes(b"stock-update")
    mods.write_bytes(b"existing-full-mods-update")
    output_rpf = tmp_path / "built-map.rpf"
    output_rpf.write_bytes(b"verified-map")
    work = tmp_path / "transaction"
    work.mkdir()
    sparse_override = tmp_path / "onigiri/common/data/gameconfig.xml"
    sparse_override.parent.mkdir(parents=True)
    sparse_override.write_bytes(_known_sparse_onigiri_gameconfig())

    original_gameconfig = _enhanced_gameconfig_xml()
    original_dlclist = _dlclist_xml()
    state = {
        "gameconfig": original_gameconfig,
        "dlclist": original_dlclist,
        "registered": False,
        "dlclist_extracts": 0,
    }
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        action = args[1]
        if action == "extract-entry":
            entry = args[4]
            output = Path(args[5])
            if entry == installer._MAP_GAMECONFIG_ENTRY:
                output.write_bytes(state["gameconfig"])
            else:
                state["dlclist_extracts"] += 1
                if state["dlclist_extracts"] == 2:
                    return Mock(
                        returncode=9, stdout="", stderr="verification blocked",
                    )
                output.write_bytes(state["dlclist"])
        elif action == "replace-entry":
            entry = args[4]
            payload = Path(args[5]).read_bytes()
            if entry == installer._MAP_GAMECONFIG_ENTRY:
                state["gameconfig"] = payload
            else:
                state["dlclist"] = payload
                state["registered"] = b"allin1_maps" in payload
        elif action == "patch":
            state["registered"] = True
        return Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=True)
    with pytest.raises(RuntimeError, match="Re-extract registered dlclist"):
        installer._activate_enhanced_standalone_map_dlc(
            tmp_path,
            result,
            output_rpf,
            work,
            asset_count=3,
        )

    assert state["gameconfig"] == original_gameconfig
    assert state["dlclist"] == original_dlclist
    assert state["registered"] is False
    assert sparse_override.read_bytes() == _known_sparse_onigiri_gameconfig()
    assert sparse_override.with_name(
        "gameconfig.xml.allin1-retired.bak"
    ).read_bytes() == _known_sparse_onigiri_gameconfig()
    receipt = (
        tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
        / installer._MAP_RUNTIME_RECEIPT
    )
    assert not receipt.exists()
    restored_entries = [
        args[4] for args in calls if args[1] == "replace-entry"
    ][-2:]
    assert restored_entries == [
        installer._MAP_GAMECONFIG_ENTRY,
        installer._MAP_DLCLIST_ENTRY,
    ]


def test_quarantine_retires_only_the_verified_startup_map_pool_profile(
    tmp_path, monkeypatch,
):
    _project, _dist, _tools = _layout(tmp_path, monkeypatch)
    mods = tmp_path / "mods/update/update.rpf"
    mods.parent.mkdir(parents=True)
    mods.write_bytes(b"existing-full-mods-update")
    pack = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    pack.mkdir(parents=True)
    (pack / "dlc.rpf").write_bytes(b"verified-map")
    (pack / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n",
        encoding="utf-8",
    )
    receipt_path = pack / dlc_maps.RUNTIME_RECEIPT
    receipt_path.write_text("{}", encoding="utf-8")
    receipt = {
        "pools": {
            "FragmentStore": {"before": 42000, "after": 52000},
            "MetaDataStore": {"before": 3200, "after": 4000},
        },
    }
    monkeypatch.setattr(
        dlc_maps, "validate_runtime_activation_receipt",
        lambda *_args, **_kwargs: (True, "verified", receipt),
    )
    state = {
        "gameconfig": _enhanced_gameconfig_xml()
            .replace(b'value="42000"', b'value="52000"')
            .replace(b'value="3200"', b'value="4000"'),
    }
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if args[1] == "extract-entry":
            Path(args[5]).write_bytes(state["gameconfig"])
        elif args[1] == "replace-entry":
            state["gameconfig"] = Path(args[5]).read_bytes()
        return Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    result = installer.InstallResult(tmp_path, is_enhanced=True)
    work = tmp_path / "work"
    work.mkdir()

    assert installer._restore_verified_startup_map_pool_profile(
        tmp_path, work, result,
    ) is True
    pools = installer._enhanced_gameconfig_pools(
        state["gameconfig"].decode("utf-8-sig")
    )
    assert pools["FragmentStore"] == 42000
    assert pools["MetaDataStore"] == 3200
    assert not receipt_path.exists()
    assert [args[1] for args in calls] == [
        "extract-entry", "replace-entry", "extract-entry",
    ]


def test_quarantine_preserves_gameconfig_without_a_verified_pool_receipt(
    tmp_path, monkeypatch,
):
    _project, _dist, _tools = _layout(tmp_path, monkeypatch)
    pack = tmp_path / "mods/update/x64/dlcpacks/allin1_maps"
    pack.mkdir(parents=True)
    (pack / "dlc.rpf").write_bytes(b"untrusted-map")
    (pack / dlc_maps.ACTIVE_MARKER).write_text(
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n",
        encoding="utf-8",
    )
    (pack / dlc_maps.RUNTIME_RECEIPT).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        dlc_maps, "validate_runtime_activation_receipt",
        lambda *_args, **_kwargs: (False, "fingerprint mismatch", {}),
    )
    monkeypatch.setattr(
        installer.subprocess, "run",
        Mock(side_effect=AssertionError("gameconfig must remain untouched")),
    )
    result = installer.InstallResult(tmp_path, is_enhanced=True)

    assert installer._restore_verified_startup_map_pool_profile(
        tmp_path, tmp_path, result,
    ) is False
    assert any("left unchanged" in warning for warning in result.warnings)


def test_enhanced_map_activation_rejects_sparse_gameconfig_before_registration(
    tmp_path, monkeypatch,
):
    _project, _dist, _tools = _layout(tmp_path, monkeypatch)
    stock = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    stock.parent.mkdir(parents=True)
    mods.parent.mkdir(parents=True)
    stock.write_bytes(b"stock-update")
    mods.write_bytes(b"existing-full-mods-update")
    output_rpf = tmp_path / "built-map.rpf"
    output_rpf.write_bytes(b"verified-map")
    work = tmp_path / "transaction"
    work.mkdir()
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        if args[1] == "extract-entry":
            output = Path(args[5])
            if args[4] == installer._MAP_GAMECONFIG_ENTRY:
                output.write_text(
                    "<CGameConfig><pools /></CGameConfig>", encoding="utf-8",
                )
            else:
                output.write_bytes(_dlclist_xml())
        return Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(ValueError, match="complete fwAllConfigs"):
        installer._activate_enhanced_standalone_map_dlc(
            tmp_path,
            installer.InstallResult(tmp_path, is_enhanced=True),
            output_rpf,
            work,
            asset_count=3,
        )
    assert not any(args[1] == "patch" for args in calls)


def test_custom_onigiri_gameconfig_is_never_retired(tmp_path):
    override = tmp_path / "onigiri/common/data/gameconfig.xml"
    override.parent.mkdir(parents=True)
    custom = (
        b"<fwAllConfigs><ConfigArray><Item><PoolName>FragmentStore</PoolName>"
        b"<PoolSize value=\"99999\" /></Item></ConfigArray></fwAllConfigs>"
    )
    override.write_bytes(custom)

    with pytest.raises(RuntimeError, match="custom onigiri"):
        installer._retire_known_sparse_onigiri_gameconfig(tmp_path)

    assert override.read_bytes() == custom
    assert not override.with_name(
        "gameconfig.xml.allin1-retired.bak"
    ).exists()


def test_preview_archive_rollback_restores_existing_bytes(tmp_path):
    archive = tmp_path / "mods/update/update.rpf"
    backup = tmp_path / "mods/update/update.rpf.allin1-previews.bak"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"damaged"); backup.write_bytes(b"original")
    installer._restore_preview_archive(archive, backup, True)
    assert archive.read_bytes() == b"original"


def test_preview_archive_rollback_removes_new_partial_archive(tmp_path):
    archive = tmp_path / "mods/update/update.rpf"
    archive.parent.mkdir(parents=True); archive.write_bytes(b"partial")
    installer._restore_preview_archive(archive, archive.with_suffix(".bak"), False)
    assert not archive.exists()


def test_refresh_stale_mods_archive_uses_current_base_transactionally(tmp_path):
    base = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    base.parent.mkdir(parents=True); mods.parent.mkdir(parents=True)
    base.write_bytes(b"current-game-archive")
    mods.write_bytes(b"old-mod-archive")
    import os
    os.utime(mods, ns=(1_000_000_000, 1_000_000_000))
    os.utime(base, ns=(5_000_000_000, 5_000_000_000))

    assert installer._refresh_stale_mods_archive(tmp_path, mods) is True
    assert mods.read_bytes() == b"current-game-archive"
    assert not mods.with_name("update.rpf.allin1-refresh.tmp").exists()


def test_refresh_current_mods_archive_leaves_it_untouched(tmp_path):
    base = tmp_path / "update/update.rpf"
    mods = tmp_path / "mods/update/update.rpf"
    base.parent.mkdir(parents=True); mods.parent.mkdir(parents=True)
    base.write_bytes(b"base"); mods.write_bytes(b"custom-current")
    import os
    os.utime(base, ns=(1_000_000_000, 1_000_000_000))
    os.utime(mods, ns=(5_000_000_000, 5_000_000_000))

    assert installer._refresh_stale_mods_archive(tmp_path, mods) is False
    assert mods.read_bytes() == b"custom-current"


@pytest.mark.parametrize("helper", [
    installer._patch_dlclist_rpf, installer._unpatch_dlclist_rpf,
    installer._remove_preview_ytds,
])
def test_rpf_helpers_handle_success_failure_and_exception(tmp_path, monkeypatch, helper):
    _project, _dist, tools = _layout(tmp_path, monkeypatch)
    patcher = tools / "RpfPatcher" / "RpfPatcher.exe"
    result = installer.InstallResult(tmp_path)
    command = {
        installer._patch_dlclist_rpf: [
            str(patcher), "patch", str(tmp_path), "allin1_previews",
        ],
        installer._unpatch_dlclist_rpf: [
            str(patcher), "unpatch", str(tmp_path),
        ],
        installer._remove_preview_ytds: [
            str(patcher), "remove-ytd", str(tmp_path), "allin1_",
        ],
    }[helper]

    success = Mock(return_value=Mock(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(installer, "run_hidden", success)
    returned = (
        helper(tmp_path, result)
        if helper is installer._patch_dlclist_rpf else helper(tmp_path)
    )
    expected_timeout = (
        600
        if helper in {
            installer._patch_dlclist_rpf,
            installer._unpatch_dlclist_rpf,
        }
        else 120
    )
    success.assert_called_once_with(
        command, capture_output=True, text=True, timeout=expected_timeout,
    )
    if helper in {installer._patch_dlclist_rpf, installer._unpatch_dlclist_rpf}:
        assert returned is True

    failure = Mock(return_value=Mock(returncode=2, stdout="", stderr="bad"))
    monkeypatch.setattr(installer, "run_hidden", failure)
    returned = (
        helper(tmp_path, result)
        if helper is installer._patch_dlclist_rpf else helper(tmp_path)
    )
    failure.assert_called_once_with(
        command, capture_output=True, text=True, timeout=expected_timeout,
    )
    if helper in {installer._patch_dlclist_rpf, installer._unpatch_dlclist_rpf}:
        assert returned is False
        if helper is installer._patch_dlclist_rpf:
            assert result.warnings[-1] == "Failed to patch dlclist.xml: bad"

    crashed = Mock(side_effect=OSError("failed"))
    monkeypatch.setattr(installer, "run_hidden", crashed)
    returned = (
        helper(tmp_path, result)
        if helper is installer._patch_dlclist_rpf else helper(tmp_path)
    )
    crashed.assert_called_once_with(
        command, capture_output=True, text=True, timeout=expected_timeout,
    )
    if helper in {installer._patch_dlclist_rpf, installer._unpatch_dlclist_rpf}:
        assert returned is False
        if helper is installer._patch_dlclist_rpf:
            assert result.warnings[-1] == "Could not patch dlclist.xml: failed"
