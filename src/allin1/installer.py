"""Main installer orchestrator.

Coordinates the full install/uninstall flow: config loading, GTA V detection,
backup creation, generator invocation, and file placement.

File placement strategy:
- ALLIN1.asi → GTA V root (next to GTA5.exe) — despawn fix + file redirection
- Data files (popgroups.ymt, dlclist.xml, gameconfig.xml) → ALLIN1/ folder
  in GTA V root — ALLIN1.asi redirects game reads to these at runtime
- ASI Loader (dinput8.dll / dsound.dll) → GTA V root — auto-downloaded from
  GitHub if not already present
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from allin1 import asi_loader
from allin1.backup import create_backup, restore_backup
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.generators.dlclist import patch_dlclist
from allin1.generators.gameconfig import patch_gameconfig
from allin1.generators.popgroups import create_base_template, generate_popgroups_xml
from allin1.vehicles.database import Vehicle, VehicleDatabase

log = logging.getLogger("allin1.installer")

ASI_FILENAME = "ALLIN1.asi"
ALLIN1_DATA_DIR = "ALLIN1"  # Folder name in game root for loose data files

# Resolve directories relative to this source file (project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ASI_DIST_DIR = _PROJECT_ROOT / "asi" / "dist"
_OUTPUT_DIR = _PROJECT_ROOT / "output"


def _is_enhanced(gta_path: Path) -> bool:
    """Check if this is GTA V Enhanced Edition."""
    return (gta_path / "GTA5_Enhanced.exe").exists()


@dataclass
class InstallResult:
    gta_path: Path
    vehicles_enabled: int
    is_enhanced: bool = False
    files_generated: list[str] = field(default_factory=list)
    files_deployed: list[str] = field(default_factory=list)
    dlc_packs_added: list[str] = field(default_factory=list)
    backup_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)
    asi_deployed: bool = False
    asi_loader_status: str = ""  # "skipped", "deployed", or "failed"
    output_dir: Path | None = None


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
    return db.filter(
        disabled_classes=config.vehicles.disabled_classes,
        disabled_vehicles=config.vehicles.disabled_vehicles,
    )


def install(config: Config, db: VehicleDatabase) -> InstallResult:
    """Run the full installation process."""
    log.info("=== Starting installation ===")
    gta_path = resolve_gta_path(config)
    enhanced = _is_enhanced(gta_path)
    result = InstallResult(gta_path=gta_path, vehicles_enabled=0, is_enhanced=enhanced)

    log.info("GTA V edition: %s", "Enhanced" if enhanced else "Legacy")

    vehicles = get_enabled_vehicles(db, config)
    result.vehicles_enabled = len(vehicles)
    log.info("Vehicles enabled: %d (of %d total)", len(vehicles), len(db))

    # --- Generate all files to output/ directory ---
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result.output_dir = _OUTPUT_DIR

    # --- Generate popgroups.ymt ---
    if config.traffic.enabled:
        log.info("Generating popgroups.ymt (rich_only_supers=%s)...",
                 config.traffic.rich_areas_only_supers)
        base_xml = create_base_template()
        modified_xml = generate_popgroups_xml(
            base_xml,
            vehicles,
            rich_areas_only_supers=config.traffic.rich_areas_only_supers,
        )
        popgroups_out = _OUTPUT_DIR / "popgroups.ymt"
        popgroups_out.write_text(modified_xml, encoding="utf-8")
        result.files_generated.append("popgroups.ymt")
        log.info("Generated popgroups.ymt → %s", popgroups_out)
    else:
        log.info("Traffic spawning disabled — skipping popgroups.ymt")

    # --- Generate dlclist.xml ---
    log.info("Generating dlclist.xml...")
    base_dlclist = '<?xml version="1.0" encoding="UTF-8"?>\n<SMandatoryPacksData>\n  <Paths>\n  </Paths>\n</SMandatoryPacksData>'
    patched_dlclist, added_packs = patch_dlclist(base_dlclist)
    dlclist_out = _OUTPUT_DIR / "dlclist.xml"
    dlclist_out.write_text(patched_dlclist, encoding="utf-8")
    result.files_generated.append("dlclist.xml")
    result.dlc_packs_added = added_packs
    log.info("Generated dlclist.xml with %d DLC pack(s) → %s", len(added_packs), dlclist_out)

    # --- Generate gameconfig.xml ---
    log.info("Generating gameconfig.xml...")
    base_gameconfig = _create_base_gameconfig()
    patched_gc = patch_gameconfig(base_gameconfig)
    gameconfig_out = _OUTPUT_DIR / "gameconfig.xml"
    gameconfig_out.write_text(patched_gc, encoding="utf-8")
    result.files_generated.append("gameconfig.xml")
    log.info("Generated gameconfig.xml → %s", gameconfig_out)

    # --- Deploy data files to ALLIN1/ folder in game root ---
    _deploy_data_files(gta_path, result)

    # --- Deploy ASI plugin (DLC vehicle despawn fix + file redirection) ---
    result.asi_deployed = _deploy_asi(gta_path)

    # --- Ensure ASI Loader is present ---
    result.asi_loader_status = asi_loader.ensure(gta_path, enhanced)

    log.info("=== Installation complete ===")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove ALLIN1 files from the GTA V directory."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    removed: list[Path] = []

    # Remove ASI plugin
    asi_dest = gta_path / ASI_FILENAME
    if asi_dest.exists():
        asi_dest.unlink()
        removed.append(asi_dest)
        log.info("Removed %s from GTA V directory", ASI_FILENAME)

    # Remove ALLIN1/ data folder
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        for f in data_dir.iterdir():
            removed.append(f)
        shutil.rmtree(data_dir)
        log.info("Removed %s/ data folder", ALLIN1_DATA_DIR)

    # Note: We intentionally do NOT remove the ASI loader DLL
    # (dinput8.dll / dsound.dll) because other mods may depend on it.

    # Clean up local output directory
    if _OUTPUT_DIR.exists():
        shutil.rmtree(_OUTPUT_DIR)
        log.info("Removed output/ directory")

    log.info("=== Uninstall complete: %d files removed ===", len(removed))
    return removed


def _deploy_data_files(gta_path: Path, result: InstallResult) -> None:
    """Copy generated files to the ALLIN1/ folder in the game root.

    ALLIN1.asi hooks the game's file system to redirect reads of these
    files at runtime, so they work for both Legacy and Enhanced editions.
    """
    data_dir = gta_path / ALLIN1_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    for filename in result.files_generated:
        src = _OUTPUT_DIR / filename
        if src.exists():
            dest = data_dir / filename
            shutil.copy2(src, dest)
            result.files_deployed.append(str(dest))
            log.info("Deployed %s → %s", filename, dest)

    log.info("Deployed %d file(s) to %s/", len(result.files_deployed), data_dir)


def _deploy_asi(gta_path: Path) -> bool:
    """Copy ALLIN1.asi to the GTA V root directory.

    The ASI disables the DLC vehicle despawn mechanism and redirects
    game file reads to the ALLIN1/ data folder.
    It's placed next to GTA5.exe so the ASI loader picks it up.

    Returns True if deployed successfully, False if the source binary is missing.
    """
    src = _ASI_DIST_DIR / ASI_FILENAME
    if not src.exists():
        log.warning(
            "%s not found at %s — DLC despawn fix will NOT be active. "
            "Run the GitHub Actions build or download from Releases.",
            ASI_FILENAME, _ASI_DIST_DIR,
        )
        return False

    dest = gta_path / ASI_FILENAME
    shutil.copy2(src, dest)
    log.info("Deployed %s to %s", ASI_FILENAME, dest)
    return True


def _create_base_gameconfig() -> str:
    """Create a minimal gameconfig.xml with default pool sizes."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<CGameConfig>
  <pools>
    <Item>
      <Name>CVehicle</Name>
      <Size value="128"/>
    </Item>
    <Item>
      <Name>CVehicleModelInfo</Name>
      <Size value="200"/>
    </Item>
    <Item>
      <Name>CHandlingDataMgr</Name>
      <Size value="200"/>
    </Item>
  </pools>
</CGameConfig>"""
