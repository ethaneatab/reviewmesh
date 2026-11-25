"""A partition worker: owns the records the ring gives it and runs each record's steps in seq order.

    .venv/bin/python -m rmflow.worker --id w1 --port 8892 [--standby]
"""
from __future__ import annotations

import argparse
import collections
import threading
import time
from collections.abc import Callable
from typing import Any

from . import db, lab, locks, logs, membership, sqsloop
from .config import settings
from .ring import HashRing, ModuloRing

log = logs.setup("worker")
RingFn = Callable[[], tuple[HashRing | ModuloRing, int]]
MAX_HOPS = 5


class FencedOut(Exception):
    """Our lock expired and a newer owner already wrote this record. Drop our result."""


def _applied_event(worker: Worker, body: dict[str, Any], token: int, conn: Any) -> str:
    db.event(conn, body["record_id"], int(body["seq"]), "APPLIED", f"worker:{worker.id}", {"token": token})
    return "APPLIED"


ProcessFn = Callable[["Worker", dict[str, Any], int], str]


def default_process(worker: Worker, body: dict[str, Any], token: int) -> str:
    with db.tx() as conn:
        return _applied_event(worker, body, token, conn)


class Worker:
    def __init__(self, worker_id: str, ring_fn: RingFn = membership.current_ring,
                 process: ProcessFn = default_process, probe: bool = False):
        self.id = worker_id
        self.ring_fn = ring_fn
        self.process = process
        self.probe = probe
        self.stats: collections.Counter[str] = collections.Counter()
        self.recent: collections.deque[dict[str, Any]] = collections.deque(maxlen=30)

    # -- ordering gate -------------------------------------------------------------------------
    # @learn:order-gate
    def _gate(self, rid: str, seq: int) -> str:
        """apply = this is the next step; duplicate = already done; wait = an earlier seq is missing."""
        with db.tx() as conn:
            conn.execute("INSERT INTO intake.workflow_state(record_id) VALUES (%s) ON CONFLICT DO NOTHING", (rid,))
            last = conn.execute("SELECT last_seq FROM intake.workflow_state WHERE record_id=%s", (rid,)).fetchone()["last_seq"]
        if lab.sabotaged("no_order_gate"):
            return "apply"
        if seq <= last:
            return "duplicate"
        return "apply" if seq == last + 1 else "wait"
    # @learn:end order-gate

    # @learn:fenced-commit
    def _commit(self, rid: str, seq: int, token: int, stage: str) -> None:
        with db.tx() as conn:
            cur = conn.execute(
                "UPDATE intake.workflow_state SET last_seq = GREATEST(last_seq, %s), fence = %s, owner = %s,"
                " stage = %s, updated_at = now() WHERE record_id = %s AND fence < %s",
                (seq, token, self.id, stage, rid, token))
            if cur.rowcount == 0:
                raise FencedOut(f"{rid} seq {seq}: token {token} is older than the stored fence")
    # @learn:end fenced-commit

    def _forward(self, body: dict[str, Any], owner: str, epoch: int) -> None:
        hops = int(body.get("hops", 0)) + 1
        if hops > MAX_HOPS:
            raise RuntimeError(f"{body['record_id']} bounced {hops} times between workers")
        fwd = {**body, "hops": hops, "partition": {**body.get("partition", {}), "owner": owner, "epoch": epoch,
                                                   "forwarded_by": self.id}}
        sqsloop.send(settings().work_queue_prefix + owner, fwd)
        with db.tx() as conn:
            db.event(conn, body["record_id"], int(body["seq"]), "FORWARDED", f"worker:{self.id}",
                     {"to": owner, "epoch": epoch, "hops": hops})
        self.stats["forwarded"] += 1

    def _probe(self, rid: str, delta: int) -> None:
        if not self.probe:
            return
        n = int(membership.r().incrby(f"rm:probe:{rid}", delta))
        if delta > 0:
            membership.r().eval("local m = tonumber(redis.call('get', KEYS[1]) or '0') "
                                "if tonumber(ARGV[1]) > m then redis.call('set', KEYS[1], ARGV[1]) end return 1",
                                1, f"rm:probe:max:{rid}", n)

    # @learn:worker-handle
    def handle(self, body: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
        rid, seq = body["record_id"], int(body["seq"])
        ring, epoch = self.ring_fn()
        owner = ring.owner(rid)
        if owner != self.id:                       # ring moved since this was queued: hand it on
            self._forward(body, owner, epoch)
            return "forwarded"
        token = locks.acquire(rid, self.id)
        if token is None:                          # previous owner is still mid-step
            self.stats["lock_busy"] += 1
            raise sqsloop.Retry(1, f"{rid} locked by {locks.holder(rid)}")
        try:
            gate = self._gate(rid, seq)
            if gate == "duplicate":
                self.stats["duplicate"] += 1
                return "duplicate"
            if gate == "wait":
                self.stats["out_of_order_wait"] += 1
                raise sqsloop.Retry(1, f"{rid} seq {seq} waits for an earlier step")
            with db.tx() as conn:
                db.event(conn, rid, seq, "WORKER_PICKED", f"worker:{self.id}",
                         {"worker": self.id, "epoch": epoch, "fence_token": token, "ring": ring.kind,
                          "receive_count": (meta or {}).get("receive_count")})
            self._probe(rid, +1)
            try:
                stage = self.process(self, body, token)
            finally:
                self._probe(rid, -1)
            self._commit(rid, seq, token, stage)
            self.stats["processed"] += 1
            self.recent.appendleft({"record_id": rid, "seq": seq, "stage": stage, "token": token, "at": time.time()})
            return stage
        finally:
            locks.release(rid, self.id, token)
    # @learn:end worker-handle


# --------------------------------------------------------------------------------------------
# Process entry point: queue consumers + heartbeat + a small admin API on the worker's port.

def build_admin(w: Worker, port: int) -> Any:
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    app = FastAPI(title=f"reviewmesh worker {w.id}")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "worker": w.id}

    @app.get("/state")
    def state() -> dict[str, Any]:
        info = membership.all_members().get(w.id, {})
        return {"worker": w.id, "port": port, "active": info.get("active"), "stats": dict(w.stats),
                "recent": list(w.recent), "epoch": membership.epoch()}

    @app.post("/join")
    def join() -> dict[str, Any]:
        return membership.set_active(w.id, True, f"{w.id} joined (scale-out)")

    @app.post("/leave")
    def leave() -> dict[str, Any]:
        return membership.set_active(w.id, False, f"{w.id} left (scale-in)")

    @app.get("/metrics")
    def metrics() -> PlainTextResponse:
        lines = [f'reviewmesh_worker_events_total{{worker="{w.id}",kind="{k}"}} {v}' for k, v in sorted(w.stats.items())]
        return PlainTextResponse(generate_latest().decode() + "\n".join(lines) + "\n", media_type=CONTENT_TYPE_LATEST)

    return app


def main() -> None:
    import uvicorn

    from . import process as steps
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--standby", action="store_true", help="start outside the ring; POST /join to scale out")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    db.migrate()
    w = Worker(a.id, process=steps.run_steps)
    if a.standby and a.id in membership.all_members():
        membership.register(a.id, a.port, active=bool(membership.all_members()[a.id].get("active")))
    else:
        membership.register(a.id, a.port, active=not a.standby)
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(2):
            membership.heartbeat(a.id)
    threading.Thread(target=beat, daemon=True).start()
    for _ in range(a.threads):
        threading.Thread(target=sqsloop.consume, args=(settings().work_queue_prefix + a.id, w.handle, stop),
                         kwargs={"batch": 1}, daemon=True).start()
    log.info("worker up", extra={"worker": a.id, "data": {"port": a.port, "standby": a.standby}})
    try:
        uvicorn.run(build_admin(w, a.port), host="127.0.0.1", port=a.port, log_level="warning")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
