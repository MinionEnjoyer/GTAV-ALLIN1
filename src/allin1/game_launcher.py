"""Resolve and start a GTA V installation without opening a console window."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


STEAM_APP_IDS = {
    "Legacy": "271590",
    "Enhanced": "3240220",
}


@dataclass(frozen=True)
class LaunchTarget:
    """A storefront URI or local executable used to start GTA V."""

    method: Literal["steam", "executable"]
    location: str
    edition: str

    @property
    def description(self) -> str:
        if self.method == "steam":
            return f"GTA V {self.edition} through Steam"
        return f"GTA V {self.edition} through {Path(self.location).name}"


def resolve_launch_target(gta_path: Path | str) -> LaunchTarget:
    """Choose the safest available launch target for a GTA V directory."""
    game = Path(gta_path).expanduser()
    if not game.is_dir():
        raise FileNotFoundError(f"GTA V folder does not exist: {game}")

    enhanced = game / "GTA5_Enhanced.exe"
    legacy = game / "GTA5.exe"
    if enhanced.is_file():
        edition = "Enhanced"
    elif legacy.is_file():
        edition = "Legacy"
    else:
        raise ValueError(
            f"'{game}' is not launchable. Expected GTA5_Enhanced.exe or GTA5.exe."
        )

    steamapps = _steamapps_directory(game)
    app_id = STEAM_APP_IDS[edition]
    if steamapps is not None and (steamapps / f"appmanifest_{app_id}.acf").is_file():
        return LaunchTarget("steam", f"steam://rungameid/{app_id}", edition)

    play_launcher = game / "PlayGTAV.exe"
    executable = play_launcher if play_launcher.is_file() else enhanced if enhanced.is_file() else legacy
    return LaunchTarget("executable", str(executable), edition)


def launch_gta(
    gta_path: Path | str,
    *,
    uri_opener: Callable[[str], object] | None = None,
    process_starter: Callable[[Path, Path], object] | None = None,
) -> LaunchTarget:
    """Launch GTA V and return the target that was started."""
    target = resolve_launch_target(gta_path)
    game = Path(gta_path).expanduser()
    if target.method == "steam":
        (uri_opener or _open_uri)(target.location)
    else:
        (process_starter or _start_executable)(Path(target.location), game)
    return target


def _steamapps_directory(game: Path) -> Path | None:
    common = game.parent
    steamapps = common.parent
    if common.name.casefold() == "common" and steamapps.name.casefold() == "steamapps":
        return steamapps
    return None


def _open_uri(uri: str) -> None:
    """Open a registered storefront URI using Windows ShellExecute."""
    if not hasattr(os, "startfile"):  # pragma: no cover - launcher targets Windows
        raise OSError("Storefront URI launching is only supported on Windows.")
    os.startfile(uri)  # type: ignore[attr-defined]


def _start_executable(executable: Path, working_directory: Path) -> None:
    """Start the Rockstar game launcher without creating a console window."""
    subprocess.Popen(
        [str(executable)],
        cwd=str(working_directory),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
