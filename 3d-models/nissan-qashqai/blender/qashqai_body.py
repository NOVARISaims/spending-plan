"""Body-shell surface of a 2014-2017 Nissan Qashqai (J11, pre-facelift).

The shell is one closed loft: at every station X along the car a closed
cross-section is built from a handful of control points (sill, bulge,
shoulder crease, beltline, roof rail, roof centre) and sampled with a
centripetal Catmull-Rom spline.  Each control point follows a profile
keyframed along X.  The profiles were measured off the side photos through
their solved cameras (perspective-corrected, see README) at the published
1806 mm width, 1590 mm height and 2646 mm wheelbase.  The greenhouse widths
from the front doors back, and every profile from the rear wheel arch back,
were then fitted to the cross-sections of a 2018 (facelift) model of the car,
whose body shell behind the windscreen is carried over; the shoulder crease
and the window line stay where the photos put them.  The nose follows the
photos and the tail the reference model, which makes the car 4.6 cm shorter
than the published 4377 mm (4331 mm bumper to bumper, 4346 mm with the front
plate).

Surface(ds) evaluates the shell continuously as S(a, b): a runs along the
stations (spaced so the surface moves about ds between them), b along the
half section.  Pure numpy.  Car frame: X forward, Y left, Z up, metres;
origin on the ground midway between the axles.
"""
import numpy as np

WHEELBASE = 2.646
X_FA, X_RA = WHEELBASE / 2.0, -WHEELBASE / 2.0      # axle positions
X_F, X_R = 2.177, -2.154                             # bumper tips (see README: 4.331 m)
HALF_W = 0.903                                       # 1806 mm body width


_PCHIP = {}


def _pchip_coeffs(keys):
    tk = tuple(tuple(k) for k in keys)
    c = _PCHIP.get(tk)
    if c is None:
        ks = sorted(tk)
        xk = np.array([k[0] for k in ks], float)
        yk = np.array([k[1] for k in ks], float)
        h = np.diff(xk)
        d = np.diff(yk) / h
        m = np.zeros_like(yk)
        for i in range(1, len(xk) - 1):
            if d[i - 1] * d[i] > 0.0:
                w1, w2 = 2.0 * h[i] + h[i - 1], h[i] + 2.0 * h[i - 1]
                m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
        m[0], m[-1] = d[0], d[-1]
        c = _PCHIP[tk] = (xk, yk, h, m)
    return c


