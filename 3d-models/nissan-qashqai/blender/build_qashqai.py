"""Procedural Blender build of a 2017 Nissan Qashqai (J11, pre-facelift).

Modelled from photos of a 2017 Qashqai Acenta (5-door, 17 in five
twin-spoke alloys, halogen headlamps with LED daytime lights, chrome window
surround), painted Gun Metallic grey and registered DE17 YAU.

The body shell is a loft (qashqai_body) with every feature outline cut in
exactly (body_build / body_mesh); wheels, mirrors, handles, badges, lamp
internals, plates and a simple interior are procedural parts
(qashqai_parts).  Width, height, wheelbase and tyres follow the published
spec (1806 mm, 1590 mm, 2646 mm, 215/60 R17); the length follows the photos
(4341 mm, see qashqai_body).

Usage:
    blender -b -P build_qashqai.py -- [--out DIR] [--render] [--samples N]
    python build_qashqai.py [...]          # with the PyPI `bpy` module

Writes (default --out is ../export next to this folder):
    SM_Qashqai_*.fbx     one FBX per Unreal static mesh (body with UCX_ hulls,
                         glass, lenses, interior, one wheel)
    Qashqai.fbx          the whole car in one FBX (for other DCC tools)
    Qashqai.glb          glTF binary with embedded textures
    textures/            number plates, grille honeycomb, plastic grain
    manifest.json        parts, material slots, wheel positions (read by the UE script)
    ../blend/Qashqai.blend
    ../renders/*.jpg     only with --render
"""
import argparse
import json
import math
import os
import shutil
import sys
import time

import bpy  # noqa: I001  (must precede bmesh with the PyPI bpy module)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import body_build as bb  # noqa: E402
import body_mesh as bm  # noqa: E402
import mesh_kit as mk  # noqa: E402
import qashqai_body as qb  # noqa: E402
import qashqai_features as F  # noqa: E402
import qashqai_interior as qi  # noqa: E402
import qashqai_parts as qp  # noqa: E402
import qashqai_textures as qt  # noqa: E402

REG = "DE17 YAU"
MESH_DS = 0.02            # body grid spacing (m)

