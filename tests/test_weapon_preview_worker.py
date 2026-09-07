"""Offline worker contracts using synthetic archives; no game or SDK install."""
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import numpy as np
import pytest
from PIL import Image
from lxml import etree as E
from allin1 import weapon_preview_worker as w, stock_weapon_previews as s


@dataclass(frozen=True)
class Geometry:
    vertices: tuple = ((0.,0.,0.), (1.,0.,0.), (0.,0.,1.))
    triangles: tuple = ((0,1,2),)
    texcoords: tuple = ((0.,0.),(1.,0.),(0.,1.))
    material_index: int = 0
    lod: str = 'high'


DRAWABLE = '''<Drawable><ShaderGroup><Shaders><Item><FileName>weapon.sps</FileName>
<RenderBucket value="0"/><Parameters><Item name="DiffuseSampler" type="Texture"><Name>diffuse</Name></Item>
</Parameters></Item></Shaders></ShaderGroup><VertexBuffer><Layout><Position/><Colour0/></Layout>
<Data>0 0 0 255 255 255 255\n1 0 0 255 255 255 255\n0 0 1 255 255 255 255</Data></VertexBuffer>
<Skeleton><Bones><Item><Name>mount</Name><ParentIndex value="-1"/>
<Translation x="0" y="0" z="0"/></Item></Bones></Skeleton></Drawable>'''


@pytest.fixture
def worker(tmp_path, monkeypatch):
    from allin1 import pegboard_blender_renderer
    monkeypatch.setattr(pegboard_blender_renderer,'render_pegboard',
        lambda gs,ts,diffuse,**kw:w.render_card(gs,ts,diffuse,materials=kw.get('materials'),flat=kw.get('flat',False)))
    native, rpf = ModuleType('allin1_sdk.native_assets'), ModuleType('allin1_sdk.rpf_tools')
    package = ModuleType('allin1_sdk'); package.__path__ = []
    for name, module in [('allin1_sdk',package),('allin1_sdk.native_assets',native),('allin1_sdk.rpf_tools',rpf)]:
        monkeypatch.setitem(sys.modules,name,module)
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    native._model_scene_from_xml = lambda *_: (NS(geometries=[Geometry()],lods=['high']),None,'')
    native._model_diffuse_texture_name = lambda _: 'diffuse'
    native._model_trs_matrix = lambda _: np.eye(4)
    def export(path, dest, **kwargs):
        dest.mkdir(parents=True)
        (dest/'drawable.xml').write_text(DRAWABLE)
        (dest/'native-workspace.json').write_text(json.dumps({'xml':{'path':'drawable.xml'}}))
        Image.new('RGBA',(8,8),'green').save(dest/'diffuse.dds')
        return dest
    native.NativeAssetInspector = lambda *_: NS(export_workspace=export)
    blobs = {
        'weapons.meta': b'<Root><Item type="CWeaponInfo"><Name>WEAPON_TEST</Name><Model>gun</Model></Item></Root>',
        'weaponarchetypes.meta': b'<Root><Item><modelName>gun</modelName><txdName>gun</txdName></Item></Root>',
        'gun.ydr': b'drawable', 'gun.ytd': b'textures',
    }
    def entries():
        return [NS(name=n,path=n,archive_path='',kind='resource',size=len(v),suffix=Path(n).suffix) for n,v in blobs.items()]
    def extract(index, entry, dest):
        dest.write_bytes(blobs[entry.name]); return dest
    service = NS(index=lambda _:NS(edition='Enhanced',entries=entries()),extract=extract,patcher='synthetic-helper')
    rpf.RpfExplorerService = lambda *_: service
    project,game,work = (tmp_path/name for name in ('project','game','work'))
    for p in (project,game,work):p.mkdir()
    (game/'pack.rpf').write_bytes(b'archive')
    job = dict(project=str(project),game=str(game),edition='Enhanced',weapon='WEAPON_TEST',archive='pack.rpf',archive_sha256=w.sha(game/'pack.rpf'))
    request = work/'job.json'
    def run(**changes):
        request.write_text(json.dumps({**job,**changes})); w.main(request)
    return NS(native=native,blobs=blobs,service=service,job=job,run=run,work=work,game=game,project=project)


def test_addon_worker_renders_without_game_or_gui(worker):
    worker.run()
    with Image.open(worker.work/'preview.png') as image:assert image.size==(512,320)


