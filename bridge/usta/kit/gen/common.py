"""Ureteclerin ortak yardimcilari: araziye oturtma (kazi/dolgu + dogal gecis), kat/oda bolme, ic mekan doseme,
peyzaj (yol, agac, aydinlatma). Yerel cerceve: on cephe z=0 (-z'ye bakar), +x yapinin sagi, y=0 zemin seviyesi."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from .. import interiors as I
from .. import parts as P
from .. import style as S
from .. import trees as T
from ..core import Build

SIZE_WORDS = {
    "küçük": 0.6, "kucuk": 0.6, "small": 0.6, "minik": 0.5,
    "orta": 1.0, "medium": 1.0, "normal": 1.0,
    "büyük": 1.4, "buyuk": 1.4, "large": 1.4, "geniş": 1.3,
    "devasa": 2.0, "dev": 2.0, "huge": 2.0, "kocaman": 1.8, "muazzam": 2.2,
}


def scale_of(params: dict, default: float = 1.0) -> float:
    s = params.get("size", params.get("ölçek", params.get("olcek")))
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, str):
        return SIZE_WORDS.get(s.strip().lower(), default)
    return default


def get_style(params: dict, ctx: dict | None, default: str) -> S.Style:
    name = params.get("style") or params.get("tarz") or default
    aliases = {"osmanlı": "ottoman", "osmanli": "ottoman", "türk": "ottoman", "turk": "ottoman", "modern": "modern",
               "çağdaş": "modern", "ortaçağ": "medieval", "ortacag": "medieval", "fantastik": "medieval",
               "fütüristik": "futuristic", "futuristik": "futuristic", "japon": "japanese", "iskandinav": "scandinavian",
               "ege": "mediterranean", "akdeniz": "mediterranean", "rustik": "rustic", "köy": "rustic", "klasik": "classical"}
    name = aliases.get(str(name).lower(), str(name).lower())
    if name not in S.STYLES:
        name = default
    st = S.get(name)
    biome = (ctx or {}).get("biome")
    if biome and params.get("adapt_biome", True):
        st = st.adapt(biome)
    return st


# ------------------------------------------------------------------ arazi
@dataclass
class Ground:
    """Yerel zemin yukseklikleri (zemin ust blogunun yerel y'si); dizin [z + m, x + m]."""
    h: np.ndarray
    m: int
    water: np.ndarray | None = None
    top: np.ndarray | None = None      # su kolonlarinda su yuzeyinin yerel y'si (oyundan; yoksa kiyidan tahmin)

    def at(self, x: int, z: int) -> int:
        """Zemin ust blogunun yerel y'si; izgara disinda en yakin kenar degeri (0 yerine: egimde havada kalmasin)."""
        i = min(max(z + self.m, 0), self.h.shape[0] - 1)
        j = min(max(x + self.m, 0), self.h.shape[1] - 1)
        return int(self.h[i, j])

    def inside(self, x: int, z: int) -> bool:
        return 0 <= z + self.m < self.h.shape[0] and 0 <= x + self.m < self.h.shape[1]


def ground_of(ctx: dict | None, w: int, d: int) -> Ground:
    t = (ctx or {}).get("terrain")
    if t is not None and "ground" in t:
        g = np.asarray(t["ground"]).astype(np.int32)
        m = int(np.asarray(t.get("margin", 4)))
        k = np.asarray(t.get("known", np.ones_like(g, dtype=bool))).astype(bool)
        g = np.where(k, g, 0)
        g = np.clip(g, -24, 40)
        wat = np.asarray(t["water"]).astype(bool) if "water" in t else None
        top = np.asarray(t["water_top"]).astype(np.int32) if "water_top" in t else None
        return Ground(g, m, wat, top)
    return Ground(np.zeros((d + 8, w + 8), dtype=np.int32), 4, None)


def seal_water(b: Build, ctx: dict | None) -> int:
    """Denizde/golde kuru cukur ve su duvari kalmasin: su kolonlarinda su yuzeyinin altindaki, disaridaki suya bagli
    hava hucreleri 'koru' (0) yapilir, dunyadaki su yerinde kalir. Kapali ic mekanlar (kule tabani vb.) kuru kalir.
    Donus: suya birakilan hucre sayisi."""
    t = (ctx or {}).get("terrain")
    if t is None or "water" not in t:
        return 0
    wat = np.asarray(t["water"]).astype(bool)
    if not wat.any():
        return 0
    m = int(np.asarray(t.get("margin", 4)))
    if "water_top" in t:
        top = np.asarray(t["water_top"]).astype(np.int32)
    else:
        from .monuments import water_level
        wl = water_level(ground_of(ctx, 0, 0))
        if wl is None:
            return 0
        top = np.full(wat.shape, wl, np.int32)
    (ox, oy, oz), ids = b.dense()
    sy, sz, sx = ids.shape
    zi, xi = np.arange(sz) + oz + m, np.arange(sx) + ox + m
    inside = ((zi >= 0) & (zi < wat.shape[0]))[:, None] & ((xi >= 0) & (xi < wat.shape[1]))[None, :]
    ZI, XI = np.meshgrid(np.clip(zi, 0, wat.shape[0] - 1), np.clip(xi, 0, wat.shape[1] - 1), indexing="ij")
    col = wat[ZI, XI] & inside
    ctop = np.where(col, top[ZI, XI], -10 ** 6)
    below = (np.arange(sy) + oy)[:, None, None] <= ctop[None]
    free = below & (ids == 1)
    if not free.any():
        return 0

    def grow(a):
        g = a.copy()
        g[1:] |= a[:-1]
        g[:-1] |= a[1:]
        g[:, 1:] |= a[:, :-1]
        g[:, :-1] |= a[:, 1:]
        g[:, :, 1:] |= a[:, :, :-1]
        g[:, :, :-1] |= a[:, :, 1:]
        return g
    reach = np.zeros_like(free)
    for sl in ((slice(None), 0), (slice(None), -1), (slice(None), slice(None), 0), (slice(None), slice(None), -1)):
        reach[sl] |= free[sl]                       # kutunun yan yuzleri: disarisi dunyadaki su
    reach |= grow(below & (ids == 0)) & free        # plan icinde dokunulmayan su hucreleri
    while True:
        nxt = grow(reach) & free
        if np.array_equal(nxt, reach):
            break
        reach = nxt
    ys, zs, xs = np.nonzero(reach)
    for y, z, x in zip(ys.tolist(), zs.tolist(), xs.tolist()):
        b.set(ox + x, oy + y, oz + z, 0)
    return len(ys)


def settle_on_ground(b: Build, g: Ground, x0: int, z0: int, x1: int, z1: int, st: S.Style, blend: int = 4,
                     top: str = "grass_block", fill_role: str = "foundation") -> None:
    """Ayak izini y=0'a oturtur: alcakta dolgu (ust temel, alt toprak), yuksekte kazi; cevrede `blend` blokluk dogal egim.
    Havada temel ya da ucurum gibi kesik birakmaz (T5)."""
    H, W = g.h.shape
    # uyarlanir gecis: ayak izi cevresindeki en buyuk yukseklik farki kadar genis (egim <= ~1/blok), arazi payi sinirinda
    ring = []
    for zi in range(H):
        for xi in range(W):
            x, z = xi - g.m, zi - g.m
            if max(x0 - x, 0, x - x1, z0 - z, 0, z - z1) > 0 and (g.water is None or not g.water[zi, xi]):
                ring.append(abs(int(g.h[zi, xi])))
    if ring:
        blend = int(max(blend, min(g.m - 1, int(np.percentile(ring, 90)) + 1)))
    for zi in range(H):
        z = zi - g.m
        for xi in range(W):
            x = xi - g.m
            gh = int(g.h[zi, xi])
            dx = max(x0 - x, 0, x - x1)
            dz = max(z0 - z, 0, z - z1)
            dist = max(dx, dz)
            if dist == 0:
                tgt = 0
            elif dist <= blend:
                f = dist / (blend + 1)
                tgt = int(round(0 * (1 - f) + gh * f))
            else:
                continue
            if g.water is not None and g.water[zi, xi] and dist > 0:
                continue
            if gh < tgt:
                # dolgu: ayak izinde temel tasi, cevrede toprak; en ustte cimen
                if dist == 0:
                    if tgt - 1 >= gh + 1:
                        st.fill(b, x, gh + 1, z, x, tgt - 1, z, fill_role)
                else:
                    if tgt - 1 >= gh + 1:
                        b.fill(x, gh + 1, z, x, tgt - 1, z, "dirt")
                    b.set(x, tgt, z, top)
            elif gh > tgt:
                b.fill(x, tgt + 1, z, x, gh + 2, z, "air")
                if dist > 0:
                    b.set(x, tgt, z, top)
            # dist == 0 icin zemin y=0 satirini yapi kendisi yazar


def clear_volume(b: Build, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int) -> None:
    """Yapi hacmindeki dogal engelleri (agac, cimen) temizler; yalniz henuz bos hucrelere hava yazar."""
    b.fill(x0, y0, z0, x1, y1, z1, "air", only_empty=True)


# ------------------------------------------------------------------ kat ve oda
@dataclass
class Floor:
    y: int                     # doseme seviyesi
    rooms: list = field(default_factory=list)  # [(kind, box)]


def _cut_at(lo: int, n: int, min_w: int, avoid):
    """lo..lo+n-1 araliginda ortaya en yakin bolme cizgisi; avoid'deki koordinatlardan (kapi sutunlari) kacar.
    Oda en az min_w (gerekirse 1 eksigi) kalmali; uygun cizgi yoksa None (o yonde bolme)."""
    mid = lo + n // 2
    for mw in (min_w, max(3, min_w - 1)):
        for k in range(0, n):
            for c in (mid + k, mid - k):
                if lo + mw <= c <= lo + n - 1 - mw and c not in avoid:
                    return c
    return None


def split_rooms(x0: int, z0: int, x1: int, z1: int, y: int, h: int, kinds: list[str], min_w: int = 4,
                avoid_x=(), avoid_z=()) -> list[tuple[str, tuple]]:
    """Ic alani (x0..x1, z0..z1 ic hava sinirlari) odalara boler; donus [(tur, (x0,y,z0,x1,y+h-1,z1))].
    avoid_x/avoid_z: bolme duvari olmamasi gereken x/z koordinatlari (dis kapi/balkon kapisi hizasi)."""
    rooms = []
    boxes = [(x0, z0, x1, z1)]
    ax, az = set(avoid_x), set(avoid_z)
    while len(boxes) < len(kinds):
        boxes.sort(key=lambda r: -((r[2] - r[0] + 1) * (r[3] - r[1] + 1)))
        a = boxes.pop(0)
        w, d = a[2] - a[0] + 1, a[3] - a[1] + 1
        if max(w, d) < 2 * min_w + 1:
            boxes.append(a)
            break
        order = ("x", "z") if w >= d else ("z", "x")
        done = False
        for axis in order:
            if axis == "x" and w >= 2 * min_w + 1:
                cut = _cut_at(a[0], w, min_w, ax)
                if cut is not None:
                    boxes += [(a[0], a[1], cut - 1, a[3]), (cut + 1, a[1], a[2], a[3])]
                    done = True
                    break
            if axis == "z" and d >= 2 * min_w + 1:
                cut = _cut_at(a[1], d, min_w, az)
                if cut is not None:
                    boxes += [(a[0], a[1], a[2], cut - 1), (a[0], cut + 1, a[2], a[3])]
                    done = True
                    break
        if not done:
            boxes.append(a)
            break
    boxes.sort(key=lambda r: (r[1], r[0]))
    for k, r in zip(kinds, boxes):
        rooms.append((k, (r[0], y, r[1], r[2], y + h - 1, r[3])))
    return rooms


def partition_walls(b: Build, rooms: list, st: S.Style, y: int, h: int, outer: tuple,
                    avoid: set | None = None) -> list[tuple[int, int, int]]:
    """Odalar arasina ic duvar ve kapi bosluklari koyar. outer = (x0,z0,x1,z1) ic sinir. avoid: kapinin iki yaninda
    olmamasi gereken (x, z) hucreleri (merdiven ve boslugu: korkuluk kapiyi kapatmasin). Donus: kapi hucreleri."""
    doors = []
    avoid = avoid or set()

    def pick(lo, hi, ok):
        mid = (lo + hi) // 2
        for v in sorted(range(lo, hi + 1), key=lambda v: (abs(v - mid), v)):
            if ok(v):
                return v
        return mid
    ox0, oz0, ox1, oz1 = outer
    seen = set()
    for _, a in rooms:
        for _, c in rooms:
            if a is c:
                continue
            # a'nin dogusunda c: aradaki duvar sutunu
            if a[3] + 2 == c[0] and not (a[5] < c[2] or c[5] < a[2]):
                wx = a[3] + 1
                lo, hi = max(a[2], c[2]), min(a[5], c[5])
                key = ("x", wx, lo, hi)
                if key in seen:
                    continue
                seen.add(key)
                st.fill(b, wx, y, lo, wx, y + h - 1, hi, "wall2")
                dz = pick(lo, hi, lambda v: not ({(wx - 1, v), (wx, v), (wx + 1, v)} & avoid))
                b.fill(wx, y, dz, wx, y + 1, dz, "air")
                doors.append((wx, y, dz))
            if a[5] + 2 == c[2] and not (a[3] < c[0] or c[3] < a[0]):
                wz = a[5] + 1
                lo, hi = max(a[0], c[0]), min(a[3], c[3])
                key = ("z", wz, lo, hi)
                if key in seen:
                    continue
                seen.add(key)
                st.fill(b, lo, y, wz, hi, y + h - 1, wz, "wall2")
                dx = pick(lo, hi, lambda v: not ({(v, wz - 1), (v, wz), (v, wz + 1)} & avoid))
                b.fill(dx, y, wz, dx, y + 1, wz, "air")
                doors.append((dx, y, wz))
    return doors


_INTERIOR_OF = {"scandinavian": "nordic", "classical": "royal",
                "mediterranean": {"base": "rustic", "wood": "oak", "fabric": "white", "fabric2": "blue", "accent": "blue",
                                  "bed": "white", "rug": "blue", "rug2": "white", "rug3": "orange"}}


def interior_style(st) -> str | dict:
    """Dis tarz paketi (kit.style) -> ic mekan stili (kit.interiors.STYLES adi ya da sozluk)."""
    base = str(getattr(st, "name", st) or "modern").split("@")[0]
    v = _INTERIOR_OF.get(base, base)
    if isinstance(v, str) and v not in I.STYLES:
        v = "modern"
    return v


def stair_keep(res: dict, facing: str = "north") -> list:
    """P.staircase donusu -> mobilya konmayacak hucreler: basamaklarin ustu 3 blok, merdiven alti bosluk,
    ust kattaki merdiven boslugunun ustu ve cikis hucresinin ustu 2 blok."""
    steps = list((res or {}).get("steps") or [])
    out = []
    if steps:
        base = min(s[1] for s in steps)
        upper = int((res or {}).get("upper", max(s[1] for s in steps)))
    for (X, Y, Z) in steps:
        out += [(X, Y + 1, Z), (X, Y + 2, Z), (X, Y + 3, Z)]
        out += [(X, yy, Z) for yy in range(base, Y - 1)]          # merdiven alti
        if Y < upper <= Y + 3:
            out += [(X, upper + 1, Z), (X, upper + 2, Z)]         # ust kattaki bosluk (hali/esya asili kalmasin)
    if steps:
        top = max(s[1] for s in steps)
        d = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[facing]
        for (X, Y, Z) in steps:
            if Y == top:
                for k in (1, 2):
                    out += [(X + d[0] * k, Y + 1, Z + d[1] * k), (X + d[0] * k, Y + 2, Z + d[1] * k)]
    return out


def stair_access(b: Build, sx: int, sz: int, fy: int, fh: int, odd: bool) -> list:
    """Kat kat degisen duz merdivenlerde (tek katlarda 2 sutun batida) bir alt merdivenin cikisindan bu merdivenin
    ilk basamagina giden yol: bolme duvari varsa acar (kapi boslugu), mobilya icin ayrilacak hucreleri dondurur."""
    side = -1 if odd else 1            # tek katta batidan, cift katta (>=2) doğudan dolanilir
    cells = [(sx + side, fy + k, z) for z in range(sz - fh, sz + 2) for k in (1, 2)]
    cells += [(sx, fy + k, sz + 1) for k in (1, 2)]
    for (x, y, z) in cells:
        cur = str(b.get(x, y, z)).split("[")[0]
        if b.get_id(x, y, z) > 1 and not cur.endswith(("_stairs", "_door")) and "glass" not in cur:
            b.set(x, y, z, "air")
    return cells


def furnish_rooms(b: Build, rooms: list, st: S.Style, doors: list, seed: int = 0, keep_clear: list | None = None) -> None:
    """Odalari doser. doors: gecis kapilari/aciklik hucreleri; keep_clear: bos kalmasi gereken hucreler
    (merdiven ustu, giris holu) — doseme sirasinda gecici bariyerle tutulur, sonra eski haline doner."""
    # walls_box'un tum kati kapsayan "katN" kayitlari bolunen katlarda yaniltir: kaldir
    b.meta["rooms"] = [r for r in b.meta.get("rooms", []) if not str(r.get("name", "")).startswith("kat")]
    held = {}
    for c in keep_clear or []:
        c = tuple(int(v) for v in c[:3])
        if c not in held and b.get_id(*c) <= 1:
            held[c] = b.get(*c)
            b.set(*c, "barrier")
    try:
        for i, (kind, box) in enumerate(rooms):
            x0, y0, z0, x1, y1, z1 = box
            dd = [d for d in doors if x0 - 1 <= d[0] <= x1 + 1 and z0 - 1 <= d[2] <= z1 + 1 and y0 <= d[1] <= y1]
            if x1 - x0 < 2 or z1 - z0 < 2 or y1 - y0 < 1:
                continue
            try:
                I.furnish(b, box, kind, style=interior_style(st), door=dd or None, seed=seed + i)
            except Exception as e:  # tarif sigmazsa oda yine aydinlatilsin
                b.meta.setdefault("notes", []).append(f"{kind}: {e}")
                cx, cz = (x0 + x1) // 2, (z0 + z1) // 2
                P.hanging_lamp(b, cx, y1, cz, st)
    finally:
        for c, orig in held.items():
            if (b.get(*c) or "").split("[")[0].endswith("barrier"):
                b.set(*c, orig)


def room_windows(b: Build, rooms: list, outer: tuple, y: int, st: S.Style, faces=("north", "south", "east", "west"),
                 w: int = 2, h: int = 2, every: int = 7) -> int:
    """Her odanin dis duvarina (outer = (x0,z0,x1,z1) ic hava siniri) oda acikligina ortali pencere(ler);
    o duvar parcasinda zaten cam varsa atlar. y = pencere alt sirasi. Donus: konan pencere sayisi."""
    ox0, oz0, ox1, oz1 = outer
    n_put = 0
    for _, (x0, y0, z0, x1, y1, z1) in rooms:
        sides = []
        if z0 == oz0 and "north" in faces:
            sides.append(("north", x0, x1, z0 - 1))
        if z1 == oz1 and "south" in faces:
            sides.append(("south", x0, x1, z1 + 1))
        if x0 == ox0 and "west" in faces:
            sides.append(("west", z0, z1, x0 - 1))
        if x1 == ox1 and "east" in faces:
            sides.append(("east", z0, z1, x1 + 1))
        for face, a0, a1, wc in sides:
            span = a1 - a0 + 1
            if span < w + 2:
                continue
            along_x = face in ("north", "south")
            seg = [(a, yy, wc) if along_x else (wc, yy, a) for a in range(a0, a1 + 1) for yy in range(y, y + h)]
            if any("glass" in str(b.get(*c)) for c in seg):
                continue
            n = max(1, (span + 1) // every)
            for i in range(n):
                a = a0 + (span * (2 * i + 1)) // (2 * n) - w // 2
                a = max(a0 + 1, min(a, a1 - w))
                X, Z = (a, wc) if along_x else (wc, a)
                P.window(b, X, y, Z, face, w, h, st)
                n_put += 1
    return n_put


def perimeter_lamps(b: Build, x0: int, z0: int, x1: int, z1: int, y: int, st: S.Style, every: int = 6,
                    faces=("north", "south", "east", "west"), skip: list | None = None) -> int:
    """Dis duvarlarin (x0..x1, z0..z1 dis yuzler) y sirasina aralikli duvar lambasi: sacak alti ve duvar dibi
    karanlik kalmasin. Duvar blogu dolu ve onu bos olan hucrelere konur; skip: [(x,z)] atlanacak duvar hucreleri."""
    skip = set(skip or [])
    n = 0
    sides = {"north": [(x, z0) for x in range(x0 + 1, x1, every)], "south": [(x, z1) for x in range(x0 + 1, x1, every)],
             "west": [(x0, z) for z in range(z0 + 1, z1, every)], "east": [(x1, z) for z in range(z0 + 1, z1, every)]}
    out = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
    for face in faces:
        dx, dz = out[face]
        for (x, z) in sides[face]:
            if (x, z) in skip or not b.is_solid(x, y, z):
                continue
            cur = str(b.get(x, y, z))
            if "glass" in cur or "door" in cur:
                continue
            if b.get_id(x + dx, y, z + dz) > 1 or b.get_id(x + dx, y - 1, z + dz) > 1:
                continue
            P.wall_lamp(b, x, y, z, face, st)
            n += 1
    return n


def light_shaft(b: Build, cx: int, cz: int, y0: int, y1: int, r: int = 2, every: int = 4, level: int = 12) -> int:
    """Kule/minare/kuyu gibi dar dikey hacimlere gorunmez isik (vanilla 'light' blogu, carpismasiz): her `every`
    blokta bir; merkeze r yaricap icinde, alti dolu ve ustu bos bir hava hucresine (duvar dibine yakin olan yegdir).
    Donus: konan isik sayisi."""
    cells = sorted(((dx, dz) for dx in range(-r, r + 1) for dz in range(-r, r + 1) if dx * dx + dz * dz <= r * r + 1),
                   key=lambda c: -(c[0] * c[0] + c[1] * c[1]))
    n = 0
    for y in range(y0, y1 + 1, every):
        placed = False
        for allow_stairs in (False, True):        # once basamak disi hucre; yoksa basamak ustu (isik carpismasiz)
            for yy in (y, y + 1, y - 1, y + 2, y - 2):
                for dx, dz in cells:
                    x, z = cx + dx, cz + dz
                    if b.get_id(x, yy, z) <= 1 and b.get_id(x, yy + 1, z) <= 1 and b.is_solid(x, yy - 1, z) and \
                            (allow_stairs or not str(b.get(x, yy - 1, z)).split("[")[0].endswith("_stairs")):
                        b.set(x, yy, z, f"light[level={level}]")
                        n += 1
                        placed = True
                        break
                if placed:
                    break
            if placed:
                break
    return n


def tower_door(b: Build, cx: int, cz: int, r: int, y: int, face: str, st: S.Style, w: int = 1, kind: str = "framed") -> tuple:
    """Yuvarlak kulenin `face` yuzune kapi: duvari keser, kapinin altina ve onune saglam zemin, oneki halka
    basamaklarini kaldirir (kapi onu 2 blok bos), disari 1 basamak. Donus: kapinin alt hucresi (x, y, z)."""
    vx, vz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[face]
    px, pz = (1, 0) if vx == 0 else (0, 1)
    X, Z = cx + vx * r, cz + vz * r
    if w == 2:
        X, Z = X - (px if face in ("north", "west") else 0), Z - (pz if face in ("north", "west") else 0)
    for k in range(w):
        xx, zz = X + px * k, Z + pz * k
        for n_ in (0, 1, 2):                      # duvar, dis halka, onundeki hucre
            ox, oz = xx + vx * n_, zz + vz * n_
            st.set(b, ox, y - 1, oz, "foundation")
            for hh in (0, 1):
                b.set(ox, y + hh, oz, "minecraft:air")
        ix, iz = xx - vx, zz - vz                 # ic taraf
        if not b.is_solid(ix, y - 1, iz):
            st.set(b, ix, y - 1, iz, "floor")
    x0 = min(X, X + px * (w - 1))
    z0 = min(Z, Z + pz * (w - 1))
    P.door(b, x0, y, z0, face, st, w=w, kind=kind)
    return (x0, y, z0)


def landscape_ring(b: Build, g: Ground, x0: int, z0: int, x1: int, z1: int, st: S.Style, seed: int = 0, trees: int = 6,
                   species: tuple[str, ...] = ("oak", "birch"), lamps: bool = True, path_to: tuple[int, int] | None = None,
                   hedge: bool = True, flowers: bool = True, avoid: list | None = None) -> None:
    """Yapinin cevresine: on yol, cicek tarhlari, cit/bitki, agaclar ve fenerler."""
    rnd = random.Random(seed)
    avoid = list(avoid or [])

    def free(x, z, r=1):
        for a in avoid:
            if a[0] - r <= x <= a[2] + r and a[1] - r <= z <= a[3] + r:
                return False
        return x0 - 1 > x or x > x1 + 1 or z0 - 1 > z or z > z1 + 1
    if path_to is not None:
        px, pz = path_to
        P.path(b, [(px, pz - 1), (px, z0 - 12)], 0, st, w=3, border=True)
        avoid.append((px - 2, z0 - 12, px + 2, pz))
        if lamps:
            for zz in range(z0 - 3, z0 - 12, -4):
                for sx in (px - 3, px + 3):
                    if free(sx, zz, 0):
                        P.lamp_post(b, sx, 1, zz, st, h=3)
                        avoid.append((sx, zz, sx, zz))
    if flowers:
        for fx0, fx1 in ((x0 + 1, x0 + 4), (x1 - 4, x1 - 1)):
            if free(fx0, z0 - 2, 0) and free(fx1, z0 - 3, 0):
                P.garden_bed(b, fx0, 0, z0 - 3, fx1, z0 - 2, st, raised=True, seed=rnd.randint(0, 999))
                avoid.append((fx0, z0 - 3, fx1, z0 - 2))
    n = 0
    tries = 0
    while n < trees and tries < 200:
        tries += 1
        side = rnd.choice(("w", "e", "n", "s"))
        if side == "w":
            x, z = x0 - rnd.randint(5, 9), rnd.randint(z0 - 4, z1 + 4)
        elif side == "e":
            x, z = x1 + rnd.randint(5, 9), rnd.randint(z0 - 4, z1 + 4)
        elif side == "s":
            x, z = rnd.randint(x0 - 4, x1 + 4), z1 + rnd.randint(5, 9)
        else:
            x, z = rnd.choice((x0 - rnd.randint(6, 10), x1 + rnd.randint(6, 10))), z0 - rnd.randint(4, 9)
        if not free(x, z, 3) or not g.inside(x, z):
            continue
        if g.water is not None and g.water[z + g.m, x + g.m]:
            continue
        gy = g.at(x, z)
        if abs(gy) > 6:
            continue
        # buyuk tac binanin catisina/saçagina uzanmasin: yakin agac orta boy
        gap = max(x0 - x, x - x1, z0 - z, z - z1)
        size = rnd.choice(("medium", "large")) if gap >= 8 else "medium"
        r = 5 if size == "large" else 4          # taclar ic ice girmesin
        if not free(x, z, r):
            continue
        try:
            T.tree(b, x, gy, z, species=rnd.choice(species), size=size, seed=rnd.randint(0, 9999))
        except Exception:
            continue
        avoid.append((x - r, z - r, x + r, z + r))
        n += 1


def finish_meta(b: Build, kind: str, st: S.Style, extra: dict | None = None) -> Build:
    b.meta["style"] = st.name
    b.meta["generator"] = kind
    if extra:
        b.meta.update(extra)
    return b


__all__ = ["Build", "P", "S", "I", "T", "np", "math", "random", "scale_of", "get_style", "Ground", "ground_of", "settle_on_ground",
           "clear_volume", "split_rooms", "partition_walls", "furnish_rooms", "interior_style", "stair_keep", "stair_access", "room_windows", "perimeter_lamps", "light_shaft", "tower_door", "landscape_ring", "finish_meta", "Floor"]
