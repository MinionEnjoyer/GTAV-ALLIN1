"""Pre-launch stock and receipt-authorized add-on weapon artwork. Never starts GTA.

Only mounted DLCs from intact enabled managed packages enter the render queue.
The cache is disposable; preview failures never grant install or spawn authority.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from xml.etree import ElementTree as ET

from PIL import Image
from allin1.release_paths import no_links, strict_json, contained
from allin1.vehicle_catalog import vehicle_model_hash
from allin1.processes import hidden_process_options
from allin1.weapon_catalog import WeaponCatalog
from allin1.launch_cancellation import checkpoint

SCHEMA = 1
RENDER_VERSION = 'catalog-card-7-runway-static-rotors'
MAX_SECONDS = None  # Complete the queue unless explicitly cancelled or skipped.
MAX_WEAPONS = 128
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_CACHE_IMAGES = 4096
PUBLIC = 'plugins/ReactorV/ui/assets/allin1/generated-weapons'
NAME = re.compile(r'weapon_[a-z0-9_]{1,56}')
HASH = re.compile(r'[0-9a-f]{64}')

def sha(path):
    value = hashlib.sha256()
    with no_links(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            checkpoint()
            value.update(chunk)
    return value.hexdigest()

def document(path, limit=4 * 1024 * 1024):
    path = no_links(path)
    if path.stat().st_size > limit: raise ValueError('Preview document exceeds limit')
    return strict_json(path.read_bytes())

def atomic(path, data):
    path = no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try: os.replace(temporary, path)
    finally: temporary.unlink(missing_ok=True)

def png(data):
    if not 0 < len(data) <= MAX_IMAGE_BYTES: raise ValueError('Invalid preview image size')
    with Image.open(io.BytesIO(data)) as image:
        if image.format != 'PNG' or image.size != (512, 320): raise ValueError('Invalid preview image format')
        image.verify()
    return data

def validated_weapons(game, mounted, *, progress=lambda *_: None):
    """Whole-package validation precedes selecting any weapon from that package."""
    root = no_links(Path(game)/'scripts/.allin1/mods')
    result, rejected = [], []
    if not root.exists(): return result, rejected
    paths = sorted(root.glob('*.json'))
    if len(paths) > 256: raise ValueError('Managed package count exceeds preview limit')
    hashes = {}
    for path in paths:
        checkpoint()
        try:
            receipt = document(path)
            if receipt.get('enabled') is not True: continue
            declarations = (receipt.get('extension') or {}).get('gbay', {}).get('catalogs', [])
            if not any(d.get('kind')=='weapon' for d in declarations):continue
            records = receipt.get('files', [])
            if not isinstance(records, list) or len(records) > 8192: raise ValueError('Invalid receipt files')
            owned = {}
            for record in records:
                target = contained(game, record['destination'])
                expected = record['sha256']
                if not isinstance(expected, str) or not HASH.fullmatch(expected): raise ValueError('Missing receipt hash')
                if record['destination'] in owned: raise ValueError('Duplicate receipt destination')
                digest = hashes.setdefault(str(target), sha(target)) if str(target) not in hashes else hashes[str(target)]
                if digest != expected: raise ValueError('Managed payload hash mismatch: '+record['destination'])
                owned[record['destination']] = expected
            selected = []
            packs = receipt.get('dlc_packs', [])
            for declaration in declarations:
                if declaration.get('kind') != 'weapon': continue
                source = declaration['source']
                if source not in owned: raise ValueError('Weapon catalog is not receipt-owned')
                catalog = WeaponCatalog.load(contained(game, source))
                if catalog.catalog_id != declaration['id']: raise ValueError('Weapon catalog identity mismatch')
                catalog.validate_package_ownership(packs)
                for weapon in catalog.weapons:
                    if weapon.source_pack not in mounted: continue
                    relative = f'mods/update/x64/dlcpacks/{weapon.source_pack}/dlc.rpf'
                    if relative not in owned: raise ValueError('Weapon archive is not receipt-owned')
                    selected.append({'weapon':weapon.weapon, 'archive':relative,
                                     'archive_sha256':owned[relative], 'package':receipt['id'],
                                     'catalog_sha256':owned[source]})
            result.extend(selected)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            rejected.append({'receipt':path.name,'reason':str(error)})
    # Ambiguous declarations are not resolved by filesystem order.
    counts = {}
    for item in result:
        key = vehicle_model_hash(item['weapon'])
        counts[key] = counts.get(key, 0)+1
    ambiguous = {item['weapon'] for item in result if counts[vehicle_model_hash(item['weapon'])] != 1}
    for name in sorted(ambiguous): rejected.append({'weapon':name,'reason':'Ambiguous catalog ownership'})
    result = sorted((v for v in result if v['weapon'] not in ambiguous), key=lambda v:v['weapon'])
    if len(result)>MAX_WEAPONS: raise ValueError('Preview weapon count exceeds bounded queue')
    progress(None, f'Validated mod list: {len(result)} mounted add-on weapons; {len(rejected)} rejected entries')
    return result, rejected

def mounted_packs(project, game):
    helper = no_links(Path(project)/'tools/RpfPatcher/RpfPatcher.exe')
    archive = no_links(Path(game)/'mods/update/update.rpf')
    if not archive.exists(): return set()
    with tempfile.TemporaryDirectory(prefix='allin1-preview-mounts-') as temp:
        output = Path(temp)/'dlclist.xml'
        subprocess.run([str(helper),'extract-entry',str(game),str(archive),'dlclist.xml',str(output)],
                       check=True, capture_output=True, timeout=20, **hidden_process_options())
        if output.stat().st_size > 2*1024*1024: raise ValueError('DLC list exceeds limit')
        # Rockstar lists include both <Item> and <item> (notably Tampa's DLC).
        # Keep mount order and path validation; never infer mounts from folders.
        return list(dict.fromkeys(match.group(1).lower() for node in ET.parse(output).iter()
                if node.tag in {'Item', 'item'}
                and (match := re.fullmatch(r'dlcpacks:[/\\]([a-zA-Z0-9_-]+)[/\\]',(node.text or '').strip()))))

def worker_command(project):
    from allin1.preview_policy import STUDIO_BACKDROP, VEHICLE_TEXTURES, THROWABLE_TEXTURES
    backdrop_identity = sha(contained(project, STUDIO_BACKDROP))
    backdrop_identity += ''.join(sha(contained(project,name)) for name in VEHICLE_TEXTURES+THROWABLE_TEXTURES)
    bundled = no_links(Path(project)/'tools/WeaponPreview/WeaponPreview.exe')
    helper_folder = Path(project)/'tools/RpfPatcher'
    helper_identity = hashlib.sha256(''.join(path.name+sha(path) for path in sorted(helper_folder.iterdir())
        if path.is_file() and path.suffix.lower() in {'.exe','.dll','.xml','.json'}).encode()).hexdigest()
    if bundled.is_file(): return [str(bundled)], sha(bundled)+helper_identity+backdrop_identity
    # Development only. Published builds contain the isolated worker, not an SDK checkout dependency.
    sdk = Path(project).parent/'ALLIN1-SDK/src'
    if not getattr(sys,'frozen',False) and (sdk/'allin1_sdk/native_assets.py').is_file():
        identity = (sha(Path(__file__).with_name('weapon_preview_worker.py'))
                    + sha(Path(__file__).with_name('weapon_card_renderer.py'))
                    + sha(Path(__file__).with_name('stock_weapon_previews.py'))
                    + sha(Path(__file__).with_name('weapon_preview_assembly.py'))
                    + sha(Path(__file__).with_name('catalog_model_previews.py'))
                    + sha(Path(__file__).with_name('catalog_model_renderer.py'))
                    + sha(Path(__file__).with_name('vehicle_blender_renderer.py'))
                    + sha(Path(__file__).with_name('vehicle_blender_scene.py'))
                    + sha(Path(__file__).with_name('vehicle_preview_paint.py'))
                    + sha(Path(__file__).with_name('pegboard_blender_renderer.py'))
                    + sha(Path(__file__).with_name('pegboard_blender_scene.py'))
                    + sha(sdk/'allin1_sdk/compiled_render.py')
                    + sha(sdk/'allin1_sdk/native_assets.py'))
        return [sys.executable,'-m','allin1.weapon_preview_worker'], identity+helper_identity+backdrop_identity
    raise FileNotFoundError('Bundled weapon preview renderer unavailable; existing artwork retained')

def key_for(item, edition, renderer):
    return hashlib.sha256(json.dumps({**item,'edition':edition,'renderer':renderer,'version':RENDER_VERSION},sort_keys=True).encode()).hexdigest()

def cached(cache, key):
    try:
        metadata = document(cache/(key+'.json'))
        data = png(no_links(cache/(key+'.png')).read_bytes())
        if metadata['sha256'] != hashlib.sha256(data).hexdigest(): return None
        return data
    except (OSError, ValueError, KeyError): return None


def reserve_cache_slot(cache, protected):
    """Evict only intact cache-owned pairs, never unrelated/edited files."""
    images = [path for path in cache.glob('*.png') if HASH.fullmatch(path.stem)]
    while len(images) >= MAX_CACHE_IMAGES:
        candidates = sorted((path for path in images if path.stem not in protected), key=lambda path:path.stat().st_mtime)
        victim = next((path for path in candidates if cached(cache,path.stem) is not None),None)
        if victim is None: raise ValueError('Preview cache is full; existing images retained')
        no_links(victim).unlink()
        no_links(victim.with_suffix('.json')).unlink()
        images.remove(victim)

def render(command, job, work, seconds):
    checkpoint()
    request = work/'job.json'
    atomic(request, json.dumps(job).encode())
    output = work/'preview.png'
    # Worker stdout/stderr are files, not unbounded pipe buffers. Kill the whole
    # worker tree on timeout so CodeWalker cannot continue into gameplay.
    with (work/'worker.log').open('wb') as log:
        # The desktop host is concurrently reading its synchronous IPC pipe.
        # Inheriting that stdin can deadlock Windows/Python worker startup.
        environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        process = subprocess.Popen([*command,str(request)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                                   env=environment,**hidden_process_options())
        deadline = time.monotonic() + seconds
        try:
            while True:
                checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError('Preview time budget reached')
                try:
                    code = process.wait(timeout=min(.25, remaining))
                    break
                except subprocess.TimeoutExpired: pass
            checkpoint()
            if code:
                log.flush()
                detail = (work/'worker.log').read_bytes()[-2000:].decode('utf-8',errors='replace')
                raise RuntimeError('Preview renderer failed: '+detail)
        finally:
            stop_worker(process)
    return png(output.read_bytes())


def stop_worker(process):
    """Only the owned preview subprocess/tree, never GTA or the sidecar."""
    if process.poll() is not None: return
    try:
        if os.name == 'nt':
            subprocess.run([str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/taskkill.exe'),
                            '/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,**hidden_process_options())
    finally:
        if process.poll() is None: process.kill()
        process.wait(timeout=10)


def stock_items(command,project,game,cache,mounted,progress, *, category='weapons', managed=()):
    """Discover through the isolated worker; no SDK runtime in the launcher."""
    from allin1.stock_weapon_previews import catalog_names
    if category=='weapons' and not catalog_names(project):return {'items':[],'errors':[]}
    checkpoint()
    with tempfile.TemporaryDirectory(prefix='discovery-',dir=cache) as folder:
        work=Path(folder);request=work/'job.json'
        atomic(request,json.dumps({'operation':'discover_stock','project':str(project),'game':str(game),
            'category':category,'managed':list(managed),
            'mounted':list(mounted),'discovery_cache':str(cache/'stock-discovery')}).encode())
        with (work/'discovery.log').open('wb') as log:
            process=subprocess.Popen([*command,str(request)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden_process_options())
            deadline=time.monotonic()+600
            next_progress=time.monotonic()+5
            try:
                while True:
                    checkpoint()
                    try:
                        code=process.wait(timeout=.25)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= next_progress:
                            lines=(work/'discovery.log').read_bytes()[-4000:].decode('utf-8',errors='replace').splitlines()
                            progress(None,lines[-1] if lines else 'Discovering installed GBAY weapon models')
                            next_progress=time.monotonic()+5
                        if time.monotonic()>deadline:raise TimeoutError('Stock discovery time budget reached')
                if code:raise RuntimeError('Stock discovery failed: '+(work/'discovery.log').read_bytes()[-2000:].decode('utf-8',errors='replace'))
                return document(work/'discovery.json',16*1024*1024)
            finally:
                stop_worker(process)


def source_unchanged(game,item):
    from allin1.stock_weapon_previews import file_state
    for pair in item.get('stock_component_assets',{}).values():
        if any(file_state(contained(game,a['archive']))!=a['state'] for a in pair):return False
    if item.get('kind')=='stock':
        from allin1.stock_weapon_previews import file_state
        authority=item.get('authority')
        if authority and sha(contained(game,authority['archive']))!=authority['archive_sha256']:return False
        return all(file_state(contained(game,a['archive']))==a['state'] for a in item['assets'])
    return sha(contained(game,item['archive']))==item['archive_sha256']

def prepare(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS, category='weapons', skip_categories=(), missing_only=False):
    """Serialize per-game cache publication; no renderer survives this call."""
    from allin1.preview_policy import validate_skip_categories
    skip_categories = validate_skip_categories(list(skip_categories))
    checkpoint()
    root = no_links(Path(cache_root))
    root.mkdir(parents=True, exist_ok=True)
    lock = contained(root, hashlib.sha256(str(Path(game).resolve()).casefold().encode()).hexdigest()+'.lock')
    try:
        stream = lock.open('xb')
    except FileExistsError:
        return {'status':'unavailable','errors':[{'reason':'Preview preparation is already active (or a stale cache lock needs removal)'}]}
    try:
        with stream:
            if type(missing_only) is not bool: raise ValueError('missing_only must be a boolean')
            if category=='all':return _prepare_all(project,game,cache_root,skip=skip,progress=progress,budget=budget,skip_categories=skip_categories,missing_only=missing_only)
            return _prepare(project,game,cache_root,skip=skip or category in skip_categories,progress=progress,budget=budget,category=category,missing_only=missing_only)
    finally: lock.unlink(missing_ok=True)


def preview_queue(items, progress, category='weapons'):
    """Report completed queue entries, not elapsed time or assumed render success."""
    total = len(items)
    for index, item in enumerate(items):
        checkpoint()
        progress(int(100 * index / total),
                 f'{"Weapon" if category=="weapons" else category.title()} previews: {index}/{total} processed · Checking {item["weapon"]}')
        yield item
    if total:
        progress(100, f'{"Weapon" if category=="weapons" else category.title()} previews: {total}/{total} processed')


def prune_published(public, cache, published, pattern, previous_hashes=None):
    """Prune obsolete generated copies, including orphans from interrupted passes.

    Never infer ownership from a PNG extension alone. The generated filename
    and recorded content digest must agree; modified/user files remain intact.
    Cache copies are retained, so deleted public copies can be regenerated.
    """
    removed = 0
    previous_hashes = previous_hashes or {}
    keep = set(published.values())
    for path in no_links(public).glob('*.png'):
        if path.name in keep or not re.fullmatch(pattern.pattern+r'\.[a-f0-9]{64}\.png', path.name):
            continue
        try:
            checkpoint()
            path = contained(public, path.name)
            key = path.name.rsplit('.', 2)[1]
            expected = previous_hashes.get(path.name)
            if not isinstance(expected, str) or not HASH.fullmatch(expected):
                receipt = cache/(key+'.json')
                record = document(receipt) if receipt.exists() else {}
                expected = record.get('sha256') if record.get('key') == key else None
            if isinstance(expected, str) and HASH.fullmatch(expected) and sha(path) == expected:
                path.unlink()
                removed += 1
        except (OSError, ValueError):
            # Links, malformed receipts and user-modified files aren't ours.
            continue
    return removed


def existing_preview(public, images, hashes, name):
    """Keep an intact indexed generated image, regardless of renderer revision."""
    checkpoint()
    filename = images.get(name)
    if not isinstance(filename, str) or not re.fullmatch(re.escape(name)+r'\.[a-f0-9]{64}\.png', filename):
        return None
    expected = hashes.get(filename)
    if not isinstance(expected, str) or not HASH.fullmatch(expected): return None
    try:
        data = png(contained(public, filename).read_bytes())
        if hashlib.sha256(data).hexdigest() != expected: return None
        return filename.rsplit('.', 2)[1], data, 'cached', None
    except (OSError, ValueError):
        return None


def _prepare(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS, category='weapons', missing_only=False):
    """Optional artwork phase, after hazards and before Reactor/GTA startup."""
    started = time.monotonic()
    if category not in ('weapons','vehicles','gear'):raise ValueError('Invalid preview category')
    limit=MAX_WEAPONS if category=='weapons' else 2048
    pattern=NAME if category=='weapons' else re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
    game, project = no_links(game).resolve(), no_links(project).resolve()
    edition = 'Enhanced' if (game/'GTA5_Enhanced.exe').exists() else 'Legacy'
    cache = no_links(Path(cache_root)/hashlib.sha256(str(game).casefold().encode()).hexdigest()[:16])
    if category!='weapons':cache=no_links(cache/category)
    report = {'schema_version':SCHEMA,'status':'complete','edition':edition,'rendered':0,'cached':0,'pending':0,'errors':[],'weapons':[]}
    public = contained(game, PUBLIC if category=='weapons' else PUBLIC.replace('generated-weapons','generated-'+category))
    index_path = public/'index.json'
    try:
        # Do not take ownership of an unrelated file at our publication path.
        if index_path.exists() and document(index_path).get('owner') != 'allin1.prelaunch-previews':
            raise ValueError('Preview publication index is not ALLIN1-owned')
        old_images = document(index_path).get('images', {}) if index_path.exists() else {}
        old_hashes = document(index_path).get('image_sha256', {}) if index_path.exists() else {}
        if not isinstance(old_hashes, dict): old_hashes = {}
        if not isinstance(old_images, dict) or len(old_images)>limit:
            raise ValueError('Invalid previous preview index')
        mounted=mounted_packs(project,game)
        checkpoint()
        if category=='vehicles':
            from allin1.catalog_model_previews import validated_vehicles
            items,rejected=validated_vehicles(game,mounted,progress=progress)
        elif category=='gear':items,rejected=[],[]
        else:items, rejected = validated_weapons(game, mounted,progress=progress)
        report['errors'].extend(rejected)
        from allin1.stock_weapon_previews import catalog_names
        if category=='weapons':requested_stock=catalog_names(project)
        else:
            from allin1.catalog_model_previews import catalog_names as model_names
            requested_stock=model_names(project,category)
        command, renderer = worker_command(project) if items or requested_stock else ([], '')
        cache.mkdir(parents=True,exist_ok=True)
        discovery_incomplete = False
        if requested_stock or (category!='weapons' and items):
            try:
                if category=='weapons':
                    stock=stock_items(command,project,game,cache,mounted,progress)
                    items=stock['items']+[{**item,'stock_component_assets':stock.get('component_assets',{})} for item in items]
                else:
                    stock=stock_items(command,project,game,cache,mounted,progress,category=category,managed=items)
                    items=stock['items']
                report['errors'].extend(stock['errors'])
                discovery_incomplete = bool(stock['errors']) or (bool(requested_stock) and not stock['items'])
                if discovery_incomplete and not stock['errors']:
                    report['errors'].append({'reason':'Preview discovery returned no models; existing artwork retained'})
                report['fallbacks']=stock.get('fallbacks',[])
                report['stock_requested']=len(requested_stock)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                report['errors'].append({'reason':str(error)})
                discovery_incomplete = True
                if category!='weapons':items=[]
        if len(items)>limit:raise ValueError('Full catalog exceeds preview queue limit')
        # Defaults stay in their own store. Never copy them into generated or
        # let fallback installation hide a user's generated/custom render.
        if missing_only or skip:
            default_public = contained(game, PUBLIC.replace('generated-weapons', 'default-' + category))
            default_index = default_public / 'index.json'
            if default_index.exists():
                defaults = document(default_index)
                if defaults.get('schema_version') == SCHEMA and defaults.get('owner') == 'allin1.default-previews':
                    default_images, default_hashes = defaults.get('images', {}), defaults.get('image_sha256', {})
                    if not isinstance(default_images, dict) or not isinstance(default_hashes, dict):
                        raise ValueError('Invalid default preview inventory')
                    needed = []
                    for item in items:
                        name = item['weapon'].lower()
                        if not existing_preview(public, old_images, old_hashes, name) and existing_preview(default_public, default_images, default_hashes, name):
                            report['defaults_reused'] = report.get('defaults_reused', 0) + 1
                        else:
                            needed.append(item)
                    items = needed
        # Store identities, not an entire vehicle catalog's PNG bytes in RAM.
        retained = {item['weapon']: result[0] for item in items
                    if (result := existing_preview(public, old_images, old_hashes, item['weapon'].lower()))} if missing_only or skip else {}
        blender_job = {}
        if any(not retained.get(item['weapon']) for item in items):
            from allin1.preview_blender import select_blender, identity
            blender = select_blender(project)
            blender_hash = identity(blender)
            renderer += blender_hash
            blender_job = {'blender_executable':str(blender),'blender_identity':blender_hash}
        report['selected_weapons'] = [item['weapon'] for item in items]
        protected = {key_for(item,edition,renderer) for item in items}
        protected.update(retained.values())
        # Keep recovery copies even when this pass uses a new renderer revision.
        protected.update(filename.rsplit('.', 2)[1] for filename in old_images.values()
                         if isinstance(filename, str) and re.fullmatch(pattern.pattern+r'\.[a-f0-9]{64}\.png', filename))
        published = {}
        published_hashes = {}
        if discovery_incomplete:
            # An incomplete discovery is not evidence that a model was removed.
            # Artwork is presentation only; it grants no install/spawn authority.
            for name in old_images:
                if not pattern.fullmatch(name): continue
                previous = existing_preview(public, old_images, old_hashes, name)
                if previous:
                    filename = old_images[name]
                    published[name] = filename
                    published_hashes[filename] = old_hashes[filename]
        from allin1.preview_render_pool import ordered_results, render_workers
        from allin1.preview_render_control import current_control
        from contextlib import nullcontext
        control = current_control()
        workers = render_workers()
        report['missing_only'] = missing_only
        report['render_workers'] = workers if not skip and any(not retained.get(item['weapon']) for item in items) else 0
        if report['render_workers']:
            progress(None, f'{category.title()} previews: {workers} parallel Blender workers; no catalog time limit')
        elif retained:
            progress(None, f'{category.title()} previews: keeping {len(retained)} existing images')
        def prepare_item(item):
            checkpoint()
            if retained.get(item['weapon']):
                result = existing_preview(public, old_images, old_hashes, item['weapon'].lower())
                return result or (retained[item['weapon']], None, 'pending', 'Existing preview changed during preparation; retry the pass')
            key = key_for(item,edition,renderer)
            data = cached(cache,key)
            if data is not None: return key, data, 'cached', None
            if skip: return key, None, 'pending', None
            if budget is not None and time.monotonic()-started >= budget:
                return key, None, 'pending', 'Explicit preview time budget reached'
            stamp = control.started() if control else None
            render_started, failed = time.monotonic(), True
            try:
                with tempfile.TemporaryDirectory(prefix='render-',dir=cache) as temp:
                    job = {**item,**blender_job,'game':str(game),'project':str(project),'edition':edition,
                           'render_threads':max(1,min(8,((os.cpu_count() or 2)-2)//(control.limit() if control else workers)))}
                    timeout = 180 if budget is None else min(180,max(1,budget-(time.monotonic()-started)))
                    data = render(command,job,Path(temp),timeout)
                failed = False
                return key, data, 'rendered', None
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                return key, None, 'pending', str(error)
            finally:
                if control:
                    control.finished(time.monotonic()-render_started, failed, stamp)
        completed, last_heartbeat = 0, 0.0
        def heartbeat():
            nonlocal last_heartbeat
            now = time.monotonic()
            if now-last_heartbeat >= 1:
                last_heartbeat = now
                progress(int(100*completed/max(1,len(items))),
                         f'{category.title()} previews: {completed}/{len(items)} processed; rendering')
        with (control.rendering() if control and report['render_workers'] else nullcontext()), \
                ordered_results(items, prepare_item, control or workers, heartbeat=heartbeat) as results:
            if report['render_workers']: heartbeat()
            for index, (item, (key, data, state, error)) in enumerate(results):
                completed = index+1
                progress(int(100*index/len(items)), f'{category.title()} previews: {index}/{len(items)} processed · {item["weapon"]}')
                if error: report['errors'].append({'weapon':item['weapon'],'reason':error})
                if data is None:
                    report['pending']+=1
                    previous = existing_preview(public, old_images, old_hashes, item['weapon'].lower())
                    if previous is None: continue
                    key, data, state, _ = previous
                    report['retained_pending'] = report.get('retained_pending', 0)+1
                if not source_unchanged(game,item):
                    report['errors'].append({'weapon':item['weapon'],'reason':'Weapon archive changed before publication'})
                    report['pending']+=1
                    continue
                if state == 'rendered':
                    # Single publication owner: parallel workers return pixels only.
                    if not (cache/(key+'.png')).exists(): reserve_cache_slot(cache,protected)
                    atomic(cache/(key+'.png'),data)
                    atomic(cache/(key+'.json'),json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'key':key,
                        'model':item['weapon'],'category':category,'edition':edition}).encode())
                report[state]+=1
                name = item['weapon'].lower()
                if not pattern.fullmatch(name): raise ValueError('Invalid artwork identity')
                filename = name+'.'+key+'.png'
                target = contained(public,filename)
                if target.exists() and sha(target)!=hashlib.sha256(data).hexdigest():
                    report['errors'].append({'weapon':item['weapon'],'reason':'Existing generated image was modified'})
                    continue
                if not target.exists(): atomic(target,data)
                published[name] = filename
                published_hashes[filename] = hashlib.sha256(data).hexdigest()
                report['weapons'].append({'weapon':item['weapon'],'cache_key':key})
        if control:
            report['render_control'] = control.status()
        if items: progress(100, f'{category.title()} previews: {len(items)}/{len(items)} processed')
        # Commit replacements first. Never interpret skipped/failed work as
        # obsolete artwork, and keep the previous identity map for recovery.
        checkpoint()
        if old_images:
            atomic(cache/'previous-publication.json', index_path.read_bytes())
        atomic(index_path,json.dumps({'schema_version':SCHEMA,'owner':'allin1.prelaunch-previews',
            'images':published,'image_sha256':published_hashes}).encode())
        report['pruned_images'] = 0
        if not skip and not report['pending'] and not report['errors']:
            report['pruned_images'] = prune_published(public, cache, published, pattern, old_hashes)
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError) as error:
        report['status']='unavailable'
        report['errors'].append({'reason':str(error)})
        # A failed preparation must not replace the last committed publication.
        # In particular, missing Blender/renderer resources are not deletions.
    report['elapsed_seconds']=round(time.monotonic()-started,3)
    if report['pending'] or report['errors']: report['status']='partial' if report['weapons'] else 'unavailable'
    progress(None,f'{"Weapon" if category=="weapons" else category.title()} previews: {report["rendered"]} generated, {report["cached"]} cached, {report["pending"]} pending')
    try:
        cache.mkdir(parents=True,exist_ok=True)
        atomic(cache/'last-run.json',json.dumps(report,indent=2).encode())
    except OSError: pass
    return report


def prepare_all(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS, skip_categories=(), missing_only=False):
    return prepare(project,game,cache_root,skip=skip,progress=progress,budget=budget,category='all',skip_categories=skip_categories,missing_only=missing_only)


def _prepare_all(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS, skip_categories=(), missing_only=False):
    """Complete all selected categories; only individual workers have deadlines."""
    started=time.monotonic(); reports={}
    for ordinal,category in enumerate(('weapons','vehicles','gear')):
        checkpoint()
        def update(percent,message):
            progress(None if percent is None else int((ordinal*100+percent)/3),message)
        reports[category]=_prepare(project,game,cache_root,skip=skip or category in skip_categories,progress=update,
            budget=None if budget is None else max(0,budget-(time.monotonic()-started)),category=category,missing_only=missing_only)
    return dict(status='complete' if all(r['status']=='complete' for r in reports.values()) else 'partial',
        categories=reports,**{k:sum(r.get(k,0) for r in reports.values()) for k in ('rendered','cached','pending')},
        errors=[dict(category=c,**e) for c,r in reports.items() for e in r.get('errors',[])])
