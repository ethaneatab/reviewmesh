package dev.reviewmesh.review;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.reviewmesh.common.AppProps;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.Message;

/** Long-polls rm-handoff. A message that keeps failing is left alone; the redrive policy parks it in the DLQ. */
@Component
public class HandoffConsumer {
    private static final Logger log = LoggerFactory.getLogger(HandoffConsumer.class);
    private final SqsClient sqs;
    private final ObjectMapper json;
    private final ReviewService review;
    private final AppProps props;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public HandoffConsumer(SqsClient sqs, ObjectMapper json, ReviewService review, AppProps props) {
        this.sqs = sqs;
        this.json = json;
        this.review = review;
        this.props = props;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void start() {
        if (!props.sqs().enabled() || !running.compareAndSet(false, true)) {
            return;
        }
        Thread t = new Thread(this::loop, "handoff-consumer");
        t.setDaemon(true);
        t.start();
    }

    private void loop() {
        String url = null;
        while (running.get()) {
            try {
                if (url == null) {
                    url = sqs.getQueueUrl(b -> b.queueName(props.sqs().handoffQueue())).queueUrl();
                }
                final String q = url;
                for (Message m : sqs.receiveMessage(b -> b.queueUrl(q).maxNumberOfMessages(5).waitTimeSeconds(2)).messages()) {
                    handle(q, m);
                }
            } catch (RuntimeException e) {
                log.warn("handoff poll failed: {}", e.toString());
                sleep(1000);
            }
        }
    }

    void handle(String url, Message m) {
        try {
            HandoffMessage h = json.readValue(m.body(), HandoffMessage.class);
            MDC.put("record_id", h.recordId());
            MDC.put("trace_id", String.valueOf(h.traceId()));
            String result = review.takeHandoff(h, m.messageId());
            log.info("handoff {} seq {}: {}", h.recordId(), h.seq(), result);
            sqs.deleteMessage(b -> b.queueUrl(url).receiptHandle(m.receiptHandle()));
        } catch (Exception e) {
            log.warn("handoff {} failed, leaving it for redelivery: {}", m.messageId(), e.toString());
        } finally {
            MDC.clear();
        }
    }

    private static void sleep(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
