"""On taraf: oyuncunun durdugu Gun Batimi Terasi (kalp kakma, banklar, havai fisek dugmesi ve 9 firlatici),
Ask Koprusu (gul kemerleri, cam zemin), adanin ucundaki iskele yolu, dev Kalp Kapisi, Ask Bulvari (isikli yansima
havuzlari, kiraz agaclari, fenerler, kemerler) ve bulvarin ortasindaki kalpli cesme meydani."""
from __future__ import annotations

import json
import math
from collections import deque

import numpy as np

import aa_core as C
import aa_tower as T
from aa_core import AX, AZ, GY, SEA, World

DECK_R = 10
POST = "pale_oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]"
LEAF_A = "flowering_azalea_leaves[distance=1,persistent=true,waterlogged=false]"
LEAF_C = "cherry_leaves[distance=1,persistent=true,waterlogged=false]"
GATE_X = -308
AVE_X0, AVE_X1 = -305, T.PFRONT - 11
PLAZA_X = -282

# havai fisek: pembe, kirmizi, altin, beyaz; her firlaticida 9 x 64 roket
_COLS = {"pink": 16738740, "rose": 16724889, "red": 16711680, "gold": 16766720, "white": 16777215, "lilac": 13148872}


def rocket_snbt(shape, cols, fades, slot, dur=2):
    c = ",".join(str(_COLS[k]) for k in cols)
    f = ",".join(str(_COLS[k]) for k in fades)
    ex = "{shape:\"%s\",colors:[I;%s],fade_colors:[I;%s],has_trail:1b,has_twinkle:1b}" % (shape, c, f)
    return ("{Slot:%db,id:\"minecraft:firework_rocket\",count:64,components:{\"minecraft:fireworks\":"
            "{flight_duration:%db,explosions:[%s]}}}" % (slot, dur, ex))


def dispenser_snbt(k):
    shapes = ("large_ball", "star", "burst", "large_ball", "small_ball", "star", "large_ball", "burst", "star")
    palettes = ((("pink", "white"), ("gold",)), (("red", "pink"), ("white",)), (("gold", "white"), ("pink",)),
                (("pink", "lilac"), ("white",)), (("rose", "gold"), ("pink",)), (("white", "pink"), ("gold",)))
    items = []
    for s in range(9):
        cols, fades = palettes[(k + s) % len(palettes)]
        items.append(rocket_snbt(shapes[(k + s) % len(shapes)], cols, fades, s, dur=2 + (k + s) % 2))
    return "{Items:[" + ",".join(items) + "]}"


def pillars(w: World, mask, top, state=C.QUARTZ):
    """Denizde ayak: dogal tabandan top'a kadar sutun."""
    zs, xs = np.nonzero(mask)
    i = w.id(state)
    for z, x in zip(zs, xs):
        fl = int(w.floor[z, x]) if w.floor is not None else C.Y0
        for y in range(max(fl, C.Y0), top + 1):
            w.G[y - C.Y0, z, x] = i


