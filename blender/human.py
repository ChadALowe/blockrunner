"""Rigged low-poly humans for Block Runner.
Builds a body from skin-modifier parts (torso, arms, legs, feet) + head, a skeleton,
distance-based weights restricted per part, recolourable materials, and animations.
Character faces -Y in Blender (glTF/three: +Z forward)."""
import os; BDIR = os.path.dirname(os.path.abspath(__file__))
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Euler
from mathutils.bvhtree import BVHTree

OUT = f'{BDIR}/people'
os.makedirs(OUT, exist_ok=True)

def srgb(h):
    c = [((h >> 16) & 255) / 255, ((h >> 8) & 255) / 255, (h & 255) / 255]
    return tuple((x / 12.92) if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in c)

def mat(name, col, rough=.75):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*srgb(col), 1); b.inputs['Roughness'].default_value = rough
    return m

# ------------------------------------------------------------------ body specs
def spec(kind):
    f = kind == 'female'
    if f:
        torso = [(.86, .12, .09, 0), (.95, .172, .11, 0), (1.0, .17, .108, 0), (1.08, .128, .088, 0), (1.17, .14, .1, -.005),
                 (1.26, .155, .122, -.018), (1.34, .158, .11, -.01), (1.4, .158, .094, 0), (1.44, .14, .084, .004), (1.475, .1, .07, .008),
                 (1.5, .066, .06, .008), (1.512, .058, .056, .008), (1.6, .05, .05, .01)]
        sh = .17
    else:
        torso = [(.86, .13, .095, 0), (.93, .168, .112, 0), (.99, .172, .112, 0), (1.08, .162, .108, 0), (1.18, .174, .118, -.004),
                 (1.28, .198, .127, -.008), (1.35, .208, .122, -.006), (1.4, .206, .108, 0), (1.44, .18, .096, .004), (1.475, .126, .082, .008),
                 (1.5, .082, .072, .008), (1.512, .074, .068, .008), (1.6, .067, .065, .01)]
        sh = .215
    k = .9 if f else 1.
    return dict(torso=torso, shoulder=(sh, 1.42), elbow=(sh + .025, 1.135), wrist=(sh + .045, .875), hand=(sh + .058, .75),
                arm=[(sh - .075, 1.415, .046 * k), (sh - .012, 1.39, .056 * k), (sh + .01, 1.27, .053 * k), (sh + .025, 1.135, .047 * k),
                     (sh + .035, 1.0, .046 * k), (sh + .04, .905, .045 * k), (sh + .045, .875, .033 * k)],
                hip=(.1, .92), knee=(.106, .5), ankle=(.11, .1),
                leg=[(.095, 1.0, .1 * k), (.1, .9, .1 * (1.04 if f else 1)), (.104, .7, .088 * k), (.106, .5, .074 * k), (.108, .3, .07 * k), (.11, .13, .068 * k), (.11, .075, .07 * k)],
                toe=-.21, head_c=(0, -.008, 1.71), head_r=(.128, .132, .148) if f else (.132, .136, .152))

# ------------------------------------------------------------------ helpers
def skin_part(name, verts, edges, radii, root=0):
    me = bpy.data.meshes.new(name); ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    me.from_pydata(verts, edges, [])
    sk = ob.modifiers.new('skin', 'SKIN'); sk.use_smooth_shade = True
    for i, r in enumerate(radii):
        me.skin_vertices[0].data[i].radius = r
    me.skin_vertices[0].data[root].use_root = True
    sub = ob.modifiers.new('sub', 'SUBSURF'); sub.levels = 1; sub.render_levels = 1
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
    return ob

def seg_dist(p, a, b):
    ab = b - a; t = max(0., min(1., (p - a).dot(ab) / ab.length_squared)); return (p - (a + ab * t)).length


def tube(name, pts, radii, segs=10, subdiv=1):
    """Lofted tube along pts with elliptical radii (rx along side axis, ry along the other)."""
    bm = bmesh.new(); rings = []
    P = [Vector(p) for p in pts]
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        ref = Vector((0, -1, 0)) if abs(t.y) < .9 else Vector((0, 0, 1))
        u = t.cross(ref).normalized(); v = u.cross(t).normalized()
        if u.x < 0: u = -u; v = -v
        rx, ry = radii[i]
        rings.append([bm.verts.new(p + u * rx * math.cos(a) + v * ry * math.sin(a)) for a in [k / segs * math.tau for k in range(segs)]])
    for a, b in zip(rings, rings[1:]):
        for k in range(segs):
            bm.faces.new((a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]))
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    if subdiv:
        m = ob.modifiers.new('sub', 'SUBSURF'); m.levels = subdiv
        bpy.context.view_layer.objects.active = ob; bpy.ops.object.modifier_apply(modifier='sub')
    return ob

def weight_part(ob, bones, allowed, power=5, override=None):
    """bones: name -> (head, tail) world vectors; allowed: list of bone names"""
    for n in allowed:
        if n not in ob.vertex_groups: ob.vertex_groups.new(name=n)
    for v in ob.data.vertices:
        p = ob.matrix_world @ v.co
        if override:
            res = override(p)
            if res:
                for n, w in res.items(): ob.vertex_groups[n].add([v.index], w, 'REPLACE')
                continue
        ds = {n: max(1e-4, seg_dist(p, *bones[n])) for n in allowed}
        ws = {n: 1 / d ** power for n, d in ds.items()}
        tot = sum(ws.values())
        top = sorted(ws.items(), key=lambda kv: -kv[1])[:2]
        t2 = sum(w for _, w in top)
        for n, w in top: ob.vertex_groups[n].add([v.index], w / t2, 'REPLACE')

def assign_mats(ob, fn):
    """fn(face_center, dominant_bone) -> material name"""
    vg = {g.index: g.name for g in ob.vertex_groups}
    for poly in ob.data.polygons:
        c = ob.matrix_world @ poly.center
        best = {}
        for vi in poly.vertices:
            for g in ob.data.vertices[vi].groups:
                best[vg[g.group]] = best.get(vg[g.group], 0) + g.weight
        dom = max(best, key=best.get) if best else ''
        name = fn(c, dom)
        poly.material_index = [m.name for m in ob.data.materials].index(name)

def add_mats(ob, names):
    for n in names: ob.data.materials.append(bpy.data.materials[n])

# ------------------------------------------------------------------ texture bake (AO + creases + seams)
def _band(nt, z, a, b, k):
    gt = nt.nodes.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; nt.links.new(z, gt.inputs[0]); gt.inputs[1].default_value = a
    lt = nt.nodes.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'; nt.links.new(z, lt.inputs[0]); lt.inputs[1].default_value = b
    m = nt.nodes.new('ShaderNodeMath'); m.operation = 'MULTIPLY'; nt.links.new(gt.outputs[0], m.inputs[0]); nt.links.new(lt.outputs[0], m.inputs[1])
    s_ = nt.nodes.new('ShaderNodeMath'); s_.operation = 'MULTIPLY'; nt.links.new(m.outputs[0], s_.inputs[0]); s_.inputs[1].default_value = k
    return s_.outputs[0]
SEAMS = {  # material: [(zmin, zmax, darken)]
    'pants': [(.975, 1.03, .35)],
    'shirt': [(1.488, 1.506, .12)],
    'shoes': [(0, .028, .6), (.085, .1, .25)]}
CLOTH = {}
def bake_body(body, kind):
    import numpy as np
    sc = bpy.context.scene; sc.render.engine = 'CYCLES'; sc.cycles.samples = 40; sc.cycles.device = 'CPU'
    if not sc.world: sc.world = bpy.data.worlds.new('bw')
    sc.world.light_settings.distance = .22
    N = 512
    ao = bpy.data.images.new('ao', N, N); det = bpy.data.images.new('det', N, N)
    mats = [s.material for s in body.material_slots]
    saved = {}
    for m in mats:
        nt = m.node_tree; im = nt.nodes.new('ShaderNodeTexImage'); im.name = 'BAKE'; im.image = ao
        for n in nt.nodes: n.select = False
        im.select = True; nt.nodes.active = im
        b = nt.nodes['Principled BSDF']; saved[m.name] = tuple(b.inputs['Base Color'].default_value)
    bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
    bpy.ops.object.bake(type='AO', margin=6)
    # creases + seams as a colour pass
    for m in mats:
        nt = m.node_tree; b = nt.nodes['Principled BSDF']; nt.nodes['BAKE'].image = det
        tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); nt.links.new(tc.outputs['Object'], sep.inputs[0])
        z = sep.outputs['Z']
        val = nt.nodes.new('ShaderNodeValue'); val.outputs[0].default_value = 1.0; out = val.outputs[0]
        if m.name in CLOTH and CLOTH[m.name][0]:
            sc_, det_ = CLOTH[m.name]
            wv = nt.nodes.new('ShaderNodeTexWave'); wv.wave_type = 'BANDS'; wv.bands_direction = 'Z'; wv.inputs['Scale'].default_value = sc_ * 3
            wv.inputs['Distortion'].default_value = det_; wv.inputs['Detail'].default_value = 3; nt.links.new(tc.outputs['Object'], wv.inputs['Vector'])
            mr = nt.nodes.new('ShaderNodeMapRange'); nt.links.new(wv.outputs['Fac'], mr.inputs['Value']); mr.inputs['To Min'].default_value = .9; mr.inputs['To Max'].default_value = 1.0
            out = mr.outputs['Result']
        for (a, bb, k) in SEAMS.get(m.name, []):
            if k <= 0: continue
            bd = _band(nt, z, a, bb, k); sub = nt.nodes.new('ShaderNodeMath'); sub.operation = 'SUBTRACT'
            nt.links.new(out, sub.inputs[0]); nt.links.new(bd, sub.inputs[1]); out = sub.outputs[0]
        cmb = nt.nodes.new('ShaderNodeCombineColor'); [nt.links.new(out, cmb.inputs[i]) for i in range(3)]
        nt.links.new(cmb.outputs[0], b.inputs['Base Color'])
    sc.render.bake.use_pass_direct = False; sc.render.bake.use_pass_indirect = False; sc.render.bake.use_pass_color = True
    bpy.ops.object.bake(type='DIFFUSE', margin=6)
    a = np.empty(N * N * 4, np.float32); ao.pixels.foreach_get(a); d = np.empty(N * N * 4, np.float32); det.pixels.foreach_get(d)
    a = a.reshape(-1, 4); d = d.reshape(-1, 4)
    av = np.clip(a[:, :1], 0, 1) ** .5 * .45 + .55
    f = np.clip(av * d[:, :3], 0, 1)
    fin = bpy.data.images.new('body_' + kind, N, N); px = np.concatenate([f, np.ones((N * N, 1), np.float32)], 1).ravel()
    fin.pixels.foreach_set(px); fin.file_format = 'JPEG'; fin.pack()
    for m in mats:   # final: texture drives base colour (the game multiplies by each zone's colour)
        nt = m.node_tree; b = nt.nodes['Principled BSDF']
        for n in list(nt.nodes):
            if n.name not in ('Principled BSDF', 'Material Output'): nt.nodes.remove(n)
        im = nt.nodes.new('ShaderNodeTexImage'); im.image = fin; nt.links.new(im.outputs['Color'], b.inputs['Base Color'])
    sc.render.engine = 'BLENDER_EEVEE' if 'BLENDER_EEVEE' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE_NEXT'

