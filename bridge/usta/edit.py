"""Duzenleme destegi (C12): bakilan yapiyi algilama (isin izi + bagli dogal olmayan bloklar), tarzini/paletini/katlarini
cikarma, mevcut yapiyi yerel bir Build olarak alma (uzerinde degisiklik yapip yeniden kurmak icin)."""
from __future__ import annotations

from collections import Counter, deque

import numpy as np

from . import blockdb
from .gameapi import GameAPI
from .worlddata import parse_blocks


def _history_boxes(api: GameAPI) -> list[list[int]]:
    """Usta'nin kurdugu (geri alinmamis) yapilarin kutulari, en yeni once: [x0,y0,z0,x1,y1,z1]."""
    try:
        ents = api.history(50).get("entries", [])
    except Exception:
        return []
    out = []
    for e in ents:
        # patlama kraterinin kutusu bir yapi degildir
        if e.get("kind") == "BUILD" and not e.get("undone") and e.get("box") and e.get("source") != "patlama":
            ox, oy, oz, sx, sy, sz = e["box"]
            out.append([ox, oy, oz, ox + sx - 1, oy + sy - 1, oz + sz - 1])
    return out


def history_box_at(api: GameAPI, x: int, y: int, z: int, pad: int = 3) -> list[int] | None:
    """Noktayi (pay ile) iceren en yeni Usta yapisinin kutusu; yoksa None."""
    for b in _history_boxes(api):
        if b[0] - pad <= x <= b[3] + pad and b[1] - pad <= y <= b[4] + pad and b[2] - pad <= z <= b[5] + pad:
            return b
    return None


def norm_box(api: GameAPI, box: list[int]) -> list[int]:
    """Kutu iki kose [x0,y0,z0,x1,y1,z1] olarak doner. history'nin [x,y,z,sx,sy,sz] bicimi de kabul edilir
    (gecmisteki bir kutuyla birebir ayniysa ya da kose sirasi tersse boyut bicimi sayilir)."""
    b = [int(v) for v in box]
    try:
        hist = [e["box"] for e in api.history(50).get("entries", []) if e.get("box")]
    except Exception:
        hist = []
    if b in hist or b[3] < b[0] or b[4] < b[1] or b[5] < b[2]:
        return [b[0], b[1], b[2], b[0] + b[3] - 1, b[1] + b[4] - 1, b[2] + b[5] - 1]
    return b


