package dev.usta.core;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.usta.UstaMod;
import dev.usta.agent.AgentManager;
import dev.usta.api.ApiServer;
import dev.usta.data.BlockDb;
import dev.usta.engine.History;
import dev.usta.engine.Job;
import dev.usta.engine.JobManager;
import dev.usta.engine.MassExplosion;
import dev.usta.game.Chat;
import dev.usta.world.Classify;
import dev.usta.world.Protection;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.storage.LevelResource;

/** Bir dunya acikken modun calisma zamani durumu (tek ornek). */
public final class Usta {
	private static volatile Usta INSTANCE;

	public final MinecraftServer server;
	public final String worldKey;
	public final Path worldDir;
	public final Settings settings;
	public final Events events = new Events();
	public final History history;
	public final Protection protection;
	public final JobManager jobs;
	public final AgentManager agent;
	public ApiServer api;
	public volatile boolean aiEnabled = true;
	public volatile String disabledReason;
	private final AtomicBoolean backupRunning = new AtomicBoolean();
	private int tickCount;

	private Usta(MinecraftServer server) {
		this.server = server;
		Path worldRoot = server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
		String folder = worldRoot.getFileName() == null ? "world" : worldRoot.getFileName().toString();
		if (folder.equals(".")) folder = worldRoot.getParent().getFileName().toString();
		long seed = server.overworld().getSeed();
		this.worldKey = Paths.worldKey(folder, seed);
		this.worldDir = Paths.ensure(Paths.world(worldKey));
		Paths.ensure(Paths.runtime());
		Paths.ensure(Paths.cache());
		Paths.ensure(Paths.logs());
		this.settings = Settings.load();
		this.history = new History(worldDir);
		this.protection = new Protection(worldDir);
		this.jobs = new JobManager(this);
		this.agent = new AgentManager(this);
		try {
			JsonObject info = new JsonObject();
			info.addProperty("folder", folder);
			info.addProperty("level_name", server.getWorldData().getLevelName());
			info.addProperty("updated", System.currentTimeMillis());
			Paths.writeAtomic(worldDir.resolve("dunya.json"), info.toString());
		} catch (IOException ignored) {
		}
	}

	public static Usta get() {
		return INSTANCE;
	}

	public static boolean testHarness() {
		return Boolean.getBoolean("usta.testHarness");
	}

	/** Yalniz tek oyunculu (LAN'a acilmamis) dunyalarda; test duzeninde ozel izinle (S4, M3). */
	public static boolean allowedServer(MinecraftServer s) {
		if (testHarness()) return true;
		return s.isSingleplayer() && !s.isPublished() && !s.isDedicatedServer();
	}

	public static void start(MinecraftServer server) {
		if (!server.isSingleplayer() && !testHarness()) {
			UstaMod.LOG.info("Usta: tek oyunculu olmayan sunucu; yapay zeka ozellikleri kapali.");
			return;
		}
		try {
			Classify.init();
			Usta u = new Usta(server);
			INSTANCE = u;
			try {
				BlockDb.ensure();
			} catch (Exception e) {
				UstaMod.LOG.warn("Blok veritabani yazilamadi", e);
			}
			u.api = new ApiServer(u);
			u.api.start();
			int resumed = u.jobs.resumeUnfinished();
			if (resumed > 0) u.pendingNotice = "Yarım kalan " + resumed + " inşa işi sürüyor.";
			UstaMod.LOG.info("Usta hazir: dunya={}, api=127.0.0.1:{}", u.worldKey, u.api.port());
		} catch (Exception e) {
			UstaMod.LOG.error("Usta baslatilamadi", e);
		}
	}

	public String pendingNotice;

	public static void stop() {
		Usta u = INSTANCE;
		if (u == null) return;
		INSTANCE = null;
		MassExplosion.reset();
		try {
			u.jobs.onServerStopping();
		} catch (Exception e) {
			UstaMod.LOG.warn("Is durdurma hatasi", e);
		}
		try {
			u.agent.shutdown();
		} catch (Exception ignored) {
		}
		if (u.api != null) u.api.stop();
	}

