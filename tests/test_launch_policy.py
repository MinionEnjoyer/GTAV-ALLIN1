import json
from pathlib import Path

import pytest

from allin1.launch_policy import (
    STORY_MODE_ARGUMENT, configure_story_mode_only,
)


def test_enabling_creates_owned_argument_and_disabling_cleans_up(tmp_path: Path):
    enabled = configure_story_mode_only(tmp_path, True)

    assert enabled.changed is True
    assert enabled.ownership == "allin1"
    assert (tmp_path / "commandline.txt").read_text() == f"{STORY_MODE_ARGUMENT}\n"
    state = json.loads(
        (tmp_path / "scripts/.allin1/launch-policy.json").read_text()
    )
    assert state["created_file"] is True

    disabled = configure_story_mode_only(tmp_path, False)

    assert disabled.changed is True
    assert not (tmp_path / "commandline.txt").exists()
    assert not (tmp_path / "scripts/.allin1/launch-policy.json").exists()


def test_owned_argument_preserves_other_options_and_line_endings(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_bytes(b"-windowed\r\n-nobattleye\r\n")

    configure_story_mode_only(tmp_path, True)
    assert commandline.read_bytes() == (
        b"-windowed\r\n-nobattleye\r\n-scofflineonly\r\n"
    )

    configure_story_mode_only(tmp_path, False)
    assert commandline.read_bytes() == b"-windowed\r\n-nobattleye\r\n"


def test_preexisting_argument_is_recognized_but_never_removed(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-windowed -SCOfflineOnly\n", encoding="utf-8")

    enabled = configure_story_mode_only(tmp_path, True)
    disabled = configure_story_mode_only(tmp_path, False)

    assert enabled.changed is False
    assert enabled.ownership == "external"
    assert disabled.argument_present is True
    assert commandline.read_text(encoding="utf-8") == "-windowed -SCOfflineOnly\n"


def test_reconciliation_is_idempotent(tmp_path: Path):
    first = configure_story_mode_only(tmp_path, True)
    second = configure_story_mode_only(tmp_path, True)

    assert first.changed is True
    assert second.changed is False
    assert second.ownership == "allin1"
    assert (tmp_path / "commandline.txt").read_text().count(
        STORY_MODE_ARGUMENT
    ) == 1


def test_disable_without_owned_state_leaves_commandline_untouched(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-windowed\n", encoding="utf-8")

    result = configure_story_mode_only(tmp_path, False)

    assert result.changed is False
    assert result.ownership == "none"
    assert commandline.read_text(encoding="utf-8") == "-windowed\n"


def test_non_directory_and_invalid_commandline_are_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        configure_story_mode_only(tmp_path / "missing", True)

    (tmp_path / "commandline.txt").mkdir()
    with pytest.raises(OSError, match="not a file"):
        configure_story_mode_only(tmp_path, True)


def test_state_write_failure_rolls_back_new_commandline(tmp_path: Path, monkeypatch):
    def fail_state(*_args, **_kwargs):
        raise OSError("state unavailable")

    monkeypatch.setattr("allin1.launch_policy._write_state", fail_state)

    with pytest.raises(OSError, match="state unavailable"):
        configure_story_mode_only(tmp_path, True)

    assert not (tmp_path / "commandline.txt").exists()


def test_state_write_failure_restores_existing_commandline(tmp_path: Path, monkeypatch):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-windowed\n", encoding="utf-8")

    def fail_state(*_args, **_kwargs):
        raise OSError("state unavailable")

    monkeypatch.setattr("allin1.launch_policy._write_state", fail_state)

    with pytest.raises(OSError, match="state unavailable"):
        configure_story_mode_only(tmp_path, True)

    assert commandline.read_text(encoding="utf-8") == "-windowed\n"
