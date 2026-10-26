"""Denetci kontrolleri: analiz baglami (Ctx), bulgu/rapor siniflari ve kontrol kaydi (CHECKS).

Yerel cerceve core.Build ile ayni: y yukari, on cephe z=0'da ve -z'ye ("north") bakar, +x yapinin sagi.
Yapi yogun diziye (build.dense()) cevrilir ve her yandan dolgulanir: altta zemin katmani, yanlarda/ustte
"keep" (bilinmeyen dunya, hava sayilir). context["ground_y"] (varsayilan 0 = yerel zemin ustu) ve istege
bagli context["heightmap"] altindaki keep hucreleri arazi (dolu zemin) sayilir.
Buyuk hacim islemleri numpy ile; Python dongusu yalniz palet, oda ve bilesen gibi kucuk kumelerde.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from typing import Callable

import numpy as np

from .. import blockdb as BDB
from ..blockdb import FACE_BIT
from . import light as LT

SEVERITIES = ("critical", "major", "minor")
SEV_RANK = {"critical": 0, "major": 1, "minor": 2}
SEV_TR = {"critical": "KRİTİK", "major": "BÜYÜK", "minor": "küçük"}

PADX, PADB, PADT = 2, 1, 3  # yan, alt (zemin), ust dolgu

# (dy, dz, dx) yerel yonler: north = -z, south = +z, east = +x, west = -x
DIRV = {"up": (1, 0, 0), "down": (-1, 0, 0), "south": (0, 1, 0), "north": (0, -1, 0), "east": (0, 0, 1), "west": (0, 0, -1)}
OPP = {"up": "down", "down": "up", "north": "south", "south": "north", "east": "west", "west": "east"}
HORIZ = ("north", "east", "south", "west")
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}
SIDE_TR = {"north": "ön (kuzey, -z)", "south": "arka (güney, +z)", "west": "sol yan (batı, -x)", "east": "sağ yan (doğu, +x)"}

WOODS = ("pale_oak", "dark_oak", "oak", "spruce", "birch", "jungle", "acacia", "mangrove", "cherry", "bamboo", "crimson",
         "warped", "poplar")
DYES = ("light_blue", "light_gray", "white", "orange", "magenta", "yellow", "lime", "pink", "gray", "cyan", "purple",
        "blue", "brown", "green", "red", "black")
DIRT = {"grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "mycelium", "moss_block", "pale_moss_block", "mud",
        "muddy_mangrove_roots", "farmland"}
SAND = {"sand", "red_sand", "suspicious_sand"}
CROPS = {"wheat", "carrots", "potatoes", "beetroots", "melon_stem", "pumpkin_stem", "attached_melon_stem",
         "attached_pumpkin_stem", "torchflower_crop", "pitcher_crop"}
FURN_ITEMS = ("_bed", "chest", "barrel", "crafting_table", "furnace", "smoker", "bookshelf", "lectern", "loom",
              "cartography_table", "fletching_table", "smithing_table", "stonecutter", "grindstone", "anvil", "cauldron",
              "composter", "brewing_stand", "enchanting_table", "jukebox", "note_block", "flower_pot", "potted_",
              "candle", "_carpet", "banner", "_sign", "bell", "decorated_pot", "_shelf", "_head", "_skull", "campfire",
              "beehive", "crafter", "lodestone", "respawn_anchor", "copper_golem_statue", "dried_ghast", "item_frame")
FURN_SHAPES = ("_stairs", "_slab", "_trapdoor", "_fence", "_pressure_plate", "_wall", "scaffolding")
LIGHT_KEYS = ("torch", "lantern", "glowstone", "froglight", "end_rod", "redstone_lamp", "shroomlight")


def _is_light_name(a: str) -> bool:
    return a == "light" or any(k in a for k in LIGHT_KEYS)
EXEMPT_WINDOW = ("depo", "bodrum", "kiler", "mahzen", "storage", "cellar", "basement", "vault", "hazine", "zindan",
                 "dungeon", "closet", "dolap", "koridor", "corridor", "hall", "merdiven", "stair", "tuvalet", "wc",
                 "sığınak", "bunker", "kasa", "gizli", "secret")
EXEMPT_SECRET = ("gizli", "secret")     # gizli kapili (meta secret_door) odaya yurunerek degil, kizilatas kapiyla girilir
EXEMPT_EMPTY = ("koridor", "corridor", "merdiven", "stair", "giriş", "hol", "hall", "antre", "balkon", "teras", "avlu",
                "courtyard")


# ====================================================================== bulgu / rapor
@dataclass
class Finding:
    check: str
    severity: str
    message: str
    fix: str
    positions: list = field(default_factory=list)
    count: int = 0
    data: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.check

    def to_dict(self) -> dict:
        d = {"check": self.check, "severity": self.severity, "message": self.message, "fix": self.fix,
             "positions": [[int(v) for v in p] for p in self.positions], "count": int(self.count)}
        if self.data:
            d["data"] = self.data
        return d

    def line(self) -> str:
        pos = ", ".join("(" + ",".join(str(int(v)) for v in p) + ")" for p in self.positions[:4])
        return f"[{SEV_TR.get(self.severity, self.severity)}] {self.check}: {self.message}" + \
               (f" — konum: {pos}" if pos else "") + f" → Çözüm: {self.fix}"


@dataclass
class Report:
    name: str
    findings: list
    score: float
    stats: dict
    checks_run: list
    errors: dict = field(default_factory=dict)
    auto_scores: dict = field(default_factory=dict)
    seconds: float = 0.0

    def by_check(self, cid: str) -> list:
        return [f for f in self.findings if f.check == cid]

    def has(self, cid: str, severity: str | None = None) -> bool:
        return any(f.check == cid and (severity is None or f.severity == severity) for f in self.findings)

    def ids(self) -> list:
        return sorted({f.check for f in self.findings})

    def counts(self) -> dict:
        c = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        return c

    @property
    def critical(self) -> int:
        return self.counts()["critical"]

    @property
    def major(self) -> int:
        return self.counts()["major"]

    @property
    def minor(self) -> int:
        return self.counts()["minor"]

    def to_dict(self) -> dict:
        c = self.counts()
        return {"name": self.name, "score": round(float(self.score), 1), "critical": c["critical"], "major": c["major"],
                "minor": c["minor"], "findings": [f.to_dict() for f in self.findings],
                "auto_scores": {k: [v[0], v[1]] for k, v in self.auto_scores.items()},
                "stats": _jsonable(self.stats), "checks_run": list(self.checks_run), "errors": dict(self.errors),
                "seconds": round(self.seconds, 3)}

    def summary(self, limit: int = 15) -> str:
        c = self.counts()
        out = [f"Denetim '{self.name}': puan {self.score:.0f}/100 — {c['critical']} kritik, {c['major']} büyük, {c['minor']} küçük bulgu."]
        for f in self.findings[:limit]:
            out.append("- " + f.line())
        if len(self.findings) > limit:
            out.append(f"... ve {len(self.findings) - limit} bulgu daha.")
        if self.errors:
            out.append("Çalışmayan kontroller: " + ", ".join(self.errors))
        return "\n".join(out)

    def __str__(self) -> str:  # pragma: no cover - kolaylik
        return self.summary()


def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, np.ndarray):
        return _jsonable(v.tolist())
    return v


# ====================================================================== kontrol kaydi
@dataclass
class Check:
    id: str
    func: Callable
    description: str
    group: str

    def __str__(self) -> str:
        return self.description


CHECKS: dict[str, Check] = {}


def check(cid: str, description: str, group: str):
    def deco(fn):
        CHECKS[cid] = Check(cid, fn, description, group)
        return fn
    return deco


# ====================================================================== dizi yardimcilari
def _pair_slices(shape, dy, dz, dx):
    """a hucreleri ve b = a + (dy,dz,dx) hucreleri icin hizali dilimler."""
    def s(d, n):
        return (slice(0, n - d), slice(d, n)) if d >= 0 else (slice(-d, n), slice(0, n + d))
    (ay, by), (az, bz), (ax, bx) = s(dy, shape[0]), s(dz, shape[1]), s(dx, shape[2])
    return (ay, az, ax), (by, bz, bx)


def shift(a: np.ndarray, dy: int = 0, dz: int = 0, dx: int = 0, fill=0) -> np.ndarray:
    """out[y,z,x] = a[y+dy, z+dz, x+dx] (disarisi fill)."""
    out = np.full(a.shape, fill, dtype=a.dtype)
    sa, sb = _pair_slices(a.shape, dy, dz, dx)
    out[sa] = a[sb]
    return out


def _xruns(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """x ekseni boyunca kesintisiz kosular: (kosu kimligi dizisi (0 = yok), kosu sayisi)."""
    m = np.ascontiguousarray(mask, dtype=bool)
    flat = m.reshape(-1)
    if flat.size == 0:
        return np.zeros(m.shape, np.int32), 0
    start = flat.copy()
    start[1:] &= ~flat[:-1]
    s3 = start.reshape(m.shape)
    s3[..., 0] = m[..., 0]
    rid = np.cumsum(start, dtype=np.int64)
    rid[~flat] = 0
    nr = int(rid.max()) if rid.size else 0
    return rid.reshape(m.shape).astype(np.int32), nr


def _uf(n: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vektorlu birlesim-bul (min etiket kancalama + isaretci atlama). Donus: kok dizisi (n+1)."""
    parent = np.arange(n + 1, dtype=np.int64)
    if a.size == 0:
        return parent
    a = a.astype(np.int64)
    b = b.astype(np.int64)
    for _ in range(200):
        pa = parent[a]
        pb = parent[b]
        ne = pa != pb
        if not ne.any():
            break
        a, b, pa, pb = a[ne], b[ne], pa[ne], pb[ne]
        lo = np.minimum(pa, pb)
        hi = np.maximum(pa, pb)
        np.minimum.at(parent, hi, lo)
        while True:
            gp = parent[parent]
            if np.array_equal(gp, parent):
                break
            parent = gp
    return parent


def label(mask: np.ndarray, conn: int = 6, planar: bool = False) -> tuple[np.ndarray, int]:
    """Bagli bilesenler (3B; 2B icin [1,h,w] ver). conn: 6 | 18 | 26. planar: yalniz ayni y katmaninda (xz 4-komsu).
    Donus: (etiket dizisi int64, 0 = arka plan; etiket = bilesenin kok kosu kimligi), kosu sayisi."""
    m = np.ascontiguousarray(mask, dtype=bool)
    rid, nr = _xruns(m)
    if nr == 0:
        return np.zeros(m.shape, np.int64), 0
    start = np.zeros(m.shape, bool)
    start[..., 0] = m[..., 0]
    start[..., 1:] = m[..., 1:] & ~m[..., :-1]
    rows = [(0, 1)] if planar else [(0, 1), (1, 0)]
    if conn >= 18 and not planar:
        rows += [(1, 1), (1, -1)]
    A, Bv = [], []
    for dy, dz in rows:
        if conn == 26 or (conn == 18 and (dy == 0 or dz == 0)):
            dxs = (-1, 0, 1)
        else:
            dxs = (0,)
        for dx in dxs:
            sa, sb = _pair_slices(m.shape, dy, dz, dx)
            both = m[sa] & m[sb]
            if not both.any():
                continue
            keep = both.copy()
            keep[..., 1:] &= ~both[..., :-1] | start[sa][..., 1:] | start[sb][..., 1:]
            A.append(rid[sa][keep])
            Bv.append(rid[sb][keep])
    if A:
        a = np.concatenate(A)
        b = np.concatenate(Bv)
    else:
        a = b = np.zeros(0, np.int64)
    parent = _uf(nr, a, b)
    return parent[rid], nr


def _groups(flat_lab: np.ndarray, wanted) -> list[tuple[int, np.ndarray]]:
    """Istenen etiketlerin hucre indeksleri (etiket basina)."""
    wanted = np.asarray(sorted(set(int(w) for w in wanted if int(w) > 0)), dtype=np.int64)
    if wanted.size == 0:
        return []
    idx = np.flatnonzero(np.isin(flat_lab, wanted))
    if idx.size == 0:
        return []
    lv = flat_lab[idx]
    order = np.argsort(lv, kind="stable")
    idx = idx[order]
    lv = lv[order]
    cut = np.flatnonzero(np.diff(lv)) + 1
    parts = np.split(idx, cut)
    keys = lv[np.r_[0, cut]]
    return [(int(k), p) for k, p in zip(keys, parts)]


def _family(nm: str) -> str:
    """Malzeme ailesi: sekil eki ve islenmis/yosunlu/catlak onekleri atilmis taban ad (oak_planks, oak_log -> oak)."""
    n = nm
    for p in ("waxed_", "exposed_", "weathered_", "oxidized_"):
        if n.startswith(p):
            n = n[len(p):]
    changed = True
    while changed:
        changed = False
        for p in ("stripped_", "polished_", "cut_", "chiseled_", "cracked_", "mossy_", "smooth_", "infested_", "cobbled_"):
            if n.startswith(p) and len(n) > len(p):
                n = n[len(p):]
                changed = True
    for s in ("_stairs", "_slab", "_wall", "_fence_gate", "_fence", "_trapdoor", "_door", "_button", "_pressure_plate",
              "_pillar"):
        if n.endswith(s):
            n = n[: -len(s)]
            break
    for w in WOODS:
        if n == w or (n.startswith(w + "_") and n[len(w) + 1:] in ("planks", "log", "wood", "hyphae", "stem", "mosaic", "block")):
            return w
    n = n.replace("bricks", "brick").replace("tiles", "tile")
    if n.endswith("_block") and n not in ("snow_block",):
        n = n[: -len("_block")]
    return n


def _dye(nm: str) -> str | None:
    for d in DYES:
        if nm.startswith(d + "_") and any(k in nm for k in ("concrete", "wool", "terracotta", "stained_glass", "carpet", "candle", "bed", "banner", "shulker")):
            if any(k in nm for k in ("concrete", "wool", "terracotta", "stained_glass")):
                return d
            return None
    return None


def _is_terracotta(n: str) -> bool:
    return n == "terracotta" or (n.endswith("_terracotta") and "glazed" not in n)


SOIL_TESTS = {
    "dirt": lambda n: n in DIRT,
    "dry": lambda n: n in DIRT or n in SAND or _is_terracotta(n),
    "farmland": lambda n: n == "farmland",
    "soul_sand": lambda n: n == "soul_sand",
    "nether": lambda n: n in DIRT or n in ("crimson_nylium", "warped_nylium", "soul_soil", "mycelium"),
    "wither": lambda n: n in DIRT or n in ("netherrack", "soul_sand", "soul_soil"),
    "azalea": lambda n: n in DIRT or n == "clay",
    "bamboo": lambda n: n in DIRT or n in SAND or n in ("gravel", "suspicious_gravel", "bamboo", "bamboo_sapling", "mud"),
    "dripleaf": lambda n: n in DIRT or n in ("clay", "big_dripleaf_stem", "big_dripleaf"),
    "cactus": lambda n: n in SAND or n == "cactus",
    "cane": lambda n: n == "sugar_cane" or n in DIRT or n in SAND,
}


def _plant_soil(nm: str) -> str:
    if nm in CROPS:
        return "farmland"
    if nm == "nether_wart":
        return "soul_sand"
    if nm in ("crimson_fungus", "warped_fungus", "crimson_roots", "warped_roots", "nether_sprouts"):
        return "nether"
    if nm == "wither_rose":
        return "wither"
    if nm in ("dead_bush", "short_dry_grass", "tall_dry_grass"):
        return "dry"
    if nm in ("azalea", "flowering_azalea", "mangrove_propagule"):
        return "azalea"
    if nm in ("bamboo", "bamboo_sapling"):
        return "bamboo"
    if nm in ("big_dripleaf", "big_dripleaf_stem", "small_dripleaf"):
        return "dripleaf"
    if nm == "cactus":
        return "cactus"
    if nm == "sugar_cane":
        return "cane"
    return "dirt"


# ====================================================================== oda
@dataclass
class Room:
    name: str
    source: str            # "meta" | "auto"
    kind: str
    cells: np.ndarray      # dolgulu dizide duz indeksler (gecilebilir hucreler)
    floor: np.ndarray      # alti dolu (zemin) olan hucreler
    bbox: tuple            # (yi0, yi1, zi0, zi1, xi0, xi1) dolgulu indeks, uclar dahil
    enclosure: float = 1.0
    attic: bool = False
    sealed: bool = False
    walk: bool = False
    standable: bool = False

    @property
    def floor_area(self) -> int:
        return int(self.floor.size)


@dataclass
class Facade:
    side: str
    has: np.ndarray        # (rows=y, cols) gorunur blok var mi
    depth: np.ndarray      # bakis yonunde ilk blogun derinligi
    pid: np.ndarray        # ilk blogun palet kimligi (yoksa 0)
    origin: tuple
    dims: tuple            # (Y, Z, X)

    def loc(self, r: int, c: int, d: int | None = None) -> list:
        x0, y0, z0 = self.origin
        Y, Z, X = self.dims
        d = int(self.depth[r, c]) if d is None else int(d)
        if self.side == "north":
            return [x0 + c, y0 + r, z0 + d]
        if self.side == "south":
            return [x0 + c, y0 + r, z0 + Z - 1 - d]
        if self.side == "west":
            return [x0 + d, y0 + r, z0 + c]
        return [x0 + X - 1 - d, y0 + r, z0 + c]


