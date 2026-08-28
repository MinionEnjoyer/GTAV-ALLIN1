"""Read-only startup monitoring for the launcher-owned Reactor V bootstrap."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol


REACTOR_PACKAGE_ID = "ragewebui.framework"
REACTOR_SCRIPT = Path("scripts/ReactorV/RageWebUI.Script.dll")
REACTOR_RUNTIME = Path("plugins/ReactorV/RageWebUI.Runtime.dll")
REACTOR_CONFIG = Path("scripts/ReactorV/ReactorV.json")
REACTOR_UI = Path("plugins/ReactorV/ui/index.html")
REACTOR_LOGO = Path("plugins/ReactorV/ui/ragewebui-logo.png")
REACTOR_PRELOADER = Path("plugins/ReactorV/ReactorV.Preloader.exe")
MAX_LOG_BYTES = 1_048_576

MILESTONE_LABELS: tuple[tuple[str, str], ...] = (
    ("launch", "Story Mode requested"),
    ("warmup", "Reactor interface preloaded"),
    ("native", "Native extensions loaded"),
    ("assets", "Story assets initialized"),
    ("dotnet", "ScriptHookVDotNet ready"),
    ("reactor", "Reactor V ready"),
    ("story", "Story Mode ready"),
)


@dataclass(frozen=True)
class ReactorInstallation:
    """Validated files needed to show and hand off the Reactor splash."""

    available: bool
    reason: str
    logo_path: Path | None = None


class _WarmupProcess(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...


@dataclass
class ReactorPreloaderStart:
    """Fail-soft result for the optional browser warm-up helper."""

    process: _WarmupProcess | None
    reason: str

    @property
    def started(self) -> bool:
        return self.process is not None

    def stop(self) -> None:
        """Stop only the helper started for a launch that subsequently failed."""
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
        except OSError:
            pass


@dataclass(frozen=True)
class LogBaseline:
    """Bounded content captured before a launch request."""

    content: bytes = b""


@dataclass(frozen=True)
class BootstrapState:
    """Monotonic startup state returned to the visual bootstrap."""

    ready: frozenset[str]
    failure: str | None = None
    terminal: bool = False
    process_seen: bool = False

    @property
    def reactor_ready(self) -> bool:
        return "reactor" in self.ready

    @property
    def story_ready(self) -> bool:
        return "story" in self.ready


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _receipt_file_hash(receipt: object, relative: Path) -> str | None:
    if not isinstance(receipt, dict):
        return None
    records = receipt.get("files")
    if not isinstance(records, list):
        return None
    target = relative.as_posix().casefold()
    for record in records:
        if not isinstance(record, dict):
            continue
        destination = str(record.get("destination", "")).replace("\\", "/")
        if destination.casefold() != target:
            continue
        checksum = record.get("sha256")
        if isinstance(checksum, str) and len(checksum) == 64:
            return checksum.casefold()
        return None
    return None


def _read_reactor_receipt(game: Path) -> dict[str, object] | None:
    receipt_path = (
        game / "scripts" / ".allin1" / "mods" / f"{REACTOR_PACKAGE_ID}.json"
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return receipt if isinstance(receipt, dict) else None


def inspect_reactor_installation(gta_path: Path | str) -> ReactorInstallation:
    """Fail closed unless the enabled receipt and critical runtime files agree."""
    game = Path(gta_path).expanduser()
    receipt_path = (
        game / "scripts" / ".allin1" / "mods" / f"{REACTOR_PACKAGE_ID}.json"
    )
    if not receipt_path.is_file():
        return ReactorInstallation(False, "Reactor V is not installed.")
    receipt = _read_reactor_receipt(game)
    if receipt is None:
        return ReactorInstallation(False, "The Reactor V install receipt is unreadable.")
    if receipt.get("id") != REACTOR_PACKAGE_ID:
        return ReactorInstallation(False, "The Reactor V install receipt is invalid.")
    if receipt.get("enabled") is not True:
        return ReactorInstallation(False, "Reactor V is disabled.")

    expected_hash = _receipt_file_hash(receipt, REACTOR_SCRIPT)
    if expected_hash is None:
        return ReactorInstallation(False, "The Reactor V script receipt is incomplete.")

    script_path = game / REACTOR_SCRIPT
    required = (
        script_path,
        game / REACTOR_RUNTIME,
        game / REACTOR_CONFIG,
        game / REACTOR_UI,
    )
    if any(not path.is_file() or path.stat().st_size <= 0 for path in required):
        return ReactorInstallation(False, "The Reactor V runtime is incomplete.")
    try:
        if _sha256(script_path).casefold() != expected_hash:
            return ReactorInstallation(False, "The Reactor V script failed validation.")
    except OSError:
        return ReactorInstallation(False, "The Reactor V script could not be validated.")

    logo_path = game / REACTOR_LOGO
    return ReactorInstallation(
        True,
        "Reactor V is ready for startup monitoring.",
        logo_path if logo_path.is_file() else None,
    )


def start_reactor_preloader(
    gta_path: Path | str,
    *,
    process_starter: Callable[..., _WarmupProcess] = subprocess.Popen,
) -> ReactorPreloaderStart:
    """Start the receipt-validated optional WebView warm-up helper.

    The helper is deliberately optional: an absent, stale, or blocked executable
    must never prevent Story Mode from launching.
    """
    game = Path(gta_path).expanduser()
    installation = inspect_reactor_installation(game)
    if not installation.available:
        return ReactorPreloaderStart(None, installation.reason)

    receipt = _read_reactor_receipt(game)
    expected_hash = _receipt_file_hash(receipt, REACTOR_PRELOADER)
    preloader = game / REACTOR_PRELOADER
    if expected_hash is None:
        return ReactorPreloaderStart(
            None, "Reactor V browser warm-up is not included in this installation.",
        )
    if not preloader.is_file() or preloader.stat().st_size <= 0:
        return ReactorPreloaderStart(
            None, "Reactor V browser warm-up executable is missing.",
        )
    try:
        if _sha256(preloader).casefold() != expected_hash:
            return ReactorPreloaderStart(
                None, "Reactor V browser warm-up failed receipt validation.",
            )
    except OSError:
        return ReactorPreloaderStart(
            None, "Reactor V browser warm-up could not be validated.",
        )

    if (game / "GTA5_Enhanced.exe").is_file():
        process_name = "GTA5_Enhanced.exe"
    elif (game / "GTA5.exe").is_file():
        process_name = "GTA5.exe"
    else:
        return ReactorPreloaderStart(None, "The GTA V executable could not be found.")

    try:
        process = process_starter(
            [str(preloader), "--wait-for-process", process_name],
            cwd=str(preloader.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return ReactorPreloaderStart(
            None, f"Reactor V browser warm-up could not start: {exc}",
        )
    return ReactorPreloaderStart(process, "Reactor V browser warm-up started.")


def _read_bounded(path: Path, limit: int = MAX_LOG_BYTES) -> bytes:
    """Read at most the newest ``limit`` bytes of a changing log."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit)
    except OSError:
        return b""


