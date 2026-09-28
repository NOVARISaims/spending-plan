"""Interior of the 2017 Qashqai Acenta: right-hand drive, 6-speed manual,
cloth seats, CD / radio unit and dual-zone climate control, modelled from
the owner's photos of the car.

Everything is built in the car frame (X forward, Y left, Z up, metres) into
one Kit (SM_Qashqai_Interior):

    lining     headliner, pillar trims, door cards and boot sides: the body
               shell offset inwards, so the trims follow the outside and keep
               the window openings exactly, with a return to each window
    floor      carpeted tub with the transmission tunnel, boot floor,
               wheel-house covers, parcel shelf
    dashboard  soft-touch dash with the instrument binnacle and dials, four
               vents, the piano-black centre stack (the audio and climate
               panels are a texture) and the gloss-black strip across the
               passenger side
    wheel      three-spoke leather wheel with satin inserts and switch pads
    console    gear lever with gaiter, e-parking brake switch, cup holders,
               armrest
    seats      front seats and the rear bench with bolsters, patterned
               centre panels and headrests
    details    door handles, armrests, speakers, window switches, interior
               mirror, sun visors, roof console, pedals, seat belts

Every closed part is oriented outwards (checked by its signed volume) and
the open surfaces face into the cabin, so the mesh works with single-sided
materials in Unreal.
"""
import math

import bpy  # noqa: F401  (must precede mathutils with the PyPI bpy module)
import numpy as np
from mathutils import Vector, geometry
from mathutils.kdtree import KDTree

import body_build as bb
import body_mesh as bm
import mesh_kit as mk
import qashqai_body as qb
import qashqai_parts as qp

DRIVER_Y = -0.37                 # right-hand drive
FLOOR_Z = 0.33
BOOT_Z = 0.64
LINING_DS = 0.035                # grid of the (coarser) shell copy used for the trims

# beltline (bottom of the side windows, and the quarter-light behind them)
BELT = [(-2.20, 1.15), (-1.42, 1.30), (-1.25, 1.25), (-1.02, 1.17), (-0.81, 1.113), (-0.39, 1.089),
        (0.12, 1.074), (0.57, 1.059), (0.81, 1.052), (1.25, 1.06)]
FRONT_DOOR = (0.80, -0.215)      # x range of the door cards
REAR_DOOR = (-0.275, -1.20)
CARD_SPLIT_Z = 0.84              # soft upper door card / harder lower part
BOOT_TRIM_X = -1.32              # boot side trims start behind the rear backrest
SHELF_Z = 1.12


def belt_z(x):
    xs, zs = zip(*BELT)
    return np.interp(x, xs, zs)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------
def signed_volume(verts, faces):
    V = np.asarray(verts, float)
    vol = 0.0
    for f in faces:
        a = V[f[0]]
        for i in range(1, len(f) - 1):
            vol += a @ np.cross(V[f[i]], V[f[i + 1]])
    return vol / 6.0


def add_closed(kit, verts, faces, mats, sharp=False, uvs=None):
    """Add a closed piece, flipped if needed so that its faces point out."""
    if signed_volume(verts, faces) < 0:
        faces = [f[::-1] for f in faces]
        if uvs is not None:
            uvs = [u[::-1] for u in uvs]
    base = len(kit.verts)
    kit.verts.extend(Vector((float(p[0]), float(p[1]), float(p[2]))) for p in verts)
    for k, f in enumerate(faces):
        kit.faces.append([base + i for i in f])
        kit.mats.append(mats[k] if isinstance(mats, (list, tuple)) else mats)
        kit.sharp.append(sharp)
        kit.uvs.append(None if uvs is None else uvs[k])
    return base


def add_open(kit, verts, faces, mats, facing, sharp=False, uvs=None):
    """Add an open surface; `facing` is a point the faces should look
    towards (their average normal is flipped to face it)."""
    V = np.asarray(verts, float)
    n = np.zeros(3)
    c = np.zeros(3)
    for f in faces:
        p = V[f]
        for i in range(len(f)):
            n += np.cross(p[i], p[(i + 1) % len(f)])
        c += p.mean(0)
    c /= max(len(faces), 1)
    if n @ (np.asarray(facing, float) - c) < 0:
        faces = [f[::-1] for f in faces]
        if uvs is not None:
            uvs = [u[::-1] for u in uvs]
    base = len(kit.verts)
    kit.verts.extend(Vector((float(p[0]), float(p[1]), float(p[2]))) for p in V)
    for k, f in enumerate(faces):
        kit.faces.append([base + i for i in f])
        kit.mats.append(mats[k] if isinstance(mats, (list, tuple)) else mats)
        kit.sharp.append(sharp)
        kit.uvs.append(None if uvs is None else uvs[k])
    return base


def loft_rows(rows, closed=True, caps=True):
    """Vertices and faces through rows of points (each (n, 3)); caps are fans
    around each end row's centroid.  Returns verts, faces, and (row, col) of
    each side face (None for cap faces)."""
    rows = [np.asarray(r, float) for r in rows]
    n = len(rows[0])
    verts = [p for r in rows for p in r]
    faces, where = [], []
    for i in range(len(rows) - 1):
        for j in range(n if closed else n - 1):
            j1 = (j + 1) % n
            faces.append([i * n + j, i * n + j1, (i + 1) * n + j1, (i + 1) * n + j])
            where.append((i, j))
    if caps and closed:
        for i, rev in ((0, True), (len(rows) - 1, False)):
            for t in cap_triangles(rows[i]):
                f = [i * n + k for k in t]
                faces.append(f[::-1] if rev else f)
                where.append(None)
    return verts, faces, where


def cap_triangles(ring):
    """Triangulate a (roughly planar) closed ring, keeping the ring's own
    winding for every triangle (works for non-convex outlines)."""
    R = np.asarray(ring, float)
    c = R.mean(0)
    _, _, vt = np.linalg.svd(R - c, full_matrices=False)
    e1, e2 = vt[0], vt[1]
    P2 = np.column_stack([(R - c) @ e1, (R - c) @ e2])
    area = 0.5 * np.sum(P2[:, 0] * np.roll(P2[:, 1], -1) - np.roll(P2[:, 0], -1) * P2[:, 1])
    tris = geometry.tessellate_polygon([[Vector((p[0], p[1], 0.0)) for p in P2]])
    out = []
    for a, b, d in tris:
        cr = (P2[b, 0] - P2[a, 0]) * (P2[d, 1] - P2[a, 1]) - (P2[b, 1] - P2[a, 1]) * (P2[d, 0] - P2[a, 0])
        out.append([a, b, d] if (cr > 0) == (area > 0) else [a, d, b])
    return out


def smooth_closed_2d(pts, n_per=3):
    return bm.smooth_closed(np.asarray(pts, float), n_per)


