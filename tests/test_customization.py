import json

import pytest

from allin1.customization import (
    CharacterLoadout, CharacterOutfit, GarageSaveStore, LoadoutStore,
    OutfitVariation, _atomic_json,
)


def test_atomic_json_creates_and_backs_up(tmp_path):
    path = tmp_path / "state.json"
    _atomic_json(path, {"version": 1})
    _atomic_json(path, {"version": 2})
    assert json.loads(path.read_text()) == {"version": 2}
    assert json.loads((tmp_path / "state.json.bak").read_text()) == {"version": 1}
    assert not (tmp_path / "state.json.tmp").exists()


def test_loadout_round_trip_normalizes_all_characters(tmp_path):
    store = LoadoutStore(tmp_path / "loadouts.json", {"WEAPON_A"}, {"GEAR_A"})
    store.save({"michael": CharacterLoadout(["WEAPON_A", "WEAPON_A"], ["GEAR_A"])})
    loaded = store.load()
    assert loaded["michael"] == CharacterLoadout(["WEAPON_A"], ["GEAR_A"], False)
    assert loaded["franklin"] == CharacterLoadout()
    assert json.loads((tmp_path / "loadouts.json").read_text())["michael"]["schema_version"] == 2


@pytest.mark.parametrize("loadouts", [
    {"lamar": CharacterLoadout()},
    {"michael": CharacterLoadout(["INVALID"], [])},
    {"michael": CharacterLoadout([], ["INVALID"])},
])
def test_loadout_rejects_unknown_values(tmp_path, loadouts):
    with pytest.raises(ValueError):
        LoadoutStore(tmp_path / "x.json", {"WEAPON_A"}, {"GEAR_A"}).save(loadouts)


def test_loadout_load_deduplicates_external_file(tmp_path):
    path = tmp_path / "x.json"
    path.write_text('{"trevor":{"weapons":["A","A"],"gear":["G","G"]}}')
    loaded = LoadoutStore(path, {"A"}, {"G"}).load()
    assert loaded["trevor"] == CharacterLoadout(["A"], ["G"], False)


def test_outfit_round_trip(tmp_path):
    path = tmp_path / "characters.json"
    outfit = CharacterOutfit(managed=True, unlock_all=True)
    outfit.components[3] = OutfitVariation(17, 2)
    outfit.props[0] = OutfitVariation(5, 1)
    store = LoadoutStore(path, set(), set())
    store.save({"franklin": CharacterLoadout(outfit=outfit)})
    loaded = store.load()["franklin"].outfit
    assert loaded.managed and loaded.unlock_all
    assert loaded.components[3] == OutfitVariation(17, 2)
    assert loaded.props[0] == OutfitVariation(5, 1)


def test_named_outfit_presets_save_apply_and_validate():
    outfit = CharacterOutfit()
    outfit.components[0] = OutfitVariation(4, 2)
    LoadoutStore.save_preset(outfit, "Street")
    outfit.components[0] = OutfitVariation()
    LoadoutStore.apply_preset(outfit, "Street")
    assert outfit.components[0] == OutfitVariation(4, 2)
    with pytest.raises(ValueError):
        LoadoutStore.save_preset(outfit, " ")
    with pytest.raises(ValueError):
        LoadoutStore.save_preset(outfit, "x" * 65)
    with pytest.raises(KeyError):
        LoadoutStore.apply_preset(outfit, "missing")


@pytest.mark.parametrize("outfit", [
    CharacterOutfit(components=[]),
    CharacterOutfit(props=[]),
    CharacterOutfit(components=[OutfitVariation(-1, 0)] * 12),
    CharacterOutfit(props=[OutfitVariation(-2, 0)] * 8),
    CharacterOutfit(props=[OutfitVariation(-1, -1)] * 8),
])
def test_outfit_validation_rejects_invalid_shapes_and_values(tmp_path, outfit):
    store = LoadoutStore(tmp_path / "characters.json", set(), set())
    with pytest.raises(ValueError):
        store.save({"michael": CharacterLoadout(outfit=outfit)})


def test_garage_round_trip_import_and_export(tmp_path):
    path = tmp_path / "garage.json"
    store = GarageSaveStore(path, {"adder", "zentorno"})
    garages = {"michael": [{"model": "adder", "slot": 0}], "trevor": []}
    store.save(garages)
    exported = tmp_path / "exports" / "garage.json"
    store.export_file(exported)
    path.unlink()
    store.import_file(exported)
    assert store.load()["michael"][0]["model"] == "adder"
    assert '"_schema_v2"' in path.read_text()


def test_empty_garage_load_and_missing_export(tmp_path):
    store = GarageSaveStore(tmp_path / "missing.json", {"adder"})
    assert store.load() == {"michael": [], "franklin": [], "trevor": []}
    with pytest.raises(FileNotFoundError):
        store.export_file(tmp_path / "out.json")


@pytest.mark.parametrize("payload", [
    [],
    {"michael": [{"model": "unknown", "slot": 0}]},
    {"michael": [{"model": "adder", "slot": -1}]},
    {"michael": [{"model": "adder", "slot": 0}, {"model": "adder", "slot": 0}]},
    {"michael": [{"model": "adder", "slot": i} for i in range(11)]},
])
def test_garage_rejects_invalid_content(tmp_path, payload):
    path = tmp_path / "garage.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        GarageSaveStore(path, {"adder"}).load()


def test_garage_repair_reassigns_and_quarantines(tmp_path):
    path = tmp_path / "garage.json"
    path.write_text(json.dumps({"michael": [{"model": "adder", "slot": 0},
        {"model": "zentorno", "slot": 0}, {"model": "unknown", "slot": 2}, "broken"],
        "franklin": "bad"}))
    report = GarageSaveStore(path, {"adder", "zentorno"}).repair()
    assert (report.kept, report.reassigned, report.quarantined) == (2, 1, 3)
    assert [v["slot"] for v in GarageSaveStore(path, {"adder", "zentorno"}).load()["michael"]] == [0, 1]
    assert report.quarantine_path.is_file()


def test_garage_repair_handles_missing_and_invalid_json(tmp_path):
    store = GarageSaveStore(tmp_path / "garage.json", {"adder"})
    assert store.repair().kept == 0
    store.path.write_text("{")
    assert store.repair().quarantined == 1 and store.load()["michael"] == []
