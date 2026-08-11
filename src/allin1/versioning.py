"""Release and installed-version tracking for the desktop manager."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from allin1 import __version__

VERSION_FILE = "ALLIN1.version"
RELEASES_API = "https://api.github.com/repos/MinionEnjoyer/GTAV-ALLIN1/releases/latest"


def normalize_version(value: str) -> tuple[int, ...]:
    """Return a comparable numeric tuple from a release tag or version text."""
    match = re.fullmatch(r"\s*[vV]?(\d+(?:\.\d+){1,3})(?:[-+][0-9A-Za-z.-]+)?\s*", value)
    if not match:
        raise ValueError(f"invalid version: {value!r}")
    parts = tuple(int(part) for part in match.group(1).split("."))
    return parts + (0,) * (4 - len(parts))


def is_newer(candidate: str, installed: str) -> bool:
    return normalize_version(candidate) > normalize_version(installed)


def read_installed_version(scripts_dir: Path | None) -> str | None:
    if scripts_dir is None:
        return None
    marker = scripts_dir / VERSION_FILE
    if not marker.is_file():
        return None
    value = marker.read_text(encoding="utf-8").strip()
    normalize_version(value)
    return value.lstrip("vV")


def write_installed_version(scripts_dir: Path, version: str = __version__) -> Path:
    normalize_version(version)
    scripts_dir.mkdir(parents=True, exist_ok=True)
    marker = scripts_dir / VERSION_FILE
    temporary = marker.with_suffix(".version.tmp")
    temporary.write_text(version + "\n", encoding="utf-8")
    temporary.replace(marker)
    return marker


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    update_available: bool
    name: str = ""


def fetch_latest_release(installed: str = __version__, *, timeout: float = 5.0,
                         opener=urlopen) -> ReleaseInfo:
    request = Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"GTAV-ALLIN1/{__version__}",
    })
    with opener(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag = str(payload["tag_name"])
    version = tag.lstrip("vV")
    normalize_version(version)
    return ReleaseInfo(
        version=version,
        url=str(payload["html_url"]),
        update_available=is_newer(version, installed),
        name=str(payload.get("name", "")),
    )
