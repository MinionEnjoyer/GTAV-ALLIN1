"""Shared contained installation path for legacy and Tauri SDK distributions."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import uuid
import zipfile
from allin1.release_paths import contained, filesystem_path, no_links, relative_path, strict_json, tree_files, unique_paths

SHELL = "allin1-sdk-desktop.exe"
SIDECAR = "sidecar/ALLIN1-SDK-Desktop-Sidecar.exe"


def validated_payloads(archive):
    infos = archive.infolist()
    if len(infos) > 20000 or sum(i.file_size for i in infos) > 2 * 1024**3: raise ValueError("SDK archive exceeds limits")
    files, directories, seen = {}, [], set()
    for item in infos:
        name = relative_path(item.orig_filename[:-1] if item.is_dir() else item.orig_filename).as_posix()
        if name.casefold() in seen: raise ValueError("Duplicate SDK destination")
        seen.add(name.casefold())
        kind = stat.S_IFMT(item.external_attr >> 16)
        if item.flag_bits & 1 or kind not in (0, stat.S_IFDIR if item.is_dir() else stat.S_IFREG): raise ValueError("Unsafe SDK archive member")
        if item.is_dir(): directories.append(name)
        else: files[name] = item
    unique_paths(list(files))
    folded_files = {name.casefold() for name in files}
    for name in directories:
        if any(parent.casefold() in folded_files for parent in [name, *[str(p) for p in relative_path(name).parents]]): raise ValueError("SDK file/directory collision")
    if "checksums.json" not in files: raise ValueError("SDK archive is missing checksums.json")
    if files["checksums.json"].file_size > 8 * 1024**2: raise ValueError("SDK checksum manifest exceeds limits")
    checksums = strict_json(archive.read(files["checksums.json"]))
    if not isinstance(checksums, dict): raise ValueError("SDK checksums must be an object")
    unique_paths(list(checksums))
    if set(checksums) != set(files) - {"checksums.json"}: raise ValueError("SDK checksum manifest does not exactly match the payload")
    for name, digest in checksums.items():
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest): raise ValueError("invalid SDK checksum")
        sha = hashlib.sha256()
        with archive.open(files[name]) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""): sha.update(chunk)
        if sha.hexdigest() != digest: raise ValueError(f"SDK checksum mismatch: {name}")
    return checksums, files


def validate_tauri(metadata, identity, checksums):
    if not isinstance(metadata, dict) or type(metadata.get("schema_version")) is not int or metadata["schema_version"] != 1 or metadata.get("product") != "ALLIN1-SDK" or metadata.get("format") != "tauri-v2": raise ValueError("Invalid Tauri SDK release metadata")
    if metadata.get("entrypoint") != SHELL or metadata.get("sidecar_entrypoint") != SIDECAR: raise ValueError("Invalid Tauri SDK entrypoint")
    if not {SHELL, SIDECAR, "resource-checksums.json", "build-identity.json", "release.json"}.issubset(checksums): raise ValueError("Tauri SDK archive is missing a required payload")
    if not isinstance(identity, dict) or identity.get("kind") != "sdk_build_identity" or type(identity.get("schema_version")) is not int or identity["schema_version"] != 1 or identity.get("sdk_version") != metadata.get("version") or identity.get("build_id") != metadata.get("build_id"):
        raise ValueError("Tauri SDK release/build identity mismatch")
    if metadata.get("build_identity_sha256") != checksums["build-identity.json"]: raise ValueError("Tauri SDK build identity hash mismatch")


def install_archive(archive_path, root, verify):
    root = no_links(root)
    if root == Path.home() or root.parent == root: raise ValueError("Invalid managed SDK root")
    disk_root = filesystem_path(root)
    if disk_root.exists() and not disk_root.is_dir(): raise ValueError("SDK root is not a directory")
    old_files = tree_files(root) if disk_root.exists() else {}
    old_owned = set()
    if old_files:
        marker = filesystem_path(contained(root, "checksums.json"))
        if not marker.is_file(): raise ValueError("Existing SDK has no ownership manifest; choose an empty destination")
        old_manifest = strict_json(marker.read_bytes())
        if not isinstance(old_manifest, dict): raise ValueError("Invalid existing SDK manifest")
        unique_paths(list(old_manifest))
        old_owned = {*old_manifest, "checksums.json"}
    pending = no_links(root.with_name(root.name + ".installing-" + uuid.uuid4().hex))
    backup = no_links(root.with_name(root.name + ".previous-" + uuid.uuid4().hex))
    with zipfile.ZipFile(no_links(archive_path)) as archive:
        _, files = validated_payloads(archive)
        preserved = {name: path for name, path in old_files.items() if name not in old_owned}
        unique_paths([*files, *preserved])
        # Validate every archive and preserved-user-file destination before staging.
        for name in [*files, *preserved]: contained(pending, name)
        disk_pending, disk_backup = filesystem_path(pending), filesystem_path(backup)
        disk_pending.mkdir(parents=True, exist_ok=False)
        try:
            for name, info in files.items():
                target = filesystem_path(contained(pending, name)); target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as incoming, target.open("xb") as outgoing: shutil.copyfileobj(incoming, outgoing)
            for name, source in preserved.items():
                target = filesystem_path(contained(pending, name)); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(filesystem_path(no_links(source)), target)
            staged = verify(pending)
            if not staged.healthy: raise ValueError(f"Staged SDK failed verification: {staged.detail}")
            if disk_root.exists(): filesystem_path(no_links(root)).replace(disk_backup)
            try:
                disk_pending.replace(disk_root)
                result = verify(root)
                if not result.healthy: raise ValueError(f"Installed SDK failed verification: {result.detail}")
                return result
            except Exception:
                if disk_root.exists(): disk_root.replace(disk_pending)
                if disk_backup.exists(): disk_backup.replace(disk_root)
                raise
        finally:
            if disk_pending.exists(): shutil.rmtree(filesystem_path(no_links(pending)))
