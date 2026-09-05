import hashlib
import json
from copy import deepcopy

from lxml import etree
import pytest

from allin1.generators import dlc_maps


def test_standalone_map_pack_references_only_its_local_device(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    assert sorted(path.name for path in root.iterdir()) == [
        "content.xml", "setup2.xml",
    ]

    content = etree.parse(str(root / "content.xml"))
    filenames = content.xpath("//dataFiles/Item/filename/text()")
    enabled = content.xpath("//filesToEnable/Item/text()")
    assert set(filenames) == set(enabled)
    assert len(enabled) == len(set(enabled))
    assert len(filenames) == len(set(name.lower() for name in filenames))
    assert all(name.startswith(f"{dlc_maps.DEVICE_NAME}:/") for name in filenames)
    assert any("yacht" in name for name in filenames)
    assert any("dlc_int_01_tr.rpf" in name for name in filenames)
    assert any("int_02_ba.rpf" in name for name in filenames)
    assert any("vwdlc_int_03.rpf" in name for name in filenames)
    assert any(name.endswith("/int_03.rpf") for name in filenames)
    assert not any("_bvh.rpf" in name for name in filenames)
    assert not any("dlcMPHeist:" in name for name in filenames)
    assert not list(root.rglob("*.ymap"))
    assert not list(root.rglob("*.ytyp"))


def test_map_assets_are_unique_and_use_base_game_archives(tmp_path):
    destinations = [asset.destination_path.lower() for asset in dlc_maps.MAP_ASSETS]
    assert len(destinations) == len(set(destinations))
    assert {asset.source_pack for asset in dlc_maps.MAP_ASSETS} == {
        "mpheist", "mptuner", "mpbattle", "mpvinewood", "mp2024_02",
    }
    for asset in dlc_maps.MAP_ASSETS:
        assert asset.change_set_key in dlc_maps.MAP_CHANGESET_BY_KEY
        archive = asset.source_archive(tmp_path)
        assert archive == (
            tmp_path / "update/x64/dlcpacks" / asset.source_pack
            / asset.source_archive_name
        )


def test_map_pack_contains_only_allin1_requested_interiors():
    paths = {asset.source_path for asset in dlc_maps.MAP_ASSETS}
    assert len(paths) == 17
    assert {
        "x64/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
        "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
        "x64/levels/gta5/interiors/int_placement_tr.rpf",
        "x64/levels/gta5/interiors/int_02_ba.rpf",
        "x64/levels/gta5/interiors/int_placement_ba.rpf",
        "x64/levels/gta5/interiors/vwdlc_int_03.rpf",
        "x64/levels/gta5/interiors/int_placement_vw.rpf",
        "x64/levels/gta5/interiors/int_03.rpf",
        "x64/levels/gta5/interiors/int_placement.rpf",
    }.issubset(paths)
    assert paths.isdisjoint({
        "x64/levels/gta5/interiors/dlc_int_02_tr.rpf",
        "x64/levels/gta5/interiors/dlc_int_04_tr.rpf",
        "x64/levels/gta5/interiors/int_01_ba.rpf",
        "x64/levels/gta5/interiors/int_03_ba.rpf",
        "x64/levels/gta5/interiors/vwdlc_int_01.rpf",
        "x64/levels/gta5/interiors/vwdlc_int_02.rpf",
        "x64/levels/gta5/interiors/vwdlc_int_05.rpf",
        "x64/levels/gta5/interiors/int_01.rpf",
        "x64/levels/gta5/interiors/int_02.rpf",
    })


def test_placement_archives_are_classified_as_dlc_map_data(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    content = etree.parse(str(root / "content.xml"))
    placement_items = content.xpath(
        "//dataFiles/Item[contains(translate(filename, "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
        "'/int_placement')]"
    )
    assert placement_items
    for item in placement_items:
        assert item.findtext("fileType") == "RPF_FILE"
        assert item.findtext("contents") == "CONTENTS_DLC_MAP_DATA"


def test_harmony_entity_set_archives_are_classified_as_map_data(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    content = etree.parse(str(root / "content.xml"))
    harmony_items = content.xpath(
        "//dataFiles/Item[contains(filename, '/interiors/int_') and "
        "contains(filename, '_ba.rpf')]"
    )
    assert len(harmony_items) == 2
    assert all(
        item.findtext("contents") == "CONTENTS_DLC_MAP_DATA"
        for item in harmony_items
    )


def test_unregistered_pack_has_no_startup_or_story_map_binding(tmp_path):
    assert not [asset for asset in dlc_maps.MAP_ASSETS if asset.proxy_names]
    root = dlc_maps.create_dlc_pack(tmp_path)
    content = etree.parse(str(root / "content.xml"))
    startup_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName="
        f"'{dlc_maps.CHANGESET_NAME}']/filesToEnable/Item/text()"
    )
    setup = etree.parse(str(root / "setup2.xml"))
    startup_groups = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    )
    assert startup_enabled == []
    assert startup_groups == []
    assert content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    ) == [
        dlc_maps.CHANGESET_NAME,
        *(item.name for item in dlc_maps.MAP_CHANGESETS),
    ]
    assert setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    ) == [
        *(item.group_name for item in dlc_maps.MAP_CHANGESETS),
    ]
    assert not setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP' or "
        "NameHash='GROUP_MAP_SP']"
    )
    assert content.xpath("string(//requiresLoadingScreen/@value)") == "false"


