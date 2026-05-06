"""Generate VehicleList.cs from data/vehicles.toml + prices.toml.

Produces a C# static class with:
- Per-class string arrays (model names)
- All[] master array
- DisplayNames dictionary (model -> display name)
- Prices dictionary (model -> price in dollars)
"""

from __future__ import annotations

from pathlib import Path

from allin1.config import load_prices
from allin1.vehicles.database import VehicleDatabase

# Map TOML class names to C# array names.
CLASS_NAMES: dict[str, str] = {
    "boats": "Boats",
    "compacts": "Compacts",
    "coupes": "Coupes",
    "cycles": "Cycles",
    "emergency": "Emergency",
    "helicopters": "Helicopters",
    "industrial": "Industrial",
    "military": "Military",
    "motorcycles": "Motorcycles",
    "muscle": "Muscle",
    "offroad": "Offroad",
    "openwheel": "Openwheel",
    "planes": "Planes",
    "sedans": "Sedans",
    "service": "Service",
    "special": "Special",
    "sportsclassics": "Sportsclassics",
    "super": "Super",
    "suvs": "Suvs",
    "vans": "Vans",
}


def generate(db: VehicleDatabase, prices: dict[str, int]) -> str:
    """Return the full VehicleList.cs source as a string."""
    lines: list[str] = []
    w = lines.append

    w("// VehicleList.cs - Auto-generated from data/vehicles.toml + prices.toml")
    w(f"// {len(db)} GTA Online DLC vehicles by class.")
    w("using System.Collections.Generic;")
    w("")
    w("namespace ALLIN1")
    w("{")
    w("    internal static class VehicleList")
    w("    {")

    # --- All[] master array ---
    all_models = [v.model for v in db.all_vehicles]
    w("        internal static readonly string[] All = {")
    for model in all_models:
        w(f'            "{model}",')
    w("        };")
    w("")

    # --- Per-class arrays ---
    for cls_key in sorted(CLASS_NAMES.keys()):
        cs_name = CLASS_NAMES[cls_key]
        vehicles = db.by_class(cls_key)
        if not vehicles:
            continue
        w(f"        internal static readonly string[] {cs_name} = {{")
        for v in vehicles:
            w(f'            "{v.model}",')
        w("        };")
        w("")

    # Deduplicate by model name — vehicles can appear in multiple classes
    # but dictionary keys must be unique.
    seen: set[str] = set()
    unique_vehicles = []
    for v in db.all_vehicles:
        if v.model not in seen:
            seen.add(v.model)
            unique_vehicles.append(v)

    # --- DisplayNames dictionary ---
    w("        internal static readonly Dictionary<string, string> DisplayNames = new Dictionary<string, string>")
    w("        {")
    for v in unique_vehicles:
        escaped = v.name.replace('"', '\\"')
        w(f'            {{ "{v.model}", "{escaped}" }},')
    w("        };")
    w("")

    # --- Prices dictionary ---
    w("        internal static readonly Dictionary<string, int> Prices = new Dictionary<string, int>")
    w("        {")
    for v in unique_vehicles:
        price = prices.get(v.model, 0)
        w(f'            {{ "{v.model}", {price} }},')
    w("        };")
    w("")

    # --- ClassNames dictionary (model -> class display name) ---
    w("        internal static readonly Dictionary<string, string> ClassNames = new Dictionary<string, string>")
    w("        {")
    for v in unique_vehicles:
        cs_name = CLASS_NAMES.get(v.vehicle_class, v.vehicle_class.capitalize())
        w(f'            {{ "{v.model}", "{cs_name}" }},')
    w("        };")

    w("    }")
    w("}")
    w("")

    return "\n".join(lines)


def generate_file(
    vehicles_path: Path,
    prices_path: Path,
    output_path: Path,
) -> int:
    """Generate VehicleList.cs and write it to output_path.

    Returns the number of vehicles written.
    """
    db = VehicleDatabase.load(vehicles_path)
    prices = load_prices(prices_path)
    source = generate(db, prices)
    output_path.write_text(source, encoding="utf-8")
    return len(db)