# ------------------------------------------------------------------ gun batimi terasi + havai fisek
def deck(w: World):
    X, Z = w.XX, w.ZZ
    d2 = (X - AX) ** 2 + (Z - AZ) ** 2
    disk = d2 <= DECK_R * DECK_R + DECK_R
    rim = disk & (d2 > (DECK_R - 1) ** 2 + (DECK_R - 1))
    w.layer(GY, disk, C.QUARTZ)
    w.layer(GY - 1, disk, C.QUARTZ)
    w.layer(GY - 2, disk, C.QUARTZ)
    w.layer(GY, rim, C.GOLD)
    hx, hz = C.heart_poly(AX + 0.5, AZ + 0.5, 0.34)
    hm = w.mask_poly(hx, hz) & disk
    w.layer(GY, hm, C.PINK)
    w.layer(GY, C.edge4(hm), C.ROSE)
    w.occ |= disk
    # alt: deniz ustunde 9 ayak + alt isik halkasi (gece suya yansir)
    legs = disk & (((X - AX) % 6 == 0) & ((Z - AZ) % 6 == 0))
    pillars(w, legs, GY - 3)
    w.layer(GY - 3, rim & ((X + Z) % 2 == 0), C.SEAL)
    # korkuluk: cam panel, dogu koprusu acik; aralarda fenerli dikmeler
    edge = C.ring_out(disk)
    open_e = (X > AX) & (np.abs(Z - AZ) <= 3)
    w.layer(GY, edge & ~open_e, C.QUARTZ)
    w.layer(GY + 1, edge & ~open_e, C.CPANE)
    posts = edge & ~open_e & (C.hash2(X, Z, 1) < 2) & (((np.round(np.degrees(np.arctan2(Z - AZ, X - AX))) % 30) == 0))
    w.layer(GY + 1, posts, C.QPILLAR)
    w.layer(GY + 2, posts, "lantern[hanging=false,waterlogged=false]")
    # banklar: batiya (gun batimina) bakan iki bank
    for zs in ((AZ - 5, AZ - 3), (AZ + 3, AZ + 5)):
        for zz in range(zs[0], zs[1] + 1):
            w.set(AX - 5, GY + 1, zz, "cherry_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]")
        w.set(AX - 5, GY + 1, zs[0] - 1, "cherry_trapdoor[facing=north,half=bottom,open=true,powered=false,waterlogged=false]")
        w.set(AX - 5, GY + 1, zs[1] + 1, "cherry_trapdoor[facing=south,half=bottom,open=true,powered=false,waterlogged=false]")
    # dort lamba diregi (capraz)
    for dx, dz in ((6, 6), (6, -6), (-6, 6), (-6, -6)):
        x, z = AX + dx, AZ + dz
        w.box(x, GY + 1, z, x, GY + 3, z, C.QPILLAR)
        w.set(x, GY + 4, z, C.FROG)
        w.set(x, GY + 5, z, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    # saksida cicekler
    for (dx, dz) in ((-8, 0), (0, -8), (0, 8)):
        w.set(AX + dx, GY + 1, AZ + dz, "potted_pink_tulip")
    fireworks(w)


def fireworks(w: World):
    """Batidaki altin kaide uzerinde kiraz dugmesi; terasin altinda (y=GY-1) kizil tas tozu agaci, kenarda yukari bakan
    9 firlatici (GY-2). Dugmeye her basista hepsi birer roket atar (dugme gucu altindaki bloga, oradan toza gecer)."""
    bx, bz = AX - 7, AZ
    w.set(bx, GY, bz, C.GOLD)
    w.set(bx, GY + 1, bz, "cherry_button[face=floor,facing=east,powered=false]")
    w.sign(bx - 1, GY + 1, bz, "west", ["HAVAİ FİŞEK", "düğmeye bas", "♥", ""], color="black", wall=False)
    w.set(bx - 1, GY, bz, C.QUARTZ)
    # firlaticilar: terasin hemen disindaki halkanin bati yarisinda esit aralikli 9 hucre (GY - 2'de, yukari bakar)
    X, Z = w.XX, w.ZZ
    R2 = DECK_R * DECK_R + DECK_R
    disk = (X - AX) ** 2 + (Z - AZ) ** 2 <= R2
    ring = C.ring_out(disk) & (X <= AX - 5)
    rz, rx = np.nonzero(ring)
    ang = np.arctan2(rz + C.Z0 - AZ, rx + C.X0 - AX)
    ang = np.where(ang < 0, ang + 2 * math.pi, ang)
    order = np.argsort(ang)
    pick = order[np.linspace(0, len(order) - 1, 9).round().astype(int)]
    disp = []
    for k, i in enumerate(pick):
        x, z = int(rx[i]) + C.X0, int(rz[i]) + C.Z0
        best = None
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            xi, zi = x + dx, z + dz
            if (xi - AX) ** 2 + (zi - AZ) ** 2 <= R2:
                best = (xi, zi)
                break
        if best is not None:
            disp.append(((x, z), best, k))
    y_d, y_w = GY - 2, GY - 1
    for (x, z), _, k in disp:
        w.set(x, y_d, z, "dispenser[facing=up,triggered=false]")
        w.be[(x, y_d, z)] = dispenser_snbt(k)
        w.set(x, y_d + 1, z, 1)
        w.set(x, y_d + 2, z, 1)
        w.set(x, y_d + 3, z, 1)
    # toz agaci (BFS, 4-komsu, teras disk icinde): kaynaktan her hedefe en kisa yol
    start = (bx, bz)
    targets = {b for _, b, _ in disp}
    prev = {start: None}
    q = deque([start])
    while q:
        c = q.popleft()
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + dx, c[1] + dz)
            if n in prev or (n[0] - AX) ** 2 + (n[1] - AZ) ** 2 > R2:
                continue
            prev[n] = c
            q.append(n)
    dust = set()
    longest = 0
    for t in targets:
        p, L = t, 0
        while p is not None:
            dust.add(p)
            p = prev.get(p)
            L += 1
        longest = max(longest, L)
    for (x, z) in dust:
        w.set(x, y_w, z, "redstone_wire[east=none,north=none,south=none,west=none,power=0]")
        w.set(x, y_w - 1, z, C.QUARTZ)
    w.notes.append(f"havai fisek: {len(disp)} firlatici, toz {len(dust)} hucre, en uzun yol {longest}")
    w.fireworks = dict(button=(bx, GY + 1, bz), dispensers=[(x, y_d, z) for (x, z), _, _ in disp])


