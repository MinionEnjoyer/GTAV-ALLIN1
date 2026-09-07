"""Exercise worker orchestration with native decoding/processes isolated.

These tests verify ownership, assembly and publication, not Blender visual quality.
"""
import json
from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from allin1 import catalog_model_renderer as renderer
from allin1 import vehicle_blender_renderer as blender


@dataclass(frozen=True)
class Geometry:
    component: str = 'body'
    lod: str = 'High'
    material_name: str = 'default'
    texture_names: tuple = ('body',)
    texture_parameters: tuple = (('DiffuseSampler', 'body'),)
    vertices: tuple = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))
    triangles: tuple = ((0, 1, 2),)
    texcoords: tuple = ((0., 0.), (1., 0.), (0., 1.))


@dataclass(frozen=True)
class Scene:
    geometries: tuple = (Geometry(),)
    bones: tuple = ()


@pytest.fixture
def worker(tmp_path, monkeypatch):
    from allin1_sdk import native_assets
    game = tmp_path / 'game'; game.mkdir()
    (game / 'stock.rpf').write_bytes(b'archive')
    work = tmp_path / 'work'; work.mkdir()
    calls = []
    def export(path, destination, **kwargs):
        destination.mkdir()
        (destination / 'native-workspace.json').write_text(json.dumps({'xml': {'path': 'model.xml'}}))
        (destination / 'model.xml').write_text('<model/>')
        Image.new('RGBA', (4, 4), 'red').save(destination / 'body.dds')
        return destination
    monkeypatch.setattr(native_assets, 'NativeAssetInspector', lambda *_: NS(export_workspace=export))
    monkeypatch.setattr(native_assets, 'load_native_model_scene', lambda *a, **kw: (Scene(), None, None))
    monkeypatch.setattr(native_assets, '_model_diffuse_texture_name', lambda g: dict(g.texture_parameters).get('DiffuseSampler'))
    monkeypatch.setattr(renderer, 'catalog_names', lambda *a: {'car', 'armor_light'})
    monkeypatch.setattr(renderer, 'GEAR_MODELS', {'armor_light': ('vest',)})
    monkeypatch.setattr(renderer, 'extract', lambda p, g, r, out: out)
    monkeypatch.setattr(renderer, 'file_state', lambda p: 'state')
    def render(*a, **kw):
        calls.append((a, kw)); return Image.new('RGB', (512, 320), 'red')
    monkeypatch.setattr(blender, 'render_vehicle', render)
    from allin1 import pegboard_blender_renderer
    monkeypatch.setattr(pegboard_blender_renderer, 'render_pegboard', render)
    job = dict(project=str(tmp_path), game=str(game), category='vehicles', weapon='car',
               model='car', edition='Enhanced', assets=[dict(path='car.yft', archive='stock.rpf', state='state')])
    return NS(job=job, work=work, calls=calls, native=native_assets, game=game)


@pytest.mark.parametrize('high', [False, True])
def test_vehicle_assembly_publishes_png_and_prefers_high_body(worker, high):
    if high:
        worker.job['assets'].append(dict(path='car_hi.yft', archive='stock.rpf', state='state'))
    renderer.render_job(worker.job, worker.work)
    with Image.open(worker.work / 'preview.png') as image: assert image.size == (512, 320)
    assert len(worker.calls) == 1
    assert len(worker.calls[0][0][1]) == 1  # Never double the base and high body.


def test_gear_uses_textured_pegboard(worker):
    worker.job.update(category='gear', weapon='armor_light', model='vest')
    worker.job['assets'][0]['path'] = 'vest.ydr'
    renderer.render_job(worker.job, worker.work)
    assert worker.calls[0][1]['category'] == 'gear'
    assert worker.calls[0][0][1]['body'].getpixel((0, 0)) == (255, 0, 0, 255)
    assert (worker.work / 'preview.png').exists()


@pytest.mark.parametrize('field,value,message', [
    ('model', '../bad', 'identity'), ('edition', 'other', 'edition'),
    ('weapon', 'unknown', 'Unknown catalog'), ('model', 'other', 'mismatch'),
    ('assets', [], 'assembly'),
])
def test_invalid_jobs_fail_before_decode(worker, field, value, message):
    worker.job[field] = value
    with pytest.raises(ValueError, match=message): renderer.render_job(worker.job, worker.work)
    assert not worker.calls and not (worker.work / 'decoded0').exists()


