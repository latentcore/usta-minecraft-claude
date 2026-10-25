"""Ic mekan doseme receteleri (interiors) -- yalniz vanilla 26.3 bloklariyla "usta isi" odalar.

API (calisma anindaki Claude icin):
  furnish(build, box, kind, style=None, door=None, seed=0) -> dict
      box   = (x0, y0, z0, x1, y1, z1): odanin IC HAVA hacmi (uclar dahil). Zemin blogu y0-1'de, tavan y1+1'de,
              duvarlar kutunun hemen disinda (x0-1, x1+1, z0-1, z1+1). Once kabugu (zemin/duvar/tavan/kapi) kur, sonra doset.
      kind  = ROOM_KINDS anahtari ya da serbest metin ("mutfak", "yatak odasi", "living room"...; detect_room_kind ile).
      style = None (recetenin varsayilani) | STYLES adi: modern, iskandinav(nordic), rustik(rustic), ortacag(medieval),
              saray(royal), osmanli(ottoman), japon(japanese), futuristik(futuristic), endustriyel(industrial)
              | sozluk: {"base": "modern", "wood": "cherry", "wood2": "dark_oak", "fabric": "blue", "rug": "white", ...}
              (anahtarlar: wood wood2 counter stone stone2 fabric fabric2 accent bed rug rug2 rug3 metal lamp flush candle
               leaves plants sconce light_order).
      door  = kapi hucreleri [(x,y,z), ...] (duvar halkasinda) ya da bos kalacak hucreler (kutu icinde). Verilmezse
              build.meta["doors"] ve duvardaki kapi bloklari aranir; o da yoksa on (-z) duvarin ortasi varsayilir.
      seed  = ceşitleme (renk/bitki/kucuk kaydirmalar); ayni seed ayni sonuc.
      Doner: oda kaydi; build.meta["rooms"] (name, kind, box, recipe, style, doors, lights, furniture) ve
             build.meta["lights"] ({pos, block, level, how, room}) listelerine de yazilir.
  furnish_<kind>(build, box, style=None, door=None, seed=0) -> dict  -- her recetenin dogrudan cagrisi (ROOM_KINDS).
  ROOM_KINDS: {kind: "Turkce aciklama"}  |  STYLES: {ad: palet}  |  detect_room_kind(metin) -> kind | None
  room_report(build, box, door=None) -> {"door_paths_ok", "dark_spots", "min_light", "unsupported", ...}  (denetim)
  light_map(build, box) -> (isik[y,z,x], koken)   -- basit blok isigi yayilimi (gece, kapali oda varsayimi)
  demo_room(kind, size=(12,4,10), style=None, seed=0) -> (build, box, doors)  -- basit kabuk + doseme
  save_room_preview(build, box, path, door=None) -> path  -- kesit izometrik, plan, tavan plani, isik haritasi

Recetelerin uydugu kurallar:
  * Her kapidan oda merkezine 2 blok yuksek yurunebilir yol acik kalir; asili isiklar yerden en az 2 blok yukarida.
  * Kutu disina yalniz: zemin/tavan katmaninda GIZLI isik blogu (deniz feneri, isiktas, kurbaga isigi, bakir ampul) ve
    duvar halkasinda duvara gomulu tam blok (aplik isigi, ekran arkasi). Kutu disinda asla hava/delik acilmaz.
  * Destek isteyen her blok destegiyle (fener, mesale, mum, hali, saksi, buton, tabela, kapi), yatak/kapi iki yarimiyla.
  * Isik: odada dogabilir (spawn) hicbir hucre karanlik (blok isigi 0) kalmaz; yurunen zemin "rahat" aydinliga
    (receteye gore 5-9) getirilir -- eksik kalan yere stile uygun ek isik (tavan gomme, asili fener, hali alti isik).
  * Varliklar (tablo, esya cercevesi, zirh askisi) konmaz.
"""
from __future__ import annotations

import random
import re
import unicodedata
from collections import deque

import numpy as np

from .. import blockdb
from ..blockdb import split_state
from ..plan import AIR, KEEP
from .core import Build

DIRS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
OPP = {"north": "south", "south": "north", "west": "east", "east": "west", "up": "down", "down": "up"}
# kanonik oda cercevesi: u = kapidan bakinca soldan saga, v = kapi duvarindan odak (karsi) duvarina
TV = {"F": (0, 1), "B": (0, -1), "R": (1, 0), "L": (-1, 0)}
OPPT = {"F": "B", "B": "F", "L": "R", "R": "L"}
CWT = {"F": "R", "R": "B", "B": "L", "L": "F"}
PERP = {"F": ("L", "R"), "B": ("R", "L"), "L": ("B", "F"), "R": ("F", "B")}
ROT16 = {"south": 0, "west": 4, "north": 8, "east": 12}
COLORS = ("white", "light_gray", "gray", "black", "brown", "red", "orange", "yellow", "lime", "green", "cyan",
          "light_blue", "blue", "purple", "magenta", "pink")
WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak", "bamboo",
         "crimson", "warped", "poplar")


def _dname(dx: int, dz: int) -> str:
    for k, (a, b) in DIRS.items():
        if (a, b) == (dx, dz):
            return k
    raise ValueError((dx, dz))


def _bname(s: str) -> str:
    return s.lstrip("!").split("[", 1)[0].split(":", 1)[-1]


# ====================================================================== malzeme yardimcilari
def wood_block(w: str, part: str) -> str:
    """wood_block("spruce", "stairs") -> "spruce_stairs"; log/wood/stripped_* nether ve bambu icin dogru adla."""
    if part in ("log", "wood", "stripped_log", "stripped_wood"):
        strip = part.startswith("stripped")
        base = part.replace("stripped_", "")
        if w == "bamboo":
            return "stripped_bamboo_block" if strip else "bamboo_block"
        if w in ("crimson", "warped"):
            base = {"log": "stem", "wood": "hyphae"}[base]
        return ("stripped_" if strip else "") + f"{w}_{base}"
    return f"{w}_{part}"


_STONE = {
    "stone_bricks": ("stone_bricks", "stone_brick_slab", "stone_brick_stairs", "stone_brick_wall"),
    "mossy_stone_bricks": ("mossy_stone_bricks", "mossy_stone_brick_slab", "mossy_stone_brick_stairs", "mossy_stone_brick_wall"),
    "bricks": ("bricks", "brick_slab", "brick_stairs", "brick_wall"),
    "quartz": ("quartz_block", "quartz_slab", "quartz_stairs", "diorite_wall"),
    "smooth_quartz": ("smooth_quartz", "smooth_quartz_slab", "smooth_quartz_stairs", "diorite_wall"),
    "quartz_bricks": ("quartz_bricks", "quartz_slab", "quartz_stairs", "diorite_wall"),
    "deepslate_tiles": ("deepslate_tiles", "deepslate_tile_slab", "deepslate_tile_stairs", "deepslate_tile_wall"),
    "deepslate_bricks": ("deepslate_bricks", "deepslate_brick_slab", "deepslate_brick_stairs", "deepslate_brick_wall"),
    "tuff_bricks": ("tuff_bricks", "tuff_brick_slab", "tuff_brick_stairs", "tuff_brick_wall"),
    "mud_bricks": ("mud_bricks", "mud_brick_slab", "mud_brick_stairs", "mud_brick_wall"),
    "nether_bricks": ("nether_bricks", "nether_brick_slab", "nether_brick_stairs", "nether_brick_wall"),
    "end_stone_bricks": ("end_stone_bricks", "end_stone_brick_slab", "end_stone_brick_stairs", "end_stone_brick_wall"),
    "prismarine_bricks": ("prismarine_bricks", "prismarine_brick_slab", "prismarine_brick_stairs", "prismarine_wall"),
    "polished_blackstone_bricks": ("polished_blackstone_bricks", "polished_blackstone_brick_slab",
                                   "polished_blackstone_brick_stairs", "polished_blackstone_brick_wall"),
    "smooth_stone": ("smooth_stone", "smooth_stone_slab", "stone_stairs", "cobblestone_wall"),
    "stone": ("stone", "stone_slab", "stone_stairs", "cobblestone_wall"),
    "purpur": ("purpur_block", "purpur_slab", "purpur_stairs", "end_stone_brick_wall"),
    "cut_sandstone": ("cut_sandstone", "cut_sandstone_slab", "smooth_sandstone_stairs", "sandstone_wall"),
    "smooth_sandstone": ("smooth_sandstone", "smooth_sandstone_slab", "smooth_sandstone_stairs", "sandstone_wall"),
    "calcite": ("calcite", "polished_diorite_slab", "polished_diorite_stairs", "diorite_wall"),
    "white_concrete": ("white_concrete", "white_concrete_slab", "white_concrete_stairs", "diorite_wall"),
    "light_gray_concrete": ("light_gray_concrete", "light_gray_concrete_slab", "light_gray_concrete_stairs", "andesite_wall"),
}


def stone_parts(db, name: str) -> dict:
    """Tas ailesi: {"block","slab","stairs","wall"} (eksik parca icin makul yedek)."""
    if name in _STONE:
        b, s, st, w = _STONE[name]
    else:
        base = name[:-1] if name.endswith("bricks") or name.endswith("tiles") else name
        b, s, st, w = name, base + "_slab", base + "_stairs", base + "_wall"
    out = {"block": b, "slab": s, "stairs": st, "wall": w}
    fb = {"block": "stone_bricks", "slab": "smooth_stone_slab", "stairs": "stone_brick_stairs", "wall": "cobblestone_wall"}
    for k, v in list(out.items()):
        if not db.has_block(v):
            out[k] = fb[k]
    return out


# ====================================================================== stiller
_BASE_STYLE = dict(
    wood="oak", wood2="spruce", counter="smooth_stone", stone="stone_bricks", stone2="polished_andesite",
    fabric="red", fabric2="white", accent="yellow", bed="red", rug="red", rug2="yellow", rug3="brown",
    metal="iron", lamp="lantern", flush="glowstone", candle="", leaves="azalea_leaves",
    plants=("potted_fern", "potted_red_tulip", "potted_azalea_bush", "potted_oxeye_daisy"),
    sconce="torch", light_order=("hang", "top", "wall", "floor", "flush"), tv=False, hearth=False)

STYLES: dict[str, dict] = {
    "modern": dict(wood="birch", wood2="dark_oak", counter="smooth_quartz", stone="smooth_quartz", stone2="polished_andesite",
                   fabric="light_gray", fabric2="gray", accent="cyan", bed="light_gray", rug="white", rug2="light_gray",
                   rug3="gray", lamp="lantern", flush="sea_lantern", candle="white", leaves="azalea_leaves",
                   plants=("potted_fern", "potted_bamboo", "potted_azalea_bush", "potted_cactus", "potted_white_tulip"),
                   sconce="rod", light_order=("flush", "hang", "floor", "top", "wall"), tv=True),
    "nordic": dict(wood="pale_oak", wood2="spruce", counter="calcite", stone="calcite", stone2="polished_diorite",
                   fabric="white", fabric2="light_gray", accent="light_blue", bed="white", rug="white", rug2="light_gray",
                   rug3="light_blue", lamp="lantern", flush="pearlescent_froglight", candle="white",
                   leaves="spruce_leaves", plants=("potted_fern", "potted_spruce_sapling", "potted_lily_of_the_valley",
                                                   "potted_azure_bluet"),
                   sconce="lantern", light_order=("hang", "flush", "floor", "top", "wall"), tv=True),
    "rustic": dict(wood="spruce", wood2="dark_oak", counter="spruce_planks", stone="cobblestone", stone2="stone_bricks",
                   fabric="brown", fabric2="red", accent="orange", bed="red", rug="red", rug2="brown", rug3="orange",
                   lamp="lantern", flush="ochre_froglight", candle="", leaves="oak_leaves",
                   plants=("potted_poppy", "potted_dandelion", "potted_fern", "potted_oxeye_daisy", "potted_red_tulip"),
                   sconce="lantern", light_order=("hang", "top", "wall", "floor", "flush"), hearth=True),
    "medieval": dict(wood="dark_oak", wood2="spruce", counter="stone_bricks", stone="stone_bricks", stone2="cobblestone",
                     fabric="red", fabric2="yellow", accent="yellow", bed="red", rug="red", rug2="yellow", rug3="black",
                     lamp="lantern", flush="glowstone", candle="", leaves="oak_leaves",
                     plants=("potted_poppy", "potted_fern", "potted_dead_bush", "potted_red_mushroom"),
                     sconce="torch", light_order=("hang", "wall", "top", "floor", "flush"), hearth=True),
    "royal": dict(wood="dark_oak", wood2="spruce", counter="quartz", stone="quartz", stone2="polished_blackstone",
                  fabric="red", fabric2="yellow", accent="yellow", bed="red", rug="red", rug2="yellow", rug3="purple",
                  metal="copper", lamp="lantern", flush="glowstone", candle="yellow", leaves="dark_oak_leaves",
                  plants=("potted_red_tulip", "potted_white_tulip", "potted_allium", "potted_azalea_bush"),
                  sconce="lantern", light_order=("hang", "top", "wall", "floor", "flush"), hearth=True),
    "ottoman": dict(wood="dark_oak", wood2="spruce", counter="smooth_sandstone", stone="smooth_sandstone",
                    stone2="cut_sandstone", fabric="red", fabric2="orange", accent="cyan", bed="red", rug="red",
                    rug2="orange", rug3="yellow", metal="copper", lamp="waxed_copper_lantern", flush="ochre_froglight",
                    candle="", leaves="flowering_azalea_leaves",
                    plants=("potted_red_tulip", "potted_orange_tulip", "potted_pink_tulip", "potted_white_tulip"),
                    sconce="lantern", light_order=("hang", "top", "floor", "flush", "wall")),
    "japanese": dict(wood="spruce", wood2="dark_oak", counter="spruce_planks", stone="polished_andesite",
                     stone2="smooth_stone", fabric="white", fabric2="gray", accent="red", bed="white", rug="green",
                     rug2="lime", rug3="red", lamp="lantern", flush="pearlescent_froglight", candle="white",
                     leaves="cherry_leaves", plants=("potted_bamboo", "potted_cherry_sapling", "potted_azalea_bush",
                                                     "potted_fern"),
                     sconce="lantern", light_order=("screen", "hang", "floor", "flush")),
    "futuristic": dict(wood="pale_oak", wood2="warped", counter="white_concrete", stone="white_concrete",
                       stone2="light_gray_concrete", fabric="white", fabric2="cyan", accent="cyan", bed="white",
                       rug="light_gray", rug2="cyan", rug3="black", lamp="end_rod", flush="sea_lantern", candle="white",
                       leaves="azalea_leaves", plants=("potted_bamboo", "potted_cactus", "potted_fern", "potted_warped_fungus"),
                       sconce="rod", light_order=("flush", "floor", "wall"), tv=True),
    "industrial": dict(wood="spruce", wood2="dark_oak", counter="polished_deepslate", stone="polished_deepslate",
                       stone2="tuff_bricks", fabric="gray", fabric2="brown", accent="orange", bed="gray", rug="gray",
                       rug2="black", rug3="brown", lamp="lantern", flush="glowstone", candle="",
                       leaves="spruce_leaves", plants=("potted_fern", "potted_cactus", "potted_dead_bush"),
                       sconce="lantern", light_order=("hang", "flush", "wall", "top", "floor")),
}
STYLE_ALIASES = {
    "cagdas": "modern", "minimal": "modern", "minimalist": "modern", "contemporary": "modern",
    "iskandinav": "nordic", "scandinavian": "nordic", "skandinav": "nordic",
    "rustik": "rustic", "koy": "rustic", "kir": "rustic", "farmhouse": "rustic", "kulube": "rustic", "cottage": "rustic",
    "ortacag": "medieval", "kale": "medieval", "castle": "medieval", "sato": "medieval",
    "saray": "royal", "kraliyet": "royal", "palace": "royal", "luks": "royal",
    "osmanli": "ottoman", "turk": "ottoman", "klasik turk": "ottoman",
    "japon": "japanese", "japan": "japanese", "zen": "japanese",
    "futuristik": "futuristic", "fütüristik": "futuristic", "bilimkurgu": "futuristic", "sci-fi": "futuristic",
    "scifi": "futuristic", "uzay": "futuristic",
    "endustriyel": "industrial", "loft": "industrial",
}


def _fold(text: str) -> str:
    """Turkce farkindalikli kucuk harf + ASCII katlama ("Çocuk Odası" -> "cocuk odasi")."""
    t = text.replace("İ", "i").replace("I", "ı").lower()
    t = t.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def resolve_style(style, default: str, db=None) -> tuple[str, dict]:
    """Stil adi/sozlugu -> (ad, tam palet). Bilinmeyen ad ValueError verir."""
    def named(n: str) -> tuple[str, dict]:
        k = _fold(n).replace(" ", "_")
        k = STYLE_ALIASES.get(k.replace("_", " "), STYLE_ALIASES.get(k, k))
        if k not in STYLES:
            raise ValueError(f"bilinmeyen stil: {n!r} (olanlar: {', '.join(STYLES)})")
        d = dict(_BASE_STYLE)
        d.update(STYLES[k])
        return k, d
    if style is None:
        return named(default)
    if isinstance(style, str):
        return named(style)
    if isinstance(style, dict):
        name, d = named(style.get("base", default))
        d.update({k: v for k, v in style.items() if k != "base"})
        if db is not None:
            for k in ("wood", "wood2"):
                if not db.has_block(wood_block(d[k], "planks")):
                    raise ValueError(f"stil {k}={d[k]!r} gecersiz agac (olanlar: {', '.join(WOODS)})")
            for k in ("fabric", "fabric2", "accent", "bed", "rug", "rug2", "rug3"):
                if d[k] not in COLORS:
                    raise ValueError(f"stil {k}={d[k]!r} gecersiz renk (olanlar: {', '.join(COLORS)})")
        return name + "*", d
    raise TypeError("style: None | str | dict")


# ====================================================================== blok siniflari (yurume / isik / destek)
_NOCOLL = {"air", "cave_air", "void_air", "light", "structure_void", "torch", "wall_torch", "soul_torch",
           "soul_wall_torch", "copper_torch", "copper_wall_torch", "redstone_torch", "redstone_wall_torch", "lever",
           "tripwire", "tripwire_hook", "redstone_wire", "rail", "vine", "glow_lichen", "cave_vines", "cave_vines_plant",
           "weeping_vines", "weeping_vines_plant", "twisting_vines", "twisting_vines_plant", "spore_blossom",
           "pale_hanging_moss", "hanging_roots", "sculk_vein", "resin_clump", "nether_portal"}
_NOCOLL_SUFFIX = ("_sign", "_banner", "_button", "_pressure_plate", "_rail")
_PLANT_SOLID = {"cactus", "bamboo", "sweet_berry_bush", "azalea", "flowering_azalea", "sea_pickle", "big_dripleaf",
                "lily_pad", "pitcher_crop", "chorus_plant", "chorus_flower"}
_SIGNAL = ("_pressure_plate", "_button", "lever", "redstone_torch", "redstone_wall_torch", "tripwire_hook",
           "redstone_wire", "rail", "tripwire")
DIRTISH = {"dirt", "grass_block", "podzol", "rooted_dirt", "coarse_dirt", "moss_block", "mud", "muddy_mangrove_roots",
           "farmland", "pale_moss_block", "mycelium"}


def _cls(db, s: str) -> str:
    """Yurume sinifi: none (carpismasiz), thin (hali/kapali alt kapak: ustunden yurunur), edge (acik kapak/merdiven
    gibi kenar paneli), slab (alt basamak 0.5), full (ustu 1.0'da basilir), fluid, block (esya/engel), keep."""
    if s == KEEP:
        return "keep"
    st = s.lstrip("!")
    n = _bname(st)
    f = db.flags_of(st)
    if f & blockdb.AIR:
        return "none"
    if n in ("water", "lava", "bubble_column"):
        return "fluid"
    if n.endswith("_carpet") or n == "moss_carpet":
        return "thin"
    if n.endswith("_trapdoor"):
        if "open=true" in st:
            return "edge"
        return "thin" if "half=bottom" in st else "full"
    if n in ("ladder",):
        return "edge"
    if n.endswith("_slab"):
        return "slab" if "type=bottom" in st else "full"
    if n in _NOCOLL or n.endswith(_NOCOLL_SUFFIX) or n.endswith("_wall_torch"):
        return "none"
    if (f & blockdb.PLANT) and n not in _PLANT_SOLID:
        return "none"
    if f & blockdb.REPLACEABLE:
        return "none"
    if int(db.sturdy[db.id(st)]) & blockdb.FACE_BIT["up"]:
        return "full"
    return "block"


def _light_tables(b: Build):
    db = b.db
    n = len(b.palette)
    emit = np.zeros(n, dtype=np.int16)
    opq = np.zeros(n, dtype=bool)
    for i, s in enumerate(b.palette):
        if i <= 1:
            continue
        st = s.lstrip("!")
        sid = db.id(st)
        emit[i] = int(db.light[sid])
        f = int(db.flags[sid])
        nm = _bname(st)
        # temkinli: merdiven/yarim levha yonlu isik kesebilir -> opak say
        opq[i] = bool(f & blockdb.SOLID_RENDER) or nm.endswith("_stairs") or (nm.endswith("_slab") and "type=double" not in st)
    return emit, opq


def light_map(b: Build, box, margin: int = 1):
    """Kutu (+margin) icin blok isigi (0..15) dizisi [y,z,x] ve koken (x,y,z). Kutu ici bilinmeyen = hava,
    kutu disi bilinmeyen = opak duvar; disaridan gelen isik yok sayilir (temkinli)."""
    x0, y0, z0, x1, y1, z1 = box
    ox, oy, oz = x0 - margin, y0 - margin, z0 - margin
    ids = b.ids_box(ox, oy, oz, x1 + margin, y1 + margin, z1 + margin)
    emit, opq = _light_tables(b)
    E = emit[ids]
    O = opq[ids].copy()
    keep = ids == 0
    inside = np.zeros(ids.shape, dtype=bool)
    inside[margin:margin + (y1 - y0 + 1), margin:margin + (z1 - z0 + 1), margin:margin + (x1 - x0 + 1)] = True
    O[keep & ~inside] = True
    O[keep & inside] = False
    T = ~O
    L = E.astype(np.int16)
    for _ in range(16):
        nb = np.zeros_like(L)
        nb[1:] = np.maximum(nb[1:], L[:-1])
        nb[:-1] = np.maximum(nb[:-1], L[1:])
        nb[:, 1:] = np.maximum(nb[:, 1:], L[:, :-1])
        nb[:, :-1] = np.maximum(nb[:, :-1], L[:, 1:])
        nb[:, :, 1:] = np.maximum(nb[:, :, 1:], L[:, :, :-1])
        nb[:, :, :-1] = np.maximum(nb[:, :, :-1], L[:, :, 1:])
        new = np.maximum(L, np.where(T, nb - 1, 0))
        if np.array_equal(new, L):
            break
        L = new
    return L, (ox, oy, oz)


def _walk_grid(b: Build, box) -> np.ndarray:
    """t[z,x]: yurunebilir hucrenin basilan yuksekligi (yarim blok: 0 zemin, 1 alt levha, 2 tam blok) ya da -1."""
    x0, y0, z0, x1, y1, z1 = box
    H = y1 - y0 + 1
    ids = b.ids_box(x0, y0 - 1, z0, x1, y0 + 2, z1)
    pal = b.palette
    cache: dict[int, str] = {}

    def c(i: int) -> str:
        if i not in cache:
            cache[i] = "keep" if i == 0 else _cls(b.db, pal[i])
        return cache[i]

    clear = ("none", "keep", "edge")
    nz, nx = z1 - z0 + 1, x1 - x0 + 1
    t = np.full((nz, nx), -1, dtype=np.int8)
    for iz in range(nz):
        for ix in range(nx):
            fl = c(int(ids[0, iz, ix]))
            if fl in ("none", "fluid"):
                continue
            c0 = c(int(ids[1, iz, ix]))
            c1 = c(int(ids[2, iz, ix])) if H >= 2 else "block"
            c2 = c(int(ids[3, iz, ix])) if H >= 3 else "block"
            if c0 in ("none", "keep", "thin", "edge") and c1 in clear:
                t[iz, ix] = 0
            elif c0 == "slab" and c1 in clear and c2 in clear:
                t[iz, ix] = 1
            elif c0 == "full" and c1 in clear and c2 in clear:
                t[iz, ix] = 2
    return t


