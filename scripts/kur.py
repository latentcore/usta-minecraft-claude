"""KUR: Usta'yi oyuncunun resmi launcher'ina kurar (S9, M1). Tekrar calistirilinca bozmaz (eksikleri tamamlar).

Adimlar: (1) on-kontrol ve ana kurulumun kaydi, (2) Fabric resmi kurucusu (yalniz yeni surum/kutuphane ekler),
(3) ayri oyun klasoru %APPDATA%\\.usta (mods, options.txt kopyasi), (4) modlar (Usta + Fabric API + Sodium + Lithium + FerriteCore;
resmi kaynaklardan, hash dogrulamali), (5) kopru (venv) + bridge.json, (6) launcher profili (launcher KAPALIYKEN; yedekli,
yalniz yeni anahtar eklenir, gerisinin degismedigi dogrulanir), (7) Claude Code MCP kaydi (kullanici kapsami, yedekli).
Her dokunus %USERPROFILE%\\UstaOyun\\usta\\kurulum\\iz.json ve proje KURULUM_IZI.md'ye yazilir. Hesap dosyalari ACILMAZ.
Kullanim: python scripts/kur.py [--no-profile] [--no-mcp] [--dry-run]
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
APPDATA = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
MC = APPDATA / ".minecraft"
# Oyun klasoru AppData DISINDA: Microsoft Store launcher'i oyunu paket icinde calistirir ve paket, AppData altinda baska
# programlarin olusturdugu dosyalari goremez (modlar hic yuklenmiyordu; OLCUM_DEFTERI 19)
GAME = Path.home() / "UstaOyun"
OLD_GAME = APPDATA / ".usta"
DATA = GAME / "usta"
STATE_DIR = DATA / "kurulum"
STATE = STATE_DIR / "iz.json"
BRIDGE_DST = GAME / "bridge"
MC_VERSION = "26.3"
LOADER = "0.20.1"
INSTALLER = ("1.1.2", "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.1.2/fabric-installer-1.1.2.jar")
FABRIC_VERSION_ID = f"fabric-loader-{LOADER}-{MC_VERSION}"
MODRINTH = [  # (proje, surum numarasi) — KARARLAR K-03/K-04
    ("fabric-api", "0.165.0+26.3"),
    ("sodium", "mc26.3-0.9.2-fabric"),
    ("lithium", "mc26.3-0.26.2-fabric"),
    ("ferrite-core", "9.0.0-fabric"),
]
PY_REQS = ["mcp==2.3.0", "numpy==2.5.4", "pillow==13.0.0", "jsonschema==4.26.0"]  # numpy 2.5 -> Python 3.12+
# Derlenmis mod (GitHub surumu): mod/build/libs'te yerel derleme yoksa buradan, sha256 dogrulanarak indirilir
RELEASE_JAR = ("https://github.com/latentcore/usta-minecraft-claude/releases/download/v0.2.0/usta-0.2.0.jar",
               "616b71aeab1c3e9b7177aea5fdce80b91a1036d064c35d99f0cf308c3113c9f2")
PROFILE_KEY = "usta-claude"
UA = {"User-Agent": "usta-kurulum/0.2"}
DRY = "--dry-run" in sys.argv


def say(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:                  # UTF-8 olmayan konsol: karakter yuzunden kurulum durmasin
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"created": dt.datetime.now().isoformat(timespec="seconds"), "touches": [], "pre_listing": None}


def save_state(st: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def touch(st: dict, path: str, what: str, undo: str) -> None:
    st["touches"] = [t for t in st["touches"] if not (t["path"] == path and t["what"] == what)]
    st["touches"].append({"path": path, "what": what, "when": dt.datetime.now().isoformat(timespec="seconds"), "undo": undo})
    save_state(st)


def sha(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dst: Path, expect: tuple[str, str] | None = None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    if expect:
        algo, want = expect
        got = sha(tmp, algo)
        if got.lower() != want.lower():
            tmp.unlink()
            raise RuntimeError(f"hash uyuşmadı: {url}")
    tmp.replace(dst)


def launcher_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, creationflags=0x08000000).stdout.lower()
    except Exception:
        return False
    return any(n in out for n in ('"minecraft.exe"', '"minecraftlauncher.exe"', '"minecraft launcher.exe"'))


def profile_file() -> Path:
    ms = MC / "launcher_profiles_microsoft_store.json"
    std = MC / "launcher_profiles.json"
    # oyuncunun kurulumunda yalniz launcher_profiles.json var (F0); ikisi de varsa en son degisen kullanilir
    if ms.exists() and std.exists():
        return ms if ms.stat().st_mtime > std.stat().st_mtime else std
    return ms if ms.exists() else std


def listing(root: Path) -> dict:
    out = {}
    for sub in ("versions", "libraries"):
        base = root / sub
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file():
                out[str(p.relative_to(root)).replace("\\", "/")] = p.stat().st_size
    return out


def java_exe() -> str:
    for c in (Path(os.environ.get("JAVA_HOME", "")) / "bin" / "java.exe", Path(r"C:\Program Files\Microsoft\jdk-17.0.20.101-hotspot\bin\java.exe")):
        if c.exists():
            return str(c)
    return shutil.which("java") or "java"


def step_fabric(st: dict) -> None:
    """Fabric surum dosyasini Fabric'in resmi meta servisinden yazar (resmi kurucunun yazdigi dosyanin aynisi).
    Kurucu 1.1.2'de profil olusturmayi kapatma secenegi olmadigindan launcher profil dosyasina dokunmamak icin bu yol secildi (KARARLAR K-08)."""
    vdir = MC / "versions" / FABRIC_VERSION_ID
    vjson = vdir / f"{FABRIC_VERSION_ID}.json"
    if vjson.exists():
        say(f"[tamam] Fabric {LOADER} ({MC_VERSION}) zaten kurulu.")
        return
    url = f"https://meta.fabricmc.net/v2/versions/loader/{MC_VERSION}/{LOADER}/profile/json"
    data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
    prof = json.loads(data)
    if prof.get("id") != FABRIC_VERSION_ID or prof.get("inheritsFrom") != MC_VERSION:
        raise RuntimeError("Fabric meta beklenmeyen yanıt verdi")
    if not DRY:
        vdir.mkdir(parents=True, exist_ok=True)
        vjson.write_bytes(data)
        (vdir / f"{FABRIC_VERSION_ID}.jar").write_bytes(b"")
    touch(st, str(vdir), "Fabric sürüm klasörü (resmi meta.fabricmc.net profil JSON'u; kütüphaneleri launcher ilk açılışta indirir)",
          "KALDIR: klasör ve Fabric kütüphaneleri silinir")
    say(f"[tamam] Fabric {LOADER} sürümü eklendi: versions/{FABRIC_VERSION_ID}")


