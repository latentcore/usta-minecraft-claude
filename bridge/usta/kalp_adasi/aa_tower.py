"""Ask Kulesi: kalp kesitli podyum (lobi, salonlar, cati havuzu) + 4 bolgeli kule (gokyuzu bahceleri, kanatli cephe,
isik cizgileri, beyazdan pembeye cam), cekirdek (merdiven kulesi + kabarcikli asansorler), tac (gokyuzu restorani,
seyir terasi) ve tepede isildayan dev kalp (icinde balayi suiti)."""
from __future__ import annotations

import math

import numpy as np

import aa_core as C
from aa_core import GY, World

TX, TZ = -200, C.AZ               # kule ve podyumun agirlik merkezi
CX, CZ = -205, C.AZ               # cekirdek merkezi
SP = 3.1                          # podyum kalp olcegi (99 x 90)
PFRONT = -242                     # podyumun kesik burnu (giris cephesi)
PFLOORS = (65, 76)                # podyum katlari: zemin (10 blok hava), ust kat (9 blok hava)
ROOF = 86                         # podyum cati dosemesi = kulenin ilk kati
ZONES = ((86, 8, 2.06), (136, 7, 1.89), (181, 6, 1.72), (221, 5, 1.55))
SKY = ((126, 2.06, 1.89), (171, 1.89, 1.72), (211, 1.72, 1.55))
CROWN, CROWN_S, DECK = 246, 1.64, 256
FH = 5
SHAFT = (CX - 5, CZ - 7, CX + 5, CZ - 1)          # merdiven kulesi dis kutusu (x0, z0, x1, z1)
TUBE_UP, TUBE_DN = (CX - 3, CZ + 3), (CX + 3, CZ + 3)
HEART_C = (-202, C.AZ)                             # tepe kalbin merkezi (x, z)
HEART_Y0, HEART_H, HEART_W, HEART_D = 263, 50, 56, 26
SUITE_Y = 276                                      # kalbin icindeki suitin dosemesi


def plate(w: World, s):
    px, pz = C.heart_poly(TX, TZ, s)
    return w.mask_poly(px, pz), (px, pz)


_GEO: dict = {}


def geo(w: World, s):
    """Bir kat plakasinin maskesi, cephe halkasi, dis halka ve yay parametreleri (onbellekli)."""
    if s in _GEO:
        return _GEO[s]
    P, poly = plate(w, s)
    if s == SP:
        P &= w.XX >= PFRONT
    ring = C.edge4(P)
    out = C.ring_out(P)
    oz, ox = np.nonzero(out)
    so, L = C.arc_param(poly[0], poly[1], ox + C.X0 + .5, oz + C.Z0 + .5)
    rz, rx = np.nonzero(ring)
    sr, _ = C.arc_param(poly[0], poly[1], rx + C.X0 + .5, rz + C.Z0 + .5)
    g = dict(P=P, poly=poly, ring=ring, out=out, oz=oz, ox=ox, so=so, rz=rz, rx=rx, sr=sr, L=L, inner=P & ~ring)
    _GEO[s] = g
    return g


def tower_floors():
    """[(y, tur, olcek, yukseklik)] -- tur: deck0 | hotel | sky | crown."""
    out = []
    for y0, n, s in ZONES:
        for k in range(n):
            y = y0 + FH * k
            out.append((y, "deck0" if y == ROOF else "hotel", s, FH))
    for y, so, si in SKY:
        out.append((y, "sky", so, 10))
    out.append((CROWN, "crown", CROWN_S, 10))
    return sorted(out)


def all_levels():
    """Merdivenin ugradigi tum doseme seviyeleri (asagidan yukari)."""
    lv = list(PFLOORS) + [f[0] for f in tower_floors()] + [DECK, SUITE_Y]
    return sorted(set(lv))


