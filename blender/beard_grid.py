import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, math, bpy, json
sys.argv += ['_']
exec(open(f'{BDIR}/human.py').read().split("if __name__ == '__main__' and 'test' in sys.argv:")[0])
import importlib.util
sp = importlib.util.spec_from_file_location('fp', f'{BDIR}/facepaint.py'); fp = importlib.util.module_from_spec(sp); sp.loader.exec_module(fp)
STY = json.load(open(f'{BDIR}/beard_styles.json'))
rig, body, extras = build('male', [])
sc = bpy.context.scene
fm = bpy.data.materials['face']; fn = fm.node_tree.nodes.new('ShaderNodeTexImage'); fm.node_tree.links.new(fn.outputs['Color'], fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(50), 0, math.radians(25))); bpy.context.object.data.energy = 3.2
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
try: sc.eevee.taa_render_samples = 8
except Exception: pass
sc.render.resolution_x = 240; sc.render.resolution_y = 260
bpy.ops.object.empty_add(location=(0, 0, 1.63)); tg = bpy.context.object
bpy.ops.object.camera_add(location=(.55, -1.25, 1.66)); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 85; cam.constraints.new('TRACK_TO').target = tg
def col(n, c): bpy.data.materials[n].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*srgb(c), 1)
SK = [0xf1c9a5, 0xdca47f, 0xc99a78, 0xab7452, 0x9c6a48, 0x7a4e32]; HC = [0x2a1a10, 0x5a3612, 0x111111, 0x7a2a10, 0x8a8a8a, 0xc9a050]
col('shirt', 0x2e7a36); col('shoulder', 0x2e7a36)
ONLY = [int(a) for a in sys.argv[sys.argv.index('--only') + 1].split(',')] if '--only' in sys.argv else None
for i, (sid, name, pieces, paint) in enumerate(STY):
    if ONLY is not None and i not in ONLY: continue
    skin, hair = SK[i % 6], HC[(i * 5) % 6]
    show = {'hair_short'} | {'beard_' + p for p in pieces}
    for e in extras: e.hide_render = e.name not in show
    col('skin', skin); col('skinflat', skin); col('hair', hair); col('beard', hair)
    fn.image = bpy.data.images.load(fp.paint(skin, hair, 0x4a2e1a, False, f'/tmp/fg_{i}.png', True, paint or False))
    sc.render.filepath = f'{BDIR}/people/bg_{i:02d}.png'; bpy.ops.render.render(write_still=True)
print('DONE')
