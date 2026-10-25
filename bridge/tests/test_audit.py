"""Denetci testleri: her kontrol icin bir olumlu (kusur var -> bulunur) ve bir olumsuz (temiz -> bulunmaz) ornek,
temiz ornek yapilarda yanlis alarm olcumu, rapor/puan sozlesmesi ve kaba basarim."""
import random
import time

import numpy as np
import pytest

import usta.audit as A
from usta.audit import (CHECKS, NEEDS_VISUAL, RUBRIC, audit, audit_plan, auto_scores, combine_scores,
                        false_alarm_rate)
from usta.kit.core import Build


# ====================================================================== yardimcilar
def has(b, cid, ctx=None, sev=None):
    r = audit(b, ctx, checks=[cid])
    assert not r.errors, r.errors
    return r.has(cid, sev)


def platform(n=6, block="stone"):
    b = Build("zemin")
    b.fill(0, 0, 0, n, 0, n, block)
    return b


def house(W=8, D=8, H=4, door=True, windows=True, roof="gable", lights=True, furniture=True, name="ev"):
    """Kucuk ama duzgun ev (testlerde olumsuz ornek tabani)."""
    b = Build(name)
    b.fill(0, 0, 0, W, 0, D, "stone_bricks")
    b.fill(1, 0, 1, W - 1, 0, D - 1, "spruce_planks")
    b.fill(0, 1, 0, W, H, D, "oak_planks", hollow=True)
    b.clear(1, 1, 1, W - 1, H, D - 1)
    for x in (0, W):
        for z in (0, D):
            b.fill(x, 1, z, x, H, z, "spruce_log")
    if door:
        b.set(W // 2, 1, 0, "oak_door[facing=south,half=lower]")
        b.set(W // 2, 2, 0, "oak_door[facing=south,half=upper]")
    if windows:
        for x in (2, W - 2):
            b.fill(x, 2, 0, x, 3, 0, "glass_pane")
            b.set(x, 1, -1, "spruce_stairs[facing=south,half=top]")
            b.fill(x, 2, D, x, 3, D, "glass_pane")
        for z in (2, D - 2):
            b.fill(0, 2, z, 0, 3, z, "glass_pane")
            b.fill(W, 2, z, W, 3, z, "glass_pane")
    if roof == "flat":
        b.fill(0, H + 1, 0, W, H + 1, D, "spruce_planks")
    elif roof == "gable":
        for i in range(D // 2 + 2):
            y = H + 1 + i
            z0, z1 = -1 + i, D + 1 - i
            if z0 < z1:
                b.fill(-1, y, z0, W + 1, y, z0, "dark_oak_stairs[facing=south]")
                b.fill(-1, y, z1, W + 1, y, z1, "dark_oak_stairs[facing=north]")
                if z0 + 1 <= z1 - 1:
                    b.fill(0, y, z0 + 1, 0, y, z1 - 1, "spruce_planks")
                    b.fill(W, y, z0 + 1, W, y, z1 - 1, "spruce_planks")
                    b.fill(1, y, z0 + 1, W - 1, y, z1 - 1, "air")
            else:
                b.fill(-1, y - 1, z0, W + 1, y - 1, z0, "spruce_planks")
                b.fill(-1, y, z0, W + 1, y, z0, "dark_oak_slab")
                break
    if lights:
        b.set(W // 2, 1, D // 2, "lantern")
        for z in (1, D - 1):
            b.set(1, 3, z, "wall_torch[facing=east]")
            b.set(W - 1, 3, z, "wall_torch[facing=west]")
        b.set(W // 2 - 1, 3, -1, "wall_torch[facing=north]")
    if furniture:
        b.set(1, 1, D - 2, "red_bed[facing=south,part=foot]")
        b.set(1, 1, D - 1, "red_bed[facing=south,part=head]")
        b.set(W - 1, 1, D - 1, "chest[facing=north]")
        b.set(W - 2, 1, D - 1, "crafting_table")
        b.fill(3, 1, 3, 5, 1, 3, "red_carpet")
    return b


# ====================================================================== temiz ornek yapilar
def cottage():
    b = Build("kulübe")
    W, D = 10, 8
    b.fill(0, 0, 0, W, 0, D, "stone_bricks")
    b.fill(1, 0, 1, W - 1, 0, D - 1, "spruce_planks")
    for x in range(0, W + 1, 3):
        b.set(x, 0, 0, "mossy_stone_bricks")
        b.set(x, 0, D, "cracked_stone_bricks")
    for z in range(0, D + 1, 3):
        b.set(0, 0, z, "cobblestone")
        b.set(W, 0, z, "cobblestone")
    b.fill(0, 1, 0, W, 4, D, "oak_planks", hollow=True)
    b.clear(1, 1, 1, W - 1, 4, D - 1)
    b.fill(0, 4, 0, W, 4, 0, "stripped_spruce_log[axis=x]")
    b.fill(0, 4, D, W, 4, D, "stripped_spruce_log[axis=x]")
    b.fill(0, 4, 0, 0, 4, D, "stripped_spruce_log[axis=z]")
    b.fill(W, 4, 0, W, 4, D, "stripped_spruce_log[axis=z]")
    for x in (0, W):
        for z in (0, D):
            b.fill(x, 1, z, x, 4, z, "spruce_log")
    for x in (4, 6):
        b.fill(x, 1, -1, x, 4, -1, "spruce_log")
    b.fill(-1, 1, 4, -1, 4, 4, "spruce_log")
    b.fill(W + 1, 1, 4, W + 1, 4, 4, "spruce_log")
    b.fill(5, 1, D + 1, 5, 4, D + 1, "spruce_log")
    b.set(5, 1, 0, "oak_door[facing=south,half=lower]")
    b.set(5, 2, 0, "oak_door[facing=south,half=upper]")
    for x in (2, 8):
        b.fill(x, 2, 0, x, 3, 0, "glass_pane")
        b.fill(x - 1, 2, -1, x - 1, 3, -1, "spruce_trapdoor[facing=north,open=true]")
        b.fill(x + 1, 2, -1, x + 1, 3, -1, "spruce_trapdoor[facing=north,open=true]")
        b.set(x, 1, -1, "spruce_stairs[facing=south,half=top]")
        b.fill(x, 2, D, x, 3, D, "glass_pane")
        b.set(x, 1, D + 1, "spruce_stairs[facing=north,half=top]")
    for z in (2, 6):
        b.fill(0, 2, z, 0, 3, z, "glass_pane")
        b.set(-1, 1, z, "spruce_stairs[facing=east,half=top]")
        b.fill(W, 2, z, W, 3, z, "glass_pane")
        b.set(W + 1, 1, z, "spruce_stairs[facing=west,half=top]")
    for i in range(6):
        y = 5 + i
        z0, z1 = -1 + i, D + 1 - i
        if z0 < z1:
            b.fill(-1, y, z0, W + 1, y, z0, "dark_oak_stairs[facing=south]")
            b.fill(-1, y, z1, W + 1, y, z1, "dark_oak_stairs[facing=north]")
            if z0 + 1 <= z1 - 1:
                b.fill(0, y, z0 + 1, 0, y, z1 - 1, "spruce_planks")
                b.fill(W, y, z0 + 1, W, y, z1 - 1, "spruce_planks")
        else:
            b.fill(-1, y - 1, z0, W + 1, y - 1, z0, "spruce_planks")
            b.fill(-1, y, z0, W + 1, y, z0, "dark_oak_slab")
    b.set(0, 6, 4, "glass_pane")
    b.set(W, 6, 4, "glass_pane")
    b.set(2, 1, 6, "red_bed[facing=south,part=foot]")
    b.set(2, 1, 7, "red_bed[facing=south,part=head]")
    b.set(1, 1, 7, "chest[facing=east]")
    b.set(8, 1, 7, "crafting_table")
    b.set(9, 1, 7, "furnace[facing=north]")
    b.set(9, 1, 6, "barrel[facing=up]")
    b.set(9, 1, 1, "bookshelf")
    b.set(9, 2, 1, "bookshelf")
    b.set(8, 1, 1, "bookshelf")
    b.set(5, 1, 5, "oak_fence")
    b.set(5, 2, 5, "oak_pressure_plate")
    b.set(4, 1, 5, "oak_stairs[facing=east]")
    b.set(6, 1, 5, "oak_stairs[facing=west]")
    b.fill(3, 1, 3, 7, 1, 3, "red_carpet")
    b.set(1, 1, 1, "potted_poppy")
    for z in (1, 4, 7):
        b.set(1, 3, z, "wall_torch[facing=east]")
        b.set(W - 1, 3, z, "wall_torch[facing=west]")
    b.fill(5, 5, 4, 5, 8, 4, "iron_chain[axis=y]")
    b.set(5, 4, 4, "lantern[hanging=true]")
    b.set(3, 8, 4, "lantern[hanging=true]")
    b.set(7, 8, 4, "lantern[hanging=true]")
    b.set(4, 3, -2, "wall_torch[facing=north]")
    b.set(6, 3, -2, "wall_torch[facing=north]")
    b.fill(5, 0, -1, 5, 0, -4, "dirt_path")
    for x in (2, 3, 7, 8):
        b.set(x, 0, -2, "grass_block")
        b.set(x, 1, -2, "poppy" if x in (2, 8) else "dandelion")
    for z in (2, 6):
        b.set(-2, 0, z, "grass_block")
        b.set(-2, 1, z, "oak_leaves[persistent=true]")
        b.set(W + 2, 0, z, "grass_block")
        b.set(W + 2, 1, z, "oak_leaves[persistent=true]")
    b.meta["rooms"].append({"name": "salon", "box": [1, 1, 1, W - 1, 4, D - 1]})
    b.meta["doors"].append({"pos": [5, 1, 0]})
    return b


def two_storey():
    b = Build("iki katlı ev")
    W, D = 12, 10
    b.fill(0, 0, 0, W, 0, D, "stone_bricks")
    b.fill(1, 0, 1, W - 1, 0, D - 1, "spruce_planks")
    for x in range(0, W + 1, 4):
        b.set(x, 0, 0, "mossy_stone_bricks")
        b.set(x, 0, D, "cracked_stone_bricks")
    b.fill(0, 1, 0, W, 4, D, "cobblestone", hollow=True)
    b.fill(0, 6, 0, W, 9, D, "spruce_planks", hollow=True)
    b.clear(1, 1, 1, W - 1, 4, D - 1)
    b.clear(1, 6, 1, W - 1, 9, D - 1)
    b.fill(0, 5, 0, W, 5, D, "dark_oak_planks")
    b.fill(1, 5, 1, W - 1, 5, D - 1, "oak_planks")
    b.fill(-1, 5, -1, W + 1, 5, -1, "dark_oak_stairs[facing=south,half=top]")
    b.fill(-1, 5, D + 1, W + 1, 5, D + 1, "dark_oak_stairs[facing=north,half=top]")
    b.fill(-1, 5, 0, -1, 5, D, "dark_oak_stairs[facing=east,half=top]")
    b.fill(W + 1, 5, 0, W + 1, 5, D, "dark_oak_stairs[facing=west,half=top]")
    for x in (0, 4, 8, W):
        b.fill(x, 1, 0, x, 9, 0, "dark_oak_log")
        b.fill(x, 1, D, x, 9, D, "dark_oak_log")
    for z in (0, 5, D):
        b.fill(0, 1, z, 0, 9, z, "dark_oak_log")
        b.fill(W, 1, z, W, 9, z, "dark_oak_log")
    b.set(6, 1, 0, "spruce_door[facing=south,half=lower]")
    b.set(6, 2, 0, "spruce_door[facing=south,half=upper]")
    for x in (2, 10):
        b.fill(x, 2, 0, x, 3, 0, "glass_pane")
        b.set(x, 1, -1, "stone_brick_stairs[facing=south,half=top]")
        b.fill(x - 1, 2, -1, x - 1, 3, -1, "spruce_trapdoor[facing=north,open=true]")
        b.fill(x + 1, 2, -1, x + 1, 3, -1, "spruce_trapdoor[facing=north,open=true]")
    for x in (2, 6, 10):
        b.fill(x, 7, 0, x, 8, 0, "glass_pane")
        b.set(x, 6, -1, "spruce_trapdoor[facing=north,half=top]")
        b.fill(x, 2, D, x, 3, D, "glass_pane")
        b.fill(x, 7, D, x, 8, D, "glass_pane")
        b.set(x, 1, D + 1, "stone_brick_stairs[facing=north,half=top]")
        b.set(x, 6, D + 1, "spruce_trapdoor[facing=south,half=top]")
    for z in (2, 8):
        for x, f in ((0, "east"), (W, "west")):
            b.fill(x, 2, z, x, 3, z, "glass_pane")
            b.fill(x, 7, z, x, 8, z, "glass_pane")
            xo = x - 1 if x == 0 else x + 1
            b.set(xo, 1, z, "stone_brick_stairs[facing=%s,half=top]" % f)
            b.set(xo, 6, z, "spruce_trapdoor[facing=%s,half=top]" % ("west" if x == 0 else "east"))
    for i in range(4):  # ic merdiven: dogu duvari boyunca +z'ye yukselir
        b.set(W - 1, 1 + i, 2 + i, "spruce_stairs[facing=south]")
        if i:
            b.fill(W - 1, 1, 2 + i, W - 1, i, 2 + i, "spruce_planks")
    b.clear(W - 1, 5, 2, W - 1, 5, 5)
    b.fill(W - 2, 6, 2, W - 2, 6, 5, "spruce_fence")
    for i in range(8):
        y = 10 + i
        x0, x1 = -1 + i, W + 1 - i
        if x0 < x1:
            b.fill(x0, y, -1, x0, y, D + 1, "deepslate_tile_stairs[facing=east]")
            b.fill(x1, y, -1, x1, y, D + 1, "deepslate_tile_stairs[facing=west]")
            if x0 + 1 <= x1 - 1:
                b.fill(x0 + 1, y, 0, x1 - 1, y, 0, "spruce_planks")
                b.fill(x0 + 1, y, D, x1 - 1, y, D, "spruce_planks")
        else:
            b.fill(x0, y - 1, -1, x0, y - 1, D + 1, "spruce_planks")
            b.fill(x0, y, -1, x0, y, D + 1, "deepslate_tile_slab")
            break
    b.fill(0, 10, 0, W, 17, D, "air", only_empty=True)
    b.fill(0, 10, 5, W, 10, 5, "dark_oak_log[axis=x]")
    b.fill(6, 12, 0, 6, 13, 0, "glass_pane")
    b.fill(6, 12, D, 6, 13, D, "glass_pane")
    b.set(1, 1, 9, "crafting_table")
    b.set(2, 1, 9, "furnace[facing=south]")
    b.set(3, 1, 9, "smoker[facing=south]")
    b.set(4, 1, 9, "barrel[facing=up]")
    b.set(1, 1, 8, "chest[facing=east]")
    for x in (5, 6):
        b.set(x, 1, 5, "spruce_fence")
        b.set(x, 2, 5, "spruce_pressure_plate")
    b.set(4, 1, 5, "spruce_stairs[facing=east]")
    b.set(7, 1, 5, "spruce_stairs[facing=west]")
    b.fill(3, 1, 3, 8, 1, 3, "green_carpet")
    b.set(1, 1, 1, "potted_fern")
    b.set(1, 1, 2, "bookshelf")
    b.set(1, 2, 2, "bookshelf")
    b.set(2, 6, 8, "blue_bed[facing=south,part=foot]")
    b.set(2, 6, 9, "blue_bed[facing=south,part=head]")
    b.set(3, 6, 9, "chest[facing=north]")
    b.set(1, 6, 9, "barrel[facing=up]")
    b.fill(2, 6, 3, 6, 6, 6, "white_carpet")
    b.set(8, 6, 9, "bookshelf")
    b.set(9, 6, 9, "bookshelf")
    b.set(8, 7, 9, "bookshelf")
    b.set(5, 6, 1, "cartography_table")
    b.set(1, 6, 1, "potted_poppy")
    for z in (3, 7):
        b.set(1, 3, z, "wall_torch[facing=east]")
        b.set(1, 8, z, "wall_torch[facing=east]")
    b.set(5, 4, 7, "lantern[hanging=true]")
    b.set(8, 4, 7, "lantern[hanging=true]")
    b.set(5, 4, 2, "lantern[hanging=true]")
    b.set(W - 1, 3, 6, "wall_torch[facing=west]")
    b.set(W - 1, 8, 6, "wall_torch[facing=west]")
    b.set(5, 9, 5, "lantern[hanging=true]")
    b.set(9, 9, 5, "lantern[hanging=true]")
    b.set(5, 3, -1, "wall_torch[facing=north]")
    b.set(7, 3, -1, "wall_torch[facing=north]")
    b.fill(6, 0, -1, 6, 0, -4, "dirt_path")
    for x in (3, 9):
        b.set(x, 0, -3, "grass_block")
        b.set(x, 1, -3, "rose_bush[half=lower]")
        b.set(x, 2, -3, "rose_bush[half=upper]")
    b.meta["rooms"] += [{"name": "mutfak", "box": [1, 1, 1, W - 1, 4, D - 1]},
                        {"name": "yatak odası", "box": [1, 6, 1, W - 1, 9, D - 1]}]
    b.meta["floors"] = [0, 5]
    return b


def tower():
    b = Build("gözcü kulesi")
    S, H = 6, 15
    b.fill(0, 0, 0, S, 0, S, "stone_bricks")
    b.fill(0, 1, 0, S, H - 1, S, "stone_bricks", hollow=True)
    b.clear(1, 1, 1, S - 1, H - 1, S - 1)
    rnd = random.Random(3)
    for y in range(0, H):
        for x in range(0, S + 1):
            for z in range(0, S + 1):
                if b.get(x, y, z) == "minecraft:stone_bricks" and rnd.random() < 0.3:
                    b.set(x, y, z, rnd.choice(["mossy_stone_bricks", "cracked_stone_bricks", "andesite"]))
    for x, z in ((-1, -1), (-1, S + 1), (S + 1, -1), (S + 1, S + 1)):
        b.fill(x, 0, z, x, 4, z, "cobblestone")
        b.set(x, 5, z, "cobblestone_wall")
    for x, z in ((-1, 0), (0, -1), (-1, S), (0, S + 1), (S + 1, 0), (S, -1), (S + 1, S), (S, S + 1)):
        b.fill(x, 0, z, x, 2, z, "cobblestone")
    for y in (5, 10):
        b.fill(1, y, 1, S - 1, y, S - 1, "spruce_planks")
    for y in range(1, 13):
        b.set(1, y, 4, "ladder[facing=east]")
    b.set(3, 1, 0, "spruce_door[facing=south,half=lower]")
    b.set(3, 2, 0, "spruce_door[facing=south,half=upper]")
    b.set(2, 3, -1, "wall_torch[facing=north]")
    b.set(4, 3, -1, "wall_torch[facing=north]")
    for y0 in (2, 7, 12):
        b.fill(3, y0, S, 3, y0 + 1, S, "glass_pane")
        b.set(3, y0 - 1, S + 1, "stone_brick_slab[type=top]")
        b.fill(S, y0, 3, S, y0 + 1, 3, "glass_pane")
        b.set(S + 1, y0 - 1, 3, "stone_brick_slab[type=top]")
        b.fill(0, y0, 3, 0, y0 + 1, 3, "glass_pane")
        b.set(-1, y0 - 1, 3, "stone_brick_slab[type=top]")
        if y0 != 2:
            b.fill(3, y0, 0, 3, y0 + 1, 0, "glass_pane")
            b.set(3, y0 - 1, -1, "stone_brick_slab[type=top]")
    for y in (5, 10):
        b.fill(-1, y, -1, S + 1, y, -1, "stone_brick_slab[type=top]")
        b.fill(-1, y, S + 1, S + 1, y, S + 1, "stone_brick_slab[type=top]")
        b.fill(-1, y, 0, -1, y, S, "stone_brick_slab[type=top]")
        b.fill(S + 1, y, 0, S + 1, y, S, "stone_brick_slab[type=top]")
    b.fill(-1, H, -1, S + 1, H, S + 1, "stone_bricks")
    for i in range(6):
        y = H + 1 + i
        a, c = -1 + i, S + 1 - i
        if a == c:
            b.set(a, y, a, "dark_oak_planks")
            b.set(a, y + 1, a, "lightning_rod")
            break
        b.fill(a, y, a, c, y, a, "dark_oak_stairs[facing=south]")
        b.fill(a, y, c, c, y, c, "dark_oak_stairs[facing=north]")
        b.fill(a, y, a + 1, a, y, c - 1, "dark_oak_stairs[facing=east]")
        b.fill(c, y, a + 1, c, y, c - 1, "dark_oak_stairs[facing=west]")
        if a + 1 <= c - 1:
            b.fill(a + 1, y, a + 1, c - 1, y, c - 1, "dark_oak_planks")
    for y in (1, 6, 11):
        b.set(5, y, 5, "barrel[facing=up]")
        b.set(4, y, 5, "chest[facing=north]")
        b.set(5, y, 4, "crafting_table" if y == 1 else "bookshelf")
        b.set(3, y, 3, "red_carpet")
        b.set(2, y, 2, "red_carpet")
        b.set(5, y + 2, 1, "wall_torch[facing=west]")
        b.set(1, y + 2, 5, "wall_torch[facing=east]")
        b.set(3, y + 3, 3, "lantern[hanging=true]")
    b.meta["rooms"] += [{"name": "giriş katı", "box": [1, 1, 1, 5, 4, 5], "type": "giriş"},
                        {"name": "orta kat", "box": [1, 6, 1, 5, 9, 5]},
                        {"name": "gözcü odası", "box": [1, 11, 1, 5, 14, 5]}]
    b.meta["floors"] = [0, 5, 10]
    return b


def garden():
    b = Build("çeşmeli bahçe")
    N = 16
    b.fill(0, 0, 0, N, 0, N, "grass_block")
    b.fill(8, 0, 0, 8, 0, N, "dirt_path")
    b.fill(0, 0, 8, N, 0, 8, "dirt_path")
    b.fill(5, 0, 5, 11, 0, 11, "stone_bricks")
    b.fill(5, 1, 5, 11, 1, 11, "stone_bricks", hollow=True)
    b.fill(6, 1, 6, 10, 1, 10, "water")
    b.fill(8, 1, 8, 8, 3, 8, "chiseled_stone_bricks")
    b.set(8, 4, 8, "stone_brick_slab")
    for x, z in ((5, 5), (5, 11), (11, 5), (11, 11)):
        b.set(x, 2, z, "stone_brick_wall")
        b.set(x, 3, z, "lantern")
    for i in range(N + 1):
        for x, z in ((i, 0), (i, N), (0, i), (N, i)):
            if x != 8 and z != 8:
                b.set(x, 1, z, "oak_leaves[persistent=true]")
    fl = ["poppy", "dandelion", "cornflower", "allium", "oxeye_daisy", "azure_bluet"]
    k = 0
    for x in range(2, 15):
        for z in (2, 3, 13, 14):
            if x in (7, 8, 9):
                continue
            b.set(x, 1, z, fl[k % len(fl)])
            k += 1
    for z in (5, 11):
        for x in (2, 14):
            b.set(x, 1, z, "rose_bush[half=lower]")
            b.set(x, 2, z, "rose_bush[half=upper]")
    for x in (3, 13):
        b.set(x, 1, 7, "oak_stairs[facing=south]")
        b.set(x, 1, 9, "oak_stairs[facing=north]")
    for x, z in ((6, 3), (10, 3), (6, 13), (10, 13), (3, 6), (13, 6)):
        b.fill(x, 1, z, x, 2, z, "spruce_fence")
        b.set(x, 3, z, "lantern")
    for (tx, tz) in ((3, 11), (13, 11)):
        b.fill(tx, 1, tz, tx, 4, tz, "oak_log")
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for dy in (4, 5):
                    if abs(dx) + abs(dz) <= (3 if dy == 4 else 2) and not (dx == 0 and dz == 0 and dy == 4):
                        if b.get(tx + dx, dy, tz + dz) in ("keep", "minecraft:air"):
                            b.set(tx + dx, dy, tz + dz, "oak_leaves[persistent=true]")
        b.set(tx, 6, tz, "oak_leaves[persistent=true]")
    return b


CLEAN = [cottage, two_storey, tower, garden]


# ====================================================================== sozlesme
def test_registry_and_docstring():
    assert len(CHECKS) >= 25
    doc = A.__doc__
    for cid, chk in CHECKS.items():
        assert cid in doc, cid
        assert chk.description and chk.group
    for req in ("flat_wall", "monotone_block", "proportion", "floating_blocks", "stair_orientation", "unsupported_attachables",
                "broken_doors", "broken_beds", "unreachable_rooms", "no_entrance", "dark_spots", "fluid_leak", "fire_hazard",
                "unsupported_gravity", "cliff_cut", "structure_overlap", "protected_overlap", "unknown_blocks",
                "dangerous_blocks", "window_presence", "roof_presence", "empty_interior", "lighting_density",
                "palette_variety", "symmetry_rhythm", "stair_walkability", "headroom", "hanging_without_support",
                "waterlogged_anomaly", "entity_on_solid"):
        assert req in CHECKS, req


def test_report_contract_and_scores():
    r = audit(house(lights=False))
    d = r.to_dict()
    for k in ("score", "critical", "major", "minor", "findings", "auto_scores"):
        assert k in d
    assert 0 <= d["score"] <= 100 and d["findings"]
    f = d["findings"][0]
    assert set(("check", "severity", "message", "fix", "positions")) <= set(f)
    assert f["severity"] in ("critical", "major", "minor")
    sev = [x["severity"] for x in d["findings"]]
    assert sev == sorted(sev, key=lambda s: ("critical", "major", "minor").index(s))
    a = auto_scores(r, None)
    assert list(a) == list(RUBRIC)
    assert a["tarz sadakati"][0] == NEEDS_VISUAL
    assert isinstance(a["teknik temizlik"][0], float)
    assert a["aydınlatma ve canavar güvenliği"][0] < 10
    c = combine_scores(a, {"tarz sadakati": 8, "isteğe uygunluk": 7})
    assert 0 <= c["total"] <= 100 and not c["missing"]
    assert "Denetim" in r.summary()


def test_audit_plan_roundtrip_rotated():
    b = cottage()
    plan = b.to_plan((100, 64, 200), "east", meta={"rooms": b.meta["rooms"]})
    d = audit_plan(plan)
    assert d["score"] >= 90, d["findings"][:3]
    assert d["critical"] == 0


# ====================================================================== yanlis alarm
def test_false_alarm_rate_on_clean_samples():
    res = false_alarm_rate([f() for f in CLEAN])
    assert res["samples"] == 4 and res["checks"] >= 30
    for d in res["details"]:
        assert not d["errors"], d
    assert res["rate"] <= 0.01, res["details"]


# ====================================================================== kontrol basina olumlu / olumsuz
def test_empty_build():
    assert has(Build("bos"), "empty_build")
    assert not has(platform(), "empty_build")


def test_unknown_blocks():
    b = platform()
    b.palette.append("minecraft:uydurma_blok")
    b.set(1, 1, 1, len(b.palette) - 1)
    assert has(b, "unknown_blocks", sev="critical")
    assert not has(platform(), "unknown_blocks")


def test_orphan_block_entity():
    b = platform()
    b.set(1, 1, 1, "stone")
    b.set_block_entity(1, 1, 1, '{Items:[]}')
    assert has(b, "orphan_block_entity")
    b2 = platform()
    b2.set(1, 1, 1, "chest")
    b2.set_block_entity(1, 1, 1, '{Items:[]}')
    assert not has(b2, "orphan_block_entity")


def test_dangerous_blocks():
    b = platform()
    b.set(2, 1, 2, "tnt")
    assert has(b, "dangerous_blocks", sev="critical")
    assert not has(platform(), "dangerous_blocks")


def test_fire_hazard():
    b = platform()
    b.set(3, 1, 3, "netherrack")
    b.set(3, 2, 3, "fire")
    b.fill(5, 1, 3, 5, 3, 3, "oak_planks")
    assert has(b, "fire_hazard", sev="critical")
    c = platform()
    c.set(3, 1, 3, "campfire[lit=true]")
    c.set(3, 3, 3, "oak_planks")
    assert has(c, "fire_hazard", sev="minor")
    ok = platform()
    ok.set(3, 1, 3, "netherrack")
    ok.set(3, 2, 3, "fire")
    ok.set(3, 1, 0, "campfire[lit=true]")
    assert not has(ok, "fire_hazard")


def basin(fluid="water", n=6):
    b = platform(n, "stone_bricks")
    b.fill(0, 1, 0, n, 1, n, "stone_bricks", hollow=True)
    b.fill(1, 1, 1, n - 1, 1, n - 1, fluid)
    return b


def test_fluid_leak():
    b = platform()
    b.set(3, 1, 3, "water")
    assert has(b, "fluid_leak", sev="major")
    assert not has(basin(), "fluid_leak")
    edge = Build("kenar")
    edge.set(0, 1, 0, "water")
    edge.set(0, 0, 0, "stone")
    assert has(edge, "fluid_leak")


def test_fluid_mix():
    b = basin()
    b.set(1, 1, 1, "lava")
    assert has(b, "fluid_mix")
    ok = basin()
    ok.fill(1, 1, 1, 1, 1, 5, "stone")
    ok.fill(2, 1, 1, 2, 1, 5, "stone")
    ok.set(1, 1, 1, "lava")
    assert not has(ok, "fluid_mix")


def test_waterlogged_anomaly():
    b = platform()
    b.set(2, 1, 2, "oak_slab[waterlogged=true]")
    assert has(b, "waterlogged_anomaly", sev="major")
    dry = basin()
    dry.set(3, 1, 3, "oak_fence[waterlogged=false]")
    dry.fill(1, 2, 1, 5, 2, 5, "water")
    dry.fill(0, 2, 0, 6, 2, 6, "stone_bricks", hollow=True)
    dry.fill(1, 2, 1, 5, 2, 5, "water")
    assert has(dry, "waterlogged_anomaly", sev="minor")
    ok = basin()
    ok.set(3, 1, 3, "oak_slab[waterlogged=true]")
    assert not has(ok, "waterlogged_anomaly")


def test_unsupported_gravity():
    b = platform()
    b.fill(0, 1, 0, 0, 3, 0, "stone")
    b.set(1, 3, 0, "sand")
    assert has(b, "unsupported_gravity")
    ok = platform()
    ok.set(1, 1, 0, "sand")
    ok.set(1, 2, 0, "gravel")
    assert not has(ok, "unsupported_gravity")


def test_unsupported_attachables():
    b = platform()
    b.set(2, 1, 2, "wall_torch[facing=north]")
    assert has(b, "unsupported_attachables")
    f = platform()
    f.set(2, 1, 2, "poppy")
    assert has(f, "unsupported_attachables")
    c = platform()
    c.set(2, 2, 2, "white_carpet")
    c.set(2, 1, 2, "air")
    assert has(c, "unsupported_attachables")
    ok = platform()
    ok.fill(0, 1, 3, 6, 3, 3, "stone_bricks")
    ok.set(2, 2, 2, "wall_torch[facing=north]")
    ok.set(4, 2, 2, "ladder[facing=north]")
    ok.set(5, 2, 2, "stone_button[face=wall,facing=north]")
    ok.set(1, 1, 1, "torch")
    ok.set(5, 1, 1, "white_carpet")
    ok.set(0, 0, 0, "grass_block")
    ok.set(0, 1, 0, "poppy")
    ok.set(6, 1, 0, "oak_fence")
    ok.set(6, 2, 0, "lantern")
    assert not has(ok, "unsupported_attachables")


def test_hanging_without_support():
    b = platform()
    b.set(2, 3, 2, "lantern[hanging=true]")
    assert has(b, "hanging_without_support", sev="major")
    ch = platform()
    ch.fill(2, 2, 2, 2, 3, 2, "iron_chain[axis=y]")
    ch.set(2, 1, 2, "lantern[hanging=true]") if False else None
    assert has(ch, "hanging_without_support", sev="minor")
    ok = platform()
    ok.fill(0, 1, 0, 0, 5, 0, "stone")
    ok.fill(0, 5, 0, 4, 5, 0, "stone_bricks")
    ok.set(2, 4, 0, "lantern[hanging=true]")
    ok.fill(4, 3, 0, 4, 4, 0, "iron_chain[axis=y]")
    ok.set(4, 2, 0, "lantern[hanging=true]")
    assert not has(ok, "hanging_without_support")


def test_broken_doors():
    b = platform()
    b.set(2, 1, 2, "oak_door[half=lower]")
    assert has(b, "broken_doors", sev="major")
    fl = Build("havada kapı")
    fl.set(0, 0, 0, "stone")
    fl.set(2, 3, 2, "oak_door[half=lower]")
    fl.set(2, 4, 2, "oak_door[half=upper]")
    assert has(fl, "broken_doors", sev="major")
    ok = platform()
    ok.set(2, 1, 2, "oak_door[half=lower,facing=south]")
    ok.set(2, 2, 2, "oak_door[half=upper,facing=south]")
    assert not has(ok, "broken_doors")


def test_broken_beds():
    b = platform()
    b.set(2, 1, 2, "red_bed[facing=north,part=foot]")
    assert has(b, "broken_beds")
    wrong = platform()
    wrong.set(2, 1, 2, "red_bed[facing=north,part=foot]")
    wrong.set(2, 1, 3, "red_bed[facing=north,part=head]")
    assert has(wrong, "broken_beds")
    ok = platform()
    ok.set(2, 1, 2, "red_bed[facing=north,part=foot]")
    ok.set(2, 1, 1, "red_bed[facing=north,part=head]")
    assert not has(ok, "broken_beds")


def test_broken_double_plants():
    b = platform(block="grass_block")
    b.set(2, 1, 2, "tall_grass[half=lower]")
    assert has(b, "broken_double_plants")
    ok = platform(block="grass_block")
    ok.set(2, 1, 2, "sunflower[half=lower]")
    ok.set(2, 2, 2, "sunflower[half=upper]")
    assert not has(ok, "broken_double_plants")


def flight(facing="east", n=4, half="bottom"):
    b = platform(8)
    for i in range(n):
        b.set(1 + i, 1 + i, 3, f"stone_brick_stairs[facing={facing},half={half}]")
        if i:
            b.fill(1 + i, 1, 3, 1 + i, i, 3, "stone_bricks")
    b.fill(1 + n, 1, 3, 1 + n, n, 3, "stone_bricks")
    return b


def test_stair_orientation():
    assert has(flight("west"), "stair_orientation")
    mid = flight("east")
    mid.set(3, 3, 3, "stone_brick_stairs[facing=east,half=top]")
    assert has(mid, "stair_orientation")
    assert not has(flight("east"), "stair_orientation")
    assert not has(cottage(), "stair_orientation")


def test_stair_walkability():
    # ust kat havadan bagli (bosluk) ama merdiven yok
    b = house(W=8, D=8, H=9, roof="flat", windows=False)
    b.fill(1, 5, 1, 7, 5, 7, "oak_planks")
    b.clear(6, 5, 5, 6, 5, 6)
    b.meta["rooms"] += [{"name": "alt", "box": [1, 1, 1, 7, 4, 7]}, {"name": "üst", "box": [1, 6, 1, 7, 9, 7]}]
    assert has(b, "stair_walkability", sev="major")
    # dusuk tavanli merdiven
    low = flight("east")
    low.fill(0, 4, 0, 8, 4, 8, "stone_bricks")
    low.fill(0, 1, 0, 0, 3, 8, "stone_bricks")
    assert has(low, "stair_walkability")
    assert not has(two_storey(), "stair_walkability")
    assert not has(flight("east"), "stair_walkability")


def test_headroom():
    b = house()
    b.set(4, 2, -1, "stone")
    assert has(b, "headroom", sev="major")
    nowhere = house()
    nowhere.set(4, 1, 0, "oak_planks")
    nowhere.set(4, 2, 0, "oak_planks")
    nowhere.set(2, 6, 0, "oak_door[facing=south,half=lower]") if False else None
    p = platform()
    p.set(2, 0, 2, "dirt_path")
    p.set(2, 2, 2, "stone")
    p.fill(0, 1, 0, 0, 2, 0, "stone")
    p.fill(0, 2, 0, 2, 2, 0, "stone")
    p.fill(2, 2, 0, 2, 2, 2, "stone")
    assert has(p, "headroom", sev="minor")
    assert not has(house(), "headroom")


def test_no_entrance():
    assert has(house(door=False), "no_entrance", sev="critical")
    assert not has(house(), "no_entrance")


def test_unreachable_rooms():
    b = house(W=12, D=8, roof="flat")
    b.fill(8, 1, 1, 8, 4, 7, "oak_planks")  # bolme duvari (tavana kadar), kapisiz
    assert has(b, "unreachable_rooms")
    vault = house(W=12, D=8)                # tonozlu catida bolme ustu acik: odalar baglidir
    vault.fill(8, 1, 1, 8, 4, 7, "oak_planks")
    assert not has(vault, "unreachable_rooms")
    ok = house(W=12, D=8, roof="flat")
    ok.fill(8, 1, 1, 8, 4, 7, "oak_planks")
    ok.set(8, 1, 4, "oak_door[facing=east,half=lower]")
    ok.set(8, 2, 4, "oak_door[facing=east,half=upper]")
    assert not has(ok, "unreachable_rooms")


def test_entity_on_solid():
    b = platform()
    b.add_entity("minecraft:painting", 2.5, 2.5, 2.5, snbt="{facing:2b}")
    assert has(b, "entity_on_solid")
    ok = platform()
    ok.fill(0, 1, 3, 6, 3, 3, "stone_bricks")
    ok.add_entity("minecraft:painting", 2.5, 2.5, 2.5, snbt="{facing:2b,variant:\"minecraft:kebab\"}")
    ok.add_entity("minecraft:item_frame", 4.5, 2.5, 2.5, snbt="{Facing:2b}")
    assert not has(ok, "entity_on_solid")


def test_structure_overlap():
    ctx = {"structures": [{"box": [2, 0, 2, 9, 4, 9], "name": "komşu ev"}]}
    assert has(platform(), "structure_overlap", ctx)
    assert not has(platform(), "structure_overlap", {"structures": [[20, 0, 20, 25, 5, 25]]})


def test_protected_overlap():
    assert has(platform(), "protected_overlap", {"protected": [[0, 0, 0, 1, 1, 1]]}, sev="critical")
    m = np.zeros((2, 2, 2), bool)
    m[0, 0, 0] = True
    assert has(platform(), "protected_overlap", {"protected_mask": {"origin": (3, 0, 3), "mask": m}})
    assert not has(platform(), "protected_overlap", {"protected": [[30, 0, 30, 31, 1, 31]]})


def test_cliff_cut():
    hm = np.full((20, 20), 6)
    ctx = {"heightmap": hm, "heightmap_origin": (-5, -5)}
    assert has(platform(), "cliff_cut", ctx)
    flat = {"heightmap": np.full((20, 20), -1), "heightmap_origin": (-5, -5)}
    assert not has(platform(), "cliff_cut", flat)
    assert not has(platform(), "cliff_cut")


def test_floating_blocks():
    b = platform()
    b.set(3, 6, 3, "stone_bricks")
    assert has(b, "floating_blocks")
    ok = platform()
    ok.fill(3, 1, 3, 3, 6, 3, "stone_bricks")
    assert not has(ok, "floating_blocks")
    anchored = platform()
    anchored.set(3, 6, 3, "stone_bricks")
    assert not has(anchored, "floating_blocks", {"anchors": [(3, 6, 3)]})


def wall(W=13, H=7, relief=False):
    b = Build("duvar")
    b.fill(0, 0, 0, W - 1, H - 1, 1, "stone_bricks")
    if relief:
        for x in range(0, W, 3):
            b.fill(x, 0, -1, x, H - 1, -1, "spruce_log")
        for x in range(1, W, 3):
            b.fill(x, 2, 0, x, 3, 0, "glass_pane")
    return b


def test_flat_wall():
    assert has(wall(), "flat_wall")
    assert has(wall(W=20, H=10), "flat_wall", sev="major")
    r = audit(wall(relief=True), checks=["flat_wall"])
    assert not [f for f in r.findings if f.data.get("side") == "north"]   # arka yuz (south) gercekten duz
    assert [f for f in audit(wall(), checks=["flat_wall"]).findings if f.data.get("side") == "north"]
    assert not has(cottage(), "flat_wall")


def test_monotone_block():
    b = Build("tek tip")
    b.fill(0, 0, 0, 10, 6, 10, "stone_bricks", hollow=True)
    assert has(b, "monotone_block", sev="major")
    assert not has(cottage(), "monotone_block")


def test_proportion():
    b = Build("kütle")
    b.fill(0, 0, 0, 2, 24, 2, "stone_bricks")
    assert has(b, "proportion")
    low = house(W=8, D=8, H=2, roof="flat")
    assert has(low, "proportion")
    assert not has(cottage(), "proportion")
    k = Build("minare kulesi")
    k.fill(0, 0, 0, 2, 24, 2, "stone_bricks")
    assert not has(k, "proportion")


def test_palette_variety():
    b = Build("tek aile")
    b.fill(0, 0, 0, 10, 5, 10, "stone_bricks", hollow=True)
    b.fill(0, 6, 0, 10, 6, 10, "stone_brick_slab")
    assert has(b, "palette_variety")
    many = Build("karmaşa")
    mats = ["stone_bricks", "oak_planks", "bricks", "sandstone", "deepslate_tiles", "prismarine", "purpur_block",
            "quartz_block", "mud_bricks", "end_stone_bricks", "nether_bricks", "copper_block", "blackstone"]
    for i, m in enumerate(mats):
        many.fill(i * 2, 0, 0, i * 2 + 1, 4, 3, m)
    assert has(many, "palette_variety")
    assert not has(cottage(), "palette_variety")


def test_window_presence():
    assert has(house(windows=False), "window_presence")
    assert not has(house(), "window_presence")


def test_roof_presence():
    assert has(house(roof=None, W=8, D=8, H=5), "roof_presence")
    assert not has(house(), "roof_presence")


def test_empty_interior():
    assert has(house(W=9, D=9, furniture=False), "empty_interior")
    assert not has(house(W=9, D=9), "empty_interior")


def test_lighting_density():
    b = house(W=14, D=14, lights=False, roof="flat")
    b.set(1, 2, 1, "wall_torch[facing=east]")
    assert has(b, "lighting_density")
    assert not has(cottage(), "lighting_density")


def test_dark_spots():
    assert has(house(lights=False), "dark_spots", sev="major")
    assert not has(house(), "dark_spots")


def facade(windows=(2, 8), W=10):
    b = Build("cephe")
    b.fill(0, 0, 0, W, 6, 1, "stone_bricks")
    for x in range(0, W + 1, 2):
        b.fill(x, 0, -1, x, 6, -1, "spruce_log") if x in (0, W) else None
    for x in windows:
        b.fill(x, 2, 0, x, 3, 0, "glass_pane")
        b.set(x, 1, -1, "stone_brick_stairs[facing=south,half=top]")
    return b


def test_symmetry_rhythm():
    assert has(facade(windows=(2, 3, 8)), "symmetry_rhythm")
    irregular = Build("ritimsiz")
    irregular.fill(0, 0, 0, 30, 6, 1, "stone_bricks")
    for x in (1, 3, 11, 13, 24, 29):
        irregular.fill(x, 2, 0, x, 3, 0, "glass_pane")
    assert has(irregular, "symmetry_rhythm")
    assert not has(facade(), "symmetry_rhythm")


def test_flat_roof():
    assert has(house(roof="flat"), "flat_roof")
    assert not has(house(), "flat_roof")
    assert not has(house(roof="flat"), "flat_roof", {"style": "modern"})


def test_bare_windows():
    assert has(house(roof="flat"), "bare_windows")
    assert not has(cottage(), "bare_windows")


# ====================================================================== basarim
def test_performance_large_build():
    b = Build("büyük blok")
    N, H = 100, 99
    b.fill(0, 0, 0, N - 1, H, N - 1, "stone_bricks", hollow=True)
    b.clear(1, 1, 1, N - 2, H - 1, N - 2)
    for y in range(0, H, 5):
        b.fill(0, y, 0, N - 1, y, N - 1, "oak_planks")
    for x in range(0, N, 10):
        b.fill(x, 1, 1, x, H - 1, N - 2, "bricks")
    for y in range(0, H - 5, 5):
        for x in range(5, N, 10):
            for z in range(5, N, 10):
                b.set(x, y + 4, z, "lantern[hanging=true]")
    t = time.perf_counter()
    r = audit(b)
    dt = time.perf_counter() - t
    assert not r.errors, r.errors
    assert dt < 10.0, dt


def test_stair_third_block_bump_is_critical():
    # 2 blok bos ama bir ust basamaga cikarken govde onceki basamagin ustune tasar: 3. blok dolu -> kafa carpar
    b = flight("east")
    b.set(2, 5, 3, "stone_bricks")                    # x=2 basamagi (y=2) uzerinde h1,h2 bos, h3 dolu
    assert has(b, "stair_walkability", sev="critical")
    low = flight("east")
    low.fill(0, 4, 0, 8, 4, 8, "stone_bricks")         # 2 blok bile yok
    assert has(low, "stair_walkability", sev="critical")
    assert not has(flight("east"), "stair_walkability")


def test_heal_stairs_reopens_stairwell_closed_later():
    from usta.kit import parts as P
    b = Build("iki kat")
    b.fill(0, 0, 0, 9, 0, 9, "stone_bricks")
    P.staircase(b, 2, 1, 6, "north", rise=4)
    b.fill(1, 4, 1, 8, 4, 8, "oak_planks")             # betik merdivenden SONRA ust kati kapatti
    assert b.get_id(2, 4, 6) > 1 and b.get_id(2, 4, 5) > 1
    assert P.heal_stairs(b) >= 3
    for z in (6, 5, 4):                                # basamaklarin ustundeki 3 blok yeniden bos
        assert b.get_id(2, 4, z) == 1
