"""Usta denetçisi: bir Build'i 38 kontrolden geçirir, 0-100 puanlar ve her bulgu için Türkçe düzeltme önerir.

Kullanım:
    from usta.audit import audit
    rep = audit(b)                      # ya da audit(b, context={...})
    print(rep.summary())                # Türkçe özet (önem sırasıyla)
    rep.to_dict()                       # JSON: score, critical/major/minor, findings, auto_scores, stats
    rep.has("dark_spots"); rep.by_check("flat_wall")
Her bulgu: check (id), severity (critical | major | minor), message, positions (yerel örnek koordinatlar [x,y,z]),
count, fix (somut çözüm). critical = oyun/dünya bozulur; major = belirgin kusur; minor = iyileştirme/ipucu.
auto_scores: 10 ölçütlü çizelge (siluet ve oran ... teknik temizlik); öznel ölçütler "needs_visual" — onları
görüntülere bakıp sen puanla, score.combine_scores(auto, {ölçüt: puan}) ile birleştir.

Bağlam (context, hepsi isteğe bağlı, yerel çerçevede):
  ground_y (varsayılan 0 = zemin üstü bloğu seviyesi; altındaki 'keep' hücreleri arazi sayılır),
  heightmap [z][x] (arazinin en üst blok y'si) + heightmap_origin (x0, z0) → cliff_cut ve zemin,
  structures / protected: kutu listesi [x0,y0,z0,x1,y1,z1] ya da {"box": [...], "name": ...},
  protected_mask {"origin": (x,y,z), "mask": [y][z][x]}, entrances [(x,y,z)], anchors [(x,y,z)],
  style / type (ör. "modern", "kule", "köprü"), request {"size": [w,h,d], "floors": n, "rooms": n, "blocks": [...]}.
Meta: b.meta["rooms"] = [{"name", "box": [x0,y0,z0,x1,y1,z1] (iç hava), "type"}], "doors" = [{"pos": [x,y,z]}],
"floors" = [y, ...] kullanılır; meta yoksa odalar otomatik bulunur (örtülü, duvarla çevrili hava).

Kontroller (id — ne arar):
  empty_build — yapı boş, hiç blok yok
  unknown_blocks — 26.3 veritabanında olmayan/geçersiz özellikli blok durumu
  orphan_block_entity — NBT (blok varlığı) blok varlığı olmayan hücreye yazılmış
  dangerous_blocks — TNT, lav, ateş (ve TNT/kristal varlıkları) var
  fire_hazard — ateş/lav yanıcı bloklara yangın yayacak kadar yakın; kamp ateşinin üstü yanıcı
  fluid_leak — su/lav kapalı havuzda değil: yanı/altı açık ya da plan dışına komşu
  fluid_mix — su ile lav temas ediyor (taş/obsidyen oluşur)
  waterlogged_anomaly — kuru yerde waterlogged=true (su taşar) ya da su içinde waterlogged=false
  unsupported_gravity — kum/çakıl/beton tozu/örsün altı boş (hava/sıvı/keep)
  unsupported_attachables — meşale, fener, ladder, tabela, flama, buton, halı, çiçek vb. gereken yüzde destek yok
  hanging_without_support — asılı fener/tabela/sarkan bitki tavana bağlı değil; zincir ucu boşlukta
  broken_doors — kapının alt/üst yarısı eksik ya da uyumsuz; altında sağlam zemin yok
  door_blocked — kapının önü ya da arkası dolu: kapı duvara açılıyor, geçilemez
  window_blocked — cam dört yandan duvarla kapalı: pencere hiçbir yöne bakmıyor
  broken_beds — yatağın baş/ayak parçası eksik ya da yönü uyumsuz
  broken_double_plants — uzun bitkinin (uzun ot, ayçiçeği, leylak...) yarısı eksik
  stair_orientation — basamak yükseliş yönüne ters (testere dişi çatı) ya da yürünen dizide ters basamak
  stair_walkability — basamak üstünde 2 blok baş boşluğu yok; oda/kat havayla bağlı ama yürünerek çıkılamıyor
  headroom — kapının önü/arkası ya da yol üstü 2 bloktan alçak; kapı boşluğa açılıyor
  no_entrance — iç mekâna dışarıdan yürüyerek girilemiyor (kapı/açıklık yok ya da eşik çok yüksek)
  unreachable_rooms — oda tamamen kapalı (kapı/açıklık yok); kapalı çatı arası
  entity_on_solid — tablo/eşya çerçevesinin arkasında duvar yok ya da bloğun içinde
  structure_overlap — bağlamdaki mevcut yapı kutularıyla çakışma
  protected_overlap — korumalı bölgeye (kutu/maske) dokunma
  cliff_cut — yapı kenarında arazide 3 bloktan yüksek sert basamak (yarma/dolgu) [heightmap gerekir]
  floating_blocks — zemine ya da yapıya bağlı olmayan havada blok kümeleri
  flat_wall — büyük düz, derinliksiz duvar yüzeyi (≥ 8x5)
  monotone_block — tek blok cepheye ya da bütün yapıya hâkim
  proportion — çok ince-uzun / uzun-basık kütle ya da 2 blokluk basık iç tavan
  palette_variety — malzeme ailesi çok az (1-2) ya da çok fazla; renk karmaşası
  window_presence — kapalı oda penceresiz
  roof_presence — duvarlarla çevrili hacmin üstü açık (çatı yok)
  empty_interior — büyük oda boş ya da çok seyrek döşenmiş
  lighting_density — iç mekân loş (ışık < 8), ışık kalabalığı ya da giriş önü karanlık
  dark_spots — üstü örtülü, blok ışığı 0, canavar doğabilecek nokta
  symmetry_rhythm — (ipucu) neredeyse simetrik cephe ya da düzensiz pencere aralıkları
  flat_roof — düz kutu çatı: tek seviye, eğim/saçak yok
  bare_windows — çerçevesiz "delik" pencereler (pervaz/kepenk/girinti yok)
"""
from __future__ import annotations

