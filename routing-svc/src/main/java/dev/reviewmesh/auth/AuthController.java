package dev.reviewmesh.auth;

import dev.reviewmesh.common.ApiException;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {
    private final JdbcTemplate db;
    private final JwtService jwt;
    private final BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder();

    public AuthController(JdbcTemplate db, JwtService jwt) {
        this.db = db;
        this.jwt = jwt;
    }

    public record Login(String username, String password) {}

    @PostMapping("/v1/auth/login")
    public Map<String, Object> login(@RequestBody Login in) {
        List<Map<String, Object>> rows = db.queryForList(
                "SELECT password_hash, role, display_name FROM users WHERE username = ?", in.username());
        if (rows.isEmpty() || in.password() == null || !bcrypt.matches(in.password(), (String) rows.get(0).get("password_hash"))) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "wrong username or password");
        }
        String role = (String) rows.get(0).get("role");
        return Map.of("token", jwt.issue(in.username(), role, 8 * 3600), "role", role,
                "username", in.username(), "display_name", rows.get(0).get("display_name"));
    }
}
