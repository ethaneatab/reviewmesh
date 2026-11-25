package dev.reviewmesh.auth;

import dev.reviewmesh.common.ApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Arrays;
import org.springframework.http.HttpStatus;

public record Principal(String sub, String role) {
    public static final String ATTR = "rm.principal";

    public static Principal of(HttpServletRequest req) {
        Object p = req.getAttribute(ATTR);
        if (p == null) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "missing bearer token");
        }
        return (Principal) p;
    }

    public Principal require(String... roles) {
        if (Arrays.asList(roles).contains(role)) {
            return this;
        }
        throw new ApiException(HttpStatus.FORBIDDEN, "role " + role + " cannot do this");
    }
}
