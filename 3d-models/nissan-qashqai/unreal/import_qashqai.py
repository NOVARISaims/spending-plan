"""Import the 2017 Nissan Qashqai into Unreal Engine 5 and assemble a Blueprint.

Run inside the Unreal Editor (the Python Editor Script Plugin is on by default
in UE5):
    * Tools > Execute Python Script... and choose this file, or
    * Output Log > switch the input box to "Python" > type
          py "C:/path/to/3d-models/nissan-qashqai/unreal/import_qashqai.py"

What it does:
    1. imports the textures listed in the manifest (number plates, grille
       honeycomb, plastic grain, seat cloth, and the interior panels with
       lettering: centre stack, dials, steering-wheel switches); normal maps
       are set up for DirectX (flipped green)
    2. creates master materials (clear-coat paint, solid, glass, plate,
       grille) and one material instance per Blender material slot
    3. imports every SM_Qashqai_*.fbx listed in ../export/manifest.json as a
       static mesh (the body with its UCX_ convex hulls) and assigns the
       material instances
    4. builds BP_Qashqai2017: body, glass, lamp lenses, interior and four
       wheel components at the hub centres, and drops one into the open level

Settings can be overridden with environment variables before launching the
editor, or by editing the constants below:
    QASHQAI_EXPORT_DIR   folder with the FBX files and manifest.json
    QASHQAI_DEST         content folder (default /Game/Vehicles/Qashqai2017)
    QASHQAI_SPAWN        "0" to skip placing an instance in the level

Re-running the script updates the assets in place and rebuilds the Blueprint.
"""
import json
import os

import unreal

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                       # pasted into the Python console
    HERE = os.getcwd()

EXPORT_DIR = os.environ.get("QASHQAI_EXPORT_DIR", os.path.normpath(os.path.join(HERE, "..", "export")))
DEST = os.environ.get("QASHQAI_DEST", "/Game/Vehicles/Qashqai2017").rstrip("/")
SPAWN_IN_LEVEL = os.environ.get("QASHQAI_SPAWN", "1") != "0"
BP_NAME = "BP_Qashqai2017"
ACTOR_LABEL = "Qashqai2017_DE17YAU"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty


def log(msg):
    unreal.log("[Qashqai] " + msg)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def import_file(filename, dest_path, dest_name, options=None):
    """Import one file and return the created/updated assets."""
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
    paths = list(task.get_editor_property("imported_object_paths") or [])
    assets = [unreal.load_asset(p) for p in paths]
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
    """UE 5.5+ routes FBX through Interchange, which ignores FbxImportUI.
    Temporarily switch back to the classic importer so the options apply."""

    CVAR = "Interchange.FeatureFlags.Import.FBX"

    def __enter__(self):
        self.previous = unreal.SystemLibrary.get_console_variable_bool_value(self.CVAR)
        unreal.SystemLibrary.execute_console_command(None, self.CVAR + " 0")
        return self

    def __exit__(self, *exc):
        if self.previous:
            unreal.SystemLibrary.execute_console_command(None, self.CVAR + " 1")
        return False


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------
def import_textures(manifest):
    """Every texture in the manifest: {key: {"file": ..., "kind": "color" | "normal"}}."""
    out = {}
    for key, info in manifest["textures"].items():
        path = os.path.join(EXPORT_DIR, info["file"])
        name = os.path.splitext(os.path.basename(path))[0]
        tex = import_file(path, DEST + "/Textures", name)[0]
        if info["kind"] == "normal":
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("flip_green_channel", True)     # OpenGL -> DirectX
        eal.save_loaded_asset(tex)
        out[key] = tex
    return out


# ---------------------------------------------------------------------------
# Master materials
# ---------------------------------------------------------------------------
def _expr(material, cls, x, y, **props):
    node = mel.create_material_expression(material, cls, x, y)
    for k, v in props.items():
        node.set_editor_property(k, v)
    return node


def _scalar(m, name, value, x, y):
    return _expr(m, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value)


def _vector(m, name, rgb, x, y):
    return _expr(m, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
                 default_value=unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))


