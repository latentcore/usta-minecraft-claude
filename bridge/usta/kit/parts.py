"""parts: yeniden kullanilabilir usta yapi parcalari. (Bu metin modul sonunda __doc__ olarak yeniden kurulur.)"""
from __future__ import annotations

import math
from functools import wraps
from typing import Callable, Iterable, Sequence

import numpy as np

from .. import blockdb
from ..plan import AIR, KEEP
from . import shapes as S
from . import style as _style
from .style import Style

CATALOG: dict[str, str] = {}
PARTS: dict[str, Callable] = {}

DIRS = ("north", "east", "south", "west")
VEC = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0), "down": (0, -1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east", "up": "down", "down": "up"}
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}
ROT = {"north": 0, "east": 1, "south": 2, "west": 3}
# Cephe cercevesinde (Frame) kanonik yon adlari: OUT = disari, IN = iceri, R = u+ (duvar boyunca), L = u-
OUT, IN, R, L = "north", "south", "east", "west"


def _st(st: Style | None) -> Style:
    return st if st is not None else _style.get("medieval")


def _db() -> blockdb.BlockDB:
    return blockdb.get()


# ====================================================================== kayit / kutu izleme
class _Rec:
    """Build vekili: tum yazmalarin kutusunu izler (parcanin bildirdigi kutuyla karsilastirmak icin)."""

    def __init__(self, b):
        object.__setattr__(self, "_b", b)
        object.__setattr__(self, "lo", [None, None, None])
        object.__setattr__(self, "hi", [None, None, None])

    def __getattr__(self, name):
        return getattr(self._b, name)

    def _grow(self, x0, y0, z0, x1, y1, z1):
        lo, hi = self.lo, self.hi
        for i, (a, c) in enumerate(((min(x0, x1), max(x0, x1)), (min(y0, y1), max(y0, y1)), (min(z0, z1), max(z0, z1)))):
            lo[i] = a if lo[i] is None else min(lo[i], a)
            hi[i] = c if hi[i] is None else max(hi[i], c)

    @property
    def box(self):
        if self.lo[0] is None:
            return None
        return (self.lo[0], self.lo[1], self.lo[2], self.hi[0], self.hi[1], self.hi[2])

    def set(self, x, y, z, state):
        self._grow(x, y, z, x, y, z)
        self._b.set(x, y, z, state)

    def fill(self, x0, y0, z0, x1, y1, z1, state, **kw):
        self._grow(x0, y0, z0, x1, y1, z1)
        self._b.fill(x0, y0, z0, x1, y1, z1, state, **kw)

    def clear(self, x0, y0, z0, x1, y1, z1):
        self._grow(x0, y0, z0, x1, y1, z1)
        self._b.clear(x0, y0, z0, x1, y1, z1)

    def forget(self, x0, y0, z0, x1, y1, z1):
        self._b.forget(x0, y0, z0, x1, y1, z1)

    def put_mask(self, x0, y0, z0, mask, state, only_empty=False):
        if mask.any():
            ys = np.nonzero(mask.any(axis=(1, 2)))[0]
            zs = np.nonzero(mask.any(axis=(0, 2)))[0]
            xs = np.nonzero(mask.any(axis=(0, 1)))[0]
            self._grow(x0 + xs[0], y0 + ys[0], z0 + zs[0], x0 + xs[-1], y0 + ys[-1], z0 + zs[-1])
        self._b.put_mask(x0, y0, z0, mask, state, only_empty=only_empty)

    def put_ids(self, x0, y0, z0, ids, palette=None):
        sy, sz, sx = ids.shape
        self._grow(x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1)
        self._b.put_ids(x0, y0, z0, ids, palette)

    def line(self, p0, p1, state):
        self._grow(*p0, *p1)
        self._b.line(p0, p1, state)


def part(name: str, desc: str):
    """Parca kaydi: CATALOG'a ekler; sonuc sozlugune 'name' ve 'written' (gercek yazma kutusu) koyar."""
    def deco(fn):
        @wraps(fn)
        def wrapper(b, *a, **kw):
            rec = _Rec(b)
            res = fn(rec, *a, **kw)
            if res is None:
                res = {}
            res.setdefault("name", name)
            res["written"] = rec.box
            if "box" not in res:
                res["box"] = rec.box
            return res
        CATALOG[name] = desc
        PARTS[name] = wrapper
        return wrapper
    return deco


def _box(*pts) -> tuple[int, int, int, int, int, int]:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _meta(b, key: str, entry: dict) -> None:
    b.meta.setdefault(key, []).append(entry)


# ====================================================================== cephe cercevesi
class Frame:
    """Cephe-yerel koordinatlar: u duvar boyunca, v yukari (y), n disari (n>0 cephenin onu, n<0 ic taraf).
    Durumlar kuzeye bakan cephe icin yazilir (north=OUT, south=IN, east=u+, west=u-); Frame dondurur."""

    def __init__(self, b, face: str = "north", origin: Sequence[int] = (0, 0, 0)):
        if face not in ROT:
            raise ValueError(f"cephe yonu: {DIRS}")
        self.b = b
        self.face = face
        self.r = ROT[face]
        self.o = (int(origin[0]), int(origin[1]), int(origin[2]))
        self._sc: dict[str, str] = {}

    def xyz(self, u: int, v: int, n: int) -> tuple[int, int, int]:
        x, z = u, -n
        for _ in range(self.r):
            x, z = -z, x
        return self.o[0] + x, self.o[1] + v, self.o[2] + z

    def dir(self, d: str) -> str:
        if d in ("up", "down"):
            return d
        return DIRS[(DIRS.index(d) + self.r) % 4]

    def s(self, state: str) -> str:
        if self.r == 0 or state in (KEEP, AIR, "air", "minecraft:air"):
            return state
        r = self._sc.get(state)
        if r is None:
            ex = state.startswith("!")
            body = state[1:] if ex else state
            r = _db().rotate(body, self.r)
            r = ("!" + r) if ex else r
            self._sc[state] = r
        return r

    def set(self, u, v, n, state) -> None:
        self.b.set(*self.xyz(u, v, n), self.s(state))

    def get(self, u, v, n) -> str:
        return self.b.get(*self.xyz(u, v, n))

    def fill(self, u0, v0, n0, u1, v1, n1, state, **kw) -> None:
        self.b.fill(*self.xyz(u0, v0, n0), *self.xyz(u1, v1, n1), self.s(state), **kw)

    def clear(self, u0, v0, n0, u1, v1, n1) -> None:
        self.b.fill(*self.xyz(u0, v0, n0), *self.xyz(u1, v1, n1), AIR)

    def sfill(self, st: Style, role: str, u0, v0, n0, u1, v1, n1, **kw) -> None:
        st.fill(self.b, *self.xyz(u0, v0, n0), *self.xyz(u1, v1, n1), role, **kw)

    def sset(self, st: Style, role: str, u, v, n) -> None:
        x, y, z = self.xyz(u, v, n)
        self.b.set(x, y, z, st.pick(role, x, y, z))

    def box(self, u0, v0, n0, u1, v1, n1) -> tuple[int, int, int, int, int, int]:
        return _box(self.xyz(u0, v0, n0), self.xyz(u1, v1, n1))

    def put_profile(self, prof: np.ndarray, u0: int, v0: int, n: int, state) -> None:
        """2B maske [v, u] -> cephe duzleminde n derinliginde yazar (state ya da (st, role))."""
        vs, us = np.nonzero(prof)
        for v, u in zip(vs.tolist(), us.tolist()):
            if isinstance(state, tuple):
                self.sset(state[0], state[1], u0 + u, v0 + v, n)
            else:
                self.set(u0 + u, v0 + v, n, state)


def facade(b, face: str, x: int, y: int, z: int, w: int = 1) -> Frame:
    """Acikligin en kucuk koordinatli alt hucresi (x,y,z) duvar duzleminde; genislik w (+x ya da +z boyunca).
    Donen Frame'de u = 0..w-1 acikligi kaplar."""
    ox = x + (w - 1 if face == "south" else 0)
    oz = z + (w - 1 if face == "west" else 0)
    return Frame(b, face, (ox, y, oz))


def _sides(x0, z0, x1, z1):
    """Dikdortgenin dort cephesi: (face, x, z, w) -- facade() argumanlari (koseler dahil)."""
    return [("north", x0, z0, x1 - x0 + 1), ("south", x0, z1, x1 - x0 + 1),
            ("east", x1, z0, z1 - z0 + 1), ("west", x0, z0, z1 - z0 + 1)]


def _post(st: Style, role: str) -> str:
    """Rol icin ince dikme: ahsapsa cit, camsa panel, metalse kendisi, tas ise duvar blogu."""
    base = st.base(role)
    if base.endswith(("_fence", "_wall", "_pane", "_bars", "iron_bars")) or base.endswith("chain"):
        return st.block(role)
    if _style.wood_of(base) and base not in ("bamboo_mosaic",):
        return st.form(role, "fence")
    if "glass" in base:
        return st.form(role, "pane")
    return st.form(role, "wall")


def _is_wood(st: Style, role: str) -> bool:
    return _style.wood_of(st.base(role)) is not None


def _axis_log(state: str, axis: str) -> str:
    db = _db()
    if "axis" in db.props(state.lstrip("!")):
        return db.with_props(state.lstrip("!"), axis=axis)
    return state


def _with(state: str, **props) -> str:
    db = _db()
    allowed = db.blocks[blockdb.split_state(state)[0]]["props"]
    pp = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in props.items() if k in allowed}
    return db.with_props(state.lstrip("!"), **pp) if pp else state


def _light(b, x, y, z, state: str) -> None:
    b.set(x, y, z, state)
    _meta(b, "lights", {"pos": [x, y, z], "block": state})


# ====================================================================== fizik denetimi
_SOIL = {"grass_block", "dirt", "coarse_dirt", "podzol", "rooted_dirt", "moss_block", "pale_moss_block", "mud",
         "muddy_mangrove_roots", "mycelium", "farmland", "crimson_nylium", "warped_nylium", "soul_soil", "soul_sand",
         "sand", "red_sand", "terracotta", "clay", "dirt_path"}
_POSTS = ("_fence", "_wall", "_pane", "iron_bars", "_bars", "end_rod", "lightning_rod", "chain")


def _short(s: str) -> str:
    n = s.lstrip("!").split("[", 1)[0]
    return n.split(":", 1)[1] if ":" in n else n


def check(b, ground: int | None = None, max_issues: int = 60) -> list[str]:
    """Fizik/kural denetimi: destek isteyen bloklar (mesale, fener, kapi, cicek, hali, tabela...), kapinin iki yarisi,
    cift bitkiler, yercekimli bloklar, yapraklar (persistent), suyun kapali hacimde olmasi.
    ground: bu y ve alti 'keep' hucreler zemin sayilir (plan disi dogal zemin). Bos liste = sorun yok."""
    db = b.db
    org, ids = b.dense()
    ox, oy, oz = org
    pal = b.palette
    n = len(pal)
    name = [""] * n
    props: list[dict] = [{} for _ in range(n)]
    flags = np.zeros(n, dtype=np.int64)
    sturdy = np.zeros(n, dtype=np.int64)
    for i, s in enumerate(pal):
        if i <= 1:
            continue
        st = s.lstrip("!")
        name[i] = _short(st)
        props[i] = blockdb.split_state(st)[1]
        flags[i] = db.flags_of(st)
        sturdy[i] = int(db.sturdy[db.id(st)])
    is_post = np.array([any(name[i].endswith(p) for p in _POSTS) and not (name[i].endswith("chain") and props[i].get("axis") not in (None, "y")) for i in range(n)])
    is_air = np.zeros(n, dtype=bool)
    is_air[1] = True
    for i in range(2, n):
        is_air[i] = bool(flags[i] & blockdb.AIR)
    sy, sz, sx = ids.shape
    issues: list[str] = []

    def at(x, y, z):
        """(palet indeksi | -1 = plan disi)"""
        if 0 <= x - ox < sx and 0 <= y - oy < sy and 0 <= z - oz < sz:
            return int(ids[y - oy, z - oz, x - ox])
        return -1

    def grounded(i, y):
        return i <= 0 and ground is not None and y <= ground

    def bad(x, y, z, i, msg):
        if len(issues) < max_issues:
            issues.append(f"({x},{y},{z}) {name[i]}: {msg}")

    def face_ok(j, face):
        return j > 1 and bool(sturdy[j] & blockdb.FACE_BIT[face])

    present = np.unique(ids)
    for i in present.tolist():
        if i <= 1:
            continue
        f = int(flags[i])
        nm = name[i]
        pr = props[i]
        need = f & (blockdb.SUPPORT_FLOOR | blockdb.SUPPORT_WALL | blockdb.SUPPORT_CEIL | blockdb.GRAVITY | blockdb.FLUID | blockdb.DOUBLE)
        leaves = nm.endswith("_leaves")
        if not need and not leaves and not nm.endswith("_bed"):
            continue
        cells = np.argwhere(ids == i)
        for (cy, cz, cx) in cells.tolist():
            x, y, z = cx + ox, cy + oy, cz + oz
            if leaves:
                if pr.get("persistent") == "false":
                    bad(x, y, z, i, "yaprak kalici degil (persistent=false -> curur)")
                continue
            if nm.endswith("_door"):
                if pr.get("half") == "lower":
                    up = at(x, y + 1, z)
                    if up <= 1 or name[up] != nm or props[up].get("half") != "upper" or props[up].get("facing") != pr.get("facing") \
                            or props[up].get("hinge") != pr.get("hinge"):
                        bad(x, y, z, i, "kapinin ust yarisi eksik/uyumsuz")
                    dn = at(x, y - 1, z)
                    if not (face_ok(dn, "up") or grounded(dn, y - 1)):
                        bad(x, y, z, i, "kapinin altinda saglam zemin yok")
                else:
                    dn = at(x, y - 1, z)
                    if dn <= 1 or name[dn] != nm or props[dn].get("half") != "lower":
                        bad(x, y, z, i, "kapinin alt yarisi eksik")
                continue
            if nm.endswith("_bed"):
                fc = pr.get("facing", "north")
                d = VEC[fc]
                if pr.get("part") == "foot":
                    o = at(x + d[0], y, z + d[2])
                    if o <= 1 or name[o] != nm or props[o].get("part") != "head":
                        bad(x, y, z, i, "yatagin bas kismi eksik")
                else:
                    o = at(x - d[0], y, z - d[2])
                    if o <= 1 or name[o] != nm or props[o].get("part") != "foot":
                        bad(x, y, z, i, "yatagin ayak kismi eksik")
                continue
            if f & blockdb.FLUID and not (f & blockdb.WATERLOGGED):
                for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (0, -1, 0)):
                    j = at(x + dx, y + dy, z + dz)
                    if j == 1 or (j <= 0 and not grounded(j, y + dy)) or (j > 1 and is_air[j]):
                        bad(x, y, z, i, "sivi kapali hacimde degil (tasar)")
                        break
                continue
            if "half" in pr and pr.get("half") == "upper" and (f & blockdb.DOUBLE):
                dn = at(x, y - 1, z)
                if dn <= 1 or name[dn] != nm or props[dn].get("half") != "lower":
                    bad(x, y, z, i, "cift blogun alt yarisi eksik")
                continue
            if f & blockdb.SUPPORT_FLOOR:
                dn = at(x, y - 1, z)
                if f & blockdb.PLANT:
                    ok = (dn > 1 and name[dn] in _SOIL) or grounded(dn, y - 1)
                    if nm in ("lily_pad",):
                        ok = dn > 1 and name[dn] == "water"
                    if not ok:
                        bad(x, y, z, i, "bitkinin altinda toprak yok")
                elif nm.endswith("_carpet") or nm in ("moss_carpet", "pale_moss_carpet"):
                    if not (dn > 1 and not is_air[dn]) and not grounded(dn, y - 1):
                        bad(x, y, z, i, "halinin alti bos")
                else:
                    if not (face_ok(dn, "up") or (dn > 1 and is_post[dn]) or grounded(dn, y - 1)):
                        bad(x, y, z, i, "altinda tasiyici yok")
                if (f & blockdb.DOUBLE) and pr.get("half") == "lower":
                    up = at(x, y + 1, z)
                    if up <= 1 or name[up] != nm or props[up].get("half") != "upper":
                        bad(x, y, z, i, "cift blogun ust yarisi eksik")
                continue
            if f & blockdb.SUPPORT_CEIL:
                up = at(x, y + 1, z)
                if not (face_ok(up, "down") or (up > 1 and is_post[up])):
                    bad(x, y, z, i, "asili ama ustunde tasiyici yok")
                continue
            if f & blockdb.SUPPORT_WALL:
                fc = pr.get("facing")
                if fc in VEC and fc not in ("up", "down"):
                    d = VEC[fc]
                    j = at(x - d[0], y, z - d[2])
                    lenient = "banner" in nm or "sign" in nm
                    if not (face_ok(j, fc) or (lenient and j > 1 and (is_post[j] or sturdy[j]))):
                        bad(x, y, z, i, f"duvara asili ama arkasi ({OPP[fc]}) saglam degil")
                continue
            if f & blockdb.GRAVITY:
                dn = at(x, y - 1, z)
                if not ((dn > 1 and not is_air[dn]) or grounded(dn, y - 1)):
                    bad(x, y, z, i, "yercekimli blogun alti bos")
    return issues


# ====================================================================== YAPI / DUVAR
@part("plinth", "Kaide: duvar dibinde dışa taşan temel kuşağı, üstü eğimli merdiven 'su basman'ı (köşeler dış köşe).")
def plinth(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, h: int | None = None,
           role: str = "foundation", lip: bool = True):
    """Ayak izi (x0..x1, z0..z1) cevresine kaide: duvar hattinda h sira temel tasi, disinda (n=+1) h-1 sira dolu
    ve en ustte iceri bakan merdiven sirasi. y = ilk (en alt) sira."""
    st = _st(st)
    h = max(1, int(st.plinth if h is None else h))
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    for face, x, z, w in _sides(x0, z0, x1, z1):
        F = facade(b, face, x, y, z, w)
        F.sfill(st, role, 0, 0, 0, w - 1, h - 1, 0)
        if lip:
            if h > 1:
                F.sfill(st, role, -1, 0, 1, w, h - 2, 1)
            F.fill(-1, h - 1, 1, w, h - 1, 1, st.stairs(role, IN, "bottom"))
    if lip:
        # koseler: on yuzlerin dis kosesi (oyun merdiven kosesini kendisi kurar)
        for (cx, cz, fc) in ((x0 - 1, z0 - 1, "south"), (x1 + 1, z0 - 1, "south"), (x0 - 1, z1 + 1, "north"), (x1 + 1, z1 + 1, "north")):
            if h > 1:
                st.fill(b, cx, y, cz, cx, y + h - 2, cz, role)
            b.set(cx, y + h - 1, cz, st.stairs(role, fc, "bottom"))
    e = 1 if lip else 0
    return {"box": (x0 - e, y, z0 - e, x1 + e, y + h - 1, z1 + e)}


@part("wall", "Dokulu dolu duvar/kutu (rol varyantları yamalı karışır; tek tip düz duvar olmaz).")
def wall(b, x0, y0, z0, x1, y1, z1, st: Style | None = None, role: str = "wall"):
    st = _st(st)
    st.fill(b, x0, y0, z0, x1, y1, z1, role)
    return {"box": _box((x0, y0, z0), (x1, y1, z1))}


@part("floor_slab", "Kat döşemesi (doku/desenli), meta 'floors'a eklenir.")
def floor_slab(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, role: str = "floor",
               pattern: str | None = None):
    st = _st(st)
    if pattern:
        floor_pattern(b, x0, y, z0, x1, z1, st, kind=pattern)
    else:
        st.fill(b, x0, y, z0, x1, y, z1, role)
    _meta(b, "floors", {"y": y, "box": list(_box((x0, y, z0), (x1, y, z1)))})
    return {"box": _box((x0, y, z0), (x1, y, z1))}


