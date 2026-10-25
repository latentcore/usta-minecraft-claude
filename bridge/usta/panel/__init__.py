"""Tarayici paneli (U8): yalniz 127.0.0.1. Erisim: tek kullanimlik giris kodu -> HttpOnly + SameSite=Strict cerez
(adres cubugunda anahtar kalmaz). Yazma istekleri ayrica CSRF basligi + Origin denetimi ister.
Calistirma: python -m usta.panel [--open]   (oyun icinden: /usta panel)"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .. import config

DEFAULT_PORT = 47860


def runtime_file() -> Path:
    return config.data_dir() / "runtime" / "panel.json"


def _restrict(path: Path) -> None:
    try:
        user = os.environ.get("USERNAME")
        if user:
            subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"], capture_output=True, creationflags=0x08000000)
    except Exception:
        pass


def _running() -> dict | None:
    f = runtime_file()
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{d['port']}/_alive", headers={"X-Usta-Master": d["master"]})
        with urllib.request.urlopen(req, timeout=2) as r:
            if r.status == 200:
                return d
    except Exception:
        return None
    return None


def ensure_running_and_login_url() -> str:
    d = _running()
    if d is None:
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        exe = str(pyw if pyw.exists() else py)
        env = dict(os.environ)
        env.setdefault("USTA_GAME_DIR", str(config.game_dir()))
        bridge_root = str(Path(__file__).resolve().parents[2])
        env["PYTHONPATH"] = bridge_root + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.Popen([exe, "-m", "usta.panel", "--serve"], cwd=bridge_root, env=env, creationflags=0x08000000 | 0x00000008,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(0.25)
            d = _running()
            if d:
                break
        if d is None:
            raise RuntimeError("panel başlatılamadı")
    req = urllib.request.Request(f"http://127.0.0.1:{d['port']}/_code", headers={"X-Usta-Master": d["master"]}, method="POST")
    with urllib.request.urlopen(req, timeout=3) as r:
        code = json.loads(r.read())["code"]
    return f"http://127.0.0.1:{d['port']}/giris?k={code}"


def main() -> None:
    if "--serve" in sys.argv:
        from .server import serve
        serve()
        return
    url = ensure_running_and_login_url()
    if "--open" in sys.argv:
        import webbrowser
        webbrowser.open(url)
    print(url)


def new_master() -> str:
    return secrets.token_hex(24)
