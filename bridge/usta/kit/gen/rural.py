"""Kirsal/doga ureteçleri: farm (ahir, tarlalar, citli agillar, hayvanlar), windmill (yel degirmeni),
treehouse_village (koprulerle bagli agac evler), japanese_garden (Japon bahcesi + cay evi).
Yerel cerceve: on z=0 (-z'ye bakar), +x sag, y=0 zemin."""
from __future__ import annotations

import math

import numpy as np

from . import register
from .. import shapes as SH
from .common import (I, P, S, T, Build, clear_volume, finish_meta, furnish_rooms, get_style, ground_of, light_shaft,
                     partition_walls, perimeter_lamps, random, room_windows, scale_of, settle_on_ground, split_rooms,
                     stair_access, stair_keep)


def _animal(b, kind: str, x: float, y: float, z: float, rnd) -> None:
    if not b.meta.get("_animals"):     # canlilar yalniz acik istekle (params animals=True); Usta guvenlik kurali
        return
    b.add_entity(f"minecraft:{kind}", x + 0.5, y, z + 0.5, yaw=float(rnd.randint(0, 359)), snbt="{PersistenceRequired:1b}")


def _field(b, x0: int, z0: int, x1: int, z1: int, crop: str, axis: str = "x") -> None:
    """Tarla: sulu ark (ortada su) + iki yaninda olgun ekin; kenarda tahta cerceve (ark 4 bloktan uzak kalmaz)."""
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            edge = x in (x0, x1) or z in (z0, z1)
            if edge:
                b.set(x, 0, z, "stripped_oak_log[axis=x]" if z in (z0, z1) else "stripped_oak_log[axis=z]")
                continue
            k = (z - z0) if axis == "x" else (x - x0)
            if k % 9 == 5:
                b.set(x, 0, z, "water")
                b.set(x, -1, z, "dirt")
            else:
                b.set(x, 0, z, "farmland[moisture=7]")
                b.set(x, 1, z, crop)


# ------------------------------------------------------------------ ciftlik
def farm_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return int(params.get("width") or max(44, round(56 * s))), int(params.get("depth") or max(36, round(46 * s)))


