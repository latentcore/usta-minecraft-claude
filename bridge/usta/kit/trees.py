"""Natural tree generators (large, varied, deterministic by seed) for the Usta kit.

Local Build frame (y up). (x, y, z) = the GROUND block under the trunk; the trunk starts at y+1
(for 2x2 trunks (x, z) is the -x/-z corner). Every call writes into the Build and returns an info dict.

  tree(b, x, y, z, species="oak", size="medium", seed=0, heights=None, ground=True, decor=True,
       leaves=None, wood=None, protect=True) -> {"species","size","height","radius","top","bbox",...}
      species: oak (round crown; large/huge = big branching oak), birch (huge = 3-stem clump), spruce (conical),
               pine (tall bare trunk, umbrella crown), jungle (huge: buttress roots, vines, cocoa), acacia (bent trunk,
               flat umbrella), dark_oak (2x2/3x3 trunk), cherry (pink, spreading), mangrove (prop roots, propagules),
               pale_oak (hanging moss, pale moss floor), willow (weeping leaf curtains + vines),
               poplar (narrow autumn column), palm (curved trunk, fronds, cocoa "coconuts"), dead (bare branches)
      size: small | medium | large | huge  (roughly 6 / 11 / 17 / 25+ blocks tall; spruce/jungle up to ~40)
      heights: optional (D,W) int heightmap, heights[z, x] = ground top y (same local frame); roots, trunk base,
               ground cover and leaf clipping then follow the terrain (else flat ground at y is assumed)
      ground: ground cover under the crown (podzol, leaf_litter, pink_petals, pale moss, mud, ferns...)
      decor: vines / cocoa / hanging moss / propagules / moss carpets;  leaves: "oak_leaves" or
             [("orange_poplar_leaves", 2), ("red_poplar_leaves", 1)];  wood: "spruce" | "stripped_birch" | ...
      protect: never overwrite existing non-natural Build blocks (walls, paths...)
  bush(b, x, y, z, kind="oak", size="small", seed=0, heights=None) -> dict
      kind: oak azalea flowering_azalea spruce jungle dark_oak birch cherry acacia mangrove pale_oak berry
  undergrowth(b, heights, area=None, density=0.3, style="forest", seed=0, water=None, avoid=None) -> int (plants)
      style: meadow forest birch taiga jungle savanna cherry dark swamp pale beach autumn
  forest(b, heights, area=None, density=0.5, species_mix="oak", seed=0, sizes=None, water=None, avoid=None,
         undergrowth=True, style=None, max_trees=400, ground=True) -> list[dict]
      area: (x0, z0, x1, z1) inclusive or (D,W) bool mask; density 0..1 (0.15 savanna .. 0.5 woodland .. 0.9 jungle);
      species_mix: "oak" | {"oak": 3, "birch": 1}; sizes: {"small": 2, "medium": 5, "large": 2, "huge": 0.5};
      trunks never overlap, crowns spaced by density, no trees on water/avoid cells, big trees placed first.
  crown_radius(species, size) -> float;  SPECIES, SIZES, BUSHES, STYLES
Guarantees: leaves persistent=true; branch logs use axis=x/y/z of the branch direction (diagonal parts and
elbows use *_wood); every log is face-connected to a log resting on/in the ground (no floating logs); leaves
are face-connected to the tree; roots/trunk base reach into the ground; only valid 26.3 block states.
"""
from __future__ import annotations

import math
import random

import numpy as np

from .. import blockdb

__all__ = ["tree", "bush", "undergrowth", "forest", "crown_radius", "SPECIES", "SIZES", "BUSHES", "STYLES"]

SPECIES = ("oak", "birch", "spruce", "pine", "jungle", "acacia", "dark_oak", "cherry", "mangrove", "pale_oak",
           "willow", "poplar", "palm", "dead")
SIZES = ("small", "medium", "large", "huge")
_ALIAS = {"darkoak": "dark_oak", "dark": "dark_oak", "pale": "pale_oak", "paleoak": "pale_oak", "fir": "spruce",
          "weeping_willow": "willow", "weeping": "willow", "sakura": "cherry", "coconut": "palm", "palm_tree": "palm",
          "scots_pine": "pine", "big_oak": "oak", "fancy_oak": "oak", "savanna": "acacia", "swamp": "mangrove",
          "autumn": "poplar", "bare": "dead"}

# ============================================================================ noise / hashing (deterministic)
_HM = (0x6C8E9CF5 & 0x7FFFFFFF, 0x3C6EF372, 0x1B873593, 0x5BD1E995 & 0x7FFFFFFF)


def _hash(seed, *cs):
    """Vectorised integer hash -> float in [0, 1)."""
    h = np.int64((int(seed) * 0x27D4EB2D + 0x165667B1) & 0xFFFFFFFF)
    for c, m in zip(cs, _HM):
        h = (h + np.asarray(c, dtype=np.int64) * m) & 0xFFFFFFFF
        h = h ^ (h >> 15)
        h = (h * 0x2C1B3C6D) & 0xFFFFFFFF
        h = h ^ (h >> 12)
    h = (h * 0x297A2D39) & 0xFFFFFFFF
    h = h ^ (h >> 15)
    return h / 4294967296.0


def _hs(seed, *cs) -> float:
    """Scalar (pure python) version of _hash."""
    h = (int(seed) * 0x27D4EB2D + 0x165667B1) & 0xFFFFFFFF
    for c, m in zip(cs, _HM):
        h = (h + int(c) * m) & 0xFFFFFFFF
        h ^= h >> 15
        h = (h * 0x2C1B3C6D) & 0xFFFFFFFF
        h ^= h >> 12
    h = (h * 0x297A2D39) & 0xFFFFFFFF
    h ^= h >> 15
    return h / 4294967296.0


def _sm(t):
    return t * t * (3.0 - 2.0 * t)


def _vnoise2(x, z, scale, seed):
    """Smooth 2D value noise in [0, 1]."""
    fx = np.asarray(x, dtype=np.float64) / scale
    fz = np.asarray(z, dtype=np.float64) / scale
    x0 = np.floor(fx)
    z0 = np.floor(fz)
    tx = _sm(fx - x0)
    tz = _sm(fz - z0)
    xi = x0.astype(np.int64)
    zi = z0.astype(np.int64)
    a = _hash(seed, xi, zi)
    b = _hash(seed, xi + 1, zi)
    c = _hash(seed, xi, zi + 1)
    d = _hash(seed, xi + 1, zi + 1)
    ab = a + (b - a) * tx
    cd = c + (d - c) * tx
    return ab + (cd - ab) * tz


def _vnoise3(x, y, z, scale, seed):
    """Smooth 3D value noise in [0, 1]."""
    f = [np.asarray(v, dtype=np.float64) / scale for v in (x, y, z)]
    i0 = [np.floor(v) for v in f]
    t = [_sm(v - w) for v, w in zip(f, i0)]
    ii = [w.astype(np.int64) for w in i0]
    acc = 0.0
    for dx in (0, 1):
        wx = t[0] if dx else 1.0 - t[0]
        for dy in (0, 1):
            wy = t[1] if dy else 1.0 - t[1]
            for dz in (0, 1):
                wz = t[2] if dz else 1.0 - t[2]
                acc = acc + wx * wy * wz * _hash(seed, ii[0] + dx, ii[1] + dy, ii[2] + dz)
    return acc


def _fbm2(x, z, scale, seed, octaves=3):
    s = 0.0
    tot = 0.0
    amp = 1.0
    for o in range(octaves):
        s = s + amp * _vnoise2(x, z, scale / (2 ** o), seed + 1013 * o)
        tot += amp
        amp *= 0.5
    return s / tot


def _mix(seed, *parts) -> int:
    h = (int(seed) * 0x9E3779B1 + 0x7F4A7C15) & 0xFFFFFFFF
    for p in parts:
        for ch in str(p):
            h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return h


# ============================================================================ small vector helpers
def _unit(x, y, z):
    n = math.sqrt(x * x + y * y + z * z) or 1.0
    return (x / n, y / n, z / n)


def _dir(az, el):
    c = math.cos(el)
    return (c * math.cos(az), math.sin(el), c * math.sin(az))


