"""Synthetic logs and temporary contracts are not live acceptance evidence."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from allin1 import map_stock_bridge_black_canary as davis
from allin1 import map_grapeseed_stock_bridge_black_canary as grapeseed
from allin1 import map_grapeseed_stock_bridge_canary as grapeseed_a
from tests.test_map_stock_bridge_black_canary import _fixture as davis_fixture
from tests.test_map_grapeseed_stock_bridge_canary import _install as grapeseed_fixture


@pytest.mark.parametrize("module", [davis, grapeseed], ids=["davis", "grapeseed"])
@pytest.mark.parametrize("damage", ["none", "noise", "missing-log", "locked", "too-large", "session-length", "session-case", "session-chars",
    "no-start", "two-starts", "bad-time", "naive-time", "missing-time", "predates", "no-block", "short-survival", "error", "fatal", "transaction"])
def test_session_evidence_requires_exact_completed_guard_session(tmp_path, module, damage):
    session = "123456abcdef"
    receipt_path = tmp_path / "install-receipt.json"
    receipt_path.write_bytes(b'{"transaction_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
    os.utime(receipt_path, (1_700_000_000, 1_700_000_000))
    receipt = json.loads(receipt_path.read_bytes())
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    name = "davis" if module is davis else "grapeseed"
    events = [
        {"session": session, "ts": start.isoformat(), "component": "Client", "message": "session_started", "level": "INFO"},
        {"session": session, "ts": (start + timedelta(seconds=1)).isoformat(), "component": "DeferredMap",
         "message": f"{name}_phase_a_runtime_activation_blocked", "property": name, "request_source": "proximity_zone" if module is davis else "startup_guard",
         "required_phase": module.PHASE, "native_group_executed": False, "ipl_requested": False, "level": "WARN"},
        {"session": session, "ts": (start + timedelta(seconds=60)).isoformat(), "component": "Client", "message": "session_survived", "level": "INFO"},
    ]
    if damage == "session-length": session = "abc"
    elif damage == "session-case": session = session.upper()
    elif damage == "session-chars": session = "z" * 12
    elif damage == "no-start": events.pop(0)
    elif damage == "two-starts": events.append(events[0].copy())
    elif damage == "bad-time": events[0]["ts"] = "not a date"
    elif damage == "naive-time": events[0]["ts"] = "2025-01-01T00:00:00"
    elif damage == "missing-time": events[0]["ts"] = None
    elif damage == "predates": events[0]["ts"] = "2020-01-01T00:00:00Z"
    elif damage == "no-block": events[1]["native_group_executed"] = True
    elif damage == "short-survival": events[2]["ts"] = events[1]["ts"]
    elif damage in {"error", "fatal"}: events[-1]["level"] = damage.upper()
    elif damage == "transaction": receipt["transaction_id"] = "short"
    log = tmp_path / module.CLIENT_LOG_RELATIVE
    log.parent.mkdir(parents=True)
    raw = "".join(json.dumps(event) + "\n" for event in events).encode()
    if damage == "noise": raw = b'not-json\n[]\n{"session":"unrelated"}\n' + raw
    log.write_bytes(raw)
    if damage == "missing-log": log.unlink()
    elif damage == "locked":
        lock = tmp_path / module.SESSION_LOCK_RELATIVE
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_bytes(b"still active")
    elif damage == "too-large": log.write_bytes(b" " * (16 * 1024 * 1024 + 1))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    if damage in {"none", "noise"}:
        result = module.inspect_phase_a_session_evidence(tmp_path, session=session, phase_a_receipt=receipt, phase_a_receipt_path=receipt_path)
        assert result["blocked_event_count"] == 1 and result["session_event_count"] == 3
        assert result["client_log_sha256"] == hashlib.sha256(raw).hexdigest().upper()
        assert result["phase_a_transaction_id"] == receipt["transaction_id"]
    else:
        with pytest.raises((RuntimeError, ValueError, FileNotFoundError)):
            module.inspect_phase_a_session_evidence(tmp_path, session=session, phase_a_receipt=receipt, phase_a_receipt_path=receipt_path)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def launch_fixture(tmp_path, monkeypatch, module):
    if module is davis:
        game, _, _, state, _ = davis_fixture(tmp_path, monkeypatch)
        receipt = json.loads((state / "install-receipt.json").read_bytes())
    else:
        game, _, _, _, receipt = grapeseed_fixture(tmp_path, monkeypatch)
    root = module._destination(game)
    if module is not grapeseed_a:
        payload = module._runtime_receipt(root / "dlc.rpf", receipt, "1" * 64)
        (root / module.RUNTIME_RECEIPT_NAME).write_text(json.dumps(payload), encoding="utf-8")
        (root / module.MARKER_NAME).write_text(module._marker_text(payload), encoding="utf-8")
    validate = module.validate_phase_a_launch_contract if module is grapeseed_a else module.validate_phase_b_launch_contract
    assert validate(game)[0]
    return game, root, validate


@pytest.mark.parametrize("module", [davis, grapeseed, grapeseed_a], ids=["davis-b", "grapeseed-b", "grapeseed-a"])
@pytest.mark.parametrize("damage", ["wrong-edition", "missing-pack", "extra-file", "directory-entry", "empty-archive", "large-archive",
    "marker-preamble", "marker-line", "marker-duplicate", "marker-key", "marker-value", "runtime-json", "runtime-object",
    "runtime-extra", "runtime-value", "runtime-groups", "source-missing", "source-changed"])
def test_launch_contract_rejects_drift_without_mutating_it(tmp_path, monkeypatch, module, damage):
    game, root, validate = launch_fixture(tmp_path, monkeypatch, module)
    marker = root / module.MARKER_NAME
    runtime = root / module.RUNTIME_RECEIPT_NAME
    archive = root / "dlc.rpf"
    if damage == "wrong-edition": (game / "GTA5_Enhanced.exe").unlink()
    elif damage == "missing-pack":
        for p in root.iterdir(): p.unlink()
        root.rmdir()
    elif damage == "extra-file": (root / "unowned.txt").write_bytes(b"preserve")
    elif damage == "directory-entry":
        archive.unlink()
        archive.mkdir()
    elif damage == "empty-archive": archive.write_bytes(b"")
    elif damage == "large-archive": archive.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    elif damage.startswith("marker"):
        text = marker.read_text(encoding="utf-8")
        if damage == "marker-preamble": text = "wrong\n" + text
        elif damage == "marker-line": text += "not a field\n"
        elif damage == "marker-duplicate": text += text.splitlines()[1] + "\n"
        elif damage == "marker-key": text += "unknown=1\n"
        else:
            lines = text.splitlines()
            key = lines[1].split("=")[0]
            lines[1] = f"{key}=changed"
            text = "\n".join(lines)
        marker.write_text(text, encoding="utf-8")
    elif damage.startswith("runtime"):
        payload = json.loads(runtime.read_bytes())
        if damage == "runtime-json": runtime.write_bytes(b"{")
        elif damage == "runtime-object": runtime.write_bytes(b"[]")
        else:
            payload[{"runtime-extra": "unknown", "runtime-value": "edition", "runtime-groups": "groups"}[damage]] = None
            runtime.write_text(json.dumps(payload), encoding="utf-8")
    else:
        source = game / (module.phase_a.STOCK_ARCHIVE_RELATIVE if module is not grapeseed_a else module.STOCK_ARCHIVE_RELATIVE)
        if damage == "source-missing": source.unlink()
        else: source.write_bytes(b"new game update")
    before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
    valid, reason, _ = validate(game)
    assert not valid and reason != "verified"
    assert before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}


@pytest.mark.parametrize("module", [davis, grapeseed], ids=["davis", "grapeseed"])
@pytest.mark.parametrize("damage", ["parent", "parent-id", "parent-hash", "observation-hash"])
def test_launch_contract_binds_parent_and_observation(tmp_path, monkeypatch, module, damage):
    game, root, validate = launch_fixture(tmp_path, monkeypatch, module)
    runtime = root / module.RUNTIME_RECEIPT_NAME
    payload = json.loads(runtime.read_bytes())
    if damage == "parent": payload["phase_a_parent"] = {}
    elif damage == "parent-id": payload["phase_a_parent"]["transaction_id"] = None
    elif damage == "parent-hash": payload["phase_a_parent"]["marker_sha256"] = "bad"
    else: payload["phase_a_observation_sha256"] = "not a hash"
    runtime.write_text(json.dumps(payload), encoding="utf-8")
    assert not validate(game)[0]


@pytest.mark.parametrize("read", [grapeseed._read_json_object, grapeseed_a._read_bounded_json_object])
@pytest.mark.parametrize("raw", [b"", b"[]", b'{"key":1,"key":2}', b"{" , b"\xff", b"x" * (256 * 1024 + 1)],
                         ids=["empty", "array", "duplicate", "malformed", "encoding", "oversize"])
def test_checkpoint_json_is_bounded_and_duplicate_free(tmp_path, read, raw):
    source = tmp_path / "evidence.json"
    with pytest.raises(RuntimeError): read(source)
    source.write_bytes(raw)
    with pytest.raises(RuntimeError): read(source)
    assert source.read_bytes() == raw
