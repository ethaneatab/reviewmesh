package dev.reviewmesh.review;

import dev.reviewmesh.auth.Principal;
import dev.reviewmesh.common.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReviewController {
    private static final String[] READERS = {"reviewer", "senior", "ops", "service"};
    private final TaskRepository tasks;
    private final ReviewService review;

    public ReviewController(TaskRepository tasks, ReviewService review) {
        this.tasks = tasks;
        this.review = review;
    }

    public record Reason(String reason) {}

    @GetMapping("/v1/tasks")
    public List<Task> list(@RequestParam(required = false) String queue,
                           @RequestParam(defaultValue = "OPEN") String status,
                           @RequestParam(defaultValue = "50") int limit, HttpServletRequest http) {
        Principal.of(http).require(READERS);
        return tasks.list(queue, status, Math.min(limit, 200));
    }

    @GetMapping("/v1/tasks/{id}")
    public Task get(@PathVariable long id, HttpServletRequest http) {
        Principal.of(http).require(READERS);
        return tasks.get(id).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "no task " + id));
    }

    @GetMapping("/v1/tasks/by-record/{recordId}")
    public Task byRecord(@PathVariable String recordId, HttpServletRequest http) {
        Principal.of(http).require(READERS);
        return tasks.byRecord(recordId).orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "no task for " + recordId));
    }

    @GetMapping("/v1/queues")
    public List<Map<String, Object>> depths(HttpServletRequest http) {
        Principal.of(http).require(READERS);
        return tasks.queueDepths();
    }

    @PostMapping("/v1/tasks/{id}/claim")
    public Task claim(@PathVariable long id, HttpServletRequest http) {
        Principal p = Principal.of(http).require("reviewer", "senior");
        return review.claim(id, p.sub(), p.role());
    }

    @PostMapping("/v1/tasks/{id}/approve")
    public Task approve(@PathVariable long id, @RequestBody(required = false) Reason body, HttpServletRequest http) {
        Principal p = Principal.of(http).require("reviewer", "senior");
        return review.decide(id, p.sub(), "approve", body == null ? null : body.reason());
    }

    @PostMapping("/v1/tasks/{id}/reject")
    public Task reject(@PathVariable long id, @RequestBody(required = false) Reason body, HttpServletRequest http) {
        Principal p = Principal.of(http).require("reviewer", "senior");
        return review.decide(id, p.sub(), "reject", body == null ? null : body.reason());
    }

    @PostMapping("/v1/tasks/{id}/escalate")
    public Task escalate(@PathVariable long id, @RequestBody(required = false) Reason body, HttpServletRequest http) {
        Principal p = Principal.of(http).require("reviewer", "senior");
        return review.escalate(id, p.sub(), body == null ? null : body.reason());
    }
}
