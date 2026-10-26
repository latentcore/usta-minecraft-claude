package dev.usta.api;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import dev.usta.UstaMod;
import dev.usta.compat.V;
import dev.usta.core.ClientHook;
import dev.usta.core.Paths;
import dev.usta.core.Settings;
import dev.usta.core.Usta;
import dev.usta.data.BlockDb;
import dev.usta.engine.History;
import dev.usta.engine.Job;
import dev.usta.engine.JobManager;
import dev.usta.engine.Plan;
import dev.usta.game.Chat;
import dev.usta.world.Protection;
import dev.usta.world.WorldIO;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.ChunkPos;

/**
 * Oyun API'si: yalniz 127.0.0.1, rastgele port, Bearer anahtar, Host denetimi (DNS rebinding),
 * Origin tasiyan istekleri reddeder (tarayicidan dogrudan erisim yok). Anahtar hicbir gunluge yazilmaz (M4, M5).
 */
public final class ApiServer {
	private static final Gson GSON = new Gson();
	private final Usta u;
	private HttpServer http;
	private ExecutorService pool;
	private String token;
	private int port;

	public ApiServer(Usta u) {
		this.u = u;
	}

	public int port() {
		return port;
	}

	public static Path discoveryFile() {
		return Paths.runtime().resolve("api.json");
	}

