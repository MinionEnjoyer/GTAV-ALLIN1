"""Read-only discovery of installed stock GBAY artwork sources.

Archive structure/metadata are cached by path, filesystem identity and helper
build. Assets are extracted only by exact indexed virtual paths. No GTA writes.
"""
from pathlib import Path
import hashlib, json, re, subprocess, tempfile
from collections import defaultdict
from allin1.config import tomllib
from allin1.prelaunch_previews import atomic, contained, document, no_links, sha, NAME
from allin1.processes import hidden_process_options
from allin1.garage_map_detection import _effective_pack_archives

REVISION=3


def component_preview(row):
    create = row.find('CreateObject')
    value = create.get('value','').casefold() if create is not None else 'true'
    if value not in ('true','false'):raise ValueError('Invalid component CreateObject flag')
    return {'model':(row.findtext('Model') or '').casefold(),
            'child_bone':row.findtext('AttachBone') or '', 'create_object':value=='true'}

def default_components(row):
    result=[]
    for point in row.findall('AttachPoints/Item'):
        selected=[c for c in point.findall('Components/Item') if c.find('Default') is not None and c.find('Default').get('value','').lower()=='true']
        if len(selected)>1:raise ValueError('Ambiguous default components at '+str(point.findtext('AttachBone')))
        for component in selected:
            name=component.findtext('Name');bone=point.findtext('AttachBone')
            if not name or not bone:raise ValueError('Incomplete default attachment')
            result.append({'name':name,'parent_bone':bone})
    if len(result)>16:raise ValueError('Too many default components')
    return result


