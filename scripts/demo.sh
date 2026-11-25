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
start_bg api .venv/bin/uvicorn rmflow.api:app --host 127.0.0.1 --port 8890
wait_http http://127.0.0.1:8890/v1/health 60
echo
echo "  intake API   http://127.0.0.1:8890/docs"
echo "  logs         .runtime/*.log   stop: scripts/stop.sh"
