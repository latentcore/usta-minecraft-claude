"""Kurulum oncesi denetim ve onarim: deniz seviyesi ustundeki su/kabarcik hucrelerinin kapatilmasi (sizinti yok),
desteksiz fener/cicek/hali/mum/tabela/kapi/yatak, toprak disindaki bitkiler; sorunlu susler kaldirilir, eksik
destek tamamlanir. Rapor W.notes'a yazilir."""
from __future__ import annotations

import numpy as np

import aa_core as C
from aa_core import SEA, World
from usta import blockdb

SOIL = ("grass_block", "dirt", "moss_block", "podzol", "coarse_dirt", "rooted_dirt", "mud", "pale_moss_block")
PLANTS = ("pink_petals", "pink_tulip", "white_tulip", "red_tulip", "orange_tulip", "oxeye_daisy", "azure_bluet", "allium",
          "lily_of_the_valley", "short_grass", "peony", "lilac", "rose_bush", "flowering_azalea", "azalea", "fern",
          "poppy", "dandelion", "cornflower", "wildflowers", "sweet_berry_bush")


def _names(w):
    return [p.lstrip("!").split("[", 1)[0].split(":")[-1] for p in w.pal]


def seal_water(w: World):
    """SEA ustundeki su ve kabarcik sutunlarinin yanlarindaki ve altindaki bos hucreleri kuvarsla kapatir."""
    G = w.G
    names = _names(w)
    wet = np.array([n in ("water", "bubble_column") for n in names])
    q = w.id(C.QUARTZ)
    fixed = 0
    for y in range(SEA + 1, C.Y1 + 1):
        L = G[y - C.Y0]
        wm = wet[L]
        if not wm.any():
            continue
        empty = L <= 1
        for dz, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = C.shift(wm, dz, dx) & empty
            if m.any():
                L[m] = q
                fixed += int(m.sum())
                empty = L <= 1
        if y - 1 >= SEA + 1:
            B = G[y - 1 - C.Y0]
            m = wm & (B <= 1)
            if m.any():
                B[m] = q
                fixed += int(m.sum())
    w.notes.append(f"denetim: su kapatma {fixed} hucre")
    return fixed


