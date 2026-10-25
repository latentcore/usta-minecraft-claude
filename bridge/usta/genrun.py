"""Parametrik ureteci calistirir: yer bulur, arazi yuksekliklerini YEREL cerceveye dondurur, kum havuzunda
gen.build(name, params, ctx) cagirir, taslak + denetim + onizleme dondurur (U4b: hizin anahtari)."""
from __future__ import annotations

import io
import json
import math

import numpy as np

from . import ops, site as sitemod
from .kit.core import FACINGS, _rot_xz
from .plan import Plan
from .worlddata import UNKNOWN, parse_columns


def local_terrain(api, origin: list[int], facing: str, width: int, depth: int, margin: int = 4) -> dict:
    """Yerel cercevede (x: 0..width-1 + pay, z: 0..depth-1 + pay) zemin yukseklikleri, origin y'sine gore."""
    times = FACINGS.index(facing)
    ox, oy, oz = origin
    lx = np.arange(-margin, width + margin)
    lz = np.arange(-margin, depth + margin)
    LX, LZ = np.meshgrid(lx, lz)
    RX, RZ = LX.copy(), LZ.copy()
    for _ in range(times % 4):
        RX, RZ = -RZ, RX.copy()
    WX, WZ = ox + RX, oz + RZ
    x0, x1, z0, z1 = int(WX.min()), int(WX.max()), int(WZ.min()), int(WZ.max())
    cols = parse_columns(api.columns(x0, z0, x1, z1, timeout_ms=6000))
    mk = sitemod.masks(cols)
    gi, gj = WZ - cols.z0, WX - cols.x0

    def take(a):
        return a[gi, gj]
    ground = take(np.where(mk["water"], cols.floor, cols.ground)).astype(np.int32)
    known = take(mk["known"])
    ground = np.where(known, ground - oy, 0)
    water_top = np.where(known, take(cols.ground) - oy, 0)     # su kolonlarinda su yuzeyinin yerel y'si
    out = {"ground": ground.astype(np.int32), "water": take(mk["water"]), "water_top": water_top.astype(np.int32), "tree": take(mk["tree"]),
           "artificial": take(mk["artificial"]), "known": known, "margin": np.array(margin)}
    biomes = cols.biomes
    if biomes:
        ids, cnt = np.unique(cols.biome[mk["known"]], return_counts=True)
        out["_biome"] = biomes[int(ids[int(np.argmax(cnt))])] if len(ids) else "minecraft:plains"
    return out


WATER_GENS = ("arch_bridge", "pier", "lighthouse")   # suya uzanan yapilar: yer bulucu su ustune izin verir


def run(name: str, params: dict, where: str = "front", origin: list[int] | None = None, facing: str | None = None,
        request_id: str | None = None, preview_kind: str = "standard") -> tuple[dict, bytes | None, str | None]:
    from . import sandbox
    from .kit import gen
    spec = gen.GENERATORS.get(name)
    if spec is None:
        return {"ok": False, "message": f"bilinmeyen üreteç: {name}", "available": sorted(gen.GENERATORS)}, None, None
    w, d = spec.footprint(params)
    api = ops.game()
    site = None
    if origin is None:
        info, _, _ = ops.site_candidates(w, d, where, request_id=request_id, max_dist=int(params.get("max_dist", 40)),
                                         allow_water=bool(params.get("on_water", name in WATER_GENS or max(w, d) >= 100)))
        cands = info.get("candidates") or []
        if not cands:                                  # duz/bos aday yok: oyuncunun onundeki alan duzlenerek kullanilir
            info, _, _ = ops.site_candidates(w, d, where, request_id=request_id, max_dist=int(params.get("max_dist", 40)),
                                             allow_water=bool(params.get("on_water", name in WATER_GENS or max(w, d) >= 100)),
                                             force=True)
            cands = info.get("candidates") or []
        if not cands:
            return {"ok": False, "message": info.get("message", "uygun yer yok"), "footprint": [w, d]}, None, None
        site = cands[0]
        origin, facing = site["origin"], site["facing"]
    facing = facing or "north"
    terr = local_terrain(api, origin, facing, w, d, margin=12)  # peyzaj halkasi (agaclar) da araziyi bilsin
    if name in ("lighthouse", "pier") and terr["water"].any():   # kiyi yapisi: taban su yuzeyinin ustunde (denizde kuru cukur yok)
        wtop = int(np.max(terr["water_top"][terr["water"]]))
        if wtop >= 0:
            origin = [origin[0], origin[1] + wtop + 1, origin[2]]
            terr = local_terrain(api, origin, facing, w, d, margin=12)
    biome = terr.pop("_biome", "minecraft:plains")
    buf = io.BytesIO()
    np.savez(buf, **{k: np.asarray(v) for k, v in terr.items()})
    ctx = {"site": {"origin": origin, "facing": facing, **({k: site[k] for k in ("x0", "z0", "x1", "z1", "ground_y")} if site else {})},
           "biome": biome, "request": request_id, "generator": name, "params": params}
    code = ("c = dict(ctx)\nc['terrain'] = globals().get('terrain')\n"
            f"b = gen.build({name!r}, {json.dumps(params, ensure_ascii=False)}, c)\n"
            f"result(b, origin={list(origin)!r}, facing={facing!r}, label={spec.label(params)!r})\n")
    r = sandbox.run_script(code, ctx, files={"terrain.npz": buf.getvalue()}, timeout=float(params.get("timeout", 120)))
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error"), "traceback": r.get("traceback", "")[-1500:]}, None, None
    plan = Plan.load(r["plan_path"])
    dr = ops.new_draft(plan, spec.label(params), f"gen:{name}", request_id)
    summ = ops.plan_summary(plan)
    summ.update({"draft_id": dr.id, "generator": name, "params": params, "site": site, "biome": biome,
                 "script_seconds": r.get("seconds")})
    m = int(np.asarray(terr["margin"]))
    actx = {"heightmap": np.asarray(terr["ground"]), "heightmap_origin": (-m, -m)}  # arazi: egimde agac/bitki 'havada' sayilmasin
    wmask = np.asarray(terr.get("water", np.zeros_like(terr["ground"], bool)), bool)
    if wmask.any():                                    # su kolonlari: su alti karanlik/ucurum sayilmaz
        from .kit.gen.monuments import water_level
        from .kit.gen.common import Ground
        actx.update(water_mask=wmask, water_level=water_level(Ground(np.asarray(terr["ground"]), m, wmask, terr.get("water_top"))))
    summ["audit"] = ops._audit_brief(ops.audit_plan(plan, actx))
    dr.summary = summ
    dr.save()
    info, data, path = ops.preview(plan=plan, kind=preview_kind)
    summ["preview"] = path
    return summ, data, path


__all__ = ["run", "local_terrain", "math", "UNKNOWN", "_rot_xz"]
