"""Preview-only paint choices, independent of edition, machine and catalog order."""
import hashlib
import math
import re

from allin1.config import tomllib
from allin1.release_paths import contained

# Display-referred sRGB; convert to scene-linear values for Blender.
PALETTE = (
    ('white', (225, 227, 224)), ('black', (25, 27, 29)),
    ('gray', (113, 117, 122)), ('red', (180, 22, 29)),
    ('blue', (25, 70, 164)), ('orange', (225, 87, 14)),
    ('yellow', (230, 185, 18)),
)

# GTA groups these under aircraft classes rather than the military class.
MILITARY_AIRCRAFT = frozenset(('akula', 'annihilator', 'annihilator2', 'hunter',
    'savage', 'valkyrie', 'valkyrie2', 'buzzard', 'cargobob', 'cargobob3', 'cargobob4',
    'hydra', 'lazer', 'raiju', 'titan', 'avenger', 'avenger2', 'avenger3', 'avenger4'))

# These span industrial and service classes. Do not recolor every industrial
# vehicle: that class also contains delivery vans and armored/security trucks.
CONSTRUCTION_VEHICLES = frozenset(('bulldozer', 'cutter', 'dump', 'biff',
    'rubble', 'tiptruck', 'tiptruck2', 'mixer', 'mixer2', 'handler', 'forklift'))
CONSTRUCTION_NAMES = re.compile(
    r'\b(bulldozer|excavator|backhoe|forklift|telehandler|dump truck|tipper|'
    r'cement mixer|concrete mixer|wheel loader|road roller|reach stacker)\b')


def linear_rgb(rgb):
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                 for v in (channel / 255 for channel in rgb))


def select_paint(model, category='', name=''):
    model = model.strip().casefold()
    category = category.strip().casefold()
    police = (model.startswith(('police', 'sheriff', 'fbi', 'riot'))
              or (category == 'emergency' and model.startswith('pol'))
              or bool(re.search(r'\b(police|sheriff|interceptor|pursuit)\b', name.casefold())))
    if category == 'military' or model in MILITARY_AIRCRAFT:
        label, rgb, style = 'olive green', (83, 91, 53), 'military'
    elif police:
        label, rgb, style = 'black and white', (25, 27, 29), 'police'
    elif category == 'emergency':
        # Ambulance/fire liveries are not civilian respray candidates either.
        label, rgb, style = 'authored emergency livery', (225, 227, 224), 'emergency'
    elif (model in CONSTRUCTION_VEHICLES or category == 'construction'
          or CONSTRUCTION_NAMES.search(name.casefold())):
        label, rgb, style = 'construction yellow', (230, 185, 18), 'construction'
    else:
        slot = int.from_bytes(hashlib.sha256(('gbay-paint-v1:' + model).encode()).digest()[:8], 'big') % len(PALETTE)
        label, rgb = PALETTE[slot]
        style = 'civilian'
    return dict(name=label, style=style, color=linear_rgb(rgb), category=category)


def paint_for_job(job):
    authority = job.get('authority')
    if authority:
        # This receipt-owned record was revalidated by the model worker.
        return select_paint(job['model'], authority.get('vehicle_category', ''), authority.get('vehicle_name', ''))
    from allin1.prelaunch_previews import document
    from pathlib import Path
    project = Path(job['project'])
    rows = []
    path = contained(project, 'data/vehicles.toml')
    if path.exists():
        if path.stat().st_size > 4 * 1024 * 1024: raise ValueError('Vehicle catalog exceeds limit')
        rows.extend(tomllib.loads(path.read_text(encoding='utf-8'))['vehicles'])
    for name in ('story_vehicles.json','catalog_only_vehicles.json'):
        path = contained(project, 'data/'+name)
        if path.exists(): rows.extend(document(path)['vehicles'])
    for row in rows:
        if row['model'].casefold() == job['model'].casefold():
            return select_paint(job['model'], row.get('category', row.get('class', '')), row.get('name', ''))
    return select_paint(job['model'])


def material_diffuse_tint(material, paint):
    """Resolve authored RGB or (2, layer, layer); these are not literal RGB=2.

    Catalog swatches are presentation choices, not live carcols state. Use a
    dark secondary/wheel/interior alongside the existing primary body palette.
    Layer numbering: Sollumz yft/properties.py VehiclePaintLayer.
    """
    from allin1.vehicle_catalog import vehicle_model_hash
    names = {'matdiffusecolor', str(vehicle_model_hash('matDiffuseColor')),
             f'hash_{vehicle_model_hash("matDiffuseColor"):08x}'}
    parameters = [p for p in material.get('shader_parameters', [])
                  if p['name'].casefold() in names]
    if not parameters:
        return None
    if len(parameters) != 1:
        raise ValueError('Ambiguous matDiffuseColor')
    parameter = parameters[0]
    values = parameter['values']
    if parameter['type'].casefold() != 'vector' or len(values) != 1 or len(values[0]) != 4:
        raise ValueError('Invalid matDiffuseColor vector')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in values[0]):
        raise ValueError('Invalid matDiffuseColor component')
    r, g, b, _ = values[0]
    if abs(r - 2) < .0001:
        layer = round(g)
        if layer not in range(1, 8) or abs(g-layer) >= .0001 or abs(b-layer) >= .0001:
            raise ValueError('Unsupported matDiffuseColor paint layer')
        dark = linear_rgb((25, 27, 29))
        layers = {
            1: paint['color'],
            2: linear_rgb((225, 227, 224)) if paint['style']=='police' else dark,
            3: paint['color'], 4: linear_rgb((65, 68, 72)),
            5: (1.0, 1.0, 1.0), 6: dark, 7: dark,
        }
        material['preview_paint_layer'] = layer
        return layers[layer]
    # Authored shader constants are already linear; do not sRGB-convert again.
    return (r, g, b)


