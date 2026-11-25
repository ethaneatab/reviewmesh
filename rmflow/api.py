"""Intake + validation API (FastAPI, port 8890)."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import auth, db, intake, logs

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


def _store() -> intake.StoreFn:
    return intake._noop_store
