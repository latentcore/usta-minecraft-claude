"""Yapi -> kod (kodla): kayipsizlik (blok blok ayni), tekrar (dongu), ayna simetrisi, blok verileri, 26.x sablon okuma."""
from pathlib import Path

import numpy as np
import pytest

from usta import blockdb, kodla, sandbox
from usta.kit.core import Build
from usta.plan import Plan
from usta.schem import nbt as N
from usta.schem.formats import import_structure_nbt

STATES = ["minecraft:stone", "minecraft:oak_planks", "minecraft:glass", "minecraft:air", "minecraft:oak_stairs[facing=east]",
          "minecraft:oak_stairs[facing=west,half=top]", "minecraft:cobblestone_wall", "minecraft:lantern[hanging=true]"]


def _random_build(seed: int) -> Build:
    rng = np.random.default_rng(seed)
    b = Build(f"rastgele {seed}")
    for _ in range(25):
        x0, y0, z0 = (int(v) for v in rng.integers(0, 14, 3))
        x1, y1, z1 = x0 + int(rng.integers(0, 6)), y0 + int(rng.integers(0, 5)), z0 + int(rng.integers(0, 6))
        b.fill(x0, y0, z0, x1, y1, z1, STATES[int(rng.integers(len(STATES)))])
    for _ in range(60):
        x, y, z = (int(v) for v in rng.integers(0, 18, 3))
        b.set(x, y, z, STATES[int(rng.integers(len(STATES)))])
    b.forget(3, 3, 3, 5, 5, 5)
    return b


@pytest.mark.parametrize("seed", range(8))
def test_random_roundtrip_exact(seed):
    b = _random_build(seed)
    code, st = kodla.roundtrip(b)
    assert st["exact"], st
    assert st["missing"] == st["extra"] == st["wrong"] == 0
    assert st["body_lines"] < st["cells"]


def test_offset_origin_roundtrip():
    b = Build("kaymis")
    b.fill(100, 64, -40, 110, 70, -30, "minecraft:stone", hollow=True)
    b.fill(101, 65, -39, 109, 69, -31, "minecraft:air")
    code, st = kodla.roundtrip(b, parts=False)
    assert st["exact"] and st["body_lines"] <= 3, (st, code)


def test_hollow_room_is_two_boxes():
    b = Build("oda")
    b.fill(0, 0, 0, 9, 5, 9, "minecraft:stone_bricks", hollow=True)
    b.fill(1, 1, 1, 8, 4, 8, "minecraft:air")
    code, st = kodla.roundtrip(b, parts=False)
    assert st["exact"]
    assert st["body_lines"] == 2, code          # dolu kutu + ic hava (boyama sirasi + ustune yazma)


def test_window_row_becomes_loop():
    b = Build("pencereli duvar")
    b.fill(0, 0, 0, 30, 6, 0, "minecraft:stone_bricks")
    for i in range(8):
        b.fill(2 + 4 * i, 2, 0, 3 + 4 * i, 4, 0, "minecraft:glass_pane")
    code, st = kodla.roundtrip(b, parts=False)
    assert st["exact"], st
    assert st["loops"] + st["loops2"] >= 1 and "for i in range(8):" in code, code
    assert st["body_lines"] <= 4, code


def test_window_grid_becomes_nested_loop():
    b = Build("izgara")
    b.fill(0, 0, 0, 24, 20, 0, "minecraft:white_concrete")
    for j in range(4):
        for i in range(5):
            b.fill(2 + 5 * i, 2 + 5 * j, 0, 3 + 5 * i, 3 + 5 * j, 0, "minecraft:light_blue_stained_glass")
    code, st = kodla.roundtrip(b)
    assert st["exact"] and st["loops2"] >= 1 and "for j in range(4):" in code, code