def supports(w: World, fix=True):
    """Destek denetimi; fix: desteksiz susu kaldir (hava yapar), bitki altini toprak degilse bitkiyi kaldir."""
    sand_id, water_id = w.id("minecraft:sand"), w.id("minecraft:water")     # once: palet asagidaki dizilerden once buyusun
    G = w.G
    names = _names(w)
    pal = w.pal
    full = np.zeros(len(pal), bool)
    for i, s in enumerate(pal):
        if i <= 1:
            continue
        try:
            full[i] = bool(C.DB.flags_of(s.lstrip("!")) & blockdb.FULL)
        except Exception:
            full[i] = False
    nonair = np.arange(len(pal)) > 1
    soil = np.array([n in SOIL for n in names])
    plant = np.array([n in PLANTS for n in names])
    upper = np.array(["half=upper" in s for s in pal])
    lower2 = np.array([("half=lower" in s) and n in ("peony", "lilac", "rose_bush") for s, n in zip(pal, names)])
    lant_floor = np.array([n.endswith("lantern") and "hanging=false" in s for s, n in zip(pal, names)])
    lant_hang = np.array([n.endswith("lantern") and "hanging=true" in s for s, n in zip(pal, names)])
    carpet = np.array([n.endswith("_carpet") for n in names])
    candle = np.array([n.endswith("candle") for n in names])
    stand_sign = np.array([n.endswith("_sign") and "wall" not in n and "hanging" not in n for n in names])
    hang_sign = np.array([n.endswith("_hanging_sign") and "wall" not in n for n in names])
    door_low = np.array([n.endswith("_door") and "half=lower" in s for s, n in zip(pal, names)])
    door_up = np.array([n.endswith("_door") and "half=upper" in s for s, n in zip(pal, names)])
    pot = np.array([n.startswith("potted_") or n == "flower_pot" for n in names])
    # deniz bitkileri: alti tam blok ya da yosun zinciri olmali; dogal zemin/su ustundeyse alti kum yapilir (yer kurulumda
    # canli araziye gore degisir), adanin tam olmayan blogu ustundeyse bitki kaldirilir
    sea = np.array([(n in ("seagrass", "kelp", "kelp_plant", "sea_pickle") or (n.endswith(("_coral", "_coral_fan")) and "dead" not in n))
                    for n in names])
    kelpish = np.array([n in ("kelp", "kelp_plant") for n in names])
    waterish = np.array([n in ("water",) for n in names])
    stats = {}
    removed = 0
    for y in range(C.Y0 + 1, C.Y1):
        L, B, A = G[y - C.Y0], G[y - 1 - C.Y0], G[y + 1 - C.Y0]
        bad_sea = sea[L] & ~full[B] & ~kelpish[B]
        if bad_sea.any():
            under = bad_sea & ((B == 0) | waterish[B])
            stats["deniz-bitkisi-taban"] = stats.get("deniz-bitkisi-taban", 0) + int(under.sum())
            if fix:
                B[under] = sand_id
                rest = bad_sea & ~under
                if rest.any():
                    stats["deniz-bitkisi-kaldirildi"] = stats.get("deniz-bitkisi-kaldirildi", 0) + int(rest.sum())
                    L[rest] = water_id
                    removed += int(rest.sum())
        checks = (
            ("bitki-toprak", plant[L] & ~upper[L] & ~soil[B]),
            ("cift-bitki-ust", upper[L] & plant[L] & ~lower2[B]),
            ("fener-alt", lant_floor[L] & ~nonair[B]),
            ("fener-ust", lant_hang[L] & ~nonair[A]),
            ("hali", carpet[L] & ~nonair[B]),
            ("mum", candle[L] & ~nonair[B]),
            ("tabela", stand_sign[L] & ~nonair[B]),
            ("asili-tabela", hang_sign[L] & ~nonair[A]),
            ("saksi", pot[L] & ~nonair[B]),
            ("kapi-alt", door_low[L] & ~(door_up[A])),
            ("kapi-ust", door_up[L] & ~(door_low[B])),
        )
        for k, m in checks:
            c = int(m.sum())
            if c:
                stats[k] = stats.get(k, 0) + c
                if fix:
                    L[m] = 1
                    removed += c
    # cift bitkilerin yetim ust yarilari (alt kaldirildiysa)
    for y in range(C.Y0 + 1, C.Y1):
        L, B = G[y - C.Y0], G[y - 1 - C.Y0]
        m = upper[L] & plant[L] & ~lower2[B]
        if m.any() and fix:
            L[m] = 1
    w.notes.append("denetim: destek " + (", ".join(f"{k} {v}" for k, v in sorted(stats.items())) or "sorun yok") +
                   (f" (kaldirilan {removed})" if fix else ""))
    return stats


