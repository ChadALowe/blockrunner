import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, math, bpy, json
sys.argv += ['_']
exec(open(f'{BDIR}/human.py').read().split("if __name__ == '__main__' and 'test' in sys.argv:")[0])
import importlib.util
sp = importlib.util.spec_from_file_location('fp', f'{BDIR}/facepaint.py'); fp = importlib.util.module_from_spec(sp); sp.loader.exec_module(fp)
WD = json.load(open(f'{BDIR}/wardrobe.json')); BY = {k: {r[0]: r for r in v} for k, v in WD.items()}
STY = {b[0]: b for b in json.load(open(f'{BDIR}/beard_styles.json'))}
kind = sys.argv[sys.argv.index('--kind') + 1]
rig, body, extras = build(kind, [])
sc = bpy.context.scene
fm = bpy.data.materials['face']; fn = fm.node_tree.nodes.new('ShaderNodeTexImage'); fm.node_tree.links.new(fn.outputs['Color'], fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.mesh.primitive_plane_add(size=20); g = bpy.context.object; g.data.materials.append(mat('ground', 0x8a8c90, .9))
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(52), 0, math.radians(28))); bpy.context.object.data.energy = 3.2
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
try: sc.eevee.taa_render_samples = 8
except Exception: pass
sc.render.resolution_x = 260; sc.render.resolution_y = 480
bpy.ops.object.empty_add(location=(0, 0, 1.0)); tg = bpy.context.object
bpy.ops.object.camera_add(location=(.9, -3.1, 1.45)); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 50; cam.constraints.new('TRACK_TO').target = tg
def setc(n, c):
    mt = bpy.data.materials.get(n)
    if not mt: return
    nt = mt.node_tree; b = nt.nodes['Principled BSDF']
    tex = [x for x in nt.nodes if x.type == 'TEX_IMAGE' and x.image and x.image.name.startswith('body_')]
    if tex:
        if 'TINT' not in nt.nodes:
            mx = nt.nodes.new('ShaderNodeMix'); mx.name = 'TINT'; mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs['Factor'].default_value = 1
            nt.links.new(tex[0].outputs['Color'], mx.inputs['A']); nt.links.new(mx.outputs['Result'], b.inputs['Base Color'])
        nt.nodes['TINT'].inputs['B'].default_value = (*srgb(c), 1)
    else: b.inputs['Base Color'].default_value = (*srgb(c), 1)
def dress(L):
    t, bo, sh, ha, ey, ex = BY['tops'][L['top']], BY['bottoms'][L['bottom']], BY['shoes'][L['shoes']], BY['hats'][L['hat']], BY['eyewear'][L['eye_']], BY['extras'][L['extra']]
    show = set(t[2]) | set(bo[2]) | set(sh[2]) | set(ha[2]) | set(ey[2]) | set(ex[2]) | {'beard_' + p for p in STY.get(L['beard'], [0, 0, [], ''])[2]}
    if L['hair'] != 'none' and (L['hat'] == 'none' or L['hair'] in ('hair_long', 'hair_bob', 'hair_pony', 'hair_bun')): show.add(L['hair'])
    for e in extras: e.hide_render = e.name not in show
    tok = {'top': L['topCol'], 'skin': L['skin'], 'trim': L['trim'], 'white': 0xe6e2da, 'bot': L['botCol']}
    setc('skin', L['skin']); setc('skinflat', L['skin']); setc('shirt', tok[t[3]]); setc('shoulder', tok[t[4]]); setc('sleeve', tok[t[5]]); setc('jacket', L['topCol'])
    setc('pants', tok[bo[3]]); setc('shin', tok[bo[4]]); setc('skirt', L['botCol']); setc('shoes', L['shoeCol']); setc('hair', L['hairCol']); setc('beard', L['hairCol'])
    setc('hat', L['hatCol']); setc('trim', L['trim'])
    fn.image = bpy.data.images.load(fp.paint(L['skin'], L['hairCol'], 0x4a2e1a, kind == 'female', '/tmp/fc_%d.png' % hash(str(L)), L['hair'] != 'none', STY.get(L['beard'], [0, 0, [], ''])[3] or False))
D = dict(skin=0xc99a78, hair='hair_short', hairCol=0x2a1a10, beard='none', top='tee', topCol=0xf2f2f2, trim=0xf2f2f2, bottom='long', botCol=0x34507e,
         shoes='trainers', shoeCol=0x222222, hat='none', hatCol=0x222222, eye_='none', extra='none')
