"""Build the locally generated ALLIN1 garage-map bridge.

Rockstar's Online map RPFs live behind ``GROUP_MAP`` content changesets.
Switching the whole game to the multiplayer map just to expose one interior
also swaps global Story Mode state and can cause loading screens, missing
furniture, and collision races.

The reference bridge contains metadata only, but Rockstar's registered groups
may still invalidate and replace broad Story world archives.  Receipt creation
therefore preserves their complete contract and a separate zero-flash policy
must approve a group before it can be installed or executed during visible
gameplay.  Historical copied-asset layouts remain here solely for rollback,
canary, and regression tooling until a scoped local pack passes live tests.
"""

from __future__ import annotations

import hashlib
import json
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
# Retained only for the explicit legacy grouped-streaming fallback.  New packs
# define one dormant content changeset per property so the in-game transition
# can request only the archives it is about to use.
STREAMING_CHANGESET_NAME = "ALLIN1_MAPS_STREAMING_MAP"
ACTIVE_MARKER = "allin1_maps.active"
RUNTIME_RECEIPT = "allin1_maps.runtime.json"
# Retained for isolated transaction fixtures and future investigation only.
# Production Install / Repair never selects the startup-registered layout:
# Story Mode crashed after the pool/receipt transaction passed static checks.
STARTUP_IPL_PACK_LAYOUT = "pruned-local-v3-startup-registered-ipl"
DEFERRED_PACK_LAYOUT = "pruned-local-v3-deferred"
LEGACY_PACK_LAYOUT = "pruned-local-v2-legacy-monolithic"
UNREGISTERED_PACK_LAYOUT = "pruned-local-v4-unregistered"
REFERENCE_PACK_LAYOUT = "official-reference-v2-deferred"
# Historical callers without an explicit layout remain fail-closed.  The
# production installer selects REFERENCE_PACK_LAYOUT only after validating
# every official source filename against the installed game.
PACK_LAYOUT = UNREGISTERED_PACK_LAYOUT
SUPPORTED_PACK_LAYOUTS = {
    STARTUP_IPL_PACK_LAYOUT,
    DEFERRED_PACK_LAYOUT,
    LEGACY_PACK_LAYOUT,
    UNREGISTERED_PACK_LAYOUT,
    REFERENCE_PACK_LAYOUT,
}
REFERENCE_GROUP_CONTRACT = "allin1-official-map-groups-v2"
# Rockstar's own DLC map changesets (including MPTUNER_MAP_UPDATE) associate
# streamed interiors with the Story/MP world map, not with the requestable IPL
# name used later as the readiness probe.
STORY_ASSOCIATED_MAP = "MO_JIM_L11"


@dataclass(frozen=True)
class MapChangeSet:
    key: str
    name: str
    group_name: str
    associated_map: str


MAP_CHANGESETS: tuple[MapChangeSet, ...] = (
    MapChangeSet(
        "grapeseed", "ALLIN1_MAPS_GRAPESEED", "ALLIN1_MAP_GRAPESEED",
        STORY_ASSOCIATED_MAP,
    ),
    MapChangeSet(
        "yacht", "ALLIN1_MAPS_YACHT", "ALLIN1_MAP_YACHT",
        STORY_ASSOCIATED_MAP,
    ),
    MapChangeSet(
        "davis", "ALLIN1_MAPS_DAVIS", "ALLIN1_MAP_DAVIS",
        STORY_ASSOCIATED_MAP,
    ),
    MapChangeSet(
        "harmony", "ALLIN1_MAPS_HARMONY", "ALLIN1_MAP_HARMONY",
        STORY_ASSOCIATED_MAP,
    ),
    MapChangeSet(
        "paleto", "ALLIN1_MAPS_PALETO", "ALLIN1_MAP_PALETO",
        STORY_ASSOCIATED_MAP,
    ),
    MapChangeSet(
        "garment_factory", "ALLIN1_MAPS_GARMENT_FACTORY",
        "ALLIN1_MAP_GARMENT_FACTORY", STORY_ASSOCIATED_MAP,
    ),
)
MAP_CHANGESET_BY_KEY = {item.key: item for item in MAP_CHANGESETS}

# Audited against the current Enhanced and Legacy Rockstar DLC metadata.  The
# bridge routes these complete official changesets from its fixed property
# groups; it never recreates a partial filesToEnable list.  Authenticity does
# not imply seamless runtime safety: most of these routes explicitly require a
# loading screen and replace unrelated world data, so production installation
# is blocked by ``validate_zero_flash_reference_groups``.  Case differences in
# Rockstar setup/content XML are accepted, but a renamed or additional route
# requires a new audited contract revision.
OFFICIAL_CHANGESET_ROUTES: dict[str, tuple[tuple[str, str], ...]] = {
    "grapeseed": (("mpheist", "MPHEIST_GTA5_CITYE_HOLLYWOOD_01"),),
    "yacht": (
        ("mpheist", "MPHEIST_PRE_MAP_CHANGES"),
        ("mpheist", "MPHEIST_GTA5_LODLIGHTS"),
        ("mpheist", "MPHEIST_GTA5_HILLS_CITYHILLS_01"),
    ),
    "davis": (("mptuner", "MPTUNER_MAP_UPDATE"),),
    "harmony": (("mpbattle", "MPBATTLE_INTERIOR_ADDITIONS"),),
    "paleto": (("mpvinewood", "mpVinewood_INTERIOR_ADDITIONS"),),
    "garment_factory": (("mp2024_02", "MP2024_02_MAP_UPDATE"),),
}

# Exact device names are read from Rockstar setup2.xml files.  They are not
# inferred from folder names: mpheist notably uses ``dlcMPHeist`` while later
# DLCs use the ``dlc_*`` form.  These devices are registered by the stock game
# before the tiny ALLIN1 bridge is loaded.
ROCKSTAR_DEVICE_BY_PACK = {
    "mpheist": "dlcMPHeist",
    "mptuner": "dlc_mpTuner",
    "mpbattle": "dlc_mpBattle",
    "mpvinewood": "dlc_mpVinewood",
    "mp2024_02": "dlc_mp2024_02",
}


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
    change_set_key: str | None = None

    @property
    def filename(self) -> str:
        path = self.destination_path.replace("x64/", "%PLATFORM%/", 1)
        return f"{DEVICE_NAME}:/{path}"

    @property
    def source_filename(self) -> str:
        """Return the exact globally registered Rockstar data-file name."""
        try:
            device = ROCKSTAR_DEVICE_BY_PACK[self.source_pack]
        except KeyError as exc:
            raise ValueError(
                f"No verified Rockstar device for {self.source_pack}"
            ) from exc
        path = self.source_path.replace("x64/", "%PLATFORM%/", 1)
        return f"{device}:/{path}"

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
    *, change_set_key: str, map_data: bool = False,
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
        contents=contents, change_set_key=change_set_key,
    )