def _deviate(d, ang, rng):
    """Rotate unit vector d by `ang` radians around a random perpendicular axis."""
    a = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    p = _unit(d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
    q = (d[1] * p[2] - d[2] * p[1], d[2] * p[0] - d[0] * p[2], d[0] * p[1] - d[1] * p[0])
    phi = rng.uniform(0, 2 * math.pi)
    c, s = math.cos(ang), math.sin(ang)
    v = (math.cos(phi) * p[0] + math.sin(phi) * q[0], math.cos(phi) * p[1] + math.sin(phi) * q[1],
         math.cos(phi) * p[2] + math.sin(phi) * q[2])
    return _unit(c * d[0] + s * v[0], c * d[1] + s * v[1], c * d[2] + s * v[2])


def _traverse(p0, p1):
    """Amanatides-Woo voxel walk: face-connected cells from p0 to p1 with the mid parameter t of each cell."""
    x0, y0, z0 = p0
    d = (p1[0] - x0, p1[1] - y0, p1[2] - z0)
    cell = [math.floor(x0), math.floor(y0), math.floor(z0)]
    end = (math.floor(p1[0]), math.floor(p1[1]), math.floor(p1[2]))
    step = [1 if v > 0 else -1 for v in d]
    tmax = [math.inf] * 3
    tdel = [math.inf] * 3
    for i in range(3):
        if abs(d[i]) > 1e-12:
            nb = cell[i] + (1 if d[i] > 0 else 0)
            tmax[i] = (nb - (x0, y0, z0)[i]) / d[i]
            tdel[i] = abs(1.0 / d[i])
    out = []
    tp = 0.0
    nmax = abs(end[0] - cell[0]) + abs(end[1] - cell[1]) + abs(end[2] - cell[2]) + 1
    for _ in range(nmax + 2):
        a = 0 if (tmax[0] <= tmax[1] and tmax[0] <= tmax[2]) else (1 if tmax[1] <= tmax[2] else 2)
        tn = min(tmax[a], 1.0)
        out.append(((cell[0], cell[1], cell[2]), (tp + tn) * 0.5))
        if (cell[0], cell[1], cell[2]) == end or tmax[a] > 1.0 + 1e-9:
            break
        cell[a] += step[a]
        tp = tmax[a]
        tmax[a] += tdel[a]
    return out


def _dilate6(m):
    o = m.copy()
    o[1:] |= m[:-1]
    o[:-1] |= m[1:]
    o[:, 1:] |= m[:, :-1]
    o[:, :-1] |= m[:, 1:]
    o[:, :, 1:] |= m[:, :, :-1]
    o[:, :, :-1] |= m[:, :, 1:]
    return o


def _reach(region, seeds, steps):
    """Cells of `region` reachable (6-connected, through region) from `seeds` within `steps` steps."""
    r = _dilate6(seeds) & region
    f = r
    for _ in range(max(0, steps - 1)):
        f = _dilate6(f) & region & ~r
        if not f.any():
            break
        r |= f
    return r


_DIRS4 = ((1, 0, "east"), (-1, 0, "west"), (0, 1, "south"), (0, -1, "north"))
_OPP = {"east": "west", "west": "east", "south": "north", "north": "south"}

# ============================================================================ species data
_SP = {
    "oak": ("oak", (("oak_leaves", 1.0),)),
    "birch": ("birch", (("birch_leaves", 1.0),)),
    "spruce": ("spruce", (("spruce_leaves", 1.0),)),
    "pine": ("spruce", (("spruce_leaves", 1.0),)),
    "jungle": ("jungle", (("jungle_leaves", 1.0),)),
    "acacia": ("acacia", (("acacia_leaves", 1.0),)),
    "dark_oak": ("dark_oak", (("dark_oak_leaves", 1.0),)),
    "cherry": ("cherry", (("cherry_leaves", 1.0),)),
    "mangrove": ("mangrove", (("mangrove_leaves", 1.0),)),
    "pale_oak": ("pale_oak", (("pale_oak_leaves", 1.0),)),
    "willow": ("oak", (("oak_leaves", 0.5), ("birch_leaves", 0.5))),
    "poplar": ("poplar", (("yellow_poplar_leaves", 0.6), ("orange_poplar_leaves", 0.3), ("red_poplar_leaves", 0.1))),
    "palm": ("jungle", (("jungle_leaves", 1.0),)),
    "dead": ("oak", ()),
}
# approximate crown radius per size (forest spacing)
_CROWN = {
    "oak": (3.2, 6.0, 9.0, 13.0), "birch": (2.6, 3.2, 3.8, 6.0), "spruce": (2.8, 4.2, 6.0, 8.5),
    "pine": (2.8, 3.6, 4.6, 6.0), "jungle": (3.0, 5.0, 7.5, 10.5), "acacia": (3.6, 5.2, 7.0, 9.0),
    "dark_oak": (4.0, 5.2, 7.0, 10.0), "cherry": (4.0, 5.5, 7.2, 9.0), "mangrove": (3.4, 4.6, 6.0, 8.0),
    "pale_oak": (3.8, 5.0, 6.6, 8.6), "willow": (4.2, 5.6, 7.2, 9.2), "poplar": (1.9, 2.4, 2.9, 3.6),
    "palm": (4.0, 5.2, 6.4, 8.0), "dead": (2.6, 3.6, 5.0, 7.0)}
# trunk footprint width (for ground/slope checks)
_TW = {"dark_oak": (2, 2, 2, 3), "pale_oak": (2, 2, 2, 3), "jungle": (1, 1, 2, 3), "spruce": (1, 1, 1, 2),
       "pine": (1, 1, 1, 2), "oak": (1, 1, 3, 3), "willow": (1, 1, 3, 3), "cherry": (1, 1, 1, 3)}


def crown_radius(species: str, size: str = "medium") -> float:
    sp = _norm_species(species)
    return _CROWN[sp][SIZES.index(_norm_size(size))]


def _norm_species(s: str) -> str:
    k = str(s).strip().lower().replace(" ", "_").replace("-", "_")
    k = _ALIAS.get(k, k)
    if k not in SPECIES:
        raise ValueError(f"unknown tree species '{s}' (choose: {', '.join(SPECIES)})")
    return k


def _norm_size(s: str) -> str:
    k = str(s).strip().lower()
    k = {"s": "small", "m": "medium", "l": "large", "xl": "huge", "big": "large", "giant": "huge"}.get(k, k)
    if k not in SIZES:
        raise ValueError(f"unknown tree size '{s}' (choose: {', '.join(SIZES)})")
    return k


def _wood_states(db, w: str) -> tuple[str, str]:
    """'oak' -> (oak_log, oak_wood); 'crimson' -> (crimson_stem, crimson_hyphae); accepts full log names."""
    w = w.split(":", 1)[-1]
    for suf in ("_log", "_wood", "_stem", "_hyphae"):
        if w.endswith(suf):
            w = w[: -len(suf)]
            break
    if db.has_block(w + "_log"):
        return w + "_log", (w + "_wood") if db.has_block(w + "_wood") else w + "_log"
    if db.has_block(w + "_stem"):
        return w + "_stem", (w + "_hyphae") if db.has_block(w + "_hyphae") else w + "_stem"
    raise ValueError(f"no log block for wood '{w}'")


def _leaf_mix(leaves):
    if leaves is None:
        return None
    if isinstance(leaves, str):
        return ((leaves, 1.0),)
    out = []
    for e in leaves:
        if isinstance(e, str):
            out.append((e, 1.0))
        else:
            out.append((str(e[0]), float(e[1])))
    return tuple(out)


# ============================================================================ build-palette classes
_SOFT = {"grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "mud", "moss_block", "pale_moss_block", "mycelium",
         "sand", "red_sand", "gravel", "clay", "dirt_path", "farmland", "snow_block", "muddy_mangrove_roots",
         "packed_mud", "suspicious_sand", "suspicious_gravel"}
_GROUNDISH = _SOFT | {"stone", "andesite", "diorite", "granite", "tuff", "deepslate", "calcite", "sandstone",
                      "red_sandstone", "terracotta", "cobblestone", "mossy_cobblestone"}


_ANY_SOLID_PLANTS = ("brown_mushroom", "red_mushroom", "leaf_litter", "moss_carpet", "pale_moss_carpet", "snow")


def _soil_ok(plant: str, below: str) -> bool:
    """Denetcinin toprak kurallariyla ayni: cicek/ot/egrelti/petal yalniz toprak turu bloklarin ustunde yasar."""
    from ..audit.checks import SOIL_TESTS, _plant_soil
    nm = plant.lstrip("!").split("[", 1)[0].split(":", 1)[-1]
    bn = below.lstrip("!").split("[", 1)[0].split(":", 1)[-1]
    if nm in _ANY_SOLID_PLANTS or nm.endswith("_carpet"):
        return "leaves" not in bn and not bn.endswith(("_slab", "_stairs", "_fence", "_wall", "_path"))
    return SOIL_TESTS[_plant_soil(nm)](bn)


def _classes(b):
    """Per palette id: free (keep/air/replaceable plant), leafy, soft ground, water, full-solid."""
    db = b.db
    n = len(b.palette)
    free = np.zeros(n, bool)
    leafy = np.zeros(n, bool)
    soft = np.zeros(n, bool)
    water = np.zeros(n, bool)
    solid = np.zeros(n, bool)
    free[0] = True
    free[1] = True
    for i in range(2, n):
        st = b.palette[i].lstrip("!")
        name = st.split("[", 1)[0].split(":", 1)[-1]
        try:
            f = db.flags_of(st)
        except Exception:
            continue
        solid[i] = bool(f & blockdb.FULL)
        if f & blockdb.AIR:
            free[i] = True
        elif name.endswith("_leaves"):
            leafy[i] = True
        elif name in _SOFT:
            soft[i] = True
        elif name == "water" or (f & blockdb.FLUID):
            water[i] = True
        elif (f & blockdb.REPLACEABLE) or ((f & blockdb.PLANT) and not (f & blockdb.FULL)) or name in (
                "leaf_litter", "pink_petals", "wildflowers", "moss_carpet", "pale_moss_carpet", "snow"):
            free[i] = True
    return free, leafy, soft, water, solid


# ============================================================================ the tree canvas
class _Tip:
    __slots__ = ("p", "d", "depth", "r")

    def __init__(self, p, d, depth, r):
        self.p, self.d, self.depth, self.r = p, d, depth, r


class _Tree:
    def __init__(self, b, x, y, z, rng, seed, log, woodb, leaves, heights):
        self.b = b
        self.x, self.y, self.z = int(x), int(y), int(z)
        self.rng = rng
        self.seed = int(seed) & 0x7FFFFFFF
        self.log_st = {a: f"{log}[axis={a}]" for a in "xyz"}
        self.wood_st = f"{woodb}[axis=y]" if "[" not in woodb and self._has_axis(woodb) else woodb
        self.log_name = log
        self.leaves = tuple(leaves)
        self.heights = None if heights is None else np.asarray(heights)
        self.logs: dict = {}
        self.trunk_cells: set = set()
        self.blobs: list = []
        self.lmasks: list = []
        self.lcells: dict = {}
        self.deco: dict = {}      # (x,y,z) -> (state, support (dx,dy,dz) or None)
        self.cover: dict = {}     # ground replacements (x,y,z) -> state
        self.mids: list = []
        self.spine: list = []
        self.reach = 7
        self.post: list = []      # decoration recipes
        self.cover_spec = None
        self.leaf_arr = None
        self.speckle = 0.0
        self.mix_scale = 3.0
        self.mix_noise = 0.4

    def _has_axis(self, name):
        try:
            return "axis" in self.b.db.blocks.get("minecraft:" + name.split(":")[-1], {}).get("props", {})
        except Exception:
            return False

    # ---------------------------------------------------------------- ground
    def gy(self, x, z) -> int:
        h = self.heights
        if h is not None:
            i, j = int(math.floor(z)), int(math.floor(x))
            if 0 <= i < h.shape[0] and 0 <= j < h.shape[1]:
                return int(h[i, j])
        return self.y

    def ground_grid(self, x0, z0, nx, nz):
        g = np.full((nz, nx), self.y, dtype=np.int64)
        h = self.heights
        if h is not None:
            D, W = h.shape
            i0, i1 = max(0, z0), min(D, z0 + nz)
            j0, j1 = max(0, x0), min(W, x0 + nx)
            if i0 < i1 and j0 < j1:
                g[i0 - z0:i1 - z0, j0 - x0:j1 - x0] = h[i0:i1, j0:j1]
        return g

    # ---------------------------------------------------------------- wood
    def setlog(self, c, axis="y", wood=False, trunk=False, force=False):
        st = self.wood_st if wood else self.log_st[axis]
        if trunk:
            self.trunk_cells.add(c)
            if force or c not in self.logs:
                self.logs[c] = st
        elif force:
            if c not in self.trunk_cells:
                self.logs[c] = st
        elif c not in self.logs:
            self.logs[c] = st

    def setraw(self, c, state, force=False):
        if force or c not in self.logs:
            self.logs[c] = state

    def tube(self, p0, p1, r0=0.5, r1=None, axis=None, state=None):
        """Face-connected log tube from p0 to p1 (radius r0 -> r1). Axis = dominant direction; diagonal -> wood."""
        if r1 is None:
            r1 = r0
        d = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        ln = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2) or 1.0
        k = max(range(3), key=lambda i: abs(d[i]))
        ax = axis or "xyz"[k]
        diag = axis is None and abs(d[k]) / ln < 0.72 and ln > 1.2
        cells = []
        for cell, t in _traverse(p0, p1):
            r = r0 + (r1 - r0) * t
            cs = [cell]
            if r > 0.55:
                P = (p0[0] + d[0] * t, p0[1] + d[1] * t, p0[2] + d[2] * t)
                R = int(math.ceil(r)) + 1
                r2 = r * r
                fx, fy, fz = math.floor(P[0]), math.floor(P[1]), math.floor(P[2])
                for ix in range(fx - R, fx + R + 1):
                    ddx = (ix + 0.5 - P[0]) ** 2
                    if ddx > r2:
                        continue
                    for iy in range(fy - R, fy + R + 1):
                        ddy = ddx + (iy + 0.5 - P[1]) ** 2
                        if ddy > r2:
                            continue
                        for iz in range(fz - R, fz + R + 1):
                            if ddy + (iz + 0.5 - P[2]) ** 2 <= r2:
                                cs.append((ix, iy, iz))
            for c in cs:
                if state is not None:
                    self.setraw(c, state)
                else:
                    self.setlog(c, ax, wood=diag)
            cells.append(cell)
        return cells

    def trunk(self, top, r0=0.5, r1=None, flare=0.0, lean=None, wobble=0.0, even=False, y0=None, cx=None, cz=None,
              bark=0.0, anchor=True):
        """Vertical trunk from y0 (default y+1) to `top` (inclusive); returns spine points (one per layer)."""
        if r1 is None:
            r1 = r0
        if y0 is None:
            y0 = self.y + 1
        bx = cx if cx is not None else (self.x + (1.0 if even else 0.5))
        bz = cz if cz is not None else (self.z + (1.0 if even else 0.5))
        n = max(1, top - y0)
        spine = []
        prev_c = None
        first = None
        ws = self.seed + 77
        for k in range(top - y0 + 1):
            f = k / n
            ox = oz = 0.0
            if lean:
                ox, oz = lean[0] * f ** 1.5, lean[1] * f ** 1.5
            if wobble:
                ox += wobble * (float(_vnoise2(k * 0.45, 3.1, 1.0, ws)) - 0.5) * 2.0
                oz += wobble * (float(_vnoise2(k * 0.45, 9.7, 1.0, ws + 1)) - 0.5) * 2.0
            px, pz = bx + ox, bz + oz
            y = y0 + k
            r = r0 + (r1 - r0) * f + flare * math.exp(-k / 1.4)
            cells = [(math.floor(px), y, math.floor(pz))]
            if r > 0.55:
                R = int(math.ceil(r)) + 1
                fx, fz = math.floor(px), math.floor(pz)
                for i in range(fx - R, fx + R + 1):
                    for kk in range(fz - R, fz + R + 1):
                        rr = r
                        if bark:
                            rr += bark * (_hs(self.seed + 5, i, y // 3, kk) - 0.5)
                        if (i + 0.5 - px) ** 2 + (kk + 0.5 - pz) ** 2 <= rr * rr:
                            cells.append((i, y, kk))
            for c in cells:
                self.setlog(c, "y", trunk=True)
            cc = (math.floor(px), math.floor(pz))
            if prev_c is not None and len(cells) == 1 and cc != prev_c:
                # single-cell layer moved sideways: keep it face connected (elbow in wood)
                for cell, _t in _traverse((prev_c[0] + 0.5, y - 0.5, prev_c[1] + 0.5), (cc[0] + 0.5, y - 0.5, cc[1] + 0.5)):
                    if cell[0:3:2] != prev_c:
                        self.setlog(cell, wood=True, trunk=True, force=True)
            prev_c = cc
            if first is None:
                first = cells
            spine.append((px, y + 0.5, pz))
        if anchor and first:
            for c in first:
                g = self.gy(c[0], c[2])
                for yy in range(min(g, y0 - 1) - 1, y0):
                    self.setlog((c[0], yy, c[2]), "y", trunk=True)
        self.spine = spine
        return spine

    def at(self, frac_or_y, absolute=False):
        """Spine point at a height fraction (0..1 of spine) or absolute y."""
        sp = self.spine
        if not sp:
            return (self.x + 0.5, self.y + 1.5, self.z + 0.5)
        if absolute:
            i = int(frac_or_y) - int(math.floor(sp[0][1]))
        else:
            i = int(round(frac_or_y * (len(sp) - 1)))
        return sp[max(0, min(len(sp) - 1, i))]

    def grow(self, p, d, L, r, depth, P, mids=True):
        """Recursive limb. P: seg wiggle up taper forks fork_at fork_ang child_len min_el. Returns tips."""
        rng = self.rng
        seg = P.get("seg", 2.2)
        n = max(1, int(round(L / seg)))
        st = L / n
        pts = [p]
        dirs = []
        cur = d
        w = P.get("wiggle", 0.22)
        up = P.get("up", 0.06)
        for _ in range(n):
            cur = _unit(cur[0] + rng.uniform(-w, w), cur[1] + rng.uniform(-w, w) * 0.5 + up, cur[2] + rng.uniform(-w, w))
            if cur[1] < P.get("min_el", -0.35):
                cur = _unit(cur[0], P.get("min_el", -0.35), cur[2])
            q = pts[-1]
            pts.append((q[0] + cur[0] * st, q[1] + cur[1] * st, q[2] + cur[2] * st))
            dirs.append(cur)
        r_end = max(0.5, r * P.get("taper", 0.6))
        axes = []
        for i in range(n):
            ra = r + (r_end - r) * i / n
            rb = r + (r_end - r) * (i + 1) / n
            self.tube(pts[i], pts[i + 1], ra, rb)
            dd = dirs[i]
            axes.append(max(range(3), key=lambda j: abs(dd[j])))
        for i in range(1, n):  # elbows where the grain changes -> wood
            if axes[i] != axes[i - 1]:
                c = tuple(math.floor(v) for v in pts[i])
                if c in self.logs and c not in self.trunk_cells:
                    self.logs[c] = self.wood_st
        tips = []
        if depth > 0:
            nf = P.get("forks", 2)
            if isinstance(nf, tuple):
                nf = rng.randint(*nf)
            if rng.random() > P.get("fork_p", 1.0):
                nf = 0
            for _ in range(nf):
                f = rng.uniform(*P.get("fork_at", (0.45, 0.9)))
                i = min(n - 1, max(0, int(f * n)))
                q = pts[i + 1] if i + 1 < len(pts) - 1 else pts[i]
                nd = _deviate(dirs[i], math.radians(rng.uniform(*P.get("fork_ang", (25, 45)))), rng)
                if nd[1] < P.get("min_el", -0.35):
                    nd = _unit(nd[0], P.get("min_el", -0.35), nd[2])
                cl = max(1.5, L * (1.0 - f * 0.6) * rng.uniform(*P.get("child_len", (0.55, 0.85))))
                rr = max(0.5, (r + (r_end - r) * f) * 0.72)
                tips += self.grow(q, nd, cl, rr, depth - 1, P, mids)
        tips.append(_Tip(pts[-1], dirs[-1], depth, r_end))
        if mids and n >= 2:
            for i in range(1, n):
                self.mids.append((pts[i], dirs[i - 1], depth))
        return tips

    def roots(self, n, length, r0=0.5, rise=1.0, start_r=0.5, cx=None, cz=None, y0=None, state=None, az0=None,
              dive=1.6):
        """Radial surface roots that rise from the trunk base and dive into the ground."""
        rng = self.rng
        cx = self.spine[0][0] if (cx is None and self.spine) else (cx if cx is not None else self.x + 0.5)
        cz = self.spine[0][2] if (cz is None and self.spine) else (cz if cz is not None else self.z + 0.5)
        if az0 is None:
            az0 = rng.uniform(0, 2 * math.pi)
        for k in range(n):
            a = az0 + k * 2 * math.pi / n + rng.uniform(-0.35, 0.35)
            L = length[0] + (length[1] - length[0]) * rng.random() if isinstance(length, tuple) else length
            steps = max(2, int(math.ceil(L)) + 1)
            pts = []
            for s in range(steps + 1):
                f = s / steps
                rr = start_r + f * L
                px, pz = cx + math.cos(a) * rr, cz + math.sin(a) * rr
                g = self.gy(px, pz)
                base = (y0 if y0 is not None else g + 1)
                if s == 0:
                    h = base + rise
                else:
                    h = g + 1 + rise * (1 - f) ** 1.6 - dive * f ** 1.4
                pts.append((px, h + 0.5, pz))
            for i in range(len(pts) - 1):
                rr0 = r0 * (1 - 0.5 * i / steps)
                self.tube(pts[i], pts[i + 1], max(0.5, rr0), max(0.5, rr0 * 0.8), state=state)

    # ---------------------------------------------------------------- leaves
    def blob(self, c, r, ry=None, ryb=None, dens=0.85, li=None, rag=1.0):
        if ry is None:
            ry = r * 0.78
        if ryb is None:
            ryb = ry * 0.72
        self.blobs.append((float(c[0]), float(c[1]), float(c[2]), float(r), float(ry), float(ryb), float(dens), li,
                           float(rag)))

    def cluster(self, c, r, flat=0.6, under=0.35, lumps=2, dens=0.82, rag=1.15, li=None):
        """Foliage pad: flattened dome (flat bottom) + a few smaller lumps on its top/sides (cauliflower look)."""
        rng = self.rng
        self.blob(c, r, r * flat, r * under, dens, li, rag)
        for _ in range(lumps):
            a = rng.uniform(0, 2 * math.pi)
            d = r * rng.uniform(0.45, 0.8)
            rr = r * rng.uniform(0.5, 0.68)
            cc = (c[0] + math.cos(a) * d, c[1] + r * flat * rng.uniform(0.15, 0.55), c[2] + math.sin(a) * d)
            self.blob(cc, rr, rr * (flat + 0.1), rr * under, dens, li, rag)

    def disc(self, cx, y, cz, R, rag=0.25, li=None, hole=0.0):
        """Flat ragged leaf disc (one layer) - acacia/spruce/pine pads."""
        if R <= 0.3:
            self.lcells[(math.floor(cx), int(y), math.floor(cz))] = li
            return
        Ri = int(math.ceil(R * (1 + rag))) + 1
        x0, z0 = math.floor(cx) - Ri, math.floor(cz) - Ri
        xs = np.arange(x0, x0 + 2 * Ri + 1) + 0.5
        zs = np.arange(z0, z0 + 2 * Ri + 1) + 0.5
        X, Z = np.meshgrid(xs, zs)
        dist = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
        n = _vnoise3(X - self.x, np.full_like(X, y - self.y), Z - self.z, 1.8, self.seed + 31)
        hsh = _hash(self.seed + 37, np.floor(X).astype(np.int64), int(y), np.floor(Z).astype(np.int64))
        lim = np.maximum(R * (1.0 + rag * (n - 0.5) * 2.0), R - 0.6)
        m = (dist <= lim) & ((dist < lim - 0.9) | (hsh < 0.7))
        if R >= 1.0:
            m |= dist <= 1.01
        if hole > 0:
            m &= dist >= hole
        m |= dist < 0.75
        self.lmasks.append((x0, int(y), z0, m[None, :, :], li))

    def leaf(self, c, li=None):
        self.lcells[(int(c[0]), int(c[1]), int(c[2]))] = li

    def _raster(self):
        boxes = []
        for (cx, cy, cz, r, ry, ryb, dens, li, rag) in self.blobs:
            boxes.append((cx - r - 1.6, cy - ryb - 1.6, cz - r - 1.6, cx + r + 1.6, cy + ry + 1.6, cz + r + 1.6))
        for (x0, y0, z0, m, li) in self.lmasks:
            boxes.append((x0, y0, z0, x0 + m.shape[2], y0 + m.shape[0], z0 + m.shape[1]))
        for (x, y, z) in self.lcells:
            boxes.append((x, y, z, x + 1, y + 1, z + 1))
        if not boxes:
            return None
        X0 = math.floor(min(b[0] for b in boxes))
        Y0 = math.floor(min(b[1] for b in boxes))
        Z0 = math.floor(min(b[2] for b in boxes))
        X1 = math.ceil(max(b[3] for b in boxes))
        Y1 = math.ceil(max(b[4] for b in boxes))
        Z1 = math.ceil(max(b[5] for b in boxes))
        MIX = 250
        arr = np.zeros((Y1 - Y0 + 1, Z1 - Z0 + 1, X1 - X0 + 1), dtype=np.int16)
        for (cx, cy, cz, r, ry, ryb, dens, li, rag) in self.blobs:
            xa, xb = math.floor(cx - r - 1.5), math.ceil(cx + r + 1.5)
            ya, yb = math.floor(cy - ryb - 1.5), math.ceil(cy + ry + 1.5)
            za, zb = math.floor(cz - r - 1.5), math.ceil(cz + r + 1.5)
            gy, gz, gx = np.meshgrid(np.arange(ya, yb + 1), np.arange(za, zb + 1), np.arange(xa, xb + 1), indexing="ij")
            fx, fy, fz = gx + 0.5, gy + 0.5, gz + 0.5
            dy = fy - cy
            d = np.sqrt(((fx - cx) / r) ** 2 + np.where(dy > 0, dy / ry, dy / ryb) ** 2 + ((fz - cz) / r) ** 2)
            n = _vnoise3(fx - self.x, fy - self.y, fz - self.z, 2.4, self.seed + 11)
            h = _hash(self.seed + 13, gx, gy, gz)
            thr = 1.0 + 0.38 * rag * (n - 0.5)
            shell = 0.2 + 0.22 * rag
            m = (d < thr) & ((d < thr - shell) | (h < 0.25 + 0.6 * dens))
            code = MIX if li is None else li + 1
            sub = arr[ya - Y0:yb - Y0 + 1, za - Z0:zb - Z0 + 1, xa - X0:xb - X0 + 1]
            sub[m & (sub == 0)] = code
        for (x0, y0, z0, m, li) in self.lmasks:
            code = MIX if li is None else li + 1
            sub = arr[y0 - Y0:y0 - Y0 + m.shape[0], z0 - Z0:z0 - Z0 + m.shape[1], x0 - X0:x0 - X0 + m.shape[2]]
            sub[m & (sub == 0)] = code
        for (x, y, z), li in self.lcells.items():
            if arr[y - Y0, z - Z0, x - X0] == 0:
                arr[y - Y0, z - Z0, x - X0] = MIX if li is None else li + 1
        if self.speckle > 0:  # a few mixed-colour leaves inside single-colour blobs
            hit = (arr > 0) & (arr != MIX)
            ys, zs, xs = np.nonzero(hit)
            sel = _hash(self.seed + 23, xs, ys, zs) < self.speckle
            arr[ys[sel], zs[sel], xs[sel]] = MIX
        # resolve mixtures with patchy noise
        mixm = arr == MIX
        if mixm.any():
            ys, zs, xs = np.nonzero(mixm)
            if len(self.leaves) <= 1:
                arr[mixm] = 1
            else:
                v = (1.0 - self.mix_noise) * _vnoise3(xs + X0 - self.x, ys + Y0 - self.y, zs + Z0 - self.z,
                                                      self.mix_scale, self.seed + 17) \
                    + self.mix_noise * _hash(self.seed + 19, xs, ys, zs)
                w = np.array([max(0.0, e[1]) for e in self.leaves], dtype=np.float64)
                cw = np.cumsum(w) / max(1e-9, w.sum())
                # stretch v (mean-centred noise) to roughly uniform
                vv = np.clip((v - 0.5) * 1.7 + 0.5, 0, 0.999999)
                idx = np.searchsorted(cw, vv, side="right")
                arr[ys, zs, xs] = (np.minimum(idx, len(self.leaves) - 1) + 1).astype(np.int16)
        return (X0, Y0, Z0), arr

    # ---------------------------------------------------------------- finishing
    def finish(self, ground=True, decor=True):
        rast = self._raster() if self.leaves else None
        # unified occupancy box (logs + leaves + margin)
        pts = list(self.logs.keys())
        if rast is not None:
            (lx, ly, lz), arr = rast
            pts += [(lx, ly, lz), (lx + arr.shape[2] - 1, ly + arr.shape[0] - 1, lz + arr.shape[1] - 1)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        X0, X1 = min(xs) - 3, max(xs) + 3
        Z0, Z1 = min(zs) - 3, max(zs) + 3
        Y1 = max(ys) + 1
        G = self.ground_grid(X0, Z0, X1 - X0 + 1, Z1 - Z0 + 1)
        Y0 = min(min(ys), int(G.min())) - 1
        sh = (Y1 - Y0 + 1, Z1 - Z0 + 1, X1 - X0 + 1)
        occ = np.zeros(sh, dtype=np.int8)
        if self.logs:
            k = np.array(list(self.logs.keys()), dtype=np.int64)
            occ[k[:, 1] - Y0, k[:, 2] - Z0, k[:, 0] - X0] = 1
        leafid = np.zeros(sh, dtype=np.int16)
        if rast is not None:
            sub = leafid[ly - Y0:ly - Y0 + arr.shape[0], lz - Z0:lz - Z0 + arr.shape[1], lx - X0:lx - X0 + arr.shape[2]]
            sub[:] = arr
        yy = np.arange(Y0, Y1 + 1)[:, None, None]
        under = yy <= G[None, :, :]
        logm = occ == 1
        leafm = (leafid > 0) & ~logm & ~under
        if leafm.any():
            leafm = _reach(leafm, logm, self.reach)
        leafid[~leafm] = 0
        occ[leafm] = 2
        self.box = (X0, Y0, Z0)
        self.occ = occ
        self.leafid = leafid
        self.G = G
        self.under = under
        if decor:
            for rec in self.post:
                rec[0](self, *rec[1:])
        if ground and self.cover_spec:
            self._ground_cover(*self.cover_spec)

    def empty(self, c):
        X0, Y0, Z0 = self.box
        i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
        if not (0 <= i < self.occ.shape[0] and 0 <= j < self.occ.shape[1] and 0 <= k < self.occ.shape[2]):
            return c[1] > self.gy(c[0], c[2]) and c not in self.deco
        return self.occ[i, j, k] == 0 and not self.under[i, j, k] and c not in self.deco

    def occ_at(self, c):
        X0, Y0, Z0 = self.box
        i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
        if 0 <= i < self.occ.shape[0] and 0 <= j < self.occ.shape[1] and 0 <= k < self.occ.shape[2]:
            return int(self.occ[i, j, k])
        return 0

    def _cands(self, src, side, salt, prob):
        """Cells next to `src` (mask) on `side` ('down' or (dx,dz)) that are empty; random subset with prob."""
        occ = self.occ
        free = (occ == 0) & ~self.under
        out = []
        rs = np.random.default_rng(self.seed + salt)
        if side == "down":
            m = src[1:] & free[:-1]
            ys, zs, xs = np.nonzero(m)
            ys = ys  # cell below = index ys (since m[i] relates src[i+1] & free[i])
            sel = rs.random(len(ys)) < prob
            X0, Y0, Z0 = self.box
            for y, z, x in zip(ys[sel], zs[sel], xs[sel]):
                out.append((int(x) + X0, int(y) + Y0, int(z) + Z0))
            return out
        dx, dz = side
        sh = np.zeros_like(src)
        if dx == 1:
            sh[:, :, 1:] = src[:, :, :-1]
        elif dx == -1:
            sh[:, :, :-1] = src[:, :, 1:]
        elif dz == 1:
            sh[:, 1:, :] = src[:, :-1, :]
        else:
            sh[:, :-1, :] = src[:, 1:, :]
        m = sh & free
        ys, zs, xs = np.nonzero(m)
        sel = rs.random(len(ys)) < prob
        X0, Y0, Z0 = self.box
        for y, z, x in zip(ys[sel], zs[sel], xs[sel]):
            out.append((int(x) + X0, int(y) + Y0, int(z) + Z0))
        return out

    def strand_down(self, c, state_fn, maxlen, support, minfree=1):
        """Hanging chain from c downward while empty and above ground+minfree."""
        cells = []
        x, y, z = c
        g = self.gy(x, z)
        for k in range(maxlen):
            cc = (x, y - k, z)
            if cc[1] <= g + minfree - 1 or not self.empty(cc):
                break
            cells.append(cc)
        n = len(cells)
        for k, cc in enumerate(cells):
            self.deco[cc] = (state_fn(k, n), support if k == 0 else (0, 1, 0))
        return n

    def _ground_cover(self, radius, blocks, plants):
        rng = random.Random(self.seed + 991)
        cx = self.spine[0][0] if self.spine else self.x + 0.5
        cz = self.spine[0][2] if self.spine else self.z + 0.5
        R = max(1.5, radius)
        Ri = int(math.ceil(R))
        for i in range(math.floor(cx) - Ri, math.floor(cx) + Ri + 1):
            for k in range(math.floor(cz) - Ri, math.floor(cz) + Ri + 1):
                d = math.hypot(i + 0.5 - cx, k + 0.5 - cz)
                if d > R:
                    continue
                g = self.gy(i, k)
                w = (1.0 - d / R) ** 0.6
                gc = (i, g, k)
                above = (i, g + 1, k)
                if self.occ_at(gc) != 0:
                    continue
                n = float(_vnoise2(i - self.x, k - self.z, 3.0, self.seed + 3))
                for st, p in blocks:
                    if rng.random() < p * w * (0.5 + n):
                        self.cover[gc] = st
                        break
                if not self.empty(above):
                    continue
                for fn, p in plants:
                    if rng.random() < p * w:
                        res = fn(rng) if callable(fn) else fn
                        if isinstance(res, tuple):  # double plant
                            top = (i, g + 2, k)
                            if self.empty(top):
                                self.deco[above] = (res[0], (0, -1, 0))
                                self.deco[top] = (res[1], (0, -1, 0))
                        else:
                            self.deco[above] = (res, (0, -1, 0))
                        break

    # ---------------------------------------------------------------- write
    def commit(self, protect=True):
        b = self.b
        X0, Y0, Z0 = self.box
        occ = self.occ
        want = np.zeros(occ.shape, dtype=np.int32)
        cls = np.zeros(occ.shape, dtype=np.int8)
        sup = {}
        # leaves
        lstates = [b.pid(f"{name}[persistent=true]") for name, _w in self.leaves]
        if lstates:
            for k, pid in enumerate(lstates):
                m = self.leafid == k + 1
                want[m] = pid
                cls[m] = 2
        # logs
        if self.logs:
            keys = np.array(list(self.logs.keys()), dtype=np.int64)
            pidc = {}
            vals = np.array([pidc.setdefault(s, b.pid(s)) for s in self.logs.values()], dtype=np.int32)
            want[keys[:, 1] - Y0, keys[:, 2] - Z0, keys[:, 0] - X0] = vals
            cls[keys[:, 1] - Y0, keys[:, 2] - Z0, keys[:, 0] - X0] = 1
        sh = occ.shape

        def inside(c):
            i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
            return 0 <= i < sh[0] and 0 <= j < sh[1] and 0 <= k < sh[2]

        extra = {}
        for c, (st, s) in self.deco.items():
            if inside(c):
                i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
                if cls[i, j, k] == 0:
                    want[i, j, k] = b.pid(st)
                    cls[i, j, k] = 3
                    sup[c] = s
            else:
                extra[c] = (st, s)
        for c, st in self.cover.items():
            if inside(c):
                i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
                if cls[i, j, k] == 0:
                    want[i, j, k] = b.pid(st)
                    cls[i, j, k] = 4
        cur = b.ids_box(X0, Y0, Z0, X0 + sh[2] - 1, Y0 + sh[0] - 1, Z0 + sh[1] - 1)
        free, leafy, soft, water, solid = _classes(b)
        if protect:
            ok = ((cls == 1) & (free[cur] | leafy[cur] | soft[cur] | water[cur])) | ((cls == 2) & free[cur]) \
                | ((cls == 3) & free[cur]) | ((cls == 4) & ((cur == 0) | soft[cur]))
        else:
            ok = cls > 0
        # mangrove roots in water -> waterlogged
        if self.logs:
            wr = (cls == 1) & ok & water[cur]
            if wr.any():
                mr = b.pid("mangrove_roots")
                want[wr & (want == mr)] = b.pid("mangrove_roots[waterlogged=true]")
        blocked = (cls == 1) & ~ok
        if blocked.any():
            logm = (cls == 1) & ok
            yy = np.arange(Y0, Y0 + sh[0])[:, None, None]
            anchor = logm & (yy <= self.G[None, :, :] + 1)
            r = _reach(logm, anchor, 10 ** 6) | anchor
            ok &= ~((cls == 1) & ~r)
            leafm = (cls == 2) & ok
            ok &= ~((cls == 2) & ~_reach(leafm, (cls == 1) & ok, self.reach))
        # decoration support check (top-down so chains fall with their support)
        if sup:
            for c in sorted(sup, key=lambda c: -c[1]):
                i, j, k = c[1] - Y0, c[2] - Z0, c[0] - X0
                if not ok[i, j, k]:
                    continue
                s = sup[c]
                if s is None:
                    continue
                q = (c[0] + s[0], c[1] + s[1], c[2] + s[2])
                if inside(q):
                    qi, qj, qk = q[1] - Y0, q[2] - Z0, q[0] - X0
                    good = (cls[qi, qj, qk] > 0 and ok[qi, qj, qk]) or bool(solid[cur[qi, qj, qk]]) or \
                        (cls[qi, qj, qk] == 0 and cur[qi, qj, qk] == 0 and s == (0, -1, 0))
                    # yer bitkisi var olan bir blogun ustune (cit yapragi, tas, yol) konmaz: yalniz uygun topraga
                    if good and s == (0, -1, 0) and cls[qi, qj, qk] == 0 and cur[qi, qj, qk] > 1 and                             not _soil_ok(b.palette[want[i, j, k]], b.palette[cur[qi, qj, qk]]):
                        good = False
                    # planda zemin yok (keep): agacin zemin seviyesindeyse toprak blogunu da plana yaz (bitki havada kalmasin)
                    if good and s == (0, -1, 0) and cls[qi, qj, qk] == 0 and cur[qi, qj, qk] == 0 and q[1] <= self.gy(q[0], q[2]):
                        want[qi, qj, qk] = b.pid("grass_block")
                        cls[qi, qj, qk] = 4
                        ok[qi, qj, qk] = True
                else:
                    good = True
                if not good:
                    ok[i, j, k] = False
        ids = np.where(ok, want, 0).astype(np.int32)
        b.put_ids(X0, Y0, Z0, ids)
        for c, (st, s) in extra.items():
            if b.get_id(*c) in (0, 1):
                b.set(*c, st)
        # info
        nz = np.nonzero(ids)
        if len(nz[0]):
            lo = (int(nz[2].min()) + X0, int(nz[0].min()) + Y0, int(nz[1].min()) + Z0)
            hi = (int(nz[2].max()) + X0, int(nz[0].max()) + Y0, int(nz[1].max()) + Z0)
        else:
            lo = hi = (self.x, self.y, self.z)
        lm = (ids > 0) & (cls == 2)
        cx = self.spine[0][0] if self.spine else self.x + 0.5
        cz = self.spine[0][2] if self.spine else self.z + 0.5
        rad = 0.0
        if lm.any():
            _, zz, xx = np.nonzero(lm)
            rad = float(np.sqrt((xx + X0 + 0.5 - cx) ** 2 + (zz + Z0 + 0.5 - cz) ** 2).max())
        return {"height": hi[1] - self.y, "top": hi[1], "radius": round(rad, 1), "bbox": [list(lo), list(hi)],
                "logs": int(((ids > 0) & (cls == 1)).sum()), "leaves": int(lm.sum()),
                "trunk": sorted({(c[0], c[2]) for c in self.trunk_cells if c[1] == self.y + 1})}


# ============================================================================ decoration recipes
def _p_vines(t, prob, maxlen, minlen=1):
    leaf = t.occ == 2
    rng = random.Random(t.seed + 401)
    for (dx, dz, _name) in _DIRS4:
        for c in t._cands(leaf, (dx, dz), 410 + dx * 3 + dz * 7, prob):
            face = _OPP[_name]
            st = f"vine[{face}=true]"
            t.strand_down(c, lambda k, n, st=st: st, rng.randint(minlen, maxlen), (-dx, 0, -dz))


def _p_trunk_vines(t, prob, maxlen):
    rng = random.Random(t.seed + 433)
    cells = [c for c in t.trunk_cells if c[1] >= t.y + 2]
    for c in cells:
        for (dx, dz, name) in _DIRS4:
            q = (c[0] + dx, c[1], c[2] + dz)
            if rng.random() < prob and t.empty(q) and t.occ_at((q[0], q[1] + 1, q[2])) != 1:
                face = _OPP[name]
                st = f"vine[{face}=true]"
                n = rng.randint(1, maxlen)
                for k in range(n):
                    qq = (q[0], q[1] - k, q[2])
                    under = (c[0], c[1] - k, c[2])
                    if not t.empty(qq) or qq[1] <= t.gy(qq[0], qq[2]):
                        break
                    if t.occ_at(under) == 1:
                        t.deco[qq] = (st, (-dx, 0, -dz))
                    else:
                        t.deco[qq] = (st, (0, 1, 0))


def _p_cocoa(t, count, hmin=2, hmax=9):
    rng = random.Random(t.seed + 457)
    cells = [c for c in t.trunk_cells if t.y + hmin <= c[1] <= t.y + hmax and "jungle" in t.logs.get(c, "")]
    rng.shuffle(cells)
    placed = 0
    for c in cells:
        if placed >= count:
            break
        dirs = list(_DIRS4)
        rng.shuffle(dirs)
        for (dx, dz, name) in dirs:
            q = (c[0] + dx, c[1], c[2] + dz)
            if t.empty(q):
                t.deco[q] = (f"cocoa[age={rng.randint(1, 2)},facing={_OPP[name]}]", (-dx, 0, -dz))
                placed += 1
                break


def _p_hang_moss(t, prob, maxlen):
    rng = random.Random(t.seed + 471)
    leaf = t.occ >= 1
    for c in t._cands(leaf, "down", 472, prob):
        t.strand_down(c, lambda k, n: "pale_hanging_moss[tip=true]" if k == n - 1 else "pale_hanging_moss[tip=false]",
                      rng.randint(1, maxlen), (0, 1, 0), minfree=2)


def _p_propagules(t, prob):
    rng = random.Random(t.seed + 487)
    m = t.leafid == (1 + next((i for i, e in enumerate(t.leaves) if e[0] == "mangrove_leaves"), -99))
    for c in t._cands(m & (t.occ == 2), "down", 488, prob):
        if c[1] > t.gy(c[0], c[2]) + 1:
            t.deco[c] = (f"mangrove_propagule[hanging=true,age={rng.randint(0, 4)}]", (0, 1, 0))


def _p_moss_top(t, prob, state="moss_carpet"):
    rng = random.Random(t.seed + 499)
    for c, st in list(t.logs.items()):
        if ("axis=x" in st or "axis=z" in st or "roots" in st or "_wood" in st) and c not in t.trunk_cells:
            q = (c[0], c[1] + 1, c[2])
            if rng.random() < prob and t.empty(q):
                t.deco[q] = (state, (0, -1, 0))


def _p_curtains(t, p_edge, p_inner, maxlen):
    """Weeping curtains: leaf strands hanging from the crown underside, mostly on its outer ring."""
    X0, Y0, Z0 = t.box
    occ = t.occ
    leaf = occ == 2
    free = (occ == 0) & ~t.under
    cand = np.zeros_like(leaf)
    cand[1:] = leaf[1:] & free[:-1]
    ys, zs, xs = np.nonzero(cand)
    if not len(ys):
        return
    cx = t.spine[0][0] if t.spine else t.x + 0.5
    cz = t.spine[0][2] if t.spine else t.z + 0.5
    d = np.sqrt((xs + X0 + 0.5 - cx) ** 2 + (zs + Z0 + 0.5 - cz) ** 2)
    R = float(d.max()) or 1.0
    rs = np.random.default_rng(t.seed + 521)
    p = np.where(d > 0.5 * R, p_edge, p_inner)
    sel = rs.random(len(ys)) < p
    rng = random.Random(t.seed + 523)
    for y, z, x in zip(ys[sel], zs[sel], xs[sel]):
        src = t.leafid[y, z, x]
        wx, wz = int(x) + X0, int(z) + Z0
        g = t.gy(wx, wz)
        n = int(rng.randint(2, maxlen) * rng.uniform(0.5, 1.0) + 0.5)
        for k in range(1, n + 1):
            q = (wx, int(y) + Y0 - k, wz)
            if q[1] <= g + 1 or not t.empty(q):
                break
            i = q[1] - Y0
            occ[i, z, x] = 2
            t.leafid[i, z, x] = src


def _p_drips(t, prob, maxlen, li=1):
    """Leaves hanging under the crown edge (cherry, willow curtains)."""
    rng = random.Random(t.seed + 503)
    leaf = t.occ == 2
    X0, Y0, Z0 = t.box
    for c in t._cands(leaf, "down", 504, prob):
        g = t.gy(c[0], c[2])
        n = rng.randint(1, maxlen)
        src = t.leafid[c[1] + 1 - Y0, c[2] - Z0, c[0] - X0]
        for k in range(n):
            q = (c[0], c[1] - k, c[2])
            if q[1] <= g + 2 or not t.empty(q):
                break
            i, j, kk = q[1] - Y0, q[2] - Z0, q[0] - X0
            t.occ[i, j, kk] = 2
            t.leafid[i, j, kk] = src if src > 0 else li


# ============================================================================ species generators
def _broadleaf(t, C):
    rng = t.rng
    h = rng.randint(*C["h"])
    T = C["trunk"]
    ttop = t.y + max(2, int(round(h * T["top"])))
    lean = None
    if T.get("lean"):
        a = rng.uniform(0, 2 * math.pi)
        m = rng.uniform(*T["lean"]) * h
        lean = (math.cos(a) * m, math.sin(a) * m)
    sp = t.trunk(ttop, T["r0"], T.get("r1", 0.5), flare=T.get("flare", 0.0), lean=lean, wobble=T.get("wobble", 0.0),
                 even=T.get("even", False), bark=T.get("bark", 0.0))
    L = C["limbs"]
    n = rng.randint(*L["n"])
    az0 = rng.uniform(0, 2 * math.pi)
    tips = []
    for k in range(n):
        f = L["at"][0] + (L["at"][1] - L["at"][0]) * (k + rng.random()) / n
        p0 = t.at(min(1.0, f / max(1e-6, T["top"])))
        a = az0 + k * 2.39996 + rng.uniform(-0.3, 0.3)
        el = math.radians(rng.uniform(*L["el"]))
        ln = rng.uniform(*L["len"]) * h
        tips += t.grow(p0, _dir(a, el), ln, L.get("r", 0.5), L.get("depth", 1), L)
    lo = C.get("low")
    if lo and rng.random() < lo.get("p", 1.0):
        P = dict(L)
        P.update(lo.get("P", {}))
        for _ in range(rng.randint(*lo["n"])):
            f = rng.uniform(*lo["at"])
            p0 = t.at(min(1.0, f / max(1e-6, T["top"])))
            a = rng.uniform(0, 2 * math.pi)
            tips += t.grow(p0, _dir(a, math.radians(rng.uniform(*lo["el"]))), rng.uniform(*lo["len"]) * h,
                           lo.get("r", 0.5), lo.get("depth", 1), P)
    if C.get("leader", True):
        ll = rng.uniform(*C.get("leader_len", (0.18, 0.28))) * h
        d = _unit(rng.uniform(-0.2, 0.2), 1.0, rng.uniform(-0.2, 0.2))
        P = dict(L)
        P["up"] = 0.25
        tips += t.grow(sp[-1], d, ll, max(0.5, T.get("r1", 0.5) * 0.9), C.get("leader_depth", 0), P)
    B = C.get("blob")
    if B:
        for tp in tips:
            r = rng.uniform(*B["r"]) * (1.0 if tp.depth == 0 else B.get("inner", 0.85))
            t.cluster((tp.p[0], tp.p[1] + B.get("lift", 0.5), tp.p[2]), r, flat=B.get("flat", 0.6),
                      under=B.get("under", 0.35), lumps=rng.randint(*B.get("lumps", (1, 2))), dens=B.get("dens", 0.82),
                      rag=B.get("rag", 1.15))
        mid = B.get("mid", 0.0)
        for (p, d, dep) in t.mids:
            if rng.random() < mid:
                r = rng.uniform(*B["r"]) * B.get("mid_r", 0.6)
                t.blob(p, r, r * B.get("flat", 0.6), r * B.get("under", 0.35), B.get("dens", 0.82),
                       rag=B.get("rag", 1.15))
    R = C.get("roots")
    if R:
        t.roots(rng.randint(*R["n"]), R["len"], r0=R.get("r", 0.5), rise=R.get("rise", 1.0),
                start_r=max(0.5, T["r0"] * 0.8 + (0.5 if T.get("even") else 0.0)))
    return h, tips


_OAK = {
    "small": dict(h=(5, 7), trunk=dict(top=0.55, r0=0.5, wobble=0.1),
                  limbs=dict(n=(2, 4), at=(0.42, 0.6), el=(30, 60), len=(0.28, 0.4), depth=0, seg=1.5, wiggle=0.2),
                  leader_len=(0.2, 0.3), blob=dict(r=(1.8, 2.3), flat=0.85, under=0.5, lumps=(1, 1), dens=0.85),
                  roots=None),
    "medium": dict(h=(9, 12), trunk=dict(top=0.5, r0=0.5, flare=0.45, wobble=0.25),
                   limbs=dict(n=(4, 6), at=(0.36, 0.6), el=(28, 65), len=(0.32, 0.46), depth=1, forks=1, fork_p=0.7,
                              fork_ang=(25, 45), fork_at=(0.5, 0.8), child_len=(0.5, 0.75), seg=2.0, wiggle=0.22,
                              up=0.06),
                   low=dict(p=0.5, n=(1, 1), at=(0.28, 0.36), el=(8, 22), len=(0.34, 0.44), depth=0),
                   leader_len=(0.28, 0.38),
                   blob=dict(r=(2.3, 2.9), flat=0.74, under=0.44, lumps=(1, 2), dens=0.82, mid=0.22, mid_r=0.65),
                   roots=dict(n=(2, 4), len=(1.5, 3.0), rise=0.5)),
    "large": dict(h=(14, 18), trunk=dict(top=0.42, r0=1.45, r1=0.8, flare=0.9, wobble=0.3, bark=0.3),
                  limbs=dict(n=(4, 6), at=(0.3, 0.52), el=(18, 48), len=(0.42, 0.56), r=0.95, taper=0.5, depth=2,
                             forks=(1, 2), fork_p=0.85, fork_ang=(22, 42), fork_at=(0.45, 0.85),
                             child_len=(0.5, 0.72), seg=2.4, wiggle=0.2, up=0.06),
                  low=dict(p=0.7, n=(1, 2), at=(0.2, 0.3), el=(4, 18), len=(0.4, 0.5), r=0.75, depth=1),
                  leader_len=(0.22, 0.32), leader_depth=1,
                  blob=dict(r=(2.6, 3.3), flat=0.64, under=0.38, lumps=(2, 2), dens=0.82, mid=0.16),
                  roots=dict(n=(4, 6), len=(2.5, 4.5), rise=1.0, r=0.6)),
    "huge": dict(h=(20, 26), trunk=dict(top=0.36, r0=2.1, r1=1.25, flare=1.2, wobble=0.35, bark=0.5),
                 limbs=dict(n=(5, 7), at=(0.24, 0.46), el=(10, 40), len=(0.46, 0.6), r=1.25, taper=0.42, depth=2,
                            forks=(2, 3), fork_p=1.0, fork_ang=(22, 40), fork_at=(0.4, 0.85), child_len=(0.48, 0.72),
                            seg=2.6, wiggle=0.2, up=0.08),
                 low=dict(p=0.85, n=(1, 3), at=(0.18, 0.28), el=(0, 15), len=(0.42, 0.52), r=0.95, depth=1),
                 leader_len=(0.28, 0.38), leader_depth=1,
                 blob=dict(r=(3.0, 3.8), flat=0.6, under=0.34, lumps=(2, 3), dens=0.82, mid=0.14),
                 roots=dict(n=(6, 8), len=(4.0, 7.0), rise=2.0, r=1.0)),
}


def _g_oak(t, size):
    _broadleaf(t, _OAK[size])
    if size in ("large", "huge"):
        t.post.append((_p_moss_top, 0.22 if size == "huge" else 0.08))
    t.cover_spec = (_CROWN["oak"][SIZES.index(size)] * 0.8,
                    [("coarse_dirt", 0.04), ("rooted_dirt", 0.03)],
                    [(_litter, 0.06), ("short_grass", 0.08), ("fern", 0.03)])


def _g_dark_oak(t, size):
    C = {
        "small": dict(h=(6, 8), trunk=dict(top=0.6, r0=0.75, r1=0.75, even=True),
                      limbs=dict(n=(3, 4), at=(0.45, 0.7), el=(15, 40), len=(0.32, 0.45), depth=0, seg=1.6),
                      leader_len=(0.12, 0.2),
                      blob=dict(r=(2.4, 2.9), flat=0.6, under=0.42, lumps=(1, 2), dens=0.92, mid=0.15),
                      roots=dict(n=(2, 3), len=(1.0, 2.0), rise=0.3)),
        "medium": dict(h=(9, 12), trunk=dict(top=0.6, r0=0.75, r1=0.75, even=True),
                       limbs=dict(n=(4, 6), at=(0.42, 0.72), el=(10, 38), len=(0.34, 0.48), depth=1, forks=1,
                                  fork_p=0.6, fork_ang=(20, 40), seg=2.0, wiggle=0.18, up=0.04),
                       leader_len=(0.12, 0.2),
                       blob=dict(r=(2.7, 3.3), flat=0.56, under=0.4, lumps=(1, 2), dens=0.92, mid=0.2),
                       roots=dict(n=(3, 5), len=(1.5, 3.0), rise=0.6)),
        "large": dict(h=(13, 16), trunk=dict(top=0.58, r0=0.75, r1=0.75, even=True, flare=0.5),
                      limbs=dict(n=(5, 7), at=(0.4, 0.7), el=(8, 34), len=(0.36, 0.5), r=0.6, depth=1, forks=(1, 2),
                                 fork_p=0.8, fork_ang=(20, 40), seg=2.2, wiggle=0.18, up=0.04),
                      leader_len=(0.12, 0.2),
                      blob=dict(r=(2.9, 3.6), flat=0.55, under=0.4, lumps=(2, 2), dens=0.92, mid=0.2),
                      roots=dict(n=(4, 6), len=(2.0, 3.5), rise=0.9, r=0.6)),
        "huge": dict(h=(18, 23), trunk=dict(top=0.52, r0=1.6, r1=1.1, flare=0.9, bark=0.5),
                     limbs=dict(n=(6, 8), at=(0.36, 0.66), el=(6, 32), len=(0.38, 0.5), r=1.0, taper=0.5, depth=2,
                                forks=2, fork_p=1.0, fork_ang=(20, 38), seg=2.5, wiggle=0.18, up=0.05),
                     leader_len=(0.12, 0.2), leader_depth=1,
                     blob=dict(r=(3.3, 4.1), flat=0.54, under=0.38, lumps=(2, 3), dens=0.92, mid=0.2),
                     roots=dict(n=(6, 8), len=(3.0, 5.5), rise=1.4, r=0.8)),
    }[size]
    _broadleaf(t, C)
    t.cover_spec = (_CROWN["dark_oak"][SIZES.index(size)] * 0.85,
                    [("podzol", 0.18), ("coarse_dirt", 0.08), ("rooted_dirt", 0.04)],
                    [(_litter, 0.14), ("brown_mushroom", 0.035), ("red_mushroom", 0.02), ("fern", 0.03)])


def _g_pale_oak(t, size):
    C = {
        "small": dict(h=(7, 9), trunk=dict(top=0.6, r0=0.75, r1=0.75, even=True),
                      limbs=dict(n=(3, 4), at=(0.45, 0.72), el=(15, 45), len=(0.3, 0.42), depth=0, seg=1.6,
                                 wiggle=0.35),
                      leader_len=(0.12, 0.2),
                      blob=dict(r=(2.2, 2.7), flat=0.6, under=0.42, lumps=(1, 2), dens=0.72, mid=0.15, rag=1.4),
                      roots=dict(n=(2, 3), len=(1.0, 2.0), rise=0.3)),
        "medium": dict(h=(10, 13), trunk=dict(top=0.58, r0=0.75, r1=0.75, even=True),
                       limbs=dict(n=(4, 6), at=(0.4, 0.72), el=(12, 45), len=(0.32, 0.46), depth=1, forks=1,
                                  fork_p=0.7, fork_ang=(25, 50), seg=1.9, wiggle=0.38, up=0.03),
                       leader_len=(0.12, 0.2),
                       blob=dict(r=(2.4, 3.0), flat=0.58, under=0.42, lumps=(1, 2), dens=0.72, mid=0.2, rag=1.4),
                       roots=dict(n=(3, 5), len=(1.5, 3.0), rise=0.6)),
        "large": dict(h=(14, 17), trunk=dict(top=0.55, r0=0.75, r1=0.75, even=True, flare=0.5),
                      limbs=dict(n=(5, 7), at=(0.38, 0.72), el=(10, 42), len=(0.34, 0.48), r=0.6, depth=1, forks=2,
                                 fork_p=0.8, fork_ang=(25, 50), seg=2.1, wiggle=0.38, up=0.03),
                      leader_len=(0.12, 0.2),
                      blob=dict(r=(2.6, 3.3), flat=0.56, under=0.42, lumps=(2, 2), dens=0.72, mid=0.2, rag=1.4),
                      roots=dict(n=(4, 6), len=(2.0, 3.5), rise=0.9, r=0.6)),
        "huge": dict(h=(19, 24), trunk=dict(top=0.5, r0=1.5, r1=1.05, flare=0.9, bark=0.6, wobble=0.2),
                     limbs=dict(n=(6, 8), at=(0.34, 0.66), el=(8, 40), len=(0.36, 0.48), r=1.0, taper=0.5, depth=2,
                                forks=2, fork_p=1.0, fork_ang=(25, 48), seg=2.4, wiggle=0.36, up=0.04),
                     leader_len=(0.12, 0.2), leader_depth=1,
                     blob=dict(r=(2.9, 3.7), flat=0.55, under=0.42, lumps=(2, 3), dens=0.72, mid=0.2, rag=1.4),
                     roots=dict(n=(6, 8), len=(3.0, 5.5), rise=1.4, r=0.8)),
    }[size]
    _broadleaf(t, C)
    t.post.append((_p_hang_moss, 0.07, 3 if size in ("small", "medium") else 4))
    t.cover_spec = (_CROWN["pale_oak"][SIZES.index(size)] * 0.9,
                    [("pale_moss_block", 0.45), ("coarse_dirt", 0.04)],
                    [("pale_moss_carpet", 0.4), ("closed_eyeblossom", 0.02), (_litter, 0.05)])


def _g_willow(t, size):
    C = {
        "small": dict(h=(7, 9), trunk=dict(top=0.5, r0=0.5, flare=0.4, wobble=0.2),
                      limbs=dict(n=(3, 4), at=(0.42, 0.55), el=(38, 62), len=(0.4, 0.52), depth=0, seg=1.5,
                                 up=-0.14, min_el=-0.6, wiggle=0.15),
                      leader_len=(0.18, 0.26),
                      blob=dict(r=(1.9, 2.4), flat=0.55, under=0.4, lumps=(1, 1), dens=0.8, lift=0.3),
                      roots=dict(n=(2, 3), len=(1.0, 2.0), rise=0.4)),
        "medium": dict(h=(10, 13), trunk=dict(top=0.48, r0=0.95, r1=0.55, flare=0.6, wobble=0.3, lean=(0.04, 0.1)),
                       limbs=dict(n=(4, 6), at=(0.4, 0.52), el=(38, 62), len=(0.4, 0.52), depth=1, forks=1,
                                  fork_p=0.6, seg=1.9, up=-0.13, min_el=-0.6, fork_ang=(20, 40), wiggle=0.15),
                       leader_len=(0.18, 0.26),
                       blob=dict(r=(2.1, 2.6), flat=0.55, under=0.4, lumps=(1, 2), dens=0.8, lift=0.3, mid=0.25,
                                 mid_r=0.6),
                       roots=dict(n=(3, 5), len=(2.0, 3.0), rise=0.7)),
        "large": dict(h=(13, 17), trunk=dict(top=0.46, r0=1.3, r1=0.75, flare=0.8, wobble=0.3, bark=0.25,
                                             lean=(0.03, 0.08)),
                      limbs=dict(n=(5, 7), at=(0.38, 0.5), el=(36, 60), len=(0.42, 0.55), r=0.8, taper=0.6, depth=1,
                                 forks=2, fork_p=0.8, seg=2.2, up=-0.12, min_el=-0.6, fork_ang=(20, 40), wiggle=0.15),
                      leader_len=(0.2, 0.28), leader_depth=1,
                      blob=dict(r=(2.3, 2.9), flat=0.55, under=0.4, lumps=(1, 2), dens=0.8, lift=0.3, mid=0.25,
                                mid_r=0.6),
                      roots=dict(n=(4, 6), len=(2.5, 4.0), rise=1.0, r=0.6)),
        "huge": dict(h=(17, 22), trunk=dict(top=0.44, r0=1.8, r1=1.0, flare=1.0, wobble=0.35, bark=0.5,
                                            lean=(0.03, 0.07)),
                     limbs=dict(n=(6, 8), at=(0.36, 0.48), el=(34, 58), len=(0.42, 0.55), r=1.0, taper=0.5, depth=2,
                                forks=2, fork_p=0.9, seg=2.4, up=-0.11, min_el=-0.6, fork_ang=(20, 38), wiggle=0.15),
                     leader_len=(0.2, 0.3), leader_depth=1,
                     blob=dict(r=(2.5, 3.1), flat=0.55, under=0.4, lumps=(1, 2), dens=0.8, lift=0.3, mid=0.25,
                               mid_r=0.6),
                     roots=dict(n=(6, 8), len=(3.0, 5.5), rise=1.4, r=0.8)),
    }[size]
    _broadleaf(t, C)
    ml = {"small": 6, "medium": 9, "large": 12, "huge": 15}[size]
    t.post.append((_p_curtains, 0.3, 0.03, ml))
    t.post.append((_p_vines, 0.1, max(3, ml - 2), 2))
    t.cover_spec = (_CROWN["willow"][SIZES.index(size)] * 0.8, [("moss_block", 0.06), ("mud", 0.04)],
                    [("short_grass", 0.14), ("fern", 0.05), ("blue_orchid", 0.015)])


def _g_cherry(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (5, 7), "medium": (8, 11), "large": (12, 15), "huge": (16, 20)}[size])
    r0 = {"small": 0.5, "medium": 0.5, "large": 0.9, "huge": 1.25}[size]
    ts = t.y + max(2, int(round(h * rng.uniform(0.32, 0.42))))
    sp = t.trunk(ts, r0, 0.5 if size != "huge" else 0.9, flare=0.4 if size != "small" else 0.0, wobble=0.15,
                 bark=0.3 if size == "huge" else 0.0)
    n = rng.randint(*{"small": (2, 3), "medium": (2, 3), "large": (3, 4), "huge": (3, 5)}[size])
    az0 = rng.uniform(0, 2 * math.pi)
    br = {"small": 0.5, "medium": 0.5, "large": 0.75, "huge": 1.0}[size]
    rr = {"small": (2.3, 2.8), "medium": (2.8, 3.4), "large": (3.2, 3.9), "huge": (3.8, 4.6)}[size]
    P = dict(seg=1.8, wiggle=0.12, up=0.05, taper=0.6, min_el=0.0)
    for i in range(n):
        a = az0 + i * 2 * math.pi / n + rng.uniform(-0.35, 0.35)
        p0 = sp[-1 - rng.randint(0, min(1, len(sp) - 1))]
        # arching limb: steep rise, then out, slight upturn at the tip
        l1 = h * rng.uniform(0.2, 0.28)
        e1 = math.radians(rng.uniform(52, 68))
        p1 = (p0[0] + math.cos(a) * math.cos(e1) * l1, p0[1] + math.sin(e1) * l1,
              p0[2] + math.sin(a) * math.cos(e1) * l1)
        t.tube(p0, p1, br, max(0.5, br * 0.8))
        l2 = h * rng.uniform(0.28, 0.38)
        e2 = math.radians(rng.uniform(6, 20))
        a2 = a + rng.uniform(-0.25, 0.25)
        tips = t.grow(p1, _dir(a2, e2), l2, max(0.5, br * 0.75), 1 if size in ("large", "huge") else 0,
                      dict(P, forks=1, fork_ang=(25, 40), fork_at=(0.5, 0.8)))
        c = tuple(math.floor(v) for v in p1)
        if c in t.logs and c not in t.trunk_cells:
            t.logs[c] = t.wood_st
        for tp in tips:
            r = rng.uniform(*rr) * (1.0 if tp.depth == 0 else 0.8)
            t.cluster((tp.p[0], tp.p[1] + 0.7, tp.p[2]), r, flat=0.5, under=0.3, lumps=rng.randint(2, 3), dens=0.88,
                      rag=1.1)
        if size in ("large", "huge"):
            r = rng.uniform(*rr) * 0.5
            t.cluster((p1[0], p1[1] + 0.8, p1[2]), r, flat=0.55, under=0.35, lumps=1, dens=0.88)
    r = rng.uniform(*rr) * 0.85
    top = (sp[-1][0] + rng.uniform(-0.6, 0.6), sp[-1][1] + h * 0.3, sp[-1][2] + rng.uniform(-0.6, 0.6))
    t.tube(sp[-1], top, 0.5)
    t.cluster((top[0], top[1] + 0.6, top[2]), r, flat=0.55, under=0.35, lumps=2, dens=0.88, rag=1.1)
    t.post.append((_p_drips, 0.2, 2, 1))
    t.cover_spec = (_CROWN["cherry"][SIZES.index(size)] * 0.95, [],
                    [(_petals, 0.3), ("short_grass", 0.05)])


def _g_birch(t, size):
    rng = t.rng
    stems = [(0.0, 0.0, 1.0)]
    if size == "huge":
        stems = [(0.0, 0.0, 1.0), (1.0, 0.0, rng.uniform(0.75, 0.9)), (0.0, 1.0, rng.uniform(0.6, 0.85))]
        if rng.random() < 0.5:
            stems.append((1.0, 1.0, rng.uniform(0.5, 0.7)))
    hb = rng.randint(*{"small": (6, 8), "medium": (9, 13), "large": (14, 18), "huge": (17, 22)}[size])
    rmax = {"small": 2.0, "medium": 2.4, "large": 2.7, "huge": 2.4}[size]
    for si, (ox, oz, hf) in enumerate(stems):
        h = max(5, int(round(hb * hf)))
        cx, cz = t.x + 0.5 + ox, t.z + 0.5 + oz
        lean = None
        if len(stems) > 1:
            a = math.atan2(oz - 0.4, ox - 0.4) + rng.uniform(-0.4, 0.4)
            m = h * rng.uniform(0.15, 0.24)
            lean = (math.cos(a) * m, math.sin(a) * m)
        elif rng.random() < 0.6:
            a = rng.uniform(0, 2 * math.pi)
            m = h * rng.uniform(0.03, 0.09)
            lean = (math.cos(a) * m, math.sin(a) * m)
        top = t.y + h - 1
        sp = t.trunk(top, 0.5, 0.5, wobble=0.18, lean=lean, cx=cx, cz=cz)
        cb = int(len(sp) * rng.uniform(0.42, 0.52))
        y = cb
        side = rng.uniform(0, 2 * math.pi)
        while y < len(sp) - 1:
            f = (y - cb) / max(1, len(sp) - 1 - cb)
            r = rmax * (0.75 + 0.35 * math.sin(math.pi * min(1.0, f * 0.9 + 0.1)))
            side += 2.39996 + rng.uniform(-0.4, 0.4)
            p0 = sp[y]
            bl = rng.uniform(0.8, 2.0) * (1.15 - 0.5 * f)
            tips = t.grow(p0, _dir(side, math.radians(rng.uniform(25, 50))), bl, 0.5, 0, dict(seg=1.3, wiggle=0.1))
            for tp in tips:
                t.cluster(tp.p, r * rng.uniform(0.8, 1.0), flat=0.9, under=0.65, lumps=1, dens=0.82, rag=1.15)
            y += rng.randint(1, 2)
        t.cluster((sp[-1][0], sp[-1][1] + 0.8, sp[-1][2]), rmax * 0.8, flat=1.0, under=0.65, lumps=1, dens=0.82,
                  rag=1.15)
        # bare twigs on the lower trunk
        for _ in range(rng.randint(0, 2) if size != "small" else 0):
            yi = rng.randint(2, max(2, cb - 1))
            if yi < len(sp):
                a = rng.uniform(0, 2 * math.pi)
                p0 = sp[yi]
                t.tube(p0, (p0[0] + math.cos(a) * 1.2, p0[1] + 0.4, p0[2] + math.sin(a) * 1.2))
    t.cover_spec = (_CROWN["birch"][SIZES.index(size)], [], [(_litter, 0.06), ("short_grass", 0.1),
                                                             (_wildflowers, 0.04), ("fern", 0.02)])


def _g_spruce(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (7, 10), "medium": (12, 17), "large": (19, 26), "huge": (28, 38)}[size])
    even = size == "huge"
    top = t.y + h - 1
    if even:
        sp = t.trunk(top, 0.75, 0.75, flare=0.7, even=True)
    else:
        sp = t.trunk(top, 0.5 if size != "large" else 0.95, 0.5, flare=0.3 if size == "large" else 0.0, wobble=0.12)
    t.reach = 9
    cbf = {"small": 0.16, "medium": 0.18, "large": 0.24, "huge": 0.3}[size]
    cb = t.y + 1 + max(1, int(round(h * cbf)))
    Rmax = min(9.0, h * rng.uniform(0.23, 0.28)) + (0.5 if even else 0.0)
    span = (top + 1) - cb
    tiers = []
    y = cb
    while y <= top - 1:
        P = 2 if size == "small" else rng.choice((2, 3, 3))
        tiers.append((y, P))
        y += P
    for (yb, P) in tiers:
        f = (yb - cb) / max(1, span)
        R = max(1.3, Rmax * (1.0 - f) ** 1.05 + 0.7)
        p = t.at(yb, absolute=True)
        t.disc(p[0], yb, p[2], R, rag=0.28)                       # tier skirt (widest)
        t.disc(p[0], yb + 1, p[2], max(1.05, R * 0.62), rag=0.25)
        if P == 3:
            t.disc(p[0], yb + 2, p[2], max(1.0, R * 0.4), rag=0.2)
        if R > 2.4:
            t.disc(p[0], yb - 1, p[2], R * 0.95, rag=0.3, hole=R * 0.6)   # drooping tips
        if R > 2.8 and yb < top - 2:
            nb = rng.randint(3, 5)
            a0 = rng.uniform(0, 2 * math.pi)
            for i in range(nb):
                a = a0 + i * 2 * math.pi / nb + rng.uniform(-0.3, 0.3)
                ln = R * rng.uniform(0.45, 0.65)
                t.tube((p[0], yb + 0.5, p[2]), (p[0] + math.cos(a) * ln, yb + 0.3 - 0.12 * ln, p[2] + math.sin(a) * ln))
    cx, cz = sp[-1][0], sp[-1][2]
    t.disc(cx, top, cz, 1.05, rag=0.15)
    for k in range(1, 3):  # leader spike
        t.leaf((math.floor(cx), top + k, math.floor(cz)))
    if size in ("large", "huge"):
        for _ in range(rng.randint(2, 5)):  # dead stubs on the bare trunk
            yi = rng.randint(2, max(2, cb - t.y - 2))
            pp = t.at(t.y + yi, absolute=True)
            a = rng.uniform(0, 2 * math.pi)
            t.tube((pp[0], pp[1], pp[2]), (pp[0] + math.cos(a) * (1.6 if even else 1.2), pp[1] - 0.3,
                                           pp[2] + math.sin(a) * (1.6 if even else 1.2)))
        t.roots(rng.randint(3, 5), (1.5, 3.0) if size == "large" else (2.5, 4.5), rise=0.6,
                start_r=0.9 if even else 0.6)
    t.cover_spec = (Rmax * 0.9, [("podzol", 0.35), ("coarse_dirt", 0.08)],
                    [("fern", 0.12), (lambda r: ("large_fern[half=lower]", "large_fern[half=upper]"), 0.03),
                     ("sweet_berry_bush[age=3]", 0.015), ("brown_mushroom", 0.01)])


def _g_pine(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (8, 11), "medium": (13, 18), "large": (19, 25), "huge": (26, 33)}[size])
    even = size == "huge"
    top = t.y + h - 1
    if even:
        sp = t.trunk(top, 0.75, 0.75, flare=0.6, even=True)
    else:
        sp = t.trunk(top, 0.5 if size != "large" else 0.95, 0.5, flare=0.3 if size == "large" else 0.0, wobble=0.35)
    t.reach = 8
    cb = int(len(sp) * rng.uniform(0.58, 0.68))
    n = rng.randint(*{"small": (3, 4), "medium": (5, 7), "large": (6, 8), "huge": (8, 11)}[size])
    a = rng.uniform(0, 2 * math.pi)
    rpad = {"small": 1.9, "medium": 2.4, "large": 2.9, "huge": 3.3}[size]
    lmax = {"small": 1.4, "medium": 2.6, "large": 3.4, "huge": 4.6}[size]
    deep = 1 if size in ("large", "huge") else 0
    for i in range(n):
        f = i / max(1, n - 1)
        yi = cb + int(round(f * (len(sp) - 2 - cb)))
        p0 = sp[min(len(sp) - 1, yi)]
        a += 2.39996 + rng.uniform(-0.3, 0.3)
        ln = lmax * (1.0 - 0.45 * f) * rng.uniform(0.8, 1.15)
        tips = t.grow(p0, _dir(a, math.radians(rng.uniform(0, 18))), ln, 0.5, deep,
                      dict(seg=1.6, wiggle=0.15, up=0.04, forks=1, fork_p=0.5, fork_ang=(25, 40)))
        for tp in tips:
            r = rpad * (1.0 - 0.25 * f) * rng.uniform(0.85, 1.05) * (1.0 if tp.depth == 0 else 0.85)
            t.cluster((tp.p[0], tp.p[1] + 0.5, tp.p[2]), r, flat=0.5, under=0.3, lumps=2, dens=0.86, rag=1.15)
    t.cluster((sp[-1][0], sp[-1][1] + 0.5, sp[-1][2]), rpad * 0.9, flat=0.55, under=0.32, lumps=2, dens=0.86,
              rag=1.15)
    for _ in range(rng.randint(1, 4)):
        yi = rng.randint(3, max(3, cb - 2))
        pp = sp[min(len(sp) - 1, yi)]
        aa = rng.uniform(0, 2 * math.pi)
        t.tube(pp, (pp[0] + math.cos(aa) * 1.3, pp[1] + 0.2, pp[2] + math.sin(aa) * 1.3))
    if size in ("large", "huge"):
        t.roots(rng.randint(3, 5), (1.5, 3.5), rise=0.6, start_r=0.9 if even else 0.6)
    t.cover_spec = (rpad * 1.6, [("podzol", 0.25), ("coarse_dirt", 0.1)],
                    [("fern", 0.08), ("short_grass", 0.06), ("sweet_berry_bush[age=3]", 0.01)])


