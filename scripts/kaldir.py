"""KALDIR: KUR'un ekledigi her seyi ve YALNIZ onlari geri alir (S9, M1).
- Launcher profilinden yalniz 'usta-claude' anahtari silinir (yedek alinir; gerisinin degismedigi dogrulanir).
- Fabric surum klasoru ve KUR'dan sonra eklenen Fabric kutuphaneleri silinir (kurulum oncesi listeye gore).
- Yeni profilde olusmus dunyalar SILINMEZ: %APPDATA%\\Usta_Yedek_Dunyalar_<tarih> klasorune tasinir.
- %APPDATA%\\.usta silinir. MCP kaydi `claude mcp remove --scope user usta` ile kaldirilir. Claude Code araci kaldirilmaz.
Kullanim: python scripts/kaldir.py [--evet]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kur  # noqa: E402


def main() -> int:
    if not kur.STATE.exists():
        print("Kurulum izi yok (Usta kurulu görünmüyor). Yapılacak bir şey yok.")
        return 0
    st = json.loads(kur.STATE.read_text(encoding="utf-8"))
    if kur.launcher_running():
        print("[BEKLİYOR] Minecraft Launcher açık: önce launcher'ı kapat, sonra KALDIR.bat'ı yeniden çalıştır.")
        return 1
    report = []
    # 1) launcher profili
    pf = Path(st.get("profile", {}).get("file") or kur.profile_file())
    if pf.exists():
        raw = pf.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        if kur.PROFILE_KEY in data.get("profiles", {}):
            bak = kur.DATA / "yedekler" / f"{pf.name}.kaldir.{dt.datetime.now():%Y%m%d-%H%M%S}.bak"
            bak.parent.mkdir(parents=True, exist_ok=True)
            bak.write_bytes(raw)
            others = json.dumps({k: v for k, v in data.items() if k != "profiles"}, sort_keys=True)
            del data["profiles"][kur.PROFILE_KEY]
            pf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            chk = json.loads(pf.read_text(encoding="utf-8"))
            assert json.dumps({k: v for k, v in chk.items() if k != "profiles"}, sort_keys=True) == others
            report.append("launcher profili kaldırıldı (öteki alanlar aynen)")
            # profil dosyasinin yedegini KALDIR sonrasi da erisilebilir yere koy
            safe = kur.APPDATA / "Usta_Kaldirma_Yedekleri"
            safe.mkdir(exist_ok=True)
            shutil.copy2(bak, safe / bak.name)
    # 2) Fabric surumu + eklenen kutuphaneler
    pre = st.get("pre_listing") or {}
    vdir = kur.MC / "versions" / kur.FABRIC_VERSION_ID
    if vdir.exists():
        shutil.rmtree(vdir)
        report.append(f"versions/{kur.FABRIC_VERSION_ID} silindi")
    removed = 0
    for sub in ("libraries",):
        base = kur.MC / sub
        if not base.exists():
            continue
        for p in sorted(base.rglob("*"), reverse=True):
            rel = str(p.relative_to(kur.MC)).replace("\\", "/")
            if p.is_file() and rel not in pre and ("net/fabricmc" in rel or "org/ow2/asm" in rel or "net/minecraft/launchwrapper" in rel
                                                     or "io/github/llamalad7" in rel):
                p.unlink()
                removed += 1
            elif p.is_dir() and not any(p.iterdir()):
                rel_dir = rel + "/"
                if not any(k.startswith(rel_dir) for k in pre):
                    p.rmdir()
    if removed:
        report.append(f"Fabric ile gelen {removed} kütüphane dosyası silindi")
    # 3) dunyalari tasi, oyun klasorunu sil
    saves = kur.GAME / "saves"
    if saves.exists() and any(saves.iterdir()):
        dst = kur.APPDATA / f"Usta_Yedek_Dunyalar_{dt.datetime.now():%Y%m%d-%H%M%S}"
        shutil.move(str(saves), str(dst))
        report.append(f"Usta profilindeki dünyalar SİLİNMEDİ, taşındı: {dst}")
    backups = kur.DATA / "yedekler"
    if backups.exists() and any(backups.iterdir()):
        dst2 = kur.APPDATA / "Usta_Kaldirma_Yedekleri"
        dst2.mkdir(exist_ok=True)
        for f in backups.iterdir():
            if f.is_file() and f.suffix == ".zip":
                shutil.move(str(f), str(dst2 / f.name))
        report.append(f"dünya yedekleri (zip) taşındı: {dst2}")
    # 4) MCP kaydi
    claude = Path.home() / ".local" / "bin" / "claude.exe"
    if claude.exists():
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
        r = subprocess.run([str(claude), "mcp", "remove", "--scope", "user", "usta"], capture_output=True, text=True, env=env,
                           creationflags=0x08000000)
        report.append("MCP kaydı kaldırıldı" if r.returncode == 0 else "MCP kaydı zaten yoktu")
    if kur.GAME.exists():
        shutil.rmtree(kur.GAME, ignore_errors=True)
        report.append(f"{kur.GAME} silindi")
    old = getattr(kur, "OLD_GAME", None)          # ilk kurulumun AppData\.usta klasoru (tasindi)
    if old is not None and old.exists():
        osaves = old / "saves"
        if osaves.exists() and any(osaves.iterdir()):
            dst3 = kur.APPDATA / f"Usta_Yedek_Dunyalar_eski_{dt.datetime.now():%Y%m%d-%H%M%S}"
            shutil.move(str(osaves), str(dst3))
            report.append(f"eski klasördeki dünyalar SİLİNMEDİ, taşındı: {dst3}")
        shutil.rmtree(old, ignore_errors=True)
        report.append(f"{old} (eski oyun klasörü) silindi")
    # 5) dogrulama: ana kurulum listesi
    now = kur.listing(kur.MC)
    extra = [k for k in now if k not in pre and ("fabric" in k.lower())]
    missing = [k for k in pre if k not in now]
    report.append(f"doğrulama: Fabric'ten kalan dosya {len(extra)}, kurulum öncesine göre eksik dosya {len(missing)}")
    print("\n".join("- " + x for x in report))
    print("Kaldırma tamam. Claude Code aracı yerinde bırakıldı (istersen README'deki komutla kaldırabilirsin).")
    return 0 if not extra and not missing else 3


if __name__ == "__main__":
    if "--evet" not in sys.argv:
        ans = input("Usta kaldırılacak (dünyaların silinmez, yedeğe taşınır). Devam? (e/h): ").strip().lower()
        if ans not in ("e", "evet", "y", "yes"):
            print("Vazgeçildi.")
            sys.exit(0)
    sys.exit(main())
