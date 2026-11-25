#!/usr/bin/env bash
# One command: containers, schema, every service. Processes keep running in the background;
# stop them with scripts/stop.sh (by pid) and the containers with docker-compose -p reviewmesh stop.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh
COMPOSE=${COMPOSE:-/opt/homebrew/bin/docker-compose}
PY=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11
[ -x .venv/bin/python ] || { $PY -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
$COMPOSE -p reviewmesh up -d --wait
.venv/bin/python -m rmflow.bootstrap          # schema, buckets, queues + DLQs, Lambda, S3 notification
start_bg api .venv/bin/uvicorn rmflow.api:app --host 127.0.0.1 --port 8890
start_bg pipeline .venv/bin/python -m rmflow.pipeline
# Three workers in the ring, a fourth on standby for the scale-out demo.
start_bg w1 .venv/bin/python -m rmflow.worker --id w1 --port 8892
start_bg w2 .venv/bin/python -m rmflow.worker --id w2 --port 8893
start_bg w3 .venv/bin/python -m rmflow.worker --id w3 --port 8894
start_bg w4 .venv/bin/python -m rmflow.worker --id w4 --port 8895 --standby
wait_http http://127.0.0.1:8890/v1/health 60
for p in 8892 8893 8894 8895; do wait_http http://127.0.0.1:$p/health 60; done
echo
echo "  intake API   http://127.0.0.1:8890/docs"
echo "  workers      w1..w3 on 8892-8894, w4 (standby) on 8895"
echo "  logs         .runtime/*.log   stop: scripts/stop.sh"
