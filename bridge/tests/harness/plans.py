"""Q2/Q3 test planlari: her biri zor bir yerlestirme durumunu sinar. Yerel koordinat, duz dunya zemini y=0 (dunyada -61)."""
from __future__ import annotations

from usta.kit.core import Build

FACES = ("north", "east", "south", "west")


def p_stairs(b: Build):
    for i, f in enumerate(FACES):
        b.set(i * 2, 1, 0, f"oak_stairs[facing={f},half=bottom]")
        b.set(i * 2, 1, 2, f"!stone_brick_stairs[facing={f},half=top,shape=straight]")


def p_logs(b: Build):
    for i, ax in enumerate("xyz"):
        b.set(i * 2, 1, 0, f"oak_log[axis={ax}]")
        b.set(i * 2, 1, 2, f"stripped_birch_log[axis={ax}]")


def p_facing_blocks(b: Build):
    for i, f in enumerate(FACES):
        b.set(i * 2, 1, 0, f"furnace[facing={f}]")
        b.set(i * 2, 1, 2, f"observer[facing={f}]")
        b.set(i * 2, 1, 4, f"piston[facing={f}]")


def p_doors(b: Build):
    b.fill(0, 0, 0, 8, 0, 2, "stone")
    for i, f in enumerate(FACES):
        hinge = "left" if i % 2 == 0 else "right"
        b.set(i * 2, 1, 1, f"oak_door[facing={f},half=lower,hinge={hinge}]")
        b.set(i * 2, 2, 1, f"oak_door[facing={f},half=upper,hinge={hinge}]")


def p_beds(b: Build):
    for i, f in enumerate(FACES):
        x, z = i * 3, 2
        dx, dz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[f]
        b.set(x, 1, z, f"red_bed[facing={f},part=foot]")
        b.set(x + dx, 1, z + dz, f"red_bed[facing={f},part=head]")


def p_tall_plants(b: Build):
    b.fill(0, 0, 0, 8, 0, 0, "grass_block")
    for i, n in enumerate(("sunflower", "rose_bush", "peony", "lilac", "tall_grass")):
        b.set(i * 2, 1, 0, f"{n}[half=lower]")
        b.set(i * 2, 2, 0, f"{n}[half=upper]")


def p_torches(b: Build):
    b.fill(0, 0, 0, 6, 0, 6, "stone")
    b.fill(3, 1, 3, 3, 3, 3, "stone")
    b.set(0, 1, 0, "torch")
    b.set(3, 2, 2, "wall_torch[facing=north]")
    b.set(3, 2, 4, "wall_torch[facing=south]")
    b.set(4, 2, 3, "wall_torch[facing=east]")
    b.set(2, 2, 3, "wall_torch[facing=west]")
    b.set(6, 1, 6, "soul_torch")


def p_lanterns(b: Build):
    b.fill(0, 4, 0, 6, 4, 2, "oak_planks")
    b.fill(0, 0, 0, 6, 0, 2, "stone")
    b.set(1, 3, 1, "lantern[hanging=true]")
    b.set(3, 1, 1, "lantern[hanging=false]")
    b.set(5, 3, 1, "soul_lantern[hanging=true]")
    b.set(5, 2, 1, "chain[axis=y]") if False else None


def p_buttons_levers(b: Build):
    b.fill(0, 0, 0, 8, 0, 4, "stone")
    b.fill(0, 1, 4, 8, 3, 4, "stone_bricks")
    b.fill(0, 4, 0, 8, 4, 4, "stone_bricks")
    b.set(1, 2, 3, "stone_button[face=wall,facing=north]")
    b.set(3, 2, 3, "lever[face=wall,facing=north]")
    b.set(5, 1, 1, "oak_button[face=floor,facing=north]")
    b.set(7, 3, 1, "lever[face=ceiling,facing=east]")


def p_ladders(b: Build):
    b.fill(2, 1, 2, 2, 4, 2, "oak_planks")
    b.fill(2, 0, 2, 2, 0, 2, "oak_planks")
    for f, (dx, dz) in (("north", (0, -1)), ("south", (0, 1)), ("east", (1, 0)), ("west", (-1, 0))):
        for y in range(1, 5):
            b.set(2 + dx, y, 2 + dz, f"ladder[facing={f}]")


def p_carpets_plates(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "oak_planks")
    for i, c in enumerate(("red", "white", "blue", "lime")):
        b.set(i, 1, 0, f"{c}_carpet")
    b.set(0, 1, 2, "stone_pressure_plate")
    b.set(2, 1, 2, "oak_pressure_plate")
    b.set(4, 1, 2, "heavy_weighted_pressure_plate")


