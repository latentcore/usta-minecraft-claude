"""Ozel ureteçler: secret_room (kizilatasla acilan gizli oda: kitaplik + gizli pistonlu kapi + hazine odasi)."""
from __future__ import annotations

from . import register
from .. import redstone as R
from .common import (I, P, Build, clear_volume, finish_meta, get_style, ground_of, perimeter_lamps, scale_of,
                     settle_on_ground)


def secret_room_dims(params: dict) -> tuple[int, int]:
    return 21, 25


def secret_room(params: dict, ctx: dict | None = None) -> Build:
    """Kizilatasla acilan gizli oda: on tarafta kitaplikli calisma odasi; arka duvari kitaplik nisli tas duvar.
    Nislerden biri gizli kapi: duvar malzemesinden iki blok, yapiskan pistonlarla yana kayar; dis yuzdeki diz hizasi
    kol ACILINCA kapi acilir, KAPANINCA kapanir. Arkada fenerli hazine/calisma odasi (sandik, harita masasi, kitaplar)."""
    st = get_style(params, ctx, params.get("style") or "medieval")
    FW, FD = secret_room_dims(params)
    b = Build(params.get("name") or "gizli oda")
    g = ground_of(ctx, FW, FD)
    clear_volume(b, -1, 1, -1, FW, 14, FD)
    settle_on_ground(b, g, -1, -1, FW, FD, st, blend=3)
    b.fill(0, 0, 0, FW - 1, 0, FD - 1, "grass_block")
    x0, z0, x1, z1 = 3, 6, 17, 22               # ev; onunde bahce (z 0..5)
    cxd = (x0 + x1) // 2
    zw = z0 + 8                                 # gizli duvar duzlemi
    wall = "stone_bricks"
    # kabuk: tas kaide, kose taslari, tek kat; ic bolme duvari zw'de (gizli kapi burada)
    P.plinth(b, x0 - 1, z0 - 1, x1 + 1, z1 + 1, 0, st, h=1)
    shell = P.walls_box(b, x0, 0, z0, x1, 5, z1, st, floors=[0], cornice_top=False, corner="quoins")
    P.door(b, cxd, 1, z0, "north", st, w=1, steps=1)
    P.canopy(b, cxd - 1, 3, z0, "north", w=3, depth=1, st=st)
    for lx in (cxd - 2, cxd + 2):
        P.wall_lamp(b, lx, 3, z0, "north", st)
    P.window_row(b, x0, 2, z0, "north", x1 - x0 + 1, st, kind="shutters", avoid=[(cxd - 2, cxd + 2)])
    P.window_row(b, x0, 2, z0, "west", zw - z0, st, kind="shutters")
    P.window_row(b, x1, 2, z0, "east", zw - z0, st, kind="shutters")
    P.roof(b, x0 - 1, z0 - 1, x1 + 1, z1 + 1, 6, st, kind="gable")
    st.fill(b, x0 + 1, 6, z0 + 1, x1 - 1, 6, z1 - 1, "ceiling")
    P.chimney(b, x1 - 3, 5, z1 - 3, 7, st)
    # on bahce: yol, cicek tarhlari, iki agac, alcak cit + kapi, fenerler
    P.path(b, [(cxd, 0), (cxd, z0 - 2)], 0, st, w=3, border=True)
    for (bx0, bx1) in ((1, cxd - 3), (cxd + 3, FW - 2)):
        if bx1 - bx0 >= 3:
            P.garden_bed(b, bx0, 0, 2, bx1, 4, st, raised=True, seed=bx0)
    for x in range(0, FW):
        if not (cxd - 1 <= x <= cxd + 1):
            b.set(x, 1, 0, st.fence("fence"))
    for (lx, lz) in ((cxd - 2, 1), (cxd + 2, 1)):
        P.lamp_post(b, lx, 1, lz, st, h=3)
    for (tx, tz) in ((1, FD - 2), (FW - 2, FD - 2)):
        P.tree(b, tx, 1, tz, st, kind="round", seed=tx)
    # ic duvar: zw duzleminde tas (iki katman: zw-1 kaplama + zw govde), gizli kapi + susleme nisleri
    for x in range(x0 + 1, x1):
        for y in range(1, 5):
            b.set(x, y, zw, wall)
    dx = cxd - 3
    rec = R.hidden_piston_door(b, dx, 1, zw, wall=wall, clad="bookshelf", lever_side="east", niches=1, niche_fill="bookshelf")
    for x in range(x0 + 1, x1):                 # kaplamanin geri kalani kitaplik (nis ve kapi sutunu disinda)
        for y in range(1, 4):
            if b.get_id(x, y, zw - 1) <= 1 and x not in (dx, dx - 3):
                b.set(x, y, zw - 1, "bookshelf")
    # on oda: calisma odasi (kitaplik duvari zaten var)
    try:
        I.furnish(b, (x0 + 1, 1, z0 + 1, x1 - 1, 5, zw - 2), "library", style="medieval", door=[(cxd, 1, z0)], seed=3)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"library: {e}")
    # gizli oda: hazine/calisma
    for x in range(x0 + 1, x1):
        b.set(x, 0, zw + 1, "polished_andesite")
    try:
        I.furnish(b, (x0 + 1, 1, zw + 1, x1 - 1, 5, z1 - 1), "armory", style="medieval", door=[(dx, 1, zw)], seed=5)
    except Exception as e:
        b.meta.setdefault("notes", []).append(f"armory: {e}")
    b.set(x1 - 2, 1, z1 - 1, "chest[facing=north,type=single]")
    b.set(x1 - 3, 1, z1 - 1, "chest[facing=north,type=single]")
    b.set(x0 + 2, 1, z1 - 1, "cartography_table")
    b.set(x0 + 3, 1, z1 - 1, "lectern[facing=north,has_book=false]")
    perimeter_lamps(b, x0, z0, x1, z1, 3, st, every=6, faces=("east", "west", "south"))
    return finish_meta(b, "secret_room", st, {"floors": [0], "door": [cxd, 1, z0], "secret_door": rec,
                                               "rooms": [{"name": "calisma", "kind": "library", "box": [x0 + 1, 1, z0 + 1, x1 - 1, 5, zw - 2]},
                                                         {"name": "gizli oda", "kind": "armory", "box": [x0 + 1, 1, zw + 1, x1 - 1, 5, z1 - 1]}]})


register("secret_room", secret_room, secret_room_dims,
         "Kızıltaşla açılan gizli oda: kitaplıklı çalışma odası; kitaplık nişlerinden biri yapışkan pistonlu gizli kapı, diz hizasındaki kolla açılır; arkada hazine odası",
         {"style": "medieval|rustic|classical"}, lambda p: p.get("name") or "gizli oda")
