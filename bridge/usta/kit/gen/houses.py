"""Konut ureteclei: house (her tarzda ev), modern_villa, ottoman_konak, japanese_teahouse."""
from __future__ import annotations

from .common import (Build, I, P, S, T, clear_volume, finish_meta, furnish_rooms, get_style, stair_access, stair_keep, room_windows, ground_of, landscape_ring,
                     partition_walls, random, scale_of, settle_on_ground, split_rooms)


# ------------------------------------------------------------------ genel ev
def house_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    w = int(params.get("width") or max(9, round(15 * s)))
    d = int(params.get("depth") or max(7, round(11 * s)))
    floors = int(params.get("floors") or (1 if s < 0.8 else 2 if s < 1.8 else 3))
    if floors >= 2:   # duz ic merdiven (giris + kat yuksekligi kadar basamak + cikis) evin icine sigsin; yoksa cikis on duvari deler
        d = max(d, get_style(params, None, "rustic").floor_h + 4)
    return w, d


def house(params: dict, ctx: dict | None = None) -> Build:
    st = get_style(params, ctx, "rustic")
    w, d = house_dims(params)
    s = scale_of(params, 1.0)
    floors = int(params.get("floors") or (1 if s < 0.8 else 2 if s < 1.8 else 3))
    seed = int(params.get("seed", 7))
    b = Build(params.get("name") or f"{st.name.split('@')[0]} ev")
    g = ground_of(ctx, w, d)
    fh = st.floor_h
    top = floors * fh
    if params.get("clear", True):       # sehir parselinde komsulari silmesin
        clear_volume(b, -6, 1, -14, w + 5, top + 14, d + 6)
    settle_on_ground(b, g, -2, -3, w + 1, d + 1, st)
    P.plinth(b, -1, -1, w, d, 0, st, h=1)
    shell = P.walls_box(b, 0, 0, 0, w - 1, top - 1, d - 1, st)
    door_x = w // 2 - (1 if w % 2 == 0 else 0)
    door_w = 2 if w >= 13 else 1
    P.door(b, door_x, 1, 0, "north", st, w=door_w, steps=1)
    avoid = [(door_x - 1, door_x + door_w)]
    jet = shell["outer"][1] < 0          # ortacag cikmasi: ust katlarin duvari 1 blok disarida
    for fi, fy in enumerate(shell["floors"]):
        e = 1 if (jet and fi > 0) else 0
        wy = fy + 2
        P.window_row(b, -e, wy, -e, "north", w + 2 * e, st, avoid=avoid if fi == 0 else
                     ([(door_x - 2, door_x + door_w + 1)] if (fi == 1 and floors >= 2 and w >= 11) else ()))
        P.window_row(b, -e, wy, d - 1 + e, "south", w + 2 * e, st)
        P.window_row(b, -e, wy, -e, "west", d + 2 * e, st)
        P.window_row(b, w - 1 + e, wy, -e, "east", d + 2 * e, st)
    if floors >= 2 and w >= 11:
        P.balcony(b, door_x - 1, shell["floors"][1], -1 if jet else 0, "north", w=door_w + 2, depth=2, st=st, door_w=door_w)
    tr = shell["rooms"][-1]               # en ust kat tavani (cati arasi dosemesi): asma lamba/gomme isik tutunsun
    st.fill(b, tr[0], top, tr[2], tr[3], top, tr[5], "ceiling")
    rk = params.get("roof") or st.roof_kind
    ox0, oz0, ox1, oz1 = shell["outer"]
    roof = P.roof(b, ox0 - 1, oz0 - 1, ox1 + 1, oz1 + 1, top, st, kind=rk, min_eave_y=3)   # sacak altinda 2 blok yol
    if st.has("chimney") or st.name.split("@")[0] in ("rustic", "medieval", "scandinavian"):
        P.chimney(b, w - 3, top - 1, d - 4, roof.get("top", top + 4) - top + 3, st)
    # ic mekan
    doors = []
    rooms_all = []
    plan = [["foyer", "living_room", "kitchen", "dining_room"], ["master_bedroom", "bathroom", "kids_room", "study"],
            ["library", "guest_room", "attic"]]
    # merdivenler (katlar arasi, arka sag kose): kat kat ust uste binmesin, tek katlarda 2 sutun batida
    stairs_at = [(w - 3 - 2 * (fi % 2), d - 3) for fi in range(len(shell["floors"]) - 1)]

    def near_stairs(f: int) -> set:
        """f. kattaki merdiven ve boslugu (+1 komsu): bolme kapisi buraya acilmasin (korkuluk kapiyi kapatmasin)."""
        out = set()
        for fi in (f - 1, f):
            if 0 <= fi < len(stairs_at):
                sx_, sz_ = stairs_at[fi]
                out |= {(sx_ + dx, z) for dx in (-1, 0, 1) for z in range(sz_ - fh - 1, sz_ + 2)}
        return out
    for fi, rb in enumerate(shell["rooms"]):
        x0, y0, z0, x1, y1, z1 = rb
        kinds = plan[min(fi, 2)]
        n = 4 if (x1 - x0) * (z1 - z0) > 120 else 2 if (x1 - x0) * (z1 - z0) > 40 else 1
        rooms = split_rooms(x0, z0, x1, z1, y0, y1 - y0 + 1, kinds[:n], avoid_x=range(door_x - 1, door_x + door_w + 1))
        doors += partition_walls(b, rooms, st, y0, y1 - y0 + 1, (x0, z0, x1, z1), avoid=near_stairs(fi))
        rooms_all += rooms
    keep = [(door_x, 1, 1), (door_x, 1, 2)]
    for fi in range(len(shell["floors"]) - 1):
        fy = shell["floors"][fi]
        sx, sz = stairs_at[fi]
        keep += stair_keep(P.staircase(b, sx, fy + 1, sz, "north", rise=fh, st=st, w=1))
        keep += stair_access(b, sx, sz, fy, fh, bool(fi % 2))
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    if params.get("landscape", True):   # sehir parselinde peyzaj/agac yok (komsu yapi ve yola tasmasin)
        landscape_ring(b, g, 0, 0, w - 1, d - 1, st, seed=seed, trees=3 + int(2 * s), path_to=(door_x + (door_w - 1) // 2, -1))
    return finish_meta(b, "house", st, {"floors": shell["floors"], "door": [door_x, 1, 0]})


def green_roof(b, x0, z0, x1, z1, y, avoid=None, seed=0, st=None, deck=False):
    """Duz catiya yesil cati: yosun/cimen yamalari, cicekler, ahsap yuruyus yolu (deck=True: ahsap teras + oturma)."""
    import random as _r
    rnd = _r.Random(seed)
    wood = st.block("wall2") if st else "spruce_planks"
    flowers = ["short_grass", "short_grass", "fern", "poppy", "dandelion", "cornflower", "oxeye_daisy", "allium"]
    for x in range(x0, x1 + 1):
        for z in range(z0, z1 + 1):
            if avoid and avoid[0] <= x <= avoid[2] and avoid[1] <= z <= avoid[3]:
                continue
            mid = (x0 + x1) // 2
            if abs(x - mid) <= 1 or (deck and (z - z0) % 9 < 4 and x - x0 < (x1 - x0) // 2):
                cur = (b.get(x, y, z) or "").split("[")[0]
                if not any(k in cur for k in ("lantern", "light", "glass", "glowstone", "detector", "lamp", "_rod")):
                    b.set(x, y, z, wood)
                continue
            cur = (b.get(x, y, z) or "").split("[")[0]
            if any(k in cur for k in ("lantern", "light", "glass", "glowstone", "detector", "lamp", "_rod")):
                continue
            if b.get_id(x, y + 1, z) > 1:
                continue
            if (x * 7 + z * 13 + seed) % 11 < 7:
                b.set(x, y, z, "moss_block")
                if rnd.random() < 0.45:
                    b.set(x, y + 1, z, rnd.choice(flowers))
    b.meta.setdefault("notes", []).append("yesil cati")


# ------------------------------------------------------------------ modern villa
def villa_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.4)
    w = int(params.get("width") or max(18, round(21 * s)))
    d = int(params.get("depth") or max(14, round(15 * s)))
    return w, d + 16  # on bahce + havuz dahil ayak izi


def modern_villa(params: dict, ctx: dict | None = None) -> Build:
    """Kademeli beyaz kutleler, konsol ust kat, cam cepheler, ahsap kaplama, duz catilar + teras, havuz, peyzaj, doseli ic."""
    st = get_style(params, ctx, "modern")
    s = scale_of(params, 1.4)
    W, Dfull = villa_dims(params)
    D = Dfull - 16
    Z = 14  # bina on cephesi z=14 (onunde havuz ve bahce)
    seed = int(params.get("seed", 3))
    floors = int(params.get("floors") or (1 if s < 0.8 else 2 if s < 1.7 else 3))
    pool = params.get("pool", True)
    b = Build(params.get("name") or "modern villa")
    g = ground_of(ctx, W, Dfull)
    fh = 5
    clear_volume(b, -6, 1, -4, W + 5, fh * floors + 10, Dfull + 4)
    settle_on_ground(b, g, -3, -2, W + 2, Dfull + 1, st, blend=5)
    # zemin: cim + on avlu dosemesi
    b.fill(-3, 0, -2, W + 2, 0, Dfull + 1, "grass_block")
    # --- zemin kat (A): tam genislik
    ax0, az0, ax1, az1 = 0, Z, W - 1, Z + D - 1
    P.plinth(b, ax0 - 1, az0 - 1, ax1 + 1, az1 + 1, 0, st, h=1)
    A = P.walls_box(b, ax0, 0, az0, ax1, fh - 1, az1, st, floors=[0], cornice_top=False)
    # --- ust kat (B): saga kaymis, one konsol
    bx0, bx1 = int(W * 0.30), W - 1
    bz0, bz1 = Z - 3, Z + D - 3
    B = None
    if floors >= 2:
        B = P.walls_box(b, bx0, fh, bz0, bx1, 2 * fh - 1, bz1, st, floors=[fh], cornice_top=False,
                        roles=["wall2"])
        # konsolun alti: bina govdesinin onundeki kisim beyaz tavan (doseme) — B'nin dosemesi zaten var
    # --- cati katı (C)
    C = None
    if floors >= 3:
        cx0, cx1 = int(W * 0.50), int(W * 0.88)
        cz0, cz1 = Z + 1, Z + int(D * 0.62)
        C = P.walls_box(b, cx0, 2 * fh, cz0, cx1, 3 * fh - 1, cz1, st, floors=[2 * fh], cornice_top=False)
    # --- cam cepheler (on): A'nin solu ve B'nin onu genis cam
    gl = st.pane()
    frame = st.block("pillar") if st.variants("pillar") else st.block("trim")

    def curtain(x0, x1, y0, y1, z, face="north"):
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                b.set(x, y, z, gl)
        for x in range(x0 - 1, x1 + 2, 4):
            b.fill(x, y0, z, x, y1, z, "!" + frame if not frame.startswith("!") else frame)

    curtain(2, bx0 - 2, 1, fh - 2, az0)                      # yasam alani cami
    curtain(bx0 + 2, ax1 - 2, 1, fh - 2, az0)                # zemin kat sag
    if B:
        curtain(bx0 + 2, bx1 - 2, fh + 1, 2 * fh - 2, bz0)    # konsol cami
        for zz in range(bz0 + 2, bz1 - 1, 4):                 # yan seritler
            P.window(b, bx1, fh + 2, zz, "east", w=2, h=2, st=st)
    if C:
        curtain(cx0 + 1, cx1 - 1, 2 * fh + 1, 3 * fh - 2, cz0)
    for zz in range(az0 + 2, az1 - 2, 4):
        P.window(b, ax0, 2, zz, "west", w=2, h=2, st=st)
        P.window(b, ax1, 2, zz, "east", w=2, h=2, st=st) if not B else None
    for xx in range(2, W - 3, 5):
        P.window(b, xx, 2, az1, "south", w=3, h=2, st=st)
    # --- giris: konsolun altinda (sag), konsol yoksa kanopili; havuz solda kalir
    ex = int(W * 0.72) if B else max(2, W - 8)
    P.door(b, ex, 1, az0, "north", st, w=2)
    if not (B and bx0 <= ex - 1 and ex + 2 <= bx1):
        P.canopy(b, ex - 1, fh - 1, az0, "north", w=4, depth=2, st=st)
    # --- duz catilar + teras korkulugu
    P.roof_flat(b, ax0, az0, ax1, az1, fh, st, overhang=1, parapet=0, details=False)
    if B:
        # A'nin cati katı = teras: cam korkuluk
        for x in range(ax0, bx0):
            b.set(x, fh + 1, az0, st.pane())
        for z in range(az0, az1 + 1):
            b.set(ax0, fh + 1, z, st.pane())
        P.roof_flat(b, bx0, bz0, bx1, bz1, 2 * fh, st, overhang=1, parapet=1 if not C else 0)
    if C:
        P.roof_flat(b, cx0, cz0, cx1, cz1, 3 * fh, st, overhang=2, parapet=0)
        P.pergola(b, bx0 + 1, 2 * fh + 1, bz0 + 1, cx0 - 2, bz0 + 5, st, h=3, greenery=True, seed=seed)
    # --- konsol alti gomme isiklar (karanlik nokta kalmasin), cephe lambalari
    lb = st.block("light_block")
    if B:
        for x in range(bx0 + 2, bx1 - 1, 4):
            for z in (bz0, bz0 + 2):
                if z < az0:
                    b.set(x, fh, z, lb)
    for x in range(1, W - 1, 6):
        P.wall_lamp(b, x, 3, az0 - 1, "north", st) if not (ex - 1 <= x <= ex + 2) else None
    P.wall_lamp(b, ex - 1, 3, az0 - 1, "north", st)
    P.wall_lamp(b, ex + 2, 3, az0 - 1, "north", st)
    # --- cati: teras bahcesi (A'nin acik kismi), isik kubbeleri, gunes panelleri
    tz0, tz1 = az0 + 1, az1 - 1
    for x0_, x1_ in ((ax0 + 2, min(bx0 - 3, ax0 + 8)),):
        if x1_ > x0_:
            P.garden_bed(b, x0_, fh, tz0 + 2, x1_, tz0 + 4, st, raised=True, seed=seed + 5)
            P.planter(b, x1_ + 2, fh + 1, tz0 + 2, st, seed=seed)
            b.fill(ax0 + 2, fh + 1, tz1 - 3, min(bx0 - 3, ax0 + 9), fh + 1, tz1 - 3, S.derive(st.block("wall2"), "slab").split("[")[0] + "[type=bottom]")
    if B:
        for x in range(bx0 + 3, bx1 - 2, 3):
            b.set(x, 2 * fh + 1, bz1 - 3, "daylight_detector")
            b.set(x, 2 * fh + 1, bz1 - 2, "daylight_detector")
    for x in range(ax0 + 3, ax1 - 2, 6):
        b.set(x, fh, az1 - 3, "glass")
    # --- ic mekan
    doors, rooms_all = [], []
    keep = [(ex, 1, az0 + 1), (ex + 1, 1, az0 + 1)]
    doors.append((ex, 1, az0))
    doors.append((ex + 1, 1, az0))
    ar = A["rooms"][0]
    big = (ar[3] - ar[0]) * (ar[5] - ar[2]) > 500
    kinds0 = ["living_room", "kitchen", "dining_room", "foyer"] + (["home_office", "gym", "bathroom", "library"] if big else [])
    rooms = split_rooms(ar[0], ar[2], ar[3], ar[5], ar[1], ar[4] - ar[1] + 1, kinds0, min_w=5, avoid_x=range(ex - 1, ex + 3))
    doors += partition_walls(b, rooms, st, ar[1], ar[4] - ar[1] + 1, (ar[0], ar[2], ar[3], ar[5]))
    rooms_all += rooms
    if B:
        br = B["rooms"][0]
        bigb = (br[3] - br[0]) * (br[5] - br[2]) > 400
        kinds1 = ["master_bedroom", "bathroom", "kids_room", "guest_room"] + (["study", "laundry"] if bigb else [])
        rooms = split_rooms(br[0], br[2], br[3], br[5], br[1], br[4] - br[1] + 1, kinds1, min_w=5)
        doors += partition_walls(b, rooms, st, br[1], br[4] - br[1] + 1, (br[0], br[2], br[3], br[5]))
        rooms_all += rooms
        sx, sz = bx0 + 1, az1 - 2
        keep += stair_keep(P.staircase(b, sx, 1, sz, "north", rise=fh, st=st, w=2))
    if B:
        br0 = B["rooms"][0]
        room_windows(b, [r for r in rooms_all if r[1][1] == br0[1]], (br0[0], br0[2], br0[3], br0[5]), fh + 2, st,
                     faces=("south", "west", "east"))
    if C:
        cr = C["rooms"][0]
        if (cr[3] - cr[0]) * (cr[5] - cr[2]) > 160:
            rooms = split_rooms(cr[0], cr[2], cr[3], cr[5], cr[1], cr[4] - cr[1] + 1, ["home_office", "lounge", "bathroom", "guest_room"], min_w=5)
            doors += partition_walls(b, rooms, st, cr[1], cr[4] - cr[1] + 1, (cr[0], cr[2], cr[3], cr[5]))
            rooms_all += rooms
        else:
            rooms_all.append(("home_office", tuple(cr)))
        room_windows(b, [r for r in rooms_all if r[1][1] == cr[1]], (cr[0], cr[2], cr[3], cr[5]), 2 * fh + 2, st,
                     faces=("south", "west", "east"))
        sx, sz = cx0 + 1, cz1 - 2
        keep += stair_keep(P.staircase(b, sx, fh + 1, sz, "north", rise=fh, st=st, w=1))
    # giris holu: kapinin arkasi 2 blok derin bos kalsin (bolme duvari kapiya denk gelirse acilir)
    b.fill(ex, 1, az0 + 1, ex + 1, 3, az0 + 2, "air")
    keep += [(x, y, z) for x in (ex, ex + 1) for y in (1, 2) for z in (az0 + 1, az0 + 2)]
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    green_roof(b, ax0 + 1, az0 + 1, ax1 - 1, az1 - 1, fh, avoid=(bx0 - 1, bz0 - 1, bx1 + 1, bz1 + 1) if B else None, seed=seed, st=st)
    if B and not C:
        green_roof(b, bx0 + 1, bz0 + 1, bx1 - 1, bz1 - 1, 2 * fh, seed=seed + 1, st=st, deck=True)
    if C:
        green_roof(b, bx0 + 1, bz0 + 1, bx1 - 1, bz1 - 1, 2 * fh, avoid=(cx0 - 1, cz0 - 1, cx1 + 1, cz1 + 1), seed=seed + 1, st=st, deck=True)
    # --- havuz, ahsap deste, sezlonglar
    if pool:
        px0 = max(2, int(W * 0.06))
        px1 = min(px0 + max(8, int(W * 0.5)), ex - 7)
        pz0, pz1 = 3, Z - 4
        pool = px1 - px0 >= 5
    if pool:
        deck = st.block("wall2")
        b.fill(px0 - 2, 0, pz0 - 2, px1 + 2, 0, pz1 + 3, deck)
        P.pool(b, px0, 0, pz0, px1, pz1, st, depth=2, lights=True, steps=True)
        for i, x in enumerate(range(px0, px1 - 1, 3)):
            b.set(x, 1, pz1 + 2, "!" + S.derive(st.block("trim"), "stairs").split("[")[0] + "[facing=north,half=bottom,shape=straight]")
            b.set(x, 1, pz1 + 3, S.derive(st.block("trim"), "slab").split("[")[0] + "[type=bottom]")
        for x in (px0 - 3, px1 + 3):
            P.lamp_post(b, x, 1, pz0, st, h=3)
    # --- bahce, yol, agaclar
    path_x = ex
    P.path(b, [(path_x, -2), (path_x, Z - 1)], 0, st, w=3, border=True)
    for z in range(0, Z - 4, 5):
        P.lamp_post(b, path_x + 3, 1, z, st, h=3)
    P.hedge(b, -3, 0, -2, -3, Dfull + 1, st, h=1)
    P.hedge(b, W + 2, 0, -2, W + 2, Dfull + 1, st, h=1)
    landscape_ring(b, g, 0, Z, W - 1, Z + D - 1, st, seed=seed, trees=4 + int(3 * s), species=("birch", "cherry", "oak"),
                   lamps=False, path_to=None, flowers=True, avoid=[(-3, -3, W + 3, Z - 1)])
    return finish_meta(b, "modern_villa", st, {"floors": [0, fh, 2 * fh][:floors], "front_yard": [0, 0, W - 1, Z - 1]})


__all__ = ["house", "house_dims", "modern_villa", "villa_dims", "I", "T", "random"]
