from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner
from lxml import etree

import allin1.cli as cli
import allin1.map_stock_bridge_black_canary as phase_b
import allin1.map_stock_bridge_canary as phase_a


SESSION = "0ce1186b7b4c"


def _dlclist(items: list[str]) -> bytes:
    root = etree.Element("SMandatoryPacksData")
    paths = etree.SubElement(root, "Paths")
    for value in items:
        etree.SubElement(paths, "Item").text = value
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )


class DlclistTool:
    def __init__(self, payload: bytes) -> None:
        self.dlclist = payload
        self.commands: list[list[str]] = []

    def __call__(self, _patcher, arguments, *, operation, timeout=600):
        del operation, timeout
        args = [str(value) for value in arguments]
        self.commands.append(args)
        if args[0] == "extract-entry":
            Path(args[4]).write_bytes(self.dlclist)
        elif args[0] == "unregister-dlc":
            root = etree.fromstring(self.dlclist)
            paths = root.find("Paths")
            assert paths is not None
            wanted = phase_a._normalized(phase_a.PACK_ENTRY)
            for item in list(paths):
                if phase_a._normalized(item.text or "") == wanted:
                    paths.remove(item)
            self.dlclist = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8",
                pretty_print=True,
            )
        elif args[0] == "replace-entry":
            self.dlclist = Path(args[4]).read_bytes()
        else:  # pragma: no cover - catches accidental Phase-B scope growth
            raise AssertionError(f"Unexpected RPF operation: {args[0]}")


