"""Isolated read-only native weapon thumbnail worker; never loads the game.

The frozen distribution contains the SDK's CPU renderer. In source checkouts
the same modules are resolved from the adjacent SDK, never downloaded at launch.
"""
from __future__ import annotations

from pathlib import Path
import json
import sys
import subprocess

from lxml import etree
from PIL import Image
from allin1.weapon_card_renderer import render_card
from allin1.prelaunch_previews import contained, document, sha, NAME
from allin1.processes import hidden_process_options


def main(request):
    job_path = Path(request).resolve()
    job = document(job_path, 65536)
    project, game = Path(job['project']), Path(job['game'])
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(project.parent/'ALLIN1-SDK/src'))
    from allin1_sdk.rpf_tools import RpfExplorerService
    from allin1_sdk.native_assets import NativeAssetInspector, _model_scene_from_xml, _model_diffuse_texture_name

    if job.get('operation')=='discover_stock':
        from allin1.stock_weapon_previews import discover
        result=discover(project,game,Path(job['discovery_cache']),job['mounted'],
                        progress=lambda p,m:print(m,flush=True))
        (job_path.parent/'discovery.json').write_text(json.dumps(result),encoding='utf-8')
        return

    if job['edition'] not in ('Legacy', 'Enhanced'): raise ValueError('Invalid edition')
    if job.get('kind')=='stock':
        from allin1.stock_weapon_previews import catalog_names, extract, file_state
        if job['weapon'] not in catalog_names(project):raise ValueError('Weapon is not in the non-throwable GBAY catalog')
        assets=job['assets']
        parts=job.get('components',[])
        if len(parts)>16 or len(assets)!=2+2*len(parts):raise ValueError('Invalid stock preview assembly')
        if Path(assets[0]['path']).name.casefold()!=job['model']+'.ydr' or not assets[1]['path'].lower().endswith('.ytd'):
            raise ValueError('Stock asset identity mismatch')
        for i,part in enumerate(parts):
            if part['asset_index']!=2+2*i or Path(assets[2+2*i]['path']).name.casefold()!=part['model']+'.ydr':raise ValueError('Component asset identity mismatch')
        extracted=[extract(project,game,ref,job_path.parent/('asset'+str(i)+('.ydr' if i%2==0 else '.ytd'))) for i,ref in enumerate(assets)]
        image=render_assets(project,game,job['model'],extracted,job['edition'],job_path.parent,parts=parts)
        if any(file_state(contained(game,a['archive']))!=a['state'] for a in assets):raise ValueError('Stock preview source changed')
        image.save(job_path.parent/'preview.png',format='PNG')
        print('Rendered stock',job['weapon'],flush=True)
        return

    if not NAME.fullmatch(job['weapon'].lower()): raise ValueError('Invalid weapon')
    if job['edition'] not in ('Legacy', 'Enhanced'): raise ValueError('Invalid edition')
    source = contained(game, job['archive'])
    if sha(source) != job['archive_sha256']: raise ValueError('Source changed before rendering')
    service = RpfExplorerService(project, game)
    index = service.index(source)
    if index.edition.casefold() != job['edition'].casefold(): raise ValueError('Archive edition mismatch')
    entries = [entry for entry in index.entries if entry.kind != 'directory']
    if len(entries) > 25000: raise ValueError('Archive index exceeds preview limit')

    def select(name):
        matches = [entry for entry in entries if entry.name.casefold() == name.casefold()]
        if len(matches) != 1: raise ValueError('Missing or ambiguous asset: '+name)
        if matches[0].size > 128*1024*1024: raise ValueError('Asset exceeds preview limit')
        return matches[0]

    def xml(name):
        entry = select(name)
        target = service.extract(index, entry, job_path.parent/name)
        if target.stat().st_size > 4*1024*1024: raise ValueError('Metadata exceeds preview limit')
        return etree.parse(str(target), etree.XMLParser(resolve_entities=False, no_network=True))

    definitions = xml('weapons.meta').xpath('.//Item[@type="CWeaponInfo"]')
    definitions = [item for item in definitions if item.findtext('Name') == job['weapon']]
    if len(definitions) != 1: raise ValueError('Weapon definition is missing or ambiguous')
    model = definitions[0].findtext('Model') or ''
    archetypes = xml('weaponarchetypes.meta')
    dictionaries = [item.findtext('txdName') for item in archetypes.findall('.//Item')
                    if item.findtext('modelName') == model]
    if len(dictionaries) != 1 or not dictionaries[0]: raise ValueError('Texture dictionary is missing or ambiguous')
    model_entry = select(model+'.ydr')
    texture_entry = select(dictionaries[0]+'.ytd')
    resources = (model_entry, texture_entry)
    extracted = [service.extract(index, entry, job_path.parent/('asset'+entry.suffix)) for entry in resources]
    from allin1.stock_weapon_previews import default_components
    selected=default_components(definitions[0]);parts=[]
    if selected:
        from allin1.weapon_preview_assembly import unique_component
        component_entries=[e for e in entries if e.name.casefold()=='weaponcomponents.meta']
        if not 0<len(component_entries)<=32 or sum(e.size for e in component_entries)>8*1024*1024:
            raise ValueError('Component metadata missing or exceeds preview budget')
        components=[]
        manifest=job_path.parent/'component-extract.tsv';destination=job_path.parent/'component-metadata'
        manifest.write_text(''.join(f'{entry.archive_path}\t{entry.path}\t{ordinal}.meta\n' for ordinal,entry in enumerate(component_entries)),encoding='utf-8')
        subprocess.run([str(service.patcher),'extract-virtual-entries',str(game),str(source),str(manifest),str(destination)],
                       check=True,capture_output=True,timeout=30,**hidden_process_options())
        for ordinal,entry in enumerate(component_entries):
            path=destination/(str(ordinal)+'.meta')
            if path.stat().st_size>4*1024*1024:raise ValueError('Component metadata exceeds limit')
            components.append(etree.parse(str(path),etree.XMLParser(resolve_entities=False,no_network=True)))
        for choice in selected:
            row=unique_component(components,choice['name']);cm=row.findtext('Model') or ''
            if not cm:continue
            cd=select(cm+'.ydr')
            txds=[n.findtext('txdName') for n in archetypes.findall('.//Item') if n.findtext('modelName')==cm]
            if len(txds)>1:raise ValueError('Ambiguous component dictionary')
            txd=(txds[0] if txds else cm)+'.ytd'
            ct=select(txd) if any(e.name.casefold()==txd.casefold() for e in entries) else texture_entry
            parts.append({**choice,'model':cm,'child_bone':row.findtext('AttachBone') or '', 'asset_index':len(extracted)})
            for entry in (cd,ct):
                extracted.append(service.extract(index,entry,job_path.parent/('asset'+str(len(extracted))+entry.suffix)))
    image=render_assets(project,game,model,extracted,job['edition'],job_path.parent,parts=parts)
    if sha(source) != job['archive_sha256']: raise ValueError('Source changed during rendering')
    image.save(job_path.parent/'preview.png', format='PNG')
    print('Rendered', job['weapon'], model, flush=True)


