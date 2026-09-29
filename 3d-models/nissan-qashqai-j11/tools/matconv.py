"""BeamNG materials (v1.5 PBR stages, or legacy Torque fields) flattened to
one metallic-roughness layer each, with the textures they use written out as
PNG.

A flat material ("spec") is a dict:
    name, base (linear RGB), base_map, alpha, alpha_map, blend
    ("OPAQUE" | "CLIP" | "BLEND"), alpha_cutoff, metallic, metallic_map,
    roughness, roughness_map, normal_map, normal_strength, coat,
    coat_roughness, emission (linear RGB), emission_map, double_sided,
    source (what it was made from)
Map values are texture keys of a TextureStore.  Where a material has both a
map and a factor the product is baked into the texture, and textures that
turn out to be a single flat value become plain factors, so every channel is
either one texture or one constant.  Normal maps are stored OpenGL-style
(green up), converted from BeamNG's DirectX-style maps."""
import os
import re

import numpy as np
from PIL import Image

import bngmat


def to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def new_spec(name, source=""):
    return {"name": name, "base": [0.8, 0.8, 0.8], "base_map": None, "alpha": 1.0, "alpha_map": None,
            "blend": "OPAQUE", "alpha_cutoff": 0.5, "metallic": 0.0, "metallic_map": None,
            "roughness": 0.5, "roughness_map": None, "normal_map": None, "normal_strength": 1.0,
            "coat": 0.0, "coat_roughness": 0.03, "emission": [0.0, 0.0, 0.0], "emission_map": None,
            "double_sided": False, "source": source}


def _stem(path):
    b = os.path.basename(path)
    b = re.sub(r"(\.(dds|png|jpg|tga))+$", "", b, flags=re.I)
    b = re.sub(r"\.(color|data|normal)(\.(dds|png))?(\.\d+)?$", "", b, flags=re.I)
    b = re.sub(r"\.(dds|png)\.\d+$", "", b, flags=re.I)
    return re.sub(r"[^A-Za-z0-9_]", "_", b)


