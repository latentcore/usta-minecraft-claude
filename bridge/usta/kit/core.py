"""Build: yerel cercevede seyrek voksel yapi (yapi ustasi arac setinin temeli).

Yerel cerceve:
  * y yukari; z derinlik: on cephe z=0'da ve -z yonune (yerel "kuzey") bakar, yapi +z'ye dogru uzanir;
  * x: yapinin KENDI sagi (kapidan disari bakarken sag). Cepheye bakan izleyici icin +x soldadir.
  * to_plan(world_origin, facing): yerel (0,0,0) dunyada world_origin'e gelir, on cephe dunyada `facing` yonune bakar.
Hucreler 16^3 parcalarda numpy dizileriyle tutulur; buyuk hacim islemleri dilimlerle yapilir (blok blok dongu yok).
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

from .. import blockdb
from ..plan import AIR, KEEP, Plan

CH = 16
FACINGS = ("north", "east", "south", "west")


def _rot_xz(x, z, times: int):
    """Saat yonunde (yukaridan bakinca) 90 derece * times: (x, z) -> (-z, x)."""
    for _ in range(times % 4):
        x, z = -z, x
    return x, z


class Build:
    def __init__(self, name: str = "yapı", db: blockdb.BlockDB | None = None):
        self.db = db or blockdb.get()
        self.name = name
        self.palette: list[str] = [KEEP, AIR]
        self._pid: dict[str, int] = {KEEP: 0, AIR: 1}
        self._raw: dict[str, int] = {KEEP: 0, "air": 1, AIR: 1}
        self.chunks: dict[tuple[int, int, int], np.ndarray] = {}
        self.block_entities: dict[tuple[int, int, int], str] = {}
        self.entities: list[dict] = []
        self.meta: dict = {"rooms": [], "floors": [], "doors": [], "windows": [], "lights": [], "notes": []}

    # ------------------------------------------------------------------ palet
    def pid(self, state) -> int:
        """Durum dizgisini palet indeksine cevirir (dogrular, eksik ozellikleri varsayilanla doldurur).
        '!' oneki: oyun baglanti/sekil duzeltmesi yapmasin (tam durum)."""
        if isinstance(state, (int, np.integer)):
            return int(state)
        i = self._raw.get(state)
        if i is not None:
            return i
        exact = state.startswith("!")
        c = self.db.canonical(state[1:] if exact else state)
        key = ("!" + c) if exact else c
        i = self._pid.get(key)
        if i is None:
            i = len(self.palette)
            self.palette.append(key)
            self._pid[key] = i
        self._raw[state] = i
        return i

    def state_of(self, pid: int) -> str:
        return self.palette[pid]

    # ------------------------------------------------------------------ hucre erisimi
    def _chunk(self, cx: int, cy: int, cz: int, create: bool = True) -> np.ndarray | None:
        k = (cx, cy, cz)
        c = self.chunks.get(k)
        if c is None and create:
            c = np.zeros((CH, CH, CH), dtype=np.int32)
            self.chunks[k] = c
        return c

    def set(self, x: int, y: int, z: int, state) -> None:
        p = self.pid(state)
        c = self._chunk(x >> 4, y >> 4, z >> 4)
        c[y & 15, z & 15, x & 15] = p

    def get(self, x: int, y: int, z: int) -> str:
        c = self._chunk(x >> 4, y >> 4, z >> 4, create=False)
        if c is None:
            return KEEP
        return self.palette[int(c[y & 15, z & 15, x & 15])]

    def get_id(self, x: int, y: int, z: int) -> int:
        c = self._chunk(x >> 4, y >> 4, z >> 4, create=False)
        return 0 if c is None else int(c[y & 15, z & 15, x & 15])

    def is_set(self, x: int, y: int, z: int) -> bool:
        return self.get_id(x, y, z) != 0

    def is_solid(self, x: int, y: int, z: int) -> bool:
        i = self.get_id(x, y, z)
        if i <= 1:
            return False
        return bool(self.db.flags_of(self.palette[i].lstrip("!")) & blockdb.FULL)

    @staticmethod
    def _norm(x0, y0, z0, x1, y1, z1):
        return min(x0, x1), min(y0, y1), min(z0, z1), max(x0, x1), max(y0, y1), max(z0, z1)

    def _apply_box(self, x0, y0, z0, x1, y1, z1, fn) -> None:
        """fn(chunk_array, slice_y, slice_z, slice_x, (gy0,gz0,gx0)) her kesisen parca icin."""
        x0, y0, z0, x1, y1, z1 = self._norm(x0, y0, z0, x1, y1, z1)
        for cy in range(y0 >> 4, (y1 >> 4) + 1):
            for cz in range(z0 >> 4, (z1 >> 4) + 1):
                for cx in range(x0 >> 4, (x1 >> 4) + 1):
                    ax, bx = max(x0, cx * CH), min(x1, cx * CH + 15)
                    ay, by = max(y0, cy * CH), min(y1, cy * CH + 15)
                    az, bz = max(z0, cz * CH), min(z1, cz * CH + 15)
                    c = self._chunk(cx, cy, cz)
                    fn(c, slice(ay - cy * CH, by - cy * CH + 1), slice(az - cz * CH, bz - cz * CH + 1),
                       slice(ax - cx * CH, bx - cx * CH + 1), (ay, az, ax))

    def fill(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, state, *, hollow: bool = False,
             replace: str | Iterable[str] | None = None, only_empty: bool = False) -> None:
        """Kutuyu doldurur (uclar dahil). hollow: yalniz kabuk. replace: yalniz bu durum(lar)in yerine.
        only_empty: yalniz bos hucrelere (keep ya da hava: clear_volume'un yazdigi hava da bos sayilir)."""
        p = self.pid(state)
        if hollow:
            x0, y0, z0, x1, y1, z1 = self._norm(x0, y0, z0, x1, y1, z1)
            for a in ((x0, y0, z0, x1, y0, z1), (x0, y1, z0, x1, y1, z1), (x0, y0, z0, x0, y1, z1),
                      (x1, y0, z0, x1, y1, z1), (x0, y0, z0, x1, y1, z0), (x0, y0, z1, x1, y1, z1)):
                self.fill(*a, state, replace=replace, only_empty=only_empty)
            return
        rep = None
        if replace is not None:
            rep = np.array([self.pid(r) for r in ([replace] if isinstance(replace, str) else replace)], dtype=np.int32)

        def fn(c, sy, sz, sx, _o):
            if rep is None and not only_empty:
                c[sy, sz, sx] = p
            else:
                v = c[sy, sz, sx]
                m = np.ones(v.shape, dtype=bool)
                if rep is not None:
                    m &= np.isin(v, rep)
                if only_empty:
                    m &= v <= 1
                v[m] = p
        self._apply_box(x0, y0, z0, x1, y1, z1, fn)

    def clear(self, x0, y0, z0, x1, y1, z1) -> None:
        """Kutuyu havaya cevirir (dunyada da bosaltilir)."""
        self.fill(x0, y0, z0, x1, y1, z1, AIR)

    def forget(self, x0, y0, z0, x1, y1, z1) -> None:
        """Kutudaki hucreleri plandan cikarir (dunyaya dokunulmaz)."""
        self.fill(x0, y0, z0, x1, y1, z1, KEEP)

    def put_mask(self, x0: int, y0: int, z0: int, mask: np.ndarray, state, only_empty: bool = False) -> None:
        """mask[y, z, x] True olan hucrelere durum yazar; mask'in (0,0,0)'i (x0,y0,z0)'a gelir."""
        p = self.pid(state)
        sy, sz, sx = mask.shape

        def fn(c, ys, zs, xs, o):
            gy, gz, gx = o
            m = mask[gy - y0: gy - y0 + (ys.stop - ys.start), gz - z0: gz - z0 + (zs.stop - zs.start),
                     gx - x0: gx - x0 + (xs.stop - xs.start)]
            v = c[ys, zs, xs]
            if only_empty:
                m = m & (v <= 1)
            v[m] = p
        if sx and sy and sz:
            self._apply_box(x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1, fn)

    def put_ids(self, x0: int, y0: int, z0: int, ids: np.ndarray, palette: list[str] | None = None) -> None:
        """Yogun dizi yazar: ids[y,z,x]; 0 (keep) atlanir. palette verilirse ids o palete goredir."""
        if palette is not None:
            remap = np.array([0 if s == KEEP else self.pid(s) for s in palette], dtype=np.int32)
            ids = remap[ids]
        sy, sz, sx = ids.shape

        def fn(c, ys, zs, xs, o):
            gy, gz, gx = o
            sub = ids[gy - y0: gy - y0 + (ys.stop - ys.start), gz - z0: gz - z0 + (zs.stop - zs.start),
                      gx - x0: gx - x0 + (xs.stop - xs.start)]
            v = c[ys, zs, xs]
            m = sub != 0
            v[m] = sub[m]
        if sx and sy and sz:
            self._apply_box(x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1, fn)

    def line(self, p0: tuple[int, int, int], p1: tuple[int, int, int], state) -> None:
        """3B Bresenham dogrusu."""
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        n = max(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
        if n == 0:
            self.set(x0, y0, z0, state)
            return
        for t in range(n + 1):
            f = t / n
            self.set(round(x0 + (x1 - x0) * f), round(y0 + (y1 - y0) * f), round(z0 + (z1 - z0) * f), state)

    # ------------------------------------------------------------------ blok varliklari / varliklar
    def set_block_entity(self, x: int, y: int, z: int, snbt: str) -> None:
        self.block_entities[(x, y, z)] = snbt

    def add_entity(self, etype: str, x: float, y: float, z: float, yaw: float = 0.0, pitch: float = 0.0, snbt: str = "{}") -> None:
        self.entities.append({"type": etype, "pos": [x, y, z], "yaw": yaw, "pitch": pitch, "snbt": snbt})

    # ------------------------------------------------------------------ olcu / ozet
    def bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
        mins = [None, None, None]
        maxs = [None, None, None]
        for (cx, cy, cz), c in self.chunks.items():
            nz = np.nonzero(c)
            if len(nz[0]) == 0:
                continue
            ys, zs, xs = nz
            lo = (cx * CH + int(xs.min()), cy * CH + int(ys.min()), cz * CH + int(zs.min()))
            hi = (cx * CH + int(xs.max()), cy * CH + int(ys.max()), cz * CH + int(zs.max()))
            for i in range(3):
                mins[i] = lo[i] if mins[i] is None else min(mins[i], lo[i])
                maxs[i] = hi[i] if maxs[i] is None else max(maxs[i], hi[i])
        if mins[0] is None:
            return None
        return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])

    def size(self) -> tuple[int, int, int]:
        b = self.bounds()
        if b is None:
            return (0, 0, 0)
        (a, b_, c), (d, e, f) = b
        return (d - a + 1, e - b_ + 1, f - c + 1)

    def dense(self) -> tuple[tuple[int, int, int], np.ndarray]:
        """(en kucuk kose, ids[y,z,x])"""
        b = self.bounds()
        if b is None:
            return (0, 0, 0), np.zeros((1, 1, 1), dtype=np.int32)
        (x0, y0, z0), (x1, y1, z1) = b
        out = np.zeros((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), dtype=np.int32)
        for (cx, cy, cz), c in self.chunks.items():
            ox, oy, oz = cx * CH - x0, cy * CH - y0, cz * CH - z0
            ay, az, ax = max(0, oy), max(0, oz), max(0, ox)
            by, bz, bx = min(out.shape[0], oy + CH), min(out.shape[1], oz + CH), min(out.shape[2], ox + CH)
            if ay >= by or az >= bz or ax >= bx:
                continue
            sub = c[ay - oy:by - oy, az - oz:bz - oz, ax - ox:bx - ox]
            dst = out[ay:by, az:bz, ax:bx]
            m = sub != 0
            dst[m] = sub[m]
        return (x0, y0, z0), out

    def count(self, solid_only: bool = False) -> int:
        n = 0
        for c in self.chunks.values():
            n += int(np.count_nonzero(c > 1)) if solid_only else int(np.count_nonzero(c))
        return n

    def histogram(self) -> dict[str, int]:
        tot: dict[int, int] = {}
        for c in self.chunks.values():
            ids, cnt = np.unique(c, return_counts=True)
            for i, k in zip(ids.tolist(), cnt.tolist()):
                if i:
                    tot[i] = tot.get(i, 0) + k
        return {self.palette[i]: k for i, k in sorted(tot.items(), key=lambda t: -t[1])}

    # ------------------------------------------------------------------ birlestirme / donusum
    def merge(self, other: "Build", dx: int = 0, dy: int = 0, dz: int = 0, rotate: int = 0, mirror_x: bool = False,
              only_empty: bool = False) -> None:
        """Baska bir yapiyi (istege bagli dondurup/aynalayip) (dx,dy,dz) kaydirmasiyla bu yapiya ekler."""
        src = other.transformed(rotate, mirror_x) if (rotate % 4 or mirror_x) else other
        (ox, oy, oz), ids = src.dense()
        remap = np.array([0 if s == KEEP else self.pid(s) for s in src.palette], dtype=np.int32)
        mapped = remap[ids]
        if only_empty:
            # mevcut dolu hucreleri koru (hava/keep bos sayilir)
            sy, sz, sx = mapped.shape          # (y, z, x)
            cur = self.ids_box(ox + dx, oy + dy, oz + dz, ox + dx + sx - 1, oy + dy + sy - 1, oz + dz + sz - 1)
            mapped = np.where(cur > 1, 0, mapped)
        self.put_ids(ox + dx, oy + dy, oz + dz, mapped)
        for (x, y, z), snbt in src.block_entities.items():
            self.block_entities[(x + dx, y + dy, z + dz)] = snbt
        for e in src.entities:
            e2 = dict(e)
            e2["pos"] = [e["pos"][0] + dx, e["pos"][1] + dy, e["pos"][2] + dz]
            self.entities.append(e2)
        for k in ("rooms", "doors", "windows", "lights", "decor_doors", "stair_air", "stair_cells"):
            for r in src.meta.get(k, []) or []:      # src: transformed() meta'yi de dondurur
                if isinstance(r, (list, tuple)) and len(r) >= 3:
                    self.meta.setdefault(k, []).append([r[0] + dx, r[1] + dy, r[2] + dz])
                    continue
                if not isinstance(r, dict):
                    continue
                r2 = dict(r)
                if "box" in r2 and len(r2["box"]) == 6:
                    b = r2["box"]
                    r2["box"] = [b[0] + dx, b[1] + dy, b[2] + dz, b[3] + dx, b[4] + dy, b[5] + dz]
                if "pos" in r2 and len(r2["pos"]) >= 3:
                    p = r2["pos"]
                    r2["pos"] = [p[0] + dx, p[1] + dy, p[2] + dz]
                self.meta.setdefault(k, []).append(r2)

    def ids_box(self, x0, y0, z0, x1, y1, z1) -> np.ndarray:
        x0, y0, z0, x1, y1, z1 = self._norm(x0, y0, z0, x1, y1, z1)
        out = np.zeros((y1 - y0 + 1, z1 - z0 + 1, x1 - x0 + 1), dtype=np.int32)
        for (cx, cy, cz), c in self.chunks.items():
            ox, oy, oz = cx * CH - x0, cy * CH - y0, cz * CH - z0
            ay, az, ax = max(0, oy), max(0, oz), max(0, ox)
            by, bz, bx = min(out.shape[0], oy + CH), min(out.shape[1], oz + CH), min(out.shape[2], ox + CH)
            if ay >= by or az >= bz or ax >= bx:
                continue
            out[ay:by, az:bz, ax:bx] = c[ay - oy:by - oy, az - oz:bz - oz, ax - ox:bx - ox]
        return out

    def transformed(self, rotate: int = 0, mirror_x: bool = False) -> "Build":
        """Yerel (0,0,0) etrafinda: once aynala (x -> -x), sonra saat yonunde rotate*90 dondur. Durumlar da donusur."""
        out = Build(self.name, self.db)
        (ox, oy, oz), ids = self.dense()
        if ids.size == 0:
            return out
        pal = list(self.palette)

        def tstate(s: str) -> str:
            if s in (KEEP, AIR):
                return s
            ex = s.startswith("!")
            b = s[1:] if ex else s
            if mirror_x:
                b = self.db.mirror(b, "x")
            if rotate % 4:
                b = self.db.rotate(b, rotate % 4)
            return ("!" + b) if ex else b

        tpal = [tstate(s) for s in pal]
        arr = ids
        x_lo, x_hi = ox, ox + ids.shape[2] - 1
        z_lo, z_hi = oz, oz + ids.shape[1] - 1
        if mirror_x:
            arr = arr[:, :, ::-1]
            x_lo, x_hi = -x_hi, -x_lo
        for _ in range(rotate % 4):
            # (x, z) -> (-z, x): yeni x ekseni = -eski z, yeni z ekseni = eski x
            arr = arr.transpose(0, 2, 1)[:, :, ::-1]
            x_lo, x_hi, z_lo, z_hi = -z_hi, -z_lo, x_lo, x_hi
        out.put_ids(x_lo, oy, z_lo, np.ascontiguousarray(arr), tpal)

        def tp(x, z):
            if mirror_x:
                x = -x
            return _rot_xz(x, z, rotate)

        for (x, y, z), snbt in self.block_entities.items():
            nx, nz = tp(x, z)
            out.block_entities[(nx, y, nz)] = snbt
        for e in self.entities:
            # surekli konum: (0,0) hucresinin merkezi etrafinda donusum
            nx, nz = tp(e["pos"][0] - 0.5, e["pos"][2] - 0.5)
            nx, nz = nx + 0.5, nz + 0.5
            e2 = dict(e)
            e2["pos"] = [nx, e["pos"][1], nz]
            e2["yaw"] = (float(e.get("yaw", 0)) * (-1 if mirror_x else 1) + 90 * (rotate % 4)) % 360
            out.entities.append(e2)
        out.meta = {k: list(v) if isinstance(v, list) else v for k, v in self.meta.items()}
        if rotate % 4 or mirror_x:   # oda/kapi/pencere/isik kayitlari da donsun (denetci dogru yerde arasin)
            for k in ("rooms", "doors", "windows", "lights", "decor_doors", "stair_air", "stair_cells"):
                items = []
                for r in self.meta.get(k, []) or []:
                    if isinstance(r, dict):
                        r2 = dict(r)
                        if "box" in r2 and len(r2["box"]) == 6:
                            bx = r2["box"]
                            ax, az = tp(bx[0], bx[2])
                            cx_, cz_ = tp(bx[3], bx[5])
                            r2["box"] = [min(ax, cx_), bx[1], min(az, cz_), max(ax, cx_), bx[4], max(az, cz_)]
                        if "pos" in r2 and len(r2["pos"]) >= 3:
                            px, pz = tp(r2["pos"][0], r2["pos"][2])
                            r2["pos"] = [px, r2["pos"][1], pz]
                        items.append(r2)
                    elif isinstance(r, (list, tuple)) and len(r) >= 3:
                        px, pz = tp(r[0], r[2])
                        items.append([px, r[1], pz])
                    else:
                        items.append(r)
                out.meta[k] = items
        return out

    # ------------------------------------------------------------------ plana derleme
    def to_plan(self, world_origin: tuple[int, int, int], facing: str = "north", meta: dict | None = None) -> Plan:
        """Yerel (0,0,0) -> world_origin; on cephe (yerel -z) dunyada `facing` yonune bakar."""
        if facing not in FACINGS:
            raise ValueError(f"facing su degerlerden biri olmali: {FACINGS}")
        times = FACINGS.index(facing)
        t = self.transformed(times) if times else self
        (lx, ly, lz), ids = t.dense()
        wx, wy, wz = world_origin
        origin = (wx + lx, wy + ly, wz + lz)
        pal = list(t.palette)
        bes = []
        for (x, y, z), snbt in t.block_entities.items():
            st = pal[int(t.get_id(x, y, z))] if t.is_set(x, y, z) else KEEP
            if st in (KEEP, AIR) or not (self.db.flags_of(st.lstrip("!")) & blockdb.BLOCK_ENTITY):
                continue        # hucredeki blok degismis (duzenlemede eski sandik/saksi gitmis): yetim veri plana girmez
            bes.append({"pos": [x - lx, y - ly, z - lz], "snbt": snbt})
        ents = []
        for e in t.entities:
            ents.append({"type": e["type"], "pos": [e["pos"][0] - lx, e["pos"][1] - ly, e["pos"][2] - lz],
                         "yaw": e.get("yaw", 0), "pitch": e.get("pitch", 0), "snbt": e.get("snbt", "{}")})
        m = {"name": self.name, "facing": facing, "local_origin_world": list(world_origin)}
        if meta:
            m.update(meta)
        return Plan(origin=origin, cells=ids, palette=pal, block_entities=bes, entities=ents, meta=m)

    def world_point(self, local: tuple[float, float, float], world_origin: tuple[int, int, int], facing: str) -> tuple[float, float, float]:
        """Yerel bir noktanin dunyadaki karsiligi (ornegin teras noktasi -> isinlama)."""
        times = FACINGS.index(facing)
        x, z = _rot_xz(local[0] - 0.5, local[2] - 0.5, times)
        return (world_origin[0] + x + 0.5, world_origin[1] + local[1], world_origin[2] + z + 0.5)