def step_gamedir(st: dict) -> None:
    for d in (GAME, GAME / "mods", GAME / "saves", GAME / "screenshots", DATA):
        d.mkdir(parents=True, exist_ok=True)
    touch(st, str(GAME), "yeni profilin ayrı oyun klasörü", "KALDIR: dünyalar yedeğe taşınır, klasör silinir")
    opt = GAME / "options.txt"
    if not opt.exists():
        src = MC / "options.txt"
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines() if src.exists() else []
        kv = {}
        order = []
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                kv[k] = v
                order.append(k)
        for k, v in (("pauseOnLostFocus", "false"), ("lang", "tr_tr")):
            if k not in kv:
                order.append(k)
            kv[k] = v
        opt.write_text("\n".join(f"{k}:{kv[k]}" for k in order) + "\n", encoding="utf-8")
        touch(st, str(opt), "options.txt ana kurulumdan KOPYALANDI (kaynağa yazılmadı); pauseOnLostFocus=false, lang=tr_tr", "KALDIR: oyun klasörüyle gider")
        say("[tamam] options.txt kopyalandı (odak kaybında duraklama kapalı, dil Türkçe).")


def find_claude() -> Path | None:
    """Claude Code: resmi kurucunun yeri, sonra PATH (winget/npm kurulumlari)."""
    for c in (Path.home() / ".local" / "bin" / "claude.exe", shutil.which("claude.exe"), shutil.which("claude")):
        if c and Path(c).exists():
            return Path(c)
    return None


