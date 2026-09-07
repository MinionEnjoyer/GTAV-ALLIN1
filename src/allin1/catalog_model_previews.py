"""Receipt-bound vehicle and stock equipment discovery for offline thumbnails.

Uses the same exact virtual archive extraction as weapon previews. Missing or
ambiguous assets use downloaded defaults or placeholders; no streaming natives or GTA process.
"""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import re
import subprocess

from allin1.config import tomllib
from allin1.prelaunch_previews import contained, document, sha, checkpoint
from allin1.stock_weapon_previews import archives, inventory
from allin1.vehicle_catalog import VehicleCatalog, vehicle_model_hash

IDENTITY = re.compile(r'[a-z0-9][a-z0-9_-]{0,63}')
LIMIT = 2048
# Equipment without a standalone drawable (e.g. the wearable juggernaut suit)
# deliberately keeps its packaged picture rather than showing a wrong model.
GEAR_MODELS = {
    **{name: ('prop_bodyarmour_'+str(index).zfill(2),) for index,name in enumerate((
        'ARMOR_SUPER_LIGHT','ARMOR_LIGHT','ARMOR_STANDARD','ARMOR_HEAVY','ARMOR_SUPER_HEAVY'),2)},
    'GADGET_PARACHUTE': ('p_parachute_s',),
    'WEAPON_FIREEXTINGUISHER': ('w_am_fire_exting',),
    'WEAPON_PETROLCAN': ('w_am_jerrycan',),
    'WEAPON_HAZARDCAN': ('w_ch_jerrycan',),
    'WEAPON_NIGHTVISION': ('hei_bio_heist_nv_goggles',),
}
GEAR_DICTIONARIES={name:'prop_armour_shop' for name in GEAR_MODELS if name.startswith('ARMOR_')}


def catalog_names(project, category):
    if category == 'gear':
        if not contained(project,'prices_gear.toml').is_file():return []
        from allin1.preview_assets import GEAR_PREVIEW_ITEMS
        return list(GEAR_PREVIEW_ITEMS)
    if category != 'vehicles':raise ValueError('Unsupported model preview category')
    names=[]
    path=contained(project,'data/vehicles.toml')
    if path.exists():
        if path.stat().st_size>4*1024*1024:raise ValueError('Vehicle catalog exceeds limit')
        names.extend(row['model'].lower() for row in tomllib.loads(path.read_text(encoding='utf-8'))['vehicles'])
    story=contained(project,'data/story_vehicles.json')
    if story.exists():names.extend(row['model'].lower() for row in document(story)['vehicles'])
    catalog_only=contained(project,'data/catalog_only_vehicles.json')
    if catalog_only.exists():names.extend(row['model'].lower() for row in document(catalog_only)['vehicles'])
    names=sorted(set(names))
    if len(names)>LIMIT or any(not IDENTITY.fullmatch(n) for n in names):raise ValueError('Invalid vehicle catalog')
    return names


def validated_vehicles(game, mounted, *, progress=lambda *_:None):
    result=[];errors=[]
    root=contained(game,'scripts/.allin1/mods')
    paths=sorted(root.glob('*.json')) if root.exists() else []
    if len(paths)>256:raise ValueError('Managed package count exceeds preview limit')
    for path in paths:
        checkpoint()
        try:
            receipt=document(path)
            if receipt.get('enabled') is not True:continue
            declarations=(receipt.get('extension') or {}).get('gbay',{}).get('catalogs',[])
            if not any(d.get('kind')=='vehicle' for d in declarations):continue
            records=receipt.get('files',[])
            if not isinstance(records,list) or len(records)>8192:raise ValueError('Invalid receipt files')
            owned={}
            for record in records:
                name=record['destination'];expected=record['sha256']
                if name in owned or not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('Invalid receipt identity')
                if sha(contained(game,name))!=expected:raise ValueError('Managed payload hash mismatch: '+name)
                owned[name]=expected
            selected=[]
            for declaration in declarations:
                if declaration.get('kind')!='vehicle':continue
                source=declaration['source']
                if source not in owned:raise ValueError('Vehicle catalog is not receipt-owned')
                catalog=VehicleCatalog.load(contained(game,source))
                if catalog.catalog_id!=declaration['id']:raise ValueError('Vehicle catalog identity mismatch')
                catalog.validate_package_ownership(receipt.get('dlc_packs',[]),allow_traffic=True)
                for vehicle in catalog.vehicles:
                    if vehicle.source_pack not in mounted:continue
                    archive=f'mods/update/x64/dlcpacks/{vehicle.source_pack}/dlc.rpf'
                    if archive not in owned:raise ValueError('Vehicle archive is not receipt-owned')
                    selected.append(dict(weapon=vehicle.model,archive=archive,archive_sha256=owned[archive],
                        catalog_sha256=owned[source],package=receipt['id'],
                        vehicle_category=vehicle.category,vehicle_name=vehicle.display_name))
            result.extend(selected)
        except (OSError,ValueError,KeyError,TypeError,AttributeError) as error:
            errors.append(dict(receipt=path.name,reason=str(error)))
    counts=defaultdict(int)
    for item in result:counts[vehicle_model_hash(item['weapon'])]+=1
    ambiguous={i['weapon'] for i in result if counts[vehicle_model_hash(i['weapon'])]>1}
    errors.extend(dict(weapon=n,reason='Ambiguous catalog ownership') for n in sorted(ambiguous))
    result=[i for i in result if i['weapon'] not in ambiguous]
    if len(result)>LIMIT:raise ValueError('Vehicle preview limit exceeded')
    return result,errors


