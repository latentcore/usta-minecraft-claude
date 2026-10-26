package dev.usta.world;

import java.util.Set;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.state.BlockState;

/**
 * Dogal / yapay blok ayrimi: "mevcut yapi" tespiti ve ustune insa korumasi icin (M2, C12).
 * Dogal: arazi, bitki, agac, su, cevher. Yapay: tahta, tugla, cam, yun, beton, esya bloklari vb.
 * Uretilmis yapilar (koy, maden, zindan) yapay sayilir; bu bilincli: onlarin uzerine de insa edilmez.
 */
public final class Classify {
	private Classify() {}

	private static volatile boolean[] naturalById;

	private static final Set<String> NATURAL_NAMES = Set.of(
		"bedrock", "gravel", "clay", "mud", "pointed_dripstone", "dripstone_block", "amethyst_block", "budding_amethyst",
		"amethyst_cluster", "large_amethyst_bud", "medium_amethyst_bud", "small_amethyst_bud", "calcite", "tuff", "smooth_basalt",
		"kelp", "kelp_plant", "seagrass", "tall_seagrass", "sea_pickle", "sugar_cane", "cactus", "cactus_flower", "bamboo",
		"bamboo_sapling", "pumpkin", "melon", "brown_mushroom", "red_mushroom", "brown_mushroom_block", "red_mushroom_block",
		"mushroom_stem", "vine", "glow_lichen", "lily_pad", "sweet_berry_bush", "magma_block", "soul_sand", "soul_soil",
		"netherrack", "basalt", "end_stone", "chorus_plant", "chorus_flower", "snow_block", "powder_snow", "packed_ice",
		"blue_ice", "sculk", "sculk_vein", "sculk_catalyst", "sculk_sensor", "sculk_shrieker", "moss_carpet", "pale_moss_carpet",
		"hanging_roots", "rooted_dirt", "spore_blossom", "big_dripleaf", "big_dripleaf_stem", "small_dripleaf", "azalea",
		"flowering_azalea", "mangrove_roots", "muddy_mangrove_roots", "bee_nest", "cobweb", "dead_bush", "short_grass",
		"tall_grass", "fern", "large_fern", "snow", "ice", "frosted_ice", "water", "lava", "bubble_column", "nether_wart_block",
		"warped_wart_block", "shroomlight", "weeping_vines", "weeping_vines_plant", "twisting_vines", "twisting_vines_plant",
		"crimson_roots", "warped_roots", "nether_sprouts", "crimson_fungus", "warped_fungus", "glowstone", "ancient_debris",
		"nether_gold_ore", "nether_quartz_ore", "obsidian", "crying_obsidian", "sand", "red_sand", "suspicious_sand",
		"suspicious_gravel", "firefly_bush", "leaf_litter", "wildflowers", "bush", "short_dry_grass", "tall_dry_grass",
		"pale_hanging_moss", "pale_moss_block", "moss_block", "creaking_heart", "resin_clump", "cave_vines", "cave_vines_plant",
		"cocoa", "dried_kelp_block", "coarse_dirt", "podzol", "mycelium", "dirt_path", "farmland", "grass_block", "dirt",
		"red_sandstone", "sandstone", "terracotta",
		// arazide kendiliginden olusanlar: cevher damari bloklari, dagdaki/derindeki gumus balikli tas
		// (kale tuglasinin gumus balikli hali kalenin parcasi: yapay kalir)
		"raw_iron_block", "raw_copper_block", "infested_stone", "infested_deepslate"
	);

	public static boolean isNatural(BlockState s) {
		boolean[] arr = naturalById;
		int id = Block.getId(s);
		if (arr != null && id >= 0 && id < arr.length) return arr[id];
		return compute(s);
	}

	public static boolean isArtificial(BlockState s) {
		return !s.isAir() && !isNatural(s);
	}

	/** Tum durumlar icin onceden hesapla (sunucu acilisinda bir kez). */
	public static void init() {
		int size = Block.BLOCK_STATE_REGISTRY.size();
		boolean[] arr = new boolean[size];
		for (int i = 0; i < size; i++) {
			BlockState s = Block.stateById(i);
			arr[i] = s != null && compute(s);
		}
		naturalById = arr;
	}

	private static boolean compute(BlockState s) {
		if (s.isAir()) return true;
		Block b = s.getBlock();
		if (b instanceof LiquidBlock) return true;
		if (s.is(BlockTags.DIRT) || s.is(BlockTags.SAND) || s.is(BlockTags.BASE_STONE_OVERWORLD) || s.is(BlockTags.BASE_STONE_NETHER)
			|| s.is(BlockTags.SUBSTRATE_OVERWORLD) || s.is(BlockTags.OVERWORLD_NATURAL_LOGS) || s.is(BlockTags.LEAVES)
			|| s.is(BlockTags.SMALL_FLOWERS) || s.is(BlockTags.FLOWERS) || s.is(BlockTags.SAPLINGS) || s.is(BlockTags.ICE)
			|| s.is(BlockTags.SNOW) || s.is(BlockTags.CORALS) || s.is(BlockTags.CORAL_BLOCKS) || s.is(BlockTags.CORAL_PLANTS)
			|| s.is(BlockTags.WALL_CORALS)
			|| s.is(BlockTags.TERRACOTTA) || s.is(BlockTags.NYLIUM) || s.is(BlockTags.CAVE_VINES) || s.is(BlockTags.MOSS_BLOCKS)
			|| s.is(BlockTags.GRASS_BLOCKS) || s.is(BlockTags.REPLACEABLE_BY_TREES) || s.is(BlockTags.GOLD_ORES)
			|| s.is(BlockTags.IRON_ORES) || s.is(BlockTags.COPPER_ORES) || s.is(BlockTags.SCULK_REPLACEABLE_WORLD_GEN)) {
			return true;
		}
		String path = BuiltInRegistries.BLOCK.getKey(b).getPath();
		if (path.endsWith("_ore")) return true;
		if (path.startsWith("waterlogged")) return true;
		return NATURAL_NAMES.contains(path);
	}
}
