"""DUNYA_ICE_AKTAR: bir dunyanin KOPYASINI Usta profiline alir; asil dunyaya dokunmaz.
Kullanim: python scripts/dunya_ice_aktar.py [klasor_ya_da_zip]   (arguman yoksa ana kurulumdaki dunyalari listeler)"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

APPDATA = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
SRC_SAVES = APPDATA / ".minecraft" / "saves"
DST_SAVES = Path.home() / "UstaOyun" / "saves"     # Usta profilinin oyun klasoru (AppData disinda; KUR.GAME)


def unique(dst: Path) -> Path:
    if not dst.exists():
        return dst
    k = 2
    while (dst.parent / f"{dst.name} ({k})").exists():
        k += 1
    return dst.parent / f"{dst.name} ({k})"


def main() -> int:
    DST_SAVES.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        src = Path(sys.argv[1].strip('"'))
    else:
        worlds = sorted([p for p in SRC_SAVES.iterdir() if (p / "level.dat").exists()], key=lambda p: -p.stat().st_mtime) if SRC_SAVES.exists() else []
        if not worlds:
            print("Ana kurulumda dünya bulunamadı. Bir klasör ya da zip yolu vererek çalıştır.")
            return 1
        for i, w in enumerate(worlds, 1):
            print(f"{i}) {w.name}")
        ch = input("Kopyalanacak dünyanın numarası: ").strip()
        if not ch.isdigit() or not (1 <= int(ch) <= len(worlds)):
            print("Vazgeçildi.")
            return 0
        src = worlds[int(ch) - 1]
    if src.is_file() and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            names = z.namelist()
            roots = {n.split("/")[0] for n in names if n.endswith("level.dat")}
            dst = unique(DST_SAVES / (src.stem))
            tmp = DST_SAVES / ("_gecici_" + src.stem)
            z.extractall(tmp)
            inner = next((tmp / r for r in roots if (tmp / r / "level.dat").exists()), tmp)
            shutil.move(str(inner), str(dst))
            shutil.rmtree(tmp, ignore_errors=True)
    elif src.is_dir() and (src / "level.dat").exists():
        dst = unique(DST_SAVES / src.name)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("session.lock"))
    else:
        print("Geçerli bir dünya klasörü (level.dat içeren) ya da zip değil.")
        return 1
    print(f"Kopyalandı: {dst}\nAslına dokunulmadı. Usta profilinde 'Tek Oyunculu' listesinde görünecek.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
