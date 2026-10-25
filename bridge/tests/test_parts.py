"""parts: her parca calisir, yalniz gecerli blok yazar, bildirdigi kutuya sigar, destek/kapi/su kurallarina uyar."""
import pytest

from usta.blockdb import split_state
from usta.kit import Build
from usta.kit import parts as P
from usta.kit import style

G = 0  # testlerde zemin yuzeyi y=0 (ve alti) dogal zemin sayilir


def floor(b, x0=-3, z0=-3, x1=12, z1=10, y=0):
    b.fill(x0, y, z0, x1, y, z1, "minecraft:stone", only_empty=True)


def wall_n(b, st, x0=-3, x1=8, h=6):
    P.wall(b, x0, 0, 0, x1, h, 0, st)


def ceil(b, y=6):
    b.fill(-3, y, -3, 3, y, 3, "minecraft:stone")


def house(b, st):
    P.walls_box(b, 0, 0, 0, 10, 4, 7, st, floors=[0])


def stairs_two_floors(b, st, kind):
    b.fill(-2, 0, -2, 12, 0, 12, "minecraft:stone")
    b.fill(-2, 4, -2, 12, 4, 12, "minecraft:stone")
    return P.staircase(b, 0, 1, 2, "east", 4, st, w=1, kind=kind)