# ------------------------------------------------------------------ cephe yardimcilari
def glass_ids(w: World, g, y, mode, panel=3):
    """Halka hucreleri icin cam kimlikleri: gradient (yukseldikce beyazdan pembeye), clear, white."""
    n = len(g["rz"])
    if mode == "clear":
        return np.full(n, w.id(C.GLASS), np.uint16)
    if mode == "white":
        return np.full(n, w.id(C.WGLASS), np.uint16)
    t = (y - ROOF) / float(CROWN - ROOF)
    p = 0.06 + 0.86 * max(0.0, min(1.0, t)) ** 1.1
    pid = (g["sr"] // panel).astype(np.int64)
    # duzenli (Bayer 4x4) titresim: beyazdan pembeye puruzsuz ombre, rastgele benek yok
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32)
    thr = (bayer[(y // FH) % 4, pid % 4] + 0.5) / 16.0
    ids = np.where(thr < p, w.id(C.PGLASS), w.id(C.WGLASS)).astype(np.uint16)
    return ids


def put_ring(w: World, g, y, ids):
    if C.Y0 <= y <= C.Y1:
        w.G[y - C.Y0][g["rz"], g["rx"]] = ids


def fins(w: World, g, y0, y1, every=3, rod_every=4, state=C.QPILLAR, cap=None):
    """Dis halkada her `every` blokta dikey kanat; her rod_every'inci kanat gece isik cizgisi (end rod)."""
    s = g["so"]
    f = (s % every) < 1.0
    rod = f & ((s // every).astype(int) % rod_every == 0)
    fz, fx = g["oz"][f & ~rod], g["ox"][f & ~rod]
    rzz, rxx = g["oz"][rod], g["ox"][rod]
    a, b = w.id(state), w.id(C.ROD_UP)
    for y in range(max(y0, C.Y0), min(y1, C.Y1) + 1):
        w.G[y - C.Y0][fz, fx] = a
        w.G[y - C.Y0][rzz, rxx] = b
    if cap is not None and C.Y0 <= y1 + 1 <= C.Y1:
        w.G[y1 + 1 - C.Y0][fz, fx] = w.id(cap)


def mullions(w: World, g, y0, y1, every=4, state=C.GOLD):
    s = g["sr"]
    m = (s % every) < 1.0
    i = w.id(state)
    for y in range(y0, y1 + 1):
        w.G[y - C.Y0][g["rz"][m], g["rx"][m]] = i


# ------------------------------------------------------------------ podyum
def podium(w: World):
    g = geo(w, SP)
    P, ring, inner = g["P"], g["ring"], g["inner"]
    X, Z = w.XX, w.ZZ
    floor_i, slab_i = w.id("polished_diorite"), w.id(C.WHITE)
    # zemin kati (ada uzerinde), ara katlar, cati
    w.occ |= C.dilate(P, 2)
    w.layer(PFLOORS[0], inner, floor_i)
    w.layers(PFLOORS[0] - 3, PFLOORS[0] - 1, P, "stone")
    # bosluklar: lobi (3 kat), balo salonu ve sinema (2 kat)
    lobby = inner & (X <= CX - 9) & (np.abs(Z - CZ) <= 25)
    w.podium_lobby = lobby
    w.layer(PFLOORS[1], inner & ~lobby, slab_i)
    w.layer(ROOF, inner, slab_i)
    # galeri korkulugu (lobi boslugunun cevresi, ust katta)
    edge = C.ring_out(lobby) & inner & ~lobby
    w.layer(PFLOORS[1] + 1, edge, C.CPANE)
    # cephe: kusaklar + cam; giriste kapilar
    for y in range(PFLOORS[0], ROOF + 1):
        if y in (PFLOORS[0],):
            put_ring(w, g, y, np.full(len(g["rz"]), w.id(C.QUARTZ), np.uint16))
        elif y in PFLOORS[1:]:
            put_ring(w, g, y, np.full(len(g["rz"]), w.id(C.WHITE), np.uint16))
        elif y == ROOF:
            put_ring(w, g, y, np.full(len(g["rz"]), w.id(C.GOLD), np.uint16))
        else:
            put_ring(w, g, y, glass_ids(w, g, y, "white" if y > PFLOORS[1] else "clear"))
    fins(w, g, PFLOORS[0], ROOF + 1, every=4, rod_every=3, cap=C.GOLD)
    # parapet: dis halka uzerinde cam (sonsuzluk kenari)
    w.layer(ROOF + 1, ring, C.GLASS)
    # cati: kalp halkasi sonsuzluk havuzu (kulenin cevresinde, kenara paralel)
    Dp, _ = C.sdf(g["poly"][0], g["poly"][1], C.X0, C.Z0, w.nx, w.nz, margin=12.0)
    Dp = np.minimum(Dp, (X - PFRONT).astype(np.float32))
    tw = geo(w, ZONES[0][2])["P"]
    pool = (Dp > 1.5) & (Dp <= 5.5) & ~C.dilate(tw, 3) & P
    w.pool_ring = pool
    w.layer(ROOF, pool, "water")
    lamps = pool & (C.hash2(X // 5, Z // 5, 4) < 2) & ((X + Z) % 5 == 0)
    w.layer(ROOF - 1, pool, C.WHITE)
    w.layer(ROOF - 1, lamps, C.SEAL)
    w.layer(ROOF + 1, C.ring_out(pool) & P & ~ring, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    # giris acikliklari: on (bati) ana giris, kuzey/guney bahce kapilari, arka (dogu) koy kapisi
    w.box(PFRONT, 66, CZ - 4, PFRONT + 1, 70, CZ + 4, 1)
    for zc, face in ((CZ - 1, "north"), (CZ + 1, "south")):
        # yan kapilar: halkanin cekirdek hizasindaki en uc hucresi
        col = ring[:, CX - C.X0]
        zs = np.nonzero(col)[0]
        zz = (zs.min() if face == "north" else zs.max()) + C.Z0
        w.box(CX - 2, 66, zz - 1, CX + 2, 70, zz + 1, 1)
    back = ring & (X > TX) & (np.abs(Z - CZ) <= 3)
    bz, bx = np.nonzero(back)
    if len(bx):
        xb = int(bx.min()) + C.X0
        w.box(xb - 1, 66, CZ - 2, xb + 2, 70, CZ + 2, 1)
    # ana giris saçagi: altin altlik, isikli
    w.box(PFRONT - 9, 72, CZ - 9, PFRONT - 1, 72, CZ + 9, C.WHITE)
    w.box(PFRONT - 9, 71, CZ - 9, PFRONT - 1, 71, CZ + 9, 0)
    w.box(PFRONT - 10, 72, CZ - 10, PFRONT - 10, 73, CZ + 10, C.GOLD)
    for zz in range(CZ - 7, CZ + 8, 3):
        for xx in range(PFRONT - 8, PFRONT, 3):
            w.set(xx, 72, zz, C.FROG)
    for zz in (CZ - 9, CZ + 9):
        w.box(PFRONT - 9, 66, zz, PFRONT - 9, 71, zz, C.QPILLAR)
    return g


# ------------------------------------------------------------------ kule kabugu
def tower(w: World):
    floors = tower_floors()
    w.tower_floors = floors
    for y, kind, s, h in floors:
        g = geo(w, s)
        if kind in ("hotel", "deck0"):
            w.layer(y, g["inner"], C.WHITE)
            band = C.GOLD if any(y == z0 for z0, _, _ in ZONES) else C.QUARTZ
            put_ring(w, g, y, np.full(len(g["rz"]), w.id(band), np.uint16))
            for yy in range(y + 1, y + h):
                put_ring(w, g, yy, glass_ids(w, g, yy, "gradient"))
            fins(w, g, y, y + h - 1)
        elif kind == "sky":
            so = s
            si = next(si for yy, s0, si in SKY if yy == y)
            go, gi = geo(w, so), geo(w, si)
            w.layer(y, go["inner"], C.WHITE)
            put_ring(w, go, y, np.full(len(go["rz"]), w.id(C.GOLD), np.uint16))
            # teras korkulugu (2 blok cam panel) ve ic cam duvar (ince altin dikmeli)
            w.layer(y + 1, go["ring"], C.CPANE)
            w.layer(y + 2, go["ring"], C.CPANE)
            for yy in range(y + 1, y + h):
                put_ring(w, gi, yy, glass_ids(w, gi, yy, "clear"))
            mullions(w, gi, y + 1, y + h - 1, every=5)
            fins(w, go, y, y + h - 2, cap=C.GOLD)
            # teras zemini: pembe-beyaz desen
            terr = go["inner"] & ~gi["P"]
            pat = (C.hash2(w.XX, w.ZZ, 21) < 0.5)
            w.layer(y, terr & pat, C.ROSE)
            w.layer(y, terr & ~pat, C.CALCITE)
            w.sky_terrace = getattr(w, "sky_terrace", {})
            w.sky_terrace[y] = terr
        elif kind == "crown":
            g = geo(w, s)
            w.layer(y, g["inner"], C.WHITE)
            put_ring(w, g, y, np.full(len(g["rz"]), w.id(C.FROG), np.uint16))
            for yy in range(y + 1, y + h):
                put_ring(w, g, yy, glass_ids(w, g, yy, "clear"))
            mullions(w, g, y + 1, y + h - 1, every=4)
            # seyir terasi: cati dosemesi, altin halka, kornis, cam korkuluk
            w.layer(DECK, g["P"], C.WHITE)
            put_ring(w, g, DECK, np.full(len(g["rz"]), w.id(C.GOLD), np.uint16))
            w.layer(DECK, g["out"], C.QUARTZ)
            w.layer(DECK - 1, g["out"], "smooth_quartz_stairs[facing=north,half=top,shape=straight,waterlogged=false]")
            w.layer(DECK + 1, g["ring"], C.CPANE)
            w.layer(DECK + 2, g["ring"], C.CPANE)
            deck = g["inner"]
            pat = ((w.XX + w.ZZ) % 6 == 0) | ((w.XX - w.ZZ) % 6 == 0)
            w.layer(DECK, deck & pat, C.ROSE)
            w.layer(DECK, deck & ~pat, C.QUARTZ)
    # kule cekirdeginin podyumdan cati dosemesine gecisi: podyum katlarinda kule plakasi alani bos kalir (lobi)
    return floors


# ------------------------------------------------------------------ cekirdek: merdiven kulesi + kabarcikli asansorler
def stair_core(w: World, levels, top_extra=4):
    x0, z0, x1, z1 = SHAFT
    sx0, sx1 = x0 + 1, x1 - 1                      # ic x (9)
    za, zdiv, zb = (z0 + 1, z0 + 2), z0 + 3, (z0 + 4, z0 + 5)
    ybot, ytop = levels[0], levels[-1]
    wall = C.WHITE
    w.box(x0, ybot, z0, x1, ytop + top_extra, z1, wall)
    w.box(sx0, ybot + 1, z0 + 1, sx1, ytop + top_extra - 1, z1 - 1, 1)
    w.box(x0, ytop + top_extra, z0, x1, ytop + top_extra, z1, C.WHITE)
    # bolme duvari (seritlerin arasi)
    w.box(sx0 + 2, ybot, zdiv, sx1 - 2, ytop + top_extra - 1, zdiv, C.QUARTZ)
    step = "smooth_quartz_stairs[facing=%s,half=bottom,shape=straight,waterlogged=false]"
    lamp = C.SEAL
    y = ybot
    end = "W"
    exits = []

    def landing(yL, e):
        xa, xb = (sx0, sx0 + 1) if e == "W" else (sx1 - 1, sx1)
        w.box(xa, yL, z0 + 1, xb, yL, z1 - 1, "polished_diorite")
        w.box(xa, yL + 1, z0 + 1, xb, yL + 3, z1 - 1, 1)
        w.set(xa if e == "W" else xb, yL + 4, z0 + 3, lamp) if yL + 4 < ytop + top_extra else None

    landing(y, end)
    for ya, yb in zip(levels[:-1], levels[1:]):
        R = yb - ya
        nfl = int(math.ceil(R / 6.0))
        parts = [R // nfl + (1 if i < R % nfl else 0) for i in range(nfl)]
        for r in parts:
            if end == "W":
                lz = za
                for k in range(1, r):
                    xk = sx1 - r + k - 1
                    w.box(xk, y + k, lz[0], xk, y + k, lz[1], step % "east")
                    w.box(xk, y + k - 1, lz[0], xk, y + k - 1, lz[1], C.QUARTZ)
                    w.box(xk, y + k + 1, lz[0], xk, y + k + 3, lz[1], 1)
                for xk in range(sx0 + 2, sx1 - r + 1):           # sahanlik uzantisi
                    w.box(xk, y, lz[0], xk, y, lz[1], "polished_diorite")
                end = "E"
            else:
                lz = zb
                for k in range(1, r):
                    xk = sx0 + r - k + 1
                    w.box(xk, y + k, lz[0], xk, y + k, lz[1], step % "west")
                    w.box(xk, y + k - 1, lz[0], xk, y + k - 1, lz[1], C.QUARTZ)
                    w.box(xk, y + k + 1, lz[0], xk, y + k + 3, lz[1], 1)
                for xk in range(sx0 + r, sx1 - 1):
                    w.box(xk, y, lz[0], xk, y, lz[1], "polished_diorite")
                end = "W"
            y += r
            landing(y, end)
        exits.append((yb, end))
    # kat cikislari: sahanligin guney duvarinda 2 genis, 3 yuksek aciklik + kat tabelasi
    names = {65: "LOBİ", 76: "1. KAT", 86: "HAVUZ", CROWN: "RESTORAN", DECK: "TERAS", SUITE_Y: "KALP SÜİT"}
    for i, (ys, _, _) in enumerate(SKY):
        names[ys] = f"BAHÇE {i + 1}"
    fl = {y: i for i, y in enumerate(sorted(f[0] for f in tower_floors()))}
    out = [(ybot, "W")] + exits
    for yL, e in out:
        xa = sx0 if e == "W" else sx1 - 1
        w.box(xa, yL + 1, z1, xa + 1, yL + 3, z1, 1)
        w.box(xa, yL, z1, xa + 1, yL, z1, "polished_diorite")
        lab = names.get(yL)
        if lab is None:
            lab = f"KAT {fl.get(yL, 0) + 2}"
        sxp = xa + 2 if e == "W" else xa - 1
        w.sign(sxp, yL + 2, z1 + 1, "south", ["MERDİVEN", lab, "", ""], color="black")
    w.stair_exits = out
    return out


def elevators(w: World, ybot=65, ytop=CROWN):
    """Iki kabarcikli asansor: yukari (ruh kumu) ve asagi (magma). Alt kapi guneyde, ust cikis guneyde."""
    for (cx, cz), up in ((TUBE_UP, True), (TUBE_DN, False)):
        w.box(cx - 1, ybot, cz - 1, cx + 1, ytop + 3, cz + 1, C.GLASS)
        w.box(cx - 1, ytop + 4, cz - 1, cx + 1, ytop + 4, cz + 1, C.GOLD)
        w.set(cx, ybot, cz, "soul_sand" if up else "magma_block")
        col = "bubble_column[drag=false]" if up else "bubble_column[drag=true]"
        w.box(cx, ybot + 1, cz, cx, ytop, cz, col)
        w.box(cx, ytop + 1, cz, cx, ytop + 3, cz, 1)
        # alt: kapi (su tutar), ust: guneye acik cikis
        w.set(cx, ybot + 1, cz + 1, "cherry_door[facing=south,half=lower,hinge=left,open=false,powered=false]")
        w.set(cx, ybot + 2, cz + 1, "cherry_door[facing=south,half=upper,hinge=left,open=false,powered=false]")
        w.box(cx, ytop + 1, cz + 1, cx, ytop + 3, cz + 1, 1)
        # isik: tup koselerinde altin + kurbaga isigi seritleri
        for (dx, dz) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            for y in range(ybot + 2, ytop + 1, 10):
                w.set(cx + dx, y, cz + dz, C.FROG)
        lab = ["ASANSÖR", "YUKARI ▲", "RESTORAN", "TERAS"] if up else ["ASANSÖR", "AŞAĞI ▼", "LOBİ", ""]
        w.sign(cx + (1 if up else -1), ybot + 3, cz + 2, "south", lab, color="black")
        w.sign(cx + (1 if up else -1), ytop + 3, cz + 2, "south",
               ["ASANSÖR", "AŞAĞI ▼", "LOBİ", ""] if not up else ["ÇIKIŞ", "GÖKYÜZÜ", "RESTORANI", ""], color="black")


# ------------------------------------------------------------------ tepe kalp
def heart(w: World):
    xc, zc = HEART_C
    y0, H, Wd, Dp = HEART_Y0, HEART_H, HEART_W, HEART_D
    # kalbin normlu sinirlari
    zs = np.linspace(-1.2, 1.4, 400)
    Xs = np.linspace(-1.3, 1.3, 400)
    ZZg, XXg = np.meshgrid(zs, Xs)
    inside = C.heart3d(XXg, 0.0, ZZg)
    zmin, zmax = float(ZZg[inside].min()), float(ZZg[inside].max())
    xmax = float(np.abs(XXg[inside]).max())
    a = (Wd / 2.0) / xmax
    b = H / (zmax - zmin)
    c = (Dp / 2.0) / 0.667
    xs = np.arange(int(xc - Dp // 2 - 2), int(xc + Dp // 2 + 3))
    ys = np.arange(y0 - 1, y0 + H + 2)
    zz = np.arange(int(zc - Wd // 2 - 2), int(zc + Wd // 2 + 3))
    Yg, Zg, Xg = np.meshgrid(ys, zz, xs, indexing="ij")
    U = (Zg + 0.5 - zc - 0.5) / a
    V = (Xg + 0.5 - xc - 0.5) / c
    Wn = (Yg + 0.5 - y0) / b + zmin
    S = C.heart3d(U, V, Wn)
    # kabuk: 6-komsuluktan biri disarida
    pad = np.pad(S, 1)
    interior = pad[1:-1, 1:-1, 1:-1] & pad[2:, 1:-1, 1:-1] & pad[:-2, 1:-1, 1:-1] & pad[1:-1, 2:, 1:-1] & \
        pad[1:-1, :-2, 1:-1] & pad[1:-1, 1:-1, 2:] & pad[1:-1, 1:-1, :-2]
    shell = S & ~interior
    # kapitone desen: pembe paneller, aralarda gece altin gibi isildayan kafes (ochre froglight)
    lattice = (((Yg - Zg) % 7) == 0) | (((Yg + Zg) % 7) == 0)
    front = Xg <= xc + 1
    win = (~front) & (Yg >= SUITE_Y + 1) & (Yg <= SUITE_Y + 5) & ~lattice
    sparkle = shell & ~lattice & (C.SH.hash01(Xg, Yg, Zg, 31) < 0.10)
    ids = np.zeros(S.shape, np.uint16)
    ids[shell] = w.id(C.PINK)
    ids[sparkle] = w.id(C.FROG)
    ids[shell & lattice] = w.id(C.OCHRE)
    ids[shell & win] = w.id(C.PGLASS)
    ids[interior] = 1
    # suit dosemesi ve ust asma kat (kalbin icinde)
    for yy, st in ((SUITE_Y, "white_concrete"), (SUITE_Y + 12, "white_concrete")):
        k = yy - (y0 - 1)
        if 0 <= k < S.shape[0]:
            layer = interior[k] & (C.erode(interior[k], 1, square=True) if yy == SUITE_Y else interior[k])
            if yy != SUITE_Y:
                # asma kat: on yarida (seyir galerisi), arkada bosluk
                layer = interior[k] & (Xg[k] <= xc - 2)
            ids[k][layer] = w.id(st)
    v = w.view(int(xs[0]), int(ys[0]), int(zz[0]), int(xs[-1]), int(ys[-1]), int(zz[-1]))
    m = ids != 0
    v[m] = ids[m]
    w.heart_box = (int(xs[0]), int(ys[0]), int(zz[0]), int(xs[-1]), int(ys[-1]), int(zz[-1]))
    w.heart_interior = (interior, ys, zz, xs)
    return w.heart_box


def pedestal(w: World):
    """Teras ustunden kalbin alt ucuna incelen altin-kuvars kaide (merdiven kulesini sarar; guney kapisi acik)."""
    x0, z0, x1, z1 = SHAFT
    door_x = (x0 + 1, x0 + 2)
    for y in range(DECK + 1, HEART_Y0 + 9):
        t = (y - DECK) / float(HEART_Y0 + 9 - DECK)
        r = 1 + int(round(2.4 * (1 - t)))
        st = C.GOLD if (y - DECK) % 5 else C.FROG
        v = w.view(x0 - r, y, z0 - r, x1 + r, y, z1 + r)
        m = np.ones(v.shape, bool)
        m[:, r:r + (z1 - z0 + 1), r:r + (x1 - x0 + 1)] = False      # merdiven kulesinin kendisi
        if y <= DECK + 4:
            m[:, r + (z1 - z0 + 1):, door_x[0] - (x0 - r):door_x[1] - (x0 - r) + 1] = False   # kapi koridoru
        v[m & (v == 0)] = w.id(st)
