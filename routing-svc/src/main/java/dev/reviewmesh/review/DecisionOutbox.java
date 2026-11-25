package dev.reviewmesh.review;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reviewmesh.common.AppProps;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.sqs.SqsClient;

/**
 * Approve / reject goes back to the Python side (export to S3) as decision.v1 on rm-decisions.
 * The message row is written in the same transaction as the decision, then sent by a poller,
 * so a crash between "decided" and "told downstream" cannot lose the decision.
 */
@Component
public class DecisionOutbox {
    private static final Logger log = LoggerFactory.getLogger(DecisionOutbox.class);
    private final JdbcTemplate db;
    private final SqsClient sqs;
    private final ObjectMapper json;
    private final AppProps props;

    public DecisionOutbox(JdbcTemplate db, SqsClient sqs, ObjectMapper json, AppProps props) {
        this.db = db;
        this.sqs = sqs;
        this.json = json;
        this.props = props;
    }

    // @learn:decision-outbox
    /** Call inside the decision's transaction. */
    public void add(Task t, String outcome, String reviewer, String reason) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("schema", "decision.v1");
        m.put("record_id", t.recordId());
        m.put("seq", t.seq());
        m.put("task_id", t.id());
        m.put("queue", t.queue());
        m.put("outcome", outcome);
        m.put("reviewer", reviewer);
        m.put("reason", reason);
        m.put("trace_id", t.traceId());
        m.put("decided_at", OffsetDateTime.now().toString());
        db.update("INSERT INTO decision_outbox(record_id, payload) VALUES (?, CAST(? AS jsonb))", t.recordId(), write(m));
    }

    @Scheduled(fixedDelay = 500)
    public void flush() {
        if (!props.sqs().enabled()) {
            return;
        }
        List<Map<String, Object>> rows = db.queryForList(
                "SELECT id, payload::text AS payload FROM decision_outbox WHERE published_at IS NULL ORDER BY id LIMIT 20");
        if (rows.isEmpty()) {
            return;
        }
        String url = sqs.getQueueUrl(b -> b.queueName(props.sqs().decisionQueue())).queueUrl();
        for (Map<String, Object> r : rows) {
            try {
                String mid = sqs.sendMessage(b -> b.queueUrl(url).messageBody((String) r.get("payload"))).messageId();
                db.update("UPDATE decision_outbox SET published_at = now(), message_id = ? WHERE id = ?", mid, r.get("id"));
            } catch (RuntimeException e) {
                log.warn("outbox send failed, will retry: {}", e.toString());
                return;
            }
        }
    }
    // @learn:end decision-outbox

    private String write(Map<String, Object> m) {
        try {
            return json.writeValueAsString(m);
        } catch (JsonProcessingException e) {
            throw new IllegalStateException(e);
        }
    }
}
