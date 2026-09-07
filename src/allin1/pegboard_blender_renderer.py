"""Validated weapon/gear interchange and isolated Cycles pegboard rendering."""
import json
import math
import os
from pathlib import Path
import subprocess
import shutil

import numpy as np
from PIL import Image

from allin1.preview_blender import select_blender, identity
from allin1.processes import hidden_process_options
from allin1.prelaunch_previews import stop_worker
from allin1.weapon_card_renderer import pegboard


def prepare_texture(source, material, textures, vertex_count):
    """Resolve GTA tint palettes before lighting; alpha indices aren't opacity."""
    pixels = np.array(source.convert('RGBA'), dtype=np.uint8)
    tints = None
    palette_name = material.get('palette')
    if palette_name:
        palette_image = textures.get(palette_name.casefold())
        if palette_image is None: raise ValueError('Missing tint palette: '+palette_name)
        palette = np.asarray(palette_image.convert('RGB'))[0].astype(float)/255
        if material.get('palette_mode') == 'vertex':
            colors = np.asarray(material.get('vertex_colours'), dtype=float)
            if colors.shape != (vertex_count,4) or not np.isfinite(colors).all():
                raise ValueError('Invalid vertex tint data')
            tints = palette[np.clip((colors[:,2]/255*len(palette)).astype(int),0,len(palette)-1)].tolist()
        else:
            indices = (pixels[:,:,3].astype(int)-32) % len(palette)
            pixels[:,:,:3] = np.rint(pixels[:,:,:3] * palette[indices]).astype(np.uint8)
        pixels[:,:,3] = 255
    elif material.get('opaque'):
        pixels[:,:,3] = 255
    elif not material.get('decal'):
        pixels[:,:,3] = np.where(pixels[:,:,3]>255*.33,255,0)
    if material.get('preview_tint') is not None:
        tint=np.asarray(material['preview_tint'],dtype=float)
        if tint.shape!=(3,) or not np.isfinite(tint).all() or (tint<0).any() or (tint>1).any():
            raise ValueError('Invalid preview tint')
        # Tint the disposable albedo only: authored fabric detail, alpha and
        # normal/specular maps survive, and source/game textures are untouched.
        pixels[:,:,:3]=np.rint(pixels[:,:,:3]*tint).astype(np.uint8)
    return Image.fromarray(pixels), tints


def export_pegboard(geometries, textures, diffuse_name, materials, target, *, flat=False, category='weapons', backdrop='pegboard', resting_flat=False, model=''):
    if category not in ('weapons','gear'): raise ValueError('Invalid pegboard category')
    if backdrop not in ('pegboard','ammo-crate'):raise ValueError('Invalid catalog backdrop')
    crate=backdrop=='ammo-crate'
    if not geometries or sum(len(g.triangles) for g in geometries)>50000:
        raise ValueError('Catalog geometry is empty or exceeds triangle budget')
    if sum(len(g.vertices) for g in geometries)>200000: raise ValueError('Catalog vertex budget exceeded')
    vertices=[np.asarray(g.vertices,dtype=float) for g in geometries]
    if any(v.ndim!=2 or v.shape[1]!=3 or not len(v) or not np.isfinite(v).all() for v in vertices):
        raise ValueError('Invalid model coordinates')
    yaw,pitch=math.radians(12),math.radians(8)
    c,s,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
    rotation=np.array([[c,-s,0],[-s*sp,-c*sp,cp],[s*cp,c*cp,sp]])
    if crate and model.casefold() in ('w_ex_pe', 'w_ex_apmine'):
        # These packages are authored Z-up, with their long edge along Y.
        # PCA tips C4 onto its straps and is unstable for near-square mines.
        # Preserve the actual resting plane; rotate only within the lid plane.
        rotation=np.array([[0.,1.,0.],[-1.,0.,0.],[0.,0.,1.]])
    elif flat or crate:
        _,axes=np.linalg.eigh(np.cov(np.concatenate(vertices).T))
        rotation=axes[:,[2,1,0] if not crate or resting_flat else [1,0,2]].T
        for axis in rotation:
            if axis[np.argmax(np.abs(axis))]<0: axis *= -1
    points=np.concatenate([v@rotation.T for v in vertices])
    lo,hi=points.min(axis=0),points.max(axis=0)
    center=(lo+hi)*.5
    scale=max((hi[0]-lo[0])/(3.2*.84),(hi[1]-lo[1])/(2*.74),1e-8)
    if crate:scale=max(float((hi-lo).max())/(.72 if resting_flat else .62),1e-8)
    if crate and resting_flat:scale=max(scale,(hi[1]-lo[1])/.36)
    if crate and not resting_flat:scale=max(scale,(hi[0]-lo[0])/.36,(hi[1]-lo[1])/.36)
    support_z=max(.542,1.10-(hi[2]-lo[2])/scale) if crate and not resting_flat else .962
    rows=[]; pixel_budget=0
    for index,(g,v) in enumerate(zip(geometries,vertices)):
        tri=np.asarray(g.triangles,dtype=int);uv=np.asarray(g.texcoords,dtype=float)
        if tri.ndim!=2 or tri.shape[1]!=3 or not len(tri) or tri.min()<0 or tri.max()>=len(v):
            raise ValueError('Invalid model indices')
        if uv.shape!=(len(v),2) or not np.isfinite(uv).all(): raise ValueError('Missing or invalid UVs')
        material=materials.get(id(g),{});local=material.get('textures',textures)
        if category=='gear' and model.casefold()=='p_parachute_s':
            # The untinted white pack disappears against the light pegboard.
            # A blue preview-only fabric finish keeps its silhouette readable.
            material={**material,'preview_tint':(45/255,95/255,175/255)}
        name=diffuse_name(g);source=local.get((name or '').casefold())
        if source is None: raise ValueError('Missing diffuse texture: '+str(name))
        pixel_budget+=source.width*source.height
        if max(source.size)>4096 or pixel_budget>64*1024*1024: raise ValueError('Pegboard texture budget exceeded')
        image,tints=prepare_texture(source,material,local,len(v))
        image.save(target/f'diffuse-{index}.png')
        # Match the established camera pose, with outward winding after reflection.
        if np.linalg.det(rotation)<0: tri=tri[:,[0,2,1]]
        row=dict(vertices=((v@rotation.T-center)/scale).tolist(),triangles=tri.tolist(),
            uv=np.column_stack((uv[:,0],1-uv[:,1])).tolist(),diffuse=f'diffuse-{index}.png',
            tints=tints,category=category,decal=bool(material.get('decal')))
        if crate:
            for point in row['vertices']:
                point[2]+=support_z-(lo[2]-center[2])/scale
                point[1]-=.22 if resting_flat else .205
        for role in ('normal','specular'):
            name=material.get(role)
            source=local.get(name.casefold()) if name else None
            if source is None: continue
            pixel_budget+=source.width*source.height
            if max(source.size)>4096 or pixel_budget>64*1024*1024: raise ValueError('Pegboard texture budget exceeded')
            source.save(target/f'{role}-{index}.png');row[role]=f'{role}-{index}.png'
        rows.append(row)
    copies=([(0,.44,0)] if resting_flat else [(-.43,0,0),(-.43,.43,0),(.43,.43,0)]) if crate else []
    return dict(category=category,meshes=rows,board_z=float((lo[2]-center[2])/scale-.055),preview_scene=backdrop,crate_open=crate and not resting_flat,support_z=support_z,display_copies=copies)


