-- Intake side of the workflow. Owned by the Python services; the Java side has its own schema.
CREATE TABLE intake.records (
    id           text PRIMARY KEY,
    client_id    text NOT NULL,
    title        text NOT NULL,
    doc_type     text NOT NULL,
    status       text NOT NULL,
    latest_seq   integer NOT NULL DEFAULT 1,
    trace_id     text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- One row per submitted version; seq orders the steps of a record.
CREATE TABLE intake.record_versions (
    record_id   text NOT NULL REFERENCES intake.records(id),
    seq         integer NOT NULL,
    fields      jsonb NOT NULL,
    doc_sha256  text,
    s3_key      text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (record_id, seq)
);

-- Client retries carry the same key; the primary key is the guard.
CREATE TABLE intake.idempotency_keys (
    client_id       text NOT NULL,
    key             text NOT NULL,
    request_sha256  text NOT NULL,
    record_id       text NOT NULL,
    seq             integer NOT NULL,
    response        jsonb NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (client_id, key)
);

-- Append-only handoff timeline. Read path: all events of one record in order.
CREATE TABLE intake.record_events (
    id         bigserial PRIMARY KEY,
    record_id  text NOT NULL,
    seq        integer NOT NULL,
    stage      text NOT NULL,
    actor      text NOT NULL,
    detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
    at         timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX record_events_by_record ON intake.record_events (record_id, id);
