"""Oyun ici yardimci komutlar (mod baslatir: python -m usta.tools <is> [arg]):
foto [is_id], harita, kaydet <is_id> [ad], kutuphane, panel. Sonuclari oyun sohbetine yazar."""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

from . import config, ops
from .gameapi import GameAPI
from .render.sheet import fit
from .render.views import Volume, iso, perspective


def _job_box(api: GameAPI, job_id: str | None) -> dict | None:
    ents = api.history(100).get("entries", [])
    for e in ents:
        if e.get("kind") == "BUILD" and not e.get("undone") and (job_id is None or e["id"] == job_id):
            return e
    return None


def tod_tint(day_time: int | None) -> tuple[float, float, float] | None:
    if day_time is None:
        return None
    t = day_time % 24000
    if 11500 <= t <= 13500:   # gun batimi
        return (1.12, 0.92, 0.78)
    if 13500 < t < 22500:     # gece
        return (0.55, 0.62, 0.85)
    if t >= 22500 or t < 500:  # safak
        return (1.05, 0.9, 0.85)
    return None


def photo(api: GameAPI, job_id: str | None) -> dict:
    e = _job_box(api, job_id)
    if e is None:
        api.chat("Fotoğraf için kurulmuş bir yapı bulamadım.", "warn")
        return {"ok": False}
    ox, oy, oz, sx, sy, sz = e["box"]
    m = max(4, int(max(sx, sz) * 0.25))
    x0, y0, z0 = ox - m, oy - 3, oz - m
    x1, y1, z1 = ox + sx - 1 + m, oy + sy + 2, oz + sz - 1 + m
    ids, pal = ops.world_volume(api, x0, y0, z0, x1, y1, z1)
    vol = Volume(ids, pal, (x0, y0, z0))
    ctx = api.context(8)
    tint = tod_tint(ctx.get("world", {}).get("day_time"))
    vy, vz, vx = ids.shape
    cx, cy, cz = vx / 2, vy * 0.35, vz / 2
    d = max(vx, vz) * 0.95 + 8
    # oyuncunun bulundugu taraftan, capraz ve hafif yukaridan
    p = ctx.get("player", {})
    ang = math.atan2((p.get("z", z0 + vz) - (z0 + cz)), (p.get("x", x0 + vx) - (x0 + cx)))
    eye = (cx + math.cos(ang + 0.5) * d, vy * 0.75 + d * 0.32, cz + math.sin(ang + 0.5) * d)
    im = perspective(vol, eye, (cx, cy, cz), size=(1280, 720), fov=60, tint=tint)
    shots = config.game_dir() / "screenshots" / "usta"
    shots.mkdir(parents=True, exist_ok=True)
    name = f"usta-{e['id']}-{time.strftime('%Y%m%d-%H%M%S')}"
    f1 = shots / f"{name}.png"
    im.save(f1)
    f2 = shots / f"{name}-izometrik.png"
    fit(iso(vol, "se", max_px=1200, tint=tint), 1280, 900).save(f2)
    api.chat(f"Fotoğraf hazır: {f1.name} (ve izometrik). Klasör: screenshots/usta", "soft",
             [{"label": "Aç", "command": f"/usta ac {f1.name}", "hover": "Fotoğrafı aç"}])
    return {"ok": True, "files": [str(f1), str(f2)]}


def harita(api: GameAPI) -> dict:
    info, data, path = ops.map_view(None, 96)
    shots = config.game_dir() / "screenshots" / "usta"
    shots.mkdir(parents=True, exist_ok=True)
    dst = shots / ("harita-" + time.strftime("%Y%m%d-%H%M%S") + ".jpg")
    dst.write_bytes(data)
    api.chat(f"Harita hazır: {dst.name}", "soft", [{"label": "Aç", "command": f"/usta ac {dst.name}", "hover": "Haritayı aç"}])
    return {"ok": True, "file": str(dst)}


def kaydet(api: GameAPI, job_id: str, name: str | None = None) -> dict:
    from . import library
    e = _job_box(api, job_id)
    if e is None:
        api.chat("Kaydedilecek yapı bulunamadı.", "warn")
        return {"ok": False}
    item = library.save_from_world(api, e, name or e.get("label") or "yapı")
    api.chat(f"Kütüphaneye kaydedildi: {item['name']} ({item['blocks']} blok).", "soft")
    return {"ok": True, "item": item}


def kutuphane(api: GameAPI) -> dict:
    from . import library
    items = library.list_items()[:8]
    if not items:
        api.chat("Kütüphane boş. Bir yapının [Kaydet] düğmesiyle ekleyebilirsin.", "soft")
        return {"ok": True, "items": []}
    api.chat("Kütüphane: " + " · ".join(f"{i['name']} ({i['size'][0]}x{i['size'][2]})" for i in items), "soft")
    return {"ok": True, "items": items}


def panel(api: GameAPI) -> dict:
    from . import panel as pnl
    url = pnl.ensure_running_and_login_url()
    import webbrowser
    webbrowser.open(url)
    api.chat("Panel tarayıcında açıldı (yalnız bu bilgisayar).", "soft")
    return {"ok": True}


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    api = GameAPI()
    try:
        if what == "foto":
            r = photo(api, arg)
        elif what == "harita":
            r = harita(api)
        elif what == "kaydet":
            r = kaydet(api, arg, sys.argv[3] if len(sys.argv) > 3 else None)
        elif what == "kutuphane":
            r = kutuphane(api)
        elif what == "panel":
            r = panel(api)
        else:
            r = {"ok": False, "message": f"bilinmeyen iş: {what}"}
    except Exception as e:  # noqa: BLE001
        try:
            api.chat(f"Yapılamadı: {e}", "error")
        except Exception:
            pass
        r = {"ok": False, "error": str(e)}
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
