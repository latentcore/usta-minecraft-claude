"""style: Style = rol -> agirlikli blok paleti (doku karisimi) + oranlar + motifler; hazir stil paketleri; biyom uyarlamasi.

Kullanim:  from usta.kit import style
    st = style.get("ottoman").adapt("minecraft:snowy_taiga")       # paket + biyom
    st.pick("wall", x, y, z)          -> deterministik agirlikli varyant ("stone_bricks" / "andesite" / ...)
    st.fill(b, x0,y0,z0,x1,y1,z1, "wall")      dokulu kutu (vektorlu, yamali karisim)
    st.put(b, shape, "roof")                     Shape/mask'i dokulu yaz
    st.stairs("roof", "south", "top") st.slab("trim","top") st.wall_of("foundation") st.fence() st.door() st.trapdoor() st.pane()
    st.put_form(b, shape, "roof", "stairs", facing="north")   turev bloklarda da doku karisimi (cati kiremitleri)
    st.block("trim")  birincil blok;  st.variants(role) -> [(durum, agirlik)];  st.with_(floor_h=5)  st.override(roof=[("bricks",1)])
Stiller (STYLES): modern, ottoman, medieval, futuristic, japanese, scandinavian, mediterranean, rustic, classical.
Roller (ROLES): foundation wall wall2 accent trim frame pillar beam roof roof_trim floor floor_alt ceiling glass glass_block
  door shutter fence railing light light_block path paving hedge plants soil water_edge tile metal detail dome carpet
Oranlar: floor_h (kat yuksekligi, doseme dahil), wall_t, bay (pencere ritmi), win_w, win_h, sill, roof_kind (gable|hip|
  flat|mansard|shed|curved), pitch (0.5|1|2), overhang, plinth, corner (quoins|pillar|log|pilaster|None), window_kind,
  door_kind, arch_kind (round|pointed|segmental|ogee|flat), motifs (frozenset; st.has('cumba')).
Biyom: st.adapt(biome) -> col (desert/badlands: kumtasi), karli/tayga (ladin, dik cati), orman/jungle/savan/bataklik/kiraz/
  soluk bahce (yerel agac), nether (kara tas, crimson/warped), end, deep_dark (derin kayrak). Bilinmeyen biyom: anahtar kelime.
Turev cozumleme (derive(name, kind)): stairs slab wall fence fence_gate door trapdoor pane carpet button pressure_plate;
  dogrudan yoksa aile kurali, o da yoksa harita rengine en yakin blok (her zaman gecerli bir 26.3 blogu).
"""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Iterable, Sequence

import numpy as np

from .. import blockdb
from . import shapes as S

__all__ = ["Style", "ROLES", "STYLES", "get", "names", "derive", "BIOMES", "biome_rule", "wood_of"]

ROLES: dict[str, str] = {
    "foundation": "temel / kaide taşı (plinth, alt kuşak)",
    "wall": "ana duvar dolgusu",
    "wall2": "ikincil duvar (üst kat sıvası, kaplama)",
    "accent": "vurgu bandı / kuşak / almaşık",
    "trim": "korniş, söve, denizlik, saçak alnı",
    "frame": "pencere/kapı kasası",
    "pillar": "sütun / pilastr / köşe dikmesi",
    "beam": "kiriş / ahşap karkas (kütük)",
    "roof": "çatı kaplaması (merdiven/basamak türevli)",
    "roof_trim": "mahya, saçak kenarı",
    "floor": "döşeme",
    "floor_alt": "desen ikinci rengi",
    "ceiling": "tavan",
    "glass": "pencere camı (panel)",
    "glass_block": "tam cam blok (cam duvar)",
    "door": "kapı",
    "shutter": "kepenk / panjur (tuzak kapı)",
    "fence": "ahşap çit / direk",
    "railing": "korkuluk (çit/duvar/cam panel/parmaklık)",
    "light": "fener (asılabilir)",
    "light_block": "gömme ışık bloğu",
    "path": "yol",
    "paving": "avlu / zemin döşemesi",
    "hedge": "çit bitkisi (yaprak)",
    "plants": "çiçek / bitki",
    "soil": "bitki toprağı",
    "water_edge": "havuz / kurna kenarı",
    "tile": "çini / karo vurgu",
    "metal": "metal (parmaklık, zincir)",
    "detail": "oyma / kilit taşı",
    "dome": "kubbe kaplaması",
    "carpet": "halı",
}

WOODS = ("pale_oak", "dark_oak", "oak", "spruce", "birch", "jungle", "acacia", "mangrove", "cherry", "bamboo",
         "crimson", "warped", "poplar")
_WOODS_BY_LEN = tuple(sorted(WOODS, key=len, reverse=True))
_COLORS = ("white", "light_gray", "gray", "black", "brown", "red", "orange", "yellow", "lime", "green", "cyan",
           "light_blue", "blue", "purple", "magenta", "pink")
_COLORS_BY_LEN = tuple(sorted(_COLORS, key=len, reverse=True))


def _db() -> blockdb.BlockDB:
    return blockdb.get()


def _short(name: str) -> str:
    n = name.lstrip("!").split("[", 1)[0]
    return n.split(":", 1)[1] if ":" in n else n


def _exists(n: str) -> bool:
    return _db().has_block(n)


def wood_of(name: str) -> str | None:
    """'stripped_spruce_log' -> 'spruce'."""
    n = _short(name)
    if n.startswith("stripped_"):
        n = n[len("stripped_"):]
    for w in _WOODS_BY_LEN:
        if n == w or n.startswith(w + "_"):
            return w
    return None


def _color_of(name: str) -> str | None:
    n = _short(name)
    for c in _COLORS_BY_LEN:
        if n.startswith(c + "_"):
            return c
    return None


# ---------------------------------------------------------------------- turev bloklar
_FORM_OVERRIDE: dict[str, dict[str, str]] = {
    "calcite": {"stairs": "polished_diorite_stairs", "slab": "polished_diorite_slab", "wall": "diorite_wall"},
    "white_terracotta": {"stairs": "smooth_sandstone_stairs", "slab": "smooth_sandstone_slab", "wall": "sandstone_wall"},
    "terracotta": {"stairs": "smooth_red_sandstone_stairs", "slab": "smooth_red_sandstone_slab", "wall": "red_sandstone_wall"},
    "smooth_stone": {"stairs": "stone_stairs", "wall": "stone_brick_wall"},
    "stone": {"wall": "stone_brick_wall"},
    "smooth_quartz": {"wall": "diorite_wall"},
    "quartz_block": {"wall": "diorite_wall"},
    "quartz_bricks": {"stairs": "quartz_stairs", "slab": "quartz_slab", "wall": "diorite_wall"},
    "quartz_pillar": {"stairs": "quartz_stairs", "slab": "quartz_slab", "wall": "diorite_wall"},
    "chiseled_quartz_block": {"stairs": "quartz_stairs", "slab": "quartz_slab", "wall": "diorite_wall"},
    "cut_sandstone": {"stairs": "sandstone_stairs"},
    "cut_red_sandstone": {"stairs": "red_sandstone_stairs"},
    "packed_mud": {"stairs": "mud_brick_stairs", "slab": "mud_brick_slab", "wall": "mud_brick_wall"},
    "mud": {"stairs": "mud_brick_stairs", "slab": "mud_brick_slab", "wall": "mud_brick_wall"},
    "hay_block": {"stairs": "bamboo_mosaic_stairs", "slab": "bamboo_mosaic_slab"},
    "bamboo_mosaic": {"fence": "bamboo_fence", "door": "bamboo_door", "trapdoor": "bamboo_trapdoor"},
    "deepslate": {"stairs": "cobbled_deepslate_stairs", "slab": "cobbled_deepslate_slab", "wall": "cobbled_deepslate_wall"},
    "chiseled_deepslate": {"stairs": "deepslate_tile_stairs", "slab": "deepslate_tile_slab", "wall": "deepslate_tile_wall"},
    "cracked_deepslate_tiles": {"stairs": "deepslate_tile_stairs", "slab": "deepslate_tile_slab", "wall": "deepslate_tile_wall"},
    "cracked_deepslate_bricks": {"stairs": "deepslate_brick_stairs", "slab": "deepslate_brick_slab", "wall": "deepslate_brick_wall"},
    "chiseled_polished_blackstone": {"stairs": "polished_blackstone_stairs", "slab": "polished_blackstone_slab", "wall": "polished_blackstone_wall"},
    "cracked_polished_blackstone_bricks": {"stairs": "polished_blackstone_brick_stairs", "slab": "polished_blackstone_brick_slab", "wall": "polished_blackstone_brick_wall"},
    "gilded_blackstone": {"stairs": "blackstone_stairs", "slab": "blackstone_slab", "wall": "blackstone_wall"},
    "basalt": {"stairs": "polished_blackstone_stairs", "slab": "polished_blackstone_slab", "wall": "blackstone_wall"},
    "polished_basalt": {"stairs": "polished_blackstone_stairs", "slab": "polished_blackstone_slab", "wall": "polished_blackstone_wall"},
    "smooth_basalt": {"stairs": "polished_blackstone_stairs", "slab": "polished_blackstone_slab", "wall": "polished_blackstone_wall"},
    "end_stone": {"stairs": "end_stone_brick_stairs", "slab": "end_stone_brick_slab", "wall": "end_stone_brick_wall"},
    "purpur_pillar": {"stairs": "purpur_stairs", "slab": "purpur_slab"},
    "cracked_nether_bricks": {"stairs": "nether_brick_stairs", "slab": "nether_brick_slab", "wall": "nether_brick_wall", "fence": "nether_brick_fence"},
    "chiseled_nether_bricks": {"stairs": "nether_brick_stairs", "slab": "nether_brick_slab", "wall": "nether_brick_wall", "fence": "nether_brick_fence"},
    "nether_bricks": {"fence": "nether_brick_fence"},
    "dripstone_block": {"stairs": "granite_stairs", "slab": "granite_slab", "wall": "granite_wall"},
    "copper_block": {"stairs": "cut_copper_stairs", "slab": "cut_copper_slab"},
    "waxed_copper_block": {"stairs": "waxed_cut_copper_stairs", "slab": "waxed_cut_copper_slab"},
    "iron_block": {"stairs": "polished_andesite_stairs", "slab": "smooth_stone_slab"},
    "snow_block": {"stairs": "smooth_quartz_stairs", "slab": "smooth_quartz_slab", "wall": "diorite_wall"},
    "glass": {"pane": "glass_pane"},
    "tinted_glass": {"pane": "gray_stained_glass_pane"},
    "moss_block": {"carpet": "moss_carpet"},
    "pale_moss_block": {"carpet": "pale_moss_carpet"},
    "bookshelf": {"stairs": "oak_stairs", "slab": "oak_slab"},
    "mushroom_stem": {"stairs": "birch_stairs", "slab": "birch_slab"},
}
_KINDS = ("stairs", "slab", "wall", "fence", "fence_gate", "door", "trapdoor", "pane", "carpet", "button",
          "pressure_plate")


