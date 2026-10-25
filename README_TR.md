<div align="center">

# Usta

**Ne istediğini yaz. Claude tasarlasın, denetlesin, Minecraft dünyana kursun.**

Minecraft Java 26.3 · Fabric · Claude (Opus, Sonnet, Haiku, Fable) · Windows

[English](README.md)

<a href="docs/media/usta_tanitim.mp4"><img src="docs/media/teaser.gif" alt="Tek komutla kurulan 14,4 milyon bloklu stadyum" width="100%"></a>

[**▶ 1080p60 tanıtım filmini izle**](docs/media/usta_tanitim.mp4)

</div>

---

## Nedir

Usta, Claude'u tek oyunculu Minecraft dünyana bağlar. Sohbete bir insana söyler gibi yazarsın:

```
/claude önüme bahçeli bir Osmanlı konağı yap
```

Usta çevreni okur (arazi, su, mevcut yapılar, nereye baktığın), yer seçer, Claude'a yapıyı bir yapı kiti üstünde kısa
bir betik olarak yazdırır, önizleme görüntüleri çıkarır, otomatik denetimden geçirir ve önüne kurar. Yapının blok blok
yükselişini izleyebilirsin. Her iş tek komutla geri alınır.

İki parçadır:

| parça | yer | ne yapar |
|---|---|---|
| Fabric modu | `mod/` (Java 25) | 127.0.0.1 üstünde yerel API, tik bütçeli inşa motoru, kalıcı geri al/yinele, koruma bölgeleri, `/claude` ve `/usta` komutları |
| Python köprüsü | `bridge/usta/` | Claude'u Claude Code CLI ile çalıştırır; yapı kiti, önizleyici, denetçi ve 38 araçlı MCP sunucusu |

## Neler yapar

- **Tarif edebildiğin her şeyi kurar.** Ev, cami, kale, otel, koca kasaba, çiftlik, ağaç, araç. Kitte 72 bileşen,
  9 tarz paketi, 30 iç mekân tarifi, 14 ağaç türü, arazi araçları, 7 kızıltaş mekanizması ve 19 parametrik üreteç var
  (ev, modern villa, Osmanlı konağı, cami, köprü, deniz feneri, kale, gökdelen, şehir bloğu, çiftlik, yel değirmeni,
  Japon bahçesi ve dahası).
- **Modeli ve düşünme düzeyini sen seç.** Yeni yapı kendiliğinden Opus'a, küçük düzenleme Sonnet'e gider. İsteğin başına
  `!opus`, `!sonnet`, `!haiku` ya da `!fable`; düşünme için `!düşük`, `!orta`, `!yüksek`, `!çokyüksek`, `!max` yaz:
  `/claude !opus !max önüme devasa bir saray yap`.
- **Kurmadan önce denetler.** 36 otomatik kontrol: destek, kapı ve merdiven yürünebilirliği (3 blok baş boşluğu),
  ışık, çatı, pencere, palet, arazi ve su. Claude bulabildiğini kurmadan önce düzeltir, kapatamadığı uyarıyı sana
  söyler.
- **Var olanı düzenler.** "Bir kat ekle", "eşyalar nerede?", "kapı tak", "baştan düzgün yap": Usta kastettiğin yapıyı
  bulur ve değiştirir.
- **Her şeyi geri alır.** `/usta geri` son işi, patlamalar dahil, geri alır. Büyük silmeler tek tık onay bekler.
- **Tek komut, 14,4 milyon blok.** `/usta stadyum` hazır bir dev stadyumu (705 × 589, yaklaşık 105.000 koltuk)
  Claude'u çağırmadan önüne kurar. Tepeleri alır, çukurları ve suyu doldurur; önde bir yapı varsa yana kayar.
  `/usta stadyum zorla` tam olduğun yere kurar.
- **Claude Code'dan da çalışır.** Herhangi bir Claude Code oturumunda "Minecraft'ta …" de, aynı 38 MCP aracını kullanır.

## Tek dünyada, bir günde yapılanlar

