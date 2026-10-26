package dev.usta.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mojang.brigadier.exceptions.CommandSyntaxException;
import dev.usta.UstaMod;
import dev.usta.compat.V;
import dev.usta.core.Usta;
import dev.usta.game.Chat;
import dev.usta.world.Classify;
import dev.usta.world.EntityGuard;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.Registries;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerBossEvent;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.BossEvent;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;

/** Is kuyrugu ve tick butceli yerlestirme. Tum dunya degisiklikleri sunucu is parcaciginda yapilir. */
public final class JobManager {
	private final Usta u;
	private final Deque<Job> queue = new ArrayDeque<>();
	private final Map<String, Job> jobs = new ConcurrentHashMap<>();
	private volatile Job active;
	private final List<CompletableFuture<?>> loading = new ArrayList<>();
	private int effectTick;

	public JobManager(Usta u) {
		this.u = u;
	}

	public static final class PlanException extends Exception {
		public final List<String> problems;

		public PlanException(String msg, List<String> problems) {
			super(msg);
			this.problems = problems;
		}
	}

	public Job get(String id) {
		return jobs.get(id);
	}

	public Job active() {
		return active;
	}

	public synchronized List<Job> queued() {
		return new ArrayList<>(queue);
	}

	/** Bu gecmis kaydi icin kuyrukta bekleyen ya da suren bir geri alma/yineleme var mi (ayni is iki kez geri alinmasin). */
	public synchronized boolean pendingFor(String entryId) {
		Job a = active;
		if (a != null && !a.finished() && a.kind != Job.Kind.BUILD && entryId.equals(a.refJob)) return true;
		for (Job q : queue) if (q.kind != Job.Kind.BUILD && entryId.equals(q.refJob)) return true;
		return false;
	}

	static String newId() {
		return Long.toString(System.currentTimeMillis(), 36) + "-" + UUID.randomUUID().toString().substring(0, 6);
	}

	// ------------------------------------------------------------------ plan -> is
	/** Plani cozer, dogrular, siralar. Herhangi bir is parcaciginda calisabilir. */
	public Job fromPlan(Plan plan, ServerLevel level, Job.Mode mode, double seconds, String label, String source,
						boolean allowModify, boolean allowDangerous) throws PlanException {
		HolderLookup<Block> lookup = V.blockLookup(u.server);
		int pn = plan.palette.length;
		BlockState[] pal = new BlockState[pn];
		boolean[] exact = new boolean[pn];
		int[] flags = new int[pn];
		List<String> problems = new ArrayList<>();
		pal[1] = Blocks.AIR.defaultBlockState();
		exact[1] = true;
		flags[1] = Physics.flags(pal[1]);
		for (int i = 2; i < pn; i++) {
			String s = plan.palette[i];
			boolean ex = s.startsWith("!");
			if (ex) s = s.substring(1);
			try {
				pal[i] = V.parseState(lookup, s).blockState();
				exact[i] = ex;
				flags[i] = Physics.flags(pal[i]);
			} catch (CommandSyntaxException e) {
				problems.add("bilinmeyen blok/özellik: '" + s + "' (" + e.getMessage() + ")");
			}
		}
		if (!problems.isEmpty()) throw new PlanException("Plan geçersiz: sürümde olmayan blok ya da özellik", problems);
		int minY = level.getMinY();
		int maxY = level.getMaxY();
		if (plan.oy < minY || plan.oy + plan.sy - 1 > maxY) {
			throw new PlanException("Plan dünya yüksekliği dışına taşıyor (" + minY + ".." + maxY + ")", List.of());
		}
		// kullanilan paletler
		int[] cells = plan.cells;
		boolean[] used = new boolean[pn];
		int n = 0;
		for (int c : cells) {
			if (c != 0) {
				used[c] = true;
				n++;
			}
		}
		if (!allowDangerous) {
			for (int i = 2; i < pn; i++) {
				if (used[i] && (flags[i] & Physics.DANGEROUS) != 0) problems.add("tehlikeli blok: " + plan.palette[i]);
			}
			if (!problems.isEmpty()) throw new PlanException("Planda TNT/lav/ateş var; yalnız açıkça istenirse kurulur (allow_dangerous)", problems);
		}
		long[] keys = new long[n];
		int k = 0;
		int sx = plan.sx, sz = plan.sz;
		double cx = (sx - 1) / 2.0, cz = (sz - 1) / 2.0;
		for (int c = 0; c < cells.length; c++) {
			int v = cells[c];
			if (v == 0) continue;
			int x = c % sx;
			int z = (c / sx) % sz;
			int y = c / (sx * sz);
			int ph = Physics.phase(pal[v], flags[v]);
			int ykey = ph == 0 ? 4095 - Math.min(y, 4095) : Math.min(y, 4095);
			double dx = x - cx, dz = z - cz;
			int d = (int) Math.min(65535, Math.sqrt(dx * dx + dz * dz) * 4);
			keys[k++] = ((long) ph << 60) | ((long) ykey << 48) | ((long) d << 32) | (c & 0xFFFFFFFFL);
		}
		Arrays.sort(keys);
		String id = newId();
		Job j = new Job(id, Job.Kind.BUILD, label == null || label.isBlank() ? "yapı" : label, level, plan.ox, plan.oy, plan.oz, plan.sx, plan.sy, plan.sz, n);
		j.idx = new int[n];
		j.target = new BlockState[n];
		j.settle = new boolean[n];
		for (int i = 0; i < n; i++) {
			int c = (int) (keys[i] & 0xFFFFFFFFL);
			int v = cells[c];
			j.idx[i] = c;
			j.target[i] = pal[v];
			j.settle[i] = !exact[v] && (flags[v] & Physics.CONNECT) != 0;
		}
		for (Plan.BlockEntitySpec be : plan.blockEntities) {
			if (be.x() < 0 || be.y() < 0 || be.z() < 0 || be.x() >= sx || be.y() >= plan.sy || be.z() >= sz) {
				problems.add("blok varlığı plan dışında: " + be.x() + "," + be.y() + "," + be.z());
				continue;
			}
			int c = plan.index(be.x(), be.y(), be.z());
			int v = cells[c];
			if (v < 2 || !pal[v].hasBlockEntity()) {
				problems.add("blok varlığı verisi olan hücrede uygun blok yok: " + be.x() + "," + be.y() + "," + be.z());
				continue;
			}
			try {
				j.targetBE.put(c, V.parseSnbt(be.snbt()));
			} catch (CommandSyntaxException e) {
				problems.add("SNBT hatalı (" + be.x() + "," + be.y() + "," + be.z() + "): " + e.getMessage());
			}
		}
		for (Plan.EntitySpec e : plan.entities) {
			try {
				V.parseSnbt(e.snbt());
			} catch (CommandSyntaxException ex) {
				problems.add("varlık SNBT hatalı: " + e.type());
				continue;
			}
			if (!e.type().equals("minecraft:painting") && !e.type().equals("minecraft:item_frame") && !e.type().equals("minecraft:glow_item_frame")
				&& !e.type().equals("minecraft:armor_stand") && !(allowModify && e.type().startsWith("minecraft:"))) {
				problems.add("varlık türüne izin yok: " + e.type() + " (canlılar yalnız açık istekle)");
				continue;
			}
			j.spawn.add(new Plan.EntitySpec(e.type(), plan.ox + e.x(), plan.oy + e.y(), plan.oz + e.z(), e.yaw(), e.pitch(), e.snbt()));
		}
		if (!problems.isEmpty()) throw new PlanException("Plan geçersiz", problems);
		j.mode = mode;
		j.seconds = seconds > 0 ? seconds : autoSeconds(mode, n);
		j.source = source;
		j.allowModify = allowModify;
		j.allowDangerous = allowDangerous;
		j.meta = plan.meta == null ? new JsonObject() : plan.meta;
		j.planCells = cells;
		j.planPalette = pal;
		return j;
	}

