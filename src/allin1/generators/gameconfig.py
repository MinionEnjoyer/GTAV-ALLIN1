"""gameconfig.xml pool size patcher.

Increases memory pool limits so the game can handle 400+ additional
vehicle models without running out of resources.
"""

from __future__ import annotations

from lxml import etree

# Pool sizes needed for 400+ extra vehicles. These values are based on
# community-tested gameconfig mods that support large vehicle counts.
POOL_OVERRIDES = {
    "CVehicle": 512,
    "CVehicleStreamRequest": 100,
    "CVehicleStreamRender": 512,
    "CVehicleStruct": 512,
    "CHandlingDataMgr": 900,
    "CVehicleModelInfo": 900,
    "CBaseModelInfo": 1400,
    "CMapData": 1024,
    "CMapDataContents": 200,
    "CPickup": 400,
    "CObject": 2048,
    "fwArchetypeDef": 1800,
    "fwArchetypePooledMap": 600,
    "fwDrawableDef": 1200,
    "FragInst": 300,
    "phBoundComposite": 500,
    "phBound": 1500,
}


def patch_gameconfig(gameconfig_xml: str) -> str:
    """Patch gameconfig.xml to increase pool sizes for large vehicle counts.

    Args:
        gameconfig_xml: Content of the existing gameconfig.xml.

    Returns:
        Patched XML string.
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(gameconfig_xml.encode(), parser)

    # gameconfig pool sizes live under various paths depending on the version.
    # Walk all pool size definitions and bump any that match our overrides.
    for pool_el in root.iter("Item"):
        name_el = pool_el.find("Name")
        size_el = pool_el.find("Size")

        if name_el is None or size_el is None:
            continue

        pool_name = (name_el.text or "").strip()
        if pool_name in POOL_OVERRIDES:
            current = int(size_el.get("value", "0"))
            target = POOL_OVERRIDES[pool_name]
            if current < target:
                size_el.set("value", str(target))

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")
