# TARZ_REHBERI — tarz paketleri ve üreteçler

## 9 tarz paketi (`bridge/usta/kit/style.py`)
| tarz | duvar / ikinci duvar | çatı | kapı | motifler |
|---|---|---|---|---|
| modern | beyaz beton / soyulmuş ladin | düz (teras) | modern cam | konsol, pergola, cam korkuluk, ahşap kaplama |
| ottoman (Osmanlı) | taş tuğla / kalsit sıva + koyu meşe karkas | kırma, tuğla, geniş saçak | kemerli | çıkma (jetty), cumba, kafes, lale, alamana |
| medieval (ortaçağ) | taş tuğla / kalsit + karkas | beşik, kaygan arduvaz | çerçeveli | çıkma, kepenk, mazgal |
| futuristic (fütüristik) | beyaz/siyah beton, açık mavi cam | düz | modern | cam giydirme, kanatlar, ışık şeritleri |
| japanese (Japon) | kalsit / koyu meşe | kavisli | çerçeveli | engawa, shoji, tōrō, kavisli saçak |
| scandinavian (İskandinav) | koyu meşe / ladin | dik beşik | çerçeveli | köşe tahtaları, beyaz söve |
| mediterranean (Ege/Akdeniz) | beyaz badana / kumtaşı | kırma | kemerli | mavi kubbe, kepenk, begonvil, pergola |
| rustic (rustik/köy) | meşe / kerpiç | beşik | çerçeveli | kütük köşe, kepenk, çiçeklik, çit bahçe |
| classical (klasik) | kuvars / kumtaşı | kırma | portik | korniş, alınlık, sütun, balüstrad |

Her tarz biyoma uyarlanır (çöl, tayga, karlı…): `style.adapt(biome)`. İç mekân stilleri ayrı: modern, nordic, rustic,
medieval, royal, ottoman, japanese, futuristic, industrial (dış tarzdan otomatik eşlenir).

## 19 üreteç (`generate(name, params)`)
| ad | ne | önemli parametreler |
|---|---|---|
| house | her tarzda 1-3 katlı döşeli ev | size, style, floors, roof |
| modern_villa | kademeli kütleler, konsol, havuz | size, floors, pool |
| ottoman_konak | taş zemin + çıkmalı üst kat, cumba, şadırvanlı bahçe | size, floors, garden |
| mosque | harim, kasnaklı kubbe, revak, avlu, minare | size, minarets |
| arch_bridge | taş kemerli köprü (göl/nehir) | length, width, span |
| lighthouse | şeritli fener kulesi + bekçi evi + iskele | size, height |
| pier | ahşap iskele | length, width |
| castle | surlar, kuleler, kapı, burç, avlu | size, wall_h, moat |
| watchtower | gözetleme kulesi | height |
| skyscraper | fütüristik cam gökdelen + meydan | floors, width, plaza |
| plaza / park | meydan / çiçekli park (araziyi düzler) | width, depth |
| apartment | dükkânlı apartman | floors, width, depth |
| city_block | 200×200 ızgara yollu şehir bloğu | width, depth, road, block |
| farm | ahır, silo, tarlalar, ağıllar, hayvanlar | size |
| windmill | yel değirmeni + ambar + tarla | height |
| treehouse_village | köprülerle bağlı ağaç evler | houses |
| japanese_garden | çay evi, koi gölü, köprü, zen bahçesi, torii | size |
| secret_room | kızıltaşla açılan gizli oda | style |

Ortak: `size` = küçük | orta | büyük | devasa (ya da sayı), `style`, `seed`, `name`.
