"""Ada: kalp seklinde yapay ada (dolgu, kumsal kademeleri, su alti sahanligi, rihtimlar, deniz cayiri, gece isildayan
deniz hiyari halkasi). Zemin yuksekligi W.top'a, kumsal/cim maskeleri W.beach / W.lawn'a yazilir."""
from __future__ import annotations

import numpy as np

import aa_core as C
from aa_core import GY, SEA, World


def island(w: World):
    ter = C.load_terrain()
    w.floor = ter["floor"].astype(np.int32)
    w.ter = ter
    px, pz = C.heart_poly(C.XT, C.AZ, C.S_ISL, ref="tip")
    w.isl_poly = (px, pz)
    D, ins = C.sdf(px, pz, C.X0, C.Z0, w.nx, w.nz)
    w.D, w.isl = D, ins
    X, Z = w.XX, w.ZZ
    # karada kurulum: adanin disinda deniz olmasi gereken kara sutunlari lagun olarak kazilir (su SEA'ye kadar)
    dry = ~ins & (D > -80) & (ter["ground"] > SEA)            # deniz seviyesinin ustune cikan kara (yosun/cayir degil)
    if dry.any():
        surf = ter["surface"].astype(np.int32)
        bed = SEA - 6
        for y in range(bed, int(surf[dry].max()) + 1):
            m = dry & (surf >= y)
            if m.any():
                w.layer(y, m, "sand" if y == bed else ("water" if y <= SEA else 1))
        w.floor = np.where(dry, bed, w.floor).astype(np.int32)
        w.notes.append(f"lagun: {int(dry.sum())} kara sutunu kazildi")
    n1 = C.noise2(X, Z, scale=22.0, seed=11) * 2 - 1
    bw = 13.0 + 5.0 * n1

    # rihtim (sert kenar) bolgeleri: koy (marina), ucun iskelesi
    cleft = (X > -132) & (np.abs(Z - C.AZ) < 60)
    tip = X < -330
    w.cleft = cleft

    h = np.full(D.shape, -999, np.int32)
    land = D > 0
    h[land & (D <= 2)] = SEA
    h[land & (D > 2)] = SEA + 1
    h[land & (D > bw * 0.6)] = SEA + 2
    h[land & (D > bw)] = GY
    hard = (cleft | tip) & land & (D <= 7)
    h[hard] = GY
    w.hard = hard
    shelf = (D <= 0) & (D > -16) & ~(cleft & (D < 0))
    sh = np.floor(SEA - 1 + D * 0.42).astype(np.int32)
    nat = w.floor
    sh = np.where(shelf & (sh > nat), sh, -999)
    h = np.where(shelf, sh, h)
    w.top = np.where(h > -999, h, w.top).astype(np.int16)

    beach = land & (h < GY)
    lawn = land & (h == GY) & ~hard
    w.beach, w.lawn = beach, lawn

    # dolgu + katmanlar (Y0'dan ust bloga)
    fillm = h > -999
    stone = w.id("stone")
    G = w.G
    hi = int(h.max())
    for y in range(C.Y0, hi + 1):
        L = G[y - C.Y0]
        m = fillm & (h >= y) & (y >= nat - 3)
        if not m.any():
            continue
        depth = h - y                      # 0 = ust blok
        L[m & (depth >= 6)] = stone
        L[m & (depth >= 3) & (depth < 6) & ~beach & ~shelf] = w.id("dirt")
        L[m & (depth >= 3) & (depth < 6) & (beach | shelf)] = w.id("sandstone")
        L[m & (depth >= 1) & (depth < 3) & ~beach & ~shelf] = w.id("dirt")
        L[m & (depth >= 1) & (depth < 3) & (beach | shelf)] = w.id("sand")
        L[m & (depth == 0) & lawn] = w.id("grass_block[snowy=false]")
        L[m & (depth == 0) & (beach | shelf)] = w.id("sand")
        L[m & (depth == 0) & hard] = w.id(C.QUARTZ)
        L[m & (depth >= 1) & (depth < 6) & hard] = w.id("stone")

    # dogal tepecikler adanin icinde kaliyorsa kes (ada zemini uzerindeki dogal bloklar)
    surf = w.ter["surface"].astype(np.int32)
    cut = land & (surf > h)
    for y in range(SEA - 6, int(surf[cut].max()) + 1 if cut.any() else SEA - 6):
        m = cut & (y > h) & (y <= surf)
        if m.any():
            G[y - C.Y0][m] = 1

    # rihtim duvari: sert kenarin disina deniz tabanindan zemine beyaz duvar + altin harpuşta
    qwall = C.ring_out(hard) & (D <= 0.5)
    for y in range(C.Y0, GY + 1):
        m = qwall & (y >= np.maximum(nat - 1, C.Y0))
        if m.any():
            G[y - C.Y0][m] = w.id(C.WHITE if y < GY else C.QUARTZ)
    w.top = np.where(qwall, GY, w.top).astype(np.int16)
    w.quay_wall = qwall

    # su alti: deniz cayiri, deniz hiyari halkasi (gece adanin cevresinde isik)
    rnd = C.hash2(X, Z, 5)
    sg = shelf & (D < -1) & (D > -12) & (rnd < 0.28) & (h < SEA - 1)
    for y in np.unique(h[sg]):
        m = sg & (h == y)
        if int(y) >= C.Y0:                                       # dogal taban belirsizse kum: bitki dusmesin
            w.layer(int(y), m & (w.G[int(y) - C.Y0] == 0), "sand")
        w.layer(int(y) + 1, m, "seagrass")
    pick = shelf & (D < -3) & (D > -8) & (C.hash2(X // 3, Z // 3, 9) < 0.10) & (rnd > 0.5) & (h < SEA - 2)
    for y in np.unique(h[pick]):
        m = pick & (h == y)
        if int(y) >= C.Y0:
            w.layer(int(y), m & (w.G[int(y) - C.Y0] == 0), "sand")
        w.layer(int(y) + 1, m, "sea_pickle[pickles=4,waterlogged=true]")
    w.notes.append(f"ada: {int(land.sum())} kara hucresi, kumsal {int(beach.sum())}, cim {int(lawn.sum())}")
