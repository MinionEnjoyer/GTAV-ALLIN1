"""Tests for the BattlEye configuration module."""

from pathlib import Path

import pytest

from allin1 import asi_loader


class TestEnsureNobattleye:
    def test_creates_file_when_missing(self, tmp_path):
        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)

        assert status == "set"
        cmdline = tmp_path / "commandline.txt"
        assert cmdline.exists()
        assert "-nobattleye" in cmdline.read_text()

    def test_already_set(self, tmp_path):
        (tmp_path / "commandline.txt").write_text("-nobattleye\n")

        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)
        assert status == "already_set"

    def test_appends_to_existing_flags(self, tmp_path):
        (tmp_path / "commandline.txt").write_text("-windowed\n")

        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)

        assert status == "set"
        text = (tmp_path / "commandline.txt").read_text()
        assert "-windowed" in text
        assert "-nobattleye" in text
        assert (tmp_path / "args.txt").read_text() == "-nobattleye -noBE\n"

    def test_legacy_args_preserve_existing_options_and_repair_is_idempotent(
        self, tmp_path,
    ):
        (tmp_path / "args.txt").write_text("-windowed\n")

        first = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)
        second = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)

        assert first == "set"
        assert second == "already_set"
        assert (tmp_path / "args.txt").read_text() == (
            "-windowed\n-nobattleye -noBE\n"
        )

    def test_enhanced_does_not_create_legacy_args_file(self, tmp_path):
        assert asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True) == "set"
        assert not (tmp_path / "args.txt").exists()

    def test_uninstall_removes_created_legacy_args_file(self, tmp_path):
        asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)

        removed = asi_loader.remove_managed_legacy_args(tmp_path)

        assert removed == [tmp_path / "args.txt"]
        assert not (tmp_path / "args.txt").exists()

    def test_uninstall_preserves_external_args_and_only_removes_owned_alias(
        self, tmp_path,
    ):
        (tmp_path / "args.txt").write_text("-windowed -nobattleye\n")
        asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)

        asi_loader.remove_managed_legacy_args(tmp_path)

        assert (tmp_path / "args.txt").read_text() == "-windowed -nobattleye\n"

    def test_legacy_args_preserve_existing_crlf_layout(self, tmp_path):
        args = tmp_path / "args.txt"
        args.write_bytes(b"-windowed\r\n")

        asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False)
        assert args.read_bytes() == b"-windowed\r\n-nobattleye -noBE\r\n"

        asi_loader.remove_managed_legacy_args(tmp_path)
        assert args.read_bytes() == b"-windowed\r\n"

    def test_legacy_args_write_failure_returns_failed(self, tmp_path):
        (tmp_path / "args.txt").mkdir()

        assert asi_loader.ensure_nobattleye(tmp_path, is_enhanced=False) == "failed"

    def test_write_failure_returns_failed(self, tmp_path):
        (tmp_path / "commandline.txt").mkdir()

        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)
        assert status == "failed"
