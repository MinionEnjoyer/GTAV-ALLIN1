"""Main installer orchestrator.

Coordinates the full install/uninstall flow: config loading, GTA V detection,
backup creation, generator invocation, and file placement.

File placement strategy:
- ALLIN1.dll → GTA V root — plugin DLL (despawn fix + file redirection)
- ALLIN1-Launcher.exe → GTA V root — injector that loads ALLIN1.dll into
  the running game process, bypassing BattlEye's proxy-DLL block
- Data files (popgroups.ymt, dlclist.xml, gameconfig.xml) → ALLIN1/ folder
  in GTA V root — ALLIN1.dll redirects game reads to these at runtime
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

DLL_FILENAME = "ALLIN1.dll"
LAUNCHER_FILENAME = "ALLIN1-Launcher.exe"
ALLIN1_DATA_DIR = "ALLIN1"  # Folder name in game root for loose data files

# Proxy DLLs that BattlEye blocks.  Remove any leftover copies from previous
# mod tool installations (Ultimate ASI Loader, ScriptHookV, etc.).
PROXY_DLLS = ("dsound.dll", "dinput8.dll", "d3d11.dll", "version.dll")
LEGACY_FILES = ("ALLIN1.asi",)  # Old filename before rename to .dll

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
    plugin_deployed: bool = False    # ALLIN1.dll
    launcher_deployed: bool = False  # ALLIN1-Launcher.exe
    battleye_status: str = ""        # "set", "already_set", or "failed"
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

    # --- Remove leftover proxy DLLs that trigger BattlEye ---
    _clean_proxy_dlls(gta_path, result)

    # --- Deploy plugin DLL + launcher exe ---
    result.plugin_deployed, result.launcher_deployed = _deploy_plugin(gta_path)

    # --- Write -nobattleye to commandline.txt (belt-and-suspenders) ---
    result.battleye_status = asi_loader.ensure_nobattleye(gta_path, enhanced)

    log.info("=== Installation complete ===")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove ALLIN1 files from the GTA V directory."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    removed: list[Path] = []

    # Remove plugin DLL, launcher exe, legacy .asi, and proxy DLLs
    for fname in (DLL_FILENAME, LAUNCHER_FILENAME, *LEGACY_FILES):
        fpath = gta_path / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fpath)
            log.info("Removed %s from GTA V directory", fname)

    for dll in PROXY_DLLS:
        p = gta_path / dll
        if p.exists():
            p.unlink()
            removed.append(p)
            log.info("Removed leftover proxy DLL: %s", dll)

    # Remove ALLIN1/ data folder
    data_dir = gta_path / ALLIN1_DATA_DIR
    if data_dir.exists():
        for f in data_dir.iterdir():
            removed.append(f)
        shutil.rmtree(data_dir)
        log.info("Removed %s/ data folder", ALLIN1_DATA_DIR)

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


def _clean_proxy_dlls(gta_path: Path, result: InstallResult) -> None:
    """Remove leftover proxy DLLs that BattlEye blocks at startup.

    Previous mod tool installations (Ultimate ASI Loader, ScriptHookV, etc.)
    may have placed proxy DLLs like dsound.dll or dinput8.dll in the game
    root.  BattlEye blocks these before the game starts.
    """
    for dll in (*PROXY_DLLS, *LEGACY_FILES):
        p = gta_path / dll
        if p.exists():
            try:
                p.unlink()
                result.warnings.append(
                    f"Removed leftover {dll} (no longer needed)."
                )
                log.info("Removed leftover file: %s", dll)
            except OSError as exc:
                result.warnings.append(
                    f"Could not remove {dll}: {exc}. Delete it manually."
                )
                log.warning("Failed to remove %s: %s", dll, exc)


def _deploy_plugin(gta_path: Path) -> tuple[bool, bool]:
    """Copy ALLIN1.dll and ALLIN1-Launcher.exe to the GTA V root.

    ALLIN1.dll is the plugin that hooks the game's file system and patches
    the despawn logic.  ALLIN1-Launcher.exe is the injector that loads the
    DLL into the running game process (bypassing BattlEye).

    Returns (plugin_deployed, launcher_deployed).
    """
    plugin_ok = False
    launcher_ok = False

    for filename, label in ((DLL_FILENAME, "plugin"), (LAUNCHER_FILENAME, "launcher")):
        src = _ASI_DIST_DIR / filename
        if not src.exists():
            log.warning(
                "%s not found at %s — run the GitHub Actions build or "
                "download from Releases.",
                filename, _ASI_DIST_DIR,
            )
            continue
        dest = gta_path / filename
        shutil.copy2(src, dest)
        log.info("Deployed %s → %s", filename, dest)
        if label == "plugin":
            plugin_ok = True
        else:
            launcher_ok = True

    return plugin_ok, launcher_ok


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
