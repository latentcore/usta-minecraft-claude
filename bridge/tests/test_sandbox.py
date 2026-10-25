"""Kum havuzu sinir testleri (Q12): sonsuz dongu, asiri bellek, asiri cikti, izinsiz dosya yazma/okuma, ag, alt surec."""
import os
from pathlib import Path

import pytest

from usta import sandbox

GOOD = """
b = Build("deneme")
b.fill(0, 0, 0, 4, 0, 4, "stone_bricks")
b.fill(0, 1, 0, 4, 3, 4, "oak_planks", hollow=True)
result(b, origin=(10, 64, 10), facing="south")
"""


@pytest.fixture(autouse=True)
def _gamedir(tmp_path, monkeypatch):
    monkeypatch.setenv("USTA_GAME_DIR", str(tmp_path / "oyun"))
    cache = tmp_path / "oyun" / "usta" / "cache"
    cache.mkdir(parents=True)
    src = Path(__file__).parent / "data" / "blockdb-26.3.json.gz"
    (cache / "blockdb-26.3.json.gz").write_bytes(src.read_bytes())


def test_good_script_produces_plan():
    r = sandbox.run_script(GOOD, timeout=60)
    assert r["ok"], r
    assert Path(r["plan_path"]).exists()
    assert r["changed"] > 0


def test_infinite_loop_is_killed():
    r = sandbox.run_script("while True:\n    pass\n", timeout=4)
    assert not r["ok"] and "süre" in r["error"]


def test_memory_limit():
    r = sandbox.run_script("x = bytearray(3 * 1024 * 1024 * 1024)\n", timeout=30, mem_mb=512)
    assert not r["ok"]


def test_output_limit():
    r = sandbox.run_script("for i in range(200000):\n    print('x' * 100)\n", timeout=30, max_output=2000)
    assert len(r["stdout"]) < 4000


def test_file_write_outside_blocked(tmp_path):
    target = tmp_path / "kotu.txt"
    r = sandbox.run_script(f"open({str(target)!r}, 'w').write('x')\n", timeout=30)
    assert not r["ok"] and "yazılamaz" in r["error"]
    assert not target.exists()


def test_file_read_outside_blocked():
    secret = os.path.join(os.path.expanduser("~"), ".claude.json")
    r = sandbox.run_script(f"open({secret!r}).read()\n", timeout=30)
    assert not r["ok"]


def test_network_blocked():
    r = sandbox.run_script("import socket\ns = socket.socket()\ns.connect(('1.1.1.1', 80))\n", timeout=30)
    assert not r["ok"]


def test_subprocess_blocked():
    r = sandbox.run_script("import os\nos.system('echo hi')\n", timeout=30)
    assert not r["ok"] and "yasak" in r["error"]


def test_disallowed_import_blocked():
    r = sandbox.run_script("import urllib.request\n", timeout=30)
    assert not r["ok"]


def test_ctypes_blocked():
    r = sandbox.run_script("import ctypes\nctypes.windll.kernel32.Beep(440, 10)\n", timeout=30)
    assert not r["ok"]


GEN_CODE = ("c = dict(ctx)\nc['terrain'] = globals().get('terrain')\n"
            "b = gen.build({name!r}, {{}}, c)\nresult(b, origin=[0, 64, 0], facing='north', label='t')\n")


@pytest.mark.parametrize("name", ["secret_room", "arch_bridge", "house"])
def test_generator_runs_in_sandbox_with_terrain_npz(name):
    """genrun yolu: arazi .npz dosyasi + uretec kum havuzunda (tembel import / ad cakismasi regresyonu)."""
    import io
    import numpy as np
    m = 12
    g = np.zeros((60 + 2 * m, 60 + 2 * m), np.int32)
    buf = io.BytesIO()
    np.savez(buf, ground=g, water=np.zeros_like(g, bool), known=np.ones_like(g, bool), margin=np.array(m))
    r = sandbox.run_script(GEN_CODE.format(name=name), {"site": {"origin": [0, 64, 0], "facing": "north"}},
                           files={"terrain.npz": buf.getvalue()}, timeout=120)
    assert r["ok"], r.get("traceback") or r
    assert r["changed"] > 100
