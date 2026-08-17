"""Build the locally generated ALLIN1 standalone map DLC.

Rockstar's Online map RPFs live behind ``GROUP_MAP`` content changesets.
Switching the whole game to the multiplayer map just to expose one interior
also swaps global Story Mode state and can cause loading screens, missing
furniture, and collision races.

The installer extracts only the required entries from the player's own GTA V
installation and rearranges them inside an ALLIN1-owned compatibility pack.
No Rockstar map assets are stored in the repository or public release.
"""

from __future__ import annotations

import logging
import shutil
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

log = logging.getLogger("allin1.generators.dlc_maps")

DLC_NAME = "allin1_maps"
DEVICE_NAME = f"dlc_{DLC_NAME}"
CHANGESET_NAME = "ALLIN1_MAPS_AUTOGEN"
STREAMING_CHANGESET_NAME = "ALLIN1_MAPS_STREAMING_MAP"
ACTIVE_MARKER = "allin1_maps.active"


@dataclass(frozen=True)
class MapAsset:
    source_pack: str
    source_path: str
    destination_path: str
    source_archive_name: str = "dlc.rpf"
    file_type: str = "RPF_FILE"
    persistent: bool = True
    overlay: bool = False
    contents: str | None = None
    proxy_names: tuple[str, ...] = ()

    @property
    def filename(self) -> str:
        path = self.destination_path.replace("x64/", "%PLATFORM%/", 1)
        return f"{DEVICE_NAME}:/{path}"

    def source_archive(self, gta_path: Path) -> Path:
        return (
            gta_path / "update" / "x64" / "dlcpacks"
            / self.source_pack / self.source_archive_name
        )

    def destination(self, dlc_root: Path) -> Path:
        return dlc_root.joinpath(*self.destination_path.split("/"))


def _proxy(
    source_pack: str, tag: str, *proxy_names: str,
) -> MapAsset:
    if not proxy_names:
        raise ValueError("A filtered proxy asset needs at least one proxy name")
    return MapAsset(
        source_pack,
        "common/data/interiorProxies.meta",
        f"common/data/allin1/{source_pack}_{tag}_interiorProxies.meta",
        file_type="INTERIOR_PROXY_ORDER_FILE",
        persistent=False,
        contents=None,
        proxy_names=tuple(proxy_names),
    )


def _rpf(
    source_pack: str, path: str, source_archive_name: str = "dlc.rpf",
    *, map_data: bool = False,
) -> MapAsset:
    # Rockstar classifies placement archives as DLC map data.  Without this
    # flag the outer RPF can stream the MLO shell/collision while the interior
    # never reaches its ready state, leaving entity-set props inert.
    archive_name = Path(path).name.lower()
    contents = (
        "CONTENTS_DLC_MAP_DATA"
        if map_data or archive_name.startswith("int_placement") else None
    )
    return MapAsset(
        source_pack, path, path, source_archive_name=source_archive_name,
        contents=contents,
    )


# Entries copied locally from the user's installed Rockstar DLC archives.
# Keep these grouped by feature so future garages can be added deliberately.
MAP_ASSETS: tuple[MapAsset, ...] = (
    # Shared High Life six-car shell used by the Grapeseed Garage, plus the
    # heist yacht shell/interior used by the fixed Super Yacht world asset.
    _rpf("mpheist", "x64/levels/gta5/interiors/dlc_garage_high_new.rpf"),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_citye/hollywood_01/hw1_blimp.rpf",
    ),
    _rpf("mpheist", "x64/levels/gta5/interiors/mpheist_yacht.rpf"),
    _rpf(
        "mpheist", "x64/levels/gta5/_hills/cityhills_01/ch1_yacht.rpf"
    ),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_hills/cityhills_01/ch1_yacht_lod.rpf",
    ),
    _rpf("mpheist", "x64/levels/gta5/_hills/cityhills_01/yacht.rpf"),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_hills/cityhills_01/yacht_metadata.rpf",
    ),
    # Los Santos Tuners Auto Shop used by the Davis garage.
    *tuple(
        _rpf("mptuner", f"x64/levels/gta5/interiors/{name}.rpf")
        for name in (
            "dlc_int_01_tr", "dlc_int_02_tr", "dlc_int_04_tr",
            "int_placement_tr",
        )
    ),

    # After Hours nightclub garage used by the five-floor Harmony Garage.
    *tuple(
        _rpf(
            "mpbattle", f"x64/levels/gta5/interiors/{name}.rpf",
            source_archive_name="dlc1.rpf",
            # The nightclub's floor and detail variations are MLO entity
            # sets, not ordinary streamed props. A generic RPF mount can
            # expose the bare shell while leaving those sets inert. Keep all
            # four archives in the map-data mount used by the proven local
            # probe, while limiting the override to Harmony.
            map_data=True,
        )
        for name in (
            "int_01_ba", "int_02_ba", "int_03_ba", "int_placement_ba",
        )
    ),

    # Diamond Casino penthouse garage used by the Paleto Bay Garage.
    *tuple(
        _rpf("mpvinewood", f"x64/levels/gta5/interiors/{name}.rpf")
        for name in (
            "vwdlc_int_01", "vwdlc_int_02", "vwdlc_int_03",
            "vwdlc_int_05", "int_placement_vw",
        )
    ),

    # Agents of Sabotage garment-factory garage.
    *tuple(
        _rpf("mp2024_02", f"x64/levels/gta5/interiors/{name}.rpf")
        for name in (
            "int_01", "int_02", "int_03", "int_placement",
        )
    ),
)


