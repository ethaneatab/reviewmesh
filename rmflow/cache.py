"""Redis cache-aside for hot lookups (record status polled by clients)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from . import db
from .membership import r

TTL_S = 1


# @learn:status-cache
def record_status(record_id: str) -> dict[str, Any]:
    key = f"rm:status:{record_id}"
    hit = r().get(key)
    if hit:
        return {**json.loads(hit), "cache": "hit"}
    with db.tx() as conn:
        row = conn.execute("SELECT id, status, latest_seq, updated_at FROM intake.records WHERE id=%s", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "no such record")
    out = {"record_id": row["id"], "status": row["status"], "seq": row["latest_seq"], "updated_at": row["updated_at"].isoformat()}
    r().set(key, json.dumps(out), ex=TTL_S)   # short TTL: a status may lag by at most one second
    return {**out, "cache": "miss"}
# @learn:end status-cache
