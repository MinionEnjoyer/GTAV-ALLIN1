"""Contained replacement installer for complete ALLIN1 Launcher releases.

This is deliberately separate from the generic updater: a Launcher portable is
an exact application tree, while game updates may legitimately overlay a small
set of package-owned files.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import uuid
import zipfile

from allin1 import __version__
from allin1.release_paths import (
    contained, filesystem_path, no_links, strict_json, tree_files, unique_paths,
)
from allin1.runtime_resources import SIDECAR_NAME, sha256, verify_resources
from allin1.updater import _archive_payloads


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHELL = "allin1-launcher-desktop.exe"
_MARKER = "checksums.json"
_STRICT_TREES = ("resources/", "runtime/", "sidecar/")
_RUNTIME_MANIFEST = "runtime/runtime-manifest.json"
_RUNTIME_IDENTITY = "runtime/lib/allin1/_desktop_build.json"


@dataclass(frozen=True)
class LauncherInstallResult:
    root: Path
    backup: Path | None
    deployed: tuple[str, ...]
    preserved: tuple[str, ...]


def _hash(path: Path) -> str:
    return sha256(filesystem_path(no_links(path)))


def _read_json(archive: zipfile.ZipFile, name: str) -> dict:
    try:
        value = strict_json(archive.read(name))
    except KeyError as exc:
        raise ValueError(f"Launcher archive is missing {name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Launcher {name} must be an object")
    return value


def _validate_identity(metadata: dict, identity: dict, checksums: dict[str, str], *, current: bool) -> None:
    required = {_SHELL, "build-identity.json", "release.json", "runtime/python.exe",
                "runtime/bootstrap.py", _RUNTIME_MANIFEST, _RUNTIME_IDENTITY}
    if not required.issubset(checksums):
        raise ValueError("Launcher archive is missing required runtime payloads")
    if (set(metadata) != {"schema_version", "product", "format", "version", "build_id",
                         "entrypoint", "unsigned_manual_download", "release_qualified"}
            or type(metadata.get("schema_version")) is not int
            or metadata["schema_version"] != 1
            or metadata.get("product") != "ALLIN1-Launcher"
            or metadata.get("format") != "tauri-v2"
            or metadata.get("entrypoint") != _SHELL
            or type(metadata.get("unsigned_manual_download")) is not bool
            or type(metadata.get("release_qualified")) is not bool):
        raise ValueError("Invalid Launcher release metadata")
    if (type(identity.get("schema_version")) is not int
            or identity["schema_version"] != 1
            or identity.get("kind") != "launcher_desktop_build"
            or not isinstance(identity.get("version"), str)
            or (current and identity["version"] != __version__)
            or not isinstance(identity.get("build_id"), str)
            or not identity["build_id"]
            or metadata.get("version") != identity["version"]
            or metadata.get("build_id") != identity["build_id"]
            or not isinstance(identity.get("resources"), dict)
            or not identity["resources"]
            or not isinstance(identity.get("runtime"), dict)
            or identity["runtime"].get("kind") != "shared-python"):
        raise ValueError("Invalid Launcher build identity")
    resources = identity["resources"]
    unique_paths(list(resources))
    expected = {"resources/" + name: digest for name, digest in resources.items()}
    actual = {name: digest for name, digest in checksums.items() if name.startswith("resources/")}
    if actual != expected:
        raise ValueError("Launcher resources do not exactly match the build identity")
    if any(not isinstance(digest, str) or not _SHA256.fullmatch(digest)
           for digest in resources.values()):
        raise ValueError("Invalid Launcher resource checksum")


def _validate_runtime(manifest: dict, embedded_identity: object, identity: dict,
                      checksums: dict[str, str]) -> None:
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if (not isinstance(manifest, dict) or set(manifest) != {"schema_version", "files"}
            or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1 or not isinstance(files, dict) or not files):
        raise ValueError("Invalid shared Launcher runtime manifest")
    unique_paths(list(files))
    runtime = {name.removeprefix("runtime/"): digest for name, digest in checksums.items()
               if name.startswith("runtime/") and name != _RUNTIME_MANIFEST}
    if files != runtime:
        raise ValueError("Shared Launcher runtime does not exactly match its manifest")
    if any(not isinstance(digest, str) or not _SHA256.fullmatch(digest)
           for digest in files.values()):
        raise ValueError("Invalid shared Launcher runtime checksum")
    if embedded_identity != identity:
        raise ValueError("Embedded shared runtime identity differs from Launcher identity")
    if any(name.casefold().startswith("sidecar/")
           or Path(name).name.casefold() in {"weaponpreview.exe", SIDECAR_NAME.casefold()}
           for name in checksums):
        raise ValueError("Shared Launcher runtime contains an obsolete frozen helper")


def _validated_archive(archive_path: Path) -> tuple[dict[str, str], dict[str, zipfile.ZipInfo]]:
    with zipfile.ZipFile(no_links(archive_path)) as archive:
        checksums = _archive_payloads(archive)
        infos = {info.filename: info for info in archive.infolist() if not info.is_dir()}
        if set(infos) != {*checksums, _MARKER}:
            raise ValueError("Launcher archive has an invalid payload inventory")
        identity = _read_json(archive, "build-identity.json")
        _validate_identity(_read_json(archive, "release.json"), identity, checksums,
                           current=True)
        _validate_runtime(_read_json(archive, _RUNTIME_MANIFEST),
                          _read_json(archive, _RUNTIME_IDENTITY), identity, checksums)
        return checksums, infos


def _verify_launcher_root(root: Path) -> None:
    root = no_links(root)
    files = tree_files(root)
    marker = filesystem_path(contained(root, _MARKER))
    if not marker.is_file():
        raise ValueError("Launcher installation is missing checksums.json")
    checksums = strict_json(marker.read_bytes())
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError("Invalid installed Launcher checksum manifest")
    unique_paths(list(checksums))
    owned = {*checksums, _MARKER}
    if not owned.issubset(files):
        raise ValueError("Launcher installation has missing files")
    if any(name.casefold().startswith(tuple(prefix.casefold() for prefix in _STRICT_TREES))
           for name in set(files) - owned):
        raise ValueError("Launcher installation has unowned resource or runtime files")
    for name, digest in checksums.items():
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("Invalid installed Launcher checksum")
        if _hash(contained(root, name)) != digest:
            raise ValueError(f"Installed Launcher checksum mismatch: {name}")
    identity = strict_json(filesystem_path(contained(root, "build-identity.json")).read_bytes())
    metadata = strict_json(filesystem_path(contained(root, "release.json")).read_bytes())
    if not isinstance(identity, dict) or not isinstance(metadata, dict):
        raise ValueError("Invalid installed Launcher identity")
    _validate_identity(metadata, identity, checksums, current=True)
    _validate_runtime(
        strict_json(filesystem_path(contained(root, _RUNTIME_MANIFEST)).read_bytes()),
        strict_json(filesystem_path(contained(root, _RUNTIME_IDENTITY)).read_bytes()),
        identity, checksums,
    )
    verify_resources(filesystem_path(contained(root, "resources")), identity)


def _old_ownership(root: Path, old_files: dict[str, Path]) -> set[str]:
    if not old_files:
        return set()
    marker = filesystem_path(contained(root, _MARKER))
    if not marker.is_file():
        raise ValueError("Existing Launcher has no ownership manifest; choose an empty destination")
    manifest = strict_json(marker.read_bytes())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("Invalid existing Launcher ownership manifest")
    unique_paths(list(manifest))
    for name, digest in manifest.items():
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ValueError("Invalid existing Launcher ownership checksum")
        path = old_files.get(name)
        if path is None or _hash(path) != digest:
            raise ValueError(f"Existing Launcher ownership does not match: {name}")
    try:
        metadata = strict_json(filesystem_path(contained(root, "release.json")).read_bytes())
        identity = strict_json(filesystem_path(contained(root, "build-identity.json")).read_bytes())
    except FileNotFoundError as exc:
        raise ValueError("Existing ownership marker is not an ALLIN1 Launcher release") from exc
    if not isinstance(metadata, dict) or not isinstance(identity, dict):
        raise ValueError("Existing ownership marker is not an ALLIN1 Launcher release")
    _validate_identity(metadata, identity, manifest, current=False)
    _validate_runtime(
        strict_json(filesystem_path(contained(root, _RUNTIME_MANIFEST)).read_bytes()),
        strict_json(filesystem_path(contained(root, _RUNTIME_IDENTITY)).read_bytes()),
        identity, manifest,
    )
    return {*manifest, _MARKER}


def _remove_tree(path: Path) -> None:
    disk_path = filesystem_path(no_links(path))
    if disk_path.exists():
        shutil.rmtree(disk_path)


def _move_directory(source: Path, target: Path) -> None:
    filesystem_path(no_links(source)).replace(filesystem_path(no_links(target)))


def _same_location(left: Path, right: Path) -> bool:
    try:
        return filesystem_path(left).samefile(filesystem_path(right))
    except OSError:
        return os.path.normcase(str(filesystem_path(left))) == os.path.normcase(str(filesystem_path(right)))


def _unsafe_root(root: Path) -> bool:
    home = no_links(Path.home())
    workspace = no_links(Path(__file__).resolve().parents[2])
    cwd = no_links(Path.cwd())
    if _same_location(root, home):
        return True
    # A destination beneath a workspace can be a disposable candidate, but the
    # workspace itself (or one of its ancestors) must never be swapped out.
    return any(_same_location(root, item) or item.is_relative_to(root)
               for item in (workspace, cwd))


def install_launcher_archive(archive: Path, root: Path) -> LauncherInstallResult:
    """Atomically replace one verified Launcher tree without launching it."""
    archive, root = no_links(Path(archive)), no_links(Path(root))
    if root.parent == root or _unsafe_root(root):
        raise ValueError("Invalid managed Launcher root")
    checksums, _ = _validated_archive(archive)
    disk_root = filesystem_path(root)
    if disk_root.exists() and not disk_root.is_dir():
        raise ValueError("Launcher root is not a directory")
    old_files = tree_files(root) if disk_root.exists() else {}
    old_owned = _old_ownership(root, old_files)
    preserved = {name: path for name, path in old_files.items() if name not in old_owned}
    if any(name.casefold().startswith(tuple(prefix.casefold() for prefix in _STRICT_TREES))
           for name in preserved):
        raise ValueError("Unowned files below Launcher resource or runtime trees are forbidden")
    unique_paths([*checksums, _MARKER, *preserved])
    originals = {name: _hash(path) for name, path in old_files.items()}
    pending = no_links(root.with_name(root.name + ".installing-" + uuid.uuid4().hex))
    backup = no_links(root.with_name(root.name + ".previous-" + uuid.uuid4().hex))
    disk_pending, disk_backup = filesystem_path(pending), filesystem_path(backup)
    disk_pending.mkdir(parents=True, exist_ok=False)
    moved_previous = False
    candidate_deployed = False
    try:
        with zipfile.ZipFile(archive) as bundle:
            for name in [*checksums, _MARKER]:
                target = filesystem_path(contained(pending, name))
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
        for name, source in preserved.items():
            target = filesystem_path(contained(pending, name))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filesystem_path(no_links(source)), target)
        _verify_launcher_root(pending)
        current_files = tree_files(root) if disk_root.exists() else {}
        if (set(current_files) != set(old_files)
                or any(_hash(current_files[name]) != digest for name, digest in originals.items())):
            raise ValueError("Launcher installation changed before deployment")
        if disk_root.exists():
            _move_directory(root, backup)
            moved_previous = True
        try:
            _move_directory(pending, root)
            candidate_deployed = True
        except Exception:
            if moved_previous and disk_backup.exists() and not disk_root.exists():
                _move_directory(backup, root)
            raise
        try:
            _verify_launcher_root(root)
        except Exception:
            if candidate_deployed and disk_root.exists():
                _move_directory(root, pending)
            if moved_previous and disk_backup.exists():
                _move_directory(backup, root)
            raise
        return LauncherInstallResult(root, backup if moved_previous else None,
                                     tuple(sorted([*checksums, _MARKER])),
                                     tuple(sorted(preserved)))
    finally:
        _remove_tree(pending)


__all__ = ["LauncherInstallResult", "install_launcher_archive"]
