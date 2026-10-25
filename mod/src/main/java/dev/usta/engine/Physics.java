package dev.usta.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.piston.PistonBaseBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;

/**
 * Blok fizigi siniflandirmasi (yerlestirme sirasi, denetci ve blok veritabani icin).
 * Bit bayraklari Python tarafinda usta/blockdb.py ile aynidir.
 */
public final class Physics {
	private Physics() {}

	public static final int AIR = 1;
	public static final int FULL = 1 << 1;          // carpisma sekli tam blok
	public static final int OPAQUE = 1 << 2;        // isigi ve gorusu kapatir
	public static final int FLUID = 1 << 3;         // sivi (kaynak ya da akan) ya da suya gomulu
	public static final int GRAVITY = 1 << 4;       // dusen blok
	public static final int SUPPORT_FLOOR = 1 << 5; // alttan destek ister
	public static final int SUPPORT_WALL = 1 << 6;  // arkadan (facing tersi) destek ister
	public static final int SUPPORT_CEIL = 1 << 7;  // ustten destek ister
	public static final int DOUBLE = 1 << 8;        // iki hucreli (kapi, yatak, uzun bitki)
	public static final int CONNECT = 1 << 9;       // komsuya baglanan (cit, duvar, panel, merdiven, kizilatas)
	public static final int BLOCK_ENTITY = 1 << 10;
	public static final int FLAMMABLE = 1 << 11;
	public static final int DANGEROUS = 1 << 12;    // TNT, lav, ates: yalniz acik istekle
	public static final int WATERLOGGED = 1 << 13;
	public static final int PLANT = 1 << 14;        // toprak/cimen ister
	public static final int REDSTONE = 1 << 15;     // kizilatas bileseni
	public static final int REPLACEABLE = 1 << 16;  // cimen, kar katmani gibi ustune konulabilen
	public static final int SOLID_RENDER = 1 << 17;

	private static final java.util.Map<BlockState, Integer> CACHE = new java.util.concurrent.ConcurrentHashMap<>();

	public static int cachedFlags(BlockState s) {
		Integer v = CACHE.get(s);
		if (v == null) {
			v = flags(s);
			CACHE.put(s, v);
		}
		return v;
	}

	public static int flags(BlockState s) {
		int f = 0;
		Block b = s.getBlock();
		if (s.isAir()) f |= AIR;
		try {
			if (s.isCollisionShapeFullBlock(EmptyBlockGetter.INSTANCE, BlockPos.ZERO)) f |= FULL;
		} catch (Exception ignored) {
		}
		if (s.canOcclude()) f |= OPAQUE;
		try {
			if (s.isSolidRender()) f |= SOLID_RENDER;
		} catch (Throwable ignored) {
		}
		if (!s.getFluidState().isEmpty()) f |= FLUID;
		if (s.hasProperty(BlockStateProperties.WATERLOGGED) && s.getValue(BlockStateProperties.WATERLOGGED)) f |= WATERLOGGED;
		if (b instanceof FallingBlock) f |= GRAVITY;
		if (s.hasBlockEntity()) f |= BLOCK_ENTITY;
		if (s.ignitedByLava()) f |= FLAMMABLE;
		if (s.canBeReplaced()) f |= REPLACEABLE;
		if (b instanceof TntBlock || b == Blocks.LAVA || b instanceof BaseFireBlock) f |= DANGEROUS;

		// Destek ihtiyaci (sinifa gore; kesin denetim oyunda canSurvive ile yapilir)
		if (b instanceof WallTorchBlock || b instanceof LadderBlock || b instanceof WallSignBlock
			|| b instanceof WallBannerBlock || b instanceof WallHangingSignBlock || b instanceof WallSkullBlock
			|| b instanceof CocoaBlock || b instanceof TripWireHookBlock) {
			f |= SUPPORT_WALL;
		} else if (b instanceof FaceAttachedHorizontalDirectionalBlock && s.hasProperty(BlockStateProperties.ATTACH_FACE)) {
			switch (s.getValue(BlockStateProperties.ATTACH_FACE)) {
				case FLOOR -> f |= SUPPORT_FLOOR;
				case CEILING -> f |= SUPPORT_CEIL;
				default -> f |= SUPPORT_WALL;
			}
		} else if (b instanceof LanternBlock && s.hasProperty(BlockStateProperties.HANGING)) {
			f |= s.getValue(BlockStateProperties.HANGING) ? SUPPORT_CEIL : SUPPORT_FLOOR;
		} else if (b instanceof CeilingHangingSignBlock) {
			f |= SUPPORT_CEIL;
		} else if (b instanceof TorchBlock || b instanceof DoorBlock || b instanceof CarpetBlock
			|| b instanceof BasePressurePlateBlock || b instanceof BaseRailBlock || b instanceof RedstoneWireBlock
			|| b instanceof DiodeBlock || b instanceof StandingSignBlock || b instanceof BannerBlock
			|| b instanceof CandleBlock || b instanceof SnowLayerBlock || b instanceof CakeBlock
			|| b instanceof FlowerPotBlock || b instanceof SeaPickleBlock || b instanceof CandleCakeBlock
			|| b instanceof BedBlock && false) {
			f |= SUPPORT_FLOOR;
		}
		if (b instanceof VegetationBlock || b instanceof CactusBlock || b instanceof SugarCaneBlock
			|| b instanceof BambooStalkBlock || b instanceof KelpBlock || b instanceof KelpPlantBlock) {
			f |= SUPPORT_FLOOR | PLANT;
		}
		if (b instanceof DoorBlock || b instanceof BedBlock || b instanceof DoublePlantBlock) f |= DOUBLE;
		if (b instanceof FenceBlock || b instanceof WallBlock || b instanceof IronBarsBlock || b instanceof StairBlock
			|| b instanceof RedstoneWireBlock || b instanceof FenceGateBlock || b instanceof TripWireBlock
			|| b instanceof ChorusPlantBlock || b instanceof VineBlock) {
			f |= CONNECT;
		}
		if (b instanceof RedstoneWireBlock || b instanceof DiodeBlock || b instanceof PistonBaseBlock
			|| b instanceof ObserverBlock || b instanceof LeverBlock || b instanceof ButtonBlock
			|| b instanceof RedstoneTorchBlock || b instanceof RedstoneWallTorchBlock || b instanceof DispenserBlock
			|| b instanceof HopperBlock || b instanceof BasePressurePlateBlock || b instanceof RedstoneLampBlock
			|| b instanceof TargetBlock || b instanceof DaylightDetectorBlock || b instanceof NoteBlock) {
			f |= REDSTONE;
		}
		return f;
	}

	/** Alti yuz icin saglamlik (isFaceSturdy) bitleri: sira Direction.values() (D,U,N,S,W,E). */
	public static int sturdyFaces(BlockState s) {
		int bits = 0;
		for (Direction d : Direction.values()) {
			try {
				if (s.isFaceSturdy(EmptyBlockGetter.INSTANCE, BlockPos.ZERO, d)) bits |= 1 << d.ordinal();
			} catch (Exception ignored) {
			}
		}
		return bits;
	}

	/** Yerlestirme evresi: 0 temizlik, 1 tam bloklar, 2 tam olmayanlar, 3 destek isteyenler, 4 sivilar. */
	public static int phase(BlockState s, int flags) {
		if ((flags & AIR) != 0) return 0;
		if ((flags & (SUPPORT_FLOOR | SUPPORT_WALL | SUPPORT_CEIL | DOUBLE)) != 0) return 3;
		if (s.getBlock() instanceof LiquidBlock) return 4;
		if ((flags & FULL) != 0) return 1;
		return 2;
	}
}
