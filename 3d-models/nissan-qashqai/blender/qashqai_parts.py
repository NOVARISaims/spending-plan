"""Procedural parts of the Qashqai that are not cut from the body shell:
wheels, wheel-well liners, mirrors, handles, badges (the Nissan roundel and
the QASHQAI script), number plates and fog lamps.  The interior is in
qashqai_interior."""
import math

import bpy  # noqa: F401  (must precede bmesh / mathutils with the PyPI bpy module)
import numpy as np
from mathutils import Matrix, Vector

import mesh_kit as mk
import qashqai_body as qb
import qashqai_features as F

# ---------------------------------------------------------------------------
# Wheel: 17 x 7J five twin-spoke alloy on a 215/60 R17 tyre.  Local frame:
# centre at the origin, axis along +Y (the outer face looks towards +Y).
# ---------------------------------------------------------------------------
TYRE_R = 0.3455
BEAD_R = 0.2159            # 17 in / 2
RIM_FACE = 0.096           # outer lip height above the centre plane


def _tyre(kit):
    grooves = (-0.058, -0.022, 0.022, 0.058)
    prof = [(0.2215, -0.092), (0.2350, -0.1000), (0.2600, -0.1058), (0.2900, -0.1075),
            (0.3150, -0.1030), (0.3320, -0.0950), (0.3410, -0.0850), (0.3450, -0.0720)]
    for g in grooves:
        prof += [(TYRE_R, g - 0.0065), (TYRE_R - 0.008, g - 0.0050), (TYRE_R - 0.008, g + 0.0050),
                 (TYRE_R, g + 0.0065)]
    prof += [(0.3450, 0.0720), (0.3410, 0.0850), (0.3320, 0.0950), (0.3150, 0.1030),
             (0.2900, 0.1075), (0.2600, 0.1058), (0.2350, 0.1000), (0.2215, 0.0920)]
    # insert intermediate tread points so the groove walls are the only sharp edges
    kit.revolve(prof, "tyre", seg=96)
    # inner closure (hidden inside the rim)
    kit.revolve([(0.2215, 0.0920), (0.2150, 0.0600), (0.2150, -0.0600), (0.2215, -0.0920)], "tyre", seg=96)


def _rim_barrel(kit):
    # outer lip (visible ring around the spokes)
    lip = [(0.2050, 0.0880), (0.2100, 0.0935), (0.2160, RIM_FACE), (0.2230, RIM_FACE + 0.0008),
           (0.2290, 0.0935), (0.2300, 0.0880), (0.2265, 0.0830)]
    kit.revolve(lip[::-1], "alloy", seg=96)
    # inner barrel, seen through the spokes
    kit.revolve([(0.2050, 0.0880), (0.2030, 0.0600), (0.1980, 0.0200), (0.1980, -0.0850),
                 (0.2150, -0.0900)], "wheel_inner", seg=96)


# spoke pairs (owner's photo): two broad flat spokes per pair, joined at the
# root and split by a slit that opens near the lug nuts and widens to ~2 cm
SPOKE_R = [0.060, 0.085, 0.100, 0.150, 0.2075]
SPOKE_OFFSET = [0.0075, 0.0115, 0.0145, 0.0200, 0.0265]    # spoke centre from the pair's axis
SPOKE_W = [0.030, 0.025, 0.022, 0.027, 0.034]


def _spokes(kit):
    r0, r1 = SPOKE_R[0], SPOKE_R[-1]
    n_s = 11
    for k in range(5):
        base = math.radians(90.0 + 72.0 * k)
        for sgn in (-1.0, 1.0):
            loops = []
            for i in range(n_s):
                t = i / (n_s - 1)
                r = r0 + (r1 - r0) * t
                phi = math.asin(float(np.interp(r, SPOKE_R, SPOKE_OFFSET)) / r) * sgn
                w = float(np.interp(r, SPOKE_R, SPOKE_W))
                hf = 0.066 + 0.026 * t ** 1.15                    # dished face
                hb = hf - 0.030 + 0.008 * t
                a = base + phi
                c = np.array([math.cos(a), math.sin(a)])
                s = np.array([-math.sin(a), math.cos(a)])
                pts2 = [(-w / 2, hb), (-w / 2, hf - 0.0025), (-w * 0.42, hf), (w * 0.42, hf),
                        (w / 2, hf - 0.0025), (w / 2, hb)]
                loop = []
                for sx, hh in pts2:
                    q = c * r + s * sx
                    loop.append(Vector((q[0], hh, q[1])))
                loops.append(loop)
            kit.loft(loops, "alloy", closed=True, caps=False)


