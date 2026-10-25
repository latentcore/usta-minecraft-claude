"""Sematik ice/disa aktarma (C9): Sponge Schematic v3 (.schem), Litematica (.litematic), vanilla yapi sablonu (.nbt).
Bicim belgelerinden kendi kodumuzla yazildi (GPL kod kopyalanmadi). Plan <-> dosya."""
from __future__ import annotations

import re
import time

import numpy as np

from .. import blockdb
from ..plan import AIR, KEEP, Plan
from . import nbt as N

# ------------------------------------------------------------------ SNBT (alt kume) <-> NBT
_NUM = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)([bBsSlLfFdD]?)$")


class _SnbtParser:
    def __init__(self, s: str):
        self.s = s
        self.i = 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def peek(self):
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def value(self):
        c = self.peek()
        if c == "{":
            return self.compound()
        if c == "[":
            return self.list()
        if c in "\"'":
            return N.Tag(N.STRING, self.quoted())
        return self.scalar()

    def quoted(self):
        q = self.s[self.i]
        self.i += 1
        out = []
        while self.i < len(self.s):
            ch = self.s[self.i]
            if ch == "\\":
                out.append(self.s[self.i + 1])
                self.i += 2
                continue
            if ch == q:
                self.i += 1
                return "".join(out)
            out.append(ch)
            self.i += 1
        raise ValueError("kapanmamış dizgi")

    def word(self):
        self.ws()
        j = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "_-.+"):
            self.i += 1
        return self.s[j:self.i]

    def scalar(self):
        w = self.word()
        m = _NUM.match(w)
        if m:
            num, suf = m.group(1), m.group(2).lower()
            if suf == "b":
                return N.Byte(int(float(num)))
            if suf == "s":
                return N.Short(int(float(num)))
            if suf == "l":
                return N.Long(int(float(num)))
            if suf == "f":
                return N.Float(float(num))
            if suf == "d" or "." in num or "e" in num.lower():
                return N.Double(float(num))
            return N.Int(int(num))
        if w == "true":
            return N.Byte(1)
        if w == "false":
            return N.Byte(0)
        return N.Tag(N.STRING, w)

    def compound(self):
        self.i += 1
        d = {}
        while True:
            c = self.peek()
            if c == "}":
                self.i += 1
                return N.Tag(N.COMPOUND, d)
            k = self.quoted() if c in "\"'" else self.word()
            self.ws()
            assert self.s[self.i] == ":", "':' bekleniyordu"
            self.i += 1
            d[k] = self.value()
            if self.peek() == ",":
                self.i += 1

    def list(self):
        self.i += 1
        self.ws()
        if self.s[self.i:self.i + 2] in ("I;", "L;", "B;"):
            kind = self.s[self.i]
            self.i += 2
            vals = []
            while self.peek() != "]":
                t = self.scalar()
                vals.append(int(t.value))
                if self.peek() == ",":
                    self.i += 1
            self.i += 1
            return {"I": N.IntArray, "L": N.LongArray, "B": lambda v: N.ByteArray(bytes(x & 255 for x in v))}[kind](vals)
        items = []
        while self.peek() != "]":
            items.append(self.value())
            if self.peek() == ",":
                self.i += 1
        self.i += 1
        et = items[0].type if items else N.END
        return N.Tag(N.LIST, (et, items))


def snbt_to_tag(s: str) -> N.Tag:
    return _SnbtParser(s).value()


def _tag_to_snbt(v) -> str:
    if isinstance(v, dict):
        return "{" + ",".join(f"{_key(k)}:{_tag_to_snbt(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_tag_to_snbt(x) for x in v) + "]"
    if isinstance(v, (bytes, bytearray)):
        return "[B;" + ",".join(f"{b}b" for b in v) + "]"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, bool):
        return "1b" if v else "0b"
    if isinstance(v, float):
        return f"{v}d"
    return str(v)


def _key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_\-.+]+", k) else '"' + k + '"'


def nbt_to_snbt(d: dict) -> str:
    return _tag_to_snbt(d)


def _state_compound(s: str) -> dict:
    name, props = blockdb.split_state(s)
    d = {"Name": name}
    if props:
        d["Properties"] = {k: v for k, v in props.items()}
    return d


