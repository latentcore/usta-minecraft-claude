package dev.usta.engine;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.reflect.TypeToken;
import dev.usta.core.Paths;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Dunya basina geri alinabilir islerin dizini (history.json). */
public final class History {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	public static final class Entry {
		public String id;
		public String kind;      // BUILD | ACTION
		public String label;
		public String state;     // DONE | CANCELLED
		public boolean undone;
		public long created;
		public long finished;
		public String dim;
		public int[] box;        // ox,oy,oz,sx,sy,sz
		public int changed;
		public String source;
		public String request;
		public String action;    // ACTION icin: time | weather | teleport
		public String actionData; // ACTION icin geri alma verisi (JSON)
	}

	private final Path file;
	private final List<Entry> entries = new ArrayList<>();

	public History(Path worldDir) {
		this.file = worldDir.resolve("history.json");
		try {
			if (Files.exists(file)) {
				List<Entry> l = GSON.fromJson(Files.readString(file, StandardCharsets.UTF_8), new TypeToken<List<Entry>>() {}.getType());
				if (l != null) entries.addAll(l);
			}
		} catch (Exception ignored) {
		}
	}

	public synchronized List<Entry> all() {
		return new ArrayList<>(entries);
	}

	public synchronized Entry get(String id) {
		for (Entry e : entries) if (e.id.equals(id)) return e;
		return null;
	}

	public synchronized void put(Entry e) {
		entries.removeIf(x -> x.id.equals(e.id));
		entries.add(e);
		save();
	}

	public synchronized void save() {
		try {
			Paths.writeAtomic(file, GSON.toJson(entries));
		} catch (Exception ignored) {
		}
	}

	/** En son geri alinmamis is. */
	public synchronized Entry lastUndoable() {
		for (int i = entries.size() - 1; i >= 0; i--) {
			Entry e = entries.get(i);
			if (!e.undone) return e;
		}
		return null;
	}

	/** En son geri alinmis is (yinele icin). */
	public synchronized Entry lastUndone() {
		Entry best = null;
		for (Entry e : entries) {
			if (e.undone && (best == null || e.finished >= best.finished)) best = e;
		}
		return best;
	}

	/** e'den sonra yapilmis ve e ile kesisen, geri alinmamis isler. */
	public synchronized List<Entry> laterOverlapping(Entry e) {
		List<Entry> out = new ArrayList<>();
		boolean after = false;
		for (Entry x : entries) {
			if (x.id.equals(e.id)) {
				after = true;
				continue;
			}
			if (after && !x.undone && x.box != null && e.box != null && overlaps(x.box, e.box) && x.dim != null && x.dim.equals(e.dim)) out.add(x);
		}
		return out;
	}

	static boolean overlaps(int[] a, int[] b) {
		return a[0] < b[0] + b[3] && b[0] < a[0] + a[3]
			&& a[1] < b[1] + b[4] && b[1] < a[1] + a[4]
			&& a[2] < b[2] + b[5] && b[2] < a[2] + a[5];
	}
}
