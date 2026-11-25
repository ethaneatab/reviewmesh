package dev.reviewmesh.auth;

import dev.reviewmesh.common.AppProps;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

/** Local-dev identities, created only when RM_SEED_DEMO=1. Passwords are obvious placeholders. */
@Component
public class DemoSeeder {
    private final JdbcTemplate db;
    private final AppProps props;

    public DemoSeeder(JdbcTemplate db, AppProps props) {
        this.db = db;
        this.props = props;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void seed() {
        if (props.seedDemo() != 1) {
            return;
        }
        BCryptPasswordEncoder bcrypt = new BCryptPasswordEncoder();
        String[][] users = {
            {"rita", "rita-demo", "reviewer", "Rita (reviewer)"},
            {"sam", "sam-demo", "senior", "Sam (senior reviewer)"},
            {"olive", "olive-demo", "ops", "Olive (release ops)"},
        };
        for (String[] u : users) {
            db.update("INSERT INTO users(username, password_hash, role, display_name) VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                    u[0], bcrypt.encode(u[1]), u[2], u[3]);
        }
    }
}
