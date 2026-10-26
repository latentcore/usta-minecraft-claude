"""Uretec kalitesi (26 Ekim taramasi): her tarz ve kat sayisinda girise ve her kata yurunerek ulasilir, sacak yola sarkmaz,
bolme kapisi merdiven boslugunun yanina dusmez, merdiven on duvari delmez, kale kapi kulesi acik, havada mesale kalmaz."""
from __future__ import annotations

import itertools

import pytest

from usta.audit import audit
from usta.kit import Build, gen
from usta.kit import parts as P
from usta.kit import style

FLAT = {"terrain": None, "biome": "minecraft:plains"}
WATCH = ("stair_walkability", "door_blocked", "headroom", "no_entrance")
STYLES = ["modern", "ottoman", "medieval", "futuristic", "japanese", "scandinavian", "mediterranean", "rustic", "classical"]


def _problems(b):
    r = audit(b)
    return [(f.check, f.severity, f.message[:80]) for f in r.findings
            if f.severity == "critical" or (f.severity == "major" and f.check in WATCH)]


@pytest.mark.parametrize("st", STYLES)
def test_house_every_style_and_floor_count_is_walkable(st):
    for fl, (w, d) in itertools.product((1, 2, 3), ((9, 8), (11, 9))):
        prm = {"floors": fl, "landscape": False, "clear": False, "style": st, "width": w, "depth": d, "seed": 2424}
        assert not _problems(gen.build("house", prm, FLAT)), (st, fl, w, d)


def test_steep_roof_eave_stays_above_walkway():
    st = style.get("scandinavian")                      # egim 2: eskiden sacak yerden 1 blok yukarida biterdi
    b = Build("cati")
    P.roof(b, -1, -1, 9, 8, 4, st, kind="gable", min_eave_y=3)
    (ox, oy, oz), ids = b.dense()
    assert oy >= 3, oy
    free = Build("cati2")
    P.roof(free, -1, -1, 9, 8, 4, st, kind="gable")    # sinirsiz: tarzin tasmasi kalir (daha asagi iner)
    assert free.dense()[0][1] < oy


def test_partition_door_avoids_stairwell():
    from usta.kit.gen.common import partition_walls
    st = style.get("rustic")
    rooms = [("a", (1, 1, 1, 5, 4, 7)), ("b", (7, 1, 1, 9, 4, 7))]
    b = Build("bolme")
    free = partition_walls(b, rooms, st, 1, 3, (1, 1, 9, 7))
    assert free == [(6, 1, 4)]                           # varsayilan: duvarin ortasi
    b2 = Build("bolme2")
    near = {(x, z) for x in (6, 7, 8) for z in range(2, 8)}
    got = partition_walls(b2, rooms, st, 1, 3, (1, 1, 9, 7), avoid=near)
    assert got and all((x, z) not in near for (x, _, z) in got), got


def test_house_depth_fits_straight_stairs_without_wall_hole():
    from usta.kit.gen.houses import house_dims
    assert house_dims({"floors": 3, "style": "futuristic", "width": 9, "depth": 8})[1] >= 9
    assert house_dims({"floors": 1, "style": "futuristic", "width": 9, "depth": 8})[1] == 8
    b = gen.build("house", {"floors": 3, "style": "futuristic", "width": 9, "depth": 8, "landscape": False, "clear": False}, FLAT)
    for fy in b.meta["floors"][1:]:
        holes = [x for x in range(1, 8) if b.get_id(x, fy + 1, 0) <= 1 and b.get_id(x, fy + 2, 0) <= 1]
        assert not holes, (fy, holes)                    # merdiven cikisi on duvari delmez


@pytest.mark.parametrize("seed", [1, 77])
def test_small_castle_gate_towers_open(seed):
    assert not _problems(gen.build("castle", {"size": "küçük", "seed": seed}, FLAT))


