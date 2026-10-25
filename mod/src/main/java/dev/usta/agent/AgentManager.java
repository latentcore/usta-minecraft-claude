package dev.usta.agent;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import dev.usta.UstaMod;
import dev.usta.core.Paths;
import dev.usta.core.Usta;
import dev.usta.engine.Job;
import dev.usta.game.Chat;
import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import net.minecraft.server.level.ServerPlayer;

/**
 * Oyun ici ve panel istekleri: basliksiz Claude kosucusunu (python -m usta.agent) baslatir, siraya koyar,
 * durum satirlarini sohbete aktarir, iptal eder; dunya basina konusma kimligini tutar (C6).
 */
public final class AgentManager {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
	private final Usta u;
	private final Deque<Request> queue = new ArrayDeque<>();
	private final Map<String, Request> all = new ConcurrentHashMap<>();
	private static final long MAX_AGENT_MS = 3 * 60 * 60_000L;   // son care siniri; /usta iptal her zaman calisir
	private volatile Request active;
	private Process proc;
	private Request pendingActivation;

	public static final class Request {
		public String id;
		public String text;
		public String source;
		public long created;
		public double x, y, z;
		public float yaw, pitch;
		public String dim;
		public String facing;
		public volatile String state = "queued";
		public String session;
		public String model;
		public List<String> jobs = new ArrayList<>();
		public String lastStatus;
		public long lastStatusAt;
		public String finalText;
		public long started;
		public boolean longWarned;
		public long firstReplyMs = -1;
	}

	public AgentManager(Usta u) {
		this.u = u;
	}

	public Request active() {
		return active;
	}

	private Path conversationFile() {
		return u.worldDir.resolve("konusma.json");
	}

	public String session() {
		try {
			Path f = conversationFile();
			if (!Files.exists(f)) return null;
			JsonObject o = JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
			return o.has("session") && !o.get("session").isJsonNull() ? o.get("session").getAsString() : null;
		} catch (Exception e) {
			return null;
		}
	}

	public void resetConversation() {
		try {
			Files.deleteIfExists(conversationFile());
		} catch (IOException ignored) {
		}
	}

	private void saveSession(String session, Request r) {
		JsonObject o = new JsonObject();
		o.addProperty("session", session);
		o.addProperty("updated", System.currentTimeMillis());
		o.addProperty("last_request", r.text);
		JsonArray jobs = new JsonArray();
		r.jobs.forEach(jobs::add);
		o.add("last_jobs", jobs);
		try {
			Paths.writeAtomic(conversationFile(), o.toString());
		} catch (IOException ignored) {
		}
	}

	/** Sunucu is parcaciginda: yeni istek. */
	public Request submit(String text, String source, ServerPlayer p) {
		long t0 = System.currentTimeMillis();
		Request r = new Request();
		r.id = "r" + Long.toString(t0, 36) + UUID.randomUUID().toString().substring(0, 4);
		r.text = text.strip();
		r.source = source;
		r.created = t0;
		if (p != null) {
			r.x = p.getX();
			r.y = p.getY();
			r.z = p.getZ();
			r.yaw = p.getYRot();
			r.pitch = p.getXRot();
			r.dim = p.level().dimension().identifier().toString();
			r.facing = p.getDirection().getName();
		} else {
			r.dim = "minecraft:overworld";
		}
		all.put(r.id, r);
		if (!u.aiEnabled) {
			Chat.toAll(u.server, Chat.error(u.disabledReason == null ? "Usta şu an kapalı." : u.disabledReason));
			r.state = "failed";
			return r;
		}
		if (!u.activated()) {
			pendingActivation = r;
			u.promptActivation();
			r.state = "waiting_activation";
			return r;
		}
		enqueue(r);
		return r;
	}

