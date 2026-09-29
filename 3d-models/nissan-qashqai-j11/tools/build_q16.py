"""Static Nissan Qashqai J11 from the BeamNG 'qashqai16' package (FastLane),
default configuration nconnecta_16dci_m, changed only where the owner's car
differs: Gun Metallic paint (the package's own paint definition), UK number
plates DE17 YAU (white front, yellow rear) and right-hand drive (the
package's own _rhd parts).

    python build_q16.py OUTDIR

Writes OUTDIR/blender/Qashqai_J11_DE17YAU.blend (+ textures), the UE5
package in OUTDIR/unreal (FBX parts, textures, manifest.json) and
OUTDIR/Qashqai_J11_DE17YAU.glb.  The package has no tyres or JBeam (they come
from BeamNG's common content), so tyres of the configured size are generated
and the wheels are placed at the hubs on the J11's track."""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "nissan-qashqai", "blender"))   # plate_texture.py

import numpy as np
import bpy
from mathutils import Matrix, Vector

import bngmat
import config
import dts31
import dtsblend
import matconv
import plate_texture

PKG = os.path.join(bngmat.ROOT, "vehicles")
NAME = "Qashqai_J11_DE17YAU"
REG = "DE17 YAU"
TRACK_F, TRACK_R = 1.565, 1.550          # J11 track widths (m)
TYRE = (0.235, 0.50, 18)                 # 235/50 R18 from the configuration
t0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - t0), *a, flush=True)


# ---------------------------------------------------------------------------
# What the configuration uses, and what the package leaves to BeamNG's
# JBeam/common files
# ---------------------------------------------------------------------------
# Lamp materials are placeholders that BeamNG swaps at run time (JBeam
# glowMap); with the lights off they show these materials.  The mapping was
# checked by sampling each lamp's UVs against the package's lamp bakes.
GLOW_OFF = {n: "qashqai16_lights" for n in (
    "qashqai16_drl", "qashqai16_lowbeam", "qashqai16_highbeam", "qashqai16_signal_L", "qashqai16_signal_R",
    "qashqai16_taillight", "qashqai16_brakelight", "qashqai16_reverselight", "qashqai16_foglight_red",
    "qashqai16_foglight", "qashqai16_chmsl", "qashqai16_signal_L_instant", "qashqai16_signal_R_instant")}
GLOW_OFF.update({n: "qashqai16_chrome" for n in (
    "qashqai16_headlight_frame", "qashqai16_domelight_F", "qashqai16_domelight_FL", "qashqai16_domelight_FR",
    "qashqai16_domelight_RL", "qashqai16_domelight_RR", "qashqai16_domelight_trunk")})
GLOW_OFF.update({n: "qashqai16_glass_domelight" for n in (
    "qashqai16_glass_domelight_F", "qashqai16_glass_domelight_FL", "qashqai16_glass_domelight_FR",
    "qashqai16_glass_domelight_RL", "qashqai16_glass_domelight_RR", "qashqai16_glass_domelight_trunk")})
GLOW_OFF.update({"qashqai16_buttons4_off": "qashqai16_buttons4", "qashqai16_buttons4_hazard": "qashqai16_buttons4",
                 "qashqai16_buttons5_off": "qashqai16_buttons5"})
GLOW_OFF.update({n: "@screen_off" for n in (
    "qashqai16_gauges_screen", "qashqai16_gauges_screen_b", "qashqai16_gps_screen", "qashqai16_gps_screen_data2",
    "qashqai16_doorajar_FL", "qashqai16_doorajar_FR", "qashqai16_doorajar_RL", "qashqai16_doorajar_RR")})
GLOW_OFF.update({n: "@indicator_off" for n in (
    "qashqai16_spec3", "qashqai16_spec4", "qashqai16_spec6", "qashqai16_spec7", "qashqai16_spec8")})

# skins chosen by the configuration (skin_* slots)
SKINS = {
    "qashqai16_seat_material": "qashqai16_seat_material.skin_seat_material.cloth_seat_material",
    "qashqai16_seat_trim": "qashqai16_seat_trim.skin_seat_trim.cloth_seat_trim",
    "qashqai16_bumper_trim": "qashqai16_bumper_trim.skin_trim_bumpers.chrome_trim_bumpers",
    "qashqai16_black4": "qashqai16_black4.skin_trim_ext.chrome_trim_ext",
    "qashqai16_black5": "qashqai16_black5.skin_trim_ext.chrome_trim_ext",
}