def test_heal_attachables_fixes_floating_torches():
    b = Build("mesale")
    b.fill(0, 0, 0, 4, 0, 4, "minecraft:stone")
    b.set(1, 1, 1, "minecraft:wall_torch[facing=east]")   # tutundugu duvar yok, alti dolu -> ayakli mesale
    b.set(3, 3, 3, "minecraft:wall_torch[facing=east]")   # havada -> kaldirilir
    b.set(2, 1, 0, "minecraft:stone")
    b.set(2, 1, 1, "minecraft:wall_torch[facing=south]")  # duvara tutunuyor -> dokunulmaz
    assert P.heal_attachables(b) == 2
    assert b.get(1, 1, 1).startswith("minecraft:torch") and b.get_id(3, 3, 3) <= 1
    assert b.get(2, 1, 1).startswith("minecraft:wall_torch")


def test_secret_room_exempt_only_with_secret_door():
    b = gen.build("secret_room", {}, FLAT)
    assert not audit(b).has("stair_walkability", "major")
    b.meta.pop("secret_door")
    assert audit(b).has("stair_walkability", "major")


def test_lever_lights_lamps_sit_under_the_wire():
    # lamba hattin icinde olsaydi yalniz ilki yanardi (oyunda denendi); tel lambalarin ustunden kesintisiz gecmeli
    from usta.kit import redstone as R
    b = Build("kollu isik")
    rec = R.lever_lights(b, 0, 1, 0, length=6, axis="x")
    assert len(rec["outputs"]) == 2
    for (x, y, z) in rec["outputs"]:
        assert y == 0 and b.get(x, y, z).startswith("minecraft:redstone_lamp")
        assert b.get(x, y + 1, z).startswith("minecraft:redstone_wire")
    assert all(b.get(x, 1, 0).startswith("minecraft:redstone_wire") for x in range(1, 7))


def test_island_slices_keep_hanging_blocks_with_their_support():
    # alttan uste dilimlerde tavandan sarkan fenerin dayanagi ayni parcada olmali (ara parcada desteksiz uyarisi olmasin)
    import numpy as np
    from usta.kalp_adasi import _mods
    C, K, M = _mods()
    G = np.zeros((290, 3, 3), np.uint16)
    pal = ["keep", "minecraft:air", "minecraft:lantern[hanging=true,waterlogged=false]", "minecraft:stone"]
    G[71 - C.Y0, 1, 1] = 2                                # SLICES'ta 71 bir dilim tepesi
    G[72 - C.Y0, 1, 1] = 3
    sl = K.slices(G, pal)
    part = next((a, b) for a, b in sl if a <= 71 <= b)
    assert part[0] <= 72 <= part[1], sl
    assert sl[0][0] == K.SLICES[0][0] and sl[-1][1] == K.SLICES[-1][1]
    assert all(b + 1 == a2 for (a, b), (a2, b2) in zip(sl, sl[1:]))   # bosluksuz, ust uste binmeden


def test_island_keeps_exactly_what_the_engine_counts_as_a_structure():
    # adanin "dokunma" kurali motorun yapi sayimiyla ayni: dogal resif (canli mercan duvar yelpazesi) dolguya girer,
    # harabe tuglasi ve olu mercan korunur (eskiden motor yelpazeyi yapi sayiyordu: ada resife degince reddediliyordu)
    from usta.kalp_adasi import _mods
    C, K, M = _mods()
    assert not K.keep_world("minecraft:tube_coral_wall_fan[facing=north,waterlogged=true]")
    assert not K.keep_world("minecraft:sand")
    assert K.keep_world("minecraft:stone_bricks")
    assert K.keep_world("minecraft:dead_tube_coral_wall_fan[facing=north,waterlogged=true]")
    assert K.keep_world("minecraft:magma_block")                  # adanin kesin listesinde yok: korunur


def test_island_undo_all_asks_once_per_group():
    # gruplu parcalar: sunucu ilk istekte hepsini kuyruga koyar; ayni parcalar ikinci kez geri alinmaz
    from usta.kalp_adasi import _mods
    C, K, M = _mods()
    calls, waited = [], []

    class A:
        def undo(self, jid):
            calls.append(jid)
            return {"ok": True, "id": "u3", "group": "ada-1", "parts": 3, "jobs": ["u3", "u2", "u1"]}

        def job(self, jid, wait_ms=0):
            waited.append(jid)
            return {"state": "DONE"}

    K.undo_all(A(), ["p1", "p2", "p3"], say=lambda m: None)
    assert calls == ["p3"] and waited == ["u3", "u2", "u1"]
