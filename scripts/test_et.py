"""TEST_ET: butun testleri kosar. Varsayilan: kopru birim testleri + mod derleme ve sunucu oyun testleri.
--tam: ayrica test duzenini (harness) acip Q2/Q3, Q4, Q5, Q6 olcumlerini kosar (yaklasik 15 dk).
Ozet: work/test_et_ozet.txt"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "bridge" / ".venv" / "Scripts" / "python.exe"
JAVA_HOME = os.environ.get("JAVA_HOME", "")
NOWIN = 0x08000000


def run(name: str, cmd: list[str], cwd: Path, env: dict | None = None, timeout: int = 1800) -> tuple[str, bool, float]:
    t0 = time.time()
    print(f"[..] {name}", flush=True)
    log = ROOT / "work" / f"test_{name.replace(' ', '_')}.log"
    log.parent.mkdir(exist_ok=True)
    with open(log, "w", encoding="utf-8") as f:
        try:
            r = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, creationflags=NOWIN)
            ok = r.returncode == 0
        except subprocess.TimeoutExpired:
            ok = False
    dt = time.time() - t0
    print(f"[{'GEÇTİ' if ok else 'KALDI'}] {name} ({dt:.0f} sn) — günlük: {log.relative_to(ROOT)}", flush=True)
    return name, ok, dt


def main() -> int:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
    env["JAVA_HOME"] = JAVA_HOME
    res = []
    res.append(run("kopru birim testleri", [str(PY), "-m", "pytest", "-q", "bridge/tests", "--ignore=bridge/tests/harness"], ROOT, env))
    res.append(run("mod derleme ve oyun testleri", [str(ROOT / "mod" / "gradlew.bat"), "build", "--console=plain"], ROOT / "mod", env))
    if "--tam" in sys.argv:
        res.append(run("test duzeni baslat", [sys.executable, "scripts/dev/harness.py", "start", "--fresh"], ROOT, env, 400))
        res.append(run("Q2-Q3 yerlestirme ve geri alma", [str(PY), "-m", "pytest", "-q", "bridge/tests/harness/test_q2_q3.py"], ROOT, env))
        res.append(run("Q4 performans", [str(PY), "scripts/dev/perf.py"], ROOT, env))
        res.append(run("Q5 kesinti", [str(PY), "scripts/dev/restart_test.py"], ROOT, env))
        res.append(run("test duzeni durdur", [sys.executable, "scripts/dev/harness.py", "stop"], ROOT, env, 200))
        res.append(run("Q6 vanilla uyumu", [sys.executable, "scripts/dev/vanilla_check.py"], ROOT, env, 600))
    lines = [f"{'GEÇTİ' if ok else 'KALDI'}\t{n}\t{dt:.0f} sn" for n, ok, dt in res]
    (ROOT / "work" / "test_et_ozet.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all(ok for _, ok, _ in res) else 1


if __name__ == "__main__":
    sys.exit(main())
