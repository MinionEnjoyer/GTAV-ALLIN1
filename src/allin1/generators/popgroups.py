"""Traffic population groups generator.

Injects MP vehicle model names into the appropriate popgroups traffic
categories so they appear as ambient traffic in single player.
"""

from __future__ import annotations

from lxml import etree

from allin1.vehicles.database import Vehicle

# Density multiplier: how many times each vehicle is added to its traffic group.
# More entries = higher chance of spawning relative to vanilla vehicles.
DENSITY_MULTIPLIERS = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 4,
}

# Base popgroups XML structure. In a real install this would be extracted from
# the game's popgroups.ymt via CodeWalker, but we ship a minimal template that
# contains the group names we need to inject into.
BASE_GROUPS = [
    "veh_poor",
    "veh_mid",
    "veh_rich",
    "veh_freeway",
    "veh_countryside_onroad",
    "veh_boats",
]


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
        rich_areas_only_supers: If True, super cars only go in veh_rich.

    Returns:
        Modified XML string ready to be converted back to .ymt format.
    """
    multiplier = DENSITY_MULTIPLIERS.get(density, 2)
    if multiplier == 0:
        return base_xml

    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(base_xml.encode(), parser)

    # Build a lookup of group name -> XML element
    group_elements: dict[str, etree._Element] = {}
    for group_el in root.iter("popcycle_group"):
        name_el = group_el.find("Name")
        if name_el is not None and name_el.text:
            group_elements[name_el.text.strip().lower()] = group_el

    for vehicle in vehicles:
        if not vehicle.traffic:
            continue

        target_groups = list(vehicle.traffic)

        # If restricting supers to rich areas, remove non-rich groups
        if rich_areas_only_supers and vehicle.vehicle_class in ("super", "sportsclassics"):
            target_groups = [g for g in target_groups if g == "veh_rich"]
            if not target_groups:
                target_groups = ["veh_rich"]

        for group_name in target_groups:
            group_el = group_elements.get(group_name.lower())
            if group_el is None:
                continue

            models_el = group_el.find("Models")
            if models_el is None:
                models_el = etree.SubElement(group_el, "Models")

            # Add the vehicle model name N times based on density
            for _ in range(multiplier):
                item = etree.SubElement(models_el, "Item")
                name = etree.SubElement(item, "Name")
                name.text = vehicle.model

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")


def create_base_template() -> str:
    """Create a minimal base popgroups XML template.

    This is used when the user doesn't have a game-extracted popgroups.ymt.
    It contains only the group definitions we inject into. A full install
    should use the actual game file extracted via CodeWalker.
    """
    root = etree.Element("CPopGroupList")

    for group_name in BASE_GROUPS:
        group = etree.SubElement(root, "popcycle_group")
        name = etree.SubElement(group, "Name")
        name.text = group_name
        etree.SubElement(group, "Models")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")
