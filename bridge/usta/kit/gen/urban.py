"""Kent ureteçleri: skyscraper (futuristik cam gokdelen + meydan), plaza (kent meydani), park (cicekli park),
apartment (apartman), city_block (yollarla sehir blogu, 200x200'e kadar). Yerel cerceve: on z=0 (-z'ye bakar), y=0 zemin."""
from __future__ import annotations

import math

import numpy as np

from . import register
from .. import shapes as SH
from .common import (I, P, S, T, Build, clear_volume, finish_meta, furnish_rooms, get_style, ground_of, light_shaft,
                     partition_walls, perimeter_lamps, random, room_windows, scale_of, settle_on_ground, split_rooms,
                     stair_access, stair_keep)


# ------------------------------------------------------------------ meydan yardimcisi
def plaza_area(b, x0: int, z0: int, x1: int, z1: int, st, seed: int = 0, keep_out=None, entrance_x: int | None = None,
               pools: bool = True, trees: bool = True):
    """Meydan zemini ve donati: desenli tas doseme (cerceve + seritler), eksende giris yolu, iki yansima havuzu,
    agac saksilari, banklar, modern lambalar, bayrak direkleri. keep_out: (x0,z0,x1,z1) bina izi (dokunulmaz)."""
    rnd = random.Random(seed)
    ko = keep_out or (0, 0, -1, -1)

    def free(x, z, pad=1):
        return not (ko[0] - pad <= x <= ko[2] + pad and ko[1] - pad <= z <= ko[3] + pad)
    cx = entrance_x if entrance_x is not None else (x0 + x1) // 2
    pave = st.block("paving")
    acc = st.block("tile")
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if not free(x, z, 0):
                continue
            edge = x in (x0, x1) or z in (z0, z1)
            band = (x - x0) % 8 == 0 or (z - z0) % 8 == 0
            b.set(x, 0, z, st.block("frame") if edge else (acc if band and not (cx - 2 <= x <= cx + 2) else pave))
    # giris aksi: binaya kadar acik renk yol
    zf = ko[1] - 2 if ko[3] >= ko[1] else z1
    for z in range(z0, max(z0, zf) + 1):
        for x in range(cx - 2, cx + 3):
            b.set(x, 0, z, st.block("trim"))
    if pools and zf - z0 >= 14:
        pz0, pz1 = z0 + 4, min(zf - 4, z0 + 4 + (zf - z0) // 2)
        for (px0, px1) in ((cx - 4 - max(5, (cx - x0) // 2), cx - 5), (cx + 5, cx + 4 + max(5, (x1 - cx) // 2))):
            px0, px1 = max(x0 + 3, px0), min(x1 - 3, px1)
            if px1 - px0 >= 4 and pz1 - pz0 >= 4:
                P.pool(b, px0, 0, pz0, px1, pz1, st, depth=1, lights=True, steps=False)
    if trees:
        for x in list(range(x0 + 3, x1 - 2, 7)):
            for z in (z0 + 2, z1 - 2):
                if free(x, z, 2) and not (cx - 3 <= x <= cx + 3):
                    P.planter(b, x, 1, z, st, kind="tree", seed=rnd.randint(0, 999))
        for z in list(range(z0 + 9, z1 - 2, 7)):
            for x in (x0 + 2, x1 - 2):
                if free(x, z, 2):
                    P.planter(b, x, 1, z, st, kind="tree", seed=rnd.randint(0, 999))
    for x in range(x0 + 6, x1 - 4, 9):
        for z in (z0 + 5, z1 - 5):
            if free(x, z, 2) and not (cx - 3 <= x <= cx + 3):
                P.lamp_post(b, x, 1, z, st, h=4, kind="modern")
    for z in range(z0 + 6, z1 - 4, 9):
        for x in (x0 + 5, x1 - 5):
            if free(x, z, 2):
                P.lamp_post(b, x, 1, z, st, h=4, kind="modern")
    for z in range(z0 + 3, zf - 2, 6):
        for x in (cx - 4, cx + 4):
            if free(x, z, 1):
                P.bench(b, x, 1, z, "east" if x < cx else "west", st, length=2)
    for dx in (-6, 6):
        if free(cx + dx, z0 + 1, 1):
            P.flagpole(b, cx + dx, 1, z0 + 1, st, h=8, color="light_blue" if dx < 0 else "white")


# ------------------------------------------------------------------ gokdelen
def skyscraper_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    W = int(params.get("width") or max(13, round(17 * s)))
    W += 1 - W % 2
    m = int(params.get("plaza") or max(10, round(14 * s)))
    return W + 2 * m + 8, W + 2 * m + 8


def _tier_mask(W: int, cham: int) -> np.ndarray:
    """W x W kare, koseleri `cham` blok pahli (45 derece) — futuristik silüet."""
    m = np.ones((W, W), bool)
    for i in range(cham):
        for j in range(cham - i):
            for (a, c) in ((i, j), (i, W - 1 - j), (W - 1 - i, j), (W - 1 - i, W - 1 - j)):
                m[a, c] = False
    return m


def _outline(mask: np.ndarray) -> np.ndarray:
    pad = np.pad(mask, 1)
    inner = pad[1:-1, 1:-1] & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    return mask & ~inner


def skyscraper(params: dict, ctx: dict | None = None) -> Build:
    """Futuristik cam gokdelen: genis podyum (lobi), pahli kademeli kat kuleleri, beyaz dikey kanatlar, mavi cam
    giydirme cephe, 4 katta bir isik kusagi, ortada doner merdivenli cekirdek, her katta tavan isiklari ve doseme,
    tepede helikopter pisti + anten; cevresinde desenli meydan, yansima havuzlari, agaclar, banklar, lambalar."""
    st = get_style(params, ctx, "futuristic")
    s = scale_of(params, 1.0)
    FW, FD = skyscraper_dims(params)
    W = FW - 8 - 2 * max(10, round(14 * s)) if not params.get("plaza") else FW - 8 - 2 * int(params["plaza"])
    W = max(11, W)
    floors = int(params.get("floors") or max(12, round(22 * s)))
    fh = 5
    seed = int(params.get("seed", 17))
    b = Build(params.get("name") or "gökdelen")
    g = ground_of(ctx, FW, FD)
    cxw, czw = FW // 2, FD // 2
    x0, z0 = cxw - W // 2, czw - W // 2
    H = floors * fh
    clear_volume(b, 0, 1, 0, FW - 1, min(H + 20, 380), FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=5)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    glass = "light_blue_stained_glass"
    fin = st.block("pillar")
    band = st.block("light_block")
    slab_mat = st.block("floor")
    edge_mat = st.block("frame")
    # kademeler: (baslangic kat, genislik, pah)
    tiers = [(0, W + 6, 3), (3, W, 3), (int(floors * 0.62), W - 4, 2), (int(floors * 0.86), W - 8, 2)]
    tiers = [t for t in tiers if t[1] >= 7]
    tiers.append((floors, 0, 0))
    core_r = 2
    plates = []
    ceil_lights = []
    for ti in range(len(tiers) - 1):
        f0, w_, ch = tiers[ti]
        f1 = tiers[ti + 1][0]
        if f1 <= f0:
            continue
        mask = _tier_mask(w_, ch)
        ol = _outline(mask)
        ox, oz = cxw - w_ // 2, czw - w_ // 2
        ys, xs = np.nonzero(ol)
        ring = list(zip(xs.tolist(), ys.tolist()))
        for f in range(f0, f1):
            fy = f * fh
            # doseme + cevre kusagi
            for (j, i) in zip(*np.nonzero(mask.T)):
                X, Z = ox + int(j), oz + int(i)
                if abs(X - cxw) <= core_r and abs(Z - czw) <= core_r:
                    continue
                b.set(X, fy, Z, slab_mat if fy > 0 else st.block("floor_alt"))
            for (j, i) in ring:
                X, Z = ox + j, oz + i
                b.set(X, fy, Z, band if (f % 4 == 3) else edge_mat)
                isfin = ((j + i) % 4 == 0) or (j in (0, w_ - 1) and i in (0, w_ - 1))
                for y in range(fy + 1, fy + fh):
                    b.set(X, y, Z, fin if isfin else glass)
                if isfin:                 # dikey kanat cepheden 1 blok tasar (derinlik, golge)
                    for (ddx, ddz) in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        jj, ii = j + ddx, i + ddz
                        if not (0 <= jj < w_ and 0 <= ii < w_) or not mask[ii, jj]:
                            b.fill(X + ddx, fy, Z + ddz, X + ddx, fy + fh - 1, Z + ddz, fin)
                            break
            # tavan isiklari (bir ustteki dosemeye gomulu; kademe gecisinde doseme ezmesin diye en sonda konur)
            for (X, Z) in ((cxw - core_r - 1, czw - core_r - 1), (cxw + core_r + 1, czw - core_r - 1),
                           (cxw - core_r - 1, czw + core_r + 1), (cxw + core_r + 1, czw + core_r + 1)):
                ceil_lights.append((X, fy + fh, Z))
            for X in range(ox + 2, ox + w_ - 2, 4):
                for Z in range(oz + 2, oz + w_ - 2, 4):
                    if mask[Z - oz, X - ox] and not (abs(X - cxw) <= core_r + 1 and abs(Z - czw) <= core_r + 1):
                        ceil_lights.append((X, fy + fh, Z))
            plates.append((f, fy, ox, oz, w_, mask))
        # kademe cati terasi (ust kademe daha dar): cam korkuluk + yesillik
        top_y = f1 * fh
        nxt = tiers[ti + 1]
        if nxt[1] > 0:
            nm = np.zeros_like(mask)
            nox, noz = cxw - nxt[1] // 2, czw - nxt[1] // 2
            sub = _tier_mask(nxt[1], nxt[2])
            nm[noz - oz: noz - oz + nxt[1], nox - ox: nox - ox + nxt[1]] = sub
            for (j, i) in zip(*np.nonzero(mask.T)):
                X, Z = ox + int(j), oz + int(i)
                if not nm[int(i), int(j)]:
                    b.set(X, top_y, Z, slab_mat)
            for (j, i) in ring:
                b.set(ox + j, top_y + 1, oz + i, st.pane("railing"))
            for k, (j, i) in enumerate(ring):
                if k % 5 == 0 and not nm[min(max(i, 0), w_ - 1), min(max(j, 0), w_ - 1)]:
                    X, Z = ox + j, oz + i
                    dx = 1 if j == 0 else -1 if j == w_ - 1 else 0
                    dz = 1 if i == 0 else -1 if i == w_ - 1 else 0
                    if dx or dz:
                        P.planter(b, X + dx, top_y + 1, Z + dz, st, kind="box", seed=seed + k)
    for (X, Y, Z) in ceil_lights:
        if b.is_solid(X, Y, Z):
            b.set(X, Y, Z, band)
    # en ust: cati dosemesi + helikopter pisti + anten
    f0, w_, ch = tiers[-2]
    mask = _tier_mask(w_, ch)
    ox, oz = cxw - w_ // 2, czw - w_ // 2
    top = H
    for (j, i) in zip(*np.nonzero(mask.T)):
        b.set(ox + int(j), top, oz + int(i), slab_mat)
    for (j, i) in zip(*np.nonzero(_outline(mask).T)):
        b.set(ox + int(j), top + 1, oz + int(i), st.pane("railing"))
    pr = min(4, w_ // 2 - 2)
    for X in range(cxw - pr, cxw + pr + 1):
        for Z in range(czw - pr, czw + pr + 1):
            b.set(X, top + 1, Z, "gray_concrete" if max(abs(X - cxw), abs(Z - czw)) < pr else "yellow_concrete")
    for dz in range(-2, 3):                       # "H"
        b.set(cxw - 1, top + 1, czw + dz, "white_concrete")
        b.set(cxw + 1, top + 1, czw + dz, "white_concrete")
    b.set(cxw, top + 1, czw, "white_concrete")
    for (X, Z) in ((cxw - pr, czw - pr), (cxw + pr, czw - pr), (cxw - pr, czw + pr), (cxw + pr, czw + pr)):
        b.set(X, top + 2, Z, "end_rod[facing=up]")
    ax, az = ox + 1 + (1 if mask[1, 1] else 3), oz + w_ // 2
    b.fill(ax, top + 1, az, ax, top + 12, az, "iron_bars")
    b.set(ax, top + 13, az, "lightning_rod[facing=up]")
    # cekirdek: doner merdiven (her kattan erisilir), cekirdek ici isik
    P.spiral_stair(b, cxw, 1, czw, H, st, r=core_r, role="trim", newel_role="accent", clear=True)
    for f in range(floors + 1):
        fy = f * fh
        for X in range(cxw - core_r, cxw + core_r + 1):
            for Z in range(czw - core_r, czw + core_r + 1):
                if max(abs(X - cxw), abs(Z - czw)) == core_r and b.get_id(X, fy, Z) <= 1 and \
                        not str(b.get(X, fy - 1, Z)).split("[")[0].endswith("_stairs"):
                    pass
    light_shaft(b, cxw, czw, 2, H - 2, r=core_r + 1, every=5, level=12)
    # giris: podyum on cephesi ortasinda cam kapi + kanopi
    pw = tiers[0][1]
    pox, poz = cxw - pw // 2, czw - pw // 2
    dx0 = cxw - 1
    P.door(b, dx0, 1, poz, "north", st, w=2, kind="modern")
    for X in range(dx0 - 3, dx0 + 5):
        for Z in (poz - 1, poz - 2, poz - 3):
            b.set(X, 4, Z, st.slab("trim", "top"))
    for X in (dx0 - 3, dx0 + 4):
        b.fill(X, 1, poz - 3, X, 3, poz - 3, st.block("pillar"))
    # ic: katlari dose (on ve arka serit), lobi + kafe, ofisler, en ust katta salon
    rooms_all, doors = [], [(dx0, 1, poz), (dx0 + 1, 1, poz)]
    cycle = [("home_office", "lab"), ("control_room", "library"), ("home_office", "cafe"), ("lab", "home_office")]
    for (f, fy, ox, oz, w_, mask) in plates:
        if f % 2 and f not in (floors - 1,) and f > 2:
            kinds = None if f % 4 == 1 else cycle[(f // 2) % len(cycle)]
        else:
            kinds = ("foyer", "cafe") if f == 0 else ("living_room", "dining_room") if f == floors - 1 else cycle[f % len(cycle)]
        if not kinds:
            continue
        inset = 2
        bx0, bx1 = ox + inset, ox + w_ - 1 - inset
        front = (bx0, fy + 1, oz + inset, bx1, fy + fh - 1, czw - core_r - 2)
        back = (bx0, fy + 1, czw + core_r + 2, bx1, fy + fh - 1, oz + w_ - 1 - inset)
        for k, box in zip(kinds, (front, back)):
            if box[5] - box[2] >= 2 and box[3] - box[0] >= 3:
                rooms_all.append((k, box))
    keep = [(dx0, 1, poz + 1), (dx0 + 1, 1, poz + 1), (dx0, 1, poz + 2), (dx0 + 1, 1, poz + 2)]
    for X in range(cxw - core_r - 1, cxw + core_r + 2):
        for Z in range(czw - core_r - 1, czw + core_r + 2):
            if max(abs(X - cxw), abs(Z - czw)) == core_r + 1:
                for f in range(floors):
                    keep += [(X, f * fh + 1, Z), (X, f * fh + 2, Z)]
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    # meydan
    m = (FW - pw) // 2
    plaza_area(b, 1, 1, FW - 2, FD - 2, st, seed=seed, keep_out=(pox, poz, pox + pw - 1, poz + pw - 1), entrance_x=cxw)
    return finish_meta(b, "skyscraper", st, {"floors": [f * fh for f in range(floors)], "height": H + 13,
                                             "door": [dx0, 1, poz], "tiers": [list(t) for t in tiers]})


# ------------------------------------------------------------------ meydan (tek basina)
def plaza_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    n = int(params.get("width") or max(25, round(35 * s)))
    return n, int(params.get("depth") or n)


def plaza(params: dict, ctx: dict | None = None) -> Build:
    """Kent meydani: desenli doseme, merkezde cesme (ya da sadirvan), yansima havuzlari, agac saksilari, banklar,
    lambalar, bayrak direkleri."""
    st = get_style(params, ctx, params.get("style") or "classical")
    FW, FD = plaza_dims(params)
    b = Build(params.get("name") or "meydan")
    g = ground_of(ctx, FW, FD)
    seed = int(params.get("seed", 13))
    clear_volume(b, 0, 1, 0, FW - 1, 12, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=4)
    plaza_area(b, 0, 0, FW - 1, FD - 1, st, seed=seed, pools=False)
    cx, cz = FW // 2, FD // 2
    kind = "sadirvan" if st.name.split("@")[0] == "ottoman" else "simple"
    P.fountain(b, cx, 0, cz, st, kind=kind, r=3 if min(FW, FD) >= 25 else 2)
    for dx, dz in ((-6, 0), (6, 0), (0, -6), (0, 6)):
        P.bench(b, cx + dx, 1, cz + dz - (1 if dx else 0), "east" if dx < 0 else "west" if dx > 0 else "south" if dz < 0 else "north",
                st, length=3) if (dx or dz) else None
    return finish_meta(b, "plaza", st, {"floors": [0]})


# ------------------------------------------------------------------ park
def park_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    n = int(params.get("width") or max(31, round(41 * s)))
    return n, int(params.get("depth") or n)


def park(params: dict, ctx: dict | None = None) -> Build:
    """Cicekli park: araziyi duzler (kazi/dolgu + dogal kenar), kivrimli yollar, bol cicek tarhlari, gol (nilufer),
    cardak, cesme, agaclar, citler, banklar, fenerler."""
    st = get_style(params, ctx, params.get("style") or "classical")
    FW, FD = park_dims(params)
    b = Build(params.get("name") or "çiçekli park")
    g = ground_of(ctx, FW, FD)
    seed = int(params.get("seed", 23))
    rnd = random.Random(seed)
    clear_volume(b, 0, 1, 0, FW - 1, 14, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=6)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    cx, cz = FW // 2, FD // 2
    # yollar: girisden merkeze kivrimli, merkez meydancik, capraz kollar
    pts_main = [(cx, 0), (cx - 3, FD // 4), (cx + 2, cz - 5), (cx, cz - 3)]
    P.path(b, pts_main, 0, st, w=3, border=True, curve=True)
    P.path(b, [(cx - 3, cz + 3), (cx - FW // 4, cz + FD // 4), (3, FD - 4)], 0, st, w=2, border=False, curve=True)
    P.path(b, [(cx + 3, cz + 3), (cx + FW // 4, cz + FD // 4 - 2), (FW - 4, FD - 6)], 0, st, w=2, border=False, curve=True)
    for x in range(cx - 4, cx + 5):
        for z in range(cz - 4, cz + 5):
            if (x - cx) ** 2 + (z - cz) ** 2 <= 20:
                st.set(b, x, 0, z, "paving")
    P.fountain(b, cx, 0, cz, st, kind="simple", r=2)
    # gol: sol arka
    lx, lz, lr = cx - FW // 4 - 1, cz - FD // 5, max(4, FW // 9)
    for x in range(lx - lr - 1, lx + lr + 2):
        for z in range(lz - lr, lz + lr + 1):
            d = ((x - lx) / (lr + 0.5)) ** 2 + ((z - lz) / (lr * 0.75 + 0.5)) ** 2
            if d <= 1.0:
                b.set(x, 0, z, "water")
                b.set(x, -1, z, "water" if d < 0.55 else "clay")
                b.set(x, -2, z, "clay" if d < 0.55 else "dirt")
                if d < 0.55 and rnd.random() < 0.1:
                    b.set(x, 1, z, "lily_pad")
            elif d <= 1.35 and b.get_id(x, 0, z) <= 1 or (d <= 1.35 and str(b.get(x, 0, z)).endswith("grass_block")):
                b.set(x, 0, z, "mud" if rnd.random() < 0.3 else "grass_block")
                if rnd.random() < 0.3:
                    b.set(x, 1, z, rnd.choice(["short_grass", "fern", "blue_orchid", "tall_grass[half=lower]"]))
                    if str(b.get(x, 1, z)).startswith("minecraft:tall_grass"):
                        b.set(x, 2, z, "tall_grass[half=upper]")
    # cardak (pergola) sag arka, banklarla
    px0, pz0 = cx + FW // 6, cz - FD // 4 - 2
    P.pergola(b, px0, 1, pz0, px0 + 6, pz0 + 4, st, h=3, greenery=True, seed=seed)
    st.fill(b, px0, 0, pz0, px0 + 6, 0, pz0 + 4, "paving")
    P.bench(b, px0 + 1, 1, pz0 + 1, "south", st, length=3)
    P.bench(b, px0 + 5, 1, pz0 + 3, "north", st, length=3)
    # cicek tarhlari: yollarin arasindaki bos cimende
    beds = 0
    for (bx, bz) in [(cx - FW // 3, cz + 2), (cx + FW // 3 - 4, cz + 1), (cx - 5, cz + FD // 3), (cx + 2, cz + FD // 3),
                     (cx - FW // 3 + 1, 4), (cx + FW // 4, 4), (cx - 8, cz - 2), (cx + 5, cz - 2)]:
        x0_, z0_ = bx, bz
        x1_, z1_ = bx + 4, bz + 3
        if 1 <= x0_ and x1_ <= FW - 2 and 1 <= z0_ and z1_ <= FD - 2:
            if all(str(b.get(x, 0, z)).split("[")[0].endswith("grass_block") for x in range(x0_, x1_ + 1) for z in range(z0_, z1_ + 1)):
                P.garden_bed(b, x0_, 0, z0_, x1_, z1_, st, raised=bool(beds % 2), density=0.9, seed=seed + beds)
                beds += 1
    # citler ve agaclar kenarda
    P.hedge(b, 0, 1, 0, cx - 3, 0, st, h=1)
    P.hedge(b, cx + 3, 1, 0, FW - 1, 0, st, h=1)
    for (tx, tz, sp) in ((3, 3, "oak"), (FW - 4, 3, "birch"), (3, FD - 8, "cherry"), (FW - 4, FD - 4, "oak"),
                         (cx + FW // 3, cz + 3, "cherry"), (cx - FW // 3 - 3, cz - 4, "birch")):
        if 2 <= tx <= FW - 3 and 2 <= tz <= FD - 3 and b.get_id(tx, 1, tz) <= 1:
            try:
                T.tree(b, tx, 0, tz, species=sp, size="medium", seed=rnd.randint(0, 9999))
            except Exception:
                pass
    for (x, z) in ((cx - 3, 6), (cx + 3, 6), (cx - 6, cz), (cx + 6, cz), (cx, cz + 6), (FW // 4, FD - 6), (3 * FW // 4, FD - 6)):
        if b.get_id(x, 1, z) <= 1:
            P.lamp_post(b, x, 1, z, st, h=4)
    for (x, z, f) in ((cx - 5, cz - 2, "east"), (cx + 5, cz + 2, "west"), (cx - 2, cz + 5, "north")):
        if b.get_id(x, 1, z) <= 1:
            P.bench(b, x, 1, z, f, st, length=2)
    # cimene serpili cicekler (yogun "cicekli park")
    flowers = ["poppy", "dandelion", "cornflower", "oxeye_daisy", "allium", "azure_bluet", "red_tulip", "orange_tulip",
               "pink_tulip", "white_tulip", "lily_of_the_valley"]
    for x in range(1, FW - 1):
        for z in range(1, FD - 1):
            if str(b.get(x, 0, z)).split("[")[0].endswith(("grass_block", "podzol", "dirt")) and b.get_id(x, 1, z) <= 1 and rnd.random() < 0.3:
                r_ = rnd.random()
                if r_ < 0.15 and b.get_id(x, 2, z) <= 1:          # uzun cicekler (uzaktan gorunur renk)
                    tall = rnd.choice(["rose_bush", "lilac", "peony", "sunflower"])
                    b.set(x, 1, z, f"{tall}[half=lower]")
                    b.set(x, 2, z, f"{tall}[half=upper]")
                else:
                    b.set(x, 1, z, rnd.choice(flowers) if r_ < 0.85 else "short_grass")
    return finish_meta(b, "park", st, {"floors": [0], "pond": [lx, lz, lr]})


# ------------------------------------------------------------------ apartman
def apartment_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return int(params.get("width") or max(13, round(17 * s))), int(params.get("depth") or max(11, round(13 * s)))


def apartment(params: dict, ctx: dict | None = None) -> Build:
    """Apartman: zemin katta dukkan vitrinleri + tenteler, ust katlarda pencere ritmi ve balkonlar, duz cati +
    parapet, cati ustu su deposu; katlar arasi merdiven, doseli daireler."""
    st = get_style(params, ctx, params.get("style") or "modern")
    s = scale_of(params, 1.0)
    w, d = apartment_dims(params)
    floors = int(params.get("floors") or max(3, round(5 * s)))
    fh = 4
    seed = int(params.get("seed", 31))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "apartman")
    g = ground_of(ctx, w, d)
    top = floors * fh
    if params.get("clear", True):
        clear_volume(b, -2, 1, -3, w + 1, top + 8, d + 1)
    settle_on_ground(b, g, -2, -3, w + 1, d + 1, st, blend=3)
    shell = P.walls_box(b, 0, 0, 0, w - 1, top - 1, d - 1, st, floors=[i * fh for i in range(floors)], cornice_top=True)
    door_x = w // 2 - 1
    P.door(b, door_x, 1, 0, "north", st, w=2, kind="modern" if st.door_kind == "modern" else None)
    colors = [("red", "white"), ("green", "white"), ("blue", "white"), ("orange", "white")]
    for side in (range(1, door_x - 2), range(door_x + 3, w - 1)):     # vitrinler + tente
        xs = list(side)
        if len(xs) >= 3:
            for x in xs:
                b.fill(x, 1, 0, x, 2, 0, "glass_pane")
            P.awning(b, xs[0], 3, 0, "north", w=len(xs), st=st, depth=2, colors=rnd.choice(colors))
    for fi, fy in enumerate(shell["floors"][1:], start=1):
        wy = fy + 1
        P.window_row(b, 0, wy, d - 1, "south", w, st, h=2)
        P.window_row(b, 0, wy, 0, "west", d, st, h=2)
        P.window_row(b, w - 1, wy, 0, "east", d, st, h=2)
        P.window_row(b, 0, wy, 0, "north", w, st, h=2, avoid=[(door_x - 1, door_x + 2)])   # balkon hizasi bos
        if fi % 2:
            P.balcony(b, door_x - 1, fy, 0, "north", w=4, depth=2, st=st, door_w=2)
        else:   # balkonsuz katta ortada duz (alinliksiz) pencere: ustteki balkon konsoluyla cakismaz
            P.window(b, door_x, wy, 0, "north", w=2, h=2, st=st, kind="modern")
    P.roof_flat(b, 0, 0, w - 1, d - 1, top, st, overhang=0, parapet=1)
    # cati: su deposu
    tx, tz = w - 4, d - 4
    SH.cylinder((tx, top + 1, tz), (tx, top + 4, tz), 1.6).put(b, "minecraft:spruce_planks")
    for (X, Z) in ((tx - 1, tz - 1), (tx + 1, tz - 1), (tx - 1, tz + 1), (tx + 1, tz + 1)):
        b.set(X, top + 1, Z, "spruce_fence")
    # ic
    # her katta dogu kenarinda merdiven holu (4 blok): merdivenler odalarin icinden gecmez, her oda hole kapiyla baglanir
    plans = [["shop"], ["living_room", "kitchen", "master_bedroom", "bathroom"]]
    rooms_all, doors = [], [(door_x, 1, 0), (door_x + 1, 1, 0)]
    hall_w = 4
    for fi, rb in enumerate(shell["rooms"]):
        x0, y0, z0, x1, y1, z1 = rb
        hx0 = x1 - hall_w + 1
        hall = ("foyer", (hx0, y0, z0, x1, y1, z1))
        kinds = plans[0] if fi == 0 else plans[1]
        rooms = split_rooms(x0, z0, hx0 - 2, z1, y0, y1 - y0 + 1, kinds, min_w=3, avoid_x=range(door_x - 1, door_x + 3))
        rooms = rooms + [hall]
        doors += partition_walls(b, rooms, st, y0, y1 - y0 + 1, (x0, z0, x1, z1))
        rooms_all += rooms
    keep = [(door_x, 1, 1), (door_x + 1, 1, 1), (door_x, 1, 2), (door_x + 1, 1, 2)]
    for fi in range(floors - 1):
        fy = shell["floors"][fi]
        sx, sz = w - 2 - 2 * (fi % 2), d - 3     # holun icinde (x1 ve x1-2 sutunlari)
        keep += stair_keep(P.staircase(b, sx, fy + 1, sz, "north", rise=fh, st=st, w=1))
        keep += stair_access(b, sx, sz, fy, fh, bool(fi % 2))
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    perimeter_lamps(b, 0, 0, w - 1, d - 1, 3, st, every=6, faces=("south", "east", "west"))
    for lx in (door_x - 1, door_x + 2):
        P.wall_lamp(b, lx, 3, 0, "north", st)
    return finish_meta(b, "apartment", st, {"floors": shell["floors"], "door": [door_x, 1, 0]})


# ------------------------------------------------------------------ sehir blogu
def city_dims(params: dict) -> tuple[int, int]:
    n = int(params.get("width") or params.get("size_m") or 200)
    if isinstance(params.get("size"), (int, float)) and params["size"] > 20:
        n = int(params["size"])
    return n, int(params.get("depth") or n)


def _road(b, x0, z0, x1, z1, axis: str, st_road: dict):
    """Asfalt yol: iki serit, kesik orta cizgi, kenarlarda bordur + kaldirim."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            b.set(x, 0, z, st_road["asphalt"] if (x * 13 + z * 7) % 9 else st_road["asphalt2"])
    if axis == "x":
        mz = (z0 + z1) // 2
        for x in range(x0, x1 + 1):
            if (x // 3) % 2 == 0:
                b.set(x, 0, mz, st_road["line"])
    else:
        mx = (x0 + x1) // 2
        for z in range(z0, z1 + 1):
            if (z // 3) % 2 == 0:
                b.set(mx, 0, z, st_road["line"])


def city_block(params: dict, ctx: dict | None = None) -> Build:
    """Yollarla sehir blogu (varsayilan 200x200): izgara yollar (asfalt, kesik orta cizgi, yaya gecitleri),
    kaldirimlar + sokak lambalari + sokak agaclari; adalarda apartmanlar, evler, dukkan siralari, bir park ve
    bir meydan; her yapi kendi ureteciyle (oda doseme dahil) uretilir ve yola bakacak sekilde doner."""
    from . import build as gen_build
    st = get_style(params, ctx, params.get("style") or "modern")
    FW, FD = city_dims(params)
    seed = int(params.get("seed", 41))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "şehir bloğu")
    g = ground_of(ctx, FW, FD)
    rw = int(params.get("road") or 7)                 # yol genisligi
    sw = 2                                            # kaldirim
    cell = int(params.get("block") or 46)             # ada + yol adimi
    clear_volume(b, 0, 1, 0, FW - 1, 40, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=8)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    road = {"asphalt": "gray_concrete", "asphalt2": "gray_concrete_powder", "line": "white_concrete",
            "curb": "smooth_stone", "walk": "smooth_stone_slab[type=double]"}
    road["walk"] = "polished_andesite"
    xs = list(range(0, FW - rw + 1, cell))
    zs = list(range(0, FD - rw + 1, cell))
    if xs[-1] + rw < FW - 10:
        xs.append(FW - rw)
    if zs[-1] + rw < FD - 10:
        zs.append(FD - rw)
    for x in xs:
        _road(b, x, 0, x + rw - 1, FD - 1, "z", road)
    for z in zs:
        _road(b, 0, z, FW - 1, z + rw - 1, "x", road)
    for x in xs:                                      # kavsaklar + yaya gecitleri
        for z in zs:
            for xx in range(x, x + rw):
                for zz in range(z, z + rw):
                    b.set(xx, 0, zz, road["asphalt"])
            for k in range(rw):
                if k % 2 == 0:
                    for zz in (z - 2, z - 3):
                        if 0 <= zz < FD:
                            b.set(x + k, 0, zz, "white_concrete")
                    for xx in (x - 2, x - 3):
                        if 0 <= xx < FW:
                            b.set(xx, 0, z + k, "white_concrete")
    # adalar
    islands = []
    for i, x in enumerate(xs):
        nx = xs[i + 1] if i + 1 < len(xs) else None
        if nx is None:
            continue
        for j, z in enumerate(zs):
            nz = zs[j + 1] if j + 1 < len(zs) else None
            if nz is None:
                continue
            ax0, az0, ax1, az1 = x + rw, z + rw, nx - 1, nz - 1
            if ax1 - ax0 < 12 or az1 - az0 < 12:
                continue
            islands.append((ax0, az0, ax1, az1))
            # kaldirim + bordur + lamba + sokak agaci
            for xx in range(ax0, ax1 + 1):
                for zz in range(az0, az1 + 1):
                    edge = min(xx - ax0, ax1 - xx, zz - az0, az1 - zz)
                    if edge < sw:
                        b.set(xx, 0, zz, road["walk"] if edge else road["curb"])
                    else:
                        b.set(xx, 0, zz, "grass_block")
            for xx in range(ax0 + 3, ax1 - 1, 12):
                for zz in (az0 + 1, az1 - 1):
                    P.lamp_post(b, xx, 1, zz, st, h=5, kind="modern")
            for zz in range(az0 + 9, az1 - 3, 12):
                for xx in (ax0 + 1, ax1 - 1):
                    P.lamp_post(b, xx, 1, zz, st, h=5, kind="modern")
    # adalara kullanim ata: park, meydan, apartmanlar, konutlar
    rnd.shuffle(islands)
    uses = ["park" if k == 0 else "plaza" if k == 1 else "apartments" if k % 3 == 2 else "houses" for k in range(len(islands))]
    flat = {"terrain": None, "biome": (ctx or {}).get("biome", "minecraft:plains")}
    placed = []
    for isl, use in zip(islands, uses):
        ax0, az0, ax1, az1 = isl
        ix0, iz0, ix1, iz1 = ax0 + sw, az0 + sw, ax1 - sw, az1 - sw
        iw, idp = ix1 - ix0 + 1, iz1 - iz0 + 1
        if use in ("park", "plaza"):
            sub_b = gen_build(use, {"width": iw, "depth": idp, "seed": rnd.randint(0, 999), "style": "classical"}, flat)
            b.merge(sub_b, ix0, 0, iz0)            # ada icini tamamen kendisi doldurur
            placed.append((use, ix0, iz0))
            continue
        # iki sira: kuzey sirasi kuzeye (yola), guney sirasi guneye bakar; parseller gercek blok sinirina gore dizilir
        rects = []
        for row, rot in (("north", 0), ("south", 2)):
            cursor = ix0 + 1
            tries = 0
            while cursor < ix1 - 8 and tries < 12:
                tries += 1
                if use == "houses":
                    prm = {"size": rnd.choice(["küçük", "orta"]), "floors": rnd.choice([1, 2, 2]), "landscape": False,
                           "clear": False, "style": rnd.choice(["rustic", "scandinavian", "mediterranean", "classical"]),
                           "width": rnd.choice([9, 11, 13]), "depth": rnd.choice([8, 9, 10]), "seed": rnd.randint(0, 9999)}
                    gname = "house"
                else:
                    prm = {"width": rnd.choice([13, 15, 17]), "depth": rnd.choice([10, 11, 12]), "floors": rnd.choice([3, 4, 5, 6]),
                           "clear": False, "style": rnd.choice(["modern", "classical", "mediterranean"]), "seed": rnd.randint(0, 9999)}
                    gname = "apartment"
                try:
                    sb = gen_build(gname, prm, flat)
                except Exception as e:
                    b.meta.setdefault("notes", []).append(f"{gname}: {e}")
                    continue
                tb = sb.transformed(rot) if rot else sb
                (tx0, ty0, tz0), ids = tb.dense()
                solid = ids > 1
                if not solid.any():
                    continue
                zs_, xs_ = np.nonzero(solid.any(axis=0))
                bx0, bx1 = tx0 + int(xs_.min()), tx0 + int(xs_.max())
                bz0, bz1 = tz0 + int(zs_.min()), tz0 + int(zs_.max())
                wid, dep = bx1 - bx0 + 1, bz1 - bz0 + 1
                if cursor + wid - 1 > ix1 - 1 or dep > idp // 2 - 1:
                    break
                dx = cursor - bx0
                dz = (iz0 + 1 - bz0) if row == "north" else (iz1 - 1 - bz1)
                r = (bx0 + dx, bz0 + dz, bx1 + dx, bz1 + dz)
                if any(not (r[2] + 1 < q[0] or q[2] + 1 < r[0] or r[3] + 1 < q[1] or q[3] + 1 < r[1]) for q in rects):
                    break
                b.merge(tb, dx, 0, dz)
                rects.append(r)
                placed.append((gname, dx, dz, row))
                cursor = r[2] + 3
        # arka bahceler: iki sira arasinda cit ve agaclar
        mz = (iz0 + iz1) // 2
        for x in range(ix0 + 2, ix1 - 1, 7):
            if all(not (q[0] - 1 <= x <= q[2] + 1 and q[1] - 1 <= mz <= q[3] + 1) for q in rects) and b.get_id(x, 1, mz) <= 1:
                P.tree(b, x, 1, mz, st, kind=rnd.choice(["round", "birch", "blossom"]), seed=rnd.randint(0, 999))
    return finish_meta(b, "city_block", st, {"floors": [0], "roads": {"x": xs, "z": zs, "width": rw}, "islands": len(islands),
                                             "buildings": len(placed)})


register("skyscraper", skyscraper, skyscraper_dims,
         "Fütüristik cam gökdelen: podyum + pahlı kademeli kule, beyaz kanatlar, mavi cam cephe, ışık kuşakları, döner merdivenli çekirdek, helikopter pisti; çevresinde desenli meydan, havuzlar, ağaçlar",
         {"size": "orta|büyük|devasa", "floors": "kat sayısı", "width": "taban genişliği", "plaza": "meydan payı"},
         lambda p: p.get("name") or "gökdelen")
register("plaza", plaza, plaza_dims, "Kent meydanı: desenli döşeme, çeşme/şadırvan, ağaç saksıları, banklar, lambalar, bayraklar",
         {"width": "genişlik", "depth": "derinlik", "style": "classical|modern|ottoman"}, lambda p: p.get("name") or "meydan")
register("park", park, park_dims,
         "Çiçekli park: araziyi düzler, kıvrımlı yollar, bol çiçek tarhları, nilüferli göl, çardak, çeşme, ağaçlar, banklar, fenerler",
         {"width": "genişlik", "depth": "derinlik"}, lambda p: p.get("name") or "çiçekli park")
register("apartment", apartment, apartment_dims,
         "Apartman: zemin katta tenteli dükkân vitrinleri, üst katlarda pencere ritmi ve balkonlar, düz çatı + su deposu, döşeli daireler",
         {"floors": "3-8", "width": "genişlik", "depth": "derinlik", "style": "modern|classical|mediterranean"},
         lambda p: p.get("name") or "apartman")
register("city_block", city_block, city_dims,
         "Şehir bloğu (varsayılan 200x200): ızgara asfalt yollar, yaya geçitleri, kaldırımlar, sokak lambaları; adalarda apartmanlar, evler, park ve meydan",
         {"width": "200", "depth": "200", "road": "yol genişliği", "block": "ada adımı"}, lambda p: p.get("name") or "şehir bloğu")
