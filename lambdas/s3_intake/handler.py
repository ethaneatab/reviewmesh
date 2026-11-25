"""S3 ObjectCreated -> look at the object -> note it on the record timeline -> enqueue for partitioning.

Runs inside the LocalStack Lambda container (python3.11). pg8000 is vendored into the zip.
"""
import hashlib
import json
import os
import urllib.parse

import boto3
import pg8000.native

ENDPOINT = os.environ.get("RM_AWS_ENDPOINT")
s3 = boto3.client("s3", endpoint_url=ENDPOINT)
sqs = boto3.client("sqs", endpoint_url=ENDPOINT)


def _sniff(head: bytes) -> str:
    if head.startswith(b"%PDF-"):
        return "pdf"
    if b"," in head.split(b"\n", 1)[0]:
        return "csv"
    return "unknown"


def _db():
    return pg8000.native.Connection(
        user=os.environ["RM_PG_USER"], password=os.environ["RM_PG_PASSWORD"],
        host=os.environ["RM_PG_HOST"], port=int(os.environ.get("RM_PG_PORT", "5432")),
        database=os.environ["RM_PG_DB"], timeout=10)


# @learn:lambda-handler
def handler(event, context):
    queue_url = sqs.get_queue_url(QueueName=os.environ["RM_INTAKE_QUEUE"])["QueueUrl"]
    sent = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        meta = obj.get("Metadata", {})
        msg = {
            "schema": "intake.v1",
            "record_id": meta["record-id"],
            "seq": int(meta["seq"]),
            "trace_id": meta.get("trace-id"),
            "s3_key": key,
            "size": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "sniff": _sniff(body[:64]),
            "via": "s3-lambda",
            "lambda_request_id": context.aws_request_id,
        }
        conn = _db()
        try:
            conn.run("INSERT INTO intake.record_events(record_id, seq, stage, actor, detail)"
                     " VALUES (:r, :s, 'LAMBDA_SEEN', :a, CAST(:d AS jsonb))",
                     r=msg["record_id"], s=msg["seq"], a="lambda:" + context.aws_request_id, d=json.dumps(msg))
            conn.run("UPDATE intake.records SET status='QUEUED', updated_at=now() WHERE id=:r AND status='STORED'",
                     r=msg["record_id"])
        finally:
            conn.close()
        out = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(msg))
        sent.append(out["MessageId"])
    return {"sent": sent}
# @learn:end lambda-handler
