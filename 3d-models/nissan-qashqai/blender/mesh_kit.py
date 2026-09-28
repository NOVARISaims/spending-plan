"""Small procedural mesh toolkit for the car parts: surfaces of revolution,
prisms from 2D outlines, sweeps along paths and lofts between sections.

Geometry is collected in a Kit (vertices, faces, per-face material names)
and turned into a Blender object with smooth-by-angle shading.
"""
import math

import bpy  # noqa: F401  (must precede bmesh / mathutils with the PyPI bpy module)
import numpy as np
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon


def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


class Kit:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.mats = []
        self.sharp = []            # per face: True = flat shaded
        self.uvs = []              # per face: list of (u, v) or None

    # low level ---------------------------------------------------------------
    def add(self, verts, faces, mat, sharp=False, uvs=None):
        base = len(self.verts)
        self.verts.extend(_v(p) for p in verts)
        for k, f in enumerate(faces):
            self.faces.append([base + i for i in f])
            self.mats.append(mat)
            self.sharp.append(sharp)
            self.uvs.append(None if uvs is None else uvs[k])
        return base

    def merge(self, other, matrix=None):
        base = len(self.verts)
        m = matrix or Matrix.Identity(4)
        self.verts.extend(m @ v for v in other.verts)
        self.faces.extend([[base + i for i in f] for f in other.faces])
        self.mats.extend(other.mats)
        self.sharp.extend(other.sharp)
        self.uvs.extend(other.uvs)

    def transform(self, matrix):
        self.verts = [matrix @ v for v in self.verts]

    # primitives --------------------------------------------------------------
    def revolve(self, profile, mat, seg=64, axis="y", closed=False, sharp=False, a0=0.0, a1=2 * math.pi,
                center=(0.0, 0.0, 0.0)):
        """Surface of revolution of profile [(r, h), ...] about an axis
        through center.  Walk the profile with the solid on your left (in
        the r-right / h-up plane) and the faces point outwards: a profile
        running towards +h at constant r gives an outward-facing cylinder."""
        full = abs(a1 - a0 - 2 * math.pi) < 1e-9
        n_ang = seg if full else seg + 1
        cx, cy, cz = center
        verts = []
        for k in range(n_ang):
            a = a0 + (a1 - a0) * k / seg
            ca, sa = math.cos(a), math.sin(a)
            for r, h in profile:
                if axis == "y":
                    verts.append((cx + r * ca, cy + h, cz + r * sa))
                elif axis == "z":
                    verts.append((cx + r * ca, cy + r * sa, cz + h))
                else:
                    verts.append((cx + h, cy + r * ca, cz + r * sa))
        n = len(profile)
        faces = []
        for k in range(seg):
            k1 = (k + 1) % n_ang if full else k + 1
            for i in range(n - 1):
                faces.append([k * n + i, k * n + i + 1, k1 * n + i + 1, k1 * n + i])
            if closed:
                faces.append([k * n + n - 1, k * n, k1 * n, k1 * n + n - 1])
        if axis != "y":
            faces = [f[::-1] for f in faces]
        return self.add(verts, faces, mat, sharp)

    def disc(self, r, h, mat, seg=48, axis="y", normal_sign=1.0, center=(0, 0, 0)):
        pts = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            if axis == "y":
                pts.append((center[0] + r * math.cos(a), center[1] + h, center[2] + r * math.sin(a)))
            elif axis == "z":
                pts.append((center[0] + r * math.cos(a), center[1] + r * math.sin(a), center[2] + h))
            else:
                pts.append((center[0] + h, center[1] + r * math.cos(a), center[2] + r * math.sin(a)))
        f = list(range(seg))
        # a +y disc seen from +y: counter-clockwise when viewed from the tip of the normal
        if (axis == "y") == (normal_sign > 0):
            f = f[::-1]
        return self.add(pts, [f], mat, True)

    def prism(self, outline, z0, z1, frame, mat, cap0=True, cap1=True, sharp=True, holes=()):
        """Extrude a 2D outline (ccw) between depths z0 < z1 in frame
        (origin, u, v, n); the cap at z1 faces +n."""
        o, u, v, n = (np.asarray(x, float) for x in frame)
        outline = np.asarray(outline, float)
        if _area(outline) < 0:
            outline = outline[::-1]
        k = len(outline)

        def P(p, z):
            return o + u * p[0] + v * p[1] + n * z
        verts = [P(p, z0) for p in outline] + [P(p, z1) for p in outline]
        faces = [[i, (i + 1) % k, k + (i + 1) % k, k + i] for i in range(k)]
        base = self.add(verts, faces, mat, sharp)
        if cap1:
            self.cap(outline, z1, frame, mat, up=True)
        if cap0:
            self.cap(outline, z0, frame, mat, up=False)
        return base

    def cap(self, outline, z, frame, mat, up=True, sharp=True, uv=None):
        o, u, v, n = (np.asarray(x, float) for x in frame)
        outline = np.asarray(outline, float)
        if _area(outline) < 0:
            outline = outline[::-1]
        pts = [o + u * p[0] + v * p[1] + n * z for p in outline]
        tris = tessellate_polygon([[Vector((p[0], p[1], 0.0)) for p in outline]])
        faces = [_orient(list(t), outline, up) for t in tris]
        uvs = None
        if uv is not None:
            uvs = [[uv(outline[i]) for i in f] for f in faces]
        return self.add(pts, faces, mat, sharp, uvs)

    def sweep(self, section, path, ups, mat, closed_section=True, sharp=False, caps=True):
        """Sweep a 2D section [(x, y)] along a 3D path with up vectors."""
        path = [np.asarray(p, float) for p in path]
        ups = [np.asarray(u, float) for u in ups]
        m = len(section)
        verts = []
        for i, p in enumerate(path):
            t = path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]
            t /= np.linalg.norm(t)
            up = ups[i] - t * (ups[i] @ t)
            up /= np.linalg.norm(up)
            side = np.cross(t, up)
            for sx, sy in section:
                verts.append(p + side * sx + up * sy)
        # a counter-clockwise section (in side/up coordinates) gets outward faces
        faces = []
        for i in range(len(path) - 1):
            for j in range(m if closed_section else m - 1):
                j1 = (j + 1) % m
                faces.append([i * m + j, (i + 1) * m + j, (i + 1) * m + j1, i * m + j1])
        base = self.add(verts, faces, mat, sharp)
        if caps and closed_section:
            last = len(path) - 1
            self._raw_face([base + j for j in range(m)], mat)
            self._raw_face([base + last * m + j for j in range(m)][::-1], mat)
        return base

    def _raw_face(self, f, mat, sharp=True):
        self.faces.append(f)
        self.mats.append(mat)
        self.sharp.append(sharp)
        self.uvs.append(None)

    def loft(self, sections, mat, closed=True, caps=True, sharp=False):
        """Loft through closed 3D sections with the same point count."""
        m = len(sections[0])
        verts = [p for s in sections for p in s]
        faces = []
        for i in range(len(sections) - 1):
            for j in range(m if closed else m - 1):
                j1 = (j + 1) % m
                faces.append([i * m + j, i * m + j1, (i + 1) * m + j1, (i + 1) * m + j])
        base = self.add(verts, faces, mat, sharp)
        if caps and closed:
            last = len(sections) - 1
            self._raw_face([base + j for j in range(m)][::-1], mat)
            self._raw_face([base + last * m + j for j in range(m)], mat)
        return base

    def fan(self, ring, centre, mat, sharp=False):
        """Triangle fan closing a ring onto a centre point (ring order sets
        the facing: counter-clockwise seen from the side the faces look to)."""
        base = self.add(list(ring) + [centre], [], mat)
        c = base + len(ring)
        k = len(ring)
        for i in range(k):
            self._raw_face([base + i, base + (i + 1) % k, c], mat, sharp)
        return base

    def box(self, c, size, mat, rot=None):
        cx, cy, cz = c
        sx, sy, sz = (s / 2 for s in size)
        pts = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
               (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
        R = rot or Matrix.Identity(3)
        pts = [R @ Vector(p) + Vector((cx, cy, cz)) for p in pts]
        faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        return self.add(pts, faces, mat, True)

    # output --------------------------------------------------------------------
    def corner_normals(self, smooth_angle=35.0):
        """Per-face lists of corner normals with smooth-by-angle shading
        (computed by Blender on a temporary mesh)."""
        me = bpy.data.meshes.new("_kit_tmp")
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        me.polygons.foreach_set("use_smooth", np.array([not s for s in self.sharp], bool))
        me.update()
        if hasattr(me, "set_sharp_from_angle"):
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        n = len(me.loops)
        cn = np.empty(n * 3)
        if hasattr(me, "corner_normals"):
            me.corner_normals.foreach_get("vector", cn)
        else:                                           # Blender < 4.1
            me.calc_normals_split()
            me.loops.foreach_get("normal", cn)
        cn = cn.reshape(-1, 3)
        starts = np.empty(len(me.polygons), int)
        totals = np.empty(len(me.polygons), int)
        me.polygons.foreach_get("loop_start", starts)
        me.polygons.foreach_get("loop_total", totals)
        out = [[tuple(cn[s + i]) for i in range(t)] for s, t in zip(starts, totals)]
        bpy.data.meshes.remove(me)
        return out

    def to_object(self, collection, materials, smooth_angle=35.0, uv_scale=1.0):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata([tuple(v) for v in self.verts], [], self.faces)
        slots = []                               # one slot per material (keys may alias)
        for m in self.mats:
            if materials[m] not in slots:
                slots.append(materials[m])
        for mat in slots:
            me.materials.append(mat)
        idx = {k: slots.index(materials[k]) for k in set(self.mats)}
        me.polygons.foreach_set("material_index", np.array([idx[m] for m in self.mats], np.int32))
        me.polygons.foreach_set("use_smooth", np.array([not s for s in self.sharp], bool))
        me.update()
        if hasattr(me, "set_sharp_from_angle"):
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        uv = me.uv_layers.new(name="UVMap")
        flat = []
        for p, uvs in zip(me.polygons, self.uvs):
            if uvs is not None and len(uvs) == p.loop_total:
                flat.extend(uvs)
            else:
                n = p.normal
                ax = int(np.argmax([abs(n.x), abs(n.y), abs(n.z)]))
                for vi in p.vertices:
                    c = me.vertices[vi].co
                    flat.append((c.y * uv_scale, c.z * uv_scale) if ax == 0 else
                                (c.x * uv_scale, c.z * uv_scale) if ax == 1 else
                                (c.x * uv_scale, c.y * uv_scale))
        uv.data.foreach_set("uv", np.array(flat, np.float32).ravel())
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


def _area(p):
    p = np.asarray(p, float)
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _orient(tri, outline, up):
    a, b, c = (outline[i] for i in tri)
    ccw = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0
    if ccw != up:
        return [tri[0], tri[2], tri[1]]
    return list(tri)


def frame_from(origin, normal, up_hint=(0.0, 0.0, 1.0)):
    """(origin, u, v, n) with n = normal, v ~ up_hint."""
    n = np.asarray(normal, float)
    n /= np.linalg.norm(n)
    up = np.asarray(up_hint, float)
    u = np.cross(up, n)
    if np.linalg.norm(u) < 1e-6:
        u = np.cross([1.0, 0.0, 0.0], n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    return (np.asarray(origin, float), u, v, n)


def circle2d(r, k=32, cx=0.0, cy=0.0):
    t = np.linspace(0, 2 * np.pi, k, endpoint=False)
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


def rounded_rect2d(w, h, r, k=6):
    r = min(r, w / 2 - 1e-6, h / 2 - 1e-6)
    out = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180),
                       (w / 2 - r, -h / 2 + r, 270)):
        for i in range(k + 1):
            a = math.radians(a0 + 90 * i / k)
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return np.array(out)
