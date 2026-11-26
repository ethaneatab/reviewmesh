"""Operational overview: queue depths (incl. DLQs), stuck records, worker liveness, and alerts.

The same conditions are Prometheus alert rules in ops/prometheus/alerts.yml; this module lets the
UI show them without running Prometheus.
"""
from __future__ import annotations

from typing import Any

import httpx
from prometheus_client import Gauge

from . import aws, db, membership
from .bootstrap import WORKERS
from .config import settings

QUEUE_DEPTH = Gauge("reviewmesh_queue_depth", "Visible messages per SQS queue", ["queue"])
STUCK = Gauge("reviewmesh_records_stuck", "Records still STORED after 20 s (lost S3 events)")
STATUS = Gauge("reviewmesh_records_by_status", "Records per status", ["status"])
WORKER_UP = Gauge("reviewmesh_worker_up", "1 if the worker heartbeats", ["worker"])


def queue_names() -> list[str]:
    s = settings()
    base = [s.intake_queue, s.handoff_queue, s.decision_queue] + [s.work_queue_prefix + w for w in WORKERS]
    return base + [s.intake_queue + "-dlq", s.handoff_queue + "-dlq", s.decision_queue + "-dlq", s.work_dlq]


# @learn:ops-alerts
def overview() -> dict[str, Any]:
    depths: dict[str, int] = {}
    for q in queue_names():
        try:
            a = aws.sqs().get_queue_attributes(QueueUrl=aws.queue_url(q), AttributeNames=["ApproximateNumberOfMessages"])
            depths[q] = int(a["Attributes"]["ApproximateNumberOfMessages"])
        except Exception:
            depths[q] = -1
        QUEUE_DEPTH.labels(q).set(depths[q])
    with db.tx() as conn:
        by_status = {r["status"]: r["n"] for r in conn.execute("SELECT status, count(*) AS n FROM intake.records GROUP BY status")}
        row = conn.execute("SELECT count(*) AS n FROM intake.records WHERE status='STORED'"
                           " AND updated_at < now() - interval '20 seconds'").fetchone()
        stuck = row["n"] if row else 0
    for k, v in by_status.items():
        STATUS.labels(k).set(v)
    STUCK.set(stuck)
    members = membership.all_members()
    for w, info in members.items():
        WORKER_UP.labels(w).set(1 if info.get("alive") else 0)
    rollout: dict[str, Any] = {}
    try:
        rollout = httpx.get(settings().routing_url + "/v1/rollout", timeout=2).json()
    except httpx.HTTPError:
        pass
    alerts = []
    for q, n in depths.items():
        if q.endswith("dlq") and n > 0:
            alerts.append({"name": "DeadLetters", "severity": "page", "detail": f"{n} message(s) parked in {q}"})
    if stuck:
        alerts.append({"name": "StuckRecords", "severity": "warn", "detail": f"{stuck} record(s) STORED for over 20 s"})
    for w, info in members.items():
        if info.get("active") and not info.get("alive"):
            alerts.append({"name": "WorkerDown", "severity": "page", "detail": f"{w} stopped heartbeating"})
    if rollout.get("status") == "ROLLED_BACK":
        rb = next((e for e in rollout.get("events", []) if e["kind"] == "ROLLBACK"), None)
        alerts.append({"name": "RolloutRolledBack", "severity": "warn", "detail": rb["reason"] if rb else "routing-v2 rolled back"})
    return {"queues": depths, "records_by_status": by_status, "stuck": stuck, "workers": members,
            "rollout": {k: rollout.get(k) for k in ("percent", "status", "window")}, "alerts": alerts}
# @learn:end ops-alerts