def test_reference_bridge_has_no_payload_and_scopes_each_official_rpf(tmp_path):
    metadata = _write_official_reference_metadata(tmp_path)
    root = dlc_maps.create_reference_dlc_pack(tmp_path, metadata)
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))

    assert content.xpath("//dataFiles/Item") == []
    assert setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    ) == [
        "GROUP_STARTUP",
        *(item.group_name for item in dlc_maps.MAP_CHANGESETS),
    ]
    assert not setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP' or "
        "NameHash='GROUP_MAP_SP']"
    )
    assert content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    ) == [dlc_maps.CHANGESET_NAME]
    for definition in dlc_maps.MAP_CHANGESETS:
        routes = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash=$group]/"
            "ContentChangeSets/Item/text()",
            group=definition.group_name,
        )
        assert [value.casefold() for value in routes] == [
            name.casefold() for _pack, name in
            dlc_maps.OFFICIAL_CHANGESET_ROUTES[definition.key]
        ]
    assert dlc_maps.validate_reference_pack_metadata(root) == (
        True, "verified metadata-only official-changeset bridge",
    )
    assert dlc_maps.validate_reference_pack_against_source_metadata(
        root, metadata,
    ) == (
        True, "verified against complete official GROUP_MAP closures",
    )


def test_zero_flash_policy_rejects_real_official_map_closures(tmp_path):
    metadata = _write_official_reference_metadata(tmp_path)
    groups = dlc_maps.reference_group_receipt(metadata)

    valid, detail = dlc_maps.validate_zero_flash_reference_groups(groups)

    assert valid is False
    assert "requires a loading screen" in detail


def test_zero_flash_policy_accepts_exact_scoped_non_invalidating_routes():
    groups = []
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
        groups.append({
            "property": definition.key,
            "group": definition.group_name,
            "references": references,
            "routes": routes,
        })

    assert dlc_maps.validate_zero_flash_reference_groups(groups) == (
        True, "verified zero-flash property scope",
    )


def test_yacht_routes_preserve_the_cross_edition_rockstar_execution_order():
    # Both the installed Legacy and Enhanced mpheist setup2.xml files route
    # these changesets in this order.  It is semantically significant: the
    # bridge must not sort the names or substitute an earlier audit order.
    assert dlc_maps.OFFICIAL_CHANGESET_ROUTES["yacht"] == (
        ("mpheist", "MPHEIST_PRE_MAP_CHANGES"),
        ("mpheist", "MPHEIST_GTA5_LODLIGHTS"),
        ("mpheist", "MPHEIST_GTA5_HILLS_CITYHILLS_01"),
    )


