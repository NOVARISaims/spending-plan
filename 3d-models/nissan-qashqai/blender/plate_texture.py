"""UK number plate textures (numpy only, no fonts needed).

Characters follow the proportions of the mandatory Charles Wright 2001
typeface: 79 mm tall, 50 mm wide (the figure 1 is narrower), 14 mm stroke,
11 mm between characters and 33 mm between the two groups, on a
520 x 111 mm plate.  Glyphs are polygons in millimetres (x right, y up,
origin at the bottom-left of the 50 x 79 character cell).
"""
import math

import numpy as np

PLATE_MM = (520.0, 111.0)
CHAR_H = 79.0
STROKE = 14.0
SPACE = 11.0
GROUP_GAP = 33.0
FRONT_BG = (0.93, 0.93, 0.91)          # reflective white (linear-ish sRGB values 0..1)
REAR_BG = (0.99, 0.80, 0.02)           # UK plate yellow
INK = (0.03, 0.03, 0.03)


def _arc(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]


def glyph(ch):
    """List of polygons; the first is the outline, the rest are holes."""
    s = STROKE
    if ch == "D":
        R = 25.0
        outer = [(0, 0), (50 - R, 0)] + _arc(50 - R, R, R, -90, 0)[1:] + \
            _arc(50 - R, 79 - R, R, 0, 90)[1:] + [(0, 79)]
        r = R - s
        inner = [(s, s), (50 - R, s)] + _arc(50 - R, R, r, -90, 0)[1:] + \
            _arc(50 - R, 79 - R, r, 0, 90)[1:] + [(s, 79 - s)]
        return [outer, inner]
    if ch == "E":
        m = 79 / 2 - s / 2
        return [[(0, 0), (50, 0), (50, s), (s, s), (s, m), (44, m), (44, m + s), (s, m + s),
                 (s, 79 - s), (50, 79 - s), (50, 79), (0, 79)]]
    if ch == "1":
        return [[(16, 0), (30, 0), (30, 79), (19, 79), (2, 64), (2, 49), (16, 61)]]
    if ch == "7":
        return [[(0, 79), (50, 79), (50, 67), (24, 0), (9, 0), (34.5, 65), (0, 65)]]
    if ch == "Y":
        return [[(0, 79), (15.5, 79), (25, 55), (34.5, 79), (50, 79), (32, 36), (32, 0), (18, 0),
                 (18, 36)]]
    if ch == "A":
        return [[(0, 0), (14.5, 0), (18.3, 17), (31.7, 17), (35.5, 0), (50, 0), (32.3, 79),
                 (17.7, 79)],
                [(21.2, 30), (28.8, 30), (25, 48)]]
    if ch == "U":
        R = 25.0
        return [[(0, 79), (0, R)] + _arc(25, R, R, 180, 360)[1:] + [(50, 79), (50 - s, 79)] +
                _arc(25, R, R - s, 360, 180)[:-1] + [(s, R), (s, 79)]]
    raise ValueError("no glyph for %r" % ch)


def glyph_width(ch):
    return 30.0 if ch == "1" else 50.0


def layout(text):
    """Glyph polygons placed on the plate (mm, origin bottom-left)."""
    groups = text.split()
    widths = [sum(glyph_width(c) for c in g) + SPACE * (len(g) - 1) for g in groups]
    total = sum(widths) + GROUP_GAP * (len(groups) - 1)
    x = (PLATE_MM[0] - total) / 2.0
    y = (PLATE_MM[1] - CHAR_H) / 2.0
    polys = []
    for gi, g in enumerate(groups):
        for ci, c in enumerate(g):
            for k, poly in enumerate(glyph(c)):
                polys.append((k > 0, [(x + px, y + py) for px, py in poly]))
            x += glyph_width(c) + (SPACE if ci < len(g) - 1 else 0.0)
        x += GROUP_GAP
    return polys


def _inside(px, py, poly):
    poly = np.asarray(poly, float)
    inside = np.zeros(px.shape, bool)
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        cond = (yi > py) != (yj > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (xj - xi) * (py - yi) / (yj - yi) + xi
        inside ^= cond & (px < xint)
        j = i
    return inside


def plate_image(text, rear, px_per_mm=4, ss=3):
    """(H, W, 3) float image, row 0 at the top."""
    W = int(PLATE_MM[0] * px_per_mm)
    H = int(PLATE_MM[1] * px_per_mm)
    xs = (np.arange(W * ss) + 0.5) / (px_per_mm * ss)
    ys = PLATE_MM[1] - (np.arange(H * ss) + 0.5) / (px_per_mm * ss)
    X, Y = np.meshgrid(xs, ys)
    ink = np.zeros(X.shape, bool)
    for hole, poly in layout(text):
        p = np.asarray(poly)
        x0, y0 = p.min(0)
        x1, y1 = p.max(0)
        m = (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
        ins = np.zeros(X.shape, bool)
        ins[m] = _inside(X[m], Y[m], poly)
        ink = ink & ~ins if hole else ink | ins
    cov = ink.reshape(H, ss, W, ss).mean(axis=(1, 3))
    bg = np.array(REAR_BG if rear else FRONT_BG)
    img = bg[None, None, :] * (1 - cov[..., None]) + np.array(INK)[None, None, :] * cov[..., None]
    # faint inner border line like real plates
    return img


if __name__ == "__main__":
    import sys
    from PIL import Image
    for rear in (False, True):
        a = plate_image("DE17 YAU", rear)
        Image.fromarray((a * 255).astype(np.uint8)).save(sys.argv[1] + ("_rear.png" if rear else "_front.png"))