# ---------------------------------------------------------------------------
# Materials: key -> (Blender name, UE instance, UE parent, settings)
#   settings: base colour (linear), roughness, metallic, and extras
# ---------------------------------------------------------------------------
PAINT = (0.125, 0.128, 0.133)      # Gun Metallic (KAD), calibrated to the 2019 photos
MATS = {
    "paint": ("M_Paint_GunMetallic", "MI_QQ_Paint", "M_QQ_Paint",
              dict(color=PAINT, rough=0.36, metal=0.75, coat=1.0, coat_rough=0.03)),
    "chrome": ("M_Chrome", "MI_QQ_Chrome", "M_QQ_Solid", dict(color=(0.92, 0.92, 0.92), rough=0.06, metal=1.0)),
    "black_gloss": ("M_BlackGloss", "MI_QQ_BlackGloss", "M_QQ_Solid",
                    dict(color=(0.008, 0.008, 0.009), rough=0.08, metal=0.0, coat=0.5)),
    "gap": ("M_PanelGap", "MI_QQ_PanelGap", "M_QQ_Solid", dict(color=(0.02, 0.02, 0.021), rough=0.6, metal=0.3)),
    "plastic": ("M_PlasticBlack", "MI_QQ_PlasticBlack", "M_QQ_Solid",
                dict(color=(0.018, 0.018, 0.019), rough=0.62, metal=0.0, normal=("grain_normal", 0.35),
                     uv_tiling=25.0)),
    "black_plastic": ("M_PlasticBlack", None, None, None),
    "liner": ("M_Liner", "MI_QQ_Liner", "M_QQ_Solid", dict(color=(0.012, 0.012, 0.012), rough=0.9, metal=0.0)),
    "underbody": ("M_Underbody", "MI_QQ_Underbody", "M_QQ_Solid",
                  dict(color=(0.03, 0.03, 0.03), rough=0.85, metal=0.0)),
    "glass": ("M_Glass", "MI_QQ_Glass", "M_QQ_Glass",
              dict(color=(0.80, 0.86, 0.84), rough=0.0, metal=0.0, transmission=1.0, ior=1.52, opacity=0.18)),
    "frit": ("M_GlassFrit", "MI_QQ_GlassFrit", "M_QQ_Solid",
             dict(color=(0.006, 0.006, 0.006), rough=0.1, metal=0.0)),
    "lens_clear": ("M_LensClear", "MI_QQ_LensClear", "M_QQ_Glass",
                   dict(color=(0.95, 0.95, 0.95), rough=0.0, metal=0.0, transmission=1.0, ior=1.49, opacity=0.08)),
    "lamp_chrome": ("M_LampChrome", "MI_QQ_LampChrome", "M_QQ_Solid",
                    dict(color=(0.62, 0.62, 0.63), rough=0.32, metal=1.0)),
    "lamp_reflector": ("M_LampReflector", "MI_QQ_LampReflector", "M_QQ_Solid",
                       dict(color=(0.90, 0.90, 0.91), rough=0.08, metal=1.0)),
    "lamp_black": ("M_LampBlack", "MI_QQ_LampBlack", "M_QQ_Solid",
                   dict(color=(0.015, 0.015, 0.016), rough=0.35, metal=0.2)),
    "led": ("M_LED_DRL", "MI_QQ_LED", "M_QQ_Solid",
            dict(color=(0.9, 0.93, 1.0), rough=0.2, metal=0.0, emission=(1.0, 1.0, 1.0), emit=0.0)),
    "tail_red": ("M_TailLensRed", "MI_QQ_TailRed", "M_QQ_Glass",
                 dict(color=(0.55, 0.012, 0.012), rough=0.05, metal=0.0, transmission=0.6, ior=1.49,
                      opacity=0.75)),
    "tail_clear": ("M_TailLensClear", "MI_QQ_TailClear", "M_QQ_Glass",
                   dict(color=(0.95, 0.93, 0.93), rough=0.03, metal=0.0, transmission=1.0, ior=1.49,
                        opacity=0.12)),
    "tail_inner": ("M_TailInner", "MI_QQ_TailInner", "M_QQ_Solid",
                   dict(color=(0.35, 0.02, 0.02), rough=0.25, metal=0.8)),
    "brake_light": ("M_BrakeLight", "MI_QQ_BrakeLight", "M_QQ_Solid",
                    dict(color=(0.5, 0.01, 0.01), rough=0.15, metal=0.0, emission=(1.0, 0.02, 0.02), emit=0.0)),
    "reflector": ("M_Reflector", "MI_QQ_Reflector", "M_QQ_Solid",
                  dict(color=(0.45, 0.01, 0.01), rough=0.15, metal=0.2)),
    "indicator": ("M_Indicator", "MI_QQ_Indicator", "M_QQ_Solid",
                  dict(color=(0.9, 0.45, 0.05), rough=0.1, metal=0.0)),
    "grille": ("M_GrilleHoneycomb", "MI_QQ_Grille", "M_QQ_Grille",
               dict(color=(0.02, 0.02, 0.02), rough=0.45, metal=0.0, tiled="honeycomb_base",
                    normal=("honeycomb_normal", 1.0), uv_tiling=10.0)),
    "tyre": ("M_Tyre", "MI_QQ_Tyre", "M_QQ_Solid", dict(color=(0.022, 0.022, 0.024), rough=0.86, metal=0.0)),
    "alloy": ("M_Alloy", "MI_QQ_Alloy", "M_QQ_Paint",
              dict(color=(0.50, 0.51, 0.53), rough=0.30, metal=0.9, coat=0.6, coat_rough=0.08)),
    "wheel_inner": ("M_WheelInner", "MI_QQ_WheelInner", "M_QQ_Solid",
                    dict(color=(0.03, 0.03, 0.033), rough=0.6, metal=0.5)),
    "cap_black": ("M_BlackGloss", None, None, None),
    "lug": ("M_LugNut", "MI_QQ_LugNut", "M_QQ_Solid", dict(color=(0.7, 0.7, 0.72), rough=0.2, metal=1.0)),
    "brake_disc": ("M_BrakeDisc", "MI_QQ_BrakeDisc", "M_QQ_Solid",
                   dict(color=(0.16, 0.145, 0.13), rough=0.5, metal=1.0)),
    "brake_hat": ("M_BrakeHat", "MI_QQ_BrakeHat", "M_QQ_Solid",
                  dict(color=(0.12, 0.10, 0.09), rough=0.7, metal=0.6)),
    "caliper": ("M_Caliper", "MI_QQ_Caliper", "M_QQ_Solid", dict(color=(0.06, 0.06, 0.065), rough=0.5, metal=0.4)),
    "mirror_glass": ("M_MirrorGlass", "MI_QQ_MirrorGlass", "M_QQ_Solid",
                     dict(color=(0.8, 0.82, 0.85), rough=0.02, metal=1.0)),
    "badge_dark": ("M_BadgeDark", "MI_QQ_BadgeDark", "M_QQ_Solid",
                   dict(color=(0.02, 0.02, 0.025), rough=0.2, metal=0.5)),
    "plate_front": ("M_PlateFront", "MI_QQ_PlateFront", "M_QQ_Plate",
                    dict(color=(0.9, 0.9, 0.9), rough=0.25, metal=0.0, decal="plate_front")),
    "plate_rear": ("M_PlateRear", "MI_QQ_PlateRear", "M_QQ_Plate",
                   dict(color=(0.9, 0.75, 0.0), rough=0.25, metal=0.0, decal="plate_rear")),
    "plate_edge": ("M_PlateEdge", "MI_QQ_PlateEdge", "M_QQ_Solid",
                   dict(color=(0.03, 0.03, 0.03), rough=0.4, metal=0.0)),
    # --- interior (from the owner's photos) --------------------------------
    "interior_dark": ("M_InteriorPlastic", "MI_QQ_InteriorPlastic", "M_QQ_Solid",
                      dict(color=(0.016, 0.016, 0.018), rough=0.62, metal=0.0, normal=("grain_normal", 0.35),
                           uv_tiling=25.0)),
    "int_soft": ("M_InteriorSoft", "MI_QQ_InteriorSoft", "M_QQ_Solid",
                 dict(color=(0.020, 0.020, 0.022), rough=0.55, metal=0.0, normal=("grain_normal", 0.5),
                      uv_tiling=18.0)),
    "int_grey": ("M_InteriorGrey", "MI_QQ_InteriorGrey", "M_QQ_Solid",
                 dict(color=(0.040, 0.040, 0.043), rough=0.6, metal=0.0, normal=("grain_normal", 0.35),
                      uv_tiling=25.0)),
    "door_card": ("M_DoorCard", "MI_QQ_DoorCard", "M_QQ_Solid",
                  dict(color=(0.024, 0.024, 0.026), rough=0.66, metal=0.0, normal=("grain_normal", 0.35),
                       uv_tiling=25.0)),
    "headliner": ("M_Headliner", "MI_QQ_Headliner", "M_QQ_Solid",
                  dict(color=(0.42, 0.42, 0.41), rough=0.95, metal=0.0, normal=("seat_fabric_normal", 0.25),
                       uv_tiling=40.0)),
    "pillar_trim": ("M_PillarTrim", "MI_QQ_PillarTrim", "M_QQ_Solid",
                    dict(color=(0.33, 0.33, 0.325), rough=0.7, metal=0.0, normal=("grain_normal", 0.25),
                         uv_tiling=25.0)),
    "carpet": ("M_Carpet", "MI_QQ_Carpet", "M_QQ_Solid",
               dict(color=(0.022, 0.022, 0.023), rough=1.0, metal=0.0, normal=("seat_fabric_normal", 0.6),
                    uv_tiling=60.0)),
    "int_silver": ("M_InteriorSatin", "MI_QQ_InteriorSatin", "M_QQ_Solid",
                   dict(color=(0.55, 0.56, 0.58), rough=0.28, metal=1.0)),
    "leather": ("M_Leather", "MI_QQ_Leather", "M_QQ_Solid",
                dict(color=(0.017, 0.017, 0.018), rough=0.45, metal=0.0, normal=("grain_normal", 0.6),
                     uv_tiling=40.0)),
    "seat": ("M_SeatFabric", "MI_QQ_SeatFabric", "M_QQ_Solid",
             dict(color=(0.016, 0.016, 0.018), rough=0.95, metal=0.0, normal=("seat_fabric_normal", 0.3),
                  uv_tiling=45.0)),
    "seat_centre": ("M_SeatFabricPattern", "MI_QQ_SeatFabricPattern", "M_QQ_Grille",
                    dict(color=(0.07, 0.07, 0.075), rough=0.92, metal=0.0, tiled="seat_fabric_base",
                         normal=("seat_fabric_normal", 0.45), uv_tiling=25.0)),
    "belt": ("M_SeatBelt", "MI_QQ_SeatBelt", "M_QQ_Solid",
             dict(color=(0.03, 0.03, 0.032), rough=0.75, metal=0.0)),
    "stack_panel": ("M_CentreStack", "MI_QQ_CentreStack", "M_QQ_Plate",
                    dict(color=(0.1, 0.1, 0.1), rough=0.18, metal=0.0, decal="stack_panel")),
    "dials": ("M_Dials", "MI_QQ_Dials", "M_QQ_Plate",
              dict(color=(0.1, 0.1, 0.1), rough=0.3, metal=0.0, decal="dials")),
    "switches": ("M_WheelSwitches", "MI_QQ_WheelSwitches", "M_QQ_Plate",
                 dict(color=(0.5, 0.5, 0.5), rough=0.35, metal=0.0, decal="switches")),
}

