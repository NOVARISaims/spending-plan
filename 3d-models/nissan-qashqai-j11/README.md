# Nissan Qashqai J11 — DE17 YAU, from the BeamNG qashqai16 package

Tools that turn the BeamNG.drive **qashqai16** static visual package
(FastLane's J11 Qashqai) into a Blender scene and UE5 assets. The result is
the package's default car (N-Connecta 1.6 dCi, pre-facelift) with only the
owner's differences applied:

- **Paint:** the package's own Gun Metallic paint.
- **Number plates:** UK plates DE17 YAU, white at the front and yellow at the
  rear.
- **Right-hand drive:** the package's own `_rhd` interior parts.

`MODEL_README.md` describes the delivered model files and how to use them in
Blender and Unreal.

**The model files are not in this repository.** They are derived from a
third-party mod that came without a licence, and this repository is public.
They were handed over directly, as four zip parts: the `.blend`, the UE5
package and the shared textures. To make them again from your copy of the
package, see below.

## Rebuilding

1. Extract the six `qashqai16_static_visual_essentials_part0N.zip` archives
   into `3d-models/nissan-qashqai-j11/package/`. That folder is git-ignored.
   Alternatively, point the `QASHQAI16_PKG` environment variable at the
   folder that contains `vehicles/`.
2. Use Python 3.11 with the Blender 4.5 `bpy` module, numpy, msgpack,
   zstandard and Pillow. The builds here used Pillow 12.3, which decodes the
   BC4, BC5 and BC7 `.dds` textures.
3. Run, from `3d-models/nissan-qashqai-j11/`:

   ```
   python tools/build_q16.py out           # scene -> out/stage1.blend, textures, material specs
   python tools/export_q16.py out          # out/blender/*.blend, out/unreal/*, out/textures/*, out/gltf/*.glb
                                           # (--pack also writes a .blend with the textures packed)
   python tools/render_q16.py out/stage1.blend out/check_ front34 rear34 dash plate_f plate_r
   ```

   `out/` is git-ignored as well.

## Tools

| File | Purpose |
|---|---|
| `tools/dts31.py` | Reader for BeamNG's DTS v31 shapes. These have an 8-byte header, a MessagePack header and a zstd body of MessagePack values in Torque3D TSShape order. |
| `tools/dtsblend.py` | Makes Blender mesh objects from DTS objects: node transforms, per-primitive materials, UVs (V flipped), stored split normals and winding checked against them. |
| `tools/config.py` | Meshes of the default configuration (`nconnecta_16dci_m.pc`), inferred from part names because the JBeam is not in the package, plus the RHD swaps. |
| `tools/bngmat.py` | Tolerant `*.materials.json` loading and texture lookup. It handles `.png` references to `.dds` files. |
| `tools/matconv.py` | Flattens BeamNG v1.5 and legacy materials into one metallic/roughness layer. It bakes factors into textures, turns uniform textures into constants and converts DirectX normal maps to OpenGL. |
| `tools/build_q16.py` | Builds the car. It applies paint, plates, RHD, the "lights off" lamp materials and the configuration's skins, and generates 235/50 R18 tyres. The wheels are placed on the hubs at the J11 track. |
| `tools/export_q16.py` | Writes the Blender file (textures packed, studio set-up), the glTF and the UE5 parts, textures and `manifest.json`. |
| `tools/import_qashqai_j11.py` | UE5 editor script. It builds master materials and material instances, imports the meshes and assembles `BP_QashqaiJ11`. |
| `tools/render_q16.py` | Cycles check renders. |

## Conversion notes

- **Lamps.** Lamp materials in the meshes are placeholders that BeamNG swaps
  at run time (JBeam `glowMap`). For each lamp, the "off" material was chosen
  by sampling the lamp's UVs against the package's emissive bakes.
- **Stray node offset.** Four tail-lamp meshes carry a 2.632 m node offset
  that BeamNG never applies. Their vertices are already in place, so the
  node transform is skipped.
- **Plate backs.** The plate meshes' back faces coincide with their fronts
  and have collapsed UVs. They are dropped, because in Cycles they showed
  through the characters.
- **Gun Metallic colour space.** The paint's base colour is read as sRGB.
  The package's preview of a neutral-grey car (the Acenta RHD) fits that
  reading, and reading it as linear would make it far too light.
