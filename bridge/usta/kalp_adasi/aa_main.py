"""Kalp Adasi: uret, onizle, kaydet.  python aa_main.py [onizle]
Siralama onemli: once ada ve kabuklar, sonra ic mekanlar ve dis mekan, en son cekirdek (merdiven + asansor) ve kalp suiti
(cekirdek kendi hacmini her seyin ustune yazar)."""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import aa_core as C  # noqa: E402
import aa_denetim  # noqa: E402
import aa_front  # noqa: E402
import aa_hotel  # noqa: E402
import aa_island  # noqa: E402
import aa_land  # noqa: E402
import aa_park  # noqa: E402
import aa_podium  # noqa: E402
import aa_tower  # noqa: E402

OUT = os.environ.get("AA_OUT") or os.path.join(os.path.expanduser(r"~\UstaOyun"), "usta", "kalp_adasi_onbellek")


def generate(say=print):
    t0 = time.time()
    w = C.World()
    steps = [("ada", aa_island.island), ("podyum", aa_tower.podium), ("kule", aa_tower.tower), ("kalp", aa_tower.heart),
             ("otel", aa_hotel.hotel), ("havuz terasi", aa_hotel.deck0), ("gokyuzu bahceleri", aa_hotel.sky_gardens),
             ("gokyuzu restorani", aa_hotel.crown), ("podyum ici", aa_podium.podium_interiors),
             ("teras-kopru-kapi-bulvar", aa_front.front), ("parklar", aa_park.parks), ("peyzaj", aa_land.land),
             ("merdiven", lambda w: aa_tower.stair_core(w, aa_tower.all_levels())), ("asansorler", aa_tower.elevators),
             ("kaide", aa_tower.pedestal), ("balayi suiti", aa_hotel.heart_suite), ("denetim", aa_denetim.audit)]
    for name, fn in steps:
        t = time.time()
        fn(w)
        say(f"{name}: {time.time() - t:.1f} sn, blok {w.count():,}")
    # yetim blok verisi: hucresi artik blok varligi tasimayan kayitlari at
    from usta import blockdb
    keep = {}
    for (x, y, z), snbt in w.be.items():
        st = w.name(x, y, z)
        if st in ("keep", "minecraft:air"):
            continue
        try:
            if C.DB.flags_of(st.lstrip("!")) & blockdb.BLOCK_ENTITY:
                keep[(x, y, z)] = snbt
        except Exception:
            pass
    w.be = keep
    say(f"toplam {time.time() - t0:.1f} sn; blok {w.count():,}; palet {len(w.pal)}; BE {len(w.be)}; varlik {len(w.ents)}")
    return w


def save(w, out=OUT):
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "G.npy"), w.G)
    meta = {"pal": w.pal, "be": [[list(k), v] for k, v in w.be.items()], "ents": w.ents, "notes": w.notes,
            "bounds": [C.X0, C.Y0, C.Z0, C.X1, C.Y1, C.Z1], "fireworks": getattr(w, "fireworks", None),
            "anchor": [C.AX, C.AY, C.AZ], "offset": list(C.offset())}
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return out


if __name__ == "__main__":
    w = generate()
    print(save(w))
    print("\n".join(w.notes))
    if "onizle" in sys.argv:
        import aa_onizle as P
        d = os.path.join(OUT, "onizleme")
        print(P.render(w, d, "ada", views=("top", "iso_se", "iso_sw"), step=2))
        print(P.perspective(w, d, "oyuncu_gozu", eye=(C.AX + 0.5, C.AY + 1.6, C.AZ + 0.5), target=(-200, 160, C.AZ),
                            size=(1280, 720), fov=80))
