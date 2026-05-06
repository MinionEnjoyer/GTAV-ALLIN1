"""Main installer orchestrator.

Coordinates the install/uninstall flow: config loading, GTA V detection,
and ALLIN1 script deployment.

File placement:
- <GTA V root>/scripts/ALLIN1.dll — SHVDN script loaded at runtime.
  Spawns 444 GTA Online DLC vehicles into Story Mode traffic.
- <GTA V root>/scripts/ALLIN1.toml — Config deployed from project config.toml.

Prerequisites (installed separately by the user):
- ScriptHookV (dinput8.dll + ScriptHookV.dll)
- ScriptHookVDotNet Enhanced (ScriptHookVDotNet.asi + ScriptHookVDotNet3.dll)
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from allin1 import asi_loader
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.vehicles.database import VehicleDatabase

log = logging.getLogger("allin1.installer")

DLL_FILENAME = "ALLIN1.dll"
SCRIPTS_DIR = "scripts"
ALLIN1_DATA_DIR = "ALLIN1"  # Legacy data folder — cleaned up on install

# Files from previous ALLIN1 versions to clean up
LEGACY_FILES = ("ALLIN1.asi", "ALLIN1.dll", "ALLIN1-Launcher.exe")

# Resolve directories relative to this source file (project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT_DIST_DIR = _PROJECT_ROOT / "script" / "dist"


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


def install(config: Config, db: VehicleDatabase) -> InstallResult:
    """Run the full installation process."""
    log.info("=== Starting installation ===")
    gta_path = resolve_gta_path(config)
    enhanced = _is_enhanced(gta_path)
    result = InstallResult(gta_path=gta_path, is_enhanced=enhanced)

    log.info("GTA V edition: %s", "Enhanced" if enhanced else "Legacy")

    # --- Clean up files from previous ALLIN1 versions ---
    _clean_legacy_files(gta_path, result)

    # --- Deploy ALLIN1.dll script ---
    result.dll_deployed = _deploy_script(gta_path)

    # --- Check for ScriptHookV ---
    result.scripthookv_found = _check_scripthookv(gta_path)

    # --- Check for ScriptHookVDotNet ---
    result.shvdn_found = _check_shvdn(gta_path)

    # --- Write -nobattleye to commandline.txt (belt-and-suspenders) ---
    result.battleye_status = asi_loader.ensure_nobattleye(gta_path, enhanced)

    log.info("=== Installation complete ===")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove ALLIN1 files from the GTA V directory."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    removed: list[Path] = []

    # Remove script DLL, config, and log from scripts/
    scripts_dir = gta_path / SCRIPTS_DIR
    for fname in (DLL_FILENAME, "ALLIN1.toml", "ALLIN1.log", "ALLIN1.ini"):
        fpath = scripts_dir / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fpath)
            log.info("Removed %s from scripts/", fname)

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
    shutil.copy2(src, dest)
    log.info("Deployed %s → %s", DLL_FILENAME, dest)

    # Deploy config.toml as ALLIN1.toml so the C# script can read it
    toml_dest = scripts_dir / "ALLIN1.toml"
    toml_src = _PROJECT_ROOT / "config.toml"
    if not toml_src.exists():
        toml_src = _PROJECT_ROOT / "config.example.toml"
    if toml_src.exists():
        shutil.copy2(toml_src, toml_dest)
        log.info("Deployed config %s -> %s", toml_src.name, toml_dest)

    # Clean up legacy INI from previous versions
    legacy_ini = scripts_dir / "ALLIN1.ini"
    if legacy_ini.exists():
        legacy_ini.unlink()
        log.info("Removed legacy ALLIN1.ini")

    return True


def _check_scripthookv(gta_path: Path) -> bool:
    """Check if ScriptHookV is installed in the game directory."""
    return (gta_path / "ScriptHookV.dll").exists()


def _check_shvdn(gta_path: Path) -> bool:
    """Check if ScriptHookVDotNet is installed in the game directory."""
    return (gta_path / "ScriptHookVDotNet.asi").exists()
