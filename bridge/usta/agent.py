"""Basliksiz Claude kosucusu (T8): oyun ici /claude ve panel istekleri.

Mod bu sureci baslatir: python -m usta.agent --request <request.json>
- Model yonlendirici ile model secer, claude -p'yi YALNIZ usta MCP araclariyla calistirir (kabuk/dosya/web yok),
- stream-json olaylarini kisa Turkce durum satirlarina cevirip oyun sohbetine yazar (en gec ~10 sn'de bir),
- dunya basina konusma kimligini (--resume) surdurur, hatalari (giris yok, kota, internet) acik Turkce bildirir.
Kisisel ayarlar, CLAUDE.md ve otomatik hafiza yuklenmez/yazilmaz (K-06).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config, router
from .agent_guide import HEADLESS_APPEND
from .gameapi import GameAPI

STATUS = {
    "get_context": "Etrafına bakıyorum…",
    "get_status": None,
    "find_site": "Önündeki araziye uygun yer arıyorum…",
    "map_view": "Haritaya bakıyorum…",
    "kit_reference": "Araç setime bakıyorum…",
    "run_build_script": "Tasarlıyorum…",
    "generate": "Tasarlıyorum…",
    "preview_draft": "Tasarımı farklı açılardan inceliyorum…",
    "audit_draft": "Denetimden geçiriyorum…",
    "place_draft": "Kuruyorum…",
    "job_status": None,
    "undo": "Geri alıyorum…",
    "redo": "Yineliyorum…",
    "view_world": "Yapıya bakıyorum…",
    "player_screenshot": "Ekranına bakıyorum…",
    "set_time": "Saati ayarlıyorum…",
    "set_weather": "Havayı ayarlıyorum…",
    "teleport_player": "Seni ışınlıyorum…",
    "terrain": "Araziyi düzenliyorum…",
    "edit_structure": "Yapıyı düzenliyorum…",
    "furnish_room": "Odayı döşüyorum…",
}

AUTH_HINTS = ("not logged in", "please run /login", "authentication", "invalid api key", "oauth", "log in", "login required")
QUOTA_HINTS = ("usage limit", "rate limit", "limit reached", "quota", "overloaded", "5-hour limit", "weekly limit")
NET_HINTS = ("enotfound", "econnrefused", "network", "getaddrinfo", "timed out", "etimedout", "unable to connect")


def _env(game_dir: str, request_id: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    env.update({
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_TELEMETRY": "1",
        "MAX_MCP_OUTPUT_TOKENS": "25000",
        "USTA_GAME_DIR": game_dir,
        "USTA_REQUEST_ID": request_id,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    if Path(git_bash).exists():
        env["CLAUDE_CODE_GIT_BASH_PATH"] = git_bash
    return env


def build_command(claude: str, prompt: str, model: str, effort: str, mcp_cfg: Path, guide: Path, session: str | None,
                  max_turns: int = 100) -> list[str]:
    cmd = [claude, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--model", model, "--effort", effort,
           "--tools", "", "--strict-mcp-config", "--mcp-config", str(mcp_cfg),
           "--allowedTools", "mcp__usta__*",
           "--disallowedTools", "Bash,PowerShell,Edit,Write,Read,WebFetch,WebSearch,NotebookEdit,Agent,Task",
           "--setting-sources", "project", "--disable-slash-commands",
           "--append-system-prompt-file", str(guide), "--max-turns", str(max_turns)]
    if session:
        cmd += ["--resume", session]
    return cmd


class Runner:
    def __init__(self, req: dict, api: GameAPI | None):
        self.req = req
        self.api = api
        self.rid = req["id"]
        self.last_status = time.time()
        self.phase = "Düşünüyorum"
        self.n_script = 0
        self.session: str | None = None
        self.final_text: str | None = None
        self.ok = False
        self.stderr_tail: list[str] = []

    def status(self, text: str, model: str | None = None, heartbeat: bool = False) -> None:
        self.last_status = time.time()
        if not heartbeat:                       # "hala calisiyorum" satiri asamayi ezmesin (ic ice yazi olmasin)
            self.phase = text.rstrip("…").rstrip(".")
        if self.api is not None:
            try:
                self.api.agent_status(self.rid, text, model)
            except Exception:
                pass
        print(f"[durum] {text}", flush=True)

    def on_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            self.session = ev.get("session_id") or self.session
        elif t == "assistant":
            for c in (ev.get("message") or {}).get("content", []):
                if c.get("type") == "tool_use":
                    name = c.get("name", "")
                    short = name.split("__")[-1]
                    msg = STATUS.get(short, "Çalışıyorum…")
                    if short == "run_build_script":
                        self.n_script += 1
                        if self.n_script > 1:
                            msg = "Tasarımı iyileştiriyorum…"
                    if msg:
                        self.status(msg)
        elif t == "user":
            for c in (ev.get("message") or {}).get("content", []):
                if c.get("type") == "tool_result":
                    self._tool_result(c)
        elif t == "result":
            self.session = ev.get("session_id") or self.session
            self.ok = ev.get("subtype") == "success" and not ev.get("is_error")
            self.final_text = ev.get("result") or ""

    def _tool_result(self, c: dict) -> None:
        content = c.get("content")
        text = ""
        if isinstance(content, list):
            for x in content:
                if isinstance(x, dict) and x.get("type") == "text":
                    text = x.get("text", "")
                    break
        elif isinstance(content, str):
            text = content
        if not text.startswith("{"):
            return
        try:
            d = json.loads(text)
        except Exception:
            return
        if d.get("ok") is False and d.get("message"):
            self.status("Sorun: " + str(d["message"])[:160])

    def events_loop(self, stop: threading.Event) -> None:
        """Modun olay akisindan bu istegin islerini izler: kurulum basladi / ilerleme / onay bekleniyor."""
        if self.api is None:
            return
        try:
            since = int(self.api.events(0, 0).get("last", 0))
        except Exception:
            return
        last_prog = 0.0
        while not stop.is_set():
            try:
                r = self.api.events(since, 5000)
            except Exception:
                if stop.wait(2.0):
                    return
                continue
            since = int(r.get("last", since))
            for ev in r.get("events", []):
                d = ev.get("data", {})
                if d.get("request") != self.rid:
                    continue
                t = ev.get("type")
                if t == "job_started" and d.get("kind") == "BUILD":
                    secs = d.get("seconds") or 0
                    eta = f", ≈{int(secs)} sn" if secs else ""
                    self.status(f"Kuruluyor: {int(d.get('total', 0)):,} blok{eta}.".replace(",", "."))
                    last_prog = time.time()
                elif t == "job_progress" and time.time() - last_prog > 8:
                    self.status(f"İnşa %{int(float(d.get('progress', 0)) * 100)}…")
                    last_prog = time.time()
                elif t == "job_awaiting_confirm":
                    self.status("Büyük silme onayın bekleniyor: sohbetteki [Onayla] düğmesine tıkla.")
                elif t == "job_failed":
                    self.status("Kurulamadı: " + str(d.get("message", ""))[:160])

    def heartbeat_loop(self, stop: threading.Event) -> None:
        t0 = time.time()
        while not stop.wait(1.0):
            age = time.time() - t0
            gap = 9.0 if age < 60 else 30.0 if age < 300 else 60.0     # uzun islerde sohbeti doldurma
            if time.time() - self.last_status > gap:
                m = int(age // 60)
                self.status(f"Hâlâ çalışıyorum: {self.phase[:1].lower() + self.phase[1:]}" + (f" ({m} dk)" if m else "") + "…",
                            heartbeat=True)


def classify_error(text: str) -> str | None:
    t = text.lower()
    claude = config.claude_exe() or r"%USERPROFILE%\.local\bin\claude.exe"
    if any(h in t for h in AUTH_HINTS):
        return f"Claude girişi yok. Bir kez şu komutu çalıştırıp giriş yap: \"{claude}\" auth login"
    if any(h in t for h in QUOTA_HINTS):
        return "Claude kullanım kotası şu an dolu; kota sıfırlanınca tekrar dene."
    if any(h in t for h in NET_HINTS):
        return "İnternete bağlanılamadı; bağlantını kontrol edip tekrar dene."
    return None


def run(req: dict) -> int:
    game_dir = req.get("game_dir") or str(config.game_dir())
    os.environ["USTA_GAME_DIR"] = game_dir
    try:
        api = GameAPI()
    except Exception:
        api = None
    r = Runner(req, api)
    from . import stadyum
    if api and stadyum.istek_mi(req["text"]):          # hizli yol: /usta stadyum -> hazir dev stadyum, Claude'suz
        force = stadyum.zorla_mi(req["text"])
        api.agent_status(r.rid, "Usta Arena önüne kuruluyor (14,4 milyon blok)" + (", zorla" if force else "") + "…")
        try:
            ok, msg = stadyum.kur_onume(game_dir, req.get("anchor"), force=force,
                                        say=lambda t: api.agent_status(r.rid, t))
        except Exception as e:
            ok, msg = False, f"Stadyum kurulamadı: {e}"
        api.agent_done(r.rid, ok, msg, r.session)
        return 0 if ok else 1
    model, text, why = router.choose(req["text"], req.get("model_pref", "auto"))
    forced_effort = router.parse_prefix(req["text"])[2]          # !dusuk/!orta/!yuksek/!cokyuksek/!max
    effort = forced_effort or router.effort_for(model, why)
    model_tr = router.display_name(model) + (f", {router.EFFORT_TR[effort]} düşünme" if forced_effort else "")
    work = Path.cwd()
    py = sys.executable
    if py.lower().endswith("pythonw.exe"):
        py = py[:-len("pythonw.exe")] + "python.exe"
    bridge_root = str(Path(__file__).resolve().parents[1])
    mcp_cfg = work / "mcp.json"
    mcp_cfg.write_text(json.dumps({"mcpServers": {"usta": {
        "command": py, "args": ["-m", "usta.mcp_server"],
        "env": {"USTA_GAME_DIR": game_dir, "USTA_REQUEST_ID": r.rid, "PYTHONPATH": bridge_root, "PYTHONIOENCODING": "utf-8"}}}},
        ensure_ascii=False), encoding="utf-8")
    guide = work / "rehber.txt"
    guide.write_text(HEADLESS_APPEND, encoding="utf-8")
    anc = req.get("anchor", {})
    prompt = (f"Oyuncunun isteği: {text}\n"
              f"(İstek anındaki çapa: x={anc.get('x')}, y={anc.get('y')}, z={anc.get('z')}, yaw={anc.get('yaw')}, "
              f"bakış={anc.get('facing')}, boyut={anc.get('dim')}. Kaynak: {req.get('source')}.)")
    mock = os.environ.get("USTA_MOCK_CLAUDE") == "1" or config.bridge_json().get("mock_claude")
    if mock:
        claude = [py, "-m", "usta.mock_claude"]
    else:
        exe = config.claude_exe()
        if not exe:
            msg = "Claude Code aracı bulunamadı; KUR.bat'ı yeniden çalıştır."
            if api:
                api.agent_done(r.rid, False, msg)
            return 2
        claude = [exe]
    cmd = claude + build_command("", prompt, model, effort, mcp_cfg, guide, req.get("session"))[1:]
    r.status(f"Claude ({model_tr}) düşünüyor…", model)
    env = _env(game_dir, r.rid)
    env["PYTHONPATH"] = bridge_root
    t0 = time.time()
    stop = threading.Event()
    hb = threading.Thread(target=r.heartbeat_loop, args=(stop,), daemon=True)
    hb.start()
    threading.Thread(target=r.events_loop, args=(stop,), daemon=True).start()
    try:
        p = subprocess.Popen(cmd, cwd=str(work), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except FileNotFoundError as e:
        stop.set()
        if api:
            api.agent_done(r.rid, False, f"Claude başlatılamadı: {e}")
        return 2
    errq: "queue.Queue[str]" = queue.Queue()

    def pump_err():
        for line in iter(p.stderr.readline, b""):
            s = line.decode("utf-8", "replace").rstrip()
            errq.put(s)
            r.stderr_tail.append(s)
            del r.stderr_tail[:-40]
    threading.Thread(target=pump_err, daemon=True).start()
    raw_log = (config.logs_dir() / f"agent-{r.rid}.jsonl").open("w", encoding="utf-8")
    for line in iter(p.stdout.readline, b""):
        s = line.decode("utf-8", "replace").strip()
        if not s:
            continue
        raw_log.write(s + "\n")
        try:
            ev = json.loads(s)
        except json.JSONDecodeError:
            r.stderr_tail.append(s)
            continue
        r.on_event(ev)
    p.wait()
    raw_log.close()
    stop.set()
    dt = time.time() - t0
    meta = {"model": model, "effort": effort, "reason": why, "seconds": round(dt, 1), "exit": p.returncode, "session": r.session}
    (work / "sonuc.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    final = (r.final_text or "").strip()
    if not r.ok:
        err = classify_error(final + "\n" + "\n".join(r.stderr_tail))
        msg = err or (final[:300] if final else "İstek tamamlanamadı (ayrıntı: usta/logs).")
        if api:
            api.agent_done(r.rid, False, msg, r.session)
        return 1
    if len(final) > 400:
        final = final[:400].rsplit(" ", 1)[0] + "…"
    if api:
        api.agent_done(r.rid, True, final or "Bitti.", r.session)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    a = ap.parse_args()
    req = json.loads(Path(a.request).read_text(encoding="utf-8"))
    sys.exit(run(req))


if __name__ == "__main__":
    main()
