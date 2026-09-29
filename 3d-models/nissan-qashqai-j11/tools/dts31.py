"""Reader for BeamNG's Torque DTS shape files, version 31: an 8-byte header
(version, exporter version, header size), a MessagePack header (info,
compression, body size, object names) and a zstd-compressed body that is a
stream of MessagePack values following Torque3D's TSShape layout.  Arrays are
written as (count, element size, bytes)."""
import struct
import msgpack
import numpy as np
import zstandard

MESH_STANDARD, MESH_SKIN, MESH_DECAL, MESH_SORTED, MESH_NULL = 0, 1, 2, 3, 4


class Stream:
    def __init__(self, data):
        self.up = msgpack.Unpacker(raw=True, strict_map_key=False, max_buffer_size=1 << 31, max_bin_len=1 << 31,
                                   max_str_len=1 << 31, max_array_len=1 << 31, max_map_len=1 << 31)
        self.up.feed(data)
        self.it = iter(self.up)
        self.count = 0

    def val(self):
        self.count += 1
        return next(self.it)

    def arr(self, dtype, width=None):
        n, es, data = self.val(), self.val(), self.val()
        if n and len(data) != n * es:
            raise ValueError("array size mismatch: %d x %d vs %d bytes" % (n, es, len(data)))
        dt = np.dtype(dtype)
        cols = width if width else (es // dt.itemsize if es else 1)
        if not n:
            return np.zeros((0, cols), dt)
        a = np.frombuffer(data, dtype=dt)
        return a.reshape(n, -1) if cols > 1 else a


class Mesh:
    pass


def read_mesh(s):
    m = Mesh()
    m.type = s.val()
    if m.type == MESH_NULL:
        return m
    m.numFrames, m.numMatFrames, m.parentMesh = s.val(), s.val(), s.val()
    m.bounds, m.center, m.radius = s.val(), s.val(), s.val()
    m.verts = s.arr("<f4")
    m.tverts = s.arr("<f4")
    m.tverts2 = s.arr("<f4")
    m.colors = s.arr("<u1")
    m.norms = s.arr("<f4")
    m.encodedNorms = s.arr("<u1")
    n, es, data = s.val(), s.val(), s.val()
    m.prims = np.frombuffer(data, dtype=np.dtype([("start", "<i4"), ("num", "<i4"), ("mat", "<u4")])) if n else \
        np.zeros(0, dtype=np.dtype([("start", "<i4"), ("num", "<i4"), ("mat", "<u4")]))
    n, es, data = s.val(), s.val(), s.val()
    m.indices = np.frombuffer(data, dtype="<u4" if es == 4 else "<u2") if n else np.zeros(0, "<u4")
    m.tangents = s.arr("<f4")
    m.vertsPerFrame, m.flags = s.val(), s.val()
    if m.type == MESH_SKIN:
        raise NotImplementedError("skin meshes")
    return m


class Shape:
    def __init__(self, path):
        b = open(path, "rb").read()
        self.version, self.exporter, hsize = struct.unpack("<HHI", b[:8])
        self.header = msgpack.unpackb(b[8:8 + hsize], raw=False, strict_map_key=False)
        body = b[8 + hsize:]
        if self.header.get("compression"):
            body = zstandard.ZstdDecompressor().stream_reader(body).read()
        s = self.s = Stream(body)
        self.smallest_size, self.smallest_dl = s.val(), s.val()
        self.radius, self.tube_radius, self.center, self.bounds = s.val(), s.val(), s.val(), s.val()
        self.nodes = s.arr("<i4")              # name, parent, firstObject, firstChild, nextSibling
        self.objects = s.arr("<i4")            # name, numMeshes, startMesh, node, nextSibling, firstDecal
        self.sub_first_node = s.arr("<i4")
        self.sub_first_object = s.arr("<i4")
        self.sub_num_nodes = s.arr("<i4")
        self.sub_num_objects = s.arr("<i4")
        self.default_rot = s.arr("<i2")        # Quat16 x, y, z, w (/ 32767)
        self.default_trans = s.arr("<f4")
        self.node_rot = s.arr("<i2")
        self.node_trans = s.arr("<f4")
        self.node_uscale = s.arr("<f4")
        self.node_ascale = s.arr("<f4")
        self.node_arb_scale = s.arr("<f4")
        self.node_arb_rot = s.arr("<i2")
        self.ground_trans = s.arr("<f4")
        self.ground_rot = s.arr("<i2")
        n, es, data = s.val(), s.val(), s.val()
        self.object_states = np.frombuffer(data, dtype=np.dtype([("vis", "<f4"), ("frame", "<i4"), ("matFrame", "<i4")])) if n else None
        self.triggers = s.arr("<u1")
        n, es, data = s.val(), s.val(), s.val()
        self.details = np.frombuffer(data, dtype=np.dtype([("name", "<i4"), ("subShape", "<i4"), ("objectDetail", "<i4"),
                                                           ("size", "<f4"), ("avgErr", "<f4"), ("maxErr", "<f4"),
                                                           ("polys", "<i4"), ("bbDim", "<i4"), ("bbDL", "<i4"),
                                                           ("bbEq", "<i4"), ("bbPol", "<i4"), ("bbPolAng", "<f4"),
                                                           ("bbPoles", "<i4")]))
        nn = s.val()
        self.names = [s.val().decode("utf-8", "replace") for _ in range(nn)]
        nm = s.val()
        self.meshes = [read_mesh(s) for _ in range(nm)]
        self.tail = []
        try:
            while True:
                self.tail.append(s.val())
        except StopIteration:
            pass

    def node_name(self, i):
        return self.names[self.nodes[i, 0]]

    def object_name(self, i):
        return self.names[self.objects[i, 0]]
