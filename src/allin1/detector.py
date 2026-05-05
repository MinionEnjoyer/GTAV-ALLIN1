"""GTA V installation path detection.

Searches across all drives, Steam libraries, Epic Games manifests,
Rockstar Games Launcher data, and the Windows Registry to find GTA V.

When a path is detected, it is cached to ``.gta_path`` in the project
root so subsequent runs (including uninstall) can skip detection.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import string
from pathlib import Path

log = logging.getLogger("allin1.detector")

# Cache file written next to config.toml / pyproject.toml
_CACHE_FILE = ".gta_path"


def _project_root() -> Path:
    """Return the project root (three levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent


def load_cached_path() -> Path | None:
    """Read a previously-cached GTA V path from ``.gta_path``."""
    cache = _project_root() / _CACHE_FILE
    if not cache.exists():
        return None
    try:
        raw = cache.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        p = Path(raw)
        if _validate_gta_path(p):
            log.info("Loaded cached GTA V path: %s", p)
            return p
        log.warning("Cached path no longer valid: %s", raw)
        return None
    except OSError as exc:
        log.debug("Could not read cache file: %s", exc)
        return None


def save_cached_path(path: Path) -> None:
    """Write a detected GTA V path to ``.gta_path`` for reuse."""
    cache = _project_root() / _CACHE_FILE
    try:
        cache.write_text(str(path), encoding="utf-8")
        log.debug("Cached GTA V path to %s", cache)
    except OSError as exc:
        log.warning("Could not write cache file: %s", exc)


def detect_gta_path() -> Path | None:
    """Attempt to auto-detect the GTA V installation directory.

    Checks the ``.gta_path`` cache first, then runs platform-specific
    detection.  On success the result is cached for future runs.
    """
    # Try cache first
    cached = load_cached_path()
    if cached is not None:
        return cached

    system = platform.system()
    log.info("Starting GTA V auto-detection on %s", system)

    result: Path | None = None
    if system == "Windows":
        result = _detect_windows()
    elif system == "Linux":
        result = _detect_linux()
    else:
        log.info("macOS detected — no native GTA V, user must specify path manually")

    if result:
        log.info("GTA V found: %s", result)
        save_cached_path(result)
    else:
        log.warning("GTA V auto-detection failed — no valid install found")

    return result


def _detect_windows() -> Path | None:
    candidates: list[Path] = []

    # 1. Windows Registry (most reliable -- set by Rockstar's installer)
    log.debug("Checking Windows Registry...")
    reg_path = _check_registry()
    if reg_path:
        log.debug("Registry hit: %s", reg_path)
        candidates.append(reg_path)
    else:
        log.debug("Registry: no GTA V keys found")

    # 2. Steam libraries (parses libraryfolders.vdf from all known locations)
    log.debug("Scanning Steam library folders...")
    steam_libs = _find_steam_libraries_windows()
    log.debug("Found %d Steam library folder(s)", len(steam_libs))
    for lib in steam_libs:
        candidates.append(lib / "steamapps" / "common" / "Grand Theft Auto V")

    # 3. Epic Games (parse manifest files for actual install location)
    log.debug("Checking Epic Games manifests...")
    epic_paths = _find_epic_install_windows()
    if epic_paths:
        log.debug("Epic Games candidates: %d", len(epic_paths))
    candidates.extend(epic_paths)

    # 4. Rockstar Games Launcher
    log.debug("Checking Rockstar Games Launcher...")
    rgl_paths = _find_rockstar_launcher_windows()
    if rgl_paths:
        log.debug("Rockstar Launcher candidates: %d", len(rgl_paths))
    candidates.extend(rgl_paths)

    # 5. Common hardcoded paths on every available drive
    drives = _get_windows_drives()
    log.debug("Available drives: %s", [str(d) for d in drives])
    for drive in drives:
        candidates.extend([
            drive / "Program Files" / "Rockstar Games" / "Grand Theft Auto V",
            drive / "Program Files (x86)" / "Rockstar Games" / "Grand Theft Auto V",
            drive / "Games" / "Grand Theft Auto V",
            drive / "Games" / "GTA V",
            drive / "Games" / "GTAV",
            drive / "Games" / "Rockstar Games" / "Grand Theft Auto V",
            drive / "SteamLibrary" / "steamapps" / "common" / "Grand Theft Auto V",
            drive / "Steam" / "steamapps" / "common" / "Grand Theft Auto V",
            drive / "Epic Games" / "GTAV",
            drive / "Epic Games" / "Grand Theft Auto V",
            drive / "Rockstar Games" / "Grand Theft Auto V",
            drive / "Grand Theft Auto V",
            drive / "GTAV",
        ])

    # Deduplicate while preserving priority order
    seen: set[str] = set()
    unique: list[Path] = []
    for p in candidates:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    log.debug("Checking %d unique candidate paths...", len(unique))
    for path in unique:
        if _validate_gta_path(path):
            log.debug("Valid GTA V install: %s", path)
            return path
        log.debug("Not valid: %s", path)

    # 6. Last resort: scan all drives for steamapps directories and GTA5.exe
    log.info("Standard detection failed — starting deep scan of all drives...")
    found = _deep_scan_windows(drives)
    if found:
        log.info("Deep scan found GTA V: %s", found)
        return found

    return None


def _detect_linux() -> Path | None:
    home = Path.home()
    candidates = [
        home / ".steam" / "steam" / "steamapps" / "common" / "Grand Theft Auto V",
        home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Grand Theft Auto V",
    ]

    # Parse Steam libraryfolders.vdf on Linux too
    vdf_paths = [
        home / ".steam" / "steam" / "steamapps" / "libraryfolders.vdf",
        home / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf",
        home / ".steam" / "root" / "steamapps" / "libraryfolders.vdf",
    ]
    for vdf in vdf_paths:
        for lib in _parse_steam_vdf(vdf):
            candidates.append(lib / "steamapps" / "common" / "Grand Theft Auto V")

    log.debug("Linux: checking %d candidate paths", len(candidates))
    for path in candidates:
        if _validate_gta_path(path):
            log.debug("Valid GTA V install: %s", path)
            return path
    return None


def _get_windows_drives() -> list[Path]:
    """Get all available drive letters on Windows."""
    drives: list[Path] = []
    # Check all possible drive letters A-Z
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if drive.exists():
            drives.append(drive)
    return drives


def _find_steam_libraries_windows() -> list[Path]:
    """Find all Steam library folders by parsing libraryfolders.vdf.

    Checks multiple possible Steam install locations including
    non-default drives.
    """
    vdf_candidates: list[Path] = []

    # Default Steam locations
    vdf_candidates.append(Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"))
    vdf_candidates.append(Path(r"C:\Program Files\Steam\steamapps\libraryfolders.vdf"))

    # Check registry for Steam install path
    try:
        import winreg
        for subkey in [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                    steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                    vdf_candidates.append(Path(steam_path) / "steamapps" / "libraryfolders.vdf")
            except (FileNotFoundError, OSError):
                continue
        # Also check HKCU
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
                vdf_candidates.append(Path(steam_path) / "steamapps" / "libraryfolders.vdf")
        except (FileNotFoundError, OSError):
            pass
    except ImportError:
        pass

    # Also scan all drives for Steam installations
    for drive in _get_windows_drives():
        vdf_candidates.extend([
            drive / "Steam" / "steamapps" / "libraryfolders.vdf",
            drive / "SteamLibrary" / "steamapps" / "libraryfolders.vdf",
            drive / "Program Files" / "Steam" / "steamapps" / "libraryfolders.vdf",
            drive / "Program Files (x86)" / "Steam" / "steamapps" / "libraryfolders.vdf",
        ])

    libraries: list[Path] = []
    seen: set[str] = set()
    for vdf in vdf_candidates:
        for lib in _parse_steam_vdf(vdf):
            key = str(lib).lower()
            if key not in seen:
                seen.add(key)
                libraries.append(lib)

    return libraries


def _parse_steam_vdf(vdf_path: Path) -> list[Path]:
    """Parse a Steam libraryfolders.vdf file for library paths."""
    if not vdf_path.exists():
        return []
    try:
        text = vdf_path.read_text(encoding="utf-8")
        paths: list[Path] = []
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            raw = match.group(1).replace("\\\\", "\\")
            paths.append(Path(raw))
        return paths
    except OSError:
        return []


def _find_epic_install_windows() -> list[Path]:
    """Find GTA V installed via Epic Games by reading manifest files."""
    paths: list[Path] = []
    manifests_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"

    if not manifests_dir.is_dir():
        return paths

    try:
        for manifest in manifests_dir.glob("*.item"):
            try:
                text = manifest.read_text(encoding="utf-8")
                # Look for GTA V app name in the manifest
                if "GTA" not in text.upper() and "9d2d0eb64d5c44529cece33fe2a46482" not in text:
                    continue
                # Extract InstallLocation
                match = re.search(r'"InstallLocation"\s*:\s*"([^"]+)"', text)
                if match:
                    install_path = Path(match.group(1).replace("\\\\", "\\"))
                    paths.append(install_path)
            except OSError:
                continue
    except OSError:
        pass

    # Fallback: common Epic install paths on all drives
    for drive in _get_windows_drives():
        paths.extend([
            drive / "Epic Games" / "GTAV",
            drive / "Epic Games" / "Grand Theft Auto V",
        ])

    return paths


def _find_rockstar_launcher_windows() -> list[Path]:
    """Find GTA V installed via Rockstar Games Launcher."""
    paths: list[Path] = []

    # Rockstar Launcher stores titles info in a settings file
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        settings_dir = Path(local_appdata) / "Rockstar Games" / "Launcher"
        settings_file = settings_dir / "settings_user.dat"
        if settings_file.exists():
            try:
                # This is a binary-ish file but install paths are readable strings
                data = settings_file.read_bytes()
                text = data.decode("utf-8", errors="ignore")
                # Look for paths containing Grand Theft Auto V
                for match in re.finditer(r'([A-Z]:\\[^\x00]+?Grand Theft Auto V)', text):
                    paths.append(Path(match.group(1)))
            except OSError:
                pass

    # Also check the Rockstar Launcher's own install registry
    try:
        import winreg
        rgl_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\GTAV", "InstallFolderEpic"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V", "InstallFolderSteam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games\Grand Theft Auto V", "InstallFolderSteam"),
        ]
        for hive, subkey, value_name in rgl_keys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        paths.append(Path(value))
            except (FileNotFoundError, OSError):
                continue
    except ImportError:
        pass

    return paths


def _check_registry() -> Path | None:
    """Check Windows Registry for GTA V install path."""
    try:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V", "InstallFolderSteam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\GTAV", "InstallFolderEpic"),
            # Uninstall entries (fallback)
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{5EFC6C07-6B87-43FC-9524-F9E967241741}", "InstallLocation"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{5EFC6C07-6B87-43FC-9524-F9E967241741}", "InstallLocation"),
        ]
        for hive, subkey, value_name in keys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        p = Path(value)
                        if _validate_gta_path(p):
                            return p
            except (FileNotFoundError, OSError):
                continue
    except ImportError:
        pass
    return None


