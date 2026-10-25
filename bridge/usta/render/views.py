"""Yazilimsal voksel goruntuleyici (numpy): izometrik, ortografik cepheler, ustten, kat kesiti, perspektif (DDA isin).
Deterministik; oyuncunun goruntusunu hic bozmaz. Hacim: ids[y, z, x] (palet indeksi; 0 = bos/bilinmiyor)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .colors import palette_arrays

BG = (238, 236, 230)
SKY_TOP = np.array([120, 165, 225], dtype=np.float32)
SKY_BOT = np.array([205, 222, 240], dtype=np.float32)

# gorunum turleri
CUBE, SLAB, FLAT, POST, SMALL, HIDDEN = 0, 1, 2, 3, 4, 5


def _kinds(palette: list[str]) -> np.ndarray:
    k = np.zeros(len(palette), dtype=np.int8)
    for i, s in enumerate(palette):
        n = s.lstrip("!").split("[", 1)[0]
        if n.endswith(("barrier", "structure_void", ":light")):
            k[i] = HIDDEN
        elif ("_slab" in n and "type=bottom" in s) or n.endswith(("_bed", "daylight_detector", "stonecutter", "_cake")) or n == "minecraft:cake":
            k[i] = SLAB
        elif n.endswith(("_carpet", "pressure_plate", "rail", "redstone_wire", "lily_pad", "moss_carpet")) or n.endswith(":snow"):
            k[i] = FLAT
        elif n.endswith(("_fence", "_wall", "_pane", "iron_bars", "_bars", "chain", "end_rod", "lightning_rod", "ladder", "scaffolding")) \
                or n.endswith("glass_pane"):
            k[i] = POST
        elif any(t in n for t in ("torch", "lantern", "flower", "sapling", "candle", "button", "lever", "tulip", "poppy",
                                  "dandelion", "orchid", "allium", "bluet", "daisy", "cornflower", "lily_of", "rose", "fern",
                                  "short_grass", "tall_grass", "bush", "sign", "banner", "head", "skull", "flower_pot", "potted",
                                  "mushroom", "dead_bush", "seagrass", "kelp", "vine", "sugar_cane")):
            k[i] = SMALL
    return k


class Volume:
    def __init__(self, ids: np.ndarray, palette: list[str], origin=(0, 0, 0)):
        self.ids = ids
        self.palette = palette
        self.origin = tuple(origin)
        self.pa = palette_arrays(palette)
        self.kind = _kinds(palette)
        hidden = self.kind == HIDDEN
        self.pa["solid"][hidden] = False

    @property
    def shape(self):
        return self.ids.shape

    def solid(self) -> np.ndarray:
        return self.pa["solid"][self.ids]

    def rotated(self, k: int) -> "Volume":
        """Saat yonunde (yukaridan) k*90 derece; yalniz konumlar (renkler yone bagli degil)."""
        a = self.ids
        for _ in range(k % 4):
            a = a.transpose(0, 2, 1)[:, :, ::-1]
        v = Volume.__new__(Volume)
        v.ids = np.ascontiguousarray(a)
        v.palette = self.palette
        v.origin = self.origin
        v.pa = self.pa
        v.kind = self.kind
        return v


# ------------------------------------------------------------------ izometrik
def _poly_mask(w: int, h: int, ox: float, oy: float, pts: list[tuple[float, float]]) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w]
    px = xs + 0.5 - ox
    py = ys + 0.5 - oy
    inside = np.ones((h, w), dtype=bool)
    n = len(pts)
    area = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    sgn = 1.0 if area > 0 else -1.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)
        inside &= cross * sgn >= -1e-6
    return inside


def _templates(A: int):
    """Her yuz turu icin piksel ofsetleri (du, dv) ve kenar maskesi. Referans: hucrenin (x, y+1, z) kosesi."""
    W, H = 2 * A + 2, 2 * A + 2
    ox, oy = A + 1, 1
    top = _poly_mask(W, H, ox, oy, [(0, 0), (A, A / 2), (0, A), (-A, A / 2)])
    east = _poly_mask(W, H, ox, oy, [(A, A / 2), (A, 1.5 * A), (0, 2 * A), (0, A)]) & ~top
    south = _poly_mask(W, H, ox, oy, [(-A, A / 2), (0, A), (0, 2 * A), (-A, 1.5 * A)]) & ~top & ~east
    post = _poly_mask(W, H, ox, oy, [(-0.22 * A, 0.4 * A), (0.22 * A, 0.4 * A), (0.22 * A, 1.55 * A), (-0.22 * A, 1.55 * A)])
    small = _poly_mask(W, H, ox, oy, [(-0.18 * A, 0.75 * A), (0.18 * A, 0.75 * A), (0.18 * A, 1.4 * A), (-0.18 * A, 1.4 * A)])
    out = {}
    for name, m in (("top", top), ("east", east), ("south", south), ("post", post), ("small", small)):
        ys, xs = np.nonzero(m)
        edge = np.zeros_like(m)
        if A >= 6:
            er = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
            edge = er
        out[name] = (xs - ox, ys - oy, edge[ys, xs])
    return out


def iso(vol: Volume, view: str = "se", max_px: int = 1024, scale: int | None = None, shadows: bool = True,
        tint: tuple[float, float, float] | None = None, bg=BG) -> Image.Image:
    """Izometrik (2:1) gorunum. view: se | sw | nw | ne (kameranin bulundugu yon)."""
    k = {"se": 0, "sw": 3, "nw": 2, "ne": 1}[view]
    v = vol.rotated(k) if k else vol
    ids = v.ids
    sy, sz, sx = ids.shape
    solid = v.pa["solid"][ids]
    if not solid.any():
        return Image.new("RGB", (64, 64), bg)
    # sinirlari kirp
    ys_, zs_, xs_ = np.nonzero(solid)
    y0, y1 = ys_.min(), ys_.max()
    z0, z1 = zs_.min(), zs_.max()
    x0, x1 = xs_.min(), xs_.max()
    ids = ids[y0:y1 + 1, z0:z1 + 1, x0:x1 + 1]
    solid = solid[y0:y1 + 1, z0:z1 + 1, x0:x1 + 1]
    sy, sz, sx = ids.shape
    if scale is None:
        A = int(max(1, min(24, max_px / max(1.0, (sx + sz)))))
        A = A if A % 2 == 0 or A == 1 else A - 1
        A = max(2, A)
    else:
        A = scale
    occl = (v.pa["opaque"][ids]) & (v.kind[ids] == CUBE)
    kind = v.kind[ids]
    pad_o = np.pad(occl, 1)
    # gorunur yuzler
    top_vis = solid & ~pad_o[2:, 1:-1, 1:-1]
    east_vis = solid & ~pad_o[1:-1, 1:-1, 2:] & (kind <= SLAB)
    south_vis = solid & ~pad_o[1:-1, 2:, 1:-1] & (kind <= SLAB)
    post_vis = solid & ((kind == POST) | (kind == SMALL))
    top_vis &= (kind <= FLAT)
    T = _templates(A)
    W = (sx + sz) * A + 4 * A
    Himg = int((sx + sz) * A / 2 + (sy + 1) * A + 4 * A)
    ref_u0 = sz * A + 2 * A
    ref_v0 = (sy + 1) * A + A
    top_col = v.pa["top"]
    side_col = v.pa["side"]
    alpha_arr = v.pa["alpha"]
    light_arr = v.pa["light"]
    height_arr = v.pa["height"]
    # golge icin yukseklik haritasi
    if shadows:
        hm = np.where(solid.any(axis=0), sy - 1 - np.argmax(solid[::-1], axis=0), -1)
    pix_all, dep_all, col_all = [], [], []

    def emit(mask, tname, shade, use_top):
        yy, zz, xx = np.nonzero(mask)
        if len(yy) == 0:
            return
        pid = ids[yy, zz, xx]
        base = (top_col if use_top else side_col)[pid].astype(np.float32)
        f = np.full(len(yy), shade, dtype=np.float32)
        if use_top:
            # ortam kapanmasi: ustteki 8 komsu
            pad_s = np.pad(solid, 1)
            cnt = np.zeros(len(yy), dtype=np.float32)
            for dz in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dz == 0 and dx == 0:
                        continue
                    cnt += pad_s[yy + 2, zz + 1 + dz, xx + 1 + dx]
            f *= 1.0 - 0.045 * cnt
            if shadows:
                sh = np.zeros(len(yy), dtype=bool)
                for kk in range(1, 28):
                    xq = xx - kk
                    zq = zz - (kk * 2) // 3
                    ok = (xq >= 0) & (zq >= 0)
                    hv = np.full(len(yy), -1)
                    hv[ok] = hm[zq[ok], xq[ok]]
                    sh |= ok & (hv >= yy + 1 + (kk * 3) // 4)
                f *= np.where(sh, 0.72, 1.0)
        f *= 1.0 + 0.25 * light_arr[pid]
        col = np.clip(base * f[:, None], 0, 255)
        du, dv, edge = T[tname]
        u = (xx - zz) * A + ref_u0
        vref = ((xx + zz) * A) // 2 - (yy + 1) * A + ref_v0
        if use_top:
            hgt = height_arr[pid]
            vref = vref + ((1.0 - hgt) * A).astype(np.int64)
        P = len(du)
        U = (u[:, None] + du[None, :]).ravel()
        Vv = (vref[:, None] + dv[None, :]).ravel()
        depth = np.repeat((xx + zz + yy).astype(np.int64) * 4 + {"top": 3, "east": 2, "south": 1, "post": 2, "small": 2}[tname], P)
        c = np.repeat(col, P, axis=0)
        if A >= 6:
            e = np.tile(edge, len(yy))
            c[e] *= 0.86
        a = np.repeat(alpha_arr[pid], P)
        ok = (U >= 0) & (U < W) & (Vv >= 0) & (Vv < Himg)
        pix_all.append((Vv[ok] * W + U[ok]).astype(np.int64))
        dep_all.append(depth[ok] * 2 + (a[ok] < 0.99))
        col_all.append(np.concatenate([c[ok], a[ok, None]], axis=1))

    emit(top_vis, "top", 1.0, True)
    emit(east_vis, "east", 0.82, False)
    emit(south_vis, "south", 0.66, False)
    emit(post_vis & (kind == POST), "post", 0.85, False)
    emit(post_vis & (kind == SMALL), "small", 0.95, False)
    img = np.empty((Himg * W, 3), dtype=np.float32)
    img[:] = bg
    if pix_all:
        pix = np.concatenate(pix_all)
        dep = np.concatenate(dep_all)
        col = np.concatenate(col_all)
        order = np.lexsort((dep, pix))
        pix, dep, col = pix[order], dep[order], col[order]
        # her piksel icin en yakin (en buyuk derinlik) opak; saydamlar ustune karisir
        last = np.r_[np.nonzero(np.diff(pix))[0], len(pix) - 1]
        img[pix[last]] = col[last, :3]
        # saydam (cam) katman: en ondekinin altindakiyle karistir
        transp = col[last, 3] < 0.99
        if transp.any():
            li = last[transp]
            prev = li - 1
            same = (prev >= 0) & (pix[np.maximum(prev, 0)] == pix[li])
            behind = np.where(same[:, None], col[np.maximum(prev, 0), :3], np.array(bg, dtype=np.float32))
            a = col[li, 3:4]
            img[pix[li]] = col[li, :3] * a + behind * (1 - a)
    img = img.reshape(Himg, W, 3)
    if tint is not None:
        img *= np.array(tint, dtype=np.float32)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    bbox = Image.fromarray((np.abs(img - np.array(bg, dtype=np.float32)).sum(axis=2) > 3).astype(np.uint8) * 255).getbbox()
    if bbox:
        pad = 8
        im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(W, bbox[2] + pad), min(Himg, bbox[3] + pad)))
    return im


# ------------------------------------------------------------------ ortografik
def ortho(vol: Volume, side: str = "south", max_px: int = 900, scale: int | None = None, bg=BG) -> Image.Image:
    """Cephe gorunumu: side = kameranin oldugu yon (south: guneyden kuzeye bakar)."""
    ids = vol.ids
    solid = vol.pa["solid"][ids] & (vol.kind[ids] != HIDDEN)
    if side == "top":
        return top(vol, max_px=max_px, scale=scale, bg=bg)
    # (y, kolon, derinlik) eksenlerine getir; derinlik 0 = kameraya en yakin
    if side == "south":
        a = ids[:, ::-1, :].transpose(0, 2, 1)  # (y, x, z_from_south)
    elif side == "north":
        a = ids[:, :, ::-1].transpose(0, 2, 1)  # x ters (kuzeyden bakan icin dogu solda)
    elif side == "east":
        a = ids[:, ::-1, ::-1]                  # (y, z ters, x_from_east)
    else:  # west
        a = ids                                 # (y, z, x_from_west)
    s = vol.pa["solid"][a]
    sy, ncol, nd = a.shape
    hit = s.any(axis=2)
    first = np.argmax(s, axis=2)
    pid = np.take_along_axis(a, first[:, :, None], axis=2)[:, :, 0]
    col = vol.pa["side"][pid].astype(np.float32)
    shade = 1.0 - 0.35 * (first / max(1, nd))
    col *= shade[:, :, None]
    al = vol.pa["alpha"][pid]
    # saydam onde ise arkadakiyle karistir
    op = vol.pa["opaque"][a] | (vol.pa["alpha"][a] >= 0.99) & s
    first_op = np.argmax(op, axis=2)
    has_op = op.any(axis=2)
    pid2 = np.take_along_axis(a, first_op[:, :, None], axis=2)[:, :, 0]
    behind = np.where(has_op[:, :, None], vol.pa["side"][pid2].astype(np.float32) * (1.0 - 0.35 * (first_op / max(1, nd)))[:, :, None],
                      np.array(bg, dtype=np.float32))
    blend = (al < 0.99) & hit
    col[blend] = col[blend] * al[blend, None] + behind[blend] * (1 - al[blend, None])
    col[~hit] = bg
    img = col[::-1]  # ust satir = en yuksek y
    if scale is None:
        scale = int(max(1, min(24, max_px / max(ncol, sy))))
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((ncol * scale, sy * scale), Image.NEAREST)
    return im


def top(vol: Volume, max_px: int = 900, scale: int | None = None, bg=BG) -> Image.Image:
    ids = vol.ids
    s = vol.pa["solid"][ids] & (vol.kind[ids] != HIDDEN)
    sy, sz, sx = ids.shape
    hit = s.any(axis=0)
    first = np.argmax(s[::-1], axis=0)
    yy = sy - 1 - first
    pid = np.take_along_axis(ids, yy[None, :, :], axis=0)[0]
    col = vol.pa["top"][pid].astype(np.float32)
    # yukseklik golgesi (hillshade)
    h = np.where(hit, yy, 0).astype(np.float32)
    gx = np.zeros_like(h)
    gz = np.zeros_like(h)
    gx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) / 2
    gz[1:-1, :] = (h[2:, :] - h[:-2, :]) / 2
    shade = np.clip(1.0 - 0.12 * gx - 0.12 * gz, 0.55, 1.25) * (0.8 + 0.2 * (h / max(1, sy)))
    col *= shade[:, :, None]
    col[~hit] = bg
    if scale is None:
        scale = int(max(1, min(24, max_px / max(sx, sz))))
    return Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).resize((sx * scale, sz * scale), Image.NEAREST)


def section(vol: Volume, y: int, max_px: int = 700, scale: int | None = None, bg=(250, 250, 248)) -> Image.Image:
    """Kat kesiti (plan): y ve y+1'deki dolu hucreler duvar/esya; y-1'deki zemin acik tonda."""
    ids = vol.ids
    sy, sz, sx = ids.shape
    s = vol.pa["solid"][ids]

    def layer(yy):
        if 0 <= yy < sy:
            return ids[yy], s[yy]
        return np.zeros((sz, sx), dtype=ids.dtype), np.zeros((sz, sx), dtype=bool)
    i1, s1 = layer(y + 1)
    i0, s0 = layer(y)
    ifl, sfl = layer(y - 1)
    col = np.empty((sz, sx, 3), dtype=np.float32)
    col[:] = bg
    floor_c = vol.pa["top"][ifl].astype(np.float32) * 0.45 + 255 * 0.55
    col[sfl] = floor_c[sfl]
    obj = s0 & ~s1
    col[obj] = vol.pa["top"][i0][obj] * 0.85
    wall = s1
    col[wall] = vol.pa["side"][i1][wall] * 0.6
    if scale is None:
        scale = int(max(2, min(24, max_px / max(sx, sz))))
    im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).resize((sx * scale, sz * scale), Image.NEAREST)
    if scale >= 6:
        a = np.asarray(im).copy()
        a[::scale, :, :] = (a[::scale, :, :] * 0.9).astype(np.uint8)
        a[:, ::scale, :] = (a[:, ::scale, :] * 0.9).astype(np.uint8)
        im = Image.fromarray(a)
    return im


# ------------------------------------------------------------------ perspektif (DDA isin izleme)
def perspective(vol: Volume, eye: tuple[float, float, float], target: tuple[float, float, float], size=(640, 360),
                fov: float = 70.0, max_steps: int | None = None, tint=None) -> Image.Image:
    """Hacim koordinatlarinda (x, y, z; hucre merkezleri .5) goz ve hedef. Hacim disi gokyuzu."""
    W, H = size
    ids = vol.ids
    sy, sz, sx = ids.shape
    solid = vol.pa["solid"][ids] & (vol.kind[ids] != HIDDEN)
    alpha = vol.pa["alpha"]
    e = np.array(eye, dtype=np.float64)
    t = np.array(target, dtype=np.float64)
    fwd = t - e
    fwd /= np.linalg.norm(fwd) + 1e-9
    up0 = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up0)
    if np.linalg.norm(right) < 1e-6:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    th = math.tan(math.radians(fov) / 2)
    js, is_ = np.meshgrid(np.arange(W), np.arange(H))
    px = (2 * (js + 0.5) / W - 1) * th * (W / H)
    py = (1 - 2 * (is_ + 0.5) / H) * th
    d = fwd[None, None, :] + px[..., None] * right[None, None, :] + py[..., None] * up[None, None, :]
    d = d.reshape(-1, 3)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    n = d.shape[0]
    # hacmin sinir kutusuna kadar ilerle (slab yontemi)
    lo = np.array([0.0, 0.0, 0.0])
    hi = np.array([sx, sy, sz], dtype=np.float64)
    dd = np.where(np.abs(d) < 1e-9, 1e-9, d)
    dvec = np.stack([dd[:, 0], dd[:, 1], dd[:, 2]], axis=1)
    t1 = (lo - e) / dvec
    t2 = (hi - e) / dvec
    tmin = np.maximum.reduce(np.minimum(t1, t2), axis=1) if False else np.max(np.minimum(t1, t2), axis=1)
    tmax = np.min(np.maximum(t1, t2), axis=1)
    hitbox = (tmax > np.maximum(tmin, 0))
    tstart = np.maximum(tmin, 0) + 1e-4
    p = e[None, :] + dvec * tstart[:, None]
    cell = np.floor(p).astype(np.int64)
    cell[:, 0] = np.clip(cell[:, 0], 0, sx - 1)
    cell[:, 1] = np.clip(cell[:, 1], 0, sy - 1)
    cell[:, 2] = np.clip(cell[:, 2], 0, sz - 1)
    step = np.where(dvec > 0, 1, -1)
    tdelta = np.abs(1.0 / dvec)
    nextb = cell + (step > 0)
    tm = (nextb - e[None, :]) / dvec
    out = np.zeros((n, 3), dtype=np.float32)
    acc_a = np.zeros(n, dtype=np.float32)
    face = np.zeros(n, dtype=np.int64)
    dist = np.zeros(n, dtype=np.float64)
    active = np.nonzero(hitbox)[0]
    # baslangic hucresi
    if max_steps is None:
        max_steps = int(sx + sy + sz + 4)
    col_top = vol.pa["top"]
    col_side = vol.pa["side"]
    for _ in range(max_steps):
        if active.size == 0:
            break
        c = cell[active]
        pid = ids[c[:, 1], c[:, 2], c[:, 0]]
        sol = solid[c[:, 1], c[:, 2], c[:, 0]]
        if sol.any():
            hi_ = active[sol]
            pidh = pid[sol]
            f = face[hi_]
            base = np.where((f == 1)[:, None], col_top[pidh], col_side[pidh]).astype(np.float32)
            shade = np.select([f == 1, f == 0, f == 2], [1.0, 0.8, 0.68], 1.0).astype(np.float32)
            fog = np.clip(1.0 - dist[hi_] / 260.0, 0.55, 1.0).astype(np.float32)
            c_ = base * (shade * fog)[:, None]
            a = alpha[pidh]
            rem = 1.0 - acc_a[hi_]
            out[hi_] += c_ * (a * rem)[:, None]
            acc_a[hi_] += a * rem
            done = acc_a[hi_] > 0.97
            keep = np.ones(active.size, dtype=bool)
            keep[np.nonzero(sol)[0][done]] = False
            active = active[keep]
            if active.size == 0:
                break
        tma = tm[active]
        ax = np.argmin(tma, axis=1)
        r = np.arange(active.size)
        dist[active] = tma[r, ax]
        cell[active, ax] += step[active, ax]
        tm[active, ax] += tdelta[active, ax]
        face[active] = np.where(ax == 1, 1, np.where(ax == 0, 0, 2))
        c = cell[active]
        inside = (c[:, 0] >= 0) & (c[:, 0] < sx) & (c[:, 1] >= 0) & (c[:, 1] < sy) & (c[:, 2] >= 0) & (c[:, 2] < sz)
        active = active[inside]
    # gokyuzu
    sky_t = np.clip((d[:, 1] + 0.2) / 1.0, 0, 1)
    sky = SKY_BOT[None, :] * (1 - sky_t[:, None]) + SKY_TOP[None, :] * sky_t[:, None]
    out = out + sky * (1.0 - acc_a)[:, None]
    img = out.reshape(H, W, 3)
    if tint is not None:
        img *= np.array(tint, dtype=np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
