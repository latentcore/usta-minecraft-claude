package dev.usta.world;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.usta.compat.V;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.zip.GZIPOutputStream;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Holder;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.biome.Biome;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

/** Dunyadan okuma: sutun ozetleri (harita), hacim dokumu, oyuncu baglami. */
public final class WorldIO {
	private WorldIO() {}

	public static final short UNKNOWN = Short.MIN_VALUE;

	// ------------------------------------------------------------------ chunk yukleme
	/**
	 * Gerekli chunk'lari yuklu hale getirir. generate=false ise yalniz diskte var olanlar yuklenir
	 * (hic olusmamis chunk olusturulmaz). HTTP is parcacigindan cagrilir; dunya islemleri sunucuda yapilir.
	 * Donus: yuklu tutulan chunk'lar (sonra release ile birakilmali).
	 */
	public static List<ChunkPos> ensureLoaded(MinecraftServer server, ServerLevel level, List<ChunkPos> need, long timeoutMs, boolean generate) {
		long deadline = System.currentTimeMillis() + timeoutMs;
		List<ChunkPos> missing;
		try {
			missing = server.submit(() -> {
				List<ChunkPos> m = new ArrayList<>();
				for (ChunkPos cp : need) if (level.getChunkSource().getChunkNow(cp.x(), cp.z()) == null) m.add(cp);
				return m;
			}).get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
		} catch (Exception e) {
			return List.of();
		}
		if (missing.isEmpty()) return List.of();
		List<ChunkPos> toLoad = new ArrayList<>();
		if (generate) {
			toLoad.addAll(missing);
		} else {
			try {
				List<CompletableFuture<Optional<CompoundTag>>> reads = server.submit(() -> {
					List<CompletableFuture<Optional<CompoundTag>>> r = new ArrayList<>();
					for (ChunkPos cp : missing) r.add(level.getChunkSource().chunkMap.read(cp));
					return r;
				}).get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
				for (int i = 0; i < missing.size(); i++) {
					try {
						Optional<CompoundTag> t = reads.get(i).get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
						if (t.isPresent()) {
							String st = t.get().getStringOr("Status", "");
							if (st.isEmpty() || st.endsWith("full")) toLoad.add(missing.get(i));
						}
					} catch (Exception ignored) {
					}
				}
			} catch (Exception e) {
				return List.of();
			}
		}
		if (toLoad.isEmpty()) return List.of();
		try {
			List<CompletableFuture<?>> futs = server.submit(() -> {
				List<CompletableFuture<?>> f = new ArrayList<>();
				for (ChunkPos cp : toLoad) f.add(level.getChunkSource().addTicketAndLoadWithRadius(V.ticket(), cp, 0));
				return f;
			}).get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
			for (CompletableFuture<?> f : futs) {
				try {
					f.get(Math.max(1, deadline - System.currentTimeMillis()), TimeUnit.MILLISECONDS);
				} catch (Exception ignored) {
				}
			}
		} catch (Exception ignored) {
		}
		return toLoad;
	}

	public static void release(MinecraftServer server, ServerLevel level, List<ChunkPos> held) {
		if (held.isEmpty()) return;
		server.execute(() -> {
			for (ChunkPos cp : held) level.getChunkSource().removeTicketWithRadius(V.ticket(), cp, 0);
		});
	}

	public static List<ChunkPos> chunksOf(int x0, int z0, int x1, int z1) {
		List<ChunkPos> l = new ArrayList<>();
		for (int cx = x0 >> 4; cx <= x1 >> 4; cx++) for (int cz = z0 >> 4; cz <= z1 >> 4; cz++) l.add(new ChunkPos(cx, cz));
		return l;
	}

