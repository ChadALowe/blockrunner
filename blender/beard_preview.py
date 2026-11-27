import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, math, bpy
sys.argv += ['_']
exec(open(f'{BDIR}/human.py').read().split("if __name__ == '__main__' and 'test' in sys.argv:")[0])
import importlib.util
sp = importlib.util.spec_from_file_location('fp', f'{BDIR}/facepaint.py'); fp = importlib.util.module_from_spec(sp); sp.loader.exec_module(fp)
rig, body, extras = build('male', [])
sc = bpy.context.scene
fm = bpy.data.materials['face']; fn = fm.node_tree.nodes.new('ShaderNodeTexImage'); fm.node_tree.links.new(fn.outputs['Color'], fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(50), 0, math.radians(25))); bpy.context.object.data.energy = 3.2
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
sc.render.resolution_x = 300; sc.render.resolution_y = 300
bpy.ops.object.empty_add(location=(0, 0, 1.66)); tg = bpy.context.object
bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 85; cam.constraints.new('TRACK_TO').target = tg
def col(n, c): bpy.data.materials[n].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*srgb(c), 1)
looks = [('stubble', 'beard_stubble', 0xc99a78, 0x2a1a10), ('moustache', 'beard_moustache', 0xe7b892, 0x5a3612),
         ('goatee', 'beard_goatee', 0x9c6a48, 0x111111), ('full', 'beard_full', 0xdca47f, 0x7a2a10)]
for nm, bd, skin, hair in looks:
    for e in extras: e.hide_render = e.name not in (bd, 'hair_short')
    col('skin', skin); col('skinflat', skin); col('hair', hair); col('beard', hair); col('shirt', 0x2e7a36); col('shoulder', 0x2e7a36)
    fn.image = bpy.data.images.load(fp.paint(skin, hair, 0x4a2e1a, False, f'/tmp/f_{nm}.png', True, nm == 'stubble'))
    for vn, pos in (('f', (.05, -1.3, 1.68)), ('q', (.85, -1.0, 1.66))):
        cam.location = pos; sc.render.filepath = f'{BDIR}/people/beard_{nm}_{vn}.png'; bpy.ops.render.render(write_still=True)
print('DONE')