@part("band", "Yatay kuşak/kordon: cephe boyunca blok, basamak, merdiven ya da kütük kiriş (kat çizgisi).")
def band(b, face: str, x: int, y: int, z: int, w: int, st: Style | None = None, role: str = "accent", kind: str = "ledge"):
    """kind: block (duvar hattinda vurgu sirasi), ledge (n=+1 ters merdiven cikinti + hatta vurgu), slab (n=+1 ust yarim
    basamak), beam (hatta yatay kutuk; rol 'beam' onerilir). (x,y,z) cephe hattinin en kucuk ucu, w uzunluk."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    if kind == "beam":
        F.fill(0, 0, 0, w - 1, 0, 0, _axis_log(st.block(role), "x"))
    elif kind in ("block", "ledge"):
        F.sfill(st, role, 0, 0, 0, w - 1, 0, 0)
    if kind == "ledge":
        F.fill(0, 0, 1, w - 1, 0, 1, st.stairs(role, IN, "top"))
    elif kind == "slab":
        F.fill(0, 0, 1, w - 1, 0, 1, st.slab(role, "top"))
    return {"box": F.box(0, 0, 0, w - 1, 0, 1 if kind in ("ledge", "slab") else 0)}


@part("cornice", "Korniş: duvar tepesinde dışa taşan bindirmeli silme (ters merdiven + basamak), 1-2 kademe.")
def cornice(b, face: str, x: int, y: int, z: int, w: int, st: Style | None = None, role: str = "trim", depth: int = 1,
            ends: bool = True):
    """(x,y,z) duvarin en ust sirasindaki en kucuk uc hucre. depth=2: iki kademeli (alt kademe y-1'de)."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    e = 1 if ends else 0
    if depth >= 2:
        F.fill(-e, -1, 1, w - 1 + e, -1, 1, st.stairs(role, IN, "top"))
        F.fill(-e, 0, 1, w - 1 + e, 0, 1, st.block(role))
        F.fill(-2 * e, 0, 2, w - 1 + 2 * e, 0, 2, st.stairs(role, IN, "top"))
        return {"box": F.box(-2 * e, -1, 0, w - 1 + 2 * e, 0, 2)}
    F.fill(-e, 0, 1, w - 1 + e, 0, 1, st.stairs(role, IN, "top"))
    return {"box": F.box(-e, 0, 1, w - 1 + e, 0, 1)}


@part("pilaster", "Pilastr: duvardan taşan dikme; tabanda ve başlıkta yana açılan merdiven profilli kaide/başlık.")
def pilaster(b, face: str, x: int, y: int, z: int, h: int, st: Style | None = None, w: int = 1, role: str = "pillar",
             flare: bool = True):
    """(x,y,z) pilastrin arkasindaki duvar hucresi (en alt); pilastr n=+1'de, w genislik, h yukseklik."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    F.sfill(st, "foundation", 0, 0, 1, w - 1, 0, 1)
    if h > 2:
        col = st.block(role)
        if "axis" in _db().props(col):
            F.fill(0, 1, 1, w - 1, h - 2, 1, _axis_log(col, "y"))
        else:
            F.sfill(st, role, 0, 1, 1, w - 1, h - 2, 1)
    F.fill(0, h - 1, 1, w - 1, h - 1, 1, st.block("detail") if st.base("detail") not in ("sea_lantern",) else st.block("trim"))
    if flare:
        F.set(-1, 0, 1, st.stairs("foundation", R, "bottom"))
        F.set(w, 0, 1, st.stairs("foundation", L, "bottom"))
        F.set(-1, h - 1, 1, st.stairs("trim", R, "top"))
        F.set(w, h - 1, 1, st.stairs("trim", L, "top"))
        F.fill(0, h - 1, 2, w - 1, h - 1, 2, st.stairs("trim", IN, "top"))
        return {"box": F.box(-1, 0, 1, w, h - 1, 2)}
    return {"box": F.box(0, 0, 1, w - 1, h - 1, 1)}


@part("pilasters", "Cephe boyunca ritmik pilastr dizisi (uçlar dahil, eşit aralık).")
def pilasters(b, face: str, x: int, y: int, z: int, length: int, h: int, st: Style | None = None, every: int | None = None,
              w: int = 1, role: str = "pillar"):
    st = _st(st)
    every = max(2, int(every or st.bay + 1))
    F = facade(b, face, x, y, z, length)
    n = max(1, round((length - w) / every))
    us = sorted({int(round(i * (length - w) / n)) for i in range(n + 1)})
    for u in us:
        X, Y, Z = F.xyz(u, 0, 0)
        if face == "south":
            X -= w - 1
        if face == "west":
            Z -= w - 1
        pilaster(b, face, X, Y, Z, h, st, w=w, role=role)
    return {"box": F.box(-1, 0, 0, length, h - 1, 2), "at": us}


@part("quoins", "Köşe taşları: köşede iki yüze dönüşümlü uzun/kısa vurgu taşları (isteğe bağlı 1 blok taşkın).")
def quoins(b, x: int, z: int, y0: int, y1: int, corner: str = "nw", st: Style | None = None, role: str = "accent",
           proud: bool = False):
    """(x,z) bina kosesindeki duvar hucresi; corner: nw/ne/sw/se (hangi kose -> yuzler disari bakar).
    Siralar donusumlu: bir sira x yuzunde 2, z yuzunde 1; sonraki tersi. proud=True: tas disa 1 tasar."""
    st = _st(st)
    sx = -1 if "w" in corner else 1
    sz = -1 if "n" in corner else 1
    ys = range(min(y0, y1), max(y0, y1) + 1)
    pts = []
    for y in ys:
        k = (y - y0) % 2
        cells = [(x, z), (x - sx, z) if k == 0 else (x, z - sz)]
        if k == 0:
            cells.append((x - 2 * sx, z))
        else:
            cells.append((x, z - 2 * sz))
        for (cx, cz) in cells:
            if proud:
                if cx == x:
                    cx2, cz2 = cx + sx, cz
                    b.set(cx2, y, cz2, st.pick(role, cx2, y, cz2))
                    pts.append((cx2, y, cz2))
                if cz == z:
                    cx2, cz2 = cx, cz + sz
                    b.set(cx2, y, cz2, st.pick(role, cx2, y, cz2))
                    pts.append((cx2, y, cz2))
            b.set(cx, y, cz, st.pick(role, cx, y, cz))
            pts.append((cx, y, cz))
        if proud:
            b.set(x + sx, y, z + sz, st.pick(role, x + sx, y, z + sz))
            pts.append((x + sx, y, z + sz))
    return {"box": _box(*pts)}


@part("column", "Sütun: kaide + gövde + başlık; slim (1x1, artı başlık), round (artı kesitli 3x3), square (3x3).")
def column(b, x: int, y: int, z: int, h: int, st: Style | None = None, kind: str = "slim", role: str = "pillar",
           base: bool = True, capital: bool = True):
    """(x,y,z) gövde merkezinin tabani; h toplam yukseklik (kaide ve baslik dahil)."""
    st = _st(st)
    h = max(3, int(h))
    shaft = st.block(role)
    if "axis" in _db().props(shaft):
        shaft = _axis_log(shaft, "y")
    fnd = "foundation"
    if kind == "slim":
        b.set(x, y, z, st.pick(fnd, x, y, z) if base else shaft)
        b.fill(x, y + 1, z, x, y + h - 2, z, shaft)
        b.set(x, y + h - 1, z, st.block("trim"))
        r = 1
        if base:
            for d in DIRS:
                dx, _, dz = VEC[d]
                b.set(x + dx, y, z + dz, st.stairs(fnd, OPP[d], "bottom"))
        if capital:
            for d in DIRS:
                dx, _, dz = VEC[d]
                b.set(x + dx, y + h - 1, z + dz, st.stairs("trim", OPP[d], "top"))
        return {"box": (x - r, y, z - r, x + r, y + h - 1, z + r)}
    if kind in ("round", "square"):
        plus = S.box(x - 1, 0, z - 1, x + 1, 0, z + 1)
        if kind == "round":
            plus = plus.where(lambda X, Y, Z: (np.abs(X - x) + np.abs(Z - z)) <= 1)
        for yy in range(y + 1, y + h - 1):
            plus.moved(0, yy, 0).put(b, shaft)
        # kaide: 3x3 tam + disinda merdiven halkasi
        st.fill(b, x - 1, y, z - 1, x + 1, y, z + 1, fnd)
        st.fill(b, x - 1, y + h - 1, z - 1, x + 1, y + h - 1, z + 1, "trim")
        for d in DIRS:
            dx, _, dz = VEC[d]
            px, pz = abs(dz), abs(dx)
            for k in (-1, 0, 1):
                cx, cz = x + 2 * dx + k * px, z + 2 * dz + k * pz
                if base:
                    b.set(cx, y, cz, st.stairs(fnd, OPP[d], "bottom"))
                if capital:
                    b.set(cx, y + h - 1, cz, st.stairs("trim", OPP[d], "top"))
        return {"box": (x - 2, y, z - 2, x + 2, y + h - 1, z + 2)}
    raise ValueError("kind: slim | round | square")


@part("beam", "Kiriş: eksenine göre döndürülmüş kütük (ya da tahta) çizgisi, iki nokta arası (eksene paralel).")
def beam(b, p0: Sequence[int], p1: Sequence[int], st: Style | None = None, role: str = "beam"):
    st = _st(st)
    (x0, y0, z0), (x1, y1, z1) = p0, p1
    d = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
    axis = "xyz"[int(np.argmax(d))]
    s = st.block(role)
    if "axis" in _db().props(s):
        s = _axis_log(s, axis)
    if sum(1 for v in d if v) <= 1:
        b.fill(x0, y0, z0, x1, y1, z1, s)
    else:
        b.line((x0, y0, z0), (x1, y1, z1), s)
    return {"box": _box(p0, p1)}


@part("timber_frame", "Ahşap karkas (bağdadi/fachwerk): dikmeler, yatay kirişler ve seyrek çapraz payandalar; dolgu sıva baskın kalır.")
def timber_frame(b, face: str, x: int, y0: int, z: int, length: int, y1: int, st: Style | None = None, spacing: int | None = None,
                 braces: str = "auto", role: str = "beam", proud: bool = False, skip: Iterable[tuple[int, int]] = ()):
    """Cephe duzleminde (x,y0,z en kucuk uc, length uzunluk) y0..y1 arasi karkas. braces: auto (genis bolmelerde
    donusumlu tek capraz, cok genislerde X) | diag | x | k | none. proud=True: ahsap 1 blok disa tasar.
    skip: [(u0,u1), ...] payanda konmayacak u araliklari (pencereler)."""
    st = _st(st)
    spacing = max(2, int(spacing or st.bay + 2))
    F = facade(b, face, x, y0, z, length)
    h = y1 - y0
    n = 1 if proud else 0
    logv = _axis_log(st.block(role), "y")
    logh = _axis_log(st.block(role), "x")
    nb = max(1, round((length - 1) / spacing))
    us = sorted({int(round(i * (length - 1) / nb)) for i in range(nb + 1)})
    F.fill(0, 0, n, length - 1, 0, n, logh)
    F.fill(0, h, n, length - 1, h, n, logh)
    for u in us:
        F.fill(u, 0, n, u, h, n, logv)
    skips = list(skip)
    if braces != "none" and h >= 3:
        diag = _axis_log(st.block(role), "x") if braces != "k" else st.block("frame")
        diag = st.block("frame")
        for bi, (a, c) in enumerate(zip(us[:-1], us[1:])):
            if any(not (c <= s0 or a >= s1) for s0, s1 in skips):
                continue
            bw = c - a - 1
            kind = braces
            if braces == "auto":
                kind = "none" if bw < 4 else ("x" if bw >= 7 else "diag")
            if kind == "none" or bw < 2:
                continue
            pts = []
            if kind in ("x", "diag"):
                flip = (bi % 2 == 1)
                for t in range(1, h):
                    f = (t - 0.5) / (h - 1)
                    u = int(round(f * (bw - 1)))
                    pts.append((c - 1 - u if flip else a + 1 + u, t))
                    if kind == "x":
                        pts.append((a + 1 + u if flip else c - 1 - u, t))
            elif kind == "k":
                k = min(bw // 2, h - 1, 2)
                for t in range(1, k + 1):
                    pts += [(a + t, t), (c - t, t)]
            for (u, v) in pts:
                F.set(u, v, n, diag)
    return {"box": F.box(0, 0, n, length - 1, h, n), "posts": us}


@part("buttress", "Payanda: dışa basamaklı kademelerle incelen taş destek (kademe üstleri eğimli merdiven).")
def buttress(b, face: str, x: int, y: int, z: int, h: int, st: Style | None = None, depth: int = 2, role: str = "foundation"):
    st = _st(st)
    F = facade(b, face, x, y, z, 1)
    seg = max(1, h // depth)
    for k in range(depth):
        top = h - 1 - k * seg - 1
        n = depth - k
        if top < 0:
            continue
        F.sfill(st, role, 0, 0, n, 0, top, n)
        F.set(0, top + 1, n, st.stairs(role, IN, "bottom"))
    return {"box": F.box(0, 0, 1, 0, h, depth)}


@part("crenellations", "Mazgallı siper: duvar halkasında dişli korkuluk (köşeler dolu), isteğe bağlı konsollu (taşkın).")
def crenellations(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, role: str = "wall",
                  corbels: bool = True, every: int = 2):
    """y = yuruyus yolunun bir ustu (siper ilk sirasi). corbels: siper 1 disa tasar, altinda ters merdiven konsollar."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    o = 1 if corbels else 0
    X0, Z0, X1, Z1 = x0 - o, z0 - o, x1 + o, z1 + o
    for face, x, z, w in _sides(X0, Z0, X1, Z1):
        F = facade(b, face, x, y, z, w)
        F.sfill(st, role, 0, 0, 0, w - 1, 0, 0)
        for u in range(w):
            if u == 0 or u == w - 1 or (u % every == 0):
                F.sset(st, role, u, 1, 0)
                if u not in (0, w - 1):
                    pass
        F.fill(0, 2, 0, 0, 2, 0, st.slab(role, "bottom"))
        F.fill(w - 1, 2, 0, w - 1, 2, 0, st.slab(role, "bottom"))
        if corbels:
            F.fill(1, -1, 0, w - 2, -1, 0, st.stairs(role, IN, "top"))
    return {"box": (X0, y - (1 if corbels else 0), Z0, X1, y + 2, Z1)}


@part("walls_box", "Dikdörtgen bina kabuğu: kat başına doku, köşe (taş/dikme/kütük/pilastr), kat kuşakları, kaide, korniş, döşemeler.")
def walls_box(b, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, st: Style | None = None, *, t: int | None = None,
              floors: Sequence[int] | None = None, roles: Sequence[str] | None = None, corner: str | None = "style",
              plinth_h: int | None = None, belts: bool = True, cornice_top: bool = True, slabs: bool = True,
              jetty: bool | None = None):
    """Dis duvarlar x0..x1, z0..z1 (dis yuzler), y0 (zemin kat dosemesi) .. y1 (duvarin en ust sirasi).
    floors: kat doseme seviyeleri (varsayilan y0, y0+floor_h, ...). roles: kat basina duvar rolu.
    jetty: ust katlar 1 blok disa tasar (ortacag); varsayilan stil motifinden. Donus: floors, rooms (ic kutular)."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    t = max(1, int(t or st.wall_t))
    if floors is None:
        floors = list(range(y0, y1, st.floor_h)) or [y0]
    floors = sorted(floors)
    nfl = len(floors)
    timber = st.has("upper_timber") or st.has("timber")
    if roles is None:
        roles = ["wall"] + [("wall2" if st.has("upper_timber") else "wall")] * (nfl - 1)
    roles = list(roles) + [roles[-1]] * (nfl - len(roles))
    if jetty is None:
        jetty = st.has("jetty") and nfl > 1
    if corner == "style":
        corner = st.corner
    ph = st.plinth if plinth_h is None else plinth_h
    rooms = []
    ext = 0
    for i, fy in enumerate(floors):
        top = (floors[i + 1] - 1) if i + 1 < nfl else y1
        e = 1 if (jetty and i > 0) else 0
        ext = max(ext, e)
        X0, Z0, X1, Z1 = x0 - e, z0 - e, x1 + e, z1 + e
        shell = S.shell_box(X0, fy, Z0, X1, top, Z1, t=t, top=False, bottom=False)
        shell.put_style(b, st, roles[i])
        up_timber = timber and roles[i] == "wall2"
        # koseler
        for (cx, cz, cn) in ((X0, Z0, "nw"), (X1, Z0, "ne"), (X0, Z1, "sw"), (X1, Z1, "se")):
            if up_timber:
                b.fill(cx, fy, cz, cx, top, cz, _axis_log(st.block("beam"), "y"))
            elif corner == "quoins":
                quoins(b, cx, cz, fy, top, cn, st)
            elif corner in ("pillar", "log"):
                col = st.block("pillar")
                b.fill(cx, fy, cz, cx, top, cz, _axis_log(col, "y") if "axis" in _db().props(col) else col)
            elif corner == "pilaster":
                for face, fx, fz in (("north" if "n" in cn else "south", cx, cz), ("west" if "w" in cn else "east", cx, cz)):
                    F = Frame(b, face, (fx, fy, fz))
                    F.sfill(st, "pillar", 0, 0, 1, 0, top - fy, 1)
                    F.fill(0, top - fy, 2, 0, top - fy, 2, st.stairs("trim", IN, "top"))
                sx = -1 if "w" in cn else 1
                sz = -1 if "n" in cn else 1
                st.fill(b, cx + sx, fy, cz + sz, cx + sx, top, cz + sz, "pillar")
        if up_timber:
            # ust kat ahsap karkas: alt/ust kiris, seyrek dikmeler; payanda yalniz 'timber' motifinde
            dense = st.has("timber")
            for face, fx, fz, w in _sides(X0, Z0, X1, Z1):
                timber_frame(b, face, fx, fy, fz, w, top, st, spacing=(st.bay + 2) if dense else (2 * st.bay + 3),
                             braces="auto" if dense else "none")
        # kat kusagi
        if i > 0 and belts:
            for face, fx, fz, w in _sides(X0, Z0, X1, Z1):
                if jetty:
                    Fp = facade(b, face, fx, fy - 1, fz, w)
                    Fp.fill(1, 0, 0, w - 2, 0, 0, st.stairs("trim", IN, "top"))
                    # konsollar (eli bogrunde): aralikli ikinci kademe
                    step = st.bay + 1
                    for u in range(1, w - 1):
                        if u == 1 or u == w - 2 or (u - 1) % step == 0:
                            Fp.set(u, -1, 0, st.stairs("trim", IN, "top"))
                elif up_timber:
                    pass
                else:
                    band(b, face, fx, fy, fz, w, st, role="accent", kind="ledge")
        if slabs:
            st.fill(b, X0 + t, fy, Z0 + t, X1 - t, fy, Z1 - t, "floor")
            _meta(b, "floors", {"y": fy, "box": [X0 + t, fy, Z0 + t, X1 - t, fy, Z1 - t]})
        room = [X0 + t, fy + 1, Z0 + t, X1 - t, top, Z1 - t]
        rooms.append(room)
        _meta(b, "rooms", {"name": f"kat{i}", "box": room})
    if ph and ph > 0:
        plinth(b, x0, z0, x1, z1, y0, st, h=ph)
    if cornice_top:
        e = 1 if (jetty and nfl > 1) else 0
        for face, fx, fz, w in _sides(x0 - e, z0 - e, x1 + e, z1 + e):
            cornice(b, face, fx, y1, fz, w, st)
    pe = 1 if (ph and ph > 0) else 0
    co = 1 if cornice_top else 0
    m = max(pe, co + ext, ext)
    return {"box": (x0 - m, y0, z0 - m, x1 + m, y1, z1 + m), "floors": floors, "rooms": rooms, "t": t,
            "outer": (x0 - ext, z0 - ext, x1 + ext, z1 + ext)}


# ====================================================================== PENCERELER
def _arch_ring(prof: np.ndarray):
    """Kemer profili [v,u] icin: cevre halkasi (8-komsuluk, alt sira haric), ic kose (merdiven) hucreleri, kilit tasi.
    Koordinatlar profilinkiyle ayni (u=0 acikligin ilk sutunu)."""
    hv, wu = prof.shape
    P = np.zeros((hv + 2, wu + 2), dtype=bool)
    P[1:-1, 1:-1] = prof
    D = P.copy()
    for dv in (-1, 0, 1):
        for du in (-1, 0, 1):
            if dv == 0 and du == 0:
                continue
            D |= np.roll(np.roll(P, dv, axis=0), du, axis=1)
    ring = D & ~P
    ring[0, :] = False  # esik sirasi ayri ele alinir
    cen = (wu + 1) / 2.0
    corners = []
    for vv in range(1, hv + 2):
        for uu in range(0, wu + 2):
            if not ring[vv, uu] or not P[vv - 1, uu]:
                continue
            if abs(uu - cen) < 1e-9:
                continue
            side = 1 if uu < cen else -1
            if 0 <= uu + side < wu + 2 and P[vv, uu + side]:
                corners.append((uu - 1, vv - 1, "west" if side == 1 else "east"))
    top_v = int(np.nonzero(prof.any(axis=1))[0].max())
    top_us = np.nonzero(prof[top_v])[0]
    key = (int(top_us[len(top_us) // 2]) if len(top_us) % 2 == 1 else None, top_v + 1)
    rv, ru = np.nonzero(ring)
    cells = [(int(u) - 1, int(v) - 1) for v, u in zip(rv, ru)]
    return cells, corners, key


def _glass(st: Style, glass: str | None) -> str:
    if glass == "block":
        return st.block("glass_block")
    if glass:
        return glass
    return st.pane()


@part("window", "Pencere: framed (söve+denizlik+alın), shutters (kepenk+çiçeklik), arched (kemerli, kilit taşı), kafes (Osmanlı kafesli), shoji, ribbon (bant cam), modern (kutu çerçeve), gothic, slit (mazgal).")
def window(b, x: int, y: int, z: int, face: str = "north", w: int | None = None, h: int | None = None, st: Style | None = None,
           kind: str | None = None, depth: int | None = None, glass: str | None = None, sill: bool = True,
           flowers: bool | None = None, arch: str | None = None, ablaq: bool | None = None):
    """(x,y,z) acikligin en kucuk koordinatli alt hucresi (duvar duzleminde); genislik w (+x ya da +z), yukseklik h.
    depth = duvar kalinligi (acikligin kesildigi derinlik; varsayilan stil wall_t). Dis ogeler n=+1 (bazen +2)."""
    st = _st(st)
    w = int(w or st.win_w)
    h = int(h or st.win_h)
    kind = kind or st.window_kind
    depth = max(1, int(depth or st.wall_t))
    F = facade(b, face, x, y, z, w)
    gl = _glass(st, glass)
    gn = -(depth - 1) if depth >= 2 else 0
    fr = "frame"
    lo_u, hi_u, lo_v, hi_v, hi_n = -1, w, -1, h, 1

    def opening(prof=None):
        if prof is None:
            F.clear(0, 0, gn, w - 1, h - 1, 0)
            F.fill(0, 0, gn, w - 1, h - 1, gn, gl)
        else:
            vs, us = np.nonzero(prof)
            for v, u in zip(vs.tolist(), us.tolist()):
                for n in range(gn, 1):
                    F.set(u, v, n, AIR)
                F.set(u, v, gn, gl)

    def jambs(role=fr, n=0, top=True, bottom=False):
        F.sfill(st, role, -1, 0, n, -1, h - 1, n)
        F.sfill(st, role, w, 0, n, w, h - 1, n)
        if top:
            F.sfill(st, role, -1, h, n, w, h, n)
        if bottom:
            F.sfill(st, role, -1, -1, n, w, -1, n)

    def stair_sill(role="trim"):
        F.fill(-1, -1, 1, w, -1, 1, st.stairs(role, IN, "top"))

    if kind in ("framed", "shutters"):
        opening()
        jambs(bottom=True)
        if sill:
            stair_sill()
        F.fill(-1, h, 1, w, h, 1, st.stairs("trim", IN, "bottom"))
        if kind == "shutters":
            for v in range(h):
                half = "bottom" if v < (h + 1) // 2 else "top"
                F.set(-1, v, 1, st.trapdoor(OUT, half, True))
                F.set(w, v, 1, st.trapdoor(OUT, half, True))
            if flowers is None:
                flowers = st.has("flower_boxes")
            if flowers:
                X, Y, Z = F.xyz(0, -1, 0)
                if face == "south":
                    X -= w - 1
                if face == "west":
                    Z -= w - 1
                flower_box(b, X, Y, Z, face, w, st)
                hi_n = 2
                lo_v = -2
    elif kind in ("arched", "gothic"):
        ak = arch or ("pointed" if kind == "gothic" else st.arch_kind)
        if ak == "flat":
            ak = "round"
        prof = S.arch_profile(w, h, ak)
        opening(prof)
        cells, corners, key = _arch_ring(prof)
        if ablaq is None:
            ablaq = st.has("almasik")
        spring = int(np.argmin(prof.all(axis=1))) if not prof.all() else h
        for (u, v) in cells:
            role = fr
            if ablaq and v >= spring:
                role = "accent" if (u + v) % 2 == 0 else fr
            F.sset(st, role, u, v, 0)
        for (u, v, d) in corners:
            F.set(u, v, 0, st.stairs(fr, d, "top"))
        if key[0] is not None and h >= 3:
            F.set(key[0], key[1], 0, st.block("detail"))
        F.sfill(st, fr, -1, -1, 0, w, -1, 0)
        if sill:
            stair_sill()
        hi_v = max(hi_v, max(v for _, v in cells))
    elif kind == "kafes":
        opening()
        jambs(bottom=True)
        if sill:
            stair_sill("frame")
        lat = st.form("frame", "trapdoor", facing=OUT, half="bottom", open=True)
        kh = max(1, h // 2)
        F.fill(0, 0, 1, w - 1, kh - 1, 1, lat)
        F.fill(-1, h, 1, w, h, 1, st.slab("frame", "top"))
    elif kind == "shoji":
        opening()
        jambs(bottom=True)
        if h >= 3:
            F.sfill(st, "wall2", 0, 0, gn, w - 1, 0, gn)
        F.fill(-1, h, 1, w, h, 1, st.slab("roof", "bottom"))
    elif kind == "ribbon":
        opening()
        jambs(bottom=True)
        for u in range(3, w - 1, 3):
            F.sfill(st, fr, u, 0, gn, u, h - 1, gn)
        F.fill(-1, h, 1, w, h, 2, st.slab("trim", "top"))
        F.fill(-1, -1, 1, w, -1, 1, st.slab(fr, "top"))
        hi_n = 2
    elif kind == "modern":
        opening()
        F.sfill(st, fr, -1, -1, 1, w, -1, 1)
        F.sfill(st, fr, -1, h, 1, w, h, 1)
        F.sfill(st, fr, -1, 0, 1, -1, h - 1, 1)
        F.sfill(st, fr, w, 0, 1, w, h - 1, 1)
    elif kind == "slit":
        F.clear(0, 0, gn, w - 1, h - 1, 0)
        if h >= 3:
            F.clear(-1, h // 2, 0, w, h // 2, 0)
        lo_u, hi_u, lo_v, hi_v, hi_n = -1, w, 0, h - 1, 0
    else:
        raise ValueError("kind: framed|shutters|arched|gothic|kafes|shoji|ribbon|modern|slit")
    bx = F.box(0, 0, gn, w - 1, h - 1, 0)
    _meta(b, "windows", {"box": list(bx), "face": face, "kind": kind})
    return {"box": F.box(lo_u, lo_v, min(gn, 0), hi_u, hi_v, hi_n), "opening": bx}


@part("flower_box", "Pencere altı çiçeklik: konsol üstünde toprak, çiçekler ve tuzak kapı kenarlar.")
def flower_box(b, x: int, y: int, z: int, face: str = "north", w: int = 1, st: Style | None = None, seed: int = 0):
    """(x,y,z) duvar duzleminde kutu hizasindaki en kucuk hucre (genelde pencere esiginin bir alti); kutu n=+1'de."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    soil = st.block("soil") if st.base("soil") in ("grass_block", "moss_block", "rooted_dirt", "coarse_dirt", "dirt") else "minecraft:rooted_dirt"
    F.fill(0, 0, 1, w - 1, 0, 1, soil)
    F.fill(0, -1, 1, w - 1, -1, 1, st.stairs("trim", IN, "top"))
    F.fill(0, 0, 2, w - 1, 0, 2, st.trapdoor(OUT, "bottom", True))
    F.set(-1, 0, 1, st.trapdoor(L, "bottom", True))
    F.set(w, 0, 1, st.trapdoor(R, "bottom", True))
    for u in range(w):
        X, Y, Z = F.xyz(u, 1, 1)
        F.set(u, 1, 1, st.pick("plants", X + seed, Y, Z))
    return {"box": F.box(-1, -1, 1, w, 1, 2)}


@part("window_row", "Cephe boyunca ritmik pencere dizisi (eşit aralık, ortalanmış, kapı aralığından kaçınır).")
def window_row(b, x: int, y: int, z: int, face: str, length: int, st: Style | None = None, w: int | None = None,
               h: int | None = None, kind: str | None = None, every: int | None = None, margin: int = 2,
               avoid: Iterable[tuple[int, int]] = (), **kw):
    """(x,y,z) cephe hattinin en kucuk ucu (pencere alt sirasi y); avoid: [(a0,a1)] eksen koordinati (x ya da z)
    araliklari (kapi vb.). Donus: 'at' = yerlestirilen pencerelerin en kucuk koseleri."""
    st = _st(st)
    w = int(w or st.win_w)
    every = int(every or (st.bay + (w - 1)))
    every = max(w + 1, every)
    Lu = length - 2 * margin
    if Lu < w:
        return {"box": (x, y, z, x, y, z), "at": []}
    n = (Lu - w) // every + 1
    span = (n - 1) * every + w
    start = margin + (Lu - span) // 2
    along_x = face in ("north", "south")
    out = []
    av = list(avoid)
    boxes = []
    for i in range(n):
        a = (x if along_x else z) + start + i * every
        if any(not (a + w - 1 < a0 - 1 or a > a1 + 1) for a0, a1 in av):
            continue
        X, Z = (a, z) if along_x else (x, a)
        r = window(b, X, y, Z, face, w, h, st, kind=kind, **kw)
        out.append((X, y, Z))
        boxes.append(r["box"])
    if not boxes:
        return {"box": (x, y, z, x, y, z), "at": []}
    bx = _box(*[(q[0], q[1], q[2]) for q in boxes], *[(q[3], q[4], q[5]) for q in boxes])
    return {"box": bx, "at": out}


@part("oculus", "Yuvarlak pencere (oculus/göz): çember çerçeve, içi cam; alınlık, kubbe kasnağı, kalkan duvarı için.")
def oculus(b, x: int, y: int, z: int, face: str = "north", r: int = 1, st: Style | None = None, glass: str | None = None,
           depth: int | None = None):
    """(x,y,z) dairenin merkez hucresi (duvar duzleminde); r yaricap (1 = arti bicimli cam, 2 = 5x5 yuvarlak)."""
    st = _st(st)
    F = Frame(b, face, (x, y, z))
    gl = _glass(st, glass)
    depth = max(1, int(depth or st.wall_t))
    gn = -(depth - 1) if depth >= 2 else 0
    R = r + 1
    inner = r * r + r - (1 if r == 1 else 0)
    outer = R * R + R
    for u in range(-R, R + 1):
        for v in range(-R, R + 1):
            d2 = u * u + v * v
            if d2 <= inner:
                for n in range(gn, 1):
                    F.set(u, v, n, AIR)
                F.set(u, v, gn, gl)
            elif d2 <= outer:
                F.sset(st, "frame", u, v, 0)
    _meta(b, "windows", {"box": list(F.box(-r, -r, gn, r, r, 0)), "face": face, "kind": "oculus"})
    return {"box": F.box(-R, -R, gn, R, R, 0)}


@part("bay_window", "Çıkma pencere (bay): konsollar üstünde öne taşan camlı kutu, köşe dikmeleri, üstünde küçük eğimli çatı.")
def bay_window(b, x: int, y: int, z: int, face: str = "north", w: int = 3, h: int = 2, depth: int = 1, st: Style | None = None):
    """(x,y,z) duvardaki acikligin en kucuk alt hucresi. Kutu n=+1..depth, u=0..w-1; on ve yanlar cam."""
    st = _st(st)
    w = max(3, int(w))
    F = facade(b, face, x, y, z, w)
    gl = st.pane()
    F.clear(0, 0, 0, w - 1, h - 1, 0)
    F.sfill(st, "trim", 0, -1, 1, w - 1, -1, depth)
    F.fill(0, -2, 1, w - 1, -2, 1, st.stairs("trim", IN, "top"))
    if depth >= 2:
        F.fill(0, -1, depth, w - 1, -1, depth, st.stairs("trim", IN, "top"))
    for n in range(1, depth + 1):
        F.sfill(st, "frame", 0, 0, n, 0, h - 1, n)
        F.sfill(st, "frame", w - 1, 0, n, w - 1, h - 1, n)
        if n < depth and h >= 2:
            F.fill(0, 0, n, 0, h - 1, n, gl)
            F.fill(w - 1, 0, n, w - 1, h - 1, n, gl)
    F.fill(1, 0, depth, w - 2, h - 1, depth, gl)
    F.sfill(st, "trim", 0, h, 1, w - 1, h, depth)
    F.fill(-1, h, depth + 1, w, h, depth + 1, st.stairs("roof", IN, "bottom"))
    F.fill(0, h + 1, 1, w - 1, h + 1, depth, st.stairs("roof", IN, "bottom"))
    F.fill(-1, h, 1, -1, h, depth, st.stairs("roof", R, "bottom"))
    F.fill(w, h, 1, w, h, depth, st.stairs("roof", L, "bottom"))
    _meta(b, "windows", {"box": list(F.box(0, 0, 1, w - 1, h - 1, depth)), "face": face, "kind": "bay"})
    return {"box": F.box(-1, -2, 0, w, h + 1, depth + 1)}


@part("cumba", "Osmanlı cumbası: üst katta konsollu (eli böğründe) çıkma, sık dikmeli uzun pencereler, kafes, saçaklı başlık.")
def cumba(b, x: int, y: int, z: int, face: str = "north", w: int = 5, h: int = 3, depth: int = 2, st: Style | None = None,
          roof: bool = True):
    """(x,y,z) cumbanin duvar duzlemindeki en kucuk alt hucresi (ust kat dosemesi + 1 = pencere alt sirasi).
    Cumba n=+1..depth tasar, u=0..w-1; y-1'de doseme, altinda konsollar; h pencere yuksekligi."""
    st = _st(st)
    w = max(3, int(w))
    depth = max(1, int(depth))
    F = facade(b, face, x, y, z, w)
    gl = st.pane()
    F.clear(1, 0, 0, w - 2, h - 1, 0)
    # doseme + kademeli konsollar (eli bogrunde)
    F.sfill(st, "floor", 0, -1, 1, w - 1, -1, depth - 1)
    F.fill(0, -1, depth, w - 1, -1, depth, st.stairs("trim", IN, "top"))
    for u in sorted({0, w - 1, *range(2, w - 2, 2)}):
        for n in range(1, depth + 1):
            F.set(u, -1 - (depth - n) - 1, n, st.stairs("trim", IN, "top"))
            for vv in range(-1 - (depth - n), -1):
                F.set(u, vv, n, st.block("trim"))
    # yan duvarlar, on yuz dikmeleri ve uzun pencereler
    logv = _axis_log(st.block("beam"), "y")
    for n in range(1, depth + 1):
        F.sfill(st, "wall2", 0, 0, n, 0, h - 1, n)
        F.sfill(st, "wall2", w - 1, 0, n, w - 1, h - 1, n)
    F.fill(0, 0, depth, 0, h - 1, depth, logv)
    F.fill(w - 1, 0, depth, w - 1, h - 1, depth, logv)
    for u in range(1, w - 1):
        if w >= 6 and u % 2 == 0 and u != w - 2:
            F.fill(u, 0, depth, u, h - 1, depth, st.block("frame"))
        else:
            F.fill(u, 0, depth, u, h - 1, depth, gl)
            if st.has("kafes") and h >= 3:
                F.set(u, 0, depth + 1, st.form("frame", "trapdoor", facing=OUT, half="bottom", open=True))
    if depth >= 2 and h >= 3:
        F.fill(0, 1, 1, 0, h - 2, depth - 1, gl)
        F.fill(w - 1, 1, 1, w - 1, h - 2, depth - 1, gl)
    F.fill(0, h, 1, w - 1, h, depth, _axis_log(st.block("beam"), "x"))
    top = h
    if roof:
        F.fill(-1, h, depth + 1, w, h, depth + 1, st.stairs("roof", IN, "bottom"))
        F.fill(-1, h + 1, 1, w, h + 1, depth, st.stairs("roof", IN, "bottom"))
        F.fill(-1, h, 1, -1, h, depth, st.stairs("roof", R, "bottom"))
        F.fill(w, h, 1, w, h, depth, st.stairs("roof", L, "bottom"))
        top = h + 1
    _meta(b, "windows", {"box": list(F.box(1, 0, depth, w - 2, h - 1, depth)), "face": face, "kind": "cumba"})
    _meta(b, "rooms", {"name": "cumba", "box": list(F.box(1, 0, 0, w - 2, h - 1, depth - 1))})
    return {"box": F.box(-1, -1 - depth, 0, w, top, depth + 1)}


# ====================================================================== KAPILAR / GIRISLER
def _place_door(F: Frame, st: Style, u0: int, w: int, n: int = 0) -> None:
    if w == 1:
        F.set(u0, 0, n, st.door(IN, "lower", "left"))
        F.set(u0, 1, n, st.door(IN, "upper", "left"))
    else:
        for k, hinge in ((0, "right"), (1, "left")):
            F.set(u0 + k, 0, n, st.door(IN, "lower", hinge))
            F.set(u0 + k, 1, n, st.door(IN, "upper", hinge))


@part("door", "Kapı: framed (söve, lento, saçak), modern (cam yan ışık, kanopi), arched (kemerli, kilit taşı, tepe camı); tek/çift kanat.")
def door(b, x: int, y: int, z: int, face: str = "north", st: Style | None = None, w: int = 1, kind: str | None = None,
         h: int | None = None, depth: int | None = None, steps: int = 0):
    """(x,y,z) kapinin alt hucresi (en kucuk koordinat; cift kanatta ikisinin kucugu), duvar duzleminde; y = doseme + 1.
    Kapi 'facing' = iceri (KIT_DEV kurali: on kapi facing=south). h toplam aciklik (2 = kapi, 3+ = tepe cami)."""
    st = _st(st)
    kind = kind or st.door_kind
    if kind == "portico":
        return portico(b, x, y, z, face, w=w, st=st)
    w = 2 if w >= 2 else 1
    h = int(h or (3 if (w == 2 or kind == "arched") else 2))
    depth = max(1, int(depth or st.wall_t))
    F = facade(b, face, x, y, z, w)
    F.clear(0, 0, -(depth - 1), w - 1, h - 1, 0)
    lo_u, hi_u, hi_v, hi_n = -1, w, h, 1
    if kind == "arched":
        ak = st.arch_kind if st.arch_kind != "flat" else "round"
        prof = S.arch_profile(w, h, ak) if w > 1 else np.ones((h, 1), dtype=bool)
        cells, corners, key = _arch_ring(prof)
        for (u, v) in cells:
            role = "frame"
            if st.has("almasik") and v >= 2:
                role = "accent" if (u + v) % 2 == 0 else "frame"
            F.sset(st, role, u, v, 0)
        for (u, v, d) in corners:
            F.set(u, v, 0, st.stairs("frame", d, "top"))
        if key[0] is not None:
            F.set(key[0], key[1], 0, st.block("detail"))
        vs, us = np.nonzero(prof)
        for v, u in zip(vs.tolist(), us.tolist()):
            if v >= 2:
                F.set(u, v, 0, st.pane())
        hi_v = max(v for _, v in cells)
    else:
        F.sfill(st, "frame", -1, 0, 0, -1, h - 1, 0)
        F.sfill(st, "frame", w, 0, 0, w, h - 1, 0)
        F.sfill(st, "frame", -1, h, 0, w, h, 0)
        if h >= 3:
            F.fill(0, 2, 0, w - 1, h - 1, 0, st.pane())
        if kind == "modern":
            F.fill(w, 0, 0, w, h - 1, 0, st.block("glass_block"))
            F.sfill(st, "frame", w + 1, 0, 0, w + 1, h, 0)
            F.fill(-1, h, 1, w + 1, h, 2, st.slab("trim", "top"))
            hi_u, hi_n = w + 1, 2
        else:
            F.fill(-1, h, 1, w, h, 1, st.stairs("trim", IN, "bottom"))
            F.set(-1, h - 1, 1, st.stairs("trim", IN, "top"))
            F.set(w, h - 1, 1, st.stairs("trim", IN, "top"))
    _place_door(F, st, 0, w)
    # kapinin onu 2 blok bos olmali: onceden konmus konsol/kusak/cikma altligi kapi hizasindan kalkar
    for u in range(w):
        for v in (0, 1):
            X, Y, Z = F.xyz(u, v, 1)
            if b.get_id(X, Y, Z) > 1 and not str(b.get(X, Y, Z)).split("[")[0].endswith("_door"):
                b.set(X, Y, Z, AIR)
    if not b.is_solid(*F.xyz(0, -1, 0)) or not b.is_solid(*F.xyz(w - 1, -1, 0)):
        F.sfill(st, "foundation", 0, -1, 0, w - 1, -1, 0)
    lo_v = -1
    ex = 0
    if steps > 0:
        X, Y, Z = F.xyz(0, 0, 0)
        if face == "south":
            X -= w - 1
        if face == "west":
            Z -= w - 1
        entrance_steps(b, X, Y, Z, face, w, steps, st)
        lo_v = -steps
        hi_n = max(hi_n, steps)
        ex = 1
    _meta(b, "doors", {"pos": list(F.xyz(0, 0, 0)), "facing": F.dir(IN), "w": w, "face": face, "kind": kind})
    return {"box": F.box(lo_u - ex, lo_v, -(depth - 1), hi_u + ex, hi_v, hi_n)}


@part("entrance_steps", "Giriş basamakları: kapı eşiğinden dışa inen merdiven, dolu altlı, iki yanda yanak duvarı.")
def entrance_steps(b, x: int, y: int, z: int, face: str = "north", w: int = 1, n: int = 1, st: Style | None = None,
                   role: str = "foundation"):
    """(x,y,z) kapinin alt hucresi (y = icerdeki doseme + 1). n basamak disa ve asagi iner; dis zemin y-n-1 seviyesinde."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    for k in range(1, n + 1):
        F.fill(0, -k, k, w - 1, -k, k, st.stairs(role, IN, "bottom"))
        if k < n:
            F.sfill(st, role, 0, -n, k, w - 1, -k - 1, k)
        F.sfill(st, role, -1, -n, k, -1, -k, k)
        F.sfill(st, role, w, -n, k, w, -k, k)
        F.set(-1, -k + 1, k, st.stairs("trim", IN, "bottom")) if k > 1 else F.set(-1, 0, k, st.slab("trim", "bottom"))
        F.set(w, -k + 1, k, st.stairs("trim", IN, "bottom")) if k > 1 else F.set(w, 0, k, st.slab("trim", "bottom"))
    return {"box": F.box(-1, -n, 1, w, 0, n)}


@part("portico", "Revaklı giriş (portik): sütunlar, arşitrav, üçgen alınlık ya da düz kanopi, platform ve basamak.")
def portico(b, x: int, y: int, z: int, face: str = "north", w: int = 2, depth: int = 3, st: Style | None = None,
            pediment: bool | None = None, steps: int = 1, col_h: int | None = None):
    """(x,y,z) kapinin alt hucresi (duvar duzleminde, y = doseme + 1). Portik n=+1..depth, u=-2..w+1; sutunlar on kosede.
    Platform y-1'de (ic dosemeyle ayni), steps basamakla dis zemine iner."""
    st = _st(st)
    w = 2 if w >= 2 else 1
    F = facade(b, face, x, y, z, w)
    if pediment is None:
        pediment = st.has("pediment") or st.has("columns")
    ch = int(col_h or 4)
    U0, U1 = -2, w + 1
    X, Y, Z = F.xyz(0, 0, 0)
    if face == "south":
        X -= w - 1
    if face == "west":
        Z -= w - 1
    door(b, X, Y, Z, face, st, w=w, kind="framed", h=3)
    F.sfill(st, "foundation", U0, -1, 1, U1, -1, depth)
    for k in range(1, steps + 1):
        F.fill(U0, -1 - k, depth + k, U1, -1 - k, depth + k, st.stairs("foundation", IN, "bottom"))
        if k < steps:
            F.sfill(st, "foundation", U0, -1 - steps, depth + k, U1, -2 - k, depth + k)
    for u in (U0, U1):
        cx, cy, cz = F.xyz(u, 0, depth)
        column(b, cx, cy, cz, ch, st, kind="slim")
    F.sfill(st, "trim", U0, ch, 1, U1, ch, depth)
    F.fill(U0 - 1, ch, depth + 1, U1 + 1, ch, depth + 1, st.stairs("trim", IN, "top"))
    F.fill(U0 - 1, ch, 1, U0 - 1, ch, depth, st.stairs("trim", R, "top"))
    F.fill(U1 + 1, ch, 1, U1 + 1, ch, depth, st.stairs("trim", L, "top"))
    top = ch
    if pediment:
        ua, ub, v = U0 - 1, U1 + 1, ch + 1
        while ua <= ub:
            if ua == ub:
                F.fill(ua, v, 1, ua, v, depth + 1, st.slab("roof_trim", "bottom"))
            else:
                F.fill(ua, v, 1, ua, v, depth + 1, st.stairs("roof", R, "bottom"))
                F.fill(ub, v, 1, ub, v, depth + 1, st.stairs("roof", L, "bottom"))
                if ub - ua >= 2:
                    F.sfill(st, "trim", ua + 1, v, depth + 1, ub - 1, v, depth + 1)
                    F.sfill(st, "wall", ua + 1, v, 1, ub - 1, v, depth)
            top = v
            ua, ub, v = ua + 1, ub - 1, v + 1
    else:
        F.fill(U0 - 1, ch + 1, 1, U1 + 1, ch + 1, depth + 1, st.slab("roof_trim", "bottom"))
        top = ch + 1
    return {"box": F.box(U0 - 1, -1 - steps, -(st.wall_t - 1), U1 + 1, top, depth + steps + 1)}


@part("arched_gate", "Kemerli kapı/geçit: kalın duvarda kemer, alternatif renkli kemer taşları (ablak), kilit taşı, isteğe bağlı kanat.")
def arched_gate(b, x: int, y: int, z: int, face: str = "north", w: int = 3, h: int = 5, st: Style | None = None,
                depth: int = 2, arch: str | None = None, ablaq: bool = True, gate: str | None = None,
                frame_role: str = "foundation"):
    """(x,y,z) acikligin en kucuk alt hucresi; aciklik n=-(depth-1)..0 boyunca kesilir; on yuzde 1 tasan
    soveler ve kilit tasi. gate: None | 'fence_gate' | 'door' (alt siraya kanatlar; door yalniz w<=2)."""
    st = _st(st)
    ak = arch or (st.arch_kind if st.arch_kind != "flat" else "round")
    prof = S.arch_profile(w, h, ak)
    F = facade(b, face, x, y, z, w)
    vs, us = np.nonzero(prof)
    for v, u in zip(vs.tolist(), us.tolist()):
        F.clear(u, v, -(depth - 1), u, v, 0)
    cells, corners, key = _arch_ring(prof)
    spring = int(np.argmin(prof.all(axis=1))) if not prof.all() else h
    for n in range(-(depth - 1), 1):
        for (u, v) in cells:
            role = frame_role
            if ablaq and v >= spring and n == 0:
                role = "accent" if (u + v) % 2 == 0 else frame_role
            F.sset(st, role, u, v, n)
        for (u, v, d) in corners:
            F.set(u, v, n, st.stairs(frame_role, d, "top"))
    top = max(v for _, v in cells)
    if key[0] is not None:
        F.set(key[0], key[1], 0, st.block("detail"))
        F.set(key[0], key[1], 1, st.stairs("trim", IN, "top"))
        top = max(top, key[1])
    F.sfill(st, "foundation", -1, 0, 1, -1, spring - 1, 1)
    F.sfill(st, "foundation", w, 0, 1, w, spring - 1, 1)
    F.set(-1, spring, 1, st.stairs("trim", IN, "top"))
    F.set(w, spring, 1, st.stairs("trim", IN, "top"))
    if gate == "fence_gate":
        for u in range(w):
            F.set(u, 0, 0, st.gate("fence", IN, False))
    elif gate == "door" and w <= 2:
        _place_door(F, st, 0, w)
    if gate:
        _meta(b, "doors", {"pos": list(F.xyz(0, 0, 0)), "facing": F.dir(IN), "w": w, "face": face, "kind": "gate"})
    return {"box": F.box(-1, 0, -(depth - 1), w, top, 1)}


@part("canopy", "Kapı saçağı: konsollar üstünde eğimli küçük çatı (merdiven), uçlarda başlıklı.")
def canopy(b, x: int, y: int, z: int, face: str = "north", w: int = 1, depth: int = 1, st: Style | None = None, role: str = "roof"):
    """(x,y,z) kapinin alt hucresi (en kucuk); sacak kapi ustunde (v=2) baslar, depth kadar tasar."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    v = 2
    for n in range(1, depth + 1):
        F.fill(-1, v + (depth - n), n, w, v + (depth - n), n, st.stairs(role, IN, "bottom"))
    F.set(-1, v - 1, 1, st.stairs("trim", IN, "top"))
    F.set(w, v - 1, 1, st.stairs("trim", IN, "top"))
    return {"box": F.box(-1, v - 1, 1, w, v + depth - 1, depth)}


# ====================================================================== BALKON / KORKULUK / MERDIVEN
@part("railing", "Korkuluk: çit/duvar/cam/parmaklık ya da balüstrad (babalar + basamak küpeşte), aralıklı baba dikmeler.")
def railing(b, p0: Sequence[int], p1: Sequence[int], st: Style | None = None, kind: str | None = None, role: str = "railing",
            newel: int = 0):
    """p0 -> p1 dogrusu boyunca (y = p0.y) korkuluk. kind: None (rol dikmesi) | balustrade | fence | wall | glass | bars.
    newel>0: her N hucrede tam blok baba + basamak baslik."""
    st = _st(st)
    y = int(p0[1])
    sh = S.line((p0[0], y, p0[2]), (p1[0], y, p1[2]), r=0.5)
    if kind in (None, "post"):
        post = _post(st, role)
    elif kind == "fence":
        post = st.fence("fence")
    elif kind == "wall":
        post = st.wall_of("foundation")
    elif kind == "glass":
        post = st.pane("glass")
    elif kind == "bars":
        post = st.block("metal") if st.base("metal").endswith("bars") else "minecraft:iron_bars"
    elif kind == "balustrade":
        post = st.wall_of("trim") if not _is_wood(st, "trim") else st.fence("fence")
    else:
        raise ValueError("kind: post|balustrade|fence|wall|glass|bars")
    sh.put(b, post)
    top = y
    if kind == "balustrade":
        sh.moved(0, 1, 0).put(b, st.slab("trim", "bottom"))
        top = y + 1
    if newel > 0:
        C = sh.coords()
        for i, (cx, cy, cz) in enumerate(C.tolist()):
            if i % newel == 0 or i == len(C) - 1:
                b.set(cx, cy, cz, st.pick("pillar", cx, cy, cz))
                b.set(cx, cy + 1, cz, st.slab("trim", "bottom"))
                top = y + 1
    bb = sh.bbox
    return {"box": (bb[0], y, bb[2], bb[3], top, bb[5])}


@part("balcony", "Balkon: konsollu taşan döşeme, profilli kenar, korkuluk, isteğe bağlı balkon kapısı.")
def balcony(b, x: int, y: int, z: int, face: str = "north", w: int = 3, depth: int = 2, st: Style | None = None,
            rail: str | None = None, door_w: int = 0):
    """(x,y,z) balkon dosemesinin duvar duzlemindeki en kucuk hucresi (ust kat doseme seviyesi y).
    Doseme n=+1..depth, u=-1..w; korkuluk y+1'de dis kenarda; door_w>0: duvarda ortali balkon kapisi."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    F.sfill(st, "trim", -1, 0, 1, w, 0, depth - 1)
    F.fill(-1, 0, depth, w, 0, depth, st.stairs("trim", IN, "top"))
    for u in range(-1, w + 1):
        if u in (-1, w) or (u + 1) % 2 == 0:
            F.set(u, -1, 1, st.stairs("trim", IN, "top"))
            if depth >= 3:
                F.set(u, -2, 1, st.stairs("trim", IN, "top"))
    post = _post(st, "railing") if rail is None else rail
    F.fill(-1, 1, depth, w, 1, depth, post)
    F.fill(-1, 1, 1, -1, 1, depth - 1, post)
    F.fill(w, 1, 1, w, 1, depth - 1, post)
    hi_v = 1
    if door_w:
        dw = 2 if door_w >= 2 else 1
        u0 = (w - dw) // 2
        X, Y, Z = F.xyz(u0, 1, 0)
        if face == "south":
            X -= dw - 1
        if face == "west":
            Z -= dw - 1
        r = door(b, X, Y, Z, face, st, w=dw, kind="framed" if st.door_kind != "modern" else "modern")
        hi_v = r["box"][4] - y
    return {"box": F.box(-2 if door_w else -1, -2 if depth >= 3 else -1, -(st.wall_t - 1), w + 1 if door_w else w,
                         hi_v, depth)}


@part("stair_flight", "Dış merdiven kolu: basamaklar, dolu altyapı, eğimli yanak başlıkları.")
def stair_flight(b, x: int, y: int, z: int, facing: str = "north", rise: int = 3, st: Style | None = None, w: int = 1,
                 role: str = "foundation", solid: bool = True, cheeks: bool = True):
    """(x,y,z) ilk basamak; her basamak `facing` (cikis) yonune 1 ilerler, 1 yukselir. Genislik w, cikis yonunun sagina.
    Son basamagin ustu y+rise seviyesindeki zeminle ayni hizadadir (yuruyus kesintisiz)."""
    st = _st(st)
    d = VEC[facing]
    sd = VEC[CW[facing]]
    pts = []
    for k in range(rise):
        for j in range(-1 if cheeks else 0, w + 1 if cheeks else w):
            X = x + k * d[0] + j * sd[0]
            Z = z + k * d[2] + j * sd[2]
            Y = y + k
            if 0 <= j < w:
                b.set(X, Y, Z, st.stairs(role, facing, "bottom"))
            else:
                b.set(X, Y, Z, st.stairs("trim", facing, "bottom"))
            if solid and k > 0:
                st.fill(b, X, y, Z, X, Y - 1, Z, role)
            pts += [(X, Y, Z), (X, y, Z)]
    return {"box": _box(*pts)}


@part("staircase", "İç merdiven (katlar arası): düz ya da U dönüşlü; basamak üstü 3 blok baş yüksekliği açılır, boşluğa korkuluk.")
def staircase(b, x: int, y: int, z: int, facing: str = "north", rise: int = 4, st: Style | None = None, w: int = 1,
              kind: str = "straight", role: str = "trim", headroom: int = 3, rail: bool = True):
    """(x,y,z) ilk basamak (alt kat dosemesi + 1). rise = kat yuksekligi (ust kat dosemesi y-1+rise seviyesinde).
    Son basamagin ustu ust kat dosemesiyle ayni hizada; U: iki kol + sahanlik (toplam genislik 2w)."""
    st = _st(st)
    d = VEC[facing]
    sd = VEC[CW[facing]]
    upper = y - 1 + rise
    steps: list[tuple[int, int, int, str]] = []

    def P(k, j):
        return x + k * d[0] + j * sd[0], z + k * d[2] + j * sd[2]

    landing: list[tuple[int, int]] = []
    ly = None
    if kind == "straight":
        for k in range(rise):
            for j in range(w):
                X, Z = P(k, j)
                steps.append((X, y + k, Z, facing))
        exit_cells = [P(rise, j) for j in range(w)]
    elif kind == "u":
        r1 = rise // 2
        r2 = rise - r1
        for k in range(r1):
            for j in range(w):
                X, Z = P(k, j)
                steps.append((X, y + k, Z, facing))
        landing = [P(r1, j) for j in range(2 * w)]
        ly = y + r1 - 1
        for m in range(r2):
            for j in range(w, 2 * w):
                X, Z = P(r1 - 1 - m, j)
                steps.append((X, y + r1 + m, Z, OPP[facing]))
        exit_cells = [P(r1 - r2 - 1, j) for j in range(w, 2 * w)]
    else:
        raise ValueError("kind: straight | u")
    stair_cells = {(X, Y, Z) for X, Y, Z, _ in steps}
    for X, Y, Z, fc in steps:
        for hh in range(1, headroom + 1):
            if (X, Y + hh, Z) not in stair_cells:
                b.set(X, Y + hh, Z, AIR)
    for X, Y, Z, fc in steps:
        b.set(X, Y, Z, st.stairs(role, fc, "bottom"))
        if (X, Y - 1, Z) not in stair_cells and Y - 1 >= y:
            b.set(X, Y - 1, Z, st.stairs(role, OPP[fc], "top"))
    pts = [(X, Y, Z) for X, Y, Z, _ in steps]
    if kind == "u":
        for (X, Z) in landing:
            st.set(b, X, ly, Z, "floor")
            for hh in range(1, headroom + 1):
                b.set(X, ly + hh, Z, AIR)
            pts += [(X, ly, Z), (X, ly + headroom, Z)]
    for (X, Z) in exit_cells:
        if not b.is_solid(X, upper, Z):
            st.set(b, X, upper, Z, "floor")
        for hh in range(1, 3):
            if b.get(X, upper + hh, Z) not in (KEEP,) and b.is_solid(X, upper + hh, Z):
                b.set(X, upper + hh, Z, AIR)
        pts.append((X, upper + 2, Z))
    if rail:
        hole = set()
        for X, Y, Z, _ in steps:
            if Y < upper <= Y + headroom:
                hole.add((X, Z))
        for (X, Z) in landing:
            if ly is not None and ly < upper <= ly + headroom:
                hole.add((X, Z))
        post = st.fence("fence")
        exits = set(exit_cells)
        for (X, Z) in sorted(hole):
            for dd in DIRS:
                v = VEC[dd]
                q = (X + v[0], Z + v[2])
                if q in hole or q in exits:
                    continue
                if any((q[0], yy, q[1]) in stair_cells for yy in range(y, upper + 2)):
                    continue
                if b.is_solid(q[0], upper, q[1]):
                    b.set(q[0], upper + 1, q[1], post)
                    pts.append((q[0], upper + 1, q[1]))
    pts += [(X, Y + headroom, Z) for X, Y, Z, _ in steps]
    # bas boslugu kaydi: betik merdivenden sonra doseme/tavan/lamba koysa bile sonda yeniden acilir (heal_stairs)
    air = [[X, Y + hh, Z] for X, Y, Z, _ in steps for hh in range(1, headroom + 1)]
    air += [[X, upper + hh, Z] for (X, Z) in exit_cells for hh in (1, 2)]
    if ly is not None:
        air += [[X, ly + hh, Z] for (X, Z) in landing for hh in range(1, headroom + 1)]
    b.meta.setdefault("stair_air", []).extend(air)
    b.meta.setdefault("stair_cells", []).extend([[X, Y, Z] for X, Y, Z, _ in steps] + [[X, Y - 1, Z] for X, Y, Z, _ in steps])
    _meta(b, "notes", f"merdiven ({x},{y},{z}) {facing} {kind} rise={rise}")
    return {"box": _box(*pts), "steps": [(X, Y, Z) for X, Y, Z, _ in steps], "upper": upper}


def heal_stairs(b) -> int:
    """parts.staircase ile kurulan merdivenlerin bas boslugunu (basamak ustu 3 blok, cikis ustu 2 blok) yeniden acar:
    betik merdivenden SONRA doseme/tavan/lamba koyduysa kafa carpmasin. Baska bir merdivenin basamagina dokunmaz
    (ust uste merdiven denetcide kritik bulgu olur). Donus: acilan hucre sayisi."""
    keep = {tuple(int(v) for v in c[:3]) for c in b.meta.get("stair_cells") or []}
    n = 0
    for c in {tuple(int(v) for v in c[:3]) for c in b.meta.get("stair_air") or []}:
        if c not in keep and b.get_id(*c) != 1:
            b.set(*c, AIR)
            n += 1
    return n


def heal_doors(b) -> int:
    """Onu ya da arkasi ince bir engelle (tek kat duvar, dolap, cit) kapanmis kapilarin gecisini acar: kapinin o yanindaki
    iki hucre (alt ve ust) bosaltilir, ama yalniz hemen arkasindaki iki hucre yurunebilirse (gercek bir gecit olusur).
    Kalin engelde kapiya dokunulmaz (denetci 'door_blocked' der). Donus: acilan hucre sayisi."""
    db = _db()

    def blocking(s: str) -> bool:
        if s in (KEEP, AIR):
            return False
        n = s.lstrip("!").split("[", 1)[0]
        if n.endswith(("_stairs", "_slab", "_carpet", "_door", "_trapdoor", "_sign", "_banner", "_pressure_plate", "_button")):
            return False
        try:
            full = db.is_full(s.lstrip("!"))
        except Exception:
            full = False
        return full or n.endswith(("_fence", "_wall", "_pane", "_bars"))

    (ox, oy, oz), ids = b.dense()
    n = 0
    for pid, s in enumerate(b.palette):
        name = s.lstrip("!").split("[", 1)[0]
        if not name.endswith("_door") or "half=lower" not in s:
            continue
        f = s.split("facing=", 1)[1].split(",", 1)[0].rstrip("]") if "facing=" in s else None
        if f not in VEC:
            continue
        d = VEC[f]
        for (y, z, x) in np.argwhere(ids == pid):
            X, Y, Z = ox + int(x), oy + int(y), oz + int(z)
            for sgn in (1, -1):
                a = (X + sgn * d[0], Z + sgn * d[2])
                c = (X + 2 * sgn * d[0], Z + 2 * sgn * d[2])
                if blocking(b.get(a[0], Y, a[1])) and blocking(b.get(a[0], Y + 1, a[1])) \
                        and not blocking(b.get(c[0], Y, c[1])) and not blocking(b.get(c[0], Y + 1, c[1])):
                    b.set(a[0], Y, a[1], AIR)
                    b.set(a[0], Y + 1, a[1], AIR)
                    n += 2
    return n


def heal_attachables(b) -> int:
    """Desteksiz kalan tutunan bloklar (duvar mesalesi, tabela, dugme, hali, cicek...): uretec bir duvari ya da zemini
    sonradan kaldirinca havada kalanlar. Oyun bunlari ilk blok guncellemesinde dusurur; burada once duzeltilir: duvar
    mesalesinin alti doluysa ayakli mesaleye doner, digerleri kaldirilir. Yalniz uretecler icin (betikte destek dunyada
    olabilir). Donus: duzeltilen blok sayisi."""
    from ..audit.checks import Ctx, _support_eval
    ctx = Ctx(b, None)
    bi, _ = _support_eval(ctx, "attach")
    n = 0
    for i in bi.tolist():
        x, y, z = ctx.loc(*np.unravel_index(i, ctx.shape))
        name = str(b.get(x, y, z) or "").split("[", 1)[0]
        if name.endswith("wall_torch") and b.is_solid(x, y - 1, z):
            b.set(x, y, z, name.replace("wall_torch", "torch"))
        else:
            b.set(x, y, z, AIR)
        n += 1
    return n


def stair_hatch(b, cx: int, cz: int, y: int, r: int = 1) -> int:
    """Doner merdivenin ust kattaki cikisi: (cx,cz) cevresindeki halkada, altinda 1-3 blok icinde basamak olan
    doseme hucrelerini acar (son basamaklarin bas boslugu). Donus: acilan hucre sayisi."""
    n = 0
    for u in range(-r, r + 1):
        for v in range(-r, r + 1):
            if (u, v) == (0, 0):
                continue
            X, Z = cx + u, cz + v
            if any(str(b.get(X, y - dy, Z)).split("[")[0].endswith("_stairs") for dy in (1, 2, 3)):   # 3: govde onceki basamagin ustune tasar
                b.set(X, y, Z, AIR)
                n += 1
    return n


@part("spiral_stair", "Döner merdiven: orta dikme etrafında yükselen basamaklar (kule, minare); r=1 dar, r=2 geniş.")
def spiral_stair(b, cx: int, y: int, cz: int, h: int, st: Style | None = None, r: int = 1, role: str = "trim",
                 newel_role: str = "pillar", clear: bool = True):
    """Merkez (cx,cz), y'den baslayan h basamak. r=1: 3x3 (8 basamak/tur), r=2: 5x5 (16/tur, ic 3x3 dolu cekirdek)."""
    st = _st(st)
    ring = [(xx, -r) for xx in range(-r, r + 1)]
    ring += [(r, zz) for zz in range(-r + 1, r + 1)]
    ring += [(xx, r) for xx in range(r - 1, -r - 1, -1)]
    ring += [(-r, zz) for zz in range(r - 1, -r, -1)]
    nr = len(ring)
    if clear:
        b.fill(cx - r, y, cz - r, cx + r, y + h + 2, cz + r, AIR)
    core = st.block(newel_role)
    if "axis" in _db().props(core):
        core = _axis_log(core, "y")
    if r == 1:
        b.fill(cx, y, cz, cx, y + h + 2, cz, core)
    else:
        st.fill(b, cx - r + 1, y, cz - r + 1, cx + r - 1, y + h + 2, cz + r - 1, newel_role)
    for i in range(h):
        u, v = ring[i % nr]
        nu, nv = ring[(i + 1) % nr]
        fc = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}[(nu - u, nv - v)]
        b.set(cx + u, y + i, cz + v, st.stairs(role, fc, "bottom"))
    return {"box": (cx - r, y, cz - r, cx + r, y + h + 2, cz + r)}


