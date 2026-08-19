import json
from pathlib import Path

import pytest

from allin1.launch_policy import (
    RETIRED_OFFLINE_ARGUMENT, remove_retired_offline_policy,
)


def _mark_owned(root: Path, *, created_file: bool) -> Path:
    state = root / "scripts/.allin1/launch-policy.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "schema_version": 1,
        "argument": RETIRED_OFFLINE_ARGUMENT,
        "inserted": True,
        "created_file": created_file,
    }), encoding="utf-8")
    return state


def test_cleanup_removes_owned_argument_and_created_file(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text(RETIRED_OFFLINE_ARGUMENT + "\n", encoding="utf-8")
    state = _mark_owned(tmp_path, created_file=True)

    result = remove_retired_offline_policy(tmp_path)

    assert result.changed is True
    assert result.ownership == "none"
    assert not commandline.exists()
    assert not state.exists()


def test_cleanup_preserves_other_options_and_line_endings(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_bytes(
        b"-windowed\r\n-nobattleye\r\n-scofflineonly\r\n"
    )
    _mark_owned(tmp_path, created_file=False)

    result = remove_retired_offline_policy(tmp_path)

    assert result.changed is True
    assert commandline.read_bytes() == b"-windowed\r\n-nobattleye\r\n"


def test_external_argument_is_never_removed(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-windowed -SCOfflineOnly\n", encoding="utf-8")

    result = remove_retired_offline_policy(tmp_path)

    assert result.changed is False
    assert result.ownership == "external"
    assert result.argument_present is True
    assert commandline.read_text(encoding="utf-8") == "-windowed -SCOfflineOnly\n"


def test_invalid_marker_is_discarded_without_changing_arguments(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-scofflineonly\n", encoding="utf-8")
    state = tmp_path / "scripts/.allin1/launch-policy.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"schema_version":2,"inserted":true}', encoding="utf-8")

    result = remove_retired_offline_policy(tmp_path)

    assert result.changed is False
    assert result.ownership == "external"
    assert commandline.exists()
    assert not state.exists()


def test_owned_marker_without_argument_is_cleaned_idempotently(tmp_path: Path):
    commandline = tmp_path / "commandline.txt"
    commandline.write_text("-windowed\n", encoding="utf-8")
    state = _mark_owned(tmp_path, created_file=False)

    first = remove_retired_offline_policy(tmp_path)
    second = remove_retired_offline_policy(tmp_path)

    assert first.changed is False and second.changed is False
    assert commandline.read_text(encoding="utf-8") == "-windowed\n"
    assert not state.exists()


def test_non_directory_and_invalid_commandline_are_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        remove_retired_offline_policy(tmp_path / "missing")

    (tmp_path / "commandline.txt").mkdir()
    with pytest.raises(OSError, match="not a file"):
        remove_retired_offline_policy(tmp_path)