def _wood_form(w: str, kind: str) -> str | None:
    if kind == "pane" or kind == "carpet" or kind == "wall":
        return None
    n = f"{w}_{kind}"
    return n if _exists(n) else None


def _try(cands: Iterable[str]) -> str | None:
    for c in cands:
        if c and _exists(c):
            return c
    return None


def _family_candidates(n: str, kind: str) -> list[str]:
    c = [f"{n}_{kind}"]
    if n.endswith("s"):
        c.append(f"{n[:-1]}_{kind}")
    if n.endswith("_block"):
        c.append(f"{n[:-6]}_{kind}")
    if n.endswith("_pillar"):
        c.append(f"{n[:-7]}_{kind}")
    return c


@lru_cache(maxsize=4096)
def derive(name: str, kind: str) -> str:
    """Tam blok adindan turev blok adi (minecraft: oneksiz). Her zaman gecerli bir blok doner."""
    if kind not in _KINDS:
        raise ValueError(f"bilinmeyen tur: {kind} (gecerli: {', '.join(_KINDS)})")
    n = _short(name)
    if n.endswith("_" + kind) and _exists(n):
        return n
    ov = _FORM_OVERRIDE.get(n, {}).get(kind)
    if ov and _exists(ov):
        return ov
    # zaten turev ise (ornegin 'cobblestone_wall' -> slab): taban adina geri don
    base = _base_of(n)
    if base != n:
        return derive(base, kind)
    w = wood_of(n)
    if w and kind in ("stairs", "slab", "fence", "fence_gate", "door", "trapdoor", "button", "pressure_plate"):
        r = _wood_form(w, kind)
        if r:
            return r
    col = _color_of(n)
    if kind == "pane":
        r = _try([f"{n}_pane", f"{col}_stained_glass_pane" if col and "glass" in n else None])
        if r:
            return r
    if kind == "carpet" and col:
        r = _try([f"{col}_carpet"])
        if r:
            return r
    r = _try(_family_candidates(n, kind))
    if r:
        return r
    stripped = n
    for pre in ("chiseled_", "cracked_", "polished_", "smooth_", "cut_", "infested_", "mossy_", "waxed_"):
        if stripped.startswith(pre):
            stripped = stripped[len(pre):]
            r = _try(_family_candidates(stripped, kind))
            if r:
                return r
    if col and kind in ("stairs", "slab"):
        r = _try([f"{col}_concrete_{kind}", f"{col}_wool_{kind}"])
        if r:
            return r
    return _nearest_form(n, kind)


def _base_of(n: str) -> str:
    """Turev blok adindan tam blok adi tahmini ('stone_brick_stairs' -> 'stone_bricks')."""
    for kind in sorted(_KINDS, key=len, reverse=True):
        suf = "_" + kind
        if n.endswith(suf) and n != suf[1:]:
            stem = n[: -len(suf)]
            w = wood_of(stem)
            if w and stem == w:
                return f"{w}_planks" if _exists(f"{w}_planks") else stem
            if kind == "pane" and stem.endswith("glass"):
                return stem
            if kind == "carpet":
                c = _color_of(n)
                if c:
                    return f"{c}_wool"
                if stem == "moss":
                    return "moss_block"
                if stem == "pale_moss":
                    return "pale_moss_block"
            for cand in (stem, stem + "s", stem + "_block", stem + "_planks"):
                if _exists(cand) and _db().is_full(cand):
                    return cand
            return stem if _exists(stem) else n
    return n


@lru_cache(maxsize=64)
def _forms_of_kind(kind: str) -> tuple[tuple[str, tuple[int, int, int]], ...]:
    db = _db()
    out = []
    for full in db.blocks:
        s = full.split(":", 1)[1]
        if not s.endswith("_" + kind):
            continue
        if kind == "wall" and ("sign" in s or "banner" in s or "torch" in s or "fan" in s or "head" in s or "skull" in s):
            continue
        if kind == "door" and s == "iron_door":
            continue
        if kind == "trapdoor" and s == "iron_trapdoor":
            continue
        if s.startswith("waxed_") or "infested" in s or "petrified" in s:
            continue
        base = _base_of(s)
        try:
            rgb = db.map_rgb(base if _exists(base) else s)
        except Exception:
            rgb = db.map_rgb(s)
        out.append((s, rgb))
    return tuple(out)


def _nearest_form(n: str, kind: str) -> str:
    db = _db()
    try:
        rgb = np.array(db.map_rgb(n), dtype=np.float64)
    except Exception:
        rgb = np.array([128, 128, 128], dtype=np.float64)
    toks = set(n.split("_"))
    best, bestd = None, 1e18
    for s, c in _forms_of_kind(kind):
        d = float(((np.array(c, dtype=np.float64) - rgb) ** 2).sum())
        d -= 40.0 * len(toks & set(s.split("_")))
        if d < bestd:
            best, bestd = s, d
    if best is None:
        raise blockdb.UnknownBlock(f"'{kind}' turunde hic blok yok")
    return best


# ---------------------------------------------------------------------- doku karisimi
@lru_cache(maxsize=16)
def _mix_cdf(mix_key: int) -> tuple[np.ndarray, np.ndarray]:
    """(1-m)*U + m*N dagiliminin deneysel CDF tablosu (yamali ama agirliklari koruyan secim icin)."""
    m = mix_key / 100.0
    n = 24000
    i = np.arange(n, dtype=np.float64)
    x = (i * 0.618034 * 37.0) % 997.0
    y = (i * 0.414214 * 11.0) % 211.0
    z = (i * 0.732051 * 23.0) % 503.0
    u = S.hash01(np.floor(x), np.floor(y), np.floor(z), 99173)
    v = S.noise(x, y, z, scale=2.7, seed=4242)
    t = np.sort((1 - m) * u + m * v)
    q = np.linspace(0, 1, 513)
    return np.quantile(t, q), q


