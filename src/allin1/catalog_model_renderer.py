"""Decode assembled vehicle fragments / equipment drawables in the worker."""
from pathlib import Path
from dataclasses import replace
import re
import numpy as np
from PIL import Image

from allin1.prelaunch_previews import contained, document, sha
from allin1.stock_weapon_previews import extract, file_state
from allin1.catalog_model_previews import IDENTITY, catalog_names, GEAR_MODELS
from allin1.weapon_card_renderer import render_card, STUDIO_BACKDROP


def select_geometries(scene):
    """Keep the best LOD of each component, not several superimposed LODs."""
    ranks={'veryhigh':0,'high':1,'med':2,'medium':2,'low':3,'vlow':4,'verylow':4}
    def component(g):
        return re.sub(r'^(?:veryhigh|high|medium|med|verylow|vlow|low) drawable ', 'drawable ',g.component,flags=re.I)
    best={}
    for g in scene.geometries:
        rank=ranks.get(g.lod.casefold(),5)
        key=component(g)
        best[key]=min(best.get(key,rank),rank)
    return [g for g in scene.geometries if ranks.get(g.lod.casefold(),5)==best[component(g)]
        and not any(x in g.component.casefold() for x in ('damaged','windscreen_cracked'))]


def parked_rotors(geometries):
    """Omit animated blur cards, retaining actual stopped blades and their hubs."""
    from allin1.vehicle_catalog import vehicle_model_hash
    names = {'vehicle_blurredrotor', 'vehicle_blurredrotor_emissive'}
    shaders = names | {f'hash_{vehicle_model_hash(n):08x}' for n in names}
    return [g for g in geometries if g.material_name.casefold().removesuffix('.sps') not in shaders]


def strip_remote_helpers(geometries):
    """Ignore tiny remote authoring quads when framing equipment, not real parts.

    Some props carry a near-origin helper quad meters away from the actual mesh.
    Only remove wholly remote faces totaling under 0.5% of the surface area.
    """
    points=np.concatenate([np.asarray(g.vertices) for g in geometries])
    lo,hi=np.percentile(points,[5,95],axis=0);extent=np.maximum(hi-lo,.01)
    result=[]
    for g in geometries:
        v=np.asarray(g.vertices);t=np.asarray(g.triangles)
        if not len(t):continue
        faces=v[t]
        outside=((faces<lo-extent)|(faces>hi+extent)).any(axis=2).all(axis=1)
        areas=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)
        if not outside.any() or areas[outside].sum()>=areas.sum()*.005:
            result.append(g);continue
        kept=t[~outside];used=np.unique(kept);mapping={int(old):n for n,old in enumerate(used)}
        result.append(replace(g,vertices=tuple(g.vertices[i] for i in used),
            texcoords=tuple(g.texcoords[i] for i in used),
            triangles=tuple(tuple(mapping[int(i)] for i in face) for face in kept)))
    return result


