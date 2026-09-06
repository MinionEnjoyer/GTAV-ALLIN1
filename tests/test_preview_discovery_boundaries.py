"""Portable preview discovery and worker-launch boundaries with synthetic data."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from allin1 import prelaunch_previews as p, stock_weapon_previews as s


@pytest.fixture
def discovery(tmp_path,monkeypatch):
    project,game,cache=(tmp_path/n for n in ('project','game','cache'))
    for path in (project,game,cache):path.mkdir()
    for name in ('RpfPatcher.exe','RpfPatcher.dll','CodeWalker.Core.dll'):
        p.atomic(project/'tools/RpfPatcher'/name,b'helper')
    p.atomic(project/'data/weapons.toml',b'catalog')
    monkeypatch.setattr(s,'catalog_names',lambda _:['WEAPON_TEST','WEAPON_MISSING'])
    monkeypatch.setattr(s,'archives',lambda *_:[game/'stock.rpf',game/'override.rpf',game/'broken.rpf'])
    def ref(name,archive):return {'name':name,'archive':archive,'state':'stable','archive_path':'','path':name}
    stock={'identity':{'archive':'stock.rpf'},'definitions':{'WEAPON_TEST':{'model':'gun','components':[
        {'name':'CLIP','parent_bone':'mount'},{'name':'DATA','parent_bone':'mount'}]}},
        'components':{'CLIP':{'model':'clip','child_bone':'mount'},'DATA':{'model':'','child_bone':''}},
        'archetypes':{},'assets':[ref(n,'stock.rpf') for n in ('gun.ydr','gun.ytd','clip.ydr')]}
    override={'identity':{'archive':'override.rpf'},'definitions':{},'components':{},'archetypes':{},'assets':[ref('gun.ydr','override.rpf')]}
    def inventory(project,game,archive,*args):
        if archive.name=='broken.rpf':raise ValueError('Invalid archive')
        return stock if archive.name=='stock.rpf' else override
    monkeypatch.setattr(s,'inventory',inventory)
    return NS(project=project,game=game,cache=cache,stock=stock,override=override,
        run=lambda:s.discover(project,game,cache,[]))


def test_stock_discovery_prefers_override_and_completes_default_parts(discovery):
    result=discovery.run();assert len(result['items'])==1
    item=result['items'][0]
    assert item['assets'][0]['archive']=='override.rpf'
    assert item['components']==[{'name':'CLIP','parent_bone':'mount','model':'clip','child_bone':'mount','asset_index':2}]
    assert item['assets'][3]==item['assets'][1]  # Shared parent texture fallback.
    assert len(result['errors'])==2 and result['archives']==3


def test_stock_ambiguous_highest_priority_is_not_guessed(discovery):
    discovery.override['assets']*=2
    result=discovery.run();assert not result['items']
    assert any('ambiguous' in e['reason'] for e in result['errors'])


def test_stock_component_dictionary_selected_when_present(discovery):
    discovery.stock['assets'].append({**discovery.stock['assets'][-1],'name':'clip.ytd','path':'clip.ytd'})
    item=discovery.run()['items'][0]
    assert item['assets'][3]['path']=='clip.ytd'


def test_mount_discovery_preserves_valid_unique_order(tmp_path,monkeypatch):
    game=tmp_path/'game';project=tmp_path/'project'
    assert p.mounted_packs(project,game)==set()
    p.atomic(game/'mods/update/update.rpf',b'archive')
    def extract(args,**kwargs):
        Path(args[-1]).write_text('<Root><Item>dlcpacks:/ONE/</Item><Item>dlcpacks:/two/</Item><Item>dlcpacks:/one/</Item><Item>../invalid</Item><Item/></Root>')
    monkeypatch.setattr(p.subprocess,'run',extract)
    assert p.mounted_packs(project,game)==['one','two']


def test_worker_selection_and_identity_changes(tmp_path,monkeypatch):
    project=tmp_path/'project';helper=project/'tools/RpfPatcher/helper.dll'
    p.atomic(helper,b'v1')
    bundled=project/'tools/WeaponPreview/WeaponPreview.exe';p.atomic(bundled,b'worker')
    command,identity=p.worker_command(project);assert command==[str(bundled)]
    helper.write_bytes(b'v2');assert p.worker_command(project)[1]!=identity
    bundled.unlink()
    monkeypatch.setattr(p.sys,'frozen',True,raising=False)
    with pytest.raises(FileNotFoundError):p.worker_command(project)
    monkeypatch.setattr(p.sys,'frozen',False)
    p.atomic(project.parent/'ALLIN1-SDK/src/allin1_sdk/native_assets.py',b'# build dependency')
    command,_=p.worker_command(project);assert command[-1]=='allin1.weapon_preview_worker'


@pytest.mark.parametrize('failure',['exit','timeout','wait_once'])
def test_render_subprocess_exit_timeout_and_poll(tmp_path,monkeypatch,failure):
    stopped=[];calls=[]
    def wait(**kwargs):
        calls.append(kwargs)
        if failure=='wait_once' and len(calls)==1:raise subprocess.TimeoutExpired('worker',.25)
        return 1
    process=NS(wait=wait)
    monkeypatch.setattr(p.subprocess,'Popen',lambda *args,**kwargs:process)
    monkeypatch.setattr(p,'stop_worker',lambda proc:stopped.append(proc))
    with pytest.raises((RuntimeError,TimeoutError)):
        p.render(['worker'],{},tmp_path,-1 if failure=='timeout' else 1)
    assert stopped==[process]


def test_owned_worker_cleanup_uses_only_its_pid(monkeypatch):
    alive=[True];commands=[];waits=[]
    process=NS(pid=234,poll=lambda:None if alive[0] else 0,kill=lambda:alive.__setitem__(0,False),wait=lambda **kwargs:waits.append(kwargs))
    monkeypatch.setattr(p.subprocess,'run',lambda args,**kwargs:commands.append(args))
    p.stop_worker(process)
    assert not alive[0] and waits
    if p.os.name=='nt':assert commands[0][-4:]==['/PID','234','/T','/F']
    commands.clear();p.stop_worker(process);assert not commands


@pytest.mark.parametrize('failure',[False,True])
def test_discovery_worker_result_or_failure_is_reaped(tmp_path,monkeypatch,failure):
    monkeypatch.setattr(s,'catalog_names',lambda _:['WEAPON_TEST'])
    stopped=[]
    def spawn(args,**kwargs):
        request=Path(args[-1]);assert json.loads(request.read_text())['operation']=='discover_stock'
        (request.parent/'discovery.json').write_text('{"items":[],"errors":[]}')
        return NS(wait=lambda **kwargs:1 if failure else 0)
    monkeypatch.setattr(p.subprocess,'Popen',spawn)
    monkeypatch.setattr(p,'stop_worker',lambda _:stopped.append(True))
    if failure:
        with pytest.raises(RuntimeError):p.stock_items(['worker'],tmp_path,tmp_path,tmp_path,[],lambda *_:None)
    else:assert p.stock_items(['worker'],tmp_path,tmp_path,tmp_path,[],lambda *_:None)=={'items':[],'errors':[]}
    assert stopped==[True]
