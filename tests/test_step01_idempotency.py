"""Step 01: a client retry must never create a second record."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

from rmflow import db

BODY = {"title": "Invoice 4471", "doc_type": "invoice", "fields": {"amount": "1200.50", "vendor": "Northwind"}}


def _post(client, token: str, key: str, body: dict | None = None):
    return client.post("/v1/records", json=body or BODY,
                       headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key})


def test_retry_replays_the_first_answer(client, submitter_token):
    key = "k-" + uuid.uuid4().hex
    first = _post(client, submitter_token, key)
    again = _post(client, submitter_token, key)
    assert first.status_code == 201
    assert again.status_code == 200 and again.headers["Idempotent-Replay"] == "true"
    assert again.json() == first.json()


def test_concurrent_retries_create_exactly_one_record(client, submitter_token):
    """Eight copies of the same request at once, like a client that timed out and retried hard."""
    key = "k-" + uuid.uuid4().hex
    title = "Retry storm " + key
    with ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(lambda _: _post(client, submitter_token, key, {**BODY, "title": title}), range(8)))
    ids = {r.json()["record_id"] for r in codes}
    with db.tx() as conn:
        n = conn.execute("SELECT count(*) AS n FROM intake.records WHERE title=%s", (title,)).fetchone()["n"]
    assert n == 1, f"{n} records for one idempotency key"
    assert len(ids) == 1
    assert sorted(r.status_code for r in codes) == [200] * 7 + [201]


def test_same_key_different_body_is_refused(client, submitter_token):
    key = "k-" + uuid.uuid4().hex
    assert _post(client, submitter_token, key).status_code == 201
    other = {**BODY, "title": "Something else"}
    assert _post(client, submitter_token, key, other).status_code == 422


def test_missing_key_or_token_is_rejected(client, submitter_token):
    r = client.post("/v1/records", json=BODY, headers={"Authorization": f"Bearer {submitter_token}"})
    assert r.status_code == 400
    r = client.post("/v1/records", json=BODY, headers={"Idempotency-Key": "k-12345678"})
    assert r.status_code == 401


def test_revision_gets_next_seq_once(client, submitter_token):
    rid = _post(client, submitter_token, "k-" + uuid.uuid4().hex).json()["record_id"]
    hdr = {"Authorization": f"Bearer {submitter_token}", "Idempotency-Key": "rev-" + uuid.uuid4().hex}
    a = client.post(f"/v1/records/{rid}/revisions", json=BODY, headers=hdr)
    b = client.post(f"/v1/records/{rid}/revisions", json=BODY, headers=hdr)
    assert a.json()["seq"] == 2 and b.json()["seq"] == 2
    assert [v["seq"] for v in client.get(f"/v1/records/{rid}").json()["versions"]] == [1, 2]
