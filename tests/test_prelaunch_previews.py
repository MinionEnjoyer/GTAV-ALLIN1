"""Preview authority, cache and failure isolation; never starts GTA."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import os
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image
from allin1 import prelaunch_previews as p


def test_mounted_packs_accepts_stock_tag_case_preserving_order(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    archive = game / 'mods/update/update.rpf'
    archive.parent.mkdir(parents=True)
    archive.touch()
    def extract(command, **kwargs):
        Path(command[-1]).write_text('''<SMandatoryPacksData><Paths>
          <Item>dlcpacks:/first/</Item>
          <item>dlcpacks:/mpxmas_604490/</item>
          <Item>dlcpacks:/FIRST/</Item>
          <item>dlcpacks:/../</item>
          <Other>dlcpacks:/not_mounted/</Other>
        </Paths></SMandatoryPacksData>''', encoding='utf-8')
    monkeypatch.setattr(p.subprocess, 'run', extract)
    assert p.mounted_packs(tmp_path, game) == ['first', 'mpxmas_604490']


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    from allin1 import preview_blender
    executable=tmp_path/'blender.exe';executable.write_bytes(b'fixture-blender')
    monkeypatch.setattr(preview_blender,'select_blender',lambda *_:executable)
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
        assert job['weapon']=='WEAPON_TEST' and seconds<=180
        assert job['blender_executable']==str(executable) and job['blender_identity']==p.sha(executable)
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


def test_missing_only_keeps_old_renderer_images_without_blender(fixture, monkeypatch):
    from allin1 import preview_blender
    f = fixture
    f.run()
    original = index(f)
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['fake-worker'], 'renderer-2'))
    monkeypatch.setattr(preview_blender, 'select_blender', lambda *_: pytest.fail('No Blender needed for retained previews'))
    result = f.run(missing_only=True)
    assert result['cached'] == 1 and result['rendered'] == 0
    assert index(f) == original and len(f.calls) == 1
    assert result['pruned_images'] == 0


def test_missing_only_reuses_defaults_without_copying_or_rendering(fixture, monkeypatch):
    from allin1 import preview_blender
    f = fixture
    folder = f.game / p.PUBLIC.replace('generated-weapons', 'default-weapons')
    filename = 'weapon_test.' + 'a' * 64 + '.png'
    p.atomic(folder / filename, f.data)
    p.atomic(folder / 'index.json', json.dumps(dict(schema_version=1, owner='allin1.default-previews',
        images={'weapon_test': filename}, image_sha256={filename: hashlib.sha256(f.data).hexdigest()})).encode())
    monkeypatch.setattr(preview_blender, 'select_blender', lambda *_: pytest.fail('Defaults need no Blender'))
    result = f.run(missing_only=True)
    assert result['defaults_reused'] == 1 and result['rendered'] == 0
    assert not f.calls and index(f) == {}
    assert (folder / filename).read_bytes() == f.data


def test_missing_only_fills_missing_entry_and_default_still_refreshes(fixture, monkeypatch):
    f = fixture
    first = f.run(missing_only=True)
    assert first['rendered'] == 1
    original = index(f)
    (f.game/p.PUBLIC/original['weapon_test']).unlink()
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['fake-worker'], 'renderer-2'))
    assert f.run(missing_only=True)['rendered'] == 1
    assert index(f) != original
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['fake-worker'], 'renderer-3'))
    assert f.run()['rendered'] == 1


def test_missing_only_does_not_retain_unvalidated_source(fixture):
    f = fixture
    f.run()
    p.atomic(f.game/f.archive, b'tampered')
    assert f.run(missing_only=True)['rendered'] == 0
    assert not index(f) and len(f.calls) == 1


def test_missing_only_mixed_catalog_keeps_existing_and_renders_new(fixture, monkeypatch):
    f = fixture
    f.run()
    original = index(f)['weapon_test']
    discover = p.validated_weapons
    def expanded(*args, **kwargs):
        items, errors = discover(*args, **kwargs)
        return [*items, {**items[0], 'weapon': 'WEAPON_NEW'}], errors
    monkeypatch.setattr(p, 'validated_weapons', expanded)
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['fake-worker'], 'renderer-2'))
    calls = []
    monkeypatch.setattr(p, 'render', lambda command, job, work, seconds: calls.append(job['weapon']) or f.data)
    result = f.run(missing_only=True)
    assert result['rendered'] == 1 and result['cached'] == 1
    assert calls == ['WEAPON_NEW']
    assert index(f)['weapon_test'] == original and 'weapon_new' in index(f)


def test_existing_preview_rejects_modified_pixels_and_path_traversal(fixture):
    f = fixture
    f.run()
    public = f.game/p.PUBLIC
    doc = p.document(public/'index.json')
    assert p.existing_preview(public, doc['images'], doc['image_sha256'], 'weapon_test')
    p.atomic(public/doc['images']['weapon_test'], b'corrupt')
    assert p.existing_preview(public, doc['images'], doc['image_sha256'], 'weapon_test') is None
    assert p.existing_preview(public, {'weapon_test': '../outside.png'}, {}, 'weapon_test') is None


def set_managed_catalog(f, names):
    catalog = p.document(f.game/f.catalog)
    template = catalog['weapons'][0]
    catalog['weapons'] = [{**template, 'weapon': name, 'name': name} for name in names]
    p.atomic(f.game/f.catalog, json.dumps(catalog).encode())
    f.receipt['files'][1]['sha256'] = p.sha(f.game/f.catalog)
    p.atomic(f.receipt_path, json.dumps(f.receipt).encode())


def test_full_stock_plus_addon_catalog_crosses_128_and_only_renders_missing(fixture, monkeypatch):
    from allin1 import stock_weapon_previews
    f = fixture
    stock_names = [f'WEAPON_STOCK_{i}' for i in range(111)]
    managed = [f'WEAPON_ADDON_{i}' for i in range(16)]
    missing = ['WEAPON_A1_EQ_M249', 'WEAPON_A1_EQ_LVOAC']
    set_managed_catalog(f, managed + missing)
    monkeypatch.setattr(stock_weapon_previews, 'catalog_names', lambda *_: stock_names)
    monkeypatch.setattr(p, 'stock_items', lambda *_: {
        'items': [{'weapon': name, 'kind': 'stock', 'assets': []} for name in stock_names], 'errors': []})
    old = {name.lower(): name.lower()+'.'+hashlib.sha256(name.encode()).hexdigest()+'.png'
           for name in stock_names + managed}
    public = f.game/p.PUBLIC
    for filename in old.values(): p.atomic(public/filename, f.data)
    p.atomic(public/'index.json', json.dumps({'schema_version': 1, 'owner': 'allin1.prelaunch-previews',
        'images': old, 'image_sha256': {name: hashlib.sha256(f.data).hexdigest() for name in old.values()}}).encode())
    calls = []
    monkeypatch.setattr(p, 'render', lambda command, job, work, seconds: calls.append(job['weapon']) or f.data)
    result = f.run(missing_only=True)
    assert result['status'] == 'complete' and not result['errors']
    assert result['rendered'] == 2 and result['cached'] == 127 and result['pending'] == 0
    assert sorted(calls) == sorted(missing)
    after = index(f)
    assert len(after) == 129 and all(after[name] == filename for name, filename in old.items())
    assert all((public/filename).read_bytes() == f.data for filename in old.values())
    assert result['pruned_images'] == 0
    calls.clear()
    again = f.run(missing_only=True)  # A publication larger than 128 must be readable on the next run too.
    assert again['cached'] == 129 and not calls and index(f) == after


def test_managed_weapon_limit_remains_separate_from_combined_catalog(fixture):
    f = fixture
    set_managed_catalog(f, [f'WEAPON_ADDON_{i}' for i in range(p.MAX_MANAGED_WEAPONS + 1)])
    with pytest.raises(ValueError, match='Managed weapon preview count 129 exceeds limit 128'):
        p.validated_weapons(f.game, {'test_pack'})


def test_total_queue_limit_preserves_previous_publication(fixture, monkeypatch):
    from allin1 import stock_weapon_previews
    f = fixture
    f.run()
    old = (f.game/p.PUBLIC/'index.json').read_bytes()
    monkeypatch.setattr(p, 'MAX_WEAPONS', 2)
    monkeypatch.setattr(stock_weapon_previews, 'catalog_names', lambda *_: ['WEAPON_A', 'WEAPON_B'])
    monkeypatch.setattr(p, 'stock_items', lambda *_: {
        'items': [{'weapon': n, 'kind': 'stock', 'assets': []} for n in ['WEAPON_A', 'WEAPON_B']], 'errors': []})
    monkeypatch.setattr(p, 'render', lambda *_: pytest.fail('Oversized queue must not render'))
    result = f.run()
    assert result['status'] == 'unavailable'
    assert '3 entries; preview queue limit is 2' in result['errors'][-1]['reason']
    assert (f.game/p.PUBLIC/'index.json').read_bytes() == old


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


def test_default_has_no_catalog_deadline_but_retains_per_model_timeout(fixture,monkeypatch):
    assert p.MAX_SECONDS is None
    clock=[0]
    def now():
        clock[0]+=3601
        return clock[0]
    monkeypatch.setattr(p.time,'monotonic',now)
    report=fixture.run()
    assert report['rendered']==1 and report['pending']==0
    assert fixture.calls[0]['render_threads']>=1


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


def test_cache_rejects_a_valid_image_with_a_replayed_cache_receipt(fixture):
    f = fixture
    cache = f.cache / 'replay'
    cache.mkdir(parents=True)
    first, second = 'a' * 64, 'b' * 64
    digest = hashlib.sha256(f.data).hexdigest()
    p.atomic(cache / (first + '.png'), f.data)
    # The data is valid, but the receipt belongs to a different source key.
    p.atomic(cache / (first + '.json'), json.dumps({'key': second,
        'sha256': digest}).encode())

    assert p.cached(cache, first) is None


@pytest.mark.skipif(os.name != 'nt', reason='Windows extended-path regression')
def test_atomic_publishes_a_generated_filename_beyond_legacy_windows_path_limit(tmp_path):
    folder = tmp_path
    # Keep the parent below MAX_PATH so this creates on legacy Windows; only
    # the generated filename pushes the final atomic destination past it.
    for segment in ('a' * 75, 'b' * 55):
        folder /= segment
        folder.mkdir()
    target = folder / ('weapon_test.' + 'c' * 64 + '.png')
    assert len(str(target.resolve())) > 260

    p.atomic(target, b'preview')

    from allin1.release_paths import filesystem_path
    assert filesystem_path(target).read_bytes() == b'preview'


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


@pytest.mark.parametrize('mode', ['skip', 'budget', 'failure'])
def test_refresh_without_replacement_keeps_finished_artwork(fixture, monkeypatch, mode):
    f = fixture
    f.run()
    original = index(f)
    image = f.game/p.PUBLIC/original['weapon_test']
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['worker'], 'new-renderer'))
    if mode == 'failure':
        def fail(*_): raise RuntimeError('render failed')
        monkeypatch.setattr(p, 'render', fail)
    result = f.run(**({'skip': True} if mode == 'skip' else {'budget': 0} if mode == 'budget' else {}))
    assert index(f) == original and image.read_bytes() == f.data
    assert result['rendered'] == 0 and result['cached'] == 1 and result['pruned_images'] == 0
    if mode != 'skip': assert result['pending'] == result['retained_pending'] == 1


def test_skip_keeps_existing_without_blender(fixture, monkeypatch):
    from allin1 import preview_blender
    f = fixture
    f.run()
    monkeypatch.setattr(preview_blender, 'select_blender', lambda *_: pytest.fail('Skipped previews need no Blender'))
    assert f.run(skip=True)['cached'] == 1


@pytest.mark.parametrize('phase', ['mounts', 'renderer', 'blender', 'publication'])
def test_preparation_exception_does_not_erase_previous_index(fixture, monkeypatch, phase):
    from allin1 import preview_blender
    f = fixture
    f.run()
    path = f.game/p.PUBLIC/'index.json'
    previous = path.read_bytes()
    def fail(*_): raise OSError('unavailable')
    if phase == 'mounts': monkeypatch.setattr(p, 'mounted_packs', fail)
    elif phase == 'renderer': monkeypatch.setattr(p, 'worker_command', fail)
    elif phase == 'blender': monkeypatch.setattr(preview_blender, 'select_blender', fail)
    else:
        original_atomic = p.atomic
        def fail_commit(target, data):
            if target == path: raise OSError('disk full')
            return original_atomic(target, data)
        monkeypatch.setattr(p, 'atomic', fail_commit)
    assert f.run()['status'] != 'complete'
    assert path.read_bytes() == previous
    assert (path.parent/next(iter(index(f).values()))).exists()


def test_refresh_records_recoverable_identity_and_previous_index(fixture, monkeypatch):
    f = fixture
    first = f.run()
    original = (f.game/p.PUBLIC/'index.json').read_bytes()
    key = first['weapons'][0]['cache_key']
    metadata = next(f.cache.rglob(key+'.json'))
    assert p.document(metadata)['model'] == 'WEAPON_TEST'
    assert p.document(metadata)['category'] == 'weapons'
    monkeypatch.setattr(p, 'worker_command', lambda *_: (['worker'], 'next-renderer'))
    assert f.run()['rendered'] == 1
    assert next(f.cache.rglob('previous-publication.json')).read_bytes() == original
    assert metadata.with_suffix('.png').exists()
