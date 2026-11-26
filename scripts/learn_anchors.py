"""Scan the source for @learn anchors and write frontend/src/generated/anchors.json.

An anchor is two comment lines around a block:
    # @learn:order-gate          (or // or --)
    ...code...
    # @learn:end order-gate
start/end in the JSON are the first and last line *between* the two markers (1-based).

    .venv/bin/python scripts/learn_anchors.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend/src/generated/anchors.json"
SCAN = ["rmflow", "lambdas", "routing-svc/src", "frontend/src", "tests", "e2e", "scripts", "ops", "docs/problems/snippets"]
EXT = {".py", ".java", ".ts", ".tsx", ".sql", ".mjs", ".yml"}
OPEN = re.compile(r"(?:#|//|--)\s*@learn:(?!end\b)([a-z0-9][a-z0-9-]*)\s*$")
CLOSE = re.compile(r"(?:#|//|--)\s*@learn:end\s+([a-z0-9][a-z0-9-]*)\s*$")


def scan() -> tuple[dict[str, dict[str, object]], list[str]]:
    found: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    for top in SCAN:
        for f in sorted((ROOT / top).rglob("*")):
            if f.suffix not in EXT or "generated" in f.parts or "node_modules" in f.parts or "target" in f.parts:
                continue
            rel = f.relative_to(ROOT).as_posix()
            if rel in ("scripts/learn_anchors.py", "scripts/check_anchors.py"):
                continue
            opened: dict[str, int] = {}
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if m := OPEN.search(line):
                    opened[m.group(1)] = n
                elif m := CLOSE.search(line):
                    aid = m.group(1)
                    if aid not in opened:
                        errors.append(f"{rel}:{n}: end without start for {aid}")
                        continue
                    if aid in found:
                        errors.append(f"{rel}:{n}: duplicate anchor {aid} (also in {found[aid]['path']})")
                    found[aid] = {"path": rel, "start": opened.pop(aid) + 1, "end": n - 1}
            errors += [f"{rel}:{n}: start without end for {aid}" for aid, n in opened.items()]
    return dict(sorted(found.items())), errors


def render(found: dict[str, dict[str, object]]) -> str:
    return json.dumps(found, indent=2) + "\n"


def main() -> int:
    found, errors = scan()
    for e in errors:
        print("error:", e)
    if errors:
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(found))
    print(f"{len(found)} anchors -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
