import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, math, bpy
sys.argv += ['_']
src = open(f'{BDIR}/human.py').read().split("if __name__ == '__main__' and 'test' in sys.argv:")[0]
exec(src)
kind = sys.argv[sys.argv.index('--kind') + 1]
rig, body, extras = build(kind, [])
import importlib.util
spec_=importlib.util.spec_from_file_location('fp',f'{BDIR}/facepaint.py');fp=importlib.util.module_from_spec(spec_);spec_.loader.exec_module(fp)
fm=bpy.data.materials['face'];fm.use_nodes=True
fnode=fm.node_tree.nodes.new('ShaderNodeTexImage');fm.node_tree.links.new(fnode.outputs['Color'],fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
def setface(skin,hair,female):
    p=fp.paint(skin,hair,0x4a2e1a,female,'/tmp/face_%x.png'%skin);fnode.image=bpy.data.images.load(p,check_existing=True)

sc = bpy.context.scene
bpy.ops.mesh.primitive_plane_add(size=20); g = bpy.context.object; g.data.materials.append(mat('ground', 0x8a8c90, .9))
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(52), 0, math.radians(28))); bpy.context.object.data.energy = 3.2
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
try: sc.eevee.taa_render_samples = 16
except Exception: pass
sc.render.resolution_x = 300; sc.render.resolution_y = 520
bpy.ops.object.empty_add(location=(0, 0, .98)); tg = bpy.context.object
bpy.ops.object.camera_add(location=(0.9, -3.0, 1.4)); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 52; cam.constraints.new('TRACK_TO').target = tg
SK = 0xc99a78
def look(show, skin=SK, hair=0x2a1a10, shirt=0xe8e8e8, top='tee', pants=0x34507e, bottom='long', shoes=0x222222, jacket=0x3a3a3a, hat=0x202020):
    for e in extras: e.hide_render = e.name not in show
    sleeve = {'tee': skin, 'long': shirt, 'vest': skin, 'hoodie': shirt, 'jacket': jacket}[top]
    shoulder = {'tee': shirt, 'long': shirt, 'vest': skin, 'hoodie': shirt, 'jacket': jacket}[top]
    jc = shirt if top == 'hoodie' else jacket
    cols = dict(skinflat=skin, skin=skin, hair=hair, beard=hair, shirt=shirt, sleeve=sleeve, shoulder=shoulder, pants=pants,
                shin=pants if bottom == 'long' else skin, shoes=shoes, jacket=jc, hat=hat)
    setface(skin, hair, kind == 'female')
    for n, c in cols.items():
        mt = bpy.data.materials[n]; nt = mt.node_tree; b = nt.nodes['Principled BSDF']
        tex = [x for x in nt.nodes if x.type == 'TEX_IMAGE' and x.image and x.image.name.startswith('body_')]
        if tex:
            if 'TINT' not in nt.nodes:
                mx = nt.nodes.new('ShaderNodeMix'); mx.name = 'TINT'; mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs['Factor'].default_value = 1
                nt.links.new(tex[0].outputs['Color'], mx.inputs['A']); nt.links.new(mx.outputs['Result'], b.inputs['Base Color'])
            nt.nodes['TINT'].inputs['B'].default_value = (*srgb(c), 1)
        else:
            b.inputs['Base Color'].default_value = (*srgb(c), 1)
if kind == 'male':
    looks = [dict(show={'hair_short', 'beard_stubble'}, shirt=0xf2f2f2, top='tee'),
             dict(show={'hair_buzz', 'beard_full', 'top_hood'}, skin=0x7a4e32, hair=0x111111, shirt=0x6d6f73, top='hoodie', pants=0x222222, shoes=0xe8e8e8),
             dict(show={'hair_afro', 'beard_moustache', 'top_jacket', 'shoes_boots'}, skin=0xab7452, hair=0x1a1a1a, shirt=0xe8e0d0, top='jacket', jacket=0x5a3420, shoes=0x4a2e1a),
             dict(show={'hat_baseball', 'beard_goatee'}, skin=0xe7b892, hair=0x5a3612, shirt=0xc8231e, top='vest', pants=0xc9b48a, bottom='short', shoes=0xe8e8e8, hat=0x1f4e9c),
             dict(show={'hat_beanie', 'hair_short', 'beard_stubble', 'shoes_boots'}, skin=0xdca47f, hair=0x8a5a2a, shirt=0x2e7a36, top='long', pants=0x55575c, hat=0x222222)]
else:
    looks = [dict(show={'hair_long'}, skin=0xe7b892, hair=0x5a3612, shirt=0xe8b23a, top='tee'),
             dict(show={'hair_bun', 'top_jacket'}, skin=0x7a4e32, hair=0x111111, shirt=0xf2f2f2, top='jacket', jacket=0x202020, pants=0x3f5f8a, bottom='short', shoes=0x8a2a2a),
             dict(show={'hair_bob', 'top_hood'}, skin=0xf1c9a5, hair=0xc9a050, shirt=0x9a4fc4, top='hoodie', pants=0x222222),
             dict(show={'hair_pony', 'shoes_boots'}, skin=0xab7452, hair=0x2a1a10, shirt=0xf08aa0, top='vest', pants=0x2d3b5c),
             dict(show={'hair_afro'}, skin=0x5e3a24, hair=0x111111, shirt=0x6ac2c9, top='long', pants=0xc9b48a, bottom='short', shoes=0xe8e8e8)]
for i, L in enumerate(looks):
    look(**L); sc.frame_set(1)
    sc.render.filepath = f'{BDIR}/people/ward_{kind}_{i}.png'; bpy.ops.render.render(write_still=True)
print('DONE')
if '--ref' in sys.argv:
    look(show={'hair_short'}, skin=0x7a4e32, hair=0x111111, shirt=0x2b2b2e, top='long', pants=0x6d6f73, shoes=0x161616)
    w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0x2a3456), 1); g.hide_render = True
    sc.render.resolution_x = 360; sc.render.resolution_y = 600; tg.location = (0, 0, .95); cam.data.lens = 48
    for nm, pos in (('front', (0, -3.4, 1.15)), ('back', (0, 3.4, 1.15)), ('side', (3.4, -.2, 1.15))):
        cam.location = pos; sc.render.filepath = f'{BDIR}/people/ref_{nm}.png'; bpy.ops.render.render(write_still=True)
    sc.render.resolution_x = 420; sc.render.resolution_y = 420; tg.location = (0, 0, 1.6); cam.data.lens = 85
    cam.location = (.35, -1.6, 1.68); sc.render.filepath = f'{BDIR}/people/ref_face.png'; bpy.ops.render.render(write_still=True)
    print('REFDONE')
