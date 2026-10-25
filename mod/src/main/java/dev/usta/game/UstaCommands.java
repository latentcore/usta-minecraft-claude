package dev.usta.game;

import com.google.gson.JsonObject;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.DoubleArgumentType;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.builder.LiteralArgumentBuilder;
import com.mojang.brigadier.context.CommandContext;
import dev.usta.core.Usta;
import dev.usta.engine.Job;
import dev.usta.world.Protection;
import java.util.List;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;

/**
 * Oyun ici komutlar: /claude <istek>, /usta <alt komut|istek>, /ai (Ingilizce takma ad). Turkce ve ASCII yazimlar birlikte (U5).
 */
public final class UstaCommands {
	private UstaCommands() {}

	public static void register(CommandDispatcher<CommandSourceStack> d) {
		d.register(Commands.literal("claude")
			.executes(UstaCommands::help)
			.then(Commands.argument("istek", StringArgumentType.greedyString()).executes(c -> request(c, StringArgumentType.getString(c, "istek")))));
		d.register(tree("usta"));
		d.register(tree("ai"));
	}

	private static LiteralArgumentBuilder<CommandSourceStack> tree(String root) {
		LiteralArgumentBuilder<CommandSourceStack> t = Commands.literal(root).executes(UstaCommands::help);
		for (String a : List.of("yardim", "yardım", "help")) t.then(Commands.literal(a).executes(UstaCommands::help));
		for (String a : List.of("geri", "undo")) {
			t.then(Commands.literal(a).executes(c -> undo(c, null, false))
				.then(Commands.argument("id", StringArgumentType.word()).executes(c -> undo(c, StringArgumentType.getString(c, "id"), false))));
		}
		for (String a : List.of("yinele", "redo")) {
			t.then(Commands.literal(a).executes(c -> undo(c, null, true))
				.then(Commands.argument("id", StringArgumentType.word()).executes(c -> undo(c, StringArgumentType.getString(c, "id"), true))));
		}
		for (String a : List.of("iptal", "cancel", "dur", "stop")) {
			t.then(Commands.literal(a).executes(c -> cancel(c, null))
				.then(Commands.argument("id", StringArgumentType.word()).executes(c -> cancel(c, StringArgumentType.getString(c, "id")))));
		}
		for (String a : List.of("duraklat", "pause")) t.then(Commands.literal(a).executes(c -> pause(c, true)));
		for (String a : List.of("surdur", "sürdür", "devam", "resume")) t.then(Commands.literal(a).executes(c -> pause(c, false)));
		for (String a : List.of("hiz", "hız", "speed", "sure", "süre")) {
			t.then(Commands.literal(a).then(Commands.argument("saniye", DoubleArgumentType.doubleArg(0, 3600)).executes(c -> speed(c, DoubleArgumentType.getDouble(c, "saniye")))));
		}
		for (String a : List.of("aninda", "anında", "instant")) t.then(Commands.literal(a).executes(c -> speed(c, 0)));
		for (String a : List.of("kip", "mode")) {
			t.then(Commands.literal(a).then(Commands.argument("kip", StringArgumentType.word()).executes(c -> mode(c, StringArgumentType.getString(c, "kip")))));
		}
		for (String a : List.of("onayla", "confirm")) {
			t.then(Commands.literal(a).then(Commands.argument("id", StringArgumentType.word()).executes(c -> confirm(c, StringArgumentType.getString(c, "id")))));
		}
		for (String a : List.of("etkinlestir", "etkinleştir", "activate")) t.then(Commands.literal(a).executes(UstaCommands::activate));
		for (String a : List.of("vazgec", "vazgeç")) t.then(Commands.literal(a).executes(c -> {
			c.getSource().sendSystemMessage(Chat.soft("Tamam, bu dünyada Usta kullanılmayacak (istediğinde /usta etkinlestir)."));
			return 1;
		}));
		for (String a : List.of("durum", "status")) t.then(Commands.literal(a).executes(UstaCommands::status));
		for (String a : List.of("yeni", "new")) t.then(Commands.literal(a).executes(c -> {
			Usta u = Usta.get();
			if (u == null) return 0;
			u.agent.resetConversation();
			c.getSource().sendSystemMessage(Chat.soft("Yeni konuşma başladı; Claude önceki istekleri artık hatırlamayacak."));
			return 1;
		}));
		for (String a : List.of("sec", "seç", "select")) {
			t.then(Commands.literal(a).then(Commands.argument("kose", StringArgumentType.word()).executes(c -> select(c, StringArgumentType.getString(c, "kose")))));
		}
		for (String a : List.of("koru", "protect")) {
			t.then(Commands.literal(a).then(Commands.argument("ad", StringArgumentType.word()).executes(c -> protect(c, StringArgumentType.getString(c, "ad"), true))));
		}
		for (String a : List.of("korumayi-kaldir", "unprotect")) {
			t.then(Commands.literal(a).then(Commands.argument("ad", StringArgumentType.word()).executes(c -> protect(c, StringArgumentType.getString(c, "ad"), false))));
		}
		for (String a : List.of("foto", "fotograf", "fotoğraf", "photo")) {
			t.then(Commands.literal(a).executes(c -> tool(c, "foto", null))
				.then(Commands.argument("id", StringArgumentType.word()).executes(c -> tool(c, "foto", StringArgumentType.getString(c, "id")))));
		}
		for (String a : List.of("harita", "map")) t.then(Commands.literal(a).executes(c -> tool(c, "harita", null)));
		for (String a : List.of("kaydet", "save")) {
			t.then(Commands.literal(a).then(Commands.argument("id", StringArgumentType.word()).executes(c -> tool(c, "kaydet", StringArgumentType.getString(c, "id")))));
		}
		for (String a : List.of("panel")) t.then(Commands.literal(a).executes(c -> tool(c, "panel", null)));
		for (String a : List.of("kutuphane", "kütüphane", "library")) t.then(Commands.literal(a).executes(c -> tool(c, "kutuphane", null)));
		for (String a : List.of("patlama", "explosion")) {
			LiteralArgumentBuilder<CommandSourceStack> pt = Commands.literal(a).executes(c -> explosion(c, null, -1));
			for (String on : List.of("hizli", "hızlı", "fast", "ac", "aç", "on")) pt.then(Commands.literal(on).executes(c -> explosion(c, true, -1)));
			for (String off : List.of("normal", "vanilla", "kapat", "off")) pt.then(Commands.literal(off).executes(c -> explosion(c, false, -1)));
			for (String th : List.of("esik", "eşik", "threshold")) {
				pt.then(Commands.literal(th).then(Commands.argument("sayi", IntegerArgumentType.integer(8, 1_000_000))
					.executes(c -> explosion(c, null, IntegerArgumentType.getInteger(c, "sayi")))));
			}
			t.then(pt);
		}
		for (String a : List.of("ac", "aç", "open")) {
			t.then(Commands.literal(a).then(Commands.argument("dosya", StringArgumentType.greedyString()).executes(c -> open(c, StringArgumentType.getString(c, "dosya")))));
		}
		t.then(Commands.argument("istek", StringArgumentType.greedyString()).executes(c -> request(c, StringArgumentType.getString(c, "istek"))));
		return t;
	}