def test_addon_default_attachment_is_assembled(worker,monkeypatch):
    worker.blobs['weapons.meta'] = b'''<Root><Item type="CWeaponInfo"><Name>WEAPON_TEST</Name><Model>gun</Model>
    <AttachPoints><Item><AttachBone>mount</AttachBone><Components><Item><Name>CLIP</Name><Default value="true"/>
    </Item></Components></Item></AttachPoints></Item></Root>'''
    worker.blobs['weaponcomponents.meta'] = b'<Root><Item><Name>CLIP</Name><Model>clip</Model><AttachBone>mount</AttachBone></Item></Root>'
    worker.blobs['clip.ydr'] = b'clip'
    def batch(args,**kwargs):
        output=Path(args[-1]);output.mkdir()
        (output/'0.meta').write_bytes(worker.blobs['weaponcomponents.meta'])
    monkeypatch.setattr(w.subprocess,'run',batch)
    worker.run()
    assert (worker.work/'part0').is_dir()
    assert (worker.work/'preview.png').is_file()


@pytest.mark.parametrize('model,create',[('reload_only','false'),('gun','true')])
def test_addon_omits_reload_only_and_duplicate_base_drawables(worker,monkeypatch,model,create):
    worker.blobs['weapons.meta'] = b'''<Root><Item type="CWeaponInfo"><Name>WEAPON_TEST</Name><Model>gun</Model>
    <AttachPoints><Item><AttachBone>mount</AttachBone><Components><Item><Name>CLIP</Name><Default value="true"/>
    </Item></Components></Item></AttachPoints></Item></Root>'''
    worker.blobs['weaponcomponents.meta'] = f'<Root><Item><Name>CLIP</Name><Model>{model}</Model><CreateObject value="{create}"/></Item></Root>'.encode()
    def batch(args,**kwargs):
        output=Path(args[-1]);output.mkdir()
        (output/'0.meta').write_bytes(worker.blobs['weaponcomponents.meta'])
    monkeypatch.setattr(w.subprocess,'run',batch)
    worker.run()
    assert not (worker.work/'part0').exists()
    assert (worker.work/'preview.png').is_file()


@pytest.mark.parametrize('changes,match',[
    ({'edition':'wrong'},'edition'),({'weapon':'../escape'},'weapon'),
    ({'archive_sha256':'0'*64},'Source changed'),({'weapon':'WEAPON_MISSING'},'definition'),
])
def test_worker_rejects_untrusted_job_before_publication(worker,changes,match):
    with pytest.raises(ValueError,match=match):worker.run(**changes)
    assert not (worker.work/'preview.png').exists()


def test_worker_rejects_changed_archive_after_render(worker,monkeypatch):
    def render(*args,**kwargs):
        (worker.game/'pack.rpf').write_bytes(b'changed')
        return Image.new('RGB',(512,320))
    monkeypatch.setattr(w,'render_assets',render)
    with pytest.raises(ValueError,match='during rendering'):worker.run()
    assert not (worker.work/'preview.png').exists()


@pytest.mark.parametrize('failure',['edition','ambiguous','missing','large','dictionary'])
def test_worker_archive_resolution_fails_closed(worker,failure):
    original=worker.service.index
    if failure=='dictionary':worker.blobs['weaponarchetypes.meta']=b'<Root/>'
    def index(source):
        value=original(source)
        if failure=='edition':value.edition='Legacy'
        if failure=='ambiguous':value.entries.append(value.entries[0])
        if failure=='missing':value.entries=value.entries[1:]
        if failure=='large':value.entries[0].size=129*1024*1024
        return value
    worker.service.index=index
    with pytest.raises(ValueError):worker.run()
    assert not (worker.work/'preview.png').exists()


def test_stock_discovery_writes_only_discovery_result(worker,monkeypatch):
    monkeypatch.setattr(s,'discover',lambda *args,**kwargs:{'items':[],'errors':[]})
    worker.run(operation='discover_stock',mounted=[],discovery_cache=str(worker.work/'cache'))
    assert json.loads((worker.work/'discovery.json').read_text())=={'items':[],'errors':[]}
    assert not (worker.work/'preview.png').exists()


@pytest.fixture
def stock(worker,monkeypatch):
    monkeypatch.setattr(s,'catalog_names',lambda _:['WEAPON_TEST'])
    monkeypatch.setattr(s,'throwable_names',lambda _:set())
    monkeypatch.setattr(s,'extract',lambda project,game,ref,dest:dest)
    monkeypatch.setattr(s,'file_state',lambda _: 'stable')
    worker.job.update(kind='stock',model='gun',assets=[{'path':'gun.ydr','archive':'pack.rpf','state':'stable'},
        {'path':'gun.ytd','archive':'pack.rpf','state':'stable'}])
    return worker


def test_stock_render_uses_verified_asset_identity(stock):
    stock.run();assert (stock.work/'preview.png').exists()