def apply_paint(manifest, paint):
    """Change only disposable paint/glass records; keep authored trim and decals."""
    from allin1.vehicle_catalog import vehicle_model_hash
    manifest['preview_paint'] = paint
    paint_names = {f'vehicle_paint{n}{suffix}' for n in range(1,10) for suffix in ('','_enveff')}
    paints = paint_names | {f'hash_{vehicle_model_hash(n):08x}' for n in paint_names}
    rotor_names = {'vehicle_blurredrotor', 'vehicle_blurredrotor_emissive'}
    rotors = rotor_names | {f'hash_{vehicle_model_hash(n):08x}' for n in rotor_names}
    secondary = {'vehicle_paint2', f'hash_{vehicle_model_hash("vehicle_paint2"):08x}'}
    for material in manifest['materials']:
        source = material['source_name'].casefold()
        # Shader-specific sampler coordinates, not the active/default UV map.
        # https://github.com/Sollumz/wiki/blob/main/documentation/fragments.yft/vehicle-shaders.md
        paint_shader = next((n for n in paint_names if source in
            (n, f'hash_{vehicle_model_hash(n):08x}')), '')
        for binding in material['texture_bindings']:
            slot = binding.get('slot', '')
            channel = 0
            if paint_shader:
                number = int(paint_shader[len('vehicle_paint')])
                if number == 9:
                    channel = 1 if slot == 'DiffuseSampler2' else 0 if slot == 'BumpSampler' else 2
                elif slot == 'DiffuseSampler2' or (slot == 'SpecSampler' and number in (3,4,8)):
                    channel = 1
                elif number == 8 and slot in ('DiffuseSampler', 'BumpSampler', 'SnowSampler0', 'SnowSampler1'):
                    channel = 1
            if channel: binding['uv_map'] = 'UV'+str(channel)
        if source in rotors:
            # Rotor cards encode blade coverage in diffuse alpha. Treating the
            # card as opaque produces a black rectangle and a square shadow.
            material['semantic'] = 'rotor'
            material['preview_cutout'] = True
        camo = next((b for b in material['texture_bindings']
                     if b.get('path') and 'camo' in b['name'].casefold()), None)
        if paint['style']=='military' and camo:
            # Some armored bodies use a layered camouflage shader rather than
            # vehicle_paint. Preserve its pattern and panel overlay, tint olive.
            material['semantic'] = 'paint'
            material['preview_camo'] = True
            material['texture_bindings'] = [
                {**b, 'role':'diffuse' if b is camo else 'overlay' if b.get('slot')=='DiffuseSampler2' else b['role']}
                for b in material['texture_bindings']
                if b is camo or b.get('slot')=='DiffuseSampler2' or b['role'] in ('normal','specular')]
        # Shader identity takes precedence over auxiliary sampler names.
        if source in paints or source.startswith('vehicle_paint'):
            material['semantic'] = 'paint'
            if any(b.get('slot') == 'DiffuseSampler2' and b.get('path') for b in material['texture_bindings']):
                # Layered paint uses a generic weather mask plus authored decals,
                # not a transparent body. Overlay the livery on solid paint.
                material['texture_bindings'] = [
                    {**b, 'role':'overlay' if b.get('slot')=='DiffuseSampler2' else b['role']}
                    for b in material['texture_bindings']
                    if b.get('slot')=='DiffuseSampler2' or b['role'] in ('normal','specular')
                    or (material.get('preview_camo') and b['role']=='diffuse')]
        semantic = material['semantic']
        # Generic worn/rust overlays are weathering, not manufacturer graphics.
        # Clean catalog resprays exclude these just like the separate dirt pass.
        material['texture_bindings'] = [b for b in material['texture_bindings']
            if not (b['role']=='overlay' and b['name'].casefold().startswith('vehicle_generic_worn_'))]
        if semantic in ('paint','glass'):
            # A civilian respray must not erase an authored logo/graphic carried
            # by the primary diffuse sampler. Only discard known generic/spec
            # masks, not every civilian diffuse texture.
            preserve = semantic == 'paint'
            masks = {b['name'].casefold() for b in material['texture_bindings'] if b['role']=='specular'}
            material['texture_bindings'] = [b for b in material['texture_bindings']
                if b['role'] not in ('diffuse','unclassified') or
                (preserve and b['role']=='diffuse' and b['name'].casefold() not in masks
                 and not b['name'].casefold().startswith('vehicle_generic'))]
        if semantic == 'paint':
            material['preview_color'] = (linear_rgb((225,227,224))
                if paint['style']=='police' and source in secondary else paint['color'])
        tint = material_diffuse_tint(material, paint)
        if tint is not None and not material.get('preview_camo'):
            material['preview_diffuse_tint'] = tint
            if semantic == 'paint':
                material['preview_color'] = tint
