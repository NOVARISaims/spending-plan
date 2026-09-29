"""Import the Nissan Qashqai J11 (DE17 YAU, Gun Metallic, right-hand drive)
into Unreal Engine 5 and assemble a Blueprint.

Run inside the Unreal Editor (the Python Editor Script Plugin is enabled by
default in UE5):
    * Tools > Execute Python Script... and pick this file, or
    * Output Log > switch the input box to "Python" and type
          py "C:/path/to/unreal/import_qashqai_j11.py"

Keep this script next to manifest.json, the SM_QashqaiJ11_*.fbx files and
the textures folder.  It
    1. imports the textures (colour maps as sRGB, data maps linear, normal
       maps as normal maps with the green channel flipped: they are
       OpenGL-style)
    2. creates four master materials (opaque, clear coat, masked,
       translucent) and one material instance per material slot, with the
       colours, factors and textures from the manifest
    3. imports the static meshes and assigns the material instances
    4. builds BP_QashqaiJ11: body, glass, interior, steering wheel and
       mechanical parts plus four wheel components, and places one in the
       open level

Settings (environment variables, or edit the constants):
    QASHQAI_J11_DIR     folder with manifest.json (default: this folder)
    QASHQAI_J11_DEST    content folder (default /Game/Vehicles/QashqaiJ11)
    QASHQAI_J11_SPAWN   "0" to skip placing the Blueprint in the level
Re-running updates the assets in place and rebuilds the Blueprint.
"""
import json
import os

import unreal

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                       # pasted into the Python console
    HERE = os.getcwd()

SRC = os.environ.get("QASHQAI_J11_DIR", HERE)
DEST = os.environ.get("QASHQAI_J11_DEST", "/Game/Vehicles/QashqaiJ11").rstrip("/")
SPAWN_IN_LEVEL = os.environ.get("QASHQAI_J11_SPAWN", "1") != "0"
BP_NAME = "BP_QashqaiJ11"
ACTOR_LABEL = "QashqaiJ11_DE17YAU"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty
ST = unreal.MaterialSamplerType


def log(msg):
    unreal.log("[QashqaiJ11] " + msg)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def import_file(filename, dest_path, dest_name, options=None):
    if not os.path.isfile(filename):
        raise RuntimeError("Missing file: " + filename)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", dest_path)
    task.set_editor_property("destination_name", dest_name)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", False)
    if options is not None:
        task.set_editor_property("options", options)
    asset_tools.import_asset_tasks([task])
    assets = [unreal.load_asset(p) for p in (task.get_editor_property("imported_object_paths") or [])]
    assets = [a for a in assets if a is not None]
    if not assets:
        raise RuntimeError("Import produced no assets: " + filename)
    return assets


def load_or_create(name, path, asset_class, factory):
    full = "%s/%s" % (path, name)
    if eal.does_asset_exist(full):
        asset = eal.load_asset(full)
        if isinstance(asset, asset_class):
            return asset
        eal.delete_asset(full)
    return asset_tools.create_asset(name, path, asset_class, factory)


class LegacyFbxImporter(object):
    """UE 5.5+ routes FBX through Interchange, which ignores FbxImportUI;
    switch back to the classic importer while this script imports."""

    CVAR = "Interchange.FeatureFlags.Import.FBX"

    def __enter__(self):
        try:
            self.previous = unreal.SystemLibrary.get_console_variable_bool_value(self.CVAR)
        except Exception:
            self.previous = False
        unreal.SystemLibrary.execute_console_command(None, self.CVAR + " 0")
        return self

    def __exit__(self, *exc):
        if self.previous:
            unreal.SystemLibrary.execute_console_command(None, self.CVAR + " 1")
        return False


# ---------------------------------------------------------------------------
# textures
# ---------------------------------------------------------------------------
def import_textures(manifest):
    out = {}
    for key, info in manifest["textures"].items():
        tex = import_file(os.path.join(SRC, info["file"]), DEST + "/Textures", key)[0]
        kind = info["kind"]
        if kind == "normal":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("flip_green_channel", True)       # OpenGL -> DirectX
        elif kind == "data":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            tex.set_editor_property("srgb", False)
        else:
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            tex.set_editor_property("srgb", True)
        eal.save_loaded_asset(tex)
        out[key] = tex
    return out


# ---------------------------------------------------------------------------
# master materials
# ---------------------------------------------------------------------------
def _expr(m, cls, x, y, **props):
    node = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        node.set_editor_property(k, v)
    return node


def _scalar(m, name, value, x, y):
    return _expr(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)


def _vector(m, name, rgba, x, y):
    return _expr(m, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                 default_value=unreal.LinearColor(*rgba))


def _texture(m, name, tex, sampler, x, y):
    node = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=tex)
    node.set_editor_property("sampler_type", sampler)
    return node


def _mul(m, a, a_out, b, b_out, x, y):
    node = _expr(m, unreal.MaterialExpressionMultiply, x, y)
    mel.connect_material_expressions(a, a_out, node, "A")
    mel.connect_material_expressions(b, b_out, node, "B")
    return node


