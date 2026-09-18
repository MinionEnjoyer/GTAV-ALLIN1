from copy import deepcopy

import pytest
from lxml import etree

from allin1.character_appearance import author_character_appearance
from allin1.protagonist_appearance import HEAD_DRAWABLE, joaat, parse_xml_bytes


def _bones():
    names = (("SKEL_ROOT", -1), ("SKEL_Pelvis", 0), ("SKEL_Spine0", 1),
             ("SKEL_Spine1", 2), ("SKEL_Head", 3), ("SKEL_L_Hand", 3),
             ("SKEL_R_Hand", 3), ("SKEL_L_Foot", 1), ("SKEL_R_Foot", 1),
             ("IK_L_Foot", 7), ("IK_R_Foot", 8), ("IK_L_Hand", 5),
             ("IK_R_Hand", 6), ("IK_Root", 0))
    return "".join(
        f'<Item><Name>{name}</Name><Tag value="{index}"/><Index value="{index}"/>'
        f'<ParentIndex value="{parent}"/></Item>'
        for index, (name, parent) in enumerate(names)
    )


def _trees(*, second_drawable=False, second_shader=False, include_palette=True, shader_extra="", yft_bones=None,
           textures=("patrick_diffuse", "patrick_normal")):
    bones = _bones()
    shader = f'''<Item><Parameters>
      <Item name="DiffuseSampler" type="Texture"><Name>source_diffuse</Name></Item>
      {"<Item name=\"TextureSamplerDiffPal\" type=\"Texture\"/>" if include_palette else ""}<Item name="VolumeSampler" type="Texture"/>
      <Item name="BumpSampler" type="Texture"/><Item name="SpecSampler" type="Texture"/>{shader_extra}
      </Parameters></Item>'''
    drawable = f'''<Item><Name>hash_976FBF04</Name><ShaderGroup><Shaders>{shader}{shader if second_shader else ''}</Shaders></ShaderGroup><Skeleton><Bones>{bones}</Bones></Skeleton></Item>'''
    ydd = parse_xml_bytes(f"<DrawableDictionary>{drawable}{drawable if second_drawable else ''}</DrawableDictionary>")
    yft = parse_xml_bytes(f"<Fragment><Name>pack:/ig_bankman</Name><Skeleton><Bones>{yft_bones or bones}</Bones></Skeleton></Fragment>")
    ymt = parse_xml_bytes('''<CPedVariationInfo><bHasTexVariations value="false"/><bHasDrawblVariations value="false"/><bHasLowLODs value="false"/><bIsSuperLOD value="false"/>
      <availComp>0 255 1 2 3 4 5 6 7 255 255 255</availComp><aComponentData3 itemType="CPVComponentData"><Item><numAvailTex value="1"/><aDrawblData3 itemType="CPVDrawblData"><Item><propMask value="17"/><numAlternatives value="0"/><aTexData itemType="CPVTextureData"><Item><texId value="1"/></Item></aTexData><clothData><ownsCloth value="false"/></clothData></Item></aDrawblData3></Item></aComponentData3><aSelectionSets itemType="CPedSelectionSet"/><compInfos itemType="CComponentInfo"><Item><pedXml_compIdx value="0"/><pedXml_drawblIdx value="0"/></Item></compInfos><propInfo><numAvailProps value="0"/><aPropMetaData itemType="CPedPropMetaData"/><aAnchors itemType="CAnchorProps"/></propInfo><dlcName/></CPedVariationInfo>''')
    entries = "".join(f'<Item><Name>{name}</Name><Usage>DIFFUSE</Usage><FileName>{name}.dds</FileName></Item>' for name in textures)
    return ydd, yft, ymt, parse_xml_bytes(f"<TextureDictionary>{entries}</TextureDictionary>")


