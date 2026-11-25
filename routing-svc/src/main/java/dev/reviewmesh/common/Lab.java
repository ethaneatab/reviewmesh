package dev.reviewmesh.common;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

/** Switches for the failing controls: -Drm.lab.sabotage=no_rollback or RM_LAB_SABOTAGE=no_rollback. */
public final class Lab {
    private Lab() {}

    public static boolean sabotaged(String name) {
        String raw = System.getProperty("rm.lab.sabotage", "");
        if (raw.isBlank()) {
            raw = System.getenv().getOrDefault("RM_LAB_SABOTAGE", "");
        }
        Set<String> on = Arrays.stream(raw.split(",")).map(String::trim).filter(s -> !s.isEmpty()).collect(Collectors.toSet());
        return on.contains(name);
    }
}
