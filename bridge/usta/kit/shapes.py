"""shapes: vektorlu (numpy) voksel geometri. Her uretec bir `Shape` dondurur: mask[y, z, x] (bool) + origin (x0, y0, z0).

Kullanim:  from usta.kit import shapes as S
    S.sphere((10, 5, 10), 4).shell().put(b, "white_concrete")      # dolu -> kabuk -> yaz
    S.cylinder((0, 0, 0), (0, 12, 0), r=3, hollow=True).put_style(b, st, "wall")   # Style dokusuyla
    (S.box(0, 0, 0, 9, 4, 9) - S.box(1, 1, 1, 8, 4, 8)).put(b, "stone_bricks")      # | & - ^ islemleri

Shape:  .mask .origin .bbox (siki) .count() .empty() .tight() .moved(dx,dy,dz) .crop(x0,y0,z0,x1,y1,z1)
        .shell(t=1, axes="xyz") .erode(t, axes) .dilate(t, axes) .surface(dir) (dir: up/down/north/south/east/west)
        .where(fn(X,Y,Z)->bool) .layer(y) .coords() -> (N,3) xyz   .put(b, state, only_empty=False)
        .put_style(b, style, role, only_empty=False)   A|B  A&B  A-B  A^B
Uretecler (uclar dahil, koordinatlar hucre merkezi; yaricap r -> d^2 <= r^2 + r):
  box(x0,y0,z0,x1,y1,z1)            shell_box(..., t=1, top=True, bottom=True)
  cylinder(p0, p1, r, hollow=False, t=1)   eksen p0->p1 (herhangi yon; eksene paralelse kusursuz daire)
  disk((cx,y,cz), r)   ring((cx,y,cz), r_out, r_in, h=1)   ellipse(cx, y, cz, rx, rz)   ellipse_box(x0,z0,x1,z1,y)
  sphere(c, r)   ellipsoid(c, rx, ry, rz)   blob(c, r, rough=.35, seed=0, scale=None)  (gurultulu organik kure)
  cone(base_c, r, h)   revolve(base_c, radii)  (her y katmani icin yaricap listesi; <0 = bos)
  dome(base_c, r, h=None, kind="hemi"|"onion"|"pointed"|"cone"|"bell")   torus(c, R, r)
  arch_profile(w, h, kind="round"|"pointed"|"segmental"|"ogee"|"flat", p=.5) -> 2B ndarray [v,u] (True = aciklik)
  arch(x, y, z, w, h, kind, depth=1, axis="x")   (aciklik hacmi; axis: aciklik genisligi x mi z mi boyunca)
  profile(prof2d[v,u], x, y, z, axis="x", depth=1)   2B profili duvar duzlemine koyup kalinlikta uzatir
  polygon(points[(x,z)...], y0, y1)   extrude(shape, n, axis="y")
  line(p0, p1, r=.5)   polyline(points, r=.5)   spline(points, r=.5, closed=False)  (Catmull-Rom)
  field(x0,y0,z0,x1,y1,z1, fn(X,Y,Z)->bool)   grid(x0,y0,z0,x1,y1,z1) -> X,Y,Z (yayinlanabilir)
Gurultu (deterministik, tohumlu): hash01(x,y,z,seed)  noise(x,y,z, scale=8, seed=0, octaves=1)  noise_box(box, scale, seed, octaves)
  scatter(shape, density, seed) -> xyz listesi (deterministik nokta serpme; cicek, kaya, agac yeri icin)
"""
from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import numpy as np

__all__ = [
    "Shape", "grid", "field", "box", "shell_box", "cylinder", "disk", "ring", "ellipse", "ellipse_box", "sphere",
    "ellipsoid", "blob", "cone", "revolve", "dome", "torus", "arch_profile", "arch", "profile", "polygon", "extrude",
    "line", "polyline", "spline", "hash01", "noise", "noise_box", "scatter", "catmull_rom",
]

_AX = {"x": 2, "y": 0, "z": 1}


