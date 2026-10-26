"""cevre (buyuk resim, kopyala/yapistir, aynala/dondur), oyun ici yardimci komutlar ve yeni MCP araclari: sahte oyun API'siyle."""
from __future__ import annotations

import gzip
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from usta import blockdb
from usta.kit.core import Build
from usta.plan import Plan


@pytest.fixture
def _gamedir(tmp_path, monkeypatch):
    monkeypatch.setenv("USTA_GAME_DIR", str(tmp_path / "oyun"))
    cache = tmp_path / "oyun" / "usta" / "cache"
    cache.mkdir(parents=True)
    src = Path(__file__).parent / "data" / "blockdb-26.3.json.gz"
    (cache / blockdb.db_path().name).write_bytes(src.read_bytes())


class FakeAPI:
    """Oyun yerine: dunya bir Build (dunya koordinatlari). Planlar dunyaya uygulanir, sohbet ve eylemler kaydedilir."""

    def __init__(self, world: Build, player=(200.5, 64.0, 300.5), facing="north", look=None, history=None, ents=None):
        self.world, self.player, self.facing, self.look = world, player, facing, look
        self.entries = history or []
        self.ents = ents or []
        self.chats, self.actions, self.plans = [], [], []

    def context(self, n=8):
        x, y, z = self.player
        return {"player": {"x": x, "y": y, "z": z, "facing": self.facing},
                "looking_at": {"pos": list(self.look)} if self.look else None}

    def history(self, n=50):
        return {"entries": self.entries}

    def blocks(self, x0, y0, z0, sx, sy, sz, dim=None, timeout_ms=None):
        ids = self.world.ids_box(x0, y0, z0, x0 + sx - 1, y0 + sy - 1, z0 + sz - 1)
        pal = ["minecraft:air"] + list(self.world.palette[1:])
        hdr = json.dumps({"size": [sx, sy, sz], "origin": [x0, y0, z0], "palette": pal, "block_entities": []}).encode()
        return gzip.compress(b"USTABLK1" + struct.pack("<I", len(hdr)) + hdr + ids.astype("<u2").tobytes())

    def submit_plan(self, data, **kw):
        p = Plan.from_bytes(data)
        self.plans.append((p, kw))
        ox, oy, oz = p.origin
        for y, z, x in zip(*np.nonzero(p.cells)):
            self.world.set(ox + int(x), oy + int(y), oz + int(z), p.palette[int(p.cells[y, z, x])])
        return {"id": f"j{len(self.plans)}"}

    def job(self, jid, wait_ms=0):
        return {"id": jid, "state": "DONE"}

    def job_action(self, jid, action):
        return {"ok": True}

    def chat(self, text, kind="soft", buttons=None):
        self.chats.append(text)
        return {"ok": True}

    def world_action(self, action, body):
        self.actions.append((action, body))
        return {"ok": True, "action": action}

    def entities(self, x0, y0, z0, x1, y1, z1):
        return self.ents


def _ground(w: Build, x0=150, z0=250, x1=260, z1=360):
    w.fill(x0, 60, z0, x1, 62, z1, "minecraft:dirt")
    w.fill(x0, 63, z0, x1, 63, z1, "minecraft:grass_block")


def _hut(w: Build, x0, z0, wood="spruce_planks"):
    """9x5x7 kulube: dolu taban, oyuk ic, kapi on (-z) yuzde, sagda tek bacali asimetri."""
    w.fill(x0, 64, z0, x0 + 8, 68, z0 + 6, f"minecraft:{wood}", hollow=True)
    w.fill(x0 + 1, 65, z0 + 1, x0 + 7, 67, z0 + 5, "minecraft:air")
    w.set(x0 + 4, 65, z0, "minecraft:oak_door[facing=north,half=lower,hinge=left]")
    w.set(x0 + 4, 66, z0, "minecraft:oak_door[facing=north,half=upper,hinge=left]")
    w.fill(x0 + 7, 69, z0 + 5, x0 + 7, 71, z0 + 5, "minecraft:bricks")      # baca: x'te asimetri


def _state(w: Build, x, y, z) -> str:
    s = w.get(x, y, z)
    return "minecraft:air" if s in (None, "keep") else s


def test_survey_finds_structures_and_ignores_terrain(_gamedir):
    from usta import cevre
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    _hut(w, 220, 310, wood="oak_planks")
    w.fill(170, 64, 330, 172, 66, 332, "minecraft:oak_log")                 # dogal: yapi sayilmaz
    w.fill(160, 64, 260, 175, 64, 260, "minecraft:dirt_path")               # koy yolu: yapilari baglamaz
    api = FakeAPI(w)
    s = cevre.survey(api, 64)
    assert s["ok"] and s["count"] == 2, s
    boxes = sorted(it["box"] for it in s["structures"])
    assert boxes == [[190, 64, 270, 198, 71, 276], [220, 64, 310, 228, 71, 316]]
    first = next(it for it in s["structures"] if it["box"][0] == 190)
    assert first["size"] == [9, 8, 7] and first["top_blocks"][0][0] == "spruce_planks"
    assert first["distance"] == pytest.approx(((194 - 200.5) ** 2 + (273 - 300.5) ** 2) ** 0.5, abs=0.1)


