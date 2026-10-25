"""Usta Arena: uret, onizle, kaydet.  python arena_main.py [onizle]"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import arena_core  # noqa: E402
from arena_bowl import Bowl  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arena_out")


def generate(with_rooms=True):
    t0 = time.time()
    w = arena_core.World()
    b = Bowl(w)
    steps = [("govde", b.structure), ("koltuk", b.seats), ("konkur", b.concourses), ("cati", b.roof),
             ("cephe", b.facade), ("saha", b.pitch), ("meydan", b.plaza), ("ekran", b.screens)]
    for name, fn in steps:
        t = time.time()
        fn()
        print(f"{name}: {time.time() - t:.1f} sn, blok {w.count():,}", flush=True)
    top = b.crown_y + 35
    b.facade_text(0, "USTA ARENA", 4, 4, top)
    b.facade_text(0, "MINECRAFT X CLAUDE", 2, 3, b.crown_y - 6, block="white_concrete")
    b.facade_text(1, "USTA", 6, 4, top)
    b.facade_text(2, "2026", 6, 4, top)
    b.facade_text(3, "2026", 6, 4, top)
    b.facade_crest(0, 24, 46)
    # ana giris sacagi (Maraton): 60 genis, 12 derin, sari alt yuz + isiklar, iki kolon
    from arena_core import B, FACADE
    zf = B + FACADE + 3
    w.box(-32, 22, zf, 32, 23, zf + 12, "white_concrete")
    w.box(-32, 21, zf, 32, 21, zf + 12, "yellow_concrete")
    for x in range(-30, 31, 6):
        w.set(x, 21, zf + 6, "sea_lantern")
    for x in (-28, 28):
        w.box(x, 0, zf + 11, x + 1, 20, zf + 12, "blue_concrete")
    w.box(-12, 0, zf, 12, 0, zf + 14, "polished_blackstone")
    if with_rooms:
        import arena_rooms
        t = time.time()
        arena_rooms.build_all(w, b)
        print(f"ic mekan: {time.time() - t:.1f} sn, blok {w.count():,}", flush=True)
    print(f"toplam {time.time() - t0:.1f} sn; blok {w.count():,}; palet {len(w.pal)}; BE {len(w.be)}; varlik {len(w.ents)}")
    return w, b


def save(w):
    os.makedirs(OUT, exist_ok=True)
    np.save(os.path.join(OUT, "G.npy"), w.G)
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"pal": w.pal, "be": [[list(k), v] for k, v in w.be.items()], "ents": w.ents, "notes": w.notes}, f,
                  ensure_ascii=False)


def preview(w, name="onizleme", step=2, views=("iso_se", "top")):
    from usta.render import views as V
    os.makedirs(OUT, exist_ok=True)
    ids = w.G[::step, ::step, ::step]
    vol = V.Volume(ids.astype(np.int32), w.pal)
    paths = []
    for v in views:
        if v.startswith("iso"):
            img = V.iso(vol, view=v.split("_")[1], max_px=1600)
        elif v == "top":
            img = V.top(vol, max_px=1400)
        else:
            img = V.ortho(vol, side=v, max_px=1400)
        p = os.path.join(OUT, f"{name}_{v}.png")
        img.save(p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    rooms = "kabuk" not in sys.argv
    w, b = generate(with_rooms=rooms)
    save(w)
    if "onizle" in sys.argv:
        for p in preview(w):
            print(p)
