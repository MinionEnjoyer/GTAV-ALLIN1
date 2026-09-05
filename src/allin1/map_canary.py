"""Guarded Enhanced Davis map-registration canary.

This module is deliberately narrower than the production map installer.  It
can build and register only the two Rockstar-owned Davis Auto Shop archives,
and it never installs or enables the native map host.  Its purpose is to prove
that GTA V Enhanced can parse a dormant, property-scoped DLC before a separate
live test is allowed to exercise the content-change-set ABI.
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

from allin1.generators import dlc_maps
from allin1.processes import run_hidden


CANARY_ID = "davis-enhanced-registration-v1"
INSTALL_CONFIRMATION = "INSTALL_DAVIS_ENHANCED_REGISTRATION_CANARY"
ROLLBACK_CONFIRMATION = "ROLLBACK_DAVIS_ENHANCED_REGISTRATION_CANARY"
STATE_SCHEMA = 1
STREAMING_CANARY_ID = "davis-enhanced-isolated-streaming-v2"
STREAMING_INSTALL_CONFIRMATION = "INSTALL_DAVIS_ENHANCED_STREAMING_CANARY_V2"
STREAMING_ROLLBACK_CONFIRMATION = "ROLLBACK_DAVIS_ENHANCED_STREAMING_CANARY_V2"
STREAMING_STATE_SCHEMA = 2
RUNTIME_RECEIPT_SCHEMA = 2
RUNTIME_CONTRACT = "allin1-isolated-property-v1"
RUNTIME_PACKAGE_ID = "allin1.online-content"
DLCLIST_ENTRY = "common/data/dlclist.xml"
PACK_ENTRY = "dlcpacks:/allin1_maps/"
RUNTIME_RECEIPT = "allin1_maps.runtime.json"
NATIVE_HOST_PATTERNS = (
    "ALLIN1MapHost*.asi",
    "ALLIN1.MapHost*.asi",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _write_json_atomic(payload: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_text_atomic(payload: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _state_root(gta_path: Path, override: Path | None = None) -> Path:
    if override is not None:
        return override.resolve()
    base = os.environ.get("LOCALAPPDATA")
    local = (
        Path(base)
        if base
        else Path.home() / "AppData" / "Local"
    )
    identity = hashlib.sha256(
        str(gta_path.resolve()).casefold().encode("utf-8")
    ).hexdigest()[:16]
    return local / "ALLIN1" / "DeveloperCanaries" / "DavisMap" / identity


def _streaming_state_root(
    gta_path: Path, override: Path | None = None,
) -> Path:
    """Return a v2 checkpoint root that can never collide with v1."""
    if override is not None:
        return override.resolve()
    base = os.environ.get("LOCALAPPDATA")
    local = Path(base) if base else Path.home() / "AppData" / "Local"
    identity = hashlib.sha256(
        str(gta_path.resolve()).casefold().encode("utf-8")
    ).hexdigest()[:16]
    return (
        local / "ALLIN1" / "DeveloperCanaries"
        / "DavisMapStreamingV2" / identity
    )


def _default_process_names() -> set[str]:
    try:
        from allin1.game_launcher import _windows_processes

        return {name.casefold() for name in _windows_processes().values()}
    except Exception:
        # A failed process probe is not permission to mutate a live game.
        return {"process-probe-unavailable"}


def _assert_game_closed(process_probe: Callable[[], set[str]]) -> None:
    names = {name.casefold() for name in process_probe()}
    running = names.intersection({"gta5.exe", "gta5_enhanced.exe"})
    if running:
        raise RuntimeError(
            "GTA V must be closed before installing or rolling back the "
            "Davis registration canary."
        )
    if "process-probe-unavailable" in names:
        raise RuntimeError(
            "Could not verify that GTA V is closed; the canary remains unchanged."
        )


def _assert_enhanced_root(gta_path: Path) -> Path:
    game = gta_path.expanduser().resolve()
    if not game.is_dir() or not (game / "GTA5_Enhanced.exe").is_file():
        raise ValueError(
            "The Davis registration canary requires an explicit GTA V "
            "Enhanced folder containing GTA5_Enhanced.exe."
        )
    return game


def _native_hosts(game: Path) -> list[str]:
    found: set[Path] = set()
    for parent in (game, game / "scripts"):
        if not parent.is_dir():
            continue
        for pattern in NATIVE_HOST_PATTERNS:
            found.update(path for path in parent.glob(pattern) if path.is_file())
    return sorted(path.relative_to(game).as_posix() for path in found)


def _run_tool(
    patcher: Path,
    arguments: list[str | Path],
    *,
    operation: str,
    timeout: int = 600,
) -> None:
    result = run_hidden(
        [str(patcher), *(str(value) for value in arguments)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"{operation} failed: {detail or f'exit code {result.returncode}'}"
        )


def _davis_assets() -> tuple[dlc_maps.MapAsset, ...]:
    assets = tuple(
        asset for asset in dlc_maps.MAP_ASSETS
        if asset.change_set_key == "davis"
    )
    if len(assets) != 2 or any(asset.file_type != "RPF_FILE" for asset in assets):
        raise RuntimeError(
            "The Davis canary contract must resolve to exactly two RPF assets."
        )
    return assets


def inspect_davis_topology(dlc_root: Path) -> dict[str, Any]:
    """Validate and summarize the zero-startup-RPF canary metadata."""
    content = etree.parse(str(dlc_root / "content.xml"))
    setup = etree.parse(str(dlc_root / "setup2.xml"))
    assets = _davis_assets()
    expected_files = [asset.filename for asset in assets]

    data_files = content.xpath("//dataFiles/Item/filename/text()")
    disabled = content.xpath("//dataFiles/Item/disabled/@value")
    changesets = content.xpath(
        "//contentChangeSets/Item/changeSetName/text()"
    )
    startup_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName=$name]/"
        "filesToEnable/Item/text()",
        name=dlc_maps.CHANGESET_NAME,
    )
    davis_enabled = content.xpath(
        "//contentChangeSets/Item[changeSetName='ALLIN1_MAPS_DAVIS']/"
        "mapChangeSetData/Item/filesToEnable/Item/text()"
    )
    associated_maps = content.xpath(
        "//contentChangeSets/Item[changeSetName='ALLIN1_MAPS_DAVIS']/"
        "mapChangeSetData/Item/associatedMap/text()"
    )
    route_invalidates = content.xpath(
        "//contentChangeSets/Item[changeSetName='ALLIN1_MAPS_DAVIS']/"
        "mapChangeSetData/Item/filesToInvalidate/Item/text()"
    )
    route_disables = content.xpath(
        "//contentChangeSets/Item[changeSetName='ALLIN1_MAPS_DAVIS']/"
        "mapChangeSetData/Item/filesToDisable/Item/text()"
    )
    requires_loading_screen = content.xpath(
        "string(//contentChangeSets/Item["
        "changeSetName='ALLIN1_MAPS_DAVIS']/requiresLoadingScreen/@value)"
    )
    use_cache_loader = content.xpath(
        "string(//contentChangeSets/Item["
        "changeSetName='ALLIN1_MAPS_DAVIS']/useCacheLoader/@value)"
    )
    loading_screen_context = content.xpath(
        "string(//contentChangeSets/Item["
        "changeSetName='ALLIN1_MAPS_DAVIS']/loadingScreenContext)"
    )
    groups = setup.xpath(
        "//contentChangeSetGroups/Item/NameHash/text()"
    )
    startup_group = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/"
        "ContentChangeSets/Item/text()"
    )
    davis_group = setup.xpath(
        "//contentChangeSetGroups/Item[NameHash='ALLIN1_MAP_DAVIS']/"
        "ContentChangeSets/Item/text()"
    )

    checks = {
        "two_davis_rpfs": data_files == expected_files,
        "all_rpfs_disabled": disabled == ["true", "true"],
        "only_base_and_davis_changesets": changesets == [
            dlc_maps.CHANGESET_NAME,
            "ALLIN1_MAPS_DAVIS",
        ],
        "zero_startup_rpf_enables": startup_enabled == [],
        "davis_enables_only_davis_rpfs": davis_enabled == expected_files,
        "story_associated_map": associated_maps == [
            dlc_maps.STORY_ASSOCIATED_MAP
        ],
        "davis_route_does_not_invalidate": route_invalidates == [],
        "davis_route_does_not_disable": route_disables == [],
        "davis_route_has_no_loading_screen":
            requires_loading_screen == "false",
        "davis_route_bypasses_cache_loader": use_cache_loader == "false",
        "davis_route_has_no_loading_context": loading_screen_context == "",
        "only_startup_and_davis_groups": groups == [
            "GROUP_STARTUP",
            "ALLIN1_MAP_DAVIS",
        ],
        "startup_group_is_inert": startup_group == [dlc_maps.CHANGESET_NAME],
        "davis_group_is_scoped": davis_group == ["ALLIN1_MAPS_DAVIS"],
        "no_global_map_group": not any(
            value in {"GROUP_MAP", "GROUP_MAP_SP"} for value in groups
        ),
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"Davis canary topology failed closed: {failed}")
    return {
        "checks": checks,
        "asset_count": len(expected_files),
        "assets": expected_files,
        "startup_rpf_enable_count": len(startup_enabled),
        "changesets": changesets,
        "groups": groups,
        "route": {
            "changeset": "ALLIN1_MAPS_DAVIS",
            "requires_loading_screen": False,
            "use_cache_loader": False,
            "loading_screen_context": "",
            "files_to_invalidate": route_invalidates,
            "files_to_disable": route_disables,
            "files_to_enable": davis_enabled,
        },
    }


def _file_manifest(root: Path) -> dict[str, dict[str, Any]]:
    if not root.exists():
        return {}
    if not root.is_dir():
        raise RuntimeError(f"Expected a directory: {root}")
    return {
        path.relative_to(root).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _copy_tree_verified(source: Path, destination: Path) -> dict[str, Any]:
    expected = _file_manifest(source)
    shutil.copytree(source, destination)
    observed = _file_manifest(destination)
    if observed != expected:
        shutil.rmtree(destination, ignore_errors=True)
        raise RuntimeError("The existing map-pack backup failed verification.")
    return expected


def _dlclist_items(payload: bytes) -> list[str]:
    try:
        root = etree.fromstring(payload)
    except etree.XMLSyntaxError as exc:
        raise RuntimeError(f"dlclist.xml is malformed: {exc}") from exc
    return [
        (item.text or "").strip()
        for item in root.xpath("//*[local-name()='Paths']/*[local-name()='Item']")
        if (item.text or "").strip()
    ]


def _extract_dlclist(
    patcher: Path,
    game: Path,
    mods_archive: Path,
    output: Path,
) -> bytes:
    output.unlink(missing_ok=True)
    _run_tool(
        patcher,
        ["extract-entry", game, mods_archive, DLCLIST_ENTRY, output],
        operation="Extract dlclist.xml",
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("RpfPatcher returned no dlclist.xml payload.")
    return output.read_bytes()


def _verify_registration_delta(before: bytes, after: bytes) -> None:
    before_items = _dlclist_items(before)
    after_items = _dlclist_items(after)
    expected = PACK_ENTRY.rstrip("/").casefold()
    before_count = sum(
        item.rstrip("/").casefold() == expected for item in before_items
    )
    after_count = sum(
        item.rstrip("/").casefold() == expected for item in after_items
    )
    if before_count:
        raise RuntimeError(
            "allin1_maps was already registered; restore the quarantined "
            "baseline before running this canary."
        )
    normalized_after_without_canary = [
        item for item in after_items
        if item.rstrip("/").casefold() != expected
    ]
    if after_count != 1 or normalized_after_without_canary != before_items:
        raise RuntimeError(
            "DLC registration changed entries outside the exact allin1_maps delta."
        )


def _build_archive(
    game: Path,
    patcher: Path,
    work: Path,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    assets = _davis_assets()
    dlc_root = dlc_maps.create_dlc_pack(
        work,
        assets=assets,
        layout=dlc_maps.DEFERRED_PACK_LAYOUT,
    )
    topology = inspect_davis_topology(dlc_root)
    manifest = work / "davis-assets.tsv"
    manifest.write_text(
        "".join(
            f"{asset.source_path}\t{asset.destination_path}\n"
            for asset in assets
        ),
        encoding="utf-8",
    )

    grouped: dict[tuple[str, str], list[dlc_maps.MapAsset]] = {}
    source_archives: dict[tuple[str, str], dict[str, Any]] = {}
    for asset in assets:
        grouped.setdefault(
            (asset.source_pack, asset.source_archive_name), []
        ).append(asset)
    for index, ((source_pack, archive_name), selected) in enumerate(
        grouped.items()
    ):
        source_archive = selected[0].source_archive(game)
        if not source_archive.is_file():
            raise FileNotFoundError(
                f"Required {source_pack} archive is missing: {source_archive}"
            )
        try:
            source_archive_relative = source_archive.relative_to(game).as_posix()
        except ValueError as exc:
            raise RuntimeError(
                "The Davis source archive escaped the declared GTA root."
            ) from exc
        source_archives[(source_pack, archive_name)] = {
            "pack": source_pack,
            "archive": archive_name,
            "source": "stock",
            "path": source_archive_relative,
            "size": source_archive.stat().st_size,
            "mtime_ns": source_archive.stat().st_mtime_ns,
            "sha256": _sha256(source_archive),
        }
        extraction = work / f"extract-{index}.tsv"
        extraction.write_text(
            "".join(
                f"{asset.source_path}\t{asset.destination_path}\n"
                for asset in selected
            ),
            encoding="utf-8",
        )
        _run_tool(
            patcher,
            [
                "extract-entries", game, source_archive,
                extraction, dlc_root,
            ],
            operation=f"Extract {source_pack} Davis assets",
        )

    missing = dlc_maps.validate_staged_assets(dlc_root, assets=assets)
    if missing:
        raise RuntimeError(
            "Davis staging is incomplete: "
            + ", ".join(str(path) for path in missing)
        )
    dlc_maps.filter_staged_proxy_assets(dlc_root, assets=assets)
    sources: list[dict[str, Any]] = []
    for asset in assets:
        staged = asset.destination(dlc_root)
        sources.append({
            "source_pack": asset.source_pack,
            "source_archive": asset.source_archive_name,
            "source_path": asset.source_path,
            "destination_path": asset.destination_path,
            "source_asset_bytes": staged.stat().st_size,
            "source_asset_sha256": _sha256(staged),
        })
    _run_tool(
        patcher,
        ["open-rpfs", game, manifest, dlc_root],
        operation="Convert Davis archives for the selected edition",
    )
    output = work / "allin1_maps-davis-canary.rpf"
    _run_tool(
        patcher,
        ["build-dlc", dlc_root, output, "--gta-path", game],
        operation="Build Davis registration canary",
    )
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("The Davis canary build produced no DLC archive.")
    _run_tool(
        patcher,
        ["verify-map-dlc", output, manifest],
        operation="Verify Davis registration canary",
    )
    return output, manifest, topology, {
        "source_archives": list(source_archives.values()),
        "source_assets": sources,
    }


def _marker_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return {
        key.strip().casefold(): value.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }


def _davis_runtime_receipt(
    archive: Path,
    topology: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Create the fixed, machine-independent Davis runtime contract."""
    references = list(topology.get("assets", []))
    route = dict(topology.get("route", {}))
    source_archives = list(provenance.get("source_archives", []))
    source_assets = list(provenance.get("source_assets", []))
    if (
        len(references) != 2
        or topology.get("startup_rpf_enable_count") != 0
        or topology.get("groups") != [
            "GROUP_STARTUP", "ALLIN1_MAP_DAVIS",
        ]
        or route.get("changeset") != "ALLIN1_MAPS_DAVIS"
        or route.get("files_to_enable") != references
        or route.get("requires_loading_screen") is not False
        or route.get("use_cache_loader") is not False
        or route.get("loading_screen_context") != ""
        or route.get("files_to_invalidate") != []
        or route.get("files_to_disable") != []
        or len(source_archives) != 1
        or len(source_assets) != 2
    ):
        raise RuntimeError(
            "The Davis streaming receipt cannot be emitted from an "
            "unverified topology or provenance set."
        )
    source_archive = source_archives[0]
    if (
        source_archive.get("pack") != "mptuner"
        or source_archive.get("archive") != "dlc.rpf"
        or source_archive.get("source") not in {"stock", "mods"}
        or Path(str(source_archive.get("path", ""))).is_absolute()
    ):
        raise RuntimeError("The Davis source archive provenance is invalid.")
    return {
        "schema": RUNTIME_RECEIPT_SCHEMA,
        "status": "verified",
        "package_id": RUNTIME_PACKAGE_ID,
        "pack_name": dlc_maps.DLC_NAME,
        "edition": "enhanced",
        "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
        "runtime_contract": RUNTIME_CONTRACT,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": _sha256(archive),
        "asset_count": 2,
        "startup_rpf_enable_count": 0,
        "properties": ["davis"],
        "declared_groups": ["GROUP_STARTUP", "ALLIN1_MAP_DAVIS"],
        "declared_changesets": [
            dlc_maps.CHANGESET_NAME, "ALLIN1_MAPS_DAVIS",
        ],
        "groups": [{
            "property": "davis",
            "group": "ALLIN1_MAP_DAVIS",
            "changesets": ["ALLIN1_MAPS_DAVIS"],
            "references": references,
            "routes": [route],
        }],
        "source_archives": source_archives,
        "sources": source_assets,
    }