import time
from collections import defaultdict

from .checks import CHECKS, SEV_RANK, SEVERITIES, Check, Ctx, Finding, Report, global_stats  # noqa: F401
from .score import NEEDS_VISUAL, RUBRIC, auto_scores, combine_scores, overall_score  # noqa: F401


def _eval_request(ctx: Ctx, stats: dict) -> dict | None:
    req = ctx.context.get("request")
    if not isinstance(req, dict) or not req:
        return None
    ok = total = 0
    notes = []
    size = stats.get("size") or [0, 0, 0]
    want = req.get("size")
    if want and len(want) == 3:
        for i, ax in enumerate(("genişlik", "yükseklik", "derinlik")):
            if want[i]:
                total += 1
                if abs(size[i] - want[i]) <= max(2, 0.15 * want[i]):
                    ok += 1
                else:
                    notes.append(f"{ax} {size[i]} (istenen {want[i]})")
    if req.get("rooms"):
        total += 1
        n = int(stats.get("rooms") or 0)
        if n >= int(req["rooms"]):
            ok += 1
        else:
            notes.append(f"oda {n} (istenen {req['rooms']})")
    if req.get("floors"):
        total += 1
        lv = len({int(r.bbox[0]) for r in ctx.used_rooms()}) if "rooms" in ctx.__dict__ else 0
        if lv >= int(req["floors"]):
            ok += 1
        else:
            notes.append(f"kat {lv} (istenen {req['floors']})")
    for blk in req.get("blocks") or []:
        total += 1
        b = str(blk).split(":")[-1]
        if any(nm == b for nm in ctx.names):
            ok += 1
        else:
            notes.append(f"{b} yok")
    return {"ok": ok, "total": total, "notes": notes}


def audit(build, context: dict | None = None, checks=None, skip=None) -> Report:
    """Yapıyı denetler. checks: yalnız bu kontrol id'leri (liste); skip: atlanacak id'ler. Donus: Report."""
    t0 = time.perf_counter()
    ctx = Ctx(build, context)
    order = {c: i for i, c in enumerate(CHECKS)}
    findings, errors, ran, timings = [], {}, [], {}
    want = None if checks is None else set([checks] if isinstance(checks, str) else checks)
    for cid, chk in CHECKS.items():
        if want is not None and cid not in want:
            continue
        if skip and cid in skip:
            continue
        if ctx.n_blocks == 0 and cid != "empty_build":
            continue
        ran.append(cid)
        t = time.perf_counter()
        try:
            res = chk.func(ctx) or []
        except Exception as e:  # bir kontrolun cokmesi butun denetimi durdurmasin
            errors[cid] = f"{type(e).__name__}: {e}"
            res = []
        timings[cid] = round(time.perf_counter() - t, 4)
        findings.extend(res)
    findings.sort(key=lambda f: (SEV_RANK.get(f.severity, 3), order.get(f.check, 99)))
    stats = ctx.stats
    if ctx.n_blocks:
        try:
            stats = global_stats(ctx)
            rq = _eval_request(ctx, stats)
            if rq:
                stats["request_eval"] = rq
        except Exception as e:  # pragma: no cover - savunma
            errors["global_stats"] = f"{type(e).__name__}: {e}"
    stats["timings"] = timings
    rep = Report(getattr(build, "name", "yapı"), findings, overall_score(findings), stats, ran, errors)
    rep.auto_scores = auto_scores(rep, build)
    rep.seconds = time.perf_counter() - t0
    return rep


