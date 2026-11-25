# Shared helpers for demo.sh / stop.sh. Every process we start gets a pid file in .runtime/,
# and we only ever stop processes by those pids.
RUNTIME=.runtime
mkdir -p "$RUNTIME"

start_bg() {  # start_bg <name> <cmd...>
  local name=$1; shift
  if [ -f "$RUNTIME/$name.pid" ] && kill -0 "$(cat "$RUNTIME/$name.pid")" 2>/dev/null; then
    echo "  $name already running (pid $(cat "$RUNTIME/$name.pid"))"; return 0
  fi
  nohup "$@" > "$RUNTIME/$name.log" 2>&1 &
  echo $! > "$RUNTIME/$name.pid"
  echo "  started $name (pid $!)"
}

wait_http() {  # wait_http <url> <seconds>
  local url=$1 n=${2:-60}
  for _ in $(seq "$n"); do curl -fs -o /dev/null "$url" && return 0; sleep 1; done
  echo "timed out waiting for $url" >&2; return 1
}