def _sym_house(axis: str) -> Build:
    b = Build("simetrik")
    W, D = 21, 11
    b.fill(0, 0, 0, W - 1, 0, D - 1, "minecraft:polished_andesite")
    b.fill(0, 1, 0, W - 1, 6, D - 1, "minecraft:oak_planks", hollow=True)
    b.fill(1, 1, 1, W - 2, 5, D - 2, "minecraft:air")
    rng = np.random.default_rng(3)
    deco = ["minecraft:lantern", "minecraft:barrel", "minecraft:bookshelf", "minecraft:flower_pot", "minecraft:crafting_table"]
    for _ in range(25):                         # duzensiz ama aynali susler (sol yarida rastgele, sagda aynasi)
        x, z = int(rng.integers(1, W // 2)), int(rng.integers(1, D - 1))
        s = deco[int(rng.integers(len(deco)))]
        b.set(x, 1, z, s)
        b.set(W - 1 - x, 1, z, s)
    for x in range(W // 2):                     # catı: dogu/bati bakan merdivenler, ortada ayna
        b.fill(x, 7 + min(x, 4), 0, x, 7 + min(x, 4), D - 1, "minecraft:oak_stairs[facing=east]")
        b.fill(W - 1 - x, 7 + min(x, 4), 0, W - 1 - x, 7 + min(x, 4), D - 1, "minecraft:oak_stairs[facing=west]")
    b.set(W // 2, 1, 0, "minecraft:oak_door[facing=north,hinge=left]")      # simetriyi bozan tek hucre
    if axis == "z":
        b = b.transformed(1)                    # 90 derece: ayna ekseni z olur
    return b


@pytest.mark.parametrize("axis", ["x", "z"])
def test_mirror_symmetry_used_and_exact(axis):
    b = _sym_house(axis)
    code, st = kodla.roundtrip(b)
    assert st["exact"], st
    assert st["symmetry"] >= 1, code
    plain, st2 = kodla.roundtrip(b, symmetry=False)
    assert st2["exact"] and st["body_lines"] < st2["body_lines"]


def test_block_entities_kept():
    b = Build("sandik")
    b.fill(0, 0, 0, 4, 0, 4, "minecraft:stone")
    b.set(2, 1, 2, "minecraft:chest[facing=south]")
    b.set_block_entity(2, 1, 2, '{Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}')
    code, st = kodla.roundtrip(b)
    assert st["exact"] and st["block_entities"] == 1 and "minecraft:diamond" in code


def test_vanilla_26_template_keys_are_read():
    """26.x yapi sablonlari durumu id/properties ile yazar (eskiden Name/Properties): ikisi de okunmali."""
    pos = lambda x, y, z: N.List(N.INT, [N.Int(x), N.Int(y), N.Int(z)])
    root = {"DataVersion": N.Int(4700), "size": pos(2, 1, 1),
            "palette": N.List(N.COMPOUND, [{"id": "minecraft:oak_stairs", "properties": {"facing": "east", "half": "bottom", "shape": "straight", "waterlogged": "false"}},
                                           {"Name": "minecraft:stone"}]),
            "blocks": N.List(N.COMPOUND, [{"pos": pos(0, 0, 0), "state": N.Int(0)}, {"pos": pos(1, 0, 0), "state": N.Int(1)}]),
            "entities": N.List(N.COMPOUND, [])}
    plan = import_structure_nbt(N.dumps(root, ""))
    got = {plan.palette[int(plan.cells[0, 0, x])] for x in (0, 1)}
    assert "minecraft:stone" in got and any(s.startswith("minecraft:oak_stairs[facing=east") for s in got), got
    b = kodla.from_plan(plan)
    assert kodla.roundtrip(b)[1]["exact"]


@pytest.fixture
def _gamedir(tmp_path, monkeypatch):
    monkeypatch.setenv("USTA_GAME_DIR", str(tmp_path / "oyun"))
    cache = tmp_path / "oyun" / "usta" / "cache"
    cache.mkdir(parents=True)
    src = Path(__file__).parent / "data" / "blockdb-26.3.json.gz"
    (cache / blockdb.db_path().name).write_bytes(src.read_bytes())


def test_code_runs_in_real_sandbox(_gamedir):
    b = _sym_house("x")
    code, st = kodla.to_code(b, "kum havuzu")
    r = sandbox.run_script(code, {"site": {"origin": [0, 0, 0], "facing": "north"}}, timeout=90)
    assert r["ok"], r
    got = Plan.load(r["plan_path"])
    want = b.to_plan((0, 0, 0), "north")
    assert got.size == want.size and got.origin == want.origin
    gs = np.array(got.palette, dtype=object)[np.asarray(got.cells)]
    ws = np.array(want.palette, dtype=object)[np.asarray(want.cells)]
    assert (gs == ws).all()


class _FakeAPI:
    """Oyun yerine: dunya bir Build (dunya koordinatlarinda); blocks() gercek USTABLK1 bicimini uretir."""

    def __init__(self, world: Build, look):
        self.world, self.look = world, look

    def context(self, n=8):
        return {"looking_at": {"pos": list(self.look)}}

    def history(self, n=50):
        return {"entries": []}

    def blocks(self, x0, y0, z0, sx, sy, sz, dim=None, timeout_ms=None):
        import gzip
        import json
        import struct
        ids = self.world.ids_box(x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1)
        pal = ["minecraft:air"] + list(self.world.palette[1:])
        cells = np.where(ids == 0, 0, ids).astype("<u2")          # 0 (yok) = hava; 1 = hava
        hdr = json.dumps({"size": [sx, sy, sz], "origin": [x0, y0, z0], "palette": pal, "block_entities": []}).encode()
        return gzip.compress(b"USTABLK1" + struct.pack("<I", len(hdr)) + hdr + cells.tobytes())


def _world_with_house():
    w = Build("dunya")
    w.fill(80, 60, 180, 130, 62, 230, "minecraft:dirt")
    w.fill(80, 63, 180, 130, 63, 230, "minecraft:grass_block")
    w.fill(80, 64, 180, 130, 75, 230, "minecraft:air")
    w.fill(100, 64, 200, 108, 68, 206, "minecraft:spruce_planks", hollow=True)
    w.fill(101, 65, 201, 107, 67, 205, "minecraft:air")
    for i in range(3):
        w.fill(101 + 3 * i, 66, 200, 101 + 3 * i, 67, 200, "minecraft:glass_pane[east=true,west=true]")
    w.set(104, 65, 206, "minecraft:spruce_door[facing=south,hinge=left]")
    w.set(104, 66, 206, "minecraft:spruce_door[facing=south,half=upper,hinge=left]")
    w.fill(100, 69, 200, 108, 69, 206, "minecraft:spruce_slab")
    w.set(98, 64, 199, "minecraft:oak_log")                                # yakindaki agac (dogal, kutu disinda)
    w.set(103, 65, 203, "minecraft:mossy_cobblestone")                     # ic: yapay
    w.set(105, 65, 203, "minecraft:dirt")                                  # ic: dogal blok (skip_natural ile dusmeli)
    return w


@pytest.mark.parametrize("skip_natural", [False, True])
def test_structure_to_code_tool_end_to_end(_gamedir, monkeypatch, skip_natural):
    from usta import mcp_server, ops
    world = _world_with_house()
    monkeypatch.setattr(ops, "game", lambda: _FakeAPI(world, (100, 66, 203)))
    out = mcp_server.structure_to_code(skip_natural=skip_natural)
    head, _, code = out.partition("\n\n")
    import json
    info = json.loads(head)
    assert info["ok"] and info["exact"] is True, info
    assert "spruce_door" in code and ("for i in range(3):" in code or skip_natural), code
    assert ("minecraft:dirt'" in code) is (not skip_natural) and "mossy_cobblestone" in code, code
    assert Path(info["file"]).exists()
    # kod gercekten dunyadaki yapiyi kuruyor: ayni kutu, ayni bloklar
    rebuilt = kodla.run(Path(info["file"]).read_text(encoding="utf-8"))
    x0, y0, z0 = info["box"][:3]
    o, ids = rebuilt.dense()
    for (lx, ly, lz, want) in ((0, 0, 0, "minecraft:spruce_planks"), (4, 1, 6, None)):
        got = rebuilt.palette[int(ids[ly - o[1], lz - o[2], lx - o[0]])]
        if want:
            assert got == want, got
        else:
            assert got.startswith("minecraft:spruce_door"), got


def test_parts_sections_exact_and_coverage():
    """Anlamli parcalar: bolum basliklari ve sarmalayicilar var, kod yine birebir, hucrelerin cogu bir bolumde."""
    from usta.kit import gen
    b = gen.build("house", {})
    code, st = kodla.roundtrip(b, "ev")
    assert st["exact"], st
    for h in ("# --- DUVARLAR", "# --- PENCERELER", "# --- KAPILAR", "# --- ÇATI"):
        assert h in code, h
    assert "duvar(b, " in code and "pencere(b, " in code and "= _dolgu" in code
    assert st["parca_yuzde"] >= 90 and st["kati_parca_yuzde"] >= 75, st
    oz = st["ozet"]
    assert oz["kapilar"] and oz["cati"].startswith("eğimli") and oz["kat_seviyeleri"], oz


@pytest.mark.parametrize("seed", range(6))
def test_parts_regroup_keeps_exactness_on_random(seed):
    b = _random_build(100 + seed)
    code, st = kodla.roundtrip(b, parts=True)
    assert st["exact"], st


def test_parts_sections_are_not_fragmented():
    """Ayni bolum gereksiz yere bolunmez: duvarlarin hepsi tek basliktadir (bagimlilik yoksa)."""
    b = Build("oda")
    b.fill(0, 0, 0, 8, 0, 8, "minecraft:spruce_planks")
    for x0, z0, x1, z1 in ((0, 0, 8, 0), (0, 8, 8, 8), (0, 1, 0, 7), (8, 1, 8, 7)):
        b.fill(x0, 1, z0, x1, 4, z1, "minecraft:stone_bricks")
    b.set(4, 1, 0, "minecraft:oak_door[facing=south]")
    b.set(4, 2, 0, "minecraft:oak_door[facing=south,half=upper]")
    for x in (2, 6):
        b.set(x, 2, 8, "minecraft:glass_pane[east=true,west=true]")
    code, st = kodla.roundtrip(b, parts=True)
    assert st["exact"]
    assert code.count("# --- DUVARLAR") == 1 and code.count("# --- PENCERELER") == 1, code
