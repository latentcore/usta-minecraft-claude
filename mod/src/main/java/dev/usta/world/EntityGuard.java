package dev.usta.world;

import dev.usta.engine.Job;
import dev.usta.game.Chat;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.ExperienceOrb;
import net.minecraft.world.entity.OwnableEntity;
import net.minecraft.world.entity.TamableAnimal;
import net.minecraft.world.entity.animal.allay.Allay;
import net.minecraft.world.entity.animal.equine.AbstractHorse;
import net.minecraft.world.entity.animal.golem.IronGolem;
import net.minecraft.world.entity.animal.golem.SnowGolem;
import net.minecraft.world.entity.decoration.ArmorStand;
import net.minecraft.world.entity.decoration.HangingEntity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.npc.villager.AbstractVillager;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

/** Oyuncu, evcil, adli ve koylu varliklara zarar verilmez; insa alanindaysa guvenli noktaya tasinir (M2). */
public final class EntityGuard {
	private EntityGuard() {}

	public static String tag(Entity e) {
		if (e instanceof Player) return "oyuncu";
		if (e instanceof AbstractVillager) return "köylü";
		if (e instanceof TamableAnimal t && t.isTame()) return "evcil";
		if (e instanceof AbstractHorse h && h.isTamed()) return "evcil";
		if (e instanceof OwnableEntity o && o.getOwnerReference() != null) return "evcil";
		if (e.hasCustomName()) return "adlı";
		if (e instanceof IronGolem || e instanceof SnowGolem || e instanceof Allay) return "yardımcı";
		return null;
	}

	public static boolean isProtected(Entity e) {
		return tag(e) != null;
	}

	/** Insa basinda: hedef hucresi kati olacak varliklari disari tasir. */
	public static void protect(Job j) {
		ServerLevel level = j.level;
		AABB box = new AABB(j.ox, j.oy, j.oz, j.ox + j.sx, j.oy + j.sy, j.oz + j.sz).inflate(0.5);
		List<Entity> ents = level.getEntities((Entity) null, box, e -> e.isAlive() && !(e instanceof ItemEntity)
			&& !(e instanceof ExperienceOrb) && !(e instanceof HangingEntity) && !(e instanceof ArmorStand));
		if (ents.isEmpty()) return;
		Map<Integer, BlockState> lookup = null;
		for (Entity e : ents) {
			BlockPos feet = e.blockPosition();
			BlockPos head = BlockPos.containing(e.getEyePosition());
			if (lookup == null && j.planCells == null) lookup = buildLookup(j);
			if (!solidTarget(j, lookup, feet) && !solidTarget(j, lookup, head)) continue;
			double[] dst = safeSpot(j, e);
			j.moved.add(new Job.Moved(e.getUUID(), e.getX(), e.getY(), e.getZ(), e.getYRot(), e.getXRot(), dst[0], dst[1], dst[2]));
			if (e instanceof ServerPlayer sp) {
				sp.teleportTo(level, dst[0], dst[1], dst[2], Set.of(), sp.getYRot(), sp.getXRot(), false);
				sp.sendSystemMessage(Chat.soft("İnşa alanının içindeydin; seni güvenli bir noktaya aldım."));
			} else {
				e.teleportTo(dst[0], dst[1], dst[2]);
				String t = tag(e);
				if (t != null) {
					Chat.toAll(level.getServer(), Chat.soft(t.substring(0, 1).toUpperCase() + t.substring(1) + " bir canlıyı ("
						+ e.getName().getString() + ") inşa alanından güvenle çıkardım."));
				}
			}
		}
	}

	private static Map<Integer, BlockState> buildLookup(Job j) {
		Map<Integer, BlockState> m = new HashMap<>();
		if (j.n > 3_000_000) return m;
		for (int k = 0; k < j.n; k++) m.put(j.idx[k], j.target[k]);
		return m;
	}

	private static boolean solidTarget(Job j, Map<Integer, BlockState> lookup, BlockPos p) {
		int x = p.getX() - j.ox, y = p.getY() - j.oy, z = p.getZ() - j.oz;
		if (x < 0 || y < 0 || z < 0 || x >= j.sx || y >= j.sy || z >= j.sz) return false;
		int cell = (y * j.sz + z) * j.sx + x;
		BlockState t;
		if (j.planCells != null) {
			int v = j.planCells[cell];
			if (v <= 1) return false;
			t = j.planPalette[v];
		} else {
			t = lookup.get(cell);
		}
		return t != null && !t.isAir() && !t.getCollisionShape(j.level, p).isEmpty();
	}

	private static double[] safeSpot(Job j, Entity e) {
		double ex = e.getX(), ez = e.getZ();
		double dW = ex - j.ox, dE = j.ox + j.sx - ex, dN = ez - j.oz, dS = j.oz + j.sz - ez;
		double m = Math.min(Math.min(dW, dE), Math.min(dN, dS));
		double tx = ex, tz = ez;
		if (m == dW) tx = j.ox - 2.5;
		else if (m == dE) tx = j.ox + j.sx + 2.5;
		else if (m == dN) tz = j.oz - 2.5;
		else tz = j.oz + j.sz + 2.5;
		int y = j.level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES, (int) Math.floor(tx), (int) Math.floor(tz));
		return new double[]{Math.floor(tx) + 0.5, y, Math.floor(tz) + 0.5};
	}

	/** Geri almada: olusturulan varliklari kaldir, tasinanlari geri koy. */
	public static void undoEntities(Job j) {
		ServerLevel level = j.level;
		for (UUID id : j.removeEntities) {
			Entity e = level.getEntity(id);
			if (e != null) e.discard();
		}
		for (Job.Moved m : j.moveBack) {
			Entity e = level.getEntity(m.id());
			if (e == null || e instanceof ServerPlayer) continue; // oyuncuyu geri almada tasimayiz
			if (e.distanceToSqr(m.nx(), m.ny(), m.nz()) < 16 * 16) e.teleportTo(m.x(), m.y(), m.z());
		}
	}
}
