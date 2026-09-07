"""Generate the reviewed supplemental roster without enabling ambient traffic."""
from __future__ import annotations

import json
import re
from pathlib import Path

from allin1.vehicle_catalog import VEHICLE_CATEGORIES


def generate(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported catalog-only schema")
    rows = document["vehicles"]
    seen = set()
    lines = ["// Generated from data/catalog_only_vehicles.json. Reviewed storage/prices; no ambient traffic.",
             "using System;", "using System.Collections.Generic;", "", "namespace ALLIN1", "{",
             "    internal static class CatalogOnlyVehicles", "    {",
             "        internal const string Storage = \"catalog_only\";",
             "        internal static readonly IReadOnlyDictionary<string, GbayVehicleRecord> Records =",
             "            new Dictionary<string, GbayVehicleRecord>(StringComparer.OrdinalIgnoreCase)",
             "            {"]
    for row in sorted(rows, key=lambda row: row["model"]):
        model = row["model"]
        if not re.fullmatch(r"[a-z0-9_]{1,64}", model) or model in seen:
            raise ValueError("Invalid or duplicate catalog-only model")
        if row["category"] not in VEHICLE_CATEGORIES or not row["name"]:
            raise ValueError("Invalid catalog-only name/category")
        seen.add(model)
        storage, price = row.get("storage", "catalog_only"), row.get("price", 0)
        tier = row.get("size_tier", 0)
        expected = {"boats": "harbour", "helicopters": "helipad"}.get(row["category"], "garage")
        if storage not in {"catalog_only", expected} or row["category"] in {"planes", "special"} and storage != "catalog_only":
            raise ValueError("Unsupported supplemental delivery route")
        if type(price) is not int or not (price == 0 if storage == "catalog_only" else 1 <= price <= 100000000):
            raise ValueError("Supplemental purchase requires a reviewed positive price")
        if type(tier) is not int or tier not in {0, 1, 2}:
            raise ValueError("Invalid supplemental size tier")
        def quote(value):
            return json.dumps(value, ensure_ascii=True)
        args = ["allin1.online-content", "catalog-only", model, row["name"],
                row["manufacturer"], row["category"]]
        lines.append("                { " + quote(model) + ", new GbayVehicleRecord(" +
                     ", ".join(map(quote, args)) + f", {price}, " + quote(storage) + ", " +
                     quote(row["source_pack"]) + f", {tier}, null, null, false, 1.0) }},")
    lines.extend(["            };", "    }", "}", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[3]
    print(generate(root / "data/catalog_only_vehicles.json"), end="")
