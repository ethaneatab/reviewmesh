package dev.reviewmesh.migration;

import dev.reviewmesh.auth.Principal;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MigrationController {
    private final MigrationService migration;

    public MigrationController(MigrationService migration) {
        this.migration = migration;
    }

    @GetMapping("/v1/migration/status")
    public Map<String, Object> status() {
        return migration.status();
    }

    @PostMapping("/v1/migration/backfill")
    public Map<String, Object> backfill(@RequestParam(defaultValue = "500") int batch, HttpServletRequest http) {
        Principal.of(http).require("ops", "service");
        return migration.backfill(Math.max(1, Math.min(batch, 5000)));
    }
}
