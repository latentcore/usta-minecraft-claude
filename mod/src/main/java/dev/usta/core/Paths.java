package dev.usta.core;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclEntryPermission;
import java.nio.file.attribute.AclEntryType;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.UserPrincipal;
import java.security.MessageDigest;
import java.util.EnumSet;
import java.util.HexFormat;
import java.util.List;
import net.fabricmc.loader.api.FabricLoader;

/** Modun verisi: oyun klasoru/usta altinda; dunya klasorune hicbir sey yazilmaz (S3). */
public final class Paths {
	private Paths() {}

	public static Path gameDir() {
		return FabricLoader.getInstance().getGameDir();
	}

	public static Path root() {
		return gameDir().resolve("usta");
	}

	public static Path runtime() {
		return root().resolve("runtime");
	}

	public static Path cache() {
		return root().resolve("cache");
	}

	public static Path backups() {
		return root().resolve("yedekler");
	}

	public static Path library() {
		return root().resolve("kutuphane");
	}

	public static Path logs() {
		return root().resolve("logs");
	}

	public static Path worlds() {
		return root().resolve("worlds");
	}

	public static Path agentWork() {
		return root().resolve("agent");
	}

	public static Path world(String key) {
		return worlds().resolve(key);
	}

	public static Path ensure(Path p) {
		try {
			Files.createDirectories(p);
		} catch (IOException e) {
			throw new RuntimeException(e);
		}
		return p;
	}

	/** Dunya anahtari: klasor adi (ASCII'ye indirgenmis) + tohumun kisa ozeti. */
	public static String worldKey(String folderName, long seed) {
		String safe = folderName.replaceAll("[^A-Za-z0-9_.-]", "_");
		if (safe.length() > 48) safe = safe.substring(0, 48);
		try {
			MessageDigest md = MessageDigest.getInstance("SHA-256");
			byte[] h = md.digest((folderName + "|" + seed).getBytes(StandardCharsets.UTF_8));
			return safe + "-" + HexFormat.of().formatHex(h, 0, 4);
		} catch (Exception e) {
			return safe;
		}
	}

	/** Atomik metin yazimi (once gecici dosya, sonra yer degistirme). */
	public static void writeAtomic(Path file, byte[] data) throws IOException {
		Files.createDirectories(file.getParent());
		Path tmp = file.resolveSibling(file.getFileName() + ".tmp");
		Files.write(tmp, data, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
		Files.move(tmp, file, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
	}

	public static void writeAtomic(Path file, String text) throws IOException {
		writeAtomic(file, text.getBytes(StandardCharsets.UTF_8));
	}

	/** Dosyayi yalniz bu Windows kullanicisinin okuyabilecegi hale getirir (M4). Basarisizsa false. */
	public static boolean restrictToOwner(Path file) {
		try {
			AclFileAttributeView view = Files.getFileAttributeView(file, AclFileAttributeView.class);
			if (view == null) return false;
			UserPrincipal owner = Files.getOwner(file);
			AclEntry entry = AclEntry.newBuilder()
				.setType(AclEntryType.ALLOW)
				.setPrincipal(owner)
				.setPermissions(EnumSet.allOf(AclEntryPermission.class))
				.build();
			view.setAcl(List.of(entry));
			return true;
		} catch (Exception e) {
			return false;
		}
	}
}
