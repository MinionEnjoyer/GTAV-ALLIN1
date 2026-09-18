"""Build a private, reversible Enhanced Franklin appearance DLC.

This intentionally narrow authoring tool accepts an existing whole-body head
ped, not an arbitrary add-on. It never edits the game or installs anything.
Use the launcher's normal reviewed package install/disable/uninstall workflow.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from allin1.protagonist_appearance import author_franklin_appearance, parse_xml_path

PACK = "franklin_spongebob"
STREAM_PATH = "x64/models/cdimages/streamedpeds_players.rpf"


def black_spec_dds() -> bytes:
    """Uncompressed 4x4 opaque black BGRA, matching A8R8G8B8 XML metadata."""
    header = [124, 0x100F, 4, 4, 16, 0, 1] + [0] * 11
    header += [32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000]
    header += [0x1000, 0, 0, 0, 0]
    return b"DDS " + struct.pack("<31I", *header) + bytes((0, 0, 0, 255)) * 16


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_xml(tree: etree._ElementTree, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def metadata() -> tuple[str, str]:
    uri = f"dlc_{PACK}:/%PLATFORM%/models/cdimages/streamedpeds_players.rpf"
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<CDataFileMgr__ContentsOfDataFileXml>
  <disabledFiles /><includedXmlFiles /><includedDataFiles />
  <dataFiles><Item>
    <filename>{uri}</filename><fileType>PEDSTREAM_FILE</fileType>
    <overlay value="true" /><disabled value="true" /><persistent value="true" />
  </Item></dataFiles>
  <contentChangeSets><Item>
    <changeSetName>CONTENT_UNLOCKING_META</changeSetName><mapChangeSetData />
    <filesToInvalidate /><filesToDisable />
    <filesToEnable><Item>{uri}</Item></filesToEnable><filesToEnableXml />
  </Item></contentChangeSets><patchFiles />
</CDataFileMgr__ContentsOfDataFileXml>
'''
    setup = f'''<?xml version="1.0" encoding="UTF-8"?>
<SSetupData>
  <deviceName>dlc_{PACK}</deviceName><datFile>content.xml</datFile>
  <timeStamp>12/09/2026 12:00:00</timeStamp><nameHash>{PACK}</nameHash>
  <contentChangeSetGroups><Item><NameHash>GROUP_STARTUP</NameHash>
    <ContentChangeSets><Item>CONTENT_UNLOCKING_META</Item></ContentChangeSets>
  </Item></contentChangeSetGroups><contentChangeSets />
  <type>EXTRACONTENT_COMPAT_PACK</type><order value="350" /><flags value="0" />
</SSetupData>
'''
    return content, setup


def prepare_paths(source: Path, output: Path, patcher: Path, game: Path) -> dict[str, Path]:
    source, output, patcher, game = (p.resolve() for p in (source, output, patcher, game))
    if not source.is_dir() or not patcher.is_file():
        raise ValueError("Source directory and native SDK compiler must exist")
    if not (game / "GTA5_Enhanced.exe").is_file():
        raise ValueError("An Enhanced installation is required for this test package")
    if output.exists() or output.is_relative_to(game) or source.is_relative_to(output):
        raise ValueError("Output must be a new directory outside the game and source tree")
    if output.is_relative_to(source):
        raise ValueError("Output cannot be inside the source tree")
    assets = {}
    for suffix in ("ydd", "yft", "ymt", "ytd"):
        matches = [p for p in source.iterdir() if p.is_file() and p.suffix.lower() == f".{suffix}"]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one source .{suffix} file")
        assets[suffix] = matches[0]
    if len({p.stem.casefold() for p in assets.values()}) != 1:
        raise ValueError("Source resource basenames must match")
    return assets


def build(source: Path, output: Path, patcher: Path, game: Path) -> Path:
    source, output, patcher, game = (p.resolve() for p in (source, output, patcher, game))
    assets = prepare_paths(source, output, patcher, game)
    output.mkdir(parents=True)
    work = output / "authoring"
    exported, authored, compiled, checked = (work / n for n in ("source", "authored", "compiled", "verified"))
    for folder in (exported, authored, compiled, checked):
        folder.mkdir(parents=True)
    calls = []

    def run(*args: str | Path) -> None:
        command = [str(patcher), *(str(a) for a in args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        calls.append({"args": command[1:], "returncode": result.returncode,
                      "stdout": result.stdout, "stderr": result.stderr})
        (work / "compiler-log.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Native compiler failed: {args[0]}\n{result.stdout}\n{result.stderr}")

    for suffix, asset in assets.items():
        run("asset-xml", asset, exported / f"source.{suffix}.xml", exported, "legacy", game)
    trees = {suffix: parse_xml_path(exported / f"source.{suffix}.xml") for suffix in assets}
    authored_result = author_franklin_appearance(trees["ydd"], trees["yft"], trees["ymt"], trees["ytd"])
    (exported / "head_spec_000.dds").write_bytes(black_spec_dds())
    diffuse = etree.Element("TextureDictionary")
    diffuse.append(deepcopy(next(item for item in trees["ytd"].getroot().findall("Item")
                                if item.findtext("Name") == "head_diff_000_a_whi")))
    outputs = {
        "player_one/head_000_r.ydd": (authored_result.ydd, assets["ydd"]),
        "player_one.yft": (authored_result.yft, assets["yft"]),
        "player_one.ymt": (authored_result.ymt, assets["ymt"]),
        "player_one/head_diff_000_a_whi.ytd": (etree.ElementTree(diffuse), assets["ytd"]),
    }
    roundtrips = {}
    for relative, (tree, original) in outputs.items():
        xml = authored / f"{relative}.xml"
        write_xml(tree, xml)
        target = compiled / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        run("asset-from-xml", xml, target, exported, "gen9", original, game)
        check_xml = checked / f"{relative}.xml"
        check_xml.parent.mkdir(parents=True, exist_ok=True)
        run("asset-xml", target, check_xml, checked, "gen9", game)
        roundtrips[relative] = parse_xml_path(check_xml)
    verify_roundtrips(authored_result, trees, roundtrips, checked)

    loose = work / "dlc"
    loose.mkdir()
    content, setup = metadata()
    (loose / "content.xml").write_text(content, encoding="utf-8")
    (loose / "setup2.xml").write_text(setup, encoding="utf-8")
    package = output / "package"
    payload = package / "payload" / PACK / "dlc.rpf"
    payload.parent.mkdir(parents=True)
    run("build-dlc", loose, payload, "--embed-rpf", compiled, STREAM_PATH, "--gta-path", game)
    run("index-json", game, payload, work / "package-index.json")
    for relative in outputs:
        extracted = work / "packed-check" / relative
        extracted.parent.mkdir(parents=True, exist_ok=True)
        run("extract-virtual-entry", game, payload, STREAM_PATH, relative, extracted)
        # Resource extraction may recompress bytes. Re-export and compare XML
        # rather than relying on identical deflate streams.
        xml = extracted.with_suffix(extracted.suffix + ".xml")
        run("asset-xml", extracted, xml, work / "packed-check", "gen9", game)
        if semantic_xml(parse_xml_path(xml).getroot()) != semantic_xml(roundtrips[relative].getroot()):
            raise ValueError(f"Packed resource changed during RPF round-trip: {relative}")
    manifest = package / "mod.toml"
    manifest.write_text(f'''schema_version = 1
id = "private.franklin-spongebob"
name = "Franklin - SpongeBob (Private Test)"
version = "0.1.0"
type = "mixed"
editions = ["enhanced"]
dependencies = ["openrpf"]
conflicts = []
dlc_packs = ["{PACK}"]

[[files]]
source = "payload/{PACK}/dlc.rpf"
destination = "mods/update/x64/dlcpacks/{PACK}/dlc.rpf"
sha256 = "{sha(payload)}"
''', encoding="utf-8")
    report = {
        "authoring": asdict(authored_result.report), "edition": "enhanced",
        "source_sha256": {p.name: sha(p) for p in assets.values()},
        "compiler_sha256": sha(patcher), "payload_sha256": sha(payload),
        "compiled_sha256": {p: sha(compiled / p) for p in outputs},
        "checks": ["ordered source skeleton agreement", "head-only component metadata",
                   "normal/specular embedded; diffuse streamed", "native Gen9 compile and XML round-trip",
                   "packed RPF resource re-extraction and semantic XML equality"],
        "in_game_verified": False,
        "limitations": ["Private testing only; no redistribution of source assets.",
                        "Stock facial animation and clothing are not provided by this model.",
                        "Mission, cutscene and load-order behavior requires an in-game test."],
        "manifest": str(manifest),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return manifest


def semantic_xml(node):
    return (node.tag, tuple(sorted(node.attrib.items())), " ".join((node.text or "").split()),
            tuple(semantic_xml(child) for child in node if isinstance(child.tag, str)))


def verify_roundtrips(authored_result, source, outputs, checked: Path) -> None:
    ydd = outputs["player_one/head_000_r.ydd"].getroot()
    yft = outputs["player_one.yft"].getroot()
    ymt = outputs["player_one.ymt"].getroot()
    ytd = outputs["player_one/head_diff_000_a_whi.ytd"].getroot()
    if yft.findtext("Name") != "pack:/player_one":
        raise ValueError("Compiled fragment lost the protagonist identity")
    for original, target in ((authored_result.ydd.getroot(), ydd), (authored_result.yft.getroot(), yft)):
        a, b = original.find(".//Skeleton/Bones"), target.find(".//Skeleton/Bones")
        fields = lambda bones: [(n.findtext("Name"), n.find("Index").get("value"),
                                  n.find("ParentIndex").get("value"), n.find("Tag").get("value")) for n in bones]
        if fields(a) != fields(b):
            raise ValueError("Compiled skeleton topology changed")
    if ydd.findtext("./Item/Name", "").lower() not in ("hash_976fbf04", "head_000_r"):
        raise ValueError("Compiled drawable hash is incorrect")
    if " ".join(ymt.findtext("availComp", "").split()) != "0 " + " ".join(["255"] * 11):
        raise ValueError("Compiled YMT exposes nonexistent components")
    if len(ymt.findall("./aComponentData3/Item")) != 1 or len(ymt.findall("./compInfos/Item")) != 1:
        raise ValueError("Compiled YMT component cardinality is incorrect")
    params = ydd.findall("./Item/ShaderGroup/Shaders/Item/Parameters/Item")
    actual = {p.get("name"): p.findtext("Name") for p in params if p.get("type") == "Texture"}
    # EnsureGen9 supplies the engine-bound depth buffer slot from its shader
    # conversion table. It is not an asset texture dependency (MetaNames:
    # depthbuffertex = 2391072543); accept only an empty slot, never a texture.
    for depth_name in ("2391072543", "depthbuffertex"):
        if depth_name in actual and actual[depth_name] is None:
            del actual[depth_name]
    expected = {p.sampler: p.output_texture for p in authored_result.report.textures}
    if actual != expected:
        raise ValueError(f"Compiled texture bindings changed: {actual}")
    if {i.findtext("Name") for i in ydd.findall("./Item/ShaderGroup/TextureDictionary/Item")} != {"head_normal_000", "head_spec_000"}:
        raise ValueError("Compiled embedded texture dictionary is incomplete")
    if [i.findtext("Name") for i in ytd.findall("Item")] != ["head_diff_000_a_whi"]:
        raise ValueError("Streamed diffuse texture is missing")
    for name in ("head_normal_000.dds", "head_spec_000.dds", "head_diff_000_a_whi.dds"):
        if not (checked / name).is_file() or (checked / name).stat().st_size <= 128:
            raise ValueError(f"Compiled texture payload is missing: {name}")
    # Conversion may alter vertex-buffer layouts, never the mesh topology.
    def indices(root):
        return [" ".join((n.text or "").split()) for n in root.findall(".//IndexBuffer/Data")]
    if not indices(ydd) or indices(source["ydd"].getroot()) != indices(ydd):
        raise ValueError("Compiled mesh index topology changed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--patcher", required=True, type=Path)
    parser.add_argument("--gta-path", required=True, type=Path)
    args = parser.parse_args()
    print(build(args.source_dir, args.output, args.patcher, args.gta_path))


if __name__ == "__main__":
    main()