class TextureStore:
    """Reads package textures (any format Pillow decodes, including the BCn
    DDS files) and writes the processed ones as PNG into outdir."""

    def __init__(self, outdir, max_size=2048):
        self.outdir = outdir
        self.max_size = max_size
        os.makedirs(outdir, exist_ok=True)
        self._cache = {}
        self.files = {}          # key -> {"file": name.png, "kind": ..., "size": [w, h], "from": [...]}

    def load(self, ref):
        """(float32 RGBA array 0..1, path) or (None, None)."""
        path = ref if os.path.isfile(str(ref)) else bngmat.resolve(ref)
        if path is None:
            return None, None
        if path not in self._cache:
            im = Image.open(path)
            im.load()
            self._cache[path] = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
        return self._cache[path], path

    @staticmethod
    def flat(a, tol=3.0 / 255):
        """Mean value if the array is (nearly) uniform, else None."""
        a2 = a.reshape(-1, a.shape[-1]) if a.ndim == 3 else a.reshape(-1, 1)
        if a2.size == 0:
            return None
        return a2.mean(0) if np.all(a2.max(0) - a2.min(0) <= tol) else None

    def put(self, key, arr, kind, sources=()):
        """Write arr (H x W, or H x W x 3/4, values 0..1 in the encoding to
        store) as <key>.png; returns key."""
        if key in self.files:
            return key
        a = np.clip(arr, 0.0, 1.0)
        h, w = a.shape[:2]
        f = max(1, int(np.ceil(max(h, w) / self.max_size)))
        if f > 1:                                    # box filter down to <= max_size
            a = a[:h - h % f, :w - w % f]
            a = a.reshape(h // f, f, w // f, f, *a.shape[2:]).mean(axis=(1, 3))
            if kind == "normal":
                n = a * 2 - 1
                n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
                a = n * 0.5 + 0.5
        img = (a * 255.0 + 0.5).astype(np.uint8)
        mode = "L" if img.ndim == 2 else ("RGB" if img.shape[2] == 3 else "RGBA")
        name = key + ".png"
        Image.fromarray(img, mode).save(os.path.join(self.outdir, name), compress_level=7)
        self.files[key] = {"file": name, "kind": kind, "size": [int(img.shape[1]), int(img.shape[0])],
                           "from": [os.path.relpath(s, bngmat.ROOT) for s in sources]}
        return key


def _channel(a, which):
    if which == "r":
        return a[..., 0]
    if which == "a":
        return a[..., 3]
    return a[..., :3]


def colour(store, ref, factor):
    """(linear RGB constant or None, texture key or None) for a colour map
    times a linear factor."""
    factor = np.asarray(factor[:3] if factor is not None else (1, 1, 1), dtype=np.float64)
    a, path = store.load(ref) if ref else (None, None)
    if a is None:
        return list(factor), None
    rgb = _channel(a, "rgb")
    c = TextureStore.flat(rgb)
    if c is not None:
        return list(to_linear(c) * factor), None
    key = "T_" + _stem(path)
    if not np.allclose(factor, 1.0):
        vals = [factor[0]] if np.allclose(factor, factor[0]) else list(factor)
        key += "_x" + "_".join(("%.3f" % v).replace(".", "p") for v in vals)
        rgb = to_srgb(to_linear(rgb) * factor)
    return [1.0, 1.0, 1.0], store.put(key, rgb, "color", [path])


def scalar(store, ref, factor, default, channel="r"):
    """(constant or None, texture key or None) for a data map times a factor."""
    f = 1.0 if factor is None else float(factor)
    a, path = store.load(ref) if ref else (None, None)
    if a is None:
        return (default if factor is None else f), None
    ch = _channel(a, channel)
    c = TextureStore.flat(ch[..., None])
    if c is not None:
        return float(c[0]) * f, None
    key = "T_" + _stem(path) + ("" if channel == "r" else "_" + channel)
    if abs(f - 1.0) > 1e-4:
        key += "_x%s" % ("%.3f" % f).replace(".", "p")
        ch = ch * f
    return 1.0, store.put(key, ch, "data", [path])


def normal(store, ref, directx=True):
    """Texture key of an OpenGL-style normal map, or None if flat/missing."""
    a, path = store.load(ref) if ref else (None, None)
    if a is None:
        return None
    rgb = _channel(a, "rgb").copy()
    if TextureStore.flat(rgb, tol=4.0 / 255) is not None:
        return None
    if directx:
        rgb[..., 1] = 1.0 - rgb[..., 1]
    # rebuild z from x, y (some maps are two-channel BC5)
    x, y = rgb[..., 0] * 2 - 1, rgb[..., 1] * 2 - 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    rgb[..., 2] = z * 0.5 + 0.5
    return store.put("T_" + _stem(path) + "_n", rgb, "normal", [path])


def opacity(store, ref, factor):
    """(constant, texture key or None) for an opacity map: its alpha channel
    if that varies, else its red channel."""
    f = 1.0 if factor is None else float(factor)
    a, path = store.load(ref) if ref else (None, None)
    if a is None:
        return f, None
    ch = a[..., 3] if TextureStore.flat(a[..., 3:4]) is None else a[..., 0]
    c = TextureStore.flat(ch[..., None])
    if c is not None:
        return float(c[0]) * f, None
    key = "T_" + _stem(path) + "_o"
    if abs(f - 1.0) > 1e-4:
        key += "_x%s" % ("%.3f" % f).replace(".", "p")
        ch = ch * f
    return 1.0, store.put(key, ch, "data", [path])


def flatten(name, d, store):
    """Flat spec for BeamNG material definition d (first stage only, as
    activeLayers defaults to 1; painted layers are handled by the caller)."""
    spec = new_spec(name, "BeamNG material %s" % d.get("mapTo", d.get("name")))
    stages = d.get("Stages") or [{}]
    s0 = {k: v for k, v in stages[0].items() if v is not None}
    translucent = bool(d.get("translucent"))
    alpha_test = bool(d.get("alphaTest"))
    legacy = float(d.get("version") or 0) < 1.5
    missing = []

    def ref(key):
        r = s0.get(key)
        if isinstance(r, str) and r and not r.startswith("@"):
            if bngmat.resolve(r) is None:
                missing.append(os.path.basename(r))
                return None
            return r
        return None

    if legacy:
        dc = s0.get("diffuseColor", [1, 1, 1, 1])
        spec["base"], spec["base_map"] = colour(store, ref("colorMap"), to_linear(dc[:3]))
        spec["roughness"] = float(s0.get("roughnessFactor", 0.5))
        spec["metallic"] = 0.0
        alpha_factor = dc[3] if len(dc) > 3 else 1.0
    else:
        bf = s0.get("baseColorFactor", [1, 1, 1, 1])
        spec["base"], spec["base_map"] = colour(store, ref("baseColorMap"), bf)
        spec["metallic"], spec["metallic_map"] = scalar(store, ref("metallicMap"), s0.get("metallicFactor"), 0.0)
        spec["roughness"], spec["roughness_map"] = scalar(store, ref("roughnessMap"), s0.get("roughnessFactor"), 1.0)
        cc = s0.get("clearCoatFactor")
        if cc:
            ccv, cct = scalar(store, ref("clearCoatMap"), cc, 0.0)
            spec["coat"] = ccv if cct is None else float(cc)
            spec["coat_roughness"] = float(s0.get("clearCoatRoughnessFactor") or 0.0)
        if s0.get("emissiveMap") or s0.get("emissiveFactor"):
            ef = s0.get("emissiveFactor", [1, 1, 1])
            e, emap = colour(store, ref("emissiveMap"), ef) if ref("emissiveMap") else (list(ef[:3]), None)
            spec["emission"], spec["emission_map"] = e, emap
        alpha_factor = bf[3] if len(bf) > 3 else 1.0
    nref = ref("normalMap")
    spec["normal_map"] = normal(store, nref, directx=not (nref and "vivace" in nref.lower()))
    spec["normal_strength"] = float(s0.get("normalMapStrength", 1.0))
    if translucent or alpha_test:
        of = s0.get("opacityFactor")
        if of is None:
            of = alpha_factor
        oref = ref("opacityMap")
        if oref is None and alpha_test and spec["base_map"] is not None:
            oref = ref("baseColorMap") or ref("colorMap")
        spec["alpha"], spec["alpha_map"] = opacity(store, oref, of)
        if alpha_test:
            spec["blend"] = "CLIP"
            spec["alpha_cutoff"] = max(float(d.get("alphaRef", 20)) / 255.0, 0.02)
        else:
            spec["blend"] = "BLEND"
    spec["double_sided"] = bool(d.get("doubleSided"))
    if missing:
        spec["missing_textures"] = missing
    return spec
