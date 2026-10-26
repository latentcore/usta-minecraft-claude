"""Uretilmis stadyumu (onbellek G.npy) oyuncunun ONUNE kurar: ana cephe oyuncuya bakar, arazi duzlenir (tepeler alinir,
cukurlar/su toprakla doldurulur), on yer dolu ise (koy, yapi) bir sonraki bos yere kayar; zorla=True ise oldugu yere kurar.
Her parca ayri is, hepsi tek grup (tek /usta geri hepsini birlikte geri alir); bir parca reddedilirse o denemenin parcalari geri alinir.
python arena_onume.py [etiket] [x z yon] [zorla] [deneme]"""
from __future__ import annotations

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import arena_core  # noqa: E402
from usta import blockdb  # noqa: E402
from usta.gameapi import GameAPI, GameError  # noqa: E402
from usta.plan import Plan  # noqa: E402
from usta.worlddata import UNKNOWN, parse_columns  # noqa: E402

DB = blockdb.get()
OUT = os.environ.get("ARENA_OUT") or os.path.join(HERE, "arena_out")
CUTS = [(-3, 12), (13, 28), (29, 44), (45, 64), (65, 88), (89, 112), (113, 162)]
FACE_K = {"north": 0, "east": 1, "south": 2, "west": 3}
FVEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
TRIES = [(0, 0), (0, 160), (0, -160), (200, 0), (200, 200), (200, -200), (420, 0)]


def rot_xz(x, z, k):
    for _ in range(k % 4):
        x, z = -z, x
    return x, z


def _rotated():
    G = np.load(os.path.join(OUT, "G.npy"))
    meta = json.load(open(os.path.join(OUT, "meta.json"), encoding="utf-8"))
    return G, meta


def _terrain(api, x0, z0, x1, z1, gy, say):
    """Parcalari olusturur (gerekirse) ve sutun verisini doner (yuzey, zemin, su tabani)."""
    for x in range(x0, x1 + 1, 256):
        for z in range(z0, z1 + 1, 256):
            sx, sz = min(256, x1 - x + 1), min(256, z1 - z + 1)
            for _ in range(3):
                try:
                    api.blocks(x, gy, z, sx, 1, sz, timeout_ms=120000, generate=True)
                    break
                except Exception:
                    time.sleep(1)
    return parse_columns(api.columns(x0, z0, x1, z1, timeout_ms=60000))


