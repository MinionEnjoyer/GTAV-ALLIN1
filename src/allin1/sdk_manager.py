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
from allin1.release_paths import no_links, contained, filesystem_path, strict_json, unique_paths, tree_files
from allin1.sdk_installation import SHELL, SIDECAR, validated_payloads, validate_tauri, install_archive

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
    r"^ALLIN1-SDK-(?P<version>\d+(?:\.\d+){1,3})-(?:win-x64|portable)\.zip$",
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
    root = root or default_sdk_root()
    try:
        root = no_links(root)
        metadata_path = filesystem_path(contained(root, SDK_RELEASE_METADATA))
        if metadata_path.is_file():
            metadata = strict_json(metadata_path.read_bytes())
            if isinstance(metadata, dict) and metadata.get("format") == "tauri-v2":
                checksums = strict_json(filesystem_path(contained(root, SDK_CHECKSUMS)).read_bytes())
                identity = strict_json(filesystem_path(contained(root, "build-identity.json")).read_bytes())
                validate_tauri(metadata, identity, checksums)
                _verify_installed_payloads(root, checksums)
                resources = strict_json(filesystem_path(contained(root, "resource-checksums.json")).read_bytes())
                _verify_resource_contract(resources, checksums)
                _verify_resource_tree(root, resources)
                for entry in (SHELL, SIDECAR):
                    with filesystem_path(contained(root, entry)).open("rb") as stream:
                        if stream.read(2) != b"MZ": raise ValueError("SDK executable is invalid")
                version = metadata["version"]
                normalize_version(version)
                return SdkStatus(root, root / SHELL, version, True, f"SDK {version} payload integrity verified (build {metadata['build_id']}); live acceptance is separate")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return SdkStatus(root, None, None, False, f"Installation metadata is invalid: {exc}")
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
    try:
        _verify_installed_payloads(root, strict_json(contained(root, SDK_CHECKSUMS).read_bytes()))
    except (OSError, ValueError, TypeError) as exc:
        return SdkStatus(root, executable, version, False, f"SDK payload verification failed: {exc}")
    return SdkStatus(root, executable, version, True, f"ALLIN1 SDK {version} payload integrity verified")


def _verify_installed_payloads(root, checksums):
    if not isinstance(checksums, dict) or not checksums: raise ValueError("Invalid SDK checksum manifest")
    unique_paths(list(checksums))
    for name, expected in checksums.items():
        if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected): raise ValueError("Invalid SDK checksum")
        digest = hashlib.sha256()
        with filesystem_path(contained(root, name)).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
        if digest.hexdigest() != expected: raise ValueError(f"SDK checksum mismatch: {name}")


def _verify_resource_contract(resources, checksums):
    if not isinstance(resources, dict): raise ValueError("Invalid SDK resource manifest")
    unique_paths(list(resources))
    if set(resources) != set(checksums) - {SHELL, SIDECAR, "resource-checksums.json", "release.json"}:
        raise ValueError("SDK resource manifest does not match packaged resources")
    if any(checksums.get(name) != digest for name, digest in resources.items()):
        raise ValueError("SDK companion resource checksum mismatch")