# ------------------------------------------------------------------ build
def build(kind, hair_styles):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    S = spec(kind)
    for n, c in (('skin', 0xc99a78), ('shirt', 0xe8e8e8), ('pants', 0x34507e), ('shoes', 0x222222), ('hair', 0x2a1a10),
                 ('eyes', 0x141414), ('white', 0xf2efe8), ('mouth', 0x7a3a34), ('hat', 0x101830), ('badge', 0xd8c050), ('sleeve', 0xe8e8e8), ('shoulder', 0xe8e8e8), ('shin', 0x34507e), ('beard', 0x2a1a10), ('jacket', 0x3a3a3a), ('face', 0xffffff), ('skinflat', 0xc99a78)):
        mat(n, c)
    # skeleton joints (world)
    sh, el, wr, ha = S['shoulder'], S['elbow'], S['wrist'], S['hand']
    hp, kn, an = S['hip'], S['knee'], S['ankle']
    J = {}
    J['hips'] = (Vector((0, 0, .93)), Vector((0, 0, 1.08)))
    J['spine'] = (Vector((0, 0, 1.08)), Vector((0, 0, 1.26)))
    J['chest'] = (Vector((0, 0, 1.26)), Vector((0, 0, 1.47)))
    J['neck'] = (Vector((0, 0, 1.47)), Vector((0, 0, 1.58)))
    J['head'] = (Vector((0, 0, 1.58)), Vector((0, 0, 1.82)))
    for s, sx in (('L', 1), ('R', -1)):
        J['upperarm_' + s] = (Vector((sx * sh[0], 0, sh[1])), Vector((sx * el[0], 0, el[1])))
        J['forearm_' + s] = (Vector((sx * el[0], 0, el[1])), Vector((sx * wr[0], 0, wr[1])))
        J['hand_' + s] = (Vector((sx * wr[0], 0, wr[1])), Vector((sx * ha[0], -.01, ha[1])))
        J['thigh_' + s] = (Vector((sx * hp[0], 0, hp[1])), Vector((sx * kn[0], -.01, kn[1])))
        J['shin_' + s] = (Vector((sx * kn[0], -.01, kn[1])), Vector((sx * an[0], .01, an[1])))
        J['foot_' + s] = (Vector((sx * an[0], .01, an[1])), Vector((sx * an[0], S['toe'], .03)))
    parts = []
    # torso
    T = [(z, rx, ry * 1.12, yo) for z, rx, ry, yo in S['torso']]
    torso = tube('torso', [(0, yo, z) for z, rx, ry, yo in T], [(rx, ry) for z, rx, ry, yo in T], segs=12)
    weight_part(torso, J, ['hips', 'spine', 'chest', 'neck'])
    parts.append(torso)
    for s, sx in (('L', 1), ('R', -1)):
        A = S['arm']
        pts = [(sx * x, 0, z) for x, z, r in A] + [(sx * (wr[0] + .005), -.006, wr[1] - .03), (sx * (ha[0] - .002), -.012, ha[1] + .03), (sx * ha[0], -.014, ha[1] - .015)]
        rad = [(r, r) for x, z, r in A] + [(.052, .036), (.06, .038), (.046, .03)]
        a = tube('arm_' + s, pts, rad, segs=8)
        th = tube('thumb_' + s, [(sx * (wr[0] - .012), -.022, wr[1] - .035), (sx * (wr[0] - .02), -.04, wr[1] - .075), (sx * (wr[0] - .02), -.046, wr[1] - .1)],
                  [(.022, .02), (.019, .018), (.015, .014)], segs=6)
        bpy.ops.object.select_all(action='DESELECT'); a.select_set(True); th.select_set(True); bpy.context.view_layer.objects.active = a; bpy.ops.object.join()
        def ov(p, s=s):
            if abs(p.x) < sh[0] - .035 and p.z > 1.38: return {'chest': .7, 'upperarm_' + s: .3}
            return None
        weight_part(a, J, ['chest', 'upperarm_' + s, 'forearm_' + s, 'hand_' + s], override=ov)
        parts.append(a)
        L = S['leg']
        l = tube('leg_' + s, [(sx * x, 0, z) for x, z, r in L], [(r, r) for x, z, r in L], segs=10)
        weight_part(l, J, ['hips', 'thigh_' + s, 'shin_' + s])
        parts.append(l)
        ft = tube('foot_' + s, [(sx * an[0], .06, .075), (sx * an[0], .01, .07), (sx * an[0], -.09, .052), (sx * an[0], S['toe'] + .015, .045), (sx * an[0], S['toe'] - .012, .04)],
                  [(.056, .056), (.068, .064), (.07, .052), (.064, .044), (.044, .03)], segs=10)
        weight_part(ft, J, ['shin_' + s, 'foot_' + s])
        parts.append(ft)
    # head (+ face details)
    hc, hr = Vector(S['head_c']), S['head_r']
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, location=hc)
    head = bpy.context.object; head.name = 'headmesh'; head.scale = hr; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in head.data.vertices:
        if v.co.z < -.02: v.co.x *= 1 - min(.22, (-.02 - v.co.z) * 2.4)          # narrower jaw
        if v.co.z < -.05 and v.co.y < -.03: v.co.y -= .014; v.co.z -= .008        # chin
        if v.co.y > .05 and v.co.z > -.02: v.co.y += .008                        # rounder back of skull
    head_bvh = BVHTree.FromPolygons([v.co.copy() for v in head.data.vertices], [tuple(f.vertices) for f in head.data.polygons])   # the real head surface, before nose and ears
    face_parts = []
    def fbox(sz, loc, m):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o = bpy.context.object; o.scale = sz
        bpy.ops.object.transform_apply(scale=True); o.data.materials.append(bpy.data.materials[m]); face_parts.append(o); return o
    fy = hc.y - hr[1] + .006
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=.024, location=(0, fy - .006, hc.z - .02)); nz = bpy.context.object
    nz.scale = (1, .9, .85); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); nz.data.materials.append(bpy.data.materials['skinflat']); face_parts.append(nz)
    bm_ = bmesh.new(); bm_.from_mesh(nz.data)

    bm_.to_mesh(nz.data); bm_.free()
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=.028, location=(sx * (hr[0] - .006), hc.y + .01, hc.z - .01)); e_ = bpy.context.object
        e_.scale = (.5, .8, 1.1); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); e_.data.materials.append(bpy.data.materials['skinflat']); face_parts.append(e_)
    head.data.materials.append(bpy.data.materials['face'])
    bpy.ops.object.select_all(action='DESELECT')
    for o in [head] + face_parts: o.select_set(True)
    bpy.context.view_layer.objects.active = head; bpy.ops.object.join()
    head.vertex_groups.new(name='head'); head.vertex_groups['head'].add([v.index for v in head.data.vertices], 1., 'REPLACE')
    parts.append(head)
    # join body
    body_mats = ['skin', 'shirt', 'pants', 'shoes', 'sleeve', 'shoulder', 'shin']
    for p in parts:
        if p is head: continue
        add_mats(p, body_mats)
    def region(c, dom):
        if dom.startswith('foot'): return 'shoes'
        if dom.startswith('hand'): return 'skin'
        if dom.startswith('forearm') or dom.startswith('upperarm'): return 'shoulder' if c.z >= 1.27 else ('sleeve' if c.z > .955 else 'skin')
        if dom in ('neck', 'chest', 'spine') and c.z >= 1.506: return 'skin'
        if dom == 'neck': return 'shirt'
        if dom.startswith('shin') or dom.startswith('thigh'): return 'pants' if c.z >= .58 else 'shin'
        if dom == 'hips': return 'pants' if c.z < 1.0 else 'shirt'
        return 'shirt'
    for p in parts:
        if p is head: continue
        assign_mats(p, region)
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        if p is not head: p.select_set(True)
    bpy.context.view_layer.objects.active = torso; bpy.ops.object.join()
    body = torso; body.name = 'body'; body.data.name = 'body'
    for uvl in list(body.data.uv_layers): body.data.uv_layers.remove(uvl)
    body.data.uv_layers.new(name='UVMap')
    bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=.006)
    bpy.ops.object.mode_set(mode='OBJECT')
    bake_body(body, kind)
    bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); head.select_set(True); bpy.context.view_layer.objects.active = body; bpy.ops.object.join()
    # merge overlapping verts at seams lightly
    bpy.ops.object.shade_smooth()
    # ---------------- armature
    arm_data = bpy.data.armatures.new('rig'); rig = bpy.data.objects.new('rig', arm_data); bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode='EDIT')
    parent = {'hips': None, 'spine': 'hips', 'chest': 'spine', 'neck': 'chest', 'head': 'neck'}
    for s in 'LR':
        parent.update({'upperarm_' + s: 'chest', 'forearm_' + s: 'upperarm_' + s, 'hand_' + s: 'forearm_' + s,
                       'thigh_' + s: 'hips', 'shin_' + s: 'thigh_' + s, 'foot_' + s: 'shin_' + s})
    for n, (h, t) in J.items():
        eb = arm_data.edit_bones.new(n); eb.head = h; eb.tail = t; eb.roll = 0
    for n, p in parent.items():
        if p: arm_data.edit_bones[n].parent = arm_data.edit_bones[p]
    # thighs/ arms not connected (offset heads)
    bpy.ops.object.mode_set(mode='OBJECT')
    body.parent = rig
    mod = body.modifiers.new('rig', 'ARMATURE'); mod.object = rig
    # ---------------- hair / hats as separate rigid meshes bound to head
    extras = []
    def rigid(ob, matname):
        ob.data.materials.clear(); ob.data.materials.append(bpy.data.materials[matname])
        ob.vertex_groups.new(name='head'); ob.vertex_groups['head'].add([v.index for v in ob.data.vertices], 1., 'REPLACE')
        ob.parent = rig; m = ob.modifiers.new('rig', 'ARMATURE'); m.object = rig
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob; bpy.ops.object.shade_smooth()
        extras.append(ob); return ob
    def cap(name, grow, z0, tilt, extra=None):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, location=hc)
        o = bpy.context.object; o.scale = (hr[0] + grow, hr[1] + grow, hr[2] + grow * .6); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        sy, sz = (hr[1] + grow) / hr[1], (hr[2] + grow * .6) / hr[2]
        for v in o.data.vertices:                                               # same rounder back of skull as the head (same rings), so the skull never pokes through
            if v.co.y > .05 * sy and v.co.z > -.02 * sz: v.co.y += .008 * sy
        bm = bmesh.new(); bm.from_mesh(o.data)
        n = Vector((0, tilt, 1)).normalized()
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, z0), plane_no=n, clear_inner=True)
        bm.to_mesh(o.data); bm.free(); o.name = name
        if extra:
            parts_ = [o] + extra()
            bpy.ops.object.select_all(action='DESELECT')
            for x in parts_: x.select_set(True)
            bpy.context.view_layer.objects.active = o; bpy.ops.object.join()
        return o
    def hbox(sz, loc, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot); b = bpy.context.object; b.scale = sz; bpy.ops.object.transform_apply(scale=True)
        m = b.modifiers.new('bev', 'BEVEL'); m.width = .02; m.segments = 2; bpy.context.view_layer.objects.active = b; bpy.ops.object.modifier_apply(modifier='bev')
        return b
    def skinned(ob, matname, allowed):
        ob.data.materials.clear(); ob.data.materials.append(bpy.data.materials[matname])
        weight_part(ob, J, allowed)
        ob.parent = rig; m = ob.modifiers.new('rig', 'ARMATURE'); m.object = rig
        bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob; bpy.ops.object.shade_smooth()
        extras.append(ob); return ob
    def joinall(objs, name):
        bpy.ops.object.select_all(action='DESELECT')
        for x in objs: x.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]; bpy.ops.object.join(); objs[0].name = name; return objs[0]
    def sph(r, loc, scale=(1, 1, 1), seg=12, rings=8):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=loc); o = bpy.context.object
        o.scale = scale; bpy.ops.object.transform_apply(scale=True); return o
    def shell(name, grow, keep):
        """copy of the head sphere, grown, keeping only verts where keep(v.co) (head-local coords)"""
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=12, location=hc)
        o = bpy.context.object; o.scale = (hr[0] + grow, hr[1] + grow, hr[2] + grow); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        for v in o.data.vertices:
            if v.co.z < -.02: v.co.x *= 1 - min(.22, (-.02 - v.co.z) * 2.4)
            if v.co.z < -.05 and v.co.y < -.03: v.co.y -= .014; v.co.z -= .008
        bm = bmesh.new(); bm.from_mesh(o.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if not all(keep(v.co) for v in f.verts)], context='FACES')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
        bm.to_mesh(o.data); bm.free(); o.name = name; return o
    # ---------- hair (all styles; the game shows one)
    rigid(cap('hair_short', .011, .03, .5), 'hair')
    rigid(cap('hair_buzz', .009, .012, .35), 'hair')
    rigid(cap('hair_afro', .045, -.005, .3, lambda: [sph(.1, (hc.x, hc.y + .01, hc.z + .07), (1.25, 1.2, 1.0))]), 'hair')
    rigid(cap('hair_long', .016, .022, .75, lambda: [hbox((hr[0] * 1.9, .05, .2), (hc.x, hc.y + hr[1] * .62, hc.z - .1), (math.radians(-8), 0, 0)),
                                                      hbox((.035, .07, .18), (hc.x + hr[0] * .97, hc.y + .02, hc.z - .055)),
                                                      hbox((.035, .07, .18), (hc.x - hr[0] * .97, hc.y + .02, hc.z - .055))]), 'hair')
    rigid(cap('hair_bun', .012, .028, .55, lambda: [sph(.05, (hc.x, hc.y + hr[1] * .8, hc.z + .07))]), 'hair')
    rigid(cap('hair_bob', .02, -.03, .45, lambda: [hbox((hr[0] * 2.15, hr[1] * 1.6, .07), (hc.x, hc.y + .02, hc.z - .045))]), 'hair')
    rigid(cap('hair_pony', .012, .028, .55, lambda: [sph(.045, (hc.x, hc.y + hr[1] * .95, hc.z + .02), (.8, 1, 1.9))]), 'hair')
    def crest():
        # one smooth fin following the scalp from the forehead to the crown
        th0, th1, n, w = math.radians(-55), math.radians(66), 18, .015
        me = bpy.data.meshes.new('crest'); ob = bpy.data.objects.new('crest', me); bpy.context.collection.objects.link(ob)
        bm = bmesh.new(); rows = []
        for k in range(n + 1):
            t = k / n; th = th0 + (th1 - th0) * t
            ry, rz = hr[1] + .009, hr[2] + .009 * .6
            y, z = ry * math.sin(th), rz * math.cos(th)
            if y > .05: y += .008                                               # same rounder back of skull
            ny, nz = math.sin(th), math.cos(th)
            hgt = .016 + .044 * math.sin(math.pi * min(1, t * 1.15)) ** .7       # tapers at the forehead, fullest behind the top
            inner = (y - ny * .012, z - nz * .012); outer = (y + ny * hgt, z + nz * hgt)
            rows.append([bm.verts.new((hc.x + sx * w * (1 if j == 0 else .75), hc.y + py, hc.z + pz)) for sx in (-1, 1) for j, (py, pz) in enumerate((inner, outer))])
        for a_, b_ in zip(rows, rows[1:]):
            for i, j in ((0, 1), (1, 3), (3, 2), (2, 0)): bm.faces.new((a_[i], a_[j], b_[j], b_[i]))
        bm.faces.new((rows[0][0], rows[0][2], rows[0][3], rows[0][1])); bm.faces.new((rows[-1][0], rows[-1][1], rows[-1][3], rows[-1][2]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); bm.to_mesh(me); bm.free()
        m = ob.modifiers.new('bev', 'BEVEL'); m.width = .005; m.segments = 2; bpy.context.view_layer.objects.active = ob; bpy.ops.object.modifier_apply(modifier='bev')
        return [ob]
    rigid(cap('hair_mohawk', .009, .012, .35, crest), 'hair')
    # ---------- facial hair (colour follows hair)
    # ---------- facial hair building blocks (combined into 30 styles in the game)
    if kind == 'male':
        def jaw(p):
            x, y, z = p
            if z < -.02: x *= 1 - min(.22, (-.02 - z) * 2.4)
            if z < -.05 and y < -.03: y -= .014; z -= .008
            return x, y, z
        def surf(lat, lon, off=0.):
            x = hr[0] * math.sin(lon) * math.cos(lat); y = -hr[1] * math.cos(lon) * math.cos(lat); z = hr[2] * math.sin(lat)
            x, y, z = jaw((x, y, z)); n = Vector((x / hr[0] ** 2, y / hr[1] ** 2, z / hr[2] ** 2)).normalized()
            base = Vector((x, y, z)); hit = head_bvh.ray_cast(Vector((0, 0, 0)), base.normalized(), 1.)
            if hit[0] is not None: base = hit[0]                                  # sit on the actual (low-poly) skin, not the ideal shape
            return tuple(base + n * off + hc)
        def curve(name, LL, RR, off=.014, sym=True, segs=8):
            if sym:
                LL = [(-lo, la) for lo, la in reversed(LL[1:])] + LL; RR = list(reversed(RR[1:])) + RR
            return tube(name, [surf(la, lo, ry * .75) for (lo, la), (rx, ry) in zip(LL, RR)], RR, segs=segs, subdiv=1)
        B = []
        def piece(o): rigid(o, 'beard'); B.append(o.name); return o
        # moustaches (points listed from the centre outwards; mirrored)
        piece(curve('beard_m_classic', [(0, -.25), (.14, -.255), (.36, -.30), (.62, -.40)], [(.018, .012), (.02, .013), (.016, .011), (.006, .004)]))
        piece(curve('beard_m_chevron', [(0, -.255), (.18, -.26), (.36, -.29), (.48, -.33)], [(.026, .018), (.026, .018), (.022, .016), (.012, .01)]))
        piece(curve('beard_m_pencil', [(0, -.3), (.14, -.305), (.28, -.32)], [(.006, .004), (.006, .004), (.003, .003)], off=.008))
        piece(curve('beard_m_handlebar', [(0, -.25), (.14, -.26), (.34, -.31), (.56, -.33), (.7, -.24), (.66, -.17)], [(.017, .012), (.018, .012), (.014, .01), (.01, .008), (.007, .006), (.004, .004)]))
        piece(curve('beard_m_walrus', [(0, -.25), (.16, -.26), (.34, -.33), (.48, -.45)], [(.032, .022), (.033, .022), (.028, .02), (.012, .01)], off=.018))
        piece(curve('beard_m_horseshoe', [(0, -.255), (.18, -.265), (.34, -.31), (.37, -.5), (.38, -.7), (.37, -.86)], [(.016, .012), (.016, .012), (.016, .012), (.015, .011), (.014, .01), (.008, .007)]))
        piece(curve('beard_m_fu', [(0, -.28), (.14, -.29), (.26, -.34), (.3, -.55), (.31, -.8), (.3, -1.0)], [(.009, .007), (.01, .007), (.009, .007), (.008, .006), (.006, .005), (.003, .003)]))
        piece(curve('beard_m_toothbrush', [(0, -.255), (.1, -.26), (.13, -.265)], [(.02, .016), (.02, .016), (.012, .01)]))
        # chin pieces
        piece(tube('beard_c_soul', [surf(-.48, 0, .005), surf(-.54, 0, .006), surf(-.6, 0, .003)], [(.012, .007), (.014, .008), (.006, .004)], segs=8, subdiv=1))
        piece(tube('beard_c_tuft', [surf(-.5, 0, .009), surf(-.66, 0, .015), surf(-.8, 0, .015), surf(-.9, 0, .008)], [(.022, .012), (.03, .02), (.026, .02), (.012, .01)], segs=10, subdiv=1))
        piece(tube('beard_c_point', [surf(-.5, 0, .009), surf(-.68, 0, .015), surf(-.86, 0, .02), surf(-1.0, 0, .04), surf(-1.08, 0, .06)], [(.024, .012), (.034, .02), (.03, .02), (.016, .012), (.004, .004)], segs=10, subdiv=1))
        piece(curve('beard_c_circle', [(0, -.74), (.14, -.71), (.26, -.6), (.32, -.46), (.33, -.34)], [(.016, .012), (.016, .012), (.015, .011), (.014, .01), (.01, .008)]))
        # shells: cheeks / jaw / chin
        def shell_piece(name, lon_ranges, low, top, extra, hole=None, thick=.009, drop=0., point=0., width=1.):
            """smooth, solid beard: a lat/lon grid clamped between two smooth curves (edges follow the cheek and jaw lines).
            The inside hugs the face; the outside is the beard's shape (bulk, hang below the chin, point)."""
            bm = bmesh.new()
            for l0, l1 in lon_ranges:
                nc = max(8, int(36 * (l1 - l0) / 3.0))
                cols = sorted(set([l0 + (l1 - l0) * k / nc for k in range(nc + 1)] + ([-.3, .3] if hole else [])))
                cols = [c for c in cols if l0 - 1e-9 <= c <= l1 + 1e-9]
                la0 = min(low(c) for c in cols); la1 = max(top(c) for c in cols)
                rows = sorted(set([la0 + (la1 - la0) * k / 14 for k in range(15)] + ([-.47, -.29] if hole else [])))
                OUT, INN = {}, {}
                for i, c in enumerate(cols):
                    for j, r in enumerate(rows):
                        lat = min(max(r, low(c)), top(c))
                        p = Vector(surf(lat, c, max(extra(lat, c), thick))) - hc
                        chin = max(0, (-lat - .62) / .45) * max(0, 1 - abs(c) / 1.1)
                        p.z -= drop * chin; p.y -= drop * .35 * chin; p.x *= width * (1 - point * chin)
                        q = Vector(surf(lat, c, -.002)) - hc
                        OUT[i, j] = bm.verts.new(p); INN[i, j] = bm.verts.new(q)
                quads = []
                for i in range(len(cols) - 1):
                    for j in range(len(rows) - 1):
                        if hole and hole((rows[j] + rows[j + 1]) / 2, (cols[i] + cols[i + 1]) / 2): continue
                        if rows[j] >= max(top(cols[i]), top(cols[i + 1])) - 1e-9: continue
                        if rows[j + 1] <= min(low(cols[i]), low(cols[i + 1])) + 1e-9: continue
                        quads.append(((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)))
                ecount = {}
                for qd in quads:
                    for k in range(4):
                        e = (qd[k], qd[(k + 1) % 4]); ecount[e] = ecount.get(e, 0) + 1
                for qd in quads:
                    for M_, rev in ((OUT, False), (INN, True)):
                        vs = [M_[k] for k in qd]
                        if rev: vs.reverse()
                        try: bm.faces.new(vs)
                        except ValueError: pass
                for (a_, b_), n_ in ecount.items():                               # side walls along the open edges
                    if n_ == 1 and ecount.get((b_, a_), 0) == 0:
                        try: bm.faces.new((OUT[b_], OUT[a_], INN[a_], INN[b_]))
                        except ValueError: pass
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
            bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges[:])
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
            fb = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(fb); fb.location = hc
            bpy.ops.object.select_all(action='DESELECT'); fb.select_set(True); bpy.context.view_layer.objects.active = fb
            bpy.ops.object.transform_apply(location=True, rotation=False, scale=False); fb.name = name
            return piece(fb)
        mouth = lambda lat, lon: -.47 < lat < -.29 and abs(lon) < .3
        sm = lambda t: t * t * (3 - 2 * t)                                    # smoothstep, so the edges curve instead of kinking
        edge = lambda lon: -.31 + .3 * sm(min(1, abs(lon) / 1.25))         # top edge of a full beard (cheek line)
        lowB = lambda lon: -1.02 + .9 * sm(min(1, abs(lon) / 1.45))        # jaw line
        mouth_hole = lambda lat, lon: mouth(lat, lon)
        chin_extra = lambda base, chin: (lambda lat, lon: base + chin * max(0, (-lat - .6) / .4) * max(0, 1 - abs(lon)))
        FULL = dict(lon_ranges=[(-1.5, 1.5)], low=lambda lon: max(-1.02, lowB(lon) - .3), top=edge, hole=mouth_hole)   # lower edge sweeps up to the jaw corner
        shell_piece('beard_f_short', extra=chin_extra(.009, .012), **FULL)
        shell_piece('beard_f_bushy', extra=chin_extra(.018, .03), thick=.014, width=1.05, **FULL)
        shell_piece('beard_f_long', extra=chin_extra(.012, .02), drop=.1, **FULL)
        shell_piece('beard_f_duck', extra=chin_extra(.012, .02), drop=.08, point=.55, **FULL)
        shell_piece('beard_f_viking', extra=chin_extra(.016, .03), thick=.013, drop=.2, point=.25, **FULL)
        shell_piece('beard_j_chops', [(-1.5, -.52), (.52, 1.5)], lambda lon: lowB(lon) - .02, lambda lon: edge(lon) + .05,
                    lambda lat, lon: .012 + .008 * max(0, 1 - abs(abs(lon) - 1.0) / .45), thick=.011)
        jl = [(lo, lowB(lo) + .2 + .04 * min(1, lo)) for lo in (0, .25, .5, .75, 1.0, 1.2, 1.38)]
        piece(curve('beard_j_strap', jl, [(.013, .008)] * 6 + [(.008, .005)], off=.003, segs=10))
        jc = [(lo, lowB(lo) + .22 + .04 * min(1, lo)) for lo in (0, .25, .5, .75, 1.0, 1.2, 1.38)]
        piece(curve('beard_j_curtain', jc, [(.026, .014), (.026, .014), (.025, .014), (.023, .013), (.02, .012), (.016, .01), (.008, .006)], off=.006, segs=12))
    # ---------- hats
    o = joinall([cap('hc1', .018, .04, .0), hbox((.17, .1, .012), (hc.x, hc.y - hr[1] - .035, hc.z + .045))], 'hat_baseball'); rigid(o, 'hat')
    o = joinall([cap('hb1', .022, .005, .2), sph(.028, (hc.x, hc.y, hc.z + hr[2] + .03))], 'hat_beanie'); rigid(o, 'hat')
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=hr[0] + .018, depth=.08, location=(hc.x, hc.y + .005, hc.z + .085)); a1 = bpy.context.object
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=hr[0] + .03, depth=.025, location=(hc.x, hc.y - .005, hc.z + .135)); a2 = bpy.context.object
    a3 = hbox((.17, .09, .012), (hc.x, hc.y - hr[1] - .03, hc.z + .055))
    rigid(joinall([a1, a2, a3], 'hat_police'), 'hat')
    # white band round the peaked cap (UK traffic officers)
    mat('trim', 0xf2f2f2)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=hr[0] + .021, depth=.03, location=(hc.x, hc.y + .005, hc.z + .07)); rigid(bpy.context.object, 'trim'); bpy.context.object.name = 'hat_police_band'
    # custodian helmet (the British bobby's tall domed helmet) with a silver badge and top knob
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=14, location=(hc.x, hc.y + .006, hc.z + .045)); hd = bpy.context.object
    hd.scale = (hr[0] + .03, hr[1] + .042, .215); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bm = bmesh.new(); bm.from_mesh(hd.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, -.012), plane_no=(0, .25, 1), clear_inner=True)
    bm.to_mesh(hd.data); bm.free()
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=hr[0] + .05, depth=.012, location=(hc.x, hc.y + .004, hc.z + .036)); hb = bpy.context.object
    hb.scale = (1, (hr[1] + .06) / (hr[0] + .05), 1); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=.016, depth=.04, location=(hc.x, hc.y + .006, hc.z + .045 + .215 + .01)); hk = bpy.context.object
    rigid(joinall([hd, hb, hk], 'hat_helmet'), 'hat')
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=8, radius=1, location=(hc.x, hc.y - hr[1] - .036, hc.z + .135)); bg = bpy.context.object
    bg.scale = (.032, .01, .04); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); bg.rotation_euler.x = math.radians(-14)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False); rigid(bg, 'trim'); bg.name = 'hat_helmet_badge'
    # ---------- tops: hoodie hood (worn with the long-sleeve top) and an open jacket shell
    bpy.ops.mesh.primitive_torus_add(major_radius=.105, minor_radius=.045, major_segments=20, minor_segments=8, location=(0, .02, 1.5), rotation=(math.radians(-14), 0, 0))
    hood = bpy.context.object; hood.scale = (1.05, 1.15, 1); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    hb_ = bmesh.new(); hb_.from_mesh(hood.data)
    bmesh.ops.delete(hb_, geom=[f for f in hb_.faces if f.calc_center_median().y < -.035], context='FACES')
    for v in hb_.verts:
        if v.co.y > .05: v.co.z += .03 * (v.co.y - .05) / .08
    hb_.to_mesh(hood.data); hb_.free(); hood.name = 'top_hood'
    skinned(hood, 'jacket', ['chest', 'neck'])
    T = S['torso']; jr = [r for r in T if .95 <= r[0] <= 1.5]
    jk = tube('top_jacket', [(0, yo, z) for z, rx, ry, yo in jr], [(rx * 1.09 + .008, ry * 1.12 * 1.14 + .008) for z, rx, ry, yo in jr], segs=14)
    bm = bmesh.new(); bm.from_mesh(jk.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().y < -.04 and abs(f.calc_center_median().x) < .05], context='FACES')
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > .95 and (f.calc_center_median().z < 1.0 or f.calc_center_median().z > 1.47)], context='FACES')
    bm.to_mesh(jk.data); bm.free()
    skinned(jk, 'jacket', ['hips', 'spine', 'chest', 'neck'])
    # ---------- boots (shaft round the ankle)
    bl = []
    for s_, sx in (('L', 1), ('R', -1)):
        b = tube('boot_' + s_, [(sx * .1, .005, .05), (sx * .1, .008, .16), (sx * .1, .008, .27)], [(.058, .062), (.056, .058), (.06, .06)], segs=10)
        weight_part(b, J, ['shin_' + s_, 'foot_' + s_]); bl.append(b)
    bt = joinall(bl, 'shoes_boots'); bt.data.materials.clear(); bt.data.materials.append(bpy.data.materials['shoes'])
    bt.parent = rig; m = bt.modifiers.new('rig', 'ARMATURE'); m.object = rig; extras.append(bt)
    # =====================================================================
    # NEW CLOTHES (overlay pieces; the game shows the ones each outfit needs)
    # =====================================================================
    def iT(z):
        if z <= T[0][0]: return T[0][1], T[0][2], T[0][3]
        for a, b in zip(T, T[1:]):
            if a[0] <= z <= b[0]:
                t = (z - a[0]) / (b[0] - a[0]); return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t
        return T[-1][1], T[-1][2], T[-1][3]
    def frontY(z): rx, ry, yo = iT(z); return yo - ry
    def tshell(name, z0, z1, grow, mat, n=12, flare=0., ridge=0., open_w=0., keep=None, allowed=('hips', 'spine', 'chest', 'neck'), segs=16):
        zs = [z0 + (z1 - z0) * i / (n - 1) for i in range(n)]
        pts, rad = [], []
        for z in zs:
            rx, ry, yo = iT(z); f = flare * max(0, (min(z1, .98) - z)) / max(.01, (min(z1, .98) - z0)) if z < .98 else 0
            k = 1 + ridge * abs(math.sin((z - z0) / .085 * math.pi))
            pts.append((0, yo, z)); rad.append(((rx + grow + f) * k, (ry + grow + f * .8) * k))
        o = tube(name, pts, rad, segs=segs, subdiv=1)
        bm = bmesh.new(); bm.from_mesh(o.data)
        kill = [f for f in bm.faces if abs(f.normal.z) > .92 and (f.calc_center_median().z < z0 + .02 or f.calc_center_median().z > z1 - .02)]
        if open_w:
            kill += [f for f in bm.faces if f.calc_center_median().y < -.03 and abs(f.calc_center_median().x) < open_w(f.calc_center_median().z)]
        if keep: kill += [f for f in bm.faces if not keep(f.calc_center_median())]
        bmesh.ops.delete(bm, geom=list(set(kill)), context='FACES'); bm.to_mesh(o.data); bm.free()
        al = list(allowed) + (['thigh_L', 'thigh_R'] if z0 < .9 else [])
        return skinned(o, mat, al)
    A = S['arm']
    def sleeves(name, mat, grow, zend=.9, ridge=0.):
        objs = []
        for s_, sx in (('L', 1), ('R', -1)):
            pts = [(sx * x, 0, z) for x, z, r in A if z >= zend - .02]
            rad = [((r + grow) * (1 + ridge * abs(math.sin(i * 1.6))),) * 2 for i, (x, z, r) in enumerate([a for a in A if a[1] >= zend - .02])]
            o = tube(name + s_, pts, rad, segs=10, subdiv=1)
            weight_part(o, J, ['chest', 'upperarm_' + s_, 'forearm_' + s_]); objs.append(o)
        o = joinall(objs, name); o.data.materials.clear(); o.data.materials.append(bpy.data.materials[mat])
        o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o; bpy.ops.object.shade_smooth()
        extras.append(o); return o
    def arm_at(z, sx):
        for a, b in zip(A, A[1:]):
            if b[1] <= z <= a[1]:
                t = (a[1] - z) / (a[1] - b[1]); return sx * (a[0] + (b[0] - a[0]) * t), a[2] + (b[2] - a[2]) * t
        return sx * A[-1][0], A[-1][2]
    def rings_on_arms(name, mat, zs, grow, minor):
        objs = []
        for s_, sx in (('L', 1), ('R', -1)):
            for z in zs:
                x, r = arm_at(z, sx)
                bpy.ops.mesh.primitive_torus_add(major_radius=r + grow, minor_radius=minor, major_segments=14, minor_segments=6, location=(x, 0, z)); objs.append(bpy.context.object)
        o = joinall(objs, name)
        al = sum([['upperarm_' + s_, 'forearm_' + s_] for s_ in 'LR'], [])
        return skinned(o, mat, al)
    def leg_at(z, sx):
        L_ = S['leg']
        for a, b in zip(L_, L_[1:]):
            if b[1] <= z <= a[1]:
                t = (a[1] - z) / (a[1] - b[1]); return sx * (a[0] + (b[0] - a[0]) * t), a[2] + (b[2] - a[2]) * t
        return sx * L_[-1][0], L_[-1][2]
    for n, c in (('trim', 0xf2f2f2), ('skirt', 0x34507e), ('hivis', 0xd8f020), ('reflect', 0xc8ccd0), ('lens', 0x1a1c22), ('frame', 0x161616), ('gold', 0xd4a62a), ('button', 0xe8e4dc), ('sole', 0xf4f2ee), ('lens2', 0x5a3a1a)):
        mat(n, c)
    neckz = 1.505
    # ---- collar (polo / shirt), placket + buttons, cuffs
    bpy.ops.mesh.primitive_torus_add(major_radius=.088 if kind == 'male' else .078, minor_radius=.016, major_segments=20, minor_segments=6, location=(0, .008, neckz - .004))
    co = bpy.context.object; co.scale = (1.08, 1.0, .7); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bm = bmesh.new(); bm.from_mesh(co.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().y < -.06 and abs(f.calc_center_median().x) < .022], context='FACES')
    for v in bm.verts:
        if v.co.y < -.02: v.co.z -= .012 * (-v.co.y / .09)   # flaps fold down at the front
    bm.to_mesh(co.data); bm.free(); co.name = 'top_collar'; skinned(co, 'jacket', ['chest', 'neck'])
    def placket(name, z0, z1, nbtn):
        parts_ = [hbox((.026, .008, z1 - z0), (0, frontY((z0 + z1) / 2) - .004, (z0 + z1) / 2))]
        for i in range(nbtn):
            z = z1 - .03 - i * (z1 - z0 - .04) / max(1, nbtn - 1); parts_.append(sph(.0075, (0, frontY(z) - .009, z), (1, .6, 1), seg=8, rings=5))
        strip = parts_[0]; skinned(strip, 'jacket', ['spine', 'chest']); strip.name = name
        if len(parts_) > 1: skinned(joinall(parts_[1:], name + '_btn'), 'button', ['spine', 'chest'])
        return strip
    placket('top_placket', 1.0, 1.49, 6)
    placket('top_placket_short', 1.36, 1.49, 2)
    rings_on_arms('top_cuffs', 'jacket', [.92], .008, .013)
    # ---- tracksuit: zip line + collar stand + stripes down the sleeves
    zp = joinall([hbox((.012, .008, .5), (0, frontY(1.24) - .006, 1.24)), hbox((.02, .01, .02), (0, frontY(1.47) - .01, 1.47))], 'top_zip'); skinned(zp, 'trim', ['spine', 'chest'])
    st = []
    for s_, sx in (('L', 1), ('R', -1)):
        pts = [(sx * (x + r * .92), 0, z) for x, z, r in A if .9 <= z <= 1.34]
        st.append(tube('ts' + s_, pts, [(.008, .008)] * len(pts), segs=6, subdiv=0)); weight_part(st[-1], J, ['upperarm_' + s_, 'forearm_' + s_])
    o = joinall(st, 'top_stripes_arm'); o.data.materials.clear(); o.data.materials.append(bpy.data.materials['trim']); o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig; extras.append(o)
    # ---- puffer jacket + gilet (ridged), parka, blazer + tie, hi-vis, jumper ribs, football stripes
    tshell('top_puffer', .95, 1.47, .042, 'jacket', n=16, ridge=.1)
    sleeves('top_puffer_sleeves', 'jacket', .028, zend=.92, ridge=.12)
    tshell('top_gilet', .95, 1.47, .036, 'jacket', n=16, ridge=.09, open_w=lambda z: .012)
    tshell('top_parka', .52, 1.48, .024, 'jacket', n=16, flare=.12, open_w=lambda z: .01)

    # =====================================================================
    # BODY-CONFORMING GARMENTS (raycast against the body so nothing sinks in)
    # =====================================================================
    pass  # BVHTree imported at the top
    def bvh_of(objs):
        vs, ps = [], []
        for ob in objs:
            mw = ob.matrix_world; base = len(vs)
            vs += [mw @ v.co for v in ob.data.vertices]; ps += [[base + i for i in pl.vertices] for pl in ob.data.polygons]
        return BVHTree.FromPolygons(vs, ps)
    BODY = bvh_of([body])
    def frontHit(x, z, tree=None, back=False):
        tree = tree or BODY
        if back:
            h = tree.ray_cast(Vector((x, 1.0, z)), Vector((0, -1, 0)))
            return h[0].y if h[0] else iT(z)[2] + iT(z)[1]
        h = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)))
        return h[0].y if h[0] else frontY(z)
    def wrap(name, z0, z1, grow, rng=None, nz=16, na=36, flare=0., solid=0., conform=True, zfn=None, fz=None):
        """grid shell around the torso; rng(z)->(t0,t1) angle range (t=0 is the front), None = closed"""
        zs = [z0 + (z1 - z0) * i / (nz - 1) for i in range(nz)]
        closed = rng is None
        bm = bmesh.new(); rows = []
        for z in zs:
            fa, fb = fz or (z0, z1)
            rx, ry, yo = iT(z); f = flare * max(0., (min(fb, 1.0) - z)) / max(.01, (min(fb, 1.0) - fa)) if z < 1.0 else 0.
            t0, t1 = (0., 2 * math.pi) if closed else rng(z)
            cnt = na if closed else na + 1
            row = []
            for i in range(cnt):
                t = t0 + (t1 - t0) * i / (na if closed else na)
                d = Vector((math.sin(t), -math.cos(t), 0.))
                ex = Vector(((rx + f) * math.sin(t), -(ry + f * .8) * math.cos(t), 0.))
                rad = ex.length
                if conform:
                    h = BODY.ray_cast(Vector((0, yo, z)), d, 1.0)
                    if h[0] is not None: rad = max(rad, (h[0] - Vector((0, yo, z))).length)
                zz = zfn(z, t) if zfn else z
                row.append(bm.verts.new((d.x * (rad + grow), yo + d.y * (rad + grow), zz)))
            rows.append(row)
        for a, b in zip(rows, rows[1:]):
            n = len(a)
            for i in range(n if closed else n - 1):
                j = (i + 1) % n; bm.faces.new((a[i], a[j], b[j], b[i]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        me_ = bpy.data.meshes.new(name); bm.to_mesh(me_); bm.free()
        o = bpy.data.objects.new(name, me_); bpy.context.collection.objects.link(o)
        if solid:
            sm = o.modifiers.new('s', 'SOLIDIFY'); sm.thickness = solid; sm.offset = 1
            bpy.context.view_layer.objects.active = o; bpy.ops.object.modifier_apply(modifier='s')
        return o
    def surf_plate(name, z0, z1, xr, off, tree=None, nz=10, nx=6, back=False):
        """thin plate lying on a surface (front by default); xr(z)->(xa,xb)"""
        bm = bmesh.new(); rows = []
        for i in range(nz):
            z = z1 - (z1 - z0) * i / (nz - 1); xa, xb = xr(z); row = []
            for k in range(nx):
                x = xa + (xb - xa) * k / (nx - 1); y = frontHit(x, z, tree, back)
                row.append(bm.verts.new((x, y + (off if back else -off), z)))
            rows.append(row)
        for a, b in zip(rows, rows[1:]):
            for k in range(nx - 1): bm.faces.new((a[k], a[k + 1], b[k + 1], b[k]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        me_ = bpy.data.meshes.new(name); bm.to_mesh(me_); bm.free()
        o = bpy.data.objects.new(name, me_); bpy.context.collection.objects.link(o)
        sm = o.modifiers.new('s', 'SOLIDIFY'); sm.thickness = .004; sm.offset = 0
        bpy.context.view_layer.objects.active = o; bpy.ops.object.modifier_apply(modifier='s'); return o
    mat('shirtw', 0xeeece6); mat('dark', 0x1a1a1a)
    TORSO_B = ['hips', 'spine', 'chest', 'neck']
    # ---- blazer: closed below the buttons, clean V above, lapels folded on the edge
    def bl_open(z): return .012 if z < 1.15 else .012 + (z - 1.15) * 1.35
    def bl_rng(z): a = bl_open(z); return (a, 2 * math.pi - a)
    bz = wrap('top_blazer', .80, 1.475, .016, rng=bl_rng, nz=17, na=34, flare=.035, solid=.006)
    skinned(bz, 'jacket', TORSO_B + ['thigh_L', 'thigh_R'])
    BLZ = bvh_of([bz])
    def lap_w(z):
        if z < 1.15: return 0.
        u = (z - 1.15) / (1.475 - 1.15)
        w = .34 * math.sin(min(1., u / .78) * math.pi / 2)
        if u > .8: w *= .55          # notch near the top
        return max(w, .0)
    lp = []
    for side in (1, -1):
        if side == 1: rr = lambda z: (bl_open(z) - .004, bl_open(z) + lap_w(z))
        else: rr = lambda z: (2 * math.pi - bl_open(z) - lap_w(z), 2 * math.pi - bl_open(z) + .004)
        lp.append(wrap('lap%d' % side, 1.15, 1.475, .024, rng=rr, nz=14, na=6, solid=.004))
    skinned(joinall(lp, 'top_lapels'), 'jacket', ['spine', 'chest', 'neck'])
    btn = [sph(.0085, (0, frontHit(0, z, BLZ) - .004, z), (1, .5, 1), seg=10, rings=6) for z in (1.08, .98)]
    skinned(joinall(btn, 'top_blazer_btn'), 'dark', ['spine', 'hips'])
    def tie_w(z):
        if z > 1.44: return .013
        if z < 1.13: return .002 + (z - 1.10) * .9
        return .013 + (1.44 - z) / (1.44 - 1.13) * .017
    tie = surf_plate('tiep', 1.10, 1.455, lambda z: (-tie_w(z), tie_w(z)), .006, nz=14, nx=5)
    kn = sph(.016, (0, frontHit(0, 1.468) - .011, 1.468), (1.15, .75, .95), seg=10, rings=7)
    skinned(joinall([tie, kn], 'top_tie'), 'trim', ['spine', 'chest', 'neck'])
    bpy.ops.mesh.primitive_torus_add(major_radius=.088 if kind == 'male' else .078, minor_radius=.014, major_segments=20, minor_segments=6, location=(0, .008, neckz - .002))
    bc = bpy.context.object; bc.scale = (1.08, 1.0, .7); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bm = bmesh.new(); bm.from_mesh(bc.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().y < -.06 and abs(f.calc_center_median().x) < .016], context='FACES')
    for v in bm.verts:
        if v.co.y < -.02: v.co.z -= .016 * (-v.co.y / .09)
    bm.to_mesh(bc.data); bm.free(); bc.name = 'top_bcollar'; skinned(bc, 'shirtw', ['chest', 'neck'])
    tshell('top_hivis', 1.0, 1.465, .012, 'hivis', n=12, open_w=lambda z: .02)
    tshell('top_hivis_bands', 1.06, 1.22, .016, 'reflect', n=6, keep=lambda c: (1.08 < c.z < 1.11 or 1.18 < c.z < 1.21), open_w=lambda z: .022)
    rb = []
    bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=.1, major_segments=24, minor_segments=6, location=(0, iT(1.0)[2], 1.0))
    r1 = bpy.context.object; rx_, ry_, _ = iT(1.0); r1.scale = (rx_ + .01, ry_ + .01, .14); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); rb.append(r1)
    skinned(joinall(rb, 'top_ribs'), 'jacket', ['hips', 'spine'])
    tshell('top_stripes', 1.0, 1.48, .009, 'trim', n=12, segs=24, keep=lambda c: int(((math.atan2(c.x, -c.y) + math.pi) / (2 * math.pi)) * 14) % 2 == 0)
    # ---- bottoms: joggers (stripes + cuffs), cargo pockets, skirts
    js = []
    for s_, sx in (('L', 1), ('R', -1)):
        pts = []
        for z in (.98, .8, .6, .4, .2, .1):
            x, r = leg_at(z, sx); pts.append((x + sx * (r + .002), 0, z))
        js.append(tube('js' + s_, pts, [(.007, .007)] * len(pts), segs=6, subdiv=0)); weight_part(js[-1], J, ['hips', 'thigh_' + s_, 'shin_' + s_])
    o = joinall(js, 'legs_stripes'); o.data.materials.clear(); o.data.materials.append(bpy.data.materials['trim']); o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig; extras.append(o)
    cf = []
    for s_, sx in (('L', 1), ('R', -1)):
        x, r = leg_at(.1, sx); bpy.ops.mesh.primitive_torus_add(major_radius=r * .82, minor_radius=.016, major_segments=14, minor_segments=6, location=(x, 0, .1)); cf.append(bpy.context.object)
    skinned(joinall(cf, 'legs_cuffs'), 'pants', ['shin_L', 'shin_R'])
    pk = []
    for s_, sx in (('L', 1), ('R', -1)):
        x, r = leg_at(.72, sx); pk.append(hbox((.03, .1, .1), (x + sx * (r - .004), 0, .72)))
    skinned(joinall(pk, 'legs_pockets'), 'pants', ['thigh_L', 'thigh_R'])
    def skirt(name, z1, r1):
        hrx, hry, _ = iT(1.0)
        o = tube(name, [(0, 0, 1.02), (0, 0, .92), (0, 0, z1)], [(hrx + .012, hry + .012), (hrx + .03, hry + .03), (r1, r1 * .78)], segs=18, subdiv=1)
        bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > .95], context='FACES'); bm.to_mesh(o.data); bm.free()
        return skinned(o, 'skirt', ['hips', 'thigh_L', 'thigh_R'])
    skirt('skirt_short', .64, .25); skirt('skirt_long', .3, .3)
    # ---- shoes: hi-tops (with white sole band) and wellies
    def shaft(name, z1, rr, mat_):
        bl_ = []
        for s_, sx in (('L', 1), ('R', -1)):
            b = tube(name + s_, [(sx * .11, .005, .05), (sx * .11, .008, (z1 + .05) / 2), (sx * .11, .008, z1)], [(rr, rr * 1.05), (rr * .96, rr), (rr * 1.04, rr * 1.04)], segs=10)
            weight_part(b, J, ['shin_' + s_, 'foot_' + s_]); bl_.append(b)
        o = joinall(bl_, name); o.data.materials.clear(); o.data.materials.append(bpy.data.materials[mat_]); o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig; extras.append(o); return o
    shaft('shoes_hitop', .2, .062, 'shoes'); shaft('shoes_wellies', .44, .072, 'shoes')
    so = []
    for s_, sx in (('L', 1), ('R', -1)):
        so.append(tube('sole' + s_, [(sx * .11, .07, .02), (sx * .11, -.02, .018), (sx * .11, -.14, .016), (sx * .11, S['toe'] - .01, .016)], [(.064, .024), (.072, .024), (.072, .022), (.05, .02)], segs=10, subdiv=1))
        weight_part(so[-1], J, ['foot_' + s_])
    o = joinall(so, 'shoes_soles'); o.data.materials.clear(); o.data.materials.append(bpy.data.materials['sole']); o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig; extras.append(o)
    # ---- hats (head-relative)
    def ring(name, r_in, r_out, z, y=0., segs=24, tilt=0.):
        bpy.ops.mesh.primitive_cylinder_add(vertices=segs, radius=r_out, depth=.012, location=(hc.x, hc.y + y, hc.z + z), rotation=(tilt, 0, 0)); o = bpy.context.object; o.name = name; return o
    rigid(joinall([cap('hbk1', .02, .03, .1), ring('hbk2', 0, hr[0] + .075, .03, .01, tilt=math.radians(-6))], 'hat_bucket'), 'hat')
    fc = cap('hfc1', .022, .05, .55); fc.scale = (1.06, 1.12, .75); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rigid(joinall([fc, hbox((.16, .07, .012), (hc.x, hc.y - hr[1] - .02, hc.z + .055), (math.radians(-12), 0, 0))], 'hat_flat'), 'hat')
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=hr[0] - .005, depth=.1, location=(hc.x, hc.y + .004, hc.z + .12)); cr = bpy.context.object
    bm = bmesh.new(); bm.from_mesh(cr.data)
    for v in bm.verts:
        if v.co.z > 0: v.co.x *= .82; v.co.y *= .9
        if v.co.z > 0 and abs(v.co.x) < .03: v.co.z -= .02
    bm.to_mesh(cr.data); bm.free()
    rigid(joinall([cr, ring('htr2', 0, hr[0] + .065, .075, tilt=math.radians(-4))], 'hat_trilby'), 'hat')
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=hr[0] + .002, depth=.02, location=(hc.x, hc.y + .004, hc.z + .085)); tb = bpy.context.object; tb.name = 'hat_trilby_band'; rigid(tb, 'trim')
    bb = joinall([cap('hbb1', .018, .04, .0), hbox((.17, .1, .012), (hc.x, hc.y + hr[1] + .035, hc.z + .045))], 'hat_backwards'); rigid(bb, 'hat')
    rigid(joinall([cap('hhd1', .03, .03, .05), ring('hhd2', 0, hr[0] + .055, .03, -.012), hbox((.03, .26, .02), (hc.x, hc.y, hc.z + hr[2] + .03))], 'hat_hard'), 'hat')
    # ---- eyewear (eye line from the face painter: lat .134, lon ±.368)
    def hp(lat, lon, off=0.):
        x = hr[0] * math.sin(lon) * math.cos(lat); y = -hr[1] * math.cos(lon) * math.cos(lat); z = hr[2] * math.sin(lat)
        n = Vector((x / hr[0] ** 2, y / hr[1] ** 2, z / hr[2] ** 2)).normalized(); return Vector((x, y, z)) + n * off + hc
    def specs(name, lens_r, lens_mat, frame=True, shape=(1, 1)):
        parts_ = []
        for sx in (1, -1):
            c = hp(.13, sx * .37, .02)
            if lens_mat:
                o = sph(lens_r, tuple(c), (shape[0], .35, shape[1]), seg=14, rings=8); parts_.append(o)
            if frame:
                bpy.ops.mesh.primitive_torus_add(major_radius=lens_r, minor_radius=.0045, major_segments=18, minor_segments=5, location=tuple(c), rotation=(math.pi / 2, 0, sx * .3))
                o = bpy.context.object; o.scale = (shape[0], 1, shape[1]); parts_.append(o)
            ear = hp(.08, sx * 1.42, .006)
            parts_.append(tube('arm' + str(sx), [tuple(hp(.13, sx * .7, .022)), tuple(hp(.12, sx * 1.1, .012)), tuple(ear)], [(.004, .004)] * 3, segs=5, subdiv=0))
        parts_.append(tube('bridge', [tuple(hp(.14, -.2, .026)), tuple(hp(.15, 0, .03)), tuple(hp(.14, .2, .026))], [(.004, .004)] * 3, segs=5, subdiv=0))
        bpy.ops.object.select_all(action='DESELECT')
        for p_ in parts_: p_.select_set(True)
        bpy.context.view_layer.objects.active = parts_[0]; bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        return joinall(parts_, name)
    rigid(specs('acc_sunglasses', .036, 'lens', frame=False, shape=(1.15, .85)), 'lens')
    rigid(specs('acc_glasses', .032, None, frame=True, shape=(1.1, .85)), 'frame')
    rigid(specs('acc_aviators', .036, 'lens', frame=False, shape=(1.05, 1.0)), 'lens2')
    # ---- extras: gold chain, scarf, backpack, headphones
    bpy.ops.mesh.primitive_torus_add(major_radius=.1 if kind == 'male' else .09, minor_radius=.007, major_segments=28, minor_segments=6, location=(0, -.03, 1.43), rotation=(math.radians(-38), 0, 0))
    ch = bpy.context.object; pend = sph(.016, (0, frontY(1.33) - .012, 1.33), (1, .4, 1.2), seg=10, rings=6)
    skinned(joinall([ch, pend], 'acc_chain'), 'gold', ['chest', 'neck'])
    bpy.ops.mesh.primitive_torus_add(major_radius=.085, minor_radius=.034, major_segments=20, minor_segments=8, location=(0, .006, 1.5)); sc1 = bpy.context.object
    tail = hbox((.07, .025, .2), (.06, frontY(1.36) - .03, 1.37), (math.radians(4), 0, math.radians(-8)))
    skinned(joinall([sc1, tail], 'acc_scarf'), 'trim', ['chest', 'neck'])
    by = -frontY(1.25) + .05
    bp = hbox((.3, .14, .34), (0, iT(1.25)[1] + iT(1.25)[2] + .07, 1.23))
    straps = [tube('st' + str(sx), [(sx * .09, frontY(1.42) - .004, 1.42), (sx * .1, 0, 1.47), (sx * .1, iT(1.4)[1] + .1, 1.4)], [(.014, .006)] * 3, segs=6, subdiv=0) for sx in (1, -1)]
    skinned(joinall([bp] + straps, 'acc_backpack'), 'trim', ['spine', 'chest'])
    hpb = tube('hpb', [tuple(hp(.05, -1.55, .012)), tuple(hp(.6, -1.3, .02)), tuple(hp(1.2, -.4, .022)), tuple(hp(1.45, 0, .022)), tuple(hp(1.2, .4, .022)), tuple(hp(.6, 1.3, .02)), tuple(hp(.05, 1.55, .012))], [(.01, .01)] * 7, segs=6, subdiv=0)
    cups = []
    for sx in (1, -1):
        c = hp(-.02, sx * 1.55, .02); bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=.042, depth=.03, location=tuple(c), rotation=(0, math.pi / 2, 0)); cups.append(bpy.context.object)
    rigid(joinall([hpb] + cups, 'acc_headphones'), 'frame')
    # =====================================================================
    # STREET / GANG WEAR (GTA SA style)
    # =====================================================================
    # ---- oversized tee: long, boxy, sleeves past the elbow
    skinned(wrap('top_bigtee', .78, 1.48, .036, nz=18, na=32, flare=.06), 'jacket', TORSO_B + ['thigh_L', 'thigh_R'])
    sleeves('top_bigtee_sleeves', 'jacket', .032, zend=1.1)
    # ---- basketball jersey: long tank, trim on neck + hem, number front and back
    jr = wrap('top_jersey', .82, 1.46, .028, nz=16, na=32, flare=.03)
    skinned(jr, 'jacket', TORSO_B + ['thigh_L', 'thigh_R'])
    JRS = bvh_of([jr])
    bpy.ops.mesh.primitive_torus_add(major_radius=.095 if kind == 'male' else .085, minor_radius=.011, major_segments=22, minor_segments=6, location=(0, .004, neckz - .02))
    jn = bpy.context.object; jn.scale = (1.1, 1.0, 1.0); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for v in jn.data.vertices:
        if v.co.y < 0: v.co.z -= .07 * (-v.co.y / .1) ** 2      # V-neck dip
    hem = wrap('jhem', .82, .845, .034, nz=2, na=32, flare=.03, fz=(.82, 1.46))
    skinned(joinall([jn, hem], 'top_jersey_trim'), 'trim', TORSO_B + ['thigh_L', 'thigh_R'])
    nums = []
    for back, txt, zc, sz in ((False, '92', 1.22, .13), (True, '92', 1.24, .17)):
        bpy.ops.object.text_add(location=(0, 0, 0)); t_ = bpy.context.object; t_.data.body = txt; t_.data.size = sz; t_.data.extrude = .003
        t_.data.resolution_u = 2; t_.data.align_x = 'CENTER'; t_.data.align_y = 'CENTER'; t_.data.fill_mode = 'BOTH'
        bpy.ops.object.convert(target='MESH'); t_ = bpy.context.object
        for v in t_.data.vertices:
            x, yv, zt = v.co.x, v.co.y, v.co.z
            wx = -x if back else x; wz = zc + yv
            y = frontHit(wx, wz, JRS, back)
            v.co = Vector((wx, y + ((.004 + zt) if back else -(.004 + zt)), wz))
        nums.append(t_)
    skinned(joinall(nums, 'top_jersey_num'), 'trim', ['spine', 'chest'])
    # ---- cholo flannel: open overshirt, top button done up, check pattern in the trim colour
    def fl_open(z): return .014 if z > 1.37 else .014 + (1.37 - z) * .95
    fl = wrap('top_flannel', .86, 1.475, .026, rng=lambda z: (fl_open(z), 2 * math.pi - fl_open(z)), nz=18, na=36, flare=.045, solid=.005)
    skinned(fl, 'jacket', TORSO_B + ['thigh_L', 'thigh_R'])
    ck = []
    for zb in [.9 + i * .075 for i in range(8)]:
        ck.append(wrap('fh', zb, zb + .014, .033, rng=lambda z: (fl_open(z) + .01, 2 * math.pi - fl_open(z) - .01), nz=2, na=36, flare=.045, fz=(.86, 1.475)))
    for k in range(14):
        tk = .3 + k * (2 * math.pi - .6) / 13
        ck.append(wrap('fv', .87, 1.46, .033, rng=lambda z, tk=tk: (max(tk, fl_open(z) + .01), max(max(tk, fl_open(z) + .01), min(tk + .05, 2 * math.pi - fl_open(z) - .01))), nz=10, na=2, flare=.045, fz=(.86, 1.475)))
    skinned(joinall(ck, 'top_flannel_check'), 'trim', TORSO_B + ['thigh_L', 'thigh_R'])
    rings_on_arms('top_flannel_cuffs', 'trim', [1.24, 1.04], .001, .0045)
    # ---- baggy jeans (sagging, boxers showing), long baggy shorts
    skinned(wrap('legs_seat', .8, .975, .016, nz=8, na=32), 'skirt', ['hips', 'thigh_L', 'thigh_R'])
    skinned(wrap('legs_boxers', .97, 1.03, .021, nz=3, na=32), 'trim', ['hips', 'spine'])
    def baggy(name, zlow, stack):
        objs = []
        for s_, sx in (('L', 1), ('R', -1)):
            zz = [z for z in (.9, .78, .64, .5, .4, .3, .2, .12, .07) if z >= zlow - .001]
            pts, rad = [], []
            for i, z in enumerate(zz):
                x, r = leg_at(z, sx); g = .03 + .018 * (1 - z)
                if stack and z < .22: g += .012 * (1 if i % 2 else .3)
                pts.append((x, 0, z)); rad.append((r + g, r + g))
            o = tube(name + s_, pts, rad, segs=14, subdiv=1)
            bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > .95], context='FACES'); bm.to_mesh(o.data); bm.free()
            weight_part(o, J, ['hips', 'thigh_' + s_, 'shin_' + s_]); objs.append(o)
        o = joinall(objs, name); o.data.materials.clear(); o.data.materials.append(bpy.data.materials['skirt'])
        o.parent = rig; m = o.modifiers.new('rig', 'ARMATURE'); m.object = rig
        bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o; bpy.ops.object.shade_smooth()
        extras.append(o); return o
    baggy('legs_baggy', .07, True)
    baggy('legs_longshorts', .4, False)
    # ---- headwear: bandana wrap (knot + tails), durag (tail flap), snapback (flat brim)
    def bn_extra():
        k = sph(.024, tuple(hp(.32, math.pi, .012)), (1.2, .8, 1), seg=10, rings=6)
        t1 = tube('bt1', [tuple(hp(.3, math.pi - .1, .02)), tuple(hp(.05, math.pi - .2, .05)), tuple(hp(-.25, math.pi - .25, .07))], [(.022, .006), (.02, .006), (.012, .005)], segs=6, subdiv=0)
        t2 = tube('bt2', [tuple(hp(.3, math.pi + .1, .02)), tuple(hp(.08, math.pi + .16, .045)), tuple(hp(-.15, math.pi + .2, .06))], [(.022, .006), (.02, .006), (.012, .005)], segs=6, subdiv=0)
        return [k, t1, t2]
    rigid(cap('hat_bandana', .012, .03, .12, bn_extra), 'hat')
    def dr_extra():
        return [tube('drt', [tuple(hp(.05, math.pi, .014)), tuple(hp(-.4, math.pi, .03)), tuple(hp(-.75, math.pi, .05)), (hc.x, hc.y + hr[1] + .03, hc.z - hr[2] - .07)], [(.05, .006), (.045, .006), (.04, .006), (.035, .005)], segs=6, subdiv=0)]
    rigid(cap('hat_durag', .008, -.0, .05, dr_extra), 'hat')
    rigid(joinall([cap('hsb1', .02, .045, .0), hbox((.18, .11, .01), (hc.x, hc.y - hr[1] - .045, hc.z + .055))], 'hat_snapback'), 'hat')
    # ---- face bandana (outlaw style) and a heavy chain with medallion
    bm = bmesh.new(); rows = []
    NR, NC = 9, 11
    for i in range(NR):
        u = i / (NR - 1); lat = -.04 - u * .98; wl = 1.42 * (1 - .55 * u ** 1.6); row = []
        for k in range(NC):
            lon = -wl + 2 * wl * k / (NC - 1)
            off = .012 + .022 * math.exp(-((lon / .28) ** 2 + ((lat + .06) / .14) ** 2))
            row.append(bm.verts.new(tuple(hp(lat, lon, off))))
        rows.append(row)
    for a, b in zip(rows, rows[1:]):
        for k in range(NC - 1): bm.faces.new((a[k], a[k + 1], b[k + 1], b[k]))
    tip = bm.verts.new(tuple(hp(-1.25, 0, .05)))
    last = rows[-1]
    for k in range(NC - 1): bm.faces.new((last[k], last[k + 1], tip))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me_ = bpy.data.meshes.new('fb'); bm.to_mesh(me_); bm.free(); fb = bpy.data.objects.new('acc_facebandana', me_); bpy.context.collection.objects.link(fb)
    sm = fb.modifiers.new('s', 'SOLIDIFY'); sm.thickness = .004; bpy.context.view_layer.objects.active = fb; bpy.ops.object.modifier_apply(modifier='s')
    rigid(fb, 'trim')
    bpy.ops.mesh.primitive_torus_add(major_radius=.115 if kind == 'male' else .1, minor_radius=.013, major_segments=32, minor_segments=6, location=(0, -.035, 1.4), rotation=(math.radians(-42), 0, 0))
    bc2 = bpy.context.object
    my = frontHit(0, 1.27) - .014
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=.038, depth=.01, location=(0, my, 1.27), rotation=(math.pi / 2, 0, 0)); md = bpy.context.object
    bpy.ops.mesh.primitive_torus_add(major_radius=.038, minor_radius=.006, major_segments=20, minor_segments=5, location=(0, my - .004, 1.27), rotation=(math.pi / 2, 0, 0)); mr = bpy.context.object
    skinned(joinall([bc2, md, mr], 'acc_bigchain'), 'gold', ['chest', 'neck'])
    return rig, body, extras

