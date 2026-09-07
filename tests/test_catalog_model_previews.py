import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from allin1 import prelaunch_previews as p
from allin1 import catalog_model_previews as m
from allin1.catalog_model_renderer import select_geometries


@pytest.fixture
def setup(tmp_path,monkeypatch):
    from allin1 import preview_blender
    executable=tmp_path/'blender.exe';executable.write_bytes(b'fixture')
    monkeypatch.setattr(preview_blender,'select_blender',lambda *_:executable)
    game=tmp_path/'game';game.mkdir();(game/'GTA5_Enhanced.exe').touch()
    project=tmp_path/'project';project.mkdir();cache=tmp_path/'cache'
    p.atomic(project/'data/vehicles.toml',b'[[vehicles]]\nmodel="kuruma"\n')
    p.atomic(project/'prices_gear.toml',b'[protection]\nARMOR_LIGHT=1000\n')
    p.atomic(game/'x64e.rpf',b'archive')
    from allin1.stock_weapon_previews import file_state
    ref=dict(archive='x64e.rpf',state=file_state(game/'x64e.rpf'),archive_path='vehicles.rpf',path='kuruma.yft')
    monkeypatch.setattr(p,'mounted_packs',lambda *_:[])
    monkeypatch.setattr(p,'worker_command',lambda *_:(['worker'],'identity'))
    calls=[]
    def discover(*args,category='weapons',**kw):
        name='kuruma' if category=='vehicles' else 'ARMOR_LIGHT'
        return dict(items=[dict(weapon=name,category=category,kind='stock',assets=[ref])],errors=[])
    monkeypatch.setattr(p,'stock_items',discover)
    buf=io.BytesIO();Image.new('RGB',(512,320),'green').save(buf,format='PNG')
    def render(*args):calls.append(args[1]);return buf.getvalue()
    monkeypatch.setattr(p,'render',render)
    return SimpleNamespace(game=game,project=project,cache=cache,calls=calls,
        run=lambda **kw:p.prepare_all(project,game,cache,**kw))


def test_categories_generate_then_reuse_and_keep_progress_monotonic(setup):
    f=setup;updates=[]
    first=f.run(progress=lambda n,s:updates.append(n))
    assert first['rendered']==2
    assert {j['category'] for j in f.calls}=={'gear','vehicles'}
    for category,name in [('vehicles','kuruma'),('gear','armor_light')]:
        index=p.document(f.game/f'plugins/ReactorV/ui/assets/allin1/generated-{category}/index.json')
        assert list(index['images'])==[name]
    assert f.run(skip=True)['cached']==2 and len(f.calls)==2
    values=[n for n in updates if n is not None]
    assert values==sorted(values)


def test_vehicle_uses_exact_blender_and_identity_changes_invalidate_cache(setup,tmp_path):
    first=setup.run()
    vehicle=next(j for j in setup.calls if j['category']=='vehicles')
    assert Path(vehicle['blender_executable'])==tmp_path/'blender.exe'
    assert len(vehicle['blender_identity'])==64
    assert first['categories']['vehicles']['render_workers'] in (1,2)
    (tmp_path/'blender.exe').write_bytes(b'changed')
    before=len(setup.calls);setup.run()
    assert len(setup.calls)==before+2  # Gear and vehicles both use Blender now.
    assert {job['category'] for job in setup.calls[before:]}=={'vehicles','gear'}


def test_models_isolate_editions_and_reject_modified_archive(setup):
    f=setup;f.run()
    (f.game/'GTA5_Enhanced.exe').unlink();(f.game/'GTA5.exe').touch()
    assert f.run()['rendered']==2
    p.atomic(f.game/'x64e.rpf',b'changed')
    assert f.run(skip=True)['status']=='partial'
    for c in ('vehicles','gear'):
        assert p.document(f.game/f'plugins/ReactorV/ui/assets/allin1/generated-{c}/index.json')['images']=={}


def test_uncached_skip_never_renders(setup):
    assert setup.run(skip=True)['pending']==2
    assert not setup.calls


