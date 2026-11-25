-- Per-record progress, written only by the worker that owns the record.
-- last_seq is the ordering gate; fence rejects writes from a worker whose lock already expired.
CREATE TABLE intake.workflow_state (
    record_id   text PRIMARY KEY REFERENCES intake.records(id),
    last_seq    integer NOT NULL DEFAULT 0,
    fence       bigint NOT NULL DEFAULT 0,
    owner       text,
    stage       text,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
