package dev.reviewmesh.common;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reviewmesh")
public record AppProps(String jwtSecret, int seedDemo, Sqs sqs) {
    public record Sqs(boolean enabled, String endpoint, String handoffQueue, String decisionQueue) {}
}
