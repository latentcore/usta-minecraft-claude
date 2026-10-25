"""Usta Arena stadyum uretici: ortak cekirdek (yogun dizi, palet, yazi, tabela, flama, arma, uzaklik alani).

Yerel cerceve: orijin saha merkezi, y=0 zemin katmani (dunya y=-61: cimenin yerine doseme). +x dogu, +z guney, +y yukari.
Dizi G[y - Y0, z - Z0, x - X0] (uint16 palet indeksi; 0 = dokunma, 1 = hava).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[3])
if "usta" not in sys.modules:
    sys.path.insert(0, os.path.join(ROOT, "bridge"))
os.environ.setdefault("USTA_GAME_DIR", os.path.join(os.path.expanduser("~"), "UstaOyun"))

import numpy as np  # noqa: E402

from usta import blockdb  # noqa: E402

DB = blockdb.get()

# ------------------------------------------------------------------ olculer (olcek 3: 1 m = 3 blok; saha 105x68 m -> 315x205)
# Cevredeki koylere dokunmadan sigan en buyuk taban; buyukluk yukseklikle: ust tribun 45 derece, cati ~140 blok.
S = 3
PL, PW = 157, 102          # saha yari boyu (x) ve yari eni (z)
A, B = PL + 18, PW + 15    # ic sinir (saha + reklam/servis alani) yari olculeri: 175, 117
LOW_ROWS = 28              # alt tribun: 2 derin, 1 yukselen sira
CROSS_D0 = 2 + 2 * LOW_ROWS            # 58: capraz koridor (y = BOXY)
BOXY = 4 + LOW_ROWS                    # 32: loca kati dosemesi
BOX_D0, BOX_D1 = CROSS_D0 + 4, CROSS_D0 + 16      # 62..73 loca ici, 74.. VIP koridoru
UP_D0 = CROSS_D0                       # ust tribun ilk sirasi (capraz koridorun ustunde)
UPY0 = BOXY + 12                       # 44: ust tribun ilk yuruyus seviyesi
UP_DEEP = 2                            # ust tribun: 2 derin, 2 yukselen sira (45 derece)
UP_ROWS = 39
BACK_D = UP_D0 + UP_DEEP * UP_ROWS     # 136
FACADE = BACK_D + 2                    # 138: dis cephe ic yuzu (d)
LAST_SEAT_Y = UPY0 + 2 * (UP_ROWS - 1) + 1   # 121
ROOF0 = LAST_SEAT_Y + 15               # 136: cati on kenar yuksekligi
LOW_CONC = (44, 56, 16)                # alt konkur (d0, d1, doseme y)
UP_CONC = (88, 100, 64)                # ust konkur
VIP_CONC = (BOX_D1, BOX_D1 + 6, BOXY)  # loca koridoru (74..79)
GATE_CONC = (FACADE - 16, FACADE - 8, 0)    # zemin kapi galerisi (122..129)
CORE_D = (103, 114)                    # merdiven kuleleri: ic duvar, dis duvar (d)
PLAZA = 36                 # cephe disi meydan genisligi
X0, X1 = -(A + FACADE + 3 + PLAZA), A + FACADE + 3 + PLAZA     # -352..352
Z0, Z1 = -(B + FACADE + 3 + PLAZA), B + FACADE + 3 + PLAZA     # -294..294
Y0, Y1 = -3, 162
WORLD_ORIGIN = (216 - X0, -61, -360 - Z1)      # yerel (0,0,0) dunyada: (568, -61, -654)


class World:
    def __init__(self):
        self.sx, self.sy, self.sz = X1 - X0 + 1, Y1 - Y0 + 1, Z1 - Z0 + 1
        self.G = np.zeros((self.sy, self.sz, self.sx), np.uint16)
        self.pal = ["keep", "minecraft:air"]
        self.pidx = {"keep": 0, "minecraft:air": 1, "air": 1}
        self.be: dict[tuple[int, int, int], str] = {}
        self.ents: list[dict] = []
        self.notes: list[str] = []

    # -------------------------------------------------------------- palet
    def id(self, state) -> int:
        if isinstance(state, (int, np.integer)):
            return int(state)
        i = self.pidx.get(state)
        if i is not None:
            return i
        exact = state.startswith("!")
        c = DB.canonical(state[1:] if exact else state)
        key = ("!" + c) if exact else c
        i = self.pidx.get(key)
        if i is None:
            i = len(self.pal)
            self.pal.append(key)
            self.pidx[key] = i
        self.pidx[state] = i
        return i

    # -------------------------------------------------------------- hucre
    def inside(self, x, y, z) -> bool:
        return X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1

    def set(self, x, y, z, state):
        if X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1:
            self.G[y - Y0, z - Z0, x - X0] = self.id(state)

    def get(self, x, y, z) -> int:
        if X0 <= x <= X1 and Y0 <= y <= Y1 and Z0 <= z <= Z1:
            return int(self.G[y - Y0, z - Z0, x - X0])
        return 0

    def name(self, x, y, z) -> str:
        return self.pal[self.get(x, y, z)]

    def box(self, x0, y0, z0, x1, y1, z1, state, only=None):
        """Kutu (uclar dahil). only: yalniz bu id'lerin (liste) uzerine yaz."""
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        za, zb = sorted((z0, z1))
        xa, ya, za = max(xa, X0), max(ya, Y0), max(za, Z0)
        xb, yb, zb = min(xb, X1), min(yb, Y1), min(zb, Z1)
        if xa > xb or ya > yb or za > zb:
            return
        v = self.G[ya - Y0:yb - Y0 + 1, za - Z0:zb - Z0 + 1, xa - X0:xb - X0 + 1]
        i = self.id(state)
        if only is None:
            v[...] = i
        else:
            v[np.isin(v, only)] = i

    def air(self, x0, y0, z0, x1, y1, z1):
        """Ic bosluk: dunyada zaten hava; 'dokunma' yazilir (gereksiz hava yerlestirmesi yok)."""
        self.box(x0, y0, z0, x1, y1, z1, 0)

    def sign(self, x, y, z, facing, lines, wood="dark_oak", color="white", glow=True, wall=True):
        """Duvar tabelasi (facing = yazinin baktigi yon) ya da ayakli tabela."""
        lines = [str(s)[:15] for s in (list(lines) + ["", "", "", ""])[:4]]
        if wall:
            self.set(x, y, z, f"{wood}_wall_sign[facing={facing},waterlogged=false]")
        else:
            rot = {"south": 0, "west": 4, "north": 8, "east": 12}[facing]
            self.set(x, y, z, f"{wood}_sign[rotation={rot},waterlogged=false]")
        msgs = ",".join(json.dumps(s, ensure_ascii=False) for s in lines)
        g = "1b" if glow else "0b"
        self.be[(x, y, z)] = ("{front_text:{messages:[" + msgs + "],color:\"" + color + "\",has_glowing_text:" + g + "},"
                              "back_text:{messages:[\"\",\"\",\"\",\"\"],color:\"black\",has_glowing_text:0b},is_waxed:1b}")

    def banner(self, x, y, z, facing=None, base="yellow", patterns=(("stripe_left", "blue"), ("stripe_center", "blue"), ("stripe_right", "blue")),
               wall=True, rotation=0):
        if wall:
            self.set(x, y, z, f"{base}_wall_banner[facing={facing}]")
        else:
            self.set(x, y, z, f"{base}_banner[rotation={rotation}]")
        pats = ",".join("{pattern:\"minecraft:%s\",color:\"%s\"}" % (p, c) for p, c in patterns)
        self.be[(x, y, z)] = "{patterns:[" + pats + "]}"

    def entity(self, etype, x, y, z, yaw=0.0, snbt="{}"):
        self.ents.append({"type": etype, "pos": [x, y, z], "yaw": yaw, "pitch": 0.0, "snbt": snbt})

    def count(self) -> int:
        return int(np.count_nonzero(self.G > 1))


