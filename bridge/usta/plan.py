"""Usta plan bicimi (USTAPLN1).

Dosya = gzip( "USTAPLN1" | u32 baslik_uzunlugu | baslik JSON (UTF-8) | hucre verisi )
- baslik: {"version":1, "origin":[x,y,z], "size":[sx,sy,sz], "palette":[...],
           "block_entities":[{"pos":[x,y,z],"snbt":"..."}],
           "entities":[{"type":"minecraft:painting","pos":[x,y,z],"yaw":0,"pitch":0,"snbt":"..."}],
           "meta":{...}, "index_width":2|4}
- hucre verisi: sx*sy*sz adet little-endian u16 (palet > 65535 ise u32);
  sira: indeks = (y*sz + z)*sx + x  (numpy dizisi sekli (sy, sz, sx), C sirasi).
- palet[0] = "keep" (dokunma), palet[1] = "minecraft:air" (temizle).
  "!" ile baslayan girdi "tam" demektir: oyun baglanti/sekil duzeltmesi (settle) yapmaz.
Koordinatlar plan icinde yerel (0..size-1); dunya konumu = origin + yerel.
"""
from __future__ import annotations

import gzip
import io
import json
import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MAGIC = b"USTAPLN1"
KEEP = "keep"
AIR = "minecraft:air"


@dataclass
class Plan:
    origin: tuple[int, int, int]
    cells: np.ndarray  # (sy, sz, sx) tamsayi palet indeksleri
    palette: list[str]
    block_entities: list[dict[str, Any]] = field(default_factory=list)
    entities: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.palette or self.palette[0] != KEEP:
            raise ValueError("palet[0] 'keep' olmali")
        if len(self.palette) < 2 or self.palette[1] != AIR:
            raise ValueError("palet[1] 'minecraft:air' olmali")
        if self.cells.ndim != 3:
            raise ValueError("cells 3 boyutlu olmali (sy, sz, sx)")

    @property
    def size(self) -> tuple[int, int, int]:
        sy, sz, sx = self.cells.shape
        return (sx, sy, sz)

    def count_changed(self) -> int:
        return int(np.count_nonzero(self.cells))

    def count_solid(self) -> int:
        return int(np.count_nonzero(self.cells > 1))

    def world_bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        ox, oy, oz = self.origin
        sx, sy, sz = self.size
        return (ox, oy, oz), (ox + sx - 1, oy + sy - 1, oz + sz - 1)

    def state_at(self, x: int, y: int, z: int) -> str:
        return self.palette[int(self.cells[y, z, x])]

    def histogram(self) -> dict[str, int]:
        ids, counts = np.unique(self.cells, return_counts=True)
        return {self.palette[int(i)]: int(c) for i, c in zip(ids, counts) if i > 0}

    # ---- serilestirme ----
    def to_bytes(self) -> bytes:
        width = 2 if len(self.palette) <= 0xFFFF else 4
        sx, sy, sz = self.size
        header = {
            "version": 1,
            "origin": [int(v) for v in self.origin],
            "size": [sx, sy, sz],
            "palette": self.palette,
            "block_entities": self.block_entities,
            "entities": self.entities,
            "meta": self.meta,
            "index_width": width,
        }
        hb = json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        dtype = "<u2" if width == 2 else "<u4"
        body = np.ascontiguousarray(self.cells, dtype=dtype).tobytes(order="C")
        raw = io.BytesIO()
        with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6, mtime=0) as gz:
            gz.write(MAGIC)
            gz.write(struct.pack("<I", len(hb)))
            gz.write(hb)
            gz.write(body)
        return raw.getvalue()

    @staticmethod
    def from_bytes(data: bytes) -> "Plan":
        raw = gzip.decompress(data)
        if raw[:8] != MAGIC:
            raise ValueError("USTAPLN1 degil")
        (hl,) = struct.unpack("<I", raw[8:12])
        header = json.loads(raw[12:12 + hl].decode("utf-8"))
        sx, sy, sz = header["size"]
        dtype = "<u2" if header.get("index_width", 2) == 2 else "<u4"
        n = sx * sy * sz
        cells = np.frombuffer(raw[12 + hl:], dtype=dtype, count=n).reshape((sy, sz, sx)).astype(np.int32)
        return Plan(origin=tuple(header["origin"]), cells=cells, palette=header["palette"],
                    block_entities=header.get("block_entities", []), entities=header.get("entities", []),
                    meta=header.get("meta", {}))

    def save(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self.to_bytes())

    @staticmethod
    def load(path: str) -> "Plan":
        with open(path, "rb") as f:
            return Plan.from_bytes(f.read())


def empty_plan(origin: tuple[int, int, int], size: tuple[int, int, int]) -> Plan:
    sx, sy, sz = size
    return Plan(origin=origin, cells=np.zeros((sy, sz, sx), dtype=np.int32), palette=[KEEP, AIR])
