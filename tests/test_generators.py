"""Tests for generator modules."""

from lxml import etree

from allin1.generators.dlclist import patch_dlclist
from allin1.generators.gameconfig import patch_gameconfig
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


class TestPopgroups:
    def test_create_base_template(self):
        xml = create_base_template()
        root = etree.fromstring(xml.encode())
        groups = [el.text for el in root.iter("Name")]
        assert "veh_poor" in groups
        assert "veh_mid" in groups
        assert "veh_rich" in groups

    def test_inject_vehicle_into_traffic(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=["veh_mid"])]
        result = generate_popgroups_xml(base, vehicles, density="low")

        root = etree.fromstring(result.encode())
        # Find the veh_mid group and check the vehicle was added
        for group in root.iter("popcycle_group"):
            name_el = group.find("Name")
            if name_el is not None and name_el.text == "veh_mid":
                models = group.find("Models")
                names = [item.find("Name").text for item in models.findall("Item")]
                assert "testcar" in names
                break
        else:
            raise AssertionError("veh_mid group not found")

    def test_density_none_returns_unchanged(self):
        base = create_base_template()
        vehicles = [_make_vehicle()]
        result = generate_popgroups_xml(base, vehicles, density="none")
        assert result == base

    def test_density_multiplier(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=["veh_mid"])]

        result_low = generate_popgroups_xml(base, vehicles, density="low")
        result_high = generate_popgroups_xml(base, vehicles, density="high")

        root_low = etree.fromstring(result_low.encode())
        root_high = etree.fromstring(result_high.encode())

        def count_items(root):
            for group in root.iter("popcycle_group"):
                name_el = group.find("Name")
                if name_el is not None and name_el.text == "veh_mid":
                    return len(group.find("Models").findall("Item"))
            return 0

        assert count_items(root_low) == 1
        assert count_items(root_high) == 4

    def test_rich_areas_only_supers(self):
        base = create_base_template()
        vehicles = [_make_vehicle(vehicle_class="super", traffic=["veh_rich", "veh_mid"])]
        result = generate_popgroups_xml(base, vehicles, density="low", rich_areas_only_supers=True)

        root = etree.fromstring(result.encode())
        for group in root.iter("popcycle_group"):
            name_el = group.find("Name")
            if name_el is not None and name_el.text == "veh_mid":
                models = group.find("Models")
                items = models.findall("Item") if models is not None else []
                assert len(items) == 0, "Super car should not be in veh_mid with restriction"

    def test_no_traffic_groups_skipped(self):
        base = create_base_template()
        vehicles = [_make_vehicle(traffic=[])]
        result = generate_popgroups_xml(base, vehicles, density="medium")
        # Should be same as base (no items added)
        root = etree.fromstring(result.encode())
        for group in root.iter("popcycle_group"):
            models = group.find("Models")
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
