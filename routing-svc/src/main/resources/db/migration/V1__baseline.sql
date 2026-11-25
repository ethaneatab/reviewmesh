-- Java side of the workflow: routing decisions, the reviewer queue, the audit trail, logins.
-- review_tasks.reviewer is a plain text column on purpose: chapter 06 migrates it to a foreign key.
CREATE TABLE users (
    username       text PRIMARY KEY,
    password_hash  text NOT NULL,
    role           text NOT NULL,
    display_name   text NOT NULL
);

CREATE TABLE routing_decisions (
    id           bigserial PRIMARY KEY,
    decision_id  text NOT NULL UNIQUE,
    record_id    text NOT NULL,
    seq          integer NOT NULL,
    engine       text NOT NULL,
    queue        text NOT NULL,
    priority     integer NOT NULL,
    reason       text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX routing_decisions_by_record ON routing_decisions (record_id, id);

CREATE TABLE review_tasks (
    id               bigserial PRIMARY KEY,
    record_id        text NOT NULL UNIQUE,
    seq              integer NOT NULL,
    title            text NOT NULL,
    doc_type         text NOT NULL,
    s3_key           text,
    queue            text NOT NULL,
    priority         integer NOT NULL,
    status           text NOT NULL,
    decision_id      text,
    reviewer         text,
    decision_reason  text,
    trace_id         text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
-- Reviewer queue read path: one queue, open work, most urgent first, oldest first.
CREATE INDEX review_tasks_queue_path ON review_tasks (queue, status, priority, created_at);

-- Dedup for the SQS handoff: a (record, seq) is taken in exactly once.
CREATE TABLE handoff_inbox (
    record_id    text NOT NULL,
    seq          integer NOT NULL,
    message_id   text NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (record_id, seq)
);

-- Append-only audit trail. Read path: everything about one record, in order.
CREATE TABLE audit_events (
    id           bigserial PRIMARY KEY,
    record_id    text NOT NULL,
    seq          integer,
    task_id      bigint,
    action       text NOT NULL,
    actor        text NOT NULL,
    from_status  text,
    to_status    text,
    detail       jsonb NOT NULL DEFAULT '{}'::jsonb,
    at           timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX audit_events_by_record ON audit_events (record_id, id);

-- Transactional outbox: a decision and its outgoing message commit together; a poller sends it.
CREATE TABLE decision_outbox (
    id            bigserial PRIMARY KEY,
    record_id     text NOT NULL,
    payload       jsonb NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz,
    message_id    text
);
CREATE INDEX decision_outbox_pending ON decision_outbox (id) WHERE published_at IS NULL;