@pytest.mark.parametrize('category', ['weapons', 'vehicles', 'gear'])
def test_selected_category_skip_is_isolated(tmp_path, monkeypatch, category):
    calls = []
    def prepare(*args, **kwargs):
        calls.append((kwargs['category'], kwargs['skip']))
        return dict(status='complete')
    monkeypatch.setattr(p, '_prepare', prepare)
    p.prepare_all(tmp_path, tmp_path, tmp_path/'cache', skip_categories=[category])
    assert calls == [(c, c == category) for c in ('weapons', 'vehicles', 'gear')]


def test_selected_skip_reuses_cache_without_rendering_skipped_category(setup):
    f = setup
    assert f.run(skip_categories=['vehicles'])['rendered'] == 1
    assert [job['category'] for job in f.calls] == ['gear']
    assert f.run(skip_categories=['gear'])['rendered'] == 1
    assert f.run(skip_categories=['vehicles', 'gear'])['cached'] == 2
    assert len(f.calls) == 2


def test_invalid_category_fails_before_cache_write(tmp_path):
    with pytest.raises(ValueError, match='skip_preview_categories'):
        p.prepare_all(tmp_path, tmp_path, tmp_path/'cache', skip_categories=['bad'])
    assert not (tmp_path/'cache').exists()


def test_vehicle_and_gear_failures_are_independent(setup,monkeypatch):
    def render(command,job,*args):
        if job['category']=='vehicles':raise ValueError('Missing wheels')
        out=io.BytesIO();Image.new('RGB',(512,320),'blue').save(out,format='PNG');return out.getvalue()
    monkeypatch.setattr(p,'render',render)
    r=setup.run()
    assert r['categories']['vehicles']['pending']==1
    assert r['categories']['gear']['rendered']==1


def test_unknown_category_is_rejected(setup):
    with pytest.raises(ValueError):p.prepare(setup.project,setup.game,setup.cache,category='../escape')


def test_receipt_vehicles_require_enabled_mounted_intact_and_unique(tmp_path):
    game=tmp_path
    archive='mods/update/x64/dlcpacks/testcar/dlc.rpf';catalog='scripts/Test/vehicles.json'
    p.atomic(game/archive,b'rpf')
    p.atomic(game/catalog,json.dumps(dict(schema_version=1,id='test-cars',name='Test',vehicles=[dict(
        model='testcar',name='Test',manufacturer='Test',category='sports',price=1,storage='garage',source_pack='testcar')])).encode())
    receipt=dict(id='test',enabled=True,dlc_packs=['testcar'],files=[dict(destination=n,sha256=p.sha(game/n)) for n in (archive,catalog)],
        extension=dict(gbay=dict(catalogs=[dict(id='test-cars',kind='vehicle',source=catalog)])))
    path=game/'scripts/.allin1/mods/test.json';p.atomic(path,json.dumps(receipt).encode())
    assert len(m.validated_vehicles(game,['testcar'])[0])==1
    assert not m.validated_vehicles(game,[])[0]
    receipt['enabled']=False;p.atomic(path,json.dumps(receipt).encode())
    assert not m.validated_vehicles(game,['testcar'])[0]
    receipt['enabled']=True;p.atomic(path,json.dumps(receipt).encode())
    p.atomic(path.with_name('duplicate.json'),json.dumps(receipt).encode())
    assert not m.validated_vehicles(game,['testcar'])[0]
    path.with_name('duplicate.json').unlink()
    p.atomic(game/archive,b'tampered')
    assert not m.validated_vehicles(game,['testcar'])[0]


def test_fragment_components_use_one_lod_each_including_wheels():
    rows=[SimpleNamespace(component=c,lod=l) for c,l in (
        ('body','High'),('body','Low'),('wheel_lf','Medium'),('wheel_lf','Low'),('wheel_rf','Medium'))]
    assert select_geometries(SimpleNamespace(geometries=rows))==[rows[0],rows[2],rows[4]]


