"""Kurulu Kalp Adasi'na yalniz degisen hucreleri uygular (onbellekteki G_kurulu.npy ile yeni G.npy farki): tek, geri
alinabilir duzeltme isi. Yeni durumda 'dokunma' (0) olup eskide dolu olan hucreler hava yapilir.
python aa_duzelt.py [kontrol]"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import aa_core as C  # noqa: E402
import aa_kur as K  # noqa: E402
from usta import blockdb  # noqa: E402
from usta.gameapi import GameAPI  # noqa: E402
from usta.plan import Plan  # noqa: E402


def main(check_only=False):
    out = K.OUT
    old = np.load(os.path.join(out, "G_kurulu.npy"), mmap_mode="r")
    new = np.load(os.path.join(out, "G.npy"), mmap_mode="r")
    m_old = json.load(open(os.path.join(out, "meta_kurulu.json"), encoding="utf-8"))
    m_new = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
    pal_old, pal = m_old["pal"], m_new["pal"]
    remap = {s: i for i, s in enumerate(pal)}
    conv = np.array([remap.get(s, -1) for s in pal_old], np.int64)
    if (conv < 0).any():                      # eski palette olup yenide olmayan durumlar: yeni palete ekle
        for i, s in enumerate(pal_old):
            if conv[i] < 0:
                pal.append(s)
                conv[i] = len(pal) - 1
    k, ax, az = C.place()
    dx, dz = ax - C.AX, az - C.AZ
    api = GameAPI(timeout=300)
    total = 0
    jobs = []
    for (ya, yb) in K.SLICES:
        o = conv[np.asarray(old[ya - C.Y0:yb - C.Y0 + 1]).astype(np.int64)]
        n_ = np.asarray(new[ya - C.Y0:yb - C.Y0 + 1]).astype(np.int64)
        diff = o != n_
        if not diff.any():
            continue
        cells = np.where(diff, np.where((n_ == 0) & (o > 1), 1, n_), 0).astype(np.uint16)
        nz = np.nonzero(cells.any(axis=0))
        ys = np.nonzero(cells.any(axis=(1, 2)))[0]
        z0, z1, x0, x1 = int(nz[0].min()), int(nz[0].max()), int(nz[1].min()), int(nz[1].max())
        y0, y1 = int(ys.min()), int(ys.max())
        sub = np.ascontiguousarray(cells[y0:y1 + 1, z0:z1 + 1, x0:x1 + 1])
        lx0, ly0, lz0 = C.X0 + x0, ya + y0, C.Z0 + z0
        bes = []
        for k, v in m_new["be"]:
            x, y, z = k
            if lx0 <= x <= lx0 + sub.shape[2] - 1 and ly0 <= y <= ly0 + sub.shape[0] - 1 and lz0 <= z <= lz0 + sub.shape[1] - 1:
                c = int(sub[y - ly0, z - lz0, x - lx0])
                if c > 1 and C.DB.flags_of(pal[c].lstrip("!")) & blockdb.BLOCK_ENTITY:
                    bes.append({"pos": [x - lx0, y - ly0, z - lz0], "snbt": v})
        p = Plan(origin=(lx0 + dx, ly0, lz0 + dz), cells=sub, palette=list(pal), block_entities=bes,
                 meta={"name": "Kalp Adası düzeltme"})
        cnt = int(np.count_nonzero(sub))
        total += cnt
        print(f"y {ya}-{yb}: {cnt} hucre, kutu {sub.shape[2]}x{sub.shape[0]}x{sub.shape[1]}", flush=True)
        if check_only:
            continue
        # koruma suzgeci burada kullanilmaz: fark hucreleri yalniz bizim kurdugumuz susler; yabanci yapiya dokunan
        # hucre olursa motor zaten reddeder (allow_modify=0)
        r = api.submit_plan(p.to_bytes(), mode="instant", label="Kalp Adası düzeltme", source="mcp", confirmed="1",
                            allow_modify="0", allow_dangerous="0")
        r = K.wait(api, r["id"])
        jobs.append(r.get("id"))
        print(f"  -> {r.get('state')} desteksiz {r.get('unsupported')} {r.get('message', '')}", flush=True)
        time.sleep(0.5)
    print(f"toplam {total} hucre, is {len(jobs)}")
    return jobs


if __name__ == "__main__":
    main(check_only="kontrol" in sys.argv)
