import hashlib
import json
import os
from pathlib import Path

import pytest

from allin1 import traffic_population as traffic


def test_absent_policy_preserves_current_runtime_traffic_defaults(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ALLIN1.toml").write_text("[traffic]\nenabled = false\nreplacement_chance = 0.71\n")
    document = traffic.inspect_population(tmp_path)["document"]
    assert document["enabled"] is False and document["replacement_chance"] == 0.71


@pytest.mark.parametrize("raw", [b"[traffic", b"[traffic]\nenabled = 5", b"x" * (traffic.MAX_BYTES + 1)], ids=["malformed", "wrong-type", "oversized"])
def test_invalid_legacy_defaults_do_not_enable_runtime_policy(tmp_path, raw):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ALLIN1.toml").write_bytes(raw)
    result = traffic.inspect_population(tmp_path)
    assert result["document"]["enabled"] is False
    assert result["warnings"] and result["document_sha256"]


@pytest.mark.parametrize("mutate, message", [
    (lambda doc: doc.__setitem__("entries", {}), "entries exceeds"),
    (lambda doc: doc.__setitem__("entries", [{}] * (traffic.MAX_ENTRIES + 1)), "entries exceeds"),
    (lambda doc: doc.__setitem__("entries", [{}]), "unsupported fields"),
    (lambda doc: doc["entries"][0].__setitem__("model", []), "identifiers must be strings"),
    (lambda doc: doc.__setitem__("replacement_chance", float("nan")), "replacement_chance"),
    (lambda doc: doc["entries"][0].__setitem__("weight", True), "weight"),
])
def test_invalid_entry_shapes_and_nonfinite_values_are_rejected(mutate, message):
    document = _document()
    mutate(document)
    with pytest.raises(ValueError, match=message):
        traffic._normalize(document, [{"package_id": "acme.traffic", "model": "acme_road"}])


@pytest.mark.parametrize("failure", ["grow", "disappear"])
def test_diagnostic_read_stays_bounded_when_invalid_file_changes(tmp_path, monkeypatch, failure):
    path = tmp_path / traffic.POLICY_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"invalid json")
    real_read = traffic._read
    real_open = Path.open

    def change_during_read(target, limit=traffic.MAX_BYTES):
        if target == path:
            if failure == "grow":
                path.write_bytes(b"x" * (traffic.MAX_BYTES + 100))
            else:
                path.unlink()
            raise ValueError("Malformed file changed during inspection")
        return real_read(target, limit)

    sizes = []

    class BoundedStream:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def read(self, size=-1):
            sizes.append(size)
            assert size == traffic.MAX_BYTES + 1
            return self.stream.read(size)

    def open_checked(target, mode="r", *args, **kwargs):
        stream = real_open(target, mode, *args, **kwargs)
        return BoundedStream(stream) if target.name == path.name and mode == "rb" else stream

    monkeypatch.setattr(traffic, "_read", change_during_read)
    monkeypatch.setattr(Path, "open", open_checked)
    result = traffic.inspect_population(tmp_path)
    assert result["document"]["enabled"] is False
    assert result["document_sha256"] == ""
    assert result["warnings"]
    assert sizes == ([traffic.MAX_BYTES + 1] if failure == "grow" else [])


def _catalog(source_pack: str = "declared") -> bytes:
    return json.dumps({
        "schema_version": 1, "id": "vehicles", "name": "ACME Vehicles",
        "vehicles": [{
            "model": "acme_road", "name": "ACME Road", "manufacturer": "ACME",
            "category": "sports", "price": 100, "storage": "garage",
            "source_pack": source_pack, "size_tier": 0,
            "preview_dictionary": None, "preview_texture": None,
            "traffic": {"enabled": True, "weight": 1.0},
        }],
    }, separators=(",", ":")).encode("utf-8")


def _registry(payload: bytes, *, packs: list[str], enabled: bool = True) -> dict:
    return {"extensions": [{
        "id": "acme.traffic", "enabled": True,
        "capabilities": ["traffic.catalog"],
        "settings": {"traffic_enabled": enabled},
        # This is ExtensionRegistry.inspect's receipt-authenticated snapshot.
        "dlc_packs": packs,
        "catalog_files": [{"path": "scripts/acme/vehicles.json",
                           "sha256": hashlib.sha256(payload).hexdigest()}],
        "gbay": {"catalogs": [{"id": "vehicles", "kind": "vehicle",
                                 "source": "scripts/acme/vehicles.json"}]},
    }]}


