"""Arac seti basvurusu (kit_reference araci icin): modul belgeleri ve kataloglar."""
from __future__ import annotations

import importlib
import inspect

TOPICS = {
    "core": "usta.kit.core", "shapes": "usta.kit.shapes", "parts": "usta.kit.parts", "style": "usta.kit.style",
    "trees": "usta.kit.trees", "terrain": "usta.kit.terrain", "interiors": "usta.kit.interiors", "gen": "usta.kit.gen",
    "audit": "usta.audit", "redstone": "usta.kit.redstone",
}


def _public_api(mod) -> str:
    lines = []
    for name, obj in inspect.getmembers(mod):
        if name.startswith("_") or getattr(obj, "__module__", None) != mod.__name__:
            continue
        if inspect.isfunction(obj) or inspect.isclass(obj):
            try:
                sig = str(inspect.signature(obj))
            except (TypeError, ValueError):
                sig = "(...)"
            doc = (inspect.getdoc(obj) or "").split("\n", 1)[0]
            lines.append(f"- {name}{sig}" + (f": {doc}" if doc else ""))
    return "\n".join(lines[:120])


def reference(topic: str = "overview") -> str:
    if topic == "overview":
        out = ["Usta araç seti başlıkları (kit_reference(topic) ile ayrıntı):"]
        for t, m in TOPICS.items():
            try:
                mod = importlib.import_module(m)
                first = (mod.__doc__ or "").strip().split("\n", 1)[0]
                out.append(f"- {t}: {first}")
            except Exception:
                out.append(f"- {t}: (henüz yok)")
        return "\n".join(out)
    m = TOPICS.get(topic)
    if not m:
        return f"bilinmeyen başlık: {topic}; olanlar: overview, " + ", ".join(TOPICS)
    try:
        mod = importlib.import_module(m)
    except Exception as e:
        return f"{topic}: yüklenemedi ({e})"
    parts = [(mod.__doc__ or "").strip(), "", "API:", _public_api(mod)]
    for cat in ("CATALOG", "GENERATORS", "ROOM_KINDS", "STYLES", "SPECIES", "CHECKS", "MECHANISMS"):
        if hasattr(mod, cat):
            v = getattr(mod, cat)
            if isinstance(v, dict):
                parts.append(f"\n{cat}:")
                parts += [f"- {k}: {d if isinstance(d, str) else getattr(d, 'description', '')}" for k, d in list(v.items())[:150]]
    s = "\n".join(parts)
    return s[:20000]
