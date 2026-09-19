"""Real SDK interchange regression: small/large vehicles retain symbol UVs."""
from pathlib import Path
import pytest


@pytest.mark.parametrize('scale',[.25,1.,8.])
def test_body_and_decal_keep_authored_relative_scale_and_uvs(tmp_path,monkeypatch,scale):
    pytest.importorskip('allin1_sdk.compiled_render', reason='Installed SDK required for real interchange test')
    from allin1_sdk.native_assets import NativeModelScene,_ModelGeometry
    from allin1_sdk.compiled_render import export_render_interchange
    uv=((.125,.25),(.875,.25),(.125,.75))
    def geometry(name,points,shader):
        return _ModelGeometry(vertices=tuple(tuple(v*scale for v in point) for point in points),
            triangles=((0,1,2),),lod='High',component=name,material_name=shader,texcoords=uv)
    body=geometry('body',((0,0,0),(4,0,0),(0,0,2)),'vehicle_paint1')
    decal=geometry('symbol',((1,-.002,.5),(2,-.002,.5),(1,-.002,1)),'vehicle_decal')
    result=export_render_interchange(NativeModelScene('fixture',(body,decal)),tmp_path)
    lines=result.obj_path.read_text().splitlines()
    vertices=[tuple(map(float,line.split()[1:])) for line in lines if line.startswith('v ')]
    uvs=[tuple(map(float,line.split()[1:])) for line in lines if line.startswith('vt ')]
    assert vertices==list(body.vertices+decal.vertices)
    assert uvs==[(u,1-v) for u,v in uv]*2


def test_decode_transform_and_export_preserve_distinct_uv_channels():
    from lxml import etree
    from allin1_sdk.native_assets import _read_model_geometry, _transform_model_geometry
    from allin1.vehicle_blender_renderer import export_vehicle_meshes
    root=etree.fromstring(b'''<Item><VertexBuffer><Layout><Position/><TexCoord0/><TexCoord1/></Layout>
      <Data>0 0 0  0 0  .2 .3\n1 0 0  1 0  .4 .3\n0 1 0  0 1  .2 .7</Data>
      </VertexBuffer><IndexBuffer><Data>0 1 2</Data></IndexBuffer></Item>''')
    g=_read_model_geometry(root.find('VertexBuffer'))
    assert g.texcoords==((0,0),(1,0),(0,1))
    assert g.texcoord_sets[1]==((.2,.3),(.4,.3),(.2,.7))
    moved=_transform_model_geometry(g,((2,0,0,4),(0,2,0,0),(0,0,2,1),(0,0,0,1)),
                                    'mirrored',reverse_winding=True)
    assert moved.texcoord_sets==g.texcoord_sets
    row=export_vehicle_meshes([moved],['mat'])[0]
    assert row['uv_layers']['UV0']==[(0,1),(1,1),(0,0)]
    assert row['uv_layers']['UV1'][0]==pytest.approx((.2,.7))
    assert row['triangles']==((0,2,1),)


@pytest.mark.parametrize('shader',['vehicle_paint3','vehicle_paint4_enveff','vehicle_paint6','vehicle_paint7'])
def test_layered_livery_binds_uv1(shader):
    from allin1.vehicle_preview_paint import apply_paint,select_paint
    from allin1.vehicle_catalog import vehicle_model_hash
    for source in (shader,f'hash_{vehicle_model_hash(shader):08X}'):
        mat=dict(source_name=source,semantic='paint',texture_bindings=[
            dict(slot='DiffuseSampler2',role='diffuse',name='logo',path='logo.png')])
        apply_paint({'materials':[mat]},select_paint('boxville'))
        assert mat['texture_bindings'][0]['uv_map']=='UV1'
        assert mat['texture_bindings'][0]['role']=='overlay'


def test_invalid_secondary_uv_is_rejected():
    from allin1_sdk.native_assets import _ModelGeometry
    from allin1.vehicle_blender_renderer import export_vehicle_meshes
    g=_ModelGeometry(((0,0,0),),(), 'High',texcoord_sets=(((0,0),),((float('nan'),0),)))
    with pytest.raises(ValueError,match='UV channel'):export_vehicle_meshes([g],['mat'])


def test_unused_invalid_channel_is_absent_not_fabricated():
    from lxml import etree
    from allin1_sdk.native_assets import _read_model_geometry
    root=etree.fromstring(b'''<Item><VertexBuffer><Layout><Position/><TexCoord0/><TexCoord1/><TexCoord2/></Layout>
      <Data>0 0 0  0 0  .2 .3  NaN NaN\n1 0 0  1 0  .4 .3  0 0\n0 1 0  0 1  .2 .7  1 1</Data>
      </VertexBuffer><IndexBuffer><Data>0 1 2</Data></IndexBuffer></Item>''')
    g=_read_model_geometry(root.find('VertexBuffer'))
    assert len(g.texcoords)==3 and len(g.texcoord_sets[1])==3
    assert g.texcoord_sets[2]==()


def test_primary_invalid_uv_is_strict_unless_consumer_validates_selection():
    from lxml import etree
    from allin1_sdk.native_assets import _read_model_geometry
    root=etree.fromstring(b'<Item><VertexBuffer><Layout><Position/><TexCoord0/></Layout><Data>0 0 0 NaN NaN</Data></VertexBuffer></Item>')
    with pytest.raises(ValueError,match='non-finite'):
        _read_model_geometry(root.find('VertexBuffer'))
    g=_read_model_geometry(root.find('VertexBuffer'),defer_uv_validation=True)
    assert g.texcoords==() and g.texcoord_sets==((),)


def test_constant_and_transparent_masks_need_no_uv_but_graphics_do(tmp_path):
    from PIL import Image
    from allin1.vehicle_blender_renderer import constant_texture_bindings,validate_material_uvs
    Image.new('RGBA',(2,2),(20,30,40,0)).save(tmp_path/'blank.png')
    Image.new('RGBA',(2,2),(128,128,128,255)).save(tmp_path/'mask.png')
    mat=dict(key='mat',source_name='paint',texture_bindings=[
        dict(role='overlay',path='blank.png',name='blank',uv_map='UV1'),
        dict(role='specular',slot='SpecSampler',path='mask.png',name='mask',uv_map='UV1')])
    manifest=dict(materials=[mat],meshes=[dict(material='mat',uv_layers={})])
    constant_texture_bindings(manifest,tmp_path)
    assert len(mat['texture_bindings'])==1 and mat['texture_bindings'][0]['constant_texture']
    validate_material_uvs(manifest)
    mat['texture_bindings']=[dict(role='overlay',path='graphic.png',name='logo',uv_map='UV1')]
    with pytest.raises(ValueError,match='Missing authored UV1'):validate_material_uvs(manifest)


def test_paint9_livery_uses_uv1_not_weather_uv2():
    from allin1.vehicle_preview_paint import apply_paint,select_paint
    mat=dict(source_name='vehicle_paint9',semantic='paint',texture_bindings=[
        dict(slot='DiffuseSampler2',role='diffuse',name='logo',path='logo.png'),
        dict(slot='SpecSampler',role='specular',name='spec',path='spec.png')])
    apply_paint({'materials':[mat]},select_paint('conada'))
    assert [b['uv_map'] for b in mat['texture_bindings']]==['UV1','UV2']