def usta_jar() -> Path:
    """Yerel derleme (mod/build/libs) varsa onu, yoksa GitHub surumundeki hazir jar'i (sha256 dogrulamali) kullanir."""
    jar = PROJECT / "mod" / "build" / "libs" / "usta-0.2.0.jar"
    if jar.exists():
        return jar
    cached = DATA / "indirilen" / "usta-0.2.0.jar"
    if not (cached.exists() and sha(cached, "sha256") == RELEASE_JAR[1]):
        say("[..] Usta modu GitHub sürümünden indiriliyor…")
        download(RELEASE_JAR[0], cached, ("sha256", RELEASE_JAR[1]))
    return cached


def step_mods(st: dict) -> None:
    mods = GAME / "mods"
    jar = usta_jar()
    for old in mods.glob("usta-*.jar"):
        old.unlink()
    shutil.copy2(jar, mods / jar.name)
    touch(st, str(mods / jar.name), "Usta modu", "KALDIR: oyun klasörüyle gider")
    for slug, ver in MODRINTH:
        api = f"https://api.modrinth.com/v2/project/{slug}/version"
        vs = json.loads(urllib.request.urlopen(urllib.request.Request(api, headers=UA), timeout=60).read())
        v = next((x for x in vs if x["version_number"] == ver), None)
        if v is None:
            raise RuntimeError(f"Modrinth'te sürüm yok: {slug} {ver}")
        f = next(x for x in v["files"] if x.get("primary")) if any(x.get("primary") for x in v["files"]) else v["files"][0]
        dst = mods / f["filename"]
        if dst.exists() and sha(dst, "sha512") == f["hashes"]["sha512"]:
            continue
        for old in mods.glob(f"{slug.split('-')[0]}*.jar"):
            if old.name != f["filename"] and "usta" not in old.name:
                old.unlink()
        download(f["url"], dst, ("sha512", f["hashes"]["sha512"]))
        st.setdefault("mods", {})[slug] = {"version": ver, "file": f["filename"], "sha512": f["hashes"]["sha512"], "url": f["url"]}
        touch(st, str(dst), f"{slug} {ver} (Modrinth resmi)", "KALDIR: oyun klasörüyle gider")
    say("[tamam] Modlar: Usta, Fabric API, Sodium, Lithium, FerriteCore (hash doğrulandı).")


