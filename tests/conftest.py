"""Tests use their own database (reviewmesh_test) and Redis db 1, never the demo data."""
from __future__ import annotations

import os

os.environ.setdefault("RM_PG_DSN", "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh_test")
os.environ.setdefault("RM_REDIS_URL", "redis://127.0.0.1:63590/1")

import pytest  # noqa: E402

from rmflow import auth, db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    db.migrate()


@pytest.fixture
def submitter_token() -> str:
    return auth.mint("acme-portal", "submitter")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from rmflow.api import app
    with TestClient(app) as c:
        yield c
