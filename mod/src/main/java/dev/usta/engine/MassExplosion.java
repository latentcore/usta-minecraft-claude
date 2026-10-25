package dev.usta.engine;

import dev.usta.UstaMod;
import dev.usta.core.Usta;
import dev.usta.game.Chat;
import dev.usta.world.Protection;
import it.unimi.dsi.fastutil.longs.Long2ObjectOpenHashMap;
import it.unimi.dsi.fastutil.longs.LongArrayList;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.BitSet;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Predicate;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.SectionPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.item.PrimedTnt;
import net.minecraft.world.level.Explosion;
import net.minecraft.world.level.ExplosionDamageCalculator;
import net.minecraft.world.level.ServerExplosion;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.TntBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.LevelChunkSection;
import net.minecraft.world.level.gamerules.GameRules;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/**
 * Toplu TNT patlamasi. Esik ve ustu bitisik TNT atesleninde (kizilatas, cakmak, ok, ates, yakin patlama) vanilla her TNT
 * icin ayri varlik + ayri patlama uretir (100.000 TNT = dakikalarca donma). Burada kume tek seferde hesaplanir:
 * krater vanilla isin modeline yakin bir guc alaniyla (havada blok basina 0.75, katida direncle) bulunur, zincirleme
 * patlayan komsu TNT'ler de kaynaga katilir, sonuc bir Usta isi olarak ates noktasindan disari dogru sok dalgasi
 * sirasiyla, patlama sesi/parcaciklariyla uygulanir. Is gecmise yazilir: /usta geri ile her sey geri gelir.
 * Kucuk kumeler (esik alti) vanilla kalir. Agir hesap sunucu is parcaciginin disinda yapilir.
 */
public final class MassExplosion {
	private MassExplosion() {}

	/** vanilla TNT: guc 4, isin basina 0.7-1.3 kat */
	static final float POWER = 4.0f * 1.3f;
	/** vanilla: her 0.3 blokta 0.225 -> havada blok basina 0.75 */
	static final float AIR_COST = 0.75f;
	/** yikilmis kati hucreden gecis: havaya ek, direncle artar (moloz) */
	static final float DEBRIS = 0.25f;
	static final int MARGIN = 8;
	public static final int FUSE_TICKS = 80;
	static final int MAX_TNT = 4_000_000;
	static final long MAX_CELLS = 16_000_000L;
	static final int MAX_ROUNDS = 6;
	/** kume taramasi ve alan goruntusu icin tick basina sure */
	static final long STEP_NANOS = 15_000_000L;
	static final Predicate<BlockState> IS_TNT = s -> s.getBlock() instanceof TntBlock;
	private static final ExplosionDamageCalculator CALC = new ExplosionDamageCalculator();
	private static final ExecutorService EXEC = Executors.newSingleThreadExecutor(r -> {
		Thread t = new Thread(r, "usta-patlama");
		t.setDaemon(true);
		return t;
	});

	/** Usta'nin kendi yerlestirmesi (insa, geri alma, krater) surerken atesleme yok sayilir: geri alma TNT'yi yeniden patlatmaz. */
	public static int suppress;
	private static final List<Blast> ACTIVE = new ArrayList<>();
	private static long activatedAt;
	private static boolean activatedCache;

	// ------------------------------------------------------------------ kancalar (TntBlockMixin, sunucu is parcacigi)
	/** TntBlock.prime basi. true: vanilla atesleme yapilmaz (TNT blok olarak kalir, patlamayi Usta yurutur). */
	public static boolean onPrime(ServerLevel level, BlockPos pos) {
		if (suppress > 0) return true;
		Usta u = usable(level);
		if (u == null) return false;
		if (claimed(level, pos)) return true;
		return start(u, level, pos.immutable(), true);
	}

	/** TntBlock.wasExploded basi (blok zaten hava). true: vanilla kisa fitilli TNT varligi olusturulmaz. */
	public static boolean onExploded(ServerLevel level, BlockPos pos) {
		if (suppress > 0) return true;
		Usta u = usable(level);
		if (u == null) return false;
		if (claimed(level, pos)) return true;
		// suren kucuk (vanilla) zincirde her TNT icin kumeyi yeniden aramamak icin
		int now = u.server.getTickCount();
		SMALL.removeIf(s -> s.expire() < now);
		for (Small s : SMALL) if (s.level() == level && s.members().get(pos.getX(), pos.getY(), pos.getZ())) return false;
		return start(u, level, pos.immutable(), false);
	}

	private record Small(ServerLevel level, Bits members, int expire) {}

	private static final List<Small> SMALL = new ArrayList<>();

	private static Usta usable(ServerLevel level) {
		Usta u = Usta.get();
		if (u == null || u.server != level.getServer() || !u.aiEnabled || !u.settings.massExplosion) return null;
		if (!level.getGameRules().get(GameRules.TNT_EXPLODES)) return null;
		long now = System.currentTimeMillis();
		if (now - activatedAt > 5000) {
			activatedCache = u.activated();
			activatedAt = now;
		}
		return activatedCache ? u : null;
	}

	private static boolean claimed(ServerLevel level, BlockPos pos) {
		int x = pos.getX(), y = pos.getY(), z = pos.getZ();
		for (Blast b : ACTIVE) {
			if (b.level != level) continue;
			// kume taramasi tick'lere bolunmusken gelen ikinci atesleme (nadir): taramayi hemen bitir
			if (b.bfs != null && !b.tnt.get(x, y, z)) b.bfs.run(MAX_TNT, Long.MAX_VALUE);
			if (b.tnt.get(x, y, z) || b.ignition.equals(pos)) return true;
		}
		return false;
	}