# Entries copied locally from the user's installed Rockstar DLC archives.
# Keep these grouped by feature so future garages can be added deliberately.
MAP_ASSETS: tuple[MapAsset, ...] = (
    # Shared High Life six-car shell used by the Grapeseed Garage, plus the
    # heist yacht shell/interior used by the fixed Super Yacht world asset.
    _rpf(
        "mpheist", "x64/levels/gta5/interiors/dlc_garage_high_new.rpf",
        change_set_key="grapeseed",
    ),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_citye/hollywood_01/hw1_blimp.rpf",
        change_set_key="grapeseed",
    ),
    # The six-car shell's requestable placement is not stored in the tiny
    # hw1_blimp.rpf drawable archive above. Rockstar keeps
    # hei_hw1_blimp_interior_v_garagem_milo_.ymap in the area's metadata RPF;
    # without this archive REQUEST_IPL cannot resolve the Grapeseed interior
    # from the standalone pack.
    _rpf(
        "mpheist",
        "x64/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
        change_set_key="grapeseed",
        map_data=True,
    ),
    _rpf(
        "mpheist", "x64/levels/gta5/interiors/mpheist_yacht.rpf",
        change_set_key="yacht",
    ),
    _rpf(
        "mpheist", "x64/levels/gta5/_hills/cityhills_01/ch1_yacht.rpf",
        change_set_key="yacht",
    ),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_hills/cityhills_01/ch1_yacht_lod.rpf",
        change_set_key="yacht",
    ),
    _rpf(
        "mpheist", "x64/levels/gta5/_hills/cityhills_01/yacht.rpf",
        change_set_key="yacht",
    ),
    _rpf(
        "mpheist",
        "x64/levels/gta5/_hills/cityhills_01/yacht_metadata.rpf",
        change_set_key="yacht",
    ),
    # The yacht's distant and LOD light IPLs are registered from mpheist's
    # top-level LODLights archive rather than either yacht placement archive.
    # Keep it in the same property-scoped group so night lighting is available
    # without enabling the rest of Rockstar's Online map group.
    _rpf(
        "mpheist", "x64/levels/gta5/LODLights.rpf",
        change_set_key="yacht",
    ),
    # Los Santos Tuners Auto Shop used by the Davis garage.  The other Tuners
    # interiors are unrelated car-meet and meth-lab content and must not be
    # mounted just because they share the same Rockstar DLC.
    _rpf(
        "mptuner", "x64/levels/gta5/interiors/dlc_int_01_tr.rpf",
        change_set_key="davis",
    ),
    _rpf(
        "mptuner", "x64/levels/gta5/interiors/int_placement_tr.rpf",
        change_set_key="davis",
    ),

    # After Hours nightclub garage used by the five-floor Harmony Garage.
    *tuple(
        _rpf(
            "mpbattle", f"x64/levels/gta5/interiors/{name}.rpf",
            source_archive_name="dlc1.rpf",
            change_set_key="harmony",
            # The nightclub's floor and detail variations are MLO entity
            # sets, not ordinary streamed props. A generic RPF mount can
            # expose the bare shell while leaving those sets inert. Keep the
            # exact garage and its placement archive in the map-data mount
            # used by the proven local probe.
            map_data=True,
        )
        for name in ("int_02_ba", "int_placement_ba")
    ),

    # Diamond Casino garage used by the Paleto Bay Garage.  Main-casino,
    # penthouse, and carpark siblings are deliberately excluded.
    _rpf(
        "mpvinewood", "x64/levels/gta5/interiors/vwdlc_int_03.rpf",
        change_set_key="paleto",
    ),
    _rpf(
        "mpvinewood", "x64/levels/gta5/interiors/int_placement_vw.rpf",
        change_set_key="paleto",
    ),

    # Agents of Sabotage garment-factory garage.  The basement and office
    # sibling interiors are not used by ALLIN1.
    _rpf(
        "mp2024_02", "x64/levels/gta5/interiors/int_03.rpf",
        change_set_key="garment_factory",
    ),
    _rpf(
        "mp2024_02", "x64/levels/gta5/interiors/int_placement.rpf",
        change_set_key="garment_factory",
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
    *, layout: str = PACK_LAYOUT,
) -> bytes:
    if assets is None:
        assets = MAP_ASSETS
    if layout not in SUPPORTED_PACK_LAYOUTS:
        raise ValueError(f"Unsupported standalone-map layout: {layout}")
    root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
    etree.SubElement(root, "disabledFiles")
    etree.SubElement(root, "includedXmlFiles")
    etree.SubElement(root, "includedDataFiles")

    data_files = etree.SubElement(root, "dataFiles")
    for entry in assets:
        if layout == REFERENCE_PACK_LAYOUT:
            continue
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
        # Enhanced's production layout registers the copied archive devices
        # once at startup, but does not execute a map changeset.  REQUEST_IPL
        # later controls which world content becomes active.  Legacy and the
        # experimental deferred layout keep RPFs out of this base changeset.
        if (
            entry.file_type == "RPF_FILE"
            and layout != STARTUP_IPL_PACK_LAYOUT
        ):
            continue
        etree.SubElement(enabled, "Item").text = entry.filename
    etree.SubElement(change, "txdToLoad")
    etree.SubElement(change, "txdToUnload")
    etree.SubElement(change, "residentResources")
    etree.SubElement(change, "unregisterResources")
    etree.SubElement(change, "requiresLoadingScreen").set("value", "false")

    map_assets = tuple(
        entry for entry in assets if entry.file_type == "RPF_FILE"
    )
    unknown_keys = sorted({
        entry.change_set_key for entry in map_assets
        if entry.change_set_key not in MAP_CHANGESET_BY_KEY
    }, key=lambda value: "" if value is None else value)
    if unknown_keys:
        labels = ["<missing>" if key is None else key for key in unknown_keys]
        raise ValueError(
            "Every map RPF must belong to a known deferred changeset: "
            + ", ".join(labels)
        )

    def append_map_change_set(
        name: str, associated_map: str,
        scoped_assets: tuple[MapAsset, ...], *, legacy: bool,
    ) -> None:
        streaming = etree.SubElement(change_sets, "Item")
        etree.SubElement(streaming, "changeSetName").text = name
        map_data = etree.SubElement(streaming, "mapChangeSetData")
        map_item = etree.SubElement(map_data, "Item")
        etree.SubElement(map_item, "associatedMap").text = associated_map
        etree.SubElement(map_item, "filesToInvalidate")
        etree.SubElement(map_item, "filesToDisable")
        map_enabled = etree.SubElement(map_item, "filesToEnable")
        for entry in scoped_assets:
            filename = (
                entry.source_filename
                if layout == REFERENCE_PACK_LAYOUT
                else entry.filename
            )
            etree.SubElement(map_enabled, "Item").text = filename
        etree.SubElement(map_item, "txdToLoad")
        etree.SubElement(map_item, "txdToUnload")
        etree.SubElement(map_item, "residentResources")
        etree.SubElement(map_item, "unregisterResources")
        etree.SubElement(streaming, "requiresLoadingScreen").set(
            "value", str(legacy).lower()
        )
        if legacy:
            etree.SubElement(streaming, "loadingScreenContext").text = (
                "LOADINGSCREEN_CONTEXT_LAST_FRAME"
            )
        # No generated cache file accompanies this pack.  Explicitly disable
        # the cache loader for deferred changesets rather than making GTA look
        # for a nonexistent cache during every property transition.
        etree.SubElement(streaming, "useCacheLoader").set(
            "value", str(legacy).lower()
        )

    if layout == LEGACY_PACK_LAYOUT:
        append_map_change_set(
            STREAMING_CHANGESET_NAME, "MO_JIM_L11", map_assets,
            legacy=True,
        )
    elif layout in {
        DEFERRED_PACK_LAYOUT,
        UNREGISTERED_PACK_LAYOUT,
        REFERENCE_PACK_LAYOUT,
    }:
        for definition in MAP_CHANGESETS:
            scoped_assets = tuple(
                entry for entry in map_assets
                if entry.change_set_key == definition.key
            )
            if scoped_assets:
                append_map_change_set(
                    definition.name, definition.associated_map,
                    scoped_assets, legacy=False,
                )

    etree.SubElement(root, "patchFiles")
    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    )


