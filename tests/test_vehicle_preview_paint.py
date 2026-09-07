import copy
import json
from pathlib import Path

import pytest

from allin1.vehicle_preview_paint import PALETTE, apply_paint, linear_rgb, paint_for_job, select_paint
from allin1.vehicle_catalog import vehicle_model_hash


def test_seven_colors_are_stable_and_all_used():
    assert {name for name, _ in PALETTE} == {'white','black','gray','red','blue','orange','yellow'}
    assert select_paint(' Kuruma ') == select_paint('KURUMA')
    names = {select_paint('car'+str(i))['name'] for i in range(200)}
    assert names == {name for name, _ in PALETTE}
    assert all(0 < channel < 1 for _, rgb in PALETTE for channel in linear_rgb(rgb))


@pytest.mark.parametrize('category,bones,expected', [
    ('planes',[],'runway'),('helicopters',[],'runway'),
    ('military',['rotor_main_slow'],'runway'),('', ['propeller_1'],'runway'),
    ('boats',['propeller_1'],'ocean'),(' Boat ',[],'ocean'),
    ('submarines',['propeller'],'ocean'),('watercraft',[],'ocean'),
    ('planes',['propeller_1','rudder'],'runway'),
    ('sports',['wheel_lf'],'studio'),('military',[],'studio')])
def test_aircraft_use_runway_without_changing_road_vehicle_studio(category,bones,expected):
    from types import SimpleNamespace
    from allin1.vehicle_blender_renderer import preview_scene_for
    assert preview_scene_for({'category':category},[SimpleNamespace(name=n) for n in bones])==expected


def test_trusted_vehicle_scene_program_compiles():
    from allin1.vehicle_blender_scene import SCENE_SCRIPT
    compile(SCENE_SCRIPT,'vehicle-preview-scene','exec')


@pytest.mark.parametrize('bottom,top,length,expected',[
    (-.7,2.0,6,0),(-1,18,12,0),(.4,3.4,8,.88),
    (1,30,10,1.6),(-10,-6,12,-9.28),(-9,1,10,-8.4),
])
def test_vessel_waterline_preserves_origin_or_bounds_draft(bottom,top,length,expected):
    import ast
    from allin1.vehicle_blender_scene import SCENE_SCRIPT
    tree=ast.parse(SCENE_SCRIPT)
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='vessel_waterline')
    namespace={}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'waterline','exec'),namespace)
    actual=namespace['vessel_waterline'](bottom,top,length)
    assert actual==pytest.approx(expected)
    assert bottom<actual<top


@pytest.mark.parametrize('model,category,name,style', [
    ('rhino','military','','military'), ('custom_tank','military','','military'),
    ('akula','helicopters','','military'), ('annihilator','helicopters','','military'),
    ('buzzard2','helicopters','','civilian'),
    ('police','emergency','','police'), ('polgauntlet','emergency','','police'),
    ('sheriff2','','','police'), ('fbi2','','','police'),
    ('custom1','emergency','Custom Police Cruiser','police'),
    ('ambulance','emergency','','emergency'), ('firetruk','emergency','','emergency'),
    ('polaris','sports','','civilian'), ('kuruma','sports','','civilian'),
])
def test_service_exceptions(model,category,name,style):
    assert select_paint(model,category,name)['style'] == style


@pytest.mark.parametrize('model', [
    'bulldozer', 'cutter', 'dump', 'biff', 'rubble', 'tiptruck', 'tiptruck2',
    'mixer', 'mixer2', 'handler', 'forklift', ' FORKLIFT ',
])
def test_construction_equipment_is_yellow(model):
    paint = select_paint(model)
    assert paint['style'] == 'construction'
    assert paint['color'] == linear_rgb((230, 185, 18))


def test_construction_classification_is_targeted_and_preserves_service_priority():
    assert select_paint('addon', 'construction')['style'] == 'construction'
    assert select_paint('addon', 'industrial', 'Custom Dump Truck')['style'] == 'construction'
    for model in ('benson', 'stockade', 'mule', 'phantom'):
        assert select_paint(model, 'industrial')['style'] == 'civilian'
    assert select_paint('addon', 'military', 'Armored Forklift')['style'] == 'military'
    assert select_paint('police', 'emergency', 'Police Dump Truck')['style'] == 'police'


