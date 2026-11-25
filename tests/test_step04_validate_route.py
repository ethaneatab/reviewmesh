"""Step 04: validation, the routing call (bounded retries + fallback) and the handoff message."""
from __future__ import annotations

import time
import uuid

import httpx
import pytest

from rmflow import contracts, process, routing_client, validation

GOOD = {"sniff": "pdf", "size": 1200, "sha256": "abc"}


def test_clean_invoice_passes_with_low_risk():
    r = validation.validate("invoice", {"amount": "880.00", "vendor": "Northwind"}, "abc", GOOD)
    assert r["passed"] and r["risk_score"] == 10


def test_problems_are_listed_not_raised():
    r = validation.validate("invoice", {"amount": "12,000"}, "abc", {**GOOD, "sniff": "unknown", "sha256": "zzz"})
    assert not r["passed"]
    assert {c["check"] for c in r["checks"] if not c["ok"]} == {"file_type", "integrity", "required_fields", "amount_format"}


def test_large_amount_is_high_risk():
    assert validation.validate("invoice", {"amount": "25000", "vendor": "X"}, None, GOOD)["risk_score"] >= 70


def _client(statuses: list[int | Exception]) -> tuple[httpx.Client, list[dict]]:
    calls: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(__import__("json").loads(req.content))
        s = statuses[min(len(calls) - 1, len(statuses) - 1)]
        if isinstance(s, Exception):
            raise s
        body = contracts.load("routing-decision.v1.json")["response"] if s < 400 else {"error": "x"}
        return httpx.Response(s, json=body)
    return httpx.Client(transport=httpx.MockTransport(handler)), calls


VAL = {"passed": True, "issues": [], "risk_score": 10}


# @learn:test-retry
def test_transient_errors_are_retried_then_succeed():
    http, calls = _client([503, 503, 200])
    slept: list[float] = []
    out = routing_client.route("rec_x", 1, "invoice", "t", VAL, "tr", "w1", http=http, sleep=slept.append)
    assert out["fallback"] is False and out["attempts"] == 3
    assert [c["attempt"] for c in calls] == [1, 2, 3]
    assert 0.16 <= slept[0] <= 0.24 and 0.32 <= slept[1] <= 0.48     # 0.2 s then 0.4 s, ±20 %


def test_retries_are_bounded_and_end_in_the_fallback_route():
    http, calls = _client([httpx.ConnectTimeout("slow")])
    slept: list[float] = []
    out = routing_client.route("rec_x", 1, "invoice", "t", VAL, "tr", "w1", http=http, sleep=slept.append)
    assert len(calls) == routing_client.ATTEMPTS == 4
    assert out["fallback"] is True and out["queue"] == "manual-triage" and out["engine"] == "fallback"
    assert sum(slept) <= 1.4 * 1.2          # 0.2 + 0.4 + 0.8, plus jitter: the worker never stalls long
# @learn:end test-retry


def test_client_errors_are_not_retried():
    http, calls = _client([400])
    out = routing_client.route("rec_x", 1, "invoice", "t", VAL, "tr", "w1", http=http, sleep=lambda s: None)
    assert len(calls) == 1 and out["fallback"] is True


# ---- contracts: the Python side of contracts/*.json -----------------------------------------

def test_routing_request_matches_the_contract_exactly():
    snap = contracts.load("routing-decision.v1.json")["request"]
    built = routing_client.decision_request("rec_1", 1, "invoice", "t", {"passed": True, "issues": ["a"], "risk_score": 10},
                                            1, "trace")
    assert contracts.shape(built) == contracts.shape(snap)


def test_handoff_message_matches_the_contract_exactly():
    snap = contracts.load("handoff.v1.json")["message"]
    built = process.handoff_message({"record_id": "rec_1", "seq": 1, "s3_key": "k"},
                                    {"title": "t", "doc_type": "invoice", "trace_id": "tr"},
                                    {"decision_id": "dec_1", "queue": "finance", "priority": 3, "engine": "v1"},
                                    {"passed": True, "issues": ["a"], "risk_score": 10}, "w1")
    assert contracts.shape(built) == contracts.shape(snap)


def test_breaking_change_detector_flags_removed_and_retyped_fields():
    snap = {"a": 1, "b": "x", "c": {"d": True}}
    assert contracts.breaking_changes(snap, {"a": 1, "b": "x", "c": {"d": True}, "new": 5}) == []
    assert contracts.breaking_changes(snap, {"a": "1", "c": {}}) == ["$.a: integer became string", "$.b: removed", "$.c.d: removed"]


@pytest.mark.live
def test_live_record_becomes_an_open_task_in_the_java_queue(live):
    import base64
    from rmflow import auth
    pdf = base64.b64encode(b"%PDF-1.4\n% live\n").decode()
    r = httpx.post(live.api + "/v1/records", headers={"Authorization": f"Bearer {live.token}", "Idempotency-Key": uuid.uuid4().hex},
                   json={"title": "live handoff", "doc_type": "contract", "filename": "c.pdf", "document_b64": pdf,
                         "fields": {"counterparty": "Contoso"}})
    rid = r.json()["record_id"]
    tok = auth.mint("rita", "reviewer")
    task = None
    for _ in range(60):
        resp = httpx.get(f"{live.routing}/v1/tasks/by-record/{rid}", headers={"Authorization": f"Bearer {tok}"})
        if resp.status_code == 200:
            task = resp.json()
            break
        time.sleep(0.5)
    assert task and task["queue"] == "legal" and task["status"] == "OPEN"
    assert contracts.breaking_changes(contracts.load("routing-decision.v1.json")["response"],
                                      live.sql("SELECT detail FROM intake.record_events WHERE record_id=%s AND stage='ROUTED'", rid)[0]["detail"]) == []
