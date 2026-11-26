"""Intake + validation API (FastAPI, port 8890)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, cache, db, exporter, intake, logs, membership, ops, ring, traffic
from .config import ROOT, settings

log = logs.setup("intake")


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.migrate()
    yield


app = FastAPI(title="reviewmesh intake", version="1.0.0", lifespan=_lifespan)
from . import learn  # noqa: E402

app.include_router(learn.router)
# Teaching videos (docs/videos/<part>.mp4). A missing file is a plain 404; the page shows "视频待生成".
app.mount("/videos", StaticFiles(directory=str(ROOT / "docs" / "videos"), check_dir=False), name="videos")


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


@app.get("/v1/ops/overview")
def ops_overview() -> dict[str, Any]:
    return ops.overview()


@app.get("/metrics")
def metrics() -> Any:
    from fastapi.responses import PlainTextResponse
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    ops.overview()          # refresh the gauges on scrape
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)


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
    except intake.KeyReuse as exc:
        raise HTTPException(422, "Idempotency-Key was already used with a different request body") from exc
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
    except intake.KeyReuse as exc:
        raise HTTPException(422, "Idempotency-Key was already used with a different request body") from exc
    return _respond(out)


@app.get("/v1/records/{record_id}")
def read_record(record_id: str) -> dict[str, Any]:
    rec = intake.get_record(record_id)
    if rec is None:
        raise HTTPException(404, "no such record")
    return rec


@app.get("/v1/records/{record_id}/status")
def record_status(record_id: str) -> dict[str, Any]:
    """The hot path: clients poll this. Served from Redis for a second before touching Postgres."""
    return cache.record_status(record_id)


@app.post("/v1/exports")
def export_batch(claims: dict[str, Any] = Depends(auth.principal)) -> dict[str, Any]:
    auth.require(claims, "ops")
    return exporter.batch_export()


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
            "moved_sample": [{"key": k, "from": a, "to": b} for k, a, b in mv[:20]],
            "moved_keys": [{"key": k, "from": a, "to": b} for k, a, b in mv]}


@app.post("/v1/ring/scale-out")
def scale_out(worker: str = "w4", _: Any = Depends(auth.ops_or_learn)) -> dict[str, Any]:
    return _scale(worker, "/join")


@app.post("/v1/ring/scale-in")
def scale_in(worker: str = "w4", _: Any = Depends(auth.ops_or_learn)) -> dict[str, Any]:
    return _scale(worker, "/leave")


# ---- rollout drill: synthetic traffic, and operator actions proxied for the learn page ---------

@app.post("/v1/rollout/traffic")
def rollout_traffic(seconds: float = 30, rps: int = 100, _: Any = Depends(auth.ops_or_learn)) -> dict[str, Any]:
    return traffic.start(min(seconds, 120), min(rps, 300))


@app.get("/v1/rollout/traffic")
def rollout_traffic_status() -> dict[str, Any]:
    return traffic.status()


@app.post("/v1/rollout/{action}")
def rollout_action(action: Literal["start", "advance", "reset", "fault"], rate: float = 0.0,
                   claims: dict[str, Any] = Depends(auth.ops_or_learn)) -> Any:
    """Forwards an operator action to the Java rollout controller with an ops token."""
    token = auth.mint(claims["sub"], "ops", 60)
    params = {"rate": rate} if action == "fault" else None
    r = httpx.post(f"{settings().routing_url}/v1/rollout/{action}", params=params, timeout=5,
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise HTTPException(r.status_code, r.text)
    return r.json()
