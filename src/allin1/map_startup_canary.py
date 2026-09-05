"""Guarded Davis-only startup-registration canary for GTA V Enhanced.

This v3 experiment packages exactly the two Rockstar-owned Davis RPFs plus the
one Davis interior-proxy record required to address that interior.  The three
files are registered by ``GROUP_STARTUP`` and actual interior lifetime is
owned by ``REQUEST_IPL``/``REMOVE_IPL``.  It intentionally contains no custom
property group and never calls or authorizes a content-changeset native.
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
from allin1.generators import dlc_maps


CANARY_ID = "davis-enhanced-isolated-startup-ipl-v3"
INSTALL_CONFIRMATION = "INSTALL_DAVIS_ENHANCED_STARTUP_IPL_CANARY_V3"
ROLLBACK_CONFIRMATION = "ROLLBACK_DAVIS_ENHANCED_STARTUP_IPL_CANARY_V3"
STATE_SCHEMA = 3
RUNTIME_RECEIPT_SCHEMA = 3
RUNTIME_CONTRACT = "allin1-isolated-startup-ipl-v1"
RUNTIME_PACKAGE_ID = "allin1.online-content"
PROPERTY_SCOPE = "davis"
DAVIS_PROXY_NAME = (
    "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_"
)
DAVIS_PROXY_START_FROM = 1117
DAVIS_IPLS = (DAVIS_PROXY_NAME,)
ASSET_COUNT = 3
RPF_ASSET_COUNT = 2
STARTUP_FILE_ENABLE_COUNT = 3
STATE_DIRECTORY = "DavisMapStartupIplV3"
QUARANTINE_REASON = (
    "The Davis startup-IPL v3 canary is quarantined after repeatable live "
    "GTA V Enhanced crashes. Deferred radius activation and startup "
    "registration both reached the same native GTA5_Enhanced.exe "
    "write-to-null before SHVDNE or ALLIN1 initialized. The copied mptuner "
    "RPFs are not safely isolated by the outer three-file manifest. "
    "Installation is disabled; startup-status and startup-rollback remain "
    "available for inspection and recovery."
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
    return (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )


def _destination(game: Path) -> Path:
    return (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )


def _davis_assets() -> tuple[dlc_maps.MapAsset, ...]:
    """Return the closed Davis payload: two RPFs and one filtered proxy."""
    return (
        *shared._davis_assets(),
        dlc_maps._proxy("mptuner", "davis", DAVIS_PROXY_NAME),
    )


def inspect_davis_startup_topology(dlc_root: Path) -> dict[str, Any]:
    """Prove the pack is three Davis files and one inert startup group."""
    content = etree.parse(str(dlc_root / "content.xml"))
    setup = etree.parse(str(dlc_root / "setup2.xml"))
    assets = _davis_assets()
    references = [asset.filename for asset in assets]

    data_files = content.xpath("//dataFiles/Item/filename/text()")
    file_types = content.xpath("//dataFiles/Item/fileType/text()")
    disabled = content.xpath("//dataFiles/Item/disabled/@value")
    changesets = content.xpath("//contentChangeSets/Item/changeSetName/text()")
    startup_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName=$name]/"
        "filesToEnable/Item/text()",
        name=dlc_maps.CHANGESET_NAME,
    )
    invalidated = content.xpath(
        "//contentChangeSets/Item/filesToInvalidate/Item/text()"
    )
    disabled_by_changeset = content.xpath(
        "//contentChangeSets/Item/filesToDisable/Item/text()"
    )
    map_routes = content.xpath("//contentChangeSets/Item/mapChangeSetData/Item")
    loading_screen = content.xpath(
        "string(//contentChangeSets/Item[changeSetName=$name]/"
        "requiresLoadingScreen/@value)",
        name=dlc_maps.CHANGESET_NAME,
    )
    groups = setup.xpath("//contentChangeSetGroups/Item/NameHash/text()")
    startup_changesets = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    )

    checks = {
        "exact_davis_startup_assets": data_files == references,
        "exactly_two_davis_rpfs": file_types.count("RPF_FILE") == 2,
        "exactly_one_davis_proxy": file_types == [
            "RPF_FILE", "RPF_FILE", "INTERIOR_PROXY_ORDER_FILE",
        ],
        "data_files_start_disabled": disabled == ["true"] * ASSET_COUNT,
        "only_base_changeset": changesets == [dlc_maps.CHANGESET_NAME],
        "startup_enables_exact_davis_files": startup_enabled == references,
        "no_file_invalidations": invalidated == [],
        "no_file_disables": disabled_by_changeset == [],
        "no_map_changeset_routes": map_routes == [],
        "no_loading_screen": loading_screen == "false",
        "only_startup_group": groups == ["GROUP_STARTUP"],
        "startup_group_is_base_only": startup_changesets == [
            dlc_maps.CHANGESET_NAME
        ],
        "no_custom_property_group": "ALLIN1_MAP_DAVIS" not in groups,
        "no_global_map_group": not any(
            group in {"GROUP_MAP", "GROUP_MAP_SP"} for group in groups
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(
            name for name, passed in checks.items() if not passed
        )
        raise RuntimeError(
            "Davis startup-IPL canary topology failed closed: " + failed
        )
    return {
        "checks": checks,
        "asset_count": ASSET_COUNT,
        "assets": references,
        "startup_rpf_enable_count": RPF_ASSET_COUNT,
        "startup_file_enable_count": STARTUP_FILE_ENABLE_COUNT,
        "changesets": [dlc_maps.CHANGESET_NAME],
        "groups": ["GROUP_STARTUP"],
        "custom_property_groups": [],
        "group_map_binding": False,
    }


def _assert_exact_staging_scope(
    dlc_root: Path, assets: tuple[dlc_maps.MapAsset, ...],
) -> None:
    expected = {
        "content.xml",
        "setup2.xml",
        *(asset.destination_path for asset in assets),
    }
    observed = {
        path.relative_to(dlc_root).as_posix()
        for path in dlc_root.rglob("*")
        if path.is_file()
    }
    if observed != expected:
        extra = sorted(observed - expected)
        missing = sorted(expected - observed)
        raise RuntimeError(
            "Davis startup staging escaped its exact three-asset scope; "
            f"extra={extra}, missing={missing}"
        )


def _inspect_filtered_proxy(path: Path) -> dict[str, Any]:
    """Verify the one retained proxy kept its original global order index."""
    try:
        tree = etree.parse(str(path))
    except (OSError, etree.XMLSyntaxError) as exc:
        raise RuntimeError(
            f"The filtered Davis interior proxy is invalid: {path}"
        ) from exc
    start_from = tree.xpath("string(/*/startFrom/@value)")
    names = tree.xpath("/*/proxies/Item/text()")
    if start_from != str(DAVIS_PROXY_START_FROM) or names != [DAVIS_PROXY_NAME]:
        raise RuntimeError(
            "The Davis proxy filter did not preserve its exact global index "
            f"and identity: startFrom={start_from!r}, proxies={names!r}"
        )
    return {
        "destination_path": path.as_posix(),
        "proxy_names": [DAVIS_PROXY_NAME],
        "start_from": DAVIS_PROXY_START_FROM,
        "entry_count": 1,
    }


def _build_archive(
    game: Path, patcher: Path, work: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    assets = _davis_assets()
    dlc_root = dlc_maps.create_dlc_pack(
        work,
        assets=assets,
        layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
    )
    topology = inspect_davis_startup_topology(dlc_root)
    manifest = work / "davis-startup-assets.tsv"
    manifest.write_text(
        "".join(
            f"{asset.source_path}\t{asset.destination_path}\n"
            for asset in assets
        ),
        encoding="utf-8",
    )

    grouped: dict[tuple[str, str], list[dlc_maps.MapAsset]] = {}
    for asset in assets:
        grouped.setdefault(
            (asset.source_pack, asset.source_archive_name), []
        ).append(asset)
    if list(grouped) != [("mptuner", "dlc.rpf")]:
        raise RuntimeError(
            "The Davis startup canary must have one mptuner source archive."
        )

    source_archives: list[dict[str, Any]] = []
    for index, ((source_pack, archive_name), selected) in enumerate(
        grouped.items()
    ):
        source_archive = selected[0].source_archive(game)
        if not source_archive.is_file():
            raise FileNotFoundError(
                f"Required {source_pack} archive is missing: {source_archive}"
            )
        try:
            relative = source_archive.relative_to(game).as_posix()
        except ValueError as exc:
            raise RuntimeError(
                "The Davis source archive escaped the declared GTA root."
            ) from exc
        stat = source_archive.stat()
        source_archives.append({
            "pack": source_pack,
            "archive": archive_name,
            "source": "stock",
            "path": relative,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": shared._sha256(source_archive),
        })
        extraction = work / f"extract-{index}.tsv"
        extraction.write_text(
            "".join(
                f"{asset.source_path}\t{asset.destination_path}\n"
                for asset in selected
            ),
            encoding="utf-8",
        )
        shared._run_tool(
            patcher,
            ["extract-entries", game, source_archive, extraction, dlc_root],
            operation="Extract mptuner Davis assets",
        )

    missing = dlc_maps.validate_staged_assets(dlc_root, assets=assets)
    if missing:
        raise RuntimeError(
            "Davis startup staging is incomplete: "
            + ", ".join(str(path) for path in missing)
        )
    filtered = dlc_maps.filter_staged_proxy_assets(dlc_root, assets=assets)
    proxy_asset = next(asset for asset in assets if asset.proxy_names)
    proxy_path = proxy_asset.destination(dlc_root)
    if filtered != [proxy_path]:
        raise RuntimeError(
            "The Davis startup canary must filter exactly one proxy asset."
        )
    proxy_filter = _inspect_filtered_proxy(proxy_path)
    proxy_filter["destination_path"] = proxy_asset.destination_path
    _assert_exact_staging_scope(dlc_root, assets)
    sources = []
    for asset in assets:
        staged = asset.destination(dlc_root)
        source = {
            "source_pack": asset.source_pack,
            "source_archive": asset.source_archive_name,
            "source_path": asset.source_path,
            "destination_path": asset.destination_path,
            "source_asset_bytes": staged.stat().st_size,
            "source_asset_sha256": shared._sha256(staged),
        }
        if asset.proxy_names:
            source.update({
                "proxy_names": list(asset.proxy_names),
                "proxy_start_from": DAVIS_PROXY_START_FROM,
            })
        sources.append(source)

    shared._run_tool(
        patcher,
        ["open-rpfs", game, manifest, dlc_root],
        operation="Convert Davis startup archives for Enhanced",
    )
    _assert_exact_staging_scope(dlc_root, assets)
    output = work / "allin1_maps-davis-startup-v3.rpf"
    shared._run_tool(
        patcher,
        ["build-dlc", dlc_root, output, "--gta-path", game],
        operation="Build Davis startup-IPL canary",
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("The Davis startup canary produced no DLC archive.")
    shared._run_tool(
        patcher,
        ["verify-map-dlc", output, manifest],
        operation="Verify Davis startup-IPL canary",
    )
    return output, manifest, topology, {
        "source_archives": source_archives,
        "sources": sources,
        "proxy_filters": [proxy_filter],
    }


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(
            character in "0123456789abcdef"
            for character in value.casefold()
        )
    )


def _provenance_is_exact(provenance: dict[str, Any]) -> bool:
    archives = provenance.get("source_archives")
    sources = provenance.get("sources")
    proxy_filters = provenance.get("proxy_filters")
    if not isinstance(archives, list) or len(archives) != 1:
        return False
    archive = archives[0]
    if not isinstance(archive, dict):
        return False
    source_kind = archive.get("source")
    expected_archive_path = (
        "mods/update/x64/dlcpacks/mptuner/dlc.rpf"
        if source_kind == "mods"
        else "update/x64/dlcpacks/mptuner/dlc.rpf"
    )
    if (
        source_kind not in {"mods", "stock"}
        or archive.get("pack") != "mptuner"
        or archive.get("archive") != "dlc.rpf"
        or archive.get("path") != expected_archive_path
        or not isinstance(archive.get("size"), int)
        or archive["size"] <= 0
        or not isinstance(archive.get("mtime_ns"), int)
        or archive["mtime_ns"] < 0
        or not _is_sha256(archive.get("sha256"))
    ):
        return False

    assets = _davis_assets()
    if not isinstance(sources, list) or len(sources) != len(assets):
        return False
    for asset, source in zip(assets, sources):
        if not isinstance(source, dict) or any((
            source.get("source_pack") != asset.source_pack,
            source.get("source_archive") != asset.source_archive_name,
            source.get("source_path") != asset.source_path,
            source.get("destination_path") != asset.destination_path,
            not isinstance(source.get("source_asset_bytes"), int),
            source.get("source_asset_bytes", 0) <= 0,
            not _is_sha256(source.get("source_asset_sha256")),
        )):
            return False
        if asset.proxy_names and (
            source.get("proxy_names") != list(asset.proxy_names)
            or source.get("proxy_start_from") != DAVIS_PROXY_START_FROM
        ):
            return False

    return proxy_filters == [{
        "destination_path": assets[-1].destination_path,
        "proxy_names": [DAVIS_PROXY_NAME],
        "start_from": DAVIS_PROXY_START_FROM,
        "entry_count": 1,
    }]


def _runtime_receipt(
    archive: Path, topology: dict[str, Any], provenance: dict[str, Any],
) -> dict[str, Any]:
    references = list(topology.get("assets", []))
    if (
        references != [asset.filename for asset in _davis_assets()]
        or topology.get("asset_count") != ASSET_COUNT
        or topology.get("startup_rpf_enable_count") != RPF_ASSET_COUNT
        or topology.get("startup_file_enable_count") !=
            STARTUP_FILE_ENABLE_COUNT
        or topology.get("changesets") != [dlc_maps.CHANGESET_NAME]
        or topology.get("groups") != ["GROUP_STARTUP"]
        or topology.get("custom_property_groups") != []
        or topology.get("group_map_binding") is not False
        or not _provenance_is_exact(provenance)
    ):
        raise RuntimeError(
            "The startup receipt cannot be emitted from a broader topology."
        )
    return {
        "schema": RUNTIME_RECEIPT_SCHEMA,
        "status": "verified",
        "canary_id": CANARY_ID,
        "package_id": RUNTIME_PACKAGE_ID,
        "pack_name": dlc_maps.DLC_NAME,
        "edition": "enhanced",
        "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_registration": "startup",
        "activation": "startup-file-registration-plus-request-ipl",
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": shared._sha256(archive),
        "asset_count": ASSET_COUNT,
        "startup_rpf_enable_count": RPF_ASSET_COUNT,
        "startup_file_enable_count": STARTUP_FILE_ENABLE_COUNT,
        "property_scope": PROPERTY_SCOPE,
        "properties": [PROPERTY_SCOPE],
        "ipls": list(DAVIS_IPLS),
        "declared_changesets": [dlc_maps.CHANGESET_NAME],
        "declared_groups": ["GROUP_STARTUP"],
        "groups": [{
            "group": "GROUP_STARTUP",
            "changesets": [dlc_maps.CHANGESET_NAME],
            "references": references,
        }],
        "custom_property_groups": [],
        "group_map_binding": False,
        "source_archives": provenance["source_archives"],
        "sources": provenance["sources"],
        "proxy_filters": provenance["proxy_filters"],
    }


def _receipt_matches(payload: Any, checkpoint: dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    references = [asset.filename for asset in _davis_assets()]
    return (
        payload.get("schema") == RUNTIME_RECEIPT_SCHEMA
        and payload.get("status") == "verified"
        and payload.get("canary_id") == CANARY_ID
        and payload.get("package_id") == RUNTIME_PACKAGE_ID
        and payload.get("pack_name") == dlc_maps.DLC_NAME
        and payload.get("edition") == "enhanced"
        and payload.get("layout") == dlc_maps.STARTUP_IPL_PACK_LAYOUT
        and payload.get("runtime_contract") == RUNTIME_CONTRACT
        and payload.get("archive_registration") == "startup"
        and payload.get("activation") ==
            "startup-file-registration-plus-request-ipl"
        and payload.get("archive_bytes") == checkpoint.get("archive_bytes")
        and payload.get("archive_sha256") == checkpoint.get("archive_sha256")
        and payload.get("asset_count") == ASSET_COUNT
        and payload.get("startup_rpf_enable_count") == RPF_ASSET_COUNT
        and payload.get("startup_file_enable_count") ==
            STARTUP_FILE_ENABLE_COUNT
        and payload.get("property_scope") == PROPERTY_SCOPE
        and payload.get("properties") == [PROPERTY_SCOPE]
        and payload.get("ipls") == list(DAVIS_IPLS)
        and payload.get("declared_changesets") == [dlc_maps.CHANGESET_NAME]
        and payload.get("declared_groups") == ["GROUP_STARTUP"]
        and payload.get("groups") == [{
            "group": "GROUP_STARTUP",
            "changesets": [dlc_maps.CHANGESET_NAME],
            "references": references,
        }]
        and payload.get("custom_property_groups") == []
        and payload.get("group_map_binding") is False
        and payload.get("source_archives") == checkpoint.get(
            "source_archives"
        )
        and payload.get("sources") == checkpoint.get("sources")
        and payload.get("proxy_filters") == checkpoint.get("proxy_filters")
    )


def _write_marker(marker: Path, archive: Path) -> None:
    shared._write_text_atomic(
        "Generated from this GTA installation and verified by ALLIN1.\n"
        f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
        "archive_registration=startup\n"
        "group_map_binding=false\n"
        "activation=startup-file-registration-plus-request-ipl\n"
        f"asset_count={ASSET_COUNT}\n"
        f"startup_rpf_enable_count={RPF_ASSET_COUNT}\n"
        f"startup_file_enable_count={STARTUP_FILE_ENABLE_COUNT}\n"
        f"reference_count={STARTUP_FILE_ENABLE_COUNT}\n"
        f"receipt={dlc_maps.RUNTIME_RECEIPT}\n"
        f"runtime_contract={RUNTIME_CONTRACT}\n"
        f"property_scope={PROPERTY_SCOPE}\n"
        "custom_property_groups=0\n"
        f"archive_bytes={archive.stat().st_size}\n"
        f"archive_sha256={shared._sha256(archive)}\n",
        marker,
    )


def _load_checkpoint(state: Path) -> dict[str, Any]:
    for name in ("install-receipt.json", "journal.json"):
        path = state / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("schema") == STATE_SCHEMA
            and payload.get("canary_id") == CANARY_ID
        ):
            return payload
    raise FileNotFoundError("No valid Davis startup-IPL v3 checkpoint exists.")


def install_davis_startup_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    """Refuse installation of the live-crashing startup-registration canary."""
    raise RuntimeError(QUARANTINE_REASON)


def _install_davis_startup_canary_forensic(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    """Recreate historical v3 checkpoints for isolated forensic tests only."""
    if confirmation != INSTALL_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {INSTALL_CONFIRMATION!r} is required."
        )
    game = shared._assert_enhanced_root(Path(gta_path))
    shared._assert_game_closed(process_probe)
    hosts = shared._native_hosts(game)
    if hosts:
        raise RuntimeError(
            "Remove the experimental map host before the startup-IPL canary: "
            + ", ".join(hosts)
        )
    tool = _tool_path(patcher)
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    mods_archive = game / "mods" / "update" / "update.rpf"
    if not mods_archive.is_file():
        raise RuntimeError(
            "A complete mods/update/update.rpf must already exist."
        )

    state = _state_root(game, state_root)
    if state.exists():
        raise RuntimeError(
            f"A Davis startup-IPL v3 checkpoint exists at {state}; inspect "
            "status and roll it back first."
        )
    state.mkdir(parents=True)
    work = state / "work"
    work.mkdir()
    destination = _destination(game)
    backup = state / "original-pack"
    original_dlclist = state / "original-dlclist.xml"
    registered_dlclist = state / "registered-dlclist.xml"
    journal_path = state / "journal.json"
    receipt_path = state / "install-receipt.json"
    pack_existed = destination.exists()
    transaction_id = uuid.uuid4().hex
    journal: dict[str, Any] = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": transaction_id,
        "edition": "enhanced",
        "status": "building",
        "pack_existed": pack_existed,
        "gameconfig_changed": False,
        "native_host_installed": False,
    }
    shared._write_json_atomic(journal, journal_path)

    mutated = False
    try:
        archive, manifest, topology, provenance = _build_archive(
            game, tool, work,
        )
        original_payload = shared._extract_dlclist(
            tool, game, mods_archive, original_dlclist,
        )
        if any(
            item.rstrip("/").casefold() ==
                shared.PACK_ENTRY.rstrip("/").casefold()
            for item in shared._dlclist_items(original_payload)
        ):
            raise RuntimeError(
                "allin1_maps is already registered; the v3 canary requires "
                "a quarantined baseline."
            )
        original_manifest: dict[str, Any] = {}
        if pack_existed:
            if not destination.is_dir():
                raise RuntimeError(
                    "The existing allin1_maps path is not a directory."
                )
            original_manifest = shared._copy_tree_verified(
                destination, backup,
            )
        journal.update({
            "status": "ready_to_mutate",
            "original_dlclist_sha256": shared._sha256(original_dlclist),
            "original_pack_manifest": original_manifest,
        })
        shared._write_json_atomic(journal, journal_path)

        mutated = True
        if destination.exists():
            shutil.rmtree(destination)
        dlc_maps.deploy_dlc_rpf(
            archive,
            game,
            layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
            asset_count=ASSET_COUNT,
        )
        deployed_archive = destination / "dlc.rpf"
        marker = destination / dlc_maps.ACTIVE_MARKER
        _write_marker(marker, deployed_archive)
        runtime_payload = _runtime_receipt(
            deployed_archive, topology, provenance,
        )
        runtime_receipt = destination / dlc_maps.RUNTIME_RECEIPT
        shared._write_json_atomic(runtime_payload, runtime_receipt)

        shared._run_tool(
            tool,
            ["register-dlc", game, dlc_maps.DLC_NAME],
            operation="Register Davis-only startup-IPL canary",
        )
        registered_payload = shared._extract_dlclist(
            tool, game, mods_archive, registered_dlclist,
        )
        shared._verify_registration_delta(original_payload, registered_payload)
        marker_values = shared._marker_fields(marker)
        expected_marker = {
            "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
            "archive_registration": "startup",
            "activation": "startup-file-registration-plus-request-ipl",
            "asset_count": str(ASSET_COUNT),
            "startup_rpf_enable_count": str(RPF_ASSET_COUNT),
            "startup_file_enable_count": str(STARTUP_FILE_ENABLE_COUNT),
            "receipt": dlc_maps.RUNTIME_RECEIPT,
            "runtime_contract": RUNTIME_CONTRACT,
            "property_scope": PROPERTY_SCOPE,
            "custom_property_groups": "0",
            "group_map_binding": "false",
        }
        if any(
            marker_values.get(key) != value
            for key, value in expected_marker.items()
        ):
            raise RuntimeError(
                "The Davis startup marker does not match its v3 contract."
            )

        for name in ("content.xml", "setup2.xml"):
            (state / name).write_bytes(
                (work / dlc_maps.DLC_NAME / name).read_bytes()
            )
        (state / "davis-startup-assets.tsv").write_bytes(manifest.read_bytes())
        (state / "runtime-receipt.json").write_bytes(
            runtime_receipt.read_bytes()
        )
        shutil.rmtree(work)
        receipt = {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": transaction_id,
            "status": "installed_startup_ipl_verified",
            "edition": "enhanced",
            "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
            "runtime_contract": RUNTIME_CONTRACT,
            "archive_registration": "startup",
            "activation": "startup-file-registration-plus-request-ipl",
            "package_id": RUNTIME_PACKAGE_ID,
            "pack_name": dlc_maps.DLC_NAME,
            "property_scope": PROPERTY_SCOPE,
            "properties": [PROPERTY_SCOPE],
            "ipls": list(DAVIS_IPLS),
            "asset_count": ASSET_COUNT,
            "startup_rpf_enable_count": RPF_ASSET_COUNT,
            "startup_file_enable_count": STARTUP_FILE_ENABLE_COUNT,
            "declared_groups": ["GROUP_STARTUP"],
            "custom_property_groups": [],
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": shared._sha256(deployed_archive),
            "marker_sha256": shared._sha256(marker),
            "runtime_receipt_sha256": shared._sha256(runtime_receipt),
            "source_archives": provenance["source_archives"],
            "sources": provenance["sources"],
            "proxy_filters": provenance["proxy_filters"],
            "original_dlclist_sha256": shared._sha256(original_dlclist),
            "registered_dlclist_sha256": shared._sha256(registered_dlclist),
            "pack_existed": pack_existed,
            "original_pack_manifest": original_manifest,
            "gameconfig_changed": False,
            "native_host_installed": False,
            "native_group_execution_enabled": False,
            "startup_archive_registration_enabled": True,
            "runtime_receipt_present": True,
        }
        shared._write_json_atomic(receipt, receipt_path)
        return receipt
    except Exception:
        if mutated:
            try:
                _restore_from_checkpoint(
                    game, state, tool, strict_current=False,
                )
            except Exception:
                pass
        raise


def _restore_from_checkpoint(
    game: Path, state: Path, patcher: Path, *, strict_current: bool,
) -> dict[str, Any]:
    checkpoint = _load_checkpoint(state)
    destination = _destination(game)
    mods_archive = game / "mods" / "update" / "update.rpf"
    original_dlclist = state / "original-dlclist.xml"
    if not mods_archive.is_file() or not original_dlclist.is_file():
        raise RuntimeError("The exact v3 rollback checkpoint is incomplete.")
    if shared._sha256(original_dlclist) != checkpoint.get(
        "original_dlclist_sha256"
    ):
        raise RuntimeError("The original v3 dlclist payload was tampered with.")

    if (
        strict_current
        and checkpoint.get("status") == "installed_startup_ipl_verified"
    ):
        archive = destination / "dlc.rpf"
        marker = destination / dlc_maps.ACTIVE_MARKER
        runtime = destination / dlc_maps.RUNTIME_RECEIPT
        if (
            not archive.is_file()
            or archive.stat().st_size != checkpoint.get("archive_bytes")
            or shared._sha256(archive) != checkpoint.get("archive_sha256")
            or not marker.is_file()
            or shared._sha256(marker) != checkpoint.get("marker_sha256")
            or not runtime.is_file()
            or shared._sha256(runtime) != checkpoint.get(
                "runtime_receipt_sha256"
            )
        ):
            raise RuntimeError(
                "The active v3 canary changed after installation; rollback "
                "refuses to overwrite unreviewed files."
            )
        with tempfile.TemporaryDirectory(
            prefix="allin1-davis-startup-status-"
        ) as tmp:
            current = Path(tmp) / "dlclist.xml"
            shared._extract_dlclist(
                patcher, game, mods_archive, current,
            )
            if shared._sha256(current) != checkpoint.get(
                "registered_dlclist_sha256"
            ):
                raise RuntimeError(
                    "dlclist.xml changed after v3 installation; exact "
                    "rollback requires review."
                )

    shared._run_tool(
        patcher,
        [
            "replace-entry", game, mods_archive,
            shared.DLCLIST_ENTRY, original_dlclist,
        ],
        operation="Restore exact pre-v3 dlclist.xml",
    )
    verified = state / "verified-restored-dlclist.xml"
    restored = shared._extract_dlclist(
        patcher, game, mods_archive, verified,
    )
    if restored != original_dlclist.read_bytes():
        raise RuntimeError("The restored v3 dlclist does not match its backup.")
    if destination.exists():
        shutil.rmtree(destination)
    if bool(checkpoint.get("pack_existed")):
        backup = state / "original-pack"
        if not backup.is_dir():
            raise RuntimeError("The original allin1_maps backup is missing.")
        shutil.copytree(backup, destination)
        if shared._file_manifest(destination) != checkpoint.get(
            "original_pack_manifest"
        ):
            raise RuntimeError(
                "The restored allin1_maps directory failed verification."
            )
    return checkpoint


def rollback_davis_startup_canary(
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
    completed = state / "rollback-receipt.json"
    if completed.is_file():
        return json.loads(completed.read_text(encoding="utf-8"))
    tool = _tool_path(patcher)
    checkpoint = _restore_from_checkpoint(
        game, state, tool, strict_current=True,
    )
    (state / "install-receipt.json").unlink(missing_ok=True)
    result = {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "transaction_id": checkpoint.get("transaction_id"),
        "status": "rolled_back",
        "restored_dlclist_sha256": checkpoint.get(
            "original_dlclist_sha256"
        ),
        "restored_original_pack": bool(checkpoint.get("pack_existed")),
    }
    shared._write_json_atomic(result, completed)
    return result


def read_davis_startup_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = shared._default_process_names,
) -> dict[str, Any]:
    game = shared._assert_enhanced_root(Path(gta_path))
    state = _state_root(game, state_root)
    names = {name.casefold() for name in process_probe()}
    game_running = bool(
        names.intersection({"gta5.exe", "gta5_enhanced.exe"})
    )
    rollback = state / "rollback-receipt.json"
    if rollback.is_file():
        payload = json.loads(rollback.read_text(encoding="utf-8"))
        return {**payload, "game_running": game_running, "healthy": True}
    try:
        checkpoint = _load_checkpoint(state)
    except FileNotFoundError:
        return {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "status": "absent",
            "edition": "enhanced",
            "game_running": game_running,
            "healthy": True,
        }

    destination = _destination(game)
    archive = destination / "dlc.rpf"
    marker = destination / dlc_maps.ACTIVE_MARKER
    runtime = destination / dlc_maps.RUNTIME_RECEIPT
    marker_values = shared._marker_fields(marker)
    archive_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and shared._sha256(archive) == checkpoint.get("archive_sha256")
    )
    marker_ok = (
        marker.is_file()
        and shared._sha256(marker) == checkpoint.get("marker_sha256")
        and marker_values.get("layout") == dlc_maps.STARTUP_IPL_PACK_LAYOUT
        and marker_values.get("archive_registration") == "startup"
        and marker_values.get("activation") ==
            "startup-file-registration-plus-request-ipl"
        and marker_values.get("asset_count") == str(ASSET_COUNT)
        and marker_values.get("startup_rpf_enable_count") ==
            str(RPF_ASSET_COUNT)
        and marker_values.get("startup_file_enable_count") ==
            str(STARTUP_FILE_ENABLE_COUNT)
        and marker_values.get("receipt") == dlc_maps.RUNTIME_RECEIPT
        and marker_values.get("runtime_contract") == RUNTIME_CONTRACT
        and marker_values.get("property_scope") == PROPERTY_SCOPE
        and marker_values.get("custom_property_groups") == "0"
        and marker_values.get("group_map_binding") == "false"
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
                and _receipt_matches(runtime_payload, checkpoint)
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            runtime_ok = False

    registration_count: int | None = None
    registration_ok = False
    tool = _tool_path(patcher)
    mods_archive = game / "mods" / "update" / "update.rpf"
    if tool.is_file() and mods_archive.is_file():
        with tempfile.TemporaryDirectory(
            prefix="allin1-davis-startup-status-"
        ) as tmp:
            current = Path(tmp) / "dlclist.xml"
            payload = shared._extract_dlclist(
                tool, game, mods_archive, current,
            )
            expected = shared.PACK_ENTRY.rstrip("/").casefold()
            registration_count = sum(
                item.rstrip("/").casefold() == expected
                for item in shared._dlclist_items(payload)
            )
            registration_ok = (
                registration_count == 1
                and shared._sha256(current) == checkpoint.get(
                    "registered_dlclist_sha256"
                )
            )
    topology_ok = (
        checkpoint.get("archive_registration") == "startup"
        and checkpoint.get("activation") ==
            "startup-file-registration-plus-request-ipl"
        and checkpoint.get("layout") == dlc_maps.STARTUP_IPL_PACK_LAYOUT
        and checkpoint.get("runtime_contract") == RUNTIME_CONTRACT
        and checkpoint.get("package_id") == RUNTIME_PACKAGE_ID
        and checkpoint.get("pack_name") == dlc_maps.DLC_NAME
        and checkpoint.get("asset_count") == ASSET_COUNT
        and checkpoint.get("startup_rpf_enable_count") == RPF_ASSET_COUNT
        and checkpoint.get("startup_file_enable_count") ==
            STARTUP_FILE_ENABLE_COUNT
        and checkpoint.get("declared_groups") == ["GROUP_STARTUP"]
        and checkpoint.get("custom_property_groups") == []
        and checkpoint.get("property_scope") == PROPERTY_SCOPE
        and checkpoint.get("ipls") == list(DAVIS_IPLS)
        and len(checkpoint.get("source_archives", [])) == 1
        and len(checkpoint.get("sources", [])) == ASSET_COUNT
        and checkpoint.get("proxy_filters") == [{
            "destination_path": _davis_assets()[-1].destination_path,
            "proxy_names": [DAVIS_PROXY_NAME],
            "start_from": DAVIS_PROXY_START_FROM,
            "entry_count": 1,
        }]
    )
    hosts = shared._native_hosts(game)
    checks = {
        "archive": archive_ok,
        "marker": marker_ok,
        "registration": registration_ok,
        "exact_davis_startup_topology": topology_ok,
        "runtime_receipt_verified": runtime_ok,
        "native_host_absent": not hosts,
        "native_group_execution_disabled": checkpoint.get(
            "native_group_execution_enabled"
        ) is False,
        "startup_archive_registration_enabled": checkpoint.get(
            "startup_archive_registration_enabled"
        ) is True,
        "gameconfig_unchanged": checkpoint.get("gameconfig_changed") is False,
    }
    return {
        "schema": STATE_SCHEMA,
        "canary_id": CANARY_ID,
        "status": checkpoint.get("status", "pending"),
        "edition": "enhanced",
        "game_running": game_running,
        "healthy": all(checks.values()),
        "checks": checks,
        "registration_count": registration_count,
        "native_hosts": hosts,
        "archive_bytes": archive.stat().st_size if archive.is_file() else 0,
        "archive_sha256": (
            shared._sha256(archive) if archive.is_file() else None
        ),
        "layout": checkpoint.get("layout"),
        "runtime_contract": checkpoint.get("runtime_contract"),
        "archive_registration": checkpoint.get("archive_registration"),
        "activation": checkpoint.get("activation"),
        "package_id": checkpoint.get("package_id"),
        "pack_name": checkpoint.get("pack_name"),
        "marker": marker_values,
        "runtime_receipt": runtime_payload,
        "asset_count": checkpoint.get("asset_count"),
        "startup_rpf_enable_count": checkpoint.get(
            "startup_rpf_enable_count"
        ),
        "startup_file_enable_count": checkpoint.get(
            "startup_file_enable_count"
        ),
        "property_scope": checkpoint.get("property_scope"),
        "ipls": checkpoint.get("ipls"),
        "declared_groups": checkpoint.get("declared_groups"),
        "custom_property_groups": checkpoint.get("custom_property_groups"),
        "source_archives": checkpoint.get("source_archives"),
        "proxy_filters": checkpoint.get("proxy_filters"),
    }
