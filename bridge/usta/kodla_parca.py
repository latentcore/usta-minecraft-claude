"""kodla_parca: yapi->kod ciktisini anlamli parcalara ayirir (gövde, döşeme, duvar, sütun, oyuk, kapı, pencere, merdiven,
çatı, korkuluk, ışık, eşya, bitki) ve kodu bu bölümlere göre sıralar. KAYIPSIZ: birbirine değen (üst üste yazan) komutların
göreli sırası korunur; yalnız değmeyenler bölümlere toplanır. Her komut bölümünün adını taşıyan ince bir sarmalayıcıyla yazılır
(`duvar(b, ...)`, `pencere(b, ...)`), sarmalayıcıların hepsi aynı dolgudur. Ayrıca yapı özeti (katlar, kapı yönleri, çatı tipi)
ve parçalara ayrılan hücre yüzdesi hesaplanır."""
from __future__ import annotations

import heapq

import numpy as np

ORDER = ["govde", "doseme", "duvar", "sutun", "oyuk", "kapi", "pencere", "merdiven", "cati", "korkuluk", "isik", "esya",
         "bitki", "parca"]
BASLIK = {"govde": "GÖVDE (dolu kütle; içi sonra oyulur)", "doseme": "DÖŞEME VE TAVAN", "duvar": "DUVARLAR", "sutun": "SÜTUNLAR",
          "oyuk": "OYUKLAR (iç boşluk, hava)", "kapi": "KAPILAR", "pencere": "PENCERELER", "merdiven": "MERDİVENLER VE BASAMAKLAR",
          "cati": "ÇATI", "korkuluk": "KORKULUK, ÇİT, DUVAR ÜSTÜ", "isik": "AYDINLATMA", "esya": "İÇ EŞYA VE SÜSLER",
          "bitki": "BİTKİ VE PEYZAJ", "parca": "DİĞER PARÇALAR", "sil": "SİLİNEN HÜCRELER"}
_ISIK = ("lantern", "torch", "lamp", "glowstone", "sea_lantern", "candle", "shroomlight", "froglight", "end_rod", "campfire",
         "jack_o_lantern", "beacon", "conduit", "light")
_ESYA = ("bed", "chest", "barrel", "crafting_table", "furnace", "smoker", "bookshelf", "lectern", "anvil", "cauldron",
         "composter", "brewing_stand", "enchanting_table", "loom", "stonecutter", "grindstone", "table", "jukebox", "note_block",
         "bell", "carpet", "banner", "flower_pot", "potted_", "sign", "decorated_pot", "beehive", "bee_nest", "skull", "head",
         "button", "lever", "pressure_plate", "tripwire", "hopper", "dropper", "dispenser", "observer", "piston", "repeater",
         "comparator", "redstone", "rail", "ladder", "scaffolding", "shelf", "hay_block", "target", "respawn_anchor", "lodestone",
         "item_frame", "armor_stand", "vault", "trial_spawner", "spawner", "jigsaw", "structure_block", "crafter", "copper_bulb")
_BITKI = ("leaves", "sapling", "flower", "tulip", "poppy", "dandelion", "orchid", "allium", "bluet", "daisy", "cornflower",
          "lily", "rose", "peony", "lilac", "sunflower", "grass", "fern", "vine", "moss", "azalea", "bush", "kelp", "seagrass",
          "coral", "sea_pickle", "bamboo", "sugar_cane", "cactus", "mushroom", "wheat", "carrots", "potatoes", "beetroots",
          "melon", "pumpkin", "berry", "dripleaf", "spore", "roots", "nylium", "wart", "petals", "farmland", "dirt", "podzol",
          "mycelium", "water", "lava", "snow", "cobweb", "pitcher", "torchflower", "hanging_roots", "leaf_litter", "cactus_flower")


def short(state: str) -> str:
    s = state.lstrip("!").split("[", 1)[0]
    return s.split(":", 1)[-1]


