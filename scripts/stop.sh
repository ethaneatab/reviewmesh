#!/usr/bin/env bash
# Stop only the processes demo.sh started, by the pids it wrote. Never by name.
cd "$(dirname "$0")/.."
for f in .runtime/*.pid; do
  [ -f "$f" ] || continue
  pid=$(cat "$f")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    for _ in $(seq 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
    echo "  stopped $(basename "$f" .pid) ($pid)"
  fi
  rm -f "$f"
done