	// ------------------------------------------------------------------ sutunlar
	/** USTACOL1: gzip( "USTACOL1" | u32 bl | baslik JSON | i16 surface | u16 surfState | i16 ground | u16 groundState | i16 floor | u16 floorState | u16 biome ). */
	public static byte[] columns(ServerLevel level, int x0, int z0, int x1, int z1) throws IOException {
		int w = x1 - x0 + 1, h = z1 - z0 + 1;
		int n = w * h;
		short[] surf = new short[n], ground = new short[n], floor = new short[n];
		char[] surfS = new char[n], groundS = new char[n], floorS = new char[n], biome = new char[n];
		Map<BlockState, Integer> pal = new HashMap<>();
		List<String> palNames = new ArrayList<>();
		Map<String, Integer> bpal = new HashMap<>();
		List<String> bNames = new ArrayList<>();
		pal.put(null, 0);
		palNames.add("?");
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		int minY = level.getMinY();
		for (int cx = x0 >> 4; cx <= x1 >> 4; cx++) {
			for (int cz = z0 >> 4; cz <= z1 >> 4; cz++) {
				LevelChunk ch = level.getChunkSource().getChunkNow(cx, cz);
				for (int lx = 0; lx < 16; lx++) {
					int x = (cx << 4) + lx;
					if (x < x0 || x > x1) continue;
					for (int lz = 0; lz < 16; lz++) {
						int z = (cz << 4) + lz;
						if (z < z0 || z > z1) continue;
						int i = (z - z0) * w + (x - x0);
						if (ch == null) {
							surf[i] = ground[i] = floor[i] = UNKNOWN;
							continue;
						}
						int ys = ch.getHeight(Heightmap.Types.WORLD_SURFACE, lx, lz);
						int yg = ch.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, lx, lz);
						int yf = ch.getHeight(Heightmap.Types.OCEAN_FLOOR, lx, lz);
						surf[i] = (short) ys;
						ground[i] = (short) yg;
						floor[i] = (short) yf;
						surfS[i] = (char) palIndex(pal, palNames, ys >= minY ? ch.getBlockState(p.set(x, ys, z)) : null);
						groundS[i] = (char) palIndex(pal, palNames, yg >= minY ? ch.getBlockState(p.set(x, yg, z)) : null);
						floorS[i] = (char) palIndex(pal, palNames, yf >= minY ? ch.getBlockState(p.set(x, yf, z)) : null);
						Holder<Biome> b = level.getBiome(p.set(x, Math.max(ys, minY), z));
						String bn = b.unwrapKey().map(k -> k.identifier().toString()).orElse("?");
						Integer bi = bpal.get(bn);
						if (bi == null) {
							bi = bNames.size();
							bpal.put(bn, bi);
							bNames.add(bn);
						}
						biome[i] = (char) (int) bi;
					}
				}
			}
		}
		JsonObject hdr = new JsonObject();
		hdr.addProperty("x0", x0);
		hdr.addProperty("z0", z0);
		hdr.addProperty("w", w);
		hdr.addProperty("h", h);
		hdr.addProperty("min_y", minY);
		hdr.addProperty("max_y", level.getMaxY());
		hdr.addProperty("unknown", (int) UNKNOWN);
		hdr.addProperty("note", "surface/ground/floor = en ust blogun y'si (WORLD_SURFACE / MOTION_BLOCKING_NO_LEAVES / OCEAN_FLOOR)");
		JsonArray pa = new JsonArray();
		palNames.forEach(pa::add);
		hdr.add("palette", pa);
		JsonArray ba = new JsonArray();
		bNames.forEach(ba::add);
		hdr.add("biomes", ba);
		ByteBuffer bb = ByteBuffer.allocate(n * 14).order(ByteOrder.LITTLE_ENDIAN);
		for (short v : surf) bb.putShort(v);
		for (char v : surfS) bb.putChar(v);
		for (short v : ground) bb.putShort(v);
		for (char v : groundS) bb.putChar(v);
		for (short v : floor) bb.putShort(v);
		for (char v : floorS) bb.putChar(v);
		for (char v : biome) bb.putChar(v);
		return pack("USTACOL1", hdr, bb.array());
	}

	private static int palIndex(Map<BlockState, Integer> pal, List<String> names, BlockState s) {
		if (s == null) return 0;
		Integer i = pal.get(s);
		if (i == null) {
			i = names.size();
			pal.put(s, i);
			names.add(V.stateString(s));
		}
		return i;
	}

	// ------------------------------------------------------------------ hacim dokumu
	/** USTABLK1: gzip( "USTABLK1" | u32 bl | baslik JSON | u16 hucre[(y*sz+z)*sx+x] ). Palet 0 = bilinmiyor (yuklu degil). */
	public static byte[] blocks(ServerLevel level, int x0, int y0, int z0, int sx, int sy, int sz) throws IOException {
		int n = sx * sy * sz;
		char[] cells = new char[n];
		Map<BlockState, Integer> pal = new HashMap<>();
		List<String> names = new ArrayList<>();
		pal.put(null, 0);
		names.add("?");
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		JsonArray bes = new JsonArray();
		for (int cx = x0 >> 4; cx <= (x0 + sx - 1) >> 4; cx++) {
			for (int cz = z0 >> 4; cz <= (z0 + sz - 1) >> 4; cz++) {
				LevelChunk ch = level.getChunkSource().getChunkNow(cx, cz);
				int ax = Math.max(x0, cx << 4), bx = Math.min(x0 + sx - 1, (cx << 4) + 15);
				int az = Math.max(z0, cz << 4), bz = Math.min(z0 + sz - 1, (cz << 4) + 15);
				for (int y = 0; y < sy; y++) {
					for (int z = az; z <= bz; z++) {
						for (int x = ax; x <= bx; x++) {
							int i = (y * sz + (z - z0)) * sx + (x - x0);
							if (ch == null) {
								cells[i] = 0;
								continue;
							}
							BlockState s = ch.getBlockState(p.set(x, y0 + y, z));
							cells[i] = (char) palIndex(pal, names, s);
						}
					}
				}
				if (ch != null) {
					for (var be : ch.getBlockEntities().values()) {
						BlockPos bp = be.getBlockPos();
						if (bp.getX() < x0 || bp.getY() < y0 || bp.getZ() < z0 || bp.getX() >= x0 + sx || bp.getY() >= y0 + sy || bp.getZ() >= z0 + sz) continue;
						JsonObject o = new JsonObject();
						JsonArray pos = new JsonArray();
						pos.add(bp.getX() - x0);
						pos.add(bp.getY() - y0);
						pos.add(bp.getZ() - z0);
						o.add("pos", pos);
						o.addProperty("type", BuiltInRegistries.BLOCK_ENTITY_TYPE.getKey(be.getType()).toString());
						o.addProperty("snbt", V.saveBlockEntity(be, level.registryAccess()).toString());
						bes.add(o);
						if (bes.size() > 4000) break;
					}
				}
			}
		}
		JsonObject hdr = new JsonObject();
		JsonArray o = new JsonArray();
		o.add(x0);
		o.add(y0);
		o.add(z0);
		hdr.add("origin", o);
		JsonArray s = new JsonArray();
		s.add(sx);
		s.add(sy);
		s.add(sz);
		hdr.add("size", s);
		JsonArray pa = new JsonArray();
		names.forEach(pa::add);
		hdr.add("palette", pa);
		hdr.add("block_entities", bes);
		ByteBuffer bb = ByteBuffer.allocate(n * 2).order(ByteOrder.LITTLE_ENDIAN);
		for (char c : cells) bb.putChar(c);
		return pack("USTABLK1", hdr, bb.array());
	}

	private static byte[] pack(String magic, JsonObject hdr, byte[] body) throws IOException {
		byte[] hb = hdr.toString().getBytes(StandardCharsets.UTF_8);
		ByteArrayOutputStream bos = new ByteArrayOutputStream(body.length / 4 + hb.length + 64);
		try (GZIPOutputStream gz = new GZIPOutputStream(bos, 1 << 16)) {
			gz.write(magic.getBytes(StandardCharsets.US_ASCII));
			gz.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(hb.length).array());
			gz.write(hb);
			gz.write(body);
		}
		return bos.toByteArray();
	}

	// ------------------------------------------------------------------ baglam
	public static JsonObject playerContext(MinecraftServer server, ServerPlayer pl, int radius) {
		ServerLevel level = pl.level();
		JsonObject o = new JsonObject();
		JsonObject pp = new JsonObject();
		pp.addProperty("x", round2(pl.getX()));
		pp.addProperty("y", round2(pl.getY()));
		pp.addProperty("z", round2(pl.getZ()));
		BlockPos bp = pl.blockPosition();
		JsonArray b = new JsonArray();
		b.add(bp.getX());
		b.add(bp.getY());
		b.add(bp.getZ());
		pp.add("block", b);
		pp.addProperty("yaw", round2(pl.getYRot()));
		pp.addProperty("pitch", round2(pl.getXRot()));
		pp.addProperty("facing", pl.getDirection().getName());
		pp.addProperty("dimension", level.dimension().identifier().toString());
		pp.addProperty("gamemode", pl.gameMode().getName());
		o.add("player", pp);
		HitResult hit = pl.pick(96.0, 1.0f, false);
		if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) {
			JsonObject la = new JsonObject();
			BlockPos lp = bh.getBlockPos();
			JsonArray l = new JsonArray();
			l.add(lp.getX());
			l.add(lp.getY());
			l.add(lp.getZ());
			la.add("pos", l);
			la.addProperty("block", V.stateString(level.getBlockState(lp)));
			la.addProperty("face", bh.getDirection().getName());
			la.addProperty("distance", round2(Math.sqrt(lp.distToCenterSqr(pl.getEyePosition()))));
			la.addProperty("artificial", Classify.isArtificial(level.getBlockState(lp)));
			o.add("looking_at", la);
		}
		JsonObject w = new JsonObject();
		w.addProperty("biome", level.getBiome(bp).unwrapKey().map(k -> k.identifier().toString()).orElse("?"));
		long ticks = V.overworldClockTicks(server);
		if (ticks >= 0) {
			w.addProperty("day_time", ticks % 24000);
			w.addProperty("day", ticks / 24000);
		}
		w.addProperty("raining", level.isRaining());
		w.addProperty("thundering", level.isThundering());
		w.addProperty("difficulty", level.getDifficulty().getSerializedName());
		w.addProperty("min_y", level.getMinY());
		w.addProperty("max_y", level.getMaxY());
		w.addProperty("sea_level", level.getSeaLevel());
		w.addProperty("ground_y_here", level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, bp.getX(), bp.getZ()) - 1);
		o.add("world", w);
		AABB box = pl.getBoundingBox().inflate(radius);
		Map<String, Integer> counts = new TreeMap<>();
		JsonArray prot = new JsonArray();
		for (Entity e : level.getEntities(pl, box, e -> e.isAlive() && !(e instanceof ItemEntity) && !(e instanceof ExperienceOrb))) {
			String type = BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
			counts.merge(type, 1, Integer::sum);
			String tag = EntityGuard.tag(e);
			if (tag != null && prot.size() < 30) {
				JsonObject eo = new JsonObject();
				eo.addProperty("type", type);
				eo.addProperty("tag", tag);
				if (e.hasCustomName()) eo.addProperty("name_untrusted", e.getCustomName().getString());
				JsonArray ep = new JsonArray();
				ep.add(e.getBlockX());
				ep.add(e.getBlockY());
				ep.add(e.getBlockZ());
				eo.add("pos", ep);
				prot.add(eo);
			}
		}
		JsonObject ents = new JsonObject();
		counts.forEach(ents::addProperty);
		JsonObject en = new JsonObject();
		en.addProperty("radius", radius);
		en.add("counts", ents);
		en.add("protected", prot);
		o.add("entities", en);
		return o;
	}

	// ------------------------------------------------------------------ varliklar
	public static JsonArray entities(ServerLevel level, AABB box, boolean nbt) {
		JsonArray arr = new JsonArray();
		for (Entity e : level.getEntities((Entity) null, box, e -> true)) {
			JsonObject o = new JsonObject();
			o.addProperty("type", BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString());
			o.addProperty("uuid", e.getUUID().toString());
			JsonArray pos = new JsonArray();
			pos.add(round2(e.getX()));
			pos.add(round2(e.getY()));
			pos.add(round2(e.getZ()));
			o.add("pos", pos);
			o.addProperty("yaw", round2(e.getYRot()));
			String tag = EntityGuard.tag(e);
			if (tag != null) o.addProperty("tag", tag);
			if (nbt && !(e instanceof ServerPlayer)) {
				try {
					var t = V.saveEntity(e, level.registryAccess());
					for (String k : new String[]{"UUID", "Pos", "Motion", "Rotation", "FallDistance", "Fire", "Air", "OnGround", "PortalCooldown",
						"Invulnerable", "Age", "Brain", "LastPoiTicks"}) t.remove(k);
					o.addProperty("snbt", t.toString());
				} catch (Exception ex) {
					o.addProperty("snbt_error", ex.toString());
				}
			}
			arr.add(o);
			if (arr.size() >= 2000) break;
		}
		return arr;
	}

	private static double round2(double v) {
		return Math.round(v * 100) / 100.0;
	}
}
