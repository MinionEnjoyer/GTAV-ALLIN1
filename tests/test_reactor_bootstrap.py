import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import allin1.reactor_bootstrap as bootstrap


def _install_reactor(
    game: Path, *, enabled: bool = True, include_preloader: bool = False,
) -> Path:
    script = game / bootstrap.REACTOR_SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(b"reactor-script")
    for relative in (
        bootstrap.REACTOR_RUNTIME,
        bootstrap.REACTOR_CONFIG,
        bootstrap.REACTOR_UI,
    ):
        target = game / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"runtime")
    receipt = game / "scripts/.allin1/mods/ragewebui.framework.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    files = [{
        "destination": bootstrap.REACTOR_SCRIPT.as_posix(),
        "sha256": hashlib.sha256(b"reactor-script").hexdigest(),
    }]
    if include_preloader:
        preloader = game / bootstrap.REACTOR_PRELOADER
        preloader.parent.mkdir(parents=True, exist_ok=True)
        preloader.write_bytes(b"reactor-preloader")
        files.append({
            "destination": bootstrap.REACTOR_PRELOADER.as_posix(),
            "sha256": hashlib.sha256(b"reactor-preloader").hexdigest(),
        })
    receipt.write_text(json.dumps({
        "id": bootstrap.REACTOR_PACKAGE_ID,
        "enabled": enabled,
        "files": files,
    }), encoding="utf-8")
    return receipt


