"""Denetci isik modeli (numpy, hucre hucre dongu yok).

* Blok isigi: kaynaklarin (blok veritabanindaki durum basina isik yayimi) her adimda 1 azalan
  Manhattan yayilimi. Tam opak kup (SOLID_RENDER) isik almaz; yarim bloklar (levha, merdiven...)
  dolu yuzlerinden isik gecirmez (yuz kapatma bitleri). Oyunun isik motorunun iyi bir yaklasigi.
* Gok isigi: "gokyuzune acik sutun" yaklasimi; hucrenin ustunde gok isigini kesen blok yoksa acik.
* Canavar dogma: alti saglam ustu (sturdy UP) gecerli zemin + hucre ve ustu dogma-bos + blok isigi 0.
"""
from __future__ import annotations

import numpy as np

from ..blockdb import FACE_BIT

# (dy, dz, dx, isigin cikti yuzu (kaynak hucrede), isigin girdigi yuz (hedef hucrede))
DIRS6 = (
    (1, 0, 0, "up", "down"),
    (-1, 0, 0, "down", "up"),
    (0, 1, 0, "south", "north"),
    (0, -1, 0, "north", "south"),
    (0, 0, 1, "east", "west"),
    (0, 0, -1, "west", "east"),
)

# Canavarin uzerinde dogamayacagi (isValidSpawn=never/ozel) yaygin bloklar
NO_SPAWN_FLOOR = ("glass", "ice", "leaves", "barrier", "magma_block")


def _slices(d: int, n: int) -> tuple[slice, slice]:
    """out[i] = a[i - d] icin (hedef, kaynak) dilimleri."""
    if d >= 0:
        return slice(d, n), slice(0, n - d)
    return slice(0, n + d), slice(-d, n)


def propagate(emit: np.ndarray, solid: np.ndarray, occ: np.ndarray | None = None, max_steps: int = 15) -> np.ndarray:
    """Blok isigi yayilimi.

    emit: (Y,Z,X) tamsayi isik yayimi (0..15); solid: isik almayan hucreler (tam opak);
    occ: (Y,Z,X) uint8 yuz bitleri: hucrenin bu yuzunden isik gecmez (yarim bloklar). Donus: uint8 isik.
    Yalniz kaynaklarin 15 blok cevresi islenir (buyuk yapilarda hiz)."""
    L = np.asarray(emit, dtype=np.int16)
    if not L.any():
        return np.zeros(L.shape, dtype=np.uint8)
    nz = np.nonzero(L)
    lo = [max(0, int(a.min()) - 15) for a in nz]
    hi = [min(L.shape[i], int(nz[i].max()) + 16) for i in range(3)]
    sl = tuple(slice(lo[i], hi[i]) for i in range(3))
    sub = _propagate_box(L[sl], solid[sl], None if occ is None else occ[sl], max_steps)
    out = np.zeros(L.shape, dtype=np.uint8)
    out[sl] = sub
    return out


def _propagate_box(L: np.ndarray, solid: np.ndarray, occ: np.ndarray | None, max_steps: int) -> np.ndarray:
    L = L.copy()
    Y, Z, X = L.shape
    recv = ~solid
    allow = []
    for dy, dz, dx, f_out, f_in in DIRS6:
        ok = recv.copy()
        if occ is not None:
            # kaynak hucre A = B - d: A'nin f_out yuzu ya da B'nin f_in yuzu doluysa gecmez
            ys, ysrc = _slices(dy, Y)
            zs, zsrc = _slices(dz, Z)
            xs, xsrc = _slices(dx, X)
            occ_a = np.zeros_like(occ)
            occ_a[ys, zs, xs] = occ[ysrc, zsrc, xsrc]
            ok &= (occ_a & FACE_BIT[f_out]) == 0
            ok &= (occ & FACE_BIT[f_in]) == 0
        allow.append(ok.astype(np.int16))
    cand = np.empty_like(L)
    tmp = np.empty_like(L)
    for _ in range(max_steps):
        cand.fill(0)
        for (dy, dz, dx, _fo, _fi), ok in zip(DIRS6, allow):
            ys, ysrc = _slices(dy, Y)
            zs, zsrc = _slices(dz, Z)
            xs, xsrc = _slices(dx, X)
            t = tmp[ys, zs, xs]
            np.multiply(L[ysrc, zsrc, xsrc], ok[ys, zs, xs], out=t)
            np.maximum(cand[ys, zs, xs], t, out=cand[ys, zs, xs])
        np.subtract(cand, 1, out=cand)
        np.maximum(cand, 0, out=cand)
        new = np.maximum(L, cand)
        if np.array_equal(new, L):
            break
        L = new
    return np.clip(L, 0, 15).astype(np.uint8)


def open_to_sky(cover: np.ndarray) -> np.ndarray:
    """cover: gok isigini kesen hucreler. Donus: hucrenin ustundeki sutunda hic kesici yoksa True."""
    acc = np.logical_or.accumulate(cover[::-1], axis=0)[::-1]
    out = np.ones(cover.shape, dtype=bool)
    out[:-1] = ~acc[1:]
    return out


def spawnable(floor_ok: np.ndarray, empty_ok: np.ndarray) -> np.ndarray:
    """Canavarin ayaklarinin bulunabilecegi hucreler: alt hucre gecerli zemin, kendisi ve ustu dogma-bos."""
    out = np.zeros(floor_ok.shape, dtype=bool)
    out[1:-1] = floor_ok[:-2] & empty_ok[1:-1] & empty_ok[2:]
    return out


def is_spawn_floor(name: str, sturdy: int, emission: int) -> bool:
    """Ustunde canavar dogabilecek zemin (ust yuzu tam saglam, kendisi isik kaynagi degil, ozel istisna degil)."""
    if not (sturdy & FACE_BIT["up"]):
        return False
    if emission >= 14:
        return False
    for t in NO_SPAWN_FLOOR:
        if t in name:
            return False
    return True


__all__ = ["propagate", "open_to_sky", "spawnable", "is_spawn_floor", "DIRS6"]
