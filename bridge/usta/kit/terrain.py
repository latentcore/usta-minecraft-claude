"""Terrain shaping on a local heightmap (Usta kit). Every function edits the Build so that, when placed, the world
terrain changes (natural layers: top block, 3-4 subsoil, stone below; material above is set to air only where
needed) and returns the NEW heightmap.

Convention: hm = int array (D, W); hm[i, j] = y of the current top SOLID ground block of local column x=j, z=i
(same local frame as the Build; under water = the water bed). surface: optional (D, W) block names of the current
top blocks (keeps sand as sand, stone as stone...). water: optional (D, W) bool mask of EXISTING water columns
(+ water_y level). Water made here is recorded in b.meta["terrain"] and later calls see it automatically.

  flatten(b, hm, pad, y=None, blend=None, max_slope=0.6, mode="both"|"cut"|"fill", material=None) -> hm
      pad: (x0, z0, x1, z1) inclusive or (D,W) bool mask; y: pad top block (default median); natural blended
      edges (auto width from the height difference, noisy outline, max 1 block step per column near the pad).
  cut(b, hm, pad, y=None, **kw) -> hm                     only lowers (terrace into a slope)
  cost(hm, pad, y=None, blend=None) -> {"y","best_y","cut","fill","total","pad_cut","pad_fill","area","changed",...}
  smooth(b, hm, area=None, sigma=2.0, strength=1.0, feather=4) -> hm        gaussian smoothing with soft edge
  hill(b, hm, x, z, radius, height, rough=0.3, stretch=1.0, angle=0.0) -> hm  height<0 digs a hollow; steep = rock
  lake(b, hm, x, z, radius, depth=3, level=None, shore=3, rough=0.3, plants=True) -> hm
      organic outline, sand/gravel/clay/dirt bed, sandy shore, lily pads/seagrass/sugar cane; fully enclosed.
  river(b, hm, path, width=5, depth=2, meander=0.5, banks=3, plants=True) -> hm
      path [(x, z), ...]; meanders, flows downhill in level steps separated by stone weirs, closed ends,
      kept inside the map; joins an existing lake when it ends in one.
  waterfall(b, hm, x, z, direction="south", height=None, width=2, pool=4, basin=3) -> hm
      (x, z) = lip cell, water falls toward `direction`; builds a rock cliff, upper basin and plunge pool;
      only the lip/falling column is open (recorded in b.meta["terrain"]["outlets"]).
  coast(b, hm, side="south", width=None, level=None, beach=6, depth=6, open_edge=False) -> hm
      sea along one map side with beach + dunes; sealed by a sandbar/reef rim unless open_edge=True.
  beach(b, hm, width=5, water=None, level=None) -> hm     sandy shore + shallow shelf along existing water
  road(b, hm, path, width=3, style="mixed"|"path"|"gravel"|"cobble"|"stone", max_grade=0.5, bridge=True,
       lights=False) -> hm   follows the terrain with gentle grade (cut/fill + blended shoulders), half-steps as
       slabs, steeper steps as stairs, plank bridges where it crosses water (listed in meta["terrain"]["bridges"]).
  forest(b, hm, area=None, density=0.5, species_mix="oak", seed=0, **kw) -> hm   (trees.forest; avoids water/roads)
  water_info(b) -> {"water","level","outlets","bridges","road"};  leaks(b) -> [(x, y, z, dir)] open water faces
Order: shape terrain and water first, then roads, then buildings/trees. All randomness is seeded (seed=...).
"""
from __future__ import annotations

import math
import random

import numpy as np

from .. import blockdb
from . import trees as _trees
from .trees import _area_mask, _fbm2, _hash, _mix, _vnoise2

__all__ = ["flatten", "cut", "cost", "smooth", "hill", "lake", "river", "waterfall", "coast", "beach", "road", "forest",
           "water_info", "leaks", "SIDES", "ROAD_STYLES"]

NOLEVEL = -(10 ** 6)
SIDES = ("north", "south", "east", "west")
_DIR = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}

# ============================================================================ grid helpers
def _hm(hm) -> np.ndarray:
    a = np.asarray(hm)
    if a.ndim != 2 or a.shape[0] < 3 or a.shape[1] < 3:
        raise ValueError("hm must be a 2D (D, W) heightmap, at least 3x3")
    return np.rint(a).astype(np.int64)


def _sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * t * (t * (t * 6 - 15) + 10)


def _gauss(a, sigma):
    a = np.asarray(a, dtype=np.float64)
    if sigma <= 0:
        return a.copy()
    r = int(math.ceil(sigma * 3))
    x = np.arange(-r, r + 1)
    k = np.exp(-(x * x) / (2.0 * sigma * sigma))
    k /= k.sum()
    D, W = a.shape
    p = np.pad(a, ((r, r), (0, 0)), mode="edge")
    out = np.zeros_like(a)
    for i in range(2 * r + 1):
        out += k[i] * p[i:i + D, :]
    p = np.pad(out, ((0, 0), (r, r)), mode="edge")
    out = np.zeros_like(a)
    for i in range(2 * r + 1):
        out += k[i] * p[:, i:i + W]
    return out


def _dil4(m, n=1):
    m = np.asarray(m, bool)
    for _ in range(n):
        o = m.copy()
        o[1:] |= m[:-1]
        o[:-1] |= m[1:]
        o[:, 1:] |= m[:, :-1]
        o[:, :-1] |= m[:, 1:]
        m = o
    return m


def _nb4(a, fill, fn):
    """Reduce the 4 neighbours of every cell with fn (np.minimum / np.maximum); outside = fill."""
    p = np.pad(a, 1, mode="constant", constant_values=fill)
    return fn(fn(p[:-2, 1:-1], p[2:, 1:-1]), fn(p[1:-1, :-2], p[1:-1, 2:]))


