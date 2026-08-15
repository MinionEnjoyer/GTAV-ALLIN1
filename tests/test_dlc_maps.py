from lxml import etree

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
    assert any("int_01_ba.rpf" in name for name in filenames)
    assert any("vwdlc_int_01.rpf" in name for name in filenames)
    assert any(name.endswith("/int_01.rpf") for name in filenames)
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
        archive = asset.source_archive(tmp_path)
        assert archive == (
            tmp_path / "update/x64/dlcpacks" / asset.source_pack
            / asset.source_archive_name
        )


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
    assert len(harmony_items) == 4
    assert all(
        item.findtext("contents") == "CONTENTS_DLC_MAP_DATA"
        for item in harmony_items
    )


def test_production_pack_has_no_startup_interior_proxy_tables(tmp_path):
    assert not [asset for asset in dlc_maps.MAP_ASSETS if asset.proxy_names]
    root = dlc_maps.create_dlc_pack(tmp_path)
    content = etree.parse(str(root / "content.xml"))
    startup_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName="
        f"'{dlc_maps.CHANGESET_NAME}']/filesToEnable/Item/text()"
    )
    map_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName="
        f"'{dlc_maps.STREAMING_CHANGESET_NAME}']/"
        "mapChangeSetData/Item/filesToEnable/Item/text()"
    )
    assert startup_enabled == []
    assert all(name.endswith(".rpf") for name in map_enabled)


def test_staged_asset_validation_rejects_missing_and_empty_files(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    assert len(dlc_maps.validate_staged_assets(root)) == len(dlc_maps.MAP_ASSETS)
    first = dlc_maps.MAP_ASSETS[0].destination(root)
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"")
    assert first in dlc_maps.validate_staged_assets(root)
    first.write_bytes(b"asset")
    assert first not in dlc_maps.validate_staged_assets(root)


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


def test_map_pack_starts_cleanly_and_streams_during_story_map_change(tmp_path):
    root = dlc_maps.create_dlc_pack(tmp_path)
    content = etree.parse(str(root / "content.xml"))
    setup = etree.parse(str(root / "setup2.xml"))
    assert content.xpath("string(//changeSetName)") == dlc_maps.CHANGESET_NAME
    assert content.xpath("string(//requiresLoadingScreen/@value)") == "false"
    assert content.xpath(
        "string(//contentChangeSets/Item[changeSetName="
        f"'{dlc_maps.STREAMING_CHANGESET_NAME}']/"
        "mapChangeSetData/Item/associatedMap)"
    ) == "MO_JIM_L11"
    assert content.xpath(
        "string(//contentChangeSets/Item[changeSetName="
        f"'{dlc_maps.STREAMING_CHANGESET_NAME}']/"
        "requiresLoadingScreen/@value)"
    ) == "true"
    assert setup.xpath("string(//NameHash)") == "GROUP_STARTUP"
    assert setup.xpath("string(//ContentChangeSets/Item)") == dlc_maps.CHANGESET_NAME
    groups = setup.xpath("//contentChangeSetGroups/Item/NameHash/text()")
    assert groups == ["GROUP_STARTUP", "GROUP_MAP", "GROUP_MAP_SP"]
    assert setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP' or "
        "NameHash='GROUP_MAP_SP']/ContentChangeSets/Item/text()"
    ) == [dlc_maps.STREAMING_CHANGESET_NAME] * 2
    assert setup.xpath("string(//type)") == "EXTRACONTENT_COMPAT_PACK"
    assert setup.xpath("string(//order/@value)") == "71"
    assert setup.xpath("string(//minorOrder/@value)") == "0"
    assert setup.xpath("string(//isLevelPack/@value)") == "false"
    assert setup.xpath("string(//subPackCount/@value)") == "0"


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
    assert (deployed / dlc_maps.ACTIVE_MARKER).is_file()
    assert not legacy.exists()
    assert dlc_maps.remove_dlc_pack(tmp_path) == [deployed]
    assert unrelated.exists()


def test_standalone_map_pack_removes_legacy_location(tmp_path):
    legacy = tmp_path / "update/x64/dlcpacks/allin1_maps"
    legacy.mkdir(parents=True)
    assert dlc_maps.remove_dlc_pack(tmp_path) == [legacy]
    assert not legacy.exists()
