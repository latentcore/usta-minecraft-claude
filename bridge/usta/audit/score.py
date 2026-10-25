"""Puanlama yardimcilari.

* overall_score(findings): bulgulardan 0-100 genel denetim puani (onem agirlikli, kontrol basina tavanli).
* auto_scores(report, build): 10 olcutlu degerlendirme cizelgesi icin olculebilen alt puanlar (0-10) + gerekce;
  olculemeyen/oznel olcutler NEEDS_VISUAL ("needs_visual") ile isaretlenir: calisma anindaki Claude goruntulere
  bakip bunlari kendisi puanlar ve combine_scores ile birlestirir.
"""
from __future__ import annotations

import math
from collections import defaultdict

NEEDS_VISUAL = "needs_visual"

RUBRIC = ("siluet ve oran", "derinlik ve doku", "palet ve renk uyumu", "ayrıntı ve süs", "iç mekân ve işlev",
          "aydınlatma ve canavar güvenliği", "peyzaj ve araziye oturma", "tarz sadakati", "isteğe uygunluk", "teknik temizlik")

WEIGHTS = {"critical": 15.0, "major": 6.0, "minor": 2.0}
CAPS = {"critical": 30.0, "major": 14.0, "minor": 5.0}

TECH = {"empty_build", "unknown_blocks", "orphan_block_entity", "dangerous_blocks", "fire_hazard", "fluid_leak", "fluid_mix",
        "waterlogged_anomaly", "unsupported_gravity", "unsupported_attachables", "hanging_without_support", "broken_doors",
        "broken_beds", "broken_double_plants", "stair_orientation", "floating_blocks", "entity_on_solid",
        "structure_overlap", "protected_overlap"}
INTERIOR = {"empty_interior", "window_presence", "unreachable_rooms", "no_entrance", "stair_walkability", "headroom"}


def overall_score(findings) -> float:
    """100'den, her bulgu icin onem agirligi dusulur; ayni kontrol + onem icin ceza tavanlidir."""
    per: dict = defaultdict(float)
    for f in findings:
        per[(f.check, f.severity)] += WEIGHTS.get(f.severity, 2.0)
    pen = sum(min(v, CAPS.get(s, 5.0)) for (_c, s), v in per.items())
    return round(max(0.0, 100.0 - pen), 1)


def _clamp(v: float) -> float:
    return round(max(0.0, min(10.0, float(v))), 1)


def _pen(findings, checks, w=None) -> float:
    w = w or {"critical": 3.0, "major": 1.5, "minor": 0.5}
    return sum(w.get(f.severity, 0.5) for f in findings if f.check in checks)


def _names(findings, checks) -> str:
    ids = sorted({f.check for f in findings if f.check in checks})
    return ", ".join(ids) if ids else "bulgu yok"