def kategori(state: str, bx: tuple, solid: np.ndarray) -> str:
    """Tek bir kutunun (x0,y0,z0,x1,y1,z1) bolumu: once blok turu, sonra geometri."""
    n = short(state)
    if state == "keep":
        return "sil"
    if n in ("air", "cave_air", "void_air"):
        return "oyuk"
    if n.endswith("_door") or n.endswith("fence_gate"):
        return "kapi"
    if "glass" in n:
        return "pencere"
    if any(k in n for k in _ISIK):
        return "isik"
    if n.endswith("_stairs") or n.endswith("_slab"):
        x0, y0, z0, x1, y1, z1 = bx
        above = solid[y1 + 1:, z0:z1 + 1, x0:x1 + 1]
        return "cati" if not above.any() else "merdiven"
    if n.endswith("_fence") or n.endswith("_wall") or n in ("chain", "iron_bars") or n.endswith("_bars") or n.endswith("_chain"):
        return "korkuluk"
    if any(k in n for k in _BITKI):
        return "bitki"
    if any(k in n for k in _ESYA) or n.endswith("_trapdoor"):
        return "esya"
    x0, y0, z0, x1, y1, z1 = bx
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    if dy == 0 and (dx + 1) * (dz + 1) >= 4 and min(dx, dz) >= 1:
        return "doseme"
    if (dx == 0) != (dz == 0) and dy >= 1:
        return "duvar"
    if dx == 0 and dz == 0 and dy >= 1:
        return "sutun"
    if dx >= 1 and dy >= 1 and dz >= 1:
        return "govde"
    return "parca"


def _item_box(it) -> tuple[int, int, int, int, int, int]:
    """Ogenin (tek kutu ya da dongu) kapladigi toplam sinir kutusu."""
    kind = it[0]
    bx = it[2]
    if kind == "box":
        return bx
    if kind == "loop":
        _, _, bx, d, n = it
        e, m = (0, 0, 0), 1
    else:
        _, _, bx, d, n, e, m = it
    xs = [bx[0] + d[0] * (n - 1) * a + e[0] * (m - 1) * c for a in (0, 1) for c in (0, 1)] + \
         [bx[3] + d[0] * (n - 1) * a + e[0] * (m - 1) * c for a in (0, 1) for c in (0, 1)]
    ys = [bx[1] + d[1] * (n - 1) * a + e[1] * (m - 1) * c for a in (0, 1) for c in (0, 1)] + \
         [bx[4] + d[1] * (n - 1) * a + e[1] * (m - 1) * c for a in (0, 1) for c in (0, 1)]
    zs = [bx[2] + d[2] * (n - 1) * a + e[2] * (m - 1) * c for a in (0, 1) for c in (0, 1)] + \
         [bx[5] + d[2] * (n - 1) * a + e[2] * (m - 1) * c for a in (0, 1) for c in (0, 1)]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def regroup(items: list[tuple], cats: list[str], max_items: int = 8000) -> list[int]:
    """Bolumlere gore sira (indeks listesi). Ust uste yazan farkli durumlu iki komutun sirasi korunur (kayipsiz)."""
    n = len(items)
    if n <= 1 or n > max_items:
        return list(range(n))
    B = np.array([_item_box(it) for it in items], dtype=np.int64)
    S = np.array([it[1] for it in items], dtype=np.int64)
    pri = [ORDER.index(c) if c in ORDER else len(ORDER) for c in cats]
    succ: list[list[int]] = [[] for _ in range(n)]
    indeg = np.zeros(n, dtype=np.int64)
    for i in range(n - 1):
        j = np.arange(i + 1, n)
        ov = ((B[j, 0] <= B[i, 3]) & (B[j, 3] >= B[i, 0]) & (B[j, 1] <= B[i, 4]) & (B[j, 4] >= B[i, 1])
              & (B[j, 2] <= B[i, 5]) & (B[j, 5] >= B[i, 2]) & (S[j] != S[i]))
        js = j[ov]
        if js.size:
            succ[i] = js.tolist()
            indeg[js] += 1
    # bolum basina hazir kuyruklar; once su anki bolumden devam (basliklar parcalanmasin), bitince en oncelikli bolum
    ready: dict[int, list[int]] = {}
    for i in range(n):
        if indeg[i] == 0:
            heapq.heappush(ready.setdefault(pri[i], []), i)
    out = []
    cur = None
    while True:
        avail = [p for p, h in ready.items() if h]
        if not avail:
            break
        p = cur if cur in avail else min(avail)
        i = heapq.heappop(ready[p])
        cur = p
        out.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(ready.setdefault(pri[j], []), j)
    if len(out) != n:                       # olmamali (bagimliliklar ileri yonlu); guvenli geri donus
        return list(range(n))
    return out