# ====================================================================== Shape
class Shape:
    """Boolean voksel maskesi: mask[y, z, x], origin = (x0, y0, z0) (dizinin (0,0,0) hucresinin yapi koordinati)."""
    __slots__ = ("mask", "origin")

    def __init__(self, mask: np.ndarray, origin: Sequence[int] = (0, 0, 0)):
        m = np.asarray(mask, dtype=bool)
        if m.ndim != 3:
            raise ValueError("Shape maskesi 3 boyutlu olmali [y, z, x]")
        self.mask = m
        self.origin = (int(origin[0]), int(origin[1]), int(origin[2]))

    # ------------------------------------------------------------- olcu
    @property
    def extent(self) -> tuple[int, int, int, int, int, int]:
        """Dizinin tam kutusu (bos hucreler dahil)."""
        x0, y0, z0 = self.origin
        sy, sz, sx = self.mask.shape
        return x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1

    @property
    def bbox(self) -> tuple[int, int, int, int, int, int] | None:
        """Dolu hucrelerin siki kutusu (x0,y0,z0,x1,y1,z1) ya da None."""
        if not self.mask.any():
            return None
        ys = np.nonzero(self.mask.any(axis=(1, 2)))[0]
        zs = np.nonzero(self.mask.any(axis=(0, 2)))[0]
        xs = np.nonzero(self.mask.any(axis=(0, 1)))[0]
        x0, y0, z0 = self.origin
        return (x0 + int(xs[0]), y0 + int(ys[0]), z0 + int(zs[0]), x0 + int(xs[-1]), y0 + int(ys[-1]), z0 + int(zs[-1]))

    def count(self) -> int:
        return int(np.count_nonzero(self.mask))

    def empty(self) -> bool:
        return not self.mask.any()

    def __repr__(self) -> str:
        return f"Shape(cells={self.count()}, bbox={self.bbox})"

    def copy(self) -> "Shape":
        return Shape(self.mask.copy(), self.origin)

    def tight(self) -> "Shape":
        b = self.bbox
        if b is None:
            return Shape(np.zeros((1, 1, 1), bool), self.origin)
        return self.crop(*b)

    def moved(self, dx: int = 0, dy: int = 0, dz: int = 0) -> "Shape":
        x0, y0, z0 = self.origin
        return Shape(self.mask, (x0 + dx, y0 + dy, z0 + dz))

    def crop(self, x0, y0, z0, x1, y1, z1) -> "Shape":
        """Verilen kutuyla kesisim (kutu disi atilir); sonuc tam olarak o kutu boyutundadir."""
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        z0, z1 = sorted((int(z0), int(z1)))
        out = np.zeros((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), dtype=bool)
        _blit(out, (x0, y0, z0), self.mask, self.origin)
        return Shape(out, (x0, y0, z0))

    # ------------------------------------------------------------- koordinat yardimcilari
    def grid(self):
        """Bu seklin dizi kutusu icin yayinlanabilir X, Y, Z koordinat dizileri."""
        return grid(*self.extent)

    def where(self, fn: Callable) -> "Shape":
        """fn(X, Y, Z) -> bool dizisi; mask & fn."""
        X, Y, Z = self.grid()
        return Shape(self.mask & np.broadcast_to(fn(X, Y, Z), self.mask.shape), self.origin)

    def layer(self, y: int) -> "Shape":
        x0, y0, z0, x1, y1, z1 = self.extent
        return self.crop(x0, y, z0, x1, y, z1)

    def coords(self) -> np.ndarray:
        """(N, 3) tamsayi dizi: her dolu hucrenin (x, y, z)'si (y, z, x sirasiyla siralanmis)."""
        ys, zs, xs = np.nonzero(self.mask)
        x0, y0, z0 = self.origin
        return np.stack([xs + x0, ys + y0, zs + z0], axis=1)

    # ------------------------------------------------------------- morfoloji
    def erode(self, t: int = 1, axes: str = "xyz", diag: bool = False) -> "Shape":
        """t kez asindirma. diag=True: kose komsulari da sayilir (kabuk kalin koseli, yuz-bagli olur)."""
        m = self.mask
        ry = (-1, 0, 1) if "y" in axes else (0,)
        rz = (-1, 0, 1) if "z" in axes else (0,)
        rx = (-1, 0, 1) if "x" in axes else (0,)
        for _ in range(int(t)):
            p = np.pad(m, 1, constant_values=False)
            sy, sz, sx = m.shape
            r = m.copy()
            for dy in ry:
                for dz in rz:
                    for dx in rx:
                        nz_ = (dy != 0) + (dz != 0) + (dx != 0)
                        if nz_ == 0 or (not diag and nz_ > 1):
                            continue
                        r &= p[1 + dy:1 + dy + sy, 1 + dz:1 + dz + sz, 1 + dx:1 + dx + sx]
            m = r
        return Shape(m, self.origin)

    def dilate(self, t: int = 1, axes: str = "xyz") -> "Shape":
        t = int(t)
        if t <= 0:
            return self.copy()
        py = t if "y" in axes else 0
        pz = t if "z" in axes else 0
        px = t if "x" in axes else 0
        m = np.pad(self.mask, ((py, py), (pz, pz), (px, px)), constant_values=False)
        for _ in range(t):
            r = m.copy()
            if "y" in axes:
                r[1:] |= m[:-1]
                r[:-1] |= m[1:]
            if "z" in axes:
                r[:, 1:] |= m[:, :-1]
                r[:, :-1] |= m[:, 1:]
            if "x" in axes:
                r[:, :, 1:] |= m[:, :, :-1]
                r[:, :, :-1] |= m[:, :, 1:]
            m = r
        x0, y0, z0 = self.origin
        return Shape(m, (x0 - px, y0 - py, z0 - pz))

    def shell(self, t: int = 1, axes: str = "xyz", diag: bool = False) -> "Shape":
        """Disa en fazla t hucre uzakliktaki dolu hucreler (kabuk). axes='xz': yalniz yanlar (ust/alt acik kalir).
        diag=True: kalin koseli (yuz-bagli) kabuk -- kule duvari gibi."""
        return Shape(self.mask & ~self.erode(t, axes, diag).mask, self.origin)

    def surface(self, direction: str = "up") -> "Shape":
        """O yondeki komsusu bos olan dolu hucreler (ust yuzey, cephe yuzeyi...)."""
        d = {"up": (0, 1, 0), "down": (0, -1, 0), "north": (0, 0, -1), "south": (0, 0, 1),
             "east": (1, 0, 0), "west": (-1, 0, 0)}[direction]
        dx, dy, dz = d
        p = np.pad(self.mask, 1, constant_values=False)
        sy, sz, sx = self.mask.shape
        nb = p[1 + dy:1 + dy + sy, 1 + dz:1 + dz + sz, 1 + dx:1 + dx + sx]
        return Shape(self.mask & ~nb, self.origin)

    # ------------------------------------------------------------- kume islemleri
    def _binop(self, other: "Shape", op) -> "Shape":
        a0 = self.extent
        b0 = other.extent
        x0, y0, z0 = min(a0[0], b0[0]), min(a0[1], b0[1]), min(a0[2], b0[2])
        x1, y1, z1 = max(a0[3], b0[3]), max(a0[4], b0[4]), max(a0[5], b0[5])
        A = np.zeros((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), dtype=bool)
        B = np.zeros_like(A)
        _blit(A, (x0, y0, z0), self.mask, self.origin)
        _blit(B, (x0, y0, z0), other.mask, other.origin)
        return Shape(op(A, B), (x0, y0, z0))

    def __or__(self, other: "Shape") -> "Shape":
        return self._binop(other, np.logical_or)

    def __and__(self, other: "Shape") -> "Shape":
        return self._binop(other, np.logical_and)

    def __sub__(self, other: "Shape") -> "Shape":
        return self._binop(other, lambda a, b: a & ~b)

    def __xor__(self, other: "Shape") -> "Shape":
        return self._binop(other, np.logical_xor)

    # ------------------------------------------------------------- yazma
    def put(self, b, state, only_empty: bool = False) -> "Shape":
        """Dolu hucrelere tek durum yazar (Build.put_mask)."""
        if self.mask.any():
            x0, y0, z0 = self.origin
            b.put_mask(x0, y0, z0, self.mask, state, only_empty=only_empty)
        return self

    def put_style(self, b, style, role: str, only_empty: bool = False) -> "Shape":
        """Style dokusuyla yazar (rol varyantlari agirlikli ve deterministik karisir)."""
        style.put(b, self, role, only_empty=only_empty)
        return self


