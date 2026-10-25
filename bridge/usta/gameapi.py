"""Oyun API'si istemcisi (yalniz 127.0.0.1). Anahtar hicbir yere yazdirilmaz."""
from __future__ import annotations

import http.client
import json
import socket
import urllib.parse
from typing import Any

from . import config


class GameNotRunning(Exception):
    """Oyun kapali ya da Usta'li bir dunya yuklu degil."""

    def __init__(self, detail: str = ""):
        msg = ("Minecraft açık değil ya da Usta'lı tek oyunculu bir dünya yüklü değil. "
               "Launcher'da 'Usta' profilini seçip bir dünyaya gir, sonra tekrar dene.")
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class GameError(Exception):
    def __init__(self, status: int, payload: dict):
        self.status = status
        self.payload = payload
        super().__init__(payload.get("message") or payload.get("error") or f"HTTP {status}")


class GameAPI:
    def __init__(self, timeout: float = 15.0):
        f = config.discovery_file()
        if not f.exists():
            raise GameNotRunning("api.json yok")
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover
            raise GameNotRunning(f"api.json okunamadı: {e}")
        self.port = int(d["port"])
        self._token = d["token"]
        self.world = d.get("world")
        self.timeout = timeout

    def __repr__(self) -> str:  # anahtar asla gorunmez
        return f"GameAPI(port={self.port}, world={self.world})"

    def _request(self, method: str, path: str, body: bytes | None = None, query: dict | None = None,
                 timeout: float | None = None, content_type: str = "application/json") -> tuple[int, bytes, str]:
        if query:
            path = path + "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout or self.timeout)
        headers = {"Authorization": f"Bearer {self._token}", "Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            headers["Content-Type"] = content_type
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            data = r.read()
            return r.status, data, r.getheader("Content-Type", "")
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            if isinstance(e, socket.timeout):
                raise GameError(504, {"error": "timeout", "message": "Oyun yanıt vermedi (duraklatılmış ya da meşgul olabilir)"})
            raise GameNotRunning(str(e))
        finally:
            conn.close()

    def _json(self, method: str, path: str, payload: Any = None, query: dict | None = None, timeout: float | None = None,
              ok_codes: tuple = (200,)) -> dict:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, data, ctype = self._request(method, path, body, query, timeout)
        try:
            obj = json.loads(data.decode("utf-8")) if data else {}
        except Exception:
            obj = {"raw": data[:200].decode("utf-8", "replace")}
        if status not in ok_codes:
            raise GameError(status, obj)
        return obj

    def _bytes(self, method: str, path: str, payload: Any = None, timeout: float | None = None) -> bytes:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        status, data, ctype = self._request(method, path, body, None, timeout)
        if status != 200:
            try:
                raise GameError(status, json.loads(data.decode("utf-8")))
            except json.JSONDecodeError:
                raise GameError(status, {"message": data[:200].decode("utf-8", "replace")})
        return data

    # ---- uclar
    def ping(self) -> dict:
        return self._json("GET", "/v1/ping", timeout=5)

    def status(self) -> dict:
        return self._json("GET", "/v1/status")

    def context(self, radius: int = 48) -> dict:
        return self._json("GET", "/v1/context", query={"radius": radius})

    def columns(self, x0: int, z0: int, x1: int, z1: int, dim: str | None = None, timeout_ms: int = 4000) -> bytes:
        p = {"x0": x0, "z0": z0, "x1": x1, "z1": z1, "timeout_ms": timeout_ms}
        if dim:
            p["dim"] = dim
        return self._bytes("POST", "/v1/region/columns", p, timeout=timeout_ms / 1000 + 20)

    def blocks(self, x0: int, y0: int, z0: int, sx: int, sy: int, sz: int, dim: str | None = None, timeout_ms: int = 4000,
               generate: bool = False) -> bytes:
        p = {"x0": x0, "y0": y0, "z0": z0, "sx": sx, "sy": sy, "sz": sz, "timeout_ms": timeout_ms, "generate": generate}
        if dim:
            p["dim"] = dim
        return self._bytes("POST", "/v1/region/blocks", p, timeout=timeout_ms / 1000 + 40)

    def entities(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, nbt: bool = False, dim: str | None = None) -> list:
        p = {"x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1, "nbt": nbt}
        if dim:
            p["dim"] = dim
        return self._json("POST", "/v1/region/entities", p).get("entities", [])

    def blockdb_bytes(self) -> bytes:
        return self._bytes("GET", "/v1/blockdb", timeout=60)

    def validate_plan(self, plan_bytes: bytes, dim: str | None = None) -> dict:
        status, data, _ = self._request("POST", "/v1/plan/validate", plan_bytes, {"dim": dim}, 60, "application/octet-stream")
        return json.loads(data.decode("utf-8"))

    def submit_plan(self, plan_bytes: bytes, **query) -> dict:
        q = {k: (("1" if v else "0") if isinstance(v, bool) else v) for k, v in query.items() if v is not None}
        status, data, _ = self._request("POST", "/v1/jobs", plan_bytes, q, 120, "application/octet-stream")
        obj = json.loads(data.decode("utf-8")) if data else {}
        if status not in (200,):
            raise GameError(status, obj)
        return obj

    def job(self, job_id: str, wait_ms: int = 0) -> dict:
        return self._json("GET", f"/v1/jobs/{job_id}", query={"wait": wait_ms}, timeout=wait_ms / 1000 + 15)

    def jobs(self) -> dict:
        return self._json("GET", "/v1/jobs")

    def job_action(self, job_id: str, action: str, seconds: float | None = None) -> dict:
        return self._json("POST", f"/v1/jobs/{job_id}/{action}", {}, query={"seconds": seconds})

    def history(self, limit: int = 50) -> dict:
        return self._json("GET", "/v1/history", query={"limit": limit})

    def undo(self, job_id: str | None = None, force: bool = False) -> dict:
        return self._json("POST", "/v1/undo", {"id": job_id, "force": force}, ok_codes=(200, 409))

    def redo(self, job_id: str | None = None) -> dict:
        return self._json("POST", "/v1/redo", {"id": job_id}, ok_codes=(200, 409))

    def chat(self, text: str, kind: str = "line", buttons: list | None = None) -> dict:
        return self._json("POST", "/v1/chat", {"text": text, "kind": kind, "buttons": buttons or []})

    def events(self, since: int = 0, wait_ms: int = 0) -> dict:
        return self._json("GET", "/v1/events", query={"since": since, "wait": wait_ms}, timeout=wait_ms / 1000 + 10)

    def screenshot(self, max_width: int = 1280) -> dict:
        return self._json("POST", "/v1/screenshot", {"max_width": max_width}, timeout=20)

    def colors(self) -> dict:
        return self._json("GET", "/v1/colors", timeout=90)

    def settings(self, update: dict | None = None) -> dict:
        if update:
            return self._json("POST", "/v1/settings", update)
        return self._json("GET", "/v1/settings")

    def protected(self) -> dict:
        return self._json("GET", "/v1/protected")

    def protect(self, region: dict) -> dict:
        return self._json("POST", "/v1/protected", region)

    def world_action(self, action: str, body: dict) -> dict:
        return self._json("POST", f"/v1/world/{action}", body, ok_codes=(200, 409))

    def agent_request(self, text: str, source: str = "panel") -> dict:
        return self._json("POST", "/v1/agent/request", {"text": text, "source": source})

    def agent_get(self, request_id: str) -> dict:
        return self._json("GET", f"/v1/agent/request/{request_id}", {})

    def agent_status(self, request_id: str, text: str, model: str | None = None) -> dict:
        body = {"request": request_id, "text": text}
        if model:
            body["model"] = model
        return self._json("POST", "/v1/agent/status", body)

    def agent_done(self, request_id: str, ok: bool, text: str, session: str | None = None) -> dict:
        return self._json("POST", "/v1/agent/done", {"request": request_id, "ok": ok, "text": text, "session": session})

    def agent_cancel(self, request_id: str | None = None) -> dict:
        return self._json("POST", "/v1/agent/cancel", {"request": request_id} if request_id else {})

    def agent_state(self) -> dict:
        return self._json("GET", "/v1/agent/state", {})

    def dev_command(self, command: str) -> dict:
        return self._json("POST", "/v1/dev/command", {"command": command})


def try_api() -> GameAPI | None:
    try:
        api = GameAPI()
        api.ping()
        return api
    except Exception:
        return None
