import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import allin1.reactor_bootstrap as bootstrap


def _install_reactor(
    game: Path,
    *,
    enabled: bool = True,
    include_preloader: bool = False,
    include_native_bootstrap: bool = False,
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
    if include_native_bootstrap:
        native_bootstrap = game / bootstrap.REACTOR_NATIVE_BOOTSTRAP
        native_bootstrap.write_bytes(b"reactor-native-bootstrap")
        files.append({
            "destination": bootstrap.REACTOR_NATIVE_BOOTSTRAP.as_posix(),
            "sha256": hashlib.sha256(b"reactor-native-bootstrap").hexdigest(),
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


def test_shared_dependency_is_detected_without_legacy_package_receipt(tmp_path):
    from allin1 import reactor_dependency as dep
    game = tmp_path / "game"
    legacy = _install_reactor(game, include_native_bootstrap=True, include_preloader=True)
    legacy.unlink()
    for name in dep.ROOT_ASIS:
        path = game / name
        if not path.exists():
            path.write_bytes(b"native")
    files = {path.relative_to(game).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in game.rglob("*") if path.is_file()}
    receipt = game / dep.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"schema_version": 1, "product": "reactor-v", "edition": "legacy",
                                   "archive_sha256": dep.RELEASES[False].sha256, "files": files}), encoding="utf-8")
    result = bootstrap.inspect_reactor_installation(game)
    assert result.available and result.native_bootstrap
    starter = Mock()
    warmed = bootstrap.start_reactor_preloader(game, process_starter=starter)
    assert not warmed.started and "native bootstrap owns" in warmed.reason
    starter.assert_not_called()
    (game / bootstrap.REACTOR_SCRIPT).write_bytes(b"edited")
    assert not bootstrap.inspect_reactor_installation(game).available


def test_corrupt_shared_receipt_does_not_fall_back_to_old_package(tmp_path):
    from allin1 import reactor_dependency as dep
    game = tmp_path / "game"
    _install_reactor(game, include_native_bootstrap=True)
    receipt = game / dep.RECEIPT
    receipt.parent.mkdir(parents=True)
    receipt.write_text("corrupt", encoding="utf-8")
    assert not bootstrap.inspect_reactor_installation(game).available


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


def test_preloader_starts_only_from_receipt_validated_install(tmp_path, monkeypatch):
    game = tmp_path / "game"
    _install_reactor(game, include_preloader=True)
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    process = Mock()
    starter = Mock(return_value=process)
    monkeypatch.setenv("SteamGameId", "3240220")
    monkeypatch.setenv("ALLIN1_REACTOR_TEST", "kept")

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
    assert "SteamGameId" not in starter.call_args.kwargs["env"]
    assert starter.call_args.kwargs["env"]["ALLIN1_REACTOR_TEST"] == "kept"


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


def test_valid_receipt_owned_native_bootstrap_is_detected(tmp_path):
    game = tmp_path / "game"
    _install_reactor(game, include_native_bootstrap=True)

    installation = bootstrap.inspect_reactor_installation(game)

    assert installation.available is True
    assert installation.native_bootstrap is True


def test_native_bootstrap_claims_fail_closed_but_old_packages_remain_compatible(
    tmp_path,
):
    game = tmp_path / "game"
    receipt = _install_reactor(game)

    old_installation = bootstrap.inspect_reactor_installation(game)
    assert old_installation.available is True
    assert old_installation.native_bootstrap is False

    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["files"].append({
        "destination": bootstrap.REACTOR_NATIVE_BOOTSTRAP.as_posix(),
        "sha256": hashlib.sha256(b"expected").hexdigest(),
    })
    receipt.write_text(json.dumps(data), encoding="utf-8")
    missing = bootstrap.inspect_reactor_installation(game)
    assert missing.available is False
    assert "native bootstrap is missing" in missing.reason

    (game / bootstrap.REACTOR_NATIVE_BOOTSTRAP).write_bytes(b"tampered")
    tampered = bootstrap.inspect_reactor_installation(game)
    assert tampered.available is False
    assert "failed validation" in tampered.reason


def test_native_bootstrap_owns_warmup_and_launcher_does_not_spawn_preloader(
    tmp_path,
):
    game = tmp_path / "game"
    _install_reactor(
        game,
        include_preloader=True,
        include_native_bootstrap=True,
    )
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    starter = Mock()

    result = bootstrap.start_reactor_preloader(game, process_starter=starter)

    assert result.started is False
    assert "native bootstrap owns" in result.reason
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


def test_fresh_runtime_session_recovers_when_aggregate_log_is_stale(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)
    session = paths["reactor"].with_name(
        "reactorv-session-20260828T120000000Z-100.log",
    )
    session.write_text(
        "source=script stage=construction_begin\n"
        "source=runtime stage=webview_navigation_completed success=True\n"
        "source=script stage=story_mode_ready\n",
        encoding="utf-8",
    )

    state = monitor.sample(process_running=True)

    assert state.reactor_ready is True
    assert state.story_ready is True
    assert paths["reactor"].read_text(encoding="utf-8") == "old session\n"


