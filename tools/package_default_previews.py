"""Collect only validated, indexed vanilla PNGs. Never modify game previews."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from allin1.default_previews import BASE, CATEGORIES, OWNER, validate_archive
from allin1.prelaunch_previews import contained, document, existing_preview, sha
from allin1.stock_weapon_previews import catalog_names as weapon_names
from allin1.catalog_model_previews import catalog_names, GEAR_MODELS

ROOT = Path(__file__).resolve().parents[1]

def package(games, output, version):
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "version": version, "categories": {}}
    report = {}
    for category in CATEGORIES:
        wanted = {n.lower() for n in (weapon_names(ROOT) if category == "weapons" else catalog_names(ROOT, category))}
        if category == "gear": wanted.intersection_update(n.lower() for n in GEAR_MODELS)
        selected = {}
        for game in games:
            folder = contained(game, BASE + "/generated-" + category)
            if not (folder / "index.json").exists(): continue
            index = document(folder / "index.json")
            if index.get("owner") != "allin1.prelaunch-previews": raise ValueError("Unexpected source owner")
            for name in wanted:
                if name in selected: continue
                result = existing_preview(folder, index["images"], index["image_sha256"], name)
                if result:
                    filename = index["images"][name]
                    selected[name] = (contained(folder, filename), index["image_sha256"][filename])
        index = {"schema_version": 1, "owner": OWNER,
                 "images": {name: path.name for name, (path, _) in sorted(selected.items())},
                 "image_sha256": {path.name: digest for path, digest in selected.values()}}
        archive = output / f"gbay-{category}.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED) as packed:
            packed.writestr("index.json", json.dumps(index, sort_keys=True))
            for path, digest in selected.values():
                data = path.read_bytes()
                if hashlib.sha256(data).hexdigest() != digest: raise ValueError("Source changed during packaging")
                packed.writestr(path.name, data)
        asset = {"url": f"https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/download/{version}/{archive.name}",
                 "sha256": sha(archive), "bytes": archive.stat().st_size, "count": len(selected)}
        validate_archive(archive, asset)
        manifest["categories"][category] = asset
        report[category] = {"included": len(selected), "catalog_total": len(wanted), "missing": sorted(wanted - selected.keys())}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    (output / "inventory.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    package(args.game, args.output, args.version)