# ------------------------------------------------------------------ animation
# Pose helper: key = {bone: (rx, ry, rz)} euler radians in bone-local space; 'loc' for hips offset (bone-local)
def set_pose(rig, pose, frame):
    for pb in rig.pose.bones:
        pb.rotation_mode = 'XYZ'
        r = pose.get(pb.name, (0, 0, 0))
        pb.rotation_euler = Euler(r, 'XYZ')
        pb.keyframe_insert('rotation_euler', frame=frame)
        if pb.name == 'hips':
            pb.location = Vector(pose.get('loc', (0, 0, 0)))
            pb.keyframe_insert('location', frame=frame)

def make_action(rig, name, keys, loop=True):
    """keys: list of (frame, pose)"""
    act = bpy.data.actions.new(name)
    rig.animation_data_create(); rig.animation_data.action = act
    for fr, pose in keys: set_pose(rig, pose, fr)
    track = rig.animation_data.nla_tracks.new(); track.name = name
    st = track.strips.new(name, int(keys[0][0]), act); st.name = name
    rig.animation_data.action = None
    return act

if __name__ == '__main__' and 'test' in sys.argv:
    rig, body, extras = build('male', ['short'])
    # test pose: left thigh +x, left upperarm +x, right forearm +x, spine +x
    p = {'spine': (.5, 0, 0), 'head': (.5, 0, 0), 'forearm_L': (-1.0, 0, 0), 'upperarm_L': (0, 0, -.6), 'thigh_R': (-1.2, 0, 0), 'shin_R': (1.2, 0, 0)}
    set_pose(rig, p, 1)
    sc = bpy.context.scene; sc.frame_set(1)
    bpy.ops.object.light_add(type='SUN', rotation=(math.radians(50), 0, math.radians(30))); bpy.context.object.data.energy = 3
    w = bpy.data.worlds.new('w'); sc.world = w; w.color = (.5, .55, .6)
    try: sc.view_settings.view_transform = 'Standard'
    except Exception: pass
    sc.render.resolution_x = 900; sc.render.resolution_y = 600
    bpy.ops.object.empty_add(location=(0, 0, 1)); tg = bpy.context.object
    bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 40
    cam.constraints.new('TRACK_TO').target = tg
    for nm, pos in (('front', (1.6, -4.2, 1.5)), ('side', (4.5, 0, 1.2))):
        cam.location = pos; sc.render.filepath = f'{OUT}/test_{nm}.png'; bpy.ops.render.render(write_still=True)
    print('DONE')