def test_preloader_session_cannot_satisfy_runtime_readiness(tmp_path, monkeypatch):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)
    session = paths["reactor"].with_name(
        "reactorv-session-20260828T120000000Z-200.log",
    )
    session.write_text(
        "source=preloader stage=webview_navigation_completed success=True\n"
        "source=preloader stage=webview_content_ready\n",
        encoding="utf-8",
    )

    state = monitor.sample(process_running=True)

    assert state.reactor_ready is False
    assert state.story_ready is False


def test_incremental_reader_reads_only_appends_and_handles_split_markers(tmp_path):
    path = tmp_path / "runtime.log"
    path.write_text("stale marker\n", encoding="utf-8")
    reader = bootstrap.IncrementalLogReader.after_current_content(path)

    assert reader.read_new_text() == ""
    with path.open("ab") as handle:
        handle.write(b"story_mode_")
    first = reader.read_new_text()
    with path.open("ab") as handle:
        handle.write(b"ready\n")
    second = reader.read_new_text()

    assert "stale marker" not in first
    assert "story_mode_ready" in second


def test_story_ready_survives_runtime_marker_falling_out_of_carry(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)

    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write("webview_navigation_completed success=True\n")
    assert monitor.sample(process_running=True).reactor_ready is True

    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write("x" * (bootstrap.LOG_CARRY_BYTES + 128) + "\n")
    monitor.sample(process_running=True)
    with paths["reactor"].open("a", encoding="utf-8") as handle:
        handle.write("story_mode_ready\n")

    state = monitor.sample(process_running=True)
    assert state.story_ready is True


def test_native_loader_markers_survive_separate_incremental_polls(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)

    with paths["shv"].open("a", encoding="utf-8") as handle:
        handle.write("INIT: Success\n")
    assert "native" not in monitor.sample(process_running=True).ready
    with paths["shv"].open("a", encoding="utf-8") as handle:
        handle.write("x" * (bootstrap.LOG_CARRY_BYTES + 128) + "\n")
    monitor.sample(process_running=True)
    with paths["asi"].open("a", encoding="utf-8") as handle:
        handle.write("LOADER: Finished loading *.asi plugins\n")

    assert "native" in monitor.sample(process_running=True).ready


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
    transient = monitor.sample(process_running=False)
    assert transient.terminal is False
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


def test_transient_process_probe_miss_recovers_without_false_failure(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)

    assert monitor.sample(process_running=True).process_seen is True
    missed = monitor.sample(process_running=False)
    recovered = monitor.sample(process_running=True)

    assert missed.terminal is False
    assert recovered.terminal is False
    assert monitor.process_missing_samples == 0


def test_disappearing_session_trace_does_not_hide_other_candidates(
    tmp_path, monkeypatch,
):
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    directory = local / "ReactorV"
    directory.mkdir(parents=True)
    existing = directory / "reactorv-session-20260828T120000000Z-100.log"
    missing = directory / "reactorv-session-20260828T120000001Z-200.log"
    existing.write_text("runtime", encoding="utf-8")
    original_glob = Path.glob

    def candidates(path, pattern):
        if path == directory and pattern == "reactorv-session-*.log":
            return iter((missing, existing))
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", candidates)

    assert bootstrap.reactor_session_log_paths() == (existing,)


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


def test_preloader_stop_is_noop_without_process_and_fail_soft_on_process_error():
    bootstrap.ReactorPreloaderStart(None, "not started").stop()

    process = Mock()
    process.poll.side_effect = OSError("process already exited")
    bootstrap.ReactorPreloaderStart(process, "started").stop()

    process.terminate.assert_not_called()


def test_receipt_helpers_reject_unstructured_and_incomplete_records():
    assert bootstrap._receipt_file_hash([], bootstrap.REACTOR_SCRIPT) is None
    assert bootstrap._receipt_file_hash({}, bootstrap.REACTOR_SCRIPT) is None
    assert bootstrap._receipt_file_hash(
        {"files": ["bad", {"destination": "elsewhere"}]},
        bootstrap.REACTOR_SCRIPT,
    ) is None
    assert bootstrap._receipt_file_hash({
        "files": [{
            "destination": str(bootstrap.REACTOR_SCRIPT).replace("/", "\\"),
            "sha256": "short",
        }],
    }, bootstrap.REACTOR_SCRIPT) is None
    assert bootstrap._receipt_contains_file([], bootstrap.REACTOR_SCRIPT) is False
    assert bootstrap._receipt_contains_file({}, bootstrap.REACTOR_SCRIPT) is False


