package dev.usta.game;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.usta.UstaMod;
import dev.usta.core.Paths;
import dev.usta.core.Usta;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Python yardimcilarini (python -m usta.tools <is> [arg]) baslatir: fotograf, harita, kaydet, panel, kutuphane.
 * Sonuc mesajlarini yardimci, oyun API'si uzerinden sohbete yazar.
 */
public final class ToolRunner {
	private ToolRunner() {}

	public static void run(Usta u, String what, String arg) {
		JsonObject cfg;
		try {
			Path f = Paths.root().resolve("bridge.json");
			if (!Files.exists(f)) {
				Chat.toAll(u.server, Chat.error("Köprü kurulu değil (usta/bridge.json yok). KUR.bat'ı çalıştırman gerekiyor."));
				return;
			}
			cfg = JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
		} catch (Exception e) {
			Chat.toAll(u.server, Chat.error("Köprü ayarı okunamadı: " + e.getMessage()));
			return;
		}
		try {
			List<String> cmd = new ArrayList<>();
			cmd.add(cfg.get("python").getAsString());
			cmd.add("-m");
			cmd.add("usta.tools");
			cmd.add(what);
			if (arg != null) cmd.add(arg);
			ProcessBuilder pb = new ProcessBuilder(cmd);
			pb.directory(Paths.ensure(Paths.agentWork()).toFile());
			Map<String, String> env = pb.environment();
			env.put("USTA_GAME_DIR", Paths.gameDir().toAbsolutePath().toString());
			env.put("PYTHONIOENCODING", "utf-8");
			env.put("PYTHONUTF8", "1");
			if (cfg.has("pythonpath")) env.put("PYTHONPATH", cfg.get("pythonpath").getAsString());
			env.keySet().removeIf(k -> k.startsWith("CLAUDE") || k.startsWith("ANTHROPIC"));
			File log = Paths.ensure(Paths.logs()).resolve("tools.log").toFile();
			pb.redirectErrorStream(true);
			pb.redirectOutput(ProcessBuilder.Redirect.appendTo(log));
			pb.start();
			Chat.toAll(u.server, Chat.soft(switch (what) {
				case "foto" -> "Fotoğraf hazırlanıyor…";
				case "harita" -> "Harita hazırlanıyor…";
				case "kaydet" -> "Kütüphaneye kaydediyorum…";
				case "panel" -> "Panel açılıyor…";
				default -> "Hazırlanıyor…";
			}));
		} catch (Exception e) {
			UstaMod.LOG.warn("Arac baslatilamadi", e);
			Chat.toAll(u.server, Chat.error("Yardımcı başlatılamadı: " + e.getMessage()));
		}
	}
}
