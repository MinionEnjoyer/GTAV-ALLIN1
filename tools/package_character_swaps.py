"""Create private exact-member character-swap packages without modifying GTA V."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from allin1.mods import ModManifest
from allin1.mod_package_contract import split_nested_rpf_entry

_GEOMETRY_SPEC = importlib.util.spec_from_file_location(
    "build_character_appearance_geometry", ROOT / "tools" / "build_character_appearance.py",
)
if _GEOMETRY_SPEC is None or _GEOMETRY_SPEC.loader is None:
    raise RuntimeError("Character appearance geometry verifier is unavailable")
_geometry_builder = importlib.util.module_from_spec(_GEOMETRY_SPEC)
_GEOMETRY_SPEC.loader.exec_module(_geometry_builder)
verify_geometry_roundtrip = _geometry_builder.verify_geometry_roundtrip

PACKAGE_IDS = {"SpongeBob": "private.story-franklin-spongebob", "Patrick": "private.story-lamar-patrick",
               "Squidward": "private.story-stretch-squidward", "Mr Krabs": "private.story-d-krabs"}
MODEL_BUILD = {"player_one": "player_one", "ig_lamardavis": "ig_lamardavis", "cs_lamardavis": "cs_lamardavis",
               "ig_stretch": "ig_stretch", "cs_stretch": "cs_stretch", "ig_ballasog": "ig_ballasog", "csb_ballasog": "csb_ballasog"}
MODEL_CHARACTER = {"player_one": "SpongeBob", "ig_lamardavis": "Patrick", "cs_lamardavis": "Patrick",
                   "ig_stretch": "Squidward", "cs_stretch": "Squidward", "ig_ballasog": "Mr Krabs", "csb_ballasog": "Mr Krabs"}
_VERSION = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _inside(root: Path, path: Path) -> Path:
    root, path = root.resolve(), path.resolve()
    if not path.is_relative_to(root): raise ValueError("Path escapes its declared root")
    return path

def _xml(path: Path) -> etree._ElementTree:
    data = path.read_bytes()
    if len(data) > 64 * 1024 * 1024 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unsafe compiled asset XML")
    return etree.ElementTree(etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)))

def _targets(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("targets") if data.get("schema_version") == 1 else None
    if not isinstance(rows, list) or len(rows) != 50: raise ValueError("targets.json must contain exactly 50 schema-1 targets")
    required = {"character","model","member_role","mods_relative_target","nested_archive","entry","extracted_original","current_original_sha256"}
    if any(not required <= set(row) for row in rows): raise ValueError("Target record is missing exact-member provenance")
    keys={tuple(str(r[k]).casefold() for k in ("mods_relative_target","nested_archive","entry")) for r in rows}
    if len(keys)!=len(rows): raise ValueError("Target inventory contains duplicate exact members")
    for row in rows:
        archive = PurePosixPath(row["mods_relative_target"])
        if archive.is_absolute() or not archive.parts or archive.parts[0] != "mods" or ".." in archive.parts or "\\" in str(archive) or ":" in str(archive) or archive.suffix != ".rpf":
            raise ValueError("Target archive must be below mods")
        if MODEL_CHARACTER.get(row["model"]) != row["character"]:
            raise ValueError("Character/model mapping is not approved")
    return rows

def _version(value: str) -> str:
    if not isinstance(value, str) or _VERSION.fullmatch(value) is None:
        raise ValueError("Version must be a safe numeric x.y.z value")
    return value

def _preflight_builds(rows: list[dict], build_root: Path) -> None:
    for model in {r["model"] for r in rows}:
        build=_inside(build_root,build_root/MODEL_BUILD[model]); report_path=_inside(build,build/"report.json")
        report=json.loads(report_path.read_text(encoding="utf-8"))
        expected=model=="csb_ballasog"
        if report.get("target_model")!=model or report.get("nonstreamed") is not expected: raise ValueError("Build report target or streamed mode mismatch")
        hashes = report.get("compiled_sha256", {})
        outputs = report.get("outputs", {})
        if set(outputs) != {"ydd", "yft", "ymt", "ytd"} or len(hashes) != 4 or set(hashes) != set(outputs.values()):
            raise ValueError("Build report must checksum all four resources")
        for kind, expected_hash in hashes.items():
            compiled_root = build/"authoring"/"compiled"
            path=_inside(compiled_root,compiled_root/kind)
            if not path.is_file() or digest(path)!=expected_hash: raise ValueError("Build report compiled checksum mismatch")
        authored_root = _inside(build, build / "authoring" / "authored")
        verified_root = _inside(build, build / "authoring" / "verified")
        for resource in (outputs["ydd"], outputs["yft"]):
            authored = _inside(authored_root, authored_root / (resource + ".xml"))
            verified = _inside(verified_root, verified_root / (resource + ".xml"))
            if not authored.is_file() or not verified.is_file():
                raise FileNotFoundError("Build authoring geometry evidence is missing")
            verify_geometry_roundtrip(_xml(authored), _xml(verified),
                                      f"{model} {Path(resource).suffix[1:].upper()} preflight")
        for row in (r for r in rows if r["model"] == model):
            source = _compiled(build, row)
            if source.relative_to(build/"authoring"/"compiled").as_posix() not in hashes:
                raise ValueError("Selected resource is not covered by build report")

def _validate_output(output: Path, build_root: Path, game: Path) -> None:
    if output.is_relative_to(game) or (output.is_relative_to(build_root) and
            (output.parent != build_root or not output.name.startswith("packages"))):
        raise ValueError("Output may not be in GTA V or a build input")
    if build_root.is_relative_to(output):
        raise ValueError("Output may not contain build inputs")

def _compiled(build: Path, row: dict) -> Path:
    root = _inside(build, build / "authoring" / "compiled")
    model, role = row["model"], row["member_role"]
    if role == "head_drawable": return _inside(root, root / model / "head_000_r.ydd")
    if role == "head_diffuse_texture": return _inside(root, root / f"head_diff_000_a_{'bla' if row.get('target_texture_id','').endswith('_bla') else 'whi'}.ytd")
    suffix = {"root_yft":"yft", "root_ymt":"ymt", "full4_ydd":"ydd", "full4_ytd":"ytd"}.get(role)
    if suffix is None: raise ValueError(f"Unsupported member role: {role}")
    return _inside(root, root / f"{model}.{suffix}")

def _variant_name(row: dict) -> str | None:
    if row["entry"].endswith("head_000_r_1.ydd"): return "hash_61496F09"
    if row["member_role"] == "head_diffuse_texture": return str(row["target_texture_id"])
    return None

def _compile_variant(source: Path, source_xml: Path, row: dict, destination: Path, assets: Path, scratch: Path, patcher: Path, game: Path, log: list[dict]) -> None:
    xml = destination.with_suffix(destination.suffix + ".xml")
    tree = _xml(source_xml)
    name = _variant_name(row)
    assert name
    node = tree.getroot().find("./Item/Name") if source.suffix == ".ydd" else tree.getroot().find("./Item/Name")
    if node is None: raise ValueError("Variant source XML has no resource name")
    node.text = name
    if source.suffix == ".ytd":
        file_name = tree.getroot().find("./Item/FileName")
        if file_name is None: raise ValueError("YTD source has no DDS filename")
        # Keep the canonical exported DDS bytes; only the resource/YTD name changes.
    xml.parent.mkdir(parents=True, exist_ok=True); tree.write(str(xml), encoding="UTF-8", xml_declaration=True)
    cmd = [str(patcher), "asset-from-xml", str(xml), str(destination), str(assets), "gen9", str(source), str(game)]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    log.append({"args":cmd[1:],"returncode":run.returncode,"stdout":run.stdout,"stderr":run.stderr})
    if run.returncode: raise RuntimeError("Native variant compiler failed: " + run.stderr)
    checked = destination.with_suffix(destination.suffix + ".verified.xml")
    scratch.mkdir(parents=True,exist_ok=True)
    cmd = [str(patcher), "asset-xml", str(destination), str(checked), str(scratch), "gen9", str(game)]
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    log.append({"args":cmd[1:],"returncode":run.returncode,"stdout":run.stdout,"stderr":run.stderr})
    if run.returncode: raise RuntimeError("Native variant verifier failed: " + run.stderr)
    actual = _xml(checked)
    if actual.getroot().findtext("./Item/Name") != name:
        raise ValueError("Recompiled variant did not retain its exact resource name")
    if source.suffix == ".ytd":
        original_dds = _inside(assets, assets/tree.getroot().findtext("./Item/FileName"))
        checked_dds = _inside(scratch, scratch/actual.getroot().findtext("./Item/FileName"))
        if digest(original_dds) != digest(checked_dds):
            raise ValueError("Recompiled variant changed diffuse DDS bytes")
    if source.suffix == ".ydd":
        old_bones = tree.getroot().xpath(".//Skeleton/Bones")
        new_bones = actual.getroot().xpath(".//Skeleton/Bones")
        old_indices = [" ".join((n.text or "").split()) for n in tree.getroot().xpath(".//IndexBuffer/Data")]
        new_indices = [" ".join((n.text or "").split()) for n in actual.getroot().xpath(".//IndexBuffer/Data")]
        if len(old_bones) != 1 or len(new_bones) != 1 or etree.tostring(old_bones[0]) != etree.tostring(new_bones[0]) or not new_indices or old_indices != new_indices:
            raise ValueError("Recompiled head variant changed skeleton or mesh topology")
        verify_geometry_roundtrip(tree, actual, f"Recompiled {row['model']} YDD variant")

def package(targets_path: Path, build_root: Path, output: Path, patcher: Path, game: Path,
            version: str = "1.0.0") -> Path:
    targets_path, build_root, output, patcher, game = (p.resolve() for p in (targets_path, build_root, output, patcher, game))
    version = _version(version)
    rows = _targets(targets_path); _preflight_builds(rows,build_root)
    if output.exists() or not patcher.is_file() or not (game / "GTA5_Enhanced.exe").is_file(): raise ValueError("Output must be new; SDK compiler and Enhanced game path must exist")
    _validate_output(output, build_root, game)
    output.mkdir(parents=True); logs=[]; report={"schema_version":1,"version":version,"in_game_verified":False,"public_redistribution":False,"packages":[]}
    for character, package_id in PACKAGE_IDS.items():
        selected=[row for row in rows if row["character"] == character]
        if not selected: raise ValueError(f"No exact targets for {character}")
        folder=output / package_id; payload=folder / "payload"; payload.mkdir(parents=True)
        entries=[]
        for index,row in enumerate(selected,1):
            original=Path(row["extracted_original"])
            if not original.is_file() or digest(original) != row["current_original_sha256"]: raise ValueError("Extracted original checksum mismatch")
            split_nested_rpf_entry(f"{row['nested_archive']}!{row['entry']}")
            build=_inside(build_root, build_root / MODEL_BUILD[row["model"]])
            source=_compiled(build,row)
            source_xml = _inside(build, build / "authoring" / "authored" / (str(source.relative_to(build / "authoring" / "compiled")) + ".xml"))
            if not source.is_file() or not source_xml.is_file(): raise FileNotFoundError("Compiled build resource/XML is missing")
            name=f"{index:03d}-{hashlib.sha256(row['mods_relative_target'].encode()).hexdigest()[:12]}{source.suffix}"
            target=payload / name
            if _variant_name(row): _compile_variant(source,source_xml,row,target,build / "authoring" / "source",output/"workchecked",patcher,game,logs)
            else: shutil.copy2(source,target)
            entries.append({"source":f"payload/{name}","archive":row["mods_relative_target"],"entry":f"{row['nested_archive']}!{row['entry']}","sha256":digest(target),"original_sha256":row["current_original_sha256"]})
        manifest=folder / "mod.toml"
        friendly={"SpongeBob":"Franklin - SpongeBob (Private Test)","Patrick":"Lamar - Patrick (Private Test)","Squidward":"Stretch - Squidward (Private Test)","Mr Krabs":"D - Krabs (Private Test)"}[character]
        lines=["schema_version = 4",f'id = "{package_id}"',f'name = "{friendly}"',f'version = "{version}"','type = "rpf"','editions = ["enhanced"]','dependencies = ["openrpf"]','conflicts = []',""]
        for item in entries:
            lines += ["[[rpf_entries]]",*(f'{key} = "{value}"' for key,value in item.items()),""]
        manifest.write_text("\n".join(lines),encoding="utf-8"); ModManifest.load(manifest)
        report["packages"].append({"id":package_id,"manifest":str(manifest),"entries":entries})
    (output/"compiler-log.json").write_text(json.dumps(logs,indent=2),encoding="utf-8")
    (output/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return output/"report.json"

def main() -> None:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--targets",required=True,type=Path);p.add_argument("--build-root",required=True,type=Path);p.add_argument("--output",required=True,type=Path);p.add_argument("--patcher",required=True,type=Path);p.add_argument("--gta-path",required=True,type=Path);p.add_argument("--version",default="1.0.0");a=p.parse_args();print(package(a.targets,a.build_root,a.output,a.patcher,a.gta_path,a.version))
if __name__ == "__main__": main()
