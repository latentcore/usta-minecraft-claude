"""Kule ic mekanlari: otel katlari (kuzey/guney suit siralari, kis bahceleri, panorama ve gun dogumu salonlari),
havuz terasi lobisi, gokyuzu bahceleri, gokyuzu restorani, seyir terasi, kalbin icindeki balayi suiti.
Her bolgede bir sablon kat dosenir, ayni bolgenin diger katlarina kopyalanir (cephe ve cekirdek her katin kendisinde)."""
from __future__ import annotations

import numpy as np

import aa_core as C
import aa_tower as T
from aa_core import World

CX, CZ = T.CX, T.CZ
LIGHTS = ("sea_lantern", "pearlescent_froglight", "ochre_froglight", "verdant_froglight", "glowstone", "shroomlight",
          "copper_bulb", "redstone_lamp")
CHAIR = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}   # masanin o yanindaki sandalyenin arkaligi
FROG = "pearlescent_froglight[axis=y]"
POST = "pale_oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]"


def floor_no(y):
    fl = sorted(f[0] for f in T.tower_floors())
    return fl.index(y) + 2 if y in fl else 0


def _is_light(name):
    n = name.lstrip("!").split("[", 1)[0].split(":")[-1]
    return n in LIGHTS


def core_mask(w):
    X, Z = w.XX, w.ZZ
    return (X >= CX - 5) & (X <= CX + 5) & (Z >= CZ - 7) & (Z <= CZ + 6)


# ------------------------------------------------------------------ kat plani
def layout(w: World, s):
    """Bir bolge plakasi icin 2B plan maskeleri ve suit kayitlari."""
    g = T.geo(w, s)
    X, Z = w.XX, w.ZZ
    inner = g["inner"]
    core = core_mask(w)
    ncor = inner & (Z >= CZ - 10) & (Z <= CZ - 8)
    scor = inner & (Z >= CZ + 7) & (Z <= CZ + 9)
    wcor = inner & (X >= CX - 8) & (X <= CX - 6) & (Z >= CZ - 10) & (Z <= CZ + 9)
    ecor = inner & (X >= CX + 6) & (X <= CX + 8) & (Z >= CZ - 10) & (Z <= CZ + 9)
    lobby = inner & core & (Z >= CZ)
    corr = ncor | scor | wcor | ecor | lobby
    walls = np.zeros(inner.shape, bool)
    walls |= inner & (Z == CZ - 11)
    walls |= inner & (Z == CZ + 10)
    walls |= inner & (X == CX - 9) & (Z >= CZ - 7) & (Z <= CZ + 6)
    walls |= inner & (X == CX + 9) & (Z >= CZ - 7) & (Z <= CZ + 6)
    walls |= inner & ((Z == CZ - 7) | (Z == CZ + 6)) & ((X <= CX - 9) | (X >= CX + 9))
    walls |= inner & ((X - (CX - 4)) % 9 == 0) & ((Z <= CZ - 12) | (Z >= CZ + 11))
    walls &= ~corr
    rooms = []
    for side, zs in (("N", -1), ("S", 1)):
        wall_z = CZ - 11 if side == "N" else CZ + 10
        region = inner & ((Z <= CZ - 12) if side == "N" else (Z >= CZ + 11)) & ~walls
        for k in range(-6, 6):
            xa, xb = CX - 3 + 9 * k, CX + 4 + 9 * k
            cells = region & (X >= xa) & (X <= xb)
            if cells.sum() < 12:
                continue
            zc = wall_z - zs
            dx = None
            for cand in [CX + 9 * k] + list(range(xa + 1, xb)):
                j = cand - C.X0
                if 0 <= j < w.nx and corr[zc - C.Z0, j] and region[wall_z + zs - C.Z0, j]:
                    dx = cand
                    break
            if dx is None:
                continue
            d = 0
            while d < 11:
                zz = wall_z + zs * (d + 1)
                row = cells[zz - C.Z0, xa - C.X0:xb - C.X0 + 1]
                if row.size == (xb - xa + 1) and row.all():
                    d += 1
                else:
                    break
            rooms.append(dict(side=side, k=k, xa=xa, xb=xb, wall_z=wall_z, zs=zs, door=(dx, wall_z), depth=d, cells=cells))
    blocks = []
    for side, sel, door in (("W", X <= CX - 10, (CX - 9, CZ)), ("E", X >= CX + 10, (CX + 9, CZ))):
        region = inner & sel & (Z >= CZ - 6) & (Z <= CZ + 5) & ~walls
        if region.sum() > 10:
            blocks.append(dict(side=side, cells=region, door=door))
    return dict(g=g, corr=corr, walls=walls, rooms=rooms, blocks=blocks, core=core, lobby=lobby,
                ncor=ncor, scor=scor, wcor=wcor, ecor=ecor)