@pytest.mark.parametrize('failure', ['source', 'empty', 'decode', 'high-decode', 'texture-ref', 'gear-model', 'missing-texture'])
def test_worker_failures_never_publish_partial_png(worker, monkeypatch, failure):
    if failure == 'source': monkeypatch.setattr(renderer, 'file_state', lambda _: 'changed')
    if failure == 'empty': monkeypatch.setattr(worker.native, 'load_native_model_scene', lambda *a, **k: (Scene(()), None, None))
    if failure == 'decode': monkeypatch.setattr(worker.native, 'load_native_model_scene', lambda *a, **k: (None, None, 'invalid'))
    if failure == 'high-decode':
        worker.job['assets'].append(dict(path='car_hi.yft', archive='stock.rpf', state='state'))
        monkeypatch.setattr(worker.native, 'load_native_model_scene', lambda *a, **k: (None if k['name'].endswith('_hi') else Scene(), None, 'invalid'))
    if failure == 'texture-ref': worker.job['assets'].append(dict(path='unsafe.exe', archive='stock.rpf', state='state'))
    if failure in ('gear-model', 'missing-texture'):
        worker.job.update(category='gear', weapon='armor_light', model='vest' if failure == 'missing-texture' else 'wrong')
        worker.job['assets'][0]['path'] = 'vest.ydr'
        monkeypatch.setattr(worker.native, '_model_diffuse_texture_name', lambda _: 'missing')
    with pytest.raises(ValueError): renderer.render_job(worker.job, worker.work)
    assert not (worker.work / 'preview.png').exists()


@pytest.mark.parametrize('failure', [None, 'authority', 'base-owner', 'hi-owner', 'hash'])
def test_managed_vehicle_requires_unchanged_receipt_authority(worker, monkeypatch, failure):
    from allin1 import catalog_model_previews, prelaunch_previews
    authority = dict(weapon='car', archive='stock.rpf', archive_sha256=renderer.sha(worker.game / 'stock.rpf'))
    worker.job['authority'] = authority
    monkeypatch.setattr(prelaunch_previews, 'mounted_packs', lambda *a: [])
    monkeypatch.setattr(catalog_model_previews, 'validated_vehicles', lambda *a: ([] if failure == 'authority' else [authority], []))
    if failure == 'base-owner': worker.job['assets'][0]['archive'] = 'other.rpf'
    if failure == 'hi-owner': worker.job['assets'].append(dict(path='car_hi.yft', archive='other.rpf', state='state'))
    if failure == 'hash': authority['archive_sha256'] = '0' * 64
    if failure:
        with pytest.raises(ValueError): renderer.render_job(worker.job, worker.work)
        assert not (worker.work / 'preview.png').exists()
    else: renderer.render_job(worker.job, worker.work)


@pytest.fixture
def blender_job(tmp_path, monkeypatch):
    from allin1_sdk import compiled_render
    executable = tmp_path / 'blender.exe'; executable.write_bytes(b'blender')
    work = tmp_path / 'work'; work.mkdir()
    texture = tmp_path / 'floor.png'; Image.new('RGB', (4, 4)).save(texture)
    decoded = tmp_path / 'decoded'; decoded.mkdir()
    Image.new('RGBA', (4, 4), 'blue').save(decoded / 'body.dds')
    Image.new('RGBA', (4, 4)).save(decoded / 'unused.dds')
    monkeypatch.setattr(blender, 'VEHICLE_TEXTURES', ['floor.png'])
    monkeypatch.setattr(blender, 'select_blender', lambda _: executable)
    monkeypatch.setattr(blender, 'identity', lambda _: 'fingerprint')
    monkeypatch.setattr(compiled_render, 'detect_blender', lambda _: NS(version='4.5.0'))
    def export(scene, target, **kw):
        (target / 'scene.obj').write_text('usemtl body\n')
        (target / 'scene.json').write_text(json.dumps({'materials': [dict(key='body', source_name='default', semantic='opaque', texture_bindings=[])]}))
        assert kw['texture_assets']['body'].exists() and 'unused' not in kw['texture_assets']
        return NS(manifest_path=target / 'scene.json', obj_path=target / 'scene.obj')
    monkeypatch.setattr(compiled_render, 'export_render_interchange', export)
    calls = []; stopped = []
    def start(command, **kwargs):
        calls.append(command)
        Image.new('RGB', (1280, 800), 'blue').save(work / 'blender/render.png')
        return NS(wait=lambda **kw: 0)
    monkeypatch.setattr(blender.subprocess, 'Popen', start)
    monkeypatch.setattr(blender, 'stop_worker', stopped.append)
    job = dict(project=str(tmp_path), model='car', blender_identity='fingerprint', render_threads=2)
    return NS(job=job, work=work, decoded=decoded, compiled=compiled_render, calls=calls, stopped=stopped)