	public void start() throws IOException {
		byte[] rnd = new byte[32];
		new SecureRandom().nextBytes(rnd);
		token = HexFormat.of().formatHex(rnd);
		http = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 64);
		pool = Executors.newFixedThreadPool(8, r -> {
			Thread t = new Thread(r, "usta-api");
			t.setDaemon(true);
			return t;
		});
		http.setExecutor(pool);
		http.createContext("/", this::handle);
		http.start();
		port = http.getAddress().getPort();
		JsonObject d = new JsonObject();
		d.addProperty("port", port);
		d.addProperty("token", token);
		d.addProperty("pid", ProcessHandle.current().pid());
		d.addProperty("world", u.worldKey);
		d.addProperty("mc", V.MC);
		d.addProperty("mod", UstaMod.version());
		d.addProperty("game_dir", Paths.gameDir().toAbsolutePath().toString());
		d.addProperty("started", System.currentTimeMillis());
		Path f = discoveryFile();
		Files.createDirectories(f.getParent());
		Files.deleteIfExists(f);
		Files.createFile(f);
		Paths.restrictToOwner(f);
		Files.writeString(f, d.toString(), StandardCharsets.UTF_8);
	}

	public void stop() {
		try {
			if (http != null) http.stop(0);
		} catch (Exception ignored) {
		}
		if (pool != null) pool.shutdownNow();
		try {
			Files.deleteIfExists(discoveryFile());
		} catch (IOException ignored) {
		}
	}

	// ------------------------------------------------------------------ cekirdek
	private static final class HttpError extends RuntimeException {
		final int code;
		final String reason;

		HttpError(int code, String reason, String msg) {
			super(msg);
			this.code = code;
			this.reason = reason;
		}
	}

	private boolean authorized(HttpExchange ex) {
		String a = ex.getRequestHeaders().getFirst("Authorization");
		if (a == null || !a.startsWith("Bearer ")) return false;
		byte[] got = a.substring(7).trim().getBytes(StandardCharsets.UTF_8);
		return MessageDigest.isEqual(got, token.getBytes(StandardCharsets.UTF_8));
	}

	private boolean hostOk(HttpExchange ex) {
		String h = ex.getRequestHeaders().getFirst("Host");
		if (h == null) return false;
		return h.equals("127.0.0.1:" + port) || h.equals("localhost:" + port);
	}

	private void handle(HttpExchange ex) {
		// try-with-resources kullanma: kaynak catch'ten ONCE kapanir ve hata yaniti hic gonderilemez
		// (istemci "yanitsiz kapandi" gorur; her 4xx "oyun kapali" sanilirdi)
		try {
			if (!hostOk(ex)) {
				send(ex, 403, err("host", "Host başlığı kabul edilmedi"));
				return;
			}
			if (ex.getRequestHeaders().containsKey("Origin")) {
				send(ex, 403, err("origin", "Tarayıcıdan doğrudan erişim kapalı"));
				return;
			}
			if (!authorized(ex)) {
				send(ex, 401, err("auth", "Anahtar yok ya da yanlış"));
				return;
			}
			if (Usta.get() != u) {
				send(ex, 503, err("stopped", "Dünya kapanıyor"));
				return;
			}
			route(ex);
		} catch (HttpError e) {
			try {
				send(ex, e.code, err(e.reason, e.getMessage()));
			} catch (Exception ignored) {
			}
		} catch (Throwable t) {
			UstaMod.LOG.warn("API hatasi: {} {}", ex.getRequestMethod(), ex.getRequestURI().getPath(), t);
			try {
				send(ex, 500, err("internal", t.toString()));
			} catch (Exception ignored) {
			}
		} finally {
			ex.close();
		}
	}

	private static JsonObject err(String reason, String msg) {
		JsonObject o = new JsonObject();
		o.addProperty("ok", false);
		o.addProperty("error", reason);
		o.addProperty("message", msg);
		return o;
	}

	private static void send(HttpExchange ex, int code, JsonElement body) throws IOException {
		byte[] b = body.toString().getBytes(StandardCharsets.UTF_8);
		ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
		ex.getResponseHeaders().set("Cache-Control", "no-store");
		ex.sendResponseHeaders(code, b.length);
		try (OutputStream os = ex.getResponseBody()) {
			os.write(b);
		}
	}

	private static void sendBytes(HttpExchange ex, byte[] b, String type) throws IOException {
		ex.getResponseHeaders().set("Content-Type", type);
		ex.getResponseHeaders().set("Cache-Control", "no-store");
		ex.sendResponseHeaders(200, b.length);
		try (OutputStream os = ex.getResponseBody()) {
			os.write(b);
		}
	}

	private static byte[] body(HttpExchange ex, int max) throws IOException {
		try (InputStream in = ex.getRequestBody()) {
			byte[] b = in.readNBytes(max + 1);
			if (b.length > max) throw new HttpError(413, "too_large", "İstek gövdesi çok büyük");
			return b;
		}
	}

	private static JsonObject jsonBody(HttpExchange ex) throws IOException {
		byte[] b = body(ex, 8 * 1024 * 1024);
		if (b.length == 0) return new JsonObject();
		JsonElement e = JsonParser.parseString(new String(b, StandardCharsets.UTF_8));
		if (!e.isJsonObject()) throw new HttpError(400, "bad_json", "JSON nesnesi bekleniyordu");
		return e.getAsJsonObject();
	}

	private static Map<String, String> query(HttpExchange ex) {
		Map<String, String> m = new HashMap<>();
		String q = ex.getRequestURI().getRawQuery();
		if (q == null) return m;
		for (String part : q.split("&")) {
			int i = part.indexOf('=');
			String k = i < 0 ? part : part.substring(0, i);
			String v = i < 0 ? "" : part.substring(i + 1);
			m.put(URLDecoder.decode(k, StandardCharsets.UTF_8), URLDecoder.decode(v, StandardCharsets.UTF_8));
		}
		return m;
	}

	private <T> T onServer(java.util.concurrent.Callable<T> c, long timeoutMs) {
		try {
			return u.server.submit(() -> {
				try {
					return c.call();
				} catch (RuntimeException e) {
					throw e;
				} catch (Exception e) {
					throw new RuntimeException(e);
				}
			}).get(timeoutMs, TimeUnit.MILLISECONDS);
		} catch (java.util.concurrent.TimeoutException e) {
			throw new HttpError(504, "timeout", "Oyun sunucusu yanıt vermedi (duraklatılmış ya da meşgul olabilir)");
		} catch (java.util.concurrent.ExecutionException e) {
			Throwable c2 = e.getCause() != null ? e.getCause() : e;
			if (c2 instanceof HttpError he) throw he;
			if (c2.getCause() instanceof HttpError he2) throw he2;
			throw new RuntimeException(c2);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new RuntimeException(e);
		}
	}

	private void requireWrite() {
		if (!u.aiEnabled) throw new HttpError(409, "disabled", u.disabledReason == null ? "Usta kapalı" : u.disabledReason);
		if (!u.activated()) {
			u.server.execute(u::promptActivation);
			throw new HttpError(409, "activation_required", "Bu dünyada ilk kullanım onayı bekleniyor: oyunda sohbetteki [Onayla ve yedekle] düğmesine tıklanmalı.");
		}
	}

	private ServerPlayer playerOrThrow() {
		ServerPlayer p = u.player();
		if (p == null) throw new HttpError(409, "no_player", "Dünyada oyuncu yok");
		return p;
	}

	// ------------------------------------------------------------------ yonlendirme
	private void route(HttpExchange ex) throws Exception {
		String m = ex.getRequestMethod();
		String path = ex.getRequestURI().getPath();
		Map<String, String> q = query(ex);
		if (path.equals("/v1/ping")) {
			JsonObject o = new JsonObject();
			o.addProperty("ok", true);
			o.addProperty("mod", UstaMod.version());
			o.addProperty("mc", V.MC);
			o.addProperty("world", u.worldKey);
			o.addProperty("paused", u.server.isPaused());
			o.addProperty("ai_enabled", u.aiEnabled);
			send(ex, 200, o);
			return;
		}
		if (path.equals("/v1/status") && m.equals("GET")) {
			send(ex, 200, status());
			return;
		}
		if (path.equals("/v1/context") && m.equals("GET")) {
			int radius = Math.max(4, Math.min(256, Integer.parseInt(q.getOrDefault("radius", "48"))));
			JsonObject ctx = onServer(() -> {
				ServerPlayer p = playerOrThrow();
				JsonObject c = WorldIO.playerContext(u.server, p, radius);
				c.addProperty("paused", u.server.isPaused());
				c.addProperty("singleplayer", Usta.allowedServer(u.server));
				c.add("protected_regions", protectedJson());
				return c;
			}, 5000);
			ClientHook.Bridge b = ClientHook.bridge;
			if (b != null) ctx.add("client", b.state());
			Job a = u.jobs.active();
			if (a != null) ctx.add("active_job", u.jobs.summary(a));
			send(ex, 200, ctx);
			return;
		}
		if (path.equals("/v1/region/columns") && m.equals("POST")) {
			JsonObject b = jsonBody(ex);
			int x0 = b.get("x0").getAsInt(), z0 = b.get("z0").getAsInt(), x1 = b.get("x1").getAsInt(), z1 = b.get("z1").getAsInt();
			if (x1 < x0 || z1 < z0 || (long) (x1 - x0 + 1) * (z1 - z0 + 1) > 1024L * 1024L) throw new HttpError(400, "bad_area", "Alan geçersiz ya da çok büyük (en çok 1024x1024)");
			ServerLevel level = u.jobs.levelOf(b.has("dim") ? b.get("dim").getAsString() : currentDim());
			long timeout = b.has("timeout_ms") ? b.get("timeout_ms").getAsLong() : 4000;
			List<ChunkPos> held = WorldIO.ensureLoaded(u.server, level, WorldIO.chunksOf(x0, z0, x1, z1), timeout, false);
			try {
				byte[] data = onServer(() -> WorldIO.columns(level, x0, z0, x1, z1), 10000);
				sendBytes(ex, data, "application/octet-stream");
			} finally {
				WorldIO.release(u.server, level, held);
			}
			return;
		}
		if (path.equals("/v1/region/blocks") && m.equals("POST")) {
			JsonObject b = jsonBody(ex);
			int x0 = b.get("x0").getAsInt(), y0 = b.get("y0").getAsInt(), z0 = b.get("z0").getAsInt();
			int sx = b.get("sx").getAsInt(), sy = b.get("sy").getAsInt(), sz = b.get("sz").getAsInt();
			if (sx <= 0 || sy <= 0 || sz <= 0 || (long) sx * sy * sz > 16_000_000L) throw new HttpError(400, "bad_box", "Hacim geçersiz ya da çok büyük (en çok 16M hücre)");
			ServerLevel level = u.jobs.levelOf(b.has("dim") ? b.get("dim").getAsString() : currentDim());
			long timeout = b.has("timeout_ms") ? b.get("timeout_ms").getAsLong() : 4000;
			boolean gen = b.has("generate") && b.get("generate").getAsBoolean();
			List<ChunkPos> held = WorldIO.ensureLoaded(u.server, level, WorldIO.chunksOf(x0, z0, x0 + sx - 1, z0 + sz - 1), timeout, gen);
			try {
				byte[] data = onServer(() -> WorldIO.blocks(level, x0, y0, z0, sx, sy, sz), 20000);
				sendBytes(ex, data, "application/octet-stream");
			} finally {
				WorldIO.release(u.server, level, held);
			}
			return;
		}
		if (path.equals("/v1/region/entities") && m.equals("POST")) {
			JsonObject b = jsonBody(ex);
			ServerLevel level = u.jobs.levelOf(b.has("dim") ? b.get("dim").getAsString() : currentDim());
			net.minecraft.world.phys.AABB box = new net.minecraft.world.phys.AABB(b.get("x0").getAsDouble(), b.get("y0").getAsDouble(), b.get("z0").getAsDouble(),
				b.get("x1").getAsDouble() + 1, b.get("y1").getAsDouble() + 1, b.get("z1").getAsDouble() + 1);
			boolean nbt = b.has("nbt") && b.get("nbt").getAsBoolean();
			int ex0 = (int) Math.floor(box.minX), ez0 = (int) Math.floor(box.minZ), ex1 = (int) Math.floor(box.maxX), ez1 = (int) Math.floor(box.maxZ);
			List<ChunkPos> need = WorldIO.chunksOf(ex0, ez0, ex1, ez1);
			List<ChunkPos> held = WorldIO.ensureLoaded(u.server, level, need, 6000, false);
			JsonArray arr;
			try {
				long until = System.currentTimeMillis() + 6000;
				while (System.currentTimeMillis() < until) {
					boolean all = onServer(() -> {
						for (ChunkPos cp : need) {
							if (level.getChunkSource().getChunkNow(cp.x(), cp.z()) != null && !level.areEntitiesLoaded(cp.pack())) return false;
						}
						return true;
					}, 5000);
					if (all) break;
					Thread.sleep(100);
				}
				arr = onServer(() -> WorldIO.entities(level, box, nbt), 10000);
			} finally {
				WorldIO.release(u.server, level, held);
			}
			JsonObject o = new JsonObject();
			o.add("entities", arr);
			send(ex, 200, o);
			return;
		}
		if (path.equals("/v1/blockdb") && m.equals("GET")) {
			Path f = BlockDb.ensure();
			if (q.containsKey("path")) {
				JsonObject o = new JsonObject();
				o.addProperty("path", f.toAbsolutePath().toString());
				send(ex, 200, o);
			} else {
				sendBytes(ex, Files.readAllBytes(f), "application/gzip");
			}
			return;
		}
		if (path.equals("/v1/plan/validate") && m.equals("POST")) {
			byte[] data = body(ex, 512 * 1024 * 1024);
			Plan plan = Plan.read(data, u.settings.maxPlanCells);
			ServerLevel level = u.jobs.levelOf(q.getOrDefault("dim", currentDim()));
			JsonObject o = new JsonObject();
			try {
				Job j = u.jobs.fromPlan(plan, level, Job.Mode.INSTANT, 0, q.get("label"), "validate", true, true);
				o.addProperty("ok", true);
				o.addProperty("changes", j.n);
			} catch (JobManager.PlanException pe) {
				o.addProperty("ok", false);
				o.addProperty("message", pe.getMessage());
				JsonArray arr = new JsonArray();
				pe.problems.stream().limit(50).forEach(arr::add);
				o.add("problems", arr);
			}
			send(ex, 200, o);
			return;
		}
		if (path.equals("/v1/jobs") && m.equals("POST")) {
			requireWrite();
			byte[] data = body(ex, 512 * 1024 * 1024);
			Plan plan = Plan.read(data, u.settings.maxPlanCells);
			ServerLevel level = u.jobs.levelOf(q.getOrDefault("dim", currentDim()));
			Job.Mode mode = Job.Mode.parse(q.get("mode"), Job.Mode.parse(u.settings.defaultMode, Job.Mode.WATCH));
			double seconds = q.containsKey("seconds") ? Double.parseDouble(q.get("seconds")) : u.settings.defaultSeconds;
			Job j;
			try {
				j = u.jobs.fromPlan(plan, level, mode, seconds, q.get("label"), q.getOrDefault("source", "api"),
					"1".equals(q.get("allow_modify")) || "true".equals(q.get("allow_modify")),
					"1".equals(q.get("allow_dangerous")) || "true".equals(q.get("allow_dangerous")));
			} catch (JobManager.PlanException pe) {
				JsonObject o = err("invalid_plan", pe.getMessage());
				JsonArray arr = new JsonArray();
				pe.problems.stream().limit(50).forEach(arr::add);
				o.add("problems", arr);
				send(ex, 422, o);
				return;
			}
			j.requestId = q.get("request");
			j.group = q.get("group");
			if ("1".equals(q.get("confirmed"))) j.confirmed = true;
			Job fj = j;
			JsonObject s = onServer(() -> {
				u.jobs.enqueue(fj);
				u.agent.attachJob(fj);
				return u.jobs.summary(fj);
			}, 5000);
			s.addProperty("ok", true);
			int pos = u.jobs.queued().indexOf(j);
			s.addProperty("queue_position", pos);
			send(ex, 200, s);
			return;
		}
		if (path.equals("/v1/jobs") && m.equals("GET")) {
			JsonObject o = new JsonObject();
			Job a = u.jobs.active();
			if (a != null) o.add("active", u.jobs.summary(a));
			JsonArray arr = new JsonArray();
			for (Job j : u.jobs.queued()) arr.add(u.jobs.summary(j));
			o.add("queued", arr);
			send(ex, 200, o);
			return;
		}
		if (path.startsWith("/v1/jobs/")) {
			String[] parts = path.substring("/v1/jobs/".length()).split("/");
			String id = parts[0];
			Job j = u.jobs.get(id);
			if (j == null) throw new HttpError(404, "no_job", "İş bulunamadı: " + id);
			if (parts.length == 1 && m.equals("GET")) {
				long wait = Math.min(55_000, Long.parseLong(q.getOrDefault("wait", "0")));
				long deadline = System.currentTimeMillis() + wait;
				while (!j.finished() && System.currentTimeMillis() < deadline) {
					Thread.sleep(150);
				}
				send(ex, 200, u.jobs.summary(j));
				return;
			}
			if (parts.length == 2 && m.equals("POST")) {
				boolean ok = switch (parts[1]) {
					case "cancel" -> u.jobs.cancel(id);
					case "pause" -> u.jobs.pause(id, true);
					case "resume" -> u.jobs.pause(id, false);
					case "confirm" -> u.jobs.confirm(id);
					case "speed" -> u.jobs.setSeconds(id, Double.parseDouble(q.getOrDefault("seconds", "0")));
					default -> throw new HttpError(404, "no_action", "Bilinmeyen işlem");
				};
				JsonObject o = u.jobs.summary(j);
				o.addProperty("ok", ok);
				send(ex, 200, o);
				return;
			}
		}
		if (path.equals("/v1/history") && m.equals("GET")) {
			JsonArray arr = new JsonArray();
			List<History.Entry> all = u.history.all();
			int limit = Integer.parseInt(q.getOrDefault("limit", "50"));
			for (int i = all.size() - 1; i >= 0 && arr.size() < limit; i--) arr.add(GSON.toJsonTree(all.get(i)));
			JsonObject o = new JsonObject();
			o.add("entries", arr);
			send(ex, 200, o);
			return;
		}
		if ((path.equals("/v1/undo") || path.equals("/v1/redo")) && m.equals("POST")) {
			requireWrite();
			JsonObject b = jsonBody(ex);
			boolean redo = path.endsWith("redo");
			String id = b.has("id") && !b.get("id").isJsonNull() ? b.get("id").getAsString() : null;
			boolean force = b.has("force") && b.get("force").getAsBoolean();
			JsonObject s = onServer(() -> undoRedo(redo, id, force, "api"), 10000);
			send(ex, s.get("ok").getAsBoolean() ? 200 : 409, s);
			return;
		}
		if (path.equals("/v1/chat") && m.equals("POST")) {
			JsonObject b = jsonBody(ex);
			String text = b.get("text").getAsString();
			if (text.length() > 600) text = text.substring(0, 600) + "…";
			String kind = b.has("kind") ? b.get("kind").getAsString() : "line";
			List<Chat.Button> buttons = new ArrayList<>();
			if (b.has("buttons")) {
				for (JsonElement e : b.getAsJsonArray("buttons")) {
					JsonObject bo = e.getAsJsonObject();
					String cmd = bo.get("command").getAsString();
					if (!cmd.startsWith("/usta ") && !cmd.startsWith("/claude")) continue; // yalniz kendi komutlarimiz
					buttons.add(new Chat.Button(bo.get("label").getAsString(), cmd, bo.has("hover") ? bo.get("hover").getAsString() : "",
						bo.has("suggest") && bo.get("suggest").getAsBoolean()));
				}
			}
			String ft = text;
			u.server.execute(() -> {
				var c = switch (kind) {
					case "soft" -> Chat.soft(ft);
					case "warn" -> Chat.warn(ft);
					case "error" -> Chat.error(ft);
					default -> Chat.line(ft);
				};
				Chat.toAll(u.server, buttons.isEmpty() ? c : Chat.withButtons(c, buttons));
			});
			JsonObject o = new JsonObject();
			o.addProperty("ok", true);
			send(ex, 200, o);
			return;
		}
		if (path.equals("/v1/events") && m.equals("GET")) {
			long since = Long.parseLong(q.getOrDefault("since", "0"));
			long wait = Math.min(25_000, Long.parseLong(q.getOrDefault("wait", "0")));
			send(ex, 200, u.events.poll(since, wait));
			return;
		}
		if (path.equals("/v1/screenshot") && m.equals("POST")) {
			ClientHook.Bridge b = ClientHook.bridge;
			if (b == null) throw new HttpError(409, "no_client", "İstemci yok (oyuncu ekranı alınamaz)");
			JsonObject body = jsonBody(ex);
			int maxW = body.has("max_width") ? body.get("max_width").getAsInt() : 1280;
			Path out = Paths.ensure(Paths.gameDir().resolve("screenshots").resolve("usta"))
				.resolve("usta-" + System.currentTimeMillis() + ".png");
			JsonObject r = b.screenshot(out, maxW).get(8, TimeUnit.SECONDS);
			send(ex, 200, r);
			return;
		}
		if (path.equals("/v1/colors") && m.equals("GET")) {
			ClientHook.Bridge b = ClientHook.bridge;
			if (b == null) throw new HttpError(409, "no_client", "İstemci yok");
			Path out = Paths.cache().resolve("colors-" + V.MC + ".json.gz");
			send(ex, 200, b.colors(out).get(60, TimeUnit.SECONDS));
			return;
		}
		if (path.equals("/v1/settings")) {
			if (m.equals("POST")) {
				JsonObject b = jsonBody(ex);
				Settings s = u.settings;
				if (b.has("defaultMode")) s.defaultMode = b.get("defaultMode").getAsString();
				if (b.has("defaultSeconds")) s.defaultSeconds = b.get("defaultSeconds").getAsDouble();
				if (b.has("effects")) s.effects = b.get("effects").getAsBoolean();
				if (b.has("celebration")) s.celebration = b.get("celebration").getAsBoolean();
				if (b.has("model")) s.model = b.get("model").getAsString();
				s.save();
			}
			send(ex, 200, JsonParser.parseString(u.settings.toJson()));
			return;
		}
		if (path.equals("/v1/protected")) {
			if (m.equals("POST")) {
				requireWrite();
				JsonObject b = jsonBody(ex);
				Protection.Region r = new Protection.Region();
				r.name = b.get("name").getAsString();
				r.dim = b.has("dim") ? b.get("dim").getAsString() : currentDim();
				r.x0 = Math.min(b.get("x0").getAsInt(), b.get("x1").getAsInt());
				r.x1 = Math.max(b.get("x0").getAsInt(), b.get("x1").getAsInt());
				r.y0 = Math.min(b.get("y0").getAsInt(), b.get("y1").getAsInt());
				r.y1 = Math.max(b.get("y0").getAsInt(), b.get("y1").getAsInt());
				r.z0 = Math.min(b.get("z0").getAsInt(), b.get("z1").getAsInt());
				r.z1 = Math.max(b.get("z0").getAsInt(), b.get("z1").getAsInt());
				u.protection.add(r);
			} else if (m.equals("DELETE")) {
				u.protection.remove(q.getOrDefault("name", ""));
			}
			JsonObject o = new JsonObject();
			o.add("regions", protectedJson());
			send(ex, 200, o);
			return;
		}
		if (path.equals("/v1/dev/command") && m.equals("POST")) {
			if (!Usta.testHarness()) throw new HttpError(404, "not_found", "Yalnız test düzeninde");
			JsonObject b = jsonBody(ex);
			String cmd = b.get("command").getAsString();
			if (cmd.equals("__gc__")) {
				System.gc();
				Thread.sleep(500);
				Runtime rt = Runtime.getRuntime();
				JsonObject o = new JsonObject();
				o.addProperty("ok", true);
				o.addProperty("heap_used_mb", (rt.totalMemory() - rt.freeMemory()) / (1024 * 1024));
				send(ex, 200, o);
				return;
			}
			onServer(() -> {
				u.server.getCommands().performPrefixedCommand(u.server.createCommandSourceStack(), cmd);
				return 1;
			}, 15000);
			JsonObject o = new JsonObject();
			o.addProperty("ok", true);
			send(ex, 200, o);
			return;
		}
		if (path.startsWith("/v1/agent/")) {
			u.agent.handleApi(ex, path.substring("/v1/agent/".length()), m, q, jsonBody(ex));
			return;
		}
		if (path.startsWith("/v1/world/")) {
			requireWrite();
			JsonObject wb = jsonBody(ex);
			JsonObject s = onServer(() -> dev.usta.game.WorldActions.handle(u, path.substring("/v1/world/".length()), wb), 10000);
			send(ex, s.has("ok") && !s.get("ok").getAsBoolean() ? 409 : 200, s);
			return;
		}
		throw new HttpError(404, "not_found", "Bilinmeyen uç: " + m + " " + path);
	}

	private String currentDim() {
		ServerPlayer p = u.player();
		return p == null ? "minecraft:overworld" : p.level().dimension().identifier().toString();
	}

	private JsonArray protectedJson() {
		JsonArray arr = new JsonArray();
		for (Protection.Region r : u.protection.all()) arr.add(GSON.toJsonTree(r));
		return arr;
	}

	/** Sunucu is parcaciginda. */
	public JsonObject undoRedo(boolean redo, String id, boolean force, String source) {
		JsonObject o = new JsonObject();
		History.Entry e = id != null ? u.history.get(id) : (redo ? u.history.lastUndone() : u.history.lastUndoable());
		if (e == null) {
			o.addProperty("ok", false);
			o.addProperty("message", redo ? "Yinelenecek iş yok" : "Geri alınacak iş yok");
			return o;
		}
		if (!redo && e.undone) {
			o.addProperty("ok", false);
			o.addProperty("message", "Bu iş zaten geri alınmış: " + e.label);
			return o;
		}
		if (redo && !e.undone) {
			o.addProperty("ok", false);
			o.addProperty("message", "Bu iş geri alınmamış: " + e.label);
			return o;
		}
		if (u.jobs.pendingFor(e.id)) {
			o.addProperty("ok", false);
			o.addProperty("pending", true);
			o.addProperty("message", (redo ? "Bu işin yinelenmesi" : "Bu işin geri alınması") + " zaten sürüyor: " + e.label);
			return o;
		}
		if ("ACTION".equals(e.kind)) {
			return dev.usta.game.WorldActions.undoRedo(u, e, redo);
		}
		if (e.group != null) {
			List<History.Entry> g = new java.util.ArrayList<>();
			for (History.Entry x : u.history.inGroup(e.group)) {
				if (x.undone == redo && "BUILD".equals(x.kind) && !u.jobs.pendingFor(x.id)) g.add(x);
			}
			if (g.size() > 1) return groupUndoRedo(g, redo, force, source);
		}
		if (!redo && !force) {
			List<History.Entry> later = u.history.laterOverlapping(e);
			if (!later.isEmpty()) {
				o.addProperty("ok", false);
				o.addProperty("message", "Bu alanda daha sonra yapılmış " + later.size() + " iş var; önce onları geri al (ya da force).");
				JsonArray arr = new JsonArray();
				for (History.Entry x : later) arr.add(x.id);
				o.add("later", arr);
				return o;
			}
		}
		// son kayit (arka planda) bitmeden geri alma/yineleme verisi okunmasin
		Job srcJob = u.jobs.get(e.id);
		if (srcJob != null && srcJob.saveFuture != null && !srcJob.saveFuture.isDone()) {
			try {
				srcJob.saveFuture.get(15, TimeUnit.SECONDS);
			} catch (Exception ignored) {
			}
		}
		try {
			Job j = redo ? u.jobs.makeRedo(e) : u.jobs.makeUndo(e);
			j.source = source;
			u.jobs.enqueue(j);
			o = u.jobs.summary(j);
			o.addProperty("ok", true);
			o.addProperty("target", e.id);
			return o;
		} catch (Exception ex2) {
			o.addProperty("ok", false);
			o.addProperty("message", "Geri alma verisi okunamadı: " + ex2.getMessage());
			return o;
		}
	}

	/** Cok parcali yapinin (ayni grup) butun parcalari: geri alma en yeniden eskiye, yineleme eskiden yeniye sirayla kuyruga. */
	private JsonObject groupUndoRedo(List<History.Entry> g, boolean redo, boolean force, String source) {
		JsonObject o = new JsonObject();
		if (!redo && !force) {
			java.util.Set<String> ids = new java.util.HashSet<>();
			for (History.Entry x : g) ids.add(x.id);
			java.util.LinkedHashSet<String> later = new java.util.LinkedHashSet<>();
			for (History.Entry x : g) for (History.Entry y : u.history.laterOverlapping(x)) if (!ids.contains(y.id)) later.add(y.id);
			if (!later.isEmpty()) {
				o.addProperty("ok", false);
				o.addProperty("message", "Bu alanda daha sonra yapılmış " + later.size() + " iş var; önce onları geri al (ya da force).");
				JsonArray arr = new JsonArray();
				later.forEach(arr::add);
				o.add("later", arr);
				return o;
			}
		}
		for (History.Entry x : g) {
			Job sj = u.jobs.get(x.id);
			if (sj != null && sj.saveFuture != null && !sj.saveFuture.isDone()) {
				try {
					sj.saveFuture.get(15, TimeUnit.SECONDS);
				} catch (Exception ignored) {
				}
			}
		}
		List<History.Entry> order = new java.util.ArrayList<>(g);
		if (!redo) java.util.Collections.reverse(order);
		Job first = null;
		JsonArray jobs = new JsonArray();
		try {
			for (History.Entry x : order) {
				Job j = redo ? u.jobs.makeRedo(x) : u.jobs.makeUndo(x);
				j.source = source;
				u.jobs.enqueue(j);
				if (first == null) first = j;
				jobs.add(j.id);
			}
		} catch (Exception ex2) {
			o.addProperty("ok", false);
			o.addProperty("message", "Geri alma verisi okunamadı: " + ex2.getMessage());
			return o;
		}
		o = u.jobs.summary(first);
		o.addProperty("ok", true);
		o.addProperty("target", order.get(0).id);
		o.addProperty("group", g.get(0).group);
		o.addProperty("parts", order.size());
		o.add("jobs", jobs);
		return o;
	}

	private JsonObject status() {
		JsonObject o = new JsonObject();
		o.addProperty("ok", true);
		o.addProperty("mod", UstaMod.version());
		o.addProperty("mc", V.MC);
		o.addProperty("world", u.worldKey);
		o.addProperty("paused", u.server.isPaused());
		o.addProperty("ai_enabled", u.aiEnabled);
		if (u.disabledReason != null) o.addProperty("disabled_reason", u.disabledReason);
		o.addProperty("activated", u.activated());
		o.addProperty("backup_running", u.backupRunning());
		o.addProperty("players", u.server.getPlayerList().getPlayerCount());
		o.addProperty("avg_tick_ms", Math.round(u.server.getAverageTickTimeNanos() / 1e4) / 100.0);
		long maxTick = 0;
		for (long t : u.server.getTickTimesNanos()) maxTick = Math.max(maxTick, t);
		o.addProperty("max_tick_ms_100", Math.round(maxTick / 1e4) / 100.0); // son 100 tick'in en uzunu
		o.addProperty("tick", u.server.getTickCount());
		Job a = u.jobs.active();
		if (a != null) o.add("active_job", u.jobs.summary(a));
		o.addProperty("queued_jobs", u.jobs.queued().size());
		o.add("agent", u.agent.statusJson());
		ClientHook.Bridge b = ClientHook.bridge;
		if (b != null) o.add("client", b.state());
		o.addProperty("history_size", u.history.all().size());
		Runtime rt = Runtime.getRuntime();
		o.addProperty("heap_used_mb", (rt.totalMemory() - rt.freeMemory()) / (1024 * 1024));
		o.addProperty("heap_max_mb", rt.maxMemory() / (1024 * 1024));
		return o;
	}
}