# ======================================================================
# ANIMATIONS  (conventions verified: +x on down-pointing bones swings the end backwards;
# spine/head +x leans forward; arm outward = -z (L) / +z (R))
# ======================================================================
def P(**kw):
    d = {}
    for k, v in kw.items():
        d[k.replace('__', '_')] = v
    return d

def mirror_pose(base):
    return base

def cycle(rig, name, frames, fn, n=8):
    keys = []
    for k in range(n + 1):
        t = k / n; keys.append((1 + t * frames, fn(t * math.tau)))
    return make_action(rig, name, keys)

def walk_pose(a, A=.42, B=.75, C=.32, lean=.04, bob=.022, tw=.07):
    s, c = math.sin(a), math.cos(a)
    kl = B * max(0, c) + .08; kr = B * max(0, -c) + .08
    tl, tr = -A * s, A * s
    return {'thigh_L': (tl, 0, 0), 'thigh_R': (tr, 0, 0), 'shin_L': (kl, 0, 0), 'shin_R': (kr, 0, 0),
            'foot_L': (-(tl + kl) * .6, 0, 0), 'foot_R': (-(tr + kr) * .6, 0, 0),
            'upperarm_L': (C * s, 0, -.06), 'upperarm_R': (-C * s, 0, .06),
            'forearm_L': (-.25 - .2 * max(0, -s), 0, 0), 'forearm_R': (-.25 - .2 * max(0, s), 0, 0),
            'hips': (0, tw * s, 0), 'spine': (lean, -tw * .6 * s, 0), 'chest': (0, -tw * .5 * s, 0), 'head': (-lean * .6, 0, 0),
            'loc': (0, -bob * (1 - abs(c)), 0)}

