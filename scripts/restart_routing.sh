#!/usr/bin/env bash
# Restart only the Java service (by its pid file), e.g. to step through the reviewer migration:
#   RM_FLYWAY_TARGET=2 RM_MIGRATION_PHASE=DUAL_WRITE scripts/restart_routing.sh
#   RM_MIGRATION_PHASE=NEW_ONLY scripts/restart_routing.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/lib.sh
export JAVA_HOME=${JAVA_HOME_21:-${JAVA_HOME:-/opt/homebrew/opt/openjdk@21}}  # CI: setup-java sets JAVA_HOME
if [ -f .runtime/routing.pid ]; then
  pid=$(cat .runtime/routing.pid)
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
  rm -f .runtime/routing.pid
fi
RM_SEED_DEMO=${RM_SEED_DEMO:-1} start_bg routing "$JAVA_HOME/bin/java" -Xmx256m -XX:+UseSerialGC -jar routing-svc/target/routing-svc-1.0.0.jar
wait_http http://127.0.0.1:8891/actuator/health 90
