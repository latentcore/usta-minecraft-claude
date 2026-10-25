"""Yapi kutuphanesi (C9): kaydet, adlandir, etiketle, onizle, yukle (dondur/aynala/tasi), sil; sematik ice/disa aktarma."""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import numpy as np

from . import config
from .plan import AIR, KEEP, Plan
from .render.sheet import sheet, to_jpeg_bytes
from .render.views import Volume
from .worlddata import parse_blocks


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name.lower().replace("ı", "i")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "yapi"


def _dir() -> Path:
    return config.library_dir()


def save_plan(plan: Plan, name: str, tags: list[str] | None = None, source: dict | None = None) -> dict:
    sl = slug(name)
    d = _dir() / sl
    k = 2
    while d.exists():
        d = _dir() / f"{sl}-{k}"
        k += 1
    d.mkdir(parents=True)
    rel = Plan(origin=(0, 0, 0), cells=plan.cells, palette=plan.palette, block_entities=plan.block_entities,
               entities=plan.entities, meta=dict(plan.meta))
    rel.save(str(d / "yapi.uplan"))
    try:
        vol = Volume(np.where(rel.cells == 1, 0, rel.cells), list(rel.palette))
        (d / "onizleme.jpg").write_bytes(to_jpeg_bytes(sheet(vol, kind="quick"), max_side=800))
    except Exception:
        pass
    item = {"name": name, "id": d.name, "size": list(rel.size), "blocks": int(np.count_nonzero(rel.cells > 1)),
            "tags": tags or [], "created": time.time(), "source": source or {}}
    (d / "bilgi.json").write_text(json.dumps(item, ensure_ascii=False, indent=1), encoding="utf-8")
    return item


def save_from_world(api, entry: dict, name: str, tags: list[str] | None = None) -> dict:
    ox, oy, oz, sx, sy, sz = entry["box"]
    blk = parse_blocks(api.blocks(ox, oy, oz, sx, sy, sz, dim=entry.get("dim")))
    pal = [KEEP] + [p for p in blk.palette[1:]]
    if AIR not in pal:
        pal.insert(1, AIR)
    remap = np.array([0] + [pal.index(p) for p in blk.palette[1:]], dtype=np.int32)
    cells = remap[blk.cells]
    # palet sirasi: keep, air zorunlu
    if pal[1] != AIR:
        ai = pal.index(AIR)
        pal[1], pal[ai] = pal[ai], pal[1]
        cells = np.where(cells == 1, -1, cells)
        cells = np.where(cells == ai, 1, cells)
        cells = np.where(cells == -1, ai, cells)
    bes = [{"pos": be["pos"], "snbt": be["snbt"]} for be in blk.block_entities]
    plan = Plan(origin=(0, 0, 0), cells=cells.astype(np.int32), palette=pal, block_entities=bes, meta={"name": name})
    return save_plan(plan, name, tags, {"job": entry.get("id"), "box": entry["box"]})


def list_items() -> list[dict]:
    out = []
    for f in sorted(_dir().glob("*/bilgi.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    out.sort(key=lambda i: -i.get("created", 0))
    return out


def load_plan(item_id: str) -> Plan:
    p = _dir() / item_id / "yapi.uplan"
    if not p.exists():
        cands = [i for i in list_items() if i["name"].lower() == item_id.lower() or i["id"] == slug(item_id)]
        if not cands:
            raise KeyError(f"kütüphanede yok: {item_id}")
        p = _dir() / cands[0]["id"] / "yapi.uplan"
    return Plan.load(str(p))


def delete(item_id: str) -> bool:
    import shutil
    d = _dir() / item_id
    if d.exists():
        shutil.rmtree(d)
        return True
    return False


def export(item_id: str, fmt: str) -> str:
    from .schem import EXPORTERS
    plan = load_plan(item_id)
    data = EXPORTERS[fmt](plan, item_id) if fmt != "nbt" else EXPORTERS[fmt](plan)
    out = config.data_dir() / "disari" / f"{item_id}.{ 'schem' if fmt == 'schem' else fmt}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return str(out)


def import_file(path: str, name: str | None = None) -> dict:
    from .schem import IMPORTERS
    ext = Path(path).suffix.lower().lstrip(".")
    if ext not in IMPORTERS:
        raise ValueError("desteklenen: .schem, .litematic, .nbt")
    plan = IMPORTERS[ext](Path(path).read_bytes())
    return save_plan(plan, name or Path(path).stem, ["içe-aktarma"], {"file": Path(path).name})
