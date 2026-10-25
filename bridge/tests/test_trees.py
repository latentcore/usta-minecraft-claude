"""Agac ureteci testleri: her tur/boy gecerli blok yazar, yapraklar persistent, havada kutuk yok, dekorlar desteklii."""
from collections import deque

import numpy as np
import pytest

from usta.kit import Build
from usta.kit import trees as T

WOODY = ("_log", "_wood", "_stem", "_hyphae", "mangrove_roots")


def _cells(b):
    (ox, oy, oz), ids = b.dense()
    out = {}
    for y, z, x in zip(*np.nonzero(ids > 1)):
        out[(int(x) + ox, int(y) + oy, int(z) + oz)] = b.palette[ids[y, z, x]]
    return out


def _name(s):
    return s.lstrip("!").split("[", 1)[0].split(":", 1)[-1]


def _bfs(start, allowed):
    seen = set(start)
    q = deque(start)
    while q:
        x, y, z = q.popleft()
        for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            n = (x + d[0], y + d[1], z + d[2])
            if n in allowed and n not in seen:
                seen.add(n)
                q.append(n)
    return seen


def check_tree(b, db, ground=0):
    cells = _cells(b)
    for s in set(cells.values()):
        db.canonical(s.lstrip("!"))  # gecersiz durum -> UnknownBlock
        if _name(s).endswith("_leaves"):
            assert "persistent=true" in s, s
    logs = {p for p, s in cells.items() if _name(s).endswith(WOODY)}
    assert logs, "no wood"
    anchors = [p for p in logs if p[1] <= ground + 1]
    assert anchors, "trunk does not reach the ground"
    reached = _bfs(anchors, logs)
    assert reached == logs, f"floating logs: {sorted(logs - reached)[:5]}"
    leaves = {p for p, s in cells.items() if _name(s).endswith("_leaves")}
    if leaves:
        conn = _bfs(list(logs), logs | leaves)
        assert leaves <= conn, f"floating leaves: {sorted(leaves - conn)[:5]}"
    return cells, logs, leaves


@pytest.mark.parametrize("species", T.SPECIES)
def test_every_species_every_size(db, species):
    for size in T.SIZES:
        b = Build("t")
        b.fill(-16, -2, -16, 16, 0, 16, "grass_block")
        info = T.tree(b, 0, 0, 0, species, size, seed=7)
        cells, logs, leaves = check_tree(b, db)
        assert info["height"] >= 4
        if species != "dead":
            assert leaves, (species, size)
        # vines hang from a supported face
        for p, s in cells.items():
            if _name(s) == "vine":
                faces = [f for f in ("north", "south", "east", "west") if f"{f}=true" in s]
                assert faces, s
                f = faces[0]
                d = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0)}[f]
                sup = cells.get((p[0] + d[0], p[1], p[2] + d[2]), "")
                above = cells.get((p[0], p[1] + 1, p[2]), "")
                assert _name(sup).endswith(("_leaves",) + WOODY) or (_name(above) == "vine" and f"{f}=true" in above), p
            if _name(s) == "cocoa":
                f = s.split("facing=")[1].split("]")[0].split(",")[0]
                d = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0)}[f]
                assert "jungle" in cells.get((p[0] + d[0], p[1], p[2] + d[2]), ""), p
            if _name(s) in ("pale_hanging_moss", "mangrove_propagule") and "hanging=false" not in s:
                above = _name(cells.get((p[0], p[1] + 1, p[2]), ""))
                assert above.endswith(("_leaves", "pale_hanging_moss") + WOODY), (p, above)


def test_branch_logs_use_axis_and_wood_elbows(db):
    b = Build("t")
    T.tree(b, 0, 0, 0, "oak", "huge", seed=3)
    names = set(_cells(b).values())
    assert any("oak_log" in s and "axis=x" in s for s in names)
    assert any("oak_log" in s and "axis=z" in s for s in names)
    assert any("oak_wood" in s for s in names)


def test_deterministic_and_seed_varies(db):
    a, b2, c = Build("a"), Build("b"), Build("c")
    T.tree(a, 0, 0, 0, "cherry", "large", seed=11)
    T.tree(b2, 0, 0, 0, "cherry", "large", seed=11)
    T.tree(c, 0, 0, 0, "cherry", "large", seed=12)
    assert _cells(a) == _cells(b2)
    assert _cells(a) != _cells(c)


