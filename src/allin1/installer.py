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
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from allin1 import asi_loader
from allin1.config import Config
from allin1.detector import detect_gta_path, validate_gta_path
from allin1.vehicles.database import VehicleDatabase
from allin1.versioning import VERSION_FILE, write_installed_version

log = logging.getLogger("allin1.installer")

DLL_FILENAME = "ALLIN1.dll"
LEMONUI_FILENAME = "LemonUI.SHVDN3.dll"
SCRIPTS_DIR = "scripts"
ALLIN1_DATA_DIR = "ALLIN1"  # Legacy data folder — cleaned up on install

# Files from previous ALLIN1 versions to clean up
LEGACY_FILES = ("ALLIN1.asi", "ALLIN1.dll", "ALLIN1-Launcher.exe")

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

    # --- Detect optional RPF loader; never install third-party executable code ---
    result.openrpf_found = _check_openrpf(gta_path, enhanced)

    # Remove ALLIN1's obsolete custom DLC registration. A stale or malformed
    # boot-time pack can crash GTA before the script client starts.
    _remove_legacy_preview_pack(gta_path)
    _unpatch_dlclist_rpf(gta_path)

    if config.general.enable_rpf_previews:
        if not result.openrpf_found:
            result.warnings.append(
                "RPF previews requested but no compatible OpenRPF/OpenIV loader was detected; "
                "safe GBAY placeholders will be used."
            )
        else:
            try:
                result.rpf_previews_deployed = _deploy_preview_dlc(gta_path, result)
            except Exception as exc:
                log.error("Preview texture injection failed: %s", exc, exc_info=True)
                result.warnings.append(f"Preview texture injection failed: {exc}")
    else:
        log.info("RPF previews disabled; using crash-safe GBAY placeholders")

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
    for fname in (DLL_FILENAME, LEMONUI_FILENAME, "ALLIN1.toml",
                   "ALLIN1.log", "ALLIN1_spawner.log", "ALLIN1_gbay.log",
                   "ALLIN1_client.log", "ALLIN1_client.log.1",
                   "ALLIN1_client.log.2", "ALLIN1_client.log.3",
                   "ALLIN1_garage.json", "ALLIN1_garages.json",
                   "ALLIN1_garages.json.bak", "ALLIN1_gbay_preferences.json",
                   "ALLIN1_gbay_preferences.json.bak", "ALLIN1_session.lock",
                   "ALLIN1_garage.quarantine.json", VERSION_FILE, "ALLIN1.ini"):
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

    # Remove legacy loose preview images (from SHV-era installs)
    scripts_dir_previews = scripts_dir / "previews"
    if scripts_dir_previews.exists():
        shutil.rmtree(scripts_dir_previews)
        removed.append(scripts_dir_previews)
        log.info("Removed legacy previews/ folder")
    logo_file = scripts_dir / "PHAT.png"
    if logo_file.exists():
        logo_file.unlink()
        removed.append(logo_file)
        log.info("Removed PHAT.png")

    # Remove preview DLC pack (legacy — DLC approach replaced by script_txds.rpf)
    removed.extend(_remove_legacy_preview_pack(gta_path))

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


def _check_openrpf(gta_path: Path, enhanced: bool) -> bool:
    """Detect a user-installed RPF loader without downloading executable code."""
    if not enhanced:
        asi_path = gta_path / "OpenIV.asi"
        found = asi_path.exists() and asi_path.stat().st_size > 0
        if found and not (gta_path / "dinput8.dll").exists():
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
    if asi_path.stat().st_size == 0:
        log.warning("OpenRPF.asi is empty or corrupt")
        return False
    asi_loaders = ("dsound.dll", "xinput1_4.dll", "dinput8.dll")
    if not any((gta_path / name).exists() for name in asi_loaders):
        log.warning("OpenRPF.asi exists but no compatible ASI loader was detected")
        return False
    log.info("User-installed OpenRPF.asi and ASI loader detected")
    return True


