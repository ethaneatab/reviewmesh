package dev.reviewmesh.review;

import java.util.List;

/** Contract: contracts/handoff.v1.json. Produced by the Python worker, consumed here from SQS rm-handoff. */
public record HandoffMessage(String schema, String recordId, int seq, String decisionId, String queue, int priority,
                             String engine, String title, String docType, String s3Key, String traceId, String worker,
                             int riskScore, Validation validation) {
    public record Validation(boolean passed, List<String> issues) {}

    public void check() {
        if (!"handoff.v1".equals(schema) || recordId == null || seq < 1 || queue == null) {
            throw new IllegalArgumentException("not a handoff.v1 message");
        }
    }
}
