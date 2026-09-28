"""Draw the interior textures that carry lettering, from the owner's photos of
the car (Acenta: CD/radio unit, dual-zone climate control, analogue dials).

    assets/T_Interior_Stack.png     centre stack face: audio unit, climate
                                    control, airbag lamp, USB / AUX sockets
    assets/T_Interior_Dials.png     instrument cluster: rev counter, speedo
                                    (mph), centre display
    assets/T_Interior_Switches.png  steering-wheel switch pads (audio on the
                                    left spoke, cruise control on the right)

The build script only copies these PNGs, so Blender doesn't need Pillow.
Rerun this after changing a layout:
    python make_interior_textures.py          (needs Pillow)

The UV layouts that the build script uses are given in millimetres here
(STACK_MM, DIALS_MM, SWITCHES_MM), so geometry and texture stay in step.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")

STACK_MM = (250.0, 310.0)        # width, height of the stack face
DIALS_MM = (320.0, 125.0)        # instrument cluster face
SWITCHES_MM = (140.0, 70.0)      # both switch pads side by side (70 x 70 each)
PX = 4.0                         # pixels per millimetre

FONT_FILES = ["DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf"]
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
             "/usr/share/fonts/truetype/freefont", "/Library/Fonts", "C:/Windows/Fonts"]

INK = (226, 228, 232)            # white-ish legends
DIM = (140, 144, 150)
BLACK = (8, 8, 9)
PANEL = (16, 16, 18)
BUTTON = (30, 31, 34)
CHROME = (205, 208, 212)
AMBER = (255, 150, 40)


def font(size_mm, bold=True):
    size = max(8, int(round(size_mm * PX)))
    for d in FONT_DIRS:
        for f in FONT_FILES if bold else FONT_FILES[1:]:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def mm(*v):
    return [x * PX for x in v]


def rrect(d, x0, y0, x1, y1, r, fill=None, outline=None, width=1.0):
    d.rounded_rectangle(mm(x0, y0, x1, y1), radius=r * PX, fill=fill, outline=outline,
                        width=max(1, int(width * PX)))


def text(d, x, y, s, size=3.2, fill=INK, anchor="mm", bold=True):
    d.text((x * PX, y * PX), s, font=font(size, bold), fill=fill, anchor=anchor)


def button(d, x0, y0, x1, y1, label=None, size=3.0, icon=None):
    rrect(d, x0, y0, x1, y1, 1.6, fill=BUTTON, outline=(58, 60, 64), width=0.35)
    # soft highlight along the top edge
    d.line(mm(x0 + 1.5, y0 + 0.8, x1 - 1.5, y0 + 0.8), fill=(70, 72, 77), width=int(0.5 * PX))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if label:
        text(d, cx, cy, label, size)
    if icon:
        icon(d, cx, cy)


def ring(d, cx, cy, r, w, fill=CHROME):
    d.ellipse(mm(cx - r, cy - r, cx + r, cy + r), outline=fill, width=max(1, int(w * PX)))


def knob_base(d, cx, cy, r):
    d.ellipse(mm(cx - r - 1.2, cy - r - 1.2, cx + r + 1.2, cy + r + 1.2), fill=(4, 4, 5))
    ring(d, cx, cy, r, 1.4)
    d.ellipse(mm(cx - r + 1.4, cy - r + 1.4, cx + r - 1.4, cy + r - 1.4), fill=(22, 22, 24))


# small icons ----------------------------------------------------------------
def ico_prev(d, cx, cy, s=1.0):
    for dx in (-1.6, 1.2):
        d.polygon(mm(cx + dx + 1.4 * s, cy - 1.4 * s, cx + dx - 0.6 * s, cy, cx + dx + 1.4 * s, cy + 1.4 * s),
                  fill=INK)
    d.rectangle(mm(cx - 3.0 * s, cy - 1.4 * s, cx - 2.5 * s, cy + 1.4 * s), fill=INK)


def ico_next(d, cx, cy, s=1.0):
    for dx in (-1.2, 1.6):
        d.polygon(mm(cx + dx - 1.4 * s, cy - 1.4 * s, cx + dx + 0.6 * s, cy, cx + dx - 1.4 * s, cy + 1.4 * s),
                  fill=INK)
    d.rectangle(mm(cx + 2.5 * s, cy - 1.4 * s, cx + 3.0 * s, cy + 1.4 * s), fill=INK)


def ico_back(d, cx, cy):
    d.arc(mm(cx - 2.2, cy - 1.8, cx + 2.2, cy + 1.8), 270, 90, fill=INK, width=int(0.5 * PX))
    d.line(mm(cx - 2.0, cy - 1.8, cx, cy - 1.8), fill=INK, width=int(0.5 * PX))
    d.polygon(mm(cx - 2.6, cy - 1.8, cx - 1.2, cy - 2.9, cx - 1.2, cy - 0.7), fill=INK)
    d.line(mm(cx - 2.0, cy + 1.8, cx, cy + 1.8), fill=INK, width=int(0.5 * PX))


def ico_phone(d, cx, cy):
    d.arc(mm(cx - 2.4, cy - 2.4, cx + 2.4, cy + 2.4), 100, 230, fill=INK, width=int(0.9 * PX))
    d.ellipse(mm(cx - 2.6, cy - 2.8, cx - 1.2, cy - 1.4), fill=INK)
    d.ellipse(mm(cx + 0.8, cy + 1.4, cx + 2.2, cy + 2.8), fill=INK)


def ico_fan(d, cx, cy, big):
    r = 2.4 if big else 1.8
    for k in range(4):
        a = math.radians(45 + 90 * k)
        px, py = cx + math.cos(a) * r * 0.55, cy + math.sin(a) * r * 0.55
        d.ellipse(mm(px - r * 0.45, py - r * 0.45, px + r * 0.45, py + r * 0.45), fill=INK)
    d.ellipse(mm(cx - 0.5, cy - 0.5, cx + 0.5, cy + 0.5), fill=BUTTON)


def ico_defrost(d, cx, cy, rear):
    if rear:
        rrect(d, cx - 2.6, cy - 1.8, cx + 2.6, cy + 1.8, 0.4, outline=INK, width=0.4)
    else:
        d.arc(mm(cx - 3.0, cy - 1.0, cx + 3.0, cy + 5.0), 200, 340, fill=INK, width=int(0.4 * PX))
    for k in (-1.2, 0.0, 1.2):
        d.line(mm(cx + k, cy - 1.0, cx + k + 0.4, cy + 1.2), fill=INK, width=int(0.35 * PX))


def ico_recirc(d, cx, cy):
    d.arc(mm(cx - 2.8, cy - 1.8, cx + 2.8, cy + 1.8), 180, 360, fill=INK, width=int(0.45 * PX))
    d.line(mm(cx - 3.2, cy + 1.6, cx + 3.2, cy + 1.6), fill=INK, width=int(0.45 * PX))
    d.polygon(mm(cx - 3.4, cy, cx - 2.0, cy, cx - 2.7, cy + 0.9), fill=INK)


def ico_seat(d, cx, cy, mode):
    d.line(mm(cx - 1.4, cy - 2.6, cx - 1.0, cy + 1.6), fill=INK, width=int(0.5 * PX))
    d.line(mm(cx - 1.0, cy + 1.6, cx + 1.8, cy + 1.6), fill=INK, width=int(0.5 * PX))
    d.ellipse(mm(cx - 1.4, cy - 3.8, cx - 0.2, cy - 2.6), fill=INK)
    if mode in (0, 2):
        d.line(mm(cx + 3.0, cy - 2.2, cx + 0.4, cy - 1.6), fill=INK, width=int(0.4 * PX))
    if mode in (1, 2):
        d.line(mm(cx + 3.0, cy + 2.6, cx + 1.4, cy + 2.0), fill=INK, width=int(0.4 * PX))


# ---------------------------------------------------------------------------
def stack():
    W, H = STACK_MM
    img = Image.new("RGB", (int(W * PX), int(H * PX)), BLACK)
    d = ImageDraw.Draw(img)
    # piano-black surround with a soft reflection band
    for k in range(int(H * PX)):
        g = int(10 + 10 * math.exp(-((k / PX - 40.0) / 25.0) ** 2))
        d.line([(0, k), (W * PX, k)], fill=(g, g, g + 1))

    # --- audio unit (CD / radio), 25..225 x 12..117 mm --------------------
    ax0, ay0, ax1, ay1 = 25.0, 12.0, 225.0, 117.0
    rrect(d, ax0, ay0, ax1, ay1, 5.0, fill=PANEL, outline=(40, 40, 44), width=0.5)
    # chrome frame: top bar and the "smile" arc under the buttons
    d.line(mm(ax0 + 8, ay0 + 6.5, ax1 - 8, ay0 + 6.5), fill=CHROME, width=int(1.2 * PX))
    rrect(d, 60.0, ay0 + 3.0, 190.0, ay0 + 6.0, 1.0, fill=(3, 3, 3))           # CD slot
    button(d, ax0 + 10, ay0 + 2.5, ax0 + 28, ay0 + 7.5, icon=lambda dd, x, y: None)
    button(d, ax1 - 28, ay0 + 2.5, ax1 - 10, ay0 + 7.5, label="\u23cf", size=3.0)
    # display
    rrect(d, 80.0, 24.0, 170.0, 58.0, 2.0, fill=(12, 10, 8), outline=(60, 62, 66), width=0.4)
    glow = Image.new("RGB", img.size, (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.text((125 * PX, 36 * PX), "FM1  97.4", font=font(6.0), fill=AMBER, anchor="mm")
    gd.text((125 * PX, 48 * PX), "BBC R2", font=font(4.2, bold=False), fill=AMBER, anchor="mm")
    glow = glow.filter(ImageFilter.GaussianBlur(1.2))
    img.paste(Image.eval(glow, lambda v: v), (0, 0), Image.eval(glow.convert("L"), lambda v: min(255, v * 3)))
    d = ImageDraw.Draw(img)
    # side buttons
    button(d, 33.0, 22.0, 72.0, 36.0, "RADIO", 3.0)
    button(d, 33.0, 40.0, 72.0, 54.0, "DISP", 3.0)
    button(d, 178.0, 22.0, 217.0, 36.0, "MEDIA", 3.0)
    button(d, 178.0, 40.0, 217.0, 54.0, icon=ico_phone)
    d.line(mm(38, 38, 67, 38), fill=CHROME, width=int(0.6 * PX))
    d.line(mm(183, 38, 212, 38), fill=CHROME, width=int(0.6 * PX))
    # chrome "smile": around the lower button block
    d.line(mm(33, 62, 60, 62), fill=CHROME, width=int(1.2 * PX))
    d.line(mm(190, 62, 217, 62), fill=CHROME, width=int(1.2 * PX))
    d.arc(mm(52, 30, 198, 104), 20, 160, fill=CHROME, width=int(1.2 * PX))
    labels = ["TA", None, None, "SETUP", None]
    icons = [None, ico_prev, ico_next, None, ico_back]
    for k in range(5):
        x0 = 62.0 + 25.5 * k
        button(d, x0, 63.0, x0 + 24.0, 75.0, labels[k], 3.0, icons[k])
    presets = ["RPT\n1", "MIX\n2", "3", "4", "5", "A-Z\n6"]
    for k in range(6):
        x0 = 66.0 + 20.0 * k
        button(d, x0, 78.0, x0 + 18.5, 92.0)
        lab = presets[k].split("\n")
        if len(lab) == 2:
            text(d, x0 + 9.25, 82.0, lab[0], 2.3)
            text(d, x0 + 9.25, 88.2, lab[1], 2.8)
        else:
            text(d, x0 + 9.25, 85.0, lab[0], 3.0)
    # knob bases (the knobs themselves are geometry)
    text(d, 44.0, 64.0, "VOL", 2.6)
    knob_base(d, 44.0, 79.0, 10.5)
    text(d, 206.0, 64.0, "MENU", 2.6)
    knob_base(d, 206.0, 79.0, 10.5)
    text(d, 206.0, 79.0, "ENTER", 2.6)

    # --- climate control, 25..225 x 124..196 mm ----------------------------
    cx0, cy0, cx1, cy1 = 25.0, 124.0, 225.0, 196.0
    rrect(d, cx0, cy0, cx1, cy1, 4.0, fill=PANEL, outline=(40, 40, 44), width=0.5)
    rrect(d, 60.0, 128.0, 190.0, 146.0, 1.5, fill=(10, 10, 12), outline=(48, 50, 54), width=0.3)  # display strip
    text(d, 90.0, 137.0, "21.0", 4.5, fill=(170, 200, 235))
    text(d, 160.0, 137.0, "21.0", 4.5, fill=(170, 200, 235))
    button(d, 31.0, 128.0, 55.0, 144.0, icon=lambda dd, x, y: ico_defrost(dd, x, y - 0.6, False))
    text(d, 43.0, 142.2, "MAX", 1.8, fill=DIM)
    button(d, 195.0, 128.0, 219.0, 144.0, icon=lambda dd, x, y: ico_defrost(dd, x, y, True))
    button(d, 31.0, 148.0, 55.0, 162.0, "A/C", 3.2)
    # AUTO and DUAL knobs with the blue / red temperature arcs
    for cx, lab in ((70.0, "AUTO"), (180.0, "DUAL")):
        d.arc(mm(cx - 17, 150.0, cx + 17, 184.0), 150, 215, fill=(40, 110, 230), width=int(1.2 * PX))
        d.arc(mm(cx - 17, 150.0, cx + 17, 184.0), 325, 30, fill=(230, 40, 35), width=int(1.2 * PX))
        knob_base(d, cx, 167.0, 12.5)
        text(d, cx, 167.0, lab, 3.0)
    button(d, 91.0, 150.0, 111.0, 163.0, icon=ico_recirc)
    button(d, 113.0, 150.0, 137.0, 163.0, icon=lambda dd, x, y: ico_fan(dd, x, y, False))
    button(d, 139.0, 150.0, 159.0, 163.0, icon=lambda dd, x, y: ico_fan(dd, x, y, True))
    button(d, 91.0, 166.0, 159.0, 178.0, "ON-OFF", 3.0)
    d.line(mm(93, 180.5, 157, 180.5), fill=CHROME, width=int(0.7 * PX))
    for k, mode in enumerate((0, 2, 1)):
        x0 = 93.0 + 22.0 * k
        button(d, x0, 182.0, x0 + 20.0, 193.0, icon=lambda dd, x, y, m=mode: ico_seat(dd, x, y, m))
    button(d, 195.0, 148.0, 219.0, 162.0, icon=lambda dd, x, y: None)
    text(d, 207.0, 155.0, "OFF", 2.6)

    # --- airbag lamp, sockets --------------------------------------------------
    text(d, 125.0, 206.0, "PASSENGER", 2.2, fill=DIM)
    text(d, 125.0, 209.5, "AIR BAG", 2.2, fill=DIM)
    rrect(d, 117.0, 212.0, 133.0, 216.0, 1.0, fill=(40, 30, 10))
    rrect(d, 88.0, 226.0, 112.0, 238.0, 2.0, fill=(20, 20, 22), outline=(60, 62, 66), width=0.4)
    rrect(d, 94.0, 230.0, 106.0, 234.0, 0.6, fill=(2, 2, 2))            # USB
    d.ellipse(mm(133.0, 226.0, 145.0, 238.0), fill=(20, 20, 22), outline=(60, 62, 66), width=int(0.4 * PX))
    d.ellipse(mm(137.0, 230.0, 141.0, 234.0), fill=(2, 2, 2))           # AUX
    text(d, 100.0, 242.0, "USB", 2.2, fill=DIM)
    text(d, 139.0, 242.0, "AUX", 2.2, fill=DIM)
    # oddments tray and 12 V socket at the bottom
    rrect(d, 40.0, 252.0, 210.0, 300.0, 4.0, fill=(5, 5, 6))
    d.ellipse(mm(180.0, 262.0, 198.0, 280.0), fill=(28, 28, 30), outline=(60, 60, 64), width=int(0.6 * PX))
    return img


def dial(d, cx, cy, r, vmax, step, minor, label, unit, red_from=None, sweep=240.0):
    d.ellipse(mm(cx - r, cy - r, cx + r, cy + r), fill=(6, 6, 7))
    a0 = 90.0 + sweep / 2.0                  # 0 at the lower left, clockwise
    n = int(round(vmax / minor))
    for k in range(n + 1):
        v = k * minor
        a = math.radians(a0 - sweep * v / vmax)
        major = abs(v / step - round(v / step)) < 1e-6
        r0 = r * (0.80 if major else 0.86)
        col = (225, 40, 30) if red_from is not None and v >= red_from else INK
        d.line(mm(cx + math.cos(a) * r0, cy - math.sin(a) * r0, cx + math.cos(a) * r * 0.93,
                  cy - math.sin(a) * r * 0.93), fill=col, width=int((0.7 if major else 0.35) * PX))
        if major:
            rr = r * 0.66
            text(d, cx + math.cos(a) * rr, cy - math.sin(a) * rr, label(v), r * 0.13, fill=col)
    text(d, cx, cy + r * 0.42, unit, r * 0.09, fill=DIM)
    # needle at rest
    a = math.radians(a0 - 1.5)
    d.line(mm(cx - math.cos(a) * r * 0.12, cy + math.sin(a) * r * 0.12, cx + math.cos(a) * r * 0.78,
              cy - math.sin(a) * r * 0.78), fill=(235, 50, 30), width=int(1.0 * PX))
    d.ellipse(mm(cx - r * 0.09, cy - r * 0.09, cx + r * 0.09, cy + r * 0.09), fill=(24, 24, 26))


def dials():
    W, H = DIALS_MM
    img = Image.new("RGB", (int(W * PX), int(H * PX)), (4, 4, 5))
    d = ImageDraw.Draw(img)
    r = 52.0
    dial(d, 62.0, 64.0, r, 8.0, 1.0, 0.5, lambda v: "%d" % v, "x1000 r/min", red_from=6.5)
    dial(d, 258.0, 64.0, r, 140.0, 20.0, 10.0, lambda v: "%d" % v, "MPH")
    # centre display
    rrect(d, 121.0, 16.0, 199.0, 110.0, 4.0, fill=(8, 9, 12), outline=(50, 52, 56), width=0.5)
    text(d, 160.0, 30.0, "12:40", 5.0, fill=(210, 215, 225))
    text(d, 160.0, 56.0, "34512 mi", 4.0, fill=(210, 215, 225), bold=False)
    text(d, 160.0, 66.0, "TRIP A  182.4", 3.0, fill=DIM, bold=False)
    for k in range(8):                        # fuel and temperature bars
        d.rectangle(mm(131.0 + 3.2 * k, 92.0 - 1.2 * k, 133.6 + 3.2 * k, 96.0), fill=(200, 205, 215))
        if k < 5:
            d.rectangle(mm(163.0 + 3.2 * k, 92.0 - 1.2 * k, 165.6 + 3.2 * k, 96.0), fill=(200, 205, 215))
    text(d, 142.0, 102.0, "E       F", 2.4, fill=DIM)
    text(d, 176.0, 102.0, "C       H", 2.4, fill=DIM)
    return img


def switches():
    W, H = SWITCHES_MM
    img = Image.new("RGB", (int(W * PX), int(H * PX)), (150, 152, 156))
    d = ImageDraw.Draw(img)
    # left pad: back, ENTER (up / down), previous / next, volume -/+
    for x0 in (0.0, 70.0):
        rrect(d, x0 + 4.0, 4.0, x0 + 66.0, 66.0, 8.0, fill=(160, 162, 166))
    button(d, 22.0, 6.0, 48.0, 16.0, icon=ico_back)
    button(d, 18.0, 19.0, 52.0, 33.0, "ENTER", 3.4)
    text(d, 35.0, 18.0, "\u25b2", 2.0)
    text(d, 35.0, 34.5, "\u25bc", 2.0)
    button(d, 12.0, 37.0, 58.0, 50.0, icon=lambda dd, x, y: (ico_prev(dd, x - 11, y), ico_next(dd, x + 11, y)))
    button(d, 10.0, 53.0, 34.0, 65.0, "\u2013", 4.0)
    button(d, 36.0, 53.0, 60.0, 65.0, "+", 4.0)
    # right pad: cruise control and phone
    button(d, 92.0, 6.0, 118.0, 16.0, "CANCEL", 2.6)
    button(d, 88.0, 19.0, 122.0, 31.0, "RES/+", 3.0)
    button(d, 88.0, 33.0, 122.0, 45.0, "SET/\u2013", 3.0)
    button(d, 80.0, 48.0, 104.0, 60.0, icon=lambda dd, x, y: ring(dd, x, y, 3.0, 0.6, INK))
    button(d, 106.0, 48.0, 130.0, 60.0, icon=ico_phone)
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, fn in (("T_Interior_Stack.png", stack), ("T_Interior_Dials.png", dials),
                     ("T_Interior_Switches.png", switches)):
        path = os.path.join(OUT, name)
        fn().save(path, optimize=True)
        print("wrote", path)


if __name__ == "__main__":
    main()
