"""Bearer tokens. The Java service issues them at /v1/auth/login; both sides share an HS256 key."""
from __future__ import annotations

import time
from typing import Any

import jwt
from fastapi import Header, HTTPException

from .config import settings

ISSUER = "reviewmesh"


def mint(sub: str, role: str, ttl_s: int = 3600) -> str:
    """Used by tests and by the learn sample client; production tokens come from the Java login."""
    now = int(time.time())
    return jwt.encode({"sub": sub, "role": role, "iss": ISSUER, "iat": now, "exp": now + ttl_s},
                      settings().jwt_secret, algorithm="HS256")


def verify(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings().jwt_secret, algorithms=["HS256"], issuer=ISSUER)


def principal(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    try:
        return verify(authorization.split(" ", 1)[1])
    except jwt.PyJWTError as exc:
        raise HTTPException(401, f"bad token: {exc}") from exc


def require(claims: dict[str, Any], *roles: str) -> None:
    if claims.get("role") not in roles:
        raise HTTPException(403, f"role {claims.get('role')} cannot do this")


def ops_or_learn(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Operator actions. In learn mode (local demo) the teaching page may trigger them without a login."""
    if settings().learn_mode and not authorization:
        return {"sub": "learn-mode", "role": "ops"}
    claims = principal(authorization)
    require(claims, "ops")
    return claims