def filter_staged_proxy_assets(
    dlc_root: Path, assets: tuple[MapAsset, ...] | None = None,
) -> list[Path]:
    """Reduce copied proxy tables to the exact ALLIN1-owned interiors.

    ``startFrom`` is a global interior-order index.  It must be shifted by the
    original position of the first retained proxy; renumbering a selected
    entry from the source table's beginning can corrupt unrelated Story Mode
    interiors.  Each generated proxy asset therefore contains one contiguous
    source range with its original global index preserved.
    """
    if assets is None:
        assets = MAP_ASSETS
    filtered: list[Path] = []
    for asset in assets:
        if not asset.proxy_names:
            continue

        path = asset.destination(dlc_root)
        try:
            tree = etree.parse(str(path))
        except (OSError, etree.XMLSyntaxError) as exc:
            raise ValueError(f"Invalid interior proxy metadata: {path}") from exc

        root = tree.getroot()
        start_node = root.find("startFrom")
        proxies_node = root.find("proxies")
        if start_node is None or proxies_node is None:
            raise ValueError(f"Incomplete interior proxy metadata: {path}")

        try:
            source_start = int(start_node.get("value", ""))
        except ValueError as exc:
            raise ValueError(f"Invalid proxy startFrom value: {path}") from exc

        source_items = list(proxies_node.findall("Item"))
        source_names = [(item.text or "").strip() for item in source_items]
        try:
            indices = [source_names.index(name) for name in asset.proxy_names]
        except ValueError as exc:
            missing = [name for name in asset.proxy_names if name not in source_names]
            raise ValueError(
                f"Required interior proxies are missing from {path}: "
                + ", ".join(missing)
            ) from exc

        first = indices[0]
        expected = list(range(first, first + len(indices)))
        if indices != expected:
            raise ValueError(
                f"Interior proxy selection must be contiguous in {path}: "
                + ", ".join(asset.proxy_names)
            )

        selected = [deepcopy(source_items[index]) for index in indices]
        for item in source_items:
            proxies_node.remove(item)
        for item in selected:
            proxies_node.append(item)
        start_node.set("value", str(source_start + first))
        tree.write(
            str(path), pretty_print=True, xml_declaration=True,
            encoding="UTF-8",
        )
        filtered.append(path)

    return filtered


def _build_content_xml(
    assets: tuple[MapAsset, ...] | None = None,
) -> bytes:
    if assets is None:
        assets = MAP_ASSETS
    root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
    etree.SubElement(root, "disabledFiles")
    etree.SubElement(root, "includedXmlFiles")
    etree.SubElement(root, "includedDataFiles")

    data_files = etree.SubElement(root, "dataFiles")
    for entry in assets:
        item = etree.SubElement(data_files, "Item")
        etree.SubElement(item, "filename").text = entry.filename
        etree.SubElement(item, "fileType").text = entry.file_type
        etree.SubElement(item, "overlay").set(
            "value", str(entry.overlay).lower()
        )
        etree.SubElement(item, "disabled").set("value", "true")
        etree.SubElement(item, "persistent").set(
            "value", str(entry.persistent).lower()
        )
        if entry.contents:
            etree.SubElement(item, "contents").text = entry.contents

    change_sets = etree.SubElement(root, "contentChangeSets")
    change = etree.SubElement(change_sets, "Item")
    etree.SubElement(change, "changeSetName").text = CHANGESET_NAME
    etree.SubElement(change, "mapChangeSetData")
    etree.SubElement(change, "filesToInvalidate")
    etree.SubElement(change, "filesToDisable")
    enabled = etree.SubElement(change, "filesToEnable")
    for entry in assets:
        if entry.file_type == "RPF_FILE":
            continue
        etree.SubElement(enabled, "Item").text = entry.filename
    etree.SubElement(change, "txdToLoad")
    etree.SubElement(change, "txdToUnload")
    etree.SubElement(change, "residentResources")
    etree.SubElement(change, "unregisterResources")
    etree.SubElement(change, "requiresLoadingScreen").set("value", "false")

    # Map archives belong to the Story/MP map transition, not GROUP_STARTUP.
    # Mounting copied Rockstar map RPFs during boot can collide with the base
    # Story world before its map order has been established.
    streaming = etree.SubElement(change_sets, "Item")
    etree.SubElement(streaming, "changeSetName").text = (
        STREAMING_CHANGESET_NAME
    )
    map_data = etree.SubElement(streaming, "mapChangeSetData")
    map_item = etree.SubElement(map_data, "Item")
    etree.SubElement(map_item, "associatedMap").text = "MO_JIM_L11"
    etree.SubElement(map_item, "filesToInvalidate")
    etree.SubElement(map_item, "filesToDisable")
    map_enabled = etree.SubElement(map_item, "filesToEnable")
    for entry in assets:
        if entry.file_type == "RPF_FILE":
            etree.SubElement(map_enabled, "Item").text = entry.filename
    etree.SubElement(map_item, "txdToLoad")
    etree.SubElement(map_item, "txdToUnload")
    etree.SubElement(map_item, "residentResources")
    etree.SubElement(map_item, "unregisterResources")
    etree.SubElement(streaming, "requiresLoadingScreen").set("value", "true")
    etree.SubElement(streaming, "loadingScreenContext").text = (
        "LOADINGSCREEN_CONTEXT_LAST_FRAME"
    )
    etree.SubElement(streaming, "useCacheLoader").set("value", "true")

    etree.SubElement(root, "patchFiles")
    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    )


