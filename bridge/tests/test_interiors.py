"""Ic mekan receteleri: her recete kucuk (5x3x5) ve buyuk (12x4x10) odada calisir; gecerli bloklar, kutu disina
yalniz gomulu tam blok, kapi->merkez yolu yurunebilir, yatak/kapi butun, destek kurallari, isik var ve karanlik yok."""
import numpy as np
import pytest

from usta import blockdb
from usta.kit import interiors as I
from usta.kit.core import Build

SIZES = [(5, 3, 5), (12, 4, 10)]


def _furnished(kind, size, door_side="north", seed=0):
    b, box, door = I.demo_room(kind, size=size, door_side=door_side, furnish_it=False)
    x0, y0, z0, x1, y1, z1 = box
    before = b.ids_box(x0 - 1, y0 - 1, z0 - 1, x1 + 1, y1 + 1, z1 + 1).copy()
    pal_before = list(b.palette)
    rec = getattr(I, f"furnish_{kind}")(b, box, door=door, seed=seed)
    return b, box, door, before, pal_before, rec


def test_at_least_25_recipes_and_api():
    assert len(I.ROOM_KINDS) >= 25
    for k, desc in I.ROOM_KINDS.items():
        assert callable(getattr(I, f"furnish_{k}")) and isinstance(desc, str) and desc
    for req in ("living_room", "kitchen", "dining_room", "master_bedroom", "kids_room", "bathroom", "library",
                "home_office", "guest_room", "foyer", "laundry", "pantry", "wine_cellar", "workshop", "tavern",
                "throne_hall", "great_hall", "armory", "bas_oda", "prayer_hall", "tea_room", "barn", "greenhouse",
                "control_room", "lab", "shop", "cafe", "gym", "pool_room", "attic"):
        assert req in I.ROOM_KINDS


@pytest.mark.parametrize("size", SIZES, ids=lambda s: "x".join(map(str, s)))
@pytest.mark.parametrize("kind", sorted(I.ROOM_KINDS))
def test_recipe_valid(kind, size, db):
    b, box, door, before, pal_before, rec = _furnished(kind, size)
    x0, y0, z0, x1, y1, z1 = box
    # gecerli, tehlikesiz bloklar
    for s in b.palette[2:]:
        st = s.lstrip("!")
        db.canonical(st)
        assert not (db.flags_of(st) & blockdb.DANGEROUS), s
    # kutu disinda yalniz zemin/tavan/duvar katmaninda gomulu TAM blok; asla hava
    after = b.ids_box(x0 - 1, y0 - 1, z0 - 1, x1 + 1, y1 + 1, z1 + 1)
    changed = np.argwhere(np.array(pal_before, dtype=object)[before] != np.array(b.palette, dtype=object)[after])
    for (iy, iz, ix) in changed:
        x, y, z = x0 - 1 + ix, y0 - 1 + iy, z0 - 1 + iz
        if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
            continue
        s = b.get(x, y, z)
        assert s != "minecraft:air", (x, y, z)
        assert db.flags_of(s.lstrip("!")) & blockdb.FULL, (x, y, z, s)
        in_xz = x0 <= x <= x1 and z0 <= z <= z1
        layer = (y in (y0 - 1, y1 + 1) and in_xz)
        ring = (y0 <= y <= y1) and ((x in (x0 - 1, x1 + 1) and z0 <= z <= z1) or (z in (z0 - 1, z1 + 1) and x0 <= x <= x1))
        assert layer or ring, (x, y, z, s)
    rep = I.room_report(b, box, door=door)
    assert rep["door_paths_ok"], (kind, size)
    assert not rep["dark_spots"], rep["dark_spots"][:5]
    assert not rep["unsupported"], rep["unsupported"][:5]
    assert rep["min_light"] >= 4
    # kabugun kapisi butun
    dx, dy, dz = door[0]
    assert "half=lower" in b.get(dx, dy, dz) and "half=upper" in b.get(dx, dy + 1, dz)
    # yataklar iki yarim
    for y in range(y0, y1 + 1):
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                s = b.get(x, y, z)
                if s.endswith("]") and "_bed[" in s:
                    assert I.support_problem(b, box, x, y, z, s) is None
    # meta
    assert rec["recipe"] == f"furnish_{kind}" and rec["box"] == list(box) and rec["lights"] > 0
    assert any(r.get("recipe") == f"furnish_{kind}" for r in b.meta["rooms"])
    assert any(l.get("room") == rec["name"] for l in b.meta["lights"])
    assert rec["furniture"]


