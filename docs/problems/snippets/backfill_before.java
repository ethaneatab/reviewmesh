// Before q02: "pending" treated any disagreement between the two columns as dirty,
// and the clean-up ran from any instance.
// @learn:before-backfill
static final String PENDING = "FROM review_tasks t LEFT JOIN reviewers r ON r.id = t.reviewer_id"
        + " WHERE (t.reviewer IS NULL) <> (t.reviewer_id IS NULL)"
        + " OR (t.reviewer IS NOT NULL AND r.handle <> t.reviewer)";

int cleared = db.update("UPDATE review_tasks SET reviewer_id = NULL"
        + " WHERE reviewer IS NULL AND reviewer_id IS NOT NULL");
// @learn:end before-backfill