def _build_setup2_xml(
    assets: tuple[MapAsset, ...] | None = None,
    *, layout: str = PACK_LAYOUT,
) -> bytes:
    if assets is None:
        assets = MAP_ASSETS
    if layout not in SUPPORTED_PACK_LAYOUTS:
        raise ValueError(f"Unsupported standalone-map layout: {layout}")
    root = etree.Element("SSetupData")
    etree.SubElement(root, "deviceName").text = DEVICE_NAME
    etree.SubElement(root, "datFile").text = "content.xml"
    etree.SubElement(root, "timeStamp").text = "08/14/2026 00:00:00"
    etree.SubElement(root, "nameHash").text = DLC_NAME
    etree.SubElement(root, "contentChangeSets")

    groups = etree.SubElement(root, "contentChangeSetGroups")
    # An unregistered archive is intentionally useful only as a staged,
    # inspectable artifact.  Do not even bind its base changeset to
    # GROUP_STARTUP: that keeps an accidentally re-added dlclist entry inert.
    if layout != UNREGISTERED_PACK_LAYOUT:
        group = etree.SubElement(groups, "Item")
        etree.SubElement(group, "NameHash").text = "GROUP_STARTUP"
        changes = etree.SubElement(group, "ContentChangeSets")
        etree.SubElement(changes, "Item").text = CHANGESET_NAME

    if layout == LEGACY_PACK_LAYOUT:
        has_map_assets = any(
            asset.file_type == "RPF_FILE" for asset in assets
        )
        deferred_groups = (
            (
                ("GROUP_MAP", STREAMING_CHANGESET_NAME),
                ("GROUP_MAP_SP", STREAMING_CHANGESET_NAME),
            ) if has_map_assets else ()
        )
    elif layout in {
        DEFERRED_PACK_LAYOUT,
        UNREGISTERED_PACK_LAYOUT,
        REFERENCE_PACK_LAYOUT,
    }:
        # Custom groups are inert until explicitly requested.  In particular,
        # none of these changesets participates in GROUP_MAP or GROUP_MAP_SP,
        # which prevents every copied interior archive from mounting while the
        # Story world is still booting.
        deferred_groups = tuple(
            (definition.group_name, definition.name)
            for definition in MAP_CHANGESETS
            if any(
                asset.file_type == "RPF_FILE"
                and asset.change_set_key == definition.key
                for asset in assets
            )
        )
    else:
        # The startup-registered/IPL-managed layout needs no map group.  The
        # base GROUP_STARTUP changeset only registers archive files; in-game
        # REQUEST_IPL/REMOVE_IPL calls own actual world-content lifetime.
        deferred_groups = ()

    for group_name, change_set_name in deferred_groups:
        map_group = etree.SubElement(groups, "Item")
        etree.SubElement(map_group, "NameHash").text = group_name
        map_changes = etree.SubElement(map_group, "ContentChangeSets")
        etree.SubElement(map_changes, "Item").text = change_set_name

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
    *, layout: str = PACK_LAYOUT,
) -> Path:
    """Create loose metadata ready for locally extracted map assets."""
    if assets is None:
        assets = MAP_ASSETS
    dlc_root = output_dir / DLC_NAME
    dlc_root.mkdir(parents=True, exist_ok=True)
    (dlc_root / "content.xml").write_bytes(_build_content_xml(
        assets, layout=layout,
    ))
    (dlc_root / "setup2.xml").write_bytes(_build_setup2_xml(
        assets, layout=layout,
    ))
    log.info("Created standalone map staging tree at %s", dlc_root)
    return dlc_root


def _changeset_index(
    content: etree._ElementTree, *, pack: str,
) -> dict[str, tuple[str, etree._Element]]:
    """Index Rockstar changesets without trusting inconsistent case."""
    result: dict[str, tuple[str, etree._Element]] = {}
    for item in content.xpath("//contentChangeSets/Item[changeSetName]"):
        name = item.xpath("string(changeSetName)").strip()
        folded = name.casefold()
        if not folded:
            continue
        if folded in result:
            raise ValueError(
                f"{pack} has case-colliding content changesets for {name}"
            )
        result[folded] = (name, item)
    return result


