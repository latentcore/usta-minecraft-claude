"""Kalp Adasi uretici: ortak cekirdek (yogun dizi, palet, kalp geometrisi, uzaklik alani, tabela/flama, kit kopruleri).

Dunya cercevesi dogrudan kullanilir: +x dogu (oyuncunun onu), +z guney (oyuncunun sagi), y mutlak.
Dizi G[y - Y0, z - Z0, x - X0] (uint16 palet indeksi; 0 = dokunma, 1 = hava).
Kalp birimi: parametrik kalp X = 16 sin^3 t, Y = 13 cos t - 5 cos 2t - 2 cos 3t - cos 4t (uc Y = -17, girinti Y = 5,
loblarin tepesi Y = 11.9, en genis X = +-16). Ucu bati (oyuncuya) bakan kalpte Y dogu, X guney yonudur.
"""
from __future__ import annotations

import json
import math
import os
import sys

_BRIDGE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # .../bridge
if _BRIDGE not in sys.path:
    sys.path.insert(0, _BRIDGE)
os.environ.setdefault("USTA_GAME_DIR", os.path.expanduser(r"~\UstaOyun"))

import numpy as np  # noqa: E402

from usta import blockdb  # noqa: E402
from usta.kit import shapes as SH  # noqa: E402

DB = blockdb.get()
HERE = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------ yerlesim
AX, AY, AZ = -368, 66, -697      # giris terasinin merkezi = oyuncunun ayak hucresi (yuzu doguya)
SEA = 62                         # denizin en ust su blogu
GY = 65                          # ada zemininin ust blogu (yurume y = 66)
XT = AX + 28                     # kalp adasinin ucu
S_ISL = 9.75                     # ada olcegi: kalp birimi -> blok (312 x 283 blok)
X0, X1 = -384, -36
Z0, Z1 = -895, -500
Y0, Y1 = 30, 319

# ------------------------------------------------------------------ malzeme (beyaz + pembe + altin)
WHITE, QUARTZ, QBLOCK, CALCITE = "white_concrete", "smooth_quartz", "quartz_block", "calcite"
QPILLAR, QBRICK, QCHISEL = "quartz_pillar[axis=y]", "quartz_bricks", "chiseled_quartz_block"
GOLD, PINK, ROSE, MAGENTA = "gold_block", "pink_concrete", "pink_terracotta", "magenta_concrete"
GLASS, WGLASS, PGLASS = "glass", "white_stained_glass", "pink_stained_glass"
WPANE, PPANE, CPANE = "white_stained_glass_pane", "pink_stained_glass_pane", "glass_pane"
FROG, OCHRE, SEAL = "pearlescent_froglight[axis=y]", "ochre_froglight[axis=y]", "sea_lantern"
ROD_UP = "end_rod[facing=up]"
CHERRY = "cherry_planks"

# furnish (kit interiors) icin romantik stil
ROMANTIC = {"base": "modern", "wood": "cherry", "wood2": "pale_oak", "counter": "smooth_quartz", "stone": "smooth_quartz",
            "stone2": "calcite", "fabric": "pink", "fabric2": "white", "accent": "yellow", "bed": "pink", "rug": "white",
            "rug2": "pink", "rug3": "magenta", "lamp": "lantern", "flush": "pearlescent_froglight", "candle": "pink",
            "leaves": "cherry_leaves", "sconce": "lantern", "tv": True,
            "plants": ("potted_pink_tulip", "potted_white_tulip", "potted_cherry_sapling", "potted_flowering_azalea_bush")}
ROMANTIC_W = dict(ROMANTIC, fabric="white", fabric2="pink", bed="white", rug="pink", rug2="white")

FACE_VEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}

# ------------------------------------------------------------------ kalp geometrisi
_T = np.linspace(0.0, 2 * math.pi, 3000, endpoint=False)
HX = 16.0 * np.sin(_T) ** 3
HY = 13.0 * np.cos(_T) - 5.0 * np.cos(2 * _T) - 2.0 * np.cos(3 * _T) - np.cos(4 * _T)


def _centroid():
    x, y = HX, HY
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    c = x * y2 - x2 * y
    a = c.sum() / 2.0
    return float(((x + x2) * c).sum() / (6 * a)), float(((y + y2) * c).sum() / (6 * a))


