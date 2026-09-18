from copy import deepcopy

import pytest
from lxml import etree

from allin1.protagonist_appearance import (
    HEAD_DRAWABLE, author_franklin_appearance, joaat, parse_xml_bytes,
    parse_xml_path,
)


def _bones(extra=""):
    names = (("SKEL_ROOT", -1), ("SKEL_Pelvis", 0), ("SKEL_Spine0", 1),
             ("SKEL_Spine1", 2), ("SKEL_Head", 3), ("SKEL_L_Hand", 3),
             ("SKEL_R_Hand", 3), ("SKEL_L_Foot", 1), ("SKEL_R_Foot", 1),
             ("IK_L_Foot", 7), ("IK_R_Foot", 8), ("IK_L_Hand", 5),
             ("IK_R_Hand", 6), ("IK_Root", 0))
    return "".join(
        f"<Item><Name>{name}</Name><Tag value=\"{index}\"/><Index value=\"{index}\"/>"
        f"<ParentIndex value=\"{parent}\"/>{extra}</Item>"
        for index, (name, parent) in enumerate(names)
    )


def _trees(*, drawable=None, yft_bones=None, texture_names=("head_diff_000_a_whi", "head_normal_000"), ymt_extra=""):
    drawable = drawable or f"hash_{joaat(HEAD_DRAWABLE):08X}"
    bones = _bones()
    ydd = parse_xml_bytes(f'''<DrawableDictionary><Item><Name>{drawable}</Name>
      <ShaderGroup><Shaders><Item><Parameters>
      <Item name="DiffuseSampler" type="Texture"><Name>chr_sb05</Name></Item>
      <Item name="BumpSampler" type="Texture"><Name>chr_sb05_N</Name></Item>
      <Item name="SpecSampler" type="Texture"><Name>old_spec</Name></Item>
      <Item name="VolumeSampler" type="Texture"><Name>givemechecker</Name></Item>
      </Parameters></Item></Shaders></ShaderGroup>
      <Skeleton><Bones>{bones}</Bones></Skeleton></Item></DrawableDictionary>''')
    yft = parse_xml_bytes(f"<Fragment><Name>pack:/ig_bankman</Name><Skeleton><Bones>{yft_bones or bones}</Bones></Skeleton></Fragment>")
    ymt = parse_xml_bytes("""<CPedVariationInfo>
      <bHasTexVariations value="false"/><bHasDrawblVariations value="false"/><bHasLowLODs value="false"/><bIsSuperLOD value="false"/>
      <availComp>0 255 1 2 3 4 5 6 7 255 255 255</availComp>
      <aComponentData3 itemType="CPVComponentData"><Item><numAvailTex value="1"/><aDrawblData3 itemType="CPVDrawblData"><Item><propMask value="17"/><numAlternatives value="0"/><aTexData itemType="CPVTextureData"><Item><texId value="1"/><distribution value="255"/></Item></aTexData><clothData><ownsCloth value="false"/></clothData></Item></aDrawblData3></Item>""" + ymt_extra + """</aComponentData3><aSelectionSets itemType="CPedSelectionSet"/><compInfos itemType="CComponentInfo"><Item><pedXml_audioID>none</pedXml_audioID><pedXml_audioID2>none</pedXml_audioID2><pedXml_expressionMods>0 0 0 0 0</pedXml_expressionMods><flags value="0"/><inclusions>0</inclusions><exclusions>0</exclusions><pedXml_vfxComps>PV_COMP_HEAD</pedXml_vfxComps><pedXml_flags value="0"/><pedXml_compIdx value="0"/><pedXml_drawblIdx value="0"/></Item></compInfos><propInfo><numAvailProps value="0"/><aPropMetaData itemType="CPedPropMetaData"/><aAnchors itemType="CAnchorProps"/></propInfo><dlcName/></CPedVariationInfo>""")
    textures = "".join(f"<Item><Name>{name}</Name></Item>" for name in texture_names)
    return ydd, yft, ymt, parse_xml_bytes(f"<TextureDictionary>{textures}</TextureDictionary>")


