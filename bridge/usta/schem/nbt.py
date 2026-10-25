"""Kucuk NBT okuyucu/yazici (Java Edition ikili NBT, big-endian; gzip). Kendi kodumuz (bagimlilik yok)."""
from __future__ import annotations

import gzip
import io
import struct
from dataclasses import dataclass
from typing import Any

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)


@dataclass
class Tag:
    """Tur bilgisi tasiyan deger (yazarken belirsiz turler icin)."""
    type: int
    value: Any


def Byte(v): return Tag(BYTE, int(v))
def Short(v): return Tag(SHORT, int(v))
def Int(v): return Tag(INT, int(v))
def Long(v): return Tag(LONG, int(v))
def Float(v): return Tag(FLOAT, float(v))
def Double(v): return Tag(DOUBLE, float(v))
def ByteArray(v): return Tag(BYTE_ARRAY, bytes(v))
def IntArray(v): return Tag(INT_ARRAY, list(v))
def LongArray(v): return Tag(LONG_ARRAY, list(v))
def List(elem_type, items): return Tag(LIST, (elem_type, list(items)))


def _infer(v) -> Tag:
    if isinstance(v, Tag):
        return v
    if isinstance(v, bool):
        return Tag(BYTE, int(v))
    if isinstance(v, int):
        return Tag(INT, v)
    if isinstance(v, float):
        return Tag(DOUBLE, v)
    if isinstance(v, str):
        return Tag(STRING, v)
    if isinstance(v, (bytes, bytearray)):
        return Tag(BYTE_ARRAY, bytes(v))
    if isinstance(v, dict):
        return Tag(COMPOUND, v)
    if isinstance(v, list):
        if not v:
            return Tag(LIST, (END, []))
        t = _infer(v[0]).type
        return Tag(LIST, (t, v))
    raise TypeError(f"NBT'ye cevrilemez: {type(v)}")


def _w_payload(out: io.BytesIO, t: Tag) -> None:
    ty, v = t.type, t.value
    if ty == BYTE:
        out.write(struct.pack(">b", v if v < 128 else v - 256))
    elif ty == SHORT:
        out.write(struct.pack(">h", v))
    elif ty == INT:
        out.write(struct.pack(">i", v))
    elif ty == LONG:
        out.write(struct.pack(">q", v if v < (1 << 63) else v - (1 << 64)))
    elif ty == FLOAT:
        out.write(struct.pack(">f", v))
    elif ty == DOUBLE:
        out.write(struct.pack(">d", v))
    elif ty == BYTE_ARRAY:
        out.write(struct.pack(">i", len(v)))
        out.write(v)
    elif ty == STRING:
        b = v.encode("utf-8")
        out.write(struct.pack(">H", len(b)))
        out.write(b)
    elif ty == LIST:
        et, items = v
        out.write(struct.pack(">bi", et, len(items)))
        for it in items:
            tt = it if isinstance(it, Tag) else Tag(et, it) if et not in (COMPOUND, LIST) or not isinstance(it, Tag) else it
            if et == COMPOUND and not isinstance(it, Tag):
                tt = Tag(COMPOUND, it)
            _w_payload(out, tt)
    elif ty == COMPOUND:
        for k, x in v.items():
            xt = _infer(x)
            out.write(struct.pack(">b", xt.type))
            kb = k.encode("utf-8")
            out.write(struct.pack(">H", len(kb)))
            out.write(kb)
            _w_payload(out, xt)
        out.write(b"\x00")
    elif ty == INT_ARRAY:
        out.write(struct.pack(">i", len(v)))
        out.write(struct.pack(f">{len(v)}i", *v))
    elif ty == LONG_ARRAY:
        out.write(struct.pack(">i", len(v)))
        vv = [x if x < (1 << 63) else x - (1 << 64) for x in v]
        out.write(struct.pack(f">{len(vv)}q", *vv))
    else:
        raise ValueError(f"bilinmeyen tur {ty}")


def dumps(root: dict, name: str = "", compress: bool = True) -> bytes:
    out = io.BytesIO()
    out.write(struct.pack(">b", COMPOUND))
    nb = name.encode("utf-8")
    out.write(struct.pack(">H", len(nb)))
    out.write(nb)
    _w_payload(out, Tag(COMPOUND, root))
    data = out.getvalue()
    return gzip.compress(data, mtime=0) if compress else data


class _R:
    def __init__(self, b: bytes):
        self.b = b
        self.i = 0

    def take(self, n):
        s = self.b[self.i:self.i + n]
        self.i += n
        return s

    def unpack(self, fmt):
        n = struct.calcsize(fmt)
        return struct.unpack(fmt, self.take(n))


def _r_payload(r: _R, ty: int):
    if ty == BYTE:
        return r.unpack(">b")[0]
    if ty == SHORT:
        return r.unpack(">h")[0]
    if ty == INT:
        return r.unpack(">i")[0]
    if ty == LONG:
        return r.unpack(">q")[0]
    if ty == FLOAT:
        return r.unpack(">f")[0]
    if ty == DOUBLE:
        return r.unpack(">d")[0]
    if ty == BYTE_ARRAY:
        (n,) = r.unpack(">i")
        return r.take(n)
    if ty == STRING:
        (n,) = r.unpack(">H")
        return r.take(n).decode("utf-8", "replace")
    if ty == LIST:
        et, n = r.unpack(">bi")
        return [_r_payload(r, et) for _ in range(n)]
    if ty == COMPOUND:
        d = {}
        while True:
            (t,) = r.unpack(">b")
            if t == END:
                return d
            (n,) = r.unpack(">H")
            k = r.take(n).decode("utf-8", "replace")
            d[k] = _r_payload(r, t)
    if ty == INT_ARRAY:
        (n,) = r.unpack(">i")
        return list(r.unpack(f">{n}i"))
    if ty == LONG_ARRAY:
        (n,) = r.unpack(">i")
        return list(r.unpack(f">{n}q"))
    raise ValueError(f"bilinmeyen NBT turu {ty}")


def loads(data: bytes) -> tuple[str, dict]:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    r = _R(data)
    (t,) = r.unpack(">b")
    if t != COMPOUND:
        raise ValueError("kok COMPOUND degil")
    (n,) = r.unpack(">H")
    name = r.take(n).decode("utf-8", "replace")
    return name, _r_payload(r, COMPOUND)
