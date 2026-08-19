"""Subprocess helpers shared by desktop repair and packaging workflows."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def hidden_process_options() -> dict[str, Any]:
    """Return platform-safe options that prevent helper console windows."""
    options: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    return options


def run_hidden(
    command: Sequence[str | Path], **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a helper process without flashing a console on Windows."""
    for key, value in hidden_process_options().items():
        kwargs.setdefault(key, value)
    normalized = [str(part) for part in command]
    try:
        return subprocess.run(normalized, **kwargs)
    except OSError as exc:
        # Windows Application Control can reject an unsigned .NET apphost while
        # still allowing the same managed assembly through the installed dotnet
        # host (WinError 4551). Keep this narrowly scoped to ALLIN1's helper.
        executable = Path(normalized[0]) if normalized else None
        managed = executable.with_suffix(".dll") if executable else None
        dotnet = shutil.which("dotnet")
        if (
            getattr(exc, "winerror", None) == 4551
            and executable is not None
            and executable.name.casefold() == "rpfpatcher.exe"
            and managed is not None
            and managed.is_file()
            and dotnet
        ):
            return subprocess.run(
                [dotnet, str(managed), *normalized[1:]], **kwargs,
            )
        raise