	public static double autoSeconds(Job.Mode mode, int n) {
		return switch (mode) {
			case INSTANT -> 0;
			case CINEMATIC -> Math.max(30, Math.min(240, n / 120.0));
			case WATCH -> Math.max(8, Math.min(60, 6 + n / 900.0));
		};
	}

	// ------------------------------------------------------------------ kuyruk
	/** Sunucu is parcaciginda cagrilmali. */
	public void enqueue(Job j) {
		jobs.put(j.id, j);
		synchronized (this) {
			queue.addLast(j);
		}
		j.saveFuture = JobStore.saveAsync(u.worldDir, j);
		JobStore.journal(u.worldDir, j, false);
		u.events.publish("job_queued", summary(j));
	}

	/** Toplu patlama gibi bekletilmemesi gereken isler: kuyrugun basina (suren is bitince ilk o). */
	public void enqueueFront(Job j) {
		jobs.put(j.id, j);
		synchronized (this) {
			queue.addFirst(j);
		}
		j.saveFuture = JobStore.saveAsync(u.worldDir, j);
		JobStore.journal(u.worldDir, j, false);
		u.events.publish("job_queued", summary(j));
	}

	public boolean cancel(String id) {
		Job j = jobs.get(id);
		if (j == null || j.finished()) return false;
		j.cancelRequested = true;
		return true;
	}

	public boolean pause(String id, boolean pause) {
		Job j = jobs.get(id);
		if (j == null || j.finished()) return false;
		j.pauseRequested = pause;
		return true;
	}

	public boolean confirm(String id) {
		Job j = jobs.get(id);
		if (j == null || j.state != Job.State.AWAITING_CONFIRM) return false;
		j.confirmed = true;
		return true;
	}

	public boolean setSeconds(String id, double seconds) {
		Job j = jobs.get(id);
		if (j == null || j.finished()) return false;
		if (seconds <= 0) {
			j.mode = Job.Mode.INSTANT;
		} else {
			// kalan isi yeni sureye yay: gecen tikleri yeniden olcekle
			double frac = j.n == 0 ? 1 : j.cursor / (double) j.n;
			j.seconds = seconds;
			j.ticksRunning = (long) (frac * seconds * 20);
			if (j.mode == Job.Mode.INSTANT) j.mode = Job.Mode.WATCH;
		}
		return true;
	}

