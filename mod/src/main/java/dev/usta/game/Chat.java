package dev.usta.game;

import java.util.List;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.HoverEvent;
import net.minecraft.network.chat.MutableComponent;
import net.minecraft.network.chat.Style;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;

/** Oyun ici mesajlar: kisa, renkli ama sade; tiklanabilir dugmeler (U5, U10). */
public final class Chat {
	private Chat() {}

	public static final int ACCENT = 0xE8A840; // altin-turuncu (mala)
	public static final int SOFT = 0xB8C4D0;

	public record Button(String label, String command, String hover, boolean suggest) {
		public static Button run(String label, String command, String hover) {
			return new Button(label, command, hover, false);
		}

		public static Button suggest(String label, String command, String hover) {
			return new Button(label, command, hover, true);
		}
	}

	public static MutableComponent prefix() {
		return Component.literal("[Usta] ").withStyle(Style.EMPTY.withColor(ACCENT).withBold(true));
	}

	public static MutableComponent line(String text) {
		return prefix().append(Component.literal(text).withStyle(Style.EMPTY.withColor(ChatFormatting.WHITE).withBold(false)));
	}

	public static MutableComponent soft(String text) {
		return prefix().append(Component.literal(text).withStyle(Style.EMPTY.withColor(SOFT).withBold(false)));
	}

	public static MutableComponent warn(String text) {
		return prefix().append(Component.literal(text).withStyle(Style.EMPTY.withColor(ChatFormatting.GOLD).withBold(false)));
	}

	public static MutableComponent error(String text) {
		return prefix().append(Component.literal(text).withStyle(Style.EMPTY.withColor(ChatFormatting.RED).withBold(false)));
	}

	public static MutableComponent withButtons(MutableComponent base, List<Button> buttons) {
		for (Button b : buttons) {
			base.append(Component.literal(" "));
			Style st = Style.EMPTY.withColor(ChatFormatting.AQUA).withBold(false).withUnderlined(false)
				.withClickEvent(b.suggest() ? new ClickEvent.SuggestCommand(b.command()) : new ClickEvent.RunCommand(b.command()));
			if (b.hover() != null && !b.hover().isEmpty()) {
				st = st.withHoverEvent(new HoverEvent.ShowText(Component.literal(b.hover())));
			}
			base.append(Component.literal("[" + b.label() + "]").withStyle(st));
		}
		return base;
	}

	public static void toAll(MinecraftServer server, Component msg) {
		for (ServerPlayer p : server.getPlayerList().getPlayers()) {
			p.sendSystemMessage(msg);
		}
	}

	public static void actionBar(MinecraftServer server, Component msg) {
		for (ServerPlayer p : server.getPlayerList().getPlayers()) {
			p.sendSystemMessage(msg, true);
		}
	}

	/** Bitis dugmeleri: [Geri al] [Fotograf] [Degistir] [Kaydet]. */
	public static List<Button> doneButtons(String jobId) {
		return List.of(
			Button.run("Geri al", "/usta geri " + jobId, "Bu yapıyı tamamen geri al"),
			Button.run("Fotoğraf", "/usta foto " + jobId, "En güzel açıdan fotoğraf çek"),
			Button.suggest("Değiştir", "/claude ", "Bu yapıda değişiklik iste (ör. çatıyı daha sivri yap)"),
			Button.run("Kaydet", "/usta kaydet " + jobId, "Kütüphaneye kaydet")
		);
	}
}