def _hub(kit):
    # centre boss
    kit.revolve([(0.0, 0.0640), (0.0300, 0.0640), (0.0620, 0.0620), (0.0760, 0.0560),
                 (0.0780, 0.0400)][::-1], "alloy", seg=64)
    # centre cap: black with a chrome ring
    kit.revolve([(0.0000, 0.0735), (0.0190, 0.0730), (0.0255, 0.0700), (0.0275, 0.0640)][::-1],
                "cap_black", seg=48)
    kit.revolve([(0.0255, 0.0715), (0.0300, 0.0700), (0.0315, 0.0650)][::-1], "chrome", seg=48)
    # five lug nuts on a 114.3 mm PCD, between the spoke pairs
    for k in range(5):
        a = math.radians(90.0 + 36.0 + 72.0 * k)
        c = (0.05715 * math.cos(a), 0.0, 0.05715 * math.sin(a))
        kit.revolve([(0.0, 0.0775), (0.0060, 0.0770), (0.0090, 0.0740), (0.0092, 0.0600)][::-1],
                    "lug", seg=6, center=c)
        # recess around each nut
        kit.revolve([(0.0120, 0.0610), (0.0135, 0.0625)][::-1], "wheel_inner", seg=24, center=c)


def _brakes(kit):
    # ventilated disc 296 mm, hat, and the dust shield behind
    kit.revolve([(0.080, -0.014), (0.148, -0.014), (0.1485, 0.000), (0.148, 0.012), (0.080, 0.012)],
                "brake_disc", seg=72)
    kit.revolve([(0.050, 0.036), (0.080, 0.034), (0.082, 0.012)][::-1], "brake_hat", seg=48)
    kit.disc(0.205, -0.070, "wheel_inner", seg=64, normal_sign=1.0)


def build_wheel(name="SM_Qashqai_Wheel"):
    kit = mk.Kit(name)
    _tyre(kit)
    _rim_barrel(kit)
    _spokes(kit)
    _hub(kit)
    _brakes(kit)
    return kit


def build_caliper(name="Caliper"):
    """Brake caliper (does not rotate): at the rear of the disc."""
    kit = mk.Kit(name)
    for side in (1,):
        a0, a1 = math.radians(120), math.radians(165)
        prof = [(0.118, -0.030), (0.158, -0.030), (0.158, 0.028), (0.118, 0.028)]
        kit.revolve(prof[::-1], "caliper", seg=10, closed=True, a0=a0, a1=a1)
    return kit


# ---------------------------------------------------------------------------
# Wheel-well liners (left side; mirrored for the right)
# ---------------------------------------------------------------------------
def build_liner(kit, arch_pts, y_outer, which, side=1.0):
    """Tunnel from the arch opening (3D points on the shell, bottom to bottom
    over the top) to an inner wall at LINER_Y."""
    xc = qb.X_FA if which == "front" else qb.X_RA
    pts = np.asarray(arch_pts, float)
    outer, inner = [], []
    for p in pts:
        d = np.array([p[0] - xc, p[2] - F.WHEEL_Z])
        d /= max(np.linalg.norm(d), 1e-9)
        q = np.array([p[0] + d[0] * 0.012, p[2] + d[1] * 0.012])      # tuck under the moulding
        outer.append((q[0], (abs(p[1]) - 0.010) * side, q[1]))
        inner.append((q[0], F.LINER_Y * side, q[1]))
    n = len(pts)
    verts = outer + inner
    faces = [[i, i + 1, n + i + 1, n + i] for i in range(n - 1)]
    if side < 0:
        faces = [f[::-1] for f in faces]
    kit.add(verts, faces, "liner", sharp=False)
    # inner wall: arch shape closed along the floor
    wall = [(p[0], p[2]) for p in inner] + [(inner[-1][0], 0.20), (inner[0][0], 0.20)]
    frame = (np.array([0.0, F.LINER_Y * side, 0.0]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0]),
             np.array([0.0, side, 0.0]))
    kit.cap(np.array(wall), 0.0, frame, "liner", up=False)