	/** END_SERVER_TICK. */
	public void tick() {
		Job j = active;
		if (j == null) {
			synchronized (this) {
				j = queue.pollFirst();
			}
			if (j == null) return;
			active = j;
			startLoading(j);
		}
		long t0 = System.nanoTime();
		MassExplosion.suppress++; // kendi yerlestirmemiz TNT atesletmez (geri alma, krater kenari)
		try {
			step(j);
		} catch (Throwable t) {
			UstaMod.LOG.error("Is hatasi: {}", j.id, t);
			j.message = "iç hata: " + t;
			finish(j, Job.State.FAILED);
		} finally {
			MassExplosion.suppress--;
		}
		long dt = System.nanoTime() - t0;
		if (j.state == Job.State.RUNNING || j.state == Job.State.SETTLING) {
			j.sumTickNanos += dt;
			j.tickSamples++;
			if (dt > j.maxTickNanos) j.maxTickNanos = dt;
		}
	}

	private void startLoading(Job j) {
		j.state = Job.State.LOADING;
		j.startedAt = System.currentTimeMillis();
		int cx0 = (j.ox >> 4) - 1, cz0 = (j.oz >> 4) - 1;
		int cx1 = ((j.ox + j.sx - 1) >> 4) + 1, cz1 = ((j.oz + j.sz - 1) >> 4) + 1;
		List<Long> keys = new ArrayList<>();
		loading.clear();
		for (int cx = cx0; cx <= cx1; cx++) {
			for (int cz = cz0; cz <= cz1; cz++) {
				ChunkPos cp = new ChunkPos(cx, cz);
				loading.add(j.level.getChunkSource().addTicketAndLoadWithRadius(V.ticket(), cp, 0));
				keys.add(cp.pack());
			}
		}
		j.chunkKeys = keys.stream().mapToLong(Long::longValue).toArray();
		u.events.publish("job_loading", summary(j));
	}

	private void releaseTickets(Job j) {
		for (long key : j.chunkKeys) {
			j.level.getChunkSource().removeTicketWithRadius(V.ticket(), ChunkPos.unpack(key), 0);
		}
		j.chunkKeys = new long[0];
	}

	private void step(Job j) {
		if (j.cancelRequested && j.state != Job.State.DONE) {
			finish(j, Job.State.CANCELLED);
			return;
		}
		switch (j.state) {
			case LOADING -> {
				for (CompletableFuture<?> f : loading) if (!f.isDone()) return;
				// varliklar chunk'tan ayri ve gecikmeli yuklenir: koruma ve geri alma icin hepsi yuklenmeli
				if (!j.entitiesWaitStarted) {
					j.entitiesWaitStarted = true;
					j.entitiesWaitUntil = System.currentTimeMillis() + 8000;
				}
				boolean all = true;
				for (long key : j.chunkKeys) {
					if (!j.level.areEntitiesLoaded(key)) {
						all = false;
						break;
					}
				}
				if (!all && System.currentTimeMillis() < j.entitiesWaitUntil) return;
				if (!all) UstaMod.LOG.warn("Is {}: bazi chunk varliklari 8 sn icinde yuklenmedi", j.id);
				loading.clear();
				if (j.before != null && j.kind != Job.Kind.UNDO) {
					// cokmeden ya da kapanistan donus: on-kopya zaten var
					beginRunning(j);
				} else if (j.kind == Job.Kind.UNDO) {
					beginRunning(j);
				} else {
					j.state = Job.State.CAPTURING;
					j.before = new BlockState[j.n];
					j.captureCursor = 0;
				}
			}
			case CAPTURING -> {
				if (j.analyzing) analyze(j, System.nanoTime(), 30_000_000L);
				else capture(j);
			}
			case SAVING -> {
				if (j.saveFuture == null || j.saveFuture.isDone()) afterSaved(j);
			}
			case AWAITING_CONFIRM -> {
				if (j.confirmed) {
					beginRunning(j);
				} else if (++effectTick % 20 == 0) {
					outline(j);
				}
			}
			case RUNNING -> {
				if (j.pauseRequested) {
					if (j.bar != null) j.bar.setName(Component.literal("Usta · " + j.label + " · duraklatıldı"));
					return;
				}
				place(j);
			}
			case SETTLING -> settle(j);
			case ENTITIES -> {
				spawnEntities(j);
				finish(j, Job.State.DONE);
			}
			default -> {
			}
		}
	}

	private BlockPos.MutableBlockPos pos(Job j, int cell, BlockPos.MutableBlockPos p) {
		return p.set(j.ox + cell % j.sx, j.oy + cell / (j.sx * j.sz), j.oz + (cell / j.sx) % j.sz);
	}

	private void capture(Job j) {
		long t0 = System.nanoTime();
		long budget = 30_000_000L;
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		HolderLookup.Provider reg = j.level.registryAccess();
		while (j.captureCursor < j.n) {
			int k = j.captureCursor++;
			pos(j, j.idx[k], p);
			BlockState s = j.level.getBlockState(p);
			j.before[k] = s;
			if (s.hasBlockEntity()) {
				BlockEntity be = j.level.getBlockEntity(p);
				if (be != null) j.beforeBE.put(j.idx[k], V.saveBlockEntity(be, reg));
			}
			if ((k & 255) == 0 && System.nanoTime() - t0 > budget) return;
		}
		analyze(j, t0, budget);
	}

