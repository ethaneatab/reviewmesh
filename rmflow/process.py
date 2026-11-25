"""The steps a worker runs for one (record, seq): validate -> route (Java) -> hand off (SQS)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import db, routing_client, sqsloop, validation
from .config import settings

if TYPE_CHECKING:
    from .worker import Worker


def handoff_message(body: dict[str, Any], rec: dict[str, Any], decision: dict[str, Any], result: dict[str, Any],
                    worker: str) -> dict[str, Any]:
    """Builds handoff.v1. contracts/handoff.v1.json pins its shape; the Java consumer parses the same file."""
    return {"schema": "handoff.v1", "record_id": body["record_id"], "seq": int(body["seq"]),
            "decision_id": decision.get("decision_id"), "queue": decision["queue"], "priority": int(decision["priority"]),
            "engine": decision["engine"], "title": rec["title"], "doc_type": rec["doc_type"],
            "s3_key": body.get("s3_key"), "trace_id": rec["trace_id"], "worker": worker,
            "risk_score": int(result["risk_score"]),
            "validation": {"passed": bool(result["passed"]), "issues": list(result["issues"])}}


# @learn:run-steps
def run_steps(worker: Worker, body: dict[str, Any], token: int) -> str:
    rid, seq = body["record_id"], int(body["seq"])
    with db.tx() as conn:
        rec = conn.execute("SELECT title, doc_type, trace_id FROM intake.records WHERE id=%s", (rid,)).fetchone()
        ver = conn.execute("SELECT fields, doc_sha256 FROM intake.record_versions WHERE record_id=%s AND seq=%s",
                           (rid, seq)).fetchone()
    if rec is None or ver is None:
        raise RuntimeError(f"{rid} seq {seq} not found in intake (orphan S3 object?)")
    result = validation.validate(rec["doc_type"], ver["fields"], ver["doc_sha256"], body)
    with db.tx() as conn:
        db.event(conn, rid, seq, "VALIDATED", f"worker:{worker.id}", result)
    decision = routing_client.route(rid, seq, rec["doc_type"], rec["title"], result, rec["trace_id"], worker.id)
    with db.tx() as conn:
        db.event(conn, rid, seq, "ROUTED", f"worker:{worker.id}", decision)
    msg = handoff_message(body, rec, decision, result, worker.id)
    mid = sqsloop.send(settings().handoff_queue, msg)
    with db.tx() as conn:
        db.event(conn, rid, seq, "HANDED_OFF", f"worker:{worker.id}", {"message_id": mid, "queue": settings().handoff_queue,
                                                                         "message": msg})
        conn.execute("UPDATE intake.records SET status='IN_REVIEW', updated_at=now() WHERE id=%s", (rid,))
    return "HANDED_OFF"
# @learn:end run-steps