	private static Usta usta(CommandContext<CommandSourceStack> c) {
		Usta u = Usta.get();
		if (u == null) {
			c.getSource().sendSystemMessage(Chat.error("Usta yalnız tek oyunculu dünyalarda çalışır."));
		} else if (!u.aiEnabled) {
			c.getSource().sendSystemMessage(Chat.error(u.disabledReason == null ? "Usta kapalı." : u.disabledReason));
			return null;
		}
		return u;
	}

	private static int help(CommandContext<CommandSourceStack> c) {
		CommandSourceStack s = c.getSource();
		s.sendSystemMessage(Chat.line("Claude ile inşa: /claude <ne istediğin>"));
		s.sendSystemMessage(Component.literal("  Örnek: /claude önüme devasa modern güzel bir ev yap").withStyle(st -> st.withColor(Chat.SOFT)));
		s.sendSystemMessage(Component.literal("  Örnek: /claude çatıyı daha sivri yap · /claude akşam olsun").withStyle(st -> st.withColor(Chat.SOFT)));
		s.sendSystemMessage(Component.literal("  /usta geri · yinele · iptal · duraklat · sürdür · hız <sn> · anında · kip <izle|anında|sinematik>").withStyle(st -> st.withColor(Chat.SOFT)));
		s.sendSystemMessage(Component.literal("  /usta foto · harita · seç 1|2 · koru <ad> · kaydet <iş> · kütüphane · panel · durum · yeni · patlama hızlı|normal").withStyle(st -> st.withColor(Chat.SOFT)));
		s.sendSystemMessage(Component.literal("  İngilizce: /ai undo · redo · cancel · pause · resume · speed · photo · map · status").withStyle(st -> st.withColor(Chat.SOFT)));
		return 1;
	}

