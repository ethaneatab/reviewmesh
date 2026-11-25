package dev.reviewmesh.review;

import dev.reviewmesh.audit.AuditRepository;
import dev.reviewmesh.common.ApiException;
import java.util.Map;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReviewService {
    private final TaskRepository tasks;
    private final AuditRepository audit;
    private final DecisionOutbox outbox;

    public ReviewService(TaskRepository tasks, AuditRepository audit, DecisionOutbox outbox) {
        this.tasks = tasks;
        this.audit = audit;
        this.outbox = outbox;
    }

    // @learn:handoff-intake
    @Transactional
    public String takeHandoff(HandoffMessage m, String messageId) {
        m.check();
        if (!tasks.markReceived(m.recordId(), m.seq(), messageId)) {
            return "duplicate";                       // SQS redelivered it; already taken in
        }
        Optional<Task> before = tasks.byRecord(m.recordId());
        Optional<Task> t = tasks.upsert(m);
        if (t.isEmpty()) {
            audit.append(m.recordId(), m.seq(), null, "HANDOFF_STALE", "routing-svc", null, null,
                    Map.of("reason", "a newer seq is already queued", "message_id", messageId));
            return "stale";
        }
        audit.append(m.recordId(), m.seq(), t.get().id(), before.isPresent() ? "TASK_SUPERSEDED" : "TASK_CREATED",
                "worker:" + m.worker(), before.map(Task::status).orElse(null), "OPEN",
                Map.of("queue", m.queue(), "priority", m.priority(), "engine", String.valueOf(m.engine()),
                        "decision_id", String.valueOf(m.decisionId()), "message_id", messageId,
                        "trace_id", String.valueOf(m.traceId())));
        return "created";
    }
    // @learn:end handoff-intake

    private Task load(long id) {
        return tasks.get(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "no task " + id));
    }

    // @learn:claim
    @Transactional
    public Task claim(long id, String reviewer, String role) {
        Task t = load(id);
        String from = t.status();
        if ("ESCALATED".equals(from) && !"senior".equals(role)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "escalated tasks need a senior reviewer");
        }
        if (!("OPEN".equals(from) || "ESCALATED".equals(from)) || !tasks.claim(id, reviewer, from)) {
            throw new ApiException(HttpStatus.CONFLICT, "task " + id + " is " + load(id).status() + ", not claimable");
        }
        audit.append(t.recordId(), t.seq(), id, "CLAIMED", reviewer, from, "CLAIMED", Map.of("queue", t.queue()));
        return load(id);
    }
    // @learn:end claim

    @Transactional
    public Task decide(long id, String reviewer, String outcome, String reason) {
        Task t = load(id);
        String to = switch (outcome) {
            case "approve" -> "APPROVED";
            case "reject" -> "REJECTED";
            default -> throw new IllegalArgumentException("outcome must be approve or reject");
        };
        if (!tasks.decide(id, reviewer, to, reason)) {
            throw new ApiException(HttpStatus.CONFLICT, "task " + id + " is not claimed by " + reviewer);
        }
        Task after = load(id);
        audit.append(t.recordId(), t.seq(), id, to, reviewer, "CLAIMED", to, Map.of("reason", String.valueOf(reason)));
        outbox.add(after, to, reviewer, reason);
        return after;
    }

    @Transactional
    public Task escalate(long id, String reviewer, String reason) {
        Task t = load(id);
        if (!tasks.escalate(id, reviewer, reason)) {
            throw new ApiException(HttpStatus.CONFLICT, "task " + id + " is not claimed by " + reviewer);
        }
        audit.append(t.recordId(), t.seq(), id, "ESCALATED", reviewer, "CLAIMED", "ESCALATED",
                Map.of("reason", String.valueOf(reason), "queue", "escalations"));
        return load(id);
    }
}
