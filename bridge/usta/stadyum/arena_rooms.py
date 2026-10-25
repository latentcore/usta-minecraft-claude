"""Ic mekanlar: merdiven kuleleri, kapilar/turnikeler, yemek bufeleri, WC, mescit, ilk yardim, localar, baskanlik locasi,
basin tribunu, TV kabinleri, VIP salonlari, Maraton zemin kati (tunel, soyunma odalari, basin toplanti, karma bolge,
muze, Fenerium, lobi, otobus garaji), yedek kulubeleri, teknik alan, teknik direktor, ilk 11, meydan ayrintilari."""
from __future__ import annotations

import math
import random

import numpy as np

from arena_core import (A, B, BOX_D0, BOX_D1, BOXY, CORE_D, CROSS_D0, FACADE, ARENA_NAVY, ARENA_YELLOW, GATE_CONC, LOW_CONC, PL,
                     PLAZA, PW, ROOF0, SIDE_IN, SIDE_OUT, UP_CONC, UP_D0, UP_DEEP, UPY0, VIP_CONC, X0, Y0, Z0, World,
                     crest, CREST_BLOCK, figure_snbt, kit_item, side_point, text_bitmap)
from arena_bowl import Bowl, SIDE_HALF, low_top, up_top

RNG = random.Random(1907)
FACE_VEC = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
CW = {"north": "east", "east": "south", "south": "west", "west": "north"}
CCW = {v: k for k, v in CW.items()}
OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}


def t_dir(side):
    """+t yonu (dunya yonu)."""
    return "east" if side in (0, 1) else "south"


class SideFrame:
    """Bir duz kenarda (t, d) -> yerel (x, z) ve yon donusumu."""

    def __init__(self, side):
        self.s = side
        self.out = SIDE_OUT[side]
        self.inn = SIDE_IN[side]
        self.tp = t_dir(side)
        self.tm = OPP[self.tp]

    def xz(self, t, d):
        return side_point(self.s, t, d)

    def box(self, w, ta, tb, da, db, y0, y1, state):
        x0, z0 = self.xz(ta, da)
        x1, z1 = self.xz(tb, db)
        w.box(x0, y0, z0, x1, y1, z1, state)

    def set(self, w, t, d, y, state):
        x, z = self.xz(t, d)
        w.set(x, y, z, state)

    def lbox(self, ta, tb, da, db, y0, y1):
        x0, z0 = self.xz(ta, da)
        x1, z1 = self.xz(tb, db)
        return (min(x0, x1), y0, min(z0, z1), max(x0, x1), y1, max(z0, z1))


# ------------------------------------------------------------------ kit odalarini dunyaya aktarma
def kit_room(w: World, box, kind, door_cells, seed=0, style=None):
    from usta.kit.core import Build
    from usta.kit import interiors
    x0, y0, z0, x1, y1, z1 = box
    b = Build("oda")
    ids = w.G[y0 - 1 - Y0:y1 + 2 - Y0, z0 - 1 - Z0:z1 + 2 - Z0, x0 - 1 - X0:x1 + 2 - X0]
    pal = np.array([0] + [b.pid(s) for s in w.pal[1:]], np.int32)
    sub = pal[ids.astype(np.int64)]
    b.put_ids(x0 - 1, y0 - 1, z0 - 1, sub)
    try:
        interiors.furnish(b, box, kind, style=style, door=[{"pos": list(c)} for c in door_cells], seed=seed)
    except Exception as e:
        w.notes.append(f"doseme atlandi ({kind}): {e}")
        return
    got = b.ids_box(x0 - 1, y0 - 1, z0 - 1, x1 + 1, y1 + 1, z1 + 1)
    remap = np.array([0 if s == "keep" else w.id(s) for s in b.palette], np.int64)
    view = w.G[y0 - 1 - Y0:y1 + 2 - Y0, z0 - 1 - Z0:z1 + 2 - Z0, x0 - 1 - X0:x1 + 2 - X0]
    m = got != 0
    view[m] = remap[got[m]].astype(np.uint16)
    for (x, y, z), snbt in b.block_entities.items():
        w.be[(x, y, z)] = snbt
    for e in b.entities:
        w.ents.append(dict(e))


# ------------------------------------------------------------------ genel oda kabugu (kenar cercevesinde)
def room(w, F: SideFrame, ta, tb, da, db, yf, h=6, floor="polished_andesite", wall="white_concrete", ceil="smooth_quartz",
         lights=True, door_d=None, door_t=None, door_w=2, door="opening", sign=None, sign_side="out"):
    """Ic hacim t[ta..tb] x d[da..db] x y[yf+1..yf+h]; duvarlar 1 disarida. door_d: kapinin oldugu duvar d degeri."""
    F.box(w, ta - 1, tb + 1, da - 1, db + 1, yf, yf + h + 1, wall)
    F.box(w, ta, tb, da, db, yf, yf, floor)
    F.box(w, ta, tb, da, db, yf + h + 1, yf + h + 1, ceil)
    F.box(w, ta, tb, da, db, yf + 1, yf + h, 0)
    if lights:
        for t in range(ta + 2, tb - 1, 5):
            for d in range(da + 2, db - 1, 5):
                F.set(w, t, d, yf + h + 1, "sea_lantern")
    doors = []
    if door_d is not None:
        tc = (ta + tb) // 2 if door_t is None else door_t
        for i in range(door_w):
            t = tc - door_w // 2 + i
            if door == "opening":
                F.box(w, t, t, door_d, door_d, yf + 1, yf + 4, 0)
            else:
                face = F.inn if door_d < da else F.out
                hinge = "left" if i == 0 else "right"
                F.set(w, t, door_d, yf + 1, f"{door}[facing={face},half=lower,hinge={hinge},open=false]")
                F.set(w, t, door_d, yf + 2, f"{door}[facing={face},half=upper,hinge={hinge},open=false]")
                F.box(w, t, t, door_d, door_d, yf + 3, yf + 4, wall)
            x, z = F.xz(t, door_d)
            doors.append((x, yf + 1, z))
        if sign:
            # tabela kapinin ustunde, koridor tarafinda
            face = F.inn if door_d < da else F.out
            dd = door_d - 1 if door_d < da else door_d + 1
            lines = sign if isinstance(sign, (list, tuple)) else [sign]
            x, z = F.xz(tc, dd)
            w.sign(x, yf + 5, z, face, lines)
    return F.lbox(ta, tb, da, db, yf + 1, yf + h), doors


