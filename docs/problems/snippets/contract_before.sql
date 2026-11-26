-- Before q03: the contract step was a bare DROP. Run early, it silently loses reviewer names.
-- @learn:before-contract
ALTER TABLE review_tasks DROP COLUMN reviewer;
-- @learn:end before-contract