	private static boolean start(Usta u, ServerLevel level, BlockPos pos, boolean seedIsTnt) {
		int threshold = Math.max(8, u.settings.massExplosionThreshold);
		TntMap w = new TntMap(u, level);
		// karar icin esik kadar TNT bulmak yeter; kumenin kalani sonraki tick'lerde taranir (atesleme ani takilmaz)
		Bfs bfs = new Bfs(w, new Bits(), 2);
		bfs.seed(pos);
		bfs.run(threshold, Long.MAX_VALUE);
		if (bfs.seen.count < threshold) {
			// seyrek dizilim (aralikli TNT): vanilla zinciri 4-5 bloga kadar ulasir
			bfs = new Bfs(w, new Bits(), 4);
			bfs.seed(pos);
			bfs.run(threshold, Long.MAX_VALUE);
			if (bfs.seen.count < threshold) {
				if (!seedIsTnt && bfs.seen.count > 0 && SMALL.size() < 64) SMALL.add(new Small(level, bfs.seen, u.server.getTickCount() + 100));
				return false;
			}
		}
		Blast b = new Blast(u, level, pos, bfs.seen, u.server.getTickCount());
		b.bfs = bfs;
		ACTIVE.add(b);
		level.playSound(null, pos, SoundEvents.TNT_PRIMED, SoundSource.BLOCKS, 1.0f, 1.0f);
		return true;
	}

	static String fmt(int n) {
		return String.format(Locale.forLanguageTag("tr"), "%,d", n);
	}

	// ------------------------------------------------------------------ sunucu tick'i
	/** Asamalar: kume taramasi -> alan goruntusu (ikisi tick basina en cok ~15 ms) -> hesap (arka planda) -> is. */
	public static void tick(Usta u) {
		if (ACTIVE.isEmpty()) return;
		int now = u.server.getTickCount();
		for (Blast b : new ArrayList<>(ACTIVE)) {
			if (b.u != u) {
				ACTIVE.remove(b);
				continue;
			}
			if (now < b.startTick + FUSE_TICKS) {
				b.level.sendParticles(ParticleTypes.SMOKE, true, false, b.ignition.getX() + 0.5, b.ignition.getY() + 1.05, b.ignition.getZ() + 0.5,
					2, 0.15, 0.05, 0.15, 0.01);
			}
			long deadline = System.nanoTime() + STEP_NANOS;
			if (b.bfs != null) {
				if (!b.bfs.run(MAX_TNT, deadline)) continue;
				b.bfsMs += b.bfs.nanos / 1e6;
				b.bfs = null;
				if (b.rounds == 0) {
					Chat.toAll(u.server, Chat.warn("Toplu patlama: " + fmt(b.tnt.count) + " TNT birlikte patlıyor (hızlı patlama, kasmasız) · geri almak için /usta geri"));
					UstaMod.LOG.info("Toplu patlama: {} TNT, kume taramasi {} ms", b.tnt.count, String.format(Locale.ROOT, "%.1f", b.bfsMs));
				}
				b.snap = prepare(b);
			}
			if (b.snap != null) {
				if (!b.snap.step(deadline)) continue;
				Snap sn = b.snap;
				b.snap = null;
				Grid g = sn.finish();
				b.snapshotMs += sn.nanos / 1e6;
				boolean atMinY = sn.y0 <= b.level.getMinY(), atMaxY = sn.y1 >= b.level.getMaxY();
				BlockPos ign = b.ignition;
				b.future = CompletableFuture.supplyAsync(() -> compute(g, ign, atMinY, atMaxY), EXEC);
				continue;
			}
			if (b.future == null || !b.future.isDone()) continue;
			CompletableFuture<Result> f = b.future;
			b.future = null;
			Result r;
			try {
				r = f.join();
			} catch (Exception e) {
				UstaMod.LOG.error("Toplu patlama hesaplanamadi", e);
				Chat.toAll(u.server, Chat.error("Toplu patlama hesaplanamadı: " + e.getMessage()));
				ACTIVE.remove(b);
				continue;
			}
			b.computeMs += r.computeMs;
			b.sweeps += r.sweeps;
			for (int i = 0; i < r.chained.size(); i++) {
				long p = r.chained.getLong(i);
				b.tnt.add(BlockPos.getX(p), BlockPos.getY(p), BlockPos.getZ(p));
			}
			if (r.extend && b.rounds < MAX_ROUNDS) {
				// zincir alanin kenarina ulasti: oradan kumeyi genislet, alani buyutup yeniden hesapla
				b.rounds++;
				Bfs e = new Bfs(new TntMap(u, b.level), b.tnt, 2);
				for (int i = 0; i < r.chained.size(); i++) e.seed(BlockPos.of(r.chained.getLong(i)));
				b.bfs = e;
				continue;
			}
			launch(b, r);
		}
	}

	public static void reset() {
		ACTIVE.clear();
		SMALL.clear();
		suppress = 0;
	}

	// ------------------------------------------------------------------ kume (BFS)
	/** Chebyshev 2..radius ofsetleri; her biri icin "ebeveyn" (1 adim yakin) komsunun 27'lik indeksi. */
	private static final int[][] FAR = new int[5][];
	private static final int FULL_MASK = ((1 << 27) - 1) & ~(1 << 13);

	static {
		for (int r = 2; r <= 4; r++) {
			List<int[]> l = new ArrayList<>();
			for (int dy = -r; dy <= r; dy++) {
				for (int dz = -r; dz <= r; dz++) {
					for (int dx = -r; dx <= r; dx++) {
						int m = Math.max(Math.abs(dx), Math.max(Math.abs(dy), Math.abs(dz)));
						if (m < 2) continue;
						int px = Integer.signum(dx), py = Integer.signum(dy), pz = Integer.signum(dz);
						l.add(new int[]{dx, dy, dz, (py + 1) * 9 + (pz + 1) * 3 + (px + 1)});
					}
				}
			}
			int[] a = new int[l.size() * 4];
			for (int i = 0; i < l.size(); i++) System.arraycopy(l.get(i), 0, a, i * 4, 4);
			FAR[r] = a;
		}
	}

	/** Derinlik oncelikli kume taramasi: radius icindeki (Chebyshev) TNT'ler birbirine bagli sayilir; tick'lere bolunebilir. */
	static final class Bfs {
		final TntMap w;
		final Bits seen;
		final int radius;
		final LongArrayList stack = new LongArrayList();
		long nanos;

		Bfs(TntMap w, Bits seen, int radius) {
			this.w = w;
			this.seen = seen;
			this.radius = radius;
		}

