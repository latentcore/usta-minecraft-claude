package dev.usta.core;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** Kullanici ayarlari (usta/ayarlar.json). Panelden ve komutla degisir. */
public final class Settings {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	/** instant | watch | cinematic */
	public String defaultMode = "watch";
	/** izlenebilir kipte varsayilan hedef sure (sn); 0 = boyuta gore otomatik */
	public double defaultSeconds = 0;
	public boolean effects = true;
	public boolean celebration = true;
	/** auto | opus | sonnet */
	public String model = "auto";
	/** anlik kipte tick basina sure butcesi (ms) */
	public int instantBudgetMs = 30;
	/** izlenebilir kipte tick basina sure tavani (ms) */
	public int watchBudgetMs = 25;
	/** onay gerektiren buyuk silme esikleri */
	public int confirmRemoveNatural = 30000;
	public int confirmRemoveArtificial = 300;
	/** plan hucre siniri (bellek) */
	public long maxPlanCells = 16_000_000L;
	/** geri alma gecmisi disk siniri (MB) */
	public int historyDiskLimitMb = 4096;
	/** buyuk TNT kumeleri tek seferde, kasmadan patlar (MassExplosion); false = vanilla */
	public boolean massExplosion = true;
	/** bu kadar ve daha fazla birbirine bagli TNT toplu patlar */
	public int massExplosionThreshold = 256;

	public static Path file() {
		return Paths.root().resolve("ayarlar.json");
	}

	public static Settings load() {
		try {
			Path f = file();
			if (Files.exists(f)) {
				Settings s = GSON.fromJson(Files.readString(f, StandardCharsets.UTF_8), Settings.class);
				if (s != null) return s;
			}
		} catch (Exception ignored) {
		}
		Settings s = new Settings();
		s.save();
		return s;
	}

	public synchronized void save() {
		try {
			Paths.writeAtomic(file(), GSON.toJson(this));
		} catch (Exception ignored) {
		}
	}

	public String toJson() {
		return GSON.toJson(this);
	}
}