def _g_jungle(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (6, 9), "medium": (13, 18), "large": (20, 28), "huge": (30, 40)}[size])
    t.reach = 9
    tt = t.y + h - 3
    if size == "huge":
        sp = t.trunk(tt, 1.8, 1.0, flare=1.1, bark=0.45, wobble=0.15)
        rt = 1.8
    elif size == "large":
        sp = t.trunk(tt, 0.75, 0.75, flare=0.6, even=True)
        rt = 1.0
    else:
        sp = t.trunk(tt, 0.5, 0.5, flare=0.35 if size == "medium" else 0.0, wobble=0.25)
        rt = 0.5
    cx, cz = sp[0][0], sp[0][2]
    # buttress roots (fins of wood)
    if size in ("large", "huge"):
        nf = rng.randint(4, 6)
        a0 = rng.uniform(0, 2 * math.pi)
        for i in range(nf):
            a = a0 + i * 2 * math.pi / nf + rng.uniform(-0.3, 0.3)
            Lf = rng.uniform(3.0, 5.0) if size == "large" else rng.uniform(4.5, 7.0)
            Hf = rng.uniform(2.5, 4.0) if size == "large" else rng.uniform(4.0, 6.5)
            x0, z0 = cx + math.cos(a) * (rt - 0.2), cz + math.sin(a) * (rt - 0.2)
            x1, z1 = cx + math.cos(a) * (rt + Lf), cz + math.sin(a) * (rt + Lf)
            for (c, tp) in _traverse((x0, 0.5, z0), (x1, 0.5, z1)):
                g = t.gy(c[0], c[2])
                fh = int(round(Hf * (1.0 - tp) ** 1.5))
                for yy in range(g - 1, g + 1 + fh):
                    t.setlog((c[0], yy, c[2]), wood=True)
            t.roots(1, (1.5, 3.0), rise=0.2, start_r=rt + Lf, cx=cx, cz=cz, az0=a)
    elif size == "medium":
        t.roots(rng.randint(2, 4), (1.5, 2.5), rise=0.6, start_r=0.6)
    # crown branches
    n = rng.randint(*{"small": (2, 3), "medium": (3, 4), "large": (4, 5), "huge": (4, 6)}[size])
    a0 = rng.uniform(0, 2 * math.pi)
    rcan = {"small": (2.0, 2.6), "medium": (3.0, 3.8), "large": (3.8, 4.8), "huge": (4.8, 6.0)}[size]
    br = {"small": 0.5, "medium": 0.5, "large": 0.6, "huge": 0.95}[size]
    for i in range(n):
        p0 = t.at(rng.uniform(0.78, 0.97))
        a = a0 + i * 2 * math.pi / n + rng.uniform(-0.3, 0.3)
        ln = h * rng.uniform(0.18, 0.3)
        tips = t.grow(p0, _dir(a, math.radians(rng.uniform(12, 35))), ln, br, 1 if size in ("large", "huge") else 0,
                      dict(seg=2.2, wiggle=0.2, up=0.05, forks=1, fork_ang=(25, 40), taper=0.6))
        for tp in tips:
            r = rng.uniform(*rcan) * (1.0 if tp.depth == 0 else 0.8)
            t.cluster((tp.p[0], tp.p[1] + 0.6, tp.p[2]), r, flat=0.48, under=0.28, lumps=rng.randint(1, 2), dens=0.88,
                      rag=1.1)
    r = rng.uniform(*rcan) * 1.05
    t.cluster((sp[-1][0], sp[-1][1] + 1.5, sp[-1][2]), r, flat=0.52, under=0.32, lumps=2, dens=0.88, rag=1.1)
    # tufts along the trunk
    if size != "small":
        for _ in range(rng.randint(2, 5)):
            p0 = t.at(rng.uniform(0.35, 0.72))
            a = rng.uniform(0, 2 * math.pi)
            tips = t.grow(p0, _dir(a, math.radians(rng.uniform(15, 40))), rng.uniform(1.8, 3.2) + rt, 0.5, 0,
                          dict(seg=1.5, wiggle=0.15))
            for tp in tips:
                rr = rng.uniform(1.6, 2.4)
                t.blob(tp.p, rr, rr * 0.6, rr * 0.4, 0.9)
    vp, vl = {"small": (0.06, 3), "medium": (0.09, 6), "large": (0.13, 10), "huge": (0.15, 14)}[size]
    t.post.append((_p_vines, vp, vl, 2))
    t.post.append((_p_trunk_vines, 0.22 if size in ("large", "huge") else 0.1, 6))
    t.post.append((_p_cocoa, {"small": 1, "medium": 2, "large": 4, "huge": 6}[size]))
    t.cover_spec = (rcan[1] * 1.2, [("rooted_dirt", 0.03)],
                    [("fern", 0.15), (lambda r: ("large_fern[half=lower]", "large_fern[half=upper]"), 0.05),
                     ("short_grass", 0.08), ("bush", 0.03)])


