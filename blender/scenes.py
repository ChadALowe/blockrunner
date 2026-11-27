import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import bpy, math, random, os, sys
OUT = f'{BDIR}/art'
os.makedirs(OUT, exist_ok=True)

def srgb(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return tuple((x / 12.92) if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in c)

def mat(name, col, rough=.6, emit=0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1); b.inputs['Roughness'].default_value = rough
    if emit:
        b.inputs['Emission Color'].default_value = (*col, 1); b.inputs['Emission Strength'].default_value = emit
    return m

def box(size, loc, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object; o.scale = size; o.data.materials.append(m); return o

def palm(x, y, h, mt, ml):
    bpy.ops.mesh.primitive_cylinder_add(vertices=7, radius=.28, depth=h, location=(x, y, h / 2)); bpy.context.object.data.materials.append(mt)
    for k in range(7):
        a = k / 7 * math.tau + .3
        o = box((.9, 3.6, .08), (x + math.cos(a) * 1.6, y + math.sin(a) * 1.6, h - .5), ml, rot=(0, 0, a - math.pi / 2))
        o.rotation_euler = (math.radians(-28) * math.cos(0), 0, a - math.pi / 2)
        o.rotation_mode = 'ZXY'; o.rotation_euler = (math.radians(-30), 0, a - math.pi / 2)

def street(seed, night=False):
    random.seed(seed)
    asphalt = mat('asphalt', srgb(0x34353a), .9); side = mat('side', srgb(0xb8ad98), .9)
    yellow = mat('yl', srgb(0xe6c347), .7)
    pal = [0xe8d4b0, 0xdba97e, 0xcbb79c, 0xb9c6cc, 0xe8c9a6, 0xa3b4bc, 0xcc9370, 0xe3b7a0]
    win = mat('win', srgb(0xffd890) if night else srgb(0x3e4a56), .3, 3 if night else 0)
    windark = mat('windark', srgb(0x2a323c), .3)
    mt = mat('trunk', srgb(0x8d6b47)); ml = mat('leaf', srgb(0x3e7d2a))
    bpy.ops.mesh.primitive_plane_add(size=400); bpy.context.object.data.materials.append(asphalt)
    for s in (-1, 1):
        box((5, 400, .3), (s * 10.5, 0, .15), side)
    for y in range(-150, 150, 7):
        box((.18, 3, .02), (0, y, .01), yellow)
    for s in (-1, 1):
        y = -120
        while y < 150:
            w = random.uniform(10, 18); h = random.uniform(10, 45); d = random.uniform(10, 16)
            m = mat('b', srgb(random.choice(pal)), .8)
            box((d, w - .6, h), (s * (13 + d / 2), y + w / 2, h / 2), m)
            fx = s * 13 - s * .05
            for zz in range(3, int(h) - 1, 4):
                for yy in range(int(y) + 2, int(y + w) - 2, 4):
                    box((.12, 2.2, 2.2), (fx, yy + 1, zz), win if (night and random.random() < .55) else windark)
            y += w
        for yy in range(-110, 150, 16):
            palm(s * 9.4, yy + (s * 4), random.uniform(8, 11), mt, ml)

def import_car(cid, loc, rotz, color=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f'{BDIR}/../assets/cars/{cid}.glb')
    new = [o for o in bpy.data.objects if o not in before]
    root = [o for o in new if o.parent is None][0]
    root.location = loc; root.rotation_euler = (0, 0, rotz)
    if color is not None:
        for o in new:
            for s in getattr(o, 'material_slots', []):
                if s.material and s.material.name.startswith('paint'):
                    m = s.material.copy(); m.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*srgb(color), 1); s.material = m
    return root

def lights(sun_rot, sun_col, sun_e, world_col, world_e):
    bpy.ops.object.light_add(type='SUN', rotation=sun_rot); s = bpy.context.object; s.data.energy = sun_e; s.data.color = sun_col; s.data.angle = .05
    w = bpy.data.worlds.new('w'); w.use_nodes = True
    bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (*world_col, 1); bg.inputs[1].default_value = world_e
    bpy.context.scene.world = w

def camera(loc, target, lens):
    bpy.ops.object.empty_add(location=target); t = bpy.context.object
    bpy.ops.object.camera_add(location=loc); c = bpy.context.object; c.data.lens = lens
    tc = c.constraints.new('TRACK_TO'); tc.target = t
    bpy.context.scene.camera = c

def render(name):
    sc = bpy.context.scene
    try: sc.view_settings.view_transform = 'Standard'
    except Exception: pass
    sc.render.resolution_x = 1280; sc.render.resolution_y = 720
    sc.render.filepath = f'{OUT}/{name}.png'
    bpy.ops.render.render(write_still=True)

def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)

# Scene 1: police chase — gold sports car with cruiser behind, low angle
fresh(); street(1)
import_car('sports', (1.8, -2, 0), math.radians(0), 0xd9a514)
import_car('police', (-1.6, 7, 0), math.radians(6))
import_car('police', (2.6, 15, 0), math.radians(-4))
lights((math.radians(68), 0, math.radians(150)), (1, .66, .42), 4.2, srgb(0xf2b488), .85)
camera((4.2, -8.6, 1.15), (0.2, 4, 1.5), 30)
render('chase')

# Scene 2: saloon parked under palms, golden hour
fresh(); street(2)
import_car('saloon', (6.2, 0, 0), math.radians(180), 0x7a1c22)
import_car('van', (-3.4, 14, 0), math.radians(180), 0xe8e8e8)
lights((math.radians(70), 0, math.radians(-120)), (1, .7, .45), 3.2, srgb(0xe8b890), .85)
camera((-1.5, -9, 2.2), (5.5, 1, 1.0), 32)
render('street')

# Scene 3: dusk van with lit windows
fresh(); street(3, night=True)
import_car('van', (-2.2, 2, 0), math.radians(180), 0x2c5d8f)
import_car('saloon', (2.4, 12, 0), math.radians(5), 0x1f4e9c)
lights((math.radians(84), 0, math.radians(200)), (.95, .45, .55), 1.6, srgb(0x6a4a90), .95)
camera((3.5, -9.5, 1.4), (-1.5, 4, 1.6), 30)
render('dusk')

# Scene 4: hero shot of sports car, top-down-ish dramatic
fresh(); street(4)
import_car('sports', (0, 0, 0), math.radians(25), 0xb3201c)
import_car('saloon', (-3.4, -14, 0), math.radians(180), 0x2e7a36)
lights((math.radians(60), 0, math.radians(40)), (1, .8, .55), 3.8, srgb(0xa8c8e8), .7)
camera((-5.5, 6.5, 6.5), (0, -.5, .6), 30)
render('hero')
print('DONE')