	/** On-kopya sonrasi: catisma, koruma, onay esikleri. */
	private void analyze(Job j, long t0, long budget) {
		if (!j.analyzing) {
			j.analyzing = true;
			j.analyzeCursor = 0;
			j.ownBoxes = u.ownBoxes(j.level);
		}
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		String dim = j.level.dimension().identifier().toString();
		boolean anyProt = !u.protection.all().isEmpty();
		while (j.analyzeCursor < j.n) {
			int k = j.analyzeCursor++;
			BlockState b = j.before[k];
			BlockState t = j.target[k];
			if (b == t) {
				j.aUnchanged++;
				continue;
			}
			pos(j, j.idx[k], p);
			if (anyProt && u.protection.isProtected(dim, p.getX(), p.getY(), p.getZ())) j.aProtected++;
			if (b.isAir()) continue;
			if (Classify.isArtificial(b)) {
				if (!insideAny(j.ownBoxes, p)) {
					j.aArtificial++;
					if (t.isAir()) j.aArtificialRemoved++;
					if (j.conflictSamples.size() < 8) {
						j.conflictSamples.add(p.getX() + "," + p.getY() + "," + p.getZ() + " "
							+ net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(b.getBlock()));
					}
				}
			} else if (t.isAir() && b.getFluidState().isEmpty()) {
				j.aNaturalRemoved++;
			}
			if ((k & 1023) == 0 && System.nanoTime() - t0 > budget) return;
		}
		int artificial = j.aArtificial, artificialRemoved = j.aArtificialRemoved, naturalRemoved = j.aNaturalRemoved;
		int unchanged = j.aUnchanged, protectedHits = j.aProtected;
		JsonObject c = new JsonObject();
		c.addProperty("artificial_changed", artificial);
		c.addProperty("artificial_removed", artificialRemoved);
		c.addProperty("natural_removed", naturalRemoved);
		c.addProperty("unchanged", unchanged);
		c.addProperty("protected", protectedHits);
		j.conflicts = c;
		if (protectedHits > 0) {
			j.message = "korunan bölgeye " + protectedHits + " hücre denk geliyor; inşa yapılmadı";
			finish(j, Job.State.FAILED);
			return;
		}
		if (artificial > 0 && !j.allowModify && j.kind == Job.Kind.BUILD) {
			String eg = j.conflictSamples.isEmpty() ? "" : " (ör. " + j.conflictSamples.get(0).replace("minecraft:", "") + ")";
			j.message = "var olan bir yapının " + artificial + " bloğuna dokunacaktı" + eg + "; açıkça istenmedikçe yapılmaz (allow_modify)";
			finish(j, Job.State.FAILED);
			return;
		}
		// on-kopya diske yazilmadan yerlestirme baslamaz (cokme guvenligi); yazim arka planda
		j.saveFuture = JobStore.saveAsync(u.worldDir, j);
		j.state = Job.State.SAVING;
	}

	private void afterSaved(Job j) {
		if (j.saveFuture.isCompletedExceptionally()) {
			j.message = "geri alma verisi diske yazılamadı";
			finish(j, Job.State.FAILED);
			return;
		}
		int artificialRemoved = j.aArtificialRemoved, naturalRemoved = j.aNaturalRemoved;
		boolean big = artificialRemoved >= u.settings.confirmRemoveArtificial || naturalRemoved >= u.settings.confirmRemoveNatural;
		if (big && !j.confirmed && j.kind == Job.Kind.BUILD) {
			j.state = Job.State.AWAITING_CONFIRM;
			JobStore.journal(u.worldDir, j, false);
			Chat.toAll(u.server, Chat.withButtons(Chat.warn("Büyük silme: " + naturalRemoved + " doğal, " + artificialRemoved
					+ " yapay blok kaldırılacak. Alan parçacıklarla gösteriliyor."),
				List.of(Chat.Button.run("Onayla", "/usta onayla " + j.id, "Bu alandaki silmeyi onayla ve kur"),
					Chat.Button.run("İptal", "/usta iptal " + j.id, "Bu işi iptal et"))));
			u.events.publish("job_awaiting_confirm", summary(j));
			outline(j);
			return;
		}
		beginRunning(j);
	}

	private static boolean insideAny(List<int[]> boxes, BlockPos p) {
		for (int[] b : boxes) {
			if (p.getX() >= b[0] && p.getX() < b[0] + b[3] && p.getY() >= b[1] && p.getY() < b[1] + b[4] && p.getZ() >= b[2] && p.getZ() < b[2] + b[5]) return true;
		}
		return false;
	}

	private void beginRunning(Job j) {
		if (j.kind != Job.Kind.UNDO) {
			if (!j.explosion) EntityGuard.protect(j); // patlamada hedefler hava: kimse gomulmez
		} else {
			EntityGuard.undoEntities(j);
		}
		j.state = Job.State.RUNNING;
		if (j.replay) j.cursor = 0;
		j.lastJournalMs = System.currentTimeMillis();
		if (j.bar == null) {
			j.bar = new ServerBossEvent(UUID.randomUUID(), Component.literal("Usta · " + j.label), BossEvent.BossBarColor.YELLOW, BossEvent.BossBarOverlay.PROGRESS);
			for (ServerPlayer pl : u.server.getPlayerList().getPlayers()) j.bar.addPlayer(pl);
		}
		JobStore.journal(u.worldDir, j, false);
		u.events.publish("job_started", summary(j));
	}

