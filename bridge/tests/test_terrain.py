"""Arazi araclari testleri: duzleme kenarlari yumusak, havada blok yok, su her zaman kapali hacimde ve plan icinde."""
import numpy as np
import pytest

from usta.kit import Build
from usta.kit import terrain as T
from usta.kit.trees import _fbm2


def land(D=48, W=48, seed=1, amp=7, base=20):
    ii, jj = np.mgrid[0:D, 0:W]
    return (base + amp * (_fbm2(jj, ii, 16.0, seed, 3) - 0.5) * 2).round().astype(int)


def _name(s):
    return s.lstrip("!").split("[", 1)[0].split(":", 1)[-1]


def water_cells(b):
    (ox, oy, oz), ids = b.dense()
    out = []
    for i, s in enumerate(b.palette):
        if i > 1 and _name(s) == "water":
            for y, z, x in zip(*np.nonzero(ids == i)):
                out.append((int(x) + ox, int(y) + oy, int(z) + oz))
    return out


def assert_columns_sound(b, hm, N, db):
    """No floating terrain: writes above the new surface are only air/plants, fill columns are solid."""
    D, W = hm.shape
    for i in range(D):
        for j in range(W):
            n, o = int(N[i, j]), int(hm[i, j])
            if n > o:
                for y in range(o + 1, n + 1):
                    assert b.db.is_full(b.get(j, y, i).lstrip("!")), (j, y, i, b.get(j, y, i))
            top = b.get(j, n + 1, i)
            if top not in ("keep", "minecraft:air"):
                f = db.flags_of(top.lstrip("!"))
                assert not (f & 2) or _name(top) in ("spruce_planks",), (j, n + 1, i, top)  # no full block on top


def test_flatten_pad_and_soft_edges(db):
    hm = land()
    b = Build("f")
    pad = (16, 16, 30, 28)
    N = T.flatten(b, hm, pad, seed=2)
    y = int(round(float(np.median(hm[16:29, 16:31]))))
    assert (N[16:29, 16:31] == y).all()
    changed = N != hm
    near = T._dil4(changed, 1)
    dz = np.abs(np.diff(N, axis=0))[(near[1:] | near[:-1])]
    dx = np.abs(np.diff(N, axis=1))[(near[:, 1:] | near[:, :-1])]
    steps = np.r_[dz, dx]
    nat = max(np.abs(np.diff(hm, axis=0)).max(), np.abs(np.diff(hm, axis=1)).max())
    assert steps.max() <= max(2, nat)
    assert (steps <= 1).mean() > 0.95
    assert (N[0] == hm[0]).all() and (N[:, -1] == hm[:, -1]).all()  # map border meets the world
    assert_columns_sound(b, hm, N, db)
    c = T.cost(hm, pad, y, seed=2)
    d = N - hm
    assert c["cut"] == int(np.clip(-d, 0, None).sum()) and c["fill"] == int(np.clip(d, 0, None).sum())
    assert c["area"] == 15 * 13 and c["best_y"] is not None


def test_flatten_rejects_bad_pad():
    with pytest.raises(ValueError):
        T.flatten(Build("x"), land(), (100, 100, 120, 120))
    with pytest.raises(ValueError):
        T.flatten(Build("x"), np.zeros(5), (0, 0, 1, 1))


def test_cut_only_lowers_and_smooth_hill(db):
    hm = land(seed=3)
    b = Build("c")
    N = T.cut(b, hm, (10, 10, 26, 26), y=int(hm.min()))
    assert (N <= hm).all()
    hm2 = land(seed=4, amp=10)
    N2 = T.smooth(Build("s"), hm2, sigma=2.5)
    lap = lambda a: np.abs(np.diff(a.astype(float), 2, axis=0)).mean()
    assert lap(N2) < lap(hm2)
    b3 = Build("h")
    N3 = T.hill(b3, hm, 24, 24, 12, 9)
    assert N3[24, 24] >= hm[24, 24] + 7 and (N3[0] == hm[0]).all()
    assert_columns_sound(b3, hm, N3, db)


