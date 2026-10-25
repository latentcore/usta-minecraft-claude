"""Panel sunucusu (stdlib http.server). Yalniz 127.0.0.1; cerez + CSRF + Host/Origin denetimi."""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import config, ops
from ..gameapi import GameAPI, GameError, GameNotRunning
from . import DEFAULT_PORT, _restrict, new_master, runtime_file

STATIC = Path(__file__).parent / "static"
MASTER = new_master()
SESSIONS: dict[str, dict] = {}  # sid -> {"csrf":..., "t":...}
CODES: dict[str, float] = {}
LOCK = threading.Lock()
TOKEN_RE = re.compile(r"[0-9a-f]{40,}")


def _mask(s: str) -> str:
    return TOKEN_RE.sub("***", s)


class H(BaseHTTPRequestHandler):
    server_version = "UstaPanel/0.1"

    def log_message(self, fmt, *args):  # gunluge anahtar dusmesin
        pass

    # ------------------------------------------------------------------ yardimcilar
    def _host_ok(self) -> bool:
        h = self.headers.get("Host", "")
        port = self.server.server_address[1]
        return h in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _origin_ok(self) -> bool:
        o = self.headers.get("Origin")
        if o is None:
            return True
        port = self.server.server_address[1]
        return o in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _session(self) -> dict | None:
        c = SimpleCookie(self.headers.get("Cookie", ""))
        sid = c.get("usta_sid")
        if not sid:
            return None
        with LOCK:
            s = SESSIONS.get(sid.value)
        return s

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n > 2_000_000:
            return {}
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    # ------------------------------------------------------------------ yonlendirme
    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method: str) -> None:
        if not self._host_ok():
            return self._json({"error": "host"}, 403)
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, dict(urllib.parse.parse_qsl(u.query))
        # ic uclar (yalniz ana anahtarla: oyundaki /usta panel ve PANEL.bat)
        if path in ("/_alive", "/_code"):
            if not hmac.compare_digest(self.headers.get("X-Usta-Master", ""), MASTER):
                return self._json({"error": "auth"}, 401)
            if path == "/_alive":
                return self._json({"ok": True})
            code = secrets.token_urlsafe(18)
            with LOCK:
                CODES[code] = time.time() + 120
            return self._json({"code": code})
        if path == "/giris":
            code = q.get("k", "")
            with LOCK:
                exp = CODES.pop(code, 0)
            if exp < time.time():
                return self._send(403, "Giriş kodu geçersiz ya da süresi doldu. Oyunda /usta panel ya da PANEL.bat ile yeniden aç.".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            sid = secrets.token_hex(24)
            csrf = secrets.token_hex(16)
            with LOCK:
                SESSIONS[sid] = {"csrf": csrf, "t": time.time()}
            # adres cubugunda kod kalmasin: hemen yonlendir
            return self._send(303, b"", "text/plain", {"Location": "/", "Set-Cookie": f"usta_sid={sid}; HttpOnly; SameSite=Strict; Path=/"})
        sess = self._session()
        if sess is None:
            return self._send(401, "Panel oturumu yok. Oyunda /usta panel ya da PANEL.bat ile aç.".encode("utf-8"), "text/plain; charset=utf-8")
        if method != "GET":
            if not self._origin_ok() or not hmac.compare_digest(self.headers.get("X-Usta-CSRF", ""), sess["csrf"]):
                return self._json({"error": "csrf"}, 403)
        if path == "/" or path == "/index.html":
            html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__CSRF__", sess["csrf"])
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if STATIC.resolve() not in f.parents or not f.exists():
                return self._json({"error": "yok"}, 404)
            ctype = "application/javascript; charset=utf-8" if f.suffix == ".js" else "text/css; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype)
        try:
            return self._api(method, path, q)
        except GameNotRunning as e:
            return self._json({"ok": False, "game": "closed", "message": str(e)}, 200)
        except GameError as e:
            return self._json({"ok": False, **e.payload}, 200)
        except Exception as e:  # noqa: BLE001
            return self._json({"ok": False, "message": _mask(f"{type(e).__name__}: {e}")}, 500)

    def _api(self, method: str, path: str, q: dict) -> None:
        if path == "/api/status":
            return self._json(ops.status())
        if path == "/api/map.json" or path == "/api/map.jpg":
            r = int(q.get("r", "96"))
            cx, cz = q.get("cx"), q.get("cz")
            center = (int(cx), int(cz)) if cx and cz else None
            info, data, _ = ops.map_view(center, r)
            if path.endswith(".jpg"):
                return self._send(200, data, "image/jpeg")
            return self._json(info)
        if path == "/api/request" and method == "POST":
            b = self._body()
            text = (b.get("text") or "").strip()[:500]
            if not text:
                return self._json({"ok": False, "message": "boş istek"})
            return self._json(GameAPI().agent_request(text, "panel"))
        if path == "/api/agent":
            return self._json(GameAPI().agent_state())
        if path == "/api/agent/cancel" and method == "POST":
            return self._json(GameAPI().agent_cancel())
        if path == "/api/events":
            since = int(q.get("since", "0"))
            return self._json(GameAPI().events(since, 20000))
        if path == "/api/jobs":
            return self._json(GameAPI().jobs())
        m = re.fullmatch(r"/api/job/([\w-]+)/(cancel|pause|resume|confirm|speed)", path)
        if m and method == "POST":
            b = self._body()
            return self._json(GameAPI().job_action(m.group(1), m.group(2), b.get("seconds")))
        if path == "/api/history":
            return self._json(GameAPI().history(int(q.get("limit", "40"))))
        m = re.fullmatch(r"/api/history/([\w-]+)/(before|after)\.jpg", path)
        if m:
            return self._send(200, _thumb(m.group(1), m.group(2)), "image/jpeg")
        m = re.fullmatch(r"/api/history/([\w-]+)/materials", path)
        if m:
            from .. import jobdata
            api = GameAPI()
            return self._json({"materials": jobdata.materials(jobdata.load(api.world, m.group(1)))[:40]})
        if path == "/api/undo" and method == "POST":
            return self._json(ops.undo(self._body().get("id")))
        if path == "/api/redo" and method == "POST":
            return self._json(ops.redo(self._body().get("id")))
        if path == "/api/library":
            from .. import library
            return self._json({"items": library.list_items()})
        m = re.fullmatch(r"/api/library/([\w-]+)/preview\.jpg", path)
        if m:
            p = config.library_dir() / m.group(1) / "onizleme.jpg"
            return self._send(200, p.read_bytes() if p.exists() else b"", "image/jpeg")
        m = re.fullmatch(r"/api/library/([\w-]+)/place", path)
        if m and method == "POST":
            return self._json(place_library_item(m.group(1), self._body()))
        m = re.fullmatch(r"/api/library/([\w-]+)", path)
        if m and method == "DELETE":
            from .. import library
            return self._json({"ok": library.delete(m.group(1))})
        if path == "/api/protected":
            api = GameAPI()
            if method == "POST":
                return self._json(api.protect(self._body()))
            return self._json(api.protected())
        if path == "/api/settings":
            api = GameAPI()
            return self._json(api.settings(self._body() if method == "POST" else None))
        if path == "/api/health":
            return self._json(health())
        if path == "/api/logs":
            return self._json({"lines": tail_logs()})
        return self._json({"error": "yok"}, 404)


def _thumb(job_id: str, which: str) -> bytes:
    from .. import jobdata
    from ..render.sheet import fit, to_jpeg_bytes
    from ..render.views import Volume, iso
    api = GameAPI()
    d = jobdata.load(api.world, job_id)
    after, before = jobdata.volumes(d)
    v = after if which == "after" else before
    if v is None:
        from PIL import Image
        return to_jpeg_bytes(Image.new("RGB", (8, 8), (230, 230, 230)))
    ids, names = v
    names = [("keep" if n in ("minecraft:air", "minecraft:cave_air") else n) for n in names]
    im = iso(Volume(ids, names), "se", max_px=420)
    return to_jpeg_bytes(fit(im, 420, 300), max_side=420)


def place_library_item(item_id: str, body: dict) -> dict:
    from .. import library
    plan = library.load_plan(item_id)
    sx, sy, sz = plan.size
    info, _, _ = ops.site_candidates(sx, sz, body.get("where", "front"))
    c = (info.get("candidates") or [None])[0]
    if not c:
        return {"ok": False, "message": info.get("message", "uygun yer yok")}
    from ..plan import Plan
    times = ("north", "east", "south", "west").index(c["facing"])
    from ..kit.core import Build
    b = Build(plan.meta.get("name", item_id))
    b.put_ids(0, 0, 0, plan.cells, plan.palette)
    for be in plan.block_entities:
        b.set_block_entity(*be["pos"], be["snbt"])
    p2: Plan = b.to_plan(tuple(c["origin"]), c["facing"])
    dr = ops.new_draft(p2, plan.meta.get("name", item_id), "library")
    return ops.place(dr.id, body.get("mode", "watch"), body.get("seconds"))


def health() -> dict:
    out = {"game": ops.status().get("game")}
    out["colors_table"] = (config.cache_dir() / f"colors-{config.MC}.json.gz").exists()
    out["blockdb"] = (config.cache_dir() / f"blockdb-{config.MC}.json.gz").exists()
    out["bridge_json"] = bool(config.bridge_json())
    out["claude_exe"] = config.claude_exe()
    return out


def tail_logs(n: int = 80) -> list[str]:
    lines: list[str] = []
    d = config.logs_dir()
    for f in sorted(d.glob("*.log"), key=lambda p: p.stat().st_mtime)[-3:]:
        try:
            lines += [f"[{f.name}] " + _mask(x) for x in f.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]]
        except Exception:
            pass
    return lines[-n:]


def serve() -> None:
    port = DEFAULT_PORT
    httpd = None
    for p in range(DEFAULT_PORT, DEFAULT_PORT + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", p), H)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        raise SystemExit("panel portu bulunamadı")
    f = runtime_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        f.unlink()
    f.write_text("{}", encoding="utf-8")
    _restrict(f)
    f.write_text(json.dumps({"port": port, "master": MASTER, "pid": os.getpid()}), encoding="utf-8")
    try:
        httpd.serve_forever()
    finally:
        try:
            f.unlink()
        except Exception:
            pass
