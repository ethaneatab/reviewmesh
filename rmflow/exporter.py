"""Decisions from the Java side -> CSV in S3 for downstream systems; batch export as Parquet + CSV."""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from . import aws, db, logs
from .config import settings

log = logs.setup("exporter")
COLUMNS = ["record_id", "seq", "title", "doc_type", "queue", "outcome", "reviewer", "reason", "decided_at", "trace_id"]


def _csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode()


# @learn:export-decision
def on_decision(body: dict[str, Any], meta: dict[str, Any]) -> None:
    """decision.v1 -> exports/decisions/dt=YYYY-MM-DD/<record>-s<seq>.csv. Same key on redelivery."""
    if body.get("schema") != "decision.v1":
        raise ValueError(f"not a decision.v1 message: {sorted(body)}")
    rid, seq = body["record_id"], int(body["seq"])
    with db.tx() as conn:
        rec = conn.execute("SELECT title, doc_type FROM intake.records WHERE id=%s", (rid,)).fetchone()
    row = {**body, **(rec or {})}
    day = str(body.get("decided_at", ""))[:10] or dt.date.today().isoformat()
    key = f"exports/decisions/dt={day}/{rid}-s{seq}.csv"
    data = _csv([row])
    aws.s3().put_object(Bucket=settings().export_bucket, Key=key, Body=data, ContentType="text/csv")
    with db.tx() as conn:
        db.event(conn, rid, seq, "EXPORTED", "exporter", {"bucket": settings().export_bucket, "key": key,
                                                          "bytes": len(data), "csv": data.decode(), "outcome": body["outcome"],
                                                          "message_id": meta.get("message_id")})
        conn.execute("UPDATE intake.records SET status=%s, updated_at=now() WHERE id=%s", (body["outcome"], rid))
    log.info("decision exported", extra={"record_id": rid, "seq": seq, "stage": "EXPORTED", "data": {"key": key}})
# @learn:end export-decision


def batch_export() -> dict[str, Any]:
    """Every exported decision so far as one Parquet file plus the same rows as CSV."""
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT e.record_id, e.seq, r.title, r.doc_type, e.detail->>'outcome' AS outcome, e.at AS exported_at"
            " FROM intake.record_events e JOIN intake.records r ON r.id = e.record_id"
            " WHERE e.stage = 'EXPORTED' ORDER BY e.id").fetchall()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    table = pa.Table.from_pylist([{**r, "exported_at": r["exported_at"].isoformat()} for r in rows],
                                 schema=pa.schema([("record_id", pa.string()), ("seq", pa.int32()), ("title", pa.string()),
                                                   ("doc_type", pa.string()), ("outcome", pa.string()),
                                                   ("exported_at", pa.string())]))
    pbuf = io.BytesIO()
    pq.write_table(table, pbuf)
    base = f"exports/batch/{stamp}"
    aws.s3().put_object(Bucket=settings().export_bucket, Key=base + ".parquet", Body=pbuf.getvalue())
    cbuf = io.StringIO()
    w = csv.writer(cbuf)
    w.writerow(table.column_names)
    for r in table.to_pylist():
        w.writerow(r.values())
    aws.s3().put_object(Bucket=settings().export_bucket, Key=base + ".csv", Body=cbuf.getvalue().encode())
    return {"rows": len(rows), "parquet": base + ".parquet", "csv": base + ".csv", "parquet_bytes": len(pbuf.getvalue())}