def _official_reference_closure(
    metadata: dict[str, tuple[Path, Path]],
    assets: tuple[MapAsset, ...],
) -> dict[str, list[tuple[str, str, etree._Element]]]:
    """Resolve full Rockstar-defined changesets covering each property.

    Selecting only the two visibly relevant RPFs drops hidden collision,
    metadata, invalidation, cache-loader, and loading-screen semantics.  The
    bridge therefore clones the smallest set of complete official GROUP_MAP
    changesets that covers every required target RPF.  Runtime still activates
    only one ALLIN1 property group at a time.
    """
    parsed: dict[
        str,
        tuple[etree._ElementTree, etree._ElementTree,
              dict[str, tuple[str, etree._Element]], list[str]],
    ] = {}
    for pack, paths in metadata.items():
        try:
            content = etree.parse(str(paths[0]))
            setup = etree.parse(str(paths[1]))
        except (OSError, etree.XMLSyntaxError) as exc:
            raise ValueError(
                f"invalid Rockstar metadata for {pack}: {exc}"
            ) from exc
        index = _changeset_index(content, pack=pack)
        group_names = [
            (value or "").strip()
            for value in setup.xpath(
                "//contentChangeSetGroups/Item[NameHash='GROUP_MAP']/"
                "ContentChangeSets/Item/text()"
            )
            if (value or "").strip()
        ]
        if not group_names:
            raise ValueError(f"{pack} has no registered GROUP_MAP changeset")
        for name in group_names:
            if name.casefold() not in index:
                raise ValueError(
                    f"{pack} GROUP_MAP references missing changeset {name}"
                )
        parsed[pack] = (content, setup, index, group_names)

    closure: dict[str, list[tuple[str, str, etree._Element]]] = {}
    for definition in MAP_CHANGESETS:
        property_assets = [
            asset for asset in assets
            if asset.file_type == "RPF_FILE"
            and asset.change_set_key == definition.key
        ]
        if not property_assets:
            continue
        resolved: list[tuple[str, str, etree._Element]] = []
        packs = list(dict.fromkeys(asset.source_pack for asset in property_assets))
        for pack in packs:
            if pack not in parsed:
                raise ValueError(f"missing extracted Rockstar metadata for {pack}")
            _content, _setup, index, group_names = parsed[pack]
            targets = {
                asset.source_filename for asset in property_assets
                if asset.source_pack == pack
            }
            covered: set[str] = set()
            for group_name in group_names:
                official_name, item = index[group_name.casefold()]
                enabled = set(item.xpath(
                    "mapChangeSetData/Item/filesToEnable/Item/text()"
                ))
                if not targets.intersection(enabled):
                    continue
                resolved.append((pack, official_name, item))
                covered.update(targets.intersection(enabled))
            missing = sorted(targets - covered)
            if missing:
                raise ValueError(
                    f"{pack} GROUP_MAP does not cover required {definition.key} "
                    "resources: " + ", ".join(missing)
                )
        closure[definition.key] = resolved
    return closure


def create_reference_dlc_pack(
    output_dir: Path,
    metadata: dict[str, tuple[Path, Path]],
    assets: tuple[MapAsset, ...] | None = None,
) -> Path:
    """Create the production zero-payload bridge from official closures."""
    if assets is None:
        assets = MAP_ASSETS
    valid, detail = validate_reference_source_metadata(metadata, assets)
    if not valid:
        raise ValueError(detail)
    closure = _official_reference_closure(metadata, assets)

    content = etree.ElementTree(etree.fromstring(_build_content_xml(
        assets, layout=REFERENCE_PACK_LAYOUT,
    )))
    setup = etree.ElementTree(etree.fromstring(_build_setup2_xml(
        assets, layout=REFERENCE_PACK_LAYOUT,
    )))
    content_sets = content.xpath(
        "/CDataFileMgr__ContentsOfDataFileXml/contentChangeSets"
    )[0]
    existing = list(content_sets.findall("Item"))
    for item in existing[1:]:
        content_sets.remove(item)

    for definition in MAP_CHANGESETS:
        sources = closure.get(definition.key, [])
        group_changes = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash=$group]/"
            "ContentChangeSets",
            group=definition.group_name,
        )
        if len(group_changes) != 1 or not sources:
            raise ValueError(
                f"No complete official map closure for {definition.key}"
            )
        changes_node = group_changes[0]
        for child in list(changes_node):
            changes_node.remove(child)
        seen: set[tuple[str, str]] = set()
        for pack, official_name, _source_item in sources:
            identity = (pack.casefold(), official_name.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            # Content changesets are registered globally by Rockstar's DLC
            # metadata. Referencing the original name preserves its complete
            # invalidation/cache/loading contract, including any future GTA
            # update to that official changeset. The ALLIN1 group itself is
            # the only new runtime unit.
            etree.SubElement(changes_node, "Item").text = official_name

    dlc_root = output_dir / DLC_NAME
    dlc_root.mkdir(parents=True, exist_ok=True)
    content.write(
        str(dlc_root / "content.xml"), pretty_print=True,
        xml_declaration=True, encoding="UTF-8",
    )
    setup.write(
        str(dlc_root / "setup2.xml"), pretty_print=True,
        xml_declaration=True, encoding="UTF-8",
    )
    valid, detail = validate_reference_pack_against_source_metadata(
        dlc_root, metadata, assets,
    )
    if not valid:
        raise ValueError(detail)
    log.info("Created official-closure map bridge at %s", dlc_root)
    return dlc_root


def validate_reference_pack_metadata(
    dlc_root: Path,
    assets: tuple[MapAsset, ...] | None = None,
) -> tuple[bool, str]:
    """Validate the zero-payload, per-property bridge contract.

    This is deliberately independent of a built RPF.  Install/Repair runs it
    both before and after packaging (after extracting the generated XML) so a
    malformed bridge can never be registered in ``dlclist.xml``.
    """
    if assets is None:
        assets = MAP_ASSETS
    try:
        content = etree.parse(str(dlc_root / "content.xml"))
        setup = etree.parse(str(dlc_root / "setup2.xml"))
    except (OSError, etree.XMLSyntaxError) as exc:
        return False, f"bridge metadata is unreadable: {exc}"

    data_files = content.xpath("//dataFiles/Item")
    if data_files:
        return False, "reference bridge must contain zero data-file payloads"

    groups = setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    )
    expected_groups = [
        "GROUP_STARTUP",
        *[
            definition.group_name
            for definition in MAP_CHANGESETS
            if any(
                asset.file_type == "RPF_FILE"
                and asset.change_set_key == definition.key
                for asset in assets
            )
        ],
    ]
    if groups != expected_groups:
        return False, "reference bridge groups do not match the fixed contract"
    if "GROUP_MAP" in groups or "GROUP_MAP_SP" in groups:
        return False, "reference bridge must not bind a global map group"

    content_index: dict[str, etree._Element] = {}
    for item in content.xpath("//contentChangeSets/Item[changeSetName]"):
        name = item.xpath("string(changeSetName)").strip()
        folded = name.casefold()
        if not folded or folded in content_index:
            return False, "reference bridge has duplicate or empty changesets"
        content_index[folded] = item
    if set(content_index) != {CHANGESET_NAME.casefold()}:
        return False, (
            "reference bridge must not clone or redefine Rockstar changesets"
        )
    for definition in MAP_CHANGESETS:
        names = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash=$group]/"
            "ContentChangeSets/Item/text()",
            group=definition.group_name,
        )
        if not names:
            return False, f"reference bridge has no closure for {definition.key}"
        seen_names: set[str] = set()
        for name in names:
            folded = (name or "").strip().casefold()
            if not folded or folded == CHANGESET_NAME.casefold():
                return False, (
                    f"reference bridge {definition.key} has an invalid route"
                )
            if folded in seen_names:
                return False, (
                    f"reference bridge {definition.key} repeats a changeset"
                )
            seen_names.add(folded)
    return True, "verified metadata-only official-changeset bridge"