ARENA_YELLOW, ARENA_NAVY = 0xFFE600, 0x14214D


def kit_item(item, color=None, name=None):
    comps = []
    if color is not None:
        comps.append(f'"minecraft:dyed_color":{color}')
    if name:
        comps.append('"minecraft:custom_name":' + json.dumps(name, ensure_ascii=False))
    c = ",components:{" + ",".join(comps) + "}" if comps else ""
    return "{id:\"minecraft:%s\",count:1%s}" % (item, c)


def figure_snbt(name, chest=ARENA_YELLOW, legs=ARENA_NAVY, feet=0x111111, head="player_head", pose=None, hand=None, small=False):
    eq = [f"head:{kit_item(head)}" if head else None,
          f"chest:{kit_item('leather_chestplate', chest)}" if chest is not None else None,
          f"legs:{kit_item('leather_leggings', legs)}" if legs is not None else None,
          f"feet:{kit_item('leather_boots', feet)}" if feet is not None else None,
          f"mainhand:{kit_item(hand)}" if hand else None]
    eq = ",".join(e for e in eq if e)
    s = "{CustomName:" + json.dumps(name, ensure_ascii=False) + ",CustomNameVisible:1b,ShowArms:1b,NoBasePlate:1b,Invulnerable:1b,"
    if small:
        s += "Small:1b,"
    s += "equipment:{" + eq + "}"
    if pose:
        s += ",Pose:" + pose
    return s + "}"


