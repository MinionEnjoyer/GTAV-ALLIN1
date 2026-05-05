"""ASI Loader deployment and BattlEye configuration.

Handles three things for one-click installation:

1. **ASI Loader deployment** — downloads Ultimate ASI Loader (MIT) from
   GitHub and places it in the GTA V root so that .asi plugins load.
2. **BattlEye bypass** — sets ``-nobattleye`` via two methods:
   a) Steam ``localconfig.vdf`` (found via Windows registry) — this is
      what actually prevents BattlEye from launching, since Steam passes
      the flag to the Rockstar Launcher *before* BattlEye starts.
   b) ``commandline.txt`` in game root — fallback for non-Steam launches.
3. **Detection** — checks whether an ASI loader is already present.

Uses only stdlib modules (urllib, zipfile, re) — no extra pip deps.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import sys
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

_COMMANDLINE_TXT = "commandline.txt"
_NOBATTLEYE_FLAG = "-nobattleye"

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
# BattlEye — set -nobattleye in Steam launch options + commandline.txt
# ---------------------------------------------------------------------------

def ensure_nobattleye(gta_path: Path, is_enhanced: bool) -> str:
    """Disable BattlEye for GTA V single-player modding.

    Uses two complementary approaches:

    1. **Steam launch options** (primary) — sets ``-nobattleye`` in Steam's
       ``localconfig.vdf`` so the Rockstar Launcher skips BattlEye entirely.
       This is the only method that works when launching through Steam,
       because BattlEye blocks proxy DLLs before the game even starts.
       Steam path is found via the Windows registry.

    2. **commandline.txt** (fallback) — writes ``-nobattleye`` to the game
       root for direct Rockstar Launcher / Epic launches.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    steam_result = _set_steam_launch_option(gta_path, is_enhanced)
    cmdline_result = _set_commandline_txt(gta_path)

    # If either method confirms already_set, report that.
    if steam_result == "already_set" and cmdline_result == "already_set":
        return "already_set"
    # If either method succeeded, report set.
    if steam_result == "set" or cmdline_result == "set":
        return "set"
    if steam_result == "already_set" or cmdline_result == "already_set":
        return "already_set"
    return "failed"


def _set_commandline_txt(gta_path: Path) -> str:
    """Write ``-nobattleye`` to ``commandline.txt`` in the game root."""
    cmdline_path = gta_path / _COMMANDLINE_TXT
    try:
        if cmdline_path.exists():
            text = cmdline_path.read_text(encoding="utf-8", errors="replace")
            if _NOBATTLEYE_FLAG in text:
                log.info("commandline.txt already contains %s", _NOBATTLEYE_FLAG)
                return "already_set"
            text = text.rstrip("\n")
            new_text = f"{text}\n{_NOBATTLEYE_FLAG}\n" if text else f"{_NOBATTLEYE_FLAG}\n"
        else:
            new_text = f"{_NOBATTLEYE_FLAG}\n"

        cmdline_path.write_text(new_text, encoding="utf-8")
        log.info("Wrote %s to %s", _NOBATTLEYE_FLAG, cmdline_path)
        return "set"
    except OSError:
        log.warning("Could not write %s", cmdline_path, exc_info=True)
        return "failed"


# ---------------------------------------------------------------------------
# Steam localconfig.vdf — the method that actually disables BattlEye
# ---------------------------------------------------------------------------

def _set_steam_launch_option(gta_path: Path, is_enhanced: bool) -> str:
    """Set ``-nobattleye`` in Steam's localconfig.vdf for the correct App ID.

    Finds Steam via the Windows registry, then locates all
    ``userdata/<id>/config/localconfig.vdf`` files and patches them.
    """
    appid = _GTA_ENHANCED_APPID if is_enhanced else _GTA_LEGACY_APPID

    steam_root = _find_steam_root_registry()
    if steam_root is None:
        log.info("Steam not found via registry — skipping localconfig.vdf")
        return "failed"

    configs = _find_localconfig_files(steam_root)
    if not configs:
        log.warning("No localconfig.vdf files found under %s", steam_root)
        return "failed"

    result = "failed"
    for config_path in configs:
        status = _patch_localconfig(config_path, appid, _NOBATTLEYE_FLAG)
        if status in ("set", "already_set"):
            result = status

    return result