def p_signs(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "stone")
    b.fill(0, 1, 2, 6, 2, 2, "stone_bricks")
    b.set(1, 1, 0, "oak_sign[rotation=8]")
    b.set_block_entity(1, 1, 0, '{front_text:{messages:["Usta","test","",""],color:"black",has_glowing_text:0b},back_text:{messages:["","","",""]},is_waxed:1b}')
    b.set(3, 2, 1, "spruce_wall_sign[facing=north]")
    b.set_block_entity(3, 2, 1, '{front_text:{messages:["Duvar","tabelası","",""],color:"blue",has_glowing_text:1b},back_text:{messages:["","","",""]},is_waxed:1b}')
    b.fill(0, 4, 0, 6, 4, 2, "oak_planks")
    b.set(5, 3, 1, "oak_hanging_sign[rotation=0,attached=false]")
    b.set_block_entity(5, 3, 1, '{front_text:{messages:["Asma","","",""]},back_text:{messages:["","","",""]},is_waxed:1b}')


def p_banners(b: Build):
    b.fill(0, 0, 0, 4, 0, 2, "stone")
    b.set(1, 1, 1, "red_banner[rotation=0]")
    b.set_block_entity(1, 1, 1, '{patterns:[{color:"white",pattern:"minecraft:circle"},{color:"red",pattern:"minecraft:stripe_left"}]}')
    b.fill(0, 1, 3, 4, 3, 3, "stone_bricks")
    b.set(3, 2, 2, "blue_wall_banner[facing=north]")


def p_flower_pots(b: Build):
    b.fill(0, 0, 0, 6, 0, 0, "oak_planks")
    for i, n in enumerate(("potted_poppy", "potted_cactus", "potted_fern", "flower_pot")):
        b.set(i * 2, 1, 0, n)


def p_gravity(b: Build):
    b.fill(0, 0, 0, 8, 0, 0, "stone")
    for i, n in enumerate(("sand", "gravel", "red_concrete_powder", "red_sand")):
        b.fill(i * 2, 1, 0, i * 2, 4, 0, n)
    b.set(8, 1, 0, "anvil[facing=north]")


def p_gravity_on_slab(b: Build):
    b.fill(0, 0, 0, 4, 0, 0, "stone")
    b.set(0, 1, 0, "stone_slab[type=top]")
    b.set(0, 2, 0, "sand")
    b.set(2, 1, 0, "scaffolding[distance=0,bottom=false]") if False else None


def p_waterlogged(b: Build):
    b.fill(0, 0, 0, 8, 0, 2, "stone")
    b.set(0, 1, 1, "oak_stairs[facing=east,waterlogged=true]")
    b.set(2, 1, 1, "oak_slab[type=bottom,waterlogged=true]")
    b.set(4, 1, 1, "!oak_fence[waterlogged=true]")
    b.set(6, 1, 1, "lantern[waterlogged=true]")
    b.set(8, 1, 1, "sea_pickle[pickles=3,waterlogged=true]")


def p_pool(b: Build):
    b.fill(0, 0, 0, 6, 2, 6, "stone_bricks")
    b.fill(1, 1, 1, 5, 2, 5, "water")


def p_lava_pool(b: Build):
    b.fill(0, 0, 0, 4, 1, 4, "deepslate_bricks")
    b.fill(1, 1, 1, 3, 1, 3, "lava")


def p_fences(b: Build):
    b.fill(0, 1, 0, 6, 1, 0, "oak_fence")
    b.fill(0, 1, 0, 0, 1, 4, "oak_fence")
    b.set(3, 1, 0, "oak_fence_gate[facing=north]")


def p_walls(b: Build):
    b.fill(0, 1, 0, 6, 2, 0, "cobblestone_wall")
    b.fill(6, 1, 0, 6, 1, 4, "cobblestone_wall")
    b.set(3, 3, 0, "torch")


def p_panes(b: Build):
    b.fill(0, 1, 0, 5, 3, 0, "glass_pane")
    b.fill(0, 1, 2, 5, 1, 2, "iron_bars")
    b.fill(0, 1, 4, 2, 1, 4, "white_stained_glass_pane")


def p_stair_corners(b: Build):
    b.set(0, 1, 0, "oak_stairs[facing=north]")
    b.set(1, 1, 0, "oak_stairs[facing=north]")
    b.set(2, 1, 0, "oak_stairs[facing=north]")
    b.set(0, 1, 1, "oak_stairs[facing=west]")
    b.set(0, 1, 2, "oak_stairs[facing=west]")
    b.set(5, 1, 0, "stone_stairs[facing=south]")
    b.set(5, 1, 1, "stone_stairs[facing=east]")