# warning-light decals on the instrument cluster: glow-only, invisible when off
SKIP = {"qashqai16_decals_gauges_rhd"}

# these lamp meshes already have vehicle-space vertices; their nodes carry a
# stray 2.632 m lift that BeamNG never applies (flexbodies are placed from
# their vertex data)
NO_NODE = {"qashqai16_taillight_L", "qashqai16_taillight_R", "qashqai16_tailgate_a_light_L",
           "qashqai16_tailgate_a_light_R"}

ROT = Matrix.Rotation(math.radians(90.0), 4, "Z")   # BeamNG (-Y forward) -> Blender (+X forward)


def short(name):
    s = name.replace("qashqai16_", "").replace("qashqai16", "body")
    for a, b in ((".skin_seat_material.cloth_seat_material", "_cloth"), (".skin_seat_trim.cloth_seat_trim", "_cloth"),
                 (".skin_trim_bumpers.chrome_trim_bumpers", "_chrome"), (".skin_trim_ext.chrome_trim_ext", "_chrome")):
        s = s.replace(a, b)
    return "M_" + "".join(c if c.isalnum() else "_" for c in s)


class Materials:
    def __init__(self, texdir):
        self.defs = bngmat.load_all()
        self.store = matconv.TextureStore(texdir)
        self.specs = {}          # final name -> spec
        self.bpy = {}            # final name -> bpy material
        self.log = {}            # dts material -> final name
        info = bngmat._load(os.path.join(PKG, "qashqai16", "info.json"))
        self.paint = info["paints"]["Gun Metallic"]

    # --- special materials -------------------------------------------------
    def paint_spec(self, name, source, normal_ref=None):
        p = self.paint
        s = matconv.new_spec(name, source)
        s["base"] = [float(v) for v in matconv.to_linear(p["baseColor"][:3])]
        s["metallic"] = float(p["metallic"])
        s["roughness"] = float(p["roughness"])
        s["coat"] = float(p["clearcoat"])
        s["coat_roughness"] = float(p["clearcoatRoughness"])
        if normal_ref:
            s["normal_map"] = matconv.normal(self.store, normal_ref, directx=False)
        return s

    def plate_spec(self, rear):
        name = "M_Plate_Rear" if rear else "M_Plate_Front"
        img = plate_texture.plate_image(REG, rear, px_per_mm=3.9, ss=3)
        key = self.store.put("T_Plate_%s_DE17YAU" % ("Rear" if rear else "Front"), img, "color")
        s = matconv.new_spec(name, "UK number plate %s (%s)" % (REG, "yellow rear" if rear else "white front"))
        s.update(base=[1.0, 1.0, 1.0], base_map=key, roughness=0.35, metallic=0.0)
        return s

    def special(self, key, name):
        s = matconv.new_spec(name)
        if key == "@screen_off":
            s.update(base=[0.004, 0.004, 0.005], roughness=0.18, source="display, switched off")
        elif key == "@indicator_off":
            s.update(base=[0.02, 0.02, 0.02], roughness=0.35, source="indicator lamp, switched off")
        elif key == "mirror":
            s.update(base=[0.9, 0.9, 0.9], metallic=1.0, roughness=0.02, source="BeamNG common 'mirror' (not in the package)")
        elif key == "grille_hex":
            path = bngmat.resolve("grille_hex_d.color.dds.002.dds")
            s["base"], s["base_map"] = matconv.colour(self.store, path, None)
            s["alpha"], s["alpha_map"] = matconv.opacity(self.store, path, None)
            s.update(blend="CLIP", alpha_cutoff=0.5, roughness=0.55, double_sided=True,
                     source="BeamNG common 'grille_hex' with the package's grille_hex_d texture")
        elif key == "qashqai16_mechanical":
            s.update(base=[0.035, 0.035, 0.037], metallic=0.4, roughness=0.6,
                     source="qashqai16_mechanical: its (vivace) textures are not in the package")
        elif key == "qashqai16_engine":
            s.update(base=[0.09, 0.09, 0.095], metallic=0.6, roughness=0.52,
                     source="qashqai16_engine: its (vivace) textures are not in the package")
        elif key == "qashqai16_pedals":
            s.update(base=[0.03, 0.03, 0.03], metallic=0.2, roughness=0.6,
                     source="qashqai16_pedals: its (vivace) textures are not in the package")
        elif key == "qashqai16_seat_material":
            # cloth: the fabric is a tiling detail map (default detail scale 2)
            # at the material's base colour
            d = self.defs[SKINS[key]]
            s0 = d["Stages"][0]
            a, path = self.store.load(s0["detailMap"])
            rgb = matconv.to_linear(a[..., :3])
            rgb = rgb * (float(s0["baseColorFactor"][0]) / rgb.mean())
            tiled = np.tile(matconv.to_srgb(rgb), (2, 2, 1))
            s["base"], s["base_map"] = [1.0, 1.0, 1.0], self.store.put("T_seatfabric_b_seat", tiled, "color", [path])
            n, npath = self.store.load(s0["detailNormalMap"])
            n = np.tile(n[..., :3], (2, 2, 1)).copy()
            n[..., 1] = 1.0 - n[..., 1]                      # DirectX -> OpenGL
            s["normal_map"] = self.store.put("T_seatfabric_seat_n", n, "normal", [npath])
            s["roughness"], s["roughness_map"] = matconv.scalar(self.store, s0.get("roughnessMap"), None, 1.0)
            s["source"] = "BeamNG material %s (cloth skin)" % SKINS[key]
        elif key == "qashqai16_bastion_lights":
            s = matconv.flatten(name, self.defs[key], self.store)
            s["roughness"] = 0.3
            s["source"] += " (its roughness map is not in the package)"
        else:
            return None
        s["name"] = name
        return s

    # --- lookup ------------------------------------------------------------
    def get(self, dts_mat, obj):
        if dts_mat == "licenseplate-52-11":
            rear = obj.endswith("_R")
            name = "M_Plate_Rear" if rear else "M_Plate_Front"
            if name not in self.specs:
                self.specs[name] = self.plate_spec(rear)
            return self.material(name)
        key = GLOW_OFF.get(dts_mat, dts_mat)
        if key == "qashqai16":
            name = "M_Paint_GunMetallic"
            if name not in self.specs:
                self.specs[name] = self.paint_spec(name, "qashqai16 body paint: the package's 'Gun Metallic' paint")
        elif key == "qashqai16_frame":
            name = "M_Paint_GunMetallic_Frame"
            if name not in self.specs:
                self.specs[name] = self.paint_spec(
                    name, "qashqai16_frame painted layer ('Gun Metallic'); its coverage mask is not in the package",
                    normal_ref=bngmat.resolve("vivace_main_nm.normal.DDS"))
        else:
            name = short(SKINS.get(key, key)) if not key.startswith("@") else \
                ("M_ScreenOff" if key == "@screen_off" else "M_IndicatorOff")
            if name not in self.specs:
                s = self.special(key, name)
                if s is None:
                    d = self.defs.get(SKINS.get(key, key))
                    if d is None:
                        raise KeyError("no definition for material %s (%s on %s)" % (key, dts_mat, obj))
                    s = matconv.flatten(name, d, self.store)
                    s["name"] = name
                self.specs[name] = s
        self.log.setdefault(dts_mat, set()).add(name)
        return self.material(name)

    def material(self, name):
        if name not in self.bpy:
            self.bpy[name] = make_material(self.specs[name], self.store)
        return self.bpy[name]

    def extra(self, spec):
        self.specs[spec["name"]] = spec
        return self.material(spec["name"])


