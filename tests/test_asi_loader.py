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

    def test_write_failure_returns_failed(self, tmp_path):
        (tmp_path / "commandline.txt").mkdir()

        status = asi_loader.ensure_nobattleye(tmp_path, is_enhanced=True)
        assert status == "failed"