def _is_davis_runtime_receipt(
    payload: Any, checkpoint: dict[str, Any],
) -> bool:
    if not isinstance(payload, dict):
        return False
    expected_files = [asset.filename for asset in _davis_assets()]
    expected_route = {
        "changeset": "ALLIN1_MAPS_DAVIS",
        "requires_loading_screen": False,
        "use_cache_loader": False,
        "loading_screen_context": "",
        "files_to_invalidate": [],
        "files_to_disable": [],
        "files_to_enable": expected_files,
    }
    return (
        payload.get("schema") == RUNTIME_RECEIPT_SCHEMA
        and payload.get("status") == "verified"
        and payload.get("package_id") == RUNTIME_PACKAGE_ID
        and payload.get("pack_name") == dlc_maps.DLC_NAME
        and payload.get("edition") == "enhanced"
        and payload.get("layout") == dlc_maps.DEFERRED_PACK_LAYOUT
        and payload.get("runtime_contract") == RUNTIME_CONTRACT
        and payload.get("archive_bytes") == checkpoint.get("archive_bytes")
        and payload.get("archive_sha256") == checkpoint.get("archive_sha256")
        and payload.get("asset_count") == 2
        and payload.get("startup_rpf_enable_count") == 0
        and payload.get("properties") == ["davis"]
        and payload.get("declared_groups") == [
            "GROUP_STARTUP", "ALLIN1_MAP_DAVIS",
        ]
        and payload.get("declared_changesets") == [
            dlc_maps.CHANGESET_NAME, "ALLIN1_MAPS_DAVIS",
        ]
        and payload.get("groups") == [{
            "property": "davis",
            "group": "ALLIN1_MAP_DAVIS",
            "changesets": ["ALLIN1_MAPS_DAVIS"],
            "references": expected_files,
            "routes": [expected_route],
        }]
        and payload.get("source_archives") == checkpoint.get(
            "source_archives"
        )
        and payload.get("sources") == checkpoint.get("sources")
    )