def winter_garden(w: World, y, cells, seed, clear=None):
    """Suitin cephe tarafindaki kis bahcesi: yosun zemin, cicekler, azalea calilari, sakayik, fener."""
    X, Z = w.XX, w.ZZ
    w.layer(y, cells, "moss_block")
    free = cells if clear is None else cells & ~clear
    r = C.hash2(X, Z, seed)
    acc = 0.0
    for st, p in (("flowering_azalea", 0.10), ("pink_tulip", 0.08), ("white_tulip", 0.06), ("azalea", 0.05),
                  ("lily_of_the_valley", 0.05), ("pink_petals[facing=north,flower_amount=4]", 0.12)):
        w.layer(y + 1, free & (r >= acc) & (r < acc + p), st)
        acc += p
    tall = free & (r >= acc) & (r < acc + 0.05)
    w.layer(y + 1, tall, "peony[half=lower]")
    w.layer(y + 2, tall, "peony[half=upper]")
    lamp = free & ((X + 2 * Z) % 7 == 0) & (r >= acc + 0.05)
    w.layer(y + 1, lamp, "lantern[hanging=false,waterlogged=false]")


def lounge(w: World, y, cells, side, seed):
    """Panorama (bati, adanin ucuna ve gun batimina) / gun dogumu (dogu) salonu: kanepeler, sehpalar, mumlar."""
    X, Z = w.XX, w.ZZ
    w.layer(y, cells, "polished_diorite")
    w.layer(y + 1, cells & ((X + Z) % 2 == 0), "white_carpet")
    w.layer(y + 1, cells & ((X + Z) % 2 == 1), "pink_carpet")
    near = cells & C.dilate(C.ring_out(cells), 1)
    view = "west" if side == "W" else "east"
    sofa = f"pink_wool_stairs[facing={C.OPP[view]},half=bottom,shape=straight,waterlogged=false]"
    r = C.hash2(X, Z, 40 + seed)
    w.layer(y + 1, near & (r < 0.30), sofa)
    w.layer(y + 1, near & (r >= 0.30) & (r < 0.40), "potted_flowering_azalea_bush")
    mid = cells & ~near & (X % 4 == 0) & (Z % 4 == 0)
    w.layer(y + 1, mid, "cherry_slab[type=top,waterlogged=false]")
    w.layer(y + 2, mid & (r < 0.6), "pink_candle[candles=3,lit=true,waterlogged=false]")
    w.layer(y + T.FH, cells & (X % 4 == 2) & (Z % 4 == 2), FROG)


