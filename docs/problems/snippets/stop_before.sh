# Before q06: send the signal and move on; the next start raced the old process for the port.
# @learn:before-stop-by-pid
for f in .runtime/*.pid; do
  pid=$(cat "$f")
  kill "$pid"
  rm -f "$f"
done
# @learn:end before-stop-by-pid
