-- Staged rollout of the new routing engine, and every change of its traffic share.
CREATE TABLE rollout_state (
    flag        text PRIMARY KEY,
    percent     integer NOT NULL,
    status      text NOT NULL,            -- IDLE | RAMPING | ROLLED_BACK | COMPLETE
    stage_since timestamptz NOT NULL DEFAULT now(),
    fault_rate  double precision NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
INSERT INTO rollout_state(flag, percent, status) VALUES ('routing-v2', 0, 'IDLE');

CREATE TABLE rollout_events (
    id          bigserial PRIMARY KEY,
    flag        text NOT NULL,
    kind        text NOT NULL,            -- START | ADVANCE | ROLLBACK | RESET | FAULT
    from_pct    integer,
    to_pct      integer,
    reason      text NOT NULL,
    error_rate  double precision,
    samples     integer,
    at          timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX rollout_events_by_flag ON rollout_events (flag, id DESC);