def hotel_zone(w: World, y0, n, s, zone_idx):
    L = layout(w, s)
    g = L["g"]
    X, Z = w.XX, w.ZZ
    inner, corr, walls = g["inner"], L["corr"], L["walls"]
    ys = [y0 + T.FH * k for k in range(n) if y0 + T.FH * k != T.ROOF]
    if not ys:
        return 0
    yt = ys[0]
    room_floor = inner & ~corr & ~walls & ~L["core"]
    w.layer(yt, room_floor, "cherry_planks")
    w.layer(yt, corr, "polished_diorite")
    for yy in range(yt + 1, yt + T.FH):
        w.layer(yy, walls, C.WHITE)
    run = (L["ncor"] & (Z == CZ - 9)) | (L["scor"] & (Z == CZ + 8)) | (L["wcor"] & (X == CX - 7)) | \
        (L["ecor"] & (X == CX + 7))
    run &= ~L["core"]
    w.layer(yt + 1, run, "pink_carpet")
    # koridor uclari (cephe camina dayanan yerler) saksi
    ends = corr & C.dilate(g["ring"], 1) & ~run
    w.layer(yt + 1, ends & (C.hash2(X, Z, 12) < 0.5), "potted_cherry_sapling")
    signs, recs = [], []
    for i, r in enumerate(L["rooms"]):
        dx, dz = r["door"]
        zs = r["zs"]
        corr_face = "south" if r["side"] == "N" else "north"
        if r["depth"] >= 4:
            za, zb = dz + zs, dz + zs * r["depth"]
            box = (r["xa"], yt + 1, min(za, zb), r["xb"], yt + T.FH - 1, max(za, zb))
            back_z = dz + zs * (r["depth"] + 1)
            back = r["cells"] & (Z == back_z)
            garden = r["cells"] & ((Z - back_z) * zs > 0)
            if back.any():
                for yy in range(yt + 1, yt + T.FH):
                    w.layer(yy, back, C.WHITE)
                win = back & (X >= r["xa"] + 2) & (X <= r["xb"] - 2)
                w.layer(yt + 2, win, C.CPANE)
                w.layer(yt + 3, win, C.CPANE)
                if garden.any():
                    # bahce gecidi: arka duvarda, arkasi bahce olan en sagdaki hucre
                    gx = None
                    for cand in range(r["xb"] - 1, r["xa"], -1):
                        j, ib, ig = cand - C.X0, back_z - C.Z0, back_z + zs - C.Z0
                        if back[ib, j] and garden[ig, j]:
                            gx = cand
                            break
                    clear = np.zeros(garden.shape, bool)
                    if gx is not None:
                        w.box(gx, yt + 1, back_z, gx, yt + 2, back_z, 1)
                        clear[back_z + zs - C.Z0, gx - C.X0] = True
                    winter_garden(w, yt, garden, seed=i + 7 * zone_idx, clear=clear)
            kind = "master_bedroom" if (i + zone_idx) % 5 else "living_room"
            style = C.ROMANTIC if (i + zone_idx) % 2 == 0 else C.ROMANTIC_W
            recs.append((box, kind, [(dx, yt + 1, dz)], i * 13 + zone_idx, style))
        else:
            w.layer(yt + 1, r["cells"] & (C.hash2(X, Z, 3) < 0.3), "potted_flowering_azalea_bush")
            w.box(dx, yt + 1, dz, dx, yt + 2, dz, 1)
        signs.append((dx + 1, dz - zs, corr_face, r))
    for b in L["blocks"]:
        dxw, dzw = b["door"]
        w.box(dxw, yt + 1, dzw - 1, dxw, yt + 3, dzw + 1, 1)
        lounge(w, yt, b["cells"], b["side"], zone_idx)
    for box, kind, doors, seed, style in recs:
        w.kit_room(box, kind, doors, seed=seed, style=style)
    # tavanda (bir ust katin dosemesinde) isik konumlari: kit'in gomdugu + salon + koridor isiklari
    top = w.G[yt + T.FH - C.Y0]
    light_ids = [i for i, s_ in enumerate(w.pal) if _is_light(s_)]
    lights_t = inner & np.isin(top, light_ids)
    lights_ids = top.copy()
    cl = (run & ((X + Z) % 4 == 0)) | (L["lobby"] & (X % 4 == 0) & (Z % 3 == 0))
    # sablonu diger katlara kopyala (yalniz plaka ici, cekirdek haric)
    tmpl = w.G[yt - C.Y0:yt + T.FH - C.Y0].copy()
    keep = inner & ~L["core"]
    be_t = {k: v for k, v in w.be.items() if yt <= k[1] < yt + T.FH and keep[k[2] - C.Z0, k[0] - C.X0]}
    for yf in ys[1:]:
        dst = w.G[yf - C.Y0:yf + T.FH - C.Y0]
        dst[:, keep] = tmpl[:, keep]
        for (bx, by, bz), snbt in be_t.items():
            w.be[(bx, by - yt + yf, bz)] = snbt
    for yf in ys:
        ceil = w.G[yf + T.FH - C.Y0]
        m = lights_t & (ceil != 0)
        ceil[m] = lights_ids[m]
        ceil[cl & (ceil != 0)] = w.id(FROG)
        fno = floor_no(yf)
        for (sx, sz, face, r) in signs:
            num = fno * 100 + r["k"] + 7 + (0 if r["side"] == "N" else 20)
            w.sign(sx, yf + 2, sz, face, ["", f"SÜİT {num}", "", ""], color="black")
    w.notes.append(f"otel bolge {zone_idx + 1}: {len(ys)} kat x {len(recs)} suit")
    return len(ys) * len(recs)


