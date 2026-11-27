import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import sys, math, bpy
sys.argv += ['_']
exec(open(f'{BDIR}/human.py').read().split("if __name__ == '__main__' and 'test' in sys.argv:")[0])
tag = sys.argv[sys.argv.index('--tag') + 1] if '--tag' in sys.argv else 'cur'
kind = sys.argv[sys.argv.index('--kind') + 1] if '--kind' in sys.argv else 'male'
sty = ['short', 'cap'] if kind == 'male' else ['long', 'bun']
rig, body, extras = build(kind, sty)
show = sys.argv[sys.argv.index('--show') + 1] if '--show' in sys.argv else 'hair_short'
for e in extras: e.hide_render = (e.name != show)
sc = bpy.context.scene
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(55), 0, math.radians(30))); bpy.context.object.data.energy = 3
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
sc.render.resolution_x = 420; sc.render.resolution_y = 480
bpy.ops.object.empty_add(location=(0, 0, 1.45)); tg = bpy.context.object
bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 60; cam.constraints.new('TRACK_TO').target = tg
for nm, pos in (('front', (.35, -1.7, 1.55)), ('side', (1.5, -.6, 1.55)), ('back', (-.6, 1.6, 1.6))):
    cam.location = pos; sc.render.filepath = f'{BDIR}/people/close_{tag}_{nm}.png'; bpy.ops.render.render(write_still=True)
print('DONE')
