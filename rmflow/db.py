"""Postgres access (psycopg 3) and the tiny migration runner for the intake schema."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
_pools: dict[str, ConnectionPool] = {}


def pool(dsn: str | None = None) -> ConnectionPool:
    dsn = dsn or settings().pg_dsn
    p = _pools.get(dsn)
    if p is None:
        p = ConnectionPool(dsn, min_size=1, max_size=12, kwargs={"row_factory": dict_row}, open=True)
        _pools[dsn] = p
    return p


@contextmanager
def tx(dsn: str | None = None) -> Iterator[psycopg.Connection[dict[str, Any]]]:
    """One transaction; commits on success, rolls back on any exception."""
    with pool(dsn).connection() as conn:
        with conn.transaction():
            yield conn  # type: ignore[misc]


def jsonb(v: Any) -> Jsonb:
    return Jsonb(v)


def migrate(dsn: str | None = None) -> list[str]:
    """Apply rmflow/migrations/*.sql in name order, once each. Returns the newly applied names."""
    applied: list[str] = []
    with psycopg.connect(dsn or settings().pg_dsn, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS intake")
        conn.execute("CREATE TABLE IF NOT EXISTS intake.schema_migrations (name text PRIMARY KEY, at timestamptz NOT NULL DEFAULT now())")
        # Serialise concurrent runners (demo + tests) on an advisory lock.
        conn.execute("SELECT pg_advisory_lock(424242)")
        try:
            done = {r[0] for r in conn.execute("SELECT name FROM intake.schema_migrations")}
            for f in sorted(MIGRATIONS.glob("*.sql")):
                if f.name in done:
                    continue
                with conn.transaction():
                    conn.execute(f.read_text())  # type: ignore[arg-type]
                    conn.execute("INSERT INTO intake.schema_migrations(name) VALUES (%s)", (f.name,))
                applied.append(f.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(424242)")
    return applied


def event(conn: psycopg.Connection[Any], record_id: str, seq: int, stage: str, actor: str, detail: dict[str, Any]) -> None:
    """Append one step of the record's handoff timeline."""
    conn.execute(
        "INSERT INTO intake.record_events(record_id, seq, stage, actor, detail) VALUES (%s,%s,%s,%s,%s)",
        (record_id, seq, stage, actor, Jsonb(detail)),
    )
