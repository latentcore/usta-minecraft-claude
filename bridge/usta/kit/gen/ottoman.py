"""Osmanli ureteçleri: ottoman_konak (avlulu/bahceli konak), mosque (avlulu, kubbeli, minareli cami).
Yerel cerceve: on cephe z=0'da (-z'ye bakar), +x yapinin sagi, y=0 zemin seviyesi."""
from __future__ import annotations

from . import register
from .. import shapes as SH
from .common import (I, P, S, T, Build, clear_volume, finish_meta, furnish_rooms, get_style, ground_of, partition_walls,
                     light_shaft, perimeter_lamps, random, room_windows, scale_of, settle_on_ground, split_rooms,
                     stair_access, stair_keep)


# ------------------------------------------------------------------ yardimcilar
def garden_wall(b, x0, z0, x1, z1, st, gate_x, gate_w=2, h=2, seed=0):
    """Avlu/bahce duvari: tas govde, ustte basamak harpusta, araliklarda baba; on cephede (z0) gate_x'te kapi."""
    pts = [(x0, z0), (x1, z0), (x1, z1), (x0, z1), (x0, z0)]
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        for t in range(max(abs(bx - ax), abs(bz - az)) + 1):
            x = ax + (t if bx > ax else -t if bx < ax else 0)
            z = az + (t if bz > az else -t if bz < az else 0)
            if z == z0 and gate_x <= x <= gate_x + gate_w - 1:
                continue
            post = (x - x0) % 5 == 0 and (z - z0) % 5 == 0
            st.fill(b, x, 1, z, x, h - 1 + (1 if post else 0), z, "foundation")
            cap_y = h + (1 if post else 0)
            b.set(x, cap_y, z, st.slab("trim" if post else "foundation", "bottom"))
    # kapi: iki baba (fenerli) + uzerinde kemerli saçak
    for px in (gate_x - 1, gate_x + gate_w):
        st.fill(b, px, 1, z0, px, h + 1, z0, "detail")
        b.set(px, h + 2, z0, st.light())
    P.canopy(b, gate_x, h - 1, z0, "north", w=gate_w, depth=1, st=st)


def ottoman_garden(b, x0, z0, x1, z1, st, axis_x, seed=0, fountain=True):
    """On bahce: eksende sadirvan, cevresinde tas yol halkasi, lale tarhlari, serviler, banklar ve fenerler."""
    rnd = random.Random(seed)
    cz = (z0 + z1) // 2
    cx = axis_x
    big = (z1 - z0) >= 16 and (x1 - x0) >= 20       # sadirvanin sacakli kulahi ~13 blok: yalniz genis bahcede
    r = 2
    if fountain:
        P.fountain(b, cx, 0, cz, st, kind="sadirvan" if big else "simple", r=r)
    ring = (r + 5) if big else (r + 2)
    P.path(b, [(cx, z0), (cx, cz - ring)], 0, st, w=3, border=True)
    P.path(b, [(cx, cz + ring), (cx, z1)], 0, st, w=3, border=True)
    P.path(b, [(cx - ring, cz - ring), (cx + ring, cz - ring), (cx + ring, cz + ring), (cx - ring, cz + ring), (cx - ring, cz - ring)],
           0, st, w=1, border=False)
    for dx in (-1, 1):
        bx0 = cx + dx * (ring + 3)
        bx1 = (x1 - 2) if dx > 0 else (x0 + 2)
        lo, hi = sorted((bx0, bx1))
        if hi - lo >= 3:
            P.garden_bed(b, lo, 0, cz - 2, hi, cz + 2, st, raised=True, seed=seed + 7 * dx)
        P.bench(b, cx + dx * (ring + 1), 1, cz - 1 if dx > 0 else cz + 1, "west" if dx > 0 else "east", st, length=3)
    for (tx, tz) in ((x0 + 2, z0 + 2), (x1 - 2, z0 + 2), (x0 + 2, z1 - 2), (x1 - 2, z1 - 2)):
        P.tree(b, tx, 1, tz, st, kind="cypress", seed=rnd.randint(0, 999))
    for (tx, tz) in ((cx - ring - 2, cz - ring - 2), (cx + ring + 2, cz - ring - 2)):
        if x0 + 2 < tx < x1 - 2 and z0 + 2 < tz < z1 - 2:
            P.tree(b, tx, 1, tz, st, kind="blossom" if rnd.random() < 0.5 else "round", seed=rnd.randint(0, 999))
    for (lx, lz) in ((cx - 2, z0 + 1), (cx + 2, z0 + 1), (cx - 2, z1 - 1), (cx + 2, z1 - 1)):
        if z0 < lz < z1:
            P.lamp_post(b, lx, 1, lz, st, h=3)