def render_assets(project,game,model,extracted,edition,work,*,parts=()):
    from allin1_sdk.native_assets import NativeAssetInspector, _model_scene_from_xml, _model_diffuse_texture_name
    inspector = NativeAssetInspector(project, game)
    workspaces = [inspector.export_workspace(path, work/('decoded'+suffix), edition=edition)
                  for suffix, path in zip(('.ydr','.ytd'), extracted)]
    manifests = [document(path/'native-workspace.json', 4*1024*1024) for path in workspaces]
    drawable=contained(workspaces[0], manifests[0]['xml']['path'])
    if not parts:return render_decoded(drawable, workspaces[1], model)
    from allin1.weapon_preview_assembly import attach_geometry
    geometries,textures,materials,root=decode_card(drawable,workspaces[1],model)
    for i,part in enumerate(parts):
        folder=work/('part'+str(i));folder.mkdir()
        pair=extracted[part['asset_index']:part['asset_index']+2]
        ws=[inspector.export_workspace(path,folder/('decoded'+suffix),edition=edition) for suffix,path in zip(('.ydr','.ytd'),pair)]
        manifest=document(ws[0]/'native-workspace.json',4*1024*1024)
        gs,ts,ms,child=decode_card(contained(ws[0],manifest['xml']['path']),ws[1],part['model'])
        placed=attach_geometry(root,child,gs,part['parent_bone'],part['child_bone'])
        for original,new in zip(gs,placed):materials[id(new)]={**ms[id(original)],'textures':ts}
        geometries.extend(placed)
    return render_card(geometries,textures,_model_diffuse_texture_name,materials=materials,
                       flat=model.casefold().startswith('w_me_knuckle'))


