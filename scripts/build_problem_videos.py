"""video/problems.src.json -> video/problems.walk.json for the line-by-line walkthrough renderer.

Code is never copied into the JSON by hand: code_from / before_from point at @learn anchors and the
code is cut from the source here. Checks: line numbers in range, every segment's lines printed for a
human to eyeball, and narration free of code symbols and ASCII digits.

    .venv/bin/python scripts/build_problem_videos.py           # build + print
    .venv/bin/python scripts/build_problem_videos.py --show ID  # print one anchor with line numbers
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from learn_anchors import ROOT, scan  # noqa: E402

SRC = ROOT / "video/problems.src.json"
OUT = ROOT / "video/problems.walk.json"
BAD = re.compile(r"->|==|[_/`{}<>;=]|[0-9]")


def cut(anchors: dict, ref: dict) -> list[str]:
    a = anchors[ref["anchor"]]
    if a["path"] != ref["path"]:
        raise SystemExit(f"{ref['anchor']} lives in {a['path']}, not {ref['path']}")
    lines = (ROOT / a["path"]).read_text(encoding="utf-8").splitlines()[a["start"] - 1:a["end"]]
    pad = min((len(x) - len(x.lstrip()) for x in lines if x.strip()), default=0)
    return [x[pad:] for x in lines]


def check_segments(pid: str, kind: str, segs: list[dict], code: list[str], errors: list[str]) -> None:
    for i, s in enumerate(segs):
        for n in s["lines"]:
            if not 1 <= n <= len(code):
                errors.append(f"{pid} {kind}[{i}]: line {n} outside 1..{len(code)}")
        if m := BAD.search(s["text"]):
            errors.append(f"{pid} {kind}[{i}]: narration has code symbol or digit {m.group(0)!r}: {s['text']}")
        shown = " | ".join(code[n - 1].strip() for n in s["lines"] if 1 <= n <= len(code))
        print(f"  {kind}[{i}] {s['lines']}: {shown[:110]}")


def main() -> int:
    anchors, errs = scan()
    if errs:
        print("\n".join(errs))
        return 1
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        for n, line in enumerate(cut(anchors, {"anchor": sys.argv[2], "path": anchors[sys.argv[2]]["path"]}), 1):
            print(f"{n:3} {line}")
        return 0
    problems = json.loads(SRC.read_text())
    errors: list[str] = []
    out = []
    for p in problems:
        print(f"{p['id']}: {p['title']}")
        code = cut(anchors, p["code_from"])
        before = cut(anchors, p["before_from"]) if p.get("before_from") else []
        if not 6 <= len(p["segments"]) + len(p.get("before_segments", [])) <= 14:
            errors.append(f"{p['id']}: needs 6-14 segments in total")
        check_segments(p["id"], "segments", p["segments"], code, errors)
        check_segments(p["id"], "before_segments", p.get("before_segments", []), before, errors)
        for k in ("title", "subtitle"):
            if re.search(r"[_/`=<>]", p[k]):
                errors.append(f"{p['id']}: {k} has a code symbol")
        out.append({"id": p["id"], "title": p["title"], "subtitle": p["subtitle"], "lang": p["lang"],
                    "code": "\n".join(code), "segments": p["segments"],
                    "example_code": "\n".join(before), "example_segments": p.get("before_segments", [])})
    for e in errors:
        print("error:", e)
    if errors:
        return 1
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(out)} problems -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
