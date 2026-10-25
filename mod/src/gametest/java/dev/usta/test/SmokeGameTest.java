package dev.usta.test;

import net.fabricmc.fabric.api.gametest.v1.GameTest;
import net.minecraft.core.BlockPos;
import net.minecraft.gametest.framework.GameTestHelper;
import net.minecraft.world.level.block.Blocks;

public class SmokeGameTest {
	@GameTest
	public void placesStone(GameTestHelper helper) {
		helper.setBlock(new BlockPos(1, 1, 1), Blocks.STONE);
		helper.assertBlockPresent(Blocks.STONE, 1, 1, 1);
		helper.succeed();
	}
}
