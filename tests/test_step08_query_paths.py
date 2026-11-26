"""Step 08: each hot query is served by the index designed for it (EXPLAIN on 20k seeded rows)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

spec = importlib.util.spec_from_file_location("explain_paths", Path(__file__).resolve().parent.parent / "scripts/explain_paths.py")
assert spec and spec.loader
xp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(xp)


def _review_schema_exists() -> bool:
    with psycopg.connect(xp.REVIEW_DSN) as c:
        return c.execute("SELECT to_regclass('review.review_tasks')").fetchone()[0] is not None


# @learn:test-explain
@pytest.mark.parametrize("title,dsn,index,sql", xp.PATHS, ids=[p[2] for p in xp.PATHS])
def test_hot_query_uses_its_index(title, dsn, index, sql):
    if dsn == xp.REVIEW_DSN and not _review_schema_exists():
        pytest.skip("Java tests have not created the review schema yet")
    xp.seed()
    plan = xp.explain(dsn, sql)
    assert index in plan, f"{title}\n{plan}"
    assert "Seq Scan" not in plan, plan
# @learn:end test-explain
