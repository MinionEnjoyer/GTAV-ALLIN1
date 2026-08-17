import json

import pytest

from allin1.customization import (
    CharacterLoadout, CharacterOutfit, GarageSaveStore, LoadoutStore,
    OutfitVariation, _atomic_json,
)


def test_character_progress_round_trip_and_validation(tmp_path):
    from allin1.customization import CharacterProgress, SKILLS
    store = LoadoutStore(tmp_path / "characters.json", {"A"}, {"G"})
    progress = CharacterProgress(True, 123456, {name: 75 for name in SKILLS})
    store.save({"michael": CharacterLoadout(progress=progress)})
    assert store.load()["michael"].progress == progress

    progress.skills["stamina"] = 101
    with pytest.raises(ValueError, match="0 to 100"):
        store.save({"michael": CharacterLoadout(progress=progress)})


@pytest.mark.parametrize("money", [-1, 2_147_483_648])
def test_character_progress_rejects_unsafe_money(tmp_path, money):
    from allin1.customization import CharacterProgress
    store = LoadoutStore(tmp_path / "characters.json", set(), set())
    with pytest.raises(ValueError, match="money"):
        store.save({"franklin": CharacterLoadout(progress=CharacterProgress(money=money))})


def test_atomic_json_creates_and_backs_up(tmp_path):
    path = tmp_path / "state.json"
    _atomic_json(path, {"version": 1})
    _atomic_json(path, {"version": 2})
    assert json.loads(path.read_text()) == {"version": 2}
    assert json.loads((tmp_path / "state.json.bak").read_text()) == {"version": 1}
    assert not (tmp_path / "state.json.tmp").exists()


def test_loadout_round_trip_normalizes_all_characters(tmp_path):
    store = LoadoutStore(tmp_path / "loadouts.json", {"WEAPON_A"}, {"GEAR_A"})
    store.save({"michael": CharacterLoadout(
        ["WEAPON_A", "WEAPON_A"], ["GEAR_A"], equipped_gear=["GEAR_A"])})
    loaded = store.load()
    assert loaded["michael"] == CharacterLoadout(
        ["WEAPON_A"], ["GEAR_A"], False, equipped_gear=["GEAR_A"],
        weapon_ammo={"WEAPON_A": 9999})
    assert loaded["franklin"] == CharacterLoadout()
    assert json.loads((tmp_path / "loadouts.json").read_text())["michael"]["schema_version"] == 8


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
    assert loaded["trevor"] == CharacterLoadout(
        ["A"], ["G"], False, equipped_gear=["G"],
        weapon_ammo={"A": 9999})


def test_weapon_ammo_round_trip_and_validation(tmp_path):
    path = tmp_path / "characters.json"
    store = LoadoutStore(path, {"WEAPON_A"}, set())
    loadout = CharacterLoadout(
        weapons=["WEAPON_A"], weapon_ammo={"WEAPON_A": 37})
    store.save({"franklin": loadout})
    assert store.load()["franklin"].weapon_ammo == {"WEAPON_A": 37}
    raw = json.loads(path.read_text())
    assert raw["franklin"]["weapon_ammo"] == {"WEAPON_A": 37}

    loadout.weapon_ammo["WEAPON_A"] = -1
    with pytest.raises(ValueError, match="ammunition"):
        store.save({"franklin": loadout})


def test_weapon_customization_round_trip_is_preserved_by_launcher(tmp_path):
    path = tmp_path / "characters.json"
    store = LoadoutStore(path, {"WEAPON_A"}, set())
    customization = {
        "owned_components": [123, 456],
        "active_components": {"2": 456},
        "owned_tints": [0, 3],
        "active_tint": 3,
    }
    store.save({"michael": CharacterLoadout(
        weapons=["WEAPON_A"], weapon_ammo={"WEAPON_A": 99},
        weapon_customizations={"WEAPON_A": customization})})
    assert store.load()["michael"].weapon_customizations == {
        "WEAPON_A": customization}


def test_loadout_rejects_unequipped_owned_gear(tmp_path):
    store = LoadoutStore(tmp_path / "loadouts.json", set(), {"ARMOR", "PARACHUTE"})
    loadout = CharacterLoadout(
        gear=["ARMOR", "PARACHUTE"], equipped_gear=["PARACHUTE"])
    with pytest.raises(ValueError, match="ARMOR"):
        store.save({"franklin": loadout})


def test_schema_five_migration_discards_unequipped_gear(tmp_path):
    path = tmp_path / "loadouts.json"
    path.write_text(json.dumps({"franklin": {
        "schema_version": 5,
        "gear": ["ARMOR", "PARACHUTE"],
        "equipped_gear": ["PARACHUTE"],
    }}))
    loaded = LoadoutStore(path, set(), {"ARMOR", "PARACHUTE"}).load()["franklin"]
    assert loaded.gear == ["PARACHUTE"]
    assert loaded.equipped_gear == ["PARACHUTE"]


def test_loadout_rejects_equipped_gear_that_is_not_owned(tmp_path):
    store = LoadoutStore(tmp_path / "loadouts.json", set(), {"ARMOR"})
    with pytest.raises(ValueError, match="ARMOR"):
        store.save({"michael": CharacterLoadout(equipped_gear=["ARMOR"])})


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
