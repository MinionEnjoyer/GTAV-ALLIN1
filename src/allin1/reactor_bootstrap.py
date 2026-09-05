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
REACTOR_NATIVE_BOOTSTRAP = Path("ReactorV.Bootstrap.asi")
MAX_LOG_BYTES = 1_048_576
MAX_REACTOR_SESSION_LOGS = 16
LOG_CARRY_BYTES = 512
LOG_ANCHOR_BYTES = 128
PROCESS_EXIT_MISS_LIMIT = 2

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
    native_bootstrap: bool = False


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


@dataclass
class IncrementalLogReader:
    """Read only bytes appended after construction, including log rotation.

    The launcher samples startup logs while GTA is doing its heaviest disk
    work.  Keeping a cursor avoids re-reading and decoding up to a megabyte per
    file on every poll.  A short overlap preserves markers split across two
    writes without retaining the whole log in memory.
    """

    path: Path
    offset: int = 0
    identity: tuple[int, int] | None = None
    carry: bytes = b""
    anchor: bytes = b""

    @classmethod
    def after_current_content(cls, path: Path) -> "IncrementalLogReader":
        reader = cls(Path(path))
        reader._reset(to_end=True)
        return reader

    @classmethod
    def from_available_content(cls, path: Path) -> "IncrementalLogReader":
        reader = cls(Path(path))
        reader._reset(to_end=False)
        return reader

    def _reset(self, *, to_end: bool) -> None:
        try:
            status = self.path.stat()
        except OSError:
            self.offset = 0
            self.identity = None
            self.carry = b""
            self.anchor = b""
            return
        self.identity = (int(status.st_dev), int(status.st_ino))
        self.offset = int(status.st_size) if to_end else max(
            0, int(status.st_size) - MAX_LOG_BYTES,
        )
        self.carry = b""
        self.anchor = self._read_anchor(self.offset)

    def _read_anchor(self, offset: int) -> bytes:
        if offset <= 0:
            return b""
        length = min(LOG_ANCHOR_BYTES, offset)
        try:
            with self.path.open("rb") as handle:
                handle.seek(offset - length)
                return handle.read(length)
        except OSError:
            return b""

    def read_new_text(self) -> str:
        try:
            status = self.path.stat()
        except OSError:
            return ""
        identity = (int(status.st_dev), int(status.st_ino))
        size = int(status.st_size)
        content_replaced = (
            bool(self.anchor)
            and size >= self.offset
            and self._read_anchor(self.offset) != self.anchor
        )
        if self.identity != identity or size < self.offset or content_replaced:
            self.identity = identity
            self.offset = max(0, size - MAX_LOG_BYTES)
            self.carry = b""
            self.anchor = self._read_anchor(self.offset)
        elif size == self.offset:
            return ""
        elif size - self.offset > MAX_LOG_BYTES:
            self.offset = size - MAX_LOG_BYTES
            self.carry = b""

        try:
            with self.path.open("rb") as handle:
                handle.seek(self.offset)
                appended = handle.read(MAX_LOG_BYTES)
                self.offset = handle.tell()
        except OSError:
            return ""
        if not appended:
            return ""
        combined = self.carry + appended
        self.carry = combined[-LOG_CARRY_BYTES:]
        self.anchor = self._read_anchor(self.offset)
        return combined.decode("utf-8", errors="replace")


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


def _receipt_contains_file(receipt: object, relative: Path) -> bool:
    """Return whether a receipt claims ownership of ``relative``.

    This is intentionally separate from :func:`_receipt_file_hash`: a package
    that names the native bootstrap but omits its checksum is malformed, while
    an older Reactor package that does not name the ASI at all remains valid.
    """
    if not isinstance(receipt, dict):
        return False
    records = receipt.get("files")
    if not isinstance(records, list):
        return False
    target = relative.as_posix().casefold()
    return any(
        isinstance(record, dict)
        and str(record.get("destination", "")).replace("\\", "/").casefold()
        == target
        for record in records
    )