def _uniform_mix(X, Y, Z, seed: int, mix: float, grain: float) -> np.ndarray:
    u = S.hash01(X, Y, Z, seed)
    if mix <= 0.01:
        return u
    v = S.noise(X, Y, Z, scale=grain, seed=seed + 7)
    t = (1 - mix) * u + mix * v
    xp, fp = _mix_cdf(int(round(mix * 100)))
    return np.interp(t, xp, fp)


def _role_seed(role: str) -> int:
    return zlib.crc32(role.encode("utf-8")) & 0x7FFFFFFF


def _normalize_state(s: str) -> str:
    """Rol girdisini gecerli kanonik duruma cevirir; yapraklar kalici (persistent=true)."""
    db = _db()
    ex = s.startswith("!")
    body = s[1:] if ex else s
    c = db.canonical(body)
    name, props = blockdb.split_state(body)
    if "persistent" in db.blocks[name]["props"]:
        c = db.with_props(c, persistent="true")  # yapilarda yapraklar asla curumesin
    return ("!" + c) if ex else c


# ---------------------------------------------------------------------- Style
Palette = dict[str, tuple[tuple[str, float], ...]]


@dataclass
class Style:
    name: str
    palette: dict
    desc: str = ""
    floor_h: int = 4
    wall_t: int = 1
    bay: int = 3
    win_w: int = 1
    win_h: int = 2
    sill: int = 1
    roof_kind: str = "gable"
    pitch: float = 1.0
    overhang: int = 1
    plinth: int = 1
    corner: str | None = "quoins"
    window_kind: str = "framed"
    door_kind: str = "framed"
    arch_kind: str = "round"
    motifs: frozenset = frozenset()
    mix: float = 0.55
    grain: float = 2.6
    seed: int = 0
    biome: str | None = None
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    # -------------------------------------------------------------- palet
    def variants(self, role: str) -> list[tuple[str, float]]:
        """[(kanonik durum, normal agirlik)] -- rol yoksa temel paletten."""
        k = ("v", role)
        if k in self._cache:
            return self._cache[k]
        ent = self.palette.get(role) or _BASE_PALETTE.get(role)
        if not ent:
            raise KeyError(f"bilinmeyen rol: {role} (roller: {', '.join(ROLES)})")
        out: list[tuple[str, float]] = []
        for s, w in ent:
            out.append((_normalize_state(s), float(w)))
        tot = sum(w for _, w in out) or 1.0
        out = [(s, w / tot) for s, w in out]
        self._cache[k] = out
        return out

    def block(self, role: str, i: int = 0) -> str:
        """Rolun birincil (ya da i.) blogu."""
        v = self.variants(role)
        return v[min(i, len(v) - 1)][0]

    def base(self, role: str, i: int = 0) -> str:
        """Ozelliksiz kisa ad (turev cozumleme icin)."""
        return _short(self.block(role, i))

    def has(self, motif: str) -> bool:
        return motif in self.motifs

    def _index(self, role: str, X, Y, Z) -> np.ndarray:
        vs = self.variants(role)
        if len(vs) == 1:
            return np.zeros(np.broadcast(X, Y, Z).shape, dtype=np.int64)
        cum = np.cumsum([w for _, w in vs])
        cum[-1] = 1.0 + 1e-9
        t = _uniform_mix(X, Y, Z, self.seed + _role_seed(role), self.mix, self.grain)
        return np.minimum(np.searchsorted(cum, t, side="right"), len(vs) - 1)

    def pick(self, role: str, x: int, y: int, z: int) -> str:
        """(x,y,z) icin deterministik agirlikli varyant (ayni nokta hep ayni blok)."""
        i = int(self._index(role, np.array([x]), np.array([y]), np.array([z]))[0])
        return self.variants(role)[i][0]

    def pick_form(self, role: str, kind: str, x: int, y: int, z: int, **props) -> str:
        i = int(self._index(role, np.array([x]), np.array([y]), np.array([z]))[0])
        return self.form(role, kind, i=i, **props)

    # -------------------------------------------------------------- turevler
    def form(self, role: str, kind: str, i: int = 0, **props) -> str:
        """Rol blogunun turevi: kind in stairs/slab/wall/fence/fence_gate/door/trapdoor/pane/carpet/button/pressure_plate."""
        key = ("f", role, kind, i, tuple(sorted(props.items())))
        r = self._cache.get(key)
        if r is not None:
            return r
        base = self.base(role, i)
        name = base if (base.endswith("_" + kind) and _exists(base)) else derive(base, kind)
        db = _db()
        allowed = db.blocks["minecraft:" + name]["props"]
        pp = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in props.items() if k in allowed}
        s = "minecraft:" + name + ("[" + ",".join(f"{k}={v}" for k, v in pp.items()) + "]" if pp else "")
        r = db.canonical(s)
        self._cache[key] = r
        return r

    def stairs(self, role: str = "trim", facing: str = "north", half: str = "bottom", i: int = 0) -> str:
        return self.form(role, "stairs", i=i, facing=facing, half=half)

    def slab(self, role: str = "trim", type: str = "bottom", i: int = 0) -> str:
        return self.form(role, "slab", i=i, type=type)

    def wall_of(self, role: str = "foundation", i: int = 0) -> str:
        return self.form(role, "wall", i=i)

    def fence(self, role: str = "fence") -> str:
        return self.form(role, "fence")

    def gate(self, role: str = "fence", facing: str = "north", open: bool = False) -> str:
        return self.form(role, "fence_gate", facing=facing, open=open)

    def door(self, facing: str = "south", half: str = "lower", hinge: str = "left", role: str = "door") -> str:
        return self.form(role, "door", facing=facing, half=half, hinge=hinge)

    def trapdoor(self, facing: str = "north", half: str = "bottom", open: bool = False, role: str = "shutter") -> str:
        return self.form(role, "trapdoor", facing=facing, half=half, open=open)

    def pane(self, role: str = "glass") -> str:
        b = self.base(role)
        if b.endswith("_pane") or b == "iron_bars" or b.endswith("_bars"):
            return self.block(role)
        return self.form(role, "pane")

    def carpet(self, role: str = "carpet") -> str:
        b = self.base(role)
        return self.block(role) if b.endswith("_carpet") else self.form(role, "carpet")

    def light(self, hanging: bool = False) -> str:
        b = self.block("light")
        db = _db()
        if "hanging" in db.props(b):
            return db.with_props(b, hanging="true" if hanging else "false")
        return b

    # -------------------------------------------------------------- yazma (vektorlu)
    def fill(self, b, x0, y0, z0, x1, y1, z1, role: str, only_empty: bool = False, replace: str | Iterable[str] | None = None) -> None:
        """Dokulu kutu doldurma (uclar dahil)."""
        x0, x1 = sorted((int(x0), int(x1)))
        y0, y1 = sorted((int(y0), int(y1)))
        z0, z1 = sorted((int(z0), int(z1)))
        vs = self.variants(role)
        if len(vs) == 1 and replace is None:
            b.fill(x0, y0, z0, x1, y1, z1, vs[0][0], only_empty=only_empty)
            return
        sh = S.box(x0, y0, z0, x1, y1, z1)
        if replace is not None:
            rep = [replace] if isinstance(replace, str) else list(replace)
            ids = b.ids_box(x0, y0, z0, x1, y1, z1)
            rid = np.array([b.pid(r) for r in rep], dtype=np.int32)
            sh = S.Shape(np.isin(ids, rid), (x0, y0, z0))
        self.put(b, sh, role, only_empty=only_empty)

    def _split(self, shape, role: str):
        if isinstance(shape, np.ndarray):
            raise TypeError("Shape bekleniyor (S.Shape(mask, origin))")
        X, Y, Z = shape.grid()
        idx = self._index(role, X, Y, Z)
        idx = np.broadcast_to(idx, shape.mask.shape)
        return idx

    def put(self, b, shape, role: str, only_empty: bool = False) -> None:
        """Shape'i rol varyantlariyla dokulu yazar."""
        if shape.empty():
            return
        vs = self.variants(role)
        x0, y0, z0 = shape.origin
        if len(vs) == 1:
            b.put_mask(x0, y0, z0, shape.mask, vs[0][0], only_empty=only_empty)
            return
        idx = self._split(shape, role)
        for i, (s, _) in enumerate(vs):
            m = shape.mask & (idx == i)
            if m.any():
                b.put_mask(x0, y0, z0, m, s, only_empty=only_empty)

    def put_form(self, b, shape, role: str, kind: str, only_empty: bool = False, **props) -> None:
        """Turev blogu (merdiven/basamak...) varyant karisimiyla yazar: her varyantin kendi turevi."""
        if shape.empty():
            return
        vs = self.variants(role)
        x0, y0, z0 = shape.origin
        if len(vs) == 1:
            b.put_mask(x0, y0, z0, shape.mask, self.form(role, kind, 0, **props), only_empty=only_empty)
            return
        idx = self._split(shape, role)
        for i in range(len(vs)):
            m = shape.mask & (idx == i)
            if m.any():
                b.put_mask(x0, y0, z0, m, self.form(role, kind, i, **props), only_empty=only_empty)

    def set(self, b, x: int, y: int, z: int, role: str) -> None:
        b.set(x, y, z, self.pick(role, x, y, z))

    # -------------------------------------------------------------- turetme
    def with_(self, **kw) -> "Style":
        """Oran/motif degistirilmis kopya: st.with_(floor_h=5, roof='hip')."""
        if "motifs" in kw and not isinstance(kw["motifs"], frozenset):
            kw["motifs"] = frozenset(kw["motifs"])
        return replace(self, _cache={}, **kw)

    def override(self, **roles) -> "Style":
        """Rol paletlerini degistirir: st.override(roof=[("bricks", .7), ("granite", .3)], glass="glass_pane")."""
        pal = dict(self.palette)
        for r, v in roles.items():
            if r not in ROLES:
                raise KeyError(f"bilinmeyen rol: {r}")
            if isinstance(v, str):
                v = [(v, 1.0)]
            pal[r] = tuple((s, float(w)) for s, w in v)
        return replace(self, palette=pal, _cache={})

    def adapt(self, biome: str | None) -> "Style":
        """Biyoma uyarlanmis kopya (malzeme ailesi, yerel agac, bitkiler, cati egimi)."""
        if not biome:
            return self
        rule = biome_rule(biome)
        bid = _short(biome)
        if not rule:
            return replace(self, biome=bid, _cache={})
        pal: dict = {}
        wmap = rule.get("wood", {})
        smap = STONE_SETS.get(rule.get("stone", ""), {})
        moss = float(rule.get("moss", 0.0))
        for role in ROLES:
            ent = self.palette.get(role) or _BASE_PALETTE[role]
            acc: dict[str, float] = {}
            for s, w in ent:
                n2 = _swap(s, wmap, smap)
                acc[n2] = acc.get(n2, 0.0) + float(w)
                if moss > 0 and role in ("foundation", "wall", "paving", "path", "water_edge"):
                    mv = _MOSSY.get(_short(n2))
                    if mv:
                        acc[mv] = acc.get(mv, 0.0) + float(w) * moss
            pal[role] = tuple(acc.items())
        for role in ("plants", "hedge", "soil", "path", "light"):
            if role in rule:
                v = rule[role]
                pal[role] = tuple(((v, 1.0),) if isinstance(v, str) else tuple((a, float(b_)) for a, b_ in v))
        kw = {}
        if rule.get("pitch_min") and self.roof_kind not in ("flat", "dome"):
            kw["pitch"] = max(self.pitch, float(rule["pitch_min"]))
        return replace(self, palette=pal, name=f"{self.name}@{bid}", biome=bid, _cache={}, **kw)

    def describe(self) -> str:
        """Kisa ozet (calisma anindaki Claude icin)."""
        parts = [f"{self.name}: {self.desc}",
                 f"kat={self.floor_h} duvar={self.wall_t} ritim={self.bay} pencere={self.win_w}x{self.win_h} "
                 f"cati={self.roof_kind}/{self.pitch} sacak={self.overhang} kose={self.corner}",
                 "motifler: " + ", ".join(sorted(self.motifs))]
        for r in ("foundation", "wall", "wall2", "trim", "roof", "glass", "door"):
            parts.append(f"  {r}: " + ", ".join(f"{_short(s)}({w:.0%})" for s, w in self.variants(r)))
        return "\n".join(parts)


