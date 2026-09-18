"""Focused contract tests for the private Franklin-appearance builder."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys

import pytest
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_franklin_appearance", ROOT / "tools" / "build_franklin_appearance.py",
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


def test_metadata_registers_only_an_overlaid_ped_stream_archive():
    content, setup = builder.metadata()
    root = etree.fromstring(content.encode())
    entries = root.findall("./dataFiles/Item")
    assert len(entries) == 1
    entry = entries[0]
    uri = "dlc_franklin_spongebob:/%PLATFORM%/models/cdimages/streamedpeds_players.rpf"
    assert entry.findtext("./filename") == uri
    assert entry.findtext("./fileType") == "PEDSTREAM_FILE"
    assert entry.find("./overlay").get("value") == "true"
    assert entry.find("./disabled").get("value") == "true"
    assert entry.find("./persistent").get("value") == "true"
    assert root.xpath("//filesToEnable/Item/text()") == [uri]
    assert not root.xpath("//filename[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'peds.meta')]")
    setup_root = etree.fromstring(setup.encode())
    assert setup_root.findtext("./deviceName") == "dlc_franklin_spongebob"
    assert setup_root.xpath("./contentChangeSetGroups/Item[NameHash='GROUP_STARTUP']/ContentChangeSets/Item/text()") == ["CONTENT_UNLOCKING_META"]


def test_black_spec_dds_is_a_deterministic_opaque_bgra_4x4_payload():
    first = builder.black_spec_dds()
    assert first == builder.black_spec_dds()
    assert len(first) == 128 + 4 * 4 * 4
    assert first[:4] == b"DDS "
    header = struct.unpack("<31I", first[4:128])
    assert header[0] == 124
    assert header[1] == 0x100F
    assert header[2:7] == (4, 4, 16, 0, 1)
    assert header[18:26] == (32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00,
                              0x000000FF, 0xFF000000)
    assert header[26] == 0x1000
    assert first[128:] == bytes((0, 0, 0, 255)) * 16


def _source_tree(path: Path, *, stems=("spongebob", "spongebob", "spongebob", "spongebob")) -> Path:
    path.mkdir()
    for suffix, stem in zip(("ydd", "yft", "ymt", "ytd"), stems):
        (path / f"{stem}.{suffix}").write_bytes(b"asset")
    return path


def _tool_and_game(path: Path) -> tuple[Path, Path]:
    patcher = path / "RpfPatcher.exe"
    patcher.write_bytes(b"tool")
    game = path / "game"
    game.mkdir()
    (game / "GTA5_Enhanced.exe").write_bytes(b"game")
    return patcher, game


def test_prepare_paths_accepts_one_matching_asset_of_each_type(tmp_path):
    source = _source_tree(tmp_path / "source")
    patcher, game = _tool_and_game(tmp_path)
    assets = builder.prepare_paths(source, tmp_path / "output", patcher, game)
    assert set(assets) == {"ydd", "yft", "ymt", "ytd"}
    assert {path.stem for path in assets.values()} == {"spongebob"}


@pytest.mark.parametrize("kind", ["existing", "inside_game", "inside_source"])
def test_prepare_paths_refuses_unsafe_output_locations(tmp_path, kind):
    source = _source_tree(tmp_path / "source")
    patcher, game = _tool_and_game(tmp_path)
    if kind == "existing":
        output = tmp_path / "existing"
        output.mkdir()
    elif kind == "inside_game":
        output = game / "appearance-output"
    else:
        output = source / "appearance-output"
    with pytest.raises(ValueError, match="Output"):
        builder.prepare_paths(source, output, patcher, game)


def test_prepare_paths_rejects_missing_or_mismatched_source_assets(tmp_path):
    source = _source_tree(tmp_path / "source", stems=("spongebob", "spongebob", "spongebob", "other"))
    patcher, game = _tool_and_game(tmp_path)
    with pytest.raises(ValueError, match="basenames"):
        builder.prepare_paths(source, tmp_path / "output", patcher, game)
    (source / "other.ytd").unlink()
    with pytest.raises(ValueError, match="exactly one source .ytd"):
        builder.prepare_paths(source, tmp_path / "output", patcher, game)


def test_semantic_xml_ignores_formatting_but_preserves_structure_and_attributes():
    first = etree.fromstring(b"<x b='2' a='1'><y> hello  world </y></x>")
    equal = etree.fromstring(b"<x a='1' b='2'><y>hello world</y></x>")
    changed = etree.fromstring(b"<x a='1' b='3'><y>hello world</y></x>")
    assert builder.semantic_xml(first) == builder.semantic_xml(equal)
    assert builder.semantic_xml(first) != builder.semantic_xml(changed)