def _new_master(name):
    m = load_or_create(name, DEST + "/Materials", unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    return m


def _finish(m):
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def _tiled_uv(m, name, default, x, y):
    uv = _expr(m, unreal.MaterialExpressionTextureCoordinate, x - 250, y)
    tiling = _scalar(m, name, default, x - 250, y + 120)
    mul = _expr(m, unreal.MaterialExpressionMultiply, x, y + 40)
    mel.connect_material_expressions(uv, "", mul, "A")
    mel.connect_material_expressions(tiling, "", mul, "B")
    return mul


def build_solid_master(textures):
    """Default lit: colour, roughness, metallic, specular, emissive and an
    optional tiling detail normal (the black plastic grain)."""
    m = _new_master("M_QQ_Solid")
    color = _vector(m, "BaseColor", (0.8, 0.8, 0.8), -600, -300)
    rough = _scalar(m, "Roughness", 0.5, -600, -150)
    metal = _scalar(m, "Metallic", 0.0, -600, -50)
    spec = _scalar(m, "Specular", 0.5, -600, 50)
    emis = _vector(m, "EmissiveColor", (0.0, 0.0, 0.0), -600, 150)
    uv = _tiled_uv(m, "DetailTiling", 25.0, -900, 300)
    normal = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -600, 300,
                   parameter_name="DetailNormal", texture=textures["grain_normal"])
    normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    mel.connect_material_expressions(uv, "", normal, "UVs")
    strength = _scalar(m, "DetailNormalStrength", 0.0, -600, 500)
    flat = _expr(m, unreal.MaterialExpressionConstant3Vector, -450, 560,
                 constant=unreal.LinearColor(0.0, 0.0, 1.0, 1.0))
    lerp = _expr(m, unreal.MaterialExpressionLinearInterpolate, -250, 400)
    mel.connect_material_expressions(flat, "", lerp, "A")
    mel.connect_material_expressions(normal, "RGB", lerp, "B")
    mel.connect_material_expressions(strength, "", lerp, "Alpha")
    mel.connect_material_property(color, "", MP.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    mel.connect_material_property(metal, "", MP.MP_METALLIC)
    mel.connect_material_property(spec, "", MP.MP_SPECULAR)
    mel.connect_material_property(emis, "", MP.MP_EMISSIVE_COLOR)
    mel.connect_material_property(lerp, "", MP.MP_NORMAL)
    return _finish(m)


def build_paint_master():
    """Clear-coat car paint (also used for the alloy wheels)."""
    m = _new_master("M_QQ_Paint")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_CLEAR_COAT)
    mel.connect_material_property(_vector(m, "BaseColor", (0.125, 0.128, 0.133), -500, -250), "",
                                  MP.MP_BASE_COLOR)
    mel.connect_material_property(_scalar(m, "Metallic", 0.75, -500, -100), "", MP.MP_METALLIC)
    mel.connect_material_property(_scalar(m, "Roughness", 0.36, -500, 0), "", MP.MP_ROUGHNESS)
    mel.connect_material_property(_scalar(m, "ClearCoat", 1.0, -500, 100), "", MP.MP_CUSTOM_DATA0)
    mel.connect_material_property(_scalar(m, "ClearCoatRoughness", 0.03, -500, 200), "", MP.MP_CUSTOM_DATA1)
    return _finish(m)


def build_glass_master():
    """Translucent, two-sided glass / lamp lens with forward-shaded specular."""
    m = _new_master("M_QQ_Glass")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", True)
    try:
        m.set_editor_property("translucency_lighting_mode",
                              unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    except Exception:                    # older enum spelling
        pass
    mel.connect_material_property(_vector(m, "BaseColor", (0.8, 0.86, 0.84), -500, -250), "", MP.MP_BASE_COLOR)
    mel.connect_material_property(_scalar(m, "Opacity", 0.2, -500, -100), "", MP.MP_OPACITY)
    mel.connect_material_property(_scalar(m, "Roughness", 0.02, -500, 0), "", MP.MP_ROUGHNESS)
    mel.connect_material_property(_scalar(m, "Specular", 1.0, -500, 100), "", MP.MP_SPECULAR)
    mel.connect_material_property(_vector(m, "EmissiveColor", (0.0, 0.0, 0.0), -500, 200), "",
                                  MP.MP_EMISSIVE_COLOR)
    return _finish(m)


def build_plate_master(textures):
    """Texture across the whole UV range: number plates and the lettered
    interior panels (centre stack, dials, wheel switches)."""
    m = _new_master("M_QQ_Plate")
    tex = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -500, -200,
                parameter_name="PlateTexture", texture=textures["plate_front"])
    mel.connect_material_property(tex, "RGB", MP.MP_BASE_COLOR)
    mel.connect_material_property(_scalar(m, "Roughness", 0.25, -500, 50), "", MP.MP_ROUGHNESS)
    return _finish(m)


