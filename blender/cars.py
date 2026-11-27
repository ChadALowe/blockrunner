import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import bpy, bmesh, math, sys, os
from mathutils import Vector

OUT = f'{BDIR}/out'
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------------- materials ----------------
def mat(name, col, rough=.5, metal=0., emit=None):
    m = bpy.data.materials.get(name)
    if m: return m
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*col, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if emit:
        b.inputs['Emission Color'].default_value = (*emit, 1)
        b.inputs['Emission Strength'].default_value = 1.5
    return m

def srgb(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return tuple((x / 12.92) if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in c)

COMMON = {
    'trim': mat('trim', srgb(0x1c1c1e), .8),
    'glass': mat('glass', srgb(0x1e2a36), .15, .2),
    'chrome': mat('chrome', srgb(0xc8ccd0), .25, .9),
    'tyre': mat('tyre', srgb(0x161616), .9),
    'hub': mat('hub', srgb(0xb9bcc0), .3, .8),
    'headlight': mat('headlight', srgb(0xfff4cf), .2, 0, srgb(0xfff0c0)),
    'taillight': mat('taillight', srgb(0xc81818), .3, 0, srgb(0xff2020)),
    'indicator': mat('indicator', srgb(0xffa020), .3, 0, srgb(0xff9010)),
    'white': mat('white', srgb(0xf2f2f2), .45),
    'lightRed': mat('lightRed', srgb(0x2050ff), .3, 0, srgb(0x2050ff)),   # UK: both halves of the bar are blue (name kept for the game)
    'lightBlue': mat('lightBlue', srgb(0x2050ff), .3, 0, srgb(0x2050ff)),
    'interior': mat('interior', srgb(0x2a2a2e), .9),
    'seat': mat('seat', srgb(0x4a3e36), .85),
    'battB': mat('battB', srgb(0x1f48b8), .4),
    'battY': mat('battY', srgb(0xd8e21a), .4, 0, srgb(0x6a7010)),
}

# ---------------- body loft ----------------
# key: (f, zb, wbot, wbelt, zbelt, wglass, wroof, zroof, crown)   f = forward (+ is front)
def interp(keys, f):
    keys = sorted(keys, key=lambda k: -k[0])
    if f >= keys[0][0]: return list(keys[0][1:])
    if f <= keys[-1][0]: return list(keys[-1][1:])
    for a, b in zip(keys, keys[1:]):
        if a[0] >= f >= b[0]:
            t = (a[0] - f) / (a[0] - b[0]) if a[0] != b[0] else 0
            return [x + (y - x) * t for x, y in zip(a[1:], b[1:])]

def build_body(name, keys, wheels_f, arch_z, zones, band_mat, mats, door=None, open_rear=False):
    # door: (front_f, back_f) or a list of (front_f, back_f, suffix); suffix 'b' = rear doors
    doors_in = [] if not door else ([(door[0], door[1], '')] if isinstance(door[0], (int, float)) else list(door))
    fs = set(k[0] for k in keys)
    for d in doors_in: fs.add(d[0]); fs.add(d[1])
    for wf in wheels_f:
        for d in (-.56, -.45, .45, .56): fs.add(round(wf + d, 4))
    fs = sorted(fs, reverse=True)
    mesh = bpy.data.meshes.new(name); obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    names = list(mats.keys())
    for n in names: mesh.materials.append(mats[n])
    bm = bmesh.new(); rings = []; ringpts = []
    for f in fs:
        zb, wbot, wbelt, zbelt, wglass, wroof, zroof, crown = interp(keys, f)
        for wf in wheels_f:
            if abs(f - wf) <= .4501: zb = max(zb, arch_z)
        right = [(0, zb), (wbot, zb), (wbelt, zbelt), (wglass, zbelt + .03), (wroof, zroof), (0, zroof + crown)]
        pts = right + [(-x, z) for x, z in reversed(right[1:-1])]
        rings.append([bm.verts.new((x, -f, z)) for x, z in pts]); ringpts.append([(x, -f, z) for x, z in pts])
    band_of = [0, 1, 2, 3, 4, 4, 3, 2, 1, 0]
    for s in range(len(rings) - 1):
        fm = (fs[s] + fs[s + 1]) / 2
        zone = 'body'
        for (hi, lo, z) in zones:
            if hi >= fm >= lo: zone = z
        A, B = rings[s], rings[s + 1]
        indoor = any(fs[s] <= d[0] + 1e-6 and fs[s + 1] >= d[1] - 1e-6 for d in doors_in)
        for i in range(10):
            j = (i + 1) % 10
            if indoor and i in (1, 2, 3, 6, 7, 8): continue
            try: fc = bm.faces.new((A[i], A[j], B[j], B[i]))
            except ValueError: continue
            fc.material_index = names.index(band_mat(zone, band_of[i]))
    cap = bm.faces.new(rings[0]); cap.material_index = names.index(band_mat('front', 2))
    if not open_rear:
        cap = bm.faces.new(list(reversed(rings[-1]))); cap.material_index = names.index(band_mat('rear', 2))
    bmesh.ops.dissolve_degenerate(bm, dist=1e-4, edges=bm.edges[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(mesh); bm.free()
    doors = {}
    for door in doors_in:
        for side, idxs in (('l', (1, 2, 3)), ('r', (6, 7, 8))):
            dn = name + '_door_' + door[2] + side
            dm = bpy.data.meshes.new(dn); do = bpy.data.objects.new(dn, dm)
            bpy.context.collection.objects.link(do)
            for n in names: dm.materials.append(mats[n])
            db = bmesh.new()
            for s in range(len(fs) - 1):
                if not (fs[s] <= door[0] + 1e-6 and fs[s + 1] >= door[1] - 1e-6): continue
                fm = (fs[s] + fs[s + 1]) / 2; zone = 'body'
                for (hi, lo, z) in zones:
                    if hi >= fm >= lo: zone = z
                for i in idxs:
                    j = (i + 1) % 10
                    vs = [db.verts.new(ringpts[s][i]), db.verts.new(ringpts[s][j]), db.verts.new(ringpts[s + 1][j]), db.verts.new(ringpts[s + 1][i])]
                    fc = db.faces.new(vs); fc.material_index = names.index(band_mat(zone, band_of[i]))
            bmesh.ops.remove_doubles(db, verts=db.verts[:], dist=1e-5)
            db.normal_update()
            sgn = 1 if side == 'l' else -1
            for fc in db.faces:
                if fc.normal.x * sgn < 0: fc.normal_flip()
            db.to_mesh(dm); db.free()
            doors[(door[2] + side, door[0])] = do
    return obj, doors

def box(name, size, loc, m, rot=(0, 0, 0), bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object; o.name = name; o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    o.data.materials.append(m)
    if bevel:
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=bevel, segments=1, affect='EDGES')
        bm.to_mesh(o.data); bm.free()
    return o

def wheel(name, x, f, r, w):
    bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=r, depth=w, location=(x, -f, r), rotation=(0, math.pi / 2, 0))
    t = bpy.context.object; t.data.materials.append(COMMON['tyre'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=r * .58, depth=w + .03, location=(x, -f, r), rotation=(0, math.pi / 2, 0))
    h = bpy.context.object; h.data.materials.append(COMMON['hub'])
    for k in range(3):
        a = k * math.pi / 3
        s = box('spoke', (w + .05, r * 1.05, .07), (x, -f, r), COMMON['trim'], rot=(a, 0, 0))
    objs = [t, h] + [o for o in bpy.context.scene.objects if o.name.startswith('spoke')]
    join(objs, name)
    o = bpy.data.objects[name]
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    return o

def join(objs, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name; objs[0].data.name = name
    return objs[0]

def smooth(o, deg=32):
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    try: bpy.ops.object.shade_auto_smooth(angle=math.radians(deg))
    except Exception: bpy.ops.object.shade_flat()

def default_band(zone, band, paint='paint'):
    if band == 0: return 'trim'
    if zone in ('front', 'rear'): return paint
    if band == 3 and zone in ('ws', 'cabin', 'rw', 'side'): return 'glass'
    if band == 4 and zone in ('ws', 'rw'): return 'glass'
    return paint

# ---------------- car designs ----------------
def car_common_details(parts, cfg):
    nf, nz, tf, tz = cfg['nose_f'], cfg['nose_z'], cfg['tail_f'], cfg['tail_z']
    bmat = COMMON[cfg.get('bumper', 'chrome')]
    parts.append(box('fb', (2.0, .24, .22), (0, -(nf + .06), cfg.get('bump_z', .44)), bmat, bevel=.03))
    parts.append(box('rb', (2.0, .24, .22), (0, -(tf - .06), cfg.get('bump_z', .44)), bmat, bevel=.03))
    for s in (-1, 1):
        parts.append(box('hl', (.42, .06, .15), (s * .62, -(nf + .005), nz), COMMON['headlight']))
        parts.append(box('ind', (.14, .06, .1), (s * .92, -(nf - .01), nz - .02), COMMON['indicator']))
        if 'tl' in cfg: parts.append(box('tl', cfg['tl'][0], (s * cfg['tl'][1], -(tf - .005), tz), COMMON['taillight']))
        else: parts.append(box('tl', (.4, .06, .14), (s * .66, -(tf - .005), tz), COMMON['taillight']))
    parts.append(box('grille', (.7, .05, .14), (0, -(nf + .01), nz), COMMON['trim']))
    parts.append(box('plateF', (.5, .03, .12), (0, -(nf + .2), cfg.get('bump_z', .44)), COMMON['white']))
    parts.append(box('plateR', (.5, .03, .14), (0, -(tf - .2), cfg.get('bump_z', .44) + .02), COMMON['white']))

def battenburg(cfg):
    """returns {'body': [...], 'l'/'r'/'bl'/'br': [...]} of check squares (UK police livery)"""
    out = {'body': []}; secs = [(2.02, .80, 'body'), (.80, -.30, ''), (-.36, -.92, 'b'), (-.92, -2.04, 'body')]
    k0 = 0
    for f0, f1, key in secs:
        n = max(1, round((f0 - f1) / .4)); L = (f0 - f1) / n
        for i in range(n):
            fc = f0 - L * (i + .5)
            for row, (z0, z1) in enumerate(((.62, .80), (.80, .98))):
                if row == 0 and any(abs(fc - wf) < .52 for wf in cfg['wheels_f']): continue
                for side, sgn in (('l', 1), ('r', -1)):
                    m = COMMON['battB'] if (k0 + i + row) % 2 == 0 else COMMON['battY']
                    b = box('chk', (.025, L - .005, z1 - z0), (sgn * 1.004, -fc, (z0 + z1) / 2), m)
                    out.setdefault('body' if key == 'body' else key + side, []).append(b)
        k0 += n
    return out

def police_text(parts):
    """POLICE on the bonnet, reading for the driver in front looking in the mirror (reversed) is overkill: plain, facing up"""
    try:
        bpy.ops.object.text_add(location=(0, -1.55, 1.005)); t = bpy.context.object; t.data.body = 'POLICE'; t.data.size = .26; t.data.extrude = .004
        t.data.align_x = 'CENTER'; t.data.align_y = 'CENTER'; t.rotation_euler = (0, 0, math.pi)
        bpy.ops.object.convert(target='MESH'); t.data.materials.clear(); t.data.materials.append(COMMON['battB']); parts.append(t)
    except Exception as e:
        print('police text skipped', e)

def build_car(cfg, x_off):
    pid = cfg['id']
    COMMON['paint_' + pid] = mat('paint_' + pid, srgb(cfg['color']), .35, .1)
    mats = {'paint': COMMON['paint_' + pid], 'trim': COMMON['trim'], 'glass': COMMON['glass'], 'white': COMMON['white']}
    body, doors = build_body('body_' + pid, cfg['keys'], cfg['wheels_f'], cfg['arch_z'], cfg['zones'], cfg.get('band', default_band), mats, cfg['door'], cfg.get('open_rear', False))
    parts = [body]
    car_common_details(parts, cfg)
    interior(parts, cfg)
    if 'extra' in cfg: cfg['extra'](parts)
    checks = battenburg(cfg) if cfg.get('checks') else {}
    parts += checks.get('body', [])
    b = join(parts, pid + '_body')
    door_objs = list(cfg['rear_doors']()) if 'rear_doors' in cfg else []
    smooth(b)
    for (side, hinge_f), d in doors.items():
        sgn = 1 if side.endswith('l') else -1
        extra_ = checks.get(side, [])
        if len(side) == 1:
            mm = COMMON['paint_' + pid] if cfg.get('mirror_paint') else COMMON['trim']
            mir = box('mir', (.16, .1, .12), (sgn * 1.07, -(hinge_f - .1), cfg['mirror_z']), mm)
            d = join([d, mir] + extra_, pid + '_door_' + side)
        else:
            d = join([d] + extra_, pid + '_door_' + side) if extra_ else d; d.name = pid + '_door_' + side
        bpy.context.scene.cursor.location = (sgn * 1.0, -hinge_f, 0)
        bpy.ops.object.select_all(action='DESELECT'); d.select_set(True); bpy.context.view_layer.objects.active = d
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        smooth(d); door_objs.append(d)
    wheels = []
    r = cfg['wheel_r']
    for nm, sx, f in (('wheel_fl', 1, cfg['wheels_f'][0]), ('wheel_fr', -1, cfg['wheels_f'][0]), ('wheel_rl', 1, cfg['wheels_f'][1]), ('wheel_rr', -1, cfg['wheels_f'][1])):
        w = wheel(pid + '_' + nm, sx * .95, f, r, .3); smooth(w, 50); wheels.append(w)
    root = bpy.data.objects.new(pid, None); bpy.context.collection.objects.link(root)
    for o in [b] + wheels + door_objs: o.parent = root
    root.location.x = x_off
    return root

def interior(parts, cfg):
    I = cfg['inside']; sf, sz, fl = I['seat_f'], I['seat_z'], I['floor']
    parts.append(box('floor', (1.86, I['len'], .04), (0, -I['floor_f'], fl), COMMON['interior']))
    for x in (-.45, .45):
        parts.append(box('cush', (.56, .56, .14), (x, -sf, sz - .07), COMMON['seat']))
        parts.append(box('back', (.56, .12, .72), (x, -(sf - .34), sz + .3), COMMON['seat'], rot=(-.18, 0, 0)))
        parts.append(box('legs', (.5, .3, sz - fl), (x, -sf, (sz + fl) / 2 - .07), COMMON['interior']))
    if I.get('bench'):
        bo = I.get('bench_off', .95)
        parts.append(box('bench', (1.6, .56, .14), (0, -(sf - bo), sz - .07), COMMON['seat']))
        parts.append(box('benchb', (1.6, .12, .6), (0, -(sf - bo - .32), sz + .26), COMMON['seat'], rot=(-.18, 0, 0)))
    if I.get('cargo'):
        cf0, cf1 = I['cargo']; cl = cf0 - cf1
        parts.append(box('cfloor', (1.86, cl, .04), (0, -(cf0 + cf1) / 2, fl), COMMON['interior']))
        for sg in (-1, 1):
            parts.append(box('cbench', (.4, cl - .3, .12), (sg * .5, -(cf0 + cf1) / 2, sz - .07), COMMON['seat']))
            parts.append(box('cbleg', (.32, cl - .4, sz - fl - .1), (sg * .5, -(cf0 + cf1) / 2, (sz + fl) / 2 - .1), COMMON['interior']))
            parts.append(box('cbback', (.08, cl - .3, .55), (sg * .75, -(cf0 + cf1) / 2, sz + .32), COMMON['seat']))
    if I.get('bulk'):
        parts.append(box('bulk', (1.9, .06, I['bulk'][1]), (0, -I['bulk'][0], fl + I['bulk'][1] / 2), COMMON['interior']))
    parts.append(box('dash', (1.86, .42, .3), (0, -I['dash_f'], I['dash_z']), COMMON['interior']))
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=.19, depth=.05, location=(-.45, -I['wheel_f'], I['wheel_z']), rotation=(math.radians(62), 0, 0))
    w = bpy.context.object; w.data.materials.append(COMMON['trim']); parts.append(w)
    parts.append(box('col', (.06, .3, .06), (-.45, -(I['wheel_f'] + .14), I['wheel_z'] - .07), COMMON['trim'], rot=(math.radians(-28), 0, 0)))

SALOON_KEYS = [
    (2.22, .42, .92, .95, .74, .88, .88, .78, .02),
    (2.08, .34, .96, 1.0, .93, .90, .90, .97, .03),
    (0.92, .32, .98, 1.0, 1.00, .90, .90, 1.05, .04),
    (0.82, .32, .98, 1.0, 1.01, .90, .88, 1.06, .04),
    (0.02, .32, .98, 1.0, 1.02, .88, .76, 1.65, .05),
    (-1.52, .32, .98, 1.0, 1.02, .88, .76, 1.62, .05),
    (-1.94, .32, .98, 1.0, 1.03, .90, .88, 1.08, .04),
    (-2.08, .34, .96, 1.0, 1.00, .90, .90, 1.05, .03),
    (-2.22, .42, .92, .95, .82, .88, .88, .86, .02)]
SALOON_ZONES = [(.82, .02, 'ws'), (.02, -1.52, 'cabin'), (-1.52, -1.94, 'rw')]

def saloon_extra(parts):
    pass

def police_band(zone, band):
    if band == 0: return 'trim'
    if zone == 'cabin' and band in (1, 2): return 'white'
    if zone == 'cabin' and band == 4: return 'white'
    return default_band(zone, band)

def police_extra(parts):
    parts.append(box('barbase', (1.3, .34, .1), (0, .45, 1.73), COMMON['trim']))
    parts.append(box('barR', (.58, .3, .14), (.33, .45, 1.83), COMMON['lightRed'], bevel=.03))
    police_text(parts)
    parts.append(box('barB', (.58, .3, .14), (-.33, .45, 1.83), COMMON['lightBlue'], bevel=.03))
    parts.append(box('push', (1.5, .12, .5), (0, -2.42, .55), COMMON['trim']))
    for s in (-1, 1): parts.append(box('pushbar', (.1, .3, .5), (s * .6, -2.3, .55), COMMON['trim']))
    parts.append(box('spot', (.12, .22, .12), (1.0, -.9, 1.14), COMMON['chrome']))

SPORTS_KEYS = [
    (2.26, .30, .90, .94, .56, .86, .86, .58, .02),
    (2.10, .27, .96, 1.0, .70, .88, .88, .74, .03),
    (0.50, .27, .98, 1.02, .86, .86, .86, .90, .05),
    (0.40, .27, .98, 1.02, .87, .86, .84, .91, .04),
    (-0.40, .27, .98, 1.02, .89, .86, .78, 1.53, .04),
    (-1.34, .27, .98, 1.02, .91, .86, .78, 1.50, .04),
    (-1.86, .27, .98, 1.02, .95, .88, .86, .98, .03),
    (-2.12, .29, .96, 1.0, .95, .88, .88, .99, .02),
    (-2.26, .33, .92, .96, .82, .86, .86, .85, .02)]
SPORTS_ZONES = [(.40, -.40, 'ws'), (-.40, -1.34, 'cabin'), (-1.34, -1.86, 'rw')]

def sports_extra(parts):
    for s in (-1, 1): parts.append(box('post', (.08, .1, .2), (s * .7, 2.08, 1.07), COMMON['trim']))
    parts.append(box('wing', (1.9, .34, .06), (0, 2.12, 1.18), COMMON['paint_sports'], bevel=.02))
    parts.append(box('scoop', (.6, .5, .08), (0, -1.1, .9), COMMON['trim'], rot=(-0.06,0,0)))
    for s in (-1, 1): parts.append(box('sidevent', (.04, .4, .14), (s * 1.02, 1.25, .7), COMMON['trim']))

VAN_KEYS = [
    (2.24, .42, .92, .95, .80, .90, .90, .84, .02),
    (2.06, .36, .96, 1.0, 1.02, .92, .92, 1.08, .03),
    (1.45, .36, .98, 1.0, 1.12, .92, .90, 1.16, .03),
    (0.95, .36, .98, 1.0, 1.14, .92, .88, 2.12, .04),
    (0.25, .36, .98, 1.0, 1.14, .92, .88, 2.13, .04),
    (-2.14, .36, .98, 1.0, 1.14, .92, .88, 2.16, .04),
    (-2.24, .40, .96, .98, 1.14, .92, .88, 2.14, .03)]
VAN_ZONES = [(1.45, .95, 'ws'), (.95, .25, 'side')]

def van_extra(parts):
    for s in (-1, 1):
        parts.append(box('stripe', (.03, 2.3, .16), (s * 1.0, 1.05, 1.32), COMMON['white']))
        parts.append(box('stripe2', (.03, 2.3, .06), (s * 1.0, 1.05, 1.18), COMMON['trim']))
    # frame around the rear opening (the rear cap is left open for the back doors)
    P = COMMON['paint_van']
    for s in (-1, 1): parts.append(box('rpost', (.1, .08, 1.72), (s * .93, 2.2, 1.28), P))
    parts.append(box('rhead', (1.96, .08, .14), (0, 2.2, 2.08), P))
    parts.append(box('rsill', (1.96, .1, .14), (0, 2.2, .45), P))

def van_rear_doors():
    # two back doors hinged on the outer posts (origin = hinge), panel + window + handle
    out = []; P = COMMON['paint_van']
    for side, sgn in (('bl', 1), ('br', -1)):
        pan = box('rdp', (.86, .05, 1.52), (sgn * .45, 2.235, 1.29), P, bevel=.015)
        win = box('rdw', (.62, .02, .42), (sgn * .47, 2.262, 1.7), COMMON['glass'])
        hd = box('rdh', (.14, .04, .05), (sgn * .1, 2.27, 1.2), COMMON['trim'])
        d = join([pan, win, hd], 'van_door_' + side)
        bpy.context.scene.cursor.location = (sgn * .9, 2.24, 0)
        bpy.ops.object.select_all(action='DESELECT'); d.select_set(True); bpy.context.view_layer.objects.active = d
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR'); smooth(d)
        out.append(d)
    return out
    parts.append(box('roofrack', (1.5, 2.4, .06), (0, .6, 2.24), COMMON['trim']))

CARS = [
    dict(id='saloon', label='Saloon', color=0x7a1c22, keys=SALOON_KEYS, zones=SALOON_ZONES, wheels_f=(1.38, -1.38), arch_z=.8, wheel_r=.38,
         nose_f=2.22, nose_z=.78, tail_f=-2.22, tail_z=.86, mirror_f=.7, mirror_z=1.09, extra=saloon_extra, door=[(.80, -.30, ''), (-.36, -.92, 'b')], inside=dict(seat_f=-.32, seat_z=.5, floor=.4, floor_f=-.6, len=2.4, dash_f=.62, dash_z=.92, wheel_f=.36, wheel_z=.92, bench=True, bench_off=.72)),
    dict(id='sports', label='Sports coupe', color=0xd4a017, keys=SPORTS_KEYS, zones=SPORTS_ZONES, wheels_f=(1.42, -1.38), arch_z=.74, wheel_r=.36,
         nose_f=2.26, nose_z=.6, tail_f=-2.26, tail_z=.86, mirror_f=.3, mirror_z=.95, bumper='trim', bump_z=.36, mirror_paint=True, extra=sports_extra, door=(.36, -1.0), inside=dict(seat_f=-.8, seat_z=.38, floor=.3, floor_f=-.75, len=1.9, dash_f=.15, dash_z=.74, wheel_f=-.14, wheel_z=.74)),
    dict(id='van', label='Van', color=0x2c5d8f, keys=VAN_KEYS, zones=VAN_ZONES, wheels_f=(1.4, -1.3), arch_z=.84, wheel_r=.4,
         nose_f=2.24, nose_z=.84, tail_f=-2.24, tail_z=1.0, mirror_f=1.35, mirror_z=1.24, extra=van_extra, door=(.92, .22), open_rear=True, rear_doors=van_rear_doors, tl=((.08, .06, .34), .94), inside=dict(seat_f=.42, seat_z=.74, floor=.46, floor_f=.7, len=1.4, dash_f=1.2, dash_z=1.12, wheel_f=.92, wheel_z=1.12, bulk=(.0, 1.6), cargo=(-.05, -2.16))),
    dict(id='police', label='Police car', color=0xf4f4f4, checks=True, keys=SALOON_KEYS, zones=SALOON_ZONES, wheels_f=(1.38, -1.38), arch_z=.8, wheel_r=.38,
         nose_f=2.22, nose_z=.78, tail_f=-2.22, tail_z=.86, mirror_f=.7, mirror_z=1.09, extra=police_extra, door=[(.80, -.30, ''), (-.36, -.92, 'b')], inside=dict(seat_f=-.32, seat_z=.5, floor=.4, floor_f=-.6, len=2.4, dash_f=.62, dash_z=.92, wheel_f=.36, wheel_z=.92, bench=True, bench_off=.72)),
]

roots = {}
for k, cfg in enumerate(CARS):
    roots[cfg['id']] = build_car(cfg, 0)
    for o in [roots[cfg['id']]] + list(roots[cfg['id']].children): o.hide_render = True; o.hide_set(True)

# ---------------- export ----------------
for cfg in CARS:
    r = roots[cfg['id']]
    bpy.ops.object.select_all(action='DESELECT')
    for o in [r] + list(r.children): o.hide_set(False); o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=f"{BDIR}/../assets/cars/{cfg['id']}.glb", export_format='GLB', use_selection=True, export_apply=True)
    for o in [r] + list(r.children): o.hide_set(True)

if 'norender' in sys.argv: sys.exit(0)
# ---------------- render previews ----------------
bpy.ops.mesh.primitive_plane_add(size=60); g = bpy.context.object; g.data.materials.append(mat('ground', srgb(0x5a5b60), .9))
bpy.ops.object.light_add(type='SUN', rotation=(math.radians(48), 0, math.radians(35))); sun = bpy.context.object; sun.data.energy = 3.2; sun.data.angle = .1
w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xa8c8e8), 1); w.node_tree.nodes['Background'].inputs[1].default_value = .9; sc.world = w
try: sc.view_settings.view_transform = 'Standard'
except Exception: pass
sc.render.resolution_x = 900; sc.render.resolution_y = 560
bpy.ops.object.empty_add(location=(0, 0, .75)); tgt = bpy.context.object
bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 50
tc = cam.constraints.new('TRACK_TO'); tc.target = tgt
views = {'front': (6.2, -8.0, 3.0), 'rear': (-6.0, 7.6, 3.2), 'door': (-7.0, -5.5, 3.2)}
for cfg in CARS:
    r = roots[cfg['id']]
    for o in [r] + list(r.children): o.hide_render = False
    for vn, pos in views.items():
        cam.location = pos
        for o in r.children:
            if '_door_r' in o.name: o.rotation_euler.z = -1.15 if vn == 'door' else 0
        sc.render.filepath = f"{OUT}/{cfg['id']}_{vn}.png"
        bpy.ops.render.render(write_still=True)
    for o in [r] + list(r.children): o.hide_render = True
print('DONE')