def _g_acacia(t, size):
    rng = t.rng
    t.reach = 9
    ts = t.y + rng.randint(*{"small": (2, 3), "medium": (3, 4), "large": (4, 6), "huge": (5, 7)}[size])
    r0 = 1.05 if size == "huge" else (0.6 if size == "large" else 0.5)
    sp = t.trunk(ts, r0, 0.5, flare=0.35 if size in ("large", "huge") else 0.0)
    nfork = rng.randint(*{"small": (1, 2), "medium": (2, 2), "large": (2, 3), "huge": (3, 4)}[size])
    a0 = rng.uniform(0, 2 * math.pi)
    Rc = {"small": (2.6, 3.2), "medium": (3.4, 4.2), "large": (4.2, 5.2), "huge": (5.0, 6.2)}[size]
    bl = {"small": (2, 3), "medium": (2, 4), "large": (3, 5), "huge": (4, 6)}[size]
    top = sp[-1]
    for i in range(nfork):
        a = a0 + i * 2 * math.pi / nfork + rng.uniform(-0.5, 0.5)
        ln = rng.randint(*bl) * (1.0 if i == 0 else rng.uniform(0.6, 0.9))
        rise = rng.uniform(0.8, 1.2)
        start = top if i == 0 or rng.random() < 0.5 else sp[max(0, len(sp) - 2)]
        p1 = (start[0] + math.cos(a) * ln, start[1] + ln * rise, start[2] + math.sin(a) * ln)
        t.tube(start, p1, 0.5)
        up = rng.randint(0, 2)
        p2 = (p1[0], p1[1] + up, p1[2])
        if up:
            t.tube(p1, p2, 0.5, axis="y")
        R = rng.uniform(*Rc) * (1.0 if i == 0 else 0.85)
        yc = math.floor(p2[1]) + 1
        t.disc(p2[0], yc, p2[2], R, rag=0.22)
        t.disc(p2[0], yc + 1, p2[2], R * rng.uniform(0.5, 0.62), rag=0.25)
        if size in ("large", "huge"):
            t.disc(p2[0], yc - 1, p2[2], R * 0.35, rag=0.2)
        if size != "small" and rng.random() < 0.6:  # a short side branch with a small pad
            b2 = a + rng.choice((-1, 1)) * rng.uniform(0.6, 1.1)
            l2 = rng.uniform(1.5, 3.0)
            mid = (start[0] + (p1[0] - start[0]) * 0.5, start[1] + (p1[1] - start[1]) * 0.5,
                   start[2] + (p1[2] - start[2]) * 0.5)
            p3 = (mid[0] + math.cos(b2) * l2, mid[1] + l2 * 0.4, mid[2] + math.sin(b2) * l2)
            t.tube(mid, p3, 0.5)
            r3 = R * rng.uniform(0.45, 0.6)
            t.disc(p3[0], math.floor(p3[1]) + 1, p3[2], r3, rag=0.25)
            t.disc(p3[0], math.floor(p3[1]) + 2, p3[2], r3 * 0.5, rag=0.25)
    if size in ("large", "huge"):
        t.roots(rng.randint(3, 4), (1.5, 3.0), rise=0.4, start_r=0.6)
    t.cover_spec = (Rc[1], [("coarse_dirt", 0.12)], [("short_dry_grass", 0.12), ("tall_dry_grass", 0.04),
                                                    ("short_grass", 0.04)])


