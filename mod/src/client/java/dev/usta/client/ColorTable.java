package dev.usta.client;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.mojang.blaze3d.platform.NativeImage;
import dev.usta.UstaMod;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.zip.GZIPOutputStream;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.server.packs.resources.Resource;
import net.minecraft.server.packs.resources.ResourceManager;
import net.minecraft.world.level.block.Block;

/**
 * Doku renk tablosu (B8, M7): oyunun YUKLU kaynaklarindan (kaynak paketleri dahil) calisma aninda her blok icin
 * ust ve yan yuzun ortalama doku rengini cikarir. Dokularin kendisi kopyalanmaz/dagitilmaz; yalniz ortalama renk yazilir.
 * Yontem: blockstates JSON -> ilk model -> ebeveyn zinciri -> textures haritasi -> PNG ortalamasi (+ cimen/yaprak/su tonu).
 */
final class ColorTable {
	private ColorTable() {}

	private static final int GRASS = 0x91BD59, FOLIAGE = 0x77AB2F, WATER = 0x3F76E4;

	static CompletableFuture<JsonObject> ensure(Path out) {
		CompletableFuture<JsonObject> f = new CompletableFuture<>();
		Minecraft mc = Minecraft.getInstance();
		Thread t = new Thread(() -> {
			try {
				f.complete(build(mc.getResourceManager(), out));
			} catch (Throwable e) {
				UstaMod.LOG.warn("Renk tablosu cikarilamadi", e);
				f.completeExceptionally(e);
			}
		}, "usta-renk");
		t.setDaemon(true);
		t.start();
		return f;
	}

	private static JsonObject readJson(ResourceManager rm, String ns, String path) {
		try {
			Optional<Resource> r = rm.getResource(Identifier.fromNamespaceAndPath(ns, path));
			if (r.isEmpty()) return null;
			try (InputStream in = r.get().open(); InputStreamReader rd = new InputStreamReader(in, StandardCharsets.UTF_8)) {
				return JsonParser.parseReader(rd).getAsJsonObject();
			}
		} catch (Exception e) {
			return null;
		}
	}

	private static String firstModel(JsonObject bs) {
		if (bs == null) return null;
		if (bs.has("variants")) {
			for (Map.Entry<String, JsonElement> e : bs.getAsJsonObject("variants").entrySet()) {
				JsonElement v = e.getValue();
				if (v.isJsonArray()) v = v.getAsJsonArray().get(0);
				if (v.isJsonObject() && v.getAsJsonObject().has("model")) return v.getAsJsonObject().get("model").getAsString();
			}
		}
		if (bs.has("multipart")) {
			for (JsonElement part : bs.getAsJsonArray("multipart")) {
				JsonElement ap = part.getAsJsonObject().get("apply");
				if (ap == null) continue;
				if (ap.isJsonArray()) ap = ap.getAsJsonArray().get(0);
				if (ap.isJsonObject() && ap.getAsJsonObject().has("model")) return ap.getAsJsonObject().get("model").getAsString();
			}
		}
		return null;
	}

	/** Model ebeveyn zinciri boyunca textures haritasini birlestirir; tintindex var mi? */
	private static Map<String, String> textures(ResourceManager rm, String modelId, boolean[] tinted) {
		Map<String, String> tex = new HashMap<>();
		String cur = modelId;
		for (int depth = 0; depth < 12 && cur != null; depth++) {
			Identifier id = Identifier.parse(cur);
			JsonObject m = readJson(rm, id.getNamespace(), "models/" + id.getPath() + ".json");
			if (m == null) break;
			if (m.has("textures")) {
				for (Map.Entry<String, JsonElement> e : m.getAsJsonObject("textures").entrySet()) {
					if (e.getValue().isJsonPrimitive()) tex.putIfAbsent(e.getKey(), e.getValue().getAsString());
				}
			}
			if (m.has("elements") && m.toString().contains("tintindex")) tinted[0] = true;
			cur = m.has("parent") ? m.get("parent").getAsString() : null;
		}
		return tex;
	}

	private static String resolve(Map<String, String> tex, String key) {
		String v = tex.get(key);
		for (int i = 0; i < 8 && v != null && v.startsWith("#"); i++) v = tex.get(v.substring(1));
		return v;
	}

	private static final Map<String, int[]> AVG_CACHE = new HashMap<>();