def _swap(s: str, wmap: dict, smap: dict) -> str:
    """Bir palet girdisinde agac/tas ailesini degistirir (gecerli degilse oldugu gibi birakir)."""
    ex = s.startswith("!")
    body = s[1:] if ex else s
    name = body.split("[", 1)[0]
    props = body[len(name):]
    short = name.split(":", 1)[-1]
    new = short
    if smap:
        if short in smap:
            new = smap[short]
        else:
            base = _base_of(short)
            if base != short and base in smap:
                kind = None
                for k in _KINDS:
                    if short.endswith("_" + k):
                        kind = k
                        break
                if kind:
                    new = derive(smap[base], kind)
    w = wood_of(new)
    if w and wmap:
        tgt = wmap.get(w) or wmap.get("*")
        if tgt and tgt != w:
            cand = _replace_wood(new, w, tgt)
            if cand and _exists(cand):
                new = cand
    if new == short:
        return s
    try:
        out = _db().canonical(new + props) if props else _db().canonical(new)
    except blockdb.UnknownBlock:
        out = _db().canonical(new)
    return ("!" + out) if ex else out


def _replace_wood(n: str, w: str, tgt: str) -> str | None:
    pre = ""
    body = n
    if body.startswith("stripped_"):
        pre, body = "stripped_", body[len("stripped_"):]
    rest = body[len(w):]  # "_planks"
    nether = {"crimson", "warped"}
    if tgt in nether and rest in ("_log", "_wood"):
        rest = "_stem" if rest == "_log" else "_hyphae"
    if w in nether and rest in ("_stem", "_hyphae"):
        rest = "_log" if rest == "_stem" else "_wood"
    if tgt == "bamboo" and rest in ("_log", "_wood"):
        return f"{pre}bamboo_block"
    if tgt == "poplar" and rest == "_leaves":
        return "yellow_poplar_leaves"
    return f"{pre}{tgt}{rest}"


_MOSSY = {"stone_bricks": "mossy_stone_bricks", "cobblestone": "mossy_cobblestone"}

STONE_SETS: dict[str, dict[str, str]] = {
    "sandstone": {"stone_bricks": "cut_sandstone", "mossy_stone_bricks": "sandstone", "cracked_stone_bricks": "sandstone",
                  "chiseled_stone_bricks": "chiseled_sandstone", "cobblestone": "sandstone", "mossy_cobblestone": "sandstone",
                  "stone": "sandstone", "smooth_stone": "smooth_sandstone", "andesite": "sandstone",
                  "polished_andesite": "smooth_sandstone", "tuff": "sandstone", "tuff_bricks": "cut_sandstone",
                  "polished_tuff": "smooth_sandstone", "coarse_dirt": "coarse_dirt"},
    "red_sandstone": {"stone_bricks": "cut_red_sandstone", "mossy_stone_bricks": "red_sandstone",
                      "cracked_stone_bricks": "red_sandstone", "chiseled_stone_bricks": "chiseled_red_sandstone",
                      "cobblestone": "red_sandstone", "mossy_cobblestone": "red_sandstone", "stone": "red_sandstone",
                      "smooth_stone": "smooth_red_sandstone", "andesite": "red_sandstone",
                      "polished_andesite": "smooth_red_sandstone", "tuff": "red_sandstone",
                      "tuff_bricks": "cut_red_sandstone", "polished_tuff": "smooth_red_sandstone"},
    "blackstone": {"stone_bricks": "polished_blackstone_bricks", "mossy_stone_bricks": "cracked_polished_blackstone_bricks",
                   "cracked_stone_bricks": "cracked_polished_blackstone_bricks",
                   "chiseled_stone_bricks": "chiseled_polished_blackstone", "cobblestone": "blackstone",
                   "mossy_cobblestone": "blackstone", "stone": "blackstone", "smooth_stone": "polished_blackstone",
                   "andesite": "blackstone", "polished_andesite": "polished_blackstone", "tuff": "blackstone",
                   "tuff_bricks": "polished_blackstone_bricks", "polished_tuff": "polished_blackstone",
                   "dirt_path": "soul_soil", "coarse_dirt": "soul_soil"},
    "deepslate": {"stone_bricks": "deepslate_bricks", "mossy_stone_bricks": "cracked_deepslate_bricks",
                  "cracked_stone_bricks": "cracked_deepslate_bricks", "chiseled_stone_bricks": "chiseled_deepslate",
                  "cobblestone": "cobbled_deepslate", "mossy_cobblestone": "cobbled_deepslate", "stone": "deepslate",
                  "smooth_stone": "polished_deepslate", "andesite": "cobbled_deepslate",
                  "polished_andesite": "polished_deepslate", "tuff": "cobbled_deepslate"},
    "end": {"stone_bricks": "end_stone_bricks", "mossy_stone_bricks": "end_stone_bricks",
            "cracked_stone_bricks": "end_stone_bricks", "chiseled_stone_bricks": "purpur_pillar",
            "cobblestone": "end_stone", "mossy_cobblestone": "end_stone", "stone": "end_stone",
            "smooth_stone": "purpur_block", "andesite": "end_stone", "polished_andesite": "purpur_block",
            "dirt_path": "end_stone", "coarse_dirt": "end_stone"},
    "mud": {"cobblestone": "packed_mud", "mossy_cobblestone": "mud_bricks", "stone_bricks": "mud_bricks",
            "andesite": "packed_mud"},
}

