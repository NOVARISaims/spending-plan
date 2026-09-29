"""Final deliverables from OUTDIR/stage1.blend (see build_q16.py):

    OUTDIR/textures/*.png                      shared by the Blender file and the UE5 package
    OUTDIR/blender/Qashqai_J11_DE17YAU.blend   studio set-up; textures from ../textures
    OUTDIR/unreal/*.fbx, manifest.json, import_qashqai_j11.py
    OUTDIR/gltf/Qashqai_J11_DE17YAU.glb        self-contained

    python export_q16.py [--pack] OUTDIR       --pack also writes a .blend with the textures packed"""
import json
import math
import os
import shutil
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "Qashqai_J11_DE17YAU"
S = np.diag([1.0, -1.0, 1.0])                 # Blender -> Unreal axes (then x100 for cm)


def log(*a):
    print("[export]", *a, flush=True)


def ue_vec(v, scale=100.0):
    return [round(float(x), 4) for x in (S @ np.asarray(v, float)) * scale]


def ue_frame(M):
    """Location (cm) and X/Z axis directions of a Blender world matrix in
    Unreal space (for MathLibrary.make_rot_from_xz)."""
    R = np.array(M.to_3x3().normalized())
    return {"location_cm": ue_vec(M.translation), "x_axis": ue_vec(R[:, 0], 1.0), "z_axis": ue_vec(R[:, 2], 1.0)}


def select_only(objs):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    for ob in objs:
        ob.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]


def joined(name, objs, pivot, tmp):
    """New object: copies of objs joined into pivot-local coordinates, left
    at the identity transform (so the pivot becomes the mesh origin)."""
    target = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    tmp.objects.link(target)
    target.matrix_world = pivot
    copies = []
    for ob in objs:
        c = ob.copy()
        c.data = ob.data.copy()
        tmp.objects.link(c)
        copies.append(c)
    select_only([target] + copies)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()
    target.matrix_world = Matrix.Identity(4)
    target.data.name = name
    return target


def triangles(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def export_fbx(path, objs):
    select_only(objs)
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"}, global_scale=1.0,
                             apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE", axis_forward="-Z",
                             axis_up="Y", use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=True,
                             use_custom_props=False, add_leaf_bones=False, bake_anim=False, path_mode="STRIP",
                             embed_textures=False)


def ue_material(spec, store_files):
    """Parent material and parameters for one flat material."""
    if spec["blend"] == "BLEND":
        parent = "M_J11_Translucent"
    elif spec["blend"] == "CLIP":
        parent = "M_J11_Masked"
    elif spec["coat"] > 0:
        parent = "M_J11_ClearCoat"
    else:
        parent = "M_J11_Opaque"
    vec = {"BaseColor": spec["base"] + [1.0], "Emissive": list(spec["emission"]) + [1.0]}
    sc = {"Metallic": spec["metallic"], "Roughness": spec["roughness"], "NormalStrength":
          spec["normal_strength"] if spec["normal_map"] else 0.0, "Opacity": spec["alpha"]}
    if parent == "M_J11_Masked":
        sc["OpacityCutoff"] = spec["alpha_cutoff"]
    if parent == "M_J11_ClearCoat":
        sc["ClearCoat"] = spec["coat"]
        sc["ClearCoatRoughness"] = spec["coat_roughness"]
    tex = {}
    for param, key in (("BaseColorMap", "base_map"), ("MetallicMap", "metallic_map"), ("RoughnessMap", "roughness_map"),
                       ("NormalMap", "normal_map"), ("EmissiveMap", "emission_map"), ("OpacityMap", "alpha_map")):
        if spec[key]:
            tex[param] = spec[key]
    if spec["emission_map"] and not any(spec["emission"]):
        vec["Emissive"] = [1.0, 1.0, 1.0, 1.0]
    return {"parent": parent, "two_sided": bool(spec["double_sided"]), "vectors": vec,
            "scalars": {k: round(float(v), 5) for k, v in sc.items()}, "textures": tex, "source": spec.get("source", "")}