def _g_mangrove(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (6, 8), "medium": (9, 12), "large": (13, 16), "huge": (17, 22)}[size])
    hr = rng.randint(*{"small": (2, 3), "medium": (3, 4), "large": (4, 5), "huge": (5, 6)}[size])
    y0 = t.y + 1 + hr
    top = t.y + h - 2
    a = rng.uniform(0, 2 * math.pi)
    m = h * rng.uniform(0.05, 0.12)
    r0 = 1.0 if size == "huge" else 0.5
    sp = t.trunk(top, r0, 0.5, lean=(math.cos(a) * m, math.sin(a) * m), wobble=0.2, y0=y0, anchor=False)
    cx, cz = sp[0][0], sp[0][2]
    roots = "mangrove_roots"
    g = t.gy(cx, cz)
    for yy in range(g, y0):  # central root column under the trunk
        t.setraw((math.floor(cx), yy, math.floor(cz)), roots)
    t.setraw((math.floor(cx), g - 1, math.floor(cz)), "muddy_mangrove_roots[axis=y]")
    n = rng.randint(*{"small": (3, 5), "medium": (4, 6), "large": (5, 7), "huge": (7, 9)}[size])
    D = {"small": (1.8, 2.8), "medium": (2.2, 3.6), "large": (2.8, 4.6), "huge": (3.6, 6.0)}[size]
    a0 = rng.uniform(0, 2 * math.pi)
    for i in range(n):
        aa = a0 + i * 2 * math.pi / n + rng.uniform(-0.35, 0.35)
        dist = rng.uniform(*D)
        ys = y0 + rng.randint(-1, 2)
        p_s = sp[max(0, min(len(sp) - 1, ys - y0))]
        ex, ez = p_s[0] + math.cos(aa) * dist, p_s[2] + math.sin(aa) * dist
        ge = t.gy(ex, ez)
        mid = (p_s[0] + math.cos(aa) * dist * 0.55, ys + 0.5 - (ys - ge) * 0.25, p_s[2] + math.sin(aa) * dist * 0.55)
        t.tube((p_s[0], ys + 0.5, p_s[2]), mid, 0.5, state=roots)
        t.tube(mid, (ex, ge + 0.5, ez), 0.5, state=roots)
        t.setraw((math.floor(ex), ge - 1, math.floor(ez)), "muddy_mangrove_roots[axis=y]")
    nb = rng.randint(3, 5)
    a1 = rng.uniform(0, 2 * math.pi)
    rr = {"small": (2.0, 2.5), "medium": (2.4, 3.0), "large": (2.8, 3.4), "huge": (3.2, 3.9)}[size]
    for i in range(nb):
        p0 = t.at(rng.uniform(0.45, 0.85))
        ang = a1 + i * 2.39996 + rng.uniform(-0.3, 0.3)
        tips = t.grow(p0, _dir(ang, math.radians(rng.uniform(22, 50))), h * rng.uniform(0.22, 0.32), 0.5,
                      1 if size in ("large", "huge") else 0, dict(seg=1.8, wiggle=0.3, up=0.05, forks=1))
        for tp in tips:
            r = rng.uniform(*rr)
            t.cluster(tp.p, r, flat=0.62, under=0.4, lumps=1, dens=0.82, rag=1.25)
    r = rng.uniform(*rr) * 1.1
    t.cluster((sp[-1][0], sp[-1][1] + 0.8, sp[-1][2]), r, flat=0.62, under=0.4, lumps=2, dens=0.82, rag=1.25)
    t.post.append((_p_propagules, 0.07))
    t.post.append((_p_vines, 0.035, 4, 1))
    t.post.append((_p_moss_top, 0.3))
    t.cover_spec = (max(D) + 1.5, [("mud", 0.5)], [("moss_carpet", 0.05), ("short_grass", 0.04)])


