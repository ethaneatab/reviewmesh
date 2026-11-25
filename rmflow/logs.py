"""Structured JSON logs. Every line carries the record id, seq, stage and trace id when known."""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

_FIELDS = ("record_id", "seq", "stage", "trace_id", "worker", "attempt", "queue")


class JsonFormatter(logging.Formatter):
    def format(self, rec: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(rec.created)) + f".{int(rec.msecs):03d}Z",
            "level": rec.levelname.lower(),
            "logger": rec.name,
            "msg": rec.getMessage(),
        }
        for f in _FIELDS:
            v = getattr(rec, f, None)
            if v is not None:
                out[f] = v
        extra = getattr(rec, "data", None)
        if extra:
            out["data"] = extra
        if rec.exc_info:
            out["exc"] = self.formatException(rec.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def setup(service: str) -> logging.Logger:
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter())
        root.handlers = [h]
        root.setLevel(logging.INFO)
        for noisy in ("botocore", "boto3", "urllib3", "httpx", "uvicorn.access"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(service)
