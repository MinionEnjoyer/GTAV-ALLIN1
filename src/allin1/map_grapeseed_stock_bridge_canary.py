"""Phase-A boot canary for Grapeseed's stock ``mpheist`` map route.

The pack contains only ``content.xml`` and ``setup2.xml``.  Its one dormant
group references Rockstar's complete, already-registered
``MPHEIST_GTA5_CITYE_HOLLYWOOD_01`` changeset, but Phase A grants no authority
to execute that group or request the Grapeseed IPL.  A separate, observed
Phase-B transaction promotes only the marker/receipt pair.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from lxml import etree
from allin1.runtime_resources import resource_root

from allin1 import map_canary as shared


CANARY_ID = "grapeseed-enhanced-stock-reference-boot-v1"
INSTALL_CONFIRMATION = (
    "INSTALL_GRAPESEED_ENHANCED_STOCK_REFERENCE_BOOT_CANARY_V1"
)
ROLLBACK_CONFIRMATION = (
    "ROLLBACK_GRAPESEED_ENHANCED_STOCK_REFERENCE_BOOT_CANARY_V1"
)
STATE_SCHEMA = 4
STATE_DIRECTORY = "GrapeseedStockReferenceBootV1"

PACK_NAME = "allin1_mpheist_grapeseed_bridge"
DEVICE_NAME = "dlc_allin1_mpheist_grapeseed_bridge"
PACK_ENTRY = f"dlcpacks:/{PACK_NAME}/"
MARKER_NAME = f"{PACK_NAME}.active"
RUNTIME_RECEIPT_NAME = f"{PACK_NAME}.runtime.json"
LAYOUT = "stock-reference-v1-metadata-only"
RUNTIME_CONTRACT = "allin1-stock-mpheist-grapeseed-boot-v1"
PHASE = "phase-a-boot-only"
INSTALL_STATUS = "installed_boot_only_pending"
RUNTIME_STATUS = "verified"
ARCHIVE_REGISTRATION = "metadata-only"
ACTIVATION = "disabled-phase-a-boot-only"
PACKAGE_ID = "allin1.online-content"

STARTUP_CHANGESET = "ALLIN1_MPHEIST_GRAPESEED_BRIDGE_AUTOGEN"
DORMANT_GROUP = "ALLIN1_STOCK_MPHEIST_GRAPESEED_V1"
STOCK_CHANGESET = "MPHEIST_GTA5_CITYE_HOLLYWOOD_01"
STOCK_STARTUP_CHANGESET = "MPHEIST_AUTOGEN"
STOCK_DEVICE = "dlcMPHeist"
STOCK_PROXY = f"{STOCK_DEVICE}:/common/data/interiorProxies.meta"
STOCK_ARCHIVE_RELATIVE = Path("update/x64/dlcpacks/mpheist/dlc.rpf")
GRAPESEED_IPL = "hei_hw1_blimp_interior_v_garagem_milo_"
OLD_PACK_NAME = "allin1_maps"
OLD_PACK_ENTRY = f"dlcpacks:/{OLD_PACK_NAME}/"
DAVIS_PACK_NAME = "allin1_mptuner_bridge"
DAVIS_PACK_ENTRY = f"dlcpacks:/{DAVIS_PACK_NAME}/"
MARKER_PREAMBLE = (
    "ALLIN1 stock mpheist Grapeseed Phase-A metadata bridge; "
    "activation disabled."
)

DEPLOYMENT_PACK_BACKUP = "deployment-pack"
ORIGINAL_PACK_BACKUP = "original-pack"
ORIGINAL_DLCLIST_BACKUP = "original-dlclist.xml"
REGISTERED_DLCLIST_SNAPSHOT = "registered-dlclist.xml"
INSTALL_RECEIPT = "install-receipt.json"
ROLLBACK_RECEIPT = "rollback-receipt.json"
JOURNAL = "journal.json"

# Every value describes a durable boundary.  A process may disappear after the
# associated operation committed but before the next value is written; status
# and rollback therefore validate live state rather than trusting this hint.
JOURNAL_STATUSES = frozenset({
    "preparing",
    "prepared",
    "old_pack_rename_pending",
    "old_pack_saved",
    "new_pack_rename_pending",
    "pack_deployed",
    "registration_pending",
    "registered",
    "receipt_pending",
    "complete",
    "rollback_registration_pending",
    "registration_restored",
    "installed_pack_remove_pending",
    "installed_pack_removed",
    "original_pack_restore_pending",
    "original_pack_restored",
    "rollback_receipt_pending",
    "rolled_back",
    "recovery_required",
})

MARKER_FIELDS = frozenset({
    "canary_id", "schema", "status", "phase", "layout",
    "runtime_contract", "archive_registration", "activation",
    "property_scope", "asset_count", "data_file_count",
    "startup_changeset", "dormant_group_count", "declared_groups",
    "stock_changesets", "ipls", "native_group_execution_enabled",
    "runtime_ipl_requests_enabled", "gameconfig_changed",
    "native_host_installed", "receipt", "archive_bytes", "archive_sha256",
})
RECEIPT_FIELDS = frozenset({
    "schema", "canary_id", "status", "phase", "package_id", "pack_name",
    "device_name", "edition", "layout", "runtime_contract",
    "archive_registration", "activation", "property_scope", "asset_count",
    "data_file_count", "startup_changeset", "dormant_group_count",
    "declared_groups", "stock_changesets", "ipls", "groups",
    "native_group_execution_enabled", "runtime_ipl_requests_enabled",
    "gameconfig_changed", "native_host_installed", "archive_bytes",
    "archive_sha256", "source_attestation",
})
GROUP_FIELDS = frozenset({
    "property", "group", "changesets", "ipls", "activation_enabled",
})
SOURCE_ATTESTATION_FIELDS = frozenset({
    "pack", "archive", "source", "path", "size", "mtime_ns",
    "archive_sha256", "content_xml_bytes", "content_xml_sha256",
    "setup2_xml_bytes", "setup2_xml_sha256", "device_name",
    "device_name_sha256", "setup_order", "stock_startup_group",
    "stock_startup_changesets", "stock_startup_changeset",
    "stock_startup_changeset_sha256", "stock_proxy", "stock_map_group",
    "stock_map_group_changesets", "changeset_name", "changeset_sha256",
    "official_semantics",
})

_EXPECTED_STOCK_GROUP_STARTUP = (
    "MPHEIST_COMMON_VEHICLE_INSURGENT",
    "MPHEIST_COMMON_VEHICLE_VALKYRIE",
    "MPHEIST_AUTOGEN",
    "MPHEIST_UNLOCKS_AUTOGEN",
)
_EXPECTED_STOCK_GROUP_MAP = (
    "MPHEIST_PRE_MAP_CHANGES",
    "MPHEIST_GTA5_LODLIGHTS",
    "MPHEIST_BUSINESS2_MAP_UPDATE",
    "MPHEIST_GTA5_CITYE_DOWNTOWN_01",
    "MPHEIST_GTA5_CITYE_HOLLYWOOD_01",
    "MPHEIST_GTA5_CITYE_INDUST_01",
    "MPHEIST_GTA5_CITYE_INDUST_02",
    "MPHEIST_GTA5_CITYE_PORT_01",
    "MPHEIST_GTA5_CITYE_SCENTRAL_01",
    "MPHEIST_GTA5_CITYE_SUNSET",
    "MPHEIST_GTA5_CITYW_AIRPORT_01",
    "MPHEIST_GTA5_CITYW_BEVERLY_01",
    "MPHEIST_GTA5_CITYW_KOREATOWN_01",
    "MPHEIST_GTA5_CITYW_SANTAMON_01",
    "MPHEIST_GTA5_CITYW_VENICE_01",
    "MPHEIST_GTA5_HILLS_CITYHILLS_01",
    "MPHEIST_GTA5_HILLS_CITYHILLS_02",
    "MPHEIST_GTA5_HILLS_CITYHILLS_03",
    "MPHEIST_GTA5_HILLS_COUNTRY_01",
    "MPHEIST_GTA5_HILLS_COUNTRY_02",
    "MPHEIST_GTA5_HILLS_COUNTRY_03",
    "MPHEIST_GTA5_HILLS_COUNTRY_04",
    "MPHEIST_GTA5_HILLS_COUNTRY_06",
    "MPHEIST_POST_MAP_CHANGES",
)
_EXPECTED_MAP_INVALIDATIONS = (
    "hw1_blimp_interior_v_garagel_milo_.interior",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_02.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_06.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_07.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_08.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_13.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_14.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_24.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hw1_rd.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hollywood.rpf",
    "platform:/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
)
_EXPECTED_MAP_FILES = (
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_apart_high_new.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_apart_high2_new.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_garage_high_new.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/heist_ornate_bank.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_02.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_blimp.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_06.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_07.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_08.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_13.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_14.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_24.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hw1_rd.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hollywood.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/hollywood_01/hollywood_metadata.rpf",
)


def _state_root(gta_path: Path, override: Path | None = None) -> Path:
    if override is not None:
        return Path(override).resolve()
    base = os.environ.get("LOCALAPPDATA")
    local = Path(base) if base else Path.home() / "AppData" / "Local"
    identity = hashlib.sha256(
        str(gta_path.resolve()).casefold().encode("utf-8")
    ).hexdigest()[:16]
    return local / "ALLIN1" / "DeveloperCanaries" / STATE_DIRECTORY / identity


def _tool_path(patcher: Path | None) -> Path:
    if patcher is not None:
        return Path(patcher).resolve()
    return (
        resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )


def _destination(game: Path) -> Path:
    return game / "mods/update/x64/dlcpacks" / PACK_NAME


def _native_map_hosts(game: Path) -> list[str]:
    found = set(shared._native_hosts(game))
    for parent in (game, game / "scripts"):
        if not parent.is_dir():
            continue
        for path in parent.glob("*.asi"):
            if "maphost" in path.stem.casefold():
                found.add(path.relative_to(game).as_posix())
    return sorted(found)


def _effective_mpheist_archive(game: Path) -> tuple[Path, str]:
    override = game / "mods" / STOCK_ARCHIVE_RELATIVE
    stock = game / STOCK_ARCHIVE_RELATIVE
    if override.is_file():
        return override, "mods"
    if stock.is_file():
        return stock, "stock"
    raise FileNotFoundError(
        "The effective mpheist DLC archive is missing: "
        f"{STOCK_ARCHIVE_RELATIVE.as_posix()}"
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _values(item: etree._Element | etree._ElementTree, path: str) -> list[str]:
    return [
        value.strip() for value in item.xpath(path)
        if isinstance(value, str) and value.strip()
    ]


def _flag(item: etree._Element, name: str) -> bool:
    return item.xpath(f"string({name}/@value)").strip().casefold() == "true"


def _one_change(content: etree._ElementTree, name: str) -> etree._Element:
    matches = [
        item for item in content.xpath("//contentChangeSets/Item[changeSetName]")
        if item.xpath("string(changeSetName)").strip().casefold()
        == name.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Effective mpheist metadata must define exactly one {name}."
        )
    return matches[0]


def inspect_effective_mpheist_metadata(
    content_path: Path,
    setup_path: Path,
    *,
    archive_path: Path,
    archive_source: str,
    game: Path,
) -> dict[str, Any]:
    """Attest the exact Rockstar route and startup proxy registration."""
    try:
        content = etree.parse(str(content_path))
        setup = etree.parse(str(setup_path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise RuntimeError(f"Effective mpheist metadata is unreadable: {exc}") from exc

    device = setup.xpath("string(/SSetupData/deviceName)").strip()
    name_hash = setup.xpath("string(/SSetupData/nameHash)").strip()
    data_file = setup.xpath("string(/SSetupData/datFile)").strip()
    pack_type = setup.xpath("string(/SSetupData/type)").strip()
    try:
        setup_order = int(setup.xpath("string(/SSetupData/order/@value)"))
    except ValueError as exc:
        raise RuntimeError("Effective mpheist setup order is invalid.") from exc
    group_startup = _values(
        setup,
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()",
    )
    group_map = _values(
        setup,
        "//contentChangeSetGroups/Item[NameHash='GROUP_MAP']/"
        "ContentChangeSets/Item/text()",
    )
    if (
        device != STOCK_DEVICE
        or name_hash != "mpHeist"
        or data_file.casefold() != "content.xml"
        or pack_type != "EXTRACONTENT_COMPAT_PACK"
        or setup_order != 10
    ):
        raise RuntimeError(
            "Effective mpheist setup identity changed; an audited contract "
            "update is required."
        )
    if tuple(group_startup) != _EXPECTED_STOCK_GROUP_STARTUP:
        raise RuntimeError(
            "Effective mpheist GROUP_STARTUP membership changed; an audited "
            "contract update is required."
        )
    if tuple(group_map) != _EXPECTED_STOCK_GROUP_MAP:
        raise RuntimeError(
            "Effective mpheist GROUP_MAP membership changed; an audited "
            "contract update is required."
        )

    startup = _one_change(content, STOCK_STARTUP_CHANGESET)
    if STOCK_PROXY not in _values(startup, "filesToEnable/Item/text()"):
        raise RuntimeError(
            "MPHEIST_AUTOGEN no longer enables the stock interior proxy file."
        )
    proxy_items = [
        item for item in content.xpath("//dataFiles/Item")
        if item.xpath("string(filename)").strip() == STOCK_PROXY
    ]
    if len(proxy_items) != 1 or (
        proxy_items[0].xpath("string(fileType)").strip()
        != "INTERIOR_PROXY_ORDER_FILE"
        or proxy_items[0].xpath(
            "string(disabled/@value)"
        ).strip().casefold() != "true"
    ):
        raise RuntimeError("The stock mpheist interior proxy contract changed.")

    change = _one_change(content, STOCK_CHANGESET)
    semantics = {
        "associated_maps": _values(
            change, "mapChangeSetData/Item/associatedMap/text()",
        ),
        "files_to_invalidate": _values(
            change, "mapChangeSetData/Item/filesToInvalidate/Item/text()",
        ),
        "files_to_disable": _values(
            change, "mapChangeSetData/Item/filesToDisable/Item/text()",
        ),
        "files_to_enable": _values(
            change, "mapChangeSetData/Item/filesToEnable/Item/text()",
        ),
        "requires_loading_screen": _flag(change, "requiresLoadingScreen"),
        "loading_screen_context": change.xpath(
            "string(loadingScreenContext)"
        ).strip(),
        "use_cache_loader": _flag(change, "useCacheLoader"),
    }
    expected_semantics = {
        "associated_maps": ["MO_JIM_L11"],
        "files_to_invalidate": list(_EXPECTED_MAP_INVALIDATIONS),
        "files_to_disable": [],
        "files_to_enable": list(_EXPECTED_MAP_FILES),
        "requires_loading_screen": True,
        "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
        "use_cache_loader": True,
    }
    if len(change.xpath("mapChangeSetData/Item")) != 1 or semantics != expected_semantics:
        raise RuntimeError(
            "Effective MPHEIST_GTA5_CITYE_HOLLYWOOD_01 semantics changed; "
            "Phase A refuses to register an unaudited reference."
        )

    entries = {
        item.xpath("string(filename)").strip(): item
        for item in content.xpath("//dataFiles/Item")
    }
    for filename in _EXPECTED_MAP_FILES:
        item = entries.get(filename)
        if (
            item is None
            or item.xpath("string(fileType)").strip() != "RPF_FILE"
            or item.xpath("string(disabled/@value)").strip().casefold()
            != "true"
        ):
            raise RuntimeError(
                f"The stock changeset references an unverified RPF: {filename}"
            )

    archive_stat = archive_path.stat()
    relative = archive_path.relative_to(game).as_posix()
    canonical_change = etree.tostring(
        change, method="c14n", with_comments=False,
    )
    canonical_startup = etree.tostring(
        startup, method="c14n", with_comments=False,
    )
    return {
        "pack": "mpheist",
        "archive": "dlc.rpf",
        "source": archive_source,
        "path": relative,
        "size": archive_stat.st_size,
        "mtime_ns": archive_stat.st_mtime_ns,
        "archive_sha256": shared._sha256(archive_path),
        "content_xml_bytes": content_path.stat().st_size,
        "content_xml_sha256": shared._sha256(content_path),
        "setup2_xml_bytes": setup_path.stat().st_size,
        "setup2_xml_sha256": shared._sha256(setup_path),
        "device_name": device,
        "device_name_sha256": _sha256_bytes(device.encode("utf-8")),
        "setup_order": setup_order,
        "stock_startup_group": "GROUP_STARTUP",
        "stock_startup_changesets": group_startup,
        "stock_startup_changeset": STOCK_STARTUP_CHANGESET,
        "stock_startup_changeset_sha256": _sha256_bytes(canonical_startup),
        "stock_proxy": STOCK_PROXY,
        "stock_map_group": "GROUP_MAP",
        "stock_map_group_changesets": group_map,
        "changeset_name": STOCK_CHANGESET,
        "changeset_sha256": _sha256_bytes(canonical_change),
        "official_semantics": semantics,
    }


def _build_content_xml() -> bytes:
    root = etree.Element("CDataFileMgr__ContentsOfDataFileXml")
    etree.SubElement(root, "disabledFiles")
    etree.SubElement(root, "includedXmlFiles")
    etree.SubElement(root, "includedDataFiles")
    etree.SubElement(root, "dataFiles")
    sets = etree.SubElement(root, "contentChangeSets")
    change = etree.SubElement(sets, "Item")
    etree.SubElement(change, "changeSetName").text = STARTUP_CHANGESET
    etree.SubElement(change, "mapChangeSetData")
    etree.SubElement(change, "filesToInvalidate")
    etree.SubElement(change, "filesToDisable")
    etree.SubElement(change, "filesToEnable")
    etree.SubElement(change, "txdToLoad")
    etree.SubElement(change, "txdToUnload")
    etree.SubElement(change, "residentResources")
    etree.SubElement(change, "unregisterResources")
    etree.SubElement(change, "requiresLoadingScreen").set("value", "false")
    etree.SubElement(root, "patchFiles")
    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8",
    )


def _build_setup2_xml() -> bytes:
    root = etree.Element("SSetupData")
    etree.SubElement(root, "deviceName").text = DEVICE_NAME
    etree.SubElement(root, "datFile").text = "content.xml"
    etree.SubElement(root, "timeStamp").text = "09/01/2026 00:00:00"
    etree.SubElement(root, "nameHash").text = PACK_NAME
    etree.SubElement(root, "contentChangeSets")
    groups = etree.SubElement(root, "contentChangeSetGroups")
    startup = etree.SubElement(groups, "Item")
    etree.SubElement(startup, "NameHash").text = "GROUP_STARTUP"
    startup_changes = etree.SubElement(startup, "ContentChangeSets")
    etree.SubElement(startup_changes, "Item").text = STARTUP_CHANGESET
    dormant = etree.SubElement(groups, "Item")
    etree.SubElement(dormant, "NameHash").text = DORMANT_GROUP
    dormant_changes = etree.SubElement(dormant, "ContentChangeSets")
    etree.SubElement(dormant_changes, "Item").text = STOCK_CHANGESET
    etree.SubElement(root, "startupScript")
    etree.SubElement(root, "scriptCallstackSize").set("value", "0")
    etree.SubElement(root, "type").text = "EXTRACONTENT_COMPAT_PACK"
    etree.SubElement(root, "order").set("value", "73")
    etree.SubElement(root, "minorOrder").set("value", "0")
    etree.SubElement(root, "isLevelPack").set("value", "false")
    etree.SubElement(root, "dependencyPackHash")
    etree.SubElement(root, "requiredVersion")
    etree.SubElement(root, "subPackCount").set("value", "0")
    return etree.tostring(
        root, pretty_print=True, xml_declaration=True, encoding="UTF-8",
    )


def create_stock_bridge_staging(output: Path) -> Path:
    root = output / PACK_NAME
    root.mkdir(parents=True, exist_ok=False)
    (root / "content.xml").write_bytes(_build_content_xml())
    (root / "setup2.xml").write_bytes(_build_setup2_xml())
    return root


def inspect_stock_bridge_topology(root: Path) -> dict[str, Any]:
    try:
        content = etree.parse(str(root / "content.xml"))
        setup = etree.parse(str(root / "setup2.xml"))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise RuntimeError(f"Grapeseed bridge metadata is unreadable: {exc}") from exc
    groups = setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    )
    startup = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    )
    dormant = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash=$group]/"
        "ContentChangeSets/Item/text()",
        group=DORMANT_GROUP,
    )
    checks = {
        "device": setup.xpath("string(/SSetupData/deviceName)") == DEVICE_NAME,
        "name_hash": setup.xpath("string(/SSetupData/nameHash)") == PACK_NAME,
        "pack_type": setup.xpath("string(/SSetupData/type)")
        == "EXTRACONTENT_COMPAT_PACK",
        "no_data_files": content.xpath("//dataFiles/Item") == [],
        "one_local_changeset": content.xpath(
            "//contentChangeSets/Item/changeSetName/text()"
        ) == [STARTUP_CHANGESET],
        "startup_is_inert": content.xpath(
            "//contentChangeSets/Item/filesToEnable/Item"
        ) == [] and content.xpath(
            "string(//contentChangeSets/Item/requiresLoadingScreen/@value)"
        ) == "false",
        "groups": groups == ["GROUP_STARTUP", DORMANT_GROUP],
        "startup_group": startup == [STARTUP_CHANGESET],
        "dormant_group": dormant == [STOCK_CHANGESET],
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise RuntimeError(f"Grapeseed bridge topology failed: {failed}")
    return {
        "checks": checks,
        "startup_changeset": STARTUP_CHANGESET,
        "groups": ["GROUP_STARTUP", DORMANT_GROUP],
        "dormant_group_count": 1,
        "stock_changesets": [STOCK_CHANGESET],
    }


def _extract_source_attestation(
    game: Path, patcher: Path, work: Path,
) -> dict[str, Any]:
    archive, source = _effective_mpheist_archive(game)
    content = work / "effective-mpheist-content.xml"
    setup = work / "effective-mpheist-setup2.xml"
    shared._run_tool(
        patcher,
        ["extract-entry", game, archive, "content.xml", content],
        operation="Read effective Enhanced mpheist content.xml",
    )
    shared._run_tool(
        patcher,
        ["extract-entry", game, archive, "setup2.xml", setup],
        operation="Read effective Enhanced mpheist setup2.xml",
    )
    if not content.is_file() or not setup.is_file():
        raise RuntimeError("RpfPatcher returned incomplete mpheist metadata.")
    return inspect_effective_mpheist_metadata(
        content, setup,
        archive_path=archive, archive_source=source, game=game,
    )


def _build_archive(
    game: Path, patcher: Path, work: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    attestation = _extract_source_attestation(game, patcher, work)
    staging = create_stock_bridge_staging(work)
    topology = inspect_stock_bridge_topology(staging)
    output = work / f"{PACK_NAME}.dlc.rpf"
    shared._run_tool(
        patcher,
        ["build-dlc", staging, output, "--gta-path", game],
        operation="Build stock mpheist Grapeseed Phase-A bridge",
        timeout=300,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("The Grapeseed stock bridge build produced no archive.")
    packaged = work / "packaged"
    packaged.mkdir()
    for name in ("content.xml", "setup2.xml"):
        extracted = packaged / name
        shared._run_tool(
            patcher,
            ["extract-entry", game, output, name, extracted],
            operation=f"Verify packaged Grapeseed stock bridge {name}",
        )
        if extracted.read_bytes() != (staging / name).read_bytes():
            raise RuntimeError(f"Packaged Grapeseed stock bridge {name} changed.")
    inspect_stock_bridge_topology(packaged)
    index_path = work / "packaged-index.json"
    shared._run_tool(
        patcher,
        ["index-json", game, output, index_path],
        operation="Index packaged Grapeseed stock bridge",
    )
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The packaged Grapeseed bridge index is unreadable.") from exc
    entries = index.get("entries") if isinstance(index, dict) else None
    paths = (
        [item.get("path") for item in entries if isinstance(item, dict)]
        if isinstance(entries, list) else None
    )
    if (
        index.get("schema_version") != 1
        or sorted(paths or []) != ["content.xml", "setup2.xml"]
        or index.get("warnings") != []
    ):
        raise RuntimeError(
            "The packaged Grapeseed bridge is not the exact two-entry RPF."
        )
    return output, topology, attestation


def _static_contract(*, status: str) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": status,
        "phase": PHASE,
        "package_id": PACKAGE_ID,
        "pack_name": PACK_NAME,
        "device_name": DEVICE_NAME,
        "edition": "enhanced",
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": ARCHIVE_REGISTRATION,
        "activation": ACTIVATION,
        "property_scope": "grapeseed",
        "asset_count": 0,
        "data_file_count": 0,
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": 1,
        "declared_groups": ["GROUP_STARTUP", DORMANT_GROUP],
        "stock_changesets": [STOCK_CHANGESET],
        "ipls": [GRAPESEED_IPL],
        "groups": [{
            "property": "grapeseed",
            "group": DORMANT_GROUP,
            "changesets": [STOCK_CHANGESET],
            "ipls": [GRAPESEED_IPL],
            "activation_enabled": False,
        }],
        "native_group_execution_enabled": False,
        "runtime_ipl_requests_enabled": False,
        "gameconfig_changed": False,
        "native_host_installed": False,
    }


def _runtime_receipt(
    archive: Path, attestation: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        **_static_contract(status=RUNTIME_STATUS),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": shared._sha256(archive),
        "source_attestation": attestation,
    }
    _assert_portable_receipt(payload)
    return payload


def _assert_portable_receipt(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, separators=(",", ":"))
    folded = serialized.casefold()
    if ":\\" in serialized or ":/users/" in folded or "/users/" in folded:
        raise RuntimeError("The Grapeseed runtime receipt contains a local path.")


def _marker_fields(receipt: dict[str, Any], *, phase_b: bool = False) -> dict[str, str]:
    del phase_b
    return {
        "canary_id": CANARY_ID,
        "schema": str(STATE_SCHEMA),
        "status": INSTALL_STATUS,
        "phase": PHASE,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": ARCHIVE_REGISTRATION,
        "activation": ACTIVATION,
        "property_scope": "grapeseed",
        "asset_count": "0",
        "data_file_count": "0",
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": "1",
        "declared_groups": f"GROUP_STARTUP,{DORMANT_GROUP}",
        "stock_changesets": STOCK_CHANGESET,
        "ipls": GRAPESEED_IPL,
        "native_group_execution_enabled": "false",
        "runtime_ipl_requests_enabled": "false",
        "gameconfig_changed": "false",
        "native_host_installed": "false",
        "receipt": RUNTIME_RECEIPT_NAME,
        "archive_bytes": str(receipt["archive_bytes"]),
        "archive_sha256": str(receipt["archive_sha256"]),
    }


def _write_marker(path: Path, receipt: dict[str, Any]) -> None:
    fields = _marker_fields(receipt)
    shared._write_text_atomic(
        MARKER_PREAMBLE + "\n"
        + "".join(f"{key}={value}\n" for key, value in fields.items()),
        path,
    )


def _parse_strict_marker(path: Path) -> tuple[dict[str, str] | None, str]:
    try:
        lines = path.read_text(encoding="utf-8").replace("\r", "").split("\n")
    except (OSError, UnicodeError) as exc:
        return None, f"marker unreadable: {exc}"
    if not lines or lines[0] != MARKER_PREAMBLE:
        return None, "marker preamble mismatch"
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if "=" not in line:
            return None, "marker line is malformed"
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in fields:
            return None, "marker has an invalid or duplicate field"
        fields[key] = value.strip()
    if set(fields) != MARKER_FIELDS:
        return None, "marker field allowlist mismatch"
    return fields, "verified"


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _read_bounded_json_object(
    path: Path, *, maximum_bytes: int = 256 * 1024,
) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"JSON contract is not a regular file: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > maximum_bytes:
        raise RuntimeError(f"JSON contract is outside its size bound: {path.name}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            path.read_bytes().decode("utf-8-sig"),
            object_pairs_hook=unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"JSON contract is unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON contract is not an object: {path.name}")
    return payload


def _source_attestation_shape_valid(payload: object) -> bool:
    if not isinstance(payload, dict) or set(payload) != SOURCE_ATTESTATION_FIELDS:
        return False
    source = payload.get("source")
    expected_path = (
        "mods/update/x64/dlcpacks/mpheist/dlc.rpf"
        if source == "mods"
        else "update/x64/dlcpacks/mpheist/dlc.rpf"
        if source == "stock"
        else ""
    )
    semantics = payload.get("official_semantics")
    return (
        payload.get("pack") == "mpheist"
        and payload.get("archive") == "dlc.rpf"
        and payload.get("path") == expected_path
        and isinstance(payload.get("size"), int) and payload["size"] > 0
        and isinstance(payload.get("mtime_ns"), int) and payload["mtime_ns"] > 0
        and _is_sha256(payload.get("archive_sha256"))
        and isinstance(payload.get("content_xml_bytes"), int)
        and payload["content_xml_bytes"] > 0
        and _is_sha256(payload.get("content_xml_sha256"))
        and isinstance(payload.get("setup2_xml_bytes"), int)
        and payload["setup2_xml_bytes"] > 0
        and _is_sha256(payload.get("setup2_xml_sha256"))
        and payload.get("device_name") == STOCK_DEVICE
        and _is_sha256(payload.get("device_name_sha256"))
        and payload.get("setup_order") == 10
        and payload.get("stock_startup_group") == "GROUP_STARTUP"
        and payload.get("stock_startup_changesets")
        == list(_EXPECTED_STOCK_GROUP_STARTUP)
        and payload.get("stock_startup_changeset") == STOCK_STARTUP_CHANGESET
        and _is_sha256(payload.get("stock_startup_changeset_sha256"))
        and payload.get("stock_proxy") == STOCK_PROXY
        and payload.get("stock_map_group") == "GROUP_MAP"
        and payload.get("stock_map_group_changesets")
        == list(_EXPECTED_STOCK_GROUP_MAP)
        and payload.get("changeset_name") == STOCK_CHANGESET
        and _is_sha256(payload.get("changeset_sha256"))
        and semantics == {
            "associated_maps": ["MO_JIM_L11"],
            "files_to_invalidate": list(_EXPECTED_MAP_INVALIDATIONS),
            "files_to_disable": [],
            "files_to_enable": list(_EXPECTED_MAP_FILES),
            "requires_loading_screen": True,
            "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
            "use_cache_loader": True,
        }
    )


def _source_attestation_identity_current(game: Path, recorded: object) -> bool:
    """Bounded source check for launch/health; intentionally skips 2.44GB hash."""
    if not _source_attestation_shape_valid(recorded):
        return False
    assert isinstance(recorded, dict)
    try:
        archive, source = _effective_mpheist_archive(game)
        stat = archive.stat()
        return (
            recorded.get("source") == source
            and recorded.get("path") == archive.relative_to(game).as_posix()
            and recorded.get("size") == stat.st_size
            and recorded.get("mtime_ns") == stat.st_mtime_ns
        )
    except (FileNotFoundError, OSError, ValueError):
        return False


def _receipt_matches_launch_contract(
    payload: object,
    *,
    game: Path,
    archive: Path,
) -> tuple[bool, str]:
    if not isinstance(payload, dict) or set(payload) != RECEIPT_FIELDS:
        return False, "receipt field allowlist mismatch"
    groups = payload.get("groups")
    if (
        not isinstance(groups, list)
        or len(groups) != 1
        or not isinstance(groups[0], dict)
        or set(groups[0]) != GROUP_FIELDS
        or groups[0] != _static_contract(status=RUNTIME_STATUS)["groups"][0]
    ):
        return False, "Phase-A Grapeseed group mismatch"
    expected = {
        **_static_contract(status=RUNTIME_STATUS),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": shared._sha256(archive),
        "source_attestation": payload.get("source_attestation"),
    }
    if payload != expected:
        return False, "receipt values mismatch"
    if not _source_attestation_identity_current(
        game, payload.get("source_attestation"),
    ):
        return False, "source archive identity or attestation shape mismatch"
    return True, "verified"


def validate_phase_a_launch_contract(
    gta_path: Path,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Validate Phase A without hashing Rockstar's multi-gigabyte archive."""
    game = Path(gta_path)
    root = _destination(game)
    archive = root / "dlc.rpf"
    marker = root / MARKER_NAME
    runtime = root / RUNTIME_RECEIPT_NAME
    try:
        if not (game / "GTA5_Enhanced.exe").is_file():
            return False, "Phase A is Enhanced-only", None
        if root.is_symlink() or not root.is_dir():
            return False, "pack root is not a regular directory", None
        entries = {path.name: path for path in root.iterdir()}
        if set(entries) != {"dlc.rpf", MARKER_NAME, RUNTIME_RECEIPT_NAME}:
            return False, "pack files differ from exact three-file layout", None
        if any(path.is_symlink() or not path.is_file() for path in entries.values()):
            return False, "pack contains a non-regular file", None
        if archive.stat().st_size <= 0 or archive.stat().st_size > 4 * 1024 * 1024:
            return False, "metadata archive size is outside the bound", None
        if _native_map_hosts(game):
            return False, "a native map host is installed", None
        if _old_pack_paths(game):
            return False, "the retired allin1_maps pack is present", None
        marker_payload, detail = _parse_strict_marker(marker)
        if marker_payload is None:
            return False, detail, None
        if marker.stat().st_size > 32 * 1024:
            return False, "marker exceeds its size bound", None
        runtime_payload = _read_bounded_json_object(runtime)
        valid, detail = _receipt_matches_launch_contract(
            runtime_payload, game=game, archive=archive,
        )
        if not valid:
            return False, detail, runtime_payload
        if marker_payload != _marker_fields(runtime_payload):
            return False, "marker values mismatch", runtime_payload
        return True, "verified", runtime_payload
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, str(exc), None