		/** seed TNT ise yigina; degilse (patlamis TNT'nin bos yeri) komsulari taranir. */
		void seed(BlockPos p) {
			long t0 = System.nanoTime();
			int x = p.getX(), y = p.getY(), z = p.getZ();
			if (w.tnt(x, y, z)) {
				seen.add(x, y, z);
				stack.add(p.asLong());
			} else {
				expand(x, y, z);
			}
			nanos += System.nanoTime() - t0;
		}

		/** true = bitti (yigin bos ya da sinir doldu); false = sure doldu, sonraki tick devam. */
		boolean run(int cap, long deadline) {
			long t0 = System.nanoTime();
			int k = 0;
			boolean done = true;
			while (!stack.isEmpty() && seen.count < cap) {
				long p = stack.popLong();
				expand(BlockPos.getX(p), BlockPos.getY(p), BlockPos.getZ(p));
				if ((++k & 255) == 0 && System.nanoTime() > deadline) {
					done = false;
					break;
				}
			}
			nanos += System.nanoTime() - t0;
			return done;
		}

		private void expand(int x, int y, int z) {
			int mask = 0;
			for (int i = 0; i < 27; i++) {
				if (i == 13) continue;
				int qx = x + i % 3 - 1, qy = y + i / 9 - 1, qz = z + (i / 3) % 3 - 1;
				if (!w.tnt(qx, qy, qz)) continue;
				mask |= 1 << i;
				if (seen.add(qx, qy, qz)) stack.add(BlockPos.asLong(qx, qy, qz));
			}
			if (radius < 2 || mask == FULL_MASK) return;
			// uzak komsu yalniz arada (1 adim yakinda) TNT yoksa denetlenir; varsa o komsu zaten kapsar
			int[] far = FAR[radius];
			for (int e = 0; e < far.length; e += 4) {
				if ((mask & (1 << far[e + 3])) != 0) continue;
				int qx = x + far[e], qy = y + far[e + 1], qz = z + far[e + 2];
				if (w.tnt(qx, qy, qz) && seen.add(qx, qy, qz)) stack.add(BlockPos.asLong(qx, qy, qz));
			}
		}
	}

	// ------------------------------------------------------------------ alan goruntusu + hesap
	/** Hesap alani: kume + ates noktasi, her yonde MARGIN; cok buyukse ates noktasi cevresi (kalan TNT yerinde kalir). */
	private static Snap prepare(Blast b) {
		int[] bb = b.tnt.bounds();
		int minY = b.level.getMinY(), maxY = b.level.getMaxY();
		int ix = b.ignition.getX(), iy = b.ignition.getY(), iz = b.ignition.getZ();
		int x0 = Math.min(bb[0], ix) - MARGIN, y0 = Math.max(minY, Math.min(bb[1], iy) - MARGIN), z0 = Math.min(bb[2], iz) - MARGIN;
		int x1 = Math.max(bb[3], ix) + MARGIN, y1 = Math.min(maxY, Math.max(bb[4], iy) + MARGIN), z1 = Math.max(bb[5], iz) + MARGIN;
		// cok buyuk alan: ates noktasi cevresindeki kisim patlar, kalan TNT yerinde kalir
		while ((long) (x1 - x0 + 1) * (y1 - y0 + 1) * (z1 - z0 + 1) > MAX_CELLS) {
			int dx = x1 - x0, dy = y1 - y0, dz = z1 - z0;
			if (dx >= dy && dx >= dz) {
				int nd = dx * 3 / 4;
				x0 = Math.max(x0, ix - nd / 2);
				x1 = x0 + nd;
			} else if (dz >= dy) {
				int nd = dz * 3 / 4;
				z0 = Math.max(z0, iz - nd / 2);
				z1 = z0 + nd;
			} else {
				int nd = dy * 3 / 4;
				y0 = Math.max(y0, iy - nd / 2);
				y1 = Math.min(maxY, y0 + nd);
			}
			b.truncated = true;
		}
		if (b.truncated) {
			Bits keep = new Bits();
			int fx0 = x0 + MARGIN, fy0 = y0 + MARGIN, fz0 = z0 + MARGIN, fx1 = x1 - MARGIN, fy1 = y1 - MARGIN, fz1 = z1 - MARGIN;
			b.tnt.forEach((x, y, z) -> {
				if (x >= fx0 && x <= fx1 && y >= fy0 && y <= fy1 && z >= fz0 && z <= fz1) keep.add(x, y, z);
			});
			b.tnt = keep;
		}
		return new Snap(b, x0, y0, z0, x1, y1, z1);
	}

	/** Alan icindeki her hucrenin patlama sinifi: 0 hava, 1 TNT, 2 duvar (yuklu degil/korunan), 3.. direnc sinifi. */
	static final class Grid {
		final int ox, oy, oz, sx, sy, sz;
		final byte[] code;
		final float[] res = new float[256];
		final float[] cost = new float[256];
		int classes = 3;
		final BitSet src;

		Grid(int ox, int oy, int oz, int sx, int sy, int sz) {
			this.ox = ox;
			this.oy = oy;
			this.oz = oz;
			this.sx = sx;
			this.sy = sy;
			this.sz = sz;
			int n = sx * sy * sz;
			this.code = new byte[n];
			this.src = new BitSet(n);
			cost[0] = AIR_COST;
			cost[1] = AIR_COST;
			cost[2] = Float.POSITIVE_INFINITY;
		}

		int idx(int x, int y, int z) {
			return ((y - oy) * sz + (z - oz)) * sx + (x - ox);
		}

		boolean inside(int x, int y, int z) {
			return x >= ox && y >= oy && z >= oz && x < ox + sx && y < oy + sy && z < oz + sz;
		}

		int classOf(float r) {
			for (int i = 3; i < classes; i++) if (res[i] == r) return i;
			if (classes < 256) {
				res[classes] = r;
				cost[classes] = AIR_COST + DEBRIS * Math.min(r, 10f);
				return classes++;
			}
			int best = 3;
			for (int i = 4; i < classes; i++) if (Math.abs(res[i] - r) < Math.abs(res[best] - r)) best = i;
			return best;
		}

