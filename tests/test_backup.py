"""Tests for backup and recovery of game files."""

from datetime import datetime
import os
from pathlib import Path
import shutil

import pytest

from allin1 import backup as backup_module
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


def test_mod_store_is_never_discovered_or_restored_as_generic_backup(tmp_path):
    game = tmp_path / "game"
    older = game / "allin1_backups" / "20260101_000000"
    latest = game / "allin1_backups" / "20260102_000000"
    # ``ALLIN1_Backups/Mods`` aliases this root on Windows; use the lexical
    # generic spelling so the disposable regression is portable too.
    mod_store = game / "allin1_backups" / "Mods" / "package" / "receipt"
    older.mkdir(parents=True); latest.mkdir(parents=True); mod_store.mkdir(parents=True)
    (older / "state.txt").write_text("old")
    (latest / "state.txt").write_text("latest")
    (mod_store / "state.txt").write_text("must never restore")

    restore_backup(game)
    assert (game / "state.txt").read_text() == "latest"
    assert list_backups(game) == [latest, older]
    (game / "state.txt").write_text("preserve")
    with pytest.raises(ValueError, match="timestamp snapshot"):
        restore_backup(game, game / "allin1_backups" / "Mods")
    assert (game / "state.txt").read_text() == "preserve"


def test_restore_without_backups_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="No backups found"):
        restore_backup(tmp_path)


def test_restore_with_empty_backups_directory_raises(tmp_path):
    (tmp_path / "allin1_backups").mkdir()
    with pytest.raises(FileNotFoundError, match="No backups found"):
        restore_backup(tmp_path)


def test_restore_rejects_non_directory(tmp_path):
    invalid = tmp_path / "backup.zip"
    invalid.write_bytes(b"not a directory")
    with pytest.raises(FileNotFoundError, match="Backup directory not found"):
        restore_backup(tmp_path, invalid)


def test_list_backups_missing_root_is_empty(tmp_path):
    assert list_backups(tmp_path) == []


def test_backups_created_in_same_clock_tick_do_not_merge(tmp_path, monkeypatch):
    game = tmp_path / "game"
    target = game / "scripts" / "state.toml"
    target.parent.mkdir(parents=True)
    target.write_text("first")

    class FrozenDateTime:
        @staticmethod
        def now():
            return datetime(2026, 1, 2, 3, 4, 5)

    monkeypatch.setattr(backup_module, "datetime", FrozenDateTime)
    first = create_backup(game, [target])
    target.write_text("second")
    second = create_backup(game, [target])

    assert first != second
    target.write_text("changed")
    restore_backup(game, first)
    assert target.read_text() == "first"
    restore_backup(game, second)
    assert target.read_text() == "second"
    target.write_text("changed again")
    restore_backup(game)
    assert target.read_text() == "second"
    assert list_backups(game)[:2] == [second, first]


def test_restore_rejects_backup_outside_managed_backup_root(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    external = tmp_path / "untrusted-backup"
    external.mkdir()
    (external / "value.txt").write_text("untrusted")

    with pytest.raises(ValueError, match="managed backups root"):
        restore_backup(game, external)
    assert not (game / "value.txt").exists()


def test_restore_preflight_rejects_late_parent_file_conflict_without_writes(tmp_path):
    game = tmp_path / "game"
    first = game / "first.txt"
    blocked = game / "mods" / "blocked" / "state.txt"
    blocked.parent.mkdir(parents=True)
    first.write_text("first original")
    blocked.write_text("blocked original")
    backup = create_backup(game, [first, blocked])
    first.write_text("first changed")
    shutil.rmtree(game / "mods")
    (game / "mods").mkdir()
    (game / "mods" / "blocked").write_text("not a directory")

    with pytest.raises(ValueError, match="parent is not a directory"):
        restore_backup(game, backup)

    assert first.read_text() == "first changed"
    assert (game / "mods" / "blocked").read_text() == "not a directory"


def test_restore_preflight_rejects_directory_target_without_writes(tmp_path):
    game = tmp_path / "game"
    first, conflict = game / "first.txt", game / "conflict.txt"
    game.mkdir()
    first.write_text("first original")
    conflict.write_text("conflict original")
    backup = create_backup(game, [first, conflict])
    first.write_text("first changed")
    conflict.unlink()
    conflict.mkdir()

    with pytest.raises(ValueError, match="not a regular file"):
        restore_backup(game, backup)

    assert first.read_text() == "first changed"
    assert conflict.is_dir()


def test_failed_backup_staging_is_not_discoverable_or_restorable(tmp_path, monkeypatch):
    game = tmp_path / "game"
    first, second = game / "first.txt", game / "second.txt"
    game.mkdir()
    first.write_text("first")
    second.write_text("second")
    original_copy = backup_module.shutil.copy2
    calls = 0

    def fail_after_first(source, destination, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated backup copy failure")
        return original_copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(backup_module.shutil, "copy2", fail_after_first)
    with pytest.raises(OSError, match="simulated backup copy failure"):
        create_backup(game, [first, second])

    root = game / backup_module.BACKUP_DIR_NAME
    assert list(root.glob(".*.staging"))
    assert list_backups(game) == []
    with pytest.raises(FileNotFoundError, match="No backups found"):
        restore_backup(game)
    assert first.read_text() == "first"
    assert second.read_text() == "second"


def test_create_rejects_external_and_hardlinked_sources_before_staging(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    external = tmp_path / "outside.txt"
    external.write_text("outside")

    with pytest.raises(ValueError, match="outside the game"):
        create_backup(game, [external])
    assert not (game / backup_module.BACKUP_DIR_NAME).exists()

    source, link = game / "source.txt", game / "source-link.txt"
    source.write_text("source")
    try:
        os.link(source, link)
    except OSError as error:
        pytest.skip(f"filesystem does not support test hard links: {error}")

    with pytest.raises(ValueError, match="Hard-linked"):
        create_backup(game, [link])
    assert not (game / backup_module.BACKUP_DIR_NAME).exists()


def test_restore_rejects_hardlinked_destination_before_writes(tmp_path):
    game = tmp_path / "game"
    target = game / "state.txt"
    game.mkdir()
    target.write_text("original")
    backup = create_backup(game, [target])
    target.unlink()
    external = tmp_path / "external.txt"
    external.write_text("external")
    try:
        os.link(external, target)
    except OSError as error:
        pytest.skip(f"filesystem does not support test hard links: {error}")

    with pytest.raises(ValueError, match="Hard-linked"):
        restore_backup(game, backup)
    assert external.read_text() == target.read_text() == "external"


def test_backup_boundaries_reject_mocked_reparse_source_and_destination(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    target = game / "state.txt"
    target.write_text("original")
    original_no_links = backup_module.no_links

    def reject_source(path):
        if Path(path) == target:
            raise ValueError("Symlink/junction/reparse path is forbidden")
        return original_no_links(path)

    monkeypatch.setattr(backup_module, "no_links", reject_source)
    with pytest.raises(ValueError, match="reparse"):
        create_backup(game, [target])
    assert not (game / backup_module.BACKUP_DIR_NAME).exists()

    monkeypatch.setattr(backup_module, "no_links", original_no_links)
    backup = create_backup(game, [target])
    target.write_text("changed")

    def reject_destination(path):
        if Path(path) == target:
            raise ValueError("Symlink/junction/reparse path is forbidden")
        return original_no_links(path)

    monkeypatch.setattr(backup_module, "no_links", reject_destination)
    with pytest.raises(ValueError, match="reparse"):
        restore_backup(game, backup)
    assert target.read_text() == "changed"
