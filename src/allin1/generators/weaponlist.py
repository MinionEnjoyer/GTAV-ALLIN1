"""Generate WeaponList.cs from data/weapons.toml + prices_weapons.toml.

Produces a C# static class with:
- Per-category string arrays (weapon internal names)
- All[] master array
- DisplayNames dictionary (weapon name -> display label)
- Prices dictionary (weapon name -> price in dollars)
- CategoryNames dictionary (weapon name -> category display name)
"""

from __future__ import annotations

from pathlib import Path

from allin1.config import load_prices

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11


# Map TOML category keys to C# array names and display labels.
CATEGORY_NAMES: dict[str, tuple[str, str]] = {
    "pistols":     ("Pistols",     "Pistols"),
    "smgs":        ("Smgs",        "SMGs"),
    "shotguns":    ("Shotguns",    "Shotguns"),
    "rifles":      ("Rifles",      "Assault Rifles"),
    "machineguns": ("MachineGuns", "Machine Guns"),
    "snipers":     ("Snipers",     "Sniper Rifles"),
    "heavy":       ("Heavy",       "Heavy Weapons"),
    "melee":       ("Melee",       "Melee"),
    "throwables":  ("Throwables",  "Throwables"),
    "misc":        ("Misc",        "Miscellaneous"),
}


def generate(weapons_path: Path, prices: dict[str, int]) -> str:
    """Return the full WeaponList.cs source as a string."""
    with open(weapons_path, "rb") as f:
        data = tomllib.load(f)

    weapons = data.get("weapons", [])

    # Group by category
    by_category: dict[str, list[dict]] = {}
    for w in weapons:
        cat = w["category"]
        by_category.setdefault(cat, []).append(w)

    lines: list[str] = []
    a = lines.append

    a("// WeaponList.cs - Auto-generated from data/weapons.toml + prices_weapons.toml")
    a(f"// {len(weapons)} GTA Online weapons by category.")
    a("using System.Collections.Generic;")
    a("")
    a("namespace ALLIN1")
    a("{")
    a("    internal static class WeaponList")
    a("    {")

    # --- All[] master array ---
    a("        internal static readonly string[] All = {")
    for w in weapons:
        a(f'            "{w["name"]}",')
    a("        };")
    a("")

    # --- Per-category arrays ---
    for cat_key in CATEGORY_NAMES:
        cs_name, _ = CATEGORY_NAMES[cat_key]
        cat_weapons = by_category.get(cat_key, [])
        if not cat_weapons:
            continue
        a(f"        internal static readonly string[] {cs_name} = {{")
        for w in cat_weapons:
            a(f'            "{w["name"]}",')
        a("        };")
        a("")

    # --- DisplayNames dictionary ---
    a("        internal static readonly Dictionary<string, string> DisplayNames = new Dictionary<string, string>")
    a("        {")
    for w in weapons:
        escaped = w["label"].replace('"', '\\"')
        a(f'            {{ "{w["name"]}", "{escaped}" }},')
    a("        };")
    a("")

    # --- Prices dictionary ---
    # prices_weapons.toml overrides; fall back to inline price from weapons.toml
    a("        internal static readonly Dictionary<string, int> Prices = new Dictionary<string, int>")
    a("        {")
    for w in weapons:
        price = prices.get(w["name"], w["price"])
        a(f'            {{ "{w["name"]}", {price} }},')
    a("        };")
    a("")

    # --- CategoryNames dictionary (weapon name -> category display name) ---
    a("        internal static readonly Dictionary<string, string> CategoryNames = new Dictionary<string, string>")
    a("        {")
    for w in weapons:
        _, display_label = CATEGORY_NAMES.get(w["category"], (w["category"], w["category"]))
        a(f'            {{ "{w["name"]}", "{display_label}" }},')
    a("        };")

    a("    }")
    a("}")
    a("")

    return "\n".join(lines)


def generate_file(weapons_path: Path, prices_path: Path, output_path: Path) -> int:
    """Generate WeaponList.cs and write it to output_path.

    Returns the number of weapons written.
    """
    prices = load_prices(prices_path)

    with open(weapons_path, "rb") as f:
        data = tomllib.load(f)

    count = len(data.get("weapons", []))
    source = generate(weapons_path, prices)
    output_path.write_text(source, encoding="utf-8")
    return count
