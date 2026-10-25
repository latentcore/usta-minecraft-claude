"""Kum havuzu (ebeveyn tarafi): yapi betigini ayri, sinirli bir surecte calistirir ve plan dosyasini dondurur."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .. import blockdb, config

BRIDGE = Path(__file__).resolve().parents[2]


def _python() -> str:
    exe = Path(sys.executable)
    # pythonw yerine python (konsolsuz calistirilacak)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def run_script(code: str, ctx: dict | None = None, timeout: float = 90.0, mem_mb: int = 2048,
               max_output: int = 65536, keep: bool = True, files: dict[str, bytes] | None = None) -> dict:
    """Betigi calistirir. Donus: {'ok', 'plan_path', 'workdir', 'stdout', 'stderr', ...}.
    ctx: betige `ctx` olarak verilir (site, anchor, style, params…)."""
    ctx = dict(ctx or {})
    root = config.work_dir() / "kumhavuzu"
    root.mkdir(parents=True, exist_ok=True)
    wd = root / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    wd.mkdir()
    dbp = blockdb.db_path()
    if not dbp.exists():
        blockdb.get()
    ctx.setdefault("blockdb", str(dbp))
    ctx.setdefault("mem_mb", mem_mb)
    ctx.setdefault("max_output", max_output)
    (wd / "ctx.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    (wd / "script.py").write_text(code, encoding="utf-8")
    for name, data in (files or {}).items():
        (wd / name).write_bytes(data)
    boot = (f"import sys; sys.path.insert(0, {str(BRIDGE)!r}); "
            f"from usta.sandbox import child; child.main({str(wd)!r})")
    env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "TEMP", "TMP", "PATH", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")}
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    t0 = time.time()
    out_f = open(wd / "stdout.txt", "wb")
    err_f = open(wd / "stderr.txt", "wb")
    try:
        p = subprocess.Popen([_python(), "-I", "-X", "utf8", "-c", boot], cwd=str(wd), env=env, stdout=out_f, stderr=err_f,
                             stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            p.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(5)
            timed_out = True
    finally:
        out_f.close()
        err_f.close()
    dt = round(time.time() - t0, 2)

    def tail(name: str) -> str:
        try:
            b = (wd / name).read_bytes()[-max_output:]
            return b.decode("utf-8", "replace")
        except Exception:
            return ""
    res: dict
    rp = wd / "result.json"
    if timed_out:
        res = {"ok": False, "error": f"Betik süre sınırını ({timeout:.0f} sn) aştı ve durduruldu."}
    elif rp.exists():
        res = json.loads(rp.read_text(encoding="utf-8"))
    else:
        res = {"ok": False, "error": f"Betik süreci sonuç yazmadan bitti (kod {p.returncode}); bellek sınırı aşılmış olabilir."}
    res["workdir"] = str(wd)
    res["wall_seconds"] = dt
    res["stdout"] = tail("stdout.txt")[-4000:]
    res["stderr"] = tail("stderr.txt")[-4000:]
    if res.get("ok"):
        res["plan_path"] = str(wd / "plan.uplan")
    if not keep and not res.get("ok"):
        shutil.rmtree(wd, ignore_errors=True)
    return res
