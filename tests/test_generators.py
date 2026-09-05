"""Tests for generator modules."""

import pytest
from lxml import etree

from allin1.generators.dlclist import patch_dlclist, unpatch_dlclist
from allin1.generators.gameconfig import (
    patch_gameconfig,
    restore_enhanced_pool_profile,
)
from allin1.generators.popgroups import create_base_template, generate_popgroups_xml
from allin1.vehicles.database import Vehicle


def _make_vehicle(model="testcar", vehicle_class="compacts", traffic=None):
    return Vehicle(
        model=model,
        name="Test Car",
        vehicle_class=vehicle_class,
        manufacturer="TestMfg",
        traffic=["veh_mid"] if traffic is None else traffic,
    )


def _find_veh_group_models(root, group_name):
    """Find all model names in a vehicle group by group name (case-insensitive)."""
    veh_groups = root.find("vehGroups")
    if veh_groups is None:
        return []
    for item in veh_groups.findall("Item"):
        name_el = item.find("Name")
        if name_el is not None and name_el.text and name_el.text.upper() == group_name.upper():
            models = item.find("models")
            if models is None:
                return []
            return [m.find("Name").text for m in models.findall("Item")]
    return []


class TestPopgroups:
    def test_create_base_template(self):
        xml = create_base_template()
        root = etree.fromstring(xml.encode())
        # Should have vehGroups with correct group names
        veh_groups = root.find("vehGroups")
        assert veh_groups is not None
        names = [item.find("Name").text for item in veh_groups.findall("Item")]
        assert "VEH_POOR" in names
        assert "VEH_MID" in names
        assert "VEH_RICH" in names

    def test_create_base_template_has_flags(self):
        xml = create_base_template()
        root = etree.fromstring(xml.encode())
        veh_groups = root.find("vehGroups")
        for item in veh_groups.findall("Item"):
            flags = item.find("flags")
            assert flags is not None
            assert "POPGROUP_AMBIENT" in flags.text

    def test_inject_vehicle_into_traffic(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=["veh_mid"])]
        result = generate_popgroups_xml(base, vehicles)

        root = etree.fromstring(result.encode())
        models = _find_veh_group_models(root, "VEH_MID")
        assert "testcar" in models

    def test_inject_vehicle_has_variations(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=["veh_mid"])]
        result = generate_popgroups_xml(base, vehicles)

        root = etree.fromstring(result.encode())
        veh_groups = root.find("vehGroups")
        for item in veh_groups.findall("Item"):
            name_el = item.find("Name")
            if name_el is not None and name_el.text == "VEH_MID":
                models = item.find("models")
                for model_item in models.findall("Item"):
                    variations = model_item.find("Variations")
                    assert variations is not None
                    assert variations.get("type") == "NULL"

    def test_no_duplicates(self):
        """Each vehicle should appear exactly once per group."""
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=["veh_mid"])]
        result = generate_popgroups_xml(base, vehicles)

        root = etree.fromstring(result.encode())
        models = _find_veh_group_models(root, "VEH_MID")
        assert models.count("testcar") == 1

    def test_rich_areas_only_supers(self):
        base = create_base_template()
        vehicles = [_make_vehicle(vehicle_class="super", traffic=["veh_rich", "veh_mid"])]
        result = generate_popgroups_xml(base, vehicles, rich_areas_only_supers=True)

        root = etree.fromstring(result.encode())
        mid_models = _find_veh_group_models(root, "VEH_MID")
        assert len(mid_models) == 0, "Super car should not be in VEH_MID with restriction"

    def test_no_traffic_groups_skipped(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=[])]
        result = generate_popgroups_xml(base, vehicles)
        root = etree.fromstring(result.encode())
        # No items should have been added to any group
        veh_groups = root.find("vehGroups")
        for item in veh_groups.findall("Item"):
            models = item.find("models")
            if models is not None:
                assert len(models.findall("Item")) == 0


