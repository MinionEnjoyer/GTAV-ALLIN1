import hashlib
import json
from pathlib import Path

import pytest

from allin1 import weapon_population as population
from allin1.config import Config
from allin1.desktop_service import LauncherService
from allin1.extensions import ExtensionManifest, ExtensionRegistry
from allin1.weapon_population import inspect_population, save_population, validate_document


PROJECT = Path(__file__).resolve().parents[1]


def _install_catalog(game: Path, *, category: str = "pistols") -> None:
    relative = "scripts/acme.weapons/weapons.json"
    catalog = {"schema_version": 1, "id": "population", "name": "ACME Weapons",
               "weapons": [{"weapon": "WEAPON_ACME_PISTOL", "name": "ACME Pistol",
                            "category": category, "price": 100, "ammo_cost_per_round": 1,
                            "source_pack": "acmepack"}]}
    payload = json.dumps(catalog, separators=(",", ":")).encode("utf-8")
    destination = game / Path(*relative.split("/"))
    destination.parent.mkdir(parents=True); destination.write_bytes(payload)
    descriptor = {"schema_version": 1, "api_version": 1, "id": "acme.weapons",
                  "name": "ACME Weapons", "version": "1.0.0", "description": "fixture",
                  "capabilities": ["gbay.catalogs"], "systems": [],
                  "gbay": {"sections": [], "catalogs": [{"id": "population", "kind": "weapon", "source": relative}]},
                  "runtime": {"assemblies": []}}
    receipts = game / "scripts" / ".allin1" / "mods"; receipts.mkdir(parents=True)
    (receipts / "acme.weapons.json").write_text(json.dumps({
        "id": "acme.weapons", "enabled": True, "requires": [], "dlc_packs": ["acmepack"],
        "extension": descriptor, "files": [{"destination": relative,
            "sha256": hashlib.sha256(payload).hexdigest()}],
    }), encoding="utf-8")


def _document(*, enabled=True, active_during_missions=False, weight=5) -> dict:
    return {"schema_version": 1, "enabled": enabled,
            "active_during_missions": active_during_missions, "replacement_chance": 0.25,
            "entries": [{"package_id": "acme.weapons", "weapon": "WEAPON_ACME_PISTOL",
                         "enabled": True, "weight": weight}]}


