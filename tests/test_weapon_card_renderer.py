from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from allin1.weapon_card_renderer import render_card, studio_backdrop, studio_lighting, pegboard


def geometry():
    return SimpleNamespace(vertices=((-1,0,-.5),(1,0,-.5),(1,0,.5),(-1,0,.5)),
                           triangles=((0,1,2),(0,2,3)),texcoords=((0,0),(1,0),(1,1),(0,1)))


def test_texture_varies_within_triangle_and_is_deterministic():
    pixels=np.zeros((64,64,3),dtype='uint8')
    pixels[:,:32]=[200,20,20];pixels[:,32:]=[20,20,200]
    texture=Image.fromarray(pixels)
    image=render_card([geometry()],{'base':texture},lambda _: 'base')
    assert image.size==(512,320)
    data=np.asarray(image)
    assert ((data[:,:,0]>data[:,:,2]*1.5)&(data[:,:,0]>100)).sum()>1000
    assert ((data[:,:,2]>data[:,:,0]*1.5)&(data[:,:,2]>100)).sum()>1000
    assert image.tobytes()==render_card([geometry()],{'base':texture},lambda _: 'base').tobytes()
    # Complete framing leaves a background margin around the object/shadow.
    assert abs(int(data[0,0,0])-190)<20


def test_missing_diffuse_fails_instead_of_generating_misleading_art():
    with pytest.raises(ValueError,match='Missing diffuse'):
        render_card([geometry()],{},lambda _: 'missing')


def test_bounded_geometry_and_dimensions():
    with pytest.raises(ValueError): render_card([],{},lambda _: '')
    with pytest.raises(ValueError): render_card([geometry()],{},lambda _: '',size=(4000,4000))
    g=geometry();g.triangles=((-1,1,2),)
    with pytest.raises(ValueError,match='indices'): render_card([g],{},lambda _: '')


def test_studio_has_light_concrete_and_textured_asphalt():
    image=np.asarray(studio_backdrop((512,320)))[:,:,:3]
    assert image[:160].mean()>image[230:].mean()+50
    assert image[250:300,100:400].std()>4


def test_lighting_is_directional_and_keeps_colours():
    normals=np.array([[-.6,.6,.53],[.6,-.6,.53]])
    normals/=np.linalg.norm(normals,axis=1,keepdims=True)
    colors=studio_lighting(np.full((2,3),.4),normals)
    assert colors[0].mean()>colors[1].mean()*1.2
    assert np.isfinite(colors).all() and colors.min()>=0 and colors.max()<=1


def test_missing_studio_asset_fails_instead_of_caching_wrong_background(tmp_path):
    with pytest.raises(FileNotFoundError): studio_backdrop((512,320),tmp_path/'missing.png')


@pytest.mark.parametrize('category', ['weapons','gear'])
def test_weapons_and_gear_keep_pegboard(category, tmp_path):
    image=render_card([geometry()],{'base':Image.new('RGB',(4,4),'red')},lambda _:'base',
                      category=category, backdrop=tmp_path/'not-used.png')
    expected=pegboard((1024,640)).resize((512,320),Image.Resampling.LANCZOS)
    assert image.getpixel((10,300))==expected.getpixel((10,300))


def test_directx_uv_vertical_orientation():
    pixels=np.zeros((64,64,3),dtype='uint8')
    pixels[:32]=[220,20,20];pixels[32:]=[20,20,220]
    image=np.asarray(render_card([geometry()],{'base':Image.fromarray(pixels)},lambda _: 'base'))
    # Geometry's upper edge has v=1, so it samples the bottom DDS rows.
    assert int(image[115,256,2])>int(image[115,256,0])*2
    assert int(image[205,256,0])>int(image[205,256,2])*2


def test_depth_buffer_does_not_depend_on_geometry_submission_order():
    front=geometry();rear=geometry()
    front.vertices=tuple((x,y+.1,z) for x,y,z in front.vertices)
    front.texture='red';rear.texture='blue'
    textures={'red':Image.new('RGB',(4,4),'red'),'blue':Image.new('RGB',(4,4),'blue')}
    a=render_card([front,rear],textures,lambda g:g.texture)
    b=render_card([rear,front],textures,lambda g:g.texture)
    assert a.tobytes()==b.tobytes()
    assert a.getpixel((256,160))[0]>150


def test_palette_alpha_is_a_colour_index_not_opacity():
    g=geometry()
    textures={'base':Image.new('RGBA',(4,4),(255,255,255,42)), 'pal':Image.new('RGB',(128,32),(20,45,90))}
    image=render_card([g],textures,lambda _: 'base',materials={id(g):{'palette':'pal','palette_mode':'alpha'}})
    r,green,b=image.getpixel((256,160))
    assert b>r*1.5 and b>green and r<70
    with pytest.raises(ValueError,match='Missing tint palette'):
        render_card([g],{'base':textures['base']},lambda _:'base',materials={id(g):{'palette':'pal'}})


def test_transparent_decal_does_not_erase_body():
    body=geometry(); decal=geometry()
    decal.vertices=tuple((x,y+.01,z) for x,y,z in decal.vertices)
    textures={'body':Image.new('RGBA',(4,4),(200,10,10,255)), 'decal':Image.new('RGBA',(4,4),(255,255,255,0))}
    image=render_card([decal,body],textures,lambda g:'body' if g is body else 'decal',materials={id(decal):{'decal':True}})
    assert image.getpixel((256,160))[0]>150 and image.getpixel((256,160))[1]<70


def test_flat_accessory_faces_board_instead_of_edge_on():
    g=geometry();g.vertices=tuple((0,x,z) for x,y,z in g.vertices)
    textures={'base':Image.new('RGB',(4,4),'red')}
    image=np.asarray(render_card([g],textures,lambda _:'base',flat=True))
    assert ((image[:,:,0]>150)&(image[:,:,1]<60)).sum()>35000