def _mark_streaming_runtime(marker: Path, archive: Path) -> None:
    existing = marker.read_text(encoding="utf-8")
    suffix = (
        f"receipt={RUNTIME_RECEIPT}\n"
        f"runtime_contract={RUNTIME_CONTRACT}\n"
        "property_scope=davis\n"
        f"archive_sha256={_sha256(archive)}\n"
    )
    _write_text_atomic(existing.rstrip() + "\n" + suffix, marker)


def install_davis_registration_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    """Install the dormant two-RPF canary without starting GTA."""
    if confirmation != INSTALL_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {INSTALL_CONFIRMATION!r} is required."
        )
    game = _assert_enhanced_root(Path(gta_path))
    _assert_game_closed(process_probe)
    hosts = _native_hosts(game)
    if hosts:
        raise RuntimeError(
            "Remove the experimental map host before the registration-only "
            "canary: " + ", ".join(hosts)
        )

    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    mods_archive = game / "mods" / "update" / "update.rpf"
    if not mods_archive.is_file():
        raise RuntimeError(
            "A complete mods/update/update.rpf must already exist. The canary "
            "will not create or replace that archive."
        )

    state = _state_root(game, state_root)
    if state.exists():
        raise RuntimeError(
            f"A Davis canary checkpoint already exists at {state}; inspect "
            "status and roll it back before starting another."
        )
    state.mkdir(parents=True)
    work = state / "work"
    work.mkdir()
    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
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
    _write_json_atomic(journal, journal_path)

    mutated = False
    try:
        archive, manifest, topology, _sources = _build_archive(
            game, tool, work,
        )
        original_payload = _extract_dlclist(
            tool, game, mods_archive, original_dlclist,
        )
        if any(
            item.rstrip("/").casefold() == PACK_ENTRY.rstrip("/").casefold()
            for item in _dlclist_items(original_payload)
        ):
            raise RuntimeError(
                "allin1_maps is already registered; this is not the required "
                "quarantined baseline."
            )
        original_manifest: dict[str, Any] = {}
        if pack_existed:
            if not destination.is_dir():
                raise RuntimeError("The existing allin1_maps path is not a directory.")
            original_manifest = _copy_tree_verified(destination, backup)

        # The journal and exact backups exist before the first game mutation.
        journal.update({
            "status": "ready_to_mutate",
            "original_dlclist_sha256": _sha256(original_dlclist),
            "original_pack_manifest": original_manifest,
        })
        _write_json_atomic(journal, journal_path)

        # From this point forward every failure must restore the persistent
        # checkpoint, including a deploy failure after the old pack is removed.
        mutated = True
        if destination.exists():
            shutil.rmtree(destination)
        dlc_maps.deploy_dlc_rpf(
            archive,
            game,
            layout=dlc_maps.DEFERRED_PACK_LAYOUT,
            asset_count=2,
        )
        runtime_receipt = destination / RUNTIME_RECEIPT
        runtime_receipt.unlink(missing_ok=True)
        _run_tool(
            tool,
            ["register-dlc", game, dlc_maps.DLC_NAME],
            operation="Register Davis canary DLC",
        )
        registered_payload = _extract_dlclist(
            tool, game, mods_archive, registered_dlclist,
        )
        _verify_registration_delta(original_payload, registered_payload)
        marker = destination / dlc_maps.ACTIVE_MARKER
        marker_values = _marker_fields(marker)
        expected_marker = {
            "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
            "archive_registration": "property-groups",
            "activation": "property-group-native-host-required",
            "asset_count": "2",
        }
        if any(marker_values.get(key) != value for key, value in expected_marker.items()):
            raise RuntimeError("The deployed Davis marker does not match the canary contract.")
        deployed_archive = destination / "dlc.rpf"

        # Preserve compact, machine-independent evidence; local absolute paths
        # are reconstructed from the explicit --gta-path and never serialized.
        (state / "content.xml").write_bytes((work / dlc_maps.DLC_NAME / "content.xml").read_bytes())
        (state / "setup2.xml").write_bytes((work / dlc_maps.DLC_NAME / "setup2.xml").read_bytes())
        (state / "davis-assets.tsv").write_bytes(manifest.read_bytes())
        shutil.rmtree(work)
        receipt = {
            "schema": STATE_SCHEMA,
            "canary_id": CANARY_ID,
            "transaction_id": transaction_id,
            "status": "installed_registration_only",
            "edition": "enhanced",
            "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
            "pack_name": dlc_maps.DLC_NAME,
            "asset_count": 2,
            "startup_rpf_enable_count": topology["startup_rpf_enable_count"],
            "groups": topology["groups"],
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": _sha256(deployed_archive),
            "marker_sha256": _sha256(marker),
            "original_dlclist_sha256": _sha256(original_dlclist),
            "registered_dlclist_sha256": _sha256(registered_dlclist),
            "pack_existed": pack_existed,
            "original_pack_manifest": original_manifest,
            "gameconfig_changed": False,
            "native_host_installed": False,
            "native_group_execution_enabled": False,
            "runtime_receipt_present": False,
        }
        # Commit marker: no game/install mutation or state write may follow.
        _write_json_atomic(receipt, receipt_path)
        return receipt
    except Exception:
        if mutated:
            try:
                _restore_from_checkpoint(
                    game, state, tool, strict_current=False,
                )
            except Exception:
                # Keep every backup and journal available for explicit rollback.
                pass
        raise