def auto_scores(report, build=None) -> dict:
    """{olcut: (puan 0-10 | "needs_visual", gerekce)}. Olculebilenler bulgu ve istatistiklerden; kismi olanlarin
    gerekcesinde 'görselle doğrula' yazar."""
    st = getattr(report, "stats", None) or {}
    F = list(getattr(report, "findings", []) or [])
    out: dict = {}
    size = st.get("size") or [0, 0, 0]

    # 1) siluet ve oran (kismi)
    roof_pitch = float(st.get("roof_pitch", 0.0))
    levels = int(st.get("skyline_levels", 1))
    s = 5.0 + 2.5 * min(1.0, roof_pitch / 0.5) + 1.5 * min(1.0, max(0, levels - 1) / 4)
    s -= _pen(F, {"proportion"}, {"critical": 3, "major": 2, "minor": 1})
    s -= _pen(F, {"flat_roof"}, {"critical": 3, "major": 2, "minor": 1.5})
    s -= _pen(F, {"roof_presence"}, {"critical": 4, "major": 3, "minor": 1})
    out["siluet ve oran"] = (_clamp(s), f"kısmi (görselle doğrula): {size[0]}x{size[2]} taban, {size[1]} yükseklik; "
                                         f"eğimli çatı oranı %{roof_pitch * 100:.0f}, siluet kademesi {levels}; "
                                         f"bulgular: {_names(F, {'proportion', 'flat_roof', 'roof_presence'})}")

    # 2) derinlik ve doku
    rel = float(st.get("relief_ratio", 0.0))
    s = 10.0 * min(1.0, rel / 0.35)
    s -= _pen(F, {"flat_wall"}, {"critical": 3, "major": 2.5, "minor": 1.2})
    s -= _pen(F, {"monotone_block"}, {"critical": 3, "major": 2, "minor": 1})
    out["derinlik ve doku"] = (_clamp(s), f"cephe kabartma oranı %{rel * 100:.0f} (hedef ≥ %35); "
                                          f"bulgular: {_names(F, {'flat_wall', 'monotone_block'})}")

    # 3) palet ve renk uyumu (kismi)
    fam = int(st.get("families", 0))
    base = {0: 2, 1: 3, 2: 6, 3: 8, 4: 10, 5: 10, 6: 10, 7: 10, 8: 8, 9: 8, 10: 6}.get(fam, 4)
    s = base - _pen(F, {"palette_variety"}, {"critical": 3, "major": 2, "minor": 1.5}) - \
        _pen(F, {"monotone_block"}, {"critical": 2, "major": 1, "minor": 0.5})
    out["palet ve renk uyumu"] = (_clamp(s), f"kısmi (renk uyumunu görselle doğrula): {fam} malzeme ailesi (ideal 4-7), "
                                             f"baskın aile payı %{float(st.get('top_family_share', 0)) * 100:.0f}; "
                                             f"bulgular: {_names(F, {'palette_variety', 'monotone_block'})}")

    # 4) ayrinti ve sus (kismi)
    dec = float(st.get("decor_ratio", 0.0))
    s = 2.0 + 8.0 * min(1.0, dec / 0.25) - _pen(F, {"bare_windows"}, {"critical": 2, "major": 1.5, "minor": 1.5})
    out["ayrıntı ve süs"] = (_clamp(s), f"kısmi (görselle doğrula): cephede yarım/süs blok oranı %{dec * 100:.0f} (hedef ≥ %25); "
                                        f"bulgular: {_names(F, {'bare_windows'})}")

    # 5) ic mekan ve islev
    rooms = st.get("rooms")
    if not rooms:
        out["iç mekân ve işlev"] = (NEEDS_VISUAL, "Oda bulunamadı (ya da ölçülmedi): yapı türüne göre iç mekânı görselle değerlendir.")
    else:
        s = 10.0 - _pen(F, INTERIOR, {"critical": 4, "major": 2, "minor": 1})
        out["iç mekân ve işlev"] = (_clamp(s), f"{rooms} oda; bulgular: {_names(F, INTERIOR)}")

    # 6) aydinlatma ve canavar guvenligi
    n_dark = int(st.get("dark_spots", 0))
    s = 10.0 if n_dark == 0 else 10.0 - min(6.0, 1.5 * math.log2(1 + n_dark))
    s -= _pen(F, {"lighting_density"}, {"critical": 2, "major": 1, "minor": 0.7})
    dim = st.get("dim_fraction")
    if isinstance(dim, (int, float)) and dim > 0.5:
        s -= 1.0
    out["aydınlatma ve canavar güvenliği"] = (_clamp(s), f"{n_dark} karanlık nokta; loş zemin oranı "
                                                         f"{'?' if dim is None else f'%{dim * 100:.0f}'}; {st.get('light_sources', 0)} ışık kaynağı; "
                                                         f"bulgular: {_names(F, {'dark_spots', 'lighting_density'})}")

    # 7) peyzaj ve araziye oturma (kismi)
    lb = int(st.get("landscape_blocks", 0))
    foot = max(1, int(size[0]) * int(size[2]))
    s = 5.0 + 4.0 * min(1.0, lb / (0.3 * foot))
    s -= _pen(F, {"cliff_cut"}, {"critical": 4, "major": 3, "minor": 1.5})
    s -= _pen(F, {"floating_blocks"}, {"critical": 3, "major": 2, "minor": 1})
    terr = "arazi verisi var" if st.get("terrain") else "arazi verisi yok"
    out["peyzaj ve araziye oturma"] = (_clamp(s), f"kısmi (görselle doğrula, {terr}): {lb} peyzaj bloğu (bitki/yaprak/yol); "
                                                  f"bulgular: {_names(F, {'cliff_cut', 'floating_blocks'})}")

    # 8) tarz sadakati
    style = st.get("style") or ""
    out["tarz sadakati"] = (NEEDS_VISUAL, "Görüntülere bakıp istenen tarzın (" + (style or "belirtilmemiş") +
                            ") malzeme, çatı biçimi ve süs dilini puanla.")

    # 9) istege uygunluk
    req = st.get("request_eval")
    if req and req.get("total"):
        s = 10.0 * req["ok"] / req["total"]
        out["isteğe uygunluk"] = (_clamp(s), f"ölçülebilen istek maddeleri: {req['ok']}/{req['total']} uygun; " +
                                  "; ".join(req.get("notes", [])[:4]) + " (geri kalanını görselle doğrula)")
    else:
        out["isteğe uygunluk"] = (NEEDS_VISUAL, "İstek metnini görüntülerle karşılaştırıp puanla (boyut, kat, oda, öğeler).")

    # 10) teknik temizlik
    s = 10.0 - _pen(F, TECH, {"critical": 3, "major": 1.5, "minor": 0.5})
    nc = sum(1 for f in F if f.check in TECH and f.severity == "critical")
    nm = sum(1 for f in F if f.check in TECH and f.severity == "major")
    out["teknik temizlik"] = (_clamp(s), f"{nc} kritik, {nm} büyük teknik bulgu; {_names(F, TECH)}")
    return out


def combine_scores(auto: dict, visual: dict | None = None) -> dict:
    """Otomatik ve gorsel puanlari birlestirir. visual: {olcut: puan} (calisma anindaki Claude'un goruntu puanlari;
    otomatik sayisal puani da gecersiz kilabilir). Donus: {"criteria": {...}, "total": 0-100, "missing": [...]}."""
    visual = visual or {}
    crit, missing = {}, []
    for k in RUBRIC:
        v = visual.get(k)
        if v is None:
            a = auto.get(k)
            v = a[0] if a else None
        if isinstance(v, (int, float)):
            crit[k] = float(v)
        else:
            missing.append(k)
    total = round(10.0 * sum(crit.values()) / len(crit), 1) if crit else 0.0
    return {"criteria": crit, "total": total, "missing": missing}


__all__ = ["NEEDS_VISUAL", "RUBRIC", "overall_score", "auto_scores", "combine_scores"]