	public void tick() {
		tickCount++;
		if (tickCount % 20 == 0) {
			boolean ok = allowedServer(server);
			if (!ok && aiEnabled) {
				aiEnabled = false;
				disabledReason = "Dünya LAN'a açıldı; Usta yalnız tek oyunculu dünyalarda çalışır, yapay zekâ özellikleri kapatıldı.";
				Job a = jobs.active();
				if (a != null) jobs.pause(a.id, true);
				agent.cancelAll("LAN");
				Chat.toAll(server, Chat.warn(disabledReason));
			} else if (ok && !aiEnabled) {
				aiEnabled = true;
				disabledReason = null;
				Chat.toAll(server, Chat.soft("Dünya yeniden tek oyunculu; Usta tekrar açık."));
			}
			if (pendingNotice != null && !server.getPlayerList().getPlayers().isEmpty()) {
				Chat.toAll(server, Chat.soft(pendingNotice));
				pendingNotice = null;
			}
		}
		if (!aiEnabled) return;
		MassExplosion.tick(this);
		jobs.tick();
		agent.tick();
	}

	public ServerPlayer player() {
		List<ServerPlayer> ps = server.getPlayerList().getPlayers();
		return ps.isEmpty() ? null : ps.get(0);
	}

	/** Bu boyuttaki geri alinmamis Usta islerinin kutulari (kendi yapilarini duzenlemek serbest). */
	public List<int[]> ownBoxes(ServerLevel level) {
		String dim = level.dimension().identifier().toString();
		List<int[]> out = new ArrayList<>();
		for (History.Entry e : history.all()) {
			// patlama kraterinin kutusu "Usta yapisi" degildir (icindeki baska yapilar korunmaya devam eder)
			if (!e.undone && e.box != null && dim.equals(e.dim) && !"patlama".equals(e.source)) out.add(e.box);
		}
		return out;
	}

	public void onJobFinished(Job j) {
		agent.onJobFinished(j);
		if (j.requestId != null) return; // ajan kendi bitis mesajini yazar
		if (j.explosion) {
			List<Chat.Button> undo = List.of(Chat.Button.run("Geri al", "/usta geri " + j.id, "Patlamadan önceki hâline döndür"));
			switch (j.state) {
				case DONE -> Chat.toAll(server, Chat.withButtons(Chat.line("Patlama bitti: " + j.label.replace("Toplu patlama: ", "")
					+ " · " + j.cursor + " blok yok oldu."), undo));
				case CANCELLED -> Chat.toAll(server, Chat.withButtons(Chat.soft("Patlama durduruldu (" + j.cursor + " blok yok oldu)."), undo));
				case FAILED -> Chat.toAll(server, Chat.error("Patlama yapılamadı: " + (j.message == null ? "bilinmeyen hata" : j.message)));
				default -> {
				}
			}
			return;
		}
		switch (j.state) {
			case DONE -> {
				if (j.kind == Job.Kind.UNDO) {
					Chat.toAll(server, Chat.soft("Geri alındı: " + j.label.replace("Geri al: ", "") + "."));
				} else if (j.kind == Job.Kind.REDO) {
					Chat.toAll(server, Chat.soft("Yinelendi: " + j.label + "."));
				} else {
					String extra = j.unsupported > 0 ? " (uyarı: " + j.unsupported + " blok desteksiz)" : "";
					Chat.toAll(server, Chat.withButtons(Chat.line("Bitti: " + j.label + " · " + j.cursor + " blok" + extra + "."), Chat.doneButtons(j.id)));
				}
			}
			case CANCELLED -> Chat.toAll(server, Chat.withButtons(Chat.soft("İptal edildi: " + j.label + " (" + j.cursor + " blok kondu)."),
				List.of(Chat.Button.run("Geri al", "/usta geri " + j.id, "Konan kısmı geri al"))));
			case FAILED -> Chat.toAll(server, Chat.error("Yapılamadı: " + j.label + " — " + (j.message == null ? "bilinmeyen hata" : j.message)));
			default -> {
			}
		}
	}

	// ------------------------------------------------------------------ ilk kullanim onayi + yedek (M2)
	public Path activationFile() {
		return worldDir.resolve("etkinlestirme.json");
	}

