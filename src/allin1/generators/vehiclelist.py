"""Generate VehicleList.cs from data/vehicles.toml + prices_vehicles.toml.

Produces a C# static class with:
- Per-class string arrays (model names)
- All[] master array
- DisplayNames dictionary (model -> display name)
- Prices dictionary (model -> price in dollars)
- PreviewDict dictionary (model -> YTD texture dict name)
"""

from __future__ import annotations

from pathlib import Path

from allin1.config import load_prices
from allin1.vehicles.database import VehicleDatabase

# Number of textures packed into each .ytd file.  GTA V has a 16 MB per-ytd
# limit; at 512x256 DXT1 (~64 KB each) 89 textures ≈ 5.7 MB — well under.
TEXTURES_PER_YTD = 89
YTD_PREFIX = "allin1_prev"


def build_preview_dict(
    models: list[str],
    textures_per_ytd: int = TEXTURES_PER_YTD,
) -> dict[str, str]:
    """Map each model name to its containing YTD dict name.

    Models are sorted alphabetically and assigned to sequential dicts
    named ``allin1_prev_01``, ``allin1_prev_02``, etc.
    """
    mapping: dict[str, str] = {}
    for idx, model in enumerate(sorted(models)):
        dict_num = idx // textures_per_ytd + 1
        mapping[model] = f"{YTD_PREFIX}_{dict_num:02d}"
    return mapping


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

    w("// VehicleList.cs - Auto-generated from data/vehicles.toml + prices_vehicles.toml")
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

    # --- Weaponized array (cross-class, sorted by model) ---
    weaponized = sorted(
        [v for v in db.all_vehicles if v.weaponized],
        key=lambda v: v.model,
    )
    if weaponized:
        w("        internal static readonly string[] Weaponized = {")
        for v in weaponized:
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
    w("")

    # --- PreviewDict dictionary (model -> YTD texture dict name) ---
    preview_mapping = build_preview_dict([v.model for v in unique_vehicles])
    w("        internal static readonly Dictionary<string, string> PreviewDict = new Dictionary<string, string>")
    w("        {")
    for model, dict_name in sorted(preview_mapping.items()):
        w(f'            {{ "{model}", "{dict_name}" }},')
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

    # Height/size calibration is maintained from in-game measurements and is
    # intentionally not generated from vehicles.toml. Preserve that section
    # when refreshing the generated catalog instead of silently deleting it.
    marker = "        //  Vehicle size data (generated from HeightChecker measurements)"
    if output_path.exists():
        existing = output_path.read_text(encoding="utf-8")
        marker_index = existing.find(marker)
        if marker_index >= 0:
            calibrated_suffix = existing[marker_index:]
            generated_close = "    }\n}\n"
            if source.endswith(generated_close):
                source = source[: -len(generated_close)] + calibrated_suffix

    output_path.write_text(source, encoding="utf-8")
    return len(db)
