"""Corrupted authorizations/indexes/caches must not become runtime evidence."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1 import garage_map_detection as detection
from tests.test_garage_map_detection import _game, _runner, _payload, REQUESTED


@pytest.mark.parametrize("value", [None, "", " path ", "a/../b", "a//b", "/absolute", "C:/absolute", "a?b"])
def test_descriptor_paths_reject_ambiguous_or_external_destinations(value):
    with pytest.raises(ValueError): detection._safe_relative(value, "test")


@pytest.mark.parametrize("value", [None, "", "x" * 513, "root.rpf!!child.rpf", "root.rpf!../escape", "root.rpf!/absolute"])
def test_virtual_archive_paths_are_bounded_relative_segments(value):
    with pytest.raises(ValueError): detection._safe_virtual_archive_path(value, "test")


def test_portable_paths_and_ipl_normalization_are_deterministic(tmp_path):
    assert detection._safe_virtual_archive_path(r"root.rpf!x64\child.rpf", "test") == "root.rpf!x64/child.rpf"
    assert detection._descriptor_ipls({"streaming": {"ipls": ["Second", "FIRST"]},
        "levels": [None, {"ipls": ["first", "third"]}, {"ipls": None}]}) == ("FIRST", "Second", "third")
    assert detection._descriptor_ipls({"streaming": None, "levels": None}) == ()
    assert detection._descriptor_ipls({"streaming": {"ipls": None}}) == ()
    with pytest.raises(ValueError): detection._descriptor_ipls({"levels": [{"ipls": [False]}]})
    with pytest.raises(ValueError):
        detection._descriptor_ipls({"streaming": {"ipls": [f"ipl_{n}" for n in range(detection.MAX_IPLS_PER_PROJECT + 1)]}})
    with pytest.raises(ValueError): detection._safe_index_path("x" * 513, "test")
    assert detection._file_identity(tmp_path / "missing", "missing")["exists"] is False
    source = tmp_path / "hash.bin"
    source.write_bytes(b"known")
    assert detection._sha256_file(source) == hashlib.sha256(b"known").hexdigest()


@pytest.mark.parametrize("damage", ["registry-schema", "extensions", "disabled", "no-maps", "too-many", "record", "wrong-root",
    "hash", "missing", "json", "utf8", "schema", "id", "duplicate", "streaming", "pack", "unsupported-edition"])
def test_map_authorization_is_complete_before_any_index_or_cache_write(tmp_path, damage):
    game, descriptor, patcher = _game(tmp_path)
    registry_path = game / "scripts/.allin1/extensions/registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    extension = registry["extensions"][0]
    record = extension["map_files"][0]
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    if damage == "registry-schema": registry["schema_version"] = 2
    elif damage == "extensions": registry["extensions"] = {}
    elif damage == "disabled": extension["enabled"] = False
    elif damage == "no-maps": extension["map_files"] = []
    elif damage == "too-many": extension["map_files"] *= detection.MAX_PROJECTS + 1
    elif damage == "record": extension["map_files"] = [None]
    elif damage == "wrong-root": record["path"] = "scripts/elsewhere/file.json"
    elif damage == "hash": record["sha256"] = "invalid"
    elif damage == "missing": descriptor.unlink()
    elif damage == "duplicate": extension["map_files"].append(dict(record))
    else:
        if damage == "schema": payload["schema_version"] = 2
        elif damage == "id": payload["id"] = "not/allowed"
        elif damage == "streaming": payload["streaming"] = None
        elif damage == "pack": payload["streaming"]["pack_name"] = "../outside"
        elif damage == "unsupported-edition": payload["editions"] = ["other"]
        raw = b"{" if damage == "json" else b"\xff" if damage == "utf8" else json.dumps(payload).encode()
        descriptor.write_bytes(raw)
        record["sha256"] = hashlib.sha256(raw).hexdigest()
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
    if damage == "unsupported-edition": assert detection._authorized_projects(game, "enhanced") == []
    else:
        with pytest.raises(ValueError):
            detection.refresh_garage_map_detection(game, patcher=patcher,
                runner=lambda *a, **k: pytest.fail("Unvalidated input reached the native indexer"))
    assert before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}


@pytest.mark.parametrize("raw", [b"", b"{", b"\xff", b" " * 21])
def test_invalid_json_is_rejected_before_use(tmp_path, raw):
    source = tmp_path / "data.json"
    source.write_bytes(raw)
    with pytest.raises(ValueError): detection._read_json(source, 20, "test")


def cache_fixture(tmp_path):
    game, _, patcher = _game(tmp_path)
    detection.refresh_garage_map_detection(game, patcher=patcher, runner=_runner([REQUESTED], []))
    envelope, payload = _payload(game)
    projects = detection._authorized_projects(game, "enhanced")
    return game / detection.CACHE_RELATIVE_PATH, envelope, payload, projects


@pytest.mark.parametrize("location,field,value", [
    ("project", "id", None), ("project", "id", "unrelated"), ("project", "unexpected", 1),
    ("project", "pack_name", "unrelated"), ("project", "descriptor_sha256", "0" * 64),
    ("project", "status", "claimed"), ("project", "status", "not_applicable"),
    ("project", "source", None), ("project", "ipl_mappings", None), ("project", "ipl_mappings", []),
    ("source", "archive_path", "../outside"), ("source", "size", True), ("source", "size", -1),
    ("source", "mtime_ns", -1), ("source", "extra", 1),
    ("mapping", "requested", None), ("mapping", "requested", "unauthorized"),
    ("mapping", "resolved", "different"), ("mapping", "match", "approximate"),
    ("mapping", "archive_path", "root.rpf!../outside"), ("mapping", "entry_path", "../outside"),
    ("mapping", "source_rpf", "C:/outside"), ("mapping", "extra", 1),
])
def test_hash_matching_cache_still_requires_exact_mapping_contract(tmp_path, location, field, value):
    destination, _, payload, expected = cache_fixture(tmp_path)
    project = payload["projects"][0]
    target = project if location == "project" else project["source"] if location == "source" else project["ipl_mappings"][0]
    target[field] = value
    detection._write_envelope(payload, destination)  # Deliberately valid outer checksum.
    assert detection._valid_cached_payload(destination, "enhanced", payload["source_identity_fingerprint"], expected) is None


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("producer", "other"), ("payload_sha256", "0" * 64),
    ("payload_json", 1), ("extra", 1)])
def test_cache_envelope_is_versioned_and_exact(tmp_path, field, value):
    destination, envelope, payload, expected = cache_fixture(tmp_path)
    envelope[field] = value
    destination.write_text(json.dumps(envelope), encoding="utf-8")
    assert detection._valid_cached_payload(destination, "enhanced", payload["source_identity_fingerprint"], expected) is None


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("edition", "legacy"), ("source_identity_fingerprint", "other"),
    ("projects", {}), ("projects", []), ("extra", 1)])
def test_cache_payload_cannot_claim_another_edition_or_identity(tmp_path, field, value):
    destination, _, payload, expected = cache_fixture(tmp_path)
    fingerprint = payload["source_identity_fingerprint"]
    payload[field] = value
    detection._write_envelope(payload, destination)
    assert detection._valid_cached_payload(destination, "enhanced", fingerprint, expected) is None


@pytest.mark.parametrize("index", [[], {"schema_version": 2, "entries": []}, {"schema_version": 1, "entries": None},
    {"schema_version": 1, "entries": [{"name": "valid.ymap", "path": "../outside"}]}])
def test_native_index_shape_failures_never_publish_a_cache(tmp_path, index):
    game, _, patcher = _game(tmp_path)
    def run(command, **kwargs):
        Path(command[-1]).write_text(json.dumps(index), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    with pytest.raises(ValueError): detection.refresh_garage_map_detection(game, patcher=patcher, runner=run)
    assert not (game / detection.CACHE_RELATIVE_PATH).exists()


def test_indexer_failure_and_unrelated_records_are_not_successful_matches(tmp_path):
    game, _, patcher = _game(tmp_path)
    with pytest.raises(RuntimeError, match="index failed"):
        detection.refresh_garage_map_detection(game, patcher=patcher,
            runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="permission denied"))
    def run(command, **kwargs):
        Path(command[-1]).write_text(json.dumps({"schema_version": 1, "entries": [None, {},
            {"name": "bad name.ymap"}, {"name": "texture.ytd"}]}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    result = detection.refresh_garage_map_detection(game, patcher=patcher, runner=run)
    assert result.verified_projects == 0 and result.unresolved_projects == 1
    assert detection._match_ipl("short", {}, []) is None
    assert detection._match_ipl(REQUESTED, {}, ["entirely_unrelated_map_name"]) is None


def test_no_ipl_and_missing_pack_states_are_distinct(tmp_path):
    game, descriptor, patcher = _game(tmp_path)
    (game / "update/x64/dlcpacks/mptuner/dlc.rpf").unlink()
    result = detection.refresh_garage_map_detection(game, patcher=patcher, runner=lambda *a, **k: pytest.fail("No archive"))
    assert result.verified_projects == 0 and result.unresolved_projects == 1
    from tests.test_garage_map_detection import _replace_descriptor_ipls
    _replace_descriptor_ipls(game, descriptor, [])
    result = detection.refresh_garage_map_detection(game, patcher=patcher)
    assert result.verified_projects == 1
    assert _payload(game)[1]["projects"][0]["status"] == "not_applicable"
    patcher.unlink()
    _replace_descriptor_ipls(game, descriptor, [REQUESTED])
    with pytest.raises(FileNotFoundError): detection.refresh_garage_map_detection(game, patcher=patcher)
