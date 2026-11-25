"""Background process: dispatcher (intake queue -> owner worker) and reconciler (lost S3 events).

    .venv/bin/python -m rmflow.pipeline
"""
from __future__ import annotations

import signal
import threading
from typing import Any

from . import db, logs, membership, sqsloop
from .config import settings

log = logs.setup("pipeline")
STUCK_AFTER_S = 20


class Poison(Exception):
    """A message we can never handle; retries will run out and it lands in the DLQ."""


# @learn:dispatch-partition
def dispatch(body: dict[str, Any], meta: dict[str, Any]) -> None:
    """Find the record's owner on the ring and move the message to that worker's queue."""
    if body.get("schema") != "intake.v1" or "record_id" not in body or "seq" not in body:
        raise Poison(f"not an intake.v1 message: {sorted(body)}")
    rid, seq = body["record_id"], int(body["seq"])
    ring, epoch = membership.current_ring()
    if not ring.nodes:
        raise sqsloop.Retry(2, "no live workers in the ring")
    p = ring.place(rid)
    partition = {"owner": p.owner, "epoch": epoch, "ring": ring.kind, "members": list(ring.nodes),
                 "key_hash": f"{p.hash:016x}", "angle": round(p.angle, 3), "vnode": p.vnode,
                 "vnode_angle": round(p.vnode_angle, 3)}
    sqsloop.send(settings().work_queue_prefix + p.owner, {**body, "partition": partition})
    with db.tx() as conn:
        db.event(conn, rid, seq, "SQS_RECEIVED", "dispatcher", {"message": body, **meta})
        db.event(conn, rid, seq, "PARTITIONED", "dispatcher", partition)
        conn.execute("UPDATE intake.records SET status='PARTITIONED', updated_at=now()"
                     " WHERE id=%s AND status IN ('STORED','RECEIVED','QUEUED')", (rid,))
    log.info("dispatched", extra={"record_id": rid, "seq": seq, "stage": "PARTITIONED", "worker": p.owner})
# @learn:end dispatch-partition


# @learn:reconciler
def reconcile_once() -> int:
    """Fallback path for a lost S3 event: a record still STORED after 20 s is enqueued directly."""
    with db.tx() as conn:
        rows = conn.execute(
            "SELECT r.id, r.latest_seq, r.trace_id, v.s3_key, v.doc_sha256 FROM intake.records r"
            " JOIN intake.record_versions v ON v.record_id = r.id AND v.seq = r.latest_seq"
            " WHERE r.status = 'STORED' AND r.updated_at < now() - make_interval(secs => %s)"
            " ORDER BY r.updated_at LIMIT 50 FOR UPDATE OF r SKIP LOCKED", (STUCK_AFTER_S,)).fetchall()
        for r in rows:
            msg = {"schema": "intake.v1", "record_id": r["id"], "seq": r["latest_seq"], "trace_id": r["trace_id"],
                   "s3_key": r["s3_key"], "sha256": r["doc_sha256"], "via": "reconciler"}
            sqsloop.send(settings().intake_queue, msg)
            db.event(conn, r["id"], r["latest_seq"], "RECONCILED", "reconciler", msg)
            conn.execute("UPDATE intake.records SET status='QUEUED', updated_at=now() WHERE id=%s", (r["id"],))
    return len(rows)
# @learn:end reconciler


def _reconcile_loop(stop: threading.Event) -> None:
    while not stop.wait(5):
        try:
            n = reconcile_once()
            if n:
                log.warning("reconciled stuck records", extra={"data": {"count": n}})
        except Exception:
            log.exception("reconcile failed")


def main() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    db.migrate()
    threads = [
        threading.Thread(target=sqsloop.consume, args=(settings().intake_queue, dispatch, stop), daemon=True),
        threading.Thread(target=_reconcile_loop, args=(stop,), daemon=True),
    ]
    for t in threads:
        t.start()
    log.info("pipeline up")
    stop.wait()


if __name__ == "__main__":
    main()