def run_pose(a):
    p = walk_pose(a, A=.85, B=1.55, C=.8, lean=.2, bob=.05, tw=.14)
    s = math.sin(a)
    p['forearm_L'] = (-1.35, 0, 0); p['forearm_R'] = (-1.35, 0, 0)
    p['upperarm_L'] = (.8 * s, 0, -.12); p['upperarm_R'] = (-.8 * s, 0, .12)
    return p

def flee_pose(a):
    p = run_pose(a); s = math.sin(a)
    p['upperarm_L'] = (-2.5 + .35 * s, 0, -.35); p['upperarm_R'] = (-2.5 - .35 * s, 0, .35)
    p['forearm_L'] = (-.7 + .3 * s, 0, 0); p['forearm_R'] = (-.7 - .3 * s, 0, 0)
    p['spine'] = (.12, 0, 0); p['head'] = (-.25, .2 * s, 0)
    return p

def idle_pose(a):
    s = math.sin(a)
    return {'chest': (.02 + .015 * s, 0, 0), 'spine': (.01, 0, 0), 'head': (-.02, .06 * math.sin(a * .5), 0),
            'upperarm_L': (.03, 0, .03 + .01 * s), 'upperarm_R': (.03, 0, -.03 - .01 * s),
            'forearm_L': (-.18, 0, 0), 'forearm_R': (-.18, 0, 0),
            'thigh_L': (0, 0, -.02), 'thigh_R': (-.03, 0, .03), 'shin_R': (.06, 0, 0),
            'hips': (0, 0, .015 * s), 'loc': (0, -.004 * (1 + s), 0)}

