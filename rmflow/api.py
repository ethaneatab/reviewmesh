"""Intake + validation API (FastAPI, port 8890)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import httpx

from . import auth, db, intake, logs, membership, ring
from .config import settings

log = logs.setup("intake")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.migrate()
    yield


app = FastAPI(title="reviewmesh intake", version="1.0.0", lifespan=_lifespan)


class RecordIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    doc_type: Literal["invoice", "contract", "claim", "kyc"]
    fields: dict[str, Any] = Field(default_factory=dict)
    filename: str | None = None
    document_b64: str | None = None
    document_text: str | None = None


def _key(idempotency_key: str | None) -> str:
    if not idempotency_key or not (8 <= len(idempotency_key) <= 128):
        raise HTTPException(400, "Idempotency-Key header (8-128 chars) is required")
    return idempotency_key


def _respond(out: intake.Outcome) -> JSONResponse:
    headers = {"Idempotent-Replay": "true"} if out.replayed else {}
    return JSONResponse(out.body, status_code=out.status, headers=headers)


@app.get("/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/records")
def create_record(body: RecordIn, claims: dict[str, Any] = Depends(auth.principal),
                  idempotency_key: str | None = Header(default=None)) -> JSONResponse:
    auth.require(claims, "submitter", "ops")
    key = _key(idempotency_key)
    try:
        out = intake.submit(claims["sub"], key, body.model_dump(exclude_none=True), store=_store())
    except intake.KeyReuse:
        raise HTTPException(422, "Idempotency-Key was already used with a different request body")
    log.info("record submitted" if not out.replayed else "idempotent replay",
             extra={"record_id": out.body.get("record_id"), "stage": "SUBMITTED"})
    return _respond(out)


@app.post("/v1/records/{record_id}/revisions")
def revise_record(record_id: str, body: RecordIn, claims: dict[str, Any] = Depends(auth.principal),
                  idempotency_key: str | None = Header(default=None)) -> JSONResponse:
    auth.require(claims, "submitter", "ops")
    key = _key(idempotency_key)
    try:
        out = intake.revise(claims["sub"], record_id, key, body.model_dump(exclude_none=True), store=_store())
    except intake.KeyReuse:
        raise HTTPException(422, "Idempotency-Key was already used with a different request body")
    return _respond(out)


@app.get("/v1/records/{record_id}")
def read_record(record_id: str) -> dict[str, Any]:
    rec = intake.get_record(record_id)
    if rec is None:
        raise HTTPException(404, "no such record")
    return rec


# @learn:timeline-merge
@app.get("/v1/records/{record_id}/timeline")
def timeline(record_id: str) -> dict[str, Any]:
    """One time-ordered list of every handoff state, from both sides (Python events + Java audit)."""
    rec = intake.get_record(record_id)
    if rec is None:
        raise HTTPException(404, "no such record")
    items = [{"at": e["at"].isoformat(), "source": "intake", "stage": e["stage"], "actor": e["actor"], "seq": e["seq"],
              "detail": e["detail"]} for e in rec["events"]]
    audit_ok = True
    try:
        r = httpx.get(f"{settings().routing_url}/v1/audit/records/{record_id}", timeout=2,
                      headers={"Authorization": "Bearer " + auth.mint("intake-api", "service", 60)})
        r.raise_for_status()
        for a in r.json()["events"]:
            items.append({"at": a["at"], "source": "audit", "stage": a["action"], "actor": a["actor"], "seq": a["seq"],
                          "detail": {**a["detail"], "from": a["from_status"], "to": a["to_status"], "task_id": a["task_id"]}})
    except httpx.HTTPError:
        audit_ok = False          # the Java side is down: show what we have, and say so
    items.sort(key=lambda i: i["at"])
    return {"record_id": record_id, "status": rec["status"], "trace_id": rec["trace_id"], "audit_available": audit_ok,
            "items": items}
# @learn:end timeline-merge


def _store() -> intake.StoreFn:
    from .storage import store_in_s3
    return store_in_s3


# ---- ring: who owns what, and the scale-out / scale-in buttons ---------------------------------

WORKER_PORTS = {"w1": 8892, "w2": 8893, "w3": 8894, "w4": 8895}


def _record_ids(limit: int = 2000) -> list[str]:
    with db.tx() as conn:
        return [r["id"] for r in conn.execute("SELECT id FROM intake.records ORDER BY created_at DESC LIMIT %s", (limit,))]


@app.get("/v1/ring")
def ring_view(sample: int = 300) -> dict[str, Any]:
    rg, epoch = membership.current_ring(max_age_s=0)
    keys = _record_ids(sample)
    placed = [rg.place(k) for k in keys] if rg.nodes else []
    counts: dict[str, int] = {n: 0 for n in rg.nodes}
    for p in placed:
        counts[p.owner] += 1
    return {"epoch": epoch, "kind": rg.kind, "vnodes": rg.vnodes, "members": membership.all_members(),
            "live": list(rg.nodes), "points": rg.points(), "counts": counts,
            "keys": [{"key": p.key, "angle": round(p.angle, 3), "owner": p.owner, "vnode": p.vnode} for p in placed],
            "history": membership.history()[:10]}


def _scale(worker: str, path: str) -> dict[str, Any]:
    before = membership.live_members()
    keys = _record_ids()
    r = httpx.post(f"http://127.0.0.1:{WORKER_PORTS[worker]}{path}", timeout=5)
    r.raise_for_status()
    after = membership.live_members()
    mv = ring.moved(keys, before, after) if before and after else []
    return {"change": r.json(), "keys_checked": len(keys), "moved": len(mv),
            "moved_fraction": round(len(mv) / len(keys), 4) if keys else None,
            "expected_fraction": round(abs(len(after) - len(before)) / max(len(after), len(before)), 4),
            "moved_sample": [{"key": k, "from": a, "to": b} for k, a, b in mv[:20]]}


@app.post("/v1/ring/scale-out")
def scale_out(worker: str = "w4") -> dict[str, Any]:
    return _scale(worker, "/join")


@app.post("/v1/ring/scale-in")
def scale_in(worker: str = "w4") -> dict[str, Any]:
    return _scale(worker, "/leave")
