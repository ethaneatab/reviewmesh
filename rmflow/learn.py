"""Learn mode: drive one sample record through the real pipeline and report each stage from real state.

Nothing here is animated: every stage is "done" only when its row exists in Postgres, its object in S3,
or its audit event in the Java service.
"""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from . import auth, aws, intake, storage
from .config import settings
from .membership import r

router = APIRouter(prefix="/learn/api")

# (id, label, video part, source anchor)
STAGES = [
    ("submit", "提交样例（幂等键）", "p1-intake", "idempotency-guard"),
    ("s3", "文档写入 S3", "p2-s3-lambda", "s3-store"),
    ("lambda", "S3 事件触发 Lambda", "p2-s3-lambda", "lambda-handler"),
    ("sqs", "消息进入 SQS", "p2-s3-lambda", "dispatch-partition"),
    ("partition", "一致性哈希选 worker", "p3-partition", "ring-lookup"),
    ("validate", "校验", "p4-route", "validate"),
    ("route", "路由决定（Java）", "p4-route", "routing-v1"),
    ("claim", "审核员认领", "p5-review", "claim"),
    ("audit", "审计记录", "p5-review", "audit-append"),
    ("export", "结论导出到 S3", "p5-review", "export-decision"),
]
SAMPLE_PDF = b"%PDF-1.4\n% reviewmesh learn sample\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"


def _guard() -> None:
    if not settings().learn_mode:
        raise HTTPException(404, "learn mode is off")


def _java(method: str, path: str, role: str = "service", sub: str = "learn-page") -> Any:
    resp = httpx.request(method, settings().routing_url + path, timeout=5,
                         headers={"Authorization": "Bearer " + auth.mint(sub, role, 120)})
    if resp.status_code >= 400:
        raise HTTPException(resp.status_code, resp.text)
    return resp.json()


@router.post("/runs")
def start_run() -> dict[str, Any]:
    """Submit the sample, then send the very same request again to show the idempotent replay."""
    _guard()
    key = "learn-" + uuid.uuid4().hex[:12]
    body = {"title": f"样例发票 {key[-4:]}", "doc_type": "invoice", "filename": "sample-invoice.pdf",
            "document_b64": base64.b64encode(SAMPLE_PDF).decode(),
            "fields": {"amount": "12800.00", "vendor": "Northwind Traders", "po": "PO-7731"}}
    first = intake.submit("learn-demo", key, body, store=storage.store_in_s3)
    again = intake.submit("learn-demo", key, body, store=storage.store_in_s3)
    rid = first.body["record_id"]
    r().set(f"rm:learn:{rid}", json.dumps({"key": key, "first": {"status": first.status, "body": first.body},
                                           "retry": {"status": again.status, "replayed": again.replayed, "body": again.body}}),
            ex=86400)
    return {"record_id": rid}


def _events(rec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in rec["events"]:
        out.setdefault(e["stage"], e)        # first occurrence of each stage
    return out


@router.get("/runs/{rid}")
def run_state(rid: str) -> dict[str, Any]:
    _guard()
    rec = intake.get_record(rid)
    if rec is None:
        raise HTTPException(404, "no such record")
    ev = _events(rec)
    try:
        audit = _java("GET", f"/v1/audit/records/{rid}")["events"]
    except (HTTPException, httpx.HTTPError):
        audit = []
    by_action = {a["action"]: a for a in audit}
    task = None
    try:
        task = _java("GET", f"/v1/tasks/by-record/{rid}")
    except (HTTPException, httpx.HTTPError):
        pass
    meta = json.loads(r().get(f"rm:learn:{rid}") or "{}")
    data: dict[str, tuple[Any, Any]] = {}
    if "SUBMITTED" in ev:
        data["submit"] = (ev["SUBMITTED"]["at"], {"idempotency_key": meta.get("key"), "first_response": meta.get("first"),
                                                   "retry_same_key": meta.get("retry"),
                                                   "request_sha256": ev["SUBMITTED"]["detail"].get("request_sha256")})
        key = ev["SUBMITTED"]["detail"].get("s3_key")
        if key:
            try:
                h = aws.s3().head_object(Bucket=settings().inbox_bucket, Key=key)
                data["s3"] = (ev["SUBMITTED"]["at"], {"bucket": settings().inbox_bucket, "key": key, "bytes": h["ContentLength"],
                                                       "etag": h["ETag"], "metadata": h["Metadata"]})
            except Exception:  # noqa: BLE001 - object not visible yet
                pass
    for stage, name in (("lambda", "LAMBDA_SEEN"), ("sqs", "SQS_RECEIVED"), ("partition", "PARTITIONED"),
                        ("validate", "VALIDATED"), ("route", "ROUTED"), ("export", "EXPORTED")):
        if name in ev:
            data[stage] = (ev[name]["at"], ev[name]["detail"])
    if "lambda" not in data and "RECONCILED" in ev:
        data["lambda"] = (ev["RECONCILED"]["at"], {"fallback": "reconciler", **ev["RECONCILED"]["detail"]})
    if "partition" in data and "WORKER_PICKED" in ev:
        data["partition"] = (data["partition"][0], {**data["partition"][1], "picked": ev["WORKER_PICKED"]["detail"]})
    if "CLAIMED" in by_action:
        a = by_action["CLAIMED"]
        data["claim"] = (a["at"], {"task_id": a["task_id"], "reviewer": a["actor"], "from": a["from_status"], "to": a["to_status"]})
    decided = next((by_action[k] for k in ("APPROVED", "REJECTED") if k in by_action), None)
    if decided:
        data["audit"] = (decided["at"], {"trail": [{"action": a["action"], "actor": a["actor"],
                                                    "transition": f"{a['from_status'] or '—'} → {a['to_status'] or '—'}"}
                                                   for a in audit]})
    stages = []
    for sid, label, part, anchor in STAGES:
        at, d = data.get(sid, (None, None))
        stages.append({"id": sid, "label": label, "part": part, "anchor": anchor, "status": "done" if d is not None else "pending",
                       "at": at.isoformat() if hasattr(at, "isoformat") else at, "data": d})
    return {"record_id": rid, "status": rec["status"], "task": task, "stages": stages}


def _task_id(rid: str) -> int:
    return int(_java("GET", f"/v1/tasks/by-record/{rid}")["id"])


@router.post("/runs/{rid}/claim")
def claim(rid: str) -> Any:
    _guard()
    return _java("POST", f"/v1/tasks/{_task_id(rid)}/claim", role="reviewer", sub="rita")


@router.post("/runs/{rid}/approve")
def approve(rid: str) -> Any:
    _guard()
    return _java("POST", f"/v1/tasks/{_task_id(rid)}/approve", role="reviewer", sub="rita")


@router.get("/migration")
def migration() -> Any:
    _guard()
    return _java("GET", "/v1/migration/status")