def _load_checkpoint(state: Path) -> dict[str, Any]:
    for name in ("install-receipt.json", "journal.json"):
        path = state / name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(payload, dict)
                and payload.get("schema") == STATE_SCHEMA
                and payload.get("canary_id") == CANARY_ID
            ):
                return payload
    raise FileNotFoundError("No valid Davis canary checkpoint exists.")


def _restore_from_checkpoint(
    game: Path,
    state: Path,
    patcher: Path,
    *,
    strict_current: bool,
) -> dict[str, Any]:
    checkpoint = _load_checkpoint(state)
    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    mods_archive = game / "mods" / "update" / "update.rpf"
    original_dlclist = state / "original-dlclist.xml"
    if not mods_archive.is_file() or not original_dlclist.is_file():
        raise RuntimeError("The exact dlclist rollback checkpoint is incomplete.")
    if _sha256(original_dlclist) != checkpoint.get("original_dlclist_sha256"):
        raise RuntimeError("The original dlclist rollback payload was tampered with.")

    if strict_current and checkpoint.get("status") == "installed_registration_only":
        current_archive = destination / "dlc.rpf"
        current_marker = destination / dlc_maps.ACTIVE_MARKER
        if (
            not current_archive.is_file()
            or current_archive.stat().st_size != checkpoint.get("archive_bytes")
            or _sha256(current_archive) != checkpoint.get("archive_sha256")
            or not current_marker.is_file()
            or _sha256(current_marker) != checkpoint.get("marker_sha256")
        ):
            raise RuntimeError(
                "The active canary pack changed after installation; rollback "
                "refuses to overwrite unreviewed files."
            )
        with tempfile.TemporaryDirectory(prefix="allin1-davis-status-") as tmp:
            current = Path(tmp) / "dlclist.xml"
            _extract_dlclist(patcher, game, mods_archive, current)
            if _sha256(current) != checkpoint.get("registered_dlclist_sha256"):
                raise RuntimeError(
                    "dlclist.xml changed after canary installation; exact "
                    "rollback requires review."
                )

    _run_tool(
        patcher,
        ["replace-entry", game, mods_archive, DLCLIST_ENTRY, original_dlclist],
        operation="Restore exact pre-canary dlclist.xml",
    )
    verified = state / "verified-restored-dlclist.xml"
    restored_payload = _extract_dlclist(
        patcher, game, mods_archive, verified,
    )
    if restored_payload != original_dlclist.read_bytes():
        raise RuntimeError("The restored dlclist.xml does not match its backup.")

    if destination.exists():
        shutil.rmtree(destination)
    if bool(checkpoint.get("pack_existed")):
        backup = state / "original-pack"
        if not backup.is_dir():
            raise RuntimeError("The original allin1_maps backup is missing.")
        shutil.copytree(backup, destination)
        if _file_manifest(destination) != checkpoint.get("original_pack_manifest"):
            raise RuntimeError("The restored allin1_maps directory failed verification.")
    return checkpoint