def test_survey_with_code_is_exact(_gamedir):
    from usta import cevre
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    s = cevre.survey(FakeAPI(w), 64, with_code=True)
    code = s["structures"][0]["code"]
    assert code["exact"] is True and Path(code["file"]).exists() and code["ozet"], code


def test_copy_then_paste_in_front_same_orientation(_gamedir):
    from usta import cevre
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    api = FakeAPI(w, player=(200.5, 64.0, 300.5), facing="north")
    code, st, path = cevre.structure_code(api, [190, 64, 270, 198, 71, 276])
    assert st["exact"]
    cevre.save_clipboard(code, {"box": [190, 64, 270, 198, 71, 276]})
    plan, box = cevre.paste_plan(api)
    assert box == [196, 63, 292, 204, 70, 298]           # onunde (kuzey = -z), ortalanmis; dolu taban zemine oturur
    assert plan.world_bounds() == ((196, 63, 292), (204, 70, 298))
    cevre.submit_and_wait(api, plan, "test")
    for dx in range(9):
        for dy in range(8):
            for dz in range(7):
                assert _state(w, 196 + dx, 63 + dy, 292 + dz) == _state(w, 190 + dx, 64 + dy, 270 + dz), (dx, dy, dz)


@pytest.mark.parametrize("op,arg", [("aynala", "x"), ("aynala", "z"), ("dondur", "180")])
def test_transform_last_moves_only_artificial_blocks(_gamedir, op, arg):
    from usta import cevre
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    before = Build("once")
    for x in range(188, 201):
        for y in range(62, 73):
            for z in range(268, 279):
                before.set(x, y, z, _state(w, x, y, z))
    hist = [{"kind": "BUILD", "id": "j1", "label": "kulübe", "box": [190, 63, 270, 9, 9, 7]}]
    api = FakeAPI(w, history=hist)
    plan, box, info = cevre.transform_last(api, op, arg)
    cevre.submit_and_wait(api, plan, "test", allow_modify=True)
    for x in range(190, 199):
        for y in range(64, 72):
            for z in range(270, 277):
                mx = 190 + 198 - x if (op == "aynala" and arg == "x") or op == "dondur" else x
                mz = 270 + 276 - z if (op == "aynala" and arg == "z") or op == "dondur" else z
                want = _state(before, mx, y, mz).split("[", 1)[0]
                assert _state(w, x, y, z).split("[", 1)[0] == want, (x, y, z)
    assert _state(w, 194, 63, 273).startswith("minecraft:grass_block")    # dogal zemin yerinde
    door = _state(w, 194, 65, 270 if op != "dondur" and arg != "z" else 276)
    assert door.startswith("minecraft:oak_door") and ("facing=north" in door) == (op == "aynala" and arg == "x"), door


def test_ingame_kod_kopyala_yapistir_and_mirror(_gamedir, monkeypatch):
    from usta import ops, tools
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    api = FakeAPI(w, look=(190, 66, 272))
    monkeypatch.setattr(ops, "game", lambda: api)
    r = tools.kod(api)
    assert r["ok"] and Path(r["file"]).exists() and "birebir ✓" in api.chats[-1], api.chats
    assert tools.kopyala(api)["ok"] and "Kopyalandı" in api.chats[-1]
    r = tools.yapistir(api)
    assert r["ok"] and api.plans and api.plans[-1][1]["mode"] == "instant", api.chats
    api.entries = [{"kind": "BUILD", "id": "j9", "label": "kopya", "box": [r["box"][0], r["box"][1], r["box"][2], 9, 8, 7]}]
    assert tools.donustur(api, "dondur", "90")["ok"] and "döndürüldü" in api.chats[-1]
    assert tools.cevre_(api)["count"] >= 1 and "Çevrende" in api.chats[-2 if api.chats[-1].startswith("Harita") else -1]


def test_mcp_command_and_entity_tools(_gamedir, monkeypatch):
    from usta import mcp_server, ops
    w = Build("dunya")
    _ground(w)
    ents = [{"type": "minecraft:zombie", "x": 1}, {"type": "minecraft:zombie", "x": 2}, {"type": "minecraft:cow", "x": 3}]
    api = FakeAPI(w, ents=ents)
    monkeypatch.setattr(ops, "game", lambda: api)
    out = json.loads(mcp_server.run_game_command("give @p minecraft:diamond 3"))
    assert out["ok"] and api.actions[-1] == ("command", {"command": "give @p minecraft:diamond 3", "source": "mcp"})
    e = json.loads(mcp_server.entities(16))
    assert e["count"] == 3 and e["by_type"] == {"minecraft:zombie": 2, "minecraft:cow": 1}
    json.loads(mcp_server.remove_entities(["hostile"], radius=20))
    assert api.actions[-1] == ("entities_remove", {"types": ["hostile"], "radius": 20, "source": "mcp"})


def test_survey_area_tool_returns_list_and_image_fallback(_gamedir, monkeypatch):
    from usta import mcp_server, ops
    w = Build("dunya")
    _ground(w)
    _hut(w, 190, 270)
    api = FakeAPI(w)
    monkeypatch.setattr(ops, "game", lambda: api)
    out = mcp_server.survey_area(48)
    info = json.loads(out[0])
    assert info["ok"] and info["count"] == 1 and info["structures"][0]["box"][:3] == [190, 64, 270]
