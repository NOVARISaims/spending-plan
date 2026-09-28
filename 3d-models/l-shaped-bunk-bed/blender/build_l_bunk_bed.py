"""Procedural Blender build of an L-shaped high-sleeper bunk bed.

Modelled from product photos of the Habitat "Norah" L-shaped single bunk bed
(white & oak effect): a top bunk with safety rails and an open end cubby, a
two-door slatted wardrobe (shelves + hanging rail), two deep cubby holes
behind the wardrobe, a staircase-style ladder with oval hand holds and a
notched landing, and a single bed underneath at 90 degrees with a shelf
headboard.

Overall size follows the published spec: L214.2 x W215.5 x H160.4 cm,
wardrobe opening 110.3 cm high, 36 cm safety rail, 190 x 90 x 16 cm mattresses.
Everything else was measured off the photos.  All dimensions are in the
constants below (centimetres) so the model can be tweaked and rebuilt.

Usage:
    blender -b -P build_l_bunk_bed.py -- [--out DIR] [--render] [--samples N]
    python build_l_bunk_bed.py [...]          # with the PyPI `bpy` module

Writes (default --out is ../export next to this folder):
    SM_LBunkBed_*.fbx    one FBX per Unreal static mesh, with UCX_ collision
    LBunkBed.fbx         every part in one FBX (for other DCC tools)
    LBunkBed.glb         glTF binary with embedded textures
    textures/            oak PBR maps shared by Blender and Unreal
    manifest.json        parts, material slots, pivots and door hinges
    ../blend/LBunkBed.blend
    ../renders/*.png     only with --render
"""
import argparse
import json
import math
import os
import sys
import zlib

import bpy  # noqa: I001  (must precede bmesh with the PyPI bpy module)
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import oak_textures  # noqa: E402

CM = 0.01            # Blender works in metres; everything below is in cm
TEX_CM = 100.0       # one UV unit covers 1 m of wood

# ---------------------------------------------------------------------------
# Dimensions (cm).  Design frame: X = 0 at the open-shelf end (left in the
# photos) increasing towards the ladder, Y = 0 at the back (wall side) and
# negative towards the room, Z = 0 on the floor.
# ---------------------------------------------------------------------------
L = 214.2            # overall length (spec)
H = 160.4            # overall height (spec)
DEPTH_ALL = 215.5    # overall depth including the lower bed (spec)
T = 1.8              # board thickness
D = 95.0             # depth of the top-bunk frame
Y_FRONT = -D
Y_LADDER = -114.8    # front of the ladder (spec: top bunk 114.8 deep incl. ladder)
Z_DECK = 120.0       # underside of the top bunk / top of the wardrobe
Z_SLATS = H - 36.0   # top of the upper slats: 36 cm safety rail (spec)
RAIL_OPEN_H = 14.0   # low rail across the ladder opening
MATT_T = 16.0        # mattress thickness (spec 190 x 90 x 16)

X_CUBBY = 21.6       # inner face of the open end cubby on the top bunk
X_WARD = 77.5        # right-hand face of the wardrobe (double side panel)
X_WARD_IN = X_WARD - 2 * T   # 73.9, inside of that double panel
Y_WARD_BACK = Y_FRONT + 51.4  # wardrobe is 51.4 deep (spec)
X_STR_L = 171.4      # outer face of the left ladder stringer
X_STR_R = L - T      # 212.4, inner face of the right stringer / right end
Y_STR_BACK = Y_FRONT   # stringers sit in front of the top bunk (19.8 deep)

WARD_DOOR_Z = (7.6, 117.9)   # 110.3 cm high door opening (spec)
DOOR_GAP = 0.3
SLATS_PER_DOOR = 4
SLAT_GAP = 1.9
BATTEN_Z = [(8.6, 13.6), (24.0, 28.0), (60.3, 65.3), (111.9, 116.9)]
WARD_SHELVES_Z = [46.5, 82.0]
X_DIVIDER = 22.3             # narrow shelf column inside the wardrobe
DEEP_SHELF_Z = 56.4          # shelf in the deep cubby holes behind the wardrobe

# Staircase ladder: (tread top Z, tread front Y); treads step forward going down.
TREADS = [(119.6, -104.9), (92.8, -107.5), (66.0, -109.9)]
TREAD_DEPTH = 13.0
LANDING_Z = 37.5
LANDING_Y = (-114.3, -22.0)
NOTCH_X = 188.5              # notch in the landing, back-left corner
NOTCH_Y = -101.0
NOTCH_R = 8.0

