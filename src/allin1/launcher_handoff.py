"""Narrow, local handoff contract for opening the ALLIN1 Launcher.

The SDK and other trusted desktop tools may ask the Launcher to show a package,
but this boundary intentionally exposes no install, enable, disable, or uninstall
operation.  Those actions remain inside the Launcher and retain their existing
trust confirmation and receipt checks.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


HANDOFF_VERSION = 1
HANDOFF_MAX_AGE_SECONDS = 30.0
HANDOFF_MAX_BYTES = 4096
_PACKAGE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def validate_package_id(value: object) -> str:
    """Return a normalized package ID accepted by the Launcher manifest contract."""
    if not isinstance(value, str):
        raise ValueError("package id must be a string")
    package_id = value.strip().casefold()
    if not _PACKAGE_ID_PATTERN.fullmatch(package_id):
        raise ValueError("package id must be a safe lowercase identifier")
    return package_id


@dataclass(frozen=True)
class LauncherHandoff:
    """A non-mutating request to reveal one Launcher package."""

    request_id: str
    package_id: str | None
    traffic: bool | None
    created_at: float
    version: int = HANDOFF_VERSION
    action: str = "show_packages"

    @classmethod
    def create(
        cls,
        package_id: str | None = None,
        *,
        traffic: bool | None = None,
        now: float | None = None,
    ) -> "LauncherHandoff":
        if traffic is not None and not isinstance(traffic, bool):
            raise ValueError("traffic intent must be true, false, or omitted")
        if traffic is not None and not package_id:
            raise ValueError("traffic intent requires a package id")
        return cls(
            request_id=uuid.uuid4().hex,
            package_id=(validate_package_id(package_id) if package_id else None),
            traffic=traffic,
            created_at=time.time() if now is None else float(now),
        )

    @classmethod
    def from_dict(cls, value: object) -> "LauncherHandoff":
        if not isinstance(value, dict):
            raise ValueError("launcher handoff must be a JSON object")
        allowed = {
            "version", "action", "request_id", "package_id", "traffic", "created_at",
        }
        if set(value) - allowed:
            raise ValueError("launcher handoff contains unsupported fields")
        version = value.get("version")
        if type(version) is not int or version != HANDOFF_VERSION:
            raise ValueError("unsupported launcher handoff version")
        if value.get("action") != "show_packages":
            raise ValueError("unsupported launcher handoff action")
        request_id = str(value.get("request_id") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise ValueError("invalid launcher handoff request id")
        package_value = value.get("package_id")
        package_id = (
            validate_package_id(package_value) if package_value is not None else None
        )
        traffic = value.get("traffic")
        if traffic is not None and not isinstance(traffic, bool):
            raise ValueError("invalid launcher handoff traffic intent")
        if traffic is not None and package_id is None:
            raise ValueError("launcher handoff traffic intent requires a package id")
        created_at = value.get("created_at")
        if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
            raise ValueError("invalid launcher handoff timestamp")
        return cls(request_id, package_id, traffic, float(created_at))

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "action": self.action,
            "request_id": self.request_id,
            "package_id": self.package_id,
            "traffic": self.traffic,
            "created_at": self.created_at,
        }


def launcher_request_root(
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Return the current user's bounded Launcher request inbox."""
    values = os.environ if environment is None else environment
    local_appdata = values.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata).expanduser().resolve(strict=False)
    else:
        base = Path.home().resolve() / ".allin1"
    return base / "ALLIN1" / "Launcher" / "Requests"


def publish_launcher_handoff(
    handoff: LauncherHandoff,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path:
    """Atomically publish a local request for an already-running Launcher."""
    root = launcher_request_root(environment)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{handoff.request_id}.json"
    temporary = root / f".{handoff.request_id}.{uuid.uuid4().hex}.tmp"
    payload = json.dumps(
        handoff.to_dict(), sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > HANDOFF_MAX_BYTES:
        raise ValueError("launcher handoff exceeds its size limit")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def consume_launcher_handoffs(
    *,
    environment: Mapping[str, str] | None = None,
    now: float | None = None,
    max_age_seconds: float = HANDOFF_MAX_AGE_SECONDS,
    limit: int = 16,
) -> tuple[LauncherHandoff, ...]:
    """Consume recent valid requests, discarding malformed or stale files."""
    root = launcher_request_root(environment)
    if not root.is_dir():
        return ()
    current_time = time.time() if now is None else float(now)
    accepted: list[LauncherHandoff] = []
    def queue_order(path: Path) -> tuple[int, str]:
        try:
            return path.stat().st_mtime_ns, path.name
        except OSError:
            return 0, path.name

    for path in sorted(root.glob("*.json"), key=queue_order)[:max(1, limit)]:
        claimed = root / f".{path.stem}.{uuid.uuid4().hex}.claimed"
        try:
            if path.is_symlink():
                continue
            # Rename first so a second reader cannot consume the same request.
            path.replace(claimed)
            if claimed.stat().st_size > HANDOFF_MAX_BYTES:
                continue
            handoff = LauncherHandoff.from_dict(
                json.loads(claimed.read_text(encoding="utf-8")),
            )
            age = current_time - handoff.created_at
            if age < -5.0 or age > max_age_seconds:
                continue
            accepted.append(handoff)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            pass
        finally:
            for consumed in (claimed, path):
                try:
                    consumed.unlink(missing_ok=True)
                except OSError:
                    pass
    return tuple(accepted)


def launcher_process_command(
    handoff: LauncherHandoff,
    *,
    executable: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    """Build an argv-only command that opens or focuses the Launcher."""
    values = os.environ if environment is None else environment
    configured = executable or values.get("ALLIN1_LAUNCHER_EXECUTABLE")
    if configured:
        command = [str(Path(configured).expanduser())]
    else:
        # A frozen Python service is not a GUI entrypoint. Never relaunch the
        # sidecar itself or implicitly import the retired Tk implementation.
        companion = Path(sys.executable).parent.parent / "allin1-launcher-desktop.exe"
        gui_entry = next(
            (
                resolved
                for name in ("allin1-launcher-desktop",)
                if (resolved := shutil.which(name))
            ),
            None,
        )
        if getattr(sys, "frozen", False) and companion.is_file():
            command = [str(companion)]
        elif gui_entry:
            command = [gui_entry]
        else:
            raise ValueError(
                "ALLIN1 Launcher executable was not found; pass --launcher-path "
                "or set ALLIN1_LAUNCHER_EXECUTABLE"
            )
    command.extend(("--workspace", "packages"))
    if handoff.package_id:
        command.extend(("--package-id", handoff.package_id))
    if handoff.traffic is not None:
        command.extend(("--traffic", "on" if handoff.traffic else "off"))
    return command


def open_launcher_packages(
    package_id: str | None = None,
    *,
    traffic: bool | None = None,
    executable: str | Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    """Open/focus Packages through the non-mutating Launcher command route."""
    handoff = LauncherHandoff.create(package_id, traffic=traffic)
    command: Sequence[str] = launcher_process_command(
        handoff, executable=executable, environment=environment,
    )
    return subprocess.Popen(command, close_fds=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
