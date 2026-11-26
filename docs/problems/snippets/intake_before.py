# Before q07: check, then insert. Two retries that arrive together both see "not found".
# @learn:before-idempotency
def submit(client_id, key, payload):
    seen = db.execute("SELECT response FROM idempotency_keys WHERE client_id=%s AND key=%s", (client_id, key)).fetchone()
    if seen:
        return seen["response"]
    record_id = "rec_" + secrets.token_hex(8)
    db.execute("INSERT INTO records(id, title) VALUES (%s, %s)", (record_id, payload["title"]))
    db.execute("INSERT INTO idempotency_keys(client_id, key, response) VALUES (%s, %s, %s)", (client_id, key, record_id))
    return record_id
# @learn:end before-idempotency
