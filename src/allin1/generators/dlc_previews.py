"""Generate a GTA V DLC pack for ALLIN1 preview texture dictionaries.

Creates the folder structure with content.xml and setup2.xml, then
optionally builds dlc.rpf using gtautil.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from lxml import etree

log = logging.getLogger("allin1.generators.dlc_previews")

DLC_NAME = "allin1_previews"
DEVICE_NAME = f"dlc_{DLC_NAME}"


def _build_content_xml(ytd_names: list[str]) -> bytes:
    """Generate content.xml registering each .ytd as a TEXTUREDICT."""
    root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")

    etree.SubElement(root, "disabledFiles")
    etree.SubElement(root, "includedXmlFiles")
    etree.SubElement(root, "includedDataFiles")

    data_files = etree.SubElement(root, "dataFiles")
    changeset_files: list[str] = []

    for name in ytd_names:
        path = f"{DEVICE_NAME}:/x64/textures/{name}.ytd"

        item = etree.SubElement(data_files, "Item")
        etree.SubElement(item, "filename").text = path
        etree.SubElement(item, "fileType").text = "TEXTUREDICT"
        el = etree.SubElement(item, "overlay")
        el.set("value", "false")
        el = etree.SubElement(item, "disabled")
        el.set("value", "true")
        el = etree.SubElement(item, "persistent")
        el.set("value", "false")

        changeset_files.append(path)

    change_sets = etree.SubElement(root, "contentChangeSets")
    cs_item = etree.SubElement(change_sets, "Item")
    etree.SubElement(cs_item, "changeSetName").text = f"{DLC_NAME}_AUTOGEN"
    files_to_enable = etree.SubElement(cs_item, "filesToEnable")
    for f in changeset_files:
        etree.SubElement(files_to_enable, "Item").text = f

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
) -> Path:
    """Create the DLC folder structure with content.xml, setup2.xml, and .ytd files.

    Returns the path to the DLC pack root folder (ready for RPF packing).
    """
    dlc_root = output_dir / DLC_NAME
    textures_dir = dlc_root / "x64" / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)

    # Copy .ytd files into the texture directory
    ytd_names: list[str] = []
    for ytd in ytd_files:
        dest = textures_dir / ytd.name
        log.debug("Copying %s (%s) -> %s", ytd, "exists" if ytd.exists() else "MISSING", dest)
        shutil.copy2(ytd, dest)
        ytd_names.append(ytd.stem)
        log.debug("Copied %s -> %s", ytd.name, dest)

    # Generate XML metadata
    content_xml = _build_content_xml(ytd_names)
    (dlc_root / "content.xml").write_bytes(content_xml)
    log.debug("Wrote content.xml")

    setup2_xml = _build_setup2_xml()
    (dlc_root / "setup2.xml").write_bytes(setup2_xml)
    log.debug("Wrote setup2.xml")

    log.info("Created DLC pack at %s (%d .ytd files)", dlc_root, len(ytd_names))
    return dlc_root


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
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dlc_rpf, dest_dir / "dlc.rpf")
    log.info("Deployed dlc.rpf -> %s", dest_dir / "dlc.rpf")

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
