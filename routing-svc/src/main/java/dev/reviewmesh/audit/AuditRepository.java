package dev.reviewmesh.audit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/** Append-only. Nothing in the code base updates or deletes an audit row. */
@Repository
public class AuditRepository {
    private final JdbcTemplate db;
    private final ObjectMapper json;

    public AuditRepository(JdbcTemplate db, ObjectMapper json) {
        this.db = db;
        this.json = json;
    }

    // @learn:audit-append
    public void append(String recordId, Integer seq, Long taskId, String action, String actor,
                       String from, String to, Map<String, ?> detail) {
        try {
            db.update("INSERT INTO audit_events(record_id, seq, task_id, action, actor, from_status, to_status, detail)"
                    + " VALUES (?,?,?,?,?,?,?, CAST(? AS jsonb))",
                    recordId, seq, taskId, action, actor, from, to, json.writeValueAsString(detail));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
    }
    // @learn:end audit-append

    public List<Map<String, Object>> forRecord(String recordId) {
        return db.queryForList("SELECT id, record_id, seq, task_id, action, actor, from_status, to_status,"
                + " detail::text AS detail, at FROM audit_events WHERE record_id = ? ORDER BY id", recordId);
    }
}
