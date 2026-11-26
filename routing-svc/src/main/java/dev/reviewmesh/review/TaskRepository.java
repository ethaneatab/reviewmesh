package dev.reviewmesh.review;

import dev.reviewmesh.migration.PhaseHolder;
import dev.reviewmesh.migration.ReviewerPhase;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * Every place that touches the reviewer is phase-aware (see ReviewerPhase), so two app versions in
 * neighbouring phases can share one database during the expand/contract migration.
 */
@Repository
public class TaskRepository {
    private final JdbcTemplate db;
    private final ReviewerPhase phase;

    // @learn:repo-constructors
    @org.springframework.beans.factory.annotation.Autowired
    public TaskRepository(JdbcTemplate db, PhaseHolder phase) {
        this(db, phase.phase());
    }

    /** For tests that run an "old" and a "new" version against the same database. */
    public TaskRepository(JdbcTemplate db, ReviewerPhase phase) {
        this.db = db;
        this.phase = phase;
    }
    // @learn:end repo-constructors

    public ReviewerPhase phase() {
        return phase;
    }

    // @learn:phase-sql
    private String cols() {
        String reviewer = phase.readsId()
                ? "(SELECT r.handle FROM reviewers r WHERE r.id = t.reviewer_id) AS reviewer"
                : "t.reviewer AS reviewer";
        String reviewerId = phase == ReviewerPhase.LEGACY ? "NULL::bigint AS reviewer_id" : "t.reviewer_id";
        return "t.id, t.record_id, t.seq, t.title, t.doc_type, t.s3_key, t.queue, t.priority, t.status, " + reviewer + ", "
                + reviewerId + ", t.decision_reason, t.trace_id, t.created_at, t.updated_at";
    }

    /** SET fragment + args that record `handle` as the reviewer (null clears it). */
    private void setReviewer(StringBuilder sql, List<Object> args, String handle) {
        List<String> parts = new ArrayList<>();
        if (phase.writesText()) {
            parts.add("reviewer = ?");
            args.add(handle);
        }
        if (phase.writesId()) {
            parts.add("reviewer_id = ?");
            args.add(handle == null ? null : reviewerId(handle));
        }
        sql.append(String.join(", ", parts));
    }

    /** WHERE fragment: "claimed by this reviewer", read from whichever column this phase trusts. */
    private String reviewerIs(List<Object> args, String handle) {
        if (phase.readsId()) {
            args.add(reviewerId(handle));
            return "reviewer_id = ?";
        }
        args.add(handle);
        return "reviewer = ?";
    }
    // @learn:end phase-sql

    long reviewerId(String handle) {
        Long id = db.queryForObject("INSERT INTO reviewers(handle) VALUES (?) ON CONFLICT (handle)"
                + " DO UPDATE SET handle = EXCLUDED.handle RETURNING id", Long.class, handle);
        return id == null ? -1 : id;
    }

    private Task map(ResultSet rs, int i) throws SQLException {
        long rid = rs.getLong("reviewer_id");
        return new Task(rs.getLong("id"), rs.getString("record_id"), rs.getInt("seq"), rs.getString("title"),
                rs.getString("doc_type"), rs.getString("s3_key"), rs.getString("queue"), rs.getInt("priority"),
                rs.getString("status"), rs.getString("reviewer"), rs.wasNull() ? null : rid, rs.getString("decision_reason"),
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
        List<Object> args = new ArrayList<>(List.of(m.recordId(), m.seq(), m.title(), m.docType(),
                m.s3Key() == null ? "" : m.s3Key(), m.queue(), m.priority(), m.decisionId() == null ? "" : m.decisionId(),
                m.traceId() == null ? "" : m.traceId()));
        StringBuilder sql = new StringBuilder(
                "INSERT INTO review_tasks(record_id, seq, title, doc_type, s3_key, queue, priority, status, decision_id, trace_id)"
                        + " VALUES (?,?,?,?,?,?,?,'OPEN',?,?)"
                        + " ON CONFLICT (record_id) DO UPDATE SET seq = EXCLUDED.seq, title = EXCLUDED.title,"
                        + " s3_key = EXCLUDED.s3_key, queue = EXCLUDED.queue, priority = EXCLUDED.priority, status = 'OPEN',"
                        + " decision_id = EXCLUDED.decision_id, decision_reason = NULL, updated_at = now(), ");
        setReviewer(sql, args, null);
        sql.append(" WHERE review_tasks.seq < EXCLUDED.seq RETURNING id");
        List<Long> ids = db.queryForList(sql.toString(), Long.class, args.toArray());
        return ids.isEmpty() ? Optional.empty() : get(ids.get(0));
    }
    // @learn:end task-upsert

    public Optional<Task> get(long id) {
        return db.query("SELECT " + cols() + " FROM review_tasks t WHERE t.id = ?", this::map, id).stream().findFirst();
    }

    public Optional<Task> byRecord(String recordId) {
        return db.query("SELECT " + cols() + " FROM review_tasks t WHERE t.record_id = ?", this::map, recordId).stream().findFirst();
    }

    // @learn:queue-query
    public List<Task> list(String queue, String status, int limit) {
        if (queue == null) {
            return db.query("SELECT " + cols() + " FROM review_tasks t WHERE t.status = ? ORDER BY t.priority, t.created_at LIMIT ?",
                    this::map, status, limit);
        }
        return db.query("SELECT " + cols() + " FROM review_tasks t WHERE t.queue = ? AND t.status = ?"
                + " ORDER BY t.priority, t.created_at LIMIT ?", this::map, queue, status, limit);
    }
    // @learn:end queue-query

    /** Conditional update: only one reviewer can win the claim. */
    public boolean claim(long id, String reviewer, String fromStatus) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE review_tasks SET status = 'CLAIMED', updated_at = now(), ");
        setReviewer(sql, args, reviewer);
        sql.append(" WHERE id = ? AND status = ?");
        args.add(id);
        args.add(fromStatus);
        return db.update(sql.toString(), args.toArray()) == 1;
    }

    public boolean decide(long id, String reviewer, String toStatus, String reason) {
        List<Object> args = new ArrayList<>(List.of(toStatus));
        args.add(reason);
        args.add(id);
        String sql = "UPDATE review_tasks SET status = ?, decision_reason = ?, updated_at = now()"
                + " WHERE id = ? AND status = 'CLAIMED' AND " + reviewerIs(args, reviewer);
        return db.update(sql, args.toArray()) == 1;
    }

    public boolean escalate(long id, String reviewer, String reason) {
        List<Object> args = new ArrayList<>();
        StringBuilder sql = new StringBuilder("UPDATE review_tasks SET status = 'ESCALATED', queue = 'escalations',"
                + " decision_reason = ?, updated_at = now(), ");
        args.add(reason);
        setReviewer(sql, args, null);
        sql.append(" WHERE id = ? AND status = 'CLAIMED' AND ");
        args.add(id);
        sql.append(reviewerIs(args, reviewer));
        return db.update(sql.toString(), args.toArray()) == 1;
    }

    public List<Map<String, Object>> queueDepths() {
        return db.queryForList("SELECT queue, status, count(*) AS n FROM review_tasks GROUP BY queue, status ORDER BY queue, status");
    }
}