# ====================================================================== analiz baglami
class Ctx:
    """Bir yapinin denetim baglami: dolgulu yogun dizi, palet tablolari ve tembel (onbellekli) analizler."""

    def __init__(self, build, context: dict | None = None):
        self.build = build
        self.db = build.db
        self.context = dict(context or {})
        meta = getattr(build, "meta", None)
        self.meta = meta if isinstance(meta, dict) else {}
        self.stats: dict = {}
        self._mc: dict = {}
        (x0, y0, z0), core = build.dense()
        self.origin = (int(x0), int(y0), int(z0))
        self.core_ids = core
        self.Y, self.Z, self.X = core.shape
        self.palette = list(build.palette)
        self._tables()
        Y, Z, X = core.shape
        self.shape = (Y + PADB + PADT, Z + 2 * PADX, X + 2 * PADX)
        ids = np.zeros(self.shape, dtype=np.int32)
        ids[PADB:PADB + Y, PADX:PADX + Z, PADX:PADX + X] = core
        gl = self._ground_grid()
        ly = self.origin[1] + np.arange(self.shape[0]) - PADB
        terr = (ids == 0) & (ly[:, None, None] <= gl[None, :, :])
        ids[terr] = self.GROUND
        ids[:PADB] = self.GROUND
        self.ids = ids
        self.flat = ids.reshape(-1)
        self.SY = self.shape[1] * self.shape[2]
        self.SZ = self.shape[2]
        self.OFF = {"up": self.SY, "down": -self.SY, "south": self.SZ, "north": -self.SZ, "east": 1, "west": -1}
        self.core_sl = (slice(PADB, PADB + Y), slice(PADX, PADX + Z), slice(PADX, PADX + X))
        cm = np.zeros(self.shape, bool)
        cm[self.core_sl] = True
        self.core_mask = cm
        self.n_blocks = int(np.count_nonzero(self.T["block"][core]))

    # ------------------------------------------------------------------ zemin
    def _ground_grid(self) -> np.ndarray:
        Z2, X2 = self.shape[1], self.shape[2]
        gy = self.context.get("ground_y")
        if gy is None:
            gy = 0 if self.origin[1] <= 1 else self.origin[1] - 1
        self.ground_y = int(gy)
        grid = np.full((Z2, X2), int(gy), dtype=np.int64)
        hm = self.context.get("heightmap")
        self.water_grid = np.zeros((Z2, X2), bool)       # arazi su kolonlari (water_mask baglami; heightmap ile ayni dizin)
        self.water_level = self.context.get("water_level")
        if hm is not None:
            hm = np.asarray(hm)
            hx0, hz0 = self.context.get("heightmap_origin", (self.origin[0], self.origin[2]))
            zs = self.origin[2] + np.arange(Z2) - PADX - int(hz0)
            xs = self.origin[0] + np.arange(X2) - PADX - int(hx0)
            vz = np.nonzero((zs >= 0) & (zs < hm.shape[0]))[0]
            vx = np.nonzero((xs >= 0) & (xs < hm.shape[1]))[0]
            if vz.size and vx.size:
                grid[np.ix_(vz, vx)] = hm[np.ix_(zs[vz], xs[vx])]
                wm = self.context.get("water_mask")
                if wm is not None:
                    wm = np.asarray(wm, bool)
                    if wm.shape == hm.shape:
                        self.water_grid[np.ix_(vz, vx)] = wm[np.ix_(zs[vz], xs[vx])]
        self.ground_grid = grid
        return grid

    def underwater(self) -> np.ndarray:
        """3B: dunyada su olan hucreler (arazi su kolonu, zemin ustu ile su seviyesi arasi; planda keep)."""
        out = np.zeros(self.shape, bool)
        if self.water_level is None or not self.water_grid.any():
            return out
        ly = self.origin[1] + np.arange(self.shape[0]) - PADB
        col = self.water_grid[None, :, :] & (ly[:, None, None] <= int(self.water_level)) &             (ly[:, None, None] > self.ground_grid[None, :, :])
        return col & (self.ids == 0)

    # ------------------------------------------------------------------ palet tablolari
    def _tables(self) -> None:
        db = self.db
        pal = self.palette
        n = len(pal) + 1
        G = n - 1
        self.GROUND, self.n = G, n
        sid = np.full(n, -1, np.int64)
        flags = np.zeros(n, np.int64)
        emit = np.zeros(n, np.int16)
        sturdy = np.zeros(n, np.int16)
        natural = np.zeros(n, np.int8)
        names = ["?"] * n
        props: list[dict] = [{} for _ in range(n)]
        for i, s in enumerate(pal):
            if i == 0:
                names[i] = "keep"
                continue
            st = str(s)
            st = st[1:] if st.startswith("!") else st
            try:
                nm, pr = BDB.split_state(st)
                names[i], props[i] = nm.split(":", 1)[-1], pr
            except Exception:
                names[i] = st
            try:
                c = db.canonical(st)
                k = db.index[c]
            except Exception:
                continue
            sid[i] = k
            flags[i] = int(db.flags[k])
            emit[i] = int(db.light[k])
            sturdy[i] = int(db.sturdy[k])
            natural[i] = int(db.natural[k])
            nm, pr = BDB.split_state(c)
            names[i], props[i] = nm.split(":", 1)[-1], pr
        names[G] = "ground"
        flags[G] = BDB.FULL | BDB.OPAQUE | BDB.SOLID_RENDER
        sturdy[G] = 63
        natural[G] = 1
        self.sid, self.flags, self.emit, self.sturdy, self.natural = sid, flags, emit, sturdy, natural
        self.names, self.props = names, props
        self.T = self._tags()

    def _tags(self) -> dict[str, np.ndarray]:
        n, G = self.n, self.GROUND
        f, nm, pr = self.flags, self.names, self.props
        idx = np.arange(n)

        def fl(bit):
            return (f & bit) != 0

        def by(fn):
            return np.array([bool(fn(nm[i], pr[i])) for i in range(n)], dtype=bool)

        T: dict[str, np.ndarray] = {}
        keep = idx == 0
        ground = idx == G
        air = (fl(BDB.AIR) | (idx == 1)) & ~ground
        invalid = (self.sid < 0) & ~keep & ~ground & (idx != 1)
        block = ~keep & ~ground & ~air
        T.update(keep=keep, ground=ground, air=air, invalid=invalid, block=block)
        invisible = by(lambda a, p: a in ("barrier", "light", "structure_void"))
        T["visible"] = block & ~invisible
        for k, bit in (("full", BDB.FULL), ("opaque", BDB.OPAQUE), ("solidr", BDB.SOLID_RENDER), ("fluid", BDB.FLUID),
                       ("wlog", BDB.WATERLOGGED), ("gravity", BDB.GRAVITY), ("flammable", BDB.FLAMMABLE),
                       ("dangerous", BDB.DANGEROUS), ("plant", BDB.PLANT), ("repl", BDB.REPLACEABLE), ("sf", BDB.SUPPORT_FLOOR),
                       ("sw", BDB.SUPPORT_WALL), ("sc", BDB.SUPPORT_CEIL), ("double", BDB.DOUBLE), ("connect", BDB.CONNECT),
                       ("be", BDB.BLOCK_ENTITY), ("redstone", BDB.REDSTONE)):
            T[k] = fl(bit) & ~keep
        T["full"] |= ground
        T["solidr"] |= ground
        T["lava"] = by(lambda a, p: a == "lava")
        T["fire"] = by(lambda a, p: a in ("fire", "soul_fire"))
        T["water_src"] = by(lambda a, p: a in ("water", "bubble_column")) | (T["fluid"] & T["plant"] & ~T["wlog"])
        T["has_water"] = T["water_src"] | T["wlog"]
        T["wl_false"] = by(lambda a, p: p.get("waterlogged") == "false")
        has_wl_prop = by(lambda a, p: "waterlogged" in p)
        carpet = by(lambda a, p: a.endswith("_carpet") or (a == "pale_moss_carpet"))
        T["carpet"] = carpet
        T["leaves"] = by(lambda a, p: a.endswith("_leaves"))
        T["glass"] = by(lambda a, p: "glass" in a)
        T["window"] = by(lambda a, p: "glass" in a or a.endswith("_bars"))
        T["door"] = by(lambda a, p: a.endswith("_door") and "half" in p)
        T["door_lower"] = T["door"] & by(lambda a, p: p.get("half") == "lower")
        T["door_upper"] = T["door"] & by(lambda a, p: p.get("half") == "upper")
        T["bed"] = by(lambda a, p: a.endswith("_bed") and "part" in p)
        T["dplant"] = by(lambda a, p: "half" in p and not a.endswith("_door")) & T["double"] & T["plant"]
        T["stairs"] = by(lambda a, p: a.endswith("_stairs"))
        T["stairs_bottom"] = T["stairs"] & by(lambda a, p: p.get("half") == "bottom")
        T["stairs_top"] = T["stairs"] & by(lambda a, p: p.get("half") == "top")
        T["slab"] = by(lambda a, p: a.endswith("_slab") and p.get("type") != "double")
        T["dirt_path"] = by(lambda a, p: a == "dirt_path")
        openable = by(lambda a, p: a.endswith(("_door", "_fence_gate", "_trapdoor")))
        T["openable"] = openable
        climb = by(lambda a, p: a in ("ladder", "vine", "scaffolding", "twisting_vines", "twisting_vines_plant", "weeping_vines",
                                      "weeping_vines_plant", "cave_vines", "cave_vines_plant")) | T["water_src"]
        T["climb"] = climb
        small = (T["sf"] | T["sw"] | T["sc"]) & ~T["opaque"] & ~T["full"] & ~T["double"] & ~T["connect"]
        snow = by(lambda a, p: a == "snow")
        snow_thin = snow & by(lambda a, p: p.get("layers", "1").isdigit() and int(p.get("layers", "1")) <= 3)
        passable = keep | air | by(lambda a, p: a in ("light", "structure_void")) | (T["repl"] & ~T["fluid"] & ~snow) | snow_thin | (T["plant"] & ~T["opaque"] & ~T["fluid"]) \
            | small | carpet | openable | climb | by(lambda a, p: a in ("cobweb", "powder_snow", "structure_void", "light"))
        passable &= ~T["lava"] & ~T["fire"] & ~ground
        T["passable"] = passable
        T["floorish"] = ~passable & ~T["lava"] & ~T["fire"] & ~keep
        T["fluid_open"] = air | (T["repl"] & ~T["fluid"] & ~has_wl_prop) | (small & ~has_wl_prop & ~T["fluid"]) | carpet | T["fire"]
        T["fluid_open"] &= ~ground
        up_down = (self.sturdy & (FACE_BIT["up"] | FACE_BIT["down"])) != 0
        T["cover"] = T["solidr"] | (T["opaque"] & ~T["full"] & ~carpet & up_down)
        T["light_solid"] = T["solidr"] | by(lambda a, p: a == "tinted_glass")
        T["light_src"] = (self.emit >= 10) & block
        spawn_floor = np.array([LT.is_spawn_floor(nm[i], int(self.sturdy[i]), int(self.emit[i])) for i in range(n)], bool)
        T["spawn_floor"] = spawn_floor & (block | ground) & ~invalid
        thick_snow = snow & ~by(lambda a, p: p.get("layers", "1") == "1")
        T["spawn_empty"] = keep | air | (T["repl"] & ~T["fluid"] & ~T["redstone"] & ~thick_snow & ~by(lambda a, p: a == "light")) \
            | (T["plant"] & ~T["opaque"] & ~T["fluid"]) \
            | by(lambda a, p: a.endswith(("_sign", "_banner", "torch")) and "hanging" not in a)
        T["spawn_empty"] &= ~T["lava"] & ~T["fire"]
        T["post_v"] = by(lambda a, p: (a.endswith("_fence") or a.endswith("_wall") or "glass_pane" in a or a.endswith("_bars")
                                        or ("chain" in a and p.get("axis") == "y")
                                        or (a.endswith(("end_rod", "lightning_rod")) and p.get("facing") in ("up", "down"))))
        # 'keep' (plana dokunulmayan hucre) zemin ustunde neredeyse her zaman havadir: destek sayilmaz
        # (mevcut bir yapiyi susluyorsan context["keep_supports"]=True ver).
        self.keep_ok = keep if self.context.get("keep_supports") else np.zeros(n, bool)
        T["solidish"] = ((T["full"] | T["connect"] | (T["opaque"] & ~(T["sf"] | T["sw"] | T["sc"])) | (self.sturdy != 0))
                         & ~carpet & ~snow) | ground | self.keep_ok
        light_like = by(lambda a, p: _is_light_name(a))
        T["light_like"] = light_like
        T["furniture"] = by(lambda a, p: any(k in a for k in FURN_ITEMS + FURN_SHAPES)) & ~light_like & block
        T["decor"] = T["visible"] & ~T["full"]
        T["natural"] = (self.natural > 0) & block
        T["landscape"] = (T["plant"] | T["leaves"] | T["dirt_path"] | by(lambda a, p: a in DIRT or a in ("gravel", "moss_carpet"))) & block
        self.light_occ = np.where(T["opaque"] & ~T["solidr"] & ~carpet & ~T["full"], self.sturdy, 0).astype(np.uint8)
        fam = [""] * n
        dye = [None] * n
        for i in range(n):
            if block[i]:
                fam[i] = _family(nm[i])
                dye[i] = _dye(nm[i])
        self.family, self.dye = fam, dye
        decor_name = light_like | by(lambda a, p: any(k in a for k in FURN_ITEMS + (
            "glass", "_bars", "chain", "_door", "button", "lever", "rail", "redstone_wire", "repeater", "comparator", "flower",
            "sapling", "short_grass", "tall_grass", "fern", "vine", "lichen", "rose", "tulip", "poppy", "dandelion", "orchid",
            "allium", "bluet", "daisy", "cornflower", "lily", "bush", "mushroom", "petals", "kelp", "seagrass", "coral",
            "bamboo", "cactus", "sugar_cane", "roots", "moss_carpet", "pressure_plate", "tripwire", "ladder")) or a == "grass_block")
        T["structural"] = (block & ~decor_name & ~T["plant"] & ~T["leaves"] & ~T["fluid"]) | (block & T["wlog"] & ~decor_name & ~T["plant"])
        return T

    # ------------------------------------------------------------------ maske / konum yardimcilari
    def m(self, tag: str) -> np.ndarray:
        """3B maske (dolgulu dizide) — palet etiketinden, onbellekli."""
        v = self._mc.get(tag)
        if v is None:
            v = self.T[tag][self.ids]
            self._mc[tag] = v
        return v

    def cm(self, tag: str) -> np.ndarray:
        """Yalniz cekirdek (yapinin kendi kutusu) icindeki maske."""
        return self.m(tag) & self.core_mask

    def loc(self, yi: int, zi: int, xi: int) -> list:
        return [self.origin[0] + int(xi) - PADX, self.origin[1] + int(yi) - PADB, self.origin[2] + int(zi) - PADX]

    def to_pad(self, x: float, y: float, z: float) -> tuple[int, int, int]:
        return (int(math.floor(y)) - self.origin[1] + PADB, int(math.floor(z)) - self.origin[2] + PADX,
                int(math.floor(x)) - self.origin[0] + PADX)

    def inside(self, yi, zi, xi) -> bool:
        return 0 <= yi < self.shape[0] and 0 <= zi < self.shape[1] and 0 <= xi < self.shape[2]

    def sample(self, idx, k: int = 6) -> list:
        idx = np.asarray(idx).ravel()
        if idx.size == 0:
            return []
        if idx.size > k:
            idx = idx[np.linspace(0, idx.size - 1, k).round().astype(np.int64)]
        yi, zi, xi = np.unravel_index(idx, self.shape)
        return [self.loc(a, b, c) for a, b, c in zip(yi, zi, xi)]

    def sample_mask(self, mask: np.ndarray, k: int = 6) -> list:
        return self.sample(np.flatnonzero(mask), k)

    def nb(self, idx: np.ndarray, d: str, steps: int = 1) -> np.ndarray:
        return idx + self.OFF[d] * steps

    def pid_name(self, p: int) -> str:
        return self.names[int(p)]

    def names_of(self, pids, k: int = 5) -> list:
        u, c = np.unique(np.asarray(pids), return_counts=True)
        order = np.argsort(-c)
        return [self.names[int(u[i])] for i in order[:k]]

    def finding(self, cid: str, sev: str, msg: str, fix: str, idx=None, positions=None, count: int | None = None,
                data: dict | None = None) -> Finding:
        pos = positions if positions is not None else (self.sample(idx) if idx is not None else [])
        cnt = count if count is not None else (int(np.asarray(idx).size) if idx is not None else len(pos))
        return Finding(cid, sev, msg, fix, pos, int(cnt), dict(data or {}))

    # ------------------------------------------------------------------ tembel analizler
    @cached_property
    def P(self) -> np.ndarray:
        return self.m("passable")

    @cached_property
    def open_sky(self) -> np.ndarray:
        return LT.open_to_sky(self.m("cover"))

    @cached_property
    def outdoorish(self) -> np.ndarray:
        """Gokyuzune acik ya da acik gokyuzune gecilebilir hucrelerden en cok 3 yatay adim uzak (yan gok isigi)."""
        P = self.P
        o = self.open_sky & P
        r = o.copy()
        for _ in range(3):
            g = r.copy()
            g[:, 1:, :] |= r[:, :-1, :]
            g[:, :-1, :] |= r[:, 1:, :]
            g[:, :, 1:] |= r[:, :, :-1]
            g[:, :, :-1] |= r[:, :, 1:]
            r = g & P
        return self.open_sky | r

    @cached_property
    def blight(self) -> np.ndarray:
        emit = self.emit[self.ids]
        return LT.propagate(emit, self.m("light_solid"), self.light_occ[self.ids])

    @cached_property
    def air_outside(self) -> np.ndarray:
        """Disariya (dolgu sinirina) gecilebilir hucrelerle bagli hava (kapilar gecilebilir)."""
        P = self.P
        lab, _ = label(P, 6)
        border = np.zeros(self.shape, bool)
        border[-1] = True
        border[:, 0, :] = border[:, -1, :] = True
        border[:, :, 0] = border[:, :, -1] = True
        outs = np.unique(lab[border & P])
        outs = outs[outs > 0]
        return np.isin(lab, outs) & P

    @cached_property
    def walk(self) -> dict:
        """Yuruyus erisimi: dis halkadan (zemin seviyesi) yurume, 1 blok basamak/zipla, merdiven/ladder/su ile tirmanma,
        kenardan dusme. Donus: S (durulabilir), reach (erisilen), B (2 blok bos)."""
        P, C = self.P, self.m("climb")
        Bm = np.zeros_like(P)
        Bm[:-1] = P[:-1] & P[1:]
        F = ~P & ~self.m("lava") & ~self.m("fire")
        fb = np.zeros_like(P)
        fb[1:] = F[:-1]
        cb = np.zeros_like(P)
        cb[1:] = C[:-1]
        S = Bm & (fb | C | cb)
        H2 = np.zeros_like(P)
        H2[:-2] = P[2:]
        rid, nr = _xruns(S)
        res = {"S": S, "B": Bm, "reach": np.zeros_like(S)}
        if nr == 0:
            return res
        A, Bv = [], []

        def add(off, ma, mb, extra=None):
            sa, sb = _pair_slices(self.shape, *off)
            both = ma[sa] & mb[sb]
            if extra is not None:
                both &= extra(sa, sb)
            if both.any():
                A.append(rid[sa][both])
                Bv.append(rid[sb][both])

        add((0, 1, 0), S, S)
        SH = S & H2
        for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            add((1, dz, dx), SH, S)
        add((1, 0, 0), S, S, extra=lambda sa, sb: C[sa] | C[sb])
        a = np.concatenate(A) if A else np.zeros(0, np.int64)
        b = np.concatenate(Bv) if Bv else np.zeros(0, np.int64)
        parent = _uf(nr, a, b)
        root = parent[rid]
        rootf = root.reshape(-1)
        # dusme kenarlari (yonlu)
        U = Bm & ~S
        land = np.full(self.shape, -1, np.int32)
        for y in range(1, self.shape[0]):
            land[y] = np.where(S[y], y, np.where(U[y], land[y - 1], -1))
        landf = land.reshape(-1)
        fa, fz = [], []
        for d in ("north", "south", "east", "west"):
            _, dz, dx = DIRV[d]
            sa, sb = _pair_slices(self.shape, 0, dz, dx)
            both = S[sa] & U[sb]
            if not both.any():
                continue
            mm = np.zeros(self.shape, bool)
            mm[sa] = both
            ai = np.flatnonzero(mm)
            bi = ai + self.OFF[d]
            ty = landf[bi]
            ok = ty >= 0
            ai, bi, ty = ai[ok], bi[ok], ty[ok].astype(np.int64)
            ti = bi - (bi // self.SY - ty) * self.SY
            fa.append(rootf[ai])
            fz.append(rootf[ti])
        ring = np.ones(self.shape[1:], bool)
        ring[PADX:PADX + self.Z, PADX:PADX + self.X] = False
        starts = set(np.unique(root[S & ring[None, :, :]]).tolist())
        for p in self.context.get("entrances") or []:
            try:
                yi, zi, xi = self.to_pad(*p[:3])
            except Exception:
                continue
            for k in range(4):
                if self.inside(yi + k, zi, xi) and S[yi + k, zi, xi]:
                    starts.add(int(root[yi + k, zi, xi]))
                    break
        starts.discard(0)
        adj: dict[int, set] = defaultdict(set)
        if fa:
            pa = np.concatenate(fa)
            pz = np.concatenate(fz)
            ne = pa != pz
            if ne.any():
                pairs = np.unique(np.stack([pa[ne], pz[ne]], axis=1), axis=0)
                for u, v in pairs.tolist():
                    adj[u].add(v)
        seen = set(starts)
        stack = list(starts)
        while stack:
            u = stack.pop()
            for v in adj.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    stack.append(v)
        lut = np.zeros(nr + 1, bool)
        if seen:
            lut[np.fromiter(seen, dtype=np.int64)] = True
        res["reach"] = lut[root] & S
        res["root"] = root
        return res

    @cached_property
    def rooms(self) -> list[Room]:
        """Odalar: meta 'rooms' kutulari + otomatik (ortulu, duvarla cevrili, kapisiz gecilebilir hava bilesenleri)."""
        P = self.P
        opn = self.m("openable")
        shape = self.shape
        below_floor = np.zeros(shape, bool)
        below_floor[1:] = ~P[:-1]
        bff = below_floor.reshape(-1)
        rooms: list[Room] = []
        # --- meta odalari
        meta_cells = []
        for i, r in enumerate(self.meta.get("rooms") or []):
            box = r.get("box") if isinstance(r, dict) else None
            if not box or len(box) != 6:
                continue
            x0, y0, z0, x1, y1, z1 = (int(v) for v in box)
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            z0, z1 = sorted((z0, z1))
            a = self.to_pad(x0, y0, z0)
            b = self.to_pad(x1, y1, z1)
            lo = [max(0, a[k]) for k in range(3)]
            hi = [min(shape[k] - 1, b[k]) for k in range(3)]
            if any(lo[k] > hi[k] for k in range(3)):
                continue
            sl = tuple(slice(lo[k], hi[k] + 1) for k in range(3))
            sub = (P & ~opn)[sl]
            gy, gz, gx = np.nonzero(sub)
            if gy.size == 0:
                continue
            cells = np.ravel_multi_index((gy + lo[0], gz + lo[1], gx + lo[2]), shape)
            nm = str(r.get("name") or r.get("ad") or f"oda{i + 1}")
            kind = str(r.get("type") or r.get("kind") or r.get("tur") or "")
            rooms.append(Room(nm, "meta", kind, cells, cells[bff[cells]], (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])))
            meta_cells.append(cells)
        meta_all = np.concatenate(meta_cells) if meta_cells else np.zeros(0, np.int64)
        # --- otomatik odalar
        mask = P & ~opn & ~self.open_sky & self.core_mask
        lab, _ = label(mask, 6)
        flat = lab.reshape(-1)
        nfl = np.bincount(flat[bff & mask.reshape(-1)], minlength=1)
        cand = np.flatnonzero(nfl >= 9)
        cand = cand[cand > 0]
        if cand.size > 400:
            cand = cand[np.argsort(-nfl[cand])[:400]]
        open_ext = (P & self.open_sky).reshape(-1)
        cover_stairs = (self.m("stairs") | self.m("slab")).reshape(-1)
        covered_air = (P & ~self.open_sky).reshape(-1)
        for lbl, cells in _groups(flat, cand):
            yi, zi, xi = np.unravel_index(cells, shape)
            if zi.max() - zi.min() < 2 or xi.max() - xi.min() < 2 or yi.max() - yi.min() < 1:
                continue
            if meta_all.size and np.isin(cells, meta_all).mean() > 0.5:
                continue
            fl = cells[bff[cells]]
            closed = opened = 0
            for d in ("north", "south", "east", "west"):
                nbi = fl + self.OFF[d]
                out = flat[nbi] != lbl
                opened += int(np.count_nonzero(open_ext[nbi] & out))
                closed += int(np.count_nonzero(~open_ext[nbi] & out))
            enc = closed / max(1, closed + opened)
            if enc < 0.7:
                continue
            # cati arasi: tepe hucrelerin ustu merdiven/levha VE zemini baska bir ortulu hacmin tavani
            top_mask = flat[cells + self.SY] != lbl
            tops = cells[top_mask]
            under_roof = bool(tops.size and cover_stairs[tops + self.SY].mean() >= 0.5)
            attic = under_roof and bool(fl.size and covered_air[np.maximum(fl - 2 * self.SY, 0)].mean() >= 0.5)
            p0 = self.loc(int(yi.min()), int(zi.min()), int(xi.min()))
            rooms.append(Room(f"oda@{p0[0]},{p0[1]},{p0[2]}", "auto", "", cells, fl,
                              (int(yi.min()), int(yi.max()), int(zi.min()), int(zi.max()), int(xi.min()), int(xi.max())),
                              enclosure=enc, attic=attic))
        out = self.air_outside.reshape(-1)
        wk = self.walk
        reach = wk["reach"].reshape(-1)
        S = wk["S"].reshape(-1)
        for r in rooms:
            r.sealed = not bool(out[r.cells].any())
            r.walk = bool(reach[r.cells].any())
            r.standable = bool(S[r.cells].any())
        return rooms

    def used_rooms(self) -> list[Room]:
        """Oyuncunun kullandigi odalar: meta odalari + disariyla baglantili otomatik odalar."""
        return [r for r in self.rooms if r.source == "meta" or not r.sealed]

    @cached_property
    def facades(self) -> dict[str, Facade]:
        core = self.ids[self.core_sl]
        vis = self.T["visible"][core]
        Y, Z, X = core.shape
        out = {}
        for side in ("north", "south", "west", "east"):
            if side in ("north", "south"):
                v = vis if side == "north" else vis[:, ::-1, :]
                has = v.any(axis=1)
                d = np.argmax(v, axis=1)
                zz = d if side == "north" else (Z - 1 - d)
                yy, xx = np.indices((Y, X))
                pid = core[yy, zz, xx]
            else:
                v = vis if side == "west" else vis[:, :, ::-1]
                has = v.any(axis=2)
                d = np.argmax(v, axis=2)
                xx = d if side == "west" else (X - 1 - d)
                yy, zz = np.indices((Y, Z))
                pid = core[yy, zz, xx]
            pid = np.where(has, pid, 0)
            out[side] = Facade(side, has, d, pid, self.origin, (Y, Z, X))
        return out

    # ------------------------------------------------------------------ destek kurallari
    @cached_property
    def rules(self) -> list:
        """Palet girdisi basina (tur, kurallar) — attach_rule onbellegi."""
        return [self.attach_rule(i) for i in range(self.n)]

    @cached_property
    def att_table(self) -> np.ndarray:
        """Destek isteyen (tutturulan/asilan) bloklar + kapilar: kendi kontrolleri bildirir."""
        t = np.array([k is not None for k, _ in self.rules], bool)
        return t | self.T["door"]

    def cond_table(self, cond: str, own: int = -1) -> np.ndarray:
        """Destek kosulu icin palet tablosu (destek hucresinin palet kimligine gore)."""
        T, n = self.T, self.n
        unknown = self.keep_ok
        if cond.startswith("sturdy:") or cond.startswith("center:"):
            kind, face = cond.split(":")
            ok = (self.sturdy & FACE_BIT[face]) != 0
            if kind == "center" and face in ("up", "down"):
                ok = ok | T["post_v"]
            return ok | T["ground"] | unknown
        if cond == "solid":
            return T["solidish"]
        if cond == "nonair":
            return ~T["air"] & (~T["keep"] | unknown)
        if cond.startswith("soil:"):
            fn = SOIL_TESTS[cond[5:]]
            return np.array([fn(self.names[i]) for i in range(n)], bool) | T["ground"] | unknown
        if cond.startswith("names:"):
            s = set(cond[6:].split(","))
            return np.array([self.names[i] in s for i in range(n)], bool) | unknown
        if cond.startswith("suffix:"):
            s = cond[7:]
            return np.array([self.names[i].endswith(s) for i in range(n)], bool) | unknown
        if cond == "same":
            return np.array([i == own or (own >= 0 and self.names[i] == self.names[own]) for i in range(n)], bool) | unknown
        if cond == "leaves":
            return T["leaves"] | unknown
        if cond == "water":
            return T["has_water"] | np.array([self.names[i] in ("ice", "packed_ice", "blue_ice", "frosted_ice") for i in range(n)], bool) | unknown
        raise ValueError(cond)

    def attach_rule(self, i: int):
        """Palet girdisi i icin (tur, kurallar). tur: 'attach' | 'hang' | 'chain' | 'multi' | None.
        kurallar: [(destek yonu, kosul)] — biri saglanirsa yeterli. Kosuldaki yuz destegin bize bakan yuzudur."""
        a, p = self.names[i], self.props[i]
        if not self.T["block"][i] or self.T["invalid"][i]:
            return None, []
        fac = p.get("facing")

        def wall(cond="sturdy"):
            if fac not in DIRV:
                return []
            d = OPP[fac]
            return [(d, f"{cond}:{fac}" if cond in ("sturdy", "center") else cond)]

        def down(cond="sturdy"):
            return [("down", f"{cond}:up" if cond in ("sturdy", "center") else cond)]

        def up(cond="sturdy"):
            return [("up", f"{cond}:down" if cond in ("sturdy", "center") else cond)]

        if a.endswith("_door") or a.endswith("_bed") or p.get("half") == "upper":
            return None, []
        if "chain" in a and p.get("axis") == "y":
            return "chain", up("nonair")
        if a.endswith("lantern") and "hanging" in p:
            return ("hang", up("center")) if p.get("hanging") == "true" else ("attach", down("center"))
        if a.endswith("_wall_hanging_sign"):
            if fac not in CW:
                return None, []
            return "attach", [(CW[fac], f"sturdy:{CCW[fac]}"), (CCW[fac], f"sturdy:{CW[fac]}"),
                              (CW[fac], "suffix:_wall_hanging_sign"), (CCW[fac], "suffix:_wall_hanging_sign")]
        if a.endswith("_hanging_sign"):
            return "hang", up("center")
        if a.endswith("wall_torch"):
            return "attach", wall()
        if a.endswith("torch"):
            return "attach", down("center")
        if a == "candle" or a.endswith("_candle"):
            return "attach", down("center")
        if a.endswith("_wall_sign"):
            return "attach", wall("solid")
        if a.endswith("_sign"):
            return "attach", down("solid")
        if a.endswith("_wall_banner"):
            return "attach", wall("solid")
        if a.endswith("_banner"):
            return "attach", down("solid")
        if a in ("ladder", "tripwire_hook") or a.endswith(("_coral_wall_fan", "amethyst_bud", "amethyst_cluster")):
            return "attach", wall()
        if a.endswith("_button") or a == "lever":
            face = p.get("face")
            if face == "floor":
                return "attach", down()
            if face == "ceiling":
                return "attach", up()
            return "attach", wall()
        if a == "bell":
            att = p.get("attachment")
            if att == "floor":
                return "attach", down()
            if att == "ceiling":
                return "hang", up("center")
            if fac in DIRV:
                return "attach", [(fac, f"sturdy:{OPP[fac]}")]
            return None, []
        if a == "cocoa":
            if fac in DIRV:
                return "attach", [(fac, "names:jungle_log,jungle_wood,stripped_jungle_log,stripped_jungle_wood")]
            return None, []
        if a.endswith("_carpet") and a != "pale_moss_carpet":
            return "attach", down("nonair")
        if a.endswith("_pressure_plate"):
            return "attach", down("center")
        if a in ("rail", "powered_rail", "detector_rail", "activator_rail", "redstone_wire", "repeater", "comparator", "snow"):
            return "attach", down()
        if a == "cake" or a.endswith("candle_cake"):
            return "attach", down("solid")
        if a.endswith(("_coral", "_coral_fan")):
            return "attach", down()
        if a == "sea_pickle":
            return "attach", down("solid")
        if a in ("spore_blossom", "hanging_roots"):
            return "hang", up()
        if a in ("cave_vines", "cave_vines_plant"):
            return "hang", up() + up("names:cave_vines,cave_vines_plant")
        if a in ("weeping_vines", "weeping_vines_plant"):
            return "hang", up() + up("names:weeping_vines,weeping_vines_plant")
        if a in ("twisting_vines", "twisting_vines_plant"):
            return "attach", down() + down("names:twisting_vines,twisting_vines_plant")
        if a == "pale_hanging_moss":
            return "hang", up() + up("names:pale_hanging_moss") + up("leaves")
        if a in ("pointed_dripstone", "sulfur_spike"):
            if p.get("vertical_direction") == "down":
                return "hang", up() + up("same")
            return "attach", down() + down("same")
        if a == "mangrove_propagule" and p.get("hanging") == "true":
            return "hang", up("names:mangrove_leaves")
        if a in ("vine", "glow_lichen", "sculk_vein", "resin_clump"):
            return "multi", []
        if a in ("lily_pad", "frogspawn"):
            return "attach", down("water")
        if a in ("brown_mushroom", "red_mushroom", "leaf_litter"):
            return "attach", down()
        if a in ("seagrass", "tall_seagrass"):
            return "attach", down()
        if a in ("kelp", "kelp_plant"):
            return "attach", down() + down("names:kelp,kelp_plant")
        if a == "cactus_flower":
            return "attach", down("center") + down("names:cactus,farmland")
        if a in ("big_dripleaf", "big_dripleaf_stem", "bamboo_sapling", "cactus", "sugar_cane") or \
                (self.T["plant"][i] and self.T["sf"][i]):
            return "attach", down(f"soil:{_plant_soil(a)}")
        return None, []