def test_authors_head_only_trees_and_exact_texture_plan_without_mutating_inputs():
    trees = _trees(ymt_extra="<Item><numAvailTex value=\"1\"/></Item>")
    before = [etree.tostring(tree) for tree in trees]
    result = author_franklin_appearance(*trees)
    assert [etree.tostring(tree) for tree in trees] == before
    assert result.ydd.getroot().findtext("./Item/Name") == f"hash_{joaat(HEAD_DRAWABLE):08X}"
    assert result.yft.getroot().findtext("./Name") == "pack:/player_one"
    root = result.ymt.getroot()
    assert root.findtext("./availComp").split() == ["0"] + ["255"] * 11
    assert len(root.findall("./aComponentData3/Item")) == 1
    assert len(root.findall("./compInfos/Item")) == 1
    assert root.find("./propInfo/numAvailProps").get("value") == "0"
    shaders = {item.get("name"): item.findtext("./Name")
               for item in result.ydd.getroot().findall("./Item/ShaderGroup/Shaders/Item/Parameters/Item")}
    assert shaders == {"DiffuseSampler": "head_diff_000_a_whi", "BumpSampler": "head_normal_000",
                       "SpecSampler": "head_spec_000", "VolumeSampler": "givemechecker"}
    embedded = result.ydd.getroot().findall("./Item/ShaderGroup/TextureDictionary/Item")
    assert [item.findtext("./Name") for item in embedded] == ["head_normal_000", "head_spec_000"]
    assert embedded[1].findtext("./Format") == "D3DFMT_A8R8G8B8"
    assert [(x.sampler, x.source_texture, x.output_texture, x.disposition) for x in result.report.textures] == [
        ("DiffuseSampler", "head_diff_000_a_whi", "head_diff_000_a_whi", "streamed_ytd"),
        ("BumpSampler", "head_normal_000", "head_normal_000", "embedded_ydd"),
        ("SpecSampler", None, "head_spec_000", "generated_black_embedded_ydd"),
        ("VolumeSampler", None, "givemechecker", "builtin_dependency"),
    ]


@pytest.mark.parametrize("drawable", ["hash_00000000", "head_000_r"])
def test_rejects_drawable_that_is_not_the_head_hash(drawable):
    with pytest.raises(ValueError, match="head_000_r hash"):
        author_franklin_appearance(*_trees(drawable=drawable))


def test_rejects_skeleton_topology_or_tag_mismatch():
    changed = _bones().replace('<Tag value="3"/>', '<Tag value="99"/>')
    with pytest.raises(ValueError, match="skeleton topology/tags differ"):
        author_franklin_appearance(*_trees(yft_bones=changed))


@pytest.mark.parametrize("textures", [("head_normal_000",), ("head_diff_000_a_whi",)])
def test_rejects_missing_required_source_texture(textures):
    with pytest.raises(ValueError, match="lacks required texture"):
        author_franklin_appearance(*_trees(texture_names=textures))


