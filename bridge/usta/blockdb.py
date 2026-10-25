"""Blok veritabani: oyunun kendi kaydindan (mod calisma aninda cikarir) durumlar, ozellikler, fizik bayraklari,
dondurme/aynalama tablolari, harita renkleri. Uydurma blok/ozellik burada yakalanir (onceki hatalar #9)."""
from __future__ import annotations

import difflib
import gzip
import json
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import config

# Java Physics ile ayni bitler
AIR = 1
FULL = 1 << 1
OPAQUE = 1 << 2
FLUID = 1 << 3
GRAVITY = 1 << 4
SUPPORT_FLOOR = 1 << 5
SUPPORT_WALL = 1 << 6
SUPPORT_CEIL = 1 << 7
DOUBLE = 1 << 8
CONNECT = 1 << 9
BLOCK_ENTITY = 1 << 10
FLAMMABLE = 1 << 11
DANGEROUS = 1 << 12
WATERLOGGED = 1 << 13
PLANT = 1 << 14
REDSTONE = 1 << 15
REPLACEABLE = 1 << 16
SOLID_RENDER = 1 << 17
SUPPORT_ANY = SUPPORT_FLOOR | SUPPORT_WALL | SUPPORT_CEIL

# Direction.values() sirasi: DOWN, UP, NORTH, SOUTH, WEST, EAST
FACE_BIT = {"down": 1, "up": 2, "north": 4, "south": 8, "west": 16, "east": 32}


class UnknownBlock(ValueError):
    pass


def split_state(s: str) -> tuple[str, dict[str, str]]:
    s = s.strip()
    if s.startswith("!"):
        s = s[1:]
    name, props = s, {}
    if "[" in s:
        name, rest = s.split("[", 1)
        rest = rest.rstrip("]")
        for part in rest.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise UnknownBlock(f"özellik biçimi hatalı: '{part}' ({s})")
            k, v = part.split("=", 1)
            props[k.strip()] = v.strip()
    name = name.strip()
    if ":" not in name:
        name = "minecraft:" + name
    return name, props


class BlockDB:
    def __init__(self, obj: dict):
        self.mc = obj.get("mc")
        self.data_version = obj.get("data_version")
        self.states: list[str] = obj["states"]
        self.index = {s: i for i, s in enumerate(self.states)}
        self.blocks: dict[str, dict] = {b["name"]: b for b in obj["blocks"]}
        self.flags = np.asarray(obj["flags"], dtype=np.int64)
        self.light = np.asarray(obj["light"], dtype=np.int32)
        self.map_color = np.asarray(obj["map_color"], dtype=np.int64)
        self.rot90 = np.asarray(obj["rot90"], dtype=np.int64)
        self.mirror_lr = np.asarray(obj["mirror_lr"], dtype=np.int64)
        self.mirror_fb = np.asarray(obj["mirror_fb"], dtype=np.int64)
        self.sturdy = np.asarray(obj["sturdy"], dtype=np.int64)
        self.natural = np.asarray(obj.get("natural", [0] * len(self.states)), dtype=np.int8)
        # her blok icin ozellik sirasi (kanonik dizgiden)
        self._order: dict[str, list[str]] = {}
        for name, b in self.blocks.items():
            first = self.states[b["first"]]
            _, props = split_state(first)
            self._order[name] = list(props.keys())
        self._names = list(self.blocks.keys())

    # ---- yukleme
    @staticmethod
    def from_file(path: Path) -> "BlockDB":
        with gzip.open(path, "rb") as f:
            return BlockDB(json.loads(f.read().decode("utf-8")))

    # ---- sorgu
    def has_block(self, name: str) -> bool:
        if ":" not in name:
            name = "minecraft:" + name
        return name in self.blocks

    def suggest(self, name: str, n: int = 3) -> list[str]:
        short = [x.split(":", 1)[1] for x in self._names]
        q = name.split(":", 1)[-1]
        return difflib.get_close_matches(q, short, n=n, cutoff=0.6)

    @lru_cache(maxsize=65536)
    def canonical(self, s: str) -> str:
        """'oak_stairs[facing=east]' -> eksik ozellikler varsayilanla doldurulmus kanonik dizgi."""
        name, props = split_state(s)
        b = self.blocks.get(name)
        if b is None:
            sug = self.suggest(name)
            raise UnknownBlock(f"bu sürümde böyle bir blok yok: '{name}'" + (f" (bunu mu demek istedin: {', '.join(sug)})" if sug else ""))
        allowed = b["props"]
        default = self.states[b["default"]]
        _, dprops = split_state(default)
        out = dict(dprops)
        for k, v in props.items():
            if k not in allowed:
                raise UnknownBlock(f"'{name}' bloğunda '{k}' özelliği yok (olanlar: {', '.join(allowed) or 'yok'})")
            if v not in allowed[k]:
                raise UnknownBlock(f"'{name}' için {k}='{v}' geçersiz (geçerli: {', '.join(allowed[k])})")
            out[k] = v
        order = self._order[name]
        if not order:
            return name
        return name + "[" + ",".join(f"{k}={out[k]}" for k in order) + "]"

    def id(self, s: str) -> int:
        return self.index[self.canonical(s)]

    def try_id(self, s: str) -> int | None:
        try:
            return self.id(s)
        except Exception:
            return None

    def props(self, s: str) -> dict[str, str]:
        return split_state(self.canonical(s))[1]

    def name(self, s: str) -> str:
        return split_state(s)[0]

    def flags_of(self, s: str) -> int:
        return int(self.flags[self.id(s)])

    def is_air(self, s: str) -> bool:
        return bool(self.flags_of(s) & AIR)

    def is_full(self, s: str) -> bool:
        return bool(self.flags_of(s) & FULL)

    def with_props(self, s: str, **kv) -> str:
        name, props = split_state(self.canonical(s))
        props.update({k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in kv.items()})
        return self.canonical(name + "[" + ",".join(f"{k}={v}" for k, v in props.items()) + "]")

    def rotate(self, s: str, times: int) -> str:
        i = self.id(s)
        for _ in range(times % 4):
            i = int(self.rot90[i])
        return self.states[i]

    def mirror(self, s: str, axis: str) -> str:
        """axis='x': x koordinatlari ters (dogu<->bati, oyunda FRONT_BACK); axis='z': kuzey<->guney (LEFT_RIGHT)."""
        i = self.id(s)
        i = int(self.mirror_fb[i] if axis == "x" else self.mirror_lr[i])
        return self.states[i]

    def map_rgb(self, s: str) -> tuple[int, int, int]:
        c = int(self.map_color[self.id(s)])
        return (c >> 16) & 255, (c >> 8) & 255, c & 255


_DB: BlockDB | None = None
_LOCK = threading.Lock()


def db_path() -> Path:
    return config.cache_dir() / f"blockdb-{config.MC}.json.gz"


def get() -> BlockDB:
    """Onbellekten ya da calisan oyundan blok veritabanini yukler."""
    global _DB
    with _LOCK:
        if _DB is not None:
            return _DB
        p = db_path()
        if not p.exists():
            from .gameapi import GameAPI
            data = GameAPI().blockdb_bytes()
            p.write_bytes(data)
        _DB = BlockDB.from_file(p)
        return _DB


def set_db(db: BlockDB) -> None:
    global _DB
    _DB = db
