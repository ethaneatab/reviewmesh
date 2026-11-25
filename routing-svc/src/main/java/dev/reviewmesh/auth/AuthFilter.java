package dev.reviewmesh.auth;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Puts the verified caller on the request; controllers decide which roles may act. */
@Component
public class AuthFilter extends OncePerRequestFilter {
    private final JwtService jwt;

    public AuthFilter(JwtService jwt) {
        this.jwt = jwt;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
            throws ServletException, IOException {
        String h = req.getHeader("Authorization");
        if (h != null && h.regionMatches(true, 0, "Bearer ", 0, 7)) {
            jwt.verify(h.substring(7)).ifPresent(p -> req.setAttribute(Principal.ATTR, p));
        }
        chain.doFilter(req, res);
    }
}
