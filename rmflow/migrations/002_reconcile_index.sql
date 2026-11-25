-- Reconciler query path: "records still STORED, oldest first". Partial, so it stays tiny.
CREATE INDEX records_stuck_stored ON intake.records (updated_at) WHERE status = 'STORED';
