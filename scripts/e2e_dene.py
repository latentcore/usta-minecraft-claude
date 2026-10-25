"""E2E_DENE: gercek basliksiz Claude ile uctan uca deneme (oyun acik + Claude girisi gerekir).
Altin setten secili istekleri oyundaki ajana gonderir (panelle ayni yol: /v1/agent/request), her biri icin sureyi ve
sonucu olcer, KANIT/e2e/<tarih>/sonuc.json'a yazar. Kullanim: python scripts/e2e_dene.py [istek_no ...] (varsayilan 1 3 8)
Her istek senin kotandan yer (OLCUM_DEFTERI.md K7). Bir istegi geri almak icin oyunda /usta geri."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bridge"))

ISTEKLER = {
    1: "önüme devasa modern güzel bir ev yap", 2: "bu tepeye bahçeli bir Osmanlı konağı yap",
    3: "avlulu, kubbeli ve minareli küçük bir cami yap", 4: "göle uzanan taş kemerli bir köprü",
    5: "deniz kenarına deniz feneri ve ahşap iskele", 6: "surlu bir ortaçağ kalesi, kuleleri ve kapısıyla",
    7: "fütüristik cam bir gökdelen ve çevresine meydan", 8: "Japon bahçesi ve çay evi",
    9: "ahırı, tarlası ve çitleriyle bir çiftlik", 10: "ormanda birbirine köprülerle bağlı ağaç evlerden küçük bir köy",
    11: "200×200 yollarla bir şehir bloğu", 12: "evimden göle kadar araziye uyan bir yol",
    13: "şu tepeyi düzle, yerine çiçekli bir park yap", 14: "bu evi bir kat yükselt ve çatısını kırma çatıya çevir",
    15: "şu odayı modern bir mutfak olarak döşe", 16: "kapısı kızıltaşla açılan gizli bir oda",
    17: "akşam olsun, yağmur yağsın, sonra beni evin terasına ışınla",
}


def claude_logged_in() -> bool:
    exe = Path.home() / ".local" / "bin" / "claude.exe"
    try:
        r = subprocess.run([str(exe), "auth", "status", "--text"], capture_output=True, text=True, timeout=30)
        return "logged in" in (r.stdout + r.stderr).lower() and "not logged" not in (r.stdout + r.stderr).lower()
    except Exception:
        return False


def main() -> int:
    nums = [int(a) for a in sys.argv[1:] if a.isdigit()] or [1, 3, 8]
    if not claude_logged_in():
        print("[KIRMIZI] Claude girişi yok. Önce: \"%USERPROFILE%\\.local\\bin\\claude.exe\" auth login")
        return 1
    from usta import ops
    api = ops.game()
    try:
        st = api.status()
    except Exception as e:
        print(f"[KIRMIZI] Oyun kapalı ya da Usta yanıt vermiyor ({e}). Usta (Claude) profiliyle bir dünyaya gir.")
        return 1
    out = ROOT / "KANIT" / "e2e" / dt.datetime.now().strftime("%Y%m%d-%H%M")
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for n in nums:
        text = ISTEKLER[n]
        print(f"#{n} {text} …", flush=True)
        t0 = time.time()
        r = api.agent_request(text, source="e2e")
        rid = r.get("request") or r.get("id")
        state = {}
        while time.time() - t0 < 600:
            time.sleep(3)
            state = api.agent_get(rid) if rid else api.agent_state()
            if state.get("state") in ("done", "failed", "cancelled"):
                break
        res.append({"n": n, "istek": text, "sn": round(time.time() - t0, 1), "durum": state.get("state"),
                    "ozet": state.get("text") or state.get("summary"), "request": rid})
        print(f"  -> {res[-1]['durum']} ({res[-1]['sn']} sn)")
    (out / "sonuc.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Sonuç: {out / 'sonuc.json'}  (oyunda /usta geri ile geri alabilirsin)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
