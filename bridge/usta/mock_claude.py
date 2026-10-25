"""Sahte Claude (yalniz test icin): `claude -p ... --output-format stream-json` gibi davranir, MCP sunucusunu
--mcp-config'ten baslatir ve istege gore hazir bir arac dizisi calistirir. Gercek modele gitmez, kota harcamaz."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HOUSE = r'''
w, d = 11, 9
b = Build("küçük taş ev")
st = {"base": "cobblestone", "wall": "spruce_planks", "frame": "stripped_spruce_log", "roof": "dark_oak_stairs", "trim": "dark_oak_slab"}
b.fill(-1, 0, -1, w, 0, d, "cobblestone")
b.fill(0, 1, 0, w - 1, 4, d - 1, st["wall"], hollow=True)
b.fill(1, 1, 1, w - 2, 4, d - 2, "air")
for x in (0, w - 1):
    for z in (0, d - 1):
        b.fill(x, 1, z, x, 4, z, "stripped_spruce_log[axis=y]")
b.fill(0, 4, 0, w - 1, 4, 0, "stripped_spruce_log[axis=x]")
b.fill(0, 4, d - 1, w - 1, 4, d - 1, "stripped_spruce_log[axis=x]")
mid = w // 2
b.set(mid, 1, 0, "spruce_door[facing=south,half=lower,hinge=left]")
b.set(mid, 2, 0, "spruce_door[facing=south,half=upper,hinge=left]")
for x in (2, w - 3):
    b.fill(x, 2, 0, x, 3, 0, "glass_pane")
    b.set(x, 1, -1, "spruce_trapdoor[facing=north,half=top,open=false]") if False else None
for z in (3, d - 4):
    b.fill(0, 2, z, 0, 3, z, "glass_pane"); b.fill(w - 1, 2, z, w - 1, 3, z, "glass_pane")
for i in range(d // 2 + 2):
    y = 5 + i
    z0, z1 = -1 + i, d - i
    if z0 > z1:
        break
    b.fill(-1, y, z0, w, y, z0, "dark_oak_stairs[facing=south]")
    b.fill(-1, y, z1, w, y, z1, "dark_oak_stairs[facing=north]")
    if z1 - z0 > 1:
        b.fill(0, y, z0 + 1, 0, y, z1 - 1, "spruce_planks"); b.fill(w - 1, y, z0 + 1, w - 1, y, z1 - 1, "spruce_planks")
    if z1 - z0 <= 1:
        b.fill(-1, y + (0 if z1 - z0 == 1 else 0), z0, w, y, z1, "dark_oak_slab") if z1 == z0 else None
b.set(mid, 3, -1, "lantern[hanging=false]") if False else None
b.set(mid - 1, 3, -1, "wall_torch[facing=north]"); b.set(mid + 1, 3, -1, "wall_torch[facing=north]")
b.set(2, 1, d - 2, "red_bed[facing=south,part=foot]") if False else None
b.set(2, 1, d - 3, "red_bed[facing=north,part=foot]"); b.set(2, 1, d - 2, "red_bed[facing=north,part=head]")
b.set(w - 2, 1, d - 2, "crafting_table"); b.set(w - 3, 1, d - 2, "furnace[facing=north]")
b.set(mid, 4, d // 2, "lantern[hanging=true]") if False else None
b.set(mid, 1, d // 2, "lantern")
b.meta["rooms"].append({"name": "oda", "box": [1, 1, 1, w - 2, 3, d - 2]})
b.meta["doors"].append({"pos": [mid, 1, 0]})
result(b, origin=site["origin"], facing=site["facing"])
'''


# altin set: anahtar kelimeler -> (uretec, parametre, izlenebilir inşa süresi sn, etiket). Gercek ajanin secimiyle ayni yol.
GOLDEN = [
    (("modern", "ev"), "modern_villa", {"size": "devasa"}, 24, "devasa modern villa"),
    (("osmanlı", "konağı"), "ottoman_konak", {"size": "büyük"}, 22, "Osmanlı konağı"),
    (("cami",), "mosque", {"size": "küçük"}, 20, "cami"),
    (("ağaç ev",), "treehouse_village", {"houses": 5}, 18, "ağaç ev köyü"),
    (("taş", "köprü"), "arch_bridge", {"length": 41}, 14, "taş kemerli köprü"),
    (("deniz feneri",), "lighthouse", {}, 16, "deniz feneri ve iskele"),
    (("kale",), "castle", {"size": "orta"}, 26, "ortaçağ kalesi"),
    (("gökdelen",), "skyscraper", {"size": "orta"}, 26, "cam gökdelen ve meydan"),
    (("japon",), "japanese_garden", {}, 16, "Japon bahçesi ve çay evi"),
    (("çiftlik",), "farm", {}, 18, "çiftlik"),
    (("şehir bloğu",), "city_block", {}, 40, "şehir bloğu"),
    (("park",), "park", {}, 14, "çiçekli park"),
    (("gizli", "oda"), "secret_room", {}, 10, "gizli oda"),
]


async def golden(call, sid, gname, prm, secs, label) -> None:
    d = await call("generate", {"name": gname, "params": prm, "where": "front", "preview": "quick"})
    if not d.get("draft_id"):
        emit({"type": "result", "subtype": "success", "is_error": True, "result": "Tasarım başarısız: " + str(d.get("message") or d.get("error")),
              "session_id": sid})
        return
    aud = d.get("audit") or {}
    j = await call("place_draft", {"draft_id": d["draft_id"], "mode": "watch", "seconds": secs})
    if not j.get("id"):
        emit({"type": "result", "subtype": "success", "is_error": True, "session_id": sid,
              "result": "Kurulamadı: " + str(j.get("message") or j.get("problems") or j.get("error") or j)[:200]})
        return
    t0 = time.time()
    while j.get("state") not in ("DONE", "FAILED", "CANCELLED") and time.time() - t0 < 600:
        if j.get("state") in ("AWAITING_CONFIRM", "CONFIRM"):
            j = await call("job_control", {"action": "confirm", "job_id": j.get("id")})
        j = await call("job_status", {"job_id": j["id"], "wait": 20})
    ok = j.get("state") == "DONE"
    emit({"type": "result", "subtype": "success", "is_error": not ok,
          "result": (f"Bitti: {label}, {j.get('placed')} blok (denetçi {aud.get('score')}, kritik {aud.get('critical', 0)})."
                     if ok else f"Kurulamadı: {j.get('message')}"), "session_id": sid})


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parse_args(argv: list[str]) -> dict:
    a = {"prompt": "", "mcp": None, "resume": None, "model": "mock"}
    i = 0
    while i < len(argv):
        t = argv[i]
        if t == "-p" and i + 1 < len(argv):
            a["prompt"] = argv[i + 1]
            i += 2
            continue
        if t == "--mcp-config":
            a["mcp"] = argv[i + 1]
            i += 2
            continue
        if t == "--resume":
            a["resume"] = argv[i + 1]
            i += 2
            continue
        if t == "--model":
            a["model"] = argv[i + 1]
            i += 2
            continue
        i += 1
    return a


async def flow(a: dict) -> None:
    sid = a["resume"] or str(uuid.uuid4())
    if os.environ.get("USTA_MOCK_FAIL") == "auth":
        emit({"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "Not logged in · Please run /login", "session_id": sid})
        return
    cfg = json.load(open(a["mcp"], encoding="utf-8"))["mcpServers"]["usta"]
    env = dict(os.environ)
    env.update(cfg.get("env", {}))
    params = StdioServerParameters(command=cfg["command"], args=cfg["args"], env=env)
    emit({"type": "system", "subtype": "init", "session_id": sid, "model": a["model"], "tools": ["mcp__usta__*"]})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            n = 0

            async def call(name: str, args: dict) -> dict:
                nonlocal n
                n += 1
                tid = f"toolu_{n}"
                emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": f"mcp__usta__{name}", "input": args}]},
                      "session_id": sid})
                res = await s.call_tool(name, args)
                txt = next((c.text for c in res.content if getattr(c, "type", "") == "text"), "{}")
                emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": [{"type": "text", "text": txt}]}]},
                      "session_id": sid})
                try:
                    return json.loads(txt)
                except Exception:
                    return {"raw": txt}

            p = a["prompt"].lower()
            ctx = await call("get_context", {"radius": 32})
            if ctx.get("game") == "closed":
                emit({"type": "result", "subtype": "success", "result": "Oyun açık değil.", "session_id": sid})
                return
            if "yağmur" in p and "ışınla" in p:
                await call("set_time", {"value": "akşam"})
                await call("set_weather", {"value": "yağmur"})
                h = await call("history", {})
                builds = [e for e in (h.get("entries") or []) if e.get("kind") == "BUILD" and not e.get("undone")]
                box = builds[0].get("box") if builds else None
                if box:   # [ox, oy, oz, sx, sy, sz]: yapinin ustu (teras) — arac guvenli noktaya oturtur
                    ox, oy, oz, sx, sy, sz = box
                    await call("teleport_player", {"x": ox + sx / 2, "y": oy + sy, "z": oz + sz / 2})
                emit({"type": "result", "subtype": "success", "result": "Bitti: akşam oldu, yağmur başladı, seni terasa ışınladım.",
                      "session_id": sid})
                return
            if "akşam" in p or "aksam" in p:
                await call("set_time", {"value": "akşam"})
                emit({"type": "result", "subtype": "success", "result": "Akşam oldu.", "session_id": sid})
                return
            if "geri al" in p:
                await call("undo", {})
                emit({"type": "result", "subtype": "success", "result": "Geri aldım.", "session_id": sid})
                return
            for keys, gname, prm, secs, label in GOLDEN:
                if all(k in p for k in keys):
                    await golden(call, sid, gname, prm, secs, label)
                    return
            site = await call("find_site", {"width": 13, "depth": 11, "where": "front", "max_dist": 30})
            cands = site.get("candidates") or []
            if not cands:
                emit({"type": "result", "subtype": "success", "result": "Önünde uygun düz alan bulamadım.", "session_id": sid})
                return
            c = cands[0]
            d = await call("run_build_script", {"code": HOUSE.replace('site["origin"]', str([c["origin"][0], c["origin"][1], c["origin"][2]]))
                                                                .replace('site["facing"]', repr(c["facing"])), "label": "küçük taş ev"})
            if not d.get("draft_id"):
                emit({"type": "result", "subtype": "success", "is_error": True, "result": "Tasarım başarısız: " + str(d.get("error")), "session_id": sid})
                return
            j = await call("place_draft", {"draft_id": d["draft_id"], "mode": "watch", "seconds": 6})
            t0 = time.time()
            while j.get("state") not in ("DONE", "FAILED", "CANCELLED") and time.time() - t0 < 120:
                j = await call("job_status", {"job_id": j["id"], "wait": 20})
            ok = j.get("state") == "DONE"
            emit({"type": "result", "subtype": "success", "is_error": not ok,
                  "result": f"Bitti: küçük taş ev, {j.get('placed')} blok." if ok else f"Kurulamadı: {j.get('message')}", "session_id": sid})


def main() -> None:
    a = parse_args(sys.argv[1:])
    asyncio.run(flow(a))


if __name__ == "__main__":
    main()