def test_install_inspection_reports_missing_receipt_and_unreadable_hashes(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    assert "not installed" in bootstrap.inspect_reactor_installation(game).reason

    _install_reactor(game)
    monkeypatch.setattr(
        bootstrap, "_sha256", Mock(side_effect=OSError("locked script")),
    )
    assert "could not be validated" in bootstrap.inspect_reactor_installation(game).reason


def test_native_bootstrap_receipt_requires_hash_and_readable_payload(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    receipt = _install_reactor(game)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["files"].append({
        "destination": bootstrap.REACTOR_NATIVE_BOOTSTRAP.as_posix(),
        "sha256": "not-a-sha256",
    })
    receipt.write_text(json.dumps(data), encoding="utf-8")
    assert "receipt is incomplete" in bootstrap.inspect_reactor_installation(game).reason

    _install_reactor(game, include_native_bootstrap=True)
    real_sha256 = bootstrap._sha256

    def unreadable_native(path):
        if Path(path) == game / bootstrap.REACTOR_NATIVE_BOOTSTRAP:
            raise OSError("locked native bootstrap")
        return real_sha256(path)

    monkeypatch.setattr(bootstrap, "_sha256", unreadable_native)
    assert "could not be validated" in bootstrap.inspect_reactor_installation(game).reason


def test_preloader_fail_soft_boundaries_and_legacy_executable(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    unavailable = bootstrap.start_reactor_preloader(
        game,
        process_starter=Mock(),
        installation=bootstrap.ReactorInstallation(False, "receipt unavailable"),
    )
    assert unavailable.reason == "receipt unavailable"

    receipt = _install_reactor(game, include_preloader=True)
    (game / bootstrap.REACTOR_PRELOADER).unlink()
    assert "executable is missing" in bootstrap.start_reactor_preloader(game).reason

    _install_reactor(game, include_preloader=True)
    assert "GTA V executable" in bootstrap.start_reactor_preloader(game).reason

    (game / "GTA5.exe").write_bytes(b"legacy")
    starter = Mock(return_value=Mock())
    started = bootstrap.start_reactor_preloader(game, process_starter=starter)
    assert started.started is True
    assert starter.call_args.args[0][-1] == "GTA5.exe"

    starter = Mock(side_effect=OSError("blocked by policy"))
    failed = bootstrap.start_reactor_preloader(game, process_starter=starter)
    assert failed.started is False
    assert "blocked by policy" in failed.reason

    # A receipt can outlive the helper file during an interrupted repair. The
    # receipt itself must remain untouched by this read-only startup probe.
    assert receipt.is_file()


def test_preloader_hash_read_error_is_reported_without_starting(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    _install_reactor(game, include_preloader=True)
    starter = Mock()
    real_sha256 = bootstrap._sha256

    def unreadable_preloader(path):
        if Path(path) == game / bootstrap.REACTOR_PRELOADER:
            raise OSError("sharing violation")
        return real_sha256(path)

    monkeypatch.setattr(bootstrap, "_sha256", unreadable_preloader)
    result = bootstrap.start_reactor_preloader(game, process_starter=starter)

    assert result.started is False
    assert "could not be validated" in result.reason
    starter.assert_not_called()


def test_incremental_reader_handles_oversized_append_and_read_errors(
    tmp_path, monkeypatch,
):
    path = tmp_path / "runtime.log"
    path.write_bytes(b"")
    reader = bootstrap.IncrementalLogReader.after_current_content(path)
    path.write_bytes(b"x" * (bootstrap.MAX_LOG_BYTES + 64))

    text = reader.read_new_text()

    assert len(text) == bootstrap.MAX_LOG_BYTES
    assert reader.offset == bootstrap.MAX_LOG_BYTES + 64

    with path.open("ab") as stream:
        stream.write(b"tail")
    original_open = Path.open

    def denied(target, *args, **kwargs):
        if target == path:
            raise OSError("sharing violation")
        return original_open(target, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    assert reader.read_new_text() == ""


def test_log_helpers_capture_append_and_fall_back_without_localappdata(
    tmp_path, monkeypatch,
):
    path = tmp_path / "runtime.log"
    path.write_text("before\n", encoding="utf-8")
    baseline = bootstrap.capture_log_baselines({"runtime": path})["runtime"]
    with path.open("a", encoding="utf-8") as stream:
        stream.write("after\n")
    assert bootstrap.fresh_log_text(path, baseline).splitlines() == ["after"]

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert bootstrap.reactor_runtime_log_path() == (
        tmp_path / "home/AppData/Local/ReactorV/reactorv-runtime.log"
    )


def test_session_log_enumeration_error_is_fail_soft(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def inaccessible(_path, _pattern):
        raise OSError("directory disappeared")

    monkeypatch.setattr(Path, "glob", inaccessible)
    assert bootstrap.reactor_session_log_paths() == ()


def test_script_start_marker_establishes_managed_runtime_prerequisites(
    tmp_path, monkeypatch,
):
    game = tmp_path / "game"
    local = tmp_path / "local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    paths = _write_logs(game, local)
    monitor = bootstrap.ReactorStartupMonitor(game)
    with paths["shvdn"].open("a", encoding="utf-8") as stream:
        stream.write("Started script RageWebUI.Script.RageWebUiScript.\n")

    state = monitor.sample(process_running=True)

    assert state.ready.issuperset({"native", "assets", "dotnet"})
    assert state.reactor_ready is False
