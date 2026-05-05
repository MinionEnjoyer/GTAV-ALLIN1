"""Backup and restore game files."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

log = logging.getLogger("allin1.backup")

BACKUP_DIR_NAME = "allin1_backups"


def create_backup(gta_path: Path, files: list[Path]) -> Path:
    """Back up the given files relative to gta_path.

    Returns the backup directory path.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = gta_path / BACKUP_DIR_NAME / timestamp
    log.info("Creating backup: %s", backup_dir)

    for file_path in files:
        if not file_path.exists():
            log.debug("Skipping (does not exist): %s", file_path)
            continue
        relative = file_path.relative_to(gta_path)
        dest = backup_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)
        log.debug("Backed up: %s", relative)

    return backup_dir


def restore_backup(gta_path: Path, backup_dir: Path | None = None) -> list[Path]:
    """Restore files from the most recent (or specified) backup.

    Returns a list of restored file paths.
    """
    backups_root = gta_path / BACKUP_DIR_NAME

    if backup_dir is None:
        if not backups_root.exists():
            log.error("No backups directory found at %s", backups_root)
            raise FileNotFoundError("No backups found.")
        # Pick the most recent backup by directory name (timestamp-sorted)
        dirs = sorted(backups_root.iterdir(), reverse=True)
        if not dirs:
            log.error("Backups directory is empty: %s", backups_root)
            raise FileNotFoundError("No backups found.")
        backup_dir = dirs[0]

    if not backup_dir.is_dir():
        log.error("Backup directory not found: %s", backup_dir)
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    log.info("Restoring from backup: %s", backup_dir)
    restored: list[Path] = []
    for src in backup_dir.rglob("*"):
        if src.is_file():
            relative = src.relative_to(backup_dir)
            dest = gta_path / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            restored.append(dest)
            log.debug("Restored: %s", relative)

    log.info("Restored %d file(s)", len(restored))
    return restored


def list_backups(gta_path: Path) -> list[Path]:
    """List all available backup directories, newest first."""
    backups_root = gta_path / BACKUP_DIR_NAME
    if not backups_root.exists():
        return []
    return sorted(backups_root.iterdir(), reverse=True)
