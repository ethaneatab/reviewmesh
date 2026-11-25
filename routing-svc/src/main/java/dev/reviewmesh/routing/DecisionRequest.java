package dev.reviewmesh.routing;

import java.util.List;

/** Contract: contracts/routing-decision.v1.json (request). Fields are snake_case on the wire. */
public record DecisionRequest(String recordId, int seq, String docType, String title, int riskScore,
                              Validation validation, int attempt, String traceId) {
    public record Validation(boolean passed, List<String> issues) {}

    public void check() {
        if (recordId == null || recordId.isBlank() || docType == null || validation == null || seq < 1) {
            throw new IllegalArgumentException("record_id, seq, doc_type and validation are required");
        }
    }
}