# ------------------------------------------------------------------ 5x7 yazi (Turkce harfler: aksan satiri + kuyruk satiri)
_BODY = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "-": [".....", ".....", ".....", ".###.", ".....", ".....", "....."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    "*": [".....", "..#..", "#####", ".###.", ".#.#.", "#...#", "....."],
}
_ACC = {"Ç": ("C", None, "..#.."), "Ş": ("S", None, "..#.."), "Ğ": ("G", ".###.", None), "Ü": ("U", ".#.#.", None),
        "Ö": ("O", ".#.#.", None), "İ": ("I", "..#..", None)}


def glyph(ch: str) -> list[str]:
    """9 satir x 5: satir 0 aksan, 1..7 govde, 8 kuyruk."""
    if ch == " ":
        return ["..."] * 9
    if ch in _ACC:
        base, top, bot = _ACC[ch]
        body = _BODY[base]
    else:
        body = _BODY.get(ch.upper(), _BODY["*"])
        top = bot = None
    return [top or "....."] + body + [bot or "....."]


def text_bitmap(s: str, sx: int = 1, sy: int = 1, gap: int = 1, accents: bool = True) -> np.ndarray:
    """Bool dizi [satir (ust=0), sutun]; her piksel sx x sy."""
    cols = []
    for i, ch in enumerate(s):
        g = glyph(ch)
        if not accents:
            g = g[1:8]
        w = len(g[0])
        for c in range(w):
            cols.append([g[r][c] == "#" for r in range(len(g))])
        if i < len(s) - 1:
            for _ in range(gap):
                cols.append([False] * len(g))
    if not cols:
        return np.zeros((1, 1), bool)
    a = np.array(cols, bool).T
    return np.repeat(np.repeat(a, sy, axis=0), sx, axis=1)


