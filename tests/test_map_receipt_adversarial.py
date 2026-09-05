"""Read-only receipt qualification against disposable archive identities."""
import hashlib
import json
from pathlib import Path

import pytest

from allin1.generators import dlc_maps as maps
from tests.test_dlc_maps import _write_official_reference_metadata


def source_receipt(game):
    identities = sorted({(a.source_pack, a.source_archive_name) for a in maps.MAP_ASSETS if a.file_type == "RPF_FILE"}
                        | {(p, "dlc.rpf") for p in maps.ROCKSTAR_DEVICE_BY_PACK})
    records = []
    for pack, archive in identities:
        relative = f"update/x64/dlcpacks/{pack}/{archive}"
        source = game / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(relative.encode())
        records.append({"pack": pack, "archive": archive, "path": relative, "source": "stock",
                        "size": source.stat().st_size, "mtime_ns": source.stat().st_mtime_ns})
    return {"source_archives": records}


@pytest.mark.parametrize("mutation", ["none", "override", "absent", "missing-record", "not-list", "not-object", "bad-pack",
    "bad-archive", "duplicate", "unexpected", "size-type", "time-type", "size", "time", "source", "path"])
def test_effective_stock_archive_receipt_is_exact_and_read_only(tmp_path, mutation):
    game = tmp_path / "disposable game"
    receipt = source_receipt(game)
    record = receipt["source_archives"][0]
    source = game / record["path"]
    if mutation == "override":
        override = game / "mods" / record["path"]
        override.parent.mkdir(parents=True)
        override.write_bytes(b"overlay")
        record.update(path=override.relative_to(game).as_posix(), source="mods", size=override.stat().st_size,
                      mtime_ns=override.stat().st_mtime_ns)
    elif mutation == "absent": source.unlink()
    elif mutation == "missing-record": receipt["source_archives"].pop()
    elif mutation == "not-list": receipt["source_archives"] = {}
    elif mutation == "not-object": receipt["source_archives"][0] = None
    elif mutation == "bad-pack": record["pack"] = None
    elif mutation == "bad-archive": record["archive"] = []
    elif mutation == "duplicate": receipt["source_archives"][0] = receipt["source_archives"][1]
    elif mutation == "unexpected": record["pack"] = "unrelated"
    elif mutation == "size-type": record["size"] = []
    elif mutation == "time-type": record["mtime_ns"] = "invalid"
    elif mutation == "size": record["size"] += 1
    elif mutation == "time": record["mtime_ns"] += 1
    elif mutation == "source": record["source"] = "mods"
    elif mutation == "path": record["path"] = "../outside.rpf"
    before = {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}
    result, reason = maps.validate_reference_source_archives(receipt, game)
    assert result is (mutation in {"none", "override"}), reason
    assert before == {p.relative_to(game).as_posix(): p.read_bytes() for p in game.rglob("*") if p.is_file()}


