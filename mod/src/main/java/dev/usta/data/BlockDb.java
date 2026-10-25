package dev.usta.data;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.usta.compat.V;
import dev.usta.core.Paths;
import dev.usta.engine.Physics;
import dev.usta.world.Classify;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.GZIPOutputStream;
import net.minecraft.SharedConstants;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Mirror;
import net.minecraft.world.level.block.Rotation;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;

/**
 * Blok veritabani: oyunun kendi kaydindan calisma aninda cikarilir (dagitilmaz).
 * Python tarafi bununla durum dogrular, dondurur/aynalar, fizik ve harita rengi bilir.
 */
public final class BlockDb {
	private BlockDb() {}

	public static Path file() {
		return Paths.cache().resolve("blockdb-" + V.MC + ".json.gz");
	}

	@SuppressWarnings({"rawtypes", "unchecked"})
	public static JsonObject build() {
		Map<BlockState, Integer> index = new IdentityHashMap<>();
		JsonArray states = new JsonArray();
		JsonArray blocks = new JsonArray();
		int i = 0;
		for (Block b : BuiltInRegistries.BLOCK) {
			List<BlockState> ps = b.getStateDefinition().getPossibleStates();
			JsonObject bo = new JsonObject();
			bo.addProperty("name", BuiltInRegistries.BLOCK.getKey(b).toString());
			bo.addProperty("first", i);
			bo.addProperty("count", ps.size());
			JsonObject props = new JsonObject();
			for (Property p : b.getStateDefinition().getProperties()) {
				JsonArray vals = new JsonArray();
				for (Object v : p.getPossibleValues()) vals.add(p.getName((Comparable) v));
				props.add(p.getName(), vals);
			}
			bo.add("props", props);
			for (BlockState s : ps) {
				index.put(s, i++);
				states.add(V.stateString(s));
			}
			bo.addProperty("default", index.get(b.defaultBlockState()));
			blocks.add(bo);
		}
		int n = i;
		JsonArray flags = new JsonArray(), light = new JsonArray(), mapc = new JsonArray(), rot = new JsonArray(),
			mlr = new JsonArray(), mfb = new JsonArray(), sturdy = new JsonArray(), natural = new JsonArray();
		for (Block b : BuiltInRegistries.BLOCK) {
			for (BlockState s : b.getStateDefinition().getPossibleStates()) {
				flags.add(Physics.flags(s));
				light.add(s.getLightEmission());
				int col;
				try {
					col = s.getMapColor(EmptyBlockGetter.INSTANCE, BlockPos.ZERO).col;
				} catch (Exception e) {
					col = 0;
				}
				mapc.add(col);
				rot.add(idx(index, s.rotate(Rotation.CLOCKWISE_90)));
				mlr.add(idx(index, s.mirror(Mirror.LEFT_RIGHT)));
				mfb.add(idx(index, s.mirror(Mirror.FRONT_BACK)));
				sturdy.add(Physics.sturdyFaces(s));
				natural.add(Classify.isNatural(s) ? 1 : 0);
			}
		}
		JsonObject o = new JsonObject();
		o.addProperty("mc", V.MC);
		o.addProperty("data_version", SharedConstants.getCurrentVersion().dataVersion().version());
		o.addProperty("count", n);
		o.add("blocks", blocks);
		o.add("states", states);
		o.add("flags", flags);
		o.add("light", light);
		o.add("map_color", mapc);
		o.add("rot90", rot);
		o.add("mirror_lr", mlr);
		o.add("mirror_fb", mfb);
		o.add("sturdy", sturdy);
		o.add("natural", natural);
		return o;
	}

	private static int idx(Map<BlockState, Integer> index, BlockState s) {
		Integer v = index.get(s);
		return v == null ? -1 : v;
	}

	/** Dosyayi yazar (yoksa ya da eskiyse) ve yolunu dondurur. */
	public static Path ensure() throws IOException {
		Path f = file();
		if (Files.exists(f) && Files.size(f) > 1000) return f;
		JsonObject o = build();
		ByteArrayOutputStream bos = new ByteArrayOutputStream();
		try (GZIPOutputStream gz = new GZIPOutputStream(bos)) {
			gz.write(o.toString().getBytes(StandardCharsets.UTF_8));
		}
		Paths.writeAtomic(f, bos.toByteArray());
		return f;
	}
}