def render_decoded(drawable, texture_folder, model):
    from allin1_sdk.native_assets import _model_diffuse_texture_name
    geometries,textures,materials,_=decode_card(drawable,texture_folder,model)
    return render_card(geometries,textures,_model_diffuse_texture_name,materials=materials,
                       flat=model.casefold().startswith('w_me_knuckle'))

def decode_card(drawable, texture_folder, model):
    from allin1_sdk.native_assets import _model_scene_from_xml, _model_diffuse_texture_name
    scene, _, warning = _model_scene_from_xml(drawable, model)
    if scene is None: raise ValueError('Native drawable conversion failed: '+str(warning))
    root = etree.parse(str(drawable), etree.XMLParser(resolve_entities=False, no_network=True)).getroot()
    shaders = root.findall('ShaderGroup/Shaders/Item')
    buffers = root.findall('.//VertexBuffer')
    if len(buffers) != len(scene.geometries): raise ValueError('Ambiguous drawable material/vertex mapping')
    materials = {}
    widths = dict(Position=3,Normal=3,BlendWeights=4,BlendIndices=4,Colour0=4,Colour1=4,Tangent=4,**{'TexCoord'+str(i):2 for i in range(8)})
    for g, buffer in zip(scene.geometries, buffers):
        if g.material_index is None or not 0 <= g.material_index < len(shaders): raise ValueError('Missing shader')
        shader = shaders[g.material_index]
        parameters = {p.get('name'):p.findtext('Name') for p in shader.findall('Parameters/Item') if p.get('type')=='Texture'}
        palette = parameters.get('TextureSamplerDiffPal') or parameters.get('TintPaletteSampler')
        shader_name = shader.findtext('FileName','').casefold()
        alpha_palette = 'TextureSamplerDiffPal' in parameters or '_palette.sps' in shader_name or shader_name in tuple(f'hash_{h:08x}' for h in (231364109,3294641629,731050667))
        material = dict(palette=palette, palette_mode='alpha' if alpha_palette else 'vertex',
                        decal=shader.find('RenderBucket') is not None and shader.find('RenderBucket').get('value') in ('1','2','3'))
        if palette and not alpha_palette:
            offset=0; colour_offset=None
            for item in buffer.findall('Layout/*'):
                if item.tag not in widths: raise ValueError('Unsupported tint vertex layout: '+item.tag)
                if item.tag=='Colour0': colour_offset=offset
                offset+=widths[item.tag]
            if colour_offset is None: raise ValueError('Tint shader has no vertex colour')
            material['vertex_colours'] = [tuple(map(float,line.split()[colour_offset:colour_offset+4])) for line in buffer.findtext('Data','').splitlines() if line.strip()]
        materials[id(g)] = material
    textures = {}
    needed = {(_model_diffuse_texture_name(g) or '').casefold() for g in scene.geometries}
    needed.update(m['palette'].casefold() for m in materials.values() if m['palette'])
    # Native YDRs may embed their own palette (knuckle dusters do). External
    # dictionaries are loaded first; the drawable's embedded texture wins.
    for texture in [*Path(texture_folder).rglob('*.dds'), *Path(drawable).parent.rglob('*.dds')]:
        if texture.stem.casefold() not in needed: continue
        with Image.open(texture) as decoded:
            if decoded.width*decoded.height > 4096*4096: raise ValueError('Diffuse texture exceeds preview pixel budget')
            decoded.load()
            decoded.thumbnail((1024,1024), Image.Resampling.LANCZOS)
            textures[texture.stem.casefold()] = decoded.convert('RGBA')
    if not textures: raise ValueError('No decoded diffuse textures; retaining existing artwork')
    # Never superimpose multiple LODs in a catalog thumbnail.
    lods = scene.lods
    preferred = next((lod for name in ('veryhigh','high','med','medium','low') for lod in lods if lod.casefold()==name), lods[0] if lods else '')
    geometries = [geometry for geometry in scene.geometries if geometry.lod==preferred]
    if not geometries: raise ValueError('No model geometry to render')
    return geometries,textures,materials,root


if __name__ == '__main__':
    main(sys.argv[1])
