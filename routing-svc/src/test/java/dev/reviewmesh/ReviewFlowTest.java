package dev.reviewmesh;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reviewmesh.common.ApiException;
import dev.reviewmesh.review.HandoffMessage;
import dev.reviewmesh.review.ReviewService;
import dev.reviewmesh.review.Task;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ReviewFlowTest {
    @Autowired ReviewService review;
    @Autowired JdbcTemplate db;
    @Autowired ObjectMapper json;

    long taskId;

    @BeforeEach
    void setUp() throws Exception {
        TestSupport.reset(db);
        HandoffMessage m = json.treeToValue(TestSupport.contract("handoff.v1.json").get("message"), HandoffMessage.class);
        review.takeHandoff(m, "m1");
        taskId = db.queryForObject("SELECT id FROM review_tasks", Long.class);
    }

    @Test
    void twoReviewersRaceForOneTaskAndExactlyOneWins() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        List<Callable<String>> jobs = List.of(() -> claim("rita"), () -> claim("sam"));
        int wins = 0;
        for (Future<String> f : pool.invokeAll(jobs)) {
            if ("won".equals(f.get())) {
                wins++;
            }
        }
        pool.shutdown();
        assertThat(wins).isEqualTo(1);
    }

    private String claim(String who) {
        try {
            review.claim(taskId, who, "reviewer");
            return "won";
        } catch (ApiException e) {
            return "lost";
        }
    }

    @Test
    void approveWritesTheAuditTrailAndTheOutboxInOneGo() {
        review.claim(taskId, "rita", "reviewer");
        Task t = review.decide(taskId, "rita", "approve", "amounts match");
        assertThat(t.status()).isEqualTo("APPROVED");
        assertThat(db.queryForList("SELECT action FROM audit_events ORDER BY id", String.class))
                .containsExactly("TASK_CREATED", "CLAIMED", "APPROVED");
        assertThat(db.queryForObject("SELECT payload->>'outcome' FROM decision_outbox", String.class)).isEqualTo("APPROVED");
    }

    @Test
    void onlyTheClaimingReviewerCanDecide() {
        review.claim(taskId, "rita", "reviewer");
        assertThatThrownBy(() -> review.decide(taskId, "sam", "reject", "no")).isInstanceOf(ApiException.class);
    }

    @Test
    void escalatedWorkNeedsASenior() {
        review.claim(taskId, "rita", "reviewer");
        review.escalate(taskId, "rita", "signature looks off");
        assertThatThrownBy(() -> review.claim(taskId, "rita", "reviewer")).isInstanceOf(ApiException.class);
        assertThat(review.claim(taskId, "sam", "senior").status()).isEqualTo("CLAIMED");
    }
}
