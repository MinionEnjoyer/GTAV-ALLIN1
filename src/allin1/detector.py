"""GTA V installation path detection."""

from __future__ import annotations

import os
import platform
import re
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
    # Common install locations
    candidates = [
        Path(r"C:\Program Files\Rockstar Games\Grand Theft Auto V"),
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V"),
        Path(r"D:\SteamLibrary\steamapps\common\Grand Theft Auto V"),
        Path(r"E:\SteamLibrary\steamapps\common\Grand Theft Auto V"),
    ]

    # Try Steam library folders
    steam_paths = _find_steam_libraries_windows()
    for sp in steam_paths:
        candidates.append(sp / "steamapps" / "common" / "Grand Theft Auto V")

    # Try Epic Games
    epic_path = Path(os.environ.get("PROGRAMFILES", "")) / "Epic Games" / "GTAV"
    candidates.append(epic_path)

    # Try Windows Registry
    reg_path = _check_registry()
    if reg_path:
        candidates.insert(0, reg_path)

    for path in candidates:
        if _validate_gta_path(path):
            return path

    return None


def _detect_linux() -> Path | None:
    home = Path.home()
    candidates = [
        home / ".steam" / "steam" / "steamapps" / "common" / "Grand Theft Auto V",
        home / ".local" / "share" / "Steam" / "steamapps" / "common" / "Grand Theft Auto V",
    ]
    for path in candidates:
        if _validate_gta_path(path):
            return path
    return None


def _find_steam_libraries_windows() -> list[Path]:
    """Parse Steam's libraryfolders.vdf to find library paths."""
    vdf_locations = [
        Path(r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf"),
        Path(r"C:\Program Files\Steam\steamapps\libraryfolders.vdf"),
    ]
    libraries: list[Path] = []
    for vdf in vdf_locations:
        if vdf.exists():
            try:
                text = vdf.read_text(encoding="utf-8")
                # Match "path" entries in the VDF
                for match in re.finditer(r'"path"\s+"([^"]+)"', text):
                    libraries.append(Path(match.group(1)))
            except OSError:
                continue
    return libraries


def _check_registry() -> Path | None:
    """Check Windows Registry for GTA V install path."""
    try:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games\Grand Theft Auto V", "InstallFolder"),
        ]
        for hive, subkey, value_name in keys:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    return Path(value)
            except FileNotFoundError:
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
    # GTA V Legacy has GTA5.exe, Enhanced has GTA5_Enhanced.exe
    has_exe = (path / "GTA5.exe").exists() or (path / "GTA5_Enhanced.exe").exists()
    has_update = (path / "update" / "update.rpf").exists()
    return has_exe or has_update