def ozet(A: np.ndarray, pal: list[str], catmap: np.ndarray, cat_names: list[str], db=None) -> dict:
    """Son hucre bolumlerinden yapi ozeti: kat seviyeleri, kapi yonleri, catı tipi, bolum hucre sayilari, ayrisma yuzdesi."""
    Y, Z, X = A.shape
    filled = A != 0
    counts = {c: int((catmap == k).sum()) for k, c in enumerate(cat_names) if (catmap == k).any()}
    total = int(filled.sum())
    parca_k = cat_names.index("parca") if "parca" in cat_names else -1
    categorized = total - counts.get("parca", 0)
    air_ids = [i for i, s in enumerate(pal) if short(s) in ("air", "cave_air", "void_air")]
    solid = filled & ~np.isin(A, air_ids)
    solid_cat = int((solid & (catmap != parca_k)).sum())
    foot = int(solid.any(axis=0).sum())
    floors = []
    if "doseme" in cat_names:
        dk = cat_names.index("doseme")
        for y in range(Y):
            if foot and (catmap[y] == dk).sum() >= 0.25 * foot:
                floors.append(y)
    doors = []
    for i, s in enumerate(pal):
        n = short(s)
        if n.endswith("_door") and "half=upper" not in s and (A == i).any():
            f = s.split("facing=", 1)[1].split(",", 1)[0].rstrip("]") if "facing=" in s else "?"
            doors += [f] * int((A == i).sum())
    roof = "yok"
    if counts.get("cati"):
        ck = cat_names.index("cati")
        roof_ids = np.unique(A[catmap == ck])
        names = [short(pal[int(i)]) for i in roof_ids]
        roof = "eğimli (merdiven)" if any(x.endswith("_stairs") for x in names) else "yarım blok"
    elif total:
        roof = "düz"
    yon = {"north": "kuzey", "south": "güney", "east": "doğu", "west": "batı"}
    return {"boyut": [X, Y, Z], "hucre": total, "parca_yuzde": round(100.0 * categorized / max(1, total), 1),
            "kati_parca_yuzde": round(100.0 * solid_cat / max(1, int(solid.sum())), 1), "bolumler": counts,
            "kat_seviyeleri": floors[:12], "kapilar": [yon.get(d, d) for d in doors][:12], "cati": roof}


def ozet_satiri(oz: dict) -> list[str]:
    b = oz["bolumler"]
    kap = oz["kapilar"]
    kap_s = f"{len(kap)} ({', '.join(sorted(set(kap)))})" if kap else "0"
    parts = [f"katlar y={','.join(str(v) for v in oz['kat_seviyeleri'])}" if oz["kat_seviyeleri"] else "kat döşemesi yok",
             f"duvar {b.get('duvar', 0) + b.get('govde', 0)} blok", f"pencere {b.get('pencere', 0)}", f"kapı {kap_s}",
             f"çatı: {oz['cati']}", f"ışık {b.get('isik', 0)}", f"eşya {b.get('esya', 0)}"]
    return [f"# Yapı özeti: {' · '.join(parts)}",
            f"# Anlamlı parçalara ayrılan hücre: %{oz['parca_yuzde']} (yalnız katı bloklar: %{oz['kati_parca_yuzde']})"]
