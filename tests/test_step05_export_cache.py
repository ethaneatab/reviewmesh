"""Step 05: decisions become CSV/Parquet in S3; the status lookup is served from Redis."""
from __future__ import annotations

import io
import uuid

import pyarrow.parquet as pq

from rmflow import aws, cache, contracts, db, exporter, intake
from rmflow.config import settings


def _record() -> str:
    return intake.submit("acme-portal", "k-" + uuid.uuid4().hex, {"title": "export me", "doc_type": "invoice"}).body["record_id"]


def test_decision_message_is_written_to_s3_as_csv(aws_resources):
    rid = _record()
    msg = {**contracts.load("decision.v1.json")["message"], "record_id": rid}
    exporter.on_decision(msg, {"message_id": "m-1"})
    key = f"exports/decisions/dt=2026-11-25/{rid}-s1.csv"
    body = aws.s3().get_object(Bucket=settings().export_bucket, Key=key)["Body"].read().decode()
    assert body.splitlines()[0] == ",".join(exporter.COLUMNS)
    assert rid in body and "APPROVED" in body and "export me" in body
    exporter.on_decision(msg, {"message_id": "m-1-again"})          # redelivery overwrites the same key
    with db.tx() as conn:
        assert conn.execute("SELECT status FROM intake.records WHERE id=%s", (rid,)).fetchone()["status"] == "APPROVED"


def test_batch_export_is_readable_parquet(aws_resources):
    rid = _record()
    exporter.on_decision({**contracts.load("decision.v1.json")["message"], "record_id": rid}, {})
    out = exporter.batch_export()
    raw = aws.s3().get_object(Bucket=settings().export_bucket, Key=out["parquet"])["Body"].read()
    table = pq.read_table(io.BytesIO(raw))
    assert table.num_rows == out["rows"] >= 1
    assert rid in table.column("record_id").to_pylist()


def test_status_lookup_hits_redis_on_the_second_call():
    rid = _record()
    cache.r().delete(f"rm:status:{rid}")
    assert cache.record_status(rid)["cache"] == "miss"
    assert cache.record_status(rid)["cache"] == "hit"
