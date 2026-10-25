package dev.usta.engine;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.usta.compat.V;
import dev.usta.core.Paths;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.minecraft.core.HolderLookup;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.StringTag;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/** Is verisinin diske yazimi: jobs/<id>/data.nbt (gzip) + journal.json. Dunya klasorunun DISINDA. */
public final class JobStore {
	private JobStore() {}

	private static final java.util.concurrent.ExecutorService IO = java.util.concurrent.Executors.newSingleThreadExecutor(r -> {
		Thread t = new Thread(r, "usta-io");
		t.setDaemon(true);
		return t;
	});

	/** Diske yazmayi sunucu is parcacigini bekletmeden yapar (buyuk islerde tick'i korur). */
	public static java.util.concurrent.CompletableFuture<Void> saveAsync(Path worldDir, Job j) {
		return java.util.concurrent.CompletableFuture.runAsync(() -> {
			try {
				save(worldDir, j);
			} catch (IOException e) {
				throw new java.util.concurrent.CompletionException(e);
			}
		}, IO);
	}

	public static Path dir(Path worldDir, String id) {
		return worldDir.resolve("jobs").resolve(id);
	}

	/** Durum dizisini palet + indeks olarak yazar. */
	private static void putStates(CompoundTag tag, String key, BlockState[] states, int count) {
		Map<BlockState, Integer> pal = new HashMap<>();
		ListTag names = new ListTag();
		int[] ids = new int[count];
		for (int i = 0; i < count; i++) {
			BlockState s = states == null ? null : states[i];
			if (s == null) {
				ids[i] = -1;
				continue;
			}
			Integer id = pal.get(s);
			if (id == null) {
				id = pal.size();
				pal.put(s, id);
				names.add(StringTag.valueOf(V.stateString(s)));
			}
			ids[i] = id;
		}
		CompoundTag t = new CompoundTag();
		t.put("palette", names);
		t.putIntArray("ids", ids);
		tag.put(key, t);
	}

	private static BlockState[] getStates(CompoundTag tag, String key, HolderLookup<Block> lookup, int count) {
		CompoundTag t = tag.getCompoundOrEmpty(key);
		ListTag names = t.getListOrEmpty("palette");
		BlockState[] pal = new BlockState[names.size()];
		for (int i = 0; i < names.size(); i++) {
			String s = names.getStringOr(i, "minecraft:air");
			try {
				pal[i] = V.parseState(lookup, s).blockState();
			} catch (Exception e) {
				pal[i] = Blocks.AIR.defaultBlockState();
			}
		}
		int[] ids = t.getIntArray("ids").orElse(new int[0]);
		if (ids.length != count) return null;
		BlockState[] out = new BlockState[count];
		for (int i = 0; i < count; i++) out[i] = ids[i] < 0 ? null : pal[ids[i]];
		return out;
	}

	private static ListTag beList(Map<Integer, CompoundTag> map) {
		ListTag l = new ListTag();
		for (var e : map.entrySet()) {
			CompoundTag c = new CompoundTag();
			c.putInt("i", e.getKey());
			c.put("t", e.getValue());
			l.add(c);
		}
		return l;
	}

	private static void readBe(ListTag l, Map<Integer, CompoundTag> into) {
		for (int k = 0; k < l.size(); k++) {
			CompoundTag c = l.getCompoundOrEmpty(k);
			into.put(c.getIntOr("i", -1), c.getCompoundOrEmpty("t"));
		}
	}

	private static ListTag uuidList(List<UUID> ids) {
		ListTag l = new ListTag();
		for (UUID u : ids) l.add(StringTag.valueOf(u.toString()));
		return l;
	}

	private static ListTag movedList(List<Job.Moved> moved) {
		ListTag l = new ListTag();
		for (Job.Moved m : moved) {
			CompoundTag c = new CompoundTag();
			c.putString("id", m.id().toString());
			c.putDouble("x", m.x());
			c.putDouble("y", m.y());
			c.putDouble("z", m.z());
			c.putFloat("yaw", m.yaw());
			c.putFloat("pitch", m.pitch());
			c.putDouble("nx", m.nx());
			c.putDouble("ny", m.ny());
			c.putDouble("nz", m.nz());
			l.add(c);
		}
		return l;
	}

	public static void save(Path worldDir, Job j) throws IOException {
		CompoundTag t = new CompoundTag();
		t.putInt("v", 1);
		t.putString("id", j.id);
		t.putString("kind", j.kind.name());
		t.putString("label", j.label == null ? "" : j.label);
		t.putString("dim", j.level.dimension().identifier().toString());
		t.putIntArray("box", new int[]{j.ox, j.oy, j.oz, j.sx, j.sy, j.sz});
		t.putInt("n", j.n);
		t.putIntArray("idx", j.idx);
		putStates(t, "target", j.target, j.n);
		if (j.before != null && j.before.length == j.n) putStates(t, "before", j.before, j.n);
		boolean[] st = j.settle;
		if (st != null && st.length == j.n) {
			int[] s = new int[j.n];
			for (int i = 0; i < j.n; i++) s[i] = st[i] ? 1 : 0;
			t.putIntArray("settle", s);
		}
		t.put("targetBE", beList(j.targetBE));
		t.put("beforeBE", beList(j.beforeBE));
		t.put("spawned", uuidList(j.spawned));
		t.put("moved", movedList(j.moved));
		ListTag ents = new ListTag();
		for (Plan.EntitySpec e : j.spawn) {
			CompoundTag c = new CompoundTag();
			c.putString("type", e.type());
			c.putDouble("x", e.x());
			c.putDouble("y", e.y());
			c.putDouble("z", e.z());
			c.putFloat("yaw", e.yaw());
			c.putFloat("pitch", e.pitch());
			c.putString("snbt", e.snbt());
			ents.add(c);
		}
		t.put("spawn", ents);
		t.putString("meta", j.meta.toString());
		Path d = dir(worldDir, j.id);
		Files.createDirectories(d);
		Path tmp = d.resolve("data.nbt.tmp");
		NbtIo.writeCompressed(t, tmp);
		Files.move(tmp, d.resolve("data.nbt"), java.nio.file.StandardCopyOption.REPLACE_EXISTING, java.nio.file.StandardCopyOption.ATOMIC_MOVE);
	}

