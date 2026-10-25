"""Saha analizi (T5): yukseklik/egim, duzluk, su/agac/yapay maskeleri, oyuncuya gore yon sozlugu ve
"onumde" en iyi taban alani aramasi. Dunya verisi oyundan (USTACOL1 sutunlari) gelir."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from . import blockdb
from .worlddata import UNKNOWN, Columns

CARDINALS = ("south", "west", "north", "east")  # Minecraft yaw 0, 90, 180, 270
VEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
TR = {"north": "kuzey", "south": "güney", "east": "doğu", "west": "batı"}


def yaw_to_cardinal(yaw: float) -> str:
    return CARDINALS[int(((yaw % 360) + 45) // 90) % 4]


def forward_vec(yaw: float) -> tuple[float, float]:
    r = math.radians(yaw)
    return (-math.sin(r), math.cos(r))


def right_vec(yaw: float) -> tuple[float, float]:
    r = math.radians(yaw)
    return (-math.cos(r), -math.sin(r))


def directions(yaw: float) -> dict:
    """Oyuncuya gore yon sozlugu: onum/arkam/sagim/solum -> dunya yonu."""
    f = yaw_to_cardinal(yaw)
    order = ["north", "east", "south", "west"]
    i = order.index(f)
    return {"önüm": f, "sağım": order[(i + 1) % 4], "arkam": order[(i + 2) % 4], "solum": order[(i + 3) % 4],
            "front": f, "right": order[(i + 1) % 4], "back": order[(i + 2) % 4], "left": order[(i + 3) % 4]}


# ------------------------------------------------------------------ maskeler
def _names(cols: Columns, which: str) -> np.ndarray:
    pal = np.array([p.split("[", 1)[0] for p in cols.palette], dtype=object)
    st = {"surface": cols.surface_state, "ground": cols.ground_state, "floor": cols.floor_state}[which]
    return pal[st]


def masks(cols: Columns) -> dict[str, np.ndarray]:
    db = blockdb.get()
    known = cols.surface != UNKNOWN
    pal = cols.palette
    nat = np.zeros(len(pal), dtype=bool)
    water = np.zeros(len(pal), dtype=bool)
    tree = np.zeros(len(pal), dtype=bool)
    lava = np.zeros(len(pal), dtype=bool)
    for i, s in enumerate(pal):
        if s == "?":
            nat[i] = True
            continue
        n = s.split("[", 1)[0]
        try:
            nat[i] = bool(db.natural[db.id(s)])
        except Exception:
            nat[i] = True
        water[i] = n in ("minecraft:water", "minecraft:bubble_column", "minecraft:kelp", "minecraft:kelp_plant", "minecraft:seagrass",
                         "minecraft:tall_seagrass") or "waterlogged=true" in s
        lava[i] = n == "minecraft:lava"
        tree[i] = n.endswith("_leaves") or n.endswith("_log") or n.endswith("_wood")
    m = {
        "known": known,
        "water": water[cols.ground_state] & known,
        "lava": lava[cols.ground_state] & known,
        "tree": tree[cols.surface_state] & known,
        "artificial": (~nat[cols.surface_state] | ~nat[cols.ground_state]) & known,
    }
    m["water_depth"] = np.where(m["water"], cols.ground - cols.floor, 0)
    return m


def ground_height(cols: Columns) -> np.ndarray:
    """Agac yapraklari haric zemin (su varsa su tabani)."""
    g = np.where(cols.ground_state >= 0, cols.ground, cols.surface)
    return g


def slope(h: np.ndarray) -> np.ndarray:
    hp = np.pad(h.astype(np.float32), 1, mode="edge")
    gx = (hp[1:-1, 2:] - hp[1:-1, :-2]) / 2
    gz = (hp[2:, 1:-1] - hp[:-2, 1:-1]) / 2
    return np.sqrt(gx * gx + gz * gz)


# ------------------------------------------------------------------ taban alani arama
@dataclass
class Site:
    x0: int
    z0: int
    x1: int
    z1: int
    facing: str              # yapinin on cephesinin baktigi dunya yonu
    ground_y: int            # onerilen zemin (pad) yuksekligi: ust blok y
    score: float
    flatness: float          # 0..1
    cut: int                 # kesilecek blok (yaklasik)
    fill: int                # doldurulacak blok
    water_frac: float
    tree_frac: float
    artificial: int
    distance: float
    width: int               # yerel genislik (x)
    depth: int               # yerel derinlik (z)
    notes: list[str] = field(default_factory=list)

    def origin(self) -> tuple[int, int, int]:
        """Yerel (0,0,0) icin dunya noktasi (Build.to_plan world_origin), y = ground_y."""
        o = {"north": (self.x0, self.z0), "east": (self.x1, self.z0), "south": (self.x1, self.z1), "west": (self.x0, self.z1)}[self.facing]
        return (o[0], self.ground_y, o[1])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["origin"] = list(self.origin())
        d["facing_tr"] = TR[self.facing]
        return d


def evaluate(cols: Columns, mk: dict, x0: int, z0: int, x1: int, z1: int) -> dict | None:
    i0, i1 = z0 - cols.z0, z1 - cols.z0
    j0, j1 = x0 - cols.x0, x1 - cols.x0
    if i0 < 0 or j0 < 0 or i1 >= cols.h or j1 >= cols.w:
        return None
    sl = (slice(i0, i1 + 1), slice(j0, j1 + 1))
    if not mk["known"][sl].all():
        return None
    g = cols.ground[sl].astype(np.float64)
    fl = cols.floor[sl].astype(np.float64)
    h = np.where(mk["water"][sl], fl, g)
    pad = int(round(float(np.median(h))))
    cut = int(np.clip(h - pad, 0, None).sum())
    fill = int(np.clip(pad - h, 0, None).sum())
    std = float(h.std())
    return {
        "pad": pad, "cut": cut, "fill": fill, "std": std, "range": float(h.max() - h.min()),
        "water": float(mk["water"][sl].mean()), "lava": float(mk["lava"][sl].mean()),
        "tree": float(mk["tree"][sl].mean()), "artificial": int(mk["artificial"][sl].sum()),
    }


def find_site(cols: Columns, anchor: dict, width: int, depth: int, where: str = "front", min_dist: int = 4,
              max_dist: int = 40, protected: list[dict] | None = None, avoid_boxes: list[list[int]] | None = None,
              allow_water: bool = False, force: bool = False) -> list[Site]:
    """force: aday cikmazsa (dev taban, yuklenmemis/agacli/sulu alan) oyuncunun onune ortalanmis zorunlu alan dondur
    (motor zemini duzler, chunk biletleriyle yukler). Oyuncunun (anchor: x,y,z,yaw) gore `where` yonunde width x depth tabanli en iyi yerleri dondurur.
    Yapinin on cephesi oyuncuya bakar. Donus: puana gore sirali en cok 5 aday."""
    yaw = float(anchor.get("yaw", 0))
    px, pz = float(anchor["x"]), float(anchor["z"])
    dirs = directions(yaw)
    wdir = dirs.get(where, where) if where in dirs else where
    if wdir not in VEC:
        wdir = dirs["front"]
    facing = OPPOSITE[wdir]
    vx, vz = VEC[wdir]
    # dunya ayak izi boyutlari
    if facing in ("north", "south"):
        wx, wz = width, depth
    else:
        wx, wz = depth, width
    mk = masks(cols)
    cands = []
    lateral = (-vz, vx)  # yana kaydirma ekseni
    for dist in range(min_dist, max_dist + 1, 2):
        for lat in range(-12, 13, 3):
            # on kenarin ortasi: oyuncudan dist uzakta
            cxf = px + vx * dist + lateral[0] * lat
            czf = pz + vz * dist + lateral[1] * lat
            if wdir == "north":
                x0, z1 = int(round(cxf - wx / 2)), int(math.floor(czf))
                x1, z0 = x0 + wx - 1, z1 - wz + 1
            elif wdir == "south":
                x0, z0 = int(round(cxf - wx / 2)), int(math.floor(czf))
                x1, z1 = x0 + wx - 1, z0 + wz - 1
            elif wdir == "east":
                z0, x0 = int(round(czf - wz / 2)), int(math.floor(cxf))
                z1, x1 = z0 + wz - 1, x0 + wx - 1
            else:
                z0, x1 = int(round(czf - wz / 2)), int(math.floor(cxf))
                z1, x0 = z0 + wz - 1, x1 - wx + 1
            # oyuncu ayak izinde olmasin
            if x0 - 1 <= px <= x1 + 1 and z0 - 1 <= pz <= z1 + 1:
                continue
            ev = evaluate(cols, mk, x0, z0, x1, z1)
            if ev is None:
                continue
            if ev["artificial"] > 0 or ev["lava"] > 0:
                continue
            if not allow_water and ev["water"] > 0.15:
                continue
            bad = False
            for b in (avoid_boxes or []):
                if x0 <= b[0] + b[3] - 1 and b[0] <= x1 and z0 <= b[2] + b[5] - 1 and b[2] <= z1:
                    bad = True
                    break
            for r in (protected or []):
                if x0 <= r["x1"] and r["x0"] <= x1 and z0 <= r["z1"] and r["z0"] <= z1:
                    bad = True
                    break
            if bad:
                continue
            area = wx * wz
            earth = (ev["cut"] + ev["fill"]) / area
            flat = 1.0 / (1.0 + ev["std"])
            ideal = min(22.0, max(6.0, 0.5 * max(width, depth) + 4.0))
            score = 100 * flat - 6 * earth - 1.2 * abs(dist - ideal) - 0.4 * abs(lat) - 40 * ev["water"] - 8 * ev["tree"]
            notes = []
            if ev["range"] > 4:
                notes.append(f"eğimli arazi (yükseklik farkı {int(ev['range'])}); zemin düzeltmesi gerekir")
            if ev["tree"] > 0.2:
                notes.append("ağaçlık alan; bazı ağaçlar kaldırılacak")
            if ev["water"] > 0:
                notes.append("kısmen su üstünde")
            cands.append(Site(x0, z0, x1, z1, facing, ev["pad"], round(score, 2), round(flat, 3), ev["cut"], ev["fill"],
                              round(ev["water"], 3), round(ev["tree"], 3), ev["artificial"], float(dist), width, depth, notes))
    if not cands and force:
        for dist in range(min_dist + 2, max_dist + 42, 8):   # onceki yapiya/korunan bolgeye binmeyen ilk uzaklik
            cxf, czf = px + vx * dist, pz + vz * dist
            if wdir == "north":
                x0, z1 = int(round(cxf - wx / 2)), int(math.floor(czf)); x1, z0 = x0 + wx - 1, z1 - wz + 1
            elif wdir == "south":
                x0, z0 = int(round(cxf - wx / 2)), int(math.floor(czf)); x1, z1 = x0 + wx - 1, z0 + wz - 1
            elif wdir == "east":
                z0, x0 = int(round(czf - wz / 2)), int(math.floor(cxf)); z1, x1 = z0 + wz - 1, x0 + wx - 1
            else:
                z0, x1 = int(round(czf - wz / 2)), int(math.floor(cxf)); z1, x0 = z0 + wz - 1, x1 - wx + 1
            clash = any(x0 <= b[0] + b[3] - 1 and b[0] <= x1 and z0 <= b[2] + b[5] - 1 and b[2] <= z1 for b in (avoid_boxes or []))
            clash = clash or any(x0 <= r["x1"] and r["x0"] <= x1 and z0 <= r["z1"] and r["z0"] <= z1 for r in (protected or []))
            if not clash:
                # taban: kutudaki bilinen yuzeyin medyani (oyuncu ucuyorsa ayak yuksekligi zemin sayilmaz)
                pad = int(math.floor(float(anchor.get("y", 64)))) - 1
                i0, i1 = max(0, z0 - cols.z0), min(cols.h - 1, z1 - cols.z0)
                j0, j1 = max(0, x0 - cols.x0), min(cols.w - 1, x1 - cols.x0)
                if i0 <= i1 and j0 <= j1:
                    sl = (slice(i0, i1 + 1), slice(j0, j1 + 1))
                    kn = mk["known"][sl]
                    if kn.any():
                        pad = int(round(float(np.median(cols.ground[sl][kn]))))
                cands.append(Site(x0, z0, x1, z1, facing, pad, 0.0, 0.0, 0, 0, 0.0, 0.0, 0, float(dist), width, depth,
                                  ["zorunlu alan: uygun düz/boş aday yok; arazi düzlenir, ağaç/su gerekiyorsa kaldırılır"]))
                break
    cands.sort(key=lambda s: -s.score)
    out: list[Site] = []
    for c in cands:
        if all(abs(c.x0 - o.x0) + abs(c.z0 - o.z0) > 6 for o in out):
            out.append(c)
        if len(out) >= 5:
            break
    return out


def summarize(cols: Columns, anchor: dict | None = None, radius: int | None = None) -> dict:
    """Bolge ozeti: yukseklik araligi, duzluk, su/agac/yapi oranlari, biyomlar."""
    mk = masks(cols)
    known = mk["known"]
    g = cols.ground[known]
    out = {
        "area": [cols.x0, cols.z0, cols.x0 + cols.w - 1, cols.z0 + cols.h - 1],
        "known_frac": round(float(known.mean()), 3),
        "ground_min": int(g.min()) if g.size else None,
        "ground_max": int(g.max()) if g.size else None,
        "ground_median": int(np.median(g)) if g.size else None,
        "mean_slope": round(float(slope(cols.ground)[known].mean()), 2) if g.size else None,
        "water_frac": round(float(mk["water"].mean()), 3),
        "tree_frac": round(float(mk["tree"].mean()), 3),
        "artificial_cells": int(mk["artificial"].sum()),
    }
    if cols.biomes:
        ids, cnt = np.unique(cols.biome[known], return_counts=True)
        out["biomes"] = {cols.biomes[int(i)]: round(int(c) / max(1, int(known.sum())), 3) for i, c in zip(ids, cnt)}
    if anchor is not None:
        out["directions"] = directions(float(anchor.get("yaw", 0)))
    return out


def structures(cols: Columns, min_cells: int = 6) -> list[dict]:
    """Dogal olmayan blok kumelerini (mevcut yapilar) bulur: sutun maskesinde bagli bilesenler."""
    mk = masks(cols)
    a = mk["artificial"].copy()
    h, w = a.shape
    seen = np.zeros_like(a)
    out = []
    for i in range(h):
        for j in range(w):
            if a[i, j] and not seen[i, j]:
                stack = [(i, j)]
                seen[i, j] = True
                cells = []
                while stack:
                    y, x = stack.pop()
                    cells.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and a[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                if len(cells) >= min_cells:
                    ys = [c[0] for c in cells]
                    xs = [c[1] for c in cells]
                    top = max(int(cols.surface[c]) for c in cells)
                    out.append({"x0": cols.x0 + min(xs), "z0": cols.z0 + min(ys), "x1": cols.x0 + max(xs), "z1": cols.z0 + max(ys),
                                "cells": len(cells), "top_y": top})
    out.sort(key=lambda s: -s["cells"])
    return out[:30]