def _state_from_compound(c: dict) -> str:
    name = c.get("Name", "minecraft:air")
    props = c.get("Properties") or {}
    if props:
        return name + "[" + ",".join(f"{k}={v}" for k, v in props.items()) + "]"
    return name


def _data_version() -> int:
    try:
        return int(blockdb.get().data_version or 0)
    except Exception:
        return 0


def _states_and_ids(plan: Plan) -> tuple[list[str], np.ndarray]:
    """Plan paletinden 'keep' ve '!' oneklerini atarak sematik paleti; keep -> hava."""
    pal = []
    idx = {}
    remap = np.zeros(len(plan.palette), dtype=np.int64)
    for i, s in enumerate(plan.palette):
        st = AIR if s == KEEP else s.lstrip("!")
        if st not in idx:
            idx[st] = len(pal)
            pal.append(st)
        remap[i] = idx[st]
    return pal, remap[plan.cells]


# ------------------------------------------------------------------ Sponge v3
def _varints(values: np.ndarray) -> bytes:
    out = bytearray()
    for v in values.tolist():
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def _read_varints(data: bytes, n: int) -> np.ndarray:
    out = np.empty(n, dtype=np.int64)
    i = k = 0
    while k < n:
        v = shift = 0
        while True:
            b = data[i]
            i += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
        out[k] = v
        k += 1
    return out


def export_schem(plan: Plan, name: str = "usta") -> bytes:
    pal, ids = _states_and_ids(plan)
    sx, sy, sz = plan.size
    order = ids.reshape(sy, sz, sx)  # index = x + z*W + y*W*L (y, z, x C sirasi)
    bes = []
    for be in plan.block_entities:
        x, y, z = be["pos"]
        st = plan.palette[int(plan.cells[y, z, x])].lstrip("!")
        data = snbt_to_tag(be.get("snbt") or "{}").value
        bes.append({"Pos": N.IntArray([x, y, z]), "Id": _be_id(st), "Data": data})
    ents = []
    for e in plan.entities:
        data = snbt_to_tag(e.get("snbt") or "{}").value
        data["id"] = e["type"]
        ents.append({"Pos": N.List(N.DOUBLE, [N.Double(c) for c in e["pos"]]), "Id": e["type"], "Data": data})
    sch = {
        "Version": N.Int(3), "DataVersion": N.Int(_data_version()),
        "Width": N.Short(sx), "Height": N.Short(sy), "Length": N.Short(sz),
        "Offset": N.IntArray([0, 0, 0]),
        "Metadata": {"Name": name, "Author": "Usta", "Date": N.Long(int(time.time() * 1000)),
                     "UstaOrigin": N.IntArray(list(plan.origin))},
        "Blocks": {"Palette": {s: N.Int(i) for i, s in enumerate(pal)}, "Data": N.ByteArray(_varints(order.ravel())),
                   "BlockEntities": N.List(N.COMPOUND, bes)},
        "Entities": N.List(N.COMPOUND, ents),
    }
    return N.dumps({"Schematic": sch}, "")


def _be_id(state: str) -> str:
    n = state.split("[", 1)[0]
    base = n.split(":", 1)[1]
    for suf, be in (("_wall_sign", "sign"), ("_wall_hanging_sign", "hanging_sign"), ("_hanging_sign", "hanging_sign"), ("_sign", "sign"),
                    ("_wall_banner", "banner"), ("_banner", "banner"), ("_bed", "bed"), ("_shulker_box", "shulker_box")):
        if base.endswith(suf):
            return "minecraft:" + be
    if base in ("trapped_chest",):
        return "minecraft:trapped_chest"
    return n


