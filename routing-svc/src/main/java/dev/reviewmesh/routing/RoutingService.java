package dev.reviewmesh.routing;

import dev.reviewmesh.audit.AuditRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RoutingService {
    private final JdbcTemplate db;
    private final RuleEngineV1 v1;
    private final AuditRepository audit;

    public RoutingService(JdbcTemplate db, RuleEngineV1 v1, AuditRepository audit) {
        this.db = db;
        this.v1 = v1;
        this.audit = audit;
    }

    /** One decision per (record, seq): a client retry gets the same answer back. */
    static String decisionId(String recordId, int seq) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256").digest((recordId + ":" + seq).getBytes(StandardCharsets.UTF_8));
            return "dec_" + HexFormat.of().formatHex(d, 0, 8);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    protected Chosen choose(DecisionRequest req) {
        return new Chosen("v1", v1.route(req));
    }

    public record Chosen(String engine, Route route) {}

    @Transactional
    public DecisionResponse decide(DecisionRequest req) {
        req.check();
        String id = decisionId(req.recordId(), req.seq());
        List<DecisionResponse> prev = db.query(
                "SELECT decision_id, record_id, seq, queue, priority, engine, reason FROM routing_decisions WHERE decision_id = ?",
                (rs, i) -> new DecisionResponse(rs.getString(1), rs.getString(2), rs.getInt(3), rs.getString(4),
                        rs.getInt(5), rs.getString(6), rs.getString(7)), id);
        if (!prev.isEmpty()) {
            return prev.get(0);
        }
        Chosen c = choose(req);
        int n = db.update("INSERT INTO routing_decisions(decision_id, record_id, seq, engine, queue, priority, reason)"
                        + " VALUES (?,?,?,?,?,?,?) ON CONFLICT (decision_id) DO NOTHING",
                id, req.recordId(), req.seq(), c.engine(), c.route().queue(), c.route().priority(), c.route().reason());
        if (n == 1) {
            audit.append(req.recordId(), req.seq(), null, "ROUTED", "routing:" + c.engine(), null, null,
                    Map.of("decision_id", id, "queue", c.route().queue(), "priority", c.route().priority(),
                            "engine", c.engine(), "reason", c.route().reason(), "trace_id", String.valueOf(req.traceId())));
        }
        return new DecisionResponse(id, req.recordId(), req.seq(), c.route().queue(), c.route().priority(), c.engine(),
                c.route().reason());
    }
}