# ---------------------------------------------------------------------- biyomlar
BIOMES = (
    "badlands", "bamboo_jungle", "basalt_deltas", "beach", "birch_forest", "cherry_grove", "cold_ocean", "crimson_forest",
    "dark_forest", "deep_cold_ocean", "deep_dark", "deep_frozen_ocean", "deep_lukewarm_ocean", "deep_ocean", "desert",
    "dripstone_caves", "end_barrens", "end_highlands", "end_midlands", "eroded_badlands", "flower_forest", "forest",
    "frozen_ocean", "frozen_peaks", "frozen_river", "grove", "ice_spikes", "jagged_peaks", "jungle", "lukewarm_ocean",
    "lush_caves", "mangrove_swamp", "meadow", "mushroom_fields", "nether_wastes", "ocean", "old_growth_birch_forest",
    "old_growth_pine_taiga", "old_growth_spruce_taiga", "pale_garden", "plains", "river", "savanna", "savanna_plateau",
    "small_end_islands", "snowy_beach", "snowy_plains", "snowy_slopes", "snowy_taiga", "soul_sand_valley",
    "sparse_jungle", "stony_peaks", "stony_shore", "sunflower_plains", "swamp", "taiga", "the_end", "the_void",
    "warm_ocean", "warped_forest", "windswept_forest", "windswept_gravelly_hills", "windswept_hills",
    "windswept_savanna", "wooded_badlands",
)

_SNOW_WOOD = {"oak": "spruce", "birch": "spruce", "jungle": "spruce", "acacia": "spruce", "mangrove": "spruce",
              "cherry": "spruce", "bamboo": "spruce", "poplar": "spruce"}
_NETHER_PLANTS = (("crimson_roots", 0.5), ("crimson_fungus", 0.25), ("warped_roots", 0.25))

# (anahtar kelimeler, kural) -- ilk eslesen kazanir; tam ad eslesmesi oncelikli
_BIOME_RULES: list[tuple[tuple[str, ...], dict]] = [
    (("soul_sand_valley",), dict(stone="blackstone", wood={"*": "warped"}, light="soul_lantern", soil="soul_soil",
                                 hedge=(("warped_wart_block", 1.0),), plants=(("warped_roots", 0.6), ("crimson_roots", 0.4)))),
    (("basalt_deltas",), dict(stone="blackstone", wood={"*": "crimson"}, soil="crimson_nylium", hedge="nether_wart_block",
                              plants=_NETHER_PLANTS)),
    (("warped",), dict(stone="blackstone", wood={"*": "warped"}, soil="warped_nylium", hedge="warped_wart_block",
                       plants=(("warped_roots", 0.7), ("warped_fungus", 0.3)))),
    (("crimson", "nether"), dict(stone="blackstone", wood={"*": "crimson"}, soil="crimson_nylium", hedge="nether_wart_block",
                                 plants=_NETHER_PLANTS)),
    (("end", "the_void"), dict(stone="end", plants=(("short_grass", 1.0),), hedge=(("pale_oak_leaves", 1.0),),
                              light="soul_lantern")),
    (("deep_dark",), dict(stone="deepslate", light="soul_lantern")),
    (("dripstone",), dict(stone="deepslate")),
    (("lush_caves",), dict(moss=0.35, hedge=(("azalea_leaves", 0.6), ("flowering_azalea_leaves", 0.4)),
                           soil=(("moss_block", 1.0),))),
    (("badlands",), dict(stone="red_sandstone", wood={"oak": "dark_oak", "spruce": "dark_oak", "birch": "acacia",
                                                      "pale_oak": "acacia", "cherry": "acacia"},
                         plants=(("dead_bush", 1.0),), soil=(("coarse_dirt", 1.0),), hedge=(("acacia_leaves", 1.0),),
                         path=(("smooth_red_sandstone", 0.5), ("red_sandstone", 0.3), ("cut_red_sandstone", 0.2)))),
    (("desert",), dict(stone="sandstone", wood={"oak": "jungle", "spruce": "jungle", "pale_oak": "birch",
                                                "mangrove": "jungle", "cherry": "jungle"},
                       plants=(("dead_bush", 0.6), ("short_dry_grass", 0.4)), soil=(("coarse_dirt", 0.5), ("rooted_dirt", 0.5)),
                       hedge=(("jungle_leaves", 0.5), ("acacia_leaves", 0.5)),
                       path=(("smooth_sandstone", 0.5), ("sandstone", 0.3), ("cut_sandstone", 0.2)))),
    (("snowy", "frozen", "ice_spikes", "grove", "jagged_peaks"), dict(wood=_SNOW_WOOD, pitch_min=1.0,
                                                                      hedge=(("spruce_leaves", 1.0),),
                                                                      plants=(("fern", 0.5), ("short_grass", 0.5)))),
    (("taiga",), dict(wood=_SNOW_WOOD, pitch_min=1.0, hedge=(("spruce_leaves", 1.0),),
                      plants=(("fern", 0.4), ("short_grass", 0.3), ("sweet_berry_bush", 0.3)))),
    (("mangrove",), dict(wood={"oak": "mangrove", "birch": "mangrove", "spruce": "mangrove", "pale_oak": "mangrove"},
                         moss=0.3, stone="mud", hedge=(("mangrove_leaves", 1.0),),
                         plants=(("blue_orchid", 0.5), ("fern", 0.5)))),
    (("swamp",), dict(wood={"oak": "dark_oak", "birch": "dark_oak"}, moss=0.35, hedge=(("oak_leaves", 1.0),),
                      plants=(("blue_orchid", 0.6), ("fern", 0.4)))),
    (("jungle",), dict(wood={"oak": "jungle", "birch": "jungle"}, moss=0.25,
                       hedge=(("jungle_leaves", 0.6), ("azalea_leaves", 0.4)),
                       plants=(("fern", 0.4), ("short_grass", 0.3), ("blue_orchid", 0.3)))),
    (("savanna",), dict(wood={"oak": "acacia", "birch": "acacia"}, hedge=(("acacia_leaves", 1.0),),
                        plants=(("short_grass", 0.5), ("short_dry_grass", 0.3), ("orange_tulip", 0.2)))),
    (("pale_garden",), dict(wood={"oak": "pale_oak", "birch": "pale_oak", "spruce": "dark_oak"}, moss=0.15,
                            hedge=(("pale_oak_leaves", 1.0),),
                            plants=(("closed_eyeblossom", 0.4), ("open_eyeblossom", 0.3), ("short_grass", 0.3)))),
    (("dark_forest",), dict(wood={"oak": "dark_oak", "birch": "dark_oak"}, moss=0.15, hedge=(("dark_oak_leaves", 1.0),))),
    (("cherry",), dict(wood={"oak": "cherry", "birch": "cherry"}, hedge=(("cherry_leaves", 1.0),),
                       plants=(("pink_petals", 0.6), ("short_grass", 0.4)))),
    (("birch",), dict(wood={"oak": "birch"}, hedge=(("birch_leaves", 1.0),))),
    (("poplar",), dict(wood={"oak": "poplar", "birch": "poplar"})),
    (("mushroom",), dict(plants=(("red_mushroom", 0.5), ("brown_mushroom", 0.5)), soil=(("mycelium", 1.0),))),
]


