"""Bilesik gorunum sayfalari: plan/yapi icin birkac acidan kucuk ama okunur goruntuler (B11 butcesi)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .views import Volume, iso, ortho, perspective, section, top

LABEL_BG = (40, 44, 52)


def _font(size: int = 14):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def label(im: Image.Image, text: str) -> Image.Image:
    f = _font(14)
    out = Image.new("RGB", (im.width, im.height + 22), (255, 255, 255))
    out.paste(im, (0, 22))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, im.width, 21], fill=LABEL_BG)
    d.text((6, 2), text, fill=(240, 240, 240), font=f)
    return out


def fit(im: Image.Image, w: int, h: int, bg=(238, 236, 230)) -> Image.Image:
    s = min(w / im.width, h / im.height)
    nw, nh = max(1, int(im.width * s)), max(1, int(im.height * s))
    r = im.resize((nw, nh), Image.NEAREST if s >= 1 else Image.LANCZOS)
    out = Image.new("RGB", (w, h), bg)
    out.paste(r, ((w - nw) // 2, (h - nh) // 2))
    return out


def grid(images: list[tuple[str, Image.Image]], cols: int = 2, cell=(512, 384)) -> Image.Image:
    rows = (len(images) + cols - 1) // cols
    W, H = cell
    out = Image.new("RGB", (cols * W, rows * (H + 22)), (255, 255, 255))
    for i, (t, im) in enumerate(images):
        r, c = divmod(i, cols)
        out.paste(label(fit(im, W, H), t), (c * W, r * (H + 22)))
    return out


def volume_from_build(build) -> tuple[Volume, tuple[int, int, int]]:
    origin, ids = build.dense()
    return Volume(ids, build.palette, origin), origin


def floor_levels(vol: Volume, max_levels: int = 4) -> list[int]:
    """Kat kesiti icin anlamli y'ler: yatay dolulugu yuksek katmanlarin ustu."""
    s = vol.pa["solid"][vol.ids]
    sy = s.shape[0]
    cover = s.reshape(sy, -1).mean(axis=1)
    cand = [y + 1 for y in range(sy - 2) if cover[y] > 0.35 and cover[y + 1] < cover[y] * 0.8]
    out = []
    for y in cand:
        if not out or y - out[-1] >= 3:
            out.append(y)
    return out[:max_levels] or [1]


def crop_visible(vol: Volume, pad: int = 1) -> Volume:
    """Gorunur (katı ya da yari saydam) bloklarin sinir kutusuna kirpar: temizlik havasi kamerayi uzaklastirmasin."""
    vis = vol.pa["solid"][vol.ids] | (vol.pa["alpha"][vol.ids] > 0.05)
    if not vis.any():
        return vol
    ys, zs, xs = (np.flatnonzero(vis.any(axis=a)) for a in ((1, 2), (0, 2), (0, 1)))
    sl = tuple(slice(max(0, int(v[0]) - pad), int(v[-1]) + pad + 1) for v in (ys, zs, xs))
    if all(s.start == 0 and s.stop >= n for s, n in zip(sl, vol.ids.shape)):
        return vol
    o = vol.origin
    return Volume(np.ascontiguousarray(vol.ids[sl]), vol.palette, (o[0] + sl[2].start, o[1] + sl[0].start, o[2] + sl[1].start))


def sheet(vol: Volume, kind: str = "standard", front: str = "north", max_side: int = 1024) -> Image.Image:
    """kind: quick (2 gorunum) | standard (4) | full (8 + kesitler)."""
    vol = crop_visible(vol)
    sy, sz, sx = vol.ids.shape
    cx, cy, cz = sx / 2, sy * 0.3, sz / 2
    dist = max(sx, sz) * 0.72 + sy * 0.3 + 4
    fv = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[front]
    eye = (cx + fv[0] * dist + 0.6 * dist * (1 if fv[1] != 0 else 0), sy * 0.45 + dist * 0.3, cz + fv[1] * dist + 0.6 * dist * (1 if fv[0] != 0 else 0))
    views: list[tuple[str, Image.Image]] = []
    if kind == "quick":
        views = [("İzometrik (GD)", iso(vol, "se", max_px=640)), ("Ön cephe", ortho(vol, front, max_px=520))]
        return grid(views, cols=2, cell=(max_side // 2, int(max_side * 0.36)))
    views = [("İzometrik (GD)", iso(vol, "se", max_px=640)), ("İzometrik (KB)", iso(vol, "nw", max_px=640)),
             ("Ön cephe (" + front + ")", ortho(vol, front, max_px=520)),
             ("Perspektif", perspective(vol, eye, (cx, cy, cz), size=(560, 360)))]
    if kind == "full":
        back = {"north": "south", "south": "north", "east": "west", "west": "east"}[front]
        side1 = {"north": "east", "south": "west", "east": "south", "west": "north"}[front]
        side2 = {"north": "west", "south": "east", "east": "north", "west": "south"}[front]
        views += [("Arka cephe (" + back + ")", ortho(vol, back, max_px=520)), ("Yan (" + side1 + ")", ortho(vol, side1, max_px=520)),
                  ("Yan (" + side2 + ")", ortho(vol, side2, max_px=520)), ("Üstten", top(vol, max_px=520)),
                  ("İzometrik (KD)", iso(vol, "ne", max_px=640)), ("İzometrik (GB)", iso(vol, "sw", max_px=640))]
        for y in floor_levels(vol):
            views.append((f"Kat kesiti y={y}", section(vol, y, max_px=520)))
        cols = 3
        return grid(views, cols=cols, cell=(max_side // cols, int(max_side // cols * 0.75)))
    return grid(views, cols=2, cell=(max_side // 2, int(max_side * 0.36)))


def save_preview(build_or_vol, path: str | Path, kind: str = "standard", front: str = "north") -> str:
    vol = build_or_vol if isinstance(build_or_vol, Volume) else volume_from_build(build_or_vol)[0]
    im = sheet(vol, kind=kind, front=front)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return str(path)


def to_jpeg_bytes(im: Image.Image, max_side: int = 1024, quality: int = 82) -> bytes:
    import io
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=quality, optimize=True)
    return b.getvalue()


__all__ = ["sheet", "save_preview", "grid", "label", "fit", "to_jpeg_bytes", "volume_from_build", "np"]