def main():
    out = os.path.abspath(sys.argv[-1])
    bpy.ops.wm.open_mainfile(filepath=os.path.join(out, "stage1.blend"))
    scene = bpy.context.scene
    scene.name = NAME
    car = bpy.data.collections[NAME]
    specs = json.load(open(os.path.join(out, "material_specs.json")))
    texinfo = json.load(open(os.path.join(out, "textures.json")))
    info = json.load(open(os.path.join(out, "build_info.json")))

    # ---------------------------------------------------------------- studio
    studio = bpy.data.collections.new("Studio (not part of the car)")
    scene.collection.children.link(studio)
    world = bpy.data.worlds.new("Studio")
    scene.world = world
    world.use_nodes = True
    env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world",
                                                  "courtyard.exr"))       # CC0, ships with Blender
    env.location = (-300, 300)
    wn, wl = world.node_tree.nodes, world.node_tree.links
    wl.new(env.outputs["Color"], wn["Background"].inputs["Color"])
    wn["Background"].inputs["Strength"].default_value = 1.0
    # the HDRI lights the car; the camera sees a plain light-grey backdrop
    plain = wn.new("ShaderNodeBackground")
    plain.inputs["Color"].default_value = (0.62, 0.62, 0.64, 1.0)
    path = wn.new("ShaderNodeLightPath")
    mix = wn.new("ShaderNodeMixShader")
    wl.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    wl.new(wn["Background"].outputs["Background"], mix.inputs[1])
    wl.new(plain.outputs["Background"], mix.inputs[2])
    wl.new(mix.outputs["Shader"], wn["World Output"].inputs["Surface"])
    floor = bpy.data.objects.new("Floor", bpy.data.meshes.new("Floor"))
    floor.data.from_pydata([(-15, -15, 0), (15, -15, 0), (15, 15, 0), (-15, 15, 0)], [], [(0, 1, 2, 3)])
    fm = bpy.data.materials.new("Studio floor")
    fm.use_nodes = True
    fb = fm.node_tree.nodes["Principled BSDF"]
    fb.inputs["Base Color"].default_value = (0.35, 0.35, 0.36, 1.0)
    fb.inputs["Roughness"].default_value = 0.7
    floor.data.materials.append(fm)
    studio.objects.link(floor)
    sun = bpy.data.objects.new("Key light", bpy.data.lights.new("Key light", "SUN"))
    sun.data.energy = 2.5
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(35), 0, math.radians(-40))
    studio.objects.link(sun)
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    cam.data.lens = 50
    cam.location = (4.6, -3.3, 1.35)
    cam.rotation_euler = (Vector((0.15, 0.0, 0.62)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    studio.objects.link(cam)
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    scene.render.film_transparent = False
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    scene.view_settings.view_transform = "AgX"
    scene.unit_settings.system = "METRIC"
    car["build"] = json.dumps(info)

    # ------------------------------------------------------------ Blender file
    bdir = os.path.join(out, "blender")
    os.makedirs(bdir, exist_ok=True)
    env.image.pack()                              # the HDRI is not in the texture folder
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(bdir, NAME + ".blend"), compress=True, copy=True,
                                relative_remap=True)
    log("saved", os.path.join(bdir, NAME + ".blend"))
    if "--pack" in sys.argv:
        for img in bpy.data.images:
            if img.source == "FILE" and not img.packed_file:
                img.pack()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(bdir, NAME + "_packed.blend"), compress=True, copy=True)
        log("saved", os.path.join(bdir, NAME + "_packed.blend"))

    # ------------------------------------------------------------------ glTF
    gdir = os.path.join(out, "gltf")
    os.makedirs(gdir, exist_ok=True)
    car_objs = [o for o in car.all_objects if o.type == "MESH"]
    select_only(car_objs)
    bpy.ops.export_scene.gltf(filepath=os.path.join(gdir, NAME + ".glb"), export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_texcoords=True, export_normals=True,
                              export_materials="EXPORT", export_image_format="AUTO", export_cameras=False,
                              export_lights=False, export_extras=False)
    log("glb written")

    # ---------------------------------------------------------------- Unreal
    udir = os.path.join(out, "unreal")
    tdir = os.path.join(out, "textures")
    if os.path.isdir(udir):
        shutil.rmtree(udir)
    os.makedirs(udir)
    tmp = bpy.data.collections.new("_export")
    scene.collection.children.link(tmp)
    cols = {c.name: c for c in car.children}
    steer = bpy.data.objects["qashqai16_steer_rhd"]
    parts = []

    def add_part(name, objs, pivot=Matrix.Identity(4), collision=False, place=True):
        ob = joined(name, objs, pivot, tmp)
        path = os.path.join(udir, name + ".fbx")
        export_fbx(path, [ob])
        slots = [m.name for m in ob.data.materials]
        part = {"name": name, "fbx": name + ".fbx", "triangles": triangles(ob), "materials": slots,
                "collision": collision}
        if place:
            part["transform"] = ue_frame(pivot)
        parts.append(part)
        log("%s: %d triangles, %d materials" % (name, part["triangles"], len(slots)))
        return ob

    add_part("SM_QashqaiJ11_Body", list(cols["Exterior"].objects), collision=True)
    add_part("SM_QashqaiJ11_Glass", list(cols["Glass"].objects))
    add_part("SM_QashqaiJ11_Interior", [o for o in cols["Interior"].objects if o != steer])
    add_part("SM_QashqaiJ11_SteeringWheel", [steer], pivot=steer.matrix_world.copy())
    add_part("SM_QashqaiJ11_Mechanical", list(cols["Mechanical"].objects))
    fl = [o for o in cols["Wheels"].objects if o.name.startswith("Wheel_FL_")]
    add_part("SM_QashqaiJ11_Wheel", fl, pivot=fl[0].matrix_world.copy(), place=False)
    wheels = {}
    for tag in ("FL", "FR", "RL", "RR"):
        ob = bpy.data.objects["Wheel_%s_Rim" % tag]
        wheels[tag] = ue_frame(ob.matrix_world)

    used = sorted({m for p in parts for m in p["materials"]})
    materials = {m: ue_material(specs[m], texinfo) for m in used}
    tex_used = sorted({k for m in materials.values() for k in m["textures"].values()})
    textures = {}
    for k in tex_used:                        # paths relative to the unreal folder
        textures[k] = {"file": "../textures/" + texinfo[k]["file"], "kind": texinfo[k]["kind"]}
    # 4x4 defaults for unused texture slots
    from PIL import Image
    for f, col, kind in (("T_J11_White.png", (255, 255, 255), "color"), ("T_J11_WhiteLinear.png", (255, 255, 255), "data"),
                         ("T_J11_FlatNormal.png", (128, 128, 255), "normal")):
        Image.new("RGB", (4, 4), col).save(os.path.join(tdir, f))
        textures[f[:-4]] = {"file": "../textures/" + f, "kind": kind}

    L = info["wheel_centres_m"]
    manifest = {
        "name": info["name"],
        "source": info["source"],
        "changes": info["changes"],
        "not_in_package": info["not_in_package"],
        "units": "centimetres",
        "unreal_mapping": "UE(x, y, z) = Blender(x, -y, z) * 100: nose towards +X, driver's side (right) towards +Y",
        "pivot": "ground level, midway between the axles, on the centre line",
        "tyre_radius_cm": round(info["tyre_radius_m"] * 100, 2),
        "parts": parts,
        "wheels": wheels,
        "materials": materials,
        "textures": textures,
    }
    json.dump(manifest, open(os.path.join(udir, "manifest.json"), "w"), indent=1)
    shutil.copy2(os.path.join(HERE, "import_qashqai_j11.py"), os.path.join(udir, "import_qashqai_j11.py"))
    log("unreal package:", len(parts), "parts,", len(materials), "materials,", len(textures), "textures")


if __name__ == "__main__":
    main()