def _normalized(value: str) -> str:
    return value.rstrip("/").casefold()


def _count_entry(payload: bytes, entry: str) -> int:
    wanted = _normalized(entry)
    return sum(
        _normalized(value) == wanted for value in shared._dlclist_items(payload)
    )


def _verify_registration_delta(before: bytes, after: bytes) -> None:
    before_items = shared._dlclist_items(before)
    after_items = shared._dlclist_items(after)
    if _count_entry(before, PACK_ENTRY) != 0:
        raise RuntimeError("The Grapeseed bridge was already registered before install.")
    if _count_entry(after, PACK_ENTRY) != 1:
        raise RuntimeError("The Grapeseed bridge registration is not exact.")
    expected = [_normalized(item) for item in before_items] + [
        _normalized(PACK_ENTRY)
    ]
    if [_normalized(item) for item in after_items] != expected:
        raise RuntimeError("dlclist.xml changed outside the one Grapeseed entry.")


def _old_pack_paths(game: Path) -> list[str]:
    result = []
    for base in ("mods/update", "update"):
        path = game / base / "x64/dlcpacks" / OLD_PACK_NAME
        if path.exists():
            result.append(path.relative_to(game).as_posix())
    return result


def _assert_clean_map_baseline(game: Path, dlclist: bytes) -> None:
    old_paths = _old_pack_paths(game)
    if old_paths or _count_entry(dlclist, OLD_PACK_ENTRY):
        raise RuntimeError(
            "Remove the retired allin1_maps pack before the Grapeseed canary."
        )
    if _count_entry(dlclist, PACK_ENTRY):
        raise RuntimeError("The Grapeseed bridge is already registered.")