def _blit(dst: np.ndarray, dst_origin, src: np.ndarray, src_origin) -> None:
    """src'yi dst'ye OR'lar (kesisim kadar)."""
    dx0, dy0, dz0 = dst_origin
    sx0, sy0, sz0 = src_origin
    sy, sz, sx = src.shape
    ty, tz, tx = dst.shape
    ox, oy, oz = sx0 - dx0, sy0 - dy0, sz0 - dz0
    ay, az, ax = max(0, oy), max(0, oz), max(0, ox)
    by, bz, bx = min(ty, oy + sy), min(tz, oz + sz), min(tx, ox + sx)
    if ay >= by or az >= bz or ax >= bx:
        return
    dst[ay:by, az:bz, ax:bx] |= src[ay - oy:by - oy, az - oz:bz - oz, ax - ox:bx - ox]


# ====================================================================== temel uretecler
def grid(x0, y0, z0, x1, y1, z1):
    """Kutudaki hucre koordinatlari: X (1,1,nx), Y (ny,1,1), Z (1,nz,1) -- yayinlanabilir float diziler."""
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((int(y0), int(y1)))
    z0, z1 = sorted((int(z0), int(z1)))
    X = np.arange(x0, x1 + 1, dtype=np.float64)[None, None, :]
    Y = np.arange(y0, y1 + 1, dtype=np.float64)[:, None, None]
    Z = np.arange(z0, z1 + 1, dtype=np.float64)[None, :, None]
    return X, Y, Z


def field(x0, y0, z0, x1, y1, z1, fn: Callable) -> Shape:
    """Kutu uzerinde fn(X, Y, Z) -> bool ile tanimli sekil."""
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((int(y0), int(y1)))
    z0, z1 = sorted((int(z0), int(z1)))
    X, Y, Z = grid(x0, y0, z0, x1, y1, z1)
    shape = (y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1)
    m = np.broadcast_to(np.asarray(fn(X, Y, Z), dtype=bool), shape).copy()
    return Shape(m, (x0, y0, z0))


def box(x0, y0, z0, x1, y1, z1) -> Shape:
    x0, x1 = sorted((int(x0), int(x1)))
    y0, y1 = sorted((int(y0), int(y1)))
    z0, z1 = sorted((int(z0), int(z1)))
    return Shape(np.ones((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), dtype=bool), (x0, y0, z0))


def shell_box(x0, y0, z0, x1, y1, z1, t: int = 1, top: bool = True, bottom: bool = True) -> Shape:
    """Kutu kabugu (kalinlik t). top/bottom=False: tavan/taban acik."""
    s = box(x0, y0, z0, x1, y1, z1)
    m = s.mask.copy()
    t = int(t)
    inner = np.zeros_like(m)
    inner[:, t:-t or None, t:-t or None] = True
    if top:
        inner[-t:] = False
    if bottom:
        inner[:t] = False
    m &= ~inner
    return Shape(m, s.origin)