HCX, HCY = _centroid()            # agirlik merkezi (HCX = 0)
HTIP, HTOP, HCLEFT = -17.0, float(HY.max()), 5.0


def heart_poly(ox, oz, s, ref="centroid", tip="west", lat_s=None):
    """Kalp cokgeni (dunya x, z). ref: 'centroid' (ox,oz agirlik merkezi) | 'tip' (ox,oz ucun kendisi).
    tip: ucun baktigi yon. s: boy olcegi, lat_s: en olcegi (verilmezse s)."""
    ls = s if lat_s is None else lat_s
    ry = HCY if ref == "centroid" else HTIP
    up = {"west": (1, 0), "east": (-1, 0), "north": (0, 1), "south": (0, -1)}[tip]
    lat = (-up[1], up[0])
    a = (HY - ry) * s
    b = HX * ls
    return ox + a * up[0] + b * lat[0], oz + a * up[1] + b * lat[1]


def heart_poly_rot(ox, oz, s, angle, ref="centroid"):
    """Ucu `angle` (radyan, +x'ten +z'ye) yonune bakan kalp cokgeni."""
    ry = HCY if ref == "centroid" else HTIP
    ux, uz = -math.cos(angle), -math.sin(angle)
    lx, lz = -uz, ux
    a = (HY - ry) * s
    b = HX * s
    return ox + a * ux + b * lx, oz + a * uz + b * lz


def raster(px, pz, x0, z0, nx, nz):
    """Cift-tek tarama: cokgen -> bool maske [z, x], hucre merkezleri (x0 + j + .5)."""
    m = np.zeros((nz, nx), bool)
    xa, za = np.asarray(px, float), np.asarray(pz, float)
    xb, zb = np.roll(xa, -1), np.roll(za, -1)
    lo, hi = int(math.floor(za.min() - z0)) - 1, int(math.ceil(za.max() - z0)) + 1
    for i in range(max(lo, 0), min(hi, nz)):
        zc = z0 + i + 0.5
        c = (za > zc) != (zb > zc)
        if not c.any():
            continue
        xs = np.sort(xa[c] + (zc - za[c]) * (xb[c] - xa[c]) / (zb[c] - za[c]))
        for a, b in zip(xs[0::2], xs[1::2]):
            j0 = max(int(math.ceil(a - 0.5 - x0)), 0)
            j1 = min(int(math.floor(b - 0.5 - x0)), nx - 1)
            if j1 >= j0:
                m[i, j0:j1 + 1] = True
    return m


def seg_distance(px, pz, qx, qz, chunk=1500):
    """Noktalar (qx, qz) ile kapali cokgen (px, pz) kenarlari arasindaki en kisa uzaklik."""
    ax, az = np.asarray(px, np.float32), np.asarray(pz, np.float32)
    bx, bz = np.roll(ax, -1), np.roll(az, -1)
    dx, dz = bx - ax, bz - az
    ll = np.maximum(dx * dx + dz * dz, 1e-9)
    qx = np.asarray(qx, np.float32).ravel()
    qz = np.asarray(qz, np.float32).ravel()
    out = np.empty(qx.shape, np.float32)
    for i in range(0, len(qx), chunk):
        x = qx[i:i + chunk, None]
        z = qz[i:i + chunk, None]
        t = np.clip(((x - ax) * dx + (z - az) * dz) / ll, 0.0, 1.0)
        ex = ax + t * dx - x
        ez = az + t * dz - z
        out[i:i + chunk] = np.sqrt((ex * ex + ez * ez).min(axis=1))
    return out


def sdf(px, pz, x0, z0, nx, nz, step=2, margin=40.0):
    """Isaretli uzaklik [z, x] (iceride +). Cokgenin kutusu + margin disi -margin ile kirpilir."""
    inside = raster(px, pz, x0, z0, nx, nz)
    d = np.full((nz, nx), -margin, np.float32)
    jx0 = max(int(math.floor(min(px) - margin - x0)), 0)
    jx1 = min(int(math.ceil(max(px) + margin - x0)), nx - 1)
    iz0 = max(int(math.floor(min(pz) - margin - z0)), 0)
    iz1 = min(int(math.ceil(max(pz) + margin - z0)), nz - 1)
    zz, xx = np.mgrid[iz0:iz1 + 1, jx0:jx1 + 1]
    dist = seg_distance(np.asarray(px)[::step], np.asarray(pz)[::step], xx + x0 + 0.5, zz + z0 + 0.5).reshape(zz.shape)
    sub = np.where(inside[iz0:iz1 + 1, jx0:jx1 + 1], dist, -dist)
    d[iz0:iz1 + 1, jx0:jx1 + 1] = np.maximum(sub, -margin)
    return d, inside


