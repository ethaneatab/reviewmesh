package dev.reviewmesh.rollout;

import dev.reviewmesh.common.Lab;
import java.util.List;
import java.util.Locale;

/**
 * The rollout decision, as a pure function so it can be tested with a fake clock.
 * Each tick looks at the new engine's error rate over the last {@code windowMs}:
 * above the threshold (with enough samples) -> back to 0 %; healthy for {@code holdMs} -> next stage.
 */
public class RolloutPolicy {
    public static final List<Integer> STAGES = List.of(1, 10, 50, 100);

    public record Config(double threshold, int minSamples, long windowMs, long holdMs) {}

    public sealed interface Action permits None, Advance, Rollback {}

    public record None() implements Action {}

    public record Advance(int to, String reason) implements Action {}

    public record Rollback(String reason, double errorRate, int samples) implements Action {}

    private final Config cfg;

    public RolloutPolicy(Config cfg) {
        this.cfg = cfg;
    }

    public Config config() {
        return cfg;
    }

    // @learn:rollback-decision
    public Action tick(String status, int percent, long stageSinceMs, OutcomeWindow.Stats v2, long nowMs) {
        if (!"RAMPING".equals(status)) {
            return new None();
        }
        boolean enough = v2.samples() >= cfg.minSamples();
        if (enough && v2.errorRate() > cfg.threshold() && !Lab.sabotaged("no_rollback")) {
            return new Rollback(String.format(Locale.ROOT, "v2 error rate %.1f%% > %.1f%% over the last %ds (n=%d)",
                    100 * v2.errorRate(), 100 * cfg.threshold(), cfg.windowMs() / 1000, v2.samples()),
                    v2.errorRate(), v2.samples());
        }
        if (enough && nowMs - stageSinceMs >= cfg.holdMs() && v2.errorRate() <= cfg.threshold()) {
            int i = STAGES.indexOf(percent);
            if (i >= 0 && i + 1 < STAGES.size()) {
                return new Advance(STAGES.get(i + 1), String.format(Locale.ROOT,
                        "healthy for %ds at %d%%: error rate %.1f%% (n=%d)", cfg.holdMs() / 1000, percent,
                        100 * v2.errorRate(), v2.samples()));
            }
        }
        return new None();
    }
    // @learn:end rollback-decision

    /** Stable bucket 0..99 per record, so one record always sees the same engine during a stage. */
    public static int bucket(String recordId) {
        java.util.zip.CRC32 crc = new java.util.zip.CRC32();
        crc.update(recordId.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        return (int) (crc.getValue() % 100);
    }
}