def _source_attestation(game: Path) -> dict:
    source = game / phase_a.STOCK_ARCHIVE_RELATIVE
    stat = source.stat()
    return {
        "pack": "mptuner",
        "archive": "dlc.rpf",
        "source": "stock",
        "path": phase_a.STOCK_ARCHIVE_RELATIVE.as_posix(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "archive_sha256": phase_a.shared._sha256(source),
        "content_xml_bytes": 36822,
        "content_xml_sha256": "1" * 64,
        "setup2_xml_bytes": 986,
        "setup2_xml_sha256": "2" * 64,
        "device_name": phase_a.STOCK_DEVICE,
        "device_name_sha256": phase_b._sha256_bytes(
            phase_a.STOCK_DEVICE.encode("utf-8")
        ),
        "setup_order": 37,
        "stock_startup_group": "GROUP_STARTUP",
        "stock_startup_changeset": phase_a.STOCK_STARTUP_CHANGESET,
        "stock_startup_changeset_sha256": "3" * 64,
        "stock_proxy": phase_a.STOCK_PROXY,
        "stock_map_group": "GROUP_MAP",
        "stock_map_group_changesets": list(phase_a._EXPECTED_STOCK_GROUP_MAP),
        "changeset_name": phase_a.STOCK_CHANGESET,
        "changeset_sha256": "4" * 64,
        "official_semantics": {
            "associated_maps": ["MO_JIM_L11"],
            "files_to_invalidate": [],
            "files_to_disable": [],
            "files_to_enable": list(phase_a._EXPECTED_MAP_FILES),
            "requires_loading_screen": True,
            "loading_screen_context": "LOADINGSCREEN_CONTEXT_LAST_FRAME",
            "use_cache_loader": True,
        },
    }


def _write_session(
    game: Path,
    *,
    session: str = SESSION,
    include_block: bool = True,
    level: str = "INFO",
    survival_seconds: int = 45,
) -> None:
    start = datetime.now(timezone.utc) + timedelta(seconds=2)
    events = [{
        "ts": start.isoformat(),
        "level": "INFO",
        "session": session,
        "component": "Client",
        "message": "session_started",
        "version": "0.6.1.0",
    }]
    if include_block:
        events.append({
            "ts": (start + timedelta(seconds=10)).isoformat(),
            "level": "WARN",
            "session": session,
            "component": "DeferredMap",
            "message": "davis_phase_a_runtime_activation_blocked",
            "property": "davis",
            "request_source": "proximity_zone",
            "required_phase": phase_b.PHASE,
            "native_group_executed": False,
            "ipl_requested": False,
        })
    events.append({
        "ts": (start + timedelta(seconds=10 + survival_seconds)).isoformat(),
        "level": level,
        "session": session,
        "component": "Traffic",
        "message": "continued_after_guard",
    })
    log = game / phase_b.CLIENT_LOG_RELATIVE
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"enhanced")
    mods_update = game / "mods/update/update.rpf"
    mods_update.parent.mkdir(parents=True)
    mods_update.write_bytes(b"mods update")
    source = game / phase_a.STOCK_ARCHIVE_RELATIVE
    source.parent.mkdir(parents=True)
    source.write_bytes(b"effective mptuner archive")
    destination = game / "mods/update/x64/dlcpacks" / phase_a.PACK_NAME
    destination.mkdir(parents=True)
    archive = destination / "dlc.rpf"
    archive.write_bytes(b"metadata-only bridge archive")

    patcher = tmp_path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    baseline = _dlclist(["dlcpacks:/mptuner/"])
    registered = _dlclist(["dlcpacks:/mptuner/", phase_a.PACK_ENTRY])
    tool = DlclistTool(registered)
    monkeypatch.setattr(phase_a.shared, "_run_tool", tool)

    state_a = tmp_path / "phase-a-state"
    state_a.mkdir()
    staging_parent = tmp_path / "staging"
    staging_parent.mkdir()
    staging = phase_a.create_stock_bridge_staging(staging_parent)
    for name in ("content.xml", "setup2.xml"):
        (state_a / name).write_bytes((staging / name).read_bytes())
    attestation = _source_attestation(game)
    runtime = destination / phase_a.RUNTIME_RECEIPT_NAME
    phase_a.shared._write_json_atomic(
        phase_a._runtime_receipt(archive, attestation), runtime,
    )
    marker = destination / phase_a.MARKER_NAME
    phase_a._write_marker(marker, archive)
    original = state_a / "original-dlclist.xml"
    original.write_bytes(baseline)
    registered_path = state_a / "registered-dlclist.xml"
    registered_path.write_bytes(registered)
    receipt = {
        **phase_a._static_checkpoint(),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": phase_a.shared._sha256(archive),
        "source_attestation": attestation,
        "transaction_id": "a" * 32,
        "topology": phase_a.inspect_stock_bridge_topology(staging),
        "marker_sha256": phase_a.shared._sha256(marker),
        "runtime_receipt_sha256": phase_a.shared._sha256(runtime),
        "original_dlclist_sha256": phase_a.shared._sha256(original),
        "registered_dlclist_sha256": phase_a.shared._sha256(registered_path),
        "pack_existed": False,
        "original_pack_manifest": {},
    }
    phase_a.shared._write_json_atomic(receipt, state_a / "install-receipt.json")
    phase_a.shared._write_json_atomic(
        {**receipt, "status": "registered"}, state_a / "journal.json",
    )
    _write_session(game)
    return game, patcher, tool, state_a, baseline


def _promote(tmp_path, monkeypatch):
    game, patcher, tool, state_a, baseline = _fixture(tmp_path, monkeypatch)
    state_b = tmp_path / "phase-b-state"
    receipt = phase_b.promote_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.PROMOTE_CONFIRMATION,
        session=SESSION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    return game, patcher, tool, state_a, state_b, baseline, receipt


