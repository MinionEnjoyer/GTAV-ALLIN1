"""Safe persistence for launcher-managed character customization."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

CHARACTERS = ("michael", "franklin", "trevor")
LOADOUT_SCHEMA_VERSION = 2
GARAGE_SCHEMA_VERSION = 2


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


@dataclass
class CharacterOutfit:
    managed: bool = False
    unlock_all: bool = False
    components: list[OutfitVariation] = field(
        default_factory=lambda: [OutfitVariation() for _ in range(12)])
    props: list[OutfitVariation] = field(
        default_factory=lambda: [OutfitVariation(-1, 0) for _ in range(8)])
    presets: dict[str, dict] = field(default_factory=dict)


@dataclass
class CharacterLoadout:
    weapons: list[str] = field(default_factory=list)
    gear: list[str] = field(default_factory=list)
    managed: bool = False
    outfit: CharacterOutfit = field(default_factory=CharacterOutfit)


class LoadoutStore:
    def __init__(self, path: Path, valid_weapons: set[str], valid_gear: set[str]) -> None:
        self.path = path
        self.valid_weapons = valid_weapons
        self.valid_gear = valid_gear

    def load(self) -> dict[str, CharacterLoadout]:
        raw = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        result = {}
        for character in CHARACTERS:
            item = raw.get(character, {})
            outfit_raw = item.get("outfit", {})
            components = [OutfitVariation(int(v.get("drawable", 0)), int(v.get("texture", 0)))
                          for v in outfit_raw.get("components", [])]
            props = [OutfitVariation(int(v.get("drawable", -1)), int(v.get("texture", 0)))
                     for v in outfit_raw.get("props", [])]
            result[character] = CharacterLoadout(
                list(dict.fromkeys(item.get("weapons", []))),
                list(dict.fromkeys(item.get("gear", []))),
                bool(item.get("managed", False)),
                CharacterOutfit(
                    bool(outfit_raw.get("managed", False)),
                    bool(outfit_raw.get("unlock_all", False)),
                    components or [OutfitVariation() for _ in range(12)],
                    props or [OutfitVariation(-1, 0) for _ in range(8)],
                    dict(outfit_raw.get("presets", {})),
                ),
            )
        return result

    def save(self, loadouts: dict[str, CharacterLoadout]) -> None:
        unknown_characters = set(loadouts) - set(CHARACTERS)
        if unknown_characters:
            raise ValueError(f"Unknown characters: {sorted(unknown_characters)}")
        output = {}
        for character in CHARACTERS:
            loadout = loadouts.get(character, CharacterLoadout())
            bad_weapons = set(loadout.weapons) - self.valid_weapons
            bad_gear = set(loadout.gear) - self.valid_gear
            if bad_weapons or bad_gear:
                raise ValueError(f"Unknown inventory items: {sorted(bad_weapons | bad_gear)}")
            self._validate_outfit(loadout.outfit)
            output[character] = {
                "weapons": sorted(set(loadout.weapons)),
                "gear": sorted(set(loadout.gear)),
                "managed": loadout.managed,
                "outfit": {
                    "managed": loadout.outfit.managed,
                    "unlock_all": loadout.outfit.unlock_all,
                    "components": [vars(value) for value in loadout.outfit.components],
                    "props": [vars(value) for value in loadout.outfit.props],
                    "presets": loadout.outfit.presets,
                },
                "schema_version": LOADOUT_SCHEMA_VERSION,
            }
        _atomic_json(self.path, output)

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
            "components": [vars(value).copy() for value in outfit.components],
            "props": [vars(value).copy() for value in outfit.props],
        }

    @staticmethod
    def apply_preset(outfit: CharacterOutfit, name: str) -> None:
        if name not in outfit.presets:
            raise KeyError(name)
        preset = outfit.presets[name]
        outfit.components = [OutfitVariation(**value) for value in preset["components"]]
        outfit.props = [OutfitVariation(**value) for value in preset["props"]]
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
