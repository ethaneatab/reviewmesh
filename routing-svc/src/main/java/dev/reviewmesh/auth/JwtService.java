package dev.reviewmesh.auth;

import dev.reviewmesh.common.AppProps;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Service;

/** HS256 tokens shared with the Python services (same issuer, same key from RM_JWT_SECRET). */
@Service
public class JwtService {
    private static final String ISSUER = "reviewmesh";
    private final SecretKey key;

    public JwtService(AppProps props) {
        this.key = Keys.hmacShaKeyFor(props.jwtSecret().getBytes(StandardCharsets.UTF_8));
    }

    public String issue(String sub, String role, long ttlSeconds) {
        Instant now = Instant.now();
        return Jwts.builder().subject(sub).issuer(ISSUER).claim("role", role)
                .issuedAt(Date.from(now)).expiration(Date.from(now.plusSeconds(ttlSeconds)))
                .signWith(key, Jwts.SIG.HS256).compact();
    }

    public Optional<Principal> verify(String token) {
        try {
            Claims c = Jwts.parser().verifyWith(key).requireIssuer(ISSUER).build().parseSignedClaims(token).getPayload();
            return Optional.of(new Principal(c.getSubject(), String.valueOf(c.get("role"))));
        } catch (JwtException | IllegalArgumentException e) {
            return Optional.empty();
        }
    }
}