def step_bridge(st: dict) -> None:
    src = PROJECT / "bridge" / "usta"
    dst = BRIDGE_DST / "usta"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    venv = BRIDGE_DST / "venv"
    py = venv / "Scripts" / "python.exe"
    if not py.exists():
        say("[..] Köprü için Python sanal ortamı kuruluyor…")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, creationflags=0x08000000)
    r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", *PY_REQS], capture_output=True, text=True,
                       creationflags=0x08000000)
    if r.returncode != 0:
        raise RuntimeError("pip hatası: " + r.stderr[-400:])
    # Claude Code MCP kaydi `python -m usta.mcp_server`'i cwd/PYTHONPATH olmadan baslatir: paket venv'e .pth ile tanitilir
    (venv / "Lib" / "site-packages" / "usta_bridge.pth").write_text(str(BRIDGE_DST) + "\n", encoding="utf-8")
    claude = find_claude()
    cfg = {"python": str(py), "pythonpath": str(BRIDGE_DST), "claude": str(claude) if claude else None, "mock_claude": False}
    (DATA / "bridge.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    (BRIDGE_DST / "config.json").write_text(json.dumps({"game_dir": str(GAME)}, ensure_ascii=False), encoding="utf-8")
    touch(st, str(BRIDGE_DST), "köprü (MCP sunucusu, araç seti) + venv", "KALDIR: oyun klasörüyle gider")
    say("[tamam] Köprü kuruldu: " + str(BRIDGE_DST))


def step_profile(st: dict) -> bool:
    if launcher_running():
        say("[BEKLİYOR] Minecraft Launcher açık: profil dosyasına dokunmadım (launcher kapanırken ezebilir). "
            "Launcher'ı kapatıp KUR.bat'ı yeniden çalıştır.")
        return False
    pf = profile_file()
    if not pf.exists():
        say("[UYARI] Launcher profil dosyası bulunamadı; launcher'ı bir kez açıp kapat, sonra KUR.bat'ı yeniden çalıştır.")
        return False
    raw = pf.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    before_others = json.dumps({k: v for k, v in data.items() if k != "profiles"}, sort_keys=True)
    before_profiles = json.dumps({k: v for k, v in data.get("profiles", {}).items() if k != PROFILE_KEY}, sort_keys=True)
    cur = data.get("profiles", {}).get(PROFILE_KEY)
    if cur and cur.get("lastVersionId") == FABRIC_VERSION_ID and cur.get("gameDir") == str(GAME):
        say("[tamam] Launcher profili zaten var: Usta (Claude).")
        return True
    bak_dir = DATA / "yedekler"
    bak_dir.mkdir(parents=True, exist_ok=True)
    bak = bak_dir / f"{pf.name}.{dt.datetime.now():%Y%m%d-%H%M%S}.bak"
    bak.write_bytes(raw)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    data.setdefault("profiles", {})[PROFILE_KEY] = {
        "name": "Usta (Claude)", "type": "custom", "created": now, "lastUsed": now, "icon": "Crafting_Table",
        "lastVersionId": FABRIC_VERSION_ID, "gameDir": str(GAME),
        "javaArgs": "-Xmx4G -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M",
    }
    if not DRY:
        pf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    check = json.loads(pf.read_text(encoding="utf-8"))
    ok = (json.dumps({k: v for k, v in check.items() if k != "profiles"}, sort_keys=True) == before_others and
          json.dumps({k: v for k, v in check["profiles"].items() if k != PROFILE_KEY}, sort_keys=True) == before_profiles)
    if not ok:
        pf.write_bytes(raw)
        raise RuntimeError("Profil dosyasında başka alanlar değişmiş görünüyor; yedekten geri yüklendi, kurulum durdu.")
    st["profile"] = {"file": str(pf), "key": PROFILE_KEY, "backup": str(bak)}
    touch(st, str(pf), f"launcher profiline TEK yeni profil eklendi ({PROFILE_KEY}); öteki alanların değişmediği doğrulandı; yedek: {bak}",
          "KALDIR: yalnız bu anahtar silinir")
    say("[tamam] Launcher'a 'Usta (Claude)' profili eklendi (öteki her şey aynen duruyor).")
    return True


def step_mcp(st: dict) -> bool:
    claude = find_claude()
    if not claude:
        say("[UYARI] Claude Code bulunamadı; MCP kaydı atlandı.")
        return False
    cj = Path.home() / ".claude.json"
    if cj.exists():
        bak = DATA / "yedekler" / f"claude.json.{dt.datetime.now():%Y%m%d-%H%M%S}.bak"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cj, bak)  # icerik okunmaz/yazdirilmaz
        st["claude_json_backup"] = str(bak)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    py = BRIDGE_DST / "venv" / "Scripts" / "python.exe"
    subprocess.run([str(claude), "mcp", "remove", "--scope", "user", "usta"], capture_output=True, env=env, creationflags=0x08000000)
    r = subprocess.run([str(claude), "mcp", "add", "--scope", "user", "usta", "--", str(py), "-m", "usta.mcp_server"],
                       capture_output=True, text=True, env=env, creationflags=0x08000000)
    if r.returncode != 0:
        say("[HATA] MCP kaydı başarısız: " + (r.stderr or r.stdout)[-300:])
        return False
    g = subprocess.run([str(claude), "mcp", "get", "usta"], capture_output=True, text=True, env=env, creationflags=0x08000000)
    ok = g.returncode == 0 and "usta.mcp_server" in g.stdout
    touch(st, str(cj), "Claude Code kullanıcı kapsamına TEK MCP kaydı (usta) — resmi `claude mcp add --scope user`; yedek alındı",
          "KALDIR: `claude mcp remove --scope user usta`")
    say("[tamam] MCP kaydı (kullanıcı kapsamı): usta" if ok else "[UYARI] MCP kaydı doğrulanamadı.")
    return ok


