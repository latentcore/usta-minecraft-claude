"""Oyun ici yardimci komutlar (mod baslatir: python -m usta.tools <is> [arg]): kod, kopyala, yapistir, cevre, aynala, dondur,
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


def _looked_box(api: GameAPI) -> list[int] | None:
    from . import edit
    la = api.context(8).get("looking_at")
    if not la:
        api.chat("Bir yapıya bak, sonra tekrar dene.", "warn")
        return None
    det = edit.detect(api, *la["pos"])
    if not det.get("ok"):
        api.chat(det.get("message", "Baktığın yerde yapı bulunamadı."), "warn")
        return None
    return det["box"]


def _code_line(st: dict) -> str:
    oz = st.get("ozet") or {}
    return (f"{st['cells']:,} hücre → {st['body_lines']} satır" + (f", parçalar %{oz.get('parca_yuzde')}" if oz else "")
            + (", birebir ✓" if st.get("exact") else ", BİREBİR DEĞİL")).replace(",", ".", 1)


def kod(api: GameAPI) -> dict:
    from . import cevre
    box = _looked_box(api)
    if box is None:
        return {"ok": False}
    code, st, path = cevre.structure_code(api, box)
    api.chat(f"Yapı koda çevrildi: {_code_line(st)}. Dosya: {path.name} (usta/calisma/kod)", "soft")
    return {"ok": bool(st.get("exact")), "file": str(path), "stats": {k: st.get(k) for k in ("cells", "body_lines", "exact", "parca_yuzde")}}


def kopyala(api: GameAPI) -> dict:
    from . import cevre
    box = _looked_box(api)
    if box is None:
        return {"ok": False}
    code, st, path = cevre.structure_code(api, box)
    if not st.get("exact"):
        api.chat("Kopya birebir doğrulanamadı; panoya konmadı.", "error")
        return {"ok": False}
    cevre.save_clipboard(code, {"box": box, "cells": st["cells"]})
    api.chat(f"Kopyalandı ({_code_line(st)}). Kurmak için bak ve: /usta yapıştır", "soft")
    return {"ok": True, "box": box}


def yapistir(api: GameAPI) -> dict:
    from . import cevre
    plan, box = cevre.paste_plan(api)
    j = cevre.submit_and_wait(api, plan, "Usta yapıştır")
    if j.get("state") == "DONE":
        api.chat(f"Yapıştırıldı: {box[0]},{box[1]},{box[2]} (geri almak için /usta geri).", "soft")
        return {"ok": True, "box": box}
    api.chat("Yapıştırılamadı: " + (j.get("message") or j.get("state") or "?") + " (önü boş bir yere bakıp tekrar dene)", "warn")
    return {"ok": False, "job": j}


def cevre_(api: GameAPI) -> dict:
    from . import cevre
    s = cevre.survey(api, 64)
    if not s["structures"]:
        api.chat("64 blok içinde yapı bulamadım.", "soft")
        return s
    parts = [f"{i + 1}) {it['size'][0]}x{it['size'][2]}, {it['style']}, {it['distance']:.0f} blok ötede" for i, it in enumerate(s["structures"][:8])]
    api.chat(f"Çevrende {s['count']} yapı: " + " · ".join(parts), "soft")
    try:
        fps = [{"x0": it["box"][0], "z0": it["box"][2], "x1": it["box"][3], "z1": it["box"][5], "facing": "north"} for it in s["structures"][:8]]
        info, data, _ = ops.map_view(None, 64, footprints=fps, title="Usta çevre")
        shots = config.game_dir() / "screenshots" / "usta"
        shots.mkdir(parents=True, exist_ok=True)
        dst = shots / ("cevre-" + time.strftime("%Y%m%d-%H%M%S") + ".jpg")
        dst.write_bytes(data)
        api.chat(f"Harita: {dst.name}", "soft", [{"label": "Aç", "command": f"/usta ac {dst.name}", "hover": "Çevre haritasını aç"}])
    except Exception:  # noqa: BLE001  (harita yardimci; liste zaten verildi)
        pass
    return s


def donustur(api: GameAPI, op: str, arg: str | None) -> dict:
    from . import cevre
    plan, box, info = cevre.transform_last(api, op, arg)
    j = cevre.submit_and_wait(api, plan, f"Usta {info['what']}", allow_modify=True)
    if j.get("state") == "DONE":
        api.chat(f"Son yapı {info['what']} (geri almak için /usta geri).", "soft")
        return {"ok": True}
    api.chat("Yapılamadı: " + (j.get("message") or j.get("state") or "?"), "warn")
    return {"ok": False, "job": j}


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
        elif what == "kod":
            r = kod(api)
        elif what == "kopyala":
            r = kopyala(api)
        elif what == "yapistir":
            r = yapistir(api)
        elif what == "cevre":
            r = cevre_(api)
        elif what in ("aynala", "dondur"):
            r = donustur(api, what, arg)
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