def _r2(r: float) -> float:
    """Voksel daire esigi: d^2 <= (r+.5)^2 - .25 (= r^2 + r): klasik guzel daireler."""
    return (r + 0.5) ** 2 - 0.25 + 1e-9


def cylinder(p0: Sequence[float], p1: Sequence[float], r: float, hollow: bool = False, t: int = 1, thick: bool = True) -> Shape:
    """p0 -> p1 eksenli silindir (uclar dahil). hollow: t kalinlikta boru (uclari acik).
    thick=True (eksene paralel borularda): kose hucreleri dolu, yuz-bagli duvar (usta kule duvari)."""
    p0 = np.asarray(p0, dtype=np.float64)
    p1 = np.asarray(p1, dtype=np.float64)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    dh = d / L if L > 1e-9 else np.array([0.0, 1.0, 0.0])
    pad = r + 1.5
    lo = np.floor(np.minimum(p0, p1) - pad).astype(int)
    hi = np.ceil(np.maximum(p0, p1) + pad).astype(int)
    rr_out = _r2(r)
    rr_in = _r2(r - t) if (hollow and r - t >= 0) else -1.0

    def fn(X, Y, Z):
        vx, vy, vz = X - p0[0], Y - p0[1], Z - p0[2]
        s = vx * dh[0] + vy * dh[1] + vz * dh[2]
        px, py, pz = vx - s * dh[0], vy - s * dh[1], vz - s * dh[2]
        q = px * px + py * py + pz * pz
        m = (q <= rr_out) & (s >= -0.5 + 1e-6) & (s <= L + 0.5 - 1e-6)
        if hollow and not aligned:
            m &= q > rr_in
        return m
    aligned = hollow and thick and int(np.count_nonzero(np.abs(dh) > 1e-9)) == 1
    out = field(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2], fn)
    if aligned:
        ax = "xyz"[int(np.argmax(np.abs(dh)))]
        plane = "".join(a for a in "xyz" if a != ax)
        out = out.shell(int(t), axes=plane, diag=True)
    return out.tight()


def disk(c: Sequence[float], r: float) -> Shape:
    """Yatay disk (tek katman, y = c[1])."""
    cx, cy, cz = c
    return cylinder((cx, cy, cz), (cx, cy, cz), r)


def ring(c: Sequence[float], r_out: float, r_in: float, h: int = 1, thick: bool = True) -> Shape:
    """Yatay halka: r_in < d <= r_out, y = c[1] .. c[1]+h-1 (thick: kose dolu, yuz-bagli)."""
    cx, cy, cz = c
    return cylinder((cx, cy, cz), (cx, cy + h - 1, cz), r_out, hollow=True, t=max(1, int(round(r_out - r_in))), thick=thick)


def ellipse(cx: float, y: int, cz: float, rx: float, rz: float) -> Shape:
    """Yatay elips (tek katman)."""
    x0, x1 = int(math.floor(cx - rx - 1)), int(math.ceil(cx + rx + 1))
    z0, z1 = int(math.floor(cz - rz - 1)), int(math.ceil(cz + rz + 1))
    ax, az = rx + 0.5, rz + 0.5
    return field(x0, y, z0, x1, y, z1, lambda X, Y, Z: ((X - cx) / ax) ** 2 + ((Z - cz) / az) ** 2 <= 1.0 - 0.25 / (ax * az) + 1e-9).tight()


def ellipse_box(x0: int, z0: int, x1: int, z1: int, y: int) -> Shape:
    """Kutuya teget yatay elips (her parite icin dogru merkez)."""
    x0, x1 = sorted((x0, x1))
    z0, z1 = sorted((z0, z1))
    return ellipse((x0 + x1) / 2, y, (z0 + z1) / 2, (x1 - x0) / 2, (z1 - z0) / 2)


def sphere(c: Sequence[float], r: float) -> Shape:
    return ellipsoid(c, r, r, r)


def ellipsoid(c: Sequence[float], rx: float, ry: float, rz: float) -> Shape:
    cx, cy, cz = c
    ax, ay, az = rx + 0.5, ry + 0.5, rz + 0.5
    lo = (int(math.floor(cx - ax)), int(math.floor(cy - ay)), int(math.floor(cz - az)))
    hi = (int(math.ceil(cx + ax)), int(math.ceil(cy + ay)), int(math.ceil(cz + az)))
    thr = 1.0 - 0.25 / max(1e-6, min(ax, ay, az)) ** 2 + 1e-9
    return field(*lo, *hi, lambda X, Y, Z: ((X - cx) / ax) ** 2 + ((Y - cy) / ay) ** 2 + ((Z - cz) / az) ** 2 <= thr).tight()


