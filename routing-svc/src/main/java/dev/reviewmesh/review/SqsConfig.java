package dev.reviewmesh.review;

import dev.reviewmesh.common.AppProps;
import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

@Configuration
public class SqsConfig {
    @Bean(destroyMethod = "close")
    public SqsClient sqsClient(AppProps props) {
        return SqsClient.builder()
                .endpointOverride(URI.create(props.sqs().endpoint()))
                .region(Region.US_EAST_1)
                // LocalStack accepts any credentials; real AWS would use the default provider chain.
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create("test", "test")))
                .httpClient(UrlConnectionHttpClient.builder().build())
                .build();
    }
}