# ------------------------------------------------------------------ konak
def konak_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    w = int(params.get("width") or max(14, round(18 * s)))
    w += w % 2                      # cift: iki kanatli kapi ve cumba eksende
    d = int(params.get("depth") or max(11, round(13 * s)))
    gz = int(params.get("garden") or max(10, round(12 * s)))
    return w + 10, gz + d + 8


def ottoman_konak(params: dict, ctx: dict | None = None) -> Build:
    """Tas zemin kat + cikmali ahsap karkas ust katlar, eksende cumba, genis sacakli kirma cati, avlu duvari,
    sadirvanli on bahce, arka bahcede kuyu ve sebze tarhlari; doseli odalar (bas oda, sofa, yatak odalari)."""
    st = get_style(params, ctx, "ottoman")
    s = scale_of(params, 1.0)
    FW, FD = konak_dims(params)
    w, gz = FW - 10, None
    d = int(params.get("depth") or max(11, round(13 * s)))
    gz = FD - d - 8
    floors = int(params.get("floors") or (2 if s < 1.3 else 3))
    seed = int(params.get("seed", 11))
    fh = st.floor_h
    top = floors * fh
    b = Build(params.get("name") or "Osmanlı konağı")
    g = ground_of(ctx, FW, FD)
    hx0, hz0 = 5, gz + 2
    hx1, hz1 = hx0 + w - 1, hz0 + d - 1
    clear_volume(b, -4, 1, -4, FW + 3, top + 16, FD + 3)
    settle_on_ground(b, g, -1, -1, FW, FD, st, blend=5)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    # --- kabuk: tas zemin kat, cikmali (jetty) ahsap karkas ust katlar
    P.plinth(b, hx0 - 1, hz0 - 1, hx1 + 1, hz1 + 1, 0, st, h=1)
    shell = P.walls_box(b, hx0, 0, hz0, hx1, top - 1, hz1, st)
    ox0, oz0, ox1, oz1 = shell["outer"]
    cx = hx0 + w // 2 - 1          # iki kanatli kapinin sol kanadi
    P.door(b, cx, 1, hz0, "north", st, w=2, steps=1)
    jet = oz0 < hz0
    cw = 6 if w >= 16 else 4
    cumba_x = hx0 + w // 2 - cw // 2
    for fi, fy in enumerate(shell["floors"]):
        e = 1 if (jet and fi > 0) else 0
        wy = fy + 2
        # zemin kat: seyrek, kucuk kafesli pencereler; ust katlar: iki kanatli uzun pencereler, aralarda beyaz siva
        kw = dict(w=1, h=2, every=4) if fi == 0 else dict(w=2, h=3, every=5)
        if fi == 0:
            P.window_row(b, hx0, wy, hz0, "north", w, st, avoid=[(cx, cx + 1)], **kw)
        else:   # avoid araliklari tam aciklik; window_row kendi 1 blok payini ekler
            P.window_row(b, hx0 - e, wy, hz0 - e, "north", w + 2 * e, st,
                         avoid=[(cumba_x, cumba_x + cw - 1)] if fi == 1 else (), **kw)
        P.window_row(b, hx0 - e, wy, hz1 + e, "south", w + 2 * e, st, **kw)
        P.window_row(b, hx0 - e, wy, hz0 - e, "west", d + 2 * e, st, **kw)
        P.window_row(b, hx1 + e, wy, hz0 - e, "east", d + 2 * e, st, **kw)
    if floors >= 2:
        fy1 = shell["floors"][1]
        # en ust kattaki cumba ana catinin genis sacagi altinda kalir: kendi catisi yok, pencere 2 sira
        topf = floors == 2
        P.cumba(b, cumba_x, fy1 + 1, oz0, "north", w=cw, h=2 if topf else 3, depth=2, st=st, roof=not topf)
        if w >= 22:   # buyuk konak: yan cephelerde de cumba
            for fx, face in ((ox0, "west"), (ox1, "east")):
                P.cumba(b, fx, fy1 + 1, hz0 + d // 2 - 2, face, w=4, h=2 if topf else 3, depth=1, st=st, roof=not topf)
    perimeter_lamps(b, hx0, hz0, hx1, hz1, 3, st, every=6, skip=[(cx - 1, hz0), (cx + 2, hz0)])
    for lx in (cx - 1, cx + 2):                      # kapinin iki yaninda fener
        P.wall_lamp(b, lx, 3, hz0, "north", st)
    tr = shell["rooms"][-1]               # en ust kat tavani (cati arasi dosemesi): asma lamba/gomme isik tutunsun
    st.fill(b, tr[0], top, tr[2], tr[3], top, tr[5], "ceiling")
    roof = P.roof(b, ox0 - 1, oz0 - 1, ox1 + 1, oz1 + 1, top, st, kind="hip")
    rt = roof.get("top", top + 4) if isinstance(roof, dict) else top + 4
    for chx in (hx0 + 2, hx1 - 3):
        P.chimney(b, chx, top - 1, hz1 - 3, rt - top + 2, st)
    # --- ic mekan: zemin kat taslik/mutfak/kiler, ust katlarda sofa + bas oda + yatak odalari
    plans = [["foyer", "kitchen", "pantry", "dining_room"], ["bas_oda", "living_room", "master_bedroom", "guest_room"],
             ["library", "kids_room", "tea_room", "home_office"]]
    doors, rooms_all = [(cx, 1, hz0), (cx + 1, 1, hz0)], []
    for fi, rb in enumerate(shell["rooms"]):
        x0, y0, z0, x1, y1, z1 = rb
        area = (x1 - x0) * (z1 - z0)
        n = 4 if area > 140 else 3 if area > 80 else 2
        rooms = split_rooms(x0, z0, x1, z1, y0, y1 - y0 + 1, plans[min(fi, 2)][:n], avoid_x=range(cx - 1, cx + 3))
        doors += partition_walls(b, rooms, st, y0, y1 - y0 + 1, (x0, z0, x1, z1))
        rooms_all += rooms
    keep = [(cx, 1, hz0 + 1), (cx + 1, 1, hz0 + 1), (cx, 1, hz0 + 2), (cx + 1, 1, hz0 + 2)]
    if floors >= 2:   # cumbanin onu bos kalsin (sedir/dolap acikligi kapatmasin)
        fy1 = shell["floors"][1]
        keep += [(x, fy1 + k, oz0 + 1) for x in range(cumba_x, cumba_x + cw) for k in (1, 2)]
        if w >= 22:
            for fx in (ox0 + 1, ox1 - 1):
                keep += [(fx, fy1 + k, z) for z in range(hz0 + d // 2 - 2, hz0 + d // 2 + 2) for k in (1, 2)]
    for fi in range(len(shell["floors"]) - 1):
        fy = shell["floors"][fi]
        sx, sz = hx1 - 2 - 2 * (fi % 2), hz1 - 2
        keep += stair_keep(P.staircase(b, sx, fy + 1, sz, "north", rise=fh, st=st, w=1))
        keep += stair_access(b, sx, sz, fy, fh, bool(fi % 2))
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    # --- avlu duvari, kapi, on bahce (sadirvan), arka bahce (kuyu, tarhlar)
    garden_wall(b, 0, 0, FW - 1, FD - 1, st, gate_x=cx, gate_w=2, h=2, seed=seed)
    ottoman_garden(b, 1, 1, FW - 2, hz0 - 3, st, axis_x=cx + 1 if False else cx, seed=seed)
    P.path(b, [(cx, hz0 - 3), (cx, hz0 - 1)], 0, st, w=4, border=False)
    by0 = hz1 + 3
    if FD - 2 - by0 >= 3:
        P.well(b, hx0 + 1, 0, by0, st)
        for k, x in enumerate(range(hx0 + 6, hx1 - 2, 5)):
            P.garden_bed(b, x, 0, by0, min(x + 3, hx1 - 2), FD - 3, st, raised=True, seed=seed + 30 + k)
        P.tree(b, hx1 + 2, 1, FD - 3, st, kind="round", seed=seed + 3)
    return finish_meta(b, "ottoman_konak", st, {"floors": shell["floors"], "door": [cx, 1, hz0],
                                                "front_yard": [1, 1, FW - 2, hz0 - 3]})


# ------------------------------------------------------------------ cami
def mosque_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 0.7)
    S_ = int(params.get("width") or max(11, round(17 * s)))
    S_ += 1 - S_ % 2                # tek: kubbe ekseni bir hucrede
    court = int(params.get("court") or max(9, round(S_ * 0.8)))
    return S_ + 12, S_ + court + 12


def mosque(params: dict, ctx: dict | None = None) -> Build:
    """Kare harim + kasnakli merkezi kubbe, kose agirlik kuleleri, revakli son cemaat yeri (kubbecikli),
    sadirvanli avlu, kemerli avlu kapisi, serefeli minare; icte mihrap, minber, kilim, avize."""
    st = get_style(params, ctx, "ottoman")
    st = st.override(wall=[("smooth_sandstone", 0.5), ("sandstone", 0.25), ("cut_sandstone", 0.25)],
                     foundation=[("stone_bricks", 0.7), ("cracked_stone_bricks", 0.3)],
                     dome=[("polished_andesite", 0.8), ("andesite", 0.2)],
                     roof=[("polished_andesite", 0.85), ("andesite", 0.15)],      # kursun gri ortu
                     trim=[("smooth_sandstone", 1.0)], frame=[("stone_bricks", 1.0)], roof_trim=[("smooth_stone", 1.0)],
                     shutter="iron_trapdoor") if params.get("stone", "kum") != "gri" else st
    FW, FD = mosque_dims(params)
    S_ = FW - 12
    court = FD - S_ - 12
    seed = int(params.get("seed", 5))
    b = Build(params.get("name") or "cami")
    g = ground_of(ctx, FW, FD)
    H = max(8, S_ // 2 + 3)                      # harim duvar yuksekligi
    r = S_ // 2 - 1                              # kubbe yaricapi
    drum = 2 if S_ >= 13 else 1
    hx0 = 6
    hx1 = hx0 + S_ - 1
    pd = 4                                       # son cemaat yeri derinligi
    cz0, cz1 = 2, 2 + court - 1                  # avlu
    hz0 = cz1 + pd + 1
    hz1 = hz0 + S_ - 1
    cx = (hx0 + hx1) // 2
    czc = (hz0 + hz1) // 2
    clear_volume(b, -4, 1, -4, FW + 3, H + r + drum + 40, FD + 3)
    settle_on_ground(b, g, -1, -1, FW, FD, st, blend=5)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    # --- harim
    P.plinth(b, hx0 - 1, hz0 - 1, hx1 + 1, hz1 + 1, 0, st, h=1)
    st.fill(b, hx0, 0, hz0, hx1, 0, hz1, "floor_alt")
    sh = SH.shell_box(hx0, 1, hz0, hx1, H - 1, hz1, t=1, top=False, bottom=False)
    sh.put_style(b, st, "wall")
    for y in (4, H - 2):                         # tas kusaklar
        if y < H - 1:
            for face, fx, fz, ln in (("north", hx0, hz0, S_), ("south", hx0, hz1, S_), ("west", hx0, hz0, S_), ("east", hx1, hz0, S_)):
                P.band(b, face, fx, y, fz, ln, st, role="foundation", kind="ledge")
    # kemerli pencereler: iki sira (alt dikdortgen kafesli, ust kemerli)
    for face, fx, fz in (("west", hx0, hz0), ("east", hx1, hz0), ("south", hx0, hz1)):
        P.window_row(b, fx, 2, fz, face, S_, st, w=1, h=2, kind="kafes", every=3)
        P.window_row(b, fx, 6, fz, face, S_, st, w=1, h=2 if H < 10 else 3, kind="arched", every=3) if H >= 9 else None
    P.window_row(b, hx0, 6, hz0, "north", S_, st, w=1, h=2, kind="arched", every=3, avoid=[(cx - 2, cx + 2)]) if H >= 9 else None
    # cati: kubbe kasnagi altinda duz cati (kenarlari korniş), kubbe acikligi icten gorunur
    for face, fx, fz in (("west", hx0, hz0), ("east", hx1, hz0), ("south", hx0, hz1)):   # yan cephelerde payanda ritmi
        P.pilasters(b, face, fx, 1, fz, S_, H - 1, st, every=4, role="foundation")
    P.roof_flat(b, hx0, hz0, hx1, hz1, H, st, overhang=1, parapet=0, details=False, role="foundation")
    SH.disk((cx, H, czc), r - 1).put(b, "minecraft:air")
    P.dome(b, cx, H + 1, czc, r, st, kind="hemi", drum=drum, windows=True, finial=True)
    for y in range(H + 1, H + 2 + drum):         # kasnak ici ve kubbe taban diski bos: ic mekana acilir
        SH.disk((cx, y, czc), r - 1).put(b, "minecraft:air")
    for (tx, tz) in ((hx0, hz0), (hx1, hz0), (hx0, hz1), (hx1, hz1)):   # kose agirlik kuleleri
        st.fill(b, tx, H + 1, tz, tx, H + 2, tz, "foundation")
        P.dome(b, tx, H + 3, tz, 1, st, kind="hemi", drum=0, windows=False, finial=True)
    # giris: kemerli taç kapi
    P.arched_gate(b, cx - 1, 1, hz0, "north", w=3, h=4, st=st, depth=1, gate="door" if False else None)
    st.fill(b, cx - 1, 1, hz0, cx + 1, 1, hz0, "floor_alt") if False else None
    # --- son cemaat yeri: kubbecikli revak (harimin on duvarina yaslanir)
    P.arcade(b, hx0, 1, hz0 - pd, "north", length=S_, st=st, depth=pd, bay=4, col_h=4, roof_kind="domes", back_wall=False)
    st.fill(b, hx0, 0, hz0 - pd, hx1, 0, hz0 - 1, "paving")
    # --- avlu: tas doseme, revaksiz duvar + kemerli kapi, merkezde sadirvan, kose servileri
    ax0, ax1 = hx0 - 2, hx1 + 2
    st.fill(b, ax0 + 1, 0, cz0 + 1, ax1 - 1, 0, cz1, "paving")
    P.floor_pattern(b, ax0 + 2, 0, cz0 + 2, ax1 - 2, cz1 - 1, st, kind="border")
    for x in range(ax0, ax1 + 1):
        if not (cx - 1 <= x <= cx + 1):
            st.fill(b, x, 1, cz0, x, 2, cz0, "wall")
            b.set(x, 3, cz0, st.slab("foundation", "bottom"))
    for z in range(cz0, hz0 - pd):
        for x in (ax0, ax1):
            st.fill(b, x, 1, z, x, 2, z, "wall")
            b.set(x, 3, z, st.slab("foundation", "bottom"))
    P.arched_gate(b, cx - 1, 1, cz0, "north", w=3, h=4, st=st, depth=1)
    P.fountain(b, cx, 0, (cz0 + cz1) // 2 + 1, st, kind="sadirvan" if (court >= 14 and S_ >= 13) else "simple", r=2)
    for (tx, tz) in ((ax0 + 2, cz0 + 2), (ax1 - 2, cz0 + 2)):
        P.tree(b, tx, 1, tz, st, kind="cypress", seed=seed + tx)
    for lx in (ax0 + 2, ax1 - 2):
        P.lamp_post(b, lx, 1, cz1 - 1, st, h=3)
    P.path(b, [(cx, -2), (cx, cz0)], 0, st, w=3, border=True)
    # --- minare: harimle avlunun birlestigi sag kosede
    mh = int(params.get("minaret_h") or max(26, S_ * 2 + 6))
    for k, mx in enumerate((hx1 + 4, hx0 - 4)):
        if k and int(params.get("minarets", 1)) < 2:
            break
        mz = hz0 + 1
        st.fill(b, mx - 4, 0, mz - 4, mx + 4, 0, mz + 4, "paving")   # kaide eteği duz zemine (harim kaidesiyle cakismasin)
        P.minaret(b, mx, 1, mz, h=mh, st=st, r=2, serefe=1 if mh < 34 else 2)
        light_shaft(b, mx, mz, 2, mh - 4, r=3, every=4, level=14)   # r=3: serefe halkasi da aday
    # --- ic: mihrap/minber/kilim/avize (prayer_hall tarifi); kubbeden uzun zincirli avize
    try:
        I.furnish(b, (hx0 + 1, 1, hz0 + 1, hx1 - 1, H - 1, hz1 - 1), "prayer_hall", style="ottoman",
                  door=[(cx, 1, hz0 - 1), (cx, 1, hz0)], seed=seed)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"prayer_hall: {e}")
    apex = H + 1
    while apex < H + drum + 3 * r and b.get_id(cx, apex, czc) <= 1:
        apex += 1                                 # kubbe kabugunun ic tepe blogu (avizenin tavani)
    drop = max(1, apex - (H - 1))
    P.chandelier(b, cx, apex, czc, st, r=2 if r >= 5 else 1, drop=drop)
    for (lx, lz) in ((cx - r + 2, czc), (cx + r - 2, czc), (cx, czc - r + 2), (cx, czc + r - 2)):
        b.set(lx, H + 1, lz, "light[level=13]")   # kasnak hizasinda gorunmez isik: kubbe ici karanlik kalmasin
    # --- cevre: avlu disinda serviler ve cimen
    rnd = random.Random(seed)
    for (tx, tz) in ((1, FD - 3), (FW - 2, FD - 3), (1, hz0 + 2), (FW - 2, hz0 + 2)):
        P.tree(b, tx, 1, tz, st, kind="cypress", seed=rnd.randint(0, 999))
    return finish_meta(b, "mosque", st, {"floors": [0], "door": [cx, 1, hz0], "court": [ax0, cz0, ax1, cz1],
                                         "rooms": [{"name": "harim", "kind": "prayer_hall",
                                                    "box": [hx0 + 1, 1, hz0 + 1, hx1 - 1, H - 1, hz1 - 1]}]})


register("ottoman_konak", ottoman_konak, konak_dims,
         "Osmanlı konağı: taş zemin kat, çıkmalı ahşap karkas üst katlar, cumba, geniş saçaklı kırma çatı, avlu duvarı, şadırvanlı bahçe",
         {"size": "orta|büyük|devasa", "floors": "2-3", "garden": "bahçe derinliği"}, lambda p: p.get("name") or "Osmanlı konağı")
register("mosque", mosque, mosque_dims,
         "Cami: kare harim, kasnaklı merkezi kubbe, kubbecikli son cemaat revakı, şadırvanlı avlu, şerefeli minare, mihrap/minber",
         {"size": "küçük|orta|büyük", "minarets": "1-2", "minaret_h": "yükseklik"}, lambda p: p.get("name") or "cami")
