"""Trusted Cycles weapon and equipment studio; inputs contain no executable code."""
SCENE_SCRIPT = r'''
import bpy, json, sys, math, random
from pathlib import Path
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]).resolve(strict=True)
manifest=json.loads((root/'scene.json').read_text())
crate=manifest.get('preview_scene')=='ammo-crate'
bpy.ops.wm.read_factory_settings(use_empty=True)

def texture(nodes,name,color=True):
    path=(root/name).resolve(strict=True);path.relative_to(root)
    node=nodes.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(path))
    if not color: node.image.colorspace_settings.name='Non-Color'
    return node

def linear(c): return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4

catalog_parts=[]
for i,row in enumerate(manifest['meshes']):
    mesh=bpy.data.meshes.new('Mesh '+str(i));mesh.from_pydata(row['vertices'],[],row['triangles']);mesh.update()
    uv=mesh.uv_layers.new()
    for loop in mesh.loops: uv.data[loop.index].uv=row['uv'][loop.vertex_index]
    for face in mesh.polygons: face.use_smooth=True
    obj=bpy.data.objects.new('Catalog part '+str(i),mesh);bpy.context.collection.objects.link(obj)
    catalog_parts.append(obj)
    mat=bpy.data.materials.new('Authored material '+str(i));mat.use_nodes=True
    mesh.materials.append(mat);nodes=mat.node_tree.nodes;links=mat.node_tree.links
    p=nodes.get('Principled BSDF')
    p.inputs['Roughness'].default_value=.43 if row['category']=='weapons' else .72
    p.inputs['Metallic'].default_value=.25 if row['category']=='weapons' else 0
    p.inputs['Specular IOR Level'].default_value=.25
    diff=texture(nodes,row['diffuse']);links.new(diff.outputs['Color'],p.inputs['Base Color'])
    links.new(diff.outputs['Alpha'],p.inputs['Alpha'])
    if row.get('tints'):
        attr=mesh.color_attributes.new(name='Authored tint',type='FLOAT_COLOR',domain='POINT')
        for dest,rgb in zip(attr.data,row['tints']): dest.color=(*map(linear,rgb),1)
        color=nodes.new('ShaderNodeVertexColor');color.layer_name='Authored tint'
        mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1
        links.new(diff.outputs['Color'],mix.inputs[1]);links.new(color.outputs['Color'],mix.inputs[2])
        links.new(mix.outputs[0],p.inputs['Base Color'])
    if row.get('normal'):
        tex=texture(nodes,row['normal'],False)
        # Native maps use the DirectX green channel; Blender uses OpenGL normals.
        inv=nodes.new('ShaderNodeVectorMath');inv.operation='MULTIPLY_ADD'
        inv.inputs[1].default_value=(1,-1,1);inv.inputs[2].default_value=(0,1,0)
        links.new(tex.outputs['Color'],inv.inputs[0])
        normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.55
        links.new(inv.outputs[0],normal.inputs['Color']);links.new(normal.outputs[0],p.inputs['Normal'])
    if row.get('specular'):
        tex=texture(nodes,row['specular'],False)
        remap=nodes.new('ShaderNodeMapRange');remap.inputs['To Min'].default_value=.15;remap.inputs['To Max'].default_value=.4
        links.new(tex.outputs['Color'],remap.inputs['Value']);links.new(remap.outputs[0],p.inputs['Specular IOR Level'])

bpy.ops.mesh.primitive_plane_add(size=2,location=(0,0,manifest['board_z']))
board=bpy.context.object;board.name='Pegboard backdrop';board.scale=(1.7,1.0625,1)
mat=bpy.data.materials.new('Warm neutral pegboard');mat.use_nodes=True;board.data.materials.append(mat)
nodes=mat.node_tree.nodes;links=mat.node_tree.links;p=nodes.get('Principled BSDF')
tex=texture(nodes,'pegboard.png');links.new(tex.outputs['Color'],p.inputs['Base Color'])
p.inputs['Roughness'].default_value=.88
bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.35;bump.inputs['Distance'].default_value=.007
links.new(tex.outputs['Color'],bump.inputs['Height']);links.new(bump.outputs[0],p.inputs['Normal'])

if crate:
    bpy.data.objects.remove(board,do_unlink=True)
    # Linked instances share meshes/materials and preserve every component's
    # relative transform; no new texture or geometry copies are allocated.
    for number,offset in enumerate(manifest.get('display_copies',[])):
        for original in catalog_parts:
            copy=original.copy();copy.name='Stocked throwable %d %s'%(number,original.name)
            bpy.context.collection.objects.link(copy);copy.location=Vector(offset)
    def surface(name,color,roughness=.8,metal=0):
        mat=bpy.data.materials.new(name);mat.use_nodes=True
        p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1)
        p.inputs['Roughness'].default_value=roughness;p.inputs['Metallic'].default_value=metal
        return mat
    wood=surface('Worn olive painted wood',(.20,.19,.085))
    metal=surface('Aged steel hardware',(.075,.085,.07),.5,.8)
    rope=surface('Natural rope',(.25,.19,.10),.95)
    ink=surface('Faded black stencil',(.025,.03,.02),1)
    concrete=surface('Warehouse concrete',(.12,.13,.125),.93)
    # Real scanned wood/concrete maps replace the earlier smooth procedural
    # approximation. Planks get separate UV crops and geometric edge chips.
    for mat,asset in ((wood,'wood_planks'),(concrete,'concrete')):
        nodes=mat.node_tree.nodes;links=mat.node_tree.links;p=nodes.get('Principled BSDF')
        diff=texture(nodes,asset+'_diff_2k.jpg')
        if mat==wood:
            tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=.68
            tint.inputs[2].default_value=(.42,.45,.19,1);links.new(diff.outputs[0],tint.inputs[1]);links.new(tint.outputs[0],p.inputs['Base Color'])
        else:links.new(diff.outputs[0],p.inputs['Base Color'])
        rough=texture(nodes,asset+'_rough_2k.jpg',False);links.new(rough.outputs[0],p.inputs['Roughness'])
        normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.85
        tex=texture(nodes,asset+'_nor_gl_2k.jpg',False);links.new(tex.outputs[0],normal.inputs['Color']);links.new(normal.outputs[0],p.inputs['Normal'])
    bare=wood.copy();bare.name='Exposed chipped timber'
    nodes=bare.node_tree.nodes;p=nodes.get('Principled BSDF')
    tex=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image.name.startswith('wood_planks_diff'))
    bare.node_tree.links.new(tex.outputs[0],p.inputs['Base Color'])
    rng=random.Random(407)
    def box(name,pos,size,mat,edge=.004):
        bpy.ops.mesh.primitive_cube_add(size=1,location=pos)
        obj=bpy.context.object;obj.name=name;obj.dimensions=size
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);obj.data.materials.append(mat)
        uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
        offset=rng.random()*.7
        for poly in obj.data.polygons:
            axis=max(range(3),key=lambda a:abs(poly.normal[a]));axes=[a for a in range(3) if a!=axis]
            for index in poly.loop_indices:
                v=obj.data.vertices[obj.data.loops[index].vertex_index].co
                uv.data[index].uv=(v[axes[0]]*.55+offset,v[axes[1]]*.22+.23+offset*.1) if mat in (wood,bare) else (v[axes[0]]/2,v[axes[1]]/2)
        bevel=obj.modifiers.new('Worn edges','BEVEL');bevel.width=edge;bevel.segments=3
        return obj
    def crate_box(base,closed,width=1.3,depth=.95):
        box('Crate bottom',(0,0,base+.025),(width,depth,.05),bare)
        for level in range(3):
            z=base+.12+level*.13
            for side in (-1,1):
                box('Side plank',(0,side*depth/2,z),(width,.045,.126),wood)
                box('End plank',(side*width/2,0,z),(.045,depth,.126),wood)
        if closed:
            for n in range(5):box('Lid plank',(0,-depth*.4+n*depth*.2,base+.45),(width,depth*.2-.004,.04),wood)
        for side in (-1,1):
            for front in (-1,1):
                box('Corner batten',(side*(width/2-.09),front*(depth/2+.029),base+.245),(.085,.04,.45),wood)
                for height in (.09,.39):
                    bpy.ops.mesh.primitive_uv_sphere_add(segments=8,ring_count=4,radius=.009,location=(side*(width/2-.09),front*(depth/2+.053),base+height))
                    bpy.context.object.name='Recessed nail';bpy.context.object.scale=(1,.35,1);bpy.context.object.data.materials.append(metal)
            for chip in range(12):
                x=rng.uniform(-width*.46,width*.46);z=base+rng.choice((.059,.185,.319,.445))+rng.uniform(-.004,.004)
                scar=box('Chipped plank edge',(x,side*(depth/2+.024),z),(rng.uniform(.015,.065),.001,rng.uniform(.003,.009)),bare)
                scar.rotation_euler.y=rng.uniform(-.15,.15)
        box('Front latch',(0,-depth/2-.026,base+.395),(.07,.018,.11),metal)
    crate_box(0,True,1.42,1.04)
    for x in (-.55,.55):box('Lower lid support batten',(x,0,.48),(.09,1.05,.04),bare)
    crate_box(.49,not manifest['crate_open'])
    if manifest['crate_open']:
        for x in (-.22,.22):box('Organizer cross divider',(x,0,.705),(.018,.88,.32),bare)
        box('Organizer row divider',(0,0,.705),(1.24,.018,.32),bare)
        # Raise small round items on a visible packing insert, not in midair.
        support=manifest['support_z']
        if support>.544:
            for dx,dy,_ in [(0,0,0)]+manifest.get('display_copies',[]):
                box('Packing insert',(dx,-.205+dy,(.54+support)/2),(.40,.38,support-.54),bare)
        # Removed lid leaning at the wall behind the stack.
        lid=box('Removed crate lid',(0,.72,.95),(1.32,.055,.92),wood);lid.rotation_euler.x=math.radians(-12)
        for x in (-.52,.52):
            batten=box('Removed lid batten',(x,.675,.95),(.085,.04,.92),bare);batten.rotation_euler.x=math.radians(-12)
    for side in (-1,1):
        # Rope loops on the short ends, clear of the product on the lid.
        curve=bpy.data.curves.new('Rope handle','CURVE');curve.dimensions='3D';curve.bevel_depth=.012;curve.bevel_resolution=3
        spline=curve.splines.new('POLY');spline.points.add(24)
        for n,point in enumerate(spline.points):
            t=n/24;point.co=(side*(.68+.065*math.sin(math.pi*t)),-.18+.36*t,.79-.11*math.sin(math.pi*t),1)
        obj=bpy.data.objects.new('Crate rope handle',curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(rope)
        box('Rope retaining plate',(side*.677,-.18,.79),(.015,.05,.055),metal)
        box('Rope retaining plate',(side*.677,.18,.79),(.015,.05,.055),metal)
    for text,z,size in (('GBAY',.285,.095),('ORDNANCE',.16,.055)):
        font=bpy.data.curves.new('Crate stencil','FONT');font.body=text;font.size=size;font.align_x='CENTER';font.extrude=0
        obj=bpy.data.objects.new('Crate stencil',font);bpy.context.collection.objects.link(obj)
        obj.location=(0,-.544,z);obj.rotation_euler=(math.pi/2,0,0);obj.data.materials.append(ink)
    can_paint=surface('Scuffed olive ammo cans',(.07,.095,.038),.63,.45)
    nodes=can_paint.node_tree.nodes;links=can_paint.node_tree.links
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=32;noise.inputs['Detail'].default_value=3
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.025,.036,.014,1)
    ramp.color_ramp.elements[1].color=(.16,.18,.09,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0]);links.new(ramp.outputs[0],nodes.get('Principled BSDF').inputs['Base Color'])
    def line_prop(name,points,radius,mat):
        curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.bevel_depth=radius;curve.bevel_resolution=2
        spline=curve.splines.new('POLY');spline.points.add(len(points)-1)
        for dest,point in zip(spline.points,points):dest.co=(*point,1)
        obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj);obj.data.materials.append(mat)
        return obj
    # Storage references: palletized, banded timber boxes and ribbed molded
    # transit cases. Grouped stacks leave an uncluttered picking area in front.
    paper=surface('Aged inventory labels',(.32,.28,.19),.95)
    rubber=surface('Case gasket and grips',(.009,.012,.01),.92)
    polymer=surface('Graphite molded case',(.024,.033,.03),.73)
    tanpoly=surface('Faded khaki case',(.19,.16,.10),.78)
    rackpaint=surface('Worn rack enamel',(.055,.072,.078),.58,.45)
    shelfpaint=surface('Old ochre shelf beams',(.19,.10,.036),.72,.35)
    dust=surface('Settled warehouse dust',(.22,.20,.155),1)
    # Fine stipple and upward-facing dust break up the previously toy-like solids.
    for material in (polymer,tanpoly,can_paint,wood,bare):
        nodes=material.node_tree.nodes;links=material.node_tree.links;p=nodes.get('Principled BSDF')
        noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=95;noise.inputs['Detail'].default_value=2
        geometry=nodes.new('ShaderNodeNewGeometry');separate=nodes.new('ShaderNodeSeparateXYZ')
        links.new(geometry.outputs['Normal'],separate.inputs[0])
        upward=nodes.new('ShaderNodeMath');upward.operation='MAXIMUM';upward.inputs[1].default_value=0;links.new(separate.outputs['Z'],upward.inputs[0])
        strength=nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=.18;links.new(upward.outputs[0],strength.inputs[0])
        mix=nodes.new('ShaderNodeMixRGB');mix.inputs[2].default_value=(.28,.25,.19,1)
        old=next(iter(p.inputs['Base Color'].links),None)
        if old:links.new(old.from_socket,mix.inputs[1])
        else:mix.inputs[1].default_value=p.inputs['Base Color'].default_value
        links.new(strength.outputs[0],mix.inputs[0]);links.new(mix.outputs[0],p.inputs['Base Color'])
        if material in (polymer,tanpoly,can_paint):
            bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.24;bump.inputs['Distance'].default_value=.001
            links.new(noise.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],p.inputs['Normal'])
    def group_parts(name,parts,pos,yaw=0):
        group=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(group)
        for part in parts:part.parent=group
        group.location=pos;group.rotation_euler.z=yaw
        return group
    def stencil(text,pos,size,mat=ink):
        data=bpy.data.curves.new('Inventory stencil','FONT');data.body=text;data.size=size;data.align_x='CENTER'
        obj=bpy.data.objects.new('Inventory stencil',data);bpy.context.collection.objects.link(obj)
        obj.location=pos;obj.rotation_euler=(math.pi/2,0,0);obj.data.materials.append(mat)
        return obj
    def pallet(pos,width=1.85,depth=.64):
        parts=[]
        for x in (-width*.38,0,width*.38):parts.append(box('Pallet runner',(x,0,.06),(.11,depth,.12),bare))
        for n in range(6):parts.append(box('Pallet deck',(-width/2+(n+.5)*width/6,0,.145),(width/6-.016,depth,.05),bare))
        group_parts('Timber storage pallet',parts,pos)
    def weapon_crate(pos,width=1.75,depth=.56,yaw=0,number=1):
        parts=[]
        for level in range(2):
            for side in (-1,1):
                parts.append(box('Rifle crate plank',(0,side*depth/2,.09+level*.16),(width,.036,.155),wood))
                parts.append(box('Rifle crate end',(side*width/2,0,.09+level*.16),(.038,depth,.155),bare))
        for n in range(4):parts.append(box('Rifle crate lid',(0,-depth*.375+n*depth*.25,.344),(width,depth*.25-.003,.028),bare))
        for x in (-width*.37,width*.37):
            parts.extend([box('Timber cleat',(x,-depth/2-.032,.17),(.075,.055,.34),bare),
                box('Black shipping band',(x,0,.366),(.018,depth+.045,.008),metal),
                box('Black shipping band',(x,-depth/2-.062,.17),(.018,.007,.34),metal)])
        parts.append(stencil('SMALL ARMS / STORAGE',(0,-depth/2-.02,.22),.061))
        parts.append(stencil('LOT 0%d   -   BAY 04'%number,(0,-depth/2-.02,.10),.045))
        parts.append(box('Paper stock label',(width*.31,-depth/2-.023,.20),(.15,.002,.09),paper))
        for n in range(18):
            parts.append(box('Timber handling scratch',(rng.uniform(-width*.48,width*.48),-depth/2-.02,rng.uniform(.025,.30)),(rng.uniform(.008,.08),.001,.002),bare))
        group_parts('Stored rifle crate',parts,pos,yaw)
    def hard_case(pos,length=1.3,mat=polymer,yaw=0):
        parts=[box('Molded case base',(0,0,.087),(length,.40,.174),mat,.035),
            box('Case perimeter seal',(0,0,.17),(length+.008,.409,.013),rubber,.025),
            box('Molded case lid',(0,0,.21),(length,.40,.073),mat,.029)]
        for x in (-length*.40,-length*.26,length*.26,length*.40):
            parts.append(box('Molded reinforcing rib',(x,0,.25),(.043,.33,.024),mat,.01))
            parts.append(box('Case latch',(x,-.215,.164),(.063,.036,.09),rubber,.009))
        for x in (-length*.47,length*.47):
            parts.append(box('Case corner bumper',(x,0,.10),(.09,.423,.19),mat,.026))
        parts.append(line_prop('Recessed carrying handle',[(-.10,-.212,.15),(-.10,-.268,.15),(.10,-.268,.15),(.10,-.212,.15)],.014,rubber))
        parts.append(box('Case asset label',(-length*.15,-.206,.095),(.17,.002,.06),paper))
        parts.append(stencil('ARMORY 04',(-length*.15,-.209,.08),.021))
        for n in range(13):parts.append(box('Case handling wear',(rng.uniform(-length*.43,length*.43),rng.uniform(-.17,.17),.249),(rng.uniform(.01,.065),.002,.001),dust))
        return group_parts('Hard rifle transit case',parts,pos,yaw)
    pallet((-1.49,.86,0))
    for level in range(3):weapon_crate((-1.49+(level%2)*.025,.86,.17+level*.362),yaw=(-.018 if level==2 else 0),number=level+1)
    hard_case((1.13,.88,0),1.38)
    hard_case((1.12,.88,.255),1.38,tanpoly,.015)
    hard_case((1.10,.88,.51),1.30,polymer,-.025)
    # Background racking has a real footprint, supported shelves and grouped stock.
    for x in (-2.65,-.90,.90,2.65):
        box('Rack upright',(x,1.88,1.25),(.07,.07,2.5),rackpaint)
        box('Rack upright',(x,1.26,1.25),(.07,.07,2.5),rackpaint)
        for z in (.18,1.28,2.32):
            box('Shelf depth rail',(x,1.57,z),(.05,.69,.09),shelfpaint)
        for z in (.35,.60,.85,1.10,1.5,1.75,2.,2.25):box('Rack punched slot',(x,1.22,z),(.017,.003,.036),ink)
    for z in (.18,1.28,2.32):
        box('Shelf deck',(0,1.57,z),(5.35,.69,.045),metal)
        box('Shelf front beam',(0,1.22,z),(5.4,.06,.095),shelfpaint)
    for x in (-1.72,1.73):
        weapon_crate((x,1.58,1.32),1.5,.50,number=7)
        weapon_crate((x,1.58,1.682),1.5,.50,number=8)
        hard_case((x,1.58,2.35),1.4,tanpoly)
    weapon_crate((0,1.58,1.32),1.5,.50,number=9)
    for x in (-.36,.12,.60):
        box('Small boxed stores',(x,1.59,1.90),(.39,.42,.40),paper)
        box('Carton seam',(x,1.59,2.103),(.045,.43,.004),bare)
        stencil('STORES',(x,1.377,1.88),.038)
    def ammo_can(pos,yaw):
        # M2A1-inspired silhouette: long/squat steel body, overhanging sealed
        # lid, end latch opposite hinge, and a folded-flat carrying handle.
        parts=[box('Ammo can body',(0,0,.124),(.40,.205,.248),can_paint,.008),
            box('Ammo can base seam',(0,0,.014),(.412,.215,.025),can_paint,.007),
            box('Ammo can lid gasket',(0,0,.246),(.414,.217,.009),rubber,.006),
            box('Ammo can overhanging lid',(0,0,.257),(.428,.229,.017),can_paint,.007),
            box('Ammo can lid pressing',(0,0,.267),(.35,.175,.007),can_paint,.007),
            box('End latch mounting plate',(.208,0,.183),(.012,.080,.112),can_paint,.005),
            box('End latch lever',(.224,0,.20),(.013,.051,.090),metal,.004),
            box('End latch toe',(.222,0,.157),(.020,.061,.012),can_paint,.003),
            box('Rear hinge bracket',(-.21,0,.242),(.018,.12,.038),can_paint,.004)]
        for x in (-.095,.095):parts.append(box('Handle pivot bracket',(x,0,.274),(.030,.032,.013),can_paint,.003))
        parts.append(line_prop('Folded flat can handle',[(-.095,0,.279),(-.095,-.065,.279),(.095,-.065,.279),(.095,0,.279)],.0055,metal))
        # A pressed bead follows the broad panel instead of tall decorative ribs.
        for side in (-1,1):
            parts.append(line_prop('Pressed side bead',[(-.165,side*.104,.048),(-.165,side*.104,.218),(.165,side*.104,.218),(.165,side*.104,.048),(-.165,side*.104,.048)],.0025,can_paint))
        yellow=surface('Faded ammo can stencil',(.43,.36,.115),.96)
        parts.append(stencil('AMMUNITION',(0,-.107,.162),.033,yellow))
        parts.append(stencil('LOT 04 / STORAGE',(0,-.107,.109),.023,yellow))
        for n in range(15):
            parts.append(box('Can edge paint chip',(rng.uniform(-.195,.195),-.107,rng.choice((.027,.231))+rng.uniform(-.004,.004)),(rng.uniform(.006,.027),.001,.002),metal))
        group_parts('M2A1 style stored ammo can',parts,pos,yaw)
    # Dunnage keeps the grouped cans off the floor; the rear can is stacked
    # with clearance for the lower can's folded handle.
    for x in (.85,1.19):box('Ammo can dunnage',(x,-.065,.035),(.07,.60,.07),bare)
    box('Ammo can shelf board',(1.02,-.065,.077),(.50,.61,.014),wood)
    ammo_can((1.02,-.22,.085),.015);ammo_can((1.02,.075,.085),0)
    ammo_can((1.02,.075,.370),0)
    # Inert props are contained in a divided supply bin on the background
    # rifle-crate stack, rather than lying in the warehouse walkway.
    capmetal=surface('Dull brass prop caps',(.28,.20,.085),.5,.65)
    bin_x,bin_y,bin_z=-1.49,.83,1.26
    box('Supply bin bottom',(bin_x,bin_y,bin_z+.012),(.70,.42,.024),bare)
    for side in (-1,1):
        box('Supply bin long wall',(bin_x,bin_y+side*.205,bin_z+.08),(.70,.018,.16),wood)
        box('Supply bin end wall',(bin_x+side*.341,bin_y,bin_z+.08),(.018,.42,.16),bare)
    box('Supply bin divider',(bin_x+.04,bin_y,bin_z+.075),(.013,.39,.125),bare)
    stencil('CORD / SPARES',(bin_x,bin_y-.216,bin_z+.056),.039)
    box('Cord packing insert',(bin_x-.15,bin_y,bin_z+.075),(.35,.37,.10),paper)
    box('Lined spare parts compartment',(bin_x+.19,bin_y,bin_z+.077),(.26,.37,.106),paper)
    for n in range(5):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.014,depth=.065,location=(bin_x+.09+n*.044,bin_y-.08+rng.uniform(-.02,.02),bin_z+.147))
        obj=bpy.context.object;obj.name='Loose inert fuse cap';obj.rotation_euler=(math.pi/2,0,rng.uniform(-.25,.25));obj.data.materials.append(capmetal)
    cord=surface('Muted red prop cord',(.22,.052,.027),.9)
    points=[]
    for n in range(161):
        t=n/160;angle=t*math.pi*8;radius=.13-.075*t
        points.append((bin_x-.15+radius*math.cos(angle),bin_y+radius*.8*math.sin(angle),bin_z+.131))
    line_prop('Loose disconnected cord coil',points,.005,cord)
    line_prop('Contained cord tail',[points[0],(bin_x-.025,bin_y-.12,bin_z+.131),(bin_x-.09,bin_y-.16,bin_z+.131)],.005,cord)
    floor=concrete.copy();floor.name='Ground-in dust and stained concrete'
    nodes=floor.node_tree.nodes;links=floor.node_tree.links;p=nodes.get('Principled BSDF')
    coord=nodes.new('ShaderNodeTexCoord');grime=nodes.new('ShaderNodeTexNoise');grime.inputs['Scale'].default_value=2.8;grime.inputs['Detail'].default_value=5
    links.new(coord.outputs['Object'],grime.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.18,.19,.17,1);ramp.color_ramp.elements[1].color=(.75,.73,.65,1)
    links.new(grime.outputs['Fac'],ramp.inputs[0])
    multiply=nodes.new('ShaderNodeMixRGB');multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1
    links.new(p.inputs['Base Color'].links[0].from_socket,multiply.inputs[1]);links.new(ramp.outputs[0],multiply.inputs[2]);links.new(multiply.outputs[0],p.inputs['Base Color'])
    box('Warehouse floor',(0,0,-.045),(30,30,.09),floor)
    box('Warehouse wall',(0,2.10,2),(30,.12,4),concrete)
    box('Wall base trim',(0,2.01,.065),(30,.06,.13),metal)
    for x in (-3,0,3):box('Warehouse upright',(x,2,2),(.09,.13,4),metal)

scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=96 if crate else 64;scene.cycles.use_denoising=True
scene.cycles.max_bounces=6;scene.cycles.transparent_max_bounces=12
prefs=bpy.context.preferences.addons['cycles'].preferences;device='CPU'
for backend in ('OPTIX','CUDA','HIP','ONEAPI','METAL'):
    try:
        prefs.compute_device_type=backend;prefs.get_devices()
        if any(d.type!='CPU' for d in prefs.devices):
            for d in prefs.devices: d.use=d.type!='CPU'
            scene.cycles.device='GPU';device=backend;break
    except Exception: pass
scene.render.resolution_x=1280;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(root/'render.png')
scene.world=bpy.data.worlds.new('Studio ambient');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.8,.87,1,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.16
data=bpy.data.cameras.new('Catalog camera');camera=bpy.data.objects.new('Catalog camera',data)
bpy.context.collection.objects.link(camera);camera.location=(0,0,8);data.type='ORTHO';data.ortho_scale=3.2
camera.rotation_euler=(0,0,0);scene.camera=camera
if crate:
    target=Vector((0,.15,.84));camera.location=(2.35,-4.45,2.65)
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    data.type='PERSP';data.lens=49
    data.dof.use_dof=True;data.dof.focus_distance=(camera.location-Vector((0,-.18,1.0))).length;data.dof.aperture_fstop=1.8
for name,pos,power,size,color in (
    ('Warm softbox',(-1.6,1.8,3),240,2.0,(1,.95,.87)),
    ('Cool fill',(1.6,-.4,2),100,2.0,(.82,.9,1)),
    ('Edge strip',(.6,1.8,.5),130,1.3,(1,1,1))):
    if crate:
        pos,power,size={'Warm softbox':((-1.4,-.8,2.9),205,1.25),'Cool fill':((1.5,-1,1.8),25,2),'Edge strip':((.4,1.2,2.8),80,1.5)}[name]
    light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='RECTANGLE';light.size=size;light.size_y=size*.5;light.color=color
    obj=bpy.data.objects.new(name,light);bpy.context.collection.objects.link(obj);obj.location=pos
    obj.rotation_euler=(-obj.location).to_track_quat('-Z','Y').to_euler()
scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
bpy.ops.render.render(write_still=True)
(root/'result.json').write_text(json.dumps(dict(engine='Cycles',device=device,samples=scene.cycles.samples,category=manifest['category'],backdrop='warehouse-ammo-crate' if crate else 'pegboard',crate_open=manifest.get('crate_open',False),display_instances=1+len(manifest.get('display_copies',[])),parts=len(manifest['meshes']))))
'''
