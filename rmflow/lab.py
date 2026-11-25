"""Switches for the failing controls. Each name turns one protection off.

RM_LAB_SABOTAGE=no_idempotency,modulo_hash,no_order_gate,no_lock
The value is read on every call so a test can flip it with monkeypatch.
"""
from __future__ import annotations

import os

KNOWN = {"no_idempotency", "modulo_hash", "no_order_gate", "no_lock"}


def sabotaged(name: str) -> bool:
    assert name in KNOWN, name
    raw = os.environ.get("RM_LAB_SABOTAGE", "")
    return name in {p.strip() for p in raw.split(",") if p.strip()}
