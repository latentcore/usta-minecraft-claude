"""kodla: bir yapiyi (Build) okunur ve KAYIPSIZ bir Python betigine cevirir; betik ayni yapiyi blok blok kurar.

Yontem:
  1) Kutu ortusu, boyama sirasiyla: malzemeler sirayla boyanir; sonra boyanacak malzemenin hucreleri "joker" sayilir
     (ustune yazilacagi icin onceki kutu oraya tasabilir). Boylece pencereli bir duvar = tek tas kutu + pencere kutulari,
     ici bos bir oda = dolu kutu + hava kutusu. Her malzeme icin uc buyume yonu denenir, en az kutulu secilir.
  2) Tekrar: ayni malzeme ve boyuttaki kutular esit aralikla diziliyorsa `for` dongusu (iki boyutlu izgarada ic ice dongu).
  3) Ayna simetrisi (x ve z): yapi (neredeyse) simetrikse yarisi + aynalama (blok yonleri de doner) + simetriyi bozan
     hucrelerin duzeltmesi; daha kisaysa secilir. Yari da kendi icinde simetrikse ic ice uygulanir.
  4) Dogrulama: uretilen betik gercekten calistirilir ve sonuc blok blok (blok verileri dahil) karsilastirilir.

Kullanim: code, st = to_code(b, name); rep = verify(code, b)  (rep["exact"] True olmali).
Betik kum havuzunda (run_build_script / edit_structure) da calisir: Build ve result orada hazir.
"""
from __future__ import annotations

import re
import time

import numpy as np

from . import blockdb
from .kit.core import Build
from .plan import AIR, KEEP

PERMS = ((0, 1, 2), (0, 2, 1), (2, 1, 0))      # (dis, orta, ic) eksen: ic once buyur. (y,z,x) dizisinde: x-, z-, y-once
SYM_MIN = 0.80                                   # simetri denemesi icin en az eslesme orani