def arc_param(px, pz, qx, qz):
    """Her (qx, qz) noktasi icin cokgen uzerindeki en yakin kosenin yay uzunlugu (cevre boyunca konum)."""
    ax, az = np.asarray(px, float), np.asarray(pz, float)
    seg = np.hypot(np.roll(ax, -1) - ax, np.roll(az, -1) - az)
    cum = np.concatenate([[0.0], np.cumsum(seg)[:-1]])
    qx = np.asarray(qx, float).ravel()
    qz = np.asarray(qz, float).ravel()
    out = np.empty(qx.shape, float)
    for i in range(0, len(qx), 2000):
        d = (qx[i:i + 2000, None] - ax[None]) ** 2 + (qz[i:i + 2000, None] - az[None]) ** 2
        out[i:i + 2000] = cum[np.argmin(d, axis=1)]
    return out, float(seg.sum())


def heart3d(X, Y, Z):
    """3B kalp (Taubin): (x^2 + 9/4 y^2 + z^2 - 1)^3 - x^2 z^3 - 9/80 y^2 z^3 <= 0; z yukari, y derinlik."""
    a = X * X + 2.25 * Y * Y + Z * Z - 1.0
    return a * a * a - X * X * Z ** 3 - 0.1125 * Y * Y * Z ** 3 <= 0


_H3 = None


def _heart3d_bounds():
    global _H3
    if _H3 is None:
        zs = np.linspace(-1.2, 1.4, 500)
        xs = np.linspace(-1.3, 1.3, 500)
        Zg, Xg = np.meshgrid(zs, xs)
        ins = heart3d(Xg, 0.0, Zg)
        _H3 = (float(np.abs(Xg[ins]).max()), float(Zg[ins].min()), float(Zg[ins].max()))
    return _H3


def heart3d_mask(xc, y0, zc, width, height, depth):
    """Dunya hucrelerinde 3B kalp: genislik z boyunca, yukseklik y (alt uc y0), derinlik x boyunca (on yuz -x).
    Doner: (xs, ys, zs, dolu[y, z, x], kabuk[y, z, x])."""
    xmax, zmin, zmax = _heart3d_bounds()
    a = (width / 2.0) / xmax
    b = height / (zmax - zmin)
    c = (depth / 2.0) / 0.667
    xs = np.arange(int(math.floor(xc - depth / 2 - 2)), int(math.ceil(xc + depth / 2 + 2)) + 1)
    ys = np.arange(int(y0) - 1, int(math.ceil(y0 + height)) + 2)
    zs = np.arange(int(math.floor(zc - width / 2 - 2)), int(math.ceil(zc + width / 2 + 2)) + 1)
    Yg, Zg, Xg = np.meshgrid(ys, zs, xs, indexing="ij")
    S = heart3d((Zg + 0.5 - zc) / a, (Xg + 0.5 - xc) / c, (Yg + 0.5 - y0) / b + zmin)
    pad = np.pad(S, 1)
    inner = pad[1:-1, 1:-1, 1:-1] & pad[2:, 1:-1, 1:-1] & pad[:-2, 1:-1, 1:-1] & pad[1:-1, 2:, 1:-1] & \
        pad[1:-1, :-2, 1:-1] & pad[1:-1, 1:-1, 2:] & pad[1:-1, 1:-1, :-2]
    return xs, ys, zs, S, S & ~inner


# ------------------------------------------------------------------ 2B morfoloji
def shift(m, dz, dx, fill=False):
    out = np.full(m.shape, fill, m.dtype)
    nz, nx = m.shape
    zs, zd = (slice(0, nz - dz), slice(dz, nz)) if dz >= 0 else (slice(-dz, nz), slice(0, nz + dz))
    xs, xd = (slice(0, nx - dx), slice(dx, nx)) if dx >= 0 else (slice(-dx, nx), slice(0, nx + dx))
    out[zd, xd] = m[zs, xs]
    return out


