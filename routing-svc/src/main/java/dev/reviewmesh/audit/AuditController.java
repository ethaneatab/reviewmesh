package dev.reviewmesh.audit;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reviewmesh.auth.Principal;
import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuditController {
    private final AuditRepository audit;
    private final ObjectMapper json;

    public AuditController(AuditRepository audit, ObjectMapper json) {
        this.audit = audit;
        this.json = json;
    }

    @GetMapping("/v1/audit/records/{recordId}")
    public Map<String, Object> trail(@PathVariable String recordId, HttpServletRequest http) throws JsonProcessingException {
        Principal.of(http).require("reviewer", "senior", "ops", "service");
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> row : audit.forRecord(recordId)) {
            Map<String, Object> r = new HashMap<>(row);
            r.put("detail", json.readTree((String) row.get("detail")));
            out.add(r);
        }
        return Map.of("record_id", recordId, "events", out);
    }
}
