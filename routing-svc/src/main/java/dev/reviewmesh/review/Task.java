package dev.reviewmesh.review;

import java.time.OffsetDateTime;

/**
 * What GET /v1/tasks returns. contracts/task.v1.json freezes the shape old clients depend on:
 * {@code reviewer} stays (a handle string) in every migration phase; {@code reviewer_id} is additive.
 */
public record Task(long id, String recordId, int seq, String title, String docType, String s3Key, String queue,
                   int priority, String status, String reviewer, Long reviewerId, String decisionReason,
                   String traceId, OffsetDateTime createdAt, OffsetDateTime updatedAt) {}