def _read_reactor_receipt(game: Path) -> dict[str, object] | None:
    from allin1.reactor_dependency import RECEIPT, RELEASES, ROOT_ASIS, _inventory
    # Prefer shared ownership after migration. An invalid shared receipt must
    # not silently fall back to an obsolete managed-package receipt.
    if (game / RECEIPT).exists():
        try:
            shared = _inventory(game, RECEIPT)
            release = RELEASES[(game / "GTA5_Enhanced.exe").is_file()]
            files = shared.get("files", {})
            required = {*ROOT_ASIS, REACTOR_SCRIPT.as_posix(), REACTOR_RUNTIME.as_posix(),
                        REACTOR_UI.as_posix(), REACTOR_PRELOADER.as_posix()}
            if (shared.get("edition") != release.edition
                    or shared.get("archive_sha256") != release.sha256
                    or not required <= files.keys()):
                return None
            # Normalize in memory for the existing read-only validation helpers;
            # this does not recreate the retired package or give it ownership.
            return {"id": REACTOR_PACKAGE_ID, "enabled": True, "shared_dependency": True,
                    "files": [{"destination": name, "sha256": digest} for name, digest in files.items()]}
        except (OSError, ValueError):
            return None
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
    from allin1.reactor_dependency import RECEIPT
    if not receipt_path.is_file() and not (game / RECEIPT).exists():
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

    native_bootstrap = False
    if _receipt_contains_file(receipt, REACTOR_NATIVE_BOOTSTRAP):
        native_hash = _receipt_file_hash(receipt, REACTOR_NATIVE_BOOTSTRAP)
        if native_hash is None:
            return ReactorInstallation(
                False, "The Reactor V native bootstrap receipt is incomplete.",
            )
        native_path = game / REACTOR_NATIVE_BOOTSTRAP
        if not native_path.is_file() or native_path.stat().st_size <= 0:
            return ReactorInstallation(
                False, "The Reactor V native bootstrap is missing.",
            )
        try:
            if _sha256(native_path).casefold() != native_hash:
                return ReactorInstallation(
                    False, "The Reactor V native bootstrap failed validation.",
                )
        except OSError:
            return ReactorInstallation(
                False, "The Reactor V native bootstrap could not be validated.",
            )
        native_bootstrap = True

    logo_path = game / REACTOR_LOGO
    return ReactorInstallation(
        True,
        "Reactor V is ready for startup monitoring.",
        logo_path if logo_path.is_file() else None,
        native_bootstrap,
    )