# textures: key -> (file name, is a normal map)
TEXTURES = {
    "plate_front": ("T_Plate_Front.png", False),
    "plate_rear": ("T_Plate_Rear.png", False),
    "honeycomb_base": ("T_Honeycomb_BaseColor.png", False),
    "honeycomb_normal": ("T_Honeycomb_Normal.png", True),
    "grain_normal": ("T_PlasticGrain_Normal.png", True),
    "seat_fabric_base": ("T_SeatFabric_BaseColor.png", False),
    "seat_fabric_normal": ("T_SeatFabric_Normal.png", True),
    "stack_panel": ("T_Interior_Stack.png", False),       # drawn by make_interior_textures.py
    "dials": ("T_Interior_Dials.png", False),
    "switches": ("T_Interior_Switches.png", False),
}
ASSETS = os.path.join(HERE, "assets")


def to_unreal(v):
    """Blender metres -> Unreal cm (FBX default axes: UE = (x, -y, z) * 100)."""
    return [round(v[0] * 100.0, 3), round(-v[1] * 100.0, 3), round(v[2] * 100.0, 3)]


# ---------------------------------------------------------------------------
# Textures and materials
# ---------------------------------------------------------------------------
def write_image(path, arr, is_data, fmt="PNG", quality=92):
    h, w = arr.shape[:2]
    img = bpy.data.images.new(os.path.basename(path), width=w, height=h, alpha=False, is_data=is_data)
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = arr[..., None] if arr.ndim == 2 else arr
    img.pixels.foreach_set(rgba[::-1].ravel())          # Blender rows start at the bottom
    img.filepath_raw = path
    img.file_format = fmt
    img.save(quality=quality) if fmt == "JPEG" else img.save()
    bpy.data.images.remove(img)
    loaded = bpy.data.images.load(path)
    if is_data:
        loaded.colorspace_settings.name = "Non-Color"
    return loaded


def make_textures(tex_dir):
    os.makedirs(tex_dir, exist_ok=True)
    front, rear = qt.plates(REG)
    hb, hr, hn = qt.honeycomb()
    fb, fn = qt.seat_fabric()
    made = {"plate_front": front, "plate_rear": rear, "honeycomb_base": hb, "honeycomb_normal": hn,
            "grain_normal": qt.grain(), "seat_fabric_base": fb, "seat_fabric_normal": fn}
    out = {}
    for key, (name, is_normal) in TEXTURES.items():
        path = os.path.join(tex_dir, name)
        if key in made:
            out[key] = write_image(path, made[key], is_normal)
        else:                                   # pre-drawn (lettering): copy from assets/
            shutil.copyfile(os.path.join(ASSETS, name), path)
            out[key] = bpy.data.images.load(path)
    return out


def _set(bsdf, name, value):
    if name in bsdf.inputs:
        bsdf.inputs[name].default_value = value


