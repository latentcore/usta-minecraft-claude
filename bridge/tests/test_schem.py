import numpy as np

from usta.kit.core import Build
from usta.schem import EXPORTERS, IMPORTERS


def _plan():
    b = Build("t")
    b.fill(0, 0, 0, 5, 0, 4, "stone_bricks")
    b.fill(0, 1, 0, 5, 3, 4, "oak_planks", hollow=True)
    b.set(2, 1, 0, "oak_door[facing=south,half=lower]")
    b.set(2, 2, 0, "oak_door[facing=south,half=upper]")
    b.set(1, 1, 1, "chest[facing=south]")
    b.set_block_entity(1, 1, 1, '{Items:[{Slot:0b,count:5,id:"minecraft:diamond"}]}')
    b.set(4, 2, 2, "oak_stairs[facing=east,half=top]")
    return b.to_plan((0, 0, 0), "north")


def _norm(plan):
    names = [s.lstrip("!") if s != "keep" else "minecraft:air" for s in plan.palette]
    return np.vectorize(lambda v: names[v])(plan.cells)


def test_roundtrip_all_formats():
    p = _plan()
    ref = _norm(p)
    for fmt in ("schem", "litematic", "nbt"):
        data = EXPORTERS[fmt](p) if fmt == "nbt" else EXPORTERS[fmt](p, "deneme")
        q = IMPORTERS[fmt](data)
        assert q.size == p.size, fmt
        assert (_norm(q) == ref).all(), fmt
        assert any("diamond" in be["snbt"] for be in q.block_entities), fmt