def dilate(m, r=1, square=False):
    out = m.copy()
    for k in range(r):
        o = out.copy()
        for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            o |= shift(out, dz, dx)
        if square or k % 2:
            for dz, dx in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                o |= shift(out, dz, dx)
        out = o
    return out


def erode(m, r=1, square=False):
    return ~dilate(~m, r, square)


def edge4(m):
    """Maskenin 4-komsuluk ic kenari (en dis halka)."""
    return m & ~erode(m, 1, square=False)


def ring_out(m):
    """Maskenin hemen disindaki 4-komsuluk halkasi."""
    return dilate(m, 1) & ~m


def hash2(x, z, seed=0):
    return SH.hash01(np.asarray(x), 0, np.asarray(z), seed)


def noise2(x, z, scale=16.0, seed=0, octaves=2):
    return SH.noise(np.asarray(x, float), 0.0, np.asarray(z, float), scale=scale, seed=seed, octaves=octaves)


# ------------------------------------------------------------------ yogun dunya
class World:
    def __init__(self):
        self.nx, self.ny, self.nz = X1 - X0 + 1, Y1 - Y0 + 1, Z1 - Z0 + 1
        self.G = np.zeros((self.ny, self.nz, self.nx), np.uint16)
        self.pal = ["keep", "minecraft:air"]
        self.pidx = {"keep": 0, "minecraft:air": 1, "air": 1}
        self.be: dict[tuple[int, int, int], str] = {}
        self.ents: list[dict] = []
        self.notes: list[str] = []
        self.XX, self.ZZ = np.meshgrid(np.arange(X0, X1 + 1), np.arange(Z0, Z1 + 1))
        self.occ = np.zeros((self.nz, self.nx), bool)        # zemini yapi/yol tutan hucreler (bitki konmaz)
        self.top = np.full((self.nz, self.nx), -999, np.int16)  # ada/kara ust blogu
        self.floor = None                                    # dogal deniz tabani (arazi onbellegi)

    # -------------------------------------------------------------- palet
    def id(self, state) -> int:
        if isinstance(state, (int, np.integer)):
            return int(state)
        i = self.pidx.get(state)
        if i is not None:
            return i
        exact = state.startswith("!")
        c = DB.canonical(state[1:] if exact else state)
        key = ("!" + c) if exact else c
        i = self.pidx.get(key)
        if i is None:
            i = len(self.pal)
            self.pal.append(key)
            self.pidx[key] = i
        self.pidx[state] = i
        return i

    def ids(self, states) -> np.ndarray:
        return np.array([self.id(s) for s in states], np.uint16)

    # -------------------------------------------------------------- hucre
    @staticmethod
    def inside(x, y, z) -> bool:
        return X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1

    def set(self, x, y, z, state):
        if X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1:
            self.G[y - Y0, z - Z0, x - X0] = self.id(state)

    def get(self, x, y, z) -> int:
        if X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1:
            return int(self.G[y - Y0, z - Z0, x - X0])
        return 0

    def name(self, x, y, z) -> str:
        return self.pal[self.get(x, y, z)]

    def view(self, x0, y0, z0, x1, y1, z1):
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        za, zb = sorted((z0, z1))
        xa, ya, za = max(xa, X0), max(ya, Y0), max(za, Z0)
        xb, yb, zb = min(xb, X1), min(yb, Y1), min(zb, Z1)
        if xa > xb or ya > yb or za > zb:
            return None
        return self.G[ya - Y0:yb - Y0 + 1, za - Z0:zb - Z0 + 1, xa - X0:xb - X0 + 1]

    def box(self, x0, y0, z0, x1, y1, z1, state, only=None, empty=False):
        """Kutu (uclar dahil). only: yalniz bu id'lerin uzerine; empty: yalniz bos (0/1) hucrelere."""
        v = self.view(x0, y0, z0, x1, y1, z1)
        if v is None:
            return
        i = self.id(state)
        if only is not None:
            v[np.isin(v, only)] = i
        elif empty:
            v[v <= 1] = i
        else:
            v[...] = i

    def hollow(self, x0, y0, z0, x1, y1, z1, state):
        for a in ((x0, y0, z0, x1, y0, z1), (x0, y1, z0, x1, y1, z1), (x0, y0, z0, x0, y1, z1), (x1, y0, z0, x1, y1, z1),
                  (x0, y0, z0, x1, y1, z0), (x0, y0, z1, x1, y1, z1)):
            self.box(*a, state)

    def layer(self, y, mask, state, empty=False, only=None):
        """Tam boy 2B maske [nz, nx] ile y katmanina yazar. state dizi de olabilir (id dizisi, ayni sekil)."""
        if not (Y0 <= y <= Y1):
            return
        L = self.G[y - Y0]
        m = mask
        if empty:
            m = m & (L <= 1)
        if only is not None:
            m = m & np.isin(L, only)
        if isinstance(state, np.ndarray):
            L[m] = state[m]
        else:
            L[m] = self.id(state)

    def layers(self, y0, y1, mask, state, empty=False, only=None):
        for y in range(max(y0, Y0), min(y1, Y1) + 1):
            self.layer(y, mask, state, empty=empty, only=only)

    def columns(self, mask, y0, ytop, state):
        """mask hucrelerinde y0 .. ytop (dahil) doldurur; y0 ve ytop tamsayi ya da [z, x] dizisi."""
        if not mask.any():
            return
        yt = np.where(mask, ytop, -9999)
        yb = np.where(mask, y0, 9999)
        i = self.id(state)
        for y in range(max(int(yb.min()), Y0), min(int(yt.max()), Y1) + 1):
            self.G[y - Y0][(yt >= y) & (yb <= y)] = i

    def sub2(self, x0, z0, x1, z1):
        """2B pencere dilimi (iz, jx) — tam boy maskelerde alt bolge secmek icin."""
        return (slice(max(z0, Z0) - Z0, min(z1, Z1) - Z0 + 1), slice(max(x0, X0) - X0, min(x1, X1) - X0 + 1))

    def mask_rect(self, x0, z0, x1, z1):
        m = np.zeros((self.nz, self.nx), bool)
        xa, xb = sorted((x0, x1))
        za, zb = sorted((z0, z1))
        m[self.sub2(xa, za, xb, zb)] = True
        return m

    def mask_disk(self, cx, cz, r, r_in=None):
        d2 = (self.XX - cx) ** 2 + (self.ZZ - cz) ** 2
        m = d2 <= r * r + r
        if r_in is not None:
            m &= d2 > r_in * r_in + r_in
        return m

    def mask_poly(self, px, pz):
        return raster(px, pz, X0, Z0, self.nx, self.nz)

    def line(self, p0, p1, state, r=0.5):
        SHp = SH.line(p0, p1, r=r)
        ox, oy, oz = SHp.origin
        ys, zs, xs = np.nonzero(SHp.mask)
        i = self.id(state)
        for y, z, x in zip(ys + oy, zs + oz, xs + ox):
            if X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1:
                self.G[y - Y0, z - Z0, x - X0] = i

    def put_shape(self, shp, state, empty=False):
        ox, oy, oz = shp.origin
        sy, sz, sx = shp.mask.shape
        v = self.view(ox, oy, oz, ox + sx - 1, oy + sy - 1, oz + sz - 1)
        if v is None:
            return
        # kirpma: gorunum kutusu ile maske kesisimi
        xa, ya, za = max(ox, X0), max(oy, Y0), max(oz, Z0)
        m = shp.mask[ya - oy:ya - oy + v.shape[0], za - oz:za - oz + v.shape[1], xa - ox:xa - ox + v.shape[2]]
        if empty:
            m = m & (v <= 1)
        v[m] = self.id(state)

    def count(self) -> int:
        return int(np.count_nonzero(self.G > 1))

    # -------------------------------------------------------------- tabela, flama, varlik
    def sign(self, x, y, z, facing, lines, wood="cherry", color="black", glow=False, wall=True, hanging=False):
        """Tabela: wall (duvara asili; facing = yazinin baktigi yon), ayakli ya da tavandan asili (hanging)."""
        lines = [str(s)[:15] for s in (list(lines) + ["", "", "", ""])[:4]]
        if hanging:
            rot = {"south": 0, "west": 4, "north": 8, "east": 12}[facing]
            self.set(x, y, z, f"{wood}_hanging_sign[attached=false,rotation={rot},waterlogged=false]")
        elif wall:
            self.set(x, y, z, f"{wood}_wall_sign[facing={facing},waterlogged=false]")
        else:
            rot = {"south": 0, "west": 4, "north": 8, "east": 12}[facing]
            self.set(x, y, z, f"{wood}_sign[rotation={rot},waterlogged=false]")
        msgs = ",".join(json.dumps(s, ensure_ascii=False) for s in lines)
        g = "1b" if glow else "0b"
        self.be[(x, y, z)] = ("{front_text:{messages:[" + msgs + "],color:\"" + color + "\",has_glowing_text:" + g + "},"
                              "back_text:{messages:[" + msgs + "],color:\"" + color + "\",has_glowing_text:" + g + "},"
                              "is_waxed:1b}")

    def banner(self, x, y, z, facing=None, base="pink", patterns=(), wall=True, rotation=0):
        if wall:
            self.set(x, y, z, f"{base}_wall_banner[facing={facing}]")
        else:
            self.set(x, y, z, f"{base}_banner[rotation={rotation}]")
        pats = ",".join("{pattern:\"minecraft:%s\",color:\"%s\"}" % (p, c) for p, c in patterns)
        self.be[(x, y, z)] = "{patterns:[" + pats + "]}"

    def entity(self, etype, x, y, z, yaw=0.0, snbt="{}"):
        self.ents.append({"type": etype, "pos": [x, y, z], "yaw": yaw, "pitch": 0.0, "snbt": snbt})

    # -------------------------------------------------------------- kit kopruleri
    def merge_build(self, b, only_empty=False, keep_ids=None):
        """Kit Build'ini (dunya koordinatli) diziye yazar. only_empty: dolu (>1) hucrelere dokunmaz."""
        if not b.chunks:
            return
        (ox, oy, oz), ids = b.dense()
        remap = np.array([0 if s == "keep" else self.id(s) for s in b.palette], np.int64)
        mapped = remap[ids].astype(np.uint16)
        sy, sz, sx = mapped.shape
        v = self.view(ox, oy, oz, ox + sx - 1, oy + sy - 1, oz + sz - 1)
        if v is None:
            return
        xa, ya, za = max(ox, X0), max(oy, Y0), max(oz, Z0)
        src = mapped[ya - oy:ya - oy + v.shape[0], za - oz:za - oz + v.shape[1], xa - ox:xa - ox + v.shape[2]]
        m = src != 0
        if only_empty:
            m &= v <= 1
        v[m] = src[m]
        for (x, y, z), snbt in b.block_entities.items():
            if self.inside(x, y, z):
                self.be[(x, y, z)] = snbt
        for e in b.entities:
            self.ents.append(dict(e))

    def kit_room(self, box, kind, doors, seed=0, style=None):
        """Kit odasi: kutu (ic hava hacmi, uclar dahil) etrafindaki kabuk diziden Build'e alinir, dosenir, geri yazilir."""
        from usta.kit.core import Build
        from usta.kit import interiors
        x0, y0, z0, x1, y1, z1 = box
        b = Build("oda")
        sub = self.view(x0 - 1, y0 - 1, z0 - 1, x1 + 1, y1 + 1, z1 + 1)
        if sub is None:
            return None
        pal = np.array([0] + [b.pid(s) for s in self.pal[1:]], np.int32)
        b.put_ids(x0 - 1, y0 - 1, z0 - 1, pal[sub.astype(np.int64)])
        try:
            rec = interiors.furnish(b, box, kind, style=style or ROMANTIC, door=[list(c) for c in doors], seed=seed)
        except Exception as e:  # pragma: no cover - dosemesiz kalir, kabuk bozulmaz
            self.notes.append(f"doseme atlandi ({kind} {box}): {e}")
            return None
        got = b.ids_box(x0 - 1, y0 - 1, z0 - 1, x1 + 1, y1 + 1, z1 + 1)
        remap = np.array([0 if s == "keep" else self.id(s) for s in b.palette], np.int64)
        m = got != 0
        sub[m] = remap[got[m]].astype(np.uint16)
        for (x, y, z), snbt in b.block_entities.items():
            self.be[(x, y, z)] = snbt
        for e in b.entities:
            self.ents.append(dict(e))
        return rec


