"""Check renders of the built car (Blender space: X forward, Y left, Z up,
origin on the ground midway between the axles).
    python render_q16.py BLEND OUTPREFIX [view ...] [--samples N] [--res WxH]"""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
blend, outp = args[0], args[1]
samples, res = 48, (1200, 675)
views = []
i = 2
while i < len(args):
    if args[i] == "--samples":
        samples = int(args[i + 1]); i += 2
    elif args[i] == "--res":
        w, h = args[i + 1].split("x"); res = (int(w), int(h)); i += 2
    else:
        views.append(args[i]); i += 1

VIEWS = {
    # name: (camera location, look-at, lens mm)
    "front34": ((4.6, -3.3, 1.35), (0.15, 0.0, 0.62), 50),      # front right, like the mod's preview
    "front34l": ((4.6, 3.3, 1.35), (0.15, 0.0, 0.62), 50),
    "rear34": ((-4.8, -3.2, 1.45), (-0.1, 0.0, 0.7), 50),
    "rear34l": ((-4.8, 3.2, 1.45), (-0.1, 0.0, 0.7), 50),
    "side": ((0.0, -7.5, 0.8), (0.0, 0.0, 0.75), 50),
    "front": ((7.0, 0.0, 0.9), (0.0, 0.0, 0.72), 60),
    "rear": ((-7.0, 0.0, 0.95), (0.0, 0.0, 0.75), 60),
    "plate_f": ((3.2, -0.25, 0.62), (2.2, 0.0, 0.52), 50),
    "plate_r": ((-3.1, 0.25, 0.95), (-2.1, 0.0, 0.85), 50),
    "cabin": ((-0.45, 0.0, 1.22), (0.9, -0.15, 0.95), 22),       # from the rear seats, looking forward
    "dash": ((-0.05, -0.37, 1.18), (0.9, -0.37, 0.98), 24),      # driver's eye (right-hand seat)
    "wheel_fr": ((2.6, -2.3, 0.45), (1.32, -0.78, 0.35), 45),
    "top": ((0.0, 0.0, 9.0), (0.0, 0.001, 0.0), 35),
}

bpy.ops.wm.open_mainfile(filepath=blend)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = samples
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 8
scene.cycles.transparent_max_bounces = 16
scene.render.resolution_x, scene.render.resolution_y = res
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Base Contrast"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "NONE"
except Exception:
    pass

# studio: bright HDRI for reflections, white floor
world = bpy.data.worlds.new("Studio")
scene.world = world
world.use_nodes = True
nt = world.node_tree
env = nt.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(os.path.join(os.path.dirname(bpy.app.binary_path or ""), "") if False else
                                 os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world", "studio.exr"))
bg = nt.nodes["Background"]
bg.inputs["Strength"].default_value = 1.2
nt.links.new(env.outputs["Color"], bg.inputs["Color"])

floor = bpy.data.meshes.new("Floor")
floor.from_pydata([(-40, -40, 0), (40, -40, 0), (40, 40, 0), (-40, 40, 0)], [], [(0, 1, 2, 3)])
fo = bpy.data.objects.new("Floor", floor)
scene.collection.objects.link(fo)
fm = bpy.data.materials.new("FloorMat")
fm.use_nodes = True
b = fm.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.62, 0.62, 0.63, 1)
b.inputs["Roughness"].default_value = 0.6
floor.materials.append(fm)

sun = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "SUN"))
sun.data.energy = 2.5
sun.data.angle = math.radians(8)
sun.rotation_euler = (math.radians(35), 0, math.radians(-40))
scene.collection.objects.link(sun)

for name in views or ["front34", "rear34", "side"]:
    loc, look, lens = VIEWS[name]
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(cam)
    scene.camera = cam
    fo.hide_render = name in ("cabin", "dash")
    scene.render.filepath = outp + name + ".png"
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath, flush=True)
