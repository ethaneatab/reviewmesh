package dev.reviewmesh.routing;

import java.util.Map;
import org.springframework.stereotype.Component;

/** The original routing: a fixed table from document type to queue, priority from the risk score. */
@Component
public class RuleEngineV1 {
    static final Map<String, String> QUEUE_BY_TYPE = Map.of(
            "invoice", "finance", "contract", "legal", "claim", "claims", "kyc", "compliance");

    // @learn:routing-v1
    public Route route(DecisionRequest r) {
        if (!r.validation().passed()) {
            return new Route("corrections", 2, "validation failed: " + String.join("; ", r.validation().issues()));
        }
        String queue = QUEUE_BY_TYPE.getOrDefault(r.docType(), "manual-triage");
        int priority = r.riskScore() >= 70 ? 1 : (r.riskScore() >= 30 ? 2 : 3);
        return new Route(queue, priority, "v1 table: " + r.docType() + " -> " + queue + ", risk " + r.riskScore());
    }
    // @learn:end routing-v1
}
