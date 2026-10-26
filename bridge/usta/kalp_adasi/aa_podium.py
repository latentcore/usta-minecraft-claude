"""Podyum ic mekanlari: cift yukseklikte lobi (kalp kakmali zemin, kalp havuzlu cesme, resepsiyon, avizeler, iki
genis merdiven), balo salonu (isikli dans pisti, sahne, piyano), Ask Sinemasi (kademeli koltuklar, perde), Gul
Restorani, Tatli Ask pastanesi; ust katta spa (havuz, kabarcikli jakuziler, sauna, masaj), cocuk kulubu, spor salonu,
dugun salonu ve butikler."""
from __future__ import annotations

import numpy as np

import aa_core as C
import aa_tower as T
from aa_core import World

CX, CZ = T.CX, T.CZ
G0, G1 = T.PFLOORS                 # 65, 76
POST = "pale_oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]"
CHAIR = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}
FROG = C.FROG

# ic hacim kutulari (x0, z0, x1, z1)
BALLROOM = (-212, -735, -187, -716)
CINEMA = (-212, -678, -187, -659)
RESTAURANT = (-185, -731, -171, -716)
CAFE = (-185, -678, -171, -663)
SPA = (-212, -735, -187, -716)
KIDS = (-212, -678, -200, -659)
GYM = (-198, -678, -187, -659)
WEDDING = (-185, -731, -171, -716)
SHOP1 = (-185, -678, -179, -663)
SHOP2 = (-177, -678, -171, -663)