def revolve(base_c: Sequence[float], radii: Sequence[float]) -> Shape:
    """Dikey donel cisim: radii[i] = y = base_c[1] + i katmanindaki yaricap (negatif = bos katman)."""
    cx, cy, cz = base_c
    radii = np.asarray(list(radii), dtype=np.float64)
    if len(radii) == 0:
        return Shape(np.zeros((1, 1, 1), bool), (int(cx), int(cy), int(cz)))
    R = max(0.0, float(radii.max()))
    x0, x1 = int(math.floor(cx - R - 1)), int(math.ceil(cx + R + 1))
    z0, z1 = int(math.floor(cz - R - 1)), int(math.ceil(cz + R + 1))
    y0 = int(cy)
    y1 = y0 + len(radii) - 1
    thr = np.where(radii >= 0, (radii + 0.5) ** 2 - 0.25 + 1e-9, -1.0)[:, None, None]
    return field(x0, y0, z0, x1, y1, z1, lambda X, Y, Z: (X - cx) ** 2 + (Z - cz) ** 2 <= thr).tight()


def cone(base_c: Sequence[float], r: float, h: int) -> Shape:
    """Tepesi yukari koni: tabanda r, en ustte tek hucre (h katman)."""
    h = max(1, int(h))
    if h == 1:
        return revolve(base_c, [r])
    radii = [r * (h - 1 - i) / (h - 1) for i in range(h)]
    return revolve(base_c, radii)


_ONION_T = [0.0, 0.12, 0.3, 0.45, 0.6, 0.72, 0.82, 0.9, 1.0]
_ONION_F = [0.86, 1.04, 1.14, 1.08, 0.82, 0.5, 0.24, 0.1, 0.0]


def _dome_radii(r: float, h: int, kind: str) -> list[float]:
    out = []
    for i in range(h):
        t = (i + 0.5) / h  # 0..1 katman merkezi
        if kind == "hemi":
            f = math.sqrt(max(0.0, 1.0 - t * t))
        elif kind == "onion":
            # boyun -> ~%35'te sisme -> hizla iceri -> ince sivri uc (ters egrilik)
            f = float(np.interp(t, _ONION_T, _ONION_F))
        elif kind == "pointed":
            # iki merkezli sivri kubbe kesiti (p=.5)
            p = 0.5
            R = 1.0 + p
            hh = math.sqrt(R * R - p * p)
            y = t * hh
            f = max(0.0, math.sqrt(max(0.0, R * R - y * y)) - p)
        elif kind == "bell":
            f = 1.0 - t ** 2.2 if t < 0.85 else (1.0 - t) * 3.0
        elif kind == "cone":
            f = 1.0 - t
        else:
            raise ValueError(f"bilinmeyen kubbe turu: {kind}")
        out.append(r * f)
    return out


def dome(base_c: Sequence[float], r: float, h: int | None = None, kind: str = "hemi") -> Shape:
    """Kubbe (dolu). kind: hemi (yarim kure/elipsoit), onion (sogan), pointed (sivri), bell (can), cone.
    base_c = taban merkezi (taban katmani dahil). h verilmezse tur icin dogal yukseklik."""
    if h is None:
        h = {"hemi": int(round(r)) + 1, "onion": int(round(r * 2.1)) + 1, "pointed": int(round(r * 1.5)) + 1,
             "bell": int(round(r * 1.3)) + 1, "cone": int(round(r * 1.6)) + 1}.get(kind, int(r) + 1)
    h = max(1, int(h))
    return revolve(base_c, _dome_radii(r, h, kind))


def torus(c: Sequence[float], R: float, r: float) -> Shape:
    """Yatay simit: merkez cemberi R, kesit yaricapi r."""
    cx, cy, cz = c
    pad = R + r + 1.5
    lo = (int(math.floor(cx - pad)), int(math.floor(cy - r - 1)), int(math.floor(cz - pad)))
    hi = (int(math.ceil(cx + pad)), int(math.ceil(cy + r + 1)), int(math.ceil(cz + pad)))
    rr = _r2(r)

    def fn(X, Y, Z):
        q = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2) - R
        return q * q + (Y - cy) ** 2 <= rr
    return field(*lo, *hi, fn).tight()


# ====================================================================== kemer profilleri
def _arch_halfwidth(kind: str, a: float, rise: float, p: float):
    """v (yay tabanindan yukari, surekli) -> yari genislik."""
    if kind == "round":
        return lambda v: np.sqrt(np.clip(a * a - v * v, 0, None))
    if kind == "segmental":
        R = (a * a + rise * rise) / (2 * rise)
        c = rise - R
        return lambda v: np.sqrt(np.clip(R * R - (v - c) ** 2, 0, None))
    if kind == "pointed":
        R = a * (1 + p)
        return lambda v: np.clip(np.sqrt(np.clip(R * R - v * v, 0, None)) - a * p, 0, None)
    if kind == "ogee":
        return lambda v: a * 0.5 * (1 + np.cos(np.pi * np.clip(v / rise, 0, 1)))
    raise ValueError(f"bilinmeyen kemer turu: {kind}")


def arch_rise(w: int, kind: str = "round", p: float = 0.5) -> int:
    """Kemer egrisinin hucre cinsinden yuksekligi (yay tabanindan tepeye)."""
    a = w / 2.0
    if kind == "flat":
        return 0
    if kind == "round":
        r = a
    elif kind == "segmental":
        r = max(1.0, a * 0.5)
    elif kind == "pointed":
        r = a * math.sqrt(1 + 2 * p)
    elif kind == "ogee":
        r = a * 1.6
    else:
        raise ValueError(f"bilinmeyen kemer turu: {kind}")
    return max(1, int(round(r)))


