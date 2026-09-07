"""Reproducible authored ALLIN1 balance pass, not GTA Online price claims.

Same-family prices are preferred; otherwise use existing category medians.
Special variants get explicit overrides. Runtime dimensions still decide fit.
"""
import json
import re
import statistics
import tomllib
from pathlib import Path
from allin1.generators.catalog_only_vehicles import generate

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = {
    "kosatka": "Submarine ownership is not implemented",
    "submersible": "Submersible storage is not implemented",
    "submersible2": "Submersible storage is not implemented",
    "minitank": "Remote-control vehicle, not regular garage delivery",
    "rcbandito": "Remote-control vehicle, not regular garage delivery",
    "ruiner3": "Wreck/mission model, not a complete road vehicle",
}
TRAILERS = set("armytanker armytrailer armytrailer2 baletrailer boattrailer boattrailer2 boattrailer3 docktrailer freighttrailer graintrailer proptrailer raketrailer tanker tanker2 tr2 tr3 tr4 trailerlarge trailerlogs trailers trailers2 trailers3 trailers4 trailers5 trailersmall trailersmall2 trflat trflat2 tvtrailer tvtrailer2".split())
OVERRIDES = {
    "zentorno": 725000, "turismor": 500000, "ignus2": 950000,
    "alpha": 125000, "panto": 18000, "rhapsody": 18000,
    "jester": 240000, "jester2": 270000, "massacro": 275000, "massacro2": 305000,
    "hakuchou": 82000, "innovation": 75000, "sanctus": 150000,
    "calico": 195000, "btype": 165000, "btype2": 250000, "btype3": 180000,
    "dukes2": 150000, "boxville5": 300000, "insurgent2": 450000,
    "technical2": 400000, "dune4": 450000, "monster": 250000,
    "monster4": 600000, "monster5": 600000, "dubsta3": 250000,
    "marshall": 250000, "zr380": 350000, "zr3802": 350000, "zr3803": 350000,
    "cerberus": 900000, "cerberus2": 900000, "cerberus3": 900000,
    "bruiser2": 650000, "bruiser3": 650000, "brutus2": 550000, "brutus3": 550000,
    "scarab2": 650000, "scarab3": 650000, "brickade2": 650000,
    "deathbike": 200000, "deathbike2": 200000, "deathbike3": 200000,
    "dominator4": 350000, "dominator5": 350000, "dominator6": 350000,
    "issi4": 180000, "issi5": 180000, "issi6": 180000,
    "impaler2": 350000, "impaler3": 350000, "impaler4": 350000,
    "imperator2": 350000, "imperator3": 350000,
    "slamvan4": 300000, "slamvan5": 300000, "slamvan6": 300000,
}

def main():
    source = ROOT / "data/catalog_only_vehicles.json"
    data = json.loads(source.read_text())
    prices = tomllib.loads((ROOT / "prices_vehicles.toml").read_text())
    anchors = {model: price for group in prices.values() if isinstance(group, dict)
               for model, price in group.items() if type(price) is int and price > 0}
    story = json.loads((ROOT / "data/story_vehicles.json").read_text())["vehicles"]
    anchors.update({row["model"]: row["price"] for row in story})
    defaults = {"boats":85000,"helicopters":450000,"industrial":95000,"military":650000,"service":45000}
    for category, group in prices.items():
        if isinstance(group, dict):
            values = [p for p in group.values() if type(p) is int and p > 0]
            if values: defaults[category] = int(round(statistics.median(values) / 500) * 500)
    for row in data["vehicles"]:
        model, category = row["model"], row["category"]
        reason = BLOCKED.get(model)
        if model in TRAILERS: reason = "Trailer storage/delivery is not implemented"
        if category == "planes": reason = "Aircraft hangar storage is not implemented"
        if category == "special": reason = "Rail/cable vehicle requires unsupported storage"
        if reason:
            row.update(price=0, storage="catalog_only", size_tier=0, purchase_audit=reason)
            continue
        family = re.sub(r"\d+$", "", model.removeprefix("drift"))
        price = OVERRIDES.get(model, anchors.get(model.removeprefix("drift"), anchors.get(family, defaults.get(category, 55000))))
        basis = "Authored variant balance" if model in OVERRIDES else (
            "Existing family price" if family in anchors or model.removeprefix("drift") in anchors else "Existing category median balance")
        if model.startswith("drift"):
            price += 25000
            basis += "; drift conversion +25000"
        storage = {"boats":"harbour", "helicopters":"helipad"}.get(category, "garage")
        tier = 2 if category in {"industrial", "military", "service"} or model in {"monster","monster4","monster5","marshall","bruiser2","bruiser3"} else 0
        row.update(price=price, storage=storage, size_tier=tier, purchase_audit=basis)
    data["description"] = "Reviewed 218-model supplement to the 935-model vanilla roster. Authored ALLIN1 prices; existing delivery and native size checks apply. No ambient traffic activation."
    source.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
    (ROOT / "script/src/CatalogOnlyVehicles.cs").write_text(generate(source), encoding="utf-8")
    from collections import Counter
    print(Counter(row["storage"] for row in data["vehicles"]))

if __name__ == "__main__": main()