def _g_poplar(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (8, 11), "medium": (12, 16), "large": (17, 22), "huge": (23, 29)}[size])
    top = t.y + h - 1
    sp = t.trunk(top, 0.5 if size != "huge" else 0.95, 0.5, flare=0.3 if size in ("large", "huge") else 0.0,
                 wobble=0.12)
    if t.leaves == _SP["poplar"][1]:
        tint = rng.random()
        if tint < 0.4:
            t.leaves = (("yellow_poplar_leaves", 0.7), ("orange_poplar_leaves", 0.25), ("red_poplar_leaves", 0.05))
        elif tint < 0.8:
            t.leaves = (("yellow_poplar_leaves", 0.35), ("orange_poplar_leaves", 0.5), ("red_poplar_leaves", 0.15))
        else:
            t.leaves = (("orange_poplar_leaves", 0.45), ("red_poplar_leaves", 0.4), ("yellow_poplar_leaves", 0.15))
    t.mix_scale = 4.5
    t.mix_noise = 0.18
    Rm = {"small": 1.9, "medium": 2.3, "large": 2.8, "huge": 3.3}[size]
    cb = int(len(sp) * rng.uniform(0.16, 0.24))
    yi = cb
    a = rng.uniform(0, 2 * math.pi)
    while yi < len(sp):
        f = (yi - cb) / max(1, len(sp) - cb)
        r = Rm * (0.45 + 0.6 * math.sin(math.pi * min(1.0, 0.12 + 0.9 * f)) ** 0.8)
        p0 = sp[yi]
        a += 2.39996
        if rng.random() < 0.6:
            tips = t.grow(p0, _dir(a, math.radians(rng.uniform(45, 70))), rng.uniform(0.8, 1.6), 0.5, 0,
                          dict(seg=1.2, wiggle=0.1))
            c = tips[-1].p
        else:
            c = p0
        t.blob((c[0], c[1] + 0.5, c[2]), r, r * 1.1, r * 0.9, 0.9, rag=1.1)
        yi += rng.randint(2, 3)
    t.blob((sp[-1][0], sp[-1][1] + 1.2, sp[-1][2]), Rm * 0.6, Rm * 1.0, Rm * 0.7, 0.9)
    t.cover_spec = (Rm * 1.8, [], [(_litter, 0.15), ("short_grass", 0.05)])


