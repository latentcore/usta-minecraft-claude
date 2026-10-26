"""Anit/altyapi ureteçleri: arch_bridge (tas kemerli kopru), lighthouse (deniz feneri + ahsap iskele), pier (iskele),
castle (surlu ortacag kalesi), watchtower (gozetleme kulesi). Yerel cerceve: on z=0 (-z'ye bakar), y=0 zemin."""
from __future__ import annotations

import math

import numpy as np

from . import register
from .. import shapes as SH
from .common import (I, P, S, T, Build, clear_volume, finish_meta, furnish_rooms, get_style, ground_of, light_shaft,
                     partition_walls, perimeter_lamps, random, room_windows, scale_of, settle_on_ground, split_rooms,
                     stair_access, stair_keep, tower_door)


# ------------------------------------------------------------------ yardimcilar
def water_level(g) -> int | None:
    """Su yuzeyi tahmini (yerel y): suya komsu kara hucrelerinin medyan zemin yuksekligi; su yoksa None."""
    if g.water is None or not g.water.any():
        return None
    w = g.water
    if getattr(g, "top", None) is not None:        # oyundan gelen gercek su yuzeyi
        return int(np.max(g.top[w]))
    edge = np.zeros_like(w)
    edge[1:, :] |= w[:-1, :]
    edge[:-1, :] |= w[1:, :]
    edge[:, 1:] |= w[:, :-1]
    edge[:, :-1] |= w[:, 1:]
    shore = edge & ~w
    if not shore.any():
        return int(np.max(g.h[w])) + 1
    return int(np.median(g.h[shore]))


def ground_top(b, g, x: int, z: int) -> int:
    """(x,z) kolonunda planin ya da arazinin en ust dolu blogu (yerel y)."""
    gy = g.at(x, z)
    for y in range(gy + 12, gy - 1, -1):
        if b.get_id(x, y, z) > 1 and b.is_solid(x, y, z):
            return y
    return gy


