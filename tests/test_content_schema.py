from __future__ import annotations

import json
from pathlib import Path

from allin1.extensions import ExtensionManifest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "content" / "allin1-content.schema.json"


def test_content_schema_declares_the_parser_supported_workbench_shape() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["workbench"] == {"$ref": "#/$defs/workbench"}

    definitions = schema["$defs"]
    workbench = definitions["workbench"]
    enhancement = definitions["weaponEnhancement"]
    component = definitions["weaponComponentLink"]
    progression = definitions["visualAssetProgression"]
    assert workbench["additionalProperties"] is False
    assert workbench["properties"]["weapon_enhancements"]["items"] == {
        "$ref": "#/$defs/weaponEnhancement"
    }
    assert set(enhancement["required"]) == {
        "id", "name", "mode", "weapon_components",
        "script_entry_points", "visual_assets",
    }
    assert enhancement["properties"]["mode"]["const"] == (
        "scripted_vanilla_components"
    )
    assert set(component["required"]) == {
        "weapon_name", "weapon_hash", "component_name", "component_hash",
    }
    assert set(progression["required"]) == {
        "dlc_pack", "archive", "families", "levels", "model_pattern",
        "texture_dictionary", "texture_pattern", "archetype_dictionary",
    }
    assert {item["type"] for item in progression["properties"][
        "base_model_pattern"
    ]["anyOf"]} == {"string", "null"}


def test_parser_accepts_the_schema_documented_workbench_contract() -> None:
    manifest = {
        "schema_version": 1,
        "api_version": 1,
        "id": "example.weapon-visuals",
        "name": "Example weapon visuals",
        "version": "1.0.0",
        "runtime": {
            "assemblies": [{
                "path": "scripts/Example/Example.dll",
                "entry_point": "Example.Runtime.Controller",
            }]
        },
        "workbench": {
            "weapon_enhancements": [{
                "id": "example.suppressor-heat",
                "name": "Suppressor heat",
                "mode": "scripted_vanilla_components",
                "weapon_components": [{
                    "weapon_name": "WEAPON_PISTOL",
                    "weapon_hash": "0x1B06D571",
                    "component_name": "COMPONENT_AT_PI_SUPP_02",
                    "component_hash": "0x65EA7EBB",
                }],
                "script_entry_points": ["Example.Runtime.Controller"],
                "visual_assets": [{
                    "dlc_pack": "example_heat",
                    "archive": "mods/update/x64/dlcpacks/example_heat/dlc.rpf",
                    "families": ["pistol"],
                    "levels": 24,
                    "model_pattern": "example_{family}_{level:02d}",
                    "texture_dictionary": "example_heat.ytd",
                    "texture_pattern": "example_gradient_{level:02d}",
                    "archetype_dictionary": "example_heat.ytyp",
                }],
            }]
        },
    }
    parsed = ExtensionManifest.from_dict(manifest)
    enhancement = parsed.workbench_weapon_enhancements[0]
    assert enhancement.enhancement_id == "example.suppressor-heat"
    assert enhancement.visual_assets[0].levels == 24
    assert parsed.to_dict()["workbench"]["weapon_enhancements"][0][
        "visual_assets"
    ][0]["base_model_pattern"] is None