def rollback_davis_registration_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    if confirmation != ROLLBACK_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {ROLLBACK_CONFIRMATION!r} is required."
        )
    game = _assert_enhanced_root(Path(gta_path))
    _assert_game_closed(process_probe)
    state = _state_root(game, state_root)
    completed = state / "rollback-receipt.json"
    if completed.is_file():
        return json.loads(completed.read_text(encoding="utf-8"))
    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
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
    _write_json_atomic(result, completed)
    return result


def read_davis_registration_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    game = _assert_enhanced_root(Path(gta_path))
    state = _state_root(game, state_root)
    names = {name.casefold() for name in process_probe()}
    game_running = bool(
        names.intersection({"gta5.exe", "gta5_enhanced.exe"})
    )
    rollback = state / "rollback-receipt.json"
    if rollback.is_file():
        payload = json.loads(rollback.read_text(encoding="utf-8"))
        return {
            **payload,
            "game_running": game_running,
            "healthy": True,
        }
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

    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    archive = destination / "dlc.rpf"
    marker = destination / dlc_maps.ACTIVE_MARKER
    marker_values = _marker_fields(marker)
    hosts = _native_hosts(game)
    runtime_receipt = destination / RUNTIME_RECEIPT
    archive_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and _sha256(archive) == checkpoint.get("archive_sha256")
    )
    marker_ok = (
        marker.is_file()
        and _sha256(marker) == checkpoint.get("marker_sha256")
        and marker_values.get("layout") == dlc_maps.DEFERRED_PACK_LAYOUT
        and marker_values.get("archive_registration") == "property-groups"
        and marker_values.get("activation") ==
            "property-group-native-host-required"
        and marker_values.get("asset_count") == "2"
    )
    registration_count: int | None = None
    registration_ok = False
    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
    mods_archive = game / "mods" / "update" / "update.rpf"
    if tool.is_file() and mods_archive.is_file():
        with tempfile.TemporaryDirectory(prefix="allin1-davis-status-") as tmp:
            current = Path(tmp) / "dlclist.xml"
            payload = _extract_dlclist(tool, game, mods_archive, current)
            expected = PACK_ENTRY.rstrip("/").casefold()
            registration_count = sum(
                item.rstrip("/").casefold() == expected
                for item in _dlclist_items(payload)
            )
            registration_ok = (
                registration_count == 1
                and _sha256(current) == checkpoint.get(
                    "registered_dlclist_sha256"
                )
            )
    topology_ok = (
        checkpoint.get("asset_count") == 2
        and checkpoint.get("startup_rpf_enable_count") == 0
        and checkpoint.get("groups") == [
            "GROUP_STARTUP", "ALLIN1_MAP_DAVIS"
        ]
    )
    checks = {
        "archive": archive_ok,
        "marker": marker_ok,
        "registration": registration_ok,
        "zero_startup_rpfs": topology_ok,
        "runtime_receipt_absent": not runtime_receipt.exists(),
        "native_host_absent": not hosts,
        "native_group_execution_disabled": checkpoint.get(
            "native_group_execution_enabled"
        ) is False,
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
        "archive_sha256": _sha256(archive) if archive.is_file() else None,
        "marker": marker_values,
        "asset_count": checkpoint.get("asset_count"),
        "startup_rpf_enable_count": checkpoint.get(
            "startup_rpf_enable_count"
        ),
        "groups": checkpoint.get("groups"),
    }


