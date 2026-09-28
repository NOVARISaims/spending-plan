"""Sanity-check the exported files by re-importing them into an empty scene.

    blender -b -P verify_exports.py -- [--dir ../export]
    python verify_exports.py [--dir ../export]      # PyPI bpy module

Checks overall dimensions against the spec, door hinge pivots, UCX collision
and material slots in every FBX, and the node / material / texture layout of
the GLB.  Exits non-zero on the first failed check.
"""
import argparse
import json
import os
import struct
import sys

import bpy  # noqa: I001  (must precede mathutils with the PyPI bpy module)
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_M = (2.142, 2.155, 1.604)       # L x W x H from the product listing
TOL = 0.003


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
    render = [o for o in bpy.context.scene.objects
              if o.type == "MESH" and not o.name.startswith("UCX_")]
    ucx = [o for o in bpy.context.scene.objects if o.name.startswith("UCX_")]
    return render, ucx


def check_fbx(export_dir, manifest):
    by_name = {}
    for part in manifest["parts"]:
        render, ucx = import_fbx(os.path.join(export_dir, part["fbx"]))
        if len(render) != 1 or render[0].name != part["name"]:
            fail("%s: expected one mesh named %s, got %s"
                 % (part["fbx"], part["name"], [o.name for o in render]))
        ob = render[0]
        if len(ucx) != part["collision_boxes"]:
            fail("%s: %d UCX meshes, manifest says %d" % (part["fbx"], len(ucx), part["collision_boxes"]))
        bad = [o.name for o in ucx if not o.name.startswith("UCX_%s_" % part["name"])]
        if bad:
            fail("%s: UCX names don't match the render mesh: %s" % (part["fbx"], bad))
        slots = [s.material.name if s.material else None for s in ob.material_slots]
        want = [s["slot"] for s in part["material_slots"]]
        if [s.split(".")[0] for s in slots] != want:
            fail("%s: material slots %s != %s" % (part["fbx"], slots, want))
        lo, hi = world_bbox([ob])
        by_name[part["name"]] = (lo, hi)
        print("  %-30s %6d tris  %2d UCX  bbox %s .. %s" % (
            part["fbx"], part["triangles"], len(ucx),
            tuple(round(c, 4) for c in lo), tuple(round(c, 4) for c in hi)))

    # Frame: overall size and pivot (back face on Y = 0, floor on Z = 0, centred on X).
    lo, hi = by_name["SM_LBunkBed_Frame"]
    size = hi - lo
    for got, want, axis in zip(size, SPEC_M, "XYZ"):
        if abs(got - want) > TOL:
            fail("frame %s size %.4f m != spec %.4f m" % (axis, got, want))
    if abs(hi.y) > TOL or abs(lo.z) > TOL or abs(lo.x + hi.x) > TOL:
        fail("frame pivot is not at the centre of the back edge on the floor: %s %s" % (lo, hi))
    print("  frame size %.3f x %.3f x %.3f m matches the spec" % tuple(size))

    # Doors: pivot on the hinge edge, i.e. the mesh starts at the origin.
    for side, sign in (("L", 1.0), ("R", -1.0)):
        lo, hi = by_name["SM_LBunkBed_Door_" + side]
        hinge_x = lo.x if sign > 0 else hi.x
        if abs(hinge_x) > TOL or abs(lo.y) > TOL or abs(lo.z) > TOL:
            fail("door %s pivot is not on its hinge edge: %s %s" % (side, lo, hi))
    print("  door pivots sit on the hinge axis")


def read_glb(path):
    with open(path, "rb") as fh:
        magic, version, length = struct.unpack("<4sII", fh.read(12))
        if magic != b"glTF" or version != 2:
            fail("GLB header")
        clen, ctype = struct.unpack("<I4s", fh.read(8))
        return json.loads(fh.read(clen))


def check_glb(export_dir, manifest):
    gltf = read_glb(os.path.join(export_dir, "LBunkBed.glb"))
    names = sorted(n.get("name") for n in gltf["nodes"])
    want = sorted(p["name"] for p in manifest["parts"])
    if names != want:
        fail("GLB nodes %s != %s" % (names, want))
    mats = sorted(m["name"] for m in gltf["materials"])
    print("  GLB nodes: %s" % ", ".join(names))
    print("  GLB materials: %s; images: %d" % (", ".join(mats), len(gltf.get("images", []))))
    oak = next(m for m in gltf["materials"] if m["name"] == "M_Oak")
    pbr = oak["pbrMetallicRoughness"]
    if "baseColorTexture" not in pbr or "normalTexture" not in oak:
        fail("GLB oak material is missing its textures")


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.normpath(os.path.join(HERE, "..", "export")))
    args = ap.parse_args(argv)
    export_dir = os.path.abspath(args.dir)
    with open(os.path.join(export_dir, "manifest.json")) as fh:
        manifest = json.load(fh)
    print("FBX files:")
    check_fbx(export_dir, manifest)
    print("GLB:")
    check_glb(export_dir, manifest)
    print("All export checks passed.")


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
