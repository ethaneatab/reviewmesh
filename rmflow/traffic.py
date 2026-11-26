"""Synthetic routing traffic for rollout drills: dry-run calls through the real Java endpoint."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from . import auth
from .config import settings

_state: dict[str, Any] = {"running": False, "sent": 0, "engines": {}, "until": 0.0}
_lock = threading.Lock()


def status() -> dict[str, Any]:
    with _lock:
        return {**_state, "engines": dict(_state["engines"])}


def _one(client: httpx.Client, token: str) -> None:
    rid = "syn_" + uuid.uuid4().hex[:16]
    body = {"record_id": rid, "seq": 1, "doc_type": "invoice", "title": "synthetic", "risk_score": 20,
            "validation": {"passed": True, "issues": []}, "attempt": 1, "trace_id": ""}
    try:
        r = client.post(settings().routing_url + "/v1/routing/decisions", json=body,
                        headers={"Authorization": f"Bearer {token}", "X-Dry-Run": "true"})
        eng = r.json().get("engine", "error") if r.status_code == 200 else f"http_{r.status_code}"
    except httpx.HTTPError:
        eng = "error"
    with _lock:
        _state["sent"] += 1
        _state["engines"][eng] = _state["engines"].get(eng, 0) + 1


def run(seconds: float, rps: int) -> None:
    token = auth.mint("traffic-generator", "service", ttl_s=int(seconds) + 60)
    with _lock:
        _state.update(running=True, sent=0, engines={}, until=time.time() + seconds)
    try:
        with httpx.Client(timeout=2) as client, ThreadPoolExecutor(8) as pool:
            end = time.time() + seconds
            while time.time() < end:
                tick = time.time()
                for _ in range(max(1, rps // 10)):
                    pool.submit(_one, client, token)
                time.sleep(max(0.0, 0.1 - (time.time() - tick)))
    finally:
        with _lock:
            _state["running"] = False


def start(seconds: float = 30, rps: int = 100) -> dict[str, Any]:
    if status()["running"]:
        return status()
    threading.Thread(target=run, args=(seconds, rps), daemon=True).start()
    time.sleep(0.05)
    return status()
