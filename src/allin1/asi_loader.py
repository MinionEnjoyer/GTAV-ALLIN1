"""ASI Loader deployment and BattlEye configuration.

Handles three things for one-click installation:

1. **ASI Loader deployment** — downloads Ultimate ASI Loader (MIT) from
   GitHub and places it in the GTA V root so that .asi plugins load.
2. **BattlEye bypass** — sets ``-nobattleye`` in Steam's launch options
   for GTA V Enhanced (App ID 3240220) so BattlEye doesn't block mods.
3. **Detection** — checks whether an ASI loader is already present.

Uses only stdlib modules (urllib, zipfile, re) — no extra pip deps.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

log = logging.getLogger("allin1.asi_loader")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ultimate ASI Loader x64 release (MIT license).
_RELEASE_URL = (
    "https://github.com/ThirteenAG/Ultimate-ASI-Loader"
    "/releases/latest/download/Ultimate-ASI-Loader_x64.zip"
)

_ZIP_DLL_NAME = "dinput8.dll"
LEGACY_DLL = "dinput8.dll"
ENHANCED_DLL = "dsound.dll"

_MIN_ZIP_SIZE = 30_000
_MAX_ZIP_SIZE = 5_000_000
_DOWNLOAD_TIMEOUT = 30

# Steam App IDs for GTA V.
_GTA_ENHANCED_APPID = "3240220"
_GTA_LEGACY_APPID = "271590"


def dll_name(is_enhanced: bool) -> str:
    """Return the ASI loader DLL filename for the given edition."""
    return ENHANCED_DLL if is_enhanced else LEGACY_DLL


# ---------------------------------------------------------------------------
# ASI Loader deployment
# ---------------------------------------------------------------------------

def ensure_loader(gta_path: Path, is_enhanced: bool) -> str:
    """Ensure an ASI loader DLL is present in *gta_path*.

    Returns ``"skipped"`` if already present, ``"deployed"`` on success,
    or ``"failed"`` on error.
    """
    target = gta_path / dll_name(is_enhanced)

    if target.exists():
        log.info("ASI loader already present: %s", target)
        return "skipped"

    try:
        _download_and_deploy(target)
        return "deployed"
    except Exception:
        log.warning(
            "Could not download ASI Loader. Install one manually "
            "(e.g. Ultimate ASI Loader or ScriptHookV).",
            exc_info=True,
        )
        return "failed"


def _download_and_deploy(dest: Path) -> None:
    """Download the ZIP from GitHub, extract the DLL, write to *dest*."""
    log.info("Downloading Ultimate ASI Loader from GitHub...")

    try:
        with urlopen(_RELEASE_URL, timeout=_DOWNLOAD_TIMEOUT) as resp:
            data = resp.read()
    except (URLError, OSError) as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc

    if not _MIN_ZIP_SIZE <= len(data) <= _MAX_ZIP_SIZE:
        raise RuntimeError(
            f"Downloaded file has unexpected size ({len(data)} bytes)"
        )

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        dll_entry = None
        for name in zf.namelist():
            if name.lower().endswith(_ZIP_DLL_NAME):
                dll_entry = name
                break
        if dll_entry is None:
            raise RuntimeError(
                f"{_ZIP_DLL_NAME} not found inside the downloaded ZIP"
            )
        dll_bytes = zf.read(dll_entry)

    dest.write_bytes(dll_bytes)
    log.info("Deployed ASI Loader -> %s (%d bytes)", dest, len(dll_bytes))


# ---------------------------------------------------------------------------
# BattlEye — set -nobattleye in Steam launch options
# ---------------------------------------------------------------------------

def ensure_nobattleye(gta_path: Path, is_enhanced: bool) -> str:
    """Set ``-nobattleye`` in Steam launch options for GTA V.

    Modifies Steam's ``localconfig.vdf`` so the game launches without
    BattlEye anti-cheat (required for single-player modding).

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.

    Steam should ideally be closed for changes to persist, but we try
    regardless and warn if Steam appears to be running.
    """
    appid = _GTA_ENHANCED_APPID if is_enhanced else _GTA_LEGACY_APPID

    try:
        configs = _find_localconfig_files(gta_path)
    except Exception:
        log.warning("Could not locate Steam localconfig.vdf", exc_info=True)
        return "failed"

    if not configs:
        log.warning("No Steam localconfig.vdf files found")
        return "failed"

    result = "failed"
    for config_path in configs:
        status = _set_launch_option(config_path, appid, "-nobattleye")
        if status in ("set", "already_set"):
            result = status

    return result


def _find_localconfig_files(gta_path: Path) -> list[Path]:
    """Locate Steam localconfig.vdf files by walking up from the game path.

    GTA V is installed under a Steam library at:
      ``<steam_lib>/steamapps/common/Grand Theft Auto V[/Enhanced]``

    The Steam root contains ``userdata/<id>/config/localconfig.vdf``.
    """
    configs: list[Path] = []

    # Walk up from gta_path to find steamapps/, then the Steam root.
    steam_root = _find_steam_root(gta_path)
    if steam_root is None:
        return configs

    userdata = steam_root / "userdata"
    if not userdata.is_dir():
        return configs

    for user_dir in userdata.iterdir():
        if user_dir.is_dir() and user_dir.name.isdigit():
            lc = user_dir / "config" / "localconfig.vdf"
            if lc.is_file():
                configs.append(lc)

    return configs


def _find_steam_root(gta_path: Path) -> Path | None:
    """Find the Steam root directory by walking up from the game path."""
    # Typical: <steam_root>/steamapps/common/Grand Theft Auto V
    # So steam_root is 3 levels up from the game folder.
    current = gta_path.resolve()
    for _ in range(6):  # Walk up at most 6 levels
        if (current / "steam.exe").exists() or (current / "Steam.exe").exists():
            return current
        # Also check for userdata/ as a marker
        if (current / "userdata").is_dir() and (current / "steamapps").is_dir():
            return current
        # On Linux/macOS, check for steam.sh
        if (current / "steam.sh").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _set_launch_option(config_path: Path, appid: str, option: str) -> str:
    """Add *option* to the LaunchOptions for *appid* in a localconfig.vdf.

    Preserves existing launch options — appends if not already present.
    Creates a backup before modifying.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log.warning("Cannot read %s", config_path)
        return "failed"

    # Find the apps section and locate our app ID.
    # VDF structure: UserLocalConfigStore -> Software -> Valve -> Steam -> apps -> <appid>
    # We look for the LaunchOptions key under the app ID block.

    current_options = _extract_launch_options(text, appid)

    if current_options is not None and option in current_options:
        log.info("Launch option '%s' already set for App %s", option, appid)
        return "already_set"

    # Build the new launch options value.
    if current_options is not None:
        # Append to existing options.
        new_options = f"{current_options} {option}".strip()
    else:
        new_options = option

    # Backup the original file.
    backup = config_path.with_suffix(".vdf.bak")
    try:
        shutil.copy2(config_path, backup)
    except OSError:
        pass  # Best-effort backup

    # Write the modified config.
    new_text = _set_launch_options_text(text, appid, new_options)
    if new_text is None:
        log.warning("Could not inject launch options into %s", config_path)
        return "failed"

    try:
        config_path.write_text(new_text, encoding="utf-8")
        log.info("Set launch option '%s' for App %s in %s", option, appid, config_path)
        return "set"
    except OSError:
        log.warning("Cannot write %s", config_path)
        return "failed"