def _reach(t: np.ndarray, starts) -> np.ndarray:
    nz, nx = t.shape
    seen = np.zeros(t.shape, dtype=bool)
    dq = deque()
    for iz, ix in starts:
        if 0 <= iz < nz and 0 <= ix < nx and t[iz, ix] >= 0 and not seen[iz, ix]:
            seen[iz, ix] = True
            dq.append((iz, ix))
    while dq:
        iz, ix = dq.popleft()
        for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jz, jx = iz + dz, ix + dx
            if 0 <= jz < nz and 0 <= jx < nx and not seen[jz, jx] and t[jz, jx] >= 0 \
                    and abs(int(t[jz, jx]) - int(t[iz, ix])) <= 1:
                seen[jz, jx] = True
                dq.append((jz, jx))
    return seen


def center_cells(box) -> list[tuple[int, int]]:
    """Oda merkezi bolgesi (x,z): geometrik merkeze Chebyshev uzakligi <= r+0.5, r = max(1, min(W,D)//4)."""
    x0, _, z0, x1, _, z1 = box
    r = max(1, min(x1 - x0 + 1, z1 - z0 + 1) // 4)
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    return [(x, z) for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)
            if abs(x - cx) <= r + 0.5 and abs(z - cz) <= r + 0.5]


def _sturdy(b: Build, box, x, y, z, face: str) -> bool:
    i = b.get_id(x, y, z)
    if i == 0:
        x0, y0, z0, x1, y1, z1 = box
        return not (x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1)
    if i == 1:
        return False
    s = b.palette[i].lstrip("!")
    return bool(int(b.db.sturdy[b.db.id(s)]) & blockdb.FACE_BIT[face])


def _center(b: Build, box, x, y, z, face: str) -> bool:
    """Ust/alt yuzde merkez destek (fener, mum, mesale, saksi icin): saglam yuz ya da direk (cit, duvar, parmaklik, zincir)."""
    if _sturdy(b, box, x, y, z, face):
        return True
    i = b.get_id(x, y, z)
    if i <= 1:
        return False
    s = b.palette[i]
    n = _bname(s)
    if n.endswith(("_fence", "_wall", "_bars", "_pane")):
        return True
    if n.endswith("_chain"):
        return "axis=y" in s
    if n == "end_rod" or n.endswith("lightning_rod"):
        return "facing=up" in s or "facing=down" in s
    return False


def _solidish(b: Build, box, x, y, z) -> bool:
    i = b.get_id(x, y, z)
    if i == 0:
        x0, y0, z0, x1, y1, z1 = box
        return not (x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1)
    if i == 1:
        return False
    s = b.palette[i].lstrip("!")
    f = b.db.flags_of(s)
    if f & blockdb.FULL:
        return True
    return int(b.db.sturdy[b.db.id(s)]) != 0


def support_problem(b: Build, box, x, y, z, s: str) -> str | None:
    """Destek kurali ihlali varsa aciklama, yoksa None (fener/mesale/mum/hali/saksi/buton/tabela/kapi/yatak/bitki)."""
    st = s.lstrip("!")
    _, props = split_state(st)
    n = _bname(st)
    db = b.db
    f = db.flags_of(st)

    def get(xx, yy, zz):
        return b.get(xx, yy, zz)

    def nonair_below():
        i = b.get_id(x, y - 1, z)
        if i == 0:
            return not (box[0] <= x <= box[3] and box[1] <= y - 1 <= box[4] and box[2] <= z <= box[5])
        return i > 1 and _bname(b.palette[i]) not in ("water", "lava")

    if n.endswith("_bed"):
        dx, dz = DIRS[props["facing"]]
        part = props["part"]
        ox, oz = (x + dx, z + dz) if part == "foot" else (x - dx, z - dz)
        o = get(ox, y, oz)
        want = "head" if part == "foot" else "foot"
        if _bname(o) != n or f"part={want}" not in o or f"facing={props['facing']}" not in o:
            return "yatagin diger yarimi yok"
        return None
    if n.endswith("_door"):
        if props["half"] == "lower":
            o = get(x, y + 1, z)
            if _bname(o) != n or "half=upper" not in o:
                return "kapinin ust yarimi yok"
            if not _sturdy(b, box, x, y - 1, z, "up"):
                return "kapi alti desteksiz"
        else:
            o = get(x, y - 1, z)
            if _bname(o) != n or "half=lower" not in o:
                return "kapinin alt yarimi yok"
        return None
    if "half" in props and props["half"] in ("upper", "lower") and (f & blockdb.DOUBLE):
        if props["half"] == "lower":
            o = get(x, y + 1, z)
            if _bname(o) != n:
                return "uzun bitkinin ust yarimi yok"
            if _bname(get(x, y - 1, z)) not in DIRTISH:
                return "bitki toprak ustunde degil"
        elif _bname(get(x, y - 1, z)) != n:
            return "uzun bitkinin alt yarimi yok"
        return None
    if n.endswith("_carpet") or n == "moss_carpet":
        return None if nonair_below() else "hali havada"
    if n.endswith("lantern") and n not in ("sea_lantern", "jack_o_lantern"):
        if props.get("hanging") == "true":
            return None if _center(b, box, x, y + 1, z, "down") else "asili fener desteksiz"
        return None if _center(b, box, x, y - 1, z, "up") else "fener desteksiz"
    if n in ("torch", "soul_torch", "copper_torch", "redstone_torch"):
        return None if _center(b, box, x, y - 1, z, "up") else "mesale desteksiz"
    if n.endswith("wall_torch"):
        fac = props["facing"]
        dx, dz = DIRS[fac]
        return None if _sturdy(b, box, x - dx, y, z - dz, fac) else "duvar mesalesi desteksiz"
    if n.endswith("candle"):
        return None if _center(b, box, x, y - 1, z, "up") else "mum desteksiz"
    if n.endswith("pressure_plate"):
        return None if _center(b, box, x, y - 1, z, "up") else "basinc plakasi desteksiz"
    if n == "flower_pot" or n.startswith("potted_"):
        return None if _center(b, box, x, y - 1, z, "up") else "saksi desteksiz"
    if n.endswith("_button") or n in ("lever", "grindstone"):
        face, fac = props.get("face"), props.get("facing")
        if face == "floor":
            return None if _sturdy(b, box, x, y - 1, z, "up") else "zemin baglantisi desteksiz"
        if face == "ceiling":
            return None if _sturdy(b, box, x, y + 1, z, "down") else "tavan baglantisi desteksiz"
        dx, dz = DIRS[fac]
        return None if _sturdy(b, box, x - dx, y, z - dz, fac) else "duvar baglantisi desteksiz"
    if n.endswith(("_wall_sign", "_wall_banner", "_wall_head", "_wall_skull")) or n in ("ladder", "tripwire_hook"):
        fac = props["facing"]
        dx, dz = DIRS[fac]
        return None if _solidish(b, box, x - dx, y, z - dz) else "duvar esyasi desteksiz"
    if n.endswith("_wall_hanging_sign"):
        dx, dz = DIRS[props["facing"]]
        if _solidish(b, box, x - dz, y, z + dx) or _solidish(b, box, x + dz, y, z - dx):
            return None
        return "duvar asma tabelasi desteksiz"
    if n.endswith("_hanging_sign"):
        return None if _center(b, box, x, y + 1, z, "down") else "asma tabela desteksiz"
    if n.endswith("_sign") or n.endswith("_banner"):
        return None if _solidish(b, box, x, y - 1, z) else "tabela/sancak desteksiz"
    if n in ("cave_vines", "cave_vines_plant", "pale_hanging_moss"):
        a = get(x, y + 1, z)
        if _bname(a) in ("cave_vines", "cave_vines_plant", "pale_hanging_moss") or _sturdy(b, box, x, y + 1, z, "down"):
            return None
        return "sarmasik desteksiz"
    if n == "lily_pad":
        return None if _bname(get(x, y - 1, z)) == "water" else "nilufer suda degil"
    if (f & blockdb.PLANT) and n not in ("sea_pickle", "kelp", "kelp_plant", "seagrass", "tall_seagrass", "lily_pad"):
        below = _bname(get(x, y - 1, z))
        if below in DIRTISH or (n in ("azalea", "flowering_azalea") and below == "clay"):
            return None
        return "bitki toprak ustunde degil"
    if f & blockdb.GRAVITY:
        return None if nonair_below() else "yercekimi blogu havada"
    return None