def _build_setup2_xml() -> bytes:
    root = etree.Element("SSetupData")
    etree.SubElement(root, "deviceName").text = DEVICE_NAME
    etree.SubElement(root, "datFile").text = "content.xml"
    etree.SubElement(root, "timeStamp").text = "08/14/2026 00:00:00"
    etree.SubElement(root, "nameHash").text = DLC_NAME
    etree.SubElement(root, "contentChangeSets")

    groups = etree.SubElement(root, "contentChangeSetGroups")
    group = etree.SubElement(groups, "Item")
    etree.SubElement(group, "NameHash").text = "GROUP_STARTUP"
    changes = etree.SubElement(group, "ContentChangeSets")
    etree.SubElement(changes, "Item").text = CHANGESET_NAME

    for group_name in ("GROUP_MAP", "GROUP_MAP_SP"):
        map_group = etree.SubElement(groups, "Item")
        etree.SubElement(map_group, "NameHash").text = group_name
        map_changes = etree.SubElement(map_group, "ContentChangeSets")
        etree.SubElement(map_changes, "Item").text = STREAMING_CHANGESET_NAME

    etree.SubElement(root, "startupScript")
    etree.SubElement(root, "scriptCallstackSize").set("value", "0")
    etree.SubElement(root, "type").text = "EXTRACONTENT_COMPAT_PACK"
    etree.SubElement(root, "order").set("value", "71")
    etree.SubElement(root, "minorOrder").set("value", "0")
    etree.SubElement(root, "isLevelPack").set("value", "false")
    etree.SubElement(root, "dependencyPackHash")
    etree.SubElement(root, "requiredVersion")
    etree.SubElement(root, "subPackCount").set("value", "0")
    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    )


def create_dlc_pack(
    output_dir: Path,
    assets: tuple[MapAsset, ...] | None = None,
) -> Path:
    """Create loose metadata ready for locally extracted map assets."""
    if assets is None:
        assets = MAP_ASSETS
    dlc_root = output_dir / DLC_NAME
    dlc_root.mkdir(parents=True, exist_ok=True)
    (dlc_root / "content.xml").write_bytes(_build_content_xml(assets))
    (dlc_root / "setup2.xml").write_bytes(_build_setup2_xml())
    log.info("Created standalone map staging tree at %s", dlc_root)
    return dlc_root


def validate_staged_assets(
    dlc_root: Path, assets: tuple[MapAsset, ...] | None = None,
) -> list[Path]:
    """Return missing or empty locally extracted files."""
    if assets is None:
        assets = MAP_ASSETS
    return [
        destination
        for asset in assets
        if not (destination := asset.destination(dlc_root)).is_file()
        or destination.stat().st_size == 0
    ]


def deploy_dlc_rpf(dlc_rpf: Path, gta_path: Path) -> Path:
    destination_dir = (
        gta_path / "mods" / "update" / "x64" / "dlcpacks" / DLC_NAME
    )
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "dlc.rpf"
    temporary = destination.with_suffix(".rpf.tmp")
    backup = destination.with_suffix(".rpf.bak")
    try:
        shutil.copy2(dlc_rpf, temporary)
        if destination.exists():
            shutil.copy2(destination, backup)
        temporary.replace(destination)
        (destination_dir / ACTIVE_MARKER).write_text(
            "Generated from this GTA installation and verified by ALLIN1.\n",
            encoding="utf-8",
        )
    except Exception:
        temporary.unlink(missing_ok=True)
        if backup.exists():
            shutil.copy2(backup, destination)
        raise

    old = gta_path / "update" / "x64" / "dlcpacks" / DLC_NAME
    if old.exists():
        shutil.rmtree(old)
    log.info("Deployed standalone map DLC to %s", destination)
    return destination_dir


def remove_dlc_pack(gta_path: Path) -> list[Path]:
    removed: list[Path] = []
    for base in ("mods/update", "update"):
        path = gta_path / base / "x64" / "dlcpacks" / DLC_NAME
        if path.exists():
            shutil.rmtree(path)
            removed.append(path)
    return removed
