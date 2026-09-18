from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from allin1.extensions import ExtensionManifest
from allin1 import ped_population as population
from allin1.ped_population import (
    MAX_DOCUMENT_BYTES,
    SUPPORTED_VANILLA_TARGETS,
    inspect_population,
    save_population,
    validate_document,
)


def _install_catalog(game: Path, *, model: str = "acme_ped",
                     source_pack: str = "acmepack") -> None:
    relative = "scripts/acme.peds/peds.json"
    catalog = {
        "schema_version": 1,
        "id": "population",
        "name": "ACME Population",
        "peds": [{
            "model": model,
            "name": "ACME Ped",
            "source_pack": source_pack,
        }],
    }
    payload = json.dumps(catalog, separators=(",", ":")).encode("utf-8")
    destination = game / Path(*relative.split("/"))
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    descriptor = {
        "schema_version": 1,
        "api_version": 1,
        "id": "acme.peds",
        "name": "ACME Peds",
        "version": "1.0.0",
        "description": "fixture",
        "capabilities": ["ped.population"],
        "systems": [],
        "gbay": {"sections": [], "catalogs": [{
            "id": "population", "kind": "ped", "source": relative,
        }]},
        "runtime": {"assemblies": []},
    }
    receipts = game / "scripts" / ".allin1" / "mods"
    receipts.mkdir(parents=True)
    (receipts / "acme.peds.json").write_text(json.dumps({
        "id": "acme.peds",
        "enabled": True,
        "requires": [],
        "dlc_packs": [source_pack],
        "extension": descriptor,
        "files": [{"destination": relative,
                   "sha256": hashlib.sha256(payload).hexdigest()}],
    }), encoding="utf-8")


def _document(mode: str = "add") -> dict:
    row = {"package_id": "acme.peds", "model": "acme_ped", "mode": mode}
    if mode == "replace":
        row["target_model"] = SUPPORTED_VANILLA_TARGETS[0]
    return {
        "schema_version": 1,
        "enabled": True,
        "replacement_chance": 0.25,
        "max_added": 2,
        "entries": [row],
    }


def test_population_inspection_uses_only_receipt_hashed_ped_catalogs(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)

    inspected = inspect_population(game)

    assert inspected["document"]["enabled"] is False
    assert inspected["models"] == [{
        "package_id": "acme.peds", "catalog_id": "population",
        "model": "acme_ped", "name": "ACME Ped", "source_pack": "acmepack",
    }]
    assert inspected["targets"] == list(SUPPORTED_VANILLA_TARGETS)
    assert inspected["warnings"] == []
    assert len(inspected["document_sha256"]) == 64


def test_population_validates_all_three_modes_and_vetted_replace_target(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)

    assert validate_document(game, _document("disabled"))["entries"][0]["mode"] == "disabled"
    assert validate_document(game, _document("add"))["entries"][0]["mode"] == "add"
    normalized = validate_document(game, _document("replace"))
    assert normalized["entries"][0]["target_model"] == SUPPORTED_VANILLA_TARGETS[0]

    bad = _document("replace")
    bad["entries"][0]["target_model"] = "player_zero"
    with pytest.raises(ValueError, match="supported vanilla ambient"):
        validate_document(game, bad)


def test_population_rejects_unknown_models_and_bad_document_shapes(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)
    unknown = _document()
    unknown["entries"][0]["model"] = "not_authorized"
    with pytest.raises(ValueError, match="receipt-authorized"):
        validate_document(game, unknown)
    malformed = _document()
    malformed["extra"] = True
    with pytest.raises(ValueError, match="must contain only"):
        validate_document(game, malformed)


def test_population_inspection_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)
    policy = game / "scripts" / ".allin1" / "ped-population.json"
    policy.parent.mkdir(exist_ok=True)
    policy.write_text(
        '{"schema_version":1,"enabled":true,"enabled":false,'
        '"replacement_chance":0,"max_added":0,"entries":[]}',
        encoding="utf-8",
    )

    inspected = inspect_population(game)

    assert inspected["document"]["enabled"] is False
    assert any("Duplicate JSON key" in warning for warning in inspected["warnings"])