# ====================================================================== oda cercevesi ve yerlestirme
class Room:
    """Bir odayi kanonik cercevede doseme baglami. u: kapidan odak duvarina bakinca soldan saga (0..U-1),
    v: kapi duvarindan odak duvarina (0..V-1), h: zeminden yukseklik (0 = y0). Yon belirtecleri durum dizgisinde:
    @F (odak duvarina dogru), @B (kapiya dogru), @L, @R; eksen @AU/@AV; standing rotation @rF.."""

    _TOK = re.compile(r"@(AU|AV|rF|rB|rL|rR|F|B|L|R)")

    def __init__(self, build: Build, box, kind: str = "oda", style=None, door=None, seed: int = 0,
                 default_style: str = "modern", comfort: int = 7):
        if len(box) != 6:
            raise ValueError("box = (x0, y0, z0, x1, y1, z1) olmali")
        x0, y0, z0, x1, y1, z1 = (int(v) for v in box)
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        z0, z1 = sorted((z0, z1))
        if x1 - x0 < 1 or z1 - z0 < 1 or y1 - y0 < 1:
            raise ValueError("oda kutusu en az 2x2x2 ic hava olmali (x0,y0,z0,x1,y1,z1)")
        self.b = build
        self.db = build.db
        self.box = (x0, y0, z0, x1, y1, z1)
        self.x0, self.y0, self.z0, self.x1, self.y1, self.z1 = self.box
        self.kind = kind
        self.style_name, self.st = resolve_style(style, default_style, self.db)
        self.seed = seed
        self.rng = random.Random(f"{kind}|{seed}")
        self.H = y1 - y0 + 1
        self.top = self.H - 1
        self.comfort = comfort
        self.door_cells, self.door_assumed = self._find_doors(door)
        self._choose_frame()
        self.occ: dict[tuple[int, int, int], str] = {}
        self.outer: dict[tuple[int, int, int], tuple[str, str]] = {}
        self.res: set[tuple[int, int]] = set()
        self.lights: list[dict] = []
        self.items: list[str] = []
        self.notes: list[str] = []
        self.planned = False
        self.hub = (self.cu, self.cv)
        self.min_hang = 2
        self._how = "design"

    # ------------------------------------------------------------------ kapilar / cerceve
    def _near(self, p) -> bool:
        x, y, z = p
        if not (self.y0 - 1 <= y <= self.y1 + 1):
            return False
        inx = self.x0 <= x <= self.x1
        inz = self.z0 <= z <= self.z1
        return (inx and inz) or (inx and z in (self.z0 - 1, self.z1 + 1)) or (inz and x in (self.x0 - 1, self.x1 + 1))

    def _find_doors(self, door):
        cells: list[tuple[int, int, int]] = []
        if door is not None:
            if isinstance(door, dict) or (len(door) == 3 and all(isinstance(c, (int, np.integer)) for c in door)):
                door = [door]
            for d in door:
                p = d.get("pos") if isinstance(d, dict) else d
                if p is not None and len(p) >= 3:
                    cells.append(tuple(int(c) for c in p[:3]))
        else:
            for d in self.b.meta.get("doors", []):
                p = d.get("pos") if isinstance(d, dict) else d
                if p is not None and len(p) >= 3:
                    cells.append(tuple(int(c) for c in p[:3]))
            if not [c for c in cells if self._near(c)]:
                for x, z in self._ring_xz():
                    s = self.b.get(x, self.y0, z)
                    if s not in (KEEP, AIR) and _bname(s).endswith("_door"):
                        cells.append((x, self.y0, z))
        cells = [c for c in cells if self._near(c)]
        if not cells:
            return [((self.x0 + self.x1) // 2, self.y0, self.z0 - 1)], True
        return cells, False

    def _ring_xz(self):
        for x in range(self.x0, self.x1 + 1):
            yield x, self.z0 - 1
            yield x, self.z1 + 1
        for z in range(self.z0, self.z1 + 1):
            yield self.x0 - 1, z
            yield self.x1 + 1, z

    def _choose_frame(self):
        ents = []
        for (x, y, z) in self.door_cells:
            ex, ez = min(max(x, self.x0), self.x1), min(max(z, self.z0), self.z1)
            if x < self.x0:
                side = "west"
            elif x > self.x1:
                side = "east"
            elif z < self.z0:
                side = "north"
            elif z > self.z1:
                side = "south"
            else:
                d = {"north": z - self.z0, "south": self.z1 - z, "west": x - self.x0, "east": self.x1 - x}
                side = min(d, key=d.get)
            if (ex, ez, side) not in ents:
                ents.append((ex, ez, side))
        self.entries_xz = ents
        main = ents[0][2]
        wx, dz = self.x1 - self.x0 + 1, self.z1 - self.z0 + 1
        length = {"north": wx, "south": wx, "west": dz, "east": dz}
        doors_on = {s: sum(1 for e in ents if e[2] == s) for s in DIRS}

        def score(s):
            return (0 if doors_on[s] else 100) + (30 if s == OPP[main] else 0) + 0.5 * length[s] - (50 if s == main else 0)
        focal = max(DIRS, key=score)
        self.focal = focal
        fx, fz = DIRS[focal]
        rx, rz = -fz, fx
        corners = [(x, z) for x in (self.x0, self.x1) for z in (self.z0, self.z1)]
        ox, oz = min(corners, key=lambda c: (c[0] * fx + c[1] * fz, c[0] * rx + c[1] * rz))
        self._o, self._f, self._r = (ox, oz), (fx, fz), (rx, rz)
        self.U = wx if rx != 0 else dz
        self.V = dz if fz != 0 else wx
        self.cu, self.cv = (self.U - 1) // 2, (self.V - 1) // 2
        rn = _dname(rx, rz)
        self.dname = {"F": focal, "B": OPP[focal], "R": rn, "L": OPP[rn]}
        self.axis = {"AU": "x" if rx else "z", "AV": "x" if fx else "z"}
        tok_of = {v: k for k, v in self.dname.items()}
        self.entries = []
        for ex, ez, side in ents:
            u, v = self.uv(ex, ez)
            self.entries.append((u, v, OPPT[tok_of[side]]))

    # ------------------------------------------------------------------ koordinat
    def xz(self, u: int, v: int) -> tuple[int, int]:
        (ox, oz), (fx, fz), (rx, rz) = self._o, self._f, self._r
        return ox + u * rx + v * fx, oz + u * rz + v * fz

    def uv(self, x: int, z: int) -> tuple[int, int]:
        (ox, oz), (fx, fz), (rx, rz) = self._o, self._f, self._r
        dx, dz = x - ox, z - oz
        return dx * rx + dz * rz, dx * fx + dz * fz

    def P(self, u: int, h: int, v: int) -> tuple[int, int, int]:
        x, z = self.xz(u, v)
        return x, self.y0 + h, z

    def inb(self, u, h, v) -> bool:
        return 0 <= u < self.U and 0 <= v < self.V and 0 <= h < self.H

    def in2(self, u, v) -> bool:
        return 0 <= u < self.U and 0 <= v < self.V

    def f(self, s: str) -> str:
        if "@" not in s:
            return s

        def rep(m):
            t = m.group(1)
            if t in ("AU", "AV"):
                return self.axis[t]
            if t[0] == "r":
                return str(ROT16[self.dname[t[1]]])
            return self.dname[t]
        return self._TOK.sub(rep, s)

    def csym(self, total: int, want: int) -> tuple[int, int]:
        """Ortalanmis parca: (baslangic, uzunluk); parite tutmazsa uzunluk 1 kisalir (simetri icin)."""
        want = max(1, min(want, total))
        if (total - want) % 2 and want > 1:
            want -= 1
        return (total - want) // 2, want

    # ------------------------------------------------------------------ malzeme
    def w(self, part: str, wood: str | None = None) -> str:
        return wood_block(wood or self.st["wood"], part)

    def w2(self, part: str) -> str:
        return wood_block(self.st["wood2"], part)

    def sp(self, part: str, stone: str | None = None) -> str:
        return stone_parts(self.db, stone or self.st["stone"])[part]

    def lamp(self, hanging: bool = False, kind: str | None = None) -> str:
        lp = kind or self.st["lamp"]
        if lp == "end_rod":
            return "end_rod[facing=down]" if hanging else "end_rod[facing=up]"
        return f"{lp}[hanging={'true' if hanging else 'false'}]"

    def chain(self, axis: str = "y") -> str:
        return ("waxed_copper_chain" if self.st["metal"] == "copper" else "iron_chain") + f"[axis={axis}]"

    def bars(self) -> str:
        return "waxed_copper_bars" if self.st["metal"] == "copper" else "iron_bars"

    def candle(self, n: int = 3, color: str | None = None) -> str:
        c = self.st["candle"] if color is None else color
        return (f"{c}_candle" if c else "candle") + f"[candles={max(1, min(4, n))},lit=true]"

    def plant_pick(self) -> str:
        return self.rng.choice(tuple(self.st["plants"]))

    # ------------------------------------------------------------------ durum sorgulari
    def _flags(self, s: str) -> int:
        return self.db.flags_of(s.lstrip("!"))

    def cls_at(self, x, y, z) -> str:
        return _cls(self.db, self.b.get(x, y, z))

    def free(self, u, h, v, walk: bool = False) -> bool:
        if not self.inb(u, h, v):
            return False
        x, y, z = self.P(u, h, v)
        if (x, y, z) in self.occ or self.b.get_id(x, y, z) > 1:
            return False
        if not walk and h <= 1 and (x, z) in self.res:
            return False
        return True

    def free_col(self, u, v, h0: int = 0, h1: int = 0, walk: bool = False) -> bool:
        return all(self.free(u, h, v, walk) for h in range(h0, h1 + 1))

    def floor_ok(self, u, v) -> bool:
        x, z = self.xz(u, v)
        i = self.b.get_id(x, self.y0 - 1, z)
        if i == 0:
            return True
        if i == 1:
            return False
        return _bname(self.b.palette[i]) not in ("water", "lava")

    def center_ok(self, x, y, z, face: str) -> bool:
        return _center(self.b, self.box, x, y, z, face)

    def wall_ok(self, u, h, v, W: str) -> bool:
        """(u,v) satir hucresinin W yonundeki duvar hucresi h yuksekliginde saglam, opak duvar mi (pencere/kapi degil)?"""
        du, dv = TV[W]
        if self.in2(u + du, v + dv) or not self.in2(u, v):
            return False
        x, z = self.xz(u + du, v + dv)
        y = self.y0 + h
        if (x, y, z) in self.outer:
            return True
        for (dx_, dy_, dz_) in self.door_cells:
            if (dx_, dz_) == (x, z) and dy_ - 1 <= y <= dy_ + 1:
                return False
        s = self.b.get(x, y, z)
        if s == KEEP:
            return True
        if s == AIR:
            return False
        n = _bname(s)
        return bool(self._flags(s) & blockdb.FULL) and "glass" not in n and "leaves" not in n and not n.endswith("_door")

    def window_at(self, u, h, v, W: str) -> bool:
        du, dv = TV[W]
        if self.in2(u + du, v + dv):
            return False
        x, z = self.xz(u + du, v + dv)
        s = self.b.get(x, self.y0 + h, z)
        n = _bname(s)
        return "glass" in n or n.endswith("_bars")

    # ------------------------------------------------------------------ yol ayirma
    def reserve(self, u, v):
        if self.in2(u, v):
            self.res.add(self.xz(u, v))

    def reserved(self, u, v) -> bool:
        return self.in2(u, v) and self.xz(u, v) in self.res

    def _lpath(self, a, b, tin):
        (u, v), (hu, hv) = a, b
        out = []
        order = ("v", "u") if tin in ("F", "B") else ("u", "v")
        for ax in order:
            if ax == "v":
                while v != hv:
                    v += 1 if hv > v else -1
                    out.append((u, v))
            else:
                while u != hu:
                    u += 1 if hu > u else -1
                    out.append((u, v))
        return out

    def plan(self, hub=None, extra=()):
        """Kapi girislerini ve kapidan merkeze (hub) giden L yolu ayir; esya bu hucrelere (h<=1) konmaz."""
        self.planned = True
        if hub is not None:
            self.hub = (min(max(hub[0], 0), self.U - 1), min(max(hub[1], 0), self.V - 1))
        self.res.clear()
        for (ue, ve, tin) in self.entries:
            self.reserve(ue, ve)
            du, dv = TV[tin]
            self.reserve(ue + du, ve + dv)
            for c in self._lpath((ue, ve), self.hub, tin):
                self.reserve(*c)
        self.reserve(*self.hub)
        for c in extra:
            self.reserve(*c)

    def center_uv(self) -> list[tuple[int, int]]:
        """Merkez bolgesi hucreleri (kanonik), merkeze yakindan uzaga."""
        cells = [self.uv(x, z) for (x, z) in center_cells(self.box)]
        cu, cv = (self.U - 1) / 2, (self.V - 1) / 2
        return sorted(cells, key=lambda c: (abs(c[0] - cu) + abs(c[1] - cv), abs(c[0] - cu), c))

    def plan_around(self, forbid, extra=()) -> bool:
        """Planlanan buyuk esyanin taban hucrelerine (forbid) degmeyen bir merkez hucresi ve kapi yollari sec."""
        forbid = set(forbid)
        for hub in self.center_uv():
            if hub in forbid:
                continue
            paths = []
            for (ue, ve, tin) in self.entries:
                du, dv = TV[tin]
                start = [(ue, ve), (ue + du, ve + dv)]
                ok = None
                for order_tin in (tin, CWT[tin]):
                    p = start + self._lpath((ue, ve), hub, order_tin)
                    if not any(c in forbid for c in p if self.in2(*c)):
                        ok = p
                        break
                if ok is None:
                    break
                paths.append(ok)
            else:
                self.planned = True
                self.hub = hub
                self.res.clear()
                for p in paths:
                    for c in p:
                        self.reserve(*c)
                self.reserve(*hub)
                for c in extra:
                    self.reserve(*c)
                return True
        self.plan(extra=extra)
        return False

    # ------------------------------------------------------------------ yazma
    def _note_light(self, x, y, z, st):
        lv = int(self.db.light[self.db.id(st.lstrip("!"))])
        if lv > 0:
            self.lights.append({"pos": [x, y, z], "block": self.db.canonical(st.lstrip("!")), "level": lv, "how": self._how})

    def put(self, u, h, v, state: str, walk: bool | None = None, force: bool = False) -> bool:
        if not self.inb(u, h, v):
            return False
        if not self.planned:
            self.plan()
        st = self.f(state)
        x, y, z = self.P(u, h, v)
        if not force:
            if (x, y, z) in self.occ or self.b.get_id(x, y, z) > 1:
                return False
            if h <= 1 and (x, z) in self.res:
                if walk is None:
                    walk = _cls(self.db, st) in ("none", "thin")
                if not walk:
                    return False
        self.b.set(x, y, z, st)
        self.occ[(x, y, z)] = st
        self._note_light(x, y, z, st)
        if "_door[" in st and "trapdoor" not in st:  # dolap/dolap kapagi: gecis kapisi degil (denetci bilsin)
            self.b.meta.setdefault("decor_doors", []).append([x, y, z])
        return True

    def puts(self, cells) -> bool:
        """Hepsi-ya-hic: [(u,h,v,state), ...]"""
        cells = list(cells)
        seen = set()
        for (u, h, v, s) in cells:
            if (u, h, v) in seen:
                return False
            seen.add((u, h, v))
            if not self.free(u, h, v, walk=_cls(self.db, self.f(s)) in ("none", "thin")):
                return False
        for c in cells:
            self.put(*c)
        return True

    def remove_xyz(self, x, y, z):
        st = self.occ.pop((x, y, z), None)
        if st is None:
            return
        self.b.set(x, y, z, AIR)
        self.lights = [l for l in self.lights if tuple(l["pos"]) != (x, y, z)]
        n = _bname(st)
        _, props = split_state(st.lstrip("!"))
        partner = None
        if n.endswith("_bed"):
            dx, dz = DIRS[props["facing"]]
            partner = (x + dx, y, z + dz) if props["part"] == "foot" else (x - dx, y, z - dz)
        elif props.get("half") in ("upper", "lower"):
            partner = (x, y + 1, z) if props["half"] == "lower" else (x, y - 1, z)
        if partner and partner in self.occ:
            self.remove_xyz(*partner)
        # ustundeki destege bagli esya
        above = (x, y + 1, z)
        if above in self.occ and _cls(self.db, self.occ[above]) != "full":
            if support_problem(self.b, self.box, *above, self.occ[above]):
                self.remove_xyz(*above)

    def _outer_ok(self, x, y, z) -> bool:
        s = self.b.get(x, y, z)
        if s == KEEP:
            return True
        if s == AIR:
            return False
        st = s.lstrip("!")
        f = self._flags(st)
        n = _bname(st)
        if not (f & blockdb.FULL) or (f & (blockdb.FLUID | blockdb.BLOCK_ENTITY)):
            return False
        if "glass" in n or "leaves" in n or n.endswith("_door") or n == "barrier":
            return False
        return int(self.db.light[self.db.id(st)]) == 0

    def _put_outer(self, x, y, z, state: str) -> bool:
        st = self.f(state)
        if not (self._flags(st) & blockdb.FULL):
            return False
        if (x, y, z) in self.outer or not self._outer_ok(x, y, z):
            return False
        self.outer[(x, y, z)] = (self.b.get(x, y, z), st)
        self.b.set(x, y, z, st)
        self._note_light(x, y, z, st)
        return True

    def put_ceiling(self, u, v, state: str) -> bool:
        """Tavan katmanina (y1+1) gomulu tam blok (gizli isik)."""
        if not self.in2(u, v):
            return False
        x, z = self.xz(u, v)
        return self._put_outer(x, self.y1 + 1, z, state)

    def put_floor(self, u, v, state: str) -> bool:
        """Zemin katmanina (y0-1) gomulu tam blok (gizli isik)."""
        if not self.in2(u, v):
            return False
        x, z = self.xz(u, v)
        return self._put_outer(x, self.y0 - 1, z, state)

    def put_wallcell(self, u, h, v, W: str, state: str) -> bool:
        """(u,v) satir hucresinin W yonundeki duvar hucresine (h) gomulu tam blok."""
        du, dv = TV[W]
        if not self.in2(u, v) or self.in2(u + du, v + dv) or not (0 <= h < self.H):
            return False
        if not self.wall_ok(u, h, v, W):
            return False
        x, z = self.xz(u + du, v + dv)
        return self._put_outer(x, self.y0 + h, z, state)

    # ------------------------------------------------------------------ duvar satirlari
    def wall_row(self, W: str) -> list[tuple[int, int]]:
        if W == "F":
            return [(u, self.V - 1) for u in range(self.U)]
        if W == "B":
            return [(u, 0) for u in range(self.U)]
        if W == "L":
            return [(0, v) for v in range(self.V)]
        return [(self.U - 1, v) for v in range(self.V)]

    def runs(self, W: str, h0: int = 0, h1: int = 0, backed: bool = True, cells=None) -> list[list[tuple[int, int]]]:
        cells = cells if cells is not None else self.wall_row(W)
        out, cur = [], []
        for (u, v) in cells:
            ok = self.free_col(u, v, h0, h1) and (not backed or all(self.wall_ok(u, h, v, W) for h in range(h0, h1 + 1)))
            if ok:
                cur.append((u, v))
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out

    def pick(self, W: str, length: int, h0: int = 0, h1: int = 0, backed: bool = True, min_len: int | None = None,
             cells=None, center: float | None = None) -> list[tuple[int, int]]:
        """W duvari boyunca serbest, (istege bagli) duvarla desteklenmis, merkeze en yakin `length` hucre."""
        row = cells if cells is not None else self.wall_row(W)
        c = (len(row) - 1) / 2 if center is None else center
        idx = {cell: i for i, cell in enumerate(row)}
        best, bkey = [], None
        for r in self.runs(W, h0, h1, backed, cells=row):
            n = min(length, len(r))
            if n < (min_len if min_len is not None else length):
                continue
            for s in range(0, len(r) - n + 1):
                seg = r[s:s + n]
                mid = (idx[seg[0]] + idx[seg[-1]]) / 2
                key = (-n, abs(mid - c), idx[seg[0]])
                if bkey is None or key < bkey:
                    best, bkey = seg, key
        return best

    # ------------------------------------------------------------------ esya parcalari
    def chair(self, u, v, face: str, mat: str | None = None, arms: str | None = None) -> bool:
        """Sandalye/koltuk: merdiven; `face` oturanin baktigi yon. arms: 'trapdoor' | 'sign' | None."""
        mat = mat or self.w("stairs")
        if not self.put(u, 0, v, f"{mat}[facing=@{OPPT[face]}]"):
            return False
        self.items.append("chair")
        if arms:
            for side in PERP[face]:
                du, dv = TV[side]
                self._arm(u + du, v + dv, side, arms)
        return True

    def _arm(self, u, v, side: str, kind: str) -> bool:
        if kind == "sign":
            return self.put(u, 0, v, f"{self.w('wall_sign')}[facing=@{side}]", walk=False)
        return self.put(u, 0, v, f"{self.w('trapdoor')}[facing=@{side},open=true]", walk=False)

    def sofa(self, cells, face: str, color: str | None = None, arms=(True, True), mat: str | None = None,
             arm_kind: str = "trapdoor") -> list:
        """Kanepe: kumas (yun) merdiven sirasi; `face` oturanlarin baktigi yon; uclarda kapak kol."""
        mat = mat or f"{color or self.st['fabric']}_wool_stairs"
        back = OPPT[face]
        placed = [(u, v) for (u, v) in cells if self.put(u, 0, v, f"{mat}[facing=@{back}]")]
        if not placed:
            return []
        self.items.append("sofa")
        if len(placed) > 1:
            du, dv = placed[-1][0] - placed[0][0], placed[-1][1] - placed[0][1]
            du, dv = (du > 0) - (du < 0), (dv > 0) - (dv < 0)
            tok = {v_: k for k, v_ in TV.items()}[(du, dv)]
        else:
            tok = PERP[face][1]
        if arms and arms[0]:
            u, v = placed[0]
            self._arm(u - TV[tok][0], v - TV[tok][1], OPPT[tok], arm_kind)
        if arms and arms[1]:
            u, v = placed[-1]
            self._arm(u + TV[tok][0], v + TV[tok][1], tok, arm_kind)
        return placed

    def table(self, cells, kind: str = "slab", wood: str | None = None, stone: str | None = None) -> list:
        """Masa ustu: 'slab' (ust yarim levha), 'trapdoor' (ince ust kapak), 'stone' (tas levha), 'block'."""
        out = []
        for (u, v) in cells:
            if kind == "trapdoor":
                s = wood_block(wood or self.st["wood2"], "trapdoor") + "[half=top,facing=@F]"
            elif kind == "stone":
                s = self.sp("slab", stone) + "[type=top]"
            elif kind == "block":
                s = wood_block(wood or self.st["wood"], "planks")
            else:
                s = wood_block(wood or self.st["wood"], "slab") + "[type=top]"
            if self.put(u, 0, v, s):
                out.append((u, v))
        if out:
            self.items.append("table")
        return out

    def pedestal(self, u, v, top: str = "plate", wood: str | None = None) -> bool:
        """Tek ayakli masa: cit + ustunde basinc plakasi / hali / fener / mum."""
        wd = wood or self.st["wood"]
        if not (self.free(u, 0, v) and self.free(u, 1, v)):
            return False
        self.put(u, 0, v, wood_block(wd, "fence"))
        if top == "plate":
            self.put(u, 1, v, wood_block(wd, "pressure_plate"))
        elif top == "lamp":
            self.put(u, 1, v, self.lamp(False))
        elif top == "candle":
            self.put(u, 1, v, self.candle(self.rng.randint(1, 3)))
        elif top.endswith("_carpet"):
            self.put(u, 1, v, top)
        self.items.append("table")
        return True

    def bed(self, u, v, d: str, color: str | None = None) -> bool:
        """Yatak: ayak ucu (u,v), bas (u,v)+d; facing = ayaktan basa."""
        du, dv = TV[d]
        hu, hv = u + du, v + dv
        if not (self.free(u, 0, v) and self.free(hu, 0, hv)):
            return False
        c = color or self.st["bed"]
        self.put(u, 0, v, f"{c}_bed[facing=@{d},part=foot]")
        self.put(hu, 0, hv, f"{c}_bed[facing=@{d},part=head]")
        self.items.append("bed")
        return True

    def rug(self, u0, v0, u1, v1, fill: str | None = None, border: str | None = None, pattern: str | None = None,
            accent: str | None = None):
        """Hali: dikdortgen; pattern: None | 'checker' | 'kilim' | 'stripes_u' | 'stripes_v' | 'center'."""
        fill = fill or self.st["rug"]
        ua, ub = sorted((u0, u1))
        va, vb = sorted((v0, v1))
        cu_, cv_ = (ua + ub) / 2, (va + vb) / 2
        n = 0
        for u in range(ua, ub + 1):
            for v in range(va, vb + 1):
                if not self.in2(u, v) or not self.free(u, 0, v, walk=True) or not self.floor_ok(u, v):
                    continue
                edge = border is not None and (u in (ua, ub) or v in (va, vb))
                c = border if edge else fill
                if not edge and accent:
                    if pattern == "checker" and (u + v) % 2:
                        c = accent
                    elif pattern == "kilim":
                        d = int(abs(u - cu_) + abs(v - cv_))
                        c = accent if d % 3 == 0 else fill
                    elif pattern == "stripes_u" and (u - ua) % 2:
                        c = accent
                    elif pattern == "stripes_v" and (v - va) % 2:
                        c = accent
                    elif pattern == "center" and abs(u - cu_) <= 0.5 and abs(v - cv_) <= 0.5:
                        c = accent
                if self.put(u, 0, v, f"{c}_carpet", walk=True):
                    n += 1
        if n:
            self.items.append("rug")
        return n

    def plant(self, u, h, v, kind: str | None = None) -> bool:
        """Saksi bitkisi: alttaki blogun ust merkezi destekli olmali (masa, tezgah, raf...)."""
        if not self.free(u, h, v):
            return False
        x, y, z = self.P(u, h, v)
        if h == 0 and not self.floor_ok(u, v):
            return False
        if h > 0 and not self.center_ok(x, y - 1, z, "up"):
            return False
        ok = self.put(u, h, v, kind or self.plant_pick())
        if ok:
            self.items.append("plant")
        return ok

    def big_plant(self, u, v, leaves: str | None = None, pot: str | None = None) -> bool:
        """Yer bitkisi: saksi + ustunde kalici yaprak (iki blok)."""
        if self.top < 1 or not (self.free(u, 0, v) and self.free(u, 1, v)) or not self.floor_ok(u, v):
            return False
        pot = pot or self.rng.choice(("potted_azalea_bush", "potted_fern", "potted_oak_sapling", "potted_flowering_azalea_bush"))
        self.put(u, 0, v, pot)
        self.put(u, 1, v, f"{leaves or self.st['leaves']}[persistent=true]")
        self.items.append("plant")
        return True

    def floor_lamp(self, u, v, kind: str | None = None) -> bool:
        """Lambader: cit + fener (ya da fütüristik: iki end rod)."""
        if self.top < 1 or not (self.free(u, 0, v) and self.free(u, 1, v)) or not self.floor_ok(u, v):
            return False
        if (kind or self.st["lamp"]) == "end_rod":
            self.put(u, 0, v, "end_rod[facing=up]")
            self.put(u, 1, v, "end_rod[facing=up]")
        else:
            self.put(u, 0, v, self.w2("fence"))
            self.put(u, 1, v, self.lamp(False, kind if kind != "end_rod" else None))
        self.items.append("floor_lamp")
        return True

    def lamp_on(self, u, h, v, kind: str = "lamp") -> bool:
        """Esya ustune fener ya da mum ('lamp' | 'candle')."""
        if not self.free(u, h, v) or h < 1:
            return False
        x, y, z = self.P(u, h, v)
        if not self.center_ok(x, y - 1, z, "up"):
            return False
        s = self.candle(self.rng.randint(2, 4)) if kind == "candle" else self.lamp(False)
        if s.startswith("end_rod"):
            s = self.candle(3)
        return self.put(u, h, v, s)

    def hang(self, u, v, drop: int | None = None, lamp: str | None = None, h_min: int = 2) -> bool:
        """Tavandan asili fener (yuksek tavanda zincirle iner); en alt nokta h>=h_min (bas boslugu)."""
        h_min = max(h_min, self.min_hang)
        if self.top < h_min or not self.in2(u, v):
            return False
        x, z = self.xz(u, v)
        if not self.center_ok(x, self.y1 + 1, z, "down"):
            return False
        lp = lamp or self.lamp(True)
        if lp.startswith("end_rod"):
            return self.put(u, self.top, v, "end_rod[facing=down]", walk=True)
        if drop is None:
            drop = max(0, min(self.H - 4, 3))
        hl = max(h_min, self.top - drop)
        cells = [(u, h, v, self.chain()) for h in range(self.top, hl, -1)] + [(u, hl, v, lp)]
        if not all(self.free(cu, ch, cv, walk=True) for (cu, ch, cv, _) in cells):
            return False
        for c in cells:
            self.put(*c, walk=True)
        self.items.append("pendant")
        return True

    def chandelier(self, u, v, size: int = 1, arm: str | None = None, candles: bool = False) -> bool:
        """Avize: tavana bagli cit hacı (size 1) ya da 3x3 halka (size 2), kollarin altinda asili fenerler.
        Alcak tavanda (top<3) tek asili fenere duser."""
        if self.top < 3:
            return self.hang(u, v)
        x, z = self.xz(u, v)
        if not self.center_ok(x, self.y1 + 1, z, "down"):
            return False
        drop = max(0, min(self.H - 5, 3))
        fl = self.top - drop
        if fl - 1 < max(2, self.min_hang):
            return self.hang(u, v)
        arm = arm or self.w2("fence")
        cells = [(u, h, v, self.chain()) for h in range(self.top, fl, -1)]
        if size >= 2:
            ring = [(u + a, v + c) for a in (-1, 0, 1) for c in (-1, 0, 1)]
            hangs = [(u + a, v + c) for a in (-1, 1) for c in (-1, 1)] + [(u, v)]
            tops = [(u + a, v + c) for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        else:
            ring = [(u, v)] + [(u + a, v + c) for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            hangs = [(u + a, v + c) for a, c in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            tops = []
        ring = [c for c in ring if self.in2(*c)]
        hangs = [c for c in hangs if self.in2(*c)]
        cells += [(a, fl, c, arm) for (a, c) in ring]
        cells += [(a, fl - 1, c, self.lamp(True)) for (a, c) in hangs]
        if candles and drop >= 1:
            cells += [(a, fl + 1, c, self.candle(3)) for (a, c) in tops if self.in2(a, c)]
        if not self.puts(cells):
            return self.hang(u, v)
        self.items.append("chandelier")
        return True

    def flush_ceiling(self, u, v, light: str | None = None) -> bool:
        if not self.in2(u, v):
            return False
        x, z = self.xz(u, v)
        if self.b.get_id(x, self.y1, z) > 1 and _cls(self.db, self.b.get(x, self.y1, z)) in ("full", "block"):
            return False
        return self.put_ceiling(u, v, light or self.st["flush"])

    def ceiling_grid(self, step: int = 4, light: str | None = None) -> int:
        n = 0
        for u in _grid(self.U, step):
            for v in _grid(self.V, step):
                n += bool(self.flush_ceiling(u, v, light))
        return n

    def pendant_grid(self, step: int = 4, skip_center: bool = False) -> int:
        n = 0
        for u in _grid(self.U, step):
            for v in _grid(self.V, step):
                if skip_center and abs(u - self.cu) <= 1 and abs(v - self.cv) <= 1:
                    continue
                n += bool(self.hang(u, v))
        return n

    def sconce(self, u, v, W: str, h: int | None = None, kind: str | None = None) -> bool:
        """Duvar apligi: W duvarina (satir hucresi u,v). kind: torch | soul | copper | rod | lantern | flush."""
        kind = kind or self.st["sconce"]
        if h is None:
            h = 2 if self.top >= 3 else 1
        h = min(h, self.top)
        if not self.wall_ok(u, h, v, W):
            return False
        out = OPPT[W]
        if kind == "flush":
            return self.put_wallcell(u, h, v, W, self.st["flush"])
        if kind == "rod":
            return self.put(u, h, v, f"end_rod[facing=@{out}]", walk=h >= 2)
        if kind == "lantern" and h >= 2 and self.free(u, h, v, walk=True) and self.free(u, h - 1, v) \
                and self.wall_ok(u, h - 1, v, W):
            return self.puts([(u, h, v, self.w2("fence")), (u, h - 1, v, self.lamp(True))])
        torch = {"soul": "soul_wall_torch", "copper": "copper_wall_torch"}.get(kind, "wall_torch")
        return self.put(u, h, v, f"{torch}[facing=@{out}]", walk=True)

    def sconces(self, W: str, step: int = 4, kind: str | None = None, h: int | None = None, skip_ends: int = 1) -> int:
        row = self.wall_row(W)
        n = 0
        idx = [i for i in _grid(len(row), step) if skip_ends <= i < len(row) - skip_ends] or [len(row) // 2]
        for i in idx:
            u, v = row[i]
            n += bool(self.sconce(u, v, W, h=h, kind=kind))
        return n

    def chiseled(self, face: str) -> str:
        bits = ",".join(f"slot_{i}_occupied={'true' if self.rng.random() < 0.7 else 'false'}" for i in range(6))
        return f"chiseled_bookshelf[facing=@{face},{bits}]"

    def bookcase(self, cells, W: str, h0: int = 0, h1: int | None = None, chiseled: float = 0.25,
                 post_every: int = 0, post: str | None = None) -> int:
        """Duvar boyu kitaplik (tavana kadar); arada oyma kitaplik; istege bagli kutuk direkler."""
        h1 = self.top if h1 is None else min(h1, self.top)
        face = OPPT[W]
        n = 0
        for i, (u, v) in enumerate(cells):
            for h in range(h0, h1 + 1):
                if not self.wall_ok(u, h, v, W):
                    continue
                if post_every and i % post_every == 0:
                    s = post or self.w2("log") + "[axis=y]"
                elif h == 1 and self.rng.random() < chiseled:
                    s = self.chiseled(face)
                elif h != 1 and self.rng.random() < chiseled * 0.5:
                    s = self.chiseled(face)
                else:
                    s = "bookshelf"
                n += bool(self.put(u, h, v, s))
        if n:
            self.items.append("bookcase")
        return n

    def wardrobe(self, cells, W: str, wood: str | None = None) -> bool:
        """Gomme dolap: iki ucta govde blogu, arada cift kanatli kapi (kapak odaya bakar), ustte korniş."""
        wd = wood or self.st["wood2"]
        if len(cells) < 3 or self.top < 1:
            return False
        if not all(self.free_col(u, v, 0, 1) and self.wall_ok(u, 0, v, W) for (u, v) in cells):
            return False
        body = wood_block(wd, "planks")
        door = wood_block(wd, "door")
        inner = cells[1:-1][:2]
        for (u, v) in (cells[0], cells[-1]):
            self.put(u, 0, v, body)
            self.put(u, 1, v, body)
        for i, (u, v) in enumerate(inner):
            hinge = "left" if i == 0 else "right"
            if len(inner) == 1:
                hinge = "left"
            self.put(u, 0, v, f"{door}[facing=@{W},half=lower,hinge={hinge},open=false]")
            self.put(u, 1, v, f"{door}[facing=@{W},half=upper,hinge={hinge},open=false]")
        for (u, v) in cells[len(inner) + 1:-1]:
            self.put(u, 0, v, body)
            self.put(u, 1, v, body)
        if self.top >= 2:
            for (u, v) in cells:
                self.put(u, 2, v, wood_block(wd, "slab") + "[type=bottom]")
        self.items.append("wardrobe")
        return True

    def sideboard(self, cells, W: str, kinds=None, deco: bool = True) -> int:
        """Alcak dolap/konsol sirasi (h=0) + ustunde saksi/fener/mum."""
        face = OPPT[W]
        kinds = kinds or ("chiseled", "barrel", "planks")
        n = 0
        placed = []
        for i, (u, v) in enumerate(cells):
            k = kinds[i % len(kinds)]
            if k == "chiseled":
                s = self.chiseled(face)
            elif k == "barrel":
                s = f"barrel[facing=@{face}]"
            elif k == "planks":
                s = self.w2("planks")
            elif k == "slab":
                s = self.w2("slab") + "[type=top]"
            else:
                s = k
            if self.put(u, 0, v, s):
                n += 1
                placed.append((u, v))
        if deco and placed:
            for i, (u, v) in enumerate(placed):
                if i == len(placed) // 2 and len(placed) >= 3:
                    self.lamp_on(u, 1, v, "candle" if self.st["lamp"] == "end_rod" else "lamp")
                elif i % 2 == 0:
                    self.plant(u, 1, v)
        if n:
            self.items.append("sideboard")
        return n

    def nook(self, corner: str = "BL", mat: str | None = None) -> bool:
        """Kose oturma kosesi: duvar boyunca berjer (kollu), koseye lambader, yanina sehpa+saksi.
        corner: B/F (kapi/odak duvari) + L/R; ornek 'BL' = kapi duvarinin sol kosesi."""
        uu = 0 if corner[1] == "L" else self.U - 1
        vv = 0 if corner[0] == "B" else self.V - 1
        dv = 1 if vv == 0 else -1
        face = "R" if uu == 0 else "L"
        chair = (uu, vv + dv)
        side = (uu, vv + 2 * dv)
        if not (self.free(*chair[:1], 0, chair[1]) and self.free(uu, 0, vv)):
            return False
        if not self.chair(chair[0], chair[1], face, mat=mat or f"{self.st['fabric']}_wool_stairs"):
            return False
        self.floor_lamp(uu, vv)
        if self.table([side], "slab"):
            self.plant(side[0], 1, side[1])
        return True

    def std_lights(self, focus=None, step: int = 4) -> None:
        """Stile gore ana aydinlatma: modern/futuristik/iskandinav tavana gomme izgara; diger stiller odakta avize."""
        fu, fv = focus if focus is not None else (self.cu, self.cv)
        order = self.st.get("light_order", ())
        first = order[0] if order else "hang"
        if first == "flush":
            self.ceiling_grid(step)
        elif first == "screen":
            for u in _grid(self.U, step):
                for v in _grid(self.V, step):
                    self._try_light("screen", u, v)
        else:
            if not self.chandelier(fu, fv, size=2 if (self.U >= 9 and self.V >= 9 and self.top >= 4) else 1):
                self.hang(fu, fv)
            if self.U >= 9 or self.V >= 9:
                for u in _grid(self.U, 5):
                    for v in _grid(self.V, 5):
                        if abs(u - fu) + abs(v - fv) >= 4:
                            self.hang(u, v)

    def column(self, u, v, block: str, h0: int = 0, h1: int | None = None) -> bool:
        h1 = self.top if h1 is None else h1
        if not all(self.free(u, h, v) for h in range(h0, h1 + 1)):
            return False
        for h in range(h0, h1 + 1):
            self.put(u, h, v, block)
        self.items.append("column")
        return True

    def banner(self, u, h, v, W: str, color: str) -> bool:
        if not self.wall_ok(u, h, v, W):
            return False
        return self.put(u, h, v, f"{color}_wall_banner[facing=@{OPPT[W]}]", walk=True)

    def chest_pair(self, a, b, face: str) -> bool:
        """Cift sandik: a,b komsu hucreler, ikisi de `face` yonune bakar."""
        da = (b[0] - a[0], b[1] - a[1])
        tok = {v_: k for k, v_ in TV.items()}[da]
        ta = "left" if tok == CWT[face] else "right"
        tb = "right" if ta == "left" else "left"
        return self.puts([(a[0], 0, a[1], f"chest[facing=@{face},type={ta}]"),
                          (b[0], 0, b[1], f"chest[facing=@{face},type={tb}]")])

    def fireplace(self, W: str, t: int | None = None, width: int = 3, stone: str | None = None) -> bool:
        """Duvara dayali ocak: tas govde, ortada yanan kamp atesi, ustte davlumbaz (W duvari, t: satir indeksi)."""
        row = self.wall_row(W)
        if len(row) < width:
            return False
        t = (len(row) - 1) // 2 if t is None else t
        s0 = max(0, min(len(row) - width, t - width // 2))
        seg = row[s0:s0 + width]
        if not all(self.free_col(u, v, 0, min(self.top, 2)) and self.wall_ok(u, 0, v, W) for (u, v) in seg):
            return False
        sp = stone_parts(self.db, stone or "bricks")
        out = OPPT[W]
        mid = seg[width // 2]
        for (u, v) in seg:
            if (u, v) == mid:
                self.put(u, 0, v, f"campfire[facing=@{out},lit=true]")
                if self.top >= 1:
                    self.put(u, 1, v, sp["block"])
            else:
                self.put(u, 0, v, sp["block"])
                if self.top >= 1:
                    self.put(u, 1, v, sp["block"])
            for h in range(2, self.top + 1):
                self.put(u, h, v, sp["block"])
        # ocak ustu (rafa mum/saksi) -- duvardan bir hucre ileride
        mu, mv = mid
        fu, fv = mu + TV[out][0], mv + TV[out][1]
        if self.top >= 2:
            for (u, v) in seg:
                a, c = u + TV[out][0], v + TV[out][1]
                if self.free(a, 2, c, walk=True):
                    self.put(a, 2, c, f"{sp['stairs']}[facing=@{W},half=top]", walk=True)
        self.items.append("fireplace")
        return True

    # ------------------------------------------------------------------ bitirme
    def _validate(self, remove: bool = True) -> list[str]:
        probs = []
        for _ in range(6):
            bad = [(p, s) for p, s in self.occ.items() if support_problem(self.b, self.box, *p, s)]
            if not bad:
                break
            for p, s in bad:
                probs.append(f"{_bname(s)}@{p}: {support_problem(self.b, self.box, *p, s)}")
                if remove:
                    self.remove_xyz(*p)
            if not remove:
                break
        return probs

    def path_ok(self) -> list[bool]:
        t = _walk_grid(self.b, self.box)
        cen = center_cells(self.box)
        out = []
        for (ex, ez, _) in self.entries_xz:
            seen = _reach(t, [(ez - self.z0, ex - self.x0)])
            out.append(bool(seen[ez - self.z0, ex - self.x0]) and any(seen[z - self.z0, x - self.x0] for x, z in cen))
        return out

    def _ensure_paths(self):
        ok = self.path_ok()
        if all(ok):
            return
        for (ue, ve, tin), good in zip(self.entries, ok):
            if good:
                continue
            path = [(ue, ve)] + self._lpath((ue, ve), self.hub, tin)
            for (u, v) in path:
                for h in range(0, min(3, self.H)):
                    p = self.P(u, h, v)
                    if p in self.occ and _cls(self.db, self.occ[p]) not in ("none", "thin", "edge"):
                        self.remove_xyz(*p)
        if not all(self.path_ok()):
            self.notes.append("kapi-merkez yolu tam acilamadi (onceden var olan engel?)")

    def _targets(self, L, org, skip):
        """Karanlik hedefler: (oncelik, x, y, z); spawn icin isik<1, yurunen zeminde isik<comfort."""
        ox, oy, oz = org
        x0, y0, z0, x1, y1, z1 = self.box
        b = self.b
        db = self.db
        ids = b.ids_box(x0, y0 - 1, z0, x1, y1, z1)
        pal = b.palette
        cache: dict[int, tuple] = {}

        def info(i):
            if i not in cache:
                if i == 0:
                    cache[i] = ("keep", False, False)
                else:
                    s = pal[i].lstrip("!")
                    sid = db.id(s)
                    n = _bname(s)
                    up = bool(int(db.sturdy[sid]) & blockdb.FACE_BIT["up"]) and int(db.light[sid]) < 14 \
                        and "glass" not in n and "leaves" not in n and n not in ("barrier",)
                    sig = n.endswith(_SIGNAL) or n in _SIGNAL
                    cache[i] = (_cls(db, s), up, sig)
            return cache[i]
        out = []
        for iy in range(1, y1 - y0 + 2):
            for iz in range(z1 - z0 + 1):
                for ix in range(x1 - x0 + 1):
                    c, _, sig = info(int(ids[iy, iz, ix]))
                    if c not in ("none", "keep", "edge") or sig:
                        continue
                    bi = int(ids[iy - 1, iz, ix])
                    if bi == 0:
                        spawn_floor = iy - 1 == 0
                    else:
                        spawn_floor = info(bi)[1]
                    if not spawn_floor:
                        continue
                    x, y, z = x0 + ix, y0 + iy - 1, z0 + iz
                    if (x, z) in skip:
                        continue
                    if L[y - oy, z - oz, x - ox] < 1:
                        out.append((100, x, y, z))
        t = _walk_grid(b, self.box)
        for iz in range(t.shape[0]):
            for ix in range(t.shape[1]):
                tv = int(t[iz, ix])
                if tv < 0:
                    continue
                x, z = x0 + ix, z0 + iz
                if (x, z) in skip:
                    continue
                y = y0 if tv == 0 else y0 + 1
                lv = int(L[y - oy, z - oz, x - ox])
                if lv < self.comfort:
                    out.append((self.comfort - lv, x, y, z))
        out.sort(key=lambda r: (-r[0], r[2], r[3], r[1]))
        return out

    def _fill_light(self):
        skip: set[tuple[int, int]] = set()
        order = list(self.st.get("light_order", ())) + ["hang", "flush", "floor", "top", "wall", "wallflush"]
        seen_o = []
        for o in order:
            if o not in seen_o:
                seen_o.append(o)
        for _ in range(90):
            L, org = light_map(self.b, self.box)
            tg = self._targets(L, org, skip)
            if not tg:
                return
            _, x, y, z = tg[0]
            if not self._add_light(x, z, seen_o):
                skip.add((x, z))

    def _add_light(self, x, z, order) -> bool:
        u0, v0 = self.uv(x, z)
        for rad in (1, 2, 3, 5):
            cand = sorted(((u, v) for u in range(u0 - rad, u0 + rad + 1) for v in range(v0 - rad, v0 + rad + 1)
                           if self.in2(u, v)), key=lambda c: (abs(c[0] - u0) + abs(c[1] - v0), c))
            for how in order:
                for (u, v) in cand:
                    if self._try_light(how, u, v):
                        return True
        return False

    def _try_light(self, how: str, u, v) -> bool:
        if how == "flush":
            return self.flush_ceiling(u, v)
        if how == "screen":
            if not self.flush_ceiling(u, v):
                return False
            if self.top >= 2:
                self.put(u, self.top, v, f"{self.w('trapdoor', 'birch')}[half=top,facing=@F]", walk=True)
            return True
        if how == "hang":
            return self.hang(u, v)
        if how == "floor":
            x, z = self.xz(u, v)
            p = (x, self.y0, z)
            cur = self.occ.get(p)
            if cur is None and not self.free(u, 0, v, walk=True):
                return False
            if cur is not None and not _bname(cur).endswith("_carpet"):
                return False
            if not self.put_floor(u, v, self.st["flush"]):
                return False
            if cur is None:
                self.put(u, 0, v, f"{self.st['rug2']}_carpet", walk=True)
            return True
        if how == "top":
            for h in (1, 2):
                if h > self.top:
                    break
                x, y, z = self.P(u, h, v)
                below = self.occ.get((x, y - 1, z))
                if below is None or _bname(below).endswith(("_bed", "_carpet")):
                    continue
                if self.lamp_on(u, h, v, "candle" if self.st["lamp"] == "end_rod" else "lamp"):
                    return True
            return False
        if how == "wall":
            for W in ("F", "B", "L", "R"):
                du, dv = TV[W]
                if self.in2(u + du, v + dv):
                    continue
                if self.sconce(u, v, W):
                    return True
            return False
        if how == "wallflush":
            for W in ("F", "B", "L", "R"):
                for h in (min(2, self.top), 1):
                    if self.put_wallcell(u, h, v, W, self.st["flush"]):
                        return True
            return False
        return False

    def finish(self) -> dict:
        if not self.planned:
            self.plan()
        self._how = "fix"
        self._validate(remove=True)
        self._ensure_paths()
        self._how = "fill"
        self._fill_light()
        self._validate(remove=True)
        return self._record()

    def _record(self) -> dict:
        rec = {"name": self.kind, "kind": self.kind, "box": list(self.box), "recipe": f"furnish_{self.kind}",
               "style": self.style_name, "seed": self.seed, "doors": [list(c) for c in self.door_cells],
               "door_assumed": self.door_assumed, "focal_wall": self.focal, "lights": len(self.lights),
               "furniture": sorted(set(self.items)), "notes": list(self.notes)}
        rooms = self.b.meta.setdefault("rooms", [])
        for r in rooms:
            if isinstance(r, dict) and list(r.get("box", [])) == list(self.box):
                nm = r.get("name")
                r.update(rec)
                if nm:
                    r["name"] = nm
                rec = r
                break
        else:
            rooms.append(rec)
        lights = self.b.meta.setdefault("lights", [])
        for l in self.lights:
            lights.append(dict(l, room=rec["name"]))
        return rec


def _grid(n: int, step: int) -> list[int]:
    """1..n-2 araliginda ortalanmis, `step` aralikli konumlar (kucuk odada orta)."""
    if n <= 2:
        return [n // 2]
    off = 1 + ((n - 3) % step) // 2
    out = list(range(off, n - 1, step))
    return out or [(n - 1) // 2]


# ====================================================================== recete kaydi
_RECIPES: dict[str, dict] = {}


def _recipe(kind: str, tr: str, style: str, comfort: int = 7, words=(), shell=None):
    def deco(fn):
        _RECIPES[kind] = {"fn": fn, "style": style, "comfort": comfort, "tr": tr, "words": tuple(words),
                          "shell": shell or ("spruce_planks", "white_terracotta", "spruce_planks")}
        return fn
    return deco


def _side_walls(R: Room):
    """Iki yan duvar (L, R) -- kapisiz/pencere az olan once."""
    def score(W):
        row = R.wall_row(W)
        return sum(R.wall_ok(u, 1, v, W) for (u, v) in row) - 3 * sum(R.reserved(u, v) for (u, v) in row)
    return sorted(("L", "R"), key=lambda W: -score(W))


def _counter_cell(R: Room, u, v, W: str, kind: str, upper: bool = True):
    """Mutfak tezgahi hucresi (W duvarina dayali): cab | sink | stove | oven | dish | fridge | corner | pantry."""
    out = OPPT[W]
    fu, fv = u + TV[out][0], v + TV[out][1]
    base = R.sp("block", R.st["counter"]) if R.st["counter"] not in WOODS and not R.st["counter"].endswith("_planks") \
        else R.st["counter"]
    front = R.w2("trapdoor") + f"[facing=@{out},open=true,half=bottom]"
    top = R.top
    if kind == "fridge":
        if not R.free_col(u, v, 0, min(1, top)):
            return False
        R.put(u, 0, v, "iron_block")
        if top >= 1:
            R.put(u, 1, v, "iron_block")
            R.put(fu, 1, fv, f"lever[face=wall,facing=@{out}]", walk=True)
        if top >= 2:
            R.put(u, 2, v, R.w2("planks"))
        R.items.append("fridge")
        return True
    if kind == "pantry":
        ok = R.put(u, 0, v, f"barrel[facing=@{out}]")
        for h in range(1, min(top, 2) + 1):
            R.put(u, h, v, f"barrel[facing=@{out}]")
        return ok
    if kind == "sink":
        if not R.put(u, 0, v, "water_cauldron[level=3]"):
            return False
        if top >= 1 and R.wall_ok(u, 1, v, W):
            R.put(u, 1, v, f"tripwire_hook[facing=@{out}]", walk=True)
        R.items.append("sink")
        return True
    if kind == "stove":
        if not R.put(u, 0, v, f"smoker[facing=@{out},lit=false]"):
            return False
        if top >= 2:
            R.put(u, 2, v, "hopper[facing=down]")
            for h in range(3, top + 1):
                R.put(u, h, v, R.sp("block", R.st["stone2"]))
        R.items.append("stove")
        return True
    s = {"oven": f"furnace[facing=@{out},lit=false]", "dish": f"blast_furnace[facing=@{out},lit=false]"}.get(kind, base)
    if not R.put(u, 0, v, s):
        return False
    if kind in ("cab", "corner"):
        if kind == "cab":
            R.put(fu, 0, fv, front)
        r = R.rng.random()
        if r < 0.22:
            R.plant(u, 1, v)
        elif r < 0.32:
            R.put(u, 1, v, "brewing_stand")
        elif r < 0.40:
            R.put(u, 1, v, "decorated_pot[facing=@" + out + "]")
    if upper and top >= 2 and kind in ("cab", "dish", "oven", "corner") and R.wall_ok(u, 2, v, W) and R.wall_ok(u, 1, v, W):
        if R.rng.random() < 0.3 and R.db.has_block(R.w("shelf")):
            R.put(u, 2, v, R.w("shelf") + f"[facing=@{out}]")
        elif R.put(u, 2, v, R.w2("planks")):
            R.put(fu, 2, fv, front, walk=True)
            if R.st["lamp"] == "end_rod" or R.style_name.startswith("modern"):
                R.put(u, 1, v, "end_rod[facing=down]")
    return True


# ---------------------------------------------------------------------- 1 oturma odasi
@_recipe("living_room", "Oturma odasi / salon: TV ya da ocak duvari, kumas kanepe + berjerler, orta sehpa, hali, lambader, kitaplik",
         "modern", 7, ("salon", "oturma odasi", "oturma", "misafir salonu", "living room", "living", "lounge",
                       "family room", "aile odasi", "sitting room"), ("oak_planks", "white_concrete", "smooth_quartz"))
def _living_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    R.plan()
    fv = V - 1
    if V >= 6 and U >= 5:
        vs = min(R.cv + 1, fv - 2)
        s0, w = R.csym(U, max(2, min(U - 4, 6)))
        if st.get("hearth") and not st.get("tv"):
            R.fireplace("F", width=3 if U < 9 else 5 if U >= 11 else 3)
        else:
            for u in range(s0, s0 + w):
                R.put(u, 0, fv, R.w2("slab") + "[type=top]")
            t0, tw = R.csym(U, max(1, min(w - 2, 5)))
            for u in range(t0, t0 + tw):
                for h in range(1, 3 if top >= 3 else 2):
                    R.put(u, h, fv, "black_concrete")
            R.plant(s0, 1, fv)
            R.plant(s0 + w - 1, 1, fv)
            R.items.append("tv")
        R.big_plant(s0 - 1, fv)
        R.big_plant(s0 + w, fv)
        R.sofa([(u, vs) for u in range(s0, s0 + w)], "F")
        tcells = R.table([(u, vs + 1) for u in range(s0 + 1, s0 + w - 1)] or [(s0, vs + 1)], "trapdoor")
        if tcells:
            R.plant(tcells[len(tcells) // 2][0], 1, vs + 1)
            if len(tcells) >= 3:
                R.lamp_on(tcells[0][0], 1, vs + 1, "candle")
        arm = f"{st['fabric2']}_wool_stairs"
        R.chair(s0 - 1, vs + 1, "R", mat=arm)
        R.chair(s0 + w, vs + 1, "L", mat=arm)
        R.floor_lamp(s0 - 2, vs)
        R.floor_lamp(s0 + w + 1, vs)
        R.rug(s0 - 2, vs - 1, s0 + w + 1, min(vs + 2, fv - 1), fill=st["rug"], border=st["rug2"])
        side = _side_walls(R)
        n = max(2, V - 5)
        R.bookcase(R.pick(side[0], n, 0, min(top, 2), min_len=2), side[0], h1=min(top, 2), chiseled=0.35)
        R.sideboard(R.pick(side[1], max(2, V - 6), 0, 0, min_len=2), side[1])
        R.std_lights((R.cu, vs))
    else:
        n = max(1, min(V - 2, 3))
        cells = R.pick("L", n, 0, 0, min_len=1, backed=False)
        R.sofa(cells, "R")
        mv = cells[len(cells) // 2][1] if cells else R.cv
        if U >= 4:
            R.table([(1, mv)], "trapdoor")
            R.plant(1, 1, mv)
        tv = R.pick("R", n, 0, 1, min_len=1)
        for (u, v) in tv:
            R.put(u, 0, v, R.w2("slab") + "[type=top]")
            R.put(u, 1, v, "black_concrete")
        R.rug(1, 1, U - 2, V - 2, fill=st["rug"], border=st["rug2"])
        R.big_plant(0, V - 1)
        R.std_lights()


# ---------------------------------------------------------------------- 2 mutfak
@_recipe("kitchen", "Mutfak: L/U tezgah (kapakli dolaplar), evye+musluk, ocak+davlumbaz, buzdolabi, ust dolaplar, ada ve tabureler",
         "modern", 8, ("mutfak", "mutfa", "kitchen", "asevi", "ascilik", "cookhouse", "kiler mutfak"),
         ("spruce_planks", "white_concrete", "smooth_quartz"))
def _kitchen(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    island = U >= 8 and V >= 8
    fv = V - 1
    if island:
        iv = fv - 3
        i0, iw = R.csym(U, min(U - 6, 4))
        icells = [(u, iv) for u in range(i0, i0 + iw)]
        R.plan_around(set(icells) | {(u, iv - 1) for u in range(i0, i0 + iw)})
    else:
        R.plan()
    back = R.pick("F", U, 0, 0, min_len=1)
    n = len(back)
    seq = ["cab"] * n
    if n >= 3:
        seq[0] = "fridge"
        win = [i for i, (u, v) in enumerate(back) if R.window_at(u, 1, v, "F") and 0 < i < n - 1]
        si = win[len(win) // 2] if win else n // 2
        seq[si] = "sink"
        so = min(n - 1, si + 2) if si + 2 < n else max(1, si - 2)
        if seq[so] == "cab":
            seq[so] = "stove"
        if n >= 7:
            for i in range(n):
                if seq[i] == "cab" and abs(i - si) == 1:
                    seq[i] = "dish"
                    break
    elif n == 2:
        seq = ["sink", "stove"]
    elif n == 1:
        seq = ["sink"]
    for (u, v), k in zip(back, seq):
        _counter_cell(R, u, v, "F", k)
    shape_u = U >= 6 and V >= 6
    depth = max(1, min(V - 4, 4)) if shape_u else max(1, min(V - 3, 3))
    sides = _side_walls(R)
    for W in (sides if shape_u else sides[:1]):
        row = [c for c in R.wall_row(W) if fv - depth <= c[1] < fv]
        row = sorted(row, key=lambda c: -c[1])
        run = []
        for c in row:
            if R.free(c[0], 0, c[1]) and R.wall_ok(c[0], 0, c[1], W):
                run.append(c)
            else:
                break
        for i, (u, v) in enumerate(run):
            k = "corner" if i == 0 else ("pantry" if i == len(run) - 1 and len(run) >= 3 else ("oven" if i == 2 else "cab"))
            _counter_cell(R, u, v, W, k)
    if island:
        if all(R.free(u, 0, v) for (u, v) in icells):
            for i, (u, v) in enumerate(icells):
                R.put(u, 0, v, "water_cauldron[level=3]" if (i == len(icells) - 1 and iw >= 3) else
                      R.sp("block", st["counter"]) if st["counter"] not in WOODS else st["counter"])
            for (u, v) in icells[:-1:2]:
                R.plant(u, 1, v)
            for (u, v) in icells:
                R.chair(u, v - 1, "F")
            for (u, v) in icells[::2]:
                R.hang(u, v)
            R.items.append("island")
    elif V >= 6 and U >= 5:
        tv = min(R.cv, fv - 3)
        t0 = 1 if not R.reserved(1, tv) else U - 3
        if R.table([(t0, tv), (t0 + 1, tv)], "slab"):
            R.chair(t0, tv - 1, "F")
            R.chair(t0 + 1, tv - 1, "F")
            R.plant(t0, 1, tv)
    if U >= 9 and V >= 9:
        tu = U - 3
        tvv = 2
        if R.pedestal(tu, tvv, "plate"):
            R.chair(tu - 1, tvv, "R")
            R.chair(tu + 1, tvv, "L")
    R.std_lights(step=3 if st["light_order"][0] == "flush" else 4)


# ---------------------------------------------------------------------- 3 yemek odasi
@_recipe("dining_room", "Yemek odasi: ortada uzun masa, sandalyeler, mumlar ve orta susu, avize, bufe/vitrin, hali",
         "rustic", 7, ("yemek odasi", "yemek salonu", "yemekhane", "dining room", "dining", "salle a manger"),
         ("dark_oak_planks", "white_terracotta", "spruce_planks"))
def _dining_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    along_u = U >= V
    LU, LV = (U, V) if along_u else (V, U)
    L = max(1, min(LU - 4, 8))
    Wt = 2 if LV >= 7 else 1
    a0, L = R.csym(LU, L)
    b0, Wt = R.csym(LV, Wt)
    if along_u:
        tcells = [(a0 + i, b0 + j) for i in range(L) for j in range(Wt)]
    else:
        tcells = [(b0 + j, a0 + i) for i in range(L) for j in range(Wt)]
    tset = set(tcells)
    ring = set()
    for (u, v) in tcells:
        for du, dv in TV.values():
            if (u + du, v + dv) not in tset:
                ring.add((u + du, v + dv))
    R.plan_around(tset)
    wood = st["wood2"] if st["wood2"] in WOODS else st["wood"]
    R.table(tcells, "slab", wood=wood)
    # sandalyeler: masanin her kenarinda, masaya bakan
    for (u, v) in sorted(ring):
        if not R.in2(u, v):
            continue
        for tok, (du, dv) in TV.items():
            if (u + du, v + dv) in tset:
                if (along_u and tok in ("F", "B")) or (not along_u and tok in ("L", "R")) or len(tcells) <= 2:
                    R.chair(u, v, tok, arms=None)
                else:
                    R.chair(u, v, tok, arms="sign")
                break
    # masa ustu: mumlar ve orta susu
    for i, (u, v) in enumerate(sorted(tcells)):
        if i % 3 == 1:
            R.plant(u, 1, v)
        elif i % 3 == 0:
            R.lamp_on(u, 1, v, "candle")
    us = sorted({c[0] for c in tcells})
    vs = sorted({c[1] for c in tcells})
    R.rug(us[0] - 1, vs[0] - 1, us[-1] + 1, vs[-1] + 1, fill=st["rug"], border=st["rug2"])
    # bufe + vitrin
    sides = _side_walls(R)
    R.sideboard(R.pick("F", max(2, U - 6), 0, 0, min_len=2), "F", kinds=("planks", "chiseled", "planks"))
    cab = R.pick(sides[0], 2, 0, min(1, top), min_len=1)
    for (u, v) in cab:
        R.put(u, 0, v, R.chiseled(OPPT[sides[0]]))
        if top >= 1:
            R.put(u, 1, v, "glass")
        if top >= 2:
            R.put(u, 2, v, R.w2("slab") + "[type=bottom]")
    for (u, v) in ((0, 0), (U - 1, 0), (0, V - 1), (U - 1, V - 1)):
        R.big_plant(u, v)
    cu = (us[0] + us[-1]) // 2
    cv = (vs[0] + vs[-1]) // 2
    if L >= 6 and along_u:
        R.chandelier(us[0] + 1, cv)
        R.chandelier(us[-1] - 1, cv)
    elif L >= 6:
        R.chandelier(cu, vs[0] + 1)
        R.chandelier(cu, vs[-1] - 1)
    else:
        R.chandelier(cu, cv)
    for W in sides:
        R.sconces(W, 4)


# ---------------------------------------------------------------------- 4 ebeveyn yatak odasi
@_recipe("master_bedroom", "Ebeveyn yatak odasi: cift kisilik yatak + bas tahtasi, komodinler ve abajur, gomme dolap, makyaj masasi, yatak ucu puf, hali",
         "nordic", 6, ("yatak odasi", "ebeveyn yatak odasi", "ebeveyn", "yatak", "bedroom", "master bedroom",
                       "uyku odasi", "sleeping room", "bed room"), ("oak_planks", "white_terracotta", "spruce_planks"))
def _master_bedroom(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    b0 = (U - 2) // 2 if U >= 4 else 0
    bw = 2 if U >= 4 else 1
    bed = [(b0 + i, fv) for i in range(bw)] + [(b0 + i, fv - 1) for i in range(bw)]
    R.plan_around(set(bed))
    for i in range(bw):
        if R.bed(b0 + i, fv - 1, "F"):
            if top >= 1:
                R.put(b0 + i, 1, fv, R.w2("trapdoor") + "[facing=@B,open=true]")
    for nu in (b0 - 1, b0 + bw):
        if R.put(nu, 0, fv, R.chiseled("B") if st["lamp"] != "end_rod" else R.sp("block")):
            R.lamp_on(nu, 1, fv, "lamp")
    if V >= 6:
        bench = [(b0 + i, fv - 2) for i in range(bw)]
        if all(R.free(u, 0, v) for (u, v) in bench):
            for (u, v) in bench:
                R.put(u, 0, v, f"{st['fabric2']}_wool_slab[type=bottom]")
            R.items.append("bench")
    R.rug(b0 - 1, fv - 2 if V < 6 else fv - 3, b0 + bw, fv - 1, fill=st["rug"], border=st["rug2"])
    sides = _side_walls(R)
    wd = R.pick(sides[0], 4 if V >= 8 else 3, 0, 1, min_len=3)
    if not R.wardrobe(wd, sides[0]) and V >= 4:
        R.bookcase(R.pick(sides[0], 2, 0, 1, min_len=1), sides[0], h1=1)
    dr = R.pick(sides[1], 3 if V >= 8 else 2, 0, 0, min_len=1)
    R.sideboard(dr, sides[1], kinds=("chiseled", "planks"))
    if U >= 8 and V >= 7:
        cu_ = 1 if sides[0] == "R" else U - 2
        R.chair(cu_, 1, "F", mat=f"{st['fabric']}_wool_stairs", arms="trapdoor")
        R.floor_lamp(cu_ + (1 if cu_ == 1 else -1), 0) or R.big_plant(cu_ + (1 if cu_ == 1 else -1), 0)
    R.big_plant(0, 0)
    R.big_plant(U - 1, 0)
    R.std_lights((R.cu, max(1, fv - 3)))


# ---------------------------------------------------------------------- 5 cocuk odasi
@_recipe("kids_room", "Cocuk odasi: ranza (alcak tavanda iki yatak), renkli dama hali, oyuncak sandigi ve renkli bloklar, oyun masasi, muzik kutusu, kitaplik",
         "modern", 7, ("cocuk odasi", "cocuk", "kids room", "kid room", "kids", "children", "childrens room", "nursery",
                       "oyun odasi", "playroom", "bebek odasi"), ("birch_planks", "white_concrete", "birch_planks"))
def _kids_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    c1, c2, c3 = R.rng.choice((("light_blue", "yellow", "lime"), ("pink", "purple", "magenta"),
                               ("lime", "orange", "yellow"), ("cyan", "red", "white")))
    side = _side_walls(R)[0]
    bu = 0 if side == "L" else U - 1
    inner = 1 if side == "L" else -1
    bunk = top >= 3 and V >= 4
    foot = [(bu, fv - 1), (bu, fv)] + ([(bu, fv - 2)] if bunk else [])
    R.plan_around(set(foot))
    if R.bed(bu, fv - 1, "F", color=c1) and bunk:
        R.put(bu, 2, fv - 1, f"{c2}_bed[facing=@F,part=foot]")
        R.put(bu, 2, fv, f"{c2}_bed[facing=@F,part=head]")
        for h in range(0, 3):
            if R.wall_ok(bu, h, fv - 2, side):
                R.put(bu, h, fv - 2, f"ladder[facing=@{OPPT[side]}]")
        R.items.append("bunk_bed")
    elif U >= 6:
        R.bed(U - 1 - bu, fv - 1, "F", color=c2)
    nu = bu + inner
    if R.put(nu, 0, fv, R.chiseled("B")):
        R.lamp_on(nu, 1, fv, "lamp")
    R.chest_pair((nu, fv - 2), (nu + inner, fv - 2), "F") if V >= 6 and U >= 6 else R.put(nu, 0, fv - 2, "chest[facing=@F]")
    # renkli oyun halisi
    r0, r1 = (1, U - 2) if U >= 5 else (0, U - 1)
    R.rug(r0, 1, r1, max(1, fv - 3) if V >= 6 else V - 2, fill=c1, accent=c2, pattern="checker", border=c3)
    # oyun masasi + kucuk sandalyeler
    if U >= 7 and V >= 6:
        tu = U - 3 if side == "L" else 2
        tv = 2
        if R.pedestal(tu, tv, f"{c3}_carpet"):
            R.chair(tu - 1, tv, "R", mat=f"{c1}_wool_stairs")
            R.chair(tu + 1, tv, "L", mat=f"{c2}_wool_stairs")
    # oyuncak bloklari ve muzik kutusu (diger yan duvar)
    oside = "R" if side == "L" else "L"
    toys = R.pick(oside, 3, 0, 0, min_len=1)
    stacks = (f"{c1}_concrete", f"{c2}_concrete", f"{c3}_concrete")
    for i, (u, v) in enumerate(toys):
        if i == 0:
            R.put(u, 0, v, "jukebox")
            R.put(u, 1, v, "copper_golem_statue[facing=@" + OPPT[oside] + "]") if R.db.has_block("copper_golem_statue") else None
        elif i == 1:
            R.put(u, 0, v, "note_block")
            R.plant(u, 1, v)
        else:
            R.put(u, 0, v, stacks[i % 3])
            R.put(u, 1, v, stacks[(i + 1) % 3])
    R.items.append("toys")
    bc = R.pick("F", max(1, min(3, U - 4)), 0, 0, min_len=1, cells=[c for c in R.wall_row("F") if abs(c[0] - bu) >= 2])
    R.bookcase(bc, "F", h1=0, chiseled=0.6)
    for (u, v) in bc[::2]:
        R.plant(u, 1, v)
    lights = ("pearlescent_froglight", "ochre_froglight", "verdant_froglight")
    i = 0
    for u in _grid(U, 4):
        for v in _grid(V, 4):
            i += bool(R.flush_ceiling(u, v, lights[i % 3]))
    if not i:
        R.std_lights()


# ---------------------------------------------------------------------- 6 banyo
@_recipe("bathroom", "Banyo: kuvars kenarli kuvet + musluk, cam dus kabini, klozet + sifon dugmesi, lavabo (kazan) + musluk, havlu (sancak), paspas",
         "modern", 8, ("banyo", "bathroom", "bath", "wc", "tuvalet", "hamam", "lavabo", "dus", "washroom", "restroom",
                       "toilet", "ensuite"), ("smooth_stone", "white_terracotta", "smooth_quartz"))
def _bathroom(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    q = stone_parts(R.db, "smooth_quartz")
    tl = 3 if U >= 9 else 2 if U >= 4 else 1
    tub = [(i, fv) for i in range(tl)]
    rim = ([(i, fv - 1) for i in range(tl)] if V >= 4 else []) + [(tl, fv)]
    shower = U >= 7 and V >= 5
    sh = [(U - 1, fv), (U - 1, fv - 1)]
    glass = [(U - 2, fv), (U - 2, fv - 1)]
    forbid = set(tub) | set(rim) | ((set(sh) | set(glass)) if shower else set())
    R.plan_around(forbid)
    can_tub = V >= 4 and all(R.free(u, 0, v) for (u, v) in tub + rim) and all(R.floor_ok(u, v) for (u, v) in tub) \
        and all(R.wall_ok(u, 0, v, "F") for (u, v) in tub) and R.wall_ok(0, 0, fv, "L")
    if can_tub:
        for (u, v) in rim:
            R.put(u, 0, v, q["block"])
        for (u, v) in tub:
            R.put(u, 0, v, "water")
        if top >= 1 and R.wall_ok(tl - 1, 1, fv, "F"):
            R.put(tl - 1, 1, fv, "tripwire_hook[facing=@B]", walk=True)
        R.rug(0, fv - 2, tl - 1, fv - 2, fill="light_blue")
        R.items.append("bathtub")
    if shower and all(R.free(u, 0, v) for (u, v) in sh + glass):
        for (u, v) in sh:
            R.put(u, 0, v, "iron_trapdoor[half=bottom,open=false,facing=@F]")
        for (u, v) in glass:
            for h in range(0, min(top, 2)):
                R.put(u, h, v, "glass_pane")
        R.put(U - 1, top, fv, "waxed_lightning_rod[facing=down]", walk=True)
        R.items.append("shower")
    # klozet: yan duvarda, kapiya yakin
    for W, u in (("R", U - 1), ("L", 0)):
        placed = False
        for v in range(1, max(2, fv - 1)):
            if R.free(u, 0, v) and R.wall_ok(u, 0, v, W) and R.wall_ok(u, 1, v, W):
                R.put(u, 0, v, f"{q['stairs']}[facing=@{W}]")
                if top >= 1:
                    R.put(u, 1, v, f"stone_button[face=wall,facing=@{OPPT[W]}]", walk=True)
                R.items.append("toilet")
                placed = True
                break
        if placed:
            break
    # lavabo + tezgah
    for W in ("L", "R", "F"):
        cells = R.pick(W, 2, 0, 0, min_len=1)
        if cells:
            u, v = cells[0]
            R.put(u, 0, v, "water_cauldron[level=3]")
            if top >= 1 and R.wall_ok(u, 1, v, W):
                R.put(u, 1, v, f"tripwire_hook[facing=@{OPPT[W]}]", walk=True)
            if len(cells) > 1:
                a, b = cells[1]
                R.put(a, 0, b, q["block"])
                R.plant(a, 1, b, "potted_fern")
            fu, fv_ = u + TV[OPPT[W]][0], v + TV[OPPT[W]][1]
            R.rug(fu, fv_, fu, fv_, fill="white")
            R.items.append("sink")
            break
    # havlular
    n = 0
    for W in ("R", "L", "B"):
        for (u, v) in R.wall_row(W):
            if n >= 2:
                break
            if R.free(u, top, v, walk=True) and top >= 2 and R.banner(u, top, v, W, "white"):
                n += 1
    R.big_plant(*(R.pick("B", 1, 0, 1, min_len=1) or [(0, 0)])[0])
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 7 kutuphane / calisma odasi
@_recipe("library", "Kutuphane / calisma odasi: tavana kadar kitapliklar (oyma raflar, kutuk direkler), kitaplik merdiveni, okuma masasi + sandalyeler + mumlar, kursu, okuma kosesi, hali",
         "rustic", 7, ("kutuphane", "library", "calisma odasi", "study", "kitaplik", "okuma odasi", "reading room",
                       "arsiv", "archive", "kitap odasi"), ("dark_oak_planks", "white_terracotta", "dark_oak_planks"))
def _library(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    big = U >= 7 and V >= 7
    tcells = []
    if big:
        t0, tl = R.csym(U, max(2, min(U - 6, 6)))
        tv = min(R.cv + 1, fv - 3)
        tcells = [(u, tv) for u in range(t0, t0 + tl)]
        R.plan_around(set(tcells) | {(u, tv + d) for u in range(t0, t0 + tl) for d in (-1, 1)})
    else:
        R.plan()
    for W in ("F", "L", "R", "B"):
        cells = [c for c in R.wall_row(W) if R.free(c[0], 0, c[1])]
        R.bookcase(cells, W, post_every=4 if len(cells) >= 7 else 0, chiseled=0.3)
    if top >= 3:
        for u in (U // 3, U - 1 - U // 3):
            if all(R.free(u, h, fv - 1, walk=True) for h in range(0, top + 1)) and not R.reserved(u, fv - 1) \
                    and R.b.get(*R.P(u, 0, fv)) == "minecraft:bookshelf":
                for h in range(0, top + 1):
                    if _bname(R.b.get(*R.P(u, h, fv))) in ("bookshelf", "chiseled_bookshelf"):
                        R.put(u, h, fv - 1, "ladder[facing=@B]", walk=True)
                R.items.append("library_ladder")
                break
    if big:
        R.table(tcells, "slab", wood=st["wood2"])
        for i, (u, v) in enumerate(tcells):
            R.chair(u, v - 1, "F")
            R.chair(u, v + 1, "B")
            if i % 2 == 0:
                R.lamp_on(u, 1, v, "candle" if i % 4 == 0 else "lamp")
        R.put(tcells[-1][0] + 1, 0, tcells[0][1], "lectern[facing=@L,has_book=true]")
        R.rug(tcells[0][0] - 1, tcells[0][1] - 2, tcells[-1][0] + 1, tcells[0][1] + 2, fill=st["rug"], border=st["rug2"])
        R.nook("BL")
        R.nook("BR")
        R.chandelier(tcells[len(tcells) // 2][0], tcells[0][1])
    else:
        mu = max(1, R.cu - 1) if U >= 4 else 0
        R.chair(mu, max(1, R.cv), "R", mat=f"{st['fabric']}_wool_stairs", arms="trapdoor")
        R.put(min(U - 2, R.cu + 1), 0, min(fv - 1, R.cv + 1), "lectern[facing=@B,has_book=true]")
        R.rug(1, 1, U - 2, V - 2, fill=st["rug"], border=st["rug2"])
        R.std_lights()


# ---------------------------------------------------------------------- 8 ev ofisi
@_recipe("home_office", "Ev ofisi: duvara dayali calisma masasi (iki ekran + dizustu + masa lambasi), kollu ofis koltugu, dosya dolaplari ve yazici, kitaplik, toplanti kosesi",
         "modern", 8, ("ofis", "ev ofisi", "calisma masasi", "home office", "office", "is odasi", "workroom", "buro"),
         ("oak_planks", "white_concrete", "smooth_quartz"))
def _home_office(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    dl = 3 if U >= 6 else 2 if U >= 3 else 1
    d0 = (U - dl) // 2
    desk = [(u, fv) for u in range(d0, d0 + dl)]
    chair = (d0 + dl // 2, fv - 1)
    R.plan_around(set(desk) | {chair})
    R.table(desk, "slab", wood=st["wood2"])
    if top >= 1:
        mons = desk[1:] if dl >= 3 else desk[:1]
        for (u, v) in mons[:2]:
            R.put(u, 1, v, "!black_stained_glass_pane[@L=true,@R=true]")
        if dl >= 2:
            R.put(desk[0][0], 1, fv, "daylight_detector")
        R.items.append("computer")
    R.chair(chair[0], chair[1], "F", mat=R.w2("stairs"), arms="trapdoor")
    if not R.lamp_on(d0 - 1, 1, fv):
        if R.put(d0 - 1, 0, fv, R.w2("planks")):
            R.lamp_on(d0 - 1, 1, fv)
    if R.put(d0 + dl, 0, fv, f"barrel[facing=@B]"):
        R.plant(d0 + dl, 1, fv)
    sides = _side_walls(R)
    fil = R.pick(sides[0], 3, 0, 1, min_len=1)
    for i, (u, v) in enumerate(fil):
        R.put(u, 0, v, R.chiseled(OPPT[sides[0]]) if i % 2 else f"barrel[facing=@{OPPT[sides[0]]}]")
        if i == 1:
            R.put(u, 1, v, f"dropper[facing=@{OPPT[sides[0]]}]")
            R.items.append("printer")
        else:
            R.plant(u, 1, v)
    R.bookcase(R.pick(sides[1], max(2, V - 5), 0, 0, min_len=1), sides[1], h1=min(top, 2), chiseled=0.4)
    R.rug(max(0, d0 - 1), fv - 3 if V >= 6 else fv - 2, min(U - 1, d0 + dl), fv - 1, fill=st["rug2"], border=st["rug3"])
    if U >= 7 and V >= 7:
        tu, tv = R.cu, 1
        if R.pedestal(tu, tv + 1, "plate") or R.pedestal(tu - 2, tv + 1, "plate"):
            pass
        R.nook("BL")
    R.big_plant(0, fv) or R.big_plant(U - 1, fv)
    R.std_lights(step=3)


# ---------------------------------------------------------------------- 9 misafir odasi
@_recipe("guest_room", "Misafir odasi: iki tek kisilik yatak + aradaki komodin ve abajur, valiz sandigi, kucuk dolap, yazi masasi, hali, bitki",
         "nordic", 6, ("misafir odasi", "misafir yatak", "guest room", "guest bedroom", "spare room", "konuk odasi"),
         ("oak_planks", "white_terracotta", "spruce_planks"))
def _guest_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    if U >= 5:
        bus = (R.cu - 1, R.cu + 1)
    else:
        bus = (R.cu,)
    cells = {(u, fv - d) for u in bus for d in (0, 1)} | {(R.cu, fv)}
    R.plan_around(cells)
    for i, u in enumerate(bus):
        R.bed(u, fv - 1, "F", color=st["bed"] if i == 0 else st["fabric2"] if st["fabric2"] in COLORS else st["bed"])
    if len(bus) == 2 and R.put(R.cu, 0, fv, R.chiseled("B")):
        R.lamp_on(R.cu, 1, fv, "lamp")
    if V >= 6:
        R.put(bus[0], 0, fv - 2, "chest[facing=@B]")
    R.rug(min(bus) - 1, fv - 2 if V < 7 else fv - 3, max(bus) + 1, fv - 1, fill=st["rug"], border=st["rug2"])
    sides = _side_walls(R)
    if not R.wardrobe(R.pick(sides[0], 3, 0, 1, min_len=3), sides[0]):
        R.wardrobe(R.pick("B", 3, 0, 1, min_len=3), "B")
    desk = R.pick(sides[1], 2, 0, 0, min_len=1)
    if desk and R.table(desk[:1], "slab"):
        u, v = desk[0]
        R.lamp_on(u, 1, v)
        R.chair(u + TV[OPPT[sides[1]]][0], v + TV[OPPT[sides[1]]][1], sides[1])
    R.big_plant(0, 0)
    R.big_plant(U - 1, 0)
    R.std_lights((R.cu, max(1, fv - 3)))


# ---------------------------------------------------------------------- 10 giris holu
@_recipe("foyer", "Giris holu / antre: kapi paspasi ve yol halisi, ortada yuvarlak masa + cicek, konsol + lamba, bank + portmanto kancalari, ayakkabilik, semsiyelik, avize",
         "nordic", 7, ("giris", "giris holu", "antre", "hol", "koridor", "foyer", "entrance", "entrance hall", "hall",
                       "vestibule", "lobby", "lobi", "hallway", "mudroom"), ("spruce_planks", "white_terracotta", "spruce_planks"))
def _foyer(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    big = U >= 7 and V >= 7
    if big:
        R.plan_around({(R.cu, R.cv)})
    else:
        R.plan()
    # paspas + yol halisi
    for (ue, ve, _) in R.entries:
        R.put(ue, 0, ve, "brown_carpet", walk=True)
    for (x, z) in sorted(R.res):
        u, v = R.uv(x, z)
        R.put(u, 0, v, f"{st['rug3']}_carpet", walk=True)
    if big:
        if R.table([(R.cu, R.cv)], "slab", wood=st["wood2"]):
            R.plant(R.cu, 1, R.cv, "potted_flowering_azalea_bush")
        R.rug(R.cu - 1, R.cv - 1, R.cu + 1, R.cv + 1, fill=st["rug2"])
    sides = _side_walls(R)
    con = R.pick(sides[0], 3 if V >= 6 else 2, 0, 0, min_len=1)
    if R.table(con, "slab", wood=st["wood2"]):
        R.lamp_on(*con[0][:1], 1, con[0][1]) if False else R.lamp_on(con[0][0], 1, con[0][1])
        R.plant(con[-1][0], 1, con[-1][1])
        R.items.append("console")
    bench = R.pick(sides[1], 3 if V >= 6 else 2, 0, 1, min_len=1)
    for (u, v) in bench:
        if R.put(u, 0, v, R.w("slab") + "[type=bottom]"):
            if top >= 1 and R.wall_ok(u, 1, v, sides[1]):
                R.put(u, 1, v, f"tripwire_hook[facing=@{OPPT[sides[1]]}]", walk=True)
    if bench:
        R.items.append("bench")
    shoe = [c for c in R.wall_row("B") if R.free(c[0], 0, c[1])]
    shoe = shoe[:2] + shoe[-2:] if len(shoe) > 4 else shoe
    for (u, v) in shoe[:2]:
        R.put(u, 0, v, R.chiseled("F"))
    if len(shoe) > 2:
        R.plant(shoe[-1][0], 0, shoe[-1][1], "potted_bamboo")
    R.big_plant(0, fv)
    R.big_plant(U - 1, fv)
    if U >= 6:
        R.sideboard(R.pick("F", 2, 0, 0, min_len=1), "F", kinds=("planks",))
    R.std_lights((R.cu, R.cv))
    for W in sides:
        R.sconces(W, 4)


# ---------------------------------------------------------------------- 11 camasir / hizmet odasi
@_recipe("laundry", "Camasir / hizmet odasi: ust uste camasir + kurutma makinesi, servis evyesi, katlama tezgahi (katli havlular), raflar, utu masasi, sicak su kazani, sepetler",
         "modern", 8, ("camasir", "camasirhane", "camasir odasi", "laundry", "utility", "hizmet odasi", "utility room",
                       "kazan dairesi", "boiler room"), ("smooth_stone", "white_concrete", "smooth_stone"))
def _laundry(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    R.plan()
    back = R.pick("F", U, 0, 0, min_len=1)
    n = len(back)
    seq = ["wash", "wash", "sink", "fold", "fold", "heater", "fold", "wash"]
    if n <= 3:
        seq = ["wash", "sink", "fold"]
    for i, (u, v) in enumerate(back):
        k = seq[i % len(seq)]
        if k == "wash":
            R.put(u, 0, v, "dispenser[facing=@B]")
            if top >= 1:
                R.put(u, 1, v, "dropper[facing=@B]")
            R.items.append("washer")
        elif k == "sink":
            R.put(u, 0, v, "water_cauldron[level=3]")
            if top >= 1 and R.wall_ok(u, 1, v, "F"):
                R.put(u, 1, v, "tripwire_hook[facing=@B]", walk=True)
        elif k == "heater":
            R.put(u, 0, v, "waxed_copper_block")
            if top >= 1:
                R.put(u, 1, v, "waxed_cut_copper")
                R.put(u, 1, v - 1, "lever[face=wall,facing=@B]", walk=True)
        else:
            R.put(u, 0, v, "smooth_stone_slab[type=top]")
            R.put(u, 1, v, f"{R.rng.choice(('white', 'light_blue', 'pink', 'yellow'))}_carpet")
        if top >= 2 and R.wall_ok(u, 2, v, "F") and k != "heater":
            R.put(u, 2, v, R.w("shelf") + "[facing=@B]")
    sides = _side_walls(R)
    ir = R.pick(sides[0], 2, 0, 0, min_len=1, backed=False)
    if ir:
        u, v = ir[0]
        if R.put(u, 0, v, "iron_trapdoor[half=top,facing=@F]"):
            R.put(u, 1, v, "heavy_weighted_pressure_plate")
            R.items.append("ironing_board")
    bk = R.pick(sides[1], 3, 0, 0, min_len=1)
    for i, (u, v) in enumerate(bk):
        R.put(u, 0, v, "composter[level=3]" if i % 2 == 0 else f"barrel[facing=up]")
    if top >= 3 and U >= 4:
        lv = max(1, R.cv - 1)
        for u in range(1, U - 1):
            if R.free(u, top, lv, walk=True):
                R.put(u, top, lv, R.chain("@AU"), walk=True)
        R.items.append("drying_line")
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 12 kiler / depo
@_recipe("pantry", "Kiler / depo: duvar boyu raf kolonlari (varil, saman balyasi, balkabagi, kavun, kurutulmus yosun, petek), raf bloklari ve kupler, ortada cift tarafli raf, asili fenerler",
         "rustic", 6, ("kiler", "depo", "ambar", "pantry", "storage", "storeroom", "store room", "larder", "erzak"),
         ("spruce_planks", "spruce_planks", "spruce_planks"))
def _pantry(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    R.plan()
    crates = ("barrel[facing=up]", "hay_block", "pumpkin", "melon", "dried_kelp_block", "barrel[facing=up]",
              "bee_nest[facing=@B]", "composter[level=8]")
    for W in ("F", "L", "R", "B"):
        face = OPPT[W]
        for i, (u, v) in enumerate(R.wall_row(W)):
            if not R.free(u, 0, v):
                continue
            c = R.rng.choice(crates).replace("@B", "@" + face)
            R.put(u, 0, v, c)
            if top >= 1:
                if i % 2 == 0 and R.db.has_block(R.w("shelf")):
                    R.put(u, 1, v, R.w("shelf") + f"[facing=@{face}]")
                else:
                    R.put(u, 1, v, R.w("slab") + "[type=top]")
                    if top >= 2:
                        R.put(u, 2, v, R.rng.choice(("decorated_pot[facing=@" + face + "]", "flower_pot",
                                                     "barrel[facing=up]", "potted_red_mushroom")))
            if top >= 3 and R.free(u, top, v, walk=True) and R.rng.random() < 0.5:
                R.put(u, top, v, "barrel[facing=@" + face + "]", walk=True)
    if U >= 7 and V >= 6:
        rv = R.cv + 1
        for u in range(2, U - 2):
            if R.free(u, 0, rv) and R.free(u, 1, rv):
                R.put(u, 0, rv, R.rng.choice(crates[:6]))
                R.put(u, 1, rv, R.w("slab") + "[type=top]")
                if top >= 2:
                    R.plant(u, 2, rv, "flower_pot") if R.rng.random() < 0.5 else R.put(u, 2, rv, "decorated_pot[facing=@B]")
        R.items.append("rack")
    R.items.append("shelves")
    R.pendant_grid(4)


# ---------------------------------------------------------------------- 13 sarap mahzeni
@_recipe("wine_cellar", "Sarap mahzeni: yan yatmis fici raflari (3 kat), tas ayaklar, tonoz kemer (ters tas merdiven), fici masa + mumlar + tabureler, los isik",
         "rustic", 5, ("sarap mahzeni", "mahzen", "sarap", "wine cellar", "cellar", "bodrum", "basement", "wine", "fici odasi"),
         ("cobblestone", "stone_bricks", "stone_bricks"))
def _wine_cellar(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    R.plan()
    sb = stone_parts(R.db, "stone_bricks")
    rack_h = min(top - 1, 2) if top >= 2 else 0
    for W in ("F", "L", "R", "B"):
        face = OPPT[W]
        row = R.wall_row(W)
        for i, (u, v) in enumerate(row):
            if not R.free(u, 0, v):
                continue
            if i % 4 == 0 and 0 < i < len(row) - 1:
                for h in range(0, top + 1):
                    R.put(u, h, v, sb["block"])
                continue
            for h in range(0, rack_h + 1):
                R.put(u, h, v, f"barrel[facing=@{face}]")
            if top >= 2:
                R.put(u, top, v, f"{sb['stairs']}[facing=@{W},half=top]", walk=True)
    R.items.append("wine_racks")
    # tadim masasi
    if U >= 5 and V >= 5:
        tu, tv = R.cu + (1 if U >= 7 else 0), R.cv + 1
        if R.put(tu, 0, tv, "barrel[facing=up]"):
            R.lamp_on(tu, 1, tv, "candle")
            for tok in ("L", "R", "F"):
                a, b = tu + TV[tok][0], tv + TV[tok][1]
                R.put(a, 0, b, R.w("slab") + "[type=bottom]")
            R.items.append("tasting_table")
    for (u, v) in ((0, V - 1), (U - 1, V - 1)):
        if R.free(u, top, v, walk=True) and top >= 2:
            R.put(u, top, v, "cobweb", walk=True)
    R.pendant_grid(5)
    R.sconces("L", 5)
    R.sconces("R", 5)


# ---------------------------------------------------------------------- 14 atolye / demirhane
@_recipe("workshop", "Atolye / demirhane: tugla ocak (yanan yuksek firin + firin) ve baca, ors, bileği tasi, su teknesi, demirci/tas kesme/ok masasi, alet duvari, malzeme yigini",
         "medieval", 7, ("atolye", "demirhane", "demirci", "workshop", "smithy", "forge", "blacksmith", "zanaat",
                         "marangoz", "tamirhane", "garage", "garaj"), ("cobblestone", "stone_bricks", "spruce_planks"))
def _workshop(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    forge = [(0, fv)] + ([(1, fv)] if U >= 5 else [])
    R.plan_around(set(forge))
    br = stone_parts(R.db, "bricks")
    for i, (u, v) in enumerate(forge):
        if R.put(u, 0, v, ("blast_furnace" if i == 0 else "furnace") + "[facing=@B,lit=true]"):
            for h in range(1, top + 1):
                R.put(u, h, v, br["block"])
    R.items.append("forge")
    q = len(forge)
    R.put(q, 0, fv, "water_cauldron[level=3]")
    if V >= 4:
        R.put(1, 0, fv - 2, "anvil[facing=@L]") or R.put(2, 0, fv - 2, "anvil[facing=@L]")
    tools = ["smithing_table", "grindstone[face=floor,facing=@B]", "stonecutter[facing=@B]", "crafting_table",
             "fletching_table"]
    side = "R"
    bench = R.pick(side, min(len(tools), max(1, V - 3)), 0, 0, min_len=1)
    for (u, v), t in zip(bench, tools):
        R.put(u, 0, v, t.replace("@B", "@L"))
        if top >= 2 and R.wall_ok(u, 2, v, side):
            R.put(u, 2, v, "waxed_lightning_rod[facing=@L]", walk=True)
        if top >= 1 and R.wall_ok(u, 1, v, side):
            R.put(u, 1, v, "tripwire_hook[facing=@L]", walk=True)
    R.items.append("workbench")
    pile = [c for c in R.wall_row("F") if c[0] >= q + 2]
    for i, (u, v) in enumerate(pile[:4]):
        R.put(u, 0, v, ("iron_block", "coal_block", "waxed_copper_block", "barrel[facing=up]")[i % 4])
    lw = R.pick("L", 3, 0, 0, min_len=1, cells=[c for c in R.wall_row("L") if c[1] < fv - 1])
    for i, (u, v) in enumerate(lw):
        R.put(u, 0, v, "chest[facing=@R]" if i == 0 else "barrel[facing=@R]")
    R.std_lights()
    R.sconces("L", 4)


# ---------------------------------------------------------------------- 15 meyhane / han salonu
@_recipe("tavern", "Meyhane / han salonu: bar tezgahi + tabureler, arkada fici ve sise raflari, ocak, mumlu masalar ve sandalyeler, araba tekerlegi avize",
         "rustic", 6, ("meyhane", "han salonu", "han odasi", "kervansaray", "tavern", "inn", "pub", "bar", "taverna",
                       "lokanta", "saloon"), ("spruce_planks", "spruce_planks", "spruce_planks"))
def _tavern(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    big = V >= 7 and U >= 6
    bar_v = fv - 2 if big else fv
    counter = [(u, bar_v) for u in range(1 if big else 0, U - 2 if big else U)]
    stools = [(u, bar_v - 1) for (u, _) in counter]
    R.plan_around(set(counter) | set(stools) | ({(u, fv - 1) for u in range(U)} if big else set()))
    for i, (u, v) in enumerate(counter):
        if R.put(u, 0, v, R.w("stripped_log") + "[axis=@AU]" if i % 3 else "barrel[facing=@B]"):
            r = R.rng.random()
            if r < 0.3:
                R.put(u, 1, v, "brewing_stand")
            elif r < 0.5:
                R.lamp_on(u, 1, v, "candle")
    for (u, v) in stools[::2] if big else []:
        R.chair(u, v, "F")
    if big:
        for i, (u, v) in enumerate(R.wall_row("F")):
            if R.free(u, 0, v):
                R.put(u, 0, v, "barrel[facing=@B]")
                if top >= 1:
                    R.put(u, 1, v, "barrel[facing=@B]") if i % 2 else R.put(u, 1, v, R.w("shelf") + "[facing=@B]")
                if top >= 2 and i % 2 == 0:
                    R.put(u, 2, v, "brewing_stand")
    R.items.append("bar")
    sides = _side_walls(R)
    if V >= 8 and U >= 7:
        row = R.wall_row(sides[1])
        R.fireplace(sides[1], t=max(1, min(len(row) - 2, (bar_v - 2) // 2 + 1)), width=3)
    tv_max = (bar_v - 2) if big else fv - 1
    for tv in range(2, max(2, tv_max), 3):
        for tu in _grid(U, 4):
            if R.free(tu, 0, tv) and R.put(tu, 0, tv, "barrel[facing=up]"):
                R.lamp_on(tu, 1, tv, "candle")
                for tok in ("L", "R", "B", "F"):
                    a, b = tu + TV[tok][0], tv + TV[tok][1]
                    R.chair(a, b, OPPT[tok])
                R.items.append("table")
    R.std_lights((R.cu, max(1, (bar_v - 1) // 2)))


# ---------------------------------------------------------------------- 16 taht salonu
@_recipe("throne_hall", "Taht salonu: girisden kursuye kirmizi yol halisi, basamakli kursu ve taht (altin arkalik, kollar), sancaklar, sutun sirasi ve mesaleler, avizeler",
         "royal", 8, ("taht", "taht salonu", "taht odasi", "throne", "throne room", "throne hall", "saray salonu",
                      "divan", "huzur salonu", "audience hall"), ("polished_andesite", "stone_bricks", "stone_bricks"))
def _throne_hall(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    R.min_hang = 3
    stone = stone_parts(R.db, st["stone"])
    d0, dw = R.csym(U, min(U - 2, 7) if U >= 5 else U)
    deep = 2 if V >= 7 else 1
    dais = [(u, fv - d) for u in range(d0, d0 + dw) for d in range(deep)]
    step_v = fv - deep
    tc = d0 + dw // 2
    R.plan_around(set(dais))
    for (u, v) in dais:
        R.put(u, 0, v, stone["block"])
    for u in range(d0, d0 + dw):
        R.put(u, 0, step_v, stone["slab"] + "[type=bottom]", walk=True)
    R.items.append("dais")
    if top >= 2:
        R.put(tc, 1, fv, f"{R.w('stairs')}[facing=@F]")
        R.put(tc, 2, fv, "gold_block")
        for s, tok in ((tc - 1, "L"), (tc + 1, "R")):
            R.put(s, 1, fv, f"{R.w('trapdoor')}[facing=@{tok},open=true]")
        if top >= 3:
            R.put(tc, 3, fv, "gold_block" if top == 3 else "chiseled_quartz_block")
        for s in (tc - 2, tc + 2):
            if 0 <= s < U and R.put(s, 1, fv, R.w2("fence")):
                R.put(s, 2, fv, R.lamp(False))
        for s in (tc - 1, tc + 1):
            R.banner(s, top, fv, "F", st["rug"])
        R.items.append("throne")
    # yol halisi
    w = 3 if U % 2 else 4
    r0 = (U - w) // 2
    for v in range(0, step_v):
        for u in range(r0, r0 + w):
            edge = u in (r0, r0 + w - 1) and w >= 3
            R.put(u, 0, v, f"{st['rug2'] if edge else st['rug']}_carpet", walk=True)
    # sutunlar
    if U >= 7 and V >= 6:
        pil = "quartz_pillar[axis=y]" if "quartz" in st["stone"] else R.w2("log") + "[axis=y]"
        for v in range(2, step_v - 1, 3):
            for u in (1, U - 2):
                if R.column(u, v, pil):
                    face = "R" if u == 1 else "L"
                    R.put(u + TV[face][0], min(2, top), v + TV[face][1], f"wall_torch[facing=@{face}]", walk=True)
        for W in ("L", "R"):
            for (u, v) in R.wall_row(W)[2:step_v - 1:3]:
                R.banner(u, top, v, W, st["rug"])
    for v in _grid(V, 4):
        if v < step_v - 1:
            R.chandelier(R.cu, v) or R.hang(R.cu, v)


# ---------------------------------------------------------------------- 17 kale buyuk salonu
@_recipe("great_hall", "Kale buyuk salonu: boydan boya ziyafet masasi + banklar, odak duvarinda yuksek masa ve efendi koltugu, dev ocak, sancaklar, halka avizeler, mesaleler",
         "medieval", 7, ("buyuk salon", "kale salonu", "ziyafet salonu", "great hall", "feast hall", "banquet hall",
                         "mead hall", "sato salonu", "sovalye salonu"), ("cobblestone", "stone_bricks", "spruce_planks"))
def _great_hall(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    tw = 2 if U >= 9 else 1
    t0 = (U - tw) // 2
    v0, v1 = (2, fv - 3) if V >= 8 else (1, fv - 2)
    table = [(t0 + i, v) for i in range(tw) for v in range(v0, v1 + 1)] if v1 >= v0 else []
    benches = [(t0 - 1, v) for v in range(v0, v1 + 1)] + [(t0 + tw, v) for v in range(v0, v1 + 1)] if table else []
    high = [(u, fv - 1) for u in range(max(1, t0 - 2), min(U - 1, t0 + tw + 2))] if V >= 6 else []
    R.plan_around(set(table) | set(benches) | set(high) | {(u, fv) for (u, _) in high})
    R.table(table, "slab")
    for (u, v) in benches:
        R.put(u, 0, v, R.w("slab") + "[type=bottom]", walk=True)
    for i, (u, v) in enumerate(sorted(table, key=lambda c: (c[1], c[0]))):
        if i % 3 == 0:
            R.lamp_on(u, 1, v, "candle")
        elif i % 5 == 1:
            R.put(u, 1, v, "cake")
    if table:
        R.items.append("feast_table")
    if high:
        R.table(high, "slab", wood=st["wood2"])
        mid = high[len(high) // 2]
        for (u, v) in high:
            R.chair(u, fv, "B", arms="sign" if (u, v) == mid else None)
        if top >= 1:
            R.put(mid[0], 1, fv, "gold_block") if top >= 2 else None
        for (u, v) in high[::2]:
            R.lamp_on(u, 1, v, "candle")
        R.items.append("high_table")
    sides = _side_walls(R)
    R.fireplace(sides[1], width=5 if V >= 10 and top >= 3 else 3, stone="stone_bricks")
    for W in ("L", "R"):
        for (u, v) in R.wall_row(W)[1::3]:
            R.banner(u, top, v, W, R.rng.choice((st["rug"], st["rug2"])))
        R.sconces(W, 3, kind="torch")
    if table:
        for v in range(v0 + 1, v1 + 1, 4):
            R.chandelier(t0, v, size=2 if (top >= 4 and U >= 9) else 1)
    R.std_lights() if not table else None


# ---------------------------------------------------------------------- 18 cephanelik
@_recipe("armory", "Cephanelik / silah odasi: mizrak raflari (paratoner), kalkan duvari (sancaklar), egitim mankenleri, ok hedefi, ors + bileği tasi + demirci masasi, silah sandiklari",
         "medieval", 7, ("cephanelik", "silah odasi", "silahhane", "armory", "armoury", "arsenal", "weapon room",
                         "zirh odasi", "muhimmat"), ("cobblestone", "stone_bricks", "spruce_planks"))
def _armory(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    tgt = (R.cu, fv)
    R.plan_around({tgt, (R.cu, fv - 1)})
    if R.put(R.cu, 0, fv, "hay_block") and top >= 1:
        R.put(R.cu, 1, fv, "target")
        R.items.append("archery_target")
    colors = (st["rug"], st["rug2"], "blue", "white", "black")
    for W in ("L", "R", "F"):
        face = OPPT[W]
        for i, (u, v) in enumerate(R.wall_row(W)):
            if not R.free(u, 0, v) or abs(u - R.cu) <= 1 and W == "F":
                continue
            k = i % 3
            if k == 0:
                R.put(u, 0, v, "waxed_lightning_rod[facing=up]")
                if top >= 2:
                    R.put(u, 1, v, "waxed_lightning_rod[facing=up]")
            elif k == 1:
                R.put(u, 0, v, f"barrel[facing=up]")
                R.put(u, 1, v, "waxed_lightning_rod[facing=up]") if top >= 2 else None
            else:
                R.put(u, 0, v, "chest[facing=@" + face + "]")
            if top >= 2 and R.wall_ok(u, top, v, W):
                R.banner(u, top, v, W, colors[i % len(colors)])
    R.items.append("weapon_racks")
    for (u, v) in ((R.cu - 2, R.cv), (R.cu + 2, R.cv)):
        if top >= 2 and R.free(u, 0, v) and R.free(u, 1, v) and R.free(u, 2, v):
            R.put(u, 0, v, R.w("fence"))
            R.put(u, 1, v, "hay_block")
            R.put(u, 2, v, "carved_pumpkin[facing=@B]")
            R.items.append("training_dummy")
    for (u, v), s in zip(((1, 1), (2, 1), (U - 2, 1)), ("anvil[facing=@F]", "grindstone[face=floor,facing=@F]", "smithing_table")):
        R.put(u, 0, v, s)
    R.std_lights()
    R.sconces("B", 4)


# ---------------------------------------------------------------------- 19 osmanli bas oda
@_recipe("bas_oda", "Osmanli bas oda: duvar boyu kirmizi sedirler, odak duvarinda ocak (kulah) ve iki yanda nisler (fener/mum), Iznik cini frizi, ortada kilim ve bakir sini, tavanda gobek + zincirli kandil",
         "ottoman", 6, ("bas oda", "basoda", "osmanli oda", "osmanli odasi", "sedir", "sedirli oda", "divanhane",
                        "ottoman room", "turkish room", "selamlik", "harem odasi", "konak odasi"),
         ("spruce_planks", "white_terracotta", "dark_oak_planks"))
def _bas_oda(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    extra = []
    for (ue, ve, tin) in R.entries:
        for tok in PERP[tin]:
            extra.append((ue + TV[tok][0], ve + TV[tok][1]))
    sini = (R.cu, min(R.cv + 1, fv - 2))
    R.plan_around({sini}, extra=extra)
    ss = stone_parts(R.db, "smooth_sandstone")
    # ocak (odak duvari)
    if U >= 5 and top >= 2:
        hc = R.cu
        cells = [(hc - 1, fv), (hc, fv), (hc + 1, fv)]
        if all(R.free(u, 0, v) for (u, v) in cells):
            R.put(hc - 1, 0, fv, ss["block"])
            R.put(hc + 1, 0, fv, ss["block"])
            R.put(hc, 0, fv, "campfire[facing=@B,lit=true]")
            for (u, v) in cells:
                R.put(u, 1, v, f"{ss['stairs']}[facing=@F,half=top]")
            for h in range(2, top + 1):
                R.put(hc, h, fv, ss["block"])
                if h == 2:
                    R.put(hc - 1, h, fv, f"{ss['stairs']}[facing=@R]")
                    R.put(hc + 1, h, fv, f"{ss['stairs']}[facing=@L]")
            R.items.append("ocak")
        # nis dolaplari
        for u in (hc - 2, hc + 2, hc - 3, hc + 3):
            if 0 <= u < U and R.free(u, 0, fv) and R.free(u, 1, fv):
                R.put(u, 0, fv, R.w("planks"))
                R.lamp_on(u, 1, fv, "lamp" if abs(u - hc) == 2 else "candle")
                R.put(u, 2, fv, f"{R.w('stairs')}[facing=@F,half=top]")
                for h in range(3, top + 1):
                    R.put(u, h, fv, R.w("planks"))
                R.items.append("nis")
    # sedirler
    cush = st["fabric"]
    for W in ("L", "R", "B", "F"):
        for i, (u, v) in enumerate(R.wall_row(W)):
            col = st["fabric2"] if (i % 4 == 0) else cush
            if R.free(u, 0, v):
                R.put(u, 0, v, f"{col}_wool_stairs[facing=@{W}]")
    R.items.append("sedir")
    # Iznik cini frizi
    tiles = ("cyan_glazed_terracotta", "light_blue_glazed_terracotta", "white_glazed_terracotta")
    if top >= 2:
        for W in ("L", "R", "B"):
            for i, (u, v) in enumerate(R.wall_row(W)):
                if R.wall_ok(u, 2, v, W) and R.free(u, 2, v, walk=True):
                    R.put(u, 2, v, f"{tiles[i % 3]}[facing=@{('F', 'R', 'B', 'L')[i % 4]}]", walk=True)
        R.items.append("cini")
    R.rug(1, 1, U - 2, V - 2, fill=st["rug"], border=st["rug2"], pattern="kilim", accent=st["rug3"])
    if R.free(*sini[:1], 0, sini[1]):
        R.put(sini[0], 0, sini[1], "waxed_cut_copper_slab[type=bottom]", walk=True)
        R.items.append("sini")
    # gobek + kandil
    if top >= 3:
        for du in (-1, 0, 1):
            for dv in (-1, 0, 1):
                if du or dv:
                    R.put(R.cu + du, top, R.cv + dv, f"{R.w2('trapdoor')}[half=top,facing=@F]", walk=True)
        R.put(R.cu, top, R.cv, R.chain(), walk=True)
        R.put(R.cu, top - 1, R.cv, R.lamp(True), walk=True)
        R.items.append("gobek")
    else:
        R.hang(R.cu, R.cv)
    if U >= 9 or V >= 9:
        for (u, v) in ((R.cu - 3, R.cv), (R.cu + 3, R.cv)):
            R.hang(u, v)


# ---------------------------------------------------------------------- 20 cami harimi
@_recipe("prayer_hall", "Cami harimi (saygili, yazisiz/sembolsuz): kible duvarinda mihrap nisi (sutunlar, sivri kemer, nis kandili), sagda mermer minber basamaklari, kibleye paralel saf halilari, giriste ayakkabilik, halka avizeler",
         "ottoman", 8, ("cami", "mescit", "camii", "harim", "namaz", "namazgah", "mosque", "prayer hall", "prayer room",
                        "masjid", "ibadethane"), ("smooth_sandstone", "white_terracotta", "smooth_sandstone"))
def _prayer_hall(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    qz = stone_parts(R.db, "quartz")
    mw = 1 if U % 2 else 2
    m0 = (U - mw) // 2
    frame = [(m0 - 1, fv), (m0 + mw, fv)]
    niche = [(m0 + i, fv) for i in range(mw)]
    n_steps = max(1, min(3, top - 1))
    mu = m0 + mw + 2
    minbar = [(mu, fv - k) for k in range(0, n_steps + 1)] if (mu <= U - 2 and V >= n_steps + 3 and top >= 2) else []
    R.plan_around(set(frame) | set(niche) | set(minbar) | {(u, fv - 1) for (u, _) in niche})
    if top >= 2 and m0 >= 1 and m0 + mw < U:
        for (u, v) in frame:
            for h in range(0, 3):
                R.put(u, h, v, "quartz_pillar[axis=y]")
        if mw == 1:
            R.put(m0, 2, fv, "chiseled_quartz_block")
            R.put(m0, 1, fv, R.lamp(True))
        else:
            R.put(m0, 2, fv, f"{qz['stairs']}[facing=@L,half=top]")
            R.put(m0 + 1, 2, fv, f"{qz['stairs']}[facing=@R,half=top]")
            R.put(m0, 0, fv, R.lamp(False))
        for h in range(3, top + 1):
            for (u, v) in frame + niche:
                R.put(u, h, v, "chiseled_quartz_block" if (u, v) in niche and h == 3 else qz["block"])
        for (u, v) in niche:
            R.put(u, 0, v, f"{st['rug2']}_carpet", walk=True)
        R.items.append("mihrab")
    if minbar:
        for k in range(1, n_steps + 1):
            u, v = mu, fv - k
            hs = n_steps - k
            for h in range(0, hs):
                R.put(u, h, v, qz["block"])
            R.put(u, hs, v, f"{qz['stairs']}[facing=@F]")
        for h in range(0, n_steps):
            R.put(mu, h, fv, qz["block"])
        if top >= n_steps + 2:
            R.put(mu, n_steps, fv, "quartz_pillar[axis=y]") if False else None
        R.items.append("minbar")
    # saf halilari: kibleye paralel siralar
    main, line = st["rug"], st["rug2"]
    for v in range(0, fv + 1):
        col = line if v % 2 else main
        for u in range(U):
            if v == 0 and R.reserved(u, v):
                continue
            R.put(u, 0, v, f"{col}_carpet", walk=True)
    R.items.append("saf_halisi")
    # ayakkabilik
    for (u, v) in [c for c in R.wall_row("B") if R.free(c[0], 1, c[1]) and not R.reserved(*c)][:4]:
        x, y, z = R.P(u, 0, v)
        R.remove_xyz(x, y, z)
        R.put(u, 0, v, R.w("slab") + "[type=top]")
        if top >= 2:
            R.put(u, 1, v, R.w("slab") + "[type=top]")
    R.items.append("shoe_rack")
    if top >= 4:
        R.chandelier(R.cu, R.cv, size=2)
        for v in _grid(V, 5):
            for u in _grid(U, 5):
                if abs(u - R.cu) + abs(v - R.cv) >= 4:
                    R.hang(u, v)
    else:
        R.pendant_grid(4)
    for W in ("L", "R"):
        R.sconces(W, 4, kind="lantern")


# ---------------------------------------------------------------------- 21 japon cay odasi
@_recipe("tea_room", "Japon cay odasi: tatami deseni (bambu kapaklar, donusumlu dokular), tokonoma (direk, bos parsomen, ikebana), shoji paneller (hus kapaklar) ve direkler, alcak masa + minderler, andon, shoji tavan isiklari",
         "japanese", 6, ("cay odasi", "japon", "japon odasi", "tatami", "tea room", "tea house", "chashitsu", "washitsu",
                         "zen", "japanese room", "dojo"), ("spruce_planks", "white_terracotta", "spruce_planks"))
def _tea_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    tw = 2 if U >= 5 else 1
    toko = [(i, fv) for i in range(tw)]
    post = (tw, fv)
    tbl = [(R.cu, min(R.cv + 1, fv - 2))] + ([(R.cu + 1, min(R.cv + 1, fv - 2))] if U >= 8 else [])
    R.plan_around(set(toko) | {post} | set(tbl))
    dark = st["wood2"]
    if top >= 1:
        R.column(post[0], post[1], wood_block(st["wood"], "stripped_log") + "[axis=y]")
        for (u, v) in toko:
            R.put(u, top, v, wood_block(dark, "slab") + "[type=top]", walk=True)
        R.banner(0, max(1, top - 1), fv, "F", "white")
        R.put(tw - 1, 0, fv, "potted_cherry_sapling" if R.rng.random() < 0.5 else "potted_flowering_azalea_bush")
        if tw == 2:
            R.put(0, 0, fv, f"{wood_block(dark, 'trapdoor')}[half=bottom,facing=@F]", walk=True)
        R.items.append("tokonoma")
    # shoji duvarlar + direkler
    for W in ("L", "R"):
        for i, (u, v) in enumerate(R.wall_row(W)):
            if i % 3 == 0 and 0 < i < V - 1:
                R.column(u, v, wood_block(st["wood"], "stripped_log") + "[axis=y]")
                continue
            for h in range(0, max(1, min(top, 2))):
                R.put(u, h, v, f"birch_trapdoor[facing=@{OPPT[W]},open=true]")
    R.items.append("shoji")
    for (u, v) in tbl:
        R.put(u, 0, v, wood_block(dark, "slab") + "[type=bottom]")
    if tbl:
        R.items.append("chabudai")
        cush = R.rng.choice(("red", "purple", "blue"))
        for (u, v) in tbl:
            for tok in ("L", "R", "F", "B"):
                a, b = u + TV[tok][0], v + TV[tok][1]
                if (a, b) not in tbl and not R.reserved(a, b):
                    R.put(a, 0, b, f"{cush}_carpet", walk=True)
        R.put(tbl[0][0] - 1, 0, tbl[0][1] + 1, "decorated_pot[facing=@B]")
    # andon
    for (u, v) in ((0, 0), (U - 1, 0)):
        R.put(u, 0, v, R.lamp(False))
    # tatami
    k = 0
    for v in range(V):
        off = v % 2
        for u0 in range(-off, U, 2):
            face = "@R" if k % 2 == 0 else "@F"
            k += 1
            for u in (u0, u0 + 1):
                if R.in2(u, v) and R.free(u, 0, v, walk=True):
                    R.put(u, 0, v, f"bamboo_trapdoor[half=bottom,facing={face}]", walk=True)
    R.items.append("tatami")
    R.std_lights(step=3)


# ---------------------------------------------------------------------- 22 ahir
@_recipe("barn", "Ahir / samanlik ici: ortada genis koridor, iki yanda citli bolmeler (kapili), samanlar ve yemlikler (kompostlu kutu) + su teknesi (kazan), arka duvarda saman yigini, kirisler ve asili fenerler",
         "rustic", 5, ("ahir", "samanlik", "barn", "stable", "ahir ici", "stall", "at ahiri", "agil", "kumes", "cattle shed",
                       "hayloft"), ("spruce_planks", "spruce_planks", "spruce_planks"))
def _barn(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    aisle = {(R.cu, v) for v in range(V)} | ({(R.cu + 1, v) for v in range(V)} if U % 2 == 0 and U >= 8 else set())
    R.plan(extra=sorted(aisle))
    fence, gate = R.w("fence"), R.w("fence_gate")
    sd = max(1, min(3, (U - len({u for u, _ in aisle}) - 2) // 2))
    for side in ("L", "R"):
        u_wall = 0 if side == "L" else U - 1
        inward = 1 if side == "L" else -1
        u_front = u_wall + inward * sd
        if any((u_front, v) in aisle for v in range(V)) or sd < 1:
            u_front = u_wall
        for s0 in range(1, fv - 1, 3):
            stall = range(s0, min(s0 + 3, fv))
            for k in range(sd + 1):
                R.put(u_wall + inward * k, 0, s0 - 1, fence)
            for v in stall:
                if v == s0 + 1:
                    R.put(u_front, 0, v, f"{gate}[facing=@{'R' if side == 'L' else 'L'}]")
                else:
                    R.put(u_front, 0, v, fence)
            R.put(u_wall, 0, s0, "hay_block[axis=@AV]")
            R.put(u_wall, 0, s0 + 1, "composter[level=7]") if sd >= 1 else None
            R.put(u_wall, 0, min(s0 + 2, fv - 1), "water_cauldron[level=3]")
            for v in stall:
                for k in range(1, sd):
                    R.put(u_wall + inward * k, 0, v, "yellow_carpet", walk=True)
            if top >= 1:
                R.put(u_front, 1, s0 - 1, R.lamp(False)) if R.free(u_front, 1, s0 - 1) else None
        R.items.append("stalls")
    for u in range(U):
        if (u, fv) in aisle:
            continue
        hmax = max(0, min(top - 1, 2 - abs(u - R.cu) // 3))
        for h in range(0, hmax + 1):
            R.put(u, h, fv, "hay_block[axis=@AU]")
    R.items.append("hay")
    if top >= 3:
        for v in range(1, V - 1, 4):
            for u in range(U):
                R.put(u, top, v, R.w("stripped_log") + "[axis=@AU]", walk=True)
            for u in (R.cu - 2, R.cu + 2):
                R.hang(u, v - 1) if False else None
        R.items.append("beams")
    R.pendant_grid(4)


# ---------------------------------------------------------------------- 23 sera
@_recipe("greenhouse", "Sera: duvar boyu toprak tarhlar (cicek, egrelti, calilar, uzun cicekler), saksi tezgahi + kompost + su, ortada nilufer havuzu, tavandan sarkan isikli magara sarmaşiklari",
         "nordic", 7, ("sera", "limonluk", "kis bahcesi", "greenhouse", "conservatory", "orangery", "glasshouse", "botanik",
                       "fidanlik", "nursery garden"), ("mud_bricks", "white_terracotta", "glass"))
def _greenhouse(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    pond = []
    if U >= 7 and V >= 7:
        pu, pv = R.cu - 1, R.cv + 1
        pond = [(pu + a, pv + b) for a in range(2) for b in range(2)]
    rim = {(u + a, v + b) for (u, v) in pond for a in (-1, 0, 1) for b in (-1, 0, 1)} - set(pond)
    R.plan_around(set(pond) | rim)
    soils = ("podzol", "rooted_dirt", "moss_block", "grass_block")
    flowers = ("poppy", "dandelion", "cornflower", "allium", "azure_bluet", "red_tulip", "orange_tulip", "pink_tulip",
               "oxeye_daisy", "lily_of_the_valley", "fern", "short_grass", "bush", "firefly_bush", "blue_orchid", "torchflower")
    tall = ("rose_bush", "peony", "lilac", "sunflower", "large_fern")
    depth = 2 if U >= 9 else 1
    for W in ("L", "R"):
        for (u0, v) in R.wall_row(W):
            for k in range(depth):
                u = u0 + (k if W == "L" else -k)
                if not R.free(u, 0, v) or not R.free(u, 1, v):
                    continue
                R.put(u, 0, v, R.rng.choice(soils))
                r = R.rng.random()
                if r < 0.18 and top >= 2 and R.free(u, 2, v):
                    t = R.rng.choice(tall)
                    R.put(u, 1, v, f"{t}[half=lower]")
                    R.put(u, 2, v, f"{t}[half=upper]")
                elif r < 0.28:
                    R.put(u, 1, v, R.rng.choice(("azalea", "flowering_azalea")))
                elif r < 0.92:
                    R.put(u, 1, v, R.rng.choice(flowers))
        R.items.append("planters")
    bench = R.pick("F", max(1, min(U - 2, 5)), 0, 0, min_len=1)
    for i, (u, v) in enumerate(bench):
        k = i % 4
        if k == 1:
            R.put(u, 0, v, "composter[level=4]")
        elif k == 3:
            R.put(u, 0, v, "water_cauldron[level=3]")
        else:
            R.put(u, 0, v, R.w("slab") + "[type=top]")
            R.plant(u, 1, v)
    R.items.append("potting_bench")
    if pond:
        for (u, v) in rim:
            R.put(u, 0, v, R.rng.choice(("mossy_cobblestone", "moss_block", "mossy_stone_bricks")))
        if all(R.b.get_id(*R.P(u, 0, v)) > 1 or (u, v) in pond for (u0, v0) in pond for (u, v) in
               ((u0 + 1, v0), (u0 - 1, v0), (u0, v0 + 1), (u0, v0 - 1))):
            for (u, v) in pond:
                R.put(u, 0, v, "water")
            R.put(pond[0][0], 1, pond[0][1], "lily_pad")
            R.put(pond[-1][0], 1, pond[-1][1], "lily_pad")
            R.items.append("pond")
        for (u, v) in sorted(rim)[::3]:
            R.put(u, 1, v, R.rng.choice(flowers[:10]))
    if top >= 3:
        for u in (1, U - 2):
            for v in _grid(V, 3):
                x, z = R.xz(u, v)
                if R.center_ok(x, R.y1 + 1, z, "down") and R.free(u, top, v, walk=True) and R.free(u, top - 1, v, walk=True):
                    R.put(u, top, v, "cave_vines_plant[berries=false]", walk=True)
                    R.put(u, top - 1, v, "cave_vines[berries=true,age=25]", walk=True)
        R.items.append("glow_vines")
    R.std_lights()


# ---------------------------------------------------------------------- 24 futuristik kontrol odasi
@_recipe("control_room", "Futuristik kontrol odasi: arkadan aydinlatmali dev veri ekrani, operator konsollari (gosterge, salter, dugme, kizilotesi panel), kaptan koltugu, sunucu dolaplari + LED cubuklar, zeminde isik seritleri",
         "futuristic", 9, ("kontrol odasi", "kontrol merkezi", "komuta", "komuta merkezi", "kopru", "control room",
                           "command center", "bridge", "mission control", "operasyon odasi", "sunucu odasi", "server room"),
         ("light_gray_concrete", "white_concrete", "white_concrete"))
def _control_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    s0, sw = R.csym(U, max(1, min(U - 2, 7)))
    screen = [(u, fv) for u in range(s0, s0 + sw)]
    cv_ = max(1, fv - 2)
    consoles = [(u, cv_) for u in range(max(0, s0), min(U, s0 + sw))]
    R.plan_around(set(consoles) | set(screen))
    sh = max(1, min(top, 3))
    data = ("cyan_stained_glass", "light_blue_stained_glass", "blue_stained_glass", "black_stained_glass")
    for i, (u, v) in enumerate(screen):
        bar = R.rng.randint(1, sh)
        for h in range(1, sh + 1):
            g = data[0] if h <= bar else data[3]
            if h == sh and i % 2:
                g = data[1]
            R.put(u, h, v, g)
            R.put_wallcell(u, h, v, "F", "sea_lantern")
        R.put(u, 0, v, "black_concrete")
    R.items.append("data_screen")
    panel = ("daylight_detector", "lever[face=floor,facing=@F]", "repeater[facing=@B]", "stone_button[face=floor,facing=@F]",
             "comparator[facing=@B]", "heavy_weighted_pressure_plate")
    for i, (u, v) in enumerate(consoles):
        if R.put(u, 0, v, "smooth_quartz_slab[type=top]"):
            R.put(u, 1, v, panel[i % len(panel)])
    for (u, v) in consoles[::2]:
        R.chair(u, v - 1, "F", mat="white_concrete_stairs", arms=None)
    R.items.append("consoles")
    cap = (R.hub[0] + 1, R.hub[1]) if R.free(R.hub[0] + 1, 0, R.hub[1]) else (R.hub[0] - 1, R.hub[1])
    if V >= 6 and R.chair(cap[0], cap[1], "F", mat="quartz_stairs", arms="trapdoor"):
        R.items.append("captain_chair")
    racks = ("observer[facing=@X]", "crafter", "waxed_copper_grate", "dispenser[facing=@X]", "polished_deepslate")
    for W in ("L", "R"):
        face = OPPT[W]
        for i, (u, v) in enumerate(R.wall_row(W)):
            if v >= cv_ or v == 0 or not R.free(u, 0, v):
                continue
            if i % 3 == 0:
                if R.put(u, 1, v, f"end_rod[facing=@{face}]", walk=False) and False:
                    pass
                continue
            for h in range(0, min(top, 2) + 1):
                R.put(u, h, v, racks[(i + h) % len(racks)].replace("@X", "@" + face))
        R.items.append("server_racks")
    for v in range(1, cv_ - 1, 2):
        for u in (R.hub[0] - 1, R.hub[0] + 1):
            if R.in2(u, v) and R.free(u, 0, v, walk=True):
                R.put_floor(u, v, "sea_lantern")
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 25 futuristik laboratuvar
@_recipe("lab", "Futuristik laboratuvar: beyaz deney tezgahlari (cam tupler, beher kazanlar, bunzen end rod, kristal ornekler), lab tabureleri, isikli numune tanklari, karantina kafesi (fener isigi), bilgisayar ve dolaplar",
         "futuristic", 9, ("laboratuvar", "lab", "laboratory", "arastirma", "deney odasi", "research lab", "science lab",
                           "bilim odasi", "kimya", "alchemy lab", "simya"), ("light_gray_concrete", "white_concrete", "white_concrete"))
def _lab(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    rows = [v for v in (R.cv + 1, R.cv + 3) if v < fv - 1] if V >= 7 else [min(R.cv + 1, fv - 1)]
    benches = [(u, v) for v in rows for u in range(1 if U >= 5 else 0, U - 1 if U >= 5 else U)]
    R.plan_around(set(benches))
    eq = ("brewing_stand", "end_rod[facing=up]", "amethyst_cluster[facing=up]", "flower_pot", "potted_crimson_fungus",
          "brewing_stand", "redstone_torch", "potted_brown_mushroom")
    for i, (u, v) in enumerate(benches):
        if R.put(u, 0, v, "white_concrete"):
            if i % 2 == 0 or R.rng.random() < 0.3:
                s = eq[(i // 2) % len(eq)]
                if s.startswith("potted") or s == "flower_pot":
                    R.plant(u, 1, v, s)
                else:
                    R.put(u, 1, v, s)
    for v in rows:
        for u in range(1, U - 1, 3):
            R.chair(u, v - 1, "F", mat="smooth_quartz_stairs")
    R.items.append("lab_benches")
    tanks = R.pick("F", max(1, min(4, U - 2)), 0, min(top, 2), min_len=1, backed=False)
    for i, (u, v) in enumerate(tanks):
        if i % 2 == 0:
            R.put(u, 0, v, "sea_lantern")
            for h in range(1, min(top, 2) + 1):
                R.put(u, h, v, R.rng.choice(("light_blue_stained_glass", "cyan_stained_glass", "lime_stained_glass")))
        else:
            R.put(u, 0, v, "water_cauldron[level=3]")
            if top >= 2:
                R.put(u, 2, v, "observer[facing=@B]")
    R.items.append("specimen_tanks")
    sides = _side_walls(R)
    cage_side = sides[1]
    cu_ = 0 if cage_side == "L" else U - 1
    inward = 1 if cage_side == "L" else -1
    if V >= 6 and U >= 6 and R.free(cu_, 0, 1) and R.free(cu_ + inward, 0, 1) and R.free(cu_ + inward, 0, 2) \
            and not R.reserved(cu_ + inward, 1):
        R.put(cu_, 0, 1, "beacon")
        for (u, v) in ((cu_ + inward, 1), (cu_ + inward, 2), (cu_, 2)):
            for h in range(0, min(top, 2)):
                R.put(u, h, v, "iron_bars")
        R.items.append("containment_cage")
    pc = R.pick(sides[0], 3, 0, 1, min_len=1)
    for i, (u, v) in enumerate(pc):
        R.put(u, 0, v, ("iron_block", "crafter", "observer[facing=@" + OPPT[sides[0]] + "]")[i % 3])
        R.put(u, 1, v, ("iron_block", "observer[facing=@" + OPPT[sides[0]] + "]", "dropper[facing=@" + OPPT[sides[0]] + "]")[i % 3])
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 26 dukkan / pazar
@_recipe("shop", "Dukkan / pazar tezgahi: buyuk odada cizgili tenteli pazar tezgahlari, kucuk odada tezgah + zil + defter (kursu); raflarda urunler (kasalar, balkabagi, kavun, petek, saksilar, kupler)",
         "rustic", 7, ("dukkan", "magaza", "pazar", "pazar tezgahi", "bakkal", "manav", "carsi", "shop", "store",
                       "market", "market stall", "stall", "bazaar", "bazar", "general store", "esnaf"),
         ("spruce_planks", "white_terracotta", "spruce_planks"))
def _shop(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    goods = ("barrel[facing=up]", "pumpkin", "melon", "hay_block", "bee_nest[facing=@F]", "dried_kelp_block",
             "chest[facing=@F]", "composter[level=8]")
    market = U >= 10 and V >= 8 and top >= 3
    if market:
        stalls = []
        for side in ("L", "R"):
            uw = 0 if side == "L" else U - 1
            uc = 1 if side == "L" else U - 2
            for s0 in range(1, fv - 1, 4):
                cells = [(uw, v) for v in range(s0, min(s0 + 3, fv))] + [(uc, v) for v in range(s0, min(s0 + 3, fv))]
                stalls.append((side, s0, cells))
        R.plan_around({c for (_, _, cs) in stalls for c in cs})
        stripes = R.rng.choice((("red", "white"), ("blue", "white"), ("green", "yellow"), ("orange", "white")))
        for side, s0, cells in stalls:
            face = OPPT[side]
            uw = 0 if side == "L" else U - 1
            uc = 1 if side == "L" else U - 2
            for v in range(s0, min(s0 + 3, fv)):
                g = R.rng.choice(goods).replace("@F", "@" + face)
                R.put(uw, 0, v, g)
                if R.put(uc, 0, v, R.w("slab") + "[type=top]"):
                    R.plant(uc, 1, v) if R.rng.random() < 0.5 else R.lamp_on(uc, 1, v, "candle")
                for k, u in enumerate((uw, uc)):
                    R.put(u, top, v, f"{stripes[(v - s0) % 2]}_wool", walk=True)
            R.put(uc + (1 if side == "L" else -1), 0, s0, R.w("fence"))
            for h in range(1, top):
                R.put(uc + (1 if side == "L" else -1), h, s0, R.w("fence"), walk=True)
        R.items.append("market_stalls")
        R.pendant_grid(4)
        return
    cv_ = fv - 2 if V >= 6 else fv - 1
    counter = [(u, cv_) for u in range(0, U - 1)]
    R.plan_around(set(counter))
    for i, (u, v) in enumerate(counter):
        if i == 1 and R.put(u, 0, v, "lectern[facing=@F,has_book=true]"):
            continue
        if R.put(u, 0, v, R.w("planks") if i % 2 else "barrel[facing=@B]"):
            if i == 0:
                R.put(u, 1, v, "bell[attachment=floor,facing=@B]")
            elif i % 3 == 2:
                R.plant(u, 1, v)
    R.put(U - 1, 0, cv_, R.w("fence_gate") + "[facing=@F]")
    R.items.append("counter")
    for W in ("F", "L", "R"):
        face = OPPT[W]
        for i, (u, v) in enumerate(R.wall_row(W)):
            if not R.free(u, 0, v):
                continue
            R.put(u, 0, v, R.rng.choice(goods).replace("@F", "@" + face))
            if top >= 1:
                if R.db.has_block(R.w("shelf")) and i % 2 == 0:
                    R.put(u, 1, v, R.w("shelf") + f"[facing=@{face}]")
                else:
                    R.put(u, 1, v, R.w("slab") + "[type=top]")
                    if top >= 2:
                        R.put(u, 2, v, R.rng.choice(("decorated_pot[facing=@" + face + "]", "flower_pot", "potted_cactus",
                                                     "lantern[hanging=false]")))
    R.items.append("shelves")
    R.std_lights()


# ---------------------------------------------------------------------- 27 kafe
@_recipe("cafe", "Kafe: kahve tezgahi (espresso makinesi = simya standi, firin, evye), camli pasta vitrini + pastalar, kara tahta menu (siyah sancak), yuvarlak masalar + ikili sandalyeler, pencere bari, sarkit lambalar",
         "industrial", 8, ("kafe", "cafe", "kahve", "kahvehane", "coffee", "coffee shop", "pastane", "bakery", "bistro",
                           "cay bahcesi", "canteen", "kantin"), ("spruce_planks", "white_terracotta", "spruce_planks"))
def _cafe(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    big = U >= 8 and V >= 7
    cv_ = fv - 2 if big else fv
    counter = [(u, cv_) for u in range(1 if big else 0, U - 1 if big else U)]
    R.plan_around(set(counter) | ({(u, fv - 1) for u in range(U)} if big else set()))
    stuff = ("brewing_stand", "cake", "flower_pot", "brewing_stand", "candle")
    for i, (u, v) in enumerate(counter):
        if i < 2 and big:
            if R.put(u, 0, v, "glass"):
                R.put(u, 1, v, "cake")
            continue
        if R.put(u, 0, v, R.w2("planks") if st["wood2"] in WOODS else "spruce_planks"):
            s = stuff[i % len(stuff)]
            if s == "candle":
                R.lamp_on(u, 1, v, "candle")
            elif s == "flower_pot":
                R.plant(u, 1, v)
            else:
                R.put(u, 1, v, s)
    R.items.append("counter")
    if big:
        for i, (u, v) in enumerate(R.wall_row("F")):
            if not R.free(u, 0, v):
                continue
            R.put(u, 0, v, ("smoker[facing=@B,lit=false]", "water_cauldron[level=3]", "barrel[facing=@B]",
                            "barrel[facing=@B]")[i % 4])
            if top >= 2 and i % 3 == 1:
                R.banner(u, top, v, "F", "black")
        R.items.append("menu_board")
    tv_max = cv_ - 2
    for tv in range(1, max(1, tv_max), 3):
        for tu in _grid(U, 4):
            if R.pedestal(tu, tv, "plate"):
                R.chair(tu - 1, tv, "R")
                R.chair(tu + 1, tv, "L")
                R.hang(tu, tv)
    sides = _side_walls(R)
    for W in sides:
        win = [c for c in R.wall_row(W) if R.window_at(c[0], 1, c[1], W) and c[1] < cv_ - 1]
        for (u, v) in win[:3]:
            if R.table([(u, v)], "slab"):
                R.chair(u + TV[OPPT[W]][0], v + TV[OPPT[W]][1], W)
        if win:
            R.items.append("window_bar")
            break
    R.big_plant(0, 0)
    R.big_plant(U - 1, 0)
    R.std_lights()


# ---------------------------------------------------------------------- 28 spor salonu
@_recipe("gym", "Spor salonu: kosu bantlari (demir kapak bant + konsol), agirlik rafi (kettlebell = agir cekirdek, ors), squat rafi (cit + zincir bar), kum torbasi (zincirli yun), yoga minderleri, dolaplar (demir kapi), su sebili",
         "modern", 9, ("spor salonu", "spor", "fitness", "gym", "gymnasium", "jimnastik", "antrenman", "workout",
                       "boks", "training room"), ("smooth_stone", "white_concrete", "smooth_quartz"))
def _gym(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    tm = [u for u in range(1, U - 1, 2)][:3] if U >= 4 else [0]
    belts = [(u, fv - k) for u in tm for k in (0, 1, 2)]
    R.plan_around(set(belts))
    for u in tm:
        if R.free(u, 0, fv) and R.free(u, 0, fv - 1) and R.free(u, 0, fv - 2):
            R.put(u, 0, fv, "polished_blackstone_wall")
            if top >= 1:
                R.put(u, 1, fv, "daylight_detector")
            R.put(u, 0, fv - 1, "iron_trapdoor[half=bottom,facing=@F]")
            R.put(u, 0, fv - 2, "iron_trapdoor[half=bottom,facing=@F]")
            R.items.append("treadmill")
    sides = _side_walls(R)
    wr = R.pick(sides[0], 3, 0, 0, min_len=1)
    for i, (u, v) in enumerate(wr):
        if R.put(u, 0, v, "polished_blackstone_slab[type=top]"):
            R.put(u, 1, v, "heavy_core" if i % 2 == 0 else "anvil[facing=@" + ("F" if sides[0] in "LR" else "R") + "]")
    if wr:
        R.items.append("weights")
    sq = R.pick(sides[1], 3, 0, 1, min_len=3)
    if len(sq) == 3 and top >= 2:
        (a, b), (c, d), (e, f) = sq
        ax = "@AV" if sides[1] in ("L", "R") else "@AU"
        R.puts([(a, 0, b, "iron_bars"), (a, 1, b, "iron_bars"), (e, 0, f, "iron_bars"), (e, 1, f, "iron_bars")])
        R.put(c, 1, d, R.chain(ax))
        R.items.append("squat_rack")
    if top >= 3:
        pu, pv = (U - 2, 1) if not R.reserved(U - 2, 1) else (1, 1)
        if R.free(pu, 1, pv) and R.free(pu, 2, pv) and R.free(pu, 0, pv):
            x, z = R.xz(pu, pv)
            if R.center_ok(x, R.y1 + 1, z, "down"):
                for h in range(3, top + 1):
                    R.put(pu, h, pv, R.chain(), walk=True)
                R.put(pu, 2, pv, "red_wool", walk=True)
                R.put(pu, 1, pv, "red_wool")
                R.items.append("punching_bag")
    mats = ("blue", "black", "light_blue")
    m = R.rng.choice(mats)
    R.rug(max(1, R.cu - 2), 1, min(U - 2, R.cu + 2), max(1, min(3, fv - 3)), fill=m, border="gray")
    lk = R.pick("B", 3, 0, 1, min_len=2)
    if len(lk) >= 2:
        for i, (u, v) in enumerate(lk):
            if i == 0 or i == len(lk) - 1:
                R.put(u, 0, v, "iron_block")
                R.put(u, 1, v, "iron_block")
            else:
                R.put(u, 0, v, "iron_door[facing=@B,half=lower,hinge=left]")
                R.put(u, 1, v, "iron_door[facing=@B,half=upper,hinge=left]")
        R.items.append("lockers")
    wc = R.pick(sides[1], 1, 0, 1, min_len=1)
    if wc:
        u, v = wc[0]
        R.put(u, 0, v, "iron_block")
        R.put(u, 1, v, "light_blue_stained_glass")
        R.items.append("water_cooler")
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 29 kapali havuz
@_recipe("pool_room", "Kapali havuz: tam blok yurume guvertesi (kapida yarim basamak), arka yarida havuz (su), havuz tabaninda gomulu fenerler, merdiven (su ici), sezlonglar, saksi bitkiler, havlu sancaklari",
         "modern", 8, ("havuz", "kapali havuz", "yuzme havuzu", "pool", "indoor pool", "swimming pool", "spa", "kaplica",
                       "aquatic", "natatorium"), ("smooth_stone", "white_terracotta", "smooth_quartz"))
def _pool_room(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    deck = stone_parts(R.db, st["stone"])["block"]
    R.plan()
    pool = []
    if U >= 3 and V >= 4:
        pv0 = max(R.cv + 1, 1)
        pv1 = fv - 1 if V >= 5 else fv
        pool = [(u, v) for u in range(1, U - 1) for v in range(pv0, pv1 + 1)]
    entries = {(ue, ve) for (ue, ve, _) in R.entries}
    if top >= 2:
        R.min_hang = 3
        for u in range(U):
            for v in range(V):
                if (u, v) in pool:
                    continue
                if (u, v) in entries:
                    R.put(u, 0, v, stone_parts(R.db, st["stone"])["slab"] + "[type=bottom]", walk=True)
                else:
                    R.put(u, 0, v, deck, walk=True)
        R.items.append("deck")
    else:
        rim = {(u + a, v + b) for (u, v) in pool for a in (-1, 0, 1) for b in (-1, 0, 1)} - set(pool)
        for (u, v) in rim:
            if R.in2(u, v) and not R.reserved(u, v):
                R.put(u, 0, v, deck)
    ok = []
    for (u, v) in pool:
        good = R.free(u, 0, v, walk=True) and R.floor_ok(u, v)
        for tok, (du, dv) in TV.items():
            a, b = u + du, v + dv
            if (a, b) in pool:
                continue
            if R.in2(a, b):
                good &= R.b.get_id(*R.P(a, 0, b)) > 1 and _cls(R.db, R.b.get(*R.P(a, 0, b))) in ("full", "slab")
            else:
                good &= R.wall_ok(u, 0, v, tok)
        if good:
            ok.append((u, v))
    for (u, v) in ok:
        R.put(u, 0, v, "water", walk=True)
    if ok:
        R.items.append("pool")
        for (u, v) in ok[::3]:
            R.put_floor(u, v, "sea_lantern")
        lu, lv = ok[0][0] + (len({c[0] for c in ok}) // 2), min(c[1] for c in ok)
        if (lu, lv) in ok:
            x, y, z = R.P(lu, 0, lv)
            R.remove_xyz(x, y, z)
            R.put(lu, 0, lv, "ladder[facing=@F,waterlogged=true]", walk=True)
    hl = 1 if top >= 2 else 0
    front = [(u, v) for v in range(0, max(1, (min(c[1] for c in ok) if ok else V))) for u in range(U)]
    n = 0
    for u in range(0, U - 1, 3):
        v = max(0, (min(c[1] for c in ok) - 2) if ok else 1)
        if (u, v) in front and not R.reserved(u, v) and not R.reserved(u, v + 1) and R.free(u, hl, v) \
                and R.in2(u, v + 1) and R.free(u, hl, v + 1) and (u, v + 1) not in ok:
            R.put(u, hl, v + 1, f"{R.w('stairs')}[facing=@F]")
            R.put(u, hl, v, "white_wool_slab[type=bottom]")
            n += 1
    if n:
        R.items.append("loungers")
    for (u, v) in ((0, 0), (U - 1, 0), (0, fv), (U - 1, fv)):
        if hl and R.free(u, 1, v) and not R.reserved(u, v):
            R.plant(u, 1, v, "potted_bamboo")
    for W in ("L", "R"):
        for (u, v) in R.wall_row(W)[1::4]:
            if top >= 2:
                R.banner(u, top, v, W, R.rng.choice(("white", "light_blue", "cyan")))
    R.ceiling_grid(3)


# ---------------------------------------------------------------------- 30 cati kati / loft
@_recipe("attic", "Cati kati / loft: yanlarda egik tavan (ters merdiven), acik kirisler ve kirislerden sarkan fenerler, egik tavan altinda yatak, minder koltuklar, eski sandik ve kutular, pencere onu calisma masasi, hali",
         "rustic", 5, ("cati kati", "cati arasi", "tavan arasi", "attic", "loft", "garret", "mansard", "asma kat"),
         ("spruce_planks", "spruce_planks", "spruce_planks"))
def _attic(R: Room):
    U, V, top, st = R.U, R.V, R.top, R.st
    fv = V - 1
    R.plan()
    stairs = R.w("stairs")
    if top >= 2 and U >= 4:
        for (W, u0, inward) in (("L", 0, 1), ("R", U - 1, -1)):
            for v in range(V):
                R.put(u0, top, v, f"{stairs}[facing=@{W},half=top]", walk=True)
                if top >= 3 and U >= 7:
                    R.put(u0, top - 1, v, f"{stairs}[facing=@{W},half=top]", walk=True)
                    R.put(u0 + inward, top, v, f"{stairs}[facing=@{W},half=top]", walk=True)
        R.items.append("sloped_ceiling")
    if top >= 2:
        for v in range(1, V - 1, 3):
            for u in range(U):
                R.put(u, top, v, R.w2("stripped_log") + "[axis=@AU]", walk=True)
        R.items.append("beams")
    side = _side_walls(R)[0]
    bu = 0 if side == "L" else U - 1
    R.bed(bu, fv - 1, "F") if V >= 3 else None
    R.put(bu, 0, max(0, fv - 2), "chest[facing=@" + OPPT[side] + "]")
    other = U - 1 - bu
    if U >= 3:
        boxes = [(other, fv), (other, fv - 1)] if V >= 3 else [(other, fv)]
        for (u, v) in boxes:
            R.put(u, 0, v, "barrel[facing=up]")
        R.put(other, 1, fv, "barrel[facing=up]") if top >= 2 else None
    mid = R.pick("F", 2, 0, 0, min_len=1, cells=[c for c in R.wall_row("F") if 1 <= c[0] <= U - 2])
    if mid and R.table(mid[:1], "slab"):
        u, v = mid[0]
        R.lamp_on(u, 1, v, "candle")
        R.chair(u, v - 1, "F")
    if U >= 5 and V >= 5:
        for (u, v) in ((R.cu - 1, R.cv), (R.cu + 1, R.cv)):
            R.put(u, 0, v, f"{st['fabric']}_wool_stairs[facing=@{'L' if u < R.cu else 'R'}]")
        R.items.append("bean_bags")
    R.rug(1, 1, U - 2, V - 2, fill=st["rug"], border=st["rug2"])
    for v in range(1, V - 1, 3):
        for u in (R.cu - 1, R.cu + 2) if U >= 6 else (R.cu,):
            if top >= 3:
                if R.free(u, top - 1, v, walk=True):
                    R.put(u, top - 1, v, R.lamp(True), walk=True)
    R.std_lights() if top < 3 else None


# ====================================================================== RECETE_SONU (yeni receteler bunun ustune)
# ====================================================================== genel API
def _resolve_kind(kind: str) -> str:
    if kind in _RECIPES:
        return kind
    k = _fold(kind).replace(" ", "_")
    if k in _RECIPES:
        return k
    d = detect_room_kind(kind)
    if d is None:
        raise ValueError(f"bilinmeyen oda turu: {kind!r} (olanlar: {', '.join(_RECIPES)})")
    return d


def furnish(build: Build, box, kind: str, style=None, door=None, seed: int = 0) -> dict:
    """Odayi `kind` recetesiyle doser; oda kaydini dondurur (build.meta rooms/lights da guncellenir)."""
    k = _resolve_kind(kind)
    spec = _RECIPES[k]
    R = Room(build, box, kind=k, style=style, door=door, seed=seed, default_style=spec["style"], comfort=spec["comfort"])
    spec["fn"](R)
    return R.finish()


def detect_room_kind(text: str) -> str | None:
    """Turkce/Ingilizce metinden oda turu ("ferah bir mutfak" -> "kitchen"); en uzun eslesen anahtar kelime kazanir."""
    if not text:
        return None
    t = " " + _fold(text) + " "
    best, blen = None, 0
    for k, spec in _RECIPES.items():
        for wd in tuple(spec["words"]) + (k.replace("_", " "),):
            fw = _fold(wd)
            if fw and re.search(r"(?<![a-z0-9])" + re.escape(fw), t) and len(fw) > blen:
                best, blen = k, len(fw)
    return best


def room_report(build: Build, box, door=None, comfort: int = 7) -> dict:
    """Denetim: kapi->merkez yollari, karanlik (spawn) hucreler, yurunen zemin isigi, destek ihlalleri."""
    R = Room(build, box, "rapor", door=door, comfort=comfort)
    paths = R.path_ok()
    L, org = light_map(build, box)
    tg = R._targets(L, org, set())
    dark = [[x, y, z] for (p, x, y, z) in tg if p == 100]
    t = _walk_grid(build, box)
    x0, y0, z0, x1, y1, z1 = R.box
    ox, oy, oz = org
    walk_light = []
    for iz in range(t.shape[0]):
        for ix in range(t.shape[1]):
            if t[iz, ix] >= 0:
                y = y0 if t[iz, ix] == 0 else y0 + 1
                walk_light.append(int(L[y - oy, iz + z0 - oz, ix + x0 - ox]))
    bad = []
    for y in range(y0 - 1, y1 + 2):
        for z in range(z0 - 1, z1 + 2):
            for x in range(x0 - 1, x1 + 2):
                i = build.get_id(x, y, z)
                if i > 1:
                    p = support_problem(build, R.box, x, y, z, build.palette[i])
                    if p:
                        bad.append({"pos": [x, y, z], "block": build.palette[i], "why": p})
    return {"doors": [list(c) for c in R.door_cells], "door_paths_ok": all(paths), "door_paths": paths,
            "dark_spots": dark, "walkable": len(walk_light), "min_light": min(walk_light) if walk_light else 0,
            "mean_light": round(sum(walk_light) / len(walk_light), 1) if walk_light else 0.0, "unsupported": bad}


def demo_room(kind: str = "living_room", size=(12, 4, 10), style=None, seed: int = 0, door_side: str = "north",
              windows: bool = True, furnish_it: bool = True):
    """Basit kabuk (zemin, duvar, tavan, mese kapi, yan duvarlarda cam) + doseme. Doner: (build, box, door)."""
    k = _resolve_kind(kind)
    W, H, D = size
    b = Build(f"demo_{k}")
    floor, wall, ceil = _RECIPES[k]["shell"]
    x0, y0, z0, x1, y1, z1 = 1, 1, 1, W, H, D
    b.fill(0, 0, 0, W + 1, 0, D + 1, floor)
    b.fill(0, H + 1, 0, W + 1, H + 1, D + 1, ceil)
    b.fill(0, 1, 0, W + 1, H, D + 1, wall)
    b.clear(x0, y0, z0, x1, y1, z1)
    dx, dz, fac = {"north": ((x0 + x1) // 2, 0, "south"), "south": ((x0 + x1) // 2, D + 1, "north"),
                   "west": (0, (z0 + z1) // 2, "east"), "east": (W + 1, (z0 + z1) // 2, "west")}[door_side]
    b.set(dx, 1, dz, f"oak_door[facing={fac},half=lower,hinge=left,open=false]")
    if H >= 2:
        b.set(dx, 2, dz, f"oak_door[facing={fac},half=upper,hinge=left,open=false]")
    b.meta["doors"].append({"pos": [dx, 1, dz], "facing": fac})
    if windows and H >= 3:
        for z in range(z0 + 1, z1, 3):
            for x in (0, W + 1):
                if (x, z) != (dx, dz):
                    b.set(x, 2, z, "glass_pane")
                    b.meta["windows"].append({"pos": [x, 2, z]})
    box = (x0, y0, z0, x1, y1, z1)
    if furnish_it:
        furnish(b, box, k, style=style, seed=seed)
    return b, box, [(dx, 1, dz)]


def _crop(build: Build, box, pad: int = 1) -> Build:
    x0, y0, z0, x1, y1, z1 = box
    c = Build("kesit", build.db)
    ids = build.ids_box(x0 - pad, y0 - pad, z0 - pad, x1 + pad, y1 + pad, z1 + pad)
    c.put_ids(x0 - pad, y0 - pad, z0 - pad, ids, build.palette)
    return c


def save_room_preview(build: Build, box, path, door=None, title: str | None = None) -> str:
    """Oda onizlemesi: iki kesit izometrik (tavan ve yakin duvarlar kaldirilmis), kapidan perspektif,
    zemin plani (y0), isik haritasi (kirmizi = karanlik, yesil = aydinlik) ve tavan plani."""
    from pathlib import Path

    from PIL import Image, ImageDraw

    from ..render.sheet import grid, label, volume_from_build
    from ..render.views import iso, perspective, section
    x0, y0, z0, x1, y1, z1 = box
    big = y1 + 1

    def cut(sides):
        c = _crop(build, box)
        c.forget(x0 - 1, y1 + 1, z0 - 1, x1 + 1, big, z1 + 1)
        for s_ in sides:
            if s_ == "south":
                c.forget(x0 - 1, y0, z1 + 1, x1 + 1, big, z1 + 1)
            elif s_ == "east":
                c.forget(x1 + 1, y0, z0 - 1, x1 + 1, big, z1 + 1)
            elif s_ == "north":
                c.forget(x0 - 1, y0, z0 - 1, x1 + 1, big, z0 - 1)
            elif s_ == "west":
                c.forget(x0 - 1, y0, z0 - 1, x0 - 1, big, z1 + 1)
        return c
    views = []
    vse, _ = volume_from_build(cut(("south", "east")))
    views.append(("Kesit izometrik (GD)", iso(vse, "se", max_px=700)))
    vnw, _ = volume_from_build(cut(("north", "west")))
    views.append(("Kesit izometrik (KB)", iso(vnw, "nw", max_px=700)))
    vol, org = volume_from_build(_crop(build, box))
    ox, oy, oz = org
    R = Room(build, box, "onizleme", door=door)
    ex, ez, _ = R.entries_xz[0]
    fx, fz = DIRS[R.focal]
    eye = (ex - ox + 0.5 - fx * 0.3, y0 - oy + 1.62, ez - oz + 0.5 - fz * 0.3)
    tgt = ((x0 + x1) / 2 - ox + 0.5 + fx * 3, y0 - oy + 0.9, (z0 + z1) / 2 - oz + 0.5 + fz * 3)
    try:
        views.append(("Kapidan perspektif", perspective(vol, eye, tgt, size=(560, 380), fov=80)))
    except Exception:
        pass
    views.append((f"Plan (y={y0})", section(vol, y0 - oy, max_px=520)))
    L, lorg = light_map(build, box)
    lx, ly, lz = lorg
    t = _walk_grid(build, box)
    W, D = x1 - x0 + 1, z1 - z0 + 1
    s = max(8, min(40, 520 // max(W, D)))
    im = Image.new("RGB", (W * s, D * s), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    for iz in range(D):
        for ix in range(W):
            x, z = x0 + ix, z0 + iz
            tv = int(t[iz, ix])
            lv = None
            if tv < 0:
                col = (150, 150, 150)
            else:
                lv = int(L[(y0 if tv == 0 else y0 + 1) - ly, z - lz, x - lx])
                if lv == 0:
                    col = (220, 40, 40)
                elif lv < 4:
                    col = (240, 140, 40)
                elif lv < 7:
                    col = (240, 210, 60)
                else:
                    g = min(1.0, (lv - 7) / 8)
                    col = (int(170 - 120 * g), int(220 - 40 * g), int(120 - 60 * g))
            dr.rectangle([ix * s, iz * s, ix * s + s - 1, iz * s + s - 1], fill=col, outline=(255, 255, 255))
            if lv is not None and s >= 14:
                dr.text((ix * s + 3, iz * s + 2), str(lv), fill=(0, 0, 0))
    for l in build.meta.get("lights", []):
        px, py, pz = l["pos"]
        if x0 - 1 <= px <= x1 + 1 and z0 - 1 <= pz <= z1 + 1 and y0 - 1 <= py <= y1 + 1:
            cx, cz = (min(max(px, x0), x1) - x0) * s + s // 2, (min(max(pz, z0), z1) - z0) * s + s // 2
            dr.ellipse([cx - s // 5, cz - s // 5, cx + s // 5, cz + s // 5], outline=(255, 255, 255), width=2)
    for (ex2, ez2, _) in R.entries_xz:
        dr.rectangle([(ex2 - x0) * s, (ez2 - z0) * s, (ex2 - x0) * s + s - 1, (ez2 - z0) * s + s - 1],
                     outline=(40, 80, 220), width=3)
    views.append(("Isik haritasi (ayak hizasi)", im))
    views.append((f"Tavan plani (y={y1})", section(vol, y1 - oy, max_px=520)))
    sheet_im = grid(views, cols=3, cell=(400, 300))
    if title:
        sheet_im = label(sheet_im, title)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sheet_im.save(path)
    return str(path)


# ====================================================================== oda turleri ve dogrudan cagrilar
ROOM_KINDS: dict[str, str] = {k: v["tr"] for k, v in _RECIPES.items()}


def furnish_living_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """living_room: bkz. ROOM_KINDS['living_room']."""
    return furnish(build, box, 'living_room', style=style, door=door, seed=seed)


def furnish_kitchen(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """kitchen: bkz. ROOM_KINDS['kitchen']."""
    return furnish(build, box, 'kitchen', style=style, door=door, seed=seed)


def furnish_dining_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """dining_room: bkz. ROOM_KINDS['dining_room']."""
    return furnish(build, box, 'dining_room', style=style, door=door, seed=seed)


def furnish_master_bedroom(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """master_bedroom: bkz. ROOM_KINDS['master_bedroom']."""
    return furnish(build, box, 'master_bedroom', style=style, door=door, seed=seed)


def furnish_kids_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """kids_room: bkz. ROOM_KINDS['kids_room']."""
    return furnish(build, box, 'kids_room', style=style, door=door, seed=seed)


def furnish_bathroom(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """bathroom: bkz. ROOM_KINDS['bathroom']."""
    return furnish(build, box, 'bathroom', style=style, door=door, seed=seed)


def furnish_library(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """library: bkz. ROOM_KINDS['library']."""
    return furnish(build, box, 'library', style=style, door=door, seed=seed)


def furnish_home_office(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """home_office: bkz. ROOM_KINDS['home_office']."""
    return furnish(build, box, 'home_office', style=style, door=door, seed=seed)


def furnish_guest_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """guest_room: bkz. ROOM_KINDS['guest_room']."""
    return furnish(build, box, 'guest_room', style=style, door=door, seed=seed)


def furnish_foyer(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """foyer: bkz. ROOM_KINDS['foyer']."""
    return furnish(build, box, 'foyer', style=style, door=door, seed=seed)


def furnish_laundry(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """laundry: bkz. ROOM_KINDS['laundry']."""
    return furnish(build, box, 'laundry', style=style, door=door, seed=seed)


def furnish_pantry(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """pantry: bkz. ROOM_KINDS['pantry']."""
    return furnish(build, box, 'pantry', style=style, door=door, seed=seed)


def furnish_wine_cellar(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """wine_cellar: bkz. ROOM_KINDS['wine_cellar']."""
    return furnish(build, box, 'wine_cellar', style=style, door=door, seed=seed)


def furnish_workshop(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """workshop: bkz. ROOM_KINDS['workshop']."""
    return furnish(build, box, 'workshop', style=style, door=door, seed=seed)


def furnish_tavern(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """tavern: bkz. ROOM_KINDS['tavern']."""
    return furnish(build, box, 'tavern', style=style, door=door, seed=seed)


def furnish_throne_hall(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """throne_hall: bkz. ROOM_KINDS['throne_hall']."""
    return furnish(build, box, 'throne_hall', style=style, door=door, seed=seed)


def furnish_great_hall(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """great_hall: bkz. ROOM_KINDS['great_hall']."""
    return furnish(build, box, 'great_hall', style=style, door=door, seed=seed)


def furnish_armory(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """armory: bkz. ROOM_KINDS['armory']."""
    return furnish(build, box, 'armory', style=style, door=door, seed=seed)


def furnish_bas_oda(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """bas_oda: bkz. ROOM_KINDS['bas_oda']."""
    return furnish(build, box, 'bas_oda', style=style, door=door, seed=seed)


def furnish_prayer_hall(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """prayer_hall: bkz. ROOM_KINDS['prayer_hall']."""
    return furnish(build, box, 'prayer_hall', style=style, door=door, seed=seed)


def furnish_tea_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """tea_room: bkz. ROOM_KINDS['tea_room']."""
    return furnish(build, box, 'tea_room', style=style, door=door, seed=seed)


def furnish_barn(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """barn: bkz. ROOM_KINDS['barn']."""
    return furnish(build, box, 'barn', style=style, door=door, seed=seed)


def furnish_greenhouse(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """greenhouse: bkz. ROOM_KINDS['greenhouse']."""
    return furnish(build, box, 'greenhouse', style=style, door=door, seed=seed)


def furnish_control_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """control_room: bkz. ROOM_KINDS['control_room']."""
    return furnish(build, box, 'control_room', style=style, door=door, seed=seed)


def furnish_lab(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """lab: bkz. ROOM_KINDS['lab']."""
    return furnish(build, box, 'lab', style=style, door=door, seed=seed)


def furnish_shop(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """shop: bkz. ROOM_KINDS['shop']."""
    return furnish(build, box, 'shop', style=style, door=door, seed=seed)


def furnish_cafe(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """cafe: bkz. ROOM_KINDS['cafe']."""
    return furnish(build, box, 'cafe', style=style, door=door, seed=seed)


def furnish_gym(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """gym: bkz. ROOM_KINDS['gym']."""
    return furnish(build, box, 'gym', style=style, door=door, seed=seed)


def furnish_pool_room(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """pool_room: bkz. ROOM_KINDS['pool_room']."""
    return furnish(build, box, 'pool_room', style=style, door=door, seed=seed)


def furnish_attic(build: Build, box, style=None, door=None, seed: int = 0) -> dict:
    """attic: bkz. ROOM_KINDS['attic']."""
    return furnish(build, box, 'attic', style=style, door=door, seed=seed)


__all__ = ["furnish", "detect_room_kind", "ROOM_KINDS", "STYLES", "room_report", "light_map", "demo_room",
           "save_room_preview", "Room", "support_problem", "center_cells"] + [f"furnish_{k}" for k in ROOM_KINDS]
