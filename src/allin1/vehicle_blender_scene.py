"""Trusted Blender scene program; no scripts from model assets are executed."""

SCENE_SCRIPT = r'''
import bpy, bmesh, json, math, sys
from pathlib import Path
from mathutils import Vector

root = Path(sys.argv[sys.argv.index('--')+1]).resolve(strict=True)
manifest = json.loads((root/'scene.json').read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
if 'meshes' in manifest:
    for record in manifest['materials']: bpy.data.materials.new(record['key'])
    for index,row in enumerate(manifest['meshes']):
        mesh=bpy.data.meshes.new('Vehicle mesh '+str(index))
        mesh.from_pydata(row['vertices'],[],row['triangles']);mesh.update()
        for name,values in row['uv_layers'].items():
            layer=mesh.uv_layers.new(name=name)
            for loop in mesh.loops:layer.data[loop.index].uv=values[loop.vertex_index]
        mat=bpy.data.materials[row['material']];mesh.materials.append(mat)
        obj=bpy.data.objects.new('Vehicle part '+str(index),mesh);bpy.context.collection.objects.link(obj)
        # Match OBJ import's -Y-forward basis without touching local UVs.
        obj.rotation_euler.z=math.pi
else:
    bpy.ops.wm.obj_import(filepath=str(root/'model.obj'),forward_axis='NEGATIVE_Y',up_axis='Z')
objects = [o for o in bpy.context.scene.objects if o.type=='MESH']
bpy.context.view_layer.update()
subject_transforms={obj.name:obj.matrix_world.copy() for obj in objects}
for obj in objects:
    # The validated interchange keeps UV-split vertices. Weld coincident
    # positions in this disposable scene (UVs remain per-loop), otherwise smooth
    # paint gets false faceting at every texture seam. Retain hard panel edges.
    bm=bmesh.new(); bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
    for edge in bm.edges:
        edge.smooth=edge.is_manifold and edge.calc_face_angle(0)<math.radians(55)
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    for face in obj.data.polygons: face.use_smooth = True

def material(name, color, roughness, metallic=0):
    mat = bpy.data.materials.new(name); mat.use_nodes=True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=roughness
    shader.inputs['Metallic'].default_value=metallic
    shader.inputs['Specular IOR Level'].default_value=.18
    return mat,shader

for record in manifest['materials']:
    mat=bpy.data.materials.get(record['key'])
    if not mat: continue
    mat.use_nodes=True; nodes=mat.node_tree.nodes; nodes.clear(); links=mat.node_tree.links
    out=nodes.new('ShaderNodeOutputMaterial'); p=nodes.new('ShaderNodeBsdfPrincipled')
    links.new(p.outputs['BSDF'],out.inputs['Surface'])
    semantic=record['semantic']
    p.inputs['Base Color'].default_value=(*record['color'],1)
    p.inputs['Roughness'].default_value=record['roughness']
    p.inputs['Metallic'].default_value=record['metallic']
    if semantic=='paint':
        p.inputs['Base Color'].default_value=(*record['preview_color'],1)
        p.inputs['Metallic'].default_value=.62
        p.inputs['Coat Weight'].default_value=.65
        p.inputs['Coat Roughness'].default_value=.13
        if manifest['preview_paint']['style']=='military':
            p.inputs['Metallic'].default_value=.12
            p.inputs['Roughness'].default_value=.52
            p.inputs['Coat Weight'].default_value=.12
    if semantic=='glass':
        p.inputs['Base Color'].default_value=(.38,.48,.52,1)
        p.inputs['Transmission Weight'].default_value=.94
        p.inputs['IOR'].default_value=1.45
        p.inputs['Roughness'].default_value=.07
        # Thin glazing: preserve reflections while allowing the cabin through.
        transparent=nodes.new('ShaderNodeBsdfTransparent')
        mix=nodes.new('ShaderNodeMixShader'); mix.inputs[0].default_value=.4
        links.new(transparent.outputs[0],mix.inputs[1]); links.new(p.outputs[0],mix.inputs[2])
        links.new(mix.outputs[0],out.inputs['Surface'])
    used=set(); base_texture=None; overlay_texture=None
    for binding in record['texture_bindings']:
        role=binding['role']; relative=binding.get('path')
        if not relative or role in used or role not in ('diffuse','normal','specular','overlay'): continue
        path=(root/relative).resolve(strict=True); path.relative_to(root)
        image=bpy.data.images.load(str(path),check_existing=False)
        if role not in ('diffuse','overlay'): image.colorspace_settings.name='Non-Color'
        texture=nodes.new('ShaderNodeTexImage'); texture.image=image; used.add(role)
        uv_name=binding.get('uv_map','UV0')
        if binding.get('constant_texture'):
            texture.inputs['Vector'].default_value=(.5,.5,0)
        elif 'meshes' in manifest:
            for obj in objects:
                if mat.name in obj.data.materials and uv_name not in obj.data.uv_layers:
                    raise ValueError('Missing authored '+uv_name+' for '+record['source_name'])
            uv=nodes.new('ShaderNodeUVMap');uv.uv_map=uv_name
            links.new(uv.outputs['UV'],texture.inputs['Vector'])
        if role=='diffuse':
            base_texture=texture
            links.new(texture.outputs['Color'],p.inputs['Base Color'])
            if semantic=='decal' or record.get('preview_cutout'):
                links.new(texture.outputs['Alpha'],p.inputs['Alpha'])
        if role=='overlay': overlay_texture=texture
        if role=='normal':
            normal=nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value=.6
            normal.uv_map=uv_name if 'meshes' in manifest else ''
            inv=nodes.new('ShaderNodeVectorMath');inv.operation='MULTIPLY_ADD'
            inv.inputs[1].default_value=(1,-1,1);inv.inputs[2].default_value=(0,1,0)
            links.new(texture.outputs['Color'],inv.inputs[0])
            links.new(inv.outputs[0],normal.inputs['Color']); links.new(normal.outputs[0],p.inputs['Normal'])
        if role=='specular': links.new(texture.outputs['Color'],p.inputs['Specular IOR Level'])
    if record.get('preview_camo') and base_texture:
        gray=nodes.new('ShaderNodeRGBToBW')
        links.new(base_texture.outputs['Color'],gray.inputs[0])
        pattern=nodes.new('ShaderNodeMapRange')
        pattern.inputs['To Min'].default_value=.45; pattern.inputs['To Max'].default_value=1.4
        links.new(gray.outputs[0],pattern.inputs['Value'])
        tint=nodes.new('ShaderNodeMixRGB'); tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
        tint.inputs[1].default_value=(*record['preview_color'],1)
        links.new(pattern.outputs[0],tint.inputs[2])
        links.new(tint.outputs[0],p.inputs['Base Color'])
        if overlay_texture:
            overlay=nodes.new('ShaderNodeMixRGB')
            links.new(overlay_texture.outputs['Alpha'],overlay.inputs[0])
            links.new(tint.outputs[0],overlay.inputs[1]); links.new(overlay_texture.outputs['Color'],overlay.inputs[2])
            links.new(overlay.outputs[0],p.inputs['Base Color'])
    elif semantic=='paint' and overlay_texture:
        overlay=nodes.new('ShaderNodeMixRGB')
        links.new(overlay_texture.outputs['Alpha'],overlay.inputs[0])
        overlay.inputs[1].default_value=(*record['preview_color'],1)
        links.new(overlay_texture.outputs['Color'],overlay.inputs[2])
        links.new(overlay.outputs[0],p.inputs['Base Color'])

    # Keep tyre/trim material properties: a paint selector does not make rubber
    # into metallic body paint. Multiply the albedo, never normal/spec/alpha.
    tint_color = record.get('preview_diffuse_tint')
    if tint_color is not None and not record.get('preview_camo'):
        if semantic != 'paint' or (base_texture and not overlay_texture):
            base = p.inputs['Base Color']
            tint = nodes.new('ShaderNodeMixRGB'); tint.name='AuthoredDiffuseTint'
            tint.blend_type='MULTIPLY'; tint.inputs[0].default_value=1
            tint.inputs[2].default_value=(*tint_color,1)
            if base.is_linked:
                links.new(base.links[0].from_socket,tint.inputs[1])
            else:
                tint.inputs[1].default_value=(1,1,1,1)
            links.new(tint.outputs[0],base)

corners=[obj.matrix_world@Vector(c) for obj in objects for c in obj.bound_box]
lo=Vector(tuple(min(v[i] for v in corners) for i in range(3)))
hi=Vector(tuple(max(v[i] for v in corners) for i in range(3)))
center=(lo+hi)*.5; dimensions=hi-lo
floor=lo.z; scale=max(dimensions.x,dimensions.y,1)
outdoor=manifest.get('preview_scene')=='runway'
ocean=manifest.get('preview_scene')=='ocean'
daylight=outdoor or ocean

def vessel_waterline(bottom,top,length):
    # Most authored GTA hulls straddle their local Z=0 waterline. If an addon
    # uses a different origin, use a bounded draft estimate, never half of a
    # sailboat's mast height. Move the sea, not the vessel or its decals.
    height=top-bottom
    if bottom<0<top and -bottom<=height*.65:return 0.0
    return bottom+min(height*.20,length*.06)

waterline=vessel_waterline(lo.z,hi.z,scale) if ocean else None

def textured_surface(name,asset):
    mat,p=material(name,(.2,.2,.2),.85)
    nodes=mat.node_tree.nodes; links=mat.node_tree.links
    for kind,socket in (('diff','Base Color'),('rough','Roughness'),('nor_gl','Normal')):
        texture=nodes.new('ShaderNodeTexImage')
        texture.image=bpy.data.images.load(str(root/(asset+'_'+kind+'_2k.jpg')))
        if kind!='diff': texture.image.colorspace_settings.name='Non-Color'
        if kind=='nor_gl':
            normal=nodes.new('ShaderNodeNormalMap'); normal.inputs['Strength'].default_value=.7
            links.new(texture.outputs['Color'],normal.inputs['Color']); links.new(normal.outputs[0],p.inputs[socket])
        elif kind=='diff' and asset=='asphalt_01':
            # Neutral dark asphalt, with enlarged aggregate readable at card size.
            gray=nodes.new('ShaderNodeRGBToBW'); shade=nodes.new('ShaderNodeMath'); shade.operation='MULTIPLY'
            shade.inputs[1].default_value=.32
            links.new(texture.outputs['Color'],gray.inputs[0]); links.new(gray.outputs[0],shade.inputs[0])
            links.new(shade.outputs[0],p.inputs[socket])
        else: links.new(texture.outputs['Color'],p.inputs[socket])
    return mat

def planar_uv(obj,axes,meters):
    layer=obj.data.uv_layers.active or obj.data.uv_layers.new()
    for loop in obj.data.loops:
        v=obj.data.vertices[loop.vertex_index].co
        layer.data[loop.index].uv=(v[axes[0]]/meters,v[axes[1]]/meters)

bpy.ops.mesh.primitive_plane_add(size=scale*30,location=(center.x,center.y,floor))
ground=bpy.context.object; ground.name='Asphalt floor'
planar_uv(ground,(0,1),6)
ground.data.materials.append(textured_surface('Dry aggregate asphalt','asphalt_01'))
bpy.ops.mesh.primitive_cube_add(size=1,location=(center.x,hi.y+scale*.65,floor+scale*2))
wall=bpy.context.object; wall.name='Clean concrete wall'; wall.dimensions=(scale*30,.2,scale*4)
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
planar_uv(wall,(0,2),4)
wall.data.materials.append(textured_surface('Concrete panels','concrete'))
wall.pass_index=2

# Sparse structural steel gives the backdrop depth and real contact shadows.
# It stays behind the vehicle bounds, never in the subject's footprint.
steel,_=material('Exposed silver structural steel',(.36,.40,.44),.28,.95)
def beam(name,location,dimensions):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    obj=bpy.context.object; obj.name=name; obj.dimensions=dimensions
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(steel)
    obj.pass_index=2
    bevel=obj.modifiers.new('Soft steel edges','BEVEL'); bevel.width=scale*.002; bevel.segments=2
    return obj
def member(name,start,end,width,depth,flanged=False):
    start,end=Vector(start),Vector(end)
    axis=end-start; rotation=axis.to_track_quat('Z','Y'); middle=(start+end)*.5
    sections=((0,width,depth),) if not flanged else (
        (0,width*.14,depth),(-depth*.44,width,depth*.12),(depth*.44,width,depth*.12))
    for index,(offset,w,d) in enumerate(sections):
        obj=beam(name+' section '+str(index),middle+rotation@Vector((0,offset,0)),(w,d,axis.length))
        obj.rotation_mode='QUATERNION'; obj.rotation_quaternion=rotation

back_y=wall.location.y-scale*.09
bay=scale*.72; rail_z=floor+scale*.32
for index in range(-5,6):
    x=center.x+bay*(index+.35)
    member('I-beam upright '+str(index),(x,back_y,floor),(x,back_y,floor+scale*4),scale*.04,scale*.05,True)
    beam('Upright base plate '+str(index),(x,back_y,floor+.025),(scale*.08,scale*.09,.05))
    if index==5:continue
    member('Horizontal crossbeam '+str(index),(x,back_y,rail_z),(x+bay,back_y,rail_z),scale*.035,scale*.045,True)
    # Low braced bays remain visible in the catalog crop (not above the camera).
    for side in (0,1):
        member('Diagonal brace '+str(index)+' '+str(side),
            (x,back_y-scale*.025,floor+scale*(.05 if side==0 else .30)),
            (x+bay,back_y-scale*.025,floor+scale*(.30 if side==0 else .05)),scale*.016,scale*.014)

if outdoor:
    # An aircraft is parked, engines off. Keep real rotor blades, runway contact
    # shadows and open sky; never squeeze it into the road-vehicle backdrop.
    for obj in list(bpy.context.scene.objects):
        if obj.pass_index==2: bpy.data.objects.remove(obj,do_unlink=True)
    ground.name='Runway asphalt'; ground.scale=(.08,1,1)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    planar_uv(ground,(0,1),6)
    asphalt=ground.data.materials[0]; nodes=asphalt.node_tree.nodes; links=asphalt.node_tree.links
    coord=nodes.new('ShaderNodeTexCoord')
    variation=nodes.new('ShaderNodeTexNoise');variation.inputs['Scale'].default_value=.32
    variation.inputs['Detail'].default_value=5;variation.inputs['Roughness'].default_value=.75
    links.new(coord.outputs['Object'],variation.inputs['Vector'])
    tones=nodes.new('ShaderNodeMapRange');tones.inputs['To Min'].default_value=.55;tones.inputs['To Max'].default_value=1.25
    links.new(variation.outputs['Fac'],tones.inputs[0])
    base=nodes.get('Principled BSDF').inputs['Base Color'];original=base.links[0].from_socket
    mottled=nodes.new('ShaderNodeMixRGB');mottled.blend_type='MULTIPLY';mottled.inputs[0].default_value=1
    links.new(original,mottled.inputs[1]);links.new(tones.outputs[0],mottled.inputs[2]);links.new(mottled.outputs[0],base)
    grass,_=material('Dry airfield grass',(.12,.16,.065),.98)
    nodes=grass.node_tree.nodes; links=grass.node_tree.links
    noise=nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=.18
    noise.inputs['Detail'].default_value=5;noise.inputs['Roughness'].default_value=.8
    coord=nodes.new('ShaderNodeTexCoord'); links.new(coord.outputs['Object'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.22;ramp.color_ramp.elements[0].color=(.025,.045,.01,1)
    ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=(.18,.12,.035,1)
    ramp.color_ramp.elements.new(.48).color=(.075,.12,.025,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    links.new(ramp.outputs[0],nodes.get('Principled BSDF').inputs['Base Color'])
    fine=nodes.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=45;fine.inputs['Detail'].default_value=3
    links.new(coord.outputs['Object'],fine.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.5;bump.inputs['Distance'].default_value=.025
    links.new(fine.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],nodes.get('Principled BSDF').inputs['Normal'])
    bpy.ops.mesh.primitive_plane_add(size=scale*180,location=(center.x,center.y,floor-.015))
    bpy.context.object.name='Airfield terrain'; bpy.context.object.data.materials.append(grass)
    paint,_=material('Runway marking paint',(.72,.73,.69),.85)
    def marking(name,x,y,width,length):
        bpy.ops.mesh.primitive_plane_add(size=1,location=(x,y,floor+.003))
        obj=bpy.context.object; obj.name=name; obj.scale=(width,length,1);obj.data.materials.append(paint)
    # Centerline beside the subject keeps markings visible without disguising
    # landing-gear contact. Runway edges recede into the open horizon.
    line_x=center.x+scale*.55
    for n in range(-14,15):
        marking('Runway centerline',line_x,center.y+n*scale*1.7,.18,scale*.7)
    for side in (-1,1):
        marking('Runway edge',center.x+side*scale*1.12,center.y,.2,scale*30)
    for n in range(-4,5):
        marking('Runway threshold',center.x+n*scale*.19,center.y+scale*3.4,scale*.075,scale*.7)
    housing,_=material('Runway light housing',(.05,.06,.065),.4,.7)
    lens,p=material('Runway edge light lens',(.55,.48,.23),.24,.1)
    p.inputs['Emission Color'].default_value=(1,.78,.36,1);p.inputs['Emission Strength'].default_value=3
    for side in (-1,1):
        for n in range(-10,15):
            x=center.x+side*scale*1.17;y=center.y+n*scale*1.1
            for name,z,radius,height,mat in (
                ('Runway light pedestal',.11,.06,.22,housing),
                ('Runway edge lamp',.27,.11,.1,lens)):
                bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=radius,depth=height,location=(x,y,floor+z))
                bpy.context.object.name=name;bpy.context.object.data.materials.append(mat)

    # General-aviation layout: hangars face a shared apron, beyond a parallel
    # taxiway and grass separation. Buildings use metre dimensions, not aircraft
    # scaling. Only their setback increases for unusually large aircraft.
    cladding,p=material('Airport corrugated metal',(.075,.095,.11),.72,.3)
    nodes=cladding.node_tree.nodes;links=cladding.node_tree.links
    wave=nodes.new('ShaderNodeTexWave');wave.bands_direction='X';wave.inputs['Scale'].default_value=12
    coord=nodes.new('ShaderNodeTexCoord');links.new(coord.outputs['Object'],wave.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.03;bump.inputs['Strength'].default_value=.35
    links.new(wave.outputs['Color'],bump.inputs['Height']);links.new(bump.outputs[0],p.inputs['Normal'])
    roof_mat,_=material('Hangar roof metal',(.07,.085,.10),.55,.6)
    door_mat,_=material('Hangar sliding doors',(.14,.16,.16),.65,.35)
    trim,_=material('Hangar blue grey trim',(.035,.075,.095),.55,.4)
    windows,p=material('Hangar clerestory windows',(.035,.065,.075),.25,.35)
    p.inputs['Coat Weight'].default_value=.4
    def airport_box(name,location,dimensions,mat):
        bpy.ops.mesh.primitive_cube_add(size=1,location=location)
        obj=bpy.context.object;obj.name=name;obj.dimensions=dimensions
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(mat);obj.pass_index=2
        return obj
    hx=center.x-max(80,scale*4.8)
    taxi_x=center.x-max(42,scale*2.5)
    start_y=center.y+max(75,scale*4)
    apron_front=hx+12
    apron,_=material('Weathered apron concrete',(.21,.22,.215),.94)
    nodes=apron.node_tree.nodes;links=apron.node_tree.links
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1.5
    ramp=nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(.14,.15,.145,1)
    ramp.color_ramp.elements[1].color=(.28,.29,.27,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    links.new(ramp.outputs[0],nodes.get('Principled BSDF').inputs['Base Color'])
    def airport_paving(name,x,y,w,d,mat):
        bpy.ops.mesh.primitive_plane_add(size=1,location=(x,y,floor+.006))
        obj=bpy.context.object;obj.name=name;obj.scale=(w,d,1)
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        obj.data.materials.append(mat);obj.pass_index=2;planar_uv(obj,(0,1),6)
    airport_paving('Shared hangar apron',(apron_front+taxi_x)/2,start_y+40,
        taxi_x-apron_front+10,120,apron)
    airport_paving('Parallel taxiway',taxi_x,center.y,12,scale*30,asphalt)
    # A single paved connector joins the apron/taxiway to the runway, rather
    # than leaving hangar doors opening onto grass.
    connector_y=start_y+100
    airport_paving('Runway taxiway connector',(taxi_x+center.x)/2,connector_y,
        center.x-taxi_x,12,asphalt)
    yellow,_=material('Taxiway yellow paint',(.55,.35,.045),.9)
    airport_paving('Taxiway guide',taxi_x,center.y,.15,scale*30,yellow)
    # Avoid coplanar markings on the apron/taxiway.
    bpy.context.object.location.z+=.002
    for index in range(3):
        x=hx;y=start_y+index*40;w=28;d=24;h=7.5
        airport_box('Airport hangar '+str(index),(x,y,floor+h/2),(d,w,h),cladding)
        front=x+d/2+.04
        airport_box('Hangar foundation',(x,y,floor+.22),(d+.15,w+.15,.44),apron)
        # Six full-height sliding leaves with visible seams and upper glazing.
        for leaf in range(6):
            py=y-11.25+leaf*4.5
            airport_box('Sliding door leaf',(front,py,floor+3.15),(.12,4.44,6.3),door_mat)
            airport_box('Door window strip',(front+.075,py,floor+5.15),(.04,4.0,.65),windows)
            airport_box('Door vertical stile',(front+.09,py-2.15,floor+3.15),(.09,.09,6.3),roof_mat)
        airport_box('Door track canopy',(front+.35,y,floor+6.65),(.8,w+.45,.3),trim)
        airport_box('Hangar fascia band',(front,y,floor+7.05),(.15,w,.4),trim)
        # Shallow gable roof with eaves, closed ends and standing seams.
        vertices=[(x+dx*(d+.6)/2,y+dy*(w+.8)/2,floor+h)
            for dx,dy in ((1,-1),(1,1),(-1,1),(-1,-1))]
        vertices += [(x+(d+.6)/2,y,floor+h+1.4),(x-(d+.6)/2,y,floor+h+1.4)]
        mesh=bpy.data.meshes.new('Hangar roof');mesh.from_pydata(vertices,[],
            [(0,4,5,3),(4,1,2,5),(0,1,4),(3,5,2)]);mesh.update()
        obj=bpy.data.objects.new('Low pitched metal roof',mesh);bpy.context.collection.objects.link(obj)
        obj.data.materials.append(roof_mat);obj.pass_index=2
        for seam in range(-6,7):
            py=y+seam*2
            z=floor+h+1.4*(1-abs(seam*2)/((w+.8)/2))+.035
            airport_box('Roof standing seam',(x,py,z),(d+.65,.065,.07),roof_mat)
        for rib in range(-11,12,2):
            airport_box('Side cladding rib',(x+rib,y-w/2-.025,floor+h/2),(.065,.06,h),door_mat)
        airport_box('Side fascia band',(x,y-w/2-.055,floor+6.8),(d,.09,.45),trim)
        for pane in range(-4,5):
            airport_box('Side clerestory window',(x+pane*2.3,y-w/2-.07,floor+5.7),(2.0,.08,.85),windows)
        airport_box('Hangar personnel door',(x+8,y-w/2-.05,floor+1.1),(1.0,.08,2.2),trim)
        airport_box('Hangar roof ridge',(x,y,floor+h+1.43),(d+.7,.25,.09),roof_mat)

    # The modest tower belongs to the apron complex, not the runway strip.
    tx=hx+7;ty=start_y+130
    airport_box('Tower operations building',(tx-4,ty,floor+1.7),(12,9,3.4),cladding)
    airport_box('Control tower stem',(tx,ty,floor+6.8),(3.5,3.5,13.6),cladding)
    for name,z,radius,height,mat in (
        ('Tower observation deck',13.4,3.5,.35,roof_mat),
        ('Control tower glazed cabin',14.7,3.1,2.3,windows),
        ('Control tower roof',16.0,3.6,.3,roof_mat)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=radius,depth=height,
            location=(tx,ty,floor+z))
        obj=bpy.context.object;obj.name=name;obj.data.materials.append(mat);obj.pass_index=2
    for corner in range(8):
        angle=corner*math.tau/8
        airport_box('Tower window mullion',(tx+3.1*math.cos(angle),ty+3.1*math.sin(angle),floor+14.7),(.12,.12,2.3),roof_mat)
    airport_box('Tower aerial',(tx,ty,floor+17.5),(.07,.07,3),roof_mat)

    # A windsock on the grass, clear of the runway and parked aircraft.
    wx=center.x-max(32,scale*1.7);wy=center.y+scale*5
    airport_box('Windsock concrete footing',(wx,wy,floor+.12),(.8,.8,.24),apron)
    airport_box('Windsock mast',(wx,wy,floor+3.25),(.1,.1,6.5),roof_mat)
    orange,_=material('Windsock orange fabric',(.65,.14,.025),.95)
    white,_=material('Windsock white fabric',(.65,.65,.58),.95)
    # Open tapered fabric tube with orange/white bands, gently sagging downwind.
    vertices=[];faces=[]
    for ring in range(6):
        t=ring/5;radius=.45*(1-t)+.15*t
        for point_index in range(16):
            a=math.tau*point_index/16
            vertices.append((wx-3.6*t,wy+radius*math.cos(a),floor+6.5-.35*t*t+radius*math.sin(a)))
    for ring in range(5):
        for point_index in range(16):
            j=(point_index+1)%16
            faces.append((ring*16+point_index,ring*16+j,(ring+1)*16+j,(ring+1)*16+point_index))
    mesh=bpy.data.meshes.new('Windsock fabric');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('Striped windsock',mesh);bpy.context.collection.objects.link(obj)
    obj.data.materials.append(orange);obj.data.materials.append(white);obj.pass_index=2
    for face in mesh.polygons:face.material_index=(face.index//16)%2

    # Far skyline: desaturated low-rise blocks with a few taller landmarks.
    # Deterministic metre-scale geometry, deliberately without sharp facade
    # detail: haze and depth of field keep it subordinate to the airfield.
    city_mats=[]
    for tint in ((.23,.27,.285),(.27,.295,.30),(.20,.25,.27)):
        mat,p=material('Distant city haze',tint,.9)
        p.inputs['Emission Color'].default_value=(*tint,1)
        p.inputs['Emission Strength'].default_value=.18;city_mats.append(mat)
    city_y=center.y+max(500,scale*28)
    for index in range(35):
        cx=center.x-850+index*34
        cy=city_y+(index*37%100)
        width=14+(index*7%17);depth=16+(index*11%16)
        height=10+(index*13%22)+(20 if index in (9,17,24) else 0)
        mat=city_mats[index%3]
        airport_box('Distant city building',(cx,cy,floor+height/2),(width,depth,height),mat)
        if index%4==0:
            airport_box('City rooftop plant',(cx+width*.1,cy,floor+height+1.3),(width*.5,depth*.55,2.6),mat)

if ocean:
    for obj in list(bpy.context.scene.objects):
        if obj.pass_index==2 or obj==ground:bpy.data.objects.remove(obj,do_unlink=True)
    water,p=material('Ocean water',(.012,.065,.085),.16)
    p.inputs['IOR'].default_value=1.333;p.inputs['Transmission Weight'].default_value=.4
    p.inputs['Coat Weight'].default_value=.2;p.inputs['Coat Roughness'].default_value=.12
    nodes=water.node_tree.nodes;links=water.node_tree.links
    coord=nodes.new('ShaderNodeTexCoord')
    swell=nodes.new('ShaderNodeTexNoise');swell.inputs['Scale'].default_value=1.8
    swell.inputs['Detail'].default_value=3;swell.inputs['Roughness'].default_value=.65
    ripples=nodes.new('ShaderNodeTexNoise');ripples.inputs['Scale'].default_value=22
    ripples.inputs['Detail'].default_value=2
    for noise in (swell,ripples):links.new(coord.outputs['Object'],noise.inputs['Vector'])
    coarse=nodes.new('ShaderNodeBump');coarse.inputs['Strength'].default_value=.3;coarse.inputs['Distance'].default_value=.10
    fine=nodes.new('ShaderNodeBump');fine.inputs['Strength'].default_value=.18;fine.inputs['Distance'].default_value=.025
    links.new(swell.outputs['Fac'],coarse.inputs['Height'])
    links.new(ripples.outputs['Fac'],fine.inputs['Height']);links.new(coarse.outputs[0],fine.inputs['Normal'])
    links.new(fine.outputs[0],p.inputs['Normal'])
    # Bounded near-water geometry for contact and gentle silhouette waves;
    # world-coordinate shader ripples continue seamlessly to the distant sea.
    span=max(100,scale*8);steps=128;vertices=[];faces=[]
    for iy in range(steps+1):
        y=-span/2+span*iy/steps
        for ix in range(steps+1):
            x=-span/2+span*ix/steps
            fade=max(0,1-(max(abs(x),abs(y))/(span/2))**8)
            z=(.055*math.sin(x*.65+y*.28)+.025*math.sin(y*1.4-x*.3))*fade
            vertices.append((center.x+x,center.y+y,waterline+z))
    for iy in range(steps):
        for ix in range(steps):
            a=iy*(steps+1)+ix;faces.append((a,a+1,a+steps+2,a+steps+1))
    mesh=bpy.data.meshes.new('Gentle ocean swells');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('Near ocean surface',mesh);bpy.context.collection.objects.link(obj)
    obj.data.materials.append(water)
    for poly in mesh.polygons:poly.use_smooth=True
    # Ring leaves the central mesh uncovered: no overlapping/coplanar surfaces.
    inner=span/2;outer=50000
    vertices=[(center.x+x,center.y+y,waterline) for r in (inner,outer)
        for x,y in ((-r,-r),(r,-r),(r,r),(-r,r))]
    mesh=bpy.data.meshes.new('Ocean horizon');mesh.from_pydata(vertices,[],
        [(i+4,(i+1)%4+4,(i+1)%4,i) for i in range(4)]);mesh.update()
    obj=bpy.data.objects.new('Open sea horizon',mesh);bpy.context.collection.objects.link(obj);obj.data.materials.append(water)
    deep,_=material('Deep ocean tint',(.006,.022,.028),1)
    bpy.ops.mesh.primitive_plane_add(size=100000,location=(center.x,center.y,waterline-15))
    bpy.context.object.name='Deep water absorption backdrop';bpy.context.object.data.materials.append(deep)

scene=bpy.context.scene
scene.render.engine='CYCLES'; scene.cycles.samples=96; scene.cycles.use_denoising=True
scene.cycles.max_bounces=7; scene.cycles.transparent_max_bounces=8
prefs=bpy.context.preferences.addons['cycles'].preferences
device='CPU'
for backend in ('OPTIX','CUDA','HIP','ONEAPI','METAL'):
    try:
        prefs.compute_device_type=backend; prefs.get_devices()
        devices=[d for d in prefs.devices if d.type!='CPU']
        if devices:
            for d in prefs.devices: d.use=d.type!='CPU'
            scene.cycles.device='GPU'; device=backend; break
    except Exception: pass
scene.render.resolution_x=1280; scene.render.resolution_y=800; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'; scene.render.filepath=str(root/'render.png')
scene.world=bpy.data.worlds.new('Soft daylight'); scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.55,.65,.8,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.065
if daylight:
    sky=scene.world.node_tree.nodes.new('ShaderNodeTexSky'); sky.sky_type='NISHITA'
    sky.sun_elevation=math.radians(28); sky.sun_rotation=math.radians(140)
    sky.sun_size=math.radians(1.5); sky.air_density=1; sky.dust_density=.6
    scene.world.node_tree.links.new(sky.outputs['Color'],scene.world.node_tree.nodes['Background'].inputs[0])
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.12
def point(obj,target): obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
target=Vector((center.x,center.y,floor+dimensions.z*.43))
if ocean:target.z=waterline+(hi.z-waterline)*.4
camera_data=bpy.data.cameras.new('Catalog camera'); camera=bpy.data.objects.new('Catalog camera',camera_data)
bpy.context.collection.objects.link(camera); camera_data.lens=52
if ocean:camera_data.clip_end=100000
direction=Vector((.56,-.78,.14 if ocean else (.10 if outdoor else .28))).normalized()
camera.location=target+direction*dimensions.length*1.75; point(camera,target); scene.camera=camera
if daylight:
    # Fit all authored blades/wings, rather than shrinking aircraft by their
    # diagonal length. Perspective framing leaves an 18% safety margin.
    right=Vector((direction.y,-direction.x,0)).normalized()
    up=direction.cross(right).normalized()
    half_x=camera_data.sensor_width/(2*camera_data.lens)
    half_y=half_x*800/1280
    distance=max((v-target).dot(direction)+max(abs((v-target).dot(right))/half_x,
        abs((v-target).dot(up))/half_y)/.82 for v in corners)
    camera.location=target+direction*distance;point(camera,target)
# Focus spans the entire vehicle. Bound the largest vehicle circle of confusion
# to 1.25 output pixels; more distant wall/supports receive natural optical blur.
depths=[(camera.location-v).dot(direction) for v in corners]
near,far=min(depths),max(depths)
focus=2*near*far/(near+far)
focal=camera_data.lens/1000; sensor=camera_data.sensor_width/1000
required=focal*focal/(focus-focal)*max(abs(d-focus)/d for d in depths)*1280/sensor/1.25
camera_data.dof.use_dof=True; camera_data.dof.focus_distance=focus
camera_data.dof.aperture_fstop=max(1.4,required)
camera_data.dof.aperture_blades=8
for name,offset,power,size,color in (
    ('Warm key',(-.8,-.6,1.4),1700,.7,(1,.94,.86)),
    ('Cool fill',(1,-.1,.8),220,.65,(.82,.9,1)),
    ('Roof strip',(.1,.55,1.4),1900,1.0,(1,1,1))):
    light=bpy.data.lights.new(name,'AREA'); light.energy=power*(scale/4)**2*(.18 if daylight else 1)
    light.shape='RECTANGLE'; light.size=scale*size; light.size_y=scale*.15; light.color=color
    obj=bpy.data.objects.new(name,light); bpy.context.collection.objects.link(obj)
    obj.location=target+Vector(offset)*scale; point(obj,target)
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
# Background-only normalized blur: exclude the vehicle and asphalt from both
# the output mask and blur input, preventing vehicle-colored halos at silhouettes.
scene.view_layers[0].use_pass_object_index=True
scene.view_layers[0].use_pass_z=True
scene.use_nodes=True; tree=scene.node_tree; tree.nodes.clear()
layers=tree.nodes.new('CompositorNodeRLayers')
mask=tree.nodes.new('CompositorNodeIDMask'); mask.index=2; mask.use_antialiasing=True
tree.links.new(layers.outputs['IndexOB'],mask.inputs[0])
mask_socket=mask.outputs[0]
if daylight:
    # Distance mask leaves the complete aircraft and its immediate contact
    # shadows sharp. Distant terrain, runway lights and sky share the blur.
    distant=tree.nodes.new('CompositorNodeMath');distant.operation='GREATER_THAN'
    distant.inputs[1].default_value=far+scale*.8
    tree.links.new(layers.outputs['Depth'],distant.inputs[0])
    combined=tree.nodes.new('CompositorNodeMath');combined.operation='MAXIMUM'
    tree.links.new(distant.outputs[0],combined.inputs[0]);tree.links.new(mask_socket,combined.inputs[1])
    mask_socket=combined.outputs[0]
weighted=tree.nodes.new('CompositorNodeMixRGB'); weighted.blend_type='MULTIPLY'; weighted.inputs[0].default_value=1
tree.links.new(layers.outputs['Image'],weighted.inputs[1]); tree.links.new(mask_socket,weighted.inputs[2])
def background_blur(socket):
    node=tree.nodes.new('CompositorNodeBlur'); node.filter_type='GAUSS'; node.size_x=14 if daylight else 16; node.size_y=node.size_x
    tree.links.new(socket,node.inputs['Image']); return node.outputs['Image']
colors=background_blur(weighted.outputs[0]); coverage=background_blur(mask_socket)
safe=tree.nodes.new('CompositorNodeMath'); safe.operation='MAXIMUM'; safe.inputs[1].default_value=.00001
tree.links.new(coverage,safe.inputs[0])
normalized=tree.nodes.new('CompositorNodeMixRGB'); normalized.blend_type='DIVIDE'; normalized.inputs[0].default_value=1
tree.links.new(colors,normalized.inputs[1]); tree.links.new(safe.outputs[0],normalized.inputs[2])
mix=tree.nodes.new('CompositorNodeMixRGB')
tree.links.new(mask_socket,mix.inputs[0]); tree.links.new(layers.outputs['Image'],mix.inputs[1]); tree.links.new(normalized.outputs[0],mix.inputs[2])
output=tree.nodes.new('CompositorNodeComposite'); tree.links.new(mix.outputs[0],output.inputs['Image'])
# Framing must never independently resize a body or decal object. Only the
# camera moves; authored relative placement and texture UVs remain intact.
for obj in objects:
    if any(abs(obj.matrix_world[i][j]-subject_transforms[obj.name][i][j])>1e-7 for i in range(4) for j in range(4)):
        raise ValueError('Vehicle/decal transform changed during studio setup: '+obj.name)
bpy.ops.render.render(write_still=True)
(root/'result.json').write_text(json.dumps({'engine':'Cycles','device':device,'samples':96,'version':bpy.app.version_string,'paint':manifest['preview_paint'],
    'backdrop':'ocean' if ocean else ('outdoor-runway' if outdoor else 'asphalt-concrete-braced-steel'),'background_blur_pixels':14 if daylight else 16,
    'waterline_z':waterline,'waterline_method':'authored-origin-or-bounded-draft' if ocean else None,
    'runway_lights':50 if outdoor else 0,'camera_elevation_degrees':math.degrees(math.asin(direction.z)),
    'airport_background':bool(outdoor),
    'airport_details':['hangar-apron','parallel-taxiway','control-tower','windsock','distant-city'] if outdoor else [],
    'subject_scaling':'authored-dimensions-camera-fit',
    'focus_distance':focus,'fstop':camera_data.dof.aperture_fstop}))
'''
