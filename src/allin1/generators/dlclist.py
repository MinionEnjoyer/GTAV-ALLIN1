"""dlclist.xml patcher.

Ensures all GTA Online DLC packs are registered in dlclist.xml so the game
engine loads their vehicle models in single player.  Also registers ALLIN1's
own custom DLC packs (e.g. preview texture dictionaries).
"""

from __future__ import annotations

import logging

from lxml import etree

log = logging.getLogger("allin1.generators.dlclist")

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

# Custom DLC packs that are safe to register at startup.
CUSTOM_DLC_PACKS = [
    "allin1_previews",  # Vehicle preview texture dictionaries for GBAY browser
]

# Includes dormant/quarantined packs so uninstall can still remove entries
# written by an older release.  Do not feed this list to patch_dlclist().
OWNED_DLC_PACKS = [
    *CUSTOM_DLC_PACKS,
    "allin1_maps",
    "allin1_mp2024_02_garment_bridge",
    "allin1_mpbattle_harmony_bridge",
    "allin1_mpvinewood_paleto_bridge",
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

    log.debug("Found %d existing DLC pack(s) in dlclist.xml", len(existing))

    added: list[str] = []
    all_packs = REQUIRED_DLC_PACKS + CUSTOM_DLC_PACKS
    for pack in all_packs:
        if pack.lower() not in existing:
            item = etree.SubElement(paths_el, "Item")
            item.text = f"dlcpacks:/{pack}/"
            added.append(pack)
            log.debug("Adding missing DLC pack: %s", pack)

    if added:
        log.info("Added %d DLC pack(s) to dlclist.xml", len(added))
    else:
        log.info("All %d required DLC packs already present", len(all_packs))

    output = '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")
    return output, added


def unpatch_dlclist(dlclist_xml: str) -> tuple[str, list[str]]:
    """Remove ALLIN1 custom DLC packs from dlclist.xml.

    Only removes entries from OWNED_DLC_PACKS, not Rockstar DLC packs. This
    includes obsolete allin1_maps registrations written by older releases.

    Returns:
        Tuple of (patched XML string, list of packs that were removed).
    """
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(dlclist_xml.encode(), parser)

    paths_el = root.find("Paths")
    if paths_el is None:
        return dlclist_xml, []

    custom_lower = {p.lower() for p in OWNED_DLC_PACKS}
    removed: list[str] = []

    for item in list(paths_el.findall("Item")):
        if item.text:
            pack = item.text.strip().strip("/").split("/")[-1].lower()
            if pack in custom_lower:
                paths_el.remove(item)
                removed.append(pack)
                log.debug("Removed custom DLC pack: %s", pack)

    if removed:
        log.info("Removed %d custom DLC pack(s) from dlclist.xml", len(removed))

    output = '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(root, pretty_print=True, encoding="unicode")
    return output, removed
