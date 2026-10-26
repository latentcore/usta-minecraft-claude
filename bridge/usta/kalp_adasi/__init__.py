"""Kalp Adasi: oyunda "/usta ada" yazilinca oyuncunun bulundugu yere kurulur (giris terasi ayaginin altinda, ada baktigi
yone uzanir; denizde dolgu, karada lagun kazilir; deniz dibindeki harabe/anit gibi yapilara dokunulmaz; ustte bir yapiya
denk gelirse yana/ileri kayar). "/usta ada zorla": tam oldugu yere, aradaki yapilarin uzerine kurar."""
from __future__ import annotations

import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_WORDS = ("kalp adası", "kalp adasi", "kalp adasi", "kalp adası", "kalp adasi", "kalpadası", "kalpadasi")
_FORCE = ("zorla", "allow_modify", "üstüne", "ustune", "yıkarak", "yikarak", "ne olursa olsun")
FVEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
TRIES = [(0, 0), (0, 360), (0, -360), (380, 0), (380, 360), (380, -360), (760, 0)]


def istek_mi(text: str) -> bool:
    t = " ".join((text or "").casefold().replace("ı", "i").split())
    raw = " ".join((text or "").casefold().split())
    if any(w in raw for w in _WORDS) or any(w.replace("ı", "i") in t for w in _WORDS):
        return len(raw.split()) <= 8
    words = raw.split()
    return any(x in ("ada", "adayı", "adayi") for x in words) and len(words) <= 5


def zorla_mi(text: str) -> bool:
    t = (text or "").casefold()
    return any(k in t for k in _FORCE)


def _mods():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import aa_core
    import aa_kur
    import aa_main
    return aa_core, aa_kur, aa_main


def kur_onume(game_dir: str, anchor: dict | None = None, force: bool = False, say=print, dry: bool = False):
    C, K, M = _mods()
    from usta.gameapi import GameAPI, GameError
    api = GameAPI(timeout=400)
    ctx = api.context(16)
    p = dict(ctx["player"])
    if anchor and anchor.get("x") is not None:
        p.update({k: anchor[k] for k in ("x", "y", "z", "facing") if anchor.get(k) is not None})
    facing = p.get("facing") or "east"
    k = C.K_OF.get(facing, 0)
    fx, fz = FVEC[facing]
    rx, rz = -fz, fx                                     # oyuncunun sagi
    px, pz = int(math.floor(p["x"])), int(math.floor(p["z"]))
    tries = TRIES[:1] if force else TRIES
    last = ""
    for n_try, (fwd, lat) in enumerate(tries, 1):
        ax, az = px + fx * fwd + rx * lat, pz + fz * fwd + rz * lat
        C.set_place(k, ax, az)
        say(f"Kalp Adası hazırlanıyor (yer {n_try}/{len(tries)}: giriş {ax},{az}, yüz {facing})…")
        t0 = time.time()
        w = M.generate(say=lambda m: None)
        meta = {"pal": w.pal, "be": [[list(kk), v] for kk, v in w.be.items()], "ents": w.ents}
        ps = K.plans(w.G, meta)
        say(f"Üretildi ({time.time() - t0:.0f} sn, {w.count():,} blok); kuruluyor…")
        if dry:
            for p_ in ps:
                v = api.validate_plan(p_.to_bytes())
                if not v.get("ok", True) or v.get("problems"):
                    return False, f"doğrulama: {v}"
            return True, f"deneme: {len(ps)} parça doğrulandı, giriş {ax},{az}"
        placed = []
        ok = True
        grp = f"ada-{int(time.time() * 1000)}"           # parcalar tek grup: tek /usta geri hepsini birlikte geri alir
        for i, p_ in enumerate(ps, 1):
            if not force and p_.origin[1] <= C.SEA:
                p_.cells = np.array(p_.cells, dtype=np.uint16)
                K.protect_existing(api, p_, say=lambda m: None)
            try:
                r = api.submit_plan(p_.to_bytes(), mode="instant", label=f"Kalp Adası ({i}/{len(ps)})", source="mcp",
                                    confirmed="1", allow_modify="1" if force else "0", allow_dangerous="0", group=grp)
            except GameError as e:                   # ornek: var olan bir yapiya dokunuyor -> bu yer olmaz, sonrakini dene
                last = str(e.payload.get("message") or e)
                K.undo_all(api, placed)
                ok = False
                break
            r = K.wait(api, r["id"])
            if r.get("state") != "DONE":
                last = r.get("message", "") or r.get("state")
                K.undo_all(api, placed)
                ok = False
                break
            placed.append(r["id"])
            say(f"Kalp Adası kuruluyor: {i}/{len(ps)}")
        if ok:
            return True, (f"Kalp Adası kuruldu: giriş terası {ax},{az} (yüz {facing}), {w.count():,} blok, {len(ps)} parça; "
                          f"tek /usta geri hepsini birlikte geri alır.")
        if force:
            break
        say(f"Bu yer olmadı ({last[:90]}); yanına/ilerisine kaydırıyorum…")
    return False, f"Kalp Adası kurulamadı: {last}. Yapıların üstüne kurmak için: /usta ada zorla"