class TestDlclist:
    def test_add_missing_packs(self):
        dlclist = """<?xml version="1.0" encoding="UTF-8"?>
<SMandatoryPacksData>
  <Paths>
    <Item>dlcpacks:/mpchristmas2/</Item>
  </Paths>
</SMandatoryPacksData>"""
        result, added = patch_dlclist(dlclist)
        assert len(added) > 0
        assert "mpchristmas2" not in added  # Already existed
        assert "mpheist" in added

    def test_no_duplicates(self):
        dlclist = """<?xml version="1.0" encoding="UTF-8"?>
<SMandatoryPacksData>
  <Paths>
    <Item>dlcpacks:/mpchristmas2/</Item>
  </Paths>
</SMandatoryPacksData>"""
        result, _ = patch_dlclist(dlclist)
        # Patch again -- should add nothing new
        _, added2 = patch_dlclist(result)
        assert len(added2) == 0

    def test_missing_paths_is_created_and_custom_pack_is_removed(self):
        empty = "<SMandatoryPacksData/>"
        patched, added = patch_dlclist(empty)
        assert "allin1_previews" in added
        assert "allin1_maps" not in added
        patched = patched.replace(
            "</Paths>",
            "<Item>dlcpacks:/allin1_maps/</Item></Paths>",
        )
        unpatched, removed = unpatch_dlclist(patched)
        assert removed == ["allin1_previews", "allin1_maps"]
        assert "allin1_previews" not in unpatched
        assert "allin1_maps" not in unpatched

    def test_unpatch_without_paths_or_text_is_safe(self):
        source = "<SMandatoryPacksData/>"
        assert unpatch_dlclist(source) == (source, [])
        source = "<SMandatoryPacksData><Paths><Item/></Paths></SMandatoryPacksData>"
        output, removed = unpatch_dlclist(source)
        assert removed == [] and "<Item/>" in output


