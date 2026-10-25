"""DURUM: saglik kontrolu — her satir YESIL ya da KIRMIZI + oyuncunun yapacagi tek adim."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kur  # noqa: E402

G, R, Y, N = "\x1b[32m", "\x1b[31m", "\x1b[33m", "\x1b[0m"
if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
    G = R = Y = N = ""


def line(ok: bool | None, name: str, detail: str = "", fix: str = "") -> bool:
    mark = f"{G}[YEŞİL]{N}" if ok else (f"{Y}[SARI] {N}" if ok is None else f"{R}[KIRMIZI]{N}")
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
    if not ok and fix:
        print(f"         yapılacak: {fix}")
    return bool(ok)


def main() -> int:
    allok = True
    allok &= line(kur.MC.exists(), "Minecraft kurulumu", str(kur.MC), "Minecraft Launcher ile Java Edition'ı kur.")
    allok &= line((kur.MC / "versions" / kur.FABRIC_VERSION_ID).exists(), f"Fabric {kur.LOADER} ({kur.MC_VERSION})", "", "KUR.bat'ı çalıştır.")
    pf = kur.profile_file()
    has_prof = False
    try:
        has_prof = kur.PROFILE_KEY in json.loads(pf.read_text(encoding="utf-8")).get("profiles", {})
    except Exception:
        pass
    allok &= line(has_prof, "Launcher profili 'Usta (Claude)'", pf.name, "Launcher'ı kapat ve KUR.bat'ı yeniden çalıştır.")
    mods = kur.GAME / "mods"
    names = [p.name for p in mods.glob("*.jar")] if mods.exists() else []
    need = ["usta-", "fabric-api", "sodium", "lithium", "ferritecore"]
    miss = [n for n in need if not any(x.lower().startswith(n) for x in names)]
    allok &= line(not miss, "Modlar", ", ".join(names) if names else "yok", "KUR.bat'ı çalıştır." + (f" Eksik: {miss}" if miss else ""))
    py = kur.BRIDGE_DST / "venv" / "Scripts" / "python.exe"
    br_ok = False
    if py.exists():
        r = subprocess.run([str(py), "-c", "import usta.mcp_server, numpy, PIL; print('ok')"], capture_output=True, text=True,
                           cwd=str(Path.home()), creationflags=0x08000000)     # MCP gibi: cwd'den bagimsiz bulunmali
        br_ok = "ok" in r.stdout
    allok &= line(br_ok, "Köprü (MCP sunucusu)", str(kur.BRIDGE_DST), "KUR.bat'ı çalıştır.")
    claude = Path.home() / ".local" / "bin" / "claude.exe"
    allok &= line(claude.exists(), "Claude Code aracı", str(claude), "KUR.bat yükleyiciyi gösterir; ya da: irm https://claude.ai/install.ps1 | iex")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    if claude.exists():
        g = subprocess.run([str(claude), "mcp", "get", "usta"], capture_output=True, text=True, env=env, creationflags=0x08000000)
        conn = g.returncode == 0 and "usta.mcp_server" in g.stdout and "Connected" in g.stdout and "Failed" not in g.stdout
        allok &= line(conn, "MCP kaydı (kullanıcı kapsamı, bağlantı)", "", "KUR.bat'ı çalıştır.")
        a = subprocess.run([str(claude), "auth", "status", "--text"], capture_output=True, text=True, env=env, creationflags=0x08000000)
        logged = a.returncode == 0
        allok &= line(logged, "Claude girişi", (a.stdout or a.stderr).strip().splitlines()[0] if (a.stdout or a.stderr).strip() else "",
                      f'"{claude}" auth login')
    api = kur.DATA / "runtime" / "api.json"
    game_open = None
    if api.exists():
        try:
            sys.path.insert(0, str(kur.BRIDGE_DST))
            os.environ["USTA_GAME_DIR"] = str(kur.GAME)
            from usta.gameapi import GameAPI
            p = GameAPI().ping()
            game_open = True
            line(True, "Oyun açık ve Usta hazır", f"dünya {p.get('world')}")
        except Exception:
            game_open = None
    if game_open is None:
        line(None, "Oyun", "şu an açık değil (bu normal; oyunu açınca Usta otomatik hazırlanır)")
    print("")
    print("Sonuç: " + ("her şey hazır." if allok else "KIRMIZI satırlardaki tek adımı yap, sonra DURUM.bat'ı yeniden çalıştır."))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