def test_protects_existing_structure(db):
    b = Build("t")
    b.fill(2, 1, -6, 2, 12, 6, "stone_bricks")
    T.tree(b, 0, 0, 0, "oak", "large", seed=1)
    for y in range(1, 13):
        for z in range(-6, 7):
            assert _name(b.get(2, y, z)) == "stone_bricks"
    check_tree(b, db)


def test_slope_heightmap_roots_reach_ground(db):
    hm = np.fromfunction(lambda i, j: 10 + (j // 3), (40, 40), dtype=int)
    b = Build("t")
    info = T.tree(b, 20, int(hm[20, 20]), 20, "dark_oak", "large", seed=2, heights=hm)
    cells = _cells(b)
    logs = {p for p, s in cells.items() if _name(s).endswith(WOODY)}
    anchors = [p for p in logs if 0 <= p[2] < 40 and 0 <= p[0] < 40 and p[1] <= hm[p[2], p[0]] + 1]
    assert anchors and _bfs(anchors, logs) == logs
    # no leaves at or below the ground
    for p, s in cells.items():
        if _name(s).endswith("_leaves") and 0 <= p[2] < 40 and 0 <= p[0] < 40:
            assert p[1] > hm[p[2], p[0]]
    assert info["radius"] > 3


def test_overrides_and_bad_input(db):
    b = Build("t")
    T.tree(b, 0, 0, 0, "oak", "medium", seed=1, leaves=[("orange_poplar_leaves", 1), ("red_poplar_leaves", 1)],
           wood="spruce")
    names = {_name(s) for s in _cells(b).values()}
    assert "spruce_log" in names and "oak_leaves" not in names
    with pytest.raises(ValueError):
        T.tree(b, 0, 0, 0, "baobab", "medium")
    with pytest.raises(ValueError):
        T.tree(b, 0, 0, 0, "oak", "gigantic")


def test_bush_and_undergrowth(db):
    b = Build("t")
    for i, k in enumerate(T.BUSHES):
        T.bush(b, i * 8, 0, 0, k, "medium", seed=i)
    for s in set(_cells(b).values()):
        db.canonical(s.lstrip("!"))
        if "_leaves" in s:
            assert "persistent=true" in s
    hm = np.full((24, 24), 5)
    b2 = Build("u")
    n = T.undergrowth(b2, hm, density=0.5, style="meadow", seed=3)
    assert n > 20
    for (x, y, z), s in _cells(b2).items():
        assert y in (5, 6, 7)  # plants on the ground (+ upper halves / soil swaps)


def test_forest_spacing_and_water(db):
    D = W = 56
    ii, jj = np.mgrid[0:D, 0:W]
    hm = (12 + 3 * np.sin(ii / 9.0) + 2 * np.cos(jj / 7.0)).round().astype(int)
    water = np.zeros((D, W), bool)
    water[20:32, 20:34] = True
    b = Build("f")
    placed = T.forest(b, hm, density=0.6, species_mix={"oak": 2, "spruce": 1, "birch": 1}, seed=5, water=water)
    assert len(placed) >= 5
    trunks = [(p["x"], p["z"]) for p in placed]
    assert len(set(trunks)) == len(trunks)
    for (x, z) in trunks:
        assert not water[max(0, z - 1):z + 2, max(0, x - 1):x + 2].any()
    for i, a in enumerate(placed):
        for c in placed[i + 1:]:
            assert (a["x"] - c["x"]) ** 2 + (a["z"] - c["z"]) ** 2 >= 9
    for p in placed:  # trunk footprints never stand in water
        for (x, z) in p["trunk"]:
            assert not water[z, x], (p["species"], x, z)
    cells = _cells(b)
    for (x, y, z), s in cells.items():  # only buried roots or high branches may reach over the water area
        if 0 <= z < D and 0 <= x < W and water[z, x] and _name(s).endswith(WOODY):
            assert y <= hm[z, x] + 1 or y > hm[z, x] + 3, (x, y, z, s)