@pytest.mark.parametrize("kind", ["living_room", "kitchen", "master_bedroom", "prayer_hall", "pool_room", "tea_room"])
def test_side_door_and_odd_sizes(kind):
    for size, side in (((9, 5, 7), "east"), ((7, 3, 11), "west"), ((6, 2, 6), "south")):
        b, box, door = I.demo_room(kind, size=size, door_side=side)
        rep = I.room_report(b, box, door=door)
        assert rep["door_paths_ok"] and not rep["dark_spots"] and not rep["unsupported"], (kind, size, side)


def test_deterministic_and_styles():
    a, box, _ = I.demo_room("living_room", seed=3)
    b, _, _ = I.demo_room("living_room", seed=3)
    assert a.histogram() == b.histogram()
    for st in ("rustik", "osmanli", {"base": "modern", "wood": "cherry", "fabric": "blue"}):
        b, box, door = I.demo_room("living_room", size=(8, 3, 8), style=st)
        assert I.room_report(b, box, door=door)["door_paths_ok"]


def test_detect_room_kind():
    cases = {"ferah bir mutfak": "kitchen", "Mutfağı yap": "kitchen", "yatak odası": "master_bedroom",
             "Çocuk Odası": "kids_room", "salon": "living_room", "oturma odası": "living_room", "banyo": "bathroom",
             "kütüphane": "library", "living room": "living_room", "taht salonu": "throne_hall",
             "spor salonu": "gym", "baş oda": "bas_oda", "cami": "prayer_hall", "japon çay odası": "tea_room",
             "ahır": "barn", "şarap mahzeni": "wine_cellar", "indoor pool": "pool_room", "çatı katı": "attic"}
    for text, want in cases.items():
        assert I.detect_room_kind(text) == want, text
    assert I.detect_room_kind("") is None
    assert I.detect_room_kind("rastgele bir kelime") is None


def test_furnish_errors_and_text_kind():
    b, box, door = I.demo_room("kitchen", size=(6, 3, 6), furnish_it=False)
    rec = I.furnish(b, box, "mutfak", door=door)
    assert rec["kind"] == "kitchen"
    with pytest.raises(ValueError):
        I.furnish(Build("x"), (0, 0, 0, 4, 2, 4), "uzay asansoru")
    with pytest.raises(ValueError):
        I.furnish(Build("x"), (0, 0, 0, 0, 2, 0), "kitchen")
    with pytest.raises(ValueError):
        I.furnish(Build("x"), (0, 0, 0, 4, 2, 4), "kitchen", style="bilinmeyen-stil")


def test_report_detects_problems():
    b = Build("x")
    box = (1, 1, 1, 5, 3, 5)
    b.fill(0, 0, 0, 6, 0, 6, "stone")
    b.set(3, 2, 3, "lantern[hanging=true]")           # tavansiz, desteksiz asili fener
    b.set(2, 1, 2, "red_bed[facing=north,part=foot]")  # tek yarim yatak
    rep = I.room_report(b, box)
    whys = {u["block"].split("[")[0] for u in rep["unsupported"]}
    assert "minecraft:lantern" in whys and "minecraft:red_bed" in whys
    empty = Build("y")
    empty.fill(0, 0, 0, 6, 4, 6, "stone")
    empty.clear(1, 1, 1, 5, 3, 5)
    assert I.room_report(empty, box)["dark_spots"]  # isiksiz oda karanlik
