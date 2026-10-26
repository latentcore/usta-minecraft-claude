"""Onizleme: uretilmis dizinin ustten, izometrik, cephe ve perspektif goruntuleri (yazilimsal, oyunu bozmaz)."""
from __future__ import annotations

import os

import numpy as np

import aa_core as C


def render(w, out_dir, name="onizleme", views=("top", "iso_sw"), step=2, box=None, max_px=1600):
    from usta.render import views as V
    os.makedirs(out_dir, exist_ok=True)
    G = w.G
    if box is not None:
        x0, y0, z0, x1, y1, z1 = box
        G = G[y0 - C.Y0:y1 - C.Y0 + 1, z0 - C.Z0:z1 - C.Z0 + 1, x0 - C.X0:x1 - C.X0 + 1]
    ybase = C.Y0 if box is None else box[1]
    ids = G[::step, ::step, ::step].astype(np.int32)
    # deniz: dokunulmayan (0) hucreler su yuzeyinin hemen altinda suyla gosterilir (onizlemede deniz gorunsun)
    water = len(w.pal)
    ys = ybase + np.arange(ids.shape[0]) * step
    for k in np.nonzero((ys >= C.SEA - 2 * step) & (ys <= C.SEA))[0]:
        L = ids[k]
        L[L == 0] = water
    vol = V.Volume(ids, w.pal + ["minecraft:water"])
    paths = []
    for v in views:
        if v.startswith("iso"):
            img = V.iso(vol, view=v.split("_")[1], max_px=max_px)
        elif v == "top":
            img = V.top(vol, max_px=max_px)
        else:
            img = V.ortho(vol, side=v, max_px=max_px)
        p = os.path.join(out_dir, f"{name}_{v}.png")
        img.save(p)
        paths.append(p)
    return paths


def perspective(w, out_dir, name, eye, target, size=(960, 540), box=None, fov=60.0):
    from usta.render import views as V
    os.makedirs(out_dir, exist_ok=True)
    G = w.G
    ox, oy, oz = C.X0, C.Y0, C.Z0
    if box is not None:
        x0, y0, z0, x1, y1, z1 = box
        G = G[y0 - C.Y0:y1 - C.Y0 + 1, z0 - C.Z0:z1 - C.Z0 + 1, x0 - C.X0:x1 - C.X0 + 1]
        ox, oy, oz = x0, y0, z0
    vol = V.Volume(G.astype(np.int32), w.pal)
    e = (eye[0] - ox, eye[1] - oy, eye[2] - oz)
    t = (target[0] - ox, target[1] - oy, target[2] - oz)
    img = V.perspective(vol, e, t, size=size, fov=fov)
    p = os.path.join(out_dir, f"{name}.png")
    img.save(p)
    return p