# ------------------------------------------------------------------ arma (Usta Arena: beyaz yazili halka, lacivert zemin, sari U)
def crest(R: int) -> list[list[str | None]]:
    n = 2 * R + 1
    out = [[None] * n for _ in range(n)]
    top_txt = text_bitmap("USTA ARENA MINECRAFT", accents=False)
    bot_txt = text_bitmap("2026", accents=False)
    for j in range(n):           # j: satir (ust = 0)
        for i in range(n):
            x, y = i - R, R - j
            r = math.hypot(x, y)
            if r > R + 0.35:
                continue
            if r > R - 1.0:
                out[j][i] = "blue"
                continue
            ring_in = R * 0.70
            if r > ring_in:
                col = "white"
                # halka yazisi: ust yayda soldan saga (harf ustu disa), alt yayda 2026 (harf ustu ice)
                th = math.atan2(y, x)                      # -pi..pi, 0 = sag
                band = (r - ring_in) / (R - 1.0 - ring_in)  # 0 ic .. 1 dis
                rowf = 1.0 - band
                if y >= -R * 0.25:
                    arc = (math.pi * 1.08 - (th if th > -0.6 else th + 2 * math.pi)) / (math.pi * 1.16)
                    tx = int(arc * top_txt.shape[1])
                    ty = int(rowf * top_txt.shape[0] * 1.05 - 0.4)
                    if 0 <= tx < top_txt.shape[1] and 0 <= ty < top_txt.shape[0] and top_txt[ty, tx]:
                        col = "red"
                else:
                    arc = (th + math.pi * 0.5) / (math.pi * 0.42) + 0.5
                    tx = int(arc * bot_txt.shape[1])
                    ty = int(band * bot_txt.shape[0] * 1.05 - 0.4)
                    if 0 <= tx < bot_txt.shape[1] and 0 <= ty < bot_txt.shape[0] and bot_txt[ty, tx]:
                        col = "red"
                out[j][i] = col
                continue
            u, v = x / ring_in, y / ring_in
            col = "blue"
            gx, gy = int((u + 0.62) / 1.24 * 5), int((0.72 - v) / 1.44 * 7)
            if 0 <= gx < 5 and 0 <= gy < 7 and _BODY["U"][gy][gx] == "#":
                col = "yellow"
            out[j][i] = col
    return out


CREST_BLOCK = {"blue": "blue_concrete", "white": "white_concrete", "red": "red_concrete", "yellow": "yellow_concrete",
               "green": "green_concrete", "lime": "lime_concrete", "brown": "brown_concrete"}


# ------------------------------------------------------------------ cokgen-yuvarlatilmis dikdortgen uzaklik alani
P_NORM = 2.6


def fields(xs: np.ndarray, zs: np.ndarray):
    """d: ic sinirdan disa uzaklik (<0 iceride); side: 0 S(+z) 1 N 2 E(+x) 3 W 4 kose; t: kenar boyu koordinat."""
    X, Z = np.meshgrid(xs, zs)
    qx, qz = np.abs(X) - A, np.abs(Z) - B
    d = np.maximum(qx, qz).astype(np.float32)
    corner = (qx > 0) & (qz > 0)
    d[corner] = ((qx[corner] ** P_NORM + qz[corner] ** P_NORM) ** (1 / P_NORM)).astype(np.float32)
    side = np.full(X.shape, 4, np.int8)
    side[(qz > 0) & (qx <= 0) & (Z > 0)] = 0
    side[(qz > 0) & (qx <= 0) & (Z < 0)] = 1
    side[(qx > 0) & (qz <= 0) & (X > 0)] = 2
    side[(qx > 0) & (qz <= 0) & (X < 0)] = 3
    side[(qx <= 0) & (qz <= 0)] = -1
    t = np.where((side == 0) | (side == 1), X, Z).astype(np.int32)
    return X, Z, d, side, t


SIDE_OUT = {0: "south", 1: "north", 2: "east", 3: "west"}
SIDE_IN = {0: "north", 1: "south", 2: "west", 3: "east"}


def side_point(side: int, t: int, d: int) -> tuple[int, int]:
    """Kenar koordinatindan (t boyunca, d disa) yerel (x, z)."""
    if side == 0:
        return t, B + d
    if side == 1:
        return t, -(B + d)
    if side == 2:
        return A + d, t
    return -(A + d), t