# Lower bed (runs along Y under the top bunk, head against the shelf headboard).
LB_X = (77.6, 171.3)         # outer faces of the side rails / footboard
LB_Y_FOOT = -DEPTH_ALL       # outer face of the footboard
LB_Y_HEAD = -22.0            # front face of the shelf headboard
FOOT_H = 57.5
LB_RAIL_Z = (20.0, 40.0)
LB_SLAT_TOP = 28.2
HEAD_SHELF_Z = 56.6          # underside of the oak headboard shelf

# Materials: name -> (linear base colour, roughness, metallic)
W, OAK, BACKER, M_TOP, M_SIDE, SCREW, CHROME = (
    "M_WhiteLaminate", "M_Oak", "M_DoorBacker", "M_MattressTop",
    "M_MattressSide", "M_ScrewCap", "M_Chrome")
MATERIALS = {
    W: ((0.83, 0.83, 0.835), 0.42, 0.0),
    OAK: ((0.60, 0.46, 0.33), 0.50, 0.0),      # textured; colour is viewport only
    BACKER: ((0.012, 0.010, 0.009), 0.80, 0.0),
    M_TOP: ((0.74, 0.74, 0.74), 0.95, 0.0),
    M_SIDE: ((0.075, 0.076, 0.082), 0.95, 0.0),
    SCREW: ((0.32, 0.32, 0.33), 0.45, 0.0),
    CHROME: ((0.90, 0.90, 0.90), 0.18, 1.0),
}
# Unreal material instance created for each Blender material slot.
UE_MATERIALS = {
    W: ("MI_BB_WhiteLaminate", "M_BB_Solid"),
    OAK: ("MI_BB_Oak", "M_BB_Wood"),
    BACKER: ("MI_BB_DoorBacker", "M_BB_Solid"),
    M_TOP: ("MI_BB_MattressTop", "M_BB_Solid"),
    M_SIDE: ("MI_BB_MattressSide", "M_BB_Solid"),
    SCREW: ("MI_BB_ScrewCap", "M_BB_Solid"),
    CHROME: ("MI_BB_Chrome", "M_BB_Solid"),
}

DOOR_OPEN_DEG = 100.0


def to_blender(p):
    """Design-frame cm -> Blender metres, with the pivot at the centre of the
    back edge on the floor."""
    return Vector(((p[0] - L / 2.0) * CM, p[1] * CM, p[2] * CM))


def to_unreal(v):
    """Blender metres -> Unreal cm (FBX default axes: UE = (x, -y, z) * 100)."""
    return [round(v[0] * 100.0, 3), round(-v[1] * 100.0, 3), round(v[2] * 100.0, 3)]


