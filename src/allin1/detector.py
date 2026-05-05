"""GTA V installation path detection.

Searches across all drives, Steam libraries, Epic Games manifests,
Rockstar Games Launcher data, and the Windows Registry to find GTA V.
"""

from __future__ import annotations

import os
import platform
import re
import string
from pathlib import Path


def detect_gta_path() -> Path | None:
    """Attempt to auto-detect the GTA V installation directory."""
    system = platform.system()

    if system == "Windows":
        return _detect_windows()
    elif system == "Linux":
        return _detect_linux()
    # macOS: no native GTA V, user must specify manually
    return None


def _detect_windows() -> Path | None:
    candidates: list[Path] = []

    # 1. Windows Registry (most reliable -- set by Rockstar's installer)
    reg_path = _check_registry()
    if reg_path:
        candidates.append(reg_path)

    # 2. Steam libraries (parses libraryfolders.vdf from all known locations)
    steam_libs = _find_steam_libraries_windows()
    for lib in steam_libs:
        candidates.append(lib / "steamapps" / "common" / "Grand Theft Auto V")

    # 3. Epic Games (parse manifest files for actual install location)
    epic_paths = _find_epic_install_windows()
    candidates.extend(epic_paths)

    # 4. Rockstar Games Launcher
    rgl_paths = _find_rockstar_launcher_windows()
    candidates.extend(rgl_paths)

    # 5. Common hardcoded paths on every available drive
    drives = _get_windows_drives()
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

    for path in unique:
        if _validate_gta_path(path):
            return path

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

    for path in candidates:
        if _validate_gta_path(path):
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


def validate_gta_path(path: str | Path) -> Path:
    """Validate a user-provided or detected GTA V path. Raises ValueError if invalid."""
    p = Path(path)
    if not _validate_gta_path(p):
        raise ValueError(
            f"'{p}' does not appear to be a valid GTA V installation. "
            "Expected to find GTA5.exe or update/update.rpf."
        )
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