def _write_official_reference_metadata(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    metadata = {}
    for pack, device in dlc_maps.ROCKSTAR_DEVICE_BY_PACK.items():
        pack_assets = [
            asset for asset in dlc_maps.MAP_ASSETS
            if asset.source_pack == pack
        ]
        content_root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
        data_files = etree.SubElement(content_root, "dataFiles")
        for asset in pack_assets:
            item = etree.SubElement(data_files, "Item")
            etree.SubElement(item, "filename").text = asset.source_filename
            etree.SubElement(item, "fileType").text = "RPF_FILE"
            etree.SubElement(item, "disabled").set("value", "true")
        proxy_name = f"{device}:/common/data/interiorProxies.meta"
        proxy = etree.SubElement(data_files, "Item")
        etree.SubElement(proxy, "filename").text = proxy_name
        etree.SubElement(proxy, "fileType").text = (
            "INTERIOR_PROXY_ORDER_FILE"
        )
        etree.SubElement(proxy, "disabled").set("value", "true")
        changes = etree.SubElement(content_root, "contentChangeSets")
        startup = etree.SubElement(changes, "Item")
        startup_name = f"{pack.upper()}_AUTOGEN"
        etree.SubElement(startup, "changeSetName").text = startup_name
        startup_enabled = etree.SubElement(startup, "filesToEnable")
        etree.SubElement(startup_enabled, "Item").text = proxy_name
        pack_routes = [
            name for routes in dlc_maps.OFFICIAL_CHANGESET_ROUTES.values()
            for route_pack, name in routes if route_pack == pack
        ]
        for route_index, change_name in enumerate(pack_routes):
            change = etree.SubElement(changes, "Item")
            etree.SubElement(change, "changeSetName").text = change_name
            map_data = etree.SubElement(change, "mapChangeSetData")
            map_item = etree.SubElement(map_data, "Item")
            etree.SubElement(map_item, "associatedMap").text = "MO_JIM_L11"
            invalidated = etree.SubElement(map_item, "filesToInvalidate")
            etree.SubElement(invalidated, "Item").text = (
                f"platform:/fixture/{pack}/{route_index}.rpf"
            )
            enabled = etree.SubElement(map_item, "filesToEnable")
            if pack != "mpheist":
                route_assets = pack_assets
            elif "HOLLYWOOD" in change_name:
                route_assets = [
                    asset for asset in pack_assets
                    if asset.change_set_key == "grapeseed"
                ]
            elif change_name.endswith("PRE_MAP_CHANGES"):
                route_assets = [
                    asset for asset in pack_assets
                    if asset.source_path.endswith("mpheist_yacht.rpf")
                ]
            elif change_name.endswith("LODLIGHTS"):
                route_assets = [
                    asset for asset in pack_assets
                    if asset.source_path.endswith("LODLights.rpf")
                ]
            else:
                route_assets = [
                    asset for asset in pack_assets
                    if asset.change_set_key == "yacht"
                    and not asset.source_path.endswith("mpheist_yacht.rpf")
                    and not asset.source_path.endswith("LODLights.rpf")
                ]
            for asset in route_assets:
                etree.SubElement(enabled, "Item").text = asset.source_filename
            etree.SubElement(change, "requiresLoadingScreen").set(
                "value", str(pack != "mpbattle").lower(),
            )
            if pack != "mpbattle":
                etree.SubElement(change, "loadingScreenContext").text = (
                    "LOADINGSCREEN_CONTEXT_LAST_FRAME"
                )
            etree.SubElement(change, "useCacheLoader").set(
                "value", str(pack != "mpbattle").lower(),
            )

        setup_root = etree.Element("SSetupData")
        etree.SubElement(setup_root, "deviceName").text = device
        groups = etree.SubElement(setup_root, "contentChangeSetGroups")
        startup_group = etree.SubElement(groups, "Item")
        etree.SubElement(startup_group, "NameHash").text = "GROUP_STARTUP"
        startup_changes = etree.SubElement(
            startup_group, "ContentChangeSets",
        )
        etree.SubElement(startup_changes, "Item").text = startup_name
        group = etree.SubElement(groups, "Item")
        etree.SubElement(group, "NameHash").text = "GROUP_MAP"
        group_changes = etree.SubElement(group, "ContentChangeSets")
        for change_name in pack_routes:
            etree.SubElement(group_changes, "Item").text = change_name

        content_path = tmp_path / f"{pack}-content.xml"
        setup_path = tmp_path / f"{pack}-setup2.xml"
        content_path.write_bytes(etree.tostring(content_root))
        setup_path.write_bytes(etree.tostring(setup_root))
        metadata[pack] = (content_path, setup_path)
    return metadata


def test_reference_sources_are_verified_against_rockstar_registration(tmp_path):
    metadata = _write_official_reference_metadata(tmp_path)
    assert dlc_maps.validate_reference_source_metadata(metadata) == (
        True, "verified against installed Rockstar content metadata",
    )

    tuner_content = etree.parse(str(metadata["mptuner"][0]))
    tuner_content.xpath("//dataFiles/Item[1]/disabled")[0].set(
        "value", "false",
    )
    tuner_content.write(str(metadata["mptuner"][0]))
    valid, reason = dlc_maps.validate_reference_source_metadata(metadata)
    assert valid is False
    assert "not a deferred Rockstar RPF" in reason


def test_reference_source_changeset_names_are_case_insensitive_but_unique(
    tmp_path,
):
    metadata = _write_official_reference_metadata(tmp_path)
    vinewood_setup = etree.parse(str(metadata["mpvinewood"][1]))
    name = vinewood_setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP']/"
        "ContentChangeSets/Item"
    )[0]
    name.text = (name.text or "").swapcase()
    vinewood_setup.write(str(metadata["mpvinewood"][1]))
    assert dlc_maps.validate_reference_source_metadata(metadata)[0] is True

    vinewood_content = etree.parse(str(metadata["mpvinewood"][0]))
    original = vinewood_content.xpath("//contentChangeSets/Item")[0]
    duplicate = deepcopy(original)
    duplicate.xpath("changeSetName")[0].text = (
        duplicate.xpath("string(changeSetName)").swapcase()
    )
    original.getparent().append(duplicate)
    vinewood_content.write(str(metadata["mpvinewood"][0]))
    valid, reason = dlc_maps.validate_reference_source_metadata(metadata)
    assert valid is False
    assert "case-colliding content changesets" in reason