def make_materials(tex):
    mats = {}
    made = {}
    for key, (name, _, _, s) in MATS.items():
        if s is None:
            continue
        m = bpy.data.materials.new(name)
        if bpy.app.version < (5, 0, 0):
            m.use_nodes = True
        m.diffuse_color = (*s["color"], 1.0)
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        _set(bsdf, "Base Color", (*s["color"], 1.0))
        _set(bsdf, "Roughness", s["rough"])
        _set(bsdf, "Metallic", s["metal"])
        if s.get("coat"):
            _set(bsdf, "Coat Weight", s["coat"])
            _set(bsdf, "Coat Roughness", s.get("coat_rough", 0.03))
        if s.get("transmission"):
            _set(bsdf, "Transmission Weight", s["transmission"])
            _set(bsdf, "IOR", s.get("ior", 1.5))
        if s.get("emission"):
            _set(bsdf, "Emission Color", (*s["emission"], 1.0))
            _set(bsdf, "Emission Strength", s.get("emit", 0.0))
        if s.get("decal"):
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = tex[s["decal"]]
            t.location = (-500, 200)
            nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if s.get("tiled") or s.get("normal"):
            # UVs are 1 unit per metre; tile the texture (glTF: KHR_texture_transform)
            uvn = nt.nodes.new("ShaderNodeTexCoord")
            uvn.location = (-1100, -100)
            mp = nt.nodes.new("ShaderNodeMapping")
            mp.location = (-900, -100)
            t = s["uv_tiling"]
            mp.inputs["Scale"].default_value = (t, t, 1.0)
            nt.links.new(uvn.outputs["UV"], mp.inputs["Vector"])
            if s.get("normal"):
                key, strength = s["normal"]
                tn = nt.nodes.new("ShaderNodeTexImage")
                tn.image = tex[key]
                tn.location = (-600, -300)
                nt.links.new(mp.outputs["Vector"], tn.inputs["Vector"])
                nm = nt.nodes.new("ShaderNodeNormalMap")
                nm.inputs["Strength"].default_value = strength
                nm.location = (-300, -300)
                nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
                nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
            if s.get("tiled"):
                tb = nt.nodes.new("ShaderNodeTexImage")
                tb.image = tex[s["tiled"]]
                tb.location = (-600, 200)
                nt.links.new(mp.outputs["Vector"], tb.inputs["Vector"])
                nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
        made[name] = m
    for key, (name, _, _, _) in MATS.items():
        mats[key] = made[name]
    return mats


def ue_materials():
    """Blender material name -> UE instance / parent / parameters."""
    out = {}
    for key, (name, inst, parent, s) in MATS.items():
        if s is None or name in out:
            continue
        textures = {}
        if s.get("decal"):
            textures["PlateTexture"] = s["decal"]
        if parent == "M_QQ_Grille":
            textures["BaseColorMap"] = s["tiled"]
            textures["NormalMap"] = s["normal"][0]
        elif s.get("normal"):
            textures["DetailNormal"] = s["normal"][0]
        out[name] = {"ue_instance": inst, "ue_parent": parent, "base_color_linear": list(s["color"]),
                     "roughness": s["rough"], "metallic": s["metal"],
                     "clear_coat": s.get("coat", 0.0), "clear_coat_roughness": s.get("coat_rough", 0.0),
                     "opacity": s.get("opacity", 1.0),
                     "emissive": [c * s.get("emit", 0.0) for c in s.get("emission", (0, 0, 0))],
                     "textures": textures,
                     "detail_normal_strength": s["normal"][1] if s.get("normal") and parent == "M_QQ_Solid" else 0.0,
                     "uv_tiling": s.get("uv_tiling", 1.0)}
    return out


# ---------------------------------------------------------------------------
# Body shell and the parts cut from it
# ---------------------------------------------------------------------------
def build_body(surf, log):
    halves = []
    for side in (1, -1):
        t0 = time.time()
        halves.append(bb.Half(surf, side))
        log("  %s side: %d faces (%.1f s)" % ("left" if side > 0 else "right", len(halves[-1].faces),
                                              time.time() - t0))
    body = bb.MeshData("SM_Qashqai_Body")
    glass = bb.MeshData("SM_Qashqai_Glass")
    lenses = bb.MeshData("SM_Qashqai_Lenses")
    for h in halves:
        # shell (paint and flush trims); the underside is dark
        ids = h.select(lambda c: c[0] == "shell")
        zc = np.array([h.P[h.faces[k], 2].mean() for k in ids])
        nz = np.array([h.N[h.faces[k], 2].mean() for k in ids])
        under = {k for k, z, n in zip(ids, zc, nz) if z < 0.33 and n < -0.45}

        def shell_mat(k, h=h, under=under):
            m = h.cls[k][1]
            return "underbody" if (m == "paint" and k in under) else m
        body.add_faces_from(h, ids, shell_mat)
        # glass sits 4 mm inside the opening, with a dark reveal
        ids = h.select(lambda c: c[0] == "glass")
        bb.add_region_part(glass, h, ids, lambda k, h=h: h.cls[k][1], disp=lambda v: np.full(len(v), -0.004))
        for name in ("glass_f", "glass_r", "glass_q", "ws", "rg"):
            reg = [k for k in ids if name in h.labels[k]]
            bb.reveal(body, h, reg, depth=0.012, mat="frit" if name in ("ws", "rg") else "black_gloss")
        # arch mouldings
        for which in ("front", "rear"):
            reg = [k for k, c in enumerate(h.cls) if c[0] == "trim" and ("trim_" + which) in h.labels[k]]
            bb.trim_part(body, h, reg, lift=0.004, lip=0.045)
        build_lamps(body, lenses, h)
        build_grilles(body, h)
    return halves, body, glass, lenses