	private void place(Job j) {
		if (j.explosion && !MassExplosion.ready(j)) return; // fitil yaniyor
		long t0 = System.nanoTime();
		boolean instant = j.mode == Job.Mode.INSTANT;
		long budget = (instant ? u.settings.instantBudgetMs : u.settings.watchBudgetMs) * 1_000_000L;
		long allowed;
		if (instant) {
			allowed = Long.MAX_VALUE;
		} else if (j.waveCursor != null) {
			// sok dalgasi: yaricap sabit hizla buyur, icinde kalan hucreler kalkar
			allowed = Math.max(0, j.waveCursor[(int) Math.min(j.ticksRunning, j.waveCursor.length - 1)] - j.cursor);
		} else {
			double totalTicks = Math.max(1, j.seconds * 20);
			long expected = (long) Math.ceil(j.n * Math.min(1.0, (j.ticksRunning + 1) / totalTicks));
			allowed = Math.max(0, expected - j.cursor);
		}
		j.ticksRunning++;
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		HolderLookup.Provider reg = j.level.registryAccess();
		int placed = 0;
		int firstK = j.cursor;
		while (j.cursor < j.n && placed < allowed) {
			int k = j.cursor;
			int cell = j.idx[k];
			BlockState t = j.target[k];
			if (t == null) {
				j.cursor++;
				continue;
			}
			pos(j, cell, p);
			j.level.setBlock(p, t, V.PLACE_FLAGS);
			CompoundTag be = j.targetBE.get(cell);
			if (be != null) {
				BlockEntity e = j.level.getBlockEntity(p);
				if (e != null) {
					V.loadBlockEntity(e, be, reg);
					V.sendBlockUpdated(j.level, p, t);
				}
			}
			j.cursor++;
			placed++;
			if ((placed & 63) == 0 && System.nanoTime() - t0 > budget) break;
		}
		if (j.explosion) {
			MassExplosion.effects(j, firstK, j.cursor);
			MassExplosion.hits(j, false);
		} else if (placed > 0 && !instant && u.settings.effects) {
			effects(j, firstK, j.cursor);
		}
		updateBar(j);
		long now = System.currentTimeMillis();
		if (now - j.lastJournalMs > 2000) {
			JobStore.journal(u.worldDir, j, false);
			j.lastJournalMs = now;
			u.events.publish("job_progress", summary(j));
		}
		if (j.cursor >= j.n) {
			j.state = Job.State.SETTLING;
			j.settleCursor = 0;
		}
	}

	private void effects(Job j, int from, int to) {
		effectTick++;
		int count = j.mode == Job.Mode.CINEMATIC ? 3 : 1;
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		for (int e = 0; e < count; e++) {
			int k = from + (int) ((to - from) * (e + 0.5) / count);
			if (k >= to || k < 0 || k >= j.n) continue;
			BlockState t = j.target[k];
			if (t == null || t.isAir()) continue;
			pos(j, j.idx[k], p);
			j.level.sendParticles(ParticleTypes.POOF, p.getX() + 0.5, p.getY() + 0.5, p.getZ() + 0.5, 1, 0.25, 0.25, 0.25, 0.01);
			if (effectTick % (j.mode == Job.Mode.CINEMATIC ? 2 : 4) == 0 && e == 0) {
				j.level.playSound(null, p, t.getSoundType().getPlaceSound(), SoundSource.BLOCKS, 0.35f, 0.9f + (effectTick % 5) * 0.05f);
			}
		}
	}

	private void updateBar(Job j) {
		if (j.bar == null) return;
		float prog = (float) j.progress();
		j.bar.setProgress(prog);
		if (j.ticksRunning % 10 == 1 || j.cursor >= j.n) {
			String eta = "";
			if (j.mode != Job.Mode.INSTANT) {
				double left = Math.max(0, j.seconds - j.ticksRunning / 20.0);
				eta = " · ~" + (int) Math.ceil(left) + " sn";
			}
			j.bar.setName(Component.literal("Usta · " + j.label + " · %" + (int) (prog * 100) + eta));
		}
	}

