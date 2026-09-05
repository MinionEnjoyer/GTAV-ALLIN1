"""Main installer orchestrator.

Coordinates the install/uninstall flow: config loading, GTA V detection,
and ALLIN1 script deployment.

File placement:
- <GTA V root>/scripts/ALLIN1.dll — SHVDN script loaded at runtime.
  Spawns the configured GTA Online DLC vehicle catalog into Story Mode traffic.
- <GTA V root>/scripts/ALLIN1.toml — Config deployed from project config.toml.

Prerequisites:
- ScriptHookV (dinput8.dll + ScriptHookV.dll)
- ScriptHookVDotNet Enhanced (ScriptHookVDotNet.asi + ScriptHookVDotNet3.dll
  + MinHook.x64.dll)
- An edition-compatible RPF loader — optional and installed only with consent
  when GBAY artwork is enabled
"""

from __future__ import annotations

import logging
import json
import hashlib
import os
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from allin1 import __version__, asi_loader
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.extensions import (
    ExtensionCatalog,
    ExtensionRegistry,
    settings_from_config,
)
from allin1.health import inspect_windows_binary, is_shvdn_runtime_ready
from allin1.garage_map_detection import (
    CACHE_RELATIVE_PATH as GARAGE_MAP_CACHE_RELATIVE,
    refresh_garage_map_detection,
)
from allin1.launch_policy import remove_retired_offline_policy
from allin1.preview_assets import GEAR_PREVIEW_ITEMS, WORLD_ASSET_PREVIEW_ITEMS
from allin1.processes import run_hidden
from allin1.reactor_bridge_contract import (
    CONTRACT_FILENAME as REACTOR_BRIDGE_CONTRACT_FILENAME,
    validate_reactor_bridge_pair,
)
from allin1.rpf_loader import (
    RpfLoaderInstallError, install_recommended_rpf_loader,
    inspect_rpf_loader, uninstall_managed_rpf_loader,
)
from allin1.vehicles.database import VehicleDatabase
from allin1.versioning import VERSION_FILE, write_installed_version
from allin1.release_paths import no_links, tree_files

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

log = logging.getLogger("allin1.installer")

DLL_FILENAME = "ALLIN1.dll"
REACTOR_BRIDGE_FILENAME = "ALLIN1.ReactorBridge.plugin"
GROUNDING_CATALOG_FILENAME = "ALLIN1_vehicle_grounding.json"
SCRIPTS_DIR = "scripts"
ALLIN1_DATA_DIR = "ALLIN1"  # Legacy data folder — cleaned up on install
RETIRED_LEMONUI_FILENAME = "LemonUI.SHVDN3.dll"
RETIRED_LEMONUI_SHA256 = (
    "B52EF80136152ED7AFDF335BD4FF16183977C8E27223AAF5C94A8C16E62E1AEB"
)
COLORED_SMOKE_PACK_ID = "allin1_smoke"
COLORED_SMOKE_QUARANTINE_REASON = (
    "Disabled after repeatable Story Mode startup hangs on GTA V Enhanced. "
    "The script-only colored smoke fallback remains available while the DLC "
    "metadata is rebuilt and validated against the current game data loader."
)

# Files from previous ALLIN1 versions to clean up
LEGACY_FILES = ("ALLIN1.asi", "ALLIN1.dll", "ALLIN1-Launcher.exe")

# Workspace artifacts written by development-only tools retired before 0.4.2.
# These are not user saves and are removed during every install/repair so an
# upgraded public installation does not retain dormant test data or DLLs.
RETIRED_DEVELOPER_ARTIFACTS = (
    "ALLIN1_height_check.toml",
    "ALLIN1_outfit_debug.log",
    "ALLIN1_entity_sets.log",
    "ALLIN1_preview_pending.toml",
    "ALLIN1_preview_pending.toml.bak",
    "ALLIN1_vehicle_grounding_outliers.json",
    "ALLIN1_vehicle_grounding_outliers.json.bak",
    "ALLIN1.dll.pre-0.3.1.bak",
    "ALLIN1.dll.pre-capture-modes.bak",
    "ALLIN1.dll.pre-furore-modelhash.bak",
    "ALLIN1.dll.pre-gbay-nav.bak",
    "ALLIN1.dll.pre-gbay-ux.bak",
    "ALLIN1.dll.pre-pushed-0.3.1.bak",
    "ALLIN1.dll.pre-seat-nav-fix.bak",
)
RETIRED_DEVELOPER_DIRECTORIES = (
    "ALLIN1_seat_tests",
)

# Resolve directories relative to this source file (project root).
from allin1.runtime_resources import resource_root

_PROJECT_ROOT = resource_root()
_SCRIPT_DIST_DIR = _PROJECT_ROOT / "script" / "dist"
_TOOLS_DIR = _PROJECT_ROOT / "tools"
_BUILTIN_CATALOG_PAYLOADS = {
    ("allin1.online-content", "story-vehicles"):
        _PROJECT_ROOT / "data" / "story_vehicles.json",
}
_BUILTIN_MAP_PAYLOADS = {
    "allin1.online-content":
        _PROJECT_ROOT / "data" / "maps" / "allin1-online-content",
}
_PRELOAD_MANIFEST_SOURCE = (
    _PROJECT_ROOT / "data" / "reactor" / "preload" / "allin1.json"
)
_PRELOAD_MANIFEST_RELATIVE = Path(
    "scripts", ".reactorv", "preload", "allin1.json"
)
_REACTOR_ARTWORK_RELATIVE = Path(
    "plugins", "ReactorV", "ui", "assets", "allin1"
)
_REACTOR_ARTWORK_SOURCES = {
    "vehicles": "previews",
    "weapons": "weapon_previews",
    "gear": "equipment_previews",
}

_MAP_GAMECONFIG_ENTRY = "common/data/gameconfig.xml"
_MAP_DLCLIST_ENTRY = "common/data/dlclist.xml"
_MAP_RUNTIME_RECEIPT = "allin1_maps.runtime.json"
from allin1.garage_bridge_contracts import (
    ADDITIONAL_INTERIOR_BRIDGES, GARMENT, GarageBridge,
)
_GARMENT_BRIDGE_PACK = "allin1_mp2024_02_garment_bridge"
_GARMENT_BRIDGE_DEVICE = "dlc_allin1_mp2024_02_garment_bridge"
_GARMENT_BRIDGE_GROUP = "ALLIN1_STOCK_MP2024_02_GARMENT_V1"
_GARMENT_BRIDGE_CHANGESET = "MP2024_02_MAP_UPDATE"
_GARMENT_BRIDGE_STARTUP = "ALLIN1_MP2024_02_GARMENT_BRIDGE_AUTOGEN"
_GARMENT_BRIDGE_MARKER = f"{_GARMENT_BRIDGE_PACK}.active"
_GARMENT_BRIDGE_RECEIPT = f"{_GARMENT_BRIDGE_PACK}.runtime.json"
_GARMENT_BRIDGE_IPLS = (
    "m24_2_int_placement",
    "m24_2_int_placement_interior_int_hacker_garage_milo_",
)

def _copy_atomic(source: Path, destination: Path) -> None:
    """Replace a deployed file without exposing a partial destination."""
    source, destination = no_links(source), no_links(destination)
    backup = no_links(destination.with_name(destination.name + ".bak"))
    if not source.is_file():
        raise FileNotFoundError(source)
    for path in (destination, backup):
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected a regular deployment file: {path}")
    existed = destination.exists()
    original_hash = _map_file_sha256(destination) if existed else None
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
    backup_stage = temporary.with_name(temporary.name + ".backup")
    try:
        shutil.copy2(source, temporary)
        if existed:
            shutil.copy2(no_links(destination), backup_stage)
            if _map_file_sha256(backup_stage) != original_hash:
                raise ValueError("Deployment destination changed during staging")
        if destination.exists() != existed or (existed and _map_file_sha256(no_links(destination)) != original_hash):
            raise ValueError("Deployment destination changed during staging")
        if existed:
            backup_stage.replace(no_links(backup))
        temporary.replace(no_links(destination))
    finally:
        temporary.unlink(missing_ok=True)
        backup_stage.unlink(missing_ok=True)


def _remove_retired_lemonui_dependency(scripts_dir: Path) -> Path | None:
    """Remove only the exact LemonUI binary shipped by older ALLIN1 builds.

    LemonUI is a shared ScriptHookVDotNet dependency and users may have their
    own copy for an unrelated mod.  A filename alone therefore is not proof of
    ownership.  The historical ALLIN1 payload hash is the only deletion
    authority used during upgrades and uninstall.
    """
    candidate = scripts_dir / RETIRED_LEMONUI_FILENAME
    if not candidate.is_file():
        return None

    try:
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest().upper()
    except OSError as exc:
        log.warning(
            "Could not inspect retired dependency %s; preserving it: %s",
            candidate, exc,
        )
        return None

    if actual != RETIRED_LEMONUI_SHA256:
        log.info(
            "Preserved non-ALLIN1 %s (SHA-256 %s)",
            RETIRED_LEMONUI_FILENAME, actual,
        )
        return None

    try:
        candidate.unlink()
    except OSError as exc:
        log.warning(
            "Could not remove retired ALLIN1 dependency %s: %s",
            candidate, exc,
        )
        return None
    log.info("Removed retired ALLIN1 dependency %s", candidate)
    return candidate


def _copy_files_transactionally(entries: tuple[tuple[Path, Path], ...]) -> None:
    """Replace a small owned file set with rollback on any partial failure."""
    checked = [(no_links(source), no_links(destination)) for source, destination in entries]
    targets = [str(destination).casefold() for _, destination in checked]
    if len(set(targets)) != len(targets):
        raise ValueError("Duplicate deployment destination")
    for source, destination in checked:
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists() and not destination.is_file():
            raise ValueError("Deployment destination is not a file")
        if any(str(parent).casefold() in targets for parent in destination.parents):
            raise ValueError("Deployment file/directory collision")
    staged: list[tuple[Path, Path, Path, bool, str | None]] = []
    committed: list[tuple[Path, Path, bool, str, str | None]] = []
    retain: set[Path] = set()
    rollback_errors: list[str] = []
    try:
        for source, destination in checked:
            destination.parent.mkdir(parents=True, exist_ok=True)
            identifier = uuid.uuid4().hex
            temporary = destination.with_name(destination.name + "." + identifier + ".pair.tmp")
            backup = destination.with_name(destination.name + "." + identifier + ".pair.bak")
            existed = destination.exists()
            original_hash = _map_file_sha256(destination) if existed else None
            staged.append((temporary, destination, backup, existed, original_hash))
            shutil.copy2(no_links(source), temporary)
            if existed:
                shutil.copy2(no_links(destination), backup)
                if _map_file_sha256(backup) != original_hash:
                    raise ValueError("Deployment destination changed during staging")

        for temporary, destination, backup, existed, original_hash in staged:
            no_links(destination)
            if destination.exists() != existed or (existed and _map_file_sha256(destination) != original_hash):
                raise ValueError("Deployment destination changed during staging")
            installed_hash = _map_file_sha256(temporary)
            os.replace(temporary, destination)
            committed.append((destination, backup, existed, installed_hash, original_hash))
    except Exception:
        for destination, backup, existed, installed_hash, original_hash in reversed(committed):
            try:
                no_links(destination)
                if not destination.is_file() or _map_file_sha256(destination) != installed_hash:
                    raise ValueError("Deployment changed after commit; automatic rollback refused")
                if existed:
                    if _map_file_sha256(no_links(backup)) != original_hash:
                        raise ValueError("Deployment rollback backup changed")
                    os.replace(backup, destination)
                else:
                    destination.unlink()
            except (OSError, ValueError) as exc:
                rollback_errors.append(f"{destination}: {exc}")
                if existed:
                    retain.add(backup)
        if rollback_errors:
            details = "; ".join(rollback_errors)
            if retain:
                details += "; rollback backups retained for review: " + ", ".join(str(path) for path in sorted(retain))
            raise RuntimeError("Deployment failed; automatic rollback incomplete: " + details)
        raise
    finally:
        for temporary, _destination, backup, _existed, _original_hash in staged:
            temporary.unlink(missing_ok=True)
            if backup not in retain:
                backup.unlink(missing_ok=True)


def _write_json_atomic(payload: dict, destination: Path) -> None:
    """Replace a JSON file while retaining the previous checkpoint."""
    destination = no_links(destination)
    no_links(destination.with_name(destination.name + ".bak"))
    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    # The source is a private temporary file; all destination/backup validation
    # and atomic publication use the same copy boundary as deployed binaries.
    with tempfile.TemporaryDirectory(prefix="allin1-json-") as temporary:
        source = Path(temporary) / "payload.json"
        source.write_text(encoded, encoding="utf-8")
        _copy_atomic(source, destination)


def _is_enhanced(gta_path: Path) -> bool:
    """Check if this is GTA V Enhanced Edition."""
    return (gta_path / "GTA5_Enhanced.exe").exists()


def _preflight_installation_roots(gta_path: Path) -> Path:
    """Reject redirected installation trees before any repair/removal writes.

    Enumerate metadata, never hash or open GTA archives. Shared trees are not
    deletion authority: individual services must still prove their ownership.
    """
    root = no_links(gta_path)
    for name in ("scripts", "mods", "plugins", ALLIN1_DATA_DIR):
        target = no_links(root / name)
        if target.exists():
            if not target.is_dir():
                raise ValueError(f"Installation directory is not a directory: {target}")
            tree_files(target)
    for name in (*LEGACY_FILES, "commandline.txt", "args.txt", "GTA5.exe", "GTA5_Enhanced.exe"):
        no_links(root / name)
    return root


@dataclass
class InstallResult:
    gta_path: Path
    is_enhanced: bool = False
    dll_deployed: bool = False
    scripthookv_found: bool = False
    shvdn_found: bool = False
    openrpf_found: bool = False
    rpf_loader_installed: bool = False
    rpf_loader_provider: str = ""
    reactor_ready: bool = False
    reactor_provider: str = ""
    rpf_previews_deployed: bool = False
    standalone_maps_deployed: bool = False
    garment_map_bridge_deployed: bool = False
    smoke_tuning_installed: bool = False
    colored_smoke_weapons_installed: bool = False
    battleye_status: str = ""
    warnings: list[str] = field(default_factory=list)