def _davis_bridge_snapshot(game: Path, dlclist: bytes) -> dict[str, Any]:
    """Record Davis without making its presence a Grapeseed prerequisite."""
    root = game / "mods/update/x64/dlcpacks" / DAVIS_PACK_NAME
    if root.exists() and not root.is_dir():
        raise RuntimeError("The Davis bridge path is not a regular directory.")
    return {
        "registration_count": _count_entry(dlclist, DAVIS_PACK_ENTRY),
        "pack_present": root.is_dir(),
        "pack_manifest": shared._file_manifest(root) if root.is_dir() else {},
    }


def _source_attestation_current(game: Path, recorded: Any) -> bool:
    if not isinstance(recorded, dict):
        return False
    try:
        archive, source = _effective_mpheist_archive(game)
        relative = archive.relative_to(game).as_posix()
        stat = archive.stat()
        return (
            recorded.get("pack") == "mpheist"
            and recorded.get("archive") == "dlc.rpf"
            and recorded.get("source") == source
            and recorded.get("path") == relative
            and recorded.get("size") == stat.st_size
            and recorded.get("mtime_ns") == stat.st_mtime_ns
            and recorded.get("archive_sha256") == shared._sha256(archive)
        )
    except (FileNotFoundError, OSError, ValueError):
        return False


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Checkpoint is unreadable: {path.name}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Checkpoint is not an object: {path.name}")
    return payload