def test_reference_group_receipt_is_fixed_and_machine_independent(tmp_path):
    metadata = _write_official_reference_metadata(tmp_path)
    receipt = dlc_maps.reference_group_receipt(metadata)
    assert [item["property"] for item in receipt] == [
        definition.key for definition in dlc_maps.MAP_CHANGESETS
    ]
    assert sum(len(item["references"]) for item in receipt) == 17
    assert all("C:\\" not in value and "/Users/" not in value
               for item in receipt for value in item["references"])
    assert dlc_maps.validate_reference_group_receipt(receipt) == (
        True, "verified",
    )


def test_verified_startup_pack_registers_archives_without_global_map_loading(
    tmp_path,
):
    root = dlc_maps.create_dlc_pack(
        tmp_path, layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))

    filenames = content.xpath("//dataFiles/Item/filename/text()")
    startup_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName=$name]/"
        "filesToEnable/Item/text()",
        name=dlc_maps.CHANGESET_NAME,
    )
    assert len(filenames) == len(dlc_maps.MAP_ASSETS) == 17
    assert startup_enabled == filenames
    assert content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    ) == [dlc_maps.CHANGESET_NAME]
    assert not content.xpath(
        "//contentChangeSets/Item/mapChangeSetData/Item"
    )
    assert content.xpath(
        "//contentChangeSets/Item/requiresLoadingScreen/@value"
    ) == ["false"]

    assert setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    ) == ["GROUP_STARTUP"]
    assert setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    ) == [dlc_maps.CHANGESET_NAME]
    assert not setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP' or "
        "NameHash='GROUP_MAP_SP']"
    )


def test_staged_asset_validation_rejects_missing_and_empty_files(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    assert len(dlc_maps.validate_staged_assets(root)) == len(dlc_maps.MAP_ASSETS)
    first = dlc_maps.MAP_ASSETS[0].destination(root)
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"")
    assert first in dlc_maps.validate_staged_assets(root)
    first.write_bytes(b"asset")
    assert first not in dlc_maps.validate_staged_assets(root)


def test_grapeseed_pack_contains_the_requestable_placement_archive():
    grapeseed_paths = {
        asset.source_path
        for asset in dlc_maps.MAP_ASSETS
        if asset.change_set_key == "grapeseed"
    }
    assert (
        "x64/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf"
        in grapeseed_paths
    )


def test_proxy_filter_preserves_original_global_order_index(tmp_path, monkeypatch):
    asset = dlc_maps._proxy(
        "mpheist", "test",
        "hei_hw1_blimp_interior_v_garagem_milo_",
    )
    monkeypatch.setattr(dlc_maps, "MAP_ASSETS", (asset,))
    root = dlc_maps.create_dlc_pack(tmp_path, assets=(asset,))
    path = asset.destination(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    document = etree.Element("SInteriorOrderData")
    etree.SubElement(document, "startFrom").set("value", "520")
    etree.SubElement(document, "filePathHash").set("value", "0")
    proxies = etree.SubElement(document, "proxies")
    for index in range(61):
        etree.SubElement(proxies, "Item").text = f"unrelated_{index}"
    etree.SubElement(proxies, "Item").text = asset.proxy_names[0]
    path.write_bytes(etree.tostring(document, xml_declaration=True,
                                    encoding="UTF-8"))

    assert dlc_maps.filter_staged_proxy_assets(root) == [path]
    filtered = etree.parse(str(path))
    assert filtered.xpath("string(/SInteriorOrderData/startFrom/@value)") == "581"
    assert filtered.xpath("/SInteriorOrderData/proxies/Item/text()") == [
        asset.proxy_names[0],
    ]


def test_proxy_filter_rejects_noncontiguous_selection(tmp_path, monkeypatch):
    asset = dlc_maps._proxy("test", "split", "first", "third")
    monkeypatch.setattr(dlc_maps, "MAP_ASSETS", (asset,))
    root = dlc_maps.create_dlc_pack(tmp_path, assets=(asset,))
    path = asset.destination(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<?xml version="1.0"?><SInteriorOrderData>'
        '<startFrom value="100"/><proxies>'
        '<Item>first</Item><Item>second</Item><Item>third</Item>'
        '</proxies></SInteriorOrderData>',
        encoding="utf-8",
    )
    try:
        dlc_maps.filter_staged_proxy_assets(root)
    except ValueError as exc:
        assert "must be contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous proxy selection was accepted")