# ====================================================================== CATILAR
_FC = ("north", "east", "south", "west")


def _roof_field(x0, z0, x1, z1, o, kind, axis=None, facing=None):
    """Genisletilmis ayak izinde (sacak dahil) her hucre icin: sacaktan uzaklik d, cikis yonu (0..3, -1 = mahya)."""
    X0, Z0, X1, Z1 = x0 - o, z0 - o, x1 + o, z1 + o
    xs = np.arange(X0, X1 + 1)[None, :]
    zs = np.arange(Z0, Z1 + 1)[:, None]
    dn = np.broadcast_to(zs - Z0, (zs.shape[0], xs.shape[1]))   # kuzey kenardan
    ds = np.broadcast_to(Z1 - zs, dn.shape)
    dw = np.broadcast_to(xs - X0, dn.shape)
    de = np.broadcast_to(X1 - xs, dn.shape)
    big = 10 ** 6
    if kind == "gable":
        if axis == "x":
            cand = np.stack([dn, np.full(dn.shape, big), ds, np.full(dn.shape, big)])
        else:
            cand = np.stack([np.full(dn.shape, big), de, np.full(dn.shape, big), dw])
    elif kind == "hip":
        cand = np.stack([dn, de, ds, dw])
    elif kind == "shed":
        f = {"south": 0, "west": 1, "north": 2, "east": 3}[facing]  # yuksek taraf facing yonunde -> alcak kenar karsida
        cand = np.full((4,) + dn.shape, big)
        cand[f] = (dn, de, ds, dw)[f]
    else:
        raise ValueError(kind)
    d = cand.min(axis=0)
    eq = cand == d[None]
    # cikis yonu: uzak kenarin tersi -> kuzey kenara yakin hucre guneye (south=2) cikar
    asc = np.full(d.shape, -1, dtype=np.int64)
    ridge = (eq[0] & eq[2]) | (eq[1] & eq[3])
    for k, a in ((0, 2), (2, 0), (1, 3), (3, 1)):
        sel = eq[k] & (asc < 0) & ~ridge
        asc[sel] = a
    return (X0, Z0, X1, Z1), d.astype(np.int64), asc


