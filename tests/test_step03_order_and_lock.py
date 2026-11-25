"""Step 03: one record's steps run in seq order on one worker, even across an ownership handoff."""
from __future__ import annotations

import random
import threading
import time
import uuid
from collections import deque
from typing import Any

import pytest

from rmflow import db, intake, locks, membership, sqsloop
from rmflow.ring import HashRing
from rmflow.worker import FencedOut, Worker

BODY = {"title": "ordered", "doc_type": "claim", "fields": {}}


def _record_with_versions(n: int) -> str:
    rid = intake.submit("acme-portal", "k-" + uuid.uuid4().hex, BODY).body["record_id"]
    for _ in range(n - 1):
        intake.revise("acme-portal", rid, "r-" + uuid.uuid4().hex, BODY)
    return rid


def _applied(rid: str) -> list[int]:
    with db.tx() as conn:
        return [r["seq"] for r in conn.execute(
            "SELECT seq FROM intake.record_events WHERE record_id=%s AND stage='APPLIED' ORDER BY id", (rid,))]


def _only(worker: str):
    rg = HashRing([worker])
    return lambda: (rg, 1)


# @learn:test-order
def test_steps_apply_in_seq_order_even_when_delivered_shuffled():
    """SQS standard queues reorder and redeliver. Deliver seq 1..6 shuffled, with one duplicate."""
    rid = _record_with_versions(6)
    w = Worker("w1", ring_fn=_only("w1"))
    msgs = [{"record_id": rid, "seq": s} for s in (5, 2, 6, 1, 3, 4, 2)]
    queue: deque[dict[str, Any]] = deque(msgs)
    for _ in range(200):
        if not queue:
            break
        m = queue.popleft()
        try:
            w.handle(m)
        except sqsloop.Retry:
            queue.append(m)            # redelivered later, like a visibility timeout
    print("\napplied order:", _applied(rid))
    assert _applied(rid) == [1, 2, 3, 4, 5, 6]
# @learn:end test-order


def test_two_owners_during_a_handoff_never_overlap_on_one_record():
    """During a ring change the old and the new owner can both believe they own the record.
    The Redis lock must keep them from running its steps at the same time."""
    rid = _record_with_versions(8)
    membership.r().delete(f"rm:probe:{rid}", f"rm:probe:max:{rid}")

    def slow(worker: Worker, body: dict[str, Any], token: int) -> str:
        time.sleep(0.03)
        with db.tx() as conn:
            db.event(conn, body["record_id"], int(body["seq"]), "APPLIED", f"worker:{worker.id}", {"token": token})
        return "APPLIED"

    old = Worker("w2", ring_fn=_only("w2"), process=slow, probe=True)
    new = Worker("w4", ring_fn=_only("w4"), process=slow, probe=True)
    queue: deque[dict[str, Any]] = deque({"record_id": rid, "seq": s} for s in range(1, 9))
    for s in range(1, 9):
        queue.append({"record_id": rid, "seq": s})     # every step delivered to both owners
    qlock = threading.Lock()

    def run(w: Worker) -> None:
        for _ in range(400):
            with qlock:
                if not queue:
                    return
                m = queue.popleft()
            try:
                w.handle(m)
            except sqsloop.Retry:
                time.sleep(0.005)
                with qlock:
                    queue.append(m)
    ts = [threading.Thread(target=run, args=(w,)) for w in (old, new)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    overlap = int(membership.r().get(f"rm:probe:max:{rid}") or 0)
    print(f"\nmax workers inside one record at once: {overlap}; applied {_applied(rid)}")
    assert overlap == 1
    assert _applied(rid) == list(range(1, 9))


def test_stale_owner_is_fenced_out_after_its_lock_expired():
    rid = _record_with_versions(1)
    w_old, w_new = Worker("w2", ring_fn=_only("w2")), Worker("w4", ring_fn=_only("w4"))
    stale = locks.acquire(rid, "w2")
    assert stale is not None
    membership.r().delete(f"rm:lock:{rid}")            # its lock expired while it was paused
    assert w_new.handle({"record_id": rid, "seq": 1}) == "APPLIED"
    with pytest.raises(FencedOut):
        w_old._commit(rid, 1, stale, "APPLIED")


def test_non_owner_forwards_instead_of_processing(aws_resources):
    rid = _record_with_versions(1)
    rg = HashRing(["w1", "w3"])
    me = "w3" if rg.owner(rid) == "w1" else "w1"
    w = Worker(me, ring_fn=lambda: (rg, 7))
    assert w.handle({"record_id": rid, "seq": 1}) == "forwarded"
    assert _applied(rid) == []
    random.seed(0)