JUMP = {'thigh_L': (-.9, 0, 0), 'thigh_R': (-.3, 0, 0), 'shin_L': (1.3, 0, 0), 'shin_R': (.7, 0, 0),
        'upperarm_L': (-.7, 0, -.5), 'upperarm_R': (-.5, 0, .5), 'forearm_L': (-.6, 0, 0), 'forearm_R': (-.6, 0, 0),
        'spine': (.08, 0, 0), 'loc': (0, .02, 0)}
SIT = {'thigh_L': (-1.5, 0, -.08), 'thigh_R': (-1.5, 0, .08), 'shin_L': (1.4, 0, 0), 'shin_R': (1.4, 0, 0),
       'foot_L': (-.15, 0, 0), 'foot_R': (-.15, 0, 0),
       'upperarm_L': (-.95, 0, .18), 'upperarm_R': (-.95, 0, -.18), 'forearm_L': (-.75, 0, 0), 'forearm_R': (-.75, 0, 0),
       'hand_L': (.2, 0, 0), 'hand_R': (.2, 0, 0), 'spine': (-.12, 0, 0), 'head': (.08, 0, 0)}
DOWN = {'hips': (-1.5, 0, 0), 'loc': (0, -.8, 0), 'thigh_L': (-.15, 0, .15), 'thigh_R': (-.35, 0, -.1), 'shin_R': (.5, 0, 0),
        'upperarm_L': (0, 0, -1.2), 'upperarm_R': (-.3, 0, 1.0), 'forearm_L': (-.3, 0, 0), 'forearm_R': (-.6, 0, 0),
        'head': (-.15, .5, 0), 'spine': (0, 0, 0)}
