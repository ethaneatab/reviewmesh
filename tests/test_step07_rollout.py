"""Step 07: staged rollout of routing v2; an error-rate regression rolls it back automatically."""
from __future__ import annotations

import time

import httpx
import pytest

ROLLBACK_DEADLINE_S = 10


@pytest.mark.live
def test_live_fault_in_v2_triggers_automatic_rollback(live):
    api = live.api
    httpx.post(api + "/v1/rollout/reset", timeout=5).raise_for_status()
    httpx.post(api + "/v1/rollout/start", timeout=5).raise_for_status()
    httpx.post(api + "/v1/rollout/advance", timeout=5).raise_for_status()           # 1 % -> 10 %
    httpx.post(api + "/v1/rollout/traffic", params={"seconds": 25, "rps": 100}, timeout=5)
    time.sleep(2)
    state = httpx.get(live.routing + "/v1/rollout", timeout=5).json()
    assert state["percent"] == 10 and state["status"] == "RAMPING"
    t0 = time.time()
    httpx.post(api + "/v1/rollout/fault", params={"rate": 0.4}, timeout=5).raise_for_status()
    while time.time() - t0 < ROLLBACK_DEADLINE_S + 5:
        state = httpx.get(live.routing + "/v1/rollout", timeout=5).json()
        if state["percent"] == 0:
            break
        time.sleep(0.25)
    took = time.time() - t0
    rb = [e for e in state["events"] if e["kind"] == "ROLLBACK"]
    print(f"\nrolled back {took:.1f}s after the fault: {rb[0]['reason'] if rb else None}")
    httpx.post(api + "/v1/rollout/reset", timeout=5)
    assert state["status"] == "ROLLED_BACK" and state["percent"] == 0
    assert took <= ROLLBACK_DEADLINE_S
    assert "v2 error rate" in rb[0]["reason"]
