"""Consistent hashing with virtual nodes, plus the naive `hash % N` it replaces.

Each worker owns `vnodes` points on a 64-bit ring. A key belongs to the first point clockwise
from its own hash. Adding a worker only takes over the arcs in front of its new points, so about
1/(N+1) of keys move; `hash % N` reshuffles almost everything.
"""
from __future__ import annotations

import bisect
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from . import lab

SPACE = 2**64
DEFAULT_VNODES = 128


def h64(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


@dataclass(frozen=True)
class Placement:
    key: str
    hash: int
    angle: float          # 0..360, for the ring picture
    owner: str
    vnode: str            # which virtual node caught it, e.g. "w2#17"
    vnode_angle: float


# @learn:ring-lookup
class HashRing:
    kind = "consistent"

    def __init__(self, nodes: Iterable[str], vnodes: int = DEFAULT_VNODES):
        self.nodes = tuple(sorted(set(nodes)))
        self.vnodes = vnodes
        pts = sorted((h64(f"{n}#{i}"), n, i) for n in self.nodes for i in range(vnodes))
        self._hashes = [p[0] for p in pts]
        self._points = pts

    def _index(self, key_hash: int) -> int:
        # First virtual node clockwise from the key; wrap around past the top of the ring.
        return bisect.bisect_right(self._hashes, key_hash) % len(self._hashes)

    def owner(self, key: str) -> str:
        if not self.nodes:
            raise LookupError("empty ring")
        return self._points[self._index(h64(key))][1]
# @learn:end ring-lookup

    def place(self, key: str) -> Placement:
        kh = h64(key)
        ph, node, i = self._points[self._index(kh)]
        return Placement(key, kh, kh * 360 / SPACE, node, f"{node}#{i}", ph * 360 / SPACE)

    def points(self) -> list[dict[str, object]]:
        return [{"node": n, "vnode": i, "angle": round(h * 360 / SPACE, 4)} for h, n, i in self._points]


class ModuloRing:
    """What most first versions do. Kept only as the failing control (RM_LAB_SABOTAGE=modulo_hash)."""
    kind = "modulo"

    def __init__(self, nodes: Iterable[str], vnodes: int = 1):
        self.nodes = tuple(sorted(set(nodes)))
        self.vnodes = 1

    def owner(self, key: str) -> str:
        return self.nodes[h64(key) % len(self.nodes)]

    def place(self, key: str) -> Placement:
        kh = h64(key)
        return Placement(key, kh, kh * 360 / SPACE, self.owner(key), self.owner(key), 0.0)

    def points(self) -> list[dict[str, object]]:
        return [{"node": n, "vnode": 0, "angle": round(i * 360 / len(self.nodes), 4)} for i, n in enumerate(self.nodes)]


def make_ring(nodes: Iterable[str], vnodes: int = DEFAULT_VNODES) -> HashRing | ModuloRing:
    if lab.sabotaged("modulo_hash"):
        return ModuloRing(nodes)
    return HashRing(nodes, vnodes)


def moved(keys: Sequence[str], before: Iterable[str], after: Iterable[str], vnodes: int = DEFAULT_VNODES) -> list[tuple[str, str, str]]:
    """Keys whose owner changed between two memberships: (key, old owner, new owner)."""
    a, b = make_ring(before, vnodes), make_ring(after, vnodes)
    out = []
    for k in keys:
        o, n = a.owner(k), b.owner(k)
        if o != n:
            out.append((k, o, n))
    return out