def build_lamps(body, lenses, h):
    # headlamp: clear lens over a satin silver housing with two reflector
    # bowls, a black shade along the top and the LED daytime strip
    ids = h.select(lambda c: c[0] == "headlamp")
    bb.add_region_part(lenses, h, ids, lambda k: "lens_clear", disp=lambda v: np.full(len(v), 0.0012))
    bb.recess(body, h, ids, 0.026, "lamp_chrome", "lamp_black")
    headlamp_internals(body, h, ids)
    # tail lamp: red lens with the clear reversing-lamp band, dark red housing
    ids = h.select(lambda c: c[0] == "taillamp")
    bb.add_region_part(lenses, h, ids, lambda k: "tail_clear" if "tl_white" in h.labels[k] else "tail_red",
                       disp=lambda v: np.full(len(v), 0.0012))
    bb.recess(body, h, ids, 0.025, "tail_inner", "tail_inner")
    # fog lamp opening: dark pocket behind the lamp unit
    ids = h.select(lambda c: c[0] == "fog")
    bb.recess(body, h, ids, 0.030, "lamp_black", "lamp_black")


def lamp_edge_path(h, ab, inward, back, step=0.012):
    """A smooth path just inside a lamp outline: the outline points (a, b)
    moved `inward` along the surface (towards the lamp's middle, which is
    roughly up for the lower edge and down for the upper edge) and `back`
    behind the surface.  Returns points and the surface normals."""
    P = h.shell.eval(ab[:, 0], ab[:, 1])
    N = h.shell.base_normal(ab[:, 0], ab[:, 1])
    z = np.array([0.0, 0.0, 1.0])
    T = z - N * (N @ z)[:, None]
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    Q = P + T * inward - N * back
    for _ in range(4):                                   # iron out small wiggles
        Q[1:-1] = 0.5 * Q[1:-1] + 0.25 * (Q[:-2] + Q[2:])
    seg = np.linalg.norm(np.diff(Q, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(2, int(math.ceil(s[-1] / step)) + 1)
    si = np.linspace(0.0, s[-1], n)
    Qi = np.column_stack([np.interp(si, s, Q[:, k]) for k in range(3)])
    Ni = np.column_stack([np.interp(si, s, N[:, k]) for k in range(3)])
    Ni /= np.linalg.norm(Ni, axis=1, keepdims=True)
    return Qi, Ni


def headlamp_internals(body, h, ids):
    """Reflector bowls, the LED daytime strip along the lower edge and a
    black shade along the upper edge, all behind the lens."""
    vids = np.array(sorted({v for k in ids for v in h.faces[k]}))
    P = h.P[vids]
    N = h.N[vids]
    c = P.mean(0)
    n = N.mean(0)
    n /= np.linalg.norm(n)
    # main axis of the lamp outline
    Q = P - c
    Q -= np.outer(Q @ n, n)
    _, _, vt = np.linalg.svd(Q, full_matrices=False)
    ax = vt[0]
    if ax[1] * h.side < 0:                   # point outwards (towards the wing)
        ax = -ax
    proj = Q @ ax
    lo, hi = proj.min(), proj.max()
    kit = mk.Kit("hl")
    for t, r in ((0.40, 0.036), (0.62, 0.042)):
        p0 = c + ax * (lo + (hi - lo) * t)
        k = np.argmin(np.linalg.norm(P - p0, axis=1))
        o, u, v, nn = mk.frame_from(P[k] - n * 0.028, n)
        rings = []
        for rr, zz in ((r, 0.018), (r * 0.80, 0.006), (r * 0.45, -0.008), (r * 0.15, -0.012)):
            rings.append([o + u * rr * math.cos(a) + v * rr * math.sin(a) + nn * zz
                          for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)])
        kit.loft(rings[::-1], "lamp_reflector", closed=True, caps=False)
        bulb = [o + u * 0.012 * math.cos(a) + v * 0.012 * math.sin(a) + nn * 0.004
                for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)]
        kit.fan(bulb, o + nn * 0.016, "lens_clear")
    hl = h.spec.regions["hl"]
    n_per = 6
    # LED strip: along the lower edge (outline points 1-9), 9 mm behind the lens
    path, pn = lamp_edge_path(h, hl[1 * n_per:9 * n_per + 1], inward=0.010, back=0.009)
    kit.sweep([(-0.0035, -0.0015), (0.0035, -0.0015), (0.0035, 0.0015), (-0.0035, 0.0015)],
              path, pn, "led")
    # black shade just behind the lens along the upper edge (points 12-19)
    path, pn = lamp_edge_path(h, hl[12 * n_per:19 * n_per + 1], inward=-0.009, back=0.004)
    kit.sweep([(-0.009, -0.001), (0.009, -0.001), (0.009, 0.001), (-0.009, 0.001)],
              path, pn, "lamp_black")
    kit_into(body, kit)


def kit_into(md, kit):
    """Append a Kit to a MeshData with smooth-by-angle corner normals."""
    if not kit.faces:
        return
    verts = [tuple(v) for v in kit.verts]
    md.add(verts, kit.faces, kit.mats, kit.corner_normals(), kit.uvs)


