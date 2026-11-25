"""Per-record lock in Redis plus a fencing token checked by the database write.

The lock keeps two workers from working on one record at the same time during an ownership
handoff. The lock can still expire under a stalled worker, so every token is also a fence:
Postgres refuses a write whose token is older than the last one it accepted.
"""
from __future__ import annotations

from . import lab
from .membership import r

LOCK_TTL_MS = 15_000
_RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


# @learn:record-lock
def acquire(record_id: str, worker: str) -> int | None:
    token = int(r().incr(f"rm:fence:{record_id}"))
    if lab.sabotaged("no_lock"):
        return token
    ok = r().set(f"rm:lock:{record_id}", f"{worker}:{token}", nx=True, px=LOCK_TTL_MS)
    return token if ok else None


def release(record_id: str, worker: str, token: int) -> None:
    r().eval(_RELEASE, 1, f"rm:lock:{record_id}", f"{worker}:{token}")
# @learn:end record-lock


def holder(record_id: str) -> str | None:
    v = r().get(f"rm:lock:{record_id}")
    return str(v) if v else None
