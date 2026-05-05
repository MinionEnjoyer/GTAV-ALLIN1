"""Main installer orchestrator.

Coordinates the full install/uninstall flow: config loading, GTA V detection,
backup creation, generator invocation, and file placement.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from allin1.backup import create_backup, restore_backup
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.generators.dlclist import patch_dlclist
from allin1.generators.gameconfig import patch_gameconfig
from allin1.generators.popgroups import create_base_template, generate_popgroups_xml
from allin1.vehicles.database import Vehicle, VehicleDatabase

log = logging.getLogger("allin1.installer")


ASI_FILENAME = "ALLIN1.asi"

# Resolve the asi/dist/ directory relative to this source file.
_ASI_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "asi" / "dist"


@dataclass
class InstallResult:
    gta_path: Path
    vehicles_enabled: int
    files_modified: list[str] = field(default_factory=list)
    dlc_packs_added: list[str] = field(default_factory=list)
    backup_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)
    asi_deployed: bool = False


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


def get_enabled_vehicles(db: VehicleDatabase, config: Config) -> list[Vehicle]:
    """Get the list of vehicles to enable based on config filters."""
    if config.vehicles.enable_all:
        return db.filter(
            disabled_classes=config.vehicles.disabled_classes,
            disabled_vehicles=config.vehicles.disabled_vehicles,
        )
    # When enable_all is false, only explicitly enabled vehicles are included.
    # For now, this still uses the full list minus exclusions.
    # The catalog UI will generate a config with specific disabled_vehicles.
    return db.filter(
        disabled_classes=config.vehicles.disabled_classes,
        disabled_vehicles=config.vehicles.disabled_vehicles,
    )


def install(config: Config, db: VehicleDatabase) -> InstallResult:
    """Run the full installation process."""
    log.info("=== Starting installation ===")
    gta_path = resolve_gta_path(config)
    mods_dir = gta_path / "mods"
    result = InstallResult(gta_path=gta_path, vehicles_enabled=0)

    vehicles = get_enabled_vehicles(db, config)
    result.vehicles_enabled = len(vehicles)
    log.info("Vehicles enabled: %d (of %d total)", len(vehicles), len(db))

    # --- File paths ---
    # dlclist.xml and gameconfig.xml live under common/data/
    update_rpf_data = mods_dir / "update" / "update.rpf" / "common" / "data"
    dlclist_path = update_rpf_data / "dlclist.xml"
    gameconfig_path = update_rpf_data / "gameconfig.xml"

    # popgroups.ymt lives under x64/levels/gta5/ (NOT common/data/)
    popgroups_dir = mods_dir / "update" / "update.rpf" / "x64" / "levels" / "gta5"
    popgroups_path = popgroups_dir / "popgroups.ymt"

    # Collect files that exist for backup
    files_to_backup = [p for p in [popgroups_path, dlclist_path, gameconfig_path] if p.exists()]

    # Also check original game files as backup source
    orig_data = gta_path / "update" / "update.rpf" / "common" / "data"
    orig_popgroups = gta_path / "update" / "update.rpf" / "x64" / "levels" / "gta5" / "popgroups.ymt"
    for orig_file in [orig_data / "dlclist.xml", orig_data / "gameconfig.xml", orig_popgroups]:
        if orig_file.exists() and orig_file not in files_to_backup:
            files_to_backup.append(orig_file)

    # --- Backup ---
    if config.general.backup and files_to_backup:
        log.info("Creating backup of %d file(s)...", len(files_to_backup))
        result.backup_dir = create_backup(gta_path, files_to_backup)
        log.info("Backup saved to: %s", result.backup_dir)
    elif not config.general.backup:
        log.info("Backup disabled in config")

    # --- Ensure mods directory structure ---
    update_rpf_data.mkdir(parents=True, exist_ok=True)
    popgroups_dir.mkdir(parents=True, exist_ok=True)
    log.debug("Mods data directory: %s", update_rpf_data)
    log.debug("Mods popgroups directory: %s", popgroups_dir)

    # --- Generate popgroups ---
    if config.traffic.enabled and config.traffic.density != "none":
        log.info("Generating popgroups.ymt (density=%s, rich_only_supers=%s)...",
                 config.traffic.density, config.traffic.rich_areas_only_supers)
        base_xml = _load_or_create_popgroups(popgroups_path, orig_popgroups)
        modified_xml = generate_popgroups_xml(
            base_xml,
            vehicles,
            density=config.traffic.density,
            rich_areas_only_supers=config.traffic.rich_areas_only_supers,
        )
        popgroups_path.write_text(modified_xml, encoding="utf-8")
        result.files_modified.append(str(popgroups_path))
        log.info("Wrote popgroups.ymt")
    else:
        log.info("Traffic spawning disabled — skipping popgroups.ymt")

    # --- Patch dlclist.xml ---
    log.info("Patching dlclist.xml...")
    dlclist_xml = _load_or_create_dlclist(dlclist_path, orig_data / "dlclist.xml")
    patched_dlclist, added_packs = patch_dlclist(dlclist_xml)
    if added_packs:
        dlclist_path.write_text(patched_dlclist, encoding="utf-8")
        result.files_modified.append(str(dlclist_path))
        result.dlc_packs_added = added_packs
        log.info("Added %d DLC pack(s) to dlclist.xml", len(added_packs))
    else:
        log.info("dlclist.xml already has all required DLC packs")

    # --- Patch gameconfig.xml ---
    log.info("Patching gameconfig.xml...")
    gameconfig_xml = _load_gameconfig(gameconfig_path, orig_data / "gameconfig.xml")
    if gameconfig_xml:
        patched_gc = patch_gameconfig(gameconfig_xml)
        gameconfig_path.write_text(patched_gc, encoding="utf-8")
        result.files_modified.append(str(gameconfig_path))
        log.info("Wrote gameconfig.xml with increased pool sizes")
    else:
        result.warnings.append(
            "gameconfig.xml not found. You may need a modified gameconfig "
            "to support 400+ vehicles. See community gameconfig mods."
        )
        log.warning("gameconfig.xml not found — skipped")

    # --- Deploy ASI plugin (DLC vehicle despawn fix) ---
    result.asi_deployed = _deploy_asi(gta_path)

    log.info("=== Installation complete: %d files modified ===", len(result.files_modified))
    return result


def uninstall(config: Config) -> list[Path]:
    """Restore backed-up files and remove ASI plugin."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    restored = restore_backup(gta_path)

    # Remove the ASI plugin from the game directory.
    asi_dest = gta_path / ASI_FILENAME
    if asi_dest.exists():
        asi_dest.unlink()
        restored.append(asi_dest)
        log.info("Removed %s from GTA V directory", ASI_FILENAME)

    log.info("=== Uninstall complete: %d files restored ===", len(restored))
    return restored


