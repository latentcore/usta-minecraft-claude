"""Usta Arena (dev stadyum): oyunda "/usta stadyum" yazilinca oyuncunun onune kurulur (arazi duzlenir; onde yapi varsa
yana/ileri kayar). "/usta stadyum zorla": oldugu yere, aradaki yapilarin uzerine kurar. Ilk calismada uretilip onbellege yazilir."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_OTHER = ("camp nou", "bernabeu", "wembley", "old trafford", "anfield",
          "maracana", "allianz", "küçük", "mini", "basit")
_FORCE = ("zorla", "allow_modify", "üstüne", "ustune", "yıkarak", "yikarak", "ne olursa olsun")


def istek_mi(text: str) -> bool:
    """Hazir stadyum yalniz "/usta stadyum [zorla]" (kisa, "stad" ile baslayan istek) ya da "usta arena" ile kurulur;
    baska her stadyum istegini (ornegin "onume kucuk bir stadyum yap") Claude tasarlar."""
    t = " ".join((text or "").casefold().split())
    if "usta arena" in t:
        return True
    w = t.split()
    return bool(w) and w[0].startswith("stad") and len(w) <= 3 and not any(o in t for o in _OTHER)


def zorla_mi(text: str) -> bool:
    t = (text or "").casefold()
    return any(k in t for k in _FORCE)


def kur_onume(game_dir: str, anchor: dict | None = None, force: bool = False, say=print) -> tuple[bool, str]:
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    cache = os.path.join(game_dir, "usta", "stadyum_onbellek")
    os.environ["ARENA_OUT"] = cache
    if not os.path.exists(os.path.join(cache, "G.npy")):
        say("Stadyum ilk kez üretiliyor (~15 sn)…")
        import arena_main
        arena_main.OUT = cache
        w, _ = arena_main.generate(with_rooms=True)
        arena_main.save(w)
    import arena_onume
    arena_onume.OUT = cache
    return arena_onume.main("", anchor, force=force, say=say)
