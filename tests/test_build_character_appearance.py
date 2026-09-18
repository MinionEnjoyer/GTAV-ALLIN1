"""Safety and verifier coverage for the private resource-only builder."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys

import pytest
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_character_appearance", ROOT / "tools" / "build_character_appearance.py",
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def _source(path: Path, *, stems=("character",) * 4) -> Path:
    path.mkdir()
    for suffix, stem in zip(("ydd", "yft", "ymt", "ytd"), stems):
        (path / f"{stem}.{suffix}").write_bytes(b"asset")
    return path


def _tool_and_game(path: Path) -> tuple[Path, Path]:
    patcher = path / "RpfPatcher.exe"
    patcher.write_bytes(b"compiler")
    game = path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    return patcher, game


def test_prepare_paths_rejects_game_source_and_existing_output(tmp_path: Path):
    source = _source(tmp_path / "source")
    patcher, game = _tool_and_game(tmp_path)
    for output in (game / "out", source / "out"):
        with pytest.raises(ValueError, match="Output"):
            builder.prepare_paths(source, output, patcher, game)
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="Output"):
        builder.prepare_paths(source, existing, patcher, game)


def test_prepare_paths_requires_one_matching_resource_set(tmp_path: Path):
    source = _source(tmp_path / "source", stems=("character", "character", "character", "other"))
    patcher, game = _tool_and_game(tmp_path)
    with pytest.raises(ValueError, match="basenames"):
        builder.prepare_paths(source, tmp_path / "output", patcher, game)
    (source / "other.ytd").unlink()
    with pytest.raises(ValueError, match="exactly one source .ytd"):
        builder.prepare_paths(source, tmp_path / "output", patcher, game)


def test_flat_normal_is_opaque_bgra_255_128_128_255():
    payload = builder.flat_normal_dds()
    assert len(payload) == 128 + 4 * 4 * 4
    assert payload[:4] == b"DDS "
    header = struct.unpack("<31I", payload[4:128])
    assert header[0:7] == (124, 0x100F, 4, 4, 16, 0, 1)
    assert header[18:26] == (32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00,
                              0x000000FF, 0xFF000000)
    assert payload[128:] == bytes((255, 128, 128, 255)) * 16


def test_black_spec_is_opaque_bgra_with_correct_channel_masks():
    payload = builder.black_spec_dds()
    header = struct.unpack("<31I", payload[4:128])
    assert header[18:26] == (32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00,
                              0x000000FF, 0xFF000000)
    assert payload[128:] == bytes((0, 0, 0, 255)) * 16


def test_native_asset_parser_accepts_large_xml_but_rejects_entities(tmp_path: Path):
    xml = tmp_path / "large.xml"
    xml.write_bytes(b"<TextureDictionary>" + b" " * (2 * 1024 * 1024) + b"</TextureDictionary>")
    assert builder.parse_asset_xml(xml).getroot().tag == "TextureDictionary"
    xml.write_bytes(b"<!DOCTYPE a [<!ENTITY x 'bad'>]><a>&x;</a>")
    with pytest.raises(ValueError, match="DTDs or entities"):
        builder.parse_asset_xml(xml)


def test_bla_ymt_uses_verified_stock_texture_id_two():
    ymt = etree.ElementTree(etree.fromstring(b"""<CPedVariationInfo>
      <aComponentData3><Item><aDrawblData3><Item><aTexData><Item>
      <texId value='1'/></Item></aTexData></Item></aDrawblData3></Item></aComponentData3>
      </CPedVariationInfo>"""))
    assert builder._set_ymt_texture_id(ymt, "bla") == 2
    assert ymt.xpath("string(./aComponentData3/Item/aDrawblData3/Item/aTexData/Item/texId/@value)") == "2"
    assert builder._set_ymt_texture_id(ymt, "whi") == 1


def _checked_trees(diffuse: str):
    ydd = etree.ElementTree(etree.fromstring(
        f"<DrawableDictionary><Item><ShaderGroup><Shaders><Item><Parameters>"
        f"<Item name='DiffuseSampler' type='Texture'><Name>{diffuse}</Name></Item>"
        f"</Parameters></Item></Shaders></ShaderGroup></Item></DrawableDictionary>".encode()))
    yft = etree.ElementTree(etree.fromstring(b"<Fragment><Name>pack:/ig_lamardavis</Name></Fragment>"))
    ymt = etree.ElementTree(etree.fromstring(b"<CPedVariationInfo/>"))
    ytd = etree.ElementTree(etree.fromstring(f"<TextureDictionary><Item><Name>{diffuse}</Name></Item></TextureDictionary>".encode()))
    return {"ydd": ydd, "yft": yft, "ymt": ymt, "ytd": ytd}


def test_verifier_rejects_wrong_compiled_diffuse_binding():
    authored = _checked_trees("head_diff_000_a_bla")
    checked = _checked_trees("head_diff_000_a_whi")
    with pytest.raises(ValueError, match="diffuse binding"):
        builder.verify_compiled(authored, checked, target_model="ig_lamardavis",
                                diffuse_name="head_diff_000_a_bla")


def _geometry_tree(payload_tag: str = "Data", payload: str | None = None,
                   indices: str = "0 1 0") -> etree._ElementTree:
    values = payload or "1 2 3 0 1 0 255 0 0 255 4 5 6 0 1 0 0 255 0 255"
    return etree.ElementTree(etree.fromstring(f"""
      <DrawableDictionary><Item><LodDistHigh value='100'/><DrawableModelsHigh><Item>
        <RenderMask value='255'/><Flags value='1'/><HasSkin value='1'/><BoneIndex value='0'/><Unknown1 value='2'/><Geometries><Item>
        <ShaderIndex value='0'/><BoundingBoxMin x='0' y='0' z='0' w='0'/>
        <BoundingBoxMax x='6' y='6' z='6' w='0'/><BoneIDs>0, 3</BoneIDs>
        <VertexBuffer><Flags value='0'/><Layout type='GTAV1'><Position/><Normal/><Colour0/></Layout>
          <{payload_tag}>{values}</{payload_tag}>
        </VertexBuffer><IndexBuffer><Data>{indices}</Data></IndexBuffer>
      </Item></Geometries></Item></DrawableModelsHigh><DrawableModelsLow><Item>
        <RenderMask value='255'/><Flags value='1'/><HasSkin value='1'/><BoneIndex value='0'/><Unknown1 value='2'/>
      </Item></DrawableModelsLow></Item></DrawableDictionary>
    """.encode()))


def test_geometry_roundtrip_normalizes_data2_to_data_without_losing_values():
    authored = _geometry_tree("Data2")
    checked = _geometry_tree("Data")
    builder.verify_geometry_roundtrip(authored, checked, "YDD")


def test_geometry_roundtrip_rejects_data2_values_collapsing_to_zero():
    authored = _geometry_tree("Data2")
    checked = _geometry_tree("Data", "0 " * 20)
    with pytest.raises(ValueError, match="vertex values collapsed"):
        builder.verify_geometry_roundtrip(authored, checked, "YDD")


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (".//VertexBuffer/Layout", "GTAV2", "vertex layout changed"),
        (".//DrawableModelsHigh/Item/RenderMask", "0", "RenderMask changed"),
        (".//DrawableModelsLow/Item/Flags", "0", "Flags changed"),
        ("./Item/LodDistHigh", "50", "LodDistHigh changed"),
    ],
)
def test_geometry_roundtrip_rejects_layout_model_or_lod_changes(
    path: str, value: str, message: str,
):
    authored = _geometry_tree()
    checked = _geometry_tree()
    field = checked.getroot().find(path)
    assert field is not None
    if field.tag == "Layout":
        field.set("type", value)
    else:
        field.set("value", value)
    with pytest.raises(ValueError, match=message):
        builder.verify_geometry_roundtrip(authored, checked, "YDD")


@pytest.mark.parametrize(
    ("payload", "indices", "message"),
    [
        ("1 " * 10, "0 1 0", "vertex count changed"),
        ("nan " + "0 " * 19, "0 1 0", "non-finite"),
        (None, "0 2 0", "out-of-range index"),
    ],
)
def test_geometry_roundtrip_rejects_malformed_or_unrenderable_mesh(
    payload: str | None, indices: str, message: str,
):
    authored = _geometry_tree()
    checked = _geometry_tree("Data", payload, indices)
    with pytest.raises(ValueError, match=message):
        builder.verify_geometry_roundtrip(authored, checked, "YDD")
