"""Step 02: the document goes to S3, an S3-triggered Lambda enqueues it, failures are bounded."""
from __future__ import annotations

import base64
import json
import threading
import time
import uuid

import pytest

from rmflow import aws, db, intake, pipeline, sqsloop, storage
from rmflow.config import settings

PDF = base64.b64encode(b"%PDF-1.4\n% test\n").decode()


def _submit(title: str) -> intake.Outcome:
    body = {"title": title, "doc_type": "invoice", "filename": "t.pdf", "document_b64": PDF, "fields": {}}
    return intake.submit("acme-portal", "k-" + uuid.uuid4().hex, body, store=storage.store_in_s3)


def test_document_lands_in_s3_with_record_metadata(aws_resources):
    out = _submit("s3 metadata")
    rid = out.body["record_id"]
    with db.tx() as conn:
        key = conn.execute("SELECT s3_key FROM intake.record_versions WHERE record_id=%s", (rid,)).fetchone()["s3_key"]
    head = aws.s3().head_object(Bucket=settings().inbox_bucket, Key=key)
    assert head["Metadata"]["record-id"] == rid and head["Metadata"]["seq"] == "1"
    assert out.body["status"] == "STORED"


def test_backoff_is_exponential_and_capped():
    assert [sqsloop.backoff_seconds(n) for n in range(1, 8)] == [1, 2, 4, 8, 16, 16, 16]


def test_reconciler_enqueues_a_record_whose_s3_event_was_lost(aws_resources):
    rid = _submit("lost event").body["record_id"]
    with db.tx() as conn:
        conn.execute("UPDATE intake.records SET updated_at = now() - interval '5 minutes' WHERE id=%s", (rid,))
    assert pipeline.reconcile_once() >= 1
    url = aws.queue_url(settings().intake_queue)
    seen = []
    for _ in range(10):
        for m in aws.sqs().receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1).get("Messages", []):
            seen.append(json.loads(m["Body"]))
            aws.sqs().delete_message(QueueUrl=url, ReceiptHandle=m["ReceiptHandle"])
        if any(b["record_id"] == rid for b in seen):
            break
    mine = [b for b in seen if b["record_id"] == rid]
    assert mine and mine[0]["via"] == "reconciler"
    with db.tx() as conn:
        assert conn.execute("SELECT status FROM intake.records WHERE id=%s", (rid,)).fetchone()["status"] == "QUEUED"


def test_poison_message_is_parked_in_the_dlq_after_bounded_retries(aws_resources):
    stop = threading.Event()
    t = threading.Thread(target=sqsloop.consume, args=(settings().intake_queue, pipeline.dispatch, stop), daemon=True)
    t.start()
    marker = uuid.uuid4().hex
    sqsloop.send(settings().intake_queue, {"schema": "garbage", "marker": marker})
    dlq = aws.queue_url(settings().intake_queue + "-dlq")
    found = None
    deadline = time.time() + 45
    try:
        while time.time() < deadline and not found:
            for m in aws.sqs().receive_message(QueueUrl=dlq, MaxNumberOfMessages=10, WaitTimeSeconds=1,
                                               AttributeNames=["ApproximateReceiveCount"]).get("Messages", []):
                if json.loads(m["Body"]).get("marker") == marker:
                    found = m
                aws.sqs().delete_message(QueueUrl=dlq, ReceiptHandle=m["ReceiptHandle"])
    finally:
        stop.set()
        t.join(5)
    assert found is not None, "poison message never reached the DLQ"


@pytest.mark.live
def test_live_s3_event_runs_the_lambda_and_reaches_sqs(live):
    import httpx
    key = "live-" + uuid.uuid4().hex
    r = httpx.post(live.api + "/v1/records", headers={"Authorization": f"Bearer {live.token}", "Idempotency-Key": key},
                   json={"title": "live lambda", "doc_type": "invoice", "filename": "l.pdf", "document_b64": PDF})
    rid = r.json()["record_id"]
    stages: list[str] = []
    for _ in range(60):
        stages = [e["stage"] for e in live.sql("SELECT stage FROM intake.record_events WHERE record_id=%s ORDER BY id", rid)]
        if "LAMBDA_SEEN" in stages and "SQS_RECEIVED" in stages:
            break
        time.sleep(0.5)
    assert stages[:3] == ["SUBMITTED", "LAMBDA_SEEN", "SQS_RECEIVED"], stages
