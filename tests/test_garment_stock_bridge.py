"""Regression coverage for the Garment Factory stock-reference bridge."""

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from allin1 import installer


def _write_stock_metadata(
    root: Path, *, requires_loading: bool = True,
    register_archive: bool = True,
) -> tuple[Path, Path]:
    filename = "dlc_mp2024_02:/x64/levels/gta5/interiors/int_placement.rpf"

    content = ET.Element("CDataFileMgr__ContentsOfDataFileXml")
    data_files = ET.SubElement(content, "dataFiles")
    if register_archive:
        data_file = ET.SubElement(data_files, "Item")
        ET.SubElement(data_file, "filename").text = filename
        ET.SubElement(data_file, "fileType").text = "RPF_FILE"
        ET.SubElement(data_file, "disabled").set("value", "true")

    changes = ET.SubElement(content, "contentChangeSets")
    change = ET.SubElement(changes, "Item")
    ET.SubElement(change, "changeSetName").text = "MP2024_02_MAP_UPDATE"
    map_data = ET.SubElement(change, "mapChangeSetData")
    map_item = ET.SubElement(map_data, "Item")
    enabled = ET.SubElement(map_item, "filesToEnable")
    ET.SubElement(enabled, "Item").text = filename
    ET.SubElement(change, "requiresLoadingScreen").set(
        "value", "true" if requires_loading else "false",
    )

    setup = ET.Element("SSetupData")
    ET.SubElement(setup, "deviceName").text = "dlc_MP2024_02"
    groups = ET.SubElement(setup, "contentChangeSetGroups")
    group = ET.SubElement(groups, "Item")
    ET.SubElement(group, "NameHash").text = "GROUP_MAP"
    group_changes = ET.SubElement(group, "ContentChangeSets")
    ET.SubElement(group_changes, "Item").text = "MP2024_02_MAP_UPDATE"

    content_path = root / "content.xml"
    setup_path = root / "setup2.xml"
    ET.ElementTree(content).write(content_path, encoding="utf-8")
    ET.ElementTree(setup).write(setup_path, encoding="utf-8")
    return content_path, setup_path


def test_garment_bridge_metadata_is_inert_until_its_dormant_group_runs(
    tmp_path,
):
    content_path, setup_path = installer._build_garment_bridge_metadata(
        tmp_path / "bridge",
    )

    content = ET.parse(content_path).getroot()
    setup = ET.parse(setup_path).getroot()
    assert content.findall("./dataFiles/Item") == []
    startup = content.find("./contentChangeSets/Item")
    assert startup is not None
    assert startup.findtext("changeSetName") == installer._GARMENT_BRIDGE_STARTUP
    assert startup.find("requiresLoadingScreen").attrib["value"] == "false"
    assert startup.findall("./mapChangeSetData/Item/filesToEnable/Item") == []

    groups = {
        group.findtext("NameHash"): [
            item.text for item in group.findall("./ContentChangeSets/Item")
        ]
        for group in setup.findall("./contentChangeSetGroups/Item")
    }
    assert groups == {
        "GROUP_STARTUP": [installer._GARMENT_BRIDGE_STARTUP],
        installer._GARMENT_BRIDGE_GROUP: [installer._GARMENT_BRIDGE_CHANGESET],
    }


def test_garment_stock_contract_accepts_the_expected_deferred_map_closure(
    tmp_path,
):
    content_path, setup_path = _write_stock_metadata(tmp_path)

    result = installer._verify_garment_stock_metadata(
        content_path, setup_path,
    )

    assert result["device_name"] == "dlc_MP2024_02"
    assert result["group_map_changesets"] == ["MP2024_02_MAP_UPDATE"]
    assert result["changeset_name"] == "MP2024_02_MAP_UPDATE"
    assert result["enabled_rpf_count"] == 1
    assert result["requires_loading_screen"] is True
    assert len(result["changeset_sha256"]) == 64


@pytest.mark.parametrize(
    ("requires_loading", "register_archive", "message"),
    [
        (False, True, "loading-screen semantics changed"),
        (True, False, "unregistered RPF"),
    ],
)
def test_garment_stock_contract_fails_closed_when_rockstar_semantics_drift(
    tmp_path, requires_loading, register_archive, message,
):
    content_path, setup_path = _write_stock_metadata(
        tmp_path,
        requires_loading=requires_loading,
        register_archive=register_archive,
    )

    with pytest.raises(RuntimeError, match=message):
        installer._verify_garment_stock_metadata(content_path, setup_path)
