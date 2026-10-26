"""Adanin parklari: cam A-cerceve Ask Sapeli + Kalp Golu (adacikta kosk), kalp seklinde cit labirenti, dev donme
dolap, atlikarinca, marina (iskele, yatlar, iki deniz feneri, yat kulubu meydani), kalp seklinde iskele uzerinde su ustu
villalar, su alti tuneli + cam kubbe restoran ve mercan bahcesi, kumsal (palmiyeler, semsiyeler, sezlonglar, plaj barlari)."""
from __future__ import annotations

import math
import random

import numpy as np

import aa_core as C
import aa_tower as T
from aa_core import AZ, GY, SEA, World
from aa_front import LEAF_A, LEAF_C, POST, pillars

CH_X0, CH_X1, CH_ZC, CH_HW, CH_H = -186, -142, -792, 11, 30
LAKE_C, LAKE_S = (-212, -792), 1.0
MAZE_C, MAZE_S = (-100, -806), 1.4
WX, WY, WZ, WR = -150, 108, -610, 37.5
CAROUSEL = (-118, -652)
LIGHTHOUSES = ((-67, -775), (-67, -619))
CLUB = (-168, -130)
DIRS = ((1, 0, "east"), (-1, 0, "west"), (0, 1, "south"), (0, -1, "north"))


def snap_dir(vx, vz):
    """Vektoru en yakin dunya yonune yuvarlar: (dx, dz, ad)."""
    if abs(vx) >= abs(vz):
        return (1, 0, "east") if vx > 0 else (-1, 0, "west")
    return (0, 1, "south") if vz > 0 else (0, -1, "north")


def grad(w, D, x, z):
    i, j = z - C.Z0, x - C.X0
    gx = float(D[i, min(j + 1, w.nx - 1)] - D[i, max(j - 1, 0)])
    gz = float(D[min(i + 1, w.nz - 1), j] - D[max(i - 1, 0), j])
    n = math.hypot(gx, gz) or 1.0
    return gx / n, gz / n