def migrate_old_game() -> None:
    """Eski AppData\\.usta kurulumundan yeni klasore bir kez: kurulum izi (KALDIR icin) ve dunyalar (kopya)."""
    if DRY or not OLD_GAME.exists() or STATE.exists():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    old_state = OLD_GAME / "usta" / "kurulum" / "iz.json"
    if old_state.exists():
        shutil.copy2(old_state, STATE)
    old_saves = OLD_GAME / "saves"
    if old_saves.exists():
        (GAME / "saves").mkdir(parents=True, exist_ok=True)
        for w in old_saves.iterdir():
            if w.is_dir() and not (GAME / "saves" / w.name).exists():
                shutil.copytree(w, GAME / "saves" / w.name)
    say(f"[tamam] Eski oyun klasöründen kurulum izi ve dünyalar kopyalandı: {OLD_GAME} -> {GAME}")


def main() -> int:
    say("Usta kurulumu başlıyor…")
    if sys.version_info < (3, 12):
        say(f"[HATA] Python {sys.version_info.major}.{sys.version_info.minor} eski: Python 3.12 ya da üstü gerekli "
            "(3.13 önerilir): https://www.python.org/downloads/")
        return 1
    if not MC.exists():
        say("[HATA] %APPDATA%\\.minecraft yok: Minecraft Launcher ve Java Edition kurulu olmalı (bunu sen kurarsın).")
        return 1
    migrate_old_game()
    st = load_state()
    if st.get("pre_listing") is None:
        st["pre_listing"] = listing(MC)
        st["pre_root_files"] = sorted(p.name for p in MC.iterdir() if p.is_file())
        save_state(st)
    step_fabric(st)
    step_gamedir(st)
    step_mods(st)
    step_bridge(st)
    prof = "--no-profile" not in sys.argv and step_profile(st)
    mcp = "--no-mcp" not in sys.argv and step_mcp(st)
    st["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
    st["profile_done"] = bool(prof)
    st["mcp_done"] = bool(mcp)
    save_state(st)
    say("")
    say("Kurulum bitti." + ("" if prof else " (Profil adımı bekliyor: launcher'ı kapatıp KUR.bat'ı tekrar çalıştır.)"))
    if not find_claude():
        say("[EKSİK] Claude Code kurulu değil; oyunda /claude çalışmaz. PowerShell'de:")
        say("        irm https://claude.ai/install.ps1 | iex")
        say("        sonra bir kez: claude auth login   ve KUR.bat'ı tekrar çalıştır.")
    say("Sıradaki: Launcher'da 'Usta (Claude)' profilini seç → Oyna. Dünyada ilk kullanımda sohbetteki")
    say("'Onayla ve yedekle' düğmesine bas, sonra örneğin: /claude önüme bir ev yap. Ayrıntı: README.md")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        say(f"[HATA] {e}")
        sys.exit(2)