def L(**k): d = dict(D); d.update(k); return d
if kind == 'male':
    looks = [('Polo', L(top='polo', topCol=0x2e7a36, bottom='cargo', botCol=0xc9b48a, shoes='trainers', shoeCol=0xf2f2f2, eye_='sunglasses', skin=0xe7b892)),
             ('Button shirt', L(top='shirt', topCol=0x6ac2c9, botCol=0x2d3b5c, shoes='smart', shoeCol=0x161616, eye_='glasses', hair='hair_buzz', beard='short', skin=0x9c6a48)),
             ('Tracksuit', L(top='tracksuit', topCol=0x1f4e9c, trim=0xf2f2f2, bottom='joggers', botCol=0x1f4e9c, shoes='trainers', shoeCol=0xf2f2f2, hat='backwards', hatCol=0x161616, extra='chain', skin=0x7a4e32, hairCol=0x111111)),
             ('Puffer', L(top='puffer', topCol=0x161616, botCol=0x6d6f73, shoes='hitops', shoeCol=0xb3201c, hat='beanie', hatCol=0xd0692a, beard='stubble', extra='headphones')),
             ('Blazer + tie', L(top='blazer', topCol=0x2d3b5c, trim=0xb3201c, botCol=0x2d3b5c, shoes='smart', shoeCol=0x161616, hat='trilby', hatCol=0x5a3420, trim2=0, beard='tache', skin=0xdca47f, hairCol=0x8a8a8a)),
             ('Hi-vis', L(top='hivis', trim=0x6d6f73, botCol=0x34507e, shoes='boots', shoeCol=0x5a3420, hat='hard', hatCol=0xe0b83c, beard='heavy', skin=0xab7452)),
             ('Parka', L(top='parka', topCol=0x556b2f, trim=0x161616, botCol=0x34507e, shoes='boots', shoeCol=0x161616, extra='scarf', beard='goatee')),
             ('Football', L(top='football', topCol=0xb3201c, trim=0xf2f2f2, bottom='short', botCol=0x161616, shoes='trainers', shoeCol=0x161616, skin=0x5e3a24 if False else 0x7a4e32, hair='hair_afro', hairCol=0x111111)),
             ('Jumper', L(top='jumper', topCol=0x7b3fa0, botCol=0xc9b48a, shoes='smart', shoeCol=0x5a3420, hat='flat', hatCol=0x6d6f73, eye_='glasses', beard='bushy', hairCol=0xc9a050, skin=0xf1c9a5)),
             ('Gilet', L(top='gilet', topCol=0x2d3b5c, trim=0xe6e2da, botCol=0x556b2f, shoes='wellies', shoeCol=0x2e7a36, hat='flat', hatCol=0x5a3420, beard='chops', skin=0xdca47f)),
             ('Bucket + aviators', L(top='tee', topCol=0xe0b83c, bottom='short', botCol=0x1f4e9c, hat='bucket', hatCol=0xf2f2f2, eye_='aviators', extra='backpack', trim=0x2e7a36, shoes='hitops', shoeCol=0xf2f2f2)),
             ('Long sleeve', L(top='long', topCol=0xd0692a, botCol=0x161616, shoes='boots', shoeCol=0x161616, beard='viking', hair='hair_long', hairCol=0x7a2a10))]
else:
    looks = [('Short skirt', L(top='tee', topCol=0xf08aa0, bottom='skirt', botCol=0x161616, shoes='hitops', shoeCol=0xf2f2f2, hair='hair_long', hairCol=0x5a3612, skin=0xe7b892)),
             ('Long skirt', L(top='polo', topCol=0xf2f2f2, bottom='longskirt', botCol=0x7b3fa0, shoes='smart', shoeCol=0x161616, hair='hair_bun', hairCol=0x111111, skin=0x7a4e32, eye_='sunglasses')),
             ('Puffer', L(top='puffer', topCol=0xf2f2f2, bottom='joggers', botCol=0x161616, trim=0xf2f2f2, shoes='trainers', shoeCol=0xf2f2f2, hair='hair_pony', hairCol=0xc9a050, skin=0xf1c9a5)),
             ('Blazer', L(top='blazer', topCol=0x161616, trim=0x161616, botCol=0x161616, shoes='smart', shoeCol=0x161616, hair='hair_bob', hairCol=0x7a2a10, eye_='glasses', skin=0xdca47f)),
             ('Parka + scarf', L(top='parka', topCol=0xb3201c, trim=0xe6e2da, botCol=0x34507e, shoes='wellies', shoeCol=0xe0b83c, hair='hair_long', hairCol=0x2a1a10, extra='scarf', skin=0xab7452)),
             ('Tracksuit', L(top='tracksuit', topCol=0x7b3fa0, trim=0xf2f2f2, bottom='joggers', botCol=0x7b3fa0, shoes='trainers', shoeCol=0xf2f2f2, hair='hair_afro', hairCol=0x111111, skin=0x5e3a24, extra='headphones')),
             ('Shirt + cargo', L(top='shirt', topCol=0x556b2f, bottom='cargo', botCol=0xc9b48a, shoes='boots', shoeCol=0x5a3420, hat='bucket', hatCol=0xc9b48a, hair='hair_bob', hairCol=0x5a3612, eye_='aviators')),
             ('Jumper', L(top='jumper', topCol=0x6ac2c9, botCol=0x34507e, shoes='hitops', shoeCol=0xb3201c, hat='beanie', hatCol=0xf08aa0, hair='hair_long', hairCol=0xc0306a, extra='backpack', trim=0x161616))]