def biome_rule(biome: str) -> dict:
    """Biyom kimligi -> uyarlama kurali (bos dict = degisiklik yok). 'minecraft:' oneki opsiyonel."""
    b = _short(biome).lower()
    for keys, rule in _BIOME_RULES:
        if b in keys:
            return rule
    best, best_len = {}, 0
    for keys, rule in _BIOME_RULES:
        for k in keys:
            if k in b and len(k) > best_len:  # en ozgul eslesme (orn. cherry_grove -> cherry, grove degil)
                best, best_len = rule, len(k)
    return best


# ---------------------------------------------------------------------- paketler
def _p(*pairs) -> tuple:
    out = []
    for p in pairs:
        if isinstance(p, str):
            out.append((p, 1.0))
        else:
            out.append((p[0], float(p[1])))
    return tuple(out)


_BASE_PALETTE: dict[str, tuple] = {
    "foundation": _p(("stone_bricks", .6), ("cobblestone", .2), ("andesite", .2)),
    "wall": _p(("stone_bricks", .7), ("cracked_stone_bricks", .15), ("andesite", .15)),
    "wall2": _p(("oak_planks", .7), ("stripped_oak_wood", .3)),
    "accent": _p("polished_andesite"),
    "trim": _p("spruce_planks"),
    "frame": _p("spruce_planks"),
    "pillar": _p("stone_bricks"),
    "beam": _p("stripped_spruce_log"),
    "roof": _p(("spruce_planks", .6), ("dark_oak_planks", .4)),
    "roof_trim": _p("spruce_planks"),
    "floor": _p("oak_planks"),
    "floor_alt": _p("spruce_planks"),
    "ceiling": _p("spruce_planks"),
    "glass": _p("glass_pane"),
    "glass_block": _p("glass"),
    "door": _p("spruce_door"),
    "shutter": _p("spruce_trapdoor"),
    "fence": _p("spruce_fence"),
    "railing": _p("spruce_fence"),
    "light": _p("lantern"),
    "light_block": _p("glowstone"),
    "path": _p(("dirt_path", .6), ("coarse_dirt", .25), ("cobblestone", .15)),
    "paving": _p(("stone_bricks", .5), ("andesite", .3), ("cobblestone", .2)),
    "hedge": _p(("oak_leaves", .6), ("azalea_leaves", .4)),
    "plants": _p(("poppy", .25), ("dandelion", .25), ("oxeye_daisy", .25), ("short_grass", .25)),
    "soil": _p("grass_block"),
    "water_edge": _p("stone_bricks"),
    "tile": _p("bricks"),
    "metal": _p("iron_bars"),
    "detail": _p("chiseled_stone_bricks"),
    "dome": _p("polished_andesite"),
    "carpet": _p("red_carpet"),
}


def _style(name: str, desc: str, pal: dict, **kw) -> Style:
    full = dict(_BASE_PALETTE)
    full.update(pal)
    if "motifs" in kw:
        kw["motifs"] = frozenset(kw["motifs"])
    return Style(name=name, palette=full, desc=desc, **kw)


STYLES: dict[str, Style] = {}

STYLES["modern"] = _style(
    "modern", "Modern villa: beyaz beton kütleler, ahşap kaplama, geniş cam, düz çatı, koyu vurgular.",
    {
        "foundation": _p(("polished_deepslate", .7), ("deepslate_tiles", .3)),
        "wall": _p(("white_concrete", .8), ("smooth_quartz", .2)),
        "wall2": _p(("stripped_spruce_wood", .55), ("spruce_planks", .45)),
        "accent": _p(("gray_concrete", .6), ("polished_deepslate", .4)),
        "trim": _p("smooth_quartz"),
        "frame": _p("black_concrete"),
        "pillar": _p("white_concrete"),
        "beam": _p("stripped_dark_oak_log"),
        "roof": _p(("smooth_stone", .6), ("light_gray_concrete", .4)),
        "roof_trim": _p("smooth_quartz"),
        "floor": _p(("pale_oak_planks", .7), ("birch_planks", .3)),
        "floor_alt": _p("polished_deepslate"),
        "ceiling": _p("smooth_quartz"),
        "glass": _p("light_gray_stained_glass_pane"),
        "glass_block": _p("light_gray_stained_glass"),
        "door": _p("dark_oak_door"),
        "shutter": _p("dark_oak_trapdoor"),
        "fence": _p("dark_oak_fence"),
        "railing": _p("light_gray_stained_glass_pane"),
        "light": _p("lantern"),
        "light_block": _p("sea_lantern"),
        "path": _p(("polished_andesite", .7), ("smooth_stone", .3)),
        "paving": _p(("smooth_stone", .5), ("polished_andesite", .3), ("polished_diorite", .2)),
        "hedge": _p(("azalea_leaves", .6), ("oak_leaves", .4)),
        "plants": _p(("white_tulip", .3), ("azure_bluet", .3), ("allium", .2), ("short_grass", .2)),
        "water_edge": _p("smooth_quartz"),
        "tile": _p("light_gray_concrete"),
        "detail": _p("polished_deepslate"),
        "dome": _p("white_concrete"),
        "carpet": _p("light_gray_carpet"),
    },
    floor_h=5, bay=4, win_w=3, win_h=3, roof_kind="flat", pitch=0.0, overhang=1, plinth=1, corner=None,
    window_kind="ribbon", door_kind="modern", arch_kind="flat", mix=0.45,
    motifs={"flat_roof", "cantilever", "glass_rail", "wood_cladding", "pergola"})

STYLES["ottoman"] = _style(
    "ottoman", "Osmanlı konağı: taş zemin kat, bağdadi sıvalı ahşap üst katlar, cumba, geniş saçak, kiremit çatı, kemer, çini.",
    {
        "foundation": _p(("stone_bricks", .55), ("andesite", .2), ("cobblestone", .15), ("mossy_stone_bricks", .1)),
        "wall": _p(("stone_bricks", .4), ("andesite", .2), ("cobblestone", .2), ("stone", .2)),
        "wall2": _p(("calcite", .55), ("white_concrete", .3), ("smooth_quartz", .15)),
        "accent": _p("bricks"),
        "trim": _p("dark_oak_planks"),
        "frame": _p("dark_oak_planks"),
        "pillar": _p("quartz_pillar"),
        "beam": _p("stripped_dark_oak_log"),
        "roof": _p(("bricks", .7), ("granite", .15), ("polished_granite", .15)),
        "roof_trim": _p("dark_oak_planks"),
        "floor": _p(("spruce_planks", .7), ("dark_oak_planks", .3)),
        "floor_alt": _p("dark_oak_planks"),
        "ceiling": _p("spruce_planks"),
        "glass": _p("glass_pane"),
        "door": _p("spruce_door"),
        "shutter": _p("spruce_trapdoor"),
        "fence": _p("dark_oak_fence"),
        "railing": _p("dark_oak_fence"),
        "light_block": _p("glowstone"),
        "path": _p(("cobblestone", .5), ("stone", .25), ("andesite", .25)),
        "paving": _p(("smooth_stone", .4), ("polished_andesite", .3), ("stone_bricks", .3)),
        "hedge": _p(("oak_leaves", .5), ("azalea_leaves", .5)),
        "plants": _p(("red_tulip", .25), ("pink_tulip", .2), ("white_tulip", .15), ("orange_tulip", .1), ("poppy", .1),
                     ("cornflower", .1), ("lily_of_the_valley", .1)),
        "water_edge": _p(("smooth_quartz", .6), ("polished_diorite", .4)),
        "tile": _p(("cyan_glazed_terracotta", .5), ("light_blue_glazed_terracotta", .5)),
        "detail": _p("chiseled_stone_bricks"),
        "dome": _p(("polished_andesite", .7), ("andesite", .3)),
        "carpet": _p("red_carpet"),
    },
    floor_h=4, bay=2, win_w=1, win_h=2, roof_kind="hip", pitch=0.5, overhang=2, plinth=1, corner="quoins",
    window_kind="kafes", door_kind="arched", arch_kind="pointed",
    motifs={"cumba", "eaves_brackets", "almasik", "tile_band", "tulips", "kafes", "upper_timber", "jetty"})

