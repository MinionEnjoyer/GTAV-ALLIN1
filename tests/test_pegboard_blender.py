from dataclasses import dataclass
import numpy as np
from PIL import Image
import pytest
from allin1.pegboard_blender_renderer import prepare_texture, export_pegboard


def test_alpha_palette_is_baked_as_color_not_transparency():
    image=Image.fromarray(np.array([[[100,200,50,32],[200,100,50,33]]],dtype=np.uint8))
    palette=Image.fromarray(np.array([[[255,0,0],[0,255,0]]],dtype=np.uint8))
    result,tints=prepare_texture(image,{'palette':'PAL','palette_mode':'alpha'},{'pal':palette},3)
    assert np.array(result).tolist()==[[[100,0,0,255],[0,100,0,255]]]
    assert tints is None


def test_vertex_palette_keeps_per_vertex_tints():
    palette=Image.fromarray(np.array([[[255,0,0],[0,255,0]]],dtype=np.uint8))
    material=dict(palette='pal',palette_mode='vertex',vertex_colours=[(0,0,0,0),(0,0,255,0)])
    result,tints=prepare_texture(Image.new('RGBA',(1,1),(50,60,70,0)),material,{'pal':palette},2)
    assert tints==[[1.,0.,0.],[0.,1.,0.]]
    assert result.getpixel((0,0))==(50,60,70,255)
    with pytest.raises(ValueError,match='vertex tint'):prepare_texture(result,material,{'pal':palette},3)


def test_only_real_transparency_survives():
    image=Image.fromarray(np.array([[[50,60,70,80],[50,60,70,100]]],dtype=np.uint8))
    result,_=prepare_texture(image,{}, {},2)
    assert np.array(result)[:,:,3].tolist()==[[0,255]]
    result,_=prepare_texture(image,{'decal':True}, {},2)
    assert np.array(result)[:,:,3].tolist()==[[80,100]]


@dataclass
class Geometry:
    vertices:tuple=((0.,0.,0.),(1.,0.,0.),(0.,0.,1.))
    triangles:tuple=((0,1,2),)
    texcoords:tuple=((0.,0.),(1.,0.),(0.,1.))


def test_opaque_magazine_alpha_is_material_data_not_a_cutout():
    source=Image.fromarray(np.array([[[65,70,75,0],[80,85,90,32],[95,100,105,64]]],dtype=np.uint8))
    result,_=prepare_texture(source,{'opaque':True},{},3)
    assert np.array(result)[:,:,3].tolist()==[[255,255,255]]
    assert np.array(result)[:,:,:3].tolist()==np.array(source)[:,:,:3].tolist()


def test_export_preserves_component_local_textures_and_framing(tmp_path):
    a,b=Geometry(),Geometry()
    red=Image.new('RGBA',(2,2),'red');blue=Image.new('RGBA',(2,2),'blue')
    output=export_pegboard([a,b],{'body':red},lambda _:'body',{id(b):{'textures':{'body':blue}}},tmp_path)
    assert len(output['meshes'])==2
    assert Image.open(tmp_path/'diffuse-0.png').getpixel((0,0))==(255,0,0,255)
    assert Image.open(tmp_path/'diffuse-1.png').getpixel((0,0))==(0,0,255,255)
    points=np.array(output['meshes'][0]['vertices'])
    assert np.ptp(points[:,0])<=3.2*.84+1e-8 and np.ptp(points[:,1])<=2*.74+1e-8
    assert output['board_z']<points[:,2].min()
    assert output['meshes'][0]['uv'][0]==[0.,1.]
    assert output['meshes'][0]['triangles']==[[0,2,1]]
    assert output['display_copies']==[]


def test_parachute_preview_is_blue_without_changing_source_or_other_gear(tmp_path):
    g=Geometry()
    source=Image.new('RGBA',(2,1),(255,255,255,255))
    source.putpixel((1,0),(0,0,0,255))
    original=source.tobytes()
    export_pegboard([g],{'body':source},lambda _:'body',{},tmp_path,
                    category='gear',model='p_parachute_s')
    with Image.open(tmp_path/'diffuse-0.png') as image:
        assert image.getpixel((0,0))==(45,95,175,255)
        assert image.getpixel((1,0))==(0,0,0,255)
    assert source.tobytes()==original
    export_pegboard([g],{'body':source},lambda _:'body',{},tmp_path,
                    category='gear',model='prop_bodyarmour_02')
    with Image.open(tmp_path/'diffuse-0.png') as image:
        assert image.getpixel((0,0))==(255,255,255,255)


