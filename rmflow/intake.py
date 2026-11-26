"""Intake: accept a record (or a revision of one) exactly once per idempotency key."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import psycopg

from . import db, lab

DOC_TYPES = ("invoice", "contract", "claim", "kyc")


@dataclass
class Outcome:
    status: int
    body: dict[str, Any]
    replayed: bool = False


class KeyReuse(Exception):
    """Same idempotency key, different request body: the client has a bug, refuse loudly."""


def request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_id_for(client_id: str, key: str) -> str:
    # Derived from the key, not random: a retry that races past the guard still lands on the same id.
    if lab.sabotaged("no_idempotency"):
        return "rec_" + secrets.token_hex(8)
    return "rec_" + hashlib.sha256(f"{client_id}\x00{key}".encode()).hexdigest()[:16]


# Hook for step 02: store the document in S3 inside the same transaction.
StoreFn = Callable[[psycopg.Connection[Any], str, int, dict[str, Any], str], dict[str, Any]]


def _noop_store(conn: psycopg.Connection[Any], record_id: str, seq: int, payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
    return {}


# @learn:idempotency-guard
def _claim_key(conn: psycopg.Connection[Any], client_id: str, key: str, digest: str,
               record_id: str, seq: int) -> Outcome | None:
    """Insert the key row first. If it already exists, wait for its owner and replay its answer."""
    if lab.sabotaged("no_idempotency"):
        return None
    row = conn.execute(
        "INSERT INTO intake.idempotency_keys(client_id, key, request_sha256, record_id, seq, response)"
        " VALUES (%s,%s,%s,%s,%s,'{}'::jsonb) ON CONFLICT DO NOTHING RETURNING key",
        (client_id, key, digest, record_id, seq),
    ).fetchone()
    if row is not None:
        return None  # we own the key; the caller does the work in this same transaction
    # Someone else holds it. FOR UPDATE blocks until their transaction commits.
    prev = conn.execute(
        "SELECT request_sha256, response FROM intake.idempotency_keys WHERE client_id=%s AND key=%s FOR UPDATE",
        (client_id, key),
    ).fetchone()
    assert prev is not None
    if prev["request_sha256"] != digest:
        raise KeyReuse(key)
    return Outcome(200, prev["response"], replayed=True)
# @learn:end idempotency-guard


def submit(client_id: str, key: str, payload: dict[str, Any], store: StoreFn = _noop_store,
           dsn: str | None = None) -> Outcome:
    digest = request_hash(payload)
    record_id = record_id_for(client_id, key)
    trace_id = uuid.uuid4().hex
    with db.tx(dsn) as conn:
        replay = _claim_key(conn, client_id, key, digest, record_id, 1)
        if replay is not None:
            return replay
        conn.execute(
            "INSERT INTO intake.records(id, client_id, title, doc_type, status, latest_seq, trace_id)"
            " VALUES (%s,%s,%s,%s,'RECEIVED',1,%s)",
            (record_id, client_id, payload["title"], payload["doc_type"], trace_id),
        )
        stored = store(conn, record_id, 1, payload, trace_id)
        conn.execute(
            "INSERT INTO intake.record_versions(record_id, seq, fields, doc_sha256, s3_key) VALUES (%s,1,%s,%s,%s)",
            (record_id, db.jsonb(payload.get("fields", {})), stored.get("sha256"), stored.get("s3_key")),
        )
        db.event(conn, record_id, 1, "SUBMITTED", f"client:{client_id}",
                 {"idempotency_key": key, "request_sha256": digest, "title": payload["title"], **stored})
        body = {"record_id": record_id, "seq": 1, "status": stored.get("status", "RECEIVED"), "trace_id": trace_id}
        if stored:
            conn.execute("UPDATE intake.records SET status=%s WHERE id=%s", (body["status"], record_id))
        _remember(conn, client_id, key, body)
    return Outcome(201, body)


def revise(client_id: str, record_id: str, key: str, payload: dict[str, Any], store: StoreFn = _noop_store,
           dsn: str | None = None) -> Outcome:
    """A corrected version of an existing record: it becomes the next seq of that record."""
    digest = request_hash({"record_id": record_id, **payload})
    with db.tx(dsn) as conn:
        rec = conn.execute("SELECT trace_id, latest_seq FROM intake.records WHERE id=%s AND client_id=%s",
                           (record_id, client_id)).fetchone()
        if rec is None:
            return Outcome(404, {"error": "no such record"})
        replay = _claim_key(conn, client_id, key, digest, record_id, rec["latest_seq"] + 1)
        if replay is not None:
            return replay
        seq = conn.execute(
            "UPDATE intake.records SET latest_seq = latest_seq + 1, updated_at = now() WHERE id=%s RETURNING latest_seq",
            (record_id,),
        ).fetchone()["latest_seq"]  # type: ignore[index]
        if not lab.sabotaged("no_idempotency"):
            conn.execute("UPDATE intake.idempotency_keys SET seq=%s WHERE client_id=%s AND key=%s", (seq, client_id, key))
        stored = store(conn, record_id, seq, payload, rec["trace_id"])
        conn.execute(
            "INSERT INTO intake.record_versions(record_id, seq, fields, doc_sha256, s3_key) VALUES (%s,%s,%s,%s,%s)",
            (record_id, seq, db.jsonb(payload.get("fields", {})), stored.get("sha256"), stored.get("s3_key")),
        )
        db.event(conn, record_id, seq, "REVISED", f"client:{client_id}", {"idempotency_key": key, **stored})
        body = {"record_id": record_id, "seq": seq, "status": stored.get("status", "RECEIVED"), "trace_id": rec["trace_id"]}
        _remember(conn, client_id, key, body)
    return Outcome(201, body)


def _remember(conn: psycopg.Connection[Any], client_id: str, key: str, body: dict[str, Any]) -> None:
    if not lab.sabotaged("no_idempotency"):
        conn.execute("UPDATE intake.idempotency_keys SET response=%s WHERE client_id=%s AND key=%s",
                     (db.jsonb(body), client_id, key))


def get_record(record_id: str, dsn: str | None = None) -> dict[str, Any] | None:
    with db.tx(dsn) as conn:
        rec = conn.execute("SELECT * FROM intake.records WHERE id=%s", (record_id,)).fetchone()
        if rec is None:
            return None
        rec["versions"] = conn.execute(
            "SELECT seq, fields, doc_sha256, s3_key, created_at FROM intake.record_versions WHERE record_id=%s ORDER BY seq",
            (record_id,)).fetchall()
        rec["events"] = conn.execute(
            "SELECT id, seq, stage, actor, detail, at FROM intake.record_events WHERE record_id=%s ORDER BY id",
            (record_id,)).fetchall()
        return rec
