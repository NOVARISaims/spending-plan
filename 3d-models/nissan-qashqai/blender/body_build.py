"""Body shell of the Qashqai with every feature cut in, plus the parts that
are made from shell regions (glass, lamp lenses and housings, arch
mouldings, grille panels).

For each side the feature outlines from qashqai_features are mapped onto
the loft, overlaid on the grid (body_mesh.overlay), and every face is
classified by the regions that contain it.  Faces keep the exact loft
position and normal, so a lens or a pane of glass made from a region lines
up perfectly with the opening it fills.
"""
import math

import bpy  # noqa: F401  (must precede bmesh / mathutils with the PyPI bpy module)
import bmesh
import numpy as np
from mathutils import Vector

import body_mesh as bm
import qashqai_body as qb
import qashqai_features as F

VIEW_STEP = 0.008           # outline sampling (m) before mapping


# ---------------------------------------------------------------------------
# View-space polygon helpers
# ---------------------------------------------------------------------------
def inset(poly, d):
    """Offset a closed polygon towards its inside by d (outwards if d < 0)."""
    return bm.offset_polyline(poly, d * np.sign(bm.polygon_area(poly)))


def clip_half(poly, p0, p1, keep):
    """Part of poly on the same side of the line p0-p1 as the point keep."""
    p0, p1, keep = (np.asarray(v, float) for v in (p0, p1, keep))
    t = p1 - p0
    n = np.array([-t[1], t[0]])
    s = np.sign((keep - p0) @ n)
    out = []
    P = [np.asarray(p, float) for p in poly]
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        va, vb = ((a - p0) @ n) * s, ((b - p0) @ n) * s
        if va >= 0:
            out.append(a)
        if va * vb < 0:
            out.append(a + (b - a) * (va / (va - vb)))
    return np.array(out)


def band(line, w):
    """Closed polygon of width w around an open polyline."""
    line = np.asarray(line, float)
    left = bm.offset_polyline(line, w / 2.0, closed=False)
    right = bm.offset_polyline(line, -w / 2.0, closed=False)
    return np.vstack([left, right[::-1]])


def extend(line, d):
    """Lengthen an open polyline by d at both ends (so grooves run into the
    neighbouring edges cleanly)."""
    line = np.asarray(line, float)
    t0 = line[0] - line[1]
    t1 = line[-1] - line[-2]
    return np.vstack([line[0] + t0 / np.linalg.norm(t0) * d, line[1:-1],
                      line[-1] + t1 / np.linalg.norm(t1) * d])


# ---------------------------------------------------------------------------
# Displacement fields beyond polylines
# ---------------------------------------------------------------------------
class Dish:
    """Elliptical recess (door-handle pocket)."""

    def __init__(self, view, c, r, depth, side=0.0):
        self.view, self.c, self.r, self.depth, self.side = view, np.asarray(c, float), np.asarray(r, float), depth, side

    def __call__(self, P, N, sides):
        d, axes = bm.VIEWS[self.view]
        p2 = P[:, list(axes)]
        q = ((p2 - self.c) / self.r)
        rr = (q ** 2).sum(1)
        out = -self.depth * np.clip(1.0 - rr, 0.0, 1.0) ** 0.6
        facing = np.abs(N[:, 1]) if self.view == "side" else -(N @ d)
        out = np.where(facing > 0.5, out, 0.0)
        if self.side:
            out = np.where(sides == self.side, out, 0.0)
        return out


class Recess:
    """Flat-bottomed recess inside a polygon with a sloped wall of width w."""

    def __init__(self, view, poly, depth, w):
        self.view, self.poly, self.depth, self.w = view, np.asarray(poly, float), depth, w

    def __call__(self, P, N, sides):
        d, axes = bm.VIEWS[self.view]
        p2 = P[:, list(axes)].copy()
        if self.view in ("front", "rear"):
            p2[:, 0] = np.abs(p2[:, 0])
        closed = np.vstack([self.poly, self.poly[:1]])
        dist, _ = bm.polyline_distance(p2, closed)
        inside = bm.points_in_polygon(p2, self.poly)
        out = np.where(inside, -self.depth * np.clip(dist / self.w, 0.0, 1.0), 0.0)
        return np.where(-(N @ d) > 0.5, out, 0.0)


SWAGE_RAMP = 0.018


