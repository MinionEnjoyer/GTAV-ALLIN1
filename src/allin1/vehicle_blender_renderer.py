"""Offline vehicle cards using the SDK's validated geometry/material interchange."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import struct
import os
import shutil
import math
from PIL import Image

from allin1.prelaunch_previews import stop_worker
from allin1.processes import hidden_process_options
from allin1.preview_blender import select_blender, identity
from allin1.preview_policy import VEHICLE_TEXTURES
from allin1.release_paths import contained
from allin1.vehicle_preview_paint import paint_for_job, apply_paint


def open_texture(path):
    try: return Image.open(path)
    except NotImplementedError:
        # GTA also uses uncompressed A8 dictionaries; Pillow rejects DDPF_ALPHA.
        # In a colour/specular sampler this single channel is a scalar mask.
        with path.open('rb') as stream:
            header=stream.read(128)
            if len(header)!=128 or header[:4]!=b'DDS ': raise ValueError('Invalid DDS header')
            height,width,pitch=struct.unpack_from('<III',header,12)
            flags,bits=struct.unpack_from('<I',header,80)[0],struct.unpack_from('<I',header,88)[0]
            if flags!=2 or bits!=8 or not 1<=width<=4096 or not 1<=height<=4096:
                raise ValueError('Unsupported DDS pixel format: '+path.name)
            stride=pitch if pitch>=width else width
            if stride>16384: raise ValueError('Invalid A8 DDS stride')
            data=stream.read(stride*height)
            if len(data)!=stride*height: raise ValueError('Truncated A8 DDS')
        scalar=Image.frombytes('L',(width,height),b''.join(data[y*stride:y*stride+width] for y in range(height)))
        return scalar.convert('RGBA')


def preview_scene_for(paint, bones):
    category=str(paint.get('category','')).strip().casefold()
    # Boat propellers must not select the aircraft backdrop. Explicit catalog
    # class wins over bone-name fallback (also keeps amphibious planes airborne).
    if category in ('boats','boat','watercraft','water vessels','submarine','submarines'):
        return 'ocean'
    if (category in ('helicopters','planes','helicopter','plane','aircraft')
            or any(b.name.casefold().startswith(('rotor_', 'propeller')) for b in bones)):
        return 'runway'
    return 'studio'


def constant_texture_bindings(manifest, root):
    """Uniform masks need no UVs; fully transparent overlays draw nothing.

    Inspect pixels, never infer this from a filename such as 'blank'.
    """
    cache = {}
    for material in manifest['materials']:
        bindings = []
        for binding in material['texture_bindings']:
            relative = binding.get('path')
            if relative and binding['role'] in ('overlay','diffuse','specular'):
                if relative not in cache:
                    with Image.open(contained(root, relative)) as image:
                        cache[relative] = image.convert('RGBA').getextrema()
                extrema = cache[relative]
                if binding['role'] == 'overlay' and extrema[3] == (0,0):
                    continue
                if all(low == high for low,high in extrema):
                    binding['constant_texture'] = True
            bindings.append(binding)
        material['texture_bindings'] = bindings


def validate_material_uvs(manifest):
    """Require artwork UVs; use the base BSDF for unavailable optional masks."""
    for material in manifest['materials']:
        meshes = [m for m in manifest['meshes'] if m['material'] == material['key']]
        kept = []
        for binding in material['texture_bindings']:
            uv = binding.get('uv_map','UV0')
            if (binding.get('path') and not binding.get('constant_texture') and
                    binding['role'] in ('diffuse','overlay','normal','specular') and
                    any(uv not in m['uv_layers'] for m in meshes)):
                generic_detail = (binding['role']=='diffuse' and
                    binding.get('name','').casefold()=='vehicle_generic_detail2' and
                    material['source_name'].casefold() in ('vehicle_mesh','hash_d963b58b'))
                if binding['role'] in ('normal','specular') or generic_detail:
                    manifest.setdefault('material_warnings',[]).append(
                        material['source_name']+': unavailable '+uv+' for '+binding['slot']+
                        '; using base material response (geometry retained)')
                    continue
                raise ValueError('Missing authored '+uv+' for '+material['source_name']+
                                 ' / '+binding['name'])
            kept.append(binding)
        material['texture_bindings'] = kept


def render_vehicle(scene, geometries, folders, job, work):
    from allin1.preview_render_pool import blender_threads
    from allin1_sdk.compiled_render import export_render_interchange, detect_blender
    from allin1.vehicle_blender_scene import SCENE_SCRIPT
    executable = Path(job['blender_executable']) if job.get('blender_executable') else select_blender(job['project'])
    fingerprint = identity(executable)
    if job.get('blender_identity', fingerprint) != fingerprint: raise ValueError('Blender changed after preview validation')
    installation = detect_blender(executable)
    if installation is None: raise ValueError('Selected Blender failed its version check')
    if int(installation.version.split('.')[0]) < 4: raise ValueError('Vehicle previews require Blender 4 or newer')
    target = work/'blender'; target.mkdir(exist_ok=True)
    for relative in VEHICLE_TEXTURES:
        source=contained(Path(job['project']),relative)
        with Image.open(source) as image:
            if image.width>4096 or image.height>4096: raise ValueError('Studio texture exceeds pixel budget')
        shutil.copyfile(source,target/source.name)
    needed = {name.casefold() for g in geometries for name in g.texture_names}
    assets = {}; pixels = 0; serial = 0
    for folder in reversed(folders):
        for path in sorted(folder.rglob('*.dds')):
            name = path.stem.casefold()
            if name not in needed: continue
            with open_texture(path) as image:
                if image.width*image.height > 4096*4096: raise ValueError('Vehicle texture exceeds pixel budget')
                image.thumbnail((2048,2048),Image.Resampling.LANCZOS)
                pixels += image.width*image.height
                if pixels > 96*1024*1024: raise ValueError('Vehicle textures exceed memory budget')
                output = target/(str(serial)+'.png'); serial += 1
                image.convert('RGBA').save(output)
                assets[name] = output
    exported = export_render_interchange(replace(scene,geometries=tuple(geometries)),target,texture_assets=assets)
    # Paint samplers often carry specular masks, not paint albedo. Keep authored
    # normal/spec maps but don't feed those masks into the showroom body colour.
    manifest = json.loads(exported.manifest_path.read_text())
    apply_paint(manifest, paint_for_job(job))
    constant_texture_bindings(manifest, target)
    # OBJ supports one UV set only. Carry exact indexed meshes alongside it so
    # Blender can bind each texture to its authored channel, including seams.
    keys = [line.split()[1] for line in exported.obj_path.read_text().splitlines()
            if line.startswith('usemtl ')]
    manifest['meshes'] = export_vehicle_meshes(geometries, keys)
    validate_material_uvs(manifest)
    manifest['preview_scene'] = preview_scene_for(manifest['preview_paint'], scene.bones)
    exported.manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    (target/'render.py').write_text(SCENE_SCRIPT,encoding='utf-8')
    with (work/'blender.log').open('wb') as log:
        process = subprocess.Popen([str(executable),'--background','--factory-startup','--disable-autoexec',
            '--threads',str(blender_threads(job)),'--python-exit-code','9','--python',str(target/'render.py'),'--',str(target)],
            stdin=subprocess.DEVNULL,stdout=log,stderr=log,**hidden_process_options())
        try:
            if process.wait(timeout=150):
                raise ValueError('Blender vehicle render failed: '+(work/'blender.log').read_text(errors='replace')[-1800:])
        finally: stop_worker(process)
    if identity(executable) != fingerprint: raise ValueError('Blender changed during rendering')
    with Image.open(target/'render.png') as image:
        if image.size != (1280,800): raise ValueError('Unexpected Blender render dimensions')
        return image.convert('RGB').resize((512,320),Image.Resampling.LANCZOS)


def export_vehicle_meshes(geometries, material_keys):
    if len(geometries) != len(material_keys):
        raise ValueError('Vehicle material/geometry count mismatch')
    rows = []
    for g, key in zip(geometries, material_keys):
        channels = getattr(g, 'texcoord_sets', ()) or (g.texcoords,)
        uvs = {}
        for channel, values in enumerate(channels):
            if not values: continue
            if len(values) != len(g.vertices) or any(
                    len(uv) != 2 or not all(math.isfinite(x) for x in uv) for uv in values):
                raise ValueError('Invalid vehicle UV channel')
            uvs['UV'+str(channel)] = [(u, 1-v) for u,v in values]
        rows.append(dict(vertices=g.vertices, triangles=g.triangles,
                         uv_layers=uvs, material=key))
    return rows
