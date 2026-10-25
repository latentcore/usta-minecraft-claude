"""Modun is verisini (jobs/<id>/data.nbt) okur: once/sonra hacimleri -> kucuk resimler, malzeme listesi."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import config
from .schem import nbt as N


def job_file(world_key: str, job_id: str) -> Path:
    return config.data_dir() / "worlds" / world_key / "jobs" / job_id / "data.nbt"


def load(world_key: str, job_id: str) -> dict:
    _, t = N.loads(job_file(world_key, job_id).read_bytes())
    box = t["box"]
    n = int(t.get("n", 0))
    idx = np.array(t["idx"], dtype=np.int64)
    out = {"box": box, "n": n, "label": t.get("label", ""), "idx": idx}
    for key in ("target", "before"):
        if key in t:
            pal = list(t[key]["palette"])
            ids = np.array(t[key]["ids"], dtype=np.int64)
            out[key] = (pal, ids)
    return out


def volumes(d: dict) -> tuple[tuple[np.ndarray, list[str]], tuple[np.ndarray, list[str]] | None]:
    """(sonra, once) hacimleri: [y,z,x] palet indeksleri; 0 = bos."""
    ox, oy, oz, sx, sy, sz = d["box"]
    idx = d["idx"]
    res = []
    for key in ("target", "before"):
        if key not in d:
            res.append(None)
            continue
        pal, ids = d[key]
        names = ["keep"] + pal
        cells = np.zeros(sx * sy * sz, dtype=np.int32)
        valid = ids >= 0
        cells[idx[valid]] = ids[valid] + 1
        res.append((cells.reshape(sy, sz, sx), names))
    return res[0], res[1]


def materials(d: dict) -> list[tuple[str, int]]:
    """Malzeme listesi (U9): yerlestirilen bloklar, hava haric."""
    if "target" not in d:
        return []
    pal, ids = d["target"]
    cnt = np.bincount(ids[ids >= 0], minlength=len(pal))
    agg: dict[str, int] = {}
    for i, c in enumerate(cnt.tolist()):
        if c == 0:
            continue
        name = pal[i].split("[", 1)[0]
        if name in ("minecraft:air", "minecraft:cave_air"):
            continue
        agg[name] = agg.get(name, 0) + c
    return sorted(agg.items(), key=lambda t: -t[1])
