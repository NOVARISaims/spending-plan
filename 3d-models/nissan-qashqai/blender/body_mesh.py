"""Body-shell mesh with the feature outlines cut in exactly.

The shell is the loft S(a, b) from qashqai_body (a = station, b = ring row).
Every feature (window, lamp, panel gap, wheel arch, trim...) is an outline
given in one of the orthographic views, in a solved photo camera, or in
parameter space.  Outlines are mapped onto the surface (ray cast + Newton
refinement), and the grid cells they cross are re-triangulated with a
constrained Delaunay triangulation in (a, b) space, so every outline becomes
a chain of mesh edges.  Each face records the regions that contain it.

Surface displacements (V-grooves for panel gaps, the lower-door swage, the
rear haunch) are analytic fields evaluated at the vertex parameters, so
normals stay exact and creases stay crisp.
"""
import math

import bpy  # noqa: F401  (must precede mathutils with the PyPI bpy module)
import numpy as np
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

import qashqai_body as qb

# Views: ray direction (from the viewer into the car) and the two world axes
# used as 2D coordinates.
VIEWS = {
    "side": (np.array([0.0, -1.0, 0.0]), (0, 2)),     # from the left: (X, Z)
    "front": (np.array([-1.0, 0.0, 0.0]), (1, 2)),    # from the front: (Y, Z)
    "rear": (np.array([1.0, 0.0, 0.0]), (1, 2)),      # from the rear: (Y, Z)
    "top": (np.array([0.0, 0.0, -1.0]), (0, 1)),      # from above: (X, Y)
}