def build_master(name, textures, kind):
    """kind: opaque | clearcoat | masked | translucent."""
    m = load_or_create(name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    white, lin, flat = textures["T_J11_White"], textures["T_J11_WhiteLinear"], textures["T_J11_FlatNormal"]
    y = -600
    base = _mul(m, _texture(m, "BaseColorMap", white, ST.SAMPLERTYPE_COLOR, -900, y), "RGB",
                _vector(m, "BaseColor", (0.8, 0.8, 0.8, 1.0), -900, y + 220), "", -500, y)
    metal = _mul(m, _texture(m, "MetallicMap", lin, ST.SAMPLERTYPE_LINEAR_COLOR, -900, y + 360), "R",
                 _scalar(m, "Metallic", 0.0, -900, y + 580), "", -500, y + 360)
    rough = _mul(m, _texture(m, "RoughnessMap", lin, ST.SAMPLERTYPE_LINEAR_COLOR, -900, y + 680), "R",
                 _scalar(m, "Roughness", 0.5, -900, y + 900), "", -500, y + 680)
    nmap = _texture(m, "NormalMap", flat, ST.SAMPLERTYPE_NORMAL, -900, y + 1000)
    flatv = _expr(m, unreal.MaterialExpressionConstant3Vector, -700, y + 1240,
                  constant=unreal.LinearColor(0.0, 0.0, 1.0, 1.0))
    lerp = _expr(m, unreal.MaterialExpressionLinearInterpolate, -500, y + 1000)
    mel.connect_material_expressions(flatv, "", lerp, "A")
    mel.connect_material_expressions(nmap, "RGB", lerp, "B")
    mel.connect_material_expressions(_scalar(m, "NormalStrength", 0.0, -900, y + 1300), "", lerp, "Alpha")
    emis = _mul(m, _texture(m, "EmissiveMap", white, ST.SAMPLERTYPE_COLOR, -900, y + 1400), "RGB",
                _vector(m, "Emissive", (0.0, 0.0, 0.0, 1.0), -900, y + 1620), "", -500, y + 1400)
    mel.connect_material_property(base, "", MP.MP_BASE_COLOR)
    mel.connect_material_property(metal, "", MP.MP_METALLIC)
    mel.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    mel.connect_material_property(lerp, "", MP.MP_NORMAL)
    mel.connect_material_property(emis, "", MP.MP_EMISSIVE_COLOR)
    if kind in ("masked", "translucent"):
        op = _mul(m, _texture(m, "OpacityMap", lin, ST.SAMPLERTYPE_LINEAR_COLOR, -900, y + 1760), "R",
                  _scalar(m, "Opacity", 1.0, -900, y + 1980), "", -500, y + 1760)
        if kind == "masked":
            sub = _expr(m, unreal.MaterialExpressionSubtract, -300, y + 1760)
            mel.connect_material_expressions(op, "", sub, "A")
            mel.connect_material_expressions(_scalar(m, "OpacityCutoff", 0.5, -500, y + 2000), "", sub, "B")
            add = _expr(m, unreal.MaterialExpressionAdd, -150, y + 1760, const_b=0.5)
            mel.connect_material_expressions(sub, "", add, "A")
            m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
            m.set_editor_property("opacity_mask_clip_value", 0.5)
            mel.connect_material_property(add, "", MP.MP_OPACITY_MASK)
        else:
            m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
            try:
                m.set_editor_property("translucency_lighting_mode",
                                      unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
            except Exception:
                pass
            mel.connect_material_property(op, "", MP.MP_OPACITY)
    if kind == "clearcoat":
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_CLEAR_COAT)
        mel.connect_material_property(_scalar(m, "ClearCoat", 1.0, -500, y + 1800), "", MP.MP_CUSTOM_DATA0)
        mel.connect_material_property(_scalar(m, "ClearCoatRoughness", 0.05, -500, y + 1900), "", MP.MP_CUSTOM_DATA1)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def build_instances(manifest, masters, textures):
    out = {}
    for slot, spec in manifest["materials"].items():
        mi = load_or_create("MI_J11_" + slot[2:] if slot.startswith("M_") else "MI_J11_" + slot,
                            DEST + "/Materials", unreal.MaterialInstanceConstant,
                            unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, masters[spec["parent"]])
        for k, v in spec["vectors"].items():
            mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v))
        for k, v in spec["scalars"].items():
            mel.set_material_instance_scalar_parameter_value(mi, k, float(v))
        for k, key in spec["textures"].items():
            mel.set_material_instance_texture_parameter_value(mi, k, textures[key])
        if spec.get("two_sided"):
            ov = mi.get_editor_property("base_property_overrides")
            ov.set_editor_property("override_two_sided", True)
            ov.set_editor_property("two_sided", True)
            mi.set_editor_property("base_property_overrides", ov)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi)
        out[slot] = mi
    return out


# ---------------------------------------------------------------------------
# static meshes
# ---------------------------------------------------------------------------
def fbx_options(collision):
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_as_skeletal", False)
    opts.set_editor_property("import_animations", False)
    opts.set_editor_property("import_materials", False)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("create_physics_asset", False)
    opts.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    data = opts.get_editor_property("static_mesh_import_data")
    data.set_editor_property("combine_meshes", True)
    data.set_editor_property("auto_generate_collision", collision)
    data.set_editor_property("generate_lightmap_u_vs", True)
    data.set_editor_property("remove_degenerates", False)
    data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    return opts


