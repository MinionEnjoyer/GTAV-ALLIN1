"""Pure, conservative authoring helpers for a protagonist appearance overlay.

This module deliberately deals only in XML trees.  It neither writes an RPF nor
registers a DLC: callers must validate and package its returned trees separately.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


MAX_XML_BYTES = 2 * 1024 * 1024
TARGET_MODELS = frozenset({"player_one"})
HEAD_DRAWABLE = "head_000_r"
_MISSING_COMPONENT = "255"
_REQUIRED_BONES = frozenset({
    "SKEL_ROOT", "SKEL_Pelvis", "SKEL_Spine0", "SKEL_Spine1",
    "SKEL_Head", "SKEL_L_Hand", "SKEL_R_Hand", "SKEL_L_Foot",
    "SKEL_R_Foot",
})
_REQUIRED_IK_BONES = frozenset({"IK_Root", "IK_L_Foot", "IK_R_Foot", "IK_L_Hand", "IK_R_Hand"})


@dataclass(frozen=True)
class TextureSelection:
    """One resource needed to build the output's streamed texture dictionaries."""

    sampler: str
    source_texture: str | None
    output_texture: str
    disposition: str


@dataclass(frozen=True)
class AppearanceAuthoringReport:
    target_model: str
    drawable_name: str
    bone_count: int
    textures: tuple[TextureSelection, ...]
    dependencies: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AppearanceAuthoringResult:
    """Fresh XML trees plus the exact texture decisions needed by a packager."""

    ydd: etree._ElementTree
    yft: etree._ElementTree
    ymt: etree._ElementTree
    report: AppearanceAuthoringReport


def parse_xml_bytes(data: bytes | str, *, label: str = "XML") -> etree._ElementTree:
    """Parse bounded, local XML without entity expansion or network access."""
    encoded = data.encode("utf-8") if isinstance(data, str) else data
    if not isinstance(encoded, bytes) or not encoded:
        raise ValueError(f"{label} must be non-empty XML bytes")
    if len(encoded) > MAX_XML_BYTES:
        raise ValueError(f"{label} exceeds the {MAX_XML_BYTES} byte limit")
    # ``resolve_entities=False`` preserves entity references rather than
    # expanding them.  Reject DTD-bearing documents too, so no caller can
    # accidentally carry a declaration into a later compiler stage.
    if b"<!doctype" in encoded.lower() or b"<!entity" in encoded.lower():
        raise ValueError(f"{label} is not safe, well-formed XML")
    try:
        root = etree.fromstring(
            encoded,
            parser=etree.XMLParser(
                resolve_entities=False, no_network=True, load_dtd=False,
                huge_tree=False, remove_blank_text=False,
            ),
        )
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ValueError(f"{label} is not safe, well-formed XML") from exc
    tree = etree.ElementTree(root)
    if tree.docinfo.doctype or any(isinstance(node, etree._Entity)
                                   for node in tree.iter()):
        raise ValueError(f"{label} is not safe, well-formed XML")
    return tree