def swage_profile(s, x):
    """Lower-door swage flowing into the rear haunch.  s > 0 is below the
    line (inside the arc over the rear wheel).  The doors step in below the
    crease; over the rear wheel the haunch stands proud."""
    k = np.clip((x + 0.86) / -0.14, 0.0, 1.0)            # 0 on the doors, 1 on the haunch
    k = k * k * (3 - 2 * k)
    door = -0.0090 * np.clip(s / SWAGE_RAMP, 0.0, 1.0) * np.clip(1.0 - (s - SWAGE_RAMP) / 0.12, 0.0, 1.0)
    haunch = 0.0115 * np.clip(s / SWAGE_RAMP, 0.0, 1.0)
    out = (1.0 - k) * door + k * haunch
    return np.where(s > 0.0, out, 0.0)


class Swage:
    def __init__(self, line):
        self.line = np.asarray(line, float)

    def __call__(self, P, N, sides):
        p2 = P[:, [0, 2]]
        dist, sgn = bm.polyline_distance(p2, self.line)
        s = dist * sgn
        out = swage_profile(s, P[:, 0])
        # fade at the front end of the line and keep off the arch mouldings
        out *= np.clip((0.80 - P[:, 0]) / 0.12 + 1.0, 0.0, 1.0)
        out *= np.clip((P[:, 2] - 0.42) / 0.05, 0.0, 1.0)
        return np.where(np.abs(N[:, 1]) > 0.5, out, 0.0)


class Crease:
    """Crisp character line on the front of the car: below the line the
    surface steps back and blends out again over `w` (a trough with a sharp
    upper edge).  The line is in front-view coordinates (|Y|, Z).  The step
    fades in and out over `fade` metres at the ends of the line and keeps
    `margin` clear of the `keep_off` outline (the headlamp)."""

    def __init__(self, line, depth, w, fade, keep_off=None, margin=0.015):
        self.line = np.asarray(line, float)
        seg = np.linalg.norm(np.diff(self.line, axis=0), axis=1)
        self.cum = np.concatenate([[0.0], np.cumsum(seg)])
        self.depth, self.w, self.fade = depth, w, fade
        self.keep_off = None if keep_off is None else np.asarray(keep_off, float)
        self.margin = margin
        self.lo = self.line.min(0) - w - 0.02
        self.hi = self.line.max(0) + w + 0.02

    def __call__(self, P, N, sides):
        out = np.zeros(len(P))
        p2 = np.column_stack([np.abs(P[:, 1]), P[:, 2]])
        m = np.all((p2 >= self.lo) & (p2 <= self.hi), axis=1) & (N[:, 0] > 0.2)
        if not m.any():
            return out
        q = p2[m]
        best = np.full(len(q), np.inf)
        sgn = np.ones(len(q))
        arc = np.zeros(len(q))
        for i, (a, b) in enumerate(zip(self.line[:-1], self.line[1:])):
            ab = b - a
            L2 = max(ab @ ab, 1e-18)
            t = np.clip(((q - a) @ ab) / L2, 0.0, 1.0)
            d = np.linalg.norm(q - (a + t[:, None] * ab), axis=1)
            cross = ab[0] * (q[:, 1] - a[1]) - ab[1] * (q[:, 0] - a[0])
            upd = d < best
            best[upd], sgn[upd] = d[upd], np.sign(cross[upd])
            arc[upd] = self.cum[i] + t[upd] * math.sqrt(L2)
        s = best * sgn                                   # > 0 above the line
        t = np.clip(-s / self.w, 0.0, 1.0)
        g = np.where(s < 0.0, 6.75 * t * (1.0 - t) ** 2, 0.0)
        L = self.cum[-1]
        g *= bm.smoothstep(arc / self.fade) * bm.smoothstep((L - arc) / self.fade)
        g *= bm.smoothstep((N[m, 0] - 0.3) / 0.25)
        if self.keep_off is not None:
            closed = np.vstack([self.keep_off, self.keep_off[:1]])
            dist, _ = bm.polyline_distance(q, closed)
            inside = bm.points_in_polygon(q, self.keep_off)
            g *= np.where(inside, 0.0, bm.smoothstep(dist / self.margin))
        out[m] = -self.depth * g
        return out


def front_view(surf, ab, side):
    """Front-view coordinates (|Y|, Z) of surface points given as (a, b)."""
    P = surf.eval(ab[:, 0], ab[:, 1], side)
    return np.column_stack([np.abs(P[:, 1]), P[:, 2]])