def test_population_never_reads_or_overwrites_an_oversized_policy(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)
    policy = game / "scripts" / ".allin1" / "ped-population.json"
    policy.parent.mkdir(exist_ok=True)
    policy.write_bytes(b"{" + (b" " * MAX_DOCUMENT_BYTES) + b"}")

    inspected = inspect_population(game)

    assert inspected["document"]["enabled"] is False
    assert any("exceeds" in warning for warning in inspected["warnings"])
    with pytest.raises(ValueError, match="exceeds"):
        save_population(game, _document(), inspected["document_sha256"])


def test_population_save_is_atomic_and_refuses_stale_editor_state(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)
    initial = inspect_population(game)
    saved = save_population(game, _document("replace"), initial["document_sha256"])

    assert saved["document"]["entries"][0]["mode"] == "replace"
    assert inspect_population(game)["document_sha256"] == saved["document_sha256"]
    with pytest.raises(ValueError, match="changed; reload"):
        save_population(game, _document("add"), initial["document_sha256"])


def test_population_catalog_requires_declared_dlc_and_matching_hash(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    _install_catalog(game)
    receipt = game / "scripts" / ".allin1" / "mods" / "acme.peds.json"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["dlc_packs"] = []
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    inspected = inspect_population(game)
    assert inspected["models"] == []
    assert any("DLC packs" in warning for warning in inspected["warnings"])
    with pytest.raises(ValueError, match="authorization is incomplete"):
        validate_document(game, _document())


def test_ped_catalog_kind_requires_its_explicit_non_shop_capability() -> None:
    descriptor = {
        "schema_version": 1, "api_version": 1, "id": "acme.peds",
        "name": "ACME", "version": "1", "description": "",
        "capabilities": [], "systems": [],
        "gbay": {"sections": [], "catalogs": [{
            "id": "population", "kind": "ped", "source": "scripts/peds.json",
        }]}, "runtime": {"assemblies": []},
    }
    with pytest.raises(ValueError, match="ped.population"):
        ExtensionManifest.from_dict(descriptor)


def _snapshot(payload: bytes, *, packs: list[str] | None = None,
              catalogs: list[dict] | None = None) -> dict:
    source = "scripts/acme.peds/peds.json"
    return {"extensions": [{
        "id": "acme.peds", "enabled": True,
        "capabilities": ["ped.population"], "dlc_packs": packs or ["acmepack"],
        "catalog_files": [{"path": source, "sha256": hashlib.sha256(payload).hexdigest()}],
        "gbay": {"catalogs": catalogs or [{"id": "population", "kind": "ped", "source": source}]},
    }]}


def _bind_registry(monkeypatch, snapshot: dict) -> None:
    class Registry:
        def __init__(self, root): pass
        def inspect(self): return snapshot
    monkeypatch.setattr(population, "ExtensionRegistry", Registry)


def test_registry_snapshot_cannot_be_broadened_by_later_ped_receipt_rewrite(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    catalog = game / "scripts/acme.peds/peds.json"
    data = json.loads(catalog.read_text())
    data["peds"][0]["source_pack"] = "forgedpack"
    payload = json.dumps(data, separators=(",", ":")).encode(); catalog.write_bytes(payload)
    receipt = game / "scripts/.allin1/mods/acme.peds.json"
    disk = json.loads(receipt.read_text()); disk["dlc_packs"] = ["forgedpack"]
    receipt.write_text(json.dumps(disk), encoding="utf-8")
    _bind_registry(monkeypatch, _snapshot(payload, packs=["acmepack"]))
    models, warnings = population._discover_models(game)
    assert models == []
    assert any("not a receipt-declared DLC pack" in warning for warning in warnings)


def test_invalid_later_ped_catalog_retracts_earlier_records_from_the_package(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.peds/peds.json").read_bytes()
    missing = "scripts/acme.peds/missing.json"
    snapshot = _snapshot(payload, catalogs=[
        {"id": "population", "kind": "ped", "source": "scripts/acme.peds/peds.json"},
        {"id": "second", "kind": "ped", "source": missing},
    ])
    snapshot["extensions"][0]["catalog_files"].append({"path": missing, "sha256": "0" * 64})
    _bind_registry(monkeypatch, snapshot)
    models, warnings = population._discover_models(game)
    assert models == []
    assert warnings


def test_bounded_reader_never_requests_more_than_limit_plus_one_bytes(
    tmp_path: Path, monkeypatch,
) -> None:
    marker = tmp_path / "marker"; marker.write_bytes(b"x")
    reads: list[int] = []

    class Stream(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class DiskPath:
        def is_file(self): return True
        def stat(self): return SimpleNamespace(st_size=1)
        def open(self, *args, **kwargs): return Stream(b"x" * 33)

    monkeypatch.setattr(population, "filesystem_path", lambda path: DiskPath())
    with pytest.raises(ValueError, match="16 byte limit"):
        population._read_bounded_bytes(marker, 16, "test")
    assert reads == [17]


@pytest.mark.parametrize("payload, message", [
    ({"schema_version": True, "id": "population", "name": "Peds", "peds": []}, "schema_version"),
    ({"schema_version": 1, "id": "wrong", "name": "Peds", "peds": []}, "does not match"),
    ({"schema_version": 1, "id": "population", "name": "", "peds": []}, "name"),
    ({"schema_version": 1, "id": "population", "name": "Peds", "peds": "bad"}, "peds"),
    ({"schema_version": 1, "id": "population", "name": "Peds", "peds": [{"model": "acme", "name": "A", "source_pack": "other"}]}, "receipt-declared"),
    ({"schema_version": 1, "id": "population", "name": "Peds", "peds": [
        {"model": "acme", "name": "A", "source_pack": "acmepack"},
        {"model": "acme", "name": "B", "source_pack": "acmepack"},
    ]}, "duplicate"),
])
def test_ped_catalog_schema_identity_name_duplicate_and_ownership_contracts(
    payload: dict, message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        population._parse_catalog(payload, package_id="acme.peds",
                                  catalog_id="population",
                                  declared_packs={"acmepack"})


@pytest.mark.parametrize("change", [
    lambda view: view["extensions"][0].__setitem__("enabled", False),
    lambda view: view["extensions"][0].__setitem__("capabilities", []),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", []),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", ["ACMEPACK"]),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", ["acmepack", "acmepack"]),
    lambda view: view["extensions"][0].__setitem__("gbay", {"catalogs": "bad"}),
    lambda view: view["extensions"][0].__setitem__("gbay", []),
    lambda view: view["extensions"][0].__setitem__("catalog_files", []),
    lambda view: view["extensions"][0]["gbay"]["catalogs"][0].__setitem__("source", "../escape.json"),
])
def test_ped_registry_gates_and_catalog_paths_fail_closed(
    tmp_path: Path, monkeypatch, change,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.peds/peds.json").read_bytes()
    view = _snapshot(payload); change(view); _bind_registry(monkeypatch, view)
    models, warnings = population._discover_models(game)
    assert models == []
    if view["extensions"][0].get("enabled") and view["extensions"][0].get("capabilities"):
        assert warnings


@pytest.mark.parametrize("mutate, message", [
    (lambda doc: doc.__setitem__("extra", True), "must contain only"),
    (lambda doc: doc.__setitem__("schema_version", True), "schema_version"),
    (lambda doc: doc.__setitem__("enabled", 1), "enabled must be"),
    (lambda doc: doc.__setitem__("replacement_chance", float("nan")), "replacement_chance"),
    (lambda doc: doc.__setitem__("max_added", True), "max_added"),
    (lambda doc: doc.__setitem__("entries", "bad"), "entries"),
    (lambda doc: doc["entries"].__setitem__(0, None), "must be an object"),
    (lambda doc: doc["entries"][0].pop("mode"), "unsupported or missing"),
    (lambda doc: doc["entries"][0].__setitem__("mode", "bad"), "mode"),
    (lambda doc: doc["entries"][0].__setitem__("target_model", "a_m_y_hipster_01"), "valid only"),
    (lambda doc: doc.__setitem__("entries", [doc["entries"][0], dict(doc["entries"][0])]), "duplicate"),
])
def test_ped_population_document_modes_targets_types_and_duplicates(
    tmp_path: Path, mutate, message: str,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    document = _document(); mutate(document)
    with pytest.raises(ValueError, match=message):
        validate_document(game, document)


@pytest.mark.parametrize("function, value", [
    (population._safe_identifier, ""),
    (population._safe_identifier, "BAD SPACE"),
    (population._safe_model, "player-zero"),
    (population._safe_model, 7),
])
def test_ped_identifier_and_model_helpers_are_closed(function, value) -> None:
    with pytest.raises(ValueError):
        function(value, "test")


def test_ped_registry_inspection_failure_is_a_warning_not_authorization(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()

    class Registry:
        def __init__(self, root): pass
        def inspect(self): raise ValueError("corrupt registry")

    monkeypatch.setattr(population, "ExtensionRegistry", Registry)
    assert population._discover_models(game) == ([], ["extension registry inspection failed: corrupt registry"])


def test_ped_strict_json_and_nonstring_identifier_contracts(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"{not json")
    with pytest.raises(ValueError, match="Invalid test document"):
        population._read_json_bytes(invalid, 64, "test document")
    with pytest.raises(ValueError, match="must be a string"):
        population._safe_identifier(7, "identifier")


@pytest.mark.parametrize("mutate, message", [
    (lambda raw: raw.__setitem__("extra", True), "only schema_version"),
    (lambda raw: raw["peds"].__setitem__(0, None), "unsupported fields"),
    (lambda raw: raw["peds"][0].__setitem__("name", 7), "name must be"),
])
def test_ped_catalog_rejects_extra_fields_nonobjects_and_nonstring_names(
    mutate, message: str,
) -> None:
    raw = {"schema_version": 1, "id": "population", "name": "Peds",
           "peds": [{"model": "acme_ped", "name": "ACME", "source_pack": "acmepack"}]}
    mutate(raw)
    with pytest.raises(ValueError, match=message):
        population._parse_catalog(raw, package_id="acme.peds", catalog_id="population",
                                  declared_packs={"acmepack"})


def test_ped_inspection_recovers_from_structurally_invalid_policy_and_rejects_bad_token(
    tmp_path: Path,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    policy = game / "scripts" / ".allin1" / "ped-population.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    malformed = _document(); malformed["entries"] = [None]
    policy.write_text(json.dumps(malformed), encoding="utf-8")
    inspected = inspect_population(game)
    assert inspected["document"]["enabled"] is False
    assert any("entries[1] must be an object" in warning for warning in inspected["warnings"])
    with pytest.raises(ValueError, match="SHA-256"):
        save_population(game, _document(), "not-a-digest")


def test_ped_registry_ignores_nonlist_capabilities_and_nonped_declarations(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.peds/peds.json").read_bytes()
    view = _snapshot(payload)
    view["extensions"][0]["capabilities"] = "ped.population"
    _bind_registry(monkeypatch, view)
    assert population._discover_models(game) == ([], [])
    view = _snapshot(payload)
    view["extensions"][0]["gbay"]["catalogs"] = [None]
    _bind_registry(monkeypatch, view)
    assert population._discover_models(game) == ([], [])
