"""Uretilmis Kalp Adasi'ni (onbellek G.npy + meta.json) dunyaya kurar: yatay dilimler halinde (alttan uste), her dilim
ayri, geri alinabilir is (/usta geri). Dunyadaki yer: tasarim cercevesi + aa_core.offset() (dx, dz).
Bir dilim reddedilirse o ana kadar kurulan dilimler geri alinir.
python aa_kur.py [kontrol] [--from N]   (kontrol: yalniz dogrula, gonderme)"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import aa_core as C  # noqa: E402
from usta import blockdb  # noqa: E402
from usta.gameapi import GameAPI  # noqa: E402
from usta.plan import Plan  # noqa: E402

OUT = os.environ.get("AA_OUT") or os.path.join(os.path.expanduser(r"~\UstaOyun"), "usta", "kalp_adasi_onbellek")
LABEL = "Kalp Adası"
SLICES = [(30, 47), (48, 56), (57, 62), (63, 65), (66, 71), (72, 79), (80, 92), (93, 120), (121, 150), (151, 180),
          (181, 210), (211, 240), (241, 268), (269, 319)]


def load(out=OUT):
    G = np.load(os.path.join(out, "G.npy"), mmap_mode="r")
    meta = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
    return G, meta


def slices(G, pal):
    """SLICES, tavandan sarkanlarin (fener, tavan zili/dugmesi, asili tabela) dayanagi ayni dilimde kalacak sekilde:
    dilim tepesinde sarkan varsa tepe yukari kayar (alttan uste kurulumda ara parcada desteksiz kalmasin)."""
    hang = np.array([("hanging=true" in s or "attachment=ceiling" in s or "face=ceiling" in s
                      or s.split("[")[0].endswith(("_hanging_sign", "spore_blossom", "hanging_roots"))) for s in pal], dtype=bool)
    out, ya = [], SLICES[0][0]
    top = min(SLICES[-1][1], C.Y0 + np.asarray(G).shape[0] - 1)
    for i, (_, yb) in enumerate(SLICES):
        if yb < ya:
            continue                                     # onceki dilim bunu yuttu
        last = i == len(SLICES) - 1
        while not last and yb < top and hang[np.asarray(G[yb - C.Y0])].any():
            yb += 1
        out.append((ya, min(yb, SLICES[-1][1])))
        ya = yb + 1
    return out


def plans(G, meta):
    """Dilim planlari; yerlesim (k, giris x, z) aa_core.place()'tan: dizi k kez 90 derece dondurulur, durumlar da."""
    k, ax, az = C.place()
    pal = meta["pal"]
    if k:
        rpal = []
        for s_ in pal:
            if s_ in ("keep", "minecraft:air"):
                rpal.append(s_)
                continue
            ex = s_.startswith("!")
            r = C.DB.rotate(s_[1:] if ex else s_, k)
            rpal.append(("!" + r) if ex else r)
    else:
        rpal = list(pal)
    be = [(tuple(kk), v) for kk, v in meta["be"]]
    ents = [e for e in meta["ents"] if "boat" not in e["type"]]     # tekne varliklari motorun varlik kuralina takilir
    out = []
    for i, (ya, yb) in enumerate(slices(G, pal)):
        sub = np.asarray(G[ya - C.Y0:yb - C.Y0 + 1])
        nz = np.nonzero(sub.any(axis=0))
        if len(nz[0]) == 0:
            continue
        z_lo, z_hi = int(nz[0].min()), int(nz[0].max())
        x_lo, x_hi = int(nz[1].min()), int(nz[1].max())
        ys = np.nonzero(sub.any(axis=(1, 2)))[0]
        y_lo, y_hi = int(ys.min()), int(ys.max())
        cells = np.ascontiguousarray(sub[y_lo:y_hi + 1, z_lo:z_hi + 1, x_lo:x_hi + 1])
        dx0, dz0 = C.X0 + x_lo, C.Z0 + z_lo                     # tasarim cercevesinde kutu kosesi
        dx1, dz1 = dx0 + cells.shape[2] - 1, dz0 + cells.shape[1] - 1
        ly0, ly1 = ya + y_lo, ya + y_lo + cells.shape[0] - 1
        xl, xh, zl, zh = dx0 - C.AX, dx1 - C.AX, dz0 - C.AZ, dz1 - C.AZ
        arr = cells
        for _ in range(k):
            arr = arr.transpose(0, 2, 1)[:, :, ::-1]
            xl, xh, zl, zh = -zh, -zl, xl, xh
        arr = np.ascontiguousarray(arr)
        ox, oz = ax + xl, az + zl
        bes = []
        for (x, y, z), snbt in be:
            if dx0 <= x <= dx1 and ly0 <= y <= ly1 and dz0 <= z <= dz1:
                st = pal[int(cells[y - ly0, z - dz0, x - dx0])]
                if st in ("keep", "minecraft:air") or not (C.DB.flags_of(st.lstrip("!")) & blockdb.BLOCK_ENTITY):
                    continue
                rx, rz = C.rot_xz(x - C.AX, z - C.AZ, k)
                bes.append({"pos": [ax + rx - ox, y - ly0, az + rz - oz], "snbt": snbt})
        es = []
        for e in ents:
            x, y, z = e["pos"]
            if ly0 <= y < ly1 + 1 and dx0 <= x < dx1 + 1 and dz0 <= z < dz1 + 1:
                rx, rz = C.rot_xz(x - 0.5 - C.AX, z - 0.5 - C.AZ, k)
                es.append({"type": e["type"], "pos": [ax + rx + 0.5 - ox, y - ly0, az + rz + 0.5 - oz],
                           "yaw": (float(e.get("yaw", 0)) + 90 * k) % 360, "pitch": 0.0, "snbt": e.get("snbt", "{}")})
        out.append(Plan(origin=(int(ox), ly0, int(oz)), cells=arr, palette=list(rpal), block_entities=bes, entities=es,
                        meta={"name": LABEL, "part": i + 1}))
    return out


