from pathlib import Path
import json
import xml.etree.ElementTree as ET

import pytest

from allin1 import installer
from allin1.garage_bridge_contracts import ADDITIONAL_INTERIOR_BRIDGES
from allin1.generators.dlclist import CUSTOM_DLC_PACKS, OWNED_DLC_PACKS


def stock(root, bridge):
    content = ET.Element("CDataFileMgr__ContentsOfDataFileXml")
    files = ET.SubElement(content, "dataFiles")
    changes = ET.SubElement(content, "contentChangeSets")
    change = ET.SubElement(changes, "Item")
    ET.SubElement(change, "changeSetName").text = bridge.changeset
    maps = ET.SubElement(change, "mapChangeSetData")
    mapping = ET.SubElement(maps, "Item")
    ET.SubElement(mapping, "associatedMap").text = "MO_JIM_L11"
    enabled = ET.SubElement(mapping, "filesToEnable")
    for name in bridge.enabled_archives:
        filename = f"{bridge.source_device}:/%PLATFORM%/levels/gta5/{name}"
        item = ET.SubElement(files, "Item")
        ET.SubElement(item, "filename").text = filename
        ET.SubElement(item, "fileType").text = "RPF_FILE"
        ET.SubElement(item, "disabled").set("value", "true")
        ET.SubElement(enabled, "Item").text = filename
    if bridge.requires_loading:
        ET.SubElement(change, "requiresLoadingScreen").set("value", "true")
    setup = ET.Element("SSetupData")
    ET.SubElement(setup, "deviceName").text = bridge.source_device
    groups = ET.SubElement(setup, "contentChangeSetGroups")
    group = ET.SubElement(groups, "Item")
    ET.SubElement(group, "NameHash").text = "GROUP_MAP"
    ET.SubElement(ET.SubElement(group, "ContentChangeSets"), "Item").text = bridge.changeset
    cp, sp = root / "content.xml", root / "setup2.xml"
    ET.ElementTree(content).write(cp)
    ET.ElementTree(setup).write(sp)
    return cp, sp


@pytest.mark.parametrize("bridge", ADDITIONAL_INTERIOR_BRIDGES, ids=lambda b: b.key)
def test_exact_stock_metadata_and_dormant_payload(tmp_path, bridge):
    cp, sp = stock(tmp_path, bridge)
    receipt = installer._verify_garment_stock_metadata(cp, sp, bridge=bridge)
    assert receipt["enabled_rpf_count"] == 5
    assert receipt["requires_loading_screen"] == bridge.requires_loading
    cp, sp = installer._build_garment_bridge_metadata(tmp_path / "staged", bridge=bridge)
    content, setup = ET.parse(cp), ET.parse(sp)
    assert not content.findall("./dataFiles/Item")
    assert not content.findall(".//filesToEnable/Item")
    groups = {g.findtext("NameHash"): [i.text for i in g.findall("./ContentChangeSets/Item")]
              for g in setup.findall("./contentChangeSetGroups/Item")}
    assert groups == {"GROUP_STARTUP": [bridge.startup], bridge.group: [bridge.changeset]}
    assert setup.findtext("deviceName") == bridge.device
    assert bridge.pack in OWNED_DLC_PACKS
    assert bridge.pack not in CUSTOM_DLC_PACKS  # Only registered after validation.
    patcher = (Path(__file__).parents[1] / "tools/RpfPatcher/Program.cs").read_text(encoding="utf-8-sig")
    owned = patcher.split("OwnedDlcEntries =", 1)[1].split("static int Main", 1)[0]
    assert f'"dlcpacks:/{bridge.pack}/"' in owned
    descriptor = json.loads((Path(__file__).parents[1] / "data/maps/allin1-online-content" /
                             f"{bridge.key}.maps.json").read_text(encoding="utf-8-sig"))
    assert descriptor["streaming"]["keep_resident"] is True
    assert "activation_radius" not in descriptor["streaming"]
    assert tuple(descriptor["streaming"]["ipls"]) == bridge.ipls


@pytest.mark.parametrize("bridge", ADDITIONAL_INTERIOR_BRIDGES, ids=lambda b: b.key)
@pytest.mark.parametrize("drift", ["world_invalidation", "extra_archive", "map", "device", "loading", "disabled"])
def test_changed_stock_contract_blocks_before_install(tmp_path, bridge, drift):
    cp, sp = stock(tmp_path, bridge)
    tree = ET.parse(cp)
    change = tree.find("./contentChangeSets/Item")
    mapping = change.find("./mapChangeSetData/Item")
    if drift == "world_invalidation":
        ET.SubElement(ET.SubElement(mapping, "filesToInvalidate"), "Item").text = "platform:/world.rpf"
    elif drift == "extra_archive":
        ET.SubElement(mapping.find("filesToEnable"), "Item").text = "dlc_other:/extra.rpf"
    elif drift == "map":
        mapping.find("associatedMap").text = "MP_MAP"
    elif drift == "device":
        st = ET.parse(sp)
        st.find("deviceName").text = "other"
        st.write(sp)
    elif drift == "loading":
        flag = change.find("requiresLoadingScreen")
        if flag is None:
            flag = ET.SubElement(change, "requiresLoadingScreen")
        flag.set("value", str(not bridge.requires_loading).lower())
    elif drift == "disabled":
        tree.find("./dataFiles/Item/disabled").set("value", "false")
    tree.write(cp)
    with pytest.raises(RuntimeError):
        installer._verify_garment_stock_metadata(cp, sp, bridge=bridge)


@pytest.mark.parametrize("filename,method,loader,save", [
    ("GarageManager.cs", "EnterFloorGarageCore", "LoadFloorGarageInterior(transition)", "FloorGarageSave()"),
    ("GarageManager.Paleto.cs", "EnterPaletoGarageCore", "LoadPaletoInterior(transition)", "PaletoSave()"),
])
def test_entry_holds_fade_and_loads_before_persisting_vehicle(filename, method, loader, save):
    source = (Path(__file__).parents[1] / "script/src" / filename).read_text(encoding="utf-8-sig")
    entry = source.split(f"private static void {method}(", 1)[1].split("private static void Leave", 1)[0]
    assert entry.index("transition.HoldFade") < entry.index(loader) < entry.index(save)
    assert "transition.Fail" in entry
    assert "transition.Complete(OfficialGarageTransitionPhase.Occupied" in entry
    assert "TryAcquireInteriorUnderBlackTransition" in source