		int codeOf(BlockState s, IdentityHashMap<BlockState, Integer> memo) {
			Integer m = memo.get(s);
			if (m != null) return m;
			FluidState f = s.getFluidState();
			int c;
			if (s.isAir() && f.isEmpty()) c = 0;
			else if (s.getBlock() instanceof TntBlock) c = 1;
			else c = classOf(Math.max(s.getBlock().getExplosionResistance(), f.getExplosionResistance()));
			memo.put(s, c);
			return c;
		}
	}

	/** Alan goruntusu parca sutunlari halinde okunur; tick basina sure sinirli. */
	static final class Snap {
		final Blast b;
		final Grid g;
		final int x0, y0, z0, x1, y1, z1;
		private final int cx1, cz0, cz1;
		private int cx, cz;
		long nanos;
		private final IdentityHashMap<BlockState, Integer> memo = new IdentityHashMap<>();

		Snap(Blast b, int x0, int y0, int z0, int x1, int y1, int z1) {
			this.b = b;
			this.x0 = x0;
			this.y0 = y0;
			this.z0 = z0;
			this.x1 = x1;
			this.y1 = y1;
			this.z1 = z1;
			this.g = new Grid(x0, y0, z0, x1 - x0 + 1, y1 - y0 + 1, z1 - z0 + 1);
			this.cx = x0 >> 4;
			this.cx1 = x1 >> 4;
			this.cz0 = z0 >> 4;
			this.cz1 = z1 >> 4;
			this.cz = cz0;
		}

		/** true = tum sutunlar okundu. */
		boolean step(long deadline) {
			long t0 = System.nanoTime();
			try {
				while (cx <= cx1) {
					column(cx, cz);
					if (++cz > cz1) {
						cz = cz0;
						cx++;
					}
					if (System.nanoTime() > deadline) return cx > cx1;
				}
				return true;
			} finally {
				nanos += System.nanoTime() - t0;
			}
		}

		private void column(int cx, int cz) {
			int ax0 = Math.max(x0, cx << 4), ax1 = Math.min(x1, (cx << 4) + 15);
			int az0 = Math.max(z0, cz << 4), az1 = Math.min(z1, (cz << 4) + 15);
			LevelChunk ch = b.level.getChunkSource().getChunkNow(cx, cz);
			if (ch == null) {
				for (int y = y0; y <= y1; y++) for (int z = az0; z <= az1; z++) for (int x = ax0; x <= ax1; x++) g.code[g.idx(x, y, z)] = 2;
				return;
			}
			LevelChunkSection[] secs = ch.getSections();
			for (int cy = y0 >> 4; cy <= y1 >> 4; cy++) {
				int si = ch.getSectionIndexFromSectionY(cy);
				if (si < 0 || si >= secs.length) continue;
				LevelChunkSection sec = secs[si];
				if (sec == null || sec.hasOnlyAir()) continue;
				int ay0 = Math.max(y0, cy << 4), ay1 = Math.min(y1, (cy << 4) + 15);
				BlockState lastS = null;
				int lastC = 0;
				for (int y = ay0; y <= ay1; y++) {
					for (int z = az0; z <= az1; z++) {
						int row = g.idx(ax0, y, z);
						for (int x = ax0; x <= ax1; x++) {
							BlockState s = sec.getBlockState(x & 15, y & 15, z & 15);
							int c;
							if (s == lastS) {
								c = lastC;
							} else {
								c = g.codeOf(s, memo);
								lastS = s;
								lastC = c;
							}
							if (c != 0) g.code[row + (x - ax0)] = (byte) c;
						}
					}
				}
			}
		}

		/** Korunan bolgeler duvar olur; kume TNT'leri kaynak. */
		Grid finish() {
			long t0 = System.nanoTime();
			String dim = b.level.dimension().identifier().toString();
			for (Protection.Region r : b.u.protection.all()) {
				if (!dim.equals(r.dim)) continue;
				int rx0 = Math.max(x0, r.x0), ry0 = Math.max(y0, r.y0), rz0 = Math.max(z0, r.z0);
				int rx1 = Math.min(x1, r.x1), ry1 = Math.min(y1, r.y1), rz1 = Math.min(z1, r.z1);
				for (int y = ry0; y <= ry1; y++) for (int z = rz0; z <= rz1; z++) for (int x = rx0; x <= rx1; x++) g.code[g.idx(x, y, z)] = 2;
			}
			b.tnt.forEach((x, y, z) -> {
				if (g.inside(x, y, z) && g.code[g.idx(x, y, z)] == 1) g.src.set(g.idx(x, y, z));
			});
			nanos += System.nanoTime() - t0;
			return g;
		}
	}

	static final class Result {
		long[] cells;      // yok olacak (hava olmayan) hucreler, sok dalgasi sirasiyla
		float[] dist;      // ates noktasina dalga uzakligi (sirali)
		int tntCount;
		final LongArrayList chained = new LongArrayList();
		boolean extend;
		int sweeps;
		double computeMs;
		int minX, minY, minZ, maxX, maxY, maxZ;
	}

	private static final int[] DX = new int[26], DY = new int[26], DZ = new int[26];
	private static final float[] LEN = new float[26];

	static {
		// 0..12: tarama sirasinda onceki (negatif dogrusal ofset), 13..25: sonraki
		int a = 0, bIdx = 13;
		for (int dy = -1; dy <= 1; dy++) {
			for (int dz = -1; dz <= 1; dz++) {
				for (int dx = -1; dx <= 1; dx++) {
					if (dx == 0 && dy == 0 && dz == 0) continue;
					boolean before = dy < 0 || (dy == 0 && (dz < 0 || (dz == 0 && dx < 0)));
					int i = before ? a++ : bIdx++;
					DX[i] = dx;
					DY[i] = dy;
					DZ[i] = dz;
					LEN[i] = (float) Math.sqrt(dx * dx + dy * dy + dz * dz);
				}
			}
		}
	}

	/** Hucre basina sabit (tohumlu) 0..1 gurultu: krater kenari ve dalga cephesi dogal gorunsun. */
	static float noise(int x, int y, int z) {
		long h = x * 0x9E3779B97F4A7C15L ^ y * 0xC2B2AE3D27D4EB4FL ^ z * 0x165667B19E3779F9L;
		h ^= h >>> 31;
		h *= 0xBF58476D1CE4E5B9L;
		h ^= h >>> 29;
		return (h >>> 40) / (float) (1L << 24);
	}

