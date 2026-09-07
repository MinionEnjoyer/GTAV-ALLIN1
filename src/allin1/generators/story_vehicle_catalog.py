"""Generate the trusted GBAY Story Vehicles catalog from base vehicles.meta.

The generator intentionally emits an allowlist rather than every model in the
archive.  Trains, trailers, aircraft without supported ALLIN1 storage, blimps,
and submersibles remain excluded.  Display labels are only fallbacks; the game
client resolves localized native labels when the catalog is loaded.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from allin1.vehicle_catalog import VehicleCatalog


SUPPORTED_TYPES = frozenset({
    "VEHICLE_TYPE_BICYCLE",
    "VEHICLE_TYPE_BIKE",
    "VEHICLE_TYPE_BOAT",
    "VEHICLE_TYPE_CAR",
    "VEHICLE_TYPE_HELI",
    "VEHICLE_TYPE_QUADBIKE",
})

CLASS_CATEGORIES = {
    "VC_BOAT": "boats",
    "VC_COMMERCIAL": "industrial",
    "VC_COMPACT": "compacts",
    "VC_COUPE": "coupes",
    "VC_CYCLE": "cycles",
    "VC_EMERGENCY": "emergency",
    "VC_HELICOPTER": "helicopters",
    "VC_INDUSTRIAL": "industrial",
    "VC_MILITARY": "military",
    "VC_MOTORCYCLE": "motorcycles",
    "VC_MUSCLE": "muscle",
    "VC_OFF_ROAD": "offroad",
    "VC_SEDAN": "sedans",
    "VC_SERVICE": "service",
    "VC_SPORT": "sports",
    "VC_SPORT_CLASSIC": "sportsclassics",
    "VC_SUPER": "super",
    "VC_SUV": "suvs",
    "VC_UTILITY": "service",
    "VC_VAN": "vans",
}

CLASS_PRICES = {
    "compacts": 18_000,
    "coupes": 42_000,
    "sedans": 30_000,
    "suvs": 48_000,
    "muscle": 55_000,
    "sports": 125_000,
    "sportsclassics": 165_000,
    "super": 500_000,
    "offroad": 55_000,
    "motorcycles": 25_000,
    "vans": 38_000,
    "boats": 85_000,
    "helicopters": 450_000,
    "military": 650_000,
    "industrial": 95_000,
    "emergency": 135_000,
    "cycles": 1_000,
    "service": 45_000,
}

MAKE_LABELS = {
    "BF": "BF",
    "HVY": "HVY",
    "LCC": "LCC",
    "MTL": "MTL",
    "OBEY": "Obey",
    "OCELOT": "Ocelot",
    "PFISTER": "Pfister",
    "TRUFFADE": "Truffade",
    "UBERMACHT": "Ubermacht",
}


def _text(item: ET.Element, name: str) -> str:
    node = item.find(name)
    return "" if node is None or node.text is None else node.text.strip()


def _fallback_label(value: str) -> str:
    if not value:
        return ""
    return value.replace("_", " ").strip().title()


def build_story_catalog(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    vehicles: list[dict[str, Any]] = []
    for item in root.findall("./InitDatas/Item"):
        model = _text(item, "modelName").lower()
        vehicle_type = _text(item, "type").upper()
        category = CLASS_CATEGORIES.get(_text(item, "vehicleClass").upper())
        if not model or vehicle_type not in SUPPORTED_TYPES or category is None:
            continue
        storage = (
            "harbour" if vehicle_type == "VEHICLE_TYPE_BOAT"
            else "helipad" if vehicle_type == "VEHICLE_TYPE_HELI"
            else "garage"
        )
        game_label = _text(item, "gameName") or model
        make_label = _text(item, "vehicleMakeName")
        vehicles.append({
            "model": model,
            "name": {"dune2": "Space Docker", "jb700": "JB 700",
                     "ztype": "Z-Type", "entityxf": "Entity XF"}.get(model, _fallback_label(game_label)),
            "manufacturer": MAKE_LABELS.get(make_label, _fallback_label(make_label)),
            "category": category,
            "price": CLASS_PRICES[category],
            "storage": storage,
            "source_pack": "base",
            "size_tier": 0,
            "traffic": {"enabled": False, "weight": 1.0},
        })
    vehicles.sort(key=lambda value: (value["category"], value["model"]))
    payload = {
        "schema_version": 1,
        "id": "story-vehicles",
        "name": "GTA V Story Vehicles",
        "vehicles": vehicles,
    }
    # Keep the checked-in generator and the launcher's parser on one contract.
    VehicleCatalog.from_dict(payload).validate_package_ownership(
        (), allow_base_game=True,
    )
    return payload


def extract_base_vehicle_meta(
    rpf_patcher: Path, gta_path: Path,
) -> str:
    archive = gta_path / "update" / "update.rpf"
    completed = subprocess.run(
        [str(rpf_patcher), "inspect", str(gta_path), str(archive)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    marker = (
        str(archive / "common" / "data" / "levels" / "gta5" / "vehicles.meta")
        .replace("/", "\\")
        .casefold()
    )
    lines = completed.stdout.splitlines()
    start = next(
        (index + 1 for index, line in enumerate(lines)
         if line.startswith("--- ") and marker in line.casefold()),
        None,
    )
    if start is None:
        raise ValueError("Could not locate base vehicles.meta in the RPF inspection")
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("--- ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gta_path", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--rpf-patcher", type=Path,
        default=Path("tools/RpfPatcher/RpfPatcher.exe"),
    )
    args = parser.parse_args()
    payload = build_story_catalog(
        extract_base_vehicle_meta(args.rpf_patcher.resolve(), args.gta_path.resolve())
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(payload['vehicles'])} Story vehicle listings: {args.output}")


if __name__ == "__main__":
    main()