def main(tag="", anchor=None, force=False, say=print, dry=False, mode="instant", seconds=None):
    api = GameAPI(timeout=400)
    ctx = api.context(16)
    p = dict(ctx["player"])
    if anchor and anchor.get("x") is not None:
        p.update({k: anchor[k] for k in ("x", "y", "z", "facing") if anchor.get(k) is not None})
    facing = p.get("facing", "north")
    k = FACE_K.get(facing, 0)
    fx, fz = FVEC[facing]
    rx_, rz_ = -fz, fx                                   # oyuncunun sagi
    G, meta = _rotated()
    pal, be, ents = meta["pal"], meta["be"], meta["ents"]
    x_lo, x_hi, z_lo, z_hi = arena_core.X0, arena_core.X1, arena_core.Z0, arena_core.Z1
    arr = G
    for _ in range(k):
        arr = arr.transpose(0, 2, 1)[:, :, ::-1]
        x_lo, x_hi, z_lo, z_hi = -z_hi, -z_lo, x_lo, x_hi
    arr = np.ascontiguousarray(arr)
    rpal = []
    for s in pal:
        if s in ("keep", "minecraft:air") or not k:
            rpal.append(s)
            continue
        ex = s.startswith("!")
        b2 = DB.rotate(s[1:] if ex else s, k)
        rpal.append(("!" + b2) if ex else b2)
    dirt, grass = len(rpal), len(rpal) + 1
    rpal += ["minecraft:dirt", "minecraft:grass_block[snowy=false]"]
    bes_all = []
    for (x, y, z), snbt in be:
        bx, bz = rot_xz(x, z, k)
        bes_all.append((bx, y, bz, snbt))
    ents_all = []
    for e in ents:
        x, y, z = e["pos"]
        ex_, ez_ = rot_xz(x - 0.5, z - 0.5, k)
        ents_all.append({"type": e["type"], "pos": [ex_ + 0.5, y, ez_ + 0.5], "yaw": (float(e.get("yaw", 0)) + 90 * k) % 360,
                         "snbt": e.get("snbt", "{}")})
    own = []
    try:
        for e in api.history(300).get("entries", []):
            if not e.get("undone") and e.get("box"):
                bx = e["box"]
                own.append((bx[0], bx[2], bx[0] + bx[3] - 1, bx[2] + bx[5] - 1))
    except Exception:
        pass
    base_d = arena_core.Z1 + 6
    px, pz = int(math.floor(p["x"])), int(math.floor(p["z"]))
    py = int(math.floor(p.get("y", ctx["world"].get("ground_y_here", 64))))
    label = "Usta Arena" + (f" #{tag}" if tag else "")
    tries = TRIES[:1] if force else TRIES
    last_err = ""
    for (fwd, lat) in tries:
        ox = px + fx * (base_d + fwd) + rx_ * lat
        oz = pz + fz * (base_d + fwd) + rz_ * lat
        X0w, Z0w, X1w, Z1w = ox + x_lo, oz + z_lo, ox + x_hi, oz + z_hi
        say(f"Arazi hazırlanıyor ({X1w - X0w + 1}x{Z1w - Z0w + 1})…")
        cols = _terrain(api, X0w, Z0w, X1w, Z1w, py, say)
        known = cols.known()
        ground = np.where(known, cols.ground, UNKNOWN)
        if known.any():
            base = int(np.median(cols.ground[known]))
        else:
            base = py - 1
        base = min(base, int(ctx["world"].get("max_y", 319)) - arena_core.Y1)    # cati dunya tavanini asmasin
        surface = np.where(known, cols.surface, base)
        floor = np.where(known, np.minimum(cols.floor, cols.ground), base)
        fill_lo = int(min(base - 1, max(int(floor.min()) + 1, base - 40)))
        say(f"Kuruluyor: merkez {ox},{oz}, zemin y={base}" + (" (zorla)" if force else ""))
        if dry:
            print(json.dumps({"merkez": [ox, oz], "zemin": base, "kutu": [X0w, Z0w, X1w, Z1w], "dolgu_alt": fill_lo,
                              "yuzey_ust": int(surface.max()), "bilinen": float(known.mean())}), flush=True)
            return True, "deneme"
        # parcalar: once dolgu (zeminin altindaki cukur/su), sonra stadyum dilimleri (tepeler temizlenerek)
        cuts = []
        if fill_lo < -3 + base:
            y = fill_lo - base
            while y < -3:
                cuts.append(("dolgu", y, min(-4, y + 30)))
                y += 31
        cuts += [("dilim", a, b) for a, b in CUTS]
        placed = []
        grp = f"stadyum-{int(time.time() * 1000)}"       # parcalar tek grup: tek /usta geri hepsini birlikte geri alir
        ok = True
        n = len(cuts)
        for i, (kind, ya, yb) in enumerate(cuts, 1):
            if kind == "dolgu":
                ys = np.arange(ya, yb + 1).reshape(-1, 1, 1)
                cells = np.where((base + ys > floor[None]) & (base + ys < base), dirt, 0).astype(np.uint16)
            else:
                sub = arr[ya - arena_core.Y0:yb - arena_core.Y0 + 1]
                cells = np.array(sub, dtype=np.uint16)
                ys = np.arange(ya, yb + 1).reshape(-1, 1, 1)
                wy = base + ys
                clear = (cells == 0) & (ys >= 1) & (wy <= surface[None])
                cells[clear] = 1
                below = (cells == 0) & (ys < 0) & (wy > floor[None])
                cells[below] = dirt
                top0 = (cells == 0) & (ys == 0) & (ground[None] < base)
                cells[top0] = grass
            nzc = np.nonzero(cells.any(axis=0))
            if len(nzc[0]) == 0:
                continue
            zi0, zi1, xi0, xi1 = int(nzc[0].min()), int(nzc[0].max()), int(nzc[1].min()), int(nzc[1].max())
            yv = np.nonzero(cells.any(axis=(1, 2)))[0]
            yi0, yi1 = int(yv.min()), int(yv.max())
            cells = np.ascontiguousarray(cells[yi0:yi1 + 1, zi0:zi1 + 1, xi0:xi1 + 1])
            lx0, ly0, lz0 = x_lo + xi0, ya + yi0, z_lo + zi0
            lx1, ly1, lz1 = lx0 + cells.shape[2] - 1, ly0 + cells.shape[0] - 1, lz0 + cells.shape[1] - 1
            bes = []
            for (x, y, z, snbt) in bes_all:
                if lx0 <= x <= lx1 and ly0 <= y <= ly1 and lz0 <= z <= lz1:
                    st = rpal[int(cells[y - ly0, z - lz0, x - lx0])]
                    if st in ("keep", "minecraft:air") or not (DB.flags_of(st.lstrip("!")) & blockdb.BLOCK_ENTITY):
                        continue
                    bes.append({"pos": [x - lx0, y - ly0, z - lz0], "snbt": snbt})
            es = [{"type": e["type"], "pos": [e["pos"][0] - lx0, e["pos"][1] - ly0, e["pos"][2] - lz0], "yaw": e["yaw"],
                   "pitch": 0.0, "snbt": e["snbt"]} for e in ents_all
                  if kind == "dilim" and ly0 <= e["pos"][1] < ly1 + 1 and lx0 <= e["pos"][0] < lx1 + 1 and lz0 <= e["pos"][2] < lz1 + 1]
            plan = Plan(origin=(ox + lx0, base + ly0, oz + lz0), cells=cells, palette=list(rpal), block_entities=bes, entities=es,
                        meta={"name": label, "part": i})
            t0 = time.time()
            extra = {"seconds": str(seconds)} if seconds else {}
            try:
                r = api.submit_plan(plan.to_bytes(), mode=mode, label=f"{label} ({i}/{n})", source="mcp", confirmed="1", **extra,
                                    allow_modify="1" if force else "0", allow_dangerous="0", group=grp)
                jid = r["id"]
                while True:
                    r = api.job(jid, wait_ms=15000)
                    if r.get("state") in ("DONE", "FAILED", "CANCELLED"):
                        break
            except GameError as e:                       # ornek: var olan bir yapiya dokunuyor -> bu yer olmaz, sonrakini dene
                r = {"state": "REFUSED", "message": str(e.payload.get("message") or e)}
            print(f"[{i}/{n}] {kind} {r.get('state')} {plan.count_solid():,} blok {time.time() - t0:.0f} sn {r.get('message', '')}", flush=True)
            if r.get("state") != "DONE":
                last_err = r.get("message", "") or r.get("state")
                for pj in reversed(placed):              # grup: sunucu hepsini tek istekte sirayla geri alir; hepsi beklenir
                    u = api.undo(pj)
                    for uid in (u.get("jobs") or ([u["id"]] if u.get("id") else [])):
                        while api.job(uid, wait_ms=15000).get("state") not in ("DONE", "FAILED", "CANCELLED"):
                            pass
                    if u.get("group"):
                        break
                ok = False
                break
            placed.append(jid)
            say(f"Stadyum kuruluyor: {i}/{n}")
        if ok:
            print("BITTI", flush=True)
            return True, (f"Usta Arena önüne kuruldu (merkez {ox},{oz}): 14,4 milyon blok, {len(placed)} parça; "
                          f"tek /usta geri hepsini birlikte geri alır.")
        if force:
            break
        say(f"Bu yer olmadı ({str(last_err)[:90]}); yanına/ilerisine kaydırıyorum…")
    return False, f"Stadyum kurulamadı: {last_err}. Önündeki yapının üstüne kurmak için: /usta stadyum zorla"


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x not in ("zorla", "deneme")]
    anc = {"x": float(a[1]), "z": float(a[2]), "facing": a[3]} if len(a) >= 4 else None
    ok, msg = main(a[0] if a else "", anc, force="zorla" in sys.argv, dry="deneme" in sys.argv)
    print(msg)
