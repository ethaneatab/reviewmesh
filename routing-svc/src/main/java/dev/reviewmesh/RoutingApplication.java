package dev.reviewmesh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.scheduling.annotation.EnableScheduling;

/** Routing decisions, the reviewer queue and the audit trail (port 8891). */
@SpringBootApplication
@ConfigurationPropertiesScan
@EnableScheduling
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
