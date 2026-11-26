package dev.reviewmesh.rollout;

import dev.reviewmesh.auth.Principal;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RolloutController {
    private final RolloutService rollout;

    public RolloutController(RolloutService rollout) {
        this.rollout = rollout;
    }

    @GetMapping("/v1/rollout")
    public Map<String, Object> view() {
        return rollout.view();
    }

    @PostMapping("/v1/rollout/start")
    public Map<String, Object> start(HttpServletRequest http) {
        rollout.start(Principal.of(http).require("ops").sub());
        return rollout.view();
    }

    @PostMapping("/v1/rollout/advance")
    public Map<String, Object> advance(HttpServletRequest http) {
        rollout.advance(Principal.of(http).require("ops").sub());
        return rollout.view();
    }

    @PostMapping("/v1/rollout/fault")
    public Map<String, Object> fault(@RequestParam double rate, HttpServletRequest http) {
        rollout.fault(Math.max(0, Math.min(rate, 1)), Principal.of(http).require("ops").sub());
        return rollout.view();
    }

    @PostMapping("/v1/rollout/reset")
    public Map<String, Object> reset(HttpServletRequest http) {
        rollout.reset(Principal.of(http).require("ops").sub());
        return rollout.view();
    }
}
