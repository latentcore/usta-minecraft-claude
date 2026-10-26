"""gen: parametrik ureteçler — sik istenen yapilar icin hizli ve kaliteli baslangic (U4b).
Kullanim (MCP): generate(name, params) ya da betikte: b = gen.build("modern_villa", {"size": "devasa"}, ctx).
Her ureteç yerel cercevede uretir: on cephe z=0'da (-z'ye bakar), y=0 zemin; araziye kendisi oturur (ctx['terrain']).
Ortak parametreler: size (küçük|orta|büyük|devasa ya da sayi), style (modern|ottoman|medieval|futuristic|japanese|
scandinavian|mediterranean|rustic|classical), seed, name. Ureteç sonrasi betikte ozellestirme serbest (b.fill, parts...).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..core import Build


@dataclass
class GenSpec:
    fn: Callable[[dict, dict], Build]
    footprint_fn: Callable[[dict], tuple[int, int]]
    description: str
    params: dict = field(default_factory=dict)
    label_fn: Callable[[dict], str] | None = None

    def footprint(self, params: dict) -> tuple[int, int]:
        return self.footprint_fn(params)

    def label(self, params: dict) -> str:
        if self.label_fn:
            return self.label_fn(params)
        return params.get("name") or self.description.split(":")[0]


GENERATORS: dict[str, GenSpec] = {}


def register(name: str, fn, footprint, description: str, params: dict | None = None, label=None) -> None:
    GENERATORS[name] = GenSpec(fn, footprint, description, params or {}, label)


def build(name: str, params: dict | None = None, ctx: dict | None = None) -> Build:
    spec = GENERATORS.get(name)
    if spec is None:
        raise KeyError(f"bilinmeyen üreteç: {name}; olanlar: {', '.join(sorted(GENERATORS))}")
    b = spec.fn(dict(params or {}), dict(ctx or {}))
    b.name = spec.label(params or {})
    from .common import seal_water
    from .. import parts as _parts
    _parts.heal_stairs(b)                      # merdiven ustu bas boslugu (sonradan konan doseme/tavan kalkar)
    _parts.heal_doors(b)                       # ince engelle kapanmis kapi onu/arkasi (gecit acilir)
    _parts.heal_attachables(b)                 # destegi sonradan kalkan mesale/tabela/hali (oyun dusururdu)
    n = seal_water(b, ctx)                     # su altinda disariya acik hava -> dunyadaki su kalir (kuru cukur yok)
    if n:
        b.meta.setdefault("notes", []).append(f"su korundu: {n} hücre")
    return b


def _load() -> None:
    from . import houses  # noqa: F401
    from .houses import house, house_dims, modern_villa, villa_dims
    register("house", house, house_dims, "Ev: her tarzda (rustik, İskandinav, Ege, ortaçağ…) 1-3 katlı, döşeli, bahçeli ev",
             {"size": "küçük|orta|büyük|devasa", "style": "rustic", "floors": "1-3", "roof": "gable|hip|mansard|flat|shed|curved"},
             lambda p: p.get("name") or "ev")
    register("modern_villa", modern_villa, villa_dims, "Modern villa: kademeli beyaz kütleler, konsol kat, cam cepheler, havuz, teras, döşeli odalar",
             {"size": "orta|büyük|devasa", "floors": "1-3", "pool": True}, lambda p: p.get("name") or "modern villa")
    for mod in ("ottoman", "monuments", "rural", "urban", "special"):
        try:
            __import__(f"{__name__}.{mod}")
        except ImportError:
            pass


_load()

GENERATORS_DOC = "\n".join(f"- {k}: {v.description} | parametreler: {v.params}" for k, v in GENERATORS.items())
__doc__ = (__doc__ or "") + "\nÜreteçler:\n" + GENERATORS_DOC
