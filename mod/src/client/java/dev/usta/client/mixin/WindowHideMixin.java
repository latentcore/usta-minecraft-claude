package dev.usta.client.mixin;

import com.mojang.blaze3d.platform.Window;
import org.lwjgl.sdl.SDLVideo;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/**
 * Yalniz gelistirme/test calistirmalarinda (-Dusta.dev.hiddenWindow=true) oyun penceresini
 * gizli olusturur: test istemcisi kullanicinin ekranini kaplamaz, odagi calmaz (K4).
 * Oyun kendi cizim hedefine (RenderTarget) cizmeye devam eder; ekran goruntusu oradan alinir.
 * Uretim kurulumunda bu ozellik tanimli olmadigi icin hicbir etkisi yoktur.
 */
@Mixin(Window.class)
public abstract class WindowHideMixin {
	@ModifyArg(
		method = "createWindow",
		at = @At(value = "INVOKE", target = "Lcom/mojang/renderpearl/api/device/GpuBackend;createWindow(Ljava/lang/String;IIJ)J"),
		index = 3
	)
	private long usta$hideWindowInDev(long flags) {
		if (Boolean.getBoolean("usta.dev.hiddenWindow")) {
			return flags | SDLVideo.SDL_WINDOW_HIDDEN;
		}
		return flags;
	}
}
