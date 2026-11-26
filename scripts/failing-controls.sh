#!/usr/bin/env bash
# Prove the hard tests are alive: with each protection switched off its test must FAIL,
# with it on the same test must PASS. Writes docs/results/failing-controls.txt.
# Needs Postgres, Redis and LocalStack up (docker-compose -p reviewmesh up -d); not the services.
set -uo pipefail
cd "$(dirname "$0")/.."
export JAVA_HOME=${JAVA_HOME_21:-/opt/homebrew/opt/openjdk@21}
OUT=docs/results/failing-controls.txt
: > "$OUT"
status=0

py_case() {  # py_case <switch> <test node>
  local sw=$1 node=$2
  for mode in off on; do
    if [ $mode = off ]; then env=RM_LAB_SABOTAGE=$sw; label="protection OFF ($sw)"; else env=RM_LAB_SABOTAGE=; label="protection ON"; fi
    res=$(env $env .venv/bin/python -m pytest "$node" -q -p no:cacheprovider 2>&1)
    rc=$?
    { echo "### $node — $label"; echo "$res" | grep -E "^E  |AssertionError|passed|failed" | head -4; echo; } >> "$OUT"
    if [ $mode = off ] && [ $rc -eq 0 ]; then echo "!! $sw: test still passes with the protection off"; status=1; fi
    if [ $mode = on ] && [ $rc -ne 0 ]; then echo "!! $sw: test fails with the protection on"; status=1; fi
  done
}

py_case no_idempotency tests/test_step01_idempotency.py::test_concurrent_retries_create_exactly_one_record
py_case modulo_hash    tests/test_step03_ring.py::test_scale_out_moves_about_one_over_n_plus_one
py_case no_order_gate  tests/test_step03_order_and_lock.py::test_steps_apply_in_seq_order_even_when_delivered_shuffled
py_case no_lock        tests/test_step03_order_and_lock.py::test_two_owners_during_a_handoff_never_overlap_on_one_record

for mode in off on; do
  if [ $mode = off ]; then prop="-Drm.lab.sabotage=no_rollback"; label="protection OFF (no_rollback)"; else prop=""; label="protection ON"; fi
  res=$(cd routing-svc && /opt/homebrew/bin/mvn -q test -Dtest='RolloutPolicyTest#errorRegressionRollsBackToZeroWithinFiveSeconds' $prop 2>&1)
  rc=$?
  { echo "### RolloutPolicyTest.errorRegressionRollsBackToZeroWithinFiveSeconds — $label";
    echo "$res" | grep -E "fault at|never rolled back|Tests run:" | head -3; [ $rc -eq 0 ] && echo "BUILD SUCCESS"; echo; } >> "$OUT"
  if [ $mode = off ] && [ $rc -eq 0 ]; then echo "!! no_rollback: test still passes"; status=1; fi
  if [ $mode = on ] && [ $rc -ne 0 ]; then echo "!! no_rollback: test fails with the protection on"; status=1; fi
done
cat "$OUT"
[ $status -eq 0 ] && echo "all 5 controls: red with the protection off, green with it on"
exit $status
