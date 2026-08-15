"""Main installer orchestrator.

Coordinates the install/uninstall flow: config loading, GTA V detection,
and ALLIN1 script deployment.

File placement:
- <GTA V root>/scripts/ALLIN1.dll — SHVDN script loaded at runtime.
  Spawns the configured GTA Online DLC vehicle catalog into Story Mode traffic.
- <GTA V root>/scripts/ALLIN1.toml — Config deployed from project config.toml.

Prerequisites (installed separately by the user):
- ScriptHookV (dinput8.dll + ScriptHookV.dll)
- ScriptHookVDotNet Enhanced (ScriptHookVDotNet.asi + ScriptHookVDotNet3.dll)
- OpenRPF (Enhanced) or OpenIV.asi (Legacy) — optional, for GBAY artwork only
"""

from __future__ import annotations

import logging
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from allin1 import asi_loader
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.health import inspect_windows_binary
from allin1.preview_assets import GEAR_PREVIEW_ITEMS, WORLD_ASSET_PREVIEW_ITEMS
from allin1.processes import run_hidden
from allin1.vehicles.database import VehicleDatabase
from allin1.versioning import VERSION_FILE, write_installed_version

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

log = logging.getLogger("allin1.installer")

DLL_FILENAME = "ALLIN1.dll"
LEMONUI_FILENAME = "LemonUI.SHVDN3.dll"
GROUNDING_CATALOG_FILENAME = "ALLIN1_vehicle_grounding.json"
SCRIPTS_DIR = "scripts"
ALLIN1_DATA_DIR = "ALLIN1"  # Legacy data folder — cleaned up on install

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
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_DIST_DIR = _PROJECT_ROOT / "script" / "dist"
_TOOLS_DIR = _PROJECT_ROOT / "tools"

def _copy_atomic(source: Path, destination: Path) -> None:
    """Replace a deployed file without exposing a partial destination."""
    temporary = destination.with_name(destination.name + ".tmp")
    backup = destination.with_name(destination.name + ".bak")
    try:
        shutil.copy2(source, temporary)
        if destination.exists():
            shutil.copy2(destination, backup)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        if backup.exists():
            shutil.copy2(backup, destination)
        raise


def _write_json_atomic(payload: dict, destination: Path) -> None:
    """Replace a JSON file while retaining the previous checkpoint."""
    temporary = destination.with_name(destination.name + ".tmp")
    backup = destination.with_name(destination.name + ".bak")
    try:
        temporary.write_text(
            json.dumps(payload, separators=(",", ":")), encoding="utf-8"
        )
        if destination.exists():
            shutil.copy2(destination, backup)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        if backup.exists():
            shutil.copy2(backup, destination)
        raise


def _is_enhanced(gta_path: Path) -> bool:
    """Check if this is GTA V Enhanced Edition."""
    return (gta_path / "GTA5_Enhanced.exe").exists()


@dataclass
class InstallResult:
    gta_path: Path
    is_enhanced: bool = False
    dll_deployed: bool = False
    scripthookv_found: bool = False
    shvdn_found: bool = False
    openrpf_found: bool = False
    rpf_previews_deployed: bool = False
    standalone_maps_deployed: bool = False
    battleye_status: str = ""
    warnings: list[str] = field(default_factory=list)


def resolve_gta_path(config: Config) -> Path:
    """Resolve the GTA V path from config or auto-detection."""
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


def _report_progress(
    callback: InstallProgress | None, percentage: int, detail: str,
) -> None:
    if callback is not None:
        callback(max(0, min(100, percentage)), detail)