NATURAL = {"water", "air", "cave_air", "void_air", "sand", "red_sand", "gravel", "stone", "dirt", "coarse_dirt", "clay",
           "kelp", "kelp_plant", "seagrass", "tall_seagrass", "sea_pickle", "bubble_column", "granite", "diorite", "andesite",
           "tuff", "deepslate", "sandstone", "grass_block", "moss_block", "glow_lichen", "dripstone_block",
           "pointed_dripstone", "bedrock", "short_grass", "tall_grass", "fern"}


def natural_name(state: str) -> bool:
    """Kesin dogal blok mu (emin olunmayan her sey korunur: harabe tuglasi, magma, kalsit, obsidyen...)."""
    n = state.split("[", 1)[0].split(":")[-1]
    return n in NATURAL or n.endswith("_ore") or ("coral" in n and "dead" not in n)


def keep_world(state: str) -> bool:
    """Dunyadaki bu blok korunur mu: adanin kesin dogal listesinde degil ya da motor onu yapi sayiyor (motorun
    'var olan yapi' reddiyle birebir ayni olsun diye blok veritabanindaki dogal bayragi da sorulur)."""
    if not natural_name(state):
        return True
    db = C.DB
    if not db.natural.any():                         # eski veritabani: dogal bayragi yok
        return False
    try:
        return not bool(db.natural[db.id(state)])
    except Exception:
        return True


