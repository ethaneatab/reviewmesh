package dev.reviewmesh;

import static org.assertj.core.api.Assertions.assertThat;

import dev.reviewmesh.rollout.OutcomeWindow;
import dev.reviewmesh.rollout.RolloutPolicy;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;

/** Simulated time: 50 v2 requests per second, a tick every 500 ms, like the real scheduler. */
class RolloutPolicyTest {
    static final long ROLLBACK_DEADLINE_MS = 5_000;
    final RolloutPolicy policy = new RolloutPolicy(new RolloutPolicy.Config(0.05, 5, 10_000, 10_000));

    /** Runs the controller loop; returns the percent after each tick. */
    List<Integer> run(double failRate, long faultFromMs, long untilMs, int startPct) {
        OutcomeWindow w = new OutcomeWindow(60_000);
        Random rnd = new Random(42);
        int pct = startPct;
        String status = "RAMPING";
        long stageSince = 0;
        List<Integer> trace = new ArrayList<>();
        for (long t = 0; t <= untilMs; t += 500) {
            for (int i = 0; i < 25 && pct > 0; i++) {
                boolean fail = t >= faultFromMs && rnd.nextDouble() < failRate;
                w.add(t, "v2", !fail);
            }
            RolloutPolicy.Action a = policy.tick(status, pct, stageSince, w.stats(t, 10_000, "v2"), t);
            if (a instanceof RolloutPolicy.Rollback) {
                pct = 0;
                status = "ROLLED_BACK";
            } else if (a instanceof RolloutPolicy.Advance adv) {
                pct = adv.to();
                stageSince = t;
                status = pct == 100 ? "COMPLETE" : "RAMPING";
            }
            trace.add(pct);
        }
        return trace;
    }

    // @learn:test-rollback
    @Test
    void errorRegressionRollsBackToZeroWithinFiveSeconds() {
        long faultAt = 3_000;
        List<Integer> trace = run(0.30, faultAt, 20_000, 10);
        int firstZero = trace.indexOf(0);
        long rolledBackAt = firstZero * 500L;
        System.out.println(firstZero < 0 ? "fault at " + faultAt + " ms, never rolled back"
                : String.format("fault at %d ms, rolled back at %d ms (%d ms later)", faultAt, rolledBackAt, rolledBackAt - faultAt));
        assertThat(firstZero).as("never rolled back").isGreaterThanOrEqualTo(0);
        assertThat(rolledBackAt - faultAt).isLessThanOrEqualTo(ROLLBACK_DEADLINE_MS);
        assertThat(trace.get(trace.size() - 1)).isZero();
    }
    // @learn:end test-rollback

    @Test
    void healthyRolloutClimbsEveryStage() {
        List<Integer> trace = run(0.0, 0, 45_000, 1);
        assertThat(trace).contains(1, 10, 50, 100);
        assertThat(trace.get(trace.size() - 1)).isEqualTo(100);
    }

    @Test
    void errorsBelowThresholdDoNotRollBack() {
        assertThat(run(0.02, 0, 30_000, 10)).doesNotContain(0);
    }

    @Test
    void bucketsAreStableAndSpread() {
        int under10 = 0;
        for (int i = 0; i < 10_000; i++) {
            if (RolloutPolicy.bucket("rec_" + i) < 10) {
                under10++;
            }
        }
        assertThat(RolloutPolicy.bucket("rec_x")).isEqualTo(RolloutPolicy.bucket("rec_x"));
        assertThat(under10).isBetween(850, 1150);
    }
}
