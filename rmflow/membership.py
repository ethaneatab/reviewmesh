"""Which workers are in the ring, kept in Redis. Workers heartbeat; join/leave bump the epoch."""
from __future__ import annotations

import json
import threading
import time
from functools import cache
from typing import Any, cast

import redis

from .config import settings
from .ring import HashRing, ModuloRing, make_ring

MEMBERS = "rm:members"
EPOCH = "rm:ring:epoch"
HISTORY = "rm:ring:history"
HEARTBEAT_TTL_S = 6


@cache
def r() -> redis.Redis:
    return redis.Redis.from_url(settings().redis_url, decode_responses=True)


def register(worker: str, port: int, active: bool) -> None:
    r().hset(MEMBERS, worker, json.dumps({"port": port, "active": active, "since": time.time()}))
    heartbeat(worker)


def heartbeat(worker: str) -> None:
    r().set(f"rm:hb:{worker}", "1", ex=HEARTBEAT_TTL_S)


def set_active(worker: str, active: bool, reason: str) -> dict[str, Any]:
    before = live_members()
    info = json.loads(r().hget(MEMBERS, worker) or "{}")
    info["active"] = active
    r().hset(MEMBERS, worker, json.dumps(info))
    epoch = int(r().incr(EPOCH))
    after = live_members()
    entry = {"epoch": epoch, "before": before, "after": after, "reason": reason, "at": time.time()}
    r().lpush(HISTORY, json.dumps(entry))
    r().ltrim(HISTORY, 0, 49)
    _cache.clear()
    return entry


def all_members() -> dict[str, dict[str, Any]]:
    raw = cast("dict[str, str]", r().hgetall(MEMBERS))  # decode_responses=True: str, not bytes
    out = {}
    for w, v in raw.items():
        info = json.loads(v)
        info["alive"] = bool(r().exists(f"rm:hb:{w}"))
        out[w] = info
    return dict(sorted(out.items()))


def live_members() -> list[str]:
    return [w for w, i in all_members().items() if i.get("active") and i.get("alive")]


def epoch() -> int:
    return int(r().get(EPOCH) or 0)


def history() -> list[dict[str, Any]]:
    return [json.loads(x) for x in r().lrange(HISTORY, 0, 49)]


_cache: dict[str, Any] = {}
_lock = threading.Lock()


def current_ring(max_age_s: float = 0.5) -> tuple[HashRing | ModuloRing, int]:
    """The ring for the current live membership, cached for half a second per process."""
    with _lock:
        now = time.time()
        if _cache.get("at", 0) + max_age_s > now:
            return _cache["ring"], _cache["epoch"]
        ring = make_ring(live_members())
        _cache.update(ring=ring, epoch=epoch(), at=now)
        return ring, _cache["epoch"]
