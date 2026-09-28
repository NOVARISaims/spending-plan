"""Import the L-shaped bunk bed into Unreal Engine 5 and assemble a Blueprint.

Run inside the Unreal Editor (the Python Editor Script Plugin is on by default
in UE5):
    * Tools > Execute Python Script... and choose this file, or
    * Output Log > switch the input box to "Python" > type
          py "C:/path/to/3d-models/l-shaped-bunk-bed/unreal/import_l_bunk_bed.py"

What it does:
    1. imports the oak textures (normal map set up for DirectX / flipped green)
    2. creates two master materials (M_BB_Solid, M_BB_Wood) and one material
       instance per Blender material slot
    3. imports every SM_LBunkBed_*.fbx listed in ../export/manifest.json as a
       static mesh with its UCX_ collision, and assigns the material instances
    4. builds BP_LShapedBunkBed: frame + two doors on hinge components +
       removable mattresses, and drops one into the open level

Settings can be overridden with environment variables before launching the
editor, or by editing the constants below:
    LBUNK_EXPORT_DIR   folder with the FBX files and manifest.json
    LBUNK_DEST         content folder (default /Game/Furniture/LShapedBunkBed)
    LBUNK_SPAWN        "0" to skip placing an instance in the level

Re-running the script updates the assets in place and rebuilds the Blueprint.
"""
import json
import os

import unreal

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:                       # pasted into the Python console
    HERE = os.getcwd()

EXPORT_DIR = os.environ.get("LBUNK_EXPORT_DIR",
                            os.path.normpath(os.path.join(HERE, "..", "export")))