def file_state(path):
    stat=no_links(path).stat()
    return {'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'ctime_ns':stat.st_ctime_ns}


def catalog_names(project):
    path=contained(project,'data/weapons.toml')
    if not path.exists():return []
    if path.stat().st_size>1024*1024:raise ValueError('Stock catalog exceeds limit')
    rows=tomllib.loads(path.read_text(encoding='utf-8'))['weapons']
    names=[r['name'] for r in rows]
    if len(names)>128 or len(set(names))!=len(names) or any(not NAME.fullmatch(n.lower()) for n in names):
        raise ValueError('Invalid stock weapon catalog')
    return sorted(names)


def throwable_names(project):
    names=set(catalog_names(project))
    if not names:return set()
    rows=tomllib.loads(contained(project,'data/weapons.toml').read_text(encoding='utf-8'))['weapons']
    return {r['name'] for r in rows if r['name'] in names and
        (r['category']=='throwables' or r['name']=='WEAPON_ACIDPACKAGE')}


def archives(game, mounted):
    result=[]
    # Base weapons, patch metadata, and older DLCs bundled into x64w.
    for relative in ('common.rpf','x64e.rpf','x64w.rpf','update/update.rpf'):
        override=contained(game,'mods/'+relative);stock=contained(game,relative)
        selected=override if override.is_file() else stock
        if selected.is_file():result.append(selected)
    if len(mounted)>256:raise ValueError('DLC discovery exceeds limit')
    for pack in mounted:
        if not re.fullmatch(r'[a-z0-9_-]{1,64}',pack):raise ValueError('Invalid mounted DLC')
        # Only installed Rockstar pack roots enter stock discovery. Add-on
        # catalogs retain the separate receipt-authorized path.
        if not contained(game,'update/x64/dlcpacks/'+pack).is_dir():continue
        result.extend(_effective_pack_archives(Path(game),pack))
    return list(dict.fromkeys(result))


def safe_virtual(value, *, archive=False):
    if value=='' and archive:return value
    for segment in value.split('!') if archive else [value]:
        if ':' in segment or '\\' in segment or any(p in ('','.','..') for p in segment.split('/')):
            raise ValueError('Unsafe archive entry path')
    if len(value)>1024 or any(ord(c)<32 for c in value):raise ValueError('Invalid archive entry path')
    return value


def extract(project,game,reference,destination):
    archive=contained(game,reference['archive'])
    if file_state(archive)!=reference['state']:raise ValueError('Preview source changed; rescan required')
    subprocess.run([str(contained(project,'tools/RpfPatcher/RpfPatcher.exe')),'extract-virtual-entry',str(game),str(archive),
                    safe_virtual(reference['archive_path'],archive=True),safe_virtual(reference['path']),str(destination)],
                   check=True,capture_output=True,timeout=35,**hidden_process_options())
    if file_state(archive)!=reference['state']:raise ValueError('Preview source changed during extraction')
    if destination.stat().st_size>128*1024*1024:raise ValueError('Preview asset exceeds limit')
    return destination


def inventory(project,game,archive,cache,helper_id, *, category='weapons'):
    from lxml import etree as E
    relative=archive.relative_to(game).as_posix();state=file_state(archive)
    identity={'archive':relative,'state':state,'helper':helper_id,'revision':REVISION,'category':category,'model_revision':2}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    stored=cache/(key+'.json')
    if stored.exists():
        result=document(stored,32*1024*1024)
        if result.get('identity')==identity:return result
    helper=contained(project,'tools/RpfPatcher/RpfPatcher.exe')
    with tempfile.TemporaryDirectory(prefix='stock-index-',dir=cache) as folder:
        work=Path(folder);index=work/'index.json'
        subprocess.run([str(helper),'index-json',str(game),str(archive),str(index)],check=True,capture_output=True,timeout=60,**hidden_process_options())
        raw=document(index,64*1024*1024)
        if len(raw['entries'])>250000:raise ValueError('Stock archive entry limit exceeded')
        entries=[e for e in raw['entries'] if e['kind']!='directory']
        assets=[];metas=[]
        for e in entries:
            name=e['name'].casefold()
            ref={'archive':relative,'state':state,'archive_path':safe_virtual(e['archive_path'],archive=True),'path':safe_virtual(e['path'])}
            if name.endswith(('.ydr','.ytd','.yft')):assets.append({'name':name,**ref})
            if name.endswith('.meta') and 'weapon' in name and not any(s in name for s in ('anim','shop','personality')):
                if category=='weapons':metas.append(e)
            if category=='vehicles' and name=='vehicles.meta':metas.append(e)
        if len(metas)>512:raise ValueError('Weapon metadata scan exceeds limit')
        definitions={};archetypes={};components={};parents={}
        if metas:
            output=work/'metadata';manifest=work/'extract.tsv'
            manifest.write_text(''.join(f"{safe_virtual(e['archive_path'],archive=True)}\t{safe_virtual(e['path'])}\t{n}.meta\n" for n,e in enumerate(metas)),encoding='utf-8')
            subprocess.run([str(helper),'extract-virtual-entries',str(game),str(archive),str(manifest),str(output)],check=True,capture_output=True,timeout=60,**hidden_process_options())
            for n,e in enumerate(metas):
                path=output/f'{n}.meta'
                if path.stat().st_size>8*1024*1024:raise ValueError('Weapon metadata exceeds limit')
                try:root=E.parse(str(path),E.XMLParser(resolve_entities=False,no_network=True))
                except E.XMLSyntaxError:continue  # Unrelated/binary metadata is not a weapon definition.
                for row in root.xpath('.//Item[@type="CWeaponInfo"]'):
                    name=row.findtext('Name');model=row.findtext('Model')
                    if name and model:definitions[name]={'model':model.casefold(),'metadata':e['path'],'components':default_components(row)}
                for row in root.xpath('.//Item[starts-with(@type,"CWeaponComponent")]'):
                    name=row.findtext('Name');model=row.findtext('Model')
                    if name:components[name]=component_preview(row)
                for row in root.findall('.//Item'):
                    model=row.findtext('modelName');txd=row.findtext('txdName')
                    if model and txd:archetypes[model.casefold()]=txd.casefold()
                for row in root.findall('.//txdRelationships/Item'):
                    child=row.findtext('child');parent=row.findtext('parent')
                    if child and parent:parents[child.casefold()]=parent.casefold()
        if file_state(archive)!=state:raise ValueError('Stock archive changed during discovery')
        result={'identity':identity,'assets':assets,'definitions':definitions,'archetypes':archetypes,'components':components,'parents':parents}
        atomic(stored,json.dumps(result).encode());return result


def discover(project,game,cache,mounted,progress=lambda *_:None):
    project,game,cache=Path(project),Path(game),Path(cache);cache.mkdir(parents=True,exist_ok=True)
    wanted=catalog_names(project);wanted_set=set(wanted)
    helper_id=''.join(sha(contained(project,'tools/RpfPatcher/'+name)) for name in ('RpfPatcher.exe','RpfPatcher.dll','CodeWalker.Core.dll'))
    candidates=archives(game,mounted);records=[];errors=[]
    for n,archive in enumerate(candidates):
        progress(10,f'Catalog discovery {n+1}/{len(candidates)}: {archive.parent.name}/{archive.name}')
        try:records.append(inventory(project,game,archive,cache,helper_id))
        except (OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
            errors.append({'archive':archive.relative_to(game).as_posix(),'reason':str(error)})
    definitions={};assets=defaultdict(list);archetypes={};components={}
    for record in records:
        for name,row in record['definitions'].items():
            if name in wanted_set:definitions[name]={**row,'source':record['identity']['archive']}
        archetypes.update(record['archetypes'])
        components.update(record.get('components',{}))
        for row in record['assets']:assets[row['name']].append(row)
    priority={a.relative_to(game).as_posix():n for n,a in enumerate(candidates)}
    def choose(name,preferred):
        rows=assets.get(name,[])
        highest=max((priority[r['archive']] for r in rows),default=-1)
        choices=[r for r in rows if priority[r['archive']]==highest]
        if len(choices)!=1:raise ValueError(f'Missing or ambiguous {name}: {len(choices)} candidates')
        return choices[0]
    items=[]
    for name in wanted:
        try:
            definition=definitions[name];model=definition['model']
            drawable=choose(model+'.ydr',definition['source'])
            txd=archetypes.get(model,model)
            texture=choose(txd+'.ytd',drawable['archive'])
            resources=[drawable,texture];parts=[]
            for selected in definition.get('components',[]):
                component=components[selected['name']]
                cm=component['model']
                if not cm or not component.get('create_object',True):continue
                cd=choose(cm+'.ydr',definition['source'])
                if cd==drawable:continue  # Base varmod already is the displayed drawable.
                ct_name=archetypes.get(cm,cm)+'.ytd'
                # Some components use the parent's shared dictionary.
                ct=choose(ct_name,cd['archive']) if assets.get(ct_name) else texture
                parts.append({**selected,**component,'asset_index':len(resources)})
                resources.extend([cd,ct])
            items.append({'weapon':name,'kind':'stock','model':model,'assets':resources,'components':parts,
                          'catalog_sha256':sha(contained(project,'data/weapons.toml'))})
        except (ValueError,KeyError) as error:errors.append({'weapon':name,'reason':str(error)})
    return {'items':items,'errors':errors,'requested':wanted,'archives':len(candidates)}