def _verify_resource_tree(root: Path, resources: dict) -> None:
    """Match the frozen SDK's exact resource-directory policy.

    Root-level projects/preferences remain unowned. Unknown files inside a
    packaged resource directory must not produce a healthy installation that
    the SDK itself refuses to start. Never delete those files during repair.
    """
    for directory in {name.split("/", 1)[0] for name in resources if "/" in name}:
        actual = {f"{directory}/{name}" for name in tree_files(contained(root, directory))}
        expected = {name for name in resources if name.startswith(directory + "/")}
        if actual != expected:
            raise ValueError(f"Stale or unlisted SDK resources: {directory}")


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
    exact = [item for item in assets if str(item.get("name", "")).casefold() == expected_name.casefold()]
    if len(exact) > 1:
        raise ValueError("latest SDK release has ambiguous archive assets")
    archive = exact[0] if exact else None
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
    matching_checksums = [item for item in assets
                          if str(item.get("name", "")).casefold() == checksum_name.casefold()]
    if len(matching_checksums) > 1:
        raise ValueError("latest SDK release has ambiguous checksum assets")
    checksum = matching_checksums[0] if matching_checksums else None
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
    archive_path = no_links(archive_path)
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("SDK archive exceeds the allowed size")
    with zipfile.ZipFile(archive_path) as archive:
        files = [item for item in archive.infolist() if not item.is_dir()]
        if len(files) > MAX_ARCHIVE_FILES:
            raise ValueError("SDK archive contains too many files")
        unpacked = sum(item.file_size for item in files)
        if unpacked > MAX_EXTRACTED_BYTES:
            raise ValueError("SDK archive expands beyond the allowed size")
        for item in archive.infolist(): _safe_member(item)
        checksums, names = validated_payloads(archive)
        try:
            metadata = strict_json(archive.read(names[SDK_RELEASE_METADATA]))
            if not isinstance(metadata, dict): raise ValueError("SDK release metadata is invalid")
        except (KeyError, TypeError) as exc:
            raise ValueError("SDK release metadata is invalid") from exc
        if metadata.get("format") == "tauri-v2":
            identity = strict_json(archive.read(names["build-identity.json"]))
            validate_tauri(metadata, identity, checksums)
            _verify_resource_contract(strict_json(archive.read(names["resource-checksums.json"])), checksums)
            version = metadata["version"]
            normalize_version(version)
            if expected_version and normalize_version(version) != normalize_version(expected_version):
                raise ValueError(f"SDK package version {version} does not match {expected_version}")
            for entry in (SHELL, SIDECAR):
                with archive.open(names[entry]) as stream:
                    if stream.read(2) != b"MZ": raise ValueError(f"SDK executable is not a Windows PE file: {entry}")
            return SdkPackageInfo(version, len(checksums), unpacked)
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
    root = no_links(root or default_sdk_root())
    package = inspect_sdk_archive(archive_path, expected_version)
    status = install_archive(archive_path, root, read_sdk_status)
    if not status.healthy or status.version != package.version:
        raise RuntimeError("SDK installation did not pass its post-install verification")
    if root == default_sdk_root() and (root / SDK_CLI_EXECUTABLE).is_file():
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
    # SdkRelease is also a public API input, not only a value returned by the
    # GitHub resolver. Validate it before network access or opening any output.
    match = _ARCHIVE_PATTERN.fullmatch(release.archive_name) if isinstance(release.archive_name, str) else None
    if match is None or normalize_version(match.group("version")) != normalize_version(release.version):
        raise ValueError("SDK archive name must be a safe release-version-matched filename")
    if type(release.archive_size) is not int or not 1 <= release.archive_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("SDK archive size is outside the allowed range")
    with opener(_github_request(release.checksum_url), timeout=timeout) as response:
        expected = _parse_checksum(_read_limited_response(response, 16 * 1024), release.archive_name)
    with tempfile.TemporaryDirectory(prefix="allin1-sdk-download-") as temporary:
        archive_path = contained(Path(temporary), release.archive_name)
        digest = hashlib.sha256()
        downloaded = 0
        with opener(_github_request(release.archive_url), timeout=timeout) as response, archive_path.open("xb") as output:
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
    """Retire the managed SDK to a recoverable sibling; never erase user files."""
    import uuid
    root = no_links(root or default_sdk_root())
    if not filesystem_path(root).exists():
        return False
    if root == Path.home() or root.parent == root: raise ValueError("Invalid managed SDK root")
    tree_files(root)
    manifest = strict_json(filesystem_path(contained(root, SDK_CHECKSUMS)).read_bytes())
    if not isinstance(manifest, dict) or not manifest: raise ValueError("Missing SDK ownership manifest")
    unique_paths(list(manifest))
    retired = no_links(root.with_name(root.name + ".uninstalled-" + uuid.uuid4().hex))
    filesystem_path(root).replace(filesystem_path(retired))
    if root == default_sdk_root():
        try:
            register_sdk_cli(root, remove=True)
        except OSError:
            pass
    return True
