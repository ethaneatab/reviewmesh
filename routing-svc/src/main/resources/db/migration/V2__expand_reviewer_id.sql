-- EXPAND. Purely additive: the old app (phase LEGACY) keeps working, it never looks at these.
CREATE TABLE reviewers (
    id            bigserial PRIMARY KEY,
    handle        text NOT NULL UNIQUE,
    display_name  text
);
ALTER TABLE review_tasks ADD COLUMN reviewer_id bigint;           -- nullable: no table rewrite
-- NOT VALID first, then VALIDATE: on a big table this avoids holding a strong lock while checking rows.
ALTER TABLE review_tasks ADD CONSTRAINT review_tasks_reviewer_fk
    FOREIGN KEY (reviewer_id) REFERENCES reviewers(id) NOT VALID;
ALTER TABLE review_tasks VALIDATE CONSTRAINT review_tasks_reviewer_fk;
CREATE INDEX review_tasks_by_reviewer ON review_tasks (reviewer_id, status) WHERE reviewer_id IS NOT NULL;