def _write_logs(game: Path, local: Path) -> dict[str, Path]:
    paths = {
        "asi": game / "asiloader.log",
        "shv": game / "ScriptHookV.log",
        "shvdn": game / "ScriptHookVDotNet.log",
        "reactor": local / "ReactorV/reactorv-runtime.log",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("old session\n", encoding="utf-8")
    return paths


def test_activation_requires_enabled_valid_receipt_and_script(tmp_path):
    game = tmp_path / "game"
    receipt = _install_reactor(game)

    result = bootstrap.inspect_reactor_installation(game)

    assert result.available is True
    assert result.logo_path is None
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_data["enabled"] = False
    receipt.write_text(json.dumps(receipt_data), encoding="utf-8")
    assert bootstrap.inspect_reactor_installation(game).available is False


def test_corrupt_or_incomplete_receipts_fail_closed(tmp_path):
    game = tmp_path / "game"
    receipt = game / "scripts/.allin1/mods/ragewebui.framework.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("not json", encoding="utf-8")
    assert "unreadable" in bootstrap.inspect_reactor_installation(game).reason

    receipt.write_text(json.dumps({"id": "wrong", "enabled": True}), encoding="utf-8")
    assert "invalid" in bootstrap.inspect_reactor_installation(game).reason

    _install_reactor(game)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["files"] = []
    receipt.write_text(json.dumps(data), encoding="utf-8")
    assert "incomplete" in bootstrap.inspect_reactor_installation(game).reason


def test_script_hash_and_runtime_files_are_validated(tmp_path):
    game = tmp_path / "game"
    _install_reactor(game)
    (game / bootstrap.REACTOR_SCRIPT).write_bytes(b"modified")
    assert "failed validation" in bootstrap.inspect_reactor_installation(game).reason

    _install_reactor(game)
    (game / bootstrap.REACTOR_RUNTIME).unlink()
    assert "runtime is incomplete" in bootstrap.inspect_reactor_installation(game).reason


def test_preloader_starts_only_from_receipt_validated_install(tmp_path):
    game = tmp_path / "game"
    _install_reactor(game, include_preloader=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    process = Mock()
    starter = Mock(return_value=process)

    result = bootstrap.start_reactor_preloader(game, process_starter=starter)

    assert result.started is True
    assert result.process is process
    command = starter.call_args.args[0]
    assert command == [
        str(game / bootstrap.REACTOR_PRELOADER),
        "--wait-for-process",
        "GTA5_Enhanced.exe",
    ]
    assert starter.call_args.kwargs["cwd"] == str(
        (game / bootstrap.REACTOR_PRELOADER).parent
    )


def test_preloader_is_optional_and_hash_mismatch_fails_soft(tmp_path):
    game = tmp_path / "game"
    _install_reactor(game)
    (game / "GTA5.exe").write_bytes(b"game")
    starter = Mock()

    absent = bootstrap.start_reactor_preloader(game, process_starter=starter)
    assert absent.started is False
    assert "not included" in absent.reason

    _install_reactor(game, include_preloader=True)
    (game / bootstrap.REACTOR_PRELOADER).write_bytes(b"tampered")
    invalid = bootstrap.start_reactor_preloader(game, process_starter=starter)
    assert invalid.started is False
    assert "receipt validation" in invalid.reason
    starter.assert_not_called()


def test_preloader_stop_terminates_only_a_running_helper():
    process = Mock()
    process.poll.return_value = None
    result = bootstrap.ReactorPreloaderStart(process, "started")

    result.stop()

    process.terminate.assert_called_once_with()


def test_baseline_ignores_stale_markers_and_new_lines_advance_state(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    paths["shv"].write_text("INIT: Success\nCORE: Creating threads\n", encoding="utf-8")
    paths["shvdn"].write_text(
        "Loading scripts from C:\\game\\scripts\n"
        "Started script RageWebUI.Script.RageWebUiScript.\n",
        encoding="utf-8",
    )
    paths["reactor"].write_text(
        "webview_navigation_completed success=True\n", encoding="utf-8",
    )
    monitor = bootstrap.ReactorStartupMonitor(game)
    monitor.mark_launch_requested()

    stale = monitor.sample(process_running=False)
    assert stale.ready == frozenset({"launch"})

    with paths["asi"].open("a", encoding="utf-8") as handle:
        handle.write("LOADER: Finished loading *.asi plugins\n")
    with paths["shv"].open("a", encoding="utf-8") as handle:
        handle.write("INIT: Success\nCORE: Creating threads\n")
    with paths["shvdn"].open("a", encoding="utf-8") as handle:
        handle.write("Loading scripts from C:\\game\\scripts\n")

    running = monitor.sample(process_running=True)
    assert running.process_seen is True
    assert running.ready == frozenset({"launch", "native", "assets", "dotnet"})

    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write("webview_navigation_completed success=True status=Unknown\n")
    ready = monitor.sample(process_running=True)
    assert ready.reactor_ready is True
    assert ready.story_ready is False
    assert ready.terminal is False

    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write("story_mode_ready\n")
    story = monitor.sample(process_running=True)
    assert story.story_ready is True
    assert story.ready.issuperset({"reactor", "story"})


def test_replaced_logs_are_read_from_the_beginning(tmp_path, monkeypatch):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)
    paths["reactor"].write_text(
        "webview_navigation_completed success=True\n", encoding="utf-8",
    )

    state = monitor.sample(process_running=True)

    assert state.reactor_ready is True
    assert state.story_ready is False
    assert state.ready.issuperset({"native", "assets", "dotnet"})


def test_fresh_preloader_trace_exposes_browser_warmup_milestone(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)
    preloader = bootstrap.reactor_preloader_log_path()

    preloader.write_text(
        "source=preloader stage=webview_content_ready paint_ms=12.0\n",
        encoding="utf-8",
    )
    still_owned = monitor.sample(process_running=False)
    assert "warmup" not in still_owned.ready

    with preloader.open("a", encoding="utf-8") as handle:
        handle.write(
            "source=preloader stage=webview_warm_cache_released "
            "browser_exited=True\n"
        )
    state = monitor.sample(process_running=False)

    assert "warmup" in state.ready


def test_story_ready_requires_fresh_runtime_marker_and_reactor(tmp_path, monkeypatch):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    paths["reactor"].write_text("old session\nstory_mode_ready\n", encoding="utf-8")
    monitor = bootstrap.ReactorStartupMonitor(game)

    stale_story = monitor.sample(process_running=True)
    assert stale_story.story_ready is False

    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write(
            "webview_navigation_completed success=True status=Unknown\n"
            "story_mode_ready\n"
        )
    complete = monitor.sample(process_running=True)
    assert complete.reactor_ready is True
    assert complete.story_ready is True


def test_runtime_failure_game_exit_and_timeout_are_terminal(tmp_path, monkeypatch):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    clock = [10.0]
    monitor = bootstrap.ReactorStartupMonitor(
        game, hard_timeout_seconds=5.0, now=lambda: clock[0],
    )
    assert monitor.sample(process_running=True).terminal is False
    exited = monitor.sample(process_running=False)
    assert exited.terminal is True
    assert "closed" in (exited.failure or "")

    second = bootstrap.ReactorStartupMonitor(
        game, hard_timeout_seconds=5.0, now=lambda: clock[0],
    )
    clock[0] = 16.0
    timeout = second.sample(process_running=False)
    assert timeout.terminal is True
    assert "timed out" in (timeout.failure or "")

    third = bootstrap.ReactorStartupMonitor(game)
    paths["reactor"].write_text(
        "webview_navigation_completed success=False\n", encoding="utf-8",
    )
    failed = third.sample(process_running=True)
    assert failed.terminal is True
    assert "could not open" in (failed.failure or "")


def test_log_reads_are_bounded_and_unreadable_logs_fail_soft(tmp_path, monkeypatch):
    path = tmp_path / "large.log"
    path.write_bytes(b"a" * (bootstrap.MAX_LOG_BYTES + 32) + b"tail")
    content = bootstrap._read_bounded(path)
    assert len(content) == bootstrap.MAX_LOG_BYTES
    assert content.endswith(b"tail")
    assert bootstrap.fresh_log_text(tmp_path / "missing.log", bootstrap.LogBaseline()) == ""

    def denied(_path, _limit=bootstrap.MAX_LOG_BYTES):
        raise AssertionError("fresh_log_text must use the fail-soft reader")

    monkeypatch.setattr(bootstrap, "_read_bounded", lambda _path: b"\xffmarker")
    assert "marker" in bootstrap.fresh_log_text(path, bootstrap.LogBaseline())