def build_grille_master(textures):
    """Tiling base colour and normal map: grille honeycomb, patterned seat cloth."""
    m = _new_master("M_QQ_Grille")
    uv = _tiled_uv(m, "UVTiling", 1.0, -900, 0)
    base = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -500, -250,
                 parameter_name="BaseColorMap", texture=textures["honeycomb_base"])
    normal = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -500, 100,
                   parameter_name="NormalMap", texture=textures["honeycomb_normal"])
    normal.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    mel.connect_material_expressions(uv, "", base, "UVs")
    mel.connect_material_expressions(uv, "", normal, "UVs")
    mel.connect_material_property(base, "RGB", MP.MP_BASE_COLOR)
    mel.connect_material_property(normal, "RGB", MP.MP_NORMAL)
    mel.connect_material_property(_scalar(m, "Roughness", 0.45, -500, 350), "", MP.MP_ROUGHNESS)
    return _finish(m)


def build_instances(manifest, masters, textures):
    """One material instance per Blender material, keyed by its slot name."""
    out = {}
    for slot, spec in manifest["materials"].items():
        mi = load_or_create(spec["ue_instance"], DEST + "/Materials", unreal.MaterialInstanceConstant,
                            unreal.MaterialInstanceConstantFactoryNew())
        parent = spec["ue_parent"]
        mel.set_material_instance_parent(mi, masters[parent])
        r, g, b = spec["base_color_linear"]
        color = unreal.LinearColor(r, g, b, 1.0)
        if parent in ("M_QQ_Solid", "M_QQ_Paint", "M_QQ_Glass"):
            mel.set_material_instance_vector_parameter_value(mi, "BaseColor", color)
            mel.set_material_instance_scalar_parameter_value(mi, "Roughness", spec["roughness"])
        if parent in ("M_QQ_Solid", "M_QQ_Paint"):
            mel.set_material_instance_scalar_parameter_value(mi, "Metallic", spec["metallic"])
        if parent == "M_QQ_Paint":
            mel.set_material_instance_scalar_parameter_value(mi, "ClearCoat", spec["clear_coat"])
            mel.set_material_instance_scalar_parameter_value(mi, "ClearCoatRoughness",
                                                             spec["clear_coat_roughness"])
        if parent == "M_QQ_Glass":
            mel.set_material_instance_scalar_parameter_value(mi, "Opacity", spec["opacity"])
        if parent in ("M_QQ_Solid", "M_QQ_Glass"):
            e = spec.get("emissive", [0, 0, 0])
            mel.set_material_instance_vector_parameter_value(mi, "EmissiveColor",
                                                             unreal.LinearColor(e[0], e[1], e[2], 1.0))
        for param, key in spec.get("textures", {}).items():
            mel.set_material_instance_texture_parameter_value(mi, param, textures[key])
        if parent == "M_QQ_Solid" and spec.get("detail_normal_strength", 0.0) > 0.0:
            # UV0 is 1 unit per metre: the grain tiles uv_tiling times per metre
            mel.set_material_instance_scalar_parameter_value(mi, "DetailNormalStrength",
                                                             spec["detail_normal_strength"])
            mel.set_material_instance_scalar_parameter_value(mi, "DetailTiling", spec.get("uv_tiling", 25.0))
        if parent == "M_QQ_Grille":
            # UV0 is 1 unit per metre; one tile covers 1 / uv_tiling metres
            mel.set_material_instance_scalar_parameter_value(mi, "UVTiling", spec.get("uv_tiling", 10.0))
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi)
        out[slot] = mi
    return out


# ---------------------------------------------------------------------------
# Static meshes
# ---------------------------------------------------------------------------
def fbx_options():
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
    data.set_editor_property("auto_generate_collision", False)    # use the UCX_ hulls
    data.set_editor_property("one_convex_hull_per_ucx", True)
    data.set_editor_property("generate_lightmap_u_vs", True)
    data.set_editor_property("remove_degenerates", True)
    data.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return opts


def slot_names(mesh):
    return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("static_materials")]


def assign_materials(mesh, instances):
    for index, slot in enumerate(slot_names(mesh)):
        mi = instances.get(slot)
        if mi is None:                   # tolerate suffixes such as "_skin0"
            mi = next((v for k, v in instances.items() if slot.startswith(k)), None)
        if mi is None:
            unreal.log_warning("[Qashqai] no material for slot %r on %s" % (slot, mesh.get_name()))
            continue
        mesh.set_material(index, mi)


