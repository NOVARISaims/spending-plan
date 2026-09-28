"""Studio preview renders for the Qashqai (Cycles, white showroom look).

Imported by build_qashqai.py when run with --render.  The "photo_*" views
use the cameras solved from the reference photos of the 2017 car (see
README), so renders can be compared one-to-one with them.
"""
import math
import os

import bpy  # noqa: I001  (must precede bmesh with the PyPI bpy module)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

import photo_cams

EXPOSURE = 0.0
SHADOW_STRENGTH = 0.75

# Cameras solved from the reference photos (photo_cams.py)
PHOTO_CAMS = {"photo_" + k: v for k, v in photo_cams.CAMS.items()}

VIEWS = {
    "front_three_quarter": dict(loc=(5.2, 3.9, 1.55), look_at=(0.15, 0.0, 0.62), lens=50.0, res=(1600, 900)),
    "rear_three_quarter": dict(loc=(-5.3, -4.0, 1.65), look_at=(-0.15, 0.0, 0.68), lens=50.0, res=(1600, 900)),
    "side": dict(loc=(0.0, 8.4, 0.85), look_at=(0.0, 0.0, 0.72), lens=50.0, res=(1600, 800)),
    "front": dict(loc=(8.5, 0.0, 0.95), look_at=(0.0, 0.0, 0.72), lens=60.0, res=(1400, 900)),
    "rear": dict(loc=(-8.5, 0.0, 1.05), look_at=(0.0, 0.0, 0.75), lens=60.0, res=(1400, 900)),
    # roughly the viewpoint of the 2019 reference photo, for the paint colour
    "paint_check": dict(loc=(-5.6, 4.6, 1.25), look_at=(-0.2, 0.0, 0.70), lens=45.0, res=(1024, 768)),
    "wheel": dict(loc=(1.35, 2.35, 0.45), look_at=(1.30, 0.80, 0.33), lens=50.0, res=(1000, 1000)),
    "detail_front": dict(loc=(3.35, 1.75, 1.10), look_at=(1.98, 0.25, 0.72), lens=50.0, res=(1400, 900)),
    "photo_left": dict(photo=True, res=(1024, 576)),
    "photo_right": dict(photo=True, res=(1024, 576)),
    "photo_front_left": dict(photo=True, res=(1024, 576)),
    "photo_front_right": dict(photo=True, res=(1024, 576)),
    "photo_rear_right": dict(photo=True, res=(1024, 576)),
}


def _floor(scene):
    me = bpy.data.meshes.new("ShadowCatcher")
    bmh = bmesh.new()
    bmesh.ops.create_grid(bmh, x_segments=1, y_segments=1, size=25.0)
    bmh.to_mesh(me)
    bmh.free()
    ob = bpy.data.objects.new("ShadowCatcher", me)
    scene.collection.objects.link(ob)
    ob.is_shadow_catcher = True
    return ob


# Studio: light grey cyclorama with a big overhead softbox and two long side
# strips, like the dealer photos.  Levels are calibrated so the Gun Metallic
# door and the floor render at the photos' pixel values.
WORLD = (0.62, 0.62, 0.63)
FLOOR_REFL = (0.20, 0.20, 0.205)
LIGHTS = {  # name: (location, target, size, energy)
    "Top": ((0.0, 0.0, 6.0), (0.0, 0.0, 0.0), (8.0, 4.0), 900.0),
    "Left": ((0.5, 7.0, 2.4), (0.0, 0.0, 0.7), (9.0, 2.0), 260.0),
    "Right": ((-0.5, -7.0, 2.4), (0.0, 0.0, 0.7), (9.0, 2.0), 260.0),
    "Front": ((7.5, 0.0, 2.0), (0.0, 0.0, 0.7), (3.0, 2.0), 160.0),
    "Rear": ((-7.5, 0.0, 2.0), (0.0, 0.0, 0.7), (3.0, 2.0), 160.0),
}


def setup_studio(scene, samples):
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    bg.inputs["Strength"].default_value = 1.0
    # reflections: darker studio floor below the horizon, bright ceiling above
    coord = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.elements[0].position = 0.46
    cr.elements[0].color = (*FLOOR_REFL, 1.0)
    cr.elements[1].position = 0.52
    cr.elements[1].color = (*WORLD, 1.0)
    top = cr.elements.new(0.95)
    top.color = (*[min(1.0, c * 1.25) for c in WORLD], 1.0)
    maprange = nt.nodes.new("ShaderNodeMapRange")
    maprange.inputs["From Min"].default_value = -1.0
    maprange.inputs["From Max"].default_value = 1.0
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], maprange.inputs["Value"])
    nt.links.new(maprange.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])

    for name, (loc, target, size, energy) in LIGHTS.items():
        light = bpy.data.lights.new(name, "AREA")
        light.shape = "RECTANGLE"
        light.size, light.size_y = size
        light.energy = energy
        ob = bpy.data.objects.new(name, light)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(ob)
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
    cy.max_bounces = 10
    cy.transmission_bounces = 10
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = EXPOSURE
    return floor


def _basis(yaw, pitch, roll):
    d = np.array([math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)])
    r = np.cross(d, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    cr, sr = math.cos(roll), math.sin(roll)
    return d, cr * r + sr * u, -sr * r + cr * u


def _camera(scene, name, v):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = 36.0
    cam.clip_start = 0.05
    cam.clip_end = 200.0
    ob = bpy.data.objects.new(name, cam)
    if v.get("photo"):
        (pos, (yaw, pitch, roll), f) = PHOTO_CAMS[name]
        d, r, u = _basis(math.radians(yaw), math.radians(pitch), math.radians(roll))
        R = Matrix([[r[0], u[0], -d[0]], [r[1], u[1], -d[1]], [r[2], u[2], -d[2]]])
        ob.matrix_world = Matrix.Translation(Vector(pos)) @ R.to_4x4()
        cam.lens = f * 36.0 / 1024.0
    else:
        cam.lens = v["lens"]
        ob.location = v["loc"]
        direction = Vector(v["look_at"]) - Vector(v["loc"])
        ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(ob)
    return ob


def _composite(path, bg=(0.78, 0.775, 0.78), jpeg_quality=None):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    a = px[..., 3:4]
    shadow = (a < 0.999) & (px[..., :3].max(axis=-1, keepdims=True) < 0.02)
    a = np.where(shadow, a * SHADOW_STRENGTH, a)
    # light grey studio (wall ~200/255 in the photos), darker floor at the bottom
    ramp = np.linspace(0.86, 1.0, h)[:, None, None]       # pixel rows run bottom -> top
    back = np.array(bg)[None, None, :] * ramp
    px[..., :3] = px[..., :3] * a + back * (1.0 - a)
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


def render_all(scene, objects, wheels, out_dir, samples, only=(), jpeg_quality=None):
    os.makedirs(out_dir, exist_ok=True)
    setup_studio(scene, samples)
    for name, v in VIEWS.items():
        if only and name not in only:
            continue
        scene.render.resolution_x, scene.render.resolution_y = v["res"]
        scene.render.resolution_percentage = 100
        scene.camera = _camera(scene, "Cam_" + name if not v.get("photo") else name, v)
        path = os.path.join(out_dir, name + ".png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        print("rendered", _composite(path, jpeg_quality=jpeg_quality))
