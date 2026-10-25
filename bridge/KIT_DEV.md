# Usta araç seti — geliştirici notu (kısa)

Proje: Minecraft Java 26.3 için "Usta" modu + Python köprüsü. Çalışma anındaki Claude, bu araç setiyle kısa Python betikleri yazarak usta işi yapılar kurar. Kalite çıtası: "bunu usta bir yapı ustası günlerce uğraşıp yapmış" dedirtmek (derinlik, doku geçişi, oran, siluet, ayrıntı, iç mekân, aydınlatma, peyzaj).

## Çalıştırma
- Python: `bridge\.venv\Scripts\python.exe` (numpy, Pillow, pytest kurulu). Çalışma klasörü `bridge`.
- Testler: `bridge\.venv\Scripts\python.exe -m pytest -q bridge\tests` (conftest blok veritabanını `tests/data/blockdb-26.3.json.gz`'den yükler; oyun gerekmez).
- Kodda blok veritabanını hazırlamak: `from usta.blockdb import BlockDB, set_db; set_db(BlockDB.from_file("tests/data/blockdb-26.3.json.gz"))`.

## Temel API (`usta/kit/core.py` — oku)
- `Build(name)`: seyrek voksel yapı. Yerel çerçeve: **y yukarı; ön cephe z=0'da ve -z'ye bakar; yapı +z'ye uzanır; +x yapının kendi sağı** (cepheye bakan izleyicinin solu). Hepsi tamsayı hücre koordinatı.
- `b.set(x,y,z,state)`, `b.get(x,y,z)`, `b.fill(x0,y0,z0,x1,y1,z1,state, hollow=, replace=, only_empty=)` (uçlar dahil), `b.clear(...)` (hava = dünyada boşalt), `b.forget(...)` (plandan çıkar = dünyaya dokunma), `b.put_mask(x0,y0,z0,mask[y,z,x],state)`, `b.line(p0,p1,state)`, `b.merge(other,dx,dy,dz,rotate=,mirror_x=)`, `b.transformed(rotate,mirror_x)`, `b.set_block_entity(x,y,z,snbt)`, `b.add_entity(type,x,y,z,yaw,pitch,snbt)`, `b.meta` (rooms/doors/windows/lights/floors listeleri: denetçi ve iç mekân bunları kullanır), `b.bounds()`, `b.size()`, `b.count()`, `b.histogram()`, `b.to_plan(world_origin, facing)`.
- Durum dizgileri: `"oak_stairs[facing=north,half=top]"` — eksik özellikler varsayılanla dolar, **olmayan blok/özellik anında `UnknownBlock` hatası verir** (uydurma yok). `"!..."` öneki: oyun bağlantı düzeltmesi yapmasın (normalde çit/duvar/cam panel/merdiven köşeleri/kızıltaş **oyunun kendi kuralıyla** otomatik bağlanır; sen bağlantı özelliği yazma).
- Yönler yerel çerçevede: `north` = -z (ön/dış), `south` = +z (arka/iç), `east` = +x (sağ), `west` = -x. Merdiven `facing` = çıkış yönü (yüksek tarafı). Kapı `facing` = kapı kapalıyken içeriden dışarıya bakış değil, oyuncunun yerleştirirken baktığı yön; ön kapı için `facing=south` (dışarıdan içeri giren oyuncunun baktığı yön) kullan. Duvar meşalesi `wall_torch[facing=X]`: X yönüne bakar, arkasındaki (X'in tersi) blok destektir.
- Blok veritabanı (`usta/blockdb.py`): `db.canonical(s)`, `db.flags_of(s)` (FULL, GRAVITY, SUPPORT_*, CONNECT, FLAMMABLE, DANGEROUS…), `db.has_block(name)`, `db.blocks` (ad → özellikler), `db.rotate`, `db.mirror`. 26.3'te olmayan blok kullanma; emin değilsen `db.has_block` ile sor.
- Görüntü: `from usta.render.sheet import save_preview; save_preview(build, "work/onizleme/x.png", kind="standard"|"full")` — **yazdığın her şeyin görüntüsüne Read ile bak ve eleştir**; düz duvar, tek tip blok, delik pencere, boş iç, düz kutu çatı = başarısızlık.

## Kurallar
- Yalnız vanilla bloklar. Dosya adları ASCII, metin UTF-8. Yalnız proje içinde (`bridge/` ve `work/`) yaz.
- Kopyalanan kod yok (özellikle GPL: WorldEdit vb.); fikir serbest, kod kendin.
- Büyük hacimler `fill`/`put_mask` ile; blok blok Python döngüsü yalnız küçük ayrıntılarda.
- Fizik: destek isteyen bloklar (meşale, fener, halı, kapı, yatak, çiçek, buton, tabela) desteğiyle birlikte; yerçekimli bloklar (kum, çakıl, beton tozu) altı dolu; sıvı kapalı hacimde; ateş/lav/TNT yok.
- Her modülün pytest testi olsun (olumlu + olumsuz örnek), testler hızlı (<10 sn).
