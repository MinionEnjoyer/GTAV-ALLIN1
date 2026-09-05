"""BattlEye configuration helpers for Story Mode launches.

``commandline.txt`` remains the general GTA command-line configuration. GTA V
Legacy's current Steam/Rockstar handoff chooses ``GTA5_BE.exe`` before that
file is expanded, however, so Legacy also needs the no-BattlEye arguments in
the earlier ``args.txt`` response file.

Uses only stdlib modules -- no extra pip dependencies.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path


log = logging.getLogger("allin1.asi_loader")

_COMMANDLINE_TXT = "commandline.txt"
_LEGACY_ARGS_TXT = "args.txt"
_NOBATTLEYE_FLAG = "-nobattleye"
_LEGACY_NO_BE_ALIAS = "-noBE"
_LEGACY_ARGUMENTS = (_NOBATTLEYE_FLAG, _LEGACY_NO_BE_ALIAS)
_STATE_RELATIVE_PATH = (
    Path("allin1_backups") / "ManagedDependencies" / "story-launch-arguments.json"
)


def ensure_nobattleye(gta_path: Path, is_enhanced: bool) -> str:
    """Install the Story Mode no-BattlEye arguments required by the edition.

    Every edition receives ``-nobattleye`` in ``commandline.txt``. Legacy also
    receives ``-nobattleye -noBE`` in ``args.txt`` so the Rockstar handoff can
    select ``GTA5.exe`` instead of ``GTA5_BE.exe``. Existing arguments are
    preserved and Legacy ``args.txt`` ownership is recorded for safe uninstall.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    game = Path(gta_path)
    commandline_status = _ensure_argument_file(
        game / _COMMANDLINE_TXT, (_NOBATTLEYE_FLAG,), one_per_line=True,
    )
    if is_enhanced:
        return commandline_status

    args_status = _ensure_managed_legacy_args(game)
    if "failed" in (commandline_status, args_status):
        return "failed"
    if "set" in (commandline_status, args_status):
        return "set"
    return "already_set"


def remove_managed_legacy_args(gta_path: Path) -> list[Path]:
    """Remove only Legacy ``args.txt`` tokens recorded as inserted by ALLIN1."""
    game = Path(gta_path)
    args_path = game / _LEGACY_ARGS_TXT
    state_path = game / _STATE_RELATIVE_PATH
    state = _read_state(state_path)
    if state is None:
        return []

    recorded = {
        str(value).casefold() for value in state.get("inserted", [])
    }
    inserted = tuple(
        flag for flag in _LEGACY_ARGUMENTS if flag.casefold() in recorded
    )
    removed_paths: list[Path] = []
    if inserted and args_path.is_file():
        original = args_path.read_bytes().decode("utf-8", errors="replace")
        updated = original
        for flag in inserted:
            updated = _remove_argument_once_preserving_layout(updated, flag)
        if not updated.strip() and state.get("created_file") is True:
            args_path.unlink()
            removed_paths.append(args_path)
        elif updated != original:
            _write_text_atomic(args_path, updated)

    state_path.unlink(missing_ok=True)
    _remove_empty_receipt_parents(state_path, game)
    return removed_paths


