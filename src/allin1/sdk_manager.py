"""Managed installation lifecycle for the standalone ALLIN1 SDK."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping
from urllib.request import Request, urlopen

from allin1 import __version__
from allin1.versioning import is_newer, normalize_version

SDK_REPOSITORY_URL = "https://github.com/MinionEnjoyer/ALLIN1-SDK"
SDK_RELEASES_API = "https://api.github.com/repos/MinionEnjoyer/ALLIN1-SDK/releases/latest"
SDK_EXECUTABLE = "ALLIN1-SDK-Desktop.exe"
SDK_CLI_EXECUTABLE = "allin1-sdk.exe"
SDK_AGENT_EXECUTABLE = "ALLIN1-SDK-Agent.exe"
SDK_UPDATER_EXECUTABLE = "ALLIN1-SDK-Updater.exe"
SDK_RELEASE_METADATA = "release.json"
SDK_CHECKSUMS = "checksums.json"
APPLICATION_CONTROL_WINERROR = 4551
MAX_ARCHIVE_BYTES = 768 * 1024 * 1024
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_FILES = 20_000
_ARCHIVE_PATTERN = re.compile(
    r"^ALLIN1-SDK-(?P<version>\d+(?:\.\d+){1,3})-win-x64\.zip$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SdkRelease:
    version: str
    name: str
    page_url: str
    archive_url: str
    archive_name: str
    archive_size: int
    checksum_url: str


@dataclass(frozen=True)
class SdkStatus:
    root: Path
    executable: Path | None
    version: str | None
    healthy: bool
    detail: str

    @property
    def installed(self) -> bool:
        return self.executable is not None


@dataclass(frozen=True)
class SdkPackageInfo:
    version: str
    file_count: int
    unpacked_size: int


ProgressCallback = Callable[[str, int, int], None]


def sdk_launch_error_message(error: OSError) -> str:
    """Translate Windows application-control failures into an actionable message."""
    if getattr(error, "winerror", None) == APPLICATION_CONTROL_WINERROR:
        return (
            "Windows Application Control blocked the SDK because this build is not signed "
            "by a publisher trusted by the active device policy.\n\n"
            "The SDK package passed ALLIN1's checksum verification, but Windows separately "
            "controls which applications may run. Reinstalling or unblocking the file will "
            "not change this policy. Install a publisher-signed SDK build, or ask the device "
            "administrator to approve ALLIN1 SDK."
        )
    return str(error)


def default_sdk_root(environment: Mapping[str, str] | None = None) -> Path:
    """Return the per-user managed SDK location without touching the game."""
    values = os.environ if environment is None else environment
    base = values.get("LOCALAPPDATA") or values.get("XDG_DATA_HOME")
    if base:
        return Path(base).expanduser().resolve() / "ALLIN1" / "SDK"
    return Path.home().resolve() / ".allin1" / "SDK"


def _normalized_path_entry(value: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.expandvars(value.strip().strip('"'))))


def updated_sdk_user_path(value: str, root: Path, *, remove: bool = False) -> str:
    """Return a de-duplicated user PATH with the managed SDK root added or removed."""
    target = _normalized_path_entry(str(root.resolve()))
    entries = [item.strip() for item in value.split(os.pathsep) if item.strip()]
    filtered = [item for item in entries if _normalized_path_entry(item) != target]
    if not remove:
        filtered.append(str(root.resolve()))
    return os.pathsep.join(filtered)


def _broadcast_environment_change() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(result),
        )
    except (AttributeError, OSError):
        pass


def register_sdk_cli(root: Path, *, remove: bool = False) -> None:
    """Register the frozen console command for future clean PowerShell sessions."""
    if os.name != "nt":
        return
    import winreg

    key = winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, "Environment", 0,
        winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE,
    )
    with key:
        try:
            current, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            current, value_type = "", winreg.REG_EXPAND_SZ
        updated = updated_sdk_user_path(str(current), root, remove=remove)
        if updated != str(current):
            winreg.SetValueEx(key, "Path", 0, value_type, updated)
    os.environ["PATH"] = updated_sdk_user_path(
        os.environ.get("PATH", ""), root, remove=remove,
    )
    _broadcast_environment_change()


def read_sdk_status(root: Path | None = None) -> SdkStatus:
    root = (root or default_sdk_root()).resolve()
    executable = root / SDK_EXECUTABLE
    if not executable.is_file():
        return SdkStatus(root, None, None, False, "Not installed")
    try:
        with executable.open("rb") as stream:
            signature = stream.read(2)
        if signature != b"MZ":
            return SdkStatus(root, executable, None, False, "SDK executable is invalid")
    except OSError as exc:
        return SdkStatus(root, executable, None, False, f"SDK executable cannot be read: {exc}")
    cli = root / SDK_CLI_EXECUTABLE
    if not cli.is_file():
        return SdkStatus(root, executable, None, False, "SDK console executable is missing")
    metadata = root / SDK_RELEASE_METADATA
    if not metadata.is_file():
        return SdkStatus(root, executable, None, False, "Installation metadata is missing")
    try:
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        version = str(payload["version"]).lstrip("vV")
        normalize_version(version)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return SdkStatus(root, executable, None, False, f"Installation metadata is invalid: {exc}")
    updater_name = payload.get("updater_entrypoint")
    if updater_name is not None:
        if updater_name != SDK_UPDATER_EXECUTABLE:
            return SdkStatus(
                root, executable, version, False,
                "Installation metadata names an invalid SDK updater",
            )
        updater = root / SDK_UPDATER_EXECUTABLE
        if not updater.is_file():
            return SdkStatus(root, executable, version, False, "SDK updater is missing")
        try:
            with updater.open("rb") as stream:
                signature = stream.read(2)
            if signature != b"MZ":
                return SdkStatus(root, executable, version, False, "SDK updater is invalid")
        except OSError as exc:
            return SdkStatus(
                root, executable, version, False,
                f"SDK updater cannot be read: {exc}",
            )
    return SdkStatus(root, executable, version, True, f"ALLIN1 SDK {version} is ready")


def _github_request(url: str) -> Request:
    return Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"GTAV-ALLIN1/{__version__}",
    })


def fetch_latest_sdk_release(*, timeout: float = 8.0, opener=urlopen) -> SdkRelease:
    """Resolve the latest public Windows SDK archive and its checksum asset."""
    with opener(_github_request(SDK_RELEASES_API), timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    version = str(payload["tag_name"]).lstrip("vV")
    normalize_version(version)
    assets = payload.get("assets", [])
    expected_name = f"ALLIN1-SDK-{version}-win-x64.zip"
    archive = next(
        (item for item in assets if str(item.get("name", "")).casefold()
         == expected_name.casefold()),
        None,
    )
    if archive is None:
        matching = [
            item for item in assets
            if _ARCHIVE_PATTERN.fullmatch(str(item.get("name", "")))
        ]
        archive = matching[0] if len(matching) == 1 else None
    if archive is None:
        raise ValueError("latest SDK release has no unambiguous win-x64 archive")
    archive_name = str(archive["name"])
    asset_version = _ARCHIVE_PATTERN.fullmatch(archive_name)
    if asset_version is None or normalize_version(asset_version.group("version")) != normalize_version(version):
        raise ValueError("SDK archive version does not match its release tag")
    checksum_name = archive_name + ".sha256"
    checksum = next(
        (item for item in assets if str(item.get("name", "")).casefold()
         == checksum_name.casefold()),
        None,
    )
    if checksum is None:
        raise ValueError(f"latest SDK release is missing {checksum_name}")
    size = int(archive.get("size", 0))
    if size < 1 or size > MAX_ARCHIVE_BYTES:
        raise ValueError(f"SDK archive size is outside the allowed range: {size} bytes")
    return SdkRelease(
        version=version,
        name=str(payload.get("name") or f"ALLIN1 SDK {version}"),
        page_url=str(payload["html_url"]),
        archive_url=str(archive["browser_download_url"]),
        archive_name=archive_name,
        archive_size=size,
        checksum_url=str(checksum["browser_download_url"]),
    )


def _read_limited_response(response, limit: int) -> bytes:
    content = bytearray()
    while True:
        chunk = response.read(min(1024 * 1024, limit + 1 - len(content)))
        if not chunk:
            return bytes(content)
        content.extend(chunk)
        if len(content) > limit:
            raise ValueError("download exceeds the allowed size")


def _parse_checksum(content: bytes, archive_name: str) -> str:
    try:
        line = next(value.strip() for value in content.decode("ascii").splitlines() if value.strip())
    except (UnicodeDecodeError, StopIteration) as exc:
        raise ValueError("SDK checksum asset is empty or invalid") from exc
    parts = line.split()
    digest = parts[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("SDK checksum asset does not contain a SHA-256 digest")
    if len(parts) > 1 and Path(parts[-1].lstrip("*")).name.casefold() != archive_name.casefold():
        raise ValueError("SDK checksum names a different archive")
    return digest


def _safe_member(info: zipfile.ZipInfo) -> PurePosixPath:
    if "\\" in info.filename or "\x00" in info.filename:
        raise ValueError(f"unsafe SDK archive member: {info.filename}")
    path = PurePosixPath(info.filename)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe SDK archive member: {info.filename}")
    if any(":" in part for part in path.parts):
        raise ValueError(f"unsafe SDK archive member: {info.filename}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ValueError(f"SDK archive contains a symbolic link: {info.filename}")
    if info.flag_bits & 0x1:
        raise ValueError(f"SDK archive contains an encrypted member: {info.filename}")
    return path


def inspect_sdk_archive(archive_path: Path, expected_version: str | None = None) -> SdkPackageInfo:
    """Validate archive structure, metadata, and every internal payload checksum."""
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("SDK archive exceeds the allowed size")
    with zipfile.ZipFile(archive_path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if len(files) > MAX_ARCHIVE_FILES:
            raise ValueError("SDK archive contains too many files")
        unpacked = sum(item.file_size for item in files)
        if unpacked > MAX_EXTRACTED_BYTES:
            raise ValueError("SDK archive expands beyond the allowed size")
        names = {_safe_member(item).as_posix(): item for item in files}
        required = {
            SDK_EXECUTABLE, SDK_CLI_EXECUTABLE, SDK_AGENT_EXECUTABLE,
            SDK_RELEASE_METADATA, SDK_CHECKSUMS,
        }
        missing = required - names.keys()
        if missing:
            raise ValueError("SDK archive is missing: " + ", ".join(sorted(missing)))
        try:
            metadata = json.loads(archive.read(names[SDK_RELEASE_METADATA]).decode("utf-8"))
            version = str(metadata["version"]).lstrip("vV")
            normalize_version(version)
            if str(metadata.get("product", "")) != "ALLIN1-SDK":
                raise ValueError("release metadata names the wrong product")
            if metadata.get("entrypoint") != SDK_EXECUTABLE:
                raise ValueError("SDK release metadata names the wrong desktop entrypoint")
            if metadata.get("cli_entrypoint") != SDK_CLI_EXECUTABLE:
                raise ValueError("SDK release metadata names the wrong console entrypoint")
            updater_name = metadata.get("updater_entrypoint")
            if updater_name is not None and updater_name != SDK_UPDATER_EXECUTABLE:
                raise ValueError("SDK release metadata names the wrong updater entrypoint")
            if updater_name is not None and SDK_UPDATER_EXECUTABLE not in names:
                raise ValueError("SDK archive is missing its declared updater executable")
            checksums = json.loads(archive.read(names[SDK_CHECKSUMS]).decode("utf-8"))
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("SDK release metadata is invalid") from exc
        if expected_version and normalize_version(version) != normalize_version(expected_version):
            raise ValueError(f"SDK package version {version} does not match {expected_version}")
        if not isinstance(checksums, dict):
            raise ValueError("SDK checksums.json must be an object")
        payload_names = set(names) - {SDK_CHECKSUMS}
        if set(checksums) != payload_names:
            raise ValueError("SDK checksum manifest does not exactly match the payload")
        for name, expected in checksums.items():
            digest = str(expected).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"invalid SDK checksum for {name}")
            actual = hashlib.sha256(archive.read(names[name])).hexdigest()
            if actual != digest:
                raise ValueError(f"SDK checksum mismatch: {name}")
        executables = [SDK_EXECUTABLE, SDK_CLI_EXECUTABLE, SDK_AGENT_EXECUTABLE]
        if updater_name is not None:
            executables.append(SDK_UPDATER_EXECUTABLE)
        for executable in executables:
            if archive.read(names[executable])[:2] != b"MZ":
                raise ValueError(f"SDK executable is not a Windows PE file: {executable}")
    return SdkPackageInfo(version, len(payload_names), unpacked)


def install_sdk_archive(
    archive_path: Path,
    root: Path | None = None,
    *,
    expected_version: str | None = None,
) -> SdkStatus:
    """Install a verified SDK package with an atomic directory swap."""
    root = (root or default_sdk_root()).resolve()
    package = inspect_sdk_archive(archive_path, expected_version)
    root.parent.mkdir(parents=True, exist_ok=True)
    pending = root.with_name(root.name + ".installing")
    backup = root.with_name(root.name + ".previous")
    for transient in (pending, backup):
        if transient.exists():
            shutil.rmtree(transient)
    pending.mkdir()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                path = _safe_member(info)
                target = pending.joinpath(*path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        if root.exists():
            root.replace(backup)
        try:
            pending.replace(root)
        except Exception:
            if backup.exists() and not root.exists():
                backup.replace(root)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if pending.exists():
            shutil.rmtree(pending)
        raise
    status = read_sdk_status(root)
    if not status.healthy or status.version != package.version:
        raise RuntimeError("SDK installation did not pass its post-install verification")
    if root == default_sdk_root():
        try:
            register_sdk_cli(root)
        except OSError as exc:
            raise RuntimeError(
                "SDK installed, but Windows could not register the allin1-sdk console command "
                f"for the current user: {exc}"
            ) from exc
    return status


def install_sdk_release(
    release: SdkRelease,
    root: Path | None = None,
    *,
    timeout: float = 60.0,
    opener=urlopen,
    progress: ProgressCallback | None = None,
) -> SdkStatus:
    """Download, externally verify, and transactionally install a release."""
    with opener(_github_request(release.checksum_url), timeout=timeout) as response:
        expected = _parse_checksum(_read_limited_response(response, 16 * 1024), release.archive_name)
    with tempfile.TemporaryDirectory(prefix="allin1-sdk-download-") as temporary:
        archive_path = Path(temporary) / release.archive_name
        digest = hashlib.sha256()
        downloaded = 0
        with opener(_github_request(release.archive_url), timeout=timeout) as response, archive_path.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise ValueError("SDK download exceeds the allowed size")
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress("Downloading SDK", downloaded, release.archive_size)
        if downloaded != release.archive_size:
            raise ValueError(
                f"SDK download size mismatch: expected {release.archive_size}, received {downloaded}"
            )
        if digest.hexdigest() != expected:
            raise ValueError("downloaded SDK archive failed SHA-256 verification")
        if progress:
            progress("Verifying SDK", downloaded, downloaded)
        return install_sdk_archive(archive_path, root, expected_version=release.version)


def sdk_update_available(status: SdkStatus, release: SdkRelease) -> bool:
    return status.version is None or is_newer(release.version, status.version)


def uninstall_sdk(root: Path | None = None) -> bool:
    """Remove only the explicitly managed SDK application directory."""
    root = (root or default_sdk_root()).resolve()
    if not root.exists():
        return False
    if root == default_sdk_root():
        try:
            register_sdk_cli(root, remove=True)
        except OSError:
            pass
    shutil.rmtree(root)
    return True
