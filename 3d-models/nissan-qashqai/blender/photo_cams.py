"""Cameras solved from the five reference photos of the 2017 car (1024 x 576
pixels).  Each entry: position (m, car frame), yaw / pitch / roll (degrees;
yaw measured from +X towards +Y) and focal length in pixels; the principal
point is the image centre.  The side views were solved from the wheel
centres and the roof silhouette, the three-quarter views from features
measured in the side views (door handles, window corners, pillars) plus the
silhouette.  Used for photo-matched renders and for tracing outlines."""
import math

import numpy as np

W, H = 1024, 576
CAMS = {
    "left": ((0.0274, 6.8589, 0.9418), (-90.425, -0.326, -0.046), 1436.2),        # c8915777
    "right": ((0.0254, -6.7931, 0.9245), (90.427, -0.284, 0.045), 1440.6),        # b12a2d38
    "front_left": ((4.9883, 3.8784, 0.8106), (-139.184, 0.031, -2.879), 1492.0),  # 5a342368
    "front_right": ((4.7585, -3.1138, 0.8751), (143.362, -0.682, 4.254), 1298.9),  # 187444bd
    "rear_right": ((-5.8623, -3.6717, 1.1725), (34.909, -3.055, 0.123), 1510.7),  # 3fa61f71
}
PHOTOS = {"left": "c8915777", "right": "b12a2d38", "front_left": "5a342368",
          "front_right": "187444bd", "rear_right": "3fa61f71"}


def basis(yaw, pitch, roll):
    """View direction, right and up vectors (angles in radians)."""
    d = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    r = np.cross(d, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    cr, sr = math.cos(roll), math.sin(roll)
    return d, cr * r + sr * u, -sr * r + cr * u


def ray(name, uv):
    """Origin and unit direction of the ray through pixel uv."""
    pos, (yaw, pitch, roll), f = CAMS[name]
    d, r, u = basis(math.radians(yaw), math.radians(pitch), math.radians(roll))
    v = d + r * (uv[0] - W / 2) / f - u * (uv[1] - H / 2) / f
    return np.array(pos, float), v / np.linalg.norm(v)


def project(name, P):
    pos, (yaw, pitch, roll), f = CAMS[name]
    d, r, u = basis(math.radians(yaw), math.radians(pitch), math.radians(roll))
    q = np.atleast_2d(P) - np.array(pos)
    z = q @ d
    return np.column_stack([W / 2 + f * (q @ r) / z, H / 2 - f * (q @ u) / z])