def _deep_scan_windows(drives: list[Path]) -> Path | None:
    """Brute-force scan drives for GTA V installation.

    Walks up to 3 levels deep on each drive looking for steamapps folders
    and GTA5.exe. This catches non-standard install locations that the
    VDF/registry methods miss.
    """
    gta_folder_names = {"grand theft auto v", "gtav", "gta v", "gta5"}
    exe_names = {"gta5.exe", "gta5_enhanced.exe", "playgtav.exe"}

    for drive in drives:
        # Strategy 1: Find any steamapps/common/Grand Theft Auto V on this drive
        # by scanning top-level and second-level directories for steamapps
        try:
            for depth1 in drive.iterdir():
                if not depth1.is_dir():
                    continue
                # Check if this IS a steamapps dir
                gta_via_steam = depth1 / "steamapps" / "common" / "Grand Theft Auto V"
                if _validate_gta_path(gta_via_steam):
                    return gta_via_steam
                # Check one more level down
                if depth1.name.lower() == "steamapps":
                    gta_path = depth1 / "common" / "Grand Theft Auto V"
                    if _validate_gta_path(gta_path):
                        return gta_path
                try:
                    for depth2 in depth1.iterdir():
                        if not depth2.is_dir():
                            continue
                        gta_via_steam2 = depth2 / "steamapps" / "common" / "Grand Theft Auto V"
                        if _validate_gta_path(gta_via_steam2):
                            return gta_via_steam2
                        if depth2.name.lower() == "steamapps":
                            gta_path2 = depth2 / "common" / "Grand Theft Auto V"
                            if _validate_gta_path(gta_path2):
                                return gta_path2
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue

        # Strategy 2: Look for GTA V folder directly at top 2 levels
        try:
            for depth1 in drive.iterdir():
                if not depth1.is_dir():
                    continue
                if depth1.name.lower() in gta_folder_names:
                    if _validate_gta_path(depth1):
                        return depth1
                try:
                    for depth2 in depth1.iterdir():
                        if not depth2.is_dir():
                            continue
                        if depth2.name.lower() in gta_folder_names:
                            if _validate_gta_path(depth2):
                                return depth2
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue

    return None


def validate_gta_path(path: str | Path) -> Path:
    """Validate a user-provided or detected GTA V path. Raises ValueError if invalid."""
    p = Path(path)
    if not _validate_gta_path(p):
        log.error("Invalid GTA V path: %s", p)
        raise ValueError(
            f"'{p}' does not appear to be a valid GTA V installation. "
            "Expected to find GTA5.exe or update/update.rpf."
        )
    log.info("Validated GTA V path: %s", p)
    save_cached_path(p)
    return p


def _validate_gta_path(path: Path) -> bool:
    """Check if a path looks like a GTA V installation."""
    if not path.is_dir():
        return False
    # GTA V Legacy has GTA5.exe, Enhanced has GTA5_Enhanced.exe or PlayGTAV.exe
    has_exe = (
        (path / "GTA5.exe").exists()
        or (path / "GTA5_Enhanced.exe").exists()
        or (path / "PlayGTAV.exe").exists()
    )
    has_update = (path / "update" / "update.rpf").exists()
    return has_exe or has_update