def _find_steam_root_registry() -> Path | None:
    """Find Steam install directory from the Windows registry.

    Reads ``HKEY_CURRENT_USER\\Software\\Valve\\Steam\\SteamPath``.
    Returns None on non-Windows or if the key doesn't exist.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            p = Path(steam_path)
            if p.is_dir():
                log.info("Steam root from registry: %s", p)
                return p
    except Exception:
        log.debug("Could not read Steam path from registry", exc_info=True)
    return None


def _find_localconfig_files(steam_root: Path) -> list[Path]:
    """Find all localconfig.vdf files under Steam's userdata/ directory."""
    configs: list[Path] = []
    userdata = steam_root / "userdata"
    if not userdata.is_dir():
        return configs

    for user_dir in userdata.iterdir():
        if user_dir.is_dir() and user_dir.name.isdigit():
            lc = user_dir / "config" / "localconfig.vdf"
            if lc.is_file():
                configs.append(lc)

    return configs


def _patch_localconfig(config_path: Path, appid: str, option: str) -> str:
    """Add *option* to LaunchOptions for *appid* in a localconfig.vdf.

    Preserves existing launch options.  Creates a .bak backup first.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    try:
        text = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        log.warning("Cannot read %s", config_path)
        return "failed"

    current = _extract_launch_options(text, appid)

    if current is not None and option in current:
        log.info("'%s' already in launch options for App %s", option, appid)
        return "already_set"

    new_value = f"{current} {option}".strip() if current else option

    # Backup before modifying.
    try:
        shutil.copy2(config_path, config_path.with_suffix(".vdf.bak"))
    except OSError:
        pass

    new_text = _set_launch_options_text(text, appid, new_value)
    if new_text is None:
        log.warning("Could not patch launch options in %s", config_path)
        return "failed"

    try:
        config_path.write_text(new_text, encoding="utf-8")
        log.info("Set '%s' for App %s in %s", option, appid, config_path)
        return "set"
    except OSError:
        log.warning("Cannot write %s", config_path)
        return "failed"


def _extract_launch_options(text: str, appid: str) -> str | None:
    """Extract the current LaunchOptions value for *appid* from VDF text."""
    pattern = (
        rf'"{re.escape(appid)}"'
        r'\s*\{'
        r'((?:[^{}]|\{[^{}]*\})*)'
        r'\}'
    )
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None

    block = match.group(1)
    opt_match = re.search(
        r'"LaunchOptions"\s+"([^"]*)"', block, re.IGNORECASE
    )
    return opt_match.group(1) if opt_match else None


def _set_launch_options_text(text: str, appid: str, value: str) -> str | None:
    """Return *text* with LaunchOptions for *appid* set to *value*.

    Handles three cases:
    1. App block has LaunchOptions → replace value
    2. App block exists without LaunchOptions → insert key
    3. No app block → create block in apps section
    """
    esc = re.escape(appid)

    # Case 1: replace existing LaunchOptions value.
    pat = rf'("{esc}"\s*\{{[^{{}}]*?"LaunchOptions"\s+)"([^"]*)"'
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        return text[:m.start(2)] + value + text[m.end(2):]

    # Case 2: app block exists, insert LaunchOptions.
    pat = rf'("{esc}"\s*\{{)'
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        pos = m.end()
        return text[:pos] + f'\n\t\t\t\t\t\t\t"LaunchOptions"\t\t"{value}"' + text[pos:]

    # Case 3: no app block — insert into the innermost "apps" section.
    matches = list(re.finditer(r'("apps"\s*\{)', text, re.IGNORECASE))
    if matches:
        pos = matches[-1].end()
        block = (
            f'\n\t\t\t\t\t\t"{appid}"'
            f'\n\t\t\t\t\t\t{{'
            f'\n\t\t\t\t\t\t\t"LaunchOptions"\t\t"{value}"'
            f'\n\t\t\t\t\t\t}}'
        )
        return text[:pos] + block + text[pos:]

    return None