def test_sdk_lod_prefixes_do_not_superimpose_vehicle_body():
    rows=[SimpleNamespace(component=c,lod=l) for c,l in (
        ('High drawable 1','High'),('Medium drawable 1','Medium'),('Low drawable 1','Low'),
        ('wheel_lf','Medium'),('wheel_lf','Low'))]
    assert select_geometries(SimpleNamespace(geometries=rows))==[rows[0],rows[3]]


def test_tiny_remote_helper_is_removed_but_real_separate_parts_remain():
    from dataclasses import dataclass
    from allin1.catalog_model_renderer import strip_remote_helpers
    @dataclass
    class Geometry:
        vertices:tuple
        triangles:tuple
        texcoords:tuple
    body=tuple((x/10,y/10,2.) for y in range(11) for x in range(11))
    triangles=tuple((y*11+x,y*11+x+1,(y+1)*11+x) for y in range(10) for x in range(10))
    vertices=body+((20.,0.,0.),(20.001,0.,0.),(20.,.001,0.))
    g=Geometry(vertices,triangles+((121,122,123),),((0,0),)*len(vertices))
    clean=strip_remote_helpers([g])[0]
    assert len(clean.triangles)==len(triangles)
    assert max(v[0] for v in clean.vertices)<=1
    large=Geometry(body+((20.,0.,0.),(21.,0.,0.),(20.,1.,0.)),g.triangles,g.texcoords)
    assert strip_remote_helpers([large])[0] is large


def test_catalog_deduplicates_story_vehicles_and_rejects_paths(tmp_path):
    p.atomic(tmp_path/'data/vehicles.toml',b'[[vehicles]]\nmodel="kuruma"\n')
    p.atomic(tmp_path/'data/story_vehicles.json',b'{"vehicles":[{"model":"kuruma"},{"model":"adder"}]}')
    assert m.catalog_names(tmp_path,'vehicles')==['adder','kuruma']
    p.atomic(tmp_path/'data/story_vehicles.json',b'{"vehicles":[{"model":"../escape"}]}')
    with pytest.raises(ValueError):m.catalog_names(tmp_path,'vehicles')


def test_no_placeholder_for_wearable_without_drawable():
    assert 'ARMOR_JUGGERNAUT' not in m.GEAR_MODELS


def test_shared_wheels_fill_only_missing_same_side_bones():
    from dataclasses import dataclass
    from allin1.catalog_model_renderer import complete_shared_wheels
    @dataclass
    class Geometry:
        component:str
        vertices:tuple
    def bone(name,index,position):
        return SimpleNamespace(name=name,index=index,parent_index=-1,rotation=(0,0,0,1),
            scale=(1,1,1),local_position=position,position=position)
    scene=SimpleNamespace(bones=[bone('wheel_lf',0,(-1,2,0)),bone('wheel_lr',1,(-1,-2,0)),
        bone('wheel_rf',2,(1,2,0)),bone('wheel_rr',3,(1,-2,0))])
    front=Geometry('wheel_lf',((-1,2,0),(-1,2,1),(-1,3,0)))
    rear=Geometry('wheel_rr',((1,-2,0),(1,-2,1),(1,-1,0)))
    result=complete_shared_wheels(scene,[front,rear])
    assert len(result)==4 and result[:2]==[front,rear]
    assert {g.component:g.vertices[0] for g in result}=={
        'wheel_lf':(-1,2,0),'wheel_lr':(-1,-2,0),'wheel_rf':(1,2,0),'wheel_rr':(1,-2,0)}


