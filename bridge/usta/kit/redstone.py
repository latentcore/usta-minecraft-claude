"""Kizilatas (redstone) mekanizmalari: vanilla kurallarla calisan kucuk devreler. Yedisi de oyunda gercek oyuncu
etkilesimiyle denendi (26 Ekim; dugme/kol: istemciden sag tik, plaka: ustune cikma, gun isigi: saat; KANIT/acik_isler_2026-10-26).
Her fonksiyon Build'e bloklari yazar ve b.meta["redstone"] listesine bir kayit ekler:
  {"kind", "trigger": [x,y,z] (kol/dugme/plaka), "outputs": [[x,y,z]...], "closed": durum aciklamasi}
Motor yerlestirme bittiginde devreleri bir kez "uyandirir" (komsu guncellemesi), boylece guc durumlari oyunun kendi
kuraliyla hesaplanir. Yerel cerceve: duvar duzlemi z0, "dis" (genel oda) -z, "ic" (gizli taraf) +z.

Mekanizmalar (MECHANISMS):
  hidden_piston_door  1x2 gizli kapi: duvar malzemesinden iki blok, yapiskan pistonlarla yana kayar; kol ACIK -> kapi acik.
                      Pistonlar duvar duzleminde, dis yuzde kaplama + ayni gorunumde susleme nisleri: kapi bir nis gibi gorunur.
  iron_door_buttons   Demir kapi + iki yanda dugme (yalniz kizilatasla acilir).
  pressure_door       Basinc plakali otomatik demir kapi (iki yanda plaka).
  night_lamps         Gun isigi algilayici (ters) + kizilatas lambalar: gece kendiliginden yanar.
  lever_lights        Kol + tel hatti; lambalar telin altinda zemine gomulu (oda/yol isigi anahtari).
  doorbell            Dugme + nota blogu (kapi zili).
  secret_hatch        Demir tuzak kapi + kol (gizli zemin kapagi).
"""
from __future__ import annotations

from .core import Build

MECHANISMS = ["hidden_piston_door", "iron_door_buttons", "pressure_door", "night_lamps", "lever_lights", "doorbell",
              "secret_hatch"]


def _rec(b: Build, kind: str, trigger, outputs, **kw) -> dict:
    r = {"kind": kind, "trigger": list(trigger) if trigger else None, "outputs": [list(o) for o in outputs]}
    r.update(kw)
    b.meta.setdefault("redstone", []).append(r)
    return r


