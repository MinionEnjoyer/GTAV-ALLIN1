"""Generate a GTA V DLC pack for ALLIN1 preview texture dictionaries.

Creates the folder structure with content.xml and setup2.xml.  The .ytd
files are placed into a staging directory that RpfPatcher packs into a
nested ``textures.rpf`` inside the outer ``dlc.rpf``.

The DLC pack mirrors Rockstar's own structure:

    dlc.rpf/
      content.xml
      setup2.xml
      x64/textures/textures.rpf   <-- nested RPF containing all .ytd files

``content.xml`` registers ``textures.rpf`` as an ``RPF_FILE`` so that
GTA's streaming system can find the .ytd files inside it and serve them
via ``REQUEST_STREAMED_TEXTURE_DICT``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from lxml import etree

log = logging.getLogger("allin1.generators.dlc_previews")

DLC_NAME = "allin1_previews"
DEVICE_NAME = f"dlc_{DLC_NAME}"
TEXTURES_RPF = "textures.rpf"


def _build_content_xml() -> bytes:
    """Generate content.xml registering the nested textures.rpf as RPF_FILE.

    Matches the structure of working Rockstar / community DLC packs:
    each dataFile entry has locked=false, disabled=true, persistent=true,
    overlay=true, and the contentChangeSet enables them at startup.
    """
    root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")

    etree.SubElement(root, "disabledFiles")
    etree.SubElement(root, "includedXmlFiles")
    etree.SubElement(root, "includedDataFiles")

    data_files = etree.SubElement(root, "dataFiles")

    # Register the nested textures.rpf as RPF_FILE — the game's streaming
    # system will index the .ytd files inside it automatically.
    rpf_path = f"{DEVICE_NAME}:/%PLATFORM%/textures/{TEXTURES_RPF}"

    item = etree.SubElement(data_files, "Item")
    etree.SubElement(item, "filename").text = rpf_path
    etree.SubElement(item, "fileType").text = "RPF_FILE"
    etree.SubElement(item, "locked").set("value", "false")
    etree.SubElement(item, "disabled").set("value", "true")
    etree.SubElement(item, "persistent").set("value", "true")
    etree.SubElement(item, "overlay").set("value", "true")

    # Content change set — enable the RPF at startup
    change_sets = etree.SubElement(root, "contentChangeSets")
    cs_item = etree.SubElement(change_sets, "Item")
    etree.SubElement(cs_item, "changeSetName").text = f"{DLC_NAME}_AUTOGEN"
    files_to_enable = etree.SubElement(cs_item, "filesToEnable")
    etree.SubElement(files_to_enable, "Item").text = rpf_path

    etree.SubElement(root, "patchFiles")

    return etree.tostring(root, pretty_print=True, xml_declaration=True,
                          encoding="UTF-8")


def _build_setup2_xml() -> bytes:
    """Generate setup2.xml for the DLC pack."""
    root = etree.Element("SSetupData")

    etree.SubElement(root, "deviceName").text = DEVICE_NAME
    etree.SubElement(root, "datFile").text = "content.xml"
    etree.SubElement(root, "timeStamp").text = "01/01/2025 00:00:00"
    etree.SubElement(root, "nameHash").text = DLC_NAME
    etree.SubElement(root, "type").text = "EXTRACONTENT_COMPAT_PACK"
    el = etree.SubElement(root, "order")
    el.set("value", "9")

    groups = etree.SubElement(root, "contentChangeSetGroups")
    group_item = etree.SubElement(groups, "Item")
    etree.SubElement(group_item, "NameHash").text = "GROUP_STARTUP"
    change_sets = etree.SubElement(group_item, "ContentChangeSets")
    etree.SubElement(change_sets, "Item").text = f"{DLC_NAME}_AUTOGEN"

    return etree.tostring(root, pretty_print=True, xml_declaration=True,
                          encoding="UTF-8")


def create_dlc_pack(
    ytd_files: list[Path],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Create the DLC folder structure with content.xml, setup2.xml, and .ytd staging.

    The .ytd files are placed into a separate staging directory
    (``<output_dir>/ytd_staging/``) rather than directly in the DLC tree.
    The caller is responsible for packing them into ``textures.rpf`` (via
    RpfPatcher) and placing the result at ``x64/textures/textures.rpf``
    inside the DLC root before packing the outer ``dlc.rpf``.

    Returns ``(dlc_root, ytd_staging_dir)``.
    """
    dlc_root = output_dir / DLC_NAME
    dlc_root.mkdir(parents=True, exist_ok=True)

    # Stage .ytd files in a separate flat directory for inner RPF packing
    ytd_staging = output_dir / "ytd_staging"
    ytd_staging.mkdir(parents=True, exist_ok=True)

    for ytd in ytd_files:
        dest = ytd_staging / ytd.name
        shutil.copy2(ytd, dest)
        log.debug("Staged %s -> %s", ytd.name, dest)

    # Generate XML metadata
    content_xml = _build_content_xml()
    (dlc_root / "content.xml").write_bytes(content_xml)
    log.debug("Wrote content.xml")

    setup2_xml = _build_setup2_xml()
    (dlc_root / "setup2.xml").write_bytes(setup2_xml)
    log.debug("Wrote setup2.xml")

    log.info("Created DLC pack at %s (%d .ytd files staged)", dlc_root, len(ytd_files))
    return dlc_root, ytd_staging


def deploy_dlc_rpf(
    dlc_rpf: Path,
    gta_path: Path,
) -> Path:
    """Deploy dlc.rpf into the mods dlcpacks folder.

    Copies the built dlc.rpf to:
        <GTA V>/mods/update/x64/dlcpacks/allin1_previews/dlc.rpf

    GTA V requires each DLC pack to have its content inside a dlc.rpf
    archive — loose files in the dlcpacks directory are not loaded.

    Returns the deployment directory.
    """
    dest_dir = gta_path / "mods" / "update" / "x64" / "dlcpacks" / DLC_NAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    destination = dest_dir / "dlc.rpf"
    temporary = dest_dir / "dlc.rpf.tmp"
    backup = dest_dir / "dlc.rpf.bak"
    try:
        shutil.copy2(dlc_rpf, temporary)
        if destination.exists():
            shutil.copy2(destination, backup)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        if backup.exists():
            shutil.copy2(backup, destination)
        raise
    log.info("Deployed dlc.rpf -> %s", destination)

    # Clean up old location (pre-mods-folder installs) and any stale loose files
    old_dir = gta_path / "update" / "x64" / "dlcpacks" / DLC_NAME
    if old_dir.exists():
        shutil.rmtree(old_dir)
        log.info("Removed old DLC pack at %s", old_dir)

    return dest_dir


def remove_dlc_pack(gta_path: Path) -> bool:
    """Remove the ALLIN1 preview DLC pack from the game directory."""
    removed = False
    for base in ("mods/update", "update"):
        dest_dir = gta_path / base / "x64" / "dlcpacks" / DLC_NAME
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
            log.info("Removed DLC pack at %s", dest_dir)
            removed = True
    return removed
