"""Preview authority, cache and failure isolation; never starts GTA."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image
from allin1 import prelaunch_previews as p


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    game, project, cache = tmp_path/'game', tmp_path/'project', tmp_path/'cache'
    game.mkdir(); project.mkdir()
    (game/'GTA5_Enhanced.exe').touch()
    archive = 'mods/update/x64/dlcpacks/test_pack/dlc.rpf'
    catalog = 'scripts/ALLIN1/Catalogs/test/weapons.json'
    p.atomic(game/archive, b'fixture-rpf')
    p.atomic(game/catalog, json.dumps({'schema_version':1,'id':'test-weapons','name':'Test',
        'weapons':[{'weapon':'WEAPON_TEST','name':'Test weapon','category':'rifles','price':10,
                    'ammo_cost_per_round':1,'source_pack':'test_pack'}]}).encode())
    receipt = {'schema_version':2,'id':'test-pack','enabled':True,'dlc_packs':['test_pack'],
        'files':[{'destination':name,'sha256':p.sha(game/name)} for name in [archive,catalog]],
        'extension':{'gbay':{'catalogs':[{'id':'test-weapons','kind':'weapon','source':catalog}]}}}
    receipt_path = game/'scripts/.allin1/mods/test.json'
    p.atomic(receipt_path, json.dumps(receipt).encode())
    buffer = io.BytesIO(); Image.new('RGB',(512,320),'green').save(buffer,format='PNG')
    data, calls = buffer.getvalue(), []
    monkeypatch.setattr(p,'mounted_packs',lambda *_:{'test_pack'})
    monkeypatch.setattr(p,'worker_command',lambda *_:(['fake-worker'],'renderer-1'))
    def render(command,job,work,seconds):
        calls.append(job)
        assert job['weapon']=='WEAPON_TEST' and seconds<=40
        return data
    monkeypatch.setattr(p,'render',render)
    return SimpleNamespace(game=game,project=project,cache=cache,archive=archive,catalog=catalog,
        receipt=receipt,receipt_path=receipt_path,data=data,calls=calls,
        run=lambda **kw:p.prepare(project,game,cache,**kw))


def index(f): return p.document(f.game/p.PUBLIC/'index.json')['images']


def test_render_then_reuse_without_worker(fixture):
    f=fixture
    assert f.run()['rendered']==1
    assert f.run()['cached']==1 and len(f.calls)==1
    assert list(index(f))==['weapon_test']
    assert p.sha(f.game/f.archive)==f.receipt['files'][0]['sha256']


def test_both_game_editions_reuse_their_cache_without_cross_publication(fixture):
    f = fixture
    legacy = f.game.parent/'Legacy game'
    shutil.copytree(f.game, legacy)
    (legacy/'GTA5_Enhanced.exe').unlink()
    (legacy/'GTA5.exe').touch()
    enhanced_result = f.run()
    legacy_result = p.prepare(f.project, legacy, f.cache)
    assert enhanced_result['edition'] == 'Enhanced' and legacy_result['edition'] == 'Legacy'
    assert enhanced_result['rendered'] == legacy_result['rendered'] == 1
    assert enhanced_result['weapons'][0]['cache_key'] != legacy_result['weapons'][0]['cache_key']
    enhanced_index = (f.game/p.PUBLIC/'index.json').read_bytes()
    legacy_index = (legacy/p.PUBLIC/'index.json').read_bytes()
    assert enhanced_index != legacy_index
    assert f.run(skip=True)['cached'] == 1
    assert p.prepare(f.project, legacy, f.cache, skip=True)['cached'] == 1
    assert len(f.calls) == 2  # No renderer launched on either warm run.
    assert (f.game/p.PUBLIC/'index.json').read_bytes() == enhanced_index
    assert (legacy/p.PUBLIC/'index.json').read_bytes() == legacy_index


def test_preview_progress_counts_completed_entries_not_render_start():
    updates = []
    queue = p.preview_queue([{'weapon':'ONE'}, {'weapon':'TWO'}], lambda *row: updates.append(row))
    assert next(queue)['weapon'] == 'ONE'
    assert updates[-1][0] == 0 and '0/2 processed' in updates[-1][1]
    assert next(queue)['weapon'] == 'TWO'
    assert updates[-1][0] == 50
    assert list(queue) == [] and updates[-1][0] == 100


def test_skipped_previews_are_processed_not_claimed_as_rendered(fixture):
    updates = []
    report = fixture.run(skip=True, progress=lambda *row: updates.append(row))
    assert report['rendered'] == 0 and report['pending'] == 1
    assert [p for p, _ in updates if p is not None] == [0, 100]
    assert '0 generated, 0 cached, 1 pending' in updates[-1][1]


@pytest.mark.parametrize('reason',['disabled','unmounted','modified','catalog-modified','ambiguous'])
def test_ineligible_packages_never_render_and_stale_index_is_removed(fixture,monkeypatch,reason):
    f=fixture; f.run(); f.calls.clear()
    if reason=='disabled':
        f.receipt['enabled']=False
        p.atomic(f.receipt_path,json.dumps(f.receipt).encode())
    elif reason=='unmounted': monkeypatch.setattr(p,'mounted_packs',lambda *_:set())
    elif reason=='modified': p.atomic(f.game/f.archive,b'changed')
    elif reason=='catalog-modified': p.atomic(f.game/f.catalog,b'{}')
    else: p.atomic(f.receipt_path.with_name('duplicate.json'),json.dumps(f.receipt).encode())
    f.run()
    assert not f.calls and not index(f)


@pytest.mark.parametrize('change',['archive','renderer','edition','corrupt-image','corrupt-metadata'])
def test_cache_invalidation(fixture,monkeypatch,change):
    f=fixture; first=f.run(); key=first['weapons'][0]['cache_key']
    if change=='archive':
        p.atomic(f.game/f.archive,b'new validated version')
        f.receipt['files'][0]['sha256']=p.sha(f.game/f.archive)
        p.atomic(f.receipt_path,json.dumps(f.receipt).encode())
    elif change=='renderer':monkeypatch.setattr(p,'worker_command',lambda *_:(['fake-worker'],'renderer-2'))
    elif change=='edition':(f.game/'GTA5_Enhanced.exe').unlink()
    else:
        path=next(f.cache.rglob(key+('.png' if change=='corrupt-image' else '.json')))
        p.atomic(path,b'corrupt')
    assert f.run()['rendered']==1 and len(f.calls)==2


def test_skip_and_budget_do_not_infer_or_launch(fixture):
    f=fixture
    assert f.run(skip=True)['pending']==1
    assert f.run(budget=0)['pending']==1
    assert not f.calls
    f.run()
    assert f.run(skip=True)['cached']==1


def test_render_failure_is_reported_and_retryable(fixture,monkeypatch):
    def fail(*_):raise TimeoutError('time budget')
    monkeypatch.setattr(p,'render',fail)
    result=fixture.run()
    assert result['status']=='unavailable' and result['pending']==1
    assert not index(fixture)
    assert result['errors'][0]['reason']=='time budget'


def test_source_changed_during_render_is_not_published(fixture,monkeypatch):
    f=fixture
    def change(*_):p.atomic(f.game/f.archive,b'changed');return f.data
    monkeypatch.setattr(p,'render',change)
    result=f.run()
    assert not index(f) and result['pending']==1


@pytest.mark.parametrize('path',['../outside','C:/outside','scripts/../bad','scripts//bad','scripts/NUL','/absolute','scripts\\bad'])
def test_portable_paths_fail_closed(tmp_path,path):
    with pytest.raises(ValueError):p.contained(tmp_path,path)


@pytest.mark.parametrize('content',[b'not-json',b'{"owner":"someone-else"}'])
def test_unowned_index_is_not_overwritten(fixture,content):
    path=fixture.game/p.PUBLIC/'index.json';p.atomic(path,content)
    assert fixture.run()['status']=='unavailable'
    assert path.read_bytes()==content and not fixture.calls


def test_malformed_receipt_does_not_crash_phase(fixture):
    p.atomic(fixture.receipt_path,b'[]')
    assert fixture.run()['status']=='unavailable'
    assert not fixture.calls


def test_invalid_png_rejected():
    with pytest.raises(ValueError):p.png(b'')
    buffer=io.BytesIO();Image.new('RGB',(1,1)).save(buffer,format='PNG')
    with pytest.raises(ValueError):p.png(buffer.getvalue())


def test_cache_lock_prevents_parallel_publication(fixture):
    f=fixture;f.cache.mkdir()
    lock=f.cache/(hashlib.sha256(str(f.game.resolve()).casefold().encode()).hexdigest()+'.lock')
    lock.touch()
    assert 'already active' in f.run()['errors'][0]['reason'] and not f.calls


def test_worker_timeout_terminates_process_tree(tmp_path,monkeypatch):
    events=[]
    clock=[0.0]
    class Process:
        pid=12345
        alive=True
        def wait(self,timeout):
            events.append('wait')
            if self.alive:
                clock[0]+=timeout
                raise subprocess.TimeoutExpired('worker',timeout)
            return 0
        def poll(self):return None if self.alive else 1
        def kill(self):
            events.append('kill')
            self.alive=False
    monkeypatch.setattr(p.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(p.subprocess,'Popen',lambda *a,**k:Process())
    monkeypatch.setattr(p.subprocess,'run',lambda args,**kw:events.append(args))
    with pytest.raises(TimeoutError):p.render(['worker'],{},tmp_path,1)
    if p.os.name=='nt':assert any(isinstance(e,list) and e[0].endswith('taskkill.exe') and e[1:]==['/PID','12345','/T','/F'] for e in events)
    assert 'kill' in events


def test_cancel_preserves_previous_index_and_complete_cache_releases_lock(fixture, monkeypatch):
    from allin1.launch_cancellation import LaunchCancellation, LaunchCancelled, checkpoint
    f = fixture
    f.run()
    previous = (f.game/p.PUBLIC/'index.json').read_bytes()
    cache = {str(path):path.read_bytes() for path in f.cache.rglob('*') if path.is_file()}
    monkeypatch.setattr(p,'worker_command',lambda *_:(['fake-worker'],'renderer-next'))
    control = LaunchCancellation()
    def cancel_render(*args):
        control.request({'review_id':'one'})
        checkpoint()
    monkeypatch.setattr(p,'render',cancel_render)
    with control.preparing('one'), pytest.raises(LaunchCancelled): f.run()
    assert (f.game/p.PUBLIC/'index.json').read_bytes() == previous
    assert {str(path):path.read_bytes() for path in f.cache.rglob('*') if path.is_file()} == cache
    assert not list(f.cache.rglob('*.lock')) and not list(f.cache.rglob('render-*'))


@pytest.mark.parametrize('phase', ['render', 'discover'])
def test_cancellation_reaps_owned_live_preview_process(tmp_path, monkeypatch, phase):
    import sys
    import threading
    import time
    from allin1.launch_cancellation import LaunchCancellation, LaunchCancelled
    from allin1 import stock_weapon_previews
    spawned = threading.Event()
    control = LaunchCancellation()
    processes = []
    original = p.subprocess.Popen
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        # Do not confuse the cleanup taskkill process with the owned worker.
        if args[0][0] == sys.executable:
            processes.append(process)
            spawned.set()
        return process
    monkeypatch.setattr(p.subprocess,'Popen',launch)
    monkeypatch.setattr(stock_weapon_previews,'catalog_names',lambda *_:['WEAPON_TEST'])
    def cancel():
        if spawned.wait(timeout=5): control.request({'review_id':'one'})
    worker = threading.Thread(target=cancel)
    command = [sys.executable,'-c','import time; time.sleep(30)']
    start = time.monotonic()
    with control.preparing('one'):
        worker.start()
        try:
            with pytest.raises(LaunchCancelled):
                if phase == 'render': p.render(command, {}, tmp_path, 20)
                else: p.stock_items(command,tmp_path,tmp_path,tmp_path,[],lambda *_:None)
            assert len(processes) == 1 and processes[0].poll() is not None
        finally:
            worker.join(timeout=5)
            for process in processes:
                if process.poll() is None: process.kill(); process.wait(timeout=5)
    assert len(processes) == 1 and processes[0].poll() is not None
    assert time.monotonic() - start < 10


def test_cache_capacity_evicts_only_intact_unprotected_pairs(fixture,monkeypatch):
    f=fixture;first=f.run();key=first['weapons'][0]['cache_key']
    cache=next(f.cache.rglob(key+'.png')).parent
    monkeypatch.setattr(p,'MAX_CACHE_IMAGES',1)
    with pytest.raises(ValueError,match='full'):p.reserve_cache_slot(cache,{key})
    p.reserve_cache_slot(cache,set())
    assert not (cache/(key+'.png')).exists()


def test_disabling_package_prunes_only_unmodified_published_cache(fixture):
    f=fixture;f.run();old=next(iter(index(f).values()))
    f.receipt['enabled']=False;p.atomic(f.receipt_path,json.dumps(f.receipt).encode())
    f.run()
    assert not (f.game/p.PUBLIC/old).exists()
    assert list(f.cache.rglob('*.png'))  # Original cache copy is recoverable.


def test_release_requires_bundled_renderer(tmp_path):
    from tests.test_release import _release_tree
    from allin1.release import collect_public_files
    root=_release_tree(tmp_path)
    (root/'tools/WeaponPreview/WeaponPreview.exe').unlink()
    with pytest.raises(FileNotFoundError,match='WeaponPreview'):collect_public_files(root)