# ====================================================================== kontroller
def _sev_by(n: int, major_at: int) -> str:
    return "major" if n >= major_at else "minor"


@check("empty_build", "Yapı boş: hiç blok yok.", "teknik")
def c_empty_build(ctx: Ctx) -> list[Finding]:
    if ctx.n_blocks == 0:
        return [ctx.finding("empty_build", "critical", "Yapıda hiç blok yok.", "Önce b.fill/b.set ile blokları yerleştir.")]
    return []


@check("unknown_blocks", "Palette 26.3 blok veritabanında olmayan ya da geçersiz özellikli durum var.", "teknik")
def c_unknown_blocks(ctx: Ctx) -> list[Finding]:
    bad = np.flatnonzero(ctx.T["invalid"])
    if bad.size == 0:
        return []
    core_flat = ctx.ids[ctx.core_sl].reshape(-1)
    cnt = np.bincount(core_flat, minlength=ctx.n)
    used = [int(p) for p in bad if cnt[p] > 0]
    if not used:
        return []
    names = [ctx.palette[p] for p in used]
    sugg = []
    for s in names[:4]:
        nm = s.lstrip("!").split("[", 1)[0]
        sg = ctx.db.suggest(nm) if hasattr(ctx.db, "suggest") else []
        if sg:
            sugg.append(f"{nm} → {', '.join(sg)}")
    mask = np.isin(ctx.ids, used) & ctx.core_mask
    return [ctx.finding("unknown_blocks", "critical",
                        f"26.3'te olmayan/geçersiz blok durumu: {', '.join(names[:5])}" + (f" (öneri: {'; '.join(sugg)})" if sugg else ""),
                        "db.has_block/db.suggest ile doğru adı bul, özellikleri db.blocks[ad]['props'] ile doğrula ve bloğu yeniden yaz.",
                        idx=np.flatnonzero(mask), data={"states": names[:10]})]