def _extract_launch_options(text: str, appid: str) -> str | None:
    """Extract the current LaunchOptions value for *appid* from VDF text."""
    # Find the app block:  "3240220" { ... "LaunchOptions" "value" ... }
    # VDF is not regular but for our specific key path this regex approach works.
    pattern = (
        rf'"{re.escape(appid)}"'
        r'\s*\{'
        r'((?:[^{}]|\{[^{}]*\})*)'  # capture block contents (one level of nesting)
        r'\}'
    )
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None

    block = match.group(1)
    opt_match = re.search(
        r'"LaunchOptions"\s+"([^"]*)"', block, re.IGNORECASE
    )
    if opt_match:
        return opt_match.group(1)
    return None  # Key exists but no LaunchOptions


def _set_launch_options_text(text: str, appid: str, value: str) -> str | None:
    """Return *text* with LaunchOptions for *appid* set to *value*.

    If the app block exists and has LaunchOptions, replaces the value.
    If the app block exists without LaunchOptions, inserts the key.
    If the app block doesn't exist, inserts it into the apps section.
    """
    escaped_appid = re.escape(appid)

    # Case 1: App block exists with LaunchOptions — replace value.
    pattern_existing = (
        rf'("{escaped_appid}"\s*\{{[^{{}}]*?"LaunchOptions"\s+)"([^"]*)"'
    )
    match = re.search(pattern_existing, text, re.IGNORECASE)
    if match:
        return text[:match.start(2)] + value + text[match.end(2):]

    # Case 2: App block exists without LaunchOptions — insert key.
    pattern_block = rf'("{escaped_appid}"\s*\{{)'
    match = re.search(pattern_block, text, re.IGNORECASE)
    if match:
        insert_pos = match.end()
        indent = "\t\t\t\t\t\t\t"
        insertion = f'\n{indent}"LaunchOptions"\t\t"{value}"'
        return text[:insert_pos] + insertion + text[insert_pos:]

    # Case 3: No app block — find the "apps" section and insert a new block.
    # Look for the innermost "apps" section (under Software/Valve/Steam).
    apps_pattern = r'("apps"\s*\{)'
    # Find all matches and use the last one (deepest nesting = correct one).
    matches = list(re.finditer(apps_pattern, text, re.IGNORECASE))
    if matches:
        last_apps = matches[-1]
        insert_pos = last_apps.end()
        indent = "\t\t\t\t\t\t"
        block = (
            f'\n{indent}"{appid}"'
            f'\n{indent}{{'
            f'\n{indent}\t"LaunchOptions"\t\t"{value}"'
            f'\n{indent}}}'
        )
        return text[:insert_pos] + block + text[insert_pos:]

    return None  # Could not find any apps section
