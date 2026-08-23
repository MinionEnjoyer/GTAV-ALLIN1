"""Consent-based installation of the optional GTA V RPF runtime loader.

The third-party binaries are never bundled with ALLIN1.  The author of
RageOpenV explicitly asks distributors to link to the official release, so
the launcher downloads the pinned release directly from its GitHub project
only after the player opts in.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable

from allin1 import __version__
from allin1.health import inspect_windows_binary, sha256_file


log = logging.getLogger("allin1.rpf_loader")

RAGEOPENV_RELEASE_PAGE = "https://github.com/Chiheb-Bacha/RageOpenV/releases/tag/v1.0"
RAGEOPENV_SOURCE = "https://github.com/Chiheb-Bacha/RageOpenV"
ULTIMATE_ASI_RELEASE_PAGE = (
    "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/tag/v9.7.4"
)
ULTIMATE_ASI_SOURCE = "https://github.com/ThirteenAG/Ultimate-ASI-Loader"


@dataclass(frozen=True)
class ReleaseAsset:
    provider: str
    version: str
    url: str
    sha256: str
    size: int
    member: str
    release_page: str
    source_url: str


# These pins are intentionally updated through an ALLIN1 release rather than
# following an unreviewed "latest" binary at runtime.
RAGEOPENV_ASSET = ReleaseAsset(
    provider="RageOpenV",
    version="v1.0",
    url="https://github.com/Chiheb-Bacha/RageOpenV/releases/download/v1.0/RageOpenV.zip",
    sha256="c39d574caa9db4462b20110e87a8229e48deeb2819883800c8e54f1c6c80548c",
    size=121759,
    member="RageOpenV.asi",
    release_page=RAGEOPENV_RELEASE_PAGE,
    source_url=RAGEOPENV_SOURCE,
)
ULTIMATE_ASI_ASSET = ReleaseAsset(
    provider="Ultimate ASI Loader",
    version="v9.7.4",
    url=(
        "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases/download/"
        "v9.7.4/Ultimate-ASI-Loader-NoPDB_x64.zip"
    ),
    sha256="e5860e7d9a1805267535b65749575b5e406cc6ea3325c7392189c578815045d1",
    size=374169,
    member="dinput8.dll",
    release_page=ULTIMATE_ASI_RELEASE_PAGE,
    source_url=ULTIMATE_ASI_SOURCE,
)

PLUGIN_NAMES = ("RageOpenV.asi", "OpenRPF.asi", "OpenIV.asi")
ENHANCED_ASI_LOADERS = ("xinput1_4.dll", "dsound.dll", "dinput8.dll")
LEGACY_ASI_LOADERS = ("dinput8.dll",)
RECEIPT_RELATIVE = Path("allin1_backups") / "ManagedDependencies" / "rpf-loader.json"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


class RpfLoaderInstallError(RuntimeError):
    """A safe, user-facing loader installation failure."""


@dataclass(frozen=True)
class RpfLoaderStatus:
    ready: bool
    plugin: Path | None
    asi_loader: Path | None
    reason: str
    conflicts: tuple[Path, ...] = ()


@dataclass(frozen=True)
class RpfLoaderInstallResult:
    installed: tuple[Path, ...]
    plugin: Path
    asi_loader: Path
    provider: str = "RageOpenV"
    version: str = RAGEOPENV_ASSET.version


def inspect_rpf_loader(gta_path: Path, enhanced: bool) -> RpfLoaderStatus:
    """Inspect supported plug-ins and ASI loaders without loading their code."""
    game = gta_path.resolve()
    preferred = game / "RageOpenV.asi"
    edition_plugin = game / ("OpenRPF.asi" if enhanced else "OpenIV.asi")
    wrong_plugin = game / ("OpenIV.asi" if enhanced else "OpenRPF.asi")

    existing = [game / name for name in PLUGIN_NAMES if (game / name).exists()]
    valid = [path for path in existing if inspect_windows_binary(path).valid]
    conflicts: list[Path] = []
    if wrong_plugin.exists():
        conflicts.append(wrong_plugin)
    if preferred.exists() and edition_plugin.exists():
        conflicts.append(edition_plugin)
    if len(valid) > 1:
        conflicts.extend(path for path in valid if path != preferred)
    conflicts = list(dict.fromkeys(conflicts))
    if conflicts:
        names = ", ".join(path.name for path in conflicts)
        return RpfLoaderStatus(
            False, None, None, f"Conflicting RPF plug-ins are present: {names}",
            tuple(conflicts),
        )

    plugin = preferred if inspect_windows_binary(preferred).valid else None
    if plugin is None and inspect_windows_binary(edition_plugin).valid:
        plugin = edition_plugin
    if plugin is None:
        invalid = [
            path for path in (preferred, edition_plugin)
            if path.exists() and not inspect_windows_binary(path).valid
        ]
        reason = (
            "RPF plug-in is invalid: " + ", ".join(path.name for path in invalid)
            if invalid else "RPF plug-in is missing"
        )
        return RpfLoaderStatus(False, None, None, reason)

    loader_names = ENHANCED_ASI_LOADERS if enhanced else LEGACY_ASI_LOADERS
    asi_loader = next(
        (
            game / name for name in loader_names
            if inspect_windows_binary(game / name).valid
        ),
        None,
    )
    if asi_loader is None:
        invalid = [game / name for name in loader_names if (game / name).exists()]
        reason = (
            "ASI loader is invalid: " + ", ".join(path.name for path in invalid)
            if invalid else "ASI loader is missing"
        )
        return RpfLoaderStatus(False, plugin, None, reason)
    return RpfLoaderStatus(True, plugin, asi_loader, "Ready")


Download = Callable[[ReleaseAsset], bytes]


def _download_asset(asset: ReleaseAsset) -> bytes:
    request = urllib.request.Request(
        asset.url,
        headers={
            "User-Agent": f"ALLIN1/{__version__} dependency-installer",
            "Accept": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                raise RpfLoaderInstallError(
                    f"{asset.provider} download is unexpectedly large."
                )
            payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise RpfLoaderInstallError(
            f"Could not download {asset.provider} from its official release: {exc}"
        ) from exc
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise RpfLoaderInstallError(
            f"{asset.provider} download exceeded the safety limit."
        )
    return payload


def _verified_member(asset: ReleaseAsset, download: Download) -> bytes:
    payload = download(asset)
    if len(payload) != asset.size:
        raise RpfLoaderInstallError(
            f"{asset.provider} size check failed; expected {asset.size} bytes, "
            f"received {len(payload)}."
        )
    actual = hashlib.sha256(payload).hexdigest()
    if actual.lower() != asset.sha256.lower():
        raise RpfLoaderInstallError(
            f"{asset.provider} SHA-256 verification failed. Nothing was installed."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if names.count(asset.member) != 1:
                raise RpfLoaderInstallError(
                    f"{asset.provider} archive does not contain the expected file."
                )
            member = PurePosixPath(asset.member)
            if member.is_absolute() or ".." in member.parts:
                raise RpfLoaderInstallError(
                    f"{asset.provider} archive contains an unsafe path."
                )
            return archive.read(asset.member)
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise RpfLoaderInstallError(
            f"{asset.provider} archive could not be read: {exc}"
        ) from exc


def _validate_binary(payload: bytes, filename: str) -> None:
    with tempfile.TemporaryDirectory(prefix="allin1-rpf-loader-") as folder:
        candidate = Path(folder) / filename
        candidate.write_bytes(payload)
        inspection = inspect_windows_binary(candidate)
    if not inspection.valid:
        raise RpfLoaderInstallError(
            f"Downloaded {filename} is not a valid x64 Windows binary "
            f"({inspection.reason})."
        )


def _create_atomic(destination: Path, payload: bytes) -> None:
    if destination.exists():
        raise RpfLoaderInstallError(
            f"Refusing to overwrite existing dependency file: {destination.name}"
        )
    temporary = destination.with_name(f".{destination.name}.allin1.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.exists():
            raise RpfLoaderInstallError(
                f"Dependency file appeared during installation: {destination.name}"
            )
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_receipt(gta_path: Path, installed: list[tuple[Path, ReleaseAsset]]) -> Path:
    receipt = gta_path / RECEIPT_RELATIVE
    receipt.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "managed_by": "ALLIN1",
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "files": [
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "provider": asset.provider,
                "version": asset.version,
                "release_page": asset.release_page,
                "source_url": asset.source_url,
            }
            for path, asset in installed
        ],
    }
    temporary = receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt)
    return receipt


def install_recommended_rpf_loader(
    gta_path: Path,
    enhanced: bool,
    *,
    download: Download | None = None,
) -> RpfLoaderInstallResult:
    """Install verified loader files into previously unused root paths."""
    game = gta_path.resolve()
    status = inspect_rpf_loader(game, enhanced)
    if status.ready:
        assert status.plugin is not None and status.asi_loader is not None
        return RpfLoaderInstallResult((), status.plugin, status.asi_loader)
    existing_plugins = [game / name for name in PLUGIN_NAMES if (game / name).exists()]
    if existing_plugins:
        details = ", ".join(path.name for path in existing_plugins)
        raise RpfLoaderInstallError(
            "A missing, invalid, or conflicting RPF plug-in must be resolved "
            f"manually before ALLIN1 can install RageOpenV: {details}."
        )

    fetch = download or _download_asset
    plugin_payload = _verified_member(RAGEOPENV_ASSET, fetch)
    _validate_binary(plugin_payload, "RageOpenV.asi")

    loader_names = ENHANCED_ASI_LOADERS if enhanced else LEGACY_ASI_LOADERS
    valid_asi = next(
        (
            game / name for name in loader_names
            if inspect_windows_binary(game / name).valid
        ),
        None,
    )
    invalid_asi = [game / name for name in loader_names if (game / name).exists()]
    if valid_asi is None and invalid_asi:
        details = ", ".join(path.name for path in invalid_asi)
        raise RpfLoaderInstallError(
            "An existing ASI loader is invalid; ALLIN1 will not overwrite it: "
            f"{details}."
        )

    asi_payload: bytes | None = None
    asi_target = valid_asi
    if asi_target is None:
        asi_payload = _verified_member(ULTIMATE_ASI_ASSET, fetch)
        asi_target = game / ("xinput1_4.dll" if enhanced else "dinput8.dll")
        _validate_binary(asi_payload, asi_target.name)

    plugin_target = game / "RageOpenV.asi"
    created: list[tuple[Path, ReleaseAsset]] = []
    try:
        _create_atomic(plugin_target, plugin_payload)
        created.append((plugin_target, RAGEOPENV_ASSET))
        if asi_payload is not None:
            _create_atomic(asi_target, asi_payload)
            created.append((asi_target, ULTIMATE_ASI_ASSET))
        status = inspect_rpf_loader(game, enhanced)
        if not status.ready:
            raise RpfLoaderInstallError(
                f"Installed files did not pass the dependency check: {status.reason}."
            )
        _write_receipt(game, created)
    except Exception:
        for path, _asset in reversed(created):
            path.unlink(missing_ok=True)
        raise

    log.info(
        "Installed managed RPF dependency: %s",
        ", ".join(path.name for path, _asset in created),
    )
    return RpfLoaderInstallResult(
        tuple(path for path, _asset in created), plugin_target, asi_target,
    )


def uninstall_managed_rpf_loader(gta_path: Path) -> list[Path]:
    """Remove only unchanged dependency files recorded as installed by ALLIN1."""
    game = gta_path.resolve()
    receipt = game / RECEIPT_RELATIVE
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        log.warning("Could not read managed RPF dependency receipt: %s", exc)
        return []
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        log.warning("Ignoring unsupported managed RPF dependency receipt")
        return []

    removed: list[Path] = []
    retained: list[dict] = []
    for entry in payload.get("files", []):
        if not isinstance(entry, dict):
            continue
        relative = PurePosixPath(str(entry.get("path", "")))
        if relative.is_absolute() or len(relative.parts) != 1 or ".." in relative.parts:
            retained.append(entry)
            continue
        target = game / relative.name
        if not target.exists():
            continue
        expected = str(entry.get("sha256", "")).lower()
        try:
            matches = len(expected) == 64 and sha256_file(target).lower() == expected
        except OSError:
            matches = False
        if not matches:
            log.warning(
                "Preserving modified managed dependency during uninstall: %s",
                target,
            )
            retained.append(entry)
            continue
        target.unlink()
        removed.append(target)

    if retained:
        payload["files"] = retained
        receipt.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        receipt.unlink(missing_ok=True)
        try:
            receipt.parent.rmdir()
            receipt.parent.parent.rmdir()
        except OSError:
            pass
    return removed
