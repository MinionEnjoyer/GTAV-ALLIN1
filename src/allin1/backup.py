"""Backup and restore game files."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR_NAME = "allin1_backups"


def create_backup(gta_path: Path, files: list[Path]) -> Path:
    """Back up the given files relative to gta_path.

    Returns the backup directory path.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = gta_path / BACKUP_DIR_NAME / timestamp

    for file_path in files:
        if not file_path.exists():
            continue
        relative = file_path.relative_to(gta_path)
        dest = backup_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)

    return backup_dir


def restore_backup(gta_path: Path, backup_dir: Path | None = None) -> list[Path]:
    """Restore files from the most recent (or specified) backup.

    Returns a list of restored file paths.
    """
    backups_root = gta_path / BACKUP_DIR_NAME

    if backup_dir is None:
        if not backups_root.exists():
            raise FileNotFoundError("No backups found.")
        # Pick the most recent backup by directory name (timestamp-sorted)
        dirs = sorted(backups_root.iterdir(), reverse=True)
        if not dirs:
            raise FileNotFoundError("No backups found.")
        backup_dir = dirs[0]

    if not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    restored: list[Path] = []
    for src in backup_dir.rglob("*"):
        if src.is_file():
            relative = src.relative_to(backup_dir)
            dest = gta_path / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            restored.append(dest)

    return restored


def list_backups(gta_path: Path) -> list[Path]:
    """List all available backup directories, newest first."""
    backups_root = gta_path / BACKUP_DIR_NAME
    if not backups_root.exists():
        return []
    return sorted(backups_root.iterdir(), reverse=True)