def _load_streaming_checkpoint(state: Path) -> dict[str, Any]:
    for name in ("install-receipt.json", "journal.json"):
        path = state / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("schema") == STREAMING_STATE_SCHEMA
            and payload.get("canary_id") == STREAMING_CANARY_ID
        ):
            return payload
    raise FileNotFoundError(
        "No valid Davis streaming canary v2 checkpoint exists."
    )


def install_davis_streaming_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    """Install the exact Davis-only runtime package without starting GTA."""
    if confirmation != STREAMING_INSTALL_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {STREAMING_INSTALL_CONFIRMATION!r} is "
            "required."
        )
    game = _assert_enhanced_root(Path(gta_path))
    _assert_game_closed(process_probe)
    hosts = _native_hosts(game)
    if hosts:
        raise RuntimeError(
            "Remove the experimental map host before the isolated streaming "
            "canary: " + ", ".join(hosts)
        )

    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
    if not tool.is_file():
        raise FileNotFoundError(f"RpfPatcher is missing: {tool}")
    mods_archive = game / "mods" / "update" / "update.rpf"
    if not mods_archive.is_file():
        raise RuntimeError(
            "A complete mods/update/update.rpf must already exist. The "
            "streaming canary will not create or replace that archive."
        )

    state = _streaming_state_root(game, state_root)
    if state.exists():
        raise RuntimeError(
            f"A Davis streaming v2 checkpoint already exists at {state}; "
            "inspect status and roll it back before starting another."
        )
    state.mkdir(parents=True)
    work = state / "work"
    work.mkdir()
    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    backup = state / "original-pack"
    original_dlclist = state / "original-dlclist.xml"
    registered_dlclist = state / "registered-dlclist.xml"
    journal_path = state / "journal.json"
    receipt_path = state / "install-receipt.json"
    pack_existed = destination.exists()
    transaction_id = uuid.uuid4().hex
    journal: dict[str, Any] = {
        "schema": STREAMING_STATE_SCHEMA,
        "canary_id": STREAMING_CANARY_ID,
        "transaction_id": transaction_id,
        "edition": "enhanced",
        "status": "building",
        "pack_existed": pack_existed,
        "gameconfig_changed": False,
        "native_host_installed": False,
    }
    _write_json_atomic(journal, journal_path)

    mutated = False
    try:
        archive, manifest, topology, provenance = _build_archive(
            game, tool, work,
        )
        original_payload = _extract_dlclist(
            tool, game, mods_archive, original_dlclist,
        )
        if any(
            item.rstrip("/").casefold() == PACK_ENTRY.rstrip("/").casefold()
            for item in _dlclist_items(original_payload)
        ):
            raise RuntimeError(
                "allin1_maps is already registered; this canary requires a "
                "quarantined baseline."
            )
        original_manifest: dict[str, Any] = {}
        if pack_existed:
            if not destination.is_dir():
                raise RuntimeError(
                    "The existing allin1_maps path is not a directory."
                )
            original_manifest = _copy_tree_verified(destination, backup)

        journal.update({
            "status": "ready_to_mutate",
            "original_dlclist_sha256": _sha256(original_dlclist),
            "original_pack_manifest": original_manifest,
        })
        _write_json_atomic(journal, journal_path)

        mutated = True
        if destination.exists():
            shutil.rmtree(destination)
        dlc_maps.deploy_dlc_rpf(
            archive,
            game,
            layout=dlc_maps.DEFERRED_PACK_LAYOUT,
            asset_count=2,
        )
        marker = destination / dlc_maps.ACTIVE_MARKER
        deployed_archive = destination / "dlc.rpf"
        _mark_streaming_runtime(marker, deployed_archive)
        runtime_payload = _davis_runtime_receipt(
            deployed_archive, topology, provenance,
        )
        runtime_receipt = destination / RUNTIME_RECEIPT
        _write_json_atomic(runtime_payload, runtime_receipt)

        _run_tool(
            tool,
            ["register-dlc", game, dlc_maps.DLC_NAME],
            operation="Register isolated Davis streaming canary DLC",
        )
        registered_payload = _extract_dlclist(
            tool, game, mods_archive, registered_dlclist,
        )
        _verify_registration_delta(original_payload, registered_payload)
        marker_values = _marker_fields(marker)
        expected_marker = {
            "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
            "archive_registration": "property-groups",
            "activation": "property-group-native-host-required",
            "asset_count": "2",
            "receipt": RUNTIME_RECEIPT,
            "runtime_contract": RUNTIME_CONTRACT,
            "property_scope": "davis",
            "archive_sha256": _sha256(deployed_archive),
        }
        if any(
            marker_values.get(key) != value
            for key, value in expected_marker.items()
        ):
            raise RuntimeError(
                "The deployed Davis streaming marker does not match the "
                "verified runtime contract."
            )

        (state / "content.xml").write_bytes(
            (work / dlc_maps.DLC_NAME / "content.xml").read_bytes()
        )
        (state / "setup2.xml").write_bytes(
            (work / dlc_maps.DLC_NAME / "setup2.xml").read_bytes()
        )
        (state / "davis-assets.tsv").write_bytes(manifest.read_bytes())
        (state / "runtime-receipt.json").write_bytes(
            runtime_receipt.read_bytes()
        )
        shutil.rmtree(work)
        receipt = {
            "schema": STREAMING_STATE_SCHEMA,
            "canary_id": STREAMING_CANARY_ID,
            "transaction_id": transaction_id,
            "status": "installed_streaming_verified",
            "edition": "enhanced",
            "layout": dlc_maps.DEFERRED_PACK_LAYOUT,
            "runtime_contract": RUNTIME_CONTRACT,
            "package_id": RUNTIME_PACKAGE_ID,
            "pack_name": dlc_maps.DLC_NAME,
            "properties": ["davis"],
            "asset_count": 2,
            "startup_rpf_enable_count": 0,
            "groups": topology["groups"],
            "archive_bytes": deployed_archive.stat().st_size,
            "archive_sha256": _sha256(deployed_archive),
            "marker_sha256": _sha256(marker),
            "runtime_receipt_sha256": _sha256(runtime_receipt),
            "source_archives": provenance["source_archives"],
            "sources": provenance["source_assets"],
            "original_dlclist_sha256": _sha256(original_dlclist),
            "registered_dlclist_sha256": _sha256(registered_dlclist),
            "pack_existed": pack_existed,
            "original_pack_manifest": original_manifest,
            "gameconfig_changed": False,
            "native_host_installed": False,
            "native_group_execution_enabled": True,
            "runtime_receipt_present": True,
        }
        _write_json_atomic(receipt, receipt_path)
        return receipt
    except Exception:
        if mutated:
            try:
                _restore_streaming_from_checkpoint(
                    game, state, tool, strict_current=False,
                )
            except Exception:
                pass
        raise


