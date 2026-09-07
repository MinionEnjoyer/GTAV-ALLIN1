"""Bounded offline catalog renderer, not an emulation of GTA's material shaders.

Orthographic z-buffer, interpolated UVs/normals and a three-light studio.
Vehicles use asphalt/concrete; weapons and gear retain their pegboard.
No GPU context, game hooks, network or per-frame game work.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


from allin1.preview_policy import STUDIO_BACKDROP


def pegboard(size):
    width, height = size
    y, x = np.mgrid[:height, :width]
    light = 1 - .17 * ((x / width - .35) ** 2 + (y / height - .2) ** 2)
    rgb = np.clip(light[..., None] * [190, 185, 172], 0, 255).astype('uint8')
    image = Image.fromarray(rgb)
    draw = ImageDraw.Draw(image)
    step = max(12, width // 32)
    r = max(1, width // 420)
    for cy in range(step // 2, height, step):
        for cx in range(step // 2, width, step):
            draw.ellipse((cx-r, cy-r+1, cx+r, cy+r+1), fill=(211, 205, 190))
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(112, 109, 100))
    return image


def studio_backdrop(size, path=None):
    from allin1.release_paths import no_links
    source = no_links(Path(path) if path is not None else Path(__file__).resolve().parents[2] / STUDIO_BACKDROP)
    if source.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Studio backdrop exceeds size limit')
    with Image.open(source) as image:
        if image.format != 'PNG' or not (1024 <= image.width <= 4096 and 640 <= image.height <= 4096):
            raise ValueError('Invalid studio backdrop dimensions or format')
        return image.convert('RGBA').resize(size, Image.Resampling.LANCZOS)


def studio_lighting(sample, normals, *, category='weapons', decal=False):
    """Linear-light soft key, cool fill, grazing rim; no invented material maps."""
    def direction(value):
        value = np.asarray(value, dtype=float)
        return value / np.linalg.norm(value)
    key = direction((-.55, .7, .65))
    fill = direction((.8, .2, .55))
    rim = direction((.8, .5, -.35))
    diffuse = (.16 + .09 * np.maximum(normals[:, 1], 0))[:, None]
    diffuse = diffuse + .95 * np.maximum(normals @ key, 0)[:, None] * [1.04, 1.0, .94]
    diffuse += .22 * np.maximum(normals @ fill, 0)[:, None] * [.83, .94, 1.08]
    half = direction(key + [0, 0, 1])
    highlight = np.maximum(normals @ half, 0) ** (28 if category == 'vehicles' else 18)
    edge = (1 - np.clip(normals[:, 2], 0, 1)) ** 3 * np.maximum(normals @ rim, 0)
    specular = (highlight * (.045 if category == 'vehicles' else .016))[:, None]
    specular = specular + edge[:, None] * [.055, .075, .095]
    if decal:
        specular = 0
    return np.clip(sample ** 2.2 * diffuse + specular, 0, 1) ** (1 / 2.2)


def render_card(geometries, textures, diffuse_name, size=(512, 320), *, materials=None, flat=False, category='weapons', backdrop=None):
    if category not in ('weapons','vehicles','gear'):raise ValueError('Invalid rendering category')
    triangle_limit=150000 if category=='vehicles' else 50000
    if not geometries or sum(len(g.triangles) for g in geometries) > triangle_limit:
        raise ValueError('Catalog geometry is empty or exceeds triangle budget')
    if sum(len(g.vertices) for g in geometries) > 200000:
        raise ValueError('Catalog vertex budget exceeded')
    if size != (512, 320):
        raise ValueError('Unsupported catalog dimensions')
    # Two-times supersampling keeps silhouettes/holes clean in small cards.
    width, height = size[0]*2, size[1]*2
    yaw, pitch = math.radians(12), math.radians(8)
    c, s, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    rotation = np.array([[c, -s, 0], [-s*sp, -c*sp, cp], [s*cp, c*cp, sp]])
    if category=='vehicles':
        yaw,pitch=math.radians(35),math.radians(16)
        c,s,cp,sp=math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
        rotation=np.array([[c,-s,0],[-s*sp,-c*sp,cp],[s*cp,c*cp,sp]])
    vertices = [np.asarray(g.vertices, dtype=float) for g in geometries]
    if any(v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all() for v in vertices):
        raise ValueError('Invalid model coordinates')
    if flat:
        # Present flat accessories broad-side to the board; firearms retain
        # their established pose. PCA avoids per-model axis guesses.
        _, axes = np.linalg.eigh(np.cov(np.concatenate(vertices).T))
        rotation = axes[:, [2, 1, 0]].T
        for axis in rotation:
            if axis[np.argmax(np.abs(axis))] < 0: axis *= -1
    transformed = [v @ rotation.T for v in vertices]
    points = np.concatenate(transformed)
    lo, hi = points.min(axis=0), points.max(axis=0)
    center = (lo + hi)/2
    scale = min(width*.84/max(hi[0]-lo[0], 1e-8), height*.74/max(hi[1]-lo[1], 1e-8))
    depth = np.full((height, width), -np.inf)
    pixels = np.zeros((height, width, 4), dtype='uint8')
    materials = materials or {}
    draw_order = sorted(zip(geometries, transformed), key=lambda pair: (
        bool(materials.get(id(pair[0]), {}).get('decal')), pair[1][:, 2].mean()))
    for g, v in draw_order:
        material = materials.get(id(g), {})
        tri = np.asarray(g.triangles, dtype=int)
        if not len(tri):
            continue
        if tri.ndim != 2 or tri.shape[1] != 3 or tri.min() < 0 or tri.max() >= len(v):
            raise ValueError('Invalid model indices')
        normals = np.zeros_like(v)
        faces = np.cross(v[tri[:,1]]-v[tri[:,0]], v[tri[:,2]]-v[tri[:,0]])
        for k in range(3):
            np.add.at(normals, tri[:,k], faces)
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        if material.get('cull_backfaces'):
            # Our model-to-camera basis has negative determinant. Outward
            # GTA triangles facing the camera therefore have negative Z here.
            tri=tri[faces[:,2]<0]
        screen = (v-center)*[scale, -scale, 1]+[width/2, height/2, 0]
        name = diffuse_name(g)
        local_textures = material.get('textures', textures)
        texture = local_textures.get((name or '').casefold())
        if texture is None and material.get('solid_colour') is not None:
            texture=Image.new('RGBA',(1,1),material['solid_colour'])
        if texture is None or len(g.texcoords) != len(v):
            raise ValueError('Missing diffuse texture or UVs: '+str(name))
        texture = np.asarray(texture.convert('RGBA'), dtype=float)/255
        palette = None
        if material.get('palette'):
            source = local_textures.get(material['palette'].casefold())
            if source is None: raise ValueError('Missing tint palette: '+material['palette'])
            palette = np.asarray(source.convert('RGB'), dtype=float)[0]/255
        vertex_tints = None
        if palette is not None and material.get('palette_mode') == 'vertex':
            colours = np.asarray(material.get('vertex_colours'), dtype=float)
            if colours.shape != (len(v), 4) or not np.isfinite(colours).all():
                raise ValueError('Invalid vertex tint data')
            vertex_tints = palette[np.clip((colours[:,2]/255*len(palette)).astype(int),0,len(palette)-1)]
        uv = np.asarray(g.texcoords, dtype=float)
        if not np.isfinite(uv).all():
            raise ValueError('Nonfinite texture coordinates')
        for indices in tri:
            p = screen[indices]
            x0, y0 = np.maximum(np.floor(p[:,:2].min(axis=0)).astype(int), [0,0])
            x1, y1 = np.minimum(np.ceil(p[:,:2].max(axis=0)).astype(int), [width-1,height-1])
            if x1 < x0 or y1 < y0:
                continue
            denominator = (p[1,1]-p[2,1])*(p[0,0]-p[2,0])+(p[2,0]-p[1,0])*(p[0,1]-p[2,1])
            if abs(denominator) < 1e-9:
                continue
            yy, xx = np.mgrid[y0:y1+1, x0:x1+1]; xx = xx+.5; yy = yy+.5
            a = ((p[1,1]-p[2,1])*(xx-p[2,0])+(p[2,0]-p[1,0])*(yy-p[2,1]))/denominator
            b = ((p[2,1]-p[0,1])*(xx-p[2,0])+(p[0,0]-p[2,0])*(yy-p[2,1]))/denominator
            weights = np.stack([a,b,1-a-b], axis=-1)
            z = weights @ p[:,2]
            region = depth[y0:y1+1,x0:x1+1]
            visible = (weights.min(axis=-1) >= -1e-6) & (z > region)
            if not visible.any():
                continue
            w = weights[visible]
            coords = w @ uv[indices]
            # CodeWalker UVs and decoded DDS rows both use the DirectX convention.
            tx = (coords[:,0] % 1)*texture.shape[1]-.5
            ty = (coords[:,1] % 1)*texture.shape[0]-.5
            ix, iy = np.floor(tx).astype(int), np.floor(ty).astype(int)
            fx, fy = (tx-ix)[:,None], (ty-iy)[:,None]
            sample = sum(texture[(iy+dy)%texture.shape[0],(ix+dx)%texture.shape[1]] *
                         (fx if dx else 1-fx)*(fy if dy else 1-fy)
                         for dy in (0,1) for dx in (0,1))
            alpha = sample[:,3].copy()
            sample = sample[:,:3].copy()
            if palette is not None:
                if vertex_tints is not None:
                    sample *= w @ vertex_tints[indices]
                else:
                    # CodeWalker's weapon palette shader: diffuse alpha is an
                    # index, (round(a*255.009995)-32)/128, not transparency.
                    palette_index = np.rint(alpha*255.009995).astype(int)-32
                    sample *= palette[np.mod(palette_index, len(palette))]
                alpha[:] = 1
            elif not material.get('decal'):
                alpha = (alpha > .33).astype(float)
            n = w @ normals[indices]
            n /= np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)
            n *= np.where(n[:,2:3] < 0, -1, 1)
            color = studio_lighting(sample, n, category=category, decal=material.get('decal', False))
            target = pixels[y0:y1+1,x0:x1+1]
            prior = target[visible].astype(float)/255
            out_alpha = alpha+prior[:,3]*(1-alpha)
            composed = (color*alpha[:,None]+prior[:,:3]*prior[:,3:4]*(1-alpha[:,None]))/np.maximum(out_alpha[:,None],1e-12)
            target[visible,:3] = (composed*255).astype('uint8')
            target[visible,3] = (out_alpha*255).astype('uint8')
            region[visible] = np.where(alpha>0, z[visible], region[visible])
    foreground = Image.fromarray(pixels)
    board = studio_backdrop((width, height), backdrop) if category == 'vehicles' else pegboard((width,height)).convert('RGBA')
    # Layered contact/soft shadow: no wraparound at the card edges.
    mask = foreground.getchannel('A')
    if category == 'vehicles':
        # Ground the model on the asphalt, rather than a car-shaped wall shadow.
        bounds = mask.getbbox()
        if bounds:
            left, top, right, bottom = bounds
            footprint = Image.new('L', (width, height))
            draw = ImageDraw.Draw(footprint)
            depth = max(10, (right-left) // 15)
            draw.ellipse((left+8, bottom-depth, right-8, min(height-1, bottom+depth//2)), fill=145)
            shadow = Image.new('RGBA', (width, height), (12, 16, 21, 0))
            shadow.putalpha(footprint.filter(ImageFilter.GaussianBlur(12)))
            board = Image.alpha_composite(board, shadow)
    for radius, offset, strength in (() if category == 'vehicles' else ((15,(9,15),.24),(3,(3,5),.16))):
        shifted = Image.new('L',(width,height)); shifted.paste(mask,offset)
        shadow = Image.new('RGBA',(width,height),(25,22,18,0))
        shadow.putalpha(shifted.filter(ImageFilter.GaussianBlur(radius)).point(lambda p: int(p*strength)))
        board = Image.alpha_composite(board, shadow)
    return Image.alpha_composite(board,foreground).convert('RGB').resize(size,Image.Resampling.LANCZOS)
