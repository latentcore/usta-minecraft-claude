"""Denizde kuru cukur olmasin: su kolonlarinda disaridaki suya bagli hava -> 'koru' (dunyadaki su kalir);
kapali ic mekan (duvarla cevrili) kuru kalir."""
import numpy as np

from usta.kit.core import Build
from usta.kit.gen.common import seal_water


def _terrain(n=20, m=4):
    g = np.full((n + 2 * m, n + 2 * m), -6, np.int32)          # deniz tabani yerel -6
    water = np.ones_like(g, bool)
    return {"ground": g, "water": water, "water_top": np.full_like(g, -1), "margin": np.array(m)}


def test_open_air_below_water_becomes_keep():
    b = Build("cukur")
    b.fill(0, -5, 0, 9, 3, 9, "air")                          # tum hacim hava: kuru cukur olurdu
    n = seal_water(b, {"terrain": _terrain()})
    assert n == 10 * 10 * 5                                    # y -5..-1 (su yuzeyi -1) suya birakildi
    assert b.get_id(5, -1, 5) == 0 and b.get_id(5, 0, 5) == 1  # su ustu hava olarak kalir


def test_enclosed_room_stays_dry():
    b = Build("keson")
    b.fill(0, -5, 0, 9, 3, 9, "air")
    b.fill(3, -5, 3, 7, 3, 7, "stone_bricks", hollow=True)    # kapali kule tabani
    b.fill(3, -5, 3, 7, -5, 7, "stone_bricks")
    seal_water(b, {"terrain": _terrain()})
    assert b.get_id(5, -3, 5) == 1                             # ic kuru
    assert b.get_id(1, -3, 1) == 0                             # dis su


def test_no_water_no_change():
    t = _terrain()
    t["water"][:] = False
    b = Build("kara")
    b.fill(0, -5, 0, 4, 3, 4, "air")
    assert seal_water(b, {"terrain": t}) == 0
