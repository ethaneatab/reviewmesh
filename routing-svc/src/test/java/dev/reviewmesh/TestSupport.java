package dev.reviewmesh;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;

public final class TestSupport {
    private TestSupport() {}

    private static final ObjectMapper JSON = new ObjectMapper();

    /** The contracts/ folder at the repo root; both test suites read the same snapshots. */
    public static JsonNode contract(String name) throws IOException {
        return JSON.readTree(Files.readString(Path.of("..", "contracts", name)));
    }

    /** Fields an old client relies on that vanished or changed JSON type. Extra fields are fine. */
    public static List<String> breakingChanges(JsonNode snap, JsonNode actual, String path) {
        List<String> out = new ArrayList<>();
        if (snap.isObject()) {
            if (actual == null || !actual.isObject()) {
                out.add(path + ": object became " + (actual == null ? "missing" : actual.getNodeType()));
                return out;
            }
            for (Iterator<Map.Entry<String, JsonNode>> it = snap.fields(); it.hasNext(); ) {
                Map.Entry<String, JsonNode> e = it.next();
                if (!actual.has(e.getKey())) {
                    out.add(path + "." + e.getKey() + ": removed");
                } else {
                    out.addAll(breakingChanges(e.getValue(), actual.get(e.getKey()), path + "." + e.getKey()));
                }
            }
            return out;
        }
        if (snap.isNull() || actual.isNull()) {
            return out;
        }
        if (snap.getNodeType() != actual.getNodeType()) {
            out.add(path + ": " + snap.getNodeType() + " became " + actual.getNodeType());
        }
        return out;
    }

    public static void reset(JdbcTemplate db) {
        db.execute("TRUNCATE review_tasks, handoff_inbox, audit_events, routing_decisions, decision_outbox RESTART IDENTITY");
    }
}
