# MİMARİ — Usta

## Parçalar
```
 Oyuncu ──/claude…──►  ┌──────────── Minecraft (tek oyunculu, entegre sunucu) ────────────┐
                     │ Usta modu (Java, Fabric)                                         │
                     │  • Komutlar (/claude, /usta, /ai)   • İş motoru (tick bütçeli)   │
                     │  • Geri al/yinele (diskte günlüklü) • Güvenlik (korunan bölge,   │
                     │  • Dünya okuyucu (sütun/hacim)        varlık koruma, ilk onay)   │
                     │  • Oyun API'si  http://127.0.0.1:<rastgele> (anahtarlı)          │
                     │  • İstemci: oyuncu ekranı fotoğrafı, doku renk tablosu           │
                     └───────────────▲─────────────────────────────▲───────────────────┘
                                     │ HTTP+JSON / ikili plan        │ süreç başlatır
          ┌──────────────────────────┴───────┐        ┌──────────────┴──────────────┐
          │ usta.mcp_server (Python, stdio)  │◄───────│ usta.agent (başsız Claude    │
          │  gözler, bağlam, saha, tasarım,  │  MCP   │ koşturucu: claude -p …       │
          │  denetçi, görüntüleyici, kum     │        │ yalnız usta araçları)        │
          │  havuzu, inşa, geri al, kütüphane│        └──────────────▲──────────────┘
          └──────────▲───────────────────────┘                       │
                     │ MCP (kullanıcı kapsamı)          ┌────────────┴─────────────┐
          Claude Code oturumları (CLI, masaüstü)         │ usta.panel (127.0.0.1)   │
                                                         │ tarayıcı paneli          │
                                                         └──────────────────────────┘
```

**Neden MCP Python'da (stdio) ve modun içinde değil:** oyun kapalıyken de sunucu ayakta kalıp "oyun açık değil" diyebilir; görüntüleyici (numpy), kum havuzu ve Claude'un yazdığı yapı betikleri Python; büyük işler oyunun JVM'ini yormaz. Mod yalnız dünyaya dokunan, oyun kurallarını bilen kısımları taşır.

