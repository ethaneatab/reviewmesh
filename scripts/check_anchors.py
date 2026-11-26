"""Fail if an anchor the UI, the videos or the docs point at is missing, misplaced or stale.

Checks: (1) every referenced id exists; (2) the marker lines really sit right outside start/end;
(3) frontend/src/generated/anchors.json equals a fresh scan.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from learn_anchors import OUT, ROOT, render, scan  # noqa: E402

REF_PATTERNS = [
    (ROOT / "frontend/src", re.compile(r"""anchor[=:]\s*["'{]\s*["']?([a-z0-9-]+)["']""")),
    (ROOT / "docs", re.compile(r"锚点 `([a-z0-9-]+)`")),
]


def references() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for base, pat in REF_PATTERNS:
        for f in base.rglob("*"):
            if f.is_file() and f.suffix in {".ts", ".tsx", ".md"} and "generated" not in f.parts:
                for m in pat.finditer(f.read_text(encoding="utf-8")):
                    refs.setdefault(m.group(1), []).append(f.relative_to(ROOT).as_posix())
    src = ROOT / "video/problems.src.json"
    if src.exists():
        for p in json.loads(src.read_text()):
            for k in ("code_from", "before_from"):
                if p.get(k):
                    refs.setdefault(p[k]["anchor"], []).append("video/problems.src.json")
    return refs


def main() -> int:
    found, errors = scan()
    for aid, a in found.items():
        lines = (ROOT / str(a["path"])).read_text(encoding="utf-8").splitlines()
        s, e = int(a["start"]), int(a["end"])
        if not (f"@learn:{aid}" in lines[s - 2] and f"@learn:end {aid}" in lines[e]):
            errors.append(f"{aid}: markers not at lines {s - 1}/{e + 1} of {a['path']}")
        if e < s:
            errors.append(f"{aid}: empty anchor")
    for aid, where in sorted(references().items()):
        if aid not in found:
            errors.append(f"{aid}: referenced from {sorted(set(where))} but no such anchor")
    if not OUT.exists() or OUT.read_text() != render(found):
        errors.append(f"{OUT.relative_to(ROOT)} is stale: run scripts/learn_anchors.py")
    for e in errors:
        print("error:", e)
    print(f"{len(found)} anchors, {len(references())} referenced ids, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
