"""Tests get their own database (reviewmesh_test), Redis db 1, bucket and queue names.

Tests marked `live` talk to the running stack from scripts/demo.sh over HTTP instead, and read the
demo database directly; they are skipped when the stack is not up.
"""
from __future__ import annotations

import os

_TEST_ENV = {
    "RM_PG_DSN": "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh_test",
    "RM_REDIS_URL": "redis://127.0.0.1:63590/1",
    "RM_INBOX_BUCKET": "rm-test-inbox",
    "RM_EXPORT_BUCKET": "rm-test-exports",
    "RM_INTAKE_QUEUE": "t-rm-intake",
    "RM_WORK_QUEUE_PREFIX": "t-rm-work-",
    "RM_WORK_DLQ": "t-rm-work-dlq",
    "RM_HANDOFF_QUEUE": "t-rm-handoff",
    "RM_DECISION_QUEUE": "t-rm-decisions",
}
for k, v in _TEST_ENV.items():
    os.environ.setdefault(k, v)

import httpx  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from rmflow import auth, aws, bootstrap, db  # noqa: E402

LIVE_API = "http://127.0.0.1:8890"
LIVE_ROUTING = "http://127.0.0.1:8891"
LIVE_DSN = "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> None:
    db.migrate()


@pytest.fixture(scope="session")
def aws_resources() -> dict[str, str]:
    bootstrap.buckets()
    qs = bootstrap.queues()
    for url in qs.values():
        aws.sqs().purge_queue(QueueUrl=url)
    return qs


@pytest.fixture
def submitter_token() -> str:
    return auth.mint("acme-portal", "submitter")


@pytest.fixture
def client(aws_resources):
    from fastapi.testclient import TestClient

    from rmflow.api import app
    with TestClient(app) as c:
        yield c


def _up(url: str) -> bool:
    try:
        return httpx.get(url, timeout=1.5).status_code < 500
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="session")
def live():
    """The running stack. Skips the test when demo.sh is not up."""
    if not _up(LIVE_API + "/v1/health"):
        pytest.skip("live stack not running (scripts/demo.sh)")

    class Live:
        api = LIVE_API
        routing = LIVE_ROUTING
        token = auth.mint("acme-portal", "submitter")

        @staticmethod
        def sql(q: str, *args):
            with psycopg.connect(LIVE_DSN, row_factory=dict_row, autocommit=True) as c:
                return c.execute(q, args).fetchall()
    return Live
