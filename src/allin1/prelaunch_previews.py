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
RENDER_VERSION = 'weapon-card-4-default-assembly'
MAX_SECONDS = 1800  # First full catalog render; subsequent launches reuse the cache.
MAX_WEAPONS = 128
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_CACHE_IMAGES = 256
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
            declarations = (receipt.get('extension') or {}).get('gbay', {}).get('catalogs', [])
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
        return list(dict.fromkeys(match.group(1).lower() for node in ET.parse(output).findall('.//Item')
                if (match := re.fullmatch(r'dlcpacks:[/\\]([a-zA-Z0-9_-]+)[/\\]',(node.text or '').strip()))))

def worker_command(project):
    bundled = no_links(Path(project)/'tools/WeaponPreview/WeaponPreview.exe')
    helper_folder = Path(project)/'tools/RpfPatcher'
    helper_identity = hashlib.sha256(''.join(path.name+sha(path) for path in sorted(helper_folder.iterdir())
        if path.is_file() and path.suffix.lower() in {'.exe','.dll','.xml','.json'}).encode()).hexdigest()
    if bundled.is_file(): return [str(bundled)], sha(bundled)+helper_identity
    # Development only. Published builds contain the isolated worker, not an SDK checkout dependency.
    sdk = Path(project).parent/'ALLIN1-SDK/src'
    if not getattr(sys,'frozen',False) and (sdk/'allin1_sdk/native_assets.py').is_file():
        identity = (sha(Path(__file__).with_name('weapon_preview_worker.py'))
                    + sha(Path(__file__).with_name('weapon_card_renderer.py'))
                    + sha(Path(__file__).with_name('stock_weapon_previews.py'))
                    + sha(Path(__file__).with_name('weapon_preview_assembly.py'))
                    + sha(sdk/'allin1_sdk/native_assets.py'))
        return [sys.executable,'-m','allin1.weapon_preview_worker'], identity+helper_identity
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
        process = subprocess.Popen([*command,str(request)],stdout=log,stderr=log,**hidden_process_options())
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


def stock_items(command,project,game,cache,mounted,progress):
    """Discover through the isolated worker; no SDK runtime in the launcher."""
    from allin1.stock_weapon_previews import catalog_names
    if not catalog_names(project):return {'items':[],'errors':[]}
    checkpoint()
    with tempfile.TemporaryDirectory(prefix='discovery-',dir=cache) as folder:
        work=Path(folder);request=work/'job.json'
        atomic(request,json.dumps({'operation':'discover_stock','project':str(project),'game':str(game),
            'mounted':list(mounted),'discovery_cache':str(cache/'stock-discovery')}).encode())
        with (work/'discovery.log').open('wb') as log:
            process=subprocess.Popen([*command,str(request)],stdout=log,stderr=log,**hidden_process_options())
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
    if item.get('kind')=='stock':
        from allin1.stock_weapon_previews import file_state
        return all(file_state(contained(game,a['archive']))==a['state'] for a in item['assets'])
    return sha(contained(game,item['archive']))==item['archive_sha256']

def prepare(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS):
    """Serialize per-game cache publication; no renderer survives this call."""
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
            return _prepare(project,game,cache_root,skip=skip,progress=progress,budget=budget)
    finally: lock.unlink(missing_ok=True)


def preview_queue(items, progress):
    """Report completed queue entries, not elapsed time or assumed render success."""
    total = len(items)
    for index, item in enumerate(items):
        checkpoint()
        progress(int(100 * index / total),
                 f'Weapon previews: {index}/{total} processed · Checking {item["weapon"]}')
        yield item
    if total:
        progress(100, f'Weapon previews: {total}/{total} processed')