Sohbete gerçekten yazılan istekler ve Usta'nın verdiği cevaplar (yazım hataları ve küfürler ayıklandı, bazıları
kısaltıldı):

| | istek | model | sonuç |
|---|---|---|---|
| <img src="docs/media/galeri/ayasofya.jpg" width="260"> | *devasa bir Ayasofya camiinin tam aynısını yap, çok büyük olsun, ihtişamlı olsun* | Opus 5.5 | 82 × 97, 64 blok yüksek, 44.000'den fazla blok: 40 pencereli ana kubbe, yarım kubbeler, 4 minare, mihrap, minber, şadırvanlı avlu |
| <img src="docs/media/galeri/iskandinav_kasabasi.jpg" width="260"> | *!opus önüme devasa bir İskandinav kasabası inşa et, hayallerdeki yaşam yeri olsun* | Opus 5.5 | 174 × 149: 18 döşeli iki katlı ev, 2 meydan, 2 park, yel değirmeni, gözetleme kulesi, taş yollar, sokak lambaları, giriş kemeri |
| <img src="docs/media/galeri/aquapark_otel.jpg" width="260"> | *!opus devasa 5 yıldızlı aquaparklı her şey dahil ultra lüks bir otel yap* | Opus 5.5 | 14 katlı kule ve 8 katlı kanatlar, yaklaşık 260 döşeli oda, lobi, restoran, çatıda sonsuzluk havuzu ve helipad; lagün, dalga havuzu, tembel nehir, kaydıraklı kule |
| <img src="docs/media/galeri/modern_villa.jpg" width="260"> | *önüme acayip lüks bir modernist ev yap, içinde her türlü ev eşyası olsun* | Opus 5.5 | 57 × 58 alanda 3 kat, yaklaşık 10.800 blok: havuz, teras bahçeleri, spor salonu ve kütüphane dahil 18 döşeli oda |
| <img src="docs/media/galeri/sahil_villasi.jpg" width="260"> | *lüks bir ev yap* → *eşyalar nerede?* → *kapılar nerede?* → *tüm yapıyı baştan, kusursuz yap* | Sonnet 5.5 → Opus 5.5 | önce 8 oda döşendi, sonra 8 kapı takıldı, en sonda eski villa geri alınıp iki katlı yeni bir sahil villası kuruldu: 32.736 blok, 9 kapı, merdiven, havuz, 7 döşeli oda; denetçi kritik hata bulmadı |
| <img src="docs/media/galeri/kizilitas_ciftligi.jpg" width="260"> | *!sonnet daha iyisini yap, redstone sistemli olsun, otomatik toplasın* | Sonnet 5.5 | 28 × 36 otomatik kavun-kabak çiftliği, 30 kızıltaş hattı: gözlemci pistonu çalıştırır, huniler ürünü sandığa taşır |
| <img src="docs/media/galeri/ciftlik.jpg" width="260"> | *!sonnet önüme profesyonel bir Minecraft farmı yap, hemen çalışmaya başlasın* | Sonnet 5.5 | 41 × 31 mahsul çiftliği: buğday, havuç, patates, pancar; sulu ve çitli, depo kulübesi ve kompost kutuları |
| <img src="docs/media/galeri/koy.jpg" width="260"> | *!haiku !düşük Minecraft köyünün aynısını yap* | Haiku 5.5 | 5 rustik ev, yollu meydan, kuyu, çan, tarlalar, saman balyaları, sokak lambaları |
| <img src="docs/media/galeri/bakkal.jpg" width="260"> | *!sonnet !düşük ufak, kaliteli, kusursuz, minimalist modern bakkal* | Sonnet 5.5 | 13 × 11, 1.285 blok: geniş camlı vitrin, raflar, ürünler ve kasa tezgâhı |
| <img src="docs/media/galeri/dev_agac.jpg" width="260"> | *!haiku !düşük hiç düşünmeden önüme devasa bir ağaç yap* | Haiku 5.5 | 68 blok yüksek, sekoya benzeri dev ağaç: konik gövde, kök kanatları, geniş taç |
| <img src="docs/media/galeri/stadyum_haiku.jpg" width="260"> | *!haiku !düşük stadyum yap* | Haiku 5.5 | 50 × 66: saha, 4 kademeli tribün, köşelerde projektör kuleleri, giriş tüneli |
| <img src="docs/media/galeri/agac_ev.jpg" width="260"> | *!opus !orta stadyum manzaralı ağaç ev yap, çatıdan maçı izleyelim* | Opus 5.5 | stadyum çatısında 39 blok yüksek ağaç ev, 8.522 blok |
| <img src="docs/media/galeri/bayrak.jpg" width="260"> | *!opus !düşük üstüne Türk bayrağının aynısını dik* | Opus 5.5 | 33 blokluk kuvars direk ve kırmızı-beyaz betondan 30 × 20 bayrak |
| <img src="docs/media/galeri/spor_araba.jpg" width="260"> | *!haiku önüme bir araba yap* | Haiku 5.5 | camlı kabini, farları ve siyah tekerlekleri olan 12 × 8 kırmızı spor araba |