STYLES["medieval"] = _style(
    "medieval", "Ortaçağ: taş zemin, ahşap karkaslı sıvalı üst kat (taşma), arduvaz çatı, kepenkler, mazgallı taş kale.",
    {
        "foundation": _p(("cobblestone", .45), ("mossy_cobblestone", .2), ("stone", .2), ("andesite", .15)),
        "wall": _p(("stone_bricks", .55), ("cracked_stone_bricks", .15), ("mossy_stone_bricks", .15), ("cobblestone", .15)),
        "wall2": _p(("calcite", .55), ("white_terracotta", .45)),
        "accent": _p("stone_bricks"),
        "trim": _p("spruce_planks"),
        "frame": _p("spruce_planks"),
        "pillar": _p("stone_bricks"),
        "beam": _p("dark_oak_log"),
        "roof": _p(("deepslate_tiles", .6), ("cobbled_deepslate", .25), ("deepslate_bricks", .15)),
        "roof_trim": _p("spruce_planks"),
        "floor": _p(("spruce_planks", .7), ("dark_oak_planks", .3)),
        "floor_alt": _p("stone_bricks"),
        "ceiling": _p("spruce_planks"),
        "door": _p("spruce_door"),
        "shutter": _p("spruce_trapdoor"),
        "fence": _p("spruce_fence"),
        "railing": _p("spruce_fence"),
        "path": _p(("dirt_path", .45), ("coarse_dirt", .25), ("cobblestone", .2), ("mossy_cobblestone", .1)),
        "paving": _p(("cobblestone", .4), ("stone_bricks", .3), ("andesite", .3)),
        "hedge": _p(("oak_leaves", .6), ("dark_oak_leaves", .4)),
        "plants": _p(("poppy", .2), ("dandelion", .2), ("oxeye_daisy", .2), ("cornflower", .15), ("short_grass", .25)),
        "carpet": _p("brown_carpet"),
        "dome": _p("deepslate_tiles"),
    },
    floor_h=4, bay=3, win_w=1, win_h=2, roof_kind="gable", pitch=1.0, overhang=1, plinth=1, corner="pillar",
    window_kind="shutters", door_kind="framed", arch_kind="round",
    motifs={"timber", "jetty", "crenels", "shutters", "upper_timber"})

STYLES["futuristic"] = _style(
    "futuristic", "Fütüristik: cam kuleler, beyaz/siyah paneller, camgöbeği ışık şeritleri, konsol çıkmalar.",
    {
        "foundation": _p(("black_concrete", .6), ("polished_blackstone", .4)),
        "wall": _p(("white_concrete", .6), ("smooth_quartz", .4)),
        "wall2": _p(("black_concrete", .7), ("gray_concrete", .3)),
        "accent": _p("cyan_concrete"),
        "trim": _p("smooth_quartz"),
        "frame": _p("black_concrete"),
        "pillar": _p("smooth_quartz"),
        "beam": _p("gray_concrete"),
        "roof": _p(("light_gray_concrete", .6), ("smooth_stone", .4)),
        "roof_trim": _p("smooth_quartz"),
        "floor": _p(("smooth_quartz", .7), ("white_concrete", .3)),
        "floor_alt": _p("black_concrete"),
        "ceiling": _p("smooth_quartz"),
        "glass": _p("light_blue_stained_glass_pane"),
        "glass_block": _p(("light_blue_stained_glass", .6), ("cyan_stained_glass", .4)),
        "door": _p("pale_oak_door"),
        "shutter": _p("iron_trapdoor"),
        "fence": _p("pale_oak_fence"),
        "railing": _p("light_blue_stained_glass_pane"),
        "light": _p("soul_lantern"),
        "light_block": _p("sea_lantern"),
        "path": _p(("light_gray_concrete", .5), ("smooth_stone", .5)),
        "paving": _p(("smooth_quartz", .5), ("white_concrete", .5)),
        "hedge": _p("azalea_leaves"),
        "plants": _p(("allium", .25), ("blue_orchid", .25), ("azure_bluet", .25), ("white_tulip", .25)),
        "soil": _p(("moss_block", .5), ("grass_block", .5)),
        "water_edge": _p("smooth_quartz"),
        "tile": _p("cyan_concrete"),
        "detail": _p("sea_lantern"),
        "dome": _p("light_blue_stained_glass"),
        "carpet": _p("light_gray_carpet"),
    },
    floor_h=5, bay=2, win_w=1, win_h=3, roof_kind="flat", pitch=0.0, overhang=2, plinth=1, corner=None,
    window_kind="ribbon", door_kind="modern", arch_kind="flat", mix=0.35,
    motifs={"glass_curtain", "light_strips", "fins", "cantilever", "flat_roof"})

STYLES["japanese"] = _style(
    "japanese", "Japon: koyu ahşap iskelet, beyaz sıva/shoji, kavisli görünümlü geniş saçaklı kiremit çatı, engawa, taş fener.",
    {
        "foundation": _p(("polished_andesite", .5), ("andesite", .3), ("stone", .2)),
        "wall": _p(("calcite", .5), ("white_concrete", .5)),
        "wall2": _p(("dark_oak_planks", .6), ("spruce_planks", .4)),
        "accent": _p("dark_oak_planks"),
        "trim": _p("dark_oak_planks"),
        "frame": _p("dark_oak_planks"),
        "pillar": _p("stripped_dark_oak_log"),
        "beam": _p("stripped_dark_oak_log"),
        "roof": _p(("deepslate_tiles", .7), ("polished_deepslate", .3)),
        "roof_trim": _p("polished_deepslate"),
        "floor": _p(("spruce_planks", .7), ("dark_oak_planks", .3)),
        "floor_alt": _p("bamboo_mosaic"),
        "ceiling": _p("spruce_planks"),
        "glass": _p("white_stained_glass_pane"),
        "glass_block": _p("white_stained_glass"),
        "door": _p("spruce_door"),
        "shutter": _p("spruce_trapdoor"),
        "fence": _p("dark_oak_fence"),
        "railing": _p("dark_oak_fence"),
        "light_block": _p("shroomlight"),
        "path": _p(("andesite", .4), ("polished_andesite", .3), ("stone", .3)),
        "paving": _p(("polished_andesite", .5), ("smooth_stone", .5)),
        "hedge": _p(("azalea_leaves", .5), ("dark_oak_leaves", .3), ("cherry_leaves", .2)),
        "plants": _p(("azure_bluet", .2), ("lily_of_the_valley", .2), ("fern", .25), ("white_tulip", .15), ("pink_tulip", .2)),
        "soil": _p(("moss_block", .5), ("grass_block", .5)),
        "water_edge": _p(("andesite", .5), ("stone", .5)),
        "tile": _p("red_concrete"),
        "metal": _p("iron_chain"),
        "detail": _p("polished_deepslate"),
        "dome": _p("deepslate_tiles"),
        "carpet": _p("green_carpet"),
    },
    floor_h=4, bay=2, win_w=2, win_h=2, roof_kind="curved", pitch=0.5, overhang=2, plinth=1, corner="pillar",
    window_kind="shoji", door_kind="framed", arch_kind="flat",
    motifs={"engawa", "curved_eaves", "shoji", "toro", "timber"})

STYLES["scandinavian"] = _style(
    "scandinavian", "İskandinav: koyu/siyah ahşap kaplama, dik çatı, beyaz pervaz ve köşe tahtaları, taş kaide.",
    {
        "foundation": _p(("cobblestone", .4), ("stone", .3), ("andesite", .3)),
        "wall": _p(("dark_oak_planks", .7), ("stripped_dark_oak_wood", .3)),
        "wall2": _p(("spruce_planks", .6), ("stripped_spruce_wood", .4)),
        "accent": _p("pale_oak_planks"),
        "trim": _p("pale_oak_planks"),
        "frame": _p("pale_oak_planks"),
        "pillar": _p("stripped_pale_oak_log"),
        "beam": _p("stripped_spruce_log"),
        "roof": _p(("deepslate_tiles", .7), ("deepslate_bricks", .3)),
        "roof_trim": _p("pale_oak_planks"),
        "floor": _p(("pale_oak_planks", .6), ("birch_planks", .4)),
        "floor_alt": _p("spruce_planks"),
        "ceiling": _p("pale_oak_planks"),
        "door": _p("spruce_door"),
        "shutter": _p("spruce_trapdoor"),
        "fence": _p("pale_oak_fence"),
        "railing": _p("pale_oak_fence"),
        "light_block": _p("ochre_froglight"),
        "path": _p(("cobblestone", .3), ("stone", .3), ("coarse_dirt", .2), ("andesite", .2)),
        "paving": _p(("stone", .5), ("polished_andesite", .5)),
        "hedge": _p(("spruce_leaves", .7), ("birch_leaves", .3)),
        "plants": _p(("fern", .3), ("short_grass", .3), ("lily_of_the_valley", .2), ("cornflower", .2)),
        "metal": _p("iron_chain"),
        "tile": _p("white_concrete"),
        "detail": _p("polished_andesite"),
        "dome": _p("deepslate_tiles"),
        "carpet": _p("white_carpet"),
    },
    floor_h=4, bay=3, win_w=1, win_h=2, roof_kind="gable", pitch=2.0, overhang=1, plinth=1, corner="pillar",
    window_kind="framed", door_kind="framed", arch_kind="flat",
    motifs={"white_trim", "steep_roof", "corner_boards"})

