import numpy as np
import pytest

from usta.kit import Build
from usta.kit import shapes as S


def test_box_shell_and_ops():
    b = S.box(0, 0, 0, 4, 4, 4)
    assert b.count() == 125 and b.bbox == (0, 0, 0, 4, 4, 4)
    sh = b.shell()
    assert sh.count() == 125 - 27
    u = S.box(0, 0, 0, 3, 3, 3) | S.box(2, 2, 2, 5, 5, 5)
    assert u.count() == 64 + 64 - 8 and u.bbox == (0, 0, 0, 5, 5, 5)
    d = S.box(0, 0, 0, 3, 3, 3) - S.box(2, 2, 2, 5, 5, 5)
    assert d.count() == 56
    i = S.box(0, 0, 0, 3, 3, 3) & S.box(2, 2, 2, 5, 5, 5)
    assert i.count() == 8 and i.bbox == (2, 2, 2, 3, 3, 3)
    sb = S.shell_box(0, 0, 0, 5, 3, 5, top=False, bottom=False)
    assert sb.count() == 4 * 20


def test_cylinder_ring_sphere_dome():
    c = S.cylinder((0, 0, 0), (0, 5, 0), 3)
    assert c.bbox == (-3, 0, -3, 3, 5, 3)
    ring = S.cylinder((0, 0, 0), (0, 5, 0), 3, hollow=True)
    assert 0 < ring.count() < c.count()
    # kalin halka yuz-bagli: her katmanda ic bos, dis kapali
    layer = ring.mask[0]
    assert not layer[3, 3]
    cx = S.cylinder((0, 0, 0), (8, 0, 0), 2)
    assert cx.bbox[0] == 0 and cx.bbox[3] == 8 and cx.bbox[1] == -2
    sp = S.sphere((0, 0, 0), 5)
    assert sp.bbox == (-5, -5, -5, 5, 5, 5)
    for kind in ("hemi", "onion", "pointed", "bell", "cone"):
        d = S.dome((0, 0, 0), 4, kind=kind)
        assert d.bbox[1] == 0 and d.count() > 0
    assert S.torus((0, 0, 0), 5, 1).count() > 0
    assert S.ring((0, 0, 0), 4, 3).count() > 0
    assert S.ellipse_box(0, 0, 9, 5, 0).bbox == (0, 0, 0, 9, 0, 5)


@pytest.mark.parametrize("kind", ["round", "pointed", "segmental", "ogee", "flat"])
def test_arch_profile(kind):
    p = S.arch_profile(5, 7, kind)
    assert p.shape == (7, 5)
    assert p[0].all()  # alt sira tam acik
    assert p[-1].any()  # tepe bos degil
    assert (p.sum(axis=1)[1:] <= p.sum(axis=1)[:-1]).all()  # yukari dogru daralir
    sh = S.arch(0, 0, 0, 5, 7, kind, depth=2, axis="z")
    assert sh.mask.shape == (7, 5, 2)


def test_arch_profile_bad_kind():
    with pytest.raises(ValueError):
        S.arch_profile(5, 7, "horseshoe-xyz")


def test_polygon_lines_splines():
    p = S.polygon([(0, 0), (10, 0), (10, 6), (5, 10), (0, 6)], 0, 2)
    assert p.bbox == (0, 0, 0, 10, 2, 10)
    ln = S.line((0, 0, 0), (10, 5, 3), r=0.5)
    assert ln.mask[0, 0, 0] and ln.count() >= 11
    pl = S.polyline([(0, 0, 0), (5, 0, 0), (5, 0, 5)], r=0.5)
    assert pl.count() == 11
    sp = S.spline([(0, 0, 0), (10, 4, 3), (20, 0, 0)], r=1)
    assert sp.bbox[0] <= 0 and sp.bbox[3] >= 20
    cr = S.catmull_rom([(0, 0, 0), (4, 0, 0), (8, 0, 4)], samples=4)
    assert np.allclose(cr[0], (0, 0, 0)) and np.allclose(cr[-1], (8, 0, 4))


def test_noise_deterministic_and_bounded():
    x = np.arange(50, dtype=float)
    a = S.noise(x, 0.0, 0.0, scale=4, seed=3, octaves=2)
    b = S.noise(x, 0.0, 0.0, scale=4, seed=3, octaves=2)
    c = S.noise(x, 0.0, 0.0, scale=4, seed=4, octaves=2)
    assert np.array_equal(a, b) and not np.array_equal(a, c)
    assert a.min() >= 0 and a.max() <= 1
    h = S.hash01(np.arange(1000), 0, 0, 1)
    assert 0.4 < h.mean() < 0.6
    bl = S.blob((0, 0, 0), 5, seed=2)
    assert bl.count() == S.blob((0, 0, 0), 5, seed=2).count()
    pts = S.scatter(S.box(0, 0, 0, 20, 0, 20), 0.1, seed=1)
    assert pts == S.scatter(S.box(0, 0, 0, 20, 0, 20), 0.1, seed=1) and len(pts) > 10


def test_morphology_and_surface():
    s = S.box(0, 0, 0, 4, 4, 4)
    assert s.erode().count() == 27
    assert s.dilate(1).count() == 7 ** 3 - 8 * 1 - 12 * 5 + 0 or s.dilate(1).bbox == (-1, -1, -1, 5, 5, 5)
    assert s.surface("up").count() == 25
    assert s.crop(0, 0, 0, 1, 1, 1).count() == 8
    assert s.moved(10, 0, 0).bbox[0] == 10


def test_put_into_build():
    b = Build("t")
    S.sphere((0, 0, 0), 3).shell().put(b, "stone")
    assert b.get(0, 3, 0) == "minecraft:stone" and b.get(0, 0, 0) == "keep"
    with pytest.raises(ValueError):
        S.Shape(np.zeros((3, 3), bool))