def validate_reference_pack_against_source_metadata(
    dlc_root: Path,
    metadata: dict[str, tuple[Path, Path]],
    assets: tuple[MapAsset, ...] | None = None,
) -> tuple[bool, str]:
    """Prove each fixed bridge group routes the full official closure."""
    if assets is None:
        assets = MAP_ASSETS
    valid, detail = validate_reference_pack_metadata(dlc_root, assets)
    if not valid:
        return valid, detail
    try:
        closure = _official_reference_closure(metadata, assets)
        setup = etree.parse(str(dlc_root / "setup2.xml"))
    except (OSError, etree.XMLSyntaxError, ValueError) as exc:
        return False, f"reference closure validation failed: {exc}"
    for definition in MAP_CHANGESETS:
        expected: list[str] = []
        seen: set[tuple[str, str]] = set()
        for pack, official_name, _item in closure.get(definition.key, []):
            identity = (pack.casefold(), official_name.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            expected.append(official_name)
        actual = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash=$group]/"
            "ContentChangeSets/Item/text()",
            group=definition.group_name,
        )
        if [value.casefold() for value in actual] != [
            value.casefold() for value in expected
        ]:
            return False, (
                f"reference bridge {definition.key} does not route its full "
                "official GROUP_MAP closure"
            )
        audited = OFFICIAL_CHANGESET_ROUTES.get(definition.key, ())
        actual_routes = tuple(
            (pack.casefold(), name.casefold())
            for pack, name, _item in closure.get(definition.key, [])
        )
        audited_routes = tuple(
            (pack.casefold(), name.casefold()) for pack, name in audited
        )
        if actual_routes != audited_routes:
            return False, (
                f"reference bridge {definition.key} official route changed; "
                "an audited contract update is required"
            )
    return True, "verified against complete official GROUP_MAP closures"


def validate_reference_source_metadata(
    metadata: dict[str, tuple[Path, Path]],
    assets: tuple[MapAsset, ...] | None = None,
) -> tuple[bool, str]:
    """Prove bridge references against this installation's Rockstar XML.

    ``metadata`` maps a DLC pack folder to extracted ``(content.xml,
    setup2.xml)`` files.  The check intentionally requires each referenced
    RPF to be a disabled, registered Rockstar data file and a member of that
    pack's real ``GROUP_MAP`` changeset.  A guessed device/path can therefore
    never reach the installed bridge merely because it looks plausible.
    """
    if assets is None:
        assets = MAP_ASSETS
    grouped: dict[str, list[MapAsset]] = {}
    for asset in assets:
        if asset.file_type == "RPF_FILE":
            grouped.setdefault(asset.source_pack, []).append(asset)

    for pack, pack_assets in grouped.items():
        paths = metadata.get(pack)
        if paths is None:
            return False, f"missing extracted Rockstar metadata for {pack}"
        try:
            content = etree.parse(str(paths[0]))
            setup = etree.parse(str(paths[1]))
        except (OSError, etree.XMLSyntaxError) as exc:
            return False, f"invalid Rockstar metadata for {pack}: {exc}"

        expected_device = ROCKSTAR_DEVICE_BY_PACK.get(pack)
        actual_device = setup.xpath("string(/SSetupData/deviceName)").strip()
        # Rockstar's setup2.xml capitalization is not consistent across
        # editions (mp2024_02 is observed as dlc_MP2024_02 in Enhanced), while
        # content.xml filenames use the lowercase device spelling. Validate
        # the setup identity case-insensitively, but retain the exact verified
        # content prefix when building bridge references.
        if actual_device.casefold() != (expected_device or "").casefold():
            return False, (
                f"{pack} device is {actual_device!r}, expected "
                f"{expected_device!r}"
            )

        map_changesets = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash='GROUP_MAP']/"
            "ContentChangeSets/Item/text()"
        )
        if not map_changesets:
            return False, f"{pack} has no registered GROUP_MAP changeset"
        content_changesets: dict[str, etree._Element] = {}
        for item in content.xpath("//contentChangeSets/Item[changeSetName]"):
            name = item.xpath("string(changeSetName)").strip()
            folded = name.casefold()
            if not folded:
                continue
            if folded in content_changesets:
                return False, (
                    f"{pack} has case-colliding content changesets for {name}"
                )
            content_changesets[folded] = item
        startup_changesets = setup.xpath(
            "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
            "ContentChangeSets/Item/text()"
        )
        if not startup_changesets:
            return False, f"{pack} has no registered GROUP_STARTUP changeset"
        startup_enabled: set[str] = set()
        for change_set_name in startup_changesets:
            change = content_changesets.get(change_set_name.strip().casefold())
            if change is None:
                return False, (
                    f"{pack} GROUP_STARTUP references missing changeset "
                    f"{change_set_name}"
                )
            startup_enabled.update(change.xpath("filesToEnable/Item/text()"))

        entries = {
            item.xpath("string(filename)").strip(): item
            for item in content.xpath("//dataFiles/Item")
        }
        proxies = [
            filename for filename, item in entries.items()
            if filename.casefold().endswith("/common/data/interiorproxies.meta")
            and item.xpath("string(fileType)").strip() ==
                "INTERIOR_PROXY_ORDER_FILE"
        ]
        if len(proxies) != 1:
            return False, (
                f"{pack} does not register one interior proxy order file"
            )
        proxy = proxies[0]
        if entries[proxy].xpath(
                "string(disabled/@value)").strip().casefold() != "true":
            return False, f"{pack} interior proxy file is not deferred"
        if proxy not in startup_enabled:
            return False, (
                f"{pack} GROUP_STARTUP does not enable {proxy}"
            )
        enabled_by_map: set[str] = set()
        for change_set_name in map_changesets:
            change = content_changesets.get(change_set_name.strip().casefold())
            if change is None:
                return False, (
                    f"{pack} GROUP_MAP references missing changeset "
                    f"{change_set_name}"
                )
            enabled_by_map.update(change.xpath(
                "mapChangeSetData/Item/filesToEnable/Item/text()"
            ))

        for asset in pack_assets:
            filename = asset.source_filename
            item = entries.get(filename)
            if item is None:
                return False, f"{pack} does not register {filename}"
            if item.xpath("string(fileType)").strip() != "RPF_FILE":
                return False, f"{filename} is not registered as RPF_FILE"
            disabled = item.xpath("string(disabled/@value)").strip().lower()
            if disabled != "true":
                return False, f"{filename} is not a deferred Rockstar RPF"
            if filename not in enabled_by_map:
                return False, (
                    f"{filename} is not enabled by {pack}'s GROUP_MAP data"
                )

    # Runtime routes complete official changesets, not merely the 17 target
    # RPFs. Prove every enabled archive in those closures is itself a deferred,
    # registered Rockstar data file before the bridge can be built.
    try:
        closure = _official_reference_closure(metadata, assets)
    except ValueError as exc:
        return False, str(exc)
    entries_by_pack: dict[str, dict[str, etree._Element]] = {}
    for pack, paths in metadata.items():
        try:
            content = etree.parse(str(paths[0]))
        except (OSError, etree.XMLSyntaxError) as exc:
            return False, f"invalid Rockstar metadata for {pack}: {exc}"
        entries_by_pack[pack] = {
            item.xpath("string(filename)").strip(): item
            for item in content.xpath("//dataFiles/Item")
        }
    for routes in closure.values():
        for pack, name, change in routes:
            entries = entries_by_pack[pack]
            for filename in change.xpath(
                "mapChangeSetData/Item/filesToEnable/Item/text()"
            ):
                item = entries.get(filename)
                if item is None:
                    return False, (
                        f"{pack} official changeset {name} enables an "
                        f"unregistered file: {filename}"
                    )
                if item.xpath("string(fileType)").strip() != "RPF_FILE" or \
                        item.xpath("string(disabled/@value)").strip().casefold() \
                        != "true":
                    return False, (
                        f"{pack} official changeset {name} enables a file "
                        f"outside the deferred RPF contract: {filename}"
                    )

    return True, "verified against installed Rockstar content metadata"