@check("orphan_block_entity", "Blok varlığı (NBT) blok varlığı taşımayan bir hücreye yazılmış.", "teknik")
def c_orphan_block_entity(ctx: Ctx) -> list[Finding]:
    bad = []
    for (x, y, z) in list(ctx.build.block_entities.keys()):
        yi, zi, xi = ctx.to_pad(x, y, z)
        if not ctx.inside(yi, zi, xi):
            bad.append([x, y, z])
            continue
        p = int(ctx.ids[yi, zi, xi])
        if not ctx.T["be"][p]:
            bad.append([int(x), int(y), int(z)])
    if not bad:
        return []
    return [ctx.finding("orphan_block_entity", "minor", f"{len(bad)} blok varlığı (NBT) blok varlığı olmayan hücrede.",
                        "set_block_entity'yi yalnız sandık/tabela/fıçı/saksı gibi blok varlıklı bloklara uygula ya da hücreye doğru bloğu koy.",
                        positions=bad[:6], count=len(bad))]


DANGEROUS_ENTITIES = ("tnt", "tnt_minecart", "end_crystal", "fireball", "small_fireball", "wither_skull", "lightning_bolt")


@check("dangerous_blocks", "TNT, lav, ateş gibi tehlikeli blok ya da varlık var.", "teknik")
def c_dangerous_blocks(ctx: Ctx) -> list[Finding]:
    out = []
    mask = ctx.cm("dangerous")
    idx = np.flatnonzero(mask)
    if idx.size:
        names = ctx.names_of(ctx.flat[idx])
        out.append(ctx.finding("dangerous_blocks", "critical", f"Tehlikeli blok: {', '.join(names)} ({idx.size} hücre).",
                               "TNT/lav/ateş kullanma: ışık için fener/deniz feneri, sıcaklık görüntüsü için kamp ateşi veya magma bloğu kullan.",
                               idx=idx, data={"blocks": names}))
    ents = [e for e in ctx.build.entities if str(e.get("type", "")).split(":")[-1] in DANGEROUS_ENTITIES]
    if ents:
        out.append(ctx.finding("dangerous_blocks", "critical", f"{len(ents)} tehlikeli varlık (TNT/kristal vb.).",
                               "Tehlikeli varlıkları kaldır.", positions=[[int(math.floor(v)) for v in e["pos"]] for e in ents[:6]],
                               count=len(ents)))
    return out


def _dilate(mask: np.ndarray, rx: int = 0, ry_down: int = 0, ry_up: int = 0, rz: int = 0) -> np.ndarray:
    """Kutu genisletme: hucre, kaynaktan x+-rx, z+-rz, y'de [-ry_down, +ry_up] uzakliktaysa True."""
    out = mask.copy()
    # x
    if rx:
        acc = out.copy()
        for d in range(1, rx + 1):
            acc[:, :, d:] |= out[:, :, :-d]
            acc[:, :, :-d] |= out[:, :, d:]
        out = acc
    if rz:
        acc = out.copy()
        for d in range(1, rz + 1):
            acc[:, d:, :] |= out[:, :-d, :]
            acc[:, :-d, :] |= out[:, d:, :]
        out = acc
    if ry_up or ry_down:
        acc = out.copy()
        for d in range(1, ry_up + 1):      # kaynagin d yukarisi
            acc[d:] |= out[:-d]
        for d in range(1, ry_down + 1):    # kaynagin d asagisi
            acc[:-d] |= out[d:]
        out = acc
    return out


@check("fire_hazard", "Ateş/lav yanıcı bloklara yakın (yangın yayılır); yanan kamp ateşinin hemen üstü yanıcı.", "teknik")
def c_fire_hazard(ctx: Ctx) -> list[Finding]:
    out = []
    flam = ctx.cm("flammable")
    src = (ctx.m("fire") | ctx.m("lava")) & ctx.core_mask
    if src.any() and flam.any():
        zone = _dilate(src, rx=2, rz=2, ry_down=1, ry_up=4)
        risk = flam & zone
        if risk.any():
            idx = np.flatnonzero(risk)
            out.append(ctx.finding("fire_hazard", "critical", f"Ateş/lav {idx.size} yanıcı bloğa yangın yayabilecek kadar yakın.",
                                   "Ateş kaynağını kaldır ya da yanıcı bloklarla arasına en az 2-3 blok taş/tuğla koy.", idx=idx))
    camp = np.array([ctx.names[i].endswith("campfire") and ctx.props[i].get("lit") == "true" for i in range(ctx.n)], bool)
    if camp.any():
        cm = camp[ctx.ids] & ctx.core_mask
        if cm.any():
            zone = _dilate(cm, ry_up=2) & ~cm
            risk = flam & zone
            if risk.any():
                out.append(ctx.finding("fire_hazard", "minor", "Yanan kamp ateşinin hemen üstünde yanıcı blok var.",
                                       "Kamp ateşinin üstünü 2-3 blok boş bırak ya da bacayı taş/tuğladan yap.",
                                       idx=np.flatnonzero(risk)))
    return out


@check("fluid_leak", "Su/lav kapalı hacimde değil: açık ya da plan dışı komşuya taşar.", "teknik")
def c_fluid_leak(ctx: Ctx) -> list[Finding]:
    out = []
    keep = ctx.m("keep")
    ks = bool(ctx.context.get("keep_supports"))
    openm = ctx.m("fluid_open") | (keep & (not ks))   # zemin ustundeki 'keep' = hava
    unk = keep & ks
    for tag, sev_def, sev_unk, nm in (("water_src", "major", "minor", "Su"), ("lava", "critical", "major", "Lav")):
        src = ctx.cm(tag)
        if not src.any():
            continue
        idx = np.flatnonzero(src)
        o = np.zeros(idx.size, bool)
        u = np.zeros(idx.size, bool)
        of, uf = openm.reshape(-1), unk.reshape(-1)
        for d in ("down", "north", "south", "east", "west"):
            j = idx + ctx.OFF[d]
            o |= of[j]
            u |= uf[j]
        if o.any():
            out.append(ctx.finding("fluid_leak", sev_def, f"{nm} kapalı değil: {int(o.sum())} sıvı hücresinin yanı/altı açık, taşar.",
                                   "Havuzun yanlarını ve tabanını dolu bloklarla kapat; sıvıyı yalnız kenarları ve altı kapalı havuza koy.",
                                   idx=idx[o]))
        u &= ~o
        if u.any():
            out.append(ctx.finding("fluid_leak", sev_unk, f"{nm} plan sınırında/‘keep’ hücresine komşu ({int(u.sum())} hücre): dünyada sızabilir.",
                                   "Havzanın kenarını ve tabanını da plana dolu blok olarak ekle (araziye güvenme).", idx=idx[u]))
    return out


@check("fluid_mix", "Su ile lav temas ediyor (taş/obsidyen oluşur).", "teknik")
def c_fluid_mix(ctx: Ctx) -> list[Finding]:
    lava = ctx.cm("lava")
    if not lava.any():
        return []
    water = ctx.m("has_water")
    zone = _dilate(lava, rx=1, rz=1, ry_down=1, ry_up=1) & ~lava
    hit = water & zone & ctx.core_mask
    if not hit.any():
        return []
    return [ctx.finding("fluid_mix", "major", "Su ile lav birbirine değiyor: taş/obsidyen oluşur, görünüm bozulur.",
                        "Su ve lavı en az bir dolu blokla ayır (tercihen lavı hiç kullanma).", idx=np.flatnonzero(hit))]


@check("waterlogged_anomaly", "Kuru ortamda waterlogged=true (su taşar) ya da su içinde waterlogged=false (hava cebi).", "teknik")
def c_waterlogged(ctx: Ctx) -> list[Finding]:
    out = []
    wl = ctx.cm("wlog") & ~ctx.cm("water_src")
    if wl.any():
        idx = np.flatnonzero(wl)
        of = (ctx.m("fluid_open") | (ctx.m("keep") & (not ctx.context.get("keep_supports")))).reshape(-1)
        spill = np.zeros(idx.size, bool)
        for d in ("down", "north", "south", "east", "west"):
            spill |= of[idx + ctx.OFF[d]]
        if spill.any():
            out.append(ctx.finding("waterlogged_anomaly", "major",
                                   f"{int(spill.sum())} waterlogged=true blok kuru ortamda: suyu yanındaki boşluğa taşır.",
                                   "Bu bloklarda waterlogged=false yaz ya da yanlarını kapat.", idx=idx[spill]))
    dry = ctx.cm("wl_false")
    if dry.any():
        idx = np.flatnonzero(dry)
        hw = ctx.m("has_water").reshape(-1)
        cnt = np.zeros(idx.size, np.int8)
        for d in ("up", "north", "south", "east", "west"):
            cnt += hw[idx + ctx.OFF[d]]
        sub = cnt >= 4
        if sub.any():
            out.append(ctx.finding("waterlogged_anomaly", "minor",
                                   f"Su içindeki {int(sub.sum())} blok waterlogged=false: suyun içinde hava cebi gibi görünür.",
                                   "Su altındaki merdiven/levha/çit/fener vb. bloklarda waterlogged=true yaz.", idx=idx[sub]))
    return out


@check("unsupported_gravity", "Kum/çakıl/beton tozu/örs gibi yerçekimli bloğun altı boş (hava/sıvı/‘keep’).", "teknik")
def c_unsupported_gravity(ctx: Ctx) -> list[Finding]:
    G = ctx.m("gravity")
    if not (G & ctx.core_mask).any():
        return []
    free = ctx.m("air") | ctx.m("water_src") | ctx.m("lava") | (ctx.m("repl") & ~ctx.m("wlog")) | ctx.m("fire")
    unk = ctx.m("keep")
    uns = np.zeros(G.shape, bool)
    via_unk = np.zeros(G.shape, bool)
    for y in range(1, G.shape[0]):
        uns[y] = G[y] & (free[y - 1] | unk[y - 1] | uns[y - 1])
        via_unk[y] = G[y] & (unk[y - 1] | via_unk[y - 1]) & ~free[y - 1]
    uns &= ctx.core_mask
    if not uns.any():
        return []
    idx = np.flatnonzero(uns)
    n_unk = int(np.count_nonzero(via_unk & uns))
    names = ctx.names_of(ctx.flat[idx])
    msg = f"{idx.size} yerçekimli blok ({', '.join(names)}) düşer: altı boş"
    if n_unk:
        msg += f" ({n_unk} tanesinin altı plan dışı/‘keep’)"
    return [ctx.finding("unsupported_gravity", "major", msg + ".",
                        "Altına dolu blok koy ya da yerçekimsiz eşdeğerini kullan (kumtaşı, beton, taş, düzgün taş).", idx=idx,
                        data={"blocks": names})]