# ---------------------------------------------------------------------------
# Feature spec for one side
# ---------------------------------------------------------------------------
class Spec:
    def __init__(self, surf, side):
        self.surf, self.side = surf, side
        self.mp = bm.Mapper(surf, side)
        self.regions, self.lines, self.fields = {}, {}, []

    # mapping helpers -----------------------------------------------------
    def view_poly(self, view, poly, closed=True, step=VIEW_STEP):
        p = bm.densify(poly, step, closed=closed)
        return self.mp.map([(view, float(a), float(b)) for a, b in p])

    def region(self, name, view, poly):
        self.regions[name] = self.view_poly(view, poly)

    def groove(self, name, view, line, w=F.GAP_W, depth=F.GAP_D, side=0.0):
        line = np.asarray(line, float)
        self.regions["gb_" + name] = self.view_poly(view, band(line, w))
        self.lines["gl_" + name] = self.view_poly(view, line, closed=False)
        self.fields.append(bm.Displacement(view, line, bm.v_groove(w, depth), side=side))

    def closed_groove(self, name, view, poly, w=F.GAP_W, depth=F.GAP_D, side=0.0):
        poly = np.asarray(poly, float)
        self.regions["gbo_" + name] = self.view_poly(view, inset(poly, -w / 2))
        self.regions["gbi_" + name] = self.view_poly(view, inset(poly, w / 2))
        closed = np.vstack([poly, poly[:1]])
        self.lines["gl_" + name] = self.view_poly(view, closed, closed=False)
        self.fields.append(bm.Displacement(view, closed, bm.v_groove(w, depth), side=side))

    def mixed(self, name, pts, n_per=6):
        """Closed outline from control points in several views, smoothed in
        parameter space."""
        ab = self.mp.map(pts)
        self.regions[name] = bm.smooth_closed(ab, n_per)

    def implicit(self, name, fn, sub=3):
        """Region {P : fn(P) < 0} contoured in parameter space."""
        s = self.surf
        A = np.linspace(0.0, s.na, s.na * sub + 1)
        B = np.linspace(0.0, s.nb, s.nb * sub + 1)
        AA, BB = np.meshgrid(A, B, indexing="ij")
        P = s.eval(AA.ravel(), BB.ravel(), self.side)
        Fv = fn(P).reshape(AA.shape)
        loops = bm.contour_polygons(Fv, A, B)
        for k, loop in enumerate(loops):
            self.regions["%s_%d" % (name, k)] = bm.simplify(loop, 0.02)

    def a_of(self, x):
        return float(np.interp(x, self.surf.st, np.arange(self.surf.na + 1)))


