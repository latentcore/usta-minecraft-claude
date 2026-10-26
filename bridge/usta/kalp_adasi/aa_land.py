"""Peyzaj: kiyi gezinti yolu, yapilari baglayan beyaz yollar, kiraz ve hus korulari, ciceklenmis azalea calilari,
cicek tarlalari (pembe yapraklar, laleler, sakayik, leylak, gul), yol fenerleri ve banklar. Son dis mekan gecisi."""
from __future__ import annotations

import math
import random

import numpy as np

import aa_core as C
import aa_park as PK
import aa_tower as T
from aa_core import AZ, GY, World

POST = "pale_oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]"


def polyline_mask(w: World, pts, r=1.5):
    X, Z = w.XX + 0.5, w.ZZ + 0.5
    m = np.zeros(X.shape, bool)
    for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:]):
        x0, x1 = sorted((ax, bx))
        z0, z1 = sorted((az, bz))
        sl = w.sub2(int(x0 - r - 2), int(z0 - r - 2), int(x1 + r + 2), int(z1 + r + 2))
        xs, zs = X[sl], Z[sl]
        dx, dz = bx - ax, bz - az
        ll = max(dx * dx + dz * dz, 1e-9)
        t = np.clip(((xs - ax) * dx + (zs - az) * dz) / ll, 0, 1)
        d = np.hypot(ax + t * dx - xs, az + t * dz - zs)
        m[sl] |= d <= r
    return m


def lamp(w: World, x, z, h=4):
    y = int(w.top[z - C.Z0, x - C.X0])
    if y < GY - 1:
        return
    w.box(x, y + 1, z, x, y + h, z, C.QPILLAR)
    w.set(x, y + h + 1, z, C.FROG)
    w.set(x, y + h + 2, z, "smooth_quartz_slab[type=bottom,waterlogged=false]")