def _deploy_preview_dlc(gta_path: Path, result: InstallResult) -> bool:
    """Build YTDs and inject them into the standard script texture archive."""
    from allin1.generators import ytd_builder
    from allin1.preview_assets import merge_previews

    previews_src = _SCRIPT_DIST_DIR / "previews"
    logo_src = _SCRIPT_DIST_DIR / "PHAT.png"

    if not previews_src.is_dir():
        log.warning("No previews/ directory found — skipping preview build")
        result.warnings.append("Preview images not found; vehicle thumbnails "
                               "will show colored placeholders.")
        return False

    ytdtoolio = _TOOLS_DIR / "YTDToolio.exe"
    if not ytdtoolio.exists():
        log.warning("YTDToolio.exe not found — skipping preview build. "
                     "Run runtools.ps1 first.")
        result.warnings.append("YTDToolio.exe missing; run runtools.ps1 first.")
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

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ytd_out = tmp_path / "ytd"
        preview_inputs = tmp_path / "preview_inputs"

        # The in-game F10 tool writes to scripts/previews. On a later install,
        # those captures override the bundled images automatically.
        merged = merge_previews(
            [previews_src, gta_path / SCRIPTS_DIR / "previews"],
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

        # Step 1: Build .ytd files from PNGs
        ytd_files = ytd_builder.build_ytd_files(
            preview_inputs,
            logo_src if logo_src.exists() else None,
            ytd_out, _TOOLS_DIR, models,
        )

        if not ytd_files:
            log.warning("No .ytd files were built")
            result.warnings.append("Failed to build preview textures.")
            return False

        # Step 1b: Convert .ytd files to Enhanced (gen9) format if needed
        if result.is_enhanced:
            log.info("Enhanced edition detected — converting .ytd files to gen9 format...")
            proc = subprocess.run(
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

        # Injecting into the game's existing script texture archive avoids a
        # custom boot-time DLC registration solely for UI artwork.
        log.info("Injecting %d preview dictionaries into script_txds.rpf...", len(ytd_files))
        mods_rpf = gta_path / "mods" / "update" / "update.rpf"
        backup_rpf = mods_rpf.with_name("update.rpf.allin1-previews.bak")
        existed_before = mods_rpf.exists()
        if existed_before:
            backup_rpf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mods_rpf, backup_rpf)
            log.info("Backed up mods update.rpf before preview injection")
        try:
            proc = subprocess.run(
                [str(rpf_patcher), "inject-ytd", str(gta_path), str(ytd_out)],
                capture_output=True, text=True, timeout=300,
            )
        except Exception:
            _restore_preview_archive(mods_rpf, backup_rpf, existed_before)
            raise
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode != 0:
            _restore_preview_archive(mods_rpf, backup_rpf, existed_before)
            error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
            raise RuntimeError(f"RpfPatcher inject-ytd failed: {error_msg}")
        if not mods_rpf.exists() or mods_rpf.stat().st_size == 0:
            _restore_preview_archive(mods_rpf, backup_rpf, existed_before)
            raise RuntimeError("RpfPatcher inject-ytd did not produce a valid mods/update/update.rpf")
        log.info("Preview texture injection completed")
        return True


def _restore_preview_archive(mods_rpf: Path, backup_rpf: Path, existed_before: bool) -> None:
    """Restore the exact pre-injection archive state after a tool failure."""
    if existed_before and backup_rpf.exists():
        shutil.copy2(backup_rpf, mods_rpf)
    elif not existed_before:
        mods_rpf.unlink(missing_ok=True)


def _remove_legacy_preview_pack(gta_path: Path) -> list[Path]:
    """Remove only obsolete ALLIN1-owned preview DLC directories."""
    removed: list[Path] = []
    for base in ("mods/update", "update"):
        dlc_dir = gta_path / base / "x64" / "dlcpacks" / "allin1_previews"
        if dlc_dir.exists():
            shutil.rmtree(dlc_dir)
            removed.append(dlc_dir)
            log.info("Removed obsolete preview DLC pack at %s", dlc_dir)
    return removed


def _patch_dlclist_rpf(gta_path: Path, result: InstallResult) -> None:
    """Add allin1_previews to dlclist.xml inside mods/update/update.rpf.

    This tells the game to load our DLC pack at boot so the texture
    dictionaries inside it are indexed and available for streaming.
    """
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.warning("RpfPatcher.exe not found — skipping dlclist patch")
        result.warnings.append("RpfPatcher.exe missing; preview textures "
                               "may not load without dlclist.xml entry.")
        return

    try:
        proc = subprocess.run(
            [str(rpf_patcher), "patch", str(gta_path)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines():
                log.info("RpfPatcher: %s", line)
        if proc.returncode == 0:
            log.info("Patched dlclist.xml with allin1_previews entry")
        else:
            error_msg = proc.stderr.strip() if proc.stderr else f"exit code {proc.returncode}"
            log.error("Failed to patch dlclist.xml: %s", error_msg)
            result.warnings.append(f"Failed to patch dlclist.xml: {error_msg}")
    except Exception as exc:
        log.error("Could not patch dlclist.xml: %s", exc)
        result.warnings.append(f"Could not patch dlclist.xml: {exc}")


def _unpatch_dlclist_rpf(gta_path: Path) -> None:
    """Remove ALLIN1 entry from dlclist.xml inside update.rpf (legacy cleanup)."""
    rpf_patcher = _TOOLS_DIR / "RpfPatcher" / "RpfPatcher.exe"
    if not rpf_patcher.exists():
        log.debug("RpfPatcher.exe not found — skipping dlclist unpatch")
        return

    try:
        proc = subprocess.run(
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
        proc = subprocess.run(
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
