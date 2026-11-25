# Ring benchmark (scripts/ring_bench.py)

Median of 5 key sets × 20 000 random record ids. Pure computation, no I/O, so the shared colima VM does not affect it.

| N → N+1 | ideal 1/(N+1) | ring, 32 vnodes | ring, 128 vnodes | ring, 256 vnodes | hash % N | load max/min (128 vnodes, N+1) |
|---|---|---|---|---|---|---|
| 2 → 3 | 0.333 | 0.352 | 0.317 | 0.337 | 0.667 | 1.13 |
| 3 → 4 | 0.250 | 0.221 | 0.277 | 0.253 | 0.751 | 1.24 |
| 4 → 5 | 0.200 | 0.161 | 0.175 | 0.193 | 0.800 | 1.29 |
| 5 → 6 | 0.167 | 0.168 | 0.150 | 0.165 | 0.834 | 1.32 |
| 6 → 7 | 0.143 | 0.121 | 0.150 | 0.156 | 0.857 | 1.40 |
| 7 → 8 | 0.125 | 0.131 | 0.129 | 0.131 | 0.873 | 1.37 |
| 8 → 9 | 0.111 | 0.107 | 0.103 | 0.105 | 0.889 | 1.40 |