def _restore_streaming_from_checkpoint(
    game: Path,
    state: Path,
    patcher: Path,
    *,
    strict_current: bool,
) -> dict[str, Any]:
    checkpoint = _load_streaming_checkpoint(state)
    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    mods_archive = game / "mods" / "update" / "update.rpf"
    original_dlclist = state / "original-dlclist.xml"
    if not mods_archive.is_file() or not original_dlclist.is_file():
        raise RuntimeError(
            "The exact streaming-canary dlclist rollback checkpoint is "
            "incomplete."
        )
    if _sha256(original_dlclist) != checkpoint.get("original_dlclist_sha256"):
        raise RuntimeError(
            "The original streaming-canary dlclist payload was tampered with."
        )

    if (
        strict_current
        and checkpoint.get("status") == "installed_streaming_verified"
    ):
        current_archive = destination / "dlc.rpf"
        current_marker = destination / dlc_maps.ACTIVE_MARKER
        current_runtime = destination / RUNTIME_RECEIPT
        if (
            not current_archive.is_file()
            or current_archive.stat().st_size != checkpoint.get("archive_bytes")
            or _sha256(current_archive) != checkpoint.get("archive_sha256")
            or not current_marker.is_file()
            or _sha256(current_marker) != checkpoint.get("marker_sha256")
            or not current_runtime.is_file()
            or _sha256(current_runtime) != checkpoint.get(
                "runtime_receipt_sha256"
            )
        ):
            raise RuntimeError(
                "The active Davis streaming canary changed after "
                "installation; rollback refuses to overwrite unreviewed files."
            )
        with tempfile.TemporaryDirectory(
            prefix="allin1-davis-streaming-status-"
        ) as tmp:
            current = Path(tmp) / "dlclist.xml"
            _extract_dlclist(patcher, game, mods_archive, current)
            if _sha256(current) != checkpoint.get("registered_dlclist_sha256"):
                raise RuntimeError(
                    "dlclist.xml changed after streaming-canary installation; "
                    "exact rollback requires review."
                )

    _run_tool(
        patcher,
        ["replace-entry", game, mods_archive, DLCLIST_ENTRY, original_dlclist],
        operation="Restore exact pre-streaming-canary dlclist.xml",
    )
    verified = state / "verified-restored-dlclist.xml"
    restored_payload = _extract_dlclist(
        patcher, game, mods_archive, verified,
    )
    if restored_payload != original_dlclist.read_bytes():
        raise RuntimeError(
            "The restored dlclist.xml does not match its streaming-canary "
            "backup."
        )

    if destination.exists():
        shutil.rmtree(destination)
    if bool(checkpoint.get("pack_existed")):
        backup = state / "original-pack"
        if not backup.is_dir():
            raise RuntimeError("The original allin1_maps backup is missing.")
        shutil.copytree(backup, destination)
        if _file_manifest(destination) != checkpoint.get(
            "original_pack_manifest"
        ):
            raise RuntimeError(
                "The restored allin1_maps directory failed verification."
            )
    return checkpoint


