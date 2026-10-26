"""cevre: buyuk resim ve yapi islemleri (Claude ve oyun ici /usta komutlari icin).

- survey: oyuncunun cevresindeki yapilari bulur (yapay blok kumeleri: kutu, boyut, tarz, en cok kullanilan bloklar),
  istenirse her birinin kod ozetini (kodla, parcali) cikarir; ust bakis haritasi uzerinde isaretler.
- structure_code: bakilan/verilen yapiyi kayipsiz koda cevirir ve dosyaya yazar.
- paste_plan: koddan (pano) oyuncunun onune kurulacak plan.
- transform_last: Usta'nin son kurdugu yapiyi yerinde aynalar/dondurur (dogal araziye dokunmadan, geri alinabilir).
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter, deque
from pathlib import Path

import numpy as np

from . import blockdb, config
from .worlddata import parse_blocks

_NOT_STRUCTURE = ("dirt_path", "farmland", "path")      # koy yollari yapilari birbirine baglamasin


def _artificial_lut(pal: list[str]) -> np.ndarray:
    db = blockdb.get()
    art = np.zeros(len(pal), dtype=bool)
    for i, s in enumerate(pal):
        if i == 0 or s in ("minecraft:air", "?") or any(k in s for k in _NOT_STRUCTURE):
            continue
        try:
            art[i] = not bool(db.natural[db.id(s.lstrip("!"))])
        except Exception:  # noqa: BLE001
            art[i] = False
    return art


def survey(api, radius: int = 64, with_code: bool = False, max_structures: int = 12, center: tuple[int, int] | None = None) -> dict:
    """Cevredeki yapilar: [{box, size, cells, top_blocks, style}] (buyukten kucuge) + istenirse kod ozeti."""
    from .edit import guess_style
    ctx = api.context(8)
    p = ctx["player"]
    px, py, pz = int(math.floor(p["x"])), int(math.floor(p["y"])), int(math.floor(p["z"]))
    if center:
        px, pz = center
    r = max(8, min(int(radius), 96))
    y0 = max(-64, py - 48)
    h = min(96, 320 - y0)
    blk = parse_blocks(api.blocks(px - r, y0, pz - r, 2 * r + 1, h, 2 * r + 1, timeout_ms=30000))
    art = _artificial_lut(blk.palette)
    A = art[blk.cells]                                     # (y, z, x)
    col = A.any(axis=0)                                    # (z, x)
    Z, X = col.shape
    seen = np.zeros_like(col)
    comps = []
    for z in range(Z):
        for x in range(X):
            if not col[z, x] or seen[z, x]:
                continue
            q = deque([(z, x)])
            seen[z, x] = True
            pts = []
            while q:
                a, b = q.popleft()
                pts.append((a, b))
                for da, db_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    na, nb = a + da, b + db_
                    if 0 <= na < Z and 0 <= nb < X and col[na, nb] and not seen[na, nb]:
                        seen[na, nb] = True
                        q.append((na, nb))
            if len(pts) >= 4:
                comps.append(pts)
    out = []
    for pts in sorted(comps, key=len, reverse=True)[:max_structures]:
        P = np.array(pts)
        za, xa = P.min(axis=0)
        zb, xb = P.max(axis=0)
        sub = A[:, za:zb + 1, xa:xb + 1]
        ys = np.nonzero(sub.any(axis=(1, 2)))[0]
        ya, yb = int(ys.min()), int(ys.max())
        cells = blk.cells[ya:yb + 1, za:zb + 1, xa:xb + 1][sub[ya:yb + 1]]
        names = Counter(blk.palette[int(c)].split("[", 1)[0].split(":", 1)[-1] for c in cells)
        top = names.most_common(6)
        box = [int(px - r + xa), int(y0 + ya), int(pz - r + za), int(px - r + xb), int(y0 + yb), int(pz - r + zb)]
        item = {"box": box, "size": [box[3] - box[0] + 1, box[4] - box[1] + 1, box[5] - box[2] + 1], "cells": int(sub.sum()),
                "top_blocks": top, "style": guess_style(["minecraft:" + n for n, _ in top]),
                "distance": round(math.hypot((box[0] + box[3]) / 2 - p["x"], (box[2] + box[5]) / 2 - p["z"]), 1)}
        if with_code:
            try:
                code, st, path = structure_code(api, box, label=f"çevre {box[0]},{box[1]},{box[2]}")
                item["code"] = {"file": str(path), "lines": st["body_lines"], "exact": st["exact"], "ozet": st.get("ozet")}
            except Exception as e:  # noqa: BLE001
                item["code"] = {"error": str(e)}
        out.append(item)
    return {"ok": True, "center": [px, py, pz], "radius": r, "structures": out, "count": len(comps)}


def code_dir() -> Path:
    d = config.work_dir() / "kod"
    d.mkdir(parents=True, exist_ok=True)
    return d


def structure_code(api, box: list[int], label: str | None = None, skip_natural: bool = False):
    """Kutudaki yapi -> (kod, istatistik, dosya). Kod calistirilip blok blok dogrulanmistir (st['exact'])."""
    from . import edit, kodla
    x0, y0, z0 = box[:3]
    b = edit.as_build(api, box, label or "mevcut yapı")
    if skip_natural:
        db = blockdb.get()
        for i, s in enumerate(b.palette):
            if i > 1 and bool(db.natural[db.id(s.lstrip("!"))]):
                for c in b.chunks.values():
                    c[c == i] = 0
    code, st = kodla.roundtrip(b, label or f"yapı {x0},{y0},{z0}", world_origin=(x0, y0, z0))
    path = code_dir() / f"yapi_{x0}_{y0}_{z0}.py"
    path.write_text(code, encoding="utf-8")
    return code, st, path


def save_clipboard(code: str, info: dict) -> Path:
    d = code_dir()
    (d / "pano.py").write_text(code, encoding="utf-8")
    (d / "pano.json").write_text(json.dumps({**info, "t": time.time()}, ensure_ascii=False), encoding="utf-8")
    return d / "pano.py"


def paste_plan(api, code: str | None = None):
    """Panodaki (ya da verilen) koddan, oyuncunun onune ayni yonde kurulacak plan."""
    from . import kodla
    if code is None:
        f = code_dir() / "pano.py"
        if not f.exists():
            raise FileNotFoundError("Pano boş: önce /usta kopyala")
        code = f.read_text(encoding="utf-8")
    b = kodla.run(code)
    (lx, ly, lz), ids = b.dense()
    Y, Z, X = ids.shape
    ctx = api.context(8)
    p = ctx["player"]
    px, py, pz = int(math.floor(p["x"])), int(math.floor(p["y"])), int(math.floor(p["z"]))
    f = p.get("facing") or "north"
    if f == "north":
        ox, oz = px - X // 2, pz - 2 - (Z - 1)
    elif f == "south":
        ox, oz = px - X // 2, pz + 2
    elif f == "east":
        ox, oz = px + 2, pz - Z // 2
    else:
        ox, oz = px - 2 - (X - 1), pz - Z // 2
    db = b.db
    bottom = ids[0]
    solid = np.array([s not in ("keep", "minecraft:air") and db.is_full(s.lstrip("!")) if i else False for i, s in enumerate(b.palette)])
    filled = bottom != 0
    oy = py - 1 if filled.any() and solid[bottom][filled].mean() >= 0.5 else py      # alt katman temelse zemine otur
    plan = b.to_plan((ox - lx, oy - ly, oz - lz), "north", meta={"label": "Usta yapıştır"})
    return plan, [ox, oy, oz, ox + X - 1, oy + Y - 1, oz + Z - 1]


def transform_last(api, op: str, arg: str | None) -> tuple[object, list[int], dict]:
    """Usta'nin son kurdugu yapiyi yerinde aynalar (op='aynala', arg x|z) ya da dondurur (op='dondur', arg 90|180|270).
    Yalniz yapay bloklar tasinir; eski yerleri havaya doner; dogal arazi yerinde kalir."""
    from . import edit
    from .kit.core import Build
    from .plan import AIR
    ents = api.history(100).get("entries", [])
    e = next((x for x in ents if x.get("kind") == "BUILD" and not x.get("undone")), None)
    if e is None:
        raise LookupError("Usta'nın kurduğu bir yapı bulunamadı")
    ox, oy, oz, sx, sy, sz = e["box"]
    box = [ox, oy, oz, ox + sx - 1, oy + sy - 1, oz + sz - 1]
    b = edit.as_build(api, box, e.get("label") or "yapı")
    lut = _artificial_lut(b.palette)                       # hava ve dogal bloklar: plandan cikar (arazi yerinde kalir)
    for c in b.chunks.values():
        c[~lut[c]] = 0
    (lx, ly, lz), ids = b.dense()
    old_art = ids != 0
    if op == "aynala":
        t = b.transformed(2, True) if (arg or "x").lower().startswith("z") else b.transformed(0, True)
        what = f"{'z' if (arg or 'x').lower().startswith('z') else 'x'} ekseninde aynalandı"
    else:
        deg = int(str(arg or "90").strip().rstrip("°") or 90) % 360
        k = {90: 1, 180: 2, 270: 3}.get(deg, 1)
        t = b.transformed(k)
        what = f"{90 * k}° döndürüldü"
    (tx, ty, tz), tids = t.dense()
    TY, TZ, TX = tids.shape
    Y, Z, X = ids.shape
    cx, cz = ox + lx + X / 2.0, oz + lz + Z / 2.0
    nx0, nz0 = int(round(cx - TX / 2.0)), int(round(cz - TZ / 2.0))
    out = Build(f"{e.get('label') or 'yapı'} ({what})")
    out.put_mask(ox + lx, oy + ly, oz + lz, old_art, AIR)              # eski yapay hucreler havaya
    out.merge(t, dx=nx0 - tx, dy=(oy + ly) - ty, dz=nz0 - tz)          # yeni hali (eskisinin ustune yazar)
    plan = out.to_plan((0, 0, 0), "north", meta={"label": f"Usta {what}"})
    return plan, box, {"what": what, "job": e.get("id")}


def submit_and_wait(api, plan, label: str, allow_modify: bool = False, timeout_s: float = 240.0) -> dict:
    r = api.submit_plan(plan.to_bytes(), mode="instant", label=label, source="usta", confirmed="1",
                        allow_modify="1" if allow_modify else "0", allow_dangerous="0")
    jid = r.get("id")
    t0 = time.time()
    while jid and time.time() - t0 < timeout_s:
        j = api.job(jid, wait_ms=5000)
        if j.get("state") in ("DONE", "FAILED", "CANCELLED"):
            return j
        if j.get("state") == "AWAITING_CONFIRM":
            api.job_action(jid, "confirm")
    return r
