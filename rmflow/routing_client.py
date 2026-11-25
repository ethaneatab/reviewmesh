"""REST client for the Java routing service, with bounded exponential retries and a fallback route."""
from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

import httpx

from . import auth, logs
from .config import settings

log = logs.setup("routing-client")
ATTEMPTS = 4
BASE_DELAY_S = 0.2
MAX_DELAY_S = 1.6
TIMEOUT_S = 2.0
FALLBACK_QUEUE = "manual-triage"


def decision_request(rid: str, seq: int, doc_type: str, title: str, validation: dict[str, Any],
                     attempt: int, trace_id: str | None) -> dict[str, Any]:
    """Builds the routing-decision.v1 request. contracts/routing-decision.v1.json pins its shape."""
    return {"record_id": rid, "seq": seq, "doc_type": doc_type, "title": title,
            "risk_score": int(validation["risk_score"]),
            "validation": {"passed": bool(validation["passed"]), "issues": list(validation["issues"])},
            "attempt": attempt, "trace_id": trace_id or ""}


def backoff(attempt: int, rnd: random.Random = random.Random()) -> float:
    """0.2 s, 0.4 s, 0.8 s … capped at 1.6 s, with ±20 % jitter so retries from many workers spread out."""
    d = min(BASE_DELAY_S * 2 ** (attempt - 1), MAX_DELAY_S)
    return float(d * rnd.uniform(0.8, 1.2))


# @learn:routing-retry
def route(rid: str, seq: int, doc_type: str, title: str, validation: dict[str, Any], trace_id: str | None,
          worker: str, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Ask Java for a route. Retry 5xx / timeouts a bounded number of times, then fall back to a human."""
    client = http or httpx.Client(timeout=TIMEOUT_S)
    token = auth.mint(f"worker:{worker}", "service", ttl_s=300)
    errors: list[str] = []
    for attempt in range(1, ATTEMPTS + 1):
        body = decision_request(rid, seq, doc_type, title, validation, attempt, trace_id)
        try:
            r = client.post(settings().routing_url + "/v1/routing/decisions", json=body,
                            headers={"Authorization": f"Bearer {token}", "X-Trace-Id": trace_id or ""})
            if r.status_code < 400:
                return {**r.json(), "attempts": attempt, "fallback": False, "errors": errors}
            errors.append(f"HTTP {r.status_code}")
            if r.status_code < 500:
                break                       # a 4xx will not get better by retrying
        except httpx.HTTPError as exc:
            errors.append(type(exc).__name__)
        if attempt < ATTEMPTS:
            sleep(backoff(attempt))
    log.warning("routing unavailable; using fallback route", extra={"record_id": rid, "seq": seq, "data": {"errors": errors}})
    return {"decision_id": None, "record_id": rid, "seq": seq, "queue": FALLBACK_QUEUE, "priority": 2,
            "engine": "fallback", "reason": f"routing unavailable after {len(errors)} attempts: {', '.join(errors)}",
            "attempts": len(errors), "fallback": True, "errors": errors}
# @learn:end routing-retry
