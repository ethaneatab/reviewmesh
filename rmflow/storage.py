"""Store the submitted document in S3, inside the intake transaction (see intake.StoreFn)."""
from __future__ import annotations

import base64
import hashlib
from typing import Any

import psycopg

from . import aws
from .config import settings


def document_bytes(payload: dict[str, Any]) -> tuple[bytes, str]:
    if payload.get("document_b64"):
        return base64.b64decode(payload["document_b64"]), payload.get("filename") or "document.pdf"
    text = payload.get("document_text") or ""
    return text.encode(), payload.get("filename") or "document.txt"


# @learn:s3-store
def store_in_s3(conn: psycopg.Connection[Any], record_id: str, seq: int, payload: dict[str, Any],
                trace_id: str) -> dict[str, Any]:
    """Last write before commit: the S3 event fires the Lambda, which expects the row to exist."""
    data, filename = document_bytes(payload)
    key = f"inbox/{record_id}/v{seq}/{filename}"
    aws.s3().put_object(Bucket=settings().inbox_bucket, Key=key, Body=data,
                        Metadata={"record-id": record_id, "seq": str(seq), "trace-id": trace_id})
    return {"s3_key": key, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "status": "STORED"}
# @learn:end s3-store