def pchip(keys, x):
    """Shape-preserving cubic interpolation through (x, y) keyframes."""
    xk, yk, h, m = _pchip_coeffs(keys)
    x = np.clip(np.asarray(x, float), xk[0], xk[-1])
    i = np.clip(np.searchsorted(xk, x) - 1, 0, len(h) - 1)
    t = (x - xk[i]) / h[i]
    t2, t3 = t * t, t * t * t
    return ((2 * t3 - 3 * t2 + 1) * yk[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
            + (-2 * t3 + 3 * t2) * yk[i + 1] + (t3 - t2) * h[i] * m[i + 1])


# ---------------------------------------------------------------------------
# Profiles (X -> value).  Heights from the side photos, widths from the
# front/rear photos and the 1806 mm body width.  Keys behind X = -1.3 (and
# the greenhouse widths back from X = 0.4) are the fit to the reference
# model's sections; the tail's plan shape is in its width keys.
# ---------------------------------------------------------------------------
P = {
    # --- side view (Z) -----------------------------------------------------
    # top silhouette on the centre line: bumper face, bonnet, windscreen,
    # roof, spoiler, tailgate glass, tailgate panel
    "z_top": [(2.177, 0.700), (2.1566, 0.780), (2.1035, 0.840), (2.0062, 0.900), (1.90, 0.935),
              (1.80, 0.975), (1.68, 1.020), (1.50, 1.065), (1.30, 1.085), (1.12, 1.100), (1.00, 1.140),
              (0.80, 1.235), (0.55, 1.365), (0.30, 1.475), (0.10, 1.545), (-0.15, 1.580),
              (-0.40, 1.590), (-0.70, 1.580), (-1.00, 1.562), (-1.30, 1.537), (-1.38, 1.532),
              (-1.44, 1.522), (-1.56, 1.509), (-1.62, 1.502), (-1.68, 1.502), (-1.73, 1.363),
              (-1.77, 1.331), (-1.86, 1.264), (-2.00, 1.141), (-2.02, 1.121), (-2.04, 0.955),
              (-2.055, 0.831), (-2.07, 0.711), (-2.115, 0.701), (-2.13, 0.630), (-2.154, 0.515)],
    # beltline / greenhouse base (side edge of the top); bonnet side edge in front
    "z_shelf": [(2.177, 0.680), (2.1035, 0.800), (1.9885, 0.870), (1.85, 0.920), (1.60, 0.990),
                (1.30, 1.045), (1.10, 1.075), (0.85, 1.090), (0.50, 1.085), (0.00, 1.105),
                (-0.50, 1.128), (-0.60, 1.134), (-0.85, 1.210), (-1.10, 1.269), (-1.38, 1.276),
                (-1.44, 1.272), (-1.56, 1.244), (-1.68, 1.184), (-1.83, 1.117), (-1.975, 1.061),
                (-2.00, 1.044), (-2.02, 0.991), (-2.04, 0.922), (-2.154, 0.507)],
    # shoulder crease under the beltline
    "z_sh": [(2.177, 0.620), (2.077, 0.740), (1.9442, 0.840), (1.80, 0.880), (1.40, 0.930),
             (0.80, 0.975), (0.00, 1.005), (-0.80, 1.035), (-1.40, 1.070), (-1.70, 1.079),
             (-1.77, 1.067), (-1.83, 1.037), (-1.86, 1.010), (-1.95, 0.924), (-2.115, 0.771),
             (-2.154, 0.730)],
    # widest line of the lower body
    "z_bulge": [(2.177, 0.520), (1.90, 0.600), (1.20, 0.660), (0.00, 0.680), (-1.20, 0.680),
                (-1.89, 0.620), (-2.154, 0.520)],
    # bottom edge of the sides (sill / bumper lower edges)
    "z_sill": [(2.177, 0.330), (2.077, 0.315), (1.90, 0.305), (1.60, 0.300), (0.90, 0.300),
               (0.00, 0.300), (-0.90, 0.300), (-1.60, 0.320), (-1.94, 0.370), (-2.09, 0.400),
               (-2.154, 0.440)],
    "z_floor": [(2.177, 0.330), (2.0947, 0.290), (1.9442, 0.250), (1.80, 0.220), (0.00, 0.200),
                (-1.80, 0.220), (-2.05, 0.310), (-2.154, 0.430)],
    # --- plan view (half widths before the nose taper) --------------------
    "w_bulge": [(2.177, 0.880), (1.80, 0.895), (1.323, 0.903), (0.60, 0.890), (-0.60, 0.890),
                (-1.30, 0.903), (-1.38, 0.904), (-1.68, 0.869), (-1.89, 0.794), (-1.975, 0.763),
                (-2.02, 0.741), (-2.055, 0.692), (-2.07, 0.662), (-2.115, 0.571), (-2.154, 0.496)],
    "w_sh": [(2.177, 0.850), (1.80, 0.868), (1.323, 0.875), (0.60, 0.868), (-0.60, 0.868),
             (-1.30, 0.878), (-1.38, 0.861), (-1.44, 0.855), (-1.62, 0.832), (-1.73, 0.805),
             (-1.86, 0.772), (-1.92, 0.734), (-1.975, 0.656), (-2.00, 0.594), (-2.154, 0.212)],
    "w_shelf": [(2.177, 0.800), (1.80, 0.825), (1.20, 0.815), (0.85, 0.805), (0.40, 0.783),
                (0.15, 0.780), (-0.35, 0.786), (-0.60, 0.770), (-0.85, 0.734), (-1.10, 0.710),
                (-1.30, 0.702), (-1.38, 0.703), (-1.62, 0.701), (-1.68, 0.714), (-1.77, 0.745),
                (-1.83, 0.747), (-1.92, 0.723), (-1.95, 0.701), (-2.00, 0.599), (-2.04, 0.503),
                (-2.154, 0.239)],
    "w_rail": [(2.177, 0.600), (1.10, 0.660), (0.60, 0.675), (0.40, 0.687), (0.15, 0.664),
               (-0.10, 0.645), (-0.60, 0.626), (-1.30, 0.579), (-1.44, 0.564), (-1.62, 0.517),
               (-1.68, 0.474), (-1.73, 0.438), (-1.86, 0.384), (-1.89, 0.379), (-1.92, 0.378),
               (-1.95, 0.402), (-2.02, 0.463), (-2.04, 0.479), (-2.055, 0.439), (-2.154, 0.166)],
    "w_sill": [(2.177, 0.830), (1.80, 0.840), (0.00, 0.845), (-1.30, 0.843), (-1.56, 0.849),
               (-1.68, 0.843), (-1.83, 0.796), (-1.95, 0.729), (-2.02, 0.662), (-2.04, 0.635),
               (-2.055, 0.589), (-2.154, 0.266)],
}

# Plan-view taper of the nose (fraction of the local widths).  It is flat
# across the number plate at bumper height and sweeps back towards the fog
# lamps; at headlamp height it is swept further (the J11's arrow-shaped
# front).  Measured from the two front three-quarter photos and the side
# silhouettes.
PLAN_FRONT_LOW = [(1.72, 1.0), (1.84, 0.995), (1.90, 0.983), (1.9619, 0.927), (2.015, 0.825),
                  (2.0504, 0.734), (2.1035, 0.508), (2.1416, 0.34)]
PLAN_FRONT_HIGH = [(1.66, 1.0), (1.78, 0.992), (1.88, 0.965), (1.9442, 0.915), (1.9885, 0.845),
                   (2.0327, 0.72), (2.077, 0.545), (2.1212, 0.36), (2.1416, 0.30)]


NOSE = 0.04          # the last 4 cm close the plan outline with a round nose


def plan_factor(x, high=False):
    """Plan-view taper that rounds the nose.  Within NOSE of each tip the
    width falls as sqrt(distance), so the outline meets the centre line
    square and the shell closes without a cap."""
    x = np.asarray(x, float)
    front = PLAN_FRONT_HIGH if high else PLAN_FRONT_LOW
    f = np.where(x > front[0][0], pchip(front, x), 1.0)
    nose = np.sqrt(np.clip((X_F - x) / NOSE, 0.0, 1.0)) * np.sqrt(np.clip((x - X_R) / NOSE, 0.0, 1.0))
    return f * nose


# ---------------------------------------------------------------------------
# Cross-sections
# ---------------------------------------------------------------------------
# The half section runs from the bottom centre, out along the floor, up the
# left side and over the roof to the top centre, through 10 control points.
# Consecutive control points are joined by centripetal Catmull-Rom segments;
# the spline is split at CREASES so the shoulder line stays crisp.  Behind the
# tail lamps (where the control point runs down across the bumper) the split
# fades out and the section is smooth there.
N_CTRL = 10
CREASES = (4,)                            # shoulder crease
CREASE_FADE = (-1.97, -1.88)              # smooth behind the first X, crisp in front of the second
SEGMENTS = [4, 3, 8, 12, 6, 7, 8, 8, 10]  # coarse sampling (camera fitting)


def crease_sharpness(x):
    """1 where the shoulder crease is crisp, 0 where the section is smooth."""
    t = np.clip((np.asarray(x, float) - CREASE_FADE[0]) / (CREASE_FADE[1] - CREASE_FADE[0]), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def controls(x):
    """Control points of the half sections at stations x: (K, 10, 2) (y, z)."""
    x = np.atleast_1d(np.asarray(x, float))
    v = {k: pchip(keys, x) for k, keys in P.items()}
    pf = plan_factor(x)                   # bumper-height rows
    ph = plan_factor(x, high=True)        # shoulder and above
    z_top = v["z_top"]
    z_shelf = np.minimum(v["z_shelf"], z_top + 0.005)
    z_sh = np.minimum(v["z_sh"], z_shelf - 0.01)
    z_bulge = np.minimum(v["z_bulge"], z_sh - 0.05)
    z_sill = np.minimum(v["z_sill"], z_bulge - 0.05)
    z_floor = np.minimum(v["z_floor"], z_sill)
    w_sill, w_bulge, w_sh = v["w_sill"] * pf, v["w_bulge"] * pf, v["w_sh"] * ph
    w_shelf = v["w_shelf"] * ph
    w_rail = np.minimum(v["w_rail"], v["w_shelf"] - 0.04) * ph
    h = z_top - z_shelf                   # greenhouse (or bonnet / bumper crown) height
    hp, hn = np.maximum(h, 0.0), np.minimum(h, 0.0)
    zero = np.zeros_like(x)
    pts = [
        (zero, z_floor),
        (w_sill - 0.14 * pf, z_floor),
        (w_sill, z_sill),
        (w_bulge, z_bulge),
        (w_sh, z_sh),                     # crease
        (w_shelf, z_shelf),
        # greenhouse arch; collapses to the bonnet / tailgate crown when h ~ 0
        (w_shelf - 0.30 * (w_shelf - w_rail), z_shelf + 0.34 * hp + 0.2 * hn),
        (w_rail, z_shelf + 0.80 * hp + 0.6 * hn),
        (w_rail * 0.70, z_shelf + 0.965 * hp + 0.9 * hn),
        (zero, z_top),
    ]
    return np.stack([np.stack(p, -1) for p in pts], 1)


def _pieces():
    """(start, end) control indices of the smooth spline pieces."""
    cuts = [0] + sorted(CREASES) + [N_CTRL - 1]
    return [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def cr_eval(ctrl, k, f, alpha=0.5, sharp=None):
    """Evaluate segment k (between control points k and k+1) at fraction f
    for every row of ctrl (K, 10, 2).  k, f: (K,) arrays.  Centripetal
    Catmull-Rom, reflected phantom points at piece ends (mirrored across
    the centre line at the section ends).  sharp (K,): how crisp the creases
    are per row (1 = split, 0 = smooth through; default 1)."""
    k = np.asarray(k, int)
    f = np.asarray(f, float)
    idx = np.arange(len(ctrl))
    start = np.zeros_like(k)
    end = np.zeros_like(k)
    for a, b in _pieces():
        m = (k >= a) & (k < b)
        start[m], end[m] = a, b
    p1 = ctrl[idx, k]
    p2 = ctrl[idx, k + 1]
    prev = ctrl[idx, np.maximum(k - 1, 0)]
    nxt = ctrl[idx, np.minimum(k + 2, N_CTRL - 1)]
    p0 = np.where((k > start)[:, None], prev, 2 * p1 - p2)
    p3 = np.where((k + 1 < end)[:, None], nxt, 2 * p2 - p1)
    # both ends lie on the centre line: mirror the neighbour so the section
    # crosses it square and the two halves meet without a crease
    mirror = np.array([-1.0, 1.0])
    p0 = np.where((k == 0)[:, None], p2 * mirror, p0)
    p3 = np.where((k + 1 == N_CTRL - 1)[:, None], p1 * mirror, p3)
    if sharp is not None:                 # blend the phantom points at a crease towards the neighbours
        s = np.broadcast_to(np.asarray(sharp, float), k.shape)[:, None]
        at_start = ((k == start) & np.isin(k, CREASES))[:, None]
        at_end = ((k + 1 == end) & np.isin(k + 1, CREASES))[:, None]
        p0 = np.where(at_start, s * p0 + (1.0 - s) * prev, p0)
        p3 = np.where(at_end, s * p3 + (1.0 - s) * nxt, p3)

    def knot(p, q):
        return np.maximum(np.linalg.norm(q - p, axis=-1), 1e-5) ** alpha

    t0 = np.zeros(len(k))
    t1 = t0 + knot(p0, p1)
    t2 = t1 + knot(p1, p2)
    t3 = t2 + knot(p2, p3)
    t = (t1 + (t2 - t1) * f)[:, None]
    t0, t1, t2, t3 = (a[:, None] for a in (t0, t1, t2, t3))
    a1 = (t1 - t) / (t1 - t0) * p0 + (t - t0) / (t1 - t0) * p1
    a2 = (t2 - t) / (t2 - t1) * p1 + (t - t1) / (t2 - t1) * p2
    a3 = (t3 - t) / (t3 - t2) * p2 + (t - t2) / (t3 - t2) * p3
    b1 = (t2 - t) / (t2 - t0) * a1 + (t - t0) / (t2 - t0) * a2
    b2 = (t3 - t) / (t3 - t1) * a2 + (t - t1) / (t3 - t1) * a3
    return (t2 - t) / (t2 - t1) * b1 + (t - t1) / (t2 - t1) * b2


class Ring:
    """Parametrisation along the half section: b in [0, n] where segment k
    spans counts[k] units (so integer b are the mesh rows)."""

    def __init__(self, counts):
        self.counts = np.asarray(counts, int)
        self.cum = np.concatenate([[0], np.cumsum(self.counts)])
        self.n = int(self.cum[-1])
        # rows that sit exactly on a control point (feature lines)
        self.ctrl_rows = self.cum.copy()

    def kf(self, b):
        b = np.clip(np.asarray(b, float), 0.0, self.n)
        k = np.clip(np.searchsorted(self.cum, b, side="right") - 1, 0, len(self.counts) - 1)
        return k, (b - self.cum[k]) / self.counts[k]


def fine_ring(ds=0.02):
    """Ring sampling with ~ds spacing on the visible sides (coarser floor)."""
    lengths = [0.707, 0.176, 0.386, 0.326, 0.121, 0.16, 0.23, 0.22, 0.475]  # at X = 0
    counts = [max(2, int(round(L / ds))) for L in lengths]
    counts[0] = max(3, int(round(lengths[0] / (4 * ds))))       # underbody floor
    return Ring(counts)


def section(x, ring=None):
    """Half cross-section at station x: (N, 2) array of (y, z) from the
    bottom centre up the left side and over the top to the top centre."""
    ring = ring or Ring(SEGMENTS)
    b = np.arange(ring.n + 1, dtype=float)
    k, f = ring.kf(b)
    ctrl = np.repeat(controls(x), len(b), axis=0)
    return cr_eval(ctrl, k, f, sharp=crease_sharpness(x))


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------
def stations(n_mid=90):
    """Coarse station X positions (camera fitting), denser at the ends and
    wheel arches."""
    xs = list(np.linspace(X_R, X_F, n_mid))
    for c, span, n in ((X_F, 0.45, 24), (X_R, 0.40, 22), (X_FA, 0.55, 18), (X_RA, 0.55, 18)):
        xs += list(np.linspace(c - span, c + span, n))
    xs = np.array(sorted(set(np.round(np.clip(xs, X_R, X_F), 5))))
    keep = [xs[0]]
    for x in xs[1:]:
        if x - keep[-1] > 0.006:
            keep.append(x)
    keep[-1] = X_F
    return np.array(keep)


def adaptive_stations(ds=0.02, n_ref=3000):
    """Stations spaced so that no point of the section moves more than ~ds
    between neighbours (dense where the nose and tail turn across X)."""
    ring = Ring(SEGMENTS)
    xs = np.linspace(X_R, X_F, n_ref)
    b = np.arange(ring.n + 1, dtype=float)
    k, f = ring.kf(b)
    ctrl = controls(xs)                                     # (n_ref, 10, 2)
    K = len(xs)
    yz = cr_eval(np.repeat(ctrl, len(b), 0), np.tile(k, K), np.tile(f, K),
                 sharp=np.repeat(crease_sharpness(xs), len(b))).reshape(K, len(b), 2)
    pts = np.concatenate([np.repeat(xs[:, None, None], len(b), 1), yz], -1)
    step = np.linalg.norm(np.diff(pts, axis=0), axis=-1).max(1)
    m = np.concatenate([[0.0], np.cumsum(step)])
    n = max(2, int(np.ceil(m[-1] / ds)))
    return np.interp(np.linspace(0.0, m[-1], n + 1), m, xs)


# ---------------------------------------------------------------------------
# Continuous surface S(a, b): a = station index, b = ring row
# ---------------------------------------------------------------------------
class Surface:
    def __init__(self, ds=0.02):
        self.ds = ds
        self.ring = fine_ring(ds)
        self.st = adaptive_stations(ds)
        self.na = len(self.st) - 1            # a in [0, na]
        self.nb = self.ring.n                 # b in [0, nb]

    def x_of(self, a):
        return np.interp(a, np.arange(self.na + 1), self.st)

    def eval(self, a, b, side=1.0):
        """Points (K, 3) for parameter arrays a, b (left side; side=-1 mirrors)."""
        a = np.atleast_1d(np.asarray(a, float))
        b = np.atleast_1d(np.asarray(b, float))
        a, b = np.broadcast_arrays(a, b)
        x = self.x_of(a.ravel())
        k, f = self.ring.kf(b.ravel())
        yz = cr_eval(controls(x), k, f, sharp=crease_sharpness(x))
        return np.column_stack([x, side * yz[:, 0], yz[:, 1]])

    def normal(self, a, b, side=1.0, toward=None, h=0.01):
        """Outward unit normals.  toward=(ac, bc): take one-sided derivatives
        on the side of that parameter point (for creases / face corners)."""
        a = np.atleast_1d(np.asarray(a, float)).ravel()
        b = np.atleast_1d(np.asarray(b, float)).ravel()
        if toward is not None:
            ac, bc = toward
            a = a + 0.04 * (np.asarray(ac, float).ravel() - a)
            b = b + 0.04 * (np.asarray(bc, float).ravel() - b)
        a0 = np.clip(a - h, 0.0, self.na)
        a1 = np.clip(a + h, 0.0, self.na)
        b0 = np.clip(b - h, 0.0, self.nb)
        b1 = np.clip(b + h, 0.0, self.nb)
        da = self.eval(a1, b, side) - self.eval(a0, b, side)
        db = self.eval(a, b1, side) - self.eval(a, b0, side)
        n = np.cross(db, da) if side > 0 else np.cross(da, db)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.maximum(ln, 1e-12)

    def grid(self, side=1.0):
        """All mesh-grid points (na+1, nb+1, 3)."""
        A, B = np.meshgrid(np.arange(self.na + 1.0), np.arange(self.nb + 1.0), indexing="ij")
        return self.eval(A, B, side).reshape(self.na + 1, self.nb + 1, 3)


# ---------------------------------------------------------------------------
# Coarse rings (camera fitting and quick checks)
# ---------------------------------------------------------------------------
def rings():
    """Closed rings (M, 2N-2, 3): full cross-sections (both sides)."""
    out = []
    for x in stations():
        half = section(x)
        right = half[::-1][1:-1] * np.array([-1.0, 1.0])       # mirror, skip shared ends
        loop = np.vstack([half, right])                          # bottom->left->top->right
        out.append(np.column_stack([np.full(len(loop), x), loop[:, 0], loop[:, 1]]))
    return np.array(out)


def silhouette_points(n=400):
    """Side-view outline (x, z) of the shell for quick checks."""
    xs = np.linspace(X_R, X_F, n)
    top = [section(x)[:, 1].max() for x in xs]
    bot = [section(x)[:, 1].min() for x in xs]
    return xs, np.array(top), np.array(bot)