def start_reactor_preloader(
    gta_path: Path | str,
    *,
    process_starter: Callable[..., _WarmupProcess] = subprocess.Popen,
    installation: ReactorInstallation | None = None,
) -> ReactorPreloaderStart:
    """Start the receipt-validated optional WebView warm-up helper.

    The helper is deliberately optional: an absent, stale, or blocked executable
    must never prevent Story Mode from launching.
    """
    game = Path(gta_path).expanduser()
    installation = installation or inspect_reactor_installation(game)
    if not installation.available:
        return ReactorPreloaderStart(None, installation.reason)
    if installation.native_bootstrap:
        return ReactorPreloaderStart(
            None,
            "Reactor V native bootstrap owns browser warm-up for this launch.",
        )

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
        helper_environment = {
            key: value for key, value in os.environ.items()
            if not key.casefold().startswith("steam")
        }
        process = process_starter(
            [str(preloader), "--wait-for-process", process_name],
            cwd=str(preloader.parent),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=helper_environment,
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


def reactor_session_log_paths() -> tuple[Path, ...]:
    """Return a bounded newest-first view of Reactor's per-process traces."""
    directory = reactor_runtime_log_path().parent
    try:
        candidates: list[tuple[int, Path]] = []
        for path in directory.glob("reactorv-session-*.log"):
            try:
                candidates.append((path.stat().st_mtime_ns, path))
            except OSError:
                # A just-exited helper can remove its transient trace while a
                # poll is enumerating the directory. Keep the remaining logs.
                continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        return tuple(path for _stamp, path in candidates[:MAX_REACTOR_SESSION_LOGS])
    except OSError:
        return ()


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
    readers: dict[str, IncrementalLogReader] = field(init=False)
    reactor_session_readers: dict[Path, IncrementalLogReader] = field(
        default_factory=dict, init=False,
    )
    reactor_runtime_sessions: set[Path] = field(default_factory=set, init=False)
    started_at: float = field(init=False)
    ready: set[str] = field(default_factory=set, init=False)
    process_seen: bool = field(default=False, init=False)
    launch_requested: bool = field(default=False, init=False)
    shv_init_seen: bool = field(default=False, init=False)
    asi_loader_seen: bool = field(default=False, init=False)
    process_missing_samples: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.gta_path = Path(self.gta_path).expanduser()
        self.log_paths = startup_log_paths(self.gta_path)
        self.readers = {
            name: IncrementalLogReader.after_current_content(path)
            for name, path in self.log_paths.items()
        }
        self.reactor_session_readers = {
            path: IncrementalLogReader.after_current_content(path)
            for path in reactor_session_log_paths()
        }
        self.started_at = self.now()

    def _fresh_reactor_session_text(self) -> str:
        fragments: list[str] = []
        for path in reversed(reactor_session_log_paths()):
            reader = self.reactor_session_readers.get(path)
            if reader is None:
                reader = IncrementalLogReader.from_available_content(path)
                self.reactor_session_readers[path] = reader
            fresh = reader.read_new_text()
            if not fresh:
                continue
            if (
                "source=script stage=construction_begin" in fresh
                or path in self.reactor_runtime_sessions
            ):
                self.reactor_runtime_sessions.add(path)
                fragments.append(fresh)
        return "\n".join(fragments)

    def mark_launch_requested(self) -> None:
        self.launch_requested = True
        self.ready.add("launch")

    def sample(self, *, process_running: bool) -> BootstrapState:
        """Poll startup facts without mutating files or invoking game code."""
        if process_running:
            self.process_seen = True
            self.process_missing_samples = 0
        elif self.process_seen:
            self.process_missing_samples += 1

        texts = {
            name: reader.read_new_text()
            for name, reader in self.readers.items()
        }
        asi = texts["asi"]
        shv = texts["shv"]
        shvdn = texts["shvdn"]
        reactor = "\n".join(
            part for part in (
                texts["reactor"], self._fresh_reactor_session_text(),
            ) if part
        )
        preloader = texts["preloader"]

        if "stage=webview_warm_cache_released" in preloader:
            self.ready.add("warmup")

        if "INIT: Success" in shv:
            self.shv_init_seen = True
        if (
            "LOADER: Finished loading *.asi plugins" in asi
            or "ScriptHookVDotNet.asi" in asi
        ):
            self.asi_loader_seen = True
        if self.shv_init_seen and self.asi_loader_seen:
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
        if story_mode_ready and (runtime_ready or "reactor" in self.ready):
            self.ready.update(
                ("native", "assets", "dotnet", "reactor", "story"),
            )

        failure = None
        terminal = False
        if "webview_navigation_completed success=False" in reactor:
            failure = "Reactor V could not open its interface."
            terminal = True
        elif (
            self.process_seen
            and not process_running
            and self.process_missing_samples >= PROCESS_EXIT_MISS_LIMIT
            and "story" not in self.ready
        ):
            failure = "GTA V closed before Story Mode became ready."
            terminal = True
        elif self.now() - self.started_at >= self.hard_timeout_seconds:
            failure = "Reactor V startup verification timed out."
            terminal = True

        return BootstrapState(
            frozenset(self.ready), failure, terminal, self.process_seen,
        )
