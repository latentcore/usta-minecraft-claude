package dev.usta.core;

import com.google.gson.JsonObject;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;

/** Istemci tarafina (oyuncu ekrani, renk tablosu, pencere durumu) erisim; istemci yoksa null. */
public final class ClientHook {
	private ClientHook() {}

	public interface Bridge {
		/** Oyuncunun gordugu karenin ekran goruntusu. */
		CompletableFuture<JsonObject> screenshot(Path out, int maxWidth);

		/** Pencere gorunur mu, kucultulmus mu, odakta mi, FPS, acik ekran. */
		JsonObject state();

		/** Doku renk tablosunu (yoksa) cikarir; yolunu dondurur. */
		CompletableFuture<JsonObject> colors(Path out);
	}

	public static volatile Bridge bridge;
}
