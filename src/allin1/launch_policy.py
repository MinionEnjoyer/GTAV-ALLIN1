"""Reversible launch policies owned by the ALLIN1 desktop launcher."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


STORY_MODE_ARGUMENT = "-scofflineonly"
_ARGUMENT_PATTERN = re.compile(
    rf"(?<!\S){re.escape(STORY_MODE_ARGUMENT)}(?!\S)", re.IGNORECASE,
)
_STATE_RELATIVE_PATH = Path("scripts") / ".allin1" / "launch-policy.json"


@dataclass(frozen=True)
class StoryModePolicyResult:
    """Describe the effective launch policy after reconciliation."""

    enabled: bool
    argument_present: bool
    changed: bool
    ownership: str


def configure_story_mode_only(
    gta_path: Path | str, enabled: bool,
) -> StoryModePolicyResult:
    """Add or remove ALLIN1's owned Story Mode-only launch argument.

    Existing launch arguments are preserved byte-for-byte except for the
    standalone argument line that ALLIN1 added. If the player already owns a
    ``-scofflineonly`` argument, ALLIN1 recognizes it but never removes it.
    """
    game = Path(gta_path).expanduser()
    if not game.is_dir():
        raise FileNotFoundError(f"GTA V folder does not exist: {game}")

    commandline = game / "commandline.txt"
    state_path = game / _STATE_RELATIVE_PATH
    original_exists = commandline.exists()
    if original_exists and not commandline.is_file():
        raise OSError(f"Launch arguments path is not a file: {commandline}")
    original = (
        commandline.read_text(encoding="utf-8-sig", errors="replace")
        if original_exists else ""
    )
    state = _read_state(state_path)
    owned = bool(state and state.get("inserted"))
    argument_present = bool(_ARGUMENT_PATTERN.search(original))

    if enabled:
        if argument_present:
            return StoryModePolicyResult(
                True, True, False, "allin1" if owned else "external",
            )
        updated = _append_argument(original)
        _write_commandline(commandline, updated)
        try:
            _write_state(state_path, created_file=not original_exists)
        except OSError:
            _restore_commandline(commandline, original, original_exists)
            raise
        return StoryModePolicyResult(True, True, True, "allin1")

    if not owned:
        state_path.unlink(missing_ok=True)
        return StoryModePolicyResult(
            False, argument_present, False,
            "external" if argument_present else "none",
        )

    updated, removed = _remove_owned_argument(original)
    if removed:
        if not updated and bool(state.get("created_file")):
            commandline.unlink(missing_ok=True)
        else:
            _write_commandline(commandline, updated)
    state_path.unlink(missing_ok=True)
    return StoryModePolicyResult(
        False, bool(_ARGUMENT_PATTERN.search(updated)), removed, "none",
    )


def _append_argument(text: str) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    separator = "" if not text or text.endswith(("\r", "\n")) else newline
    return f"{text}{separator}{STORY_MODE_ARGUMENT}{newline}"


def _remove_owned_argument(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip().casefold() == STORY_MODE_ARGUMENT.casefold():
            del lines[index]
            return "".join(lines), True
    return text, False


def _read_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return None
    return value


def _write_state(path: Path, *, created_file: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "argument": STORY_MODE_ARGUMENT,
        "inserted": True,
        "created_file": created_file,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_commandline(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.allin1.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _restore_commandline(path: Path, text: str, existed: bool) -> None:
    if existed:
        _write_commandline(path, text)
    else:
        path.unlink(missing_ok=True)