	private void enqueue(Request r) {
		synchronized (this) {
			queue.addLast(r);
		}
		if (active != null) {
			Chat.toAll(u.server, Chat.soft("Sıraya aldım: önceki istek bitince başlayacağım."));
		} else {
			Chat.toAll(u.server, Chat.soft("Anladım. Önündeki araziye bakıyorum…"));
		}
		r.firstReplyMs = System.currentTimeMillis() - r.created;
		u.events.publish("agent_queued", json(r));
	}

	/** Etkinlestirme bitince bekleyen istegi baslat. */
	public void onActivated() {
		Request r = pendingActivation;
		pendingActivation = null;
		if (r != null) {
			r.state = "queued";
			enqueue(r);
		}
	}

	public void tick() {
		Request r = active;
		if (r == null) {
			if (u.backupRunning()) return;
			synchronized (this) {
				r = queue.pollFirst();
			}
			if (r == null) return;
			start(r);
			return;
		}
		Process p = proc;
		if (p != null && !p.isAlive() && !"done".equals(r.state) && !"failed".equals(r.state) && !"cancelled".equals(r.state)) {
			int code = p.exitValue();
			r.state = "failed";
			Chat.toAll(u.server, Chat.error("Claude oturumu beklenmedik biçimde kapandı (kod " + code + "). Ayrıntı: usta/logs/agent-" + r.id + ".log"));
			finishActive();
		} else if (r.started > 0) {
			// Uzun dusunme (Opus + !max) 20 dakikayi rahat asar: kesme, yalniz bir kez hatirlat; son care siniri 3 saat
			long age = System.currentTimeMillis() - r.started;
			if (!r.longWarned && age > 20 * 60_000L) {
				r.longWarned = true;
				Chat.toAll(u.server, Chat.soft("Uzun bir iş; Claude çalışmaya devam ediyor. Durdurmak istersen: /usta iptal"));
			}
			if (age > MAX_AGENT_MS) {
				Chat.toAll(u.server, Chat.error("İstek 3 saati aştı; Claude oturumunu durduruyorum (kurulmakta olan yapı yarıda kesilmez)."));
				cancel(r.id, "zaman aşımı", false);
			}
		}
	}

	private JsonObject bridgeConfig() {
		try {
			Path f = Paths.root().resolve("bridge.json");
			if (!Files.exists(f)) return null;
			return JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
		} catch (Exception e) {
			return null;
		}
	}

	private void start(Request r) {
		active = r;
		r.state = "running";
		r.started = System.currentTimeMillis();
		r.session = session();
		JsonObject cfg = bridgeConfig();
		if (cfg == null || !cfg.has("python")) {
			Chat.toAll(u.server, Chat.error("Köprü kurulu değil (usta/bridge.json yok). KUR.bat'ı çalıştırman gerekiyor."));
			r.state = "failed";
			finishActive();
			return;
		}
		try {
			Path work = Paths.ensure(Paths.agentWork().resolve(r.id));
			JsonObject req = json(r);
			req.addProperty("world_key", u.worldKey);
			req.addProperty("game_dir", Paths.gameDir().toAbsolutePath().toString());
			req.addProperty("model_pref", u.settings.model);
			if (r.session != null) req.addProperty("session", r.session);
			Path reqFile = work.resolve("request.json");
			Files.writeString(reqFile, req.toString(), StandardCharsets.UTF_8);
			List<String> cmd = new ArrayList<>();
			cmd.add(cfg.get("python").getAsString());
			cmd.add("-m");
			cmd.add("usta.agent");
			cmd.add("--request");
			cmd.add(reqFile.toAbsolutePath().toString());
			ProcessBuilder pb = new ProcessBuilder(cmd);
			pb.directory(work.toFile());
			Map<String, String> env = pb.environment();
			env.put("USTA_GAME_DIR", Paths.gameDir().toAbsolutePath().toString());
			env.put("PYTHONIOENCODING", "utf-8");
			env.put("PYTHONUTF8", "1");
			if (cfg.has("pythonpath")) env.put("PYTHONPATH", cfg.get("pythonpath").getAsString());
			// Claude Code ortam degiskenleri ebeveynden sizmasin
			env.keySet().removeIf(k -> k.startsWith("CLAUDE") || k.startsWith("ANTHROPIC"));
			File log = Paths.ensure(Paths.logs()).resolve("agent-" + r.id + ".log").toFile();
			pb.redirectErrorStream(true);
			pb.redirectOutput(ProcessBuilder.Redirect.appendTo(log));
			proc = pb.start();
			u.events.publish("agent_started", json(r));
		} catch (Exception e) {
			UstaMod.LOG.warn("Ajan baslatilamadi", e);
			Chat.toAll(u.server, Chat.error("Claude koşucusu başlatılamadı: " + e.getMessage()));
			r.state = "failed";
			finishActive();
		}
	}

