"""Generate Calorie Ledger app icons (dark gradient + gauge/progress mark).

Outputs into web/icons/: icon-192.png, icon-512.png, icon-512-maskable.png,
apple-touch-icon.png (180x180). Run: python tools/make_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
BASE = 1024
SS = 4  # supersample factor

BG_TOP = (14, 21, 38)
BG_BOTTOM = (27, 43, 75)
GLOW = (56, 189, 248)
ARC_FROM = (52, 211, 153)   # green
ARC_TO = (56, 189, 248)     # sky
TRACK = (30, 42, 74)
NEEDLE = (231, 237, 247)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def base_image(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        row = lerp(BG_TOP, BG_BOTTOM, y / (size - 1))
        for x in range(size):
            px[x, y] = row
    # soft diagonal glow top-right
    glow = Image.new("L", (size, size), 0)
    gd = ImageDraw.Draw(glow)
    gx, gy, gr = int(size * 0.82), int(size * 0.16), int(size * 0.55)
    for r in range(gr, 0, -8):
        alpha = int(26 * (1 - r / gr))
        gd.ellipse([gx - r, gy - r, gx + r, gy + r], fill=alpha)
    tint = Image.new("RGB", (size, size), GLOW)
    img = Image.composite(tint, img, glow)
    return img


def draw_mark(img: Image.Image, scale: float = 1.0) -> None:
    """Gauge ring (progress arc + needle) centred, sized by `scale`."""
    size = img.width
    d = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2 + size * 0.02
    radius = size * 0.30 * scale
    stroke = int(size * 0.075 * scale)
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    gap_half = 38  # degrees of opening at the bottom (like a dial/scale)
    start_deg = 90 + gap_half
    end_deg = 90 - gap_half + 360

    d.arc(bbox, start=start_deg, end=end_deg, fill=TRACK, width=stroke)

    # progress arc ~72% of the dial, colour-interpolated in segments
    sweep = (end_deg - start_deg) * 0.72
    steps = 90
    for i in range(steps):
        t0 = i / steps
        t1 = (i + 1) / steps
        col = lerp(ARC_FROM, ARC_TO, t0)
        d.arc(bbox, start=start_deg + sweep * t0, end=start_deg + sweep * t1 + 0.8,
              fill=col, width=stroke)
    # round caps
    for ang, col in ((start_deg, ARC_FROM), (start_deg + sweep, ARC_TO)):
        rad = math.radians(ang)
        ex = cx + radius * math.cos(rad)
        ey = cy + radius * math.sin(rad)
        d.ellipse([ex - stroke / 2, ey - stroke / 2, ex + stroke / 2, ey + stroke / 2], fill=col)

    # needle pointing at the arc tip
    tip_ang = math.radians(start_deg + sweep)
    nx = cx + radius * 0.62 * math.cos(tip_ang)
    ny = cy + radius * 0.62 * math.sin(tip_ang)
    d.line([cx, cy, nx, ny], fill=NEEDLE, width=int(size * 0.030 * scale))
    hub = size * 0.045 * scale
    d.ellipse([cx - hub, cy - hub, cx + hub, cy + hub], fill=NEEDLE)
    hub2 = hub * 0.45
    d.ellipse([cx - hub2, cy - hub2, cx + hub2, cy + hub2], fill=lerp(BG_TOP, BG_BOTTOM, 0.5))

    # tick marks on the open gap side removed for cleanliness; add trend dot:
    dot_ang = math.radians(start_deg + sweep + 26)
    dx = cx + radius * math.cos(dot_ang)
    dy = cy + radius * math.sin(dot_ang)
    r = stroke * 0.28
    d.ellipse([dx - r, dy - r, dx + r, dy + r], fill=(143, 160, 191))


def rounded_mask(size: int, radius_frac: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_frac)
    d.rounded_rectangle([0, 0, size, size], radius=r, fill=255)
    return mask


def make(size: int, out: str, *, mark_scale: float = 1.0, rounded: float | None = None) -> None:
    big = base_image(size * SS)
    draw_mark(big, scale=mark_scale)
    img = big.resize((size, size), Image.LANCZOS)
    if rounded:
        mask = rounded_mask(size, rounded)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(img, (0, 0), mask)
        canvas.save(OUT / out)
    else:
        img.save(OUT / out)
    print(f"wrote {out} ({size}x{size})")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make(512, "icon-512.png")
    make(192, "icon-192.png")
    make(512, "icon-512-maskable.png", mark_scale=0.78)  # safe zone for maskable
    make(180, "apple-touch-icon.png")


if __name__ == "__main__":
    main()
