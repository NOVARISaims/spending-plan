"""Sanity-check the exported files by re-importing them into an empty scene.

    blender -b -P verify_exports.py -- [--dir ../export]
    python verify_exports.py [--dir ../export]      # PyPI bpy module

Checks the body size and pivot, the wheel size and pivot, UCX collision and
material slots in every FBX, that the interior sits inside the body with its
trims facing into the cabin, the texture files, and the node / material /
texture layout of the GLB (four wheels at the manifest positions).  Exits
non-zero on the first failed check.
"""
import argparse
import json
import os
import struct
import sys

import bpy  # noqa: I001  (must precede mathutils with the PyPI bpy module)
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import qashqai_body as qb  # noqa: E402

TOL = 0.004


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in objs:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        for v in me.vertices:
            p = ob.matrix_world @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
        ev.to_mesh_clear()
    return lo, hi


def import_fbx(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    render = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("UCX_")]
    ucx = [o for o in bpy.context.scene.objects if o.name.startswith("UCX_")]
    return render, ucx


def check_fbx(export_dir, manifest):
    boxes = {}
    for part in manifest["parts"]:
        render, ucx = import_fbx(os.path.join(export_dir, part["fbx"]))
        if len(render) != 1 or render[0].name != part["name"]:
            fail("%s: expected one mesh named %s, got %s" % (part["fbx"], part["name"], [o.name for o in render]))
        ob = render[0]
        if len(ucx) != part["collision_hulls"]:
            fail("%s: %d UCX meshes, manifest says %d" % (part["fbx"], len(ucx), part["collision_hulls"]))
        bad = [o.name for o in ucx if not o.name.startswith("UCX_%s_" % part["name"])]
        if bad:
            fail("%s: UCX names don't match the render mesh: %s" % (part["fbx"], bad))
        slots = [s.material.name if s.material else None for s in ob.material_slots]
        want = [s["slot"] for s in part["material_slots"]]
        if [s.split(".")[0] for s in slots] != want:
            fail("%s: material slots %s != %s" % (part["fbx"], slots, want))
        lo, hi = world_bbox([ob])
        boxes[part["name"]] = (lo, hi)
        print("  %-28s %7d tris  %d UCX  bbox %s .. %s" % (
            part["fbx"], part["triangles"], len(ucx), tuple(round(c, 3) for c in lo), tuple(round(c, 3) for c in hi)))

    # body: bumper tips (the front plate stands up to 4 cm proud), symmetric
    # about the centre line, roof height (the aerial rises above it), origin
    # on the ground between the axles
    lo, hi = boxes["SM_Qashqai_Body"]
    if abs(lo.x - qb.X_R) > 0.01 or not (qb.X_F - 0.005 < hi.x < qb.X_F + 0.04):
        fail("body ends %.3f / %.3f m, expected %.3f / %.3f (+ plate)" % (hi.x, lo.x, qb.X_F, qb.X_R))
    if abs(lo.y + hi.y) > 0.01:
        fail("body is not centred on the centre line: %.3f .. %.3f" % (lo.y, hi.y))
    render, _ = import_fbx(os.path.join(export_dir, "SM_Qashqai_Body.fbx"))
    ob = render[0]
    pts = [ob.matrix_world @ v.co for v in ob.data.vertices]
    roof = max(p.z for p in pts if abs(p.x) < 1.0 and abs(p.y) < 0.3)
    if abs(roof - 1.59) > 0.015 or not (1.58 < hi.z < 1.72):
        fail("roof at %.3f m (spec 1.59 m), top of the aerial at %.3f m" % (roof, hi.z))
    print("  body %.3f m bumper to bumper (%.3f m with the plate), %.3f m wide over the mirrors, roof %.3f m"
          % (qb.X_F - qb.X_R, hi.x - lo.x, hi.y - lo.y, roof))
    # wheel: centred on its pivot, 690 mm tyre
    lo, hi = boxes["SM_Qashqai_Wheel"]
    dia = hi.z - lo.z
    if abs(dia - 2 * manifest["wheel_radius_cm"] / 100.0) > TOL or abs(lo.x + hi.x) > TOL or abs(lo.z + hi.z) > TOL:
        fail("wheel pivot / size wrong: %s %s" % (lo, hi))
    print("  wheel %.3f m diameter, pivot at the hub centre" % dia)
    check_interior(export_dir, boxes)


