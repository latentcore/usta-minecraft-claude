"""Usta MCP sunucusu (stdio). Claude Code'a kullanici kapsaminda kayitlidir; oyun kapaliyken de calisir.
Calistirma: python -m usta.mcp_server"""
from __future__ import annotations

import functools
import json
import os
import traceback
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from . import ops
from .agent_guide import INSTRUCTIONS
from .gameapi import GameError, GameNotRunning

server = MCPServer(name="usta", instructions=INSTRUCTIONS)
REQUEST_ID = os.environ.get("USTA_REQUEST_ID") or None


def _j(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(s) > 24000:
        s = s[:24000] + "…(kısaltıldı)"
    return s


def tool(name: str, desc: str):
    """Hata dostu sarmalayici: oyun kapali / API hatasi -> anlasilir metin."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except GameNotRunning as e:
                return _j({"ok": False, "game": "closed", "message": str(e)})
            except GameError as e:
                return _j({"ok": False, "status": e.status, **e.payload})
            except KeyError as e:
                return _j({"ok": False, "message": f"bulunamadı: {e}"})
            except Exception as e:  # noqa: BLE001
                return _j({"ok": False, "message": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)[-800:]})
        server.tool(name=name, description=desc, structured_output=False)(wrapper)
        return wrapper
    return deco


def _with_image(info: dict, data: bytes | None) -> list:
    out: list = [_j(info)]
    if data:
        out.append(Image(data=data, format="jpeg"))
    return out


# ------------------------------------------------------------------ durum ve baglam
@tool("get_status", "Oyun açık mı, hangi dünya, süren iş/istek, duraklatma, Usta sürümü. Oyun kapalıysa bunu söyler.")
def get_status() -> str:
    return _j(ops.status())


@tool("get_context", "Oyuncunun konumu, bakış yönü, baktığı blok, boyut, biyom, saat/hava, oyun kipi, yakındaki varlıklar "
      "(evcil/adlı/köylü etiketli), istek anındaki çapa, yön sözlüğü (önüm/sağım…), çevre arazi özeti ve mevcut yapılar. "
      "Her inşa isteğinde İLK bunu çağır.")
def get_context(radius: int = 48) -> str:
    return _j(ops.context(radius, REQUEST_ID))


@tool("map_view", "Kuş bakışı harita görüntüsü: chunk ızgarası, koordinatlar, kuzey oku, ölçek, oyuncu oku, mevcut yapılar, korunan "
      "bölgeler. radius 8-256 (en çok 512x512 blok alan). center verilmezse çapa/oyuncu.")
def map_view(radius: int = 64, center_x: int | None = None, center_z: int | None = None) -> list:
    c = (center_x, center_z) if center_x is not None and center_z is not None else None
    info, data, _ = ops.map_view(c, radius, REQUEST_ID)
    return _with_image(info, data)


@tool("find_site", "Oyuncuya göre (where: front|right|left|back ya da north/south/east/west) width x depth tabanlı en iyi yerleri bulur; "
      "yapının ön cephesi oyuncuya bakar. Düzlük, kazı/dolgu, su, ağaç, mevcut yapı ve korunan bölgeleri hesaba katar. "
      "Adayları ve haritasını döndürür; candidates[0].origin ve facing'i betiğe ver.")
def find_site(width: int, depth: int, where: str = "front", min_dist: int = 4, max_dist: int = 40, allow_water: bool = False) -> list:
    info, data, _ = ops.site_candidates(width, depth, where, min_dist, max_dist, REQUEST_ID, allow_water)
    return _with_image(info, data)


# ------------------------------------------------------------------ tasarim
@tool("kit_reference", "Araç seti başvurusu: topic = overview | core | shapes | parts | style | trees | terrain | interiors | gen | audit | redstone. "
      "Modülün API özetini ve katalogunu döndürür.")
def kit_reference(topic: str = "overview") -> str:
    from . import kitdoc
    return kitdoc.reference(topic)


@tool("run_build_script", "Kısa bir Python yapı betiğini kum havuzunda çalıştırır (ağ/dosya yok, süre ve bellek sınırlı). Betikte hazır: "
      "Build, kit, shapes, parts, style, trees, terrain, interiors, gen, np, ctx, site, anchor. Sonunda result(b, origin=[x,y,z], facing='south'). "
      "Taslak (draft_id), özet, denetçi bulguları ve araziyle birlikte önizleme görüntüsü döner. Kurmaz.")
def run_build_script(code: str, origin: list[int] | None = None, facing: str | None = None, label: str | None = None,
                     params: dict | None = None, preview: str = "standard") -> list:
    info, data, _ = ops.run_build_script(code, origin, facing, label, REQUEST_ID, params, preview_kind=preview)
    return _with_image(info, data)


@tool("preview_draft", "Taslağı araziyle birlikte görüntüler. kind: quick (2 görünüm) | standard (4) | full (8 açı + kat kesitleri).")
def preview_draft(draft_id: str, kind: str = "standard") -> list:
    info, data, _ = ops.preview(draft_id, kind=kind)
    return _with_image(info, data)


@tool("audit_draft", "Taslağı denetçiden geçirir: 25+ kontrol (düz duvar, tek tip blok, havada blok, desteksiz meşale, kırık kapı/yatak, "
      "ulaşılamayan oda, karanlık nokta, sızan sıvı, yangın riski…), puan ve düzeltme önerileri.")
def audit_draft(draft_id: str) -> str:
    d = ops.Draft.load(draft_id)
    return _j(ops.audit_plan(d.plan()))


@tool("place_draft", "Taslağı dünyaya kurar. mode: watch (izlenebilir hızlı, varsayılan) | instant | cinematic; seconds: hedef süre. "
      "allow_modify yalnız oyuncu var olan bir yapının değiştirilmesini AÇIKÇA istediyse; allow_dangerous yalnız TNT/lav/ateş açıkça istendiyse. "
      "~45 sn bekleyip ilerlemeyi döndürür; sürüyorsa job_status ile devam et.")
def place_draft(draft_id: str, mode: str = "watch", seconds: float | None = None, allow_modify: bool = False,
                allow_dangerous: bool = False) -> str:
    return _j(ops.place(draft_id, mode, seconds, allow_modify, allow_dangerous, REQUEST_ID))


@tool("job_status", "Bir inşa işinin durumu ve ilerlemesi; wait saniye (en çok 50) bitmesini bekler.")
def job_status(job_id: str, wait: float = 30) -> str:
    return _j(ops.job_status(job_id, wait))


@tool("job_control", "Süren işi yönet: action = cancel | pause | resume | speed (seconds ile; 0 = anında bitir) | confirm.")
def job_control(job_id: str, action: str, seconds: float | None = None) -> str:
    return _j(ops.job_control(job_id, action, seconds))


@tool("undo", "Bir işi (job_id verilmezse en sonuncusunu) tamamen geri alır: bloklar, blok varlıkları, varlıklar; zaman/hava/ışınlanma da.")
def undo(job_id: str | None = None) -> str:
    return _j(ops.undo(job_id))


@tool("redo", "Geri alınmış bir işi yineler.")
def redo(job_id: str | None = None) -> str:
    return _j(ops.redo(job_id))


@tool("history", "Bu dünyadaki geri alınabilir işler (en yeni önce): id, etiket, kutu, durum.")
def history(limit: int = 20) -> str:
    return _j(ops.game().history(limit))


# ------------------------------------------------------------------ gozler
@tool("view_world", "Dünyanın bir bölgesini (kutu) farklı açılardan yazılımsal olarak görüntüler (izometrik, cephe, perspektif; "
      "kind=full ile 8 açı + kat kesitleri). Oyuncunun ekranını bozmaz.")
def view_world(x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, kind: str = "standard") -> list:
    info, data, _ = ops.world_view(x0, y0, z0, x1, y1, z1, kind)
    return _with_image(info, data)


@tool("player_screenshot", "Oyuncunun ekranında görünen kare (oyun penceresi görünürken). Pencere küçültülmüşse view_world kullan.")
def player_screenshot(max_width: int = 1024) -> list:
    info, data = ops.screenshot(max_width)
    return _with_image(info, data)


# ------------------------------------------------------------------ dunya eylemleri (yalniz acik istekle)
@tool("set_time", "YALNIZ oyuncu açıkça isterse: saati değiştir. value: sabah|gündüz|öğle|akşam|gece|gece yarısı ya da 0-23999. Geri alınabilir.")
def set_time(value: str) -> str:
    return _j(ops.game().world_action("time", {"set": value, "source": "agent" if REQUEST_ID else "mcp"}))


@tool("set_weather", "YALNIZ oyuncu açıkça isterse: hava = açık|yağmur|fırtına (clear|rain|thunder); duration tik. Geri alınabilir.")
def set_weather(value: str, duration: int = 6000) -> str:
    return _j(ops.game().world_action("weather", {"set": value, "duration": duration, "source": "agent" if REQUEST_ID else "mcp"}))


@tool("teleport_player", "YALNIZ oyuncu açıkça isterse: oyuncuyu ışınla (x,y,z; isteğe bağlı yaw/pitch). Güvenli bir noktaya (ayak altı dolu, "
      "baş hizası boş) ışınla. Geri alınabilir.")
def teleport_player(x: float, y: float, z: float, yaw: float | None = None, pitch: float | None = None) -> str:
    body = {"x": x, "y": y, "z": z, "source": "agent" if REQUEST_ID else "mcp"}
    if yaw is not None:
        body["yaw"] = yaw
    if pitch is not None:
        body["pitch"] = pitch
    return _j(ops.game().world_action("teleport", body))


@tool("say", "Oyun sohbetine kısa bir Türkçe satır yaz (kind: soft|line|warn).")
def say(text: str, kind: str = "soft") -> str:
    return _j(ops.say(text, kind))


# ------------------------------------------------------------------ duzenleme ve arazi
@tool("detect_structure", "Bakılan (ya da verilen x,y,z) noktadaki yapıyı algılar: bağlı doğal olmayan bloklar, kutu, boyut, palet, "
      "kat seviyeleri, çatı ve tarz tahmini. Düzenleme isteklerinin ilk adımı.")
def detect_structure(x: int | None = None, y: int | None = None, z: int | None = None) -> str:
    from . import edit
    api = ops.game()
    if x is None:
        la = api.context(8).get("looking_at")
        if not la:
            return _j({"ok": False, "message": "Oyuncu bir bloğa bakmıyor; x,y,z ver."})
        x, y, z = la["pos"]
    return _j(edit.detect(api, x, y, z))


@tool("edit_structure", "Mevcut bir yapıyı düzenleme betiği: betikte `existing` (Build; yerel 0,0,0 = yapının kutusunun en küçük köşesi, "
      "1 blok pay dahil; ön -z) hazır. Değiştir ve result(existing) ya da yeni bir Build döndür (origin verilmezse kutunun köşesi). "
      "box = [x0,y0,z0,x1,y1,z1] (iki köşe; history'nin [x,y,z,sx,sy,sz] kutusu da olur); box verilmezse oyuncunun baktığı "
      "yapı, o da yoksa Usta'nın son kurduğu yapı alınır. Kurarken place_draft(allow_modify=true).")
def edit_structure(code: str, box: list[int] | None = None, at: list[int] | None = None, label: str | None = None,
                   preview: str = "standard") -> list:
    info, data, _ = ops.edit_script(code, box, at, label, REQUEST_ID, preview)
    return _with_image(info, data)


@tool("terrain_script", "Arazi betiği (doldur, kes, yumuşat, tepe, göl, nehir, şelale, sahil, orman, yol): betikte `terrain` sözlüğü "
      "(ground/surface/floor [z,x] yerel y, water/tree/artificial maskeleri) ve `terrain` modülü fonksiyonları hazır. "
      "Alan x0..x1, z0..z1 (dünya). Yerel (0,0,0) = (x0, en düşük taban-1, z0).")
def terrain_script(code: str, x0: int, z0: int, x1: int, z1: int, label: str | None = None, preview: str = "standard") -> list:
    info, data, _ = ops.terrain_script(code, x0, z0, x1, z1, label, REQUEST_ID, preview)
    return _with_image(info, data)


# ------------------------------------------------------------------ uretecler, kizilatas
@tool("list_generators", "Parametrik üreteçlerin (ev, villa, konak, cami, kale, kule, köprü, deniz feneri, gökdelen, çiftlik, köy, "
      "şehir bloğu, park…) listesi, parametreleri ve tarz paketleri.")
def list_generators() -> str:
    from . import kitdoc
    return kitdoc.reference("gen")


@tool("generate", "Hazır bir üreteçle hızlı ve kaliteli taslak üretir (en hızlı yol). name = list_generators'tan; params = sözlük "
      "(ölçü, kat, tarz, ek özellikler); site verilmezse oyuncunun önünde uygun yer aranır (where). Taslak + önizleme döner; kurmak için place_draft.")
def generate(name: str, params: dict | None = None, where: str = "front", origin: list[int] | None = None, facing: str | None = None,
             preview: str = "standard") -> list:
    from . import genrun
    info, data, _ = genrun.run(name, params or {}, where, origin, facing, REQUEST_ID, preview)
    return _with_image(info, data)


@tool("redstone_list", "Hazır kızıltaş mekanizmaları ve parametreleri: gizli piston kapı (oyunda denendi), demir kapı+düğme, "
      "basınç plakalı kapı, gece lambası, kollu ışık, kapı zili, gizli kapak (vanilla kurallarıyla yazıldı, oyunda denenmedi). "
      "Listede olmayan devreyi run_build_script ile sıfırdan kur ve oyuncuya 'devre denenmedi' de.")
def redstone_list() -> str:
    from . import kitdoc
    return kitdoc.reference("redstone")


# ------------------------------------------------------------------ kutuphane ve sematik
@tool("library_list", "Kaydedilmiş yapılar (ad, boyut, blok sayısı, etiketler).")
def library_list() -> str:
    from . import library
    return _j({"items": library.list_items()[:60]})


@tool("library_save", "Kurulmuş bir yapıyı (job_id) kütüphaneye kaydeder (ad, etiketler).")
def library_save(job_id: str, name: str, tags: list[str] | None = None) -> str:
    from . import library
    api = ops.game()
    e = next((x for x in api.history(200).get("entries", []) if x["id"] == job_id), None)
    if not e:
        return _j({"ok": False, "message": "iş bulunamadı"})
    return _j({"ok": True, "item": library.save_from_world(api, e, name, tags)})


@tool("library_place", "Kütüphanedeki bir yapıyı oyuncunun önüne (where) ya da origin/facing ile taslak olarak hazırlar; "
      "rotate (0-3, saat yönü 90°) ve mirror_x ile döndürülebilir/aynalanabilir. Kurmak için place_draft.")
def library_place(item: str, where: str = "front", origin: list[int] | None = None, facing: str | None = None, rotate: int = 0,
                  mirror_x: bool = False) -> list:
    from . import library
    from .kit.core import Build
    plan = library.load_plan(item)
    b = Build(plan.meta.get("name", item))
    b.put_ids(0, 0, 0, plan.cells, plan.palette)
    for be in plan.block_entities:
        b.set_block_entity(*be["pos"], be["snbt"])
    if rotate % 4 or mirror_x:
        b = b.transformed(rotate, mirror_x)
    if origin is None:
        sx, sy, sz = b.size()
        info, _, _ = ops.site_candidates(sx, sz, where, request_id=REQUEST_ID)
        c = (info.get("candidates") or [None])[0]
        if not c:
            return [_j({"ok": False, "message": info.get("message", "uygun yer yok")})]
        origin, facing = c["origin"], c["facing"]
    lb = b.bounds()
    p = b.to_plan((origin[0] - lb[0][0], origin[1] - lb[0][1], origin[2] - lb[0][2]), facing or "north")
    dr = ops.new_draft(p, b.name, "library", REQUEST_ID)
    info, data, _ = ops.preview(dr.id)
    return _with_image({"draft_id": dr.id, **ops.plan_summary(p)}, data)


@tool("library_delete", "Kütüphaneden bir yapıyı siler.")
def library_delete(item: str) -> str:
    from . import library
    return _j({"ok": library.delete(item)})


@tool("export_schematic", "Kütüphanedeki yapıyı dışa aktarır: format = schem (Sponge/WorldEdit) | litematic (Litematica) | nbt (vanilla yapı şablonu).")
def export_schematic(item: str, format: str = "schem") -> str:
    from . import library
    return _j({"ok": True, "path": library.export(item, format)})


@tool("import_schematic", "Bir .schem / .litematic / .nbt dosyasını kütüphaneye alır (yol, isteğe bağlı ad).")
def import_schematic(path: str, name: str | None = None) -> str:
    from . import library
    return _j({"ok": True, "item": library.import_file(path, name)})


# ------------------------------------------------------------------ koruma, secim, gorseller
@tool("protect_region", "Korunan bölge ekler (Usta buraya asla yazmaz). x0..x1, y0..y1, z0..z1 dünya koordinatları.")
def protect_region(name: str, x0: int, z0: int, x1: int, z1: int, y0: int = -64, y1: int = 320) -> str:
    return _j(ops.game().protect({"name": name, "x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1}))


@tool("list_protected", "Korunan bölgeler (ad ve kutu); Usta bu alanlara asla yazmaz.")
def list_protected() -> str:
    return _j(ops.game().protected())


@tool("get_selection", "Oyuncunun /usta seç 1 ve /usta seç 2 ile seçtiği iki köşe (varsa).")
def get_selection() -> str:
    st = ops.game().status()
    return _j({"selection": st.get("selection"), "note": "Seçim yoksa oyuncudan /usta seç 1 ve /usta seç 2 istemek yerine baktığı noktayı kullan."})


@tool("photo", "Kurulmuş bir yapının (job_id; verilmezse son yapı) en güzel açıdan fotoğrafı (yazılımsal, gün saatine göre ışık); "
      "player_view=true ise oyuncu ekranı da. Dosyalar oyun klasöründe screenshots/usta altına kaydedilir.")
def photo(job_id: str | None = None, player_view: bool = False) -> list:
    info, data = ops.photo(job_id, player_view)
    return _with_image(info, data)


@tool("materials", "Bir işin malzeme listesi (blok türü ve adet).")
def materials(job_id: str) -> str:
    return _j(ops.materials(job_id))


@tool("before_after", "Bir işin önce-sonra karşılaştırma görüntüsü.")
def before_after(job_id: str) -> list:
    info, data = ops.before_after(job_id)
    return _with_image(info, data)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
