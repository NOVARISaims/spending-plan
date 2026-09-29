"""Blender objects from BeamNG DTS v31 shapes (see dts31.py).

Objects stay in BeamNG space (Z up, the car facing -Y, +X = the car's left)
with their node transforms; the caller moves them into place."""
import numpy as np
import bpy
from mathutils import Matrix, Quaternion

import dts31


def node_worlds(S):
    """World matrix of every node: parent @ translation @ rotation, with the
    Quat16 rotations stored as (x, y, z, w) / 32767."""
    q = S.default_rot.astype(float) / 32767.0
    t = S.default_trans.astype(float)
    W = [None] * len(S.nodes)

    def get(i):
        if W[i] is None:
            x, y, z, w = q[i]
            Q = Quaternion((w, x, y, z))
            if Q.magnitude > 0:
                Q.normalize()
            L = Matrix.Translation(t[i]) @ Q.to_matrix().to_4x4()
            p = S.nodes[i, 1]
            W[i] = get(p) @ L if p >= 0 else L
        return W[i]
    return [get(i) for i in range(len(S.nodes))]


def material_names(S):
    """Material list stored after the meshes: 7 values per material."""
    return [S.tail[2 + 7 * i].decode() for i in range((len(S.tail) - 2) // 7)]


def object_index(S):
    return {S.object_name(i): i for i in range(len(S.objects))}


def build_object(S, i, worlds, mats, material_for, name=None, use_node=True, drop_flat_uv=False):
    """Mesh object for DTS object i (detail level 0), or None if it has no
    geometry.  material_for(dts_material_name, object_name) returns the
    bpy material for each primitive.  use_node=False leaves out the node
    transform (for meshes whose vertices are already in vehicle space);
    drop_flat_uv removes triangles whose UVs collapse to a point."""
    oname = S.object_name(i)
    name = name or oname
    nm, sm, node = S.objects[i, 1], S.objects[i, 2], S.objects[i, 3]
    if nm <= 0:
        return None
    m = S.meshes[sm]
    if m.type == dts31.MESH_NULL or len(m.verts) == 0:
        return None
    tris, tmat = [], []
    for p in m.prims:
        mat = int(p["mat"])
        if mat & 0xC0000000:
            raise ValueError("%s: non-triangle primitive %x" % (oname, mat))
        idx = np.asarray(m.indices[p["start"]:p["start"] + p["num"]], dtype=np.int64).reshape(-1, 3)
        tris.append(idx)
        tmat.append(np.full(len(idx), -1 if mat & 0x10000000 else mat & 0x0FFFFFFF))
    tris = np.vstack(tris)
    tmat = np.concatenate(tmat)
    V = m.verts.astype(np.float64)
    # winding: agree with the stored vertex normals
    fn = np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]])
    has_normals = len(m.norms) == len(V)
    flip = has_normals and (np.einsum("ij,ij->i", fn, m.norms[tris].sum(1)) < 0).mean() > 0.5
    if flip:
        tris = tris[:, ::-1]
    # drop zero-area triangles and exact duplicates (same corners in the same
    # cyclic order and the same material); back faces are kept
    area = np.linalg.norm(np.cross(V[tris[:, 1]] - V[tris[:, 0]], V[tris[:, 2]] - V[tris[:, 0]]), axis=1)
    r = np.argmin(tris, axis=1)
    rot = np.stack([tris[np.arange(len(tris)), (r + k) % 3] for k in range(3)], axis=1)
    key = np.column_stack([rot, tmat])
    _, first = np.unique(key, axis=0, return_index=True)
    keep = np.zeros(len(tris), bool)
    keep[first] = True
    keep &= area > 1e-12
    if drop_flat_uv and len(m.tverts) == len(V):
        T = m.tverts.astype(np.float64)
        e1, e2 = T[tris[:, 1]] - T[tris[:, 0]], T[tris[:, 2]] - T[tris[:, 0]]
        keep &= np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 2e-6
    tris, tmat = tris[keep], tmat[keep]
    # only the vertices the triangles use
    used, inv = np.unique(tris, return_inverse=True)
    loops = tris.ravel()                     # original indices, for the per-corner UVs
    tris = inv.reshape(tris.shape)

    me = bpy.data.meshes.new(name)
    me.from_pydata(V[used].tolist(), [], tris.tolist())
    slot = {}
    for k in sorted(set(tmat.tolist())):
        mname = mats[k] if k >= 0 else "__nomat__"
        me.materials.append(material_for(mname, oname))
        slot[k] = len(me.materials) - 1
    me.polygons.foreach_set("material_index", np.array([slot[k] for k in tmat], dtype=np.int32))
    if len(m.tverts) == len(V):
        uv = me.uv_layers.new(name="UVMap")
        T = m.tverts[loops].astype(np.float64).copy()
        T[:, 1] = 1.0 - T[:, 1]
        uv.data.foreach_set("uv", T.ravel())
    if len(m.tverts2) == len(V):
        uv2 = me.uv_layers.new(name="UVMap2")
        T = m.tverts2[loops].astype(np.float64).copy()
        T[:, 1] = 1.0 - T[:, 1]
        uv2.data.foreach_set("uv", T.ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(tris), dtype=bool))
    if has_normals:
        N = m.norms[used].astype(np.float64)
        N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        me.normals_split_custom_set_from_vertices(N.tolist())
    me.update()
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = worlds[node] if use_node else Matrix.Identity(4)
    ob["dts_object"] = oname
    ob["dts_node"] = S.node_name(node)
    return ob
