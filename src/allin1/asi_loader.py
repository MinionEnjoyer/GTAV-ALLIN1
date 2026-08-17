"""BattlEye configuration helper.

Writes ``-nobattleye`` to ``commandline.txt`` in the GTA V root as a
belt-and-suspenders measure.  The primary BattlEye bypass is the runtime
injector (ALLIN1-Launcher.exe), which sidesteps BattlEye entirely by
injecting after the game has started.

Uses only stdlib modules — no extra pip deps.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("allin1.asi_loader")

_COMMANDLINE_TXT = "commandline.txt"
_NOBATTLEYE_FLAG = "-nobattleye"


def ensure_nobattleye(gta_path: Path, is_enhanced: bool) -> str:
    """Write ``-nobattleye`` to ``commandline.txt`` in the game root.

    Returns ``"set"``, ``"already_set"``, or ``"failed"``.
    """
    cmdline_path = gta_path / _COMMANDLINE_TXT
    try:
        if cmdline_path.exists():
            text = cmdline_path.read_text(encoding="utf-8", errors="replace")
            if _NOBATTLEYE_FLAG in text:
                log.info("commandline.txt already contains %s", _NOBATTLEYE_FLAG)
                return "already_set"
            text = text.rstrip("\n")
            new_text = f"{text}\n{_NOBATTLEYE_FLAG}\n" if text else f"{_NOBATTLEYE_FLAG}\n"
        else:
            new_text = f"{_NOBATTLEYE_FLAG}\n"

        cmdline_path.write_text(new_text, encoding="utf-8")
        log.info("Wrote %s to %s", _NOBATTLEYE_FLAG, cmdline_path)
        return "set"
    except OSError:
        log.warning("Could not write %s", cmdline_path, exc_info=True)
        return "failed"
