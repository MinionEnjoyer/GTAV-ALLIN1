"""ASI Loader deployment and BattlEye configuration.

Handles three things for one-click installation:

1. **ASI Loader deployment** — downloads Ultimate ASI Loader (MIT) from
   GitHub and places it in the GTA V root so that .asi plugins load.
2. **BattlEye bypass** — writes ``-nobattleye`` to a ``commandline.txt``
   file in the GTA V root, disabling BattlEye for single-player modding.
   Works regardless of launcher (Steam, Rockstar, Epic).
3. **Detection** — checks whether an ASI loader is already present.

Uses only stdlib modules (urllib, zipfile) — no extra pip deps.
"""

from __future__ import annotations

import io
import logging
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
# BattlEye — write -nobattleye to commandline.txt in game root
# ---------------------------------------------------------------------------

def ensure_nobattleye(gta_path: Path, is_enhanced: bool) -> str:
    """Ensure ``-nobattleye`` is present in the game's ``commandline.txt``.

    GTA V reads command-line arguments from ``commandline.txt`` in its root
    directory on every launch.  This works with Steam, Rockstar Launcher,
    and Epic — no launcher-specific config files needed.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    cmdline_path = gta_path / _COMMANDLINE_TXT

    try:
        if cmdline_path.exists():
            text = cmdline_path.read_text(encoding="utf-8", errors="replace")
            if _NOBATTLEYE_FLAG in text:
                log.info("commandline.txt already contains %s", _NOBATTLEYE_FLAG)
                return "already_set"
            # Append to existing content (preserve other flags).
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