# ---------------------------------------------------------------------------
# 2D outline helpers
# ---------------------------------------------------------------------------
def _dedupe(pts, eps=1e-6):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= eps and abs(out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


def rounded_rect(a0, a1, b0, b1, radii=(0.0, 0.0, 0.0, 0.0), seg=10):
    """Counter-clockwise rectangle outline with per-corner radii, corners in
    the order (a0,b0), (a1,b0), (a1,b1), (a0,b1)."""
    corners = [((a0, b0), (1, 1), 180.0), ((a1, b0), (-1, 1), 270.0),
               ((a1, b1), (-1, -1), 0.0), ((a0, b1), (1, -1), 90.0)]
    pts = []
    for ((ca, cb), (sa, sb), start), r in zip(corners, radii):
        if r <= 0.0:
            pts.append((ca, cb))
            continue
        oa, ob = ca + sa * r, cb + sb * r
        for k in range(seg + 1):
            ang = math.radians(start + 90.0 * k / seg)
            pts.append((oa + r * math.cos(ang), ob + r * math.sin(ang)))
    return _dedupe(pts)


def stadium(ca, cb, w, h, seg=12):
    r = min(w, h) / 2.0
    return rounded_rect(ca - w / 2, ca + w / 2, cb - h / 2, cb + h / 2, (r, r, r, r), seg)


def circle(ca, cb, r, seg=16):
    return [(ca + r * math.cos(2 * math.pi * k / seg), cb + r * math.sin(2 * math.pi * k / seg))
            for k in range(seg)]


# ---------------------------------------------------------------------------
# Mesh builder
# ---------------------------------------------------------------------------
class Part:
    """Accumulates the geometry of one exported mesh (one Unreal static mesh).

    Every board is its own closed solid; UVs are box-projected in world space
    at a constant texel density with U following the wood grain, plus a random
    per-board offset so neighbouring boards don't repeat the same figure.
    """

    def __init__(self, name, pivot=None, bevel=0.15, segments=2):
        self.name = name
        # Default pivot = the asset origin: centre of the back edge on the floor.
        self.pivot = Vector(pivot if pivot is not None else (L / 2.0, 0.0, 0.0))
        self.bevel = bevel
        self.segments = segments
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.mats = []
        self.collision = []
        self.rng = np.random.default_rng(zlib.crc32(name.encode()))

    def _local(self, p):
        return Vector(((p[0] - self.pivot.x) * CM, (p[1] - self.pivot.y) * CM,
                       (p[2] - self.pivot.z) * CM))

    def _slot(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def _finish(self, faces, mat, face_mats, grain):
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        off = self.rng.uniform(0.0, 1.0, 2)
        for f in faces:
            n = f.normal
            axis = max(range(3), key=lambda i: abs(n[i]))
            key = ("+" if n[axis] > 0 else "-") + "XYZ"[axis]
            f.material_index = self._slot((face_mats or {}).get(key, mat))
            ua, va = [i for i in range(3) if i != axis]
            if grain == va:
                ua, va = va, ua
            for loop in f.loops:
                p = loop.vert.co / CM + self.pivot
                loop[self.uv].uv = (p[ua] / TEX_CM + off[0], p[va] / TEX_CM + off[1])

    def box(self, x0, x1, y0, y1, z0, z1, mat=W, faces=None, grain=None, collide=False):
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        if grain is None:
            dims = (x1 - x0, y1 - y0, z1 - z0)
            grain = max(range(3), key=dims.__getitem__)
        v = [self.bm.verts.new(self._local((x, y, z)))
             for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                 (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        fs = [self.bm.faces.new([v[i] for i in q]) for q in quads]
        self._finish(fs, mat, faces, grain)
        if collide:
            self.collision.append((x0, x1, y0, y1, z0, z1))
        return fs

    def prism(self, outline, holes, axis, a0, a1, mat=W, faces=None, grain=None,
              collide=False):
        """Extrude a 2D outline (optionally with holes) along axis 'X'/'Y'/'Z'
        between a0 and a1.  2D coordinates use the remaining axes in XYZ order
        (X -> (y, z), Y -> (x, z), Z -> (x, y))."""
        ai = "XYZ".index(axis)
        oi = [i for i in range(3) if i != ai]
        loops = [_dedupe(outline)] + [_dedupe(h) for h in holes]
        flat = [p for lp in loops for p in lp]
        tris = tessellate_polygon([[Vector((p[0], p[1], 0.0)) for p in lp] for lp in loops])

        def to3(p, a):
            c = [0.0, 0.0, 0.0]
            c[ai], c[oi[0]], c[oi[1]] = a, p[0], p[1]
            return c

        v0 = [self.bm.verts.new(self._local(to3(p, a0))) for p in flat]
        v1 = [self.bm.verts.new(self._local(to3(p, a1))) for p in flat]
        fs = []
        for t in tris:
            fs.append(self.bm.faces.new([v0[i] for i in t]))
            fs.append(self.bm.faces.new([v1[i] for i in reversed(t)]))
        start = 0
        for lp in loops:
            n = len(lp)
            for i in range(n):
                a, b = start + i, start + (i + 1) % n
                fs.append(self.bm.faces.new([v0[a], v0[b], v1[b], v1[a]]))
            start += n
        if grain is None:
            ext = [max(p[k] for p in loops[0]) - min(p[k] for p in loops[0]) for k in (0, 1)]
            grain = oi[0] if ext[0] >= ext[1] else oi[1]
        self._finish(fs, mat, faces, grain)
        if collide:
            lo = [0.0] * 3
            hi = [0.0] * 3
            lo[ai], hi[ai] = sorted((a0, a1))
            for k in (0, 1):
                lo[oi[k]] = min(p[k] for p in loops[0])
                hi[oi[k]] = max(p[k] for p in loops[0])
            self.collision.append((lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
        return fs

    def screw(self, x, y, z, face, r=0.6, depth=0.18):
        """Grey plastic cover cap on a board face ('-X', '+X', '-Y', '+Y')."""
        sign = -1.0 if face[0] == "-" else 1.0
        axis = face[1]
        if axis == "X":
            self.prism(circle(y, z, r), [], "X", x - 0.05 * sign, x + depth * sign, SCREW)
        else:
            self.prism(circle(x, z, r), [], "Y", y - 0.05 * sign, y + depth * sign, SCREW)

    def to_object(self, collection, materials):
        me = bpy.data.meshes.new(self.name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for key in self.mats:
            me.materials.append(materials[key])
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        if hasattr(me, "use_auto_smooth"):          # Blender < 4.1
            me.use_auto_smooth = True
        me.update()
        ob = bpy.data.objects.new(self.name, me)
        ob.location = to_blender(self.pivot)
        collection.objects.link(ob)
        if self.bevel > 0.0:
            bev = ob.modifiers.new("Bevel", "BEVEL")
            bev.width = self.bevel * CM
            bev.segments = self.segments
            bev.limit_method = "ANGLE"
            bev.angle_limit = math.radians(35.0)
            bev.harden_normals = True
            bev.use_clamp_overlap = True
        return ob


# ---------------------------------------------------------------------------
# The furniture
# ---------------------------------------------------------------------------
def build_top_bunk(fr):
    oak_edge_x = {"-X": OAK}
    # Deck over the wardrobe and deep cubbies; its end edge is oak.
    fr.box(0, X_WARD, Y_FRONT, 0, Z_DECK - T, Z_DECK, W, oak_edge_x, collide=True)
    # Open end cubby (opens towards -X), oak front edges like the photos.
    fr.box(0, X_CUBBY, Y_FRONT + T, -T, H - T, H, W, oak_edge_x)
    fr.box(X_CUBBY - T, X_CUBBY, Y_FRONT + T, -T, Z_DECK, H - T, W)
    fr.collision.append((0, X_CUBBY, Y_FRONT + T, -T, Z_DECK, H))
    # Safety rails: front (up to the ladder), back, right-hand end.
    fr.box(0, X_STR_L, Y_FRONT, Y_FRONT + T, Z_DECK, H, W, collide=True)
    fr.box(0, X_STR_R, -T, 0, Z_DECK, H, W, collide=True)
    fr.box(X_STR_R, L, Y_STR_BACK, LB_Y_HEAD, Z_DECK, H, W, collide=True)
    # Low front rail across the ladder opening (mattress retainer); its top
    # sweeps up into the left stringer with a small fillet.
    x0, x1, zt, r = X_STR_L + T, X_STR_R, Z_DECK + RAIL_OPEN_H, 5.0
    rail = [(x0, Z_DECK), (x1, Z_DECK), (x1, zt), (x0 + r, zt)]
    rail += [(x0 + r - r * math.sin(math.radians(a)), zt + r - r * math.cos(math.radians(a)))
             for a in range(10, 90, 10)]
    rail += [(x0, zt + r)]
    fr.prism(rail, [], "Y", Y_FRONT, Y_FRONT + T, W, collide=True)
    # Slat ledges and slats.
    zl = Z_SLATS - 1.2
    fr.box(X_CUBBY, X_STR_R, Y_FRONT + T, Y_FRONT + T + 2.0, zl - 2.0, zl, OAK)
    fr.box(X_CUBBY, X_STR_R, -T - 2.0, -T, zl - 2.0, zl, OAK)
    n = 16
    pitch = (X_STR_R - X_CUBBY - 7.0) / (n - 1)
    for i in range(n):
        x = X_CUBBY + 0.1 + i * pitch
        fr.box(x, x + 7.0, Y_FRONT + T, -T, zl, Z_SLATS, OAK)
    fr.collision.append((X_CUBBY, X_STR_R, Y_FRONT + T, -T, Z_DECK, Z_SLATS))
    # Screw caps on the guard rail and the low rail (as in the photos).
    for x in (33.0, 120.0):
        fr.screw(x, Y_FRONT, Z_DECK + 3.2, "-Y")
    for z in (Z_DECK + 3.0, Z_DECK + 11.0):
        fr.screw(X_STR_R - 3.0, Y_FRONT, z, "-Y")


def build_wardrobe(fr):
    zb0, zb1 = 5.5, 7.3                      # carcass bottom panel
    top = Z_DECK - T                          # underside of the deck
    fr.box(0, T, Y_FRONT, Y_WARD_BACK, 0, top, W)                    # left side
    fr.box(X_WARD_IN, X_WARD, Y_FRONT, 0, 0, top, W)                 # double right side
    fr.box(T, X_WARD_IN, Y_WARD_BACK - T, Y_WARD_BACK, 0, top, W)    # back
    fr.box(T, X_WARD_IN, Y_FRONT, Y_WARD_BACK - T, zb0, zb1, W, {"+Z": OAK})
    fr.box(T, X_WARD_IN, Y_FRONT + 3.0, Y_FRONT + 3.0 + T, 0, zb0, W)  # recessed plinth
    fr.collision.append((0, X_WARD, Y_FRONT + 4.0, Y_WARD_BACK, 0, top))
    # Interior: oak divider with two shelves on the left, hanging space on the right.
    y_in0, y_in1 = Y_FRONT + 4.0, Y_WARD_BACK - T
    fr.box(X_DIVIDER, X_DIVIDER + T, y_in0, y_in1, zb1, top, OAK, grain=2)
    for z in WARD_SHELVES_Z:
        fr.box(T, X_DIVIDER, y_in0, y_in1, z, z + T, OAK, grain=0)
    # Hanging rail with two end brackets.
    y_rail, z_rail = (y_in0 + y_in1) / 2.0, 108.0
    fr.prism(circle(y_rail, z_rail, 1.1, 20), [], "X", X_DIVIDER + T, X_WARD_IN, CHROME)
    for x in (X_DIVIDER + T, X_WARD_IN - 0.6):
        fr.box(x, x + 0.6, y_rail - 2.0, y_rail + 2.0, z_rail - 2.5, z_rail + 2.0, CHROME)


def build_deep_cubbies(fr):
    """Two deep cubby holes behind the wardrobe, open to the end of the bed."""
    top = Z_DECK - T
    y0, y1 = Y_WARD_BACK, -T
    fr.box(0, X_WARD_IN, -T, 0, 0, top, W)                           # back panel
    fr.box(0, X_WARD_IN, y0, y1, 5.5, 7.3, W, {"-X": OAK})           # floor
    fr.box(1.0, 1.0 + T, y0, y1, 0, 5.5, W)                          # plinth
    # Shelf with a white lip, as seen in the three-quarter photo.
    fr.box(0, X_WARD_IN, y0, y1, DEEP_SHELF_Z, DEEP_SHELF_Z + T, W, {"+Z": OAK}, grain=0)
    fr.box(0, T, y0, y1, DEEP_SHELF_Z - 4.0, DEEP_SHELF_Z, W)
    fr.collision.append((0, X_WARD_IN, y0, 0, 0, top))


def build_ladder(fr):
    # Wide oak stringers: rounded front-top corner, stadium hand hold.
    outline = rounded_rect(Y_LADDER, Y_STR_BACK, 0.0, H, (0.0, 0.0, 0.4, 9.0), seg=16)
    hole = stadium(-106.1, 146.3, 6.5, 13.7)
    for x0 in (X_STR_L, X_STR_R):
        fr.prism(outline, [hole], "X", x0, x0 + T, OAK, grain=2, collide=True)
    x0, x1 = X_STR_L + T, X_STR_R
    # Treads: oak top board over a white sub-board, fixed with caps on the stringers.
    for z, y in TREADS:
        yb = y + TREAD_DEPTH
        fr.box(x0, x1, y, yb, z - T, z, OAK, grain=0, collide=True)
        fr.box(x0, x1, y + 0.5, yb, z - T - 1.6, z - T, W, grain=0)
        for ys in (y + 3.0, min(yb, Y_STR_BACK) - 3.0):
            fr.screw(X_STR_L, ys, z - 1.7, "-X")
            fr.screw(L, ys, z - 1.7, "+X")
    # Landing: notched oak board on a white sub-board, over a white box.
    ya, yb = LANDING_Y
    r = NOTCH_R
    notch = [(x0, ya), (x1, ya), (x1, yb), (NOTCH_X, yb), (NOTCH_X, NOTCH_Y + r)]
    for k in range(1, 12):
        ang = math.radians(-90.0 * k / 12)
        notch.append((NOTCH_X - r + r * math.cos(ang), NOTCH_Y + r + r * math.sin(ang)))
    notch += [(NOTCH_X - r, NOTCH_Y), (x0, NOTCH_Y)]
    fr.prism(notch, [], "Z", LANDING_Z - T, LANDING_Z, OAK, grain=0)
    fr.prism(notch, [], "Z", LANDING_Z - T - 1.6, LANDING_Z - T, W, grain=0)
    zt = LANDING_Z - T - 1.6
    fr.box(x0, x1, ya + 1.0, ya + 1.0 + T, 2.3, zt, W)               # box front
    fr.box(x0, x1, ya + 1.0, yb, 0.5, 2.3, W, {"-Y": OAK})           # box bottom
    fr.box(X_STR_L, x0, Y_STR_BACK, yb, 0, zt, W)                    # box sides
    fr.box(X_STR_R, L, Y_STR_BACK, yb, 0, zt, W)
    fr.collision.append((x0, x1, ya, yb, 0, LANDING_Z))
    for ys in (ya + 4.0, ya + 11.0):
        fr.screw(X_STR_L, ys, LANDING_Z - 1.7, "-X")
        fr.screw(L, ys, LANDING_Z - 1.7, "+X")


def build_lower_bed(fr):
    xa, xb = LB_X
    y_in = LB_Y_FOOT + T
    # Footboard with softly rounded top corners.
    fb = rounded_rect(xa, xb, 0.0, FOOT_H, (0.0, 0.0, 1.5, 1.5), seg=6)
    fr.prism(fb, [], "Y", LB_Y_FOOT, y_in, W, collide=True)
    for x in (xa + 2.8, xb - 2.8):
        for z in (25.5, 35.0):
            fr.screw(x, LB_Y_FOOT, z, "-Y")
    # Oak side rails, slat ledges and slats.
    z0, z1 = LB_RAIL_Z
    for x in (xa, xb - T):
        fr.box(x, x + T, y_in, LB_Y_HEAD, z0, z1, OAK, grain=1, collide=True)
    zl = LB_SLAT_TOP - 1.2
    fr.box(xa + T, xa + T + 2.0, y_in, LB_Y_HEAD, zl - 2.0, zl, OAK, grain=1)
    fr.box(xb - T - 2.0, xb - T, y_in, LB_Y_HEAD, zl - 2.0, zl, OAK, grain=1)
    n = 14
    pitch = (LB_Y_HEAD - y_in - 7.0) / (n - 1)
    for i in range(n):
        y = y_in + i * pitch
        fr.box(xa + T, xb - T, y, y + 7.0, zl, LB_SLAT_TOP, OAK, grain=0)
    fr.collision.append((xa + T, xb - T, y_in, LB_Y_HEAD, zl - 2.0, LB_SLAT_TOP))
    # Shelf headboard spanning from the wardrobe to the back-right post.
    fr.box(X_WARD, X_STR_R, LB_Y_HEAD, LB_Y_HEAD + T, 0, HEAD_SHELF_Z, W)
    fr.box(X_WARD, X_STR_R, -T, 0, 0, HEAD_SHELF_Z, W)
    fr.box(X_WARD, X_STR_R, LB_Y_HEAD - 0.6, 0, HEAD_SHELF_Z, HEAD_SHELF_Z + T, OAK, grain=0)
    fr.collision.append((X_WARD, X_STR_R, LB_Y_HEAD - 0.6, 0, 0, HEAD_SHELF_Z + T))
    # Full-height oak post at the back-right corner carrying the top bunk.
    fr.box(X_STR_R, L, LB_Y_HEAD, 0, 0, H, OAK, grain=2, collide=True)


def build_door(side):
    """Slatted door: 4 oak slats over 4 oak battens on a dark backer panel.
    The pivot sits on the hinge axis (front outer corner) so it can swing."""
    width = (X_WARD_IN - T - 3 * DOOR_GAP) / 2.0
    if side == "L":
        xa = T + DOOR_GAP
        pivot = (xa, Y_FRONT, WARD_DOOR_Z[0])
    else:
        xa = X_WARD_IN - DOOR_GAP - width
        pivot = (xa + width, Y_FRONT, WARD_DOOR_Z[0])
    xb = xa + width
    part = Part("SM_LBunkBed_Door_" + side, pivot)
    za, zb = WARD_DOOR_Z
    y_slat, y_batten, y_backer = Y_FRONT + 1.5, Y_FRONT + 2.8, Y_FRONT + 4.0
    slat_w = (width - (SLATS_PER_DOOR - 1) * SLAT_GAP) / SLATS_PER_DOOR
    for i in range(SLATS_PER_DOOR):
        x = xa + i * (slat_w + SLAT_GAP)
        part.box(x, x + slat_w, Y_FRONT, y_slat, za, zb, OAK, grain=2)
    for z0, z1 in BATTEN_Z:
        part.box(xa, xb, y_slat, y_batten, z0, z1, OAK, grain=0)
    part.box(xa, xb, y_batten, y_backer, za, zb, W, {"-Y": BACKER})
    part.collision.append((xa, xb, Y_FRONT, y_backer, za, zb))
    return part


def build_mattress(name, x0, x1, y0, y1, z0):
    part = Part(name, bevel=2.4, segments=4)
    part.box(x0, x1, y0, y1, z0, z0 + MATT_T, M_SIDE, {"+Z": M_TOP, "-Z": M_TOP}, collide=True)
    return part


def build_parts():
    frame = Part("SM_LBunkBed_Frame")
    build_top_bunk(frame)
    build_wardrobe(frame)
    build_deep_cubbies(frame)
    build_ladder(frame)
    build_lower_bed(frame)
    mid_u = (X_CUBBY + X_STR_R) / 2.0
    mid_l = (LB_X[0] + LB_X[1]) / 2.0
    y_head = LB_Y_HEAD - 0.8
    return [
        frame,
        build_door("L"),
        build_door("R"),
        build_mattress("SM_LBunkBed_Mattress_Upper", mid_u - 95.0, mid_u + 95.0,
                       Y_FRONT + T + 0.7, -T - 0.7, Z_SLATS),
        build_mattress("SM_LBunkBed_Mattress_Lower", mid_l - 45.0, mid_l + 45.0,
                       y_head - 190.0, y_head, LB_SLAT_TOP),
    ]


# ---------------------------------------------------------------------------
# Textures and materials
# ---------------------------------------------------------------------------
def write_image(path, arr, is_data, fmt, quality=92):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h, alpha=False,
                              is_data=is_data)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = arr[..., None] if arr.ndim == 2 else arr
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path
    img.file_format = fmt
    img.save(quality=quality) if fmt == "JPEG" else img.save()
    bpy.data.images.remove(img)
    loaded = bpy.data.images.load(path)
    if is_data:
        loaded.colorspace_settings.name = "Non-Color"
    return loaded


def make_textures(tex_dir, size):
    os.makedirs(tex_dir, exist_ok=True)
    base, rough, normal = oak_textures.oak_maps(size)
    half = slice(None, None, 2)
    return {
        "base": write_image(os.path.join(tex_dir, "T_Oak_BaseColor.jpg"), base, False, "JPEG"),
        "rough": write_image(os.path.join(tex_dir, "T_Oak_Roughness.png"),
                             rough[half, half], True, "PNG"),
        "normal": write_image(os.path.join(tex_dir, "T_Oak_Normal.png"),
                              normal[half, half], True, "PNG"),
    }


def make_materials(tex):
    mats = {}
    for name, (color, rough, metal) in MATERIALS.items():
        m = bpy.data.materials.new(name)
        if bpy.app.version < (5, 0, 0):      # always node-based from 5.0
            m.use_nodes = True
        m.diffuse_color = (*color, 1.0)
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        if name == OAK:
            nodes = nt.nodes
            tb = nodes.new("ShaderNodeTexImage")
            tb.image = tex["base"]
            tb.location = (-600, 300)
            tr = nodes.new("ShaderNodeTexImage")
            tr.image = tex["rough"]
            tr.location = (-600, 0)
            tn = nodes.new("ShaderNodeTexImage")
            tn.image = tex["normal"]
            tn.location = (-600, -300)
            nm = nodes.new("ShaderNodeNormalMap")
            nm.inputs["Strength"].default_value = 0.6
            nm.location = (-250, -300)
            nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
            nt.links.new(tr.outputs["Color"], bsdf.inputs["Roughness"])
            nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        mats[name] = m
    return mats


# ---------------------------------------------------------------------------
# Scene assembly and export
# ---------------------------------------------------------------------------
def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def make_collision(part, collection):
    objs = []
    for i, (x0, x1, y0, y1, z0, z1) in enumerate(part.collision):
        c = Part("UCX_%s_%02d" % (part.name, i), part.pivot, bevel=0.0)
        c.box(x0, x1, y0, y1, z0, z1)
        ob = c.to_object(collection, {W: None})
        ob.data.materials.clear()
        ob.display_type = "WIRE"
        ob.hide_render = True
        objs.append(ob)
    return objs


def op_kwargs(op, **kw):
    """Drop keyword arguments an operator doesn't know (API drift between versions)."""
    props = op.get_rna_type().properties.keys()
    return {k: v for k, v in kw.items() if k in props}


def select_only(objs):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_fbx(path, objs):
    select_only(objs)
    op = bpy.ops.export_scene.fbx
    op(**op_kwargs(op, filepath=path, use_selection=True, object_types={"MESH"},
                   global_scale=1.0, apply_unit_scale=True,
                   apply_scale_options="FBX_SCALE_NONE", axis_forward="-Z", axis_up="Y",
                   use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=False,
                   use_custom_props=False, add_leaf_bones=False, bake_anim=False,
                   path_mode="STRIP", embed_textures=False))


def export_glb(path, objs):
    select_only(objs)
    op = bpy.ops.export_scene.gltf
    op(**op_kwargs(op, filepath=path, export_format="GLB", use_selection=True,
                   export_apply=True, export_yup=True, export_texcoords=True,
                   export_normals=True, export_materials="EXPORT",
                   export_image_format="AUTO", export_jpeg_quality=90,
                   export_cameras=False, export_lights=False, export_extras=False))


def triangle_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ob.evaluated_get(dg).to_mesh_clear()
    return n


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    return scene


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "export")))
    ap.add_argument("--blend", default=os.path.normpath(os.path.join(HERE, "..", "blend",
                                                                     "LBunkBed.blend")))
    ap.add_argument("--renders", default=os.path.normpath(os.path.join(HERE, "..", "renders")))
    ap.add_argument("--tex-size", type=int, default=2048)
    ap.add_argument("--render", action="store_true", help="render preview images (Cycles)")
    ap.add_argument("--samples", type=int, default=160)
    ap.add_argument("--views", default="", help="comma separated subset of views to render")
    ap.add_argument("--jpeg", type=int, default=0, metavar="QUALITY",
                    help="save renders as JPEG with this quality instead of PNG")
    ap.add_argument("--no-export", action="store_true")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    scene = reset_scene()
    tex = make_textures(os.path.join(out, "textures"), args.tex_size)
    mats = make_materials(tex)

    root = new_collection("LBunkBed")
    col_coll = new_collection("Collision (UCX)", root)
    parts = build_parts()
    objects, collisions, slots = {}, {}, {}
    for part in parts:
        ucx = make_collision(part, col_coll)
        objects[part.name] = part.to_object(root, mats)
        slots[part.name] = list(part.mats)
        collisions[part.name] = ucx

    manifest = {
        "name": "L-shaped high sleeper bunk bed with wardrobe (white & oak)",
        "reference": "Habitat Norah L Shaped Single Bunk Bed - White & Oak",
        "units": "centimetres",
        "overall_cm": {"length_x": L, "depth_y": DEPTH_ALL, "height_z": H},
        "pivot": "floor level, back (wall) face, centred along the length",
        "unreal_mapping": "UE(x, y, z) = Blender(x, -y, z) * 100 (FBX -Z forward / Y up)",
        "materials": {k: {"ue_instance": v[0], "ue_parent": v[1],
                          "base_color_linear": MATERIALS[k][0],
                          "roughness": MATERIALS[k][1], "metallic": MATERIALS[k][2]}
                      for k, v in UE_MATERIALS.items()},
        "textures": {"base_color": "textures/T_Oak_BaseColor.jpg",
                     "roughness": "textures/T_Oak_Roughness.png",
                     "normal": "textures/T_Oak_Normal.png",
                     "normal_convention": "OpenGL (+Y); flip green in Unreal",
                     "uv_scale": "1 UV unit = %g cm" % TEX_CM},
        "parts": [],
    }

    if not args.no_export:
        for name, ob in objects.items():
            ucx = collisions[name]
            saved = [(o, o.location.copy()) for o in [ob] + ucx]
            for o, _ in saved:            # export with the pivot at the file origin
                o.location = (0.0, 0.0, 0.0)
            export_fbx(os.path.join(out, name + ".fbx"), [ob] + ucx)
            for o, loc in saved:
                o.location = loc
        render_objs = list(objects.values())
        export_fbx(os.path.join(out, "LBunkBed.fbx"), render_objs)
        export_glb(os.path.join(out, "LBunkBed.glb"), render_objs)

    for name, ob in objects.items():
        entry = {
            "name": name,
            "fbx": name + ".fbx",
            "material_slots": [{"slot": m, "ue_instance": UE_MATERIALS[m][0]}
                               for m in slots[name]],
            "pivot_blender_m": [round(c, 5) for c in ob.location],
            "pivot_unreal_cm": to_unreal(ob.location),
            "collision_boxes": len(collisions[name]),
            "triangles": triangle_count(ob),
        }
        if "_Door_" in name:
            sign = -1.0 if name.endswith("_L") else 1.0
            entry["hinge"] = {"axis": "Z", "max_open_deg": DOOR_OPEN_DEG,
                              "blender_open_sign": sign, "unreal_open_yaw_sign": -sign,
                              "gltf_open_sign": sign}
        manifest["parts"].append(entry)
    with open(os.path.join(out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    col_coll.hide_render = True
    if args.render:
        import render_views
        render_views.render_all(scene, objects, args.renders, args.samples,
                                [v for v in args.views.split(",") if v], args.jpeg or None)

    col_coll.hide_viewport = True
    for ob in objects.values():
        if "_Door_" in ob.name:
            ob.rotation_euler = (0.0, 0.0, 0.0)
    os.makedirs(os.path.dirname(os.path.abspath(args.blend)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend), relative_remap=True,
                                compress=True)
    total = sum(p["triangles"] for p in manifest["parts"])
    print("Built %d parts, %d triangles -> %s" % (len(parts), total, out))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
