-- CONTRACT. Only after every instance runs NEW_ONLY and the backfill reports zero pending rows.
-- The guard makes an early contract fail loudly instead of silently dropping reviewer names.
-- @learn:contract-guard
DO $$
DECLARE pending bigint;
BEGIN
    SELECT count(*) INTO pending FROM review_tasks t LEFT JOIN reviewers r ON r.id = t.reviewer_id
     WHERE t.reviewer IS NOT NULL AND (t.reviewer_id IS NULL OR r.handle <> t.reviewer);
    IF pending > 0 THEN
        RAISE EXCEPTION 'contract blocked: % review_tasks rows are not backfilled (POST /v1/migration/backfill)', pending;
    END IF;
END $$;
-- @learn:end contract-guard
ALTER TABLE review_tasks DROP COLUMN reviewer;
