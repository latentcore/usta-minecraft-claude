"""Oyun ici komutlarin TEK KAYNAGI: ad, yazimlar (Java literalleri), arguman, ne yapar.
mod/.../UstaCommands.java bu listeyle tests/test_tutarlilik.py'de karsilastirilir; README'deki komut tablosu ve
AJAN_REHBERI.md buradan scripts/dev/rehber_uret.py ile uretilir. Yeni komut: once buraya, sonra Java'ya."""
from __future__ import annotations

from typing import NamedTuple


class Komut(NamedTuple):
    ad: str                   # sohbette gosterilen Turkce ad (/usta <ad>)
    yazimlar: tuple           # Java'daki literal yazimlar (Turkce, ASCII, Ingilizce); "istek" yolunda bos
    arg: str                  # arguman bicimi ("" = yok)
    ne: str                   # ne yapar (tek cumle)
    yol: str = "java"         # "java": UstaCommands literali; "istek": istek metninden hizli yol (Claude'suz)
    ic: bool = False          # yalniz sohbet dugmeleri/istemleri icin (yardimda gosterilmez)


KOMUTLAR: list[Komut] = [
    Komut("yardım", ("yardim", "yardım", "help"), "", "Komut listesini gösterir."),
    Komut("geri", ("geri", "undo"), "[iş]", "Son işi (ya da verilen işi) geri alır; patlamalar dahil."),
    Komut("yinele", ("yinele", "redo"), "[iş]", "Geri alınan işi yeniden uygular."),
    Komut("iptal", ("iptal", "cancel", "dur", "stop"), "[iş]", "Süren işi iptal eder."),
    Komut("duraklat", ("duraklat", "pause"), "", "Süren inşayı duraklatır."),
    Komut("sürdür", ("surdur", "sürdür", "devam", "resume"), "", "Duraklatılan inşayı sürdürür."),
    Komut("hız", ("hiz", "hız", "speed", "sure", "süre"), "<sn>", "Süren inşayı yaklaşık bu kadar saniyede bitirir."),
    Komut("anında", ("aninda", "anında", "instant"), "", "Süren inşayı hemen bitirir."),
    Komut("kip", ("kip", "mode"), "<izle|anında|sinematik>", "Varsayılan kurulum kipini seçer."),
    Komut("durum", ("durum", "status"), "", "Usta'nın durumunu gösterir (oyun, süren iş, Claude girişi)."),
    Komut("yeni", ("yeni", "new"), "", "Yeni konuşma başlatır: Claude önceki istekleri unutur."),
    Komut("seç", ("sec", "seç", "select"), "1|2", "Baktığın bloğu seçim köşesi yapar."),
    Komut("koru", ("koru", "protect"), "<ad>", "Seçili bölgeyi korumaya alır: Usta oraya yazmaz."),
    Komut("korumayı-kaldır", ("korumayi-kaldir", "korumayı-kaldır", "unprotect"), "<ad>", "Bölgenin korumasını kaldırır."),
    Komut("foto", ("foto", "fotograf", "fotoğraf", "photo"), "[iş]", "Son yapının fotoğrafını ve izometrik görüntüsünü çeker."),
    Komut("harita", ("harita", "map"), "", "Çevrenin kuşbakışı haritasını çıkarır."),
    Komut("kaydet", ("kaydet", "save"), "<iş>", "Yapıyı kütüphaneye kaydeder."),
    Komut("kütüphane", ("kutuphane", "kütüphane", "library"), "", "Kütüphanedeki yapıları listeler."),
    Komut("panel", ("panel",), "", "Tarayıcı panelini açar (yalnız bu bilgisayar)."),
    Komut("kod", ("kod", "code"), "", "Baktığın yapıyı birebir Python koduna çevirir (usta/calisma/kod)."),
    Komut("kopyala", ("kopyala", "copy"), "", "Baktığın yapıyı panoya kopyalar (birebir doğrulanır)."),
    Komut("yapıştır", ("yapistir", "yapıştır", "paste"), "", "Panodaki yapıyı önüne, baktığın yöne kurar."),
    Komut("çevre", ("cevre", "çevre", "survey"), "", "64 blok içindeki yapıları listeler ve haritasını çıkarır."),
    Komut("aynala", ("aynala", "mirror"), "[x|z]", "Son kurulan yapıyı yerinde aynalar."),
    Komut("döndür", ("dondur", "döndür", "rotate"), "[90|180|270]", "Son kurulan yapıyı yerinde döndürür."),
    Komut("patlama", ("patlama", "explosion"), "[hızlı|normal|eşik <n>]", "Büyük TNT kümelerinin hızlı (kasmasız) patlamasını açar ya da kapatır."),
    Komut("ada", (), "[zorla|deneme]", "Kalp Adası tatil köyünü bulunduğun yere, baktığın yöne kurar.", yol="istek"),
    Komut("stadyum", (), "[zorla]", "Hazır dev stadyumu önüne kurar.", yol="istek"),
    Komut("onayla", ("onayla", "confirm"), "<iş>", "Onay bekleyen işi onaylar (sohbetteki düğme).", ic=True),
    Komut("etkinleştir", ("etkinlestir", "etkinleştir", "activate"), "", "Usta'yı bu dünyada açar (ilk kullanım istemi).", ic=True),
    Komut("vazgeç", ("vazgec", "vazgeç"), "", "Usta'yı bu dünyada kullanmaz (ilk kullanım istemi).", ic=True),
    Komut("aç", ("ac", "aç", "open"), "<dosya>", "Fotoğraf ya da haritayı açar (sohbetteki düğme).", ic=True),
]


def gorunen() -> list[Komut]:
    """Yardimda ve README'de gosterilen komutlar."""
    return [k for k in KOMUTLAR if not k.ic]


def tablo() -> str:
    """README ve AJAN_REHBERI icin Markdown komut tablosu."""
    rows = ["| komut | ne yapar |", "|---|---|",
            "| `/claude <istek>` · `/usta <istek>` | Claude'a Türkçe istek (inşa, düzenleme, saat, hava…). |"]
    for k in gorunen():
        cmd = (f"/usta {k.ad}" + (f" {k.arg}" if k.arg else "")).replace("|", "\\|")   # GFM tablosunda | kacislanir
        rows.append(f"| `{cmd}` | {k.ne} |")
    rows.append("| `/ai …` | İngilizce takma ad: aynı alt komutlar İngilizce yazımlarıyla (undo, redo, photo, code…). |")
    return "\n".join(rows)