def _g_palm(t, size):
    rng = t.rng
    h = rng.randint(*{"small": (6, 8), "medium": (9, 12), "large": (13, 16), "huge": (17, 22)}[size])
    a = rng.uniform(0, 2 * math.pi)
    lean = h * rng.uniform(0.18, 0.35)
    cx, cz = t.x + 0.5, t.z + 0.5
    pts = []
    for k in range(h + 1):
        f = k / h
        off = lean * f ** 2.2
        pts.append((cx + math.cos(a) * off, t.y + 1 + k + 0.5, cz + math.sin(a) * off))
    rb = 0.9 if size in ("large", "huge") else 0.5
    for k in range(h):
        r = rb if k < 2 else 0.5
        t.tube(pts[k], pts[k + 1], r, r)
    for c in list(t.logs):
        t.trunk_cells.add(c)
    first = [c for c in t.logs if c[1] == t.y + 1]
    for c in first:
        g = t.gy(c[0], c[2])
        for yy in range(min(g, t.y) - 1, t.y + 1):
            t.setlog((c[0], yy, c[2]), "y", trunk=True)
    t.spine = pts
    head = tuple(math.floor(v) for v in pts[-1])
    t.setlog(head, wood=True, trunk=True, force=True)
    hx, hy, hz = head[0] + 0.5, head[1] + 0.5, head[2] + 0.5
    t.reach = 24   # fronds are long face-connected leaf chains
    nfr = rng.randint(*{"small": (6, 7), "medium": (7, 9), "large": (8, 10), "huge": (9, 11)}[size])
    L = {"small": (3.5, 4.5), "medium": (4.5, 6.0), "large": (5.5, 7.0), "huge": (6.5, 8.5)}[size]
    b0 = rng.uniform(0, 2 * math.pi)
    for i in range(nfr):
        b = b0 + i * 2 * math.pi / nfr + rng.uniform(-0.25, 0.25)
        ln = rng.uniform(*L)
        lift = rng.uniform(1.0, 1.4)
        drop = rng.uniform(1.4, 2.4) * (ln / 5.0)
        k = (lift * ln + drop) / (ln * ln)   # parabola: arches up, then hangs `drop` below the head at the tip
        prev = (hx, hy, hz)
        steps = int(ln * 2)
        perp = (-math.sin(b), math.cos(b))
        side = rng.choice((-1, 1))
        for s in range(1, steps + 1):
            dd = s / 2.0
            p = (hx + math.cos(b) * dd, hy + lift * dd - k * dd * dd, hz + math.sin(b) * dd)
            for c, _tt in _traverse(prev, p):
                if c != head:
                    t.leaf(c)
            f = dd / ln
            if 0.3 < f < 0.85 and s % 3 == 0:     # sparse leaflets, alternating sides, hanging a little
                side = -side
                q = (math.floor(p[0] + perp[0] * side * 0.95), math.floor(p[1]), math.floor(p[2] + perp[1] * side * 0.95))
                if (q[0], q[2]) != (math.floor(p[0]), math.floor(p[2])):
                    t.leaf(q)
                    if f > 0.5 and rng.random() < 0.6:
                        t.leaf((q[0], q[1] - 1, q[2]))
            prev = p
        tip = (math.floor(prev[0]), math.floor(prev[1]), math.floor(prev[2]))
        t.leaf((tip[0], tip[1] - 1, tip[2]))   # drooping tip
    t.leaf((head[0], head[1] + 1, head[2]))
    for (dx, dz, _n) in _DIRS4:
        if rng.random() < 0.5:
            t.leaf((head[0] + dx, head[1] + 1, head[2] + dz))
    below = (head[0], head[1] - 1, head[2])   # coconuts
    if below in t.logs:
        dirs = list(_DIRS4)
        rng.shuffle(dirs)
        for (dx, dz, name) in dirs[: rng.randint(2, 3)]:
            q = (below[0] + dx, below[1], below[2] + dz)
            t.deco[q] = (f"cocoa[age=2,facing={_OPP[name]}]", (-dx, 0, -dz))
    t.cover_spec = None


def _g_dead(t, size):
    rng = t.rng
    C = {
        "small": dict(h=(5, 7), trunk=dict(top=0.65, r0=0.5, wobble=0.25),
                      limbs=dict(n=(2, 3), at=(0.4, 0.7), el=(35, 70), len=(0.45, 0.65), depth=1, forks=1, fork_p=0.6,
                                 seg=1.6, wiggle=0.22, up=0.05, fork_ang=(25, 50))),
        "medium": dict(h=(8, 11), trunk=dict(top=0.55, r0=0.5, flare=0.4, wobble=0.3),
                       limbs=dict(n=(3, 4), at=(0.3, 0.6), el=(25, 62), len=(0.45, 0.62), depth=1, forks=1,
                                  fork_p=0.8, seg=2.0, wiggle=0.22, up=0.05, fork_ang=(25, 50),
                                  child_len=(0.55, 0.8))),
        "large": dict(h=(12, 16), trunk=dict(top=0.55, r0=1.0, r1=0.6, flare=0.7, wobble=0.35, bark=0.3),
                      limbs=dict(n=(4, 6), at=(0.3, 0.62), el=(25, 62), len=(0.48, 0.64), r=0.7, depth=2,
                                 forks=(1, 2), fork_p=0.9, seg=2.2, wiggle=0.22, up=0.05, fork_ang=(25, 50),
                                 child_len=(0.55, 0.8))),
        "huge": dict(h=(16, 21), trunk=dict(top=0.5, r0=1.5, r1=0.9, flare=1.0, wobble=0.35, bark=0.5),
                     limbs=dict(n=(5, 7), at=(0.3, 0.6), el=(20, 58), len=(0.46, 0.6), r=0.9, taper=0.5, depth=2,
                                forks=2, fork_p=1.0, seg=2.4, wiggle=0.22, up=0.05, fork_ang=(25, 50),
                                child_len=(0.55, 0.8))),
    }[size]
    C["leader_len"] = (0.15, 0.25)
    C["leader_depth"] = 1 if size in ("large", "huge") else 0
    _broadleaf(t, C)
    if size in ("large", "huge"):
        t.roots(rng.randint(4, 6), (2.0, 4.0), rise=0.8, start_r=0.8)
    t.cover_spec = (_CROWN["dead"][SIZES.index(size)] * 0.6, [("coarse_dirt", 0.15)],
                    [("dead_bush", 0.04), (_litter, 0.06)])


def _litter(rng):
    return f"leaf_litter[facing={rng.choice(('north', 'south', 'east', 'west'))},segment_amount={rng.randint(1, 4)}]"


def _petals(rng):
    return f"pink_petals[facing={rng.choice(('north', 'south', 'east', 'west'))},flower_amount={rng.randint(1, 4)}]"


def _wildflowers(rng):
    return f"wildflowers[facing={rng.choice(('north', 'south', 'east', 'west'))},flower_amount={rng.randint(1, 4)}]"


_GEN = {"oak": _g_oak, "birch": _g_birch, "spruce": _g_spruce, "pine": _g_pine, "jungle": _g_jungle,
        "acacia": _g_acacia, "dark_oak": _g_dark_oak, "cherry": _g_cherry, "mangrove": _g_mangrove,
        "pale_oak": _g_pale_oak, "willow": _g_willow, "poplar": _g_poplar, "palm": _g_palm, "dead": _g_dead}


# ============================================================================ public API
def tree(b, x: int, y: int, z: int, species: str = "oak", size: str = "medium", seed: int = 0, heights=None,
         ground: bool = True, decor: bool = True, leaves=None, wood: str | None = None, protect: bool = True) -> dict:
    """Grow one tree. (x, y, z) = ground block under the trunk (trunk starts at y+1). See module docstring."""
    sp = _norm_species(species)
    sz = _norm_size(size)
    wname, lmix = _SP[sp]
    log, woodb = _wood_states(b.db, wood or wname)
    lm = _leaf_mix(leaves)
    if lm is not None:
        for name, _w in lm:
            b.db.canonical(f"{name}[persistent=true]")  # validate early
    rng = random.Random(_mix(seed, sp, sz))
    t = _Tree(b, x, y, z, rng, _mix(seed, sp, sz, "n"), log, woodb, lm if lm is not None else lmix, heights)
    _GEN[sp](t, sz)
    if not t.logs:
        raise RuntimeError("tree generator produced no wood")
    t.finish(ground=ground, decor=decor)
    info = t.commit(protect=protect)
    info.update({"species": sp, "size": sz, "x": int(x), "y": int(y), "z": int(z), "seed": seed})
    return info


BUSHES = ("oak", "azalea", "flowering_azalea", "spruce", "jungle", "dark_oak", "birch", "cherry", "acacia", "mangrove",
          "pale_oak", "berry")
_BUSH = {
    "oak": ("oak", (("oak_leaves", 1.0),)), "azalea": ("oak", (("azalea_leaves", 0.7), ("flowering_azalea_leaves", 0.3))),
    "flowering_azalea": ("oak", (("flowering_azalea_leaves", 0.65), ("azalea_leaves", 0.35))),
    "spruce": ("spruce", (("spruce_leaves", 1.0),)), "jungle": ("jungle", (("oak_leaves", 1.0),)),
    "dark_oak": ("dark_oak", (("dark_oak_leaves", 1.0),)), "birch": ("birch", (("birch_leaves", 1.0),)),
    "cherry": ("cherry", (("cherry_leaves", 1.0),)), "acacia": ("acacia", (("acacia_leaves", 1.0),)),
    "mangrove": ("mangrove", (("mangrove_leaves", 1.0),)), "pale_oak": ("pale_oak", (("pale_oak_leaves", 1.0),)),
}


