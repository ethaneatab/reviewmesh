"""A small SQS consumer loop with bounded exponential backoff.

On failure the message is not deleted; its visibility is pushed out by 2^(n-1) seconds
(n = receive count, capped). After MAX_RECEIVES the queue's redrive policy parks it in the DLQ.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from . import aws, logs

log = logs.setup("sqsloop")
BACKOFF_CAP_S = 16


class Retry(Exception):
    """Not an error: put the message back for a short while (e.g. waiting for an earlier seq)."""

    def __init__(self, delay_s: int = 1, why: str = ""):
        super().__init__(why)
        self.delay_s = delay_s


def backoff_seconds(receive_count: int) -> int:
    return int(min(2 ** max(receive_count - 1, 0), BACKOFF_CAP_S))


Handler = Callable[[dict[str, Any], dict[str, Any]], None]


def consume(queue: str, handler: Handler, stop: threading.Event, batch: int = 5, wait_s: int = 2) -> None:
    sqs = aws.sqs()
    url = aws.queue_url(queue)
    while not stop.is_set():
        try:
            resp = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=batch, WaitTimeSeconds=wait_s,
                                       AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
                                       MessageAttributeNames=["All"])
        except Exception:  # LocalStack restarting, network blip
            log.exception("receive failed", extra={"queue": queue})
            stop.wait(1)
            continue
        for m in resp.get("Messages", []):
            n = int(m["Attributes"].get("ApproximateReceiveCount", "1"))
            meta = {"message_id": m["MessageId"], "receive_count": n, "queue": queue,
                    "sent_ts": m["Attributes"].get("SentTimestamp")}
            try:
                body = json.loads(m["Body"])
                handler(body, meta)
            except Retry as r:
                sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"], VisibilityTimeout=r.delay_s)
                continue
            except Exception:
                delay = backoff_seconds(n)
                log.exception("handler failed; backing off", extra={"queue": queue, "attempt": n, "data": {"delay_s": delay}})
                try:
                    sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"], VisibilityTimeout=delay)
                except Exception:
                    log.exception("could not change visibility")
                continue
            sqs.delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])


def send(queue: str, body: dict[str, Any]) -> str:
    return str(aws.sqs().send_message(QueueUrl=aws.queue_url(queue), MessageBody=json.dumps(body))["MessageId"])
