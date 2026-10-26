package dev.usta.test;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.gametest.v1.context.TestSingleplayerContext;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;

/**
 * Senaryo testi (yalniz -Dusta.scenario=... ile): gercek istemci + entegre sunucu ile dunya acar, dis surucunun
 * scenario/commands/ klasorune yazdigi komutlari oyuncu olarak gonderir, gelen sohbet satirlarini zaman damgasiyla
 * scenario/chat.log'a yazar. scenario/done olusunca ya da sure bitince kapanir.
 */
@SuppressWarnings("UnstableApiUsage")
public class ScenarioClientGameTest implements FabricClientGameTest {
	private static volatile Path chatLog;
	private static boolean registered;

	@Override
	public void runTest(ClientGameTestContext context) {
		String scenario = System.getProperty("usta.scenario", "");
		if (scenario.isEmpty()) return;
		int minutes = Integer.getInteger("usta.scenarioMinutes", 10);
		String seed = System.getProperty("usta.seed", "");
		Path dir = FabricLoader.getInstance().getGameDir().resolve("scenario");
		try {
			Files.createDirectories(dir.resolve("commands"));
			for (String n : List.of("ready.json", "done", "chat.log")) Files.deleteIfExists(dir.resolve(n));
			try (Stream<Path> s = Files.list(dir.resolve("commands"))) {
				for (Path p : s.toList()) Files.deleteIfExists(p);
			}
		} catch (IOException e) {
			throw new RuntimeException(e);
		}
		chatLog = dir.resolve("chat.log");
		if (!registered) {
			registered = true;
			ClientReceiveMessageEvents.GAME.register((msg, overlay) -> {
				if (overlay) return;
				log(msg.getString());
			});
			// istemciye gelen sesler (ses kapaliyken de: dinleyici sessizlik kontrolunden once cagrilir); yalniz test edilenler
			context.runOnClient(mc -> mc.getSoundManager().addListener((sound, events, range) -> {
				String id = String.valueOf(sound.getIdentifier());
				for (String k : List.of("explode", "explosion", "note_block", "door", "button", "pressure_plate", "lever", "piston", "bell")) {
					if (id.contains(k)) {
						log("[ses] " + id);
						return;
					}
				}
			}));
		}
		var builder = context.worldBuilder();
		if (!seed.isEmpty()) {
			builder = builder.setUseConsistentSettings(false).adjustSettings(s -> {
				s.setSeed(seed);
				s.setAllowCommands(true);
			});
		}
		try (TestSingleplayerContext sp = builder.create()) {
			sp.getServer().runCommand("gamerule spawn_mobs false");        // 26.3 kural adlari (snake_case)
			sp.getServer().runCommand("time set 6000");
			sp.getServer().runCommand("gamerule advance_time false");
			sp.getServer().runCommand("gamerule advance_weather false");
			sp.getServer().runCommand("weather clear 999999");
			context.waitTicks(40);
			Files.writeString(dir.resolve("ready.json"), "{\"scenario\":\"" + scenario + "\",\"t\":" + System.currentTimeMillis() + "}", StandardCharsets.UTF_8);
			long deadline = System.currentTimeMillis() + minutes * 60_000L;
			List<String> done = new ArrayList<>();
			while (System.currentTimeMillis() < deadline && !Files.exists(dir.resolve("done"))) {
				List<Path> cmds;
				try (Stream<Path> s = Files.list(dir.resolve("commands"))) {
					cmds = s.filter(p -> p.toString().endsWith(".txt")).sorted().toList();
				}
				for (Path p : cmds) {
					String name = p.getFileName().toString();
					if (done.contains(name)) continue;
					done.add(name);
					String cmd = Files.readString(p, StandardCharsets.UTF_8).strip();
					log(">> " + cmd);
					if (cmd.startsWith("/")) cmd = cmd.substring(1);
					String fc = cmd;
					if (fc.startsWith("server ")) {
						sp.getServer().runCommand(fc.substring(7));
					} else if (fc.startsWith("client:")) {
						client(context, fc.substring(7).trim());
					} else {
						context.runOnClient(mc -> mc.player.connection.sendCommand(fc));
					}
				}
				context.waitTicks(5);
			}
		} catch (IOException e) {
			throw new RuntimeException(e);
		}
	}

	/** client:particles -> parcacik sayisi; client:render N -> gorus mesafesi (parca); client:use x y z [yuz] -> oyuncu o bloga sag tiklar (dugme, kol, kapi). */
	private static void client(ClientGameTestContext context, String cmd) {
		String[] a = cmd.split("\\s+");
		if (a[0].equals("particles")) {
			context.runOnClient(mc -> log("[parcacik] " + mc.particleEngine.countParticles()));
		} else if (a[0].equals("render") && a.length >= 2) {
			int n = Integer.parseInt(a[1]);
			context.runOnClient(mc -> {
				mc.options.renderDistance().set(n);
				log("[gorus] " + mc.options.renderDistance().get());
			});
		} else if (a[0].equals("use") && a.length >= 4) {
			net.minecraft.core.BlockPos pos = new net.minecraft.core.BlockPos(Integer.parseInt(a[1]), Integer.parseInt(a[2]), Integer.parseInt(a[3]));
			net.minecraft.core.Direction face = a.length >= 5 ? net.minecraft.core.Direction.byName(a[4]) : net.minecraft.core.Direction.UP;
			net.minecraft.core.Direction f = face == null ? net.minecraft.core.Direction.UP : face;
			context.runOnClient(mc -> {
				var hit = new net.minecraft.world.phys.BlockHitResult(net.minecraft.world.phys.Vec3.atCenterOf(pos), f, pos, false);
				var r = mc.gameMode.useItemOn(mc.player, net.minecraft.world.InteractionHand.MAIN_HAND, hit);
				log("[kullan] " + pos.toShortString() + " -> " + r);
			});
		} else {
			log("[client] bilinmeyen: " + cmd);
		}
	}

	private static synchronized void log(String s) {
		Path f = chatLog;
		if (f == null) return;
		try {
			Files.writeString(f, System.currentTimeMillis() + "\t" + s.replace('\n', ' ') + "\n", StandardCharsets.UTF_8,
				StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (IOException ignored) {
		}
	}

	@SuppressWarnings("unused")
	private static Minecraft mc() {
		return Minecraft.getInstance();
	}
}