	private void settle(Job j) {
		if (j.explosion && !MassExplosion.shell(j)) return; // krater kenari: dusen kum, akan su, havada kalan mesale
		long t0 = System.nanoTime();
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		int total = j.n * 2;
		while (j.settleCursor < total) {
			int k = j.settleCursor % j.n;
			j.settleCursor++;
			if (j.settle == null || !j.settle[k]) continue;
			pos(j, j.idx[k], p);
			BlockState cur = j.level.getBlockState(p);
			BlockState upd = Block.updateFromNeighbourShapes(cur, j.level, p);
			if (upd != cur && !upd.isAir()) {
				j.level.setBlock(p, upd, V.SETTLE_FLAGS);
				j.target[k] = upd;
				j.settledChanged++;
			}
			if ((j.settleCursor & 255) == 0 && System.nanoTime() - t0 > 25_000_000L) return;
		}
		// kizilatas: sessiz yerlestirme komsu guncellemesi yapmaz; devreleri bir kez uyandir ki guc durumlarini
		// (kol/mesale/tel/piston/kapi/lamba) oyunun kendi kuraliyla hesaplasinlar
		if (!j.redstoneDone) {
			j.redstoneDone = true;
			int woke = 0;
			for (int k = 0; k < j.n && woke < 4096; k++) {
				BlockState t = j.target[k];
				if (t == null || t.isAir()) continue;
				Block blk = t.getBlock();
				if ((Physics.cachedFlags(t) & Physics.REDSTONE) == 0 && !(blk instanceof net.minecraft.world.level.block.DoorBlock)
					&& !(blk instanceof net.minecraft.world.level.block.TrapDoorBlock)
					&& !(blk instanceof net.minecraft.world.level.block.FenceGateBlock)) continue;
				pos(j, j.idx[k], p);
				BlockPos bp = p.immutable();
				BlockState cur = j.level.getBlockState(bp);
				j.level.updateNeighborsAt(bp, cur.getBlock(), null);
				for (net.minecraft.core.Direction d : net.minecraft.core.Direction.values()) {
					j.level.updateNeighborsAt(bp.relative(d), cur.getBlock(), null);
				}
				cur.handleNeighborChanged(j.level, bp, cur.getBlock(), null, false);
				woke++;
			}
			if (woke > 0) j.redstoneWoke = woke;
		}
		// destek denetimi (oyunun kendi kurali), artimli
		if (j.supportCursor < 0) j.supportCursor = 0;
		while (j.supportCursor < j.n) {
			int k = j.supportCursor++;
			BlockState t = j.target[k];
			if (t == null || t.isAir()) continue;
			int f = Physics.cachedFlags(t);
			if ((f & (Physics.SUPPORT_FLOOR | Physics.SUPPORT_WALL | Physics.SUPPORT_CEIL)) == 0) continue;
			pos(j, j.idx[k], p);
			if (!t.canSurvive(j.level, p)) {
				j.unsupported++;
				if (j.unsupportedSamples.size() < 8) {
					j.unsupportedSamples.add(p.getX() + "," + p.getY() + "," + p.getZ() + " "
						+ net.minecraft.core.registries.BuiltInRegistries.BLOCK.getKey(t.getBlock()));
				}
			}
			if ((k & 1023) == 0 && System.nanoTime() - t0 > 25_000_000L) return;
		}
		j.state = Job.State.ENTITIES;
	}

	private void spawnEntities(Job j) {
		for (Plan.EntitySpec e : j.spawn) {
			try {
				CompoundTag tag = V.parseSnbt(e.snbt());
				tag.putString("id", e.type());
				Entity ent = V.loadEntity(tag, j.level);
				if (ent == null) continue;
				ent.snapTo(e.x(), e.y(), e.z(), e.yaw(), e.pitch());
				if (j.level.addFreshEntity(ent)) j.spawned.add(ent.getUUID());
			} catch (Exception ex) {
				UstaMod.LOG.warn("Varlik olusturulamadi: {}", e.type(), ex);
			}
		}
	}

	private void outline(Job j) {
		double x0 = j.ox, y0 = j.oy, z0 = j.oz, x1 = j.ox + j.sx, y1 = j.oy + j.sy, z1 = j.oz + j.sz;
		int steps = 24;
		for (int i = 0; i <= steps; i++) {
			double t = i / (double) steps;
			double x = x0 + (x1 - x0) * t, z = z0 + (z1 - z0) * t;
			for (double y : new double[]{y0, y1}) {
				j.level.sendParticles(ParticleTypes.END_ROD, x, y, z0, 1, 0, 0, 0, 0);
				j.level.sendParticles(ParticleTypes.END_ROD, x, y, z1, 1, 0, 0, 0, 0);
				j.level.sendParticles(ParticleTypes.END_ROD, x0, y, z, 1, 0, 0, 0, 0);
				j.level.sendParticles(ParticleTypes.END_ROD, x1, y, z, 1, 0, 0, 0, 0);
			}
		}
	}

