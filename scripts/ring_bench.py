"""Measure how many keys move when the ring grows N -> N+1, consistent hashing vs hash % N.

    .venv/bin/python scripts/ring_bench.py      # writes docs/results/ring-bench.md
Five independent key sets of 20 000 random ids each; the table shows the median.
"""
from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rmflow.ring import HashRing, ModuloRing  # noqa: E402


def frac(a, b, keys) -> float:
    return sum(1 for k in keys if a.owner(k) != b.owner(k)) / len(keys)


def spread(rg, keys) -> float:
    c = {n: 0 for n in rg.nodes}
    for k in keys:
        c[rg.owner(k)] += 1
    return max(c.values()) / min(c.values())


def main() -> None:
    sets = []
    for seed in range(5):
        rnd = random.Random(seed)
        sets.append([f"rec_{rnd.getrandbits(64):016x}" for _ in range(20_000)])
    rows = ["| N → N+1 | ideal 1/(N+1) | ring, 32 vnodes | ring, 128 vnodes | ring, 256 vnodes | hash % N | load max/min (128 vnodes, N+1) |",
            "|---|---|---|---|---|---|---|"]
    for n in range(2, 9):
        before = [f"w{i}" for i in range(1, n + 1)]
        after = before + [f"w{n + 1}"]
        cells = []
        for v in (32, 128, 256):
            cells.append(statistics.median(frac(HashRing(before, v), HashRing(after, v), ks) for ks in sets))
        mod = statistics.median(frac(ModuloRing(before), ModuloRing(after), ks) for ks in sets)
        sp = statistics.median(spread(HashRing(after, 128), ks) for ks in sets)
        rows.append(f"| {n} → {n + 1} | {1 / (n + 1):.3f} | " + " | ".join(f"{c:.3f}" for c in cells)
                    + f" | {mod:.3f} | {sp:.2f} |")
    out = ROOT / "docs/results/ring-bench.md"
    out.write_text("# Ring benchmark (scripts/ring_bench.py)\n\nMedian of 5 key sets × 20 000 random record ids. "
                   "Pure computation, no I/O, so the shared colima VM does not affect it.\n\n" + "\n".join(rows) + "\n")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