# ---------------------------------------------------------------------------
# Door mirror (left; mirrored for the right)
# ---------------------------------------------------------------------------
def build_mirror(kit, side=1.0):
    """Body-coloured cap with an LED indicator, black base on the door sail."""
    x0, z0 = F.MIRROR_BASE
    y0 = 0.795
    # housing: superellipse sections along Y (outwards)
    secs = []
    ys = np.linspace(0.86, 1.032, 9)
    for k, y in enumerate(ys):
        t = (y - ys[0]) / (ys[-1] - ys[0])
        L = 0.172 - 0.034 * t ** 2                   # fore-aft length
        H = 0.136 - 0.040 * t ** 2.2                 # height
        xc = x0 - 0.005 - 0.030 * t                  # sweeps back towards the tip
        zc = z0 + 0.055 + 0.006 * t
        if k == len(ys) - 1:
            L, H = L * 0.55, H * 0.6
        ring = []
        for a in np.linspace(0, 2 * np.pi, 28, endpoint=False):
            ca, sa = math.cos(a), math.sin(a)
            ex = 3.2 if ca > 0 else 2.4                # rounder at the front
            ring.append(Vector((xc + L / 2 * np.sign(ca) * abs(ca) ** (2 / ex), y * side,
                                zc + H / 2 * np.sign(sa) * abs(sa) ** (2 / 3.0))))
        secs.append(ring if side > 0 else ring[::-1])
    kit.loft(secs, "paint", closed=True, caps=True)
    # mirror glass on the rear face
    g = []
    for a in np.linspace(0, 2 * np.pi, 28, endpoint=False):
        ca, sa = math.cos(a), math.sin(a)
        yy = 0.945 + 0.078 * np.sign(ca) * abs(ca) ** 0.8
        zz = z0 + 0.057 + 0.047 * np.sign(sa) * abs(sa) ** 0.7
        g.append(Vector((x0 - 0.080 - 0.018 * (yy - 0.87) / 0.15, yy * side, zz)))
    kit.loft([g, [Vector((p.x + 0.004, p.y, p.z)) for p in g]], "mirror_glass", closed=True, caps=True)
    # indicator strip along the lower front edge
    path, ups = [], []
    for t in np.linspace(0.0, 1.0, 10):
        y = 0.90 + 0.12 * t
        path.append((x0 + 0.040 - 0.035 * t, y * side, z0 + 0.012 + 0.012 * t))
        ups.append((0.6, 0.0, 0.8))
    kit.sweep([(-0.006, -0.004), (0.006, -0.004), (0.006, 0.004), (-0.006, 0.004)], path, ups, "indicator")
    # base / arm
    kit.box((x0 - 0.01, (y0 + 0.045) * side, z0 + 0.030), (0.12, 0.09, 0.05), "black_plastic")


# ---------------------------------------------------------------------------
# Door handle (body-coloured pull), given the shell point and normal
# ---------------------------------------------------------------------------
def build_handle(kit, P, N, side=1.0):
    t = np.array([1.0, 0.0, 0.0])
    n = np.asarray(N, float)
    n /= np.linalg.norm(n)
    up = np.cross(n, t) * (1 if side > 0 else -1)
    up /= np.linalg.norm(up)
    path, ups = [], []
    L = F.HANDLE_LEN
    for s in np.linspace(-0.5, 0.5, 13):
        bow = 0.018 * (1 - (2 * s) ** 2) ** 0.5            # stands off the door in the middle
        path.append(np.asarray(P) + t * s * L + n * (0.004 + bow))
        ups.append(up)
    sec = [(0.0, -F.HANDLE_H / 2), (0.009, -0.013), (0.012, 0.0), (0.009, 0.013), (0.0, F.HANDLE_H / 2),
           (-0.006, 0.010), (-0.006, -0.010)]
    if side < 0:
        sec = [(-sx, sy) for sx, sy in sec][::-1]
    kit.sweep(sec[::-1], path, ups, "paint")