	private void finish(Job j, Job.State st) {
		j.state = st;
		j.finishedAt = System.currentTimeMillis();
		if (j.explosion) MassExplosion.onFinished(j);
		releaseTickets(j);
		loading.clear();
		if (j.bar != null) {
			j.bar.removeAllPlayers();
			j.bar = null;
		}
		active = null;
		boolean touched = j.cursor > 0;
		boolean recorded = j.kind == Job.Kind.BUILD && touched && (st == Job.State.DONE || st == Job.State.CANCELLED);
		if (recorded) {
			History.Entry e = new History.Entry();
			e.id = j.id;
			e.kind = "BUILD";
			e.label = j.label;
			e.state = st.name();
			e.created = j.createdAt;
			e.finished = j.finishedAt;
			e.dim = j.level.dimension().identifier().toString();
			e.box = new int[]{j.ox, j.oy, j.oz, j.sx, j.sy, j.sz};
			e.changed = j.cursor;
			e.source = j.source;
			e.request = j.requestId;
			e.group = j.group;
			if (st == Job.State.CANCELLED) {
				// kismi is: geri alma yalniz yerlestirilen kismi kapsar
				truncate(j);
			}
			java.util.concurrent.CompletableFuture<?> prev = j.saveFuture == null ? java.util.concurrent.CompletableFuture.completedFuture(null) : j.saveFuture;
			j.saveFuture = prev.handle((a, b) -> null).thenCompose(x -> JobStore.saveAsync(u.worldDir, j))
				.whenComplete((a, b) -> {
					if (b != null) UstaMod.LOG.warn("Is verisi yazilamadi: {}", j.id, b);
					release(j);
				});
			u.history.put(e);
		} else if (j.kind == Job.Kind.UNDO && st == Job.State.DONE) {
			History.Entry e = u.history.get(j.refJob);
			if (e != null) {
				e.undone = true;
				e.finished = System.currentTimeMillis();
				u.history.put(e);
			}
		} else if (j.kind == Job.Kind.REDO && st == Job.State.DONE) {
			History.Entry e = u.history.get(j.refJob);
			if (e != null) {
				try {
					Job src = JobStore.load(u.worldDir, j.refJob, this::levelOf, V.blockLookup(u.server));
					src.before = j.before;
					src.beforeBE.clear();
					src.beforeBE.putAll(j.beforeBE);
					src.spawned.clear();
					src.spawned.addAll(j.spawned);
					src.moved.clear();
					src.moved.addAll(j.moved);
					JobStore.saveAsync(u.worldDir, src);
				} catch (Exception ex) {
					UstaMod.LOG.warn("Yineleme verisi guncellenemedi", ex);
				}
				e.undone = false;
				e.finished = System.currentTimeMillis();
				u.history.put(e);
			}
		}
		if (!recorded) {
			java.util.concurrent.CompletableFuture<?> prev = j.saveFuture == null ? java.util.concurrent.CompletableFuture.completedFuture(null) : j.saveFuture;
			prev.whenComplete((a, b) -> release(j));
		}
		JobStore.journal(u.worldDir, j, true);
		pruneFinished();
		JsonObject s = summary(j);
		u.events.publish("job_" + st.name().toLowerCase(Locale.ROOT), s);
		u.onJobFinished(j);
	}

	/** Biten isin buyuk dizilerini birakir (bellek is bitince geri doner); geri alma diskten yuklenir. */
	private static void release(Job j) {
		j.released = true;
		j.planCells = null;
		j.planPalette = null;
		j.idx = null;
		j.target = null;
		j.before = null;
		j.settle = null;
		j.targetBE.clear();
		j.beforeBE.clear();
		j.ownBoxes = null;
		j.waveCursor = null;
		j.blast = null;
	}

	private void pruneFinished() {
		if (jobs.size() <= 300) return;
		List<Job> fin = new ArrayList<>();
		for (Job x : jobs.values()) if (x.finished()) fin.add(x);
		fin.sort((a, b) -> Long.compare(a.finishedAt, b.finishedAt));
		for (int i = 0; i < fin.size() - 200; i++) jobs.remove(fin.get(i).id);
	}

	/** Iptal edilen isin geri alma verisini yerlestirilen kisimla sinirlar. */
	private static void truncate(Job j) {
		int m = j.cursor;
		j.idx = Arrays.copyOf(j.idx, m);
		j.target = Arrays.copyOf(j.target, m);
		if (j.before != null) j.before = Arrays.copyOf(j.before, m);
		if (j.settle != null) j.settle = Arrays.copyOf(j.settle, m);
		j.n = m;
	}

	// ------------------------------------------------------------------ geri al / yinele
	public Job makeUndo(History.Entry e) throws Exception {
		ServerLevel level = levelOf(e.dim);
		Job src = JobStore.load(u.worldDir, e.id, this::levelOf, V.blockLookup(u.server));
		if (src.before == null) throw new IllegalStateException("bu işin geri alma verisi yok");
		int n = src.effectiveN();
		Job j = new Job(newId(), Job.Kind.UNDO, "Geri al: " + src.label, level, src.ox, src.oy, src.oz, src.sx, src.sy, src.sz, n);
		j.idx = new int[n];
		j.target = new BlockState[n];
		j.settle = new boolean[n];
		for (int i = 0; i < n; i++) {
			j.idx[i] = src.idx[n - 1 - i];
			j.target[i] = src.before[n - 1 - i];
		}
		j.targetBE.putAll(src.beforeBE);
		j.removeEntities.addAll(src.spawned);
		j.moveBack.addAll(src.moved);
		j.refJob = src.id;
		j.mode = Job.Mode.INSTANT;
		j.source = "undo";
		j.before = new BlockState[0];
		return j;
	}

	public Job makeRedo(History.Entry e) throws Exception {
		ServerLevel level = levelOf(e.dim);
		Job src = JobStore.load(u.worldDir, e.id, this::levelOf, V.blockLookup(u.server));
		int n = src.effectiveN();
		Job j = new Job(newId(), Job.Kind.REDO, src.label, level, src.ox, src.oy, src.oz, src.sx, src.sy, src.sz, n);
		j.idx = Arrays.copyOf(src.idx, n);
		j.target = Arrays.copyOf(src.target, n);
		j.settle = new boolean[n];
		j.targetBE.putAll(src.targetBE);
		j.spawn.addAll(src.spawn);
		j.refJob = src.id;
		j.mode = Job.Mode.INSTANT;
		j.source = "redo";
		j.allowModify = true;
		return j;
	}

	public ServerLevel levelOf(String dim) {
		if (dim == null) return u.server.overworld();
		ServerLevel l = u.server.getLevel(ResourceKey.create(Registries.DIMENSION, Identifier.parse(dim)));
		return l == null ? u.server.overworld() : l;
	}

