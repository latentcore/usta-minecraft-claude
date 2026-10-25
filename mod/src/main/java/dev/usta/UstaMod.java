package dev.usta;

import dev.usta.core.Usta;
import dev.usta.game.Chat;
import dev.usta.game.UstaCommands;
import dev.usta.engine.Job;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class UstaMod implements ModInitializer {
	public static final String MOD_ID = "usta";
	public static final Logger LOG = LoggerFactory.getLogger("Usta");

	public static String version() {
		return FabricLoader.getInstance().getModContainer(MOD_ID).map(c -> c.getMetadata().getVersion().getFriendlyString()).orElse("?");
	}

	@Override
	public void onInitialize() {
		CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) -> UstaCommands.register(dispatcher));
		ServerLifecycleEvents.SERVER_STARTED.register(Usta::start);
		ServerLifecycleEvents.SERVER_STOPPING.register(server -> Usta.stop());
		ServerTickEvents.END_SERVER_TICK.register(server -> {
			Usta u = Usta.get();
			if (u != null && u.server == server) u.tick();
		});
		ServerPlayConnectionEvents.JOIN.register((handler, sender, server) -> {
			Usta u = Usta.get();
			if (u == null || u.server != server) return;
			Job a = u.jobs.active();
			if (a != null && a.bar != null) a.bar.addPlayer(handler.getPlayer());
			server.execute(() -> handler.getPlayer().sendSystemMessage(Chat.soft("Usta hazır. Örnek: /claude önüme modern bir ev yap · yardım: /usta")));
		});
		LOG.info("Usta {} yuklendi", version());
	}
}