def _prepare(project, game, cache_root, *, skip=False, progress=lambda *_:None, budget=MAX_SECONDS):
    """Optional artwork phase, after hazards and before Reactor/GTA startup."""
    started = time.monotonic()
    game, project = no_links(game).resolve(), no_links(project).resolve()
    edition = 'Enhanced' if (game/'GTA5_Enhanced.exe').exists() else 'Legacy'
    cache = no_links(Path(cache_root)/hashlib.sha256(str(game).casefold().encode()).hexdigest()[:16])
    report = {'schema_version':SCHEMA,'status':'complete','edition':edition,'rendered':0,'cached':0,'pending':0,'errors':[],'weapons':[]}
    public = contained(game, PUBLIC)
    index_path = public/'index.json'
    try:
        # Do not take ownership of an unrelated file at our publication path.
        if index_path.exists() and document(index_path).get('owner') != 'allin1.prelaunch-previews':
            raise ValueError('Preview publication index is not ALLIN1-owned')
        old_images = document(index_path).get('images', {}) if index_path.exists() else {}
        if not isinstance(old_images, dict) or len(old_images)>MAX_WEAPONS:
            raise ValueError('Invalid previous preview index')
        mounted=mounted_packs(project,game)
        checkpoint()
        items, rejected = validated_weapons(game, mounted,progress=progress)
        report['errors'].extend(rejected)
        from allin1.stock_weapon_previews import catalog_names
        requested_stock=catalog_names(project)
        command, renderer = worker_command(project) if items or requested_stock else ([], '')
        cache.mkdir(parents=True,exist_ok=True)
        if requested_stock:
            try:
                stock=stock_items(command,project,game,cache,mounted,progress)
                items=stock['items']+items
                report['errors'].extend(stock['errors'])
                report['stock_requested']=len(requested_stock)
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                report['errors'].append({'reason':str(error)})
        if len(items)>MAX_WEAPONS:raise ValueError('Full catalog exceeds preview queue limit')
        report['selected_weapons'] = [item['weapon'] for item in items]
        protected = {key_for(item,edition,renderer) for item in items}
        published = {}
        for item in preview_queue(items, progress):
            key = key_for(item,edition,renderer)
            data = cached(cache,key)
            if data is not None: report['cached']+=1
            elif skip or time.monotonic()-started >= budget:
                report['pending']+=1
                continue
            else:
                try:
                    with tempfile.TemporaryDirectory(prefix='render-',dir=cache) as temp:
                        work = Path(temp)
                        job = {**item,'game':str(game),'project':str(project),'edition':edition}
                        data = render(command,job,work,min(40,max(1,budget-(time.monotonic()-started))))
                    if not source_unchanged(game,item): raise ValueError('Weapon archive changed during rendering')
                    if not (cache/(key+'.png')).exists(): reserve_cache_slot(cache,protected)
                    atomic(cache/(key+'.png'),data)
                    atomic(cache/(key+'.json'),json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'key':key}).encode())
                    report['rendered']+=1
                except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
                    report['errors'].append({'weapon':item['weapon'],'reason':str(error)})
                    report['pending']+=1
                    continue
            name = item['weapon'].lower()
            if not NAME.fullmatch(name): raise ValueError('Invalid artwork identity')
            if not source_unchanged(game,item):
                raise ValueError('Weapon archive changed before publication')
            filename = name+'.'+key+'.png'
            target = contained(public,filename)
            if target.exists() and sha(target)!=hashlib.sha256(data).hexdigest():
                report['errors'].append({'weapon':item['weapon'],'reason':'Existing generated image was modified'})
                continue
            if not target.exists(): atomic(target,data)
            published[name] = filename
            report['weapons'].append({'weapon':item['weapon'],'cache_key':key})
        # Fresh index omits disabled/unmounted/tampered sources and stale results.
        checkpoint()
        atomic(index_path,json.dumps({'schema_version':SCHEMA,'owner':'allin1.prelaunch-previews','images':published}).encode())
        for previous in set(old_images.values())-set(published.values()):
            # Only prune a formerly indexed image if it still matches our cache.
            if not isinstance(previous,str) or not re.fullmatch(r'weapon_[a-z0-9_]{1,56}\.[a-f0-9]{64}\.png',previous): continue
            key = previous.rsplit('.',2)[1]
            data = cached(cache,key)
            old_path = contained(public,previous)
            if data is not None and old_path.exists() and sha(old_path)==hashlib.sha256(data).hexdigest():
                old_path.unlink()
    except (OSError,ValueError,KeyError,TypeError,AttributeError,subprocess.SubprocessError) as error:
        report['status']='unavailable'
        report['errors'].append({'reason':str(error)})
        # Suppress stale generated overrides if validation could not complete.
        try:
            if index_path.exists() and document(index_path).get('owner')=='allin1.prelaunch-previews':
                atomic(index_path,json.dumps({'schema_version':SCHEMA,'owner':'allin1.prelaunch-previews','images':{}}).encode())
        except (OSError,ValueError,AttributeError): pass
    report['elapsed_seconds']=round(time.monotonic()-started,3)
    if report['pending'] or report['errors']: report['status']='partial' if report['weapons'] else 'unavailable'
    progress(None,f'Weapon previews: {report["rendered"]} generated, {report["cached"]} cached, {report["pending"]} pending')
    try:
        cache.mkdir(parents=True,exist_ok=True)
        atomic(cache/'last-run.json',json.dumps(report,indent=2).encode())
    except OSError: pass
    return report