def hidden_piston_door(b: Build, x0: int, y: int, z0: int, wall: str = "stone_bricks", clad: str | None = None,
                       lever_side: str = "east", niches: int = 2, niche_fill: str = "bookshelf") -> dict:
    """(x0, y, z0): kapi acikliginin alt hucresi (y = zemin + 1), duvar duzlemi z0; dis taraf z0-1.
    Kapali: duvar malzemesinden iki blok aciklikta (pistonlar uzamis, mesale onlari besler).
    Kol (dis yuzde, diz hizasi) ACILINCA mesale soner -> pistonlar ceker -> aciklik bosalir.
    Yerlesim (dogu tarafi): x0+1 piston basi, x0+2 yapiskan pistonlar, x0+3 mesale + ustunde blok, x0+4 kolun blogu.
    Dis kaplama (z0-1) x0+1..x0+4'u ortuyor; kapi sutunu x0'da dis kaplama yok (nis gibi gorunur) ve ayni gorunumde
    `niches` adet susleme nisi (arka yuzu niche_fill) kapiyi gizler."""
    clad = clad or wall
    s = 1 if lever_side == "east" else -1
    face_w = "west" if s > 0 else "east"
    # duvar govdesi ve dis kaplama
    for dx in range(-1, 6):
        X = x0 + s * dx
        for yy in range(y, y + 3):
            if dx == 0 and yy < y + 2:
                continue
            if b.get_id(X, yy, z0) <= 1:
                b.set(X, yy, z0, wall)
    for dx in range(1, 5):
        X = x0 + s * dx
        for yy in range(y, y + 3):
            b.set(X, yy, z0 - 1, clad)
    b.set(x0, y + 2, z0 - 1, clad)
    # kapali konum: iki kapi blogu aciklikta, piston baslari, uzamis yapiskan pistonlar
    for yy in (y, y + 1):
        b.set(x0, yy, z0, wall)
        b.set(x0 + s, yy, z0, f"piston_head[facing={face_w},short=false,type=sticky]")
        b.set(x0 + 2 * s, yy, z0, f"sticky_piston[extended=true,facing={face_w}]")
    # ters cevirici: mesale (A blogunun yan yuzunde) alt pistonu besler, ustundeki blok (C) ust pistonu besler
    b.set(x0 + 4 * s, y, z0, wall)                                     # A
    b.set(x0 + 3 * s, y, z0, f"redstone_wall_torch[facing={face_w},lit=true]")
    b.set(x0 + 3 * s, y + 1, z0, wall)                                 # C
    b.set(x0 + 4 * s, y + 1, z0, wall)
    b.set(x0 + 3 * s, y + 2, z0, wall)
    # kol: A'nin dis yuzunde (z0-1), diz hizasi; kaplamada bu hucre bos
    b.set(x0 + 4 * s, y, z0 - 1, "lever[face=wall,facing=north,powered=false]")
    # susleme nisleri: kapi sutunu gibi, karsi tarafta (kapi bunlardan biri gibi gorunur)
    for k in range(1, niches + 1):
        X = x0 - s * 3 * k
        for yy in (y, y + 1):
            b.set(X, yy, z0, niche_fill)
            for dxx in (-1, 1):
                if b.get_id(X + dxx, yy, z0 - 1) <= 1:
                    b.set(X + dxx, yy, z0 - 1, clad)
        b.set(X, y + 2, z0 - 1, clad)
        b.set(X, y + 2, z0, wall)
    return _rec(b, "hidden_piston_door", (x0 + 4 * s, y, z0 - 1), [(x0, y, z0), (x0, y + 1, z0)],
                closed="kol kapali: kapi bloklari aciklikta", open="kol acik: aciklik bos (pistonlar ceker)",
                doorway=[x0, y, z0])


def iron_door_buttons(b: Build, x: int, y: int, z: int, facing: str = "south", button: str = "stone_button") -> dict:
    """(x,y,z) demir kapinin alt yarisi (duvar duzleminde). Iki yanda dugmeler (kapinin sag ust yanindaki duvarda)."""
    b.set(x, y, z, f"iron_door[facing={facing},half=lower,hinge=left,open=false,powered=false]")
    b.set(x, y + 1, z, f"iron_door[facing={facing},half=upper,hinge=left,open=false,powered=false]")
    dz = 1 if facing == "south" else -1 if facing == "north" else 0
    dx = 1 if facing == "east" else -1 if facing == "west" else 0
    side = (1, 0) if dz else (0, 1)
    wx, wz = x + side[0], z + side[1]
    btns = []
    for sgn in (1, -1):
        bx, bz = wx + dx * sgn, wz + dz * sgn
        f = {(0, 1): "south", (0, -1): "north", (1, 0): "east", (-1, 0): "west"}[(dx * sgn, dz * sgn)]
        b.set(bx, y + 1, bz, f"{button}[face=wall,facing={f},powered=false]")
        btns.append((bx, y + 1, bz))
    return _rec(b, "iron_door_buttons", btns[0], [(x, y, z)], wall_cell=[wx, y + 1, wz])