def parse_xml_path(path: str | Path, *, label: str = "XML") -> etree._ElementTree:
    """Read one regular, bounded XML file before using :func:`parse_xml_bytes`."""
    candidate = Path(path)
    if not candidate.is_file():
        raise ValueError(f"{label} must be an existing regular file")
    try:
        with candidate.open("rb") as stream:
            data = stream.read(MAX_XML_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    if not data or len(data) > MAX_XML_BYTES:
        raise ValueError(f"{label} exceeds the {MAX_XML_BYTES} byte limit")
    return parse_xml_bytes(data, label=label)


def joaat(value: str) -> int:
    """GTA's case-insensitive Jenkins one-at-a-time hash."""
    result = 0
    for byte in value.lower().encode("ascii"):
        result = (result + byte) & 0xFFFFFFFF
        result = (result + (result << 10)) & 0xFFFFFFFF
        result ^= result >> 6
    result = (result + (result << 3)) & 0xFFFFFFFF
    result ^= result >> 11
    return (result + (result << 15)) & 0xFFFFFFFF


def author_franklin_appearance(
    ydd: etree._ElementTree, yft: etree._ElementTree,
    ymt: etree._ElementTree, ytd: etree._ElementTree,
    *, target_model: str = "player_one",
) -> AppearanceAuthoringResult:
    """Validate source trees and return non-mutating, `player_one`-named trees.

    The output intentionally exposes only component 0.  It cannot make missing
    clothing assets safe, and it records rather than invents the verified builtin
    ``givemechecker`` dependency.
    """
    target = (target_model or "").strip().lower()
    if target not in TARGET_MODELS:
        raise ValueError("target model is not allowlisted")
    source_ydd = _root(ydd, "DrawableDictionary", "YDD")
    source_yft = _root(yft, "Fragment", "YFT")
    source_ymt = _root(ymt, "CPedVariationInfo", "YMT")
    source_ytd = _root(ytd, "TextureDictionary", "YTD")

    drawables = source_ydd.findall("./Item")
    if len(drawables) != 1:
        raise ValueError("source YDD must contain exactly one whole-body drawable")
    drawable_name = _text(drawables[0].find("./Name"), "source drawable name")
    expected_hash = joaat(HEAD_DRAWABLE)
    if drawable_name.lower() != f"hash_{expected_hash:08x}":
        raise ValueError("source drawable is not the head_000_r hash")

    ydd_bones = _skeleton(drawables[0], "YDD")
    yft_bones = _skeleton(source_yft, "YFT")
    if ydd_bones != yft_bones:
        raise ValueError("source YDD and YFT skeleton topology/tags differ")
    missing_bones = sorted(_REQUIRED_BONES - {bone[0] for bone in ydd_bones})
    if missing_bones:
        raise ValueError("source skeleton lacks required humanoid bones: " +
                         ", ".join(missing_bones))
    _source_head_component(source_ymt)

    textures = {_text(item.find("./Name"), "source YTD texture name")
                for item in source_ytd.findall("./Item")}
    for name in ("head_diff_000_a_whi", "head_normal_000"):
        if name not in textures:
            raise ValueError(f"source YTD lacks required texture: {name}")

    output_ydd = deepcopy(ydd)
    output_ydd.getroot().find("./Item/Name").text = f"hash_{expected_hash:08X}"
    _repair_ydd_textures(output_ydd.getroot(), source_ytd)
    output_yft = deepcopy(yft)
    output_yft.getroot().find("./Name").text = f"pack:/{target}"
    output_ymt = etree.ElementTree(_head_only_ymt(source_ymt))

    selections = (
        TextureSelection("DiffuseSampler", "head_diff_000_a_whi", "head_diff_000_a_whi", "streamed_ytd"),
        TextureSelection("BumpSampler", "head_normal_000", "head_normal_000", "embedded_ydd"),
        TextureSelection("SpecSampler", None, "head_spec_000", "generated_black_embedded_ydd"),
        TextureSelection("VolumeSampler", None, "givemechecker", "builtin_dependency"),
    )
    return AppearanceAuthoringResult(
        output_ydd, output_yft, output_ymt,
        AppearanceAuthoringReport(
            target, HEAD_DRAWABLE, len(ydd_bones), selections,
            ("givemechecker",),
            ("The source skeleton has no exact stock-player compatibility proof; "
             "missing facial bones remain a runtime limitation.",),
        ),
    )


def _root(tree: etree._ElementTree, name: str, label: str) -> etree._Element:
    if not isinstance(tree, etree._ElementTree) or tree.getroot() is None:
        raise ValueError(f"{label} must be an XML element tree")
    root = tree.getroot()
    if root.tag != name:
        raise ValueError(f"{label} root must be {name}")
    return root


def _text(element: etree._Element | None, label: str) -> str:
    value = (element.text or "").strip() if element is not None else ""
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _skeleton(root: etree._Element, label: str) -> tuple[tuple[str, int, int, int], ...]:
    # Component YDDs carry their skeleton directly; a fragment YFT carries it
    # in its Drawable.  Reject ambiguity instead of choosing an arbitrary one.
    skeletons = root.xpath("./Skeleton | ./Drawable/Skeleton")
    if len(skeletons) != 1:
        raise ValueError(f"{label} must contain exactly one skeleton")
    items = skeletons[0].findall("./Bones/Item")
    if not items:
        raise ValueError(f"{label} has no skeleton bones")
    result = []
    for item in items:
        try:
            result.append((_text(item.find("./Name"), f"{label} bone name"),
                           int(item.find("./Index").get("value")),
                           int(item.find("./ParentIndex").get("value")),
                           int(item.find("./Tag").get("value"))))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"{label} has malformed skeleton data") from exc
    if [item[1] for item in result] != list(range(len(result))):
        raise ValueError(f"{label} skeleton indices must be contiguous")
    names = [item[0] for item in result]
    tags = [item[3] for item in result]
    if len(set(names)) != len(names) or len(set(tags)) != len(tags):
        raise ValueError(f"{label} skeleton bone names and tags must be unique")
    roots = [item for item in result if item[2] == -1]
    if len(roots) != 1 or roots[0][0] != "SKEL_ROOT":
        raise ValueError(f"{label} skeleton must have one SKEL_ROOT")
    for index, (_, _, parent, _) in enumerate(result):
        if parent < -1 or parent >= index:
            raise ValueError(f"{label} skeleton parents must be earlier and acyclic")
    by_name = {item[0]: item for item in result}
    missing = sorted((_REQUIRED_BONES | _REQUIRED_IK_BONES) - set(by_name))
    if missing:
        raise ValueError("source skeleton lacks required humanoid bones: " +
                         ", ".join(missing))
    untagged = sorted(name for name in (_REQUIRED_BONES | _REQUIRED_IK_BONES) - {"SKEL_ROOT"}
                      if by_name[name][3] == 0)
    if untagged:
        raise ValueError("source skeleton has untagged required humanoid bones: " +
                         ", ".join(untagged))
    _require_ancestor(by_name, "SKEL_ROOT", "SKEL_Pelvis", label)
    _require_ancestor(by_name, "SKEL_ROOT", "SKEL_Spine0", label)
    _require_ancestor(by_name, "SKEL_Spine0", "SKEL_Spine1", label)
    _require_ancestor(by_name, "SKEL_Spine1", "SKEL_Head", label)
    _require_ancestor(by_name, "SKEL_L_Foot", "IK_L_Foot", label)
    _require_ancestor(by_name, "SKEL_R_Foot", "IK_R_Foot", label)
    _require_ancestor(by_name, "SKEL_L_Hand", "IK_L_Hand", label)
    _require_ancestor(by_name, "SKEL_R_Hand", "IK_R_Hand", label)
    return tuple(result)