def arch_profile(w: int, h: int, kind: str = "round", p: float = 0.5, ss: int = 4) -> np.ndarray:
    """Kemerli acikligin 2B maskesi [v, u] (v=0 en alt sira; True = acik). w genislik, h toplam yukseklik.
    kind: round (yarim daire), pointed (sivri/Osmanli, p sivrilik 0..1), segmental (basik),
    ogee (kas kemer), flat (dikdortgen). Hucreler yuzde 50'den fazla icerideyse acik sayilir (alt-ornekleme)."""
    w, h = int(w), int(h)
    out = np.zeros((h, w), dtype=bool)
    if w <= 0 or h <= 0:
        return out
    if kind == "flat" or w == 1:
        out[:] = True
        return out
    a = w / 2.0
    rise = min(arch_rise(w, kind, p), max(1, h - 1))
    spring = h - rise
    hw = _arch_halfwidth(kind, a, float(rise), p)
    # alt-ornekleme
    us = (np.arange(w * ss) + 0.5) / ss
    vs = (np.arange(h * ss) + 0.5) / ss
    U, V = np.meshgrid(us, vs)
    vrel = V - spring
    inside = np.where(vrel <= 0, True, np.abs(U - a) <= hw(np.maximum(vrel, 0)))
    cov = inside.reshape(h, ss, w, ss).mean(axis=(1, 3))
    out = cov > 0.5
    out[: max(0, spring), :] = True
    # tepe sirasi bos kalmasin: en az tek hucre
    if not out[-1].any():
        out[-1, (w - 1) // 2: w // 2 + 1] = True
    return out


def profile(prof: np.ndarray, x: int, y: int, z: int, axis: str = "x", depth: int = 1) -> Shape:
    """2B profil [v, u] -> duvar duzleminde sekil. axis='x': u yapinin x'i boyunca (kuzey/guney cephesi),
    derinlik +z yonunde `depth` hucre; axis='z': u z boyunca, derinlik +x yonunde. (x,y,z) = u=0,v=0 hucresi."""
    prof = np.asarray(prof, dtype=bool)
    hv, wu = prof.shape
    depth = max(1, int(depth))
    if axis == "x":
        m = np.repeat(prof[:, None, :], depth, axis=1)          # [y, z, x]
    elif axis == "z":
        m = np.repeat(prof[:, :, None], depth, axis=2)          # [y, z(u), x(depth)]
    else:
        raise ValueError("axis 'x' ya da 'z' olmali")
    return Shape(m, (x, y, z))


def arch(x: int, y: int, z: int, w: int, h: int, kind: str = "round", depth: int = 1, axis: str = "x", p: float = 0.5) -> Shape:
    """Kemerli aciklik hacmi (kesmek ya da cam koymak icin). Bkz. arch_profile, profile."""
    return profile(arch_profile(w, h, kind, p), x, y, z, axis, depth)


# ====================================================================== cokgen / ekstruzyon
def polygon(points: Sequence[Sequence[float]], y0: int, y1: int | None = None, edges: bool = True) -> Shape:
    """(x, z) cokgeni (cift-tek kurali) y0..y1 boyunca dolu prizma. edges: kenar hucreleri dahil."""
    if y1 is None:
        y1 = y0
    P = np.asarray(points, dtype=np.float64)
    x0, x1 = int(math.floor(P[:, 0].min())), int(math.ceil(P[:, 0].max()))
    z0, z1 = int(math.floor(P[:, 1].min())), int(math.ceil(P[:, 1].max()))
    xs = np.arange(x0, x1 + 1, dtype=np.float64)
    zs = np.arange(z0, z1 + 1, dtype=np.float64)
    X, Z = np.meshgrid(xs, zs)  # [z, x]
    inside = np.zeros(X.shape, dtype=bool)
    n = len(P)
    near = np.zeros(X.shape, dtype=bool)
    for i in range(n):
        ax_, az_ = P[i]
        bx_, bz_ = P[(i + 1) % n]
        cond = (az_ > Z) != (bz_ > Z)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (bx_ - ax_) * (Z - az_) / (bz_ - az_ + 1e-300) + ax_
        inside ^= cond & (X < xint)
        if edges:
            ex, ez = bx_ - ax_, bz_ - az_
            L2 = ex * ex + ez * ez
            if L2 < 1e-12:
                d2 = (X - ax_) ** 2 + (Z - az_) ** 2
            else:
                tt = np.clip(((X - ax_) * ex + (Z - az_) * ez) / L2, 0, 1)
                d2 = (X - ax_ - tt * ex) ** 2 + (Z - az_ - tt * ez) ** 2
            near |= d2 <= 0.25 + 1e-9
    m2 = inside | near
    y0, y1 = sorted((int(y0), int(y1)))
    m = np.repeat(m2[None, :, :], y1 - y0 + 1, axis=0)
    return Shape(m, (x0, y0, z0)).tight()


def extrude(shape: Shape, n: int, axis: str = "y") -> Shape:
    """Seklin o eksendeki ilk katmanini n kez tekrarlar (2B profilden prizma)."""
    ai = _AX[axis]
    sl = [slice(None)] * 3
    sl[ai] = slice(0, 1)
    base = shape.mask[tuple(sl)]
    reps = [1, 1, 1]
    reps[ai] = int(n)
    return Shape(np.tile(base, reps), shape.origin)


# ====================================================================== cizgiler / egriler
def _capsules(segs: np.ndarray, r: float) -> Shape:
    """segs: (K, 2, 3) dogru parcalari; her parcaya r uzakliktaki hucreler."""
    pts = segs.reshape(-1, 3)
    pad = r + 1.0
    lo = np.floor(pts.min(axis=0) - pad).astype(int)
    hi = np.ceil(pts.max(axis=0) + pad).astype(int)
    X, Y, Z = grid(lo[0], lo[1], lo[2], hi[0], hi[1], hi[2])
    shape = (hi[1] - lo[1] + 1, hi[2] - lo[2] + 1, hi[0] - lo[0] + 1)
    m = np.zeros(shape, dtype=bool)
    if r <= 0.5 + 1e-9:
        # ince cizgi: DDA ornekleme (bosluksuz, ana eksende adim basina tek hucre)
        for a, b in segs:
            n = int(np.ceil(np.abs(b - a).max())) + 1
            t = np.linspace(0.0, 1.0, max(2, n))[:, None]
            P = np.floor(a[None, :] + (b - a)[None, :] * t + 0.5).astype(int) - lo
            m[P[:, 1], P[:, 2], P[:, 0]] = True
        return Shape(m, tuple(lo)).tight()
    rr = (r + 1e-6) ** 2
    for a, b in segs:
        d = b - a
        L2 = float(d @ d)
        # yalniz parcanin kutusunda hesapla (hiz)
        slo = np.floor(np.minimum(a, b) - pad).astype(int) - lo
        shi = np.ceil(np.maximum(a, b) + pad).astype(int) - lo + 1
        xs, ys, zs = X[:, :, slo[0]:shi[0]], Y[slo[1]:shi[1]], Z[:, slo[2]:shi[2]]
        vx, vy, vz = xs - a[0], ys - a[1], zs - a[2]
        if L2 < 1e-12:
            q = vx * vx + vy * vy + vz * vz
        else:
            t = np.clip((vx * d[0] + vy * d[1] + vz * d[2]) / L2, 0, 1)
            qx, qy, qz = vx - t * d[0], vy - t * d[1], vz - t * d[2]
            q = qx * qx + qy * qy + qz * qz
        m[slo[1]:shi[1], slo[2]:shi[2], slo[0]:shi[0]] |= q <= rr
    return Shape(m, tuple(lo)).tight()


def line(p0: Sequence[float], p1: Sequence[float], r: float = 0.5) -> Shape:
    """Kalin dogru (kapsul). r=.5: ince (26-bagli), r=.75: yuz-bagli (yurunebilir/kesintisiz)."""
    return _capsules(np.asarray([[p0, p1]], dtype=np.float64), r)


def polyline(points: Sequence[Sequence[float]], r: float = 0.5, closed: bool = False) -> Shape:
    P = np.asarray(points, dtype=np.float64)
    if len(P) == 1:
        return line(P[0], P[0], r)
    if closed:
        P = np.vstack([P, P[:1]])
    segs = np.stack([P[:-1], P[1:]], axis=1)
    return _capsules(segs, r)


def catmull_rom(points: Sequence[Sequence[float]], samples: int = 8, closed: bool = False) -> np.ndarray:
    """Catmull-Rom egrisi (noktalardan gecer) -> yogun nokta dizisi (N, 3)."""
    P = np.asarray(points, dtype=np.float64)
    if len(P) < 2:
        return P.copy()
    if closed:
        ext = np.vstack([P[-1:], P, P[:2]])
        nseg = len(P)
    else:
        ext = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        nseg = len(P) - 1
    out = []
    ts = np.linspace(0, 1, max(2, samples), endpoint=False)[:, None]
    for i in range(nseg):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        t2, t3 = ts * ts, ts * ts * ts
        pt = 0.5 * ((2 * p1) + (-p0 + p2) * ts + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
        out.append(pt)
    out.append(P[:1] if closed else P[-1:])
    return np.vstack(out)


def spline(points: Sequence[Sequence[float]], r: float = 0.5, closed: bool = False, samples: int | None = None) -> Shape:
    """Noktalardan gecen yumusak egri (Catmull-Rom), kalinlik r."""
    P = np.asarray(points, dtype=np.float64)
    if samples is None:
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1).max() if len(P) > 1 else 1.0
        samples = int(max(4, min(64, seg * 2)))
    C = catmull_rom(P, samples, closed)
    return polyline(C, r)


# ====================================================================== gurultu
_M1, _M2, _M3, _M4 = np.uint32(0x8DA6B343), np.uint32(0xD8163841), np.uint32(0xCB1AB31F), np.uint32(0x165667B1)
_F1, _F2 = np.uint32(0x7FEB352D), np.uint32(0x846CA68B)


def _u32(a) -> np.ndarray:
    return (np.asarray(a, dtype=np.int64) & 0xFFFFFFFF).astype(np.uint32)


def _hash_u32(x, y, z, seed: int = 0) -> np.ndarray:
    with np.errstate(over="ignore"):
        h = _u32(x) * _M1 + _u32(y) * _M2 + _u32(z) * _M3 + _u32(np.int64(seed)) * _M4
        h = np.atleast_1d(h).astype(np.uint32)
        h ^= h >> np.uint32(16)
        h *= _F1
        h ^= h >> np.uint32(15)
        h *= _F2
        h ^= h >> np.uint32(16)
    return h


def hash01(x, y, z, seed: int = 0) -> np.ndarray:
    """Tamsayi koordinatlar icin deterministik [0,1) degerleri (yayinlanabilir)."""
    x, y, z = np.broadcast_arrays(np.asarray(x), np.asarray(y), np.asarray(z))
    h = _hash_u32(np.floor(x), np.floor(y), np.floor(z), seed).reshape(x.shape)
    return h.astype(np.float64) / 4294967296.0


def _vnoise(x, y, z, seed: int) -> np.ndarray:
    x, y, z = np.broadcast_arrays(np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64), np.asarray(z, dtype=np.float64))
    xi, yi, zi = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - xi, y - yi, z - zi
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    fz = fz * fz * (3 - 2 * fz)
    xi, yi, zi = xi.astype(np.int64), yi.astype(np.int64), zi.astype(np.int64)

    def h(dx, dy, dz):
        return _hash_u32(xi + dx, yi + dy, zi + dz, seed).reshape(x.shape).astype(np.float64) / 4294967296.0
    c00 = h(0, 0, 0) * (1 - fx) + h(1, 0, 0) * fx
    c10 = h(0, 1, 0) * (1 - fx) + h(1, 1, 0) * fx
    c01 = h(0, 0, 1) * (1 - fx) + h(1, 0, 1) * fx
    c11 = h(0, 1, 1) * (1 - fx) + h(1, 1, 1) * fx
    c0 = c00 * (1 - fy) + c10 * fy
    c1 = c01 * (1 - fy) + c11 * fy
    return c0 * (1 - fz) + c1 * fz


