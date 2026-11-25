package dev.reviewmesh;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reviewmesh.auth.JwtService;
import dev.reviewmesh.review.HandoffMessage;
import dev.reviewmesh.review.ReviewService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/** Provider side of contracts/*.json: what Java returns and what it can parse. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ContractTest {
    @Autowired MockMvc mvc;
    @Autowired JwtService jwt;
    @Autowired ObjectMapper json;
    @Autowired ReviewService review;
    @Autowired JdbcTemplate db;

    @BeforeEach
    void clean() {
        TestSupport.reset(db);
    }

    // @learn:java-contract-test
    @Test
    void routingResponseKeepsEveryFieldOfTheV1Snapshot() throws Exception {
        JsonNode snap = TestSupport.contract("routing-decision.v1.json");
        String body = mvc.perform(post("/v1/routing/decisions")
                        .header("Authorization", "Bearer " + jwt.issue("worker:test", "service", 60))
                        .contentType(MediaType.APPLICATION_JSON).content(snap.get("request").toString()))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(TestSupport.breakingChanges(snap.get("response"), json.readTree(body), "$")).isEmpty();
    }
    // @learn:end java-contract-test

    @Test
    void handoffSnapshotParsesAndBecomesAnOpenTask() throws Exception {
        HandoffMessage m = json.treeToValue(TestSupport.contract("handoff.v1.json").get("message"), HandoffMessage.class);
        assertThat(m.recordId()).isEqualTo("rec_1c875595f6d03061");
        assertThat(m.validation().passed()).isTrue();
        assertThat(review.takeHandoff(m, "msg-1")).isEqualTo("created");
        assertThat(review.takeHandoff(m, "msg-1-redelivered")).isEqualTo("duplicate");
    }

    @Test
    void anOlderSeqArrivingLateDoesNotOverwriteTheTask() throws Exception {
        JsonNode base = TestSupport.contract("handoff.v1.json").get("message");
        HandoffMessage v2 = json.treeToValue(((com.fasterxml.jackson.databind.node.ObjectNode) base.deepCopy()).put("seq", 2), HandoffMessage.class);
        HandoffMessage v1 = json.treeToValue(base, HandoffMessage.class);
        assertThat(review.takeHandoff(v2, "m2")).isEqualTo("created");
        assertThat(review.takeHandoff(v1, "m1")).isEqualTo("stale");
        assertThat(db.queryForObject("SELECT seq FROM review_tasks", Integer.class)).isEqualTo(2);
    }

    @Test
    void routingRequiresAServiceToken() throws Exception {
        JsonNode snap = TestSupport.contract("routing-decision.v1.json");
        mvc.perform(post("/v1/routing/decisions").contentType(MediaType.APPLICATION_JSON).content(snap.get("request").toString()))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/v1/routing/decisions").header("Authorization", "Bearer " + jwt.issue("rita", "reviewer", 60))
                        .contentType(MediaType.APPLICATION_JSON).content(snap.get("request").toString()))
                .andExpect(status().isForbidden());
    }
}