STYLES["mediterranean"] = _style(
    "mediterranean", "Akdeniz/Ege: kireç badanalı beyaz duvarlar, mavi kepenk ve kapılar, kiremit çatı, çardak, begonvil.",
    {
        "foundation": _p(("smooth_sandstone", .6), ("sandstone", .4)),
        "wall": _p(("white_concrete", .5), ("calcite", .35), ("smooth_quartz", .15)),
        "wall2": _p(("smooth_sandstone", .6), ("white_terracotta", .4)),
        "accent": _p("blue_concrete"),
        "trim": _p("smooth_quartz"),
        "frame": _p("warped_planks"),
        "pillar": _p("smooth_quartz"),
        "beam": _p("stripped_oak_log"),
        "roof": _p(("smooth_red_sandstone", .5), ("red_sandstone", .3), ("granite", .2)),
        "roof_trim": _p("smooth_quartz"),
        "floor": _p(("terracotta", .6), ("orange_terracotta", .4)),
        "floor_alt": _p("smooth_quartz"),
        "ceiling": _p("white_concrete"),
        "door": _p("warped_door"),
        "shutter": _p("warped_trapdoor"),
        "fence": _p("oak_fence"),
        "railing": _p("diorite_wall"),
        "light_block": _p("ochre_froglight"),
        "path": _p(("polished_diorite", .3), ("andesite", .35), ("stone", .35)),
        "paving": _p(("polished_diorite", .4), ("calcite", .3), ("smooth_quartz", .3)),
        "hedge": _p(("flowering_azalea_leaves", .5), ("azalea_leaves", .3), ("cherry_leaves", .2)),
        "plants": _p(("allium", .2), ("pink_tulip", .2), ("poppy", .2), ("blue_orchid", .2), ("oxeye_daisy", .2)),
        "water_edge": _p("smooth_quartz"),
        "tile": _p(("blue_glazed_terracotta", .5), ("light_blue_glazed_terracotta", .5)),
        "detail": _p("chiseled_quartz_block"),
        "dome": _p("blue_concrete"),
        "carpet": _p("blue_carpet"),
    },
    floor_h=4, bay=3, win_w=1, win_h=2, roof_kind="hip", pitch=0.5, overhang=1, plinth=1, corner=None,
    window_kind="shutters", door_kind="arched", arch_kind="round", mix=0.6,
    motifs={"shutters", "pergola", "blue_dome", "bougainvillea", "whitewash"})

STYLES["rustic"] = _style(
    "rustic", "Kır köyü: kütük köşeler, karışık tahta duvarlar, kerpiç dolgu, ahşap kiremit çatı, çiçek kutuları, çit bahçe.",
    {
        "foundation": _p(("cobblestone", .5), ("mossy_cobblestone", .25), ("stone", .25)),
        "wall": _p(("oak_planks", .55), ("spruce_planks", .3), ("stripped_oak_wood", .15)),
        "wall2": _p(("packed_mud", .5), ("mud_bricks", .5)),
        "accent": _p("stripped_spruce_wood"),
        "trim": _p("spruce_planks"),
        "frame": _p("dark_oak_planks"),
        "pillar": _p("spruce_log"),
        "beam": _p("spruce_log"),
        "roof": _p(("spruce_planks", .45), ("dark_oak_planks", .3), ("oak_planks", .25)),
        "roof_trim": _p("spruce_planks"),
        "floor": _p(("oak_planks", .6), ("spruce_planks", .4)),
        "floor_alt": _p("cobblestone"),
        "ceiling": _p("spruce_planks"),
        "door": _p("spruce_door"),
        "shutter": _p("spruce_trapdoor"),
        "fence": _p("oak_fence"),
        "railing": _p("spruce_fence"),
        "path": _p(("dirt_path", .6), ("coarse_dirt", .25), ("cobblestone", .15)),
        "paving": _p(("cobblestone", .5), ("mossy_cobblestone", .3), ("stone", .2)),
        "hedge": _p(("oak_leaves", .6), ("birch_leaves", .4)),
        "plants": _p(("poppy", .2), ("dandelion", .25), ("cornflower", .15), ("short_grass", .25), ("oxeye_daisy", .15)),
        "soil": _p(("grass_block", .7), ("coarse_dirt", .15), ("rooted_dirt", .15)),
        "water_edge": _p("cobblestone"),
        "metal": _p("iron_chain"),
        "dome": _p("spruce_planks"),
        "carpet": _p("brown_carpet"),
    },
    floor_h=4, bay=3, win_w=1, win_h=2, roof_kind="gable", pitch=1.0, overhang=1, plinth=1, corner="log",
    window_kind="shutters", door_kind="framed", arch_kind="round", mix=0.6,
    motifs={"log_corners", "shutters", "flower_boxes", "fence_garden"})

STYLES["classical"] = _style(
    "classical", "Klasik/neoklasik: mermer sütunlar, alınlık, korniş, korkuluklu teras, bakır yeşili kubbe.",
    {
        "foundation": _p(("stone_bricks", .6), ("polished_andesite", .4)),
        "wall": _p(("smooth_quartz", .55), ("quartz_bricks", .25), ("calcite", .2)),
        "wall2": _p(("smooth_sandstone", .6), ("cut_sandstone", .4)),
        "accent": _p("quartz_bricks"),
        "trim": _p("smooth_quartz"),
        "frame": _p("smooth_quartz"),
        "pillar": _p("quartz_pillar"),
        "beam": _p("smooth_quartz"),
        "roof": _p(("polished_andesite", .6), ("andesite", .4)),
        "roof_trim": _p("smooth_quartz"),
        "floor": _p(("polished_diorite", .5), ("smooth_quartz", .5)),
        "floor_alt": _p("polished_andesite"),
        "ceiling": _p("smooth_quartz"),
        "door": _p("dark_oak_door"),
        "shutter": _p("dark_oak_trapdoor"),
        "fence": _p("dark_oak_fence"),
        "railing": _p("diorite_wall"),
        "path": _p(("smooth_stone", .5), ("polished_andesite", .5)),
        "paving": _p(("smooth_stone", .4), ("polished_diorite", .3), ("polished_andesite", .3)),
        "hedge": _p(("oak_leaves", .5), ("spruce_leaves", .5)),
        "plants": _p(("white_tulip", .3), ("lily_of_the_valley", .3), ("azure_bluet", .2), ("oxeye_daisy", .2)),
        "water_edge": _p("smooth_quartz"),
        "tile": _p("polished_andesite"),
        "detail": _p("chiseled_quartz_block"),
        "dome": _p("waxed_oxidized_cut_copper"),
        "carpet": _p("red_carpet"),
    },
    floor_h=5, bay=3, win_w=1, win_h=3, roof_kind="hip", pitch=0.5, overhang=1, plinth=1, corner="pilaster",
    window_kind="framed", door_kind="portico", arch_kind="round", mix=0.4,
    motifs={"columns", "pediment", "balustrade", "cornice"})


def names() -> list[str]:
    return list(STYLES)


def get(name: str = "medieval", biome: str | None = None) -> Style:
    """Hazir stil (kopya) ve istege bagli biyom uyarlamasi: get("ottoman", "desert")."""
    key = name.lower().strip()
    aliases = {"osmanli": "ottoman", "osmanlı": "ottoman", "ortacag": "medieval", "ortaçağ": "medieval",
               "japon": "japanese", "iskandinav": "scandinavian", "akdeniz": "mediterranean", "ege": "mediterranean",
               "aegean": "mediterranean", "koy": "rustic", "köy": "rustic", "village": "rustic", "klasik": "classical",
               "futurist": "futuristic", "fütüristik": "futuristic", "modern_villa": "modern"}
    key = aliases.get(key, key)
    if key not in STYLES:
        raise KeyError(f"bilinmeyen stil: {name} (olanlar: {', '.join(STYLES)})")
    st = replace(STYLES[key], _cache={})
    return st.adapt(biome) if biome else st
