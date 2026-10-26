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
	/** Claude'un calistirabilecegi oyun komutlari. Yonetici/sunucu komutlari (op, stop, ban, reload, save…) yok; blok yazan
	 * komutlar (fill, setblock, clone, place) da yok: dunya degisikligi her zaman geri alinabilir Usta planiyla yapilir. */
	static final Set<String> ALLOWED_COMMANDS = Set.of("give", "effect", "summon", "gamerule", "difficulty", "xp", "experience",
		"enchant", "tp", "teleport", "time", "weather", "playsound", "stopsound", "particle", "title", "clear", "item", "attribute",
		"spawnpoint", "setworldspawn", "locate", "tellraw", "ride", "tag", "gamemode", "worldborder", "random", "rotate", "loot",
		"spreadplayers", "recipe", "advancement");

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
			case "command" -> {
				// oyun komutu kapisi: yalniz izinli komutlar; cikti geri doner. Komutlar geri alinamaz (oyuncu istediyse calisir).
				String cmd = b.get("command").getAsString().trim();
				if (cmd.startsWith("/")) cmd = cmd.substring(1);
				String root = cmd.split("\\s+", 2)[0].toLowerCase(java.util.Locale.ROOT);
				if (root.equals("kill") || root.equals("damage")) {
					return fail(res, "Canlı silmek/yaralamak için remove_entities kullan (oyuncu, evcil, adlı ve köylüler korunur).");
				}
				if (!ALLOWED_COMMANDS.contains(root)) {
					return fail(res, "Bu komuta izin yok: " + root + ". İzinli: " + String.join(", ", new java.util.TreeSet<>(ALLOWED_COMMANDS)));
				}
				java.util.List<String> out = new java.util.ArrayList<>();
				net.minecraft.commands.CommandSource cap = new net.minecraft.commands.CommandSource() {
					@Override
					public void sendSystemMessage(net.minecraft.network.chat.Component message) {
						if (out.size() < 40) out.add(message.getString());
					}

					@Override
					public boolean acceptsSuccess() {
						return true;
					}

					@Override
					public boolean acceptsFailure() {
						return true;
					}

					@Override
					public boolean shouldInformAdmins() {
						return false;
					}
				};
				net.minecraft.commands.CommandSourceStack st = u.server.createCommandSourceStack().withSource(cap);
				ServerPlayer p = u.player();
				if (p != null) st = st.withEntity(p).withPosition(p.position()).withLevel(p.level()).withRotation(p.getRotationVector());
				u.server.getCommands().performPrefixedCommand(st, cmd);
				data.addProperty("command", cmd);
				com.google.gson.JsonArray arr = new com.google.gson.JsonArray();
				out.forEach(arr::add);
				data.add("output", arr);
				say = "Komut: /" + cmd + (out.isEmpty() ? "" : " → " + out.get(out.size() - 1));
			}
			case "entities_remove" -> {
				// canli temizleme: oyuncu, evcil, adli, koylu ve yardimcilar (EntityGuard) hic silinmez
				ServerPlayer p = u.player();
				ServerLevel lvl = b.has("dim") ? u.jobs.levelOf(b.get("dim").getAsString()) : (p != null ? p.level() : u.server.overworld());
				double cx = b.has("x") ? b.get("x").getAsDouble() : (p != null ? p.getX() : 0);
				double cy = b.has("y") ? b.get("y").getAsDouble() : (p != null ? p.getY() : 64);
				double cz = b.has("z") ? b.get("z").getAsDouble() : (p != null ? p.getZ() : 0);
				double r = Math.max(1, Math.min(96, b.has("radius") ? b.get("radius").getAsDouble() : 24));
				java.util.Set<String> types = new java.util.HashSet<>();
				if (b.has("types")) b.getAsJsonArray("types").forEach(t -> types.add(t.getAsString().contains(":") ? t.getAsString() : "minecraft:" + t.getAsString()));
				if (types.isEmpty()) return fail(res, "Hangi canlılar? types ver (ör. [\"zombie\"] ya da [\"hostile\"]).");
				boolean hostile = types.remove("minecraft:hostile");
				net.minecraft.world.phys.AABB box = new net.minecraft.world.phys.AABB(cx - r, cy - r, cz - r, cx + r, cy + r, cz + r);
				int removed = 0, skipped = 0;
				for (net.minecraft.world.entity.Entity en : lvl.getEntities((net.minecraft.world.entity.Entity) null, box, en -> en.isAlive())) {
					String id = net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(en.getType()).toString();
					boolean match = types.contains(id) || (hostile && en instanceof net.minecraft.world.entity.monster.Enemy);
					if (!match) continue;
					if (en instanceof net.minecraft.world.entity.player.Player || dev.usta.world.EntityGuard.isProtected(en)) {
						skipped++;
						continue;
					}
					en.discard();
					removed++;
				}
				data.addProperty("removed", removed);
				data.addProperty("protected_skipped", skipped);
				say = removed + " canlı kaldırıldı" + (skipped > 0 ? " (" + skipped + " korunan canlıya dokunulmadı)" : "") + ".";
			}
			default -> {
				return fail(res, "Bilinmeyen işlem: " + action);
			}
		}
		boolean undoable = !action.equals("command") && !action.equals("entities_remove");
		History.Entry e = new History.Entry();
		e.id = Long.toString(System.currentTimeMillis(), 36) + "-" + UUID.randomUUID().toString().substring(0, 6);
		e.kind = "ACTION";
		e.action = action;
		e.actionData = data.toString();
		e.label = switch (action) {
			case "time" -> "zaman";
			case "weather" -> "hava";
			case "command" -> "komut";
			case "entities_remove" -> "canlı temizleme";
			default -> "ışınlanma";
		};
		e.state = "DONE";
		e.created = e.finished = System.currentTimeMillis();
		e.source = b.has("source") ? b.get("source").getAsString() : "api";
		if (undoable) {
			u.history.put(e);
			Chat.toAll(u.server, Chat.withButtons(Chat.soft(say), java.util.List.of(Chat.Button.run("Geri al", "/usta geri " + e.id, "Bu değişikliği geri al"))));
		} else {
			// geri alinamaz: gecmise yazilmaz (sahte "Geri al" dugmesi olmasin), mod gunlugune yazilir
			dev.usta.UstaMod.LOG.info("Usta {} ({}): {}", e.label, e.source, data);
			Chat.toAll(u.server, Chat.soft(say));
		}
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