def test_promotes_exact_observed_phase_a_without_changing_archive_or_dlclist(
    tmp_path, monkeypatch,
):
    game, patcher, tool, state_a, _baseline = _fixture(
        tmp_path, monkeypatch,
    )
    state_b = tmp_path / "phase-b-state"
    destination = phase_b._destination(game)
    archive_before = (destination / "dlc.rpf").read_bytes()
    dlclist_before = tool.dlclist
    ready = phase_b.read_davis_stock_reference_black_transition_canary_status(
        game, state_root=state_b, phase_a_state_root=state_a,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert ready["status"] == "promotion_ready"
    assert ready["healthy"] is True

    receipt = phase_b.promote_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.PROMOTE_CONFIRMATION,
        session=SESSION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )

    runtime = json.loads((
        destination / phase_b.RUNTIME_RECEIPT_NAME
    ).read_text(encoding="utf-8"))
    marker, detail = phase_b._parse_strict_marker(
        destination / phase_b.MARKER_NAME,
    )
    assert detail == "verified"
    assert marker is not None and set(marker) == phase_b.MARKER_FIELDS
    assert set(runtime) == phase_b.RECEIPT_FIELDS
    assert set(runtime["groups"][0]) == phase_b.GROUP_FIELDS
    assert runtime["activation"] == phase_b.ACTIVATION
    assert runtime["activation_scope"] == "garage-entry-only"
    assert runtime["proximity_activation_enabled"] is False
    assert runtime["black_transition_required"] is True
    assert runtime["keep_resident"] is True
    assert runtime["release_on_exit"] is False
    assert runtime["groups"][0]["group"] == phase_a.DORMANT_GROUP
    assert runtime["groups"][0]["ipls"] == [phase_b.DAVIS_IPL]
    assert (destination / "dlc.rpf").read_bytes() == archive_before
    assert tool.dlclist == dlclist_before
    assert str(tmp_path) not in json.dumps(runtime)
    assert str(tmp_path) not in json.dumps(receipt)

    status = phase_b.read_davis_stock_reference_black_transition_canary_status(
        game, state_root=state_b, phase_a_state_root=state_a,
        patcher=patcher, process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert all(status["checks"].values())
    assert phase_b.promote_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.PROMOTE_CONFIRMATION,
        session=SESSION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    ) == receipt


@pytest.mark.parametrize("failure", ["wrong-session", "missing-block", "error", "lock"])
def test_session_evidence_fails_closed(tmp_path, monkeypatch, failure):
    game, patcher, _tool, state_a, _baseline = _fixture(tmp_path, monkeypatch)
    session = SESSION
    if failure == "wrong-session":
        session = "b" * 12
    elif failure == "missing-block":
        _write_session(game, include_block=False)
    elif failure == "error":
        _write_session(game, level="ERROR")
    else:
        (game / phase_b.SESSION_LOCK_RELATIVE).write_text("active")

    with pytest.raises((RuntimeError, ValueError)):
        phase_b.promote_davis_stock_reference_black_transition_canary(
            game,
            confirmation=phase_b.PROMOTE_CONFIRMATION,
            session=session,
            state_root=tmp_path / "phase-b-state",
            phase_a_state_root=state_a,
            patcher=patcher,
            process_probe=lambda: set(),
        )
    assert not (tmp_path / "phase-b-state").exists()


def test_second_atomic_replace_failure_restores_phase_a_exactly(
    tmp_path, monkeypatch,
):
    game, patcher, _tool, state_a, _baseline = _fixture(tmp_path, monkeypatch)
    destination = phase_b._destination(game)
    marker = destination / phase_b.MARKER_NAME
    runtime = destination / phase_b.RUNTIME_RECEIPT_NAME
    marker_before = marker.read_bytes()
    runtime_before = runtime.read_bytes()

    class FailSecondReplace:
        count = 0

        def __call__(self, source: Path, target: Path) -> None:
            self.count += 1
            if self.count == 2:
                raise OSError("injected marker commit failure")
            os.replace(source, target)

    with pytest.raises(OSError, match="marker commit failure"):
        phase_b.promote_davis_stock_reference_black_transition_canary(
            game,
            confirmation=phase_b.PROMOTE_CONFIRMATION,
            session=SESSION,
            state_root=tmp_path / "phase-b-state",
            phase_a_state_root=state_a,
            patcher=patcher,
            process_probe=lambda: set(),
            replace=FailSecondReplace(),
        )
    assert marker.read_bytes() == marker_before
    assert runtime.read_bytes() == runtime_before
    assert not (tmp_path / "phase-b-state").exists()