def test_rejects_multiple_drawables():
    ydd, yft, ymt, ytd = _trees()
    ydd.getroot().append(deepcopy(ydd.getroot()[0]))
    with pytest.raises(ValueError, match="exactly one whole-body drawable"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_rejects_ymt_without_component_zero_head_mapping():
    ydd, yft, ymt, ytd = _trees()
    ymt.getroot().find("./availComp").text = "255 " * 12
    with pytest.raises(ValueError, match="map component 0"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_rejects_head_ymt_with_extra_drawable_or_texture_variant():
    ydd, yft, ymt, ytd = _trees()
    head = ymt.getroot().find("./aComponentData3/Item")
    head.find("./aDrawblData3").append(deepcopy(head.find("./aDrawblData3/Item")))
    with pytest.raises(ValueError, match="exactly one drawable"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_rejects_duplicate_shader_sampler_and_malformed_flag():
    ydd, yft, ymt, ytd = _trees()
    params = ydd.getroot().find("./Item/ShaderGroup/Shaders/Item/Parameters")
    params.append(deepcopy(params[0]))
    with pytest.raises(ValueError, match="duplicate"):
        author_franklin_appearance(ydd, yft, ymt, ytd)
    ydd, yft, ymt, ytd = _trees()
    ymt.getroot().remove(ymt.getroot().find("./bHasLowLODs"))
    with pytest.raises(ValueError, match="bHasLowLODs"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_rejects_duplicate_bone_tag():
    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[2]/Tag")[0].set("value", "0")
    with pytest.raises(ValueError, match="names and tags must be unique"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_safe_parser_rejects_entities_and_oversized_input():
    with pytest.raises(ValueError, match="safe"):
        parse_xml_bytes(b'<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
    with pytest.raises(ValueError, match="byte limit"):
        parse_xml_bytes(b"<x>" + b"a" * (2 * 1024 * 1024) + b"</x>")


@pytest.mark.parametrize("payload", [b"", b"<broken>", 12])
def test_safe_parser_rejects_empty_malformed_and_non_byte_input(payload):
    with pytest.raises(ValueError, match="non-empty|safe"):
        parse_xml_bytes(payload)


def test_path_parser_requires_one_readable_bounded_regular_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing.xml"
    with pytest.raises(ValueError, match="existing regular file"):
        parse_xml_path(missing)

    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="byte limit"):
        parse_xml_path(empty)

    valid = tmp_path / "valid.xml"
    valid.write_text("<Root/>", encoding="utf-8")
    original_open = type(valid).open

    def refused(self, *args, **kwargs):
        if self == valid:
            raise OSError("refused")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(type(valid), "open", refused)
    with pytest.raises(ValueError, match="could not be read"):
        parse_xml_path(valid)


def test_authoring_rejects_non_allowlisted_target_and_wrong_tree_roots():
    with pytest.raises(ValueError, match="allowlisted"):
        author_franklin_appearance(*_trees(), target_model="player_zero")

    trees = list(_trees())
    trees[0] = parse_xml_bytes("<Fragment/>")
    with pytest.raises(ValueError, match="YDD root"):
        author_franklin_appearance(*trees)

    trees = list(_trees())
    trees[1] = None
    with pytest.raises(ValueError, match="YFT must be"):
        author_franklin_appearance(*trees)


def test_skeleton_validation_rejects_missing_malformed_and_noncontiguous_bones():
    ydd, yft, ymt, ytd = _trees()
    skeleton = ydd.getroot().find("./Item/Skeleton")
    skeleton.getparent().remove(skeleton)
    with pytest.raises(ValueError, match="exactly one skeleton"):
        author_franklin_appearance(ydd, yft, ymt, ytd)

    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[2]/Index")[0].set("value", "8")
    with pytest.raises(ValueError, match="contiguous"):
        author_franklin_appearance(ydd, yft, ymt, ytd)

    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[2]/Tag")[0].attrib.clear()
    with pytest.raises(ValueError, match="malformed skeleton"):
        author_franklin_appearance(ydd, yft, ymt, ytd)


def test_skeleton_validation_rejects_bad_root_parent_tag_and_ancestry():
    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[1]/Name")[0].text = "OTHER_ROOT"
    with pytest.raises(ValueError, match="one SKEL_ROOT"):
        author_franklin_appearance(ydd, yft, ymt, ytd)

    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[2]/ParentIndex")[0].set("value", "99")
    with pytest.raises(ValueError, match="earlier and acyclic"):
        author_franklin_appearance(ydd, yft, ymt, ytd)

    ydd, yft, ymt, ytd = _trees()
    for tree in (ydd, yft):
        tree.getroot().xpath(".//Skeleton/Bones/Item[5]/ParentIndex")[0].set("value", "1")
    with pytest.raises(ValueError, match="ancestry"):
        author_franklin_appearance(ydd, yft, ymt, ytd)
