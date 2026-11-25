package dev.reviewmesh.review;

import java.time.OffsetDateTime;

/** What GET /v1/tasks returns. Contract: contracts/task.v1.json, which old clients depend on. */
public record Task(long id, String recordId, int seq, String title, String docType, String s3Key, String queue,
                   int priority, String status, String reviewer, String decisionReason,
                   String traceId, OffsetDateTime createdAt, OffsetDateTime updatedAt) {}
