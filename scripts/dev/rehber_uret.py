"""AJAN_REHBERI.md ve README'deki komut tablosunu TEK KAYNAKTAN uretir:
bridge/usta/agent_guide.py (talimat), bridge/usta/mcp_server.py (araclar), bridge/usta/komutlar.py (oyun ici komutlar).
Kullanim: bridge/.venv/Scripts/python.exe scripts/dev/rehber_uret.py [--kontrol]   (--kontrol: yazmaz, fark varsa 1 doner)"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bridge"))

from usta import komutlar  # noqa: E402
from usta.agent_guide import HEADLESS_APPEND, INSTRUCTIONS  # noqa: E402

REHBER = ROOT / "AJAN_REHBERI.md"
BAS = "<!-- komutlar:başla — scripts/dev/rehber_uret.py üretir, elle düzenleme -->"
SON = "<!-- komutlar:bitir -->"
# komut tablosunun durdugu Turkce README (herkese acik depoda README_TR.md, ozel depoda README.md)
README = next((p for p in (ROOT / "README_TR.md", ROOT / "README.md") if p.exists() and BAS in p.read_text(encoding="utf-8")),
              ROOT / "README.md")


def araclar() -> list[tuple[str, str]]:
    from usta import mcp_server
    return [(t.name, t.description) for t in mcp_server.server._tool_manager.list_tools()]


def rehber_metni() -> str:
    ar = araclar()
    satir = ["# AJAN_REHBERI — Claude'un Usta'da izlediği talimatlar", "",
             "> Bu dosya üretilir: `bridge/.venv/Scripts/python.exe scripts/dev/rehber_uret.py`. Elle düzenleme; kaynağı düzenle:",
             "> talimat `bridge/usta/agent_guide.py`, araçlar `bridge/usta/mcp_server.py`, oyun içi komutlar `bridge/usta/komutlar.py`.",
             "> `bridge/tests/test_tutarlilik.py` bu dosyanın, README'nin ve oyun içi yardımın kaynakla aynı olduğunu denetler.", "",
             "## Talimat (MCP sunucusu her oturumda Claude'a verir)", "", "```text", INSTRUCTIONS.rstrip("\n"), "```", "",
             "## Oyun içinden gelen koşulara ek talimat", "", "```text", HEADLESS_APPEND.rstrip("\n"), "```", "",
             f"## Araçlar ({len(ar)})", "", "| araç | ne yapar |", "|---|---|"]
    for name, desc in ar:
        satir.append(f"| `{name}` | {' '.join(desc.split()).replace('|', chr(92) + '|')} |")
    satir += ["", "## Oyun içi komutlar", "", komutlar.tablo(), ""]
    return "\n".join(satir)


def readme_metni(text: str) -> str:
    i, j = text.find(BAS), text.find(SON)
    if i < 0 or j < i:
        raise SystemExit("README'de komut tablosu işaretleri yok")
    return text[:i] + BAS + "\n" + komutlar.tablo() + "\n" + text[j:]


def main() -> int:
    kontrol = "--kontrol" in sys.argv
    want_r = rehber_metni().replace("\n", "\r\n")          # AJAN_REHBERI CRLF
    cur_rd = README.read_text(encoding="utf-8")
    want_rd = readme_metni(cur_rd)
    cur_r = REHBER.read_bytes().decode("utf-8") if REHBER.exists() else ""
    fark = [p.name for p, a, b in ((REHBER, cur_r, want_r), (README, cur_rd, want_rd)) if a != b]
    if kontrol:
        print("fark: " + ", ".join(fark) if fark else "güncel")
        return 1 if fark else 0
    REHBER.write_bytes(want_r.encode("utf-8"))
    README.write_bytes(want_rd.encode("utf-8"))
    print("yazıldı: " + (", ".join(fark) if fark else "değişiklik yok"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
