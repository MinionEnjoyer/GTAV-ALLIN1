"""Pure XML authoring for controlled story-character appearance overlays.

The caller owns DDS generation and DLC/RPF packaging.  This module deliberately
does neither: it validates a complete source set and returns fresh XML trees plus
an explicit record of every texture decision needed by a packager.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from lxml import etree

from .protagonist_appearance import (
    HEAD_DRAWABLE,
    TextureSelection,
    _black_spec_texture,
    _head_only_ymt,
    _root,
    _skeleton,
    _source_head_component,
    _text,
    joaat,
)


TARGET_MODELS = frozenset({
    "player_one",
    "ig_lamardavis", "cs_lamardavis",
    "ig_stretch", "cs_stretch",
    "ig_ballasog", "csb_ballasog",
})
_REQUIRED_SAMPLERS = frozenset({
    "DiffuseSampler", "VolumeSampler", "BumpSampler", "SpecSampler",
})
_OPTIONAL_SAMPLERS = frozenset({"TextureSamplerDiffPal"})


@dataclass(frozen=True)
class CharacterAppearanceReport:
    target_model: str
    drawable_name: str
    bone_count: int
    textures: tuple[TextureSelection, ...]
    dependencies: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CharacterAppearanceResult:
    ydd: etree._ElementTree
    yft: etree._ElementTree
    ymt: etree._ElementTree
    report: CharacterAppearanceReport


def author_character_appearance(
    ydd: etree._ElementTree,
    yft: etree._ElementTree,
    ymt: etree._ElementTree,
    ytd: etree._ElementTree,
    *,
    target_model: str,
    diffuse_texture: str,
    normal_texture: str | None,
) -> CharacterAppearanceResult:
    """Author a one-drawable, component-0 story-character overlay.

    ``diffuse_texture`` and ``normal_texture`` are source YTD names, not output
    names.  A ``None`` normal explicitly requests a generated flat normal.  The
    original input trees are never modified.
    """
    target = (target_model or "").strip().lower()
    if target not in TARGET_MODELS:
        raise ValueError("target model is not allowlisted")
    diffuse = _required_name(diffuse_texture, "diffuse texture")
    normal = _optional_name(normal_texture, "normal texture")
    source_ydd = _root(ydd, "DrawableDictionary", "YDD")
    source_yft = _root(yft, "Fragment", "YFT")
    source_ymt = _root(ymt, "CPedVariationInfo", "YMT")
    source_ytd = _root(ytd, "TextureDictionary", "YTD")

    drawables = source_ydd.findall("./Item")
    if len(drawables) != 1:
        raise ValueError("source YDD must contain exactly one whole-body drawable")
    source_drawable_name = _text(drawables[0].find("./Name"), "source drawable name")
    allowed_drawable_names = {HEAD_DRAWABLE, f"hash_{joaat(HEAD_DRAWABLE):08x}"}
    if source_drawable_name.lower() not in allowed_drawable_names:
        raise ValueError("source drawable must be head_000_r or its hash_976FBF04 name")
    ydd_bones = _skeleton(drawables[0], "YDD")
    yft_bones = _skeleton(source_yft, "YFT")
    if ydd_bones != yft_bones:
        raise ValueError("source YDD and YFT skeleton topology/tags differ")
    _source_head_component(source_ymt)

    source_textures: dict[str, etree._Element] = {}
    for item in source_ytd.findall("./Item"):
        name = _text(item.find("./Name"), "source YTD texture name")
        if name in source_textures:
            raise ValueError(f"source YTD has duplicate texture name: {name}")
        source_textures[name] = item
    if diffuse not in source_textures:
        raise ValueError(f"source YTD lacks required diffuse texture: {diffuse}")
    if normal is not None and normal not in source_textures:
        raise ValueError(f"source YTD lacks required normal texture: {normal}")

    output_ydd = deepcopy(ydd)
    output_drawable = output_ydd.getroot().find("./Item")
    assert output_drawable is not None  # established above
    _text(output_drawable.find("./Name"), "source drawable name")
    output_drawable.find("./Name").text = f"hash_{joaat(HEAD_DRAWABLE):08X}"
    _repair_shader_and_dictionary(output_drawable, source_textures, normal)

    output_yft = deepcopy(yft)
    _text(output_yft.getroot().find("./Name"), "source fragment name")
    output_yft.getroot().find("./Name").text = f"pack:/{target}"
    output_ymt = etree.ElementTree(_head_only_ymt(source_ymt))

    normal_selection = (
        TextureSelection("BumpSampler", normal, "head_normal_000", "embedded_ydd")
        if normal is not None
        else TextureSelection("BumpSampler", None, "head_normal_000", "generated_flat_embedded_ydd")
    )
    selections = (
        TextureSelection("DiffuseSampler", diffuse, "head_diff_000_a_whi", "streamed_ytd"),
        normal_selection,
        TextureSelection("SpecSampler", None, "head_spec_000", "generated_black_embedded_ydd"),
        TextureSelection("VolumeSampler", None, "givemechecker", "builtin_dependency"),
    )
    return CharacterAppearanceResult(
        output_ydd, output_yft, output_ymt,
        CharacterAppearanceReport(
            target, HEAD_DRAWABLE, len(ydd_bones), selections,
            ("givemechecker",),
            ("This is an XML-only conversion; package loading and engine behavior "
             "must be verified separately.",),
        ),
    )


def _required_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _optional_name(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _required_name(value, label)


def _repair_shader_and_dictionary(
    drawable: etree._Element,
    source_textures: dict[str, etree._Element],
    normal_name: str | None,
) -> None:
    shaders = drawable.findall("./ShaderGroup/Shaders/Item")
    if len(shaders) != 1:
        raise ValueError("YDD must contain exactly one supported whole-body shader")
    parameters = [item for item in shaders[0].findall("./Parameters/Item")
                  if item.get("type") == "Texture"]
    names = [item.get("name") for item in parameters]
    if None in names or len(set(names)) != len(names):
        raise ValueError("YDD shader has duplicate or unnamed texture samplers")
    if not _REQUIRED_SAMPLERS.issubset(names) or not set(names).issubset(
            _REQUIRED_SAMPLERS | _OPTIONAL_SAMPLERS):
        raise ValueError("YDD shader has unsupported texture samplers")
    by_name = {item.get("name"): item for item in parameters}
    palette = by_name.get("TextureSamplerDiffPal")
    if palette is not None and palette.find("./Name") is not None and (palette.findtext("./Name") or "").strip():
        raise ValueError("YDD shader has an unverified palette texture binding")
    _set_sampler(by_name["DiffuseSampler"], "head_diff_000_a_whi")
    _set_sampler(by_name["BumpSampler"], "head_normal_000")
    _set_sampler(by_name["SpecSampler"], "head_spec_000")
    _set_sampler(by_name["VolumeSampler"], "givemechecker")

    group = drawable.find("./ShaderGroup")
    assert group is not None
    dictionary = group.find("./TextureDictionary")
    if dictionary is None:
        dictionary = etree.SubElement(group, "TextureDictionary")
    else:
        dictionary.clear()
    dictionary.append(_normal_texture(source_textures.get(normal_name) if normal_name else None))
    dictionary.append(_black_spec_texture())


def _set_sampler(parameter: etree._Element, texture_name: str) -> None:
    node = parameter.find("./Name")
    if node is None:
        node = etree.SubElement(parameter, "Name")
    node.text = texture_name


def _normal_texture(source: etree._Element | None) -> etree._Element:
    if source is None:
        item = etree.Element("Item")
        etree.SubElement(item, "Name").text = "head_normal_000"
        etree.SubElement(item, "Unk32").set("value", "128")
        etree.SubElement(item, "Usage").text = "NORMAL"
        etree.SubElement(item, "UsageFlags").text = "X32, X64, X128, X512, UNK24"
        etree.SubElement(item, "ExtraFlags").set("value", "0")
        etree.SubElement(item, "Width").set("value", "4")
        etree.SubElement(item, "Height").set("value", "4")
        etree.SubElement(item, "MipLevels").set("value", "1")
        etree.SubElement(item, "Format").text = "D3DFMT_A8R8G8B8"
        etree.SubElement(item, "FileName").text = "head_normal_000.dds"
        return item
    item = deepcopy(source)
    item.find("./Name").text = "head_normal_000"
    file_name = item.find("./FileName")
    if file_name is None:
        file_name = etree.SubElement(item, "FileName")
    file_name.text = "head_normal_000.dds"
    usage = item.find("./Usage")
    if usage is None:
        usage = etree.SubElement(item, "Usage")
    usage.text = "NORMAL"
    return item
