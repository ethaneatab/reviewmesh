package dev.reviewmesh.rollout;

import java.sql.Timestamp;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Feature flag "routing-v2": its traffic share lives in Postgres, its outcomes in memory. */
@Service
public class RolloutService {
    public static final String FLAG = "routing-v2";
    private static final Logger log = LoggerFactory.getLogger(RolloutService.class);
    private final JdbcTemplate db;
    private final RolloutPolicy policy;
    private final OutcomeWindow window = new OutcomeWindow(180_000);
    private volatile Map<String, Object> cached;
    private volatile long cachedAt;

    public RolloutService(JdbcTemplate db,
                          @Value("${reviewmesh.rollout.threshold:0.05}") double threshold,
                          @Value("${reviewmesh.rollout.min-samples:5}") int minSamples,
                          @Value("${reviewmesh.rollout.window-ms:10000}") long windowMs,
                          @Value("${reviewmesh.rollout.hold-ms:10000}") long holdMs) {
        this.db = db;
        this.policy = new RolloutPolicy(new RolloutPolicy.Config(threshold, minSamples, windowMs, holdMs));
    }

    /** Read on every routing call; cached for 200 ms so the hot path does not hit Postgres each time. */
    Map<String, Object> state() {
        long now = System.currentTimeMillis();
        Map<String, Object> s = cached;
        if (s == null || now - cachedAt > 200) {
            s = db.queryForMap("SELECT flag, percent, status, stage_since, fault_rate FROM rollout_state WHERE flag = ?", FLAG);
            cached = s;
            cachedAt = now;
        }
        return s;
    }

    private void invalidate() {
        cached = null;
    }

    public boolean useV2(String recordId) {
        return RolloutPolicy.bucket(recordId) < ((Number) state().get("percent")).intValue();
    }

    /** Fault injection for the drill: the new engine throws on this share of calls. */
    public boolean shouldFail() {
        double rate = ((Number) state().get("fault_rate")).doubleValue();
        return rate > 0 && ThreadLocalRandom.current().nextDouble() < rate;
    }

    public void record(String engine, boolean ok) {
        window.add(System.currentTimeMillis(), engine, ok);
    }

    // @learn:rollout-tick
    @Scheduled(fixedDelay = 500)
    @Transactional
    public void tick() {
        Map<String, Object> s = db.queryForMap("SELECT percent, status, stage_since FROM rollout_state WHERE flag = ? FOR UPDATE", FLAG);
        long now = System.currentTimeMillis();
        int pct = ((Number) s.get("percent")).intValue();
        OutcomeWindow.Stats v2 = window.stats(now, policy.config().windowMs(), "v2");
        RolloutPolicy.Action a = policy.tick((String) s.get("status"), pct, ((Timestamp) s.get("stage_since")).getTime(), v2, now);
        if (a instanceof RolloutPolicy.Rollback r) {
            db.update("UPDATE rollout_state SET percent = 0, status = 'ROLLED_BACK', stage_since = now(), updated_at = now() WHERE flag = ?", FLAG);
            event("ROLLBACK", pct, 0, r.reason(), r.errorRate(), r.samples());
            log.warn("automatic rollback of {}: {}", FLAG, r.reason());
            invalidate();
        } else if (a instanceof RolloutPolicy.Advance adv) {
            db.update("UPDATE rollout_state SET percent = ?, status = ?, stage_since = now(), updated_at = now() WHERE flag = ?",
                    adv.to(), adv.to() == 100 ? "COMPLETE" : "RAMPING", FLAG);
            event("ADVANCE", pct, adv.to(), adv.reason(), v2.errorRate(), v2.samples());
            invalidate();
        }
    }
    // @learn:end rollout-tick

    private void event(String kind, Integer from, Integer to, String reason, Double rate, Integer n) {
        db.update("INSERT INTO rollout_events(flag, kind, from_pct, to_pct, reason, error_rate, samples) VALUES (?,?,?,?,?,?,?)",
                FLAG, kind, from, to, reason, rate, n);
    }

    @Transactional
    public void start(String who) {
        int pct = ((Number) state().get("percent")).intValue();
        db.update("UPDATE rollout_state SET percent = 1, status = 'RAMPING', stage_since = now(), updated_at = now() WHERE flag = ?", FLAG);
        event("START", pct, 1, "started by " + who, null, null);
        invalidate();
    }

    @Transactional
    public void advance(String who) {
        int pct = ((Number) state().get("percent")).intValue();
        int i = RolloutPolicy.STAGES.indexOf(pct);
        int to = i >= 0 && i + 1 < RolloutPolicy.STAGES.size() ? RolloutPolicy.STAGES.get(i + 1) : pct;
        db.update("UPDATE rollout_state SET percent = ?, status = ?, stage_since = now(), updated_at = now() WHERE flag = ?",
                to, to == 100 ? "COMPLETE" : "RAMPING", FLAG);
        event("ADVANCE", pct, to, "manual advance by " + who, null, null);
        invalidate();
    }

    @Transactional
    public void fault(double rate, String who) {
        db.update("UPDATE rollout_state SET fault_rate = ?, updated_at = now() WHERE flag = ?", rate, FLAG);
        event("FAULT", null, null, String.format(java.util.Locale.ROOT, "fault injection set to %.0f%% by %s", rate * 100, who), rate, null);
        invalidate();
    }

    @Transactional
    public void reset(String who) {
        int pct = ((Number) state().get("percent")).intValue();
        db.update("UPDATE rollout_state SET percent = 0, status = 'IDLE', fault_rate = 0, stage_since = now(), updated_at = now() WHERE flag = ?", FLAG);
        event("RESET", pct, 0, "reset by " + who, null, null);
        invalidate();
    }

    public Map<String, Object> view() {
        long now = System.currentTimeMillis();
        Map<String, Object> out = new LinkedHashMap<>(db.queryForMap(
                "SELECT flag, percent, status, stage_since, fault_rate, updated_at FROM rollout_state WHERE flag = ?", FLAG));
        OutcomeWindow.Stats v2 = window.stats(now, policy.config().windowMs(), "v2");
        out.put("window", Map.of("samples", v2.samples(), "errors", v2.errors(), "error_rate", v2.errorRate(),
                "seconds", policy.config().windowMs() / 1000));
        out.put("config", Map.of("threshold", policy.config().threshold(), "min_samples", policy.config().minSamples(),
                "hold_seconds", policy.config().holdMs() / 1000, "stages", RolloutPolicy.STAGES));
        out.put("series", window.series(now, 90));
        List<Map<String, Object>> events = db.queryForList("SELECT id, kind, from_pct, to_pct, reason, error_rate, samples, at"
                + " FROM rollout_events WHERE flag = ? ORDER BY id DESC LIMIT 30", FLAG);
        out.put("events", events);
        return out;
    }
}