def _install(game: Path, payload: bytes, *, receipt_packs: list[str]) -> None:
    catalog = game / "scripts/acme/vehicles.json"
    catalog.parent.mkdir(parents=True); catalog.write_bytes(payload)
    receipt = game / "scripts/.allin1/mods/acme.traffic.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({"id": "acme.traffic", "dlc_packs": receipt_packs}), encoding="utf-8")


def test_traffic_uses_registry_receipt_snapshot_not_a_second_mutable_receipt(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()
    # The catalog advertises "forged" ownership.  The registry snapshot only
    # authorized "declared"; a subsequent receipt rewrite must not expand it.
    payload = _catalog("forged")
    _install(game, payload, receipt_packs=["forged"])
    snapshot = _registry(payload, packs=["declared"])

    class Registry:
        def __init__(self, root): pass
        def inspect(self): return snapshot

    monkeypatch.setattr(traffic, "ExtensionRegistry", Registry)
    models, warnings = traffic._discover_models(game)
    assert models == []
    assert any("unowned DLC pack" in warning for warning in warnings)


def test_traffic_respects_effective_package_setting_before_reading_catalog(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()
    payload = _catalog("declared")
    # No receipt/catalog is installed: effective false must short-circuit it.
    snapshot = _registry(payload, packs=["declared"], enabled=False)

    class Registry:
        def __init__(self, root): pass
        def inspect(self): return snapshot

    monkeypatch.setattr(traffic, "ExtensionRegistry", Registry)
    models, warnings = traffic._discover_models(game)
    assert models == []
    assert warnings == []


def _bind_registry(monkeypatch, snapshot: dict) -> None:
    class Registry:
        def __init__(self, root): pass
        def inspect(self): return snapshot
    monkeypatch.setattr(traffic, "ExtensionRegistry", Registry)


def _document(*, entries=None) -> dict:
    return {"schema_version": 1, "enabled": True, "replacement_chance": 0.25,
            "entries": entries if entries is not None else [{
                "package_id": "acme.traffic", "model": "acme_road",
                "enabled": True, "weight": 2,
            }]}


def _authorized_game(tmp_path: Path, monkeypatch, *, payload: bytes | None = None):
    game = tmp_path / "game"; game.mkdir(parents=True)
    payload = payload or _catalog()
    _install(game, payload, receipt_packs=["declared"])
    _bind_registry(monkeypatch, _registry(payload, packs=["declared"]))
    return game, payload


def test_persisted_policy_round_trip_and_absent_token_are_review_bound(
    tmp_path: Path, monkeypatch,
) -> None:
    game, _ = _authorized_game(tmp_path, monkeypatch)
    absent = traffic.inspect_population(game)
    assert absent["models"][0]["model"] == "acme_road"
    assert absent["document"]["entries"][0]["enabled"] is True
    saved = traffic.save_population(game, _document(), absent["document_sha256"])
    path = game / traffic.POLICY_PATH
    assert path.is_file()
    assert saved["document"]["entries"][0]["weight"] == 2.0
    present = traffic.inspect_population(game)
    assert present["document_sha256"] == saved["document_sha256"]
    assert present["document"] == saved["document"]


@pytest.mark.parametrize("kind, expected_hash", [
    ("malformed", True), ("oversized", False),
])
def test_malformed_and_oversized_persisted_policy_fail_closed(
    tmp_path: Path, monkeypatch, kind: str, expected_hash: bool,
) -> None:
    game, _ = _authorized_game(tmp_path, monkeypatch)
    content = b'{"broken":' if kind == "malformed" else b"x" * (traffic.MAX_BYTES + 1)
    path = game / traffic.POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    result = traffic.inspect_population(game)
    assert result["document"]["enabled"] is False
    assert result["warnings"]
    assert bool(result["document_sha256"]) is expected_hash


@pytest.mark.parametrize("mutate, message", [
    (lambda doc: doc.__setitem__("extra", True), "missing or unsupported"),
    (lambda doc: doc.__setitem__("schema_version", True), "schema_version"),
    (lambda doc: doc.__setitem__("enabled", 1), "enabled must be a boolean"),
    (lambda doc: doc.__setitem__("replacement_chance", 1.1), "replacement_chance"),
    (lambda doc: doc.__setitem__("entries", [{"package_id": "unknown.pkg", "model": "acme_road", "enabled": True, "weight": 1}]), "authorized"),
    (lambda doc: doc.__setitem__("entries", [doc["entries"][0], dict(doc["entries"][0])]), "duplicate"),
    (lambda doc: doc["entries"][0].__setitem__("enabled", 1), "enabled must be a boolean"),
    (lambda doc: doc["entries"][0].__setitem__("weight", 20.1), "weight"),
])
def test_policy_schema_bounds_boolean_duplicate_and_ownership_guards(
    tmp_path: Path, monkeypatch, mutate, message: str,
) -> None:
    game, _ = _authorized_game(tmp_path, monkeypatch)
    document = _document(); mutate(document)
    with pytest.raises(ValueError, match=message):
        traffic.validate_document(game, document)


def test_stale_review_and_failed_second_validation_leave_no_temp_or_policy(
    tmp_path: Path, monkeypatch,
) -> None:
    game, _ = _authorized_game(tmp_path, monkeypatch)
    review = traffic.inspect_population(game)
    path = game / traffic.POLICY_PATH
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="changed; reload"):
        traffic.save_population(game, _document(), review["document_sha256"])
    before = path.read_bytes()
    real_validate = traffic.validate_document
    calls = 0

    def fail_after_write(root, document):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("authorization changed during save")
        return real_validate(root, document)

    # Use the current document's digest so execution reaches the private temp
    # write, then force the revalidation failure that must clean it up.
    monkeypatch.setattr(traffic, "validate_document", fail_after_write)
    with pytest.raises(ValueError, match="authorization changed"):
        traffic.save_population(game, _document(), hashlib.sha256(before).hexdigest())
    assert path.read_bytes() == before
    assert not list(path.parent.glob(".traffic-population.*.tmp"))


def test_catalog_hash_tamper_unsupported_class_and_invalid_weight_are_not_listed(
    tmp_path: Path, monkeypatch,
) -> None:
    payload = _catalog()
    game, _ = _authorized_game(tmp_path, monkeypatch, payload=payload)
    catalog = game / "scripts/acme/vehicles.json"
    catalog.write_bytes(payload + b" ")
    models, warnings = traffic._discover_models(game)
    assert models == [] and warnings

    boat = json.loads(_catalog().decode())
    boat["vehicles"][0]["category"] = "boats"
    boat["vehicles"][0]["storage"] = "harbour"
    boat_payload = json.dumps(boat, separators=(",", ":")).encode()
    game, _ = _authorized_game(tmp_path / "boat", monkeypatch, payload=boat_payload)
    models, warnings = traffic._discover_models(game)
    assert models == [] and any("not a road vehicle" in warning for warning in warnings)

    invalid = json.loads(_catalog().decode())
    invalid["vehicles"][0]["traffic"]["weight"] = 20.1
    invalid_payload = json.dumps(invalid, separators=(",", ":")).encode()
    game, _ = _authorized_game(tmp_path / "weight", monkeypatch, payload=invalid_payload)
    models, warnings = traffic._discover_models(game)
    assert models == [] and warnings


def test_catalog_symlink_escape_is_rejected_before_catalog_read(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()
    outside = tmp_path / "outside.json"; payload = _catalog(); outside.write_bytes(payload)
    destination = game / "scripts/acme/vehicles.json"; destination.parent.mkdir(parents=True)
    try:
        os.symlink(outside, destination)
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable on this Windows host")
    _bind_registry(monkeypatch, _registry(payload, packs=["declared"]))
    models, warnings = traffic._discover_models(game)
    assert models == []
    assert any("Symlink/junction/reparse" in warning for warning in warnings)


@pytest.mark.parametrize("gate", ["extension_disabled", "capability_missing", "setting_disabled", "item_disabled"])
def test_every_traffic_opt_in_gate_must_be_open(
    tmp_path: Path, monkeypatch, gate: str,
) -> None:
    payload = _catalog()
    game, _ = _authorized_game(tmp_path, monkeypatch, payload=payload)
    snapshot = _registry(payload, packs=["declared"])
    extension = snapshot["extensions"][0]
    if gate == "extension_disabled":
        extension["enabled"] = False
    elif gate == "capability_missing":
        extension["capabilities"] = []
    elif gate == "setting_disabled":
        extension["settings"]["traffic_enabled"] = False
    else:
        document = json.loads(payload.decode())
        document["vehicles"][0]["traffic"]["enabled"] = False
        payload = json.dumps(document, separators=(",", ":")).encode()
        (game / "scripts/acme/vehicles.json").write_bytes(payload)
        extension["catalog_files"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
    _bind_registry(monkeypatch, snapshot)
    models, warnings = traffic._discover_models(game)
    assert models == []
    assert warnings == []
