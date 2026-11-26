"""boto3 clients pointed at LocalStack (or real AWS when RM_AWS_ENDPOINT is empty)."""
from __future__ import annotations

import os
from functools import cache
from typing import Any

import boto3
from botocore.config import Config

from .config import settings

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")       # LocalStack accepts any value
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")


@cache
def client(name: str) -> Any:
    s = settings()
    cfg = Config(retries={"max_attempts": 3, "mode": "standard"}, s3={"addressing_style": "path"},
                 connect_timeout=3, read_timeout=25)
    return boto3.client(name, endpoint_url=s.aws_endpoint or None, region_name=s.aws_region, config=cfg)  # type: ignore[call-overload]


def s3() -> Any:
    return client("s3")


def sqs() -> Any:
    return client("sqs")


@cache
def queue_url(name: str) -> str:
    return str(sqs().get_queue_url(QueueName=name)["QueueUrl"])
