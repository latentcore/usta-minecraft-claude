"""Kase: tribunler (iki kat, koltuk desenleri, yazilar), merdiven koridorlari, vomitoryler, cati, cephe, saha, meydan."""
from __future__ import annotations

import math

import numpy as np

from arena_core import (A, B, BACK_D, BOX_D0, BOX_D1, BOXY, CROSS_D0, CREST_BLOCK, FACADE, GATE_CONC, LAST_SEAT_Y, LOW_CONC,
                     LOW_ROWS, PL, PLAZA, PW, ROOF0, S, UP_CONC, UP_D0, UP_DEEP, UP_ROWS, UPY0, VIP_CONC, X0, Y0, Z0, World,
                     crest, fields, text_bitmap)

SIDE_HALF = {0: A, 1: A, 2: B, 3: B}           # duz kenar yari uzunlugu (t)


def roof_y(d):
    return ROOF0 + np.floor((np.asarray(d) + 5) * 6 / (FACADE + 8)).astype(np.int32)


def low_top(d):
    return 4 + (d - 2) // 2


def up_top(d):
    return UPY0 + 2 * ((d - UP_D0) // UP_DEEP)


class Bowl:
    def __init__(self, w: World):
        self.w = w
        xs = np.arange(X0, X0 + w.sx)
        zs = np.arange(Z0, Z0 + w.sz)
        self.X, self.Z, self.d, self.side, self.t = fields(xs, zs)
        self.Di = np.floor(self.d).astype(np.int32)
        self.half = np.zeros(self.Di.shape, np.int32)
        for s, h in SIDE_HALF.items():
            self.half[self.side == s] = h

    # -------------------------------------------------------------- yardimci: kolon dizisiyle dikey doldurma
    def fill_span(self, mask, y0, y1arr, state):
        w = self.w
        i = w.id(state)
        y1arr = np.where(mask, y1arr, -999)
        top = int(y1arr.max()) if mask.any() else -999
        for y in range(y0, top + 1):
            m = mask & (y1arr >= y)
            if m.any():
                w.G[y - Y0][m] = i

    def put_layer(self, y, mask, state):
        w = self.w
        if isinstance(state, np.ndarray):
            w.G[y - Y0][mask] = state[mask]
        else:
            w.G[y - Y0][mask] = w.id(state)

    # -------------------------------------------------------------- kase govdesi
    def structure(self):
        w, D = self.w, self.Di
        mass, walk = "gray_concrete", "light_gray_concrete"
        # on duvar (saha tarafi): lacivert, ustu beyaz bant + cam korkuluk
        fw = (D >= 0) & (D < 2)
        self.fill_span(fw, 0, np.full(D.shape, 3), "blue_concrete")
        self.put_layer(4, fw, "white_concrete")
        self.put_layer(5, (D == 0), "glass_pane")
        # alt tribun
        low = (D >= 2) & (D < CROSS_D0)
        lt = np.where(low, low_top(D), -1)
        self.fill_span(low, 0, lt - 1, mass)
        for y in range(4, 4 + LOW_ROWS):
            self.put_layer(y, low & (lt == y), walk)
        # capraz koridor + loca balkonu (y=BOXY), ustunde ust tribunun alt yuzu (y>=BOXY+8)
        cross = (D >= CROSS_D0) & (D < BOX_D0)
        self.fill_span(cross, 0, np.full(D.shape, BOXY - 1), mass)
        self.put_layer(BOXY, cross, "polished_andesite")
        # ust tribunun on alni (d CROSS_D0-2..CROSS_D0-1)
        fascia = (D >= CROSS_D0 - 2) & (D < CROSS_D0)
        self.fill_span(fascia, BOXY + 8, np.full(D.shape, UPY0 - 1), "blue_concrete")
        self.put_layer(UPY0 - 2, fascia & (D == CROSS_D0 - 2), "yellow_concrete")
        self.put_layer(UPY0, fascia, "white_concrete")
        self.put_layer(UPY0 + 1, (D == CROSS_D0 - 2), "glass_pane")
        up = (D >= UP_D0) & (D < BACK_D)
        ut = np.where(up, up_top(D), -1)
        upper_mass = up & (D < BOX_D0)
        for y in range(BOXY + 8, UPY0 + 2 * UP_ROWS):
            m = upper_mass & (ut > y)
            if m.any():
                w.G[y - Y0][m] = w.id(mass)
        deep = (D >= BOX_D0) & (D < BACK_D)
        self.fill_span(deep, 0, ut - 1, mass)
        for y in range(UPY0, UPY0 + 2 * UP_ROWS):
            self.put_layer(y, up & (ut == y), walk)
        # arka duvar
        back = (D >= BACK_D) & (D < FACADE)
        self.fill_span(back, 0, np.full(D.shape, LAST_SEAT_Y + 1), mass)
        self.put_layer(LAST_SEAT_Y + 2, back, "white_concrete")
        self.lt, self.ut = lt, ut

    # -------------------------------------------------------------- koltuklar (desen + yazilar) ve merdiven koridorlari
    def seats(self):
        w, D, S, T = self.w, self.Di, self.side, self.t
        Y, N, GR = w.id("yellow_concrete"), w.id("blue_concrete"), w.id("light_gray_concrete")
        half = self.half
        on_side = (S >= 0) & (np.abs(T) <= half - 2)
        aisle = on_side & ((np.mod(T, 30) == 0) | (np.mod(T, 30) == 1)) & (np.abs(T) <= half - 10)
        self.aisle = aisle
        low = (D >= 2) & (D < CROSS_D0)
        up = (D >= UP_D0) & (D < BACK_D)
        r = np.where(low, (D - 2) // 2, -1)
        u = np.where(up, (D - UP_D0) // UP_DEEP, -1)
        low_seat = low & (((D - 2) % 2) == 1) & ~aisle
        up_seat = up & (((D - UP_D0) % UP_DEEP) == UP_DEEP - 1) & ~aisle
        col_low = np.full(D.shape, Y, np.uint16)
        col_up = np.full(D.shape, N, np.uint16)
        ends = (S == 2) | (S == 3)
        stripe = (np.mod(T // 6, 2) == 0)
        col_low[ends & ~stripe] = N           # kale arkalari: cubuklu (sari-lacivert dikey seritler)
        col_up[ends & stripe] = Y
        col_low[S == 4] = N                   # koseler lacivert
        col_up[S == 4] = N

        def stamp(side, tier, rowidx, txt, sx, sy, row_top, fg, mirror=False, bg=None, arr=None):
            bm = text_bitmap(txt, sx=sx, sy=sy, accents=True)
            H, Wd = bm.shape
            m = (S == side) & tier
            tt = (-T if mirror else T) + Wd // 2
            rr = row_top - rowidx           # metin satiri (ust = 0) -> sira
            ok = m & (tt >= 0) & (tt < Wd) & (rr >= 0) & (rr < H)
            idx = np.nonzero(ok)
            hit = bm[rr[idx], tt[idx]]
            if bg is not None:
                arr[idx] = bg
            arr[tuple(a[hit] for a in idx)] = fg

        # Acik tribun (kuzey): alt kat USTA ARENA (lacivert harf, sari zemin), ust kat 2026 (sari, lacivert zemin)
        stamp(1, low, r, "USTA ARENA", 3, 2, 23, N, arr=col_low)
        stamp(1, up, u, "2026", 6, 4, 36, Y, arr=col_up)
        # Ana tribun (guney): ust katta USTA X CLAUDE (sari), sahadan bakana okunur
        stamp(0, up, u, "USTA X CLAUDE", 3, 3, 31, Y, mirror=True, arr=col_up)
        # dogu kale arkasi: taraftar tribunu
        stamp(2, low, r, "USTA", 6, 2, 22, N, bg=Y, arr=col_low)
        # bati ust tribun guney yarisi: misafir tribunu (gri), sinirda demir parmaklik
        away = (S == 3) & up & (T >= 50)
        col_up[away] = GR
        self.away = away
        lt, ut = self.lt, self.ut
        for y in range(5, 5 + LOW_ROWS):
            m = low_seat & (lt + 1 == y)
            if m.any():
                w.G[y - Y0][m] = col_low[m]
        for y in range(UPY0 + 1, UPY0 + 1 + 2 * UP_ROWS, 2):
            m = up_seat & (ut + 1 == y)
            if m.any():
                w.G[y - Y0][m] = col_up[m]
        # merdiven koridorlari: alt tribunde arka hucrede, ust tribunde orta + arka hucrede yarim basamaklar
        for s, face in ((0, "south"), (1, "north"), (2, "east"), (3, "west")):
            st = w.id(f"polished_andesite_stairs[facing={face},half=bottom,shape=straight,waterlogged=false]")
            m1 = aisle & (S == s) & low & (((D - 2) % 2) == 1)
            for y in range(5, 5 + LOW_ROWS):
                mm = m1 & (lt + 1 == y)
                if mm.any():
                    w.G[y - Y0][mm] = st
            m2 = aisle & (S == s) & up & (((D - UP_D0) % UP_DEEP) == UP_DEEP - 1)
            for y in range(UPY0 + 1, UPY0 + 1 + 2 * UP_ROWS, 2):
                mm = m2 & (ut + 1 == y)
                if mm.any():
                    w.G[y - Y0][mm] = st
        # misafir siniri
        fence = (S == 3) & up & (T >= 48) & (T < 50)
        for k in range(1, 4):
            for y in range(UPY0, UPY0 + 2 * UP_ROWS + 1):
                mm = fence & (ut == y)
                if mm.any():
                    w.G[y + k - Y0][mm] = w.id("iron_bars")
        self.low_seat, self.up_seat = low_seat, up_seat
        n = int(np.count_nonzero(low_seat)) + int(np.count_nonzero(up_seat))
        w.notes.append(f"koltuk: {n}")
        self.seat_count = n

    # -------------------------------------------------------------- konkurlar ve vomitoryler
    def concourses(self):
        w, D, S, T = self.w, self.Di, self.side, self.t
        on_side = (S >= 0) & (np.abs(T) <= self.half - 12)
        floor, wall, ceil = w.id("polished_andesite"), w.id("white_concrete"), w.id("smooth_quartz")
        lamp = w.id("sea_lantern")

        def ring_corr(d0, d1, yf, h=6):
            m = (D >= d0) & (D < d1) & (S != -1)
            w.G[yf - Y0][m] = floor
            for y in range(yf + 1, yf + h + 1):
                w.G[y - Y0][m] = 0
            w.G[yf + h + 1 - Y0][m] = ceil
            edge = ((D == d0 - 1) | (D == d1)) & (S != -1)
            for y in range(yf + 1, yf + h + 1):
                w.G[y - Y0][edge] = wall
            w.G[yf + 1 - Y0][edge] = w.id("blue_concrete")
            w.G[yf + 4 - Y0][edge] = w.id("yellow_concrete")
            lm = m & (D == (d0 + d1) // 2) & (np.mod(T, 6) == 0)
            w.G[yf + h + 1 - Y0][lm] = lamp
            return m

        self.c_low = ring_corr(*LOW_CONC)
        self.c_up = ring_corr(*UP_CONC)
        self.c_vip = ring_corr(*VIP_CONC)
        self.c_gate = ring_corr(*GATE_CONC)
        lt, ut = self.lt, self.ut
        yl, yu = LOW_CONC[2], UP_CONC[2]
        d_exit_l = 2 + 2 * (yl - 4)                 # alt tribunde yuruyus y=yl olan sira
        d_exit_u = UP_D0 + UP_DEEP * ((yu - UPY0) // 2)
        d_open_l = 2 + 2 * (yl + 8 - 4)             # tavan ustu en az 1 blok kalinca kapali tunel
        d_open_u = UP_D0 + UP_DEEP * ((yu + 8 - UPY0 + 1) // 2)
        vl = on_side & (np.mod(T, 60) >= 12) & (np.mod(T, 60) < 18) & (D >= d_exit_l) & (D < LOW_CONC[0])
        vu = on_side & (np.mod(T, 60) >= 42) & (np.mod(T, 60) < 48) & (D >= d_exit_u) & (D < UP_CONC[0])
        vl &= ~((S == 0) & (np.abs(T) < 24))
        vu &= ~((S == 0) & (np.abs(T) < 72))
        for (vm, yf, top, d_open) in ((vl, yl, lt, d_open_l), (vu, yu, ut, d_open_u)):
            if not vm.any():
                continue
            w.G[yf - Y0][vm] = floor
            ymax = int(np.max(np.where(vm, top + 2, 0)))
            for y in range(yf + 1, ymax + 1):
                w.G[y - Y0][vm & (D < d_open)] = 0
                if y <= yf + 6:
                    w.G[y - Y0][vm & (D >= d_open)] = 0
            w.G[yf + 7 - Y0][vm & (D >= d_open)] = ceil
            self._trench_rails(vm, top, yf, d_open)
        self.vl, self.vu = vl, vu

    def _trench_rails(self, vm, top, yf, d_open):
        w = self.w
        pane = w.id("glass_pane")
        edge = np.zeros(vm.shape, bool)
        for ax in (0, 1):
            for sh in (-1, 1):
                edge |= np.roll(vm, sh, axis=ax)
        edge &= ~vm & (self.Di < d_open) & (top > yf)
        if not edge.any():
            return
        for y in range(yf + 1, int(np.max(np.where(edge, top + 2, 0))) + 1):
            m = edge & (top + 1 == y)
            if m.any():
                w.G[y + 1 - Y0][m] = pane

    # -------------------------------------------------------------- cati: celik uzay kafes + yari saydam membran
    def roof(self):
        w, D, S, T = self.w, self.Di, self.side, self.t
        cov = (D >= -5) & (D < FACADE + 3)
        ry = roof_y(D)
        memb, purlin, steel, bars = (w.id("white_stained_glass"), w.id("light_gray_concrete"), w.id("iron_block"),
                                     w.id("iron_bars"))
        lamp = w.id("pearlescent_froglight")
        X, Z = self.X, self.Z
        for y in np.unique(ry[cov]):
            m = cov & (ry == y)
            w.G[y - Y0][m] = memb
            # alt kafes izgarasi (6 blokta bir, iki yonde), aradaki dikmeler ve aydinlatma
            grid = m & ((np.mod(X, 6) == 0) | (np.mod(Z, 6) == 0)) & (D >= -3)
            w.G[y - 5 - Y0][grid] = steel
            node = m & (np.mod(X, 6) == 0) & (np.mod(Z, 6) == 0) & (D >= -3)
            for k in range(1, 5):
                w.G[y - k - Y0][node] = bars
            pm = m & (np.mod(D, 12) == 3)
            w.G[y - 1 - Y0][pm] = purlin
            lm = node & (np.mod(X, 12) == 0) & (np.mod(Z, 12) == 0) & (D > 0) & (D < FACADE)
            w.G[y - 6 - Y0][lm] = lamp
        # on kenar alinligi: lacivert bant + sari serit, altinda projektor dizisi
        front = (D >= -5) & (D <= -3)
        fy0 = ROOF0 - 8
        for y in range(fy0, ROOF0 + 1):
            w.G[y - Y0][front & (ry >= y)] = w.id("blue_concrete")
        w.G[fy0 + 3 - Y0][front & (D == -5)] = w.id("yellow_concrete")
        w.G[fy0 + 4 - Y0][front & (D == -5)] = w.id("yellow_concrete")
        w.G[fy0 - 1 - Y0][(D == -4) & (np.mod(T, 2) == 0)] = w.id("sea_lantern")
        w.G[fy0 - 2 - Y0][(D == -4) & (np.mod(T, 4) == 0)] = w.id("sea_lantern")
        # cati ustu ana kafes kirisler: kenarlarda her 24 blokta, kosede capraz; arkadan one alcalan kemer
        half = self.half
        girder = (S >= 0) & (np.mod(T, 24) == 12) & (np.abs(T) <= half) & cov
        corner = (S == 4) & cov
        ax_ = np.abs(X) - A
        az_ = np.abs(Z) - B
        ang = np.degrees(np.arctan2(az_, ax_))
        for a0 in (18.0, 36.0, 54.0, 72.0):
            girder |= corner & (np.abs(ang - a0) < 0.25 + 18.0 / np.maximum(self.d, 1))
        rib = girder & (D >= 20)
        hrib = ry + 1 + ((D - 20) * 16 // (FACADE - 20)).clip(0, 16)
        for yy in np.unique(hrib[rib]):
            w.G[yy - Y0][rib & (hrib == yy)] = steel
        for k in range(1, 17):
            m = rib & (np.mod(D, 8) == 0) & (ry + k < hrib)
            if m.any():
                yy_arr = ry + k
                for yy in np.unique(yy_arr[m]):
                    w.G[yy - Y0][m & (yy_arr == yy)] = bars
        # makas alt kirisleri (catinin altinda, gorunur): girder hattinda 7 derin ucgen kafes
        for k in range(1, 8):
            y = ry - k
            chord = girder & (k == 7)
            diag = girder & (np.mod(D + k, 7) == 0)
            for yy in np.unique(y[girder]):
                w.G[yy - Y0][chord & (y == yy)] = steel
                w.G[yy - Y0][diag & (y == yy) & (k < 7)] = steel
        self.ry = ry

    # -------------------------------------------------------------- dev ekranlar (kale arkalari, cati altinda)
    def screens(self):
        w = self.w
        top = ROOF0 - 10
        for sgn in (1, -1):
            x = sgn * (A - 2)
            z0, z1 = -40, 40
            y0, y1 = top - 34, top - 2
            w.box(x, y0 - 1, z0 - 1, x + sgn, y1 + 1, z1 + 1, "black_concrete")
            w.box(x - sgn, y0, z0, x - sgn, y1, z1, "black_stained_glass")
            cr = crest(14)                      # sahadan bakana sag: dogu ekraninda +z, bati ekraninda -z
            for j, row in enumerate(cr):
                for i, c in enumerate(row):
                    if c:
                        zz = (z0 + 2 + i) if sgn > 0 else (z1 - 2 - i)
                        w.set(x - sgn, y1 - 2 - j, zz, CREST_BLOCK[c])
            bm = text_bitmap("USTA", sx=2, sy=2, accents=False)
            H, Wd = bm.shape
            for j in range(H):
                for i in range(Wd):
                    if bm[j, i]:
                        zz = (z0 + 36 + i) if sgn > 0 else (z1 - 36 - i)
                        w.set(x - sgn, y1 - 6 - j, zz, "yellow_concrete")
            bm = text_bitmap("ARENA", sx=1, sy=1, accents=True)
            H, Wd = bm.shape
            for j in range(H):
                for i in range(Wd):
                    if bm[j, i]:
                        zz = (z0 + 30 + i) if sgn > 0 else (z1 - 30 - i)
                        w.set(x - sgn, y0 + 12 - j, zz, "white_concrete")
            for zz in (z0 + 6, z1 - 6):
                w.box(x, y1 + 2, zz, x, ROOF0 - 9, zz, "iron_chain[axis=y]")

    # -------------------------------------------------------------- dis cephe
    def facade(self):
        w, D, S, T = self.w, self.Di, self.side, self.t
        f = (D >= FACADE) & (D < FACADE + 3)
        ry = roof_y(D)
        top = np.where(f, ry - 1, -1)
        self.fill_span(f & (D == FACADE), 0, top, "light_gray_concrete")
        cw = f & (D == FACADE + 1)
        fin = cw & (np.mod(T, 6) == 0)
        glass = cw & ~fin
        for y in range(0, int(top.max()) + 1):
            if y % 8 == 0:
                w.G[y - Y0][cw & (top >= y)] = w.id("blue_concrete")
                if y % 16 == 0 and y > 0:
                    w.G[y - Y0][cw & (top >= y) & (np.mod(T, 3) == 1)] = w.id("sea_lantern")
            else:
                w.G[y - Y0][fin & (top >= y)] = w.id("blue_concrete")
                w.G[y - Y0][glass & (top >= y)] = w.id("light_blue_stained_glass")
        of = f & (D == FACADE + 2) & (np.mod(T, 12) == 6)
        self.fill_span(of, 1, top - 2, "yellow_concrete")
        crown_y = int(ROOF0) - 32
        crown = f & (D == FACADE + 2)
        for y in range(crown_y, int(top.max()) + 1):
            w.G[y - Y0][crown & (top >= y)] = w.id("blue_concrete")
        w.G[crown_y - 1 - Y0][crown] = w.id("yellow_concrete")
        w.G[crown_y - 2 - Y0][crown] = w.id("yellow_concrete")
        self.crown_y = crown_y
        self.facade_top = top

    @staticmethod
    def outside_point(side, u, d):
        """Disaridan cepheye bakan izleyicinin sagina dogru u (merkezden) ve d uzakliginda yerel (x, z)."""
        if side == 0:
            return u, B + d
        if side == 1:
            return -u, -(B + d)
        if side == 2:
            return A + d, -u
        return -(A + d), u

    def facade_text(self, side, text, sx, sy, ytop, block="ochre_froglight", u_center=0, d=FACADE + 3):
        w = self.w
        bm = text_bitmap(text, sx=sx, sy=sy, accents=True)
        H, Wd = bm.shape
        for j in range(H):
            for i in range(Wd):
                if bm[j, i]:
                    x, z = self.outside_point(side, u_center - Wd // 2 + i, d)
                    w.set(x, ytop - j, z, block)

    def facade_crest(self, side, R, yc, u_center=0):
        w = self.w
        cr = crest(R)
        for j, row in enumerate(cr):
            for i, c in enumerate(row):
                if c:
                    x, z = self.outside_point(side, u_center + i - R, FACADE + 2)
                    w.set(x, yc + R - j, z, CREST_BLOCK[c])
                    x2, z2 = self.outside_point(side, u_center + i - R, FACADE + 3)
                    if c == "blue":
                        w.set(x2, yc + R - j, z2, "blue_concrete")

    # -------------------------------------------------------------- saha
    def pitch(self):
        w = self.w
        X, Z, D = self.X, self.Z, self.Di
        inside = D < 0
        grass, moss = w.id("grass_block[snowy=false]"), w.id("moss_block")
        stripe = (np.mod((X + PL) // 16, 2) == 0)
        lay = np.where(stripe, grass, moss).astype(np.uint16)
        w.G[0 - Y0][inside] = lay[inside]
        outer = inside & ((np.abs(X) > PL + 6) | (np.abs(Z) > PW + 6))
        w.G[0 - Y0][outer] = w.id("green_concrete")
        road = inside & ((np.abs(X) >= A - 4) | (np.abs(Z) >= B - 4))
        w.G[0 - Y0][road] = w.id("gray_concrete")
        line = w.id("white_concrete")
        k = S                                                     # 1 m = S blok

        def L(x0, z0, x1, z1):
            w.box(x0, 0, z0, x1, 0, z1, line)
        L(-PL, -PW, PL, -PW)
        L(-PL, PW, PL, PW)
        L(-PL, -PW, -PL, PW)
        L(PL, -PW, PL, PW)
        L(0, -PW, 0, PW)
        rc = 9.15 * k
        for a in np.linspace(0, 2 * math.pi, 1400):
            w.set(int(round(rc * math.cos(a))), 0, int(round(rc * math.sin(a))), line)
        w.box(-1, 0, -1, 1, 0, 1, line)
        pa_d, pa_w = int(16.5 * k), int(20.16 * k)
        ga_d, ga_w = int(5.5 * k), int(9.16 * k)
        for sgn in (-1, 1):
            gx = sgn * PL
            L(gx - sgn * pa_d, -pa_w, gx - sgn * pa_d, pa_w)
            L(gx, -pa_w, gx - sgn * pa_d, -pa_w)
            L(gx, pa_w, gx - sgn * pa_d, pa_w)
            L(gx - sgn * ga_d, -ga_w, gx - sgn * ga_d, ga_w)
            L(gx, -ga_w, gx - sgn * ga_d, -ga_w)
            L(gx, ga_w, gx - sgn * ga_d, ga_w)
            px = gx - sgn * 11 * k
            w.box(px - 1, 0, -1, px + 1, 0, 1, line)
            for a in np.linspace(-math.pi / 2, math.pi / 2, 600):
                xx = px - sgn * rc * math.cos(a)
                zz = rc * math.sin(a)
                if abs(xx - gx) > pa_d:
                    w.set(int(round(xx)), 0, int(round(zz)), line)
            for zs in (-1, 1):
                cz = zs * PW
                for a in np.linspace(0, math.pi / 2, 40):
                    w.set(int(round(gx - sgn * k * math.cos(a))), 0, int(round(cz - zs * k * math.sin(a))), line)
                w.set(gx, 1, cz, "yellow_concrete")
                w.box(gx, 2, cz, gx, 5, cz, "yellow_stained_glass_pane")
                w.banner(gx, 6, cz, wall=False, base="yellow", rotation=4 if sgn < 0 else 12,
                         patterns=(("stripe_left", "blue"), ("stripe_center", "blue"), ("stripe_right", "blue")))
            # kale: 7.32 x 2.44 x 2 m -> 29 x 10 x 8 (direkler beyaz beton, ag beyaz cam panel)
            zl, zr = -11, 11
            for zz in (zl, zr):
                w.box(gx, 1, zz, gx, 7, zz, "white_concrete")
            w.box(gx, 8, zl, gx, 8, zr, "white_concrete")
            back = gx + sgn * 6
            w.box(back, 1, zl, back, 6, zr, "white_stained_glass_pane")
            for zz in (zl, zr):
                w.box(gx + sgn, 1, zz, back, 6, zz, "white_stained_glass_pane")
            w.box(gx + sgn, 7, zl, back, 7, zr, "white_stained_glass_pane")
            w.box(gx + sgn, 0, zl, back, 0, zr, "white_concrete")
        # reklam panolari (LED): 2 yuksek, renkli yuz + siyah ust; Maraton onu aciktir (yedek kulubeleri)
        boards = [("z", -(PW + 8), -(PL + 10), PL + 10), ("z", PW + 8, -(PL + 10), PL + 10),
                  ("x", -(PL + 10), -(PW + 8), PW + 8), ("x", PL + 10, -(PW + 8), PW + 8)]
        colors = ["yellow_concrete", "blue_concrete", "white_concrete", "light_blue_concrete", "lime_concrete", "orange_concrete"]
        for kind, c, a0, a1 in boards:
            for a in range(a0, a1 + 1):
                col = colors[((a - a0) // 24) % len(colors)]
                if kind == "z":
                    if abs(a) <= 74 and c > 0:
                        continue
                    pos = [(a, c)]
                else:
                    if abs(a) <= 14:
                        continue
                    pos = [(c, a)]
                for (xx, zz) in pos:
                    w.set(xx, 1, zz, col)
                    w.set(xx, 2, zz, col)
                    w.set(xx, 3, zz, "black_concrete")

    # -------------------------------------------------------------- meydan
    def plaza(self):
        w, D, X, Z = self.w, self.Di, self.X, self.Z
        pl = (D >= FACADE + 3) & (D < FACADE + 3 + PLAZA)
        grid = (np.mod(X, 8) == 0) | (np.mod(Z, 8) == 0)
        a, b2 = w.id("polished_andesite"), w.id("smooth_stone")
        lay = np.where(grid, a, b2).astype(np.uint16)
        w.G[0 - Y0][pl] = lay[pl]
        edge = (D >= FACADE + 3) & (D < FACADE + 5)
        w.G[0 - Y0][edge] = w.id("yellow_concrete")
        rim = (D >= FACADE + 3 + PLAZA - 2) & (D < FACADE + 3 + PLAZA)
        w.G[0 - Y0][rim] = w.id("blue_concrete")
        self.plaza_mask = pl
