"""Ultimate ASI Loader downloader and deployer.

Downloads the MIT-licensed Ultimate ASI Loader by ThirteenAG from GitHub
and deploys it to the GTA V root directory, enabling .asi plugin loading
without any manual setup.

Uses only stdlib modules (urllib, zipfile) — no extra pip dependencies.
"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

log = logging.getLogger("allin1.asi_loader")

# Ultimate ASI Loader x64 release (MIT license).
_RELEASE_URL = (
    "https://github.com/ThirteenAG/Ultimate-ASI-Loader"
    "/releases/latest/download/Ultimate-ASI-Loader_x64.zip"
)

# The ZIP contains dinput8.dll.  For Enhanced Edition we rename to dsound.dll.
_ZIP_DLL_NAME = "dinput8.dll"
LEGACY_DLL = "dinput8.dll"
ENHANCED_DLL = "dsound.dll"

# Reasonable size bounds for the download (the ZIP is typically ~100–200 KB).
_MIN_ZIP_SIZE = 30_000
_MAX_ZIP_SIZE = 5_000_000

_DOWNLOAD_TIMEOUT = 30  # seconds


def dll_name(is_enhanced: bool) -> str:
    """Return the ASI loader DLL filename for the given edition."""
    return ENHANCED_DLL if is_enhanced else LEGACY_DLL


def ensure(gta_path: Path, is_enhanced: bool) -> str:
    """Ensure an ASI loader DLL is present in *gta_path*.

    Returns a status string: ``"skipped"``, ``"deployed"``, or ``"failed"``.

    * If the target DLL already exists, returns ``"skipped"`` (another mod
      or the user already provides an ASI loader).
    * On success, downloads and deploys the DLL, returns ``"deployed"``.
    * On any error (network, corrupt ZIP, I/O), logs a warning and returns
      ``"failed"`` — the rest of the installation can still continue.
    """
    target = gta_path / dll_name(is_enhanced)

    if target.exists():
        log.info("ASI loader already present: %s", target)
        return "skipped"

    try:
        _download_and_deploy(target, is_enhanced)
        return "deployed"
    except Exception:
        log.warning(
            "Could not download ASI Loader. You may need to install one "
            "manually (e.g. Ultimate ASI Loader or ScriptHookV).",
            exc_info=True,
        )
        return "failed"


def _download_and_deploy(dest: Path, is_enhanced: bool) -> None:
    """Download the ZIP, extract the DLL, and write it to *dest*."""
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
        # Find the DLL inside the ZIP (may be in a subdirectory).
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
    log.info("Deployed ASI Loader → %s (%d bytes)", dest, len(dll_bytes))