	public static void journal(Path worldDir, Job j, boolean clean) {
		JsonObject o = new JsonObject();
		o.addProperty("id", j.id);
		o.addProperty("kind", j.kind.name());
		o.addProperty("state", j.state.name());
		o.addProperty("cursor", j.cursor);
		o.addProperty("clean", clean);
		o.addProperty("mode", j.mode.name());
		o.addProperty("seconds", j.seconds);
		o.addProperty("source", j.source);
		o.addProperty("label", j.label);
		o.addProperty("ref", j.refJob);
		o.addProperty("request", j.requestId);
		o.addProperty("updated", System.currentTimeMillis());
		try {
			Paths.writeAtomic(dir(worldDir, j.id).resolve("journal.json"), o.toString());
		} catch (IOException ignored) {
		}
	}

	public static JsonObject readJournal(Path worldDir, String id) {
		try {
			Path f = dir(worldDir, id).resolve("journal.json");
			if (!Files.exists(f)) return null;
			return JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
		} catch (Exception e) {
			return null;
		}
	}

	/** Diskten tam is verisini yukler (seviye cagiran tarafindan verilir). */
	public static Job load(Path worldDir, String id, java.util.function.Function<String, net.minecraft.server.level.ServerLevel> levelOf, HolderLookup<Block> lookup) throws IOException {
		Path f = dir(worldDir, id).resolve("data.nbt");
		CompoundTag t = NbtIo.readCompressed(f, NbtAccounter.unlimitedHeap());
		int[] box = t.getIntArray("box").orElseThrow();
		int n = t.getIntOr("n", 0);
		Job j = new Job(id, Job.Kind.valueOf(t.getStringOr("kind", "BUILD")), t.getStringOr("label", ""), levelOf.apply(t.getStringOr("dim", "minecraft:overworld")),
			box[0], box[1], box[2], box[3], box[4], box[5], n);
		j.idx = t.getIntArray("idx").orElse(new int[0]);
		j.target = getStates(t, "target", lookup, n);
		j.before = t.contains("before") ? getStates(t, "before", lookup, n) : null;
		int[] s = t.getIntArray("settle").orElse(null);
		j.settle = new boolean[n];
		if (s != null && s.length == n) for (int i = 0; i < n; i++) j.settle[i] = s[i] != 0;
		readBe(t.getListOrEmpty("targetBE"), j.targetBE);
		readBe(t.getListOrEmpty("beforeBE"), j.beforeBE);
		ListTag sp = t.getListOrEmpty("spawned");
		for (int k = 0; k < sp.size(); k++) j.spawned.add(UUID.fromString(sp.getStringOr(k, "")));
		ListTag mv = t.getListOrEmpty("moved");
		for (int k = 0; k < mv.size(); k++) {
			CompoundTag c = mv.getCompoundOrEmpty(k);
			j.moved.add(new Job.Moved(UUID.fromString(c.getStringOr("id", "")), c.getDoubleOr("x", 0), c.getDoubleOr("y", 0), c.getDoubleOr("z", 0),
				c.getFloatOr("yaw", 0), c.getFloatOr("pitch", 0), c.getDoubleOr("nx", 0), c.getDoubleOr("ny", 0), c.getDoubleOr("nz", 0)));
		}
		ListTag ents = t.getListOrEmpty("spawn");
		for (int k = 0; k < ents.size(); k++) {
			CompoundTag c = ents.getCompoundOrEmpty(k);
			j.spawn.add(new Plan.EntitySpec(c.getStringOr("type", ""), c.getDoubleOr("x", 0), c.getDoubleOr("y", 0), c.getDoubleOr("z", 0),
				c.getFloatOr("yaw", 0), c.getFloatOr("pitch", 0), c.getStringOr("snbt", "{}")));
		}
		try {
			j.meta = JsonParser.parseString(t.getStringOr("meta", "{}")).getAsJsonObject();
		} catch (Exception ignored) {
		}
		return j;
	}

	public static long dirSize(Path p) {
		try (var s = Files.walk(p)) {
			return s.filter(Files::isRegularFile).mapToLong(f -> {
				try {
					return Files.size(f);
				} catch (IOException e) {
					return 0L;
				}
			}).sum();
		} catch (IOException e) {
			return 0L;
		}
	}
}
