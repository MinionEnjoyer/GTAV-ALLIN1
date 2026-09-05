"""Checksum-verified deployment with contained, versioned rollback receipts."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from allin1.release_paths import contained, no_links, relative_path, strict_json, unique_paths

MAX_RELEASE_BYTES = 2 * 1024 * 1024 * 1024
MAX_RELEASE_FILES = 20_000
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class UpdateResult:
    deployed: tuple[str, ...]
    backup: Path


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with no_links(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_release(output: Path, root: Path, files: list[Path], *,
                    extra_files: dict[str, bytes] | None = None) -> Path:
    root = no_links(root)
    sources = {}
    for path in files:
        source = no_links(path if path.is_absolute() else root / path)
        if not source.is_file():
            raise FileNotFoundError(source)
        name = source.relative_to(root).as_posix()
        if name in sources:
            raise ValueError(f"duplicate archive member: {name}")
        sources[name] = source
    generated = extra_files or {}
    for name in generated:
        try:
            relative_path(name)
            if name.casefold() == "checksums.json":
                raise ValueError("reserved manifest")
        except ValueError as exc:
            raise ValueError(f"unsafe generated archive member: {name}") from exc
    unique_paths([*sources, *generated, "checksums.json"])
    output = no_links(output)
    if output in sources.values():
        raise ValueError("release output would overwrite its input")
    output.parent.mkdir(parents=True, exist_ok=True)
    checksums = {}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*sources, *generated]):
            content = sources[name].read_bytes() if name in sources else generated[name]
            checksums[name] = hashlib.sha256(content).hexdigest()
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
        info = zipfile.ZipInfo("checksums.json", (2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(checksums, indent=2, sort_keys=True))
    return output


def _archive_payloads(archive: zipfile.ZipFile) -> dict[str, str]:
    infos = archive.infolist()
    if len(infos) > MAX_RELEASE_FILES or sum(i.file_size for i in infos) > MAX_RELEASE_BYTES:
        raise ValueError("release archive exceeds allowed size")
    names = []
    for item in infos:
        try:
            name = relative_path(item.orig_filename).as_posix()
        except ValueError as exc:
            raise ValueError(f"unsafe archive member: {item.orig_filename}") from exc
        mode = item.external_attr >> 16
        if item.is_dir() or item.flag_bits & 1 or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            raise ValueError(f"unsafe archive member type: {name}")
        names.append(name)
    unique_paths(names)
    if "checksums.json" not in names:
        raise ValueError("release is missing checksums.json")
    if archive.getinfo("checksums.json").file_size > 8 * 1024 * 1024:
        raise ValueError("checksums.json exceeds allowed size")
    checksums = strict_json(archive.read("checksums.json"))
    if not isinstance(checksums, dict) or not checksums:
        raise ValueError("checksums.json must be a nonempty object")
    unique_paths(list(checksums))
    if set(checksums) != set(names) - {"checksums.json"}:
        raise ValueError("checksum manifest must exactly match archive payloads")
    for name, digest in checksums.items():
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"invalid checksum: {name}")
        actual = hashlib.sha256()
        with archive.open(name) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                actual.update(chunk)
        if actual.hexdigest() != digest:
            raise ValueError(f"checksum mismatch: {name}")
    return checksums


def _target(root: Path, name: str) -> Path:
    path = contained(root, name)
    if path.exists() and not path.is_file():
        raise ValueError(f"release destination is not a regular file: {name}")
    for parent in path.parents:
        if parent.exists() and not parent.is_dir():
            raise ValueError(f"release parent is not a directory: {parent}")
    return path


def _replace(source: Path, target: Path) -> None:
    target = no_links(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".update-" + uuid.uuid4().hex)
    try:
        with no_links(source).open("rb") as incoming, temporary.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        no_links(target)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def deploy_release(archive_path: Path, destination: Path, backup_root: Path) -> UpdateResult:
    destination, backup_root = no_links(destination), no_links(backup_root)
    if destination == backup_root or destination.is_relative_to(backup_root) or backup_root.is_relative_to(destination):
        raise ValueError("installation and backup roots must be disjoint")
    backup = backup_root / ("previous-" + uuid.uuid4().hex)
    with zipfile.ZipFile(no_links(archive_path)) as archive:
        checksums = _archive_payloads(archive)
        targets = {name: _target(destination, name) for name in checksums}
        for name in checksums:
            _target(backup / "files", name)
        originals = {name: _sha(path) if path.exists() else None for name, path in targets.items()}
        # Validate every path and archive member before any destination write.
        with tempfile.TemporaryDirectory(prefix="allin1-update-") as temporary:
            staging = Path(temporary)
            for name in checksums:
                source = contained(staging, name)
                source.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as incoming, source.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                if _sha(source) != checksums[name]:
                    raise ValueError(f"staged checksum mismatch: {name}")
            backup.mkdir(parents=True, exist_ok=False)
            for name, digest in originals.items():
                if digest is not None:
                    saved = contained(backup / "files", name)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(targets[name], saved)
                    if _sha(saved) != digest:
                        raise ValueError(f"installation changed while backing up: {name}")
            receipt = {"schema_version": 2, "destination": str(destination),
                       "files": {name: {"before": originals[name], "after": digest} for name, digest in checksums.items()}}
            (backup / "deployed.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            deployed = []
            try:
                for name, path in targets.items():
                    _target(destination, name)
                    if (_sha(path) if path.exists() else None) != originals[name]:
                        raise ValueError(f"installation changed before deployment: {name}")
                    _replace(contained(staging, name), path)
                    deployed.append(name)
            except Exception:
                rollback_update(destination, backup, deployed)
                raise
    return UpdateResult(tuple(deployed), backup)


def rollback_update(destination: Path, backup: Path, deployed: list[str] | None = None) -> tuple[str, ...]:
    destination, backup = no_links(destination), no_links(backup)
    receipt = strict_json(contained(backup, "deployed.json").read_bytes())
    if not isinstance(receipt, dict) or receipt.get("schema_version") != 2:
        raise ValueError("rollback requires a versioned, destination-bound receipt")
    if receipt.get("destination") != str(destination) or not isinstance(receipt.get("files"), dict):
        raise ValueError("rollback receipt belongs to another installation")
    files = receipt["files"]
    unique_paths(list(files))
    selected = list(files) if deployed is None else deployed
    unique_paths(selected)
    if not set(selected).issubset(files):
        raise ValueError("rollback selection is not in its receipt")
    plan = []
    for name, evidence in files.items():
        target, saved = _target(destination, name), _target(backup / "files", name)
        if not isinstance(evidence, dict) or set(evidence) != {"before", "after"}:
            raise ValueError("invalid rollback file evidence")
        before, after = evidence["before"], evidence["after"]
        if not isinstance(after, str) or not SHA256.fullmatch(after) or (before is not None and (not isinstance(before, str) or not SHA256.fullmatch(before))):
            raise ValueError("invalid rollback checksum")
        if before is not None and (not saved.is_file() or _sha(saved) != before):
            raise ValueError(f"rollback backup checksum mismatch: {name}")
        if name in selected:
            if not target.is_file() or _sha(target) != after:
                raise ValueError(f"installation changed since deployment: {name}")
            plan.append((name, target, saved, before))
    # A bad last entry cannot cause an earlier valid entry to be restored/deleted.
    for name, target, saved, before in plan:
        if before is None:
            no_links(target).unlink()
        else:
            _replace(saved, target)
    return tuple(name for name, *_ in plan)
