package dev.reviewmesh.routing;

/** Contract: contracts/routing-decision.v1.json (response). Add fields freely; never rename or drop one. */
public record DecisionResponse(String decisionId, String recordId, int seq, String queue, int priority,
                               String engine, String reason) {}