# ---------------------------------------------------------------------------
# Displacement fields
# ---------------------------------------------------------------------------
def _seg_dist(p, a, b):
    """Distance from points p (N,2) to segment a-b, plus the side sign."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-18), 0.0, 1.0)
    q = a + t[:, None] * ab
    d = np.linalg.norm(p - q, axis=1)
    cross = ab[0] * (p[:, 1] - a[1]) - ab[1] * (p[:, 0] - a[0])
    return d, np.sign(cross)


def polyline_distance(p, line):
    """Unsigned distance to a polyline and the sign of the nearest segment's
    side (+1 = left of the direction of travel)."""
    best = np.full(len(p), np.inf)
    sign = np.ones(len(p))
    for a, b in zip(line[:-1], line[1:]):
        d, s = _seg_dist(p, a, b)
        m = d < best
        best[m], sign[m] = d[m], s[m]
    return best, sign


class Displacement:
    """Offset along the surface normal as a function of the signed distance
    s (metres, in the view plane) to a polyline.  profile(s) -> metres."""

    def __init__(self, view, line, profile, side=1.0, box=None):
        self.view = view
        self.line = np.asarray(line, float)
        self.profile = profile
        self.side = side              # which body side it applies to (+1 left, -1 right, 0 both)
        self.box = box                # optional (xmin, xmax, zmin, zmax) world clip

    def __call__(self, P, N, sides):
        d, axes = VIEWS[self.view]
        p2 = P[:, list(axes)].copy()
        if self.view in ("front", "rear"):
            p2[:, 0] = np.abs(p2[:, 0])
        elif self.view == "top":
            p2[:, 1] = np.abs(p2[:, 1])
        dist, sgn = polyline_distance(p2, self.line)
        out = self.profile(dist * sgn)
        if self.side:
            out = np.where(sides == self.side, out, 0.0)
        # fade out (rather than cut off) where the surface turns away from
        # the view and at the edges of the clip box, so nothing tears
        facing = -(N @ d) if self.view != "side" else np.abs(N[:, 1])
        out = out * smoothstep((facing - 0.25) / 0.2)
        if self.box is not None:
            x0, x1, z0, z1 = self.box
            e = 0.02
            out = out * smoothstep((P[:, 0] - x0) / e) * smoothstep((x1 - P[:, 0]) / e) \
                * smoothstep((P[:, 2] - z0) / e) * smoothstep((z1 - P[:, 2]) / e)
        return out


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def v_groove(width, depth):
    """Panel gap: V-shaped groove centred on the line."""
    h = width / 2.0
    return lambda s: -depth * np.clip(1.0 - np.abs(s) / h, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Displaced surface
# ---------------------------------------------------------------------------
class Shell:
    """S(a, b) plus displacement fields, for one side (+1 left, -1 right)."""

    def __init__(self, surf, side, fields=()):
        self.surf = surf
        self.side = float(side)
        self.fields = list(fields)

    def base(self, a, b):
        return self.surf.eval(a, b, self.side)

    def base_normal(self, a, b, toward=None):
        return self.surf.normal(a, b, self.side, toward=toward)

    def eval(self, a, b):
        P = self.base(a, b)
        if not self.fields:
            return P
        N = self.base_normal(a, b)
        return P + N * self._offset(P, N)[:, None]

    def offset(self, a, b):
        """Total displacement along the base normal at (a, b)."""
        P = self.base(a, b)
        if not self.fields:
            return np.zeros(len(P))
        return self._offset(P, self.base_normal(a, b))

    def _offset(self, P, N):
        sides = np.full(len(P), self.side)
        d = np.zeros(len(P))
        for f in self.fields:
            d += f(P, N, sides)
        return d

    def normal(self, a, b, toward=None, h=0.01):
        a = np.atleast_1d(np.asarray(a, float)).ravel()
        b = np.atleast_1d(np.asarray(b, float)).ravel()
        if toward is not None:
            ac, bc = toward
            a = a + 0.04 * (np.asarray(ac, float).ravel() - a)
            b = b + 0.04 * (np.asarray(bc, float).ravel() - b)
        na, nb = self.surf.na, self.surf.nb
        a0, a1 = np.clip(a - h, 0, na), np.clip(a + h, 0, na)
        b0, b1 = np.clip(b - h, 0, nb), np.clip(b + h, 0, nb)
        da = self.eval(a1, b) - self.eval(a0, b)
        db = self.eval(a, b1) - self.eval(a, b0)
        n = np.cross(db, da) if self.side > 0 else np.cross(da, db)
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def camera_basis(yaw, pitch, roll):
    """View direction, right and up vectors of a photo camera (yaw measured
    from +X towards +Y)."""
    d = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    r = np.cross(d, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    cr, sr = math.cos(roll), math.sin(roll)
    return d, cr * r + sr * u, -sr * r + cr * u


def pixel_ray(cam, uv):
    cx, cy, cz, yaw, pitch, roll, f, ppx, ppy = cam
    d, r, u = camera_basis(yaw, pitch, roll)
    ray = d + r * (uv[0] - ppx) / f - u * (uv[1] - ppy) / f
    return np.array([cx, cy, cz], float), ray / np.linalg.norm(ray)


# ---------------------------------------------------------------------------
# Mapping view coordinates onto the surface
# ---------------------------------------------------------------------------
class Mapper:
    """Ray casts view / camera points onto the (undisplaced) shell of one
    side and returns surface parameters (a, b)."""

    def __init__(self, surf, side, sub=3):
        self.surf = surf
        self.side = float(side)
        A = np.linspace(0.0, surf.na, surf.na * sub + 1)
        B = np.linspace(0.0, surf.nb, surf.nb * sub + 1)
        AA, BB = np.meshgrid(A, B, indexing="ij")
        P = surf.eval(AA, BB, self.side)
        self.ab = np.column_stack([AA.ravel(), BB.ravel()])
        ni, nj = len(A), len(B)
        idx = np.arange(ni * nj).reshape(ni, nj)
        q = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], -1).reshape(-1, 4)
        tris = np.vstack([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
        self.tris = tris
        self.P = P
        self.bvh = BVHTree.FromPolygons([Vector(p) for p in P], tris.tolist(), all_triangles=True)

    def _hit(self, origin, direction):
        loc, nrm, fi, dist = self.bvh.ray_cast(Vector(origin), Vector(direction))
        if loc is None:
            return None
        t = self.tris[fi]
        # barycentric weights
        p0, p1, p2 = (np.array(self.P[k]) for k in t)
        v0, v1, v2 = p1 - p0, p2 - p0, np.array(loc) - p0
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        wv = (d11 * d20 - d01 * d21) / den
        ww = (d00 * d21 - d01 * d20) / den
        return self.ab[t[0]] * (1 - wv - ww) + self.ab[t[1]] * wv + self.ab[t[2]] * ww

    def _refine(self, ab, origin, direction, iters=4):
        """Newton: S(a, b) on the ray through origin."""
        d = np.asarray(direction, float) / np.linalg.norm(direction)
        u = np.cross(d, [0.0, 0.0, 1.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(d, [1.0, 0.0, 0.0])
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        o = np.asarray(origin, float)
        a, b = ab
        for _ in range(iters):
            def f(a_, b_):
                q = self.surf.eval([a_], [b_], self.side)[0] - o
                q = q - d * (q @ d)
                return np.array([q @ u, q @ v])
            r = f(a, b)
            h = 1e-4
            J = np.column_stack([(f(a + h, b) - r) / h, (f(a, b + h) - r) / h])
            try:
                step = np.linalg.solve(J, -r)
            except np.linalg.LinAlgError:
                break
            a = float(np.clip(a + step[0], 0.0, self.surf.na))
            b = float(np.clip(b + step[1], 0.0, self.surf.nb))
            if np.abs(step).max() < 1e-7:
                break
        return (a, b)

    def view_point(self, view, c):
        """Surface parameters of the first hit of a view ray at 2D coords c."""
        d, (i, j) = VIEWS[view]
        o = np.zeros(3)
        o[i], o[j] = c[0], c[1]
        if view == "side":
            o[1] = 5.0 * self.side
            d = np.array([0.0, -self.side, 0.0])
        elif view in ("front", "rear"):
            o[1] = c[0] * self.side          # outlines are authored for the left half (Y >= 0)
            o[0] = 5.0 if view == "front" else -5.0
        elif view == "top":
            o[1] = c[1] * self.side
            o[2] = 5.0
        hit = self._hit(o, d)
        if hit is None:
            return None
        return self._refine(hit, o, d)

    def camera_point(self, cam, uv):
        """Surface parameters of the pixel uv of a solved photo camera
        [cx, cy, cz, yaw, pitch, roll, f, ppx, ppy] (left-side frame)."""
        o, d = pixel_ray(cam, uv)
        if self.side < 0:
            o, d = o * [1, -1, 1], d * [1, -1, 1]
        hit = self._hit(o, d)
        if hit is None:
            return None
        return self._refine(hit, o, d)

    def _ray(self, view, c):
        d, (i, j) = VIEWS[view]
        o = np.zeros(3)
        o[i], o[j] = c[0], c[1]
        if view == "side":
            o[1] = 5.0 * self.side
            d = np.array([0.0, -self.side, 0.0])
        elif view in ("front", "rear"):
            # outlines are authored for the left half; points on the centre
            # line land on the seam
            o[1] = max(c[0], 1e-6) * self.side
            o[0] = 5.0 if view == "front" else -5.0
        elif view == "top":
            o[1] = max(c[1], 1e-6) * self.side
            o[2] = 5.0
        return o, d

    def cam_ray(self, name, uv):
        import photo_cams
        o, d = photo_cams.ray(name, uv)
        if self.side < 0:                      # photos of the left side trace the right by symmetry
            o, d = o * [1, -1, 1], d * [1, -1, 1]
        return o, d

    def map(self, pts, iters=5):
        """pts: list of (view, c0, c1) / ("ab", a, b).  Returns (K, 2) surface
        parameters: BVH ray cast, then a vectorised Newton refinement."""
        ab = np.zeros((len(pts), 2))
        O = np.zeros((len(pts), 3))
        D = np.zeros((len(pts), 3))
        fixed = np.zeros(len(pts), bool)
        for k, p in enumerate(pts):
            if p[0] == "ab":
                ab[k] = (p[1], p[2])
                fixed[k] = True
                continue
            if p[0].startswith("cam:"):
                o, d = self.cam_ray(p[0][4:], (p[1], p[2]))
            else:
                o, d = self._ray(p[0], (p[1], p[2]))
            hit = self._hit(o, d)
            if hit is None:
                raise ValueError("outline point misses the body: %r" % (p,))
            ab[k], O[k], D[k] = hit, o, d
        m = ~fixed
        if m.any():
            ab[m] = self._newton(ab[m], O[m], D[m], iters)
        return ab

    def map_rays(self, O, D, iters=5):
        """Surface parameters of the first hits of rays O + t D (left-side frame
        points are mirrored for the right side)."""
        O = np.atleast_2d(np.asarray(O, float)).copy()
        D = np.atleast_2d(np.asarray(D, float)).copy()
        if self.side < 0:
            O[:, 1] *= -1.0
            D[:, 1] *= -1.0
        ab = np.zeros((len(O), 2))
        for k in range(len(O)):
            hit = self._hit(O[k], D[k])
            if hit is None:
                raise ValueError("ray misses the body: %r %r" % (O[k], D[k]))
            ab[k] = hit
        return self._newton(ab, O, D, iters)

    def _newton(self, ab, O, D, iters):
        D = D / np.linalg.norm(D, axis=1, keepdims=True)
        ref = np.where(np.abs(D[:, 2:3]) > 0.9, [[1.0, 0.0, 0.0]], [[0.0, 0.0, 1.0]])
        U = np.cross(D, ref)
        U /= np.linalg.norm(U, axis=1, keepdims=True)
        V = np.cross(D, U)

        def f(a, b):
            q = self.surf.eval(a, b, self.side) - O
            return np.column_stack([(q * U).sum(1), (q * V).sum(1)])

        a, b = ab[:, 0].copy(), ab[:, 1].copy()
        h = 1e-4
        for _ in range(iters):
            r = f(a, b)
            ja = (f(a + h, b) - r) / h
            jb = (f(a, b + h) - r) / h
            det = ja[:, 0] * jb[:, 1] - jb[:, 0] * ja[:, 1]
            ok = np.abs(det) > 1e-14
            det = np.where(ok, det, 1.0)
            da = (-r[:, 0] * jb[:, 1] + jb[:, 0] * r[:, 1]) / det
            db = (-ja[:, 0] * r[:, 1] + r[:, 0] * ja[:, 1]) / det
            da, db = np.where(ok, da, 0.0), np.where(ok, db, 0.0)
            step = np.clip(np.column_stack([da, db]), -2.0, 2.0)
            a = np.clip(a + step[:, 0], 0.0, self.surf.na)
            b = np.clip(b + step[:, 1], 0.0, self.surf.nb)
            if np.abs(step).max() < 1e-7:
                break
        return np.column_stack([a, b])


# ---------------------------------------------------------------------------
# Outline helpers (view space)
# ---------------------------------------------------------------------------
def densify(poly, step, closed=True):
    """Insert points so no segment is longer than step (same units)."""
    poly = np.asarray(poly, float)
    pts = list(poly) + ([poly[0]] if closed else [])
    out = []
    for p, q in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(q - p) / step)))
        for k in range(n):
            out.append(p + (q - p) * k / n)
    if not closed:
        out.append(pts[-1])
    return np.array(out)


def smooth_closed(ctrl, n_per=8):
    """Closed centripetal Catmull-Rom through ctrl points (N, 2)."""
    ctrl = np.asarray(ctrl, float)
    N = len(ctrl)
    out = []
    for i in range(N):
        p0, p1, p2, p3 = ctrl[(i - 1) % N], ctrl[i], ctrl[(i + 1) % N], ctrl[(i + 2) % N]
        out.extend(_cr_seg(p0, p1, p2, p3, n_per))
    return np.array(out)


def smooth_open(ctrl, n_per=8):
    ctrl = np.asarray(ctrl, float)
    ext = np.vstack([2 * ctrl[0] - ctrl[1], ctrl, 2 * ctrl[-1] - ctrl[-2]])
    out = []
    for i in range(1, len(ext) - 2):
        out.extend(_cr_seg(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], n_per))
    out.append(ctrl[-1])
    return np.array(out)


def _cr_seg(p0, p1, p2, p3, n, alpha=0.5):
    def kn(a, b):
        return max(np.linalg.norm(b - a), 1e-6) ** alpha
    t0, t1 = 0.0, kn(p0, p1)
    t2 = t1 + kn(p1, p2)
    t3 = t2 + kn(p2, p3)
    out = []
    for k in range(n):
        t = t1 + (t2 - t1) * k / n
        a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
        a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
        a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
        b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
        b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
        out.append((t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2)
    return out


def offset_polyline(poly, dist, closed=True):
    """Offset a 2D polyline sideways (+ = left of travel) with mitred joins."""
    poly = np.asarray(poly, float)
    n = len(poly)
    out = []
    for i in range(n):
        if closed:
            p_prev, p, p_next = poly[i - 1], poly[i], poly[(i + 1) % n]
        else:
            p = poly[i]
            p_prev = poly[i - 1] if i > 0 else 2 * p - poly[i + 1]
            p_next = poly[i + 1] if i < n - 1 else 2 * p - poly[i - 1]
        t1 = p - p_prev
        t2 = p_next - p
        t1 /= max(np.linalg.norm(t1), 1e-12)
        t2 /= max(np.linalg.norm(t2), 1e-12)
        n1 = np.array([-t1[1], t1[0]])
        n2 = np.array([-t2[1], t2[0]])
        m = n1 + n2
        lm = np.linalg.norm(m)
        if lm < 1e-9:
            m = n1
        else:
            m /= lm
        scale = 1.0 / max(m @ n1, 0.35)
        out.append(p + m * dist * scale)
    return np.array(out)


def polygon_area(p):
    p = np.asarray(p, float)
    return 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def points_in_polygon(pts, poly):
    """Even-odd test, vectorised over pts (N, 2)."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    px, py = poly[:, 0], poly[:, 1]
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi, xj, yj = px[i], py[i], px[j], py[j]
        cond = ((yi > y) != (yj > y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
        inside ^= cond & (x < xint)
        j = i
    return inside


# ---------------------------------------------------------------------------
# Overlay: grid + outlines -> faces with region labels
# ---------------------------------------------------------------------------
def _cells_touched(segs, na, nb):
    """Grid cells (i, j) crossed by any segment (a, b) -> set."""
    cells = set()
    for (a0, b0), (a1, b1) in segs:
        n = int(max(abs(a1 - a0), abs(b1 - b0)) * 4) + 2
        for t in np.linspace(0.0, 1.0, n):
            a = a0 + (a1 - a0) * t
            b = b0 + (b1 - b0) * t
            i = int(min(max(math.floor(a), 0), na - 1))
            j = int(min(max(math.floor(b), 0), nb - 1))
            cells.add((i, j))
            # points on a grid line touch both neighbours
            if abs(a - round(a)) < 1e-6:
                cells.add((int(min(max(round(a) - 1, 0), na - 1)), j))
            if abs(b - round(b)) < 1e-6:
                cells.add((i, int(min(max(round(b) - 1, 0), nb - 1))))
    return cells


def overlay(na, nb, regions, lines):
    """Planar overlay of the (na x nb) cell grid with closed region outlines
    and open polylines, all in (a, b) parameter space.

    regions: {name: (K, 2) closed polygon}  lines: {name: (K, 2) polyline}
    Returns dict(ab=(V, 2), faces=[[v...]], labels=[frozenset], line_verts={name: set})
    Grid vertex (i, j) has index i * (nb + 1) + j.
    """
    segs = []
    for poly in regions.values():
        p = np.asarray(poly, float)
        segs += list(zip(p, np.roll(p, -1, axis=0)))
    for line in lines.values():
        p = np.asarray(line, float)
        segs += list(zip(p[:-1], p[1:]))
    touched = _cells_touched(segs, na, nb)
    # dilate so the CDT zone boundary never carries inserted vertices
    zone = set()
    for i, j in touched:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                ii, jj = i + di, j + dj
                if 0 <= ii < na and 0 <= jj < nb:
                    zone.add((ii, jj))
    zone = sorted(zone)
    zone_set = set(zone)
    nbv = nb + 1
    gid = lambda i, j: i * nbv + j  # noqa: E731

    # --- CDT input -----------------------------------------------------------
    in_verts, in_ids = [], []          # coords and global grid ids (or -1)
    vmap = {}

    def add_grid(i, j):
        k = gid(i, j)
        if k not in vmap:
            vmap[k] = len(in_verts)
            in_verts.append((float(i), float(j)))
            in_ids.append(k)
        return vmap[k]

    in_faces = []
    for (i, j) in zone:
        in_faces.append([add_grid(i, j), add_grid(i + 1, j), add_grid(i + 1, j + 1), add_grid(i, j + 1)])
    n_cells = len(in_faces)
    in_edges = []
    edge_line = []                      # input edge index -> line name or None
    region_names = list(regions)
    for name in region_names:
        p = np.asarray(regions[name], float)
        if polygon_area(p) < 0:          # the CDT needs counter-clockwise faces
            p = p[::-1]
        base = len(in_verts)
        for q in p:
            in_verts.append((float(q[0]), float(q[1])))
            in_ids.append(-1)
        idx = list(range(base, base + len(p)))
        in_faces.append(idx)
        for k in range(len(p)):
            in_edges.append((idx[k], idx[(k + 1) % len(p)]))
            edge_line.append(None)
    for name, line in lines.items():
        p = np.asarray(line, float)
        base = len(in_verts)
        for q in p:
            in_verts.append((float(q[0]), float(q[1])))
            in_ids.append(-1)
        for k in range(len(p) - 1):
            in_edges.append((base + k, base + k + 1))
            edge_line.append(name)

    out = geometry.delaunay_2d_cdt([Vector(v) for v in in_verts], in_edges, in_faces, 4, 1e-7, True)
    o_verts, o_edges, o_faces, o_orig_v, o_orig_e, o_orig_f = out

    # --- vertices ------------------------------------------------------------
    ab = [(float(i), float(j)) for i in range(na + 1) for j in range(nb + 1)]
    omap = []
    for k, v in enumerate(o_verts):
        gids = [in_ids[q] for q in o_orig_v[k] if in_ids[q] >= 0]
        if gids:
            omap.append(gids[0])
        else:
            omap.append(len(ab))
            ab.append((v.x, v.y))

    # --- faces ---------------------------------------------------------------
    faces, labels = [], []
    polys = {n: np.asarray(regions[n], float) for n in region_names}
    for (i, j) in ((i, j) for i in range(na) for j in range(nb)):
        if (i, j) in zone_set:
            continue
        faces.append([gid(i, j), gid(i + 1, j), gid(i + 1, j + 1), gid(i, j + 1)])
        labels.append(None)             # classified below
    plain = len(faces)
    for f, orig in zip(o_faces, o_orig_f):
        cells = [q for q in orig if q < n_cells]
        if not cells:
            continue
        regs = frozenset(region_names[q - n_cells] for q in orig if q >= n_cells)
        faces.append([omap[k] for k in f])
        labels.append(regs)
    # classify untouched cells by their centres
    centres = np.array([[f[0] // nbv + 0.5, f[0] % nbv + 0.5] for f in faces[:plain]]) if plain else np.zeros((0, 2))
    member = {n: points_in_polygon(centres, polys[n]) for n in region_names}
    for k in range(plain):
        labels[k] = frozenset(n for n in region_names if member[n][k])

    # --- vertices on open lines ----------------------------------------------
    line_verts = {n: set() for n in lines}
    for k, e in enumerate(o_edges):
        for q in o_orig_e[k]:
            if q < len(edge_line) and edge_line[q] is not None:
                line_verts[edge_line[q]].update(omap[v] for v in e)
    return dict(ab=np.array(ab), faces=faces, labels=labels, line_verts=line_verts)


# ---------------------------------------------------------------------------
# Implicit regions -> polygons (marching squares in parameter space)
# ---------------------------------------------------------------------------
def contour_polygons(F, a_vals, b_vals):
    """Closed polylines of F = 0 (inside: F < 0) sampled on a grid
    F[i, j] at (a_vals[i], b_vals[j]).  The grid is padded with 'outside'
    so contours close along the domain boundary (clamped back onto it)."""
    Fp = np.pad(F, 1, constant_values=1.0)
    ap = np.concatenate([[a_vals[0] - 1e-3], a_vals, [a_vals[-1] + 1e-3]])
    bp = np.concatenate([[b_vals[0] - 1e-3], b_vals, [b_vals[-1] + 1e-3]])
    ni, nj = Fp.shape
    segs = {}

    def interp(i0, j0, i1, j1):
        f0, f1 = Fp[i0, j0], Fp[i1, j1]
        t = f0 / (f0 - f1) if f0 != f1 else 0.5
        a = ap[i0] + (ap[i1] - ap[i0]) * t
        b = bp[j0] + (bp[j1] - bp[j0]) * t
        return (round(float(np.clip(a, a_vals[0], a_vals[-1])), 9),
                round(float(np.clip(b, b_vals[0], b_vals[-1])), 9))

    inside = Fp < 0
    for i in range(ni - 1):
        for j in range(nj - 1):
            c = (inside[i, j], inside[i + 1, j], inside[i + 1, j + 1], inside[i, j + 1])
            if all(c) or not any(c):
                continue
            # edges: 0 bottom (i,j)-(i+1,j), 1 right (i+1,j)-(i+1,j+1),
            #        2 top (i+1,j+1)-(i,j+1), 3 left (i,j+1)-(i,j)
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
            pts = {}
            for e in range(4):
                p, q = corners[e], corners[(e + 1) % 4]
                if inside[p] != inside[q]:
                    pts[e] = interp(p[0], p[1], q[0], q[1])
            es = sorted(pts)
            if len(es) == 2:
                pairs = [(es[0], es[1])]
            else:                                   # saddle: pair by the centre value
                centre = Fp[i:i + 2, j:j + 2].mean() < 0
                pairs = [(0, 1), (2, 3)] if centre == inside[i, j] else [(0, 3), (1, 2)]
            for e0, e1 in pairs:
                p0, p1 = pts[e0], pts[e1]
                segs.setdefault(p0, []).append(p1)
                segs.setdefault(p1, []).append(p0)
    loops = []
    seen = set()
    for start in list(segs):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = [q for q in segs[cur] if q != prev and q not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) >= 4:
            loops.append(np.array(loop))
    return loops


def simplify(poly, tol):
    """Drop nearly collinear points (closed polyline)."""
    keep = [poly[0]]
    for k in range(1, len(poly) - 1):
        a, b, c = np.array(keep[-1]), poly[k], poly[k + 1]
        ab, ac = b - a, c - a
        area = abs(ab[0] * ac[1] - ab[1] * ac[0])
        if area / max(np.linalg.norm(ac), 1e-12) > tol:
            keep.append(b)
    keep.append(poly[-1])
    return np.array(keep)