def build_grilles(body, h):
    # upper grille: honeycomb recessed 35 mm behind the opening
    ids = h.select(lambda c: c[0] == "grille")
    bb.recess(body, h, ids, 0.035, "grille", "lamp_black")
    ids = h.select(lambda c: c[0] == "grille_low")
    bb.recess(body, h, ids, 0.030, "grille", "lamp_black")
    # two horizontal slats across the lower grille
    S = h.spec
    for z in (0.352, 0.405):
        slat = np.array([(0.0, z - 0.008), (0.585, z - 0.008), (0.585, z + 0.008), (0.0, z + 0.008)])
        xs = S.view_poly("front", slat)
        bb.surface_patch(body, h, xs, offset=-0.010, mat="black_gloss", thickness=0.018)
    # chrome V over the grille
    low = np.array(F.CHROME_V_LOW)
    high = np.array(F.CHROME_V_HIGH)
    band = np.vstack([low, high[::-1]])
    poly = S.view_poly("front", band)
    bb.surface_patch(body, h, poly, offset=0.006, mat="chrome", thickness=0.016)


# ---------------------------------------------------------------------------
# Procedural parts placed on the shell
# ---------------------------------------------------------------------------
def shell_point(h, view, c):
    ab = h.spec.mp.map([(view, c[0], c[1])])
    P = h.shell.eval(ab[:, 0], ab[:, 1])[0]
    N = h.shell.normal(ab[:, 0], ab[:, 1])[0]
    return P, N


def build_parts(halves, surf):
    left, right = halves
    kit = mk.Kit("parts")
    # wheel-well liners
    for h, side in ((left, 1.0), (right, -1.0)):
        for which in ("front", "rear"):
            arch = bm.densify(F.arch_polyline(which), 0.02, closed=False)
            ab = h.spec.mp.map([("side", x, z) for x, z in arch])
            pts = h.shell.eval(ab[:, 0], ab[:, 1])
            qp.build_liner(kit, pts, None, which, side)
        # mirrors
        m = mk.Kit("mirror")
        qp.build_mirror(m, side)
        kit.merge(m)
        # handles
        for (x, z) in F.HANDLES:
            P, N = shell_point(h, "side", (x, z))
            qp.build_handle(kit, P, N, side)
    # badges
    P, N = shell_point(left, "front", (0.0, F.LOGO_FRONT["z"]))
    Nf = np.array([1.0, 0.0, 0.25])
    qp.build_logo(kit, mk.frame_from(P - np.array([0.012, 0, 0]), Nf), F.LOGO_FRONT["d"], depth=0.012)
    P, N = shell_point(left, "rear", (0.0, F.LOGO_REAR["z"]))
    qp.build_logo(kit, mk.frame_from(P, np.array([-1.0, 0.0, N[2]])), F.LOGO_REAR["d"], depth=0.008)
    # model badge on the tailgate
    b = F.BADGE_REAR
    V, faces = qp.text_mesh(b["text"], b["cap"], b["depth"], b["spacing"])
    h = left if b["y"] > 0 else right
    ab = h.spec.mp.map([("rear", abs(b["y"] - x), b["z"] + y) for x, y, _ in V])
    P = h.shell.eval(ab[:, 0], ab[:, 1])
    N = h.shell.normal(ab[:, 0], ab[:, 1])
    kit.add(P + N * (0.0008 + V[:, 2:3]), faces, "chrome", sharp=False)
    # number plates
    P, N = shell_point(left, "front", (0.0, F.PLATE_FRONT["z"]))
    tilt = math.radians(3.0)
    nf = np.array([math.cos(tilt), 0.0, math.sin(tilt)])
    fr = mk.frame_from(P + nf * 0.012, nf)
    qp.build_plate(kit, fr, "plate_front")
    holder = mk.frame_from(P + nf * 0.008, nf)
    kit.prism(mk.rounded_rect2d(0.528, 0.118, 0.010), -0.045, 0.0, holder, "plate_edge", cap0=False)
    P, N = shell_point(left, "rear", (0.0, F.PLATE_REAR["z"]))
    nr = np.array([N[0], 0.0, N[2]])
    nr /= np.linalg.norm(nr)
    qp.build_plate(kit, mk.frame_from(P + nr * 0.005, nr, (0, 0, 1)), "plate_rear")
    # fog lamps
    c, n = bb.fog_frame(left.spec)
    for side in (1.0, -1.0):
        cc = c * np.array([1, side, 1])
        nn = n * np.array([1, side, 1])
        qp.build_fog(kit, cc + nn * 0.002, nn, F.FOG["w"], F.FOG["h"], F.FOG["ring"])
    # rear reflectors and high-level brake light
    for side in (1.0, -1.0):
        P, N = shell_point(left, "rear", (F.REFLECTOR["y"], F.REFLECTOR["z"]))
        P = P * np.array([1, side, 1])
        N = N * np.array([1, side, 1])
        fr = mk.frame_from(P, N)
        kit.prism(mk.rounded_rect2d(F.REFLECTOR["w"], F.REFLECTOR["h"], 0.006), -0.004, 0.003, fr, "reflector")
    P, N = shell_point(left, "rear", (0.0, F.BRAKE_LIGHT["z"]))
    fr = mk.frame_from(P, N)
    kit.prism(mk.rounded_rect2d(F.BRAKE_LIGHT["w"], F.BRAKE_LIGHT["h"], 0.006), -0.004, 0.004, fr, "brake_light")
    # aerial on the roof
    P, N = shell_point(left, "top", (-1.56, 0.0))
    kit.box(tuple(P + np.array([0, 0, 0.012])), (0.07, 0.035, 0.03), "black_plastic")
    path = [P + np.array([-0.01, 0, 0.02]) + np.array([-math.sin(math.radians(52)), 0,
                                                       math.cos(math.radians(52))]) * t for t in np.linspace(0, 0.24, 6)]
    kit.sweep(list(zip(0.0045 * np.cos(np.linspace(0, 2 * np.pi, 8, endpoint=False)),
                       0.0045 * np.sin(np.linspace(0, 2 * np.pi, 8, endpoint=False)))),
              path, [np.array([1.0, 0, 0.6])] * len(path), "black_plastic")
    # wipers
    build_wipers(kit, left)
    # brake calipers (fixed to the knuckles)
    cal = qp.build_caliper()
    for (x, y), side in ((F.wheel_centres()[0], 1), (F.wheel_centres()[1], 1),
                         (F.wheel_centres()[0], -1), (F.wheel_centres()[1], -1)):
        M = Matrix.Translation((x, y * side, F.WHEEL_Z)) @ Matrix.Scale(side, 4, (0, 1, 0))
        c = mk.Kit("c")
        c.merge(cal, M)
        if side < 0:
            c.faces = [f[::-1] for f in c.faces]
        kit.merge(c)
    return kit


