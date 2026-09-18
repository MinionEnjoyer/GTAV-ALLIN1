"""Build private story-character appearance resources without changing GTA V.

The output is an authoring/compiled-resource folder and a machine-readable
audit report.  It intentionally does not create a DLC, RPF, manifest, or make
any write below ``--gta-path``.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from allin1.character_appearance import author_character_appearance

MAX_ASSET_XML_BYTES = 64 * 1024 * 1024


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flat_normal_dds() -> bytes:
    """A deterministic 4x4 A8R8G8B8 flat normal in BGRA order."""
    header = [124, 0x100F, 4, 4, 16, 0, 1] + [0] * 11
    header += [32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000]
    header += [0x1000, 0, 0, 0, 0]
    return b"DDS " + struct.pack("<31I", *header) + bytes((255, 128, 128, 255)) * 16


def black_spec_dds() -> bytes:
    """Uncompressed opaque black BGRA specular resource for the YDD."""
    header = [124, 0x100F, 4, 4, 16, 0, 1] + [0] * 11
    header += [32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000]
    header += [0x1000, 0, 0, 0, 0]
    return b"DDS " + struct.pack("<31I", *header) + bytes((0, 0, 0, 255)) * 16


def write_xml(tree: etree._ElementTree, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, pretty_print=True)


def parse_asset_xml(path: Path) -> etree._ElementTree:
    """Safely load a native-export XML asset without the small UI XML limit."""
    payload = path.read_bytes()
    if len(payload) > MAX_ASSET_XML_BYTES:
        raise ValueError(f"Asset XML exceeds the {MAX_ASSET_XML_BYTES} byte limit")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("Asset XML may not declare DTDs or entities")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             remove_blank_text=False, huge_tree=False)
    try:
        return etree.ElementTree(etree.fromstring(payload, parser=parser))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Invalid native asset XML: {path.name}") from exc


def prepare_paths(source: Path, output: Path, patcher: Path, game: Path) -> dict[str, Path]:
    source, output, patcher, game = (path.resolve() for path in (source, output, patcher, game))
    if not source.is_dir() or not patcher.is_file():
        raise ValueError("Source directory and native SDK compiler must exist")
    if not (game / "GTA5_Enhanced.exe").is_file():
        raise ValueError("An Enhanced GTA V installation is required")
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(game):
        raise ValueError("Output must be a new directory outside the source tree and GTA V")
    if source.is_relative_to(output):
        raise ValueError("Output cannot contain the source tree")
    assets: dict[str, Path] = {}
    for suffix in ("ydd", "yft", "ymt", "ytd"):
        matches = [path for path in source.iterdir() if path.is_file() and path.suffix.casefold() == f".{suffix}"]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one source .{suffix} file")
        assets[suffix] = matches[0]
    if len({path.stem.casefold() for path in assets.values()}) != 1:
        raise ValueError("Source resource basenames must match")
    return assets


def _texture(root: etree._Element, name: str) -> etree._Element:
    item = next((node for node in root.findall("./Item") if node.findtext("Name") == name), None)
    if item is None:
        raise ValueError(f"Source YTD lacks required texture: {name}")
    return item


def _texture_filename(item: etree._Element, label: str) -> str:
    filename = item.findtext("FileName")
    if not filename or Path(filename).name != filename:
        raise ValueError(f"{label} requires a safe DDS FileName")
    return filename


def _streamed_ytd(source: etree._ElementTree, diffuse: str, suffix: str) -> etree._ElementTree:
    name = f"head_diff_000_a_{suffix}"
    item = deepcopy(_texture(source.getroot(), diffuse))
    item.find("Name").text = name
    filename = item.find("FileName")
    if filename is None:
        filename = etree.SubElement(item, "FileName")
    filename.text = name + ".dds"
    root = etree.Element("TextureDictionary")
    root.append(item)
    return etree.ElementTree(root)


def _set_diffuse_binding(ydd: etree._ElementTree, texture_name: str) -> None:
    parameter = ydd.getroot().find("./Item/ShaderGroup/Shaders/Item/Parameters/Item[@name='DiffuseSampler']/Name")
    if parameter is None:
        raise ValueError("Authored YDD lacks DiffuseSampler")
    parameter.text = texture_name


def _set_ymt_texture_id(ymt: etree._ElementTree, texture_suffix: str) -> int:
    """Use the stock component-0 mapping: whi=1 and bla=2."""
    texture_id = 2 if texture_suffix == "bla" else 1
    values = ymt.findall("./aComponentData3/Item/aDrawblData3/Item/aTexData/Item/texId")
    if len(values) != 1:
        raise ValueError("Authored head YMT must contain exactly one texture mapping")
    values[0].set("value", str(texture_id))
    return texture_id


def _copy_texture_asset(exported: Path, item: etree._Element, destination: str) -> None:
    source = exported / _texture_filename(item, "source texture")
    if not source.is_file():
        raise FileNotFoundError(f"Native exporter did not emit texture payload: {source.name}")
    target = exported / destination
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)


def _semantic_xml(node: etree._Element):
    return (node.tag, tuple(sorted(node.attrib.items())), " ".join((node.text or "").split()),
            tuple(_semantic_xml(child) for child in node if isinstance(child.tag, str)))


_VERTEX_ELEMENT_WIDTHS = {
    "Position": 3, "Normal": 3, "Tangent": 4, "Binormal": 3,
    "BlendWeights": 4, "BlendIndices": 4,
}
def _numbers(text: str | None, *, label: str) -> tuple[float, ...]:
    """Read a native XML numeric payload, rejecting lossy/non-finite input."""
    tokens = (text or "").split()
    if not tokens:
        raise ValueError(f"{label} has malformed numeric data")
    try:
        values = tuple(float(token) for token in tokens)
    except ValueError as exc:
        raise ValueError(f"{label} has malformed numeric data") from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"{label} has non-finite numeric data")
    return values


def _vertex_layout(buffer: etree._Element, *, label: str) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    layout = buffer.find("./Layout")
    if layout is None or not list(layout):
        raise ValueError(f"{label} has no vertex layout")
    # Layout type changes the packed interpretation even if its child
    # declarations happen to look identical.
    return (("__layout__", tuple(sorted(layout.attrib.items()))),) + tuple(
        (item.tag, tuple(sorted(item.attrib.items())))
        for item in layout if isinstance(item.tag, str)
    )


def _vertex_stride(layout: tuple[tuple[str, tuple[tuple[str, str], ...]], ...], *, label: str) -> int:
    width = 0
    for name, _ in layout:
        if name == "__layout__":
            continue
        if name in _VERTEX_ELEMENT_WIDTHS:
            width += _VERTEX_ELEMENT_WIDTHS[name]
        elif name.startswith("Colour") or name.startswith("Color"):
            width += 4
        elif name.startswith("TexCoord"):
            width += 2
        else:
            raise ValueError(f"{label} has unsupported vertex layout element: {name}")
    return width


def _vertex_values(buffer: etree._Element, *, label: str) -> tuple[float, ...]:
    # CodeWalker emits either Data or Data2 for the same packed vertex stream.
    payloads = [child for child in buffer if child.tag in {"Data", "Data2"}]
    if len(payloads) != 1:
        raise ValueError(f"{label} must have exactly one Data or Data2 vertex payload")
    return _numbers(payloads[0].text, label=label + " vertex data")


def _int_values(element: etree._Element | None, *, label: str) -> tuple[int, ...]:
    tokens = (element.text or "").replace(",", " ").split() if element is not None else []
    if not tokens:
        raise ValueError(f"{label} is missing")
    try:
        values = tuple(int(token, 10) for token in tokens)
    except ValueError as exc:
        raise ValueError(f"{label} has malformed integer data") from exc
    return values


def _close_values(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    # The native converter can make harmless float formatting/normalization
    # changes.  This still detects a component becoming zero or otherwise lost.
    return len(left) == len(right) and all(
        math.isclose(a, b, rel_tol=1e-5, abs_tol=1e-6)
        for a, b in zip(left, right)
    )


def _field_values(element: etree._Element | None, *, label: str) -> tuple[float, ...]:
    if element is None:
        raise ValueError(f"{label} is missing")
    values: list[float] = []
    for value in element.attrib.values():
        values.extend(_numbers(value, label=label))
    if element.text and element.text.strip():
        values.extend(_numbers(element.text, label=label))
    if not values:
        raise ValueError(f"{label} is empty")
    return tuple(values)


def verify_geometry_roundtrip(authored: etree._ElementTree, checked: etree._ElementTree,
                              label: str = "Compiled asset") -> None:
    """Require the native conversion to preserve renderable mesh semantics.

    This deliberately normalizes Data/Data2, which are alternate XML spellings
    for one vertex stream, but otherwise fails closed on lost vertices, bounds,
    bone palettes, render flags, or invalid index references.
    """
    left_geometries = authored.getroot().xpath(".//Geometries/Item")
    right_geometries = checked.getroot().xpath(".//Geometries/Item")
    if not left_geometries or len(left_geometries) != len(right_geometries):
        raise ValueError(f"{label} geometry count changed")
    # Drawable-level flags and bounds determine whether an otherwise valid mesh
    # is selected and culled.  They are separate from the per-geometry bounds.
    left_drawables = authored.getroot().xpath("./Item | ./Drawable")
    right_drawables = checked.getroot().xpath("./Item | ./Drawable")
    if len(left_drawables) != len(right_drawables):
        raise ValueError(f"{label} drawable count changed")
    for number, (left, right) in enumerate(zip(left_drawables, right_drawables)):
        prefix = f"{label} drawable {number}"
        for field in ("FlagsHigh", "FlagsMed", "FlagsLow", "FlagsVlow",
                      "LodDistHigh", "LodDistMed", "LodDistLow", "LodDistVlow",
                      "BoundingBoxMin", "BoundingBoxMax", "BoundingSphereCenter",
                      "BoundingSphereRadius"):
            left_field, right_field = left.find("./" + field), right.find("./" + field)
            if (left_field is None) != (right_field is None):
                raise ValueError(f"{prefix} {field} changed")
            if left_field is not None:
                left_values = _field_values(left_field, label=prefix + " authored " + field)
                right_values = _field_values(right_field, label=prefix + " compiled " + field)
                if not _close_values(left_values, right_values):
                    raise ValueError(f"{prefix} {field} changed")
        for level in ("DrawableModelsHigh", "DrawableModelsMedium",
                      "DrawableModelsLow", "DrawableModelsVeryLow"):
            left_level, right_level = left.find("./" + level), right.find("./" + level)
            if (left_level is None) != (right_level is None):
                raise ValueError(f"{prefix} {level} changed")
            if left_level is None:
                continue
            left_models, right_models = left_level.findall("./Item"), right_level.findall("./Item")
            if len(left_models) != len(right_models):
                raise ValueError(f"{prefix} {level} model count changed")
            for model_number, (left_model, right_model) in enumerate(zip(left_models, right_models)):
                model_prefix = f"{prefix} {level} model {model_number}"
                for field in ("RenderMask", "Flags", "HasSkin", "BoneIndex", "Unknown1"):
                    left_field, right_field = left_model.find("./" + field), right_model.find("./" + field)
                    if (left_field is None) != (right_field is None):
                        raise ValueError(f"{model_prefix} {field} changed")
                    if left_field is not None and _field_values(
                            left_field, label=model_prefix + " authored " + field) != _field_values(
                            right_field, label=model_prefix + " compiled " + field):
                        raise ValueError(f"{model_prefix} {field} changed")
    for number, (left, right) in enumerate(zip(left_geometries, right_geometries)):
        prefix = f"{label} geometry {number}"
        for field in ("ShaderIndex", "BoneIDs"):
            if field == "BoneIDs":
                if _int_values(left.find("./BoneIDs"), label=prefix + " authored bone palette") != _int_values(
                        right.find("./BoneIDs"), label=prefix + " compiled bone palette"):
                    raise ValueError(f"{prefix} bone palette changed")
            elif _field_values(left.find("./" + field), label=prefix + " authored " + field) != _field_values(
                    right.find("./" + field), label=prefix + " compiled " + field):
                raise ValueError(f"{prefix} {field} changed")
        for field in ("BoundingBoxMin", "BoundingBoxMax", "BoundingSphereCenter", "BoundingSphereRadius"):
            left_field, right_field = left.find("./" + field), right.find("./" + field)
            if (left_field is None) != (right_field is None):
                raise ValueError(f"{prefix} {field} changed")
            if left_field is not None and not _close_values(
                    _field_values(left_field, label=prefix + " authored " + field),
                    _field_values(right_field, label=prefix + " compiled " + field)):
                raise ValueError(f"{prefix} {field} changed")
        left_buffer, right_buffer = left.find("./VertexBuffer"), right.find("./VertexBuffer")
        if left_buffer is None or right_buffer is None:
            raise ValueError(f"{prefix} lost its vertex buffer")
        left_layout, right_layout = _vertex_layout(left_buffer, label=prefix + " authored"), _vertex_layout(right_buffer, label=prefix + " compiled")
        if left_layout != right_layout:
            raise ValueError(f"{prefix} vertex layout changed")
        stride = _vertex_stride(left_layout, label=prefix)
        left_values, right_values = _vertex_values(left_buffer, label=prefix + " authored"), _vertex_values(right_buffer, label=prefix + " compiled")
        if len(left_values) % stride or len(right_values) % stride:
            raise ValueError(f"{prefix} vertex data does not match its layout")
        if len(left_values) != len(right_values):
            raise ValueError(f"{prefix} vertex count changed")
        if len(set(left_values)) > 1 and len(set(right_values)) == 1:
            raise ValueError(f"{prefix} vertex values collapsed")
        if not _close_values(left_values, right_values):
            raise ValueError(f"{prefix} vertex values changed")
        for field in ("Flags",):
            left_field, right_field = left_buffer.find("./" + field), right_buffer.find("./" + field)
            if _field_values(left_field, label=prefix + " authored " + field) != _field_values(
                    right_field, label=prefix + " compiled " + field):
                raise ValueError(f"{prefix} vertex {field} changed")
        left_indices = _int_values(left.find("./IndexBuffer/Data"), label=prefix + " authored indices")
        right_indices = _int_values(right.find("./IndexBuffer/Data"), label=prefix + " compiled indices")
        vertex_count = len(left_values) // stride
        if any(index < 0 or index >= vertex_count for index in (*left_indices, *right_indices)):
            raise ValueError(f"{prefix} has an out-of-range index")
        if left_indices != right_indices:
            raise ValueError(f"{prefix} index data changed")


def verify_compiled(
    authored: dict[str, etree._ElementTree], checked: dict[str, etree._ElementTree],
    *, target_model: str, diffuse_name: str,
) -> None:
    if checked["yft"].getroot().findtext("Name") != f"pack:/{target_model}":
        raise ValueError("Compiled fragment lost the requested target identity")
    if checked["ydd"].getroot().findtext("./Item/ShaderGroup/Shaders/Item/Parameters/Item[@name='DiffuseSampler']/Name") != diffuse_name:
        raise ValueError("Compiled drawable diffuse binding changed")
    ytd_items = checked["ytd"].getroot().findall("./Item")
    if [item.findtext("Name") for item in ytd_items] != [diffuse_name]:
        raise ValueError("Compiled streamed YTD does not contain exactly the canonical diffuse")
    def bones(tree: etree._ElementTree):
        roots = tree.getroot().xpath(".//Skeleton/Bones")
        root = roots[0] if len(roots) == 1 else None
        if root is None:
            raise ValueError("Compiled resource lost its skeleton")
        return [(node.findtext("Name"), node.find("Index").get("value"),
                 node.find("ParentIndex").get("value"), node.find("Tag").get("value"))
                for node in root.findall("./Item")]
    if bones(authored["ydd"]) != bones(checked["ydd"]):
        raise ValueError("Compiled drawable skeleton topology changed")
    if bones(authored["yft"]) != bones(checked["yft"]):
        raise ValueError("Compiled fragment skeleton topology changed")
    verify_geometry_roundtrip(authored["ydd"], checked["ydd"], "Compiled drawable")
    verify_geometry_roundtrip(authored["yft"], checked["yft"], "Compiled fragment")
    bindings = {item.get("name"): item.findtext("Name") for item in checked["ydd"].xpath(".//Parameters/Item[@type='Texture']")}
    for depth_name in ("depthbuffertex", "2391072543"):
        if bindings.get(depth_name) is None:
            bindings.pop(depth_name, None)
    if bindings != {"DiffuseSampler": diffuse_name, "BumpSampler": "head_normal_000",
                    "SpecSampler": "head_spec_000", "VolumeSampler": "givemechecker"}:
        raise ValueError("Compiled drawable texture bindings changed")
    embedded = {item.findtext("Name") for item in checked["ydd"].xpath("./Item/ShaderGroup/TextureDictionary/Item")}
    if embedded != {"head_normal_000", "head_spec_000"}:
        raise ValueError("Compiled drawable embedded texture dictionary changed")
    if len(checked["ymt"].xpath("./aComponentData3/Item")) != 1 or len(checked["ymt"].xpath("./compInfos/Item")) != 1:
        raise ValueError("Compiled head YMT component cardinality changed")
    expected_tex_id = authored["ymt"].xpath("string(./aComponentData3/Item/aDrawblData3/Item/aTexData/Item/texId/@value)")
    actual_tex_id = checked["ymt"].xpath("string(./aComponentData3/Item/aDrawblData3/Item/aTexData/Item/texId/@value)")
    if actual_tex_id != expected_tex_id:
        raise ValueError("Compiled head YMT texture mapping changed")


def build(source: Path, output: Path, patcher: Path, game: Path, *, target_model: str,
          diffuse_texture: str, normal_texture: str | None, texture_suffix: str,
          nonstreamed: bool = False) -> Path:
    """Author and compile the four controlled resources, returning report.json."""
    if texture_suffix not in {"whi", "bla"}:
        raise ValueError("texture suffix must be whi or bla")
    assets = prepare_paths(source, output, patcher, game)
    output = output.resolve()
    output.mkdir(parents=True)
    work = output / "authoring"
    exported, authored_dir, compiled_dir, checked_dir = (work / name for name in ("source", "authored", "compiled", "verified"))
    for directory in (exported, authored_dir, compiled_dir, checked_dir):
        directory.mkdir(parents=True)
    calls: list[dict[str, object]] = []

    def run(*args: str | Path) -> None:
        command = [str(patcher.resolve()), *(str(arg) for arg in args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        calls.append({"args": command[1:], "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        (work / "compiler-log.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Native compiler failed: {args[0]}\n{result.stdout}\n{result.stderr}")

    for suffix, asset in assets.items():
        run("asset-xml", asset, exported / f"source.{suffix}.xml", exported, "legacy", game.resolve())
    source_trees = {suffix: parse_asset_xml(exported / f"source.{suffix}.xml") for suffix in assets}
    result = author_character_appearance(source_trees["ydd"], source_trees["yft"], source_trees["ymt"], source_trees["ytd"],
                                         target_model=target_model, diffuse_texture=diffuse_texture, normal_texture=normal_texture)
    diffuse_name = f"head_diff_000_a_{texture_suffix}"
    _set_diffuse_binding(result.ydd, diffuse_name)
    texture_id = _set_ymt_texture_id(result.ymt, texture_suffix)
    diffuse_item = _texture(source_trees["ytd"].getroot(), diffuse_texture)
    _copy_texture_asset(exported, diffuse_item, diffuse_name + ".dds")
    if normal_texture is None:
        (exported / "head_normal_000.dds").write_bytes(flat_normal_dds())
    else:
        _copy_texture_asset(exported, _texture(source_trees["ytd"].getroot(), normal_texture), "head_normal_000.dds")
    (exported / "head_spec_000.dds").write_bytes(black_spec_dds())
    # This keeps all four generated resources self-contained.  ``nonstreamed``
    # is recorded for a packager; it does not write any game/DLC archive.
    authored = {"ydd": result.ydd, "yft": result.yft, "ymt": result.ymt,
                "ytd": _streamed_ytd(source_trees["ytd"], diffuse_texture, texture_suffix)}
    names = (
        {kind: f"{target_model}.{kind}" for kind in ("ydd", "yft", "ymt", "ytd")}
        if nonstreamed else
        {"ydd": f"{target_model}/head_000_r.ydd", "yft": f"{target_model}.yft",
         "ymt": f"{target_model}.ymt", "ytd": f"{diffuse_name}.ytd"}
    )
    checked: dict[str, etree._ElementTree] = {}
    for suffix, tree in authored.items():
        xml = authored_dir / (names[suffix] + ".xml")
        write_xml(tree, xml)
        binary = compiled_dir / names[suffix]
        binary.parent.mkdir(parents=True, exist_ok=True)
        run("asset-from-xml", xml, binary, exported, "gen9", assets[suffix], game.resolve())
        roundtrip = checked_dir / (names[suffix] + ".xml")
        roundtrip.parent.mkdir(parents=True, exist_ok=True)
        run("asset-xml", binary, roundtrip, checked_dir, "gen9", game.resolve())
        checked[suffix] = parse_asset_xml(roundtrip)
    verify_compiled(authored, checked, target_model=target_model, diffuse_name=diffuse_name)
    for texture in ("head_normal_000.dds", "head_spec_000.dds", diffuse_name + ".dds"):
        path = checked_dir / texture
        if not path.is_file() or path.stat().st_size <= 128:
            raise ValueError(f"Compiled texture payload is missing: {texture}")
    report = {
        "schema_version": 1, "target_model": target_model, "texture_suffix": texture_suffix,
        "nonstreamed": nonstreamed, "ymt_texture_id": texture_id,
        "source_sha256": {kind: sha(path) for kind, path in assets.items()},
        "compiler_sha256": sha(patcher.resolve()), "compiled_sha256": {names[kind]: sha(compiled_dir / names[kind]) for kind in names},
        "authoring": asdict(result.report), "outputs": names,
        "canonical_textures": {
            "diffuse": diffuse_name, "normal": "head_normal_000", "specular": "head_spec_000",
        },
        "checks": ["source containment", "source resource cardinality", "native Gen9 compile", "Gen9 XML round trip", "no GTA V writes"],
        "limitations": ["No DLC/RPF or manifest is produced.", "Stock texture-index mapping must be reviewed before package installation."],
    }
    path = output / "report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--patcher", required=True, type=Path)
    parser.add_argument("--gta-path", required=True, type=Path)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--diffuse-texture", required=True)
    parser.add_argument("--normal-texture")
    parser.add_argument("--texture-suffix", required=True, choices=("whi", "bla"))
    parser.add_argument("--nonstreamed", action="store_true")
    args = parser.parse_args()
    print(build(args.source_dir, args.output, args.patcher, args.gta_path,
                target_model=args.target_model, diffuse_texture=args.diffuse_texture,
                normal_texture=args.normal_texture, texture_suffix=args.texture_suffix,
                nonstreamed=args.nonstreamed))


if __name__ == "__main__":
    main()