def p_redstone(b: Build):
    b.fill(0, 0, 0, 8, 0, 4, "stone")
    b.fill(0, 1, 2, 6, 1, 2, "redstone_wire")
    b.set(7, 1, 2, "repeater[facing=west,delay=2]")
    b.set(8, 1, 2, "redstone_lamp")
    b.set(0, 1, 0, "redstone_torch")
    b.set(3, 1, 4, "comparator[facing=north,mode=compare]")


def p_chest_items(b: Build):
    b.fill(0, 0, 0, 4, 0, 2, "stone")
    b.set(0, 1, 1, "chest[facing=south,type=single]")
    b.set_block_entity(0, 1, 1, '{Items:[{Slot:0b,count:5,id:"minecraft:diamond"},{Slot:13b,count:64,id:"minecraft:oak_planks"}]}')
    b.set(2, 1, 1, "chest[facing=south,type=right]")
    b.set(3, 1, 1, "chest[facing=south,type=left]")
    b.set_block_entity(2, 1, 1, '{Items:[{Slot:0b,count:1,id:"minecraft:apple"}]}')


def p_barrel_furnace(b: Build):
    b.fill(0, 0, 0, 4, 0, 0, "stone")
    b.set(0, 1, 0, "barrel[facing=up]")
    b.set_block_entity(0, 1, 0, '{Items:[{Slot:1b,count:3,id:"minecraft:bread"}]}')
    b.set(2, 1, 0, "furnace[facing=south]")
    b.set_block_entity(2, 1, 0, '{Items:[{Slot:0b,count:4,id:"minecraft:iron_ore"}]}')
    b.set(4, 1, 0, "smoker[facing=south]")


def p_misc_be(b: Build):
    b.fill(0, 0, 0, 8, 0, 0, "stone")
    b.set(0, 1, 0, "decorated_pot")
    b.set(2, 1, 0, "brewing_stand")
    b.set(4, 1, 0, "lectern[facing=north]")
    b.set(6, 1, 0, "chiseled_bookshelf[facing=north]")
    b.set(8, 1, 0, "enchanting_table")


def p_item_frames(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "stone")
    b.fill(0, 1, 2, 6, 3, 2, "oak_planks")
    b.add_entity("minecraft:item_frame", 1.5, 2.5, 1.5, 0, 0, '{Facing:2b,Item:{count:1,id:"minecraft:compass"}}')
    b.add_entity("minecraft:glow_item_frame", 3.5, 2.5, 1.5, 0, 0, '{Facing:2b,Item:{count:1,id:"minecraft:map"}}')


def p_paintings(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "stone")
    b.fill(0, 1, 2, 6, 4, 2, "spruce_planks")
    b.add_entity("minecraft:painting", 2.5, 2.5, 1.5, 0, 0, '{facing:2b,variant:"minecraft:kebab"}')


def p_armor_stand(b: Build):
    b.fill(0, 0, 0, 2, 0, 2, "stone")
    b.add_entity("minecraft:armor_stand", 1.5, 1.0, 1.5, 180, 0, '{equipment:{head:{count:1,id:"minecraft:iron_helmet"},chest:{count:1,id:"minecraft:iron_chestplate"}}}')


def p_crops(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "farmland[moisture=7]")
    b.set(3, 0, 1, "water")
    for x in range(7):
        for z in range(3):
            if (x, z) != (3, 1):
                b.set(x, 1, z, "wheat[age=7]" if x < 3 else "carrots[age=5]")


def p_sugar_cactus(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "sand")
    b.set(1, 0, 1, "water")
    b.fill(2, 1, 1, 2, 3, 1, "sugar_cane")
    b.fill(5, 1, 1, 5, 3, 1, "cactus")


def p_flowers(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "grass_block")
    for i, n in enumerate(("poppy", "dandelion", "blue_orchid", "allium", "oxeye_daisy", "cornflower", "lily_of_the_valley")):
        b.set(i, 1, 1, n)
    b.set(0, 1, 0, "oak_sapling")
    b.set(2, 1, 0, "short_grass")


def p_rails(b: Build):
    b.fill(0, 0, 0, 6, 0, 4, "stone")
    b.fill(0, 1, 0, 4, 1, 0, "rail[shape=east_west]")
    b.set(5, 1, 0, "rail[shape=south_west]")
    b.fill(5, 1, 1, 5, 1, 3, "powered_rail[shape=north_south,powered=false]")