def test_stock_throwable_routes_to_crate_from_catalog_not_request(stock,monkeypatch):
    monkeypatch.setattr(s,'throwable_names',lambda _:{'WEAPON_TEST'})
    seen=[]
    monkeypatch.setattr(w,'render_assets',lambda *a,**kw:seen.append(kw['job']['preview_backdrop']) or Image.new('RGB',(512,320)))
    stock.run(preview_backdrop='pegboard')
    assert seen==['ammo-crate']


def test_addon_throwable_routes_from_verified_metadata(worker,monkeypatch):
    worker.blobs['weapons.meta']=b'<Root><Item type="CWeaponInfo"><Name>WEAPON_TEST</Name><Model>gun</Model><Group>GROUP_THROWN</Group></Item></Root>'
    seen=[]
    monkeypatch.setattr(w,'render_assets',lambda *a,**kw:seen.append(kw['job']['preview_backdrop']) or Image.new('RGB',(512,320)))
    worker.run(preview_backdrop='pegboard')
    assert seen==['ammo-crate']


@pytest.mark.parametrize('failure',['weapon','count','model','component','changed'])
def test_stock_rejects_invalid_assemblies(stock,failure,monkeypatch):
    if failure=='weapon':stock.job['weapon']='WEAPON_NO'
    if failure=='count':stock.job['assets']=[]
    if failure=='model':stock.job['model']='different'
    if failure=='component':
        stock.job['assets']*=2
        stock.job['components']=[{'asset_index':9,'model':'clip'}]
    if failure=='changed':monkeypatch.setattr(s,'file_state',lambda _:'changed')
    with pytest.raises(ValueError):stock.run()
    assert not (stock.work/'preview.png').exists()


@pytest.mark.parametrize('mode',['plain','alpha','vertex','embedded'])
def test_decode_materials_and_high_lod(worker,mode):
    path=worker.work/'drawable.xml';root=E.fromstring(DRAWABLE)
    if mode in ('alpha','vertex'):
        p=E.SubElement(root.find('.//Parameters'),'Item',name='TextureSamplerDiffPal' if mode=='alpha' else 'TintPaletteSampler',type='Texture')
        E.SubElement(p,'Name').text='palette'
        Image.new('RGBA',(8,8),'white').save(worker.work/'palette.dds')
    path.write_bytes(E.tostring(root))
    Image.new('RGBA',(8,8),'green').save(worker.work/'diffuse.dds')
    gs,ts,ms,_=w.decode_card(path,worker.work,'gun')
    assert len(gs)==1 and 'diffuse' in ts
    if mode=='vertex':assert len(ms[id(gs[0])]['vertex_colours'])==3
    if mode=='alpha':assert ms[id(gs[0])]['palette_mode']=='alpha'


@pytest.mark.parametrize('failure',['scene','buffers','shader','layout','colour','textures','lod'])
def test_decode_rejects_incomplete_or_ambiguous_art(worker,failure):
    path=worker.work/'drawable.xml';root=E.fromstring(DRAWABLE)
    if failure=='scene':worker.native._model_scene_from_xml=lambda *_:(None,None,'invalid')
    if failure=='buffers':root.remove(root.find('VertexBuffer'))
    if failure=='shader':root.find('ShaderGroup/Shaders').clear()
    if failure in ('layout','colour'):
        p=E.SubElement(root.find('.//Parameters'),'Item',name='TintPaletteSampler',type='Texture');E.SubElement(p,'Name').text='palette'
        if failure=='layout':E.SubElement(root.find('.//Layout'),'Unsupported')
        else:root.find('.//Layout').remove(root.find('.//Colour0'))
    if failure=='lod':worker.native._model_scene_from_xml=lambda *_:(NS(geometries=[Geometry()],lods=['low']),None,'')
    path.write_bytes(E.tostring(root))
    if failure!='textures':Image.new('RGBA',(8,8),'green').save(worker.work/'diffuse.dds')
    with pytest.raises(ValueError):w.decode_card(path,worker.work,'gun')


@pytest.mark.parametrize('bucket,opaque', [('0',True),('1',False),('2',False),('3',False)])
def test_weapon_alpha_policy_uses_render_bucket(worker,bucket,opaque):
    path=worker.work/'drawable.xml';root=E.fromstring(DRAWABLE)
    shader=root.find('ShaderGroup/Shaders/Item')
    node=shader.find('RenderBucket')
    if node is None:node=E.SubElement(shader,'RenderBucket')
    node.set('value',bucket);path.write_bytes(E.tostring(root))
    Image.new('RGBA',(8,8),(50,60,70,0)).save(worker.work/'diffuse.dds')
    gs,_,ms,_=w.decode_card(path,worker.work,'gun')
    assert ms[id(gs[0])]['opaque'] is opaque