def reference_group_receipt(
    metadata: dict[str, tuple[Path, Path]],
    assets: tuple[MapAsset, ...] | None = None,
) -> list[dict[str, object]]:
    """Describe the actual official changesets routed by the bridge."""
    if assets is None:
        assets = MAP_ASSETS
    closure = _official_reference_closure(metadata, assets)

    def values(item: etree._Element, path: str) -> list[str]:
        return [
            value.strip() for value in item.xpath(path)
            if isinstance(value, str) and value.strip()
        ]

    def flag(item: etree._Element, name: str) -> bool:
        return item.xpath(f"string({name}/@value)").strip().casefold() == "true"

    result: list[dict[str, object]] = []
    for definition in MAP_CHANGESETS:
        routes = []
        seen: set[tuple[str, str]] = set()
        for pack, official_name, item in closure.get(definition.key, []):
            identity = (pack.casefold(), official_name.casefold())
            if identity in seen:
                continue
            seen.add(identity)
            routes.append({
                "pack": pack,
                "changeset": official_name,
                "associated_maps": values(
                    item, "mapChangeSetData/Item/associatedMap/text()",
                ),
                "files_to_invalidate": values(
                    item,
                    "mapChangeSetData/Item/filesToInvalidate/Item/text()",
                ),
                "files_to_disable": values(
                    item,
                    "mapChangeSetData/Item/filesToDisable/Item/text()",
                ),
                "files_to_enable": values(
                    item, "mapChangeSetData/Item/filesToEnable/Item/text()",
                ),
                "requires_loading_screen": flag(
                    item, "requiresLoadingScreen",
                ),
                "loading_screen_context": item.xpath(
                    "string(loadingScreenContext)"
                ).strip(),
                "use_cache_loader": flag(item, "useCacheLoader"),
            })
        result.append({
            "property": definition.key,
            "group": definition.group_name,
            "references": [
                asset.source_filename for asset in assets
                if asset.file_type == "RPF_FILE"
                and asset.change_set_key == definition.key
            ],
            "routes": routes,
        })
    return result


def validate_reference_group_receipt(
    groups: object,
    assets: tuple[MapAsset, ...] | None = None,
) -> tuple[bool, str]:
    """Validate a receipt against the fixed routes and target references."""
    if assets is None:
        assets = MAP_ASSETS
    if not isinstance(groups, list) or len(groups) != len(MAP_CHANGESETS):
        return False, "bridge group receipt count does not match"
    for index, definition in enumerate(MAP_CHANGESETS):
        item = groups[index]
        if not isinstance(item, dict):
            return False, "bridge group receipt item is malformed"
        if item.get("property") != definition.key or \
                item.get("group") != definition.group_name:
            return False, "bridge group receipt identity does not match"
        expected_refs = [
            asset.source_filename for asset in assets
            if asset.file_type == "RPF_FILE"
            and asset.change_set_key == definition.key
        ]
        if item.get("references") != expected_refs:
            return False, (
                f"bridge {definition.key} target references do not match"
            )
        routes = item.get("routes")
        expected_routes = OFFICIAL_CHANGESET_ROUTES.get(definition.key, ())
        if not isinstance(routes, list) or len(routes) != len(expected_routes):
            return False, f"bridge {definition.key} route count does not match"
        enabled: list[str] = []
        for route, (expected_pack, expected_name) in zip(
            routes, expected_routes,
        ):
            if not isinstance(route, dict):
                return False, f"bridge {definition.key} route is malformed"
            pack = route.get("pack")
            name = route.get("changeset")
            if not isinstance(pack, str) or not isinstance(name, str) or \
                    pack.casefold() != expected_pack.casefold() or \
                    name.casefold() != expected_name.casefold():
                return False, f"bridge {definition.key} route changed"
            for field in (
                "associated_maps", "files_to_invalidate",
                "files_to_disable", "files_to_enable",
            ):
                values = route.get(field)
                if not isinstance(values, list) or not all(
                    isinstance(value, str) and value.strip()
                    for value in values
                ):
                    return False, (
                        f"bridge {definition.key} route {field} is malformed"
                    )
            if not isinstance(route.get("requires_loading_screen"), bool) or \
                    not isinstance(route.get("use_cache_loader"), bool) or \
                    not isinstance(route.get("loading_screen_context"), str):
                return False, (
                    f"bridge {definition.key} route flags are malformed"
                )
            enabled.extend(route["files_to_enable"])
        missing = sorted(set(expected_refs) - set(enabled))
        if missing:
            return False, (
                f"bridge {definition.key} official closure omits targets: "
                + ", ".join(missing)
            )
    return True, "verified"


