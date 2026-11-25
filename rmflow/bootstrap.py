"""Create buckets, queues, the S3-triggered Lambda and the intake schema. Safe to run again.

    .venv/bin/python -m rmflow.bootstrap
"""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from . import aws, db, logs
from .config import ROOT, settings

log = logs.setup("bootstrap")
WORKERS = ("w1", "w2", "w3", "w4")
# Bounded retries: a message that fails this many receives is parked in the DLQ.
MAX_RECEIVES = 4
# Distributions vendored into the Lambda zip, *with* their dist-info: scramp reads its own
# version through importlib.metadata at import time and fails without it.
VENDORED = ("pg8000", "scramp", "asn1crypto", "python-dateutil", "six")


def _queue(name: str, dlq_arn: str | None, visibility: int) -> str:
    attrs: dict[str, str] = {"VisibilityTimeout": str(visibility)}
    if dlq_arn:
        attrs["RedrivePolicy"] = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": str(MAX_RECEIVES)})
    sqs = aws.sqs()
    url = str(sqs.create_queue(QueueName=name)["QueueUrl"])
    sqs.set_queue_attributes(QueueUrl=url, Attributes=attrs)
    return url


def _arn(url: str) -> str:
    return str(aws.sqs().get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"])


def queues() -> dict[str, str]:
    s = settings()
    out: dict[str, str] = {}
    pairs = [(s.intake_queue, s.intake_queue + "-dlq"), (s.handoff_queue, s.handoff_queue + "-dlq"),
             (s.decision_queue, s.decision_queue + "-dlq")]
    pairs += [(s.work_queue_prefix + w, s.work_dlq) for w in WORKERS]
    for main, dlq in pairs:
        dlq_url = _queue(dlq, None, 30)
        out[dlq] = dlq_url
        out[main] = _queue(main, _arn(dlq_url), 10)
    return out


def buckets() -> None:
    s = settings()
    for b in (s.inbox_bucket, s.export_bucket):
        try:
            aws.s3().head_bucket(Bucket=b)
        except ClientError:
            aws.s3().create_bucket(Bucket=b)


def lambda_zip() -> bytes:
    """Deterministic zip (fixed timestamps), so an unchanged handler has an unchanged hash."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def put(path: Path, arcname: str) -> None:
            info = zipfile.ZipInfo(arcname, date_time=(2024, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
        put(ROOT / "lambdas/s3_intake/handler.py", "handler.py")
        for dist_name in VENDORED:
            dist = importlib.metadata.distribution(dist_name)
            for f in sorted(dist.files or [], key=str):
                if "__pycache__" in f.parts or f.suffix == ".pyc" or str(f).startswith(".."):
                    continue
                put(Path(str(dist.locate_file(f))), str(f))
    return buf.getvalue()


def _lambda_env() -> dict[str, str]:
    return {
        "RM_AWS_ENDPOINT": os.environ.get("RM_LAMBDA_AWS_ENDPOINT", "http://localstack:4566"),
        "RM_PG_HOST": os.environ.get("RM_LAMBDA_PG_HOST", "postgres"),
        "RM_PG_PORT": "5432",
        "RM_PG_DB": os.environ.get("RM_LAMBDA_PG_DB", "reviewmesh"),
        "RM_PG_USER": "reviewmesh",
        "RM_PG_PASSWORD": os.environ.get("RM_LAMBDA_PG_PASSWORD", "reviewmesh-dev"),
        "RM_INTAKE_QUEUE": settings().intake_queue,
    }


def _wait_active(lam: Any, name: str) -> None:
    for _ in range(240):
        cfg = lam.get_function(FunctionName=name)["Configuration"]
        if cfg.get("State") == "Active" and cfg.get("LastUpdateStatus") in (None, "Successful"):
            return
        time.sleep(0.5)
    raise RuntimeError(f"lambda {name} did not become Active")


# @learn:lambda-deploy
def deploy_lambda() -> str:
    """Create or update the function only when the code or env changed.

    Updating swaps LocalStack's runtime container; S3 events that arrive during the swap can be lost,
    so an unchanged deploy must be a no-op (and the reconciler covers the rest).
    """
    s = settings()
    lam = aws.client("lambda")
    code = lambda_zip()
    digest = base64.b64encode(hashlib.sha256(code).digest()).decode()
    env = {"Variables": _lambda_env()}
    try:
        cfg = lam.get_function(FunctionName=s.lambda_name)["Configuration"]
    except ClientError:
        lam.create_function(FunctionName=s.lambda_name, Runtime="python3.11", Handler="handler.handler",
                            Role="arn:aws:iam::000000000000:role/rm-s3-intake", Code={"ZipFile": code},
                            Timeout=20, MemorySize=256, Environment=env)
        log.info("lambda created")
    else:
        if cfg.get("CodeSha256") != digest:
            _wait_active(lam, s.lambda_name)
            lam.update_function_code(FunctionName=s.lambda_name, ZipFile=code)
            log.info("lambda code updated")
        if cfg.get("Environment", {}).get("Variables") != env["Variables"]:
            _wait_active(lam, s.lambda_name)
            lam.update_function_configuration(FunctionName=s.lambda_name, Environment=env)
    _wait_active(lam, s.lambda_name)
    return str(lam.get_function(FunctionName=s.lambda_name)["Configuration"]["FunctionArn"])
# @learn:end lambda-deploy


def wire_s3(arn: str) -> None:
    s = settings()
    try:
        aws.client("lambda").add_permission(
            FunctionName=s.lambda_name, StatementId="s3-inbox", Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com", SourceArn=f"arn:aws:s3:::{s.inbox_bucket}")
    except ClientError:
        pass
    aws.s3().put_bucket_notification_configuration(
        Bucket=s.inbox_bucket,
        NotificationConfiguration={"LambdaFunctionConfigurations": [
            {"LambdaFunctionArn": arn, "Events": ["s3:ObjectCreated:*"],
             "Filter": {"Key": {"FilterRules": [{"Name": "prefix", "Value": "inbox/"}]}}}]})


def main() -> None:
    applied = db.migrate()
    buckets()
    qs = queues()
    wire_s3(deploy_lambda())
    log.info("bootstrap ok", extra={"data": {"migrations": applied, "queues": sorted(qs)}})


if __name__ == "__main__":
    main()
