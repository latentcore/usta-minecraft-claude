"""Kus bakisi harita (U2a): sutun verisinden renkli, golgeli harita + ust katmanlar
(chunk izgarasi, koordinat etiketleri, kuzey oku, olcek cubugu, oyuncu oku ve bakis yonu, plan izi, korunan bolgeler)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ..worlddata import UNKNOWN, Columns
from .colors import colors_for
from .sheet import _font


def base_map(cols: Columns, which: str = "surface") -> np.ndarray:
    st = {"surface": cols.surface_state, "ground": cols.ground_state}[which]
    hgt = {"surface": cols.surface, "ground": cols.ground}[which]
    pal_rgb = np.zeros((len(cols.palette), 3), dtype=np.float32)
    for i, s in enumerate(cols.palette):
        if s == "?":
            pal_rgb[i] = (30, 30, 34)
            continue
        try:
            t, _, a = colors_for(s)
            pal_rgb[i] = t
        except Exception:
            pal_rgb[i] = (150, 150, 150)
    rgb = pal_rgb[st]
    known = hgt != UNKNOWN
    h = np.where(known, hgt, 0).astype(np.float32)
    hp = np.pad(h, 1, mode="edge")
    gx = (hp[1:-1, 2:] - hp[1:-1, :-2]) / 2
    gz = (hp[2:, 1:-1] - hp[:-2, 1:-1]) / 2
    shade = np.clip(1.0 - 0.10 * gx - 0.14 * gz, 0.6, 1.3)
    rgb *= shade[:, :, None]
    # su derinligi koyulastirma
    water = np.isin(cols.ground_state, [i for i, s in enumerate(cols.palette) if s.startswith("minecraft:water")])
    depth = np.clip((cols.ground - cols.floor).astype(np.float32), 0, 12)
    rgb[water] *= (1.0 - 0.04 * depth[water])[:, None]
    rgb[~known] = (30, 30, 34)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def render(cols: Columns, px_per_block: int | None = None, max_px: int = 900, player: dict | None = None,
           footprints: list[dict] | None = None, structures: list[dict] | None = None, protected: list[dict] | None = None,
           title: str | None = None) -> Image.Image:
    img = base_map(cols)
    H, W = img.shape[:2]
    s = px_per_block or max(1, min(12, max_px // max(W, H)))
    im = Image.fromarray(img).resize((W * s, H * s), Image.NEAREST)
    margin_l, margin_t, margin_b = 46, 26, 34
    out = Image.new("RGB", (im.width + margin_l + 10, im.height + margin_t + margin_b), (250, 250, 248))
    out.paste(im, (margin_l, margin_t))
    d = ImageDraw.Draw(out, "RGBA")
    f = _font(12)

    def P(x, z):
        return margin_l + (x - cols.x0) * s, margin_t + (z - cols.z0) * s

    # chunk izgarasi + etiketler
    step = 16 if W * s / 16 >= 6 else 64
    x = math.ceil(cols.x0 / step) * step
    while x <= cols.x0 + W:
        px, _ = P(x, cols.z0)
        d.line([(px, margin_t), (px, margin_t + H * s)], fill=(255, 255, 255, 70), width=1)
        if (x // step) % max(1, int(80 / (step * s)) + 1) == 0:
            d.text((px + 2, 6), str(x), fill=(60, 60, 60), font=f)
        x += step
    z = math.ceil(cols.z0 / step) * step
    while z <= cols.z0 + H:
        _, pz = P(cols.x0, z)
        d.line([(margin_l, pz), (margin_l + W * s, pz)], fill=(255, 255, 255, 70), width=1)
        if (z // step) % max(1, int(60 / (step * s)) + 1) == 0:
            d.text((4, pz - 7), str(z), fill=(60, 60, 60), font=f)
        z += step
    # korunan bolgeler
    for r in protected or []:
        a = P(r["x0"], r["z0"])
        b = P(r["x1"] + 1, r["z1"] + 1)
        d.rectangle([a, b], outline=(220, 40, 40, 255), width=2, fill=(220, 40, 40, 40))
        d.text((a[0] + 2, a[1] + 2), "korunan: " + str(r.get("name", "")), fill=(150, 20, 20), font=f)
    # mevcut yapilar
    for st in structures or []:
        a = P(st["x0"], st["z0"])
        b = P(st["x1"] + 1, st["z1"] + 1)
        d.rectangle([a, b], outline=(255, 140, 0, 255), width=1)
    # plan izleri
    for i, fp in enumerate(footprints or []):
        a = P(fp["x0"], fp["z0"])
        b = P(fp["x1"] + 1, fp["z1"] + 1)
        col = (40, 120, 255, 255) if i == 0 else (40, 120, 255, 140)
        d.rectangle([a, b], outline=col, width=3 if i == 0 else 1, fill=(40, 120, 255, 45 if i == 0 else 15))
        lab = fp.get("label") or (f"aday {i + 1}" if i else "seçilen")
        d.text((a[0] + 3, a[1] + 3), lab, fill=(10, 40, 120), font=f)
        if fp.get("facing"):
            cx, cz = (fp["x0"] + fp["x1"] + 1) / 2, (fp["z0"] + fp["z1"] + 1) / 2
            vx, vz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[fp["facing"]]
            hw = (fp["x1"] - fp["x0"] + 1) / 2 if vz else (fp["z1"] - fp["z0"] + 1) / 2
            ex, ez = cx + vx * (abs(vz) * (fp["z1"] - fp["z0"] + 1) / 2 + abs(vx) * (fp["x1"] - fp["x0"] + 1) / 2), cz + vz * (abs(vz) * (fp["z1"] - fp["z0"] + 1) / 2 + abs(vx) * (fp["x1"] - fp["x0"] + 1) / 2)
            d.line([P(cx, cz), P(ex, ez)], fill=(10, 40, 120, 255), width=2)
            del hw
    # oyuncu
    if player:
        px, pz = P(player["x"], player["z"])
        yaw = math.radians(float(player.get("yaw", 0)))
        fx, fz = -math.sin(yaw), math.cos(yaw)
        L = max(10, 3 * s)
        tip = (px + fx * L, pz + fz * L)
        left = (px - fz * L * 0.45 - fx * L * 0.3, pz + fx * L * 0.45 - fz * L * 0.3)
        right = (px + fz * L * 0.45 - fx * L * 0.3, pz - fx * L * 0.45 - fz * L * 0.3)
        d.polygon([tip, left, right], fill=(230, 30, 60, 255), outline=(255, 255, 255, 255))
        for k in range(1, 6):
            q = (px + fx * L * (1 + k), pz + fz * L * (1 + k))
            d.ellipse([q[0] - 1.5, q[1] - 1.5, q[0] + 1.5, q[1] + 1.5], fill=(230, 30, 60, 160))
    # kuzey oku + olcek
    nx, ny = out.width - 26, margin_t + 20
    d.polygon([(nx, ny - 14), (nx - 7, ny + 6), (nx + 7, ny + 6)], fill=(30, 30, 30))
    d.text((nx - 4, ny + 7), "K", fill=(30, 30, 30), font=f)
    blocks = 10 if W < 120 else 50 if W < 600 else 100
    bx0, by = margin_l, out.height - 14
    d.rectangle([bx0, by - 4, bx0 + blocks * s, by], fill=(30, 30, 30))
    d.text((bx0 + blocks * s + 6, by - 10), f"{blocks} blok", fill=(30, 30, 30), font=f)
    if title:
        d.text((margin_l + 100, out.height - 26), title, fill=(30, 30, 30), font=f)
    return out