def protect_existing(api, p, say=print):
    """Dunyadaki dogal olmayan bloklarin (okyanus aniti, harabe, batik gemi, yikik portal...) hucrelerini 'dokunma' yapar."""
    from usta.worlddata import parse_blocks
    ox, oy, oz = p.origin
    sy, sz, sx = p.cells.shape
    kept = 0
    for x in range(0, sx, 64):
        for z in range(0, sz, 64):
            wx, wz = min(64, sx - x), min(64, sz - z)
            b = parse_blocks(api.blocks(ox + x, oy, oz + z, wx, sy, wz, timeout_ms=60000))
            bad = np.array([keep_world(n) for n in b.palette])
            m = bad[b.cells]
            m &= b.cells != 0
            if m.any():
                view = p.cells[:, z:z + wz, x:x + wx]
                hit = m & (view != 0)
                kept += int(hit.sum())
                view[hit] = 0
    if kept:
        p.block_entities[:] = [e for e in p.block_entities
                               if p.cells[e["pos"][1], e["pos"][2], e["pos"][0]] != 0]
        say(f"  var olan yapilara dokunulmadi: {kept:,} hucre korundu")
    return kept


def wait(api, jid, say=print):
    while True:
        r = api.job(jid, wait_ms=15000)
        if r.get("state") in ("DONE", "FAILED", "CANCELLED"):
            return r
        if r.get("state") == "AWAITING_CONFIRM":
            api.job_action(jid, "confirm")


def undo_all(api, ids, say=print):
    """Parcalari en yeniden geri alir. Ayni gruptaki parcalari sunucu tek istekte sirayla kuyruga koyar: hepsi beklenir,
    sonraki parcalar icin yeniden istenmez (iki kez geri alma olmaz)."""
    for jid in reversed(ids):
        try:
            u = api.undo(jid)
            for uid in (u.get("jobs") or ([u["id"]] if u.get("id") else [])):
                wait(api, uid)
            if u.get("group"):
                break
        except Exception as e:  # pragma: no cover
            say(f"geri alma hatasi {jid}: {e}")


def main(check_only=False, start=1, say=print):
    api = GameAPI(timeout=400)
    G, meta = load()
    ps = plans(G, meta)
    n = len(ps)
    total = sum(p.count_solid() for p in ps)
    say(f"{n} dilim, {total:,} blok; yerlesim {C.place()}")
    for i, p in enumerate(ps, 1):
        v = api.validate_plan(p.to_bytes())
        if not v.get("ok", True) or v.get("problems"):
            say(f"[{i}/{n}] DOGRULAMA: " + json.dumps(v, ensure_ascii=False)[:1500])
            return False, []
        sx, sy, sz = p.size
        say(f"[{i}/{n}] koken {p.origin} boyut {sx}x{sy}x{sz} blok {p.count_solid():,} BE {len(p.block_entities)} "
            f"varlik {len(p.entities)} degisim {v.get('changes')}")
    if check_only:
        return True, []
    placed = []
    grp = f"ada-{int(time.time() * 1000)}"               # parcalar tek grup: tek /usta geri hepsini birlikte geri alir
    for i, p in enumerate(ps, 1):
        if i < start:
            continue
        t0 = time.time()
        p.cells = np.array(p.cells, dtype=np.uint16)
        protect_existing(api, p, say)
        r = api.submit_plan(p.to_bytes(), mode="instant", label=f"{LABEL} ({i}/{n})", source="mcp", confirmed="1",
                            allow_modify="0", allow_dangerous="0", group=grp)
        jid = r["id"]
        r = wait(api, jid)
        st = r.get("state")
        say(f"[{i}/{n}] {st} {time.time() - t0:.0f} sn {r.get('message', '')}")
        if st != "DONE":
            say(json.dumps(r, ensure_ascii=False)[:2000])
            undo_all(api, placed, say)
            return False, placed
        placed.append(jid)
        time.sleep(1)
    return True, placed


if __name__ == "__main__":
    st = int(sys.argv[sys.argv.index("--from") + 1]) if "--from" in sys.argv else 1
    ok, ids = main(check_only="kontrol" in sys.argv, start=st)
    print("BITTI" if ok else "KURULAMADI", ids)
