"""BeamNG material definitions (materials.json, v1.5): tolerant loading and
texture path resolution against the extracted package."""
import glob
import json
import os
import re

# the folder the six package zips were extracted into (it contains vehicles/)
ROOT = os.path.abspath(os.environ.get("QASHQAI16_PKG", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                  "..", "package")))


def _load(path):
    t = open(path, encoding="utf-8-sig").read()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        t = re.sub(r"//[^\n]*", "", t)
        t = re.sub(r",(\s*[}\]])", r"\1", t)
        return json.loads(t)


def load_all():
    mats = {}
    for f in sorted(glob.glob(ROOT + "/vehicles/**/*.materials.json", recursive=True)):
        for k, v in _load(f).items():
            if isinstance(v, dict) and str(v.get("class", "")).lower() == "material":
                mats[v.get("mapTo", k)] = dict(v, _file=f)
    return mats


_index = None


def resolve(ref):
    """Package file for a material texture reference (BeamNG accepts .png
    references for .dds files), or None."""
    global _index
    if not ref:
        return None
    if _index is None:
        _index = {}
        for f in glob.glob(ROOT + "/vehicles/**/*", recursive=True):
            if os.path.isfile(f):
                _index.setdefault(os.path.basename(f).lower(), []).append(f)
    rel = ref.lstrip("/").replace("\\", "/")
    base, ext = os.path.splitext(rel)
    cands = [ROOT + "/" + rel]
    for e in (".dds", ".DDS", ".png", ".jpg"):
        cands.append(ROOT + "/" + base + e)
    for c in cands:
        if os.path.isfile(c):
            return c
    stem = os.path.basename(base).lower()
    for e in (".dds", ".png", ".jpg"):
        hits = _index.get(stem + e)
        if hits:
            return sorted(hits)[0]
    return None
