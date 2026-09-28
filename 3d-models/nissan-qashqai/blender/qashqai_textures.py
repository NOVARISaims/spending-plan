"""Textures for the Qashqai, generated with numpy: number plates, the
honeycomb grille mesh, a fine grain for the black plastic trim and the seat
cloth.  (The lettered interior panels are drawn by make_interior_textures.)"""
import math

import numpy as np

import plate_texture


def honeycomb(size=512, cells=7):
    """Tileable hexagonal mesh (pointy-top) with `cells` hexes across (7
    across and 8 rows keep the cells regular on a square tile).
    Returns base colour (H, W, 3), roughness (H, W) and an OpenGL normal
    map (H, W, 3)."""
    h = size
    w = size
    # hex lattice: horizontal pitch p, vertical pitch p*sqrt(3)/2; make it tile
    p = w / cells
    rows = int(round(h / (p * math.sqrt(3) / 2)))
    rows += rows % 2
    vp = h / rows
    ys, xs = np.mgrid[0:h, 0:w].astype(float) + 0.5
    best = np.full((h, w), np.inf)
    for r in range(-1, rows + 2):
        cy = r * vp
        off = (p / 2) if (r % 2) else 0.0
        for c in range(-1, cells + 2):
            cx = c * p + off
            dx = np.minimum(np.abs(xs - cx), w - np.abs(xs - cx))
            dy = np.minimum(np.abs(ys - cy), h - np.abs(ys - cy))
            # hex norm of a pointy-top cell: vertical edges at |dx| = p/2
            d = np.maximum(dx, dx / 2 + dy * math.sqrt(3) / 2)
            best = np.minimum(best, d)
    # best = hex-metric distance to the nearest cell centre; ribs near p/2
    rib_half = p * 0.16
    edge = p / 2
    t = np.clip((best - (edge - rib_half)) / (rib_half * 1.2), 0.0, 1.0)   # 0 hole .. 1 rib
    height = t ** 1.5
    base = np.stack([0.006 + 0.022 * height] * 3, -1)
    rough = 0.55 - 0.25 * height
    gy, gx = np.gradient(height * 6.0)
    n = np.stack([-gx, gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = n * 0.5 + 0.5
    return base, rough, normal


def grain(size=512, seed=7):
    """Fine plastic grain normal map (tileable, OpenGL)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(size)
    fx, fy = np.meshgrid(f, f)
    r = np.sqrt(fx ** 2 + fy ** 2)
    spec = np.exp(-(r / 0.08) ** 2) * (r > 0)
    noise = np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size))) * spec).real
    noise /= np.abs(noise).max()
    gy, gx = np.gradient(noise * 2.0)
    n = np.stack([-gx, gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def seat_fabric(size=256, dots=16, checks=2):
    """Tileable seat cloth from the owner's photos: a fine two-tone knit (a
    light fleck on a charcoal ground, `dots` per tile) whose fleck brightness
    steps in a larger checker (`checks` per tile).  Returns base colour
    (H, W, 3) and an OpenGL normal map (H, W, 3) for the knit relief."""
    ys, xs = np.mgrid[0:size, 0:size].astype(float) + 0.5
    u, v = xs / size, ys / size
    # knit: rows of small raised loops, offset every other row
    pu = u * dots
    pv = v * dots
    row = np.floor(pv)
    pu = pu + 0.5 * (row % 2)
    fu, fv = pu - np.floor(pu) - 0.5, pv - row - 0.5
    loop = np.clip(1.0 - np.sqrt((fu / 0.42) ** 2 + (fv / 0.34) ** 2), 0.0, 1.0)
    check = ((np.floor(u * checks) + np.floor(v * checks)) % 2).astype(float)
    fleck = loop ** 1.2 * (0.6 + 0.4 * check)
    base = np.stack([0.020 + 0.26 * fleck] * 3, -1)
    base[..., 2] += 0.012 * fleck                      # the grey has a faint blue cast
    gy, gx = np.gradient(loop * 3.0)
    n = np.stack([-gx, gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return base, n * 0.5 + 0.5


def plates(text):
    return plate_texture.plate_image(text, False), plate_texture.plate_image(text, True)