def rollback_davis_streaming_canary(
    gta_path: Path,
    *,
    confirmation: str,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    if confirmation != STREAMING_ROLLBACK_CONFIRMATION:
        raise PermissionError(
            f"Exact confirmation {STREAMING_ROLLBACK_CONFIRMATION!r} is "
            "required."
        )
    game = _assert_enhanced_root(Path(gta_path))
    _assert_game_closed(process_probe)
    state = _streaming_state_root(game, state_root)
    completed = state / "rollback-receipt.json"
    if completed.is_file():
        return json.loads(completed.read_text(encoding="utf-8"))
    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
    checkpoint = _restore_streaming_from_checkpoint(
        game, state, tool, strict_current=True,
    )
    (state / "install-receipt.json").unlink(missing_ok=True)
    result = {
        "schema": STREAMING_STATE_SCHEMA,
        "canary_id": STREAMING_CANARY_ID,
        "transaction_id": checkpoint.get("transaction_id"),
        "status": "rolled_back",
        "restored_dlclist_sha256": checkpoint.get(
            "original_dlclist_sha256"
        ),
        "restored_original_pack": bool(checkpoint.get("pack_existed")),
    }
    _write_json_atomic(result, completed)
    return result


def read_davis_streaming_canary_status(
    gta_path: Path,
    *,
    state_root: Path | None = None,
    patcher: Path | None = None,
    process_probe: Callable[[], set[str]] = _default_process_names,
) -> dict[str, Any]:
    game = _assert_enhanced_root(Path(gta_path))
    state = _streaming_state_root(game, state_root)
    names = {name.casefold() for name in process_probe()}
    game_running = bool(
        names.intersection({"gta5.exe", "gta5_enhanced.exe"})
    )
    rollback = state / "rollback-receipt.json"
    if rollback.is_file():
        payload = json.loads(rollback.read_text(encoding="utf-8"))
        return {**payload, "game_running": game_running, "healthy": True}
    try:
        checkpoint = _load_streaming_checkpoint(state)
    except FileNotFoundError:
        return {
            "schema": STREAMING_STATE_SCHEMA,
            "canary_id": STREAMING_CANARY_ID,
            "status": "absent",
            "edition": "enhanced",
            "game_running": game_running,
            "healthy": True,
        }

    destination = (
        game / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    archive = destination / "dlc.rpf"
    marker = destination / dlc_maps.ACTIVE_MARKER
    runtime_receipt = destination / RUNTIME_RECEIPT
    marker_values = _marker_fields(marker)
    archive_ok = (
        archive.is_file()
        and archive.stat().st_size == checkpoint.get("archive_bytes")
        and _sha256(archive) == checkpoint.get("archive_sha256")
    )
    marker_ok = (
        marker.is_file()
        and _sha256(marker) == checkpoint.get("marker_sha256")
        and marker_values.get("layout") == dlc_maps.DEFERRED_PACK_LAYOUT
        and marker_values.get("archive_registration") == "property-groups"
        and marker_values.get("activation") ==
            "property-group-native-host-required"
        and marker_values.get("asset_count") == "2"
        and marker_values.get("receipt") == RUNTIME_RECEIPT
        and marker_values.get("runtime_contract") == RUNTIME_CONTRACT
        and marker_values.get("property_scope") == "davis"
        and marker_values.get("archive_sha256") == checkpoint.get(
            "archive_sha256"
        )
    )
    runtime_payload: Any = None
    runtime_ok = False
    if runtime_receipt.is_file():
        try:
            runtime_payload = json.loads(
                runtime_receipt.read_text(encoding="utf-8")
            )
            runtime_ok = (
                _sha256(runtime_receipt) == checkpoint.get(
                    "runtime_receipt_sha256"
                )
                and _is_davis_runtime_receipt(runtime_payload, checkpoint)
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            runtime_ok = False

    registration_count: int | None = None
    registration_ok = False
    tool = (
        Path(patcher).resolve()
        if patcher is not None
        else resource_root()
        / "tools" / "RpfPatcher" / "RpfPatcher.exe"
    )
    mods_archive = game / "mods" / "update" / "update.rpf"
    if tool.is_file() and mods_archive.is_file():
        with tempfile.TemporaryDirectory(
            prefix="allin1-davis-streaming-status-"
        ) as tmp:
            current = Path(tmp) / "dlclist.xml"
            payload = _extract_dlclist(tool, game, mods_archive, current)
            expected = PACK_ENTRY.rstrip("/").casefold()
            registration_count = sum(
                item.rstrip("/").casefold() == expected
                for item in _dlclist_items(payload)
            )
            registration_ok = (
                registration_count == 1
                and _sha256(current) == checkpoint.get(
                    "registered_dlclist_sha256"
                )
            )
    topology_ok = (
        checkpoint.get("asset_count") == 2
        and checkpoint.get("startup_rpf_enable_count") == 0
        and checkpoint.get("groups") == [
            "GROUP_STARTUP", "ALLIN1_MAP_DAVIS",
        ]
        and checkpoint.get("properties") == ["davis"]
        and len(checkpoint.get("source_archives", [])) == 1
        and len(checkpoint.get("sources", [])) == 2
    )
    hosts = _native_hosts(game)
    checks = {
        "archive": archive_ok,
        "marker": marker_ok,
        "registration": registration_ok,
        "exact_isolated_topology": topology_ok,
        "runtime_receipt_verified": runtime_ok,
        "native_host_absent": not hosts,
        "native_group_execution_enabled": checkpoint.get(
            "native_group_execution_enabled"
        ) is True,
        "gameconfig_unchanged": checkpoint.get("gameconfig_changed") is False,
    }
    return {
        "schema": STREAMING_STATE_SCHEMA,
        "canary_id": STREAMING_CANARY_ID,
        "status": checkpoint.get("status", "pending"),
        "edition": "enhanced",
        "game_running": game_running,
        "healthy": all(checks.values()),
        "checks": checks,
        "registration_count": registration_count,
        "native_hosts": hosts,
        "archive_bytes": archive.stat().st_size if archive.is_file() else 0,
        "archive_sha256": _sha256(archive) if archive.is_file() else None,
        "marker": marker_values,
        "runtime_receipt": runtime_payload,
        "asset_count": checkpoint.get("asset_count"),
        "startup_rpf_enable_count": checkpoint.get(
            "startup_rpf_enable_count"
        ),
        "properties": checkpoint.get("properties"),
        "groups": checkpoint.get("groups"),
        "source_archives": checkpoint.get("source_archives"),
    }