def test_inspection_discovers_only_receipt_hashed_weapon_catalogs(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    result = inspect_population(game)
    assert result["document"]["enabled"] is False
    assert result["document"]["active_during_missions"] is False
    assert result["models"] == [{"package_id": "acme.weapons", "weapon": "WEAPON_ACME_PISTOL",
                                 "name": "ACME Pistol", "category": "pistols"}]
    assert result["warnings"] == []


def test_document_is_strict_authorized_and_stale_safe(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    initial = inspect_population(game)
    saved = save_population(game, _document(), initial["document_sha256"])
    assert saved["document"]["replacement_chance"] == 0.25
    with pytest.raises(ValueError, match="changed; reload"):
        save_population(game, _document(weight=6), initial["document_sha256"])
    forged = _document(); forged["entries"][0]["package_id"] = "other.package"
    with pytest.raises(ValueError, match="owned"):
        validate_document(game, forged)
    malformed = _document(); malformed["entries"][0]["enabled"] = 1
    with pytest.raises(ValueError, match="boolean"):
        validate_document(game, malformed)
    malformed = _document(); malformed["schema_version"] = True
    with pytest.raises(ValueError, match="schema_version"):
        validate_document(game, malformed)


def test_legacy_mission_setting_defaults_false_and_save_normalizes_it(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    legacy = _document()
    del legacy["active_during_missions"]
    normalized = validate_document(game, legacy)
    assert normalized["active_during_missions"] is False

    path = game / "scripts/.allin1/weapon-population.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(legacy, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    inspected = inspect_population(game)
    assert inspected["document"]["active_during_missions"] is False
    assert inspected["document_sha256"] == hashlib.sha256(raw).hexdigest()
    saved = save_population(game, inspected["document"], inspected["document_sha256"])
    assert saved["document"]["active_during_missions"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["active_during_missions"] is False


@pytest.mark.parametrize("value", [0, "false", None])
def test_mission_setting_requires_a_strict_boolean(tmp_path: Path, value: object) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    document = _document(); document["active_during_missions"] = value
    with pytest.raises(ValueError, match="active_during_missions"):
        validate_document(game, document)


def test_mission_setting_accepts_true(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    assert validate_document(game, _document(active_during_missions=True))["active_during_missions"] is True


def test_mission_setting_roundtrips_when_master_policy_is_disabled(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    initial = inspect_population(game)
    document = _document(enabled=False, active_during_missions=True)
    saved = save_population(game, document, initial["document_sha256"])
    assert saved["document"]["enabled"] is False
    assert saved["document"]["active_during_missions"] is True
    assert inspect_population(game)["document"] == saved["document"]


def test_changed_catalog_or_undeclared_dlc_is_not_authorized(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    catalog = game / "scripts/acme.weapons/weapons.json"
    catalog.write_bytes(catalog.read_bytes() + b" ")
    inspected = inspect_population(game)
    assert inspected["models"] == []
    with pytest.raises(ValueError, match="receipt-authorized"):
        validate_document(game, _document())


def test_ui_inventory_excludes_runtime_ineligible_firearm_tiers(tmp_path: Path) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game, category="heavy")
    inspected = inspect_population(game)
    assert inspected["models"] == []
    with pytest.raises(ValueError, match="receipt-authorized"):
        validate_document(game, _document())


def test_builtin_nonweapon_catalog_does_not_block_public_weapon_policy_apply(tmp_path: Path) -> None:
    """The launcher must ignore its own non-weapon GBAY catalog on this path."""
    game = tmp_path / "Disposable Enhanced game"; game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"synthetic")
    _install_catalog(game)
    builtin = ExtensionManifest.load(
        PROJECT / "content" / "allin1-online-content" / "allin1.content.json",
    )
    ExtensionRegistry(game).register_builtin(builtin)

    state = tmp_path / "Launcher state"; state.mkdir()
    service = LauncherService(PROJECT, state, allow_game_writes=True)
    service.require_closed = lambda: None
    config = Config.default()
    config.general.gta_enhanced_path = str(game)
    config.general.target_edition = "enhanced"
    config.save(service.manager.config_path)

    inspected = service.inspect({"module": "weapon_manager"})["weapon_population"]
    assert inspected["warnings"] == []
    review = service.review({
        "action": "weapon_population_save",
        "expected_document_sha256": inspected["document_sha256"],
        "document": _document(),
    })
    applied = service.apply({
        "review_id": review["review_id"],
        "review_sha256": review["review_sha256"],
        "confirmed": True,
    })
    assert applied["result"]["document"] == _document()
    assert (game / "scripts/.allin1/weapon-population.json").is_file()


def _snapshot(payload: bytes, *, packs: list[str] | None = None,
              catalogs: list[dict] | None = None) -> dict:
    source = "scripts/acme.weapons/weapons.json"
    return {"extensions": [{
        "id": "acme.weapons", "enabled": True,
        "capabilities": ["gbay.catalogs"], "dlc_packs": packs or ["acmepack"],
        "catalog_files": [{"path": source, "sha256": hashlib.sha256(payload).hexdigest()}],
        "gbay": {"catalogs": catalogs or [{"id": "population", "kind": "weapon", "source": source}]},
    }]}


def _bind_registry(monkeypatch, snapshot: dict) -> None:
    class Registry:
        def __init__(self, root): pass
        def inspect(self): return snapshot
    monkeypatch.setattr(population, "ExtensionRegistry", Registry)


def test_registry_snapshot_cannot_be_broadened_by_a_later_receipt_rewrite(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()
    _install_catalog(game)
    catalog = game / "scripts/acme.weapons/weapons.json"
    data = json.loads(catalog.read_text())
    data["weapons"][0]["source_pack"] = "forgedpack"
    payload = json.dumps(data, separators=(",", ":")).encode(); catalog.write_bytes(payload)
    # Registry authenticated the old ownership snapshot while a mutable receipt
    # now claims the forged pack.  Discovery must use the snapshot, not disk.
    receipt = game / "scripts/.allin1/mods/acme.weapons.json"
    disk = json.loads(receipt.read_text()); disk["dlc_packs"] = ["forgedpack"]
    receipt.write_text(json.dumps(disk), encoding="utf-8")
    _bind_registry(monkeypatch, _snapshot(payload, packs=["acmepack"]))
    models, warnings = population._discover_models(game)
    assert models == []
    assert any("unowned DLC pack" in warning for warning in warnings)


def test_hash_checked_catalog_is_parsed_from_the_verified_bytes_not_reread(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    catalog = game / "scripts/acme.weapons/weapons.json"; payload = catalog.read_bytes()
    _bind_registry(monkeypatch, _snapshot(payload))

    def reread_forbidden(*args, **kwargs):
        raise AssertionError("catalog path was read after byte verification")

    monkeypatch.setattr(population.WeaponCatalog, "load", reread_forbidden)
    models, warnings = population._discover_models(game)
    assert len(models) == 1
    assert warnings == []


def test_invalid_later_catalog_retracts_all_earlier_records_from_its_package(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    first = game / "scripts/acme.weapons/weapons.json"; payload = first.read_bytes()
    second_source = "scripts/acme.weapons/missing.json"
    snapshot = _snapshot(payload, catalogs=[
        {"id": "population", "kind": "weapon", "source": "scripts/acme.weapons/weapons.json"},
        {"id": "second", "kind": "weapon", "source": second_source},
    ])
    snapshot["extensions"][0]["catalog_files"].append({
        "path": second_source, "sha256": "0" * 64,
    })
    _bind_registry(monkeypatch, snapshot)
    models, warnings = population._discover_models(game)
    assert models == []
    assert warnings


def test_oversized_policy_is_not_hashed_from_unbounded_content(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    path = game / "scripts/.allin1/weapon-population.json"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x" * (population.MAX_DOCUMENT_BYTES + 1))
    result = inspect_population(game)
    assert result["document"]["enabled"] is False
    assert result["warnings"]
    assert result["document_sha256"] == hashlib.sha256(
        population._canonical_bytes(population._default_document())).hexdigest()


def test_final_stale_check_cleans_temp_and_preserves_concurrent_document(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    initial = inspect_population(game)
    path = game / "scripts/.allin1/weapon-population.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    concurrent = b'{"concurrent":true}'
    path.write_bytes(concurrent)
    actual_read = population._read_bounded_bytes
    real_validate = population.validate_document
    reads = 0

    def staged_read(candidate, limit, label):
        nonlocal reads
        reads += 1
        if reads == 1:
            return population._canonical_bytes(population._default_document())
        return actual_read(candidate, limit, label)

    def validate_then_stage(root, document):
        result = real_validate(root, document)
        monkeypatch.setattr(population, "_read_bounded_bytes", staged_read)
        return result

    # Validation completes against the authorized catalog, then the first
    # state read sees the reviewed absent token and the final read sees the
    # concurrent writer's bytes after the temp file has been created.
    monkeypatch.setattr(population, "validate_document", validate_then_stage)
    with pytest.raises(ValueError, match="changed; reload"):
        save_population(game, _document(), initial["document_sha256"])
    assert path.read_bytes() == concurrent
    assert not list(path.parent.glob(".weapon-population.*.tmp"))


@pytest.mark.parametrize("change", [
    lambda view: view["extensions"][0].__setitem__("enabled", False),
    lambda view: view["extensions"][0].__setitem__("capabilities", []),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", []),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", ["ACMEPACK"]),
    lambda view: view["extensions"][0].__setitem__("dlc_packs", ["acmepack", "acmepack"]),
    lambda view: view["extensions"][0].__setitem__("gbay", {"catalogs": "bad"}),
    lambda view: view["extensions"][0].__setitem__("catalog_files", []),
    lambda view: view["extensions"][0].__setitem__("catalog_files", "bad"),
    lambda view: view["extensions"][0]["gbay"]["catalogs"][0].__setitem__("source", "../escape.json"),
])
def test_registry_gates_and_catalog_authorization_fail_closed(
    tmp_path: Path, monkeypatch, change,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.weapons/weapons.json").read_bytes()
    view = _snapshot(payload); change(view); _bind_registry(monkeypatch, view)
    models, warnings = population._discover_models(game)
    assert models == []
    # Disabled/non-weapon-capability packages are deliberately ignored; every
    # malformed authorized package instead surfaces a diagnostic warning.
    if view["extensions"][0].get("enabled") and view["extensions"][0].get("capabilities"):
        assert warnings


@pytest.mark.parametrize("mutate, message", [
    (lambda raw: raw.__setitem__("schema_version", True), "schema"),
    (lambda raw: raw.__setitem__("id", "wrong"), "id does not match"),
    (lambda raw: raw.__setitem__("name", ""), "name"),
    (lambda raw: raw["weapons"][0].__setitem__("category", "throwables"), "Unsupported firearm"),
    (lambda raw: raw["weapons"][0].__setitem__("source_pack", "base"), "Invalid add-on"),
    (lambda raw: raw["weapons"].append(dict(raw["weapons"][0])), "Duplicate weapon"),
])
def test_catalog_schema_identity_and_ownership_contracts(
    tmp_path: Path, monkeypatch, mutate, message: str,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    raw = json.loads((game / "scripts/acme.weapons/weapons.json").read_text())
    mutate(raw)
    payload = json.dumps(raw, separators=(",", ":")).encode()
    (game / "scripts/acme.weapons/weapons.json").write_bytes(payload)
    _bind_registry(monkeypatch, _snapshot(payload))
    models, warnings = population._discover_models(game)
    assert models == []
    assert any(message.lower() in warning.lower() for warning in warnings)


@pytest.mark.parametrize("mutate, message", [
    (lambda doc: doc.__setitem__("extra", True), "must contain only"),
    (lambda doc: doc.__setitem__("schema_version", 2), "schema_version"),
    (lambda doc: doc.__setitem__("enabled", 1), "enabled must be"),
    (lambda doc: doc.__setitem__("active_during_missions", 1), "active_during_missions"),
    (lambda doc: doc.__setitem__("replacement_chance", float("nan")), "replacement_chance"),
    (lambda doc: doc.__setitem__("entries", "bad"), "entries"),
    (lambda doc: doc["entries"].__setitem__(0, None), "must contain only"),
    (lambda doc: doc["entries"][0].__setitem__("weight", 0), "weight"),
    (lambda doc: doc["entries"][0].__setitem__("weight", True), "weight"),
    (lambda doc: doc["entries"][0].__setitem__("weapon", "weapon_acme_pistol"), "receipt-authorized"),
    (lambda doc: doc.__setitem__("entries", [doc["entries"][0], dict(doc["entries"][0])]), "duplicate"),
])
def test_population_document_type_bounds_and_duplicate_contracts(
    tmp_path: Path, mutate, message: str,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    document = _document(); mutate(document)
    with pytest.raises(ValueError, match=message):
        validate_document(game, document)


def test_catalog_hash_dictionary_ignores_malformed_rows_and_duplicate_json_policy_fails_closed(
    tmp_path: Path, monkeypatch,
) -> None:
    assert population._catalog_hashes({"catalog_files": [None, {"path": "x", "sha256": "bad"}]}) == {}
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    policy = game / "scripts/.allin1/weapon-population.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text('{"enabled":true,"enabled":false}', encoding="utf-8")
    result = inspect_population(game)
    assert result["document"]["enabled"] is False
    assert any("Duplicate JSON key" in warning for warning in result["warnings"])
    with pytest.raises(ValueError, match="SHA-256"):
        save_population(game, _document(), "invalid")


def test_weapon_registry_inspection_failure_is_a_warning_not_authorization(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir()

    class Registry:
        def __init__(self, root): pass
        def inspect(self): raise ValueError("corrupt registry")

    monkeypatch.setattr(population, "ExtensionRegistry", Registry)
    assert population._discover_models(game) == ([], ["extension registry inspection failed: corrupt registry"])


def test_weapon_catalog_hashes_nonlist_and_invalid_policy_recover_safely(tmp_path: Path) -> None:
    assert population._catalog_hashes({"catalog_files": "bad"}) == {}
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    policy = game / "scripts" / ".allin1" / "weapon-population.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    malformed = _document(); malformed["entries"] = [None]
    policy.write_text(json.dumps(malformed), encoding="utf-8")
    inspected = inspect_population(game)
    assert inspected["document"]["enabled"] is False
    assert any("entries[1]" in warning for warning in inspected["warnings"])


def test_weapon_invalid_catalog_source_and_hash_are_not_authorized(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.weapons/weapons.json").read_bytes()
    view = _snapshot(payload)
    view["extensions"][0]["gbay"]["catalogs"][0]["source"] = "/outside.json"
    _bind_registry(monkeypatch, view)
    assert population._discover_models(game)[0] == []
    view = _snapshot(payload)
    view["extensions"][0]["catalog_files"][0]["sha256"] = "0" * 64
    _bind_registry(monkeypatch, view)
    models, warnings = population._discover_models(game)
    assert models == []
    assert any("failed its receipt hash" in warning for warning in warnings)


def test_weapon_registry_ignores_nonlist_capabilities_and_nonweapon_declarations(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.weapons/weapons.json").read_bytes()
    view = _snapshot(payload)
    view["extensions"][0]["capabilities"] = "gbay.catalogs"
    _bind_registry(monkeypatch, view)
    assert population._discover_models(game) == ([], [])
    view = _snapshot(payload)
    view["extensions"][0]["gbay"]["catalogs"] = [None]
    _bind_registry(monkeypatch, view)
    assert population._discover_models(game) == ([], [])


def test_actual_weapon_catalogs_still_require_dlc_receipts_and_valid_declarations(
    tmp_path: Path, monkeypatch,
) -> None:
    game = tmp_path / "game"; game.mkdir(); _install_catalog(game)
    payload = (game / "scripts/acme.weapons/weapons.json").read_bytes()

    view = _snapshot(payload)
    view["extensions"][0]["dlc_packs"] = []
    _bind_registry(monkeypatch, view)
    models, warnings = population._discover_models(game)
    assert models == []
    assert any("receipt-declared DLC packs" in warning for warning in warnings)

    view = _snapshot(payload)
    view["extensions"][0]["gbay"]["catalogs"] = [{"kind": "weapon"}]
    _bind_registry(monkeypatch, view)
    models, warnings = population._discover_models(game)
    assert models == []
    assert any("weapon catalog id" in warning for warning in warnings)