def assign_materials(mesh, instances):
    for index, sm in enumerate(mesh.get_editor_property("static_materials")):
        slot = str(sm.get_editor_property("material_slot_name"))
        mi = instances.get(slot)
        if mi is None:                   # tolerate suffixes such as "_skin0"
            mi = next((v for k, v in instances.items() if slot.startswith(k)), None)
        if mi is None:
            unreal.log_warning("[QashqaiJ11] no material for slot %r on %s" % (slot, mesh.get_name()))
            continue
        mesh.set_material(index, mi)


def import_meshes(manifest, instances):
    meshes = {}
    with LegacyFbxImporter():
        for part in manifest["parts"]:
            assets = import_file(os.path.join(SRC, part["fbx"]), DEST + "/Meshes", part["name"],
                                 fbx_options(part.get("collision", False)))
            mesh = next((a for a in assets if isinstance(a, unreal.StaticMesh)), None)
            if mesh is None:
                raise RuntimeError("No static mesh imported from " + part["fbx"])
            assign_materials(mesh, instances)
            eal.save_loaded_asset(mesh)
            meshes[part["name"]] = mesh
            log("imported %s (%d triangles)" % (mesh.get_name(), part["triangles"]))
    return meshes


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
def rotation(frame):
    x = unreal.Vector(*frame["x_axis"])
    z = unreal.Vector(*frame["z_axis"])
    return unreal.MathLibrary.make_rot_from_xz(x, z)


def remove_blueprint(path):
    if not eal.does_asset_exist(path):
        return
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in actors.get_all_level_actors():
        if actor.get_class().get_name().startswith(BP_NAME):
            actors.destroy_actor(actor)
    eal.delete_asset(path)


def build_blueprint(manifest, meshes):
    path = "%s/%s" % (DEST, BP_NAME)
    remove_blueprint(path)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.Actor)
    bp = asset_tools.create_asset(BP_NAME, DEST, None, factory)
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(context=bp)
    root = handles[0]
    for h in handles:
        if isinstance(lib.get_object(lib.get_data(h)), unreal.SceneComponent):
            root = h
            break

    def add(name, mesh, frame=None, collision=False):
        handle, fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=root, new_class=unreal.StaticMeshComponent, blueprint_context=bp))
        if str(fail):
            raise RuntimeError("Could not add %s: %s" % (name, fail))
        sds.rename_subobject(handle, unreal.Text(name))
        comp = lib.get_object(lib.get_data(handle))
        comp.set_editor_property("static_mesh", mesh)
        if frame is not None:
            comp.set_editor_property("relative_location", unreal.Vector(*frame["location_cm"]))
            comp.set_editor_property("relative_rotation", rotation(frame))
        if not collision:
            comp.set_editor_property("collision_profile_name", "NoCollision")
        return comp

    for part in manifest["parts"]:
        if part["name"] == "SM_QashqaiJ11_Wheel":
            continue
        add(part["name"].replace("SM_QashqaiJ11_", ""), meshes[part["name"]], part.get("transform"),
            part.get("collision", False))
    for tag, frame in manifest["wheels"].items():
        add("Wheel_" + tag, meshes["SM_QashqaiJ11_Wheel"], frame)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    eal.save_loaded_asset(bp)
    log("built %s" % path)
    return bp


def spawn(bp):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_object(bp, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator(0.0, 0.0, 0.0))
    if actor:
        actor.set_actor_label(ACTOR_LABEL)
        log("placed %s at the world origin (nose towards +X, wheels on the ground)" % ACTOR_LABEL)
    return actor


def main():
    with open(os.path.join(SRC, "manifest.json")) as fh:
        manifest = json.load(fh)
    steps = 6 if SPAWN_IN_LEVEL else 5
    with unreal.ScopedSlowTask(steps, "Importing Nissan Qashqai J11") as task:
        task.make_dialog(True)
        task.enter_progress_frame(1, "Textures")
        textures = import_textures(manifest)
        task.enter_progress_frame(1, "Materials")
        masters = {n: build_master(n, textures, k) for n, k in (
            ("M_J11_Opaque", "opaque"), ("M_J11_ClearCoat", "clearcoat"), ("M_J11_Masked", "masked"),
            ("M_J11_Translucent", "translucent"))}
        instances = build_instances(manifest, masters, textures)
        task.enter_progress_frame(1, "Static meshes")
        meshes = import_meshes(manifest, instances)
        task.enter_progress_frame(1, "Blueprint")
        bp = build_blueprint(manifest, meshes)
        if SPAWN_IN_LEVEL:
            task.enter_progress_frame(1, "Placing in level")
            spawn(bp)
        task.enter_progress_frame(1, "Saving")
        eal.save_directory(DEST, only_if_is_dirty=True, recursive=True)
    log("done: assets in " + DEST)


if __name__ == "__main__":
    main()