SET = sys.argv[sys.argv.index('--set') + 1] if '--set' in sys.argv else 'main'
if SET == 'gang':
    if kind == 'male':
        looks = [('Grove OG', L(top='vest', topCol=0xf2f2f2, bottom='baggy', botCol=0x34507e, trim=0xf2f2f2, shoes='trainers', shoeCol=0xf2f2f2, hat='bandana', hatCol=0x2e7a36, extra='chain', skin=0x5e3a24, hair='hair_buzz', hairCol=0x111111, beard='stubtache')),
                 ('Grove jersey', L(top='jersey', topCol=0x2e7a36, trim=0xf2f2f2, bottom='longshorts', botCol=0x161616, shoes='hitops', shoeCol=0xf2f2f2, hat='snapback', hatCol=0x2e7a36, extra='bigchain', skin=0x7a4e32, hair='hair_buzz', hairCol=0x111111)),
                 ('Ballas', L(top='bigtee', topCol=0x7b3fa0, bottom='baggy', botCol=0x161616, trim=0xf2f2f2, shoes='trainers', shoeCol=0x161616, hat='bandana', hatCol=0x7b3fa0, eye_='sunglasses', extra='chain', skin=0x5e3a24, hair='hair_short', hairCol=0x111111, beard='goatee')),
                 ('Vagos', L(top='flannel', topCol=0xe0b83c, trim=0x161616, bottom='longshorts', botCol=0xc9b48a, shoes='trainers', shoeCol=0xf2f2f2, hat='durag', hatCol=0xe0b83c, skin=0xab7452, hair='hair_buzz', hairCol=0x111111, beard='horseshoe')),
                 ('Aztecas', L(top='flannel', topCol=0x2aa8a8, trim=0x10334a, bottom='baggy', botCol=0xc9b48a, trim2=0, shoes='smart', shoeCol=0x161616, hat='none', skin=0xab7452, hair='hair_buzz', hairCol=0x111111, beard='handlebar', eye_='sunglasses')),
                 ('Hood up', L(top='bigtee', topCol=0x161616, bottom='baggy', botCol=0x2d3b5c, trim=0xb3201c, shoes='hitops', shoeCol=0xb3201c, hat='snapback', hatCol=0xb3201c, extra='facemask', skin=0x9c6a48, hair='hair_short', hairCol=0x111111)),
                 ('Blazer + tie', L(top='blazer', topCol=0x2d3b5c, trim=0xb3201c, botCol=0x2d3b5c, shoes='smart', shoeCol=0x161616, beard='tache', skin=0xdca47f, hairCol=0x8a8a8a)),
                 ('Blazer open', L(top='blazeropen', topCol=0x5a5a5e, botCol=0x161616, shoes='smart', shoeCol=0x5a3420, skin=0x7a4e32, hair='hair_buzz', hairCol=0x111111, extra='bigchain', eye_='sunglasses'))]
    else:
        looks = [('Grove girl', L(top='jersey', topCol=0x2e7a36, trim=0xf2f2f2, bottom='baggy', botCol=0x34507e, shoes='hitops', shoeCol=0xf2f2f2, hat='bandana', hatCol=0x2e7a36, hair='hair_pony', hairCol=0x111111, skin=0x5e3a24, extra='chain')),
                 ('Ballas girl', L(top='bigtee', topCol=0x7b3fa0, bottom='longshorts', botCol=0x161616, shoes='trainers', shoeCol=0xf2f2f2, hat='snapback', hatCol=0x7b3fa0, hair='hair_long', hairCol=0x111111, skin=0x7a4e32, eye_='sunglasses')),
                 ('Chola', L(top='flannel', topCol=0x161616, trim=0x6d6f73, bottom='baggy', botCol=0xc9b48a, shoes='smart', shoeCol=0x161616, hair='hair_long', hairCol=0x111111, skin=0xab7452, extra='bigchain')),
                 ('Blazer', L(top='blazer', topCol=0x161616, trim=0x161616, botCol=0x161616, shoes='smart', shoeCol=0x161616, hair='hair_bob', hairCol=0x7a2a10, eye_='glasses', skin=0xdca47f))]
for i, (nm, LL) in enumerate(looks):
    dress(LL); sc.frame_set(1)
    sc.render.filepath = f'{BDIR}/people/cl{SET}_{kind}_{i:02d}.png'; bpy.ops.render.render(write_still=True)
json.dump([n for n, _ in looks], open(f'{BDIR}/people/cl{SET}_{kind}.json', 'w'))
print('DONE')