def test_authors_patrick_with_supplied_normal_without_mutating_inputs():
    trees = _trees()
    before = [etree.tostring(tree) for tree in trees]
    result = author_character_appearance(*trees, target_model="ig_lamardavis",
                                         diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    assert [etree.tostring(tree) for tree in trees] == before
    assert result.yft.getroot().findtext("./Name") == "pack:/ig_lamardavis"
    assert result.ydd.getroot().findtext("./Item/Name") == f"hash_{joaat(HEAD_DRAWABLE):08X}"
    parameters = {item.get("name"): item.findtext("./Name") for item in result.ydd.xpath("./Item/ShaderGroup/Shaders/Item/Parameters/Item[@type='Texture']")}
    assert parameters["DiffuseSampler"] == "head_diff_000_a_whi"
    assert parameters["BumpSampler"] == "head_normal_000"
    assert parameters["SpecSampler"] == "head_spec_000"
    assert parameters["VolumeSampler"] == "givemechecker"
    assert len(result.ymt.getroot().findall("./aComponentData3/Item")) == 1
    assert result.ymt.getroot().findtext("./availComp").split() == ["0"] + ["255"] * 11
    textures = result.ydd.xpath("./Item/ShaderGroup/TextureDictionary/Item")
    assert [(x.findtext("./Name"), x.findtext("./Usage")) for x in textures] == [("head_normal_000", "NORMAL"), ("head_spec_000", "SPECULAR")]


def test_authors_patrick_layout_without_optional_palette_sampler():
    result = author_character_appearance(*_trees(include_palette=False), target_model="cs_lamardavis",
                                         diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    assert result.yft.getroot().findtext("./Name") == "pack:/cs_lamardavis"


def test_rejects_unverified_palette_binding_without_mutating_input():
    trees = _trees()
    ydd = trees[0]
    palette = ydd.xpath("./Item/ShaderGroup/Shaders/Item/Parameters/Item[@name='TextureSamplerDiffPal']")[0]
    etree.SubElement(palette, "Name").text = "untracked_palette"
    before = etree.tostring(ydd)
    with pytest.raises(ValueError, match="unverified palette"):
        author_character_appearance(*trees, target_model="ig_lamardavis",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    assert etree.tostring(ydd) == before


def test_authors_krabs_with_generated_flat_normal_and_complete_bindings():
    result = author_character_appearance(*_trees(textures=("krabs_diffuse",)), target_model="ig_ballasog",
                                         diffuse_texture="krabs_diffuse", normal_texture=None)
    textures = result.ydd.xpath("./Item/ShaderGroup/TextureDictionary/Item")
    assert textures[0].findtext("./Name") == "head_normal_000"
    assert textures[0].findtext("./Usage") == "NORMAL"
    assert textures[0].findtext("./Format") == "D3DFMT_A8R8G8B8"
    names = {item.get("name"): item.findtext("./Name") for item in result.ydd.xpath("./Item/ShaderGroup/Shaders/Item/Parameters/Item[@type='Texture']")}
    assert all(names[name] for name in ("DiffuseSampler", "BumpSampler", "SpecSampler", "VolumeSampler"))
    assert result.report.textures[1].disposition == "generated_flat_embedded_ydd"


@pytest.mark.parametrize("target", ["ig_unknown", "", "player_two"])
def test_rejects_unknown_target(target):
    with pytest.raises(ValueError, match="allowlisted"):
        author_character_appearance(*_trees(), target_model=target,
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")


def test_rejects_missing_diffuse_or_normal_source_texture():
    with pytest.raises(ValueError, match="diffuse"):
        author_character_appearance(*_trees(), target_model="ig_stretch",
                                    diffuse_texture="missing", normal_texture="patrick_normal")
    with pytest.raises(ValueError, match="normal"):
        author_character_appearance(*_trees(), target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="missing")


@pytest.mark.parametrize("drawable", ["hash_00000000", "another_drawable"])
def test_rejects_source_drawable_other_than_head_hash(drawable):
    ydd, yft, ymt, ytd = _trees()
    ydd.getroot().find("./Item/Name").text = drawable
    with pytest.raises(ValueError, match="head_000_r"):
        author_character_appearance(ydd, yft, ymt, ytd, target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")


def test_rejects_duplicate_source_texture_names():
    ydd, yft, ymt, ytd = _trees()
    ytd.getroot().append(deepcopy(ytd.getroot()[0]))
    with pytest.raises(ValueError, match="duplicate texture"):
        author_character_appearance(ydd, yft, ymt, ytd, target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")


def test_rejects_malformed_skeleton_multiple_drawables_and_shaders():
    malformed = _bones().replace('<ParentIndex value="0"/>', '<ParentIndex value="99"/>', 1)
    with pytest.raises(ValueError, match="parents"):
        author_character_appearance(*_trees(yft_bones=malformed), target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    with pytest.raises(ValueError, match="one whole-body drawable"):
        author_character_appearance(*_trees(second_drawable=True), target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    with pytest.raises(ValueError, match="unsupported texture samplers"):
        author_character_appearance(*_trees(shader_extra='<Item name="Other" type="Texture"/>'), target_model="ig_stretch",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")


def test_rejects_multiple_shader_and_skeleton_mismatch():
    with pytest.raises(ValueError, match="exactly one supported"):
        author_character_appearance(*_trees(second_shader=True), target_model="csb_ballasog",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
    ydd, yft, ymt, ytd = _trees()
    yft.getroot().xpath("./Skeleton/Bones/Item[2]/Tag")[0].set("value", "42")
    with pytest.raises(ValueError, match="topology/tags differ"):
        author_character_appearance(ydd, yft, ymt, ytd, target_model="csb_ballasog",
                                    diffuse_texture="patrick_diffuse", normal_texture="patrick_normal")