SPECS = {
    "plinth": lambda b, st: P.plinth(b, 0, 0, 8, 6, 1, st, h=2),
    "wall": lambda b, st: P.wall(b, 0, 1, 0, 5, 4, 1, st),
    "floor_slab": lambda b, st: P.floor_slab(b, 0, 1, 0, 6, 5, st, pattern="checker"),
    "band": lambda b, st: P.band(b, "east", 0, 2, 0, 6, st),
    "cornice": lambda b, st: P.cornice(b, "south", 0, 4, 0, 6, st, depth=2),
    "pilaster": lambda b, st: P.pilaster(b, "north", 2, 1, 0, 5, st),
    "pilasters": lambda b, st: P.pilasters(b, "west", 0, 1, 0, 13, 5, st),
    "quoins": lambda b, st: P.quoins(b, 0, 0, 1, 6, "nw", st, proud=True),
    "column": lambda b, st: [P.column(b, 0, 1, 0, 5, st, kind=k) for k in ("slim", "round", "square")][-1],
    "beam": lambda b, st: P.beam(b, (0, 3, 0), (6, 3, 0), st),
    "timber_frame": lambda b, st: P.timber_frame(b, "north", 0, 1, 0, 13, 5, st),
    "buttress": lambda b, st: P.buttress(b, "north", 2, 1, 0, 6, st),
    "crenellations": lambda b, st: P.crenellations(b, 0, 0, 8, 6, 5, st),
    "walls_box": lambda b, st: P.walls_box(b, 0, 0, 0, 10, 8, 7, st),
    "window": lambda b, st: (wall_n(b, st, -3, 30, 8), [P.window(b, 1 + 4 * i, 2, 0, "north", 2 if k in ("ribbon", "modern", "shoji", "arched") else 1, 3, st, kind=k)
                                                         for i, k in enumerate(("framed", "shutters", "arched", "kafes", "shoji", "ribbon", "modern", "slit"))])[1][-1],
    "flower_box": lambda b, st: (wall_n(b, st), P.flower_box(b, 2, 1, 0, "north", 2, st))[1],
    "window_row": lambda b, st: (wall_n(b, st, -3, 14), P.window_row(b, 0, 2, 0, "north", 12, st))[1],
    "oculus": lambda b, st: (wall_n(b, st), P.oculus(b, 3, 3, 0, "north", 1, st))[1],
    "bay_window": lambda b, st: (wall_n(b, st), P.bay_window(b, 2, 3, 0, "north", 3, 2, 1, st))[1],
    "cumba": lambda b, st: (wall_n(b, st, -3, 10, 9), P.cumba(b, 2, 6, 0, "north", 5, 3, 2, st))[1],
    "door": lambda b, st: (floor(b), wall_n(b, st, -3, 14), P.door(b, 1, 1, 0, "north", st, w=1, kind="framed"),
                           P.door(b, 5, 1, 0, "north", st, w=2, kind="arched"), P.door(b, 10, 1, 0, "north", st, kind="modern"))[-1],
    "entrance_steps": lambda b, st: P.entrance_steps(b, 3, 3, 0, "north", 2, 2, st),
    "portico": lambda b, st: (floor(b, -6, -6, 12, 6, y=-1), wall_n(b, st, -3, 12, 8), P.portico(b, 5, 1, 0, "north", 2, 3, st))[-1],
    "arched_gate": lambda b, st: (floor(b), wall_n(b, st, -3, 10, 7), P.arched_gate(b, 2, 1, 0, "north", 3, 5, st, depth=1, gate="fence_gate"))[-1],
    "canopy": lambda b, st: (wall_n(b, st), P.canopy(b, 3, 1, 0, "north", 1, 2, st))[1],
    "railing": lambda b, st: [P.railing(b, (0, 1, k * 2), (6, 1, k * 2), st, kind=kd, newel=3)
                              for k, kd in enumerate((None, "balustrade", "fence", "wall", "glass", "bars"))][-1],
    "balcony": lambda b, st: (floor(b), wall_n(b, st, -3, 8, 8), P.balcony(b, 2, 4, 0, "north", 3, 2, st, door_w=1))[-1],
    "stair_flight": lambda b, st: P.stair_flight(b, 0, 1, 0, "north", 4, st, w=2),
    "staircase": lambda b, st: (stairs_two_floors(b, st, "straight"), stairs_two_floors(Build("u"), st, "u"))[0],
    "spiral_stair": lambda b, st: P.spiral_stair(b, 0, 1, 0, 10, st, r=1),
    "roof_gable": lambda b, st: (house(b, st), P.roof_gable(b, 0, 0, 10, 7, 5, st))[1],
    "roof_hip": lambda b, st: (house(b, st), P.roof_hip(b, 0, 0, 10, 7, 5, st))[1],
    "roof_pyramid": lambda b, st: P.roof_pyramid(b, 0, 0, 8, 8, 5, st),
    "roof_shed": lambda b, st: (house(b, st), P.roof_shed(b, 0, 0, 10, 7, 5, st, facing="west"))[1],
    "roof_mansard": lambda b, st: (house(b, st), P.roof_mansard(b, 0, 0, 10, 7, 5, st))[1],
    "roof_curved": lambda b, st: (house(b, st), P.roof_curved(b, 0, 0, 10, 7, 5, st))[1],
    "roof_flat": lambda b, st: (house(b, st), P.roof_flat(b, 0, 0, 10, 7, 5, st, parapet=1))[1],
    "dormer": lambda b, st: (house(b, st), P.roof_gable(b, 0, 0, 10, 7, 5, st, pitch=1), P.dormer(b, 4, 6, 2, "north", 1, 2, st))[-1],
    "chimney": lambda b, st: P.chimney(b, 2, 1, 2, 6, st),
    "dome": lambda b, st: [P.dome(Build("d"), 0, 1, 0, 5, st, kind=k, drum=3) for k in ("onion", "pointed")] and P.dome(b, 0, 1, 0, 5, st, kind="hemi", drum=3),
    "spire": lambda b, st: P.spire(b, 0, 1, 0, 3, 8, st),
    "roof": lambda b, st: (house(b, st), P.roof(b, 0, 0, 10, 7, 5, st))[1],
    "minaret": lambda b, st: P.minaret(b, 0, 1, 0, 30, st, serefe=2),
    "tower": lambda b, st: [P.tower(Build("t"), 0, 1, 0, 4, 12, st, top=t) for t in ("crenel", "dome", "none")] and P.tower(b, 0, 1, 0, 4, 12, st, top="cone"),
    "arcade": lambda b, st: [P.arcade(Build("a"), 0, 1, 0, "east", 13, st, roof_kind=k) for k in ("shed", "flat")] and P.arcade(b, 0, 1, 0, "north", 13, st, roof_kind="domes"),
    "pool": lambda b, st: P.pool(b, 0, 0, 0, 9, 6, st),
    "fountain": lambda b, st: (P.fountain(Build("f"), 0, 0, 0, st, kind="simple"), P.fountain(b, 0, 0, 0, st, kind="sadirvan"))[1],
    "garden_bed": lambda b, st: (P.garden_bed(b, 0, 0, 0, 5, 4, st), P.garden_bed(b, 8, 0, 0, 12, 4, st, raised=False))[0],
    "hedge": lambda b, st: P.hedge(b, 0, 1, 0, 6, 1, st, h=2, organic=True),
    "path": lambda b, st: P.path(b, [(0, 0), (10, 0), (10, 8)], 0, st, w=3),
    "stepping_stones": lambda b, st: P.stepping_stones(b, [(0, 0), (6, 3), (12, 0)], 0, st),
    "fence_line": lambda b, st: [P.fence_line(Build("f"), [(0, 0), (10, 0), (10, 6)], 1, st, kind=k, gate_at=(5, 0)) for k in ("wall", "hedge")]
    and P.fence_line(b, [(0, 0), (10, 0), (10, 6)], 1, st, kind="fence", gate_at=(5, 0), gate_w=2),
    "gate": lambda b, st: (P.gate(b, 2, 1, 0, "north", 2, st), P.gate(b, 10, 1, 0, "west", 2, st, arch=True))[0],
    "tree": lambda b, st: [P.tree(b, i * 8, 1, 0, kind=k, seed=i) for i, k in enumerate(("round", "conifer", "cypress", "blossom", "olive", "palm"))][0],
    "planter": lambda b, st: [P.planter(b, i * 5, 1, 0, st, kind=k) for i, k in enumerate(("pot", "box", "urn", "tree", "topiary"))][0],
    "well": lambda b, st: P.well(b, 0, 0, 0, st),
    "pergola": lambda b, st: P.pergola(b, 0, 1, 0, 8, 4, st),
    "bench": lambda b, st: P.bench(b, 0, 1, 0, "west", st),
    "flagpole": lambda b, st: P.flagpole(b, 0, 1, 0, st),
    "awning": lambda b, st: (wall_n(b, st), P.awning(b, 0, 4, 0, "north", 4, st))[1],
    "lamp_post": lambda b, st: [P.lamp_post(b, i * 4, 1, 0, st, kind=k) for i, k in enumerate(("crook", "top", "modern", "toro"))][0],
    "wall_lamp": lambda b, st: (wall_n(b, st, -3, 14), [P.wall_lamp(b, i * 3, 3, 0, "north", st, kind=k) for i, k in enumerate(("lantern", "sconce", "torch", "modern"))][0])[1],
    "hanging_lamp": lambda b, st: (ceil(b), P.hanging_lamp(b, 0, 6, 0, st, 2))[1],
    "chandelier": lambda b, st: (ceil(b), P.chandelier(b, 0, 6, 0, st, r=2))[1],
    "floor_pattern": lambda b, st: [P.floor_pattern(b, 0, 1, i * 8, 6, i * 8 + 6, st, kind=k)
                                    for i, k in enumerate(("checker", "herringbone", "border", "diagonal", "medallion", "planks"))][0],
    "ceiling": lambda b, st: P.ceiling(b, 0, 6, 0, 9, 6, st, medallion=True),
    "rug": lambda b, st: (floor(b), P.rug(b, 0, 1, 0, 6, 4, st))[1],
    "table": lambda b, st: (floor(b), P.table(b, 0, 1, 0, st=st), P.table(b, 3, 1, 0, 5, 1, st))[1],
    "chair": lambda b, st: (floor(b), P.chair(b, 2, 1, 2, "south", st))[1],
    "bed": lambda b, st: (floor(b), P.bed(b, 2, 1, 2, "east", "blue"))[1],
    "sedir": lambda b, st: (floor(b), P.sedir(b, 1, 1, 1, "north", 4, st))[1],
    "bookcase": lambda b, st: (floor(b), P.bookcase(b, 0, 1, 1, "north", 4, 3, st))[1],
}