# ====================================================================== 1) kutu ortusu
def _greedy(must: np.ndarray, allowed: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """must hucrelerini allowed icinde kalan, acgozlu buyutulmus kutularla orter. Diziler (dis, orta, ic) eksenli.
    Doner: [(o0, m0, i0, o1, m1, i1)]. Uclarda must icermeyen dilimler geri kirpilir (kutular sikidir)."""
    O, M, I = must.shape
    covered = np.zeros(must.shape, dtype=bool)
    out = []
    for f in np.flatnonzero(must):
        o, r = divmod(int(f), M * I)
        m, i = divmod(r, I)
        if covered[o, m, i]:
            continue
        i1 = i
        row = allowed[o, m]
        while i1 + 1 < I and row[i1 + 1]:
            i1 += 1
        while i1 > i and not must[o, m, i1]:
            i1 -= 1
        m1 = m
        while m1 + 1 < M and allowed[o, m1 + 1, i:i1 + 1].all():
            m1 += 1
        while m1 > m and not must[o, m1, i:i1 + 1].any():
            m1 -= 1
        o1 = o
        while o1 + 1 < O and allowed[o1 + 1, m:m1 + 1, i:i1 + 1].all():
            o1 += 1
        while o1 > o and not must[o1, m:m1 + 1, i:i1 + 1].any():
            o1 -= 1
        covered[o:o1 + 1, m:m1 + 1, i:i1 + 1] |= must[o:o1 + 1, m:m1 + 1, i:i1 + 1]
        out.append((o, m, i, o1, m1, i1))
    return out


def _boxes(must: np.ndarray, allowed: np.ndarray) -> list[tuple[int, int, int, int, int, int]]:
    """Uc buyume yonunu dener; en az kutulu olani (x0,y0,z0,x1,y1,z1) olarak dondurur. Diziler (y,z,x)."""
    best = None
    for p in PERMS:
        mt = np.ascontiguousarray(must.transpose(p))
        at = np.ascontiguousarray(allowed.transpose(p))
        bx = _greedy(mt, at)
        if best is None or len(bx) < len(best[1]):
            best = (p, bx)
        if len(bx) <= 1:
            break
    p, bx = best
    res = []
    for (o0, m0, i0, o1, m1, i1) in bx:
        lo, hi = [0, 0, 0], [0, 0, 0]                # (y, z, x) sirasinda
        lo[p[0]], lo[p[1]], lo[p[2]] = o0, m0, i0
        hi[p[0]], hi[p[1]], hi[p[2]] = o1, m1, i1
        res.append((lo[2], lo[0], lo[1], hi[2], hi[0], hi[1]))
    return res


def _orders(A: np.ndarray, states: list[int]) -> list[list[int]]:
    """Denenecek boyama siralari: kaplayan (sinir kutusu buyuk) once, cok olan once, az olan once."""
    cnt, vol = {}, {}
    for s in states:
        m = A == s
        cnt[s] = int(m.sum())
        ys, zs, xs = np.nonzero(m)
        vol[s] = (int(ys.max() - ys.min()) + 1) * (int(zs.max() - zs.min()) + 1) * (int(xs.max() - xs.min()) + 1)
    o1 = sorted(states, key=lambda s: (-vol[s], -cnt[s], s))
    o2 = sorted(states, key=lambda s: (-cnt[s], s))
    o3 = sorted(states, key=lambda s: (cnt[s], s))
    out = []
    for o in (o1, o2, o3):
        if o not in out:
            out.append(o)
    return out


def cover_all(A: np.ndarray, quick: bool = False) -> list[list[tuple[int, tuple]]]:
    """A[y,z,x] (0 = yapida degil) -> her boyama sirasi icin [(durum, kutu)] listesi (aday ortuler)."""
    states = [int(s) for s in np.unique(A) if s != 0]
    if not states:
        return [[]]
    nonempty = A != 0
    orders = _orders(A, states)
    if quick:
        orders = orders[:1]
    out = []
    for order in orders:
        done = np.zeros(A.shape, dtype=bool)
        cmds = []
        for s in order:
            must = A == s
            allowed = nonempty & ~done
            for bx in _boxes(must, allowed):
                cmds.append((s, bx))
            done |= must
        out.append(cmds)
    return out


def cover(A: np.ndarray, quick: bool = False) -> list[tuple[int, tuple]]:
    """En az kutulu boyama sirasi (dongusuz kullanim icin)."""
    return min(cover_all(A, quick), key=len)


# ====================================================================== 2) tekrar -> dongu
def _runs(items: list[tuple[int, int, int]], k_near: int = 6) -> list[tuple[tuple[int, int, int], tuple[int, int, int], int]]:
    """Konum kumesinde esit aralikli diziler: [(baslangic, adim, adet)] (adet 1 = tek). Aday adimlar: uc eksen
    sirasinda (x,y,z / y,z,x / z,x,y) siralanmis listelerde sonraki birkac konum (buyuk kumelerde de hizli)."""
    pos = sorted(set(items))
    pset = set(pos)
    used = set()
    out = []
    views = []
    for key in (lambda q: (q[0], q[1], q[2]), lambda q: (q[1], q[2], q[0]), lambda q: (q[2], q[0], q[1])):
        lst = sorted(pos, key=key)
        views.append((lst, {q: k for k, q in enumerate(lst)}))
    for p in pos:
        if p in used:
            continue
        cands = []
        for lst, at in views:
            k = at[p] + 1
            got = 0
            while k < len(lst) and got < k_near:
                q = lst[k]
                if q not in used and q > p:
                    cands.append(q)
                    got += 1
                k += 1
        best = (1, (0, 0, 0))
        for q in cands:
            d = (q[0] - p[0], q[1] - p[1], q[2] - p[2])
            n = 1
            while (p[0] + n * d[0], p[1] + n * d[1], p[2] + n * d[2]) in pset and (p[0] + n * d[0], p[1] + n * d[1], p[2] + n * d[2]) not in used:
                n += 1
            if n > best[0]:
                best = (n, d)
        n, d = best
        if n < 3:
            used.add(p)
            out.append((p, (0, 0, 0), 1))
            continue
        for k in range(n):
            used.add((p[0] + k * d[0], p[1] + k * d[1], p[2] + k * d[2]))
        out.append((p, d, n))
    return out


def loops(cmds: list[tuple[int, tuple]]) -> list[tuple]:
    """Ayni durumun ardisik komut blogunda ayni boyutlu kutulari dongulere toplar. Ogeler:
    ("box", s, kutu) | ("loop", s, kutu0, d, n) | ("loop2", s, kutu0, d, n, e, m). Durumlar arasi sira korunur."""
    out = []
    i = 0
    while i < len(cmds):
        s = cmds[i][0]
        j = i
        while j < len(cmds) and cmds[j][0] == s:
            j += 1
        groups: dict[tuple, list] = {}
        order = []
        for _, bx in cmds[i:j]:
            size = (bx[3] - bx[0], bx[4] - bx[1], bx[5] - bx[2])
            if size not in groups:
                groups[size] = []
                order.append(size)
            groups[size].append((bx[0], bx[1], bx[2]))
        for size in order:
            runs = _runs(groups[size])
            # ayni (adim, adet) dizilerinin baslangiclari da esit aralikliysa ic ice dongu
            bucket: dict[tuple, list] = {}
            singles = []
            for p, d, n in runs:
                if n == 1:
                    singles.append(p)
                else:
                    bucket.setdefault((d, n), []).append(p)
            for (d, n), starts in bucket.items():
                for p0, e, m in _runs(starts):
                    bx0 = (p0[0], p0[1], p0[2], p0[0] + size[0], p0[1] + size[1], p0[2] + size[2])
                    if m >= 2:
                        out.append(("loop2", s, bx0, d, n, e, m))
                    else:
                        out.append(("loop", s, bx0, d, n))
            for p0, d, n in _runs(singles) if len(singles) >= 3 else [(p, (0, 0, 0), 1) for p in singles]:
                bx0 = (p0[0], p0[1], p0[2], p0[0] + size[0], p0[1] + size[1], p0[2] + size[2])
                out.append(("box", s, bx0) if n == 1 else ("loop", s, bx0, d, n))
        i = j
    return out


# ====================================================================== 3) kod yazimi
def _short_state(db: blockdb.BlockDB, s: str) -> str:
    """Kanonik durumdan varsayilan ozellikleri atar (Build.pid geri tamamlar: kayipsiz)."""
    exact = s.startswith("!")
    c = s[1:] if exact else s
    name, props = blockdb.split_state(c)
    b = db.blocks.get(name)
    if b is None or not props:
        return s
    _, dp = blockdb.split_state(db.states[b["default"]])
    keep = [(k, v) for k, v in props.items() if dp.get(k) != v]
    out = name + ("[" + ",".join(f"{k}={v}" for k, v in keep) + "]" if keep else "")
    return ("!" if exact else "") + out


def _varnames(db: blockdb.BlockDB, states: list[str]) -> dict[str, str]:
    used: set[str] = set()
    out = {}
    for s in states:
        if s == AIR:
            out[s] = "AIR"
            used.add("AIR")
            continue
        exact = s.startswith("!")
        name, props = blockdb.split_state(_short_state(db, s).lstrip("!"))
        base = name.split(":", 1)[-1].upper()
        parts = []
        for k, v in props.items():
            parts.append(k.upper() if v == "true" else ("NO_" + k.upper() if v == "false" else v.upper()))
        v = re.sub(r"[^A-Z0-9_]", "_", "_".join([base] + parts))
        if v[0].isdigit():
            v = "B_" + v
        if exact:
            v += "_TAM"
        cand, k = v, 2
        while cand in used:
            cand = f"{v}_{k}"
            k += 1
        used.add(cand)
        out[s] = cand
    return out


def _term(base: int, steps: list[tuple[int, str]]) -> str:
    t = str(base)
    for k, var in steps:
        if k:
            t += f" + {k}*{var}" if k > 0 else f" - {-k}*{var}"
    return t


def _box_args(bx, d=(0, 0, 0), e=(0, 0, 0)) -> str:
    x0, y0, z0, x1, y1, z1 = bx
    st = lambda a, ax: [(d[ax], "i"), (e[ax], "j")]
    return ", ".join([_term(x0, st(0, 0)), _term(y0, st(0, 1)), _term(z0, st(0, 2)), _term(x1, st(0, 0)), _term(y1, st(0, 1)), _term(z1, st(0, 2))])


def _cmd(var: str, bx, const: str, d=(0, 0, 0), e=(0, 0, 0), helper: str | None = None) -> str:
    x0, y0, z0, x1, y1, z1 = bx
    if helper and const != "KEEP":
        return f"{helper}({var}, {_box_args(bx, d, e)}, {const})"
    if (x0, y0, z0) == (x1, y1, z1):
        a = _box_args(bx, d, e).split(", ")[:3]
        if const == "KEEP":
            return f"{var}.forget({a[0]}, {a[1]}, {a[2]}, {a[0]}, {a[1]}, {a[2]})"
        return f"{var}.set({a[0]}, {a[1]}, {a[2]}, {const})"
    if const == "KEEP":
        return f"{var}.forget({_box_args(bx, d, e)})"
    return f"{var}.fill({_box_args(bx, d, e)}, {const})"


def _emit(items: list[tuple], var: str, names: dict[int, str], ind: str = "", cats: list[str] | None = None) -> list[str]:
    """cats verilirse her komut bolum adli sarmalayiciyla yazilir ve bolum degisince baslik eklenir."""
    from .kodla_parca import BASLIK
    lines = []
    last = None
    for k, it in enumerate(items):
        kind, s = it[0], it[1]
        c = names[s]
        h = cats[k] if cats else None
        if h and h != last:
            lines.append(f"{ind}# --- {BASLIK.get(h, h)}")
            last = h
        hh = h if h and h not in ("sil",) else None
        if kind == "box":
            lines.append(ind + _cmd(var, it[2], c, helper=hh))
        elif kind == "loop":
            _, _, bx, d, n = it
            lines.append(f"{ind}for i in range({n}):")
            lines.append(ind + "    " + _cmd(var, bx, c, d, helper=hh))
        else:
            _, _, bx, d, n, e, m = it
            lines.append(f"{ind}for j in range({m}):")
            lines.append(f"{ind}    for i in range({n}):")
            lines.append(ind + "        " + _cmd(var, bx, c, d, e, helper=hh))
    return lines


def _parts_of(items: list[tuple], pc: dict | None) -> tuple[list[tuple], list[str] | None]:
    """Parca kipi: ogeleri bolumlere ayirir ve kayipsiz yeniden siralar."""
    if not pc:
        return items, None
    from .kodla_parca import kategori, regroup
    cats = [kategori(pc["pal"][it[1]] if it[1] else "keep", it[2], pc["solid"]) for it in items]
    order = regroup(items, cats)
    return [items[k] for k in order], [cats[k] for k in order]


# ====================================================================== 4) simetri
def _mirror_ids(A: np.ndarray, pal: list[str], axis: str, db: blockdb.BlockDB, pid) -> np.ndarray:
    """A'nin aynasi (durumlar da aynalanir), ayni sekil ve palet indeksleriyle."""
    snap = list(pal)                     # pid() yeni durum ekleyebilir: anlik kopya uzerinde dolas
    remap = np.zeros(max(len(snap), int(A.max()) + 1), dtype=np.int64)
    for i, s in enumerate(snap):
        if i == 0 or s in (KEEP, AIR):
            remap[i] = i
            continue
        exact = s.startswith("!")
        try:
            # kurulumdaki merge ile ayni donusum: x aynasi; z aynasi = x aynasi + 180 derece
            m = db.mirror(s.lstrip("!"), "x")
            if axis == "z":
                m = db.rotate(m, 2)
        except Exception:
            m = s.lstrip("!")
        remap[i] = pid(("!" if exact else "") + m)
    M = remap[A]
    return M[:, :, ::-1] if axis == "x" else M[:, ::-1, :]


class _Ctx:
    def __init__(self, palette: list[str], db: blockdb.BlockDB):
        self.pal = list(palette)
        self.db = db
        self.idx = {s: i for i, s in enumerate(self.pal)}

    def pid(self, s: str) -> int:
        i = self.idx.get(s)
        if i is None:
            i = len(self.pal)
            self.pal.append(s)
            self.idx[s] = i
        return i


def _plain(A: np.ndarray, quick: bool) -> list[tuple]:
    """Boyama siralarindan, donguler katlandiktan sonra en kisa olani (izgara pencereler: once duvar, sonra ic ice dongu)."""
    return min((loops(c) for c in cover_all(A, quick)), key=_cost)


def _cost(items: list[tuple]) -> int:
    return sum(1 if it[0] == "box" else 2 if it[0] == "loop" else 3 for it in items)


def _plan(A: np.ndarray, ctx: _Ctx, depth: int, quick: bool, symmetry: bool) -> dict:
    """En kisa yazimi secer: duz ({kind:'plain', items}) ya da simetrik ({kind:'sym', axis, half, fix})."""
    plain = {"kind": "plain", "items": _plain(A, quick)}
    plain["cost"] = _cost(plain["items"])
    best = plain
    if not symmetry or depth >= 2 or A.size < 64:
        return best
    filled = A != 0
    for axis in ("x", "z"):
        n = A.shape[2] if axis == "x" else A.shape[1]
        if n < 4:
            continue
        M = _mirror_ids(A, ctx.pal, axis, ctx.db, ctx.pid)
        both = filled | (M != 0)
        score = float((A == M)[both].mean()) if both.any() else 0.0
        if score < SYM_MIN:
            continue
        h = (n + 1) // 2
        H = A.copy()
        if axis == "x":
            H[:, :, h:] = 0
        else:
            H[:, h:, :] = 0
        sub = _plan(H, ctx, depth + 1, quick, symmetry)
        # yeniden kurulum: yari + aynasi (aynanin ustune yazdigi orta sutun dahil)
        HM = _mirror_ids(H, ctx.pal, axis, ctx.db, ctx.pid)
        R = np.where(HM != 0, HM, H)
        fix = []
        for s in [int(v) for v in np.unique(A) if v != 0]:
            must = (A == s) & (R != s)
            if must.any():
                fix += [(s, bx) for bx in _boxes(must, A == s)]
        extra = (A == 0) & (R != 0)
        if extra.any():
            fix += [(0, bx) for bx in _boxes(extra, A == 0)]
        fix_items = loops(fix)
        cost = sub["cost"] + 3 + _cost(fix_items)
        if cost < best["cost"]:
            best = {"kind": "sym", "axis": axis, "n": n, "half": sub, "fix": fix_items, "cost": cost, "score": score}
    return best


def _render(node: dict, var: str, names: dict[int, str], counter: list[int], pc: dict | None = None) -> list[str]:
    if node["kind"] == "plain":
        items, cats = _parts_of(node["items"], pc)
        if pc is not None:
            pc.setdefault("used", set()).update(c for c in (cats or []) if c != "sil")
        return _emit(items, var, names, cats=cats)
    counter[0] += 1
    hv = f"yari{counter[0]}"
    lines = [f"{hv} = Build(\"yarı\")"]
    lines += _render(node["half"], hv, names, counter, pc)
    n = node["n"]
    lines.append(f"{var}.merge({hv})")
    if node["axis"] == "x":
        lines.append(f"{var}.merge({hv}, dx={n - 1}, mirror_x=True)          # x ekseninde ayna (eşleşme %{node['score'] * 100:.0f})")
    else:
        lines.append(f"{var}.merge({hv}, dz={n - 1}, rotate=2, mirror_x=True)   # z ekseninde ayna (eşleşme %{node['score'] * 100:.0f})")
    if node["fix"]:
        lines.append("# simetriyi bozan hücreler")
        items, cats = _parts_of(node["fix"], pc)
        if pc is not None:
            pc.setdefault("used", set()).update(c for c in (cats or []) if c != "sil")
        lines += _emit(items, var, names, cats=cats)
    return lines


def _expand(it) -> list[tuple]:
    """Ogenin tum kutulari (dongu acilmis)."""
    if it[0] == "box":
        return [it[2]]
    if it[0] == "loop":
        _, _, bx, d, n = it
        e, m = (0, 0, 0), 1
    else:
        _, _, bx, d, n, e, m = it
    out = []
    for j in range(m):
        for i in range(n):
            o = (d[0] * i + e[0] * j, d[1] * i + e[1] * j, d[2] * i + e[2] * j)
            out.append((bx[0] + o[0], bx[1] + o[1], bx[2] + o[2], bx[3] + o[0], bx[4] + o[1], bx[5] + o[2]))
    return out


def _parts_summary(A: np.ndarray, pal: list[str], solid: np.ndarray, quick: bool, node: dict) -> dict:
    """Hucre basina bolum (duz ortu uzerinden, boyama sirasiyla) -> yapi ozeti."""
    from .kodla_parca import ORDER, kategori, ozet, regroup
    items = node["items"] if node["kind"] == "plain" else _plain(A, quick)
    cats = [kategori(pal[it[1]] if it[1] else "keep", it[2], solid) for it in items]
    order = regroup(items, cats)
    names = ORDER + ["sil"]
    cm = np.full(A.shape, -1, dtype=np.int16)
    for k in order:
        ci = names.index(cats[k])
        for (x0, y0, z0, x1, y1, z1) in _expand(items[k]):
            cm[y0:y1 + 1, z0:z1 + 1, x0:x1 + 1] = ci
    cm[A == 0] = -1
    return ozet(A, pal, cm, names, None)


def _used_states(node: dict, acc: set[int]) -> None:
    if node["kind"] == "plain":
        for it in node["items"]:
            acc.add(it[1])
        return
    _used_states(node["half"], acc)
    for it in node["fix"]:
        acc.add(it[1])


def _count_kinds(node: dict, acc: dict) -> None:
    if node["kind"] == "sym":
        acc["symmetry"] = acc.get("symmetry", 0) + 1
        _count_kinds(node["half"], acc)
        items = node["fix"]
    else:
        items = node["items"]
    for it in items:
        acc[it[0]] = acc.get(it[0], 0) + 1


# ====================================================================== disa acik
def dense_of(b: Build) -> tuple[tuple[int, int, int], np.ndarray, list[str]]:
    o, ids = b.dense()
    return o, ids, list(b.palette)


def to_code(b: Build, name: str | None = None, world_origin: tuple[int, int, int] | None = None, symmetry: bool = True,
            loops_on: bool = True, quick: bool | None = None, parts: bool = True) -> tuple[str, dict]:
    """Build -> (betik, istatistik). Betikteki yerel (0,0,0) = yapinin en kucuk kosesi. parts: anlamli bolumler + ozet."""
    t0 = time.time()
    db = b.db
    o, A, pal = dense_of(b)
    A = A.astype(np.int64)
    ctx = _Ctx(pal, db)
    n_cells = int(np.count_nonzero(A))
    if quick is None:
        quick = A.size > 600_000                 # buyuk yapida tek boyama sirasi (hiz)
    if A.size > 3_000_000:
        symmetry = False
    if loops_on:
        node = _plan(A, ctx, 0, quick, symmetry)
    else:
        node = {"kind": "plain", "items": [("box", s, bx) for s, bx in cover(A, quick)]}
    used: set[int] = set()
    _used_states(node, used)
    used.discard(0)
    order = sorted(used, key=lambda s: ctx.pal[s])
    states = [ctx.pal[s] for s in order]
    vn = _varnames(db, states)
    names = {s: vn[ctx.pal[s]] for s in order}
    names[0] = "KEEP"
    pc = None
    oz = None
    if parts:
        air = [i for i, s in enumerate(ctx.pal) if s in (AIR, "minecraft:cave_air", "minecraft:void_air")]
        solid = (A != 0) & ~np.isin(A, air)
        pc = {"pal": ctx.pal, "solid": solid}
        try:
            oz = _parts_summary(A, ctx.pal, solid, quick, node)
        except Exception:  # noqa: BLE001  (ozet yardimci bilgi; kodu engellemez)
            oz = None
    body = _render(node, "b", names, [0], pc)
    if pc is not None and pc.get("used"):
        from .kodla_parca import ORDER
        used_h = [h for h in ORDER if h in pc["used"]]
        body = ["def _dolgu(b, x0, y0, z0, x1, y1, z1, m):", "    b.fill(x0, y0, z0, x1, y1, z1, m)",
                " = ".join(used_h + ["_dolgu"]), ""] + body
    Y, Z, X = A.shape
    nm = name or b.name or "yapı"
    wo = None if world_origin is None else (world_origin[0] + o[0], world_origin[1] + o[1], world_origin[2] + o[2])
    head = [f"# Usta yapı→kod (kayıpsız): {nm} · boyut {X}x{Y}x{Z} (x,y,z) · " + f"{n_cells:,}".replace(",", ".") + " hücre",
            "# Yerel (0,0,0) = yapının en küçük köşesi; ön -z. Çalıştırınca aynı yapıyı blok blok kurar."]
    if wo is not None:
        head.append(f"# Dünyada aynı yere: result(b, origin=({wo[0]}, {wo[1]}, {wo[2]}), facing=\"north\")")
    if oz is not None:
        from .kodla_parca import ozet_satiri
        head += ozet_satiri(oz)
    head.append(f"b = Build({nm!r})")
    consts = [f"{names[s]} = {_short_state(db, ctx.pal[s])!r}" for s in order]
    bes = []
    for (x, y, z), snbt in sorted(b.block_entities.items()):
        lx, ly, lz = x - o[0], y - o[1], z - o[2]
        bes.append(f"b.set_block_entity({lx}, {ly}, {lz}, {snbt!r})")      # hepsi (kayipsiz; plana yalniz gecerliler girer)
    lines = head + [""] + consts + [""] + body
    if bes:
        lines += ["", "# blok verileri (sandık, tabela, saksı…)"] + bes
    lines += ["", "result(b)"]
    code = "\n".join(lines) + "\n"
    kinds: dict = {}
    _count_kinds(node, kinds)
    stats = {"name": nm, "size": [X, Y, Z], "cells": n_cells, "states": len(order), "lines": len(lines), "body_lines": len(body),
             "block_entities": len(bes), "boxes": kinds.get("box", 0), "loops": kinds.get("loop", 0), "loops2": kinds.get("loop2", 0),
             "symmetry": kinds.get("symmetry", 0), "lines_per_1000": round(len(body) * 1000 / max(1, n_cells), 2),
             "seconds": round(time.time() - t0, 2), "origin": list(o)}
    if oz is not None:
        stats.update({"parca_yuzde": oz["parca_yuzde"], "kati_parca_yuzde": oz["kati_parca_yuzde"], "ozet": oz})
    return code, stats


def run(code: str) -> Build:
    """Betigi calistirir, kurdugu Build'i dondurur (kum havuzu disinda; yalniz Build ve result)."""
    got: dict = {}

    def result(b, **kw):
        got["b"] = b

    ns = {"Build": Build, "result": result, "np": np, "__name__": "__kodla__"}
    exec(compile(code, "kodla_betik.py", "exec"), ns)
    return got.get("b") or ns["b"]


def compare(a: Build, b: Build, a_origin: tuple[int, int, int] | None = None) -> dict:
    """a (ozgun) ile b (betikten) blok blok: hucre durumlari + blok verileri. a_origin: a'nin betikteki (0,0,0)'i."""
    oa, A, pa = dense_of(a)
    if a_origin is not None:
        oa = a_origin
    ob, B, pb = dense_of(b)
    key = {s: i for i, s in enumerate(sorted(set(pa) | set(pb)))}
    ka = np.array([key[s] for s in pa], dtype=np.int64)
    kb = np.array([key[s] for s in pb], dtype=np.int64)
    keep = key[KEEP]
    # ortak cerceve: a'nin koordinatlari (betikteki 0,0,0 = a'nin en kucuk kosesi)
    off = (ob[0], ob[1], ob[2])           # betik cercevesinde b2 kosesi
    Y = max(A.shape[0], off[1] + B.shape[0])
    Z = max(A.shape[1], off[2] + B.shape[1])
    X = max(A.shape[2], off[0] + B.shape[2])
    lo = (min(0, off[1]), min(0, off[2]), min(0, off[0]))
    shape = (Y - lo[0], Z - lo[1], X - lo[2])
    FA = np.full(shape, keep, dtype=np.int64)
    FB = np.full(shape, keep, dtype=np.int64)
    FA[-lo[0]:-lo[0] + A.shape[0], -lo[1]:-lo[1] + A.shape[1], -lo[2]:-lo[2] + A.shape[2]] = ka[A]
    FB[off[1] - lo[0]:off[1] - lo[0] + B.shape[0], off[2] - lo[1]:off[2] - lo[1] + B.shape[1], off[0] - lo[2]:off[0] - lo[2] + B.shape[2]] = kb[B]
    diff = FA != FB
    missing = int(np.count_nonzero(diff & (FB == keep)))
    extra = int(np.count_nonzero(diff & (FA == keep)))
    wrong = int(np.count_nonzero(diff)) - missing - extra
    bea = {(x - oa[0], y - oa[1], z - oa[2]): v for (x, y, z), v in a.block_entities.items()}
    beb = dict(b.block_entities)
    be_diff = sum(1 for k in set(bea) | set(beb) if bea.get(k) != beb.get(k))
    cells = int(np.count_nonzero(FA != keep))
    return {"exact": missing == 0 and extra == 0 and wrong == 0 and be_diff == 0, "cells": cells,
            "match_pct": round(100.0 * (cells - missing - wrong) / max(1, cells), 4), "missing": missing, "extra": extra,
            "wrong": wrong, "block_entity_diff": be_diff}


def roundtrip(b: Build, name: str | None = None, **kw) -> tuple[str, dict]:
    """Cevir + calistir + karsilastir. Istatistige 'exact' ve 'match_pct' eklenir."""
    code, st = to_code(b, name, **kw)
    t0 = time.time()
    rebuilt = run(code)
    cmp = compare(b, rebuilt)
    st.update(cmp)
    st["verify_seconds"] = round(time.time() - t0, 2)
    return code, st


def from_plan(plan, name: str = "yapı") -> Build:
    """Plan (or. vanilla yapi sablonu) -> Build (yerel 0,0,0 = planin kosesi)."""
    b = Build(name)
    b.put_ids(0, 0, 0, np.asarray(plan.cells), list(plan.palette))
    for be in plan.block_entities:
        b.set_block_entity(*be["pos"], be["snbt"])
    return b