# ---------------------------------------------------------------------------
# Badges
# ---------------------------------------------------------------------------
def build_logo(kit, frame, d, depth=0.010):
    """Nissan roundel: chrome ring with a horizontal bar."""
    o, u, v, n = frame
    ring_o, ring_i = d / 2, d / 2 - d * 0.085
    outer = mk.circle2d(ring_o, 48)
    inner = mk.circle2d(ring_i, 48)
    # ring as a tube-ish prism: outer wall + inner wall + face
    kit.prism(outer, 0.0, depth, frame, "chrome", cap0=False, cap1=False, sharp=False)
    ki = len(inner)
    wall = [o + u * p[0] + v * p[1] for p in inner] + [o + u * p[0] + v * p[1] + n * depth for p in inner]
    kit.add(wall, [[ki + i, ki + (i + 1) % ki, (i + 1) % ki, i] for i in range(ki)], "chrome", sharp=False)
    ring_v = [o + u * p[0] + v * p[1] + n * depth for p in outer] + [o + u * p[0] + v * p[1] + n * depth for p in inner]
    faces = [[i, (i + 1) % 48, 48 + (i + 1) % 48, 48 + i] for i in range(48)]
    kit.add(ring_v, faces, "chrome", sharp=True)
    # bar across the middle
    bw, bh = d * 1.02, d * 0.22
    kit.prism(mk.rounded_rect2d(bw, bh, bh * 0.2), 0.0, depth * 1.2, frame, "chrome")
    kit.prism(mk.rounded_rect2d(bw * 0.9, bh * 0.62, bh * 0.1), depth * 1.2, depth * 1.35, frame, "badge_dark")


def text_mesh(text, cap_height, depth, spacing=1.0):
    """Extruded letters from Blender's built-in font: vertices (text x to the
    right, y up, z out of the face from 0 to depth) and faces."""
    cu = bpy.data.curves.new("_badge", "FONT")
    cu.body = text
    cu.size = cap_height / 0.72
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = depth / 2
    cu.space_character = spacing
    ob = bpy.data.objects.new("_badge", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    V = np.array([v.co[:] for v in me.vertices]) + np.array([0.0, 0.0, depth / 2])
    faces = [list(p.vertices) for p in me.polygons]
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    bpy.context.view_layer.update()
    return V, faces


# ---------------------------------------------------------------------------
# Number plates (UV mapped to the plate texture)
# ---------------------------------------------------------------------------
def build_plate(kit, frame, mat, w=0.520, h=0.111, t=0.004, r=0.008):
    outline = mk.rounded_rect2d(w, h, r, 4)
    kit.prism(outline, -t, 0.0, frame, "plate_edge", cap1=False)
    kit.cap(outline, 0.0, frame, mat, up=True, uv=lambda p: ((p[0] + w / 2) / w, (p[1] + h / 2) / h))


# ---------------------------------------------------------------------------
# Fog lamp: chrome oval ring, clear lens, dark reflector
# ---------------------------------------------------------------------------
def build_fog(kit, c, n, w, h, ring):
    frame = mk.frame_from(c, n)
    o, u, v, nn = frame
    t = np.linspace(0, 2 * np.pi, 40, endpoint=False)

    def ell(sx, sy, z):
        return [o + u * (sx * math.cos(a)) + v * (sy * math.sin(a)) + nn * z for a in t]
    rx, ry = w / 2, h / 2
    ri, qi = rx - ring - 0.002, ry - ring - 0.002
    # chrome bezel: outer skirt, flat face, inner return
    rings = [ell(rx + 0.004, ry + 0.004, -0.002), ell(rx, ry, 0.006), ell(rx - ring, ry - ring, 0.006),
             ell(ri, qi, -0.004)]
    for a_, b_ in zip(rings[:-1], rings[1:]):
        kit.loft([a_, b_], "chrome", closed=True, caps=False)
    # slightly domed clear lens, dark reflector bowl behind it
    dome = [ell(ri, qi, -0.004), ell(ri * 0.75, qi * 0.75, -0.001), ell(ri * 0.4, qi * 0.4, 0.001)]
    kit.loft(dome, "lens_clear", closed=True, caps=False)
    kit.fan(dome[-1], o + nn * 0.0015, "lens_clear")
    # dark housing with a small chrome reflector cup in the middle
    kit.loft([ell(ri, qi, -0.040), ell(ri, qi, -0.004)], "lamp_black", closed=True, caps=True)
    cup = [ell(ri * 0.55, qi * 0.75, -0.012), ell(ri * 0.35, qi * 0.5, -0.026), ell(ri * 0.1, qi * 0.15, -0.032)]
    kit.loft(cup, "lamp_chrome", closed=True, caps=False)