def bush(b, x: int, y: int, z: int, kind: str = "oak", size: str = "small", seed: int = 0, heights=None,
         protect: bool = True) -> dict:
    """Shrub on the ground block (x, y, z): a woody core inside an irregular leaf mound (or a berry patch)."""
    k = str(kind).lower()
    sz = _norm_size(size)
    rng = random.Random(_mix(seed, "bush", k, sz))
    if k == "berry":
        n = {"small": 3, "medium": 6, "large": 10, "huge": 16}[sz]
        placed = 0
        h = None if heights is None else np.asarray(heights)
        for _ in range(n * 3):
            dx, dz = rng.randint(-2, 2), rng.randint(-2, 2)
            px, pz = x + dx, z + dz
            gy = y
            if h is not None and 0 <= pz < h.shape[0] and 0 <= px < h.shape[1]:
                gy = int(h[pz, px])
            if b.get_id(px, gy + 1, pz) in (0, 1) and (b.get_id(px, gy, pz) == 0 or b.is_solid(px, gy, pz)):
                b.set(px, gy + 1, pz, f"sweet_berry_bush[age={rng.randint(2, 3)}]")
                placed += 1
                if placed >= n:
                    break
        return {"kind": k, "size": sz, "plants": placed}
    if k not in _BUSH:
        raise ValueError(f"unknown bush kind '{kind}' (choose: {', '.join(BUSHES)})")
    wname, lmix = _BUSH[k]
    log, woodb = _wood_states(b.db, wname)
    t = _Tree(b, x, y, z, rng, _mix(seed, "bushn", k, sz), log, woodb, lmix, heights)
    t.reach = 5
    base = (x + 0.5, y + 1.5, z + 0.5)
    t.setlog((x, y + 1, z), "y", trunk=True)
    t.setlog((x, y, z), "y", trunk=True)
    t.spine = [base]
    if sz == "small":
        r = rng.uniform(1.3, 1.7)
        t.blob((base[0], y + 1.6, base[2]), r, r * 0.75, r * 0.6, 0.9)
    elif sz == "medium":
        t.setlog((x, y + 2, z), "y", trunk=True)
        r = rng.uniform(1.9, 2.3)
        t.blob((base[0], y + 2.0, base[2]), r, r * 0.7, r * 0.55, 0.9)
        a = rng.uniform(0, 2 * math.pi)
        t.tube((base[0], y + 1.5, base[2]), (base[0] + math.cos(a) * 1.4, y + 1.6, base[2] + math.sin(a) * 1.4))
        t.blob((base[0] + math.cos(a) * 1.6, y + 1.6, base[2] + math.sin(a) * 1.6), r * 0.7, r * 0.55, r * 0.45, 0.9)
    else:
        nb = 3 if sz == "large" else 5
        R = 2.2 if sz == "large" else 2.7
        t.setlog((x, y + 2, z), "y", trunk=True)
        a0 = rng.uniform(0, 2 * math.pi)
        t.blob((base[0], y + 2.2, base[2]), R, R * 0.7, R * 0.55, 0.9)
        for i in range(nb):
            a = a0 + i * 2 * math.pi / nb + rng.uniform(-0.3, 0.3)
            d = R * rng.uniform(0.9, 1.3)
            p = (base[0] + math.cos(a) * d, y + 1.6, base[2] + math.sin(a) * d)
            t.tube((base[0], y + 1.5, base[2]), p)
            r = R * rng.uniform(0.6, 0.85)
            t.blob((p[0], y + 1.2 + r * 0.5, p[2]), r, r * 0.7, r * 0.55, 0.9)
    t.finish(ground=False, decor=False)
    info = t.commit(protect=protect)
    info.update({"kind": k, "size": sz})
    return info


# ---------------------------------------------------------------------------- undergrowth
def _double(lower):
    return lambda r: (f"{lower}[half=lower]", f"{lower}[half=upper]")


STYLES = {
    "meadow": ([("short_grass", 40), (_double("tall_grass"), 10), ("dandelion", 3), ("poppy", 3), ("oxeye_daisy", 2),
                ("cornflower", 2), ("azure_bluet", 2), (_wildflowers, 4), ("allium", 1), (_double("lilac"), 0.6),
                (_double("rose_bush"), 0.5), (_double("peony"), 0.5), ("pink_tulip", 0.6), ("white_tulip", 0.6)], []),
    "forest": ([("short_grass", 30), ("fern", 9), (_double("tall_grass"), 5), ("bush", 6), (_litter, 9),
                (_double("large_fern"), 2), ("lily_of_the_valley", 1), ("brown_mushroom", 1), ("dandelion", 1),
                ("poppy", 1)], [("coarse_dirt", 0.03), ("podzol", 0.03)]),
    "birch": ([("short_grass", 30), (_double("tall_grass"), 6), (_wildflowers, 7), ("fern", 3), ("bush", 4),
               ("lily_of_the_valley", 2), (_litter, 4), (_double("lilac"), 0.6)], []),
    "taiga": ([("fern", 25), (_double("large_fern"), 8), ("short_grass", 10), ("sweet_berry_bush[age=3]", 3),
               ("brown_mushroom", 1), (_litter, 2)], [("podzol", 0.25), ("coarse_dirt", 0.05)]),
    "jungle": ([("fern", 25), (_double("large_fern"), 10), ("short_grass", 15), (_double("tall_grass"), 6), ("bush", 6)],
               [("rooted_dirt", 0.02)]),
    "savanna": ([("short_dry_grass", 25), ("tall_dry_grass", 12), ("short_grass", 10), (_double("tall_grass"), 4),
                 ("dead_bush", 1)], [("coarse_dirt", 0.06)]),
    "cherry": ([(_petals, 30), ("short_grass", 20), (_double("tall_grass"), 3), (_wildflowers, 3)], []),
    "dark": ([("short_grass", 15), ("fern", 8), ("brown_mushroom", 3), ("red_mushroom", 2), (_litter, 12), ("bush", 3)],
             [("podzol", 0.1), ("coarse_dirt", 0.05)]),
    "swamp": ([("short_grass", 25), ("fern", 6), ("blue_orchid", 3), ("bush", 4), ("brown_mushroom", 1)],
              [("mud", 0.05)]),
    "pale": ([("pale_moss_carpet", 22), ("short_grass", 6), ("closed_eyeblossom", 2), (_litter, 4)],
             [("pale_moss_block", 0.3)]),
    "beach": ([("short_dry_grass", 6), ("dead_bush", 1), ("tall_dry_grass", 2)], []),
    "autumn": ([(_litter, 30), ("short_grass", 12), ("fern", 4), ("bush", 3), ("brown_mushroom", 1)],
               [("coarse_dirt", 0.03)]),
}
_STYLE_FOR = {"oak": "forest", "birch": "birch", "spruce": "taiga", "pine": "taiga", "jungle": "jungle",
              "acacia": "savanna", "dark_oak": "dark", "cherry": "cherry", "mangrove": "swamp", "pale_oak": "pale",
              "willow": "swamp", "poplar": "autumn", "palm": "beach", "dead": "savanna"}
_PLANT_SOIL = {"grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "moss_block", "pale_moss_block", "mud",
               "mycelium"}
_DRY_OK = {"short_dry_grass", "tall_dry_grass", "dead_bush"}


def _area_mask(area, D, W):
    if area is None:
        return np.ones((D, W), bool)
    if isinstance(area, np.ndarray) and area.dtype == bool:
        if area.shape != (D, W):
            raise ValueError(f"area mask shape {area.shape} != heightmap {(D, W)}")
        return area.copy()
    x0, z0, x1, z1 = [int(v) for v in area]
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    m = np.zeros((D, W), bool)
    m[max(0, z0):min(D, z1 + 1), max(0, x0):min(W, x1 + 1)] = True
    return m


def undergrowth(b, heights, area=None, density: float = 0.3, style: str = "forest", seed: int = 0, water=None,
                avoid=None, surface=None) -> int:
    """Scatter ground plants (grass, ferns, flowers, petals, litter, berries...) on top of a heightmap."""
    hm = np.asarray(heights)
    D, W = hm.shape
    if style not in STYLES:
        raise ValueError(f"unknown style '{style}' (choose: {', '.join(STYLES)})")
    plants, cover = STYLES[style]
    A = _area_mask(area, D, W)
    if water is not None:
        A &= ~np.asarray(water, bool)
    if avoid is not None:
        A &= ~np.asarray(avoid, bool)
    ii, jj = np.mgrid[0:D, 0:W]
    patch = _fbm2(jj, ii, 9.0, seed + 5)
    p = np.clip(density * (0.25 + 1.5 * patch), 0, 1)
    sel = A & (_hash(seed + 7, jj, ii) < p)
    rng = random.Random(seed + 11)
    tot = sum(w for _, w in plants)
    cum = []
    acc = 0.0
    for fn, w in plants:
        acc += w / tot
        cum.append((acc, fn))
    n = 0
    db = b.db
    soil_cache = {}

    def soil_ok(pid, name_hint=None):
        if pid == 0:
            return True if name_hint is None else (name_hint in _PLANT_SOIL or name_hint in ("sand", "red_sand"))
        r = soil_cache.get(pid)
        if r is None:
            nm = b.palette[pid].lstrip("!").split("[", 1)[0].split(":", 1)[-1]
            r = 2 if nm in _PLANT_SOIL else (1 if nm in ("sand", "red_sand") else 0)
            soil_cache[pid] = r
        return r

    for i, j in zip(*np.nonzero(sel)):
        x, z, g = int(j), int(i), int(hm[i, j])
        gid = b.get_id(x, g, z)
        hint = None
        if surface is not None:
            hint = str(surface[i, j]).split("[", 1)[0].split(":", 1)[-1]
        s = soil_ok(gid, hint) if gid != 0 else (2 if hint is None or hint in _PLANT_SOIL else (1 if hint in ("sand", "red_sand") else 0))
        if s == 0:
            continue
        if b.get_id(x, g + 1, z) not in (0, 1):
            continue
        u = rng.random()
        fn = cum[-1][1]
        for c, f in cum:
            if u <= c:
                fn = f
                break
        st = fn(rng) if callable(fn) else fn
        if isinstance(st, tuple):
            if b.get_id(x, g + 2, z) not in (0, 1):
                continue
            if s == 1:
                continue
            b.set(x, g + 1, z, st[0])
            b.set(x, g + 2, z, st[1])
        else:
            nm = st.split("[", 1)[0]
            if s == 1 and nm not in _DRY_OK:
                continue
            b.set(x, g + 1, z, st)
        n += 1
        if s == 2:
            for cst, cp in cover:
                if rng.random() < cp * 2 and db.has_block(cst):
                    b.set(x, g, z, cst)
                    break
    return n


# ---------------------------------------------------------------------------- forest
def _edt_simple(mask):
    """Euclidean distance to nearest True (inf if none) - exact, vectorised (two-pass)."""
    D, W = mask.shape
    if not mask.any():
        return np.full((D, W), np.inf)
    BIG = D + W + 5
    idx = np.arange(W)
    left = np.where(mask, idx[None, :], -BIG)
    left = np.maximum.accumulate(left, axis=1)
    right = np.where(mask, idx[None, :], 3 * BIG)
    right = np.minimum.accumulate(right[:, ::-1], axis=1)[:, ::-1]
    g = np.minimum(idx[None, :] - left, right - idx[None, :]).astype(np.float64)
    g2 = g * g
    out = np.empty((D, W))
    ks = np.arange(D)
    ch = max(1, int(4_000_000 // max(1, D * W)))
    for i0 in range(0, D, ch):
        ii = np.arange(i0, min(D, i0 + ch))
        d2 = g2[None, :, :] + ((ii[:, None] - ks[None, :]) ** 2)[:, :, None]
        out[ii] = d2.min(axis=1)
    return np.sqrt(out)


def forest(b, heights, area=None, density: float = 0.5, species_mix="oak", seed: int = 0, sizes=None, water=None,
           avoid=None, undergrowth: bool = True, style: str | None = None, max_trees: int = 400, ground: bool = True,
           slope_max: int = 4) -> list:
    """Place a natural forest on a heightmap (see module docstring). Returns the placed trees' info dicts."""
    hm = np.asarray(heights)
    D, W = hm.shape
    A = _area_mask(area, D, W)
    wm = None if water is None else np.asarray(water, bool)
    if wm is not None:
        near_w = wm.copy()
        near_w[1:] |= wm[:-1]
        near_w[:-1] |= wm[1:]
        near_w[:, 1:] |= wm[:, :-1]
        near_w[:, :-1] |= wm[:, 1:]
    if isinstance(species_mix, str):
        mix = {_norm_species(species_mix): 1.0}
    elif isinstance(species_mix, dict):
        mix = {_norm_species(k): float(v) for k, v in species_mix.items() if float(v) > 0}
    else:
        mix = {_norm_species(k): 1.0 for k in species_mix}
    if not mix:
        raise ValueError("species_mix is empty")
    szw = sizes or {"small": 2.0, "medium": 5.0, "large": 2.2, "huge": 0.5}
    szw = {_norm_size(k): float(v) for k, v in szw.items() if float(v) > 0}
    density = float(min(1.0, max(0.02, density)))
    rng = random.Random(_mix(seed, "forest"))
    cells = np.argwhere(A)
    if len(cells) == 0:
        return []
    avoid_d = None
    if avoid is not None:
        avoid_d = _edt_simple(np.asarray(avoid, bool))
    tries = int(min(30000, max(300, len(cells) * 0.6)))
    sp_names = list(mix)
    sp_w = [mix[k] for k in sp_names]
    sz_names = list(szw)
    sz_w = [szw[k] for k in sz_names]
    cand = []
    for _ in range(tries):
        i, j = cells[rng.randrange(len(cells))]
        sp = rng.choices(sp_names, sp_w)[0]
        sz = rng.choices(sz_names, sz_w)[0]
        R = _CROWN[sp][SIZES.index(sz)] * rng.uniform(0.9, 1.1)
        cand.append((R, int(j), int(i), sp, sz))
    cand.sort(key=lambda c: -c[0])
    spacing = 1.55 - 1.0 * density
    clear = _fbm2(np.arange(W)[None, :], np.arange(D)[:, None], 16.0, seed + 23)
    px = np.zeros(0)
    pz = np.zeros(0)
    pr = np.zeros(0)
    pw = np.zeros(0)
    chosen = []
    for (R, x, z, sp, sz) in cand:
        if len(chosen) >= max_trees:
            break
        if density < 0.85 and rng.random() > min(1.0, (0.35 + 1.3 * clear[z, x]) * (0.4 + density)):
            continue
        tw = _TW.get(sp, (1, 1, 1, 1))[SIZES.index(sz)]
        x0 = x - (tw // 2 if tw % 2 else 0)
        z0 = z - (tw // 2 if tw % 2 else 0)
        x1, z1 = x0 + tw - 1, z0 + tw - 1
        if x0 < 0 or z0 < 0 or x1 >= W or z1 >= D:
            continue
        if not A[z0:z1 + 1, x0:x1 + 1].all():
            continue
        if sp != "mangrove" and wm is not None and near_w[max(0, z0 - 1):z1 + 2, max(0, x0 - 1):x1 + 2].any():
            continue
        if sp == "mangrove" and wm is not None and wm[z0:z1 + 1, x0:x1 + 1].any():
            continue
        foot = hm[max(0, z0 - 1):z1 + 2, max(0, x0 - 1):x1 + 2]
        if int(foot.max()) - int(foot.min()) > slope_max:
            continue
        if avoid_d is not None and avoid_d[z, x] < max(2.0, R * 0.75):
            continue
        if len(px):
            d = np.sqrt((px - x) ** 2 + (pz - z) ** 2)
            if (d < (pr + R) * spacing).any() or (d < (pw + tw) * 0.5 + 2.0).any():
                continue
        px = np.append(px, x)
        pz = np.append(pz, z)
        pr = np.append(pr, R)
        pw = np.append(pw, tw)
        gy = int(hm[z0:z1 + 1, x0:x1 + 1].min())
        chosen.append((x0 if tw == 2 else x, gy, z0 if tw == 2 else z, sp, sz))
    out = []
    for k, (x, gy, z, sp, sz) in enumerate(chosen):
        info = tree(b, x, gy, z, sp, sz, seed=_mix(seed, "t", k) & 0xFFFFFF, heights=hm, ground=ground)
        out.append(info)
    if undergrowth and out:
        st = style or _STYLE_FOR.get(max(mix, key=mix.get), "forest")
        ug_area = A.copy()
        undergrowth_fn(b, hm, area=ug_area, density=0.12 + 0.3 * density, style=st, seed=seed + 1, water=wm,
                       avoid=None if avoid is None else np.asarray(avoid, bool))
    return out


undergrowth_fn = undergrowth