def check_interior(export_dir, boxes):
    """Interior inside the shell; headliner and door cards face the cabin
    (single-sided materials in Unreal would hide them otherwise)."""
    blo, bhi = boxes["SM_Qashqai_Body"]
    lo, hi = boxes["SM_Qashqai_Interior"]
    if lo.x < blo.x or hi.x > bhi.x or lo.y < blo.y or hi.y > bhi.y or lo.z < 0.15 or hi.z > 1.6:
        fail("interior pokes out of the body: %s .. %s" % (tuple(lo), tuple(hi)))
    render, _ = import_fbx(os.path.join(export_dir, "SM_Qashqai_Interior.fbx"))
    ob = render[0]
    me = ob.data
    names = [s.material.name.split(".")[0] if s.material else "" for s in ob.material_slots]
    roof, cards = Vector(), Vector()
    for p in me.polygons:
        c = ob.matrix_world @ p.center
        n = (ob.matrix_world.to_3x3() @ p.normal) * p.area
        m = names[p.material_index]
        if m == "M_Headliner" and c.z > 1.42 and abs(c.x) < 0.8:
            roof += n
        if m in ("M_DoorCard", "M_InteriorSoft") and c.y > 0.6 and 0.5 < c.z < 1.0 and -1.0 < c.x < 0.7:
            cards += n
    if roof.length == 0 or roof.normalized().z > -0.8:
        fail("headliner does not face down into the cabin: %s" % tuple(roof))
    if cards.length == 0 or cards.normalized().y > -0.8:
        fail("left door cards do not face into the cabin: %s" % tuple(cards))
    print("  interior inside the body; headliner and door cards face the cabin (%d triangles)"
          % sum(len(p.vertices) - 2 for p in me.polygons))


def check_textures(export_dir, manifest):
    for key, info in manifest["textures"].items():
        path = os.path.join(export_dir, info["file"])
        if not os.path.isfile(path):
            fail("texture %s missing: %s" % (key, path))
    print("  %d texture files present" % len(manifest["textures"]))


def read_glb(path):
    with open(path, "rb") as fh:
        magic, version, length = struct.unpack("<4sII", fh.read(12))
        if magic != b"glTF" or version != 2:
            fail("GLB header")
        clen, ctype = struct.unpack("<I4s", fh.read(8))
        return json.loads(fh.read(clen))


def check_glb(export_dir, manifest):
    gltf = read_glb(os.path.join(export_dir, "Qashqai.glb"))
    names = sorted(n.get("name") for n in gltf["nodes"])
    want = sorted([p["name"] for p in manifest["parts"] if p["name"] != "SM_Qashqai_Wheel"]
                  + ["Wheel_" + t for t in manifest["wheels"]])
    if names != want:
        fail("GLB nodes %s != %s" % (names, want))
    for node in gltf["nodes"]:
        if node["name"].startswith("Wheel_"):
            tag = node["name"][6:]
            bx, by, bz = manifest["wheels"][tag]["blender_m"]
            tx, ty, tz = node.get("translation", [0, 0, 0])
            # glTF is Y-up: (x, y, z)_blender -> (x, z, -y)
            if max(abs(tx - bx), abs(ty - bz), abs(tz + by)) > 1e-3:
                fail("GLB wheel %s at %s, expected %s" % (tag, node.get("translation"), (bx, bz, -by)))
    mats = {m["name"]: m for m in gltf["materials"]}
    for name in ("M_PlateFront", "M_PlateRear"):
        if "baseColorTexture" not in mats[name]["pbrMetallicRoughness"]:
            fail("GLB %s has no plate texture" % name)
    for name in ("M_CentreStack", "M_Dials", "M_WheelSwitches"):
        if "baseColorTexture" not in mats[name]["pbrMetallicRoughness"]:
            fail("GLB %s has no panel texture" % name)
    for name in ("M_GrilleHoneycomb", "M_SeatFabricPattern"):
        if "normalTexture" not in mats[name] or "baseColorTexture" not in mats[name]["pbrMetallicRoughness"]:
            fail("GLB %s lacks its tiled textures" % name)
    print("  GLB nodes: %s" % ", ".join(names))
    print("  GLB %d materials, %d images" % (len(mats), len(gltf.get("images", []))))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.normpath(os.path.join(HERE, "..", "export")))
    args = ap.parse_args(argv)
    export_dir = os.path.abspath(args.dir)
    with open(os.path.join(export_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    print("FBX files:")
    check_fbx(export_dir, manifest)
    print("Textures:")
    check_textures(export_dir, manifest)
    print("GLB:")
    check_glb(export_dir, manifest)
    print("All export checks passed.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