	private static int request(CommandContext<CommandSourceStack> c, String text) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (text.isBlank()) return help(c);
		ServerPlayer p = c.getSource().getPlayer();
		u.agent.submit(text, "oyun", p);
		return 1;
	}

	private static int undo(CommandContext<CommandSourceStack> c, String id, boolean redo) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (!u.activated()) {
			u.promptActivation();
			return 0;
		}
		JsonObject r = u.api.undoRedo(redo, id, false, "oyun");
		if (!r.get("ok").getAsBoolean()) {
			c.getSource().sendSystemMessage(Chat.warn(r.has("message") ? r.get("message").getAsString() : "Yapılamadı"));
			return 0;
		}
		if (r.has("state") && "DONE".equals(r.get("state").getAsString())) return 1;
		c.getSource().sendSystemMessage(Chat.soft(redo ? "Yineliyorum…" : "Geri alıyorum…"));
		return 1;
	}

	private static int cancel(CommandContext<CommandSourceStack> c, String id) {
		Usta u = usta(c);
		if (u == null) return 0;
		boolean any = false;
		if (id != null) {
			any = u.jobs.cancel(id) || u.agent.cancel(id, null);
		} else {
			if (u.agent.active() != null) any = u.agent.cancel(null, null);
			Job a = u.jobs.active();
			if (a != null) any |= u.jobs.cancel(a.id);
		}
		if (!any) c.getSource().sendSystemMessage(Chat.soft("İptal edilecek bir şey yok."));
		return 1;
	}

	private static int pause(CommandContext<CommandSourceStack> c, boolean pause) {
		Usta u = usta(c);
		if (u == null) return 0;
		Job a = u.jobs.active();
		if (a == null) {
			c.getSource().sendSystemMessage(Chat.soft("Süren bir inşa yok."));
			return 0;
		}
		u.jobs.pause(a.id, pause);
		c.getSource().sendSystemMessage(Chat.soft(pause ? "Duraklattım." : "Sürdürüyorum."));
		return 1;
	}

	private static int speed(CommandContext<CommandSourceStack> c, double seconds) {
		Usta u = usta(c);
		if (u == null) return 0;
		Job a = u.jobs.active();
		if (a == null) {
			c.getSource().sendSystemMessage(Chat.soft("Süren bir inşa yok; varsayılan kip için /usta kip <izle|anında|sinematik>."));
			return 0;
		}
		u.jobs.setSeconds(a.id, seconds);
		c.getSource().sendSystemMessage(Chat.soft(seconds <= 0 ? "Anında bitiriyorum." : "Kalan kısmı ~" + (int) seconds + " saniyeye yaydım."));
		return 1;
	}

	private static int mode(CommandContext<CommandSourceStack> c, String m) {
		Usta u = usta(c);
		if (u == null) return 0;
		Job.Mode mode = Job.Mode.parse(m, null);
		if (mode == null) {
			c.getSource().sendSystemMessage(Chat.warn("Kip: izle, anında ya da sinematik"));
			return 0;
		}
		u.settings.defaultMode = mode.name().toLowerCase();
		u.settings.save();
		c.getSource().sendSystemMessage(Chat.soft("Varsayılan kip: " + switch (mode) {
			case INSTANT -> "anında";
			case CINEMATIC -> "sinematik";
			case WATCH -> "izlenebilir hızlı";
		}));
		return 1;
	}

	/** /usta patlama [hızlı|normal|eşik N]: buyuk TNT kumelerinin toplu (kasmasiz) patlamasi. */
	private static int explosion(CommandContext<CommandSourceStack> c, Boolean on, int threshold) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (on != null) u.settings.massExplosion = on;
		if (threshold > 0) u.settings.massExplosionThreshold = threshold;
		if (on != null || threshold > 0) u.settings.save();
		c.getSource().sendSystemMessage(Chat.soft(u.settings.massExplosion
			? "Hızlı patlama açık: " + u.settings.massExplosionThreshold + " ve üstü bitişik TNT tek seferde, kasmadan patlar (geri al: /usta geri). Vanilla için: /usta patlama normal"
			: "Hızlı patlama kapalı: TNT'ler vanilla gibi tek tek patlar (büyük kümede oyun donabilir). Açmak için: /usta patlama hızlı"));
		return 1;
	}

	private static int confirm(CommandContext<CommandSourceStack> c, String id) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (u.jobs.confirm(id)) {
			c.getSource().sendSystemMessage(Chat.soft("Onaylandı; kuruyorum."));
			return 1;
		}
		c.getSource().sendSystemMessage(Chat.warn("Onay bekleyen böyle bir iş yok."));
		return 0;
	}

	private static int activate(CommandContext<CommandSourceStack> c) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (u.activated()) {
			c.getSource().sendSystemMessage(Chat.soft("Usta bu dünyada zaten açık."));
			u.agent.onActivated();
			return 1;
		}
		u.activate(u.agent::onActivated);
		return 1;
	}

	private static int status(CommandContext<CommandSourceStack> c) {
		Usta u = usta(c);
		if (u == null) return 0;
		Job a = u.jobs.active();
		String job = a == null ? "inşa yok" : a.label + " %" + (int) (a.progress() * 100) + " (" + a.state + ")";
		var ar = u.agent.active();
		String ag = ar == null ? "istek yok" : "istek sürüyor: " + ar.text;
		c.getSource().sendSystemMessage(Chat.line("Durum: " + job + " · " + ag + " · sırada " + u.jobs.queued().size() + " iş · geçmiş " + u.history.all().size()));
		return 1;
	}

	private static int select(CommandContext<CommandSourceStack> c, String which) {
		Usta u = usta(c);
		if (u == null) return 0;
		ServerPlayer p = c.getSource().getPlayer();
		if (p == null) return 0;
		BlockPos pos;
		HitResult hit = p.pick(96.0, 1.0f, false);
		if (hit instanceof BlockHitResult bh && hit.getType() == HitResult.Type.BLOCK) pos = bh.getBlockPos();
		else pos = p.blockPosition();
		if (which.equals("temizle") || which.equals("clear")) {
			Selection.clear(u);
			c.getSource().sendSystemMessage(Chat.soft("Seçim temizlendi."));
			return 1;
		}
		int k = which.equals("2") ? 2 : 1;
		Selection.set(u, k, pos, p.level().dimension().identifier().toString());
		c.getSource().sendSystemMessage(Chat.soft("Köşe " + k + ": " + pos.getX() + " " + pos.getY() + " " + pos.getZ()));
		Selection.show(u, p.level());
		return 1;
	}

	private static int protect(CommandContext<CommandSourceStack> c, String name, boolean add) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (!add) {
			boolean ok = u.protection.remove(name);
			c.getSource().sendSystemMessage(ok ? Chat.soft("Koruma kaldırıldı: " + name) : Chat.warn("Böyle bir korunan bölge yok."));
			return ok ? 1 : 0;
		}
		int[] box = Selection.box(u);
		if (box == null) {
			c.getSource().sendSystemMessage(Chat.warn("Önce iki köşe seç: /usta seç 1 ve /usta seç 2 (baktığın blok)."));
			return 0;
		}
		Protection.Region r = new Protection.Region();
		r.name = name;
		r.dim = Selection.dim(u);
		r.x0 = box[0];
		r.y0 = box[1];
		r.z0 = box[2];
		r.x1 = box[3];
		r.y1 = box[4];
		r.z1 = box[5];
		u.protection.add(r);
		c.getSource().sendSystemMessage(Chat.soft("Korunan bölge eklendi: " + name + " (Usta buraya hiçbir şey yazmaz)."));
		return 1;
	}

	/** Yalniz Usta'nin kendi ciktilarini (ekran goruntusu/harita/disari aktarma) isletim sisteminde acar. */
	private static int open(CommandContext<CommandSourceStack> c, String name) {
		Usta u = usta(c);
		if (u == null) return 0;
		if (name.contains("/") || name.contains("\\") || name.contains("..")) {
			c.getSource().sendSystemMessage(Chat.warn("Geçersiz dosya adı."));
			return 0;
		}
		for (java.nio.file.Path dir : new java.nio.file.Path[]{dev.usta.core.Paths.gameDir().resolve("screenshots").resolve("usta"),
			dev.usta.core.Paths.root().resolve("disari")}) {
			java.nio.file.Path f = dir.resolve(name);
			if (java.nio.file.Files.isRegularFile(f)) {
				try {
					new ProcessBuilder("explorer.exe", f.toAbsolutePath().toString()).start();
				} catch (java.io.IOException e) {
					c.getSource().sendSystemMessage(Chat.warn("Açılamadı: " + e.getMessage()));
				}
				return 1;
			}
		}
		c.getSource().sendSystemMessage(Chat.warn("Dosya bulunamadı: " + name));
		return 0;
	}

	/** Python araclari gerektiren komutlar: kopru yardimcisi calistirilir (foto, harita, kaydet, panel, kutuphane). */
	private static int tool(CommandContext<CommandSourceStack> c, String what, String arg) {
		Usta u = usta(c);
		if (u == null) return 0;
		ToolRunner.run(u, what, arg);
		return 1;
	}
}
