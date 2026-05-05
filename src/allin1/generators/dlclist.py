"""dlclist.xml patcher.

Ensures all GTA Online DLC packs are registered in dlclist.xml so the game
engine loads their vehicle models in single player.
"""

from __future__ import annotations

from lxml import etree

# All MP DLC packs that contain vehicles. These should already be present in
# a standard GTA V install, but we verify and add any missing entries.
# Order matches Rockstar's update history.
REQUIRED_DLC_PACKS = [
    "mpchristmas2",
    "mpheist",
    "mpluxe",
    "mpluxe2",
    "mplowrider",
    "mphalloween",
    "mpxmas_604490",
    "mpjanuary2016",
    "mpvalentines2",
    "mplowrider2",
    "mpexecutive",
    "mpstunt",
    "mpimportexport",
    "mpgunrunning",
    "mpsmuggler",
    "mpdoomsday",
    "mpchristmas2017",
    "mpassault",
    "mpbattle",
    "mpchristmas2018",
    "mparena",
    "mpvinewood",
    "mpheist3",
    "mpheist4",
    "mpsum",
    "mpchristmas3",
    "mptuner",
    "mpsecurity",
    "mpg9ec",
    "mpsum2",
    "mpchristmas3_b",
    "mp2023_01",
    "mp2023_02",
    "mpchristmas2023",
    "mp2024_01",
    "mp2024_02",
    "mpchristmas2024",
    "mp2025_01",
]


def patch_dlclist(dlclist_xml: str) -> tuple[str, list[str]]:
    """Ensure all required DLC packs are in dlclist.xml.

    Args:
        dlclist_xml: Content of the existing dlclist.xml file.

    Returns:
        Tuple of (patched XML string, list of packs that were added).
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(dlclist_xml.encode(), parser)

    paths_el = root.find("Paths")
    if paths_el is None:
        paths_el = etree.SubElement(root, "Paths")

    # Collect existing entries (normalized to lowercase)
    existing: set[str] = set()
    for item in paths_el.findall("Item"):
        if item.text:
            # Extract pack name from path like "dlcpacks:/mpheist/"
            pack = item.text.strip().strip("/").split("/")[-1].lower()
            existing.add(pack)

    added: list[str] = []
    for pack in REQUIRED_DLC_PACKS:
        if pack.lower() not in existing:
            item = etree.SubElement(paths_el, "Item")
            item.text = f"dlcpacks:/{pack}/"
            added.append(pack)

    output = '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")
    return output, added
