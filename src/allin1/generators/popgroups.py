"""Traffic population groups generator.

Injects MP vehicle model names into the appropriate popgroups traffic
categories so they appear as ambient traffic in single player.

The popgroups.ymt XML schema uses this structure:
  <CPopGroupList>
    <pedGroups>...</pedGroups>
    <vehGroups>
      <Item>
        <Name>VEH_POOR</Name>
        <models>
          <Item>
            <Name>asea</Name>
            <Variations type="NULL"/>
          </Item>
        </models>
        <flags>POPGROUP_SCENARIO POPGROUP_AMBIENT</flags>
      </Item>
    </vehGroups>
  </CPopGroupList>
"""

from __future__ import annotations

import logging

from lxml import etree

from allin1.vehicles.database import Vehicle

log = logging.getLogger("allin1.generators.popgroups")

# Density multiplier: how many times each vehicle is added to its traffic group.
# More entries = higher chance of spawning relative to vanilla vehicles.
DENSITY_MULTIPLIERS = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 4,
}

# Vehicle groups we inject into.  Names are UPPERCASE to match the game format.
# The vehicle database uses lowercase (veh_poor) — we normalize on lookup.
BASE_VEH_GROUPS = [
    "VEH_POOR",
    "VEH_MID",
    "VEH_RICH",
    "VEH_FREEWAY",
    "VEH_COUNTRYSIDE_ONROAD",
    "VEH_BOATS",
]


def _add_vehicle_item(parent: etree._Element, model_name: str) -> None:
    """Append a single vehicle <Item> to a <models> element."""
    item = etree.SubElement(parent, "Item")
    name = etree.SubElement(item, "Name")
    name.text = model_name
    variations = etree.SubElement(item, "Variations")
    variations.set("type", "NULL")


def generate_popgroups_xml(
    base_xml: str,
    vehicles: list[Vehicle],
    density: str = "medium",
    rich_areas_only_supers: bool = True,
) -> str:
    """Generate a modified popgroups XML with MP vehicles injected.

    Args:
        base_xml: The base popgroups XML content (from template or game extract).
        vehicles: List of enabled vehicles to add.
        density: Traffic density level ("none", "low", "medium", "high").
        rich_areas_only_supers: If True, super cars only go in VEH_RICH.

    Returns:
        Modified XML string in the correct popgroups.ymt format.
    """
    multiplier = DENSITY_MULTIPLIERS.get(density, 2)
    if multiplier == 0:
        log.info("Density is 'none' — returning base XML unchanged")
        return base_xml

    log.info("Generating popgroups: %d vehicles, density=%s (x%d), rich_only_supers=%s",
             len(vehicles), density, multiplier, rich_areas_only_supers)

    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(base_xml.encode(), parser)

    # Build a lookup of group name (uppercase) -> <models> element.
    # The game uses <vehGroups> -> <Item> -> <Name> + <models>.
    group_models: dict[str, etree._Element] = {}

    veh_groups_el = root.find("vehGroups")
    if veh_groups_el is not None:
        for item_el in veh_groups_el.findall("Item"):
            name_el = item_el.find("Name")
            if name_el is not None and name_el.text:
                models_el = item_el.find("models")
                if models_el is None:
                    models_el = etree.SubElement(item_el, "models")
                group_models[name_el.text.strip().upper()] = models_el

    for vehicle in vehicles:
        if not vehicle.traffic:
            continue

        target_groups = [g.upper() for g in vehicle.traffic]

        # If restricting supers to rich areas, remove non-rich groups
        if rich_areas_only_supers and vehicle.vehicle_class in ("super", "sportsclassics"):
            target_groups = [g for g in target_groups if g == "VEH_RICH"]
            if not target_groups:
                target_groups = ["VEH_RICH"]

        for group_name in target_groups:
            models_el = group_models.get(group_name)
            if models_el is None:
                continue

            # Add the vehicle model name N times based on density
            for _ in range(multiplier):
                _add_vehicle_item(models_el, vehicle.model)

    injected = sum(1 for v in vehicles if v.traffic)
    log.info("Injected %d vehicle(s) into traffic groups", injected)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(
        root, pretty_print=True, encoding="unicode")


def create_base_template() -> str:
    """Create a minimal base popgroups XML template.

    This is used when the user doesn't have a game-extracted popgroups.ymt.
    It contains only the vehicle group definitions we inject into.
    For best results, extract the full popgroups.ymt from your game
    using CodeWalker — it includes vanilla vehicles and ped groups.
    """
    root = etree.Element("CPopGroupList")

    # Empty pedGroups (vanilla peds would normally be here)
    etree.SubElement(root, "pedGroups")

    # Vehicle groups
    veh_groups = etree.SubElement(root, "vehGroups")
    for group_name in BASE_VEH_GROUPS:
        item = etree.SubElement(veh_groups, "Item")
        name = etree.SubElement(item, "Name")
        name.text = group_name
        etree.SubElement(item, "models")
        flags = etree.SubElement(item, "flags")
        flags.text = "POPGROUP_SCENARIO POPGROUP_AMBIENT"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(
        root, pretty_print=True, encoding="unicode")
