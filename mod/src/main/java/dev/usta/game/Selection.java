package dev.usta.game;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.usta.core.Paths;
import dev.usta.core.Usta;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;

/** Iki koseli secim (dunya basina, diskte). */
public final class Selection {
	private Selection() {}

	private static Path file(Usta u) {
		return u.worldDir.resolve("secim.json");
	}

	private static JsonObject read(Usta u) {
		try {
			Path f = file(u);
			if (Files.exists(f)) return JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
		} catch (Exception ignored) {
		}
		return new JsonObject();
	}

	public static void set(Usta u, int k, BlockPos p, String dim) {
		JsonObject o = read(u);
		JsonObject c = new JsonObject();
		c.addProperty("x", p.getX());
		c.addProperty("y", p.getY());
		c.addProperty("z", p.getZ());
		o.add("p" + k, c);
		o.addProperty("dim", dim);
		try {
			Paths.writeAtomic(file(u), o.toString());
		} catch (Exception ignored) {
		}
	}

	public static void clear(Usta u) {
		try {
			Files.deleteIfExists(file(u));
		} catch (Exception ignored) {
		}
	}

	public static String dim(Usta u) {
		JsonObject o = read(u);
		return o.has("dim") ? o.get("dim").getAsString() : "minecraft:overworld";
	}

	/** min x,y,z, max x,y,z ya da null */
	public static int[] box(Usta u) {
		JsonObject o = read(u);
		if (!o.has("p1") || !o.has("p2")) return null;
		JsonObject a = o.getAsJsonObject("p1"), b = o.getAsJsonObject("p2");
		return new int[]{
			Math.min(a.get("x").getAsInt(), b.get("x").getAsInt()), Math.min(a.get("y").getAsInt(), b.get("y").getAsInt()),
			Math.min(a.get("z").getAsInt(), b.get("z").getAsInt()), Math.max(a.get("x").getAsInt(), b.get("x").getAsInt()),
			Math.max(a.get("y").getAsInt(), b.get("y").getAsInt()), Math.max(a.get("z").getAsInt(), b.get("z").getAsInt())};
	}

	public static JsonObject json(Usta u) {
		return read(u);
	}

	/** Secimi ince parcacik cizgisiyle gosterir. */
	public static void show(Usta u, ServerLevel level) {
		int[] b = box(u);
		if (b == null) return;
		double x0 = b[0], y0 = b[1], z0 = b[2], x1 = b[3] + 1, y1 = b[4] + 1, z1 = b[5] + 1;
		int steps = 20;
		for (int i = 0; i <= steps; i++) {
			double t = i / (double) steps;
			double x = x0 + (x1 - x0) * t, z = z0 + (z1 - z0) * t, y = y0 + (y1 - y0) * t;
			for (double yy : new double[]{y0, y1}) {
				level.sendParticles(ParticleTypes.HAPPY_VILLAGER, x, yy, z0, 1, 0, 0, 0, 0);
				level.sendParticles(ParticleTypes.HAPPY_VILLAGER, x, yy, z1, 1, 0, 0, 0, 0);
				level.sendParticles(ParticleTypes.HAPPY_VILLAGER, x0, yy, z, 1, 0, 0, 0, 0);
				level.sendParticles(ParticleTypes.HAPPY_VILLAGER, x1, yy, z, 1, 0, 0, 0, 0);
			}
			for (double[] c : new double[][]{{x0, z0}, {x1, z0}, {x0, z1}, {x1, z1}}) {
				level.sendParticles(ParticleTypes.HAPPY_VILLAGER, c[0], y, c[1], 1, 0, 0, 0, 0);
			}
		}
	}
}
