"""Tests for backup and recovery of game files."""

import pytest

from allin1.backup import create_backup, list_backups, restore_backup


def test_create_and_restore_nested_files(tmp_path):
    game = tmp_path / "game"
    target = game / "mods" / "update" / "update.rpf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original")

    backup = create_backup(game, [target, game / "missing.dat"])
    target.write_bytes(b"changed")
    restored = restore_backup(game, backup)

    assert target.read_bytes() == b"original"
    assert restored == [target]


def test_restore_uses_most_recent_backup(tmp_path):
    game = tmp_path / "game"
    first = game / "allin1_backups" / "20260101_000000"
    latest = game / "allin1_backups" / "20260102_000000"
    first.mkdir(parents=True)
    latest.mkdir(parents=True)
    (first / "value.txt").write_text("old")
    (latest / "value.txt").write_text("new")

    restore_backup(game)

    assert (game / "value.txt").read_text() == "new"
    assert list_backups(game) == [latest, first]


def test_restore_without_backups_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="No backups found"):
        restore_backup(tmp_path)


def test_restore_rejects_non_directory(tmp_path):
    invalid = tmp_path / "backup.zip"
    invalid.write_bytes(b"not a directory")
    with pytest.raises(FileNotFoundError, match="Backup directory not found"):
        restore_backup(tmp_path, invalid)


def test_list_backups_missing_root_is_empty(tmp_path):
    assert list_backups(tmp_path) == []