class TestGameconfig:
    def test_patch_pool_sizes(self):
        gameconfig = """<?xml version="1.0" encoding="UTF-8"?>
<CGameConfig>
  <pools>
    <Item>
      <Name>CVehicle</Name>
      <Size value="128"/>
    </Item>
    <Item>
      <Name>CHandlingDataMgr</Name>
      <Size value="200"/>
    </Item>
  </pools>
</CGameConfig>"""
        result = patch_gameconfig(gameconfig)
        root = etree.fromstring(result.encode())

        for item in root.iter("Item"):
            name = item.find("Name")
            size = item.find("Size")
            if name is not None and size is not None:
                if name.text == "CVehicle":
                    assert int(size.get("value")) == 512
                elif name.text == "CHandlingDataMgr":
                    assert int(size.get("value")) == 900

    def test_does_not_lower_existing_values(self):
        gameconfig = """<?xml version="1.0" encoding="UTF-8"?>
<CGameConfig>
  <pools>
    <Item>
      <Name>CVehicle</Name>
      <Size value="9999"/>
    </Item>
  </pools>
</CGameConfig>"""
        result = patch_gameconfig(gameconfig)
        root = etree.fromstring(result.encode())

        for item in root.iter("Item"):
            name = item.find("Name")
            size = item.find("Size")
            if name is not None and name.text == "CVehicle":
                assert int(size.get("value")) == 9999

    def test_patch_enhanced_pool_sizes_and_preserve_full_document(self):
        gameconfig = """<?xml version="1.0" encoding="UTF-8"?>
<!-- keep this document-level comment -->
<fwAllConfigs custom="preserved">
  <ConfigArray>
    <Item>
      <Build>any</Build>
      <Platforms>Any</Platforms>
      <Config type="CGameConfig">
        <PoolSizes>
          <Entries>
            <Item><PoolName>FragmentStore</PoolName><PoolSize value="42000"/></Item>
            <Item><PoolName>MetaDataStore</PoolName><PoolSize value="3200"/></Item>
            <Item><PoolName>TxdStore</PoolName><PoolSize value="80200"/></Item>
            <Item><PoolName>DwdStore</PoolName><PoolSize value="20500"/></Item>
            <Item><PoolName>UnrelatedPool</PoolName><PoolSize value="77"/></Item>
          </Entries>
        </PoolSizes>
        <UnrelatedSection><Sentinel value="unchanged"/></UnrelatedSection>
      </Config>
    </Item>
  </ConfigArray>
</fwAllConfigs>"""

        result = patch_gameconfig(gameconfig)
        root = etree.fromstring(result.encode())
        sizes = {
            item.findtext("PoolName"): int(item.find("PoolSize").get("value"))
            for item in root.iter("Item")
            if item.find("PoolName") is not None
        }

        assert sizes == {
            "FragmentStore": 52000,
            "MetaDataStore": 4000,
            "TxdStore": 100000,
            "DwdStore": 25000,
            "UnrelatedPool": 77,
        }
        assert root.get("custom") == "preserved"
        assert root.find(".//UnrelatedSection/Sentinel").get("value") == "unchanged"
        assert "keep this document-level comment" in result

    def test_enhanced_does_not_lower_existing_values(self):
        gameconfig = """<fwAllConfigs><ConfigArray><Item>
  <Config type="CGameConfig"><PoolSizes><Entries>
    <Item><PoolName>FragmentStore</PoolName><PoolSize value="64000"/></Item>
    <Item><PoolName>MetaDataStore</PoolName><PoolSize value="6000"/></Item>
  </Entries></PoolSizes></Config>
</Item></ConfigArray></fwAllConfigs>"""

        result = patch_gameconfig(gameconfig)
        root = etree.fromstring(result.encode())
        sizes = {
            item.findtext("PoolName"): int(item.find("PoolSize").get("value"))
            for item in root.iter("Item")
            if item.find("PoolName") is not None
        }
        assert sizes == {"FragmentStore": 64000, "MetaDataStore": 6000}

    def test_restore_map_pool_profile_only_reverts_exact_receipt_values(self):
        gameconfig = """<fwAllConfigs><ConfigArray><Item>
  <Config type="CGameConfig"><PoolSizes><Entries>
    <Item><PoolName>FragmentStore</PoolName><PoolSize value="52000"/></Item>
    <Item><PoolName>MetaDataStore</PoolName><PoolSize value="7000"/></Item>
    <Item><PoolName>TxdStore</PoolName><PoolSize value="100000"/></Item>
    <Item><PoolName>UnrelatedPool</PoolName><PoolSize value="77"/></Item>
  </Entries></PoolSizes></Config>
</Item></ConfigArray></fwAllConfigs>"""
        receipt = {
            "FragmentStore": {"before": 42000, "after": 52000},
            "MetaDataStore": {"before": 3200, "after": 4000},
            "TxdStore": {"before": 80200, "after": 100000},
        }

        result = restore_enhanced_pool_profile(gameconfig, receipt)
        root = etree.fromstring(result.encode())
        sizes = {
            item.findtext("PoolName"): int(item.find("PoolSize").get("value"))
            for item in root.iter("Item")
            if item.find("PoolName") is not None
        }

        assert sizes == {
            "FragmentStore": 42000,
            # A value changed after ALLIN1's transaction remains user-owned.
            "MetaDataStore": 7000,
            "TxdStore": 80200,
            "UnrelatedPool": 77,
        }

    @pytest.mark.parametrize(
        "receipt",
        [
            {},
            {"UnknownPool": {"before": 1, "after": 2}},
            {"FragmentStore": {"before": 52000, "after": 42000}},
            {"FragmentStore": {"before": 42000, "after": "52000"}},
        ],
    )
    def test_restore_map_pool_profile_rejects_untrusted_receipts(self, receipt):
        gameconfig = """<fwAllConfigs><ConfigArray><Item>
  <Config type="CGameConfig"><PoolSizes><Entries>
    <Item><PoolName>FragmentStore</PoolName><PoolSize value="52000"/></Item>
  </Entries></PoolSizes></Config>
</Item></ConfigArray></fwAllConfigs>"""

        with pytest.raises(ValueError):
            restore_enhanced_pool_profile(gameconfig, receipt)

    @pytest.mark.parametrize(
        ("source", "message"),
        [
            ("", "non-empty XML text"),
            ("<CGameConfig>", "Invalid gameconfig.xml"),
            ("<CGameConfig><pools/></CGameConfig>", "no Legacy Name/Size"),
            (
                "<NotAGameConfig><Item><PoolName>FragmentStore</PoolName>"
                "<PoolSize value='42000'/></Item></NotAGameConfig>",
                "Unsupported gameconfig.xml root",
            ),
            (
                "<fwAllConfigs><Item><PoolName>FragmentStore</PoolName>"
                "<PoolSize value='42000'/></Item></fwAllConfigs>",
                "no Legacy Name/Size",
            ),
            (
                "<fwAllConfigs><ConfigArray><Item><Config type='CGameConfig'>"
                "<PoolSizes><Entries><Item><PoolName>FragmentStore</PoolName>"
                "</Item></Entries></PoolSizes></Config></Item></ConfigArray></fwAllConfigs>",
                "PoolName and PoolSize must both be present",
            ),
            (
                "<CGameConfig><pools><Item><Name>CVehicle</Name>"
                "<Size value='many'/></Item></pools></CGameConfig>",
                "invalid size",
            ),
        ],
    )
    def test_rejects_invalid_or_unsupported_documents(self, source, message):
        with pytest.raises(ValueError, match=message):
            patch_gameconfig(source)
