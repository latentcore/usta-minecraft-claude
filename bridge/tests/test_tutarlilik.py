"""Tutarlilik: talimat, rehber, README, oyun ici yardim ve kod ayni seyi soyluyor mu (tek kaynak: agent_guide, komutlar,
mcp_server). Bir yer degisip digeri unutulursa bu test kirilir; duzeltmek icin scripts/dev/rehber_uret.py."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JAVA = ROOT / "mod/src/main/java/dev/usta/game/UstaCommands.java"
sys.path.insert(0, str(ROOT / "scripts" / "dev"))


def _rehber():
    import rehber_uret
    return rehber_uret


def _java() -> str:
    return JAVA.read_text(encoding="utf-8")


def _java_groups() -> list[frozenset]:
    """tree() icindeki `for (String a : List.of(...))` yazim gruplari."""
    src = _java()
    body = src[src.index("tree(String root)"):src.index("private static Usta usta(")]
    return [frozenset(re.findall(r'"([^"]+)"', m)) for m in re.findall(r"for \(String a : List\.of\(([^)]*)\)\)", body)]


def _help_text() -> str:
    src = _java()
    body = src[src.index("private static int help("):]
    body = body[:body.index("\n\t}\n")]
    return " ".join(re.findall(r'literal\("([^"]*)"\)', body)) + " " + " ".join(re.findall(r'line\("([^"]*)"\)', body))


def test_java_commands_match_single_source():
    from usta.komutlar import KOMUTLAR
    want = {frozenset(k.yazimlar) for k in KOMUTLAR if k.yol == "java"}
    got = set(_java_groups())
    assert got == want, f"Java'da fazla: {sorted(map(sorted, got - want))}; Java'da eksik: {sorted(map(sorted, want - got))}"
    for k in KOMUTLAR:
        assert k.ad in k.yazimlar or k.yol == "istek", f"{k.ad}: gösterilen ad Java yazımları arasında değil"


def test_ingame_help_lists_every_visible_command():
    from usta.komutlar import KOMUTLAR, gorunen
    h = _help_text()
    missing = [k.ad for k in gorunen() if not re.search(r"(?<![\wçğıöşü-])" + re.escape(k.ad) + r"(?![\wçğıöşü-])", h)]
    assert not missing, f"/usta yardım'da yok: {missing}"
    eng = re.search(r'literal\("\s*İngilizce:([^"]*)"\)', _java()).group(1).replace("/ai", "")
    aliases = {a for k in KOMUTLAR for a in k.yazimlar}
    unknown = [w for w in re.findall(r"[a-z]+", eng) if w not in aliases]
    assert not unknown, f"yardımın İngilizce satırında komut olmayan sözcük: {unknown}"


def test_istek_fast_paths_exist():
    from usta import kalp_adasi, stadyum
    assert kalp_adasi.istek_mi("ada") and stadyum.istek_mi("stadyum")


def test_generated_files_are_current():
    r = _rehber()
    readme = r.README.read_text(encoding="utf-8")
    assert r.readme_metni(readme) == readme, f"{r.README.name} komut tablosu eski: scripts/dev/rehber_uret.py çalıştır"
    rehber = (ROOT / "AJAN_REHBERI.md").read_bytes().decode("utf-8")
    assert rehber == r.rehber_metni().replace("\n", "\r\n"), "AJAN_REHBERI.md eski: scripts/dev/rehber_uret.py çalıştır"


def _readmes() -> list[str]:
    """Ozel depoda README.md (Turkce); herkese acik depoda README.md (Ingilizce) + README_TR.md."""
    return [p.read_text(encoding="utf-8") for p in (ROOT / "README.md", ROOT / "README_TR.md") if p.exists()]


def test_readme_counts_match_code():
    from usta import mcp_server
    from usta.audit import CHECKS
    from usta.kit import gen, interiors, parts, redstone, style, trees
    n_tools = len(mcp_server.server._tool_manager.list_tools())
    seen = {"arac": 0, "kontrol": 0, "kit": 0}
    for readme in _readmes():
        text = " ".join(readme.split())                   # satir kirilmalari sayilarin arasina girmesin
        for m in re.findall(r"(\d+) (?:MCP aracı|araçlı MCP|araç\)|MCP tools|MCP aracını|tool MCP server|-tool MCP)", text):
            assert int(m) == n_tools, f"README araç sayısı {m}, kodda {n_tools}"
            seen["arac"] += 1
        for m in re.findall(r"(\d+) (?:otomatik )?(?:kontrol|automatic checks|checks)\b", text):
            assert int(m) == len(CHECKS), f"README kontrol sayısı {m}, kodda {len(CHECKS)}"
            seen["kontrol"] += 1
        for m in re.findall(r"(\d+) parametri(?:k üreteç|c generators)|Üreteçler \((\d+)\)", text):
            assert int(m[0] or m[1]) == len(gen.GENERATORS)
        names = re.search(r"### Üreteçler \(\d+\)\n(.+?)\n\n", readme, re.S)
        if names:
            got = sorted(re.sub(r"\(.*?\)", "", n).strip(" .") for n in names.group(1).replace("\n", " ").split(","))
            assert got == sorted(gen.GENERATORS)
        kit = re.search(r"(\d+) bileşen, (\d+) tarz paketi, (\d+) iç mekân tarifi, (\d+) ağaç türü, .*?(\d+) kızıltaş", text)
        if kit:                                           # kayitli parcalar (@part); yardimcilar (heal_*) sayilmaz
            assert tuple(map(int, kit.groups())) == (len(parts.CATALOG), len(style.STYLES), len(interiors._RECIPES),
                                                    len(trees.SPECIES), len(redstone.MECHANISMS))
            seen["kit"] += 1
    assert all(seen.values()), f"README'de sayı satırı bulunamadı: {seen}"


def test_audit_docstring_lists_every_check():
    import usta.audit as A
    from usta.audit import CHECKS
    doc = A.__doc__ or ""
    assert f"{len(CHECKS)} kontrolden" in doc
    from usta import kitdoc
    assert f"{len(CHECKS)} kontrolden" in kitdoc.reference("overview")


def test_guide_mentions_only_existing_tools():
    from usta import mcp_server
    from usta.agent_guide import HEADLESS_APPEND, INSTRUCTIONS
    tools = {t.name for t in mcp_server.server._tool_manager.list_tools()}
    text = INSTRUCTIONS + HEADLESS_APPEND
    # arac adina benzeyen (alt cizgili) sozcukler: ya arac ya da bilinen parametre/kontrol adi olmali
    known = {"allow_modify", "allow_dangerous", "draft_id", "stair_walkability", "with_code", "kit_reference"}
    words = set(re.findall(r"(?<![\w.])([a-z]+(?:_[a-z]+)+)(?![\w(])", text)) | set(re.findall(r"(?<![\w.])([a-z]+(?:_[a-z]+)+)\(", text))
    unknown = sorted(w for w in words if w not in tools and w not in known)
    assert not unknown, f"talimatta olmayan araç/ad: {unknown}"
    for t in ("survey_area", "structure_to_code", "run_game_command", "remove_entities", "entities"):
        assert t in tools and t in INSTRUCTIONS, t


@pytest.mark.parametrize("rel", ["README.md", "README_TR.md", "AJAN_REHBERI.md", "bridge/usta/agent_guide.py", "bridge/usta/komutlar.py"])
def test_no_removed_feature_leftovers(rel):
    if not (ROOT / rel).exists():
        pytest.skip(f"{rel} bu depoda yok")
    text = (ROOT / rel).read_text(encoding="utf-8")
    for bad in (r"\bTV\b", r"televizyon", r"\bEdge\b", r"/tv\b"):
        for m in re.finditer(bad, text, re.I):
            line = text[text.rfind("\n", 0, m.start()) + 1:text.find("\n", m.end())]
            assert "TV/EKRAN: çalışan TV ya da video ekranı yok" in line, f"{rel}: kaldırılan özellik kalıntısı: {line.strip()[:120]}"
    help_ = _help_text()
    assert not re.search(r"\btv\b", help_, re.I)