SITUP = {'hips': (-.55, 0, 0), 'loc': (0, -.62, 0), 'spine': (.55, 0, 0), 'chest': (.2, 0, 0),
         'thigh_L': (-1.35, 0, -.1), 'thigh_R': (-1.0, 0, .1), 'shin_L': (2.0, 0, 0), 'shin_R': (1.4, 0, 0),
         'upperarm_L': (-.4, 0, -.25), 'upperarm_R': (.2, 0, .3), 'forearm_L': (-.5, 0, 0), 'forearm_R': (-.3, 0, 0)}
CROUCH = {'hips': (0, 0, 0), 'loc': (0, -.42, 0), 'spine': (.55, 0, 0), 'thigh_L': (-1.5, 0, -.05), 'thigh_R': (-1.25, 0, .05),
          'shin_L': (2.1, 0, 0), 'shin_R': (2.0, 0, 0), 'foot_L': (-.55, 0, 0), 'foot_R': (-.7, 0, 0),
          'upperarm_L': (-.5, 0, -.2), 'upperarm_R': (-.5, 0, .2), 'forearm_L': (-.6, 0, 0), 'forearm_R': (-.6, 0, 0)}

def animate(rig):
    sc = bpy.context.scene; sc.render.fps = 30
    cycle(rig, 'idle', 90, idle_pose, n=6)
    cycle(rig, 'walk', 32, walk_pose, n=8)
    cycle(rig, 'run', 20, run_pose, n=8)
    cycle(rig, 'flee', 20, flee_pose, n=8)
    make_action(rig, 'jump', [(1, JUMP), (10, JUMP)])
    make_action(rig, 'sit', [(1, SIT), (10, SIT)])
    make_action(rig, 'down', [(1, DOWN), (10, DOWN)])
    make_action(rig, 'getup', [(1, DOWN), (12, SITUP), (24, CROUCH), (38, idle_pose(0))])

