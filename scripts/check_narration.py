"""Lint video/narration.json and video/parts.json against the narration rules."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
segs = json.loads((ROOT / "video/narration.json").read_text())
parts = [p["part"] for p in json.loads((ROOT / "video/parts.json").read_text())]
errors = []
if not 25 <= len(segs) <= 45:
    errors.append(f"{len(segs)} segments, want 25-45")
if len({s["id"] for s in segs}) != len(segs):
    errors.append("duplicate ids")
seen: list[str] = []
for s in segs:
    if m := re.search(r"->|==|[_/`*#<>{}=]|[0-9]", s["text"]):
        errors.append(f"{s['id']}: code symbol or digit {m.group(0)!r}")
    if s["part"] not in parts:
        errors.append(f"{s['id']}: unknown part {s['part']}")
    if not seen or seen[-1] != s["part"]:
        if s["part"] in seen:
            errors.append(f"{s['id']}: part {s['part']} is not contiguous")
        if "这一段" not in s["text"]:
            errors.append(f"{s['id']}: first segment of {s['part']} should say what the part is about")
        seen.append(s["part"])
if seen != parts:
    errors.append(f"part order {seen} != parts.json {parts}")
for e in errors:
    print("error:", e)
print(f"{len(segs)} segments, {len(seen)} parts, {len(errors)} problems")
sys.exit(1 if errors else 0)