	public boolean activated() {
		if (testHarness() || Boolean.getBoolean("usta.autoActivate")) return true;
		try {
			Path f = activationFile();
			if (!Files.exists(f)) return false;
			return JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject().get("activated").getAsBoolean();
		} catch (Exception e) {
			return false;
		}
	}

	public boolean backupRunning() {
		return backupRunning.get();
	}

	public void promptActivation() {
		Chat.toAll(server, Chat.withButtons(
			Chat.line("Bu dünyada Usta'yı ilk kez kullanıyorsun. Başlamadan önce dünyanın sıkıştırılmış bir yedeğini (dünya klasörünün dışına) alacağım."),
			List.of(Chat.Button.run("Onayla ve yedekle", "/usta etkinlestir", "Yedeği al ve Usta'yı bu dünyada aç"),
				Chat.Button.run("Vazgeç", "/usta vazgec", "Bu dünyada Usta kullanılmasın"))));
	}

	/** Sunucu is parcaciginda cagrilir: kaydet, kaydi durdur, yedegi arka planda al. */
	public void activate(Runnable after) {
		if (activated()) {
			if (after != null) after.run();
			return;
		}
		if (!backupRunning.compareAndSet(false, true)) return;
		Chat.toAll(server, Chat.soft("Dünya kaydediliyor ve yedekleniyor…"));
		server.saveEverything(true, true, true);
		List<ServerLevel> levels = new ArrayList<>();
		for (ServerLevel l : server.getAllLevels()) {
			if (!l.noSave) {
				l.noSave = true;
				levels.add(l);
			}
		}
		Path worldRoot = server.getWorldPath(LevelResource.ROOT).toAbsolutePath().normalize();
		String stamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
		Path zip = Paths.ensure(Paths.backups()).resolve(worldKey + "-" + stamp + ".zip");
		Thread t = new Thread(() -> {
			String err = null;
			long size = 0;
			try {
				zipDir(worldRoot, zip);
				size = Files.size(zip);
			} catch (Exception e) {
				err = e.toString();
			}
			final String ferr = err;
			final long fsize = size;
			server.execute(() -> {
				for (ServerLevel l : levels) l.noSave = false;
				backupRunning.set(false);
				if (ferr != null) {
					Chat.toAll(server, Chat.error("Yedek alınamadı (" + ferr + "); güvenlik için Usta bu dünyada açılmadı."));
					return;
				}
				JsonObject o = new JsonObject();
				o.addProperty("activated", true);
				o.addProperty("backup", zip.toString());
				o.addProperty("size", fsize);
				o.addProperty("at", System.currentTimeMillis());
				try {
					Paths.writeAtomic(activationFile(), o.toString());
				} catch (IOException e) {
					Chat.toAll(server, Chat.error("Etkinleştirme kaydı yazılamadı: " + e.getMessage()));
					return;
				}
				Chat.toAll(server, Chat.soft("Yedek hazır (" + (fsize / (1024 * 1024)) + " MB): " + zip.getFileName() + ". Usta bu dünyada açık."));
				if (after != null) after.run();
			});
		}, "usta-yedek");
		t.setDaemon(true);
		t.start();
	}

	private static void zipDir(Path root, Path zip) throws IOException {
		Path tmp = zip.resolveSibling(zip.getFileName() + ".part");
		try (OutputStream os = Files.newOutputStream(tmp); ZipOutputStream zos = new ZipOutputStream(os)) {
			zos.setLevel(6);
			try (var walk = Files.walk(root)) {
				for (Path p : walk.toList()) {
					if (Files.isDirectory(p)) continue;
					String name = root.relativize(p).toString().replace('\\', '/');
					if (name.equals("session.lock")) continue;
					zos.putNextEntry(new ZipEntry(root.getFileName() + "/" + name));
					try {
						Files.copy(p, zos);
					} catch (IOException e) {
						// kilitli dosya: atla ama zip'i bozma
					}
					zos.closeEntry();
				}
			}
		}
		Files.move(tmp, zip, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
	}
}