def export(kind, styles):
    rig, body, extras = build(kind, styles)
    animate(rig)
    bpy.ops.object.select_all(action='DESELECT')
    for o in [rig, body] + extras: o.select_set(True)
    kw = dict(filepath=f'{BDIR}/../assets/people/{kind}.glb', export_format='GLB', use_selection=True, export_apply=False, export_skins=True,
              export_animations=True, export_def_bones=True, export_frame_step=2, export_image_format='JPEG')
    try: bpy.ops.export_scene.gltf(**kw, export_animation_mode='NLA_TRACKS')
    except TypeError: bpy.ops.export_scene.gltf(**kw)
    return rig, body, extras

if __name__ == '__main__' and 'export' in sys.argv:
    kind = sys.argv[sys.argv.index('export') + 1]
    styles = ['short', 'cap'] if kind == 'male' else ['long', 'bun']
    rig, body, extras = export(kind, styles)
    # ---------- preview renders
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=20); g = bpy.context.object; g.data.materials.append(mat('ground', 0x8a8c90, .9))
    bpy.ops.object.light_add(type='SUN', rotation=(math.radians(50), 0, math.radians(25))); bpy.context.object.data.energy = 3.2
    w = bpy.data.worlds.new('w'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (*srgb(0xb8cce0), 1); sc.world = w
    try: sc.view_settings.view_transform = 'Standard'
    except Exception: pass
    sc.render.resolution_x = 360; sc.render.resolution_y = 560
    try: sc.eevee.taa_render_samples = 16
    except Exception: pass
    bpy.ops.object.empty_add(location=(0, 0, .95)); tg = bpy.context.object
    bpy.ops.object.camera_add(); cam = bpy.context.object; sc.camera = cam; cam.data.lens = 50; cam.constraints.new('TRACK_TO').target = tg
    def colours(skin, shirt, pants, shoes, hair):
        for n, c in (('skin', skin), ('shirt', shirt), ('pants', pants), ('shoes', shoes), ('hair', hair)):
            bpy.data.materials[n].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (*srgb(c), 1)
    def show_extra(name):
        for e in extras: e.hide_render = (e.name != name)
    def play(anim, frame):
        rig.animation_data.action = bpy.data.actions[anim]
        for t in rig.animation_data.nla_tracks: t.mute = True
        sc.frame_set(frame)
    if kind == 'male':
        looks = [('a', 0xc99a78, 0xf2f2f2, 0x34507e, 0x222222, 0x2a1a10, 'hair_short'),
                 ('b', 0x7a4e32, 0xd94b3a, 0x2b2b2b, 0xe8e8e8, 0x111111, 'hair_short'),
                 ('cop', 0xe0b48f, 0x22335e, 0x1a2442, 0x111111, 0x3a2412, 'hat_cap')]
    else:
        looks = [('a', 0xe7b892, 0xe8b23a, 0x3f5f8a, 0x8a2a2a, 0x5a3612, 'hair_long'),
                 ('b', 0xab7452, 0x45a05a, 0xc9b48a, 0x222222, 0x111111, 'hair_bun')]
    for nm, *cols, ex in looks:
        colours(*cols); show_extra(ex); play('idle', 1)
        cam.location = (1.2, -3.6, 1.35); sc.render.filepath = f'{OUT}/prev_{kind}_{nm}.png'; bpy.ops.render.render(write_still=True)
    colours(*looks[0][1:6]); show_extra(looks[0][6])
    sc.render.resolution_x = 300; sc.render.resolution_y = 460
    for anim, frames in (('walk', [1, 9, 17, 25]), ('run', [1, 6, 11, 16]), ('flee', [1]), ('sit', [1]), ('jump', [1]), ('down', [1]), ('getup', [12, 24])):
        for fr in frames:
            play(anim, fr); cam.location = (3.6, -.6, 1.2) if anim != 'down' else (2.6, -2.4, 2.2)
            sc.render.filepath = f'{OUT}/anim_{kind}_{anim}_{fr:02d}.png'; bpy.ops.render.render(write_still=True)
    print('DONE')

if __name__ == '__main__' and 'exportonly' in sys.argv:
    for kind in ('male', 'female'):
        export(kind, ['short', 'cap'] if kind == 'male' else ['long', 'bun'])
    print('DONE')
