"""Oyundan gelen ikili verilerin (USTACOL1 sutunlar, USTABLK1 hacim) ayristirilmasi."""
from __future__ import annotations

import gzip
import json
import struct
from dataclasses import dataclass, field

import numpy as np

UNKNOWN = -32768


@dataclass
class Columns:
    x0: int
    z0: int
    w: int
    h: int
    min_y: int
    max_y: int
    surface: np.ndarray        # (h, w) en ust non-air blogun y'si (WORLD_SURFACE)
    surface_state: np.ndarray  # (h, w) palet indeksi
    ground: np.ndarray         # MOTION_BLOCKING_NO_LEAVES (su yuzeyi ya da agac altindaki zemin)
    ground_state: np.ndarray
    floor: np.ndarray          # OCEAN_FLOOR (suyun altindaki kati zemin)
    floor_state: np.ndarray
    biome: np.ndarray
    palette: list[str]
    biomes: list[str]

    def known(self) -> np.ndarray:
        return self.surface != UNKNOWN

    def at(self, x: int, z: int) -> dict:
        i, j = z - self.z0, x - self.x0
        return {
            "surface": int(self.surface[i, j]), "surface_block": self.palette[int(self.surface_state[i, j])],
            "ground": int(self.ground[i, j]), "ground_block": self.palette[int(self.ground_state[i, j])],
            "floor": int(self.floor[i, j]), "floor_block": self.palette[int(self.floor_state[i, j])],
            "biome": self.biomes[int(self.biome[i, j])] if self.biomes else "?",
        }


def _unpack(data: bytes, magic: bytes) -> tuple[dict, bytes]:
    raw = gzip.decompress(data)
    if raw[:8] != magic:
        raise ValueError(f"{magic!r} bekleniyordu")
    (hl,) = struct.unpack("<I", raw[8:12])
    hdr = json.loads(raw[12:12 + hl].decode("utf-8"))
    return hdr, raw[12 + hl:]


def parse_columns(data: bytes) -> Columns:
    hdr, body = _unpack(data, b"USTACOL1")
    w, h = hdr["w"], hdr["h"]
    n = w * h
    arr = np.frombuffer(body, dtype="<i2", count=n * 7).reshape(7, h, w)
    u = arr.view(np.uint16)
    return Columns(
        x0=hdr["x0"], z0=hdr["z0"], w=w, h=h, min_y=hdr["min_y"], max_y=hdr["max_y"],
        surface=arr[0].astype(np.int32), surface_state=u[1].astype(np.int32),
        ground=arr[2].astype(np.int32), ground_state=u[3].astype(np.int32),
        floor=arr[4].astype(np.int32), floor_state=u[5].astype(np.int32),
        biome=u[6].astype(np.int32), palette=hdr["palette"], biomes=hdr.get("biomes", []),
    )


@dataclass
class Blocks:
    origin: tuple[int, int, int]
    size: tuple[int, int, int]  # sx, sy, sz
    cells: np.ndarray           # (sy, sz, sx) palet indeksi; 0 = bilinmiyor
    palette: list[str]
    block_entities: list[dict] = field(default_factory=list)

    def state(self, wx: int, wy: int, wz: int) -> str:
        x, y, z = wx - self.origin[0], wy - self.origin[1], wz - self.origin[2]
        return self.palette[int(self.cells[y, z, x])]


def parse_blocks(data: bytes) -> Blocks:
    hdr, body = _unpack(data, b"USTABLK1")
    sx, sy, sz = hdr["size"]
    cells = np.frombuffer(body, dtype="<u2", count=sx * sy * sz).reshape(sy, sz, sx).astype(np.int32)
    return Blocks(origin=tuple(hdr["origin"]), size=(sx, sy, sz), cells=cells, palette=hdr["palette"],
                  block_entities=hdr.get("block_entities", []))