def detect(api: GameAPI, x: int, y: int, z: int, reach: int = 40, dim: str | None = None) -> dict:
    """(x,y,z) noktasindan baslayip bagli yapay bloklari bulur (26-komsuluk, en cok reach yaricap)."""
    db = blockdb.get()
    x0, y0, z0 = x - reach, max(y - reach, -64), z - reach
    sx, sy, sz = 2 * reach + 1, min(2 * reach + 1, 320 - y0), 2 * reach + 1
    blk = parse_blocks(api.blocks(x0, y0, z0, sx, sy, sz, dim=dim, timeout_ms=8000))
    pal = blk.palette
    art = np.zeros(len(pal), dtype=bool)
    for i, s in enumerate(pal):
        if i == 0 or s in ("minecraft:air", "?"):
            continue
        try:
            art[i] = not bool(db.natural[db.id(s)])
        except Exception:
            art[i] = False
    A = art[blk.cells]
    start = (y - y0, z - z0, x - x0)
    if not (0 <= start[0] < sy and 0 <= start[1] < sz and 0 <= start[2] < sx):
        return {"ok": False, "message": "nokta alan dışında"}
    if not A[start]:
        # baslangic dogalsa (orn. yapinin dibindeki cimen) en yakin yapay blogu ara
        cand = np.argwhere(A)
        hb = history_box_at(api, x, y, z)
        if hb is not None and (len(cand) == 0 or int(np.min(np.abs(cand - np.array(start)).sum(axis=1))) > 6):
            # nokta Usta'nin kurdugu bir yapinin icinde ama bos (oda ici, avlu): o yapinin kutusu
            return {"ok": True, "box": hb, "size": [hb[3] - hb[0] + 1, hb[4] - hb[1] + 1, hb[5] - hb[2] + 1],
                    "source": "history", "message": "Usta'nın kurduğu yapı (geçmişteki kutusu)"}
        if len(cand) == 0:
            return {"ok": False, "message": "yakında yapay blok (yapı) bulunamadı"}
        d = np.abs(cand - np.array(start)).sum(axis=1)
        start = tuple(int(v) for v in cand[int(np.argmin(d))])
        if int(np.min(d)) > 6:
            return {"ok": False, "message": "baktığın yerde bir yapı yok"}
    seen = np.zeros_like(A)
    q = deque([start])
    seen[start] = True
    pts = []
    offs = [(dy, dz, dx) for dy in (-1, 0, 1) for dz in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dz, dx) != (0, 0, 0)]
    while q and len(pts) < 600_000:
        p = q.popleft()
        pts.append(p)
        for o in offs:
            n = (p[0] + o[0], p[1] + o[1], p[2] + o[2])
            if 0 <= n[0] < sy and 0 <= n[1] < sz and 0 <= n[2] < sx and A[n] and not seen[n]:
                seen[n] = True
                q.append(n)
    P = np.array(pts)
    ymin, zmin, xmin = P.min(axis=0)
    ymax, zmax, xmax = P.max(axis=0)
    names = [pal[int(blk.cells[tuple(p)])].split("[", 1)[0] for p in pts]
    top = Counter(names).most_common(12)
    # katlar: yatay dolulugu yuksek y seviyeleri
    layer = Counter(int(p[0]) for p in pts)
    w = (xmax - xmin + 1) * (zmax - zmin + 1)
    floors = sorted(int(y0 + yy) for yy, c in layer.items() if c > 0.45 * w)
    res = {
        "ok": True, "cells": len(pts),
        "box": [int(x0 + xmin), int(y0 + ymin), int(z0 + zmin), int(x0 + xmax), int(y0 + ymax), int(z0 + zmax)],
        "size": [int(xmax - xmin + 1), int(ymax - ymin + 1), int(zmax - zmin + 1)],
        "palette_top": top, "floor_levels": floors[:12], "style_guess": guess_style([n for n, _ in top]),
        "roof_guess": roof_guess(blk, P, pal, y0),
        "touches_reach_limit": bool(xmin == 0 or zmin == 0 or xmax == sx - 1 or zmax == sz - 1 or ymax == sy - 1),
    }
    return res


def guess_style(names: list[str]) -> str:
    s = " ".join(names)
    score = {
        "modern": sum(k in s for k in ("concrete", "quartz", "glass", "smooth_stone", "calcite")),
        "ottoman": sum(k in s for k in ("terracotta", "glazed", "prismarine", "cut_sandstone")),
        "medieval": sum(k in s for k in ("stone_bricks", "cobblestone", "mossy", "deepslate_bricks")),
        "rustic": sum(k in s for k in ("oak_log", "spruce_log", "planks", "hay")),
        "japanese": sum(k in s for k in ("cherry", "bamboo", "dark_oak")),
        "futuristic": sum(k in s for k in ("sea_lantern", "tinted_glass", "end_rod", "iron_block")),
    }
    best = max(score.items(), key=lambda t: t[1])
    return best[0] if best[1] > 0 else "bilinmiyor"


def roof_guess(blk, P, pal, y0) -> str:
    top_y = int(P[:, 0].max())
    top_names = [pal[int(blk.cells[tuple(p)])] for p in P if p[0] >= top_y - 2]
    st = sum("_stairs" in n for n in top_names)
    sl = sum("_slab" in n for n in top_names)
    if st > len(top_names) * 0.4:
        return "eğimli (merdivenli: beşik/kırma)"
    if sl > len(top_names) * 0.4:
        return "düz (levha)"
    return "düz ya da karışık"


def as_build(api: GameAPI, box: list[int], name: str = "mevcut yapı", dim: str | None = None):
    """Dunyadaki kutuyu yerel bir Build'e alir (yerel 0,0,0 = kutunun en kucuk kosesi). Duzenleyip
    `b.to_plan((x0,y0,z0),'north')` ile ayni yere yeniden kurulabilir (allow_modify gerekir)."""
    from .kit.core import Build
    x0, y0, z0, x1, y1, z1 = box
    blk = parse_blocks(api.blocks(x0, y0, z0, x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1, dim=dim))
    b = Build(name)
    pal = ["keep" if p in ("?",) else p for p in blk.palette]
    b.put_ids(0, 0, 0, blk.cells, pal)
    for be in blk.block_entities:
        b.set_block_entity(*be["pos"], be["snbt"])
    return b