def audit_plan(plan, context: dict | None = None) -> dict:
    """Plan (USTAPLN1) denetimi: plani yapinin kendi yerel cercevesine geri cevirir (meta 'facing' ve
    'local_origin_world' varsa) ki meta odalari hizalansin; sonra audit(...).to_dict()."""
    from ..kit.core import FACINGS, Build
    meta = dict(getattr(plan, "meta", None) or {})
    b0 = Build(str(meta.get("label") or meta.get("name") or "plan"))
    facing = meta.get("facing")
    low = meta.get("local_origin_world")
    off = (0, 0, 0)
    times = 0
    if facing in FACINGS and low is not None and len(low) == 3:
        times = FACINGS.index(facing)
        off = tuple(int(plan.origin[i]) - int(low[i]) for i in range(3))
    remap = []
    for s in plan.palette:
        try:
            remap.append(b0.pid(s) if s != "keep" else 0)
        except Exception:
            b0.palette.append(s)
            b0._pid[s] = len(b0.palette) - 1
            remap.append(len(b0.palette) - 1)
    import numpy as np
    ids = np.asarray(remap, dtype=np.int32)[plan.cells]
    b0.put_ids(off[0], off[1], off[2], ids)
    for be in plan.block_entities or []:
        p = be.get("pos") or [0, 0, 0]
        b0.block_entities[(int(p[0]) + off[0], int(p[1]) + off[1], int(p[2]) + off[2])] = be.get("snbt", "{}")
    for e in plan.entities or []:
        p = e.get("pos") or [0, 0, 0]
        b0.add_entity(e.get("type", ""), p[0] + off[0], p[1] + off[1], p[2] + off[2], e.get("yaw", 0), e.get("pitch", 0),
                      e.get("snbt", "{}"))
    b = b0
    if times:
        try:
            b = b0.transformed(rotate=(4 - times) % 4)
        except Exception:
            b = b0
            meta.pop("rooms", None)
    for k in ("rooms", "doors", "windows", "lights", "floors", "notes"):
        if isinstance(meta.get(k), list):
            b.meta[k] = list(meta[k])
    if meta.get("style"):
        b.meta["style"] = meta["style"]
    return audit(b, context).to_dict()


def false_alarm_rate(samples, min_severity: str = "minor", checks=None) -> dict:
    """Temiz (kusursuz kabul edilen) örnek yapılarda yanlış alarm ölçümü.
    samples: Build listesi ya da (Build, context) çiftleri. min_severity: bu önem ve üstü sayılır.
    Donus: {"rate": bulgu çıkan (örnek, kontrol) çiftleri / (örnek x kontrol), "fired": {id: örnek sayısı},
    "samples": n, "checks": m, "details": [{"name", "fired", "score"}]}."""
    rank = SEV_RANK[min_severity]
    fired: dict = defaultdict(int)
    details = []
    n = m = 0
    for s in samples:
        b, cx = (s if isinstance(s, tuple) else (s, None))
        rep = audit(b, cx, checks=checks)
        ids = sorted({f.check for f in rep.findings if SEV_RANK.get(f.severity, 3) <= rank})
        for i in ids:
            fired[i] += 1
        details.append({"name": getattr(b, "name", "?"), "fired": ids, "score": rep.score, "errors": rep.errors})
        n += 1
        m = max(m, len(rep.checks_run))
    total = n * m
    return {"rate": (sum(fired.values()) / total) if total else 0.0, "samples": n, "checks": m, "fired": dict(fired),
            "details": details}


__all__ = ["audit", "audit_plan", "false_alarm_rate", "Report", "Finding", "CHECKS", "Ctx", "auto_scores",
           "combine_scores", "overall_score", "RUBRIC", "NEEDS_VISUAL"]