# ------------------------------------------------------------------ ask koprusu
def bridge(w: World):
    x0, x1 = AX + DECK_R, C.XT + 2
    X, Z = w.XX, w.ZZ
    m = w.mask_rect(x0, AZ - 3, x1, AZ + 3)
    w.layer(GY, m, C.QUARTZ)
    w.layer(GY - 1, m, C.WHITE)
    w.layer(GY, m & (Z == AZ) & ((X % 2) == 0), C.GLASS)
    w.layer(GY - 1, m & (Z == AZ) & ((X % 2) == 0), C.SEAL)
    w.layer(GY, m & (np.abs(Z - AZ) == 1), C.ROSE)
    w.layer(GY - 1, m & (np.abs(Z - AZ) == 3) & (X % 3 == 0), C.SEAL)
    w.occ |= m
    legs = m & (np.abs(Z - AZ) == 3) & ((X - x0) % 6 == 3)
    pillars(w, legs, GY - 2)
    edge = m & (np.abs(Z - AZ) == 3)
    w.layer(GY + 1, edge, C.CPANE)
    # gul kemerleri: her 4 blokta beyaz kemer + azalea/kiraz yapraklari + asili fener
    for x in range(x0 + 2, x1 - 1, 4):
        for zz in (AZ - 3, AZ + 3):
            w.box(x, GY + 1, zz, x, GY + 4, zz, C.QPILLAR)
        w.box(x, GY + 5, AZ - 2, x, GY + 5, AZ + 2, C.QUARTZ)
        w.set(x, GY + 5, AZ - 3, "smooth_quartz_stairs[facing=south,half=top,shape=straight,waterlogged=false]")
        w.set(x, GY + 5, AZ + 3, "smooth_quartz_stairs[facing=north,half=top,shape=straight,waterlogged=false]")
        w.box(x, GY + 6, AZ - 2, x, GY + 6, AZ + 2, LEAF_A)
        w.set(x, GY + 6, AZ, LEAF_C)
        for zz in (AZ - 4, AZ + 4):
            w.box(x, GY + 3, zz, x, GY + 5, zz, LEAF_A)
        w.set(x, GY + 4, AZ, "lantern[hanging=true,waterlogged=false]")


