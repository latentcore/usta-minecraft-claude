"""Model yonlendirici (T13): kural tabanli, aninda.
Yeni yapi / buyuk tasarim -> Opus; kucuk duzenleme, soru, fotograf, harita, zaman/hava -> Sonnet.
Zorlama (istegin basina): !opus !sonnet !haiku !fable, kisa !o !s !h !f; ya da ilk kelime model adi
("haiku: ...", "fable 5.1 ...", "sonnet 5.5 ...")."""
from __future__ import annotations

import re

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"
FABLE = "claude-fable-5-1"
FORCE = {"opus": OPUS, "o": OPUS, "sonnet": SONNET, "s": SONNET, "haiku": HAIKU, "h": HAIKU, "fable": FABLE, "f": FABLE}
NAMES = {OPUS: "Opus 5.5", SONNET: "Sonnet 5.5", HAIKU: "Haiku 5.5", FABLE: "Fable 5.1"}

BUILD_VERBS = r"\b(yap|yapar mısın|yapsana|kur|inşa et|insa et|oluştur|olustur|dik|tasarla|build|make|create|construct)\b"
EDIT_WORDS = r"\b(değiştir|degistir|yükselt|yukselt|genişlet|genislet|daralt|boya|sivri|yassı|çevir|cevir|taşı|tasi|kaldır|kaldir|sil|tamir|onar|döşe|dose|aydınlat|aydinlat|ekle|bir kat|kat daha|daha)\b"
BIG_WORDS = (r"\b(devasa|dev|büyük|buyuk|kocaman|muhteşem|muhtesem|görkemli|gorkemli|usta işi|detaylı|detayli|kusursuz|kale|sur|şehir|sehir|"
             r"köy|koy|mahalle|saray|cami|camii|konak|gökdelen|gokdelen|villa|liman|üs|us|kompleks|kampüs|stadyum|katedral|park|"
             r"çiftlik|ciftlik|köprü|kopru|deniz feneri|kule|tapınak|tapinak|meydan|bahçe|bahce|ev|evi|hamam|han|çay evi|cay evi)\b")
QUESTION = r"(\?|\b(ne|nerede|neresi|nasıl|nasil|kaç|kac|hangi|mi|mı|mu|mü|göster|goster|anlat|fotoğraf|fotograf|harita|neredeyim)\b)"
WORLD_ONLY = r"\b(akşam|aksam|sabah|gece|öğle|ogle|gündüz|gunduz|yağmur|yagmur|fırtına|firtina|güneşli|gunesli|ışınla|isinla|saat)\b"


EFFORTS = {"düşük": "low", "dusuk": "low", "low": "low", "orta": "medium", "medium": "medium",
           "yüksek": "high", "yuksek": "high", "high": "high", "çokyüksek": "xhigh", "cokyuksek": "xhigh", "xhigh": "xhigh",
           "max": "max", "maks": "max", "maksimum": "max"}
EFFORT_TR = {"low": "düşük", "medium": "orta", "high": "yüksek", "xhigh": "çok yüksek", "max": "en yüksek"}


def parse_prefix(text: str) -> tuple[str, str | None, str | None]:
    """Bastaki isaretler, her sirada ve birlikte: model (!opus !sonnet !haiku !fable, kisa !o !s !h !f; ya da ilk kelime
    model adi: "haiku: ...", "fable 5.1 ...") ve dusunme duzeyi (!dusuk !orta !yuksek !cokyuksek !max).
    Donus: (temiz metin, model|None, effort|None)."""
    t = text.strip()
    model = effort = None
    named = re.match(r"^(opus|sonnet|haiku|fable)(?:\s*5[.,]\d)?\s*(?::\s*|\s+)", t, flags=re.I)
    if named:   # kisa bicim olmadan yalniz uzun adlar ("o" Turkce kelime)
        model, t = FORCE[named.group(1).lower()], t[named.end():]
    while True:
        m = re.match(r"^!([^\s!:]+?)(?:\s*5[.,]\d)?\s*:?(?:\s+|$)", t)
        if not m:
            break
        k = m.group(1).lower()
        if k in FORCE and model is None:
            model = FORCE[k]
        elif k in EFFORTS and effort is None:
            effort = EFFORTS[k]
        else:
            break
        t = t[m.end():]
    return t, model, effort


def strip_force(text: str) -> tuple[str, str | None]:
    t, model, _ = parse_prefix(text)
    return t, model


def display_name(model: str) -> str:
    return NAMES.get(model, model)


def choose(text: str, pref: str | None = "auto") -> tuple[str, str, str]:
    """(model, temizlenmis metin, gerekce)"""
    clean, forced = strip_force(text)
    if forced:
        return forced, clean, "zorlandı"
    p = (pref or "auto").lower()
    if p in FORCE or p in NAMES:
        m = FORCE.get(p, p)
        return m, clean, f"ayar: hep {display_name(m)}"
    t = clean.lower()
    build = re.search(BUILD_VERBS, t) is not None
    big = re.search(BIG_WORDS, t) is not None
    edit = re.search(EDIT_WORDS, t) is not None
    question = re.search(QUESTION, t) is not None
    world_only = re.search(WORLD_ONLY, t) is not None and not big
    if world_only and not (build and big):          # "gece yap" bir yapi degil, zaman eylemi
        return SONNET, clean, "zaman/hava/ışınlanma"
    if build and big and not (edit and not re.search(r"\b(devasa|kale|şehir|sehir|köy|koy|mahalle|saray|gökdelen|villa)\b", t)):
        return OPUS, clean, "yeni yapı / büyük tasarım"
    if build and not edit:
        return OPUS, clean, "yeni yapı"
    if edit:
        return SONNET, clean, "düzenleme"
    if question:
        return SONNET, clean, "soru / görüntü"
    return SONNET, clean, "varsayılan küçük iş"


def effort_for(model: str, reason: str) -> str:
    """Hiz hedefiyle kalite dengesi: yeni yapida orta, kucuk islerde dusuk."""
    if model in (OPUS, FABLE):
        return "medium"
    return "low"