def lights_and_candles(w: World):
    """Mum: alti tam ust yuzlu degilse kaldir. Fener: altinda destek yoksa ve ustu doluysa asili fenere cevir, yoksa
    kaldir; asili fenerin ustu bossa ve alti destekliyse ayakli fenere cevir."""
    G = w.G
    pal = w.pal
    n = len(pal)
    up = np.zeros(n, bool)
    down = np.zeros(n, bool)
    for i, s_ in enumerate(pal):
        if i <= 1:
            continue
        st = s_.lstrip("!")
        try:
            sd = int(C.DB.sturdy[C.DB.id(st)])
        except Exception:
            continue
        nm = st.split("[", 1)[0].split(":")[-1]
        post = nm.endswith(("_fence", "_wall")) or nm in ("iron_chain", "end_rod", "lightning_rod", "iron_bars")
        up[i] = bool(sd & blockdb.FACE_BIT["up"]) or post
        down[i] = bool(sd & blockdb.FACE_BIT["down"]) or post or nm.endswith("_chain")
    names = _names(w)
    candle = np.array([nm.endswith("candle") for nm in names])
    lf = [i for i, s_ in enumerate(pal) if names[i] == "lantern" and "hanging=false" in s_]
    lh = [i for i, s_ in enumerate(pal) if names[i] == "lantern" and "hanging=true" in s_]
    lant_f = np.zeros(n, bool)
    lant_f[lf] = True
    lant_h = np.zeros(n, bool)
    lant_h[lh] = True
    hang_id = w.id("lantern[hanging=true,waterlogged=false]")
    stand_id = w.id("lantern[hanging=false,waterlogged=false]")
    fixed = {"mum": 0, "fener-asildi": 0, "fener-oturdu": 0, "fener-kaldirildi": 0}
    for y in range(C.Y0 + 1, C.Y1):
        L, B, A = G[y - C.Y0], G[y - 1 - C.Y0], G[y + 1 - C.Y0]
        m = candle[L] & ~up[B]
        if m.any():
            L[m] = 1
            fixed["mum"] += int(m.sum())
        m = lant_f[L] & ~up[B]
        if m.any():
            to_h = m & down[A]
            L[to_h] = hang_id
            L[m & ~to_h] = 1
            fixed["fener-asildi"] += int(to_h.sum())
            fixed["fener-kaldirildi"] += int((m & ~to_h).sum())
        m = lant_h[L] & ~down[A]
        if m.any():
            to_s = m & up[B]
            L[to_s] = stand_id
            L[m & ~to_s] = 1
            fixed["fener-oturdu"] += int(to_s.sum())
            fixed["fener-kaldirildi"] += int((m & ~to_s).sum())
    w.notes.append("denetim: " + ", ".join(f"{k} {v}" for k, v in fixed.items()))
    return fixed


def signs_and_pads(w: World):
    """Duvar tabelasi arkasindaki blok tam blok degilse: alti tam bloksa ayakli tabelaya cevir, degilse kaldir.
    Nilufer suyun ustunde degilse kaldir."""
    G = w.G
    pal = w.pal
    names = _names(w)
    full = np.zeros(len(pal), bool)
    for i, s_ in enumerate(pal):
        if i > 1:
            try:
                full[i] = bool(C.DB.flags_of(s_.lstrip("!")) & blockdb.FULL)
            except Exception:
                pass
    water = np.array([n == "water" for n in names])
    rot = {"south": 0, "west": 4, "north": 8, "east": 12}
    fixed = {"tabela-ayakli": 0, "tabela-kaldirildi": 0, "nilufer": 0}
    for (x, y, z) in list(w.be.keys()):
        st = w.name(x, y, z)
        nm = st.split("[", 1)[0].split(":")[-1]
        if not nm.endswith("_wall_sign"):
            continue
        face = C.DB.props(st.lstrip("!")).get("facing", "north")
        fx, fz = C.FACE_VEC[face]
        if full[w.get(x - fx, y, z - fz)]:
            continue
        wood = nm[:-len("_wall_sign")]
        if full[w.get(x, y - 1, z)]:
            w.set(x, y, z, f"{wood}_sign[rotation={rot[face]},waterlogged=false]")
            fixed["tabela-ayakli"] += 1
        else:
            w.set(x, y, z, 1)
            w.be.pop((x, y, z), None)
            fixed["tabela-kaldirildi"] += 1
    pad = w.id("lily_pad")
    for y in range(C.Y0 + 1, C.Y1):
        L, B = G[y - C.Y0], G[y - 1 - C.Y0]
        m = (L == pad) & ~water[B]
        if m.any():
            L[m] = 1
            fixed["nilufer"] += int(m.sum())
    w.notes.append("denetim: " + ", ".join(f"{k} {v}" for k, v in fixed.items()))
    return fixed


def audit(w: World):
    seal_water(w)
    st = supports(w, fix=True)
    lights_and_candles(w)
    signs_and_pads(w)
    return st