def test_rollback_restores_phase_a_then_phase_a_rollback_remains_available(
    tmp_path, monkeypatch,
):
    game, patcher, tool, state_a, state_b, baseline, _receipt = _promote(
        tmp_path, monkeypatch,
    )
    destination = phase_b._destination(game)

    rolled_back = phase_b.rollback_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert rolled_back["status"] == "rolled_back_to_phase_a"
    status = phase_a.read_davis_stock_reference_boot_canary_status(
        game, state_root=state_a, patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert phase_b.rollback_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    ) == rolled_back

    phase_a.rollback_davis_stock_reference_boot_canary(
        game,
        confirmation=phase_a.ROLLBACK_CONFIRMATION,
        state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert not destination.exists()
    assert phase_a.shared._dlclist_items(tool.dlclist) == (
        phase_a.shared._dlclist_items(baseline)
    )


def test_phase_b_status_and_rollback_preserve_grapeseed_and_unrelated_dlc(
    tmp_path, monkeypatch,
):
    game, patcher, tool, state_a, state_b, _baseline, _receipt = _promote(
        tmp_path, monkeypatch,
    )
    grapeseed = "dlcpacks:/allin1_grapeseed_stock_bridge/"
    unrelated = "dlcpacks:/unrelated_after_davis_promotion/"
    tool.dlclist = _dlclist([
        "dlcpacks:/mptuner/", phase_a.PACK_ENTRY, grapeseed, unrelated,
    ])
    before_rollback = tool.dlclist

    status = phase_b.read_davis_stock_reference_black_transition_canary_status(
        game,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert status["healthy"] is True
    assert status["checks"]["davis_registration_exact"] is True
    assert all(status["checks"].values())

    phase_b.rollback_davis_stock_reference_black_transition_canary(
        game,
        confirmation=phase_b.ROLLBACK_CONFIRMATION,
        state_root=state_b,
        phase_a_state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert tool.dlclist == before_rollback
    assert phase_a.shared._dlclist_items(tool.dlclist) == [
        "dlcpacks:/mptuner/", phase_a.PACK_ENTRY, grapeseed, unrelated,
    ]
    restored = phase_a.read_davis_stock_reference_boot_canary_status(
        game,
        state_root=state_a,
        patcher=patcher,
        process_probe=lambda: set(),
    )
    assert restored["healthy"] is True
    assert all(restored["checks"].values())


def test_phase_b_rollback_refuses_tampered_runtime(tmp_path, monkeypatch):
    game, patcher, _tool, state_a, state_b, _baseline, _receipt = _promote(
        tmp_path, monkeypatch,
    )
    runtime = phase_b._destination(game) / phase_b.RUNTIME_RECEIPT_NAME
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["proximity_activation_enabled"] = True
    runtime.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed; rollback refuses"):
        phase_b.rollback_davis_stock_reference_black_transition_canary(
            game,
            confirmation=phase_b.ROLLBACK_CONFIRMATION,
            state_root=state_b,
            phase_a_state_root=state_a,
            patcher=patcher,
            process_probe=lambda: set(),
        )


def test_cli_requires_exact_phase_b_authorization(tmp_path, monkeypatch):
    game = tmp_path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"enhanced")
    called = False

    def unexpected(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run")

    monkeypatch.setattr(
        phase_b,
        "promote_davis_stock_reference_black_transition_canary",
        unexpected,
    )
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    result = CliRunner().invoke(cli.main, [
        "--config", str(tmp_path / "missing.toml"),
        "map-canary", "stock-black-promote",
        "--gta-path", str(game), "--session", SESSION,
        "--yes", "--confirm-canary", "wrong",
    ])
    assert result.exit_code != 0
    assert "requires --yes" in result.output
    assert called is False


def test_contract_rejects_unknown_fields_and_authority_drift(
    tmp_path, monkeypatch,
):
    game, _patcher, _tool, _state_a, _state_b, _baseline, _receipt = _promote(
        tmp_path, monkeypatch,
    )
    runtime = phase_b._destination(game) / phase_b.RUNTIME_RECEIPT_NAME
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    payload["future_authority"] = False
    runtime.write_text(json.dumps(payload), encoding="utf-8")
    valid, detail, _ = phase_b.validate_phase_b_launch_contract(game)
    assert valid is False
    assert "allowlist" in detail