Usta yapamadığını da söyler: oyunda denenmemiş kızıltaş devresini ("devre denenmedi") belirtir, ünlü bir yapının
birebir kopya değil yorum olduğunu söyler, kapatamadığı denetçi uyarılarını aktarır.

## Kurulum (Windows)

Gerekenler:

- Resmi launcher ile Minecraft Java Edition
- [python.org](https://www.python.org/downloads/)'dan Python 3.12 ya da üstü (3.13 önerilir); kurarken
  **Add python.exe to PATH** kutusunu işaretle
- [Claude Code](https://claude.com/claude-code): PowerShell'de bir kez kur ve giriş yap. Usta, Claude'u senin Claude
  hesabınla çalıştırır:
  ```powershell
  irm https://claude.ai/install.ps1 | iex
  claude auth login
  ```

Sonra:

1. [Releases](https://github.com/latentcore/usta-minecraft-claude/releases/latest) sayfasından
   **Usta-v0.1.0-Windows.zip** dosyasını indir ve bir klasöre çıkar.
2. Minecraft launcher'ı kapat, **KUR.bat**'a çift tıkla.
3. Launcher'ı aç, **Usta (Claude)** profilini seç, Oyna'ya bas.
4. Bir dünyada Usta'yı ilk kez kullanırken sohbetteki **Onayla ve yedekle** düğmesine bas (Usta dünyanın yedeğini
   alır), sonra örneğin `/claude önüme bir ev yap` yaz.

Kurucu ayrı bir **Usta (Claude)** launcher profili ve ayrı oyun klasörü (`%USERPROFILE%\UstaOyun`) ekler; normal
kurulumuna ve dünyalarına dokunmaz. Fabric'i, modu, Fabric API'yi ve performans modlarını (Sodium, Lithium,
FerriteCore) resmi kaynaklarından hash doğrulamasıyla kurar, köprüyü sanal ortama kurar ve MCP sunucusunu Claude Code'a
kaydeder. Python ya da Claude Code eksikse neyi kuracağını açıkça söyler. Tekrar çalıştırırsan yalnız eksikleri
tamamlar.

**Kaynaktan.** Depoyu klonlamak da yeter: mod derlenmemişse `KUR.bat` hazır jar'ı sürüm sayfasından indirir ve
SHA-256'sını doğrular. Kendin derlemek istersen JDK 25 kur, `JAVA_HOME`'u ona göster ve `mod` klasöründe
`gradlew build` çalıştır.

| betik | ne yapar |
|---|---|
| `KUR.bat` | kurar ya da onarır |
| `KALDIR.bat` | kaldırır (dünyalar silinmez, yedeğe taşınır) |
| `DURUM.bat` | sağlık kontrolü, her satır yeşil ya da kırmızı |
| `PANEL.bat` | yerel web paneli: istekler, işler, geri al, önizlemeler |
| `DUNYA_ICE_AKTAR.bat` | normal kurulumdaki bir dünyayı Usta profiline kopyalar |

## Komutlar

| komut | |
|---|---|
| `/claude <istek>` | kur, düzenle ya da sor |
| `/claude !haiku !düşük <istek>` | model ve düşünme düzeyi seç |
| `/usta geri` · `/usta yinele` | geri al · yinele |
| `/usta iptal` · `duraklat` · `sürdür` · `hız <sn>` | çalışan işi iptal et, duraklat, sürdür ya da süresini ayarla |
| `/usta foto` · `/usta harita` · `/usta panel` · `/usta durum` | fotoğraf, harita, web paneli, durum |
| `/usta stadyum` · `/usta stadyum zorla` | 14,4 milyon bloklu stadyum |
| `/usta patlama hızlı` · `normal` · `eşik 500` | hızlı patlamayı aç/kapat, TNT eşiği |
| `/ai undo` · `redo` · `cancel` · `status` … | İngilizce karşılıklar |

## Güvenlik

- API yalnız 127.0.0.1'de dinler; jeton yalnız senin kullanıcının okuyabildiği bir dosyadadır. `Origin` başlıklı
  istekler reddedilir, dünyayı LAN'a açarsan API kapanır.
- Dünyaya yalnız vanilla blok ve varlık yazılır. Mod verisi dünya klasörünün dışındadır.
- Usta, sen açıkça istemedikçe mevcut yapıların ya da korunan bölgelerin üstüne kurmaz. Oyuncu, evcil, adlı canlılar
  ve köylüler güvenli yere taşınır.
- Her iş geri alınabilir; Usta bir dünyaya ilk dokunduğunda yedek alınır; büyük silmeler onay ister.
- Dünyadaki yazılar (tabela, kitap) veri sayılır, asla talimat değildir.

## Motorun içi

- **Tik bütçeli inşa motoru.** Büyük işler oyun tiklerine yayılır; parça biletleri ve güvenli bir yerleştirme sırasıyla
  kurulur, kızıltaş devreleri iş bitince bir kez uyandırılır. 14,4 milyon bloklu stadyumun gözünün önünde
  yükselebilmesi bundan.
- **Hızlı patlama, motorun stres testi.** 256 ve üstü bitişik TNT, binlerce ayrı varlık yerine tek geçişte çözülür:
  4 saniye fitil, şok dalgası, krater ve vanilla hasar. 100.000 TNT'lik denemede sunucu 20 TPS'te kaldı. Küçük kümeler
  vanilla kalır, patlamalar her iş gibi geri alınır, `/usta patlama normal` özelliği tamamen kapatır.

## Belgeler

[ARCHITECTURE.md](ARCHITECTURE.md) · [AJAN_REHBERI.md](AJAN_REHBERI.md) · [TARZ_REHBERI.md](TARZ_REHBERI.md) ·
[LISANSLAR.md](LISANSLAR.md) · [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## Film hakkında

Film oyunun içinde, kamerayı her karede bir tik ilerleten bir Fabric istemci oyun testiyle çekildi; her kare
1920 × 1080 kaydedildiği için bilgisayar ne kadar yavaş olursa olsun hareket akıcı kalır. Stadyum, kamera etrafında
dönerken `/usta stadyum`'un çalıştırdığı kodla canlı kuruluyor; parça parça yükselsin diye izlenebilir kipte.
Sohbet satırı, yazılar ve galeri kurguda eklendi; müzik örnekleme değil, üretildi.

## Notlar

- Bu proje Claude Code (Claude Opus 5.5) ile yazıldı.
- Mojang Studios, Microsoft ya da Anthropic ile bağlantılı değildir, onlarca onaylanmamıştır. Minecraft, Mojang
  Synergies AB'nin; Claude, Anthropic'in ticari markasıdır.
- Claude için kendi Claude hesabın gerekir; istekler onun kullanımına sayılır.

## Lisans

[MIT](LICENSE)
