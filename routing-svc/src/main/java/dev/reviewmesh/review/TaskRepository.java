package dev.reviewmesh.review;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private final JdbcTemplate db;

    public TaskRepository(JdbcTemplate db) {
        this.db = db;
    }

    private static final String COLS = "t.id, t.record_id, t.seq, t.title, t.doc_type, t.s3_key, t.queue, t.priority,"
            + " t.status, t.reviewer, t.decision_reason, t.trace_id, t.created_at, t.updated_at";

    private Task map(ResultSet rs, int i) throws SQLException {
        return new Task(rs.getLong("id"), rs.getString("record_id"), rs.getInt("seq"), rs.getString("title"),
                rs.getString("doc_type"), rs.getString("s3_key"), rs.getString("queue"), rs.getInt("priority"),
                rs.getString("status"), rs.getString("reviewer"), rs.getString("decision_reason"),
                rs.getString("trace_id"), rs.getObject("created_at", OffsetDateTime.class),
                rs.getObject("updated_at", OffsetDateTime.class));
    }

    /** First time we see (record, seq): true. A redelivered SQS message: false. */
    public boolean markReceived(String recordId, int seq, String messageId) {
        return db.update("INSERT INTO handoff_inbox(record_id, seq, message_id) VALUES (?,?,?) ON CONFLICT DO NOTHING",
                recordId, seq, messageId) == 1;
    }

    // @learn:task-upsert
    /** A newer seq replaces the task; an older seq arriving late changes nothing. */
    public Optional<Task> upsert(HandoffMessage m) {
        List<Long> ids = db.queryForList(
                "INSERT INTO review_tasks(record_id, seq, title, doc_type, s3_key, queue, priority, status, decision_id, trace_id)"
                        + " VALUES (?,?,?,?,?,?,?,'OPEN',?,?)"
                        + " ON CONFLICT (record_id) DO UPDATE SET seq = EXCLUDED.seq, title = EXCLUDED.title,"
                        + " s3_key = EXCLUDED.s3_key, queue = EXCLUDED.queue, priority = EXCLUDED.priority, status = 'OPEN',"
                        + " decision_id = EXCLUDED.decision_id, reviewer = NULL, decision_reason = NULL, updated_at = now()"
                        + " WHERE review_tasks.seq < EXCLUDED.seq RETURNING id",
                Long.class, m.recordId(), m.seq(), m.title(), m.docType(), m.s3Key(), m.queue(), m.priority(),
                m.decisionId(), m.traceId());
        return ids.isEmpty() ? Optional.empty() : get(ids.get(0));
    }
    // @learn:end task-upsert

    public Optional<Task> get(long id) {
        return db.query("SELECT " + COLS + " FROM review_tasks t WHERE t.id = ?", this::map, id).stream().findFirst();
    }

    public Optional<Task> byRecord(String recordId) {
        return db.query("SELECT " + COLS + " FROM review_tasks t WHERE t.record_id = ?", this::map, recordId).stream().findFirst();
    }

    // @learn:queue-query
    public List<Task> list(String queue, String status, int limit) {
        if (queue == null) {
            return db.query("SELECT " + COLS + " FROM review_tasks t WHERE t.status = ? ORDER BY t.priority, t.created_at LIMIT ?",
                    this::map, status, limit);
        }
        return db.query("SELECT " + COLS + " FROM review_tasks t WHERE t.queue = ? AND t.status = ?"
                + " ORDER BY t.priority, t.created_at LIMIT ?", this::map, queue, status, limit);
    }
    // @learn:end queue-query

    /** Conditional update: only one reviewer can win the claim. */
    public boolean claim(long id, String reviewer, String fromStatus) {
        return db.update("UPDATE review_tasks SET status = 'CLAIMED', reviewer = ?, updated_at = now()"
                + " WHERE id = ? AND status = ?", reviewer, id, fromStatus) == 1;
    }

    public boolean decide(long id, String reviewer, String toStatus, String reason) {
        return db.update("UPDATE review_tasks SET status = ?, decision_reason = ?, updated_at = now()"
                + " WHERE id = ? AND status = 'CLAIMED' AND reviewer = ?", toStatus, reason, id, reviewer) == 1;
    }

    public boolean escalate(long id, String reviewer, String reason) {
        return db.update("UPDATE review_tasks SET status = 'ESCALATED', queue = 'escalations', reviewer = NULL,"
                + " decision_reason = ?, updated_at = now() WHERE id = ? AND status = 'CLAIMED' AND reviewer = ?",
                reason, id, reviewer) == 1;
    }

    public List<java.util.Map<String, Object>> queueDepths() {
        return db.queryForList("SELECT queue, status, count(*) AS n FROM review_tasks GROUP BY queue, status ORDER BY queue, status");
    }
}
