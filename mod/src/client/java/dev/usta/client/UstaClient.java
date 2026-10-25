package dev.usta.client;

import com.google.gson.JsonObject;
import com.mojang.blaze3d.platform.NativeImage;
import dev.usta.UstaMod;
import dev.usta.core.ClientHook;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import net.fabricmc.api.ClientModInitializer;
import net.minecraft.client.Minecraft;
import net.minecraft.client.Screenshot;

public final class UstaClient implements ClientModInitializer {
	@Override
	public void onInitializeClient() {
		ClientHook.bridge = new Bridge();
		// renk tablosu yoksa oyun acildiktan sonra arka planda cikar (gorunteleyicinin gercek renkleri icin)
		net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents.CLIENT_STARTED.register(mc -> {
			Path f = dev.usta.core.Paths.cache().resolve("colors-" + dev.usta.compat.V.MC + ".json.gz");
			if (!Files.exists(f)) ColorTable.ensure(f);
		});
		UstaMod.LOG.info("Usta istemci tarafi yuklendi");
	}

	static final class Bridge implements ClientHook.Bridge {
		@Override
		public CompletableFuture<JsonObject> screenshot(Path out, int maxWidth) {
			CompletableFuture<JsonObject> f = new CompletableFuture<>();
			Minecraft mc = Minecraft.getInstance();
			mc.execute(() -> {
				try {
					JsonObject st = state();
					Screenshot.takeScreenshot(mc.gameRenderer.mainRenderTarget(), img -> {
						try (NativeImage image = img) {
							Files.createDirectories(out.getParent());
							int w = image.getWidth(), h = image.getHeight();
							if (maxWidth > 0 && w > maxWidth) {
								int nh = Math.max(1, h * maxWidth / w);
								try (NativeImage small = new NativeImage(maxWidth, nh, false)) {
									image.resizeSubRectTo(0, 0, w, h, small);
									small.writeToFile(out);
									w = maxWidth;
									h = nh;
								}
							} else {
								image.writeToFile(out);
							}
							JsonObject o = new JsonObject();
							o.addProperty("ok", true);
							o.addProperty("path", out.toAbsolutePath().toString());
							o.addProperty("width", w);
							o.addProperty("height", h);
							o.add("client", st);
							f.complete(o);
						} catch (Exception e) {
							f.completeExceptionally(e);
						}
					});
				} catch (Exception e) {
					f.completeExceptionally(e);
				}
			});
			return f;
		}

		@Override
		public JsonObject state() {
			Minecraft mc = Minecraft.getInstance();
			JsonObject o = new JsonObject();
			o.addProperty("fps", mc.getFps());
			o.addProperty("paused", mc.isPaused());
			o.addProperty("screen", mc.gui.screen() == null ? "" : mc.gui.screen().getClass().getSimpleName());
			o.addProperty("focused", mc.isWindowActive());
			o.addProperty("width", mc.getWindow().getWidth());
			o.addProperty("height", mc.getWindow().getHeight());
			return o;
		}

		@Override
		public CompletableFuture<JsonObject> colors(Path out) {
			return ColorTable.ensure(out);
		}
	}
}