def axes_frame(o, u, v):
    """Right-handed frame (o, u, v, u x v)."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    v = np.asarray(v, float) / np.linalg.norm(v)
    return (np.asarray(o, float), u, v, np.cross(u, v))


def rot90(pts):
    """Rotate a 2D outline by 90 degrees (keeps its winding)."""
    pts = np.asarray(pts, float)
    return np.column_stack([-pts[:, 1], pts[:, 0]])


def rounded_box(kit, centre, size, radius, mat, ex=(1.0, 0.0, 0.0), ey=(0.0, 1.0, 0.0), seg=4):
    """Box with rounded edges round its third axis (a rounded-rectangle
    prism): size[0] along ex, size[1] along ey, size[2] along ex x ey."""
    o, u, v, n = axes_frame(centre, ex, ey)
    outline = mk.rounded_rect2d(size[0], size[1], radius, seg)
    kit.prism(outline, -size[2] / 2, size[2] / 2, (o, u, v, n), mat, sharp=False)


def recess_prism(kit, outline, depth, frame, mat, back_mat=None, z_top=0.0):
    """Pocket behind an outline: walls facing into the pocket and a floor
    facing out of it (for vents, cup holders)."""
    o, u, v, n = (np.asarray(a, float) for a in frame)
    outline = np.asarray(outline, float)
    if mk._area(outline) < 0:
        outline = outline[::-1]
    k = len(outline)

    def P(p, z):
        return o + u * p[0] + v * p[1] + n * z
    verts = [P(p, z_top - depth) for p in outline] + [P(p, z_top) for p in outline]
    faces = [[k + i, k + (i + 1) % k, (i + 1) % k, i] for i in range(k)]
    kit.add(verts, faces, mat, True)
    kit.cap(outline, z_top - depth, (o, u, v, n), back_mat or mat, up=True)


def pillow(kit, frame, w, d, h, mats, bolster=0.0, bolster_w=0.11, taper=0.0, crown=0.008,
           panels=(), panel_v=(0.0, 1.0), n_u=18, round_r=0.025, back_mat=None):
    """Upholstered block: width w (across, u), length d (along, v), thickness
    h (up, n) in frame (o, U, V, Nn); o is the middle of the v=0 edge on the
    bottom face.  The top rises into side bolsters; `panels` are u ranges
    (fractions of the width, -0.5..0.5) of the patterned centre panels over
    the v fraction range panel_v.  mats = (panel, side)."""
    o, U, V, Nn = (np.asarray(a, float) for a in frame)
    mat_panel, mat_side = mats
    back_mat = back_mat or mat_side
    # v stations with rounded ends
    ends = [(0.0, 0.45, 0.024), (0.006, 0.70, 0.013), (0.016, 0.86, 0.006), (0.032, 0.95, 0.002),
            (0.06, 1.0, 0.0)]
    vs = [e for e in ends] + [(d * t, 1.0, 0.0) for t in np.linspace(0.18, 0.82, 6)] + \
        [(d - e[0], e[1], e[2]) for e in ends[::-1]]
    us = np.linspace(-0.5, 0.5, n_u)
    rows, top_n = [], n_u
    for v, hf, inset in vs:
        wv = w * (1.0 - taper * v / d) - 2 * inset
        r = min(round_r, h * hf * 0.45)
        top = []
        for s in us[::-1]:
            u = s * wv
            b = bolster * smoothstep((abs(u) - (wv / 2 - bolster_w)) / 0.045)
            hh = h * hf + (b - crown * math.cos(math.pi * s)) * hf
            e = max(0.0, abs(u) - (wv / 2 - r)) / r            # round over the top edges
            hh -= r * (1.0 - math.sqrt(max(0.0, 1.0 - e * e)))
            top.append((u, hh))
        side_l = [(-wv / 2 - 0.3 * r * math.sin(math.pi * t), top[-1][1] * (1.0 - t)) for t in (0.2, 0.45, 0.7)]
        side_l.append((-wv / 2 + 0.15 * r, 0.12 * r))
        bottom = [(-wv / 2 + r * 0.6, 0.0), (0.0, 0.0), (wv / 2 - r * 0.6, 0.0)]
        side_r = [(wv / 2 - 0.15 * r, 0.12 * r)]
        side_r += [(wv / 2 + 0.3 * r * math.sin(math.pi * t), top[0][1] * (1.0 - t)) for t in (0.7, 0.45, 0.2)]
        ring = top + side_l + bottom + side_r
        rows.append([o + U * uu + V * v + Nn * nn for uu, nn in ring])
    verts, faces, where = loft_rows(rows, closed=True, caps=True)
    mats_out = []
    for wh in where:
        if wh is None:
            mats_out.append(mat_side)
            continue
        i, j = wh
        v_mid = (vs[i][0] + vs[i + 1][0]) / 2 / d
        if j < top_n - 1:
            s = (us[::-1][j] + us[::-1][j + 1]) / 2       # the top runs from +0.5 to -0.5
            inside = any(a <= s <= b for a, b in panels) and panel_v[0] <= v_mid <= panel_v[1]
            mats_out.append(mat_panel if inside else mat_side)
        elif top_n + 3 <= j <= top_n + 6:
            mats_out.append(back_mat)
        else:
            mats_out.append(mat_side)
    add_closed(kit, verts, faces, mats_out)


def torus(kit, centre, eu, ev, R, section, mat, seg=48, sharp=False):
    """Closed sweep of a 2D section (radial, axial) around a circle of
    radius R in the plane (eu, ev) through centre."""
    c = np.asarray(centre, float)
    eu, ev = np.asarray(eu, float), np.asarray(ev, float)
    ax = np.cross(eu, ev)
    rows = []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        rad = eu * math.cos(a) + ev * math.sin(a)
        rows.append([c + rad * (R + sr) + ax * sa for sr, sa in section])
    rows.append(rows[0])
    verts, faces, _ = loft_rows(rows, closed=True, caps=False)
    # weld the seam
    n = len(section)
    m = seg * n
    faces = [[v if v < m else v - m for v in f] for f in faces]
    verts = verts[:m]
    add_closed(kit, verts, faces, mat, sharp)


def ellipse2d(a, b, k=16):
    t = np.linspace(0, 2 * np.pi, k, endpoint=False)
    return [(a * math.cos(s), b * math.sin(s)) for s in t]


def quad_uv(kit, corners, mat, uv=((0, 0), (1, 0), (1, 1), (0, 1)), facing=None, nu=1, nv=1):
    """Textured rectangle from corners (p00, p10, p11, p01) as an nu x nv grid."""
    p00, p10, p11, p01 = (np.asarray(p, float) for p in corners)
    verts, faces, uvs = [], [], []
    for j in range(nv + 1):
        for i in range(nu + 1):
            s, t = i / nu, j / nv
            verts.append((p00 * (1 - s) + p10 * s) * (1 - t) + (p01 * (1 - s) + p11 * s) * t)
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            f = [a, a + 1, a + nu + 2, a + nu + 1]
            faces.append(f)
            uvs.append([_uv_at(uv, (idx % (nu + 1)) / nu, (idx // (nu + 1)) / nv) for idx in f])
    if facing is None:
        facing = verts[0] + np.cross(p10 - p00, p01 - p00)
    add_open(kit, verts, faces, mat, facing, sharp=True, uvs=uvs)


def _uv_at(uv, s, t):
    (u00, v00), (u10, v10), (u11, v11), (u01, v01) = uv
    u = (u00 * (1 - s) + u10 * s) * (1 - t) + (u01 * (1 - s) + u11 * s) * t
    v = (v00 * (1 - s) + v10 * s) * (1 - t) + (v01 * (1 - s) + v11 * s) * t
    return (u, v)


def cylinder(kit, p0, p1, r, mat, seg=16, r1=None, caps=True):
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    ax = p1 - p0
    L = np.linalg.norm(ax)
    ax /= L
    o, u, v, n = mk.frame_from(p0, ax)
    r1 = r if r1 is None else r1
    rows = [[p0 + (u * math.cos(a) + v * math.sin(a)) * r for a in np.linspace(0, 2 * np.pi, seg, endpoint=False)],
            [p1 + (u * math.cos(a) + v * math.sin(a)) * r1 for a in np.linspace(0, 2 * np.pi, seg, endpoint=False)]]
    verts, faces, _ = loft_rows(rows, closed=True, caps=caps)
    add_closed(kit, verts, faces, mat)


# ---------------------------------------------------------------------------
# Lining: the shell offset inwards
# ---------------------------------------------------------------------------
class Lining:
    """Trim surfaces from a coarse copy of the body shell, and a lookup for
    placing parts on them."""

    def __init__(self, surf_ds=LINING_DS, log=print):
        self.surf = qb.Surface(surf_ds)
        # cut the colour changes into the trim mesh so they run straight
        belt = [(x, z) for x, z in BELT if -1.45 <= x <= 0.95]
        lines = {"trim_belt": ("side", belt),
                 "trim_split": ("side", [(0.86, CARD_SPLIT_Z), (BOOT_TRIM_X, CARD_SPLIT_Z)]),
                 "trim_boot": ("side", [(BOOT_TRIM_X, BOOT_Z - 0.04), (BOOT_TRIM_X, SHELF_Z), (-1.90, SHELF_Z)])}
        self.halves = []
        for side in (1, -1):
            self.halves.append(bb.Half(self.surf, side, lines))
        log("  lining shell ready")
        self.points = {1: [], -1: []}

    def thickness(self, P, N):
        x, z = P[:, 0], P[:, 2]
        dz = z - belt_z(x)
        door = np.interp(dz, [-0.75, -0.50, -0.30, -0.12, -0.04, 0.0], [0.10, 0.125, 0.14, 0.12, 0.085, 0.065])
        w_up = smoothstep(dz / 0.03)
        t = door * (1.0 - w_up) + 0.045 * w_up
        w_roof = smoothstep((N[:, 2] - 0.55) / 0.2)
        t = t * (1.0 - w_roof) + 0.035 * w_roof
        w_boot = smoothstep((-1.22 - x) / 0.10)
        t = t * (1.0 - w_boot) + np.minimum(t, 0.06) * w_boot
        w_tail = smoothstep((-N[:, 0] - 0.35) / 0.3)
        return t * (1.0 - w_tail) + 0.05 * w_tail

    def select(self, h):
        ids = [k for k, c in enumerate(h.cls) if c[0] == "shell"]
        ab = np.array([h.ab[h.faces[k]].mean(0) for k in ids])
        P = h.shell.base(ab[:, 0], ab[:, 1])
        N = h.shell.base_normal(ab[:, 0], ab[:, 1])
        x, z = P[:, 0], P[:, 2]
        keep = (x <= 1.13) & (x >= -2.08) & (N[:, 2] >= -0.55)
        keep &= np.where(x > -1.18, z >= 0.40, z >= BOOT_Z - 0.02)
        keep &= ~((x < -1.97) & (z < 0.80))           # no trim over the bumper's ledge (it would fold out)
        keep &= ~((x > 1.00) & (z < 1.00))           # engine-bay side of the dash
        keep &= ~((x > 1.00) & (N[:, 2] > 0.5))      # cowl: under the dash top
        keep &= np.abs(P[:, 1]) > 2e-4                # slivers where a glass outline meets the centre line
        return [k for k, m in zip(ids, keep) if m]

    @staticmethod
    def material(P, N):
        x, z = P[0], P[2]
        zb = float(belt_z(x))
        if N[2] > 0.6 and z > 1.25:
            return "headliner"
        if x < -1.85 and N[0] < -0.35:
            return "interior_dark"                    # tailgate trim under the glass
        if z > zb or (x < BOOT_TRIM_X and z > SHELF_Z):
            return "headliner"                        # pillar trims: same light grey
        if x < BOOT_TRIM_X:
            return "carpet"
        return "int_soft" if z > CARD_SPLIT_Z else "door_card"

    def build(self, kit):
        for h in self.halves:
            ids = self.select(h)
            faces = [h.faces[k] for k in ids]
            used = sorted({v for f in faces for v in f})
            remap = {v: i for i, v in enumerate(used)}
            lf = [[remap[v] for v in f] for f in faces]
            ab = h.ab[used]
            B = h.shell.base(ab[:, 0], ab[:, 1])
            D = bb.smooth_field(h.shell.base_normal(ab[:, 0], ab[:, 1]), *bb.region_edges(lf), 12)
            L = B - D * self.thickness(B, D)[:, None]
            mats = []
            for f in lf:
                mats.append(self.material(B[f].mean(0), D[f].mean(0)))
            # faces point into the cabin: reverse the shell's outward winding
            base = len(kit.verts)
            kit.verts.extend(Vector(tuple(p)) for p in L)
            for f, m in zip(lf, mats):
                kit.faces.append([base + i for i in f[::-1]])
                kit.mats.append(m)
                kit.sharp.append(False)
                kit.uvs.append(None)
            # returns to the window openings and the cut edges
            for u, v, nb in bb.boundary(h, ids):
                pu, pv = h.P[u], h.P[v]
                if abs(pu[1]) < 1e-3 and abs(pv[1]) < 1e-3:
                    continue                          # centre line: the other half continues
                lu, lv = L[remap[u]], L[remap[v]]
                glass = nb is not None and h.cls[nb][0] == "glass"
                m = "headliner" if glass and (pu[2] + pv[2]) / 2 > belt_z((pu[0] + pv[0]) / 2) + 0.02 \
                    else ("int_soft" if glass else "interior_dark")
                kit.add([pv, pu, lu, lv], [[0, 1, 2, 3]], m, True)
            # lookup of the trim surface (side walls only) for placing parts
            side = 1 if h.side > 0 else -1
            m = np.abs(D[:, 1]) > 0.55
            self.points[side] = (L[m], -D[m])

    def at(self, x, z, side):
        """Point on the door card / side trim at (x, z) and its normal (into
        the cabin)."""
        P, N = self.points[side]
        if not hasattr(self, "_kd"):
            self._kd = {}
        if side not in self._kd:
            kd = KDTree(len(P))
            for i, p in enumerate(P):
                kd.insert((p[0], 0.0, p[2]), i)
            kd.balance()
            self._kd[side] = kd
        found = self._kd[side].find_n((x, 0.0, z), 4)
        w = np.array([1.0 / max(d, 1e-4) for _, _, d in found])
        idx = [i for _, i, _ in found]
        p = (P[idx] * w[:, None]).sum(0) / w.sum()
        n = (N[idx] * w[:, None]).sum(0)
        n /= np.linalg.norm(n)
        p[0], p[2] = x, z
        return p, n


# ---------------------------------------------------------------------------
# Floor, boot, parcel shelf
# ---------------------------------------------------------------------------
def floor_z(x):
    return np.interp(x, [-1.20, -0.45, 0.70, 0.86, 0.98, 1.06], [0.35, 0.34, 0.33, 0.36, 0.48, 0.62])


def tunnel_h(x):
    return np.interp(x, [-1.20, -0.30, 0.20, 0.60, 1.06], [0.05, 0.06, 0.13, 0.15, 0.15])


def build_floor(kit):
    rows = []
    xs = [1.06, 1.02, 0.98, 0.92, 0.86, 0.78, 0.60, 0.35, 0.10, -0.15, -0.35, -0.55, -0.80, -1.00, -1.14]
    for x in xs:
        zf, th = float(floor_z(x)), float(tunnel_h(x))
        half = [(0.06, zf + th), (0.10, zf + th * 0.92), (0.135, zf + th * 0.2), (0.16, zf), (0.45, zf - 0.003),
                (0.70, zf), (0.765, zf + 0.04), (0.795, zf + 0.14)]
        sec = [(-y, z) for y, z in half[::-1]] + half
        rows.append([(x, y, z) for y, z in sec])
    verts, faces, _ = loft_rows(rows, closed=False, caps=False)
    add_open(kit, verts, faces, "carpet", (0.0, 0.0, 2.0))
    # firewall behind the dash
    fw = [(1.06, -0.79, 0.46), (1.06, 0.79, 0.46), (1.08, 0.79, 1.0), (1.08, -0.79, 1.0)]
    add_open(kit, fw, [[0, 1, 2, 3]], "interior_dark", (0.0, 0.0, 0.8))


def build_boot(kit):
    # floor board between the wheel houses, wider behind them
    outline = [(-1.10, -0.56), (-1.76, -0.56), (-1.80, -0.70), (-1.97, -0.66), (-2.03, -0.52),
               (-2.03, 0.52), (-1.97, 0.66), (-1.80, 0.70), (-1.76, 0.56), (-1.10, 0.56)]
    frame = (np.array([0.0, 0.0, BOOT_Z - 0.015]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
             np.array([0, 0, 1.0]))
    kit.prism(np.array(outline), 0.0, 0.015, frame, "carpet")
    # wheel-house covers
    for side in (1, -1):
        rows = []
        for x in np.linspace(-1.10, -1.78, 9):
            s = (x + 1.44) / 0.34
            top = BOOT_Z + 0.17 * math.sqrt(max(0.0, 1.0 - s * s)) + 0.015
            sec = [(0.55, BOOT_Z - 0.01), (0.555, top - 0.03), (0.58, top), (0.66, top + 0.005), (0.80, top + 0.01),
                   (0.80, BOOT_Z - 0.01)]
            rows.append([(x, side * y, z) for y, z in sec])
        verts, faces, _ = loft_rows(rows, closed=True, caps=True)
        add_closed(kit, verts, faces, "carpet")
    # parcel shelf (load cover) under the tailgate glass; its back edge follows
    # the tailgate trim, which curves forward into the narrow rear corners
    outline = [(-1.33, -0.66), (-1.86, -0.60), (-1.93, -0.50), (-1.965, -0.40), (-1.985, -0.28),
               (-1.985, 0.28), (-1.965, 0.40), (-1.93, 0.50), (-1.86, 0.60), (-1.33, 0.66)]
    frame = (np.array([0.0, 0.0, 1.095]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    kit.prism(np.array(outline), 0.0, 0.012, frame, "carpet")
    # the raised rear edge of the shelf
    kit.box((-1.93, 0.0, 1.13), (0.05, 0.80, 0.06), "carpet")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
# closed side profiles (x, z), same topology: windscreen base, top, brow,
# face, lower edge, underside, firewall
PASSENGER = [(1.070, 1.085), (0.970, 1.080), (0.840, 1.068), (0.710, 1.050), (0.655, 1.035), (0.625, 1.005),
             (0.615, 0.960), (0.628, 0.880), (0.665, 0.745), (0.700, 0.645), (0.760, 0.610), (0.880, 0.600),
             (0.980, 0.590), (1.050, 0.620), (1.070, 0.800), (1.075, 0.990)]
DASH_END = [(1.040, 1.060), (0.950, 1.058), (0.840, 1.050), (0.720, 1.036), (0.668, 1.022), (0.642, 0.996),
            (0.634, 0.955), (0.645, 0.880), (0.672, 0.760), (0.705, 0.668), (0.760, 0.630), (0.880, 0.620),
            (0.980, 0.610), (1.040, 0.630), (1.055, 0.800), (1.055, 0.980)]
CENTRE = [(1.070, 1.085), (0.970, 1.080), (0.840, 1.068), (0.710, 1.050), (0.660, 1.035), (0.632, 1.005),
          (0.625, 0.960), (0.628, 0.860), (0.635, 0.720), (0.645, 0.600), (0.690, 0.520), (0.800, 0.500),
          (0.950, 0.520), (1.050, 0.560), (1.070, 0.800), (1.075, 0.990)]
DRIVER = [(1.070, 1.085), (0.970, 1.080), (0.860, 1.070), (0.800, 1.058), (0.770, 1.040), (0.758, 1.030),
          (0.758, 0.915), (0.705, 0.890), (0.668, 0.830), (0.680, 0.700), (0.730, 0.600), (0.860, 0.580),
          (0.970, 0.570), (1.050, 0.620), (1.070, 0.800), (1.075, 0.990)]
DASH_KEYS = [(-0.79, DASH_END), (-0.66, DASH_END), (-0.60, DRIVER), (-0.19, DRIVER), (-0.13, CENTRE),
             (0.13, CENTRE), (0.20, PASSENGER), (0.66, PASSENGER), (0.79, DASH_END)]
N_PER = 3


def dash_profile(y):
    ys = [k[0] for k in DASH_KEYS]
    i = int(np.clip(np.searchsorted(ys, y) - 1, 0, len(ys) - 2))
    y0, p0 = DASH_KEYS[i]
    y1, p1 = DASH_KEYS[i + 1]
    t = float(smoothstep((y - y0) / (y1 - y0)))
    P = np.array(p0) * (1 - t) + np.array(p1) * t
    return smooth_closed_2d(P, N_PER)


def dash_face_x(y, z):
    """x of the dash face (rear-facing side) at (y, z)."""
    prof = dash_profile(y)
    face = prof[4 * N_PER:10 * N_PER]
    order = np.argsort(face[:, 1])
    return float(np.interp(z, face[order, 1], face[order, 0]))


def build_dashboard(kit):
    ys = sorted(set(list(np.round(np.arange(-0.79, 0.7901, 0.02), 4)) + [k[0] for k in DASH_KEYS]))
    rows = []
    for y in ys:
        prof = dash_profile(y)
        rows.append([(x, y, z) for x, z in prof])
    verts, faces, where = loft_rows(rows, closed=True, caps=True)
    mats = []
    for wh in where:
        if wh is None:
            mats.append("int_soft")
            continue
        i, j = wh
        seg = j // N_PER
        y = (ys[i] + ys[i + 1]) / 2
        if seg <= 5:
            mats.append("int_soft")                  # top and brow
        elif seg <= 8:
            mats.append("int_grey" if (y > 0.18 and seg >= 7) else "int_soft")
        else:
            mats.append("interior_dark")
    add_closed(kit, verts, faces, mats)

    # instrument hood over the dials
    hood = [(0.835, 1.058), (0.770, 1.092), (0.700, 1.088), (0.652, 1.066), (0.640, 1.048), (0.652, 1.038),
            (0.700, 1.043), (0.770, 1.036), (0.820, 1.040)]
    rows = []
    hy = np.linspace(-0.615, -0.135, 17)
    for y in hy:
        e = min(y - hy[0], hy[-1] - y)
        s = 0.35 + 0.65 * smoothstep(e / 0.05)
        c = np.array([0.75, 1.055])
        rows.append([(c[0] + (x - c[0]) * (0.7 + 0.3 * s), y, c[1] + (z - c[1]) * s) for x, z in
                     smooth_closed_2d(hood, 2)])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "int_soft")

    # dials: textured face in the recess, satin rings round the two dials
    y0, y1, z0, z1 = -0.240, -0.500, 0.922, 1.022
    xf = 0.754
    quad_uv(kit, [(xf, y0, z0), (xf, y1, z0), (xf, y1, z1), (xf, y0, z1)], "dials",
            uv=((0, 0), (1, 0), (1, 1), (0, 1)), facing=(0.0, -0.37, 0.95))
    for u in (62.0 / 320.0, 258.0 / 320.0):
        c = (xf - 0.003, y0 + (y1 - y0) * u, z1 - (z1 - z0) * (64.0 / 125.0))
        torus(kit, c, (0, 1, 0), (0, 0, 1), 0.0425, ellipse2d(0.0022, 0.003, 8), "int_silver", seg=40)

    # centre stack: piano-black block with the audio / climate texture
    sx, sz0, sz1 = 0.598, 0.585, 0.990
    frame = axes_frame((sx, 0.0, (sz0 + sz1) / 2), (0, -1.0, 0), (0, 0, 1.0))          # faces -X
    kit.prism(mk.rounded_rect2d(0.275, sz1 - sz0, 0.025, 5), -0.09, 0.0, frame, "black_gloss")
    xt = sx - 0.0015
    quad_uv(kit, [(xt, 0.125, 0.625), (xt, -0.125, 0.625), (xt, -0.125, 0.935), (xt, 0.125, 0.935)],
            "stack_panel", facing=(0.0, 0.0, 0.78))
    for (u_mm, v_mm, r, L) in ((44.0, 79.0, 0.0085, 0.013), (206.0, 79.0, 0.0085, 0.013),
                               (70.0, 167.0, 0.0105, 0.015), (180.0, 167.0, 0.0105, 0.015)):
        y = 0.125 - u_mm / 1000.0
        z = 0.935 - v_mm / 1000.0
        cylinder(kit, (xt, y, z), (xt - L, y, z), r, "interior_dark", seg=24, r1=r * 0.94)
        cylinder(kit, (xt - L + 0.0035, y, z), (xt - L - 0.0003, y, z), r * 0.97, "int_silver", seg=24)
    # centre vents with the hazard switch
    vent(kit, (sx - 0.002, 0.0, 0.962), (-1.0, 0.0, 0.0), 0.255, 0.046, divider=True)
    # side vents at the ends of the dash
    for side in (1, -1):
        y = 0.715 * side
        x = dash_face_x(y, 0.965) - 0.002
        vent(kit, (x, y, 0.965), (-1.0, -0.18 * side, 0.0), 0.115, 0.058)
    # driver's outer vent sits beside the binnacle as well, the passenger side
    # gets the gloss-black band with a satin line under it
    path, ups = [], []
    for y in np.linspace(0.155, 0.755, 16):
        z = 0.938 - 0.018 * (y - 0.155) / 0.6
        path.append(np.array([dash_face_x(y, z) - 0.003, y, z]))
        ups.append(np.array([-0.15, 0.0, 1.0]))
    kit.sweep([(-0.0025, -0.013), (0.0025, -0.013), (0.0025, 0.013), (-0.0025, 0.013)], path, ups, "black_gloss")
    kit.sweep([(-0.0015, -0.0195), (0.0015, -0.0195), (0.0015, -0.0155), (-0.0015, -0.0155)], path, ups,
              "int_silver")
    # glovebox catch
    y, z = 0.40, 0.815
    rounded_box(kit, (dash_face_x(y, z) - 0.004, y, z), (0.07, 0.018, 0.012), 0.006, "interior_dark",
                ex=(0, 1, 0), ey=(0, 0, 1))
    # demister slots on top of the dash
    for y0_, y1_ in ((-0.62, -0.10), (0.10, 0.62)):
        kit.box((1.00, (y0_ + y1_) / 2, 1.0795), (0.035, y1_ - y0_, 0.004), "black_plastic")


def vent(kit, centre, normal, w, h, divider=False):
    """Rounded vent: satin frame, dark louvres, optional hazard switch."""
    c = np.asarray(centre, float)
    fr = mk.frame_from(c, normal)
    outer = mk.rounded_rect2d(w, h, h * 0.35, 5)
    inner = mk.rounded_rect2d(w - 0.012, h - 0.012, h * 0.28, 5)
    o, u, v, n = fr
    kit.prism(outer, -0.004, 0.004, fr, "int_silver", cap1=False, cap0=False, sharp=False)
    # frame face: ring between outer and inner at the front
    ring_face(kit, outer, inner, 0.004, fr, "int_silver")
    recess_prism(kit, inner, 0.029, fr, "black_plastic", z_top=0.004)
    for k in range(3):
        z = -h * 0.28 + k * h * 0.28
        slat = (o + v * z - n * 0.008, u, v, n)
        kit.prism(mk.rounded_rect2d(w - 0.02, 0.004, 0.0015, 2), -0.006, 0.006, slat, "interior_dark")
    if divider:
        sw = (o - n * 0.001, u, v, n)
        kit.prism(mk.rounded_rect2d(0.034, h - 0.01, 0.004, 3), -0.02, 0.006, sw, "black_gloss")
        tri = [(0.0, 0.009), (-0.009, -0.006), (0.009, -0.006)]
        kit.prism(np.array(tri), 0.006, 0.0075, sw, "brake_light")


def ring_face(kit, outer, inner, z, frame, mat):
    """Flat ring between two outlines with the same point count."""
    o, u, v, n = (np.asarray(a, float) for a in frame)
    k = len(outer)
    verts = [o + u * p[0] + v * p[1] + n * z for p in outer] + [o + u * p[0] + v * p[1] + n * z for p in inner]
    faces = [[i, (i + 1) % k, k + (i + 1) % k, k + i] for i in range(k)]
    add_open(kit, verts, faces, mat, o + n * 1.0, sharp=True)


# ---------------------------------------------------------------------------
# Steering wheel and column (right-hand drive)
# ---------------------------------------------------------------------------
WHEEL_C = np.array([0.505, DRIVER_Y, 0.935])
WHEEL_TILT = math.radians(24.0)          # column angle below horizontal
WHEEL_R = 0.186


def wheel_axes():
    a = np.array([math.cos(WHEEL_TILT), 0.0, -math.sin(WHEEL_TILT)])     # into the dash
    up = np.array([math.sin(WHEEL_TILT), 0.0, math.cos(WHEEL_TILT)])     # up the wheel face
    right = np.array([0.0, -1.0, 0.0])                                   # driver's right
    return a, up, right


def build_steering_wheel(kit):
    a, up, right = wheel_axes()
    C = WHEEL_C
    # rim: leather, slightly oval section
    torus(kit, C, up, right, WHEEL_R, ellipse2d(0.0185, 0.0165, 16), "leather", seg=72)
    # hub / airbag cover
    face = C - a * 0.035
    outline = [(-0.088, 0.034), (-0.079, 0.062), (-0.040, 0.076), (0.040, 0.076), (0.079, 0.062), (0.088, 0.034),
               (0.068, -0.034), (0.034, -0.070), (-0.034, -0.070), (-0.068, -0.034)]
    outline = smooth_closed_2d(outline, 3)
    rows = []
    for depth, s in ((0.060, 0.80), (0.045, 0.97), (0.012, 1.0), (0.004, 0.96), (0.0, 0.88)):
        rows.append([face + a * depth + right * p[0] * s + up * p[1] * s for p in outline])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "int_soft")
    qp.build_logo(kit, mk.frame_from(face - a * 0.002 + up * 0.012, -a, up), 0.050, depth=0.006)
    # side spokes with satin wings and the switch pads
    for sgn in (1, -1):                                  # +1: driver's right spoke
        pts = []
        for t in np.linspace(0.0, 1.0, 5):
            r = 0.070 + (WHEEL_R - 0.070) * t
            pts.append(C + right * sgn * r - up * 0.012 - a * (0.020 - 0.012 * t))
        kit.sweep(ellipse2d(0.011, 0.022, 10), pts, [up] * len(pts), "interior_dark")
        wing = [C + right * sgn * (0.075 + 0.105 * t) - up * (0.036 - 0.012 * t) - a * (0.031 - 0.01 * t)
                for t in np.linspace(0.0, 1.0, 5)]
        kit.sweep([(-0.009, -0.004), (0.009, -0.004), (0.009, 0.004), (-0.009, 0.004)], wing, [-a] * len(wing),
                  "int_silver")
        # switch pad: left spoke (driver's left, sgn=-1) audio, right spoke cruise
        pc = C + right * sgn * 0.108 + up * 0.002 - a * 0.030
        hw = 0.030
        u0, u1 = (0.5, 1.0) if sgn > 0 else (0.0, 0.5)
        kit.prism(mk.rounded_rect2d(0.068, 0.068, 0.012, 4), -0.006, 0.0,
                  axes_frame(pc + a * 0.0005, -right, up), "interior_dark")
        p00 = pc - right * hw - up * hw
        p10 = pc + right * hw - up * hw
        p11 = pc + right * hw + up * hw
        p01 = pc - right * hw + up * hw
        quad_uv(kit, [p00, p10, p11, p01], "switches", uv=((u0, 0), (u1, 0), (u1, 1), (u0, 1)),
                facing=pc - a * 1.0)
        rim = [pc + a * 0.001 + (right * math.cos(t) + up * math.sin(t)) * hw * 1.2
               for t in np.linspace(0, 2 * np.pi, 33)]
        kit.sweep(ellipse2d(0.0025, 0.0035, 6), rim, [-a] * len(rim), "int_silver", caps=True)
    # lower V spokes (satin)
    for sgn in (1, -1):
        p0 = C + right * sgn * 0.030 - up * 0.058 - a * 0.020
        ang = math.radians(146.0)
        p1 = C + (up * math.cos(ang) + right * sgn * math.sin(ang)) * (WHEEL_R - 0.004) - a * 0.004
        path = [p0 + (p1 - p0) * t for t in np.linspace(0, 1, 4)]
        kit.sweep(ellipse2d(0.012, 0.007, 10), path, [-a] * len(path), "int_silver")
    # column shroud and stalks
    rows = []
    for t, w, hh in ((0.05, 0.050, 0.045), (0.12, 0.060, 0.055), (0.26, 0.070, 0.068)):
        c = C + a * t - up * 0.012
        rows.append([c + right * x + up * z for x, z in mk.rounded_rect2d(w * 2, hh * 2, 0.02, 3)])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "interior_dark")
    for sgn in (1, -1):
        p0 = C + a * 0.095 + right * sgn * 0.058 + up * 0.012
        p1 = p0 + right * sgn * 0.13 - up * 0.025 - a * 0.02
        cylinder(kit, p0, p1, 0.0075, "interior_dark", seg=10, r1=0.0065)


# ---------------------------------------------------------------------------
# Centre console
# ---------------------------------------------------------------------------
def build_console(kit):
    rows = []
    stations = [(0.640, 0.52, 0.125), (0.600, 0.53, 0.125), (0.45, 0.525, 0.120), (0.20, 0.530, 0.115),
                (0.00, 0.545, 0.112), (-0.10, 0.550, 0.110), (-0.36, 0.550, 0.108), (-0.40, 0.520, 0.100)]
    for x, top, hw in stations:
        z0 = float(floor_z(x)) + float(tunnel_h(x)) * 0.5
        sec = [(hw, z0), (hw, top - 0.02), (hw - 0.012, top - 0.003), (hw - 0.03, top),
               (-hw + 0.03, top), (-hw + 0.012, top - 0.003), (-hw, top - 0.02), (-hw, z0)]
        rows.append([(x, y, z) for y, z in sec])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "interior_dark")
    # piano-black top plate round the gear lever and switch
    frame = (np.array([0.34, 0.0, 0.527]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    kit.prism(mk.rounded_rect2d(0.30, 0.19, 0.04, 4), 0.0, 0.004, frame, "black_gloss")
    # gear lever: satin surround, leather gaiter, gloss knob with a satin collar
    gx, gy, gz = 0.37, 0.0, 0.531
    fr = (np.array([gx, gy, gz]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    ring_face(kit, mk.rounded_rect2d(0.125, 0.105, 0.035, 5), mk.rounded_rect2d(0.105, 0.085, 0.028, 5),
              0.0045, fr, "int_silver")
    kit.prism(mk.rounded_rect2d(0.125, 0.105, 0.035, 5), 0.0, 0.0045, fr, "int_silver", cap1=False, cap0=False,
              sharp=False)
    rows = []
    for z, rx, ry in ((0.532, 0.052, 0.042), (0.555, 0.047, 0.040), (0.585, 0.034, 0.030), (0.62, 0.020, 0.019),
                      (0.655, 0.012, 0.012)):
        rows.append([(gx + rx * math.cos(t) - (z - gz) * 0.10, gy + ry * math.sin(t), z)
                     for t in np.linspace(0, 2 * np.pi, 20, endpoint=False)])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "leather")
    kc = np.array([gx - 0.026, gy, 0.700])
    rows = []
    for dz, r in ((-0.040, 0.010), (-0.030, 0.016), (-0.015, 0.021), (0.0, 0.0235), (0.015, 0.023),
                  (0.028, 0.019), (0.036, 0.011), (0.039, 0.003)):
        rows.append([kc + np.array([r * 1.05 * math.cos(t), r * math.sin(t), dz])
                     for t in np.linspace(0, 2 * np.pi, 24, endpoint=False)])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "black_gloss")
    cylinder(kit, kc + np.array([0, 0, -0.046]), kc + np.array([0, 0, -0.036]), 0.0165, "int_silver", seg=24)
    # e-parking brake switch (driver's side of the lever)
    frame = (np.array([0.300, -0.075, 0.531]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
    kit.prism(mk.rounded_rect2d(0.042, 0.030, 0.006, 3), 0.0, 0.004, frame, "int_silver")
    kit.prism(mk.rounded_rect2d(0.032, 0.020, 0.005, 3), 0.004, 0.012, frame, "black_gloss")
    # cup holders
    for cx in (0.165, 0.075):
        fr = (np.array([cx, 0.0, 0.531]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]))
        circ = mk.circle2d(0.037, 28)
        ring_face(kit, mk.circle2d(0.041, 28), circ, 0.002, fr, "int_silver")
        recess_prism(kit, circ, 0.07, fr, "interior_dark", z_top=0.002)
    # armrest
    rows = []
    for x, s in ((0.02, 0.85), (0.012, 0.97), (0.0, 1.0), (-0.30, 1.0), (-0.33, 0.95), (-0.345, 0.8)):
        sec = [(0.100 * s, 0.545), (0.100 * s, 0.63), (0.085 * s, 0.655 * (0.9 + 0.1 * s)),
               (-0.085 * s, 0.655 * (0.9 + 0.1 * s)), (-0.100 * s, 0.63), (-0.100 * s, 0.545)]
        rows.append([(x, y, z) for y, z in smooth_closed_2d(sec, 3)])
    verts, faces, _ = loft_rows(rows, closed=True, caps=True)
    add_closed(kit, verts, faces, "leather")
    # stack foot: where the console meets the dash
    kit.prism(mk.rounded_rect2d(0.25, 0.08, 0.02, 3), -0.06, 0.0, axes_frame((0.60, 0.0, 0.54), (0, -1.0, 0),
                                                                            (0, 0, 1.0)), "interior_dark")


# ---------------------------------------------------------------------------
# Seats
# ---------------------------------------------------------------------------
SEAT_MATS = ("seat_centre", "seat")


def frame(o, U, V, N):
    return tuple(np.asarray(a, float) for a in (o, U, V, N))


def front_seat(kit, yc):
    cushion_tilt = math.radians(12.0)
    back_tilt = math.radians(21.0)
    x_rear, z_base = -0.215, 0.445
    V = np.array([math.cos(cushion_tilt), 0.0, math.sin(cushion_tilt)])
    Nn = np.array([-math.sin(cushion_tilt), 0.0, math.cos(cushion_tilt)])
    U = np.array([0.0, 1.0, 0.0])
    pillow(kit, frame((x_rear, yc, z_base), U, V, Nn), 0.51, 0.50, 0.105, SEAT_MATS, bolster=0.04,
           panels=[(-0.20, 0.20)], panel_v=(0.10, 0.88))
    # backrest
    Vb = np.array([-math.sin(back_tilt), 0.0, math.cos(back_tilt)])
    Nb = np.array([math.cos(back_tilt), 0.0, math.sin(back_tilt)])
    ob = np.array([x_rear - 0.035, yc, z_base + 0.07])
    pillow(kit, frame(ob, U, Vb, Nb), 0.53, 0.63, 0.10, SEAT_MATS, bolster=0.065, bolster_w=0.12, taper=0.12,
           panels=[(-0.19, 0.19)], panel_v=(0.10, 0.82), round_r=0.03)
    # headrest on two posts
    top = ob + Vb * 0.63 + Nb * 0.045
    for dy in (-0.075, 0.075):
        cylinder(kit, top + U * dy - Vb * 0.03, top + U * dy + Vb * 0.075, 0.0065, "int_silver", seg=10)
    ho = top + Vb * 0.055 - Nb * 0.05
    pillow(kit, frame(ho, U, Vb, Nb), 0.27, 0.20, 0.10, SEAT_MATS, bolster=0.0, crown=0.01, round_r=0.035)
    # base with side covers and runners
    kit.box((x_rear + 0.25, yc, (FLOOR_Z + z_base) / 2 + 0.01), (0.44, 0.40, z_base - FLOOR_Z), "interior_dark")
    for sgn in (1, -1):
        rounded_box(kit, (x_rear + 0.22, yc + sgn * 0.262, z_base + 0.02), (0.40, 0.11, 0.022), 0.03,
                    "interior_dark", ex=(1, 0, 0), ey=(0, 0, 1))
        kit.box((x_rear + 0.25, yc + sgn * 0.19, FLOOR_Z + 0.012), (0.62, 0.035, 0.024), "black_plastic")


def rear_bench(kit):
    cushion_tilt = math.radians(10.0)
    back_tilt = math.radians(24.0)
    x_rear, z_base = -1.075, 0.470
    U = np.array([0.0, 1.0, 0.0])
    V = np.array([math.cos(cushion_tilt), 0.0, math.sin(cushion_tilt)])
    Nn = np.array([-math.sin(cushion_tilt), 0.0, math.cos(cushion_tilt)])
    panels = [(-0.44, -0.16), (-0.10, 0.10), (0.16, 0.44)]
    pillow(kit, frame((x_rear, 0.0, z_base), U, V, Nn), 1.30, 0.50, 0.10, SEAT_MATS, bolster=0.012,
           bolster_w=0.08, panels=panels, panel_v=(0.10, 0.90), n_u=40)
    Vb = np.array([-math.sin(back_tilt), 0.0, math.cos(back_tilt)])
    Nb = np.array([math.cos(back_tilt), 0.0, math.sin(back_tilt)])
    ob = np.array([x_rear - 0.03, 0.0, z_base + 0.06])
    pillow(kit, frame(ob, U, Vb, Nb), 1.30, 0.58, 0.10, SEAT_MATS, bolster=0.02, bolster_w=0.10, taper=0.05,
           panels=panels, panel_v=(0.10, 0.85), n_u=40, back_mat="carpet")
    top = ob + Vb * 0.58 + Nb * 0.05
    for yc, w, hgt in ((-0.44, 0.25, 0.17), (0.0, 0.22, 0.14), (0.44, 0.25, 0.17)):
        for dy in (-0.065, 0.065):
            cylinder(kit, top + U * (yc + dy) - Vb * 0.03, top + U * (yc + dy) + Vb * 0.05, 0.006, "int_silver",
                     seg=10)
        ho = top + U * yc + Vb * 0.03 - Nb * 0.045
        pillow(kit, frame(ho, U, Vb, Nb), w, hgt, 0.09, SEAT_MATS, bolster=0.0, crown=0.01, round_r=0.03)
    # cushion base down to the floor
    kit.box((x_rear + 0.24, 0.0, (FLOOR_Z + z_base) / 2 + 0.01), (0.46, 1.24, z_base - FLOOR_Z), "carpet")


def seat_belts(kit, lining):
    """Front belts hanging down the B-pillars, rear outer belts from the
    C-pillars to the bench."""
    for side in (1, -1):
        p_top, n_top = lining.at(-0.265, 1.30, side)
        p_bot, n_bot = lining.at(-0.300, 0.47, side)
        path = [p_top + n_top * 0.012, (p_top + p_bot) / 2 + (n_top + n_bot) * 0.012, p_bot + n_bot * 0.02]
        kit.sweep([(-0.024, -0.0015), (0.024, -0.0015), (0.024, 0.0015), (-0.024, 0.0015)], path,
                  [n_top, (n_top + n_bot) / 2, n_bot], "belt")
        rounded_box(kit, p_top + n_top * 0.012, (0.05, 0.07, 0.012), 0.012, "pillar_trim",
                    ex=(1, 0, 0), ey=(0, 0, 1))
        # rear outer belt
        p0, n0 = lining.at(-1.30, 1.16, side)
        p0 = p0 + n0 * 0.03
        p1 = np.array([-1.06, side * 0.60, 0.62])
        path = [p0 + (p1 - p0) * t for t in np.linspace(0, 1, 4)]
        kit.sweep([(-0.022, -0.0015), (0.022, -0.0015), (0.022, 0.0015), (-0.022, 0.0015)], path,
                  [np.array([1.0, 0.0, 0.3])] * 4, "belt")


# ---------------------------------------------------------------------------
# Door cards, roof and footwell details
# ---------------------------------------------------------------------------
def door_details(kit, lining):
    Z = np.array([0.0, 0.0, 1.0])
    for side in (1, -1):
        for (xf, xr), front in ((FRONT_DOOR, True), (REAR_DOOR, False)):
            # armrest ledge, rising towards the front
            x0, x1 = xf - (0.20 if front else 0.12), xr + (0.10 if front else 0.35)
            path = []
            for x in np.linspace(x0, x1, 8):
                z = 0.70 + (0.03 if front else 0.02) * smoothstep((x - x1) / (x0 - x1))
                p, n = lining.at(x, z, side)
                path.append(p + n * 0.026)
            kit.sweep(rot90(mk.rounded_rect2d(0.060, 0.050, 0.014, 3)), path, [Z] * len(path), "int_soft")
            # door pull / handle: chrome lever on a gloss-black bezel
            xh = xf - (0.19 if front else 0.13)
            p, n = lining.at(xh, 0.935, side)
            fr = mk.frame_from(p + n * 0.004, n, (0, 0, 1))
            kit.prism(mk.rounded_rect2d(0.16, 0.052, 0.022, 5), -0.006, 0.0, fr, "black_gloss")
            o, u, v, nn = fr
            lever = [o + u * (0.055 - 0.11 * t) + v * (0.004 * math.sin(math.pi * t)) + nn * (0.004 + 0.012 * t)
                     for t in np.linspace(0, 1, 6)]
            kit.sweep(ellipse2d(0.006, 0.004, 8), lever, [v] * len(lever), "chrome")
            # speaker grille low on the card
            p, n = lining.at(xf - (0.17 if front else 0.18), 0.53, side)
            fs = mk.frame_from(p + n * 0.002, n, (0, 0, 1))
            kit.prism(mk.circle2d(0.080, 32), -0.004, 0.006, fs, "interior_dark", cap1=False, cap0=False,
                      sharp=False)
            ring_face(kit, mk.circle2d(0.080, 32), mk.circle2d(0.070, 32), 0.006, fs, "interior_dark")
            kit.prism(mk.circle2d(0.070, 32), -0.004, 0.003, fs, "black_plastic")
            # window switches on the armrest (four on the driver's door)
            if front:
                p, n = lining.at(xf - 0.36, 0.73, side)
                n_sw = 4 if side < 0 else 1
                c = p + n * 0.030 + Z * 0.030
                fsw = axes_frame(c, (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
                kit.prism(mk.rounded_rect2d(0.03 * n_sw + 0.02, 0.045, 0.008, 3), 0.0, 0.005, fsw, "black_gloss")
                for k in range(n_sw):
                    kit.box((c[0] - 0.015 * (n_sw - 1) + 0.03 * k, c[1], c[2] + 0.009), (0.018, 0.026, 0.009),
                            "interior_dark")
            # door pocket along the bottom of the card
            p, n = lining.at((xf + xr) / 2 + (0.02 if front else 0.12), 0.46, side)
            L = abs(xf - xr) * (0.55 if front else 0.35)
            fp = mk.frame_from(p + n * 0.02, n, (0, 0, 1))
            kit.prism(mk.rounded_rect2d(L, 0.10, 0.02, 3), -0.02, 0.035, fp, "door_card")


def roof_details(kit):
    # interior mirror with the rain-sensor cover
    kit.box((0.235, 0.0, 1.465), (0.09, 0.10, 0.03), "interior_dark")
    cylinder(kit, (0.235, 0.0, 1.455), (0.255, 0.0, 1.415), 0.006, "interior_dark", seg=10)
    fr = axes_frame((0.255, 0.0, 1.395), (0, -1.0, 0), (0, 0, 1.0))          # glass faces -X
    kit.prism(mk.rounded_rect2d(0.25, 0.068, 0.028, 5), -0.03, 0.0, fr, "interior_dark", sharp=False)
    kit.prism(mk.rounded_rect2d(0.24, 0.060, 0.025, 5), 0.0, 0.0015, fr, "mirror_glass")
    # map-light console
    rounded_box(kit, (0.06, 0.0, 1.508), (0.22, 0.12, 0.03), 0.03, "pillar_trim")
    for dy in (-0.045, 0.045):
        kit.box((0.035, dy, 1.492), (0.05, 0.035, 0.003), "lens_clear")
    # sun visors folded up under the headliner
    for side in (1, -1):
        c = np.array([0.215, side * 0.36, 1.492])
        pitch = math.radians(-17.0)
        ex = np.array([math.cos(pitch), 0.0, math.sin(pitch)])
        rounded_box(kit, c, (0.16, 0.34, 0.024), 0.03, "headliner", ex=ex, ey=(0, 1, 0))
    # grab handles over the passenger door and the rear doors
    for x, side in ((0.20, 1), (-0.70, 1), (-0.70, -1)):
        p = np.array([x, side * 0.60, 1.43])
        path = [p + np.array([dx, 0.0, -0.02 * math.sin(math.pi * (dx + 0.12) / 0.24)]) for dx in
                np.linspace(-0.12, 0.12, 7)]
        kit.sweep(ellipse2d(0.007, 0.011, 8), path, [np.array([0, 0, 1.0])] * len(path), "pillar_trim")


def pedals(kit):
    """Clutch, brake and throttle for the right-hand-drive driver."""
    for y, w, h, z, hinge in ((-0.215, 0.065, 0.075, 0.46, False), (-0.33, 0.075, 0.075, 0.45, False),
                              (-0.465, 0.050, 0.15, 0.40, True)):
        x = 0.83 if not hinge else 0.87
        n = np.array([-math.cos(math.radians(35)), 0.0, math.sin(math.radians(35))])
        fr = mk.frame_from(np.array([x, y, z]), n, (1, 0, 0.6))
        kit.prism(mk.rounded_rect2d(w, h, 0.012, 3), -0.012, 0.0, fr, "tyre")
        if not hinge:
            cylinder(kit, (x + 0.01, y, z + 0.03), (0.93, y, 0.72), 0.008, "wheel_inner", seg=8)


# ---------------------------------------------------------------------------
def build_interior(kit, log=print, lining_ds=LINING_DS):
    lining = Lining(lining_ds, log=log)
    lining.build(kit)
    log("  lining: %d faces" % len(kit.faces))
    build_floor(kit)
    build_boot(kit)
    build_dashboard(kit)
    build_steering_wheel(kit)
    build_console(kit)
    front_seat(kit, DRIVER_Y)
    front_seat(kit, -DRIVER_Y)
    rear_bench(kit)
    seat_belts(kit, lining)
    door_details(kit, lining)
    roof_details(kit)
    pedals(kit)
    log("  interior: %d faces" % len(kit.faces))
    return lining