	/**
	 * Guc alani (en guclu yol): kaynaklar POWER ile baslar; hava/yikilmis hucreden gecis blok basina AIR_COST (+moloz).
	 * Kati hucre, gelen guc 0.3*(direnc+0.3)'u asarsa yikilir ve gecirgen olur (sonraki patlamalar acilan bosluktan ilerler).
	 * Kume disi TNT yikilirsa o da patlar (zincir). Ileri/geri taramalarla duragan duruma kadar.
	 */
	static Result compute(Grid g, BlockPos ign, boolean atMinY, boolean atMaxY) {
		long t0 = System.nanoTime();
		final int sx = g.sx, sy = g.sy, sz = g.sz, n = sx * sy * sz;
		final byte[] code = g.code;
		final float[] cost = g.cost, res = g.res;
		final float[] pow = new float[n];
		final BitSet clear = new BitSet(n);
		final BitSet chained = new BitSet(n);
		final int[] off = new int[26];
		for (int i = 0; i < 26; i++) off[i] = (DY[i] * sz + DZ[i]) * sx + DX[i];
		for (int c = g.src.nextSetBit(0); c >= 0; c = g.src.nextSetBit(c + 1)) {
			int x = g.ox + c % sx, z = g.oz + (c / sx) % sz, y = g.oy + c / (sx * sz);
			pow[c] = POWER * (0.85f + 0.15f * noise(x, y, z));
			clear.set(c);
		}
		int sweeps = 0;
		boolean changed = true;
		while (changed && sweeps < 12) {
			changed = false;
			boolean fwd = (sweeps & 1) == 0;
			int base = fwd ? 0 : 13, step = fwd ? 1 : -1;
			for (int y = fwd ? 0 : sy - 1; fwd ? y < sy : y >= 0; y += step) {
				for (int z = fwd ? 0 : sz - 1; fwd ? z < sz : z >= 0; z += step) {
					int row = (y * sz + z) * sx;
					for (int x = fwd ? 0 : sx - 1; fwd ? x < sx : x >= 0; x += step) {
						int c = row + x;
						int cc = code[c] & 0xFF;
						if (cc == 2) continue;
						float cur = pow[c];
						float best = cur;
						for (int i = base; i < base + 13; i++) {
							int nx = x + DX[i], ny = y + DY[i], nz = z + DZ[i];
							if (nx < 0 || ny < 0 || nz < 0 || nx >= sx || ny >= sy || nz >= sz) continue;
							int p = c + off[i];
							float pp = pow[p];
							if (pp <= best) continue;
							int pc = code[p] & 0xFF;
							if (pc != 0 && !clear.get(p)) continue;
							float cand = pp - LEN[i] * cost[pc];
							if (cand > best) best = cand;
						}
						if (best <= cur) continue;
						pow[c] = best;
						changed = true;
						if (cc != 0 && !clear.get(c)) {
							int wx = g.ox + x, wy = g.oy + y, wz = g.oz + z;
							float f = 0.8f + 0.35f * noise(wx, wy, wz);
							if (cc == 1) {
								if (best * f > 0.09f) {
									clear.set(c);
									chained.set(c);
									pow[c] = Math.max(best, POWER * (0.85f + 0.15f * noise(wz, wx, wy)));
								}
							} else if (best * f > 0.3f * (res[cc] + 0.3f)) {
								clear.set(c);
							}
						}
					}
				}
			}
			sweeps++;
		}
		Result r = new Result();
		r.sweeps = sweeps;
		int m = clear.cardinality();
		long[] cells = new long[m];
		float[] dist = new float[m];
		long[] keys = new long[m];
		double icx = ign.getX() + 0.5, icy = ign.getY() + 0.5, icz = ign.getZ() + 0.5;
		int k = 0;
		r.minX = r.minY = r.minZ = Integer.MAX_VALUE;
		r.maxX = r.maxY = r.maxZ = Integer.MIN_VALUE;
		for (int c = clear.nextSetBit(0); c >= 0; c = clear.nextSetBit(c + 1)) {
			int cc = code[c] & 0xFF;
			if (cc == 0) continue;
			int lx = c % sx, lz = (c / sx) % sz, ly = c / (sx * sz);
			int x = g.ox + lx, y = g.oy + ly, z = g.oz + lz;
			if (cc == 1) r.tntCount++;
			if (chained.get(c)) {
				r.chained.add(BlockPos.asLong(x, y, z));
				boolean edge = lx < MARGIN || lz < MARGIN || lx >= sx - MARGIN || lz >= sz - MARGIN
					|| (ly < MARGIN && !atMinY) || (ly >= sy - MARGIN && !atMaxY);
				if (edge) r.extend = true;
			}
			double dx = x + 0.5 - icx, dy = y + 0.5 - icy, dz = z + 0.5 - icz;
			float d = (float) Math.sqrt(dx * dx + dy * dy + dz * dz) + 1.5f * noise(z, y, x);
			cells[k] = BlockPos.asLong(x, y, z);
			dist[k] = d;
			keys[k] = ((long) Float.floatToIntBits(d) << 32) | k;
			k++;
			if (x < r.minX) r.minX = x;
			if (y < r.minY) r.minY = y;
			if (z < r.minZ) r.minZ = z;
			if (x > r.maxX) r.maxX = x;
			if (y > r.maxY) r.maxY = y;
			if (z > r.maxZ) r.maxZ = z;
		}
		keys = Arrays.copyOf(keys, k);
		Arrays.sort(keys);
		r.cells = new long[k];
		r.dist = new float[k];
		for (int i = 0; i < k; i++) {
			int j = (int) (keys[i] & 0xFFFFFFFFL);
			r.cells[i] = cells[j];
			r.dist[i] = dist[j];
		}
		r.computeMs = (System.nanoTime() - t0) / 1e6;
		return r;
	}

