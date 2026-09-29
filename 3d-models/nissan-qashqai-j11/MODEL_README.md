# Nissan Qashqai J11 — DE17 YAU (Blender and Unreal Engine 5)

The default car from the BeamNG.drive **qashqai16** package (FastLane): the
N-Connecta 1.6 dCi manual, pre-facelift (2014–2017), with 18" N-Connecta
wheels. The owner's car differs from it in four ways, and nothing else was
changed:

| Change | What was done |
|---|---|
| Paint | The package's own **Gun Metallic** paint replaces the default Ink Blue: base colour sRGB 0.309 grey (linear 0.078), metallic 0.8, roughness 0.65, clear coat 1.0, clear-coat roughness 0.05. |
| Number plates | UK plates **DE17 YAU**: white at the front, yellow at the rear, Charles Wright 2001 characters on 520 × 111 mm plates. They replace the placeholder EU plates, using the package's plate meshes. |
| Roof rails | Removed: the package's separate roof-rail part is left off, leaving its plain roof panel. |
| Right-hand drive | The package's own `_rhd` parts: dashboard, steering wheel, instruments and needles, stalks, start button, pedals, handbrake, glovebox, interior mirror, front door cards, wing-mirror glass and wipers. |

## Files

The model comes in four zip files of under 30 MB each. **Extract all four into the same folder.** They merge into one `Qashqai_J11_DE17YAU` folder:

```
Qashqai_J11_DE17YAU/
  README.md
  blender/Qashqai_J11_DE17YAU.blend      part 1
  unreal/  SM_QashqaiJ11_*.fbx, manifest.json, import_qashqai_j11.py      part 2
  textures/  *.png (shared by Blender and Unreal)      parts 3 and 4
```

**Blender** — `blender/Qashqai_J11_DE17YAU.blend`
- Saved with Blender 4.5; open it in 4.5 or newer.
- Textures load from `../textures`, so keep the folder layout. To make a single self-contained file, use File > External Data > Pack Resources, then save.
- Collections: `Exterior`, `Glass`, `Interior`, `Mechanical`, `Wheels`.
- The `Studio (not part of the car)` collection has a camera, floor, key light and CC0 HDRI, so F12 renders straight away in Cycles.
- Each part keeps its BeamNG name and pivot (steering wheel, needles, pedals and door glass keep their own origins).

**Unreal Engine 5** — the `unreal` folder, plus `textures`
- `import_qashqai_j11.py` does the whole import. In the editor, choose Tools > Execute Python Script and pick the file, or in the Output Log's Python box enter `py "C:/path/to/Qashqai_J11_DE17YAU/unreal/import_qashqai_j11.py"`.
  - It imports the textures and builds four master materials (opaque, clear coat, masked, translucent) plus one material instance per slot.
  - It imports the six meshes and assembles `BP_QashqaiJ11`: body, glass, interior, steering wheel, mechanical parts and four wheels. It places one in the open level at the origin.
  - Assets go to `/Game/Vehicles/QashqaiJ11`.
- Units are centimetres, nose towards +X, driver's side (right) towards +Y, wheels on the ground at Z = 0.

Blender axes: X forward, Y left, Z up. The origin is on the ground, midway between the axles, on the centre line. Length is 4.37 m, wheelbase 2.64 m.

## Things the package does not contain, and how they were handled

- **Tyres** come from BeamNG's common content, which is not in the package. The configured size, 235/50 R18, was generated as a plain tyre with four grooves.
- **Wheel placement** normally comes from the JBeam, which is also missing. The N-Connecta rims sit on the hub centres from the package's hub meshes, on the J11's track (1565 mm front, 1550 mm rear). The right-hand rims are turned to face outwards.
- **Lights are off.**
  - In BeamNG the lamp materials are placeholders, swapped at run time. The model uses the package's own "off" lamp materials: chrome reflectors with the lamp normal bake, behind the clear and red lenses.
  - The instrument warning-light decals are left out, because they are invisible with the ignition off. The dash and navigation screens are dark.
- **Missing textures:**
  - The package leaves out the "vivace" donor textures used by the engine, underbody and pedal materials, so those have plain colours.
  - The painted inner-panel material uses the Gun Metallic paint, because its coverage mask is also missing.
- The four tail-lamp inner meshes carry a stray 2.6 m node offset in the file. It was ignored, because their vertices are already in place.

## Rights

This model is converted from FastLane's BeamNG.drive mod. The package came without a licence file. Treat the model as personal use only, and check with the mod's author before sharing or publishing it.
