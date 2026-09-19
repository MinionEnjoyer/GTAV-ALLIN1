"""Backup and restore game files."""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from allin1.release_paths import filesystem_path, no_links, tree_files

log = logging.getLogger("allin1.backup")

BACKUP_DIR_NAME = "allin1_backups"
_sequence_lock = threading.Lock()
_last_sequence = 0
_BACKUP_ID = re.compile(
    r"^(?:\d{8}_\d{6}|\d{8}_\d{6}_\d{6}_\d{20}_[0-9a-f]{32})$"
)


def _is_backup_id(name: str) -> bool:
    """Only generic timestamp snapshots are restore authority.

    Windows treats ``allin1_backups`` and ``ALLIN1_Backups`` as the same
    directory.  Package rollback storage below ``Mods`` must therefore never
    appear in generic backup discovery or be explicitly restored as a tree.
    """
    return bool(_BACKUP_ID.fullmatch(name))


def _next_sequence() -> int:
    """Return an in-process monotonic suffix for backup discovery ordering."""
    global _last_sequence
    with _sequence_lock:
        _last_sequence = max(time.monotonic_ns(), _last_sequence + 1)
        return _last_sequence


def create_backup(gta_path: Path, files: list[Path]) -> Path:
    """Back up the given files relative to gta_path.

    Returns the backup directory path.
    """
    game_root = no_links(Path(gta_path).expanduser())
    if not filesystem_path(game_root).is_dir():
        raise FileNotFoundError(f"Game directory not found: {game_root}")
    backups_root = no_links(game_root / BACKUP_DIR_NAME)

    # Validate the complete plan before creating any visible backup.  In
    # particular, a hard link or reparse point must never turn a backup into
    # an authority to read from, or later restore over, another location.
    planned: list[tuple[Path, Path]] = []
    for file_path in files:
        candidate = no_links(Path(file_path).expanduser())
        if not filesystem_path(candidate).exists():
            log.debug("Skipping (does not exist): %s", candidate)
            continue
        if not filesystem_path(candidate).is_file():
            raise ValueError(f"Backup source is not a regular file: {candidate}")
        try:
            relative = candidate.relative_to(game_root)
        except ValueError as exc:
            raise ValueError(f"Backup source is outside the game directory: {candidate}") from exc
        planned.append((candidate, relative))

    filesystem_path(backups_root).mkdir(parents=True, exist_ok=True)
    no_links(backups_root)
    # Seconds-only names caused two backups in one UI action to merge.  The
    # later copy could overwrite the earlier original, making recovery lose
    # the first state.  A private staging directory plus a unique final name
    # prevents both merging and partially-written backups being selected.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = backups_root / f"{timestamp}_{_next_sequence():020d}_{uuid.uuid4().hex}"
    staging_dir = backups_root / f".{backup_dir.name}.staging"
    log.info("Creating backup: %s", backup_dir)

    filesystem_path(staging_dir).mkdir()
    try:
        for file_path, relative in planned:
            dest = no_links(staging_dir / relative)
            disk_dest = filesystem_path(dest)
            disk_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filesystem_path(file_path), disk_dest)
            log.debug("Backed up: %s", relative)
        os.replace(filesystem_path(staging_dir), filesystem_path(backup_dir))
    except Exception:
        # Keep the private, dot-prefixed staging directory for inspection.
        # It is deliberately excluded from discovery and is never selected
        # for automatic restore.
        raise

    return backup_dir


def restore_backup(gta_path: Path, backup_dir: Path | None = None) -> list[Path]:
    """Restore files from the most recent (or specified) backup.

    Returns a list of restored file paths.
    """
    game_root = no_links(Path(gta_path).expanduser())
    if not filesystem_path(game_root).is_dir():
        raise FileNotFoundError(f"Game directory not found: {game_root}")
    backups_root = no_links(game_root / BACKUP_DIR_NAME)

    if backup_dir is None:
        dirs = list_backups(game_root)
        if not dirs:
            log.error("Backups directory is empty: %s", backups_root)
            raise FileNotFoundError("No backups found.")
        backup_dir = dirs[0]
    else:
        candidate = Path(backup_dir).expanduser()
        if not candidate.is_absolute():
            candidate = backups_root / candidate
        backup_dir = no_links(candidate)
        if not filesystem_path(backup_dir).is_dir():
            log.error("Backup directory not found: %s", backup_dir)
            raise FileNotFoundError(f"Backup directory not found: {backup_dir}")
        if backup_dir.parent != backups_root:
            raise ValueError("Backup directory must be directly below the managed backups root")
        if not _is_backup_id(backup_dir.name):
            raise ValueError("Backup directory is not a managed timestamp snapshot")

    if (not filesystem_path(backup_dir).is_dir()
            or not _is_backup_id(backup_dir.name)):
        log.error("Backup directory not found: %s", backup_dir)
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    log.info("Restoring from backup: %s", backup_dir)
    backup_files = tree_files(backup_dir)
    # Validate every destination's complete parent chain before any
    # restoration write. A later directory/file collision must not leave an
    # earlier target restored while the requested backup is only half applied.
    destinations: list[Path] = []
    for relative in backup_files:
        parent = game_root
        for segment in Path(relative).parts[:-1]:
            parent = no_links(parent / segment)
            if (filesystem_path(parent).exists() and
                    not filesystem_path(parent).is_dir()):
                raise ValueError(
                    f"Restore destination parent is not a directory: {parent}")
        # Do this only after the parent walk.  On POSIX, lstat() of a child
        # beneath a file raises NotADirectoryError rather than FileNotFoundError;
        # the preflight above turns that into the intended no-write rejection.
        destination = no_links(game_root / relative)
        if (filesystem_path(destination).exists() and
                not filesystem_path(destination).is_file()):
            raise ValueError(
                f"Restore destination is not a regular file: {destination}")
        destinations.append(destination)

    restored: list[Path] = []
    for (relative, src), dest in zip(backup_files.items(), destinations):
        disk_dest = filesystem_path(dest)
        disk_dest.parent.mkdir(parents=True, exist_ok=True)
        temporary = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.restore")
        try:
            shutil.copy2(filesystem_path(src), filesystem_path(temporary))
            os.replace(filesystem_path(temporary), disk_dest)
        finally:
            filesystem_path(temporary).unlink(missing_ok=True)
        restored.append(dest)
        log.debug("Restored: %s", relative)

    log.info("Restored %d file(s)", len(restored))
    return restored


def list_backups(gta_path: Path) -> list[Path]:
    """List all available backup directories, newest first."""
    game_root = no_links(Path(gta_path).expanduser())
    backups_root = no_links(game_root / BACKUP_DIR_NAME)
    if not filesystem_path(backups_root).exists():
        return []
    if not filesystem_path(backups_root).is_dir():
        raise ValueError(f"Backups root is not a directory: {backups_root}")
    backups: list[Path] = []
    for entry in filesystem_path(backups_root).iterdir():
        if not _is_backup_id(entry.name):
            continue
        try:
            # Keep public return values in the caller's lexical form even
            # though enumeration uses an extended Windows path.
            candidate = no_links(backups_root / entry.name)
        except ValueError:
            continue
        if filesystem_path(candidate).is_dir():
            backups.append(candidate)
    return sorted(backups, reverse=True)