def test_construction_paint_keeps_decals_and_unpainted_trim():
    decal = dict(source_name='vehicle_decal', semantic='decal', texture_bindings=[
        dict(role='diffuse', name='construction_markings', path='decal.png')])
    trim = dict(source_name='rubber', semantic='rubber', texture_bindings=[])
    body = dict(source_name='vehicle_paint1', semantic='paint', texture_bindings=[])
    manifest = dict(materials=[copy.deepcopy(decal), copy.deepcopy(trim), body])
    apply_paint(manifest, select_paint('handler'))
    assert manifest['materials'][:2] == [decal, trim]
    assert body['preview_color'] == linear_rgb((230, 185, 18))


def test_classification_uses_catalog_and_receipt_not_game_edition(tmp_path):
    data=tmp_path/'data';data.mkdir()
    (data/'vehicles.toml').write_text('[[vehicles]]\nmodel="tank"\nclass="military"\n')
    (data/'story_vehicles.json').write_text(json.dumps({'vehicles':[{'model':'patrol','name':'Police Cruiser','category':'emergency'}]}))
    job=dict(project=tmp_path,model='tank',edition='Legacy')
    assert paint_for_job(job)['style']=='military'
    assert paint_for_job(job)==paint_for_job({**job,'edition':'Enhanced'})
    assert paint_for_job({**job,'model':'patrol'})['style']=='police'
    assert paint_for_job({**job,'model':'custom','authority':{'vehicle_category':'military'}})['style']=='military'
    (data/'catalog_only_vehicles.json').write_text(json.dumps({'vehicles':[
        {'model':'newboat','category':'boats','name':'New boat'}]}))
    assert paint_for_job({**job,'model':'newboat'})['category']=='boats'


def test_paint_changes_only_body_preserving_service_liveries_and_trim():
    def record(source,semantic):
        return dict(source_name=source,semantic=semantic,color=[.1,.2,.3],texture_bindings=[
            dict(role='diffuse',name='police_sign',path='livery.png'),
            dict(role='normal',name='normal',path='normal.png'),
            dict(role='specular',name='specular',path='specular.png'),
            dict(role='unclassified',name='mask',path='mask.png')])
    records=[record('vehicle_paint1','metal'),
        record(f'hash_{vehicle_model_hash("vehicle_paint2"):08X}','metal'),
        record('rubber','rubber'),record('window','glass'),record('decal','diffuse')]
    original=copy.deepcopy(records)
    manifest=dict(materials=records)
    apply_paint(manifest,select_paint('police'))
    assert records[0]['preview_color']==linear_rgb((25,27,29))
    assert records[1]['preview_color']==linear_rgb((225,227,224))
    assert records[2]==original[2] and records[4]==original[4]
    assert {b['role'] for b in records[0]['texture_bindings']}=={'diffuse','normal','specular'}
    assert {b['role'] for b in records[3]['texture_bindings']}=={'normal','specular'}
    civilian=dict(materials=copy.deepcopy(original))
    apply_paint(civilian,select_paint('kuruma'))
    assert {b['role'] for b in civilian['materials'][0]['texture_bindings']}=={'diffuse','normal','specular'}


def test_generic_diffuse_masks_are_not_service_liveries():
    manifest={'materials':[dict(source_name='vehicle_paint1',semantic='paint',texture_bindings=[
        dict(role='diffuse',name='vehicle_generic_alloy_silver_spec',path='mask.png')])]}
    apply_paint(manifest,select_paint('police'))
    assert manifest['materials'][0]['texture_bindings']==[]


def test_armored_layered_camo_shader_keeps_pattern_and_panel_overlay():
    manifest={'materials':[dict(source_name='hash_C30069B8',semantic='neutral fallback',texture_bindings=[
        dict(role='diffuse',slot='DiffuseSampler',name='vehicle_generic_worn_diff',path='generic.png'),
        dict(role='unclassified',slot='SnowSampler0',name='tank_camo',path='camo.png'),
        dict(role='diffuse',slot='DiffuseSampler2',name='tank_panels',path='panels.png'),
        dict(role='normal',slot='BumpSampler2',name='tank_panel_n',path='normal.png')])]}
    apply_paint(manifest,select_paint('rhino','military'))
    material=manifest['materials'][0]
    assert material['semantic']=='paint' and material['preview_camo']
    assert [(b['role'],b['name']) for b in material['texture_bindings']]==[
        ('diffuse','tank_camo'),('overlay','tank_panels'),('normal','tank_panel_n')]
    assert material['preview_color']==linear_rgb((83,91,53))