	// ------------------------------------------------------------------ is olarak uygulama
	private static void launch(Blast b, Result r) {
		Usta u = b.u;
		int n = r.cells.length;
		if (n == 0) {
			ACTIVE.remove(b);
			return;
		}
		int ox = r.minX, oy = r.minY, oz = r.minZ;
		int sx = r.maxX - ox + 1, sy = r.maxY - oy + 1, sz = r.maxZ - oz + 1;
		String label = "Toplu patlama: " + fmt(r.tntCount) + " TNT";
		Job j = new Job(JobManager.newId(), Job.Kind.BUILD, label, b.level, ox, oy, oz, sx, sy, sz, n);
		j.idx = new int[n];
		j.target = new BlockState[n];
		j.settle = new boolean[n];
		BlockState air = Blocks.AIR.defaultBlockState();
		for (int k = 0; k < n; k++) {
			long p = r.cells[k];
			j.idx[k] = ((BlockPos.getY(p) - oy) * sz + (BlockPos.getZ(p) - oz)) * sx + (BlockPos.getX(p) - ox);
			j.target[k] = air;
		}
		// sok dalgasi: sabit hizla genisleyen yaricap; en uzak hucre ~9 sn'de
		float maxD = r.dist[n - 1];
		float speed = Math.max(15f, maxD / 9f);
		int ticks = Math.max(1, (int) Math.ceil(maxD / speed * 20));
		int[] wave = new int[ticks];
		int cur = 0;
		for (int t = 0; t < ticks; t++) {
			float rad = speed * (t + 1) / 20f;
			while (cur < n && r.dist[cur] <= rad) cur++;
			wave[t] = t == ticks - 1 ? n : cur;
		}
		j.mode = Job.Mode.WATCH;
		j.seconds = ticks / 20.0;
		j.source = "patlama";
		j.allowModify = true;
		j.allowDangerous = true;
		j.confirmed = true;
		j.explosion = true;
		j.waveCursor = wave;
		j.blast = b;
		j.meta.addProperty("tnt", r.tntCount);
		j.meta.addProperty("ignition", b.ignition.getX() + "," + b.ignition.getY() + "," + b.ignition.getZ());
		j.meta.addProperty("cluster_ms", Math.round(b.bfsMs * 10) / 10.0);
		j.meta.addProperty("snapshot_ms", Math.round(b.snapshotMs * 10) / 10.0);
		j.meta.addProperty("compute_ms", Math.round(b.computeMs * 10) / 10.0);
		j.meta.addProperty("sweeps", b.sweeps);
		j.meta.addProperty("rounds", b.rounds);
		if (b.truncated) j.meta.addProperty("truncated", true);
		b.job = j;
		b.dist = r.dist;
		b.speed = speed;
		UstaMod.LOG.info("Toplu patlama isi: {} TNT, {} hucre, hesap {} ms ({} tarama, {} tur), dalga {} sn", r.tntCount, n,
			String.format(Locale.ROOT, "%.1f", b.computeMs), b.sweeps, b.rounds, String.format(Locale.ROOT, "%.1f", j.seconds));
		if (b.truncated) Chat.toAll(u.server, Chat.soft("Küme çok büyük: ateşlenen yerin çevresi patlıyor, uzak kısım yerinde kalıyor."));
		if (u.jobs.active() != null) Chat.toAll(u.server, Chat.soft("Patlama, süren iş bitince başlayacak."));
		u.jobs.enqueueFront(j);
	}

	/** Fitil: dalga ates aninin 4 sn sonrasinda baslar. false = henuz degil. */
	static boolean ready(Job j) {
		Blast b = j.blast;
		if (b == null) return true;
		int left = b.startTick + FUSE_TICKS - j.level.getServer().getTickCount();
		if (left > 0) {
			if (j.bar != null && left % 10 == 0) j.bar.setName(Component.literal("Usta · " + j.label + " · fitil " + (left + 19) / 20 + " sn"));
			return false;
		}
		if (!b.boomed) {
			b.boomed = true;
			Vec3 c = Vec3.atCenterOf(b.ignition);
			b.level.sendParticles(ParticleTypes.EXPLOSION_EMITTER, true, true, c.x, c.y, c.z, 1, 0, 0, 0, 0);
			boom(b, c, 1.0f);
			b.hits = collectHits(b);
		}
		return true;
	}

	/** Her tick: yeni kalkan hucrelerden birkacinda patlama parcacigi + ses (oyuncuya dogru yaklastirilmis). */
	static void effects(Job j, int from, int to) {
		Blast b = j.blast;
		int placed = to - from;
		if (b == null || placed <= 0) return;
		RandomSource rnd = j.level.getRandom();
		BlockPos.MutableBlockPos p = new BlockPos.MutableBlockPos();
		int bursts = Math.min(4, 1 + placed / 1500);
		for (int e = 0; e < bursts; e++) {
			int k = from + rnd.nextInt(placed);
			cell(j, j.idx[k], p);
			if (e == 0) {
				j.level.sendParticles(ParticleTypes.EXPLOSION_EMITTER, true, true, p.getX() + 0.5, p.getY() + 0.5, p.getZ() + 0.5, 1, 0, 0, 0, 0);
			} else {
				j.level.sendParticles(ParticleTypes.EXPLOSION, true, false, p.getX() + 0.5, p.getY() + 0.5, p.getZ() + 0.5, 3, 1.5, 1.5, 1.5, 0);
			}
			if (e == 0 && (j.ticksRunning & 1) == 0) boom(b, Vec3.atCenterOf(p), 1.0f);
		}
	}

	/** Patlama sesi: uzaktaki oyuncu da duysun diye ses oyuncuya dogru yaklastirilir (yon korunur). */
	private static void boom(Blast b, Vec3 at, float vol) {
		RandomSource rnd = b.level.getRandom();
		float pitch = (1.0f + (rnd.nextFloat() - rnd.nextFloat()) * 0.2f) * 0.7f;
		for (ServerPlayer pl : b.level.players()) {
			Vec3 pp = pl.getEyePosition();
			double d = pp.distanceTo(at);
			if (d > 512) continue;
			Vec3 s = at;
			if (d > 12) s = pp.add(at.subtract(pp).scale((12 + d * 0.15) / d));
			b.level.playSound(null, s.x, s.y, s.z, SoundEvents.GENERIC_EXPLODE, SoundSource.BLOCKS, 4.0f * vol, pitch);
		}
	}