def complete_shared_wheels(scene, geometries):
    """Instantiate a shared wheel template at otherwise empty wheel bones.

    The SDK assembles/mirrors authored children. Many cars author just a front
    pair and reuse it on the rear axle; only fill explicit, unrepresented bones.
    """
    bones={b.index:b for b in scene.bones};world={};visiting=set()
    def matrix(b):
        if b.index in world:return world[b.index]
        if b.index in visiting:raise ValueError('Wheel skeleton cycle')
        visiting.add(b.index)
        x,y,z,w=b.rotation
        q=np.array([x,y,z,w]);q=q/max(np.linalg.norm(q),1e-12);x,y,z,w=q
        rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
            [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
            [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        local=np.eye(4);local[:3,:3]=rotation@np.diag(b.scale);local[:3,3]=b.local_position
        world[b.index]=matrix(bones[b.parent_index])@local if b.parent_index in bones else local
        visiting.remove(b.index)
        return world[b.index]
    wheels={b.name:b for b in scene.bones if re.fullmatch(r'wheel_[lr](?:f|r|m[1-3])',b.name)}
    present={g.component for g in geometries};result=list(geometries)
    for name,bone in wheels.items():
        if name in present:continue
        choices=[b for n,b in wheels.items() if n in present and n[6]==name[6]]
        if not choices:continue
        source=min(choices,key=lambda b:np.linalg.norm(np.array(b.position)-bone.position))
        transform=matrix(bone)@np.linalg.inv(matrix(source))
        for g in geometries:
            if g.component!=source.name:continue
            v=np.array(g.vertices);v=v@transform[:3,:3].T+transform[:3,3]
            result.append(replace(g,component=name,vertices=tuple(map(tuple,v))))
    return result


def render_job(job,work):
    from allin1_sdk.native_assets import (NativeAssetInspector, load_native_model_scene,
        _model_diffuse_texture_name, _HASHED_VEHICLE_SHADER_SEMANTICS)
    project,game=Path(job['project']),Path(job['game'])
    category=job['category'];name=job['weapon'];model=job['model']
    if not IDENTITY.fullmatch(name.lower()) or not IDENTITY.fullmatch(model):raise ValueError('Invalid preview model identity')
    if job['edition'] not in ('Legacy','Enhanced'):raise ValueError('Invalid edition')
    authority=job.get('authority')
    if authority:
        from allin1.catalog_model_previews import validated_vehicles
        from allin1.prelaunch_previews import mounted_packs
        allowed,_=validated_vehicles(game,mounted_packs(project,game))
        if authority not in allowed or name!=authority['weapon']:raise ValueError('Managed preview authority changed')
    elif name not in catalog_names(project,category):raise ValueError('Unknown catalog model')
    if category=='vehicles' and name!=model:raise ValueError('Vehicle model mismatch')
    if category=='gear' and model not in GEAR_MODELS.get(name,()):raise ValueError('Equipment model mismatch')
    refs=job['assets'];extension='.yft' if category=='vehicles' else '.ydr'
    if not 1<=len(refs)<=11 or Path(refs[0]['path']).name.lower()!=model+extension:
        raise ValueError('Invalid model preview assembly')
    if authority and refs[0]['archive']!=authority['archive']:raise ValueError('Model is not receipt-owned')
    has_hi=category=='vehicles' and len(refs)>1 and Path(refs[1]['path']).name.lower()==model+'_hi.yft'
    if authority and has_hi and refs[1]['archive']!=authority['archive']:raise ValueError('High model is not receipt-owned')
    if any(not ref['path'].lower().endswith('.ytd') for ref in refs[2 if has_hi else 1:]):raise ValueError('Invalid texture reference')
    inspector=NativeAssetInspector(project,game)
    folders=[]
    for n,ref in enumerate(refs):
        path=extract(project,game,ref,work/('asset'+str(n)+(extension if n==0 or (n==1 and has_hi) else '.ytd')))
        folders.append(inspector.export_workspace(path,work/('decoded'+str(n)),edition=job['edition']))
    manifest=document(folders[0]/'native-workspace.json')
    xml=contained(folders[0],manifest['xml']['path'])
    scene,_,warning=load_native_model_scene(xml,name=model,defer_uv_validation=category=='vehicles')
    if scene is None:raise ValueError('Model conversion failed: '+str(warning))
    geometries=select_geometries(scene)
    if has_hi:
        high_manifest=document(folders[1]/'native-workspace.json')
        high,_,warning=load_native_model_scene(contained(folders[1],high_manifest['xml']['path']),name=model+'_hi',defer_uv_validation=True)
        if high is None:raise ValueError('High model conversion failed: '+str(warning))
        high_geometry=select_geometries(high)
        # Hi fragments provide the close-up body; base fragments supply wheel
        # templates and their complete skeleton. Never overlay both bodies.
        geometries=[g for g in high_geometry if not g.component.startswith('wheel_')]+[
            g for g in geometries if g.component.startswith('wheel_')]
    if not geometries:raise ValueError('No supported model geometry')
    if category=='gear':geometries=strip_remote_helpers(geometries)
    if category=='vehicles':
        geometries=parked_rotors(geometries)
        geometries=complete_shared_wheels(scene,geometries)
        # Show clean catalog vehicles, not the optional dirt overlay. Its
        # coplanar decal is not opaque body geometry.
        geometries=[g for g in geometries if not (_model_diffuse_texture_name(g) or '').casefold().startswith('vehicle_genericmud')]
        from allin1.vehicle_blender_renderer import render_vehicle
        image=render_vehicle(scene,geometries,folders,job,work)
        if any(file_state(contained(game,r['archive']))!=r['state'] for r in refs):raise ValueError('Model source changed')
        if authority and sha(contained(game,authority['archive']))!=authority['archive_sha256']:raise ValueError('Managed archive changed')
        image.save(work/'preview.png',format='PNG')
        return
    needed={(_model_diffuse_texture_name(g) or '').casefold() for g in geometries}
    needed.update(name.casefold() for g in geometries for slot,name in g.texture_parameters
                  if slot in ('BumpSampler','SpecSampler'))
    textures={};pixels=0
    from allin1.vehicle_blender_renderer import open_texture
    # Shared dictionaries first, then vehicle-specific, then embedded textures.
    for folder in reversed(folders):
        for path in sorted(folder.rglob('*.dds')):
            if path.stem.casefold() not in needed:continue
            with open_texture(path) as source:
                if source.width*source.height>4096*4096:raise ValueError('Texture exceeds pixel budget')
                source.thumbnail((1024,1024),Image.Resampling.LANCZOS)
                pixels+=source.width*source.height
                if pixels>64*1024*1024:raise ValueError('Texture assembly exceeds memory budget')
                textures[path.stem.casefold()]=source.convert('RGBA')
    materials={}
    for g in geometries:
        texture=_model_diffuse_texture_name(g)
        shader=(g.material_name or '').casefold()
        semantic=_HASHED_VEHICLE_SHADER_SEMANTICS.get(shader,shader)
        parameters=dict(g.texture_parameters)
        materials[id(g)]={'normal':parameters.get('BumpSampler'),'specular':parameters.get('SpecSampler')}
        if category=='vehicles':materials[id(g)]={'cull_backfaces':True}
        if category=='vehicles' and 'decal' in semantic:materials[id(g)]={'decal':True}
        if category=='vehicles' and 'paint' in semantic:
            # Paint's specular mask is not an albedo map. Use a neutral showroom
            # paint colour rather than rendering that mask as black/white paint.
            materials[id(g)]={'solid_colour':(112,140,148,255),'textures':{},'cull_backfaces':True}
            continue
        # Paint and glass shaders can legitimately have no diffuse sampler.
        # Unknown missing textures fail instead of silently producing blank art.
        if not texture or texture.casefold() not in textures:
            if category=='vehicles' and (any(n in semantic for n in ('glass','light','chrome')) or (texture or '').startswith('script_rt_')):
                colour=(63,79,88,255) if 'glass' in semantic else (60,65,65,255)
                materials[id(g)]={'solid_colour':colour}
            else:raise ValueError('Missing model texture: '+str(texture))
    from allin1.pegboard_blender_renderer import render_pegboard
    image=render_pegboard(geometries,textures,_model_diffuse_texture_name,materials=materials,
                         category=category,job=job,work=work)
    if any(file_state(contained(game,r['archive']))!=r['state'] for r in refs):raise ValueError('Model source changed')
    if authority and sha(contained(game,authority['archive']))!=authority['archive_sha256']:raise ValueError('Managed archive changed')
    image.save(work/'preview.png',format='PNG')