DEST = os.environ.get("LBUNK_DEST", "/Game/Furniture/LShapedBunkBed").rstrip("/")
SPAWN_IN_LEVEL = os.environ.get("LBUNK_SPAWN", "1") != "0"
BP_NAME = "BP_LShapedBunkBed"
ACTOR_LABEL = "LShapedBunkBed"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("[LBunkBed] " + msg)


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
# Textures and materials
# ---------------------------------------------------------------------------
def import_textures(manifest):
    tex_dir = DEST + "/Textures"
    spec = manifest["textures"]
    out = {}
    for key, name, kind in (("base_color", "T_Oak_BaseColor", "color"),
                            ("roughness", "T_Oak_Roughness", "mask"),
                            ("normal", "T_Oak_Normal", "normal")):
        tex = import_file(os.path.join(EXPORT_DIR, spec[key]), tex_dir, name)[0]
        if kind == "normal":
            tex.set_editor_property("compression_settings",
                                    unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("flip_green_channel", True)   # OpenGL -> DirectX
        elif kind == "mask":
            tex.set_editor_property("compression_settings",
                                    unreal.TextureCompressionSettings.TC_MASKS)
            tex.set_editor_property("srgb", False)
        eal.save_loaded_asset(tex)
        out[kind] = tex
    return out


def _expr(material, cls, x, y, **props):
    node = mel.create_material_expression(material, cls, x, y)
    for k, v in props.items():
        node.set_editor_property(k, v)
    return node


def build_solid_master():
    m = load_or_create("M_BB_Solid", DEST + "/Materials", unreal.Material,
                       unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    color = _expr(m, unreal.MaterialExpressionVectorParameter, -500, -200,
                  parameter_name="BaseColor", default_value=unreal.LinearColor(0.8, 0.8, 0.8, 1))
    rough = _expr(m, unreal.MaterialExpressionScalarParameter, -500, 0,
                  parameter_name="Roughness", default_value=0.5)
    metal = _expr(m, unreal.MaterialExpressionScalarParameter, -500, 100,
                  parameter_name="Metallic", default_value=0.0)
    spec = _expr(m, unreal.MaterialExpressionScalarParameter, -500, 200,
                 parameter_name="Specular", default_value=0.5)
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def build_wood_master(textures):
    m = load_or_create("M_BB_Wood", DEST + "/Materials", unreal.Material,
                       unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    uv = _expr(m, unreal.MaterialExpressionTextureCoordinate, -1200, 0)
    tiling = _expr(m, unreal.MaterialExpressionScalarParameter, -1200, 120,
                   parameter_name="UVTiling", default_value=1.0)
    uv_scaled = _expr(m, unreal.MaterialExpressionMultiply, -1000, 40)
    mel.connect_material_expressions(uv, "", uv_scaled, "A")
    mel.connect_material_expressions(tiling, "", uv_scaled, "B")

    def sampler(name, tex, sampler_type, y):
        node = _expr(m, unreal.MaterialExpressionTextureSampleParameter2D, -750, y,
                     parameter_name=name, texture=tex)
        node.set_editor_property("sampler_type", sampler_type)
        mel.connect_material_expressions(uv_scaled, "", node, "UVs")
        return node

    base = sampler("BaseColorMap", textures["color"],
                   unreal.MaterialSamplerType.SAMPLERTYPE_COLOR, -300)
    rough = sampler("RoughnessMap", textures["mask"],
                    unreal.MaterialSamplerType.SAMPLERTYPE_MASKS, 0)
    normal = sampler("NormalMap", textures["normal"],
                     unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, 300)
    tint = _expr(m, unreal.MaterialExpressionVectorParameter, -500, -450,
                 parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1))
    tinted = _expr(m, unreal.MaterialExpressionMultiply, -300, -300)
    mel.connect_material_expressions(base, "RGB", tinted, "A")
    mel.connect_material_expressions(tint, "", tinted, "B")
    rscale = _expr(m, unreal.MaterialExpressionScalarParameter, -500, 120,
                   parameter_name="RoughnessScale", default_value=1.0)
    rough_out = _expr(m, unreal.MaterialExpressionMultiply, -300, 0)
    mel.connect_material_expressions(rough, "R", rough_out, "A")
    mel.connect_material_expressions(rscale, "", rough_out, "B")
    mel.connect_material_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough_out, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    return m


def build_instances(manifest, masters):
    """One material instance per Blender material slot, keyed by slot name."""
    out = {}
    for slot, spec in manifest["materials"].items():
        mi = load_or_create(spec["ue_instance"], DEST + "/Materials",
                            unreal.MaterialInstanceConstant,
                            unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, masters[spec["ue_parent"]])
        if spec["ue_parent"] == "M_BB_Solid":
            r, g, b = spec["base_color_linear"]
            mel.set_material_instance_vector_parameter_value(
                mi, "BaseColor", unreal.LinearColor(r, g, b, 1.0))
            mel.set_material_instance_scalar_parameter_value(mi, "Roughness", spec["roughness"])
            mel.set_material_instance_scalar_parameter_value(mi, "Metallic", spec["metallic"])
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
    data.set_editor_property("auto_generate_collision", False)   # use the UCX_ boxes
    data.set_editor_property("one_convex_hull_per_ucx", True)
    data.set_editor_property("generate_lightmap_u_vs", True)
    data.set_editor_property("remove_degenerates", True)
    data.set_editor_property("normal_import_method",
                             unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    return opts


def slot_names(mesh):
    return [str(m.get_editor_property("material_slot_name"))
            for m in mesh.get_editor_property("static_materials")]


def assign_materials(mesh, instances):
    for index, slot in enumerate(slot_names(mesh)):
        mi = instances.get(slot)
        if mi is None:                   # tolerate suffixes such as "_skin0"
            mi = next((v for k, v in instances.items() if slot.startswith(k)), None)
        if mi is None:
            unreal.log_warning("[LBunkBed] no material for slot %r on %s"
                               % (slot, mesh.get_name()))
            continue
        mesh.set_material(index, mi)


def import_meshes(manifest, instances):
    meshes = {}
    with LegacyFbxImporter():
        for part in manifest["parts"]:
            assets = import_file(os.path.join(EXPORT_DIR, part["fbx"]), DEST + "/Meshes",
                                 part["name"], fbx_options())
            mesh = next((a for a in assets if isinstance(a, unreal.StaticMesh)), None)
            if mesh is None:
                raise RuntimeError("No static mesh imported from " + part["fbx"])
            assign_materials(mesh, instances)
            eal.save_loaded_asset(mesh)
            meshes[part["name"]] = mesh
            log("imported %s (%d triangles in Blender)" % (mesh.get_name(), part["triangles"]))
    return meshes


def y_axis_sign(frame, manifest):
    """The frame sits behind the wall line in Blender (-Y) and should land on +Y
    in Unreal.  Returns -1 if the importer did not mirror Y, so hinge
    placement still lines up with the meshes."""
    box = frame.get_bounding_box()
    lo, hi = box.get_editor_property("min"), box.get_editor_property("max")
    size = (hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
    spec = manifest["overall_cm"]
    log("frame bounds %.1f x %.1f x %.1f cm (spec %.1f x %.1f x %.1f)"
        % (size + (spec["length_x"], spec["depth_y"], spec["height_z"])))
    if abs(size[2] - spec["height_z"]) > 2.0:
        unreal.log_warning("[LBunkBed] unexpected frame height - check the FBX unit settings")
    if (lo.y + hi.y) >= 0.0:
        return 1.0
    unreal.log_warning("[LBunkBed] Y was not mirrored on import; adjusting hinge positions")
    return -1.0


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


def build_blueprint(manifest, meshes, ysign):
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
        name = part["name"].replace("SM_LBunkBed_", "")
        mesh = meshes[part["name"]]
        if "hinge" in part:
            x, y, z = part["pivot_unreal_cm"]
            hinge_h, hinge = add(root, unreal.SceneComponent, "Hinge_" + name)
            hinge.set_editor_property("relative_location", unreal.Vector(x, y * ysign, z))
            _, comp = add(hinge_h, unreal.StaticMeshComponent, name)
        else:
            _, comp = add(root, unreal.StaticMeshComponent, name)
        comp.set_editor_property("static_mesh", mesh)

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    eal.save_loaded_asset(bp)
    log("built %s" % path)
    return bp


def open_doors(actor, manifest, degrees, ysign=1.0):
    """Swing the wardrobe doors of a placed bunk bed (editor preview helper),
    e.g. open_doors(unreal.EditorLevelLibrary.get_selected_level_actors()[0], m, 90)."""
    for part in manifest["parts"]:
        hinge = part.get("hinge")
        if not hinge:
            continue
        name = "Hinge_" + part["name"].replace("SM_LBunkBed_", "")
        yaw = hinge["unreal_open_yaw_sign"] * ysign * min(degrees, hinge["max_open_deg"])
        for comp in actor.get_components_by_class(unreal.SceneComponent):
            if comp.get_name() == name:
                comp.set_editor_property("relative_rotation",
                                         unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))


def spawn(bp):
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actor = actors.spawn_actor_from_object(bp, unreal.Vector(0.0, 0.0, 0.0),
                                           unreal.Rotator(roll=0.0, pitch=0.0, yaw=0.0))
    if actor:
        actor.set_actor_label(ACTOR_LABEL)
        log("placed %s at the world origin (back edge on the X axis, facing +Y)" % ACTOR_LABEL)
    return actor


def main():
    with open(os.path.join(EXPORT_DIR, "manifest.json")) as fh:
        manifest = json.load(fh)
    steps = 6 if SPAWN_IN_LEVEL else 5
    with unreal.ScopedSlowTask(steps, "Importing L-shaped bunk bed") as task:
        task.make_dialog(True)
        task.enter_progress_frame(1, "Textures")
        textures = import_textures(manifest)
        task.enter_progress_frame(1, "Materials")
        masters = {"M_BB_Solid": build_solid_master(), "M_BB_Wood": build_wood_master(textures)}
        instances = build_instances(manifest, masters)
        task.enter_progress_frame(1, "Static meshes")
        meshes = import_meshes(manifest, instances)
        ysign = y_axis_sign(meshes["SM_LBunkBed_Frame"], manifest)
        task.enter_progress_frame(1, "Blueprint")
        bp = build_blueprint(manifest, meshes, ysign)
        if SPAWN_IN_LEVEL:
            task.enter_progress_frame(1, "Placing in level")
            spawn(bp)
        task.enter_progress_frame(1, "Saving")
        eal.save_directory(DEST, only_if_is_dirty=True, recursive=True)
    log("done: assets in " + DEST)


if __name__ == "__main__":
    main()
