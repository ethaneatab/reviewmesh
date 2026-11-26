package dev.reviewmesh.rollout;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Sliding window of routing outcomes, per engine, in millisecond timestamps. Thread-safe. */
public class OutcomeWindow {
    record Outcome(long atMs, String engine, boolean ok) {}

    public record Stats(int samples, int errors) {
        public double errorRate() {
            return samples == 0 ? 0 : (double) errors / samples;
        }
    }

    private final Deque<Outcome> items = new ArrayDeque<>();
    private final long keepMs;

    public OutcomeWindow(long keepMs) {
        this.keepMs = keepMs;
    }

    public synchronized void add(long nowMs, String engine, boolean ok) {
        items.addLast(new Outcome(nowMs, engine, ok));
        while (!items.isEmpty() && items.peekFirst().atMs() < nowMs - keepMs) {
            items.removeFirst();
        }
    }

    /** A new rollout attempt starts with an empty window: the last attempt's errors must not count. */
    public synchronized void clear() {
        items.clear();
    }

    public synchronized Stats stats(long nowMs, long windowMs, String engine) {
        int n = 0;
        int err = 0;
        for (Outcome o : items) {
            if (o.atMs() >= nowMs - windowMs && o.engine().equals(engine)) {
                n++;
                if (!o.ok()) {
                    err++;
                }
            }
        }
        return new Stats(n, err);
    }

    /** One point per second for the console chart. */
    public synchronized List<Map<String, Object>> series(long nowMs, int seconds) {
        long start = (nowMs / 1000 - seconds + 1) * 1000;
        int[][] b = new int[seconds][3];
        for (Outcome o : items) {
            int i = (int) ((o.atMs() - start) / 1000);
            if (i < 0 || i >= seconds) {
                continue;
            }
            if (o.engine().equals("v2")) {
                b[i][0]++;
                if (!o.ok()) {
                    b[i][1]++;
                }
            } else {
                b[i][2]++;
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (int i = 0; i < seconds; i++) {
            Map<String, Object> p = new LinkedHashMap<>();
            p.put("t", start / 1000 + i);
            p.put("v2", b[i][0]);
            p.put("v2_errors", b[i][1]);
            p.put("v1", b[i][2]);
            out.add(p);
        }
        return out;
    }
}