def build_wipers(kit, h):
    """Two front wipers parked along the base of the windscreen, one rear."""
    for y0, y1, x_off in ((-0.62, 0.02, 0.0), (0.06, 0.66, 0.018)):
        pts = []
        for t in np.linspace(0.0, 1.0, 9):
            y = y0 + (y1 - y0) * t
            x = 1.050 - 0.030 * t - x_off
            P, N = shell_point(h, "top", (x, max(abs(y), 1e-4)))
            if y < 0:
                P = P * np.array([1, -1, 1])
                N = N * np.array([1, -1, 1])
            pts.append((P + N * 0.018, N))
        path = [p for p, _ in pts]
        ups = [n for _, n in pts]
        kit.sweep([(-0.009, -0.006), (0.009, -0.006), (0.004, 0.008), (-0.004, 0.008)], path, ups,
                  "black_plastic")
    # rear wiper on the tailgate glass
    base, n0 = shell_point(h, "rear", (0.0, 1.232))
    tip, n1 = shell_point(h, "rear", (0.30, 1.40))
    path = [base + (tip - base) * t + (n0 * (1 - t) + n1 * t) * 0.02 for t in np.linspace(0, 1, 6)]
    ups = [n0 * (1 - t) + n1 * t for t in np.linspace(0, 1, 6)]
    kit.sweep([(-0.008, -0.005), (0.008, -0.005), (0.004, 0.008), (-0.004, 0.008)], path, ups,
              "black_plastic")
    kit.box(tuple(base + n0 * 0.015), (0.04, 0.05, 0.04), "black_plastic")