## Veri yerleri
- Yeni profilin oyun klasörü: `%USERPROFILE%\UstaOyun\` (mods, config, saves, screenshots, options.txt kopyası). AppData
  DIŞINDA: Microsoft Store launcher'ı oyunu paket içinde çalıştırır ve paket, AppData'da dışarıdan oluşturulan dosyaları görmez.
- Modun verisi: `%USERPROFILE%\UstaOyun\usta\` -> `worlds\<dünya-anahtarı>\` (geçmiş, iş günlükleri, korunan bölgeler, konuşma), `yedekler\`, `kutuphane\`, `runtime\api.json` (port+anahtar, yalnız oyuncunun Windows kullanıcısı okuyabilir), `cache\` (blok veritabanı, renk tablosu), `logs\`.
- Köprü: `%USERPROFILE%\UstaOyun\bridge\` (venv + paket + config.json).
- Dünya klasörüne mod verisi YAZILMAZ (S3). Dünya anahtarı = klasör adı + tohumun kısa özeti.
- Geliştirmede oyun klasörü `mod/run` (ya da test klasörleri); köprü `USTA_GAME_DIR` ile yönlendirilir.

## Oyun API'si (v1)
- Yalnız `127.0.0.1`, rastgele port; `Authorization: Bearer <anahtar>`; `Host` başlığı yalnız `127.0.0.1:<port>`/`localhost:<port>` (DNS rebinding koruması); `Origin` başlığı taşıyan her istek reddedilir (tarayıcıdan doğrudan erişim yok; panel kendi sunucusu üzerinden vekil olur).
- Tek oyunculu değilse (LAN'a açıldıysa) bütün yazma uçları kapanır.
- Uçlar: `ping, status, context, region/columns, region/blocks, blockdb, plan/validate, jobs (POST ikili plan), jobs/{id}[?wait], jobs/{id}/{cancel,pause,resume,speed}, history, undo, redo, chat, events (uzun yoklama), screenshot, colors, protect, selection, agent/*, world/*`.

## Plan biçimi — USTAPLN1 (bkz. `bridge/usta/plan.py`)
gzip( sihirli `USTAPLN1` | u32 başlık uzunluğu | başlık JSON | u16/u32 hücre dizisi ). Palet[0]=`keep`, palet[1]=`minecraft:air`; `!` önekli giriş "tam" (oyun bağlantı düzeltmesi yapmaz). Blok varlıkları SNBT, varlıklar tür+konum+SNBT. Mod her girişi oyunun kendi ayrıştırıcısıyla (`BlockStateParser`) doğrular; bilinmeyen blok/özellik -> ret.

## İş motoru
1. **Hazırlık (ayrı iş parçacığı):** paleti çöz, sıralama: (0) temizlenecekler yukarıdan aşağı (1) tam bloklar aşağıdan yukarı (2) tam olmayanlar (3) destek isteyenler, çift bloklar birlikte (4) sıvılar (5) varlıklar. İzlenebilir kipte her katman merkezden dışa.
2. **Önce-kopya:** değişecek her hücrenin eski durumu + blok varlığı NBT'si diske (sıkıştırılmış). Varlık koruma: oyuncu/evcil/adlı/köylü alan içindeyse güvenli noktaya taşınır (kaydı tutulur).
3. **Yerleştirme (sunucu tick'i):** `setBlock(UPDATE_CLIENTS | UPDATE_SKIP_ALL_SIDEEFFECTS)`; tick başına süre bütçesi (anında ~30 ms, izlenebilir hedef süreye göre); chunk'lar `TicketType.DRAGON` biletiyle yüklü tutulur.
4. **Yerleşme turu:** bağlanan bloklar (çit, duvar, cam panel, merdiven, kızıltaş) `Block.updateFromNeighbourShapes` ile oyunun kendi kuralıyla bağlanır; destek denetimi `canSurvive`; ışık oyunun motorunda.
5. **Günlük:** her N blokta imleç; temiz kapanışta kaldığı yerden, çökmede baştan (eş güçlü) devam. Geri alma önce-kopyadan, yineleme yerleşmiş plandan.
6. **Hızlı patlama (`MassExplosion`):** `TntBlockMixin` `TntBlock.prime` ve `wasExploded` başında; eşik (256) ve üstü bitişik
   TNT'de vanilla varlık/patlama yerine: küme taraması ve alan görüntüsü tick başına ≤15 ms dilimlerle, krater güç alanı
   (havada blok başına 0.75, katıda dirençle; yıkılan hücre geçirgen, zincirleme TNT kaynağa katılır) arka plan iş
   parçacığında; sonuç kuyruğun başına bir Usta işi: 4 sn fitil, ateş noktasından sabit hızlı şok dalgası sırası,
   parçacık/ses, dalga geçtikçe canlılara vanilla hasar formülü, sonda krater kenarına şekil güncellemesi. İş adımları
   sırasında TNT ateşlemesi bastırılır (geri alma yeniden patlatmaz).

## Güvenlik modeli (özet)
Yerel ve anahtarlı API; kum havuzu (ayrı süreç, iş nesnesiyle bellek/süreç sınırı, denetim kancalarıyla ağ/dosya/alt süreç yasağı, zaman ve çıktı sınırı); başsız koşu yalnız `mcp__usta__*`; dünya yazıları "güvenilmeyen veri" etiketiyle; büyük silme ve var olan yapıya dokunma oyunda tek tıkla onay; tehlikeli bloklar (TNT, lav, ateş…) yalnız açık istekle.

## Sürüm katmanı
Sürüme bağlı çağrılar `dev.usta.compat.V` içinde toplanır (bilet türü, bayraklar, NBT okuma/yazma, zaman/hava). Sonraki sürüme taşırken önce orası güncellenir.
