"""Versioned stdio host for the Tauri Launcher; never imports Tkinter."""
from __future__ import annotations
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys
from queue import Full, Queue
from threading import Event, Lock, Thread
from allin1.desktop_service import LauncherService, serializable
from allin1.release_paths import strict_json
from allin1.runtime_resources import frozen_identity

MAX_REQUEST = 1024 * 1024
HEARTBEAT_SECONDS = 15
OPERATIONS = frozenset({
    "catalog", "inspect", "review", "apply", "load_profile", "health",
    "check_update", "read_garages", "check_sdk_update", "startup_status", "shutdown", "open_activity_folder", "open_launcher_release", "cancel_launch", "set_preview_workers",
})


@contextlib.contextmanager
def progress_frames(service, request_id, send, interval):
    """Liveness is not advancement; stop/join before sending the terminal frame."""
    stopped, emission_lock = Event(), Lock()
    last = (None, "Waiting for the launcher service")
    connected = True

    def emit(heartbeat=False):
        nonlocal connected
        if not connected:
            return
        control = getattr(service, "launch_cancellation", None)
        previews = getattr(service, "preview_render_control", None)
        work = getattr(service, "rpf_progress", None)
        snapshot = work.snapshot() if work is not None else None
        try:
            send(request_id, "progress", {"schema_version": 1, "event": "launcher.progress",
                 "percentage": last[0], "message": last[1], **({"heartbeat": True} if heartbeat else {}),
                 **(control.status() if control else {}),
                 **({"preview_render": previews.status()} if previews else {}),
                 **({"rpf_work": snapshot} if snapshot is not None else {})})
        except OSError:
            # Losing a progress consumer must not abort/roll back an archive write.
            connected = False
            stopped.set()

    def progress(percentage, message):
        nonlocal last
        with emission_lock:
            last = (percentage, message)
            emit()

    def heartbeat():
        while not stopped.wait(interval):
            with emission_lock:
                emit(heartbeat=True)

    service.progress = progress
    ticker = Thread(target=heartbeat, name="launcher-heartbeat")
    ticker.start()
    try:
        yield
    finally:
        stopped.set()
        ticker.join()


def serve(service, incoming, outgoing, *, heartbeat_interval=HEARTBEAT_SECONDS):
    if heartbeat_interval <= 0:
        raise ValueError("Heartbeat interval must be positive")
    output_lock = Lock()
    def send(request_id, kind, payload):
        message = json.dumps({"schema_version": 1, "request_id": request_id, "kind": kind, "payload": serializable(payload)}, allow_nan=False)
        if len(message.encode()) > 4 * 1024**2: raise ValueError("Launcher response exceeds 4 MiB")
        with output_lock:
            outgoing.write(message + "\n"); outgoing.flush()

    # Keep ordinary requests strictly serialized. The input thread may only
    # signal review-scoped cancellation/scheduling; it cannot run a second mutation.
    pending = Queue(maxsize=1)
    def execute():
        while (request := pending.get()) is not None:
            request_id, operation, payload = request
            try:
                if operation == "protocol_error":
                    send(request_id, "error", payload)
                    continue
                with progress_frames(service, request_id, send, heartbeat_interval), contextlib.redirect_stdout(sys.stderr):
                    if operation == "shutdown": result = {"closed": True}
                    elif operation == "review": result = service.review(payload)
                    elif operation == "apply": result = service.apply(payload)
                    else: result = service.read(operation, payload)
                send(request_id, "result", result)
            except Exception as error:
                try: send(request_id, "error", {"message": str(error), "error_type": type(error).__name__})
                except OSError: return  # Disconnected output must not strand the bounded input queue.
    worker = Thread(target=execute, name="launcher-operations")
    worker.start()
    def enqueue(request):
        while worker.is_alive():
            try:
                pending.put(request, timeout=.1)
                return
            except Full: pass
        raise RuntimeError("Launcher operation worker disconnected")
    try:
        while True:
            line = incoming.readline(MAX_REQUEST + 1)
            if not line: break
            if len(line.encode()) > MAX_REQUEST or not line.endswith("\n"): break
            request_id = operation = None
            try:
                request = strict_json(line)
                if not isinstance(request, dict) or set(request) != {"schema_version", "request_id", "operation", "payload"} or type(request["schema_version"]) is not int or request["schema_version"] != 1:
                    raise ValueError("Invalid Launcher protocol envelope")
                request_id = request["request_id"]
                if not isinstance(request_id, str) or not 1 <= len(request_id) <= 96: raise ValueError("Invalid request identity")
                payload = request["payload"]
                if not isinstance(payload, dict): raise ValueError("Payload must be an object")
                operation = request["operation"]
                if not isinstance(operation, str) or operation not in OPERATIONS:
                    raise ValueError("Invalid Launcher operation")
                if operation == "cancel_launch":
                    send(request_id, "result", service.cancel_launch(payload))
                elif operation == "set_preview_workers":
                    send(request_id, "result", service.set_preview_workers(payload))
                else:
                    enqueue((request_id, operation, payload))
                    if operation == "shutdown": break
            except Exception as error:
                payload = {"message": str(error), "error_type": type(error).__name__}
                if operation in ("cancel_launch", "set_preview_workers"): send(request_id, "error", payload)
                else: enqueue((request_id, "protocol_error", payload))
    finally:
        if worker.is_alive(): enqueue(None)
        worker.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--allow-game-writes", action="store_true")
    parser.add_argument("--allow-launch", action="store_true")
    parser.add_argument("--expected-build-id")
    args = parser.parse_args()
    identity = frozen_identity(args.project_root)
    if args.expected_build_id and (identity is None or identity["build_id"] != args.expected_build_id):
        raise ValueError("Launcher shell and service build identities disagree")
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"): stream.reconfigure(encoding="utf-8")
    state = args.state_root or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ALLIN1" / "Launcher"
    from allin1.sdk_manager import default_sdk_root
    from allin1.mods import default_package_library_root
    from allin1.assistant_manager import default_assistant_root
    sdk_root = None if args.state_root else default_sdk_root()
    service = LauncherService(args.project_root, state, allow_game_writes=args.allow_game_writes, allow_launch=args.allow_launch, sdk_root=sdk_root,
                              package_library_root=None if args.state_root else default_package_library_root(),
                              assistant_root=None if args.state_root else default_assistant_root())
    service.build_identity = identity
    serve(service, sys.stdin, sys.stdout)


if __name__ == "__main__": main()
