"""Textures for the Qashqai, generated with numpy: number plates, the
honeycomb grille mesh and a fine grain for the black plastic trim."""
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


def plates(text):
    return plate_texture.plate_image(text, False), plate_texture.plate_image(text, True)