def p_candles_cake(b: Build):
    b.fill(0, 0, 0, 6, 0, 0, "oak_planks")
    b.set(0, 1, 0, "candle[candles=3]")
    b.set(2, 1, 0, "cake")
    b.set(4, 1, 0, "white_candle_cake")
    b.set(6, 1, 0, "snow[layers=4]")


def p_chains_rods(b: Build):
    b.fill(0, 5, 0, 6, 5, 0, "stone")
    b.fill(0, 0, 0, 6, 0, 0, "stone")
    b.fill(1, 2, 0, 1, 4, 0, "iron_chain[axis=y]")
    b.set(1, 1, 0, "lantern[hanging=true]")
    b.set(3, 1, 0, "end_rod[facing=up]")
    b.set(5, 1, 0, "lightning_rod[facing=up]")


def p_amethyst(b: Build):
    b.fill(0, 0, 0, 4, 2, 2, "amethyst_block")
    b.fill(1, 1, 1, 3, 2, 2, "air")
    b.set(1, 1, 1, "amethyst_cluster[facing=up]")
    b.set(3, 2, 2, "large_amethyst_bud[facing=down]") if False else None


def p_slabs_mixed(b: Build):
    b.fill(0, 1, 0, 4, 1, 0, "stone_slab[type=bottom]")
    b.fill(0, 1, 1, 4, 1, 1, "oak_slab[type=top]")
    b.fill(0, 1, 2, 4, 1, 2, "smooth_quartz_slab[type=double]")


def p_trapdoors(b: Build):
    b.fill(0, 0, 0, 6, 0, 2, "stone")
    for i, f in enumerate(FACES):
        b.set(i * 2, 1, 0, f"oak_trapdoor[facing={f},half=top,open=false]")
        b.set(i * 2, 1, 2, f"iron_trapdoor[facing={f},half=bottom,open=true]")


def p_vines_leaves(b: Build):
    b.fill(0, 1, 0, 0, 4, 0, "oak_log[axis=y]")
    b.fill(-1, 4, -1, 1, 5, 1, "oak_leaves[persistent=true]")
    b.set(1, 3, 0, "vine[west=true]")
    b.set(1, 2, 0, "vine[west=true]")


def p_large_mix(b: Build):
    b.fill(0, 0, 0, 15, 0, 15, "polished_andesite")
    b.fill(0, 1, 0, 15, 5, 15, "white_concrete", hollow=True)
    b.fill(1, 1, 1, 14, 5, 14, "air")
    b.fill(0, 6, 0, 15, 6, 15, "dark_oak_planks")
    for x in range(2, 14, 3):
        b.fill(x, 2, 0, x, 3, 0, "glass_pane")
    b.set(7, 1, 0, "oak_door[facing=south,half=lower]")
    b.set(7, 2, 0, "oak_door[facing=south,half=upper]")
    b.set(7, 5, 7, "lantern[hanging=true]")


def p_clear_area(b: Build):
    """Mevcut zemini temizleyip doldurur (hava ve keep karisik)."""
    b.fill(0, -1, 0, 5, -1, 5, "air")
    b.fill(0, -2, 0, 5, -2, 5, "stone")
    b.set(2, -1, 2, "water")


def p_bubble(b: Build):
    b.fill(0, 0, 0, 2, 5, 2, "glass")
    b.fill(1, 1, 1, 1, 4, 1, "water")
    b.set(1, 0, 1, "soul_sand")


def p_heads(b: Build):
    b.fill(0, 0, 0, 4, 0, 0, "stone")
    b.set(0, 1, 0, "skeleton_skull[rotation=8]")
    b.set(2, 1, 0, "zombie_head[rotation=4]")
    b.set(4, 1, 0, "creeper_head[rotation=0]")


def p_bell_lectern(b: Build):
    b.fill(0, 0, 0, 4, 0, 2, "stone")
    b.set(0, 1, 1, "bell[attachment=floor,facing=north]")
    b.fill(2, 3, 1, 4, 3, 1, "oak_planks")
    b.set(3, 2, 1, "bell[attachment=ceiling,facing=north]")


def p_campfire_safe(b: Build):
    b.fill(0, 0, 0, 4, 0, 4, "cobblestone")
    b.set(2, 1, 2, "campfire[lit=false]")


PLANS = {name[2:]: fn for name, fn in globals().items() if name.startswith("p_") and callable(fn)}
DANGEROUS = {"lava_pool"}