def validate_zero_flash_reference_groups(
    groups: object,
) -> tuple[bool, str]:
    """Reject official map routes that can visibly replace the Story world.

    A reference bridge is only suitable for an in-world, on-demand transition
    when the referenced Rockstar changesets are themselves property-scoped.
    ``requiresLoadingScreen`` and cache-loader routes explicitly do not meet
    that contract.  Invalidating/disabling registered world files, or enabling
    resources beyond the property's audited references, is equally unsafe:
    those operations can expose a partially replaced world for one or more
    frames even when GTA happens not to display its loading screen.

    The check is deliberately separate from structural receipt validation.
    A receipt can be authentic and complete while accurately describing a
    route that is unsuitable for seamless Story Mode use.
    """
    valid, detail = validate_reference_group_receipt(groups)
    if not valid:
        return False, detail
    assert isinstance(groups, list)

    for group in groups:
        assert isinstance(group, dict)
        property_name = str(group["property"])
        references = {
            str(value).casefold() for value in group["references"]
        }
        enabled: set[str] = set()
        routes = group["routes"]
        assert isinstance(routes, list)
        for route in routes:
            assert isinstance(route, dict)
            route_name = str(route["changeset"])
            if route["requires_loading_screen"]:
                return False, (
                    f"{property_name}/{route_name} requires a loading screen"
                )
            if str(route["loading_screen_context"]).strip():
                return False, (
                    f"{property_name}/{route_name} declares a loading-screen "
                    "context"
                )
            if route["use_cache_loader"]:
                return False, (
                    f"{property_name}/{route_name} requires the map cache loader"
                )
            if route["files_to_invalidate"]:
                return False, (
                    f"{property_name}/{route_name} invalidates Story world files"
                )
            if route["files_to_disable"]:
                return False, (
                    f"{property_name}/{route_name} disables Story world files"
                )
            enabled.update(
                str(value).casefold() for value in route["files_to_enable"]
            )
        unexpected = sorted(enabled - references)
        if unexpected:
            return False, (
                f"{property_name} enables {len(unexpected)} unrelated map "
                "resource(s)"
            )
        missing = sorted(references - enabled)
        if missing:
            return False, (
                f"{property_name} omits {len(missing)} required map resource(s)"
            )
    return True, "verified zero-flash property scope"


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


