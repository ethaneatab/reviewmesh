"""Step 03: consistent hashing moves about 1/(N+1) of the keys when a worker joins."""
from __future__ import annotations

import statistics

from rmflow import ring

KEYS = [f"rec_{i:08x}" for i in range(20_000)]


# @learn:test-ring-migration
def test_scale_out_moves_about_one_over_n_plus_one():
    before, after = ["w1", "w2", "w3"], ["w1", "w2", "w3", "w4"]
    mv = ring.moved(KEYS, before, after)
    frac = len(mv) / len(KEYS)
    print(f"\n3 -> 4 workers: moved {len(mv)}/{len(KEYS)} = {frac:.4f} (ideal 1/4 = 0.25)")
    assert 0.20 <= frac <= 0.30, f"moved {frac:.2%} of keys, expected about 25%"
    # Every moved key moves *to* the new worker; nothing shuffles between the old ones.
    assert {new for _, _, new in mv} == {"w4"}
# @learn:end test-ring-migration


def test_scale_in_only_moves_the_leaving_workers_keys():
    mv = ring.moved(KEYS, ["w1", "w2", "w3", "w4"], ["w1", "w2", "w3"])
    assert {old for _, old, _ in mv} == {"w4"}


def test_virtual_nodes_spread_the_load():
    rg = ring.HashRing(["w1", "w2", "w3", "w4"])
    counts = [sum(1 for k in KEYS if rg.owner(k) == n) for n in rg.nodes]
    spread = max(counts) / min(counts)
    print(f"\nload per worker {counts}, max/min {spread:.2f}")
    assert spread < 1.35


def test_placement_is_deterministic_and_matches_owner():
    a, b = ring.HashRing(["w2", "w1", "w3"]), ring.HashRing(["w1", "w2", "w3"])
    for k in KEYS[:500]:
        assert a.owner(k) == b.owner(k) == a.place(k).owner
        assert 0 <= a.place(k).angle < 360


def test_modulo_baseline_moves_most_keys():
    """Not a control switch: this documents what hash % N would do, for the README table."""
    before, after = ring.ModuloRing(["w1", "w2", "w3"]), ring.ModuloRing(["w1", "w2", "w3", "w4"])
    frac = sum(1 for k in KEYS if before.owner(k) != after.owner(k)) / len(KEYS)
    print(f"\nhash % N, 3 -> 4: moved {frac:.4f}")
    assert frac > 0.6
    assert statistics.mean([0.0]) == 0.0


import pytest  # noqa: E402


@pytest.mark.live
def test_live_scale_out_moves_about_a_quarter_of_real_record_ids(live):
    import httpx
    out = httpx.post(live.api + "/v1/ring/scale-out", timeout=10).json()
    try:
        assert out["change"]["after"] == ["w1", "w2", "w3", "w4"]
        assert out["keys_checked"] >= 100
        assert 0.15 <= out["moved_fraction"] <= 0.35, out["moved_fraction"]
        assert {m["to"] for m in out["moved_sample"]} == {"w4"}
    finally:
        httpx.post(live.api + "/v1/ring/scale-in", timeout=10)