def make_material(spec, store):
    m = bpy.data.materials.new(spec["name"])
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes["Principled BSDF"]
    out = nodes["Material Output"]
    bsdf.location, out.location = (300, 300), (650, 300)
    y = [600]

    def tex(key, colorspace):
        info = store.files[key]
        path = os.path.join(store.outdir, info["file"])
        img = bpy.data.images.get(info["file"]) or bpy.data.images.load(path, check_existing=True)
        img.colorspace_settings.name = colorspace
        n = nodes.new("ShaderNodeTexImage")
        n.image = img
        n.location = (-500, y[0])
        y[0] -= 280
        return n

    if spec["base_map"]:
        links.new(tex(spec["base_map"], "sRGB").outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Base Color"].default_value = (*spec["base"], 1.0)
    if spec["metallic_map"]:
        links.new(tex(spec["metallic_map"], "Non-Color").outputs["Color"], bsdf.inputs["Metallic"])
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    if spec["roughness_map"]:
        links.new(tex(spec["roughness_map"], "Non-Color").outputs["Color"], bsdf.inputs["Roughness"])
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    if spec["normal_map"]:
        nm = nodes.new("ShaderNodeNormalMap")
        nm.location = (0, y[0] + 140)
        nm.inputs["Strength"].default_value = spec["normal_strength"]
        links.new(tex(spec["normal_map"], "Non-Color").outputs["Color"], nm.inputs["Color"])
        links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if spec["coat"] > 0:
        bsdf.inputs["Coat Weight"].default_value = spec["coat"]
        bsdf.inputs["Coat Roughness"].default_value = spec["coat_roughness"]
    if any(spec["emission"]) or spec["emission_map"]:
        if spec["emission_map"]:
            links.new(tex(spec["emission_map"], "sRGB").outputs["Color"], bsdf.inputs["Emission Color"])
        else:
            bsdf.inputs["Emission Color"].default_value = (*spec["emission"], 1.0)
        bsdf.inputs["Emission Strength"].default_value = 1.0
    if spec["blend"] in ("CLIP", "BLEND"):
        a_src = None
        if spec["alpha_map"]:
            a_src = tex(spec["alpha_map"], "Non-Color").outputs["Color"]
        if spec["blend"] == "CLIP":
            # alpha >= cutoff, in the form the glTF exporter reads as MASK
            lt = nodes.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            lt.location = (-150, -400)
            lt.inputs[1].default_value = spec["alpha_cutoff"]
            sub = nodes.new("ShaderNodeMath")
            sub.operation = "SUBTRACT"
            sub.location = (50, -400)
            sub.inputs[0].default_value = 1.0
            if a_src is not None:
                links.new(a_src, lt.inputs[0])
            else:
                lt.inputs[0].default_value = spec["alpha"]
            links.new(lt.outputs[0], sub.inputs[1])
            links.new(sub.outputs[0], bsdf.inputs["Alpha"])
        else:
            if a_src is not None:
                links.new(a_src, bsdf.inputs["Alpha"])
            else:
                bsdf.inputs["Alpha"].default_value = spec["alpha"]
            m.surface_render_method = "BLENDED"
            m.use_transparency_overlap = True
    m.use_backface_culling = not spec["double_sided"]
    m["source"] = spec.get("source", "")
    return m


# ---------------------------------------------------------------------------
# Wheels
# ---------------------------------------------------------------------------
def hub_centre(ob):
    """Wheel-axis centre of a hub mesh (BeamNG space): the mean of the
    vertices on its outer face."""
    M = ob.matrix_world
    V = np.array([M @ v.co for v in ob.data.vertices])
    side = 1 if V[:, 0].mean() > 0 else -1
    xo = V[:, 0].max() if side > 0 else V[:, 0].min()
    s = np.abs(V[:, 0] - xo) < 0.01
    return side, xo, V[s, 1].mean(), V[s, 2].mean()


def tyre_mesh(name, width, aspect, rim_in):
    """Tyre around the X axis (the rim's axle), revolved from a profile with
    four circumferential grooves."""
    r_rim = rim_in * 0.0254 / 2
    r_out = r_rim + width * aspect
    hw = width / 2
    bead = r_rim + 0.006
    prof = [(-0.098, bead), (-0.108, bead + 0.012), (-0.116, r_rim + 0.045), (-hw, r_rim + 0.068),
            (-0.116, r_out - 0.036), (-0.110, r_out - 0.017), (-0.100, r_out - 0.006), (-0.090, r_out)]
    grooves = [-0.066, -0.024, 0.024, 0.066]
    x = -0.090
    tread = []
    for g in grooves:
        tread += [(g - 0.006, r_out), (g - 0.005, r_out - 0.008), (g + 0.005, r_out - 0.008), (g + 0.006, r_out)]
    prof += tread + [(-px, pr) for px, pr in reversed(prof)]
    n = 144
    verts, faces = [], []
    P = len(prof)
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        for px, pr in prof:
            verts.append((px, pr * c, pr * s))
    for k in range(n):
        k2 = (k + 1) % n
        for i in range(P - 1):
            a0, a1 = k * P + i, k * P + i + 1
            b0, b1 = k2 * P + i, k2 * P + i + 1
            faces.append((a0, a1, b1, b0))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    # outward normals on the tread
    c = np.array([p.center for p in me.polygons])
    nrm = np.array([p.normal for p in me.polygons])
    tread = np.hypot(c[:, 1], c[:, 2]) > r_out - 0.002
    radial = c[tread].copy()
    radial[:, 0] = 0
    if (np.einsum("ij,ij->i", nrm[tread], radial) < 0).mean() > 0.5:
        me.flip_normals()
    me.polygons.foreach_set("use_smooth", np.ones(len(faces), dtype=bool))
    # UVs: around the tyre x along the profile
    uv = me.uv_layers.new(name="UVMap")
    cum = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(np.array(prof), axis=0).T))])
    cum /= cum[-1]
    luv = []
    for f in me.polygons:
        for li in f.loop_indices:
            vi = me.loops[li].vertex_index
            k, i = divmod(vi, P)
            luv.append((k / n, cum[i]))
    # the seam: faces joining the last ring to the first use u = 1
    for f in me.polygons:
        ks = [me.loops[li].vertex_index // P for li in f.loop_indices]
        if max(ks) - min(ks) > 1:
            for li in f.loop_indices:
                if me.loops[li].vertex_index // P == 0:
                    luv[li] = (1.0, luv[li][1])
    uv.data.foreach_set("uv", np.array(luv).ravel())
    ob = bpy.data.objects.new(name, me)
    return ob, r_out


def main():
    out = os.path.abspath(sys.argv[-1])
    blend_dir, ue_dir = os.path.join(out, "blender"), os.path.join(out, "unreal")
    texdir = os.path.join(out, "textures")
    for d in (out, blend_dir, ue_dir, texdir):
        os.makedirs(d, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    mats = Materials(texdir)

    S = dts31.Shape(os.path.join(PKG, "qashqai16", "qashqai16.dts"))
    SW = dts31.Shape(os.path.join(PKG, "common", "qashqai16_wheels", "qashqai16_wheel.dts"))
    worlds, names, index = dtsblend.node_worlds(S), dtsblend.material_names(S), dtsblend.object_index(S)
    log("shapes read")

    root = bpy.data.collections.new(NAME)
    scene.collection.children.link(root)
    cols = {}
    for c in ("Exterior", "Glass", "Interior", "Mechanical", "Wheels"):
        cols[c] = bpy.data.collections.new(c)
        root.children.link(cols[c])
    group = {}
    for n in config.EXTERIOR:
        group[config.RHD_SWAP.get(n, n)] = "Exterior"
    for n in config.INTERIOR:
        group[config.RHD_SWAP.get(n, n)] = "Interior"
    for n in config.MECHANICAL:
        group[config.RHD_SWAP.get(n, n)] = "Mechanical"

    built = {}
    for n in config.selection(rhd=True):
        if n in SKIP:
            continue
        ob = dtsblend.build_object(S, index[n], worlds, names, mats.get,
                                   name=n.replace("1qashqai16_", "qashqai16_"), use_node=n not in NO_NODE,
                                   drop_flat_uv="licenseplate" in n)   # the plates' hidden backs
        if ob is None:
            log("no geometry:", n)
            continue
        g = group[n]
        if all(ms and mats.specs[ms.name]["blend"] == "BLEND" for ms in ob.data.materials):
            g = "Glass"
        cols[g].objects.link(ob)
        built[n] = ob
    log("built %d objects, %d materials" % (len(built), len(mats.specs)))

    # --- wheels: the N-Connecta rim at each hub, with a tyre ---------------
    hubs = {"FL": built["qashqai16_hub_FL"], "FR": built["qashqai16_hub_FR"], "R": built["qashqai16_hub_R"]}
    _, _, yf, zf = hub_centre(hubs["FL"])
    _, _, yr, zr = hub_centre(hubs["R"])
    wmats = dtsblend.material_names(SW)
    wi = dtsblend.object_index(SW)
    rim_proto = dtsblend.build_object(SW, wi[config.WHEEL], dtsblend.node_worlds(SW), wmats, mats.get, name="Rim")
    tyre_proto, r_tyre = tyre_mesh("Tyre", *TYRE)
    tyre_mat = mats.extra(dict(matconv.new_spec("M_Tyre", "generated: 235/50 R18 tyre (not in the package)"),
                               base=[0.022, 0.022, 0.023], roughness=0.82))
    tyre_proto.data.materials.append(tyre_mat)
    wheel_pos = {"FL": (TRACK_F / 2, yf, zf), "FR": (-TRACK_F / 2, yf, zf),
                 "RL": (TRACK_R / 2, yr, zr), "RR": (-TRACK_R / 2, yr, zr)}
    wheels = {}
    for tag, (x, y, z) in wheel_pos.items():
        M = Matrix.Translation((x, y, z))
        if x < 0:                                  # right side: rim face towards -X
            M = M @ Matrix.Rotation(math.pi, 4, "Z")
        for proto, kind in ((rim_proto, "Rim"), (tyre_proto, "Tyre")):
            ob = bpy.data.objects.new("Wheel_%s_%s" % (tag, kind), proto.data)
            ob.matrix_world = M
            cols["Wheels"].objects.link(ob)
            wheels.setdefault(tag, []).append(ob)
    bpy.data.objects.remove(rim_proto)
    bpy.data.objects.remove(tyre_proto)
    ground = (zf + zr) / 2 - r_tyre
    ymid = (yf + yr) / 2
    log("hubs: front y %.3f z %.3f, rear y %.3f z %.3f; wheelbase %.3f; ground z %.3f" % (yf, zf, yr, zr, yr - yf, ground))

    # --- into Blender space: X forward, Y left, Z up; origin on the ground
    # midway between the axles ---------------------------------------------
    T = ROT @ Matrix.Translation((0.0, -ymid, -ground))
    for ob in list(root.all_objects):
        ob.matrix_world = T @ ob.matrix_world

    info = {"name": "Nissan Qashqai J11 (2014-2017), N-Connecta 1.6 dCi, Gun Metallic, %s, right-hand drive" % REG,
            "source": "BeamNG.drive mod 'qashqai16' by FastLane (static visual package), configuration nconnecta_16dci_m",
            "changes": ["paint: the package's 'Gun Metallic' definition instead of the default Ink Blue",
                        "number plates: UK %s, white front and yellow rear, instead of the EU placeholder plates" % REG,
                        "right-hand drive: the package's own _rhd dashboard, steering wheel, pedals, stalks, "
                        "gauges, glovebox, door cards, mirrors and wipers"],
            "not_in_package": ["tyres (generated, 235/50 R18)", "JBeam (wheel placement from the hubs and the J11 track)",
                               "vivace textures for mechanical/engine/pedal materials (plain fallbacks)"],
            "wheel_centres_m": {k: [round(v, 4) for v in (T @ Vector(p))] for k, p in wheel_pos.items()},
            "tyre_radius_m": round(r_tyre, 4)}
    json.dump(info, open(os.path.join(out, "build_info.json"), "w"), indent=1)
    json.dump({k: sorted(v) for k, v in sorted(mats.log.items())}, open(os.path.join(out, "material_map.json"), "w"), indent=1)
    json.dump(mats.specs, open(os.path.join(out, "material_specs.json"), "w"), indent=1)
    json.dump(mats.store.files, open(os.path.join(out, "textures.json"), "w"), indent=1)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, "stage1.blend"))
    log("saved stage1; textures:", len(mats.store.files))


if __name__ == "__main__":
    main()
