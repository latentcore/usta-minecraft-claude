package dev.usta.engine;

import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerBossEvent;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.block.state.BlockState;

/** Bir yerlestirme isi (insa, geri alma ya da yineleme). Yalniz sunucu is parcaciginda degistirilir. */
public final class Job {
	public enum Kind { BUILD, UNDO, REDO }

	public enum State { QUEUED, LOADING, CAPTURING, SAVING, AWAITING_CONFIRM, RUNNING, SETTLING, ENTITIES, DONE, CANCELLED, FAILED }

	public enum Mode {
		INSTANT, WATCH, CINEMATIC;

		public static Mode parse(String s, Mode def) {
			if (s == null) return def;
			return switch (s.toLowerCase()) {
				case "instant", "anlik", "aninda", "anında" -> INSTANT;
				case "cinematic", "sinematik", "yavas", "yavaş" -> CINEMATIC;
				case "watch", "izle", "izlenebilir" -> WATCH;
				default -> def;
			};
		}
	}

	public record Moved(UUID id, double x, double y, double z, float yaw, float pitch, double nx, double ny, double nz) {}

	public final String id;
	public final Kind kind;
	public String label;
	public final ServerLevel level;
	public final int ox, oy, oz, sx, sy, sz;
	public int n;
	/** yalniz BUILD hazirliginda (kalici degil): plan hucreleri ve cozulmus palet */
	public transient int[] planCells;
	public transient BlockState[] planPalette;
	/** yerel hucre indeksleri, yerlestirme sirasinda */
	public int[] idx;
	public BlockState[] target;
	public boolean[] settle;
	public final Map<Integer, CompoundTag> targetBE = new HashMap<>();
	public final List<Plan.EntitySpec> spawn = new ArrayList<>();
	public BlockState[] before;
	public final Map<Integer, CompoundTag> beforeBE = new HashMap<>();
	public final List<UUID> spawned = new ArrayList<>();
	public final List<Moved> moved = new ArrayList<>();
	/** UNDO icin: geri alinirken silinecek varliklar ve geri tasinacaklar */
	public final List<UUID> removeEntities = new ArrayList<>();
	public final List<Moved> moveBack = new ArrayList<>();

	public volatile State state = State.QUEUED;
	public Mode mode = Mode.WATCH;
	public double seconds = 20;
	public int cursor;
	public int captureCursor;
	public int settleCursor;
	public long ticksRunning;
	public long createdAt = System.currentTimeMillis();
	public long startedAt;
	public long finishedAt;
	public String source = "api";
	public String requestId;
	public String refJob; // UNDO/REDO icin hedef is
	public String message;
	public boolean allowModify;
	public boolean allowDangerous;
	public boolean replay; // cokmeden sonra bastan yeniden yerlestirme
	public boolean entitiesWaitStarted;
	// artimli analiz / kayit / destek denetimi (tek tick'i uzatmamak icin)
	public boolean analyzing;
	public int analyzeCursor;
	public int aArtificial, aArtificialRemoved, aNaturalRemoved, aUnchanged, aProtected;
	public java.util.List<int[]> ownBoxes;
	public java.util.concurrent.CompletableFuture<?> saveFuture;
	public int supportCursor = -1;
	public boolean redstoneDone;      // yerlestirme sonrasi kizilatas uyandirma gecisi yapildi mi
	public int redstoneWoke;          // uyandirilan devre ogesi sayisi
	public boolean released;
	public long entitiesWaitUntil;
	public volatile boolean cancelRequested;
	public volatile boolean pauseRequested;
	public volatile boolean confirmed;
	public JsonObject conflicts = new JsonObject();
	public JsonObject meta = new JsonObject();
	public long[] chunkKeys = new long[0];
	public ServerBossEvent bar;
	// olcumler
	public long maxTickNanos;
	public long sumTickNanos;
	public long tickSamples;
	public int unsupported;
	public int settledChanged;
	public int lastJournalCursor;
	public long lastJournalMs;
	// toplu patlama (MassExplosion): fitil, sok dalgasi sirasi, efektler; kalici degil
	public boolean explosion;
	public transient int[] waveCursor;
	transient MassExplosion.Blast blast;

	public Job(String id, Kind kind, String label, ServerLevel level, int ox, int oy, int oz, int sx, int sy, int sz, int n) {
		this.id = id;
		this.kind = kind;
		this.label = label;
		this.level = level;
		this.ox = ox;
		this.oy = oy;
		this.oz = oz;
		this.sx = sx;
		this.sy = sy;
		this.sz = sz;
		this.n = n;
	}

	public int lx(int cell) {
		return cell % sx;
	}

	public int lz(int cell) {
		return (cell / sx) % sz;
	}

	public int ly(int cell) {
		return cell / (sx * sz);
	}

	public int effectiveN() {
		return n;
	}

	public boolean finished() {
		return state == State.DONE || state == State.CANCELLED || state == State.FAILED;
	}

	public double progress() {
		return switch (state) {
			case DONE -> 1.0;
			case RUNNING, SETTLING, ENTITIES -> n == 0 ? 1.0 : Math.min(1.0, cursor / (double) n);
			default -> 0.0;
		};
	}
}