def install(
    config: Config,
    db: VehicleDatabase,
    progress: InstallProgress | None = None,
) -> InstallResult:
    """Run the full installation process."""
    log.info("=== Starting installation ===")
    _report_progress(progress, 0, "Preparing repair")
    gta_path = resolve_gta_path(config)
    _report_progress(progress, 5, "Game folder verified")
    enhanced = _is_enhanced(gta_path)
    result = InstallResult(gta_path=gta_path, is_enhanced=enhanced)

    log.info("GTA V edition: %s", "Enhanced" if enhanced else "Legacy")

    # --- Clean up files from previous ALLIN1 versions ---
    _clean_legacy_files(gta_path, result)
    _report_progress(progress, 15, "Previous installation checked")

    # --- Deploy ALLIN1.dll script ---
    result.dll_deployed = _deploy_script(gta_path)
    _report_progress(progress, 28, "Client files repaired")

    # --- Check for ScriptHookV ---
    result.scripthookv_found = _check_scripthookv(gta_path)

    # --- Check for ScriptHookVDotNet ---
    result.shvdn_found = _check_shvdn(gta_path)

    # --- Detect optional RPF loader; never install third-party executable code ---
    result.openrpf_found = _check_openrpf(gta_path, enhanced)
    _report_progress(progress, 38, "Dependencies verified")

    # Rebuild ALLIN1-owned DLC registrations transactionally. The standalone
    # map pack is useful even when artwork has been disabled.
    _remove_preview_pack(gta_path)
    _remove_map_pack(gta_path)
    _unpatch_dlclist_rpf(gta_path)
    _report_progress(progress, 43, "DLC registration refreshed")

    # Build the standalone compatibility pack from this GTA installation.
    # Garment Factory, Davis, Harmony, Grapeseed, Paleto Bay, and the yacht
    # deliberately do not enable the global multiplayer map as a fallback, so
    # a successful repair must leave this pack installed and registered.
    result.standalone_maps_deployed = _deploy_standalone_map_dlc(
        gta_path, result, progress=progress,
    )
    if not result.standalone_maps_deployed:
        raise RuntimeError(
            "Standalone map support could not be installed; ALLIN1 garage "
            "interiors would be unavailable."
        )
    _report_progress(progress, 49, "Standalone map support installed")

    if config.general.enable_rpf_previews:
        if not result.openrpf_found:
            result.warnings.append(
                "RPF previews requested but no compatible OpenRPF/OpenIV loader was detected; "
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

    # --- Write -nobattleye to commandline.txt (belt-and-suspenders) ---
    result.battleye_status = asi_loader.ensure_nobattleye(gta_path, enhanced)
    _report_progress(progress, 96, "Finalizing Story Mode settings")

    log.info("=== Installation complete ===")
    _report_progress(progress, 100, "Repair complete")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove ALLIN1 files from the GTA V directory."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    removed: list[Path] = []

    # Remove script DLL, config, and log from scripts/
    scripts_dir = gta_path / SCRIPTS_DIR
    for fname in (DLL_FILENAME, LEMONUI_FILENAME, "ALLIN1.toml",
                   "ALLIN1.log", "ALLIN1_spawner.log", "ALLIN1_gbay.log",
                   "ALLIN1_client.log", "ALLIN1_client.log.1",
                   "ALLIN1_client.log.2", "ALLIN1_client.log.3",
                   "ALLIN1_garage.json", "ALLIN1_garages.json",
                   "ALLIN1_floor_garage.json", "ALLIN1_floor_garage.json.bak",
                   "ALLIN1_floor_themes.json", "ALLIN1_floor_themes.json.bak",
                   "ALLIN1_davis_garage.json", "ALLIN1_davis_garage.json.bak",
                   "ALLIN1_davis_customization.json", "ALLIN1_davis_customization.json.bak",
                    "ALLIN1_garment_factory_garage.json",
                    "ALLIN1_garment_factory_garage.json.bak",
                    "ALLIN1_rural_garage.json", "ALLIN1_rural_garage.json.bak",
                    "ALLIN1_paleto_garage.json", "ALLIN1_paleto_garage.json.bak",
                    "ALLIN1_yacht_helipad.json", "ALLIN1_yacht_helipad.json.bak",
                   GROUNDING_CATALOG_FILENAME,
                   GROUNDING_CATALOG_FILENAME + ".bak",
                   *RETIRED_DEVELOPER_ARTIFACTS,
                   "ALLIN1_garages.json.bak", "ALLIN1_gbay_preferences.json",
                   "ALLIN1_gbay_preferences.json.bak", "ALLIN1_session.lock",
                   "ALLIN1_garage.quarantine.json", "ALLIN1_preview_pending.toml",
                   VERSION_FILE, "ALLIN1.ini"):
        fpath = scripts_dir / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fpath)
            log.info("Removed %s from scripts/", fname)

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

    # Remove ALLIN1/ data folder (legacy — no longer used)
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        for f in data_dir.iterdir():
            removed.append(f)
        shutil.rmtree(data_dir)
        log.info("Removed %s/ data folder", ALLIN1_DATA_DIR)

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

    # Unpatch dlclist.xml in mods/update/update.rpf (legacy cleanup)
    _unpatch_dlclist_rpf(gta_path)

    # Remove ALLIN1 .ytd files from script_txds.rpf inside mods/update.rpf
    _remove_preview_ytds(gta_path)

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

    # Remove legacy ALLIN1/ data folder
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        try:
            shutil.rmtree(data_dir)
            result.warnings.append(
                f"Removed old {ALLIN1_DATA_DIR}/ folder (no longer needed)."
            )
            log.info("Removed legacy data folder: %s", data_dir)
        except OSError as exc:
            result.warnings.append(
                f"Could not remove {ALLIN1_DATA_DIR}/: {exc}. Delete it manually."
            )
            log.warning("Failed to remove %s: %s", data_dir, exc)


