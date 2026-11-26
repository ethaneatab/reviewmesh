"""EXPLAIN ANALYZE the hot query paths on seeded tables; writes docs/results/explain.md.

    .venv/bin/python scripts/explain_paths.py
Seeds synthetic rows (prefix xp_) into the *test* databases only, never the demo database.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
INTAKE_DSN = "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh_test"
REVIEW_DSN = "postgresql://reviewmesh:reviewmesh-dev@127.0.0.1:54390/reviewmesh_jtest"

PATHS = [
    ("reconciler: records still STORED, oldest first", INTAKE_DSN, "records_stuck_stored",
     "SELECT id FROM intake.records WHERE status = 'STORED' AND updated_at < now() - interval '20 seconds'"
     " ORDER BY updated_at LIMIT 50"),
    ("timeline: every event of one record, in order", INTAKE_DSN, "record_events_by_record",
     "SELECT * FROM intake.record_events WHERE record_id = 'xp_000123' ORDER BY id"),
    ("reviewer queue: open work in one queue, urgent first", REVIEW_DSN, "review_tasks_queue_path",
     "SELECT * FROM review.review_tasks WHERE queue = 'finance' AND status = 'OPEN' ORDER BY priority, created_at LIMIT 50"),
    ("audit trail: one record", REVIEW_DSN, "audit_events_by_record",
     "SELECT * FROM review.audit_events WHERE record_id = 'xp_000123' ORDER BY id"),
]


def seed() -> None:
    with psycopg.connect(INTAKE_DSN, autocommit=True) as c:
        if c.execute("SELECT count(*) FROM intake.records WHERE id LIKE 'xp_%'").fetchone()[0] < 20000:
            c.execute("INSERT INTO intake.records(id, client_id, title, doc_type, status, trace_id, updated_at)"
                      " SELECT 'xp_' || lpad(g::text, 6, '0'), 'xp', 'seed', 'invoice',"
                      " CASE WHEN g % 400 = 0 THEN 'STORED' ELSE 'IN_REVIEW' END, 'x', now() - (g || ' seconds')::interval"
                      " FROM generate_series(1, 20000) g ON CONFLICT DO NOTHING")
            c.execute("INSERT INTO intake.record_events(record_id, seq, stage, actor)"
                      " SELECT 'xp_' || lpad((g % 20000)::text, 6, '0'), 1, 'SEED', 'xp' FROM generate_series(1, 100000) g")
        c.execute("ANALYZE intake.records")
        c.execute("ANALYZE intake.record_events")
    with psycopg.connect(REVIEW_DSN, autocommit=True) as c:
        if c.execute("SELECT to_regclass('review.review_tasks')").fetchone()[0] is None:
            raise SystemExit("run the Java tests once first (they create the review schema in reviewmesh_jtest)")
        if c.execute("SELECT count(*) FROM review.review_tasks WHERE record_id LIKE 'xp_%'").fetchone()[0] < 20000:
            c.execute("INSERT INTO review.review_tasks(record_id, seq, title, doc_type, queue, priority, status)"
                      " SELECT 'xp_' || lpad(g::text, 6, '0'), 1, 'seed', 'invoice',"
                      " (ARRAY['finance','legal','claims','compliance'])[1 + g % 4], 1 + g % 3,"
                      " (ARRAY['OPEN','APPROVED','REJECTED','APPROVED','APPROVED'])[1 + g % 5]"
                      " FROM generate_series(1, 20000) g ON CONFLICT DO NOTHING")
            c.execute("INSERT INTO review.audit_events(record_id, action, actor)"
                      " SELECT 'xp_' || lpad((g % 20000)::text, 6, '0'), 'SEED', 'xp' FROM generate_series(1, 100000) g")
        c.execute("ANALYZE review.review_tasks")
        c.execute("ANALYZE review.audit_events")


def explain(dsn: str, sql: str) -> str:
    with psycopg.connect(dsn) as c:
        return "\n".join(r[0] for r in c.execute("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) " + sql))


def main() -> list[tuple[str, str, str]]:
    seed()
    out = []
    md = ["# Query paths (scripts/explain_paths.py)\n",
          "20 000 synthetic records / tasks and 100 000 events in the test databases, `ANALYZE` first. "
          "Plans are from `EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF)`.\n"]
    for title, dsn, index, sql in PATHS:
        plan = explain(dsn, sql)
        out.append((title, index, plan))
        md += [f"## {title}\n", f"expected index: `{index}`\n", "```sql", sql, "```", "```text", plan, "```\n"]
    (ROOT / "docs/results/explain.md").write_text("\n".join(md))
    return out


if __name__ == "__main__":
    for title, index, plan in main():
        print(f"{title}: {'uses ' + index if index in plan else 'DOES NOT USE ' + index}")
    sys.exit(0)