def paths(w: World):
    X, Z = w.XX, w.ZZ
    lawn = w.lawn & ~w.occ
    # kiyi gezinti yolu (cimin kumsala bakan kenari)
    prom = w.lawn & C.dilate(w.beach, 3) & ~w.occ
    w.layer(GY, prom, C.CALCITE)
    w.layer(GY, prom & C.dilate(w.beach, 1), "polished_diorite")
    w.layer(GY, prom & ((X + Z) % 9 == 0), C.ROSE)
    routes = [
        [(-205, -747), (-205, -770), (-198, -786)],          # podyum kuzey kapisi -> sapel avlusu
        [(-205, -647), (-185, -628), (-158, -612)],          # podyum guney kapisi -> donme dolap
        [(-145, -713), (-140, -760), (-132, -806)],          # yat kulubu -> labirent girisi
        [(-145, -681), (-128, -655)],                        # yat kulubu -> atlikarinca
        [(-88, -786), (-71, -776)],                          # labirent -> kuzey deniz feneri
        [(-110, -646), (-71, -621)],                         # atlikarinca -> guney deniz feneri
        [(-140, -792), (-132, -806)],                        # sapel arkasi -> labirent
        [(-145, -610), (-127, -646)],                        # donme dolap -> atlikarinca
        [(-262, -712), (-243, -760), (-232, -790)],          # bulvar -> kalp golu
        [(-262, -682), (-235, -640), (-207, -622)],          # bulvar -> donme dolap
        [(-282, -712), (-266, -748)],                        # cesme meydani -> su alti girisi
        [(-282, -682), (-266, -642)],                        # cesme meydani -> villa iskelesi
    ]
    allp = np.zeros(X.shape, bool)
    for pts in routes:
        m = polyline_mask(w, pts, 1.5) & (w.lawn | w.beach) & ~w.occ
        allp |= m
    w.layer(GY, allp & w.lawn, C.QUARTZ)
    w.layer(GY, allp & w.lawn & C.edge4(allp), C.CALCITE)
    w.layer(GY, allp & w.beach & (w.top >= GY - 2), "smooth_sandstone")
    w.occ |= allp | prom
    # yol fenerleri: gezinti yolu ve ara yollar boyunca
    zs, xs = np.nonzero((prom | allp) & (C.hash2(X // 13, Z // 13, 5) < 2) & ((X % 13 == 0) & (Z % 13 == 0)))
    for z, x in zip(zs, xs):
        lamp(w, int(x) + C.X0, int(z) + C.Z0)
    w.notes.append(f"yollar: {int(allp.sum())} + gezinti {int(prom.sum())} hucre")
    return allp | prom


def groves(w: World, walk):
    from usta.kit import trees
    X, Z = w.XX, w.ZZ
    free = w.lawn & ~w.occ & ~C.dilate(walk, 2) & ~C.dilate(w.occ, 3)
    rng = random.Random(1907)
    pts = []
    step = 11
    for z in range(C.Z0 + 4, C.Z1 - 4, step):
        for x in range(C.X0 + 4, C.X1 - 4, step):
            jx = x + rng.randint(-3, 3)
            jz = z + rng.randint(-3, 3)
            if not (C.X0 < jx < C.X1 and C.Z0 < jz < C.Z1):
                continue
            if free[jz - C.Z0, jx - C.X0] and w.D[jz - C.Z0, jx - C.X0] > 18:
                pts.append((jx, jz))
    b = C.kit_build("koru")
    n_tree = n_bush = 0
    for i, (x, z) in enumerate(pts):
        r = rng.random()
        y = int(w.top[z - C.Z0, x - C.X0])
        try:
            if r < 0.62:
                trees.tree(b, x, y, z, species="cherry", size="large" if r < 0.2 else "medium", seed=2000 + i)
                n_tree += 1
            elif r < 0.78:
                trees.tree(b, x, y, z, species="birch", size="medium", seed=2000 + i)
                n_tree += 1
            else:
                trees.bush(b, x, y, z, kind="flowering_azalea" if r < 0.92 else "cherry", size="small", seed=2000 + i)
                n_bush += 1
        except Exception as e:  # pragma: no cover
            w.notes.append(f"agac atlandi: {e}")
    w.merge_build(b, only_empty=True)
    for (x, z) in pts:
        w.occ[z - C.Z0, x - C.X0] = True
    w.notes.append(f"koru: {n_tree} agac, {n_bush} cali")


def meadows(w: World):
    X, Z = w.XX, w.ZZ
    G = w.G
    y = GY + 1
    free = w.lawn & ~w.occ & (G[y - C.Y0] == 0) & (G[GY - C.Y0] == w.id("grass_block[snowy=false]"))
    patch = C.noise2(X, Z, scale=14.0, seed=33)
    r = C.hash2(X, Z, 34)
    dense = patch > 0.55
    p_scale = np.where(dense, 1.0, 0.35)
    table = [("pink_petals[facing=north,flower_amount=4]", 0.16), ("pink_petals[facing=east,flower_amount=2]", 0.06),
             ("pink_tulip", 0.03), ("white_tulip", 0.025), ("oxeye_daisy", 0.02), ("azure_bluet", 0.02),
             ("lily_of_the_valley", 0.015), ("allium", 0.008), ("short_grass", 0.06)]
    acc = np.zeros(X.shape, np.float32)
    for st, p in table:
        m = free & (r >= acc) & (r < acc + p * p_scale)
        w.layer(y, m, st)
        acc = acc + p * p_scale
    for st, p in (("peony", 0.010), ("lilac", 0.007), ("rose_bush", 0.010)):
        m = free & (r >= acc) & (r < acc + p * p_scale) & (G[y + 1 - C.Y0] == 0)
        w.layer(y, m, f"{st}[half=lower]")
        w.layer(y + 1, m, f"{st}[half=upper]")
        acc = acc + p * p_scale
    # gul bahceleri: sapelin ve podyumun cevresinde yogun gul + sakayik tarhlari
    rose = w.lawn & ~w.occ & (G[y - C.Y0] == 0) & (
        (np.abs(X - (PK.CH_X0 + PK.CH_X1) / 2) <= 30) & (np.abs(Z - PK.CH_ZC) <= 20) |
        (C.dilate(T.geo(w, T.SP)["P"], 6) & ~C.dilate(T.geo(w, T.SP)["P"], 3)))
    rr = C.hash2(X, Z, 35)
    m = rose & (rr < 0.30) & (G[y + 1 - C.Y0] == 0)
    w.layer(y, m & (rr < 0.18), "rose_bush[half=lower]")
    w.layer(y + 1, m & (rr < 0.18), "rose_bush[half=upper]")
    w.layer(y, m & (rr >= 0.18), "peony[half=lower]")
    w.layer(y + 1, m & (rr >= 0.18), "peony[half=upper]")


def benches(w: World, walk):
    X, Z = w.XX, w.ZZ
    prom_side = w.lawn & ~w.occ & C.dilate(walk, 1) & ~walk & ((X * 3 + Z * 5) % 23 == 0)
    zs, xs = np.nonzero(prom_side)
    n = 0
    for z, x in zip(zs, xs):
        wx, wz = int(x) + C.X0, int(z) + C.Z0
        gx, gz = PK.grad(w, w.D, wx, wz)
        dx, dz, face = PK.snap_dir(-gx, -gz)
        if w.G[GY + 1 - C.Y0, z, x] != 0:
            continue
        w.set(wx, GY + 1, wz, f"cherry_stairs[facing={C.OPP[face]},half=bottom,shape=straight,waterlogged=false]")
        n += 1
    w.notes.append(f"bank: {n}")


def land(w: World):
    walk = paths(w)
    groves(w, walk)
    meadows(w)
    benches(w, walk)
