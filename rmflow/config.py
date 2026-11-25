"""Runtime settings. Everything comes from the environment; defaults are local-dev placeholders."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project_repo_url() -> str:
    # The one place the GitHub account is defined is project.json at the repo root.
    return str(json.loads((ROOT / "project.json").read_text())["repo_url"])


@dataclass(frozen=True)
class Settings:
    pg_dsn: str
    redis_url: str
    aws_endpoint: str
    aws_region: str
    routing_url: str
    jwt_secret: str
    learn_mode: bool
    seed_demo: bool
    repo_url: str
    inbox_bucket: str
    export_bucket: str
    intake_queue: str
    work_queue_prefix: str
    work_dlq: str
    handoff_queue: str
    decision_queue: str
    lambda_name: str


@lru_cache
def settings() -> Settings:
    e = os.environ.get
    return Settings(
        pg_dsn=e("RM_PG_DSN", "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh"),
        redis_url=e("RM_REDIS_URL", "redis://127.0.0.1:63590/0"),
        aws_endpoint=e("RM_AWS_ENDPOINT", "http://127.0.0.1:45690"),
        aws_region=e("AWS_DEFAULT_REGION", "us-east-1"),
        routing_url=e("RM_ROUTING_URL", "http://127.0.0.1:8891"),
        jwt_secret=e("RM_JWT_SECRET", "dev-only-jwt-signing-key-not-for-production-use"),
        learn_mode=e("RM_LEARN_MODE", "1") == "1",
        seed_demo=e("RM_SEED_DEMO", "0") == "1",
        repo_url=e("REPO_URL", _project_repo_url()),
        inbox_bucket=e("RM_INBOX_BUCKET", "reviewmesh-inbox"),
        export_bucket=e("RM_EXPORT_BUCKET", "reviewmesh-exports"),
        intake_queue=e("RM_INTAKE_QUEUE", "rm-intake"),
        work_queue_prefix=e("RM_WORK_QUEUE_PREFIX", "rm-work-"),
        work_dlq=e("RM_WORK_DLQ", "rm-work-dlq"),
        handoff_queue=e("RM_HANDOFF_QUEUE", "rm-handoff"),
        decision_queue=e("RM_DECISION_QUEUE", "rm-decisions"),
        lambda_name=e("RM_LAMBDA_NAME", "rm-s3-intake"),
    )