# ------------------------------------------------------------------ ucun yolu, kalp kapisi, bulvar
def tip_path(w: World):
    X, Z = w.XX, w.ZZ
    path = (X >= C.XT) & (X < GATE_X + 3) & (np.abs(Z - AZ) <= 3) & (w.D > -1)
    w.layer(GY, path, C.QUARTZ)
    w.layer(GY, path & (np.abs(Z - AZ) == 1), C.ROSE)
    w.layer(GY, path & (Z == AZ) & (X % 4 == 0), C.GOLD)
    for y in range(SEA - 2, GY):
        w.layer(y, path & (w.top < GY), C.WHITE if y < GY - 1 else "stone")
    w.top = np.where(path, GY, w.top).astype(np.int16)
    w.occ |= path
    side = C.dilate(path, 1) & ~path & (w.D > 0)
    w.layer(GY + 1, side & (w.top >= GY - 1) & ((X % 2) == 0), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    for x in range(C.XT + 4, GATE_X, 6):
        for zz in (AZ - 4, AZ + 4):
            if w.top[zz - C.Z0, x - C.X0] >= GY - 1:
                w.box(x, GY, zz, x, GY, zz, C.QUARTZ)
                w.box(x, GY + 1, zz, x, GY + 3, zz, C.QPILLAR)
                w.set(x, GY + 4, zz, C.FROG)


def heart_gate(w: World):
    """Dev Kalp Kapisi: dikey kalp halkasi (dis kuvars, ortada altin, ic kenarda gece isildayan kurbaga isigi); kalbin
    alt ucu yerin altinda kalir, iki ayak arasindan ~22 blok genis gecit acilir."""
    s = 1.35
    ytip = GY - 13
    py = ytip + (C.HY + 17.0) * s
    pz = AZ + 0.5 + C.HX * s
    ys = np.arange(GY, int(py.max()) + 3)
    zs = np.arange(int(pz.min()) - 3, int(pz.max()) + 4)
    Yg, Zg = np.meshgrid(ys, zs, indexing="ij")
    dist = C.seg_distance(pz, py, Zg.ravel() + 0.5, Yg.ravel() + 0.5).reshape(Yg.shape)
    ins = C.raster(pz, py, int(zs[0]), int(ys[0]), len(zs), len(ys))          # [y, z]
    sd = np.where(ins, dist, -dist)
    band = (sd > -2.2) & (sd <= 1.3)
    layers = ((C.QUARTZ, band & (sd <= -0.6)), (C.GOLD, band & (sd > -0.6) & (sd <= 0.4)), (None, band & (sd > 0.4)))
    for dx in (-1, 0, 1):
        x = GATE_X + dx
        for st, m in layers:
            st = st or (C.FROG if dx == 0 else C.GOLD)
            yy, zz = np.nonzero(m)
            for a, b in zip(yy, zz):
                w.set(x, int(ys[a]), int(zs[b]), st)
    # ayaklar: halkanin zemine degdigi yerlerde kuvars kaide + cicek kasalari
    foot = np.nonzero(band[0])[0]
    legs = sorted({int(zs[i]) for i in foot})
    for side in (-1, 1):
        zz = [z for z in legs if (z - AZ) * side > 0]
        if not zz:
            continue
        zc = int(round(np.mean(zz)))
        w.box(GATE_X - 2, GY, zc - 2, GATE_X + 2, GY + 1, zc + 2, C.QUARTZ)
        w.box(GATE_X - 2, GY + 1, zc - 2, GATE_X + 2, GY + 1, zc + 2, "smooth_quartz_slab[type=top,waterlogged=false]",
              only=[0, 1])
        w.box(GATE_X - 3, GY + 1, zc + side * 3, GATE_X + 3, GY + 1, zc + side * 4, "moss_block")
        w.box(GATE_X - 3, GY + 2, zc + side * 3, GATE_X + 3, GY + 2, zc + side * 4, "flowering_azalea")
        for k in range(5):
            w.box(GATE_X - 2, GY - 1 - k, zc - 2, GATE_X + 2, GY - 1 - k, zc + 2, C.QUARTZ)
    w.occ |= w.mask_rect(GATE_X - 3, AZ - 20, GATE_X + 3, AZ + 20)


def avenue(w: World):
    X, Z = w.XX, w.ZZ
    dz = np.abs(Z - AZ)
    sec = (X >= AVE_X0) & (X <= AVE_X1)
    land = w.D > 1.5
    walk = sec & (dz <= 4) & land
    pool = sec & (dz >= 5) & (dz <= 8) & land & (w.D > 3)
    curb = sec & (dz == 9) & land
    lawn = sec & (dz >= 10) & (dz <= 14) & (w.D > 6)
    hedge = sec & (dz == 15) & (w.D > 7)
    plaza = (X - PLAZA_X) ** 2 + (Z - AZ) ** 2 <= 15 * 15 + 15
    walk &= ~plaza
    pool &= ~C.dilate(plaza, 1)
    pat = ((X + Z) % 2 == 0)
    w.layer(GY, walk, C.QUARTZ)
    w.layer(GY, walk & (dz == 4), C.ROSE)
    w.layer(GY, walk & (dz == 0) & (X % 6 == 0), C.GOLD)
    w.layer(GY, walk & (dz == 2) & pat, C.CALCITE)
    w.layer(GY, pool, "water")
    w.layer(GY - 1, pool, C.WHITE)
    w.layer(GY - 1, pool & (dz == 6) & (X % 4 == 0), C.SEAL)
    w.layer(GY, curb, C.QUARTZ)
    w.layer(GY + 1, curb & (X % 2 == 0), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    w.layer(GY, lawn, "grass_block[snowy=false]")
    w.layer(GY + 1, hedge, LEAF_A)
    w.layer(GY + 2, hedge & (X % 3 == 0), LEAF_A)
    w.occ |= walk | pool | curb | hedge
    # kiraz agaclari (cimen seritlerinde), fenerler, banklar
    from usta.kit import trees
    b = C.kit_build("bulvar")
    i = 0
    for x in range(AVE_X0 + 6, AVE_X1 - 3, 10):
        for zz in (AZ - 12, AZ + 12):
            if lawn[zz - C.Z0, x - C.X0] and not plaza[zz - C.Z0, x - C.X0]:
                trees.tree(b, x, GY, zz, species="cherry", size="medium", seed=900 + i)
                i += 1
    w.merge_build(b, only_empty=True)
    for x in range(AVE_X0 + 1, AVE_X1, 10):
        for zz in (AZ - 9, AZ + 9):
            if curb[zz - C.Z0, x - C.X0] and not plaza[zz - C.Z0, x - C.X0]:
                w.box(x, GY + 1, zz, x, GY + 4, zz, C.QPILLAR)
                w.set(x, GY + 5, zz, C.FROG)
                w.set(x, GY + 6, zz, "smooth_quartz_slab[type=bottom,waterlogged=false]")
                for dzz in (-1, 1):
                    w.set(x, GY + 5, zz + dzz, "lantern[hanging=false,waterlogged=false]") if False else None
    for x in range(AVE_X0 + 6, AVE_X1, 10):
        for zz, f in ((AZ - 10, "north"), (AZ + 10, "south")):
            if lawn[zz - C.Z0, x - C.X0] and not plaza[zz - C.Z0, x - C.X0]:
                for k in (-1, 0, 1):
                    w.set(x + k + 2, GY + 1, zz, f"cherry_stairs[facing={f},half=bottom,shape=straight,waterlogged=false]")
    # cicek kemerleri (yuruyus yolunun ustunde)
    for x in range(AVE_X0 + 3, AVE_X1, 14):
        if plaza[AZ - C.Z0, x - C.X0]:
            continue
        for zz in (AZ - 4, AZ + 4):
            w.box(x, GY + 1, zz, x, GY + 5, zz, C.QPILLAR)
        w.box(x, GY + 6, AZ - 3, x, GY + 6, AZ + 3, C.QUARTZ)
        w.set(x, GY + 6, AZ - 4, "smooth_quartz_stairs[facing=south,half=top,shape=straight,waterlogged=false]")
        w.set(x, GY + 6, AZ + 4, "smooth_quartz_stairs[facing=north,half=top,shape=straight,waterlogged=false]")
        w.box(x, GY + 7, AZ - 3, x, GY + 7, AZ + 3, LEAF_A)
        w.box(x - 1, GY + 7, AZ - 1, x + 1, GY + 7, AZ + 1, LEAF_C)
        w.set(x, GY + 5, AZ, "lantern[hanging=true,waterlogged=false]")
    fountain_plaza(w)


def fountain_plaza(w: World):
    """Bulvarin ortasinda daire meydan: kalp seklinde havuz, ortada pembe kalp heykeli, cevrede banklar."""
    X, Z = w.XX, w.ZZ
    d2 = (X - PLAZA_X) ** 2 + (Z - AZ) ** 2
    plaza = d2 <= 15 * 15 + 15
    ring = plaza & (d2 > 13 * 13 + 13)
    w.layer(GY, plaza, C.QUARTZ)
    w.layer(GY, plaza & (((X - PLAZA_X) + (Z - AZ)) % 4 == 0), C.CALCITE)
    w.layer(GY, ring, C.ROSE)
    hx, hz = C.heart_poly(PLAZA_X, AZ + 0.5, 0.62)
    hm = w.mask_poly(hx, hz)
    w.layer(GY, hm, C.WHITE)
    w.layer(GY + 1, C.edge4(hm), "smooth_quartz_slab[type=bottom,waterlogged=false]")
    water = hm & ~C.edge4(hm)
    w.layer(GY + 1, water, "water")
    w.layer(GY, water & ((X + Z) % 3 == 0), C.SEAL)
    w.layer(GY + 2, water & (C.hash2(X, Z, 77) < 0.12), "lily_pad")
    w.occ |= plaza
    # heykel: kaide ustunde 3B pembe kalp (altin kabuk desenli, isildayan noktalar)
    w.box(PLAZA_X - 1, GY + 1, AZ - 1, PLAZA_X + 1, GY + 3, AZ + 1, C.QUARTZ)
    w.box(PLAZA_X - 1, GY + 4, AZ - 1, PLAZA_X + 1, GY + 4, AZ + 1, C.GOLD)
    xs, ys, zs, S, shell = C.heart3d_mask(PLAZA_X + 0.5, GY + 5, AZ + 0.5, 12, 11, 6)
    ids = np.zeros(S.shape, np.uint16)
    Yg, Zg, Xg = np.meshgrid(ys, zs, xs, indexing="ij")
    ids[S] = w.id(C.PINK)
    ids[shell & (((Yg + Zg) % 4) == 0)] = w.id(C.GOLD)
    ids[shell & (((Yg - Zg) % 5) == 0)] = w.id(C.FROG)
    v = w.view(int(xs[0]), int(ys[0]), int(zs[0]), int(xs[-1]), int(ys[-1]), int(zs[-1]))
    v[ids != 0] = ids[ids != 0]
    for a in range(0, 360, 30):
        t = math.radians(a)
        x = PLAZA_X + int(round(12 * math.cos(t)))
        z = AZ + int(round(12 * math.sin(t)))
        if abs(z - AZ) <= 5 and abs(x - PLAZA_X) > 8:
            continue
        w.box(x, GY + 1, z, x, GY + 3, z, C.QPILLAR)
        w.set(x, GY + 4, z, C.FROG)


def front(w: World):
    deck(w)
    bridge(w)
    tip_path(w)
    heart_gate(w)
    avenue(w)