def render_pegboard(geometries,textures,diffuse_name,*,materials=None,flat=False,category='weapons',job,work):
    from allin1.preview_render_pool import blender_threads
    from allin1_sdk.compiled_render import detect_blender
    from allin1.pegboard_blender_scene import SCENE_SCRIPT
    executable=Path(job['blender_executable']) if job.get('blender_executable') else select_blender(job['project'])
    fingerprint=identity(executable)
    if job.get('blender_identity',fingerprint)!=fingerprint: raise ValueError('Blender changed after preview validation')
    installation=detect_blender(executable)
    if installation is None or int(installation.version.split('.')[0])<4: raise ValueError('Catalog previews require Blender 4 or newer')
    target=work/'blender';target.mkdir(exist_ok=True)
    manifest=export_pegboard(geometries,textures,diffuse_name,materials or {},target,flat=flat,category=category,
        backdrop=job.get('preview_backdrop','pegboard'),resting_flat=job.get('weapon') in
        ('WEAPON_STICKYBOMB','WEAPON_PROXMINE','WEAPON_PIPEBOMB','WEAPON_FLARE','WEAPON_NEWSPAPER','WEAPON_ACIDPACKAGE'),
        model=job.get('model',''))
    (target/'scene.json').write_text(json.dumps(manifest,allow_nan=False),encoding='utf-8')
    if manifest['preview_scene']=='ammo-crate':
        from allin1.preview_policy import THROWABLE_TEXTURES, VEHICLE_TEXTURES
        from allin1.prelaunch_previews import contained
        for relative in THROWABLE_TEXTURES+tuple(p for p in VEHICLE_TEXTURES if '/concrete_' in p):
            source=contained(Path(job['project']),relative)
            with Image.open(source) as image:
                if max(image.size)>4096:raise ValueError('Crate texture exceeds pixel budget')
            shutil.copyfile(source,target/source.name)
    pegboard((2048,1280)).save(target/'pegboard.png')
    (target/'render.py').write_text(SCENE_SCRIPT,encoding='utf-8')
    with (work/'blender.log').open('wb') as log:
        process=subprocess.Popen([str(executable),'--background','--factory-startup','--disable-autoexec',
            '--threads',str(blender_threads(job)),'--python-exit-code','9',
            '--python',str(target/'render.py'),'--',str(target)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
            **hidden_process_options())
        try:
            if process.wait(timeout=150): raise ValueError('Blender pegboard render failed: '+(work/'blender.log').read_text(errors='replace')[-1800:])
        finally: stop_worker(process)
    if identity(executable)!=fingerprint: raise ValueError('Blender changed during rendering')
    with Image.open(target/'render.png') as image:
        if image.size!=(1280,800): raise ValueError('Unexpected Blender render dimensions')
        return image.convert('RGB').resize((512,320),Image.Resampling.LANCZOS)