def test_rotor_cards_preserve_alpha_and_layered_body_stays_opaque():
    rotor=dict(source_name=f'hash_{vehicle_model_hash("vehicle_blurredrotor"):08X}',
        semantic='neutral fallback',texture_bindings=[dict(role='diffuse',name='blades',path='blade.png')])
    body=dict(source_name=f'hash_{vehicle_model_hash("vehicle_paint4_enveff"):08X}',
        semantic='decal',texture_bindings=[
            dict(role='diffuse',slot='DiffuseSampler',name='vehicle_generic_worn_diff',path='mask.png'),
            dict(role='diffuse',slot='DiffuseSampler2',name='annihilator_decals',path='livery.png')])
    manifest={'materials':[rotor,body]}
    apply_paint(manifest,select_paint('annihilator','helicopters'))
    assert rotor['preview_cutout'] and rotor['semantic']=='rotor'
    assert body['semantic']=='paint' and body['preview_color']
    assert body['texture_bindings']==[dict(role='overlay',slot='DiffuseSampler2',name='annihilator_decals',path='livery.png',uv_map='UV1')]


def test_apc_wear_mask_is_not_white_body_albedo():
    material=dict(source_name='vehicle_paint1',semantic='paint',texture_bindings=[
        dict(role='diffuse',name='halftrack_worn',path='mask.png'),
        dict(role='specular',name='halftrack_worn',path='mask.png')])
    apply_paint({'materials':[material]},select_paint('apc','military'))
    assert material['texture_bindings']==[dict(role='specular',name='halftrack_worn',path='mask.png')]
    assert material['preview_color']==linear_rgb((83,91,53))


def tinted_material(rgb, semantic='tyre', source='hash_1D5F09CE'):
    return dict(source_name=source, semantic=semantic, texture_bindings=[
        dict(slot='DiffuseSampler', role='diffuse', name='tyrewallwhite', path='tyre.png'),
        dict(slot='BumpSampler', role='normal', name='normal', path='normal.png')],
        shader_parameters=[dict(name='matDiffuseColor',type='Vector',values=[[*rgb,0]])])


@pytest.mark.parametrize('model', ['bruiser3', 'deathbike3'])
def test_nightmare_tyres_and_rims_use_authored_paint_channels(model):
    tyre = tinted_material((2,2,2))
    rim = tinted_material((2,4,4))
    bindings = copy.deepcopy(tyre['texture_bindings'])
    apply_paint({'materials':[tyre,rim]},select_paint(model))
    assert tyre['preview_paint_layer']==2 and rim['preview_paint_layer']==4
    assert tyre['preview_diffuse_tint']==linear_rgb((25,27,29))
    assert rim['preview_diffuse_tint']==linear_rgb((65,68,72))
    assert tyre['semantic']=='tyre' and tyre['texture_bindings']==bindings
    assert 'preview_color' not in tyre


@pytest.mark.parametrize('rgb', [(1,1,1), (0,0,0), (.05,.1,.25), (1.3,.5,.6)])
def test_fixed_authored_tints_are_not_repainted_or_gamma_converted(rgb):
    mat = tinted_material(rgb)
    apply_paint({'materials':[mat]},select_paint('deathbike3'))
    assert mat['preview_diffuse_tint']==rgb
    assert 'preview_paint_layer' not in mat


def test_authored_layer_overrides_shader_number_and_keeps_livery():
    mat = tinted_material((2,2,2),'paint','vehicle_paint1')
    mat['texture_bindings'].append(dict(slot='DiffuseSampler2',role='diffuse',name='logo',path='logo.png'))
    apply_paint({'materials':[mat]},select_paint('police'))
    assert mat['preview_color']==linear_rgb((225,227,224))
    assert any(b['name']=='logo' and b['role']=='overlay' for b in mat['texture_bindings'])


@pytest.mark.parametrize('rgb', [(2,0,0),(2,8,8),(2,2,4),(float('nan'),0,0)])
def test_invalid_paint_selector_is_not_rendered_as_white_rgb(rgb):
    with pytest.raises(ValueError,match='matDiffuseColor'):
        apply_paint({'materials':[tinted_material(rgb)]},select_paint('deathbike3'))


def test_unpainted_default_and_missing_tint_do_not_force_black_tyres():
    default = tinted_material((2,5,5))
    absent = tinted_material((2,2,2)); absent.pop('shader_parameters')
    original = copy.deepcopy(absent)
    apply_paint({'materials':[default,absent]},select_paint('deathbike3'))
    assert default['preview_diffuse_tint']==(1,1,1)
    assert absent==original