def test_map_pack_defers_each_property_outside_story_map_groups(tmp_path):
    root = dlc_maps.create_dlc_pack(
        tmp_path, layout=dlc_maps.DEFERRED_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))
    assert content.xpath("string(//changeSetName)") == dlc_maps.CHANGESET_NAME
    assert content.xpath("string(//requiresLoadingScreen/@value)") == "false"

    definitions = {item.name: item for item in dlc_maps.MAP_CHANGESETS}
    generated_names = content.xpath(
        "//contentChangeSets/Item[position() > 1]/changeSetName/text()"
    )
    assert generated_names == [item.name for item in dlc_maps.MAP_CHANGESETS]
    assert {
        item.associated_map for item in dlc_maps.MAP_CHANGESETS
    } == {dlc_maps.STORY_ASSOCIATED_MAP}
    for change_set_name, definition in definitions.items():
        item = content.xpath(
            "//contentChangeSets/Item[changeSetName=$name]",
            name=change_set_name,
        )[0]
        assert item.xpath("string(mapChangeSetData/Item/associatedMap)") == (
            definition.associated_map
        )
        assert item.xpath("string(requiresLoadingScreen/@value)") == "false"
        assert item.xpath("string(useCacheLoader/@value)") == "false"
        assert set(item.xpath(
            "mapChangeSetData/Item/filesToEnable/Item/text()"
        )) == {
            asset.filename for asset in dlc_maps.MAP_ASSETS
            if asset.change_set_key == definition.key
        }

    assert setup.xpath("string(//NameHash)") == "GROUP_STARTUP"
    assert setup.xpath("string(//ContentChangeSets/Item)") == dlc_maps.CHANGESET_NAME
    groups = setup.xpath("//contentChangeSetGroups/Item/NameHash/text()")
    assert groups == [
        "GROUP_STARTUP",
        *(item.group_name for item in dlc_maps.MAP_CHANGESETS),
    ]
    assert "GROUP_MAP" not in groups
    assert "GROUP_MAP_SP" not in groups
    assert setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    ) == [dlc_maps.CHANGESET_NAME]
    for definition in dlc_maps.MAP_CHANGESETS:
        assert setup.xpath(
            "string(//contentChangeSetGroups/Item[NameHash=$group]/"
            "ContentChangeSets/Item)", group=definition.group_name,
        ) == definition.name
    assert setup.xpath("string(//type)") == "EXTRACONTENT_COMPAT_PACK"
    assert setup.xpath("string(//order/@value)") == "71"
    assert setup.xpath("string(//minorOrder/@value)") == "0"
    assert setup.xpath("string(//isLevelPack/@value)") == "false"
    assert setup.xpath("string(//subPackCount/@value)") == "0"


def test_legacy_group_streaming_uses_the_validated_layout(tmp_path):
    root = dlc_maps.create_dlc_pack(
        tmp_path, layout=dlc_maps.LEGACY_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))

    change_sets = content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    )
    assert change_sets == [
        dlc_maps.CHANGESET_NAME, dlc_maps.STREAMING_CHANGESET_NAME,
    ]
    assert content.xpath(
        "string(//contentChangeSets/Item[changeSetName=$name]/"
        "requiresLoadingScreen/@value)",
        name=dlc_maps.STREAMING_CHANGESET_NAME,
    ) == "true"
    assert content.xpath(
        "string(//contentChangeSets/Item[changeSetName=$name]/"
        "useCacheLoader/@value)",
        name=dlc_maps.STREAMING_CHANGESET_NAME,
    ) == "true"
    assert setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    ) == ["GROUP_STARTUP", "GROUP_MAP", "GROUP_MAP_SP"]


def test_deferred_map_generation_rejects_unowned_rpf(tmp_path):
    unowned = dlc_maps.MapAsset(
        "test", "x64/unowned.rpf", "x64/unowned.rpf",
    )
    try:
        dlc_maps.create_dlc_pack(tmp_path, assets=(unowned,))
    except ValueError as exc:
        assert "known deferred changeset" in str(exc)
        assert "<missing>" in str(exc)
    else:
        raise AssertionError("unowned RPF was silently omitted")


def test_subset_pack_registers_only_its_present_property_group(tmp_path):
    davis_assets = tuple(
        asset for asset in dlc_maps.MAP_ASSETS
        if asset.change_set_key == "davis"
    )
    root = dlc_maps.create_dlc_pack(
        tmp_path, assets=davis_assets,
        layout=dlc_maps.DEFERRED_PACK_LAYOUT,
    )
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))

    assert content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    ) == [dlc_maps.CHANGESET_NAME, "ALLIN1_MAPS_DAVIS"]
    assert setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    ) == ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"]


