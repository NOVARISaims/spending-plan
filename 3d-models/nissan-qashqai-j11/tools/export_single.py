"""Single-file versions of the car, each under the 30 MB upload limit:

    OUTDIR/single/Qashqai_J11_DE17YAU.blend   textures packed (large ones as JPEG)
    OUTDIR/single/Qashqai_J11_DE17YAU.glb     the six UE5 parts (wheel mesh instanced
                                              four times), for UE5's glTF import

    python export_single.py OUTDIR          (after build_q16.py and export_q16.py)"""
import json
import os
import re
import sys

import bpy
from mathutils import Matrix
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_q16 as ex                        # noqa: E402  (joined(), select_only())

NAME = "Qashqai_J11_DE17YAU"
# 2048 px lamp atlases that only texture the dome-light and third-brake-light
# lenses: half size is plenty for parts that small
HALF = {"T_lights_b.png", "T_lights_nm_n.png", "T_lights2_b.png", "T_lights2_nm_n.png"}


def log(*a):
    print("[single]", *a, flush=True)


def jpeg_textures(out):
    """JPEG copies of the larger colour, normal and roughness/metallic maps
    (opacity masks stay PNG); returns {png name: jpg path}."""
    info = {v["file"]: v["kind"] for v in json.load(open(os.path.join(out, "textures.json"))).values()}
    src, dst = os.path.join(out, "textures"), os.path.join(out, "textures_jpg")
    os.makedirs(dst, exist_ok=True)
    done = {}
    for f in sorted(os.listdir(src)):
        kind = info.get(f)
        path = os.path.join(src, f)
        if kind is None or os.path.getsize(path) < 150_000:
            continue
        if kind == "data" and re.search(r"_o(_x[0-9p_]+)?\.png$", f):
            continue                           # opacity masks stay PNG (hard alpha-clip edges)
        im = Image.open(path)
        im = im.convert("L") if im.mode == "L" else im.convert("RGB")
        if f in HALF:
            im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
        jp = os.path.join(dst, f[:-4] + ".jpg")
        im.save(jp, quality=95 if kind != "color" else 92, optimize=True, subsampling=0 if kind == "normal" else 2)
        done[f] = jp
    return done


def use_jpegs(done):
    for img in bpy.data.images:
        base = os.path.basename(img.filepath)
        if base in done:
            cs = img.colorspace_settings.name
            img.filepath = done[base]
            img.reload()
            img.colorspace_settings.name = cs
            img.name = os.path.basename(done[base])


def main():
    out = os.path.abspath(sys.argv[-1])
    sdir = os.path.join(out, "single")
    os.makedirs(sdir, exist_ok=True)
    done = jpeg_textures(out)
    log("JPEG copies:", len(done))

    # ---------------------------------------------------------- packed .blend
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "blender", NAME + ".blend"))
    use_jpegs(done)
    for img in bpy.data.images:
        if img.source == "FILE" and not img.packed_file:
            img.pack()
    blend = os.path.join(sdir, NAME + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, copy=True)
    log("blend %.1f MiB" % (os.path.getsize(blend) / 2 ** 20))

    # -------------------------------------------------- .glb of the six parts
    scene = bpy.context.scene
    car = bpy.data.collections[NAME]
    cols = {c.name: c for c in car.children}
    tmp = bpy.data.collections.new("_glb")
    scene.collection.children.link(tmp)
    steer = bpy.data.objects["qashqai16_steer_rhd"]
    parts = [ex.joined("Body", list(cols["Exterior"].objects), Matrix.Identity(4), tmp),
             ex.joined("Glass", list(cols["Glass"].objects), Matrix.Identity(4), tmp),
             ex.joined("Interior", [o for o in cols["Interior"].objects if o != steer], Matrix.Identity(4), tmp),
             ex.joined("Mechanical", list(cols["Mechanical"].objects), Matrix.Identity(4), tmp)]
    sw = ex.joined("SteeringWheel", [steer], steer.matrix_world.copy(), tmp)
    sw.matrix_world = steer.matrix_world.copy()
    parts.append(sw)
    fl = [o for o in cols["Wheels"].objects if o.name.startswith("Wheel_FL_")]
    wheel = ex.joined("Wheel_FL", fl, fl[0].matrix_world.copy(), tmp)
    wheel.matrix_world = fl[0].matrix_world.copy()
    parts.append(wheel)
    for tag in ("FR", "RL", "RR"):
        w = bpy.data.objects.new("Wheel_" + tag, wheel.data)       # instances of one mesh
        w.matrix_world = bpy.data.objects["Wheel_%s_Rim" % tag].matrix_world.copy()
        tmp.objects.link(w)
        parts.append(w)
    ex.select_only(parts)
    glb = os.path.join(sdir, NAME + ".glb")
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_texcoords=True, export_normals=True,
                              export_materials="EXPORT", export_image_format="AUTO", export_cameras=False,
                              export_lights=False, export_extras=False)
    log("glb %.1f MiB" % (os.path.getsize(glb) / 2 ** 20))


if __name__ == "__main__":
    main()