def pier_deck(b, g, x0: int, z0: int, length: int, width: int, y: int, st, axis: str = "z", sign: int = 1,
              end_platform: bool = True, seed: int = 0, boat: bool = False) -> dict:
    """Ahsap iskele: (x0,z0) kiyidaki ilk deck hucresinin kosesi; `axis` boyunca `sign` yonunde `length` blok.
    Kutuk direkler (3 blokta bir) zemine/su tabanina iner, deck tahta (y), korkuluk cit, direk basinda fener,
    ucta T platform + bank + bagli kayik."""
    rnd = random.Random(seed)
    post = "stripped_dark_oak_log[axis=y]"
    fence = "dark_oak_fence"

    def deckb(X, Z):   # yipranmis tahta karisimi
        return "spruce_planks" if (X * 7 + Z * 3 + seed) % 5 else "stripped_spruce_wood[axis=x]"
    deck = "spruce_planks"

    def cell(u, v):  # u: iskele boyunca, v: enine
        return (x0 + v, z0 + sign * u) if axis == "z" else (x0 + sign * u, z0 + v)
    cells = []
    for u in range(length):
        for v in range(width):
            X, Z = cell(u, v)
            b.set(X, y, Z, deckb(X, Z))
            cells.append((X, Z))
    for v in range(-1, width + 1):             # kiyi ucu: tas basamak/oturtma
        X, Z = cell(0, v)
        bot = g.at(X, Z)
        for yy in range(bot + 1, y + 1):
            b.set(X, yy, Z, "stone_bricks" if (yy + v) % 3 else "mossy_stone_bricks")
    plat = []
    if end_platform and length >= 8:
        for u in range(length, length + 3):
            for v in range(-2, width + 2):
                X, Z = cell(u, v)
                b.set(X, y, Z, deck)
                plat.append((X, Z))
    # direkler: kenarlarda her 3 blokta, zemine kadar
    allu = length + (3 if plat else 0)
    for u in range(0, allu, 3):
        for v in ((-2, width + 1) if u >= length and plat else (0, width - 1)):
            X, Z = cell(u, v)
            bot = g.at(X, Z)
            if bot < y - 1:
                b.fill(X, bot + 1, Z, X, y - 1, Z, post)
    # korkuluk: iki yan cit (girisi acik), direk basinda fener
    for u in range(1, allu):
        inplat = u >= length
        for v in ((-3, width + 2) if inplat else (-1, width)):
            X, Z = cell(u, v)
            b.set(X, y, Z, deck)
            b.set(X, y + 1, Z, fence)
            if u % 6 == 0:
                b.set(X, y + 2, Z, "lantern")
    if plat:
        for v in range(-3, width + 3):
            X, Z = cell(allu, v)
            b.set(X, y, Z, deck)
            b.set(X, y + 1, Z, fence)
        for v in (-2, width + 1):
            bx, bz = cell(length + 1, v)
            b.set(bx, y + 1, bz, "barrel[facing=up]")
        # kayik (varlik): yalniz acikca istenince — Usta guvenlik kurali varliklari acik istekle yazar
        if boat:
            kx, kz = cell(length + 1, width + 4)
            b.add_entity("minecraft:oak_boat", kx + 0.5, y + 0.0, kz + 0.5, yaw=0.0 if axis == "z" else 90.0)
    return {"cells": cells + plat, "end": cell(allu, width // 2)}


def _hang(b, x: int, z: int, y_from: int, st) -> None:
    """(x,z) ustundeki ilk dolu bloga (cati/tavan) zincirli fener asar."""
    for y in range(y_from, y_from + 8):
        if b.get_id(x, y, z) > 1:
            P.hanging_lamp(b, x, y, z, st, length=max(1, y - y_from - 1))
            return


# ------------------------------------------------------------------ tas kemerli kopru
def bridge_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    L = int(params.get("length") or max(21, round(33 * s)))
    W = int(params.get("width") or (5 if s < 1.3 else 7))
    return W + 4, L


def arch_bridge(params: dict, ctx: dict | None = None) -> Build:
    """Tas kemerli kopru: z boyunca (z=0 yakin kiyi). Ayaklar su tabanina iner (memba yuzunde sivri sel yaran),
    kemer halkasi kontrast tas, kemer altina dokunulmaz (su yerinde kalir), parapet + baslikli babalar,
    ayaklarin ustunde fener, iki ucta yumusak rampa."""
    st = get_style(params, ctx, "medieval")
    st = st.override(trim=[("smooth_stone", 0.6), ("stone_bricks", 0.4)],                      # kemer halkasi: acik tas
                     wall=[("cobblestone", 0.4), ("mossy_cobblestone", 0.35), ("andesite", 0.25)],      # aynalik: koyu, yosunlu
                     foundation=[("stone_bricks", 0.5), ("mossy_stone_bricks", 0.3), ("cracked_stone_bricks", 0.2)],
                     path=[("polished_andesite", 0.6), ("andesite", 0.4)])
    FW, L = bridge_dims(params)
    W = FW - 4
    b = Build(params.get("name") or "taş köprü")
    g = ground_of(ctx, FW, L)
    wl = water_level(g)
    xs0, xs1 = 2, 2 + W - 1                        # deck (ic) genisligi
    bank0 = max(g.at(x, 0) for x in range(xs0, xs1 + 1))
    bank1 = max(g.at(x, L - 1) for x in range(xs0, xs1 + 1))
    base = wl if wl is not None else min(g.at((xs0 + xs1) // 2, z) for z in range(L))
    span = int(params.get("span") or (7 if L < 40 else 9))
    rise = span // 2 if params.get("arch", "round") == "round" else max(2, span // 3)
    spring = base + 2                              # ayaklar sudan 1 blok gorunsun, kemer acikligi yuksek
    deck = max(bank0, bank1, spring + rise + 1) + 1          # yuruyus deck_y+1
    ramp0, ramp1 = max(0, deck - bank0 - 1), max(0, deck - bank1 - 1)
    zs0, zs1 = ramp0 + 1, L - 2 - ramp1                      # kemerli govde araligi
    n = max(1, (zs1 - zs0 + 1 - 2) // (span + 2))
    used = n * (span + 2) + 2
    zs0 = zs0 + max(0, (zs1 - zs0 + 1 - used) // 2)
    piers = [zs0 + k * (span + 2) for k in range(n + 1)]     # her ayak 2 blok kalin: z, z+1
    clear_volume(b, 0, deck + 1, -2, FW - 1, deck + 6, L + 1)

    def under(z: int) -> int:
        """z kesitinde kemer alt yuzu (bu y ve ustu dolu); ayakta zemine kadar."""
        for p in piers:
            if p <= z <= p + 1:
                return -999
        for p in piers[:-1]:
            a, c = p + 2, p + 2 + span - 1
            if a <= z <= c:
                t = (z - a + 0.5) / span                  # 0..1
                if params.get("arch", "round") == "round":
                    dxc = abs(z + 0.5 - (a + span / 2))
                    return spring + int(math.sqrt(max(0.0, (span / 2) ** 2 - dxc * dxc)))
                else:
                    R = (span ** 2 / 4 + rise ** 2) / (2 * rise)
                    dx = (t - 0.5) * span
                    h = math.sqrt(max(0.0, R * R - dx * dx)) - (R - rise)
                return spring + int(round(h))
        return -999 if z < piers[0] or z > piers[-1] + 1 else spring
    for z in range(L):
        # rampa bolgeleri: zemine oturan dolgu
        if z < zs0 or z > piers[-1] + 1:
            for x in range(xs0 - 1, xs1 + 2):
                gy = g.at(x, z)
                top = deck if zs0 <= z <= piers[-1] + 1 else (bank0 + 1 + max(0, z - 0) if z < zs0 else bank1 + 1 + max(0, L - 1 - z))
                top = min(deck, top)
                if top - 1 >= gy + 1:
                    st.fill(b, x, gy + 1, z, x, top - 1, z, "wall")
                if xs0 <= x <= xs1:
                    if top < deck:
                        b.set(x, top, z, st.stairs("path", "south" if z < zs0 else "north", "bottom"))
                        if top - 1 >= gy + 1:
                            st.set(b, x, top - 1, z, "path")
                    else:
                        st.set(b, x, deck, z, "path")
            continue
        u = under(z)
        if u != -999 and g.at((xs0 + xs1) // 2, z) >= spring - 1:
            u = -999                                   # kiyi ustunde: kemer yerine zemine oturan dayanak
        for x in range(xs0 - 1, xs1 + 2):
            lo = (g.at(x, z) + 1) if u == -999 else u
            if lo <= deck - 1:
                st.fill(b, x, lo, z, x, deck - 1, z, "foundation" if u == -999 else "wall")
            st.set(b, x, deck, z, "path")
        if u != -999:   # kemer halkasi: alt yuzde kontrast tas sirasi
            for x in range(xs0 - 1, xs1 + 2):
                if u <= deck - 1:
                    st.set(b, x, u, z, "trim")
    # kemer alti yumusatma: basamak gecislerine ters merdiven (kutu degil kemer gorunsun)
    for k in range(len(piers) - 1):
        a, c = piers[k] + 2, piers[k] + 2 + span - 1
        mid = (a + c) / 2
        for z in range(a, c + 1):
            zp = z - 1 if z <= mid else z + 1
            uz, up = under(z), under(zp)
            if uz == -999 or g.at((xs0 + xs1) // 2, z) >= spring - 1:
                continue
            if up == -999 or up < uz:
                face = "north" if zp < z else "south"
                for x in range(xs0 - 1, xs1 + 2):
                    if b.get_id(x, uz - 1, z) <= 1 and uz - 1 >= spring:
                        b.set(x, uz - 1, z, st.stairs("trim", face, "top"))
    # aynaliklarda sarmasik (seyrek)
    rnd = random.Random(int(params.get("seed", 3)))
    for z in range(L):
        for x, face in ((xs0 - 2, "east"), (xs1 + 2, "west")):
            if rnd.random() < 0.12 and b.is_solid(x - (1 if face == "west" else -1) * 0 + (1 if face == "east" else -1), deck - 1, z):
                for y in range(deck - 1, deck - 1 - rnd.randint(1, 3), -1):
                    if b.get_id(x, y, z) <= 1:
                        b.set(x, y, z, f"vine[{face}=true]")
    # ayak sel yaranlari (iki yuz) ve fenerler
    for p in piers:
        for (xx, dx) in ((xs0 - 2, -1), (xs1 + 2, 1)):
            top = deck - 1
            bot = min(g.at(xx, p), g.at(xx, p + 1)) + 1
            for zz in (p, p + 1):
                if top >= bot:
                    st.fill(b, xx, bot, zz, xx, top, zz, "foundation")
            b.set(xx, top + 1, p, st.stairs("foundation", "south", "bottom"))
            b.set(xx, top + 1, p + 1, st.stairs("foundation", "north", "bottom"))
            tip = xx + dx
            bt = g.at(tip, p) + 1
            if top - 1 >= bt:
                st.fill(b, tip, bt, p, tip, top - 1, p + 1, "foundation")
            b.set(tip, top, p, st.stairs("foundation", "east" if dx < 0 else "west", "bottom"))
            b.set(tip, top, p + 1, st.stairs("foundation", "east" if dx < 0 else "west", "bottom"))
    # parapet: iki yan, babalar ayak hizasinda, ustlerinde fener
    for z in range(L):
        dz_top = deck if zs0 <= z <= piers[-1] + 1 else None
        if dz_top is None:
            continue
        for x in (xs0 - 1, xs1 + 1):
            ispost = any(p <= z <= p + 1 for p in piers)
            st.set(b, x, deck + 1, z, "foundation")
            b.set(x, deck + 2, z, st.slab("trim", "bottom")) if not ispost else st.set(b, x, deck + 2, z, "foundation")
            if ispost and z in piers:
                b.set(x, deck + 3, z, "lantern")
    return finish_meta(b, "arch_bridge", st, {"deck_y": deck, "piers": piers, "water_level": wl, "span": span,
                                              "floors": [deck]})


# ------------------------------------------------------------------ deniz feneri + iskele
def lighthouse_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return max(22, round(26 * s)), max(34, round(40 * s))


def lighthouse(params: dict, ctx: dict | None = None) -> Build:
    """Kirmizi-beyaz seritli yuvarlak fener kulesi (doner merdiven, galeri, camli fener odasi, isik), bekci evi,
    kiyidan suya uzanan ahsap iskele (direkler tabana iner, fenerli korkuluk, uc platform, kayik)."""
    st = get_style(params, ctx, "scandinavian")
    s = scale_of(params, 1.0)
    FW, FD = lighthouse_dims(params)
    b = Build(params.get("name") or "deniz feneri")
    g = ground_of(ctx, FW, FD)
    seed = int(params.get("seed", 9))
    wl = water_level(g)
    # su hangi yonde? (on/arka/sol/sag yarida su orani) -> iskele o yone
    if g.water is not None and g.water.any():
        m = g.m
        wv = g.water[m:m + FD, m:m + FW]
        fr = {"back": wv[FD // 2:, :].mean(), "front": wv[:FD // 2, :].mean(), "left": wv[:, :FW // 2].mean(),
              "right": wv[:, FW // 2:].mean()}
        side = max(fr, key=fr.get)
    else:
        side = "back"
    r = 4 if s < 1.6 else 5        # ic cap: doner merdiven + kapidan giris icin en az r=4
    h = int(params.get("height") or max(18, round(24 * s)))
    # kule kara tarafinda
    tx, tz = {"back": (FW // 2, 7), "front": (FW // 2, FD - 8), "left": (FW - 8, FD // 2), "right": (7, FD // 2)}[side]
    clear_volume(b, tx - 12, 1, tz - 12, tx + 12, h + 16, tz + 12)
    land = [(tx - 9, tz - 7, tx + 9, tz + 7)]
    for (x0, z0, x1, z1) in land:
        settle_on_ground(b, g, x0, z0, x1, z1, st, blend=3)
        for x in range(x0, x1 + 1):
            for z in range(z0, z1 + 1):
                if not (g.water is not None and g.water[z + g.m, x + g.m] if g.inside(x, z) else False):
                    b.set(x, 0, z, "grass_block")
    # kule govdesi: seritli
    red = [("red_concrete", 0.7), ("red_terracotta", 0.3)]
    white = [("white_concrete", 0.6), ("calcite", 0.4)]
    stt = st.override(wall=white, foundation=[("stone_bricks", 0.6), ("cobblestone", 0.4)], roof=[("red_concrete", 1.0)],
                      floor=[("spruce_planks", 1.0)])
    tw = P.tower(b, tx, 0, tz, r=r, h=h, st=stt, top="none", floors=True, stair=True)
    band = 4
    for y in range(1, h):
        if (y // band) % 2 == 1:
            ring = SH.cylinder((tx, y, tz), (tx, y, tz), r, hollow=True, t=1)
            for (X, Y, Z) in ring.coords().tolist():
                if b.is_solid(X, Y, Z) and "glass" not in str(b.get(X, Y, Z)):
                    b.set(X, Y, Z, red[0][0] if (X + Z) % 3 else red[1][0])
    # kapi (kara tarafina bakan yuzde) + basamak
    dside = {"back": "north", "front": "south", "left": "east", "right": "west"}[side]
    vx, vz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[dside]
    dx_, dy_, dz_ = tower_door(b, tx, tz, r, 1, dside, stt, w=1)
    px_, pz_ = (1, 0) if vx == 0 else (0, 1)
    P.wall_lamp(b, dx_ + px_, 3, dz_ + pz_, dside, stt)
    # galeri (balkon halkasi) + fener odasi + kubbe
    gy = h
    SH.disk((tx, gy, tz), r + 2).put_style(b, stt, "foundation")
    ring = SH.ring((tx, gy + 1, tz), r + 2, r + 1, 1)
    ring.put(b, "minecraft:iron_bars")
    _lr = max(2, r - 1)
    SH.cylinder((tx, gy + 1, tz), (tx, gy + 3, tz), _lr, hollow=True, t=1).put(b, "minecraft:glass")
    for dx, dz in ((-_lr, 0), (_lr, 0), (0, -_lr), (0, _lr)):
        b.fill(tx + dx, gy + 1, tz + dz, tx + dx, gy + 3, tz + dz, "minecraft:iron_bars")   # dikmeler
    b.set(tx, gy + 1, tz, "minecraft:sea_lantern")
    b.set(tx, gy + 2, tz, "minecraft:glowstone")
    b.set(tx, gy + 3, tz, "minecraft:sea_lantern")
    # galeriye cikis: fener odasina bir kapi acikligi (camda) — merdiven ustu kat galeriye acilir
    b.set(tx + vx * _lr, gy + 1, tz + vz * _lr, "minecraft:air")
    b.set(tx + vx * _lr, gy + 2, tz + vz * _lr, "minecraft:air")
    SH.disk((tx, gy, tz), r - 1).put(b, "minecraft:spruce_planks")
    P.stair_hatch(b, tx, tz, gy)
    P.dome(b, tx, gy + 4, tz, _lr + 1, stt.override(dome=[("red_concrete", 1.0)]), kind="hemi", drum=0, windows=False, finial=True)
    SH.dome((tx, gy + 4, tz), _lr + 1).put(b, "minecraft:red_concrete", only_empty=True)   # kucuk kapak: ici dolu
    light_shaft(b, tx, tz, 2, h - 2, r=r - 1, every=4, level=13)
    # bekci evi: kulenin yaninda (kara tarafinda)
    hw, hd = 8, 6
    if side in ("back", "front"):
        hx0, hz0 = tx + r + 2, tz - 3
    else:
        hx0, hz0 = tx - 4, tz + r + 2
    sh = P.walls_box(b, hx0, 0, hz0, hx0 + hw - 1, 5, hz0 + hd - 1, st, floors=[0])
    P.door(b, hx0 + 2, 1, hz0, "north", st, w=1, steps=0)
    P.window_row(b, hx0, 2, hz0 + hd - 1, "south", hw, st)
    P.window_row(b, hx0 + hw - 1, 2, hz0, "east", hd, st)
    P.roof(b, hx0 - 1, hz0 - 1, hx0 + hw, hz0 + hd, 6, st, kind="gable")
    P.chimney(b, hx0 + hw - 2, 5, hz0 + 1, 5, st)
    try:
        I.furnish(b, tuple(sh["rooms"][0]), "living_room", style="nordic", door=[(hx0 + 2, 1, hz0)], seed=seed)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"bekci evi: {e}")
    perimeter_lamps(b, hx0, hz0, hx0 + hw - 1, hz0 + hd - 1, 3, st, every=5)
    # iskele: kuleden suya
    deck_y = (wl if wl is not None else 0) + 1
    if side == "back":
        pier = pier_deck(b, g, FW // 2 - 1, tz + r + 3, FD - (tz + r + 3) - 4, 3, deck_y, st, axis="z", sign=1, seed=seed, boat=bool(params.get("boat")))
    elif side == "front":
        pier = pier_deck(b, g, FW // 2 - 1, tz - r - 3, tz - r - 3 - 3, 3, deck_y, st, axis="z", sign=-1, seed=seed, boat=bool(params.get("boat")))
    elif side == "left":
        pier = pier_deck(b, g, tx - r - 3, FD // 2 - 1, tx - r - 3 - 3, 3, deck_y, st, axis="x", sign=-1, seed=seed, boat=bool(params.get("boat")))
    else:
        pier = pier_deck(b, g, tx + r + 3, FD // 2 - 1, FW - (tx + r + 3) - 4, 3, deck_y, st, axis="x", sign=1, seed=seed, boat=bool(params.get("boat")))
    for k, (lx, lz) in enumerate(((tx - r - 3, tz - r - 3), (tx + r + 3, tz - r - 3))):
        if g.inside(lx, lz) and not (g.water is not None and g.water[lz + g.m, lx + g.m]):
            P.lamp_post(b, lx, 1, lz, st, h=3)
    return finish_meta(b, "lighthouse", st, {"tower": [tx, tz, r, h], "pier_side": side, "water_level": wl,
                                             "floors": [0]})


def pier_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    return int(params.get("width") or 3) + 8, int(params.get("length") or max(14, round(22 * s))) + 5


def pier(params: dict, ctx: dict | None = None) -> Build:
    """Ahsap iskele: kiyidan (z=0) suya uzanan tahta deck, tabana inen kutuk direkler, fenerli korkuluk,
    ucta genis platform, variller ve bagli kayik."""
    st = get_style(params, ctx, "rustic")
    FW, FD = pier_dims(params)
    W = FW - 8
    b = Build(params.get("name") or "iskele")
    g = ground_of(ctx, FW, FD)
    wl = water_level(g)
    y = (wl if wl is not None else max(0, g.at(FW // 2, 0))) + 1
    clear_volume(b, 0, y + 1, 0, FW - 1, y + 4, FD - 1)
    pier_deck(b, g, (FW - W) // 2, 0, FD - 5, W, y, st, axis="z", sign=1, seed=int(params.get("seed", 4)),
              boat=bool(params.get("boat")))
    return finish_meta(b, "pier", st, {"deck_y": y, "water_level": wl, "floors": [y]})


# ------------------------------------------------------------------ kale
def castle_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    n = int(params.get("width") or max(33, round(43 * s)))
    n += 1 - n % 2
    return n + 8, n + 8


def castle(params: dict, ctx: dict | None = None) -> Build:
    """Surlu ortacag kalesi: kalin sur + seyirdim yolu + mazgal, kose yuvarlak kuleleri (kulahli), iki kuleli
    kapi binasi (kemerli gecit, kaldirilmis demir parmaklik), ic avluda burc (donjon: buyuk salon, taht salonu,
    silahlik), ahir, demirci, kuyu, sanclar, sura cikan merdivenler; isteğe bagli hendek."""
    st = get_style(params, ctx, "medieval")
    st = st.override(wall=[("stone_bricks", 0.5), ("cobblestone", 0.2), ("mossy_stone_bricks", 0.15), ("andesite", 0.15)],
                     wall2=[("stone_bricks", 0.6), ("cracked_stone_bricks", 0.2), ("mossy_stone_bricks", 0.2)],
                     roof=[("deepslate_tiles", 0.7), ("cobbled_deepslate", 0.3)])
    st = st.with_(motifs=frozenset(m for m in st.motifs if m not in ("jetty", "upper_timber", "timber")))
    FW, FD = castle_dims(params)
    N = FW - 8
    s = scale_of(params, 1.0)
    seed = int(params.get("seed", 21))
    b = Build(params.get("name") or "ortaçağ kalesi")
    g = ground_of(ctx, FW, FD)
    x0, z0 = 4, 4
    x1, z1 = x0 + N - 1, z0 + N - 1
    Hw = int(params.get("wall_h") or (8 if s < 1.3 else 10))       # sur yuksekligi (seyirdim yolu y=Hw)
    T_ = 3                                                         # sur kalinligi
    clear_volume(b, -2, 1, -2, FW + 1, Hw + 26, FD + 1)
    settle_on_ground(b, g, x0 - 3, z0 - 3, x1 + 3, z1 + 3, st, blend=5)
    b.fill(x0 - 3, 0, z0 - 3, x1 + 3, 0, z1 + 3, "grass_block")
    # --- sur: dis kabuk + dolgu + seyirdim yolu + mazgal
    for k in range(T_):
        sh = SH.shell_box(x0 + k, 1, z0 + k, x1 - k, Hw - 1, z1 - k, t=1, top=False, bottom=False)
        sh.put_style(b, st, "wall")
    walk = SH.shell_box(x0, Hw, z0, x1, Hw, z1, t=T_, top=False, bottom=False)
    walk.put_style(b, st, "floor_alt")
    P.crenellations(b, x0, z0, x1, z1, Hw + 1, st, role="wall", corbels=True, every=2)
    for (ix0, iz0, ix1, iz1) in ((x0 + T_, z0 + T_, x1 - T_, z1 - T_),):   # ic kenar: alcak korkuluk duvari
        for x in range(ix0 - 1, ix1 + 2):
            for z in (iz0 - 1, iz1 + 1):
                b.set(x, Hw + 1, z, st.wall_of("foundation"))
        for z in range(iz0 - 1, iz1 + 2):
            for x in (ix0 - 1, ix1 + 1):
                b.set(x, Hw + 1, z, st.wall_of("foundation"))
    # dis yuzde payandalar ve ok mazgallari (duz duvar yuzeyi kalmasin)
    gx = (x0 + x1) // 2
    for face, fx, fz, ln in (("south", x0, z1, N), ("west", x0, z0, N), ("east", x1, z0, N), ("north", x0, z0, N)):
        for k in range(8, ln - 7, 7):
            X, Z = (fx + k, fz) if face in ("north", "south") else (fx, fz + k)
            if face == "north" and abs(X - gx) <= 7:
                continue
            P.buttress(b, face, X, 1, Z, Hw - 2, st, depth=2)
            for dk in (-3, 3):
                XX, ZZ = (X + dk, Z) if face in ("north", "south") else (X, Z + dk)
                if face == "north" and abs(XX - gx) <= 7:
                    continue
                b.fill(XX, Hw - 4, ZZ, XX, Hw - 3, ZZ, "black_stained_glass_pane")   # ok mazgali (girinti yok)
    # --- kose kuleleri
    tr = 4 if N < 51 else 5
    th = Hw + 6
    corners = [(x0, z0), (x1, z0), (x0, z1), (x1, z1)]
    for (cx_, cz_) in corners:
        P.tower(b, cx_, 0, cz_, r=tr, h=th, st=st, top="cone" if params.get("roofs", True) else "crenel")
        # sur yolundan kuleye kapi (iki yonde)
        for (dx, dz) in ((1 if cx_ == x0 else -1, 0), (0, 1 if cz_ == z0 else -1)):
            X, Z = cx_ + dx * tr, cz_ + dz * tr
            b.fill(X, Hw + 1, Z, X, Hw + 2, Z, "air")
            b.set(X, Hw, Z, st.block("floor_alt"))
        light_shaft(b, cx_, cz_, 2, th - 2, r=tr - 1, every=4, level=13)
    # --- kapi binasi: on surun ortasinda iki kule + kemerli gecit
    gw = 3
    for (cx_, cz_) in ((gx - 6, z0), (gx + 6, z0)):
        P.tower(b, cx_, 0, cz_, r=4, h=Hw + 4, st=st, top="crenel")
        tower_door(b, cx_, cz_, 4, 1, "south", st, w=1)          # avludan kapi kulesine giris
        light_shaft(b, cx_, cz_, 2, Hw + 2, r=3, every=4, level=13)
    P.arched_gate(b, gx - 1, 1, z0, "north", w=gw, h=5, st=st, depth=T_, arch="round")
    for z in range(z0, z0 + T_):                       # gecit: tam aciklik, tas doseme
        b.fill(gx - 1, 1, z, gx + 1, 4, z, "air")
        st.fill(b, gx - 1, 0, z, gx + 1, 0, z, "floor_alt")
    # kaldirilmis demir parmaklik (yalniz ust sira: gecisi kapatmaz) + gecit isiklari
    for x in range(gx - 1, gx + 2):
        b.set(x, 4, z0, "iron_bars")
    if b.is_solid(gx, 5, z0 + 1):
        P.hanging_lamp(b, gx, 5, z0 + 1, st)
    for lx in (gx - 2, gx + 2):
        P.wall_lamp(b, lx, 4, z0, "north", st)
    # --- sura cikan merdivenler: ic yuze bitisik tas kol (alti dolu), ustte korkuluk acilir
    for (sx, dxw) in ((x0 + T_, -1), (x1 - T_, 1)):
        zz = z0 + T_ + 6
        for k in range(Hw):
            b.set(sx, 1 + k, zz + k, st.stairs("foundation", "south", "bottom"))
            if k:
                st.fill(b, sx, 1, zz + k, sx, k, zz + k, "foundation")
            b.fill(sx, 2 + k, zz + k, sx, 3 + k, zz + k, "air")
        for z in (zz + Hw - 1, zz + Hw):
            b.fill(sx + dxw, Hw + 1, z, sx + dxw, Hw + 2, z, "air")
    # --- burc (donjon)
    kw = 13 if N < 41 else 15
    kx0 = (x0 + x1) // 2 - kw // 2
    kz0 = z1 - T_ - kw - 3
    kx1, kz1 = kx0 + kw - 1, kz0 + kw - 1
    kfl = 3
    kfh = 5
    P.plinth(b, kx0 - 1, kz0 - 1, kx1 + 1, kz1 + 1, 0, st, h=1)
    shell = P.walls_box(b, kx0, 0, kz0, kx1, kfl * kfh - 1, kz1, st.with_(floor_h=kfh), floors=[0, kfh, 2 * kfh],
                        roles=["wall", "wall2", "wall2"], corner="quoins", cornice_top=False)
    ktop = kfl * kfh
    st.fill(b, kx0, ktop, kz0, kx1, ktop, kz1, "floor_alt")
    P.crenellations(b, kx0, kz0, kx1, kz1, ktop + 1, st, role="wall", corbels=True, every=2)
    for (cx_, cz_) in ((kx0, kz0), (kx1, kz0), (kx0, kz1), (kx1, kz1)):   # burc kose kuleleri (ustte)
        SH.cylinder((cx_, ktop + 1, cz_), (cx_, ktop + 4, cz_), 1.6, hollow=False).put_style(b, st, "wall")
        P.spire(b, cx_, ktop + 5, cz_, 2, 5, st, role="roof")
    P.flagpole(b, (kx0 + kx1) // 2, ktop + 1, (kz0 + kz1) // 2, st, h=7, color="red")
    kdx = (kx0 + kx1) // 2 - 1
    P.door(b, kdx, 1, kz0, "north", st, w=2, kind="arched", steps=1)
    for fi, fy in enumerate(shell["floors"]):
        P.window_row(b, kx0, fy + 2, kz0, "north", kw, st, w=1, h=2, kind="arched" if fi else "slit",
                     avoid=[(kdx, kdx + 1)] if fi == 0 else ())
        P.window_row(b, kx0, fy + 2, kz1, "south", kw, st, w=1, h=2, kind="arched" if fi else "slit")
        P.window_row(b, kx0, fy + 2, kz0, "west", kw, st, w=1, h=2, kind="arched" if fi else "slit")
        P.window_row(b, kx1, fy + 2, kz0, "east", kw, st, w=1, h=2, kind="arched" if fi else "slit")
    rooms_all, doors = [], [(kdx, 1, kz0), (kdx + 1, 1, kz0)]
    kinds = [["great_hall"], ["throne_hall"], ["armory", "master_bedroom"]]
    for fi, rb in enumerate(shell["rooms"]):
        rx0, ry0, rz0, rx1, ry1, rz1 = rb
        rooms = split_rooms(rx0, rz0, rx1, rz1, ry0, ry1 - ry0 + 1, kinds[fi], min_w=4, avoid_x=range(kdx - 1, kdx + 3))
        doors += partition_walls(b, rooms, st, ry0, ry1 - ry0 + 1, (rx0, rz0, rx1, rz1))
        rooms_all += rooms
    keep = [(kdx, 1, kz0 + 1), (kdx + 1, 1, kz0 + 1), (kdx, 1, kz0 + 2), (kdx + 1, 1, kz0 + 2)]
    for fi in range(kfl):
        fy = shell["floors"][fi]
        sx, sz = kx1 - 2 - 2 * (fi % 2), kz1 - 2
        upto = fy + kfh if fi < kfl - 1 else ktop
        keep += stair_keep(P.staircase(b, sx, fy + 1, sz, "north", rise=kfh, st=st, w=1))
        keep += stair_access(b, sx, sz, fy, kfh, bool(fi % 2))
    furnish_rooms(b, rooms_all, st, doors, seed, keep)
    perimeter_lamps(b, kx0, kz0, kx1, kz1, 3, st, every=5, skip=[(kdx - 1, kz0), (kdx + 2, kz0)])
    # --- avlu: yol, kuyu, ahir (sol sur dibinde sundurma), demirci (sag), fenerler
    ix0, iz0, ix1, iz1 = x0 + T_, z0 + T_, x1 - T_, z1 - T_
    P.path(b, [(gx, z0 + T_), (gx, kz0 - 3)], 0, st, w=3, border=True)
    wz = (z0 + kz0) // 2                              # kuyu, kapi kulesi kapisinin onunu (z0+5..z0+6) kapatmasin
    if wz - 1 <= z0 + 6 and z0 + 8 <= kz0 - 5:
        wz = z0 + 8
    P.well(b, gx + 5 if wz - 1 > z0 + 6 else gx + 9, 0, wz, st)
    sx0, sz0 = ix0 + 1, iz0 + 6 + Hw + 2              # ahir/demirci: sur merdivenlerinin arkasinda
    sw, sd = 5, min(12, z1 - T_ - sz0 - 1)
    if sd >= 6:
        for z in range(sz0, sz0 + sd):                        # ahir: tek egimli sundurma, bolmeler, saman
            b.set(sx0 + sw - 1, 1, z, "spruce_fence")
            for y in (1, 2, 3):
                b.set(sx0 + sw, y, z, "spruce_log[axis=y]") if (z - sz0) % 4 == 0 else None
        P.roof_shed(b, sx0 - 1, sz0 - 1, sx0 + sw, sz0 + sd, 4, st, facing="west")
        for z in range(sz0 + 1, sz0 + sd - 1, 3):
            b.set(sx0, 1, z, "hay_block[axis=y]")
            b.set(sx0 + 1, 1, z, "hay_block[axis=x]")
        b.set(sx0 + 2, 1, sz0 + sd - 2, "hay_block[axis=y]")
        if params.get("animals"):    # canlilar yalniz acik istekle (Usta guvenlik kurali)
            for z in range(sz0 + 2, sz0 + sd - 1, 4):
                b.add_entity("minecraft:horse", sx0 + 2.5, 1, z + 0.5, snbt="{PersistenceRequired:1b}")
        for z in range(sz0 + 2, sz0 + sd - 1, 4):
            _hang(b, sx0 + 2, z, 3, st)
    bx0 = ix1 - 6
    if sd >= 6:                                               # demirci
        P.roof_shed(b, bx0, sz0 - 1, ix1 + 1, sz0 + 6, 4, st, facing="east")
        b.set(bx0 + 2, 1, sz0 + 1, "anvil[facing=north]")
        b.set(bx0 + 4, 1, sz0 + 1, "blast_furnace[facing=west,lit=false]")
        b.set(bx0 + 4, 1, sz0 + 2, "smithing_table")
        b.set(bx0 + 4, 1, sz0 + 3, "grindstone[face=floor,facing=west]")
        b.set(bx0 + 1, 1, sz0 + 4, "barrel[facing=up]")
        b.set(bx0 + 3, 1, sz0 + 4, "cauldron")
        _hang(b, bx0 + 2, sz0 + 2, 3, st)
        _hang(b, bx0 + 4, sz0 + 5, 3, st)
    for (lx, lz) in ((gx - 4, iz0 + 2), (gx + 4, iz0 + 2), (gx - 4, kz0 - 3), (gx + 4, kz0 - 3)):
        P.lamp_post(b, lx, 1, lz, st, h=3)
    # --- hendek (istege bagli)
    if params.get("moat"):
        for x in range(x0 - 3, x1 + 4):
            for z in range(z0 - 3, z1 + 4):
                if (x < x0 - 1 or x > x1 + 1 or z < z0 - 1 or z > z1 + 1) and not (gx - 1 <= x <= gx + 1 and z < z0):
                    b.fill(x, -2, z, x, 0, z, "water")
        for x in range(gx - 1, gx + 2):
            for z in range(z0 - 3, z0 - 1):
                b.set(x, 0, z, "spruce_planks")
    return finish_meta(b, "castle", st, {"floors": [0, kfh, 2 * kfh], "door": [kdx, 1, kz0], "walls": [x0, z0, x1, z1],
                                         "gate": [gx, 1, z0]})


# ------------------------------------------------------------------ gozetleme kulesi
def watchtower_dims(params: dict) -> tuple[int, int]:
    s = scale_of(params, 1.0)
    r = 4 if s < 1.6 else 5
    return 2 * r + 9, 2 * r + 9


def watchtower(params: dict, ctx: dict | None = None) -> Build:
    """Gozetleme kulesi: yuvarlak tas govde, doner merdiven, mazgallar, mazgalli tepe, isaret atesi, sancak."""
    st = get_style(params, ctx, "medieval")
    s = scale_of(params, 1.0)
    FW, FD = watchtower_dims(params)
    r = 4 if s < 1.6 else 5
    h = int(params.get("height") or max(14, round(20 * s)))
    b = Build(params.get("name") or "gözetleme kulesi")
    g = ground_of(ctx, FW, FD)
    cx, cz = FW // 2, FD // 2
    clear_volume(b, 0, 1, 0, FW - 1, h + 12, FD - 1)
    settle_on_ground(b, g, cx - r - 2, cz - r - 2, cx + r + 2, cz + r + 2, st, blend=3)
    stw = st.with_(motifs=frozenset(m for m in st.motifs if m not in ("jetty", "upper_timber", "timber")))
    P.tower(b, cx, 0, cz, r=r, h=h, st=stw, top="crenel")
    tower_door(b, cx, cz, r, 1, "north", stw, w=1)
    light_shaft(b, cx, cz, 2, h - 2, r=r - 1, every=4, level=13)
    P.flagpole(b, cx + 1, h + 1, cz + 1, stw, h=5, color="red")
    P.path(b, [(cx, cz - r - 3), (cx, 0)], 0, st, w=3, border=False)
    for (lx, lz) in ((cx - 2, cz - r - 2), (cx + 2, cz - r - 2)):
        P.lamp_post(b, lx, 1, lz, st, h=3)
    return finish_meta(b, "watchtower", st, {"tower": [cx, cz, r, h], "floors": [0]})


register("arch_bridge", arch_bridge, bridge_dims,
         "Taş kemerli köprü: su tabanına inen ayaklar, sel yaranlar, kemer halkası, parapet ve fenerler, rampalar (z boyunca uzanır)",
         {"length": "uzunluk", "width": "5|7", "span": "kemer açıklığı", "arch": "segment|round"},
         lambda p: p.get("name") or "taş köprü")
register("lighthouse", lighthouse, lighthouse_dims,
         "Deniz feneri: kırmızı-beyaz şeritli kule, döner merdiven, galeri, camlı fener odası; bekçi evi; suya uzanan ahşap iskele ve kayık",
         {"size": "orta|büyük", "height": "kule yüksekliği", "boat": "True: iskelede kayık (açıkça istenirse)"}, lambda p: p.get("name") or "deniz feneri")
register("pier", pier, pier_dims, "Ahşap iskele: tabana inen kütük direkler, fenerli korkuluk, uç platform, variller, kayık",
         {"length": "uzunluk", "width": "genişlik", "boat": "True: kayık (açıkça istenirse)"}, lambda p: p.get("name") or "iskele")
register("castle", castle, castle_dims,
         "Ortaçağ kalesi: mazgallı kalın surlar ve seyirdim yolu, külahlı köşe kuleleri, iki kuleli kapı, burç (donjon), ahır, demirci, kuyu",
         {"size": "orta|büyük|devasa", "wall_h": "sur yüksekliği", "moat": False, "roofs": True, "animals": "True: ahırda atlar (açıkça istenirse)"},
         lambda p: p.get("name") or "ortaçağ kalesi")
register("watchtower", watchtower, watchtower_dims, "Gözetleme kulesi: yuvarlak taş gövde, döner merdiven, mazgallı tepe, sancak",
         {"size": "orta|büyük", "height": "yükseklik"}, lambda p: p.get("name") or "gözetleme kulesi")