def _load_or_create_popgroups(mods_path: Path, orig_path: Path) -> str:
    """Load existing popgroups or create a base template."""
    if mods_path.exists():
        return mods_path.read_text(encoding="utf-8")
    if orig_path.exists():
        return orig_path.read_text(encoding="utf-8")
    return create_base_template()


def _load_or_create_dlclist(mods_path: Path, orig_path: Path) -> str:
    """Load existing dlclist.xml."""
    if mods_path.exists():
        return mods_path.read_text(encoding="utf-8")
    if orig_path.exists():
        return orig_path.read_text(encoding="utf-8")
    # Minimal dlclist if none found
    return '<?xml version="1.0" encoding="UTF-8"?>\n<SMandatoryPacksData>\n  <Paths>\n  </Paths>\n</SMandatoryPacksData>'


def _load_gameconfig(mods_path: Path, orig_path: Path) -> str | None:
    """Load existing gameconfig.xml, or None if not found."""
    if mods_path.exists():
        return mods_path.read_text(encoding="utf-8")
    if orig_path.exists():
        return orig_path.read_text(encoding="utf-8")
    return None


def _deploy_asi(gta_path: Path) -> bool:
    """Copy ALLIN1.asi to the GTA V root directory.

    The ASI disables the DLC vehicle despawn mechanism in single player.
    It's placed next to GTA5.exe (not in mods/) so the ASI loader picks it up.

    Returns True if deployed successfully, False if the source binary is missing.
    """
    src = _ASI_DIST_DIR / ASI_FILENAME
    if not src.exists():
        log.warning(
            "%s not found at %s — DLC despawn fix will NOT be active. "
            "Build the ASI from asi/ or download a pre-built binary.",
            ASI_FILENAME, _ASI_DIST_DIR,
        )
        return False

    dest = gta_path / ASI_FILENAME
    shutil.copy2(src, dest)
    log.info("Deployed %s to %s", ASI_FILENAME, dest)
    return True
