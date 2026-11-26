package dev.reviewmesh;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import dev.reviewmesh.migration.MigrationService;
import dev.reviewmesh.migration.PhaseHolder;
import dev.reviewmesh.migration.ReviewerPhase;
import dev.reviewmesh.review.HandoffMessage;
import dev.reviewmesh.review.Task;
import dev.reviewmesh.review.TaskRepository;
import java.util.List;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

/**
 * Expand / contract, step by step, on a scratch database. At every step the old and the new app
 * version (two TaskRepository instances in neighbouring phases) share the same tables, read each
 * other's writes, and the task JSON keeps every field of contracts/task.v1.json.
 */
class MigrationCompatTest {
    static final String URL = System.getenv().getOrDefault("RM_MIGR_JDBC_URL",
            "jdbc:postgresql://127.0.0.1:54390/reviewmesh_migr?currentSchema=review");
    final DriverManagerDataSource ds = new DriverManagerDataSource(URL, "reviewmesh", "reviewmesh-dev");
    final JdbcTemplate db = new JdbcTemplate(ds);
    final ObjectMapper json = new ObjectMapper().registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    int recordNo = 0;

    void migrateTo(String target) {
        Flyway.configure().dataSource(ds).schemas("review").target(target).cleanDisabled(false).load().migrate();
    }

    TaskRepository app(ReviewerPhase p) {
        return new TaskRepository(db, p);
    }

    long newTask(TaskRepository repo) {
        recordNo++;
        HandoffMessage m = new HandoffMessage("handoff.v1", "rec_m" + recordNo, 1, "dec_" + recordNo, "finance", 3, "v1",
                "migration task " + recordNo, "invoice", "inbox/x", "trace", "w1", 10, new HandoffMessage.Validation(true, List.of()));
        return repo.upsert(m).orElseThrow().id();
    }

    String reviewerSeenBy(TaskRepository repo, long id) {
        return repo.get(id).orElseThrow().reviewer();
    }

    void assertOldClientsStillWork(TaskRepository repo, long id) throws Exception {
        Task t = repo.get(id).orElseThrow();
        JsonNode snap = TestSupport.contract("task.v1.json").get("response");
        assertThat(TestSupport.breakingChanges(snap, json.valueToTree(t), "$")).as("phase %s", repo.phase()).isEmpty();
    }

    @BeforeEach
    void freshSchema() {
        Flyway.configure().dataSource(ds).schemas("review").cleanDisabled(false).load().clean();
    }

    // @learn:test-expand-contract
    @Test
    void everyStepRunsOldAndNewSideBySide() throws Exception {
        migrateTo("1");
        TaskRepository v1 = app(ReviewerPhase.LEGACY);
        long a = newTask(v1);
        assertThat(v1.claim(a, "rita", "OPEN")).isTrue();

        // EXPAND: new nullable column + reviewers table. Old app untouched; new app dual-writes.
        migrateTo("2");
        TaskRepository v2 = app(ReviewerPhase.DUAL_WRITE);
        long b = newTask(v1);
        long c = newTask(v2);
        assertThat(v1.claim(b, "sam", "OPEN")).isTrue();
        assertThat(v2.claim(c, "rita", "OPEN")).isTrue();
        assertThat(reviewerSeenBy(v1, c)).isEqualTo("rita");          // old reads what new wrote
        assertThat(reviewerSeenBy(v2, b)).isEqualTo("sam");           // new reads what old wrote
        assertThat(v1.decide(c, "rita", "APPROVED", "ok")).isTrue();  // old can finish new's claim
        for (long id : new long[] {a, b, c}) {
            assertOldClientsStillWork(v1, id);
            assertOldClientsStillWork(v2, id);
        }

        // BACKFILL: once no LEGACY instance is left, copy old values into the new column.
        MigrationService mig = new MigrationService(db, new PhaseHolder(ReviewerPhase.DUAL_WRITE));
        assertThat(mig.pending()).isEqualTo(2);                       // a and b were written by v1
        assertThat(mig.backfill(1).get("remaining")).isEqualTo(1L);   // batched
        assertThat(mig.backfill(500).get("remaining")).isEqualTo(0L);

        // SWITCH READS: v3 trusts reviewer_id, still writes both so v2 stays correct.
        TaskRepository v3 = app(ReviewerPhase.READ_NEW);
        long d = newTask(v3);
        assertThat(v3.claim(d, "sam", "OPEN")).isTrue();
        assertThat(reviewerSeenBy(v3, b)).isEqualTo("sam");           // backfilled row reads right
        assertThat(reviewerSeenBy(v2, d)).isEqualTo("sam");

        // NEW ONLY: v4 stops writing the text column; v3 reads through the id, so they agree.
        TaskRepository v4 = app(ReviewerPhase.NEW_ONLY);
        long e = newTask(v4);
        assertThat(v4.claim(e, "rita", "OPEN")).isTrue();
        assertThat(reviewerSeenBy(v3, e)).isEqualTo("rita");
        assertThat(v4.decide(d, "sam", "REJECTED", "blurry scan")).isTrue();   // claimed by v3
        assertThat(mig.pending()).isZero();

        // CONTRACT: drop the old column. Only NEW_ONLY is still running.
        migrateTo("3");
        long f = newTask(v4);
        assertThat(v4.claim(f, "sam", "OPEN")).isTrue();
        for (long id : new long[] {a, b, c, d, e, f}) {
            assertOldClientsStillWork(v4, id);
        }
        assertThat(reviewerSeenBy(v4, a)).isEqualTo("rita");          // the very first row survived
        assertThatThrownBy(() -> v1.get(a)).hasMessageContaining("reviewer");  // why v1 had to be gone first
    }
    // @learn:end test-expand-contract

    @Test
    void contractRefusesToRunBeforeTheBackfill() {
        migrateTo("2");
        TaskRepository v1 = app(ReviewerPhase.LEGACY);
        long a = newTask(v1);
        v1.claim(a, "rita", "OPEN");
        assertThatThrownBy(() -> migrateTo("3")).hasStackTraceContaining("contract blocked: 1 review_tasks rows are not backfilled");
        assertThat(reviewerSeenBy(v1, a)).isEqualTo("rita");          // nothing was dropped
    }

    @Test
    void skippingAPhaseIsCaught() {
        // LEGACY next to NEW_ONLY is not a neighbouring pair: the old app cannot see the new app's claims.
        migrateTo("2");
        TaskRepository v1 = app(ReviewerPhase.LEGACY);
        TaskRepository v4 = app(ReviewerPhase.NEW_ONLY);
        long a = newTask(v4);
        v4.claim(a, "rita", "OPEN");
        assertThat(reviewerSeenBy(v1, a)).isNull();
    }
}
