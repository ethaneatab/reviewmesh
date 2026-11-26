package dev.reviewmesh.routing;

import dev.reviewmesh.auth.Principal;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RoutingController {
    private static final Logger log = LoggerFactory.getLogger(RoutingController.class);
    private final RoutingService routing;

    public RoutingController(RoutingService routing) {
        this.routing = routing;
    }

    // @learn:routing-endpoint
    @PostMapping("/v1/routing/decisions")
    public DecisionResponse decide(@RequestBody DecisionRequest req, HttpServletRequest http) {
        Principal.of(http).require("service", "ops");
        if ("true".equalsIgnoreCase(http.getHeader("X-Dry-Run"))) {
            return routing.dryRun(req);
        }
        MDC.put("record_id", req.recordId());
        MDC.put("trace_id", String.valueOf(req.traceId()));
        try {
            DecisionResponse out = routing.decide(req);
            log.info("routed {} seq {} -> {} via {}", req.recordId(), req.seq(), out.queue(), out.engine());
            return out;
        } finally {
            MDC.clear();
        }
    }
    // @learn:end routing-endpoint
}