def test_blender_outputs_resized_card_and_binds_safe_process_flags(blender_job):
    f = blender_job
    image = blender.render_vehicle(Scene(), [Geometry()], [f.decoded], f.job, f.work)
    assert image.size == (512, 320) and image.getpixel((0, 0)) == (0, 0, 255)
    assert '--disable-autoexec' in f.calls[0] and '--factory-startup' in f.calls[0]
    assert len(f.stopped) == 1
    data = json.loads((f.work / 'blender/scene.json').read_text())
    assert data['preview_scene'] == 'studio' and data['meshes'][0]['uv_layers']['UV0'][0] == [0., 1.]


@pytest.mark.parametrize('failure', ['identity', 'version-check', 'old-version', 'exit', 'timeout', 'changed', 'dimensions'])
def test_blender_rejects_invalid_runtime_or_output_and_cleans_worker(blender_job, monkeypatch, failure):
    import subprocess
    f = blender_job
    if failure == 'identity': f.job['blender_identity'] = 'changed'
    if failure in ('version-check', 'old-version'):
        monkeypatch.setattr(f.compiled, 'detect_blender', lambda _: None if failure == 'version-check' else NS(version='3.6.0'))
    if failure == 'changed':
        sequence = iter(['fingerprint', 'changed']); monkeypatch.setattr(blender, 'identity', lambda _: next(sequence))
    if failure in ('exit', 'timeout', 'dimensions'):
        def start(command, **kwargs):
            Image.new('RGB', (10, 10)).save(f.work / 'blender/render.png')
            def wait(**kw):
                if failure == 'timeout': raise subprocess.TimeoutExpired(command, kw['timeout'])
                return 9 if failure == 'exit' else 0
            return NS(wait=wait)
        monkeypatch.setattr(blender.subprocess, 'Popen', start)
    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        blender.render_vehicle(Scene(), [Geometry()], [f.decoded], f.job, f.work)
    assert len(f.stopped) == (0 if failure in ('identity', 'version-check', 'old-version') else 1)


@pytest.mark.parametrize('outcome', ['success', 'unavailable', 'error'])
def test_memory_probe_keeps_unknown_capacity_conservative(monkeypatch, outcome):
    import ctypes
    from allin1 import preview_render_pool as pool
    def status(pointer):
        if outcome == 'error': raise OSError('unavailable')
        pointer._obj.available = 12 * 2**30
        return int(outcome == 'success')
    monkeypatch.setattr(pool, 'os', NS(name='nt'))
    monkeypatch.setattr(ctypes, 'windll', NS(kernel32=NS(GlobalMemoryStatusEx=status)), raising=False)
    memory = pool.available_memory()
    assert memory == (12 * 2**30 if outcome == 'success' else None)
    assert pool.worker_limit(16, memory) == (4 if outcome == 'success' else 1)


def test_optional_vehicle_masks_with_missing_uv_are_reported_not_misaligned():
    manifest = dict(materials=[dict(key='body', source_name='vehicle_mesh', texture_bindings=[
        dict(path='mask.png', role=role, uv_map='UV1', name='vehicle_generic_detail2', slot=role)
        for role in ('diffuse', 'normal', 'specular')])], meshes=[dict(material='body', uv_layers={'UV0': []})])
    blender.validate_material_uvs(manifest)
    assert manifest['materials'][0]['texture_bindings'] == []
    assert len(manifest['material_warnings']) == 3
    with pytest.raises(ValueError, match='count mismatch'): blender.export_vehicle_meshes([Geometry()], [])


def test_slow_worker_emits_heartbeat_and_preserves_order():
    import time
    from allin1.preview_render_pool import ordered_results
    beats = []
    def run(value): time.sleep(.3); return value * 2
    with ordered_results([1, 2], run, 1, heartbeat=lambda: beats.append(True)) as rows:
        assert list(rows) == [(1, 2), (2, 4)]
    assert beats
