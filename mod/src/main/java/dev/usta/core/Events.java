package dev.usta.core;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.util.ArrayDeque;
import java.util.Deque;

/** Olay halkasi: uzun yoklama (long-poll) ile koprunun ve panelin izledigi olaylar. */
public final class Events {
	private final Deque<JsonObject> ring = new ArrayDeque<>();
	private long seq = 0;
	private static final int MAX = 2000;

	public synchronized long publish(String type, JsonObject data) {
		JsonObject e = new JsonObject();
		e.addProperty("seq", ++seq);
		e.addProperty("type", type);
		e.addProperty("t", System.currentTimeMillis());
		e.add("data", data == null ? new JsonObject() : data);
		ring.addLast(e);
		while (ring.size() > MAX) ring.removeFirst();
		notifyAll();
		return seq;
	}

	public synchronized long lastSeq() {
		return seq;
	}

	/** since'ten sonraki olaylar; yoksa waitMs kadar bekler. */
	public synchronized JsonObject poll(long since, long waitMs) {
		long deadline = System.currentTimeMillis() + Math.max(0, waitMs);
		while (seq <= since) {
			long left = deadline - System.currentTimeMillis();
			if (left <= 0) break;
			try {
				wait(left);
			} catch (InterruptedException e) {
				Thread.currentThread().interrupt();
				break;
			}
		}
		JsonArray arr = new JsonArray();
		for (JsonObject e : ring) {
			if (e.get("seq").getAsLong() > since) arr.add(e);
		}
		JsonObject res = new JsonObject();
		res.addProperty("last", seq);
		res.add("events", arr);
		return res;
	}
}