def farm(params: dict, ctx: dict | None = None) -> Build:
    """Ciftlik: kirmizi govdeli, beyaz cerceveli mansart catili ahir (ici bolmeli, samanli, hayvanli), tahil silosu,
    rustik ciftlik evi, dort ayri ekinli sulu tarla, citli agillar (inek, koyun, domuz, tavuk), kuyu, korkuluk,
    saman balyalari, cevre citi ve kapi, toprak yollar, fenerler."""
    st = get_style(params, ctx, "rustic")
    FW, FD = farm_dims(params)
    seed = int(params.get("seed", 51))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "çiftlik")
    b.meta["_animals"] = bool(params.get("animals"))
    g = ground_of(ctx, FW, FD)
    clear_volume(b, -2, 1, -2, FW + 1, 24, FD + 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=6)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    cx = FW // 2
    # --- toprak yollar: kapidan ahira ve eve
    P.path(b, [(cx, 0), (cx, FD // 2)], 0, st, w=3, border=False)
    # --- ahir (sag arka): kirmizi govde, beyaz kose/cerceve, mansart cati
    bw, bd = 13, 17
    bx0, bz0 = FW - bw - 4, FD - bd - 4
    bx1, bz1 = bx0 + bw - 1, bz0 + bd - 1
    stb = st.override(wall=[("red_terracotta", 0.7), ("red_concrete", 0.15), ("terracotta", 0.15)],
                      pillar=[("stripped_birch_log", 1.0)], trim=[("birch_planks", 1.0)], frame=[("birch_planks", 1.0)],
                      roof=[("deepslate_tiles", 0.7), ("cobbled_deepslate", 0.3)], floor=[("spruce_planks", 0.6), ("oak_planks", 0.4)])
    stb = stb.with_(motifs=frozenset(m for m in stb.motifs if m not in ("log_corners",)), corner="pillar")
    P.plinth(b, bx0 - 1, bz0 - 1, bx1 + 1, bz1 + 1, 0, stb, h=1)
    shell = P.walls_box(b, bx0, 0, bz0, bx1, 6, bz1, stb, floors=[0], cornice_top=False)
    # buyuk ahir kapisi (on cephe = kuzey yuzu), uzerinde saman kapagi; beyaz X capraz
    gx = (bx0 + bx1) // 2 - 1
    for x in range(gx, gx + 3):
        b.fill(x, 1, bz0, x, 4, bz0, "air")
    b.fill(gx - 1, 5, bz0, gx + 3, 5, bz0, "stripped_birch_log[axis=x]")
    for x in (gx - 1, gx + 3):                         # beyaz kapi kasasi
        b.fill(x, 1, bz0, x, 4, bz0, "stripped_birch_log[axis=y]")
    b.fill(gx + 1, 7, bz0, gx + 1, 8, bz0, "air")
    b.set(gx + 1, 7, bz0 - 1, "hay_block[axis=y]")
    P.roof_mansard(b, bx0 - 1, bz0 - 1, bx1 + 1, bz1 + 1, 7, stb, steep_rows=3)
    for z in range(bz0 + 3, bz1 - 1, 4):
        P.window(b, bx0, 3, z, "west", w=1, h=2, st=stb, kind="shutters")
        P.window(b, bx1, 3, z, "east", w=1, h=2, st=stb, kind="shutters")
    try:
        I.furnish(b, tuple(shell["rooms"][0]), "barn", style="rustic", door=[(gx + 1, 1, bz0)], seed=seed)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"barn: {e}")
    for z in range(bz0 + 4, bz1 - 2, 6):
        _animal(b, "cow", (bx0 + bx1) // 2, 1, z, rnd)
    perimeter_lamps(b, bx0, bz0, bx1, bz1, 4, stb, every=6, skip=[(gx - 1, bz0), (gx + 3, bz0)])
    # --- silo (ahirin solunda)
    sx, sz, sr = bx0 - 4, bz0 + 3, 2
    SH.cylinder((sx, 1, sz), (sx, 13, sz), sr, hollow=True, t=1).put(b, "minecraft:smooth_stone")
    for y in range(4, 14, 3):                          # demir cemberler
        SH.cylinder((sx, y, sz), (sx, y, sz), sr, hollow=True, t=1).put(b, "minecraft:iron_block")
    SH.disk((sx, 0, sz), sr).put(b, "minecraft:stone_bricks")
    P.dome(b, sx, 14, sz, sr, st.override(dome=[("cut_copper", 1.0)]), kind="hemi", drum=0, windows=False, finial=True)
    SH.cylinder((sx, 1, sz), (sx, 13, sz), sr - 1).put(b, "minecraft:hay_block")   # ici dolu (tahil)
    SH.dome((sx, 14, sz), sr).put(b, "minecraft:hay_block", only_empty=True)
    # --- ciftlik evi (sol arka): rustik ev ureteci
    from . import build as gen_build
    hb = gen_build("house", {"size": "küçük", "floors": 1, "style": params.get("house_style", "rustic"), "landscape": False,
                             "clear": False, "width": 11, "depth": 9, "seed": seed + 1}, {"terrain": None})
    (hx0_, hy0_, hz0_), (hx1_, hy1_, hz1_) = hb.bounds()
    hdx = 4 - hx0_ + 1
    hdz = max(FD // 2 + 7 - hz0_, FD - 3 - hz1_)       # agillarin arkasinda, on cephesi kuzeye
    b.merge(hb, hdx, 0, hdz)
    door = hb.meta.get("doors", [{}])[0].get("pos", [5, 1, 0])
    P.path(b, [(cx, FD // 2), (door[0] + hdx, FD // 2), (door[0] + hdx, door[2] + hdz - 2)], 0, st, w=2, border=False)
    P.path(b, [(cx, FD // 2), (gx + 1, FD // 2), (gx + 1, bz0 - 2)], 0, st, w=3, border=False)
    # --- tarlalar (on yari): dort ekin
    crops = ["wheat[age=7]", "carrots[age=7]", "potatoes[age=7]", "beetroots[age=3]"]
    fz0, fz1 = 4, FD // 2 - 5
    fw = (cx - 3 - 3) // 2
    fields = [(3, fz0, 3 + fw - 1, fz1), (3 + fw + 1, fz0, cx - 3, fz1)]
    fields += [(cx + 3, fz0, cx + 3 + fw - 1, fz1), (cx + 3 + fw + 1, fz0, FW - 4, fz1)]
    for k, (x0, z0, x1, z1) in enumerate(fields):
        if x1 - x0 >= 4 and z1 - z0 >= 4:
            _field(b, x0, z0, x1, z1, crops[k % 4], axis="x")
    # korkuluk (tarlada)
    sx_, sz_ = 3 + fw // 2, fz0 + 3
    if b.get(sx_, 1, sz_).split("[")[0].endswith(("wheat", "carrots", "potatoes", "beetroots")):
        b.set(sx_, 0, sz_, "dirt")
        b.set(sx_, 1, sz_, "oak_fence")
        b.set(sx_, 2, sz_, "hay_block[axis=y]")
        b.set(sx_, 3, sz_, "carved_pumpkin[facing=north]")
        b.set(sx_ - 1, 2, sz_, "oak_fence")
        b.set(sx_ + 1, 2, sz_, "oak_fence")
    # --- agillar (orta sol): koyun/domuz; tavuk kumesi
    px0, pz0 = 3, FD // 2 - 2
    px1, pz1 = min(cx - 4, bx0 - 8), FD // 2 + 4
    P.fence_line(b, [(px0, pz0), (px1, pz0), (px1, pz1), (px0, pz1), (px0, pz0)], 1, st, kind="fence", post_every=4,
                 gate_at=(px1, (pz0 + pz1) // 2), lights=False)
    mid = (px0 + px1) // 2
    for z in range(pz0 + 1, pz1):
        b.set(mid, 1, z, "oak_fence")
    b.set(mid, 1, (pz0 + pz1) // 2, "oak_fence_gate[facing=east]")
    for k in range(3):
        _animal(b, "sheep", px0 + 2 + k * 2, 1, pz0 + 2 + k, rnd)
        _animal(b, "pig", mid + 2 + k * 2, 1, pz0 + 2 + k, rnd)
    for (x, z) in ((px0 + 1, pz1 - 1), (mid + 1, pz1 - 1)):
        b.set(x, 1, z, "composter[level=7]")
        b.set(x + 1, 1, z, "cauldron")
    # tavuk kumesi: kucuk sundurma + tavuklar
    kx0, kz0 = cx + 3, FD // 2 - 2
    for x in range(kx0, kx0 + 6):
        for z in (kz0, kz0 + 5):
            b.set(x, 1, z, "oak_fence")
    for z in range(kz0, kz0 + 6):
        for x in (kx0, kx0 + 5):
            b.set(x, 1, z, "oak_fence")
    b.set(kx0, 1, kz0 + 2, "oak_fence_gate[facing=east]")
    P.roof_shed(b, kx0 + 1, kz0 + 3, kx0 + 4, kz0 + 4, 3, st, facing="south")
    b.fill(kx0 + 1, 1, kz0 + 4, kx0 + 4, 2, kz0 + 4, "oak_planks")
    b.set(kx0 + 2, 1, kz0 + 3, "hay_block[axis=y]")
    for k in range(4):
        _animal(b, "chicken", kx0 + 1 + k, 1, kz0 + 1 + (k % 2), rnd)
    # --- kuyu, saman balyalari, fenerler, agaclar
    P.well(b, cx - 3, 0, FD // 2 + 7, st)
    for (x, z, h) in ((bx0 - 2, bz1 - 2, 2), (bx0 - 3, bz1 - 3, 1), (bx0 - 2, bz1 - 4, 1)):
        for y in range(1, h + 1):
            b.set(x, y, z, "hay_block[axis=y]")
    for (x, z) in ((cx - 2, FD // 2 - 2), (cx + 2, FD // 2 - 2), (cx - 2, FD // 2 + 6), (gx + 4, bz0 - 3)):
        if b.get_id(x, 1, z) <= 1:
            P.lamp_post(b, x, 1, z, st, h=3)
    for (x, z) in ((2, FD - 3), (FW - 3, 2), (2, 2), (FW - 3, FD // 2)):
        if b.get_id(x, 1, z) <= 1:
            try:
                T.tree(b, x, 0, z, species=rnd.choice(["oak", "birch"]), size="medium", seed=rnd.randint(0, 9999))
            except Exception:
                pass
    # --- cevre citi + kapi
    P.fence_line(b, [(0, 0), (FW - 1, 0), (FW - 1, FD - 1), (0, FD - 1), (0, 0)], 1, st, kind="fence", post_every=4,
                 gate_at=(cx, 0), gate_w=3, lights=True)
    return finish_meta(b, "farm", st, {"floors": [0], "barn": [bx0, bz0, bx1, bz1], "fields": [list(f) for f in fields]})


# ------------------------------------------------------------------ yel degirmeni
def windmill_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return max(21, round(25 * s)), max(21, round(25 * s))


def windmill(params: dict, ctx: dict | None = None) -> Build:
    """Yel degirmeni: tas kaide + kademeli daralan ahsap govde, konik baslik, on yuzde dort kanatli pervane
    (kutuk kollar + yun yelken), kapi, pencereler, icinde degirmen tasi/cuval/variller; yaninda un ambari ve tarla."""
    st = get_style(params, ctx, "rustic")
    FW, FD = windmill_dims(params)
    seed = int(params.get("seed", 61))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "yel değirmeni")
    g = ground_of(ctx, FW, FD)
    cx, cz = FW // 2, FD // 2 + 2
    H = int(params.get("height") or 16)
    clear_volume(b, 0, 1, 0, FW - 1, H + 16, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=4)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    # govde: alt 5 sira tas (r=5), ustte ahsap daralan (r 4 -> 3)
    SH.disk((cx, 0, cz), 5).put(b, "minecraft:stone_bricks")
    for y in range(1, H + 1):
        r = 5 if y <= 5 else (4 if y <= 11 else 3)
        mat = ("cobblestone" if (y + cx) % 3 else "mossy_cobblestone") if y <= 5 else ("spruce_planks" if y % 4 else "stripped_spruce_log[axis=y]")
        SH.cylinder((cx, y, cz), (cx, y, cz), r, hollow=True, t=1).put(b, f"minecraft:{mat}")
        if y in (6, 12):   # kademe: ust disk saçak
            SH.ring((cx, y, cz), r + 2, r, 1).put(b, "minecraft:spruce_slab[type=bottom]")
    for y in (5, 11):   # ara katlar: doner merdivenin 3x3 boslugu acik
        (SH.disk((cx, y, cz), 4 if y == 5 else 3) - SH.box(cx - 1, y, cz - 1, cx + 1, y, cz + 1)).put(b, "minecraft:spruce_planks")
    P.spiral_stair(b, cx, 1, cz, H - 2, st, r=1, clear=False)
    # konik baslik
    P.spire(b, cx, H + 1, cz, 4, 7, st.override(roof=[("dark_oak_planks", 0.6), ("spruce_planks", 0.4)]), role="roof", flare=True)
    SH.cone((cx, H + 1, cz), 4, 7).put(b, "minecraft:dark_oak_planks", only_empty=True)
    SH.disk((cx, H, cz), 3).put(b, "minecraft:spruce_planks")
    P.stair_hatch(b, cx, cz, H)
    # pervane: on yuzde (z kucuk), merkez kutuk + dort kol + yun yelken
    hz = cz - 4 - 1
    hy = H - 1
    b.fill(cx, hy, hz, cx, hy, cz - 3, "stripped_dark_oak_log[axis=z]")
    L = 9
    for (dx, dy) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        for k in range(1, L + 1):
            X, Y = cx + dx * k, hy + dy * k
            if Y < 2:
                break
            b.set(X, Y, hz, "dark_oak_fence")
            if k >= 3:   # yelken: kolun bir yaninda
                sx_, sy_ = X - dx, Y
                if b.get_id(sx_, sy_, hz) <= 1:
                    b.set(sx_, sy_, hz, "white_wool" if k % 2 else "light_gray_wool")
    # kapi + pencereler
    from .common import tower_door
    tower_door(b, cx, cz, 5, 1, "south", st, w=1)
    for (dx, dz, face) in ((5, 0, "east"), (-5, 0, "west")):
        P.window(b, cx + dx, 2, cz + dz, face, w=1, h=2, st=st, kind="shutters")
    for (dx, dz, face) in ((4, 0, "east"), (-4, 0, "west"), (0, 4, "south")):
        b.set(cx + dx, 8, cz + dz, "glass_pane")
        b.set(cx + dx, 9, cz + dz, "glass_pane")
    # ic: degirmen tasi, cuvallar, variller
    b.set(cx - 3, 1, cz, "grindstone[face=floor,facing=east]")
    b.set(cx - 3, 1, cz - 1, "barrel[facing=up]")
    b.set(cx - 3, 1, cz + 1, "barrel[facing=up]")
    b.set(cx + 3, 1, cz - 2, "white_wool")
    b.set(cx + 3, 1, cz - 1, "hay_block[axis=y]")
    b.set(cx - 2, 6, cz, "stonecutter[facing=east]")
    light_shaft(b, cx, cz, 2, H - 2, r=3, every=4, level=13)
    # un ambari (sag) + kucuk bugday tarlasi (sol)
    ax0, az0 = cx + 6, cz - 2
    sh = P.walls_box(b, ax0, 0, az0, ax0 + 5, 5, az0 + 5, st, floors=[0], cornice_top=False)
    P.door(b, ax0 + 2, 1, az0 + 5, "south", st, w=1)
    P.window(b, ax0 + 5, 2, az0 + 2, "east", w=2, h=2, st=st, kind="shutters")
    P.window(b, ax0 + 2, 2, az0, "north", w=2, h=2, st=st, kind="shutters")
    P.roof(b, ax0 - 1, az0 - 1, ax0 + 6, az0 + 6, 6, st, kind="gable")
    for k in range(3):
        b.set(ax0 + 1 + k, 1, az0 + 1, "barrel[facing=up]")
    b.set(ax0 + 4, 1, az0 + 1, "hay_block[axis=y]")
    P.hanging_lamp(b, ax0 + 2, 5, az0 + 3, st)
    _field(b, 2, 2, cx - 7, FD - 3, "wheat[age=7]", axis="z")
    P.path(b, [(cx, FD - 1), (cx, cz + 8)], 0, st, w=3, border=False)
    for (x, z) in ((cx - 3, cz + 7), (cx + 3, cz + 7)):
        P.lamp_post(b, x, 1, z, st, h=3)
    return finish_meta(b, "windmill", st, {"floors": [0, 5, 11], "tower": [cx, cz, H]})


# ------------------------------------------------------------------ agac evler koyu
def treehouse_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return max(40, round(52 * s)), max(40, round(52 * s))


def _giant_tree(b, x: int, z: int, top: int, crown_y: int, rnd, wood: str = "oak", leaves: str = "oak_leaves") -> None:
    """2x2 govdeli dev agac: kok yayilimi, govde top'a kadar, dallar, crown_y'den baslayan genis yaprak tacı."""
    log = f"{wood}_log[axis=y]"
    for dx in (0, 1):
        for dz in (0, 1):
            b.fill(x + dx, 1, z + dz, x + dx, top, z + dz, log)
    for (dx, dz, ax) in ((-1, 0, "x"), (2, 1, "x"), (0, -1, "z"), (1, 2, "z"), (-1, 1, "x"), (2, 0, "x")):
        b.set(x + dx, 1, z + dz, f"{wood}_log[axis={ax}]")
    for k in range(4):                                  # dallar
        ang = k * math.pi / 2 + rnd.random() * 0.6
        for t in range(1, 5):
            X = int(round(x + 0.5 + math.cos(ang) * t))
            Z = int(round(z + 0.5 + math.sin(ang) * t))
            Y = crown_y + t // 2
            b.set(X, Y, Z, f"{wood}_log[axis={'x' if abs(math.cos(ang)) > 0.7 else 'z'}]")
    R = 6
    blob = SH.blob((x + 0.5, crown_y + 3, z + 0.5), R, rough=0.35, seed=rnd.randint(0, 999), squash=0.65)
    blob.put(b, f"minecraft:{leaves}[persistent=true]", only_empty=True)


def treehouse_village(params: dict, ctx: dict | None = None) -> Build:
    """Ormanda agac ev koyu: dev agaclarin govdesi cevresinde tahta platformlar, ustlerinde kucuk kulubeler,
    platformlari baglayan asma kopruler (cit korkuluklu, fenerli), govdeye sarili merdivenler, yerde kamp atesi
    meydani, cevrede orman ve calilar."""
    st = get_style(params, ctx, "rustic")
    FW, FD = treehouse_dims(params)
    seed = int(params.get("seed", 71))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "ağaç ev köyü")
    g = ground_of(ctx, FW, FD)
    clear_volume(b, 0, 1, 0, FW - 1, 36, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=4)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    n = int(params.get("houses") or 5)
    cx, cz = FW // 2, FD // 2
    pts = []
    for k in range(n):
        ang = 2 * math.pi * k / n + 0.4
        rr = min(FW, FD) * 0.3
        pts.append((int(cx + math.cos(ang) * rr), int(cz + math.sin(ang) * rr)))
    plats = []
    for k, (x, z) in enumerate(pts):
        py = 9 + (k % 3) * 2                           # platform yuksekligi (kademeli)
        top = py + 7
        _giant_tree(b, x, z, top, py + 5, rnd, wood="oak" if k % 2 else "dark_oak",
                    leaves="oak_leaves" if k % 2 else "dark_oak_leaves")
        pr = 4
        # platform (2x2 govdenin cevresi), kenar kirisi, cit korkuluk
        for X in range(x - pr, x + pr + 2):
            for Z in range(z - pr, z + pr + 2):
                if (X - x - 0.5) ** 2 + (Z - z - 0.5) ** 2 <= (pr + 0.6) ** 2 and b.get_id(X, py, Z) <= 1:
                    b.set(X, py, Z, "spruce_planks")
        for X in range(x - pr - 1, x + pr + 3):
            for Z in range(z - pr - 1, z + pr + 3):
                d2 = (X - x - 0.5) ** 2 + (Z - z - 0.5) ** 2
                if (pr + 0.6) ** 2 < d2 <= (pr + 1.5) ** 2 and b.get_id(X, py + 1, Z) <= 1:
                    b.set(X, py, Z, "spruce_planks")
                    b.set(X, py + 1, Z, "spruce_fence")
        # destek payandalari (govdeden platform altina)
        for (dx, dz, f) in ((-2, 0, "east"), (3, 1, "west"), (0, -2, "south"), (1, 3, "north")):
            b.set(x + dx, py - 1, z + dz, f"spruce_stairs[facing={f},half=top]")
        # kulube: platform uzerinde govdenin yaninda 5x5
        hx0, hz0 = x - 3, z - 3
        side = k % 4
        if side == 0:
            hx0, hz0 = x + 2, z - 2
        elif side == 1:
            hx0, hz0 = x - 4, z - 2
        elif side == 2:
            hx0, hz0 = x - 1, z + 2
        else:
            hx0, hz0 = x - 1, z - 4
        hw = 4
        for X in range(hx0, hx0 + hw):
            for Z in range(hz0, hz0 + hw):
                if b.get_id(X, py, Z) <= 1:
                    b.set(X, py, Z, "spruce_planks")
        sh = SH.shell_box(hx0, py + 1, hz0, hx0 + hw - 1, py + 3, hz0 + hw - 1, t=1, top=False, bottom=False)
        for (X, Y, Z) in sh.coords().tolist():
            if b.get_id(X, Y, Z) <= 1 or "leaves" in str(b.get(X, Y, Z)):
                b.set(X, Y, Z, "spruce_planks" if Y != py + 2 or (X + Z) % 3 else "glass_pane")
        for X in range(hx0 - 1, hx0 + hw + 1):
            for Z in range(hz0 - 1, hz0 + hw + 1):
                b.set(X, py + 4, Z, "spruce_slab[type=bottom]")
        b.fill(hx0 + 1, py + 4, hz0 + 1, hx0 + hw - 2, py + 4, hz0 + hw - 2, "spruce_planks")
        # kulube kapisi govdeye bakan yuzde
        dxs = [(hx0 + hw // 2, hz0) if hz0 > z else (hx0 + hw // 2, hz0 + hw - 1) if hz0 + hw - 1 < z else
               (hx0, hz0 + hw // 2) if hx0 > x else (hx0 + hw - 1, hz0 + hw // 2)]
        for (DX, DZ) in dxs:
            b.fill(DX, py + 1, DZ, DX, py + 2, DZ, "air")
        b.set(hx0 + hw - 2, py + 1, hz0 + hw - 2, "barrel[facing=up]")
        b.set(hx0 + 1, py + 1, hz0 + hw - 2, "crafting_table")
        b.set(hx0 + hw // 2, py + 3, hz0 + hw // 2, "lantern[hanging=true]")
        # govdeye sarilan merdiven: yerden platforma
        steps = []
        ring = [(-1, -1), (0, -1), (1, -1), (2, -1), (2, 0), (2, 1), (2, 2), (1, 2), (0, 2), (-1, 2), (-1, 1), (-1, 0)]
        for i in range(py - 1):
            u, v = ring[i % len(ring)]
            nu, nv = ring[(i + 1) % len(ring)]
            X, Z = x + u, z + v
            ddx, ddz = nu - u, nv - v
            f = "east" if ddx > 0 else "west" if ddx < 0 else "south" if ddz > 0 else "north"
            b.set(X, 1 + i, Z, f"spruce_stairs[facing={f},half=bottom]")
            for hh in (1, 2, 3):
                if "leaves" in str(b.get(X, 1 + i + hh, Z)) or b.get_id(X, 1 + i + hh, Z) <= 1:
                    if not str(b.get(X, 1 + i + hh, Z)).endswith("_planks"):
                        b.set(X, 1 + i + hh, Z, "air")
            steps.append((X, 1 + i, Z))
        # platforma cikis: son 3 basamagin ustundeki platform hucreleri acik (bas boslugu), kenarina korkuluk
        for (X, Y, Z) in steps[-3:]:
            for hh in (1, 2, 3):
                if Y + hh <= py + 1 and b.get_id(X, Y + hh, Z) > 1 and not str(b.get(X, Y + hh, Z)).split("[")[0].endswith("_stairs"):
                    if Y + hh == py or Y + hh < py or "leaves" in str(b.get(X, Y + hh, Z)):
                        b.set(X, Y + hh, Z, "air")
        # platform alti ve govde dibi isiklar (golgede canavar dogmasin)
        for (X, Z) in ((x - pr + 1, z), (x + pr, z + 1), (x, z + pr), (x + 1, z - pr + 1)):
            if b.is_solid(X, py, Z) and b.get_id(X, py - 1, Z) <= 1:
                P.hanging_lamp(b, X, py, Z, st, length=1)
        for (X, Z) in ((x - 3, z - 3), (x + 4, z + 4)):
            if b.get_id(X, 1, Z) <= 1:
                P.lamp_post(b, X, 1, Z, st, h=3)
        for (X, Z) in ((x - pr, z), (x + pr + 1, z + 1), (x, z + pr + 1), (x + 1, z - pr)):
            if b.get_id(X, py + 1, Z) <= 1:
                b.set(X, py + 1, Z, "lantern")
        plats.append((x, z, py, pr))
    # asma kopruler: komsu platformlar arasi (cember sirasiyla)
    for k in range(n):
        x0_, z0_, y0_, r0 = plats[k]
        x1_, z1_, y1_, r1 = plats[(k + 1) % n]
        ax, az = x0_ + 0.5, z0_ + 0.5
        bx, bz = x1_ + 0.5, z1_ + 0.5
        dist = math.hypot(bx - ax, bz - az)
        ux, uz = (bx - ax) / dist, (bz - az) / dist
        sx_, sz_ = ax + ux * (r0 + 1.6), az + uz * (r0 + 1.6)
        ex_, ez_ = bx - ux * (r1 + 1.6), bz - uz * (r1 + 1.6)
        L = math.hypot(ex_ - sx_, ez_ - sz_)
        steps_n = max(2, int(L * 2))
        px_, pz_ = -uz, ux
        last = None
        for i in range(steps_n + 1):
            t = i / steps_n
            X = sx_ + (ex_ - sx_) * t
            Z = sz_ + (ez_ - sz_) * t
            sag = math.sin(math.pi * t) * min(2.0, L / 10)
            Y = int(round(y0_ + (y1_ - y0_) * t - sag))
            for w_ in (-1, 0, 1):
                XX, ZZ = int(math.floor(X + px_ * w_)), int(math.floor(Z + pz_ * w_))
                if b.get_id(XX, Y, ZZ) <= 1 or "leaves" in str(b.get(XX, Y, ZZ)):
                    b.set(XX, Y, ZZ, "spruce_slab[type=top]" if w_ == 0 else "spruce_planks")
                for hh in (1, 2):
                    if "leaves" in str(b.get(XX, Y + hh, ZZ)):
                        b.set(XX, Y + hh, ZZ, "air")
            for w_ in (-2, 2):
                XX, ZZ = int(math.floor(X + px_ * w_)), int(math.floor(Z + pz_ * w_))
                if b.get_id(XX, Y + 1, ZZ) <= 1:
                    b.set(XX, Y, ZZ, "spruce_planks")
                    b.set(XX, Y + 1, ZZ, "spruce_fence")
        # kopru ucunda platform korkulugunu ac
        for (X0, Z0, Y0) in ((sx_, sz_, y0_), (ex_, ez_, y1_)):
            for w_ in (-1, 0, 1):
                XX, ZZ = int(math.floor(X0 + px_ * w_ - ux * 0.8)), int(math.floor(Z0 + pz_ * w_ - uz * 0.8))
                if str(b.get(XX, Y0 + 1, ZZ)).endswith("fence"):
                    b.set(XX, Y0 + 1, ZZ, "air")
    # yer: kamp atesi meydani, kutuk banklar, calilar, orman zemini
    SH.disk((cx, 0, cz), 4).put(b, "minecraft:coarse_dirt")
    b.set(cx, 1, cz, "campfire[lit=true,facing=north]")
    for (dx, dz, ax) in ((-3, 0, "z"), (3, 0, "z"), (0, -3, "x"), (0, 3, "x")):
        b.set(cx + dx, 1, cz + dz, f"stripped_oak_log[axis={ax}]")
    for _ in range(int(FW * FD * 0.012)):
        X, Z = rnd.randint(1, FW - 2), rnd.randint(1, FD - 2)
        if b.get_id(X, 1, Z) <= 1 and all(math.hypot(X - p[0], Z - p[1]) > 7 for p in plats) and math.hypot(X - cx, Z - cz) > 6:
            r_ = rnd.random()
            if r_ < 0.15:
                try:
                    T.bush(b, X, 0, Z, kind=rnd.choice(["oak", "azalea", "berry"]), size="small", seed=rnd.randint(0, 999))
                except Exception:
                    pass
            elif r_ < 0.75:
                b.set(X, 1, Z, rnd.choice(["fern", "short_grass", "short_grass", "brown_mushroom", "dandelion"]))
    for (x, z) in ((cx - 5, cz - 5), (cx + 5, cz + 5)):
        P.lamp_post(b, x, 1, z, st, h=3)
    return finish_meta(b, "treehouse_village", st, {"floors": [0] + sorted({p[2] for p in plats}), "platforms": plats})


# ------------------------------------------------------------------ Japon bahcesi + cay evi
def japanese_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return max(34, round(44 * s)), max(30, round(38 * s))


def japanese_garden(params: dict, ctx: dict | None = None) -> Build:
    """Japon bahcesi ve cay evi: yukseltilmis ahsap cay evi (engawa verandasi, shoji paneller, kavisli cati,
    tatamili cay odasi), koi golu (nilufer, kayalar), kirmizi kemerli kopru, basamak taslari, tas fenerler (toro),
    kiraz ve cam agaclari, bambu korusu, tirmikli cakil zen bahcesi, bambu cit, kirmizi torii kapisi."""
    st = get_style(params, ctx, "japanese")
    FW, FD = japanese_dims(params)
    seed = int(params.get("seed", 81))
    rnd = random.Random(seed)
    b = Build(params.get("name") or "Japon bahçesi")
    g = ground_of(ctx, FW, FD)
    clear_volume(b, 0, 1, 0, FW - 1, 16, FD - 1)
    settle_on_ground(b, g, 0, 0, FW - 1, FD - 1, st, blend=4)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    for x in range(FW):
        for z in range(FD):
            if rnd.random() < 0.25:
                b.set(x, 0, z, "moss_block")
    cx = FW // 2
    # --- cay evi (arka orta): 9x7, yukseltilmis doseme (y=1), engawa
    tw, td = 11, 9
    tx0, tz0 = cx - tw // 2, FD - td - 4
    tx1, tz1 = tx0 + tw - 1, tz0 + td - 1
    for X in range(tx0 - 1, tx1 + 2):              # tas temel ayaklari + doseme
        for Z in range(tz0 - 2, tz1 + 2):
            b.set(X, 1, Z, "spruce_planks" if not (X in (tx0 - 1, tx1 + 1) or Z in (tz0 - 2, tz1 + 1)) else "stripped_spruce_wood[axis=y]")
    for (X, Z) in ((tx0 - 1, tz0 - 2), (tx1 + 1, tz0 - 2), (tx0 - 1, tz1 + 1), (tx1 + 1, tz1 + 1), (cx, tz0 - 2)):
        b.set(X, 0, Z, "polished_andesite")
    stj = st.override(wall=[("white_concrete", 0.5), ("calcite", 0.5)])
    sh = SH.shell_box(tx0, 2, tz0, tx1, 5, tz1, t=1, top=False, bottom=False)
    sh.put(b, "minecraft:birch_planks")
    for X in range(tx0, tx1 + 1):              # shoji: ust sira acik kagit (beyaz cam), dikmeler koyu
        for Z in (tz0, tz1):
            if (X - tx0) % 3 == 0:
                b.fill(X, 2, Z, X, 5, Z, "stripped_dark_oak_log[axis=y]")
            else:
                b.fill(X, 3, Z, X, 4, Z, "white_stained_glass_pane")
    for Z in range(tz0, tz1 + 1):
        for X in (tx0, tx1):
            if (Z - tz0) % 3 == 0:
                b.fill(X, 2, Z, X, 5, Z, "stripped_dark_oak_log[axis=y]")
            else:
                b.fill(X, 3, Z, X, 4, Z, "white_stained_glass_pane")
    b.fill(tx0, 2, tz0, tx1, 2, tz0, "stripped_dark_oak_log[axis=x]")
    b.fill(cx - 1, 2, tz0, cx + 1, 4, tz0, "air")          # giris (surgulu kapi acik)
    b.fill(tx0 + 1, 6, tz0 + 1, tx1 - 1, 6, tz1 - 1, "spruce_planks")
    P.roof_curved(b, tx0 - 2, tz0 - 3, tx1 + 2, tz1 + 2, 6, st, kind="hip")
    for (X, Z) in ((tx0 - 1, tz0 - 2), (tx1 + 1, tz0 - 2)):   # engawa direkleri
        b.fill(X, 2, Z, X, 5, Z, "stripped_dark_oak_log[axis=y]")
    P.stepping_stones(b, [(cx, 2), (cx - 3, FD // 3), (cx + 2, FD // 2), (cx, tz0 - 4)], 0, st, spacing=2, seed=seed)
    try:
        I.furnish(b, (tx0 + 1, 2, tz0 + 1, tx1 - 1, 5, tz1 - 1), "tea_room", style="japanese", door=[(cx, 2, tz0)], seed=seed)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"tea_room: {e}")
    b.set(cx, 1, tz0 - 3, "spruce_stairs[facing=south,half=bottom]")
    b.set(cx - 1, 1, tz0 - 3, "spruce_stairs[facing=south,half=bottom]")
    b.set(cx + 1, 1, tz0 - 3, "spruce_stairs[facing=south,half=bottom]")
    # --- koi golu (sol on), kayalar, nilufer
    lx, lz, rx, rz = cx - FW // 4, FD // 3 + 1, max(5, FW // 6), max(4, FD // 7)
    pond = []
    for X in range(lx - rx - 1, lx + rx + 2):
        for Z in range(lz - rz - 1, lz + rz + 2):
            d = ((X - lx) / (rx + 0.5)) ** 2 + ((Z - lz) / (rz + 0.5)) ** 2 + 0.15 * math.sin(X * 0.9 + Z)
            if d <= 1.0:
                b.set(X, 0, Z, "water")
                b.set(X, -1, Z, "water" if d < 0.6 else "mud")
                b.set(X, -2, Z, "mud")
                pond.append((X, Z))
                if d < 0.6 and rnd.random() < 0.08:
                    b.set(X, 1, Z, "lily_pad")
            elif d <= 1.4:
                gb = rnd.choice(["mossy_cobblestone", "andesite", "moss_block", "gravel"])
                b.set(X, 0, Z, gb)
                if rnd.random() < 0.12:
                    b.set(X, 1, Z, "fern" if gb == "moss_block" else rnd.choice(["andesite_wall", "mossy_cobblestone_wall"]))
    # kirmizi kemerli kopru golun ortasindan (x boyunca)
    bz = lz
    bx0, bx1 = lx - rx - 1, lx + rx + 1
    span = bx1 - bx0
    for X in range(bx0, bx1 + 1):
        t = (X - bx0) / max(1, span)
        Y = 1 + int(round(math.sin(math.pi * t) * 1.6))
        for dz in (-1, 0, 1):
            b.set(X, Y, bz + dz, "crimson_planks" if dz == 0 else "crimson_slab[type=top]")
        for dz in (-2, 2):
            b.set(X, Y, bz + dz, "crimson_planks")
            b.set(X, Y + 1, bz + dz, "crimson_fence")
    for X in (bx0, bx1):
        for dz in (-2, 2):
            b.set(X, 2, bz + dz, "crimson_fence")
            b.set(X, 3, bz + dz, "lantern")
    # --- zen bahcesi (sag on): tirmikli cakil + kaya adalari
    zx0, zz0, zx1, zz1 = cx + 3, 3, FW - 4, FD // 2 - 1
    for X in range(zx0, zx1 + 1):
        for Z in range(zz0, zz1 + 1):
            edge = X in (zx0, zx1) or Z in (zz0, zz1)
            b.set(X, 0, Z, "polished_andesite" if edge else ("gravel" if (Z - zz0) % 2 else "light_gray_concrete_powder"))
    for (X, Z, s_) in ((zx0 + 4, zz0 + 4, 2), (zx1 - 4, zz1 - 3, 1), ((zx0 + zx1) // 2 + 2, zz0 + 2, 1)):
        SH.blob((X + 0.5, 1, Z + 0.5), s_ + 0.8, rough=0.4, seed=X + Z, squash=0.7).put(b, "minecraft:andesite")
        b.set(X, 1, Z, "mossy_cobblestone")
    # --- toro fenerleri, bitkiler, agaclar, bambu
    for (X, Z) in ((cx - 3, 4), (cx + 3, FD // 2 + 2), (lx + rx + 3, lz - rz - 2), (tx0 - 3, tz0 - 2), (tx1 + 3, tz0 - 2)):
        if 1 <= X < FW - 1 and 1 <= Z < FD - 1 and b.get_id(X, 1, Z) <= 1:
            P.lamp_post(b, X, 1, Z, st, h=3, kind="toro")
    for (X, Z, sp) in ((3, FD - 5, "cherry"), (FW - 5, FD - 5, "cherry"), (lx - rx - 4, lz + rz + 3, "pine"),
                       (lx + rx + 4, lz + rz + 4, "cherry"), (FW - 4, FD // 2 + 2, "pine")):
        if 2 <= X <= FW - 3 and 2 <= Z <= FD - 3 and b.get_id(X, 1, Z) <= 1:
            try:
                T.tree(b, X, 0, Z, species=sp, size="medium", seed=rnd.randint(0, 9999))
            except Exception:
                pass
    for _ in range(40):                                         # bambu korusu (sol arka)
        X, Z = rnd.randint(2, tx0 - 4), rnd.randint(FD // 2 + 4, FD - 3)
        if b.get_id(X, 1, Z) <= 1 and str(b.get(X, 0, Z)).split("[")[0].endswith(("grass_block", "moss_block")):
            hgt = rnd.randint(4, 9)
            for y in range(1, hgt + 1):
                b.set(X, y, Z, "bamboo[age=1,leaves=" + ("large" if y >= hgt - 1 else "small" if y >= hgt - 3 else "none") + ",stage=0]")
    for _ in range(int(FW * FD * 0.03)):
        X, Z = rnd.randint(1, FW - 2), rnd.randint(1, FD - 2)
        if b.get_id(X, 1, Z) <= 1 and str(b.get(X, 0, Z)).split("[")[0].endswith(("grass_block", "moss_block")):
            b.set(X, 1, Z, rnd.choice(["fern", "short_grass", "azure_bluet", "pink_petals[flower_amount=3,facing=north]", "moss_carpet"]))
    # --- bambu cit + torii kapisi (on orta)
    for X in range(FW):
        for Z in (0, FD - 1):
            if not (Z == 0 and cx - 2 <= X <= cx + 2):
                b.set(X, 1, Z, "bamboo_fence")
    for Z in range(FD):
        for X in (0, FW - 1):
            b.set(X, 1, Z, "bamboo_fence")
    for X in (cx - 2, cx + 2):
        b.fill(X, 1, 0, X, 6, 0, "red_concrete")
        b.set(X, 0, 0, "polished_blackstone")
    b.fill(cx - 3, 5, 0, cx + 3, 5, 0, "red_concrete")
    b.fill(cx - 4, 7, 0, cx + 4, 7, 0, "black_concrete")
    b.set(cx - 4, 7, 0, "blackstone_stairs[facing=east,half=top]")
    b.set(cx + 4, 7, 0, "blackstone_stairs[facing=west,half=top]")
    b.fill(cx - 3, 6, 0, cx + 3, 6, 0, "red_concrete")
    b.set(cx, 6, 0, "red_concrete")
    b.fill(cx - 1, 6, 0, cx + 1, 6, 0, "red_concrete")
    P.path(b, [(cx, 0), (cx, 2)], 0, st, w=3, border=False)
    return finish_meta(b, "japanese_garden", st, {"floors": [1], "teahouse": [tx0, tz0, tx1, tz1], "pond": [lx, lz, rx, rz]})


register("farm", farm, farm_dims,
         "Çiftlik: kırmızı gövdeli mansart çatılı ahır (bölmeli, samanlı, hayvanlı), silo, çiftlik evi, sulu ekin tarlaları, çitli ağıllar (inek, koyun, domuz, tavuk), korkuluk, kuyu, çevre çiti",
         {"size": "orta|büyük", "house_style": "rustic", "animals": "True: inek/koyun/domuz/tavuk (yalnız oyuncu açıkça isterse)"}, lambda p: p.get("name") or "çiftlik")
register("windmill", windmill, windmill_dims,
         "Yel değirmeni: taş kaide + daralan ahşap gövde, konik başlık, dört kanatlı yelken pervanesi, değirmen içi; un ambarı ve buğday tarlası",
         {"height": "gövde yüksekliği"}, lambda p: p.get("name") or "yel değirmeni")
register("treehouse_village", treehouse_village, treehouse_dims,
         "Ağaç ev köyü: dev ağaçlarda platformlar ve kulübeler, aralarında asma köprüler, gövdeye sarılı merdivenler, kamp ateşi meydanı, orman zemini",
         {"houses": "3-7", "size": "orta|büyük"}, lambda p: p.get("name") or "ağaç ev köyü")
register("japanese_garden", japanese_garden, japanese_dims,
         "Japon bahçesi + çay evi: engawalı yükseltilmiş çay evi (shoji, kavisli çatı, tatami odası), koi gölü, kırmızı kemerli köprü, taş fenerler, kiraz/çam, bambu, zen çakıl bahçesi, torii",
         {"size": "orta|büyük"}, lambda p: p.get("name") or "Japon bahçesi")