def test_standalone_map_pack_deploy_and_remove_are_owned(tmp_path):
    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"maps")
    unrelated = tmp_path / "mods/update/x64/dlcpacks/user_pack"
    unrelated.mkdir(parents=True)
    destination = tmp_path / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"old-maps")
    legacy = tmp_path / "update/x64/dlcpacks/allin1_maps"
    legacy.mkdir(parents=True)
    (legacy / "dlc.rpf").write_bytes(b"legacy")
    deployed = dlc_maps.deploy_dlc_rpf(archive, tmp_path)
    assert (deployed / "dlc.rpf").read_bytes() == b"maps"
    assert (deployed / "dlc.rpf.bak").read_bytes() == b"old-maps"
    marker = (deployed / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert f"layout={dlc_maps.PACK_LAYOUT}" in marker
    assert "archive_registration=disabled" in marker
    assert "group_map_binding=false" in marker
    assert "activation=disabled-for-startup-safety" in marker
    assert f"asset_count={len(dlc_maps.MAP_ASSETS)}" in marker
    assert "archive_bytes=4" in marker
    assert not legacy.exists()
    assert dlc_maps.remove_dlc_pack(tmp_path) == [deployed]
    assert unrelated.exists()


def test_deploy_marker_records_explicit_legacy_contract(tmp_path):
    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"legacy-maps")
    deployed = dlc_maps.deploy_dlc_rpf(
        archive,
        tmp_path,
        layout=dlc_maps.LEGACY_PACK_LAYOUT,
        asset_count=3,
    )
    marker = (deployed / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert f"layout={dlc_maps.LEGACY_PACK_LAYOUT}" in marker
    assert "archive_registration=group-map" in marker
    assert "group_map_binding=true" in marker
    assert "activation=story-map-groups" in marker
    assert "asset_count=3" in marker


def test_reference_bridge_marker_records_zero_payload_contract(tmp_path):
    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"metadata only")
    deployed = dlc_maps.deploy_dlc_rpf(
        archive,
        tmp_path,
        layout=dlc_maps.REFERENCE_PACK_LAYOUT,
        asset_count=0,
        reference_count=len(dlc_maps.MAP_ASSETS),
    )
    marker = (deployed / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert "archive_registration=metadata-bridge" in marker
    assert "activation=property-group-runtime" in marker
    assert "asset_count=0" in marker
    assert "reference_count=17" in marker
    assert f"group_contract={dlc_maps.REFERENCE_GROUP_CONTRACT}" in marker


def test_reference_bridge_receipt_validates_archive_and_fixed_groups(tmp_path):
    metadata = _write_official_reference_metadata(tmp_path / "metadata")
    pack = tmp_path / "allin1_maps"
    pack.mkdir()
    archive = pack / "dlc.rpf"
    archive.write_bytes(b"metadata bridge")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    marker = (
        f"layout={dlc_maps.REFERENCE_PACK_LAYOUT}\n"
        "archive_registration=metadata-bridge\n"
        "activation=property-group-runtime\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        "asset_count=0\n"
        f"reference_count={len(dlc_maps.MAP_ASSETS)}\n"
        f"group_contract={dlc_maps.REFERENCE_GROUP_CONTRACT}\n"
        f"archive_bytes={archive.stat().st_size}\n"
        f"archive_sha256={archive_hash}\n"
    )
    (pack / dlc_maps.ACTIVE_MARKER).write_text(marker, encoding="utf-8")
    receipt = {
        "schema": 1,
        "status": "verified",
        "package_id": "allin1.online-content",
        "pack_name": dlc_maps.DLC_NAME,
        "layout": dlc_maps.REFERENCE_PACK_LAYOUT,
        "edition": "enhanced",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
        "asset_count": 0,
        "reference_count": len(dlc_maps.MAP_ASSETS),
        "group_contract": dlc_maps.REFERENCE_GROUP_CONTRACT,
        "groups": dlc_maps.reference_group_receipt(metadata),
    }
    (pack / dlc_maps.RUNTIME_RECEIPT).write_text(
        json.dumps(receipt), encoding="utf-8",
    )

    assert dlc_maps.validate_reference_bridge_receipt(
        pack, edition="enhanced",
    ) == (True, "verified", receipt)
    receipt["groups"][0]["group"] = "GROUP_MAP"
    (pack / dlc_maps.RUNTIME_RECEIPT).write_text(
        json.dumps(receipt), encoding="utf-8",
    )
    valid, reason, _ = dlc_maps.validate_reference_bridge_receipt(
        pack, edition="enhanced",
    )
    assert valid is False
    assert "group receipt" in reason


def test_standalone_map_pack_removes_legacy_location(tmp_path):
    legacy = tmp_path / "update/x64/dlcpacks/allin1_maps"
    legacy.mkdir(parents=True)
    assert dlc_maps.remove_dlc_pack(tmp_path) == [legacy]
    assert not legacy.exists()


def test_runtime_activation_receipt_matches_archive_and_marker(tmp_path):
    pack = tmp_path / "allin1_maps"
    pack.mkdir()
    archive = pack / "dlc.rpf"
    archive.write_bytes(b"verified map archive")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    gameconfig_hash = hashlib.sha256(b"full gameconfig").hexdigest()
    marker = (
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
        "archive_registration=startup\n"
        "activation=verified-startup-registration\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        "asset_count=15\n"
        f"archive_bytes={archive.stat().st_size}\n"
        f"archive_sha256={archive_hash}\n"
        f"gameconfig_sha256={gameconfig_hash}\n"
    )
    (pack / dlc_maps.ACTIVE_MARKER).write_text(marker, encoding="utf-8")
    receipt = {
        "schema": 1,
        "status": "verified",
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "edition": "enhanced",
        "gameconfig_entry": "common/data/gameconfig.xml",
        "asset_count": 15,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
        "gameconfig_sha256": gameconfig_hash,
        "pools": {"FragmentStore": {"before": 42000, "after": 52000}},
    }
    (pack / dlc_maps.RUNTIME_RECEIPT).write_text(
        json.dumps(receipt), encoding="utf-8",
    )

    valid, reason, parsed = dlc_maps.validate_runtime_activation_receipt(
        pack, edition="enhanced",
    )
    assert valid is True
    assert reason == "verified"
    assert parsed == receipt

    archive.write_bytes(b"tampered")
    valid, reason, _ = dlc_maps.validate_runtime_activation_receipt(
        pack, edition="enhanced",
    )
    assert valid is False
    assert "size" in reason or "fingerprint" in reason


def _runtime_activation_fixture(tmp_path):
    pack = tmp_path / "allin1_maps"
    pack.mkdir(parents=True)
    archive = pack / "dlc.rpf"
    archive.write_bytes(b"verified map archive")
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    gameconfig_hash = hashlib.sha256(b"full gameconfig").hexdigest()
    marker = {
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "archive_registration": "startup",
        "activation": "verified-startup-registration",
        "receipt": dlc_maps.RUNTIME_RECEIPT,
        "asset_count": "15",
        "archive_bytes": str(archive.stat().st_size),
        "archive_sha256": archive_hash,
        "gameconfig_sha256": gameconfig_hash,
    }
    receipt = {
        "schema": 1,
        "status": "verified",
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "edition": "enhanced",
        "gameconfig_entry": "common/data/gameconfig.xml",
        "asset_count": 15,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_hash,
        "gameconfig_sha256": gameconfig_hash,
        "pools": {"FragmentStore": {"before": 42000, "after": 52000}},
    }

    def write():
        (pack / dlc_maps.ACTIVE_MARKER).write_text(
            "".join(f"{key}={value}\n" for key, value in marker.items()),
            encoding="utf-8",
        )
        (pack / dlc_maps.RUNTIME_RECEIPT).write_text(
            json.dumps(receipt), encoding="utf-8",
        )

    write()
    return pack, archive, marker, receipt, write


def test_proxy_filter_rejects_malformed_or_incomplete_metadata(tmp_path):
    with pytest.raises(ValueError, match="at least one proxy"):
        dlc_maps._proxy("fixture", "empty")

    asset = dlc_maps._proxy("fixture", "test", "wanted_proxy")
    root = tmp_path / "pack"
    path = asset.destination(root)
    path.parent.mkdir(parents=True)

    # Assets without a proxy selection are intentionally ignored.
    plain = dlc_maps.MapAsset("fixture", "source", "plain.meta")
    assert dlc_maps.filter_staged_proxy_assets(root, (plain,)) == []

    path.write_text("not xml", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid interior proxy metadata"):
        dlc_maps.filter_staged_proxy_assets(root, (asset,))

    path.write_text("<CInteriorProxyOrderData/>", encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete interior proxy metadata"):
        dlc_maps.filter_staged_proxy_assets(root, (asset,))

    path.write_text(
        "<CInteriorProxyOrderData><startFrom value='bad'/><proxies>"
        "<Item>wanted_proxy</Item></proxies></CInteriorProxyOrderData>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid proxy startFrom"):
        dlc_maps.filter_staged_proxy_assets(root, (asset,))

    path.write_text(
        "<CInteriorProxyOrderData><startFrom value='4'/><proxies>"
        "<Item>different_proxy</Item></proxies></CInteriorProxyOrderData>",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="wanted_proxy"):
        dlc_maps.filter_staged_proxy_assets(root, (asset,))


def test_map_metadata_builders_and_deployer_reject_invalid_contracts(tmp_path):
    with pytest.raises(ValueError, match="Unsupported standalone-map layout"):
        dlc_maps._build_content_xml(layout="unknown")
    with pytest.raises(ValueError, match="Unsupported standalone-map layout"):
        dlc_maps._build_setup2_xml(layout="unknown")

    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"maps")
    with pytest.raises(ValueError, match="Unsupported standalone-map layout"):
        dlc_maps.deploy_dlc_rpf(archive, tmp_path, layout="unknown")
    with pytest.raises(ValueError, match="non-negative"):
        dlc_maps.deploy_dlc_rpf(archive, tmp_path, asset_count=-1)


def test_deferred_deploy_records_property_group_activation(tmp_path):
    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"maps")

    deployed = dlc_maps.deploy_dlc_rpf(
        archive, tmp_path, layout=dlc_maps.DEFERRED_PACK_LAYOUT, asset_count=2,
    )

    marker = (deployed / dlc_maps.ACTIVE_MARKER).read_text(encoding="utf-8")
    assert "archive_registration=property-groups" in marker
    assert "activation=property-group-native-host-required" in marker


@pytest.mark.parametrize("with_backup", [False, True])
def test_deploy_failure_cleans_temporary_and_restores_owned_backup(
    tmp_path, monkeypatch, with_backup,
):
    archive = tmp_path / "source.rpf"
    archive.write_bytes(b"new maps")
    destination = tmp_path / "mods/update/x64/dlcpacks/allin1_maps/dlc.rpf"
    if with_backup:
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"old maps")
    original_write_text = type(destination).write_text

    def fail_marker(path, *args, **kwargs):
        if path.name == dlc_maps.ACTIVE_MARKER:
            raise OSError("disk full")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(type(destination), "write_text", fail_marker)

    with pytest.raises(OSError, match="disk full"):
        dlc_maps.deploy_dlc_rpf(archive, tmp_path)

    assert not destination.with_suffix(".rpf.tmp").exists()
    if with_backup:
        assert destination.read_bytes() == b"old maps"


