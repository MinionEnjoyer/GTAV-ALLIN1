import sys
from pathlib import Path
from dataclasses import dataclass
import pytest
import numpy as np
from lxml import etree as E
from allin1.stock_weapon_previews import default_components,component_preview
from allin1.weapon_preview_assembly import bone_matrix,attach_geometry,unique_component

@pytest.fixture
def sdk_geometry():
    # The compiled preview worker owns this optional dependency. Ordinary
    # launcher installations and unit-test jobs do not require the SDK.
    pytest.importorskip('allin1_sdk.native_assets', reason='SDK geometry integration requires the preview build dependency')

def root(name,position):
    return E.fromstring(f'''<Drawable><Skeleton><Bones><Item><Name>{name}</Name><ParentIndex value="-1"/>
      <Translation x="{position}" y="0" z="0"/><Rotation x="0" y="0" z="0" w="1"/>
      <Scale x="1" y="1" z="1"/></Item></Bones></Skeleton></Drawable>''')

@dataclass(frozen=True)
class Geometry:
    vertices:tuple

def test_attachment_matches_parent_and_child_pivots(sdk_geometry):
    gs=[Geometry(((2.,0.,0.),(3.,1.,0.)))]
    placed=attach_geometry(root('WAPClip',10),root('AAPClip',2),gs,'WAPClip','AAPClip')
    assert np.allclose(placed[0].vertices,[(10,0,0),(11,1,0)])
    assert gs[0].vertices[0]==(2.,0.,0.)

def test_missing_anchor_blocks_partial_preview(sdk_geometry):
    with pytest.raises(ValueError,match='attachment bone'):bone_matrix(root('gun_root',0),'missing')

def test_cycle_blocks_assembly(sdk_geometry):
    r=root('WAPClip',0);r.find('Skeleton/Bones/Item/ParentIndex').set('value','0')
    with pytest.raises(ValueError,match='hierarchy'):bone_matrix(r,'WAPClip')

def test_default_parts_only_not_every_optional_barrel():
    r=E.fromstring('''<Item><AttachPoints><Item><AttachBone>WAPBarrel</AttachBone><Components>
      <Item><Name>BARREL_DEFAULT</Name><Default value="true"/></Item>
      <Item><Name>BARREL_HEAVY</Name><Default value="false"/></Item></Components></Item></AttachPoints></Item>''')
    assert default_components(r)==[{'name':'BARREL_DEFAULT','parent_bone':'WAPBarrel'}]
    r.find('.//Components/Item[2]/Default').set('value','true')
    with pytest.raises(ValueError,match='Ambiguous'):default_components(r)

def test_component_identity_invalidates_cached_preview():
    from allin1.prelaunch_previews import key_for
    base={'weapon':'WEAPON_ASSAULTRIFLE_MK2','components':[{'model':'barrel1'}]}
    revised={**base,'components':[{'model':'barrel2'}]}
    assert key_for(base,'Enhanced','renderer')!=key_for(revised,'Enhanced','renderer')

def test_pack_with_multiple_component_metadata_files_resolves_by_id():
    roots=[E.fromstring('<Root><Item><Name>COMPONENT_A</Name><Model>model_a</Model></Item></Root>'),
           E.fromstring('<Root><Item><Name>COMPONENT_B</Name><Model>model_b</Model></Item></Root>')]
    assert unique_component(roots,'COMPONENT_B').findtext('Model')=='model_b'
    with pytest.raises(ValueError,match='ambiguous'):unique_component([*roots,roots[1]],'COMPONENT_B')


def test_component_root_is_allowed_only_for_child_and_tag_zero(sdk_geometry):
    child=root('W_PI_APPistol_Mag1',2)
    E.SubElement(child.find('Skeleton/Bones/Item'),'Tag',value='0')
    assert bone_matrix(child,'AAPClip',component_root=True)[0,3]==2
    assert bone_matrix(child,'',component_root=True)[0,3]==2
    with pytest.raises(ValueError,match='attachment bone'):bone_matrix(child,'AAPClip')
    child.find('Skeleton/Bones/Item/Tag').set('value','42')
    with pytest.raises(ValueError,match='attachment bone'):bone_matrix(child,'AAPClip',component_root=True)


def test_duplicate_identity_anchor_child_is_equivalent(sdk_geometry):
    import copy
    parent=root('WAPScop_2',4)
    bone=parent.find('Skeleton/Bones/Item');E.SubElement(bone,'Tag',value='3634')
    alias=copy.deepcopy(bone);alias.find('ParentIndex').set('value','0');alias.find('Translation').set('x','0')
    parent.find('Skeleton/Bones').append(alias)
    assert bone_matrix(parent,'WAPScop_2')[0,3]==4
    alias.find('Translation').set('x','0.01')
    with pytest.raises(ValueError,match='ambiguous'):bone_matrix(parent,'WAPScop_2')
    alias.find('Translation').set('x','4');alias.find('ParentIndex').set('value','-1')
    with pytest.raises(ValueError,match='ambiguous'):bone_matrix(parent,'WAPScop_2')


def test_singular_component_pivot_is_rejected(sdk_geometry):
    child=root('AAPClip',0);child.find('Skeleton/Bones/Item/Scale').set('x','0')
    with pytest.raises(ValueError,match='Singular'):attach_geometry(root('WAPClip',0),child,[],'WAPClip','AAPClip')


def test_metadata_controls_render_object_creation():
    row=E.fromstring('<Item><Model>w_lr_40mm</Model><AttachBone/><CreateObject value="false"/></Item>')
    assert component_preview(row)=={'model':'w_lr_40mm','child_bone':'','create_object':False}
    row.find('CreateObject').set('value','true');assert component_preview(row)['create_object']
    row.find('CreateObject').set('value','invalid')
    with pytest.raises(ValueError,match='CreateObject'):component_preview(row)

def test_real_regression_previews_have_required_parts():
    import json
    path=Path(__file__).resolve().parents[1]/'build/preview-assembly-20260906/discovery.json'
    if not path.exists():pytest.skip('Local game fixtures not distributed')
    rows={r['weapon']:r for r in json.loads(path.read_text())['items']}
    assert [p['name'] for p in rows['WEAPON_NAVYREVOLVER']['components']]==['COMPONENT_NAVYREVOLVER_CLIP_01']
    assert {p['name'] for p in rows['WEAPON_ASSAULTRIFLE_MK2']['components']}=={'COMPONENT_ASSAULTRIFLE_MK2_CLIP_01','COMPONENT_AT_AR_BARREL_01'}