	/** {r, g, b, alpha*255} */
	private static int[] average(ResourceManager rm, String texId) {
		if (texId == null) return null;
		int[] c = AVG_CACHE.get(texId);
		if (c != null) return c;
		Identifier id = Identifier.parse(texId);
		try {
			Optional<Resource> r = rm.getResource(Identifier.fromNamespaceAndPath(id.getNamespace(), "textures/" + id.getPath() + ".png"));
			if (r.isEmpty()) return null;
			try (InputStream in = r.get().open(); NativeImage img = NativeImage.read(in)) {
				int w = img.getWidth(), h = Math.min(img.getHeight(), w); // animasyonlu dokularda ilk kare
				long sr = 0, sg = 0, sb = 0, sa = 0, n = 0;
				for (int y = 0; y < h; y++) {
					for (int x = 0; x < w; x++) {
						int argb = img.getPixel(x, y);
						int a = (argb >>> 24) & 255;
						n++;
						if (a < 16) continue;
						sr += (long) ((argb >> 16) & 255) * a;
						sg += (long) ((argb >> 8) & 255) * a;
						sb += (long) (argb & 255) * a;
						sa += a;
					}
				}
				if (sa == 0) c = new int[]{0, 0, 0, 0};
				else c = new int[]{(int) (sr / sa), (int) (sg / sa), (int) (sb / sa), (int) (sa / Math.max(1, n))};
			}
		} catch (Exception e) {
			c = null;
		}
		AVG_CACHE.put(texId, c);
		return c;
	}

	private static int[] tint(int[] c, int rgb) {
		if (c == null) return null;
		return new int[]{c[0] * ((rgb >> 16) & 255) / 255, c[1] * ((rgb >> 8) & 255) / 255, c[2] * (rgb & 255) / 255, c[3]};
	}

	static JsonObject build(ResourceManager rm, Path out) throws Exception {
		long t0 = System.currentTimeMillis();
		JsonObject blocks = new JsonObject();
		int ok = 0, miss = 0;
		for (Block b : BuiltInRegistries.BLOCK) {
			Identifier key = BuiltInRegistries.BLOCK.getKey(b);
			JsonObject bs = readJson(rm, key.getNamespace(), "blockstates/" + key.getPath() + ".json");
			String model = firstModel(bs);
			if (model == null) {
				miss++;
				continue;
			}
			boolean[] tinted = {false};
			Map<String, String> tex = textures(rm, model, tinted);
			String topT = null, sideT = null;
			for (String k : new String[]{"top", "end", "up", "all", "texture", "cross", "plant", "pattern", "particle"}) {
				topT = resolve(tex, k);
				if (topT != null) break;
			}
			for (String k : new String[]{"side", "all", "texture", "front", "north", "wall", "cross", "plant", "particle"}) {
				sideT = resolve(tex, k);
				if (sideT != null) break;
			}
			int[] top = average(rm, topT), side = average(rm, sideT);
			if (top == null && side == null) {
				miss++;
				continue;
			}
			if (top == null) top = side;
			if (side == null) side = top;
			String path = key.getPath();
			if (tinted[0]) {
				int tc = path.contains("water") ? WATER : (path.contains("leaves") || path.contains("vine")) ? FOLIAGE
					: (path.contains("grass") || path.contains("fern") || path.contains("sugar_cane")) ? GRASS : -1;
				if (tc != -1) {
					top = tint(top, tc);
					if (!path.equals("grass_block")) side = tint(side, tc);
				}
			}
			if (path.equals("water")) top = side = new int[]{63, 118, 228, 180};
			JsonObject o = new JsonObject();
			com.google.gson.JsonArray ta = new com.google.gson.JsonArray(), sa = new com.google.gson.JsonArray();
			ta.add(top[0]);
			ta.add(top[1]);
			ta.add(top[2]);
			sa.add(side[0]);
			sa.add(side[1]);
			sa.add(side[2]);
			o.add("top", ta);
			o.add("side", sa);
			o.addProperty("alpha", Math.round(Math.max(top[3], side[3]) / 255.0 * 100) / 100.0);
			blocks.add(key.toString(), o);
			ok++;
		}
		JsonObject root = new JsonObject();
		root.addProperty("note", "Ortalama doku renkleri; oyunun yuklu kaynaklarindan calisma aninda cikarildi (dokular dagitilmaz).");
		root.add("blocks", blocks);
		ByteArrayOutputStream bos = new ByteArrayOutputStream();
		try (GZIPOutputStream gz = new GZIPOutputStream(bos)) {
			gz.write(root.toString().getBytes(StandardCharsets.UTF_8));
		}
		Files.createDirectories(out.getParent());
		Files.write(out, bos.toByteArray());
		JsonObject res = new JsonObject();
		res.addProperty("ok", true);
		res.addProperty("path", out.toAbsolutePath().toString());
		res.addProperty("blocks", ok);
		res.addProperty("missing", miss);
		res.addProperty("ms", System.currentTimeMillis() - t0);
		return res;
	}
}
