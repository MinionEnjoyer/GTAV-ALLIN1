"""One-way cleanup for the retired 0.5.0 offline launch experiment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


RETIRED_OFFLINE_ARGUMENT = "-scofflineonly"
_ARGUMENT_PATTERN = re.compile(
    rf"(?<!\S){re.escape(RETIRED_OFFLINE_ARGUMENT)}(?!\S)", re.IGNORECASE,
)
_STATE_RELATIVE_PATH = Path("scripts") / ".allin1" / "launch-policy.json"


@dataclass(frozen=True)
class LaunchPolicyCleanupResult:
    """Describe cleanup of an ALLIN1-owned retired launch argument."""

    changed: bool
    argument_present: bool
    ownership: str


def remove_retired_offline_policy(
    gta_path: Path | str,
) -> LaunchPolicyCleanupResult:
    """Remove only the offline argument previously inserted by ALLIN1.

    The retired experiment recorded ownership in ``launch-policy.json``. An
    argument without that valid marker belongs to the player or another tool
    and is never changed.
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
    owned = bool(
        state
        and state.get("inserted") is True
        and str(state.get("argument", "")).casefold()
        == RETIRED_OFFLINE_ARGUMENT.casefold()
    )
    argument_present = bool(_ARGUMENT_PATTERN.search(original))

    if not owned:
        state_path.unlink(missing_ok=True)
        return LaunchPolicyCleanupResult(
            False, argument_present,
            "external" if argument_present else "none",
        )

    updated, removed = _remove_owned_argument(original)
    if removed:
        if not updated and bool(state.get("created_file")):
            commandline.unlink(missing_ok=True)
        else:
            _write_commandline(commandline, updated)
    state_path.unlink(missing_ok=True)
    return LaunchPolicyCleanupResult(
        removed, bool(_ARGUMENT_PATTERN.search(updated)), "none",
    )


def _remove_owned_argument(text: str) -> tuple[str, bool]:
    lines = text.splitlines(keepends=True)
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].strip().casefold() == RETIRED_OFFLINE_ARGUMENT.casefold():
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


def _write_commandline(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.allin1.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
