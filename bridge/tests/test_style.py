import pytest

from usta.blockdb import UnknownBlock, split_state
from usta.kit import Build
from usta.kit import style
from usta.kit import shapes as S

KINDS = ("stairs", "slab", "wall")


@pytest.mark.parametrize("name", style.names())
def test_all_roles_all_biomes_resolve(name, db):
    assert len(style.names()) >= 8
    for bio in (None,) + style.BIOMES + ("minecraft:some_future_biome", "minecraft:poplar_forest"):
        st = style.get(name, bio)
        for role in style.ROLES:
            vs = st.variants(role)
            assert vs and abs(sum(w for _, w in vs) - 1.0) < 1e-6
            for i, (s, _) in enumerate(vs):
                assert db.canonical(s.lstrip("!")) == s.lstrip("!")
                if s.split("[")[0].endswith("_leaves"):
                    assert "persistent=true" in s
                for k in KINDS:
                    f = st.form(role, k, i)
                    assert db.has_block(split_state(f)[0])
        # rol turleri dogru blok ailesinden
        assert st.base("door").endswith("_door")
        assert st.base("shutter").endswith("_trapdoor")
        assert "hanging" in db.props(st.block("light"))
        assert db.light[db.id(st.block("light_block"))] >= 10
        assert st.pane().split("[")[0].endswith(("_pane", "_bars"))


def test_pick_deterministic_and_weighted():
    st = style.get("medieval")
    a = [st.pick("wall", x, 3, 0) for x in range(400)]
    assert a == [st.pick("wall", x, 3, 0) for x in range(400)]
    counts = {}
    for x in range(60):
        for y in range(40):
            s = st.pick("wall", x, y, 0)
            counts[s] = counts.get(s, 0) + 1
    main = st.variants("wall")[0][0]
    assert len(counts) >= 3
    assert 0.35 < counts[main] / 2400 < 0.75


def test_fill_textured_only_role_blocks():
    st = style.get("ottoman")
    b = Build("t")
    st.fill(b, 0, 0, 0, 15, 10, 0, "wall")
    allowed = {s for s, _ in st.variants("wall")}
    h = b.histogram()
    assert set(h) <= allowed and len(h) >= 3
    st.put_form(b, S.box(0, 12, 0, 15, 12, 0), "roof", "stairs", facing="south")
    assert any("stairs" in k for k in b.histogram())


def test_biome_adaptation():
    d = style.get("medieval").adapt("minecraft:desert")
    names = {s.split("[")[0] for r in ("wall", "foundation", "paving") for s, _ in d.variants(r)}
    assert not any(n.endswith(("stone_bricks", "cobblestone")) for n in names)
    assert any("sandstone" in n for n in names)
    sn = style.get("rustic").adapt("snowy_taiga")
    assert sn.pitch >= 1.0
    assert not any(s.startswith("minecraft:oak_") for r in style.ROLES for s, _ in sn.variants(r))
    nether = style.get("modern").adapt("minecraft:crimson_forest")
    assert "crimson" in nether.base("door") or "warped" in nether.base("door")
    j = style.get("japanese").adapt("cherry_grove")
    assert j.base("hedge") == "cherry_leaves"
    assert style.get("ottoman").adapt("plains").base("roof") == "bricks"


def test_errors():
    with pytest.raises(KeyError):
        style.get("bilinmeyen_stil")
    with pytest.raises(KeyError):
        style.get("modern").override(olmayan_rol="stone")
    with pytest.raises(UnknownBlock):
        style.get("modern").override(wall="minecraft:uydurma_blok").variants("wall")
    with pytest.raises(ValueError):
        style.derive("stone", "olmayan_tur")


def test_derive_fallbacks(db):
    assert style.derive("stone_bricks", "stairs") == "stone_brick_stairs"
    assert style.derive("quartz_block", "slab") == "quartz_slab"
    assert style.derive("stripped_spruce_log", "fence") == "spruce_fence"
    assert style.derive("calcite", "stairs") == "polished_diorite_stairs"
    for n in ("white_terracotta", "hay_block", "glowstone", "cyan_glazed_terracotta"):
        for k in ("stairs", "slab", "wall"):
            assert db.has_block(style.derive(n, k))
    st = style.get("scandinavian").with_(floor_h=5, motifs={"a"})
    assert st.floor_h == 5 and st.has("a")
    assert "iskandinav" in style.get("iskandinav").name or style.get("iskandinav").name == "scandinavian"
    assert style.get("osmanli").describe().startswith("ottoman")