def capture_log_baselines(paths: Mapping[str, Path]) -> dict[str, LogBaseline]:
    """Capture stale log content so it cannot satisfy a new launch."""
    return {name: LogBaseline(_read_bounded(path)) for name, path in paths.items()}


def fresh_log_text(path: Path, baseline: LogBaseline) -> str:
    """Return only content written after a baseline, including replaced logs."""
    current = _read_bounded(path)
    previous = baseline.content
    if current == previous:
        return ""
    if previous and current.startswith(previous):
        current = current[len(previous):]
    return current.decode("utf-8", errors="replace")


def reactor_runtime_log_path() -> Path:
    """Return the per-user Reactor runtime log used for the final handoff."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "ReactorV" / "reactorv-runtime.log"
    return Path.home() / "AppData" / "Local" / "ReactorV" / "reactorv-runtime.log"


def reactor_preloader_log_path() -> Path:
    """Return the hidden browser warm-up log monitored by the launcher."""
    return reactor_runtime_log_path().with_name("reactorv-preloader.log")


def startup_log_paths(gta_path: Path | str) -> dict[str, Path]:
    game = Path(gta_path).expanduser()
    return {
        "asi": game / "asiloader.log",
        "shv": game / "ScriptHookV.log",
        "shvdn": game / "ScriptHookVDotNet.log",
        "reactor": reactor_runtime_log_path(),
        "preloader": reactor_preloader_log_path(),
    }


@dataclass
class ReactorStartupMonitor:
    """Turn fresh GTA/Reactor logs into a monotonic startup timeline."""

    gta_path: Path
    hard_timeout_seconds: float = 300.0
    now: Callable[[], float] = time.monotonic
    log_paths: dict[str, Path] = field(init=False)
    baselines: dict[str, LogBaseline] = field(init=False)
    started_at: float = field(init=False)
    ready: set[str] = field(default_factory=set, init=False)
    process_seen: bool = field(default=False, init=False)
    launch_requested: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.gta_path = Path(self.gta_path).expanduser()
        self.log_paths = startup_log_paths(self.gta_path)
        self.baselines = capture_log_baselines(self.log_paths)
        self.started_at = self.now()

    def mark_launch_requested(self) -> None:
        self.launch_requested = True
        self.ready.add("launch")

    def sample(self, *, process_running: bool) -> BootstrapState:
        """Poll startup facts without mutating files or invoking game code."""
        if process_running:
            self.process_seen = True

        texts = {
            name: fresh_log_text(path, self.baselines[name])
            for name, path in self.log_paths.items()
        }
        asi = texts["asi"]
        shv = texts["shv"]
        shvdn = texts["shvdn"]
        reactor = texts["reactor"]
        preloader = texts["preloader"]

        if "stage=webview_warm_cache_released" in preloader:
            self.ready.add("warmup")

        if (
            "INIT: Success" in shv
            and (
                "LOADER: Finished loading *.asi plugins" in asi
                or "ScriptHookVDotNet.asi" in asi
            )
        ):
            self.ready.add("native")
        if "CORE: Creating threads" in shv or "CORE: Launching main()" in shv:
            self.ready.update(("native", "assets"))
        if "Loading scripts from" in shvdn:
            self.ready.update(("native", "assets", "dotnet"))
        script_started = "Started script RageWebUI.Script.RageWebUiScript." in shvdn
        runtime_ready = (
            "webview_navigation_completed success=True" in reactor
            or "directx_ready" in reactor.casefold()
            or "ready renderer=DirectX" in reactor
        )
        if script_started:
            self.ready.update(("native", "assets", "dotnet"))
        if runtime_ready:
            self.ready.update(("native", "assets", "dotnet", "reactor"))
        story_mode_ready = "story_mode_ready" in reactor.casefold()
        if runtime_ready and story_mode_ready:
            self.ready.update(
                ("native", "assets", "dotnet", "reactor", "story"),
            )

        failure = None
        terminal = False
        if "webview_navigation_completed success=False" in reactor:
            failure = "Reactor V could not open its interface."
            terminal = True
        elif self.process_seen and not process_running and "story" not in self.ready:
            failure = "GTA V closed before Story Mode became ready."
            terminal = True
        elif self.now() - self.started_at >= self.hard_timeout_seconds:
            failure = "Reactor V startup verification timed out."
            terminal = True

        return BootstrapState(
            frozenset(self.ready), failure, terminal, self.process_seen,
        )