def discover(project,game,cache,mounted,category,managed=(),progress=lambda *_:None):
    project,game,cache=Path(project),Path(game),Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    wanted=catalog_names(project,category)
    candidates=archives(game,mounted)
    if category=='gear':
        # These catalog props live in base prop/weapon archives and mpheist.
        # Do not index every world/map DLC merely to render ten equipment items.
        candidates=[p for p in candidates if p.name in ('common.rpf','x64e.rpf','update.rpf') or p.parent.name=='mpheist']
        for stock in (game/'x64c.rpf',):
            if not stock.is_file():continue
            override=contained(game,'mods/'+stock.name)
            candidate=override if override.is_file() else stock
            if candidate not in candidates:candidates.insert(0,candidate)
    for item in managed:
        candidate=contained(game,item['archive'])
        if sha(candidate)!=item['archive_sha256']:raise ValueError('Managed archive changed')
        if candidate not in candidates:candidates.append(candidate)
    helper_id=''.join(sha(contained(project,'tools/RpfPatcher/'+n)) for n in ('RpfPatcher.exe','RpfPatcher.dll','CodeWalker.Core.dll'))
    records=[];errors=[]
    for n,archive in enumerate(candidates):
        progress(None,f'{category.title()} model discovery {n+1}/{len(candidates)}: {archive.name}')
        try:records.append(inventory(project,game,archive,cache,helper_id,category=category))
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
            errors.append(dict(archive=archive.relative_to(game).as_posix(),reason=str(error)))
    assets=defaultdict(list);txds={};parents={};owned_metadata={}
    managed_archives={i['archive'] for i in managed}
    for record in records:
        archive=record['identity']['archive']
        if archive in managed_archives:owned_metadata[archive]=record
        else:
            txds.update(record['archetypes'])
            parents.update(record.get('parents',{}))
        for row in record['assets']:assets[row['name']].append(row)
    priorities={p.relative_to(game).as_posix():n for n,p in enumerate(candidates)}
    def choose(name,owner=None,companion=None):
        choices=assets.get(name,[])
        if owner:choices=[r for r in choices if r['archive']==owner]
        else:choices=[r for r in choices if r['archive'] not in managed_archives]
        highest=max((priorities[r['archive']] for r in choices),default=-1)
        choices=[r for r in choices if priorities[r['archive']]==highest]
        if len(choices)>1 and companion:
            # Some Rockstar patch packs carry both a TXD patch and a complete
            # vehicle family. Use the unique texture next to the selected model,
            # never a lower-priority archive or an arbitrary first match.
            adjacent=[r for r in choices if r['archive']==companion['archive'] and
                      r['archive_path']==companion['archive_path']]
            if len(adjacent)==1:choices=adjacent
        if len(choices)!=1:raise ValueError('Missing or ambiguous asset: '+name)
        return choices[0]
    official=set(wanted)
    owned={i['weapon']:i for i in managed if i['weapon'] not in official}
    errors.extend(dict(weapon=i['weapon'],reason='Managed catalog collides with stock vehicle') for i in managed if i['weapon'] in official)
    items=[];fallbacks=[]
    for name in sorted(official | set(owned)):
        try:
            owner=owned.get(name,{}).get('archive')
            local_txds={**txds,**owned_metadata.get(owner,{}).get('archetypes',{})}
            local_parents={**parents,**owned_metadata.get(owner,{}).get('parents',{})}
            models=(name,) if category=='vehicles' else GEAR_MODELS.get(name,())
            if not models:
                fallbacks.append(dict(item=name,reason='No standalone model; using downloaded defaults or placeholder'))
                continue
            suffix='.yft' if category=='vehicles' else '.ydr'
            model=next((m for m in models if m+suffix in assets),None)
            if not model:raise ValueError('No standalone model; using downloaded defaults or placeholder')
            drawable=choose(model+suffix,owner)
            # Keep the base skeleton/wheels, and use the hi body when present.
            resources=[drawable]
            if category=='vehicles' and model+'_hi.yft' in assets:
                resources.append(choose(model+'_hi.yft',owner))
            txd=GEAR_DICTIONARIES.get(name,local_txds.get(model,model)) if category=='gear' else local_txds.get(model,model)
            if txd+'.ytd' in assets:resources.append(choose(txd+'.ytd',owner,drawable))
            if category=='gear':
                for suffix in ('+hi.ytd','+hidr.ytd'):
                    if model+suffix in assets:resources.insert(1,choose(model+suffix,owner))
            if category=='vehicles':
                if txd+'+hi.ytd' in assets:resources.insert(2 if len(resources)>1 and resources[1]['name'].endswith('_hi.yft') else 1,choose(txd+'+hi.ytd',owner,drawable))
                visited={txd}
                while txd in local_parents:
                    txd=local_parents[txd]
                    if txd in visited or len(visited)>=5:raise ValueError('Cyclic or excessive texture inheritance')
                    visited.add(txd)
                    parent_owner=owner if owner and any(a['archive']==owner for a in assets.get(txd+'.ytd',[])) else None
                    resources.append(choose(txd+'.ytd',parent_owner))
                for shared in ('vehshare.ytd','vehshare_worn.ytd'):
                    if shared in assets:resources.append(choose(shared))
            items.append(dict(weapon=name,kind='stock',category=category,model=model,assets=resources,
                authority=owned.get(name),catalog_identity=hashlib.sha256(json.dumps(wanted).encode()).hexdigest()))
        except (ValueError,KeyError) as error:errors.append(dict(weapon=name,reason=str(error)))
    return dict(items=items,errors=errors,fallbacks=fallbacks,requested=wanted)