def kit_build(name="parca"):
    from usta.kit.core import Build
    return Build(name, db=DB)


def offset():
    """Tasarim cercevesinden dunyaya kaydirma (dx, dz): AA_OFFSET="dx,dz" ya da konum.json; varsayilan (0, 0)."""
    env = os.environ.get("AA_OFFSET")
    if env:
        a, b = env.split(",")
        return int(a), int(b)
    p = os.path.join(HERE, "konum.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        return int(d["dx"]), int(d["dz"])
    return 0, 0


# yerlestirme: tasarim cercevesi (giris AX,AZ, yuz doguya) -> dunya (giris AXW,AZW, k kez 90 derece saat yonu)
PLACE = {"k": None, "ax": None, "az": None}
K_OF = {"east": 0, "south": 1, "west": 2, "north": 3}


def set_place(k, ax, az):
    PLACE.update(k=int(k) % 4, ax=int(ax), az=int(az))


def place():
    """(k, dunyada giris x, dunyada giris z). Ayarlanmadiysa konum.json kaydirmasi (k = 0)."""
    if PLACE["k"] is None:
        dx, dz = offset()
        return 0, AX + dx, AZ + dz
    return PLACE["k"], PLACE["ax"], PLACE["az"]


def rot_xz(x, z, k):
    for _ in range(k % 4):
        x, z = -z, x
    return x, z


def to_world(x, z):
    """Tasarim (x, z) -> dunya (x, z); diziler de olur."""
    k, ax, az = place()
    rx, rz = rot_xz(np.asarray(x) - AX, np.asarray(z) - AZ, k)
    return ax + rx, az + rz


def cache_dir():
    d = os.environ.get("AA_OUT") or os.path.join(os.path.expanduser(r"~\UstaOyun"), "usta", "kalp_adasi_onbellek")
    os.makedirs(d, exist_ok=True)
    return d


def load_terrain():
    """Dogal deniz tabani/zemin, tasarim cercevesine hizali: dunya sutunlari (gerekirse parcalar uretilerek) okunur,
    donusle tasarim hucrelerine orneklenir. Onbellek yerlesime ozeldir."""
    k, ax, az = place()
    dx, dz = ax - AX, az - AZ
    if k == 0 and os.path.exists(os.path.join(HERE, "arazi_onbellek.npz" if (dx, dz) == (0, 0) else f"arazi_{dx}_{dz}.npz")):
        p = os.path.join(HERE, "arazi_onbellek.npz" if (dx, dz) == (0, 0) else f"arazi_{dx}_{dz}.npz")
    else:
        p = os.path.join(cache_dir(), f"arazi_k{k}_{ax}_{az}.npz")
    if not os.path.exists(p):
        from usta.gameapi import GameAPI
        from usta.worlddata import parse_columns
        api = GameAPI(timeout=200)
        wx, wz = to_world(np.array([X0, X1, X0, X1]), np.array([Z0, Z0, Z1, Z1]))
        wx0, wx1 = int(wx.min()) - 16, int(wx.max()) + 16
        wz0, wz1 = int(wz.min()) - 16, int(wz.max()) + 16
        for x in range(wx0, wx1 + 1, 256):
            for z in range(wz0, wz1 + 1, 256):
                api.blocks(x, SEA, z, min(256, wx1 - x + 1), 1, min(256, wz1 - z + 1), timeout_ms=150000, generate=True)
        c = parse_columns(api.columns(wx0, wz0, wx1, wz1, timeout_ms=60000))
        water = np.array([("water" in c.palette[s]) for s in c.ground_state.ravel()]).reshape(c.ground.shape)
        XX, ZZ = np.meshgrid(np.arange(X0, X1 + 1), np.arange(Z0, Z1 + 1))
        WX, WZ = to_world(XX, ZZ)
        ii, jj = WZ - c.z0, WX - c.x0
        np.savez_compressed(p, x0=X0, z0=Z0, surface=c.surface[ii, jj], ground=c.ground[ii, jj], floor=c.floor[ii, jj],
                            water=water[ii, jj])
    d = np.load(p)
    x0, z0 = int(d["x0"]), int(d["z0"])
    sl = (slice(Z0 - z0, Z1 - z0 + 1), slice(X0 - x0, X1 - x0 + 1))
    out = {k_: d[k_][sl] for k_ in ("surface", "ground", "floor", "water")}
    unk = out["surface"] == -32768
    if unk.any():                      # bilinmeyen sutunlar: acik deniz varsay
        out["floor"] = np.where(unk, 45, out["floor"])
        out["surface"] = np.where(unk, SEA, out["surface"])
        out["ground"] = np.where(unk, SEA, out["ground"])
    return out