def _edt_idx(mask):
    """Exact Euclidean distance to the nearest True cell + its (i, j) index."""
    mask = np.asarray(mask, bool)
    D, W = mask.shape
    if not mask.any():
        z = np.zeros((D, W), np.int64)
        return np.full((D, W), np.inf), (z, z)
    BIG = 10 ** 7
    idx = np.arange(W)[None, :]
    left = np.maximum.accumulate(np.where(mask, idx, -BIG), axis=1)
    right = np.minimum.accumulate(np.where(mask, idx, BIG)[:, ::-1], axis=1)[:, ::-1]
    dl = idx - left
    dr = right - idx
    hj = np.where(dl <= dr, left, right)
    g = np.minimum(dl, dr).astype(np.float64)
    g[g > D + W + 2] = 1e7
    g2 = g * g
    out = np.empty((D, W))
    ki = np.empty((D, W), np.int64)
    ks = np.arange(D)
    ch = max(1, int(3_000_000 // max(1, D * W)))
    cols = np.arange(W)
    for i0 in range(0, D, ch):
        ii = np.arange(i0, min(D, i0 + ch))
        d2 = g2[None, :, :] + ((ii[:, None] - ks[None, :]) ** 2)[:, :, None].astype(np.float64)
        k = d2.argmin(axis=1)
        out[ii] = np.take_along_axis(d2, k[:, None, :], axis=1)[:, 0, :]
        ki[ii] = k
    nj = hj[ki, cols[None, :]]
    return np.sqrt(out), (ki, np.clip(nj, 0, W - 1))


def _border_dist(D, W):
    ii, jj = np.mgrid[0:D, 0:W]
    return np.minimum(np.minimum(ii, jj), np.minimum(D - 1 - ii, W - 1 - jj)).astype(np.float64)


def _pad_mask(pad, D, W) -> np.ndarray:
    if isinstance(pad, np.ndarray) and pad.dtype == bool:
        if pad.shape != (D, W):
            raise ValueError(f"pad mask shape {pad.shape} != heightmap {(D, W)}")
        m = pad.copy()
    else:
        if len(pad) != 4:
            raise ValueError("pad must be (x0, z0, x1, z1) or a (D, W) bool mask")
        m = _area_mask(pad, D, W)
    if not m.any():
        raise ValueError("pad lies outside the heightmap")
    return m


def _components(mask):
    """Connected components (4-neighbour) label array (-1 = background)."""
    mask = np.asarray(mask, bool)
    D, W = mask.shape
    lab = np.where(mask, np.arange(D * W).reshape(D, W), D * W + 1).astype(np.int64)
    big = D * W + 1
    for _ in range(D + W + 4):
        nb = _nb4(lab, big, np.minimum)
        new = np.where(mask, np.minimum(lab, nb), big)
        if (new == lab).all():
            break
        lab = new
    return np.where(mask, lab, -1)


# ============================================================================ registry (water, roads ...)
def _state(b, hm, water=None, water_y=None):
    shape = tuple(hm.shape)
    t = b.meta.get("terrain")
    if not isinstance(t, dict) or t.get("shape") != shape:
        t = {"shape": shape, "water": np.zeros(shape, bool), "level": np.full(shape, NOLEVEL, np.int64),
             "outlets": set(), "bridges": [], "road": np.zeros(shape, bool), "trees": []}
        b.meta["terrain"] = t
    if water is not None:
        wm = np.asarray(water, bool)
        if wm.shape != shape:
            raise ValueError(f"water mask shape {wm.shape} != heightmap {shape}")
        new = wm & ~t["water"]
        if new.any():
            if water_y is not None:
                lv = np.broadcast_to(np.asarray(water_y, np.int64), shape)
            else:  # estimate: a natural water surface sits at its lowest bank
                lv = np.full(shape, NOLEVEL, np.int64)
                lab = _components(new)
                ring = _dil4(new) & ~new
                for c in np.unique(lab[lab >= 0]):
                    comp = lab == c
                    rr = _dil4(comp) & ring
                    lv[comp] = int(hm[rr].min()) if rr.any() else int(hm[comp].max()) + 1
            t["level"] = np.where(new, lv, t["level"])
            t["water"] = t["water"] | new
    return t


def water_info(b) -> dict:
    """Water/road registry of this Build (masks are (D, W) arrays of the last heightmap shape)."""
    t = b.meta.get("terrain") or {}
    return {k: t.get(k) for k in ("water", "level", "outlets", "bridges", "road")}


def _protect_water(N, hm, st, allow_fill=None):
    """Keep water columns unchanged (unless filled above their level where allowed) and never lower a bank below
    the adjacent water surface."""
    w = st["water"]
    if not w.any():
        return N
    N = N.copy()
    lev = st["level"]
    keep = w.copy()
    if allow_fill is not None:
        keep &= ~(allow_fill & (N >= lev))
    N[keep] = hm[keep]
    wl = np.where(w & keep, lev, NOLEVEL)
    need = _nb4(wl, NOLEVEL, np.maximum)
    land = ~(w & keep)
    N[land] = np.maximum(N[land], need[land])
    return N


# ============================================================================ materials
_MAT = {
    "grass_block": ("grass_block", "dirt", "stone"), "dirt": ("dirt", "dirt", "stone"),
    "coarse_dirt": ("coarse_dirt", "dirt", "stone"), "podzol": ("podzol", "dirt", "stone"),
    "mycelium": ("mycelium", "dirt", "stone"), "rooted_dirt": ("rooted_dirt", "dirt", "stone"),
    "moss_block": ("moss_block", "dirt", "stone"), "pale_moss_block": ("pale_moss_block", "dirt", "stone"),
    "dirt_path": ("grass_block", "dirt", "stone"), "farmland": ("grass_block", "dirt", "stone"),
    "mud": ("mud", "mud", "clay"), "sand": ("sand", "sand", "sandstone"), "red_sand": ("red_sand", "red_sand", "red_sandstone"),
    "gravel": ("gravel", "gravel", "stone"), "clay": ("clay", "clay", "stone"),
    "stone": ("stone", "stone", "stone"), "andesite": ("andesite", "stone", "stone"),
    "diorite": ("diorite", "stone", "stone"), "granite": ("granite", "stone", "stone"),
    "tuff": ("tuff", "tuff", "stone"), "calcite": ("calcite", "stone", "stone"),
    "deepslate": ("deepslate", "deepslate", "deepslate"), "sandstone": ("sandstone", "sandstone", "sandstone"),
    "red_sandstone": ("red_sandstone", "red_sandstone", "red_sandstone"),
    "snow_block": ("snow_block", "dirt", "stone"), "snow": ("snow_block", "dirt", "stone"),
    "powder_snow": ("snow_block", "dirt", "stone"), "ice": ("packed_ice", "packed_ice", "stone"),
    "packed_ice": ("packed_ice", "packed_ice", "stone"), "terracotta": ("terracotta", "terracotta", "terracotta"),
}
_ROCK = (("stone", 0.62), ("andesite", 0.18), ("cobblestone", 0.08), ("mossy_cobblestone", 0.07), ("tuff", 0.05))


def _bname(s) -> str:
    return str(s).lstrip("!").split("[", 1)[0].split(":", 1)[-1]


def _soil(name) -> tuple[str, str, str]:
    n = _bname(name)
    if n in _MAT:
        return _MAT[n]
    if n.endswith("_terracotta"):
        return (n, n, "terracotta")
    if n.endswith("_concrete_powder") or n.endswith("_concrete"):
        return ("grass_block", "dirt", "stone")
    return ("grass_block", "dirt", "stone")


class _Pal:
    """Turns block names into Build palette ids (cached)."""

    def __init__(self, b):
        self.b = b
        self.c = {}

    def __call__(self, s):
        if s is None:
            return 0
        i = self.c.get(s)
        if i is None:
            i = self.b.pid(s)
            self.c[s] = i
        return i

    def grid(self, names):
        arr = np.asarray(names, dtype=object)
        out = np.zeros(arr.shape, np.int64)
        for v in set(arr.ravel().tolist()):
            out[arr == v] = self(v)
        return out


def _pick(weights, u):
    """Choose from [(name, w), ...] with uniform samples u (array) -> object array of names."""
    w = np.array([max(0.0, x[1]) for x in weights], np.float64)
    cw = np.cumsum(w) / max(1e-9, w.sum())
    idx = np.minimum(np.searchsorted(cw, np.clip(u, 0, 0.999999), side="right"), len(weights) - 1)
    names = np.array([x[0] for x in weights], dtype=object)
    return names[idx]


def _patchy(D, W, seed, scale=4.0, mix=0.3):
    ii, jj = np.mgrid[0:D, 0:W]
    v = (1 - mix) * _fbm2(jj, ii, scale, seed, 2) + mix * _hash(seed + 1, jj, ii)
    return np.clip((v - 0.5) * 1.6 + 0.5, 0, 0.999999)


def _layers(b, D, W, surface=None, material=None, new=None, seed=0, rocky=True):
    """(top, sub, deep) name grids for every column; steep new terrain gets rock."""
    top = np.full((D, W), "grass_block", dtype=object)
    sub = np.full((D, W), "dirt", dtype=object)
    deep = np.full((D, W), "stone", dtype=object)
    if surface is not None:
        sarr = np.asarray(surface, dtype=object)
        for v in set(sarr.ravel().tolist()):
            m = sarr == v
            t, s, d = _soil(v)
            top[m], sub[m], deep[m] = t, s, d
    if material is not None and material != "keep":
        t, s, d = _soil(material) if _bname(material) in _MAT else (material, "dirt", "stone")
        top[:] = material if _bname(material) not in _MAT else t
        sub[:] = s
        deep[:] = d
    if rocky and new is not None:
        hi = _nb4(new, -10 ** 6, np.maximum)
        lo = _nb4(new, 10 ** 6, np.minimum)
        step = np.maximum(hi - new, new - lo)
        u = _patchy(D, W, seed + 71, 3.0, 0.4)
        rock = _pick(_ROCK, u)
        steep = step >= 3
        med = (step == 2) & (u < 0.3)
        grassy = np.isin(top, ["grass_block", "podzol", "mycelium", "moss_block", "pale_moss_block", "snow_block",
                               "coarse_dirt", "dirt"])
        top[steep & grassy] = rock[steep & grassy]
        sub[steep & grassy] = rock[steep & grassy]
        top[med & grassy & (u < 0.15)] = "coarse_dirt"
    return top, sub, deep


# ============================================================================ writing columns / water
def _natural_ids(b):
    db = b.db
    n = len(b.palette)
    nat = np.zeros(n, bool)
    wat = np.zeros(n, bool)
    full = np.zeros(n, bool)
    nat[0] = nat[1] = True
    for i in range(2, n):
        st = b.palette[i].lstrip("!")
        try:
            sid = db.id(st)
            f = int(db.flags[sid])
        except Exception:
            continue
        name = _bname(st)
        nat[i] = bool(db.natural[sid]) or name.endswith(("_leaves", "_log", "_wood")) or bool(f & blockdb.PLANT)
        wat[i] = name == "water" or bool(f & blockdb.FLUID) or "waterlogged=true" in st
        full[i] = bool(f & blockdb.FULL)
    return nat, wat, full


def _commit(b, old, new, top, sub, deep, *, changed=None, clear=2, sub_depth=3, seed=0, force_lo=None, protect=True):
    """Write column changes. top/sub/deep: (D,W) palette id grids. Cells (new, max(old,new)+clear] -> air;
    new -> top; sub for 3-4 cells below; deep fills down to the old surface; force_lo extends sub downward."""
    D, W = old.shape
    ch = (new != old) if changed is None else (np.asarray(changed, bool) | (new != old))
    if force_lo is not None:
        ch = ch | (force_lo < new)
    if not ch.any():
        return
    ii, jj = np.nonzero(ch)
    i0, i1, j0, j1 = int(ii.min()), int(ii.max()), int(jj.min()), int(jj.max())
    sl = (slice(i0, i1 + 1), slice(j0, j1 + 1))
    o, n, c = old[sl], new[sl], ch[sl]
    clr = np.broadcast_to(np.asarray(clear, np.int64), (D, W))[sl]
    sd = sub_depth + (_hash(seed + 5, jj.min() + np.arange(n.shape[1])[None, :],
                            ii.min() + np.arange(n.shape[0])[:, None]) < 0.5).astype(np.int64)
    flo = None if force_lo is None else force_lo[sl]
    lo_col = n - sd - 1
    if flo is not None:
        lo_col = np.minimum(lo_col, flo)
    ylo = int(lo_col[c].min())
    yhi = int(np.maximum(np.maximum(o, n) + clr, n)[c].max())
    Y = np.arange(ylo, yhi + 1)[:, None, None]
    cc = c[None]
    nn = n[None]
    air = cc & (Y > nn) & (Y <= (np.maximum(o, n) + clr)[None])
    topm = cc & (Y == nn)
    subm = cc & (Y < nn) & (Y >= (n - sd)[None])
    if flo is not None:
        subm |= cc & (Y < nn) & (Y >= flo[None])
    deepm = cc & (Y < (n - sd)[None]) & (Y > o[None]) & ~subm
    ids = np.zeros((Y.shape[0],) + n.shape, np.int64)
    ids[air] = 1
    ids[topm] = np.broadcast_to(top[sl][None], ids.shape)[topm]
    ids[subm] = np.broadcast_to(sub[sl][None], ids.shape)[subm]
    ids[deepm] = np.broadcast_to(deep[sl][None], ids.shape)[deepm]
    if protect:
        cur = b.ids_box(j0, ylo, i0, j1, yhi, i1)
        nat, wat, _full = _natural_ids(b)
        ok = nat[cur] & ~(wat[cur] & (ids == 1))
        ids[~ok] = 0
    b.put_ids(j0, ylo, i0, ids.astype(np.int32))


def _put_water(b, mask, level, bottom):
    """Water source blocks in columns `mask` from bottom+1 up to level (inclusive)."""
    if not mask.any():
        return
    ii, jj = np.nonzero(mask)
    i0, i1, j0, j1 = int(ii.min()), int(ii.max()), int(jj.min()), int(jj.max())
    sl = (slice(i0, i1 + 1), slice(j0, j1 + 1))
    m, lv, bt = mask[sl], level[sl], bottom[sl]
    ylo = int(bt[m].min()) + 1
    yhi = int(lv[m].max())
    if yhi < ylo:
        return
    Y = np.arange(ylo, yhi + 1)[:, None, None]
    sel = m[None] & (Y > bt[None]) & (Y <= lv[None])
    cur = b.ids_box(j0, ylo, i0, j1, yhi, i1)
    nat, _w, _f = _natural_ids(b)
    ids = np.where(sel & nat[cur], b.pid("water[level=0]"), 0)
    b.put_ids(j0, ylo, i0, ids.astype(np.int32))


def _seal(b, N, wmask, level, top, sub):
    """Make every horizontal neighbour and the floor of every water cell an explicit solid block."""
    D, W = N.shape
    if not wmask.any():
        return N
    if wmask[0, :].any() or wmask[-1, :].any() or wmask[:, 0].any() or wmask[:, -1].any():
        raise ValueError("internal: water reached the heightmap border")
    BIG = 10 ** 6
    wlo = np.where(wmask, N + 1, BIG)
    whi = np.where(wmask, level, -BIG)
    need_lo = _nb4(wlo, BIG, np.minimum)
    need_hi = _nb4(whi, -BIG, np.maximum)
    land = ~wmask
    N = N.copy()
    low = land & (N < need_hi)
    raised = np.zeros_like(low)
    if low.any():
        raised = low
        N[low] = need_hi[low]
    lo = np.where(wmask, np.minimum(need_lo, N), need_lo)
    req = (lo <= N) & ((need_lo < BIG) | wmask)
    if not req.any():
        return N
    ii, jj = np.nonzero(req)
    i0, i1, j0, j1 = int(ii.min()), int(ii.max()), int(jj.min()), int(jj.max())
    sl = (slice(i0, i1 + 1), slice(j0, j1 + 1))
    r, l, n = req[sl], lo[sl], N[sl]
    ylo = int(l[r].min())
    yhi = int(n[r].max())
    Y = np.arange(ylo, yhi + 1)[:, None, None]
    cur = b.ids_box(j0, ylo, i0, j1, yhi, i1)
    nat, wat, full = _natural_ids(b)
    want = r[None] & (Y >= l[None]) & (Y <= n[None]) & ~full[cur]
    topm = want & (Y == n[None])
    ids = np.where(topm, np.broadcast_to(top[sl][None], want.shape), np.broadcast_to(sub[sl][None], want.shape))
    ids = np.where(want & (nat[cur] | wat[cur] | (cur <= 1)), ids, 0)
    b.put_ids(j0, ylo, i0, ids.astype(np.int32))
    del raised
    return N


def _register_water(st, mask, level):
    st["water"] = st["water"] | mask
    st["level"] = np.where(mask, level, st["level"])


# ============================================================================ planning
def _blend(hm, pad, target, *, max_slope=0.6, blend=None, rough=0.25, seed=0, mode="both"):
    """Float surface: `target` on the pad, smooth natural transition back to hm around it."""
    D, W = hm.shape
    h = hm.astype(np.float64)
    dist, (ni, nj) = _edt_idx(pad)
    E = target[ni, nj].astype(np.float64)
    Es = _gauss(E, 1.2)
    E = np.where(pad, target, Es)
    if blend is None:
        dlt = _gauss(np.abs(h - E), 2.0)
        Bc = np.clip(dlt / max(0.15, max_slope) * 1.25 + 2.0, 3.0, 48.0)
    else:
        Bc = np.full((D, W), max(1.0, float(blend)))
    ii, jj = np.mgrid[0:D, 0:W]
    Bc = Bc * (1.0 + rough * (_fbm2(jj, ii, 9.0, seed + 3) - 0.5) * 2.0)
    w = _sstep(dist / np.maximum(1.0, Bc))
    T = E + (h - E) * w
    T = np.where(pad, target, T)
    bd = _border_dist(D, W)
    lock = _sstep(bd / 3.0)
    T = np.where(pad, T, h + (T - h) * lock)
    zone = (~pad) & (dist < Bc + 1)
    for _ in range(24):  # relax corner artefacts inside the transition zone
        P = np.pad(T, 1, mode="edge")
        avg = (P[:-2, 1:-1] + P[2:, 1:-1] + P[1:-1, :-2] + P[1:-1, 2:]) * 0.25
        T = np.where(zone & (bd > 0), 0.5 * T + 0.5 * avg, T)
    if mode == "cut":
        T = np.minimum(T, h)
    elif mode == "fill":
        T = np.maximum(T, h)
    return T, zone


def _limit_steps(N, mod, max_step=1, iters=80, hm=None, mode="both"):
    N = N.copy()
    for _ in range(iters):
        hi = _nb4(N, 10 ** 6, np.minimum) + max_step
        lo = _nb4(N, -10 ** 6, np.maximum) - max_step
        new = np.where(mod, np.minimum(np.maximum(N, lo), hi), N)
        if hm is not None:
            if mode == "cut":
                new = np.minimum(new, hm)
            elif mode == "fill":
                new = np.maximum(new, hm)
        if (new == N).all():
            break
        N = new
    return N


def _plan_flatten(hm, P, y, *, blend=None, max_slope=0.6, mode="both", seed=0, rough=0.25):
    D, W = hm.shape
    tgt = np.full((D, W), float(y))
    if mode == "cut":
        tgt = np.minimum(tgt, hm)
    elif mode == "fill":
        tgt = np.maximum(tgt, hm)
    T, zone = _blend(hm, P, tgt, max_slope=max_slope, blend=blend, rough=rough, seed=seed, mode=mode)
    N = np.rint(T).astype(np.int64)
    N[P] = np.rint(tgt[P]).astype(np.int64)
    bd = _border_dist(D, W)
    mod = (~P) & (bd > 0) & _dil4(N != hm, 2)
    return _limit_steps(N, mod, 1, hm=hm, mode=mode)


# ============================================================================ public: flatten / cut / cost
def flatten(b, hm, pad, y=None, *, blend=None, max_slope=0.6, mode="both", material=None, surface=None, water=None,
            water_y=None, clear=2, seed=0, rough=0.25) -> np.ndarray:
    """Level a pad (top block at y) with natural blended edges. Returns the new heightmap."""
    hm = _hm(hm)
    D, W = hm.shape
    P = _pad_mask(pad, D, W)
    if mode not in ("both", "cut", "fill"):
        raise ValueError("mode: both | cut | fill")
    if y is None:
        y = int(round(float(np.median(hm[P]))))
    y = int(y)
    st = _state(b, hm, water, water_y)
    N = _plan_flatten(hm, P, y, blend=blend, max_slope=max_slope, mode=mode, seed=seed, rough=rough)
    N = _protect_water(N, hm, st, allow_fill=P)
    filled = st["water"] & P & (N >= st["level"])
    pal = _Pal(b)
    t, s, d = _layers(b, D, W, surface, None, N, seed)
    if material is not None and material != "keep":
        mt = np.where(P, material, t)
        t = mt
    _commit(b, hm, N, pal.grid(t), pal.grid(s), pal.grid(d), changed=P if material is not None else None,
            clear=clear, seed=seed)
    if filled.any():
        st["water"] = st["water"] & ~filled
        st["level"] = np.where(filled, NOLEVEL, st["level"])
    if st["water"].any():
        N = _seal(b, N, st["water"], st["level"], pal.grid(t), pal.grid(s))
    return N


def cut(b, hm, pad, y=None, **kw) -> np.ndarray:
    """Only lower the terrain inside the pad to y (terraces into slopes); blended like flatten."""
    kw["mode"] = "cut"
    return flatten(b, hm, pad, y, **kw)


def cost(hm, pad, y=None, *, blend=None, max_slope=0.6, mode="both", seed=0) -> dict:
    """Earthwork estimate for flatten(): blocks to cut / fill incl. the blended edge, and the cheapest pad y."""
    hm = _hm(hm)
    D, W = hm.shape
    P = _pad_mask(pad, D, W)
    hv = hm[P]
    cands = range(int(np.percentile(hv, 5)), int(np.percentile(hv, 95)) + 1)
    best_y, best = None, None
    for yy in cands:
        c = int(np.clip(hv - yy, 0, None).sum() + np.clip(yy - hv, 0, None).sum())
        if best is None or c < best:
            best_y, best = yy, c
    if y is None:
        y = best_y
    N = _plan_flatten(hm, P, int(y), blend=blend, max_slope=max_slope, mode=mode, seed=seed)
    d = N - hm
    return {"y": int(y), "best_y": int(best_y), "cut": int(np.clip(-d, 0, None).sum()),
            "fill": int(np.clip(d, 0, None).sum()), "total": int(np.abs(d).sum()),
            "pad_cut": int(np.clip(hv - y, 0, None).sum()), "pad_fill": int(np.clip(y - hv, 0, None).sum()),
            "area": int(P.sum()), "changed": int((d != 0).sum()), "max_cut": int(max(0, -d.min())),
            "max_fill": int(max(0, d.max()))}


# ============================================================================ smooth / hill
def smooth(b, hm, area=None, *, sigma=2.0, strength=1.0, feather=4, surface=None, water=None, water_y=None, clear=2,
           seed=0) -> np.ndarray:
    """Gaussian smoothing of the terrain inside `area` (soft feathered edge). Returns the new heightmap."""
    hm = _hm(hm)
    D, W = hm.shape
    A = _area_mask(area, D, W)
    st = _state(b, hm, water, water_y)
    Hs = _gauss(hm, sigma)
    din = _edt_idx(~A)[0] if (~A).any() else np.full((D, W), 1e9)
    w = np.where(A, _sstep(din / max(1.0, feather)), 0.0) * float(strength)
    w *= _sstep(_border_dist(D, W) / 3.0)
    N = np.rint(hm + (Hs - hm) * w).astype(np.int64)
    N = _protect_water(N, hm, st)
    pal = _Pal(b)
    t, s, d = _layers(b, D, W, surface, None, N, seed)
    _commit(b, hm, N, pal.grid(t), pal.grid(s), pal.grid(d), clear=clear, seed=seed)
    if st["water"].any():
        N = _seal(b, N, st["water"], st["level"], pal.grid(t), pal.grid(s))
    return N


def _blobmask(D, W, x, z, radius, rough, stretch, angle, seed):
    ii, jj = np.mgrid[0:D, 0:W]
    dx, dz = jj - float(x), ii - float(z)
    ca, sa = math.cos(angle), math.sin(angle)
    u = dx * ca + dz * sa
    v = -dx * sa + dz * ca
    r = np.sqrt((u / max(0.2, stretch)) ** 2 + v ** 2)
    th = np.arctan2(v, u)
    n = _vnoise2(np.cos(th) * 2.2 + 50.0, np.sin(th) * 2.2 + 50.0, 1.0, seed + 9)
    n2 = _fbm2(jj, ii, 6.0, seed + 10)
    R = radius * (1.0 + rough * ((n - 0.5) * 1.6 + (n2 - 0.5) * 0.8))
    return r, R


def hill(b, hm, x, z, radius, height, *, rough=0.3, stretch=1.0, angle=0.0, surface=None, water=None, water_y=None,
         clear=2, seed=0) -> np.ndarray:
    """Raise a natural hill (or dig a hollow with height < 0) centred on column (x, z)."""
    hm = _hm(hm)
    D, W = hm.shape
    st = _state(b, hm, water, water_y)
    r, R = _blobmask(D, W, x, z, radius, rough, stretch, angle, seed)
    t = r / np.maximum(0.5, R)
    prof = np.where(t < 1.0, (np.cos(np.pi * np.clip(t, 0, 1)) * 0.5 + 0.5) ** 1.25, 0.0)
    ii, jj = np.mgrid[0:D, 0:W]
    bumps = 0.14 * abs(height) * (_fbm2(jj, ii, 5.0, seed + 2) - 0.5) * 2.0 * np.sqrt(prof)
    dlt = height * prof + bumps * (1 if height > 0 else 0.5)
    dlt *= _sstep(_border_dist(D, W) / 3.0)
    N = np.rint(hm + dlt).astype(np.int64)
    N = _protect_water(N, hm, st)
    pal = _Pal(b)
    tt, s, d = _layers(b, D, W, surface, None, N, seed)
    _commit(b, hm, N, pal.grid(tt), pal.grid(s), pal.grid(d), clear=clear, seed=seed)
    if st["water"].any():
        N = _seal(b, N, st["water"], st["level"], pal.grid(tt), pal.grid(s))
    return N


# ============================================================================ water bodies
_BED = (("sand", 0.42), ("gravel", 0.22), ("clay", 0.16), ("dirt", 0.12), ("coarse_dirt", 0.08))
_RIVERBED = (("gravel", 0.42), ("sand", 0.26), ("clay", 0.14), ("dirt", 0.1), ("coarse_dirt", 0.08))


def _water_plants(b, mask, level, bottom, shore_land, N, seed, *, lily=0.05, grass=0.25, kelp=0.0, cane=0.25,
                  pickles=0.0):
    rng = random.Random(seed + 77)
    D, W = mask.shape
    dep = level - bottom
    wl = np.where(mask, level, NOLEVEL)
    din = _edt_idx(~mask)[0]
    for i, j in zip(*np.nonzero(mask)):
        x, z, bt, lv = int(j), int(i), int(bottom[i, j]), int(level[i, j])
        dp = lv - bt
        u = rng.random()
        if kelp and dp >= 4 and u < kelp:
            hgt = rng.randint(2, dp - 1)
            for k in range(1, hgt):
                b.set(x, bt + k, z, "kelp_plant")
            b.set(x, bt + hgt, z, f"kelp[age={rng.randint(15, 24)}]")
            continue
        if dp >= 3 and u < grass * 0.35:
            b.set(x, bt + 1, z, "tall_seagrass[half=lower]")
            b.set(x, bt + 2, z, "tall_seagrass[half=upper]")
        elif dp >= 2 and u < grass:
            b.set(x, bt + 1, z, "seagrass")
        elif pickles and u < grass + pickles:
            b.set(x, bt + 1, z, f"sea_pickle[pickles={rng.randint(1, 4)},waterlogged=true]")
        if lily and dp >= 2 and din[i, j] >= 2 and rng.random() < lily:
            if b.get_id(x, lv + 1, z) in (0, 1):
                b.set(x, lv + 1, z, "lily_pad")
    if cane:
        adj = _nb4(wl, NOLEVEL, np.maximum)
        cand = shore_land & (adj > NOLEVEL) & (N == adj)
        for i, j in zip(*np.nonzero(cand)):
            if rng.random() < cane:
                x, z, g = int(j), int(i), int(N[i, j])
                gname = _bname(b.get(x, g, z))
                if gname not in ("grass_block", "dirt", "sand", "red_sand", "coarse_dirt", "podzol", "mud", "moss_block",
                                 "keep"):
                    continue
                hgt = rng.randint(1, 3)
                for k in range(1, hgt + 1):
                    if b.get_id(x, g + k, z) not in (0, 1):
                        break
                    b.set(x, g + k, z, "sugar_cane")


def lake(b, hm, x, z, radius, *, depth=3, level=None, shore=3, rough=0.3, stretch=1.0, angle=0.0, plants=True,
         surface=None, water=None, water_y=None, max_slope=0.6, clear=2, seed=0) -> np.ndarray:
    """Natural lake centred on (x, z). Water stays inside the map and is fully enclosed. Returns the new heightmap."""
    hm = _hm(hm)
    D, W = hm.shape
    st = _state(b, hm, water, water_y)
    r, R = _blobmask(D, W, x, z, radius, rough, stretch, angle, seed)
    M = r <= R
    m = int(shore) + 2
    inner = np.zeros((D, W), bool)
    inner[m:D - m, m:W - m] = True
    M &= inner
    M &= ~_dil4(st["water"], 2)
    if M.sum() < 4:
        raise ValueError("lake does not fit: move it away from the map edge / existing water or make it larger")
    lab = _components(M)  # keep the component containing the centre (or the largest)
    vals, cnt = np.unique(lab[lab >= 0], return_counts=True)
    keep = vals[np.argmax(cnt)]
    if 0 <= int(z) < D and 0 <= int(x) < W and lab[int(z), int(x)] >= 0:
        keep = lab[int(z), int(x)]
    M = lab == keep
    dout, _ = _edt_idx(M)
    ring = (dout > 0) & (dout <= 2.5)
    if level is None:
        level = int(np.floor(np.percentile(hm[ring], 30))) - 1
    level = int(level)
    din = _edt_idx(~M)[0]
    Reff = math.sqrt(M.sum() / math.pi)
    ramp = max(1.5, min(Reff * 0.6, depth * 1.8))
    ii, jj = np.mgrid[0:D, 0:W]
    dep = 1.0 + (depth - 1.0) * _sstep((din - 1.0) / ramp) + (_fbm2(jj, ii, 4.0, seed + 4) - 0.5) * 1.2
    dep = np.clip(np.rint(dep), 1, max(1, depth + 1)).astype(np.int64)
    bottom = level - dep
    S = (dout > 0) & (dout <= shore)
    tgt = np.where(M, bottom, level + np.maximum(0.0, dout - 1.3) * 0.45).astype(np.float64)
    pad = M | S
    T, zone = _blend(hm, pad, tgt, max_slope=max_slope, rough=rough * 0.8, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[M] = bottom[M]
    adj = _dil4(M) & ~M
    N[adj] = np.maximum(N[adj], level)
    N = _limit_steps(N, (~pad) & zone, 1)
    N[adj] = np.maximum(N[adj], level)
    N = _protect_water(N, hm, st)
    pal = _Pal(b)
    t, s, d = _layers(b, D, W, surface, None, N, seed)
    u = _patchy(D, W, seed + 21, 4.0, 0.3)
    bed = _pick(_BED, u)
    t = np.where(M, bed, t)
    s = np.where(M, np.where(np.isin(bed, ["sand", "gravel"]), bed, "dirt"), s)
    psand = np.clip(1.35 - 0.42 * dout, 0, 1)
    shore_sand = S & (u < psand)
    t = np.where(shore_sand, np.where(u < psand * 0.15, "gravel", "sand"), t)
    s = np.where(shore_sand, "sand", s)
    tg, sg, dg = pal.grid(t), pal.grid(s), pal.grid(d)
    _commit(b, hm, N, tg, sg, dg, changed=M | S, clear=clear, seed=seed)
    lev = np.where(M, level, NOLEVEL)
    _put_water(b, M, lev, N)
    _register_water(st, M, level)
    N = _seal(b, N, st["water"], st["level"], tg, sg)
    if plants:
        _water_plants(b, M, lev, N, S, N, seed, lily=0.06, grass=0.22, cane=0.22)
    return N


def _resample(p, step=0.5):
    p = np.asarray(p, np.float64)
    seg = np.sqrt(((p[1:] - p[:-1]) ** 2).sum(1))
    s = np.r_[0.0, np.cumsum(seg)]
    L = float(s[-1])
    n = max(2, int(L / step) + 1)
    t = np.linspace(0.0, L, n)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1), t


def _chaikin(p, it=2):
    p = np.asarray(p, np.float64)
    for _ in range(it):
        if len(p) < 3:
            return p
        q = [p[0]]
        for a, c in zip(p[:-1], p[1:]):
            q.append(0.75 * a + 0.25 * c)
            q.append(0.25 * a + 0.75 * c)
        q.append(p[-1])
        p = np.array(q)
    return p


def _nearest(c, D, W, radius):
    """Distance from every cell (j, i) to the polyline samples c[:, (x, z)] (inf beyond radius) + nearest index."""
    dist = np.full((D, W), np.inf)
    kk = np.full((D, W), -1, np.int64)
    x0 = max(0, int(math.floor(c[:, 0].min() - radius - 1)))
    x1 = min(W - 1, int(math.ceil(c[:, 0].max() + radius + 1)))
    z0 = max(0, int(math.floor(c[:, 1].min() - radius - 1)))
    z1 = min(D - 1, int(math.ceil(c[:, 1].max() + radius + 1)))
    if x0 > x1 or z0 > z1:
        return dist, kk
    zz, xx = np.mgrid[z0:z1 + 1, x0:x1 + 1]
    cx = xx.ravel().astype(np.float64)
    cz = zz.ravel().astype(np.float64)
    coarse = c[::6]
    keep = np.zeros(len(cx), bool)
    ch = max(1, 2_000_000 // max(1, len(coarse)))
    for a in range(0, len(cx), ch):
        d2 = (cx[a:a + ch, None] - coarse[None, :, 0]) ** 2 + (cz[a:a + ch, None] - coarse[None, :, 1]) ** 2
        keep[a:a + ch] = d2.min(1) <= (radius + 3.5) ** 2
    cx, cz = cx[keep], cz[keep]
    if not len(cx):
        return dist, kk
    ch = max(1, 3_000_000 // max(1, len(c)))
    best = np.empty(len(cx))
    bk = np.empty(len(cx), np.int64)
    for a in range(0, len(cx), ch):
        d2 = (cx[a:a + ch, None] - c[None, :, 0]) ** 2 + (cz[a:a + ch, None] - c[None, :, 1]) ** 2
        k = d2.argmin(1)
        bk[a:a + ch] = k
        best[a:a + ch] = np.sqrt(d2[np.arange(len(k)), k])
    sel = best <= radius
    dist[cz[sel].astype(np.int64), cx[sel].astype(np.int64)] = best[sel]
    kk[cz[sel].astype(np.int64), cx[sel].astype(np.int64)] = bk[sel]
    return dist, kk


def river(b, hm, path, *, width=5, depth=2, meander=0.5, banks=3, plants=True, surface=None, water=None, water_y=None,
          max_slope=0.6, clear=2, seed=0) -> np.ndarray:
    """River along a polyline [(x, z), ...] with meanders, sloped banks and stone weirs between level steps.
    Ends are closed (inside the map); ending in existing water joins it at that water's level."""
    hm = _hm(hm)
    D, W = hm.shape
    pts = np.asarray(path, np.float64)
    if pts.ndim != 2 or len(pts) < 2 or pts.shape[1] != 2:
        raise ValueError("path must be a list of at least two (x, z) points")
    st = _state(b, hm, water, water_y)
    width = max(1.0, float(width))
    half0 = width / 2.0
    c, s = _resample(_chaikin(pts, 2), 0.5)
    rng = random.Random(_mix(seed, "river"))
    if meander > 0 and len(c) > 4:
        tng = np.gradient(c, axis=0)
        tng /= np.maximum(1e-9, np.linalg.norm(tng, axis=1, keepdims=True))
        nrm = np.stack([-tng[:, 1], tng[:, 0]], 1)
        lam = 7.0 * width + 14.0
        L = s[-1]
        phase = rng.uniform(0, 2 * math.pi)
        amp = meander * (0.8 * width + 2.0)
        off = amp * (np.sin(2 * math.pi * s / lam + phase) * 0.75 + (_vnoise2(s / (lam * 0.6), 7.0, 1.0, seed) - 0.5) * 1.2)
        taper = _sstep(np.minimum(s, L - s) / (lam * 0.35))
        c = c + nrm * (off * taper)[:, None]
        c, s = _resample(c, 0.5)
    margin = half0 + banks + 2.0
    ok = (c[:, 0] >= margin) & (c[:, 0] <= W - 1 - margin) & (c[:, 1] >= margin) & (c[:, 1] <= D - 1 - margin)
    if not ok.any():
        raise ValueError("river path lies too close to the map edge (keep width/2 + banks + 2 cells inside)")
    best, cur, bs, start = (0, 0), 0, 0, 0
    for i, v in enumerate(ok):  # longest inside run
        if v:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[1] - best[0]:
                best = (start, i + 1)
        else:
            cur = 0
    c, s = c[best[0]:best[1]], s[best[0]:best[1]] - s[best[0]]
    if len(c) < 3:
        raise ValueError("river path too short inside the map")
    nS = len(c)
    wv = width * (1.0 + 0.16 * (_vnoise2(s / 11.0, 3.0, 1.0, seed + 5) - 0.5) * 2.0)
    half = wv / 2.0
    dist, kk = _nearest(c, D, W, float(half.max()) + banks + 1.5)
    has = kk >= 0
    kc = np.where(has, kk, 0)
    hv = half[kc]
    C = has & (dist <= hv)
    if C.sum() < 3:
        raise ValueError("river channel is empty")
    # natural water level per sample: below the lower bank, smoothed, flowing downhill
    hs = np.zeros(nS)
    cnt = np.zeros(nS)
    bandc = has & (dist <= hv + 1.5)
    np.add.at(hs, kc[bandc], hm[bandc].astype(np.float64))
    np.add.at(cnt, kc[bandc], 1.0)
    hs = np.where(cnt > 0, hs / np.maximum(cnt, 1), np.nan)
    if np.isnan(hs).all():
        raise ValueError("river outside the map")
    idx = np.arange(nS)
    good = ~np.isnan(hs)
    hs = np.interp(idx, idx[good], hs[good])
    kw = max(1, int(width * 2))
    ker = np.ones(2 * kw + 1) / (2 * kw + 1)
    hsm = np.convolve(np.pad(hs, kw, mode="edge"), ker, mode="valid")
    Lnat = np.floor(np.minimum(hsm, hs + 0.5)).astype(np.int64) - 1
    q = max(2, nS // 4)
    rev = Lnat[:q].mean() < Lnat[-q:].mean()
    if rev:
        Lnat = Lnat[::-1]
    # joining existing water at the downstream end
    ex = st["water"]
    jl = None
    if ex.any():
        endk = 0 if rev else nS - 1
        near = has & _dil4(ex, 1) & (np.abs(kc - endk) <= kw * 3) & C
        if near.any():
            touch = _dil4(near, 1) & ex
            if touch.any():
                jl = int(st["level"][touch].max())
    L = np.minimum.accumulate(Lnat)
    if jl is not None:
        L = np.maximum(L, jl)
        L = np.minimum.accumulate(L)
        L[-max(2, kw * 2):] = jl
    min_run = max(16, int(6 * width))
    for _ in range(50):  # merge short runs into the next (lower) one
        changed = False
        runs = []
        a = 0
        for i in range(1, nS + 1):
            if i == nS or L[i] != L[a]:
                runs.append((a, i))
                a = i
        for (a, e) in runs[:-1]:
            if e - a < min_run:
                L[a:e] = L[e]
                changed = True
                break
        if not changed:
            break
    if rev:
        L = L[::-1]
    lev = np.where(C, L[kc], NOLEVEL)
    # weirs: channel cells next to lower channel water
    nbmin = _nb4(np.where(C, lev, 10 ** 6), 10 ** 6, np.minimum)
    weir = C & (nbmin < lev)
    Wt = C & ~weir
    if jl is not None:
        Wt &= ~ex
    latf = np.clip(dist / np.maximum(0.5, hv), 0, 1)
    ii, jj = np.mgrid[0:D, 0:W]
    dpt = 1.0 + (depth - 1.0) * (1.0 - latf ** 2) ** 0.8 + (_fbm2(jj, ii, 3.0, seed + 6) - 0.5) * 0.9
    dpt = np.clip(np.rint(dpt), 1, depth + 1).astype(np.int64)
    bottom = lev - dpt
    Bk = has & ~C & (dist <= hv + banks)
    btgt = L[kc] + 1.0 + np.maximum(0.0, dist - hv - 1.0) * 0.35
    tgt = np.where(Wt, bottom, np.where(weir, lev, btgt)).astype(np.float64)
    pad = C | Bk
    if jl is not None:
        pad &= ~ex
    T, zone = _blend(hm, pad, tgt, max_slope=max_slope, rough=0.2, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[Wt] = bottom[Wt]
    N[weir] = lev[weir]
    wl = np.where(Wt, lev, NOLEVEL)
    need = _nb4(wl, NOLEVEL, np.maximum)
    land = ~Wt
    N[land] = np.maximum(N[land], need[land])
    N = _limit_steps(N, (~pad) & zone, 1)
    N[land] = np.maximum(N[land], need[land])
    N = _protect_water(N, hm, st)
    pal = _Pal(b)
    t, s_, d = _layers(b, D, W, surface, None, N, seed)
    u = _patchy(D, W, seed + 31, 3.5, 0.35)
    bed = _pick(_RIVERBED, u)
    t = np.where(Wt, bed, t)
    s_ = np.where(Wt, np.where(np.isin(bed, ["sand", "gravel"]), bed, "dirt"), s_)
    rock = _pick((("mossy_cobblestone", 0.4), ("cobblestone", 0.3), ("stone", 0.2), ("andesite", 0.1)), u)
    t = np.where(weir, rock, t)
    s_ = np.where(weir, rock, s_)
    nearbank = Bk & (dist - hv <= 1.6)
    bmat = _pick((("grass_block", 0.42), ("gravel", 0.18), ("sand", 0.14), ("coarse_dirt", 0.12), ("mud", 0.14)),
                 _patchy(D, W, seed + 33, 2.5, 0.4))
    t = np.where(nearbank, bmat, t)
    s_ = np.where(nearbank & np.isin(bmat, ["sand", "gravel"]), bmat, s_)
    tg, sg, dg = pal.grid(t), pal.grid(s_), pal.grid(d)
    _commit(b, hm, N, tg, sg, dg, changed=pad, clear=clear, seed=seed)
    levw = np.where(Wt, lev, NOLEVEL)
    _put_water(b, Wt, levw, N)
    _register_water(st, Wt, levw)
    N = _seal(b, N, st["water"], st["level"], tg, sg)
    if plants:
        _water_plants(b, Wt, levw, N, Bk, N, seed + 1, lily=0.015, grass=0.18, cane=0.12)
    return N


def waterfall(b, hm, x, z, direction="south", *, height=None, width=2, pool=4, basin=3, rough=0.25, plants=True,
              surface=None, water=None, water_y=None, clear=2, seed=0) -> np.ndarray:
    """Waterfall: lip cell (x, z) of an upper basin, water falls toward `direction` into a plunge pool.
    Builds the rock cliff when the ground is not steep enough. Returns the new heightmap."""
    hm = _hm(hm)
    D, W = hm.shape
    if direction not in _DIR:
        raise ValueError("direction: north | south | east | west")
    st = _state(b, hm, water, water_y)
    dx, dz = _DIR[direction]
    px, pz = -dz, dx
    ii, jj = np.mgrid[0:D, 0:W]
    u = (jj - int(x)) * dx + (ii - int(z)) * dz
    v = (jj - int(x)) * px + (ii - int(z)) * pz
    width = max(1, int(width))
    vlo, vhi = -((width - 1) // 2), width // 2
    pool = max(2, int(pool))
    basin = max(2, int(basin))
    n1 = _fbm2(jj, ii, 5.0, seed + 41)
    # regions
    lip = (u == 0) & (v >= vlo) & (v <= vhi)
    ub = np.sqrt((u + basin + 0.5) ** 2 + (v - (vlo + vhi) / 2.0) ** 2) <= basin * (1.0 + rough * (n1 - 0.5) * 2)
    chan = (u <= 0) & (u >= -basin) & (v >= vlo) & (v <= vhi)
    U = (ub | chan) & (u <= 0) & ~lip
    pc = 1.0 + pool * 0.6
    P = np.sqrt((u - pc) ** 2 + (v - (vlo + vhi) / 2.0) ** 2 * 1.1) <= pool * (1.0 + rough * (n1 - 0.5) * 2)
    P |= (u >= 1) & (u <= 2) & (v >= vlo - 1) & (v <= vhi + 1)
    P &= u >= 1
    Rp = basin * 2 + width + 3
    plateau = (u <= 0) & (np.sqrt(np.maximum(0, -u) ** 2 * 0.6 + v.astype(np.float64) ** 2) <= Rp * (1 + 0.2 * (n1 - 0.5)))
    margin = 2
    inner = np.zeros((D, W), bool)
    inner[margin:D - margin, margin:W - margin] = True
    if not (inner[lip].all() and (P & inner).sum() >= 4):
        raise ValueError("waterfall does not fit inside the map here (move it inward)")
    P &= inner
    U &= inner
    plateau &= inner
    if (P & _dil4(st["water"], 1)).any() or ((U | lip) & _dil4(st["water"], 1)).any():
        raise ValueError("waterfall overlaps existing water")
    glow = int(np.median(hm[P]))
    ghigh = int(np.median(hm[U | lip])) if (U | lip).any() else glow
    Lp = glow - 1
    if height is None:
        Lt = max(ghigh - 1, Lp + 5)
    else:
        Lt = Lp + max(3, int(height))
    # targets
    pdist = _edt_idx(~P)[0]
    pdep = np.clip(np.rint(1 + 2.2 * _sstep((pdist - 1) / 2.0) + (n1 - 0.5)), 1, 4).astype(np.int64)
    pdep = np.where((u == 1) & (v >= vlo) & (v <= vhi), np.maximum(pdep, 3), pdep)
    udist = _edt_idx(~U)[0]
    udep = np.clip(np.rint(1 + 1.5 * _sstep((udist - 1) / 2.0)), 1, 3).astype(np.int64)
    pshore = (~P) & (_edt_idx(P)[0] <= 3) & (u >= 1)
    tgt = np.full((D, W), np.nan)
    tgt[plateau] = Lt + 1
    tgt[U] = Lt - udep[U]
    tgt[lip] = Lt - 1
    tgt[P] = Lp - pdep[P]
    dps = _edt_idx(P)[0]
    tgt[pshore] = Lp + 1 + np.maximum(0.0, dps[pshore] - 1.0) * 0.4
    pad = ~np.isnan(tgt)
    tgt = np.where(pad, tgt, 0.0)
    T, zone = _blend(hm, pad, tgt, max_slope=0.8, rough=rough, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[pad] = np.rint(tgt[pad]).astype(np.int64)
    N = _limit_steps(N, (~pad) & zone, 1)
    N = _protect_water(N, hm, st)
    waterm = U | lip | P
    levm = np.where(U | lip, Lt, np.where(P, Lp, NOLEVEL))
    need = _nb4(np.where(waterm, levm, NOLEVEL), NOLEVEL, np.maximum)
    landm = ~waterm
    # the column in front of the lip is open on purpose (pool), everything else is a bank
    N[landm] = np.maximum(N[landm], need[landm])
    pal = _Pal(b)
    t, s_, d = _layers(b, D, W, surface, None, N, seed)
    uu = _patchy(D, W, seed + 51, 2.5, 0.45)
    rock = _pick(_ROCK, uu)
    face = plateau & (u >= -2) & (np.abs(v - (vlo + vhi) / 2.0) <= Rp)
    face |= lip | (U & (u >= -1))
    s_ = np.where(face, rock, s_)
    d = np.where(face, rock, d)
    t = np.where(face & ~lip & (uu < 0.35), "mossy_cobblestone", t)
    t = np.where(lip, "mossy_cobblestone", t)
    bed = _pick(_BED, uu)
    t = np.where(U | P, bed, t)
    t = np.where(pshore & (uu < 0.5), "gravel", t)
    s_ = np.where(U | P, np.where(np.isin(bed, ["sand", "gravel"]), bed, "dirt"), s_)
    flo = np.full((D, W), 10 ** 6, np.int64)
    flo[face] = Lp - 4
    tg, sg, dg = pal.grid(t), pal.grid(s_), pal.grid(d)
    _commit(b, hm, N, tg, sg, dg, changed=pad, clear=clear, seed=seed, force_lo=np.where(face, flo, N))
    _put_water(b, U | lip, np.where(U | lip, Lt, NOLEVEL), N)
    _put_water(b, P, np.where(P, Lp, NOLEVEL), N)
    _register_water(st, U | lip, Lt)
    _register_water(st, P, Lp)
    N = _seal(b, N, st["water"], st["level"], tg, sg)
    # falling water in front of the lip (intended flow, recorded as outlets)
    outs = st["outlets"]
    for i, j in zip(*np.nonzero(lip)):
        fx, fz = int(j) + dx, int(i) + dz
        outs.add((int(j), Lt, int(i)))
        b.set(fx, Lt, fz, "water[level=1]")
        outs.add((fx, Lt, fz))
        for yy in range(Lp + 1, Lt):
            b.set(fx, yy, fz, "water[level=8]")
            outs.add((fx, yy, fz))
    if plants:
        _water_plants(b, P, np.where(P, Lp, NOLEVEL), N, pshore, N, seed + 3, lily=0.08, grass=0.2, cane=0.0)
        rng = random.Random(seed + 9)
        for i, j in zip(*np.nonzero(face & (u == 0) & ~lip)):  # vines down the cliff face
            fx, fz = int(j) + dx, int(i) + dz
            if 0 <= fz < D and 0 <= fx < W and N[fz, fx] < N[i, j] - 2 and rng.random() < 0.3:
                facen = {(-1, 0): "east", (1, 0): "west", (0, -1): "south", (0, 1): "north"}[(dx, dz)]
                facen = {"east": "west", "west": "east", "south": "north", "north": "south"}[facen]
                top = int(N[i, j])
                for k in range(rng.randint(2, max(2, top - int(N[fz, fx]) - 1))):
                    yy = top - k
                    if yy <= N[fz, fx] + 1 or b.get_id(fx, yy, fz) not in (0, 1):
                        break
                    b.set(fx, yy, fz, f"vine[{facen}=true]")
    return N


def coast(b, hm, side="south", *, width=None, level=None, beach=6, depth=6, rough=0.35, open_edge=False, plants=True,
          surface=None, water=None, water_y=None, max_slope=0.6, clear=2, seed=0) -> np.ndarray:
    """Sea along one side of the map with a sandy beach and dunes. Sealed by a natural sandbar/reef rim on the map
    edge unless open_edge=True (only when the world beyond is sea at the same level)."""
    hm = _hm(hm)
    D, W = hm.shape
    if side not in _DIR:
        raise ValueError("side: north | south | east | west")
    st = _state(b, hm, water, water_y)
    ii, jj = np.mgrid[0:D, 0:W]
    if side == "south":
        u, v, n_along = (D - 1 - ii), jj, W
    elif side == "north":
        u, v, n_along = ii, jj, W
    elif side == "east":
        u, v, n_along = (W - 1 - jj), ii, D
    else:
        u, v, n_along = jj, ii, D
    across = D if side in ("north", "south") else W
    if width is None:
        width = max(6, across // 3)
    sv = width * (1.0 + rough * (_fbm2(v.astype(np.float64), 0.0 * v, 14.0, seed + 61, 2) - 0.5) * 2.0)
    sv = np.clip(sv, 3, across - beach - 4)
    S = u < sv
    rim = np.zeros((D, W), bool)
    if not open_edge:
        rim = S & ((u == 0) | (v == 0) | (v == n_along - 1))
    Sw = S & ~rim
    if not open_edge:
        Sw &= (u >= 1) & (v >= 1) & (v <= n_along - 2)
    Sw &= ~_dil4(st["water"], 1)
    if Sw.sum() < 4:
        raise ValueError("coast: no room for the sea")
    shore_band = (np.abs(u - sv) <= 2.5)
    if level is None:
        level = int(np.floor(np.percentile(hm[shore_band], 25))) - 1
    level = int(level)
    dsea = sv - u
    dp = np.clip(np.rint(1.0 + dsea * 0.42 + (_fbm2(jj, ii, 5.0, seed + 62) - 0.5) * 1.5), 1, depth).astype(np.int64)
    if not open_edge:  # shallow slope up to the sandbar rim
        drim = _edt_idx(rim)[0] if rim.any() else np.full((D, W), 1e9)
        dp = np.minimum(dp, np.maximum(1, np.rint(drim * 0.9)).astype(np.int64))
    bottom = level - dp
    dl = u - sv
    B = (~S) & (dl < beach)
    dune = (_fbm2(jj, ii, 4.0, seed + 63) - 0.4) * 1.6 * _sstep((dl - beach * 0.45) / (beach * 0.5))
    btgt = level + np.maximum(0.0, dl) * 0.32 + np.maximum(0.0, dune)
    tgt = np.where(Sw, bottom, np.where(rim, level + ((_hash(seed + 64, jj, ii) < 0.25) * 1.0), btgt)).astype(np.float64)
    pad = S | B
    T, zone = _blend(hm, pad, tgt, max_slope=max_slope, rough=0.2, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[Sw] = bottom[Sw]
    N[rim] = np.rint(tgt[rim]).astype(np.int64)
    wl = np.where(Sw, level, NOLEVEL)
    need = _nb4(wl, NOLEVEL, np.maximum)
    land = ~Sw
    N[land] = np.maximum(N[land], need[land])
    N = _limit_steps(N, (~pad) & zone, 1)
    N[land] = np.maximum(N[land], need[land])
    N = _protect_water(N, hm, st)
    pal = _Pal(b)
    t, s_, d = _layers(b, D, W, surface, None, N, seed)
    uu = _patchy(D, W, seed + 65, 4.0, 0.3)
    seab = _pick((("sand", 0.62), ("gravel", 0.16), ("clay", 0.1), ("sand", 0.12)), uu)
    t = np.where(Sw, seab, t)
    s_ = np.where(Sw, np.where(seab == "clay", "clay", "sand"), s_)
    d = np.where(Sw | B, "sandstone", d)
    bsand = B & (uu < np.clip(1.5 - dl / max(1.0, beach) * 0.9, 0, 1))
    t = np.where(bsand, "sand", t)
    s_ = np.where(bsand | B, "sand", s_)
    rimm = _pick((("sand", 0.45), ("gravel", 0.25), ("stone", 0.15), ("andesite", 0.1), ("mossy_cobblestone", 0.05)), uu)
    t = np.where(rim, rimm, t)
    s_ = np.where(rim, np.where(np.isin(rimm, ["sand", "gravel"]), rimm, "stone"), s_)
    tg, sg, dg = pal.grid(t), pal.grid(s_), pal.grid(d)
    _commit(b, hm, N, tg, sg, dg, changed=pad, clear=clear, seed=seed)
    lev = np.where(Sw, level, NOLEVEL)
    _put_water(b, Sw, lev, N)
    _register_water(st, Sw, level)
    if open_edge:
        st["open_edge"] = True
        N2 = N
        inner = Sw.copy()
        inner[0, :] = inner[-1, :] = inner[:, 0] = inner[:, -1] = False
        tmp = st["water"] & ~(Sw & ~inner)
        N2 = _seal_inner(b, N2, tmp, st["level"], tg, sg)
        N = N2
    else:
        N = _seal(b, N, st["water"], st["level"], tg, sg)
    if plants:
        _water_plants(b, Sw, lev, N, B, N, seed + 4, lily=0.0, grass=0.2, kelp=0.12, cane=0.08, pickles=0.02)
        rng = random.Random(seed + 66)
        for i, j in zip(*np.nonzero(B & (dl > beach * 0.35))):
            x_, z_, g = int(j), int(i), int(N[i, j])
            if _bname(b.get(x_, g, z_)) == "sand" and b.get_id(x_, g + 1, z_) in (0, 1):
                r = rng.random()
                if r < 0.05:
                    b.set(x_, g + 1, z_, "short_dry_grass")
                elif r < 0.07:
                    b.set(x_, g + 1, z_, "tall_dry_grass")
                elif r < 0.075:
                    b.set(x_, g + 1, z_, "dead_bush")
    return N


def _seal_inner(b, N, wmask, level, top, sub):
    """_seal variant that tolerates water on the map border (open_edge coasts)."""
    D, W = N.shape
    m = wmask.copy()
    m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = False
    return _seal(b, N, m, level, top, sub) if m.any() else N


def beach(b, hm, *, width=5, level=None, water=None, water_y=None, surface=None, clear=2, seed=0) -> np.ndarray:
    """Turn the land along existing water into a sandy beach with a shallow sandy shelf (never adds water)."""
    hm = _hm(hm)
    D, W = hm.shape
    st = _state(b, hm, water, water_y if level is None else level)
    wm = st["water"]
    if not wm.any():
        raise ValueError("beach: no water known (pass water=mask or create a lake/river/coast first)")
    dout, (ni, nj) = _edt_idx(wm)
    lvn = st["level"][ni, nj]
    S = (~wm) & (dout <= width)
    tgt = (lvn + np.maximum(0.0, dout - 1.0) * 0.4).astype(np.float64)
    T, zone = _blend(hm, S, tgt, max_slope=0.6, rough=0.2, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[S] = np.maximum(np.rint(tgt[S]).astype(np.int64), lvn[S])
    din, (li, lj) = _edt_idx(~wm)
    shelf = wm & (din <= 3)
    lv = st["level"]
    sh = np.rint(lv - (0.6 + din * 0.75)).astype(np.int64)
    N[shelf] = np.maximum(hm[shelf], np.minimum(sh[shelf], lv[shelf] - 1))
    N[wm & ~shelf] = hm[wm & ~shelf]
    need = _nb4(np.where(wm, lv, NOLEVEL), NOLEVEL, np.maximum)
    N[~wm] = np.maximum(N[~wm], need[~wm])
    N = _limit_steps(N, (~S) & (~wm) & zone, 1)
    N[~wm] = np.maximum(N[~wm], need[~wm])
    pal = _Pal(b)
    t, s_, d = _layers(b, D, W, surface, None, N, seed)
    uu = _patchy(D, W, seed + 71, 3.0, 0.4)
    sandy = (S & (uu < np.clip(1.4 - dout / max(1.0, width) * 0.8, 0, 1))) | shelf
    t = np.where(sandy, np.where(uu < 0.08, "gravel", "sand"), t)
    s_ = np.where(sandy, "sand", s_)
    d = np.where(sandy, "sandstone", d)
    tg, sg, dg = pal.grid(t), pal.grid(s_), pal.grid(d)
    _commit(b, hm, N, tg, sg, dg, changed=S | shelf, clear=np.where(wm, 0, clear), seed=seed)
    N = _seal(b, N, wm, lv, tg, sg)
    return N


# ============================================================================ roads
ROAD_STYLES = {
    "mixed": dict(top=(("dirt_path", 0.56), ("coarse_dirt", 0.14), ("gravel", 0.18), ("cobblestone", 0.07),
                       ("mossy_cobblestone", 0.05)),
                  firm=(("gravel", 0.4), ("coarse_dirt", 0.35), ("cobblestone", 0.25)),
                  slab=(("cobblestone_slab", 0.6), ("mossy_cobblestone_slab", 0.4)),
                  stairs=(("cobblestone_stairs", 0.6), ("mossy_cobblestone_stairs", 0.4)),
                  edge=(("coarse_dirt", 0.35), ("gravel", 0.15), (None, 0.5))),
    "path": dict(top=(("dirt_path", 0.82), ("coarse_dirt", 0.12), ("gravel", 0.06)),
                 firm=(("coarse_dirt", 0.7), ("gravel", 0.3)),
                 slab=(("spruce_slab", 1.0),), stairs=(("spruce_stairs", 1.0),),
                 edge=(("coarse_dirt", 0.2), (None, 0.8))),
    "gravel": dict(top=(("gravel", 0.7), ("coarse_dirt", 0.12), ("cobblestone", 0.08), ("andesite", 0.1)),
                   firm=(("gravel", 0.6), ("andesite", 0.4)),
                   slab=(("andesite_slab", 0.5), ("cobblestone_slab", 0.5)),
                   stairs=(("andesite_stairs", 0.5), ("cobblestone_stairs", 0.5)),
                   edge=(("coarse_dirt", 0.3), ("gravel", 0.2), (None, 0.5))),
    "cobble": dict(top=(("cobblestone", 0.45), ("mossy_cobblestone", 0.2), ("andesite", 0.12), ("gravel", 0.08),
                        ("stone", 0.15)),
                   firm=(("cobblestone", 0.6), ("mossy_cobblestone", 0.4)),
                   slab=(("cobblestone_slab", 0.5), ("mossy_cobblestone_slab", 0.3), ("stone_slab", 0.2)),
                   stairs=(("cobblestone_stairs", 0.6), ("mossy_cobblestone_stairs", 0.25), ("stone_stairs", 0.15)),
                   edge=(("gravel", 0.25), ("coarse_dirt", 0.2), (None, 0.55))),
    "stone": dict(top=(("stone_bricks", 0.55), ("mossy_stone_bricks", 0.2), ("cracked_stone_bricks", 0.15),
                       ("andesite", 0.1)),
                  firm=(("stone_bricks", 0.7), ("mossy_stone_bricks", 0.3)),
                  slab=(("stone_brick_slab", 0.7), ("mossy_stone_brick_slab", 0.3)),
                  stairs=(("stone_brick_stairs", 0.7), ("mossy_stone_brick_stairs", 0.3)),
                  edge=(("gravel", 0.3), ("cobblestone", 0.15), (None, 0.55))),
}


def road(b, hm, path, *, width=3, style="mixed", max_grade=0.5, bridge=True, clearance=3, lights=False, edge=True,
         surface=None, water=None, water_y=None, seed=0) -> np.ndarray:
    """Road/path along a polyline [(x, z), ...] that follows the terrain with a gentle grade (max_grade blocks of
    rise per block), cut/fill with blended shoulders, slabs for half steps, stairs where steeper, and plank bridges
    over water (bridge=False: the road stops at the water, spans are still recorded)."""
    hm = _hm(hm)
    D, W = hm.shape
    if style not in ROAD_STYLES:
        raise ValueError(f"style: {', '.join(ROAD_STYLES)}")
    pts = np.asarray(path, np.float64)
    if pts.ndim != 2 or len(pts) < 2 or pts.shape[1] != 2:
        raise ValueError("path must be a list of at least two (x, z) points")
    st = _state(b, hm, water, water_y)
    S = ROAD_STYLES[style]
    width = max(1.0, float(width))
    hw = width / 2.0
    c, s = _resample(_chaikin(pts, 2), 0.5)
    nS = len(c)
    dist, kk = _nearest(c, D, W, hw + 2.5)
    has = kk >= 0
    kc = np.where(has, kk, 0)
    R = has & (dist <= hw + 0.05)
    if not R.any():
        raise ValueError("road lies outside the heightmap")
    wm = st["water"]
    lv = st["level"]
    # terrain + water per sample
    hs = np.zeros(nS)
    cnt = np.zeros(nS)
    land = R & ~wm
    np.add.at(hs, kc[land], hm[land].astype(np.float64))
    np.add.at(cnt, kc[land], 1.0)
    over = np.zeros(nS, bool)
    wlev = np.full(nS, float(NOLEVEL))
    wr = R & wm
    if wr.any():
        over[np.unique(kc[wr])] = True
        np.maximum.at(wlev, kc[wr], lv[wr].astype(np.float64))
    idx = np.arange(nS)
    good = cnt > 0
    if not good.any():
        hs = np.full(nS, float(np.max(lv[wr])) + 2)
    else:
        hs = np.interp(idx, idx[good], hs[good] / np.maximum(cnt[good], 1))
    kw = 5
    ker = np.ones(2 * kw + 1) / (2 * kw + 1)
    p = np.convolve(np.pad(hs, kw, mode="edge"), ker, mode="valid")
    p = 0.5 * p + 0.5 * hs
    g = max(0.05, float(max_grade)) * 0.5
    lb = np.where(over, wlev + 2.0, -1e9)
    for i in range(1, nS):
        lb[i] = max(lb[i], lb[i - 1] - g)
    for i in range(nS - 2, -1, -1):
        lb[i] = max(lb[i], lb[i + 1] - g)
    p = np.maximum(p, lb)
    for _ in range(3):
        for i in range(1, nS):
            p[i] = min(max(p[i], p[i - 1] - g), p[i - 1] + g)
        for i in range(nS - 2, -1, -1):
            p[i] = min(max(p[i], p[i + 1] - g), p[i + 1] + g)
        p = np.maximum(p, lb)
    H = p[kc]
    Hq = np.round(H * 2.0) / 2.0
    full = np.floor(Hq).astype(np.int64)
    half = (Hq - full) >= 0.5
    deck = R & wm
    landR = R & ~wm
    # terrain with blended shoulders
    tgt = np.where(landR, full, 0).astype(np.float64)
    T, zone = _blend(hm, landR, tgt, max_slope=0.75, rough=0.15, seed=seed)
    N = np.rint(T).astype(np.int64)
    N[landR] = full[landR]
    N = _limit_steps(N, (~landR) & zone & ~wm, 1)
    N = _protect_water(N, hm, st)
    N[landR] = np.maximum(N[landR], full[landR])
    pal = _Pal(b)
    t, s_, d = _layers(b, D, W, surface, None, N, seed)
    u = _patchy(D, W, seed + 81, 2.2, 0.45)
    topn = _pick(S["top"], u)
    firm = _pick(S["firm"], u)
    # stairs where the road climbs a full block between neighbours along the road without a half step
    tng = np.gradient(c, axis=0)
    tx, tz = tng[:, 0][kc], tng[:, 1][kc]
    ax_x = np.abs(tx) >= np.abs(tz)
    sx = np.where(ax_x, np.sign(tx), 0).astype(np.int64)
    sz = np.where(ax_x, 0, np.sign(tz)).astype(np.int64)
    stair = np.zeros((D, W), bool)
    sface = np.full((D, W), "", dtype=object)
    ii, jj = np.nonzero(landR & ~half)
    for i, j in zip(ii, jj):
        for sgn in (1, -1):
            ni_, nj_ = i + sgn * sz[i, j], j + sgn * sx[i, j]
            if 0 <= ni_ < D and 0 <= nj_ < W and landR[ni_, nj_] and full[ni_, nj_] >= full[i, j] + 1:
                stair[i, j] = True
                dxs, dzs = nj_ - j, ni_ - i
                sface[i, j] = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}.get((dxs, dzs), "")
                break
    stair &= sface != ""
    covered = (half | stair) & landR
    rt = np.where(covered, firm, topn)
    if edge:
        en = _pick(S["edge"], _patchy(D, W, seed + 82, 2.0, 0.5))
        rim = (~R) & has & (dist <= hw + 1.0) & ~wm & (en != None)  # noqa: E711
        t = np.where(rim & (np.abs(N - full) <= 0), en, t)
    t = np.where(landR, rt, t)
    s_ = np.where(landR & np.isin(rt, ["gravel"]), "gravel", s_)
    tg, sg, dg = pal.grid(t), pal.grid(s_), pal.grid(d)
    clr = np.where(landR, clearance, 2)
    shoulder = has & (dist <= hw + 1.0) & ~wm if edge else np.zeros((D, W), bool)
    _commit(b, hm, N, tg, sg, dg, changed=landR | shoulder, clear=clr, seed=seed)
    slabn = _pick(S["slab"], u)
    stn = _pick(S["stairs"], u)
    for i, j in zip(*np.nonzero(landR & half)):
        b.set(int(j), int(full[i, j]) + 1, int(i), f"{slabn[i, j]}[type=bottom]")
    for i, j in zip(*np.nonzero(landR & stair)):
        b.set(int(j), int(full[i, j]) + 1, int(i), f"{stn[i, j]}[facing={sface[i, j]},half=bottom]")
    # bridges
    spans = []
    if over.any():
        runs = []
        a = None
        for k in range(nS + 1):
            o = k < nS and over[k]
            if o and a is None:
                a = k
            elif not o and a is not None:
                runs.append((a, k - 1))
                a = None
        for (a, e) in runs:
            ks = np.arange(max(0, a - 2), min(nS, e + 3))
            info = {"start": [float(c[a][0]), float(c[a][1])], "end": [float(c[e][0]), float(c[e][1])],
                    "deck_y": int(np.floor(p[a:e + 1].max())), "length": round((e - a) * 0.5, 1),
                    "water_level": int(wlev[a:e + 1].max()), "built": bool(bridge)}
            spans.append(info)
            if not bridge:
                continue
            dmask = has & np.isin(kc, ks) & (dist <= hw + 1.05) & wm
            rail = dmask & (dist > hw + 0.05)
            for i, j in zip(*np.nonzero(dmask)):
                yd = int(full[i, j])
                x_, z_ = int(j), int(i)
                b.set(x_, yd, z_, "spruce_planks")
                if half[i, j] and not rail[i, j]:
                    b.set(x_, yd + 1, z_, "spruce_slab[type=bottom]")
                if rail[i, j]:
                    b.set(x_, yd + 1, z_, "spruce_fence")
                    if int(kc[i, j]) % 8 == 0:
                        bot = int(N[i, j])
                        for yy in range(bot + 1, yd):
                            b.set(x_, yy, z_, "stripped_spruce_log[axis=y]")
                        if lights:
                            b.set(x_, yd + 2, z_, "lantern[hanging=false]")
                for yy in range(yd + 1 + (1 if rail[i, j] else 0), yd + clearance + 1):
                    if b.get_id(x_, yy, z_) == 0:
                        b.set(x_, yy, z_, "air")
    st["bridges"].extend(spans)
    st["road"] = st["road"] | R | (has & (dist <= hw + 1.05) & wm)
    if lights and landR.any():  # lanterns on fence posts along the road edge
        rng = random.Random(seed + 91)
        side = (~R) & has & (dist > hw + 0.5) & (dist <= hw + 1.5) & ~wm
        for i, j in zip(*np.nonzero(side & (kc % 24 == 0))):
            x_, z_, gg = int(j), int(i), int(N[i, j])
            if b.get_id(x_, gg + 1, z_) in (0, 1) and rng.random() < 0.5:
                b.set(x_, gg + 1, z_, "spruce_fence")
                b.set(x_, gg + 2, z_, "lantern[hanging=false]")
    if wm.any():
        N = _seal(b, N, wm, lv, tg, sg)
    return N


# ============================================================================ forest + checks
def forest(b, hm, area=None, density=0.5, species_mix="oak", seed=0, **kw) -> np.ndarray:
    """trees.forest() on this heightmap; avoids registered water and roads. Returns hm (unchanged)."""
    hm = _hm(hm)
    st = _state(b, hm, kw.pop("water", None), kw.pop("water_y", None))
    avoid = kw.pop("avoid", None)
    av = st["road"].copy()
    if avoid is not None:
        av |= np.asarray(avoid, bool)
    placed = _trees.forest(b, hm, area=area, density=density, species_mix=species_mix, seed=seed,
                           water=st["water"] if st["water"].any() else None, avoid=av if av.any() else None, **kw)
    st["trees"].extend(placed)
    return hm


def leaks(b, outlets=True) -> list:
    """Water cells with an open side or floor (air, keep/unknown or a replaceable plant). Intended waterfall flow
    cells recorded in meta["terrain"]["outlets"] are ignored when outlets=True."""
    db = b.db
    (ox, oy, oz), ids = b.dense()
    n = len(b.palette)
    isw = np.zeros(n, bool)
    seal = np.zeros(n, bool)
    for i in range(2, n):
        st = b.palette[i].lstrip("!")
        try:
            f = db.flags_of(st)
        except Exception:
            continue
        name = _bname(st)
        if name == "water" or (f & blockdb.FLUID) or "waterlogged=true" in st:
            isw[i] = True
        elif (f & blockdb.FULL) or not (f & (blockdb.AIR | blockdb.REPLACEABLE | blockdb.PLANT)):
            seal[i] = True
    Wm = isw[ids]
    if not Wm.any():
        return []
    ok = np.pad(seal[ids] | Wm, 1, constant_values=False)
    out = []
    allow = (b.meta.get("terrain") or {}).get("outlets", set()) if outlets else set()
    Y, Z, X = Wm.shape
    checks = (("down", (0, 1, 1), (-1, 0, 0)), ("north", (1, 0, 1), (0, -1, 0)), ("south", (1, 2, 1), (0, 1, 0)),
              ("west", (1, 1, 0), (0, 0, -1)), ("east", (1, 1, 2), (0, 0, 1)))
    for name, (a, c_, e), _d in checks:
        nb = ok[a:a + Y, c_:c_ + Z, e:e + X]
        bad = Wm & ~nb
        for y, z, x in zip(*np.nonzero(bad)):
            p = (int(x) + ox, int(y) + oy, int(z) + oz)
            if p in allow:
                continue
            out.append(p + (name,))
    return out
