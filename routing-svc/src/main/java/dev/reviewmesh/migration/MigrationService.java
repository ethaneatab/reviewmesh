package dev.reviewmesh.migration;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class MigrationService {
    /**
     * Rows whose old text value is not reflected in the new column. The V3 guard uses the same predicate.
     * A row with an id and no text is fine: NEW_ONLY writes exactly that.
     */
    static final String PENDING = "FROM review_tasks t LEFT JOIN reviewers r ON r.id = t.reviewer_id"
            + " WHERE t.reviewer IS NOT NULL AND (t.reviewer_id IS NULL OR r.handle <> t.reviewer)";

    private final JdbcTemplate db;
    private final PhaseHolder phase;

    public MigrationService(JdbcTemplate db, PhaseHolder phase) {
        this.db = db;
        this.phase = phase;
    }

    public boolean hasTextColumn() {
        return Boolean.TRUE.equals(db.queryForObject("SELECT EXISTS (SELECT 1 FROM information_schema.columns"
                + " WHERE table_schema = current_schema() AND table_name = 'review_tasks' AND column_name = 'reviewer')", Boolean.class));
    }

    public long pending() {
        if (!hasTextColumn()) {
            return 0;
        }
        Long n = db.queryForObject("SELECT count(*) " + PENDING, Long.class);
        return n == null ? 0 : n;
    }

    // @learn:backfill
    /** Re-runnable, in batches. Also repairs rows an old LEGACY instance changed during the overlap. */
    public Map<String, Object> backfill(int batch) {
        if (!hasTextColumn()) {
            return Map.of("updated", 0, "remaining", 0, "note", "already contracted");
        }
        db.update("INSERT INTO reviewers(handle) SELECT DISTINCT reviewer FROM review_tasks WHERE reviewer IS NOT NULL"
                + " ON CONFLICT (handle) DO NOTHING");
        int set = db.update("UPDATE review_tasks t SET reviewer_id = r.id FROM reviewers r WHERE r.handle = t.reviewer"
                + " AND t.reviewer_id IS DISTINCT FROM r.id AND t.id IN (SELECT t2.id FROM review_tasks t2"
                + " WHERE t2.reviewer IS NOT NULL ORDER BY t2.id LIMIT ?)", batch);
        // A LEGACY instance that un-assigned a task cleared only the text. Repair that, but only while no
        // NEW_ONLY instance exists yet: for NEW_ONLY, "id set, text empty" is a real claim, not a leftover.
        int cleared = phase.phase() == ReviewerPhase.DUAL_WRITE
                ? db.update("UPDATE review_tasks SET reviewer_id = NULL WHERE reviewer IS NULL AND reviewer_id IS NOT NULL")
                : 0;
        return Map.of("updated", set + cleared, "remaining", pending());
    }
    // @learn:end backfill

    public Map<String, Object> status() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("phase", phase.phase().name());
        out.put("schema_history", db.queryForList("SELECT version, description, installed_on, success"
                + " FROM flyway_schema_history WHERE version IS NOT NULL ORDER BY installed_rank"));
        List<String> cols = db.queryForList("SELECT column_name FROM information_schema.columns"
                + " WHERE table_schema = current_schema() AND table_name = 'review_tasks' ORDER BY ordinal_position", String.class);
        out.put("review_tasks_columns", cols);
        out.put("has_reviewer_text", cols.contains("reviewer"));
        out.put("has_reviewer_id", cols.contains("reviewer_id"));
        out.put("pending_backfill", pending());
        out.put("reviewers", cols.contains("reviewer_id")
                ? db.queryForObject("SELECT count(*) FROM reviewers", Long.class) : 0L);
        return out;
    }
}
