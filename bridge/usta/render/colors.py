"""Blok renkleri: (1) oyunun dokularindan calisma aninda cikarilan renk tablosu (istemci, varsa),
(2) blok veritabanindaki harita rengi + ad tabanli duzeltmeler. Dokular dagitilmaz (M7)."""
from __future__ import annotations

import gzip
import json
from functools import lru_cache

import numpy as np

from .. import blockdb, config

# (top_rgb, side_rgb, alpha) duzeltmeleri: harita rengi yetersiz kalan yaygin bloklar
OVERRIDES: dict[str, tuple] = {
    "grass_block": ((96, 156, 62), (134, 96, 67), 1.0),
    "dirt_path": ((148, 122, 65), (134, 96, 67), 1.0),
    "podzol": ((91, 63, 24), (134, 96, 67), 1.0),
    "mycelium": ((111, 99, 105), (134, 96, 67), 1.0),
    "water": ((50, 90, 200), (45, 80, 185), 0.75),
    "lava": ((230, 110, 20), (220, 95, 15), 1.0),
    "glass": ((205, 225, 235), (190, 215, 230), 0.35),
    "glass_pane": ((205, 225, 235), (190, 215, 230), 0.35),
    "tinted_glass": ((50, 40, 55), (45, 38, 50), 0.6),
    "ice": ((145, 183, 253), (135, 175, 250), 0.7),
    "snow": ((248, 252, 252), (240, 246, 246), 1.0),
    "snow_block": ((248, 252, 252), (240, 246, 246), 1.0),
    "sand": ((219, 207, 163), (214, 202, 158), 1.0),
    "stone": ((125, 125, 125), (118, 118, 118), 1.0),
    "smooth_stone": ((160, 160, 160), (152, 152, 152), 1.0),
    "stone_bricks": ((122, 121, 122), (115, 114, 115), 1.0),
    "cobblestone": ((127, 127, 127), (118, 118, 118), 1.0),
    "deepslate_bricks": ((70, 70, 72), (64, 64, 66), 1.0),
    "polished_deepslate": ((72, 72, 74), (66, 66, 68), 1.0),
    "white_concrete": ((207, 213, 214), (200, 206, 207), 1.0),
    "light_gray_concrete": ((125, 125, 115), (118, 118, 108), 1.0),
    "gray_concrete": ((54, 57, 61), (50, 53, 57), 1.0),
    "black_concrete": ((8, 10, 15), (8, 10, 15), 1.0),
    "quartz_block": ((235, 229, 222), (230, 224, 217), 1.0),
    "smooth_quartz": ((236, 230, 223), (230, 224, 217), 1.0),
    "calcite": ((223, 224, 220), (216, 217, 213), 1.0),
    "torch": ((255, 200, 90), (255, 190, 80), 1.0),
    "wall_torch": ((255, 200, 90), (255, 190, 80), 1.0),
    "lantern": ((255, 190, 90), (210, 160, 80), 1.0),
    "glowstone": ((250, 210, 130), (240, 200, 120), 1.0),
    "sea_lantern": ((210, 230, 225), (200, 222, 218), 1.0),
    "oak_leaves": ((70, 120, 40), (62, 108, 36), 0.95),
    "birch_leaves": ((95, 140, 55), (85, 128, 50), 0.95),
    "spruce_leaves": ((50, 90, 55), (45, 82, 50), 0.95),
    "jungle_leaves": ((60, 135, 30), (54, 122, 28), 0.95),
    "acacia_leaves": ((80, 125, 35), (72, 112, 32), 0.95),
    "dark_oak_leaves": ((55, 100, 30), (50, 90, 27), 0.95),
    "cherry_leaves": ((235, 170, 200), (225, 160, 192), 0.95),
    "azalea_leaves": ((95, 125, 45), (86, 114, 40), 0.95),
    "mangrove_leaves": ((70, 125, 40), (63, 112, 36), 0.95),
    "pale_oak_leaves": ((150, 155, 140), (140, 145, 130), 0.95),
    "short_grass": ((96, 156, 62), (96, 156, 62), 0.6),
    "tall_grass": ((96, 156, 62), (96, 156, 62), 0.6),
}

LOG_TOP = {"oak": (175, 140, 85), "spruce": (110, 80, 45), "birch": (195, 180, 125), "jungle": (165, 120, 80),
           "acacia": (170, 92, 50), "dark_oak": (75, 55, 30), "mangrove": (120, 55, 45), "cherry": (220, 175, 165),
           "pale_oak": (220, 210, 205)}