	private void finishActive() {
		Request r = active;
		active = null;
		proc = null;
		if (r != null) u.events.publish("agent_finished", json(r));
	}

	public boolean cancel(String id, String why) {
		return cancel(id, why, true);
	}

	/** jobsToo=false: yalniz Claude oturumu durur; istegin baslattigi insa isleri bitene kadar surer (zaman asimi). */
	public boolean cancel(String id, String why, boolean jobsToo) {
		Request r = id == null ? active : all.get(id);
		if (r == null) return false;
		synchronized (this) {
			queue.remove(r);
		}
		if (r == active) {
			Process p = proc;
			if (p != null) {
				p.descendants().forEach(ProcessHandle::destroyForcibly);
				p.destroyForcibly();
			}
			if (jobsToo) {
				for (String jid : r.jobs) u.jobs.cancel(jid);
			}
			r.state = "cancelled";
			finishActive();
		} else {
			r.state = "cancelled";
		}
		Chat.toAll(u.server, Chat.soft("İstek iptal edildi" + (why == null ? "." : " (" + why + ").")));
		return true;
	}

	public void cancelAll(String why) {
		synchronized (this) {
			queue.clear();
		}
		if (active != null) cancel(active.id, why);
	}

	public void shutdown() {
		Process p = proc;
		if (p != null) {
			p.descendants().forEach(ProcessHandle::destroyForcibly);
			p.destroyForcibly();
		}
	}

	public void attachJob(Job j) {
		if (j.requestId == null) return;
		Request r = all.get(j.requestId);
		if (r != null && !r.jobs.contains(j.id)) r.jobs.add(j.id);
	}

	public void onJobFinished(Job j) {
		// ajan is durumunu kendi araclariyla izler; burada yalniz olay yayimlanir
	}

	public JsonObject statusJson() {
		JsonObject o = new JsonObject();
		Request r = active;
		if (r != null) o.add("active", json(r));
		synchronized (this) {
			o.addProperty("queued", queue.size());
		}
		o.addProperty("has_session", session() != null);
		return o;
	}

	public static JsonObject json(Request r) {
		JsonObject o = new JsonObject();
		o.addProperty("id", r.id);
		o.addProperty("text", r.text);
		o.addProperty("source", r.source);
		o.addProperty("state", r.state);
		o.addProperty("created", r.created);
		JsonObject a = new JsonObject();
		a.addProperty("x", Math.round(r.x * 100) / 100.0);
		a.addProperty("y", Math.round(r.y * 100) / 100.0);
		a.addProperty("z", Math.round(r.z * 100) / 100.0);
		a.addProperty("yaw", r.yaw);
		a.addProperty("pitch", r.pitch);
		a.addProperty("dim", r.dim);
		a.addProperty("facing", r.facing);
		o.add("anchor", a);
		JsonArray jobs = new JsonArray();
		r.jobs.forEach(jobs::add);
		o.add("jobs", jobs);
		if (r.lastStatus != null) o.addProperty("last_status", r.lastStatus);
		if (r.model != null) o.addProperty("model", r.model);
		if (r.finalText != null) o.addProperty("final", r.finalText);
		if (r.firstReplyMs >= 0) o.addProperty("first_reply_ms", r.firstReplyMs);
		return o;
	}

	// ------------------------------------------------------------------ API
	public void handleApi(HttpExchange ex, String sub, String method, Map<String, String> q, JsonObject body) throws Exception {
		JsonObject res;
		if (sub.equals("request") && method.equals("POST")) {
			String text = body.get("text").getAsString();
			String source = body.has("source") ? body.get("source").getAsString() : "panel";
			Request r = u.server.submit(() -> {
				ServerPlayer p = u.player();
				return submit(text, source, p);
			}).get(5, TimeUnit.SECONDS);
			res = json(r);
		} else if (sub.startsWith("request/") && method.equals("GET")) {
			Request r = all.get(sub.substring("request/".length()));
			if (r == null) {
				res = new JsonObject();
				res.addProperty("ok", false);
				res.addProperty("message", "istek yok");
			} else {
				res = json(r);
			}
		} else if (sub.equals("status") && method.equals("POST")) {
			Request r = all.get(body.get("request").getAsString());
			String text = body.get("text").getAsString();
			if (text.length() > 300) text = text.substring(0, 300) + "…";
			if (r != null) {
				r.lastStatus = text;
				r.lastStatusAt = System.currentTimeMillis();
				if (body.has("model")) r.model = body.get("model").getAsString();
			}
			String ft = text;
			u.server.execute(() -> Chat.toAll(u.server, Chat.soft(ft)));
			u.events.publish("agent_status", body);
			res = new JsonObject();
			res.addProperty("ok", true);
		} else if (sub.equals("done") && method.equals("POST")) {
			Request r = all.get(body.get("request").getAsString());
			boolean ok = body.has("ok") && body.get("ok").getAsBoolean();
			String text = body.has("text") ? body.get("text").getAsString() : (ok ? "Bitti." : "Yapılamadı.");
			if (text.length() > 500) text = text.substring(0, 500) + "…";
			String session = body.has("session") && !body.get("session").isJsonNull() ? body.get("session").getAsString() : null;
			String ft = text;
			if (r != null) r.state = ok ? "done" : "failed";   // hemen: surec cikisiyla yaris olmasin (tick "beklenmedik kapanma" demesin)
			u.server.execute(() -> {
				if (r != null) {
					r.finalText = ft;
					r.state = ok ? "done" : "failed";
					if (session != null) saveSession(session, r);
					String lastJob = null;
					for (String jid : r.jobs) {
						Job j = u.jobs.get(jid);
						if (j != null && j.kind == Job.Kind.BUILD && j.state == Job.State.DONE) lastJob = jid;
					}
					if (ok && lastJob != null) {
						Chat.toAll(u.server, Chat.withButtons(Chat.line(ft), Chat.doneButtons(lastJob)));
					} else {
						Chat.toAll(u.server, ok ? Chat.line(ft) : Chat.error(ft));
					}
					if (r == active) finishActive();
				}
			});
			res = new JsonObject();
			res.addProperty("ok", true);
		} else if (sub.equals("cancel") && method.equals("POST")) {
			String id = body.has("request") ? body.get("request").getAsString() : null;
			boolean ok = u.server.submit(() -> cancel(id, null)).get(5, TimeUnit.SECONDS);
			res = new JsonObject();
			res.addProperty("ok", ok);
		} else if (sub.equals("state") && method.equals("GET")) {
			res = statusJson();
		} else {
			res = new JsonObject();
			res.addProperty("ok", false);
			res.addProperty("message", "bilinmeyen ajan ucu");
		}
		byte[] b = res.toString().getBytes(StandardCharsets.UTF_8);
		ex.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
		ex.sendResponseHeaders(200, b.length);
		try (OutputStream os = ex.getResponseBody()) {
			os.write(b);
		}
	}

	@SuppressWarnings("unused")
	private static String pretty(Object o) {
		return GSON.toJson(o);
	}
}