def _support_eval(ctx: Ctx, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """Verilen turdeki (attach/hang/chain) desteksiz hucreler: (indeksler, palet kimlikleri)."""
    rules = {}
    for i, (k, r) in enumerate(ctx.rules):
        if k == kind and r:
            rules[i] = r
    if not rules:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    pids = np.fromiter(rules.keys(), dtype=np.int64)
    sel = np.isin(ctx.ids, pids) & ctx.core_mask
    idx = np.flatnonzero(sel)
    if idx.size == 0:
        return idx, idx
    pv = ctx.flat[idx]
    bad_i, bad_p = [], []
    for p in np.unique(pv):
        ii = idx[pv == p]
        ok = np.zeros(ii.size, bool)
        for d, cond in rules[int(p)]:
            tab = ctx.cond_table(cond, own=int(p))
            ok |= tab[ctx.flat[ii + ctx.OFF[d]]]
        bad_i.append(ii[~ok])
        bad_p.append(np.full(int((~ok).sum()), p))
    return np.concatenate(bad_i), np.concatenate(bad_p)


@check("unsupported_attachables", "Meşale/fener/merdiven(ladder)/tabela/flama/buton/halı/çiçek gibi destek isteyen blok desteksiz.", "teknik")
def c_unsupported_attachables(ctx: Ctx) -> list[Finding]:
    bi, bp = _support_eval(ctx, "attach")
    extra_i, extra_p = [], []
    # kaktus: yaninda kati blok olamaz; seker kamisi: toprak/kum altindaysa o bloğun yaninda su gerekir
    for p in range(ctx.n):
        a = ctx.names[p]
        if a not in ("cactus", "sugar_cane") or not ctx.T["block"][p]:
            continue
        idx = np.flatnonzero((ctx.ids == p) & ctx.core_mask)
        if idx.size == 0:
            continue
        if a == "cactus":
            sol = ctx.T["solidish"] & ~ctx.T["keep"] & ~ctx.T["ground"]
            bad = np.zeros(idx.size, bool)
            for d in ("north", "south", "east", "west"):
                bad |= sol[ctx.flat[idx + ctx.OFF[d]]]
        else:
            below = idx + ctx.OFF["down"]
            soil = ~np.array([ctx.names[i] == "sugar_cane" for i in range(ctx.n)], bool)[ctx.flat[below]] & \
                ~ctx.T["keep"][ctx.flat[below]] & ~ctx.T["ground"][ctx.flat[below]]
            water = np.zeros(idx.size, bool)
            hw = ctx.T["has_water"] | np.array([ctx.names[i] == "frosted_ice" for i in range(ctx.n)], bool) | ctx.T["keep"]
            for d in ("north", "south", "east", "west"):
                water |= hw[ctx.flat[below + ctx.OFF[d]]]
            bad = soil & ~water
        extra_i.append(idx[bad])
        extra_p.append(np.full(int(bad.sum()), p))
    # cok yuzlu (sarmasik, parlayan liken...): en az bir dolu yuze tutunmali
    for p in range(ctx.n):
        k, _ = ctx.rules[p]
        if k != "multi":
            continue
        idx = np.flatnonzero((ctx.ids == p) & ctx.core_mask)
        if idx.size == 0:
            continue
        faces = [f for f in DIRV if ctx.props[p].get(f) == "true"]
        ok = np.zeros(idx.size, bool)
        for f in faces:
            tab = ctx.cond_table(f"sturdy:{OPP[f]}")
            ok |= tab[ctx.flat[idx + ctx.OFF[f]]]
        if ctx.names[p] == "vine":
            vine = np.array([ctx.names[i] == "vine" for i in range(ctx.n)], bool)
            ok |= vine[ctx.flat[idx + ctx.OFF["up"]]]
        extra_i.append(idx[~ok])
        extra_p.append(np.full(int((~ok).sum()), p))
    if extra_i:
        bi = np.concatenate([bi] + extra_i)
        bp = np.concatenate([bp] + extra_p)
    if bi.size == 0:
        return []
    names = ctx.names_of(bp)
    sev = "major"
    return [ctx.finding("unsupported_attachables", sev, f"{bi.size} destek isteyen blok desteksiz: {', '.join(names)}.",
                        "Gereken yüzü sağlam blok ekle (duvar meşalesi/tabela/ladder: arkasında dolu blok; meşale/fener/halı: altında; "
                        "çiçek/fidan: altında çimen/toprak) ya da bloğu kaldır.", idx=bi, data={"blocks": names})]


@check("hanging_without_support", "Asılı fener/asılı tabela/sarkan bitki tavana bağlı değil; zincirin üst ucu boşlukta.", "teknik")
def c_hanging(ctx: Ctx) -> list[Finding]:
    out = []
    bi, bp = _support_eval(ctx, "hang")
    if bi.size:
        names = ctx.names_of(bp)
        out.append(ctx.finding("hanging_without_support", "major", f"{bi.size} asılı blok tavana bağlı değil: {', '.join(names)}.",
                               "Üstüne dolu blok, çit, duvar ya da zincir koy; asılı feneri zincirle kirişe/tavana bağla.", idx=bi,
                               data={"blocks": names}))
    ci, cp = _support_eval(ctx, "chain")
    if ci.size:
        out.append(ctx.finding("hanging_without_support", "minor", f"{ci.size} zincirin üst ucu boşlukta bitiyor.",
                               "Zinciri tavana/kirişe kadar uzat ya da üstüne bir blok koy.", idx=ci))
    return out


def _partner(ctx: Ctx, tag: str, prop: str, mapping: dict, offset_fn) -> tuple[np.ndarray, np.ndarray]:
    """Iki parcali bloklar: (eksik hucreler, uyumsuz hucreler)."""
    pids = np.flatnonzero(ctx.T[tag])
    if pids.size == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    missing, mismatch = [], []
    for p in pids:
        idx = np.flatnonzero((ctx.ids == p) & ctx.core_mask)
        if idx.size == 0:
            continue
        pr = ctx.props[p]
        other = mapping.get(pr.get(prop))
        if other is None:
            continue
        try:
            exp = ctx.db.index[ctx.db.with_props("minecraft:" + ctx.names[p] + "[" + ",".join(f"{k}={v}" for k, v in pr.items()) + "]",
                                                 **{prop: other})]
        except Exception:
            continue
        off = offset_fn(pr)
        if off is None:
            continue
        q = ctx.flat[idx + off]
        same = ctx.sid[q] == exp
        same_block = np.array([ctx.names[int(v)] == ctx.names[p] for v in q], bool) & \
            np.array([ctx.props[int(v)].get(prop) == other for v in q], bool)
        missing.append(idx[~same & ~same_block])
        mismatch.append(idx[~same & same_block])
    cat = lambda L: np.concatenate(L) if L else np.zeros(0, np.int64)  # noqa: E731
    return cat(missing), cat(mismatch)


@check("broken_doors", "Kapının alt/üst yarısı eksik ya da uyumsuz; alt yarının altında sağlam zemin yok.", "teknik")
def c_broken_doors(ctx: Ctx) -> list[Finding]:
    out = []
    miss, mism = _partner(ctx, "door", "half", {"lower": "upper", "upper": "lower"},
                          lambda pr: ctx.OFF["up"] if pr.get("half") == "lower" else ctx.OFF["down"])
    if miss.size:
        out.append(ctx.finding("broken_doors", "major", f"{miss.size} kapı yarım: alt ya da üst yarısı eksik (oyun kapıyı siler).",
                               "Kapıyı iki yarısıyla yaz: half=lower ve hemen üstünde half=upper (aynı facing/hinge/open).", idx=miss))
    if mism.size:
        out.append(ctx.finding("broken_doors", "minor", f"{mism.size} kapının iki yarısı uyumsuz (facing/hinge/open farklı).",
                               "Alt ve üst yarıda facing, hinge, open ve powered değerlerini aynı yaz.", idx=mism))
    low = ctx.cm("door_lower")
    if low.any():
        idx = np.flatnonzero(low)
        tab = ctx.cond_table("sturdy:up")
        bad = ~tab[ctx.flat[idx + ctx.OFF["down"]]]
        if bad.any():
            out.append(ctx.finding("broken_doors", "major", f"{int(bad.sum())} kapının altında sağlam zemin yok (kapı kırılır).",
                                   "Kapının altına dolu bir blok (döşeme/eşik) koy.", idx=idx[bad]))
    return out


@check("door_blocked", "Kapının önü ya da arkası dolu blokla kapalı: kapı duvara açılıyor, geçilemez.", "teknik")
def c_door_blocked(ctx: Ctx) -> list[Finding]:
    pf = ctx.P.reshape(-1)
    walk = np.array([n.endswith(("_stairs", "_slab", "_carpet")) or n in ("carpet", "snow") for n in ctx.names], dtype=bool)
    ok = pf | walk[ctx.flat]
    up = ctx.OFF["up"]
    deco = _meta_cells(ctx, "decor_doors")   # dolap kapagi: gecis kapisi degil
    bad = []
    for p in np.flatnonzero(ctx.T["door_lower"]):
        idx = np.flatnonzero((ctx.ids == p) & ctx.core_mask)
        idx = idx[~np.isin(idx, deco)] if deco.size else idx
        f = ctx.props[p].get("facing")
        if idx.size == 0 or f not in DIRV:
            continue
        for d in (f, OPP[f]):
            n = idx + ctx.OFF[d]
            bad.append(idx[~ok[n] & ~ok[n + up]])
    bad = np.unique(np.concatenate(bad)) if bad else np.zeros(0, np.int64)
    if bad.size == 0:
        return []
    return [ctx.finding("door_blocked", "major", f"{bad.size} kapının önü ya da arkası dolu: kapı duvara açılıyor, geçilemez.",
                        "Kapının önündeki ve arkasındaki iki hücreyi (alt ve üst) boş bırak ya da kapıyı açıklığa taşı.", idx=bad)]


@check("window_blocked", "Pencere dört yandan dolu bloklarla kapalı: hiçbir yöne bakmıyor (ışık ve görüş yok).", "estetik")
def c_window_blocked(ctx: Ctx) -> list[Finding]:
    g = ctx.cm("glass")
    if not g.any():
        return []
    idx = np.flatnonzero(g)
    shut = (ctx.T["opaque"] & ~ctx.T["glass"])[ctx.flat]
    closed = np.ones(idx.size, dtype=bool)
    for d in ("north", "south", "east", "west"):
        closed &= shut[idx + ctx.OFF[d]]
    # tavan/zemin penceresi (ustu ya da alti acik) yukari/asagi bakar: kapali degil
    closed &= shut[idx + ctx.OFF["up"]] & shut[idx + ctx.OFF["down"]]
    if not closed.any():
        return []
    return [ctx.finding("window_blocked", "minor", f"{int(closed.sum())} pencere camı dört yandan duvarla kapalı (dışarı bakmıyor).",
                        "Camı dış duvar düzlemine taşı ya da önündeki/arkasındaki bloğu kaldır.", idx=idx[closed])]


@check("broken_beds", "Yatağın baş ya da ayak parçası eksik veya yönü uyumsuz.", "teknik")
def c_broken_beds(ctx: Ctx) -> list[Finding]:
    def off(pr):
        f = pr.get("facing")
        if f not in DIRV:
            return None
        return ctx.OFF[f] if pr.get("part") == "foot" else ctx.OFF[OPP[f]]
    miss, mism = _partner(ctx, "bed", "part", {"foot": "head", "head": "foot"}, off)
    bad = np.concatenate([miss, mism])
    if bad.size == 0:
        return []
    return [ctx.finding("broken_beds", "major", f"{bad.size} yatak parçası yarım ya da uyumsuz (oyun yatağı siler).",
                        "Yatağı iki blok yaz: part=foot ve onun facing yönündeki komşuda aynı facing ile part=head.", idx=bad)]


@check("broken_double_plants", "Uzun bitkinin (uzun ot, ayçiçeği, leylak...) alt/üst yarısı eksik.", "teknik")
def c_broken_double_plants(ctx: Ctx) -> list[Finding]:
    miss, mism = _partner(ctx, "dplant", "half", {"lower": "upper", "upper": "lower"},
                          lambda pr: ctx.OFF["up"] if pr.get("half") == "lower" else ctx.OFF["down"])
    bad = np.concatenate([miss, mism])
    if bad.size == 0:
        return []
    return [ctx.finding("broken_double_plants", "minor", f"{bad.size} uzun bitki yarım (alt/üst yarı eksik).",
                        "Uzun çiçek/ot/eğreltiyi half=lower + hemen üstünde half=upper olarak iki blok yaz.", idx=bad)]


def _stair_tables(ctx: Ctx):
    face = np.full(ctx.n, -1, np.int8)
    for i in range(ctx.n):
        if ctx.T["stairs"][i]:
            f = ctx.props[i].get("facing")
            if f in HORIZ:
                face[i] = HORIZ.index(f)
    return face


def _stair_pairs(ctx: Ctx):
    """Yukselen merdiven ciftleri: (alt basamak indeksi, ust basamak indeksi, yukselis yonu).
    Yun merdivenler (tente, minder) suslemedir: yurunen dizi sayilmaz."""
    wool = np.array(["wool" in n for n in ctx.names], bool)
    SB = ctx.m("stairs_bottom") & ~wool[ctx.ids]
    out = []
    for d in HORIZ:
        _, dz, dx = DIRV[d]
        sa, sb = _pair_slices(ctx.shape, 1, dz, dx)
        both = SB[sa] & SB[sb]
        if not both.any():
            continue
        mm = np.zeros(ctx.shape, bool)
        mm[sa] = both
        ai = np.flatnonzero(mm)
        out.append((ai, ai + ctx.OFF["up"] + ctx.OFF[d], d))
    return out


@check("stair_orientation", "Merdiven basamakları anlamsız yönde: yükseliş yönüne ters bakıyor ya da yürünen dizide ters (half=top) basamak.", "teknik")
def c_stair_orientation(ctx: Ctx) -> list[Finding]:
    face = _stair_tables(ctx)
    mats = {}
    same_mat = np.array([mats.setdefault(n, len(mats)) for n in ctx.names], np.int64)   # ad (ozelliksiz) kimligi
    wrong = []
    for ai, bi, d in _stair_pairs(ctx):
        want_bad = HORIZ.index(OPP[d])
        want = HORIZ.index(d)
        fa = face[ctx.flat[ai]]
        fb = face[ctx.flat[bi]]
        # yalniz ayni eksende dizilen ciftler bir 'merdiven/egim' olusturur; dik bakan komsu (sacak kornisi +
        # alinlik egimi gibi iki ayri oge) cift sayilmaz
        axis = ((fa == want) | (fa == want_bad)) & ((fb == want) | (fb == want_bad))
        axis &= same_mat[ctx.flat[ai]] == same_mat[ctx.flat[bi]]
        wrong.append(ai[axis & (fa == want_bad)])
        wrong.append(bi[axis & (fb == want_bad)])
    out = []
    w = np.unique(np.concatenate(wrong)) if wrong else np.zeros(0, np.int64)
    w = w[ctx.core_mask.reshape(-1)[w]] if w.size else w
    if w.size:
        out.append(ctx.finding("stair_orientation", "major", f"{w.size} merdiven basamağı ters: yükseliş yönüne bakmıyor (çatı/merdiven testere dişi gibi).",
                               "facing'i yüksek tarafa (çıkış yönüne) çevir; çatıda basamaklar mahyaya, merdivende yukarı kata bakmalı.", idx=w))
    # yurunen dizide ters (half=top) basamak
    ST = ctx.m("stairs_top") & ctx.core_mask
    if ST.any():
        idx = np.flatnonzero(ST)
        sbt = ctx.T["stairs_bottom"]
        bad = np.zeros(idx.size, bool)
        for d in HORIZ:
            lo = ctx.flat[idx - ctx.OFF["up"] - ctx.OFF[d]]
            hi = ctx.flat[idx + ctx.OFF["up"] + ctx.OFF[d]]
            want = HORIZ.index(d)
            bad |= sbt[lo] & sbt[hi] & (face[lo] == want) & (face[hi] == want)
        if bad.any():
            out.append(ctx.finding("stair_orientation", "major", f"Yürünen merdiven dizisinde {int(bad.sum())} ters (half=top) basamak.",
                                   "Yürünen basamaklarda half=bottom kullan; ters merdiveni yalnız saçak altı/süs için kullan.", idx=idx[bad]))
    return out


def _meta_cells(ctx: Ctx, key: str) -> np.ndarray:
    """meta[key] = [[x,y,z], ...] -> dolgulu duz dizinler (gecersizler atlanir)."""
    out = []
    for c in ctx.meta.get(key) or []:
        try:
            yi, zi, xi = ctx.to_pad(*c[:3])
        except Exception:
            continue
        if ctx.inside(yi, zi, xi):
            out.append(np.ravel_multi_index((yi, zi, xi), ctx.shape))
    return np.array(sorted(set(out)), np.int64)


@check("stair_walkability", "Merdiven basamaklarında 2 blok baş boşluğu yok ya da katlar/odalar arasında yürünebilir merdiven yok.", "iç mekân")
def c_stair_walkability(ctx: Ctx) -> list[Finding]:
    out = []
    P = ctx.P.reshape(-1)
    reach = ctx.walk["reach"]
    near = reach.copy()
    near[:-1] |= reach[1:]
    near[1:] |= reach[:-1]
    nearh = near.copy()                     # yatayda da 1 komsu: basamaga yurume alanindan adim atilabilir mi
    nearh[:, 1:, :] |= near[:, :-1, :]
    nearh[:, :-1, :] |= near[:, 1:, :]
    nearh[:, :, 1:] |= near[:, :, :-1]
    nearh[:, :, :-1] |= near[:, :, 1:]
    near = near.reshape(-1)
    nearh = nearh.reshape(-1)
    cov = (~ctx.outdoorish).reshape(-1)
    face = _stair_tables(ctx)
    steps, lower, dead = [], [], []
    names_ = ctx.names
    cap = np.array([n.endswith(("_stairs", "_slab")) for n in names_], dtype=bool)[ctx.flat]
    for ai, bi, d in _stair_pairs(ctx):
        want = HORIZ.index(d)
        ok = (face[ctx.flat[ai]] == want)
        steps.append(ai[ok])
        steps.append(bi[ok])
        lower.append((ai[ok], bi[ok]))       # (alt basamak, ustundeki bir sonraki basamak)
        # ust basamagin hemen ustu basamak/yarim blokla kapaliysa bu dizi yurunen merdiven degil (kademeli kutle, oturma)
        dead.append(ai[ok][cap[bi[ok] + ctx.OFF["up"]]])
    if steps:
        s = np.unique(np.concatenate(steps))
        s = s[ctx.core_mask.reshape(-1)[s]]
        up1, up2, up3 = s + ctx.OFF["up"], s + 2 * ctx.OFF["up"], s + 3 * ctx.OFF["up"]
        # yurunen basamak: ustune ulasilabiliyor ya da (ortulu ve basamagin kendisi yurume alanina bitisik);
        # ulasilamayan suslemeler (cikma altindaki cumba catisi, sacak) sayilmaz
        rel = near[up1] | (cov[up1] & nearh[s])
        PW = P | ctx.m("fluid").reshape(-1)   # havuz basamagi: ustu su = yuzulebilir bosluk
        rel &= ~ctx.m("fluid").reshape(-1)[up1]
        # cephe kabartmasi (pencere cevresi, korniş): iki yani ve arkasi dolu, ustu kapali basamak yurunen merdiven degildir
        full = (ctx.T["full"] & ~ctx.T["stairs"])[ctx.flat]
        fs = face[ctx.flat[s]]
        relief = np.zeros(s.size, dtype=bool)
        for k, dname in enumerate(HORIZ):
            m = fs == k
            if not m.any():
                continue
            left, right = HORIZ[(k + 1) % 4], HORIZ[(k + 3) % 4]
            si = s[m]
            relief[m] = full[si + ctx.OFF[left]] & full[si + ctx.OFF[right]] & full[si + ctx.OFF[dname]] & ~P[si + ctx.OFF["up"]]
        rel &= ~relief
        # dogrudan ustu basamak/yarim blokla kapali basamak (kademeli kutle) ve kapali basamaga cikan basamak yurunmez
        rel &= ~cap[up1]
        if dead:
            rel &= ~np.isin(s, np.concatenate(dead))
        bad = rel & ~(PW[up1] & PW[up2])
        if bad.any():
            out.append(ctx.finding("stair_walkability", "critical", f"{int(bad.sum())} merdiven basamağının üstünde 2 blok baş boşluğu yok: oyuncu ancak eğilerek ya da hiç geçemez.",
                                   "Her basamağın üstünde 3 blok boşluk bırak; üst katın döşemesini merdiven boyunca aç (parts.staircase bunu yapar).", idx=s[bad]))
        # bir ust basamaga cikarken govde onceki basamagin ustune tasar: orada 3. blok da bos olmali (yoksa kafa carpar);
        lo = np.unique(np.concatenate([p[0] for p in lower]))
        lo_mask = np.isin(s, lo)
        # acik havada yana dogru >=4 basamaklik sira (kosede saçak basamagi dahil) cati egimidir:
        # komsu catinin sacagi 3. bloga girse de yurunen merdiven degil
        st_ = ctx.T["stairs"][ctx.flat]
        run = np.ones(s.size, dtype=np.int64)
        for k in range(4):
            m = fs == k
            if not m.any():
                continue
            for side in (HORIZ[(k + 1) % 4], HORIZ[(k + 3) % 4]):
                cont = np.ones(int(m.sum()), dtype=bool)
                for j in range(1, 4):
                    cont &= st_[s[m] + j * ctx.OFF[side]]
                    run[np.flatnonzero(m)[cont]] += 1
        roof = (run >= 4) & ~cov[up1]
        bad3 = rel & ~bad & lo_mask & ~PW[up3] & ~roof
        if bad3.any():
            out.append(ctx.finding("stair_walkability", "critical", f"{int(bad3.sum())} basamakta yukarı çıkarken kafa çarpar: basamağın üstündeki 3. blok dolu.",
                                   "Merdiven boşluğunu bir blok daha erken aç: üst kat döşemesini/tavanı basamakların üstünde 3 blok yükseklikte kaldır.", idx=s[bad3]))
    rooms_f = []
    for r in ctx.used_rooms():
        if r.sealed or r.walk or not r.standable or (ctx.meta.get("secret_door") and _exempt(r, EXEMPT_SECRET)):
            continue
        rooms_f.append(ctx.finding("stair_walkability", "major",
                               f"'{r.name}' odasına havadan bağlantı var ama yürüyerek ulaşılamıyor (merdiven/ladder/basamak eksik ya da 1 bloktan yüksek).",
                               "Katlar arasına merdiven (her basamak 1 blok), ladder ya da iskele ekle; girişlerde 2 blok yükseklik bırak.",
                               idx=r.floor if r.floor.size else r.cells, data={"room": r.name}))
    out += _compact(rooms_f, "stair_walkability", "{n} odaya havadan bağlantı var ama yürüyerek ulaşılamıyor: {names}.")
    floors = ctx.meta.get("floors") or []
    S = ctx.walk["S"]
    for fl in floors:
        y = fl.get("y") if isinstance(fl, dict) else fl
        if not isinstance(y, (int, float)):
            continue
        yi = int(y) - ctx.origin[1] + PADB + 1
        if not (0 < yi < ctx.shape[0]):
            continue
        lay = S[yi] & ctx.core_mask[yi] & ~ctx.outdoorish[yi]
        if lay.sum() >= 4 and not (reach[yi] & lay).any():
            ii = np.flatnonzero(lay) + yi * ctx.SY
            out.append(ctx.finding("stair_walkability", "major", f"y={int(y)} katına yürüyerek çıkılamıyor.",
                                   "Bu kata merdiven ya da ladder bağla.", idx=ii, data={"floor": int(y)}))
    return out


@check("headroom", "Kapının önü/arkası ya da yol üstünde 2 blok boşluk yok; kapı boşluğa açılıyor.", "iç mekân")
def c_headroom(ctx: Ctx) -> list[Finding]:
    out = []
    wk = ctx.walk
    B = wk["B"].reshape(-1)
    S = wk["S"].reshape(-1)
    low = ctx.cm("door_lower")
    blocked, nowhere = [], []
    if low.any():
        idx = np.flatnonzero(low)
        deco = _meta_cells(ctx, "decor_doors")   # mobilya kapilari (dolap): gecis kapisi degil
        if deco.size:
            idx = np.setdiff1d(idx, deco)
        pv = ctx.flat[idx]
        for p in np.unique(pv):
            f = ctx.props[int(p)].get("facing")
            if f not in HORIZ:
                continue
            ii = idx[pv == p]
            for side in (f, OPP[f]):
                j = ii + ctx.OFF[side]
                blocked.append(ii[~B[j]])
                nowhere.append(ii[B[j] & ~S[j]])
    bl = np.unique(np.concatenate(blocked)) if blocked else np.zeros(0, np.int64)
    nw = np.unique(np.concatenate(nowhere)) if nowhere else np.zeros(0, np.int64)
    nw = np.setdiff1d(nw, bl)
    if bl.size:
        out.append(ctx.finding("headroom", "major", f"{bl.size} kapının önünde/arkasında 2 blok yükseklikte boşluk yok.",
                               "Kapının iki yanında ayak ve baş hizasını (2 blok) boş bırak.", idx=bl))
    if nw.size:
        out.append(ctx.finding("headroom", "minor", f"{nw.size} kapı boşluğa açılıyor (önünde basılacak zemin yok).",
                               "Kapının önüne zemin, balkon ya da basamak ekle; gereksizse kapıyı kaldır.", idx=nw))
    path = ctx.cm("dirt_path")
    if path.any():
        idx = np.flatnonzero(path)
        P = ctx.P.reshape(-1)
        bad = ~(P[idx + ctx.OFF["up"]] & P[idx + 2 * ctx.OFF["up"]])
        if bad.any():
            out.append(ctx.finding("headroom", "minor", f"{int(bad.sum())} yol bloğunun üstünde 2 blok boşluk yok.",
                                   "Yolun üstünde 2 blok yükseklik bırak (kemer/sundurma en az 3 blok olmalı).", idx=idx[bad]))
    bad_meta = []
    for dd in ctx.meta.get("doors") or []:
        pos = dd.get("pos") if isinstance(dd, dict) else dd
        if not pos or len(pos) < 3:
            continue
        yi, zi, xi = ctx.to_pad(*pos[:3])
        if not ctx.inside(yi, zi, xi):
            continue
        if ctx.T["door"][int(ctx.ids[yi, zi, xi])]:
            continue
        i0 = np.ravel_multi_index((yi, zi, xi), ctx.shape)
        if not B[i0]:
            bad_meta.append(ctx.loc(yi, zi, xi))
    if bad_meta:
        out.append(ctx.finding("headroom", "minor", f"{len(bad_meta)} meta kapı konumu kapalı (2 blok geçit yok).",
                               "Kapı konumunu 2 blok yüksekliğinde boşalt ya da oraya kapı koy.", positions=bad_meta[:6], count=len(bad_meta)))
    return out


def _compact(items: list[Finding], cid: str, msg: str, fix: str | None = None, limit: int = 4) -> list[Finding]:
    """Ayni turden cok sayida oda bulgusunu tek bulguda toplar (rapor sel olmasin)."""
    if len(items) <= limit:
        return items
    sev = min((f.severity for f in items), key=lambda s: SEV_RANK[s])
    names = [f.data.get("room", "?") for f in items]
    pos = [f.positions[0] for f in items if f.positions][:6]
    return [Finding(cid, sev, msg.format(n=len(items), names=", ".join(names[:6]) + (" ..." if len(names) > 6 else "")),
                    fix or items[0].fix, pos, sum(f.count for f in items), {"rooms": names[:30]})]


def _room_cands(ctx: Ctx) -> list[Room]:
    return [r for r in ctx.rooms if r.source == "meta" or r.floor_area >= 9]


@check("no_entrance", "Yapıya giriş yok: iç mekâna dışarıdan yürüyerek ulaşılamıyor.", "iç mekân")
def c_no_entrance(ctx: Ctx) -> list[Finding]:
    rooms = [r for r in _room_cands(ctx) if r.standable and not r.attic]
    if not rooms:
        return []
    if any(r.walk for r in rooms):
        return []
    any_air = any(not r.sealed for r in rooms)
    idx = np.concatenate([r.floor for r in rooms])
    if any_air:
        msg = "Yapıya yürüyerek girilemiyor: açıklık var ama eşik/basamak çok yüksek ya da geçit 2 bloktan alçak."
    else:
        msg = "Yapıya giriş yok: iç mekân tamamen kapalı (kapı ya da açıklık yok)."
    return [ctx.finding("no_entrance", "critical", msg,
                        "Zemine yakın bir duvara 2 blok yüksekliğinde kapı (ya da kapı boşluğu) aç; önüne en çok 1 blok basamak/yol koy.",
                        idx=idx)]


@check("unreachable_rooms", "Bir oda (meta ya da otomatik bulunan) kapalı: girişlerden hiçbir açıklıkla ulaşılamıyor.", "iç mekân")
def c_unreachable_rooms(ctx: Ctx) -> list[Finding]:
    rooms = [r for r in _room_cands(ctx) if r.standable or r.source == "meta"]
    if not rooms or not any(r.walk for r in rooms if not r.attic):
        return []   # hic giris yoksa no_entrance bildirir
    out = []
    for r in rooms:
        if not r.sealed:
            continue
        if r.source == "auto" and r.attic:
            out.append(ctx.finding("unreachable_rooms", "minor", f"Çatı arası boşluğu ({r.name}) kapalı ve ulaşılamaz.",
                                   "Çatı arasına ladder + tuzak kapı ile erişim aç, aydınlat ya da boşluğu doldur.", idx=r.floor,
                                   data={"room": r.name}))
            continue
        sev = "major" if (r.source == "meta" or r.floor_area >= 12) else "minor"
        out.append(ctx.finding("unreachable_rooms", sev, f"'{r.name}' odası kapalı: kapı ya da açıklık yok ({r.floor_area} zemin hücresi).",
                               "Odaya kapı ya da 2 blok yüksekliğinde geçit aç (koridordan veya komşu odadan).", idx=r.floor,
                               data={"room": r.name}))
    return _compact(out, "unreachable_rooms", "{n} oda kapalı/ulaşılamaz (kapı ya da açıklık yok): {names}.")


def _hanging_facing(e: dict) -> str | None:
    t = str(e.get("type", "")).split(":")[-1]
    snbt = str(e.get("snbt") or "")
    m = re.search(r'\b[Ff]acing\s*:\s*"?([a-zA-Z]+|-?\d+)', snbt)
    if m:
        v = m.group(1)
        if v.isalpha():
            v = v.lower()
            return v if v in DIRV else None
        v = int(v)
        if t == "painting":
            return {0: "south", 1: "west", 2: "north", 3: "east"}.get(v)
        return {0: "down", 1: "up", 2: "north", 3: "south", 4: "west", 5: "east"}.get(v)
    try:
        yaw = float(e.get("yaw", 0)) % 360
    except Exception:
        return None
    return ("south", "west", "north", "east")[int(((yaw + 45) % 360) // 90)]


@check("entity_on_solid", "Tablo/eşya çerçevesinin arkasında sağlam duvar yok ya da bloğun içinde.", "teknik")
def c_entity_on_solid(ctx: Ctx) -> list[Finding]:
    bad, inside = [], []
    sol = ctx.T["solidish"]
    for e in ctx.build.entities:
        t = str(e.get("type", "")).split(":")[-1]
        if t not in ("painting", "item_frame", "glow_item_frame"):
            continue
        f = _hanging_facing(e)
        pos = e.get("pos") or [0, 0, 0]
        yi, zi, xi = ctx.to_pad(*pos[:3])
        if f is None or not ctx.inside(yi, zi, xi):
            continue
        cur = int(ctx.ids[yi, zi, xi])
        dy, dz, dx = DIRV[OPP[f]]
        sy, sz, sx = yi + dy, zi + dz, xi + dx
        if not ctx.inside(sy, sz, sx):
            continue
        sp = int(ctx.ids[sy, sz, sx])
        p = [int(math.floor(v)) for v in pos[:3]]
        if ctx.T["full"][cur] and not ctx.T["keep"][cur]:
            inside.append(p)
        elif not sol[sp]:
            bad.append(p)
    out = []
    if bad:
        out.append(ctx.finding("entity_on_solid", "major", f"{len(bad)} tablo/eşya çerçevesinin arkasında sağlam duvar yok (düşer).",
                               "Tabloyu/çerçeveyi dolu bir duvar bloğunun önüne yerleştir ya da facing'ini duvara göre düzelt.",
                               positions=bad[:6], count=len(bad)))
    if inside:
        out.append(ctx.finding("entity_on_solid", "major", f"{len(inside)} tablo/çerçeve dolu bloğun içinde.",
                               "Varlığı duvarın önündeki boş hücreye taşı.", positions=inside[:6], count=len(inside)))
    return out


def _boxes(v) -> list[tuple[list, str]]:
    out = []
    for i, b in enumerate(v or []):
        if isinstance(b, dict):
            box, nm = b.get("box"), str(b.get("name") or b.get("ad") or f"bölge{i + 1}")
        else:
            box, nm = b, f"bölge{i + 1}"
        if box is not None and len(box) == 6:
            out.append(([int(t) for t in box], nm))
    return out


def _overlap(ctx: Ctx, boxes) -> tuple[np.ndarray, list]:
    set_mask = (ctx.core_ids != 0)
    Y, Z, X = ctx.core_ids.shape
    x0, y0, z0 = ctx.origin
    hits, names = [], []
    for box, nm in boxes:
        a0, b0, c0, a1, b1, c1 = box
        lo = (max(min(b0, b1) - y0, 0), max(min(c0, c1) - z0, 0), max(min(a0, a1) - x0, 0))
        hi = (min(max(b0, b1) - y0, Y - 1), min(max(c0, c1) - z0, Z - 1), min(max(a0, a1) - x0, X - 1))
        if any(lo[k] > hi[k] for k in range(3)):
            continue
        sub = set_mask[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1]
        gy, gz, gx = np.nonzero(sub)
        if gy.size:
            hits.append(np.ravel_multi_index((gy + lo[0] + PADB, gz + lo[1] + PADX, gx + lo[2] + PADX), ctx.shape))
            names.append(nm)
    return (np.unique(np.concatenate(hits)) if hits else np.zeros(0, np.int64)), names


@check("structure_overlap", "Plan bağlamda verilen mevcut yapı kutularıyla çakışıyor.", "çevre")
def c_structure_overlap(ctx: Ctx) -> list[Finding]:
    boxes = _boxes(ctx.context.get("structures"))
    if not boxes:
        return []
    idx, names = _overlap(ctx, boxes)
    if idx.size == 0:
        return []
    return [ctx.finding("structure_overlap", "major", f"Plan mevcut yapıyla çakışıyor: {', '.join(names[:4])} ({idx.size} hücre).",
                        "Yapıyı kaydır/döndür ya da çakışan kısmı b.forget(...) ile plandan çıkar.", idx=idx, data={"structures": names[:10]})]


@check("protected_overlap", "Plan korumalı bölgeye (kutu ya da maske) dokunuyor.", "çevre")
def c_protected_overlap(ctx: Ctx) -> list[Finding]:
    boxes = _boxes(ctx.context.get("protected"))
    idx, names = _overlap(ctx, boxes) if boxes else (np.zeros(0, np.int64), [])
    pm = ctx.context.get("protected_mask")
    if pm is not None:
        if isinstance(pm, dict):
            org, mask = pm.get("origin", (0, 0, 0)), np.asarray(pm.get("mask"), bool)
        else:
            org, mask = pm[0], np.asarray(pm[1], bool)
        set_mask = np.zeros(ctx.shape, bool)
        set_mask[ctx.core_sl] = ctx.core_ids != 0
        my, mz, mx = mask.shape
        ox, oy, oz = (int(v) for v in org)
        a = ctx.to_pad(ox, oy, oz)
        lo = [max(0, a[k]) for k in range(3)]
        hi = [min(ctx.shape[k], a[k] + (my, mz, mx)[k]) for k in range(3)]
        if all(lo[k] < hi[k] for k in range(3)):
            sub = mask[lo[0] - a[0]:hi[0] - a[0], lo[1] - a[1]:hi[1] - a[1], lo[2] - a[2]:hi[2] - a[2]]
            hit = set_mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]] & sub
            gy, gz, gx = np.nonzero(hit)
            if gy.size:
                idx = np.union1d(idx, np.ravel_multi_index((gy + lo[0], gz + lo[1], gx + lo[2]), ctx.shape))
                names = names + ["maske"]
    if idx.size == 0:
        return []
    return [ctx.finding("protected_overlap", "critical", f"Plan korumalı bölgeye dokunuyor: {', '.join(names[:4])} ({idx.size} hücre).",
                        "Korumalı alanı plandan çıkar (b.forget(...)) ya da yapıyı başka yere taşı.", idx=idx, data={"zones": names[:10]})]


@check("cliff_cut", "Yapı kenarında arazi 3 bloktan yüksek sert basamak yapıyor (yarma/dolgu uçurumu).", "çevre")
def c_cliff_cut(ctx: Ctx) -> list[Finding]:
    hm = ctx.context.get("heightmap")
    if hm is None:
        return []
    hm = np.asarray(hm)
    hx0, hz0 = ctx.context.get("heightmap_origin", (ctx.origin[0], ctx.origin[2]))
    core = ctx.ids[ctx.core_sl]
    blk = ctx.T["block"][core]
    foot = blk.any(axis=0)
    if not foot.any():
        return []
    Y = blk.shape[0]
    low = np.argmax(blk, axis=0)  # en alttaki blok
    Zc, Xc = foot.shape
    # yalniz zemine oturan kolonlar yapi kenari sayilir: tac/sacak/konsol gibi havadaki kolonlar ve bitki atlanir
    stripped = np.array([n.startswith("stripped_") for n in ctx.names], bool)   # soyulmus kutuk = yapi malzemesi
    vt = (ctx.T["leaves"] | ctx.T["plant"] | ((ctx.T["wlog"] | np.array(
        [n.endswith(("_log", "_wood", "_stem", "_hyphae")) for n in ctx.names], bool)) & ~stripped) | np.array(
        [n.endswith("_leaves") or n in ("mangrove_roots", "muddy_mangrove_roots") for n in ctx.names], bool))
    veg = vt[core]
    lowveg = np.take_along_axis(veg, low[None], axis=0)[0]
    cz_, cx_ = np.nonzero(foot)
    hz = np.clip(ctx.origin[2] + cz_ - int(hz0), 0, hm.shape[0] - 1)   # izgara disi: en yakin kenar
    hx = np.clip(ctx.origin[0] + cx_ - int(hx0), 0, hm.shape[1] - 1)
    tcol = hm[hz, hx].astype(np.int64)
    lowy = ctx.origin[1] + low[cz_, cx_]
    hover = lowy - 1 > tcol + 1
    foot = foot.copy()
    foot[cz_[hover | lowveg[cz_, cx_]], cx_[hover | lowveg[cz_, cx_]]] = False
    if not foot.any():
        return []
    pts, steps = [], []
    for d, (dz, dx) in (("north", (-1, 0)), ("south", (1, 0)), ("west", (0, -1)), ("east", (0, 1))):
        zz, xx = np.nonzero(foot)
        nz, nx = zz + dz, xx + dx
        inb = (nz >= 0) & (nz < Zc) & (nx >= 0) & (nx < Xc)
        edge = ~inb.copy()
        edge[inb] = ~foot[nz[inb], nx[inb]]
        zz, xx, nz, nx = zz[edge], xx[edge], nz[edge], nx[edge]
        lx = ctx.origin[0] + nx - int(hx0)
        lz = ctx.origin[2] + nz - int(hz0)
        ok = (lx >= 0) & (lx < hm.shape[1]) & (lz >= 0) & (lz < hm.shape[0])
        wet = ctx.water_grid[nz + PADX, nx + PADX] | ctx.water_grid[zz + PADX, xx + PADX]
        ok &= ~wet                                       # su kenari (kopru ayagi, iskele): ucurum sayilmaz
        if not ok.any():
            continue
        t = hm[lz[ok], lx[ok]].astype(np.int64)
        base = ctx.origin[1] + low[zz[ok], xx[ok]] - 1
        st = t - base
        big = np.abs(st) > 3
        for a, b, c, s in zip(nx[ok][big], t[big], nz[ok][big], st[big]):
            pts.append([int(ctx.origin[0] + a), int(b), int(ctx.origin[2] + c)])
            steps.append(int(s))
    if not pts:
        return []
    mx = max(abs(s) for s in steps)
    sev = "major" if (mx >= 6 or len(pts) >= 6) else "minor"
    kind = "yarma (arazi yapıdan yüksek)" if np.mean(steps) > 0 else "dolgu/uçurum (arazi yapıdan alçak)"
    k = max(1, len(pts) // 6)
    return [ctx.finding("cliff_cut", sev, f"Yapı kenarında {len(pts)} noktada {mx} bloğa varan sert arazi basamağı: {kind}.",
                        "Kenarı teraslarla, istinat duvarıyla ya da eğimli toprak/taş dolguyla yumuşat; taban kotunu araziye yaklaştır.",
                        positions=pts[::k][:6], count=len(pts), data={"max_step": mx})]


@check("floating_blocks", "Zemine ya da yapıya bağlı olmayan, havada duran blok kümeleri.", "teknik")
def c_floating_blocks(ctx: Ctx) -> list[Finding]:
    invis = np.array([n in ("light", "structure_void") for n in ctx.names], bool)[ctx.ids]   # gorunmez isik havada durabilir
    blk = (ctx.m("block") & ~invis) | ctx.m("ground")
    lab, _ = label(blk, 26)
    flat = lab.reshape(-1)
    grounded = set(np.unique(lab[ctx.m("ground")]).tolist())
    for p in ctx.context.get("anchors") or []:
        yi, zi, xi = ctx.to_pad(*p[:3])
        if ctx.inside(yi, zi, xi):
            grounded.add(int(lab[yi, zi, xi]))
    grounded.discard(0)
    core_blk = (ctx.m("block") & ~invis & ctx.core_mask).reshape(-1)
    labs = np.unique(flat[core_blk])
    # yalniz tutturulan bloklardan (mesale, fener, tabela, kapi...) olusan parcalari destek kontrolleri bildirir
    solid_part = core_blk & ~ctx.att_table[ctx.flat]
    nonatt = np.bincount(flat[solid_part], minlength=int(flat.max()) + 1)
    floating = [int(v) for v in labs if v > 0 and int(v) not in grounded and nonatt[int(v)] > 0]
    if not floating:
        return []
    sizes = np.bincount(flat, minlength=max(floating) + 1)
    floating.sort(key=lambda v: -sizes[v])
    total = int(sum(sizes[v] for v in floating))
    reps = []
    for v in floating[:6]:
        i = int(np.flatnonzero(flat == v)[0]) if sizes[v] < 50000 else int(np.argmax(flat == v))
        reps.append(ctx.sample(np.array([i]))[0])
    sev = "major" if max(sizes[v] for v in floating) >= 4 else "minor"
    return [ctx.finding("floating_blocks", sev, f"{len(floating)} parça ({total} blok) havada: zemine ya da yapıya bağlı değil.",
                        "Parçayı yapıya bağla (kiriş, sütun, zincir, payanda) ya da kaldır.", positions=reps, count=total,
                        data={"parts": len(floating), "largest": int(sizes[floating[0]])})]


# ---------------------------------------------------------------------- cephe tabanli
FLAT_MINOR = ((5, 8), (8, 5), (6, 7), (7, 6))
FLAT_MAJOR = ((6, 12), (12, 6), (8, 9), (9, 8))


def _rect_find(P: np.ndarray, sizes) -> tuple[int, int, int, int] | None:
    """P (2B bool) icinde tamamen dolu h x w pencere ara (integral goruntu). Donus: (r, c, h, w) ya da None."""
    H, W = P.shape
    I = np.zeros((H + 1, W + 1), np.int32)
    I[1:, 1:] = np.cumsum(np.cumsum(P, axis=0, dtype=np.int32), axis=1)
    for h, w in sizes:
        if h > H or w > W:
            continue
        S = I[h:, w:] - I[:-h, w:] - I[h:, :-w] + I[:-h, :-w]
        hit = np.argwhere(S == h * w)
        if hit.size:
            r, c = hit[len(hit) // 2]
            return int(r), int(c), h, w
    return None


@check("flat_wall", "Büyük, düz, derinliksiz duvar yüzeyi (çıkıntı/girinti/pervaz yok).", "estetik")
def c_flat_wall(ctx: Ctx) -> list[Finding]:
    out = []
    full = ctx.T["full"] & ~ctx.T["leaves"]
    for side, fc in ctx.facades.items():
        plane = fc.has & full[fc.pid]
        if plane.sum() < 40:
            continue
        vals, cnts = np.unique(fc.depth[plane], return_counts=True)
        best = None
        for v in vals[cnts >= 40]:
            Pm = plane & (fc.depth == v)
            r = _rect_find(Pm, FLAT_MAJOR)
            if r is not None:
                best = ("major", r, v)
                break
            r = _rect_find(Pm, FLAT_MINOR)
            if r is not None and best is None:
                best = ("minor", r, v)
        if best is None:
            continue
        sev, (r, c, h, w), v = best
        pos = [fc.loc(r, c, v), fc.loc(r + h - 1, c + w - 1, v), fc.loc(r + h // 2, c + w // 2, v)]
        out.append(ctx.finding("flat_wall", sev, f"{SIDE_TR[side]} cephede en az {w}x{h} düz, derinliksiz duvar yüzeyi.",
                               "Sütun/kirişle 1 blok öne çık, pencereleri 1 blok içeri al, merdiven/levha/tuzak kapıyla pervaz-korniş ekle, "
                               "doku geçişi (2-3 yakın ton) kullan.", positions=pos, count=h * w, data={"side": side, "w": w, "h": h}))
    return out


def _facade_shares(ctx: Ctx, fc: Facade):
    p = fc.pid[fc.has]
    if p.size == 0:
        return 0, None, 0.0
    names = np.array([ctx.names[int(i)] for i in range(ctx.n)], dtype=object)
    u, c = np.unique(names[p], return_counts=True)
    k = int(np.argmax(c))
    return int(p.size), str(u[k]), float(c[k] / p.size)


@check("monotone_block", "Tek bir blok cepheye ya da bütün yapıya hâkim (doku yok).", "estetik")
def c_monotone_block(ctx: Ctx) -> list[Finding]:
    out = []
    core = ctx.ids[ctx.core_sl].reshape(-1)
    blk = ctx.T["block"][core]
    if blk.sum() >= 64:
        cnt = np.bincount(core[blk], minlength=ctx.n)
        byname: dict[str, int] = defaultdict(int)
        for i in np.flatnonzero(cnt):
            byname[ctx.names[i]] += int(cnt[i])
        nm, c = max(byname.items(), key=lambda t: t[1])
        share = c / blk.sum()
        if share >= 0.7:
            sev = "major" if share >= 0.85 else "minor"
            out.append(ctx.finding("monotone_block", sev, f"Yapının %{share * 100:.0f}'i tek blok: {nm}.",
                                   "Ana malzemeye 2-3 yakın tonlu varyant karıştır (ör. taş tuğla + yosunlu/çatlak + andezit), "
                                   "çerçeve, taban ve çatı için ayrı malzeme kullan.", count=int(c), data={"block": nm, "share": round(share, 3)}))
    for side, fc in ctx.facades.items():
        area, nm, share = _facade_shares(ctx, fc)
        if area < 30 or nm is None or share < 0.72:
            continue
        if out and out[0].data.get("block") == nm and share < 0.85:
            continue
        sev = "major" if share >= 0.85 else "minor"
        rr, cc = np.nonzero(fc.has)
        k = len(rr) // 2
        out.append(ctx.finding("monotone_block", sev, f"{SIDE_TR[side]} cephenin %{share * 100:.0f}'i tek blok ({nm}).",
                               "Cepheyi taban (koyu taş), gövde (ana malzeme + varyant), çerçeve (kütük/ahşap) ve çatı olarak katmanla.",
                               positions=[fc.loc(int(rr[k]), int(cc[k]))], count=area, data={"side": side, "block": nm, "share": round(share, 3)}))
    return out


def _block_bbox(ctx: Ctx):
    core = ctx.T["block"][ctx.ids[ctx.core_sl]]
    if not core.any():
        return None
    ys = np.flatnonzero(core.any(axis=(1, 2)))
    zs = np.flatnonzero(core.any(axis=(0, 2)))
    xs = np.flatnonzero(core.any(axis=(0, 1)))
    return (int(xs[-1] - xs[0] + 1), int(ys[-1] - ys[0] + 1), int(zs[-1] - zs[0] + 1))


def _ctx_kind(ctx: Ctx) -> str:
    return " ".join(str(ctx.context.get(k) or "") for k in ("type", "kind", "style", "tur")).lower() + " " + \
        str(ctx.meta.get("style") or "").lower() + " " + str(ctx.build.name or "").lower()


@check("proportion", "Tuhaf oranlar: çok ince-uzun, çok yayvan-basık kütle ya da basık (2 blok) iç tavan.", "estetik")
def c_proportion(ctx: Ctx) -> list[Finding]:
    bb = _block_bbox(ctx)
    if bb is None:
        return []
    W, H, D = bb
    kind = _ctx_kind(ctx)
    out = []
    mn, mxh = min(W, D), max(W, D)
    tall_ok = any(k in kind for k in ("kule", "tower", "minare", "minaret", "obelisk", "fener", "lighthouse", "anıt", "direk", "pole", "heykel", "statue"))
    if H >= 12 and H / max(1, mxh) > 5 and not tall_ok:
        r = H / max(1, mxh)
        out.append(ctx.finding("proportion", "major" if r > 8 else "minor", f"Kütle çok ince ve uzun (yükseklik/genişlik = {r:.1f}; {W}x{D} taban, {H} yükseklik).",
                               "Tabanı genişlet ya da kademeli (yukarı doğru daralan) yap; kuleyse payanda, çıkma ve kat kornişleri ekle.",
                               count=H, data={"W": W, "H": H, "D": D}))
    long_ok = any(k in kind for k in ("köprü", "bridge", "sur", "wall", "duvar", "yol", "road", "çit", "fence", "iskele", "pier", "kanal", "aqueduct", "su kemeri"))
    if mn >= 3 and mxh / mn > 5 and H < 1.5 * mn and not long_ok:
        out.append(ctx.finding("proportion", "minor", f"Uzun ince kutu kütle ({W}x{D}, yükseklik {H}): oran {mxh / mn:.1f}.",
                               "Kütleyi böl: çıkıntı, kule, kat farkı, avlu ya da çatı kırılmalarıyla ritim ver.", count=mxh, data={"W": W, "H": H, "D": D}))
    rooms = [r for r in ctx.used_rooms() if r.source == "meta" or r.floor_area >= 9]
    if rooms and H <= 4 and W * D >= 200:
        out.append(ctx.finding("proportion", "minor", f"Çok basık kütle: {W}x{D} tabana {H} yükseklik.",
                               "Kat yüksekliğini 4-5 bloğa çıkar ya da çatıyı yükselt.", count=H, data={"W": W, "H": H, "D": D}))
    low_rooms = []
    P = ctx.P
    for r in rooms:
        if r.floor.size == 0:
            continue
        h = np.zeros(r.floor.size, np.int16)
        cur = r.floor.copy()
        Pf = P.reshape(-1)
        alive = np.ones(r.floor.size, bool)
        for k in range(6):
            inb = cur < Pf.size
            ok = np.zeros(cur.size, bool)
            ok[inb] = Pf[cur[inb]]
            alive &= ok
            h += alive
            cur = cur + ctx.OFF["up"]
            if not alive.any():
                break
        if np.median(h) <= 2:
            low_rooms.append(r)
    if low_rooms:
        idx = np.concatenate([r.floor for r in low_rooms])
        out.append(ctx.finding("proportion", "minor", f"{len(low_rooms)} odada iç tavan yalnız 2 blok: basık ve sıkışık.",
                               "Kat yüksekliğini döşeme dahil 4-5 blok yap (en az 3 blok boşluk).", idx=idx,
                               data={"rooms": [r.name for r in low_rooms[:6]]}))
    return out


@check("palette_variety", "Malzeme paleti çok dar (1-2 aile) ya da çok dağınık/uyumsuz (çok aile, çok renk).", "estetik")
def c_palette_variety(ctx: Ctx) -> list[Finding]:
    core = ctx.ids[ctx.core_sl].reshape(-1)
    st = ctx.T["structural"][core]
    n = int(st.sum())
    if n < 60:
        return []
    cnt = np.bincount(core[st], minlength=ctx.n)
    fam: dict[str, int] = defaultdict(int)
    dyes: dict[str, int] = defaultdict(int)
    for i in np.flatnonzero(cnt):
        fam[ctx.family[i]] += int(cnt[i])
        if ctx.dye[i]:
            dyes[ctx.dye[i]] += int(cnt[i])
    main = [f for f, c in fam.items() if c / n >= 0.03]
    sig = [f for f, c in fam.items() if c / n >= 0.02]
    ctx.stats["families"] = len(main)
    out = []
    if n >= 150 and len(main) <= 2:
        sev = "major" if len(main) <= 1 else "minor"
        out.append(ctx.finding("palette_variety", sev, f"Yalnız {len(main)} malzeme ailesi ({', '.join(sorted(main))}): doku zayıf.",
                               "Ana malzeme + vurgu/çerçeve + taban + çatı için 4-6 uyumlu aile seç (ör. taş tuğla, koyu meşe, kalsit, kiremit).",
                               count=n, data={"families": sorted(main)}))
    if len(sig) >= 11:
        out.append(ctx.finding("palette_variety", "minor", f"{len(sig)} farklı malzeme ailesi: palet dağınık, uyumsuz görünür.",
                               "Paleti 4-7 aileye indir; az kullanılanları baskın ailenin varyantlarıyla değiştir.", count=len(sig),
                               data={"families": sorted(sig)}))
    big_dyes = [d for d, c in dyes.items() if c / n >= 0.02]
    if len(big_dyes) >= 5:
        out.append(ctx.finding("palette_variety", "minor", f"{len(big_dyes)} farklı boya rengi ({', '.join(sorted(big_dyes))}): renk karmaşası.",
                               "Bir ana renk + 1-2 vurgu rengiyle sınırla; doğal malzemelerle dengele.", count=len(big_dyes),
                               data={"dyes": sorted(big_dyes)}))
    return out


def _exempt(r: Room, keys) -> bool:
    s = (r.name + " " + r.kind).lower()
    return any(k in s for k in keys)


@check("window_presence", "Kapalı oda penceresiz (cam/cam panel/parmaklık ya da dışa açıklık yok).", "iç mekân")
def c_window_presence(ctx: Ctx) -> list[Finding]:
    out = []
    win = ctx.m("window").reshape(-1)
    ext = (ctx.P & ctx.open_sky).reshape(-1)
    for r in ctx.used_rooms():
        if r.attic or r.floor_area < 6 or _exempt(r, EXEMPT_WINDOW):
            continue
        has = False
        for d in DIRV:
            j = r.cells + ctx.OFF[d]
            if win[j].any() or (d not in ("up", "down") and ext[j].any()):
                has = True
                break
        if has:
            continue
        sev = "major" if r.floor_area >= 12 else "minor"
        out.append(ctx.finding("window_presence", sev, f"'{r.name}' odası penceresiz ({r.floor_area} zemin hücresi).",
                               "Dış duvara 2-3 blokta bir cam panel/vitray pencere aç; pervaz ve kepenkle çerçevele.", idx=r.floor,
                               data={"room": r.name}))
    return _compact(out, "window_presence", "{n} oda penceresiz: {names}.")


@check("roof_presence", "Duvarlarla çevrili hacmin üstü açık: çatı/örtü yok.", "estetik")
def c_roof_presence(ctx: Ctx) -> list[Finding]:
    out = []
    P = ctx.P
    roofsky = LT.open_to_sky(ctx.m("cover") | ctx.m("glass"))   # cam cati/isik kubbesi de ortudur
    opn = ctx.m("openable")
    mask = P & ~opn
    lab, _ = label(mask, 6, planar=True)
    ring = np.ones(ctx.shape[1:], bool)
    ring[1:-1, 1:-1] = False
    outs = np.unique(lab[:, ring])
    enc = mask & ~np.isin(lab, outs) & ctx.core_mask
    if enc.any():
        lab3, _ = label(enc, 6)
        flat = lab3.reshape(-1)
        below = np.zeros(ctx.shape, bool)
        below[1:] = ~P[:-1]
        nfl = np.bincount(flat[(below & enc).reshape(-1)], minlength=1)
        cand = np.flatnonzero(nfl >= 9)
        cand = cand[cand > 0]
        sky = roofsky.reshape(-1)
        cov_air = (P & ~ctx.open_sky).reshape(-1)
        wet = ctx.m("fluid").reshape(-1)
        veg = (ctx.m("leaves") | ctx.m("wlog")).reshape(-1)
        wet = wet | np.roll(wet, -ctx.SY) | np.roll(wet, -2 * ctx.SY)  # suyun ustundeki hava da havuza ait
        for lbl, cells in _groups(flat, cand):
            yi, zi, xi = np.unravel_index(cells, ctx.shape)
            if yi.max() - yi.min() < 2:
                continue
            # havuz/hendek: hacmin cogu sivi ya da zemin altinda -> cati beklenmez
            if wet[cells].mean() > 0.3 or (ctx.origin[1] + int(yi.max()) - PADB) < 1:
                continue
            # agac taclari arasi bosluk: cevreleyen 'duvar' cogunlukla yaprak/kutuk -> yapi degil
            ring = np.concatenate([cells + ctx.OFF[d] for d in ("north", "south", "east", "west")])
            ring = ring[~enc.reshape(-1)[ring]]
            if ring.size and veg[ring].mean() > 0.5:
                continue
            uncovered = float(sky[cells].mean())
            if uncovered < 0.75:
                continue
            # avlu mu? cevredeki (4 blok) ortulu ic hacim
            fz = np.unique(zi * ctx.shape[2] + xi)
            foot = np.zeros(ctx.shape[1:], bool).reshape(-1)
            foot[fz] = True
            foot = foot.reshape(ctx.shape[1:])
            dil = foot.copy()
            for _ in range(4):
                g = dil.copy()
                g[1:, :] |= dil[:-1, :]
                g[:-1, :] |= dil[1:, :]
                g[:, 1:] |= dil[:, :-1]
                g[:, :-1] |= dil[:, 1:]
                dil = g
            ringc = dil & ~foot
            ylev = int(yi.min()) + 1
            lay = slice(ylev, min(ctx.shape[0], ylev + 3))
            covered_near = cov_air.reshape(ctx.shape)[lay][:, ringc].sum()
            open_near = (P & ctx.open_sky)[lay][:, ringc].sum()
            if covered_near > 0.5 * max(1, covered_near + open_near):
                continue
            fl = cells[below.reshape(-1)[cells]]
            if fl.size > 120:      # genis acik avlu/kale ici/bahce: oda degil
                continue
            out.append(ctx.finding("roof_presence", "major", f"Duvarlarla çevrili {fl.size} zemin hücrelik hacmin üstü açık: çatı yok.",
                                   "Kapalı hacmi eğimli (merdiven + levha) ya da teraslı bir çatıyla ört; bilinçli avluysa yok say.", idx=fl))
    for r in ctx.rooms:
        if r.source != "meta":
            continue
        sky = roofsky.reshape(-1)[r.cells]
        if sky.mean() > 0.5:
            out.append(ctx.finding("roof_presence", "major", f"'{r.name}' odasının üstü açık (çatı/tavan yok).",
                                   "Odanın üstünü tavan ve çatıyla kapat.", idx=r.floor, data={"room": r.name}))
    return out


@check("empty_interior", "Büyük oda boş: mobilya/eşya yok ya da çok seyrek.", "iç mekân")
def c_empty_interior(ctx: Ctx) -> list[Finding]:
    out = []
    furn = ctx.m("furniture")
    ents = [e for e in ctx.build.entities if str(e.get("type", "")).split(":")[-1] in ("painting", "item_frame", "glow_item_frame", "armor_stand")]
    epos = [ctx.to_pad(*e["pos"][:3]) for e in ents if e.get("pos")]
    for r in ctx.used_rooms():
        if r.attic or r.floor_area < 16 or _exempt(r, EXEMPT_EMPTY):
            continue
        y0, y1, z0, z1, x0, x1 = r.bbox
        # esya zeminde durur: yalniz zemin + 2 blok yuksekligine bak (tonozlu odada cati merdivenleri sayilmasin)
        sub = furn[y0:min(y1, y0 + 2) + 1, z0:z1 + 1, x0:x1 + 1]
        n = int(np.count_nonzero(sub))
        n += sum(1 for (a, b, c) in epos if y0 <= a <= y1 and z0 - 1 <= b <= z1 + 1 and x0 - 1 <= c <= x1 + 1)
        dens = n / max(1, r.floor_area)
        if n == 0:
            sev = "major" if r.floor_area >= 25 else "minor"
            msg = f"'{r.name}' odası ({r.floor_area} zemin hücresi) bomboş: hiç eşya yok."
        elif dens < 1 / 30:
            sev = "minor"
            msg = f"'{r.name}' odası ({r.floor_area} zemin hücresi) çok seyrek döşenmiş ({n} eşya)."
        else:
            continue
        out.append(ctx.finding("empty_interior", sev, msg,
                               "İşlevine uygun eşya ekle: yatak, sandık/fıçı, masa (çit + baskı plakası), sandalye (merdiven), kitaplık, halı, saksı, tablo.",
                               idx=r.floor, data={"room": r.name, "items": n}))
    return _compact(out, "empty_interior", "{n} oda boş ya da çok seyrek döşenmiş: {names}.")


@check("lighting_density", "İç mekân loş (zeminin çoğunda ışık < 8), aşırı ışık kalabalığı ya da girişin önü karanlık.", "aydınlatma")
def c_lighting_density(ctx: Ctx) -> list[Finding]:
    out = []
    L = ctx.blight.reshape(-1)
    S = ctx.walk["S"].reshape(-1)
    src = ctx.m("light_src")
    dims, totf, totdim = [], 0, 0
    for r in ctx.used_rooms():
        if r.attic or r.floor_area < 6:
            continue
        fl = r.floor[S[r.floor]]
        if fl.size < 6:
            continue
        dim = L[fl] < 8
        totf += fl.size
        totdim += int(dim.sum())
        if fl.size >= 12 and dim.mean() >= 0.5:
            dims.append((r, fl[dim], float(dim.mean())))
        y0, y1, z0, z1, x0, x1 = r.bbox
        nl = int(np.count_nonzero(src[y0:y1 + 2, z0:z1 + 1, x0:x1 + 1]))
        if r.floor_area >= 9 and nl / r.floor_area > 0.25:
            out.append(ctx.finding("lighting_density", "minor", f"'{r.name}' odasında ışık kalabalığı ({nl} kaynak / {r.floor_area} zemin).",
                                   "Işık kaynaklarını azalt; gizli aydınlatma (halı altı ışık bloğu, levha arkası fener) kullan.",
                                   idx=r.floor, data={"room": r.name}))
    if totf:
        ctx.stats["dim_fraction"] = round(totdim / totf, 3)
    dimf = [ctx.finding("lighting_density", "minor", f"'{r.name}' odası loş: zeminin %{frac * 100:.0f}'inde ışık 8'in altında.",
                        "Her 6-8 blokta bir fener/duvar meşalesi ya da gizli ışık ekle; köşeleri unutma.", idx=idx,
                        data={"room": r.name}) for r, idx, frac in dims]
    out = _compact(out, "lighting_density", "{n} odada ışık kalabalığı: {names}.") + \
        _compact(dimf, "lighting_density", "{n} oda loş (zeminin yarısından çoğunda ışık < 8): {names}.")
    low = ctx.cm("door_lower")
    if low.any():
        idx = np.flatnonzero(low)
        od = ctx.outdoorish.reshape(-1)
        dark = []
        for i in idx:
            f = ctx.props[int(ctx.flat[i])].get("facing")
            if f not in HORIZ:
                continue
            a, b = i + ctx.OFF[f], i + ctx.OFF[OPP[f]]
            if od[a] == od[b]:
                continue
            o = a if od[a] else b
            if S[o] and L[o] < 8:
                dark.append(i)
        if dark:
            out.append(ctx.finding("lighting_density", "minor", f"{len(dark)} giriş kapısının önü karanlık (ışık < 8).",
                                   "Kapının iki yanına duvar feneri/meşale ya da üstüne asılı fener koy.", idx=np.array(dark)))
    return out


@check("dark_spots", "Üstü örtülü karanlık nokta: blok ışığı 0, altı sağlam, üstünde 2 boşluk — canavar doğabilir.", "aydınlatma")
def c_dark_spots(ctx: Ctx) -> list[Finding]:
    sp = LT.spawnable(ctx.m("spawn_floor"), ctx.m("spawn_empty"))
    spots = sp & (ctx.blight == 0) & ~ctx.outdoorish & ctx.core_mask
    if spots.any():
        # yalniz agac taci altinda (ustunde yaprak/kutukten baska ortu yok): dogal golge, acik arazi gibi sayilir
        strp = np.array([n.startswith("stripped_") for n in ctx.names], bool)
        vt = ctx.T["leaves"] | ((ctx.T["wlog"] | np.array(
            [n.endswith(("_log", "_wood", "_stem", "_hyphae")) for n in ctx.names], bool)) & ~strp)
        spots &= ~LT.open_to_sky(ctx.m("cover") & ~vt[ctx.ids])
        spots &= ~ctx.underwater()                       # dunyada su altinda: canavar dogmaz
    if not spots.any():
        ctx.stats["dark_spots"] = 0
        return []
    open_ = spots & ctx.air_outside
    sealed = spots & ~ctx.air_outside
    ctx.stats["dark_spots"] = int(spots.sum())
    out = []
    if open_.any():
        idx = np.flatnonzero(open_)
        out.append(ctx.finding("dark_spots", "major", f"{idx.size} karanlık nokta (blok ışığı 0, üstü örtülü): canavar doğabilir.",
                               "Bu noktalara en çok 6-8 blok mesafede ışık kaynağı ekle (fener, duvar meşalesi, deniz feneri, gizli ışık).", idx=idx))
    if sealed.any():
        idx = np.flatnonzero(sealed)
        out.append(ctx.finding("dark_spots", "minor", f"Kapalı boşluklarda {idx.size} karanlık nokta (çatı arası/duvar içi): canavar doğup sıkışabilir.",
                               "Kapalı boşlukları doldur, levhayla 1 bloğa indir ya da içine ışık koy.", idx=idx))
    return out


@check("symmetry_rhythm", "İpucu: ön cephe neredeyse simetrik ama birkaç hücre bozuyor; pencere aralıkları düzensiz.", "estetik")
def c_symmetry_rhythm(ctx: Ctx) -> list[Finding]:
    fc = ctx.facades.get("north")
    if fc is None or not fc.has.any():
        return []
    out = []
    cols = np.flatnonzero(fc.has.any(axis=0))
    rows = np.flatnonzero(fc.has.any(axis=1))
    c0, c1 = int(cols[0]), int(cols[-1])
    W = c1 - c0 + 1
    # doku varyantlari (yosunlu/catlak/andezit serpintisi) asimetri sayilmasin: BICIM + derinlik karsilastirilir
    T = ctx.T
    form = np.zeros(ctx.n, np.int64)
    form[T["visible"]] = 1
    form[T["visible"] & ~T["full"]] = 2
    form[T["window"]] = 3
    form[T["door"]] = 4
    form[T["light_like"] & T["visible"]] = 5
    form[T["plant"] | T["leaves"]] = 6
    if W >= 7:
        sub_has = fc.has[:, c0:c1 + 1]
        sub = np.where(sub_has, form[fc.pid[:, c0:c1 + 1]] * 1000 + fc.depth[:, c0:c1 + 1], -1)
        mir = sub[:, ::-1]
        any_ = sub_has | sub_has[:, ::-1]
        diff = (sub != mir) & any_
        tot = int(any_.sum())
        nd = int(diff.sum())
        sym = 1 - nd / max(1, tot)
        if 0.85 <= sym < 0.985 and nd // 2 <= 12:
            rr, cc = np.nonzero(diff[:, : (W + 1) // 2])
            pos = [fc.loc(int(r), int(c) + c0) if fc.has[r, c + c0] else fc.loc(int(r), W - 1 - int(c) + c0) for r, c in zip(rr[:6], cc[:6])]
            out.append(ctx.finding("symmetry_rhythm", "minor", f"Ön cephe neredeyse simetrik (%{sym * 100:.0f}); {nd // 2} hücre çifti bozuyor.",
                                   "Simetriyi tamamla (karşılıklı pencere/süs) ya da asimetriyi bilinçli ve belirgin yap.", positions=pos, count=nd // 2,
                                   data={"symmetry": round(sym, 3)}))
    # ritim: ayni kat bandindaki acikliklar (pencere + kapi) arasindaki araliklar
    opening = fc.has & (ctx.T["window"] | ctx.T["door"])[fc.pid]
    if opening.any():
        lab, _ = label(opening[None, :, :], 18)
        lab = lab[0]
        groups = _groups(lab.reshape(-1), np.unique(lab[lab > 0]))
        bands: dict[int, list] = defaultdict(list)
        for _, cells in groups:
            r, c = np.unravel_index(cells, lab.shape)
            bands[int(r.max())].append(float(c.mean()))
        for top, centers in bands.items():
            if len(centers) < 4:
                continue
            cs = np.sort(np.array(centers))
            gaps = np.diff(cs)
            if gaps.mean() <= 0:
                continue
            cv = float(gaps.std() / gaps.mean())
            if cv > 0.4:
                out.append(ctx.finding("symmetry_rhythm", "minor", f"Ön cephede pencere/kapı aralıkları düzensiz (aralıklar: {', '.join(str(int(round(g))) for g in gaps)}).",
                                       "Açıklıkları eşit aralıkla diz (ör. her 3-4 blokta bir) ya da bilinçli gruplar (2'li/3'lü) yap.",
                                       positions=[fc.loc(top, int(round(c))) for c in cs[:6]], count=len(centers), data={"cv": round(cv, 3)}))
                break
    return out


@check("flat_roof", "Çatı düz kutu: tek seviye, eğim/saçak/mahya yok.", "estetik")
def c_flat_roof(ctx: Ctx) -> list[Finding]:
    kind = _ctx_kind(ctx)
    if any(k in kind for k in ("modern", "flat", "düz çatı", "teras", "fütürist", "futur", "bunker", "brutal")):
        return []
    rooms = [r for r in ctx.used_rooms() if not r.attic and (r.source == "meta" or r.floor_area >= 9)]
    if not rooms:
        return []
    core = ctx.ids[ctx.core_sl]
    vis = ctx.T["visible"][core]
    Y = vis.shape[0]
    has = vis.any(axis=0)
    top = Y - 1 - np.argmax(vis[::-1], axis=0)
    cols = np.zeros(has.shape, bool)
    for r in rooms:
        _, zi, xi = np.unravel_index(r.cells, ctx.shape)
        cols[zi - PADX, xi - PADX] = True
    cols &= has
    if cols.sum() < 9:
        return []
    th = top[cols]
    vals, cnt = np.unique(th, return_counts=True)
    mode = int(vals[np.argmax(cnt)])
    if cnt.max() / th.size < 0.9:
        return []
    zz, xx = np.nonzero(cols & (top == mode))
    tp = core[mode, zz, xx]
    if ctx.T["full"][tp].mean() < 0.8:
        return []
    roof_fp = vis[mode]
    lower_fp = vis[:mode].any(axis=0) if mode > 0 else np.zeros_like(roof_fp)
    if int(np.count_nonzero(roof_fp & ~lower_fp)) > 0:   # cati alt kutlenin disina tasiyor = sacak var
        return []
    above = vis[mode + 1:].any(axis=0) & cols if mode + 1 < Y else np.zeros_like(cols)
    if above.sum() > 0.1 * cols.sum():
        return []
    pos = [[ctx.origin[0] + int(x), ctx.origin[1] + mode, ctx.origin[2] + int(z)] for z, x in list(zip(zz, xx))[:: max(1, len(zz) // 4)][:4]]
    return [ctx.finding("flat_roof", "minor", f"Çatı düz kutu: {int(cols.sum())} sütunun %{cnt.max() / th.size * 100:.0f}'i aynı seviyede, saçak taşması yok.",
                        "Eğimli çatı (merdiven + levha) yap, 1 blok saçak taşır, mahya ve çatı penceresi ekle; düz çatı istenmişse korkuluk/parapet ve teras süsü ekle.",
                        positions=pos, count=int(cols.sum()))]


def _grow2d(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for _ in range(r):
        g = out.copy()
        g[1:, :] |= out[:-1, :]
        g[:-1, :] |= out[1:, :]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


@check("bare_windows", "Pencereler çerçevesiz 'delik pencere': pervaz, kepenk, girinti ya da farklı çerçeve malzemesi yok.", "estetik")
def c_bare_windows(ctx: Ctx) -> list[Finding]:
    out = []
    full = ctx.T["full"]
    win = ctx.T["window"]
    names = np.array([ctx.names[i] for i in range(ctx.n)], dtype=object)
    for side, fc in ctx.facades.items():
        wm = fc.has & win[fc.pid]
        if wm.sum() < 2:
            continue
        wall = fc.has & full[fc.pid] & ~win[fc.pid]
        if wall.sum() < 10:
            continue
        u, c = np.unique(names[fc.pid[wall]], return_counts=True)
        dom = u[np.argmax(c)]
        lab, _ = label(wm[None, :, :], 18)
        lab = lab[0]
        groups = _groups(lab.reshape(-1), np.unique(lab[lab > 0]))
        if len(groups) < 2:
            continue
        H, W = wm.shape
        bare = []
        for _, cells in groups:
            g = np.zeros(wm.size, bool)
            g[cells] = True
            g = g.reshape(wm.shape)
            ring = _grow2d(g, 1)
            # 8-komsuluk
            ring[1:, 1:] |= g[:-1, :-1]
            ring[1:, :-1] |= g[:-1, 1:]
            ring[:-1, 1:] |= g[1:, :-1]
            ring[:-1, :-1] |= g[1:, 1:]
            ring &= ~wm
            rr, cc = np.nonzero(ring)
            if rr.size == 0:
                continue
            wd = int(fc.depth[g].min())
            framed = False
            for a, b in zip(rr, cc):
                if not fc.has[a, b]:
                    continue
                if fc.depth[a, b] != wd or not full[fc.pid[a, b]] or names[fc.pid[a, b]] != dom:
                    framed = True
                    break
            if not framed:
                r0, c0 = np.unravel_index(cells[0], wm.shape)
                bare.append(fc.loc(int(r0), int(c0)))
        frac = len(bare) / len(groups)
        if frac >= 0.6:
            out.append(ctx.finding("bare_windows", "minor", f"{SIDE_TR[side]} cephedeki pencerelerin %{frac * 100:.0f}'i çerçevesiz (delik pencere).",
                                   "Pencerelere pervaz (merdiven/levha), kepenk (tuzak kapı), farklı malzemeden çerçeve (soyulmuş kütük) ekle; camı 1 blok içeri al.",
                                   positions=bare[:6], count=len(bare), data={"side": side}))
    return out


# ====================================================================== genel istatistikler (puanlama icin)
def global_stats(ctx: Ctx) -> dict:
    st = ctx.stats
    bb = _block_bbox(ctx)
    st["size"] = list(bb) if bb else [0, 0, 0]
    st["blocks"] = ctx.n_blocks
    core = ctx.ids[ctx.core_sl].reshape(-1)
    if ctx.n_blocks:
        stc = ctx.T["structural"][core]
        cnt = np.bincount(core[stc], minlength=ctx.n)
        fam: dict[str, int] = defaultdict(int)
        for i in np.flatnonzero(cnt):
            fam[ctx.family[i]] += int(cnt[i])
        tot = max(1, int(stc.sum()))
        st.setdefault("families", sum(1 for c in fam.values() if c / tot >= 0.03))
        st["top_family_share"] = round(max(fam.values()) / tot, 3) if fam else 0.0
        st["landscape_blocks"] = int(np.count_nonzero(ctx.T["landscape"][core]))
        st["light_sources"] = int(np.count_nonzero(ctx.T["light_src"][core]))
    fac = {}
    tot_vis = tot_rel = tot_dec = 0
    for side, fc in ctx.facades.items():
        area = int(fc.has.sum())
        if area == 0:
            continue
        d = fc.depth[fc.has]
        vals, cnt = np.unique(d, return_counts=True)
        mode = vals[np.argmax(cnt)]
        partial = ~ctx.T["full"][fc.pid[fc.has]]
        rel = (d != mode) | partial
        tot_vis += area
        tot_rel += int(rel.sum())
        tot_dec += int(partial.sum())
        _, nm, share = _facade_shares(ctx, fc)
        fac[side] = {"area": area, "relief": round(float(rel.mean()), 3), "top_block": nm, "top_share": round(share, 3)}
    st["facades"] = fac
    st["relief_ratio"] = round(tot_rel / tot_vis, 3) if tot_vis else 0.0
    st["decor_ratio"] = round(tot_dec / tot_vis, 3) if tot_vis else 0.0
    # ust yuzey: egimli cati orani ve siluet kademeleri
    corev = ctx.ids[ctx.core_sl]
    vis = ctx.T["visible"][corev]
    if vis.any():
        Y = vis.shape[0]
        has = vis.any(axis=0)
        top = Y - 1 - np.argmax(vis[::-1], axis=0)
        zz, xx = np.nonzero(has)
        tp = corev[top[has], zz, xx]
        st["roof_pitch"] = round(float((ctx.T["stairs"] | ctx.T["slab"])[tp].mean()), 3)
        vals, cnt = np.unique(top[has], return_counts=True)
        st["skyline_levels"] = int(np.count_nonzero(cnt >= max(2, 0.05 * has.sum())))
    st["terrain"] = ctx.context.get("heightmap") is not None
    st["style"] = str(ctx.context.get("style") or ctx.meta.get("style") or "")
    if "rooms" in ctx.__dict__:
        ur = ctx.used_rooms()
        st["rooms"] = len(ur)
        st["sealed_rooms"] = sum(1 for r in ctx.rooms if r.sealed and r.source == "auto")
    return st


__all__ = ["Finding", "Report", "Check", "CHECKS", "Ctx", "Room", "Facade", "label", "global_stats", "SEVERITIES", "SEV_RANK"]