def import_meshes(manifest, instances):
    meshes = {}
    with LegacyFbxImporter():
        for part in manifest["parts"]:
            assets = import_file(os.path.join(EXPORT_DIR, part["fbx"]), DEST + "/Meshes", part["name"],
                                 fbx_options())
            mesh = next((a for a in assets if isinstance(a, unreal.StaticMesh)), None)
            if mesh is None:
                raise RuntimeError("No static mesh imported from " + part["fbx"])
            assign_materials(mesh, instances)
            eal.save_loaded_asset(mesh)
            meshes[part["name"]] = mesh
            log("imported %s (%d triangles in Blender)" % (mesh.get_name(), part["triangles"]))
    body = meshes.get("SM_Qashqai_Body")
    if body is not None:
        box = body.get_bounding_box()
        lo, hi = box.get_editor_property("min"), box.get_editor_property("max")
        spec = manifest["overall_cm"]
        log("body bounds %.1f x %.1f x %.1f cm (%.1f cm bumper to bumper; the front plate and the aerial "
            "stand proud)" % (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z, spec["length_x"]))
        if abs((hi.x - lo.x) - spec["length_x"]) > 6.0:
            unreal.log_warning("[Qashqai] unexpected body length - check the FBX unit settings")
    return meshes


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------
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
    for h in handles:                       # attach to DefaultSceneRoot if present
        obj = lib.get_object(lib.get_data(h))
        if isinstance(obj, unreal.SceneComponent):
            root = h
            break

    def add(parent, cls, name):
        handle, fail = sds.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=parent, new_class=cls, blueprint_context=bp))
        if str(fail):
            raise RuntimeError("Could not add %s: %s" % (name, fail))
        sds.rename_subobject(handle, unreal.Text(name))
        return handle, lib.get_object(lib.get_data(handle))

    for part in manifest["parts"]:
        if part["name"] == "SM_Qashqai_Wheel":
            continue
        _, comp = add(root, unreal.StaticMeshComponent, part["name"].replace("SM_Qashqai_", ""))
        comp.set_editor_property("static_mesh", meshes[part["name"]])
        if part["name"] in ("SM_Qashqai_Glass", "SM_Qashqai_Lenses", "SM_Qashqai_Interior"):
            comp.set_editor_property("collision_profile_name", "NoCollision")
    wheel = meshes.get("SM_Qashqai_Wheel")
    for tag, spec in manifest["wheels"].items():
        x, y, z = spec["unreal_cm"]
        _, comp = add(root, unreal.StaticMeshComponent, "Wheel_" + tag)
        comp.set_editor_property("static_mesh", wheel)
        comp.set_editor_property("relative_location", unreal.Vector(x, y, z))
        comp.set_editor_property("relative_rotation", unreal.Rotator(roll=0.0, pitch=0.0,
                                                                     yaw=spec["yaw_deg_unreal"]))
        comp.set_editor_property("collision_profile_name", "NoCollision")

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    eal.save_loaded_asset(bp)
    log("built %s" % path)
    return bp


def spin_wheels(actor, degrees):
    """Editor preview helper: roll all four wheels by `degrees` about their
    axles, e.g. spin_wheels(unreal.EditorLevelLibrary.get_selected_level_actors()[0], 45)."""
    for comp in actor.get_components_by_class(unreal.StaticMeshComponent):
        name = comp.get_name()
        if name.startswith("Wheel_"):
            rot = comp.get_editor_property("relative_rotation")
            sign = 1.0 if name.endswith("L") else -1.0
            comp.set_editor_property("relative_rotation", unreal.Rotator(
                roll=0.0, pitch=rot.pitch + sign * degrees, yaw=rot.yaw))


def spawn(bp):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_object(bp, unreal.Vector(0.0, 0.0, 0.0),
                                           unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
    if actor:
        actor.set_actor_label(ACTOR_LABEL)
        log("placed %s at the world origin (nose towards +X, wheels on the ground)" % ACTOR_LABEL)
    return actor


def main():
    with open(os.path.join(EXPORT_DIR, "manifest.json")) as fh:
        manifest = json.load(fh)
    steps = 6 if SPAWN_IN_LEVEL else 5
    with unreal.ScopedSlowTask(steps, "Importing Nissan Qashqai 2017") as task:
        task.make_dialog(True)
        task.enter_progress_frame(1, "Textures")
        textures = import_textures(manifest)
        task.enter_progress_frame(1, "Materials")
        masters = {"M_QQ_Solid": build_solid_master(textures), "M_QQ_Paint": build_paint_master(),
                   "M_QQ_Glass": build_glass_master(), "M_QQ_Plate": build_plate_master(textures),
                   "M_QQ_Grille": build_grille_master(textures)}
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
