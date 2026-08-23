"""Safe persistence for launcher-managed character customization."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

CHARACTERS = ("michael", "franklin", "trevor")
LOADOUT_SCHEMA_VERSION = 8
GARAGE_SCHEMA_VERSION = 2
SKILLS = ("stamina", "strength", "lung_capacity", "driving", "flying", "shooting", "stealth")

_CHARACTER_FIELDS = frozenset({
    "weapons", "weapon_ammo", "weapon_customizations", "gear",
    "equipped_gear", "properties", "smoke_grenades", "active_smoke_color",
    "managed", "outfit", "progress", "schema_version",
})
_OUTFIT_FIELDS = frozenset({
    "managed", "unlock_all", "components", "props", "presets",
})
_PROGRESS_FIELDS = frozenset({"managed", "money", "skills"})
_VARIATION_FIELDS = frozenset({"drawable", "texture"})


def _unknown_fields(value: object, known: frozenset[str] | tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        key: deepcopy(item)
        for key, item in value.items()
        if key not in known
    }


def _with_known_fields(
    extra_fields: dict[str, object], known_fields: dict[str, object],
) -> dict[str, object]:
    result = deepcopy(extra_fields)
    result.update(known_fields)
    return result


@dataclass(frozen=True)
class GarageRepairReport:
    kept: int
    reassigned: int
    quarantined: int
    quarantine_path: Path | None


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup = path.with_suffix(path.suffix + ".bak")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    if path.exists():
        shutil.copy2(path, backup)
    temporary.replace(path)


@dataclass
class OutfitVariation:
    drawable: int = 0
    texture: int = 0
    extra_fields: dict[str, object] = field(default_factory=dict)


@dataclass
class CharacterOutfit:
    managed: bool = False
    unlock_all: bool = False
    components: list[OutfitVariation] = field(
        default_factory=lambda: [OutfitVariation() for _ in range(12)])
    props: list[OutfitVariation] = field(
        default_factory=lambda: [OutfitVariation(-1, 0) for _ in range(8)])
    presets: dict[str, dict] = field(default_factory=dict)
    extra_fields: dict[str, object] = field(default_factory=dict)


@dataclass
class CharacterProgress:
    managed: bool = False
    money: int = 0
    skills: dict[str, int] = field(default_factory=lambda: {name: 0 for name in SKILLS})
    extra_skills: dict[str, object] = field(default_factory=dict)
    extra_fields: dict[str, object] = field(default_factory=dict)


@dataclass
class CharacterLoadout:
    weapons: list[str] = field(default_factory=list)
    gear: list[str] = field(default_factory=list)
    managed: bool = False
    outfit: CharacterOutfit = field(default_factory=CharacterOutfit)
    progress: CharacterProgress = field(default_factory=CharacterProgress)
    equipped_gear: list[str] = field(default_factory=list)
    weapon_ammo: dict[str, int] = field(default_factory=dict)
    weapon_customizations: dict[str, dict] = field(default_factory=dict)
    properties: list[str] = field(default_factory=list)
    smoke_grenades: dict[str, int] = field(default_factory=dict)
    active_smoke_color: str = "white"
    schema_version: int = LOADOUT_SCHEMA_VERSION
    extra_fields: dict[str, object] = field(default_factory=dict)


def _load_variation(value: object, default_drawable: int) -> OutfitVariation:
    raw = value if isinstance(value, dict) else {}
    return OutfitVariation(
        int(raw.get("drawable", default_drawable)),
        int(raw.get("texture", 0)),
        _unknown_fields(raw, _VARIATION_FIELDS),
    )


def _serialize_variation(
    value: OutfitVariation, existing: object | None = None,
) -> dict[str, object]:
    preserved = _unknown_fields(existing, _VARIATION_FIELDS)
    preserved.update(deepcopy(value.extra_fields))
    return _with_known_fields(preserved, {
        "drawable": value.drawable,
        "texture": value.texture,
    })


class LoadoutStore:
    def __init__(self, path: Path, valid_weapons: set[str], valid_gear: set[str]) -> None:
        self.path = path
        self.valid_weapons = valid_weapons
        self.valid_gear = valid_gear
        self._root_extra_fields: dict[str, object] = {}
        self._loaded = False

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Character save root must be an object")
        return raw

    def load(self) -> dict[str, CharacterLoadout]:
        raw = self._read()
        self._root_extra_fields = _unknown_fields(raw, CHARACTERS)
        self._loaded = True
        result = {}
        for character in CHARACTERS:
            item = raw.get(character, {})
            if not isinstance(item, dict):
                raise ValueError(f"Character state for {character} must be an object")
            weapons = list(dict.fromkeys(item.get("weapons", [])))
            gear = list(dict.fromkeys(item.get("gear", [])))
            schema_version = int(item.get("schema_version", 0))
            equipped_source = item.get("equipped_gear", []) or []
            if schema_version < 4:
                equipped_source = gear
            owned_gear = set(gear)
            equipped_gear = [
                value
                for value in dict.fromkeys(equipped_source)
                if value in owned_gear
            ]
            # Gear is consumable as of schema 6. An item remains owned only
            # while equipped; older unequipped locker entries are discarded.
            gear = list(equipped_gear)
            ammo_source = item.get("weapon_ammo", {}) or {}
            if schema_version < 5:
                weapon_ammo = {weapon: 9999 for weapon in weapons}
            else:
                weapon_ammo = {
                    weapon: max(0, int(ammo_source.get(weapon, 9999)))
                    for weapon in weapons
                }
            customization_source = item.get("weapon_customizations", {}) or {}
            weapon_customizations = {
                weapon: dict(value)
                for weapon, value in customization_source.items()
                if weapon in weapons and isinstance(value, dict)
            }
            outfit_raw = item.get("outfit", {})
            if not isinstance(outfit_raw, dict):
                outfit_raw = {}
            components = [
                _load_variation(value, 0)
                for value in outfit_raw.get("components", [])
            ]
            props = [
                _load_variation(value, -1)
                for value in outfit_raw.get("props", [])
            ]
            progress_raw = item.get("progress", {})
            if not isinstance(progress_raw, dict):
                progress_raw = {}
            skills_raw = progress_raw.get("skills", {})
            if not isinstance(skills_raw, dict):
                skills_raw = {}
            result[character] = CharacterLoadout(
                weapons,
                gear,
                bool(item.get("managed", False)),
                CharacterOutfit(
                    bool(outfit_raw.get("managed", False)),
                    bool(outfit_raw.get("unlock_all", False)),
                    components or [OutfitVariation() for _ in range(12)],
                    props or [OutfitVariation(-1, 0) for _ in range(8)],
                    deepcopy(outfit_raw.get("presets", {})),
                    _unknown_fields(outfit_raw, _OUTFIT_FIELDS),
                ),
                CharacterProgress(
                    bool(progress_raw.get("managed", False)),
                    int(progress_raw.get("money", 0)),
                    {
                        name: int(skills_raw.get(name, 0))
                        for name in SKILLS
                    },
                    _unknown_fields(skills_raw, SKILLS),
                    _unknown_fields(progress_raw, _PROGRESS_FIELDS),
                ),
                equipped_gear,
                weapon_ammo,
                weapon_customizations,
                deepcopy(item.get("properties", [])),
                deepcopy(item.get("smoke_grenades", {})),
                str(item.get("active_smoke_color", "white")),
                max(LOADOUT_SCHEMA_VERSION, schema_version),
                _unknown_fields(item, _CHARACTER_FIELDS),
            )
        return result

    def save(self, loadouts: dict[str, CharacterLoadout]) -> None:
        unknown_characters = set(loadouts) - set(CHARACTERS)
        if unknown_characters:
            raise ValueError(f"Unknown characters: {sorted(unknown_characters)}")
        existing = {} if self._loaded else self._read()
        root_extra_fields = (
            self._root_extra_fields
            if self._loaded else _unknown_fields(existing, CHARACTERS)
        )
        output = deepcopy(root_extra_fields)
        for character in CHARACTERS:
            loadout = loadouts.get(character, CharacterLoadout())
            existing_item = existing.get(character, {})
            if not isinstance(existing_item, dict):
                existing_item = {}
            bad_weapons = set(loadout.weapons) - self.valid_weapons
            bad_gear = set(loadout.gear) - self.valid_gear
            bad_equipped = set(loadout.equipped_gear) - set(loadout.gear)
            unequipped_gear = set(loadout.gear) - set(loadout.equipped_gear)
            bad_ammo = set(loadout.weapon_ammo) - set(loadout.weapons)
            bad_customizations = set(loadout.weapon_customizations) - set(loadout.weapons)
            if bad_weapons or bad_gear or bad_equipped or unequipped_gear or bad_ammo or bad_customizations:
                raise ValueError(f"Unknown inventory items: "
                                 f"{sorted(bad_weapons | bad_gear | bad_equipped | unequipped_gear | bad_ammo | bad_customizations)}")
            if any(not isinstance(value, int) or value < 0
                   for value in loadout.weapon_ammo.values()):
                raise ValueError("Weapon ammunition must be a non-negative whole number")
            self._validate_outfit(loadout.outfit)
            self._validate_progress(loadout.progress)
            existing_outfit = existing_item.get("outfit", {})
            if not isinstance(existing_outfit, dict):
                existing_outfit = {}
            existing_components = existing_outfit.get("components", [])
            if not isinstance(existing_components, list):
                existing_components = []
            existing_props = existing_outfit.get("props", [])
            if not isinstance(existing_props, list):
                existing_props = []
            outfit_extra_fields = _unknown_fields(
                existing_outfit, _OUTFIT_FIELDS)
            outfit_extra_fields.update(deepcopy(loadout.outfit.extra_fields))

            existing_progress = existing_item.get("progress", {})
            if not isinstance(existing_progress, dict):
                existing_progress = {}
            existing_skills = existing_progress.get("skills", {})
            if not isinstance(existing_skills, dict):
                existing_skills = {}
            progress_extra_fields = _unknown_fields(
                existing_progress, _PROGRESS_FIELDS)
            progress_extra_fields.update(deepcopy(loadout.progress.extra_fields))
            extra_skills = _unknown_fields(existing_skills, SKILLS)
            extra_skills.update(deepcopy(loadout.progress.extra_skills))

            character_extra_fields = _unknown_fields(
                existing_item, _CHARACTER_FIELDS)
            character_extra_fields.update(deepcopy(loadout.extra_fields))
            output[character] = _with_known_fields(character_extra_fields, {
                "weapons": sorted(set(loadout.weapons)),
                "gear": sorted(set(loadout.gear)),
                "equipped_gear": sorted(set(loadout.equipped_gear)),
                "weapon_ammo": {
                    weapon: loadout.weapon_ammo.get(weapon, 9999)
                    for weapon in sorted(set(loadout.weapons))
                },
                "weapon_customizations": {
                    weapon: loadout.weapon_customizations[weapon]
                    for weapon in sorted(loadout.weapon_customizations)
                },
                "managed": loadout.managed,
                "properties": deepcopy(loadout.properties),
                "smoke_grenades": deepcopy(loadout.smoke_grenades),
                "active_smoke_color": loadout.active_smoke_color,
                "outfit": _with_known_fields(outfit_extra_fields, {
                    "managed": loadout.outfit.managed,
                    "unlock_all": loadout.outfit.unlock_all,
                    "components": [
                        _serialize_variation(
                            value,
                            existing_components[index]
                            if index < len(existing_components) else None,
                        )
                        for index, value in enumerate(loadout.outfit.components)
                    ],
                    "props": [
                        _serialize_variation(
                            value,
                            existing_props[index]
                            if index < len(existing_props) else None,
                        )
                        for index, value in enumerate(loadout.outfit.props)
                    ],
                    "presets": deepcopy(loadout.outfit.presets),
                }),
                "progress": _with_known_fields(progress_extra_fields, {
                    "managed": loadout.progress.managed,
                    "money": loadout.progress.money,
                    "skills": _with_known_fields(
                        extra_skills, deepcopy(loadout.progress.skills)),
                }),
                "schema_version": max(
                    LOADOUT_SCHEMA_VERSION, int(loadout.schema_version)),
            })
        _atomic_json(self.path, output)
        self._root_extra_fields = deepcopy(root_extra_fields)
        self._loaded = True

    @staticmethod
    def _validate_progress(progress: CharacterProgress) -> None:
        if not isinstance(progress.money, int) or not 0 <= progress.money <= 2_147_483_647:
            raise ValueError("Character money must be between 0 and 2,147,483,647")
        if set(progress.skills) != set(SKILLS):
            raise ValueError("Character progress must include every supported skill")
        if any(not isinstance(value, int) or not 0 <= value <= 100
               for value in progress.skills.values()):
            raise ValueError("Character skills must be whole numbers from 0 to 100")

    @staticmethod
    def _validate_outfit(outfit: CharacterOutfit) -> None:
        if len(outfit.components) != 12 or len(outfit.props) != 8:
            raise ValueError("Outfits require 12 component slots and 8 prop slots")
        for value in outfit.components:
            if value.drawable < 0 or value.texture < 0:
                raise ValueError("Component drawable and texture IDs cannot be negative")
        for value in outfit.props:
            if value.drawable < -1 or value.texture < 0:
                raise ValueError("Prop drawable must be -1 or greater; texture cannot be negative")
        for name in outfit.presets:
            if not name.strip() or len(name) > 64:
                raise ValueError("Outfit preset names must contain 1-64 characters")

    @staticmethod
    def save_preset(outfit: CharacterOutfit, name: str) -> None:
        name = name.strip()
        if not name or len(name) > 64:
            raise ValueError("Outfit preset names must contain 1-64 characters")
        outfit.presets[name] = {
            "components": [_serialize_variation(value) for value in outfit.components],
            "props": [_serialize_variation(value) for value in outfit.props],
        }

    @staticmethod
    def apply_preset(outfit: CharacterOutfit, name: str) -> None:
        if name not in outfit.presets:
            raise KeyError(name)
        preset = outfit.presets[name]
        outfit.components = [
            _load_variation(value, 0) for value in preset["components"]
        ]
        outfit.props = [
            _load_variation(value, -1) for value in preset["props"]
        ]
        LoadoutStore._validate_outfit(outfit)


class GarageSaveStore:
    """Edit/import/export ALLIN1 garage saves without touching GTA savegames."""

    def __init__(self, path: Path, valid_models: set[str]) -> None:
        self.path = path
        self.valid_models = valid_models

    def load(self) -> dict[str, list[dict]]:
        if not self.path.exists():
            return {character: [] for character in CHARACTERS}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Garage save root must be an object")
        result = {character: list(raw.get(character, [])) for character in CHARACTERS}
        self.validate(result)
        return result

    def validate(self, garages: dict[str, list[dict]]) -> None:
        for character in CHARACTERS:
            vehicles = garages.get(character, [])
            if len(vehicles) > 10:
                raise ValueError(f"{character} garage exceeds 10 vehicles")
            slots: set[int] = set()
            for vehicle in vehicles:
                model, slot = vehicle.get("model"), vehicle.get("slot")
                if model not in self.valid_models:
                    raise ValueError(f"Unknown vehicle model: {model}")
                if not isinstance(slot, int) or not 0 <= slot < 10 or slot in slots:
                    raise ValueError(f"Invalid or duplicate garage slot: {slot}")
                slots.add(slot)

    def save(self, garages: dict[str, list[dict]]) -> None:
        self.validate(garages)
        output = {"_schema_v2": []}
        output.update({c: garages.get(c, []) for c in CHARACTERS})
        _atomic_json(self.path, output)

    def import_file(self, source: Path) -> None:
        candidate = GarageSaveStore(source, self.valid_models).load()
        self.save(candidate)

    def export_file(self, destination: Path) -> None:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, destination)

    def repair(self, quarantine_path: Path | None = None) -> GarageRepairReport:
        """Salvage valid vehicles, reassign bad slots, and quarantine rejected data."""
        if not self.path.exists():
            return GarageRepairReport(0, 0, 0, None)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rejected = [{"reason": "invalid_json", "value": str(exc)}]
            raw = {}
        else:
            rejected = []
            if not isinstance(raw, dict):
                rejected.append({"reason": "invalid_root", "value": raw})
                raw = {}
        repaired = {character: [] for character in CHARACTERS}
        reassigned = 0
        for character in CHARACTERS:
            entries = raw.get(character, [])
            if not isinstance(entries, list):
                rejected.append({"character": character, "reason": "invalid_list", "value": entries})
                continue
            used: set[int] = set()
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("model") not in self.valid_models:
                    rejected.append({"character": character, "reason": "invalid_vehicle", "value": entry})
                    continue
                if len(repaired[character]) >= 10:
                    rejected.append({"character": character, "reason": "garage_full", "value": entry})
                    continue
                candidate = entry.get("slot")
                if not isinstance(candidate, int) or not 0 <= candidate < 10 or candidate in used:
                    candidate = next(slot for slot in range(10) if slot not in used)
                    reassigned += 1
                clean = dict(entry)
                clean["slot"] = candidate
                used.add(candidate)
                repaired[character].append(clean)
        self.save(repaired)
        written: Path | None = None
        if rejected:
            written = quarantine_path or self.path.with_name(self.path.stem + ".quarantine.json")
            _atomic_json(written, {"schema_version": 1, "rejected": rejected})
        return GarageRepairReport(sum(map(len, repaired.values())), reassigned,
                                  len(rejected), written)
