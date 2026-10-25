"""Kum havuzu cocuk sureci: yapi betigini sinirlar altinda calistirir (M5).

Katmanlar: (1) Windows is nesnesi (bellek siniri, alt surec yasagi, kapaninca oldur),
(2) denetim kancasi (PEP 578): ag, alt surec, ctypes, kayit defteri, calisma klasoru disina yazma ve
izinsiz okuma engellenir, (3) yalniz izinli moduller ice aktarilir, (4) cikti boyutu sinirli.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

ALLOWED_TOP = {
    "numpy", "math", "random", "itertools", "functools", "collections", "dataclasses", "typing", "enum", "statistics",
    "heapq", "bisect", "string", "re", "json", "copy", "operator", "fractions", "decimal", "colorsys", "textwrap", "usta",
    "abc", "types", "warnings", "numbers", "contextlib", "_collections_abc",
}
BLOCKED_EVENT_PREFIXES = (
    "socket.", "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.kill", "os.fork",
    "ctypes.", "winreg.", "_winapi.", "msvcrt.", "webbrowser.", "urllib.Request", "http.client.", "ftplib.", "smtplib.",
    "telnetlib.", "imaplib.", "poplib.", "nntplib.", "glob.glob", "os.listdir", "os.scandir", "shutil.",
    "sys._getframe", "object.__getattr__" if False else "__never__",
)


class _LimitedWriter:
    def __init__(self, inner, limit):
        self.inner = inner
        self.left = limit

    def write(self, s):
        if self.left <= 0:
            return len(s)
        s2 = s[: self.left]
        self.left -= len(s2)
        if self.left <= 0:
            s2 += "\n[çıktı sınırı aşıldı]\n"
        return self.inner.write(s2)

    def flush(self):
        try:
            self.inner.flush()
        except Exception:
            pass


def _job_limits(mem_mb: int) -> bool:
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

        class EXT(ctypes.Structure):
            _fields_ = [("Basic", BASIC), ("Io", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return False
        info = EXT()
        JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
        JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x100
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        info.Basic.LimitFlags = JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        info.Basic.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = mem_mb * 1024 * 1024
        ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            return False
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        ok = k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
        globals()["_JOB_HANDLE"] = job  # acik kalsin
        return bool(ok)
    except Exception:
        return False


def main(workdir: str) -> None:
    t0 = time.time()
    res_path = os.path.join(workdir, "result.json")
    ctx = json.load(open(os.path.join(workdir, "ctx.json"), encoding="utf-8"))
    code = open(os.path.join(workdir, "script.py"), encoding="utf-8").read()
    bridge = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 1) gerekli her seyi onceden yukle (hata bicimlendirme dahil)
    import linecache, tokenize, unicodedata, textwrap, difflib  # noqa: F401,E401
    import zipfile, zlib  # noqa: F401,E401  (np.load .npz arazi dosyasi icin; kancadan once)
    import numpy as np  # noqa: F401
    import numpy.lib.format, numpy.ma, numpy.linalg, numpy.random  # noqa: F401,E401  (numpy tembel alt modulleri)
    from usta.blockdb import BlockDB, set_db
    set_db(BlockDB.from_file(ctx["blockdb"]))
    import usta.kit as kit
    from usta.kit import core
    mods = {}
    for name in ("shapes", "parts", "style", "trees", "terrain", "interiors", "gen", "redstone"):
        try:
            mods[name] = __import__(f"usta.kit.{name}", fromlist=["*"])
        except ImportError:
            pass
        except Exception as e:  # modul hatasi betigi engellemesin
            mods[name] = None
            print(f"[uyarı] usta.kit.{name} yüklenemedi: {e}", file=sys.stderr)
    from usta.plan import Plan  # noqa: F401
    import usta.audit.checks  # noqa: F401  (agaclarin toprak kurali denetcinin tablolarini kullanir)
    # girdi dosyalari kancadan ONCE okunur (np.load/zip/codec tembel importlari kum havuzu kuralina takilmasin)
    pre_terrain = None
    tpath = os.path.join(workdir, "terrain.npz")
    if os.path.exists(tpath):
        with np.load(tpath, allow_pickle=False) as tz:
            pre_terrain = {k: np.array(tz[k]) for k in tz.files}
    pre_existing = None
    epath = os.path.join(workdir, "existing.uplan")
    if os.path.exists(epath):
        pre_existing = Plan.load(epath)
    # 2) is nesnesi
    limits_ok = _job_limits(int(ctx.get("mem_mb", 2048)))
    # 3) denetim kancasi
    wd = os.path.normcase(os.path.abspath(workdir))
    read_roots = [wd, os.path.normcase(bridge), os.path.normcase(os.path.dirname(os.__file__)),
                  os.path.normcase(sys.prefix), os.path.normcase(sys.base_prefix),
                  os.path.normcase(os.path.dirname(os.path.abspath(ctx["blockdb"])))]
    preloaded = set(sys.modules)

    def under(p, roots):
        try:
            p = os.path.normcase(os.path.abspath(p))
        except Exception:
            return False
        return any(p == r or p.startswith(r + os.sep) for r in roots)

    def hook(event, args):
        if event == "import":
            mod = args[0] or ""
            top = mod.split(".")[0]
            if mod in preloaded or top in ALLOWED_TOP:
                return
            raise PermissionError(f"kum havuzu: '{mod}' modülü kullanılamaz")
        if event.startswith(BLOCKED_EVENT_PREFIXES):
            raise PermissionError(f"kum havuzu: '{event}' yasak")
        if event == "open":
            path, mode, flags = (list(args) + [None, None, None])[:3]
            if isinstance(path, int) or path is None:
                return
            path = os.fsdecode(path) if isinstance(path, (bytes, os.PathLike)) else str(path)
            writing = (mode and any(c in str(mode) for c in "wax+")) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
            if writing:
                if not under(path, [wd]):
                    raise PermissionError("kum havuzu: çalışma klasörü dışına yazılamaz")
            elif not under(path, read_roots):
                raise PermissionError("kum havuzu: bu dosya okunamaz")
        if event in ("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.truncate", "os.utime", "os.link", "os.symlink"):
            p = args[0] if args else ""
            if not under(os.fsdecode(p) if not isinstance(p, int) else "", [wd]):
                raise PermissionError(f"kum havuzu: '{event}' yasak")

    sys.addaudithook(hook)
    sys.stdout = _LimitedWriter(sys.stdout, int(ctx.get("max_output", 65536)))
    sys.stderr = _LimitedWriter(sys.stderr, int(ctx.get("max_output", 65536)))
    out = {"ok": False}
    captured: dict = {}

    def result(build, origin=None, facing=None, label=None, meta=None):
        captured["build"] = build
        captured["origin"] = origin
        captured["facing"] = facing
        captured["label"] = label
        captured["meta"] = meta or {}

    class _Site(dict):                      # hem site["origin"] hem site.origin (ajan rehberi bu bicimi ogretir)
        __getattr__ = dict.get

    ns = {"__name__": "__usta_script__", "ctx": ctx, "kit": kit, "Build": core.Build, "np": np, "result": result,
          "site": _Site(ctx.get("site") or {}), "anchor": ctx.get("anchor")}
    if pre_existing is not None:
        ep = pre_existing
        eb = core.Build(ctx.get("existing_name") or "mevcut yapı")
        eb.put_ids(0, 0, 0, ep.cells, ep.palette)
        for be in ep.block_entities:
            eb.set_block_entity(*be["pos"], be["snbt"])
        ns["existing"] = eb
    for k, v in mods.items():
        if v is not None:
            ns[k] = v
    if mods.get("terrain") is not None:
        ns["terrain_kit"] = mods["terrain"]
    if pre_terrain is not None:            # arazi verisi 'terrain' adini alir (modul: terrain_kit / kit.terrain)
        ns["terrain"] = pre_terrain
    try:
        exec(compile(code, "yapi_betigi.py", "exec"), ns)
        b = captured.get("build") or ns.get("b") or ns.get("build")
        if b is None or not isinstance(b, core.Build):
            raise RuntimeError("Betik bir Build üretmedi: sonunda result(b) çağır (ya da 'b' adlı bir Build bırak).")
        if mods.get("parts") is not None:      # merdiven ustune sonradan doseme/tavan konduysa bas boslugunu geri ac
            healed = mods["parts"].heal_stairs(b)
            if healed:
                b.meta.setdefault("notes", []).append(f"merdiven baş boşluğu yeniden açıldı: {healed} hücre")
        site = ctx.get("site") or {}
        origin = captured.get("origin") or site.get("origin") or [0, 0, 0]
        facing = captured.get("facing") or site.get("facing") or "north"
        cells = 1
        for v in b.size():
            cells *= max(1, v)
        if cells > int(ctx.get("max_cells", 16_000_000)):
            raise RuntimeError(f"Yapı çok büyük ({cells} hücre); en çok {ctx.get('max_cells')}.")
        plan = b.to_plan(tuple(int(v) for v in origin), facing, meta={"label": captured.get("label") or b.name, **captured.get("meta", {}),
                                                                       "rooms": b.meta.get("rooms", []), "style": b.meta.get("style")})
        plan.save(os.path.join(workdir, "plan.uplan"))
        lb = b.bounds()
        out = {"ok": True, "label": captured.get("label") or b.name, "size": list(plan.size), "origin": list(plan.origin),
               "facing": facing, "local_bounds": [list(lb[0]), list(lb[1])] if lb else None, "changed": plan.count_changed(),
               "solid": plan.count_solid(), "palette_top": list(plan.histogram().items())[:12] if plan.count_changed() < 3_000_000 else [],
               "rooms": len(b.meta.get("rooms", [])), "limits": limits_ok, "seconds": round(time.time() - t0, 2)}
        try:
            import pickle  # noqa: F401  (yalniz on-yuklenmisse)
        except Exception:
            pass
        np.save(os.path.join(workdir, "local_ids.npy"), b.dense()[1]) if False else None
    except BaseException as e:  # noqa: BLE001
        try:
            tb = traceback.format_exc(limit=6)
        except BaseException:  # noqa: BLE001
            tb = repr(e)
        out = {"ok": False, "error": f"{type(e).__name__}: {e}", "traceback": tb[-2500:], "seconds": round(time.time() - t0, 2)}
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