def noise(x, y, z, scale: float = 8.0, seed: int = 0, octaves: int = 1, persistence: float = 0.5, lacunarity: float = 2.0) -> np.ndarray:
    """Deterministik deger gurultusu [0,1] (yumusak). scale = desen boyu (hucre). Yayinlanabilir diziler."""
    total = 0.0
    amp = 1.0
    norm = 0.0
    f = 1.0 / max(1e-6, scale)
    for o in range(max(1, int(octaves))):
        total = total + amp * _vnoise(np.asarray(x) * f, np.asarray(y) * f, np.asarray(z) * f, seed + o * 1013)
        norm += amp
        amp *= persistence
        f *= lacunarity
    return total / norm


def noise_box(bx: Sequence[int], scale: float = 8.0, seed: int = 0, octaves: int = 1) -> np.ndarray:
    """Kutu (x0,y0,z0,x1,y1,z1) icin gurultu dizisi [y, z, x]."""
    X, Y, Z = grid(*bx)
    v = noise(X, Y, Z, scale, seed, octaves)
    return np.broadcast_to(v, (Y.shape[0], Z.shape[1], X.shape[2])).copy()


def blob(c: Sequence[float], r: float, rough: float = 0.35, seed: int = 0, scale: float | None = None, squash: float = 1.0) -> Shape:
    """Organik yumru: yaricapi gurultuyle oynayan kure (kaya, cali, agac tacı). squash<1: basik."""
    cx, cy, cz = c
    if scale is None:
        scale = max(2.0, r * 0.9)
    R = r * (1 + rough) + 1
    ry = R * squash
    lo = (int(math.floor(cx - R)), int(math.floor(cy - ry)), int(math.floor(cz - R)))
    hi = (int(math.ceil(cx + R)), int(math.ceil(cy + ry)), int(math.ceil(cz + R)))

    def fn(X, Y, Z):
        d = np.sqrt((X - cx) ** 2 + ((Y - cy) / max(1e-6, squash)) ** 2 + (Z - cz) ** 2)
        n = noise(X, Y, Z, scale, seed, octaves=2)
        return d <= (r + 0.5) * (1 + rough * (2 * n - 1))
    return field(*lo, *hi, fn).tight()


def scatter(shape: Shape, density: float = 0.1, seed: int = 0, min_dist: int = 0) -> list[tuple[int, int, int]]:
    """Seklin dolu hucrelerinden deterministik secim (density olasiligi). min_dist>0: Chebyshev uzakligi seyreltme."""
    C = shape.coords()
    if len(C) == 0:
        return []
    u = hash01(C[:, 0], C[:, 1], C[:, 2], seed)
    sel = C[u < density]
    if min_dist <= 0:
        return [tuple(int(v) for v in p) for p in sel]
    out: list[tuple[int, int, int]] = []
    for p in sel:
        if all(max(abs(int(p[0]) - q[0]), abs(int(p[2]) - q[2])) > min_dist or abs(int(p[1]) - q[1]) > min_dist for q in out):
            out.append((int(p[0]), int(p[1]), int(p[2])))
    return out