def deploy_dlc_rpf(
    dlc_rpf: Path,
    gta_path: Path,
    *,
    layout: str = PACK_LAYOUT,
    asset_count: int | None = None,
    reference_count: int | None = None,
) -> Path:
    """Deploy a verified map pack and record its actual activation contract.

    ``layout`` is deliberately supplied by the caller that selected the pack
    topology.  A deferred pack and a legacy GROUP_MAP pack have materially
    different startup and runtime behavior, so presenting either one as the
    other would make the in-game safety gate unreliable.
    """
    if layout not in SUPPORTED_PACK_LAYOUTS:
        raise ValueError(f"Unsupported standalone-map layout: {layout}")
    if asset_count is None:
        asset_count = len(MAP_ASSETS)
    if asset_count < 0:
        raise ValueError("asset_count must be non-negative")
    if reference_count is None:
        reference_count = 0
    if reference_count < 0:
        raise ValueError("reference_count must be non-negative")

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
        if layout == REFERENCE_PACK_LAYOUT:
            activation = "property-group-runtime"
            archive_registration = "metadata-bridge"
        elif layout == UNREGISTERED_PACK_LAYOUT:
            activation = "disabled-for-startup-safety"
            archive_registration = "disabled"
        elif layout == LEGACY_PACK_LAYOUT:
            activation = "story-map-groups"
            archive_registration = "group-map"
        elif layout == DEFERRED_PACK_LAYOUT:
            activation = "property-group-native-host-required"
            archive_registration = "property-groups"
        else:
            activation = "startup-file-registration-plus-request-ipl"
            archive_registration = "startup"
        (destination_dir / ACTIVE_MARKER).write_text(
            "Generated from this GTA installation and verified by ALLIN1.\n"
            f"layout={layout}\n"
            f"archive_registration={archive_registration}\n"
            f"group_map_binding={str(layout == LEGACY_PACK_LAYOUT).lower()}\n"
            f"activation={activation}\n"
            f"asset_count={asset_count}\n"
            f"reference_count={reference_count}\n"
            f"group_contract={REFERENCE_GROUP_CONTRACT}\n"
            f"archive_bytes={destination.stat().st_size}\n",
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


def validate_reference_bridge_receipt(
    pack_root: Path,
    *,
    edition: str,
    gta_path: Path | None = None,
) -> tuple[bool, str, dict[str, object] | None]:
    """Validate the production metadata bridge and its compact receipt."""
    marker_path = pack_root / ACTIVE_MARKER
    receipt_path = pack_root / RUNTIME_RECEIPT
    archive_path = pack_root / "dlc.rpf"
    if not archive_path.is_file() or archive_path.stat().st_size <= 0:
        return False, "bridge archive is missing or empty", None
    try:
        marker = {
            key.strip().lower(): value.strip()
            for raw in marker_path.read_text(
                encoding="utf-8", errors="strict",
            ).splitlines()
            if "=" in raw
            for key, value in [raw.split("=", 1)]
            if key.strip()
        }
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, f"bridge marker or receipt is unreadable: {exc}", None
    if not isinstance(receipt, dict):
        return False, "bridge receipt is not a JSON object", None

    expected = {
        "layout": REFERENCE_PACK_LAYOUT,
        "archive_registration": "metadata-bridge",
        "activation": "property-group-runtime",
        "receipt": RUNTIME_RECEIPT,
        "group_contract": REFERENCE_GROUP_CONTRACT,
    }
    for key, value in expected.items():
        if marker.get(key, "").casefold() != value.casefold():
            return False, f"bridge marker {key} does not match", receipt
    if receipt.get("schema") != 1 or receipt.get("status") != "verified":
        return False, "bridge receipt status/schema is invalid", receipt
    receipt_expected = {
        "package_id": "allin1.online-content",
        "pack_name": DLC_NAME,
        "layout": REFERENCE_PACK_LAYOUT,
        "edition": edition.strip().lower(),
        "group_contract": REFERENCE_GROUP_CONTRACT,
    }
    for key, value in receipt_expected.items():
        actual = receipt.get(key)
        if not isinstance(actual, str) or actual.casefold() != value.casefold():
            return False, f"bridge receipt {key} does not match", receipt
    try:
        marker_bytes = int(marker.get("archive_bytes", "0"))
        marker_assets = int(marker.get("asset_count", "-1"))
        marker_refs = int(marker.get("reference_count", "0"))
        receipt_bytes = int(receipt.get("archive_bytes", 0))
        receipt_assets = int(receipt.get("asset_count", -1))
        receipt_refs = int(receipt.get("reference_count", 0))
    except (TypeError, ValueError):
        return False, "bridge receipt counts are invalid", receipt
    expected_refs = len(MAP_ASSETS)
    if marker_assets != 0 or receipt_assets != 0:
        return False, "bridge unexpectedly declares copied assets", receipt
    if marker_refs != expected_refs or receipt_refs != expected_refs:
        return False, "bridge reference count does not match", receipt
    archive_bytes = archive_path.stat().st_size
    if marker_bytes != archive_bytes or receipt_bytes != archive_bytes:
        return False, "bridge archive size does not match", receipt

    marker_hash = marker.get("archive_sha256", "").lower()
    receipt_hash = str(receipt.get("archive_sha256", "")).lower()
    if not _is_sha256(marker_hash) or marker_hash != receipt_hash:
        return False, "bridge archive fingerprints disagree", receipt
    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest().lower() != receipt_hash:
        return False, "bridge archive failed its fingerprint", receipt
    groups_valid, groups_detail = validate_reference_group_receipt(
        receipt.get("groups"),
    )
    if not groups_valid:
        return False, groups_detail, receipt
    if gta_path is not None:
        sources_valid, source_detail = validate_reference_source_archives(
            receipt, gta_path,
        )
        if not sources_valid:
            return False, source_detail, receipt
    serialized = json.dumps(receipt, separators=(",", ":"))
    if ":\\" in serialized or "/Users/" in serialized:
        return False, "bridge receipt leaks a local path", receipt
    return True, "verified", receipt


def validate_reference_source_archives(
    receipt: dict[str, object], gta_path: Path,
) -> tuple[bool, str]:
    """Ensure the effective stock/mods archive roots have not changed."""
    expected = sorted({
        (asset.source_pack, asset.source_archive_name)
        for asset in MAP_ASSETS if asset.file_type == "RPF_FILE"
    } | {
        (pack, "dlc.rpf") for pack in ROCKSTAR_DEVICE_BY_PACK
    })
    raw_sources = receipt.get("source_archives")
    if not isinstance(raw_sources, list) or len(raw_sources) != len(expected):
        return False, "bridge source archive receipt is incomplete"
    sources: dict[tuple[str, str], dict[str, object]] = {}
    for item in raw_sources:
        if not isinstance(item, dict):
            return False, "bridge source archive receipt is malformed"
        pack = item.get("pack")
        archive = item.get("archive")
        if not isinstance(pack, str) or not isinstance(archive, str):
            return False, "bridge source archive identity is malformed"
        identity = (pack.casefold(), archive.casefold())
        if identity in sources:
            return False, "bridge source archive identity is duplicated"
        sources[identity] = item
    if set(sources) != {
        (pack.casefold(), archive.casefold()) for pack, archive in expected
    }:
        return False, "bridge source archive allowlist does not match"

    for pack, archive in expected:
        item = sources[(pack.casefold(), archive.casefold())]
        relative = Path("update") / "x64" / "dlcpacks" / pack / archive
        override = gta_path / "mods" / relative
        stock = gta_path / relative
        if override.is_file():
            effective = override
            source = "mods"
        elif stock.is_file():
            effective = stock
            source = "stock"
        else:
            return False, f"bridge source archive is missing: {relative.as_posix()}"
        expected_path = effective.relative_to(gta_path).as_posix()
        stat = effective.stat()
        try:
            recorded_size = int(item.get("size", -1))
            recorded_mtime = int(item.get("mtime_ns", -1))
        except (TypeError, ValueError):
            return False, "bridge source archive timestamps are malformed"
        if (
            item.get("source") != source
            or item.get("path") != expected_path
            or recorded_size != stat.st_size
            or recorded_mtime != stat.st_mtime_ns
        ):
            return False, (
                f"bridge source archive changed after Install / Repair: "
                f"{relative.as_posix()}"
            )
    return True, "verified"


def validate_runtime_activation_receipt(
    pack_root: Path,
    *,
    edition: str,
) -> tuple[bool, str, dict[str, object] | None]:
    """Inspect a historical/experimental startup receipt against its archive.

    A valid result documents only the old static transaction; it does not make
    startup activation safe. Production Install / Repair removes this receipt,
    and Health rejects startup registration regardless of the result here.
    """

    marker_path = pack_root / ACTIVE_MARKER
    receipt_path = pack_root / RUNTIME_RECEIPT
    archive_path = pack_root / "dlc.rpf"
    if not archive_path.is_file() or archive_path.stat().st_size <= 0:
        return False, "map archive is missing or empty", None
    try:
        marker = {
            key.strip().lower(): value.strip()
            for raw in marker_path.read_text(
                encoding="utf-8", errors="strict",
            ).splitlines()
            if "=" in raw
            for key, value in [raw.split("=", 1)]
            if key.strip()
        }
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return False, f"marker or receipt is unreadable: {exc}", None
    if not isinstance(receipt, dict):
        return False, "runtime receipt is not a JSON object", None

    expected_marker = {
        "layout": STARTUP_IPL_PACK_LAYOUT,
        "archive_registration": "startup",
        "activation": "verified-startup-registration",
        "receipt": RUNTIME_RECEIPT,
    }
    for key, expected in expected_marker.items():
        if marker.get(key, "").casefold() != expected.casefold():
            return False, f"marker {key} is not {expected}", receipt

    expected_receipt = {
        "status": "verified",
        "layout": STARTUP_IPL_PACK_LAYOUT,
        "edition": edition.strip().lower(),
        "gameconfig_entry": "common/data/gameconfig.xml",
    }
    if receipt.get("schema") != 1:
        return False, "runtime receipt schema is not 1", receipt
    for key, expected in expected_receipt.items():
        value = receipt.get(key)
        if not isinstance(value, str) or value.casefold() != expected.casefold():
            return False, f"receipt {key} does not match {expected}", receipt

    archive_bytes = archive_path.stat().st_size
    try:
        marker_bytes = int(marker.get("archive_bytes", "0"))
        marker_assets = int(marker.get("asset_count", "0"))
        receipt_bytes = int(receipt.get("archive_bytes", 0))
        receipt_assets = int(receipt.get("asset_count", 0))
    except (TypeError, ValueError):
        return False, "receipt size or asset count is invalid", receipt
    if marker_bytes != archive_bytes or receipt_bytes != archive_bytes:
        return False, "archive size does not match the activation receipt", receipt
    if marker_assets <= 0 or receipt_assets != marker_assets:
        return False, "asset count does not match the activation receipt", receipt

    marker_archive_hash = marker.get("archive_sha256", "").lower()
    marker_config_hash = marker.get("gameconfig_sha256", "").lower()
    receipt_archive_hash = str(receipt.get("archive_sha256", "")).lower()
    receipt_config_hash = str(receipt.get("gameconfig_sha256", "")).lower()
    if not _is_sha256(marker_archive_hash) or not _is_sha256(marker_config_hash):
        return False, "marker fingerprints are invalid", receipt
    if marker_archive_hash != receipt_archive_hash:
        return False, "archive fingerprints disagree", receipt
    if marker_config_hash != receipt_config_hash:
        return False, "gameconfig fingerprints disagree", receipt

    digest = hashlib.sha256()
    with archive_path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest().lower() != receipt_archive_hash:
        return False, "map archive failed its activation fingerprint", receipt
    if not isinstance(receipt.get("pools"), dict) or not receipt["pools"]:
        return False, "runtime receipt has no verified pool changes", receipt
    return True, "verified", receipt


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )
