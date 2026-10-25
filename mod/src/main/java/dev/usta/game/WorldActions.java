package dev.usta.game;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.usta.compat.V;
import dev.usta.core.Usta;
import dev.usta.engine.History;
import java.util.Set;
import java.util.UUID;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.saveddata.WeatherData;

/**
 * Zaman, hava ve isinlanma: yalniz acik istekle (M2); her degisiklik tek cumleyle bildirilir ve geri alinabilir.
 */
public final class WorldActions {
	private WorldActions() {}

	private static long targetTimeOfDay(String s) {
		return switch (s.toLowerCase()) {
			case "sunrise", "sabah", "gundogumu", "gündoğumu" -> 0;
			case "day", "gun", "gün", "gunduz", "gündüz" -> 1000;
			case "noon", "ogle", "öğle", "oglen", "öğlen" -> 6000;
			case "sunset", "aksam", "akşam", "gunbatimi", "günbatımı" -> 12000;
			case "night", "gece" -> 13000;
			case "midnight", "geceyarisi", "gece yarısı" -> 18000;
			default -> Long.parseLong(s);
		};
	}

	/** Sunucu is parcaciginda. */
	public static JsonObject handle(Usta u, String action, JsonObject b) {
		JsonObject res = new JsonObject();
		JsonObject data = new JsonObject();
		String say;
		switch (action) {
			case "time" -> {
				long cur = V.overworldClockTicks(u.server);
				if (cur < 0) return fail(res, "Dünya saati okunamadı");
				long tod = targetTimeOfDay(b.get("set").getAsString()) % 24000;
				long base = (cur / 24000) * 24000;
				long nt = base + tod;
				if (nt < cur) nt += 24000;
				V.setOverworldClockTicks(u.server, nt);
				data.addProperty("old", cur);
				data.addProperty("new", nt);
				say = "Saat değiştirildi (" + tod + "). Geri alınabilir.";
			}
			case "weather" -> {
				WeatherData w = u.server.getWeatherData();
				data.addProperty("old_clear", w.getClearWeatherTime());
				data.addProperty("old_rain", w.getRainTime());
				data.addProperty("old_thunder", w.getThunderTime());
				data.addProperty("old_raining", w.isRaining());
				data.addProperty("old_thundering", w.isThundering());
				String set = b.get("set").getAsString().toLowerCase();
				int dur = b.has("duration") ? b.get("duration").getAsInt() : 6000;
				switch (set) {
					case "clear", "acik", "açık", "gunesli", "güneşli" -> u.server.setWeatherParameters(dur, 0, false, false);
					case "rain", "yagmur", "yağmur" -> u.server.setWeatherParameters(0, dur, true, false);
					case "thunder", "firtina", "fırtına" -> u.server.setWeatherParameters(0, dur, true, true);
					default -> {
						return fail(res, "Bilinmeyen hava: " + set);
					}
				}
				data.addProperty("new", set);
				data.addProperty("duration", dur);
				say = "Hava değişti: " + set + ". Geri alınabilir.";
			}
			case "teleport" -> {
				ServerPlayer p = u.player();
				if (p == null) return fail(res, "Oyuncu yok");
				ServerLevel lvl = b.has("dim") ? u.jobs.levelOf(b.get("dim").getAsString()) : p.level();
				data.addProperty("old_x", p.getX());
				data.addProperty("old_y", p.getY());
				data.addProperty("old_z", p.getZ());
				data.addProperty("old_yaw", p.getYRot());
				data.addProperty("old_pitch", p.getXRot());
				data.addProperty("old_dim", p.level().dimension().identifier().toString());
				double x = b.get("x").getAsDouble(), y = b.get("y").getAsDouble(), z = b.get("z").getAsDouble();
				float yaw = b.has("yaw") ? b.get("yaw").getAsFloat() : p.getYRot();
				float pitch = b.has("pitch") ? b.get("pitch").getAsFloat() : p.getXRot();
				p.teleportTo(lvl, x, y, z, Set.of(), yaw, pitch, false);
				data.addProperty("x", x);
				data.addProperty("y", y);
				data.addProperty("z", z);
				data.addProperty("yaw", yaw);
				data.addProperty("pitch", pitch);
				data.addProperty("dim", lvl.dimension().identifier().toString());
				say = "Seni ışınladım. Geri alınabilir.";
			}
			default -> {
				return fail(res, "Bilinmeyen işlem: " + action);
			}
		}
		History.Entry e = new History.Entry();
		e.id = Long.toString(System.currentTimeMillis(), 36) + "-" + UUID.randomUUID().toString().substring(0, 6);
		e.kind = "ACTION";
		e.action = action;
		e.actionData = data.toString();
		e.label = switch (action) {
			case "time" -> "zaman";
			case "weather" -> "hava";
			default -> "ışınlanma";
		};
		e.state = "DONE";
		e.created = e.finished = System.currentTimeMillis();
		e.source = b.has("source") ? b.get("source").getAsString() : "api";
		u.history.put(e);
		Chat.toAll(u.server, Chat.withButtons(Chat.soft(say), java.util.List.of(Chat.Button.run("Geri al", "/usta geri " + e.id, "Bu değişikliği geri al"))));
		res.addProperty("ok", true);
		res.addProperty("id", e.id);
		res.add("data", data);
		return res;
	}

	/** ACTION gecmis kaydini geri alir (redo=false) ya da yineler (redo=true). Sunucu is parcaciginda. */
	public static JsonObject undoRedo(Usta u, History.Entry e, boolean redo) {
		JsonObject res = new JsonObject();
		JsonObject d = JsonParser.parseString(e.actionData).getAsJsonObject();
		switch (e.action) {
			case "time" -> V.setOverworldClockTicks(u.server, redo ? d.get("new").getAsLong() : d.get("old").getAsLong());
			case "weather" -> {
				if (redo) {
					String set = d.get("new").getAsString();
					int dur = d.get("duration").getAsInt();
					boolean thunder = set.startsWith("thunder") || set.startsWith("f");
					boolean rain = thunder || set.startsWith("rain") || set.startsWith("yag") || set.startsWith("yağ");
					u.server.setWeatherParameters(rain ? 0 : dur, rain ? dur : 0, rain, thunder);
				} else {
					WeatherData w = u.server.getWeatherData();
					u.server.setWeatherParameters(d.get("old_clear").getAsInt(), d.get("old_rain").getAsInt(),
						d.get("old_raining").getAsBoolean(), d.get("old_thundering").getAsBoolean());
					w.setThunderTime(d.get("old_thunder").getAsInt());
				}
			}
			case "teleport" -> {
				ServerPlayer p = u.player();
				if (p == null) return fail(res, "Oyuncu yok");
				String pre = redo ? "" : "old_";
				ServerLevel lvl = u.jobs.levelOf(d.get(pre + "dim").getAsString());
				p.teleportTo(lvl, d.get(pre + "x").getAsDouble(), d.get(pre + "y").getAsDouble(), d.get(pre + "z").getAsDouble(), Set.of(),
					d.get(pre + "yaw").getAsFloat(), d.get(pre + "pitch").getAsFloat(), false);
			}
			default -> {
				return fail(res, "Bilinmeyen işlem");
			}
		}
		e.undone = !redo;
		e.finished = System.currentTimeMillis();
		u.history.put(e);
		Chat.toAll(u.server, Chat.soft((redo ? "Yinelendi: " : "Geri alındı: ") + e.label + "."));
		res.addProperty("ok", true);
		res.addProperty("target", e.id);
		res.addProperty("state", "DONE");
		return res;
	}

	private static JsonObject fail(JsonObject o, String msg) {
		o.addProperty("ok", false);
		o.addProperty("message", msg);
		return o;
	}
}