def _ensure_managed_legacy_args(game: Path) -> str:
    args_path = game / _LEGACY_ARGS_TXT
    state_path = game / _STATE_RELATIVE_PATH
    if args_path.exists() and not args_path.is_file():
        log.warning("Could not write %s because it is not a file", args_path)
        return "failed"

    original_exists = args_path.is_file()
    try:
        original_bytes = args_path.read_bytes() if original_exists else None
        original = (
            original_bytes.decode("utf-8", errors="replace")
            if original_bytes is not None else ""
        )
        missing = tuple(
            flag for flag in _LEGACY_ARGUMENTS
            if not _argument_pattern(flag).search(original)
        )
        prior = _read_state(state_path)
        prior_inserted = {
            str(value).casefold()
            for value in (prior or {}).get("inserted", [])
        }

        if missing:
            updated = _append_arguments(original, missing)
            _write_text_atomic(args_path, updated)

        state = {
            "schema_version": 1,
            "path": _LEGACY_ARGS_TXT,
            "created_file": bool(
                (prior or {}).get("created_file") is True or not original_exists
            ),
            "inserted": [
                flag for flag in _LEGACY_ARGUMENTS
                if flag.casefold() in prior_inserted or flag in missing
            ],
        }
        try:
            _write_state_atomic(state_path, state)
        except OSError:
            if missing:
                if original_bytes is None:
                    args_path.unlink(missing_ok=True)
                else:
                    _write_bytes_atomic(args_path, original_bytes)
            raise
    except OSError:
        log.warning("Could not manage %s", args_path, exc_info=True)
        return "failed"

    if missing:
        log.info("Wrote %s to %s", " ".join(missing), args_path)
        return "set"
    log.info("%s already contains the Legacy Story Mode arguments", args_path.name)
    return "already_set"


def _ensure_argument_file(
    path: Path, arguments: tuple[str, ...], *, one_per_line: bool,
) -> str:
    try:
        if path.exists() and not path.is_file():
            raise OSError(f"Launch arguments path is not a file: {path}")
        original = (
            path.read_bytes().decode("utf-8", errors="replace")
            if path.is_file() else ""
        )
        missing = tuple(
            flag for flag in arguments
            if not _argument_pattern(flag).search(original)
        )
        if not missing:
            log.info("%s already contains %s", path.name, " ".join(arguments))
            return "already_set"
        updated = _append_arguments(original, missing, one_per_line=one_per_line)
        _write_text_atomic(path, updated)
        log.info("Wrote %s to %s", " ".join(missing), path)
        return "set"
    except OSError:
        log.warning("Could not write %s", path, exc_info=True)
        return "failed"


def _append_arguments(
    text: str, arguments: tuple[str, ...], *, one_per_line: bool = False,
) -> str:
    newline = "\r\n" if "\r\n" in text else "\n"
    separator = newline if one_per_line else " "
    addition = separator.join(arguments)
    if not text:
        return addition + newline
    return text.rstrip("\r\n") + newline + addition + newline


def _argument_pattern(argument: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<!\S){re.escape(argument)}(?!\S)", re.IGNORECASE,
    )


def _remove_argument_once_preserving_layout(text: str, argument: str) -> str:
    match = _argument_pattern(argument).search(text)
    if match is None:
        return text

    line_start = text.rfind("\n", 0, match.start()) + 1
    line_end = text.find("\n", match.end())
    if line_end < 0:
        line_end = len(text)
        newline_end = line_end
    else:
        newline_end = line_end + 1
    line = text[line_start:line_end]
    relative_start = match.start() - line_start
    relative_end = match.end() - line_start
    remainder = line[:relative_start] + line[relative_end:]
    if not remainder.strip():
        return text[:line_start] + text[newline_end:]

    remove_start = match.start()
    remove_end = match.end()
    if remove_start > line_start and text[remove_start - 1] in " \t":
        remove_start -= 1
    elif remove_end < line_end and text[remove_end] in " \t":
        remove_end += 1
    return text[:remove_start] + text[remove_end:]


def _read_state(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("path") != _LEGACY_ARGS_TXT
        or not isinstance(value.get("inserted"), list)
    ):
        return None
    return value


def _write_state_atomic(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(path, json.dumps(state, indent=2) + "\n")


def _write_text_atomic(path: Path, text: str) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"))


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.allin1.tmp")
    try:
        temporary.write_bytes(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_empty_receipt_parents(path: Path, game: Path) -> None:
    parent = path.parent
    stop = game / "allin1_backups"
    while parent != game and parent != stop.parent:
        try:
            parent.rmdir()
        except OSError:
            break
        if parent == stop:
            break
        parent = parent.parent