def _profile(pitch: float, s: int, ridge: bool = False) -> list[tuple[int, str]]:
    """Duvar hattindan s satir icerideki cati sirasi: [(dy, tur)] tur: stairs|slab_top|slab|full."""
    if pitch <= 0.5:
        r = s
        if r % 2 == 0:
            return [(r // 2, "slab" if ridge else "stairs")]
        return [((r - 1) // 2, "slab_top")]
    if pitch >= 2:
        return [(2 * s, "full"), (2 * s + 1, "slab" if ridge else "stairs")]
    return [(s, "slab" if ridge else "stairs")]


def _column(H_prev: int, H: int, stairs_top: bool = True) -> list[tuple[int, str]]:
    """Yarim blok cinsinden H_prev'ten H'ye kesintisiz dolgu: ust yarim basamak / tam / alt yarim basamak / merdiven."""
    out: list[tuple[int, str]] = []
    if H <= H_prev:
        H_prev = H - 1
    h = H_prev
    if h % 2 == 1:
        out.append(((h - 1) // 2, "slab_top"))
        h += 1
    while H - h >= 2:
        out.append((h // 2, "full"))
        h += 2
    if H - h == 1:
        out.append((h // 2, "slab"))
    if stairs_top and out and out[-1][1] == "full" and H % 2 == 0:
        out[-1] = (out[-1][0], "stairs")
    return out


def _curved_profile(n_rows: int, o: int) -> list[list[tuple[int, str]]]:
    """Japon cati kesiti: sacakta yatik (yarim basamak), ortada 45, mahyaya dogru dik. Satir basina [(dy, tur)]."""
    flat = max(2, o + (o % 2))
    incs = []
    for d in range(n_rows):
        if d < flat:
            incs.append(1)
        else:
            f = (d - flat) / max(1, n_rows - flat - 1)
            incs.append(2 if f < 0.6 else 4)
    H = -sum(incs[:o])
    out = []
    Hp = H + incs[0] - 1
    for d in range(n_rows):
        H += incs[d]
        out.append(_column(Hp, H))
        Hp = H
    return out


def _put_roof(b, st: Style, field, profile_rows, y: int, role: str, trim_role: str | None, verge_cols, under: bool,
              gable_planes, gable_role: str | None, ridge_cap: bool):
    (X0, Z0, X1, Z1), d, asc = field
    dmax = int(d.max())
    occupied: dict[tuple[int, int], int] = {}
    groups: dict[tuple[str, int, str, bool], list[tuple[int, int, int]]] = {}
    lowest = np.full(d.shape, 10 ** 6, dtype=np.int64)
    topmost = np.full(d.shape, -10 ** 6, dtype=np.int64)
    toptype: dict[tuple[int, int], str] = {}
    for iz in range(d.shape[0]):
        for ix in range(d.shape[1]):
            dd = int(d[iz, ix])
            a = int(asc[iz, ix])
            prof = profile_rows(dd, a < 0)
            X, Z = X0 + ix, Z0 + iz
            is_trim = trim_role is not None and (X, Z) in verge_cols
            for (dy, typ) in prof:
                Y = y + dy
                lowest[iz, ix] = min(lowest[iz, ix], Y)
                if Y >= topmost[iz, ix]:
                    topmost[iz, ix] = Y
                    toptype[(X, Z)] = typ
                key = (typ, a, "trim" if is_trim else "roof", False)
                groups.setdefault(key, []).append((X, Y, Z))
    for (typ, a, which, _), cells in groups.items():
        rl = trim_role if which == "trim" else role
        fc = _FC[a] if a >= 0 else "north"
        for (X, Y, Z) in cells:
            if typ == "stairs":
                s = st.pick_form(rl, "stairs", X, Y, Z, facing=fc, half="bottom")
            elif typ == "slab":
                s = st.pick_form(rl, "slab", X, Y, Z, type="bottom")
            elif typ == "slab_top":
                s = st.pick_form(rl, "slab", X, Y, Z, type="top")
            else:
                s = st.pick(rl, X, Y, Z)
            b.set(X, Y, Z, s)
    # alt kat (puruzsuz sacak alti): her basamagin altina ters merdiven
    if under:
        for iz in range(d.shape[0]):
            for ix in range(d.shape[1]):
                a = int(asc[iz, ix])
                if a < 0 or int(d[iz, ix]) == 0:
                    continue
                X, Z = X0 + ix, Z0 + iz
                Y = int(lowest[iz, ix]) - 1
                if not b.is_set(X, Y, Z):
                    b.set(X, Y, Z, st.pick_form(role, "stairs", X, Y, Z, facing=OPP[_FC[a]], half="top"))
    # kalkan duvarlari
    if gable_planes:
        for (axis, c, a0, a1) in gable_planes:
            for a_ in range(a0, a1 + 1):
                X, Z = (c, a_) if axis == "x" else (a_, c)
                iz, ix = Z - Z0, X - X0
                if not (0 <= iz < d.shape[0] and 0 <= ix < d.shape[1]):
                    continue
                top = int(lowest[iz, ix]) - 1
                if top >= y:
                    st.fill(b, X, y, Z, X, top, Z, gable_role or "wall")
    # mahya basligi
    if ridge_cap:
        for iz in range(d.shape[0]):
            for ix in range(d.shape[1]):
                if int(d[iz, ix]) != dmax:
                    continue
                X, Z = X0 + ix, Z0 + iz
                tt = toptype.get((X, Z))
                Y = int(topmost[iz, ix]) + 1
                if tt in ("stairs", "full"):
                    b.set(X, Y, Z, st.pick_form(role, "slab", X, Y, Z, type="bottom"))
    return int(topmost.max()), lowest


def _eave_brackets(b, st: Style, x0, z0, x1, z1, y, o, lowest, X0, Z0, sides=("north", "south", "east", "west"), every=2):
    if o <= 0:
        return
    for face, fx, fz, w in _sides(x0, z0, x1, z1):
        if face not in sides:
            continue
        F = facade(b, face, fx, y, fz, w)
        for u in range(0, w, every):
            X, _, Z = F.xyz(u, 0, 1)
            iz, ix = Z - Z0, X - X0
            if not (0 <= iz < lowest.shape[0] and 0 <= ix < lowest.shape[1]):
                continue
            Y = int(lowest[iz, ix]) - 1
            if not b.is_set(X, Y, Z):
                b.set(X, Y, Z, F.s(st.stairs("trim", IN, "top")))


def _roof_common(kind, b, x0, z0, x1, z1, y, st, axis, pitch, overhang, role, trim, gable_role, under, facing=None,
                 brackets=None, profile=None, min_eave_y=None):
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    o = int(st.overhang if overhang is None else overhang)
    pitch = float(st.pitch if pitch is None or pitch == 0 else pitch) if (pitch or st.pitch) else 1.0
    if brackets is None:
        brackets = st.has("eaves_brackets")
    if min_eave_y is not None and profile is None:
        # sacak (alt suslemesi dahil) min_eave_y'nin altina sarkmasin: altinda yurunen yol 2 blok bos kalir
        drop = 1 if (under and pitch >= 1) or brackets else 0
        while o > 0 and y + min(dy for dy, _ in _profile(pitch, -o)) - drop < min_eave_y:
            o -= 1
    if axis is None:
        axis = "x" if (x1 - x0) >= (z1 - z0) else "z"
    field = _roof_field(x0, z0, x1, z1, o, kind, axis, facing)
    (X0, Z0, X1, Z1), d, asc = field
    if profile is None:
        def rows(dd, ridge):
            return _profile(pitch, dd - o, ridge)
    else:
        def rows(dd, ridge):
            return profile(dd, ridge)
    verge = set()
    gplanes = []
    if kind == "gable":
        if axis == "x":
            verge = {(X0, zz) for zz in range(Z0, Z1 + 1)} | {(X1, zz) for zz in range(Z0, Z1 + 1)}
            gplanes = [("x", x0, z0, z1), ("x", x1, z0, z1)]
        else:
            verge = {(xx, Z0) for xx in range(X0, X1 + 1)} | {(xx, Z1) for xx in range(X0, X1 + 1)}
            gplanes = [("z", z0, x0, x1), ("z", z1, x0, x1)]
    elif kind == "shed":
        lowside = OPP[facing]
        sides = {"north": "x", "south": "x", "east": "z", "west": "z"}
        if facing in ("north", "south"):
            verge = {(X0, zz) for zz in range(Z0, Z1 + 1)} | {(X1, zz) for zz in range(Z0, Z1 + 1)}
            gplanes = [("x", x0, z0, z1), ("x", x1, z0, z1), ("z", z1 if facing == "south" else z0, x0, x1)]
        else:
            verge = {(xx, Z0) for xx in range(X0, X1 + 1)} | {(xx, Z1) for xx in range(X0, X1 + 1)}
            gplanes = [("z", z0, x0, x1), ("z", z1, x0, x1), ("x", x1 if facing == "east" else x0, z0, z1)]
    if gable_role is None:
        gable_role = "wall2" if st.has("upper_timber") or st.has("timber") else "wall"
    top, lowest = _put_roof(b, st, field, rows, y, role, ("roof_trim" if trim else None), verge,
                            under and pitch >= 1 and profile is None, gplanes, gable_role, ridge_cap=(kind != "shed"))
    if brackets:
        sides_ = ("north", "south") if (kind == "gable" and axis == "x") else (("east", "west") if kind == "gable" else ("north", "south", "east", "west"))
        _eave_brackets(b, st, x0, z0, x1, z1, y, o, lowest, X0, Z0, sides_)
    low = int(lowest.min()) - (1 if (under or brackets) else 0)
    return {"box": (X0, min(low, y), Z0, X1, top + 1, Z1), "top": top, "eave_y": int(lowest.min()), "overhang": o,
            "axis": axis}


@part("roof_gable", "Beşik çatı: saçak taşkını, kalkan duvarları, kontrast kenar (alın tahtası), mahya başlığı, düzgün saçak altı.")
def roof_gable(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, axis: str | None = None,
               pitch: float | None = None, overhang: int | None = None, role: str = "roof", trim: bool = True,
               gable_role: str | None = None, under: bool = True, brackets: bool | None = None,
               min_eave_y: int | None = None):
    """(x0,z0)-(x1,z1) duvar dis yuzleri; y = duvar hattindaki ilk cati sirasi (duvarin en ust sirasi + 1).
    axis: mahya yonu ('x' | 'z'; varsayilan uzun kenar). pitch: 0.5 (basamak+yarim), 1 (45), 2 (dik). Sacak duvar
    ustunden asagi sarkar (gercekci); kalkan ucgeni gable_role ile dolar. min_eave_y: sacagin (alt susu dahil) inebilecegi
    en dusuk y; tasma bu sinira gore kisalir (sacak altinda yurunen yol 2 blok bos kalsin)."""
    return _roof_common("gable", b, x0, z0, x1, z1, y, st, axis, pitch, overhang, role, trim, gable_role, under,
                        brackets=brackets, min_eave_y=min_eave_y)


@part("roof_hip", "Kırma çatı (dört yana eğimli; kare tabanda piramit): kalça çizgileri oyunda dış köşe olur, saçak konsolları (Osmanlı).")
def roof_hip(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, pitch: float | None = None,
             overhang: int | None = None, role: str = "roof", trim: bool = False, under: bool = True,
             brackets: bool | None = None, min_eave_y: int | None = None):
    """Bkz. roof_gable. Kare ayak izinde piramit (roof_pyramid)."""
    return _roof_common("hip", b, x0, z0, x1, z1, y, st, None, pitch, overhang, role, trim, None, under,
                        brackets=brackets, min_eave_y=min_eave_y)


@part("roof_pyramid", "Piramit çatı (kare kule/köşk başlığı), tepesine alem/sivri uç.")
def roof_pyramid(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, pitch: float | None = None,
                 overhang: int | None = None, role: str = "roof", finial: bool = True, min_eave_y: int | None = None):
    r = _roof_common("hip", b, x0, z0, x1, z1, y, st, None, pitch, overhang, role, False, None, True, min_eave_y=min_eave_y)
    if finial:
        cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
        b.set(cx, r["top"] + 1, cz, "minecraft:lightning_rod[facing=up]")
        r["box"] = r["box"][:4] + (max(r["box"][4], r["top"] + 1),) + r["box"][5:]
    return r


@part("roof_shed", "Tek eğimli (sundurma) çatı: yüksek taraf facing yönünde, yan kalkanlar.")
def roof_shed(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, facing: str = "south",
              pitch: float | None = None, overhang: int | None = None, role: str = "roof", trim: bool = True,
              min_eave_y: int | None = None):
    """facing = cikis yonu (yuksek kenar o tarafta). Varsayilan egim 0.5 (yatik)."""
    return _roof_common("shed", b, x0, z0, x1, z1, y, st, None, 0.5 if pitch is None else pitch, overhang, role, trim,
                        None, True, facing=facing, min_eave_y=min_eave_y)


@part("roof_mansard", "Mansart çatı: dik alt etek (2 sıra dolu+basamak) ve yatık üst kırma; çatı katına yer açar.")
def roof_mansard(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, steep_rows: int = 2,
                 overhang: int | None = None, role: str = "roof", top_pitch: float = 0.5, min_eave_y: int | None = None):
    st = _st(st)
    o = int(st.overhang if overhang is None else overhang)
    k = int(steep_rows)

    def prof(dd, ridge):
        s = dd - o
        if s < k:
            return _profile(2.0, s, ridge and s == k - 1)
        base = 2 * k
        return [(base + dy, t) for dy, t in _profile(top_pitch, s - k, ridge)]
    while min_eave_y is not None and o > 0 and y + min(dy for dy, _ in prof(0, False)) < min_eave_y:
        o -= 1                                   # dik etek yurunen yola sarkmasin
    return _roof_common("hip", b, x0, z0, x1, z1, y, st, None, 2.0, o, role, False, None, True, profile=prof)


@part("roof_curved", "Kavisli görünümlü Japon çatısı: saçakta yatık yarım basamak, ortada 45°, mahyada dik; köşeleri kalkık.")
def roof_curved(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, kind: str = "hip",
                overhang: int | None = None, role: str = "roof", upturn: bool = True, min_eave_y: int | None = None):
    st = _st(st)
    o = int(st.overhang if overhang is None else overhang)
    x0_, x1_ = sorted((x0, x1))
    z0_, z1_ = sorted((z0, z1))
    while True:
        span = min(x1_ - x0_, z1_ - z0_) + 1 + 2 * o
        nrows = span // 2 + 1
        rows = _curved_profile(nrows, o)
        if min_eave_y is None or o <= 0 or y + min(dy for dy, _ in rows[0]) >= min_eave_y:
            break
        o -= 1                                   # kalkik sacak yurunen yola sarkmasin

    def prof(dd, ridge):
        pr = rows[min(dd, len(rows) - 1)]
        if ridge:
            return [(dy, ("slab" if t == "stairs" else t)) for dy, t in pr]
        return pr
    axis = "x" if (x1_ - x0_) >= (z1_ - z0_) else "z"
    r = _roof_common(kind, b, x0_, z0_, x1_, z1_, y, st, axis, 1.0, o, role, False, None, False, profile=prof)
    if upturn and o >= 1:
        X0, Z0, X1, Z1 = x0_ - o, z0_ - o, x1_ + o, z1_ + o
        ey = y + rows[0][0][0]
        for (cx, cz, fx, fz) in ((X0, Z0, -1, -1), (X1, Z0, 1, -1), (X0, Z1, -1, 1), (X1, Z1, 1, 1)):
            b.set(cx, ey, cz, st.block("roof_trim"))
            b.set(cx, ey + 1, cz, st.stairs("roof_trim", "north" if fz > 0 else "south", "bottom"))
        r["box"] = (r["box"][0], r["box"][1], r["box"][2], r["box"][3], max(r["box"][4], ey + 1), r["box"][5])
    return r


@part("roof_flat", "Düz çatı: dokulu döşeme, saçak alnı, korkuluk duvarı (parapet) + harpuşta, çatı üstü ayrıntıları (ışıklık, baca, güneş paneli).")
def roof_flat(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, overhang: int | None = None,
              parapet: int | None = None, details: bool = True, role: str = "roof", min_eave_y: int | None = None):
    """y = cati dosemesi seviyesi (duvarin en ust sirasi + 1). parapet: 0 yok, 1+ yukseklik (+ yarim harpusta).
    min_eave_y yalniz arayuz uyumu icin: duz catinin alni en cok y-1'e iner."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    o = int(st.overhang if overhang is None else overhang)
    if parapet is None:
        parapet = 0 if o > 0 else 1
    X0, Z0, X1, Z1 = x0 - o, z0 - o, x1 + o, z1 + o
    st.fill(b, x0, y, z0, x1, y, z1, role)
    if o > 0:
        ring = S.box(X0, y, Z0, X1, y, Z1) - S.box(x0, y, z0, x1, y, z1)
        ring.put_style(b, st, "roof_trim")
        S.box(X0, y - 1, Z0, X1, y - 1, Z1).surface("down")
        edge = S.box(X0, y - 1, Z0, X1, y - 1, Z1) - S.box(X0 + 1, y - 1, Z0 + 1, X1 - 1, y - 1, Z1 - 1)
        edge.put(b, st.slab("roof_trim", "top"))
    top = y
    if parapet > 0:
        P0, Q0, P1, Q1 = (x0, z0, x1, z1) if o > 0 else (X0, Z0, X1, Z1)
        sh = S.shell_box(P0, y + 1, Q0, P1, y + parapet, Q1, top=False, bottom=False)
        sh.put_style(b, st, "wall")
        cap = S.shell_box(P0, y + parapet + 1, Q0, P1, y + parapet + 1, Q1, top=False, bottom=False)
        cap.put(b, st.slab("roof_trim", "bottom"))
        top = y + parapet + 1
    if details and (x1 - x0) >= 6 and (z1 - z0) >= 6:
        cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
        # isiklik (cam blok) + cercevesi
        st.fill(b, cx - 1, y, cz - 1, cx + 1, y, cz, "glass_block") if st.base("glass_block") else None
        b.fill(cx - 1, y, cz - 1, cx + 1, y, cz, st.block("glass_block"))
        b.fill(cx - 2, y + 1, cz - 2, cx + 2, y + 1, cz - 2, st.slab("roof_trim", "bottom"))
        b.fill(cx - 2, y + 1, cz + 1, cx + 2, y + 1, cz + 1, st.slab("roof_trim", "bottom"))
        b.set(cx - 2, y + 1, cz - 1, st.slab("roof_trim", "bottom"))
        b.set(cx - 2, y + 1, cz, st.slab("roof_trim", "bottom"))
        b.set(cx + 2, y + 1, cz - 1, st.slab("roof_trim", "bottom"))
        b.set(cx + 2, y + 1, cz, st.slab("roof_trim", "bottom"))
        # havalandirma bacalari
        for (vx, vz) in ((x0 + 2, z0 + 2), (x1 - 2, z0 + 2)):
            b.set(vx, y + 1, vz, st.block("accent"))
            b.set(vx, y + 2, vz, "minecraft:lightning_rod[facing=up]")
        # klima/teknik kutu
        b.fill(x1 - 3, y + 1, z1 - 3, x1 - 2, y + 1, z1 - 2, "minecraft:smooth_stone")
        b.fill(x1 - 3, y + 2, z1 - 3, x1 - 2, y + 2, z1 - 2, "minecraft:iron_trapdoor[half=bottom]")
        # gunes paneli dizisi
        if (x1 - x0) >= 10:
            b.fill(x0 + 2, y + 1, z1 - 3, x0 + 5, y + 1, z1 - 2, "minecraft:daylight_detector")
        top = max(top, y + 2)
    return {"box": (X0, y - (1 if o > 0 else 0), Z0, X1, top, Z1), "top": top}


@part("dormer", "Çatı penceresi (dormer): öne bakan küçük kalkanlı çıkma, pencere, iki yana eğimli mini çatı; arkası çatıya gömülür.")
def dormer(b, x: int, y: int, z: int, face: str = "north", w: int = 1, h: int = 2, st: Style | None = None, depth: int = 3):
    """(x,y,z) dormer penceresinin en kucuk alt hucresi, dormer on duvari duzleminde (genelde sacak hattinin biraz
    icinde, cati yuzeyinde). Dormer n=-depth..0 icine gomulur; ic taraf temizlenir (cati arasina acilir)."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    W0, W1 = -1, w
    wallr = "wall2" if st.has("upper_timber") or st.has("timber") else "wall"
    # on duvar + yanlar
    for n in range(-depth, 1):
        F.sfill(st, wallr, W0, -1, n, W0, h, n)
        F.sfill(st, wallr, W1, -1, n, W1, h, n)
    F.sfill(st, wallr, W0, -1, 0, W1, -1, 0)
    F.clear(0, 0, -depth + 1, w - 1, h - 1, -1)
    F.fill(0, 0, 0, w - 1, h - 1, 0, st.pane())
    F.sfill(st, "frame", 0, -1, 0, w - 1, -1, 0)
    F.fill(-1, -1, 1, w, -1, 1, st.stairs("trim", IN, "top"))
    # mini besik cati (mahya n yonunde)
    half = (w + 2 + 1) // 2
    top_v = h
    for k in range(half + 1):
        ua, ub = W0 - 1 + k, W1 + 1 - k
        v = h + k
        if ua > ub:
            break
        if ua == ub:
            F.fill(ua, v, -depth, ua, v, 1, st.slab("roof_trim", "bottom"))
        else:
            F.fill(ua, v, -depth, ua, v, 1, st.stairs("roof", R, "bottom"))
            F.fill(ub, v, -depth, ub, v, 1, st.stairs("roof", L, "bottom"))
            if ub - ua >= 2:
                F.sfill(st, wallr, ua + 1, v, 0, ub - 1, v, 0)
                F.clear(ua + 1, v, -depth + 1, ub - 1, v, -1)
        top_v = v
    _meta(b, "windows", {"box": list(F.box(0, 0, 0, w - 1, h - 1, 0)), "face": face, "kind": "dormer"})
    return {"box": F.box(W0 - 1, -1, -depth, W1 + 1, top_v, 1)}


@part("chimney", "Baca: tuğla/taş gövde, bindirmeli taç (ters merdiven halkası), başlık ve baca külahları (duvar blokları).")
def chimney(b, x: int, y: int, z: int, h: int, st: Style | None = None, w: int = 2, d: int | None = None, role: str = "tile"):
    """(x,y,z) gövdenin en kucuk alt kosesi; w x d kesit (varsayilan 2x2), h gövde yuksekligi (tac haric)."""
    st = _st(st)
    d = int(d or w)
    r_ = role if st.base(role) not in ("sea_lantern",) and not st.base(role).endswith("glazed_terracotta") else "foundation"
    st.fill(b, x, y, z, x + w - 1, y + h - 1, z + d - 1, r_)
    ty = y + h
    # tac: disa tasan ters merdiven halkasi + tam sira + baca kulahlari
    for face, fx, fz, ww in _sides(x, z, x + w - 1, z + d - 1):
        F = facade(b, face, fx, ty, fz, ww)
        F.fill(0, 0, 1, ww - 1, 0, 1, st.stairs("foundation", IN, "top"))
    for (cx, cz) in ((x - 1, z - 1), (x + w, z - 1), (x - 1, z + d), (x + w, z + d)):
        b.set(cx, ty, cz, st.slab("foundation", "top"))
    st.fill(b, x, ty, z, x + w - 1, ty, z + d - 1, "foundation")
    pot = st.wall_of("foundation")
    for xx in range(x, x + w):
        for zz in range(z, z + d):
            b.set(xx, ty + 1, zz, pot)
    b.set(x, ty, z, AIR) if (w >= 2 and d >= 2) and False else None
    return {"box": (x - 1, y, z - 1, x + w, ty + 1, z + d)}


def _smooth_dome_surface(b, st: Style, shape: S.Shape, cx: float, cz: float, role: str, min_y: int) -> None:
    """Kubbe dis yuzeyindeki basamak kenarlarina merkeze bakan merdiven koyar (puruzsuz gorunum)."""
    m = shape.mask
    x0, y0, z0 = shape.origin
    p = np.pad(m, 1)
    sy, sz, sx = m.shape
    above = p[2:, 1:-1, 1:-1]
    for (dname, dx, dz) in (("north", 0, -1), ("south", 0, 1), ("west", -1, 0), ("east", 1, 0)):
        nb = p[1:-1, 1 + dz:1 + dz + sz, 1 + dx:1 + dx + sx]
        cand = m & ~above & ~nb
        ys, zs, xs = np.nonzero(cand)
        for yy, zz, xx in zip(ys.tolist(), zs.tolist(), xs.tolist()):
            X, Y, Z = x0 + xx, y0 + yy, z0 + zz
            if Y < min_y:
                continue
            vx, vz = X - cx, Z - cz
            if abs(vx) >= abs(vz):
                fc = "west" if vx > 0 else "east"
            else:
                fc = "north" if vz > 0 else "south"
            if (dx, dz) != {"west": (1, 0), "east": (-1, 0), "north": (0, 1), "south": (0, -1)}[fc]:
                continue
            b.set(X, Y, Z, st.pick_form(role, "stairs", X, Y, Z, facing=fc, half="bottom"))


@part("dome", "Kubbe: kasnak (pencereli tambur), yarım küre/soğan/sivri kabuk, basamak yumuşatma, kurşun kaplama, alem; içte avize kancası.")
def dome(b, cx: int, y: int, cz: int, r: int, st: Style | None = None, kind: str = "hemi", drum: int = 0,
         windows: bool = True, finial: bool = True, role: str = "dome", h: int | None = None, smooth: bool = True):
    """(cx, y, cz) kubbe/tambur tabaninin merkezi; r yaricap (dis). drum>0: o kadar yukseklikte pencereli tambur.
    kind: hemi | onion | pointed | bell | cone. Ici bos; tepe hucresinin alti avize icin uygundur."""
    st = _st(st)
    r = int(r)
    if drum > 0:
        ring = S.cylinder((cx, y, cz), (cx, y + drum - 1, cz), r, hollow=True, t=1)
        ring.put_style(b, st, "wall")
        # tambur kornisi
        cr = S.ring((cx, y + drum, cz), r + 1, r, 1)
        for (X, Y, Z) in cr.coords().tolist():
            vx, vz = X - cx, Z - cz
            fc = ("west" if vx > 0 else "east") if abs(vx) >= abs(vz) else ("north" if vz > 0 else "south")
            b.set(X, Y - 1, Z, st.stairs("foundation", fc, "top"))
        if windows and r >= 3 and drum >= 3:
            n = 8 if r >= 5 else 4
            for i in range(n):
                ang = 2 * math.pi * i / n
                wx, wz = cx + int(round(math.cos(ang) * r)), cz + int(round(math.sin(ang) * r))
                for yy in range(y + 1, y + drum - 1):
                    b.set(wx, yy, wz, AIR)
                    b.set(wx, yy, wz, st.pane())
    base = y + drum
    solid = S.dome((cx, base, cz), r, h=h, kind=kind)
    shell = solid.shell(1, diag=True)
    if st.base(role).endswith("glass") or "glass" in st.base(role):
        shell.put_style(b, st, role)
    else:
        shell.put_style(b, st, role)
        if smooth and kind in ("hemi", "pointed", "onion", "bell"):
            _smooth_dome_surface(b, st, shell, cx, cz, role, base + 1)
    bb = solid.bbox
    top = bb[4]
    if finial:
        b.set(cx, top + 1, cz, st.block("detail") if st.base("detail") in ("gold_block",) else "minecraft:lightning_rod[facing=up]")
        top += 1
    return {"box": (min(bb[0], cx - r - 1), y, min(bb[2], cz - r - 1), max(bb[3], cx + r + 1), top, max(bb[5], cz + r + 1)),
            "top": top, "apex_inside": (cx, bb[4] - 1, cz)}


@part("spire", "Konik külah/sivri çatı: dairesel kule başlığı, taşkın saçak halkası, basamak yumuşatma, tepe ucu.")
def spire(b, cx: int, y: int, cz: int, r: int, h: int | None = None, st: Style | None = None, role: str = "roof",
          flare: bool = True, finial: bool = True):
    """(cx,y,cz) koninin taban merkezi; r taban yaricapi; h yukseklik (varsayilan 2.5r)."""
    st = _st(st)
    h = int(h or round(r * 2.5) + 1)
    cone = S.cone((cx, y, cz), r, h)
    sh = cone.shell(1, diag=True)
    sh.put_style(b, st, role)
    _smooth_dome_surface(b, st, sh, cx, cz, role, y)
    lo = y
    if flare:
        ring = S.ring((cx, y - 1, cz), r + 1, r, 1)
        for (X, Y, Z) in ring.coords().tolist():
            vx, vz = X - cx, Z - cz
            fc = ("west" if vx > 0 else "east") if abs(vx) >= abs(vz) else ("north" if vz > 0 else "south")
            b.set(X, Y, Z, st.pick_form(role, "stairs", X, Y, Z, facing=fc, half="bottom"))
        lo = y - 1
    top = y + h - 1
    if finial:
        b.set(cx, top + 1, cz, "minecraft:lightning_rod[facing=up]")
        top += 1
    return {"box": (cx - r - 1, lo, cz - r - 1, cx + r + 1, top, cz + r + 1), "top": top}


@part("roof", "Çatı dağıtıcı: stilin roof_kind'ine göre gable/hip/flat/mansard/shed/curved/pyramid çağırır.")
def roof(b, x0: int, z0: int, x1: int, z1: int, y: int, st: Style | None = None, kind: str | None = None, **kw):
    st = _st(st)
    kind = kind or st.roof_kind
    fn = {"gable": roof_gable, "hip": roof_hip, "flat": roof_flat, "mansard": roof_mansard, "shed": roof_shed,
          "curved": roof_curved, "pyramid": roof_pyramid}.get(kind)
    if fn is None:
        raise ValueError("kind: gable|hip|flat|mansard|shed|curved|pyramid")
    r = fn(b, x0, z0, x1, z1, y, st, **kw)
    return {k: v for k, v in r.items() if k not in ("name", "written")}


# ====================================================================== KULELER
def _ring_stairs(b, st: Style, cx: int, y: int, cz: int, r_out: float, r_in: float, role: str, half: str, inward: bool = True):
    ring = S.ring((cx, y, cz), r_out, r_in, 1)
    for (X, Y, Z) in ring.coords().tolist():
        vx, vz = X - cx, Z - cz
        if abs(vx) >= abs(vz):
            fc = ("west" if vx > 0 else "east") if inward else ("east" if vx > 0 else "west")
        else:
            fc = ("north" if vz > 0 else "south") if inward else ("south" if vz > 0 else "north")
        b.set(X, Y, Z, st.pick_form(role, "stairs", X, Y, Z, facing=fc, half=half))
    return ring


@part("minaret", "Minare: kare kürsü + pabuç geçişi, ince gövde, mukarnaslı şerefe(ler) ve taş korkuluk, petek, kurşun külah ve alem.")
def minaret(b, cx: int, y: int, cz: int, h: int = 36, st: Style | None = None, r: int = 2, serefe: int = 1,
            shaft_role: str = "pillar", base_role: str = "foundation", cap_role: str = "dome", rail_role: str = "foundation"):
    """(cx, y, cz) kursunun taban merkezi (y = zemin + 1). h kulah ucuna kadar toplam yukseklik (alem haric).
    serefe 1-3 balkon. Saygili, sade oranlar: kursu ~%12, govde, serefeler govdenin ust yarisinda, kulah ~%22."""
    st = _st(st)
    r = max(1, int(r))
    serefe = max(1, min(3, int(serefe)))
    kb = r + 1  # kursu yari genisligi
    base_h = max(3, int(round(h * 0.12)))
    cap_h = max(6, int(round(h * 0.26)))
    shaft_top = y + h - cap_h - 1
    # kursu (kare kaide) + silme
    st.fill(b, cx - kb, y, cz - kb, cx + kb, y + base_h - 1, cz + kb, base_role)
    for face, fx, fz, w in _sides(cx - kb, cz - kb, cx + kb, cz + kb):
        F = facade(b, face, fx, y + base_h - 1, fz, w)
        F.fill(0, 0, 1, w - 1, 0, 1, st.stairs("foundation", IN, "top"))
        F.fill(0, -base_h + 1, 1, w - 1, -base_h + 1, 1, st.stairs("foundation", IN, "bottom"))
    by = y + base_h
    # pabuc: kare -> yuvarlak gecis
    _ring_stairs(b, st, cx, by, cz, r + 1, r, base_role, "bottom")
    shaft_col = st.block(shaft_role)
    if "axis" in _db().props(shaft_col):
        shaft_col = _axis_log(shaft_col, "y")
    S.cylinder((cx, by, cz), (cx, shaft_top, cz), r).put(b, shaft_col)
    # serefeler: govdenin %55..%85 araliginda
    span = shaft_top - by
    levels = [by + int(span * (0.62 + 0.24 * i / max(1, serefe - 1))) if serefe > 1 else by + int(span * 0.72) for i in range(serefe)]
    rail = st.wall_of(rail_role) if not _is_wood(st, rail_role) else _post(st, rail_role)
    for ys in levels:
        _ring_stairs(b, st, cx, ys - 2, cz, r + 1, r, "foundation", "top")
        S.ring((cx, ys - 1, cz), r + 1, r, 1).put_style(b, st, "foundation")
        _ring_stairs(b, st, cx, ys - 1, cz, r + 2, r + 1, "foundation", "top")
        S.disk((cx, ys, cz), r + 2).put_style(b, st, "foundation")
        S.ring((cx, ys + 1, cz), r + 2, r + 1, 1, thick=True).put(b, rail)
        S.cylinder((cx, ys, cz), (cx, ys, cz), r).put(b, shaft_col)
    # petek (ust govde) korniş + kulah
    _ring_stairs(b, st, cx, shaft_top, cz, r + 1, r, "foundation", "top")
    sp = spire(b, cx, shaft_top + 1, cz, r, cap_h, st, role=cap_role, flare=False, finial=False)
    tip = sp["top"]
    b.set(cx, tip + 1, cz, "minecraft:lightning_rod[facing=up]")
    return {"box": (cx - max(kb + 1, r + 2), y, cz - max(kb + 1, r + 2), cx + max(kb + 1, r + 2), tip + 1, cz + max(kb + 1, r + 2)),
            "serefe": levels, "top": tip + 1}


@part("tower", "Yuvarlak kule: kalın duvar, mazgal pencereler, katlar ve döner merdiven, konsollu üst kat; külah, mazgallı siper ya da kubbe.")
def tower(b, cx: int, y: int, cz: int, r: int = 4, h: int = 16, st: Style | None = None, top: str = "cone",
          role: str = "wall", floors: bool = True, stair: bool = True):
    """(cx,y,cz) taban merkezi (y = zemin kat dosemesi). top: cone | crenel | dome | none."""
    st = _st(st)
    r = max(2, int(r))
    S.disk((cx, y, cz), r).put_style(b, st, "foundation")
    # ic hacim bos: kule bir surun/duvarin kosesine oturtulsa da merdiven ve katlar dolu tasa gomulmesin
    S.cylinder((cx, y + 1, cz), (cx, y + h - 1, cz), r - 1, hollow=False).put(b, AIR)
    S.cylinder((cx, y + 1, cz), (cx, y + h - 1, cz), r, hollow=True, t=1).put_style(b, st, role)
    S.ring((cx, y, cz), r + 1, r, 1).put_style(b, st, "foundation")
    _ring_stairs(b, st, cx, y + 1, cz, r + 1, r, "foundation", "bottom")
    fh = st.floor_h
    if floors and r >= 3:
        for fy in range(y + fh, y + h - 1, fh):
            (S.disk((cx, fy, cz), r - 1) - S.box(cx - 1, fy, cz - 1, cx + 1, fy, cz + 1)).put_style(b, st, "floor")
            _meta(b, "floors", {"y": fy, "box": [cx - r + 1, fy, cz - r + 1, cx + r - 1, fy, cz + r - 1]})
    if stair and r >= 3:
        spiral_stair(b, cx, y + 1, cz, h - 2, st, r=1, clear=False)
    # mazgallar: dort yonde, her katta
    for fy in range(y + 2, y + h - 2, fh):
        for d in DIRS:
            dx, _, dz = VEC[d]
            X, Z = cx + dx * r, cz + dz * r
            b.set(X, fy, Z, st.pane())            # mazgal: cam panel (yagmur/canavar girmez, isik alir)
            b.set(X, fy + 1, Z, st.pane())
    _meta(b, "rooms", {"name": "kule", "box": [cx - r + 1, y + 1, cz - r + 1, cx + r - 1, y + h - 1, cz + r - 1]})
    tp = y + h - 1
    if top in ("crenel", "cone", "dome"):
        _ring_stairs(b, st, cx, tp, cz, r + 1, r, "foundation", "top")
        S.ring((cx, tp + 1, cz), r + 1, r, 1).put_style(b, st, role)
        S.disk((cx, tp, cz), r - 1).put_style(b, st, "floor")
        if stair and r >= 3:
            stair_hatch(b, cx, cz, tp)
        tp += 1
    if top == "crenel":
        ring = S.ring((cx, tp + 1, cz), r + 1, r, 1)
        C = ring.coords()
        ang = np.arctan2(C[:, 2] - cz, C[:, 0] - cx)
        k = np.floor((ang + np.pi) / (2 * np.pi) * max(8, 2 * r + 4)).astype(int)
        for (X, Y, Z), kk in zip(C.tolist(), k.tolist()):
            if kk % 2 == 0:
                b.set(X, Y, Z, st.pick(role, X, Y, Z))
        tp += 1
    elif top == "cone":
        sp = spire(b, cx, tp + 1, cz, r + 1, None, st, role="roof", flare=True)
        # kulah ici dolu: ulasilamayan kapali cati arasi (canavar yuvasi) birakma
        S.cone((cx, tp + 1, cz), r + 1, sp["top"] - tp - 1).put_style(b, st, "roof", only_empty=True)
        tp = sp["top"]
    elif top == "dome":
        d = dome(b, cx, tp + 1, cz, r, st, kind="hemi")
        tp = d["top"]
    return {"box": (cx - r - 2, y, cz - r - 2, cx + r + 2, tp, cz + r + 2), "top": tp}


# ====================================================================== AVLU / SU
@part("arcade", "Revak (kemerli galeri): sütunlar, alternatif renkli kemerler, tavan, arka duvar; üstünde sundurma, düz ya da her gözde küçük kubbe.")
def arcade(b, x: int, y: int, z: int, face: str = "north", length: int = 13, st: Style | None = None, depth: int = 3,
           bay: int = 4, col_h: int = 4, arch: str | None = None, roof_kind: str = "shed", back_wall: bool = True,
           ablaq: bool | None = None):
    """(x,y,z) on hattin (kemerlerin) en kucuk ucundaki ilk sutunun tabani (y = yuruyus seviyesi, doseme y-1).
    Galeri n=0 (kemer duzlemi) .. n=-depth (arka duvar); length = sutun sayisi*bay+1'e yuvarlanir.
    roof_kind: shed | flat | domes (Osmanli revak kubbeleri)."""
    st = _st(st)
    nb = max(1, (length - 1) // bay)
    L = nb * bay + 1
    F = facade(b, face, x, y, z, L)
    ak = arch or (st.arch_kind if st.arch_kind != "flat" else "round")
    if ablaq is None:
        ablaq = st.has("almasik")
    span = bay - 1
    rise = S.arch_rise(span, ak) if span > 1 else 0
    h_open = col_h + rise
    top = h_open  # kemer duvarinin en ust sirasi (v)
    # doseme
    F.sfill(st, "paving", 0, -1, -depth, L - 1, -1, 0)
    # on kemer duvari
    F.sfill(st, "wall", 0, col_h, 0, L - 1, top, 0)
    prof = S.arch_profile(span, h_open, ak)
    cells, corners, key = _arch_ring(prof)
    spring = int(np.argmin(prof.all(axis=1))) if not prof.all() else h_open
    for i in range(nb):
        u0 = i * bay + 1
        vs, us = np.nonzero(prof)
        for v, u in zip(vs.tolist(), us.tolist()):
            F.set(u0 + u, v, 0, AIR)
        for (u, v) in cells:
            if u < 0 or u >= span or v < spring:
                if v >= spring:
                    role = ("accent" if (u + v) % 2 == 0 else "foundation") if ablaq else "trim"
                    if st.base("trim") == st.base("frame") and _is_wood(st, "trim"):
                        role = ("accent" if (u + v) % 2 == 0 else "foundation") if ablaq else "foundation"
                    F.sset(st, role, u0 + u, v, 0)
                continue
            role = ("accent" if (u + v) % 2 == 0 else "foundation") if ablaq else "foundation"
            F.sset(st, role, u0 + u, v, 0)
        for (u, v, d) in corners:
            F.set(u0 + u, v, 0, st.stairs("foundation", d, "top"))
        if key[0] is not None:
            F.set(u0 + key[0], key[1], 0, st.block("detail"))
    # sutunlar
    shaft = st.block("pillar")
    if "axis" in _db().props(shaft):
        shaft = _axis_log(shaft, "y")
    for i in range(nb + 1):
        u = i * bay
        F.sset(st, "foundation", u, 0, 0)
        F.fill(u, 1, 0, u, col_h - 2, 0, shaft)
        F.set(u, col_h - 1, 0, st.block("detail") if st.base("detail") != "sea_lantern" else st.block("trim"))
        F.set(u, 0, 1, st.stairs("foundation", IN, "bottom"))
        F.set(u, col_h - 1, 1, st.stairs("trim", IN, "top"))
    # korniş
    F.fill(-1, top + 1, 1, L, top + 1, 1, st.stairs("trim", IN, "top"))
    # tavan ve arka duvar, yan duvarlar
    F.sfill(st, "ceiling", 0, top + 1, -depth, L - 1, top + 1, 0)
    if back_wall:
        F.sfill(st, "wall", -1, -1, -depth - 1, L, top + 1, -depth - 1)
    F.sfill(st, "wall", -1, -1, -depth, -1, top + 1, 0)
    F.sfill(st, "wall", L, -1, -depth, L, top + 1, 0)
    hi_v = top + 1
    if roof_kind == "shed":
        for k in range(depth + 3):
            n = 1 - k
            F.fill(-2, top + 2 + k // 2, n, L + 1, top + 2 + k // 2, n,
                   st.stairs("roof", IN, "bottom") if k % 2 == 0 else st.slab("roof", "top"))
            hi_v = max(hi_v, top + 2 + k // 2)
        F.fill(-2, top + 1, 2, L + 1, top + 1, 2, st.stairs("roof", IN, "bottom"))
    elif roof_kind == "flat":
        F.fill(-1, top + 2, -depth - 1, L, top + 2, 1, st.slab("roof_trim", "bottom"))
        hi_v = top + 2
    elif roof_kind == "domes":
        F.sfill(st, "roof", -1, top + 2, -depth - 1, L, top + 2, 1)
        rr = max(1, min(span, depth + 1) // 2)
        for i in range(nb):
            cu = i * bay + bay // 2
            cxx, cyy, czz = F.xyz(cu, top + 3, -(depth // 2))
            dd = dome(b, cxx, cyy, czz, rr, st, kind="hemi", finial=True)
            hi_v = max(hi_v, dd["top"] - y)
    _meta(b, "rooms", {"name": "revak", "box": list(F.box(0, 0, -depth, L - 1, top, -1))})
    return {"box": F.box(-2, -1, -depth - 1, L + 1, hi_v, 2), "length": L}


@part("pool", "Havuz: kaplamalı çanak, kenar taşı, su altı ışıkları, suya inen basamaklar (su tamamen kapalı hacimde).")
def pool(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, depth: int = 2, lights: bool = True,
         steps: bool = True, lining: str = "water_edge", coping: str = "water_edge"):
    """(x0..x1, z0..z1) kenar tasi dahil dis olcu; y = zemin yuzeyi (kenar tasi bu seviyede). Su y-depth..y-1."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    yb = y - depth - 1
    st.fill(b, x0, yb, z0, x1, y - 1, z1, lining)
    b.fill(x0 + 1, y - depth, z0 + 1, x1 - 1, y - 1, z1 - 1, "minecraft:water")
    b.fill(x0 + 1, y, z0 + 1, x1 - 1, y + 1, z1 - 1, AIR)
    ring = S.box(x0, y, z0, x1, y, z1) - S.box(x0 + 1, y, z0 + 1, x1 - 1, y, z1 - 1)
    ring.put_style(b, st, coping)
    if lights:
        lb = st.block("light_block")
        if not (_db().light[_db().id(lb)] >= 10):
            lb = "minecraft:sea_lantern"
        ly = y - 1 if depth == 1 else y - 2
        for xx in range(x0 + 2, x1 - 1, 3):
            for zz in (z0, z1):
                _light(b, xx, ly, zz, lb)
        for zz in range(z0 + 2, z1 - 1, 3):
            for xx in (x0, x1):
                _light(b, xx, ly, zz, lb)
    if steps and (x1 - x0) >= 5 and (z1 - z0) >= 3:
        zc0, zc1 = z0 + 1, min(z1 - 1, z0 + 3)
        for k in range(depth):
            for zz in range(zc0, zc1 + 1):
                b.set(x0 + 1 + k, y - 1 - k, zz, st.form(lining, "stairs", facing="west", half="bottom", waterlogged=True))
    return {"box": (x0, yb, z0, x1, y + 1, z1)}


@part("fountain", "Çeşme/şadırvan: sadirvan (sekizgen havuz, musluklu orta hazne, sütunlu geniş saçaklı külah, asma fener) ya da simple (yuvarlak havuz, kademeli taş kâse).")
def fountain(b, cx: int, y: int, cz: int, st: Style | None = None, kind: str = "simple", r: int = 3):
    """(cx, y, cz): y = zemin yuzeyi (havuz tabani bu seviyede, kenar y+1). r havuz yaricapi."""
    st = _st(st)
    r = max(2, int(r))
    edge = "water_edge"
    if kind == "simple":
        S.disk((cx, y, cz), r).put_style(b, st, edge)
        ring = S.ring((cx, y + 1, cz), r, r - 1, 1)
        ring.put_style(b, st, edge)
        _ring_stairs(b, st, cx, y + 1, cz, r + 1, r, edge, "bottom")
        water = S.disk((cx, y + 1, cz), r - 1) - S.box(cx, y + 1, cz, cx, y + 1, cz)
        water.put(b, "minecraft:water")
        b.set(cx, y + 1, cz, st.pick(edge, cx, y + 1, cz))
        b.set(cx, y + 2, cz, st.wall_of(edge))
        for d in DIRS:
            dx, _, dz = VEC[d]
            b.set(cx + dx, y + 3, cz + dz, st.stairs(edge, d, "top"))
        b.set(cx, y + 3, cz, st.pick(edge, cx, y + 3, cz))
        b.set(cx, y + 4, cz, "minecraft:water_cauldron[level=3]")
        return {"box": (cx - r - 1, y, cz - r - 1, cx + r + 1, y + 4, cz + r + 1)}
    if kind != "sadirvan":
        raise ValueError("kind: simple | sadirvan")
    R = r + 3
    S.disk((cx, y, cz), R).put_style(b, st, "paving")
    S.disk((cx, y, cz), r).put_style(b, st, edge)
    S.ring((cx, y + 1, cz), r, r - 1, 1).put_style(b, st, edge)
    _ring_stairs(b, st, cx, y + 1, cz, r + 1, r, edge, "bottom", inward=True)
    hz = S.disk((cx, y + 1, cz), 1)
    water = S.disk((cx, y + 1, cz), r - 1) - hz
    water.put(b, "minecraft:water")
    # orta hazne (sekizgen govde) + musluklar + kubbecik
    for yy in range(y + 1, y + 4):
        hz.moved(0, yy - (y + 1), 0).put_style(b, st, edge)
    for d in DIRS:
        dx, _, dz = VEC[d]
        b.set(cx + 2 * dx, y + 2, cz + 2 * dz, f"minecraft:lightning_rod[facing={d}]")
    _ring_stairs(b, st, cx, y + 4, cz, 1.5, 0, edge, "bottom")
    b.set(cx, y + 4, cz, st.pick(edge, cx, y + 4, cz))
    b.set(cx, y + 5, cz, st.wall_of(edge))
    # oturma taslari
    for d in DIRS:
        dx, _, dz = VEC[d]
        for k in (-1, 1):
            px, pz = abs(dz), abs(dx)
            b.set(cx + dx * (r + 2) + k * px * 2, y + 1, cz + dz * (r + 2) + k * pz * 2, st.slab(edge, "bottom"))
    # sutunlar (8) ve sacakli kulah
    ch = 5
    cr = r + 1
    pts = []
    for i in range(8):
        ang = 2 * math.pi * (i + 0.5) / 8
        px, pz = cx + int(round(math.cos(ang) * (cr + 0.6))), cz + int(round(math.sin(ang) * (cr + 0.6)))
        pts.append((px, pz))
    shaft = st.block("pillar")
    if "axis" in _db().props(shaft):
        shaft = _axis_log(shaft, "y")
    for (px, pz) in pts:
        b.set(px, y + 1, pz, st.pick("foundation", px, y + 1, pz))
        b.fill(px, y + 2, pz, px, y + ch - 1, pz, shaft)
        b.set(px, y + ch, pz, st.block("trim"))
    ty = y + ch + 1
    S.disk((cx, ty - 1, cz), cr + 1).put_style(b, st, "ceiling")
    sp = spire(b, cx, ty, cz, cr + 2, max(4, cr + 2), st, role="dome", flare=True, finial=True)
    b.fill(cx, ty - 2, cz, cx, ty - 2, cz, "minecraft:iron_chain[axis=y]")
    _light(b, cx, ty - 3, cz, st.light(hanging=True))
    return {"box": (cx - R - 1, y, cz - R - 1, cx + R + 1, sp["top"], cz + R + 1)}


# ====================================================================== BAHCE / PEYZAJ
def _plant_state(st: Style, x: int, y: int, z: int, seed: int = 0) -> list[tuple[int, str]]:
    """(dy, durum) listesi: cift bitkilerde iki yari, cicek tarhi icin dolgun petal miktari."""
    s = st.pick("plants", x + seed * 7, y, z)
    db = _db()
    pr = db.props(s)
    if "flower_amount" in pr:
        s = db.with_props(s, flower_amount="4")
    if "half" in pr:
        return [(0, db.with_props(s, half="lower")), (1, db.with_props(s, half="upper"))]
    return [(0, s)]


@part("garden_bed", "Çiçek tarhı: taş/ahşap kenarlı yükseltilmiş ya da zemine gömülü toprak, stile göre deterministik çiçek karışımı.")
def garden_bed(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, raised: bool = True,
               density: float = 0.7, seed: int = 0, edge_role: str = "foundation"):
    """y = zemin yuzeyi. raised: kenar + toprak y+1, bitkiler y+2; degilse toprak y, kenar y (gomme), bitkiler y+1."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    yl = y + 1 if raised else y
    ring = S.box(x0, yl, z0, x1, yl, z1) - S.box(x0 + 1, yl, z0 + 1, x1 - 1, yl, z1 - 1)
    if raised:
        ring.put_style(b, st, edge_role)
        for face, fx, fz, w in _sides(x0, z0, x1, z1):
            F = facade(b, face, fx, yl, fz, w)
            F.fill(0, 1, 0, w - 1, 1, 0, st.slab(edge_role, "bottom")) if False else None
    else:
        ring.put_style(b, st, "paving")
    soil = st.block("soil")
    b.fill(x0 + 1, yl, z0 + 1, x1 - 1, yl, z1 - 1, soil)
    if raised:
        b.fill(x0 + 1, y, z0 + 1, x1 - 1, y, z1 - 1, "minecraft:dirt")
    inner = S.box(x0 + 1, yl + 1, z0 + 1, x1 - 1, yl + 1, z1 - 1)
    C = inner.coords()
    u = S.hash01(C[:, 0], C[:, 1], C[:, 2], 1234 + seed)
    top = yl + 1
    for (X, Y, Z), uu in zip(C.tolist(), u.tolist()):
        if uu < density:
            for dy, s in _plant_state(st, X, Y, Z, seed):
                b.set(X, Y + dy, Z, s)
                top = max(top, Y + dy)
    return {"box": (x0, y if raised else y, z0, x1, top, z1)}


@part("hedge", "Budanmış çit bitkisi (yaprak, kalıcı): kutu/şerit; organic=True üst kenarı doğal dalgalı.")
def hedge(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, h: int = 2, organic: bool = False, seed: int = 0):
    """(x0..x1, z0..z1) taban, y = taban seviyesi (zeminin bir ustu), h yukseklik."""
    st = _st(st)
    sh = S.box(x0, y, z0, x1, y + h - 1, z1)
    if organic:
        sh = sh.where(lambda X, Y, Z: (Y < y + h - 1) | (S.noise(X, Y, Z, 3.0, seed) > 0.42))
    st.put(b, sh, "hedge")
    return {"box": _box((x0, y, z0), (x1, y + h - 1, z1))}


def _pts3(points, y):
    out = []
    for p in points:
        if len(p) == 2:
            out.append((float(p[0]), float(y), float(p[1])))
        else:
            out.append((float(p[0]), float(y), float(p[2])))
    return out


@part("path", "Yol: köşe noktalarından (ya da eğri) geçen dokulu yol, iki yanında bordür; Arnavut kaldırımı / toprak / taş.")
def path(b, points: Sequence[Sequence[int]], y: int, st: Style | None = None, w: int = 3, border: bool = True,
         curve: bool = False, role: str = "path", border_role: str = "paving"):
    """points: [(x,z), ...] (ya da (x,y,z)); y = zemin yuzeyi (yol bu seviyedeki zemini degistirir).
    curve=True: Catmull-Rom egrisi. w yol genisligi."""
    st = _st(st)
    P3 = _pts3(points, y)
    r = max(0.5, w / 2.0)
    sh = S.spline(P3, r=r) if (curve and len(P3) > 2) else S.polyline(P3, r=r)
    x0_, _, z0_, x1_, _, z1_ = sh.extent
    sh = sh.crop(x0_, y, z0_, x1_, y, z1_)
    st.put(b, sh, role)
    out = sh
    if border:
        bd = sh.dilate(1, axes="xz") - sh
        bd = bd.crop(bd.extent[0], y, bd.extent[2], bd.extent[3], y, bd.extent[5])
        st.put(b, bd, border_role)
        out = sh | bd
    bb = out.bbox
    return {"box": bb}


@part("stepping_stones", "Basamak taşları: çim üstünde eğri boyunca aralıklı yarım taşlar (Japon bahçesi, park).")
def stepping_stones(b, points: Sequence[Sequence[int]], y: int, st: Style | None = None, spacing: int = 2, role: str = "path",
                    seed: int = 0):
    """points: [(x,z)...]; y = zemin yuzeyi; taslar y+1'de alt yarim basamak (kabartma)."""
    st = _st(st)
    C = S.catmull_rom(_pts3(points, y), samples=16)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(C, axis=0), axis=1))]
    L = seg[-1]
    pts = []
    t = 0.0
    k = 0
    while t <= L + 1e-6:
        i = int(np.searchsorted(seg, t))
        i = min(max(i, 0), len(C) - 1)
        X, _, Z = C[i]
        X, Z = int(round(X)), int(round(Z))
        cells = [(X, Z)]
        if S.hash01(X, y, Z, seed)[()] < 0.4:
            cells.append((X + 1, Z) if k % 2 == 0 else (X, Z + 1))
        for (cx, cz) in cells:
            b.set(cx, y + 1, cz, st.pick_form(role, "slab", cx, y + 1, cz, type="bottom"))
            pts.append((cx, y + 1, cz))
        t += spacing + 1
        k += 1
    return {"box": _box(*pts) if pts else (0, y, 0, 0, y, 0)}


@part("fence_line", "Çit/duvar hattı: köşe noktalarından geçen çit, taş duvar, çit bitkisi; aralıklı babalar (bazıları fenerli) ve kapı.")
def fence_line(b, points: Sequence[Sequence[int]], y: int, st: Style | None = None, kind: str = "fence", post_every: int = 4,
               gate_at: Sequence[int] | None = None, gate_w: int = 1, lights: bool = True):
    """points: [(x,z)...] eksene paralel parcalar onerilir; y = taban (zeminin bir ustu). kind: fence | wall | hedge.
    gate_at: (x,z) kapi hucresi (hat uzerinde)."""
    st = _st(st)
    P3 = _pts3(points, y)
    sh = S.polyline(P3, r=0.5)
    sh = sh.crop(sh.extent[0], y, sh.extent[2], sh.extent[3], y, sh.extent[5])
    C = [tuple(c) for c in sh.coords().tolist()]
    # sira: noktalar boyunca yaklasik dizilim (koseler baba olsun)
    corners = {(int(round(p[0])), int(round(p[2]))) for p in P3}
    gate_cells = set()
    if gate_at is not None:
        gx, gz = int(gate_at[0]), int(gate_at[-1])
        gate_cells = {(gx, gz)}
        if gate_w >= 2:
            if (gx + 1, y, gz) in set(C):
                gate_cells.add((gx + 1, gz))
            elif (gx, y, gz + 1) in set(C):
                gate_cells.add((gx, gz + 1))
    top = y
    if kind == "hedge":
        for (X, Y, Z) in C:
            if (X, Z) in gate_cells:
                continue
            b.set(X, Y, Z, st.pick("hedge", X, Y, Z))
            b.set(X, Y + 1, Z, st.pick("hedge", X, Y + 1, Z))
        top = y + 1
    else:
        rail = st.fence("fence") if kind == "fence" else st.wall_of("foundation")
        cs = set(C)
        for (X, Y, Z) in C:
            if (X, Z) in gate_cells:
                continue
            b.set(X, Y, Z, rail)
        # babalar
        posts = []
        for idx, (X, Y, Z) in enumerate(sorted(C, key=lambda c: (c[0], c[2]))):
            if (X, Z) in gate_cells:
                continue
            nbx = ((X + 1, Y, Z) in cs) + ((X - 1, Y, Z) in cs)
            nbz = ((X, Y, Z + 1) in cs) + ((X, Y, Z - 1) in cs)
            is_corner = (X, Z) in corners or (nbx and nbz) or (nbx + nbz) <= 1
            along = X if nbx else Z
            if is_corner or along % post_every == 0:
                posts.append((X, Y, Z))
        for i, (X, Y, Z) in enumerate(posts):
            if kind == "fence":
                col = st.block("pillar") if _is_wood(st, "pillar") else st.block("beam")
                b.set(X, Y, Z, _axis_log(col, "y"))
                if lights and i % 2 == 0:
                    _light(b, X, Y + 1, Z, st.light(False))
                    top = max(top, y + 1)
            else:
                st.set(b, X, Y, Z, "foundation")
                st.set(b, X, Y + 1, Z, "foundation")
                if lights and i % 2 == 0:
                    b.set(X, Y + 2, Z, st.block("detail") if st.base("detail") != "sea_lantern" else st.block("trim"))
                    _light(b, X, Y + 3, Z, st.light(False))
                    top = max(top, y + 3)
                else:
                    b.set(X, Y + 2, Z, st.slab("foundation", "bottom"))
                    top = max(top, y + 2)
        for (gx, gz) in gate_cells:
            horiz = ((gx + 1, y, gz) in cs) or ((gx - 1, y, gz) in cs)
            fc = "south" if horiz else "east"
            b.set(gx, y, gz, st.gate("fence", fc, False))
    bb = sh.bbox
    return {"box": (bb[0], y, bb[2], bb[3], top, bb[5])}


@part("gate", "Bahçe kapısı: iki taş baba (başlıklı, fenerli), çit kanatları; arch=True üstte kirişli küçük çatı (kapı saçağı).")
def gate(b, x: int, y: int, z: int, face: str = "north", w: int = 2, st: Style | None = None, arch: bool = False,
         lights: bool = True):
    """(x,y,z) kapi acikliginin en kucuk alt hucresi (hat duzleminde), y = zemin + 1."""
    st = _st(st)
    F = facade(b, face, x, y, z, w)
    for u in (-1, w):
        F.sfill(st, "foundation", u, 0, 0, u, 2, 0)
        F.set(u, 3, 0, st.block("detail") if st.base("detail") != "sea_lantern" else st.block("trim"))
    F.fill(0, 0, 0, w - 1, 0, 0, st.gate("fence", IN, False))
    top = 3
    if lights and not arch:
        for u in (-1, w):
            X, Y, Z = F.xyz(u, 4, 0)
            _light(b, X, Y, Z, st.light(False))
        top = 4
    if arch:
        F.fill(-2, 4, 0, w + 1, 4, 0, _axis_log(st.block("beam"), "x"))
        F.fill(-2, 5, 1, w + 1, 5, 1, st.stairs("roof", IN, "bottom"))
        F.fill(-2, 5, -1, w + 1, 5, -1, st.stairs("roof", OUT, "bottom"))
        F.fill(-2, 5, 0, w + 1, 5, 0, st.block("roof_trim"))
        F.fill(-2, 6, 0, w + 1, 6, 0, st.slab("roof", "bottom"))
        if lights:
            X, Y, Z = F.xyz((w - 1) // 2, 3, 0)
            _light(b, X, Y, Z, st.light(True))
        top = 6
        return {"box": F.box(-2, 0, -1, w + 1, top, 1)}
    return {"box": F.box(-1, 0, 0, w, top, 0)}


@part("tree", "Süs ağacı (kalıcı yapraklı): round (yuvarlak taç), conifer (çam), cypress (servi), blossom (kiraz), olive (zeytin), palm (palmiye).")
def tree(b, x: int, y: int, z: int, st: Style | None = None, kind: str = "round", h: int | None = None, seed: int = 0):
    """(x,y,z) govdenin tabani (zemin + 1). Agaclar dogal malzemeyle: tur kendi odun/yapragini secer."""
    mats = {"round": ("oak_log", "oak_leaves"), "conifer": ("spruce_log", "spruce_leaves"), "cypress": ("spruce_log", "spruce_leaves"),
            "blossom": ("cherry_log", "cherry_leaves"), "olive": ("dark_oak_log", "pale_oak_leaves"),
            "palm": ("jungle_log", "jungle_leaves"), "birch": ("birch_log", "birch_leaves")}
    if kind not in mats:
        raise ValueError(f"kind: {', '.join(mats)}")
    log, lv = mats[kind]
    leaves = f"minecraft:{lv}[persistent=true]"
    logy = f"minecraft:{log}[axis=y]"
    rnd = lambda k: float(S.hash01(x + k, y, z, seed + 77)[()])  # noqa: E731
    pts = [(x, y, z)]
    if kind == "round" or kind == "blossom" or kind == "birch":
        h = int(h or 6 + int(rnd(1) * 3))
        b.fill(x, y, z, x, y + h - 2, z, logy)
        cr = 2.6 + rnd(2) * 1.2
        canopy = S.blob((x, y + h - 1, z), cr, rough=0.3, seed=seed, squash=0.8)
        st_ = _style.get("medieval").override(hedge=[(lv, 1.0)])
        canopy.put(b, leaves, only_empty=True)
        for k, (dx, dz) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
            if rnd(10 + k) < 0.55:
                b.line((x, y + h - 3, z), (x + 2 * dx, y + h - 1, z + 2 * dz), f"minecraft:{log}[axis={'x' if dx else 'z'}]")
        bb = canopy.bbox
        pts += [(bb[0], bb[1], bb[2]), (bb[3], bb[4], bb[5])]
    elif kind == "conifer":
        h = int(h or 9 + int(rnd(1) * 4))
        b.fill(x, y, z, x, y + h - 1, z, logy)
        radii = []
        for i in range(h - 1):
            t = i / max(1, h - 2)
            base = 3.2 * (1 - t) + 0.3
            radii.append(base * (0.75 if i % 2 else 1.0) if i >= 2 else -1)
        cone = S.revolve((x, y, z), radii + [0])
        cone.put(b, leaves, only_empty=True)
        b.set(x, y + h, z, leaves)
        pts += [(x - 4, y, z - 4), (x + 4, y + h, z + 4)]
    elif kind == "cypress":
        h = int(h or 9 + int(rnd(1) * 4))
        b.fill(x, y, z, x, y + h - 3, z, logy)
        body = S.ellipsoid((x, y + h / 2.0 + 0.5, z), 1.3, h / 2.0, 1.3)
        body = body.where(lambda X, Y, Z: Y >= y + 1)
        body.put(b, leaves, only_empty=True)
        bb = body.bbox
        pts += [(bb[0], bb[1], bb[2]), (bb[3], bb[4], bb[5])]
    elif kind == "olive":
        h = int(h or 4 + int(rnd(1) * 2))
        b.fill(x, y, z, x, y + 1, z, logy)
        b.line((x, y + 2, z), (x + 1, y + h - 1, z), "minecraft:dark_oak_log[axis=y]")
        b.line((x, y + 2, z), (x - 1, y + h - 1, z + 1), "minecraft:dark_oak_log[axis=y]")
        canopy = S.blob((x, y + h, z), 2.6, rough=0.4, seed=seed, squash=0.6)
        canopy.put(b, leaves, only_empty=True)
        bb = canopy.bbox
        pts += [(bb[0], bb[1], bb[2]), (bb[3], bb[4], bb[5])]
    elif kind == "palm":
        h = int(h or 8 + int(rnd(1) * 3))
        lean = 1 if rnd(3) < 0.5 else -1
        top = (x + lean, y + h - 1, z)
        b.line((x, y, z), (x, y + h // 2, z), logy)
        b.line((x, y + h // 2, z), top, logy)
        tx, ty, tz = top
        b.set(tx, ty + 1, tz, leaves)
        for (dx, dz) in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            L = 3 if dx and dz else 4
            for k in range(1, L + 1):
                b.set(tx + dx * k, ty + (1 if k < 2 else 0) - (1 if k == L else 0), tz + dz * k, leaves)
        pts += [(tx - 4, y, tz - 4), (tx + 4, ty + 1, tz + 4)]
    return {"box": _box(*pts)}


@part("planter", "Saksı/ekici: pot (çiçekli saksı), box (kenarlı toprak + çalı), urn (süslü küp), tree (saksıda küçük ağaç), topiary (kesme top).")
def planter(b, x: int, y: int, z: int, st: Style | None = None, kind: str = "pot", seed: int = 0):
    """(x,y,z) ekicinin tabani (zemin + 1 ya da teras dosemesi + 1)."""
    st = _st(st)
    pots = ["potted_red_tulip", "potted_azure_bluet", "potted_allium", "potted_fern", "potted_white_tulip",
            "potted_oxeye_daisy", "potted_azalea_bush", "potted_flowering_azalea_bush", "potted_cornflower"]
    if kind == "pot":
        i = int(S.hash01(x, y, z, seed)[()] * len(pots))
        b.set(x, y, z, "minecraft:" + pots[i])
        return {"box": (x, y, z, x, y, z)}
    if kind == "urn":
        b.set(x, y, z, st.pick("foundation", x, y, z))
        b.set(x, y + 1, z, "minecraft:decorated_pot")
        return {"box": (x, y, z, x, y + 1, z)}
    if kind == "box":
        b.set(x, y, z, "minecraft:rooted_dirt")
        for d in DIRS:
            dx, _, dz = VEC[d]
            b.set(x + dx, y, z + dz, st.trapdoor(d, "bottom", True))
        b.set(x, y + 1, z, "minecraft:flowering_azalea" if S.hash01(x, y, z, seed)[()] < 0.5 else "minecraft:azalea")
        return {"box": (x - 1, y, z - 1, x + 1, y + 1, z + 1)}
    if kind in ("tree", "topiary"):
        b.set(x, y, z, st.pick("foundation", x, y, z))
        for d in DIRS:
            dx, _, dz = VEC[d]
            b.set(x + dx, y, z + dz, st.stairs("foundation", OPP[d], "bottom"))
        b.set(x, y + 1, z, "minecraft:spruce_log[axis=y]" if kind == "topiary" else "minecraft:oak_log[axis=y]")
        if kind == "topiary":
            b.fill(x, y + 2, z, x, y + 2, z, "minecraft:spruce_log[axis=y]")
            S.sphere((x, y + 4, z), 1.4).put(b, "minecraft:spruce_leaves[persistent=true]", only_empty=True)
            return {"box": (x - 2, y, z - 2, x + 2, y + 6, z + 2)}
        S.blob((x, y + 3, z), 1.6, rough=0.25, seed=seed).put(b, "minecraft:azalea_leaves[persistent=true]", only_empty=True)
        return {"box": (x - 3, y, z - 3, x + 3, y + 6, z + 3)}
    raise ValueError("kind: pot | box | urn | tree | topiary")


@part("well", "Kuyu: taş bilezik, su dolu kapalı kuyu gövdesi, iki dikme, makaralı kiriş, zincir ve küçük beşik çatı.")
def well(b, x: int, y: int, z: int, st: Style | None = None):
    """(x,y,z): y = zemin yuzeyi; (x,z) 2x2 su agzinin en kucuk kosesi. Bilezik y+1, su y-2..y."""
    st = _st(st)
    st.fill(b, x - 1, y - 3, z - 1, x + 2, y, z + 2, "foundation")
    b.fill(x, y - 2, z, x + 1, y, z + 1, "minecraft:water")
    ring = S.box(x - 1, y + 1, z - 1, x + 2, y + 1, z + 2) - S.box(x, y + 1, z, x + 1, y + 1, z + 1)
    ring.put_style(b, st, "foundation")
    post = st.fence("fence")
    for (px, pz) in ((x - 1, z), (x + 2, z)):
        b.fill(px, y + 2, pz, px, y + 3, pz, post)
    b.fill(x - 1, y + 4, z, x + 2, y + 4, z, _axis_log(st.block("beam"), "x"))
    b.set(x, y + 3, z, "minecraft:iron_chain[axis=y]")
    b.fill(x - 2, y + 4, z - 1, x + 3, y + 4, z - 1, st.stairs("roof", "south", "bottom"))
    b.fill(x - 2, y + 4, z + 1, x + 3, y + 4, z + 1, st.stairs("roof", "north", "bottom"))
    b.fill(x - 2, y + 5, z, x + 3, y + 5, z, st.slab("roof", "bottom"))
    return {"box": (x - 2, y - 3, z - 1, x + 3, y + 5, z + 2)}


@part("pergola", "Çardak/pergola: kütük dikmeler, boyuna kirişler, enine latalar, üstte yer yer sarmaşık-yaprak (begonvil), asma fener.")
def pergola(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, h: int = 3, every: int = 3,
            greenery: bool = True, seed: int = 0):
    """(x0..x1, z0..z1) dis olcu; y = zemin + 1 (dikme tabani); kirişler y+h'de, latalar y+h+1'de."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    along_x = (x1 - x0) >= (z1 - z0)
    beam = st.block("beam")
    logy = _axis_log(beam, "y")
    a0, a1 = (x0, x1) if along_x else (z0, z1)
    posts = sorted({a0, a1, *range(a0, a1 + 1, every)})
    for a in posts:
        for c in ((z0, z1) if along_x else (x0, x1)):
            X, Z = (a, c) if along_x else (c, a)
            b.fill(X, y, Z, X, y + h - 1, Z, logy)
    for c in ((z0, z1) if along_x else (x0, x1)):
        if along_x:
            b.fill(x0 - 1, y + h, c, x1 + 1, y + h, c, _axis_log(beam, "x"))
        else:
            b.fill(c, y + h, z0 - 1, c, y + h, z1 + 1, _axis_log(beam, "z"))
    for a in range(a0, a1 + 1, 2):
        if along_x:
            b.fill(a, y + h + 1, z0 - 1, a, y + h + 1, z1 + 1, _axis_log(beam, "z"))
        else:
            b.fill(x0 - 1, y + h + 1, a, x1 + 1, y + h + 1, a, _axis_log(beam, "x"))
    top = y + h + 1
    if greenery:
        roof = S.box(x0 - 1, y + h + 2, z0 - 1, x1 + 1, y + h + 2, z1 + 1)
        roof = roof.where(lambda X, Y, Z: S.noise(X, Y, Z, 2.5, seed) > 0.55)
        if not roof.empty():
            st.put(b, roof, "hedge")
            top = y + h + 2
    cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
    if along_x:
        cx = cx - (cx - a0) % 2
    else:
        cz = cz - (cz - a0) % 2
    _light(b, cx, y + h, cz, st.light(True))
    return {"box": (x0 - 1, y, z0 - 1, x1 + 1, top, z1 + 1)}


@part("bench", "Bank: oturak merdiven sırası, iki uçta kolçak (açık tuzak kapı); taş ya da ahşap.")
def bench(b, x: int, y: int, z: int, facing: str = "north", st: Style | None = None, length: int = 3, role: str = "trim"):
    """(x,y,z) bankin bir ucu; banka oturan facing yonune bakar; bank oturanin sagina dogru (facing'in saat yonu) uzar."""
    st = _st(st)
    sd = VEC[CW[facing]]
    pts = []
    for k in range(length):
        X, Z = x + sd[0] * k, z + sd[2] * k
        b.set(X, y, Z, st.stairs(role, OPP[facing], "bottom"))
        pts.append((X, y, Z))
    lx, lz = x - sd[0], z - sd[2]
    rx, rz = x + sd[0] * length, z + sd[2] * length
    b.set(lx, y, lz, st.trapdoor(CCW[facing], "bottom", True, role="shutter"))
    b.set(rx, y, rz, st.trapdoor(CW[facing], "bottom", True, role="shutter"))
    pts += [(lx, y, lz), (rx, y, rz)]
    return {"box": _box(*pts)}


@part("flagpole", "Bayrak direği: taş kaide, ince direk (demir parmaklık/çit), tepe alemi, direğe asılı flama (duvar bayrağı).")
def flagpole(b, x: int, y: int, z: int, st: Style | None = None, h: int = 9, color: str = "red", side: str = "east"):
    """(x,y,z) direk tabani (zemin + 1). Flama direğin `side` tarafinda, tepeye yakin asilir."""
    st = _st(st)
    st.fill(b, x - 1, y, z - 1, x + 1, y, z + 1, "foundation")
    for d in DIRS:
        dx, _, dz = VEC[d]
        b.set(x + dx * 2, y, z + dz * 2, st.stairs("foundation", OPP[d], "bottom"))
    b.set(x, y + 1, z, st.wall_of("foundation"))
    pole = "minecraft:iron_bars" if not _is_wood(st, "fence") or st.has("flat_roof") else st.fence("fence")
    b.fill(x, y + 2, z, x, y + h, z, pole)
    b.set(x, y + h + 1, z, "minecraft:lightning_rod[facing=up]")
    d = VEC[side]
    db = _db()
    ban = f"minecraft:{color}_wall_banner"
    if not db.has_block(ban):
        ban = "minecraft:red_wall_banner"
    b.set(x + d[0], y + h - 1, z + d[2], f"{ban}[facing={side}]")
    return {"box": (x - 2, y, z - 2, x + 2, y + h + 1, z + 2)}


@part("awning", "Tente: çizgili yün merdivenlerle eğimli saçak + sarkan pervaz (dükkân, kafe, pazar).")
def awning(b, x: int, y: int, z: int, face: str = "north", w: int = 3, st: Style | None = None, depth: int = 2,
           colors: Sequence[str] = ("red", "white")):
    """(x,y,z) duvar duzleminde tentenin bagli oldugu en ust sira, en kucuk uc; depth kadar disa ve asagi iner."""
    F = facade(b, face, x, y, z, w)
    db = _db()
    for n in range(1, depth + 1):
        for u in range(w):
            c = colors[u % len(colors)]
            s = f"minecraft:{c}_wool_stairs" if db.has_block(f"{c}_wool_stairs") else "minecraft:red_wool_stairs"
            F.set(u, -(n - 1), n, f"{s}[facing=south,half=bottom]")
    for u in range(w):
        c = colors[u % len(colors)]
        F.set(u, -depth, depth, f"minecraft:{c}_wool_slab[type=top]" if db.has_block(f"{c}_wool_slab") else "minecraft:red_wool_slab[type=top]")
    return {"box": F.box(0, -depth, 1, w - 1, 0, depth)}


# ====================================================================== AYDINLATMA
@part("lamp_post", "Sokak/bahçe lambası: crook (kollu, asılı fener), top (direk üstü fener), modern (ışık bloğu + şapka), toro (Japon taş feneri).")
def lamp_post(b, x: int, y: int, z: int, st: Style | None = None, h: int = 4, kind: str | None = None, arm: str = "east"):
    """(x,y,z) direk tabani (zemin + 1). Destekler her zaman gecerli: fener alttan dikmeye ya da ustten kola dayanir."""
    st = _st(st)
    if kind is None:
        kind = "modern" if (st.has("flat_roof") or st.has("glass_curtain")) else ("toro" if st.has("toro") else "crook")
    if kind == "toro":
        b.set(x, y, z, st.pick("foundation", x, y, z))
        b.set(x, y + 1, z, st.wall_of("foundation"))
        _light(b, x, y + 2, z, st.light(False))
        b.set(x, y + 3, z, st.pick("foundation", x, y + 3, z))
        for d in DIRS:
            dx, _, dz = VEC[d]
            b.set(x + dx, y + 3, z + dz, st.stairs("foundation", OPP[d], "bottom"))
        b.set(x, y + 4, z, st.wall_of("foundation"))
        return {"box": (x - 1, y, z - 1, x + 1, y + 4, z + 1)}
    if kind == "modern":
        post = st.wall_of("frame") if not _is_wood(st, "frame") else st.fence("frame")
        b.set(x, y, z, st.pick("foundation", x, y, z))
        b.fill(x, y + 1, z, x, y + h - 2, z, post)
        lb = st.block("light_block")
        _light(b, x, y + h - 1, z, lb)
        b.set(x, y + h, z, st.slab("frame", "bottom"))
        return {"box": (x, y, z, x, y + h, z)}
    post = st.fence("fence")
    b.set(x, y, z, st.pick("foundation", x, y, z))
    b.fill(x, y + 1, z, x, y + h - 1, z, post)
    if kind == "top":
        _light(b, x, y + h, z, st.light(False))
        return {"box": (x, y, z, x, y + h, z)}
    if kind != "crook":
        raise ValueError("kind: crook | top | modern | toro")
    d = VEC[arm]
    ax, az = x + d[0], z + d[2]
    b.set(ax, y + h - 1, az, post)
    b.set(x, y + h, z, st.slab("trim", "bottom"))
    b.set(ax, y + h, az, st.slab("trim", "bottom"))
    _light(b, ax, y + h - 2, az, st.light(True))
    return {"box": _box((x, y, z), (ax, y + h, az))}


@part("wall_lamp", "Duvar lambası: lantern (çit kol + asılı fener), sconce (basamak raf + fener + şapka), torch (duvar meşalesi), modern (end_rod).")
def wall_lamp(b, x: int, y: int, z: int, face: str = "north", st: Style | None = None, kind: str | None = None):
    """(x,y,z) lambanin tutundugu DUVAR blogu; lamba onun disinda (n=+1) durur."""
    st = _st(st)
    if kind is None:
        kind = "modern" if (st.has("flat_roof") or st.has("glass_curtain")) else "lantern"
    F = Frame(b, face, (x, y, z))
    if kind == "lantern":
        F.set(0, 1, 1, st.fence("fence"))
        X, Y, Z = F.xyz(0, 0, 1)
        _light(b, X, Y, Z, st.light(True))
        return {"box": F.box(0, 0, 1, 0, 1, 1)}
    if kind == "sconce":
        F.set(0, -1, 1, st.slab("trim", "top"))
        X, Y, Z = F.xyz(0, 0, 1)
        _light(b, X, Y, Z, st.light(False))
        F.set(0, 1, 1, st.trapdoor(OUT, "top", False))
        return {"box": F.box(0, -1, 1, 0, 1, 1)}
    if kind == "torch":
        X, Y, Z = F.xyz(0, 0, 1)
        _light(b, X, Y, Z, F.s("minecraft:wall_torch[facing=north]"))
        return {"box": F.box(0, 0, 1, 0, 0, 1)}
    if kind == "modern":
        X, Y, Z = F.xyz(0, 0, 1)
        _light(b, X, Y, Z, F.s("minecraft:end_rod[facing=north]"))
        return {"box": F.box(0, 0, 1, 0, 0, 1)}
    raise ValueError("kind: lantern | sconce | torch | modern")


@part("hanging_lamp", "Asma fener: tavandan zincirle sarkan fener (destek: zincir/tavan).")
def hanging_lamp(b, x: int, y: int, z: int, st: Style | None = None, length: int = 1):
    """(x,y,z) TAVAN blogu (destek); zincir y-1..y-length, fener y-length-1."""
    st = _st(st)
    for k in range(1, length + 1):
        b.set(x, y - k, z, "minecraft:iron_chain[axis=y]")
    _light(b, x, y - length - 1, z, st.light(True))
    return {"box": (x, y - length - 1, z, x, y - 1, z)}


@part("chandelier", "Avize: zincir, çit kollu göbek, kol uçlarında ve ortada asılı fenerler (r=1 artı, r=2 geniş).")
def chandelier(b, x: int, y: int, z: int, st: Style | None = None, r: int = 1, drop: int = 1):
    """(x,y,z) TAVAN blogu; zincir drop kadar iner, gobek y-drop-1, fenerler y-drop-2."""
    st = _st(st)
    for k in range(1, drop + 1):
        b.set(x, y - k, z, "minecraft:iron_chain[axis=y]")
    hy = y - drop - 1
    post = st.fence("fence")
    b.set(x, hy, z, post)
    ly = hy - 1
    _light(b, x, ly, z, st.light(True))
    for d in DIRS:
        dx, _, dz = VEC[d]
        for k in range(1, r + 1):
            b.set(x + dx * k, hy, z + dz * k, post)
        _light(b, x + dx * r, ly, z + dz * r, st.light(True))
    return {"box": (x - r, ly, z - r, x + r, y - 1, z + r)}


# ====================================================================== IC MEKAN
@part("floor_pattern", "Desenli döşeme: checker (dama), herringbone (balıksırtı kütük), border (bordürlü), diagonal, medallion (Osmanlı göbek), planks (iki ahşap şerit).")
def floor_pattern(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, kind: str = "border"):
    """y = doseme blogu seviyesi."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    X, Y, Z = S.grid(x0, y, z0, x1, y, z1)
    shape = (1, z1 - z0 + 1, x1 - x0 + 1)
    base = S.box(x0, y, z0, x1, y, z1)
    if kind == "checker":
        m = np.broadcast_to(((X + Z) % 2) == 0, shape)
    elif kind == "diagonal":
        m = np.broadcast_to(((X + Z) % 4) == 0, shape)
    elif kind == "planks":
        m = np.broadcast_to(((Z if (x1 - x0) >= (z1 - z0) else X) % 2) == 0, shape)
    elif kind == "border":
        m = np.broadcast_to((X == x0) | (X == x1) | (Z == z0) | (Z == z1) | (X == x0 + 2) & (Z >= z0 + 2) & (Z <= z1 - 2)
                            | (X == x1 - 2) & (Z >= z0 + 2) & (Z <= z1 - 2) | (Z == z0 + 2) & (X >= x0 + 2) & (X <= x1 - 2)
                            | (Z == z1 - 2) & (X >= x0 + 2) & (X <= x1 - 2), shape)
    elif kind == "medallion":
        cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        dd = np.abs(X - cx) + np.abs(Z - cz)
        m = np.broadcast_to((X == x0) | (X == x1) | (Z == z0) | (Z == z1) | ((np.floor(dd) % 3) == 0) & (dd <= min(x1 - x0, z1 - z0) / 2.0), shape)
    elif kind == "herringbone":
        w = _style.wood_of(st.base("floor"))
        if w and _db().has_block(f"stripped_{w}_log"):
            lx = f"minecraft:stripped_{w}_log[axis=x]"
            lz = f"minecraft:stripped_{w}_log[axis=z]"
        elif w == "bamboo":
            lx = lz = "minecraft:stripped_bamboo_block[axis=x]"
        else:
            lx = lz = None
        m = np.broadcast_to(((X - Z) % 4) < 2, shape)
        if lx:
            S.Shape(m.copy(), (x0, y, z0)).put(b, lx)
            S.Shape(~m, (x0, y, z0)).put(b, lz)
            return {"box": (x0, y, z0, x1, y, z1)}
    else:
        raise ValueError("kind: checker|herringbone|border|diagonal|medallion|planks")
    mm = S.Shape(m.copy(), (x0, y, z0))
    st.put(b, base - mm, "floor")
    st.put(b, mm, "floor_alt" if kind != "medallion" else "floor_alt")
    if kind == "medallion":
        cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
        b.set(cx, y, cz, st.block("tile"))
    return {"box": (x0, y, z0, x1, y, z1)}


@part("ceiling", "Tavan: dokulu tavan, kısa açıklık boyunca kütük kirişler, aralarda gömme ışık; medallion=True Osmanlı göbek + avize.")
def ceiling(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None, beams: bool = True, lights: bool = True,
            every: int = 3, medallion: bool = False):
    """y = tavan blogu seviyesi; kirişler y-1'de (tavandan sarkar)."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    st.fill(b, x0, y, z0, x1, y, z1, "ceiling")
    along_x = (x1 - x0) >= (z1 - z0)
    lo = y
    beam = st.block("beam")
    gaps = []
    if beams:
        rng = range(x0 + every, x1, every) if along_x else range(z0 + every, z1, every)
        prev = x0 if along_x else z0
        for a in rng:
            if along_x:
                b.fill(a, y - 1, z0, a, y - 1, z1, _axis_log(beam, "z"))
            else:
                b.fill(x0, y - 1, a, x1, y - 1, a, _axis_log(beam, "x"))
            gaps.append((prev, a))
            prev = a
        gaps.append((prev, x1 if along_x else z1))
        lo = y - 1
    if lights:
        lb = st.block("light_block")
        if beams:
            for i, (a, c) in enumerate(gaps):
                if i % 2 == 0 and c - a >= 2:
                    m = (a + c) // 2
                    X, Z = (m, (z0 + z1) // 2) if along_x else ((x0 + x1) // 2, m)
                    _light(b, X, y, Z, lb)
        else:
            for xx in range(x0 + 2, x1 - 1, 4):
                for zz in range(z0 + 2, z1 - 1, 4):
                    _light(b, xx, y, zz, lb)
    if medallion:
        cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
        for (dx, dz) in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
            b.set(cx + dx, y, cz + dz, st.block("tile"))
        for (dx, dz) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            b.set(cx + dx, y, cz + dz, st.block("accent"))
        chandelier(b, cx, y, cz, st, r=1, drop=1)
        lo = min(lo, y - 3)
    return {"box": (x0 - (1 if medallion else 0), lo, z0 - (1 if medallion else 0), x1 + (1 if medallion else 0), y, z1 + (1 if medallion else 0))}


@part("rug", "Halı/kilim: bordür, zemin ve ortada eşkenar dörtgen göbek motifi (halı katmanı).")
def rug(b, x0: int, y: int, z0: int, x1: int, z1: int, st: Style | None = None,
        colors: Sequence[str] | None = None):
    """y = hali katmani (doseme + 1). colors: (zemin, bordur, motif) renk adlari."""
    st = _st(st)
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    if colors is None:
        base = st.base("carpet").replace("_carpet", "")
        colors = (base, "white" if base not in ("white",) else "light_gray", "black" if base in ("red", "brown") else "blue")
    field_c, border_c, motif_c = colors
    cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
    rad = min(x1 - x0, z1 - z0) / 2.0 - 1
    for X in range(x0, x1 + 1):
        for Z in range(z0, z1 + 1):
            c = field_c
            if X in (x0, x1) or Z in (z0, z1):
                c = border_c
            elif abs(X - cx) + abs(Z - cz) <= rad and (int(abs(X - cx) + abs(Z - cz)) % 2 == 0):
                c = motif_c
            b.set(X, y, Z, f"minecraft:{c}_carpet")
    return {"box": (x0, y, z0, x1, y, z1)}


@part("table", "Masa: 1x1 dikme+basınç plakası; daha büyükte kenarı ters merdiven profilli üst tabla.")
def table(b, x0: int, y: int, z0: int, x1: int | None = None, z1: int | None = None, st: Style | None = None, role: str = "trim"):
    """(x0..x1, z0..z1) masa ustu (y = doseme + 1)."""
    st = _st(st)
    x1 = x0 if x1 is None else x1
    z1 = z0 if z1 is None else z1
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    if x0 == x1 and z0 == z1:
        b.set(x0, y, z0, st.fence("fence"))
        b.set(x0, y + 1, z0, st.form("fence", "pressure_plate"))
        return {"box": (x0, y, z0, x0, y + 1, z0)}
    for X in range(x0, x1 + 1):
        for Z in range(z0, z1 + 1):
            if X in (x0, x1) and x1 > x0:
                b.set(X, y, Z, st.stairs(role, "west" if X == x0 else "east", "top"))
            elif Z in (z0, z1) and z1 > z0:
                b.set(X, y, Z, st.stairs(role, "north" if Z == z0 else "south", "top"))
            else:
                b.set(X, y, Z, st.slab(role, "top"))
    return {"box": (x0, y, z0, x1, y, z1)}


@part("chair", "Sandalye: oturak merdiven + iki yanda kolçak (açık tuzak kapı).")
def chair(b, x: int, y: int, z: int, facing: str = "north", st: Style | None = None, arms: bool = True, role: str = "trim"):
    """(x,y,z) oturak; oturan facing yonune bakar."""
    st = _st(st)
    b.set(x, y, z, st.stairs(role, OPP[facing], "bottom"))
    pts = [(x, y, z)]
    if arms:
        for side in (CW[facing], CCW[facing]):
            d = VEC[side]
            b.set(x + d[0], y, z + d[2], st.trapdoor(side, "bottom", True))
            pts.append((x + d[0], y, z + d[2]))
    return {"box": _box(*pts)}


@part("bed", "Yatak: baş ve ayak yarıları doğru yönde (facing = ayaktan başa).")
def bed(b, x: int, y: int, z: int, facing: str = "north", color: str = "red"):
    """(x,y,z) yatagin BAS hucresi; ayak = bas - facing yonu."""
    d = VEC[facing]
    db = _db()
    n = f"{color}_bed" if db.has_block(f"{color}_bed") else "red_bed"
    b.set(x, y, z, f"minecraft:{n}[facing={facing},part=head]")
    b.set(x - d[0], y, z - d[2], f"minecraft:{n}[facing={facing},part=foot]")
    return {"box": _box((x, y, z), (x - d[0], y, z - d[2]))}


@part("sedir", "Osmanlı sedir/divan: duvar boyunca yünlü minder oturak (sırt duvara dayalı), uçlarda kolçak, önde halı.")
def sedir(b, x: int, y: int, z: int, face: str = "north", length: int = 4, st: Style | None = None, color: str = "red",
          carpet: bool = True):
    """(x,y,z) duvarin IC yuzune bitisik ilk oturak hucresi (y = doseme + 1); face = duvarin dis yuzunun baktigi yon
    (sedir duvardan iceri bakar). length duvar boyunca (+x ya da +z)."""
    st = _st(st)
    db = _db()
    F = facade(b, face, x, y, z, length)
    seat = f"minecraft:{color}_wool_stairs" if db.has_block(f"{color}_wool_stairs") else "minecraft:red_wool_stairs"
    F.fill(0, 0, 0, length - 1, 0, 0, seat + "[facing=north,half=bottom]")
    F.set(-1, 0, 0, st.trapdoor(L, "bottom", True))
    F.set(length, 0, 0, st.trapdoor(R, "bottom", True))
    if carpet:
        F.fill(0, -1 + 1, -1, length - 1, 0, -1, f"minecraft:{st.base('carpet')}" if st.base("carpet").endswith("_carpet") else "minecraft:red_carpet")
    return {"box": F.box(-1, 0, -1 if carpet else 0, length, 0, 0)}


@part("bookcase", "Kitaplık duvarı: ahşap çerçeve içinde kitaplık ve oyma kitaplıklar, üst korniş.")
def bookcase(b, x: int, y: int, z: int, face: str = "north", length: int = 4, h: int = 3, st: Style | None = None):
    """(x,y,z) kitapligin duvarin IC yuzune bitisik en kucuk alt hucresi; face = duvarin dis yonu."""
    st = _st(st)
    F = facade(b, face, x, y, z, length)
    for u in range(length):
        for v in range(h):
            Xb, Yb, Zb = F.xyz(u, v, 0)
            k = float(S.hash01(Xb, Yb, Zb, 5)[()])
            if u in (0, length - 1):
                F.sset(st, "frame", u, v, 0)
            else:
                F.set(u, v, 0, "minecraft:chiseled_bookshelf[facing=south]" if k < 0.18 else "minecraft:bookshelf")
    F.fill(0, h, 0, length - 1, h, 0, st.slab("trim", "bottom"))
    return {"box": F.box(0, 0, 0, length - 1, h, 0)}


def _build_doc() -> str:
    head = [
        "parts: yeniden kullanılabilir usta yapı parçaları (72+). Her parça: parts.<ad>(b, ..., st=style.get('modern')).",
        "Yerel çerçeve: ön cephe z=0'da -z'ye bakar; +x yapının kendi sağı; y yukarı. face = duvarın DIŞ yüzünün baktığı yön.",
        "Dönüş: çoğunlukla {'box': (x0,y0,z0,x1,y1,z1)}; oda/kapı/pencere/ışık bilgisi b.meta'ya eklenir (denetçi kullanır).",
        "Doğrulama: parts.check(b, ground=None) -> sorun listesi (desteksiz meşale/fener, yarım kapı/yatak, havada blok).",
        "Kural: destek isteyenler destekleriyle; düz duvar yerine derinlikli duvar; çerçeveli pencere; saçaklı çatı.",
        "",
        "Katalog:",
    ]
    return "\n".join(head + [f"- {k}: {v}" for k, v in CATALOG.items()])


__doc__ = _build_doc()
