package dev.reviewmesh.migration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PhaseHolder {
    private final ReviewerPhase phase;

    public PhaseHolder(@Value("${reviewmesh.migration.phase:NEW_ONLY}") ReviewerPhase phase) {
        this.phase = phase;
    }

    public ReviewerPhase phase() {
        return phase;
    }
}