def resolve_gta_path(config: Config) -> Path:
    """Resolve the GTA V path from config or auto-detection."""
    target = config.general.target_edition.strip().lower()
    if target in {"legacy", "enhanced"}:
        configured = (
            config.general.gta_legacy_path if target == "legacy"
            else config.general.gta_enhanced_path
        )
        if configured.strip().lower() != "auto":
            log.info("Using configured GTA V %s path: %s", target, configured)
            return validate_gta_path(configured)
    if config.general.gta_path != "auto":
        log.info("Using configured GTA V path: %s", config.general.gta_path)
        return validate_gta_path(config.general.gta_path)

    log.info("GTA V path set to 'auto' — running detection...")
    detected = detect_gta_path()
    if detected is None:
        log.error("Auto-detection failed — no GTA V install found")
        raise FileNotFoundError(
            "Could not auto-detect GTA V installation. "
            "Set gta_path in config.toml to your GTA V directory."
        )
    return detected


InstallProgress = Callable[[int, str], None]
RpfLoaderConsent = Callable[[Path, bool], bool]


def _report_progress(
    callback: InstallProgress | None, percentage: int, detail: str,
) -> None:
    if callback is not None:
        callback(max(0, min(100, percentage)), detail)


def install(
    config: Config,
    db: VehicleDatabase,
    progress: InstallProgress | None = None,
    rpf_loader_consent: RpfLoaderConsent | None = None,
    reactor_consent: Callable[[Path, bool], bool] | None = None,
) -> InstallResult:
    """Run the full installation process."""
    log.info("=== Starting installation ===")
    _report_progress(progress, 0, "Preparing repair")
    gta_path = _preflight_installation_roots(resolve_gta_path(config))
    _report_progress(progress, 5, "Game folder verified")
    enhanced = _is_enhanced(gta_path)
    result = InstallResult(gta_path=gta_path, is_enhanced=enhanced)

    log.info("GTA V edition: %s", "Enhanced" if enhanced else "Legacy")

    # Resolve the separately distributed shared dependency before any core,
    # map, registry, or configuration writes. Unknown installations fail closed.
    from allin1.reactor_dependency import (
        ReactorInstallError, dependency_recorded, install_dependency,
    )
    backend = config.script.gbay_ui_backend.strip().lower()
    if backend != "legacy":
        approved = reactor_consent is not None and reactor_consent(gta_path, enhanced)
        if approved or dependency_recorded(gta_path, enhanced):
            try:
                validate_reactor_bridge_pair(_SCRIPT_DIST_DIR, expected_version=__version__)
            except (OSError, ValueError) as exc:
                raise ReactorInstallError(f"ALLIN1's Reactor bridge is incomplete: {exc}") from exc
            result.reactor_provider = install_dependency(
                gta_path, enhanced, allow_download=approved,
                progress=lambda detail: _report_progress(progress, 8, detail),
            )
            result.reactor_ready = True
        elif backend == "reactor":
            raise ReactorInstallError(
                "Reactor-only GBAY needs the shared Reactor V dependency. "
                "Allow its verified download in Install/Repair (CLI: --reactor install). "
                "No game files were changed."
            )
        else:
            result.warnings.append(
                "Reactor V installation was skipped. Existing Reactor files were left untouched; "
                "the auto backend can use the compatibility menu. Allow the Reactor download "
                "in Install/Repair to enable the shared dependency and GBAY presentation."
            )

    # --- Clean up files from previous ALLIN1 versions ---
    _clean_legacy_files(gta_path, result)
    _report_progress(progress, 15, "Previous installation checked")

    # --- Deploy ALLIN1.dll script ---
    result.dll_deployed = _deploy_script(gta_path, config)
    _report_progress(progress, 28, "Client files repaired")

    # --- Check for ScriptHookV ---
    result.scripthookv_found = _check_scripthookv(gta_path)

    # --- Check for ScriptHookVDotNet ---
    result.shvdn_found = _check_shvdn(gta_path)
    if result.reactor_ready:
        from allin1.rpf_loader import ENHANCED_ASI_LOADERS, LEGACY_ASI_LOADERS
        from allin1.health import inspect_windows_binary
        loader_names = ENHANCED_ASI_LOADERS if enhanced else LEGACY_ASI_LOADERS
        if not any(inspect_windows_binary(gta_path / name).valid for name in loader_names):
            result.warnings.append(
                "Reactor is installed, but a compatible x64 ASI loader is missing. "
                "Install the ASI loader supplied with Script Hook V before launching."
            )
        if not result.scripthookv_found or not result.shvdn_found:
            result.warnings.append(
                "Reactor/ALLIN1 game integration still requires the edition-correct "
                "Script Hook V and complete ScriptHookVDotNet v3 runtime. These are not bundled."
            )

    # --- Detect optional RPF loader and offer a verified official download ---
    reactor_catalog_artwork = (
        config.script.gbay_ui_backend.strip().lower() == "reactor" or result.reactor_ready
    )
    legacy_rpf_previews = (
        config.general.enable_rpf_previews and not reactor_catalog_artwork
    )
    result.openrpf_found = _check_openrpf(gta_path, enhanced)
    if (
        legacy_rpf_previews
        and not result.openrpf_found
        and rpf_loader_consent is not None
        and rpf_loader_consent(gta_path, enhanced)
    ):
        _report_progress(progress, 34, "Installing optional RPF loader")
        try:
            dependency = install_recommended_rpf_loader(gta_path, enhanced)
            result.openrpf_found = _check_openrpf(gta_path, enhanced)
            result.rpf_loader_installed = bool(dependency.installed)
            result.rpf_loader_provider = (
                f"{dependency.provider} {dependency.version}"
            )
        except (RpfLoaderInstallError, OSError) as exc:
            log.warning("Optional RPF loader installation failed: %s", exc)
            result.warnings.append(
                f"Optional RPF loader was not installed: {exc}"
            )
    _report_progress(progress, 38, "Dependencies verified")

    # Remove every historical copied-asset map layout before evaluating the
    # metadata-only bridge.  Authentic Rockstar routes are not assumed safe:
    # the zero-flash contract below rejects loading-screen/cache-loader groups
    # and broad Story-world replacements before anything is registered.
    if enhanced:
        # This exclusion is independent of the smoke feature toggle: Repair
        # must also clean up a failed pack left by an older configuration.
        _remove_merged_smoke_canary(gta_path)
        _remove_colored_smoke_weapons(gta_path)
        _write_rpf_quarantine(gta_path)
    _report_progress(progress, 47, "Retiring copied map compatibility data")

    # Resolve Rockstar IPL names outside the game process. The managed client
    # consumes only this small checksummed cache, so archive enumeration never
    # competes with Story Mode streaming or the ScriptHookVDotNet game thread.
    try:
        detection = refresh_garage_map_detection(gta_path)
        log.info(detection.summary)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        log.warning("Garage map name detection was not refreshed: %s", exc)
        result.warnings.append(
            "Garage map name detection could not be refreshed; bundled "
            f"verified names will be used: {exc}"
        )
    _report_progress(progress, 49, "Garage map names verified")

    try:
        result.standalone_maps_deployed = _deploy_standalone_map_dlc(
            gta_path, result, progress=progress,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        # A bridge that cannot be proven is safer absent: runtime entry then
        # fails immediately with repair guidance instead of waiting on an IPL
        # whose Rockstar RPF is disabled in Story Mode.
        _unpatch_dlclist_rpf(gta_path, "allin1_maps")
        _remove_map_pack(gta_path)
        result.standalone_maps_deployed = False
        log.warning("Shared map bridge withheld by safety policy: %s", exc)
        result.warnings.append(
            "The shared map pack (including the yacht) remains unavailable. "
            "Independent garage bridges are checked separately. "
            f"Shared-pack safety check: {exc}"
        )
    _report_progress(progress, 52, "Garage map bridge verified")

    # Garment Factory uses a Rockstar map changeset which explicitly requires
    # a loading transition, so it cannot participate in the visible-world
    # all-property bridge above. Install its own metadata-only dormant group;
    # the client may execute it only while its owned entry fade is fully black.
    try:
        result.garment_map_bridge_deployed = _deploy_garment_stock_bridge(
            gta_path, result,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        _unpatch_dlclist_rpf(gta_path, _GARMENT_BRIDGE_PACK)
        _remove_owned_dlc_pack(gta_path, _GARMENT_BRIDGE_PACK)
        result.garment_map_bridge_deployed = False
        log.error("Garment Factory bridge installation failed: %s", exc,
                  exc_info=True)
        result.warnings.append(
            "Garment Factory support was not installed because its scoped "
            f"Rockstar map contract could not be verified: {exc}"
        )
    _report_progress(progress, 54, "Garment Factory map bridge verified")

    # These exact interior-only closures are independent of allin1_maps.
    # Each remains dormant until its owned garage-entry black transition.
    for bridge in ADDITIONAL_INTERIOR_BRIDGES:
        try:
            _deploy_garment_stock_bridge(gta_path, result, bridge=bridge)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            log.error("%s map bridge failed: %s", bridge.label, exc, exc_info=True)
            result.warnings.append(
                f"{bridge.label} map support was not installed: {exc}"
            )

    if reactor_catalog_artwork:
        # Reactor serves the curated PNG catalogs from its allowlisted asset
        # root. Keeping the old streamed-texture DLC in parallel adds an RPF
        # loader dependency and needless boot-time archive indexing without
        # providing any artwork to the active presentation layer.
        log.info(
            "Reactor GBAY artwork is authoritative; removing legacy preview DLC"
        )
        _remove_preview_pack(gta_path)
        _unpatch_dlclist_rpf(gta_path, "allin1_previews")
    elif config.general.enable_rpf_previews:
        if not result.openrpf_found:
            result.warnings.append(
                "RPF previews requested but no edition-compatible RPF loader was detected; "
                "safe GBAY placeholders will be used."
            )
        else:
            try:
                result.rpf_previews_deployed = _deploy_preview_dlc(
                    gta_path, result, progress=progress,
                )
            except Exception as exc:
                log.error("Preview texture injection failed: %s", exc, exc_info=True)
                result.warnings.append(f"Preview texture injection failed: {exc}")
    else:
        log.info("RPF previews disabled; using crash-safe GBAY placeholders")
        _remove_preview_pack(gta_path)
        _unpatch_dlclist_rpf(gta_path, "allin1_previews")

    if config.script.enhanced_smoke_effects:
        stock_update = gta_path / "update" / "update.rpf"
        archive_is_real = stock_update.is_file() and stock_update.stat().st_size > 1024
        if result.openrpf_found and archive_is_real:
            result.smoke_tuning_installed = _install_smoke_tuning(
                gta_path, result,
            )
            # Do not let Install / Repair silently reintroduce a DLC pack that
            # has failed the only validation that matters: loading Story Mode.
            # Keep its lower-risk archive tuning independent from the quarantined
            # custom weapon definitions.
            result.warnings.append(
                "Independent colored-smoke weapon DLC is quarantined after "
                "repeatable Story Mode startup hangs. Colored purchases remain "
                "staged but unavailable until a corrected pack passes its canary."
            )
        elif result.openrpf_found:
            log.debug("Skipping smoke RPF tuning for placeholder update.rpf")
        else:
            result.warnings.append(
                "Enhanced smoke requested but no edition-compatible RPF "
                "loader was detected; scripted CASEVAC smoke remains available, "
                "but purchasable colored weapons require the custom weapon pack."
            )

    # --- Write -nobattleye to commandline.txt (belt-and-suspenders) ---
    result.battleye_status = asi_loader.ensure_nobattleye(gta_path, enhanced)
    _report_progress(progress, 96, "Finalizing Story Mode settings")

    log.info("=== Installation complete ===")
    _report_progress(progress, 100, "Repair complete")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove client payloads, retaining preferences, saves and recovery data."""
    log.info("=== Starting uninstall ===")
    gta_path = _preflight_installation_roots(resolve_gta_path(config))
    removed: list[Path] = []

    # Restore the shared host before removing our bridge. Refuse edited UI
    # rather than partially uninstalling and leaving another mod's host broken.
    from allin1.reactor_dependency import CONSUMER_RECEIPT, remove_consumer
    managed_reactor_ui = (gta_path / CONSUMER_RECEIPT).exists()
    removed.extend(remove_consumer(gta_path))

    # Legacy needs an early args.txt response file so Rockstar selects the
    # non-BattlEye executable. Remove only tokens whose receipt proves ALLIN1
    # inserted them; player and third-party launch arguments remain untouched.
    try:
        removed.extend(asi_loader.remove_managed_legacy_args(gta_path))
    except OSError:
        log.warning("Could not clean up managed Legacy launch arguments", exc_info=True)

    # Remove the retired offline argument only when ALLIN1's ownership marker
    # proves it came from the pre-release experiment. Player-authored launch
    # arguments remain untouched.
    try:
        commandline_existed = (gta_path / "commandline.txt").is_file()
        remove_retired_offline_policy(gta_path)
        if commandline_existed and not (gta_path / "commandline.txt").exists():
            removed.append(gta_path / "commandline.txt")
    except OSError:
        log.warning("Could not clean up retired offline launch policy", exc_info=True)

    _remove_smoke_tuning(gta_path)
    _remove_merged_smoke_canary(gta_path)
    _remove_colored_smoke_weapons(gta_path)

    # Remove the official descriptors from the shared content registry while
    # preserving third-party receipts and namespaced settings. Reinstalling the
    # launcher host can then restore the official packs without erasing package
    # configuration owned by the user.
    try:
        registry = ExtensionRegistry(gta_path)
        for manifest in ExtensionCatalog(_PROJECT_ROOT / "content").discover():
            registry.unregister_builtin(manifest.extension_id, force=True)
            for catalog in manifest.gbay_catalogs:
                if (manifest.extension_id, catalog.catalog_id) not in _BUILTIN_CATALOG_PAYLOADS:
                    continue
                destination = gta_path / Path(*catalog.source.parts)
                for candidate in (destination, destination.with_name(destination.name + ".bak")):
                    if candidate.is_file():
                        candidate.unlink()
                        removed.append(candidate)
            if manifest.extension_id in _BUILTIN_MAP_PAYLOADS:
                destination_root = (
                    gta_path / "scripts" / "ALLIN1" / "Maps"
                    / manifest.extension_id
                )
                if destination_root.is_dir():
                    shutil.rmtree(destination_root)
                    removed.append(destination_root)
    except (OSError, ValueError):
        log.warning("Could not fully reconcile the content registry", exc_info=True)

    # Remove runtime payloads/caches, not user preferences or character saves.
    scripts_dir = gta_path / SCRIPTS_DIR
    retired_lemonui = _remove_retired_lemonui_dependency(scripts_dir)
    if retired_lemonui is not None:
        removed.append(retired_lemonui)
    for preload_candidate in (
        gta_path / _PRELOAD_MANIFEST_RELATIVE,
        (gta_path / _PRELOAD_MANIFEST_RELATIVE).with_suffix(".json.tmp"),
    ):
        if preload_candidate.is_file():
            preload_candidate.unlink()
            removed.append(preload_candidate)
    map_cache = gta_path / Path(*GARAGE_MAP_CACHE_RELATIVE.parts)
    for candidate in (
        map_cache,
        map_cache.with_name(map_cache.name + ".tmp"),
        map_cache.with_name(map_cache.name + ".bak"),
    ):
        if candidate.is_file():
            candidate.unlink()
            removed.append(candidate)
    for fname in (DLL_FILENAME,
                   "ALLIN1.log", "ALLIN1_spawner.log", "ALLIN1_gbay.log",
                   "ALLIN1_client.log", "ALLIN1_client.log.1",
                   "ALLIN1_client.log.2", "ALLIN1_client.log.3",
                   GROUNDING_CATALOG_FILENAME,
                   GROUNDING_CATALOG_FILENAME + ".bak",
                   *RETIRED_DEVELOPER_ARTIFACTS,
                   "ALLIN1_session.lock",
                   "ALLIN1_rpf_quarantine.json",
                   "ALLIN1_rpf_quarantine.json.bak",
                   "ALLIN1_colored_smoke_merged_canary.json",
                   "ALLIN1_preview_pending.toml",
                   VERSION_FILE):
        fpath = scripts_dir / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fpath)
            log.info("Removed %s from scripts/", fname)

    for reactor_name in (
        REACTOR_BRIDGE_FILENAME, REACTOR_BRIDGE_CONTRACT_FILENAME,
    ):
        reactor_file = scripts_dir / "ReactorV" / reactor_name
        if reactor_file.is_file():
            reactor_file.unlink()
            removed.append(reactor_file)
            log.info("Removed %s from scripts/ReactorV/", reactor_name)

    reactor_artwork = gta_path / _REACTOR_ARTWORK_RELATIVE
    if reactor_artwork.is_dir() and not managed_reactor_ui:
        shutil.rmtree(reactor_artwork)
        removed.append(reactor_artwork)
        log.info("Removed ALLIN1 artwork from the Reactor V asset host")

    for dirname in RETIRED_DEVELOPER_DIRECTORIES:
        dpath = scripts_dir / dirname
        if dpath.exists():
            shutil.rmtree(dpath)
            removed.append(dpath)
            log.info("Removed %s from scripts/", dirname)

    # Remove legacy files from game root
    for fname in LEGACY_FILES:
        fpath = gta_path / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fpath)
            log.info("Removed %s from GTA V directory", fname)

    # No receipt proves that an old data folder contains only generated files.
    # It may contain projects/saves; preserve it in place.
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        log.info("Preserved legacy %s/ user data", ALLIN1_DATA_DIR)

    # Remove legacy loose preview images (from SHV-era installs)
    for preview_folder in (
        "previews", "weapon_previews", "equipment_previews",
        "world_asset_previews",
    ):
        scripts_dir_previews = scripts_dir / preview_folder
        if scripts_dir_previews.exists():
            shutil.rmtree(scripts_dir_previews)
            removed.append(scripts_dir_previews)
            log.info("Removed %s/ capture folder", preview_folder)
    logo_file = scripts_dir / "PHAT.png"
    if logo_file.exists():
        logo_file.unlink()
        removed.append(logo_file)
        log.info("Removed PHAT.png")

    # Remove the ALLIN1-owned preview DLC pack.
    removed.extend(_remove_preview_pack(gta_path))
    removed.extend(_remove_map_pack(gta_path))
    removed.extend(_remove_owned_dlc_pack(
        gta_path, _GARMENT_BRIDGE_PACK,
    ))
    for bridge in ADDITIONAL_INTERIOR_BRIDGES:
        removed.extend(_remove_owned_dlc_pack(gta_path, bridge.pack))

    # Unpatch dlclist.xml in mods/update/update.rpf (legacy cleanup)
    _unpatch_dlclist_rpf(gta_path)

    # Remove ALLIN1 .ytd files from script_txds.rpf inside mods/update.rpf
    _remove_preview_ytds(gta_path)

    # Remove only unchanged third-party loader files that ALLIN1 installed and
    # recorded. User-installed or subsequently modified files are preserved.
    removed.extend(uninstall_managed_rpf_loader(gta_path))

    # Remove -nobattleye from commandline.txt (or the whole file if it only
    # contained that flag).
    cmdline = gta_path / "commandline.txt"
    if cmdline.exists():
        try:
            lines = cmdline.read_text(encoding="utf-8", errors="replace").splitlines()
            remaining = [ln for ln in lines if ln.strip() != "-nobattleye"]
            if remaining and any(ln.strip() for ln in remaining):
                cmdline.write_text("\n".join(remaining) + "\n", encoding="utf-8")
            else:
                cmdline.unlink()
                removed.append(cmdline)
            log.info("Removed -nobattleye from commandline.txt")
        except OSError:
            pass

    log.info("=== Uninstall complete: %d files removed ===", len(removed))
    return removed


def _clean_legacy_files(gta_path: Path, result: InstallResult) -> None:
    """Remove files from previous ALLIN1 versions."""
    # Remove old ASI / injector / DLL files from game root
    for fname in LEGACY_FILES:
        p = gta_path / fname
        if p.exists():
            try:
                p.unlink()
                result.warnings.append(f"Removed old {fname} (no longer needed).")
                log.info("Removed legacy file: %s", fname)
            except OSError as exc:
                result.warnings.append(
                    f"Could not remove {fname}: {exc}. Delete it manually."
                )
                log.warning("Failed to remove %s: %s", fname, exc)

    # A folder name alone cannot authorize deletion of old user data.
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        result.warnings.append(f"Preserved {ALLIN1_DATA_DIR}/ legacy user data; it is not needed by the current client.")
        log.info("Preserved legacy data folder: %s", data_dir)


def _deploy_script(gta_path: Path, config: Config | None = None) -> bool:
    """Copy ALLIN1.dll to GTA V scripts/ folder. Returns True if deployed."""
    src = _SCRIPT_DIST_DIR / DLL_FILENAME
    if not src.exists():
        log.warning(
            "%s not found at %s — run the GitHub Actions build or "
            "download from Releases.",
            DLL_FILENAME, _SCRIPT_DIST_DIR,
        )
        return False

    reactor_bridge_src = _SCRIPT_DIST_DIR / REACTOR_BRIDGE_FILENAME
    reactor_contract_src = (
        _SCRIPT_DIST_DIR / REACTOR_BRIDGE_CONTRACT_FILENAME
    )
    backend = (config.script.gbay_ui_backend if config is not None else "auto")
    if not reactor_bridge_src.is_file():
        message = (
            f"{REACTOR_BRIDGE_FILENAME} is missing from {_SCRIPT_DIST_DIR}; "
            "the Reactor V GBAY surface cannot be installed."
        )
        if backend == "reactor":
            log.error("%s The configured Reactor-only backend requires it.", message)
            return False
        if backend == "auto":
            log.warning("%s GBAY will use the compatibility menu.", message)
    else:
        try:
            validate_reactor_bridge_pair(
                _SCRIPT_DIST_DIR, expected_version=__version__,
            )
        except ValueError as exc:
            log.error(
                "Refusing to install an incompatible ALLIN1/Reactor bridge "
                "binary pair: %s", exc,
            )
            return False

    scripts_dir = gta_path / SCRIPTS_DIR
    scripts_dir.mkdir(exist_ok=True)
    _remove_retired_lemonui_dependency(scripts_dir)
    dest = scripts_dir / DLL_FILENAME
    if reactor_bridge_src.is_file():
        reactor_dir = scripts_dir / "ReactorV"
        reactor_bridge_dest = reactor_dir / REACTOR_BRIDGE_FILENAME
        reactor_contract_dest = (
            reactor_dir / REACTOR_BRIDGE_CONTRACT_FILENAME
        )
        _copy_files_transactionally((
            (src, dest),
            (reactor_bridge_src, reactor_bridge_dest),
            (reactor_contract_src, reactor_contract_dest),
        ))
        log.info(
            "Deployed compatible %s + %s pair",
            DLL_FILENAME, REACTOR_BRIDGE_FILENAME,
        )
    else:
        _copy_atomic(src, dest)
    write_installed_version(scripts_dir)
    log.info("Deployed %s → %s", DLL_FILENAME, dest)

    # Optional presentation adapter. It is inert unless Reactor's Script and
    # Core assemblies are already loaded, and it never brings a second copy of
    # Reactor Core into the game process.
    if reactor_bridge_src.exists():
        _deploy_reactor_catalog_artwork(gta_path)

    # Deploy the exact in-memory configuration selected by this install. This
    # keeps custom CLI config paths and extension compatibility bindings from
    # silently falling back to an unrelated project-root file.
    toml_dest = scripts_dir / "ALLIN1.toml"
    if config is not None:
        config.save(toml_dest)
        log.info("Deployed active launcher configuration -> %s", toml_dest)
    else:
        toml_src = _PROJECT_ROOT / "config.toml"
        if not toml_src.exists():
            toml_src = _PROJECT_ROOT / "config.example.toml"
        if toml_src.exists():
            _copy_atomic(toml_src, toml_dest)
            log.info("Deployed config %s -> %s", toml_src.name, toml_dest)

    _deploy_grounding_catalog(scripts_dir)
    _deploy_preload_manifest(gta_path)
    _deploy_content_registry(gta_path, config or Config.default())

    # Development-only runtime tools are retired. Their generated artifacts
    # are not user data and must not survive install or repair.
    for retired_name in RETIRED_DEVELOPER_ARTIFACTS:
        retired_path = scripts_dir / retired_name
        if retired_path.exists():
            retired_path.unlink()
            log.info("Removed retired developer artifact %s", retired_name)
    for retired_name in RETIRED_DEVELOPER_DIRECTORIES:
        retired_path = scripts_dir / retired_name
        if retired_path.exists():
            shutil.rmtree(retired_path)
            log.info("Removed retired developer directory %s", retired_name)

    # Clean up legacy INI from previous versions
    legacy_ini = scripts_dir / "ALLIN1.ini"
    if legacy_ini.exists():
        legacy_ini.unlink()
        log.info("Removed legacy ALLIN1.ini")

    return True


def _deploy_reactor_catalog_artwork(gta_path: Path) -> int:
    """Publish curated card art inside Reactor's allowlisted UI asset root.

    Reactor deliberately cannot read arbitrary local files.  ALLIN1 therefore
    copies only its release-owned PNG catalogs beneath the already mapped UI
    directory.  The bridge can then use portable ``assets/allin1/...`` URLs
    without exposing a GTA path or widening Reactor's filesystem boundary.
    """
    from allin1.reactor_dependency import CONSUMER_RECEIPT
    if (gta_path / CONSUMER_RECEIPT).is_file():
        # The dependency transaction already deployed and receipted our art.
        return 0
    reactor_ui = gta_path / "plugins" / "ReactorV" / "ui"
    if not (reactor_ui / "index.html").is_file():
        log.info(
            "Reactor V UI is not installed; browser catalog artwork was not staged"
        )
        return 0

    destination_root = gta_path / _REACTOR_ARTWORK_RELATIVE
    copied = 0
    for category, source_name in _REACTOR_ARTWORK_SOURCES.items():
        source_root = _SCRIPT_DIST_DIR / source_name
        if not source_root.is_dir():
            log.warning(
                "Reactor catalog artwork source is missing: %s", source_root
            )
            continue
        sources = {
            source.name.casefold(): source
            for source in source_root.iterdir()
            if source.is_file() and source.suffix.casefold() == ".png"
        }
        destination = destination_root / category
        destination.mkdir(parents=True, exist_ok=True)
        for stale in destination.glob("*.png"):
            if stale.name.casefold() not in sources:
                stale.unlink()
        for source in sources.values():
            target = destination / source.name
            if _same_file_payload(source, target):
                continue
            temporary = target.with_name(target.name + ".tmp")
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            copied += 1
    log.info(
        "Published Reactor V catalog artwork (%d updated file(s)) -> %s",
        copied,
        destination_root,
    )
    return copied


def _deploy_preload_manifest(gta_path: Path) -> Path:
    """Deploy the static request before registry rebuild appends authorized data."""
    if not _PRELOAD_MANIFEST_SOURCE.is_file():
        raise FileNotFoundError(
            f"ReactorV preload manifest is missing: {_PRELOAD_MANIFEST_SOURCE}"
        )
    destination = gta_path / _PRELOAD_MANIFEST_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    _copy_atomic(_PRELOAD_MANIFEST_SOURCE, destination)
    log.info("Deployed ReactorV preload manifest -> %s", destination)
    return destination


def _deploy_content_registry(gta_path: Path, config: Config) -> None:
    """Install/update official declarative packs without resetting user choices."""
    catalog = ExtensionCatalog(_PROJECT_ROOT / "content")
    manifests = catalog.discover()
    if not manifests:
        log.warning("No official ALLIN1 content descriptors were found")
        return
    registry = ExtensionRegistry(gta_path)
    for manifest in manifests:
        for catalog in manifest.gbay_catalogs:
            source = _BUILTIN_CATALOG_PAYLOADS.get(
                (manifest.extension_id, catalog.catalog_id)
            )
            if source is None:
                continue
            if not source.is_file():
                raise FileNotFoundError(
                    f"Built-in catalog payload is missing: {source}"
                )
            destination = gta_path / Path(*catalog.source.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_atomic(source, destination)
        map_files: list[dict[str, str]] = []
        if "world.maps" in manifest.capabilities:
            source_root = _BUILTIN_MAP_PAYLOADS.get(manifest.extension_id)
            if source_root is None:
                raise FileNotFoundError(
                    "Built-in map payload mapping is missing for "
                    f"{manifest.extension_id}"
                )
            if not source_root.is_dir():
                raise FileNotFoundError(
                    f"Built-in map payload folder is missing: {source_root}"
                )
            sources = sorted(
                source_root.glob("*.maps.json"),
                key=lambda path: path.name.casefold(),
            )
            if not sources:
                raise FileNotFoundError(
                    f"Built-in map payload folder is empty: {source_root}"
                )
            destination_root = (
                gta_path / "scripts" / "ALLIN1" / "Maps"
                / manifest.extension_id
            )
            destination_root.mkdir(parents=True, exist_ok=True)
            current_names = {source.name.casefold() for source in sources}
            for stale in destination_root.glob("*.maps.json"):
                if stale.name.casefold() not in current_names:
                    stale.unlink()
            for source in sources:
                destination = destination_root / source.name
                expected_sha256 = ExtensionRegistry._file_sha256(source)
                _copy_atomic(source, destination)
                if ExtensionRegistry._file_sha256(destination) != expected_sha256:
                    raise OSError(
                        f"Built-in map payload copy failed verification: {source}"
                    )
                relative = destination.relative_to(gta_path).as_posix()
                map_files.append({
                    "path": relative,
                    "sha256": expected_sha256,
                })
        registry.register_builtin(
            manifest,
            enabled=None,
            settings=settings_from_config(manifest, config),
            map_files=map_files,
        )
    registry.rebuild()
    log.info("Registered %d official ALLIN1 content package(s)", len(manifests))


def _deploy_grounding_catalog(scripts_dir: Path) -> None:
    """Seed validated outcomes without replacing newer resolved user data."""
    source = _PROJECT_ROOT / "data" / "vehicle_grounding.json"
    if not source.is_file():
        log.warning("Validated vehicle grounding catalog is missing: %s", source)
        return
    destination = scripts_dir / GROUNDING_CATALOG_FILENAME
    seed = json.loads(source.read_text(encoding="utf-8"))
    seed_entries = seed.get("Entries", {})
    if not isinstance(seed_entries, dict):
        raise ValueError("validated grounding catalog has no Entries object")
    if not destination.exists():
        _copy_atomic(source, destination)
        log.info("Deployed %d validated vehicle grounding offsets", len(seed_entries))
        return

    try:
        current = json.loads(destination.read_text(encoding="utf-8"))
        current_entries = current.get("Entries", {})
        if not isinstance(current_entries, dict):
            raise ValueError("installed grounding catalog has no Entries object")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        log.warning("Replacing unreadable grounding checkpoint: %s", exc)
        _copy_atomic(source, destination)
        return

    normalized = {
        str(key).strip().lower(): value
        for key, value in current_entries.items()
        if str(key).strip()
    }
    added = 0
    for key, entry in seed_entries.items():
        model = str(key).strip().lower()
        existing = normalized.get(model)
        existing_resolved = isinstance(existing, dict) and (
            (existing.get("Stable") is True
             and existing.get("Status") == "measured")
            or existing.get("Status") == "unsupported"
        )
        if existing_resolved:
            continue
        normalized[model] = entry
        added += 1
    if added == 0:
        log.info("Installed grounding checkpoint already contains validated offsets")
        return

    current["SchemaVersion"] = 1
    current["TotalModels"] = max(
        int(current.get("TotalModels") or 0), int(seed.get("TotalModels") or 0)
    )
    current["Entries"] = dict(sorted(normalized.items()))
    values = [entry for entry in normalized.values() if isinstance(entry, dict)]
    current["MeasuredModels"] = sum(
        entry.get("Status") == "measured" for entry in values
    )
    current["StableModels"] = sum(
        entry.get("Stable") is True and entry.get("Status") == "measured"
        for entry in values
    )
    current["UnsupportedModels"] = sum(
        entry.get("Status") == "unsupported" for entry in values
    )
    current["OutlierModels"] = sum(
        not (
            (entry.get("Stable") is True and entry.get("Status") == "measured")
            or entry.get("Status") == "unsupported"
        )
        for entry in values
    )
    _write_json_atomic(current, destination)
    log.info("Merged %d validated vehicle grounding offsets", added)


def _check_scripthookv(gta_path: Path) -> bool:
    """Check if ScriptHookV is installed in the game directory."""
    return inspect_windows_binary(gta_path / "ScriptHookV.dll").valid


def _check_shvdn(gta_path: Path) -> bool:
    """Check whether ALLIN1's complete ScriptHookVDotNet runtime is valid."""
    return is_shvdn_runtime_ready(gta_path)


def _check_openrpf(gta_path: Path, enhanced: bool) -> bool:
    """Detect a valid edition-compatible RPF plug-in and ASI loader."""
    status = inspect_rpf_loader(gta_path, enhanced)
    if status.ready:
        log.info(
            "RPF dependency detected: %s through %s",
            status.plugin.name if status.plugin else "unknown",
            status.asi_loader.name if status.asi_loader else "unknown",
        )
    else:
        log.warning("RPF dependency unavailable: %s", status.reason)
    return status.ready


def _deploy_preview_dlc(
    gta_path: Path,
    result: InstallResult,
    progress: InstallProgress | None = None,
) -> bool:
    """Build and register a DLC pack containing streamed preview dictionaries."""
    from allin1.generators import dlc_previews
    from allin1.generators import ytd_builder
    from allin1.preview_assets import merge_previews

    previews_src = _SCRIPT_DIST_DIR / "previews"
    logo_src = _SCRIPT_DIST_DIR / "PHAT.png"
    brand_logo_src = _SCRIPT_DIST_DIR / "ALLIN1.png"
    weapon_previews_src = _SCRIPT_DIST_DIR / "weapon_previews"
    equipment_previews_src = _SCRIPT_DIST_DIR / "equipment_previews"
    world_asset_previews_src = _SCRIPT_DIST_DIR / "world_asset_previews"

    if not previews_src.is_dir():
        log.warning("No previews/ directory found — skipping preview build")
        result.warnings.append("Preview images not found; vehicle thumbnails "
                               "will show colored placeholders.")
        return False

    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe not found — skipping preview build. "
                     "Run runtools.ps1 first.")
        result.warnings.append("RpfPatcher.exe missing; run runtools.ps1 first.")
        return False

    # Dictionary assignment is generated from the complete sorted catalog.
    # Never derive it from the set of successful captures: one missing image
    # would shift every subsequent texture into the wrong dictionary.
    models = sorted(v.model for v in VehicleDatabase.load(
        _PROJECT_ROOT / "data" / "vehicles.toml"
    ))
    with (_PROJECT_ROOT / "data" / "weapons.toml").open("rb") as stream:
        weapon_ids = sorted(
            item["name"] for item in tomllib.load(stream).get("weapons", [])
        )
    gear_ids = sorted(GEAR_PREVIEW_ITEMS)
    world_asset_ids = sorted(WORLD_ASSET_PREVIEW_ITEMS)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ytd_out = tmp_path / "ytd"
        preview_inputs = tmp_path / "preview_inputs"
        weapon_preview_inputs = tmp_path / "weapon_preview_inputs"
        equipment_preview_inputs = tmp_path / "equipment_preview_inputs"
        world_asset_preview_inputs = tmp_path / "world_asset_preview_inputs"

        # Raw captures are source material, not approved catalog art. Package
        # only the reviewed repository assets so an old or incomplete capture
        # folder cannot silently replace curated previews during repair.
        merged = merge_previews(
            [previews_src],
            preview_inputs,
            models,
        )
        if merged.copied == 0:
            log.warning("No valid PNG preview files found")
            result.warnings.append("No valid vehicle previews were found.")
            return False
        if merged.rejected:
            result.warnings.append(
                f"Ignored {len(merged.rejected)} invalid preview capture(s)."
            )
        if merged.missing:
            result.warnings.append(
                f"{len(merged.missing)} vehicle preview(s) missing; placeholders will be used."
            )
        log.info("Building preview textures for %d/%d vehicles...",
                 merged.copied, len(models))

        weapon_merged = merge_previews(
            [weapon_previews_src],
            weapon_preview_inputs,
            weapon_ids,
        )
        equipment_merged = merge_previews(
            [equipment_previews_src],
            equipment_preview_inputs,
            gear_ids,
        )
        world_asset_merged = merge_previews(
            [world_asset_previews_src],
            world_asset_preview_inputs,
            world_asset_ids,
        )
        if (weapon_merged.rejected or equipment_merged.rejected
                or world_asset_merged.rejected):
            rejected_count = (
                len(weapon_merged.rejected) + len(equipment_merged.rejected)
                + len(world_asset_merged.rejected)
            )
            result.warnings.append(
                f"Ignored {rejected_count} invalid catalog preview capture(s)."
            )
        if weapon_merged.copied:
            log.info("Building preview textures for %d/%d weapons...",
                     weapon_merged.copied, len(weapon_ids))
        if equipment_merged.copied:
            log.info("Building preview textures for %d/%d equipment items...",
                     equipment_merged.copied, len(gear_ids))
        if world_asset_merged.copied:
            log.info("Building preview textures for %d/%d world assets...",
                     world_asset_merged.copied, len(world_asset_ids))

        preview_groups = []
        if weapon_merged.copied:
            preview_groups.append(
                ("allin1_weapon", weapon_preview_inputs, weapon_ids)
            )
        if equipment_merged.copied:
            preview_groups.append(
                ("allin1_gear", equipment_preview_inputs, gear_ids)
            )
        if world_asset_merged.copied:
            preview_groups.append(
                ("allin1_asset", world_asset_preview_inputs, world_asset_ids)
            )

        # Step 1: Build .ytd files from PNGs
        _report_progress(progress, 50, "Building preview textures")
        ytd_files = ytd_builder.build_ytd_files(
            preview_inputs,
            logo_src if logo_src.exists() else None,
            ytd_out, _TOOLS_DIR, models,
            brand_logo_path=brand_logo_src if brand_logo_src.exists() else None,
            preview_groups=preview_groups,
        )

        if not ytd_files:
            log.warning("No .ytd files were built")
            result.warnings.append("Failed to build preview textures.")
            return False
        _report_progress(progress, 64, "Preview textures built")

        # Step 1b: Convert .ytd files to Enhanced (gen9) format if needed
        if result.is_enhanced:
            log.info("Enhanced edition detected — converting .ytd files to gen9 format...")
            _report_progress(progress, 68, "Converting Enhanced textures")
            proc = run_hidden(
                [str(rpf_patcher), "convert-gen9", str(ytd_out)],
                capture_output=True, text=True, timeout=300,
            )
            if proc.stdout:
                for line in proc.stdout.strip().splitlines():
                    log.info("RpfPatcher: %s", line)
            if proc.returncode != 0:
                error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
                raise RuntimeError(f"RpfPatcher convert-gen9 failed: {error_msg}")
            log.info("Gen9 conversion complete.")

        # Put the dictionaries in a nested RPF and register that RPF as DLC
        # content. This is required for REQUEST_STREAMED_TEXTURE_DICT to see
        # custom dictionaries on Enhanced; a loose directory inside
        # update2.rpf is not automatically part of the streaming index.
        dlc_work = tmp_path / "dlc"
        dlc_root, ytd_staging = dlc_previews.create_dlc_pack(
            ytd_files, dlc_work,
        )
        output_rpf = dlc_work / "allin1_previews.dlc.rpf"
        _report_progress(progress, 74, "Packaging preview DLC")
        proc = run_hidden(
            [
                str(rpf_patcher), "build-dlc", str(dlc_root), str(output_rpf),
                "--embed-rpf", str(ytd_staging), "x64/textures/textures.rpf",
            ],
            capture_output=True, text=True, timeout=300,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
            raise RuntimeError(f"RpfPatcher build-dlc failed: {error_msg}")
        if not output_rpf.is_file() or output_rpf.stat().st_size == 0:
            raise RuntimeError("RpfPatcher build-dlc produced no archive")

        _report_progress(progress, 84, "Verifying preview DLC")
        verify = run_hidden(
            [str(rpf_patcher), "verify-dlc", str(output_rpf), str(ytd_staging)],
            capture_output=True, text=True, timeout=300,
        )
        if verify.stdout:
            for line in verify.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if verify.returncode != 0:
            error_msg = verify.stderr.strip() if verify.stderr else f"exit code {verify.returncode}"
            raise RuntimeError(f"RpfPatcher verify-dlc failed: {error_msg}")

        deployed_dir = dlc_previews.deploy_dlc_rpf(output_rpf, gta_path)
        _report_progress(progress, 90, "Registering preview DLC")
        if not _patch_dlclist_rpf(gta_path, result, "allin1_previews"):
            shutil.rmtree(deployed_dir, ignore_errors=True)
            raise RuntimeError(
                "RpfPatcher patch failed; could not register the preview DLC in dlclist.xml"
            )
        log.info("Preview texture DLC built, verified, deployed, and registered")
        return True


def _map_patcher_command(
    rpf_patcher: Path,
    arguments: list[str],
    *,
    operation: str,
    timeout: int = 300,
) -> None:
    """Run one archive transaction command and turn every failure into an error."""
    proc = run_hidden(
        [str(rpf_patcher), *arguments],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.stdout:
        for line in proc.stdout.strip().splitlines():
            log.info("RpfPatcher map activation: %s", line)
    if proc.returncode != 0:
        error_msg = (
            proc.stderr.strip() if proc.stderr
            else f"exit code {proc.returncode}"
        )
        raise RuntimeError(f"{operation} failed: {error_msg}")


def _map_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _enhanced_gameconfig_pools(xml_text: str) -> dict[str, int]:
    """Validate a complete Enhanced gameconfig and return its pool values."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Enhanced gameconfig.xml: {exc}") from exc

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    if local_name(root.tag) != "fwAllConfigs":
        raise ValueError(
            "Enhanced map activation requires the complete fwAllConfigs "
            "gameconfig.xml from mods/update/update.rpf"
        )

    def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
        return [
            child for child in element
            if isinstance(child.tag, str) and local_name(child.tag) == name
        ]

    # Enhanced's fwAllConfigs document is layered. The base CGameConfig and a
    # platform/build override may legitimately name the same pool (the stock
    # file defines ScaleformStore in both the Any/Any base and x64 override).
    # A duplicate inside one Entries collection is still malformed. Collapse
    # valid cross-scope overrides to their largest value for activation checks
    # and receipts; ALLIN1 only raises values, so this is the conservative
    # effective value for a layered document.
    pools: dict[str, int] = {}
    handled_items: set[int] = set()
    for config in root.iter():
        if (
            not isinstance(config.tag, str)
            or local_name(config.tag) != "Config"
            or config.get("type") != "CGameConfig"
        ):
            continue
        for pool_sizes in direct_children(config, "PoolSizes"):
            for entries in direct_children(pool_sizes, "Entries"):
                scope_names: set[str] = set()
                for item in direct_children(entries, "Item"):
                    name_elements = direct_children(item, "PoolName")
                    size_elements = direct_children(item, "PoolSize")
                    if not name_elements and not size_elements:
                        continue
                    handled_items.add(id(item))
                    if len(name_elements) != 1 or len(size_elements) != 1:
                        raise ValueError(
                            "Malformed Enhanced gameconfig pool entry: "
                            "PoolName and PoolSize must each appear exactly once"
                        )
                    name = (name_elements[0].text or "").strip()
                    value = size_elements[0].get("value")
                    if not name or value is None:
                        raise ValueError(
                            "Malformed Enhanced gameconfig pool entry"
                        )
                    try:
                        parsed = int(value)
                    except ValueError as exc:
                        raise ValueError(
                            "Malformed Enhanced gameconfig pool "
                            f"{name!r}: {value!r}"
                        ) from exc
                    if parsed < 0:
                        raise ValueError(
                            "Malformed Enhanced gameconfig pool "
                            f"{name!r}: negative value"
                        )
                    if name in scope_names:
                        raise ValueError(
                            "Malformed Enhanced gameconfig pool "
                            f"{name!r}: duplicate within one Entries scope"
                        )
                    scope_names.add(name)
                    pools[name] = max(pools.get(name, parsed), parsed)

    # Do not silently accept PoolName/PoolSize-shaped data outside the schema
    # location above. This preserves the prior fail-closed malformed-document
    # behavior while allowing only the known layered-config duplicate shape.
    for item in root.iter():
        if (
            not isinstance(item.tag, str)
            or local_name(item.tag) != "Item"
            or id(item) in handled_items
        ):
            continue
        children = [
            local_name(child.tag)
            for child in item
            if isinstance(child.tag, str)
        ]
        if "PoolName" in children or "PoolSize" in children:
            raise ValueError(
                "Malformed Enhanced gameconfig pool entry outside "
                "Config/PoolSizes/Entries"
            )
    if not pools:
        raise ValueError(
            "Enhanced fwAllConfigs gameconfig.xml contains no pool entries"
        )
    return pools


def _ensure_full_mods_update_archive(gta_path: Path) -> tuple[Path, bool]:
    """Return the full mods update archive, copying the stock archive if needed."""
    stock_archive = gta_path / "update" / "update.rpf"
    mods_archive = gta_path / "mods" / "update" / "update.rpf"
    if not stock_archive.is_file():
        raise RuntimeError(
            "Stock update/update.rpf is missing; map activation was left disabled"
        )
    if mods_archive.exists() and not mods_archive.is_file():
        raise RuntimeError(
            "mods/update/update.rpf is not a file; map activation was left disabled"
        )
    if mods_archive.is_file():
        # Refuse to overwrite a potentially customized archive from an older
        # game build. Repair guidance can handle that case explicitly.
        if (
            mods_archive.stat().st_mtime_ns + 1_000_000_000
            < stock_archive.stat().st_mtime_ns
        ):
            raise RuntimeError(
                "mods/update/update.rpf predates the installed game update; "
                "refresh it before enabling standalone maps"
            )
        return mods_archive, False

    mods_archive.parent.mkdir(parents=True, exist_ok=True)
    temporary = mods_archive.with_name("update.rpf.allin1-map-copy.tmp")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(stock_archive, temporary)
        if temporary.stat().st_size != stock_archive.stat().st_size:
            raise RuntimeError("Full update.rpf copy failed size verification")
        os.replace(temporary, mods_archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return mods_archive, True


def _same_file_payload(first: Path, second: Path) -> bool:
    """Compare owned artwork without trusting timestamps from release ZIPs."""
    if not first.is_file() or not second.is_file():
        return False
    if first.stat().st_size != second.stat().st_size:
        return False
    first_digest = hashlib.sha256()
    second_digest = hashlib.sha256()
    with first.open("rb") as left, second.open("rb") as right:
        for left_chunk, right_chunk in zip(
            iter(lambda: left.read(1024 * 1024), b""),
            iter(lambda: right.read(1024 * 1024), b""),
        ):
            first_digest.update(left_chunk)
            second_digest.update(right_chunk)
    return first_digest.digest() == second_digest.digest()


def _retire_known_sparse_onigiri_gameconfig(
    gta_path: Path,
) -> tuple[Path, Path] | None:
    """Retire only ALLIN1's historical three-pool loose override.

    Any other loose gameconfig may be user-authored. It is never modified,
    but it also prevents activation because it could supersede the verified
    full-archive payload at runtime.
    """
    override = gta_path / "onigiri" / "common" / "data" / "gameconfig.xml"
    if not override.exists():
        return None
    if not override.is_file():
        raise RuntimeError(
            "A non-file onigiri gameconfig override blocks map activation"
        )
    payload = override.read_bytes()
    if not payload or len(payload) > 4096:
        raise RuntimeError(
            "A custom onigiri gameconfig override is present; ALLIN1 left it "
            "untouched and kept standalone maps disabled"
        )
    try:
        root = ET.fromstring(payload.decode("utf-8-sig"))
    except (UnicodeError, ET.ParseError) as exc:
        raise RuntimeError(
            "An unreadable onigiri gameconfig override blocks map activation"
        ) from exc

    def local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    values: dict[str, int] = {}
    malformed = local_name(root.tag) != "CGameConfig"
    for item in root.iter():
        if not isinstance(item.tag, str) or local_name(item.tag) != "Item":
            continue
        children = {
            local_name(child.tag): child
            for child in item
            if isinstance(child.tag, str)
        }
        name_element = children.get("Name")
        size_element = children.get("Size")
        if name_element is None and size_element is None:
            continue
        if name_element is None or size_element is None:
            malformed = True
            break
        name = (name_element.text or "").strip()
        raw_value = size_element.get("value")
        try:
            value = int(raw_value) if raw_value is not None else -1
        except ValueError:
            malformed = True
            break
        if not name or value < 0 or name in values:
            malformed = True
            break
        values[name] = value

    known_signature = {
        "CVehicle": 512,
        "CVehicleModelInfo": 900,
        "CHandlingDataMgr": 900,
    }
    if malformed or values != known_signature:
        raise RuntimeError(
            "A custom onigiri gameconfig override is present; ALLIN1 left it "
            "untouched and kept standalone maps disabled"
        )

    backup = override.with_name("gameconfig.xml.allin1-retired.bak")
    if backup.exists() and (
        not backup.is_file() or backup.read_bytes() != payload
    ):
        raise RuntimeError(
            "The retired onigiri gameconfig backup path is already occupied"
        )
    if not backup.exists():
        backup_temporary = backup.with_name(backup.name + ".tmp")
        backup_temporary.unlink(missing_ok=True)
        shutil.copy2(override, backup_temporary)
        if backup_temporary.read_bytes() != payload:
            backup_temporary.unlink(missing_ok=True)
            raise RuntimeError("Could not verify the retired gameconfig backup")
        os.replace(backup_temporary, backup)
    override.unlink()
    log.info("Retired the known sparse ALLIN1 onigiri gameconfig override")
    return override, backup


def _restore_retired_onigiri_gameconfig(
    retired: tuple[Path, Path] | None,
) -> None:
    if retired is None:
        return
    override, backup = retired
    if not backup.is_file():
        raise RuntimeError("Retired onigiri gameconfig backup is missing")
    payload = backup.read_bytes()
    if override.exists():
        if not override.is_file() or override.read_bytes() != payload:
            raise RuntimeError(
                "Cannot restore onigiri gameconfig over a different file"
            )
        return
    temporary = override.with_name(override.name + ".allin1-restore.tmp")
    temporary.unlink(missing_ok=True)
    shutil.copy2(backup, temporary)
    if temporary.read_bytes() != payload:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Could not verify restored onigiri gameconfig")
    os.replace(temporary, override)


def _restore_map_update_payloads(
    rpf_patcher: Path,
    gta_path: Path,
    mods_archive: Path,
    original_gameconfig: Path,
    original_dlclist: Path,
    *,
    archive_created: bool,
) -> None:
    """Restore the exact archive payloads captured before map activation."""
    if archive_created:
        mods_archive.unlink(missing_ok=True)
        return
    failures: list[str] = []
    for entry, payload, label in (
        (_MAP_GAMECONFIG_ENTRY, original_gameconfig, "gameconfig.xml"),
        (_MAP_DLCLIST_ENTRY, original_dlclist, "dlclist.xml"),
    ):
        try:
            _map_patcher_command(
                rpf_patcher,
                [
                    "replace-entry", str(gta_path), str(mods_archive),
                    entry, str(payload),
                ],
                operation=f"Restore original {label}",
            )
        except Exception as exc:  # Best effort must attempt both payloads.
            failures.append(str(exc))
    if failures:
        raise RuntimeError("; ".join(failures))


def _dlclist_registers_allin1_maps(xml_text: str) -> bool:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid dlclist.xml after registration: {exc}") from exc
    expected = "dlcpacks:/allin1_maps"
    return any(
        (element.text or "").strip().rstrip("/").lower() == expected
        for element in root.iter()
        if isinstance(element.tag, str)
        and element.tag.rsplit("}", 1)[-1] == "Item"
    )


def _dlclist_registered_pack_names(xml_text: str) -> set[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid dlclist.xml after registration: {exc}") from exc
    result: set[str] = set()
    for element in root.iter():
        if not isinstance(element.tag, str) or \
                element.tag.rsplit("}", 1)[-1] != "Item":
            continue
        value = (element.text or "").strip().replace("\\", "/").rstrip("/")
        prefix = "dlcpacks:/"
        if value.casefold().startswith(prefix):
            name = value[len(prefix):].strip("/").casefold()
            if name:
                result.add(name)
    return result


def _activate_enhanced_standalone_map_dlc(
    gta_path: Path,
    result: InstallResult,
    output_rpf: Path,
    work: Path,
    *,
    asset_count: int,
) -> None:
    """Experimental pool/registration transaction; not used by Install/Repair.

    The transaction is retained for isolated tooling tests only.  Passing its
    static verification did not prevent a Story Mode loading crash, so no
    production caller may treat this helper as an approved activation path.
    """
    from allin1.generators import dlc_maps
    from allin1.generators.gameconfig import (
        ENHANCED_POOL_OVERRIDES,
        patch_gameconfig,
    )

    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    mods_archive, archive_created = _ensure_full_mods_update_archive(gta_path)
    original_gameconfig = work / "original-gameconfig.xml"
    original_dlclist = work / "original-dlclist.xml"
    patched_gameconfig = work / "patched-gameconfig.xml"
    verified_gameconfig = work / "verified-gameconfig.xml"
    verified_dlclist = work / "verified-dlclist.xml"
    destination_dir = (
        gta_path / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    receipt_path = destination_dir / _MAP_RUNTIME_RECEIPT
    originals_captured = False
    retired_onigiri: tuple[Path, Path] | None = None

    try:
        for entry, output, label in (
            (_MAP_GAMECONFIG_ENTRY, original_gameconfig, "gameconfig.xml"),
            (_MAP_DLCLIST_ENTRY, original_dlclist, "dlclist.xml"),
        ):
            _map_patcher_command(
                rpf_patcher,
                [
                    "extract-entry", str(gta_path), str(mods_archive),
                    entry, str(output),
                ],
                operation=f"Extract original {label}",
            )
        originals_captured = True

        original_text = original_gameconfig.read_bytes().decode("utf-8-sig")
        before_pools = _enhanced_gameconfig_pools(original_text)
        missing_pools = sorted(
            set(ENHANCED_POOL_OVERRIDES).difference(before_pools)
        )
        if missing_pools:
            raise ValueError(
                "Enhanced gameconfig.xml is incomplete for standalone-map "
                "activation; missing pools: " + ", ".join(missing_pools)
            )
        patched_text = patch_gameconfig(original_text)
        after_pools = _enhanced_gameconfig_pools(patched_text)
        patched_gameconfig.write_text(patched_text, encoding="utf-8")

        _map_patcher_command(
            rpf_patcher,
            [
                "replace-entry", str(gta_path), str(mods_archive),
                _MAP_GAMECONFIG_ENTRY, str(patched_gameconfig),
            ],
            operation="Install Enhanced gameconfig pool profile",
        )
        _map_patcher_command(
            rpf_patcher,
            [
                "extract-entry", str(gta_path), str(mods_archive),
                _MAP_GAMECONFIG_ENTRY, str(verified_gameconfig),
            ],
            operation="Re-extract Enhanced gameconfig",
        )
        verified_bytes = verified_gameconfig.read_bytes()
        expected_bytes = patched_gameconfig.read_bytes()
        verified_pools = _enhanced_gameconfig_pools(
            verified_bytes.decode("utf-8-sig")
        )
        if verified_bytes != expected_bytes or verified_pools != after_pools:
            raise RuntimeError(
                "Enhanced gameconfig verification did not match the installed payload"
            )

        retired_onigiri = _retire_known_sparse_onigiri_gameconfig(gta_path)
        dlc_maps.deploy_dlc_rpf(
            output_rpf,
            gta_path,
            layout=dlc_maps.STARTUP_IPL_PACK_LAYOUT,
            asset_count=asset_count,
        )
        receipt_path.unlink(missing_ok=True)
        if not _patch_dlclist_rpf(gta_path, result, "allin1_maps"):
            raise RuntimeError("Could not register the verified standalone map pack")
        _map_patcher_command(
            rpf_patcher,
            [
                "extract-entry", str(gta_path), str(mods_archive),
                _MAP_DLCLIST_ENTRY, str(verified_dlclist),
            ],
            operation="Re-extract registered dlclist.xml",
        )
        if not _dlclist_registers_allin1_maps(
            verified_dlclist.read_bytes().decode("utf-8-sig")
        ):
            raise RuntimeError(
                "dlclist.xml verification did not find the allin1_maps entry"
            )

        deployed_archive = destination_dir / "dlc.rpf"
        archive_bytes = deployed_archive.stat().st_size
        archive_sha256 = _map_file_sha256(deployed_archive)
        gameconfig_sha256 = hashlib.sha256(verified_bytes).hexdigest().upper()
        pool_receipt = {
            name: {"before": before_pools[name], "after": after_pools[name]}
            for name in sorted(ENHANCED_POOL_OVERRIDES)
            if name in before_pools and name in after_pools
        }
        marker = destination_dir / dlc_maps.ACTIVE_MARKER
        marker_temporary = marker.with_name(marker.name + ".tmp")
        marker_temporary.write_text(
            "Generated from this GTA installation and verified by ALLIN1.\n"
            f"layout={dlc_maps.STARTUP_IPL_PACK_LAYOUT}\n"
            "archive_registration=startup\n"
            "group_map_binding=false\n"
            "activation=verified-startup-registration\n"
            f"asset_count={asset_count}\n"
            f"archive_bytes={archive_bytes}\n"
            f"receipt={_MAP_RUNTIME_RECEIPT}\n"
            f"archive_sha256={archive_sha256}\n"
            f"gameconfig_sha256={gameconfig_sha256}\n",
            encoding="utf-8",
        )
        os.replace(marker_temporary, marker)

        # This receipt is the activation commit marker and must be written last.
        _write_json_atomic({
            "schema": 1,
            "status": "verified",
            "layout": dlc_maps.STARTUP_IPL_PACK_LAYOUT,
            "archive_sha256": archive_sha256,
            "archive_bytes": archive_bytes,
            "gameconfig_sha256": gameconfig_sha256,
            "gameconfig_entry": _MAP_GAMECONFIG_ENTRY,
            "pools": pool_receipt,
            "asset_count": asset_count,
            "edition": "enhanced",
        }, receipt_path)
    except Exception as activation_error:
        receipt_path.unlink(missing_ok=True)
        rollback_failures: list[str] = []
        try:
            if originals_captured:
                _restore_map_update_payloads(
                    rpf_patcher,
                    gta_path,
                    mods_archive,
                    original_gameconfig,
                    original_dlclist,
                    archive_created=archive_created,
                )
            elif archive_created:
                mods_archive.unlink(missing_ok=True)
        except Exception as rollback_error:
            rollback_failures.append(str(rollback_error))
        try:
            _restore_retired_onigiri_gameconfig(retired_onigiri)
        except Exception as rollback_error:
            rollback_failures.append(str(rollback_error))
        if rollback_failures:
            raise RuntimeError(
                f"Map activation failed ({activation_error}); rollback also "
                f"failed ({'; '.join(rollback_failures)})"
            ) from activation_error
        raise


def _restore_verified_startup_map_pool_profile(
    gta_path: Path,
    work: Path,
    result: InstallResult,
) -> bool:
    """Retire the pool changes from a proven startup-map activation.

    The map receipt is the only authority to lower a pool.  An invalid or
    absent receipt leaves the user's gameconfig untouched; the caller still
    removes the unsafe DLC registration before invoking this helper.
    """
    from allin1.generators import dlc_maps
    from allin1.generators.gameconfig import restore_enhanced_pool_profile

    pack_root = (
        gta_path / "mods" / "update" / "x64" / "dlcpacks"
        / dlc_maps.DLC_NAME
    )
    marker = pack_root / dlc_maps.ACTIVE_MARKER
    receipt_path = pack_root / dlc_maps.RUNTIME_RECEIPT
    try:
        marker_text = marker.read_text(encoding="utf-8")
    except OSError:
        return False
    if dlc_maps.STARTUP_IPL_PACK_LAYOUT not in marker_text:
        return False

    valid, detail, receipt = dlc_maps.validate_runtime_activation_receipt(
        pack_root, edition="enhanced",
    )
    if not valid or not isinstance(receipt, dict):
        result.warnings.append(
            "The retired startup map registration was quarantined, but its "
            "pool profile was left unchanged because the activation receipt "
            f"could not be verified ({detail})."
        )
        return False

    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    mods_archive = gta_path / "mods" / "update" / "update.rpf"
    if not rpf_patcher.is_file() or not mods_archive.is_file():
        raise RuntimeError(
            "Cannot retire the verified map pool profile without the full "
            "mods/update/update.rpf and RpfPatcher.exe"
        )

    original = work / "quarantine-original-gameconfig.xml"
    restored = work / "quarantine-restored-gameconfig.xml"
    verified = work / "quarantine-verified-gameconfig.xml"
    _map_patcher_command(
        rpf_patcher,
        [
            "extract-entry", str(gta_path), str(mods_archive),
            _MAP_GAMECONFIG_ENTRY, str(original),
        ],
        operation="Extract retired map gameconfig profile",
    )
    original_bytes = original.read_bytes()
    original_text = original_bytes.decode("utf-8-sig")
    restored_text = restore_enhanced_pool_profile(
        original_text, receipt.get("pools"),
    )
    if restored_text == original_text:
        receipt_path.unlink(missing_ok=True)
        return True
    restored.write_text(restored_text, encoding="utf-8")

    try:
        _map_patcher_command(
            rpf_patcher,
            [
                "replace-entry", str(gta_path), str(mods_archive),
                _MAP_GAMECONFIG_ENTRY, str(restored),
            ],
            operation="Retire ALLIN1 map pool profile",
        )
        _map_patcher_command(
            rpf_patcher,
            [
                "extract-entry", str(gta_path), str(mods_archive),
                _MAP_GAMECONFIG_ENTRY, str(verified),
            ],
            operation="Verify retired ALLIN1 map pool profile",
        )
        if verified.read_bytes() != restored.read_bytes():
            raise RuntimeError(
                "Retired ALLIN1 map pool profile failed verification"
            )
    except Exception:
        _map_patcher_command(
            rpf_patcher,
            [
                "replace-entry", str(gta_path), str(mods_archive),
                _MAP_GAMECONFIG_ENTRY, str(original),
            ],
            operation="Roll back retired map pool profile",
        )
        raise

    receipt_path.unlink(missing_ok=True)
    log.info("Retired the verified startup-map gameconfig pool profile")
    return True


def _effective_rockstar_dlc_archive(
    gta_path: Path, pack: str, archive_name: str = "dlc.rpf",
) -> tuple[Path, str]:
    """Resolve the same per-sibling mods overlay that GTA will mount."""
    relative = Path("update") / "x64" / "dlcpacks" / pack / archive_name
    override = gta_path / "mods" / relative
    if override.is_file():
        return override, "mods"
    stock = gta_path / relative
    if stock.is_file():
        return stock, "stock"
    raise FileNotFoundError(
        "Required Rockstar DLC archive is missing from both the stock and "
        f"mods overlay roots: {relative.as_posix()}"
    )


def _remove_owned_dlc_pack(gta_path: Path, pack_name: str) -> list[Path]:
    """Remove one exact ALLIN1-owned DLC directory from the mods overlay."""
    if pack_name not in {_GARMENT_BRIDGE_PACK, *(bridge.pack for bridge in ADDITIONAL_INTERIOR_BRIDGES)}:
        raise ValueError(f"Refusing to remove unowned DLC pack: {pack_name}")
    destination = gta_path / "mods/update/x64/dlcpacks" / pack_name
    if not destination.is_dir():
        return []
    shutil.rmtree(destination)
    log.info("Removed owned DLC pack at %s", destination)
    return [destination]


def _xml_child_text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return (child.text or "").strip() if child is not None else ""


def _find_content_changeset(root: ET.Element, name: str) -> ET.Element:
    matches = [
        item for item in root.findall("./contentChangeSets/Item")
        if _xml_child_text(item, "changeSetName").casefold()
        == name.casefold()
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Rockstar metadata does not contain exactly one {name} changeset"
        )
    return matches[0]


def _verify_garment_stock_metadata(
    content_path: Path, setup_path: Path, *, bridge: GarageBridge = GARMENT,
) -> dict[str, object]:
    """Verify one fixed stock interior closure before registration."""
    try:
        content = ET.parse(content_path).getroot()
        setup = ET.parse(setup_path).getroot()
    except ET.ParseError as exc:
        raise RuntimeError(f"{bridge.source_pack} metadata is invalid XML: {exc}") from exc

    device = _xml_child_text(setup, "deviceName")
    if device.casefold() != bridge.source_device.casefold():
        raise RuntimeError(
            f"{bridge.source_pack} device is {device!r}, expected {bridge.source_device!r}"
        )
    group_refs: list[str] = []
    for group in setup.findall("./contentChangeSetGroups/Item"):
        if _xml_child_text(group, "NameHash").casefold() != "group_map":
            continue
        group_refs.extend(
            (item.text or "").strip()
            for item in group.findall("./ContentChangeSets/Item")
            if (item.text or "").strip()
        )
    if bridge.changeset.casefold() not in {
        value.casefold() for value in group_refs
    }:
        raise RuntimeError(
            f"{bridge.source_pack} GROUP_MAP no longer references "
            + bridge.changeset
        )

    change = _find_content_changeset(content, bridge.changeset)
    enabled = [
        (item.text or "").strip()
        for item in change.findall("./mapChangeSetData/Item/filesToEnable/Item")
        if (item.text or "").strip()
    ]
    if not enabled:
        raise RuntimeError(
            f"{bridge.changeset} enables no registered map archives"
        )
    data_files = {
        _xml_child_text(item, "filename"): item
        for item in content.findall("./dataFiles/Item")
        if _xml_child_text(item, "filename")
    }
    for filename in enabled:
        item = data_files.get(filename)
        if item is None or _xml_child_text(item, "fileType") != "RPF_FILE":
            raise RuntimeError(
                f"{bridge.label} changeset references unregistered RPF {filename}"
            )
        disabled = item.find("disabled")
        if disabled is None or disabled.attrib.get("value", "").casefold() \
                != "true":
            raise RuntimeError(
                f"{bridge.label} changeset RPF is not deferred: {filename}"
            )

    if bridge.enabled_archives:
        expected = {
            f"{bridge.source_device}:/%PLATFORM%/levels/gta5/{name}".casefold()
            for name in bridge.enabled_archives
        }
        if len(enabled) != len(expected) or {name.casefold() for name in enabled} != expected:
            raise RuntimeError(f"{bridge.label} interior archive allowlist changed")
        for path in ("./filesToInvalidate/Item", "./filesToDisable/Item",
                     "./mapChangeSetData/Item/filesToInvalidate/Item",
                     "./mapChangeSetData/Item/filesToDisable/Item"):
            if change.findall(path):
                raise RuntimeError(f"{bridge.label} interior closure modifies world archives")
        maps = change.findall("./mapChangeSetData/Item")
        if len(maps) != 1 or _xml_child_text(maps[0], "associatedMap") != "MO_JIM_L11":
            raise RuntimeError(f"{bridge.label} associated Story map changed")

    requires_loading = change.find("requiresLoadingScreen")
    actual_requires_loading = requires_loading is not None and requires_loading.attrib.get(
        "value", "").casefold() == "true"
    if actual_requires_loading != bridge.requires_loading:
        raise RuntimeError(
            f"{bridge.label} changeset loading-screen semantics changed; an audited "
            "runtime contract update is required"
        )
    change_bytes = ET.tostring(change, encoding="utf-8")
    return {
        "device_name": device,
        "group_map_changesets": group_refs,
        "changeset_name": bridge.changeset,
        "changeset_sha256": hashlib.sha256(change_bytes).hexdigest().upper(),
        "enabled_rpf_count": len(enabled),
        "requires_loading_screen": actual_requires_loading,
    }


def _build_garment_bridge_metadata(root: Path, *, bridge: GarageBridge = GARMENT) -> tuple[Path, Path]:
    """Create the zero-payload, dormant stock-reference bridge metadata."""
    root.mkdir(parents=True, exist_ok=False)
    content = ET.Element("CDataFileMgr__ContentsOfDataFileXml")
    for name in (
        "disabledFiles", "includedXmlFiles", "includedDataFiles", "dataFiles",
    ):
        ET.SubElement(content, name)
    sets = ET.SubElement(content, "contentChangeSets")
    change = ET.SubElement(sets, "Item")
    ET.SubElement(change, "changeSetName").text = bridge.startup
    for name in (
        "mapChangeSetData", "filesToInvalidate", "filesToDisable",
        "filesToEnable", "txdToLoad", "txdToUnload", "residentResources",
        "unregisterResources",
    ):
        ET.SubElement(change, name)
    ET.SubElement(change, "requiresLoadingScreen").set("value", "false")
    ET.SubElement(content, "patchFiles")

    setup = ET.Element("SSetupData")
    ET.SubElement(setup, "deviceName").text = bridge.device
    ET.SubElement(setup, "datFile").text = "content.xml"
    ET.SubElement(setup, "timeStamp").text = "09/02/2026 00:00:00"
    ET.SubElement(setup, "nameHash").text = bridge.pack
    ET.SubElement(setup, "contentChangeSets")
    groups = ET.SubElement(setup, "contentChangeSetGroups")
    startup = ET.SubElement(groups, "Item")
    ET.SubElement(startup, "NameHash").text = "GROUP_STARTUP"
    startup_changes = ET.SubElement(startup, "ContentChangeSets")
    ET.SubElement(startup_changes, "Item").text = bridge.startup
    dormant = ET.SubElement(groups, "Item")
    ET.SubElement(dormant, "NameHash").text = bridge.group
    dormant_changes = ET.SubElement(dormant, "ContentChangeSets")
    ET.SubElement(dormant_changes, "Item").text = bridge.changeset
    ET.SubElement(setup, "startupScript")
    ET.SubElement(setup, "scriptCallstackSize").set("value", "0")
    ET.SubElement(setup, "type").text = "EXTRACONTENT_COMPAT_PACK"
    ET.SubElement(setup, "order").set("value", "74")
    ET.SubElement(setup, "minorOrder").set("value", "0")
    ET.SubElement(setup, "isLevelPack").set("value", "false")
    ET.SubElement(setup, "dependencyPackHash")
    ET.SubElement(setup, "requiredVersion")
    ET.SubElement(setup, "subPackCount").set("value", "0")

    ET.indent(content, space="  ")
    ET.indent(setup, space="  ")
    content_path = root / "content.xml"
    setup_path = root / "setup2.xml"
    ET.ElementTree(content).write(
        content_path, encoding="utf-8", xml_declaration=True,
    )
    ET.ElementTree(setup).write(
        setup_path, encoding="utf-8", xml_declaration=True,
    )
    return content_path, setup_path


def _deploy_garment_stock_bridge(
    gta_path: Path, result: InstallResult, *, bridge: GarageBridge = GARMENT,
) -> bool:
    """Install one property bridge, retaining Garment as the compatible default."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.is_file():
        raise FileNotFoundError(
            f"RpfPatcher.exe is required to build the {bridge.label} bridge"
        )

    with tempfile.TemporaryDirectory(prefix="allin1-garment-bridge-") as tmp:
        work = Path(tmp)
        source, source_kind = _effective_rockstar_dlc_archive(
            gta_path, bridge.source_pack,
        )
        stock_content = work / "rockstar-content.xml"
        stock_setup = work / "rockstar-setup2.xml"
        for name, destination in (
            ("content.xml", stock_content), ("setup2.xml", stock_setup),
        ):
            _map_patcher_command(
                rpf_patcher,
                ["extract-entry", str(gta_path), str(source), name,
                 str(destination)],
                operation=f"Read {bridge.source_pack} {name}",
            )
        semantics = _verify_garment_stock_metadata(
            stock_content, stock_setup, bridge=bridge,
        )

        staging = work / bridge.pack
        staged_content, staged_setup = _build_garment_bridge_metadata(staging, bridge=bridge)
        output = work / f"{bridge.pack}.dlc.rpf"
        _map_patcher_command(
            rpf_patcher,
            ["build-dlc", str(staging), str(output), "--gta-path",
             str(gta_path)],
            operation=f"Build {bridge.label} stock-reference bridge",
            timeout=300,
        )
        if not output.is_file() or output.stat().st_size <= 0:
            raise RuntimeError(f"{bridge.label} bridge produced no archive")
        packaged = work / "packaged"
        packaged.mkdir()
        for name, expected in (
            ("content.xml", staged_content), ("setup2.xml", staged_setup),
        ):
            actual = packaged / name
            _map_patcher_command(
                rpf_patcher,
                ["extract-entry", str(gta_path), str(output), name,
                 str(actual)],
                operation=f"Verify packaged {bridge.label} bridge {name}",
            )
            if actual.read_bytes() != expected.read_bytes():
                raise RuntimeError(
                    f"Packaged {bridge.label} bridge {name} differs from staging"
                )

        source_stat = source.stat()
        source_sha256 = _map_file_sha256(source)
        archive_sha256 = _map_file_sha256(output)
        archive_bytes = output.stat().st_size
        source_attestation = {
            "pack": bridge.source_pack,
            "archive": "dlc.rpf",
            "source": source_kind,
            "path": source.relative_to(gta_path).as_posix(),
            "size": source_stat.st_size,
            "mtime_ns": source_stat.st_mtime_ns,
            "archive_sha256": source_sha256,
            **semantics,
        }
        receipt = {
            "schema": 1,
            "status": "verified",
            "package_id": "allin1.online-content",
            "pack_name": bridge.pack,
            "device_name": bridge.device,
            "edition": "enhanced" if result.is_enhanced else "legacy",
            "layout": "stock-reference-v1-metadata-only",
            "runtime_contract":
                bridge.contract,
            "archive_bytes": archive_bytes,
            "archive_sha256": archive_sha256,
            "property_scope": bridge.scope,
            "activation": bridge.activation,
            "black_transition_required": True,
            "keep_resident": True,
            "release_on_exit": False,
            "declared_groups": ["GROUP_STARTUP", bridge.group],
            "stock_changeset": bridge.changeset,
            "ipls": list(bridge.ipls),
            "source_attestation": source_attestation,
        }

        destination = (
            gta_path / "mods/update/x64/dlcpacks" / bridge.pack
        )
        prior = work / "prior"
        had_prior = destination.is_dir()
        if had_prior:
            shutil.copytree(destination, prior)
        was_registered = False
        mods_archive = gta_path / "mods/update/update.rpf"
        before_dlclist = work / "before-dlclist.xml"
        if mods_archive.is_file():
            _map_patcher_command(
                rpf_patcher,
                ["extract-entry", str(gta_path), str(mods_archive),
                 _MAP_DLCLIST_ENTRY, str(before_dlclist)],
                operation="Read pre-install DLC registration",
            )
            was_registered = bridge.pack in \
                _dlclist_registered_pack_names(
                    before_dlclist.read_text(encoding="utf-8-sig")
                )
        try:
            if was_registered and not _unpatch_dlclist_rpf(gta_path, bridge.pack):
                raise RuntimeError(
                    f"Could not remove the prior {bridge.label} bridge registration"
                )
            _remove_owned_dlc_pack(gta_path, bridge.pack)
            destination.mkdir(parents=True)
            shutil.copy2(output, destination / "dlc.rpf")
            _write_json_atomic(receipt, destination / bridge.receipt)
            (destination / bridge.marker).write_text(
                f"ALLIN1 {bridge.label} stock-reference bridge\n"
                "schema=1\n"
                "status=verified\n"
                f"property_scope={bridge.scope}\n"
                f"activation={bridge.activation}\n"
                "black_transition_required=true\n"
                "keep_resident=true\n"
                "release_on_exit=false\n"
                f"declared_groups=GROUP_STARTUP,{bridge.group}\n"
                f"stock_changeset={bridge.changeset}\n"
                f"ipls={','.join(bridge.ipls)}\n"
                f"receipt={bridge.receipt}\n"
                f"archive_bytes={archive_bytes}\n"
                f"archive_sha256={archive_sha256}\n",
                encoding="utf-8",
            )
            if not _patch_dlclist_rpf(
                    gta_path, result, bridge.pack):
                raise RuntimeError(
                    f"Could not register the {bridge.label} bridge"
                )
            verified = work / "verified-dlclist.xml"
            _map_patcher_command(
                rpf_patcher,
                ["extract-entry", str(gta_path), str(mods_archive),
                 _MAP_DLCLIST_ENTRY, str(verified)],
            operation=f"Verify {bridge.label} bridge registration",
            )
            if bridge.pack not in _dlclist_registered_pack_names(
                    verified.read_text(encoding="utf-8-sig")):
                raise RuntimeError(
                    f"dlclist.xml does not contain the {bridge.label} bridge"
                )
        except Exception:
            _unpatch_dlclist_rpf(gta_path, bridge.pack)
            _remove_owned_dlc_pack(gta_path, bridge.pack)
            if had_prior:
                shutil.copytree(prior, destination)
            if was_registered:
                _patch_dlclist_rpf(gta_path, result, bridge.pack)
            raise

        log.info(
            "%s bridge installed: %d bytes; source %s verified",
            bridge.label, archive_bytes, source_attestation["path"],
        )
        return True


def _deploy_standalone_map_dlc(
    gta_path: Path,
    result: InstallResult,
    progress: InstallProgress | None = None,
) -> bool:
    """Install a verified zero-payload bridge only when it is transition-safe.

    The RPF contains only ``content.xml`` and ``setup2.xml``.  Each dormant
    ALLIN1 group references exact Rockstar RPF_FILE names proven against the
    target installation's own content metadata.  Structural verification is
    followed by a stricter zero-flash check because a complete official group
    can still invalidate global Story archives or require a loading screen.
    Failure occurs before any game mutation, and the outer install transaction
    removes an older unsafe bridge rather than leaving it active.
    """
    from allin1.generators import dlc_maps

    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.is_file():
        raise FileNotFoundError(
            "RpfPatcher.exe is required to build the garage map bridge"
        )

    with tempfile.TemporaryDirectory(prefix="allin1-map-bridge-") as tmp:
        work = Path(tmp)
        # Extract only Rockstar's small metadata documents.  Device names and
        # RPF filenames are validated from disk on every Install / Repair; a
        # game update cannot silently leave the bridge pointing at guesses.
        source_metadata: dict[str, tuple[Path, Path]] = {}
        source_archives: list[dict[str, object]] = []
        archive_identities = sorted({
            (asset.source_pack, asset.source_archive_name)
            for asset in dlc_maps.MAP_ASSETS
            if asset.file_type == "RPF_FILE"
        } | {
            (pack, "dlc.rpf")
            for pack in dlc_maps.ROCKSTAR_DEVICE_BY_PACK
        })
        for pack, archive_name in archive_identities:
            archive, source_kind = _effective_rockstar_dlc_archive(
                gta_path, pack, archive_name,
            )
            stat = archive.stat()
            source_archives.append({
                "pack": pack,
                "archive": archive_name,
                "source": source_kind,
                "path": archive.relative_to(gta_path).as_posix(),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            })
        for pack in sorted(dlc_maps.ROCKSTAR_DEVICE_BY_PACK):
            source, _source_kind = _effective_rockstar_dlc_archive(
                gta_path, pack,
            )
            content = work / f"rockstar-{pack}-content.xml"
            setup = work / f"rockstar-{pack}-setup2.xml"
            _map_patcher_command(
                rpf_patcher,
                [
                    "extract-entry", str(gta_path), str(source),
                    "content.xml", str(content),
                ],
                operation=f"Read {pack} content metadata",
            )
            _map_patcher_command(
                rpf_patcher,
                [
                    "extract-entry", str(gta_path), str(source),
                    "setup2.xml", str(setup),
                ],
                operation=f"Read {pack} setup metadata",
            )
            source_metadata[pack] = (content, setup)
        valid, detail = dlc_maps.validate_reference_source_metadata(
            source_metadata,
        )
        if not valid:
            raise RuntimeError(detail)

        groups = dlc_maps.reference_group_receipt(source_metadata)
        transition_safe, transition_detail = (
            dlc_maps.validate_zero_flash_reference_groups(groups)
        )
        if not transition_safe:
            raise RuntimeError(
                "Garage map bridge cannot meet the zero-flash Story Mode "
                f"contract: {transition_detail}"
            )

        # Build each dormant property group from complete Rockstar GROUP_MAP
        # changesets. This preserves official invalidation, collision, cache,
        # and loading-screen semantics instead of guessing a two-RPF subset.
        dlc_root = dlc_maps.create_reference_dlc_pack(work, source_metadata)
        valid, detail = (
            dlc_maps.validate_reference_pack_against_source_metadata(
                dlc_root, source_metadata,
            )
        )
        if not valid:
            raise RuntimeError(detail)

        output_rpf = work / "allin1_maps.bridge.rpf"
        _report_progress(progress, 50, "Building lightweight garage map bridge")
        _map_patcher_command(
            rpf_patcher,
            [
                "build-dlc", str(dlc_root), str(output_rpf),
                "--gta-path", str(gta_path),
            ],
            operation="Build garage map bridge",
            timeout=300,
        )
        if not output_rpf.is_file() or output_rpf.stat().st_size <= 0:
            raise RuntimeError("Garage map bridge build produced no archive")

        # Prove the packaged XML is byte-for-byte the metadata we validated.
        packaged = work / "packaged"
        packaged.mkdir()
        for name in ("content.xml", "setup2.xml"):
            extracted = packaged / name
            _map_patcher_command(
                rpf_patcher,
                [
                    "extract-entry", str(gta_path), str(output_rpf),
                    name, str(extracted),
                ],
                operation=f"Verify packaged {name}",
            )
            if extracted.read_bytes() != (dlc_root / name).read_bytes():
                raise RuntimeError(
                    f"Packaged garage bridge {name} differs from staging"
                )
        valid, detail = (
            dlc_maps.validate_reference_pack_against_source_metadata(
                packaged, source_metadata,
            )
        )
        if not valid:
            raise RuntimeError(detail)

        # Mutate the game only after every source and packaged artifact check
        # has passed.  A failure leaves no active map bridge rather than
        # restoring one of the retired copied-asset layouts.
        if not _unpatch_dlclist_rpf(gta_path, dlc_maps.DLC_NAME):
            raise RuntimeError("Could not remove the previous map registration")
        _remove_map_pack(gta_path)
        deployed = dlc_maps.deploy_dlc_rpf(
            output_rpf,
            gta_path,
            layout=dlc_maps.REFERENCE_PACK_LAYOUT,
            asset_count=0,
            reference_count=len(dlc_maps.MAP_ASSETS),
        )
        if not _patch_dlclist_rpf(gta_path, result, dlc_maps.DLC_NAME):
            raise RuntimeError("Could not register the garage map bridge")

        mods_archive = gta_path / "mods" / "update" / "update.rpf"
        verified_dlclist = work / "verified-dlclist.xml"
        if not mods_archive.is_file():
            raise RuntimeError("Registered mods/update/update.rpf is missing")
        _map_patcher_command(
            rpf_patcher,
            [
                "extract-entry", str(gta_path), str(mods_archive),
                _MAP_DLCLIST_ENTRY, str(verified_dlclist),
            ],
            operation="Verify garage map bridge registration",
        )
        if not _dlclist_registers_allin1_maps(
                verified_dlclist.read_text(encoding="utf-8-sig")):
            raise RuntimeError(
                "dlclist.xml does not contain the garage map bridge"
            )
        registered_packs = _dlclist_registered_pack_names(
            verified_dlclist.read_text(encoding="utf-8-sig")
        )
        missing_official = sorted(
            set(dlc_maps.ROCKSTAR_DEVICE_BY_PACK) - registered_packs
        )
        if missing_official:
            raise RuntimeError(
                "dlclist.xml does not register required Rockstar map DLCs: "
                + ", ".join(missing_official)
            )

        archive = deployed / "dlc.rpf"
        archive_hash = _map_file_sha256(archive)
        receipt = {
            "schema": 1,
            "status": "verified",
            "package_id": "allin1.online-content",
            "pack_name": dlc_maps.DLC_NAME,
            "layout": dlc_maps.REFERENCE_PACK_LAYOUT,
            "edition": "enhanced" if result.is_enhanced else "legacy",
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": archive_hash,
            "asset_count": 0,
            "reference_count": len(dlc_maps.MAP_ASSETS),
            "group_contract": dlc_maps.REFERENCE_GROUP_CONTRACT,
            "groups": groups,
            "source_archives": source_archives,
        }
        _write_json_atomic(receipt, deployed / _MAP_RUNTIME_RECEIPT)
        marker = deployed / dlc_maps.ACTIVE_MARKER
        marker.write_text(
            "Generated by ALLIN1; contains metadata only and no Rockstar assets.\n"
            f"layout={dlc_maps.REFERENCE_PACK_LAYOUT}\n"
            "archive_registration=metadata-bridge\n"
            "group_map_binding=false\n"
            "activation=property-group-runtime\n"
            f"receipt={_MAP_RUNTIME_RECEIPT}\n"
            "asset_count=0\n"
            f"reference_count={len(dlc_maps.MAP_ASSETS)}\n"
            f"group_contract={dlc_maps.REFERENCE_GROUP_CONTRACT}\n"
            f"archive_bytes={archive.stat().st_size}\n"
            f"archive_sha256={archive_hash}\n",
            encoding="utf-8",
        )
        log.info(
            "Garage map bridge installed: %d bytes, %d official references, "
            "%d dormant property groups",
            archive.stat().st_size, len(dlc_maps.MAP_ASSETS), len(groups),
        )
        return True


def _deploy_retired_copied_map_dlc(
    gta_path: Path,
    result: InstallResult,
    progress: InstallProgress | None = None,
) -> bool:
    """Build a local compatibility pack from the installed Rockstar RPFs.

    The public ALLIN1 package contains no Rockstar map assets.  Required
    entries are extracted from this GTA installation into a temporary staging
    tree, rearranged under the ALLIN1 device, packed, and then discarded.
    """
    from allin1.generators import dlc_maps

    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        result.warnings.append(
            "RpfPatcher.exe missing; standalone map support was not installed."
        )
        return False

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        # Crash-driven fail-safe: no edition may select a startup-registered
        # layout until a later implementation passes an actual Story Mode boot
        # canary.  Do not key this choice off ``result.is_enhanced``.
        selected_layout = dlc_maps.UNREGISTERED_PACK_LAYOUT
        dlc_root = dlc_maps.create_dlc_pack(
            work, layout=selected_layout,
        )
        combined_manifest = work / "extract-all.tsv"
        combined_manifest.write_text(
            "".join(
                f"{asset.source_path}\t{asset.destination_path}\n"
                for asset in dlc_maps.MAP_ASSETS
            ),
            encoding="utf-8",
        )
        grouped_assets: dict[tuple[str, str], list[dlc_maps.MapAsset]] = {}
        for asset in dlc_maps.MAP_ASSETS:
            key = (asset.source_pack, asset.source_archive_name)
            grouped_assets.setdefault(key, []).append(asset)

        for index, (source_key, assets) in enumerate(grouped_assets.items()):
            source_pack, source_archive_name = source_key
            source_archive = assets[0].source_archive(gta_path)
            if not source_archive.is_file():
                raise RuntimeError(
                    "Required GTA map archive is missing: "
                    f"{source_archive}"
                )
            manifest = work / f"extract-{source_pack}-{source_archive_name}.tsv"
            manifest.write_text(
                "".join(
                    f"{asset.source_path}\t{asset.destination_path}\n"
                    for asset in assets
                ),
                encoding="utf-8",
            )
            _report_progress(
                progress,
                44 + int((index / max(len(grouped_assets), 1)) * 3),
                f"Importing installed map assets ({source_pack}/{source_archive_name})",
            )
            extract = run_hidden(
                [
                    str(rpf_patcher), "extract-entries", str(gta_path),
                    str(source_archive), str(manifest), str(dlc_root),
                ],
                capture_output=True, text=True, timeout=300,
            )
            if extract.stdout:
                for line in extract.stdout.strip().splitlines():
                    log.info("RpfPatcher: %s", line)
            if extract.returncode != 0:
                error_msg = (
                    extract.stderr.strip() if extract.stderr
                    else f"exit code {extract.returncode}"
                )
                raise RuntimeError(
                    f"Could not import {source_pack} map assets: {error_msg}"
                )

        dlc_maps.filter_staged_proxy_assets(dlc_root)
        missing = dlc_maps.validate_staged_assets(dlc_root)
        if missing:
            raise RuntimeError(
                "Standalone map staging is incomplete: "
                + ", ".join(str(path) for path in missing[:5])
            )

        _report_progress(progress, 47, "Converting standalone map archives")
        convert = run_hidden(
            [
                str(rpf_patcher), "open-rpfs", str(gta_path),
                str(combined_manifest), str(dlc_root),
            ],
            capture_output=True, text=True, timeout=300,
        )
        if convert.stdout:
            for line in convert.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if convert.returncode != 0:
            error_msg = (
                convert.stderr.strip() if convert.stderr
                else f"exit code {convert.returncode}"
            )
            raise RuntimeError(
                f"Could not convert standalone map archives: {error_msg}"
            )

        output_rpf = work / "allin1_maps.dlc.rpf"
        _report_progress(progress, 48, "Packaging standalone map support")
        proc = run_hidden(
            [
                str(rpf_patcher), "build-dlc", str(dlc_root), str(output_rpf),
                "--gta-path", str(gta_path),
            ],
            capture_output=True, text=True, timeout=600,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode != 0:
            error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
            raise RuntimeError(f"RpfPatcher build-dlc failed: {error_msg}")
        if not output_rpf.is_file() or output_rpf.stat().st_size == 0:
            raise RuntimeError("RpfPatcher build-dlc produced no map archive")
        map_size = output_rpf.stat().st_size
        log.info(
            "Pruned standalone map DLC built: %d assets, %d bytes (%.2f MiB)",
            len(dlc_maps.MAP_ASSETS), map_size, map_size / (1024 * 1024),
        )

        _report_progress(progress, 49, "Verifying standalone map support")
        verify = run_hidden(
            [
                str(rpf_patcher), "verify-map-dlc", str(output_rpf),
                str(combined_manifest),
            ],
            capture_output=True, text=True, timeout=300,
        )
        if verify.returncode != 0:
            error_msg = (
                verify.stderr.strip() if verify.stderr
                else f"exit code {verify.returncode}"
            )
            raise RuntimeError(
                f"RpfPatcher verify-map-dlc failed: {error_msg}"
            )

        # Every edition remains explicitly unregistered.  A present archive is
        # an inspected/staged compatibility artifact, never an active DLC.
        # Unpatch before deployment so a stale registration from any previous
        # build cannot make the newly copied archive reachable at startup.
        if not _unpatch_dlclist_rpf(gta_path, "allin1_maps"):
            _remove_map_pack(gta_path)
            raise RuntimeError(
                "RpfPatcher unpatch failed; allin1_maps could not be "
                "quarantined safely"
            )
        if result.is_enhanced:
            _restore_verified_startup_map_pool_profile(
                gta_path, work, result,
            )

        deployed_dir = dlc_maps.deploy_dlc_rpf(
            output_rpf,
            gta_path,
            layout=selected_layout,
            asset_count=len(dlc_maps.MAP_ASSETS),
        )
        (deployed_dir / _MAP_RUNTIME_RECEIPT).unlink(missing_ok=True)
        result.warnings.append(
            "Map-backed garages and the yacht are temporarily unavailable. "
            "ALLIN1 built the local 16-asset map archive for inspection, but "
            "kept it unregistered after Story Mode startup crashes."
        )
        log.info(
            "Standalone map DLC built and deployed without startup registration "
            "(layout=%s, assets=%d, bytes=%d)",
            selected_layout, len(dlc_maps.MAP_ASSETS),
            output_rpf.stat().st_size,
        )
        return True


def _refresh_stale_mods_archive(gta_path: Path, mods_rpf: Path) -> bool:
    """Refresh an archive predating the current game update, transactionally.

    OpenRPF redirects the game to ``mods/update/update.rpf``.  An archive left
    behind by an older game build can therefore crash Enhanced before scripts
    load.  The caller has already made a rollback copy before this function is
    used.
    """
    base_rpf = gta_path / "update" / mods_rpf.name
    if not mods_rpf.is_file() or not base_rpf.is_file():
        return False
    # NTFS timestamps have ample resolution, but allow one second for archives
    # created by tools that round timestamps during extraction/copying.
    if mods_rpf.stat().st_mtime_ns + 1_000_000_000 >= base_rpf.stat().st_mtime_ns:
        return False

    available = shutil.disk_usage(mods_rpf.parent).free
    required = base_rpf.stat().st_size + (64 * 1024 * 1024)
    if available < required:
        raise RuntimeError(
            "Not enough free space to refresh stale mods/update/update.rpf "
            f"(need at least {required:,} bytes free)."
        )

    temporary = mods_rpf.with_name("update.rpf.allin1-refresh.tmp")
    temporary.unlink(missing_ok=True)
    try:
        shutil.copy2(base_rpf, temporary)
        if temporary.stat().st_size != base_rpf.stat().st_size:
            raise RuntimeError("Refreshed update.rpf copy failed size verification")
        os.replace(temporary, mods_rpf)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    log.warning(
        "Refreshed stale mods/update/update.rpf (%s) from current base archive (%s)",
        mods_rpf, base_rpf,
    )
    return True


def _restore_preview_archives(
    archives: list[tuple[Path, Path, bool]],
) -> None:
    """Restore every archive snapshot in reverse preparation order."""
    for archive, backup, existed_before in reversed(archives):
        _restore_preview_archive(archive, backup, existed_before)


def _restore_preview_archive(mods_rpf: Path, backup_rpf: Path, existed_before: bool) -> None:
    """Restore the exact pre-injection archive state after a tool failure."""
    if existed_before and backup_rpf.exists():
        shutil.copy2(backup_rpf, mods_rpf)
    elif not existed_before:
        mods_rpf.unlink(missing_ok=True)


def _remove_preview_pack(gta_path: Path) -> list[Path]:
    """Remove only ALLIN1-owned preview DLC directories."""
    removed: list[Path] = []
    for base in ("mods/update", "update"):
        dlc_dir = gta_path / base / "x64" / "dlcpacks" / "allin1_previews"
        if dlc_dir.exists():
            shutil.rmtree(dlc_dir)
            removed.append(dlc_dir)
            log.info("Removed preview DLC pack at %s", dlc_dir)
    return removed


def _remove_map_pack(gta_path: Path) -> list[Path]:
    """Remove only the ALLIN1-owned standalone map DLC directories."""
    from allin1.generators import dlc_maps
    removed = dlc_maps.remove_dlc_pack(gta_path)
    for path in removed:
        log.info("Removed standalone map DLC pack at %s", path)
    return removed


def _patch_dlclist_rpf(
    gta_path: Path, result: InstallResult, pack_name: str = "allin1_previews",
) -> bool:
    """Add an ALLIN1-owned DLC pack to the mods dlclist.xml.

    This tells the game to load our DLC pack at boot so the texture
    dictionaries inside it are indexed and available for streaming.
    """
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe not found — skipping dlclist patch")
        result.warnings.append("RpfPatcher.exe missing; preview textures "
                               "may not load without dlclist.xml entry.")
        return False

    try:
        proc = run_hidden(
            [str(rpf_patcher), "patch", str(gta_path), pack_name],
            # Registration now stages and verifies the complete update.rpf
            # before an atomic swap.  A mechanical disk can legitimately
            # need several minutes for that fail-safe transaction.
            capture_output=True, text=True, timeout=600,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode == 0:
            log.info("Patched dlclist.xml with %s entry", pack_name)
            return True
        else:
            error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
            log.error("Failed to patch dlclist.xml: %s", error_msg)
            result.warnings.append(f"Failed to patch dlclist.xml: {error_msg}")
            return False
    except Exception as exc:
        log.error("Could not patch dlclist.xml: %s", exc)
        result.warnings.append(f"Could not patch dlclist.xml: {exc}")
        return False


def _unpatch_dlclist_rpf(gta_path: Path, *pack_names: str) -> bool:
    """Remove selected ALLIN1 entries, or every owned entry during uninstall."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe not found — cannot unpatch dlclist")
        return False

    try:
        proc = run_hidden(
            [str(rpf_patcher), "unpatch", str(gta_path), *pack_names],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            log.info("Unpatched dlclist.xml in update.rpf")
            return True
        else:
            log.warning("RpfPatcher unpatch failed (rc=%d): %s",
                        proc.returncode,
                        (proc.stderr or "")[:300])
            return False
    except Exception as exc:
        log.warning("Could not unpatch dlclist.xml: %s", exc)
        return False


def _install_smoke_tuning(gta_path: Path, result: InstallResult) -> bool:
    """Patch only ALLIN1's dedicated smoke-grenade records in update.rpf."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        result.warnings.append(
            "RpfPatcher.exe missing; enhanced smoke archive tuning was skipped."
        )
        return False
    try:
        proc = run_hidden(
            [str(rpf_patcher), "install-smoke-tuning", str(gta_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher smoke: %s", line)
        if proc.returncode == 0:
            log.info("Installed and verified custom smoke archive tuning")
            return True
        detail = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
        result.warnings.append(f"Enhanced smoke archive tuning failed: {detail}")
        return False
    except Exception as exc:
        log.error("Could not install smoke archive tuning: %s", exc, exc_info=True)
        result.warnings.append(f"Could not install smoke archive tuning: {exc}")
        return False


def _remove_smoke_tuning(gta_path: Path) -> None:
    """Restore only ALLIN1's two original smoke entries when installed."""
    marker = gta_path / "scripts" / "ALLIN1_smoke_tuning.json"
    if not marker.exists():
        return
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe missing — cannot restore smoke tuning entries")
        return
    try:
        proc = run_hidden(
            [str(rpf_patcher), "remove-smoke-tuning", str(gta_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            log.info("Removed custom smoke archive tuning")
        else:
            log.warning("RpfPatcher smoke removal failed (rc=%d): %s",
                        proc.returncode, (proc.stderr or "")[:300])
    except Exception as exc:
        log.warning("Could not remove smoke archive tuning: %s", exc)


def _install_colored_smoke_weapons(
    gta_path: Path, result: InstallResult,
) -> bool:
    """Generate and install seven current-build smoke weapon definitions."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        result.warnings.append(
            "RpfPatcher.exe missing; independent colored smoke weapons were skipped."
        )
        return False
    try:
        proc = run_hidden(
            [str(rpf_patcher), "install-colored-smoke-weapons", str(gta_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher colored smoke: %s", line)
        if proc.returncode == 0:
            log.info("Installed and verified independent colored smoke weapons")
            return True
        detail = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
        result.warnings.append(f"Colored smoke weapon installation failed: {detail}")
        return False
    except Exception as exc:
        log.error("Could not install colored smoke weapons: %s", exc, exc_info=True)
        result.warnings.append(f"Could not install colored smoke weapons: {exc}")
        return False


def _remove_colored_smoke_weapons(gta_path: Path) -> None:
    """Remove only the ALLIN1 colored-smoke DLC and registration."""
    marker = gta_path / "scripts" / "ALLIN1_colored_smoke_weapons.json"
    archive = (
        gta_path / "mods" / "update" / "x64" / "dlcpacks" /
        COLORED_SMOKE_PACK_ID / "dlc.rpf"
    )
    if not marker.exists() and not archive.exists():
        return
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe missing — cannot remove colored smoke DLC")
        return
    try:
        proc = run_hidden(
            [str(rpf_patcher), "remove-colored-smoke-weapons", str(gta_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            log.info("Removed independent colored smoke weapons")
        else:
            log.warning("Colored smoke removal failed (rc=%d): %s",
                        proc.returncode, (proc.stderr or "")[:300])
    except Exception as exc:
        log.warning("Could not remove colored smoke weapons: %s", exc)


def _remove_merged_smoke_canary(gta_path: Path) -> None:
    """Restore base weapons.meta when the one-color merge canary is present."""
    marker = (
        gta_path / "scripts" / "ALLIN1_colored_smoke_merged_canary.json"
    )
    if not marker.is_file():
        return
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning(
            "RpfPatcher.exe missing — cannot restore merged smoke canary"
        )
        return
    try:
        proc = run_hidden(
            [str(rpf_patcher), "remove-merged-smoke-canary", str(gta_path)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            log.info("Restored base weapons.meta after merged smoke canary")
        else:
            log.warning(
                "Merged smoke canary removal failed (rc=%d): %s",
                proc.returncode, (proc.stderr or "")[:300],
            )
    except Exception as exc:
        log.warning("Could not remove merged smoke canary: %s", exc)


def _write_rpf_quarantine(gta_path: Path) -> None:
    """Persist boot-tested RPF exclusions for diagnostics and pre-launch checks."""
    scripts = gta_path / SCRIPTS_DIR
    scripts.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(
        {
            "schema": 1,
            "packs": {
                COLORED_SMOKE_PACK_ID: {
                    "state": "quarantined",
                    "reason": COLORED_SMOKE_QUARANTINE_REASON,
                }
            },
        },
        scripts / "ALLIN1_rpf_quarantine.json",
    )


def _remove_preview_ytds(gta_path: Path) -> None:
    """Remove ALLIN1 preview .ytd files from script_txds.rpf."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.debug("RpfPatcher.exe not found — skipping ytd removal")
        return

    # Remove all .ytd files whose name starts with "allin1_"
    try:
        proc = run_hidden(
            [str(rpf_patcher), "remove-ytd", str(gta_path), "allin1_"],
            capture_output=True, text=True, timeout=120,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode == 0:
            log.info("Removed ALLIN1 .ytd files from script_txds.rpf")
        else:
            log.warning("RpfPatcher remove-ytd failed (rc=%d): %s",
                        proc.returncode,
                        (proc.stderr or "")[:300])
    except Exception as exc:
        log.warning("Could not remove .ytd files from script_txds.rpf: %s", exc)