def shell(w: World, box, yf, h, wall=C.WHITE, floor="polished_diorite", doors=(), glass=None):
    """Dikdortgen oda kabugu. box ic hacim (x0,z0,x1,z1); hava yf+1..yf+h; zemin yf; duvarlar halkada.
    doors: [(x, z, genislik, yukseklik, eksen)] eksen 'x' = kapi x boyunca uzanir (kuzey/guney duvari)."""
    x0, z0, x1, z1 = box
    w.box(x0 - 1, yf + 1, z0 - 1, x1 + 1, yf + h, z1 + 1, wall)
    w.box(x0, yf + 1, z0, x1, yf + h, z1, 1)
    if floor:
        w.box(x0, yf, z0, x1, yf, z1, floor)
    if glass:
        # ust bant: koridora bakan duvarlarda cam serit (ic mekan aydinligi)
        for (a, b, c, d) in glass:
            w.box(a, yf + h - 1, b, c, yf + h - 1, d, C.CPANE)
    for (dx, dz, wd, ht, ax) in doors:
        if ax == "x":
            w.box(dx - wd // 2, yf + 1, dz, dx - wd // 2 + wd - 1, yf + ht, dz, 1)
        else:
            w.box(dx, yf + 1, dz - wd // 2, dx, yf + ht, dz - wd // 2 + wd - 1, 1)


def chandelier(w: World, x, z, y_ceil, drop=4, r=2):
    """Altin halkali avize: tavandan zincir, altin gobek, kollarda kurbaga isigi ve mumlar."""
    for y in range(y_ceil - drop, y_ceil):
        w.set(x, y, z, "iron_chain[axis=y,waterlogged=false]")
    yb = y_ceil - drop - 1
    w.set(x, yb, z, C.GOLD)
    w.set(x, yb - 1, z, FROG)
    for dx, dz in ((r, 0), (-r, 0), (0, r), (0, -r)):
        for k in range(1, r):
            w.set(x + (dx // r) * k, yb, z + (dz // r) * k, "iron_chain[axis=%s,waterlogged=false]" % ("x" if dx else "z"))
        w.set(x + dx, yb, z + dz, C.GOLD)
        w.set(x + dx, yb - 1, z + dz, "lantern[hanging=true,waterlogged=false]")
        w.set(x + dx, yb + 1, z + dz, "pink_candle[candles=3,lit=true,waterlogged=false]")


def table_grid(w: World, mask, y, step=4, seed=0, cloth="white_carpet", chairs="cherry"):
    """Yuvarlak masa (cit + ortu + mum) ve dort yaninda sandalye."""
    X, Z = w.XX, w.ZZ
    t = mask & (X % step == 1) & (Z % step == 1)
    t &= C.erode(mask, 1, square=True)
    w.layer(y + 1, t, POST)
    w.layer(y + 2, t, cloth)
    w.layer(y + 3, t & (C.hash2(X, Z, seed) < 0.5), "potted_pink_tulip")
    w.layer(y + 3, t & (C.hash2(X, Z, seed) >= 0.5) & (C.hash2(X, Z, seed) < 0.8), "potted_white_tulip")
    for (dx, dz), f in CHAIR.items():
        m = C.shift(t, dz, dx) & mask
        w.layer(y + 1, m, f"{chairs}_stairs[facing={f},half=bottom,shape=straight,waterlogged=false]", empty=True)
    return t


def rect_mask(w, box):
    x0, z0, x1, z1 = box
    return w.mask_rect(x0, z0, x1, z1)


# ------------------------------------------------------------------ lobi
def lobby(w: World):
    X, Z = w.XX, w.ZZ
    L = w.podium_lobby
    inner = T.geo(w, T.SP)["inner"]
    gfl = inner & ~(rect_mask(w, (-213, -737, -186, -714)) | rect_mask(w, (-213, -680, -186, -657)))
    # zemin: beyaz kuvars + altin cizgiler; lobide dev pembe kalp kakmasi ve altin kontur
    pat = ((X % 6 == 0) | (Z % 6 == 0))
    w.layer(G0, gfl & ~pat, C.QUARTZ)
    w.layer(G0, gfl & pat, C.CALCITE)
    hx, hz = C.heart_poly(-228, CZ, 1.05)
    hm = w.mask_poly(hx, hz) & L
    w.layer(G0, hm, C.ROSE)
    w.layer(G0, C.edge4(hm), C.GOLD)
    # kalp havuzlu cesme (ortada): kenar kuvars, icinde su, ortada altin sutun ve kurbaga isigi
    fx, fz = C.heart_poly(-229, CZ, 0.42)
    fm = w.mask_poly(fx, fz)
    w.layer(G0, fm, C.WHITE)
    w.layer(G0 + 1, C.edge4(fm), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    inner_f = fm & ~C.edge4(fm)
    w.layer(G0 + 1, inner_f, "water")
    w.layer(G0, inner_f & ((X + Z) % 3 == 0), C.SEAL)
    w.box(-229, G0 + 1, CZ, -229, G0 + 4, CZ, C.GOLD)
    w.set(-229, G0 + 5, CZ, FROG)
    for dz in (-1, 1):
        w.set(-229, G0 + 2, CZ + dz, "lily_pad") if False else None
    # resepsiyon: cekirdegin onunde kavisli tezgah (kuvars + altin), zil, saksilar
    for zz in range(CZ - 7, CZ + 8):
        xx = -216 + (1 if abs(zz - CZ) > 5 else 0)
        w.set(xx, G0 + 1, zz, C.QUARTZ)
        w.set(xx, G0 + 2, zz, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.set(-216, G0 + 2, CZ - 2, C.QUARTZ)          # zil tam blogun ustunde (yarim basamakta oyun dusurur)
    w.set(-216, G0 + 3, CZ - 2, "bell[attachment=floor,facing=west,powered=false]")
    w.set(-216, G0 + 3, CZ + 3, "potted_pink_tulip")
    w.set(-216, G0 + 3, CZ - 5, "potted_white_tulip")
    w.box(-216, G0 + 1, CZ - 8, -216, G0 + 1, CZ - 8, C.GOLD)
    w.box(-216, G0 + 1, CZ + 8, -216, G0 + 1, CZ + 8, C.GOLD)
    w.sign(T.SHAFT[0] - 1, G0 + 4, CZ - 4, "west", ["KALP KULESİ", "RESEPSİYON", "♥ HOŞ GELDİN ♥", ""], color="black")
    # oturma gruplari: pembe kanepe sirasi + onunde sehpa ve mum
    for (sx, sz, face) in ((-236, CZ - 10, "west"), (-236, CZ + 10, "west"), (-224, CZ - 19, "north"),
                           (-224, CZ + 19, "south")):
        stair = f"pink_wool_stairs[facing={C.OPP[face]},half=bottom,shape=straight,waterlogged=false]"
        fx_, fz_ = C.FACE_VEC[face]
        for k in range(-2, 3):
            if face in ("west", "east"):
                w.set(sx, G0 + 1, sz + k, stair)
            else:
                w.set(sx + k, G0 + 1, sz, stair)
        for k in (-1, 0, 1):
            tx, tz = (sx + 2 * fx_, sz + k) if face in ("west", "east") else (sx + k, sz + 2 * fz_)
            w.set(tx, G0 + 1, tz, "cherry_slab[type=top,waterlogged=false]")
        w.set(sx + 2 * fx_, G0 + 2, sz + 2 * fz_, "pink_candle[candles=4,lit=true,waterlogged=false]")
    # avizeler (cift yukseklik: tavan 86)
    for (cx_, cz_) in ((-232, CZ), (-222, CZ - 12), (-222, CZ + 12), (-226, CZ)):
        chandelier(w, cx_, cz_, T.ROOF, drop=6 if cx_ != -226 else 3, r=2)
    # saksilarda kiraz agaclari (lobi koseleri)
    from usta.kit import trees
    b = C.kit_build("lobi_agac")
    for i, (tx, tz) in enumerate(((-236, CZ - 4), (-236, CZ + 4), (-219, CZ - 21), (-219, CZ + 21))):
        w.box(tx - 1, G0 + 1, tz - 1, tx + 1, G0 + 1, tz + 1, C.QUARTZ)
        w.set(tx, G0 + 1, tz, "grass_block[snowy=false]")
        trees.tree(b, tx, G0 + 1, tz, species="cherry", size="small", seed=500 + i, ground=False)
    w.merge_build(b, only_empty=True)
    # iki genis merdiven: zeminden ust kat galerisine (bosluk kenarlari boyunca, doguya cikar)
    for zsg in (-1, 1):
        zz0 = CZ + zsg * 23
        zs = sorted((zz0, zz0 + zsg * 2))
        for k in range(10):
            xx = -230 + k
            w.box(xx, G0 + 1 + k, zs[0], xx, G0 + 1 + k, zs[1],
                  "quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
            if k:
                w.box(xx, G0 + 1, zs[0], xx, G0 + k, zs[1], C.QUARTZ)
        w.box(-220, G1, zs[0], -214, G1, zs[1], C.QUARTZ)
        w.box(-220, G1 + 1, zs[0], -214, G1 + 3, zs[1], 1)
        rail_z = zs[0] - 1 if zsg > 0 else zs[1] + 1
        for k in range(10):
            w.set(-230 + k, G0 + 2 + k, rail_z, C.CPANE)
        edge_z = zs[0] - 1 if zsg < 0 else zs[1] + 1
        w.box(-220, G1 + 1, edge_z, -214, G1 + 1, edge_z, 1)
        w.box(-213, G1 + 1, zs[0], -213, G1 + 1, zs[1], 1)
    # yol gosteren tabelalar
    for zz, lines in ((CZ - 12, ["↖ BALO SALONU", "↖ GÜL RESTORANI", "↖ SPA (1. KAT)", ""]),
                      (CZ + 12, ["↗ AŞK SİNEMASI", "↗ PASTANE", "↗ BUTİKLER", ""])):
        w.box(-214, G0 + 1, zz, -214, G0 + 2, zz, C.QPILLAR)
        w.sign(-214, G0 + 3, zz, "west", lines, color="black", wall=False)


# ------------------------------------------------------------------ balo salonu
def ballroom(w: World):
    X, Z = w.XX, w.ZZ
    x0, z0, x1, z1 = BALLROOM
    h = G1 - G0 - 1
    shell(w, BALLROOM, G0, h, wall=C.WHITE, floor="cherry_planks",
          doors=((-206, z1 + 1, 3, 4, "x"), (-194, z1 + 1, 3, 4, "x")))
    m = rect_mask(w, BALLROOM)
    pat = ((X + Z) % 2 == 0)
    w.layer(G0, m & pat, C.QUARTZ)
    w.layer(G0, m & ~pat, "cherry_planks")
    dance = rect_mask(w, (-206, -731, -195, -720))
    w.layer(G0, dance & pat, FROG)
    w.layer(G0, dance & ~pat, "pink_glazed_terracotta[facing=north]")
    w.layer(G0, C.edge4(dance), C.GOLD)
    # sahne (dogu ucu): bir kat yuksek, pembe perde, piyano, mikrofon, hoparlorler
    w.box(x1 - 4, G0 + 1, z0 + 2, x1, G0 + 1, z1 - 2, C.QUARTZ)
    w.box(x1 - 5, G0 + 1, z0 + 2, x1 - 5, G0 + 1, z1 - 2, "smooth_quartz_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
    w.box(x1, G0 + 2, z0 + 1, x1, G0 + h, z1 - 1, "pink_wool")
    w.box(x1, G0 + h, z0 + 1, x1, G0 + h, z1 - 1, C.GOLD)
    pz = (z0 + z1) // 2
    w.box(x1 - 3, G0 + 2, pz - 3, x1 - 1, G0 + 2, pz - 2, "black_concrete")
    w.box(x1 - 3, G0 + 3, pz - 3, x1 - 1, G0 + 3, pz - 3, "quartz_slab[type=bottom,waterlogged=false]")
    w.set(x1 - 2, G0 + 2, pz - 1, "polished_blackstone_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
    w.set(x1 - 3, G0 + 2, pz + 2, "lightning_rod[facing=up,powered=false,waterlogged=false]")
    for zz in (z0 + 3, z1 - 3):
        w.set(x1 - 1, G0 + 2, zz, "jukebox[has_record=false]")
        w.set(x1 - 1, G0 + 3, zz, "note_block[instrument=harp,note=0,powered=false]")
    # yuvarlak masalar (dans pistinin cevresi)
    ring = m & ~C.dilate(dance, 2) & ~rect_mask(w, (x1 - 6, z0, x1, z1))
    table_grid(w, ring, G0, step=4, seed=3)
    # avizeler
    for cx_ in (-208, -200, -192):
        for cz_ in (-730, -721):
            chandelier(w, cx_, cz_, G1, drop=3, r=2)
    w.sign(-206, G0 + 6, z1 + 2, "south", ["BALO", "SALONU", "♥", ""], color="black")


# ------------------------------------------------------------------ sinema
def cinema(w: World):
    x0, z0, x1, z1 = CINEMA
    h = G1 - G0 - 1
    shell(w, CINEMA, G0, h, wall="black_concrete", floor="red_carpet" if False else "black_concrete",
          doors=((-190, z0 - 1, 3, 4, "x"), (-198, z0 - 1, 3, 5, "x")))
    w.box(x0, G0 + 1, z0, x1 - 5 - 2 * 7, G0 + 6, z1, "black_concrete")
    # perde (dogu duvari): beyaz beton, siyah cerceve, altin ust kenar
    w.box(x1 + 1, G0 + 3, z0 + 2, x1 + 1, G0 + h - 1, z1 - 2, C.WHITE)
    w.box(x1 + 1, G0 + h, z0 + 1, x1 + 1, G0 + h, z1 - 1, C.GOLD)
    # kademeli koltuk siralari (bati yukari), orta ve yan koridorlar
    zc = (z0 + z1) // 2
    for r in range(7):
        xa, xb = x1 - 5 - 2 * r - 1, x1 - 5 - 2 * r
        yt = G0 + r
        if r:
            w.box(xa, G0 + 1, z0, xb, yt, z1, "black_concrete")
        for zz in range(z0, z1 + 1):
            aisle = zz in (z0, zc, z1)
            if aisle:
                w.set(xb, yt + 1, zz, "smooth_quartz_slab[type=bottom,waterlogged=false]") if r else None
                continue
            w.set(xb, yt + 1, zz, "pink_wool_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        w.set(xa, yt + 1, z0, "sea_lantern") if False else None
    # yan duvar isiklari (los) ve projektor
    for zz in (z0 - 1, z1 + 1):
        for xx in range(x0 + 1, x1, 4):
            w.set(xx, G0 + 5, zz, "ochre_froglight[axis=y]")
    w.set(x0 - 1, G0 + 8, zc, C.SEAL)
    # giris onunde misir/patlamis misir bufesi
    w.box(-200, G0 + 1, z0 - 4, -197, G0 + 1, z0 - 4, "red_concrete")
    w.box(-200, G0 + 2, z0 - 4, -197, G0 + 2, z0 - 4, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.set(-199, G0 + 3, z0 - 4, "decorated_pot[cracked=false,facing=north,waterlogged=false]")
    w.sign(-206, G0 + 6, z0 - 2, "north", ["AŞK", "SİNEMASI", "♥ ♥ ♥", ""], color="black")


# ------------------------------------------------------------------ restoran, pastane
def restaurant(w: World):
    x0, z0, x1, z1 = RESTAURANT
    h = G1 - G0 - 1
    shell(w, RESTAURANT, G0, h, floor="cherry_planks", doors=((-178, z1 + 1, 3, 4, "x"),))
    m = rect_mask(w, RESTAURANT)
    X, Z = w.XX, w.ZZ
    w.layer(G0, m & ((X + Z) % 2 == 0), C.QUARTZ)
    bar = rect_mask(w, (x1, z0 + 1, x1, z1 - 3))
    w.layer(G0 + 1, bar, C.QUARTZ)
    w.layer(G0 + 2, bar, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.layer(G0 + 3, bar & (Z % 2 == 0), "brewing_stand")
    table_grid(w, m & ~rect_mask(w, (x1 - 1, z0, x1, z1)), G0, step=4, seed=11)
    for cz_ in (-727, -720):
        chandelier(w, -178, cz_, G1, drop=3, r=1)
    w.sign(-178, G0 + 6, z1 + 2, "south", ["GÜL", "RESTORANI", "", ""], color="black")


def cafe(w: World):
    x0, z0, x1, z1 = CAFE
    h = G1 - G0 - 1
    shell(w, CAFE, G0, h - 4, floor="polished_diorite", doors=((-178, z0 - 1, 3, 4, "x"),))
    w.box(x0, G0 + h - 3, z0, x1, G0 + h - 3, z1, C.WHITE)          # alcak tavan (5 yuksek kafe)
    w.kit_room((x0, G0 + 1, z0, x1, G0 + h - 4, z1), "cafe", [(-178, G0 + 1, z0 - 1)], seed=21, style=C.ROMANTIC)
    w.sign(-178, G0 + 5, z0 - 2, "north", ["TATLI AŞK", "PASTANESİ", "", ""], color="black")


# ------------------------------------------------------------------ ust kat
def spa(w: World):
    x0, z0, x1, z1 = SPA
    h = T.ROOF - G1 - 1
    shell(w, SPA, G1, h, floor=C.QUARTZ, doors=((-206, z1 + 1, 3, 4, "x"),))
    X, Z = w.XX, w.ZZ
    # havuz: 1 derin, zemin seviyesinde su, tabaninda isiklar (balo salonunun tavaninda kaset isik)
    pool = rect_mask(w, (-207, -731, -194, -722))
    w.layer(G1, pool, "water")
    w.layer(G1 - 1, pool, C.WHITE)
    w.layer(G1 - 1, pool & (X % 3 == 0) & (Z % 3 == 0), C.SEAL)
    w.layer(G1 + 1, C.ring_out(pool), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    # kabarcikli jakuziler (yukseltilmis, 3x3 kabarcik)
    for jz in (-731, -721):
        jx = -191
        w.box(jx - 2, G1 + 1, jz - 2, jx + 2, G1 + 2, jz + 2, C.GOLD)
        w.box(jx - 1, G1 + 1, jz - 1, jx + 1, G1 + 1, jz + 1, "soul_sand")
        w.box(jx - 1, G1 + 2, jz - 1, jx + 1, G1 + 2, jz + 1, "bubble_column[drag=false]")
        w.set(jx + 2, G1 + 3, jz, "pink_candle[candles=4,lit=true,waterlogged=false]")
    # sauna (bati ucu): ladin, banklar, yanan ocak
    w.box(x0, G1 + 1, z0, x0 + 3, G1 + 4, z0 + 4, "spruce_planks")
    w.box(x0, G1 + 1, z0 + 1, x0 + 2, G1 + 3, z0 + 3, 1)
    w.box(x0 + 3, G1 + 1, z0 + 2, x0 + 3, G1 + 2, z0 + 2, 1)
    w.box(x0, G1 + 1, z0 + 1, x0, G1 + 1, z0 + 3, "spruce_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
    w.set(x0 + 2, G1 + 1, z0 + 1, "smoker[facing=south,lit=true]")
    w.set(x0 + 1, G1 + 4, z0 + 2, "ochre_froglight[axis=y]")
    w.sign(x0 + 4, G1 + 3, z0 + 2, "east", ["SAUNA", "", "", ""], color="black")
    # masaj yataklari (dogu ucu)
    for zz in (-728, -725, -722, -719):
        w.box(x0, G1 + 1, zz, x0 + 2, G1 + 1, zz, "white_wool_slab[type=bottom,waterlogged=false]")
        w.set(x0 + 1, G1 + 1, zz + 1, "pink_carpet")
    w.layer(G1 + 1, C.edge4(rect_mask(w, SPA)) & ((X + Z) % 3 == 0), "potted_cherry_sapling", empty=True)
    w.layer(T.ROOF, rect_mask(w, SPA) & (X % 4 == 0) & (Z % 4 == 0), FROG, only=[w.id(C.WHITE)])
    w.sign(-206, G1 + 5, z1 + 2, "south", ["GÜL SPA", "HAVUZ · JAKUZİ", "SAUNA · MASAJ", ""], color="black")


def upper_rooms(w: World):
    h = T.ROOF - G1 - 1
    shell(w, KIDS, G1, h, floor=None, doors=((-206, KIDS[1] - 1, 3, 4, "x"),))
    w.kit_room((KIDS[0], G1 + 1, KIDS[1], KIDS[2], T.ROOF - 1, KIDS[3]), "kids_room", [(-206, G1 + 1, KIDS[1] - 1)],
               seed=31, style=C.ROMANTIC)
    shell(w, GYM, G1, h, floor=None, doors=((-193, GYM[1] - 1, 3, 4, "x"),))
    w.kit_room((GYM[0], G1 + 1, GYM[1], GYM[2], T.ROOF - 1, GYM[3]), "gym", [(-193, G1 + 1, GYM[1] - 1)], seed=32,
               style=C.ROMANTIC_W)
    shell(w, WEDDING, G1, h, floor=None, doors=((-178, WEDDING[3] + 1, 3, 4, "x"),))
    w.kit_room((WEDDING[0], G1 + 1, WEDDING[1], WEDDING[2], T.ROOF - 1, WEDDING[3]), "great_hall",
               [(-178, G1 + 1, WEDDING[3] + 1)], seed=33, style=C.ROMANTIC)
    # pasta (dugun salonunun basinda)
    w.set(WEDDING[0] + 2, G1 + 1, WEDDING[1] + 2, "white_concrete")
    w.set(WEDDING[0] + 2, G1 + 2, WEDDING[1] + 2, "cake[bites=0]")
    for box, door, seed in ((SHOP1, -182, 41), (SHOP2, -174, 42)):
        shell(w, box, G1, h, floor=None, doors=((door, box[1] - 1, 1, 3, "x"),))
        w.kit_room((box[0], G1 + 1, box[1], box[2], T.ROOF - 1, box[3]), "shop", [(door, G1 + 1, box[1] - 1)], seed=seed,
                   style=C.ROMANTIC)
    w.sign(-206, G1 + 5, KIDS[1] - 2, "north", ["ÇOCUK", "KULÜBÜ", "", ""], color="black")
    w.sign(-193, G1 + 5, GYM[1] - 2, "north", ["SPOR", "SALONU", "", ""], color="black")
    w.sign(-178, G1 + 5, WEDDING[3] + 2, "south", ["DÜĞÜN", "SALONU", "♥", ""], color="black")
    w.sign(-182, G1 + 4, SHOP1[1] - 2, "north", ["ÇİÇEKÇİ", "", "", ""], color="black")
    w.sign(-174, G1 + 4, SHOP2[1] - 2, "north", ["KUYUMCU", "", "", ""], color="black")
    # ust kat zemini (odalar disi): beyaz-pembe desen, galeri isiklari
    X, Z = w.XX, w.ZZ
    inner = T.geo(w, T.SP)["inner"] & ~w.podium_lobby
    rooms = rect_mask(w, (-213, -736, -170, -715)) | rect_mask(w, (-213, -679, -170, -658))
    fl = inner & ~rooms
    w.layer(G1, fl & ((X + Z) % 4 == 0), C.ROSE, only=[w.id(C.WHITE)])
    w.layer(T.ROOF, fl & (X % 5 == 0) & (Z % 5 == 0), FROG, only=[w.id(C.WHITE)])
    w.layer(G1, inner & ~rooms & (X % 6 == 3) & (Z % 6 == 3), FROG, only=[w.id(C.WHITE), w.id(C.ROSE)])


def podium_interiors(w: World):
    lobby(w)
    ballroom(w)
    cinema(w)
    restaurant(w)
    cafe(w)
    spa(w)
    upper_rooms(w)