# ------------------------------------------------------------------ ask sapeli
def chapel(w: World):
    X, Z = w.XX, w.ZZ
    x0, x1, zc, hw, H = CH_X0, CH_X1, CH_ZC, CH_HW, CH_H
    y0 = GY + 1
    foot = w.mask_rect(x0 - 1, zc - hw - 1, x1 + 1, zc + hw + 1)
    w.layer(GY, foot, C.CALCITE)
    w.layer(GY, foot & ((X + Z) % 2 == 0), C.QUARTZ)
    dz = np.abs(Z - zc)
    inx = (X >= x0) & (X <= x1)
    for y in range(y0, y0 + H + 1):
        h = hw * (1.0 - (y - y0) / float(H))
        sec = inx & (dz <= h + 0.5)
        shell = sec & ((dz > h - 0.75) | (X == x0) | (X == x1))
        rib = shell & (((X - x0) % 5 == 0) | (X == x0) | (X == x1))
        glass = C.GLASS if y < y0 + 6 else (C.PGLASS if y < y0 + 20 else C.WGLASS)
        w.layer(y, shell & ~rib, glass)
        w.layer(y, rib, C.QUARTZ)
        if h < 1.6:
            w.layer(y, sec, C.GOLD)
        w.layer(y, sec & ~shell, 1)
    # alinliklar: buyuk pembe kalp pencere (altin konturlu), A cerceve kesitine kirpilmis
    sw = 0.32
    py = y0 + 10 + (C.HY - C.HCY) * sw
    pzz = zc + 0.5 + C.HX * sw
    ys = np.arange(y0, y0 + H + 1)
    zs = np.arange(zc - hw - 1, zc + hw + 2)
    win = C.raster(pzz, py, int(zs[0]), int(ys[0]), len(zs), len(ys))       # [y, z]
    Ys, Zs = np.meshgrid(ys, zs, indexing="ij")
    win &= np.abs(Zs - zc) <= hw * (1.0 - (Ys - y0) / float(H)) - 1.0
    for xx in (x0, x1):
        for a, b in zip(*np.nonzero(win)):
            w.set(xx, int(ys[a]), int(zs[b]), C.PGLASS)
        for a, b in zip(*np.nonzero(C.edge4(win))):
            w.set(xx, int(ys[a]), int(zs[b]), C.GOLD)
    w.box(x0, y0, zc - 1, x0, y0 + 3, zc + 1, 1)
    w.box(x0, y0 + 4, zc - 2, x0, y0 + 4, zc + 2, C.GOLD)
    w.box(x0 - 3, y0 + 5, zc - 3, x0 - 1, y0 + 5, zc + 3, C.QUARTZ)
    w.box(x0 - 3, y0 + 4, zc - 3, x0 - 1, y0 + 4, zc + 3, C.FROG)
    w.box(x0 - 3, y0 + 4, zc - 2, x0 - 1, y0 + 4, zc + 2, 0)
    for zz in (zc - 3, zc + 3):
        w.box(x0 - 3, y0, zz, x0 - 3, y0 + 4, zz, C.QPILLAR)
    # zil: on tepe altinda
    w.box(x0 - 2, y0 + H - 5, zc, x0 - 1, y0 + H - 5, zc, C.QUARTZ)
    w.set(x0 - 2, y0 + H - 6, zc, "bell[attachment=ceiling,facing=east,powered=false]")
    # ic: zemin, koridor halisi, oturaklar, sunak, cicek kemeri, avizeler
    inside = inx & (dz <= hw - 1) & (X > x0) & (X < x1)
    w.layer(GY, inside & ((X + Z) % 2 == 0), C.QUARTZ)
    w.layer(GY, inside & ((X + Z) % 2 == 1), C.CALCITE)
    aisle = inside & (dz <= 1) & (X < x1 - 9)
    w.layer(y0, aisle & (dz == 0), "white_carpet")
    w.layer(y0, aisle & (dz == 1), "pink_carpet")
    w.layer(GY, inside & (dz == 2) & ((X - x0) % 4 == 0), C.SEAL)
    for x in range(x0 + 4, x1 - 11, 3):
        for zz in range(zc - 8, zc + 9):
            if abs(zz - zc) < 2:
                continue
            w.set(x, y0, zz, "cherry_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        for zz, f in ((zc - 9, "north"), (zc + 9, "south")):
            w.set(x, y0, zz, f"cherry_trapdoor[facing={f},half=bottom,open=true,powered=false,waterlogged=false]")
        w.set(x, y0, zc - 2, "cherry_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        w.set(x, y0, zc + 2, "cherry_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        if (x - x0) % 6 == 4:
            for zz in (zc - 10, zc + 10):
                w.set(x, y0, zz, "lantern[hanging=false,waterlogged=false]")
    ax0 = x1 - 9
    w.box(ax0, y0, zc - 7, x1 - 1, y0, zc + 7, C.QUARTZ)
    w.box(ax0, y0, zc - 7, ax0, y0, zc + 7, "smooth_quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    w.box(ax0 + 3, y0 + 1, zc - 5, x1 - 1, y0 + 1, zc + 5, C.QUARTZ)
    w.box(ax0 + 3, y0 + 1, zc - 5, ax0 + 3, y0 + 1, zc + 5,
          "smooth_quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    ya = y0 + 2
    ka = x1 - 4
    for zz in (zc - 3, zc + 3):
        w.box(ka, ya, zz, ka, ya + 4, zz, C.QPILLAR)
        w.box(ka, ya + 2, zz + (1 if zz > zc else -1), ka, ya + 4, zz + (1 if zz > zc else -1), LEAF_A)
    w.box(ka, ya + 5, zc - 3, ka, ya + 5, zc + 3, C.QUARTZ)
    w.box(ka, ya + 6, zc - 3, ka, ya + 6, zc + 3, LEAF_A)
    w.box(ka - 1, ya + 6, zc - 1, ka + 1, ya + 6, zc + 1, LEAF_C)
    for zz in (zc - 1, zc + 1):
        w.set(ka, ya + 4, zz, "lantern[hanging=true,waterlogged=false]")
    w.box(x1 - 2, ya, zc - 1, x1 - 2, ya, zc + 1, "smooth_quartz_slab[type=top,waterlogged=false]")
    for zz in (zc - 1, zc + 1):
        w.set(x1 - 2, ya + 1, zz, "white_candle[candles=4,lit=true,waterlogged=false]")
    w.set(x1 - 2, ya + 1, zc, "pink_candle[candles=3,lit=true,waterlogged=false]")
    for zz in (zc - 5, zc + 5):
        w.set(ax0 + 4, ya, zz, "potted_white_tulip")
        w.set(x1 - 1, ya, zz, "potted_pink_tulip")
    for x in range(x0 + 6, x1 - 2, 8):
        top_y = y0 + H - 4
        for y in range(y0 + 15, top_y + 1):
            w.set(x, y, zc, "iron_chain[axis=y,waterlogged=false]")
        w.set(x, y0 + 14, zc, C.GOLD)
        for ddx, ddz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            w.set(x + ddx, y0 + 14, zc + ddz, C.GOLD)
            w.set(x + ddx, y0 + 13, zc + ddz, "lantern[hanging=true,waterlogged=false]")
        w.set(x, y0 + 13, zc, C.FROG)
    w.sign(x0 - 1, y0 + 2, zc + 2, "west", ["AŞK ŞAPELİ", "♥", "", ""], color="black")
    # on avlu: kalp kakmali beyaz zemin, banklar
    court = w.mask_rect(x0 - 11, zc - 6, x0 - 1, zc + 6)
    w.layer(GY, court, C.QUARTZ)
    hx, hz = C.heart_poly(x0 - 6, zc + 0.5, 0.25)
    w.layer(GY, w.mask_poly(hx, hz) & court, C.ROSE)
    for zz, f in ((zc - 6, "north"), (zc + 6, "south")):
        for xx in range(x0 - 9, x0 - 3, 3):
            w.set(xx, y0, zz, f"cherry_stairs[facing={f},half=bottom,shape=straight,waterlogged=false]")
    w.occ |= foot | court


def heart_lake(w: World):
    """Sapelin onunde kalp seklinde gol: kuvars kenar, nilufer, su alti isiklari, ortada adacikta beyaz kosk."""
    X, Z = w.XX, w.ZZ
    px, pz = C.heart_poly(LAKE_C[0], LAKE_C[1], LAKE_S)
    Dl, M = C.sdf(px, pz, C.X0, C.Z0, w.nx, w.nz, margin=6.0)
    depth = np.clip(1 + Dl / 2.5, 1, 4).astype(np.int32)
    for d in range(1, 5):
        m = M & (depth >= d)
        w.layer(GY - d, m, "water")
    bed = GY - depth - 1
    for y in range(GY - 6, GY):
        w.layer(y, M & (bed == y), "sand")
    w.layer(GY, M, "water")
    lamps = M & ((X + Z) % 4 == 0) & (depth >= 2)
    for y in range(GY - 6, GY):
        w.layer(y, lamps & (bed == y), C.SEAL)
    rim = C.ring_out(M)
    w.layer(GY, rim, C.QUARTZ)
    w.layer(GY + 1, rim & ((X + Z) % 2 == 0), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.layer(GY + 1, M & (C.hash2(X, Z, 51) < 0.07) & (Dl > 1.5), "lily_pad")
    # adacik + kosk
    cx, cz = LAKE_C[0] - 2, LAKE_C[1]
    isl = (X - cx) ** 2 + (Z - cz) ** 2 <= 12
    for y in range(GY - 6, GY + 1):
        w.layer(y, isl, "dirt" if y < GY else "grass_block[snowy=false]")
    for ddx, ddz in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
        w.box(cx + ddx, GY + 1, cz + ddz, cx + ddx, GY + 4, cz + ddz, C.QPILLAR)
    w.box(cx - 3, GY + 5, cz - 3, cx + 3, GY + 5, cz + 3, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.box(cx - 2, GY + 5, cz - 2, cx + 2, GY + 5, cz + 2, C.QUARTZ)
    w.box(cx - 1, GY + 6, cz - 1, cx + 1, GY + 6, cz + 1, C.GOLD)
    w.set(cx, GY + 4, cz, "lantern[hanging=true,waterlogged=false]")
    for zz in (cz - 1, cz + 1):
        w.set(cx + 1, GY + 1, zz, "cherry_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    # kopru: adaciktan doguya (sapele bakan kiyiya)
    bx0 = cx + 3
    row = M[cz - C.Z0]
    xs = [x for x in range(bx0, bx0 + 30) if row[x - C.X0]]
    if xs:
        bx1 = max(xs) + 1
        w.box(bx0, GY, cz - 1, bx1, GY, cz + 1, "pale_oak_planks")
        for x in range(bx0, bx1 + 1, 2):
            for zz in (cz - 1, cz + 1):
                w.set(x, GY + 1, zz, POST)
    w.occ |= M | rim | isl


# ------------------------------------------------------------------ kalp labirenti
def maze(w: World):
    X, Z = w.XX, w.ZZ
    px, pz = C.heart_poly(MAZE_C[0], MAZE_C[1], MAZE_S)
    M = w.mask_poly(px, pz) & ~w.occ & (w.D > 8)
    Me = C.erode(M, 1, square=True)
    zs_, xs_ = np.nonzero(M)
    gx0, gz0 = int(xs_.min()) + C.X0, int(zs_.min()) + C.Z0
    ni = (int(xs_.max()) + C.X0 - gx0) // 3 + 1
    nj = (int(zs_.max()) + C.Z0 - gz0) // 3 + 1
    ok = np.zeros((ni, nj), bool)
    for i in range(ni):
        for j in range(nj):
            x, z = gx0 + 3 * i, gz0 + 3 * j
            sl = Me[z - C.Z0:z - C.Z0 + 2, x - C.X0:x - C.X0 + 2]
            ok[i, j] = sl.size == 4 and sl.all()
    hedge = M.copy()
    rng = random.Random(1914)
    # baslangic: kalbin ucuna en yakin dugum
    tipx = MAZE_C[0] - 17.83 * MAZE_S
    cand = [(abs(gx0 + 3 * i - tipx) + abs(gz0 + 3 * j - MAZE_C[1]), i, j) for i in range(ni) for j in range(nj) if ok[i, j]]
    if not cand:
        return
    _, si, sj = min(cand)
    seen = {(si, sj)}
    stack = [(si, sj)]
    open_cells = set()

    def carve(i, j):
        x, z = gx0 + 3 * i, gz0 + 3 * j
        for a in range(2):
            for b in range(2):
                open_cells.add((x + a, z + b))
    carve(si, sj)
    while stack:
        i, j = stack[-1]
        nb = [(i + di, j + dj, di, dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))
              if 0 <= i + di < ni and 0 <= j + dj < nj and ok[i + di, j + dj] and (i + di, j + dj) not in seen]
        if not nb:
            stack.pop()
            continue
        a, b, di, dj = rng.choice(nb)
        x, z = gx0 + 3 * i, gz0 + 3 * j
        # aradaki duvar
        if di:
            wx = x + (2 if di > 0 else -1)
            open_cells.update({(wx, z), (wx, z + 1)})
        else:
            wz = z + (2 if dj > 0 else -1)
            open_cells.update({(x, wz), (x + 1, wz)})
        carve(a, b)
        seen.add((a, b))
        stack.append((a, b))
    # merkez meydan (agirlik merkezi cevresi) ve giris
    for (x, z) in list(open_cells):
        pass
    cx, cz = MAZE_C
    for x in range(cx - 4, cx + 5):
        for z in range(cz - 4, cz + 5):
            if M[z - C.Z0, x - C.X0]:
                open_cells.add((x, z))
    sx_, sz_ = gx0 + 3 * si, gz0 + 3 * sj
    for x in range(sx_ - 6, sx_ + 1):
        for z in (sz_, sz_ + 1):
            if 0 <= z - C.Z0 < w.nz and 0 <= x - C.X0 < w.nx and M[z - C.Z0, x - C.X0]:
                open_cells.add((x, z))
    for (x, z) in open_cells:
        hedge[z - C.Z0, x - C.X0] = False
    path = M & ~hedge
    w.layer(GY, M, "grass_block[snowy=false]")
    w.layer(GY, path & (C.hash2(X, Z, 3) < 0.5), "moss_block")
    r = C.hash2(X, Z, 8)
    for y in range(GY + 1, GY + 4):
        w.layer(y, hedge & (r < 0.78), "azalea_leaves[distance=1,persistent=true,waterlogged=false]")
        w.layer(y, hedge & (r >= 0.78), LEAF_A)
    w.layer(GY + 1, path & (C.hash2(X // 2, Z // 2, 4) < 0.06), "lantern[hanging=false,waterlogged=false]")
    w.layer(GY + 1, path & (C.hash2(X, Z, 9) < 0.10), "pink_petals[facing=south,flower_amount=2]", empty=True)
    # merkez: kucuk kalp cesme + kemer
    hx, hz = C.heart_poly(cx, cz + 0.5, 0.18)
    hm = w.mask_poly(hx, hz)
    w.layer(GY, hm, C.QUARTZ)
    w.layer(GY + 1, C.edge4(hm), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.layer(GY + 1, hm & ~C.edge4(hm), "water")
    w.box(cx + 3, GY + 1, cz - 3, cx + 3, GY + 4, cz - 3, C.QPILLAR)
    w.box(cx + 3, GY + 1, cz + 3, cx + 3, GY + 4, cz + 3, C.QPILLAR)
    w.box(cx + 3, GY + 5, cz - 3, cx + 3, GY + 5, cz + 3, LEAF_A)
    w.set(cx + 3, GY + 4, cz, "lantern[hanging=true,waterlogged=false]")
    w.box(cx + 3, GY + 5, cz - 2, cx + 3, GY + 5, cz + 2, C.QUARTZ)
    w.sign(sx_ - 7, GY + 1, sz_, "west", ["AŞK", "LABİRENTİ", "merkezde", "sürpriz ♥"], color="black", wall=False)
    w.occ |= M


# ------------------------------------------------------------------ donme dolap ve atlikarinca
def wheel(w: World):
    def line_yz(x, y0, z0, y1, z1, st, r=0.5):
        n = int(max(abs(y1 - y0), abs(z1 - z0)) * 2) + 1
        for t in np.linspace(0, 1, n):
            y = y0 + (y1 - y0) * t
            z = z0 + (z1 - z0) * t
            for dy in ((0,) if r <= 0.5 else (-1, 0, 1)):
                for dz in ((0,) if r <= 0.5 else (-1, 0, 1)):
                    w.set(x, int(round(y)) + dy, int(round(z)) + dz, st)
    ys = np.arange(int(WY - WR - 3), int(WY + WR + 4))
    zs = np.arange(int(WZ - WR - 3), int(WZ + WR + 4))
    Yg, Zg = np.meshgrid(ys, zs, indexing="ij")
    dist = np.hypot(Yg - WY, Zg - WZ)
    ang = np.degrees(np.arctan2(Yg - WY, Zg - WZ)) % 360
    rim = (dist > WR - 1.2) & (dist <= WR + 0.9)
    glow = rim & (dist > WR) & ((ang // 4).astype(int) % 2 == 0)
    inner = (dist > WR - 7.6) & (dist <= WR - 6.6)
    for xr in (WX - 3, WX + 3):
        for m, st in ((rim, C.WHITE), (glow, C.FROG), (inner, C.WHITE)):
            yy, zz = np.nonzero(m)
            for a, b in zip(yy, zz):
                w.set(xr, int(ys[a]), int(zs[b]), st)
        for k in range(18):
            t = math.radians(k * 20)
            line_yz(xr, WY + 4 * math.sin(t), WZ + 4 * math.cos(t), WY + (WR - 1) * math.sin(t), WZ + (WR - 1) * math.cos(t),
                    C.WHITE)
            t2 = math.radians(k * 20 + 10)
            line_yz(xr, WY + (WR - 7) * math.sin(t), WZ + (WR - 7) * math.cos(t), WY + (WR - 1) * math.sin(t2),
                    WZ + (WR - 1) * math.cos(t2), "iron_bars")
    # gobek: x boyunca silindir
    for x in range(WX - 8, WX + 9):
        for y in range(WY - 4, WY + 5):
            for z in range(WZ - 4, WZ + 5):
                d = math.hypot(y - WY, z - WZ)
                if d <= 3.6:
                    w.set(x, y, z, C.GOLD if abs(x - WX) >= 7 or d > 2.8 else C.WHITE)
    w.box(WX - 9, WY, WZ, WX + 9, WY, WZ, C.FROG)
    # kabinler: 18 aks, her birinden zincirle sarkan pembe camli kabin
    cabins = []
    for k in range(18):
        t = math.radians(k * 20 + 10)
        ya = int(round(WY + WR * math.sin(t)))
        za = int(round(WZ + WR * math.cos(t)))
        w.box(WX - 3, ya, za, WX + 3, ya, za, C.GOLD)
        w.set(WX, ya - 1, za, "iron_chain[axis=y,waterlogged=false]")
        w.box(WX - 1, ya - 2, za - 1, WX + 1, ya - 2, za + 1, C.WHITE)
        w.set(WX, ya - 2, za, C.FROG)
        w.box(WX - 1, ya - 4, za - 1, WX + 1, ya - 3, za + 1, C.PGLASS)
        w.box(WX, ya - 4, za, WX, ya - 3, za, 1)
        w.box(WX - 1, ya - 5, za - 1, WX + 1, ya - 5, za + 1, C.WHITE)
        cabins.append((ya - 5, za))
    # ayaklar (iki A cerceve) ve capraz bagler
    low = min(cabins)
    for xa in (WX - 6, WX + 6):
        for side in (-1, 1):
            zf = WZ + side * 24
            line_yz(xa, WY, WZ, GY + 1, zf, C.WHITE, r=1.0)
            w.box(xa - 1, GY - 2, zf - 2, xa + 1, GY, zf + 2, C.QUARTZ)
        for yb in (GY + 16, GY + 30):
            frac = (WY - yb) / float(WY - GY - 1)
            dzb = int(24 * frac)
            w.box(xa, yb, WZ - dzb, xa, yb, WZ + dzb, C.WHITE)
    # binis platformu, gise
    yb, zb = low
    w.box(WX - 7, GY, WZ - 7, WX + 7, GY, WZ + 7, C.QUARTZ)
    if yb > GY:
        w.box(WX - 2, GY + 1, zb - 2, WX + 2, yb, zb + 2, C.QUARTZ, only=[0])
    w.box(WX - 7, GY, WZ - 7, WX + 7, GY, WZ - 7, C.ROSE)
    w.box(WX - 7, GY, WZ + 7, WX + 7, GY, WZ + 7, C.ROSE)
    w.box(WX + 9, GY + 1, WZ + 8, WX + 11, GY + 3, WZ + 10, C.WHITE)
    w.box(WX + 10, GY + 1, WZ + 8, WX + 10, GY + 2, WZ + 8, 1)
    w.box(WX + 8, GY + 4, WZ + 7, WX + 12, GY + 4, WZ + 11, "pink_wool_slab[type=bottom,waterlogged=false]")
    w.sign(WX + 10, GY + 3, WZ + 7, "north", ["DÖNME DOLAP", "♥ 18 KABİN ♥", "", ""], color="black")
    w.occ |= w.mask_rect(WX - 9, WZ - 26, WX + 12, WZ + 26)


def carousel(w: World):
    X, Z = w.XX, w.ZZ
    cx, cz = CAROUSEL
    d2 = (X - cx) ** 2 + (Z - cz) ** 2
    ang = (np.degrees(np.arctan2(Z - cz, X - cx)) % 360) // 22.5
    plat = d2 <= 8 * 8 + 8
    w.layer(GY, d2 <= 9 * 9 + 9, C.QUARTZ)
    w.layer(GY + 1, plat, C.QUARTZ)
    w.layer(GY + 1, plat & (ang % 2 == 0) & (d2 > 4), C.ROSE)
    for y in range(GY + 2, GY + 10):
        w.layer(y, d2 <= 2, C.GOLD if y % 2 else "glass")
    canopy = d2 <= 9 * 9 + 9
    w.layer(GY + 10, canopy & (ang % 2 == 0), "pink_wool")
    w.layer(GY + 10, canopy & (ang % 2 == 1), "white_wool")
    w.layer(GY + 9, canopy & (d2 > 8 * 8 + 8) & (ang % 2 == 0), C.FROG)
    w.layer(GY + 11, d2 <= 5 * 5 + 5, "pink_wool_slab[type=bottom,waterlogged=false]")
    w.layer(GY + 11, (d2 <= 5 * 5 + 5) & (ang % 2 == 1), "white_wool_slab[type=bottom,waterlogged=false]")
    w.box(cx, GY + 11, cz, cx, GY + 13, cz, C.GOLD)
    w.set(cx, GY + 14, cz, "lightning_rod[facing=up,powered=false,waterlogged=false]")
    for k in range(12):
        t = math.radians(k * 30)
        px, pz = cx + int(round(6 * math.cos(t))), cz + int(round(6 * math.sin(t)))
        w.box(px, GY + 2, pz, px, GY + 9, pz, C.ROD_UP)
        tx, tz = int(round(-math.sin(t))), int(round(math.cos(t)))
        bx, bz = px + (tx if abs(tx) >= abs(tz) else 0), pz + (tz if abs(tz) > abs(tx) else 0)
        w.set(bx, GY + 3 + (k % 2), bz, "white_wool" if k % 2 else "pink_wool")
        w.set(bx, GY + 4 + (k % 2), bz, "pink_carpet" if k % 2 else "white_carpet")
    w.sign(cx - 10, GY + 1, cz, "west", ["ATLIKARINCA", "♥", "", ""], color="black", wall=False)
    w.occ |= d2 <= 11 * 11


# ------------------------------------------------------------------ marina
def yacht(w: World, xs, zc, L, B, name, hot_tub=False):
    """Pruva doguya bakan yat: beyaz govde (pembe serit), tik guverte, iki kat ust yapi, flybridge, radar."""
    hull = {}
    for i in range(L):
        t = i / float(L - 1)
        hb = (B / 2.0) * min(1.0, ((1.0 - t) / 0.33) ** 0.55)
        hull[xs + i] = hb
    for x, hb in hull.items():
        for y in range(SEA - 4, SEA + 2):
            k = (y - (SEA - 5)) / 6.0
            hby = hb * (0.35 + 0.65 * k)
            for z in range(int(zc - hby - 1), int(zc + hby + 2)):
                if abs(z + 0.5 - (zc + 0.5)) <= hby:
                    edge = abs(z + 0.5 - (zc + 0.5)) > hby - 1.0
                    st = C.WHITE
                    if y == SEA and edge:
                        st = C.PINK
                    w.set(x, y, z, st)
        for z in range(int(zc - hb - 1), int(zc + hb + 2)):
            dzz = abs(z + 0.5 - (zc + 0.5))
            if dzz <= hb:
                w.set(x, SEA + 1, z, "pale_oak_planks" if dzz <= hb - 1 else C.QUARTZ)
                if dzz > hb - 1:
                    w.set(x, SEA + 2, z, C.CPANE)
    # ust yapi
    a, b = xs + int(L * 0.14), xs + int(L * 0.62)
    hbm = min(hull[x] for x in range(a, b + 1))
    zw = int(hbm) - 2
    w.box(a, SEA + 2, zc - zw, b, SEA + 4, zc + zw, C.WHITE)
    w.box(a + 1, SEA + 2, zc - zw + 1, b - 1, SEA + 4, zc + zw - 1, 1)
    w.box(a, SEA + 3, zc - zw, b, SEA + 3, zc + zw, "black_stained_glass")
    w.box(a, SEA + 5, zc - zw - 1, b + 1, SEA + 5, zc + zw + 1, C.WHITE)
    w.box(b + 1, SEA + 5, zc - zw - 1, b + 1, SEA + 5, zc + zw + 1, C.GOLD)
    w.box(a, SEA + 2, zc, a, SEA + 3, zc, 1)
    w.box(a + 2, SEA + 2, zc - 1, b - 2, SEA + 2, zc + 1, "pink_carpet")
    a2, b2 = a + int((b - a) * 0.3), a + int((b - a) * 0.75)
    w.box(a2, SEA + 6, zc - zw + 1, b2, SEA + 7, zc + zw - 1, C.WHITE)
    w.box(a2 + 1, SEA + 6, zc - zw + 2, b2 - 1, SEA + 7, zc + zw - 2, 1)
    w.box(b2, SEA + 6, zc - zw + 1, b2, SEA + 7, zc + zw - 1, "tinted_glass")
    w.box(a2, SEA + 8, zc - zw + 1, b2, SEA + 8, zc + zw - 1, C.WHITE)
    w.set((a2 + b2) // 2, SEA + 9, zc, "lightning_rod[facing=up,powered=false,waterlogged=false]")
    w.box((a2 + b2) // 2 - 1, SEA + 9, zc, (a2 + b2) // 2 + 1, SEA + 9, zc, "end_rod[facing=east]")
    w.set(a2 + 1, SEA + 6, zc, "cherry_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
    # pruvada guneslenme minderi ve sicak havuz, kicta sezlong
    p0 = xs + int(L * 0.68)
    w.box(p0, SEA + 2, zc - 1, p0 + 2, SEA + 2, zc + 1, "white_wool_slab[type=bottom,waterlogged=false]")
    if hot_tub:
        w.box(p0 - 3, SEA + 2, zc - 2, p0 - 1, SEA + 2, zc + 2, C.GOLD)
        w.box(p0 - 2, SEA + 1, zc - 1, p0 - 2, SEA + 1, zc + 1, "soul_sand")
        w.box(p0 - 2, SEA + 2, zc - 1, p0 - 2, SEA + 2, zc + 1, "bubble_column[drag=false]")
    for zz in (zc - 1, zc + 1):
        w.set(xs + 1, SEA + 2, zz, "white_wool_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    w.sign(xs - 1, SEA + 1, zc, "west", ["", name, "♥", ""], color="black")
    w.set(xs + L - 2, SEA + 2, zc, "lantern[hanging=false,waterlogged=false]")


def lighthouse(w: World, cx, cz):
    for y in range(GY - 4, GY + 2):
        for dx in range(-4, 5):
            for dz in range(-4, 5):
                if abs(dx) + abs(dz) <= 6:
                    w.set(cx + dx, y, cz + dz, C.QUARTZ)
    top = GY + 30
    for y in range(GY + 2, top):
        r = 3.2 - 1.0 * (y - GY - 2) / float(top - GY - 2)
        stripe = ((y - GY) // 4) % 2 == 0
        for dx in range(-4, 5):
            for dz in range(-4, 5):
                d = math.hypot(dx, dz)
                if d <= r:
                    w.set(cx + dx, y, cz + dz, (C.PINK if stripe else C.WHITE) if d > r - 1 else 1)
    for dx in range(-4, 5):
        for dz in range(-4, 5):
            d = math.hypot(dx, dz)
            if d <= 4.3:
                w.set(cx + dx, top, cz + dz, C.QUARTZ)
            if 3.4 < d <= 4.3:
                w.set(cx + dx, top + 1, cz + dz, "iron_bars")
            if d <= 2.3:
                for y in range(top + 1, top + 5):
                    w.set(cx + dx, y, cz + dz, C.GLASS if d > 1.3 else C.FROG)
            if d <= 2.9:
                w.set(cx + dx, top + 5, cz + dz, C.GOLD)
    w.set(cx, top + 6, cz, C.GOLD)
    w.set(cx, top + 7, cz, "lightning_rod[facing=up,powered=false,waterlogged=false]")
    w.set(cx, GY + 2, cz - 3, 1)
    w.set(cx, GY + 3, cz - 3, 1)


def marina(w: World):
    X, Z = w.XX, w.ZZ
    # orta iskele + parmak iskeleler (su ustunde, kiraz tahta)
    pier = w.mask_rect(-128, AZ - 1, -72, AZ + 1) & (w.D <= 2)
    for xf in (-104,):
        pier |= w.mask_rect(xf, AZ - 16, xf + 1, AZ + 16) & (w.D <= -1.5)
    w.layer(SEA + 1, pier, "cherry_planks")
    w.layer(SEA, pier, "cherry_planks")
    legs = pier & ((X % 5 == 0) & ((Z - AZ) % 3 == 0))
    pillars(w, legs, SEA - 1, "stripped_cherry_log[axis=y]")
    edge = pier & ~C.erode(pier, 1)
    w.layer(SEA + 2, edge & ((X + Z) % 6 == 0), POST)
    w.layer(SEA + 3, edge & ((X + Z) % 12 == 0), "lantern[hanging=false,waterlogged=false]")
    w.occ |= pier
    # rihtimdan iskeleye iki basamak (koyun basi)
    for zz in (AZ - 1, AZ, AZ + 1):
        w.set(-128, GY, zz, 1)
        w.set(-128, GY - 1, zz, "smooth_quartz_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        w.set(-128, GY - 2, zz, C.QUARTZ)
        w.set(-127, GY, zz, 1)
        w.set(-127, GY - 1, zz, 1)
        w.set(-127, GY - 2, zz, "cherry_planks")
    yacht(w, -93, AZ + 6, 22, 7, "PEMBE RÜYA")
    yacht(w, -93, AZ - 7, 20, 6, "ALTIN KALP")
    yacht(w, -70, AZ, 30, 11, "AŞK GEMİSİ", hot_tub=True)
    for (lx, lz) in LIGHTHOUSES:
        lighthouse(w, lx, lz)
        w.occ |= (X - lx) ** 2 + (Z - lz) ** 2 <= 36
    # tekneler (varlik): iskelenin uclarinda bagli kiraz kayiklari
    for (bx, bz) in ((-112, AZ + 3), (-112, AZ - 3), (-100, AZ + 9), (-100, AZ - 10)):
        w.entity("minecraft:cherry_boat", bx + 0.5, SEA + 0.6, bz + 0.5, yaw=90.0)
    yacht_club(w)


def yacht_club(w: World):
    X, Z = w.XX, w.ZZ
    x0, x1 = CLUB
    plaza = (X >= x0) & (X <= x1) & (np.abs(Z - AZ) <= 16) & (w.D > 4) & ~w.occ
    wave = ((Z - AZ + (np.round(3 * np.sin(X / 4.0))).astype(int)) % 5 == 0)
    w.layer(GY, plaza, C.QUARTZ)
    w.layer(GY, plaza & wave, C.ROSE)
    px0, px1, pz0, pz1 = -152, -138, AZ - 7, AZ + 7
    w.box(px0, GY + 1, pz0, px1, GY + 5, pz1, C.GLASS)
    w.box(px0 + 1, GY + 1, pz0 + 1, px1 - 1, GY + 5, pz1 - 1, 1)
    for (xx, zz) in ((px0, pz0), (px0, pz1), (px1, pz0), (px1, pz1)):
        w.box(xx, GY + 1, zz, xx, GY + 5, zz, C.QPILLAR)
    w.box(px0 - 1, GY + 6, pz0 - 1, px1 + 1, GY + 6, pz1 + 1, C.WHITE)
    w.box(px0 - 1, GY + 6, pz0 - 1, px1 + 1, GY + 6, pz0 - 1, C.GOLD)
    w.box(px0 - 1, GY + 6, pz1 + 1, px1 + 1, GY + 6, pz1 + 1, C.GOLD)
    w.box(px0, GY + 1, AZ - 1, px0, GY + 3, AZ + 1, 1)
    w.box(px1, GY + 1, AZ - 1, px1, GY + 3, AZ + 1, 1)
    from aa_podium import table_grid
    table_grid(w, w.mask_rect(px0 + 1, pz0 + 1, px1 - 1, pz1 - 1), GY, step=4, seed=61)
    w.layer(GY + 6, w.mask_rect(px0 + 2, pz0 + 2, px1 - 2, pz1 - 2) & (X % 4 == 0) & (Z % 4 == 0), C.FROG)
    w.sign(px0 - 1, GY + 4, AZ + 3, "west", ["YAT KULÜBÜ", "♥", "", ""], color="black", wall=False) if False else None
    w.sign(px0 - 1, GY + 3, AZ + 2, "west", ["YAT KULÜBÜ", "♥", "", ""], color="black")
    w.occ |= plaza


# ------------------------------------------------------------------ su ustu villalar (kalp iskele)
def villas(w: World):
    X, Z = w.XX, w.ZZ
    D = w.D
    xt = -262
    col = D[:, xt - C.X0]
    cand = [z for z in range(AZ, C.Z1) if 6 <= col[z - C.Z0] <= 9]
    if not cand:
        return
    zt = max(cand)
    gx, gz = grad(w, D, xt, zt)
    ang = math.atan2(gz, gx)                       # uc adaya bakar
    s = 2.0
    ox = xt - 17.83 * s * math.cos(ang)
    oz = zt - 17.83 * s * math.sin(ang)
    px, pz = C.heart_poly_rot(ox, oz, s, ang)
    Dh, Mh = C.sdf(px, pz, C.X0, C.Z0, w.nx, w.nz, margin=14.0)
    walk = (np.abs(Dh) <= 1.5) & (D < 7)
    w.layer(GY - 1, walk, "pale_oak_planks")
    legs = walk & (C.hash2(X // 4, Z // 4, 2) < 2) & ((X + Z) % 5 == 0)
    pillars(w, legs & (D < 0), GY - 2, "stripped_pale_oak_log[axis=y]")
    post = walk & (np.abs(Dh) > 1.0) & ((X * 7 + Z * 3) % 11 == 0)
    w.layer(GY, post, POST)
    w.layer(GY + 1, post & ((X + Z) % 2 == 0), "lantern[hanging=false,waterlogged=false]")
    w.occ |= walk
    # villalar: cevre boyunca 10 nokta (ucun cevresi haric), disa dogru
    s_arc, L = C.arc_param(px, pz, px, pz)
    tip_i = int(np.argmin((px - xt) ** 2 + (pz - zt) ** 2))
    order = np.roll(np.arange(len(px)), -tip_i)
    picks = [order[int(len(order) * f)] for f in np.linspace(0.07, 0.93, 22)]
    placed = []
    for n, i in enumerate(picks):
        p = (float(px[i]), float(pz[i]))
        nx_, nz_ = grad(w, Dh, int(round(p[0])), int(round(p[1])))
        out = (-nx_, -nz_)
        dx, dz, face = snap_dir(*out)
        c = (int(round(p[0] + out[0] * 8)), int(round(p[1] + out[1] * 8)))
        if len(placed) >= 10 or any(abs(c[0] - q[0]) < 13 and abs(c[1] - q[1]) < 13 for q in placed):
            continue
        if D[c[1] - C.Z0, c[0] - C.X0] > -6:
            continue
        placed.append(c)
        villa(w, c[0], c[1], face, n)
        # baglanti yolu
        for k in range(0, 9):
            qx = int(round(p[0] + out[0] * k))
            qz = int(round(p[1] + out[1] * k))
            w.box(qx - 1, GY - 1, qz - 1, qx + 1, GY - 1, qz + 1, "pale_oak_planks", only=[0, 1])
    w.notes.append(f"su ustu villa: {len(placed)}")


def villa(w: World, cx, cz, face, n):
    """Su ustu villa (yerel: u yanal, v disa / denize dogru). Platform 11x11, ev 7x5, onde dalma havuzu ve sezlonglar."""
    fx, fz = C.FACE_VEC[face]
    lx, lz = -fz, fx

    def P(u, v):
        return cx + u * lx + v * fx, cz + u * lz + v * fz
    yd = GY - 1
    for u in range(-5, 6):
        for v in range(-5, 6):
            x, z = P(u, v)
            w.set(x, yd, z, "pale_oak_planks")
            w.set(x, yd - 1, z, C.WHITE)
            if abs(u) == 5 and abs(v) == 5 or (u == 0 and v == 0):
                fl = int(w.floor[z - C.Z0, x - C.X0]) if C.Z0 <= z <= C.Z1 and C.X0 <= x <= C.X1 else C.Y0
                for y in range(max(fl, C.Y0), yd - 1):
                    w.set(x, y, z, "stripped_pale_oak_log[axis=y]")
    # ev: v = -5..0 (adaya yakin yarim), u = -4..4
    for u in range(-4, 5):
        for v in range(-5, 1):
            x, z = P(u, v)
            edge = abs(u) == 4 or v in (-5, 0)
            for y in range(yd + 1, yd + 5):
                if edge:
                    st = C.WHITE
                    if v == 0 and abs(u) < 4:
                        st = C.CPANE
                    elif abs(u) == 4 and -4 <= v <= -1 and y in (yd + 2, yd + 3):
                        st = C.CPANE
                    w.set(x, y, z, st)
                else:
                    w.set(x, y, z, 1)
            w.set(x, yd + 5, z, C.WHITE)
    for u in range(-5, 6):
        for v in range(-6, 2):
            x, z = P(u, v)
            if abs(u) == 5 or v in (-6, 1):
                w.set(x, yd + 5, z, C.GOLD if v == 1 else "smooth_quartz_slab[type=bottom,waterlogged=false]")
    # kapi (adaya bakan arka duvar ortasi) ve camli zemin
    x, z = P(0, -5)
    w.box(min(x, x), yd + 1, min(z, z), x, yd + 2, z, 1)
    for (u, v) in ((-1, -2), (0, -2), (1, -2)):
        x, z = P(u, v)
        w.set(x, yd, z, C.GLASS)
        w.set(x, yd - 1, z, C.SEAL)
    # ic: iki kisilik yatak (bas adaya, ayak denize), komodin + mum, kanepe
    hx_, hz_ = P(-1, -4)
    hx2, hz2 = P(0, -4)
    fx1, fz1 = P(-1, -3)
    fx2, fz2 = P(0, -3)
    bf = face
    w.set(hx_, yd + 1, hz_, f"pink_bed[facing={C.OPP[bf]},occupied=false,part=head]")
    w.set(fx1, yd + 1, fz1, f"pink_bed[facing={C.OPP[bf]},occupied=false,part=foot]")
    w.set(hx2, yd + 1, hz2, f"pink_bed[facing={C.OPP[bf]},occupied=false,part=head]")
    w.set(fx2, yd + 1, fz2, f"pink_bed[facing={C.OPP[bf]},occupied=false,part=foot]")
    for u in (-2, 1):
        x, z = P(u, -4)
        w.set(x, yd + 1, z, "cherry_slab[type=top,waterlogged=false]")
        w.set(x, yd + 2, z, "pink_candle[candles=2,lit=true,waterlogged=false]")
    for u in (2, 3):
        x, z = P(u, -1)
        w.set(x, yd + 1, z, f"white_wool_stairs[facing={C.OPP[face]},half=bottom,shape=straight,waterlogged=false]")
    x, z = P(3, -4)
    w.set(x, yd + 1, z, "potted_flowering_azalea_bush")
    x, z = P(0, -1)
    w.set(x, yd + 4, z, "lantern[hanging=true,waterlogged=false]")
    # on guverte: dalma havuzu (3x2), sezlonglar, fener
    for u in (-3, -2, -1):
        for v in (2, 3):
            x, z = P(u, v)
            w.set(x, yd, z, "water")
            w.set(x, yd - 1, z, C.WHITE)
    for u in (-4, 0):
        for v in (1, 4):
            pass
    for u in (2, 4):
        x, z = P(u, 2)
        x2, z2 = P(u, 3)
        w.set(x, yd + 1, z, f"white_wool_stairs[facing={C.OPP[face]},half=bottom,shape=straight,waterlogged=false]")
        w.set(x2, yd + 1, z2, "white_wool_slab[type=bottom,waterlogged=false]")
    x, z = P(5, 5)
    w.set(x, yd + 1, z, POST)
    w.set(x, yd + 2, z, "lantern[hanging=false,waterlogged=false]")
    x, z = P(-5, 5)
    w.set(x, yd + 1, z, POST)
    w.set(x, yd + 2, z, "lantern[hanging=false,waterlogged=false]")
    x, z = P(1, -6)
    w.sign(x, yd + 2, z, C.OPP[face], ["", f"VİLLA {n + 1}", "♥", ""], color="black")


# ------------------------------------------------------------------ su alti tuneli, cam kubbe, mercanlar
def aquarium(w: World):
    D = w.D
    xt = -262
    col = D[:, xt - C.X0]
    cand = [z for z in range(C.Z0, AZ) if 6 <= col[z - C.Z0] <= 9]
    if not cand:
        return
    ez = min(cand)
    ex = xt
    # kubbe yeri: kuzeybatida, adadan en az 24 blok, taban 40..50
    best = None
    for dxk in range(-60, -20, 2):
        for dzk in range(-70, -20, 2):
            x, z = ex + dxk, ez + dzk
            if not (C.X0 + 16 < x < C.X1 - 16 and C.Z0 + 16 < z < C.Z1 - 16):
                continue
            if D[z - C.Z0, x - C.X0] > -26:
                continue
            fl = int(w.floor[z - C.Z0, x - C.X0])
            if 38 <= fl <= 50:
                sc = abs(dxk + 38) + abs(dzk + 40)
                if best is None or sc < best[0]:
                    best = (sc, x, z, fl)
    if best is None:
        w.notes.append("su alti kubbe: uygun yer yok")
        return
    _, dxw, dzw, fl = best
    fy = fl + 1
    R = 12
    # ic hacim (3B): egimli tunel + duz tunel (bati, sonra kuzey) + kubbe
    x0, x1 = dxw - R - 3, ex + 6
    z0, z1 = dzw - R - 3, ez + 4
    y0, y1 = fy - 2, GY + 6
    nx, ny, nz = x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1
    I = np.zeros((ny, nz, nx), bool)
    stairs = []
    steps = GY - 1 - fy
    for k in range(steps):
        x = ex - k
        yf = GY - 1 - k
        I[yf + 1 - y0:yf + 4 - y0, ez - 1 - z0:ez + 2 - z0, x - x0] = True
        stairs.append((x, yf))
    xs_end = ex - steps
    I[fy + 1 - y0:fy + 4 - y0, ez - 1 - z0:ez + 2 - z0, dxw - 1 - x0:xs_end + 1 - x0] = True
    I[fy + 1 - y0:fy + 4 - y0, dzw - z0:ez + 2 - z0, dxw - 1 - x0:dxw + 2 - x0] = True
    Yg, Zg, Xg = np.meshgrid(np.arange(y0, y1 + 1), np.arange(z0, z1 + 1), np.arange(x0, x1 + 1), indexing="ij")
    dome = ((Xg - dxw) ** 2 + (Zg - dzw) ** 2 + (Yg - fy) ** 2 < (R - 0.5) ** 2) & (Yg > fy)
    I |= dome
    pad = np.pad(I, 1)
    dil = pad[1:-1, 1:-1, 1:-1] | pad[2:, 1:-1, 1:-1] | pad[:-2, 1:-1, 1:-1] | pad[1:-1, 2:, 1:-1] | \
        pad[1:-1, :-2, 1:-1] | pad[1:-1, 1:-1, 2:] | pad[1:-1, 1:-1, :-2]
    shell = dil & ~I
    below = np.zeros_like(I)
    below[:-1] = I[1:]
    floor = shell & below
    ids = np.zeros(I.shape, np.uint16)
    ids[shell] = w.id(C.GLASS)
    ang = (np.degrees(np.arctan2(Zg - dzw, Xg - dxw)) % 30)
    rib = shell & dome.any() & (((ang < 2.5) | (ang > 27.5)) & ((Xg - dxw) ** 2 + (Zg - dzw) ** 2 <= (R + 1) ** 2))
    ids[rib & ~floor] = w.id(C.QUARTZ)
    ids[floor] = w.id(C.QUARTZ)
    ids[floor & ((Xg + Zg) % 4 == 0)] = w.id(C.SEAL)
    ids[I] = 1
    # yukarida (kumsal ustu) kabugu acik birak: giris pavyonu
    above = Yg >= GY
    ids[shell & above] = 0
    v = w.view(x0, y0, z0, x1, y1, z1)
    m = ids != 0
    v[m] = ids[m]
    for (x, yf) in stairs:
        w.box(x, yf, ez - 1, x, yf, ez + 1, "quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
        w.box(x, yf - 1, ez - 1, x, yf - 1, ez + 1, C.QUARTZ)
    # kubbe ici: zemin deseni, masalar, ortada "ters akvaryum" (cam sutunda su + yosun + deniz hiyari)
    X2, Z2 = w.XX, w.ZZ
    dfl = ((X2 - dxw) ** 2 + (Z2 - dzw) ** 2 <= (R - 1) ** 2)
    w.layer(fy, dfl & ((X2 + Z2) % 2 == 0), C.CALCITE)
    hx, hz = C.heart_poly(dxw + 0.5, dzw + 0.5, 0.22)
    w.layer(fy, w.mask_poly(hx, hz), C.ROSE)
    from aa_podium import table_grid
    ring = dfl & ((X2 - dxw) ** 2 + (Z2 - dzw) ** 2 >= 16) & ((X2 - dxw) ** 2 + (Z2 - dzw) ** 2 <= 64)
    table_grid(w, ring, fy, step=4, seed=71)
    w.box(dxw - 1, fy + 1, dzw - 1, dxw + 1, fy + 8, dzw + 1, C.GLASS)
    w.box(dxw, fy + 1, dzw, dxw, fy + 7, dzw, "water")
    w.set(dxw, fy + 1, dzw, "sand")                              # yosun yalniz tam blok ustunde tutunur
    for ddx, ddz in ((1, 0), (-1, 0)):
        w.set(dxw + ddx, fy + 1, dzw + ddz, C.SEAL)
    w.box(dxw, fy + 2, dzw, dxw, fy + 6, dzw, "kelp_plant")
    w.set(dxw, fy + 7, dzw, "kelp[age=20]")
    w.sign(ex + 2, GY + 2, ez, "west", ["SU ALTI", "RESTORANI", "↓ ♥ ↓", ""], color="black", wall=False)
    # giris pavyonu (kumsal ustunde): cam kutu, beyaz cati
    w.box(ex - 1, GY, ez - 3, ex + 5, GY, ez + 3, C.QUARTZ)
    w.box(ex - 1, GY + 1, ez - 3, ex + 5, GY + 4, ez + 3, C.GLASS)
    w.box(ex, GY + 1, ez - 2, ex + 4, GY + 4, ez + 2, 1)
    w.box(ex - 2, GY + 5, ez - 4, ex + 6, GY + 5, ez + 4, C.WHITE)
    w.box(ex - 2, GY + 5, ez - 4, ex + 6, GY + 5, ez - 4, C.GOLD)
    w.box(ex + 5, GY + 1, ez - 1, ex + 5, GY + 3, ez + 1, 1)
    for x in range(ex - 1, ex + 5):
        for zz in range(ez - 3, ez + 4):
            for y in range(SEA - 2, GY):
                if abs(zz - ez) >= 2 and w.get(x, y, zz) in (0, 1):
                    w.set(x, y, zz, C.QUARTZ)
    w.box(ex - 2, GY, ez - 1, ex, GY + 3, ez + 1, 1)
    for k in range(3):
        w.box(ex - k, GY - 1 - k, ez - 1, ex - k, GY - 1 - k, ez + 1,
              "quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    w.occ |= w.mask_rect(ex - 2, ez - 4, ex + 6, ez + 4)
    reef(w, dxw, dzw, R, I_box=(x0, z0, x1, z1), I=I)
    w.notes.append(f"su alti kubbe: merkez {dxw},{dzw}, zemin y={fy}, merdiven {steps} basamak")


def reef(w: World, cx, cz, R, I_box, I):
    X, Z = w.XX, w.ZZ
    d2 = (X - cx) ** 2 + (Z - cz) ** 2
    zone = (d2 >= (R + 1) ** 2) & (d2 <= (R + 16) ** 2) & (w.D < -6)
    x0, z0, x1, z1 = I_box
    tunnel = np.zeros(zone.shape, bool)
    tunnel[w.sub2(x0, z0, x1, z1)] = I.any(axis=0)
    zone &= ~C.dilate(tunnel, 2)
    fl = w.floor
    r = C.hash2(X, Z, 91)
    blocks = ("brain_coral_block", "bubble_coral_block", "fire_coral_block", "horn_coral_block", "tube_coral_block")
    plants = ("brain_coral", "bubble_coral", "fire_coral", "horn_coral", "tube_coral")
    fans = ("brain_coral_fan", "bubble_coral_fan", "fire_coral_fan", "horn_coral_fan", "tube_coral_fan")
    kind = (C.hash2(X // 3, Z // 3, 92) * 5).astype(int) % 5
    zs, xs = np.nonzero(zone & (r < 0.55))
    for z, x in zip(zs, xs):
        y = int(fl[z, x])
        if y < C.Y0 or y > SEA - 4:
            continue
        k = int(kind[z, x])
        rr = float(r[z, x])
        wx, wz = int(x) + C.X0, int(z) + C.Z0
        if rr >= 0.22 and w.G[y - C.Y0, z, x] == 0:
            w.set(wx, y, wz, "sand")                      # bitki dogal tabanda: tabani kum yap (oyun desteksizi dusurur)
        if rr < 0.22:
            w.set(wx, y, wz, blocks[k])
            if rr < 0.15:
                w.set(wx, y + 1, wz, f"{fans[k]}[waterlogged=true]")
        elif rr < 0.34:
            w.set(wx, y + 1, wz, f"{plants[k]}[waterlogged=true]")
        elif rr < 0.40:
            w.set(wx, y + 1, wz, "sea_pickle[pickles=3,waterlogged=true]")
        elif rr < 0.47:
            hgt = 3 + int(rr * 100) % 6
            for yy in range(y + 1, min(y + hgt, SEA - 1)):
                w.set(wx, yy, wz, "kelp_plant")
            w.set(wx, min(y + hgt, SEA - 1), wz, "kelp[age=24]")
        else:
            w.set(wx, y + 1, wz, "seagrass")


# ------------------------------------------------------------------ kumsal
def beach(w: World):
    from usta.kit import trees
    X, Z = w.XX, w.ZZ
    D = w.D
    band = w.beach & (D >= 5) & (D <= 11) & ~w.occ
    rng = random.Random(77)
    zs, xs = np.nonzero(band & (C.hash2(X, Z, 13) < 0.05))
    order = list(range(len(xs)))
    rng.shuffle(order)
    palms = []
    for i in order:
        x, z = int(xs[i]) + C.X0, int(zs[i]) + C.Z0
        if any((x - a) ** 2 + (z - b) ** 2 < 15 * 15 for a, b in palms):
            continue
        palms.append((x, z))
    b = C.kit_build("palmiye")
    for k, (x, z) in enumerate(palms):
        try:
            trees.tree(b, x, int(w.top[z - C.Z0, x - C.X0]), z, species="palm", size="large" if k % 3 == 0 else "medium",
                       seed=300 + k, ground=False)
        except Exception as e:  # pragma: no cover
            w.notes.append(f"palmiye atlandi: {e}")
    w.merge_build(b, only_empty=True)
    for (x, z) in palms:
        w.occ[z - C.Z0 - 1:z - C.Z0 + 2, x - C.X0 - 1:x - C.X0 + 2] = True
    # semsiye + iki sezlong (denize bakar)
    sb = w.beach & (D >= 3) & (D <= 8) & ~C.dilate(w.occ, 2)
    zs, xs = np.nonzero(sb & (C.hash2(X, Z, 17) < 0.10))
    order = list(range(len(xs)))
    rng.shuffle(order)
    sets = []
    for i in order:
        x, z = int(xs[i]) + C.X0, int(zs[i]) + C.Z0
        if any((x - a) ** 2 + (z - c) ** 2 < 16 * 16 for a, c in sets) or                 any((x - a) ** 2 + (z - c) ** 2 < 5 * 5 for a, c in palms):
            continue
        sets.append((x, z))
    for k, (x, z) in enumerate(sets):
        y = int(w.top[z - C.Z0, x - C.X0])
        gx, gz = grad(w, D, x, z)
        dx, dz, face = snap_dir(-gx, -gz)              # denize dogru
        lx, lz = -dz, dx
        w.box(x, y + 1, z, x, y + 3, z, "cherry_fence[east=false,north=false,south=false,waterlogged=false,west=false]")
        for u in (-1, 0, 1):
            for v in (-1, 0, 1):
                st = "pink_wool" if (u, v) == (0, 0) else ("pink_wool_slab[type=bottom,waterlogged=false]" if (u + v) % 2
                                                           else "white_wool_slab[type=bottom,waterlogged=false]")
                w.set(x + u, y + 4, z + v, st)
        for side in (-2, 2):
            sx, sz = x + lx * side, z + lz * side
            if w.top[sz - C.Z0, sx - C.X0] != y:
                continue
            w.set(sx, y + 1, sz, f"white_wool_stairs[facing={C.OPP[face]},half=bottom,shape=straight,waterlogged=false]")
            if w.top[sz + dz - C.Z0, sx + dx - C.X0] == y:
                w.set(sx + dx, y + 1, sz + dz, "white_wool_slab[type=bottom,waterlogged=false]")
            w.set(sx - dx, y + 1, sz - dz, "pink_carpet") if w.top[sz - dz - C.Z0, sx - dx - C.X0] == y else None
        w.occ[z - C.Z0 - 3:z - C.Z0 + 4, x - C.X0 - 3:x - C.X0 + 4] = True
    w.notes.append(f"kumsal: {len(palms)} palmiye, {len(sets)} semsiye takimi")
    # plaj barlari: kuzeybati ve guneybati kumsalinda
    for zsign in (-1, 1):
        x = -232
        col = D[:, x - C.X0]
        cz = [z for z in range(C.Z0, C.Z1) if 9 <= col[z - C.Z0] <= 11 and (z - AZ) * zsign > 60]
        if not cz:
            continue
        z = cz[0] if zsign < 0 else cz[-1]
        beach_bar(w, x, z, zsign)


def beach_bar(w: World, cx, cz, zsign):
    y = int(w.top[cz - C.Z0, cx - C.X0])
    w.box(cx - 4, y, cz - 3, cx + 4, y, cz + 3, "cherry_planks")
    for (dx, dz) in ((-4, -3), (4, -3), (-4, 3), (4, 3)):
        w.box(cx + dx, y + 1, cz + dz, cx + dx, y + 3, cz + dz, "stripped_cherry_log[axis=y]")
    w.box(cx - 5, y + 4, cz - 4, cx + 5, y + 4, cz + 4, "pink_wool_slab[type=bottom,waterlogged=false]")
    w.box(cx - 4, y + 4, cz - 3, cx + 4, y + 4, cz + 3, "pink_wool")
    w.box(cx - 2, y + 5, cz - 1, cx + 2, y + 5, cz + 1, "white_wool_slab[type=bottom,waterlogged=false]")
    fz = cz - 2 * zsign
    w.box(cx - 3, y + 1, fz, cx + 3, y + 1, fz, C.QUARTZ)
    w.box(cx - 3, y + 2, fz, cx + 3, y + 2, fz, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.box(cx - 3, y + 1, cz + 2 * zsign, cx + 3, y + 1, cz + 2 * zsign, "cherry_shelf[facing=%s,powered=false,side_chain=unconnected,waterlogged=false]" % ("north" if zsign > 0 else "south"))
    w.box(cx - 2, y + 2, cz + 2 * zsign, cx + 2, y + 2, cz + 2 * zsign, "brewing_stand")
    for dx in (-3, -1, 1, 3):
        w.set(cx + dx, y + 1, fz - zsign, "cherry_fence[east=false,north=false,south=false,waterlogged=false,west=false]")
        w.set(cx + dx, y + 2, fz - zsign, "pink_carpet")
    w.set(cx, y + 3, cz, "lantern[hanging=true,waterlogged=false]")
    w.sign(cx, y + 3, fz - zsign, "north" if zsign < 0 else "south", ["PLAJ BARI", "♥", "", ""], color="black") if False else None
    w.occ[cz - C.Z0 - 5:cz - C.Z0 + 6, cx - C.X0 - 6:cx - C.X0 + 7] = True


def parks(w: World):
    chapel(w)
    heart_lake(w)
    maze(w)
    wheel(w)
    carousel(w)
    marina(w)
    villas(w)
    aquarium(w)
    beach(w)
