package dev.usta.mixin;

import dev.usta.engine.MassExplosion;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.Explosion;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.TntBlock;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Buyuk TNT kumeleri icin toplu patlama (bkz. MassExplosion). Tum atesleme yollari (kizilatas, cakmak, yanan ok,
 * ates, kirilan dengesiz TNT) prime(Level, BlockPos, LivingEntity, ItemStack)'e; yakin patlamanin zinciri wasExploded'a
 * ugrar. Kucuk kumelerde ikisi de dokunulmadan vanilla calisir.
 */
@Mixin(TntBlock.class)
public abstract class TntBlockMixin {
	@Inject(method = "prime(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/entity/LivingEntity;Lnet/minecraft/world/item/ItemStack;)Z",
		at = @At("HEAD"), cancellable = true)
	private static void usta$massPrime(Level level, BlockPos pos, LivingEntity source, ItemStack itemStack, CallbackInfoReturnable<Boolean> cir) {
		if (level instanceof ServerLevel sl && MassExplosion.onPrime(sl, pos)) cir.setReturnValue(false);
	}

	@Inject(method = "wasExploded", at = @At("HEAD"), cancellable = true)
	private void usta$massChain(ServerLevel level, BlockPos pos, Explosion explosion, CallbackInfo ci) {
		if (MassExplosion.onExploded(level, pos)) ci.cancel();
	}
}