def build_spec(surf, side):
    S = Spec(surf, side)
    ring = surf.ring
    b_floor_edge = float(ring.cum[1])

    # --- side glass ----------------------------------------------------------
    dlo = bm.smooth_closed(np.array(F.DLO), 4)
    dlo_in = inset(dlo, F.CHROME_W)
    glass = inset(dlo, F.CHROME_W + F.SEAL_W)
    S.region("dlo", "side", dlo)
    S.region("dlo_in", "side", dlo_in)
    g_f = clip_half(glass, *F.SAIL, keep=(0.3, 1.25))
    g_f = clip_half(g_f, *F.B_FRONT, keep=(0.0, 1.2))
    g_r = clip_half(glass, *F.B_REAR, keep=(-0.6, 1.2))
    g_r = clip_half(g_r, *F.C_FRONT, keep=(-0.6, 1.2))
    g_q = clip_half(glass, *F.C_REAR, keep=(-1.2, 1.25))
    S.region("glass_f", "side", g_f)
    S.region("glass_r", "side", g_r)
    S.region("glass_q", "side", g_q)

    # --- windscreen, rear glass, spoiler -----------------------------------
    S.region("ws", "top", np.array(F.WINDSCREEN))
    S.region("ws_clear", "top", np.array(F.WS_CLEAR))
    S.region("rg", "rear", np.array(F.REAR_GLASS))
    S.region("rg_clear", "rear", np.array(F.RG_CLEAR))
    S.region("spoiler_band", "rear", np.array(F.SPOILER_BAND))

    # --- wheel arches ----------------------------------------------------------
    for which in ("front", "rear"):
        arch = bm.densify(F.arch_polyline(which), VIEW_STEP, closed=False)
        ab = S.mp.map([("side", x, z) for x, z in arch])
        b_in = b_floor_edge * F.LINER_Y / (0.845 - 0.14)
        a0, a1 = ab[0, 0], ab[-1, 0]
        under = np.array([[a1, b_in], [a0, b_in]])
        S.regions["arch_" + which] = np.vstack([ab, under])
        # moulding band outside the opening
        w = F.ARCH_TRIM_W[which]
        xc = qb.X_FA if which == "front" else qb.X_RA
        off = bm.offset_polyline(arch, w, closed=False)
        if np.hypot(off[len(off) // 2, 0] - xc, off[len(off) // 2, 1] - F.WHEEL_Z) < \
                np.hypot(arch[len(arch) // 2, 0] - xc, arch[len(arch) // 2, 1] - F.WHEEL_Z):
            off = bm.offset_polyline(arch, -w, closed=False)
        trim = np.vstack([arch, off[::-1]])
        S.region("trim_" + which, "side", trim)

    # --- cladding along the sills -------------------------------------------
    top = np.array(F.CLAD_TOP)
    top_ab = S.view_poly("side", top, closed=False)
    a_f, a_r = S.a_of(top[0, 0]), S.a_of(top[-1, 0])
    S.regions["clad"] = np.vstack([top_ab, [[a_r, b_floor_edge], [a_f, b_floor_edge]]])

    # --- lamps, grilles ---------------------------------------------------------
    S.mixed("hl", F.HEADLAMP)
    S.mixed("tl", F.TAILLAMP)
    S.region("tl_white", "rear", np.array(F.TAILLAMP_WHITE))      # clear reversing-lamp band
    S.region("grille", "front", np.array(F.GRILLE))
    S.region("grille_low", "front", np.array(F.GRILLE_LOW))
    fog_c, fog_n = fog_frame(S)
    ring_pts = fog_outline(fog_c, fog_n)
    S.regions["fog"] = S.mp.map_rays(ring_pts + fog_n * 0.3, np.tile(-fog_n, (len(ring_pts), 1)))

    # --- lower black bumper sections ------------------------------------------
    def rear_lower(P):
        z_top = np.interp(np.abs(P[:, 1]), [0.0, 0.6, 0.8, 0.95], [0.515, 0.517, 0.535, 0.55])
        return np.maximum(P[:, 2] - z_top, P[:, 0] + 1.735)
    S.implicit("rear_lower", rear_lower)

    def front_lip(P):
        return np.maximum(P[:, 2] - 0.312, 1.735 - P[:, 0])
    S.implicit("front_lip", front_lip)

    # --- cowl ---------------------------------------------------------------------
    S.region("cowl", "top", np.array([(F.COWL_X, 0.0), (F.COWL_X, 0.690), (1.028, 0.690),
                                      (1.052, 0.560), (1.074, 0.300), (1.082, 0.0)]))

    # --- panel gaps ---------------------------------------------------------------
    for name, line in F.GAPS_SIDE.items():
        S.groove(name, "side", extend(line, 0.004))
    # (the bonnet's front edge is the top edge of the grille and headlamps)
    S.groove("bonnet_side", "top", np.array(F.BONNET_SIDE_TOP))
    S.groove("bonnet_rear", "top", np.array([(F.COWL_X, 0.0), (F.COWL_X, 0.70)]))
    S.groove("tailgate", "rear", np.array(F.TAILGATE_GAP))
    if side < 0:
        f = F.FUEL_FLAP
        S.closed_groove("fuel", "side", F.rounded_rect(f["x0"], f["x1"], f["z0"], f["z1"], f["r"]),
                        side=-1.0)

    # --- rear plate recess ----------------------------------------------------------
    recess = np.array(F.PLATE_RECESS)
    S.region("recess", "rear", recess)
    S.region("recess_in", "rear", inset(recess, 0.007))
    S.fields.append(Recess("rear", recess, 0.012, 0.007))

    # --- sculpting --------------------------------------------------------------------
    S.lines["swage"] = S.view_poly("side", np.array(F.SWAGE), closed=False)
    S.fields.append(Swage(np.array(F.SWAGE)))
    sw = np.array(F.SWAGE)
    S.lines["swage_ramp"] = S.view_poly("side", bm.offset_polyline(sw, SWAGE_RAMP, closed=False), closed=False)
    # bonnet: the centre section stands proud of two creases that converge
    # towards the grille
    crease = np.array(F.BONNET_CREASE)
    S.lines["bonnet_crease"] = S.view_poly("top", crease, closed=False)
    S.lines["bonnet_ramp"] = S.view_poly("top", bm.offset_polyline(crease, -0.045, closed=False), closed=False)
    S.fields.append(bm.Displacement("top", crease, lambda s: 0.0045 * np.clip(-s / 0.045, 0.0, 1.0),
                                    box=(crease[0, 0] - 0.02, crease[-1, 0] + 0.02, 0.0, 3.0)))
    # front bumper: crisp crease under each headlamp, stepping back below it
    bc = bm.smooth_open(S.mp.map(F.BUMPER_CREASE), 6)
    S.lines["bumper_crease"] = bc
    S.fields.append(Crease(front_view(surf, bc, side), depth=0.0055, w=0.045, fade=0.05,
                           keep_off=front_view(surf, S.regions["hl"], side)))
    for (x, z) in F.HANDLES:
        S.fields.append(Dish("side", (x, z - 0.012), (0.080, 0.030), 0.010))
    return S


def fog_frame(S):
    """Centre and outward normal of the fog lamp on the bumper (left frame;
    the parameterisation is symmetric, so either side's mapper will do)."""
    surf = S.surf
    ab = S.mp.map([("front", F.FOG["y"], F.FOG["z"])])
    P = surf.eval(ab[:, 0], ab[:, 1], 1.0)[0]
    N = surf.normal(ab[:, 0], ab[:, 1], 1.0)[0]
    N[2] = 0.0
    N /= np.linalg.norm(N)
    return P, N


def fog_outline(c, n, k=40, scale=1.0):
    u = np.cross([0.0, 0.0, 1.0], n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    t = np.linspace(0, 2 * np.pi, k, endpoint=False)
    rx, ry = F.FOG["w"] / 2 * scale, F.FOG["h"] / 2 * scale
    return np.array([c + u * rx * math.cos(a) + v * ry * math.sin(a) for a in t])


# ---------------------------------------------------------------------------
# Face classification
# ---------------------------------------------------------------------------
HOLE = "hole"


def classify(lab):
    """Map the set of regions containing a face to (class, material)."""
    def has(prefix):
        return any(r == prefix or r.startswith(prefix + "_") for r in lab)

    if has("arch_front") or has("arch_rear"):
        return ("hole", None)
    if "trim_front" in lab or "trim_rear" in lab:
        return ("trim", "plastic")
    for g in ("glass_f", "glass_r", "glass_q"):
        if g in lab:
            return ("glass", "glass")
    if "ws" in lab:
        return ("glass", "glass" if "ws_clear" in lab else "frit")
    if "rg" in lab:
        return ("glass", "glass" if "rg_clear" in lab else "frit")
    if "hl" in lab:
        return ("headlamp", None)
    if "tl" in lab:
        return ("taillamp", None)
    if "fog" in lab:
        return ("fog", None)
    if "grille" in lab:
        return ("grille", None)
    if "grille_low" in lab:
        return ("grille_low", None)
    if "dlo" in lab and "dlo_in" not in lab:
        return ("shell", "chrome")
    if "dlo_in" in lab:
        return ("shell", "black_gloss")
    if "spoiler_band" in lab:
        return ("shell", "black_gloss")
    if "gbo_fuel" in lab and "gbi_fuel" not in lab:
        return ("shell", "gap")
    if any(r.startswith("gb_") for r in lab):
        return ("shell", "gap")
    if "clad" in lab or has("rear_lower") or has("front_lip") or "cowl" in lab:
        return ("shell", "plastic")
    return ("shell", "paint")


# ---------------------------------------------------------------------------
# Half assembly
# ---------------------------------------------------------------------------
class Half:
    """Overlay result for one side: vertices, faces, classes, normals."""

    def __init__(self, surf, side, extra_lines=None):
        self.surf, self.side = surf, float(side)
        self.spec = build_spec(surf, side)
        for name, (view, pts) in (extra_lines or {}).items():   # more edges to cut in (interior trims)
            self.spec.lines[name] = self.spec.view_poly(view, np.asarray(pts, float), closed=False)
        ov = bm.overlay(surf.na, surf.nb, self.spec.regions, self.spec.lines)
        self.ab = ov["ab"]
        self.faces = ov["faces"]
        self.labels = ov["labels"]
        self.line_verts = ov["line_verts"]
        self.shell = bm.Shell(surf, side, self.spec.fields)
        self.P = self.shell.eval(self.ab[:, 0], self.ab[:, 1])
        self.N = self.shell.normal(self.ab[:, 0], self.ab[:, 1])     # smooth vertex normals
        self.cls = [classify(l) for l in self.labels]
        # (a, b) faces wind inwards on the left side; the mirror image on the
        # right side winds outwards already
        if self.side > 0:
            self.faces = [f[::-1] for f in self.faces]

    def loop_normals(self, faces):
        """Analytic normals for every corner of the given faces."""
        vi = np.array([v for f in faces for v in f])
        fc = np.array([self.ab[f].mean(0) for f in faces])
        fi = np.repeat(np.arange(len(faces)), [len(f) for f in faces])
        return self.shell.normal(self.ab[vi, 0], self.ab[vi, 1], toward=(fc[fi, 0], fc[fi, 1]))

    def select(self, pred):
        return [k for k, c in enumerate(self.cls) if pred(c)]

    def region_faces(self, name):
        return [k for k, l in enumerate(self.labels) if name in l]


# ---------------------------------------------------------------------------
# Mesh data containers
# ---------------------------------------------------------------------------
class MeshData:
    """Vertices, faces, per-face material names and per-loop normals."""

    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.mats = []
        self.normals = []            # per loop (None = flat)
        self.uvs = []                # per loop (None = auto box projection)

    def add(self, verts, faces, mats, normals=None, uvs=None):
        base = len(self.verts)
        self.verts.extend([tuple(map(float, v)) for v in verts])
        for k, f in enumerate(faces):
            self.faces.append([base + i for i in f])
            self.mats.append(mats[k] if isinstance(mats, (list, tuple)) else mats)
            if normals is not None:
                self.normals.append([tuple(map(float, n)) for n in normals[k]])
            else:
                self.normals.append(None)
            self.uvs.append(uvs[k] if uvs is not None else None)
        return base

    def add_faces_from(self, half, face_ids, mat_of, offset=0.0, flip=False):
        """Copy faces of a half (with analytic normals), optionally offset
        along the normal."""
        if not face_ids:
            return
        faces = [half.faces[k] for k in face_ids]
        used = sorted({v for f in faces for v in f})
        remap = {v: i for i, v in enumerate(used)}
        P = half.P[used]
        if offset:
            P = P + half.N[used] * offset
        ln = half.loop_normals(faces)
        out_faces, out_norms, k0 = [], [], 0
        for f in faces:
            nf = ln[k0:k0 + len(f)]
            k0 += len(f)
            if flip:
                out_faces.append([remap[v] for v in f[::-1]])
                out_norms.append([tuple(-n) for n in nf[::-1]])
            else:
                out_faces.append([remap[v] for v in f])
                out_norms.append([tuple(n) for n in nf])
        mats = [mat_of(k) for k in face_ids]
        self.add(P, out_faces, mats, out_norms)

    def to_object(self, collection, materials, weld_centre=True, smooth=True):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        slots = []                               # one slot per material (keys may alias)
        for m in self.mats:
            if materials[m] not in slots:
                slots.append(materials[m])
        for mat in slots:
            me.materials.append(mat)
        idx = {k: slots.index(materials[k]) for k in set(self.mats)}
        mi = np.array([idx[m] for m in self.mats], dtype=np.int32)
        me.polygons.foreach_set("material_index", mi)
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), dtype=bool))
        # loop normals: analytic where given, face normal elsewhere
        me.update()
        loops = []
        for p, ns in zip(me.polygons, self.normals):
            if ns is None or len(ns) != p.loop_total:
                n = tuple(p.normal)
                loops.extend([n] * p.loop_total)
            else:
                loops.extend(ns)
        uv = me.uv_layers.new(name="UVMap")
        flat = []
        for p, uvs in zip(me.polygons, self.uvs):
            if uvs is not None:
                flat.extend(uvs)
            else:
                flat.extend(box_uv([me.vertices[v].co for v in p.vertices], p.normal))
        uv.data.foreach_set("uv", np.array(flat, dtype=np.float32).ravel())
        if smooth:
            me.normals_split_custom_set(loops)
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        return ob


def box_uv(cos, n, scale=1.0):
    """World-space box projection (1 UV unit = 1 m)."""
    ax = int(np.argmax(np.abs(n)))
    if ax == 0:
        return [(c.y * scale, c.z * scale) for c in cos]
    if ax == 1:
        return [(c.x * scale, c.z * scale) for c in cos]
    return [(c.x * scale, c.y * scale) for c in cos]


# ---------------------------------------------------------------------------
# Parts made from shell regions
# ---------------------------------------------------------------------------
def edge_map(half):
    em = {}
    for k, f in enumerate(half.faces):
        for i in range(len(f)):
            u, v = f[i], f[(i + 1) % len(f)]
            em.setdefault((min(u, v), max(u, v)), []).append(k)
    half._edge_map = em
    return em


def boundary(half, ids):
    """Directed boundary edges (u, v, neighbour face or None) of a face set,
    in the faces' winding order (region interior on the left)."""
    em = getattr(half, "_edge_map", None) or edge_map(half)
    S = set(ids)
    out = []
    for k in ids:
        f = half.faces[k]
        for i in range(len(f)):
            u, v = f[i], f[(i + 1) % len(f)]
            others = [q for q in em[(min(u, v), max(u, v))] if q != k]
            if not any(q in S for q in others):
                out.append((u, v, others[0] if others else None))
    return out


def smooth_vertex_normals(P, faces):
    N = np.zeros_like(P)
    for f in faces:
        p = P[f]
        n = np.zeros(3)
        for i in range(len(f)):                       # Newell's method
            a, b = p[i], p[(i + 1) % len(f)]
            n += np.cross(a, b)
        for v in f:
            N[v] += n
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def add_region_part(md, half, ids, mat_of, disp=None, smooth=False, flip=False, normals=None, depth=None):
    """Copy region faces with vertices moved by disp(ids_of_vertices) ->
    offsets along the normal.  Returns {shell vertex: new position}.
    normals="panel": faces at full depth keep the shell's smooth normals,
    faces on the ramp down to the outline are flat (a crisp recess wall)."""
    if not ids:
        return {}
    faces = [half.faces[k] for k in ids]
    used = sorted({v for f in faces for v in f})
    remap = {v: i for i, v in enumerate(used)}
    N = half.N[used]
    off = disp(np.array(used)) if disp is not None else np.zeros(len(used))
    P = half.P[used] + N * off[:, None]
    lf = [[remap[v] for v in f] for f in faces]
    if normals == "panel":
        ln = half.loop_normals(faces)
        norms, k0 = [], 0
        for f, l in zip(faces, lf):
            deep = np.all(np.abs(off[l]) > 0.97 * depth)
            if deep:
                norms.append([tuple(n) for n in ln[k0:k0 + len(f)]])
            else:
                p = P[l]
                fn = np.zeros(3)
                for i in range(len(l)):
                    fn += np.cross(p[i], p[(i + 1) % len(l)])
                fn /= max(np.linalg.norm(fn), 1e-12)
                norms.append([tuple(fn)] * len(f))
            k0 += len(f)
    elif smooth:
        VN = smooth_vertex_normals(P, lf)
        norms = [[tuple(VN[i]) for i in f] for f in lf]
    else:
        ln = half.loop_normals(faces)
        norms, k0 = [], 0
        for f in faces:
            norms.append([tuple(n) for n in ln[k0:k0 + len(f)]])
            k0 += len(f)
    if flip:
        lf = [f[::-1] for f in lf]
        norms = [[tuple(-np.array(n)) for n in ns[::-1]] for ns in norms]
    md.add(P, lf, [mat_of(k) for k in ids], norms)
    return {v: P[remap[v]] for v in used}


def trim_part(md, half, ids, lift=0.004, lip=0.035, mat="plastic"):
    """Raised moulding: region faces lifted by `lift`, a wall down to the
    shell on edges next to paint and a lip into the hole elsewhere."""
    top = add_region_part(md, half, ids, lambda k: mat, disp=lambda v: np.full(len(v), lift))
    for u, v, nb in boundary(half, ids):
        pu, pv = top[u], top[v]
        if nb is not None and half.cls[nb][0] == "shell":
            bu, bv = half.P[u], half.P[v]
        else:
            bu, bv = pu - half.N[u] * lip, pv - half.N[v] * lip
        md.add([pu, bu, bv, pv], [[0, 1, 2, 3]], [mat])


def reveal(md, half, ids, depth=0.014, mat="black_gloss"):
    """Dark return around an opening (window reveal)."""
    for u, v, nb in boundary(half, ids):
        pu, pv = half.P[u], half.P[v]
        nu, nv = half.N[u], half.N[v]
        md.add([pu, pv, pv - nv * depth, pu - nu * depth], [[0, 1, 2, 3]], [mat])


def region_edges(faces):
    """Unique undirected edges (as two index arrays) of a list of faces."""
    e = {(min(f[i], f[(i + 1) % len(f)]), max(f[i], f[(i + 1) % len(f)])) for f in faces for i in range(len(f))}
    e = np.array(sorted(e), dtype=np.int64).reshape(-1, 2)
    return e[:, 0], e[:, 1]


def smooth_field(V, e0, e1, iters, keep=0.5):
    """Laplacian smoothing of per-vertex vectors over an edge graph."""
    V = V.copy()
    cnt = np.bincount(e0, minlength=len(V)) + np.bincount(e1, minlength=len(V))
    cnt = np.maximum(cnt, 1)[:, None]
    for _ in range(iters):
        acc = np.zeros_like(V)
        np.add.at(acc, e0, V[e1])
        np.add.at(acc, e1, V[e0])
        V = keep * V + (1.0 - keep) * acc / cnt
        V /= np.maximum(np.linalg.norm(V, axis=1, keepdims=True), 1e-12)
    return V


def recess(md, half, ids, depth, panel_mat, wall_mat, iters=40):
    """Recessed panel behind an opening and straight walls from the
    opening's edge down to it.  The panel is the undisplaced surface pushed
    back along a smoothed normal, so creases, grooves and the shoulder line
    that cross an opening don't wrinkle the panel behind it."""
    if not ids:
        return
    mats = panel_mat if callable(panel_mat) else (lambda k: panel_mat)
    faces = [half.faces[k] for k in ids]
    used = sorted({v for f in faces for v in f})
    remap = {v: i for i, v in enumerate(used)}
    lf = [[remap[v] for v in f] for f in faces]
    ab = half.ab[used]
    D = smooth_field(half.shell.base_normal(ab[:, 0], ab[:, 1]), *region_edges(lf), iters)
    P = half.shell.base(ab[:, 0], ab[:, 1]) - D * depth
    md.add(P, lf, [mats(k) for k in ids], [[tuple(D[i]) for i in f] for f in lf])
    for u, v, _ in boundary(half, ids):
        md.add([half.P[u], half.P[v], P[remap[v]], P[remap[u]]], [[0, 1, 2, 3]], [wall_mat])


def boundary_distance(half, ids):
    """3D distance of each region vertex to the region outline."""
    bnd = boundary(half, ids)
    bv = np.array(sorted({u for u, _, _ in bnd} | {v for _, v, _ in bnd}))
    B = half.P[bv]

    def dist(vids):
        Q = half.P[vids]
        d = np.full(len(Q), np.inf)
        for s in range(0, len(B), 256):
            d = np.minimum(d, np.linalg.norm(Q[:, None, :] - B[None, s:s + 256, :], axis=2).min(1))
        return d
    return dist


def bowl(half, ids, depth, ramp):
    """Displacement for a recessed housing: 0 on the outline, -depth inside."""
    dist = boundary_distance(half, ids)

    def disp(vids):
        s = np.clip(dist(vids) / ramp, 0.0, 1.0)
        return -depth * s * s * (3 - 2 * s)
    return disp, dist


def surface_patch(md, half, poly_ab, offset, mat, thickness=0.0, sub=2):
    """Separate piece following the shell inside a parameter-space polygon
    (e.g. the chrome V over the grille opening), lifted by `offset`, with
    side walls of `thickness` going back towards the shell."""
    poly = np.asarray(poly_ab, float)
    if bm.polygon_area(poly) < 0:
        poly = poly[::-1]
    a0, b0 = poly.min(0)
    a1, b1 = poly.max(0)
    ga = np.arange(math.floor(a0), math.ceil(a1) + 1e-9, 1.0 / sub)
    gb = np.arange(math.floor(b0), math.ceil(b1) + 1e-9, 1.0 / sub)
    G = np.array([(a, b) for a in ga for b in gb])
    G = G[bm.points_in_polygon(G, poly)] if len(G) else np.zeros((0, 2))
    verts = [Vector((p[0], p[1])) for p in poly] + [Vector((p[0], p[1])) for p in G]
    n = len(poly)
    edges = [(i, (i + 1) % n) for i in range(n)]
    out = bm.geometry.delaunay_2d_cdt(verts, edges, [list(range(n))], 1, 1e-9, True)
    ab = np.array([(v.x, v.y) for v in out[0]])
    faces = [list(f) for f in out[2]]
    S = half.shell
    Pb = S.eval(ab[:, 0], ab[:, 1])                  # sits on the sculpted shell
    N = S.normal(ab[:, 0], ab[:, 1])
    P = Pb + N * offset
    if half.side > 0:
        faces = [f[::-1] for f in faces]
    norms = [[tuple(N[v]) for v in f] for f in faces]
    md.add(P, faces, [mat] * len(faces), norms)
    if thickness:
        # outline walls
        em = {}
        for f in faces:
            for i in range(len(f)):
                u, v = f[i], f[(i + 1) % len(f)]
                em[(u, v)] = em.get((u, v), 0) + 1
        for (u, v) in list(em):
            if (v, u) in em:
                continue
            pu, pv = P[u], P[v]
            md.add([pu, pu - N[u] * thickness, pv - N[v] * thickness, pv], [[0, 1, 2, 3]], [mat])