	// ------------------------------------------------------------------ yeniden baslatma
	/** Sunucu acilisinda yarim kalan isleri bulur ve kuyruga koyar. */
	public int resumeUnfinished() {
		Path jobsDir = u.worldDir.resolve("jobs");
		if (!Files.isDirectory(jobsDir)) return 0;
		int count = 0;
		try (var ds = Files.list(jobsDir)) {
			for (Path d : ds.toList()) {
				String id = d.getFileName().toString();
				JsonObject jr = JobStore.readJournal(u.worldDir, id);
				if (jr == null) continue;
				String st = jr.get("state").getAsString();
				if (st.equals("DONE") || st.equals("CANCELLED") || st.equals("FAILED")) continue;
				try {
					Job j = JobStore.load(u.worldDir, id, this::levelOf, V.blockLookup(u.server));
					j.mode = Job.Mode.valueOf(jr.get("mode").getAsString());
					j.seconds = jr.get("seconds").getAsDouble();
					j.source = jr.has("source") && !jr.get("source").isJsonNull() ? jr.get("source").getAsString() : "resume";
					if (jr.has("ref") && !jr.get("ref").isJsonNull()) j.refJob = jr.get("ref").getAsString();
					if (jr.has("request") && !jr.get("request").isJsonNull()) j.requestId = jr.get("request").getAsString();
					boolean clean = jr.get("clean").getAsBoolean();
					int cursor = jr.get("cursor").getAsInt();
					if (st.equals("RUNNING") || st.equals("SETTLING") || st.equals("ENTITIES")) {
						j.cursor = clean ? cursor : 0;
						j.replay = !clean;
					} else {
						j.cursor = 0;
						if (st.equals("LOADING") || st.equals("CAPTURING") || st.equals("QUEUED")) j.before = null;
					}
					j.allowModify = true; // ilk denetimden gecmisti
					jobs.put(j.id, j);
					synchronized (this) {
						queue.addFirst(j);
					}
					count++;
				} catch (Exception e) {
					UstaMod.LOG.warn("Yarim is yuklenemedi: {}", id, e);
				}
			}
		} catch (Exception e) {
			UstaMod.LOG.warn("Is klasoru okunamadi", e);
		}
		return count;
	}

	/** Temiz kapanis: aktif isin imlecini "temiz" olarak yaz. */
	public void onServerStopping() {
		Job j = active;
		if (j != null) {
			JobStore.journal(u.worldDir, j, true);
			releaseTickets(j);
			if (j.bar != null) j.bar.removeAllPlayers();
		}
		synchronized (this) {
			for (Job q : queue) JobStore.journal(u.worldDir, q, true);
		}
	}

	// ------------------------------------------------------------------ ozet
	public JsonObject summary(Job j) {
		JsonObject o = new JsonObject();
		o.addProperty("id", j.id);
		o.addProperty("kind", j.kind.name());
		o.addProperty("label", j.label);
		o.addProperty("state", j.state.name());
		o.addProperty("mode", j.mode.name());
		o.addProperty("seconds", j.seconds);
		o.addProperty("total", j.effectiveN());
		o.addProperty("placed", j.cursor);
		o.addProperty("progress", Math.round(j.progress() * 1000) / 1000.0);
		JsonArray box = new JsonArray();
		for (int v : new int[]{j.ox, j.oy, j.oz, j.sx, j.sy, j.sz}) box.add(v);
		o.add("box", box);
		o.addProperty("dim", j.level.dimension().identifier().toString());
		o.addProperty("source", j.source);
		if (j.explosion) {
			o.addProperty("explosion", true);
			o.add("explosion_meta", j.meta);
		}
		if (j.requestId != null) o.addProperty("request", j.requestId);
		if (j.message != null) o.addProperty("message", j.message);
		o.add("conflicts", j.conflicts);
		o.addProperty("unsupported", j.unsupported);
		if (!j.unsupportedSamples.isEmpty()) {
			JsonArray us = new JsonArray();
			j.unsupportedSamples.forEach(us::add);
			o.add("unsupported_samples", us);
		}
		if (!j.conflictSamples.isEmpty()) {
			JsonArray cs = new JsonArray();
			j.conflictSamples.forEach(cs::add);
			o.add("conflict_samples", cs);
		}
		o.addProperty("settled_changed", j.settledChanged);
		o.addProperty("redstone_woke", j.redstoneWoke);
		o.addProperty("moved_entities", j.moved.size());
		o.addProperty("spawned_entities", j.spawned.size());
		o.addProperty("paused", j.pauseRequested || u.server.isPaused());
		if (j.tickSamples > 0) {
			o.addProperty("avg_tick_ms", Math.round(j.sumTickNanos / (double) j.tickSamples / 1e4) / 100.0);
			o.addProperty("max_tick_ms", Math.round(j.maxTickNanos / 1e4) / 100.0);
		}
		if (j.startedAt > 0) {
			long end = j.finishedAt > 0 ? j.finishedAt : System.currentTimeMillis();
			o.addProperty("elapsed_s", Math.round((end - j.startedAt) / 100.0) / 10.0);
		}
		return o;
	}

}