def import_schem(data: bytes) -> Plan:
    _, root = N.loads(data)
    sch = root.get("Schematic", root)
    W, H, L = int(sch["Width"]) & 0xFFFF, int(sch["Height"]) & 0xFFFF, int(sch["Length"]) & 0xFFFF
    blocks = sch.get("Blocks") or {"Palette": sch.get("Palette"), "Data": sch.get("BlockData"), "BlockEntities": sch.get("BlockEntities", [])}
    pal_map = blocks["Palette"]
    inv = {int(v): k for k, v in pal_map.items()}
    vals = _read_varints(blocks["Data"], W * H * L).reshape(H, L, W)
    pal = [KEEP, AIR]
    remap = {}
    for i, s in inv.items():
        s2 = blockdb.get().canonical(s) if s != "minecraft:air" else AIR
        if s2 not in pal:
            pal.append(s2)
        remap[i] = pal.index(s2)
    cells = np.vectorize(lambda v: remap[int(v)])(vals).astype(np.int32)
    bes = []
    for be in blocks.get("BlockEntities") or []:
        p = be.get("Pos")
        bes.append({"pos": [int(p[0]), int(p[1]), int(p[2])], "snbt": nbt_to_snbt(be.get("Data", {}))})
    ents = []
    for e in sch.get("Entities") or []:
        d = dict(e.get("Data", {}))
        d.pop("id", None)
        d.pop("UUID", None)
        ents.append({"type": e.get("Id", d.get("id")), "pos": list(e["Pos"]), "yaw": 0, "pitch": 0, "snbt": nbt_to_snbt(d)})
    meta = sch.get("Metadata", {}) or {}
    return Plan(origin=(0, 0, 0), cells=cells, palette=pal, block_entities=bes, entities=ents, meta={"name": meta.get("Name", "şematik")})


# ------------------------------------------------------------------ Litematica
def _pack_bits(values: np.ndarray, bits: int) -> list[int]:
    n = len(values)
    total = (n * bits + 63) // 64
    longs = [0] * total
    for i, v in enumerate(values.tolist()):
        start = i * bits
        a, off = start >> 6, start & 63
        longs[a] |= (v << off) & 0xFFFFFFFFFFFFFFFF
        if off + bits > 64:
            longs[a + 1] |= v >> (64 - off)
    return longs


def _unpack_bits(longs: list[int], bits: int, n: int) -> np.ndarray:
    L = [x & 0xFFFFFFFFFFFFFFFF for x in longs]
    mask = (1 << bits) - 1
    out = np.empty(n, dtype=np.int64)
    for i in range(n):
        start = i * bits
        a, off = start >> 6, start & 63
        v = L[a] >> off
        if off + bits > 64:
            v |= L[a + 1] << (64 - off)
        out[i] = v & mask
    return out


def export_litematic(plan: Plan, name: str = "usta") -> bytes:
    pal, ids = _states_and_ids(plan)
    if pal[0] != AIR:
        air = pal.index(AIR) if AIR in pal else None
        if air is None:
            pal.insert(0, AIR)
            ids = ids + 1
        else:
            pal[0], pal[air] = pal[air], pal[0]
            ids = np.where(ids == 0, -1, ids)
            ids = np.where(ids == air, 0, ids)
            ids = np.where(ids == -1, air, ids)
    sx, sy, sz = plan.size
    bits = max(2, int(np.ceil(np.log2(max(2, len(pal))))))
    longs = _pack_bits(ids.reshape(sy, sz, sx).ravel(), bits)
    tes = []
    for be in plan.block_entities:
        d = snbt_to_tag(be.get("snbt") or "{}").value
        d["x"], d["y"], d["z"] = N.Int(be["pos"][0]), N.Int(be["pos"][1]), N.Int(be["pos"][2])
        tes.append(d)
    now = N.Long(int(time.time() * 1000))
    region = {
        "Position": {"x": N.Int(0), "y": N.Int(0), "z": N.Int(0)},
        "Size": {"x": N.Int(sx), "y": N.Int(sy), "z": N.Int(sz)},
        "BlockStatePalette": N.List(N.COMPOUND, [_state_compound(s) for s in pal]),
        "BlockStates": N.LongArray(longs),
        "TileEntities": N.List(N.COMPOUND, tes),
        "Entities": N.List(N.COMPOUND, []),
        "PendingBlockTicks": N.List(N.COMPOUND, []), "PendingFluidTicks": N.List(N.COMPOUND, []),
    }
    root = {
        "Version": N.Int(6), "SubVersion": N.Int(1), "MinecraftDataVersion": N.Int(_data_version()),
        "Metadata": {"Name": name, "Author": "Usta", "Description": "Usta ile üretildi", "RegionCount": N.Int(1),
                     "TotalBlocks": N.Int(int(np.count_nonzero(ids))), "TotalVolume": N.Int(sx * sy * sz),
                     "TimeCreated": now, "TimeModified": now,
                     "EnclosingSize": {"x": N.Int(sx), "y": N.Int(sy), "z": N.Int(sz)}},
        "Regions": {name: region},
    }
    return N.dumps(root, "")