@lru_cache(maxsize=1)
def texture_table() -> dict:
    p = config.cache_dir() / f"colors-{config.MC}.json.gz"
    try:
        if p.exists():
            with gzip.open(p, "rb") as f:
                return json.loads(f.read().decode("utf-8"))
    except Exception:
        pass
    return {}


def _map_rgb(db: blockdb.BlockDB, state: str) -> tuple[int, int, int]:
    c = int(db.map_color[db.id(state)])
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


@lru_cache(maxsize=65536)
def colors_for(state: str) -> tuple[tuple[int, int, int], tuple[int, int, int], float]:
    """(ust renk, yan renk, opaklik)"""
    s = state.lstrip("!")
    db = blockdb.get()
    name = s.split("[", 1)[0].split(":", 1)[-1]
    tt = texture_table()
    if tt:
        e = tt.get("states", {}).get(s) or tt.get("blocks", {}).get("minecraft:" + name)
        if e:
            return tuple(e["top"]), tuple(e["side"]), float(e.get("alpha", 1.0))
    if name in OVERRIDES:
        return OVERRIDES[name]
    base = name
    for suf in ("_stairs", "_slab", "_wall", "_fence_gate", "_fence", "_pressure_plate", "_button", "_trapdoor", "_door", "_sign",
                "_wall_sign", "_hanging_sign", "_wall_hanging_sign", "_carpet", "_pane"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    for alias in (base, base + "s", base + "_block", base + "_planks", base.replace("_brick", "_bricks")):
        if alias in OVERRIDES:
            t, sd, a = OVERRIDES[alias]
            if name.endswith("_pane"):
                return t, sd, 0.35
            return t, sd, a
    for wood, top in LOG_TOP.items():
        if name in (f"{wood}_log", f"{wood}_wood", f"stripped_{wood}_log", f"{wood}_stem"):
            side = _map_rgb(db, s)
            if "axis=y" in s or "axis" not in s:
                return top, side, 1.0
            return side, side, 1.0
    rgb = _map_rgb(db, s)
    if rgb == (0, 0, 0):
        f = db.flags_of(s)
        if f & blockdb.AIR:
            return (0, 0, 0), (0, 0, 0), 0.0
        if "glass" in name:
            return (205, 225, 235), (190, 215, 230), 0.35
        rgb = (150, 150, 150)
    alpha = 1.0
    if "glass" in name:
        alpha = 0.4
    elif name.endswith("leaves"):
        alpha = 0.95
    side = tuple(int(v * 0.93) for v in rgb)
    return rgb, side, alpha


def palette_arrays(palette: list[str]) -> dict[str, np.ndarray]:
    """Palet icin renk/ozellik dizileri: top[n,3], side[n,3], alpha[n], solid[n], opaque[n], light[n], kind[n]."""
    db = blockdb.get()
    n = len(palette)
    top = np.zeros((n, 3), dtype=np.float32)
    side = np.zeros((n, 3), dtype=np.float32)
    alpha = np.zeros(n, dtype=np.float32)
    solid = np.zeros(n, dtype=bool)
    opaque = np.zeros(n, dtype=bool)
    light = np.zeros(n, dtype=np.float32)
    height = np.ones(n, dtype=np.float32)  # gorsel yukseklik (yarim levha 0.5)
    for i, s in enumerate(palette):
        if i == 0 or s in ("keep", "?", "minecraft:air", "minecraft:cave_air", "minecraft:void_air"):
            continue
        try:
            st = s.lstrip("!")
            f = db.flags_of(st)
            if f & blockdb.AIR:
                continue
            t, sd, a = colors_for(st)
            top[i] = t
            side[i] = sd
            alpha[i] = a
            solid[i] = True
            opaque[i] = bool(f & blockdb.FULL) and a >= 0.99 and "leaves" not in st
            light[i] = float(db.light[db.id(st)]) / 15.0
            if "_slab" in st and "type=bottom" in st:
                height[i] = 0.5
            elif ("_carpet" in st or "pressure_plate" in st or "snow[layers=1" in st or st.endswith(":snow")):
                height[i] = 0.12
        except Exception:
            top[i] = side[i] = (200, 0, 200)
            alpha[i] = 1.0
            solid[i] = True
    return {"top": top, "side": side, "alpha": alpha, "solid": solid, "opaque": opaque, "light": light, "height": height}