def test_lake_is_enclosed(db):
    hm = land(seed=5)
    b = Build("l")
    N = T.lake(b, hm, 24, 24, 10, depth=4, seed=1)
    wc = water_cells(b)
    assert len(wc) > 100
    assert T.leaks(b) == []
    info = T.water_info(b)
    w = info["water"]
    assert w.any() and not (w[0].any() or w[-1].any() or w[:, 0].any() or w[:, -1].any())
    lv = int(info["level"][w].max())
    assert all(y <= lv for (_x, y, _z) in wc)
    assert (N[w] < lv).all()
    names = {_name(s) for s in b.palette[2:]}
    assert {"sand"} & names and ({"seagrass", "lily_pad", "sugar_cane", "tall_seagrass"} & names)


def test_river_inside_map_and_enclosed(db):
    hm = land(seed=6)
    b = Build("r")
    N = T.river(b, hm, [(0, 5), (25, 22), (47, 44)], width=5, depth=2, meander=0.6, seed=3)
    assert T.leaks(b) == []
    w = T.water_info(b)["water"]
    assert w.sum() > 40
    ii, jj = np.nonzero(w)
    assert ii.min() >= 2 and jj.min() >= 2 and ii.max() <= 45 and jj.max() <= 45
    with pytest.raises(ValueError):
        T.river(Build("x"), hm, [(3, 3)])


def test_waterfall_only_intended_flow_is_open(db):
    hm = land(seed=7, amp=2)
    b = Build("w")
    T.waterfall(b, hm, 24, 20, "south", height=8, width=2, seed=2)
    assert T.leaks(b) == []
    open_flow = T.leaks(b, outlets=False)
    assert open_flow  # the lip / falling column is the intended outlet
    falling = [p for p in water_cells(b) if "level=8" in b.get(*p)]
    assert len(falling) >= 2 * 5
    with pytest.raises(ValueError):
        T.waterfall(Build("x"), hm, 1, 1, "north")


def test_coast_sealed_unless_open_edge(db):
    hm = land(seed=8)
    b = Build("c")
    T.coast(b, hm, "south", width=14, seed=1)
    assert T.leaks(b) == []
    assert len(water_cells(b)) > 200
    b2 = Build("c2")
    T.coast(b2, hm, "east", width=12, open_edge=True, seed=1)
    assert T.leaks(b2)  # open edge = water reaches the plan border (only for real seas outside)


def test_beach_needs_water_and_keeps_enclosure(db):
    hm = land(seed=9)
    with pytest.raises(ValueError):
        T.beach(Build("x"), hm)
    b = Build("b")
    N = T.lake(b, hm, 24, 24, 9, seed=2)
    N = T.beach(b, N, width=4)
    assert T.leaks(b) == []
    names = {_name(s) for s in b.palette[2:]}
    assert "sand" in names


def test_road_grade_slabs_and_bridge(db):
    hm = land(seed=10, amp=9)
    b = Build("rd")
    N = T.lake(b, hm, 26, 24, 9, seed=3)
    N = T.road(b, N, [(2, 24), (46, 26)], width=3, seed=1)
    info = T.water_info(b)
    assert info["bridges"] and info["bridges"][0]["built"]
    assert T.leaks(b) == []
    names = {_name(s) for s in b.palette[2:]}
    assert "spruce_planks" in names and "spruce_fence" in names
    # gentle grade along the (land) road cells
    road = info["road"] & ~info["water"]
    hz = np.abs(np.diff(np.where(road, N, -999), axis=1))
    ok = road[:, 1:] & road[:, :-1]
    assert hz[ok].max() <= 1
    b2 = Build("rd2")
    T.road(b2, land(seed=11, amp=10), [(2, 2), (45, 45)], width=3, style="cobble", max_grade=0.5)
    names2 = {_name(s) for s in b2.palette[2:]}
    assert names2 & {"cobblestone", "mossy_cobblestone"}
    assert names2 & {"cobblestone_slab", "mossy_cobblestone_slab", "stone_slab", "cobblestone_stairs"}


def test_forest_avoids_water_and_roads(db):
    hm = land(seed=12, amp=4)
    b = Build("fo")
    N = T.lake(b, hm, 14, 14, 7, seed=1)
    N = T.road(b, N, [(0, 40), (47, 40)], width=3)
    T.forest(b, N, density=0.6, species_mix={"oak": 1, "birch": 1}, seed=3)
    st = b.meta["terrain"]
    assert st["trees"]
    for t in st["trees"]:
        assert not st["water"][t["z"], t["x"]] and not st["road"][t["z"], t["x"]]
    assert T.leaks(b) == []


def test_leaks_detects_open_water():
    b = Build("x")
    b.set(0, 0, 0, "water")
    assert T.leaks(b)
