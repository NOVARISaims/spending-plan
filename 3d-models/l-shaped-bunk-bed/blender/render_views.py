"""Studio preview renders for the bunk bed (Cycles, white product-shot look).

Imported by build_l_bunk_bed.py when run with --render.  The cameras marked
"photo" were solved against the retailer photos (see README) so renders can
be compared one-to-one with them.
"""
import math
import os

import bpy  # noqa: I001  (must precede bmesh with the PyPI bpy module)
import bmesh
import numpy as np
from mathutils import Euler, Vector

# Exposure / shadow density calibrated so white laminate and oak match the
# pixel values of the product photos (see README).
EXPOSURE = -1.1
SHADOW_STRENGTH = 0.6

VIEWS = {
    # "photo" cameras, solved from the retailer photos (image crops noted)
    "front": dict(loc=(0.075, -5.6939, 1.2644), rot=(86.87, -0.235, -0.354), lens=68.137,
                  shift=(-0.0362, -0.1607), res=(1186, 1050)),
    "front_no_mattress": dict(loc=(0.135, -6.35, 1.122), rot=(90.0, 0.0, 0.0), lens=76.0,
                              shift=(-0.0567, -0.198), res=(1186, 1050), mattress=False),
    "three_quarter": dict(loc=(-3.2534, -6.0291, 1.306), rot=(92.595, -0.204, -31.906),
                          lens=69.781, shift=(-0.0052, -0.285), res=(1186, 900)),
    "ladder": dict(loc=(0.7519, -5.4031, 1.2176), rot=(100.672, -0.863, 2.499), lens=75.254,
                   shift=(-0.0427, -0.6459), res=(1186, 1180), mattress=False),
    # extra views (camera aimed with look_at)
    "wardrobe_open": dict(loc=(-0.88, -2.95, 1.40), look_at=(-0.70, -0.70, 0.62), lens=30.0,
                          res=(1200, 1200), doors=100.0),
    "right_front": dict(loc=(3.45, -4.75, 2.35), look_at=(0.05, -1.05, 0.72), lens=46.0,
                        res=(1400, 1050)),
    "plan": dict(loc=(0.0, -1.078, 6.0), rot=(0.0, 0.0, 0.0), ortho=2.55, res=(1100, 1100),
                 shadow=False),
}


def _floor(scene):
    me = bpy.data.meshes.new("ShadowCatcher")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=15.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("ShadowCatcher", me)
    scene.collection.objects.link(ob)
    ob.is_shadow_catcher = True
    return ob


def setup_studio(scene, samples):
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    if bpy.app.version < (5, 0, 0):          # always node-based from 5.0
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs["Strength"].default_value = 0.35

    def area(name, loc, target, size, energy):
        light = bpy.data.lights.new(name, "AREA")
        light.size = size
        light.energy = energy
        ob = bpy.data.objects.new(name, light)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)
        return ob

    # Big soft sources from the front and above, like a product light tent.
    area("Key", (-1.5, -6.0, 4.0), (0.0, -1.0, 0.8), 7.0, 700.0)
    area("Fill", (3.5, -5.5, 2.5), (0.0, -1.0, 0.8), 7.0, 260.0)
    area("Top", (0.0, -1.2, 6.0), (0.0, -1.2, 0.0), 8.0, 220.0)
    floor = _floor(scene)

    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.device = "CPU"
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    cy.max_bounces = 8
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = EXPOSURE
    return floor


def _camera(scene, name, v):
    cam = bpy.data.cameras.new(name)
    if "ortho" in v:
        cam.type = "ORTHO"
        cam.ortho_scale = v["ortho"]
    else:
        cam.lens = v["lens"]
    cam.sensor_width = 36.0
    cam.sensor_fit = "AUTO"
    cam.shift_x, cam.shift_y = v.get("shift", (0.0, 0.0))
    cam.clip_start = 0.05
    cam.clip_end = 100.0
    ob = bpy.data.objects.new(name, cam)
    ob.location = v["loc"]
    if "look_at" in v:
        direction = Vector(v["look_at"]) - Vector(v["loc"])
        ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    else:
        ob.rotation_euler = Euler([math.radians(a) for a in v["rot"]], "XYZ")
    scene.collection.objects.link(ob)
    return ob


def _composite_on_white(path, jpeg_quality=None):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    a = px[..., 3:4]
    # Shadow-catcher pixels are black with partial alpha: soften them to match
    # the very diffuse shadows of the product photos.
    shadow = (a < 0.999) & (px[..., :3].max(axis=-1, keepdims=True) < 0.02)
    a = np.where(shadow, a * SHADOW_STRENGTH, a)
    px[..., :3] = px[..., :3] * a + (1.0 - a)
    px[..., 3] = 1.0
    img.pixels.foreach_set(px.ravel())
    if jpeg_quality:
        out = os.path.splitext(path)[0] + ".jpg"
        img.filepath_raw = out
        img.file_format = "JPEG"
        img.save(quality=jpeg_quality)
        bpy.data.images.remove(img)
        os.remove(path)
        return out
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    return path


def render_all(scene, objects, out_dir, samples, only=(), jpeg_quality=None):
    os.makedirs(out_dir, exist_ok=True)
    floor = setup_studio(scene, samples)
    doors = [o for n, o in objects.items() if "_Door_" in n]
    mattresses = [o for n, o in objects.items() if "_Mattress_" in n]
    for name, v in VIEWS.items():
        if only and name not in only:
            continue
        scene.render.resolution_x, scene.render.resolution_y = v["res"]
        scene.render.resolution_percentage = 100
        scene.camera = _camera(scene, "Cam_" + name, v)
        for d in doors:
            sign = -1.0 if d.name.endswith("_L") else 1.0
            d.rotation_euler = (0.0, 0.0, math.radians(sign * v.get("doors", 0.0)))
        for m in mattresses:
            m.hide_render = not v.get("mattress", True)
        floor.hide_render = not v.get("shadow", True)
        path = os.path.join(out_dir, name + ".png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print("rendered", _composite_on_white(path, jpeg_quality))
    for d in doors:
        d.rotation_euler = (0.0, 0.0, 0.0)
    for m in mattresses:
        m.hide_render = False