def test_runtime_receipt_rejects_missing_or_unreadable_artifacts(tmp_path):
    pack = tmp_path / "missing"
    pack.mkdir()
    valid, reason, receipt = dlc_maps.validate_runtime_activation_receipt(
        pack, edition="enhanced",
    )
    assert (valid, receipt) == (False, None)
    assert "missing or empty" in reason

    pack, _archive, _marker, _receipt, _write = _runtime_activation_fixture(
        tmp_path / "unreadable",
    )
    (pack / dlc_maps.RUNTIME_RECEIPT).write_text("not json", encoding="utf-8")
    valid, reason, receipt = dlc_maps.validate_runtime_activation_receipt(
        pack, edition="enhanced",
    )
    assert (valid, receipt) == (False, None)
    assert "unreadable" in reason


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("receipt_not_object", "not a JSON object"),
        ("marker_layout", "marker layout"),
        ("schema", "schema is not 1"),
        ("receipt_status", "receipt status"),
        ("invalid_counts", "size or asset count is invalid"),
        ("asset_count", "asset count does not match"),
        ("marker_hash", "marker fingerprints are invalid"),
        ("archive_hash_disagreement", "archive fingerprints disagree"),
        ("config_hash_disagreement", "gameconfig fingerprints disagree"),
        ("archive_digest", "map archive failed"),
        ("missing_pools", "no verified pool changes"),
    ],
)
def test_runtime_receipt_contract_fails_closed_at_each_boundary(
    tmp_path, case, expected,
):
    pack, archive, marker, receipt, write = _runtime_activation_fixture(tmp_path)
    if case == "receipt_not_object":
        write()
        (pack / dlc_maps.RUNTIME_RECEIPT).write_text("[]", encoding="utf-8")
    elif case == "marker_layout":
        marker["layout"] = "legacy"
        write()
    elif case == "schema":
        receipt["schema"] = 2
        write()
    elif case == "receipt_status":
        receipt["status"] = "pending"
        write()
    elif case == "invalid_counts":
        marker["asset_count"] = "many"
        write()
    elif case == "asset_count":
        receipt["asset_count"] = 14
        write()
    elif case == "marker_hash":
        marker["archive_sha256"] = "not-a-hash"
        write()
    elif case == "archive_hash_disagreement":
        receipt["archive_sha256"] = "0" * 64
        write()
    elif case == "config_hash_disagreement":
        receipt["gameconfig_sha256"] = "0" * 64
        write()
    elif case == "archive_digest":
        archive.write_bytes(b"X" * archive.stat().st_size)
        write()
    elif case == "missing_pools":
        receipt["pools"] = {}
        write()

    valid, reason, parsed = dlc_maps.validate_runtime_activation_receipt(
        pack, edition="enhanced",
    )

    assert valid is False
    assert expected in reason
    if case == "receipt_not_object":
        assert parsed is None
    else:
        assert parsed is not None
