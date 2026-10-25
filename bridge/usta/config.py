"""Yollar ve yapilandirma. Oyun klasoru: USTA_GAME_DIR > kopru config.json > %APPDATA%\\.usta"""
from __future__ import annotations

import json
import os
from pathlib import Path

MC = "26.3"
BRIDGE_ROOT = Path(__file__).resolve().parent.parent


def _bridge_config() -> dict:
    for p in (BRIDGE_ROOT / "config.json", BRIDGE_ROOT.parent / "config.json"):
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def game_dir() -> Path:
    env = os.environ.get("USTA_GAME_DIR")
    if env:
        return Path(env)
    cfg = _bridge_config()
    if cfg.get("game_dir"):
        return Path(cfg["game_dir"])
    if (Path.home() / "UstaOyun").exists():       # Store launcher'i AppData'daki disaridan dosyalari gormez: klasor AppData disinda
        return Path.home() / "UstaOyun"
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(appdata) / ".usta"


def data_dir() -> Path:
    return game_dir() / "usta"


def discovery_file() -> Path:
    return data_dir() / "runtime" / "api.json"


def cache_dir() -> Path:
    p = data_dir() / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def work_dir() -> Path:
    p = data_dir() / "calisma"
    p.mkdir(parents=True, exist_ok=True)
    return p


def renders_dir() -> Path:
    p = data_dir() / "gorseller"
    p.mkdir(parents=True, exist_ok=True)
    return p


def library_dir() -> Path:
    p = data_dir() / "kutuphane"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def bridge_json() -> dict:
    p = data_dir() / "bridge.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def claude_exe() -> str | None:
    cfg = bridge_json()
    if cfg.get("claude") and Path(cfg["claude"]).exists():
        return cfg["claude"]
    cand = Path.home() / ".local" / "bin" / "claude.exe"
    if cand.exists():
        return str(cand)
    from shutil import which
    return which("claude")
