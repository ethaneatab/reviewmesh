"""Create N metadata-only records (no document, never processed) so the ring page has keys to place.

    .venv/bin/python scripts/seed_records.py 600
"""
from __future__ import annotations

import sys
import uuid

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from rmflow import db, intake  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 600
db.migrate()
with db.tx() as conn:
    have = conn.execute("SELECT count(*) AS n FROM intake.records WHERE client_id='ring-seed'").fetchone()["n"]
for i in range(have, n):
    intake.submit("ring-seed", f"seed-{i:05d}-{uuid.uuid5(uuid.NAMESPACE_URL, str(i)).hex[:8]}",
                  {"title": f"[seed] key {i}", "doc_type": "kyc", "fields": {}})
print(f"ring-seed records: {max(n, have)}")
