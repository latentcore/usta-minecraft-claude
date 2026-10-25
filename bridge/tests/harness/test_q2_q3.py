"""Q2 (dogru yerlestirme) + Q3 (geri al / yinele) — test duzeni (harness) acikken calisir.
Calistirma: python scripts/dev/harness.py start --fresh ; pytest -q bridge/tests/harness/test_q2_q3.py
Her plan oyuncudan uzak (x>=1000) ayri bir yere kurulur: yuklu olmayan chunk'lara yazma da sinanir."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("USTA_GAME_DIR", str(ROOT / "mod" / "run" / "harness"))

from usta import blockdb  # noqa: E402
from usta.gameapi import GameAPI  # noqa: E402
from usta.kit.core import Build  # noqa: E402
from usta.worlddata import parse_blocks  # noqa: E402

from .plans import DANGEROUS, PLANS  # noqa: E402

GROUND_Y = -61
RESULTS: dict[str, dict] = {}


@pytest.fixture(scope="module")
def api():
    try:
        a = GameAPI()
        a.ping()
    except Exception:
        pytest.skip("test düzeni (harness) kapalı")
    return a


def _snap(api, box):
    x0, y0, z0, x1, y1, z1 = box
    for _ in range(8):
        blk = parse_blocks(api.blocks(x0, y0, z0, x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1, generate=True, timeout_ms=20000))
        if not (blk.cells == 0).any():
            break
        time.sleep(1.0)
    assert not (blk.cells == 0).any(), "anlık görüntüde yüklenmemiş hücre kaldı"
    states = {}
    for y in range(blk.size[1]):
        for z in range(blk.size[2]):
            for x in range(blk.size[0]):
                states[(x0 + x, y0 + y, z0 + z)] = blk.palette[int(blk.cells[y, z, x])]
    bes = {}
    for be in blk.block_entities:
        p = be["pos"]
        bes[(x0 + p[0], y0 + p[1], z0 + p[2])] = re.sub(r",?components:\{\}", "", be["snbt"])
    ents = api.entities(x0, y0, z0, x1, y1, z1)
    elist = sorted((e["type"], round(e["pos"][0], 1), round(e["pos"][1], 1), round(e["pos"][2], 1)) for e in ents
                   if e["type"] != "minecraft:player")
    return states, bes, elist


def _diff(a, b, keys=None):
    keys = keys if keys is not None else set(a) | set(b)
    return [k for k in keys if a.get(k) != b.get(k)]


@pytest.mark.parametrize("name", sorted(PLANS))
def test_place_undo_redo(api, name):
    db = blockdb.get()
    idx = sorted(PLANS).index(name)
    b = Build(name)
    PLANS[name](b)
    origin = (1000 + idx * 24, GROUND_Y, 1000)
    plan = b.to_plan(origin, "north")
    (ox, oy, oz) = plan.origin
    sx, sy, sz = plan.size
    m = 2
    box = (ox - m, oy - m, oz - m, ox + sx - 1 + m, oy + sy - 1 + m, oz + sz - 1 + m)
    before = _snap(api, box)
    t0 = time.time()
    r = api.submit_plan(plan.to_bytes(), mode="instant", label=f"q2-{name}", source="test", allow_dangerous=name in DANGEROUS)
    j = api.job(r["id"], wait_ms=60000)
    dt = time.time() - t0
    assert j["state"] == "DONE", j
    after = _snap(api, box)
    # --- Q2: plan hucreleri
    wrong = []
    for y in range(sy):
        for z in range(sz):
            for x in range(sx):
                pid = int(plan.cells[y, z, x])
                if pid == 0:
                    continue
                want = plan.palette[pid]
                exact = want.startswith("!")
                want = want.lstrip("!")
                got = after[0][(ox + x, oy + y, oz + z)]
                flags = db.flags_of(want)
                if (flags & blockdb.CONNECT) and not exact:
                    if want.split("[")[0] != got.split("[")[0]:
                        wrong.append(((x, y, z), want, got))
                elif got != want:
                    wrong.append(((x, y, z), want, got))
    # blok varligi verisi
    be_missing = []
    for (lx, ly, lz), snbt in plan_bes(plan).items():
        got = after[1].get((ox + lx, oy + ly, oz + lz), "")
        for token in re.findall(r'"([A-Za-zÇĞİÖŞÜçğıöşü][^"]*)"', snbt):
            if token not in got and token.strip('"') not in got:
                be_missing.append(((lx, ly, lz), token))
    items = [e for e in after[2] if e[0] in ("minecraft:item", "minecraft:falling_block")]
    ents_expected = len(plan.entities)
    ents_got = len([e for e in after[2] if e[0] not in ("minecraft:item", "minecraft:falling_block", "minecraft:experience_orb")]) - \
        len([e for e in before[2] if e[0] not in ("minecraft:item", "minecraft:falling_block", "minecraft:experience_orb")])
    # plan disi halka degismedi (sivi sizmasi / bozulma yok)
    ring = [k for k in before[0] if not (ox <= k[0] < ox + sx and oy <= k[1] < oy + sy and oz <= k[2] < oz + sz)]
    ring_changed = _diff(before[0], after[0], ring)
    res = {"seconds": round(dt, 2), "placed": j.get("placed"), "wrong": len(wrong), "be_missing": len(be_missing),
           "drops_or_falling": len(items), "entities_expected": ents_expected, "entities_new": ents_got,
           "ring_changed": len(ring_changed), "unsupported": j.get("unsupported"), "settled": j.get("settled_changed")}
    # --- Q3: geri al
    u = api.undo(r["id"])
    assert u.get("ok"), u
    uj = api.job(u["id"], wait_ms=60000)
    assert uj["state"] == "DONE", uj
    undone = _snap(api, box)
    res["undo_block_diff"] = len(_diff(before[0], undone[0]))
    res["undo_be_diff"] = len(_diff(before[1], undone[1]))
    res["undo_entity_diff"] = int(before[2] != undone[2])
    # --- Q3: yinele
    rr = api.redo(r["id"])
    assert rr.get("ok"), rr
    rj = api.job(rr["id"], wait_ms=60000)
    assert rj["state"] == "DONE", rj
    redone = _snap(api, box)
    res["redo_block_diff"] = len(_diff(after[0], redone[0]))
    res["redo_be_diff"] = len(_diff(after[1], redone[1]))
    res["redo_entity_diff"] = int(sorted((e[0]) for e in after[2]) != sorted((e[0]) for e in redone[2]))
    RESULTS[name] = res
    out = ROOT / "work" / "q2q3.json"
    prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    prev[name] = res
    out.write_text(json.dumps(prev, ensure_ascii=False, indent=1), encoding="utf-8")
    assert not wrong, wrong[:5]
    assert not be_missing, be_missing[:5]
    assert not items, items[:5]
    assert ents_got == ents_expected, (ents_got, ents_expected)
    assert not ring_changed, ring_changed[:5]
    assert j.get("unsupported", 0) == 0
    assert res["undo_block_diff"] == 0 and res["undo_be_diff"] == 0 and res["undo_entity_diff"] == 0, res
    assert res["redo_block_diff"] == 0 and res["redo_be_diff"] == 0 and res["redo_entity_diff"] == 0, res


def plan_bes(plan):
    return {tuple(be["pos"]): be["snbt"] for be in plan.block_entities}