def test_discovery_inherits_textures_and_blocks_cycles(tmp_path,monkeypatch):
    project=tmp_path/'project';game=tmp_path/'game';cache=tmp_path/'cache'
    p.atomic(project/'data/vehicles.toml',b'[[vehicles]]\nmodel="adder"\n')
    for n in ('RpfPatcher.exe','RpfPatcher.dll','CodeWalker.Core.dll'):p.atomic(project/'tools/RpfPatcher'/n,b'helper')
    p.atomic(game/'x64e.rpf',b'archive')
    monkeypatch.setattr(m,'archives',lambda *_:[game/'x64e.rpf'])
    record=dict(identity=dict(archive='x64e.rpf'),archetypes={'adder':'adder'},parents={'adder':'interior'},assets=[
        dict(name=n,archive='x64e.rpf',path=n) for n in ('adder.yft','adder.ytd','interior.ytd','vehshare.ytd')])
    monkeypatch.setattr(m,'inventory',lambda *a,**kw:record)
    result=m.discover(project,game,cache,[],'vehicles')
    assert [r['path'] for r in result['items'][0]['assets']]==['adder.yft','adder.ytd','interior.ytd','vehshare.ytd']
    record['assets'].extend(dict(name=n,archive='x64e.rpf',path=n) for n in ('adder_hi.yft','adder+hi.ytd'))
    result=m.discover(project,game,cache,[],'vehicles')
    assert [r['path'] for r in result['items'][0]['assets']][:4]==['adder.yft','adder_hi.yft','adder+hi.ytd','adder.ytd']
    record['parents']['interior']='adder'
    assert not m.discover(project,game,cache,[],'vehicles')['items']
    record['parents'].clear();record['assets'].append(record['assets'][0])
    assert 'ambiguous' in m.discover(project,game,cache,[],'vehicles')['errors'][0]['reason']


def test_duplicate_patch_texture_uses_unique_model_companion(tmp_path,monkeypatch):
    project=tmp_path/'project';game=tmp_path/'game'
    p.atomic(project/'data/vehicles.toml',b'[[vehicles]]\nmodel="buffalo3"\n')
    for n in ('RpfPatcher.exe','RpfPatcher.dll','CodeWalker.Core.dll'):
        p.atomic(project/'tools/RpfPatcher'/n,b'helper')
    p.atomic(game/'patch.rpf',b'archive')
    monkeypatch.setattr(m,'archives',lambda *_:[game/'patch.rpf'])
    def ref(name,folder):return dict(name=name,path=name,archive='patch.rpf',archive_path=folder)
    record=dict(identity=dict(archive='patch.rpf'),archetypes={},parents={},assets=[
        ref('buffalo3.yft','vehicles.rpf'),ref('buffalo3.ytd','vehicles.rpf'),
        ref('buffalo3.ytd','txd_patches.rpf')])
    monkeypatch.setattr(m,'inventory',lambda *a,**kw:record)
    result=m.discover(project,game,tmp_path/'cache',[],'vehicles')
    assert result['items'][0]['assets'][1]['archive_path']=='vehicles.rpf'
    record['assets'].append(ref('buffalo3.ytd','vehicles.rpf'))
    assert not m.discover(project,game,tmp_path/'cache',[],'vehicles')['items']


def test_all_categories_share_the_same_publication_lock(setup,monkeypatch):
    attempts=[]
    original=p._prepare
    def within_lock(*args,**kwargs):
        attempts.append(setup.run())
        return original(*args,**kwargs)
    monkeypatch.setattr(p,'_prepare',within_lock)
    setup.run()
    assert len(attempts)==3
    assert all(r['status']=='unavailable' and 'already active' in r['errors'][0]['reason'] for r in attempts)


def test_desktop_routes_every_category():
    from allin1.desktop_service import LauncherService
    import inspect
    assert 'prepare_all' in inspect.getsource(LauncherService.prepare_previews)


def test_default_queue_does_not_starve_later_categories(setup,monkeypatch):
    budgets=[]
    original=p._prepare
    def record(*args,**kwargs):
        budgets.append(kwargs['budget'])
        return original(*args,**kwargs)
    monkeypatch.setattr(p,'_prepare',record)
    result=setup.run()
    assert budgets==[None,None,None]
    assert result['categories']['gear']['rendered']==1


def test_parked_rotors_remove_only_blur_materials():
    from allin1.catalog_model_renderer import parked_rotors
    from allin1.vehicle_catalog import vehicle_model_hash
    names=['vehicle_blurredrotor','vehicle_blurredrotor_emissive.sps',
           f'hash_{vehicle_model_hash("vehicle_blurredrotor"):08X}',
           'vehicle_mesh','vehicle_paint1','vehicle_decal']
    rows=[SimpleNamespace(material_name=n) for n in names]
    assert parked_rotors(rows)==rows[3:]