def pressure_door(b: Build, x: int, y: int, z: int, facing: str = "south", plate: str = "stone_pressure_plate") -> dict:
    """Demir kapi + iki yaninda basinc plakasi (otomatik kapi)."""
    b.set(x, y, z, f"iron_door[facing={facing},half=lower,hinge=left,open=false,powered=false]")
    b.set(x, y + 1, z, f"iron_door[facing={facing},half=upper,hinge=left,open=false,powered=false]")
    dz = 1 if facing in ("south", "north") else 0
    dx = 1 if facing in ("east", "west") else 0
    plates = [(x + dx, y, z + dz), (x - dx, y, z - dz)]
    for (px, py, pz) in plates:
        b.set(px, py, pz, f"{plate}[powered=false]")
    return _rec(b, "pressure_door", plates[0], [(x, y, z)])


def night_lamps(b: Build, x: int, y: int, z: int, lamps: list | None = None) -> dict:
    """(x,y,z) ters gun isigi algilayicisi (ustu acik olmali). lamps: algilayiciya bitisik kizilatas lamba hucreleri
    (varsayilan dort yan). Gece algilayici guc verir -> lambalar yanar."""
    b.set(x, y, z, "daylight_detector[inverted=true,power=0]")
    lamps = lamps or [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1)]
    for (lx, ly, lz) in lamps:
        b.set(lx, ly, lz, "redstone_lamp[lit=false]")
    return _rec(b, "night_lamps", (x, y, z), lamps, note="gece (gok isigi < 7) yanar")


def lever_lights(b: Build, x: int, y: int, z: int, length: int = 6, axis: str = "x", lamp_every: int = 3) -> dict:
    """Zeminde kol + tel hatti; aralikli kizilatas lambalar telin ALTINDA, zemine gomulu (tel ustunde durdugu blogu besler,
    hat lambalarin ustunden kesintisiz gecer: hepsi yanar). (x,y,z) kolun hucresi (y = zemin + 1); lambalar y-1'de.
    (Lamba hattin icinde olsaydi yalniz ilki yanardi: telle beslenen lamba sonraki teli beslemez; oyunda denendi.)"""
    b.set(x, y, z, "lever[face=floor,facing=east,powered=false]")
    outs = []
    for k in range(1, length + 1):
        X, Z = (x + k, z) if axis == "x" else (x, z + k)
        b.set(X, y, Z, "redstone_wire[east=side,west=side,north=none,south=none,power=0]" if axis == "x"
              else "redstone_wire[north=side,south=side,east=none,west=none,power=0]")
        if k % lamp_every == 0:
            b.set(X, y - 1, Z, "redstone_lamp[lit=false]")
            outs.append((X, y - 1, Z))
    return _rec(b, "lever_lights", (x, y, z), outs)


def doorbell(b: Build, x: int, y: int, z: int, facing: str = "north", instrument: str = "bell") -> dict:
    """(x,y,z) dugmenin hucresi; dugme (x,y,z)'de, arkasindaki blok nota blogu (dugme onu dogrudan besler)."""
    back = {"north": (0, 1), "south": (0, -1), "east": (-1, 0), "west": (1, 0)}[facing]
    nx, nz = x + back[0], z + back[1]
    b.set(nx, y, nz, f"note_block[instrument={instrument},note=12,powered=false]")
    b.set(x, y, z, f"oak_button[face=wall,facing={facing},powered=false]")
    return _rec(b, "doorbell", (x, y, z), [(nx, y, nz)])


def secret_hatch(b: Build, x: int, y: int, z: int, lever_at: tuple | None = None) -> dict:
    """(x,y,z) zemin kapagi hucresi: demir tuzak kapi (kapali). Bitisik kol acar. lever_at: kolun hucresi (zemin ustu)."""
    b.set(x, y, z, "iron_trapdoor[facing=north,half=top,open=false,powered=false]")
    lx, ly, lz = lever_at or (x + 1, y + 1, z)
    b.set(lx, ly, lz, "lever[face=floor,facing=north,powered=false]")
    return _rec(b, "secret_hatch", (lx, ly, lz), [(x, y, z)])


__all__ = MECHANISMS + ["MECHANISMS", "Build"]