def bridge_receipt(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    archive = pack / "dlc.rpf"
    archive.write_bytes(b"synthetic bridge archive")
    marker = dict(layout=maps.REFERENCE_PACK_LAYOUT, archive_registration="metadata-bridge",
                  activation="property-group-runtime", receipt=maps.RUNTIME_RECEIPT, asset_count="0",
                  reference_count=str(len(maps.MAP_ASSETS)), group_contract=maps.REFERENCE_GROUP_CONTRACT,
                  archive_bytes=str(archive.stat().st_size), archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    receipt = dict(schema=1, status="verified", package_id="allin1.online-content", pack_name=maps.DLC_NAME,
                   layout=maps.REFERENCE_PACK_LAYOUT, edition="enhanced", asset_count=0,
                   reference_count=len(maps.MAP_ASSETS), group_contract=maps.REFERENCE_GROUP_CONTRACT,
                   archive_bytes=archive.stat().st_size, archive_sha256=marker["archive_sha256"],
                   groups=maps.reference_group_receipt(_write_official_reference_metadata(tmp_path / "metadata")))
    def write():
        (pack / maps.ACTIVE_MARKER).write_text("".join(f"{k}={v}\n" for k, v in marker.items()), encoding="utf-8")
        (pack / maps.RUNTIME_RECEIPT).write_text(json.dumps(receipt), encoding="utf-8")
    write()
    return pack, archive, marker, receipt, write


@pytest.mark.parametrize("field,value,reason", [
    ("schema", 2, "status/schema"), ("status", "claimed", "status/schema"),
    ("package_id", "unrelated", "package_id"), ("pack_name", None, "pack_name"),
    ("layout", "old", "layout"), ("edition", "legacy", "edition"), ("group_contract", [], "group_contract"),
    ("archive_bytes", "bad", "counts"), ("archive_bytes", 5, "size"),
    ("asset_count", 1, "copied assets"), ("reference_count", 1, "reference count"),
    ("archive_sha256", "0" * 64, "fingerprints disagree"), ("groups", [], "group receipt count"),
    ("local_debug", r"C:\Users\private\file", "local path"),
])
def test_reference_bridge_rejects_bad_receipt_fields(tmp_path, field, value, reason):
    pack, archive, _, receipt, write = bridge_receipt(tmp_path)
    receipt[field] = value
    write()
    valid, detail, _ = maps.validate_reference_bridge_receipt(pack, edition="enhanced")
    assert not valid and reason in detail
    assert archive.read_bytes() == b"synthetic bridge archive"


@pytest.mark.parametrize("field", ["layout", "archive_registration", "activation", "receipt", "group_contract"])
def test_reference_bridge_rejects_mismatched_marker(tmp_path, field):
    pack, _, marker, _, write = bridge_receipt(tmp_path)
    marker[field] = "unrelated"
    write()
    valid, reason, _ = maps.validate_reference_bridge_receipt(pack, edition="enhanced")
    assert not valid and f"marker {field}" in reason


@pytest.mark.parametrize("damage", ["empty", "missing", "malformed-json", "not-object", "bad-utf8", "fingerprint", "source-drift"])
def test_reference_bridge_rejects_damaged_or_stale_evidence(tmp_path, damage):
    pack, archive, _, receipt, write = bridge_receipt(tmp_path)
    options = {}
    if damage == "empty": archive.write_bytes(b"")
    elif damage == "missing": (pack / maps.ACTIVE_MARKER).unlink()
    elif damage == "malformed-json": (pack / maps.RUNTIME_RECEIPT).write_bytes(b"{")
    elif damage == "not-object": (pack / maps.RUNTIME_RECEIPT).write_bytes(b"[]")
    elif damage == "bad-utf8": (pack / maps.ACTIVE_MARKER).write_bytes(b"\xff")
    elif damage == "fingerprint": archive.write_bytes(b"x" * archive.stat().st_size)
    else:
        options["gta_path"] = tmp_path / "game"
        receipt.update(source_receipt(options["gta_path"]))
        write()
        assert maps.validate_reference_bridge_receipt(pack, edition="enhanced", **options)[0]
        (options["gta_path"] / receipt["source_archives"][0]["path"]).write_bytes(b"changed")
    assert not maps.validate_reference_bridge_receipt(pack, edition="enhanced", **options)[0]


@pytest.mark.parametrize("mutation", ["not-object", "references", "routes", "route-object", "route-pack", "route-name",
    "associated_maps", "files_to_invalidate", "files_to_disable", "files_to_enable", "requires_loading_screen",
    "use_cache_loader", "loading_screen_context", "missing-target"])
def test_reference_routes_require_complete_typed_contract(tmp_path, mutation):
    _, _, _, receipt, _ = bridge_receipt(tmp_path)
    groups = receipt["groups"]
    if mutation == "not-object": groups[0] = None
    elif mutation == "references": groups[0]["references"] = []
    elif mutation == "routes": groups[0]["routes"] = []
    elif mutation == "route-object": groups[0]["routes"][0] = None
    elif mutation in {"route-pack", "route-name"}:
        groups[0]["routes"][0]["pack" if mutation == "route-pack" else "changeset"] = "wrong"
    elif mutation == "missing-target":
        for route in groups[0]["routes"]: route["files_to_enable"] = []
    else: groups[0]["routes"][0][mutation] = None
    assert not maps.validate_reference_group_receipt(groups)[0]


@pytest.mark.parametrize("field,value", [("loading_screen_context", "BLACK"), ("use_cache_loader", True),
    ("files_to_invalidate", ["world.rpf"]), ("files_to_disable", ["world.rpf"]), ("files_to_enable", ["unrelated.rpf"])])
def test_zero_flash_qualification_rejects_world_replacement(tmp_path, field, value):
    _, _, _, receipt, _ = bridge_receipt(tmp_path)
    groups = receipt["groups"]
    for group in groups:
        for route in group["routes"]:
            route.update(requires_loading_screen=False, loading_screen_context="", use_cache_loader=False,
                         files_to_invalidate=[], files_to_disable=[], files_to_enable=list(group["references"]))
    assert maps.validate_zero_flash_reference_groups(groups)[0]
    if field == "files_to_enable": groups[0]["routes"][0][field].extend(value)
    else: groups[0]["routes"][0][field] = value
    assert not maps.validate_zero_flash_reference_groups(groups)[0]