@pytest.mark.parametrize('resting_flat',[True,False])
def test_throwable_rests_on_crate_lid_with_uvs_intact(tmp_path,resting_flat):
    g=Geometry(vertices=((0,0,0),(.1,0,0),(0,.2,.5)))
    output=export_pegboard([g],{'body':Image.new('RGBA',(1,1),'red')},lambda _:'body',{},tmp_path,
        backdrop='ammo-crate',resting_flat=resting_flat)
    points=np.array(output['meshes'][0]['vertices'])
    assert output['preview_scene']=='ammo-crate'
    assert points[:,2].min()==pytest.approx(output['support_z'])
    if resting_flat:assert points[:,2].min()==pytest.approx(.962)
    else:
        assert points[:,2].max()>=1.1-1e-8
        assert np.ptp(points[:,0])<=.36+1e-8 and np.ptp(points[:,1])<=.36+1e-8
    assert np.ptp(points,axis=0).max()<=.72+1e-8
    assert output['crate_open']==(not resting_flat)
    assert output['meshes'][0]['uv']==[[0,1],[1,1],[0,0]]
    assert len(output['display_copies'])==(1 if resting_flat else 3)
    for offset in [(0,0,0)]+output['display_copies']:
        instance=points+offset
        assert instance[:,0].min()>-.63 and instance[:,0].max()<.63
        assert instance[:,1].min()>-.45 and instance[:,1].max()<.45
        assert instance[:,2].min()==pytest.approx(output['support_z'])


def test_flat_throwable_copies_fit_separate_lid_rows(tmp_path):
    # Wide, almost square packages must not overlap when duplicated.
    g=Geometry(vertices=((0,0,0),(.8,0,0),(0,.7,.1),(.8,.7,.1)),
        triangles=((0,1,2),(1,3,2)),texcoords=((0,0),(1,0),(0,1),(1,1)))
    output=export_pegboard([g],{'body':Image.new('RGBA',(1,1),'red')},lambda _:'body',{},tmp_path,
        backdrop='ammo-crate',resting_flat=True)
    first=np.array(output['meshes'][0]['vertices']);second=first+output['display_copies'][0]
    assert first[:,1].max()<second[:,1].min()
    assert first[:,1].min()>-.45 and second[:,1].max()<.45


def test_crate_scene_program_compiles():
    from allin1.pegboard_blender_scene import SCENE_SCRIPT
    compile(SCENE_SCRIPT,'catalog-scene','exec')


@pytest.mark.parametrize('model',['w_ex_pe','w_ex_apmine'])
def test_flat_packages_keep_authored_top_up_without_pca_tilt(tmp_path,model):
    g=Geometry(vertices=((-1,-2,0),(1,-2,0),(-1,2,0),(1,2,1)),
        triangles=((0,1,2),(1,3,2)),texcoords=((0,0),(1,0),(0,1),(1,1)))
    output=export_pegboard([g],{'body':Image.new('RGBA',(1,1),'red')},lambda _:'body',{},tmp_path,
        backdrop='ammo-crate',resting_flat=True,model=model)
    v=np.array(output['meshes'][0]['vertices'])
    assert v[0,2]==pytest.approx(v[1,2])==pytest.approx(v[2,2])
    assert v[3,2]>v[0,2]
    assert v[0,2]==pytest.approx(.962)
    assert output['meshes'][0]['triangles']==[[0,1,2],[1,3,2]]


@pytest.mark.parametrize('field,value',[
    ('vertices',((float('nan'),0,0),(1,0,0),(0,0,1))),
    ('triangles',((0,1,9),)),('texcoords',((0,0),)),
])
def test_invalid_geometry_is_blocked_before_blender(tmp_path,field,value):
    g=Geometry();setattr(g,field,value)
    with pytest.raises(ValueError):export_pegboard([g],{'body':Image.new('RGBA',(1,1),'red')},lambda _:'body',{},tmp_path)


@pytest.mark.parametrize('failure',[None,'identity','version','timeout','process','dimensions'])
def test_isolated_blender_boundary(tmp_path,monkeypatch,failure):
    import sys,subprocess
    from types import ModuleType,SimpleNamespace
    from allin1 import pegboard_blender_renderer as r
    module=ModuleType('allin1_sdk.compiled_render')
    module.detect_blender=lambda _:SimpleNamespace(version='3.6' if failure=='version' else '4.5')
    monkeypatch.setitem(sys.modules,'allin1_sdk.compiled_render',module)
    exe=tmp_path/'blender.exe';exe.write_bytes(b'fixture executable')
    calls=[];stopped=[]
    class Process:
        def wait(self,timeout):
            assert timeout==150
            if failure=='timeout':raise subprocess.TimeoutExpired('blender',timeout)
            Image.new('RGB',(1,1) if failure=='dimensions' else (1280,800)).save(tmp_path/'blender/render.png')
            return 1 if failure=='process' else 0
    def start(args,**kwargs):calls.append(args);return Process()
    monkeypatch.setattr(r.subprocess,'Popen',start)
    monkeypatch.setattr(r,'stop_worker',lambda p:stopped.append(p))
    job=dict(project=str(tmp_path),blender_executable=str(exe),blender_identity='bad' if failure=='identity' else r.identity(exe))
    def run():return r.render_pegboard([Geometry()],{'body':Image.new('RGBA',(1,1),'red')},lambda _:'body',job=job,work=tmp_path)
    if failure:
        with pytest.raises((ValueError,subprocess.TimeoutExpired)):run()
    else: assert run().size==(512,320)
    if failure in ('identity','version'):assert not calls
    else:
        assert len(stopped)==1 and calls[0][0]==str(exe)
        assert '--disable-autoexec' in calls[0] and '--factory-startup' in calls[0]
