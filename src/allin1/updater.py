"""Checksum-verified transactional release deployment and rollback."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class UpdateResult:
    deployed: tuple[str, ...]
    backup: Path


def package_release(output: Path, root: Path, files: list[Path]) -> Path:
    """Create a deterministic updater archive with a SHA-256 manifest."""
    checksums: dict[str, str] = {}
    relative_files: list[tuple[str, Path]] = []
    for path in files:
        source = path if path.is_absolute() else root / path
        if not source.is_file():
            raise FileNotFoundError(source)
        relative = source.relative_to(root).as_posix()
        checksums[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
        relative_files.append((relative, source))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, source in sorted(relative_files):
            info = zipfile.ZipInfo(relative, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
        archive.writestr("checksums.json", json.dumps(checksums, indent=2, sort_keys=True))
    return output


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = []
    for item in archive.infolist():
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe archive member: {item.filename}")
        members.append(item)
    return members


def _load_checksums(root: Path) -> dict[str, str]:
    path = root / "checksums.json"
    if not path.is_file():
        raise ValueError("release is missing checksums.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("checksums.json must be an object")
    return {str(name): str(value).lower() for name, value in raw.items()}


def deploy_release(archive_path: Path, destination: Path, backup_root: Path) -> UpdateResult:
    """Verify every declared release file, then deploy with rollback on failure."""
    backup = backup_root / "previous"
    with tempfile.TemporaryDirectory(prefix="allin1-update-") as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(staging, members=_safe_members(archive))
        checksums = _load_checksums(staging)
        for relative, expected in checksums.items():
            source = staging / relative
            if not source.is_file():
                raise ValueError(f"release file is missing: {relative}")
            actual = hashlib.sha256(source.read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"checksum mismatch: {relative}")
        if backup.exists():
            shutil.rmtree(backup)
        backup.mkdir(parents=True)
        deployed: list[str] = []
        try:
            for relative in checksums:
                source, target = staging / relative, destination / relative
                if target.exists():
                    saved = backup / relative
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary_target = target.with_suffix(target.suffix + ".update")
                shutil.copy2(source, temporary_target)
                temporary_target.replace(target)
                deployed.append(relative)
        except Exception:
            rollback_update(destination, backup, deployed)
            raise
    (backup / "deployed.json").write_text(json.dumps(deployed, indent=2), encoding="utf-8")
    return UpdateResult(tuple(deployed), backup)


def rollback_update(destination: Path, backup: Path, deployed: list[str] | None = None) -> tuple[str, ...]:
    if deployed is None:
        marker = backup / "deployed.json"
        if not marker.is_file():
            raise FileNotFoundError(marker)
        deployed = list(json.loads(marker.read_text(encoding="utf-8")))
    restored = []
    for relative in deployed:
        target, saved = destination / relative, backup / relative
        if saved.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, target)
        else:
            target.unlink(missing_ok=True)
        restored.append(relative)
    return tuple(restored)
