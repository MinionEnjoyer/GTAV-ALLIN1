"""Main installer orchestrator.

Coordinates the full install/uninstall flow: config loading, GTA V detection,
backup creation, generator invocation, and file placement.

File placement strategy:
- ALLIN1.asi → GTA V root (next to GTA5.exe) — works for both editions
- popgroups.ymt, dlclist.xml, gameconfig.xml:
  - Enhanced Edition → onigiri/ folder (loose file replacement via onigiri.asi)
  - Legacy Edition → output/ folder locally, user imports via OpenIV/CodeWalker
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
    # Start with a minimal gameconfig template
    base_gameconfig = _create_base_gameconfig()
    patched_gc = patch_gameconfig(base_gameconfig)
    gameconfig_out = _OUTPUT_DIR / "gameconfig.xml"
    gameconfig_out.write_text(patched_gc, encoding="utf-8")
    result.files_generated.append("gameconfig.xml")
    log.info("Generated gameconfig.xml → %s", gameconfig_out)

    # --- Deploy files based on edition ---
    if enhanced:
        _deploy_enhanced(gta_path, result)
    else:
        log.info("Legacy edition — generated files saved to output/ folder")
        log.info("Use OpenIV or CodeWalker to import them into update.rpf")

    # --- Deploy ASI plugin (DLC vehicle despawn fix) ---
    result.asi_deployed = _deploy_asi(gta_path)

    log.info("=== Installation complete ===")
    return result


def uninstall(config: Config) -> list[Path]:
    """Restore backed-up files and remove ASI plugin."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    enhanced = _is_enhanced(gta_path)
    restored: list[Path] = []

    # Remove ASI plugin
    asi_dest = gta_path / ASI_FILENAME
    if asi_dest.exists():
        asi_dest.unlink()
        restored.append(asi_dest)
        log.info("Removed %s from GTA V directory", ASI_FILENAME)

    # Remove onigiri files (Enhanced Edition)
    if enhanced:
        onigiri_files = [
            gta_path / "onigiri" / "platform" / "levels" / "gta5" / "popgroups.ymt",
            gta_path / "onigiri" / "common" / "data" / "dlclist.xml",
            gta_path / "onigiri" / "common" / "data" / "gameconfig.xml",
        ]
        for f in onigiri_files:
            if f.exists():
                f.unlink()
                restored.append(f)
                log.info("Removed %s", f)

    # Clean up output directory
    if _OUTPUT_DIR.exists():
        shutil.rmtree(_OUTPUT_DIR)
        log.info("Removed output/ directory")

    log.info("=== Uninstall complete: %d files removed ===", len(restored))
    return restored


def _deploy_enhanced(gta_path: Path, result: InstallResult) -> None:
    """Deploy generated files to the onigiri folder for Enhanced Edition."""
    log.info("Enhanced Edition — deploying to onigiri/ folder")

    # popgroups.ymt → onigiri/platform/levels/gta5/
    popgroups_src = _OUTPUT_DIR / "popgroups.ymt"
    if popgroups_src.exists():
        dest_dir = gta_path / "onigiri" / "platform" / "levels" / "gta5"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "popgroups.ymt"
        shutil.copy2(popgroups_src, dest)
        result.files_deployed.append(str(dest))
        log.info("Deployed popgroups.ymt → %s", dest)

    # dlclist.xml → onigiri/common/data/
    dlclist_src = _OUTPUT_DIR / "dlclist.xml"
    if dlclist_src.exists():
        dest_dir = gta_path / "onigiri" / "common" / "data"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "dlclist.xml"
        shutil.copy2(dlclist_src, dest)
        result.files_deployed.append(str(dest))
        log.info("Deployed dlclist.xml → %s", dest)

    # gameconfig.xml → onigiri/common/data/
    gameconfig_src = _OUTPUT_DIR / "gameconfig.xml"
    if gameconfig_src.exists():
        dest_dir = gta_path / "onigiri" / "common" / "data"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "gameconfig.xml"
        shutil.copy2(gameconfig_src, dest)
        result.files_deployed.append(str(dest))
        log.info("Deployed gameconfig.xml → %s", dest)


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