def _current_dlclist(
    game: Path, patcher: Path, output: Path,
) -> bytes:
    return shared._extract_dlclist(
        patcher, game, game / "mods/update/update.rpf", output,
    )


def _is_sha256_value(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _is_transaction_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _durable_file(path: Path) -> None:
    """Flush a completed transaction artifact before publishing its state."""
    # Windows' _commit rejects a descriptor opened read-only.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _durable_json(payload: dict[str, Any], path: Path) -> None:
    shared._write_json_atomic(payload, path)
    _durable_file(path)


def _hit(
    fault_injector: Callable[[str], None] | None,
    boundary: str,
) -> None:
    if fault_injector is not None:
        fault_injector(boundary)


def _transaction_paths(
    game: Path, transaction_id: str,
) -> dict[str, Path]:
    if not _is_transaction_id(transaction_id):
        raise RuntimeError("The Grapeseed Phase-A transaction id is invalid.")
    # Keep the same-volume transaction name deliberately short: GTA roots and
    # pytest sandboxes can already be close to Win32's legacy MAX_PATH limit.
    root = _destination(game).parent / f".a1g-{transaction_id[:12]}"
    return {
        "root": root,
        "stage_building": root / "stage-building",
        "stage": root / "staged-pack",
        "saved": root / "original-pack",
        "discarded": root / "deployed-pack",
        "restore": root / "restore-pack",
    }


def _load_transaction_journal(state: Path) -> dict[str, Any]:
    journal = _load_json(state / JOURNAL)
    if (
        journal.get("schema") != STATE_SCHEMA
        or journal.get("canary_id") != CANARY_ID
        or journal.get("phase") != PHASE
        or journal.get("edition") != "enhanced"
        or journal.get("status") not in JOURNAL_STATUSES
        or not _is_transaction_id(journal.get("transaction_id"))
        or not isinstance(journal.get("pack_existed"), bool)
        or not isinstance(journal.get("original_pack_manifest"), dict)
        or not isinstance(journal.get("deployed_pack_manifest"), dict)
        or not isinstance(journal.get("source_attestation"), dict)
        or not isinstance(journal.get("davis_bridge_snapshot"), dict)
        or not isinstance(journal.get("topology"), dict)
        or not isinstance(journal.get("archive_bytes"), int)
        or journal.get("archive_bytes", 0) <= 0
    ):
        raise RuntimeError("The Grapeseed Phase-A transaction journal is invalid.")
    for field in (
        "original_dlclist_sha256",
        "archive_sha256",
        "marker_sha256",
        "runtime_receipt_sha256",
        "content_xml_sha256",
        "setup2_xml_sha256",
    ):
        if not _is_sha256_value(journal.get(field)):
            raise RuntimeError(
                f"The Grapeseed Phase-A journal {field} is invalid."
            )
    pack_existed = journal["pack_existed"]
    if pack_existed != bool(journal["original_pack_manifest"]):
        # An empty pre-existing directory is permitted and has an empty manifest.
        backup = state / ORIGINAL_PACK_BACKUP
        if not (pack_existed and backup.is_dir()):
            raise RuntimeError(
                "The Grapeseed Phase-A original-pack identity is inconsistent."
            )
    return journal


def _transaction_artifact_checks(
    state: Path, journal: dict[str, Any],
) -> dict[str, bool]:
    original_dlclist = state / ORIGINAL_DLCLIST_BACKUP
    original_pack = state / ORIGINAL_PACK_BACKUP
    deployment_pack = state / DEPLOYMENT_PACK_BACKUP
    try:
        original_dlclist_ok = (
            original_dlclist.is_file()
            and shared._sha256(original_dlclist)
            == journal["original_dlclist_sha256"]
        )
        original_pack_ok = (
            original_pack.is_dir()
            and shared._file_manifest(original_pack)
            == journal["original_pack_manifest"]
            if journal["pack_existed"]
            else not original_pack.exists()
        )
        deployment_pack_ok = (
            deployment_pack.is_dir()
            and shared._file_manifest(deployment_pack)
            == journal["deployed_pack_manifest"]
        )
        metadata_ok = (
            (state / "content.xml").is_file()
            and shared._sha256(state / "content.xml")
            == journal["content_xml_sha256"]
            and (state / "setup2.xml").is_file()
            and shared._sha256(state / "setup2.xml")
            == journal["setup2_xml_sha256"]
            and all(inspect_stock_bridge_topology(state)["checks"].values())
        )
    except (OSError, RuntimeError, KeyError, TypeError):
        original_dlclist_ok = False
        original_pack_ok = False
        deployment_pack_ok = False
        metadata_ok = False
    return {
        "original_dlclist_artifact": original_dlclist_ok,
        "original_pack_artifact": original_pack_ok,
        "deployment_pack_artifact": deployment_pack_ok,
        "metadata_artifacts": metadata_ok,
    }


def _manifest_kind(
    path: Path,
    *,
    original_manifest: dict[str, Any],
    deployed_manifest: dict[str, Any],
) -> str:
    if not path.exists():
        return "absent"
    if not path.is_dir() or path.is_symlink():
        return "unknown"
    try:
        observed = shared._file_manifest(path)
    except (OSError, RuntimeError):
        return "unknown"
    if observed == deployed_manifest:
        return "deployed"
    if observed == original_manifest:
        return "original"
    return "unknown"


def _registration_snapshot(
    game: Path, patcher: Path,
) -> tuple[bytes, int, int]:
    with tempfile.TemporaryDirectory(
        prefix="allin1-grapeseed-phase-a-registration-"
    ) as tmp:
        current = Path(tmp) / "dlclist.xml"
        payload = _current_dlclist(game, patcher, current)
    return (
        payload,
        _count_entry(payload, PACK_ENTRY),
        _count_entry(payload, OLD_PACK_ENTRY),
    )


def _live_transaction_state(
    game: Path,
    state: Path,
    patcher: Path,
    journal: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, bool]]:
    paths = _transaction_paths(game, journal["transaction_id"])
    original_manifest = journal["original_pack_manifest"]
    deployed_manifest = journal["deployed_pack_manifest"]
    destination = _destination(game)
    destination_kind = _manifest_kind(
        destination,
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    saved_kind = _manifest_kind(
        paths["saved"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    stage_building_kind = _manifest_kind(
        paths["stage_building"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    stage_kind = _manifest_kind(
        paths["stage"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    discarded_kind = _manifest_kind(
        paths["discarded"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    restore_kind = _manifest_kind(
        paths["restore"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    try:
        payload, registration_count, retired_count = _registration_snapshot(
            game, patcher,
        )
    except (OSError, RuntimeError):
        payload, registration_count, retired_count = b"", -1, -1

    pack_existed = journal["pack_existed"]
    expected_pre = "original" if pack_existed else "absent"
    paths_known = (
        destination_kind in {"absent", "original", "deployed"}
        and saved_kind in ({"absent", "original"} if pack_existed else {"absent"})
        and stage_kind in {"absent", "deployed"}
        and discarded_kind in {"absent", "deployed"}
        and restore_kind in ({"absent", "original"} if pack_existed else {"absent"})
    )
    registration_known = registration_count in {0, 1} and retired_count == 0
    artifacts = _transaction_artifact_checks(state, journal)
    safe = paths_known and registration_known and all(artifacts.values())
    if safe and destination_kind == expected_pre and registration_count == 0:
        shape = "pre_mutation"
    elif safe and destination_kind == "deployed" and registration_count == 1:
        shape = "installed"
    elif safe:
        shape = "known_partial"
    else:
        shape = "unknown_drift"
    details = {
        "destination": destination_kind,
        "saved_original": saved_kind,
        "staged_deployment": stage_kind,
        "stage_building": stage_building_kind,
        "discarded_deployment": discarded_kind,
        "restore_stage": restore_kind,
        "registration_count": registration_count,
        "retired_registration_count": retired_count,
        "dlclist_sha256": _sha256_bytes(payload) if payload else None,
    }
    checks = {
        **artifacts,
        "transaction_paths_known": paths_known,
        "registration_known": registration_known,
        "retired_allin1_maps_absent": retired_count == 0,
    }
    return shape, details, checks


def _set_journal_status(
    journal: dict[str, Any],
    journal_path: Path,
    status: str,
    fault_injector: Callable[[str], None] | None,
) -> None:
    if status not in JOURNAL_STATUSES:
        raise RuntimeError(f"Unknown Grapeseed transaction state: {status}")
    journal["status"] = status
    _durable_json(journal, journal_path)
    _hit(fault_injector, status)


def _assert_recovery_safe(
    game: Path,
    state: Path,
    patcher: Path,
    journal: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    shape, details, checks = _live_transaction_state(
        game, state, patcher, journal,
    )
    if not all(checks.values()):
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise RuntimeError(
            "Grapeseed Phase-A rollback refuses to overwrite unknown live "
            f"drift: {failed}; live={details}."
        )
    return shape, details


def _rollback_result(
    journal: dict[str, Any], dlclist_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": journal["transaction_id"],
        "status": "rolled_back",
        "original_dlclist_sha256": journal["original_dlclist_sha256"],
        "restored_dlclist_sha256": dlclist_sha256,
        "restored_original_pack": journal["pack_existed"],
    }


def _guarded_transaction_rollback(
    game: Path,
    state: Path,
    patcher: Path,
    journal: dict[str, Any],
    *,
    replace: Callable[[Path, Path], None] = os.replace,
    fault_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Restore only our exact registration and exact known pack images."""
    journal_path = state / JOURNAL
    _assert_recovery_safe(game, state, patcher, journal)

    _set_journal_status(
        journal, journal_path, "rollback_registration_pending", fault_injector,
    )
    _payload, registration_count, retired_count = _registration_snapshot(
        game, patcher,
    )
    if retired_count:
        raise RuntimeError(
            "Grapeseed rollback refuses to operate while allin1_maps is registered."
        )
    if registration_count == 1:
        shared._run_tool(
            patcher,
            ["unregister-dlc", game, PACK_NAME],
            operation="Unregister only the Grapeseed Phase-A bridge",
        )
        _hit(fault_injector, "registration_removed_live")
    elif registration_count != 0:
        raise RuntimeError("The Grapeseed registration count is not recoverable.")
    payload, registration_count, retired_count = _registration_snapshot(
        game, patcher,
    )
    if registration_count != 0 or retired_count != 0:
        raise RuntimeError("The Grapeseed registration removal did not verify.")
    _set_journal_status(
        journal, journal_path, "registration_restored", fault_injector,
    )

    paths = _transaction_paths(game, journal["transaction_id"])
    destination = _destination(game)
    original_manifest = journal["original_pack_manifest"]
    deployed_manifest = journal["deployed_pack_manifest"]
    destination_kind = _manifest_kind(
        destination,
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    discarded_kind = _manifest_kind(
        paths["discarded"],
        original_manifest=original_manifest,
        deployed_manifest=deployed_manifest,
    )
    if destination_kind == "deployed":
        if discarded_kind == "absent":
            paths["root"].mkdir(parents=True, exist_ok=True)
            _set_journal_status(
                journal, journal_path, "installed_pack_remove_pending",
                fault_injector,
            )
            replace(destination, paths["discarded"])
            _hit(fault_injector, "installed_pack_removed_live")
        elif discarded_kind == "deployed":
            raise RuntimeError(
                "Grapeseed rollback refuses duplicate deployed pack images."
            )
        else:
            raise RuntimeError(
                "Grapeseed rollback refuses an unknown discarded pack."
            )
    elif destination_kind not in {"absent", "original"}:
        raise RuntimeError(
            "Grapeseed rollback refuses to overwrite the active pack."
        )
    _set_journal_status(
        journal, journal_path, "installed_pack_removed", fault_injector,
    )

    if journal["pack_existed"]:
        destination_kind = _manifest_kind(
            destination,
            original_manifest=original_manifest,
            deployed_manifest=deployed_manifest,
        )
        if destination_kind == "absent":
            saved_kind = _manifest_kind(
                paths["saved"],
                original_manifest=original_manifest,
                deployed_manifest=deployed_manifest,
            )
            restore_source = paths["saved"]
            if saved_kind == "absent":
                restore_kind = _manifest_kind(
                    paths["restore"],
                    original_manifest=original_manifest,
                    deployed_manifest=deployed_manifest,
                )
                if restore_kind == "absent":
                    paths["root"].mkdir(parents=True, exist_ok=True)
                    shutil.copytree(
                        state / ORIGINAL_PACK_BACKUP, paths["restore"],
                    )
                    if shared._file_manifest(paths["restore"]) != original_manifest:
                        raise RuntimeError(
                            "The Grapeseed restore stage failed verification."
                        )
                elif restore_kind != "original":
                    raise RuntimeError(
                        "The Grapeseed restore stage contains unknown drift."
                    )
                restore_source = paths["restore"]
            elif saved_kind != "original":
                raise RuntimeError(
                    "The saved Grapeseed preimage contains unknown drift."
                )
            _set_journal_status(
                journal, journal_path, "original_pack_restore_pending",
                fault_injector,
            )
            replace(restore_source, destination)
            _hit(fault_injector, "original_pack_restored_live")
        elif destination_kind != "original":
            raise RuntimeError(
                "The Grapeseed original pack cannot be restored safely."
            )
    elif destination.exists():
        raise RuntimeError(
            "The Grapeseed pack should be absent after guarded rollback."
        )
    _set_journal_status(
        journal, journal_path, "original_pack_restored", fault_injector,
    )

    shape, _details = _assert_recovery_safe(game, state, patcher, journal)
    if shape != "pre_mutation":
        raise RuntimeError("The Grapeseed pre-mutation state did not restore.")
    result = _rollback_result(journal, _sha256_bytes(payload))
    _set_journal_status(
        journal, journal_path, "rollback_receipt_pending", fault_injector,
    )
    _durable_json(result, state / ROLLBACK_RECEIPT)
    _hit(fault_injector, "rollback_receipt_written_live")
    _set_journal_status(
        journal, journal_path, "rolled_back", fault_injector,
    )
    return result


def install_grapeseed_stock_reference_boot_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
    replace: Callable[[Path, Path], None] = os.replace,
    fault_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Install the execution-disabled Enhanced Grapeseed Phase-A bridge."""
    if confirmation != INSTALL_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {INSTALL_CONFIRMATION!r} is required."
        )
    game = shared._assert_enhanced_root(Path(gta_path))
    shared._assert_game_closed(process_probe)
    hosts = _native_map_hosts(game)
    if hosts:
        raise RuntimeError(
            "Remove every native ALLIN1 map host before Grapeseed Phase A: "
            + ", ".join(hosts)
        )
    tool = _tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    if not (game / "mods/update/update.rpf").is_file():
        raise RuntimeError("A complete mods/update/update.rpf must already exist.")

    state = _state_root(game, state_root)
    if state.exists():
        if (state / INSTALL_RECEIPT).is_file() and not (
            state / ROLLBACK_RECEIPT
        ).is_file():
            status = read_grapeseed_stock_reference_boot_canary_status(
                game, state_root=state, patcher=tool,
                process_probe=process_probe,
            )
            if status.get("healthy") is True:
                return _load_json(state / INSTALL_RECEIPT)
        raise RuntimeError(
            f"A Grapeseed Phase-A checkpoint already exists at {state}."
        )
    state.mkdir(parents=True)
    work = state / "work"
    work.mkdir()
    destination = _destination(game)
    backup = state / ORIGINAL_PACK_BACKUP
    deployment_backup = state / DEPLOYMENT_PACK_BACKUP
    original_dlclist = state / ORIGINAL_DLCLIST_BACKUP
    registered_dlclist = state / REGISTERED_DLCLIST_SNAPSHOT
    journal_path = state / JOURNAL
    transaction_id = uuid.uuid4().hex
    pack_existed = destination.exists()
    transaction_paths = _transaction_paths(game, transaction_id)
    journal: dict[str, Any] | None = None
    try:
        archive, topology, attestation = _build_archive(game, tool, work)
        original_payload = _current_dlclist(game, tool, original_dlclist)
        _durable_file(original_dlclist)
        _assert_clean_map_baseline(game, original_payload)
        davis_snapshot = _davis_bridge_snapshot(game, original_payload)
        original_manifest: dict[str, Any] = {}
        if pack_existed:
            if not destination.is_dir() or destination.is_symlink():
                raise RuntimeError("The existing Grapeseed bridge is not a directory.")
            original_manifest = shared._copy_tree_verified(destination, backup)
            for artifact in backup.rglob("*"):
                if artifact.is_file():
                    _durable_file(artifact)

        deployment_backup.mkdir()
        deployed_archive = deployment_backup / "dlc.rpf"
        shutil.copy2(archive, deployed_archive)
        _durable_file(deployed_archive)
        runtime_payload = _runtime_receipt(deployed_archive, attestation)
        runtime = deployment_backup / RUNTIME_RECEIPT_NAME
        _durable_json(runtime_payload, runtime)
        marker = deployment_backup / MARKER_NAME
        _write_marker(marker, runtime_payload)
        _durable_file(marker)
        deployed_manifest = shared._file_manifest(deployment_backup)
        if set(deployed_manifest) != {
            "dlc.rpf", MARKER_NAME, RUNTIME_RECEIPT_NAME,
        }:
            raise RuntimeError("The staged Grapeseed pack layout is not exact.")
        for name in ("content.xml", "setup2.xml"):
            target = state / name
            target.write_bytes((work / PACK_NAME / name).read_bytes())
            _durable_file(target)

        journal = {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": transaction_id,
            "status": "preparing",
            "phase": PHASE,
            "edition": "enhanced",
            "pack_existed": pack_existed,
            "original_dlclist_sha256": shared._sha256(original_dlclist),
            "original_pack_manifest": original_manifest,
            "deployed_pack_manifest": deployed_manifest,
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": shared._sha256(deployed_archive),
            "marker_sha256": shared._sha256(marker),
            "runtime_receipt_sha256": shared._sha256(runtime),
            "content_xml_sha256": shared._sha256(state / "content.xml"),
            "setup2_xml_sha256": shared._sha256(state / "setup2.xml"),
            "source_attestation": attestation,
            "davis_bridge_snapshot": davis_snapshot,
            "topology": topology,
        }
        _durable_json(journal, journal_path)
        _hit(fault_injector, "preparing")

        # Materialize through a private build name and publish the complete
        # same-volume tree with one atomic rename.  A power loss during copy
        # can leave only unregistered preparation debris, never a partial live
        # destination.
        destination.parent.mkdir(parents=True, exist_ok=True)
        if transaction_paths["root"].exists():
            raise RuntimeError("The Grapeseed transaction staging path already exists.")
        transaction_paths["root"].mkdir()
        shutil.copytree(deployment_backup, transaction_paths["stage_building"])
        if (
            shared._file_manifest(transaction_paths["stage_building"])
            != deployed_manifest
        ):
            raise RuntimeError("The same-volume Grapeseed deployment stage drifted.")
        for artifact in transaction_paths["stage_building"].rglob("*"):
            if artifact.is_file():
                _durable_file(artifact)
        replace(transaction_paths["stage_building"], transaction_paths["stage"])
        _set_journal_status(
            journal, journal_path, "prepared", fault_injector,
        )

        _set_journal_status(
            journal, journal_path, "old_pack_rename_pending", fault_injector,
        )
        if pack_existed:
            replace(destination, transaction_paths["saved"])
            _hit(fault_injector, "old_pack_saved_live")
        elif destination.exists():
            raise RuntimeError("The Grapeseed destination appeared during install.")
        _set_journal_status(
            journal, journal_path, "old_pack_saved", fault_injector,
        )

        _set_journal_status(
            journal, journal_path, "new_pack_rename_pending", fault_injector,
        )
        replace(transaction_paths["stage"], destination)
        _hit(fault_injector, "pack_deployed_live")
        _set_journal_status(
            journal, journal_path, "pack_deployed", fault_injector,
        )
        if shared._file_manifest(destination) != deployed_manifest:
            raise RuntimeError("The deployed Grapeseed Phase-A pack drifted.")

        _set_journal_status(
            journal, journal_path, "registration_pending", fault_injector,
        )
        shared._run_tool(
            tool,
            ["register-dlc", game, PACK_NAME],
            operation="Register metadata-only mpheist Grapeseed Phase-A bridge",
        )
        _hit(fault_injector, "registration_added_live")
        registered_payload = _current_dlclist(game, tool, registered_dlclist)
        _durable_file(registered_dlclist)
        _verify_registration_delta(original_payload, registered_payload)
        if _davis_bridge_snapshot(game, registered_payload) != davis_snapshot:
            raise RuntimeError("Grapeseed installation changed the Davis bridge.")
        journal["registered_dlclist_sha256"] = shared._sha256(
            registered_dlclist
        )
        _set_journal_status(
            journal, journal_path, "registered", fault_injector,
        )
        live_runtime = destination / RUNTIME_RECEIPT_NAME
        live_marker = destination / MARKER_NAME
        if shared._marker_fields(live_marker) != _marker_fields(runtime_payload):
            raise RuntimeError("The deployed Grapeseed Phase-A marker changed.")
        if _load_json(live_runtime) != runtime_payload:
            raise RuntimeError("The deployed Grapeseed Phase-A receipt changed.")
        receipt = {
            **_static_contract(status=INSTALL_STATUS),
            "archive_bytes": journal["archive_bytes"],
            "archive_sha256": journal["archive_sha256"],
            "source_attestation": attestation,
            "transaction_id": transaction_id,
            "topology": topology,
            "marker_sha256": journal["marker_sha256"],
            "runtime_receipt_sha256": journal["runtime_receipt_sha256"],
            "original_dlclist_sha256": journal["original_dlclist_sha256"],
            "registered_dlclist_sha256": journal["registered_dlclist_sha256"],
            "pack_existed": pack_existed,
            "original_pack_manifest": original_manifest,
            "deployed_pack_manifest": deployed_manifest,
            "davis_bridge_snapshot": davis_snapshot,
        }
        shutil.rmtree(work)
        _set_journal_status(
            journal, journal_path, "receipt_pending", fault_injector,
        )
        _durable_json(receipt, state / INSTALL_RECEIPT)
        _hit(fault_injector, "install_receipt_written_live")
        if not pack_existed:
            transaction_root = transaction_paths["root"]
            if (
                transaction_root.is_symlink()
                or not transaction_root.is_dir()
                or any(transaction_root.iterdir())
            ):
                raise RuntimeError(
                    "The empty Grapeseed transaction root could not be "
                    "verified for cleanup."
                )
            transaction_root.rmdir()
        _set_journal_status(
            journal, journal_path, "complete", fault_injector,
        )
        return receipt
    except Exception as install_error:
        if journal is not None:
            try:
                _guarded_transaction_rollback(
                    game, state, tool, journal,
                )
            except Exception as recovery_error:
                journal.update({
                    "status": "recovery_required",
                    "install_error": type(install_error).__name__,
                    "recovery_error": str(recovery_error),
                })
                _durable_json(journal, journal_path)
                raise RuntimeError(
                    "Grapeseed Phase-A install failed and exact rollback also "
                    f"failed: {recovery_error}"
                ) from install_error
        transaction_root = transaction_paths["root"]
        if transaction_root.exists():
            shutil.rmtree(transaction_root, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)
        raise


def rollback_grapeseed_stock_reference_boot_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
    replace: Callable[[Path, Path], None] = os.replace,
    fault_injector: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if confirmation != ROLLBACK_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {ROLLBACK_CONFIRMATION!r} is required."
        )
    game = shared._assert_enhanced_root(Path(gta_path))
    shared._assert_game_closed(process_probe)
    tool = _tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    state = _state_root(game, state_root)
    rollback_path = state / ROLLBACK_RECEIPT
    if rollback_path.is_file():
        payload = _load_json(rollback_path)
        status = read_grapeseed_stock_reference_boot_canary_status(
            game, state_root=state, patcher=tool,
            process_probe=process_probe,
        )
        if status.get("healthy") is not True:
            raise RuntimeError("The completed Grapeseed rollback drifted.")
        journal = _load_transaction_journal(state)
        if journal.get("status") != "rolled_back":
            journal["status"] = "rolled_back"
            _durable_json(journal, state / JOURNAL)
        return payload
    if not (state / JOURNAL).is_file():
        # The implementation publishes the first journal before its first live
        # rename.  Therefore a journal-less state directory is preparation
        # debris only.  Never infer ownership of or touch the destination.
        _payload, registration_count, retired_count = _registration_snapshot(
            game, tool,
        )
        if registration_count != 0 or retired_count != 0:
            raise RuntimeError(
                "The journal-less Grapeseed checkpoint is not a clean "
                "pre-mutation state; rollback refuses live changes."
            )
        shutil.rmtree(state)
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": None,
            "status": "discarded_pre_mutation_checkpoint",
            "restored_original_pack": False,
        }
    journal = _load_transaction_journal(state)
    return _guarded_transaction_rollback(
        game, state, tool, journal,
        replace=replace, fault_injector=fault_injector,
    )


def read_grapeseed_stock_reference_boot_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    game = shared._assert_enhanced_root(Path(gta_path))
    state = _state_root(game, state_root)
    running = bool(
        {name.casefold() for name in process_probe()}.intersection(
            {"gta5.exe", "gta5_enhanced.exe"}
        )
    )
    if not state.exists():
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "absent",
            "transaction_state": "clean",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": True,
        }
    tool = _tool_path(patcher)
    if not (state / JOURNAL).is_file():
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "pre_mutation",
            "transaction_state": "pre_mutation",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
            "recoverable": True,
            "checks": {"durable_journal": False, "live_mutation_possible": False},
            "recovery_action": (
                "Run the guarded Grapeseed Phase-A rollback to discard the "
                "pre-mutation checkpoint."
            ),
        }

    try:
        journal = _load_transaction_journal(state)
        shape, details, transaction_checks = _live_transaction_state(
            game, state, tool, journal,
        )
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "interrupted_drifted",
            "transaction_state": "interrupted_drifted",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
            "recoverable": False,
            "checks": {"transaction_journal": False},
            "detail": str(exc),
        }

    rollback_path = state / ROLLBACK_RECEIPT
    if rollback_path.is_file():
        try:
            rollback = _load_json(rollback_path)
        except RuntimeError:
            rollback = {}
        receipt_ok = (
            rollback.get("schema") == STATE_SCHEMA
            and rollback.get("canary_id") == CANARY_ID
            and rollback.get("transaction_id") == journal["transaction_id"]
            and rollback.get("status") == "rolled_back"
        )
        checks = {
            **transaction_checks,
            "rollback_receipt": receipt_ok,
            "registration_restored": details["registration_count"] == 0,
            "pack_restored": shape == "pre_mutation",
        }
        return {
            **rollback,
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "rolled_back",
            "journal_status": journal.get("status"),
            "transaction_state": "clean",
            "live_pack_state": shape,
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": all(checks.values()),
            "recoverable": all(checks.values()),
            "checks": checks,
            "live": details,
        }

    receipt_path = state / INSTALL_RECEIPT
    if not receipt_path.is_file() or journal.get("status") != "complete":
        recoverable = all(transaction_checks.values())
        pre_mutation = (
            shape == "pre_mutation"
            and journal.get("status") in {"preparing", "prepared"}
        )
        status = (
            "pre_mutation" if pre_mutation
            else "interrupted_recoverable" if recoverable
            else "interrupted_drifted"
        )
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": status,
            "journal_status": journal.get("status"),
            "transaction_state": status,
            "live_pack_state": shape,
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
            "recoverable": recoverable,
            "checks": transaction_checks,
            "live": details,
            "recovery_action": (
                "Run the guarded Grapeseed Phase-A rollback while GTA is closed."
                if recoverable else None
            ),
        }

    try:
        checkpoint = _load_json(receipt_path)
    except RuntimeError as exc:
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "interrupted_drifted",
            "transaction_state": "interrupted_drifted",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": False,
            "recoverable": all(transaction_checks.values()),
            "checks": {**transaction_checks, "install_receipt": False},
            "detail": str(exc),
        }
    destination = _destination(game)
    archive = destination / "dlc.rpf"
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    runtime_payload: dict[str, Any] | None = None
    try:
        runtime_payload = _load_json(runtime)
    except RuntimeError:
        pass
    archive_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and shared._sha256(archive) == checkpoint.get("archive_sha256")
    )
    marker_ok = (
        archive_ok and marker.is_file()
        and shared._sha256(marker) == checkpoint.get("marker_sha256")
        and runtime_payload is not None
        and shared._marker_fields(marker) == _marker_fields(runtime_payload)
    )
    expected_runtime = (
        _runtime_receipt(archive, checkpoint.get("source_attestation"))
        if archive_ok else None
    )
    runtime_ok = (
        runtime_payload == expected_runtime
        and runtime.is_file()
        and shared._sha256(runtime) == checkpoint.get("runtime_receipt_sha256")
    )
    dlclist_ok = False
    davis_unaffected = False
    registration_count: int | None = None
    if tool.is_file() and (game / "mods/update/update.rpf").is_file():
        try:
            payload, registration_count, retired_count = _registration_snapshot(
                game, tool,
            )
            dlclist_ok = registration_count == 1 and retired_count == 0
            # Davis may be installed, promoted, or removed later.  Grapeseed
            # owns neither its registration nor its files; only reject a
            # duplicate Davis registration or a malformed Davis pack path.
            davis_count = _count_entry(payload, DAVIS_PACK_ENTRY)
            davis_root = (
                game / "mods/update/x64/dlcpacks" / DAVIS_PACK_NAME
            )
            davis_unaffected = (
                davis_count in {0, 1}
                and (not davis_root.exists() or davis_root.is_dir())
            )
        except (OSError, RuntimeError):
            pass
    files = (
        {path.name for path in destination.iterdir() if path.is_file()}
        if destination.is_dir() else set()
    )
    topology_ok = False
    try:
        topology = inspect_stock_bridge_topology(state)
        topology_ok = all(topology["checks"].values())
    except (OSError, RuntimeError):
        pass
    checks = {
        "transaction_journal": all(transaction_checks.values()),
        "transaction_live_state": shape == "installed",
        "install_receipt": checkpoint.get("transaction_id")
        == journal["transaction_id"],
        "archive": archive_ok,
        "marker": marker_ok,
        "runtime_receipt": runtime_ok,
        "dlclist_registration": dlclist_ok,
        "exact_zero_payload_files": files
        == {"dlc.rpf", MARKER_NAME, RUNTIME_RECEIPT_NAME},
        "exact_metadata_topology": topology_ok,
        "source_attestation_current": _source_attestation_current(
            game, checkpoint.get("source_attestation"),
        ),
        "retired_allin1_maps_absent": not _old_pack_paths(game),
        "davis_bridge_unaffected": davis_unaffected,
        "native_map_host_absent": not _native_map_hosts(game),
    }
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": checkpoint.get("status", INSTALL_STATUS),
        "journal_status": journal.get("status"),
        "transaction_state": "clean" if all(checks.values()) else "drifted",
        "live_pack_state": shape,
        "phase": PHASE,
        "edition": "enhanced",
        "game_running": running,
        "healthy": all(checks.values()),
        "checks": checks,
        "registration_count": registration_count,
        "pack_name": PACK_NAME,
        "device_name": DEVICE_NAME,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "activation": ACTIVATION,
        "runtime_receipt": runtime_payload,
        "live": details,
    }