def import_litematic(data: bytes) -> Plan:
    _, root = N.loads(data)
    regions = root["Regions"]
    rname, reg = next(iter(regions.items()))
    sx, sy, sz = (abs(int(reg["Size"][k])) for k in ("x", "y", "z"))
    pal_raw = [_state_from_compound(c) for c in reg["BlockStatePalette"]]
    bits = max(2, int(np.ceil(np.log2(max(2, len(pal_raw))))))
    vals = _unpack_bits(reg["BlockStates"], bits, sx * sy * sz).reshape(sy, sz, sx)
    pal = [KEEP, AIR]
    remap = []
    for s in pal_raw:
        s2 = AIR if s == "minecraft:air" else blockdb.get().canonical(s)
        if s2 not in pal:
            pal.append(s2)
        remap.append(pal.index(s2))
    cells = np.array(remap, dtype=np.int32)[vals]
    bes = []
    for te in reg.get("TileEntities") or []:
        d = dict(te)
        x, y, z = int(d.pop("x", 0)), int(d.pop("y", 0)), int(d.pop("z", 0))
        bes.append({"pos": [x, y, z], "snbt": nbt_to_snbt(d)})
    return Plan(origin=(0, 0, 0), cells=cells, palette=pal, block_entities=bes, meta={"name": root.get("Metadata", {}).get("Name", rname)})


# ------------------------------------------------------------------ vanilla yapi sablonu
def export_structure_nbt(plan: Plan) -> bytes:
    pal, ids = _states_and_ids(plan)
    sx, sy, sz = plan.size
    a = ids.reshape(sy, sz, sx)
    bes = {tuple(be["pos"]): be.get("snbt") or "{}" for be in plan.block_entities}
    blocks = []
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                d = {"pos": N.List(N.INT, [N.Int(x), N.Int(y), N.Int(z)]), "state": N.Int(int(a[y, z, x]))}
                if (x, y, z) in bes:
                    d["nbt"] = snbt_to_tag(bes[(x, y, z)]).value
                blocks.append(d)
    ents = []
    for e in plan.entities:
        d = snbt_to_tag(e.get("snbt") or "{}").value
        d["id"] = e["type"]
        p = e["pos"]
        ents.append({"pos": N.List(N.DOUBLE, [N.Double(c) for c in p]),
                     "blockPos": N.List(N.INT, [N.Int(int(c // 1)) for c in p]), "nbt": d})
    root = {"DataVersion": N.Int(_data_version()), "size": N.List(N.INT, [N.Int(sx), N.Int(sy), N.Int(sz)]),
            "palette": N.List(N.COMPOUND, [_state_compound(s) for s in pal]), "blocks": N.List(N.COMPOUND, blocks),
            "entities": N.List(N.COMPOUND, ents)}
    return N.dumps(root, "")


def import_structure_nbt(data: bytes) -> Plan:
    _, root = N.loads(data)
    sx, sy, sz = (int(v) for v in root["size"])
    pal_raw = [_state_from_compound(c) for c in root["palette"]]
    pal = [KEEP, AIR]
    remap = []
    for s in pal_raw:
        s2 = AIR if s == "minecraft:air" else ("minecraft:structure_void" if s == "minecraft:structure_void" else blockdb.get().canonical(s))
        if s2 not in pal:
            pal.append(s2)
        remap.append(pal.index(s2))
    cells = np.zeros((sy, sz, sx), dtype=np.int32)
    bes = []
    for b in root["blocks"]:
        x, y, z = (int(v) for v in b["pos"])
        p = remap[int(b["state"])]
        if pal[p] == "minecraft:structure_void":
            continue
        cells[y, z, x] = p
        if "nbt" in b:
            bes.append({"pos": [x, y, z], "snbt": nbt_to_snbt(b["nbt"])})
    return Plan(origin=(0, 0, 0), cells=cells, palette=pal, block_entities=bes, meta={"name": "yapı şablonu"})


EXPORTERS = {"schem": export_schem, "litematic": export_litematic, "nbt": export_structure_nbt}
IMPORTERS = {"schem": import_schem, "litematic": import_litematic, "nbt": import_structure_nbt}