STYLES_FOR_TEST = ("medieval", "ottoman", "modern", "japanese")


def test_catalog_complete():
    assert len(P.CATALOG) >= 50
    assert set(SPECS) == set(P.CATALOG), set(P.CATALOG) ^ set(SPECS)
    for name, desc in P.CATALOG.items():
        assert isinstance(desc, str) and len(desc) > 15
        assert callable(getattr(P, name))
    assert "minaret" in P.__doc__ and "check" in P.__doc__


def _contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] <= inner[2]
            and outer[3] >= inner[3] and outer[4] >= inner[4] and outer[5] >= inner[5])


@pytest.mark.parametrize("name", sorted(SPECS))
@pytest.mark.parametrize("sty", STYLES_FOR_TEST)
def test_part_runs_valid_supported(name, sty, db):
    st = style.get(sty)
    b = Build(name)
    res = SPECS[name](b, st)
    assert isinstance(res, dict) and res.get("box") is not None
    # yalniz gecerli, kanonik bloklar
    for s in b.palette[2:]:
        body = s.lstrip("!")
        assert db.canonical(body) == body
    # parca kendi bildirdigi kutunun disina yazmaz
    if res.get("written") is not None:
        assert _contains(res["box"], res["written"]), (res["box"], res["written"])
    issues = P.check(b, ground=G)
    assert not issues, issues[:5]


