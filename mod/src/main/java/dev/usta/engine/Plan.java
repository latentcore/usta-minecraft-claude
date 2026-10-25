package dev.usta.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.GZIPInputStream;

/**
 * USTAPLN1 plani (Python tarafindaki usta/plan.py ile ayni bicim).
 * hucre indeksi = (y*sz + z)*sx + x ; palet[0]="keep", palet[1]="minecraft:air"; "!" oneki = tam (settle yok).
 */
public final class Plan {
	public static final byte[] MAGIC = "USTAPLN1".getBytes(StandardCharsets.US_ASCII);

	public int ox, oy, oz;
	public int sx, sy, sz;
	public String[] palette;
	public int[] cells;
	public final List<BlockEntitySpec> blockEntities = new ArrayList<>();
	public final List<EntitySpec> entities = new ArrayList<>();
	public JsonObject meta = new JsonObject();

	public record BlockEntitySpec(int x, int y, int z, String snbt) {}

	public record EntitySpec(String type, double x, double y, double z, float yaw, float pitch, String snbt) {}

	public int index(int x, int y, int z) {
		return (y * sz + z) * sx + x;
	}

	public int volume() {
		return sx * sy * sz;
	}

	public static Plan read(byte[] gz, long maxCells) throws IOException {
		try (InputStream in = new GZIPInputStream(new ByteArrayInputStream(gz), 1 << 16);
			 DataInputStream din = new DataInputStream(in)) {
			byte[] magic = din.readNBytes(8);
			if (magic.length != 8 || !java.util.Arrays.equals(magic, MAGIC)) throw new IOException("USTAPLN1 degil");
			byte[] lenb = din.readNBytes(4);
			int hl = ByteBuffer.wrap(lenb).order(ByteOrder.LITTLE_ENDIAN).getInt();
			if (hl <= 0 || hl > 256 * 1024 * 1024) throw new IOException("baslik boyutu gecersiz");
			byte[] hb = din.readNBytes(hl);
			JsonObject h = JsonParser.parseString(new String(hb, StandardCharsets.UTF_8)).getAsJsonObject();
			Plan p = new Plan();
			JsonArray o = h.getAsJsonArray("origin");
			p.ox = o.get(0).getAsInt();
			p.oy = o.get(1).getAsInt();
			p.oz = o.get(2).getAsInt();
			JsonArray s = h.getAsJsonArray("size");
			p.sx = s.get(0).getAsInt();
			p.sy = s.get(1).getAsInt();
			p.sz = s.get(2).getAsInt();
			if (p.sx <= 0 || p.sy <= 0 || p.sz <= 0) throw new IOException("boyut gecersiz");
			long vol = (long) p.sx * p.sy * p.sz;
			if (vol > maxCells) throw new IOException("plan cok buyuk: " + vol + " hucre (sinir " + maxCells + ")");
			JsonArray pal = h.getAsJsonArray("palette");
			p.palette = new String[pal.size()];
			for (int i = 0; i < pal.size(); i++) p.palette[i] = pal.get(i).getAsString();
			if (p.palette.length < 2 || !"keep".equals(p.palette[0]) || !"minecraft:air".equals(p.palette[1])) {
				throw new IOException("palet[0]=keep, palet[1]=minecraft:air olmali");
			}
			int width = h.has("index_width") ? h.get("index_width").getAsInt() : 2;
			int n = (int) vol;
			byte[] body = din.readNBytes(n * width);
			if (body.length != n * width) throw new IOException("hucre verisi eksik");
			ByteBuffer bb = ByteBuffer.wrap(body).order(ByteOrder.LITTLE_ENDIAN);
			p.cells = new int[n];
			for (int i = 0; i < n; i++) {
				int v = width == 2 ? (bb.getShort() & 0xFFFF) : bb.getInt();
				if (v < 0 || v >= p.palette.length) throw new IOException("palet disi indeks: " + v);
				p.cells[i] = v;
			}
			if (h.has("block_entities")) {
				for (JsonElement e : h.getAsJsonArray("block_entities")) {
					JsonObject be = e.getAsJsonObject();
					JsonArray pos = be.getAsJsonArray("pos");
					p.blockEntities.add(new BlockEntitySpec(pos.get(0).getAsInt(), pos.get(1).getAsInt(), pos.get(2).getAsInt(),
						be.has("snbt") ? be.get("snbt").getAsString() : "{}"));
				}
			}
			if (h.has("entities")) {
				for (JsonElement e : h.getAsJsonArray("entities")) {
					JsonObject en = e.getAsJsonObject();
					JsonArray pos = en.getAsJsonArray("pos");
					p.entities.add(new EntitySpec(en.get("type").getAsString(),
						pos.get(0).getAsDouble(), pos.get(1).getAsDouble(), pos.get(2).getAsDouble(),
						en.has("yaw") ? en.get("yaw").getAsFloat() : 0f,
						en.has("pitch") ? en.get("pitch").getAsFloat() : 0f,
						en.has("snbt") ? en.get("snbt").getAsString() : "{}"));
				}
			}
			if (h.has("meta") && h.get("meta").isJsonObject()) p.meta = h.getAsJsonObject("meta");
			return p;
		}
	}
}