def _deploy_script(gta_path: Path) -> bool:
    """Copy ALLIN1.dll to GTA V scripts/ folder. Returns True if deployed."""
    src = _SCRIPT_DIST_DIR / DLL_FILENAME
    if not src.exists():
        log.warning(
            "%s not found at %s — run the GitHub Actions build or "
            "download from Releases.",
            DLL_FILENAME, _SCRIPT_DIST_DIR,
        )
        return False

    scripts_dir = gta_path / SCRIPTS_DIR
    scripts_dir.mkdir(exist_ok=True)
    dest = scripts_dir / DLL_FILENAME
    _copy_atomic(src, dest)
    write_installed_version(scripts_dir)
    log.info("Deployed %s → %s", DLL_FILENAME, dest)

    # Deploy LemonUI dependency (required by GBAY menu system)
    lemonui_src = _SCRIPT_DIST_DIR / LEMONUI_FILENAME
    if lemonui_src.exists():
        lemonui_dest = scripts_dir / LEMONUI_FILENAME
        _copy_atomic(lemonui_src, lemonui_dest)
        log.info("Deployed %s → %s", LEMONUI_FILENAME, lemonui_dest)

    # Deploy config.toml as ALLIN1.toml so the C# script can read it
    toml_dest = scripts_dir / "ALLIN1.toml"
    toml_src = _PROJECT_ROOT / "config.toml"
    if not toml_src.exists():
        toml_src = _PROJECT_ROOT / "config.example.toml"
    if toml_src.exists():
        _copy_atomic(toml_src, toml_dest)
        log.info("Deployed config %s -> %s", toml_src.name, toml_dest)

    _deploy_grounding_catalog(scripts_dir)

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
    """Check if ScriptHookVDotNet is installed in the game directory."""
    return inspect_windows_binary(gta_path / "ScriptHookVDotNet.asi").valid


def _check_openrpf(gta_path: Path, enhanced: bool) -> bool:
    """Detect a user-installed RPF loader without downloading executable code."""
    if not enhanced:
        asi_path = gta_path / "OpenIV.asi"
        found = inspect_windows_binary(asi_path).valid
        if found and not inspect_windows_binary(gta_path / "dinput8.dll").valid:
            log.warning("OpenIV.asi exists but dinput8.dll ASI loader is missing")
            found = False
        if found:
            log.info("OpenIV.asi found — mods folder support available")
        else:
            log.warning(
                "OpenIV.asi not found. Install OpenIV for vehicle preview "
                "textures to work."
            )
        return found

    # OpenIV.asi is a Legacy binary; loading it alongside OpenRPF on Enhanced
    # is an invalid configuration.
    asi_path = gta_path / "OpenRPF.asi"
    if not asi_path.exists():
        log.warning("OpenRPF.asi not found; optional artwork will use placeholders")
        return False
    if (gta_path / "OpenIV.asi").exists():
        log.error("Both OpenRPF.asi and OpenIV.asi are installed on Enhanced")
        return False
    inspection = inspect_windows_binary(asi_path)
    if not inspection.valid:
        log.warning("OpenRPF.asi is invalid: %s", inspection.reason)
        return False
    asi_loaders = ("dsound.dll", "xinput1_4.dll", "dinput8.dll")
    if not any(inspect_windows_binary(gta_path / name).valid for name in asi_loaders):
        log.warning("OpenRPF.asi exists but no compatible ASI loader was detected")
        return False
    log.info("User-installed OpenRPF.asi and ASI loader detected")
    return True


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


def _deploy_standalone_map_dlc(
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
        dlc_root = dlc_maps.create_dlc_pack(work)
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

        deployed_dir = dlc_maps.deploy_dlc_rpf(output_rpf, gta_path)
        if not _patch_dlclist_rpf(gta_path, result, "allin1_maps"):
            shutil.rmtree(deployed_dir, ignore_errors=True)
            raise RuntimeError(
                "RpfPatcher patch failed; could not register allin1_maps"
            )
        log.info("Standalone map DLC built, deployed, and registered")
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
            capture_output=True, text=True, timeout=120,
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


def _unpatch_dlclist_rpf(gta_path: Path) -> None:
    """Remove ALLIN1 entry from dlclist.xml inside update.rpf (legacy cleanup)."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.debug("RpfPatcher.exe not found — skipping dlclist unpatch")
        return

    try:
        proc = run_hidden(
            [str(rpf_patcher), "unpatch", str(gta_path)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            log.info("Unpatched dlclist.xml in update.rpf")
        else:
            log.warning("RpfPatcher unpatch failed (rc=%d): %s",
                        proc.returncode,
                        (proc.stderr or "")[:300])
    except Exception as exc:
        log.warning("Could not unpatch dlclist.xml: %s", exc)


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