@pytest.mark.parametrize("face", ["north", "east", "south", "west"])
def test_facade_parts_every_face(face, db):
    st = style.get("mediterranean")
    b = Build("f")
    b.fill(-6, 0, -6, 16, 0, 16, "minecraft:stone")
    P.walls_box(b, 0, 0, 0, 10, 8, 10, st, floors=[0, 4])
    x, z = {"north": (3, 0), "south": (3, 10), "east": (10, 3), "west": (0, 3)}[face]
    r = P.door(b, x, 1, z, face, st, w=2)
    P.window(b, x + (4 if face in ("north", "south") else 0), 2, z + (4 if face in ("east", "west") else 0), face, 1, 2, st, kind="shutters")
    P.wall_lamp(b, x - (1 if face in ("north", "south") else 0), 3, z - (1 if face in ("east", "west") else 0), face, st, kind="torch")
    assert not P.check(b, ground=0)
    d = b.meta["doors"][-1]
    want = {"north": "south", "south": "north", "east": "west", "west": "east"}[face]
    assert d["facing"] == want  # kapi iceri bakar (KIT_DEV)
    lower = [s for s in b.palette if s.endswith("_door") is False and "_door[" in s and "half=lower" in s]
    upper = [s for s in b.palette if "_door[" in s and "half=upper" in s]
    assert lower and upper
    assert _contains(r["box"], r["written"])


def test_check_catches_problems():
    b = Build("bad")
    b.set(0, 5, 0, "minecraft:lantern[hanging=true]")           # askida, ustu bos
    b.set(3, 5, 0, "minecraft:wall_torch[facing=north]")         # arkasi bos
    b.set(6, 5, 0, "minecraft:oak_door[half=lower,facing=south]")  # ust yarisi yok
    b.set(9, 5, 0, "minecraft:poppy")                             # toprak yok
    b.set(12, 5, 0, "minecraft:oak_leaves[persistent=false]")
    b.set(15, 5, 0, "minecraft:water")                            # kapali degil
    b.set(18, 5, 0, "minecraft:sand")                             # alti bos
    issues = P.check(b)
    assert len(issues) >= 7
    ok = Build("ok")
    ok.set(0, 6, 0, "minecraft:stone")
    ok.set(0, 5, 0, "minecraft:lantern[hanging=true]")
    ok.set(3, 5, 1, "minecraft:stone")
    ok.set(3, 5, 0, "minecraft:wall_torch[facing=north]")
    assert P.check(ok) == []


def test_frame_rotation_and_meta():
    st = style.get("medieval")
    b = Build("m")
    P.window(b, 0, 2, 5, "east", 2, 2, st, kind="framed")
    w = b.meta["windows"][-1]
    assert w["face"] == "east" and w["box"][0] == w["box"][3] == 0
    stairs = [s for s in b.palette if "stairs" in s]
    assert any("facing=west" in s for s in stairs)  # east cephesinde 'iceri' = west
    b2 = Build("s")
    b2.fill(-2, 0, -2, 12, 0, 12, "minecraft:stone")
    b2.fill(-2, 4, -2, 12, 4, 12, "minecraft:stone")
    r = P.staircase(b2, 0, 1, 2, "east", 4, st)
    # yurunebilir: her basamak bir oncekinden 1 yuksek ve bir ileride, ustunde 2 hucre bos
    steps = r["steps"]
    for (x0, y0, z0), (x1, y1, z1) in zip(steps, steps[1:]):
        assert (x1 - x0, y1 - y0, z1 - z0) == (1, 1, 0)
    for (x, y, z) in steps:
        for hh in (1, 2):
            assert b2.get(x, y + hh, z) in ("minecraft:air", "keep") or "stairs" in b2.get(x, y + hh, z)
    assert b2.is_solid(steps[-1][0] + 1, r["upper"], steps[-1][2])
    assert split_state(b2.get(*steps[0]))[1]["facing"] == "east"