# ------------------------------------------------------------------ merdiven kulesi (her 8 blokta sahanlik)
def stair_core(w, F: SideFrame, t0, top_level=64, open_in=(16, 32, 64), open_out=(0,)):
    di, do = CORE_D
    lane1, lane2 = (di + 1, di + 5), (di + 6, do - 1)
    F.box(w, t0 - 1, t0 + 10, di, do, 0, top_level + 7, "light_gray_concrete")
    F.box(w, t0, t0 + 9, di + 1, do - 1, 1, top_level + 6, 0)
    st_up = "smooth_quartz_stairs[facing=%s,half=bottom,shape=straight,waterlogged=false]"
    for k in range(0, top_level // 8 + 1):
        ya = 8 * k
        F.box(w, t0, t0 + 2, di + 1, do - 1, ya, ya, "polished_andesite")
        if ya + 4 <= top_level:
            F.box(w, t0 + 7, t0 + 9, di + 1, do - 1, ya + 4, ya + 4, "polished_andesite")
            for i in range(4):
                F.box(w, t0 + 3 + i, t0 + 3 + i, lane1[0], lane1[1], ya + 1 + i, ya + 1 + i, st_up % F.tp)
                F.box(w, t0 + 3 + i, t0 + 3 + i, lane1[0], lane1[1], ya + i, ya + i, "smooth_quartz")
                F.box(w, t0 + 6 - i, t0 + 6 - i, lane2[0], lane2[1], ya + 5 + i, ya + 5 + i, st_up % F.tm)
                F.box(w, t0 + 6 - i, t0 + 6 - i, lane2[0], lane2[1], ya + 4 + i, ya + 4 + i, "smooth_quartz")
            F.set(w, t0 + 8, do, ya + 7, "lantern[hanging=false]") if False else None
        F.set(w, t0 + 1, di + 3, ya + 6, "sea_lantern")
        if ya in open_in:
            F.box(w, t0, t0 + 2, di, di, ya + 1, ya + 4, 0)
            F.box(w, t0, t0 + 2, di - 1, di - 1, ya + 1, ya + 4, 0)
            x, z = F.xz(t0 + 1, di - 1)
            w.sign(x, ya + 5, z, F.inn, ["MERDİVEN", f"KOT +{ya}", "", ""])
        if ya in open_out:
            F.box(w, t0, t0 + 2, do, GATE_CONC[0] - 1, ya + 1, ya + 4, 0)
            F.box(w, t0, t0 + 2, do + 1, GATE_CONC[0] - 1, ya, ya, "polished_andesite")


# ------------------------------------------------------------------ yemek bufesi
MENUS = [("KÖFTE EKMEK", "180 TL"), ("TAVUK DÖNER", "160 TL"), ("SİMİT & ÇAY", "60 TL"), ("HAMBURGER", "220 TL"),
         ("PİZZA", "200 TL"), ("KAŞARLI TOST", "90 TL"), ("KOKOREÇ", "190 TL"), ("DONDURMA", "70 TL"),
         ("TÜRK KAHVESİ", "80 TL"), ("AYRAN - SU", "40 TL"), ("SU BÖREĞİ", "110 TL"), ("HAŞLAMA MISIR", "50 TL"),
         ("LAHMACUN", "120 TL"), ("PATATES", "90 TL"), ("ARENA BURGER", "250 TL"), ("SALEP", "75 TL")]


def kiosk(w, F: SideFrame, ta, tb, da, db, yf, n):
    name, price = MENUS[n % len(MENUS)]
    box, _ = room(w, F, ta, tb, da, db, yf, h=5, floor="white_concrete", wall="yellow_concrete", ceil="smooth_quartz",
                  lights=True)
    # on yuz: genis servis penceresi + tezgah (koridor tarafinda d = da-1)
    F.box(w, ta, tb, da - 1, da - 1, yf + 1, yf + 1, "polished_andesite")
    F.box(w, ta, tb, da - 1, da - 1, yf + 2, yf + 2, f"smooth_quartz_slab[type=bottom,waterlogged=false]")
    F.box(w, ta, tb, da - 1, da - 1, yf + 3, yf + 4, 0)
    F.box(w, ta - 1, tb + 1, da - 1, da - 1, yf + 5, yf + 5, "blue_concrete")
    x, z = F.xz((ta + tb) // 2, da - 2)
    w.sign(x, yf + 5, z, F.inn, [name, price, "USTA ARENA", "BÜFE"], color="yellow")
    # tezgah arkasi: izgara, firin, buzdolabi, cay ocagi
    gear = ["smoker[facing=%s,lit=true]", "furnace[facing=%s,lit=false]", "iron_block", "barrel[facing=up,open=false]",
            "blast_furnace[facing=%s,lit=false]", "cauldron", "brewing_stand", "chiseled_quartz_block"]
    for i, t in enumerate(range(ta, tb + 1)):
        g = gear[(i + n) % len(gear)]
        F.set(w, t, db, yf + 1, g % F.inn if "%s" in g else g)
        if i % 2 == 0:
            F.set(w, t, db, yf + 2, "light_blue_stained_glass")
        F.set(w, t, da + 1, yf + 1, "spruce_slab[type=top,waterlogged=false]")
    F.set(w, (ta + tb) // 2, (da + db) // 2, yf + 5, "lantern[hanging=true]") if False else None
    return box


# ------------------------------------------------------------------ WC
def wc(w, F: SideFrame, ta, tb, da, db, yf, gender):
    box, _ = room(w, F, ta, tb, da, db, yf, h=5, floor="white_concrete", wall="light_gray_concrete", ceil="smooth_quartz",
                  door_d=da - 1, door_w=3, sign=[f"{gender} WC", "TUVALET", "♿", ""])
    # dama zemin
    for t in range(ta, tb + 1):
        for d in range(da, db + 1):
            if (t + d) % 2:
                F.set(w, t, d, yf, "light_gray_concrete")
    # kabinler arka duvarda: bolme (beyaz cam), kapi (huş), klozet (kuvars basamak), yanda kagit (tripwire hook)
    for t in range(ta + 1, tb - 1, 3):
        F.box(w, t - 1, t - 1, db - 2, db, yf + 1, yf + 3, "white_stained_glass_pane")
        F.set(w, t, db, yf + 1, f"quartz_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
        F.set(w, t + 1, db - 2, yf + 1, f"birch_door[facing={F.inn},half=lower,hinge=left,open=false]")
        F.set(w, t + 1, db - 2, yf + 2, f"birch_door[facing={F.inn},half=upper,hinge=left,open=false]")
        F.box(w, t, t, db - 2, db - 2, yf + 1, yf + 3, "white_stained_glass_pane")
    F.box(w, tb - 1, tb - 1, db - 2, db, yf + 1, yf + 3, "white_stained_glass_pane")
    # lavabolar (su dolu kazan) + ayna (cam) + kurutma (tas dugme) yan duvarda
    for d in range(da + 1, db - 3, 2):
        F.set(w, ta, d, yf + 1, "water_cauldron[level=3]")
        F.set(w, ta, d, yf + 2, "glass_pane")
        F.set(w, ta, d, yf + 3, "glass_pane")
    if gender == "ERKEK":
        for d in range(da + 1, db - 3, 2):
            F.set(w, tb, d, yf + 2, f"iron_trapdoor[facing={CW[F.tp] if False else F.tm},half=top,open=true,powered=false,waterlogged=false]")
    return box


# ------------------------------------------------------------------ loca
def suite(w, F: SideFrame, ta, tb, n, president=False):
    yf = BOXY
    da, db = BOX_D0 + 1, BOX_D1 - 2          # 63..72
    floor = "polished_diorite" if not president else "gold_block"
    box, doors = room(w, F, ta, tb, da, db, yf, h=6, floor=floor, wall="white_concrete", ceil="smooth_quartz",
                      lights=True, door_d=db + 1, door_w=1, door="dark_oak_door",
                      sign=["BAŞKANLIK", "LOCASI", "", ""] if president else [f"LOCA {n}", "", "", ""])
    # on cephe: tamamen cam (sahaya bakan), alt korkuluk
    F.box(w, ta, tb, da - 1, da - 1, yf + 1, yf + 6, "glass_pane")
    F.box(w, ta, tb, da - 1, da - 1, yf + 1, yf + 1, "white_concrete")
    # hali + koltuklar (sahaya bakan) + sehpa + TV + mini bar
    rug = "blue_carpet" if not president else "yellow_carpet"
    F.box(w, ta, tb, da + 1, db - 1, yf + 1, yf + 1, rug)
    sofa = f"{'quartz' if not president else 'dark_oak'}_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]"
    for t in range(ta, tb + 1):
        F.set(w, t, da + 2, yf + 1, sofa)
        if (tb - ta) > 6:
            F.set(w, t, da + 5, yf + 1, sofa)
    F.set(w, (ta + tb) // 2, da + 4, yf + 1, "dark_oak_slab[type=top,waterlogged=false]")
    F.set(w, ta, db, yf + 1, "barrel[facing=up,open=false]")
    F.set(w, ta + 1, db, yf + 1, "brewing_stand")
    F.set(w, ta + 2, db, yf + 1, "iron_block")
    F.set(w, tb, db - 2, yf + 2, "black_stained_glass")
    F.set(w, tb, db - 2, yf + 3, "black_stained_glass")
    F.set(w, tb - 1, db - 2, yf + 2, "black_stained_glass")
    F.set(w, tb - 1, db - 2, yf + 3, "black_stained_glass")
    F.set(w, tb, db, yf + 1, "potted_bamboo" if president else "potted_red_tulip")
    # balkon koltuklari (cam onunde, capraz koridor ustunde): 2 sira deri koltuk
    seat = f"{'polished_blackstone' if not president else 'bamboo_mosaic'}_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]"
    for t in range(ta, tb + 1):
        F.set(w, t, da - 2, yf + 1, seat)
        F.set(w, t, da - 4, yf + 1, seat)
    if president:
        F.box(w, ta, tb, da - 1, da - 1, yf + 6, yf + 6, "gold_block")
        w.banner(*F.xz(ta, db), yf + 4, facing=F.inn) if False else None
        x, z = F.xz(ta + 1, db)
        w.banner(x, yf + 4, z, facing=F.inn)
        x, z = F.xz(tb - 1, db)
        w.banner(x, yf + 4, z, facing=F.inn)
    return box


# ------------------------------------------------------------------ TV kabinleri ve basin tribunu (Maraton ust tribun onu)
def press_tribune(w, F: SideFrame):
    ta, tb = -36, 36
    rows = 6
    for u in range(rows):
        d0 = UP_D0 + UP_DEEP * u
        y = UPY0 + 2 * u
        for t in range(ta, tb + 1):
            if t % 30 in (0, 1):
                continue
            F.set(w, t, d0, y + 1, "spruce_slab[type=top,waterlogged=false]")
            if t % 2 == 0:
                F.set(w, t, d0, y + 2, "black_stained_glass_pane")
            F.set(w, t, d0 + 1, y + 1, f"dark_oak_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
    x, z = F.xz(0, UP_D0 - 3)
    w.sign(x, UPY0 - 1, z, F.inn, ["BASIN", "TRİBÜNÜ", "", ""])
    # TV kabinleri: iki yanda 5'er cam kabin, ilk 4 sira duzlestirilir
    for side_sign in (-1, 1):
        for i in range(5):
            tc = side_sign * (44 + i * 10)
            ta2, tb2 = tc - 4, tc + 4
            d0, d1 = UP_D0, UP_D0 + 7
            F.box(w, ta2, tb2, d0, d1, UPY0 - 1, UPY0, "light_gray_concrete")
            F.box(w, ta2, tb2, d0, d1, UPY0 + 1, UPY0 + 6, 0)
            F.box(w, ta2, tb2, d0, d0, UPY0 + 1, UPY0 + 5, "glass_pane")
            F.box(w, ta2 - 1, ta2 - 1, d0, d1, UPY0 + 1, UPY0 + 5, "white_stained_glass_pane")
            F.box(w, tb2 + 1, tb2 + 1, d0, d1, UPY0 + 1, UPY0 + 5, "white_stained_glass_pane")
            F.box(w, ta2 - 1, tb2 + 1, d0, d1 + 1, UPY0 + 6, UPY0 + 6, "white_concrete")
            F.box(w, ta2, tb2, d0 + 1, d0 + 1, UPY0 + 1, UPY0 + 1, "spruce_slab[type=top,waterlogged=false]")
            for t in range(ta2, tb2 + 1, 2):
                F.set(w, t, d0 + 1, UPY0 + 2, "black_stained_glass_pane")
            for t in (tc - 2, tc + 2):
                F.set(w, t, d0 + 3, UPY0 + 1, f"spruce_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
            F.set(w, tc, d0 + 1, UPY0 + 2, "lightning_rod[facing=up,powered=false,waterlogged=false]")
            F.box(w, ta2, tb2, d1, d1, UPY0 + 1, UPY0 + 2, "barrel[facing=up,open=false]")
            F.set(w, tc, d1, UPY0 + 3, "observer[facing=%s,powered=false]" % F.inn)
            x, z = F.xz(tc, d0 - 1)
            w.sign(x, UPY0 + 5, z, F.inn, [f"TV {i + 1 + (0 if side_sign > 0 else 5)}", "YORUM KABİNİ", "", ""])
    # ana kamera platformu (on alin ortasinda)
    F.box(w, -3, 3, UP_D0 - 6, UP_D0 - 3, UPY0 - 1, UPY0 - 1, "light_gray_concrete")
    F.box(w, -3, 3, UP_D0 - 6, UP_D0 - 6, UPY0, UPY0, "iron_bars")
    for t in (-2, 0, 2):
        F.set(w, t, UP_D0 - 4, UPY0, "oak_fence")
        F.set(w, t, UP_D0 - 4, UPY0 + 1, "observer[facing=%s,powered=false]" % F.inn)


# ------------------------------------------------------------------ kapilar, turnikeler, giseler
def gates(w, b: Bowl):
    n = 1
    for s in (0, 2, 1, 3):
        F = SideFrame(s)
        half = SIDE_HALF[s]
        for t in range(-half + 30, half - 20, 60):
            if s == 0 and abs(t) < 40:
                continue
            gi, go = GATE_CONC[1], FACADE + 2
            F.box(w, t - 3, t + 3, gi, go, 1, 7, 0)
            F.box(w, t - 3, t + 3, gi, go, 0, 0, "polished_andesite")
            F.box(w, t - 4, t + 4, go, go, 8, 9, "yellow_concrete")
            # turnike hatti: demir parmaklik + citli kapilar
            dturn = FACADE - 3
            for tt in range(t - 3, t + 4):
                F.set(w, tt, dturn, 1, "iron_bars" if tt % 2 else f"oak_fence_gate[facing={F.inn},in_wall=false,open=false,powered=false]")
            # guvenlik x-isini kapisi
            F.box(w, t - 3, t - 3, FACADE - 6, FACADE - 6, 1, 3, "iron_block")
            F.box(w, t - 1, t - 1, FACADE - 6, FACADE - 6, 1, 3, "iron_block")
            F.box(w, t - 3, t - 1, FACADE - 6, FACADE - 6, 4, 4, "iron_block")
            x, z = F.xz(t, go + 1)
            w.sign(x, 9, z, F.out, [f"KAPI {n}", ["MARATON", "AÇIK", "KALE ARKASI", "KALE ARKASI"][s], "TRİBÜNÜ", ""])
            # disarida gise kulubesi
            gb = FACADE + 6
            F.box(w, t + 6, t + 10, gb, gb + 4, 0, 5, "blue_concrete")
            F.box(w, t + 7, t + 9, gb + 1, gb + 3, 1, 4, 0)
            F.box(w, t + 7, t + 9, gb, gb, 2, 3, "glass_pane")
            F.box(w, t + 6, t + 10, gb, gb + 4, 5, 5, "yellow_concrete")
            x, z = F.xz(t + 8, gb - 1)
            w.sign(x, 4, z, F.out, ["GİŞE", "BİLET", "PASSOLİG", ""])
            n += 1


def free_spans(lo, hi, busy):
    """[lo, hi] araliginda mesgul araliklar disinda kalan parcalar."""
    cuts = sorted((max(lo, a), min(hi, b)) for a, b in busy if b >= lo and a <= hi)
    out, cur = [], lo
    for a, b in cuts:
        if a - 2 > cur:
            out.append((cur, a - 2))
        cur = max(cur, b + 2)
    if hi > cur:
        out.append((cur, hi))
    return out


def split_span(a, b, wmin, wmax):
    n = max(1, (b - a + 2) // (wmax + 2))
    while n > 1 and (b - a + 2) // n - 2 < wmin:
        n -= 1
    if (b - a + 2) // n - 2 < wmin:
        return []
    step = (b - a + 2) // n
    return [(a + i * step, a + i * step + step - 2) for i in range(n)]


def fan_banners(w):
    """Saha onu duvarlarina taraftar bayraklari (GFB kale arkasi yogun)."""
    pats = [(("stripe_left", "blue"), ("stripe_center", "blue"), ("stripe_right", "blue")),
            (("half_vertical", "blue"),),
            (("stripe_middle", "yellow"), ("border", "yellow"))]
    for s in (0, 1, 2, 3):
        F = SideFrame(s)
        half = SIDE_HALF[s]
        step = 3 if s == 2 else 9
        for k, t in enumerate(range(-half + 6, half - 5, step)):
            if s == 0 and abs(t) < 80:
                continue
            x, z = F.xz(t, -1)
            base = "yellow" if k % 3 != 1 else "blue"
            w.banner(x, 3, z, facing=F.inn, base=base, patterns=pats[k % 3])


# ------------------------------------------------------------------ duz kenar modulleri (konkur katlari)
def side_modules(w, b: Bowl):
    kinds_front = ["kiosk", "kiosk", "wc_e", "wc_k", "kiosk", "first_aid", "kiosk", "mescit", "kiosk", "shop", "kiosk", "kiosk"]
    cnt = {"kiosk": 0, "room": 0}
    suites_n = 1
    for s in (0, 1, 2, 3):
        F = SideFrame(s)
        half = SIDE_HALF[s]
        cores = [-(half - 60), half - 70]
        busy = []
        for t0 in cores:
            busy.append((t0 - 3, t0 + 13))
            # cekirdek gecitleri: alt konkur, VIP koridoru, ust konkur -> kule
            F.box(w, t0, t0 + 2, LOW_CONC[1], CORE_D[0] - 1, LOW_CONC[2] + 1, LOW_CONC[2] + 5, 0)
            F.box(w, t0, t0 + 2, LOW_CONC[1], CORE_D[0] - 1, LOW_CONC[2], LOW_CONC[2], "polished_andesite")
            F.box(w, t0, t0 + 2, VIP_CONC[1], CORE_D[0] - 1, VIP_CONC[2] + 1, VIP_CONC[2] + 5, 0)
            F.box(w, t0, t0 + 2, VIP_CONC[1], CORE_D[0] - 1, VIP_CONC[2], VIP_CONC[2], "polished_andesite")
            F.box(w, t0, t0 + 2, UP_CONC[1], CORE_D[0] - 1, UP_CONC[2] + 1, UP_CONC[2] + 5, 0)
            F.box(w, t0, t0 + 2, UP_CONC[1], CORE_D[0] - 1, UP_CONC[2], UP_CONC[2], "polished_andesite")
            stair_core(w, F, t0)

        def free(ta, tb):
            return all(tb < a or ta > bb for a, bb in busy)

        # alt konkur (y=16): on sira bufeler/WC/mescit/ilk yardim (d 57..74), kapilari konkura
        yf = LOW_CONC[2]
        i = 0
        t = -half + 16
        while t < half - 16:
            kind = kinds_front[(i + s * 3) % len(kinds_front)]
            wdt = 23 if kind.startswith("wc") or kind in ("mescit", "shop", "first_aid") else 11
            ta, tb = t, t + wdt - 1
            if not free(ta - 1, tb + 1):
                t += 4
                continue
            da, db = LOW_CONC[1] + 1, LOW_CONC[1] + 18
            if kind == "kiosk":
                kiosk(w, F, ta, tb, da, db, yf, cnt["kiosk"])
                cnt["kiosk"] += 1
            elif kind == "wc_e":
                wc(w, F, ta, tb, da, db, yf, "ERKEK")
            elif kind == "wc_k":
                wc(w, F, ta, tb, da, db, yf, "KADIN")
            else:
                label = {"first_aid": ["İLK YARDIM", "SAĞLIK", "+", ""], "mescit": ["MESCİT", "", "", ""],
                         "shop": ["ARENA STORE", "MAĞAZA", "", ""]}[kind]
                fk = {"first_aid": "lab", "mescit": "prayer_hall", "shop": "shop"}[kind]
                box, doors = room(w, F, ta, tb, da, db, yf, h=5, door_d=da - 1, door_w=3, sign=label,
                                  wall="white_concrete", floor="polished_diorite")
                kit_room(w, box, fk, doors, seed=i + 7 * s)
                if kind == "first_aid":
                    for (du, dv) in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)):
                        F.set(w, ta + 3 + du, da - 1, yf + 3 + dv, "red_concrete")
            i += 1
            t = tb + 2
        # localar (y=BOXY): kenar boyunca 9'luk moduller; Maraton ortasinda baskanlik locasi
        if s == 0:
            suite(w, F, -14, 14, 0, president=True)
            busy.append((-16, 16))
        t = -half + 12
        while t < half - 12:
            ta, tb = t, t + 7
            if not free(ta - 1, tb + 1):
                t += 3
                continue
            suite(w, F, ta, tb, suites_n)
            suites_n += 1
            t = tb + 2
        # bos araliklar (cekirdekler ve baskanlik locasi disi)
        spans = free_spans(-half + 16, half - 16, busy)
        # VIP salonlari (y=BOXY, d 81..101)
        vip_kinds = [("living_room", ["VIP SALON", "ARENA", "LOUNGE", ""]), ("dining_room", ["RESTORAN", "2026", "", ""]),
                     ("tea_room", ["ÇAY", "SALONU", "", ""]), ("great_hall", ["BUSINESS", "CLUB", "", ""]),
                     ("library", ["KULÜP", "KÜTÜPHANESİ", "", ""]), ("kitchen", ["VIP", "MUTFAK", "", ""])]
        k = 0
        for (sa, sb) in spans:
            for (ta, tb) in split_span(sa, sb, 26, 40):
                kind, label = vip_kinds[(k + s) % len(vip_kinds)]
                box, doors = room(w, F, ta, tb, VIP_CONC[1] + 1, CORE_D[0] - 2, BOXY, h=6, door_d=VIP_CONC[1], door_w=3,
                                  door="opening", sign=label, floor="polished_diorite", wall="white_concrete")
                kit_room(w, box, kind, doors, seed=k + 11 * s)
                k += 1
        # alt konkur arka sira: buyuk salonlar (d 78..100), cekirdek gecitlerine kapili
        hall_kinds = [("cafe", ["ARENA CAFE", "", "", ""]), ("dining_room", ["TARAFTAR", "RESTORANI", "", ""]),
                      ("kids_room", ["ÇOCUK", "OYUN ALANI", "", ""]), ("library", ["KUPA", "SERGİSİ", "", ""])]
        for ci, t0 in enumerate(cores):
            for side_k, (ta, tb, dt) in enumerate(((t0 - 34, t0 - 2, t0 - 1), (t0 + 4, t0 + 36, t0 + 3))):
                if ta < -half + 14 or tb > half - 14:
                    continue
                kind, label = hall_kinds[(ci * 2 + side_k + s) % len(hall_kinds)]
                box, _ = room(w, F, ta, tb, 78, 100, LOW_CONC[2], h=6, floor="polished_diorite", wall="white_concrete")
                F.box(w, dt, dt, 87, 90, LOW_CONC[2] + 1, LOW_CONC[2] + 4, 0)
                x, z = F.xz(dt, 86)
                kit_room(w, box, kind, [(x, LOW_CONC[2] + 1, z)], seed=ci + 5 * s)
                tt = dt + (-1 if side_k == 0 else 1)
                xs_, zs_ = F.xz(dt + (1 if side_k == 0 else -1), 91)
                w.sign(xs_, LOW_CONC[2] + 4, zs_, F.tp if side_k == 0 else F.tm, label)
        # ust konkur arkasi (y=64, d 102..134): kafeterya, cay ocagi, WC, Maraton'da panorama restoran (cephe camli)
        up_kinds = ["cafe", "wc_e", "wc_k", "tea_room", "dining_room"]
        k = 0
        for (sa, sb) in spans:
            for (ta, tb) in split_span(sa, sb, 22, 34):
                kind = up_kinds[(k + s) % len(up_kinds)]
                yf = UP_CONC[2]
                if kind.startswith("wc"):
                    wc(w, F, ta, tb, 102, 120, yf, "ERKEK" if kind == "wc_e" else "KADIN")
                    F.box(w, (ta + tb) // 2 - 1, (ta + tb) // 2 + 1, UP_CONC[1], 101, yf + 1, yf + 3, 0)
                else:
                    pano = (s == 0 and kind == "dining_room")
                    db = 137 if pano else 134
                    label = (["PANORAMA", "RESTORAN", "", ""] if pano else
                             {"cafe": ["KAFETERYA", "", "", ""], "tea_room": ["ÇAY OCAĞI", "", "", ""],
                              "dining_room": ["RESTORAN", "", "", ""]}[kind])
                    box, doors = room(w, F, ta, tb, 102, db, yf, h=6, door_d=101, door_w=3, sign=None,
                                      floor="polished_diorite", wall="white_concrete")
                    F.box(w, (ta + tb) // 2 - 1, (ta + tb) // 2 + 1, UP_CONC[1], 101, yf + 1, yf + 4, 0)
                    x, z = F.xz((ta + tb) // 2 + 3, UP_CONC[1] - 1)
                    w.sign(x, yf + 5, z, F.inn, label)
                    if pano:
                        F.box(w, ta, tb, FACADE, FACADE, yf + 1, yf + 6, 0)
                    kit_room(w, box, kind, doors, seed=k + 3 * s)
                k += 1
        # zemin kat (Maraton disi): kapi galerisine bakan hizmet odalari (d 100..120)
        if s != 0:
            svc = [("lab", ["İLK YARDIM", "SAĞLIK", "", ""]), ("control_room", ["POLİS", "GÜVENLİK", "", ""]),
                   ("home_office", ["TARAFTAR", "HİZMETLERİ", "", ""]), ("workshop", ["ZEMİN", "BAKIM", "", ""]),
                   ("pantry", ["DEPO", "", "", ""]), ("shop", ["ARENA STORE", "", "", ""])]
            k = 0
            for (sa, sb) in spans:
                for (ta, tb) in split_span(sa, sb, 20, 30):
                    kind, label = svc[(k + s) % len(svc)]
                    box, doors = room(w, F, ta, tb, 100, 120, 0, h=6, door_d=121, door_w=2, door="opening", sign=label,
                                      floor="polished_andesite", wall="white_concrete")
                    kit_room(w, box, kind, doors, seed=100 + k + s)
                    k += 1
        # ust konkur (y=64): dis duvar boyunca bufe tezgahlari
        yf = UP_CONC[2]
        for tc in range(-half + 20, half - 20, 30):
            if not free(tc - 4, tc + 4):
                continue
            dd = UP_CONC[1] - 1
            F.box(w, tc - 4, tc + 4, dd, dd, yf + 1, yf + 1, "yellow_concrete")
            F.box(w, tc - 4, tc + 4, dd, dd, yf + 2, yf + 2, "smooth_quartz_slab[type=bottom,waterlogged=false]")
            F.box(w, tc - 4, tc + 4, dd + 1, dd + 1, yf + 1, yf + 3, "white_concrete")
            name, price = MENUS[(tc // 30 + s * 5) % len(MENUS)]
            x, z = F.xz(tc, dd)
            w.sign(x, yf + 5, z, F.inn, [name, price, "", ""], color="yellow")
            F.set(w, tc - 3, dd, yf + 3, "smoker[facing=%s,lit=true]" % F.inn) if False else None


# ------------------------------------------------------------------ Maraton zemin kati: oyuncu ve basin bolgesi
LOCKERS = [(str(n), f"OYUNCU {n}") for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21)]


def main_ground(w, b: Bowl):
    F = SideFrame(0)
    yf = 0
    # --- oyuncu tuneli: sahadan (on duvar) tunel salonuna; ilk 10 d acik hendek
    F.box(w, -5, 5, 0, 44, 1, 6, 0)
    F.box(w, -5, 5, 0, 44, 0, 0, "black_concrete")
    for d in range(0, 10):
        F.box(w, -5, 5, d, d, 7, low_top(d) + 2, 0)
    F.box(w, -6, -6, 0, 44, 1, 6, "white_concrete")
    F.box(w, 6, 6, 0, 44, 1, 6, "white_concrete")
    F.box(w, -6, -6, 0, 44, 3, 3, "yellow_concrete")
    F.box(w, 6, 6, 0, 44, 3, 3, "yellow_concrete")
    F.box(w, -6, -6, 0, 44, 2, 2, "blue_concrete")
    F.box(w, 6, 6, 0, 44, 2, 2, "blue_concrete")
    F.box(w, -5, 5, 10, 44, 7, 7, "smooth_quartz")
    for d in range(12, 44, 4):
        F.set(w, 0, d, 7, "sea_lantern")
    # tunel agzi
    # sahaya uzanan katlanir tunel (beyaz cerceve, yari saydam cati)
    for d in range(-14, 0):
        F.box(w, -5, 5, d, d, 6, 6, "white_stained_glass")
        for t in (-5, 5):
            F.box(w, t, t, d, d, 1, 5, "yellow_stained_glass_pane" if d % 2 else "blue_stained_glass_pane")
        if d % 3 == 0:
            F.box(w, -5, 5, d, d, 6, 6, "white_concrete")
    # --- tunel salonu (d 45..62): dev arma duvari, el sikisma cizgisi, flash roportaj panolari
    box, _ = room(w, F, -30, 30, 45, 62, yf, h=8, floor="polished_blackstone", wall="blue_concrete", ceil="smooth_quartz")
    F.box(w, -5, 5, 44, 44, 1, 6, 0)
    cr = crest(4)
    for j, row in enumerate(cr):
        for i, c in enumerate(row):
            if c:
                F.set(w, -(i - 4), 63, 9 - j, CREST_BLOCK[c])
    for t in range(-28, 29, 4):
        F.set(w, t, 47, 1, "yellow_carpet")
    for tt in (-24, 24):
        F.box(w, tt - 3, tt + 3, 61, 61, 1, 5, "white_concrete")
        for t in range(tt - 3, tt + 4, 2):
            F.set(w, t, 61, 3, "blue_concrete")
            F.set(w, t, 61, 4, "yellow_concrete")
        x, z = F.xz(tt, 60)
        w.sign(x, 5, z, F.inn, ["FLASH", "RÖPORTAJ", "USTA", ""])
    x, z = F.xz(0, 44)
    w.sign(x, 6, z, F.out, ["OYUNCU TÜNELİ", "BU TÜNELDEN", "GEÇMEK BİR", "ONURDUR"])
    # --- ev sahibi soyunma odasi (dogu: t 9..47, d 12..42)
    box, doors = room(w, F, 9, 47, 13, 42, yf, h=6, floor="blue_concrete", wall="white_concrete", ceil="smooth_quartz",
                      door_d=43, door_t=28, door_w=3, door="opening",
                      sign=["EV SAHİBİ", "SOYUNMA ODASI", "", ""], sign_side="out")
    # zemin: dev arma halisi
    cr = crest(11)
    for j, row in enumerate(cr):
        for i, c in enumerate(row):
            if c:
                F.set(w, 28 + i - 11, 27 + j - 11, 1, {"blue": "blue_carpet", "white": "white_carpet", "red": "red_carpet",
                                                        "yellow": "yellow_carpet", "green": "green_carpet",
                                                        "lime": "lime_carpet", "brown": "brown_carpet"}[c])
    # dolaplar: iki uzun duvar boyunca, her biri 2 genis nis; isim tabelasi + forma (zirh askisi) + bank
    lockers = []
    for t in range(10, 46, 3):
        lockers.append((t, 13, F.out))       # pitch tarafi (d dusuk) duvar -> yuz ice
        lockers.append((t, 42, F.inn))
    for k, (t, d, face) in enumerate(lockers[:len(LOCKERS)]):
        num, name = LOCKERS[k]
        dd = d
        inward = 1 if d == 13 else -1
        F.set(w, t, dd, 1, "spruce_planks")
        F.set(w, t, dd, 4, "spruce_planks")
        F.set(w, t, dd, 5, "yellow_concrete")
        F.set(w, t + 1, dd, 1, "spruce_planks")
        F.set(w, t + 1, dd, 4, "spruce_planks")
        face_dir = F.out if inward > 0 else F.inn
        x, z = F.xz(t, dd + inward)
        w.sign(x, 5, z, face_dir, [num, name, "", ""], color="white")
        ex, ez = F.xz(t, dd)
        yaw = 0.0 if face_dir == "south" else 180.0
        w.entity("minecraft:armor_stand", ex + 0.5, 2.0, ez + 0.5, yaw=yaw,
                 snbt=figure_snbt(f"{num} {name}", chest=ARENA_YELLOW, legs=ARENA_NAVY, feet=0x111111, head=None))
        # bank
        F.set(w, t, dd + 2 * inward, 1, f"spruce_stairs[facing={F.inn if inward < 0 else F.out},half=bottom,shape=straight,waterlogged=false]")
        F.set(w, t + 1, dd + 2 * inward, 1, f"spruce_stairs[facing={F.inn if inward < 0 else F.out},half=bottom,shape=straight,waterlogged=false]")
    # taktik tahtasi (bati duvari): yesil saha + beyaz oyuncular 4-2-3-1
    for j in range(5):
        for i in range(9):
            F.set(w, 8, 20 + i, 2 + j, "green_concrete")
    for (i, j) in ((4, 0), (1, 1), (3, 1), (5, 1), (7, 1), (3, 2), (5, 2), (2, 3), (4, 3), (6, 3), (4, 4)):
        F.set(w, 8, 20 + i, 2 + j, "white_concrete")
    # --- hidroterapi (t 49..63, d 13..27): buz havuzu, jakuzi (ruh kumu kabarcik), sauna
    box, doors = room(w, F, 49, 63, 13, 27, yf, h=6, floor="smooth_quartz", wall="white_concrete", ceil="smooth_quartz")
    F.box(w, 48, 48, 18, 20, 1, 3, 0)
    x, z = F.xz(47, 21)
    w.sign(x, 4, z, F.tm, ["HİDROTERAPİ", "BUZ HAVUZU", "JAKUZİ", "SAUNA"])
    F.box(w, 50, 55, 14, 19, 0, 0, "water")
    F.box(w, 50, 55, 14, 19, -1, -1, "packed_ice")
    F.box(w, 57, 62, 14, 19, 0, 0, "water")
    F.box(w, 57, 62, 14, 19, -1, -1, "soul_sand")
    F.box(w, 49, 63, 21, 26, 1, 1, "spruce_planks")
    F.box(w, 49, 63, 21, 21, 2, 4, "spruce_planks")
    F.box(w, 55, 57, 21, 21, 2, 3, 0)
    for t in range(50, 63, 2):
        F.set(w, t, 25, 2, f"spruce_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
    x, z = F.xz(56, 20)
    w.sign(x, 4, z, F.inn, ["SAUNA", "", "", ""])
    # --- fizyoterapi + masaj (t 49..63, d 30..42)
    box, doors = room(w, F, 49, 63, 30, 42, yf, h=6, floor="polished_diorite", wall="white_concrete")
    F.box(w, 48, 48, 34, 36, 1, 3, 0)
    x, z = F.xz(47, 37)
    w.sign(x, 4, z, F.tm, ["FİZYOTERAPİ", "MASAJ", "", ""])
    F.box(w, 64, 64, 18, 20, 1, 3, 0)
    F.box(w, 64, 64, 34, 36, 1, 3, 0)
    for t in range(50, 63, 4):
        F.box(w, t, t + 1, 33, 35, 1, 1, "white_wool")
        F.box(w, t, t + 1, 38, 40, 1, 1, "white_wool")
    F.box(w, 49, 63, 42, 42, 1, 2, "barrel[facing=up,open=false]")
    # --- misafir soyunma odasi (bati: t -47..-9) + dus
    box, doors = room(w, F, -47, -9, 13, 42, yf, h=6, floor="gray_concrete", wall="light_gray_concrete",
                      door_d=43, door_t=-28, door_w=3, sign=["MİSAFİR TAKIM", "SOYUNMA ODASI", "", ""])
    for t in range(-46, -10, 3):
        for d, inward in ((13, 1), (42, -1)):
            F.box(w, t, t + 1, d, d, 1, 4, "gray_concrete")
            F.set(w, t, d + 2 * inward, 1, f"stone_brick_stairs[facing={F.inn if inward < 0 else F.out},half=bottom,shape=straight,waterlogged=false]")
    box, doors = room(w, F, -63, -49, 13, 42, yf, h=6, floor="smooth_quartz", wall="white_concrete",
                      door_d=43, door_t=-56, door_w=2, sign=["MİSAFİR", "DUŞ", "", ""])
    for t in range(-62, -49, 3):
        F.set(w, t, 14, 1, "water_cauldron[level=3]")
        F.box(w, t + 1, t + 1, 13, 18, 1, 3, "white_stained_glass_pane")
    # --- ev sahibi duslari (t 65..79, d 13..42)
    box, doors = room(w, F, 65, 79, 13, 42, yf, h=6, floor="smooth_quartz", wall="white_concrete",
                      door_d=43, door_t=72, door_w=2, sign=["EV SAHİBİ", "DUŞLAR", "", ""])
    for d in range(14, 42, 3):
        F.set(w, 79, d, 1, "water_cauldron[level=3]")
        F.box(w, 74, 79, d + 1, d + 1, 1, 3, "light_blue_stained_glass_pane")
    # --- koridor (d 44 hizasinda degil; tunel salonunun yanlarinda dogu-bati koridor d 64..69)
    F.box(w, -103, 100, 64, 69, 1, 6, 0)
    F.box(w, -103, 100, 64, 69, 0, 0, "polished_andesite")
    F.box(w, -103, 100, 64, 69, 7, 7, "smooth_quartz")
    for t in range(-98, 99, 6):
        F.set(w, t, 66, 7, "sea_lantern")
    F.box(w, -100, 100, 63, 63, 1, 6, "white_concrete") if False else None
    for tt in (-28, 28, -56, 56, 72):
        F.box(w, tt - 1, tt + 1, 43, 63, 1, 4, 0)
        F.box(w, tt - 1, tt + 1, 43, 63, 0, 0, "polished_andesite")
    # --- ikinci sira odalar (d 71..96): hakem, doping, saglik, teknik direktor ofisi, antrenor odasi, video analiz,
    #     malzeme, top cocuklari, VAR, guvenlik kontrol, basin calisma, TV studyosu, fotografci odasi
    progs = [
        (-98, -80, "control_room", ["GÜVENLİK", "KONTROL", "MERKEZİ", ""]),
        (-78, -64, "lab", ["DOPİNG", "KONTROL", "", ""]),
        (-62, -48, "home_office", ["HAKEM", "ODASI", "", ""]),
        (-46, -32, "control_room", ["VAR", "ODASI", "", ""]),
        (-30, -16, "lab", ["SAĞLIK", "MERKEZİ", "", ""]),
        (16, 34, "home_office", ["TEKNİK DİREKTÖR", "OFİSİ", "", ""]),
        (36, 50, "home_office", ["YARDIMCI", "ANTRENÖRLER", "", ""]),
        (52, 66, "library", ["VİDEO ANALİZ", "TAKTİK", "", ""]),
        (68, 82, "laundry", ["MALZEME", "ODASI", "", ""]),
        (84, 98, "gym", ["ISINMA", "SALONU", "", ""]),
    ]
    for (ta, tb, kind, label) in progs:
        box, doors = room(w, F, ta, tb, 71, 92, yf, h=6, door_d=70, door_w=2, door="dark_oak_door", sign=label,
                          floor="polished_diorite", wall="white_concrete")
        kit_room(w, box, kind, doors, seed=ta)
        if "OFİSİ" in label[1]:
            x, z = F.xz((ta + tb) // 2, 88)
            w.banner(x, 4, z + 3 if False else z, facing=F.inn) if False else None
            for tt in (ta + 1, tb - 1):
                x, z = F.xz(tt, 93)
                w.banner(x, 4, z, facing=F.inn)
            x, z = F.xz((ta + tb) // 2, 90)
            w.entity("minecraft:armor_stand", x + 0.5, 1.0, z + 0.5, yaw=180.0,
                     snbt=figure_snbt("Teknik Direktör", chest=ARENA_NAVY, legs=ARENA_NAVY, feet=0x111111,
                                      head="player_head", small=False))
    # --- basin toplanti salonu (t -175..-104, d 12..52): kursu, sponsor duvari, sira sira koltuk, kamera platformu
    ta, tb, da, db = -168, -104, 13, 52
    box, doors = room(w, F, ta, tb, da, db, yf, h=7, floor="blue_concrete", wall="white_concrete", ceil="smooth_quartz",
                      door_d=db + 1, door_t=-136, door_w=3, door="opening", sign=["BASIN TOPLANTI", "SALONU", "", ""])
    # sponsor duvari (bati duvari t=ta-1): arma + dama deseni
    for d in range(da, db + 1):
        for y in range(1, 8):
            F.set(w, ta - 1, d, y, "yellow_concrete" if ((d // 4) + (y // 2)) % 2 else "blue_concrete")
    cr = crest(4)
    for rep in range(3):
        dc = da + 8 + rep * 12
        for j, row in enumerate(cr):
            for i, c in enumerate(row):
                if c:
                    F.set(w, ta - 1, dc + i - 4, 7 - j + 1, CREST_BLOCK[c])
    # kursu: yukseltilmis platform, uzun masa, 3 koltuk, mikrofonlar, isimlik
    F.box(w, ta, ta + 5, da + 6, db - 6, 1, 1, "smooth_stone")
    F.box(w, ta + 3, ta + 3, da + 12, db - 12, 2, 2, "dark_oak_slab[type=top,waterlogged=false]")
    for d in (da + 14, (da + db) // 2, db - 14):
        if d != (da + db) // 2:
            F.set(w, ta + 1, d, 2, f"dark_oak_stairs[facing={F.tm},half=bottom,shape=straight,waterlogged=false]")
        F.set(w, ta + 3, d, 3, "lightning_rod[facing=up,powered=false,waterlogged=false]")
    x, z = F.xz(ta + 2, (da + db) // 2)
    w.entity("minecraft:armor_stand", x + 0.5, 2.0, z + 0.5, yaw=-90.0,
             snbt=figure_snbt("Teknik Direktör", chest=ARENA_NAVY, legs=ARENA_NAVY, feet=0x111111, head="player_head"))
    xs, zs = F.xz(ta + 4, (da + db) // 2)
    w.sign(xs, 2, zs, F.tp, ["TEKNİK DİREKTÖR", "OFİSİ", "", ""], wall=False)
    # gazeteci koltuklari: sira sira, ortada koridor
    for row, t in enumerate(range(ta + 10, tb - 6, 3)):
        for d in range(da + 2, db - 1):
            if abs(d - (da + db) // 2) <= 1:
                continue
            F.set(w, t, d, 1, f"blue_wool")
            F.set(w, t, d, 2, f"quartz_stairs[facing={F.tp},half=bottom,shape=straight,waterlogged=false]") if False else None
            F.set(w, t, d, 1, f"dark_oak_stairs[facing={F.tp},half=bottom,shape=straight,waterlogged=false]")
    # kamera platformu (arka): sehpali kameralar
    F.box(w, tb - 4, tb, da + 2, db - 2, 1, 1, "smooth_stone")
    for d in range(da + 4, db - 3, 5):
        F.set(w, tb - 2, d, 2, "oak_fence")
        F.set(w, tb - 2, d, 3, f"observer[facing={F.tm},powered=false]")
    # ceviri kabinleri
    for d in (da + 1, db - 1):
        F.box(w, tb - 8, tb - 6, d, d, 1, 4, "glass")
    # --- basin calisma odasi (t -175..-104, d 56..96)
    box, doors = room(w, F, -168, -104, 56, 96, yf, h=6, floor="polished_diorite", wall="white_concrete",
                      door_d=55, door_t=-136, door_w=3, sign=["BASIN", "ÇALIŞMA ODASI", "", ""])
    for t in range(-166, -106, 4):
        for d in range(58, 95):
            F.set(w, t, d, 1, "spruce_slab[type=top,waterlogged=false]")
            if d % 2 == 0:
                F.set(w, t, d, 2, "black_stained_glass_pane")
            F.set(w, t + 1, d, 1, f"spruce_stairs[facing={F.tm},half=bottom,shape=straight,waterlogged=false]")
    F.box(w, -137, -135, 54, 54, 1, 4, 0)
    F.box(w, -103, -103, 64, 69, 1, 5, 0)
    F.set(w, -105, 60, 1, "brewing_stand")
    F.set(w, -105, 62, 1, "dispenser[facing=%s,triggered=false]" % F.tm)
    # --- karma bolge (mixed zone): soyunma -> otobus yolu, bariyerler + sponsor panolari (t -102..-66, d 44..62)
    F.box(w, -102, -66, 44, 62, 1, 6, 0)
    F.box(w, -102, -66, 44, 62, 0, 0, "polished_andesite")
    F.box(w, -102, -66, 44, 62, 7, 7, "smooth_quartz")
    F.box(w, -102, -66, 52, 52, 1, 1, "iron_bars")
    F.box(w, -102, -66, 54, 54, 1, 1, "iron_bars")
    for t in range(-100, -66, 2):
        F.set(w, t, 61, 2, "yellow_concrete" if t % 4 else "blue_concrete")
        F.set(w, t, 61, 3, "blue_concrete" if t % 4 else "yellow_concrete")
    x, z = F.xz(-84, 60)
    w.sign(x, 5, z, F.inn, ["KARMA BÖLGE", "MIXED ZONE", "", ""])
    F.box(w, -92, -80, 63, 63, 1, 5, 0)
    F.box(w, -2, 2, 70, 99, 1, 5, 0)
    F.box(w, -2, 2, 70, 99, 0, 0, "polished_andesite")
    # --- ana lobi / VIP girisi (cift kat, t -30..30, d 100..121) + resepsiyon + avize
    box, doors = room(w, F, -30, 30, 100, 120, yf, h=13, floor="polished_diorite", wall="white_concrete",
                      ceil="smooth_quartz", lights=False)
    for t in range(-30, 31):
        for d in range(100, 121):
            if (t + d) % 6 == 0:
                F.set(w, t, d, 0, "yellow_concrete")
    cr = crest(8)
    for j, row in enumerate(cr):
        for i, c in enumerate(row):
            if c:
                F.set(w, i - 8, 110 + j - 8, 0, CREST_BLOCK[c])
    F.box(w, -8, 8, 102, 102, 1, 1, "dark_oak_planks")
    F.box(w, -8, 8, 102, 102, 2, 2, "dark_oak_slab[type=bottom,waterlogged=false]")
    for t in (-18, 0, 18):
        F.box(w, t, t, 110, 110, 9, 13, "iron_chain[axis=y]")
        F.box(w, t - 1, t + 1, 109, 111, 8, 8, "gold_block")
        F.set(w, t, 110, 7, "sea_lantern")
    F.box(w, -30, 30, 121, 121, 1, 12, "glass")
    F.box(w, -4, 4, 121, FACADE + 2, 1, 6, 0)
    x, z = F.xz(0, 99)
    w.sign(x, 7, z, F.out, ["ANA GİRİŞ", "VIP LOBİ", "", ""])
    # --- kulup muzesi (t -175..-34, d 100..121): kupalar, vitrinler, tarih duvari
    box, doors = room(w, F, -168, -34, 100, 120, yf, h=9, floor="polished_blackstone", wall="blue_concrete",
                      ceil="smooth_quartz", door_d=121, door_t=-100, door_w=4, sign=["ARENA", "MÜZESİ", "2026", ""])
    for k, t in enumerate(range(-164, -38, 8)):
        F.box(w, t, t + 2, 108, 110, 1, 1, "quartz_block")
        F.set(w, t + 1, 109, 2, "gold_block" if k % 3 else "diamond_block")
        F.box(w, t, t + 2, 108, 110, 3, 3, "glass")
        F.box(w, t, t, 108, 110, 2, 2, "glass")
        F.box(w, t + 2, t + 2, 108, 110, 2, 2, "glass")
        F.set(w, t + 1, 108, 2, "glass")
        F.set(w, t + 1, 110, 2, "glass")
        x, z = F.xz(t + 1, 107)
        w.sign(x, 1, z, F.inn, [["ŞAMPİYONLUK", "TÜRKİYE KUPASI", "SÜPER KUPA", "BALKAN KUPASI"][k % 4],
                                str(1959 + k * 4), "", ""], wall=False)
        # duvarda tarihi formalar
        ex, ez = F.xz(t + 1, 119)
        w.entity("minecraft:armor_stand", ex + 0.5, 1.0, ez + 0.5, yaw=180.0,
                 snbt=figure_snbt(f"Forma {k + 1}", chest=[ARENA_YELLOW, ARENA_NAVY, 0xFFFFFF][k % 3],
                                  legs=[ARENA_NAVY, 0xFFFFFF, ARENA_NAVY][k % 3], feet=0x111111, head=None))
    # --- Fenerium magazasi (t 34..120, d 100..121)
    box, doors = room(w, F, 34, 118, 100, 120, yf, h=7, floor="polished_diorite", wall="yellow_concrete",
                      door_d=121, door_t=76, door_w=4, door="opening", sign=["ARENA STORE", "RESMİ MAĞAZA", "", ""])
    kit_room(w, box, "shop", doors, seed=1907)
    for k, t in enumerate(range(38, 116, 6)):
        ex, ez = F.xz(t, 104)
        w.entity("minecraft:armor_stand", ex + 0.5, 1.0, ez + 0.5, yaw=0.0,
                 snbt=figure_snbt(["İÇ SAHA FORMASI", "DEPLASMAN FORMASI", "3. FORMA", "KALECİ FORMASI"][k % 4],
                                  chest=[ARENA_YELLOW, 0xFFFFFF, ARENA_NAVY, 0x2F9E44][k % 4],
                                  legs=[ARENA_NAVY, 0xFFFFFF, ARENA_NAVY, 0x2F9E44][k % 4], feet=0x111111, head=None))
    # --- takim otobusu garaji (t 124..170, d 60..120), cephede arac kapisi
    box, doors = room(w, F, 124, 172, 60, 120, yf, h=9, floor="gray_concrete", wall="light_gray_concrete",
                      ceil="smooth_stone", lights=True)
    F.box(w, 140, 156, 120, FACADE + 2, 1, 8, 0)
    F.box(w, 140, 156, 121, FACADE + 2, 0, 0, "gray_concrete")
    x, z = F.xz(148, FACADE + 3)
    w.sign(x, 9, z, F.out, ["TAKIM", "OTOBÜSÜ", "GİRİŞİ", ""])
    bus(w, F, 130, 75, "ev")
    bus(w, F, 150, 75, "away")


def bus(w, F: SideFrame, t0, d0, kind):
    """16 uzun (d), 5 genis (t), 6 yuksek otobus; d boyunca."""
    body = ("yellow_concrete", "blue_concrete") if kind == "ev" else ("white_concrete", "light_gray_concrete")
    for d in range(d0, d0 + 16):
        for t in range(t0, t0 + 5):
            F.set(w, t, d, 1, "black_concrete" if d in (d0 + 2, d0 + 3, d0 + 12, d0 + 13) and t in (t0, t0 + 4) else body[1])
            F.set(w, t, d, 2, body[1])
            for y in (3, 4):
                edge = t in (t0, t0 + 4) or d in (d0, d0 + 15)
                F.set(w, t, d, y, "black_stained_glass" if edge and d not in (d0 + 15,) else body[0])
            F.set(w, t, d, 5, body[0])
    F.box(w, t0 + 1, t0 + 3, d0, d0, 3, 4, "light_blue_stained_glass")
    F.set(w, t0, d0, 2, "sea_lantern")
    F.set(w, t0 + 4, d0, 2, "sea_lantern")


# ------------------------------------------------------------------ saha kenari: yedek kulubeleri, teknik alan, 4. hakem
def pitchside(w, b: Bowl):
    F = SideFrame(0)
    for tc, home in ((40, True), (-40, False)):
        ta, tb = tc - 12, tc + 12
        d0, d1 = -9, -2                                   # B-9 .. B-2
        F.box(w, ta, tb, d0, d1, 0, 0, "black_concrete")
        seat = "bamboo_mosaic_stairs" if home else "polished_blackstone_stairs"
        for k, d in enumerate((d0 + 2, d0 + 4, d0 + 6)):
            if k:
                F.box(w, ta + 1, tb - 1, d, d, 1, k, "black_concrete")
            F.box(w, ta + 1, tb - 1, d, d, k + 1, k + 1, f"{seat}[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
        F.box(w, ta, tb, d0, d1, 5, 5, "light_gray_stained_glass")
        F.box(w, ta, ta, d0, d1, 1, 4, "glass_pane")
        F.box(w, tb, tb, d0, d1, 1, 4, "glass_pane")
        F.box(w, ta, tb, d1, d1, 1, 4, "glass_pane")
        F.box(w, ta, tb, d0 - 1, d0 - 1, 5, 5, "yellow_concrete" if home else "white_concrete")
        x, z = F.xz(tc, d0 - 1)
        w.sign(x, 4, z, F.inn, ["EV SAHİBİ" if home else "MİSAFİR", "YEDEK KULÜBESİ", "", ""])
        # teknik alan cizgisi (onunde)
        for t in range(ta - 3, tb + 4):
            F.set(w, t, -12, 0, "white_concrete")
        for d in range(-12, d0):
            F.set(w, ta - 3, d, 0, "white_concrete")
            F.set(w, tb + 3, d, 0, "white_concrete")
    # teknik direktor: ev sahibi teknik alaninda, sahaya bakar
    x, z = F.xz(40, -11)
    w.entity("minecraft:armor_stand", x + 0.5, 1.0, z + 0.5, yaw=180.0,
             snbt=figure_snbt("Teknik Direktör", chest=ARENA_NAVY, legs=ARENA_NAVY, feet=0x111111, head="player_head",
                              pose="{RightArm:[-90f,0f,0f],LeftArm:[-10f,0f,-10f]}"))
    # 4. hakem masasi + tabela
    F.box(w, -12, -9, -6, -6, 1, 1, "spruce_slab[type=top,waterlogged=false]")
    F.set(w, -11, -4, 1, f"spruce_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
    F.set(w, -10, -6, 2, "redstone_lamp[lit=false]")
    x, z = F.xz(-10, -7)
    w.sign(x, 1, z, F.inn, ["4. HAKEM", "", "", ""], wall=False)
    # ilk 11: mac oncesi dizilis (orta cizgide, Maraton'a bakar)
    lineup = [(str(n), "Oyuncu", 0x2F9E44 if n == 1 else ARENA_YELLOW, 0x2F9E44 if n == 1 else ARENA_NAVY) for n in range(1, 12)]
    for k, (num, name, ch, lg) in enumerate(lineup):
        x = -30 + k * 6
        w.entity("minecraft:armor_stand", x + 0.5, 1.0, 40 + 0.5, yaw=0.0,
                 snbt=figure_snbt(f"{num} {name}", chest=ch, legs=lg, feet=0x111111, head="player_head",
                                  pose="{RightArm:[0f,0f,10f],LeftArm:[0f,0f,-10f]}"))
    # top: orta noktada (beyaz kafa yerine kar topu yok; beyaz yun 1 blok)
    # fotografci alanlari (kale arkasi): tabure dizisi
    for sgn in (-1, 1):
        for zz in range(-60, 61, 6):
            if abs(zz) < 16:
                continue
            w.set(sgn * (PL + 6), 1, zz, "spruce_trapdoor[facing=north,half=top,open=false,powered=false,waterlogged=false]")


# ------------------------------------------------------------------ meydan ayrintilari
def plaza_details(w, b: Bowl):
    for s in (0, 1, 2, 3):
        F = SideFrame(s)
        half = SIDE_HALF[s]
        dd = FACADE + 3 + PLAZA - 6
        for t in range(-half - 20, half + 21, 20):
            # agac saksisi + agac, lamba direkleri
            F.box(w, t - 1, t + 1, dd - 1, dd + 1, 1, 1, "blue_concrete")
            F.set(w, t, dd, 1, "grass_block")
            F.box(w, t, t, dd, dd, 2, 5, "oak_log[axis=y]")
            F.box(w, t - 2, t + 2, dd - 2, dd + 2, 6, 7, "oak_leaves[distance=1,persistent=true,waterlogged=false]")
            F.box(w, t - 1, t + 1, dd - 1, dd + 1, 8, 8, "oak_leaves[distance=1,persistent=true,waterlogged=false]")
            tl = t + 10
            F.box(w, tl, tl, dd, dd, 1, 6, "iron_bars")
            F.set(w, tl, dd, 7, "sea_lantern")
            F.set(w, tl, dd - 4, 1, f"spruce_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
            F.set(w, tl + 1, dd - 4, 1, f"spruce_stairs[facing={F.out},half=bottom,shape=straight,waterlogged=false]")
            F.set(w, tl - 2, dd - 4, 1, "composter[level=0]")
    # ana meydan (ana tribun onu): bayrak direkleri, 2026 aniti, dev arma kaidesi
    F = SideFrame(0)
    for t in range(-150, 151, 20):
        if abs(t) < 30:
            continue
        x, z = F.xz(t, FACADE + 14)
        w.box(x, 1, z, x, 18, z, "iron_bars")
        w.set(x, 19, z, "gold_block")
        w.banner(x + 1 if False else x, 16, z - 1 if False else z + 1, facing="south") if False else None
        bx, bz = F.xz(t, FACADE + 15)
        w.banner(bx, 16, bz, facing="south")
    bm = text_bitmap("2026", sx=2, sy=2, accents=False)
    H, Wd = bm.shape
    for j in range(H):
        for i in range(Wd):
            if bm[j, i]:
                for dz in range(3):
                    x, z = F.xz(-Wd // 2 + i, FACADE + 22 + dz)
                    w.set(x, H - j, z, "yellow_concrete" if dz != 1 else "blue_concrete")
    F.box(w, -26, 26, FACADE + 20, FACADE + 26, 0, 0, "polished_blackstone")


# ------------------------------------------------------------------ hepsi
def build_all(w: World, b: Bowl):
    gates(w, b)
    side_modules(w, b)
    press_tribune(w, SideFrame(0))
    main_ground(w, b)
    pitchside(w, b)
    plaza_details(w, b)
    fan_banners(w)
