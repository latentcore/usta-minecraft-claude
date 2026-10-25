package dev.usta.compat;

import com.mojang.brigadier.exceptions.CommandSyntaxException;
import net.minecraft.commands.arguments.blocks.BlockStateParser;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.TicketType;
import net.minecraft.util.ProblemReporter;
import net.minecraft.world.clock.WorldClock;
import net.minecraft.world.clock.WorldClocks;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntitySpawnRequest;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.storage.TagValueInput;
import net.minecraft.world.level.storage.TagValueOutput;
import org.jspecify.annotations.Nullable;

/**
 * Surume bagli cagrilarin tek yeri (Minecraft 26.3). Bir sonraki surume tasirken once burasi guncellenir.
 */
public final class V {
	private V() {}

	public static final String MC = "26.3";

	/** Yerlestirme: istemciye gonder, komsu guncellemesi/dusen esya/onPlace/blok varligi yan etkisi yok. */
	public static final int PLACE_FLAGS = Block.UPDATE_CLIENTS | Block.UPDATE_SKIP_ALL_SIDEEFFECTS;
	/** Yerlesme turu: yalniz bu blogun durumu degisir, yayilim yok. */
	public static final int SETTLE_FLAGS = Block.UPDATE_CLIENTS | Block.UPDATE_SKIP_ALL_SIDEEFFECTS;

	/** Kayit (registry) eklememek icin vanilla bilet turu: zaman asimsiz, kalici degil, yukler. */
	public static TicketType ticket() {
		return TicketType.DRAGON;
	}

	public static HolderLookup<Block> blockLookup(MinecraftServer server) {
		return server.registryAccess().lookupOrThrow(Registries.BLOCK);
	}

	public static BlockStateParser.BlockResult parseState(HolderLookup<Block> lookup, String s) throws CommandSyntaxException {
		return BlockStateParser.parseForBlock(lookup, s, false);
	}

	public static String stateString(BlockState s) {
		return BlockStateParser.serialize(s);
	}

	public static CompoundTag parseSnbt(String s) throws CommandSyntaxException {
		return TagParser.parseCompoundFully(s);
	}

	public static CompoundTag saveBlockEntity(BlockEntity be, HolderLookup.Provider reg) {
		return be.saveWithoutMetadata(reg);
	}

	public static void loadBlockEntity(BlockEntity be, CompoundTag tag, HolderLookup.Provider reg) {
		CompoundTag t = tag.copy();
		t.remove("x");
		t.remove("y");
		t.remove("z");
		t.remove("id");
		be.loadWithComponents(TagValueInput.create(ProblemReporter.DISCARDING, reg, t));
		be.setChanged();
	}

	public static CompoundTag saveEntity(Entity e, HolderLookup.Provider reg) {
		TagValueOutput out = TagValueOutput.createWithContext(ProblemReporter.DISCARDING, reg);
		e.save(out);
		return out.buildResult();
	}

	public static @Nullable Entity loadEntity(CompoundTag tag, ServerLevel level) {
		return EntityType.loadEntityRecursive(tag, level, new EntitySpawnRequest(EntitySpawnReason.LOAD, true), e -> e);
	}

	public static void sendBlockUpdated(ServerLevel level, BlockPos pos, BlockState state) {
		level.sendBlockUpdated(pos, state, state, Block.UPDATE_CLIENTS);
	}

	/** Overworld saatinin toplam tikleri (26.x dunya saatleri). */
	public static long overworldClockTicks(MinecraftServer server) {
		try {
			var holder = server.registryAccess().lookupOrThrow(Registries.WORLD_CLOCK).getOrThrow(WorldClocks.OVERWORLD);
			return server.clockManager().getInstance(holder).totalTicks();
		} catch (Exception e) {
			return -1L;
		}
	}

	public static void setOverworldClockTicks(MinecraftServer server, long ticks) {
		var holder = server.registryAccess().lookupOrThrow(Registries.WORLD_CLOCK).getOrThrow(WorldClocks.OVERWORLD);
		server.clockManager().setTotalTicks(holder, ticks);
	}

	@SuppressWarnings("unused")
	private static Class<?> keep = WorldClock.class;
}