def hotel(w: World):
    total = 0
    for i, (y0, n, s) in enumerate(T.ZONES):
        total += hotel_zone(w, y0, n, s, i)
    w.notes.append(f"otel: toplam {total} suit")
    return total


# ------------------------------------------------------------------ havuz terasi lobisi (86)
def deck0(w: World):
    y = T.ROOF
    g = T.geo(w, T.ZONES[0][2])
    X, Z = w.XX, w.ZZ
    core = core_mask(w)
    area = g["inner"] & ~core
    pat = ((X // 3 + Z // 3) % 2 == 0)
    w.layer(y, area & pat, C.QUARTZ)
    w.layer(y, area & ~pat, "pink_glazed_terracotta[facing=north]")
    bar = area & (Z >= CZ - 16) & (Z <= CZ - 15) & (np.abs(X - CX) <= 12)
    w.layer(y + 1, bar, C.QUARTZ)
    w.layer(y + 2, bar, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    stools = area & (Z == CZ - 13) & (np.abs(X - CX) <= 11) & (X % 2 == 0)
    w.layer(y + 1, stools, "cherry_fence[east=false,north=false,south=false,waterlogged=false,west=false]")
    w.layer(y + 2, stools, "pink_carpet")
    shelf = area & (Z == CZ - 18) & (np.abs(X - CX) <= 12)
    w.layer(y + 1, shelf, "cherry_shelf[facing=south,powered=false,side_chain=unconnected,waterlogged=false]")
    w.layer(y + 2, shelf & (X % 2 == 0), "brewing_stand")
    seat = area & ~C.dilate(core, 4) & (X % 5 == 0) & (Z % 5 == 0) & (np.abs(Z - CZ) > 18)
    seat &= C.erode(area, 2)
    w.layer(y + 1, seat, "cherry_slab[type=top,waterlogged=false]")
    w.layer(y + 2, seat, "pink_candle[candles=2,lit=true,waterlogged=false]")
    for (dx, dz), f in CHAIR.items():
        m = C.shift(seat, dz, dx) & area
        w.layer(y + 1, m, f"white_wool_stairs[facing={f},half=bottom,shape=straight,waterlogged=false]", empty=True)
    w.layer(y + 1, C.edge4(area) & (C.hash2(X, Z, 9) < 0.25), "potted_cherry_sapling", empty=True)
    w.layer(y + T.FH, area & (X % 5 == 2) & (Z % 5 == 2), FROG)
    # terasa cikislar: on (bati) ve kuzey/guney (cekirdek hizasi) cephe halkasinda
    ring = g["ring"]
    col = np.nonzero(ring[:, CX - C.X0])[0]
    for zz in (int(col.min()) + C.Z0, int(col.max()) + C.Z0):
        w.box(CX - 1, y + 1, zz, CX + 1, y + 3, zz, 1)
    row = np.nonzero(ring[CZ - C.Z0])[0]
    xf = int(row.min()) + C.X0
    w.box(xf, y + 1, CZ - 1, xf, y + 3, CZ + 1, 1)
    w.box(CX - 14, y + 1, CZ - 15, CX - 14, y + 1, CZ - 15, C.QPILLAR)
    w.sign(CX - 14, y + 2, CZ - 15, "south", ["HAVUZ BARI", "♥", "", ""], color="black", wall=False)


# ------------------------------------------------------------------ gokyuzu bahceleri
def sky_garden(w: World, y, so, si, idx):
    from usta.kit import trees
    gi = T.geo(w, si)
    X, Z = w.XX, w.ZZ
    core = core_mask(w)
    area = gi["inner"] & ~C.dilate(core, 2)
    path = area & ((np.abs(Z - CZ) <= 1) | (np.abs(X - CX) <= 1) | C.edge4(area) |
                   (C.dilate(core, 3) & ~C.dilate(core, 2)))
    garden = area & ~path
    w.layer(y, garden, "grass_block[snowy=false]")
    pat = (X + Z) % 2 == 0
    w.layer(y, path & pat, C.CALCITE)
    w.layer(y, path & ~pat, C.ROSE)
    w.layer(y, C.dilate(core, 2) & ~core & gi["inner"], "polished_diorite")
    b = C.kit_build("bahce")
    spots = garden & C.erode(garden, 2, square=True) & (X % 9 == 4) & (Z % 9 == 4)
    for i, (zz, xx) in enumerate(zip(*np.nonzero(spots))):
        sp = "cherry" if (i + idx) % 3 else "birch"
        try:
            trees.tree(b, int(xx) + C.X0, y, int(zz) + C.Z0, species=sp, size="small", seed=100 * idx + i, ground=False)
        except Exception as e:  # pragma: no cover
            w.notes.append(f"agac atlandi: {e}")
    for (cx_, cy_, cz_), c in b.chunks.items():
        for ly in range(16):
            if cy_ * 16 + ly >= y + 9:
                c[ly] = 0
    w.merge_build(b, only_empty=True)
    r = C.hash2(X, Z, 70 + idx)
    w.layer(y + 1, garden & (r < 0.08), "pink_tulip", empty=True)
    w.layer(y + 1, garden & (r >= 0.08) & (r < 0.14), "white_tulip", empty=True)
    w.layer(y + 1, garden & (r >= 0.14) & (r < 0.26), "pink_petals[facing=east,flower_amount=3]", empty=True)
    bench = path & C.dilate(garden, 1) & ((X + Z) % 11 == 0) & ~C.edge4(area)
    w.layer(y + 1, bench, "cherry_slab[type=bottom,waterlogged=false]", empty=True)
    lamps = path & (X % 6 == 0) & (Z % 6 == 0)
    w.layer(y + 1, lamps, POST, empty=True)
    w.layer(y + 2, lamps, "lantern[hanging=false,waterlogged=false]", empty=True)
    w.layer(y + 10, gi["inner"] & (X % 5 == 0) & (Z % 5 == 0), FROG, only=[w.id(C.WHITE), w.id("cherry_planks"),
                                                                        w.id("polished_diorite")])
    w.sign(CX + 1, y + 3, CZ, "south", ["GÖKYÜZÜ", f"BAHÇESİ {idx + 1}", "", ""], color="black")


def sky_gardens(w: World):
    for i, (y, so, si) in enumerate(T.SKY):
        sky_garden(w, y, so, si, i)


# ------------------------------------------------------------------ gokyuzu restorani (tac) ve seyir terasi
def crown(w: World):
    y = T.CROWN
    g = T.geo(w, T.CROWN_S)
    X, Z = w.XX, w.ZZ
    core = core_mask(w)
    area = g["inner"] & ~core
    pat = ((X + Z) % 4 == 0) | ((X - Z) % 4 == 0)
    w.layer(y, area & pat, C.GOLD)
    w.layer(y, area & ~pat, C.QUARTZ)
    band = area & C.dilate(g["ring"], 4) & ~C.dilate(g["ring"], 1) & ~C.dilate(core, 2)
    tables = band & (X % 4 == 1) & (Z % 4 == 1)
    w.layer(y + 1, tables, POST)
    w.layer(y + 2, tables, "white_carpet")
    w.layer(y + 3, tables & ((X + Z) % 2 == 0), "potted_pink_tulip")
    w.layer(y + 3, tables & ((X + Z) % 2 == 1), "potted_white_tulip")
    for (dx, dz), f in CHAIR.items():
        m = C.shift(tables, dz, dx) & area & (C.hash2(X, Z, 8 + dx + 3 * dz) < 0.7)
        w.layer(y + 1, m, f"cherry_stairs[facing={f},half=bottom,shape=straight,waterlogged=false]", empty=True)
    bar = area & C.dilate(core, 2) & ~C.dilate(core, 1) & (Z < CZ - 6)
    w.layer(y + 1, bar, C.QUARTZ)
    w.layer(y + 2, bar, "smooth_quartz_slab[type=bottom,waterlogged=false]")
    ch = area & (X % 8 == 0) & (Z % 8 == 4) & ~C.dilate(g["ring"], 3) & ~C.dilate(core, 1)
    for yy in range(y + 6, y + 10):
        w.layer(yy, ch, "iron_chain[axis=y,waterlogged=false]")
    w.layer(y + 5, ch, C.GOLD)
    w.layer(y + 4, ch, FROG)
    w.layer(y + 10, area & (X % 5 == 0) & (Z % 5 == 2) & ~ch, FROG, only=[w.id(C.WHITE)])
    px, pz = CX - 13, CZ + 9
    w.box(px, y + 1, pz, px + 2, y + 1, pz + 1, "black_concrete")
    w.box(px, y + 2, pz, px + 2, y + 2, pz, "quartz_slab[type=bottom,waterlogged=false]")
    w.box(px, y + 2, pz + 1, px + 2, y + 2, pz + 1, "black_concrete")
    w.set(px + 1, y + 1, pz + 2, "polished_blackstone_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]")
    w.sign(CX + 6, y + 3, CZ - 8, "north", ["GÖKYÜZÜ", "RESTORANI", "♥", ""], color="black")
    d = T.DECK
    deck = g["inner"] & ~C.dilate(core, 4)
    edge = deck & C.dilate(g["ring"], 2) & ~C.dilate(g["ring"], 1)
    w.layer(d + 1, edge & ((X + Z) % 5 == 0), "cherry_slab[type=bottom,waterlogged=false]")
    w.layer(d + 1, edge & ((X + Z) % 5 == 2), "potted_flowering_azalea_bush")
    posts = deck & C.dilate(g["ring"], 3) & ~C.dilate(g["ring"], 2) & ((X + 2 * Z) % 9 == 0)
    w.layer(d + 1, posts, POST)
    w.layer(d + 2, posts, POST)
    w.layer(d + 3, posts, "lantern[hanging=false,waterlogged=false]")


def heart_suite(w: World):
    """Kalbin icindeki balayi suiti: pembe yatak platformu, iki kisilik yatak (dogudaki pencerelere bakar), gul
    yapraklari, mumlar, kabarcikli jakuzi, kanepe, asma kata merdiven."""
    interior, ys, zz, xs = w.heart_interior
    y = T.SUITE_Y
    k = y - int(ys[0])
    xc, zc = T.HEART_C
    Xg = np.broadcast_to(xs[None, :], (len(zz), len(xs)))
    Zg = np.broadcast_to(zz[:, None], (len(zz), len(xs)))
    shaft = (Xg >= T.SHAFT[0] - 1) & (Xg <= T.SHAFT[2] + 1) & (Zg >= T.SHAFT[1] - 1) & (Zg <= T.SHAFT[3] + 2)
    v = w.view(int(xs[0]), y + 1, int(zz[0]), int(xs[-1]), y + 1, int(zz[-1]))[0]
    floor = w.view(int(xs[0]), y, int(zz[0]), int(xs[-1]), y, int(zz[-1]))[0]
    fl = interior[k]
    walk = fl & C.erode(fl, 1, square=True)
    floor[walk & ((Xg + Zg) % 2 == 0)] = w.id(C.QUARTZ)
    floor[walk & ((Xg + Zg) % 2 == 1)] = w.id(C.WHITE)
    bx, bz = xc + 4, zc + 6                       # yatak basi (bati), ayak doguda: yatanlar dogudaki camlara bakar
    dx, dz = Xg - (bx + 1), Zg - (bz - 0.5)
    plat = walk & (dx * dx + dz * dz <= 18) & ~shaft
    v[plat] = w.id("pink_wool_slab[type=bottom,waterlogged=false]")
    petals = walk & ~plat & ~shaft & (C.SH.hash01(Xg, y, Zg, 4) < 0.30)
    v[petals] = w.id("pink_petals[facing=north,flower_amount=4]")
    for zb in (bz - 1, bz):
        w.set(bx, y + 1, zb, "pink_bed[facing=west,occupied=false,part=head]")
        w.set(bx + 1, y + 1, zb, "pink_bed[facing=west,occupied=false,part=foot]")
        w.set(bx - 1, y + 1, zb, "white_wool")
        w.set(bx - 1, y + 2, zb, "gold_block")
    for zn in (bz - 3, bz + 2):
        w.set(bx, y + 1, zn, "cherry_slab[type=top,waterlogged=false]")
        w.set(bx, y + 2, zn, "pink_candle[candles=4,lit=true,waterlogged=false]")
    # pencere onunde kanepe (doguya, pencerelere bakar)
    for zz_ in range(zc - 4, zc + 1):
        w.set(xc + 8, y + 1, zz_, "white_wool_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
    w.set(xc + 9, y + 1, zc - 2, "cherry_slab[type=top,waterlogged=false]")
    w.set(xc + 9, y + 2, zc - 2, "potted_pink_tulip")
    # jakuzi (kabarcikli): 3x3, ruh kumu ustunde kabarcik sutunu, altin kenar
    jx, jz = xc - 5, zc + 11
    w.box(jx - 2, y, jz - 2, jx + 2, y + 1, jz + 2, C.GOLD)
    w.box(jx - 1, y - 1, jz - 1, jx + 1, y - 1, jz + 1, C.GOLD)
    w.box(jx - 1, y, jz - 1, jx + 1, y, jz + 1, "soul_sand")
    w.box(jx - 1, y + 1, jz - 1, jx + 1, y + 1, jz + 1, "bubble_column[drag=false]")
    # asma kata merdiven (guney kenari, batiya cikar): 12 basamak
    sz = zc + 15
    for i in range(12):
        xx = xc + 9 - i
        yy = y + 1 + i
        w.set(xx, yy, sz, "quartz_stairs[facing=west,half=bottom,shape=straight,waterlogged=false]")
        if i:
            w.set(xx, yy - 1, sz, C.QUARTZ)
        for hh in range(1, 4):
            if w.get(xx, yy + hh, sz) not in (0, 1):
                w.set(xx, yy + hh, sz, 1)
    # asma kat korkulugu (merdivenin vardigi yer acik)
    top = w.view(int(xs[0]), y + 13, int(zz[0]), int(xs[-1]), y + 13, int(zz[-1]))[0]
    if k + 12 < interior.shape[0]:
        mz = interior[k + 12]
        rail = mz & (Xg == xc - 2) & (np.abs(Zg - sz) > 1)
        top[rail] = w.id(C.CPANE)
    w.sign(T.SHAFT[0] + 3, y + 3, T.SHAFT[3] + 1, "south", ["BALAYI", "SÜİTİ", "♥", ""], color="black")