	private static void cell(Job j, int cell, BlockPos.MutableBlockPos p) {
		p.set(j.ox + cell % j.sx, j.oy + cell / (j.sx * j.sz), j.oz + (cell / j.sx) % j.sz);
	}

	// ------------------------------------------------------------------ canlilara etki (dalga ulasinca, vanilla formulu)
	record Hit(UUID id, Vec3 center, double arrival, int count) {}

	private static List<Hit> collectHits(Blast b) {
		List<Hit> out = new ArrayList<>();
		int[] bb = b.tnt.bounds();
		AABB box = new AABB(bb[0], bb[1], bb[2], bb[3] + 1, bb[4] + 1, bb[5] + 1).inflate(8.5);
		Vec3 ign = Vec3.atCenterOf(b.ignition);
		for (Entity e : b.level.getEntities((Entity) null, box, Entity::isAlive)) {
			Vec3 ep = e.position();
			int ex = (int) Math.floor(ep.x), ey = (int) Math.floor(ep.y), ez = (int) Math.floor(ep.z);
			double best = Double.MAX_VALUE;
			int bx = 0, by = 0, bz = 0, count = 0;
			for (int y = ey - 8; y <= ey + 8; y++) {
				for (int z = ez - 8; z <= ez + 8; z++) {
					for (int x = ex - 8; x <= ex + 8; x++) {
						if (!b.tnt.get(x, y, z)) continue;
						double dx = x + 0.5 - ep.x, dy = y + 0.06 - ep.y, dz = z + 0.5 - ep.z;
						double d2 = dx * dx + dy * dy + dz * dz;
						if (d2 > 64) continue;
						count++;
						if (d2 < best) {
							best = d2;
							bx = x;
							by = y;
							bz = z;
						}
					}
				}
			}
			if (count == 0) continue;
			Vec3 c = new Vec3(bx + 0.5, by + 0.06, bz + 0.5);
			out.add(new Hit(e.getUUID(), c, c.distanceTo(ign) + 2.0, count));
		}
		out.sort((a, c) -> Double.compare(a.arrival, c.arrival));
		return out;
	}

	/** Dalga cephesinin gectigi canlilara hasar + itme. flush: is bitti, kalanlarin hepsi. */
	static void hits(Job j, boolean flush) {
		Blast b = j.blast;
		if (b == null || b.hits == null || b.dist == null) return;
		double front = flush ? Double.MAX_VALUE : (j.cursor > 0 ? b.dist[Math.min(j.cursor, b.dist.length) - 1] : 0);
		while (b.hitCursor < b.hits.size() && b.hits.get(b.hitCursor).arrival <= front) {
			Hit h = b.hits.get(b.hitCursor++);
			Entity e = b.level.getEntity(h.id());
			if (e == null || !e.isAlive()) continue;
			try {
				hurt(b.level, e, h);
			} catch (Exception ex) {
				UstaMod.LOG.warn("Patlama varlik etkisi uygulanamadi: {}", e, ex);
			}
		}
	}

	private static void hurt(ServerLevel level, Entity e, Hit h) {
		Vec3 center = h.center();
		ServerExplosion ex = new ServerExplosion(level, null, null, null, center, 4.0f, false, Explosion.BlockInteraction.DESTROY_WITH_DECAY);
		if (e.ignoreExplosion(ex)) return;
		double dist = Math.sqrt(e.distanceToSqr(center)) / 8.0;
		if (dist > 1.0) return;
		float exposure = ServerExplosion.getSeenPercent(center, e);
		// ayni anda cevresinde patlayan TNT sayisi kadar guclenir (vanilla'da art arda vuruslar); sinirli
		float stack = Math.min(3f, 1f + h.count() / 40f);
		if (CALC.shouldDamageEntity(ex, e)) e.hurtServer(level, ex.getDamageSource(), CALC.getEntityDamageAmount(ex, e, exposure) * stack);
		double kbRes = e instanceof LivingEntity le ? le.getAttributeValue(Attributes.EXPLOSION_KNOCKBACK_RESISTANCE) : 0.0;
		double kb = (1.0 - dist) * exposure * CALC.getKnockbackMultiplier(e) * (1.0 - kbRes) * Math.min(2.0, stack);
		Vec3 origin = e instanceof PrimedTnt ? e.position() : e.getEyePosition();
		Vec3 dir = origin.subtract(center);
		if (dir.lengthSqr() > 1.0E-6) {
			e.pushFromExplosion(dir.normalize().scale(kb));
			e.needsSync = true;
		}
		e.onExplosionHit(null);
	}

	// ------------------------------------------------------------------ krater kenari (yerlestirme bitince)
	private static final Direction[] DIRS = Direction.values();

	/** Kraterin komsularina vanilla sekil guncellemesi: havada kalan mesale duser, kum/cakil duser, su akar. true = bitti. */
	static boolean shell(Job j) {
		Blast b = j.blast;
		if (b == null || j.idx == null) return true;
		if (b.member == null) {
			b.member = new BitSet(j.sx * j.sy * j.sz);
			for (int k = 0; k < j.n; k++) b.member.set(j.idx[k]);
		}
		long t0 = System.nanoTime();
		BlockPos.MutableBlockPos q = new BlockPos.MutableBlockPos();
		while (b.shellCursor < j.n) {
			int k = b.shellCursor++;
			int cell = j.idx[k];
			int x = cell % j.sx, z = (cell / j.sx) % j.sz, y = cell / (j.sx * j.sz);
			for (Direction d : DIRS) {
				int nx = x + d.getStepX(), ny = y + d.getStepY(), nz = z + d.getStepZ();
				if (nx >= 0 && ny >= 0 && nz >= 0 && nx < j.sx && ny < j.sy && nz < j.sz && b.member.get((ny * j.sz + nz) * j.sx + nx)) continue;
				q.set(j.ox + nx, j.oy + ny, j.oz + nz);
				if (!j.level.isInWorldBounds(q)) continue;
				BlockState st = j.level.getBlockState(q);
				if (st.isAir()) continue;
				BlockPos qi = q.immutable(); // planlanan tik konumu saklar
				BlockState upd = Block.updateFromNeighbourShapes(st, j.level, qi);
				if (upd != st) j.level.setBlock(qi, upd, Block.UPDATE_ALL);
			}
			if ((k & 255) == 0 && System.nanoTime() - t0 > 20_000_000L) return false;
		}
		return true;
	}