def _require_ancestor(bones: dict[str, tuple[str, int, int, int]],
                      ancestor: str, descendant: str, label: str) -> None:
    parent = bones[descendant][2]
    while parent != -1:
        candidate = next(item for item in bones.values() if item[1] == parent)
        if candidate[0] == ancestor:
            return
        parent = candidate[2]
    raise ValueError(f"{label} skeleton lacks {ancestor} -> {descendant} ancestry")


def _source_head_component(root: etree._Element) -> etree._Element:
    available = _text(root.find("./availComp"), "YMT availComp").split()
    if len(available) != 12 or available[0] != "0":
        raise ValueError("YMT must map component 0 to its first component data")
    components = root.findall("./aComponentData3/Item")
    if not components:
        raise ValueError("YMT has no component data")
    head = components[0]
    drawables = head.findall("./aDrawblData3/Item")
    if len(drawables) != 1:
        raise ValueError("YMT head component must have exactly one drawable")
    drawable = drawables[0]
    # propMask 17 is the standard component-0 '_r' drawable suffix.
    if _attribute(drawable.find("./propMask"), "value", "YMT head propMask") != "17":
        raise ValueError("YMT head component does not resolve head_000_r")
    if _attribute(head.find("./numAvailTex"), "value", "YMT head numAvailTex") != "1":
        raise ValueError("YMT head component must have exactly one texture")
    if _attribute(drawable.find("./numAlternatives"), "value", "YMT head numAlternatives") != "0":
        raise ValueError("YMT head component must have no alternatives")
    textures = drawable.findall("./aTexData/Item")
    if len(textures) != 1 or _attribute(textures[0].find("./texId"), "value", "YMT head texId") != "1":
        raise ValueError("YMT head component must map exactly one texId 1 texture")
    if _attribute(drawable.find("./clothData/ownsCloth"), "value", "YMT head ownsCloth") != "false":
        raise ValueError("YMT head component must not own cloth")
    return head


def _attribute(element: etree._Element | None, name: str, label: str) -> str:
    value = element.get(name) if element is not None else None
    if value is None:
        raise ValueError(f"{label} is required")
    return value


