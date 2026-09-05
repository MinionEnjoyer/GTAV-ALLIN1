"""Phase-A boot canary for Rockstar's stock mptuner map metadata.

The canary contains no Rockstar assets and authorizes no runtime action.  Its
only purpose is to prove that Enhanced can boot with a tiny DLC whose dormant
group references the already-registered ``MPTUNER_MAP_UPDATE`` changeset.
Activation is deliberately a separate, future transaction.
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


CANARY_ID = "davis-enhanced-stock-reference-boot-v4"
INSTALL_CONFIRMATION = "INSTALL_DAVIS_ENHANCED_STOCK_REFERENCE_BOOT_CANARY_V4"
ROLLBACK_CONFIRMATION = "ROLLBACK_DAVIS_ENHANCED_STOCK_REFERENCE_BOOT_CANARY_V4"
STATE_SCHEMA = 4
STATE_DIRECTORY = "DavisStockReferenceBootV4"

PACK_NAME = "allin1_mptuner_bridge"
DEVICE_NAME = "dlc_allin1_mptuner_bridge"
PACK_ENTRY = f"dlcpacks:/{PACK_NAME}/"
MARKER_NAME = f"{PACK_NAME}.active"
RUNTIME_RECEIPT_NAME = f"{PACK_NAME}.runtime.json"
LAYOUT = "stock-reference-v1-metadata-only"
RUNTIME_CONTRACT = "allin1-stock-mptuner-davis-boot-v1"
PHASE = "phase-a-boot-only"
INSTALL_STATUS = "installed_boot_only_pending"
RUNTIME_STATUS = "verified"
ARCHIVE_REGISTRATION = "metadata-only"
ACTIVATION = "disabled-phase-a-boot-only"
PACKAGE_ID = "allin1.online-content"

STARTUP_CHANGESET = "ALLIN1_MPTUNER_BRIDGE_AUTOGEN"
DORMANT_GROUP = "ALLIN1_STOCK_MPTUNER_DAVIS_V1"
STOCK_CHANGESET = "MPTUNER_MAP_UPDATE"
STOCK_STARTUP_CHANGESET = "MPTUNER_AUTOGEN"
STOCK_DEVICE = "dlc_mpTuner"
STOCK_PROXY = f"{STOCK_DEVICE}:/common/data/interiorProxies.meta"
STOCK_ARCHIVE_RELATIVE = Path("update/x64/dlcpacks/mptuner/dlc.rpf")
OLD_PACK_NAME = "allin1_maps"
OLD_PACK_ENTRY = f"dlcpacks:/{OLD_PACK_NAME}/"

_EXPECTED_STOCK_GROUP_MAP = (
    "MPTUNER_MAP_UPDATE",
    "MPTUNER_MAP_UPDATE_NAVMESH_ONLY",
)
_EXPECTED_MAP_FILES = (
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_int_01_tr.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_int_02_tr.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/dlc_int_04_tr.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/interiors/int_placement_tr.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "dt1_17_tuner_additions.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "id2_18_tuner_additions.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "sc1_02_tuner_additions.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "sc1_28_tuner_additions.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "ss1_05_tuner_additions.rpf",
    f"{STOCK_DEVICE}:/%PLATFORM%/levels/gta5/_citye/tuner_additions/"
    "tuner_additions_metadata.rpf",
)


def _state_root(gta_path: Path, override: Path | None = None) -> Path:
    if override is not None:
        return override.resolve()
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
    """Find every ASI whose name identifies it as a native map host."""
    found = set(shared._native_hosts(game))
    for parent in (game, game / "scripts"):
        if not parent.is_dir():
            continue
        for path in parent.glob("*.asi"):
            if "maphost" in path.stem.casefold():
                found.add(path.relative_to(game).as_posix())
    return sorted(found)


def _effective_mptuner_archive(game: Path) -> tuple[Path, str]:
    override = game / "mods" / STOCK_ARCHIVE_RELATIVE
    stock = game / STOCK_ARCHIVE_RELATIVE
    if override.is_file():
        return override, "mods"
    if stock.is_file():
        return stock, "stock"
    raise FileNotFoundError(
        "The effective Enhanced mptuner DLC archive is missing from both "
        f"the mods and stock roots: {STOCK_ARCHIVE_RELATIVE.as_posix()}"
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _values(item: etree._Element, path: str) -> list[str]:
    return [
        value.strip() for value in item.xpath(path)
        if isinstance(value, str) and value.strip()
    ]


def _flag(item: etree._Element, name: str) -> bool:
    return item.xpath(f"string({name}/@value)").strip().casefold() == "true"


def _one_change(
    content: etree._ElementTree, name: str,
) -> etree._Element:
    matches = [
        item for item in content.xpath("//contentChangeSets/Item[changeSetName]")
        if item.xpath("string(changeSetName)").strip().casefold()
        == name.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Effective mptuner metadata must define exactly one {name}."
        )
    return matches[0]


def inspect_effective_mptuner_metadata(
    content_path: Path,
    setup_path: Path,
    *,
    archive_path: Path,
    archive_source: str,
    game: Path,
) -> dict[str, Any]:
    """Attest the exact stock route and its startup proxy registration."""
    try:
        content = etree.parse(str(content_path))
        setup = etree.parse(str(setup_path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise RuntimeError(f"Effective mptuner metadata is unreadable: {exc}") from exc

    device = setup.xpath("string(/SSetupData/deviceName)").strip()
    name_hash = setup.xpath("string(/SSetupData/nameHash)").strip()
    data_file = setup.xpath("string(/SSetupData/datFile)").strip()
    pack_type = setup.xpath("string(/SSetupData/type)").strip()
    try:
        setup_order = int(setup.xpath("string(/SSetupData/order/@value)"))
    except ValueError as exc:
        raise RuntimeError("Effective mptuner setup order is invalid.") from exc
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
        or name_hash != "mpTuner"
        or data_file.casefold() != "content.xml"
        or pack_type != "EXTRACONTENT_COMPAT_PACK"
        or setup_order < 0
        or setup_order >= 72
    ):
        raise RuntimeError(
            "Effective mptuner setup identity changed; an audited contract "
            "update is required."
        )
    if STOCK_STARTUP_CHANGESET not in group_startup:
        raise RuntimeError(
            "Effective mptuner GROUP_STARTUP no longer registers MPTUNER_AUTOGEN."
        )
    if tuple(group_map) != _EXPECTED_STOCK_GROUP_MAP:
        raise RuntimeError(
            "Effective mptuner GROUP_MAP membership changed; an audited "
            "contract update is required."
        )

    startup = _one_change(content, STOCK_STARTUP_CHANGESET)
    startup_files = _values(startup, "filesToEnable/Item/text()")
    if STOCK_PROXY not in startup_files:
        raise RuntimeError(
            "MPTUNER_AUTOGEN no longer enables the stock interior proxy file."
        )
    proxy_items = [
        item for item in content.xpath("//dataFiles/Item")
        if item.xpath("string(filename)").strip() == STOCK_PROXY
    ]
    if len(proxy_items) != 1:
        raise RuntimeError(
            "Effective mptuner content does not register one interior proxy file."
        )
    proxy_item = proxy_items[0]
    if (
        proxy_item.xpath("string(fileType)").strip()
        != "INTERIOR_PROXY_ORDER_FILE"
        or proxy_item.xpath("string(disabled/@value)").strip().casefold()
        != "true"
    ):
        raise RuntimeError("The stock mptuner interior proxy contract changed.")

    change = _one_change(content, STOCK_CHANGESET)
    map_items = change.xpath("mapChangeSetData/Item")
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
        "files_to_invalidate": [],
        "files_to_disable": [],
        "files_to_enable": list(_EXPECTED_MAP_FILES),
        "requires_loading_screen": True,
        "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
        "use_cache_loader": True,
    }
    if len(map_items) != 1 or semantics != expected_semantics:
        raise RuntimeError(
            "Effective MPTUNER_MAP_UPDATE semantics changed; Phase A refuses "
            "to register an unaudited reference."
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
        "pack": "mptuner",
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
    etree.SubElement(root, "order").set("value", "72")
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
        raise RuntimeError(f"Stock bridge metadata is unreadable: {exc}") from exc
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
    }
    data_files = content.xpath("//dataFiles/Item")
    changesets = _values(content, "//contentChangeSets/Item/changeSetName/text()")
    groups = _values(setup, "//contentChangeSetGroups/Item/NameHash/text()")
    startup_refs = _values(
        setup,
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()",
    )
    dormant_refs = _values(
        setup,
        "//contentChangeSetGroups/Item[NameHash='"
        + DORMANT_GROUP
        + "']/ContentChangeSets/Item/text()",
    )
    base = _one_change(content, STARTUP_CHANGESET)
    checks = {
        "metadata_files_only": files == {"content.xml", "setup2.xml"},
        "zero_data_files": data_files == [],
        "one_inert_local_changeset": changesets == [STARTUP_CHANGESET],
        "inert_startup_has_no_map_routes": base.xpath("mapChangeSetData/Item") == [],
        "inert_startup_enables_nothing": _values(base, "filesToEnable/Item/text()") == [],
        "inert_startup_invalidates_nothing": _values(base, "filesToInvalidate/Item/text()") == [],
        "inert_startup_disables_nothing": _values(base, "filesToDisable/Item/text()") == [],
        "inert_startup_no_loading_screen": not _flag(base, "requiresLoadingScreen"),
        "exact_groups": groups == ["GROUP_STARTUP", DORMANT_GROUP],
        "exact_startup_reference": startup_refs == [STARTUP_CHANGESET],
        "exact_dormant_stock_reference": dormant_refs == [STOCK_CHANGESET],
        "device_matches": setup.xpath("string(/SSetupData/deviceName)").strip()
        == DEVICE_NAME,
        "name_matches": setup.xpath("string(/SSetupData/nameHash)").strip()
        == PACK_NAME,
        "order_after_mptuner": setup.xpath("string(/SSetupData/order/@value)")
        == "72",
        "not_global_map_group": not any(
            value in {"GROUP_MAP", "GROUP_MAP_SP"} for value in groups
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise RuntimeError("Stock bridge topology failed closed: " + failed)
    return {
        "checks": checks,
        "asset_count": 0,
        "data_file_count": 0,
        "startup_changeset": STARTUP_CHANGESET,
        "groups": ["GROUP_STARTUP", DORMANT_GROUP],
        "dormant_group_count": 1,
        "stock_changesets": [STOCK_CHANGESET],
    }


def _extract_source_attestation(
    game: Path, patcher: Path, work: Path,
) -> dict[str, Any]:
    archive, source = _effective_mptuner_archive(game)
    content = work / "effective-mptuner-content.xml"
    setup = work / "effective-mptuner-setup2.xml"
    shared._run_tool(
        patcher,
        ["extract-entry", game, archive, "content.xml", content],
        operation="Read effective Enhanced mptuner content.xml",
    )
    shared._run_tool(
        patcher,
        ["extract-entry", game, archive, "setup2.xml", setup],
        operation="Read effective Enhanced mptuner setup2.xml",
    )
    if not content.is_file() or not setup.is_file():
        raise RuntimeError("RpfPatcher returned incomplete mptuner metadata.")
    return inspect_effective_mptuner_metadata(
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
        operation="Build stock mptuner Phase-A bridge",
        timeout=300,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("The stock bridge build produced no DLC archive.")
    packaged = work / "packaged"
    packaged.mkdir()
    for name in ("content.xml", "setup2.xml"):
        extracted = packaged / name
        shared._run_tool(
            patcher,
            ["extract-entry", game, output, name, extracted],
            operation=f"Verify packaged stock bridge {name}",
        )
        if extracted.read_bytes() != (staging / name).read_bytes():
            raise RuntimeError(f"Packaged stock bridge {name} changed.")
    inspect_stock_bridge_topology(packaged)
    index_path = work / "packaged-index.json"
    shared._run_tool(
        patcher,
        ["index-json", game, output, index_path],
        operation="Index packaged stock bridge",
    )
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The packaged stock bridge index is unreadable.") from exc
    entries = index.get("entries") if isinstance(index, dict) else None
    indexed_paths = (
        [item.get("path") for item in entries if isinstance(item, dict)]
        if isinstance(entries, list) else None
    )
    if (
        not isinstance(index, dict)
        or index.get("schema_version") != 1
        or not isinstance(indexed_paths, list)
        or not all(isinstance(value, str) for value in indexed_paths)
        or sorted(indexed_paths) != ["content.xml", "setup2.xml"]
        or index.get("warnings") != []
    ):
        raise RuntimeError(
            "The packaged stock bridge is not the exact two-metadata-entry RPF."
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
        "asset_count": 0,
        "data_file_count": 0,
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": 1,
        "declared_groups": ["GROUP_STARTUP", DORMANT_GROUP],
        "stock_changesets": [STOCK_CHANGESET],
        "groups": [{
            "property": "davis",
            "group": DORMANT_GROUP,
            "changesets": [STOCK_CHANGESET],
            "activation_enabled": False,
        }],
        "native_group_execution_enabled": False,
        "runtime_ipl_requests_enabled": False,
        "gameconfig_changed": False,
        "native_host_installed": False,
    }


def _static_runtime_receipt() -> dict[str, Any]:
    return _static_contract(status=RUNTIME_STATUS)


def _static_checkpoint() -> dict[str, Any]:
    return _static_contract(status=INSTALL_STATUS)


def _runtime_receipt(
    archive: Path, attestation: dict[str, Any],
) -> dict[str, Any]:
    return {
        **_static_runtime_receipt(),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": shared._sha256(archive),
        "source_attestation": attestation,
    }


def _write_marker(path: Path, archive: Path) -> None:
    fields = {
        "canary_id": CANARY_ID,
        "schema": str(STATE_SCHEMA),
        "status": INSTALL_STATUS,
        "phase": PHASE,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": ARCHIVE_REGISTRATION,
        "activation": ACTIVATION,
        "asset_count": "0",
        "data_file_count": "0",
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": "1",
        "declared_groups": f"GROUP_STARTUP,{DORMANT_GROUP}",
        "stock_changesets": STOCK_CHANGESET,
        "native_group_execution_enabled": "false",
        "runtime_ipl_requests_enabled": "false",
        "gameconfig_changed": "false",
        "native_host_installed": "false",
        "receipt": RUNTIME_RECEIPT_NAME,
        "archive_bytes": str(archive.stat().st_size),
        "archive_sha256": shared._sha256(archive),
    }
    shared._write_text_atomic(
        "ALLIN1 stock mptuner Phase-A metadata bridge; activation disabled.\n"
        + "".join(f"{key}={value}\n" for key, value in fields.items()),
        path,
    )


def _expected_marker(archive: Path) -> dict[str, str]:
    return {
        "canary_id": CANARY_ID,
        "schema": str(STATE_SCHEMA),
        "status": INSTALL_STATUS,
        "phase": PHASE,
        "layout": LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": ARCHIVE_REGISTRATION,
        "activation": ACTIVATION,
        "asset_count": "0",
        "data_file_count": "0",
        "startup_changeset": STARTUP_CHANGESET,
        "dormant_group_count": "1",
        "declared_groups": f"GROUP_STARTUP,{DORMANT_GROUP}",
        "stock_changesets": STOCK_CHANGESET,
        "native_group_execution_enabled": "false",
        "runtime_ipl_requests_enabled": "false",
        "gameconfig_changed": "false",
        "native_host_installed": "false",
        "receipt": RUNTIME_RECEIPT_NAME,
        "archive_bytes": str(archive.stat().st_size),
        "archive_sha256": shared._sha256(archive),
    }


def _runtime_matches(payload: Any, checkpoint: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    expected = {
        **_static_runtime_receipt(),
        "archive_bytes": checkpoint.get("archive_bytes"),
        "archive_sha256": checkpoint.get("archive_sha256"),
        "source_attestation": checkpoint.get("source_attestation"),
    }
    return payload == expected


def _normalized(value: str) -> str:
    return value.rstrip("/").casefold()


def _count_entry(payload: bytes, entry: str) -> int:
    expected = _normalized(entry)
    return sum(_normalized(item) == expected for item in shared._dlclist_items(payload))


def _verify_registration_delta(before: bytes, after: bytes) -> None:
    before_items = shared._dlclist_items(before)
    after_items = shared._dlclist_items(after)
    expected = _normalized(PACK_ENTRY)
    if any(_normalized(item) == expected for item in before_items):
        raise RuntimeError("The stock bridge was already registered.")
    without_bridge = [item for item in after_items if _normalized(item) != expected]
    if _count_entry(after, PACK_ENTRY) != 1 or without_bridge != before_items:
        raise RuntimeError(
            "DLC registration changed entries outside the exact stock bridge delta."
        )


def _verify_unregistration_delta(before: bytes, after: bytes) -> None:
    """Prove that rollback removed only the Davis bridge registration."""
    before_items = shared._dlclist_items(before)
    after_items = shared._dlclist_items(after)
    expected = _normalized(PACK_ENTRY)
    if _count_entry(before, PACK_ENTRY) != 1:
        raise RuntimeError("The Davis bridge registration is not exact.")
    preserved = [item for item in before_items if _normalized(item) != expected]
    if _count_entry(after, PACK_ENTRY) != 0 or after_items != preserved:
        raise RuntimeError(
            "DLC rollback changed entries outside the exact Davis bridge delta."
        )


def _registration_snapshot(
    game: Path, patcher: Path,
) -> tuple[bytes, int, int, int]:
    """Read the live list once and report only Davis-owned invariants."""
    mods_archive = game / "mods/update/update.rpf"
    with tempfile.TemporaryDirectory(
        prefix="allin1-stock-bridge-registration-"
    ) as tmp:
        current = Path(tmp) / "dlclist.xml"
        payload = shared._extract_dlclist(
            patcher, game, mods_archive, current,
        )
    return (
        payload,
        _count_entry(payload, PACK_ENTRY),
        _count_entry(payload, OLD_PACK_ENTRY),
        _count_entry(payload, "dlcpacks:/mptuner/"),
    )


def _old_pack_paths(game: Path) -> list[str]:
    found = []
    for base in ("mods/update", "update"):
        path = game / base / "x64/dlcpacks" / OLD_PACK_NAME
        if path.exists():
            found.append(path.relative_to(game).as_posix())
    return found


def _assert_clean_map_baseline(game: Path, dlclist: bytes) -> None:
    old_paths = _old_pack_paths(game)
    if old_paths:
        raise RuntimeError(
            "The retired allin1_maps pack is still present: " + ", ".join(old_paths)
        )
    if _count_entry(dlclist, OLD_PACK_ENTRY):
        raise RuntimeError(
            "The retired allin1_maps pack is still registered in dlclist.xml."
        )
    if _count_entry(dlclist, PACK_ENTRY):
        raise RuntimeError(
            "The stock bridge is already registered; roll back its checkpoint first."
        )
    if _count_entry(dlclist, "dlcpacks:/mptuner/") != 1:
        raise RuntimeError(
            "The attested stock mptuner DLC must be registered exactly once."
        )


def _load_checkpoint(state: Path) -> dict[str, Any]:
    for name in ("install-receipt.json", "journal.json"):
        path = state / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("schema") == STATE_SCHEMA
            and payload.get("canary_id") == CANARY_ID
        ):
            return payload
    raise FileNotFoundError("No valid stock-reference boot checkpoint exists.")


def _supersede_verified_rollback(
    game: Path,
    state: Path,
    patcher: Path,
) -> Path:
    """Move one fully verified completed checkpoint aside for a new run."""
    if not (state / "rollback-receipt.json").is_file():
        raise RuntimeError(
            f"A Phase-A checkpoint exists at {state}; inspect or roll it back first."
        )
    try:
        payload, checks = _verify_completed_rollback(game, state, patcher)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "The prior Phase-A rollback cannot be verified and will not be "
            "superseded."
        ) from exc
    if not all(checks.values()):
        failed = ", ".join(name for name, ok in checks.items() if not ok)
        raise RuntimeError(
            "The prior Phase-A rollback will not be superseded because its "
            f"live baseline failed: {failed}"
        )
    transaction = str(payload.get("transaction_id", "")).strip()
    if len(transaction) != 32 or not all(
        character in "0123456789abcdef" for character in transaction
    ):
        raise RuntimeError(
            "The verified rollback has no safe transaction identity."
        )
    archive = state.with_name(state.name + ".rolled-back-" + transaction[:12])
    if archive.exists():
        raise RuntimeError(
            f"The prior rollback archive already exists: {archive}"
        )
    state.rename(archive)
    return archive


def install_davis_stock_reference_boot_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    """Install the metadata-only, execution-disabled Phase-A bridge."""
    if confirmation != INSTALL_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {INSTALL_CONFIRMATION!r} is required."
        )
    game = shared._assert_enhanced_root(Path(gta_path))
    shared._assert_game_closed(process_probe)
    hosts = _native_map_hosts(game)
    if hosts:
        raise RuntimeError(
            "Remove every native ALLIN1 map host before Phase A: "
            + ", ".join(hosts)
        )
    tool = _tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    mods_archive = game / "mods/update/update.rpf"
    if not mods_archive.is_file():
        raise RuntimeError("A complete mods/update/update.rpf must already exist.")

    state = _state_root(game, state_root)
    if state.exists():
        _supersede_verified_rollback(game, state, tool)
    state.mkdir(parents=True)
    work = state / "work"
    work.mkdir()
    destination = _destination(game)
    backup = state / "original-pack"
    original_dlclist = state / "original-dlclist.xml"
    registered_dlclist = state / "registered-dlclist.xml"
    journal_path = state / "journal.json"
    receipt_path = state / "install-receipt.json"
    transaction_id = uuid.uuid4().hex
    pack_existed = destination.exists()
    journal: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": transaction_id,
        "status": "building",
        "phase": PHASE,
        "edition": "enhanced",
        "pack_existed": pack_existed,
        "gameconfig_changed": False,
        "native_host_installed": False,
        "native_group_execution_enabled": False,
        "runtime_ipl_requests_enabled": False,
    }
    shared._write_json_atomic(journal, journal_path)

    mutated = False
    try:
        archive, topology, attestation = _build_archive(game, tool, work)
        original_payload = shared._extract_dlclist(
            tool, game, mods_archive, original_dlclist,
        )
        _assert_clean_map_baseline(game, original_payload)
        original_manifest: dict[str, Any] = {}
        if pack_existed:
            if not destination.is_dir():
                raise RuntimeError("The existing stock bridge path is not a directory.")
            original_manifest = shared._copy_tree_verified(destination, backup)
        journal.update({
            "status": "ready_to_mutate",
            "original_dlclist_sha256": shared._sha256(original_dlclist),
            "original_pack_manifest": original_manifest,
            "source_attestation": attestation,
        })
        shared._write_json_atomic(journal, journal_path)

        journal["status"] = "mutation_started"
        shared._write_json_atomic(journal, journal_path)
        mutated = True
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        deployed_archive = destination / "dlc.rpf"
        shutil.copy2(archive, deployed_archive)
        runtime = destination / RUNTIME_RECEIPT_NAME
        shared._write_json_atomic(
            _runtime_receipt(deployed_archive, attestation), runtime,
        )
        marker = destination / MARKER_NAME
        _write_marker(marker, deployed_archive)
        journal.update({
            "status": "deployed",
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": shared._sha256(deployed_archive),
            "marker_sha256": shared._sha256(marker),
            "runtime_receipt_sha256": shared._sha256(runtime),
        })
        shared._write_json_atomic(journal, journal_path)

        shared._run_tool(
            tool,
            ["register-dlc", game, PACK_NAME],
            operation="Register metadata-only stock mptuner Phase-A bridge",
        )
        registered_payload = shared._extract_dlclist(
            tool, game, mods_archive, registered_dlclist,
        )
        _verify_registration_delta(original_payload, registered_payload)
        journal.update({
            "status": "registered",
            "registered_dlclist_sha256": shared._sha256(registered_dlclist),
        })
        shared._write_json_atomic(journal, journal_path)
        if shared._marker_fields(marker) != _expected_marker(deployed_archive):
            raise RuntimeError("The deployed Phase-A marker does not match.")
        runtime_payload = json.loads(runtime.read_text(encoding="utf-8"))
        provisional = {
            **_static_runtime_receipt(),
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": shared._sha256(deployed_archive),
            "source_attestation": attestation,
        }
        if runtime_payload != provisional:
            raise RuntimeError("The deployed Phase-A receipt does not match.")

        for name in ("content.xml", "setup2.xml"):
            (state / name).write_bytes((work / PACK_NAME / name).read_bytes())
        receipt = {
            **_static_checkpoint(),
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": shared._sha256(deployed_archive),
            "source_attestation": attestation,
            "transaction_id": transaction_id,
            "topology": topology,
            "marker_sha256": shared._sha256(marker),
            "runtime_receipt_sha256": shared._sha256(runtime),
            "original_dlclist_sha256": shared._sha256(original_dlclist),
            "registered_dlclist_sha256": shared._sha256(registered_dlclist),
            "pack_existed": pack_existed,
            "original_pack_manifest": original_manifest,
        }
        shutil.rmtree(work)
        shared._write_json_atomic(receipt, receipt_path)
        return receipt
    except Exception as install_error:
        if mutated:
            try:
                _restore_from_checkpoint(game, state, tool, strict_current=False)
            except Exception as recovery_error:
                journal.update({
                    "status": "recovery_required",
                    "install_error": type(install_error).__name__,
                    "recovery_error": str(recovery_error),
                })
                shared._write_json_atomic(journal, journal_path)
                raise RuntimeError(
                    "Phase-A installation failed and its automatic rollback "
                    f"also failed: {recovery_error}"
                ) from install_error
            else:
                shutil.rmtree(state)
        else:
            # A source/preflight refusal made no game mutation and must not
            # strand an unusable checkpoint that blocks the corrected retry.
            shutil.rmtree(state, ignore_errors=True)
        raise


def _source_attestation_current(game: Path, recorded: Any) -> bool:
    if not isinstance(recorded, dict):
        return False
    try:
        archive, source = _effective_mptuner_archive(game)
        relative = archive.relative_to(game).as_posix()
        stat = archive.stat()
        return (
            recorded.get("source") == source
            and recorded.get("path") == relative
            and recorded.get("size") == stat.st_size
            and recorded.get("mtime_ns") == stat.st_mtime_ns
            and recorded.get("archive_sha256") == shared._sha256(archive)
        )
    except (FileNotFoundError, OSError, ValueError):
        return False


def _restore_from_checkpoint(
    game: Path, state: Path, patcher: Path, *, strict_current: bool,
) -> tuple[dict[str, Any], str]:
    checkpoint = _load_checkpoint(state)
    destination = _destination(game)
    mods_archive = game / "mods/update/update.rpf"
    original = state / "original-dlclist.xml"
    if not mods_archive.is_file() or not original.is_file():
        raise RuntimeError("The exact Phase-A rollback checkpoint is incomplete.")
    if shared._sha256(original) != checkpoint.get("original_dlclist_sha256"):
        raise RuntimeError("The original Phase-A dlclist backup was tampered with.")

    pack_existed = bool(checkpoint.get("pack_existed"))
    expected_manifest = checkpoint.get("original_pack_manifest")
    backup = state / "original-pack"
    if pack_existed:
        if (
            not isinstance(expected_manifest, dict)
            or not backup.is_dir()
            or shared._file_manifest(backup) != expected_manifest
        ):
            raise RuntimeError(
                "The original stock bridge backup is missing or corrupt."
            )
    elif expected_manifest != {}:
        raise RuntimeError("The Phase-A original-pack checkpoint is inconsistent.")

    archive = destination / "dlc.rpf"
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    deployed_pack_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and shared._sha256(archive) == checkpoint.get("archive_sha256")
        and marker.is_file()
        and shared._sha256(marker) == checkpoint.get("marker_sha256")
        and runtime.is_file()
        and shared._sha256(runtime) == checkpoint.get("runtime_receipt_sha256")
    )
    try:
        original_pack_live = (
            destination.is_dir()
            and shared._file_manifest(destination) == expected_manifest
            if pack_existed else not destination.exists()
        )
    except (OSError, RuntimeError):
        original_pack_live = False

    current_payload, registration_count, retired_count, mptuner_count = (
        _registration_snapshot(game, patcher)
    )
    if retired_count != 0:
        raise RuntimeError(
            "Phase-A rollback refuses while the retired allin1_maps pack is "
            "registered."
        )
    if mptuner_count != 1:
        raise RuntimeError(
            "Phase-A rollback requires the stock mptuner registration exactly once."
        )
    if registration_count not in {0, 1}:
        raise RuntimeError("The Davis bridge registration count is not recoverable.")

    status = checkpoint.get("status")
    if strict_current and status == "mutation_started":
        raise RuntimeError(
            "Phase-A stopped during its first mutation; explicit recovery "
            "requires manual review of the destination pack."
        )
    if strict_current and status in {
        INSTALL_STATUS, "deployed", "registered", "recovery_required",
    }:
        # A prior rollback attempt may already have removed our registration
        # or restored the original pack.  Accept only those known partial
        # shapes so the guarded operation can be resumed without touching an
        # unrelated DLC-list entry.
        known_pack_shape = deployed_pack_ok or original_pack_live or (
            registration_count == 0 and not destination.exists()
        )
        if not known_pack_shape:
            raise RuntimeError(
                "The active Phase-A bridge changed after installation; "
                "rollback refuses to overwrite unreviewed files."
            )
        if registration_count == 1 and not deployed_pack_ok:
            raise RuntimeError(
                "The registered Phase-A pack is not the attested Davis bridge."
            )

    if registration_count == 1:
        shared._run_tool(
            patcher,
            ["unregister-dlc", game, PACK_NAME],
            operation="Unregister only the Davis Phase-A bridge",
        )
        (
            restored_payload,
            restored_registration_count,
            restored_retired_count,
            restored_mptuner_count,
        ) = _registration_snapshot(game, patcher)
        _verify_unregistration_delta(current_payload, restored_payload)
    else:
        restored_payload = current_payload
        restored_registration_count = registration_count
        restored_retired_count = retired_count
        restored_mptuner_count = mptuner_count
    if (
        restored_registration_count != 0
        or restored_retired_count != 0
        or restored_mptuner_count != 1
    ):
        raise RuntimeError("The Davis registration removal did not verify.")

    if not original_pack_live:
        if destination.exists():
            shutil.rmtree(destination)
        if pack_existed:
            shutil.copytree(backup, destination)
            if shared._file_manifest(destination) != expected_manifest:
                raise RuntimeError("The restored stock bridge failed verification.")
    return checkpoint, _sha256_bytes(restored_payload)


def rollback_davis_stock_reference_boot_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    if confirmation != ROLLBACK_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {ROLLBACK_CONFIRMATION!r} is required."
        )
    game = shared._assert_enhanced_root(Path(gta_path))
    shared._assert_game_closed(process_probe)
    state = _state_root(game, state_root)
    complete = state / "rollback-receipt.json"
    if complete.is_file():
        tool = _tool_path(patcher)
        payload, checks = _verify_completed_rollback(game, state, tool)
        if not all(checks.values()):
            failed = ", ".join(name for name, ok in checks.items() if not ok)
            raise RuntimeError(
                "The completed Phase-A rollback no longer matches the live "
                f"baseline: {failed}"
            )
        return payload
    tool = _tool_path(patcher)
    checkpoint, restored_dlclist_sha256 = _restore_from_checkpoint(
        game, state, tool, strict_current=True,
    )
    (state / "install-receipt.json").unlink(missing_ok=True)
    result = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": checkpoint.get("transaction_id"),
        "status": "rolled_back",
        "restored_dlclist_sha256": restored_dlclist_sha256,
        "restored_original_pack": bool(checkpoint.get("pack_existed")),
    }
    shared._write_json_atomic(result, complete)
    return result


def _verify_completed_rollback(
    game: Path, state: Path, patcher: Path,
) -> tuple[dict[str, Any], dict[str, bool]]:
    """Validate an idempotent rollback receipt against the live baseline."""
    checkpoint = _load_checkpoint(state)
    path = state / "rollback-receipt.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    expected_identity = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": checkpoint.get("transaction_id"),
        "status": "rolled_back",
        "restored_original_pack": bool(checkpoint.get("pack_existed")),
    }
    receipt_ok = (
        isinstance(payload, dict)
        and set(payload) == {
            *expected_identity,
            "restored_dlclist_sha256",
        }
        and all(payload.get(key) == value for key, value in expected_identity.items())
        and _is_sha256(payload.get("restored_dlclist_sha256"))
    )
    destination = _destination(game)
    expected_manifest = checkpoint.get("original_pack_manifest")
    if bool(checkpoint.get("pack_existed")):
        pack_ok = (
            destination.is_dir()
            and isinstance(expected_manifest, dict)
            and shared._file_manifest(destination) == expected_manifest
        )
    else:
        pack_ok = not destination.exists() and expected_manifest == {}

    checkpoint_ok = False
    old_registration_absent = False
    registration_absent = False
    mptuner_registered = False
    mods_archive = game / "mods/update/update.rpf"
    original = state / "original-dlclist.xml"
    if patcher.is_file() and mods_archive.is_file() and original.is_file():
        with tempfile.TemporaryDirectory(
            prefix="allin1-stock-bridge-rollback-status-"
        ) as tmp:
            current = Path(tmp) / "dlclist.xml"
            current_payload = shared._extract_dlclist(
                patcher, game, mods_archive, current,
            )
            checkpoint_ok = (
                shared._sha256(original)
                == checkpoint.get("original_dlclist_sha256")
            )
            old_registration_absent = (
                _count_entry(current_payload, OLD_PACK_ENTRY) == 0
            )
            registration_absent = _count_entry(current_payload, PACK_ENTRY) == 0
            mptuner_registered = (
                _count_entry(current_payload, "dlcpacks:/mptuner/") == 1
            )
    checks = {
        "rollback_receipt": receipt_ok,
        "rollback_checkpoint": checkpoint_ok,
        "bridge_pack_restored": pack_ok,
        "davis_registration_absent": registration_absent,
        "retired_registration_absent": old_registration_absent,
        "retired_pack_absent": not _old_pack_paths(game),
        "mptuner_registered_once": mptuner_registered,
        "native_map_host_absent": not _native_map_hosts(game),
    }
    return payload if isinstance(payload, dict) else {}, checks


def read_davis_stock_reference_boot_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    game = shared._assert_enhanced_root(Path(gta_path))
    state = _state_root(game, state_root)
    names = {name.casefold() for name in process_probe()}
    running = bool(names.intersection({"gta5.exe", "gta5_enhanced.exe"}))
    rolled_back = state / "rollback-receipt.json"
    if rolled_back.is_file():
        tool = _tool_path(patcher)
        try:
            payload, checks = _verify_completed_rollback(game, state, tool)
        except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
            payload, checks = {}, {"rollback_receipt": False}
        return {
            **payload,
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "rolled_back",
            "game_running": running,
            "healthy": all(checks.values()),
            "checks": checks,
        }
    try:
        checkpoint = _load_checkpoint(state)
    except FileNotFoundError:
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "absent",
            "phase": PHASE,
            "edition": "enhanced",
            "game_running": running,
            "healthy": True,
        }

    destination = _destination(game)
    archive = destination / "dlc.rpf"
    marker = destination / MARKER_NAME
    runtime = destination / RUNTIME_RECEIPT_NAME
    archive_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and shared._sha256(archive) == checkpoint.get("archive_sha256")
    )
    marker_ok = (
        archive_ok
        and marker.is_file()
        and shared._sha256(marker) == checkpoint.get("marker_sha256")
        and shared._marker_fields(marker) == _expected_marker(archive)
    )
    runtime_payload: Any = None
    runtime_ok = False
    if runtime.is_file():
        try:
            runtime_payload = json.loads(runtime.read_text(encoding="utf-8"))
            runtime_ok = (
                shared._sha256(runtime) == checkpoint.get(
                    "runtime_receipt_sha256"
                )
                and _runtime_matches(runtime_payload, checkpoint)
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            runtime_ok = False

    registration_count: int | None = None
    registration_ok = False
    old_registration_count: int | None = None
    mptuner_registration_count: int | None = None
    tool = _tool_path(patcher)
    mods_archive = game / "mods/update/update.rpf"
    if tool.is_file() and mods_archive.is_file():
        (
            _payload,
            registration_count,
            old_registration_count,
            mptuner_registration_count,
        ) = _registration_snapshot(game, tool)
        registration_ok = (
            registration_count == 1
            and old_registration_count == 0
            and mptuner_registration_count == 1
        )

    original_snapshot = state / "original-dlclist.xml"
    registered_snapshot = state / "registered-dlclist.xml"
    try:
        registration_evidence_ok = (
            original_snapshot.is_file()
            and shared._sha256(original_snapshot)
            == checkpoint.get("original_dlclist_sha256")
            and registered_snapshot.is_file()
            and shared._sha256(registered_snapshot)
            == checkpoint.get("registered_dlclist_sha256")
        )
    except OSError:
        registration_evidence_ok = False

    files = (
        {path.name for path in destination.iterdir() if path.is_file()}
        if destination.is_dir() else set()
    )
    exact_files = files == {"dlc.rpf", MARKER_NAME, RUNTIME_RECEIPT_NAME}
    state_topology = False
    try:
        with tempfile.TemporaryDirectory(
            prefix="allin1-stock-bridge-topology-"
        ) as tmp:
            metadata = Path(tmp) / PACK_NAME
            metadata.mkdir()
            for name in ("content.xml", "setup2.xml"):
                shutil.copy2(state / name, metadata / name)
            state_topology = all(
                inspect_stock_bridge_topology(metadata)["checks"].values()
            )
    except (OSError, RuntimeError):
        state_topology = False
    static_ok = all(
        checkpoint.get(key) == value
        for key, value in _static_checkpoint().items()
    )
    hosts = _native_map_hosts(game)
    checks = {
        "archive": archive_ok,
        "marker": marker_ok,
        "runtime_receipt": runtime_ok,
        "dlclist_registration": registration_ok,
        "registration_transaction_evidence": registration_evidence_ok,
        "exact_zero_payload_files": exact_files,
        "exact_metadata_topology": state_topology,
        "exact_phase_a_contract": static_ok,
        "source_attestation_current": _source_attestation_current(
            game, checkpoint.get("source_attestation"),
        ),
        "retired_allin1_maps_absent": not _old_pack_paths(game),
        "native_map_host_absent": not hosts,
        "native_group_execution_disabled": checkpoint.get(
            "native_group_execution_enabled"
        ) is False,
        "runtime_ipl_requests_disabled": checkpoint.get(
            "runtime_ipl_requests_enabled"
        ) is False,
        "gameconfig_unchanged": checkpoint.get("gameconfig_changed") is False,
    }
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": checkpoint.get("status"),
        "phase": PHASE,
        "edition": "enhanced",
        "game_running": running,
        "healthy": all(checks.values()),
        "checks": checks,
        "registration_count": registration_count,
        "old_registration_count": old_registration_count,
        "mptuner_registration_count": mptuner_registration_count,
        "native_hosts": hosts,
        "pack_name": PACK_NAME,
        "device_name": DEVICE_NAME,
        "layout": checkpoint.get("layout"),
        "runtime_contract": checkpoint.get("runtime_contract"),
        "activation": checkpoint.get("activation"),
        "archive_registration": checkpoint.get("archive_registration"),
        "archive_bytes": archive.stat().st_size if archive.is_file() else 0,
        "archive_sha256": shared._sha256(archive) if archive.is_file() else None,
        "marker": shared._marker_fields(marker),
        "runtime_receipt": runtime_payload,
        "source_attestation": checkpoint.get("source_attestation"),
    }