# ---------------------------------------------------------------------------
# Scene assembly and export
# ---------------------------------------------------------------------------
def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def make_hulls(body_ob, collection):
    """Convex UCX_ hulls: lower body front/rear halves and the cabin."""
    me = body_ob.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    parts = [
        ("lower_front", (co[:, 2] < 1.02) & (co[:, 0] > -0.05)),
        ("lower_rear", (co[:, 2] < 1.02) & (co[:, 0] < 0.05)),
        ("cabin", (co[:, 2] > 0.95) & (co[:, 0] < 1.15) & (co[:, 0] > -2.0)),
    ]
    obs = []
    for i, (name, m) in enumerate(parts):
        pts = co[m]
        bmh = bmesh.new()
        for p in pts[:: max(1, len(pts) // 4000)]:
            bmh.verts.new(p)
        bmesh.ops.convex_hull(bmh, input=bmh.verts)
        # drop interior leftovers
        loose = [v for v in bmh.verts if not v.link_faces]
        bmesh.ops.delete(bmh, geom=loose, context="VERTS")
        mh = bpy.data.meshes.new("UCX_%s_%02d" % (body_ob.name, i))
        bmh.to_mesh(mh)
        bmh.free()
        ob = bpy.data.objects.new(mh.name, mh)
        collection.objects.link(ob)
        ob.display_type = "WIRE"
        ob.hide_render = True
        obs.append(ob)
    return obs


def op_kwargs(op, **kw):
    """Drop keyword arguments an operator doesn't know (API drift between versions)."""
    props = op.get_rna_type().properties.keys()
    return {k: v for k, v in kw.items() if k in props}


def select_only(objs):
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_fbx(path, objs):
    select_only(objs)
    op = bpy.ops.export_scene.fbx
    op(**op_kwargs(op, filepath=path, use_selection=True, object_types={"MESH"},
                   global_scale=1.0, apply_unit_scale=True,
                   apply_scale_options="FBX_SCALE_NONE", axis_forward="-Z", axis_up="Y",
                   use_mesh_modifiers=True, mesh_smooth_type="FACE", use_tspace=False,
                   use_custom_props=False, add_leaf_bones=False, bake_anim=False,
                   path_mode="STRIP", embed_textures=False))


def export_glb(path, objs):
    select_only(objs)
    op = bpy.ops.export_scene.gltf
    op(**op_kwargs(op, filepath=path, export_format="GLB", use_selection=True,
                   export_apply=True, export_yup=True, export_texcoords=True,
                   export_normals=True, export_materials="EXPORT",
                   export_image_format="AUTO", export_jpeg_quality=90,
                   export_cameras=False, export_lights=False, export_extras=False))


def triangle_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ob.evaluated_get(dg).to_mesh_clear()
    return n


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    return scene


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.normpath(os.path.join(HERE, "..", "export")))
    ap.add_argument("--blend", default=os.path.normpath(os.path.join(HERE, "..", "blend", "Qashqai.blend")))
    ap.add_argument("--renders", default=os.path.normpath(os.path.join(HERE, "..", "renders")))
    ap.add_argument("--ds", type=float, default=MESH_DS, help="body grid spacing in metres")
    ap.add_argument("--render", action="store_true", help="render preview images (Cycles)")
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--views", default="", help="comma separated subset of views to render")
    ap.add_argument("--jpeg", type=int, default=0, metavar="QUALITY",
                    help="save renders as JPEG with this quality instead of PNG")
    ap.add_argument("--no-export", action="store_true")
    ap.add_argument("--no-interior", action="store_true")
    args = ap.parse_args(argv)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    t_start = time.time()

    def log(msg):
        print("[%6.1fs] %s" % (time.time() - t_start, msg), flush=True)

    scene = reset_scene()
    tex = make_textures(os.path.join(out, "textures"))
    mats = make_materials(tex)
    root = new_collection("Qashqai")
    col_coll = new_collection("Collision (UCX)", root)

    log("body shell")
    surf = qb.Surface(args.ds)
    halves, body_md, glass_md, lens_md = build_body(surf, log)
    log("parts")
    kit = build_parts(halves, surf)
    kit_into(body_md, kit)
    objects = {}
    objects["SM_Qashqai_Body"] = body_md.to_object(root, mats)
    objects["SM_Qashqai_Glass"] = glass_md.to_object(root, mats)
    objects["SM_Qashqai_Lenses"] = lens_md.to_object(root, mats)
    if not args.no_interior:
        log("interior")
        ik = mk.Kit("SM_Qashqai_Interior")
        qi.build_interior(ik, log, lining_ds=max(qi.LINING_DS, args.ds * 1.6))
        objects["SM_Qashqai_Interior"] = ik.to_object(root, mats)
    wheel_mesh = qp.build_wheel().to_object(root, mats)
    wheel_mesh.name = "SM_Qashqai_Wheel"
    objects["SM_Qashqai_Wheel"] = wheel_mesh
    # four wheel instances for the scene (linked duplicates)
    wheels = {}
    for tag, (x, y), side in (("FL", F.wheel_centres()[0], 1), ("FR", F.wheel_centres()[0], -1),
                              ("RL", F.wheel_centres()[1], 1), ("RR", F.wheel_centres()[1], -1)):
        ob = bpy.data.objects.new("Wheel_" + tag, wheel_mesh.data)
        ob.location = (x, y * side, F.WHEEL_Z)
        ob.rotation_euler = (0.0, 0.0, 0.0 if side > 0 else math.pi)
        root.objects.link(ob)
        wheels[tag] = ob
    wheel_mesh.hide_render = True
    wheel_mesh.hide_viewport = True
    ucx = make_hulls(objects["SM_Qashqai_Body"], col_coll)
    log("objects built")

    manifest = {
        "name": "Nissan Qashqai 2017 (J11 pre-facelift), Gun Metallic, reg DE17 YAU",
        "units": "centimetres",
        "overall_cm": {"length_x": round((qb.X_F - qb.X_R) * 100, 1), "width_y": 180.6, "height_z": 159.0,
                       "wheelbase": 264.6},
        "pivot": "ground level, midway between the axles, on the centre line",
        "unreal_mapping": "UE(x, y, z) = Blender(x, -y, z) * 100 (FBX -Z forward / Y up)",
        "materials": ue_materials(),
        "textures": {key: {"file": "textures/" + name, "kind": "normal" if is_normal else "color"}
                     for key, (name, is_normal) in TEXTURES.items()},
        "normal_map_convention": "OpenGL (+Y); flip green in Unreal",
        "wheels": {tag: {"blender_m": [round(c, 4) for c in ob.location], "unreal_cm": to_unreal(ob.location),
                         "yaw_deg_unreal": 0.0 if tag.endswith("L") else 180.0} for tag, ob in wheels.items()},
        "wheel_radius_cm": round(qp.TYRE_R * 100, 2),
        "parts": [],
    }

    if not args.no_export:
        log("exporting")
        for name, ob in objects.items():
            objs = [ob] + (ucx if name == "SM_Qashqai_Body" else [])
            hidden = ob.hide_viewport
            ob.hide_viewport = False
            export_fbx(os.path.join(out, name + ".fbx"), objs)
            ob.hide_viewport = hidden
        render_objs = [o for n, o in objects.items() if n != "SM_Qashqai_Wheel"] + list(wheels.values())
        # the FBX exporter mixes up material slots on shared meshes: give each
        # wheel its own copy for the combined file (glTF keeps the instancing)
        shared = wheel_mesh.data
        for ob in wheels.values():
            ob.data = shared.copy()
        export_fbx(os.path.join(out, "Qashqai.fbx"), render_objs)
        for ob in wheels.values():
            copy = ob.data
            ob.data = shared
            bpy.data.meshes.remove(copy)
        export_glb(os.path.join(out, "Qashqai.glb"), render_objs)

    for name, ob in objects.items():
        manifest["parts"].append({
            "name": name,
            "fbx": name + ".fbx",
            "material_slots": [{"slot": m.name, "ue_instance": manifest["materials"][m.name]["ue_instance"]}
                               for m in ob.data.materials],
            "collision_hulls": len(ucx) if name == "SM_Qashqai_Body" else 0,
            "triangles": triangle_count(ob),
        })
    with open(os.path.join(out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    col_coll.hide_render = True
    if args.render:
        import render_views
        render_views.render_all(scene, objects, wheels, args.renders, args.samples,
                                [v for v in args.views.split(",") if v], args.jpeg or None)
    col_coll.hide_viewport = True
    os.makedirs(os.path.dirname(os.path.abspath(args.blend)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(args.blend), relative_remap=True, compress=True)
    total = sum(p["triangles"] for p in manifest["parts"])
    log("built %d meshes, %d triangles -> %s" % (len(objects), total, out))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