def _head_only_ymt(source: etree._Element) -> etree._Element:
    root = etree.Element("CPedVariationInfo")
    for name in ("bHasTexVariations", "bHasDrawblVariations", "bHasLowLODs", "bIsSuperLOD"):
        value = _attribute(source.find(f"./{name}"), "value", f"YMT {name}")
        etree.SubElement(root, name).set("value", value)
    etree.SubElement(root, "availComp").text = " ".join(["0"] + [_MISSING_COMPONENT] * 11)
    component_data = etree.SubElement(root, "aComponentData3", itemType="CPVComponentData")
    component_data.append(deepcopy(_source_head_component(source)))
    etree.SubElement(root, "aSelectionSets", itemType="CPedSelectionSet")
    infos = etree.SubElement(root, "compInfos", itemType="CComponentInfo")
    source_info = next((item for item in source.findall("./compInfos/Item")
                        if item.find("./pedXml_compIdx") is not None and
                        item.find("./pedXml_compIdx").get("value") == "0" and
                        item.find("./pedXml_drawblIdx") is not None and
                        item.find("./pedXml_drawblIdx").get("value") == "0"), None)
    if source_info is None:
        raise ValueError("YMT has no component-0 drawable-0 info")
    infos.append(deepcopy(source_info))
    prop = etree.SubElement(root, "propInfo")
    etree.SubElement(prop, "numAvailProps").set("value", "0")
    etree.SubElement(prop, "aPropMetaData", itemType="CPedPropMetaData")
    etree.SubElement(prop, "aAnchors", itemType="CAnchorProps")
    etree.SubElement(root, "dlcName")
    return root


def _repair_ydd_textures(ydd: etree._Element, source_ytd: etree._Element) -> None:
    """Give the head drawable a closed normal/spec dictionary and diffuse link."""
    drawable = ydd.find("./Item")
    shaders = drawable.findall("./ShaderGroup/Shaders/Item") if drawable is not None else []
    if len(shaders) != 1:
        raise ValueError("YDD must contain exactly one supported head shader")
    shader = shaders[0]
    texture_parameters = [item for item in shader.findall("./Parameters/Item")
                          if item.get("type") == "Texture"]
    sampler_names = [item.get("name") for item in texture_parameters]
    expected_samplers = {"DiffuseSampler", "BumpSampler", "SpecSampler", "VolumeSampler"}
    if None in sampler_names or len(set(sampler_names)) != len(sampler_names):
        raise ValueError("YDD head shader has duplicate or unnamed texture samplers")
    if set(sampler_names) != expected_samplers:
        raise ValueError("YDD head shader has unsupported texture samplers")
    parameters = {item.get("name"): item for item in texture_parameters}
    # The variation system resolves diffuse from its per-drawable YTD. Normal
    # and specular must live in the drawable's own TextureDictionary instead.
    _set_sampler(parameters["DiffuseSampler"], "head_diff_000_a_whi")
    _set_sampler(parameters["BumpSampler"], "head_normal_000")
    _set_sampler(parameters["SpecSampler"], "head_spec_000")
    if _sampler_name(parameters["VolumeSampler"]) != "givemechecker":
        raise ValueError("YDD head shader must retain builtin givemechecker volume sampler")

    dictionary = drawable.find("./ShaderGroup/TextureDictionary")
    if dictionary is None:
        dictionary = etree.Element("TextureDictionary")
        drawable.find("./ShaderGroup").append(dictionary)
    else:
        dictionary.clear()
    normal = next((item for item in source_ytd.findall("./Item")
                   if _text(item.find("./Name"), "source YTD texture name") == "head_normal_000"), None)
    if normal is None:  # defended above; keeps this helper safe if reordered.
        raise ValueError("source YTD lacks required texture: head_normal_000")
    dictionary.append(deepcopy(normal))
    dictionary.append(_black_spec_texture())


def _set_sampler(parameter: etree._Element, texture_name: str) -> None:
    name = parameter.find("./Name")
    if name is None:
        name = etree.SubElement(parameter, "Name")
    name.text = texture_name


def _sampler_name(parameter: etree._Element) -> str:
    return _text(parameter.find("./Name"), "YDD sampler texture name")


def _black_spec_texture() -> etree._Element:
    """Metadata for a deterministic 4×4 opaque-black A8R8G8B8 DDS payload."""
    item = etree.Element("Item")
    etree.SubElement(item, "Name").text = "head_spec_000"
    etree.SubElement(item, "Unk32").set("value", "128")
    etree.SubElement(item, "Usage").text = "SPECULAR"
    etree.SubElement(item, "UsageFlags").text = "X32, X64, X128, X512, UNK24"
    etree.SubElement(item, "ExtraFlags").set("value", "0")
    etree.SubElement(item, "Width").set("value", "4")
    etree.SubElement(item, "Height").set("value", "4")
    etree.SubElement(item, "MipLevels").set("value", "1")
    etree.SubElement(item, "Format").text = "D3DFMT_A8R8G8B8"
    etree.SubElement(item, "FileName").text = "head_spec_000.dds"
    return item
