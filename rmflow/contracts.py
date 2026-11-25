"""Compare a JSON value with a contract snapshot by shape: same keys, same JSON types."""
from __future__ import annotations

import json
from typing import Any

from .config import ROOT


def load(name: str) -> dict[str, Any]:
    return dict(json.loads((ROOT / "contracts" / name).read_text()))


def shape(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if v is None:
        return "null"
    return "string"


def breaking_changes(snapshot: Any, actual: Any, path: str = "$") -> list[str]:
    """What an old client would trip over: a field that vanished or changed type. Extra fields are fine."""
    out: list[str] = []
    if isinstance(snapshot, dict):
        if not isinstance(actual, dict):
            return [f"{path}: object became {shape(actual)}"]
        for k, sv in snapshot.items():
            if k not in actual:
                out.append(f"{path}.{k}: removed")
            else:
                out += breaking_changes(sv, actual[k], f"{path}.{k}")
        return out
    if snapshot is None or actual is None:
        return out
    s, a = shape(snapshot), shape(actual)
    if isinstance(snapshot, list):
        if not isinstance(actual, list):
            return [f"{path}: list became {a}"]
        return breaking_changes(snapshot[0], actual[0], f"{path}[0]") if snapshot and actual else []
    if s != a and not ({s, a} <= {"integer", "number"}):
        out.append(f"{path}: {s} became {a}")
    return out
