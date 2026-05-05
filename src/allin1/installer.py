"""Main installer orchestrator.

Coordinates the install/uninstall flow: config loading, GTA V detection,
and ASI plugin deployment.

File placement:
- ALLIN1.asi → GTA V root — ASI plugin loaded by ScriptHookV at runtime.
  The plugin discovers DLC vehicles via native API and spawns them in traffic.

Prerequisite: ScriptHookV must be installed separately by the user.
It handles BattlEye bypass and ASI loading.
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

ASI_FILENAME = "ALLIN1.asi"
ALLIN1_DATA_DIR = "ALLIN1"  # Legacy data folder — cleaned up on install

# Files from previous ALLIN1 versions to clean up
LEGACY_FILES = ("ALLIN1.dll", "ALLIN1-Launcher.exe")

# Proxy DLLs from other mod tools that can conflict
PROXY_DLLS = ("dsound.dll", "dinput8.dll")

# Resolve directories relative to this source file (project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ASI_DIST_DIR = _PROJECT_ROOT / "asi" / "dist"


def _is_enhanced(gta_path: Path) -> bool:
    """Check if this is GTA V Enhanced Edition."""
    return (gta_path / "GTA5_Enhanced.exe").exists()


@dataclass
class InstallResult:
    gta_path: Path
    is_enhanced: bool = False
    asi_deployed: bool = False
    scripthookv_found: bool = False
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

    # --- Deploy ASI plugin ---
    result.asi_deployed = _deploy_asi(gta_path)

    # --- Check for ScriptHookV ---
    result.scripthookv_found = _check_scripthookv(gta_path)

    # --- Write -nobattleye to commandline.txt (belt-and-suspenders) ---
    result.battleye_status = asi_loader.ensure_nobattleye(gta_path, enhanced)

    log.info("=== Installation complete ===")
    return result


def uninstall(config: Config) -> list[Path]:
    """Remove ALLIN1 files from the GTA V directory."""
    log.info("=== Starting uninstall ===")
    gta_path = resolve_gta_path(config)
    removed: list[Path] = []

    # Remove ASI plugin and legacy files
    for fname in (ASI_FILENAME, *LEGACY_FILES):
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
    # Remove old injector/DLL files
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

    # Remove legacy ALLIN1/ data folder (no longer needed — native API approach)
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


def _deploy_asi(gta_path: Path) -> bool:
    """Copy ALLIN1.asi to the GTA V root.  Returns True if deployed."""
    src = _ASI_DIST_DIR / ASI_FILENAME
    if not src.exists():
        log.warning(
            "%s not found at %s — run the GitHub Actions build or "
            "download from Releases.",
            ASI_FILENAME, _ASI_DIST_DIR,
        )
        return False
    dest = gta_path / ASI_FILENAME
    shutil.copy2(src, dest)
    log.info("Deployed %s → %s", ASI_FILENAME, dest)
    return True


def _check_scripthookv(gta_path: Path) -> bool:
    """Check if ScriptHookV is installed in the game directory."""
    shv_dll = gta_path / "ScriptHookV.dll"
    return shv_dll.exists()
