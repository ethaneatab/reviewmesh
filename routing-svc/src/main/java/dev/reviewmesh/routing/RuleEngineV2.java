package dev.reviewmesh.routing;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * The new routing logic behind the "routing-v2" flag: same queues as v1, but a busy queue overflows
 * into "shared-review", and priority uses finer risk bands. Queue depths are a hot lookup, cached 2 s.
 */
@Component
public class RuleEngineV2 {
    static final int OVERFLOW_AT = 20;
    private final JdbcTemplate db;
    private volatile Map<String, Long> depths = Map.of();
    private volatile long depthsAt;

    public RuleEngineV2(JdbcTemplate db) {
        this.db = db;
    }

    long depth(String queue) {
        long now = System.currentTimeMillis();
        if (now - depthsAt > 2000) {
            Map<String, Long> m = new HashMap<>();
            List<Map<String, Object>> rows = db.queryForList("SELECT queue, count(*) AS n FROM review_tasks WHERE status = 'OPEN' GROUP BY queue");
            for (Map<String, Object> r : rows) {
                m.put((String) r.get("queue"), ((Number) r.get("n")).longValue());
            }
            depths = m;
            depthsAt = now;
        }
        return depths.getOrDefault(queue, 0L);
    }

    // @learn:routing-v2
    public Route route(DecisionRequest r) {
        if (!r.validation().passed()) {
            return new Route("corrections", 2, "v2: validation failed (" + r.validation().issues().size() + " issues)");
        }
        String home = RuleEngineV1.QUEUE_BY_TYPE.getOrDefault(r.docType(), "manual-triage");
        long d = depth(home);
        String queue = d > OVERFLOW_AT ? "shared-review" : home;
        int priority = r.riskScore() >= 70 ? 1 : (r.riskScore() >= 40 ? 2 : 3);
        return new Route(queue, priority, "v2 load-aware: " + home + " has " + d + " open" + (queue.equals(home) ? "" : ", overflow to shared-review"));
    }
    // @learn:end routing-v2
}
