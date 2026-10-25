package dev.usta.world;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import dev.usta.core.Paths;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Korunan bolgeler (dunya basina): buralara hicbir is yazamaz (C10). */
public final class Protection {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	public static final class Region {
		public String name;
		public String dim;
		public int x0, y0, z0, x1, y1, z1;
		public long created;

		public boolean contains(String d, int x, int y, int z) {
			return dim.equals(d) && x >= x0 && x <= x1 && y >= y0 && y <= y1 && z >= z0 && z <= z1;
		}
	}

	private final Path file;
	private final List<Region> regions = new ArrayList<>();

	public Protection(Path worldDir) {
		this.file = worldDir.resolve("korunan.json");
		try {
			if (Files.exists(file)) {
				List<Region> l = GSON.fromJson(Files.readString(file, StandardCharsets.UTF_8), new TypeToken<List<Region>>() {}.getType());
				if (l != null) regions.addAll(l);
			}
		} catch (Exception ignored) {
		}
	}

	public synchronized boolean isProtected(String dim, int x, int y, int z) {
		for (Region r : regions) if (r.contains(dim, x, y, z)) return true;
		return false;
	}

	public synchronized List<Region> all() {
		return new ArrayList<>(regions);
	}

	public synchronized void add(Region r) {
		regions.removeIf(x -> x.name.equals(r.name));
		r.created = System.currentTimeMillis();
		regions.add(r);
		save();
	}

	public synchronized boolean remove(String name) {
		boolean ok = regions.removeIf(x -> x.name.equals(name));
		if (ok) save();
		return ok;
	}

	private void save() {
		try {
			Paths.writeAtomic(file, GSON.toJson(regions));
		} catch (Exception ignored) {
		}
	}
}