	static void onFinished(Job j) {
		Blast b = j.blast;
		if (b != null) {
			if (j.state == Job.State.DONE) hits(j, true);
			ACTIVE.remove(b);
		}
	}

	// ------------------------------------------------------------------ veri yapilari
	static final class Blast {
		final Usta u;
		final ServerLevel level;
		final BlockPos ignition;
		final int startTick;
		Bits tnt;
		Bfs bfs;
		Snap snap;
		CompletableFuture<Result> future;
		int rounds;
		int sweeps;
		boolean truncated;
		boolean boomed;
		double bfsMs, snapshotMs, computeMs;
		Job job;
		float[] dist;
		float speed;
		List<Hit> hits;
		int hitCursor;
		int shellCursor;
		BitSet member;

		Blast(Usta u, ServerLevel level, BlockPos ignition, Bits tnt, int startTick) {
			this.u = u;
			this.level = level;
			this.ignition = ignition;
			this.tnt = tnt;
			this.startTick = startTick;
		}
	}

	/** 16^3 bolumlere ayrilmis seyrek bit kumesi (konum basina 1 bit). */
	static final class Bits {
		private final Long2ObjectOpenHashMap<long[]> map = new Long2ObjectOpenHashMap<>();
		private long lastKey = Long.MIN_VALUE;
		private long[] last;
		int count;

		interface Visitor {
			void at(int x, int y, int z);
		}

		static int bit(int x, int y, int z) {
			return ((y & 15) << 8) | ((z & 15) << 4) | (x & 15);
		}

		private long[] sec(int x, int y, int z, boolean create) {
			long key = SectionPos.asLong(x >> 4, y >> 4, z >> 4);
			if (key == lastKey) return last;
			long[] s = map.get(key);
			if (s == null) {
				if (!create) return null;
				s = new long[64];
				map.put(key, s);
			}
			lastKey = key;
			last = s;
			return s;
		}

		boolean get(int x, int y, int z) {
			long[] s = sec(x, y, z, false);
			if (s == null) return false;
			int i = bit(x, y, z);
			return (s[i >>> 6] & (1L << i)) != 0;
		}

		boolean add(int x, int y, int z) {
			long[] s = sec(x, y, z, true);
			int i = bit(x, y, z);
			long m = 1L << i;
			if ((s[i >>> 6] & m) != 0) return false;
			s[i >>> 6] |= m;
			count++;
			return true;
		}

		void forEach(Visitor v) {
			for (var e : map.long2ObjectEntrySet()) {
				long key = e.getLongKey();
				int bx = SectionPos.x(key) << 4, by = SectionPos.y(key) << 4, bz = SectionPos.z(key) << 4;
				long[] s = e.getValue();
				for (int w = 0; w < 64; w++) {
					long word = s[w];
					while (word != 0) {
						int t = Long.numberOfTrailingZeros(word);
						word &= word - 1;
						int i = (w << 6) | t;
						v.at(bx + (i & 15), by + (i >> 8), bz + ((i >> 4) & 15));
					}
				}
			}
		}

		/** {minX, minY, minZ, maxX, maxY, maxZ} */
		int[] bounds() {
			int[] b = {Integer.MAX_VALUE, Integer.MAX_VALUE, Integer.MAX_VALUE, Integer.MIN_VALUE, Integer.MIN_VALUE, Integer.MIN_VALUE};
			forEach((x, y, z) -> {
				if (x < b[0]) b[0] = x;
				if (y < b[1]) b[1] = y;
				if (z < b[2]) b[2] = z;
				if (x > b[3]) b[3] = x;
				if (y > b[4]) b[4] = y;
				if (z > b[5]) b[5] = z;
			});
			return b;
		}
	}

	/** Dunyadaki TNT'ler, bolum bolum (bolum paletinde TNT yoksa hic taranmaz); yuklu olmayan ve korunan yer TNT sayilmaz. */
	static final class TntMap {
		private static final long[] NONE = new long[64];
		private final ServerLevel level;
		private final Usta u;
		private final String dim;
		private final boolean anyProt;
		private final int minY, maxY;
		private final Long2ObjectOpenHashMap<long[]> cache = new Long2ObjectOpenHashMap<>();
		private long lastKey = Long.MIN_VALUE;
		private long[] last;

		TntMap(Usta u, ServerLevel level) {
			this.u = u;
			this.level = level;
			this.dim = level.dimension().identifier().toString();
			this.anyProt = !u.protection.all().isEmpty();
			this.minY = level.getMinY();
			this.maxY = level.getMaxY();
		}

		boolean tnt(int x, int y, int z) {
			if (y < minY || y > maxY) return false;
			long key = SectionPos.asLong(x >> 4, y >> 4, z >> 4);
			long[] s;
			if (key == lastKey) {
				s = last;
			} else {
				s = cache.get(key);
				if (s == null) {
					s = load(x >> 4, y >> 4, z >> 4);
					cache.put(key, s);
				}
				lastKey = key;
				last = s;
			}
			if (s == NONE) return false;
			int i = Bits.bit(x, y, z);
			if ((s[i >>> 6] & (1L << i)) == 0) return false;
			return !anyProt || !u.protection.isProtected(dim, x, y, z);
		}

		private long[] load(int cx, int cy, int cz) {
			LevelChunk ch = level.getChunkSource().getChunkNow(cx, cz);
			if (ch == null) return NONE;
			LevelChunkSection[] secs = ch.getSections();
			int si = ch.getSectionIndexFromSectionY(cy);
			if (si < 0 || si >= secs.length) return NONE;
			LevelChunkSection sec = secs[si];
			if (sec == null || sec.hasOnlyAir() || !sec.maybeHas(IS_TNT)) return NONE;
			long[] b = new long[64];
			boolean any = false;
			for (int i = 0; i < 4096; i++) {
				if (IS_TNT.test(sec.getBlockState(i & 15, i >> 8, (i >> 4) & 15))) {
					b[i >>> 6] |= 1L << i;
					any = true;
				}
			}
			return any ? b : NONE;
		}
	}
}
