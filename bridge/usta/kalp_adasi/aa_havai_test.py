"""Havai fisek devresinin oyun ici denemesi: suda kucuk bir kopya (altin blok + kol, terasin altindaki gibi toz hatti,
yukari bakan firlatici, ayni roket verisi). Kol acik kurulur; motorun kizil tas uyandirma gecisi devreyi calistirir.
Roket varligi aranir, sonra deneme tamamen geri alinir.  python aa_havai_test.py x z"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import aa_core as C  # noqa: E402
import aa_front as F  # noqa: E402
from usta.gameapi import GameAPI  # noqa: E402
from usta.plan import Plan  # noqa: E402


def main(tx, tz):
    api = GameAPI(timeout=120)
    pal = ["keep", "minecraft:air"]

    def pid(s):
        c = C.DB.canonical(s)
        if c not in pal:
            pal.append(c)
        return pal.index(c)
    # yerel: x 0..6, y 0..4 (y0 = 63), z 0..2
    cells = np.zeros((5, 3, 8), np.uint16)
    q = pid(C.QUARTZ)
    for x in range(0, 6):
        cells[0, 1, x] = q                               # 63: destek
        cells[1, 1, x] = pid("redstone_wire[east=none,north=none,south=none,west=none,power=0]")   # 64: toz
        cells[2, 1, x] = q                               # 65: teras yuzeyi
    cells[2, 1, 0] = pid(C.GOLD)
    cells[3, 1, 0] = pid("lever[face=floor,facing=east,powered=true]")
    cells[0, 1, 6] = pid("dispenser[facing=up,triggered=false]")
    cells[1:5, 1, 6] = 1
    be = [{"pos": [6, 0, 1], "snbt": F.dispenser_snbt(0)}]
    plan = Plan(origin=(tx, 63, tz), cells=cells, palette=pal, block_entities=be, meta={"name": "havai fisek denemesi"})
    r = api.submit_plan(plan.to_bytes(), mode="instant", label="havai fişek denemesi", source="mcp", confirmed="1")
    jid = r["id"]
    while True:
        r = api.job(jid, wait_ms=5000)
        if r.get("state") in ("DONE", "FAILED", "CANCELLED"):
            break
    print("is:", r.get("state"), r.get("message", ""), flush=True)
    seen = []
    t0 = time.time()
    while time.time() - t0 < 6:
        es = api.entities(tx - 8, 60, tz - 8, tx + 16, 140, tz + 8)
        rk = [e for e in es if "firework" in e.get("type", "")]
        if rk:
            seen = rk
            break
        time.sleep(0.3)
    print("roket:", len(seen), [e.get("type") for e in seen][:3], flush=True)
    b = api.blocks(tx + 6, 63, tz + 1, 1, 1, 1, timeout_ms=5000)
    from usta.worlddata import parse_blocks
    bb = parse_blocks(b)
    print("firlatici:", bb.palette[int(bb.cells[0, 0, 0])], "BE:", str(bb.block_entities)[:300], flush=True)
    time.sleep(3)
    u = api.undo(jid)
    if u.get("id"):
        while True:
            r2 = api.job(u["id"], wait_ms=5000)
            if r2.get("state") in ("DONE", "FAILED", "CANCELLED"):
                break
    print("geri alindi", flush=True)
    return len(seen) > 0


if __name__ == "__main__":
    print("SONUC:", main(int(sys.argv[1]), int(sys.argv[2])))
